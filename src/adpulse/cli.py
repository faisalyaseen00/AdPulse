"""AdPulse command line: `adpulse --help`."""
from __future__ import annotations

import logging
import subprocess
import sys

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

from .config import PROJECT_ROOT, get_settings

app = typer.Typer(add_completion=False, help="AdPulse - marketing data agent on ClickHouse.")
console = Console()


def _llm_or_none():
    from .llm import LLMError, get_llm
    try:
        return get_llm()
    except LLMError:
        return None


@app.command("init-db")
def init_db():
    """Create warehouse tables and the read-only agent user."""
    from . import warehouse
    warehouse.init_db()
    console.print("[green]✓[/] warehouse initialised")


@app.command("demo-data")
def demo_data(days: int = 180, seed: int = 42):
    """Generate the demo dataset (CSV per Airbyte stream) into data/demo/."""
    from .pipeline import demo_data as gen
    counts = gen.generate(get_settings().demo_dir, days=days, seed=seed)
    for k, v in counts.items():
        console.print(f"  {k:<28} {v:>9,} rows")


@app.command()
def ingest(mode: str = typer.Option("auto", help="auto | airbyte | direct")):
    """Land source data in ClickHouse raw tables."""
    from .pipeline import ingest as ing
    ing.ingest(mode, progress=console.print)


@app.command()
def transform():
    """Rebuild the modeled tables (dim_/fct_/mart_)."""
    from .pipeline import transform as tr
    tr.run_models(progress=console.print)


@app.command()
def sync(mode: str = typer.Option("auto", help="auto | airbyte | direct")):
    """init-db + ingest + transform."""
    init_db()
    ingest(mode)
    transform()


@app.command()
def setup(mode: str = typer.Option("direct", help="auto | airbyte | direct")):
    """One-shot local setup: demo data -> warehouse -> models -> first recommendations."""
    demo_data()
    sync(mode)
    recommend()


@app.command()
def bootstrap(wait: int = typer.Option(120, help="Seconds to wait for ClickHouse")):
    """Server start-up: wait for ClickHouse, create schema + read-only user, load demo data only if empty."""
    import time

    from . import warehouse
    deadline = time.monotonic() + wait
    while not (h := warehouse.ping()).ok:
        if "authentication" in h.error.lower() or time.monotonic() > deadline:
            console.print(f"[red]ClickHouse not reachable:[/] {h.error[:300]}")
            raise typer.Exit(1)
        time.sleep(2)
    warehouse.init_db()
    console.print("[green]✓[/] schema and read-only user ready")
    try:
        n = int(warehouse.query_df("SELECT count() AS n FROM fct_ad_daily").iloc[0]["n"])
    except Exception:  # noqa: BLE001
        n = 0
    if n:
        console.print(f"[green]✓[/] warehouse already has data ({n:,} ad-day rows), nothing to load")
        return
    console.print("empty warehouse: loading the demo dataset")
    from .pipeline import ingest as ing
    from .pipeline import transform as tr
    if not (get_settings().demo_dir / "meta_ads_insights.csv").exists():
        demo_data()
    ing.ingest("direct", progress=console.print)
    tr.run_models(progress=console.print)
    recommend()


@app.command()
def ask(question: str):
    """Ask the agent a question in plain English."""
    from .agent.core import AdPulseAgent
    llm = _llm_or_none()
    if llm is None:
        console.print("[red]No LLM configured.[/] Set GROQ_API_KEY, ANTHROPIC_API_KEY or OPENROUTER_API_KEY (and LLM_PROVIDER) in .env")
        raise typer.Exit(1)
    with console.status("thinking…"):
        ans = AdPulseAgent(llm).ask(question)
    for st in ans.steps:
        icon = {"ok": "[green]✓[/]", "retry": "[yellow]↻[/]", "fail": "[red]✗[/]"}.get(st.status, "•")
        console.print(f" {icon} {st.name}: [dim]{st.detail[:140]}[/]")
    if not ans.ok:
        console.print(f"[red]{ans.error}[/]")
        raise typer.Exit(1)
    console.print(Panel(Markdown(f"**{ans.headline}**\n\n{ans.answer_markdown}"),
                        title="verified ✓" if ans.verified else "needs review", border_style="green" if ans.verified else "yellow"))
    console.print(Panel(ans.sql, title="SQL", border_style="dim"))


@app.command()
def audit(days: int = 30, save: bool = typer.Option(False, help="Queue flagged terms as negative keywords")):
    """Google search term audit."""
    from .actions import recommendations as recs
    from .audit import search_terms
    df = search_terms.audit(days, llm=_llm_or_none())
    s = search_terms.summary(df)
    t = Table("search term", "campaign", "cost", "conv", "intent", "negative")
    for r in df[df["flagged"]].itertuples():
        t.add_row(r.search_term, r.campaign_name, f"${r.cost:,.2f}", f"{r.conversions:.0f}", r.intent, r.suggested_negative)
    console.print(t)
    console.print(f"[bold]{s['flagged']}[/] of {s['terms']} terms flagged · wasted "
                  f"[red]${s['wasted_spend']:,.2f}[/] ({s['wasted_share']:.1%} of search spend)")
    if save:
        n = recs.save(recs.audit_recommendations(df))
        console.print(f"[green]✓[/] queued {n} negative keyword recommendation(s) for approval")


@app.command()
def recommend(window: int = 30,
              refresh: bool = typer.Option(False, help="Rebuild waiting suggestions with current wording/numbers")):
    """Generate pause/scale recommendations (pending human approval)."""
    from .actions import recommendations as recs
    if refresh:
        console.print(f"[green]✓[/] refreshed: {recs.refresh_pending(window)} suggestion(s) waiting for approval")
        return
    found = recs.rule_recommendations(window)
    n = recs.save(found)
    console.print(f"[green]✓[/] {len(found)} recommendation(s) found, {n} new queued for approval")


@app.command()
def report(send: bool = typer.Option(False, help="Deliver the report"), days: int = 7,
           slack: bool = typer.Option(True, help="Include Slack when sending"),
           email: bool = typer.Option(True, help="Include email when sending")):
    """Build the weekly report (and optionally send it): `adpulse report --send --no-slack` emails only."""
    from .reports import weekly
    rep = weekly.build(days=days, llm=_llm_or_none())
    console.print(Markdown(weekly.to_markdown(rep)))
    if send:
        results = weekly.deliver(rep, slack=slack, email=email)
        for ch, res in results.items():
            console.print(f"  {ch}: {res}")
        if any(v.startswith("error") for v in results.values()):
            raise typer.Exit(1)
    else:
        weekly.save(rep, [], "generated")


@app.command()
def scheduler(once: bool = typer.Option(False, help="Run the weekly job now and exit"),
              dry_run: bool = typer.Option(False, help="With --once: build and save, but don't send"),
              show: bool = typer.Option(False, "--next", help="Print the next scheduled run and exit")):
    """Send the weekly report on schedule (REPORT_SCHEDULE_DAY / _TIME / REPORT_TIMEZONE). Runs until stopped."""
    from datetime import datetime, timezone

    from . import scheduler as sch
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    sched = sch.Schedule.from_settings()
    if show:
        console.print(f"schedule: {sched.describe()}\nnext run: {sched.next_run(datetime.now(timezone.utc)):%A %Y-%m-%d %H:%M %Z}")
        return
    if once:
        res = sch.run_weekly(send=not dry_run)
        for ch, r in res.items():
            console.print(f"  {ch}: {r}")
        if any(v.startswith("error") for v in res.values()):
            raise typer.Exit(1)
        return
    sch.serve()


@app.command()
def ui(port: int = 8501):
    """Launch the Streamlit app."""
    subprocess.run([sys.executable, "-m", "streamlit", "run", str(PROJECT_ROOT / "app" / "main.py"),
                    "--server.port", str(port)], check=False)


def main():  # pragma: no cover
    logging.basicConfig(level=logging.WARNING)
    app()


if __name__ == "__main__":  # pragma: no cover
    main()

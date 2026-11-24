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
def recommend(window: int = 30):
    """Generate pause/scale recommendations (pending human approval)."""
    from .actions import recommendations as recs
    found = recs.rule_recommendations(window)
    n = recs.save(found)
    console.print(f"[green]✓[/] {len(found)} recommendation(s) found, {n} new queued for approval")


@app.command()
def report(send: bool = typer.Option(False, help="Deliver to Slack / email"), days: int = 7):
    """Build the weekly report (and optionally send it)."""
    from .reports import weekly
    rep = weekly.build(days=days, llm=_llm_or_none())
    console.print(Markdown(weekly.to_markdown(rep)))
    if send:
        for ch, res in weekly.deliver(rep).items():
            console.print(f"  {ch}: {res}")
    else:
        weekly.save(rep, [], "generated")


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

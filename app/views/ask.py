import html
import numbers

import pandas as pd
import plotly.express as px
import streamlit as st
import ui

from adpulse.actions import recommendations as recs
from adpulse.agent.core import AdPulseAgent, AgentAnswer, Turn
from adpulse.config import get_settings
from adpulse.llm import LLMError, get_llm

SUGGESTIONS = [
    "Which ads brought in the most valuable customers last month?",
    "How much does it cost to win a new customer on Meta vs Google, month by month?",
    "Which ads are losing money right now?",
    "How much did we waste on Google searches that never led to a sale last month?",
    "Compare Meta and Google this quarter: spend, new customers and what those customers are worth",
]

ui.hero("Ask a question", "Ask anything about your ads in your own words. Every number in the answer is "
        "checked against your real data before you see it.")
if not ui.require_warehouse():
    st.stop()

settings = get_settings()
if not settings.llm_configured:
    st.warning("**The AI assistant is switched off.** Add an AI key (for example `GROQ_API_KEY`) to the app "
               "settings, then restart the app.", icon="🔑")
    st.stop()


@st.cache_resource(show_spinner=False)
def agent() -> AdPulseAgent:
    return AdPulseAgent(get_llm())


st.session_state.setdefault("chat", [])
chat: list[AgentAnswer] = st.session_state.chat


def render_answer(a: AgentAnswer, idx: int) -> None:
    if not a.ok:
        st.error("I couldn't answer that one. Try asking it a different way, or ask about a specific ad, "
                 "campaign or time period.")
        with st.expander("Behind the scenes"):
            st.caption(a.error)
            render_steps(a)
        return
    n, ok = a.numbers_checked, a.numbers_verified
    if a.verified:
        trust = ("✓ Checked: every number below matches your data", "good")
    elif n and ok < n:
        trust = (f"Read with care: {n - ok} number(s) couldn't be matched to your data", "warn")
    else:
        trust = ("Read with care: this answer needs a second look", "warn")
    ui.badges(trust, (f"Answered in {a.latency_ms / 1000:.0f} seconds", "muted"))
    st.markdown(ui.md(f"### {a.headline}"))
    st.markdown(ui.md(a.answer_markdown))
    if a.caveats:
        st.caption(ui.md("Good to know: " + " ".join(c.rstrip(".") + "." for c in a.caveats)))

    tabs = st.tabs(["Chart", "Table"])
    with tabs[0]:
        render_chart(a)
    with tabs[1]:
        st.dataframe(ui.friendly_df(a.data), hide_index=True, width="stretch")
        st.download_button("Download as spreadsheet (CSV)", a.data.to_csv(index=False), f"adpulse_{a.id}.csv",
                           "text/csv", key=f"dl_{a.id}")

    with st.expander("Behind the scenes: how this answer was worked out"):
        st.markdown(ui.md(f"**Approach.** {a.reasoning}"))
        if a.critic and a.critic.verdict == "fail":
            st.warning("The reviewer step still had concerns: " + "; ".join(a.critic.issues))
        st.markdown("**Number check.** Each number in the answer is looked up in the results:")
        if not a.number_checks:
            st.caption("The answer quotes no numbers.")
        for c in a.number_checks:
            st.markdown(f"{'✅' if c.verified else '❌'} `{c.text}` "
                        f"{('found in ' + c.source) if c.verified else 'not found in the results'}")
        st.markdown("**Database query** (read-only; it can't change anything):")
        st.code(a.sql, language="sql")
        if a.assumptions:
            st.caption("Assumptions: " + " ".join(x.rstrip(".") + "." for x in a.assumptions))
        st.markdown("**Steps**")
        render_steps(a)

    if a.suggested_actions:
        st.markdown("**Suggested next steps.** Add one to your suggestions list; nothing changes until you approve it.")
        econ = ui.ad_economics(30).set_index("ad_name")
        for j, s in enumerate(a.suggested_actions):
            c1, c2 = st.columns([5, 1.3])
            kind = {"pause_ad": ("Pause this ad", "bad"), "scale_ad": ("Give it more budget", "good"),
                    "investigate": ("Worth a closer look", "info")}[s.action]
            c1.html(f'{ui.badge(kind[0], kind[1])} <b>{html.escape(s.ad_name)}</b> '
                    f'<span class="ap-muted">on {s.platform.title()}: {html.escape(s.rationale)}</span>')
            key = f"q_{a.id}_{j}"
            if s.action != "investigate" and c2.button("Add to suggestions", key=key, width="stretch",
                                                       disabled=st.session_state.get(key + "_done", False)):
                row = econ.loc[s.ad_name] if s.ad_name in econ.index else None
                metrics = {} if row is None else {
                    k: (None if pd.isna(v) else float(v)) for k, v in row.to_dict().items()
                    if isinstance(v, numbers.Number)}
                n_new = recs.save([recs.Rec(
                    s.action, s.platform, "" if row is None else row["ad_id"], s.ad_name,
                    "" if row is None else row["campaign_name"], f"From chat: {s.rationale}",
                    metrics | {"question": a.question}, float(metrics.get("spend_window") or 0), source="agent")])
                ui.suggestions_changed()
                st.session_state[key + "_done"] = True
                st.toast("Added to suggestions" if n_new else "Already in your suggestions", icon="✅")


def render_steps(a: AgentAnswer) -> None:
    st.html("".join(
        f'<div class="ap-step"><div class="ic">{ui.step_icon(s.status)}</div><div class="nm">{html.escape(s.name)}</div>'
        f'<div class="dt">{html.escape(s.detail[:400])}</div><div class="ms">{s.ms or ""}{" ms" if s.ms else ""}</div></div>'
        for s in a.steps))


def render_chart(a: AgentAnswer) -> None:
    c, df = a.chart, a.data
    if c is None or c.type == "none" or df.empty or c.x not in df.columns or c.y not in df.columns:
        st.caption("This answer is easiest to read as a table.")
        return
    color = c.color if c.color in df.columns else None
    cmap = ui.PLATFORM_COLORS if color == "platform" else None
    labels = {col: ui.friendly_name(col) for col in df.columns}
    if color == "platform":
        df = df.assign(platform=df["platform"].astype(str).str.title())
        cmap = {k.title(): v for k, v in ui.PLATFORM_COLORS.items()}
    kw = {"x": c.x, "y": c.y, "color": color, "color_discrete_map": cmap, "color_discrete_sequence": ui.SERIES,
          "labels": labels}
    if c.type == "line":
        fig = px.line(df, **kw)
    elif c.type == "scatter":
        fig = px.scatter(df, **kw, hover_data=df.columns[:4].tolist())
    else:
        horizontal = df[c.x].dtype == object and len(df) > 5
        if horizontal:
            fig = px.bar(df.iloc[::-1], x=c.y, y=c.x, color=color, color_discrete_map=cmap,
                         color_discrete_sequence=ui.SERIES, orientation="h", labels=labels)
        else:
            fig = px.bar(df, **kw)
    fig.update_layout(title=c.title or None, legend_title_text="")
    money = any(w in c.y.lower() for w in ("ltv", "spend", "revenue", "cac", "cost", "value"))
    fig = ui.style_fig(fig, height=360 + (12 * max(0, len(df) - 8) if c.type == "bar" else 0))
    if money:
        fig.update_xaxes(tickprefix="$") if (c.type == "bar" and df[c.x].dtype == object and len(df) > 5) \
            else fig.update_yaxes(tickprefix="$")
    st.plotly_chart(fig, width="stretch", key=f"chart_{a.id}")


# ------------------------------------------------------------------ chat
if not chat:
    st.html('<div class="ap-how">' + "".join(
        f'<div class="st"><div class="n">{n}</div><div class="h">{h}</div><div class="d">{d}</div></div>'
        for n, h, d in [
            ("1", "You ask", "In plain words, like you'd ask a colleague."),
            ("2", "AdPulse looks it up", "It reads your ad and sales data. It can look, never change."),
            ("3", "A second check", "Another pass reviews the logic before you see anything."),
            ("4", "Every number verified", "Each figure in the answer is matched to your real data."),
        ]) + "</div>")
    ui.section("Try a question")
    for i in range(0, len(SUGGESTIONS), 2):
        cols = st.columns(2)
        for col, s in zip(cols, SUGGESTIONS[i:i + 2]):
            if col.button(s, width="stretch", icon=":material/arrow_outward:", key=f"sugg_{i}_{s[:12]}"):
                st.session_state.pending_q = s
                st.rerun()

for i, a in enumerate(chat):
    with st.chat_message("user"):
        st.markdown(ui.md(a.question))
    with st.chat_message("assistant", avatar=":material/monitor_heart:"):
        render_answer(a, i)

question = st.chat_input("Ask about your ads, customers, sales or wasted spend…")
question = question or st.session_state.pop("pending_q", None)
if question:
    with st.chat_message("user"):
        st.markdown(ui.md(question))
    with st.chat_message("assistant", avatar=":material/monitor_heart:"):
        history = [Turn(a.question, a.sql, a.headline) for a in chat if a.ok]
        try:
            with st.status("Looking at your data and double-checking the numbers…", expanded=False) as status:
                ans = agent().ask(question, history)
                status.update(label="Answer ready" if ans.ok else "Couldn't answer",
                              state="complete" if ans.ok else "error")
        except LLMError as e:
            st.error(str(e))
            st.stop()
        chat.append(ans)
        render_answer(ans, len(chat) - 1)

if chat and st.button("Start a new conversation", type="tertiary"):
    st.session_state.chat = []
    st.rerun()

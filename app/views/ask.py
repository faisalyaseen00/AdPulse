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
    "Which ads brought customers with the highest LTV last month?",
    "What was our CAC by platform for each of the last 3 months?",
    "Which ads have the worst LTV to CAC ratio in the last 30 days?",
    "How much did we spend on Google search terms that never converted last month?",
    "Compare Meta vs Google: spend, new customers and 90-day LTV this quarter",
]

ui.hero("Ask AdPulse", "Plain-English questions → SQL → warehouse math → critic review → verified answer.")
if not ui.require_warehouse():
    st.stop()

settings = get_settings()
if not settings.llm_configured:
    st.warning("**No LLM configured.** Add your key to `.env`: `GROQ_API_KEY` with `LLM_PROVIDER=groq` "
               "(or `ANTHROPIC_API_KEY` / `OPENROUTER_API_KEY`), then restart the app.", icon="🔑")
    st.stop()


@st.cache_resource(show_spinner=False)
def agent() -> AdPulseAgent:
    return AdPulseAgent(get_llm())


st.session_state.setdefault("chat", [])
chat: list[AgentAnswer] = st.session_state.chat


def render_answer(a: AgentAnswer, idx: int) -> None:
    if not a.ok:
        st.error(f"I couldn't answer that: {a.error}")
        with st.expander("Trace"):
            render_steps(a)
        return
    n, ok = a.numbers_checked, a.numbers_verified
    critic_ok = a.critic is not None and a.critic.verdict == "pass"
    ui.badges(
        ("✓ Verified" if a.verified else "⚠ Needs review", "good" if a.verified else "warn"),
        (f"Critic {'passed' if critic_ok else 'flagged issues'}", "good" if critic_ok else "warn"),
        (f"{ok}/{n} numbers traced to data", "good" if n == ok else "bad"),
        (f"{len(a.data)} rows", "muted"), (f"{a.latency_ms / 1000:.1f}s · {a.attempts} SQL attempt(s)", "muted"),
    )
    st.markdown(f"#### {a.headline}")
    st.markdown(a.answer_markdown)
    if a.caveats:
        st.caption("Caveats: " + " · ".join(a.caveats))
    if a.critic and a.critic.verdict == "fail":
        st.warning("The critic still had concerns: " + "; ".join(a.critic.issues))

    tabs = st.tabs(["Chart", "Data", "SQL", "How I got this", "Number check"])
    with tabs[0]:
        render_chart(a)
    with tabs[1]:
        st.dataframe(a.data, hide_index=True, width="stretch")
        st.download_button("Download CSV", a.data.to_csv(index=False), f"adpulse_{a.id}.csv", "text/csv",
                           key=f"dl_{a.id}")
    with tabs[2]:
        st.code(a.sql, language="sql")
        if a.assumptions:
            st.caption("Assumptions: " + " · ".join(a.assumptions))
    with tabs[3]:
        st.markdown(f"**Plan.** {a.reasoning}")
        render_steps(a)
    with tabs[4]:
        if not a.number_checks:
            st.caption("The answer quotes no numbers.")
        for c in a.number_checks:
            st.markdown(f"{'✅' if c.verified else '❌'} `{c.text}` — "
                        f"{('found as ' + c.source) if c.verified else 'not found in the result'}")

    if a.suggested_actions:
        st.markdown("**Suggested actions** — queued for human approval, never applied automatically")
        econ = recs.ad_economics(30).set_index("ad_name")
        for j, s in enumerate(a.suggested_actions):
            c1, c2 = st.columns([5, 1.3])
            kind = {"pause_ad": ("⏸ Pause", "bad"), "scale_ad": ("🚀 Scale", "good"),
                    "investigate": ("🔍 Investigate", "info")}[s.action]
            c1.html(f'{ui.badge(kind[0], kind[1])} <b>{html.escape(s.ad_name)}</b> '
                    f'<span class="ap-muted">({s.platform}) — {html.escape(s.rationale)}</span>')
            key = f"q_{a.id}_{j}"
            if s.action != "investigate" and c2.button("Queue for approval", key=key, width="stretch",
                                                       disabled=st.session_state.get(key + "_done", False)):
                row = econ.loc[s.ad_name] if s.ad_name in econ.index else None
                metrics = {} if row is None else {
                    k: (None if pd.isna(v) else float(v)) for k, v in row.to_dict().items()
                    if isinstance(v, numbers.Number)}
                n_new = recs.save([recs.Rec(
                    s.action, s.platform, "" if row is None else row["ad_id"], s.ad_name,
                    "" if row is None else row["campaign_name"], f"From chat: {s.rationale}",
                    metrics | {"question": a.question}, float(metrics.get("spend_window") or 0), source="agent")])
                st.session_state[key + "_done"] = True
                st.toast("Queued for approval" if n_new else "Already pending in the approval queue", icon="✅")


def render_steps(a: AgentAnswer) -> None:
    st.html("".join(
        f'<div class="ap-step"><div class="ic">{ui.step_icon(s.status)}</div><div class="nm">{html.escape(s.name)}</div>'
        f'<div class="dt">{html.escape(s.detail[:400])}</div><div class="ms">{s.ms or ""}{" ms" if s.ms else ""}</div></div>'
        for s in a.steps))


def render_chart(a: AgentAnswer) -> None:
    c, df = a.chart, a.data
    if c is None or c.type == "none" or df.empty or c.x not in df.columns or c.y not in df.columns:
        st.caption("A table is the clearest view for this result.")
        return
    color = c.color if c.color in df.columns else None
    cmap = ui.PLATFORM_COLORS if color == "platform" else None
    kw = dict(x=c.x, y=c.y, color=color, color_discrete_map=cmap, color_discrete_sequence=ui.SERIES)
    if c.type == "line":
        fig = px.line(df, **kw)
    elif c.type == "scatter":
        fig = px.scatter(df, **kw, hover_data=df.columns[:4].tolist())
    else:
        horizontal = df[c.x].dtype == object and len(df) > 5
        if horizontal:
            fig = px.bar(df.iloc[::-1], x=c.y, y=c.x, color=color, color_discrete_map=cmap,
                         color_discrete_sequence=ui.SERIES, orientation="h")
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
    st.markdown("**Try one of these:**")
    cols = st.columns(len(SUGGESTIONS[:3]))
    for col, s in zip(cols, SUGGESTIONS[:3]):
        if col.button(s, width="stretch"):
            st.session_state.pending_q = s
            st.rerun()
    cols = st.columns(len(SUGGESTIONS[3:]))
    for col, s in zip(cols, SUGGESTIONS[3:]):
        if col.button(s, width="stretch"):
            st.session_state.pending_q = s
            st.rerun()

for i, a in enumerate(chat):
    with st.chat_message("user"):
        st.markdown(a.question)
    with st.chat_message("assistant", avatar="📈"):
        render_answer(a, i)

question = st.chat_input("Ask about spend, CAC, LTV, ROAS, campaigns, search terms…")
question = question or st.session_state.pop("pending_q", None)
if question:
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant", avatar="📈"):
        history = [Turn(a.question, a.sql, a.headline) for a in chat if a.ok]
        try:
            with st.status("Writing SQL, querying ClickHouse, reviewing the result…", expanded=False) as status:
                ans = agent().ask(question, history)
                status.update(label="Done" if ans.ok else "Failed", state="complete" if ans.ok else "error")
        except LLMError as e:
            st.error(str(e))
            st.stop()
        chat.append(ans)
        render_answer(ans, len(chat) - 1)

if chat:
    if st.button("Clear conversation", type="tertiary"):
        st.session_state.chat = []
        st.rerun()

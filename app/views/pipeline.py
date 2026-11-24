import pandas as pd
import streamlit as st
import ui

from adpulse import warehouse
from adpulse.config import get_settings
from adpulse.pipeline import demo_data, ingest, transform

ui.hero("Data pipeline", "Sources → Airbyte → ClickHouse raw → modeled tables → agent.")
s = get_settings()
h = warehouse.health()
if not h.ok:
    st.error(f"ClickHouse is offline: {h.error[:300]}")
    st.stop()

counts = warehouse.table_counts()
rows = dict(zip(counts.table, counts.rows))


def n(t):
    return f"{int(rows.get(t, 0) or 0):,}"


st.html('<div class="ap-flow">' + '<div class="arr">→</div>'.join([
    '<div class="node"><div class="t">Sources</div><div class="v">4</div><div class="s">Meta Ads · Google Ads · GA4 · Shopify</div></div>',
    '<div class="node"><div class="t">Airbyte</div><div class="v">6 streams</div><div class="s">PyAirbyte connectors / Airbyte OSS</div></div>',
    f'<div class="node"><div class="t">Raw layer</div><div class="v">{sum(int(v or 0) for k, v in rows.items() if k.startswith("raw_")):,}</div><div class="s">rows in raw_* tables</div></div>',
    f'<div class="node"><div class="t">Models</div><div class="v">{sum(1 for k in rows if k.startswith(("dim_", "fct_", "mart_")))}</div><div class="s">dim / fct / mart tables</div></div>',
    '<div class="node"><div class="t">Agent</div><div class="v">read-only</div><div class="s">SQL guard + readonly user</div></div>',
]) + "</div>")

c1, c2, c3 = st.columns(3)
mode = c1.selectbox("Ingest mode", ["auto", "airbyte", "direct"],
                    help="auto uses PyAirbyte when installed, otherwise the direct CSV loader.")
log_box = st.empty()


def run(fn, *args):
    lines: list[str] = []

    def progress(msg: str):
        lines.append(msg)
        log_box.code("\n".join(lines[-30:]))

    with st.spinner("Running…"):
        try:
            fn(*args, progress=progress) if args else fn(progress=progress)
            ui.clear_cache()
            st.success("Done")
        except Exception as e:  # noqa: BLE001
            st.error(f"{type(e).__name__}: {e}")


if c2.button("Sync now (ingest + transform)", type="primary", width="stretch"):
    def full(mode, progress):
        warehouse.init_db()
        if not (s.demo_dir / "meta_ads_insights.csv").exists():
            progress("demo data not found, generating…")
            demo_data.generate(s.demo_dir)
        ingest.ingest(mode, progress=progress)
        transform.run_models(progress=progress)
    run(full, mode)
if c3.button("Rebuild models only", width="stretch"):
    run(transform.run_models)

t1, t2, t3 = st.tabs(["Tables", "Sync runs", "Freshness"])
with t1:
    st.dataframe(counts, hide_index=True, width="stretch",
                 column_config={"rows": st.column_config.NumberColumn("Rows", format="%d")})
with t2:
    hist = ingest.sync_history()
    if hist.empty:
        st.caption("No syncs yet.")
    else:
        st.dataframe(hist, hide_index=True, width="stretch", column_config={
            "rows": st.column_config.NumberColumn("Rows", format="%d"),
            "seconds": st.column_config.NumberColumn("Seconds", format="%.2f")})
with t3:
    try:
        f = warehouse.query_df("""
            SELECT 'Meta Ads' AS source, toString(max(date)) AS latest FROM raw_meta_ads_insights
            UNION ALL SELECT 'Google Ads', toString(max(date)) FROM raw_google_ads_ad_performance
            UNION ALL SELECT 'Google search terms', toString(max(date)) FROM raw_google_ads_search_terms
            UNION ALL SELECT 'GA4 sessions', toString(max(session_start)) FROM raw_ga4_sessions
            UNION ALL SELECT 'Shopify orders', toString(max(created_at)) FROM raw_shop_orders
        """)
        f["age_days"] = (pd.Timestamp.now() - pd.to_datetime(f.latest)).dt.days
        st.dataframe(f, hide_index=True, width="stretch")
    except Exception as e:  # noqa: BLE001
        st.caption(f"Freshness unavailable: {e}")

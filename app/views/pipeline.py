import pandas as pd
import streamlit as st
import ui

from adpulse import warehouse
from adpulse.config import get_settings
from adpulse.pipeline import demo_data, ingest, transform

ui.hero("Data status", "Where your numbers come from.")
s = get_settings()
h = ui.health()
if not h.ok:
    ui.require_warehouse()
    st.stop()

counts = ui.table_counts()
rows = dict(zip(counts.table, counts.rows))
raw_rows = sum(int(v or 0) for k, v in rows.items() if k.startswith("raw_"))

try:
    fresh = ui.q("""
        SELECT 'Meta ads' AS source, toString(max(date)) AS latest FROM raw_meta_ads_insights
        UNION ALL SELECT 'Google ads', toString(max(date)) FROM raw_google_ads_ad_performance
        UNION ALL SELECT 'Google searches', toString(max(date)) FROM raw_google_ads_search_terms
        UNION ALL SELECT 'Website visits (Google Analytics)', toString(max(session_start)) FROM raw_ga4_sessions
        UNION ALL SELECT 'Shop orders (Shopify)', toString(max(created_at)) FROM raw_shop_orders
    """)
    fresh["latest"] = pd.to_datetime(fresh.latest, format="mixed")
    fresh["age"] = (pd.Timestamp.now() - fresh.latest).dt.days
except Exception:  # noqa: BLE001  (tables not created yet)
    fresh = pd.DataFrame()

newest = fresh.latest.max() if not fresh.empty else None
ui.kpi_row([
    ui.kpi("Sources connected", "4", note="Meta, Google Ads, Google Analytics, Shopify"),
    ui.kpi("Records stored", f"{raw_rows:,}", note="ad results, visits, orders, customers"),
    ui.kpi("Data up to", f"{newest:%b %-d}" if newest is not None else "–",
           note=f"{int((pd.Timestamp.now() - newest).days)} day(s) ago" if newest is not None else ""),
    ui.kpi("Safety", "Read-only", note="the AI can look at data, never change it"),
])

ui.section("Freshness")
if fresh.empty:
    st.info("No data loaded yet. Click **Load data now** below.")
else:
    st.dataframe(fresh, hide_index=True, width="stretch", column_config={
        "source": "Source", "latest": st.column_config.DatetimeColumn("Latest data", format="MMM D, YYYY"),
        "age": st.column_config.NumberColumn("Days old", format="%d")})
st.caption("This demo uses sample data for a coffee brand. Connecting your real Meta, Google and Shopify "
           "accounts replaces it.")

ui.section("Refresh")
c1, c2 = st.columns(2)
log_box = st.empty()


def run(fn, *args):
    lines: list[str] = []

    def progress(msg: str):
        lines.append(msg)
        log_box.code("\n".join(lines[-30:]))

    with st.spinner("Working…"):
        try:
            fn(*args, progress=progress) if args else fn(progress=progress)
            ui.clear_cache()
            st.success("Done. Your numbers are up to date.")
        except Exception as e:  # noqa: BLE001
            st.error(f"Something went wrong: {e}")


with st.expander("Advanced settings"):
    mode = st.selectbox("How to load", ["auto", "airbyte", "direct"],
                        help="auto uses the Airbyte connectors when installed, otherwise a direct file loader.")

if c1.button("Load data now", type="primary", icon=":material/sync:", width="stretch",
             help="Collects the latest data from every source and rebuilds the numbers."):
    def full(mode, progress):
        warehouse.init_db()
        if not (s.demo_dir / "meta_ads_insights.csv").exists():
            progress("sample data not found, creating it…")
            demo_data.generate(s.demo_dir)
        ingest.ingest(mode, progress=progress)
        transform.run_models(progress=progress)
    run(full, mode)
if c2.button("Recalculate numbers only", icon=":material/calculate:", width="stretch",
             help="Rebuilds every total and ratio from the data already stored. Quick."):
    run(transform.run_models)

with st.expander("Technical details (for developers)"):
    st.caption(f"Database: ClickHouse {h.version} · loads via Airbyte (PyAirbyte) or direct CSV · "
               "the AI queries through a separate read-only user")
    t1, t2 = st.tabs(["Tables", "Load history"])
    with t1:
        st.dataframe(counts, hide_index=True, width="stretch",
                     column_config={"rows": st.column_config.NumberColumn("Rows", format="%d")})
    with t2:
        hist = ingest.sync_history()
        if hist.empty:
            st.caption("No loads yet.")
        else:
            st.dataframe(hist, hide_index=True, width="stretch", column_config={
                "rows": st.column_config.NumberColumn("Rows", format="%d"),
                "seconds": st.column_config.NumberColumn("Seconds", format="%.2f")})

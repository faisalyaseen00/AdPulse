export const money = (v: number | null | undefined, decimals = 0) =>
  v == null || Number.isNaN(v)
    ? "–"
    : `${v < 0 ? "−" : ""}$${Math.abs(v).toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}`;

export const num = (v: number | null | undefined, decimals = 0) =>
  v == null || Number.isNaN(v) ? "–" : v.toLocaleString("en-US", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });

export const pct = (v: number | null | undefined, decimals = 1) =>
  v == null || Number.isNaN(v) ? "–" : `${(v * 100).toFixed(decimals)}%`;

export const times = (v: number | null | undefined) => (v == null || Number.isNaN(v) ? "–" : `${v.toFixed(1)}×`);

export const date = (iso: string | null | undefined, opts: Intl.DateTimeFormatOptions = { month: "short", day: "numeric" }) =>
  iso ? new Date(iso).toLocaleDateString("en-US", opts) : "–";

export const title = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

/** Turn database column names into words people use. */
const NAMES: Record<string, string> = {
  ad_name: "Ad", campaign_name: "Campaign", platform: "Where", spend: "Ad spend", spend_window: "Ad spend",
  revenue: "Sales", new_customers: "New customers", new_customers_window: "New customers", cac: "Cost per customer",
  cac_window: "Cost per customer", ltv: "Customer value", ltv_estimate: "Customer value", ltv_90d: "Value (90 days)",
  ltv_to_cac: "Value vs cost", roas: "Back per $1", roas_window: "Back per $1", clicks: "Clicks",
  impressions: "Views", conversions: "Sales", cost: "Cost", month: "Month", week: "Week", day: "Day", date: "Date",
  customers: "Customers", search_term: "Search",
};
export const friendly = (col: string) => NAMES[col] ?? title(col.replaceAll("_", " "));

const MONEY_HINT = /(spend|revenue|cost|cac|ltv|value|sales|price|profit|amount)/i;
export const isMoneyCol = (col: string) => MONEY_HINT.test(col) && !/ratio|to_cac|count|customers$/i.test(col);

export function cell(col: string, v: unknown): string {
  if (v == null) return "–";
  if (typeof v === "number") {
    if (/to_cac/.test(col)) return times(v);
    if (/roas/.test(col)) return money(v, 2);
    if (/share|rate|ctr|pct/.test(col)) return pct(v);
    if (isMoneyCol(col)) return money(v, Math.abs(v) < 1000 ? 2 : 0);
    return num(v, Number.isInteger(v) ? 0 : 2);
  }
  if (typeof v === "string" && /^\d{4}-\d{2}-\d{2}T/.test(v)) return date(v, { month: "short", day: "numeric", year: "numeric" });
  if (col === "platform" && typeof v === "string") return title(v);
  return String(v);
}

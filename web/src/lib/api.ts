/** Thin client for the AdPulse Python API (api/main.py). */
// Accepts "https://api.example.com", "https://api.example.com/" or a bare "api.example.com" (https is added).
const RAW = ((import.meta.env.VITE_API_URL as string | undefined) ?? "").trim().replace(/\/+$/, "");
const BASE = RAW && !/^https?:\/\//i.test(RAW) ? `https://${RAW}` : RAW;

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE}/api${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError("Can't reach the AdPulse server. Check that the API is running.", 0);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = typeof body.detail === "string" ? body.detail : detail;
    } catch { /* not JSON */ }
    throw new ApiError(detail || "Something went wrong", res.status);
  }
  // A web page instead of data means the request never reached the API (usually VITE_API_URL was not set
  // when the site was built, so the host served the app's own index.html).
  if (!(res.headers.get("content-type") ?? "").includes("json")) {
    throw new ApiError(
      BASE
        ? `The address ${BASE} did not answer like the AdPulse server. Check VITE_API_URL.`
        : "The AdPulse server address is not set. Add VITE_API_URL on Vercel and redeploy.",
      res.status,
    );
  }
  return res.json() as Promise<T>;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body: unknown) => request<T>(path, { method: "POST", body: JSON.stringify(body) }),
};

// ---------------------------------------------------------------- response types
export interface Health {
  warehouse: boolean;
  warehouse_error: string;
  ai: boolean;
  slack: boolean;
  email: boolean;
  data_until: string | null;
  pending: number;
}

export interface NextStep { tone: "good" | "bad" | "warn"; title: string; detail: string; value: string; value_note: string }

export interface AdRow {
  ad_id: string; ad_name: string; verdict: "scale" | "losing" | "ok"; platform: string; campaign_name: string;
  spend_window: number; new_customers_window: number; cac_window: number | null; ltv_estimate: number | null;
  ltv_to_cac: number | null; roas_window: number | null;
}

export interface Overview {
  days: number;
  end_date: string;
  roas: number;
  roas_prev: number;
  kpis: {
    spend: number; spend_change: number | null; revenue: number; revenue_change: number | null;
    customers: number; customers_change: number | null; cac: number; cac_change: number | null;
    ltv90: number; ltv_to_cac: number | null;
  };
  journey: { impressions: number; clicks: number; sessions: number; customers: number; revenue: number; ltv90: number };
  daily: { day: string; spend: number; revenue: number; customers: number }[];
  weekly: { week: string; spend: number; revenue: number }[];
  platform_cac: { platform: string; spend: number; customers: number; cac: number }[];
  next_steps: NextStep[];
  ads: AdRow[];
  target_cac: number;
}

export interface Suggestion {
  id: string; created_at: string; kind: "pause_ad" | "scale_ad" | "negative_keyword"; platform: string;
  entity_id: string; entity_name: string; campaign_name: string; reason: string; metrics: string | Record<string, unknown>;
  est_impact: number; status: "pending" | "approved" | "rejected" | "applied"; decided_by: string;
  decided_at: string | null; note: string; source: string;
}

export interface Answer {
  id: string; question: string; ok: boolean; headline: string; answer_markdown: string; sql: string;
  reasoning: string; assumptions: string[]; caveats: string[]; columns: string[]; rows: Record<string, unknown>[];
  chart: { type: "bar" | "line" | "scatter" | "none"; x: string; y: string; color: string; title: string } | null;
  critic: { verdict: "pass" | "fail"; issues: string[] } | null;
  number_checks: { text: string; verified: boolean; source: string }[];
  numbers_checked: number; numbers_verified: number; verified: boolean;
  suggested_actions: { action: "pause_ad" | "scale_ad" | "investigate"; platform: string; ad_name: string; rationale: string }[];
  steps: { name: string; status: string; detail: string; ms: number }[];
  latency_ms: number; error: string;
}

export interface WasteTerm {
  search_term: string; campaign_name?: string; cost: number; clicks: number; conversions: number; intent: string;
  intent_label: string; reason: string; classified_by: string; flagged: boolean; wasted_spend: number;
  suggested_negative: string;
}

export interface Wasted {
  summary: { terms: number; flagged: number; wasted_spend: number; total_cost: number; wasted_share: number };
  terms: WasteTerm[];
  reasons: { reason: string; wasted_spend: number }[];
  campaigns: { campaign_name: string; wasted_spend: number }[];
}

export interface Report {
  id: string; period_start: string; period_end: string;
  kpis: { label: string; value: number; previous: number; text: string; previous_text: string; change: number | null; good: boolean | null; better: string }[];
  top_ads: Record<string, unknown>[]; worst_ads: Record<string, unknown>[]; platform: Record<string, unknown>[];
  waste: { flagged?: number; wasted_spend?: number; wasted_share?: number; terms?: number };
  top_waste_terms: Record<string, unknown>[]; pending: number; commentary: string[]; commentary_source: string;
}

export interface DataStatus {
  sources: { source: string; latest: string; age_days: number }[];
  tables: { table: string; engine: string; rows: number; size: string }[];
  raw_rows: number;
  history: Record<string, unknown>[];
  version: string;
}

export interface Job { id: string; state: "running" | "done" | "failed"; log: string[]; error: string; kind: string }

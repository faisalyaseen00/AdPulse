import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronDown } from "lucide-react";
import { BrandLogo } from "@/components/Brand";
import { api, type Suggestion } from "@/lib/api";
import { date, money, num, times, title } from "@/lib/format";
import { setReviewer, useReviewer } from "@/lib/reviewer";
import { Badge, Button, cx, ErrorState, inputCls, LoadingBlock, Segmented, Stat } from "@/components/ui";

type Kind = "scale_ad" | "pause_ad" | "negative_keyword";
const GROUPS: { kind: Kind; heading: string; intro: string; impact: string }[] = [
  { kind: "scale_ad", heading: "Increase budget", intro: "These ads win customers worth far more than they cost. More budget should bring more of them.", impact: "Extra customer value" },
  { kind: "pause_ad", heading: "Pause ads", intro: "These ads cost more to win a customer than that customer is worth. Pausing them stops the loss.", impact: "Saved" },
  { kind: "negative_keyword", heading: "Block searches", intro: "People using these searches were never going to buy. Blocking them keeps the budget for buyers.", impact: "Saved" },
];
const STATUS: Record<Suggestion["status"], { label: string; tone: "warn" | "info" | "muted" | "good" }> = {
  pending: { label: "Awaiting decision", tone: "warn" },
  approved: { label: "Approved", tone: "info" },
  rejected: { label: "Rejected", tone: "muted" },
  applied: { label: "Done", tone: "good" },
};
const ORIGIN: Record<string, string> = { rules: "Ad performance check", audit: "Wasted searches review", agent: "Ask a question" };

type Filter = "pending" | "approved" | "closed";

function metricsOf(s: Suggestion): Record<string, number> {
  if (typeof s.metrics === "string") {
    try { return JSON.parse(s.metrics); } catch { return {}; }
  }
  return (s.metrics ?? {}) as Record<string, number>;
}

/** The two numbers that justify a change, phrased for a business reader. */
function evidence(s: Suggestion): [string, string][] {
  const m = metricsOf(s);
  if (s.kind === "negative_keyword") {
    return [["Cost", money(m.cost ?? 0, 2)], ["Sales", num(m.conversions ?? 0)]];
  }
  return [
    ["Cost per customer", m.cac_window != null ? money(m.cac_window, 2) : "–"],
    ["Customer value", m.ltv_estimate != null ? `${money(m.ltv_estimate, 2)} (${times(m.ltv_to_cac)})` : "–"],
  ];
}

export default function Suggestions() {
  const qc = useQueryClient();
  const who = useReviewer();
  const [days, setDays] = useState(30);
  const [filter, setFilter] = useState<Filter>("pending");
  const [msg, setMsg] = useState("");
  const q = useQuery({ queryKey: ["suggestions"], queryFn: () => api.get<Suggestion[]>("/suggestions") });

  const refresh = () => { qc.invalidateQueries({ queryKey: ["suggestions"] }); qc.invalidateQueries({ queryKey: ["health"] }); };
  const check = useMutation({
    mutationFn: () => api.post<{ added: number }>("/suggestions/check", { days }),
    onSuccess: (r) => { setMsg(r.added ? `${r.added} new suggestion${r.added === 1 ? "" : "s"} added.` : "No new suggestions. The list is up to date."); refresh(); },
  });

  const rows = useMemo(() => q.data ?? [], [q.data]);
  const pending = rows.filter((r) => r.status === "pending");
  const approved = rows.filter((r) => r.status === "approved");
  const closed = rows.filter((r) => r.status === "applied" || r.status === "rejected");
  const atStake = pending.reduce((a, r) => a + (r.est_impact || 0), 0);
  const shown = filter === "pending" ? pending : filter === "approved" ? approved : closed;

  if (q.isPending) return <LoadingBlock />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => q.refetch()} />;

  return (
    <article>
      <header className="flex flex-wrap items-end justify-between gap-x-12 gap-y-6 border-b border-ink pb-8">
        <div className="max-w-[64ch]">
          <h1 className="text-[clamp(2.4rem,3.8vw,3.6rem)] leading-[1.04]">Recommended changes</h1>
          <p className="mt-4 text-[1.12rem] leading-relaxed text-ink-2">
            {pending.length
              ? <>{num(pending.length)} changes are awaiting a decision, worth an estimated <span className="font-semibold text-ink">{money(atStake)} a month</span>. Each one is based on your own figures, and nothing changes in Meta or Google until someone makes the change after approval.</>
              : "Nothing is awaiting a decision. Check again after new data has loaded."}
          </p>
        </div>
        <div className="grid gap-3 justify-items-start lg:justify-items-end">
          <div className="flex flex-wrap items-center gap-3">
            <label htmlFor="window" className="text-[0.95rem] text-ink-2">Based on the last</label>
            <select id="window" className={cx(inputCls, "w-32")} value={days} onChange={(e) => setDays(+e.target.value)}>
              {[14, 30, 60].map((d) => <option key={d} value={d}>{d} days</option>)}
            </select>
            <Button kind="primary" onClick={() => check.mutate()} loading={check.isPending}>Check for new suggestions</Button>
          </div>
          {msg && <p className="text-[0.95rem] text-good" role="status">{msg}</p>}
        </div>
      </header>

      {!who && <NamePrompt />}

      <section aria-label="Summary" className="grid grid-cols-2 gap-y-8 border-b border-line py-8 md:grid-cols-4">
        <Stat label="Awaiting decision" value={num(pending.length)} />
        <Stat label="Monthly impact if approved" value={money(atStake)} />
        <Stat label="Approved, to be made" value={num(approved.length)} />
        <Stat label="Completed" value={num(rows.filter((r) => r.status === "applied").length)} />
      </section>

      <div className="mt-10 border-b border-line">
        <Segmented<Filter> label="Show" value={filter} onChange={setFilter} options={[
          { value: "pending", label: `Awaiting decision (${pending.length})` },
          { value: "approved", label: `Approved (${approved.length})` },
          { value: "closed", label: `Completed or rejected (${closed.length})` }]} />
      </div>

      {shown.length === 0 ? (
        <p className="py-12 text-[1.05rem] text-ink-2">
          {filter === "pending" ? "Nothing is awaiting a decision." : filter === "approved" ? "No approved changes are waiting to be made." : "No completed or rejected changes yet."}
        </p>
      ) : (
        GROUPS.map((g) => {
          const items = shown.filter((s) => s.kind === g.kind).sort((a, b) => (b.est_impact || 0) - (a.est_impact || 0));
          if (!items.length) return null;
          const total = items.reduce((a, s) => a + (s.est_impact || 0), 0);
          return (
            <section key={g.kind} className="mt-12">
              <div className="flex flex-wrap items-end justify-between gap-4">
                <div>
                  <h2 className="text-[1.7rem] leading-tight">{g.heading} <span className="font-sans text-[1.05rem] font-normal text-ink-2">{num(items.length)}</span></h2>
                  <p className="mt-1.5 max-w-[70ch] text-[1rem] text-ink-2">{g.intro}</p>
                </div>
                <p className="text-right">
                  <span className="block font-display text-[1.7rem] leading-none">{money(total)}</span>
                  <span className="mt-1 block text-[0.95rem] text-ink-2">{g.impact.toLowerCase()} each month</span>
                </p>
              </div>
              <div className="table-frame mt-5">
                <table className="data-table min-w-[980px]">
                  <thead>
                    <tr>
                      <th>{g.kind === "negative_keyword" ? "Search" : "Ad"}</th>
                      <th>Why</th>
                      <th className="num">{g.kind === "negative_keyword" ? "Cost" : "Cost per customer"}</th>
                      <th className="num">{g.kind === "negative_keyword" ? "Sales" : "Customer value"}</th>
                      <th className="num">{g.impact} / month</th>
                      <th className="w-[230px] text-right">{filter === "pending" ? "Decision" : "Status"}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((s) => <Row key={s.id} s={s} who={who} onChange={refresh} />)}
                  </tbody>
                </table>
              </div>
            </section>
          );
        })
      )}
    </article>
  );
}

function NamePrompt() {
  const [draft, setDraft] = useState("");
  return (
    <form onSubmit={(e) => { e.preventDefault(); if (draft.trim()) setReviewer(draft); }}
      className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-md border border-line bg-surface px-5 py-4">
      <div>
        <p className="font-semibold">Add your name to make decisions</p>
        <p className="mt-0.5 text-[0.95rem] text-ink-2">It is recorded with every approval and rejection, so the team can see who decided.</p>
      </div>
      <div className="flex gap-2">
        <label htmlFor="who" className="sr-only">Your name</label>
        <input id="who" className={cx(inputCls, "w-52")} placeholder="Your name" value={draft} onChange={(e) => setDraft(e.target.value)} />
        <Button kind="primary" type="submit" disabled={!draft.trim()}>Save name</Button>
      </div>
    </form>
  );
}

function Row({ s, who, onChange }: { s: Suggestion; who: string; onChange: () => void }) {
  const [note, setNote] = useState("");
  const [noteOpen, setNoteOpen] = useState(false);
  const [change, setChange] = useState(false);
  const decide = useMutation({
    mutationFn: (status: string) => api.post(`/suggestions/${s.id}/decide`, { status, by: who, note }),
    onSuccess: onChange,
  });
  const payload = useQuery({ queryKey: ["change", s.id], queryFn: () => api.get(`/suggestions/${s.id}/change`), enabled: change });
  const [ev1, ev2] = evidence(s);
  const busy = (st: string) => decide.isPending && decide.variables === st;
  const open = s.status === "pending" || s.status === "approved";

  return (
    <>
      <tr>
        <td className="w-[26%]">
          <p className="font-semibold">{s.entity_name}</p>
          <p className="mt-1 inline-flex items-center gap-1.5 text-[0.92rem] text-ink-2">
            <BrandLogo brand={s.platform} className="h-3.5" />{s.campaign_name || title(s.platform)}
          </p>
        </td>
        <td>
          <p className="max-w-[52ch] text-[0.97rem] leading-relaxed text-ink-2">{s.reason}</p>
          <p className="mt-1.5 text-[0.88rem] text-muted">{ORIGIN[s.source] ?? s.source}, {date(s.created_at, { month: "long", day: "numeric" })}</p>
          {s.decided_by && (
            <p className="mt-1 text-[0.9rem] text-ink-2">
              {STATUS[s.status].label} by <span className="font-medium text-ink">{s.decided_by}</span>{s.decided_at ? ` on ${date(s.decided_at, { month: "long", day: "numeric" })}` : ""}{s.note ? `: “${s.note}”` : ""}
            </p>
          )}
        </td>
        <td className="num">{ev1[1]}</td>
        <td className="num">{ev2[1]}</td>
        <td className="num"><span className={cx("font-display text-[1.35rem]", s.kind === "scale_ad" ? "text-good" : "text-ink")}>{money(s.est_impact)}</span></td>
        <td className="text-right">
          {!open ? (
            <Badge tone={STATUS[s.status].tone}>{STATUS[s.status].label}</Badge>
          ) : !who ? (
            <span className="text-[0.92rem] text-ink-2" title="Add your name above the summary to approve or reject">Name needed</span>
          ) : (
            <div className="grid justify-items-end gap-2">
              <div className="flex items-center gap-4">
                {s.status === "pending" ? (
                  <>
                    <button type="button" onClick={() => decide.mutate("rejected")} disabled={decide.isPending}
                      className="text-[0.93rem] font-medium text-ink-2 underline decoration-line-strong underline-offset-4 hover:text-bad hover:decoration-bad disabled:opacity-50">
                      {busy("rejected") ? "Rejecting…" : "Reject"}
                    </button>
                    <Button kind="primary" loading={busy("approved")} onClick={() => decide.mutate("approved")}>
                      <Check className="size-4" strokeWidth={2.25} />Approve
                    </Button>
                  </>
                ) : (
                  <>
                    <button type="button" onClick={() => decide.mutate("rejected")} disabled={decide.isPending}
                      className="text-[0.93rem] font-medium text-ink-2 underline decoration-line-strong underline-offset-4 hover:text-ink disabled:opacity-50">
                      {busy("rejected") ? "Undoing…" : "Undo"}
                    </button>
                    <Button kind="primary" loading={busy("applied")} onClick={() => decide.mutate("applied")}>Mark as done</Button>
                  </>
                )}
              </div>
              <div className="flex gap-4 text-[0.88rem]">
                {s.status === "approved" && (
                  <button type="button" onClick={() => setChange((v) => !v)} className="inline-flex items-center gap-1 text-ink-2 hover:text-ink">
                    Exact change <ChevronDown className={cx("size-3.5 transition-transform", change && "rotate-180")} />
                  </button>
                )}
                {!noteOpen && <button type="button" onClick={() => setNoteOpen(true)} className="text-ink-2 hover:text-ink">Add a note</button>}
              </div>
              {noteOpen && (
                <input autoFocus aria-label="Note" placeholder="Reason, saved with the decision" className={cx(inputCls, "w-[220px]")} value={note} onChange={(e) => setNote(e.target.value)} />
              )}
              {decide.isError && <p className="text-[0.9rem] text-bad">{(decide.error as Error).message}</p>}
            </div>
          )}
        </td>
      </tr>
      {change && payload.data != null && (
        <tr>
          <td colSpan={6} className="bg-paper">
            <p className="mb-2 text-[0.92rem] font-medium">Change to make in {title(s.platform)}</p>
            <pre className="overflow-x-auto text-[0.85rem] text-ink-2">{JSON.stringify(payload.data, null, 2)}</pre>
          </td>
        </tr>
      )}
    </>
  );
}

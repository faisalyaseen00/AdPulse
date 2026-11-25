import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { api, type Wasted as W } from "@/lib/api";
import { money, num, pct } from "@/lib/format";
import { Button, cx, ErrorState, inputCls, LoadingBlock, SectionTitle, Segmented, Toggle } from "@/components/ui";

const PERIODS = [7, 30, 90].map((d) => ({ value: d, label: `${d} days` }));

export default function Wasted() {
  const qc = useQueryClient();
  const [days, setDays] = useState(30);
  const [minCost, setMinCost] = useState(5);
  const [ai, setAi] = useState(true);
  const q = useQuery({
    queryKey: ["wasted", days, minCost, ai],
    queryFn: () => api.get<W>(`/wasted?days=${days}&min_cost=${minCost}&ai=${ai}`),
  });
  const flagged = useMemo(() => q.data?.terms.filter((t) => t.flagged) ?? [], [q.data]);
  const [chosen, setChosen] = useState<Set<string>>(new Set());
  useEffect(() => { setChosen(new Set(flagged.map((t) => t.search_term))); }, [flagged]);
  const [msg, setMsg] = useState("");
  const chosenCost = flagged.filter((t) => chosen.has(t.search_term)).reduce((a, t) => a + t.cost, 0);

  const block = useMutation({
    mutationFn: () => api.post<{ added: number }>("/wasted/block", { days, min_cost: minCost, ai, terms: [...chosen] }),
    onSuccess: (r) => {
      setMsg(r.added ? `${r.added} search${r.added === 1 ? "" : "es"} sent to Suggestions for approval.` : "These are already in your suggestions.");
      qc.invalidateQueries({ queryKey: ["suggestions"] });
      qc.invalidateQueries({ queryKey: ["health"] });
    },
  });

  const s = q.data?.summary;

  return (
    <article>
      <header className="grid gap-x-16 gap-y-8 border-b border-ink pb-10 lg:grid-cols-2">
        <div>
          <h1 className="text-[clamp(2.5rem,4.2vw,4.1rem)] leading-[1.03]">
            {s ? <><span className="text-bad">{money(s.wasted_spend)}</span> went to searches that were never going to buy.</> : "Wasted searches"}
          </h1>
          <p className="mt-6 max-w-[56ch] text-[1.12rem] leading-relaxed text-ink-2">
            Google showed your ads to people looking for jobs, free samples, a café nearby or a competitor. Blocking those
            searches keeps the same budget for people who buy.
          </p>
        </div>
        <div className="flex flex-col justify-end gap-6 lg:items-end">
          <Segmented label="Period" value={days} options={PERIODS} onChange={setDays} />
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 lg:justify-end">
            <label className="flex items-center gap-2 text-[0.95rem] text-ink-2">
              Ignore searches under $
              <input type="number" min={0} step={1} className={cx(inputCls, "w-20")} value={minCost} onChange={(e) => setMinCost(Math.max(0, +e.target.value))} />
            </label>
            <Toggle checked={ai} onChange={setAi} label="Let AI sort unusual searches" />
          </div>
        </div>
      </header>

      {q.isPending ? <div className="mt-8"><LoadingBlock /></div> : q.isError ? <div className="mt-8"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div> : !q.data.terms.length ? (
        <p className="py-10 text-[1.05rem] text-ink-2">No Google searches in this period. Try a longer period or a lower minimum.</p>
      ) : (
        <>
          {/* share of budget */}
          <section className="border-b border-line py-8">
            <div className="flex flex-wrap items-baseline justify-between gap-4">
              <p className="text-[1.05rem] text-ink-2">
                <span className="font-display text-[2rem] text-ink">{pct(s!.wasted_share, 0)}</span> of the search budget, across{" "}
                <span className="font-semibold text-ink">{num(s!.flagged)}</span> of {num(s!.terms)} searches checked
              </p>
              <p className="text-[0.95rem] text-ink-2">{money(s!.total_cost)} spent on Google searches in total</p>
            </div>
            <div className="mt-4 flex h-3 overflow-hidden" role="img" aria-label={`${pct(s!.wasted_share, 0)} of search budget wasted`}>
              <div className="bg-bad" style={{ width: `${s!.wasted_share * 100}%` }} />
              <div className="flex-1 bg-line" />
            </div>
            <div className="mt-2 flex justify-between text-[0.9rem] text-ink-2">
              <span>Wasted</span><span>Reached people who buy</span>
            </div>
          </section>

          <div className="grid gap-x-16 lg:grid-cols-2">
            <section>
              <SectionTitle>Why they won't buy</SectionTitle>
              <ul className="grid gap-4">
                {q.data.reasons.map((r) => (
                  <li key={r.reason}>
                    <div className="flex items-baseline justify-between gap-4 text-[1rem]">
                      <span className="text-ink-2">{r.reason}</span>
                      <span className="font-semibold tabular-nums">{money(r.wasted_spend)}</span>
                    </div>
                    <div className="mt-1.5 h-[5px] bg-canvas">
                      <div className="h-full bg-ink" style={{ width: `${(r.wasted_spend / q.data.reasons[0].wasted_spend) * 100}%` }} />
                    </div>
                  </li>
                ))}
              </ul>
            </section>
            <section>
              <SectionTitle>By campaign</SectionTitle>
              <ul className="divide-y divide-line">
                {q.data.campaigns.map((c) => (
                  <li key={c.campaign_name} className="flex items-baseline justify-between gap-4 py-3.5 text-[1rem]">
                    <span>{c.campaign_name}</span>
                    <span className="font-display text-[1.45rem] leading-none">{money(c.wasted_spend)}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-4 text-[0.95rem] leading-relaxed text-ink-2">
                Competitor campaigns attract people searching for another brand by name. Most of them were never
                going to switch.
              </p>
            </section>
          </div>

          <SectionTitle>Searches to block</SectionTitle>
          <p className="-mt-2 mb-5 text-[1rem] text-ink-2">All are selected. Untick any search you would rather keep paying for.</p>
          <div className="table-frame">
            <table className="data-table min-w-[860px]">
              <thead>
                <tr>
                  <th className="w-12"><span className="sr-only">Block</span></th>
                  <th>Search term</th>
                  <th>Reason</th>
                  <th className="num">Cost</th>
                  <th className="num">Sales</th>
                  <th>Negative keyword</th>
                </tr>
              </thead>
              <tbody>
                {flagged.map((t) => {
                  const on = chosen.has(t.search_term);
                  return (
                    <tr key={t.search_term} className={cx(!on && "text-faint")}>
                      <td>
                        <input type="checkbox" className="size-4 accent-[#16181d]" aria-label={`Block ${t.search_term}`} checked={on}
                          onChange={() => setChosen((cur) => { const n = new Set(cur); if (n.has(t.search_term)) n.delete(t.search_term); else n.add(t.search_term); return n; })} />
                      </td>
                      <td className="font-medium">{t.search_term}</td>
                      <td className="text-ink-2">{t.reason}{t.classified_by === "llm" && <span className="ml-2 text-[0.9rem] text-muted">(AI)</span>}</td>
                      <td className="num">{money(t.cost, 2)}</td>
                      <td className="num">{num(t.conversions)}</td>
                      <td ><code className="text-[0.88rem] text-ink-2">{t.suggested_negative}</code></td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* decision bar */}
          <div className="sticky bottom-0 z-10 mt-6 flex flex-wrap items-center justify-between gap-4 border-t border-ink bg-paper py-4">
            <p className="text-[1rem] text-ink-2">
              <span className="font-semibold text-ink">{num(chosen.size)}</span> searches selected,{" "}
              <span className="font-semibold text-ink">{money(chosenCost)}</span> of spend. Each one waits for approval;
              nothing is blocked in Google Ads automatically.
            </p>
            <div className="flex items-center gap-4">
              {msg && <span className="text-[0.95rem] text-good" role="status">{msg} <Link to="/suggestions" className="font-medium underline underline-offset-4">Open Suggestions</Link></span>}
              <Button kind="primary" disabled={!chosen.size} loading={block.isPending} onClick={() => block.mutate()}>
                Send {chosen.size} to Suggestions
              </Button>
            </div>
          </div>
        </>
      )}
    </article>
  );
}

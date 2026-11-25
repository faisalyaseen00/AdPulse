import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrandLogo } from "@/components/Brand";
import { api, type Health, type Report as R } from "@/lib/api";
import { date, money, num, times, title } from "@/lib/format";
import { Badge, Button, Change, cx, ErrorState, inputCls, LoadingBlock, SectionTitle, Toggle } from "@/components/ui";

type AdLine = { ad_name: string; platform: string; campaign_name?: string; spend: number; new_customers: number; cac: number; avg_ltv: number; ltv_to_cac: number };

export default function Report() {
  const qc = useQueryClient();
  const [end, setEnd] = useState("");
  const [ai, setAi] = useState(true);
  const [msg, setMsg] = useState<{ tone: "good" | "bad"; text: string } | null>(null);
  const health = useQuery({ queryKey: ["health"], queryFn: () => api.get<Health>("/health") });
  const qs = `${end ? `end=${end}&` : ""}ai=${ai}`;
  const q = useQuery({ queryKey: ["report", end, ai], queryFn: () => api.get<R>(`/report?${qs}`) });
  const sched = useQuery({ queryKey: ["schedule"], queryFn: () => api.get<{ describe: string; next_run: string }>("/report/schedule") });
  const hist = useQuery({ queryKey: ["report-history"], queryFn: () => api.get<Record<string, string>[]>("/report/history") });

  const send = useMutation({
    mutationFn: (to: { slack: boolean; email: boolean }) => api.post<Record<string, string>>("/report/send", { end: end || null, ai, ...to }),
    onSuccess: (r) => {
      const bad = Object.entries(r).filter(([, v]) => !/^(sent|ok)/i.test(v));
      setMsg(bad.length ? { tone: "bad", text: bad.map(([k, v]) => `${title(k)}: ${v}`).join(". ") } : { tone: "good", text: `Sent to ${Object.keys(r).map(title).join(" and ")}.` });
      qc.invalidateQueries({ queryKey: ["report-history"] });
    },
    onError: (e) => setMsg({ tone: "bad", text: (e as Error).message }),
  });

  const download = async () => {
    const { markdown } = await api.get<{ markdown: string }>(`/report/markdown?${qs}`);
    const url = URL.createObjectURL(new Blob([markdown], { type: "text/markdown" }));
    Object.assign(document.createElement("a"), { href: url, download: `adpulse_weekly_${q.data?.period_end ?? "report"}.md` }).click();
    URL.revokeObjectURL(url);
  };

  const k = (label: string) => q.data?.kpis.find((x) => x.label.toLowerCase().startsWith(label));
  const sales = k("sales from ads");
  const spend = k("ad spend");

  return (
    <article>
      <header className="grid gap-x-16 gap-y-8 border-b border-ink pb-10 lg:grid-cols-2">
        <div>
          <p className="text-[1.05rem] text-ink-2">
            {q.data ? <>Week of {date(q.data.period_start, { month: "long", day: "numeric" })} to {date(q.data.period_end, { month: "long", day: "numeric", year: "numeric" })}</> : "Weekly report"}
          </p>
          <h1 className="mt-4 text-[clamp(2.5rem,4.2vw,4.1rem)] leading-[1.03]">
            {sales && spend ? <>{money(sales.value)} in sales from {money(spend.value)} of ads this week.</> : "The Monday summary for your team."}
          </h1>
          <p className="mt-6 max-w-[56ch] text-[1.12rem] leading-relaxed text-ink-2">
            This is the report your team receives {sched.data ? sched.data.describe : "every Monday"}. You can also send it
            now, or download it.
          </p>
        </div>

        <aside className="flex flex-col justify-end gap-5 lg:items-end">
          <div className="flex flex-wrap gap-2 lg:justify-end">
            <Button kind="primary" disabled={!health.data?.slack} title={health.data?.slack ? undefined : "Slack isn't set up"} loading={send.isPending && send.variables?.slack} onClick={() => send.mutate({ slack: true, email: false })}>
              <BrandLogo brand="slack" className="h-4 brightness-0 invert" />Send to Slack
            </Button>
            <Button disabled={!health.data?.email} title={health.data?.email ? undefined : "Email isn't set up"} loading={send.isPending && send.variables?.email} onClick={() => send.mutate({ slack: false, email: true })}>Email it</Button>
            <Button onClick={download} disabled={!q.data}>Download</Button>
          </div>
          <div className="flex flex-wrap items-center gap-x-6 gap-y-3 lg:justify-end">
            <label className="flex items-center gap-2 text-[0.95rem] text-ink-2">
              Week ending
              <input type="date" className={cx(inputCls, "w-40")} value={end} onChange={(e) => setEnd(e.target.value)} />
            </label>
            <Toggle checked={ai} onChange={setAi} label="AI-written summary" />
          </div>
          <p className="text-[0.95rem] text-ink-2">
            Slack {health.data?.slack ? <span className="font-medium text-good">connected</span> : <span className="font-medium text-muted">not set up</span>}
            <span className="mx-2 text-line-strong">/</span>
            Email {health.data?.email ? <span className="font-medium text-good">connected</span> : <span className="font-medium text-muted">not set up</span>}
          </p>
          {msg && <p className={cx("text-[0.95rem]", msg.tone === "good" ? "text-good" : "text-bad")} role="status">{msg.text}</p>}
        </aside>
      </header>

      {q.isPending ? <div className="mt-8"><LoadingBlock rows={3} /></div> : q.isError ? <div className="mt-8"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div> : (
        <>
          <section aria-label="This week's figures" className="grid grid-cols-2 gap-y-8 border-b border-line py-8 md:grid-cols-3 xl:grid-cols-6">
            {q.data.kpis.map((kp, i) => (
              <div key={kp.label} className={cx("min-w-0 pr-5", i > 0 && "xl:border-l xl:border-line xl:pl-6")}>
                <p className="text-[0.95rem] font-medium text-ink-2">{kp.label}</p>
                <p className="mt-2 font-display text-[1.9rem] leading-none">{kp.text}</p>
                <p className="mt-2"><Change value={kp.change} better={kp.better as "up" | "down" | "neutral"} suffix="vs week before" /></p>
              </div>
            ))}
          </section>

          <div className="grid gap-x-16 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
            <section>
              <SectionTitle>The week in brief</SectionTitle>
              <ol className="grid gap-5">
                {q.data.commentary.map((c, i) => (
                  <li key={i} className="grid grid-cols-[2rem_minmax(0,1fr)] gap-3">
                    <span className="font-display text-[1.25rem] leading-snug text-faint">{i + 1}.</span>
                    <p className="text-[1.08rem] leading-relaxed text-ink-2">{c}</p>
                  </li>
                ))}
              </ol>
              <p className="mt-5 text-[0.95rem] text-ink-2">{q.data.commentary_source === "llm" ? "Written by the AI assistant from the figures above, then checked against them." : "Written from the figures above."}</p>
            </section>
            <section>
              <SectionTitle>Wasted searches</SectionTitle>
              <p className="text-[1.05rem] leading-relaxed text-ink-2">
                <span className="font-display text-[1.9rem] text-bad">{money(q.data.waste.wasted_spend)}</span> went to {num(q.data.waste.flagged ?? 0)} searches
                that never sold, {Math.round((q.data.waste.wasted_share ?? 0) * 100)}% of search spend.
              </p>
              <ul className="mt-4 divide-y divide-line border-y border-line">
                {(q.data.top_waste_terms as { search_term: string; cost: number }[]).map((t) => (
                  <li key={t.search_term} className="flex justify-between gap-4 py-2.5 text-[0.98rem]">
                    <span>{t.search_term}</span><span className="tabular-nums text-ink-2">{money(t.cost, 2)}</span>
                  </li>
                ))}
              </ul>
              {q.data.pending > 0 && <p className="mt-4 text-[0.98rem] text-ink-2">{q.data.pending} suggestions are waiting for approval.</p>}
            </section>
          </div>

          <div className="grid gap-x-16 lg:grid-cols-2">
            <AdList heading="Best ads this week" rows={q.data.top_ads as AdLine[]} tone="good" />
            <AdList heading="Ads losing money" rows={q.data.worst_ads as AdLine[]} tone="bad" />
          </div>
        </>
      )}

      <SectionTitle>Report history</SectionTitle>
      <div className="table-frame">
        <table className="data-table min-w-[640px]">
          <thead>
            <tr>
              <th>Prepared on</th><th>Week covered</th><th>Sent to</th><th>Status</th>
            </tr>
          </thead>
          <tbody>
            {(hist.data ?? []).map((h) => (
              <tr key={h.id}>
                <td >{date(h.created_at, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</td>
                <td >{date(h.period_start)} to {date(h.period_end)}</td>
                <td className="text-ink-2">{h.channels ? h.channels.split(",").map(title).join(", ") : "Not sent"}</td>
                <td ><Badge tone={h.status === "sent" ? "good" : h.status === "failed" ? "bad" : "muted"}>{h.status === "generated" ? "Prepared" : title(h.status)}</Badge></td>
              </tr>
            ))}
            {hist.data?.length === 0 && <tr><td colSpan={4} className="text-ink-2">No reports yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </article>
  );
}

function AdList({ heading, rows, tone }: { heading: string; rows: AdLine[]; tone: "good" | "bad" }) {
  return (
    <section>
      <SectionTitle>{heading}</SectionTitle>
      <ol className="divide-y divide-line">
        {rows.map((a, i) => (
          <li key={a.ad_name} className="grid grid-cols-[2rem_minmax(0,1fr)_auto] items-baseline gap-3 py-4">
            <span className="font-display text-[1.2rem] text-faint">{i + 1}</span>
            <div>
              <p className="font-medium">{a.ad_name}</p>
              <p className="mt-0.5 inline-flex items-center gap-1.5 text-[0.92rem] text-ink-2">
                <BrandLogo brand={a.platform} className="h-3.5" />
                {money(a.spend)} spent, {num(a.new_customers)} customers at {money(a.cac, 2)}
              </p>
            </div>
            <div className="text-right">
              <p className={cx("font-display text-[1.6rem] leading-none", tone === "good" ? "text-good" : "text-bad")}>{times(a.ltv_to_cac)}</p>
              <p className="mt-1 text-[0.92rem] text-ink-2">value vs cost</p>
            </div>
          </li>
        ))}
        {!rows.length && <li className="py-4 text-ink-2">None this week.</li>}
      </ol>
    </section>
  );
}

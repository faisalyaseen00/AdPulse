import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrandLogo } from "@/components/Brand";
import { api, type DataStatus as D, type Job } from "@/lib/api";
import { date, num } from "@/lib/format";
import { Badge, Button, cx, ErrorState, LoadingBlock, SectionTitle, Stat } from "@/components/ui";

function age(days: number) {
  return days <= 0 ? "today" : days === 1 ? "1 day old" : `${days} days old`;
}

export default function DataStatus() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["data-status"], queryFn: () => api.get<D>("/data/status") });
  const [jobId, setJobId] = useState<string | null>(null);

  const start = useMutation({
    mutationFn: (kind: "full" | "models") => api.post<Job>("/data/refresh", { kind }),
    onSuccess: (j) => setJobId(j.id),
  });
  // follow the real job state; never assume success because the request was accepted
  const job = useQuery({
    queryKey: ["job", jobId],
    queryFn: () => api.get<Job>(`/data/jobs/${jobId}`),
    enabled: !!jobId,
    refetchInterval: (query) => (query.state.data?.state === "running" ? 1500 : false),
  });
  useEffect(() => {
    if (job.data && job.data.state !== "running") qc.invalidateQueries();
  }, [job.data?.state, qc]);
  const running = job.data?.state === "running" || start.isPending;

  const sources = q.data?.sources ?? [];
  const newest = sources.reduce<string | null>((m, s) => (!m || s.latest > m ? s.latest : m), null);
  const oldest = sources.reduce((m, s) => Math.max(m, s.age_days), 0);

  return (
    <article>
      <header className="grid gap-x-16 gap-y-8 border-b border-ink pb-10 lg:grid-cols-2">
        <div>
          <h1 className="text-[clamp(2.5rem,4.2vw,4.1rem)] leading-[1.03]">
            {newest ? <>Your numbers run to {date(newest, { month: "long", day: "numeric" })}.</> : "Where your numbers come from."}
          </h1>
          <p className="mt-6 max-w-[56ch] text-[1.12rem] leading-relaxed text-ink-2">
            AdPulse collects ad results from Meta and Google, website visits from Google Analytics and orders from
            Shopify, then works out every figure from those records. {oldest > 2 ? "Some sources are a few days behind; load fresh data before the client meeting." : "Everything is current."}
          </p>
        </div>
        <section aria-label="Refresh" className="self-end rounded-md border border-line bg-surface">
          <div className="border-b border-line px-6 py-4">
            <h2 className="text-[1.3rem]">Refresh the numbers</h2>
          </div>
          <div className="grid divide-y divide-line">
            <div className="flex flex-wrap items-center justify-between gap-4 px-6 py-5">
              <div className="max-w-[40ch]">
                <p className="font-semibold">Load fresh data</p>
                <p className="mt-0.5 text-[0.95rem] text-ink-2">Pull the latest records from every source, then rebuild every figure. A few minutes.</p>
              </div>
              <Button kind="primary" loading={running && start.variables === "full"} disabled={running} onClick={() => start.mutate("full")}>Load fresh data</Button>
            </div>
            <div className="flex flex-wrap items-center justify-between gap-4 px-6 py-5">
              <div className="max-w-[40ch]">
                <p className="font-semibold">Recalculate figures</p>
                <p className="mt-0.5 text-[0.95rem] text-ink-2">Rebuild totals and ratios from the records already stored. Seconds.</p>
              </div>
              <Button loading={running && start.variables === "models"} disabled={running} onClick={() => start.mutate("models")}>Recalculate</Button>
            </div>
          </div>
        </section>
      </header>

      {(job.data || start.isError) && (
        <section className="mt-8 border-l-2 border-ink bg-surface px-5 py-4">
          <div className="flex flex-wrap items-center gap-3">
            {job.data?.state === "running" && <Badge tone="info">Working</Badge>}
            {job.data?.state === "done" && <Badge tone="good">Done. Every figure is up to date.</Badge>}
            {(job.data?.state === "failed" || start.isError) && <Badge tone="bad">Failed</Badge>}
            {job.data?.error && <span className="text-[0.95rem] text-bad">{job.data.error}</span>}
            {start.isError && <span className="text-[0.95rem] text-bad">{(start.error as Error).message}</span>}
          </div>
          {!!job.data?.log.length && <pre className="mt-3 max-h-56 overflow-auto text-[0.85rem] leading-relaxed text-ink-2">{job.data.log.join("\n")}</pre>}
        </section>
      )}

      {q.isPending ? <div className="mt-8"><LoadingBlock /></div> : q.isError ? <div className="mt-8"><ErrorState error={q.error} onRetry={() => q.refetch()} /></div> : (
        <>
          <section aria-label="Summary" className="grid grid-cols-2 gap-y-8 border-b border-line py-8 md:grid-cols-4">
            <Stat label="Sources connected" value={num(sources.length)}><span className="text-[0.92rem] text-ink-2">ads, website and shop</span></Stat>
            <Stat label="Records stored" value={num(q.data.raw_rows)}><span className="text-[0.92rem] text-ink-2">ad results, visits and orders</span></Stat>
            <Stat label="Newest data" value={date(newest)}><span className="text-[0.92rem] text-ink-2">{newest ? age(Math.floor((Date.now() - new Date(newest).getTime()) / 864e5)) : ""}</span></Stat>
            <Stat label="AI access" value="Read-only"><span className="text-[0.92rem] text-ink-2">it can look, never change</span></Stat>
          </section>

          <SectionTitle>Sources</SectionTitle>
          <p className="-mt-2 mb-5 text-[1rem] text-ink-2">A source counts as fresh when its latest record is no more than two days old.</p>
          <ul className="grid gap-px overflow-hidden rounded-md border border-line bg-line sm:grid-cols-2 xl:grid-cols-5">
            {sources.map((src) => {
              const tone = src.age_days <= 2 ? "good" : src.age_days <= 7 ? "warn" : "bad";
              return (
                <li key={src.source} className="flex flex-col bg-surface p-5">
                  <BrandLogo brand={src.source} className="h-7 max-w-10 self-start object-contain" />
                  <p className="mt-5 text-[1.05rem] font-semibold leading-snug">{src.source}</p>
                  <p className="mt-1 text-[0.95rem] text-ink-2">Latest record {date(src.latest, { month: "short", day: "numeric" })}</p>
                  <div className="mt-auto pt-5">
                    <div className="flex h-[5px] gap-[3px]" aria-hidden>
                      {Array.from({ length: 7 }, (_, i) => (
                        <span key={i} className={cx("flex-1", i < Math.min(7, src.age_days) ? (tone === "good" ? "bg-good" : tone === "warn" ? "bg-saffron" : "bg-bad") : "bg-canvas")} />
                      ))}
                    </div>
                    <p className="mt-2"><Badge tone={tone}>{age(src.age_days)}</Badge></p>
                  </div>
                </li>
              );
            })}
          </ul>
          <p className="mt-4 text-[0.98rem] text-ink-2">This demo runs on sample data for a coffee brand. Connecting real Meta, Google and Shopify accounts replaces it.</p>

          <SectionTitle>Recent loads</SectionTitle>
          <div className="table-frame">
            <table className="data-table min-w-[720px]">
              <thead>
                <tr>
                  {["Started", "Source", "Destination table", "Rows", "Duration", "Result"].map((h, i) => <th key={h} className={cx((i === 3 || i === 4) && "num")}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {(q.data.history as Record<string, string | number>[]).slice(0, 12).map((h) => (
                  <tr key={String(h.run_id) + h.target_table}>
                    <td >{date(String(h.started_at), { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</td>
                    <td ><span className="inline-flex items-center gap-2"><BrandLogo brand={String(h.source)} className="h-3.5" />{String(h.source)}</span></td>
                    <td className="text-ink-2">{String(h.target_table)}</td>
                    <td className="num">{num(Number(h.rows))}</td>
                    <td className="num">{Number(h.seconds).toFixed(1)} s</td>
                    <td ><Badge tone={h.status === "succeeded" ? "good" : "bad"}>{h.status === "succeeded" ? "Loaded" : String(h.status)}</Badge></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </article>
  );
}

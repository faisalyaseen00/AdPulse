import { useState } from "react";
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api, type AdRow, type Overview as O } from "@/lib/api";
import { date, money, num, pct, times, title } from "@/lib/format";
import { Badge, cx, ErrorState, LoadingBlock, SectionTitle, Segmented } from "@/components/ui";
import { SalesSpendChart } from "@/components/charts";
import { KpiCard } from "@/components/KpiCard";
import { Funnel } from "@/components/Funnel";
import { BrandLogo, BrandName } from "@/components/Brand";

const PERIODS = [7, 30, 90].map((d) => ({ value: d, label: `${d} days` }));
const PLATFORM: Record<string, string> = { meta: "var(--color-meta)", google: "var(--color-google)" };

const usd0 = (v: number) => money(v);
const usd2 = (v: number) => money(v, 2);
const int = (v: number) => num(Math.round(v));

export default function Overview() {
  const [days, setDays] = useState(30);
  const q = useQuery({ queryKey: ["overview", days], queryFn: () => api.get<O>(`/overview?days=${days}`) });

  return q.isPending ? <LoadingBlock rows={4} /> : q.isError ? <ErrorState error={q.error} onRetry={() => q.refetch()} />
    : <Report d={q.data} days={days} setDays={setDays} />;
}

function verdict(roas: number) {
  if (roas >= 1.5) return { line: "Advertising is clearly profitable.", tone: "good" as const, label: "Healthy return" };
  if (roas >= 1) return { line: "Advertising pays for itself, with room to grow.", tone: "warn" as const, label: "Breaking even" };
  return { line: "Advertising currently costs more than it brings back.", tone: "bad" as const, label: "Losing money" };
}

function Report({ d, days, setDays }: { d: O; days: number; setDays: (n: number) => void }) {
  const k = d.kpis;
  const v = verdict(d.roas);
  const labels = d.daily.map((r) => date(r.day));
  const start = d.daily[0]?.day;
  const totalSpend = d.platform_cac.reduce((a, p) => a + p.spend, 0);
  const cheap = d.platform_cac[0];
  const dear = d.platform_cac[d.platform_cac.length - 1];

  return (
    <article>
      {/* ---- masthead: period toolbar, then the answer and the evidence side by side ---- */}
      <header className="grid gap-x-16 gap-y-12 border-b border-ink pb-12 lg:grid-cols-2">
        <div>
          <h1 className="text-[clamp(2.7rem,4.6vw,4.6rem)] leading-[1.02]">
            Every dollar on ads returned <span className="whitespace-nowrap">{money(d.roas, 2)}.</span>
          </h1>
          <p className="mt-7 max-w-[56ch] text-[1.15rem] leading-[1.65] text-ink-2">
            {v.line} From {date(start, { month: "long", day: "numeric" })} to {date(d.end_date, { month: "long", day: "numeric" })},{" "}
            {money(k.revenue)} in sales came from {money(k.spend)} of advertising, and {num(k.customers)} new customers
            joined at {money(k.cac, 2)} each.
          </p>
        </div>
        <figure className="flex flex-col">
          <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
            <figcaption className="text-[1.05rem] font-semibold text-ink">Sales and ad spend, day by day</figcaption>
            <Segmented label="Period" value={days} options={PERIODS} onChange={setDays} />
          </div>
          <div className="mt-1 flex gap-5 text-[0.95rem] text-ink-2">
            <span className="flex items-center gap-2"><span className="h-[2px] w-5 bg-ink" />Sales</span>
            <span className="flex items-center gap-2"><span className="h-[2px] w-5 bg-saffron" />Ad spend</span>
          </div>
          <div className="mt-4 flex-1"><SalesSpendChart data={d.daily} xKey="day" height={260} compact /></div>
        </figure>
      </header>

      {/* ---- the figures ---- */}
      <section aria-label="Key figures" className="grid grid-cols-2 gap-y-10 border-b border-line py-10 md:grid-cols-3 xl:grid-cols-5">
        {[
          <KpiCard key="r" label="Sales from ads" value={k.revenue} format={usd0} change={k.revenue_change} note={`vs prior ${d.days} days`} series={d.daily.map((r) => r.revenue)} seriesLabels={labels} />,
          <KpiCard key="s" label="Ad spend" value={k.spend} format={usd0} change={k.spend_change} better="neutral" note={`vs prior ${d.days} days`} series={d.daily.map((r) => r.spend)} seriesLabels={labels} accent="#d4920f" delay={0.05} />,
          <KpiCard key="c" label="New customers" value={k.customers} format={int} change={k.customers_change} note={`vs prior ${d.days} days`} series={d.daily.map((r) => r.customers)} seriesLabels={labels} delay={0.1} />,
          <KpiCard key="a" label="Cost per new customer" value={k.cac} format={usd2} change={k.cac_change} better="down" note={`vs prior ${d.days} days`} series={d.daily.map((r) => (r.customers ? r.spend / r.customers : 0))} seriesLabels={labels} delay={0.15} />,
          <KpiCard key="v" label="Value of a customer" value={k.ltv90} format={usd2} note={`${times(k.ltv_to_cac)} what it costs to win one`} delay={0.2} />,
        ].map((el, i) => (
          <div key={i} className={cx("min-w-0 pr-6", i > 0 && "border-l border-line pl-6", "max-md:[&:nth-child(odd)]:border-l-0 max-md:[&:nth-child(odd)]:pl-0")}>{el}</div>
        ))}
      </section>

      {/* ---- ranked next steps ---- */}
      <SectionTitle action={<Link to="/suggestions" className="text-[0.88rem] font-medium underline decoration-line-strong underline-offset-4 hover:decoration-ink">All suggestions</Link>}>
        What to do next
      </SectionTitle>
      {d.next_steps.length ? (
        <ol className="divide-y divide-line">
          {d.next_steps.map((s, i) => (
            <li key={s.title} className="grid grid-cols-[2.5rem_minmax(0,1fr)] gap-x-4 gap-y-3 py-5 sm:grid-cols-[3rem_minmax(0,1fr)_auto] sm:items-baseline">
              <span className="font-display text-[1.6rem] leading-none text-faint">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <p className="text-[1.05rem] font-semibold">{s.title}</p>
                <p className="mt-1 text-[0.98rem] text-ink-2">{s.detail}</p>
              </div>
              <div className="col-start-2 sm:col-start-3 sm:text-right">
                <p className={cx("font-display text-[1.7rem] leading-none", s.tone === "good" ? "text-good" : "text-ink")}>{s.value}</p>
                <p className="mt-1 text-[0.95rem] text-ink-2">{s.value_note}</p>
                <Link to={s.tone === "warn" ? "/wasted" : "/suggestions"} className="mt-2 inline-block text-[0.92rem] font-medium underline decoration-line-strong underline-offset-4 hover:decoration-ink">
                  Review
                </Link>
              </div>
            </li>
          ))}
        </ol>
      ) : <p className="text-[1.02rem] text-ink-2">Nothing needs attention in this period.</p>}

      {/* ---- the journey ---- */}
      <SectionTitle>From ad to customer</SectionTitle>
      <Funnel stages={[
        { label: "Saw an ad", value: d.journey.impressions, display: compact(d.journey.impressions), rate: "ad views" },
        { label: "Clicked", value: d.journey.clicks, display: compact(d.journey.clicks), rate: d.journey.impressions ? `${pct(d.journey.clicks / d.journey.impressions)} of viewers` : "" },
        { label: "Visited the site", value: d.journey.sessions, display: compact(d.journey.sessions), rate: "visits from ads" },
        { label: "Became customers", value: d.journey.customers, display: num(d.journey.customers), rate: d.journey.sessions ? `${pct(d.journey.customers / d.journey.sessions)} of visits` : "" },
      ]} />
      <p className="mt-6 max-w-[70ch] text-[1.02rem] leading-relaxed text-ink-2">
        Those {num(d.journey.customers)} new customers spent <span className="font-semibold text-ink">{money(d.journey.revenue)}</span>,
        and each is worth about <span className="font-semibold text-ink">{money(d.journey.ltv90, 2)}</span> over their first 90 days.
      </p>

      {/* ---- trend and channels ---- */}
      <div className="grid gap-x-14 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <section>
          <SectionTitle>Weekly sales and spend, last six months</SectionTitle>
          <div className="mb-3 flex flex-wrap gap-x-8 gap-y-1 text-[0.95rem]">
            <span className="flex items-center gap-2"><span className="h-[2px] w-4 bg-ink" /><span className="text-ink-2">Sales from ads</span> <b className="font-semibold">{money(d.weekly.reduce((a, r) => a + r.revenue, 0))}</b></span>
            <span className="flex items-center gap-2"><span className="h-[2px] w-4 bg-saffron" /><span className="text-ink-2">Ad spend</span> <b className="font-semibold">{money(d.weekly.reduce((a, r) => a + r.spend, 0))}</b></span>
          </div>
          <SalesSpendChart data={d.weekly} xKey="week" height={260} />
        </section>
        <section>
          <SectionTitle>Meta and Google</SectionTitle>
          <p className="text-[0.95rem] text-ink-2">Share of ad spend</p>
          <div className="mt-2 flex h-3 overflow-hidden rounded-[3px]" role="img"
            aria-label={d.platform_cac.map((p) => `${title(p.platform)} ${pct(totalSpend ? p.spend / totalSpend : 0, 0)}`).join(", ")}>
            {d.platform_cac.map((p) => (
              <div key={p.platform} style={{ width: `${totalSpend ? (p.spend / totalSpend) * 100 : 0}%`, background: PLATFORM[p.platform] }} className="h-full border-r-2 border-paper last:border-r-0" />
            ))}
          </div>
          <dl className="mt-6 grid grid-cols-2 gap-x-6">
            {d.platform_cac.map((p) => (
              <div key={p.platform} className="border-t-2 pt-3" style={{ borderColor: PLATFORM[p.platform] }}>
                <dt className="flex items-center justify-between text-[0.98rem] font-semibold"><BrandName brand={p.platform} /> <span className="font-normal text-ink-2">{pct(totalSpend ? p.spend / totalSpend : 0, 0)}</span></dt>
                <dd className="mt-3 font-display text-[2rem] leading-none">{money(p.cac, 2)}</dd>
                <dd className="mt-1 text-[0.95rem] text-ink-2">per new customer</dd>
                <dd className="mt-3 text-[0.95rem] text-ink-2">{money(p.spend)} spent<br />{num(p.customers)} customers</dd>
              </div>
            ))}
          </dl>
          {cheap && dear && cheap !== dear && (
            <p className="mt-6 border-l-2 border-saffron pl-3 text-[1rem] text-ink-2">
              {title(cheap.platform)} wins customers {money(dear.cac - cheap.cac, 2)} cheaper than {title(dear.platform)}.
            </p>
          )}
        </section>
      </div>

      {/* ---- every ad ---- */}
      <SectionTitle>Every ad, best to worst</SectionTitle>
      <AdTable ads={d.ads} />
    </article>
  );
}

function compact(v: number) {
  return v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e4 ? `${Math.round(v / 1e3)}k` : num(v);
}

const VERDICT: Record<AdRow["verdict"], { label: string; tone: "good" | "bad" | "muted" }> = {
  scale: { label: "Give more budget", tone: "good" },
  losing: { label: "Losing money", tone: "bad" },
  ok: { label: "Doing fine", tone: "muted" },
};

function AdTable({ ads }: { ads: AdRow[] }) {
  const sorted = [...ads].sort((a, b) => (b.ltv_to_cac ?? -1) - (a.ltv_to_cac ?? -1));
  const max = Math.max(3, ...sorted.map((a) => a.ltv_to_cac ?? 0));
  return (
    <>
      <div className="table-frame">
        <table className="data-table min-w-[900px]">
          <thead>
            <tr>
              <th>Ad</th>
              <th>Status</th>
              <th className="num">Spend</th>
              <th className="num">New customers</th>
              <th className="num">Cost per customer</th>
              <th className="w-[280px]">Customer value against cost</th>
            </tr>
          </thead>
          <tbody>
            {sorted.map((a) => {
              const r = a.ltv_to_cac ?? 0;
              const v = VERDICT[a.verdict];
              return (
                <tr key={a.ad_id}>
                  <td>
                    <p className="font-medium">{a.ad_name}</p>
                    <p className="mt-1 inline-flex items-center gap-1.5 text-[0.92rem] text-ink-2"><BrandLogo brand={a.platform} className="h-3.5" />{a.campaign_name}</p>
                  </td>
                  <td><Badge tone={v.tone}>{v.label}</Badge></td>
                  <td className="num">{money(a.spend_window)}</td>
                  <td className="num">{num(a.new_customers_window)}</td>
                  <td className="num">{money(a.cac_window, 2)}</td>
                  <td>
                    <div className="flex items-center gap-3 pt-1">
                      <div className="relative h-[6px] flex-1 bg-canvas">
                        <div className={cx("absolute inset-y-0 left-0", a.verdict === "losing" ? "bg-bad" : a.verdict === "scale" ? "bg-good" : "bg-ink-2")}
                          style={{ width: `${Math.min(100, (r / max) * 100)}%` }} />
                        <div className="absolute -inset-y-1.5 w-px bg-ink" style={{ left: `${(1 / max) * 100}%` }} />
                      </div>
                      <span className="w-12 text-right font-semibold tabular-nums">{times(a.ltv_to_cac)}</span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-[0.95rem] text-ink-2">The thin vertical line marks break-even: an ad to the right of it wins customers worth more than they cost.</p>
    </>
  );
}

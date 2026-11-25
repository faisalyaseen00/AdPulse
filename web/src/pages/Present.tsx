import { Suspense, lazy, useCallback, useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { ArrowLeft, ArrowRight, Expand, X } from "lucide-react";
import { api, type AdRow, type Overview, type Wasted } from "@/lib/api";
import { date, money, num, pct, times, title } from "@/lib/format";
import { cx } from "@/components/ui";
import { KpiCard } from "@/components/KpiCard";
import { Logo } from "@/components/Logo";
import { Funnel } from "@/components/Funnel";
import { hasWebGL } from "@/robot/Fallback2D";

const RobotScene = lazy(() => import("@/robot/RobotScene"));
const PLATFORM: Record<string, string> = { meta: "#8aa0d6", google: "#b5c27a" };
const usd0 = (v: number) => money(v);
const int = (v: number) => num(Math.round(v));

/** Full-screen, data-driven client presentation. Arrow keys / space to move, Esc to leave. */
export default function Present() {
  const [params] = useSearchParams();
  const days = Number(params.get("days") ?? 30) || 30;
  const navigate = useNavigate();
  const ov = useQuery({ queryKey: ["overview", days], queryFn: () => api.get<Overview>(`/overview?days=${days}`) });
  const ws = useQuery({ queryKey: ["wasted", days, 5, false], queryFn: () => api.get<Wasted>(`/wasted?days=${days}&min_cost=5&ai=false`) });
  const [i, setI] = useState(() => Math.max(0, (Number(params.get("slide")) || 1) - 1));
  const [dir, setDir] = useState(1);

  const slides = ov.data && ws.data ? buildSlides(ov.data, ws.data) : [];
  const n = slides.length;
  const go = useCallback((to: number) => {
    setI((cur) => {
      const next = Math.max(0, Math.min(n - 1, to));
      setDir(next >= cur ? 1 : -1);
      return next;
    });
  }, [n]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (["ArrowRight", "PageDown", " ", "Enter"].includes(e.key)) { e.preventDefault(); go(i + 1); }
      else if (["ArrowLeft", "PageUp", "Backspace"].includes(e.key)) { e.preventDefault(); go(i - 1); }
      else if (e.key === "Home") go(0);
      else if (e.key === "End") go(n - 1);
      else if (e.key === "Escape" && !document.fullscreenElement) navigate("/");
      else if (e.key.toLowerCase() === "f") toggleFull();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, i, n, navigate]);

  const still = !!useReducedMotion();

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-[#16181d] text-white">
      {/* top bar */}
      <div className="flex h-14 shrink-0 items-center justify-between px-5 sm:px-8">
        <div className="flex items-center gap-2.5">
          <Logo dark className="[&_svg]:size-7" />
          <span className="hidden text-sm text-white/40 sm:inline">· Marketing review</span>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={toggleFull} className="rounded-lg p-2 text-white/60 hover:bg-white/10 hover:text-white" aria-label="Full screen (F)" title="Full screen (F)"><Expand className="size-5" /></button>
          <Link to="/" className="rounded-lg p-2 text-white/60 hover:bg-white/10 hover:text-white" aria-label="Close presentation (Esc)" title="Close (Esc)"><X className="size-5" /></Link>
        </div>
      </div>

      {/* slide */}
      <div className="relative min-h-0 flex-1 overflow-hidden">
        {!n ? (
          <div className="grid h-full place-items-center text-white/60">{ov.isError || ws.isError ? "Couldn't load the data for this presentation." : "Preparing your presentation…"}</div>
        ) : (
          <AnimatePresence mode="wait" custom={dir}>
            <motion.div
              key={i}
              custom={dir}
              initial={still ? false : { opacity: 0, x: dir * 60 }}
              animate={{ opacity: 1, x: 0 }}
              exit={still ? undefined : { opacity: 0, x: dir * -60 }}
              transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
              className="absolute inset-0 overflow-y-auto px-5 py-6 sm:px-12 lg:px-20"
            >
              <div className="mx-auto flex min-h-full max-w-[1180px] flex-col justify-center">{slides[i].body}</div>
            </motion.div>
          </AnimatePresence>
        )}
      </div>

      {/* controls */}
      <div className="flex h-16 shrink-0 items-center gap-4 px-5 sm:px-8">
        <button onClick={() => go(i - 1)} disabled={i === 0} className="rounded-md border border-white/20 p-2 text-white/80 hover:bg-white/10 disabled:opacity-30" aria-label="Previous slide"><ArrowLeft className="size-5" /></button>
        <div className="flex flex-1 items-center gap-1.5" role="tablist" aria-label="Slides">
          {slides.map((s, k) => (
            <button key={k} role="tab" aria-selected={k === i} aria-label={s.title} title={s.title} onClick={() => go(k)}
              className="group relative h-[3px] flex-1 overflow-hidden bg-white/15">
              <span className={cx("absolute inset-0 transition-colors", k <= i ? "bg-saffron" : "group-hover:bg-white/30")} />
            </button>
          ))}
        </div>
        <span className="w-14 text-right text-sm tabular-nums text-white/50">{n ? `${i + 1} / ${n}` : ""}</span>
        <button onClick={() => go(i + 1)} disabled={i >= n - 1} className="rounded-md bg-saffron p-2 text-ink hover:bg-[#e0a52a] disabled:opacity-30" aria-label="Next slide"><ArrowRight className="size-5" /></button>
      </div>
    </div>
  );
}

function toggleFull() {
  if (document.fullscreenElement) document.exitFullscreen?.();
  else document.documentElement.requestFullscreen?.().catch(() => {});
}

// ---------------------------------------------------------------- slide building blocks
function Kicker({ children }: { children: ReactNode }) {
  return <p className="kicker !text-white/60">{children}</p>;
}
function Heading({ children }: { children: ReactNode }) {
  return <h2 className="mt-4 max-w-[22ch] text-[2.5rem] leading-[1.05] sm:text-[3.5rem]">{children}</h2>;
}
function Sub({ children }: { children: ReactNode }) {
  return <p className="mt-4 max-w-[60ch] text-lg text-white/65">{children}</p>;
}
function Rise({ children, d = 0, className }: { children: ReactNode; d?: number; className?: string }) {
  const still = !!useReducedMotion();
  return (
    <motion.div className={className} initial={still ? false : { opacity: 0, y: 16 }} animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 + d, duration: 0.5, ease: [0.22, 1, 0.36, 1] }}>
      {children}
    </motion.div>
  );
}

function AdRows({ ads, tone }: { ads: AdRow[]; tone: "good" | "bad" }) {
  const max = Math.max(3, ...ads.map((a) => a.ltv_to_cac ?? 0));
  return (
    <div className="grid gap-3">
      {ads.map((a, k) => (
        <Rise key={a.ad_id} d={0.1 + k * 0.08}>
          <div className="rounded-md border border-white/15 p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-3">
              <div>
                <p className="text-lg font-semibold">{a.ad_name}</p>
                <p className="text-sm text-white/55"><span className="mr-1.5 inline-block size-2 rounded-[2px]" style={{ background: PLATFORM[a.platform] }} />{title(a.platform)} · {money(a.spend_window)} spent · {num(a.new_customers_window)} customers</p>
              </div>
              <p className={cx("font-display text-[2.2rem] leading-none", tone === "good" ? "text-[#7fd1a6]" : "text-[#f19a8e]")}>{times(a.ltv_to_cac)}</p>
            </div>
            <div className="relative mt-4 h-[5px] bg-white/10">
              <motion.div className="absolute inset-y-0 left-0" style={{ background: tone === "good" ? "#7fd1a6" : "#f19a8e" }}
                initial={{ width: 0 }} animate={{ width: `${Math.min(100, ((a.ltv_to_cac ?? 0) / max) * 100)}%` }} transition={{ delay: 0.4 + k * 0.08, duration: 0.8 }} />
              <div className="absolute -inset-y-1 w-px bg-white/50" style={{ left: `${(1 / max) * 100}%` }} />
            </div>
            <p className="mt-2 text-xs text-white/45">Each customer is worth {money(a.ltv_estimate, 2)} and costs {money(a.cac_window, 2)} to win. The white line is break-even.</p>
          </div>
        </Rise>
      ))}
    </div>
  );
}

function RobotCorner() {
  const [webgl] = useState(hasWebGL);
  if (!webgl) return null;
  return (
    <div className="pointer-events-none mx-auto h-[260px] w-[220px]">
      <Suspense fallback={null}><RobotScene modelUrl="/robot.glb" state="happy" variant="launcher" active reducedMotion={false} /></Suspense>
    </div>
  );
}

// ---------------------------------------------------------------- the deck, from live data
function buildSlides(d: Overview, w: Wasted): { title: string; body: ReactNode }[] {
  const k = d.kpis;
  const labels = d.daily.map((r) => date(r.day));
  const ads = d.ads;
  const winners = [...ads].filter((a) => a.verdict === "scale" || (a.ltv_to_cac ?? 0) >= 2.5).sort((a, b) => (b.ltv_to_cac ?? 0) - (a.ltv_to_cac ?? 0)).slice(0, 3);
  const losers = [...ads].filter((a) => a.verdict === "losing").sort((a, b) => b.spend_window - a.spend_window).slice(0, 3);
  const lostSpend = losers.reduce((a, x) => a + x.spend_window, 0);
  const period = `${date(d.daily[0]?.day, { month: "long", day: "numeric" })} – ${date(d.end_date, { month: "long", day: "numeric", year: "numeric" })}`;
  const totalSpend = d.platform_cac.reduce((a, p) => a + p.spend, 0);
  const verdictLine = d.roas >= 1.5 ? "Advertising is clearly profitable." : d.roas >= 1 ? "Advertising pays for itself, with room to grow." : "Advertising currently costs more than it returns.";

  return [
    {
      title: "Cover",
      body: (
        <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          <div>
            <Rise><Kicker>Marketing performance review</Kicker></Rise>
            <Rise d={0.05}><h1 className="mt-4 font-display text-[3.2rem] font-medium leading-[1.0] tracking-[-0.02em] sm:text-[5rem]">How your ads turned into customers</h1></Rise>
            <Rise d={0.12}><p className="mt-6 text-xl text-white/60">{period} · last {d.days} days</p></Rise>
            <Rise d={0.2}><p className="mt-10 text-sm text-white/40">Prepared with AdPulse. Every number comes straight from your ad, website and shop data.</p></Rise>
          </div>
          <Rise d={0.15} className="hidden lg:block">
            <div className="rounded-md border border-white/15 p-8">
              <p className="text-white/60">Every $1 on ads brought back</p>
              <p className="mt-2 font-display text-[6rem] leading-none tracking-[-0.03em] text-saffron">{money(d.roas, 2)}</p>
              <p className="mt-6 text-white/70">{verdictLine}</p>
            </div>
          </Rise>
        </div>
      ),
    },
    {
      title: "The bottom line",
      body: (
        <>
          <Rise><Kicker>The bottom line</Kicker></Rise>
          <Rise d={0.05}><Heading>{money(k.revenue)} in sales from {money(k.spend)} of ads</Heading></Rise>
          <Rise d={0.1}><Sub>{verdictLine} {num(k.customers)} new customers joined, each costing {money(k.cac, 2)} to win.</Sub></Rise>
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            <KpiCard dark label="Sales from ads" value={k.revenue} format={usd0} change={k.revenue_change} series={d.daily.map((r) => r.revenue)} seriesLabels={labels} accent="#d4920f" note="vs previous period" />
            <KpiCard dark label="Ad spend" value={k.spend} format={usd0} change={k.spend_change} better="neutral" series={d.daily.map((r) => r.spend)} seriesLabels={labels} accent="#c8c9c2" delay={0.1} />
            <KpiCard dark label="New customers" value={k.customers} format={int} change={k.customers_change} series={d.daily.map((r) => r.customers)} seriesLabels={labels} accent="#7fd1a6" delay={0.2} />
          </div>
        </>
      ),
    },
    {
      title: "From ad to customer",
      body: (
        <>
          <Rise><Kicker>From ad to customer</Kicker></Rise>
          <Rise d={0.05}><Heading>{num(d.journey.impressions)} ad views became {num(d.journey.customers)} customers</Heading></Rise>
          <Rise d={0.1}><Sub>{pct(d.journey.impressions ? d.journey.clicks / d.journey.impressions : 0)} of people who saw an ad clicked, and {pct(d.journey.sessions ? d.journey.customers / d.journey.sessions : 0)} of website visits turned into a sale.</Sub></Rise>
          <Rise d={0.15} className="mt-12">
            <Funnel dark color="#f4f4f1" stages={[
              { label: "Saw an ad", value: d.journey.impressions, display: compact(d.journey.impressions) },
              { label: "Clicked", value: d.journey.clicks, display: compact(d.journey.clicks), rate: pct(d.journey.impressions ? d.journey.clicks / d.journey.impressions : 0) + " of viewers" },
              { label: "Visited the site", value: d.journey.sessions, display: compact(d.journey.sessions) },
              { label: "Became customers", value: d.journey.customers, display: num(d.journey.customers), rate: pct(d.journey.sessions ? d.journey.customers / d.journey.sessions : 0) + " of visits" },
            ]} />
          </Rise>
        </>
      ),
    },
    {
      title: "Meta vs Google",
      body: (
        <>
          <Rise><Kicker>Meta vs Google</Kicker></Rise>
          <Rise d={0.05}><Heading>{d.platform_cac.length > 1 ? `${title(d.platform_cac[0].platform)} wins customers ${money(d.platform_cac[d.platform_cac.length - 1].cac - d.platform_cac[0].cac, 2)} cheaper` : "Where the budget went"}</Heading></Rise>
          <div className="mt-12 grid gap-4 md:grid-cols-2">
            {d.platform_cac.map((p, k2) => (
              <Rise key={p.platform} d={0.12 + k2 * 0.08}>
                <div className="rounded-md border border-white/15 p-7">
                  <div className="flex items-center gap-2 text-lg font-semibold"><span className="size-3 rounded-[2px]" style={{ background: PLATFORM[p.platform] }} />{title(p.platform)}</div>
                  <p className="mt-6 text-white/55">Cost to win one customer</p>
                  <p className="font-display text-[3.6rem] leading-none tracking-[-0.02em]">{money(p.cac, 2)}</p>
                  <div className="mt-6 grid grid-cols-2 gap-4 border-t border-white/10 pt-5 text-sm">
                    <div><p className="text-white/50">Ad spend</p><p className="text-xl font-semibold">{money(p.spend)}</p><p className="text-xs text-white/40">{pct(totalSpend ? p.spend / totalSpend : 0, 0)} of budget</p></div>
                    <div><p className="text-white/50">New customers</p><p className="text-xl font-semibold">{num(p.customers)}</p></div>
                  </div>
                </div>
              </Rise>
            ))}
          </div>
        </>
      ),
    },
    {
      title: "What's working",
      body: (
        <>
          <Rise><Kicker>What's working</Kicker></Rise>
          <Rise d={0.05}><Heading>These ads win customers worth far more than they cost</Heading></Rise>
          <div className="mt-10">{winners.length ? <AdRows ads={winners} tone="good" /> : <Sub>No ad clearly stands out in this period.</Sub>}</div>
        </>
      ),
    },
    {
      title: "What's leaking",
      body: (
        <>
          <Rise><Kicker>What's leaking</Kicker></Rise>
          <Rise d={0.05}><Heading>{losers.length ? `${losers.length} ads spent ${money(lostSpend)} on customers worth less than they cost` : "No ad is losing money right now"}</Heading></Rise>
          <div className="mt-10">{losers.length ? <AdRows ads={losers} tone="bad" /> : null}</div>
        </>
      ),
    },
    {
      title: "Wasted searches",
      body: (
        <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
          <div>
            <Rise><Kicker>Wasted searches</Kicker></Rise>
            <Rise d={0.05}><Heading>{money(w.summary.wasted_spend)} paid for clicks that were never going to buy</Heading></Rise>
            <Rise d={0.1}><Sub>{num(w.summary.flagged)} Google searches came from job hunters, freebie seekers and people looking for a café. That is {pct(w.summary.wasted_share, 0)} of the search budget.</Sub></Rise>
          </div>
          <Rise d={0.15}>
            <div className="rounded-md border border-white/15 p-7">
              {w.reasons.slice(0, 6).map((r, k2) => (
                <div key={r.reason} className="py-2.5">
                  <div className="flex justify-between text-sm"><span className="text-white/80">{r.reason}</span><b className="font-semibold">{money(r.wasted_spend)}</b></div>
                  <div className="mt-1.5 h-[5px] bg-white/10">
                    <motion.div className="h-[5px] bg-[#f19a8e]" initial={{ width: 0 }} animate={{ width: `${(r.wasted_spend / w.reasons[0].wasted_spend) * 100}%` }} transition={{ delay: 0.3 + k2 * 0.06, duration: 0.7 }} />
                  </div>
                </div>
              ))}
            </div>
          </Rise>
        </div>
      ),
    },
    {
      title: "Next steps",
      body: (
        <>
          <Rise><Kicker>Recommended next steps</Kicker></Rise>
          <Rise d={0.05}><Heading>{d.next_steps.length === 1 ? "One move" : `${d.next_steps.length} moves`}, each approved by you before anything changes</Heading></Rise>
          <div className="mt-10 grid gap-4 lg:grid-cols-3">
            {d.next_steps.map((s, k2) => {
              const c = s.tone === "good" ? "#7fd1a6" : s.tone === "bad" ? "#f19a8e" : "#d4920f";
              return (
                <Rise key={s.title} d={0.1 + k2 * 0.08}>
                  <div className="flex h-full flex-col rounded-md border border-white/15 p-6">
                    <span className="font-display text-[2rem] leading-none text-white/35">{String(k2 + 1).padStart(2, "0")}</span>
                    <p className="mt-5 text-lg font-semibold leading-snug">{s.title}</p>
                    <p className="mt-2 flex-1 text-sm text-white/60">{s.detail}</p>
                    <p className="mt-6 font-display text-[2.2rem] leading-none" style={{ color: c }}>{s.value}</p>
                    <p className="text-sm text-white/50">{s.value_note}</p>
                  </div>
                </Rise>
              );
            })}
          </div>
        </>
      ),
    },
    {
      title: "Ask anything",
      body: (
        <div className="grid items-center gap-8 lg:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
          <div>
            <Rise><Kicker>Ask anything</Kicker></Rise>
            <Rise d={0.05}><Heading>Questions get plain answers, checked against your data</Heading></Rise>
            <Rise d={0.1}><Sub>Type a question the way you would ask a colleague. AdPulse looks it up, a second step double-checks the logic, and every number in the answer is matched to your real data.</Sub></Rise>
            <Rise d={0.18}>
              <div className="mt-8 grid gap-2">
                {["Which ads brought in the most valuable customers last month?", "Is Meta or Google cheaper for new customers?", "Where are we wasting money?"].map((q2) => (
                  <div key={q2} className="w-fit border-l-2 border-saffron pl-3 font-display text-[1.15rem] text-white/85">{q2}</div>
                ))}
              </div>
            </Rise>
            <Rise d={0.24}>
              <Link to="/ask" className="mt-8 inline-flex h-10 items-center gap-2 rounded-md bg-saffron px-4 font-medium text-ink hover:bg-[#e0a52a]">Try it live <ArrowRight className="size-4" /></Link>
            </Rise>
          </div>
          <Rise d={0.1}><RobotCorner /></Rise>
        </div>
      ),
    },
  ];
}

function compact(v: number) {
  return v >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : v >= 1e4 ? `${Math.round(v / 1e3)}k` : num(v);
}

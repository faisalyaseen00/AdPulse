import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Menu, X } from "lucide-react";
import { api, type Health } from "@/lib/api";
import { date } from "@/lib/format";
import { setReviewer, useReviewer } from "@/lib/reviewer";
import { cx } from "./ui";
import { Logo } from "./Logo";
import RobotLauncher from "./RobotLauncher";

const NAV = [
  { to: "/", label: "Overview" },
  { to: "/ask", label: "Ask" },
  { to: "/suggestions", label: "Suggestions" },
  { to: "/wasted", label: "Wasted searches" },
  { to: "/report", label: "Weekly report" },
  { to: "/data", label: "Data" },
];

function NavItems({ pending, onNavigate, vertical }: { pending?: number; onNavigate?: () => void; vertical?: boolean }) {
  return (
    <>
      {NAV.map((n) => (
        <NavLink key={n.to} to={n.to} end={n.to === "/"} onClick={onNavigate}
          className={({ isActive }) => cx(
            "relative flex items-center whitespace-nowrap text-[0.92rem] transition-colors",
            vertical ? "py-3 text-lg" : "h-16",
            isActive
              ? cx("font-semibold text-ink", !vertical && "after:absolute after:inset-x-0 after:bottom-[-1px] after:h-[2px] after:bg-ink")
              : "text-muted hover:text-ink",
          )}>
          {n.label}
          {n.to === "/suggestions" && pending ? (
            <span className="ml-1.5 rounded-[4px] bg-saffron-soft px-1.5 py-px text-[0.72rem] font-semibold tabular-nums text-marigold-ink">{pending}</span>
          ) : null}
        </NavLink>
      ))}
    </>
  );
}

/** "Reviewing as …": the name saved with every approval. */
function Reviewer() {
  const name = useReviewer();
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState(name);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const off = (e: MouseEvent) => { if (!box.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", off);
    return () => document.removeEventListener("mousedown", off);
  }, [open]);
  return (
    <div className="relative" ref={box}>
      <button type="button" onClick={() => { setDraft(name); setOpen((o) => !o); }} aria-expanded={open}
        className="text-[0.86rem] text-muted hover:text-ink">
        {name ? <>Reviewing as <span className="font-semibold text-ink underline decoration-line-strong underline-offset-4">{name}</span></>
          : <span className="underline decoration-line-strong underline-offset-4">Add your name</span>}
      </button>
      {open && (
        <form onSubmit={(e) => { e.preventDefault(); setReviewer(draft); setOpen(false); }}
          className="absolute right-0 top-[calc(100%+10px)] z-50 w-72 rounded-md border border-ink bg-surface p-4 shadow-[0_12px_32px_-12px_rgb(22_24_29/0.35)]">
          <label htmlFor="reviewer" className="text-[0.84rem] font-semibold">Your name</label>
          <p className="mt-0.5 text-xs text-muted">Saved with every approve or reject, so the team knows who decided.</p>
          <div className="mt-3 flex gap-2">
            <input id="reviewer" autoFocus value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="e.g. Faisal"
              className="h-9 min-w-0 flex-1 rounded-md border border-line-strong px-3 text-sm focus:border-ink focus:outline-none" />
            <button type="submit" className="h-9 rounded-md bg-ink px-3 text-sm font-medium text-white">Save</button>
          </div>
        </form>
      )}
    </div>
  );
}

export default function Layout() {
  const { pathname } = useLocation();
  const [open, setOpen] = useState(false);
  const { data: h } = useQuery({ queryKey: ["health"], queryFn: () => api.get<Health>("/health"), refetchInterval: 60_000 });

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-paper/95 backdrop-saturate-150">
        <div className="mx-auto flex h-16 w-full items-center gap-10 px-[clamp(20px,2.6vw,48px)]">
          <Link to="/" aria-label="AdPulse home" className="shrink-0"><Logo /></Link>
          <nav aria-label="Main" className="hidden items-center gap-7 lg:flex">
            <NavItems pending={h?.pending} />
          </nav>
          <div className="ml-auto hidden items-center gap-5 lg:flex">
            <Reviewer />
            <Link to="/present" className="inline-flex h-9 items-center rounded-md bg-ink px-3.5 text-[0.86rem] font-medium text-white hover:bg-ink-2">
              Present
            </Link>
          </div>
          <button className="ml-auto rounded-md p-2 hover:bg-canvas lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">
            <Menu className="size-5" />
          </button>
        </div>
      </header>

      {open && (
        <div className="fixed inset-0 z-40 bg-paper lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <div className="flex h-16 items-center justify-between border-b border-line px-5">
            <Logo />
            <button className="rounded-md p-2 hover:bg-canvas" onClick={() => setOpen(false)} aria-label="Close menu"><X className="size-5" /></button>
          </div>
          <nav className="grid divide-y divide-line px-5" aria-label="Main">
            <NavItems vertical pending={h?.pending} onNavigate={() => setOpen(false)} />
            <Link to="/present" onClick={() => setOpen(false)} className="py-3 text-lg">Present to client</Link>
          </nav>
          <div className="px-5 pt-6"><Reviewer /></div>
        </div>
      )}

      <main className="mx-auto w-full flex-1 px-[clamp(20px,2.6vw,48px)] pb-24 pt-10 sm:pt-14">
        <Outlet />
      </main>

      <footer className="bg-ink text-paper">
        <div className={cx("mx-auto grid w-full gap-x-12 gap-y-10 px-[clamp(20px,2.6vw,48px)] pb-10 pt-14 md:grid-cols-2 xl:grid-cols-[minmax(0,1.6fr)_repeat(3,minmax(0,1fr))]", pathname === "/" && "lg:pr-32")}>
          <div className="max-w-[42ch]">
            <Logo dark size="lg" />
            <p className="mt-5 text-[1rem] leading-relaxed text-white/70">
              Marketing intelligence for people who run the business. Every figure here is computed from your own ad,
              website and shop data, and nothing changes in your ad accounts without your approval.
            </p>
          </div>
          {[
            { head: "Insights", links: [["/", "Overview"], ["/ask", "Ask a question"], ["/present", "Present to a client"]] },
            { head: "Actions", links: [["/suggestions", "Suggestions"], ["/wasted", "Wasted searches"], ["/report", "Weekly report"]] },
          ].map((col) => (
            <nav key={col.head} aria-label={col.head}>
              <p className="text-[0.95rem] font-semibold text-white">{col.head}</p>
              <ul className="mt-4 grid gap-2.5">
                {col.links.map(([to, label]) => (
                  <li key={to}><Link to={to} className="text-[0.98rem] text-white/70 transition-colors hover:text-white">{label}</Link></li>
                ))}
              </ul>
            </nav>
          ))}
          <div>
            <p className="text-[0.95rem] font-semibold text-white">System</p>
            <ul className="mt-4 grid gap-2.5 text-[0.98rem] text-white/70">
              {[
                [!!h?.warehouse, h?.warehouse ? `Data up to ${date(h.data_until, { month: "long", day: "numeric" })}` : "Data not connected"],
                [!!h?.ai, h?.ai ? "AI assistant ready" : "AI assistant off"],
                [!!h?.slack, h?.slack ? "Slack reports on" : "Slack not set up"],
              ].map(([ok, label]) => (
                <li key={String(label)} className="flex items-center gap-2.5">
                  <span className={cx("size-1.5 rounded-full", ok ? "bg-[#7fd1a6]" : "bg-white/30")} aria-hidden />{label}
                </li>
              ))}
              <li><Link to="/data" className="text-white/70 underline decoration-white/30 underline-offset-4 hover:text-white">Data status</Link></li>
            </ul>
          </div>
        </div>
        <div className="border-t border-white/10">
          <div className={cx("mx-auto flex w-full flex-wrap items-center justify-between gap-x-8 gap-y-2 px-[clamp(20px,2.6vw,48px)] py-5 text-[0.9rem] text-white/50", pathname === "/" && "lg:pr-32")}>
            <span>© {new Date().getFullYear()} AdPulse</span>
            <span>Read-only analysis. Changes to Meta and Google are made by people, after approval.</span>
          </div>
        </div>
      </footer>

      {pathname === "/" && <RobotLauncher />}
    </div>
  );
}

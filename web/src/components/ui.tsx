import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Loader2 } from "lucide-react";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

/** Page title in the serif, with an optional kicker line above and a short standfirst below. */
export function PageHeader({ title, description, actions, kicker }: { title: string; description?: string; actions?: ReactNode; kicker?: string }) {
  return (
    <header className="mb-10 flex flex-wrap items-end justify-between gap-x-8 gap-y-4 border-b border-ink pb-6">
      <div className="min-w-0">
        {kicker && <p className="kicker mb-3">{kicker}</p>}
        <h1 className="text-[clamp(2.1rem,3.6vw,3.1rem)] leading-[1.02] text-ink">{title}</h1>
        {description && <p className="mt-3 max-w-[62ch] text-[0.98rem] leading-relaxed text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

export function Card({ children, className, pad = true }: { children: ReactNode; className?: string; pad?: boolean }) {
  return <section className={cx("rounded-md border border-line bg-surface", pad && "p-6", className)}>{children}</section>;
}

/** Section heading: serif title, optional note, hairline underneath. */
export function SectionTitle({ children, note, action }: { children: ReactNode; note?: string; action?: ReactNode }) {
  return (
    <div className="mb-5 mt-14 flex flex-wrap items-baseline justify-between gap-3 border-b border-line pb-3">
      <div className="flex flex-wrap items-baseline gap-3">
        <h2 className="text-[1.55rem] leading-tight">{children}</h2>
        {note && <span className="text-[0.95rem] text-muted">{note}</span>}
      </div>
      {action}
    </div>
  );
}

type Tone = "good" | "bad" | "warn" | "info" | "muted";
const DOT: Record<Tone, string> = {
  good: "bg-good", bad: "bg-bad", warn: "bg-saffron", info: "bg-ink", muted: "bg-faint",
};
const TEXT: Record<Tone, string> = {
  good: "text-good", bad: "text-bad", warn: "text-marigold-ink", info: "text-ink", muted: "text-muted",
};
/** Status label: a coloured dot and text. No filled pills. */
export function Badge({ tone = "muted", children }: { tone?: Tone; children: ReactNode }) {
  return (
    <span className={cx("inline-flex items-center gap-1.5 whitespace-nowrap text-[0.9rem] font-medium", TEXT[tone])}>
      <span className={cx("size-1.5 rounded-full", DOT[tone])} aria-hidden />
      {children}
    </span>
  );
}

type BtnKind = "primary" | "secondary" | "ghost" | "danger";
const BTN: Record<BtnKind, string> = {
  primary: "bg-ink text-white hover:bg-ink-2",
  secondary: "border border-line-strong bg-surface text-ink hover:border-ink",
  ghost: "text-ink-2 underline-offset-4 hover:underline",
  danger: "border border-line-strong bg-surface text-bad hover:border-bad",
};
export function Button({ kind = "secondary", loading, children, className, disabled, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { kind?: BtnKind; loading?: boolean }) {
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx("inline-flex h-9 items-center justify-center gap-2 rounded-md px-3.5 text-[0.86rem] font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-45", BTN[kind], className)}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

/** Period switch drawn as text tabs with an ink underline, like a report's section tabs. */
export function Segmented<T extends string | number>({ value, options, onChange, label }:
  { value: T; options: { value: T; label: string }[]; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex items-center gap-5">
      {options.map((o) => (
        <button
          key={String(o.value)}
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={cx("relative h-10 text-[0.98rem] transition-colors",
            o.value === value
              ? "font-semibold text-ink after:absolute after:inset-x-0 after:bottom-0 after:h-[2px] after:bg-ink"
              : "text-ink-2 hover:text-ink")}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** "+2.2%" / "−1.6%" coloured by whether the move is good for the business. */
export function Change({ value, better = "up", suffix = "vs previous period" }:
  { value: number | null | undefined; better?: "up" | "down" | "neutral"; suffix?: string }) {
  if (value == null) return <span className="text-sm text-faint">No earlier data</span>;
  const up = value > 0;
  const flat = Math.abs(value) < 0.005;
  const good = flat || better === "neutral" ? null : up === (better === "up");
  return (
    <span className="text-[0.92rem] text-ink-2">
      <span className={cx("font-semibold tabular-nums", good === true && "text-good", good === false && "text-bad", good === null && "text-ink-2")}>
        {flat ? "flat" : `${up ? "+" : "−"}${(Math.abs(value) * 100).toFixed(1)}%`}
      </span>
      {suffix ? ` ${suffix}` : ""}
    </span>
  );
}

/** A figure in a row of figures: label, serif number, one line of context. */
export function Stat({ label, value, children, hint }: { label: string; value: ReactNode; children?: ReactNode; hint?: string }) {
  return (
    <div className="min-w-0 border-l border-line py-1 pl-5 first:border-l-0 first:pl-0" title={hint}>
      <div className="text-[0.95rem] font-medium text-ink-2">{label}</div>
      <div className="mt-2 font-display text-[2rem] leading-none tracking-[-0.02em]">{value}</div>
      <div className="mt-2 min-h-5">{children}</div>
    </div>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx("animate-pulse rounded-md bg-canvas", className)} />;
}

export function LoadingBlock({ rows = 3 }: { rows?: number }) {
  return (
    <div className="grid gap-4" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <Skeleton key={i} className="h-24" />)}
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  return (
    <div className="flex flex-wrap items-start gap-4 border-l-2 border-bad bg-surface py-4 pl-5 pr-4">
      <div className="flex-1">
        <p className="font-semibold">This section didn't load.</p>
        <p className="mt-0.5 text-sm text-muted">{error instanceof Error ? error.message : "Unknown error"}</p>
      </div>
      {onRetry && <Button onClick={onRetry}>Try again</Button>}
    </div>
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="grid gap-1.5 text-sm">
      <span className="font-medium text-ink-2">{label}</span>
      {children}
      {hint && <span className="text-xs text-faint">{hint}</span>}
    </label>
  );
}

export const inputCls = "h-9 rounded-md border border-line-strong bg-surface px-3 text-sm text-ink placeholder:text-faint focus:border-ink focus:outline-none";

export function Toggle({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2.5 text-sm text-ink-2">
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        onClick={() => onChange(!checked)}
        className={cx("relative h-[18px] w-8 rounded-[5px] border transition-colors", checked ? "border-ink bg-ink" : "border-line-strong bg-surface")}
      >
        <span className={cx("absolute top-[2px] size-3 rounded-[3px] transition-all", checked ? "left-[15px] bg-white" : "left-[2px] bg-line-strong")} />
      </button>
      {label}
    </label>
  );
}

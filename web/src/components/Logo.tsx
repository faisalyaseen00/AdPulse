import { cx } from "./ui";

/**
 * AdPulse wordmark: set in Newsreader, "Ad" upright and "Pulse" in italic, tightly tracked, so the name itself is the
 * logo. No separate mark. `dark` inverts it for the presentation deck.
 */
export function Logo({ dark = false, className, size = "md" }: { dark?: boolean; className?: string; size?: "sm" | "md" | "lg" }) {
  const scale = size === "lg" ? "text-[2.2rem]" : size === "sm" ? "text-[1.3rem]" : "text-[1.7rem]";
  return (
    <span className={cx("inline-flex items-baseline font-display leading-none tracking-[-0.035em]", scale, dark ? "text-paper" : "text-ink", className)}>
      <span className="font-semibold">Ad</span>
      <span className="font-medium italic">Pulse</span>
    </span>
  );
}

/** Kept for the favicon-sized contexts that still want a square mark (browser tab icon). */
export function Mark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cx("shrink-0", className)} aria-hidden>
      <rect width="32" height="32" rx="7" fill="#16181d" />
      <text x="16" y="22.5" textAnchor="middle" fontFamily="Newsreader, Georgia, serif" fontSize="17" fontWeight="600" fill="#f4f4f1">A</text>
      <text x="22.5" y="22.5" textAnchor="middle" fontFamily="Newsreader, Georgia, serif" fontSize="17" fontStyle="italic" fill="#d4920f">p</text>
    </svg>
  );
}

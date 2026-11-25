/*
Adapted from "Funnel Chart" by bklitai (21st.dev registry component).
Changes for AdPulse: horizontal only, log-scaled widths (ad views to customers span three orders of magnitude, so a
linear funnel collapses to a line), step-to-step conversion labels, AdPulse colours, light/dark, reduced motion.
*/
import { useCallback, useEffect, useRef, useState } from "react";
import { motion, useReducedMotion, useSpring, useTransform } from "motion/react";
import { cx } from "./ui";

export interface FunnelStage {
  label: string;
  value: number;
  display: string;
  /** shown under the label, e.g. "1.8% of views clicked" */
  rate?: string;
}

const spring = { stiffness: 120, damping: 20, mass: 1 };

function segPath(n0: number, n1: number, w: number, H: number, scale: number) {
  const my = H / 2;
  const h0 = n0 * H * 0.42 * scale;
  const h1 = n1 * H * 0.42 * scale;
  const cx = w * 0.55;
  return `M 0 ${my - h0} C ${cx} ${my - h0}, ${w - cx} ${my - h1}, ${w} ${my - h1} L ${w} ${my + h1} C ${w - cx} ${my + h1}, ${cx} ${my + h0}, 0 ${my + h0} Z`;
}

function Segment({ i, n0, n1, w, H, color, hovered, dimmed, still }: {
  i: number; n0: number; n1: number; w: number; H: number; color: string; hovered: boolean; dimmed: boolean; still: boolean;
}) {
  const grow = useSpring(still ? 1 : 0, spring);
  const sx = useTransform(grow, [0, 1], [0, 1]);
  const op = useSpring(1, { stiffness: 300, damping: 24 });
  const lift = useSpring(1, { stiffness: 300, damping: 22 });
  useEffect(() => { op.set(dimmed ? 0.35 : 1); }, [dimmed, op]);
  useEffect(() => { lift.set(hovered ? 1.08 : 1); }, [hovered, lift]);
  useEffect(() => {
    if (still) return;
    const t = setTimeout(() => grow.set(1), i * 140);
    return () => clearTimeout(t);
  }, [grow, i, still]);
  const layers = [1, 0.82, 0.66];
  return (
    <motion.div className="pointer-events-none relative shrink-0" style={{ width: w, height: H, opacity: op }}>
      <motion.div className="absolute inset-0" style={{ scaleX: sx, scaleY: lift, transformOrigin: "left center" }}>
        <svg className="absolute inset-0 h-full w-full overflow-visible" viewBox={`0 0 ${w} ${H}`} preserveAspectRatio="none" aria-hidden>
          {layers.map((s, l) => (
            <path key={l} d={segPath(n0, n1, w, H, s)} fill={color} opacity={0.07 + l * 0.11} />
          ))}
        </svg>
      </motion.div>
    </motion.div>
  );
}

export function Funnel({ stages, color = "#16181d", dark, className }: {
  stages: FunnelStage[]; color?: string; dark?: boolean; className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [sz, setSz] = useState({ w: 0, h: 0 });
  const [hover, setHover] = useState<number | null>(null);
  const still = !!useReducedMotion();
  const measure = useCallback(() => {
    const r = ref.current?.getBoundingClientRect();
    if (r && r.width > 0 && r.height > 0) setSz({ w: r.width, h: r.height });
  }, []);
  useEffect(() => {
    measure();
    const ro = new ResizeObserver(measure);
    if (ref.current) ro.observe(ref.current);
    return () => ro.disconnect();
  }, [measure]);

  // log scale: the last stage still has visible thickness
  const logs = stages.map((s) => Math.log10(Math.max(1, s.value)));
  const top = Math.max(...logs);
  const bottom = Math.min(...logs);
  const norm = logs.map((l) => 0.22 + 0.78 * ((l - bottom) / Math.max(0.0001, top - bottom)));
  const gap = 4;
  const n = stages.length;
  const segW = (sz.w - gap * (n - 1)) / n;

  return (
    <div className={cx("relative w-full select-none", className)}>
      <div ref={ref} className="relative h-[200px] w-full">
        {sz.w > 0 && (
          <div className="absolute inset-0 flex" style={{ gap }}>
            {stages.map((s, i) => (
              <Segment key={s.label} i={i} n0={norm[i]} n1={norm[Math.min(i + 1, n - 1)]} w={segW} H={sz.h}
                color={color} hovered={hover === i} dimmed={hover !== null && hover !== i} still={still} />
            ))}
          </div>
        )}
        {sz.w > 0 && stages.map((s, i) => (
          <div key={s.label} className="absolute top-0 flex h-full items-center justify-center"
            style={{ left: (segW + gap) * i, width: segW }}
            onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <motion.span
              initial={still ? false : { opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: still ? 0 : i * 0.14 + 0.35, duration: 0.35 }}
              className={cx("rounded-[4px] px-2 py-0.5 text-[0.78rem] font-semibold tabular-nums",
                dark ? "bg-white text-ink" : "bg-ink text-white")}
            >
              {s.display}
            </motion.span>
          </div>
        ))}
      </div>
      <div className="mt-3 grid" style={{ gridTemplateColumns: `repeat(${n}, minmax(0, 1fr))`, gap }}>
        {stages.map((s, i) => (
          <div key={s.label} className={cx("px-1 text-center transition-opacity", hover !== null && hover !== i && "opacity-40")}>
            <div className={cx("text-[0.98rem] font-semibold", dark ? "text-white" : "text-ink")}>{s.label}</div>
            {s.rate && <div className={cx("mt-0.5 text-[0.9rem]", dark ? "text-white/65" : "text-ink-2")}>{s.rate}</div>}
          </div>
        ))}
      </div>
    </div>
  );
}

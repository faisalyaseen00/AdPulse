/*
Adapted from "Tweenly Chart KPI" by Manjunath Irukulla (21st.dev, MIT License).
Copyright (c) 2026 Manjunath Irukulla. Permission is hereby granted, free of charge, to any person obtaining a copy of
this software, to deal in the Software without restriction, subject to including this notice. THE SOFTWARE IS
PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND.

AdPulse edition: an editorial "figure" rather than a card. Serif headline number with a count-up, a signed change
coloured by business meaning, and a hairline sparkline you can scrub. No fills, dots or pills.
*/
import { useEffect, useRef, useState } from "react";
import { animate, useInView, useReducedMotion } from "motion/react";
import { cx } from "./ui";

const EASE = [0.22, 1, 0.36, 1] as const;

export interface KpiCardProps {
  label: string;
  value: number;
  format: (n: number) => string;
  change?: number | null;
  better?: "up" | "down" | "neutral";
  series?: number[];
  seriesLabels?: string[];
  note?: string;
  accent?: string;
  dark?: boolean;
  delay?: number;
  className?: string;
}

function useCountUp(target: number, format: (n: number) => string, run: boolean, still: boolean, delay: number) {
  const ref = useRef<HTMLSpanElement>(null);
  const cur = useRef(0);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (still) { cur.current = target; el.textContent = format(target); return; }
    el.textContent = format(cur.current);
    if (!run) return;
    const c = animate(cur.current, target, {
      duration: 0.9, delay, ease: EASE,
      onUpdate: (v) => { cur.current = v; el.textContent = format(v); },
    });
    return () => c.stop();
  }, [target, format, run, still, delay]);
  return ref;
}

function path(values: number[], w: number, h: number) {
  const lo = Math.min(...values), hi = Math.max(...values);
  const span = hi - lo || 1;
  const n = values.length;
  return values.map((v, i) => {
    const x = n > 1 ? (i / (n - 1)) * w : w / 2;
    const y = 3 + (1 - (v - lo) / span) * (h - 6);
    return [x, y] as [number, number];
  });
}

function Spark({ values, labels, color, format, dark }: { values: number[]; labels?: string[]; color: string; format: (n: number) => string; dark?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(0);
  const [hover, setHover] = useState<number | null>(null);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    setW(el.getBoundingClientRect().width);
    const ro = new ResizeObserver(([e]) => setW(e.contentRect.width));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const h = 34;
  const pts = w ? path(values, w, h) : [];
  const d = pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
  const at = hover ?? pts.length - 1;
  return (
    <div ref={box} className="relative mt-4 h-[34px] w-full"
      onPointerMove={(e) => {
        if (!w) return;
        const r = e.currentTarget.getBoundingClientRect();
        setHover(Math.max(0, Math.min(values.length - 1, Math.round(((e.clientX - r.left) / w) * (values.length - 1)))));
      }}
      onPointerLeave={() => setHover(null)}>
      {w > 0 && (
        <svg width={w} height={h} className="block overflow-visible" aria-hidden>
          <path d={d} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
          <circle cx={pts[at][0]} cy={pts[at][1]} r={2.75} fill={color} />
        </svg>
      )}
      {hover !== null && (
        <div className={cx("pointer-events-none absolute -top-7 whitespace-nowrap text-[0.85rem]", dark ? "text-white/80" : "text-muted")}
          style={{ left: Math.min(Math.max(pts[at][0] - 40, 0), Math.max(0, w - 110)) }}>
          {labels?.[at] ? `${labels[at]}: ` : ""}<span className={dark ? "font-semibold text-white" : "font-semibold text-ink"}>{format(values[at])}</span>
        </div>
      )}
    </div>
  );
}

export function KpiCard({ label, value, format, change, better = "up", series, seriesLabels, note, accent, dark, delay = 0, className }: KpiCardProps) {
  const box = useRef<HTMLDivElement>(null);
  const inView = useInView(box, { once: true, margin: "-40px" });
  const still = !!useReducedMotion();
  const countRef = useCountUp(value, format, inView, still, delay);

  const has = change != null && Number.isFinite(change);
  const up = has && change! > 0;
  const flat = has && Math.abs(change!) < 0.005;
  const good = !has || flat || better === "neutral" ? null : up === (better === "up");
  const tone = good === true ? (dark ? "text-[#7fd1a6]" : "text-good") : good === false ? (dark ? "text-[#f19a8e]" : "text-bad") : dark ? "text-white/80" : "text-ink-2";

  return (
    <div ref={box} className={cx("min-w-0", className)}>
      <div className={cx("text-[0.98rem] font-medium", dark ? "text-white/75" : "text-ink-2")}>{label}</div>
      <span ref={countRef} className="mt-2 block font-display text-[2.6rem] leading-none tracking-[-0.025em] tabular-nums">
        {format(still ? value : 0)}
      </span>
      <div className={cx("mt-2.5 text-[0.93rem] xl:whitespace-nowrap", dark ? "text-white/70" : "text-ink-2")}>
        {has && <span className={cx("font-semibold tabular-nums", tone)}>{flat ? "flat" : `${up ? "+" : "−"}${Math.abs(change! * 100).toFixed(1)}%`}</span>}
        {note && <span>{has ? " " : ""}{note}</span>}
      </div>
      {series && series.length > 1 && (
        <Spark values={series} labels={seriesLabels} color={accent ?? (dark ? "#f4f4f1" : "#16181d")} format={format} dark={dark} />
      )}
    </div>
  );
}

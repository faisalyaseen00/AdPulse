import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Scatter, ScatterChart,
  Tooltip, XAxis, YAxis,
} from "recharts";
import { cell, date, friendly, isMoneyCol, money } from "@/lib/format";

const AX = { fontSize: 13, fill: "#4a4e56" };
const GRID = "#e6e6e1";

function Tip({ active, payload, label, fmtLabel }: {
  active?: boolean; payload?: { name: string; value: number; color: string; dataKey: string }[]; label?: string;
  fmtLabel?: (l: string) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-md border border-ink bg-surface px-3 py-2 text-sm">
      <div className="mb-1 font-medium">{fmtLabel ? fmtLabel(String(label)) : label}</div>
      {payload.map((p) => (
        <div key={p.dataKey} className="flex items-center gap-2 text-ink-2">
          <span className="size-2 rounded-full" style={{ background: p.color }} aria-hidden />
          <span className="text-muted">{p.name}</span>
          <span className="ml-auto pl-4 font-medium">{cell(p.dataKey, p.value)}</span>
        </div>
      ))}
    </div>
  );
}

/** Sales vs ad spend over time. Two series, one axis (both are dollars). */
export function SalesSpendChart({ data, xKey, height = 260, compact }: {
  data: { spend: number; revenue: number }[] & Record<string, unknown>[]; xKey: string; height?: number; compact?: boolean;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: compact ? 0 : 4 }}>
        <defs>
          <linearGradient id="rev" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#16181d" stopOpacity={0.07} />
            <stop offset="1" stopColor="#16181d" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke={GRID} vertical={false} />
        <XAxis dataKey={xKey} tick={AX} tickLine={false} axisLine={false} minTickGap={28}
          tickFormatter={(v) => date(v)} />
        <YAxis tick={AX} tickLine={false} axisLine={false} width={compact ? 44 : 56}
          tickFormatter={(v) => (v >= 1000 ? `$${+(v / 1000).toFixed(1)}k` : `$${v}`)} />
        <Tooltip content={<Tip fmtLabel={(l) => date(l, { month: "short", day: "numeric", year: "numeric" })} />} />
        <Area type="monotone" dataKey="revenue" name="Sales from ads" stroke="#16181d" strokeWidth={2} fill="url(#rev)" isAnimationActive={false} />
        <Area type="monotone" dataKey="spend" name="Ad spend" stroke="#d4920f" strokeWidth={2} fill="none" isAnimationActive={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

const SERIES = ["#16181d", "#d4920f", "#2e4a86", "#6b7a3a", "#b3261e", "#8b8f97"];

/** Chart for an assistant answer, following the chart spec the agent chose. */
export function AnswerChart({ type, x, y, color, rows }: {
  type: "bar" | "line" | "scatter"; x: string; y: string; color?: string; rows: Record<string, unknown>[];
}) {
  const yMoney = isMoneyCol(y);
  const yFmt = (v: number) => (yMoney ? money(v, Math.abs(v) < 100 ? 2 : 0) : cell(y, v));
  // colour column -> pivot so each group becomes its own series
  let data = rows;
  let keys = [y];
  if (color && rows.length && color in rows[0]) {
    const groups = [...new Set(rows.map((r) => String(r[color])))];
    if (groups.length <= SERIES.length) {
      const byX = new Map<string, Record<string, unknown>>();
      for (const r of rows) {
        const k = String(r[x]);
        const o = byX.get(k) ?? { [x]: r[x] };
        o[String(r[color])] = r[y];
        byX.set(k, o);
      }
      data = [...byX.values()];
      keys = groups;
    }
  }
  const isDate = typeof rows[0]?.[x] === "string" && /^\d{4}-\d{2}/.test(String(rows[0][x]));
  const xFmt = (v: unknown) => (isDate ? date(String(v), { month: "short", year: "2-digit" }) : String(v));
  const horizontal = type === "bar" && !isDate && data.length > 5;
  const common = { data, margin: { top: 8, right: 12, bottom: 0, left: 4 } };

  if (type === "scatter") {
    return (
      <ResponsiveContainer width="100%" height={320}>
        <ScatterChart {...common}>
          <CartesianGrid stroke={GRID} />
          <XAxis dataKey={x} name={friendly(x)} tick={AX} tickLine={false} />
          <YAxis dataKey={y} name={friendly(y)} tick={AX} tickLine={false} tickFormatter={yFmt} width={64} />
          <Tooltip />
          <Scatter data={rows} fill="#16181d" isAnimationActive={false} />
        </ScatterChart>
      </ResponsiveContainer>
    );
  }
  if (type === "line") {
    return (
      <ResponsiveContainer width="100%" height={320}>
        <LineChart {...common}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey={x} tick={AX} tickLine={false} axisLine={false} tickFormatter={xFmt} minTickGap={20} />
          <YAxis tick={AX} tickLine={false} axisLine={false} tickFormatter={yFmt} width={64} />
          <Tooltip content={<Tip fmtLabel={(l) => xFmt(l)} />} />
          {keys.map((k, i) => (
            <Line key={k} type="monotone" dataKey={k} name={keys.length > 1 ? cell("platform", k) : friendly(y)}
              stroke={SERIES[i % SERIES.length]} strokeWidth={2} dot={false} isAnimationActive={false} />
          ))}
        </LineChart>
      </ResponsiveContainer>
    );
  }
  return (
    <ResponsiveContainer width="100%" height={horizontal ? Math.max(240, data.length * 34) : 320}>
      <BarChart {...common} layout={horizontal ? "vertical" : "horizontal"}>
        <CartesianGrid stroke={GRID} horizontal={!horizontal} vertical={horizontal} />
        {horizontal ? (
          <>
            <XAxis type="number" tick={AX} tickLine={false} axisLine={false} tickFormatter={yFmt} />
            <YAxis type="category" dataKey={x} tick={AX} tickLine={false} axisLine={false} width={170} />
          </>
        ) : (
          <>
            <XAxis dataKey={x} tick={AX} tickLine={false} axisLine={false} tickFormatter={xFmt} />
            <YAxis tick={AX} tickLine={false} axisLine={false} tickFormatter={yFmt} width={64} />
          </>
        )}
        <Tooltip content={<Tip fmtLabel={(l) => xFmt(l)} />} cursor={{ fill: "#ecece7" }} />
        {keys.map((k, i) => (
          <Bar key={k} dataKey={k} name={keys.length > 1 ? cell("platform", k) : friendly(y)}
            fill={SERIES[i % SERIES.length]} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} maxBarSize={36} isAnimationActive={false} />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

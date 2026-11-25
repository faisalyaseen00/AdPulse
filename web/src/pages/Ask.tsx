import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Markdown from "react-markdown";
import { ArrowUp, Check, ChevronDown, X } from "lucide-react";
import { api, type Answer, type Health } from "@/lib/api";
import { cell, friendly, title } from "@/lib/format";
import { Badge, Button, Card, cx } from "@/components/ui";
import { AnswerChart } from "@/components/charts";

const EXAMPLES = [
  "Which ads brought in the most valuable customers last month?",
  "How much does it cost to win a new customer on Meta vs Google, month by month?",
  "Which ads are losing money right now?",
  "How much did we waste on Google searches that never led to a sale last month?",
];

// keep the conversation while moving between pages (lost on reload, like before)
let saved: Answer[] = [];

export default function Ask() {
  const { data: health } = useQuery({ queryKey: ["health"], queryFn: () => api.get<Health>("/health") });
  const [chat, setChat] = useState<Answer[]>(saved);
  const [text, setText] = useState("");
  const [pendingQ, setPendingQ] = useState<string | null>(null);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => { saved = chat; }, [chat]);

  const ask = useMutation({
    mutationFn: (question: string) => api.post<Answer>("/ask", {
      question,
      history: chat.filter((a) => a.ok).map((a) => ({ question: a.question, sql: a.sql, headline: a.headline })),
    }),
    onMutate: (q) => setPendingQ(q),
    onSuccess: (a) => setChat((c) => [...c, a]),
    onSettled: () => setPendingQ(null),
  });

  useEffect(() => { end.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [chat.length, pendingQ]);

  const send = (q: string) => {
    const s = q.trim();
    if (!s || ask.isPending) return;
    setText("");
    ask.mutate(s);
  };

  const empty = !chat.length && !pendingQ;
  const form = (
    <form
      className={cx("flex items-end gap-2 rounded-md border border-ink bg-surface p-2 focus-within:ring-2 focus-within:ring-ink/10", !empty && "sticky bottom-4 shadow-[0_12px_32px_-18px_rgb(22_24_29/0.5)]")}
      onSubmit={(e) => { e.preventDefault(); send(text); }}
    >
      <label htmlFor="q" className="sr-only">Your question</label>
      <textarea
        id="q"
        rows={empty ? 2 : 1}
        value={text}
        autoFocus
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(text); } }}
        placeholder="For example: which ads brought in the most valuable customers last month?"
        className="max-h-40 min-h-12 flex-1 resize-none bg-transparent px-4 py-3 text-[1.08rem] placeholder:text-faint focus:outline-none"
      />
      <Button kind="primary" type="submit" disabled={!text.trim()} loading={ask.isPending} className="h-11 px-6 disabled:bg-ink/80 disabled:opacity-100">
        Ask{!ask.isPending && <ArrowUp className="size-4" />}
      </Button>
    </form>
  );

  const steps = [
    ["Reads your data", "Ad, website and shop records. Read-only: it can look, never change."],
    ["Checks its logic", "A second step reviews the query before you see anything."],
    ["Verifies every number", "Each figure in the answer is matched to the actual results."],
  ];

  // ---- first visit: a centred, search-like page
  if (empty) {
    return (
      <article className="mx-auto max-w-[960px] pt-4 sm:pt-10">
        <header className="text-center">
          <h1 className="text-[clamp(2.6rem,5vw,4.4rem)] leading-[1.02]">What would you like to know?</h1>
          <p className="mx-auto mt-5 max-w-[58ch] text-[1.12rem] leading-relaxed text-ink-2">
            Ask about ads, customers, sales or wasted spend the way you would ask a colleague.
            Answers come from your own data, and every number is checked before you see it.
          </p>
        </header>

        {health && !health.ai && (
          <p className="mt-8 border-l-2 border-bad pl-4 text-[1rem] text-ink-2">
            The AI assistant is switched off. Add an AI key (for example GROQ_API_KEY) to the server settings and restart it.
          </p>
        )}

        <div className="mt-10">{form}</div>
        {ask.isError && <p className="mt-4 border-l-2 border-bad pl-4 text-bad">{(ask.error as Error).message}</p>}

        <section className="mt-12">
          <h2 className="text-[1.35rem]">Or start with one of these</h2>
          <div className="mt-4 grid gap-px overflow-hidden rounded-md border border-line bg-line sm:grid-cols-2">
            {EXAMPLES.map((e) => (
              <button key={e} onClick={() => send(e)}
                className="bg-surface px-5 py-5 text-left text-[1.02rem] leading-snug text-ink-2 transition-colors hover:bg-paper hover:text-ink">
                {e}
              </button>
            ))}
          </div>
        </section>

        <section className="mt-14 border-t border-ink pt-8">
          <h2 className="text-[1.35rem]">How each answer is checked</h2>
          <ol className="mt-6 grid gap-8 sm:grid-cols-3">
            {steps.map(([t, d], i) => (
              <li key={t}>
                <p className="font-display text-[2.2rem] leading-none text-faint">{String(i + 1).padStart(2, "0")}</p>
                <p className="mt-3 text-[1.05rem] font-semibold">{t}</p>
                <p className="mt-1 text-[0.98rem] leading-relaxed text-ink-2">{d}</p>
              </li>
            ))}
          </ol>
        </section>
      </article>
    );
  }

  // ---- in a conversation: answers on the left, reference rail on the right
  return (
    <article className="grid gap-x-16 gap-y-12 xl:grid-cols-[minmax(0,1fr)_340px]">
      <div className="min-w-0">
        <header className="flex flex-wrap items-end justify-between gap-4 border-b border-ink pb-6">
          <h1 className="text-[clamp(2rem,3.2vw,2.8rem)] leading-[1.05]">Your questions</h1>
          <Button onClick={() => setChat([])}>Start a new conversation</Button>
        </header>

        <div className="mt-10 grid gap-12">
          {chat.map((a) => <Exchange key={a.id} a={a} />)}
          {pendingQ && (
            <div className="grid gap-4">
              <Question text={pendingQ} />
              <div className="border-l-2 border-line pl-4">
                <p className="flex items-center gap-2.5 text-[1.02rem] text-ink-2">
                  <span className="relative flex size-2"><span className="absolute inline-flex size-full animate-ping rounded-full bg-saffron opacity-75" /><span className="relative inline-flex size-2 rounded-full bg-saffron" /></span>
                  Reading your data and checking the numbers
                </p>
                <p className="mt-1 text-[0.95rem] text-muted">This usually takes 10 to 30 seconds.</p>
              </div>
            </div>
          )}
          {ask.isError && <p className="border-l-2 border-bad pl-4 text-bad">{(ask.error as Error).message}</p>}
          <div ref={end} />
        </div>

        <div className="mt-8">{form}</div>
      </div>

      <aside className="xl:sticky xl:top-24 xl:self-start">
        <h2 className="border-b border-line pb-3 text-[1.25rem]">Ask a follow-up</h2>
        <ul className="divide-y divide-line">
          {EXAMPLES.map((e) => (
            <li key={e}>
              <button onClick={() => send(e)} disabled={ask.isPending}
                className="w-full py-3.5 text-left text-[0.98rem] leading-snug text-ink-2 transition-colors hover:text-ink disabled:opacity-50">
                {e}
              </button>
            </li>
          ))}
        </ul>
        <h2 className="mt-10 border-b border-line pb-3 text-[1.25rem]">How answers are checked</h2>
        <ol className="mt-4 grid gap-3">
          {steps.map(([t, d], i) => (
            <li key={t} className="grid grid-cols-[1.5rem_minmax(0,1fr)] gap-2 text-[0.95rem]">
              <span className="font-display text-faint">{i + 1}.</span>
              <p><span className="font-medium text-ink">{t}.</span> <span className="text-ink-2">{d}</span></p>
            </li>
          ))}
        </ol>
      </aside>
    </article>
  );
}

function Question({ text }: { text: string }) {
  return <p className="border-l-2 border-saffron pl-4 font-display text-[1.35rem] leading-snug text-ink">{text}</p>;
}

function Exchange({ a }: { a: Answer }) {
  const [view, setView] = useState<"chart" | "table">(a.chart && a.chart.type !== "none" && a.columns.includes(a.chart.x) && a.columns.includes(a.chart.y) ? "chart" : "table");
  const canChart = !!a.chart && a.chart.type !== "none" && a.columns.includes(a.chart.x) && a.columns.includes(a.chart.y);

  if (!a.ok) {
    return (
      <div className="grid gap-3">
        <Question text={a.question} />
        <Card>
          <p className="font-medium">I couldn't answer that one.</p>
          <p className="mt-1 text-[0.98rem] text-ink-2">Try asking it a different way, or ask about a specific ad, campaign or time period.</p>
          <Details a={a} />
        </Card>
      </div>
    );
  }

  const trust = a.verified
    ? <Badge tone="good">Every number matches your data</Badge>
    : a.numbers_checked && a.numbers_verified < a.numbers_checked
      ? <Badge tone="warn">{a.numbers_checked - a.numbers_verified} number(s) couldn't be matched: read with care</Badge>
      : <Badge tone="warn">Needs a second look</Badge>;

  const csv = () => {
    const rows = [a.columns.join(","), ...a.rows.map((r) => a.columns.map((c) => JSON.stringify(r[c] ?? "")).join(","))];
    const url = URL.createObjectURL(new Blob([rows.join("\n")], { type: "text/csv" }));
    Object.assign(document.createElement("a"), { href: url, download: `adpulse_${a.id}.csv` }).click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="grid gap-3">
      <Question text={a.question} />
      <Card>
        <div className="flex flex-wrap items-center gap-2">
          {trust}
          <span className="text-[0.92rem] text-ink-2">Answered in {Math.round(a.latency_ms / 1000)} seconds</span>
        </div>
        <h2 className="mt-3 text-xl font-semibold leading-snug tracking-[-0.01em]">{a.headline}</h2>
        <div className="prose-ap mt-2 text-[0.95rem] text-ink-2"><Markdown>{a.answer_markdown}</Markdown></div>
        {a.caveats.length > 0 && <p className="mt-4 border-l-2 border-line pl-3 text-[0.98rem] text-ink-2">{a.caveats.join(" ")}</p>}

        {a.rows.length > 0 && (
          <div className="mt-5 border-t border-line pt-4">
            <div className="mb-3 flex items-center justify-between gap-2">
              <div className="inline-flex rounded-lg border border-line-strong p-0.5 text-sm" role="tablist">
                {(["chart", "table"] as const).map((v) => (
                  <button key={v} role="tab" aria-selected={view === v} disabled={v === "chart" && !canChart} onClick={() => setView(v)}
                    className={cx("h-7 rounded-md px-3 disabled:opacity-40", view === v ? "bg-navy text-on-navy" : "text-ink-2 hover:bg-canvas")}>
                    {title(v)}
                  </button>
                ))}
              </div>
              <Button kind="ghost" onClick={csv}>CSV</Button>
            </div>
            {view === "chart" && canChart ? (
              <>
                {a.chart!.title && <p className="mb-2 text-sm font-medium text-ink-2">{a.chart!.title}</p>}
                <AnswerChart type={a.chart!.type as "bar" | "line" | "scatter"} x={a.chart!.x} y={a.chart!.y} color={a.chart!.color} rows={a.rows} />
              </>
            ) : (
              <div className="table-frame max-h-[440px]">
                <table className="data-table">
                  <thead className="sticky top-0">
                    <tr>{a.columns.map((c) => <th key={c} className={cx(typeof a.rows[0]?.[c] === "number" && "num")}>{friendly(c)}</th>)}</tr>
                  </thead>
                  <tbody>
                    {a.rows.map((r, i) => (
                      <tr key={i}>{a.columns.map((c) => <td key={c} className={cx(typeof r[c] === "number" && "num")}>{cell(c, r[c])}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}

        {a.suggested_actions.length > 0 && <Actions a={a} />}
        <Details a={a} />
      </Card>
    </div>
  );
}

function Actions({ a }: { a: Answer }) {
  const qc = useQueryClient();
  const [done, setDone] = useState<Record<number, string>>({});
  const add = useMutation({
    mutationFn: ({ s }: { s: Answer["suggested_actions"][number]; i: number }) =>
      api.post<{ added: number }>("/suggestions/from-answer", { ...s, question: a.question }),
    onSuccess: (r, { i }) => {
      setDone((d) => ({ ...d, [i]: r.added ? "Added" : "Already in your list" }));
      qc.invalidateQueries({ queryKey: ["suggestions"] });
      qc.invalidateQueries({ queryKey: ["health"] });
    },
  });
  const KIND = { pause_ad: ["Pause this ad", "bad"], scale_ad: ["Give it more budget", "good"], investigate: ["Worth a closer look", "info"] } as const;

  return (
    <div className="mt-5 border-t border-line pt-4">
      <p className="text-sm font-medium">Suggested next steps</p>
      <p className="mt-0.5 text-[0.95rem] text-ink-2">Adding one puts it in your suggestions list. Nothing changes until someone approves it.</p>
      <ul className="mt-3 grid gap-2">
        {a.suggested_actions.map((s, i) => (
          <li key={i} className="flex flex-wrap items-center gap-3 rounded-lg border border-line p-3">
            <Badge tone={KIND[s.action][1]}>{KIND[s.action][0]}</Badge>
            <span className="min-w-[200px] flex-1 text-sm"><b className="font-medium">{s.ad_name}</b> <span className="text-muted">on {title(s.platform)}: {s.rationale}</span></span>
            {s.action !== "investigate" && (
              done[i] ? <span className="text-sm text-good">{done[i]}</span> : (
                <Button onClick={() => add.mutate({ s, i })} loading={add.isPending && add.variables?.i === i}>Add to suggestions</Button>
              )
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function Details({ a }: { a: Answer }) {
  return (
    <details className="group mt-5 border-t border-line pt-3">
      <summary className="flex cursor-pointer list-none items-center gap-1 text-sm font-medium text-ink-2">
        <ChevronDown className="size-4 transition-transform group-open:rotate-180" aria-hidden />How this answer was worked out
      </summary>
      <div className="mt-3 grid gap-4 text-sm">
        {a.error && <p className="text-bad">{a.error}</p>}
        {a.reasoning && <p className="text-ink-2"><b className="font-medium">Approach.</b> {a.reasoning}</p>}
        {a.critic?.verdict === "fail" && <p className="text-warn">The review step still had concerns: {a.critic.issues.join("; ")}</p>}
        <div>
          <p className="font-medium">Number check</p>
          {a.number_checks.length ? (
            <ul className="mt-1 grid gap-1">
              {a.number_checks.map((c, i) => (
                <li key={i} className="flex items-center gap-2">
                  {c.verified ? <Check className="size-4 text-good" /> : <X className="size-4 text-bad" />}
                  <code className="rounded bg-canvas px-1.5">{c.text}</code>
                  <span className="text-muted">{c.verified ? `found in ${c.source}` : "not found in the results"}</span>
                </li>
              ))}
            </ul>
          ) : <p className="text-muted">The answer quotes no numbers.</p>}
        </div>
        {a.sql && (
          <div>
            <p className="font-medium">Database query</p><p className="text-ink-2">Read-only: it can look at your data, never change it.</p>
            <pre className="mt-1 overflow-x-auto rounded-lg bg-canvas p-3 text-xs leading-relaxed"><code>{a.sql}</code></pre>
          </div>
        )}
        {a.assumptions.length > 0 && <p className="text-muted">Assumptions: {a.assumptions.join(" ")}</p>}
        <ol className="grid gap-1">
          {a.steps.map((s, i) => (
            <li key={i} className="grid grid-cols-[16px_150px_1fr_auto] items-start gap-2">
              <span className={cx("mt-1.5 size-2 rounded-full", s.status === "ok" ? "bg-good" : s.status === "fail" ? "bg-bad" : s.status === "retry" ? "bg-saffron" : "bg-faint")} />
              <span className="font-medium">{s.name}</span>
              <span className="text-muted">{s.detail}</span>
              <span className="text-xs text-faint">{s.ms ? `${s.ms} ms` : ""}</span>
            </li>
          ))}
        </ol>
      </div>
    </details>
  );
}



"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  Activity, AlertTriangle, ArrowUpRight, Brain, Eraser, FlaskConical, IndianRupee,
  Landmark, Moon, Pencil, Phone, Play, Repeat, RotateCcw, ScrollText, ShieldAlert,
  ShieldCheck, Sun, Sunrise, Zap, type LucideIcon,
} from "lucide-react";
import { ClippedAreaChart } from "@/components/ui/clipped-area-chart";
import { TimelineAnimation } from "@/components/ui/timeline-animation";
import { connectWs, get, post, rupees, AuditRow, Failure, Metrics, QuietHours, WsEvent } from "@/lib/api";
import { cn } from "@/lib/utils";

interface TranscriptLine { failure_id: string; speaker: string; text: string; intent: string | null; ts: number }
interface SeriesPoint { t: number; cum_paise: number }

const hhmmss = (t: number) => new Date(t * 1000).toLocaleTimeString("en-IN", { hour12: false });
const hh = (h: number) => `${String(h).padStart(2, "0")}:00`;
const HOURS = Array.from({ length: 24 }, (_, i) => i);

const OUTCOME_STYLE: Record<string, string> = {
  PASSED: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
  BLOCKED: "bg-amber-500/15 text-amber-400 border-amber-500/30",
  HALTED: "bg-red-500/15 text-red-400 border-red-500/30",
  INFO: "bg-sky-500/15 text-sky-400 border-sky-500/30",
};

const INTENT_STYLE: Record<string, string> = {
  PRICE_OBJECTION: "bg-amber-500/20 text-amber-300",
  OPT_OUT: "bg-red-500/20 text-red-300",
  NO_FUNDS: "bg-sky-500/20 text-sky-300",
  AGREEMENT: "bg-emerald-500/20 text-emerald-300",
};

const STATUS_STYLE: Record<string, string> = {
  open: "text-zinc-400", recovering: "text-sky-400", recovered: "text-emerald-400",
  lost: "text-red-400", suppressed: "text-amber-400", queued: "text-indigo-400",
};

const YIELD_TARGET = 50; // % — the batch-proven recovery bar

export default function Dashboard() {
  const timelineRef = useRef<HTMLDivElement>(null);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [series, setSeries] = useState<SeriesPoint[]>([]);
  const [audit, setAudit] = useState<AuditRow[]>([]);
  const [brain, setBrain] = useState<AuditRow[]>([]);
  const [failures, setFailures] = useState<Failure[]>([]);
  const [transcript, setTranscript] = useState<TranscriptLine[]>([]);
  const [callLive, setCallLive] = useState(false);
  const [banksDown, setBanksDown] = useState<string[]>([]);
  const [batchBusy, setBatchBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const [sandboxOpen, setSandboxOpen] = useState(false);
  const [simBusy, setSimBusy] = useState<string | null>(null);
  const [quiet, setQuiet] = useState<QuietHours | null>(null);
  const [quietOpen, setQuietOpen] = useState(false);
  const [quietDraft, setQuietDraft] = useState({ start_h: 21, end_h: 9 });
  const [quietSaving, setQuietSaving] = useState(false);

  const loadSeries = () => get<SeriesPoint[]>("/api/recovery-series").then(setSeries).catch(() => {});

  useEffect(() => {
    get<Metrics>("/api/metrics").then(setMetrics).catch(() => {});
    loadSeries();
    get<AuditRow[]>("/api/audit?limit=60").then((rows) => {
      setAudit(rows.filter((r) => r.category !== "brain"));
      setBrain(rows.filter((r) => r.category === "brain").slice(0, 12));
    }).catch(() => {});
    get<Failure[]>("/api/failures?limit=30").then(setFailures).catch(() => {});
    get<{ down: string[] }>("/api/bank-health").then((b) => setBanksDown(b.down)).catch(() => {});
    get<QuietHours>("/api/quiet-hours").then(setQuiet).catch(() => {});

    const off = connectWs((e: WsEvent) => {
      setConnected(true);
      const d = e.data as never;
      if (e.type === "metrics") { setMetrics(d); loadSeries(); }
      if (e.type === "audit") {
        const row = d as AuditRow;
        if (row.category === "brain") setBrain((b) => [row, ...b].slice(0, 12));
        else setAudit((a) => [row, ...a].slice(0, 80));
      }
      if (e.type === "failure") setFailures((f) => [d as Failure, ...f].slice(0, 30));
      if (e.type === "failure_update") {
        const u = d as { id: string; status: string };
        setFailures((fs) => fs.map((f) => (f.id === u.id ? { ...f, status: u.status } : f)));
      }
      if (e.type === "transcript") setTranscript((t) => [...t, d as TranscriptLine].slice(-14));
      if (e.type === "call_started") { setCallLive(true); setTranscript([]); }
      if (e.type === "call_ended") setCallLive(false);
      if (e.type === "quiet_hours") setQuiet(d as QuietHours);
      if (e.type === "bank_health") {
        const b = d as { bank: string; status: string };
        setBanksDown((prev) => b.status === "down" ? [...new Set([...prev, b.bank])] : prev.filter((x) => x !== b.bank));
      }
    });
    return off;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const runBatch = async () => {
    setBatchBusy(true);
    try { await post("/simulate/batch", { n: 500, seed: 42 }); } finally { setBatchBusy(false); }
  };

  const sim = async (label: string, path: string, body?: Record<string, unknown>) => {
    setSimBusy(label);
    try { await post(path, body); } finally { setSimBusy(null); }
  };

  const SIMS: [LucideIcon, string, string, string, Record<string, unknown> | undefined][] = [
    [ShieldAlert, "Card-testing attack", "5 rapid failures — 5th gets suppressed", "/demo/fraud-burst", undefined],
    [Landmark, "HDFC outage", "6 issuer-down failures held — mark it up from the bank strip", "/demo/outage?bank=HDFC&n=6", undefined],
    [Moon, "Clock → 11 PM", "simulate TRAI quiet hours — calls queue", "/demo/clock", { hour: 23 }],
    [Sunrise, "Clock → 10 AM", "window opens — queued calls are placed", "/demo/clock", { hour: 10 }],
    [Sun, "Clock → real", "back to actual IST", "/demo/clock", { hour: null }],
  ];

  const openQuietEditor = () => {
    if (quiet) setQuietDraft({ start_h: quiet.start_h, end_h: quiet.end_h });
    setQuietOpen((o) => !o);
  };

  const saveQuiet = async (start_h: number, end_h: number) => {
    setQuietSaving(true);
    try {
      setQuiet(await post<QuietHours>("/api/quiet-hours", { start_h, end_h }));
      setQuietDraft({ start_h, end_h });
      setQuietOpen(false);
    } finally { setQuietSaving(false); }
  };

  const clearState = async () => {
    await post("/demo/reset");
    setFailures([]); setAudit([]); setBrain([]); setTranscript([]);
    setBanksDown([]); setCallLive(false); setSeries([]);
    get<QuietHours>("/api/quiet-hours").then(setQuiet).catch(() => {});  // reset restores the default window
  };

  const yieldPct = metrics?.yield_pct ?? 0;

  const kpis: { icon: LucideIcon; label: string; value: string; chip: string; up: boolean }[] = [
    { icon: IndianRupee, label: "Total Recovered", value: metrics ? rupees(metrics.recovered_paise) : "—", chip: metrics ? `${metrics.recovered_count} paid` : "…", up: true },
    { icon: Repeat, label: "MRR Saved", value: metrics ? `${rupees(metrics.mrr_saved_paise)}/mo` : "—", chip: metrics ? `${metrics.mrr_saved_count} subs` : "…", up: true },
    { icon: AlertTriangle, label: "₹ At Risk", value: metrics ? rupees(metrics.at_risk_paise) : "—", chip: "live", up: false },
    { icon: Activity, label: "Failures Seen", value: metrics ? String(metrics.failures_count) : "—", chip: "all time", up: false },
  ];

  return (
    <div ref={timelineRef} className="min-h-screen bg-zinc-950 text-zinc-100">
      <header className="sticky top-0 z-20 border-b border-zinc-800 bg-zinc-950/85 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl border border-emerald-500/30 bg-emerald-500/10 text-emerald-400">
              <ShieldCheck className="h-5 w-5" aria-hidden />
            </span>
            <div>
              <div className="text-lg font-extrabold leading-tight tracking-tight">Revive Command Center</div>
              <div className="text-[10px] text-zinc-500">AI Revenue Recovery · Tomato merchant account</div>
            </div>
          </div>
          <div className="flex items-center gap-2 text-xs">
            <span className={cn("mr-1 flex items-center gap-1.5 font-semibold", connected ? "text-emerald-400" : "text-zinc-500")}>
              <span className={cn("h-2 w-2 rounded-full", connected ? "animate-pulse bg-emerald-400" : "bg-zinc-600")} />
              {connected ? "LIVE" : "connecting…"}
            </span>
            <button onClick={runBatch} disabled={batchBusy}
              className="flex cursor-pointer items-center gap-1.5 rounded-xl bg-violet-600 px-3 py-1.5 font-bold text-white transition-colors duration-200 hover:bg-violet-500 disabled:opacity-50">
              <Play className="h-3.5 w-3.5" aria-hidden />
              {batchBusy ? "Running batch…" : "Run 500-Record Batch"}
            </button>
            <button onClick={() => setSandboxOpen((o) => !o)}
              className={cn("flex cursor-pointer items-center gap-1.5 rounded-xl border px-3 py-1.5 font-bold transition-colors duration-200",
                sandboxOpen
                  ? "border-amber-500 bg-amber-500 text-white"
                  : "border-zinc-700 bg-zinc-900 hover:border-zinc-500 hover:bg-zinc-800")}>
              <FlaskConical className="h-3.5 w-3.5" aria-hidden />
              Sandbox
            </button>
            <button onClick={clearState} title="wipe all demo state for a fresh run"
              className="flex cursor-pointer items-center gap-1.5 rounded-xl border border-zinc-700 bg-zinc-900 px-3 py-1.5 font-bold transition-colors duration-200 hover:border-zinc-500 hover:bg-zinc-800">
              <Eraser className="h-3.5 w-3.5" aria-hidden />
              Clear state
            </button>
            <Link href="/"
              className="group hidden cursor-pointer items-center gap-x-1 rounded-xl border border-zinc-700 bg-zinc-900 px-3 py-1.5 font-bold transition-colors duration-200 hover:border-zinc-500 hover:bg-zinc-800 sm:flex">
              storefront
              <span className="relative flex h-4 w-4 items-center justify-center overflow-hidden">
                <ArrowUpRight className="absolute h-3.5 w-3.5 transition-all duration-500 group-hover:-translate-y-4 group-hover:translate-x-4" aria-hidden />
                <ArrowUpRight className="absolute h-3.5 w-3.5 -translate-x-4 translate-y-4 transition-all duration-500 group-hover:translate-x-0 group-hover:translate-y-0" aria-hidden />
              </span>
            </Link>
          </div>
        </div>
        {sandboxOpen && (
          <div className="border-t border-zinc-800 bg-zinc-900">
            <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 px-4 py-2.5">
              <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                Test-mode event simulator — system events a single checkout can&apos;t produce
              </span>
              {SIMS.map(([Icon, label, hint, path, body]) => (
                <button key={label} onClick={() => sim(label, path, body)} disabled={simBusy !== null} title={hint}
                  className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1 text-xs font-bold transition-colors duration-200 hover:border-zinc-500 disabled:opacity-50">
                  <Icon className="h-3.5 w-3.5" aria-hidden />
                  {simBusy === label ? "…" : label}
                </button>
              ))}
            </div>

            <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-2 border-t border-zinc-800/70 px-4 py-2.5">
              <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">
                Guardrail policy
              </span>
              <button onClick={openQuietEditor}
                title="edit the TRAI quiet-hours window — outbound calls inside it are queued, never placed"
                className={cn("flex cursor-pointer items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs font-bold transition-colors duration-200",
                  quietOpen
                    ? "border-amber-500 bg-amber-500 text-white"
                    : quiet?.in_quiet
                      ? "border-amber-500/50 bg-amber-500/10 text-amber-300 hover:border-amber-400"
                      : "border-zinc-700 bg-zinc-950 hover:border-zinc-500")}>
                <Moon className="h-3.5 w-3.5" aria-hidden />
                TRAI quiet hours {quiet ? `${hh(quiet.start_h)}–${hh(quiet.end_h)}` : "…"}
                <Pencil className="h-3 w-3 opacity-70" aria-hidden />
              </button>
              {quiet && (
                <span className="font-mono text-[10px] text-zinc-500">
                  now {hh(quiet.hour_ist)} IST ·{" "}
                  {quiet.in_quiet ? "inside window — calls queue" : "outside window — calls place"}
                </span>
              )}
            </div>

            {quietOpen && (
              <div className="mx-auto flex max-w-6xl flex-wrap items-end gap-3 border-t border-zinc-800/70 px-4 py-3">
                <HourSelect label="Quiet from" value={quietDraft.start_h}
                  onChange={(v) => setQuietDraft((q) => ({ ...q, start_h: v }))} />
                <HourSelect label="Quiet until" value={quietDraft.end_h}
                  onChange={(v) => setQuietDraft((q) => ({ ...q, end_h: v }))} />
                <button onClick={() => saveQuiet(quietDraft.start_h, quietDraft.end_h)} disabled={quietSaving}
                  className="cursor-pointer rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-bold text-white transition-colors duration-200 hover:bg-emerald-500 disabled:opacity-50">
                  {quietSaving ? "Saving…" : "Save window"}
                </button>
                {quiet && (
                  <button onClick={() => saveQuiet(quiet.default_start_h, quiet.default_end_h)} disabled={quietSaving}
                    title="back to the TRAI default"
                    className="flex cursor-pointer items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-xs font-bold transition-colors duration-200 hover:border-zinc-500 disabled:opacity-50">
                    <RotateCcw className="h-3.5 w-3.5" aria-hidden />
                    Default {hh(quiet.default_start_h)}–{hh(quiet.default_end_h)}
                  </button>
                )}
                <button onClick={() => setQuietOpen(false)}
                  className="cursor-pointer rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-xs font-bold text-zinc-400 transition-colors duration-200 hover:border-zinc-500 hover:text-zinc-200">
                  Cancel
                </button>
                <p className="basis-full text-[10px] leading-relaxed text-zinc-500">
                  Voice calls landing inside this window are queued until {hh(quietDraft.end_h)} IST — never placed.
                  Same hour on both sides switches quiet hours off entirely. Every change lands in the audit log.
                </p>
              </div>
            )}
          </div>
        )}
      </header>

      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6">
        {/* ── advanced-stats block ─────────────────────────────── */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* main chart */}
          <TimelineAnimation animationNum={1} timelineRef={timelineRef}
            className="rounded-3xl border border-zinc-800 bg-zinc-900 p-8 lg:col-span-2">
            <div className="mb-4 flex items-end justify-between">
              <div>
                <p className="mb-1 text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-500">
                  Cumulative recovery
                </p>
                <h4 className="text-3xl font-black tracking-tighter">
                  {metrics ? rupees(metrics.recovered_paise) : "—"}
                  <span className="ml-2 text-sm font-medium text-zinc-500">recovered to date</span>
                </h4>
              </div>
              <span className="text-xs font-medium text-zinc-500">{series.length} recoveries</span>
            </div>
            <ClippedAreaChart
              data={series.map((s) => s.cum_paise)}
              emptyText="No recoveries yet — run the batch or complete a recovery link."
            />
          </TimelineAnimation>

          {/* breakdown column */}
          <div className="flex flex-col gap-4">
            <TimelineAnimation animationNum={2} timelineRef={timelineRef}
              className="flex h-full flex-col justify-between rounded-3xl bg-white p-6 text-zinc-900 shadow-lg">
              <div>
                <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.2em] text-zinc-400">
                  Primary Goal
                </p>
                <h4 className="text-xl font-bold tracking-tight">Recovery Yield</h4>
              </div>
              <div className="mt-8">
                <div className="mb-2 flex items-end justify-between">
                  <span className="text-3xl font-semibold tracking-tighter">{yieldPct}%</span>
                  <span className="mb-1 text-xs font-medium text-zinc-500">Target: {YIELD_TARGET}%</span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-zinc-200">
                  <div className="h-full rounded-full bg-zinc-900 transition-all duration-700"
                    style={{ width: `${Math.min(100, (yieldPct / YIELD_TARGET) * 100)}%` }} />
                </div>
              </div>
            </TimelineAnimation>

            <TimelineAnimation animationNum={3} timelineRef={timelineRef}
              className="h-full rounded-3xl border border-zinc-800 bg-zinc-900 p-6">
              <div className="mb-4 flex items-center gap-3">
                <div className="flex size-8 items-center justify-center rounded-lg border border-zinc-700 bg-zinc-950">
                  <ShieldCheck className="h-5 w-5 text-zinc-100" aria-hidden />
                </div>
                <h4 className="font-bold text-zinc-100">Bounded Autonomy</h4>
              </div>
              <p className="text-sm text-zinc-400">
                Every action passes{" "}
                <span className="font-semibold text-zinc-100">5 server-side guardrails</span>{" "}
                before it executes — full audit trail below.
              </p>
            </TimelineAnimation>
          </div>
        </div>

        {/* KPI row */}
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          {kpis.map((kpi, index) => (
            <TimelineAnimation animationNum={4 + index} timelineRef={timelineRef} key={kpi.label}
              className={cn(
                "rounded-2xl border border-zinc-800 bg-zinc-900 p-6 transition-colors",
                kpi.up ? "hover:border-emerald-500/60 hover:bg-emerald-500/10" : "hover:border-rose-500/60 hover:bg-rose-500/10"
              )}>
              <p className="mb-2 text-xs font-bold uppercase tracking-widest text-zinc-500">{kpi.label}</p>
              <div className="flex items-baseline justify-between">
                <p className="text-2xl font-black tracking-tighter text-zinc-100">{kpi.value}</p>
                <span className={cn("rounded px-1.5 py-0.5 text-xs font-bold",
                  kpi.up ? "bg-emerald-500/10 text-emerald-400" : "bg-rose-500/10 text-rose-400")}>
                  {kpi.chip}
                </span>
              </div>
            </TimelineAnimation>
          ))}
        </div>

        {/* bank health */}
        <div className="flex flex-wrap items-center gap-2 rounded-2xl border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-xs">
          <span className="flex items-center gap-1.5 font-bold text-zinc-500">
            <Landmark className="h-3.5 w-3.5" aria-hidden /> Bank health:
          </span>
          {[...new Set(["HDFC", "ICICI", "SBI", "AXIS", "KOTAK", ...banksDown])].map((b) =>
            banksDown.includes(b) ? (
              <button key={b} onClick={() => post(`/demo/outage-recover?bank=${b}`)}
                title="mark bank up — releases held failures and sends each customer a UPI recovery link"
                className="animate-pulse cursor-pointer rounded-full border border-red-500/40 bg-red-500/10 px-2.5 py-0.5 font-mono font-bold text-red-400 transition-colors hover:animate-none hover:border-emerald-500/50 hover:bg-emerald-500/10 hover:text-emerald-400">
                {b} ▼ DOWN · click: bank up
              </button>
            ) : (
              <span key={b} className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-0.5 font-mono font-bold text-emerald-400">
                {b} ▲
              </span>
            )
          )}
        </div>

        {/* live panels */}
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="space-y-4">
            <Panel icon={Phone} title={`Live Call ${callLive ? "· IN PROGRESS" : ""}`} pulse={callLive}>
              {transcript.length === 0 ? (
                <Empty>No active call. Fail a payment on the storefront and Asha will ring.</Empty>
              ) : (
                <div className="space-y-2">
                  {transcript.map((t, i) => (
                    <div key={i} className={cn("flex", t.speaker === "agent" ? "justify-start" : "justify-end")}>
                      <div className={cn("max-w-[85%] rounded-2xl px-3 py-2 text-xs leading-relaxed",
                        t.speaker === "agent" ? "bg-emerald-500/10 text-emerald-100" : "bg-zinc-800 text-zinc-200")}>
                        <span className="mb-0.5 block text-[9px] font-bold uppercase opacity-60">
                          {t.speaker === "agent" ? "Asha (AI)" : "Customer"} · {hhmmss(t.ts)}
                        </span>
                        {t.text}
                        {t.intent && (
                          <span className={cn("ml-2 rounded-full px-2 py-0.5 text-[9px] font-bold", INTENT_STYLE[t.intent] || "")}>
                            {t.intent}
                          </span>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </Panel>

            <Panel icon={Zap} title="Failure Stream">
              {failures.length === 0 ? <Empty>Waiting for failures…</Empty> : (
                <div className="space-y-1.5">
                  {failures.slice(0, 8).map((f) => (
                    <div key={f.id} className="flex items-center justify-between rounded-lg bg-zinc-800/60 px-3 py-2 text-xs">
                      <div>
                        <div className="font-bold">{f.customer_name} · {rupees(f.amount)}</div>
                        <div className="font-mono text-[10px] text-zinc-500">{f.error_code} · {f.bank}</div>
                      </div>
                      <span className={cn("font-mono text-[10px] font-bold uppercase", STATUS_STYLE[f.status] || "")}>{f.status}</span>
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>

          <Panel icon={Brain} title="Agent Brain — live reasoning" onClear={brain.length ? () => setBrain([]) : undefined}>
            {brain.length === 0 ? <Empty>Decisions will appear here.</Empty> : (
              <div className="space-y-2">
                {brain.map((b) => (
                  <div key={b.id} className="rounded-lg border-l-2 border-sky-500/60 bg-zinc-800/50 px-3 py-2 text-xs leading-relaxed text-zinc-300">
                    <div className="mb-0.5 font-mono text-[9px] text-zinc-500">{hhmmss(b.created_at)}</div>
                    {b.message}
                  </div>
                ))}
              </div>
            )}
          </Panel>

          <Panel icon={ScrollText} title="Audit Log — every action, every check" onClear={audit.length ? () => setAudit([]) : undefined}>
            {audit.length === 0 ? <Empty>Audit trail will stream here.</Empty> : (
              <div className="space-y-1.5">
                {audit.slice(0, 20).map((a) => (
                  <div key={a.id} className="rounded-lg bg-zinc-800/50 px-3 py-1.5 text-[11px] leading-snug">
                    <div className="flex items-center gap-2">
                      <span className={cn("rounded border px-1.5 py-px font-mono text-[9px] font-bold", OUTCOME_STYLE[a.outcome] || OUTCOME_STYLE.INFO)}>
                        {a.outcome}
                      </span>
                      {a.rule && <span className="font-mono text-[9px] text-zinc-500">{a.rule}</span>}
                      <span className="ml-auto font-mono text-[9px] text-zinc-500">{hhmmss(a.created_at)}</span>
                    </div>
                    <div className="mt-0.5 text-zinc-300">{a.message}</div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </div>
      </main>
    </div>
  );
}

function Panel({ icon: Icon, title, children, pulse, onClear }: {
  icon: LucideIcon; title: string; children: React.ReactNode; pulse?: boolean; onClear?: () => void;
}) {
  return (
    <div className={cn("rounded-3xl border bg-zinc-900 p-4",
      pulse ? "border-emerald-500/50 shadow-[0_0_24px_rgba(16,185,129,0.15)]" : "border-zinc-800")}>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="flex items-center gap-1.5 text-xs font-extrabold uppercase tracking-wider text-zinc-400">
          <Icon className={cn("h-3.5 w-3.5", pulse && "animate-pulse text-emerald-400")} aria-hidden />
          {title}
        </h2>
        {onClear && (
          <button onClick={onClear}
            className="cursor-pointer rounded border border-zinc-700 px-2 py-0.5 text-[10px] font-bold text-zinc-400 transition-colors duration-200 hover:border-zinc-500 hover:text-zinc-200">
            clear
          </button>
        )}
      </div>
      <div className="max-h-[420px] overflow-y-auto pr-1">{children}</div>
    </div>
  );
}

function HourSelect({ label, value, onChange }: {
  label: string; value: number; onChange: (v: number) => void;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[10px] font-bold uppercase tracking-wider text-zinc-500">{label}</span>
      <select value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="cursor-pointer rounded-lg border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 font-mono text-xs font-bold text-zinc-100 transition-colors duration-200 hover:border-zinc-500 focus:border-amber-500 focus:outline-none">
        {HOURS.map((h) => <option key={h} value={h}>{hh(h)} IST</option>)}
      </select>
    </label>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <div className="py-8 text-center text-xs text-zinc-600">{children}</div>;
}

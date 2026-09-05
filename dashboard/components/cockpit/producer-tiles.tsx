"use client";

import * as React from "react";
import { AnimatePresence, motion } from "motion/react";
import {
  ClipboardCheck,
  Mic,
  FileText,
  Calendar as CalendarIcon,
  Dumbbell,
  Ghost,
  BookOpen,
  Radar,
  ShieldCheck,
  ListChecks,
  Bot,
  Target,
  type LucideIcon,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { MagicCard } from "@/components/ui/magic-card";
import { BlurFade } from "@/components/ui/blur-fade";
import { AnimatedCircularProgressBar } from "@/components/ui/animated-circular-progress-bar";
import type { CockpitPayload } from "@/lib/cockpit-data";

/* ---------- verdict → colour ---------- */

type Verdict = "green" | "amber" | "red" | "neutral" | "off";

/** Maps a raw verdict string to a colour bucket. Returns null when the string
 *  doesn't map to a known verdict (missing, "off", or an unrecognised word) --
 *  callers then fall back to the section's `ok`/`say` presence via sectionVerdict. */
function normVerdict(v: unknown): Verdict | null {
  const s = String(v ?? "").toLowerCase().trim();
  if (s === "green" || s === "ok" || s === "pass") return "green";
  if (s === "amber" || s === "yellow" || s === "warn" || s === "degraded") return "amber";
  if (s === "red" || s === "fail" || s === "broken") return "red";
  return null;
}

/** Section-aware verdict: a producer that reports ok===true with a populated
 *  `say` line is NOT "no data" just because it didn't emit a green/amber/red
 *  verdict word (several producers emit verdict:"off" as their own neutral
 *  state, e.g. standup/shadow/watchers) -- that renders as a neutral "OK" chip.
 *  Only a genuinely missing/empty section, or ok===false with nothing to show,
 *  is "NO DATA". */
function sectionVerdict(section: Record<string, unknown> | undefined, raw: unknown): Verdict {
  if (!section) return "off";
  const mapped = normVerdict(raw);
  if (mapped) return mapped;
  if (section["ok"] === true) return "neutral";
  if (typeof section["say"] === "string" && section["say"]) return "neutral";
  return "off";
}

function verdictLabel(v: Verdict): string {
  switch (v) {
    case "green":
      return "GREEN";
    case "amber":
      return "AMBER";
    case "red":
      return "RED";
    case "neutral":
      return "OK";
    default:
      return "NO DATA";
  }
}

function verdictColor(v: Verdict): string {
  switch (v) {
    case "green":
      return "var(--gc-good)";
    case "amber":
      return "var(--gc-warn)";
    case "red":
      return "var(--gc-bad)";
    case "neutral":
      return "var(--gc-text-2)";
    default:
      return "var(--gc-text-3)";
  }
}

/** US Eastern DST window for a given year: 2nd Sunday of March through the
 *  1st Sunday of November (the actual 2am transition instant is not worth
 *  modelling for a dashboard "N ago" label -- day-granularity is enough). */
function nthSundayUtcMs(year: number, month1to12: number, n: number): number {
  const d = new Date(Date.UTC(year, month1to12 - 1, 1));
  let count = 0;
  while (true) {
    if (d.getUTCDay() === 0) {
      count += 1;
      if (count === n) return d.getTime();
    }
    d.setUTCDate(d.getUTCDate() + 1);
  }
}

/** Parses a zone-less "YYYY-MM-DD[ T]HH:MM[:SS]" stamp as America/New_York
 *  wall-clock time and returns the UTC epoch ms. Stamps that already carry a
 *  zone (Z or +/-HH:MM) are parsed directly. Returns null if unparseable. */
function parseEtStampEpoch(raw: string): number | null {
  const s = raw.trim();
  if (/[zZ]$|[+-]\d{2}:?\d{2}$/.test(s)) {
    const t = Date.parse(s);
    return Number.isNaN(t) ? null : t;
  }
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/);
  if (!m) return null;
  const [, y, mo, d, h, mi, se] = m;
  const year = Number(y);
  const wallUtcGuess = Date.UTC(year, Number(mo) - 1, Number(d), Number(h), Number(mi), se ? Number(se) : 0);
  const dstStart = nthSundayUtcMs(year, 3, 2);
  const dstEnd = nthSundayUtcMs(year, 11, 1);
  const isDst = wallUtcGuess >= dstStart && wallUtcGuess < dstEnd;
  return wallUtcGuess + (isDst ? 4 : 5) * 3_600_000;
}

/** Freshness label. `stamp_et` (parsed as ET, DST-aware) is the primary
 *  source -- verified against this live payload, `fresh_h` is unreliable
 *  (returned 24 for almost every section and 6 for a section whose stamp was
 *  3 minutes old), so it is only a last-resort fallback when stamp_et is
 *  missing or unparseable. Never silently prints a wrong "24 h ago". */
function freshLabel(section: Record<string, unknown> | undefined): string {
  if (!section) return "NO DATA";
  const stamp = section["stamp_et"];
  if (typeof stamp === "string" && stamp) {
    const epoch = parseEtStampEpoch(stamp);
    if (epoch != null) {
      const diffMs = Math.max(0, Date.now() - epoch);
      const mins = diffMs / 60_000;
      if (mins < 60) return `${Math.max(1, Math.round(mins))} min ago`;
      const hrs = diffMs / 3_600_000;
      return `${hrs < 10 ? hrs.toFixed(1) : Math.round(hrs)} h ago`;
    }
  }
  const h = section["fresh_h"];
  if (typeof h === "number") {
    return h < 1 ? `${Math.round(h * 60)} min ago` : `${h} h ago`;
  }
  return "NO DATA";
}

function say(section: Record<string, unknown> | undefined, fallback = "NO DATA"): string {
  if (!section) return fallback;
  const s = section["say"];
  return typeof s === "string" && s ? s : fallback;
}

/* ---------- small inline graphics ---------- */

function ChecksBar({ n, red }: { n: number; red: number }) {
  const ok = Math.max(0, n - red);
  const total = Math.max(1, n);
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-[var(--gc-line)]">
      <div className="h-full" style={{ width: `${(ok / total) * 100}%`, background: "var(--gc-good)" }} />
      {red > 0 && <div className="h-full" style={{ width: `${(red / total) * 100}%`, background: "var(--gc-bad)" }} />}
    </div>
  );
}

function Sparkline({ values, color }: { values: number[]; color: string }) {
  if (!values.length) return null;
  const w = 120, h = 28;
  const max = Math.max(...values, 1), min = Math.min(...values, 0);
  const range = Math.max(1, max - min);
  const step = w / Math.max(1, values.length - 1);
  const pts = values.map((v, i) => `${i * step},${h - ((v - min) / range) * h}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} width="100%" height={h} preserveAspectRatio="none">
      <polyline points={pts} fill="none" stroke={color} strokeWidth={1.5} />
    </svg>
  );
}

function HeatStrip({ cells }: { cells: { value: number; label?: string }[] }) {
  if (!cells.length) return null;
  const max = Math.max(...cells.map((c) => Math.abs(c.value)), 1);
  return (
    <div className="flex gap-[2px]">
      {cells.map((c, i) => (
        <div
          key={i}
          title={c.label}
          className="h-3 flex-1 rounded-[2px]"
          style={{ background: c.value >= 0 ? "var(--gc-good)" : "var(--gc-bad)", opacity: 0.25 + Math.min(1, Math.abs(c.value) / max) * 0.75 }}
        />
      ))}
    </div>
  );
}

function Dayline({ items }: { items: { label: string; fired_today?: boolean; failed_today?: boolean }[] }) {
  if (!items.length) return null;
  return (
    <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5">
      {items.slice(0, 8).map((it, i) => {
        const color = it.failed_today ? "var(--gc-bad)" : it.fired_today ? "var(--gc-good)" : "var(--gc-text-3)";
        return (
          <span
            key={i}
            title={it.label}
            className="inline-block h-2 w-2 shrink-0 rounded-full"
            style={{ background: color, boxShadow: `0 0 4px ${color}` }}
          />
        );
      })}
    </div>
  );
}

/* ---------- Tile ---------- */

export type TileSpec = {
  key: string;
  icon: LucideIcon;
  title: string;
  verdict: Verdict;
  summary: string;
  freshness: string;
  graphic?: React.ReactNode;
  detail?: React.ReactNode;
};

/* ---------- expandable tile: click expands in place (motion height) ---------- */

export function Tile({ spec }: { spec: TileSpec }) {
  const [expanded, setExpanded] = React.useState(false);
  const Icon = spec.icon;
  const color = verdictColor(spec.verdict);

  return (
    <MagicCard
      className="rounded-xl border border-[var(--gc-line)] bg-[var(--gc-panel)] p-0"
      gradientColor="var(--gc-panel-solid)"
      gradientFrom="var(--gc-indigo)"
      gradientTo="var(--gc-cyan)"
    >
      <button
        type="button"
        onClick={() => setExpanded((e) => !e)}
        className="flex w-full flex-col gap-2.5 rounded-xl p-3.5 text-left"
      >
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="gc-icon-tile flex h-8 w-8 shrink-0 items-center justify-center rounded-lg">
              <Icon className="h-4 w-4" style={{ color: "var(--gc-cyan)" }} />
            </span>
            <span className="truncate text-[13px] font-medium text-[var(--gc-text)]">
              {spec.title}
            </span>
          </div>
          <Badge
            variant="outline"
            className="shrink-0 border-[var(--gc-line-strong)] px-1.5 text-[10px] font-semibold"
            style={{ color }}
          >
            {verdictLabel(spec.verdict)}
          </Badge>
        </div>
        <p className="line-clamp-2 min-h-[2.2em] text-[12px] leading-snug text-[var(--gc-text-2)]">
          {spec.summary}
        </p>
        {spec.graphic && <div className="pt-0.5">{spec.graphic}</div>}
        <div className="text-[10px] text-[var(--gc-text-3)]">{spec.freshness}</div>
      </button>
      <AnimatePresence initial={false}>
        {expanded && spec.detail && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden border-t border-[var(--gc-line)]"
          >
            <div className="p-3.5">{spec.detail}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </MagicCard>
  );
}

/* ---------- group heading ---------- */

function GroupHeading({ children, id }: { children: React.ReactNode; id?: string }) {
  return (
    <div id={id} className="mb-2 scroll-mt-6 text-[13px] font-semibold uppercase tracking-wider text-[var(--gc-text-3)]">
      {children}
    </div>
  );
}

function DetailList({ items }: { items: string[] }) {
  if (!items.length) return <div className="text-[12px] text-[var(--gc-text-3)]">NO DATA</div>;
  return (
    <ul className="flex flex-col gap-1.5">
      {items.map((it, i) => (
        <li key={i} className="text-[12px] leading-snug text-[var(--gc-text-2)]">
          • {it}
        </li>
      ))}
    </ul>
  );
}

/* ---------- section builders ---------- */

function s(data: CockpitPayload, key: string): Record<string, unknown> | undefined {
  const v = data?.[key];
  return v && typeof v === "object" ? (v as Record<string, unknown>) : undefined;
}

export function ProducerTiles({ data }: { data: CockpitPayload }) {
  const prep = s(data, "prep");
  const standup = s(data, "standup");
  const eod = s(data, "eod");
  const calendar = s(data, "calendar");
  const gym = s(data, "gym");
  const shadow = s(data, "shadow");
  const learning = s(data, "learning");
  const watchers = s(data, "watchers");
  const guards = s(data, "guards");
  const tasks = s(data, "tasks");
  const righttail = s(data, "righttail");
  const autonomy = s(data, "autonomy");
  const goal = s(data, "goal");

  // Kitchen OP-32 trust gate (I4, GOAL-KITCHEN-INTEGRITY-2026-09-05): rendered on the
  // Autopilot tile per that goal's DONE-WHEN (c) -- autonomy.engines.kitchen.provenance,
  // written by gamma_autonomy.py from free_model_audit.py's bar-state file.
  const kitchenProvenance = ((autonomy?.engines as Record<string, unknown>)?.kitchen as Record<string, unknown>)
    ?.provenance as Record<string, unknown> | undefined;
  const kitchenTrustGate = (kitchenProvenance?.trust_gate as string | undefined) ?? undefined;
  const kitchenFabRate = (kitchenProvenance?.fabricated_artifact_rate as number | undefined) ?? undefined;
  const kitchenProvMissing = kitchenProvenance?.provenance_missing as number | undefined;
  const kitchenFilesScored = kitchenProvenance?.files_scored as number | undefined;

  // Checkpoint packet (GOAL-CHECKPOINT-PACKET-2026-09-29 C5): verdict counts written
  // by checkpoint_packet.py -> gamma_autonomy.py's checkpoint_packet block. Rendered
  // on the same Autopilot tile with a link to the GENERATED markdown file -- never
  // re-derived here, this is a pure display of the packet's own numbers.
  const checkpointPacket = autonomy?.checkpoint_packet as Record<string, unknown> | undefined;

  // Small local aliases keep the tile arrays below to one line of JSX-glue each.
  const ring = (value: number, color: string) => (
    <div className="flex justify-start">
      <AnimatedCircularProgressBar max={100} min={0} value={value} gaugePrimaryColor={color} gaugeSecondaryColor="var(--gc-line)" className="h-12 w-12 text-[10px]" />
    </div>
  );
  const checks = (prep?.checks as { name?: string; status?: string; detail?: string }[]) || [];
  const audits = (gym?.audits as { name?: string; verdict?: string; summary?: string }[]) || [];
  const shadowLive = (shadow?.live as { name?: string; verdict?: string }[]) || [];
  const watcherRows = (watchers?.watchers as { name?: string; observations?: number; would_be_pnl?: number }[]) || [];
  const guardProblems = (guards?.problems as { name?: string; note?: string }[]) || [];
  const righttailPerArm = (righttail?.per_arm as Record<string, { n_waves?: number; n_taken?: number; capture_rate?: number | null }>) || {};
  const taskLanes = (tasks?.lanes as { lane?: string; worst?: string; tasks?: { name?: string; state?: string }[] }[]) || [];
  const dayline = taskLanes.flatMap((l) => (l.tasks || []).map((t) => ({ label: t.name || "", fired_today: t.state === "Ready" })));
  const doneWhen = (goal?.done_when as string[]) || [];
  const goalProgress = (goal?.progress_log as unknown[]) || [];
  const goalPct = doneWhen.length ? Math.min(100, Math.round((goalProgress.length / doneWhen.length) * 100)) : 0;
  const winToday = (learning?.windows as Record<string, Record<string, number>>)?.today;
  const win7d = (learning?.windows as Record<string, Record<string, number>>)?.["7d"];
  const latestVerdicts = (learning?.latest_verdicts as { at_et?: string; kind?: string; subject?: string; text?: string }[]) || [];

  // calendar.views is keyed by roster (safe-2/bold-2/.../BOOK); BOOK is the
  // book-wide daily net P&L series -- that's the day-level series to strip.
  const calendarViews = calendar?.["views"] as Record<string, { days?: Record<string, { g?: number; n?: number; t?: number }> }> | undefined;
  const bookDays = calendarViews?.["BOOK"]?.days;
  const bookDayEntries = bookDays
    ? Object.entries(bookDays).sort(([a], [b]) => a.localeCompare(b)).slice(-30)
    : [];

  const tradingTiles: TileSpec[] = [
    { key: "prep", icon: ClipboardCheck, title: "Premarket prep", verdict: sectionVerdict(prep, prep?.verdict), summary: say(prep), freshness: freshLabel(prep),
      graphic: <ChecksBar n={typeof prep?.n_checks === "number" ? prep.n_checks : 0} red={typeof prep?.n_red === "number" ? prep.n_red : 0} />,
      detail: <DetailList items={checks.map((c) => `${c.status ?? "?"} — ${c.detail ?? c.name ?? "check"}`)} /> },
    { key: "standup", icon: Mic, title: "Standup", verdict: sectionVerdict(standup, standup?.verdict), summary: say(standup), freshness: freshLabel(standup),
      detail: <div className="whitespace-pre-wrap text-[12px] leading-relaxed text-[var(--gc-text-2)]">{(standup?.text_plain as string) || "NO DATA"}</div> },
    { key: "eod", icon: FileText, title: "EOD debrief", verdict: sectionVerdict(eod, eod?.verdict), summary: say(eod, "NO DATA"), freshness: freshLabel(eod),
      detail: <div className="text-[12px] text-[var(--gc-text-3)]">{(eod?.error as string) || "NO DATA"}</div> },
    { key: "calendar", icon: CalendarIcon, title: "Journal calendar", verdict: bookDayEntries.length ? "neutral" : "off",
      summary: bookDayEntries.length ? `${bookDayEntries.length}d strip — book net P&L` : "NO DATA", freshness: freshLabel(calendar),
      graphic: bookDayEntries.length
        ? <HeatStrip cells={bookDayEntries.map(([date, d]) => ({ value: d.n ?? d.g ?? 0, label: `${date}: ${(d.n ?? d.g ?? 0).toFixed(0)}` }))} />
        : undefined,
      detail: <DetailList items={bookDayEntries.slice(-10).reverse().map(([date, d]) => `${date} — net ${(d.n ?? 0).toFixed(2)} (${d.t ?? 0} trades)`)} /> },
  ];

  const researchTiles: TileSpec[] = [
    { key: "gym", icon: Dumbbell, title: "Gym scorecard", verdict: sectionVerdict(gym, gym?.overall_verdict ?? gym?.verdict), summary: say(gym), freshness: freshLabel(gym),
      graphic: ring(audits.length ? Math.round((audits.filter((a) => (a.verdict || "").toUpperCase() === "GREEN").length / audits.length) * 100) : 0, "var(--gc-cyan)"),
      detail: <DetailList items={audits.map((a) => `${a.verdict ?? "?"} — ${a.name ?? "audit"}: ${a.summary ?? ""}`)} /> },
    { key: "shadow", icon: Ghost, title: "Shadow board", verdict: sectionVerdict(shadow, shadow?.verdict), summary: say(shadow), freshness: freshLabel(shadow),
      detail: <DetailList items={shadowLive.map((l) => `${(l.verdict || "off").toUpperCase()} — ${l.name ?? "clock"}`)} /> },
    { key: "learning", icon: BookOpen, title: "Learning ledger", verdict: win7d || winToday ? "neutral" : "off",
      summary: learning ? `${winToday?.commits ?? 0} commits today, ${winToday?.kitchen_analyses ?? 0} analyses` : "NO DATA", freshness: freshLabel(learning),
      graphic: learning ? <Sparkline color="var(--gc-violet)" values={[win7d?.kitchen_analyses ?? 0, winToday?.kitchen_analyses ?? 0]} /> : undefined,
      detail: <DetailList items={latestVerdicts.slice(0, 8).map((v) => `${(v.kind ?? "?").toUpperCase()} — ${v.subject ?? "item"} (${v.at_et ?? ""})`)} /> },
    { key: "watchers", icon: Radar, title: "Watcher fleet", verdict: sectionVerdict(watchers, watchers?.verdict), summary: say(watchers), freshness: freshLabel(watchers),
      detail: <DetailList items={watcherRows.map((w) => `${w.name ?? "watcher"} — ${w.observations ?? 0} obs, $${(w.would_be_pnl ?? 0).toFixed(2)}`)} /> },
  ];

  const rigTiles: TileSpec[] = [
    { key: "righttail", icon: Target, title: "Right-tail capture", verdict: sectionVerdict(righttail, righttail?.verdict), summary: say(righttail), freshness: freshLabel(righttail),
      graphic: ring(Math.round(((righttail?.book_capture_rate as number | null) ?? 0) * 100), "var(--gc-cyan)"),
      detail: <DetailList items={[
        ...Object.entries(righttailPerArm).map(([arm, d]) => `${arm} — ${d.n_taken ?? 0}/${d.n_waves ?? 0} waves (${d.capture_rate != null ? `${(d.capture_rate * 100).toFixed(0)}%` : "N/A"})`),
        `${(righttail?.cap4_would_refuse_count as number | undefined) ?? 0} waves flagged would_be_refused_under_cap4 (TIGHT-LADDER forward ledger, 09-29 checkpoint)`,
      ]} /> },
    { key: "guards", icon: ShieldCheck, title: "Guards", verdict: sectionVerdict(guards, guards?.verdict), summary: say(guards), freshness: freshLabel(guards),
      detail: <DetailList items={guardProblems.map((p) => `${p.name ?? "task"} — ${p.note ?? "problem"}`)} /> },
    { key: "tasks", icon: ListChecks, title: "Scheduled tasks", verdict: sectionVerdict(tasks, tasks?.verdict), summary: say(tasks), freshness: freshLabel(tasks),
      graphic: dayline.length ? <Dayline items={dayline} /> : undefined,
      detail: <div className="flex flex-col gap-3">{taskLanes.map((l, i) => (
        <div key={i} className="text-[12px] text-[var(--gc-text-2)]"><span className="font-medium text-[var(--gc-text)]">{l.lane}</span> — {l.worst}</div>
      ))}</div> },
    { key: "autonomy", icon: Bot, title: "Autopilot",
      verdict: kitchenTrustGate === "DEGRADED" ? "red" : autonomy?.awake ? "green" : "off",
      summary: autonomy
        ? `${autonomy.awake ? "Awake" : "Quiet"}${(autonomy.quiet as Record<string, unknown>)?.active ? " — quiet hours" : ""}`
          + (kitchenTrustGate ? ` — Kitchen ${kitchenTrustGate}${kitchenFabRate != null ? ` (${(kitchenFabRate * 100).toFixed(1)}%)` : ""}` : "")
          + (checkpointPacket ? ` — Checkpoint ${checkpointPacket.met ?? 0}✓/${checkpointPacket.not_met ?? 0}✗/${checkpointPacket.insufficient_n ?? 0}⋯` : "")
        : "NO DATA",
      freshness: freshLabel(autonomy),
      detail: (kitchenTrustGate || checkpointPacket) ? (
        <div className="flex flex-col gap-2">
          {kitchenTrustGate ? (
            <div className="text-[12px] text-[var(--gc-text-2)]">
              Kitchen fabricated-artifact rate (30d): <span className="font-medium text-[var(--gc-text)]">
                {kitchenFabRate != null ? `${(kitchenFabRate * 100).toFixed(2)}%` : "N/A"}
              </span> ({kitchenProvMissing ?? "?"}/{kitchenFilesScored ?? "?"} files) — trust gate:{" "}
              <span className="font-medium text-[var(--gc-text)]">{kitchenTrustGate}</span>
            </div>
          ) : null}
          {checkpointPacket ? (
            <div className="text-[12px] text-[var(--gc-text-2)]">
              Checkpoint packet ({(checkpointPacket.generation_date as string) ?? "?"}, {(checkpointPacket.row_count as number) ?? 0} rows):{" "}
              <span className="font-medium text-[var(--gc-text)]">{(checkpointPacket.met as number) ?? 0} met</span>
              {" / "}
              <span className="font-medium text-[var(--gc-text)]">{(checkpointPacket.not_met as number) ?? 0} not met</span>
              {" / "}
              <span className="font-medium text-[var(--gc-text)]">{(checkpointPacket.insufficient_n as number) ?? 0} insufficient</span>
              {(checkpointPacket.provisional as number) ? <> {" / "}<span className="font-medium text-[var(--gc-text)]">{checkpointPacket.provisional as number} provisional</span></> : null}
              {" — "}
              <a href={`/${(checkpointPacket.file_0929 as string) ?? ""}`} className="underline hover:text-[var(--gc-text)]">09-29</a>
              {" · "}
              <a href={`/${(checkpointPacket.file_1030 as string) ?? ""}`} className="underline hover:text-[var(--gc-text)]">10-30</a>
            </div>
          ) : null}
        </div>
      ) : undefined },
    { key: "goal", icon: Target, title: "Active goal", verdict: goal?.active ? "green" : "off", summary: (goal?.title as string) || "NO DATA",
      freshness: goal?.days_left != null ? `${goal.days_left}d left` : "NO DATA",
      graphic: ring(goalPct, "var(--gc-violet)"),
      detail: <DetailList items={doneWhen} /> },
  ];

  const groups: { label: string; tiles: TileSpec[] }[] = [
    { label: "Trading", tiles: tradingTiles },
    { label: "Research", tiles: researchTiles },
    { label: "Rig", tiles: rigTiles },
  ];

  return (
    <div className="flex flex-col gap-6">
      {groups.map((g) => (
        <section key={g.label}>
          <GroupHeading id={String(g.label).toLowerCase() === "rig" ? "rig" : undefined}>{g.label}</GroupHeading>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {g.tiles.map((t, i) => (
              <BlurFade key={t.key} delay={i * 0.05} inView>
                <Tile spec={t} />
              </BlurFade>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

export default ProducerTiles;

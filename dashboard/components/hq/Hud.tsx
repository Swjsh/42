"use client";

import { useEffect, useRef, useState, useSyncExternalStore, Fragment } from "react";
import { getLivePerf, subscribeLivePerf } from "@/lib/hq-live-perf";
import { getAutoOrbitResumedAtMs, subscribeAutoOrbitResumed } from "@/lib/hq-camera-mode";
import { setHoveredPersonaIndex } from "@/lib/hq-hover-persona";
import Link from "next/link";
import type { HqApiResponse, TradingStatus, CrewEvent, PersonaState } from "./types";
import { auditVerdictColor, hhmmFromEtIso, isRegularTradingHours, minutesSinceEvidence, nowEtDayOfWeek, nowEtMinutes, personaStatusColor, truncateOneLine } from "./palette";
import type { MotionEvent } from "@/lib/useMotionEvents";
// CREW-2 (roster, 2026-09-14): the crew panel's pill/now/last/next derivation
// -- see lib/crew.ts's own header for why this logic lives there (pure,
// zero fs/fetch, ground truth stays in lib/personas.ts's PersonaState).
import { crewLastLine, crewNextLine, crewNowLine, deriveCrewPill, CREW_PILL_COLOR } from "@/lib/crew";
import { formatLiveSpyLine } from "@/lib/hq-market-pure";
import { formatPositionClause } from "@/lib/hq-positions-pure";

const BLOCKED_SOURCE_LABEL: Record<string, string> = {
  discord: "Discord",
  conductor_proposal: "Proposal",
  queue_escalation: "Escalation",
  goal_blocked: "Goal",
};

// ─── LIVE-1 item 5 (2026-09-14, coordinator-directed mid-task addition):
//     trading status strip -- "are we ready to trade today?" answered
//     without J asking. Pure functions, no component state -- recomputed
//     every Hud render (which already happens ~1x/sec off useEtClock's own
//     interval), matching this file's existing "read the clock fresh every
//     time" convention. ───────────────────────────────────────────────────

const TRADING_STRIP_COLOR = {
  green: "#22ff88",
  amber: "#ffb020",
  red: "#ff3b3b",
  grey: "#7f93b0",
} as const;
type TradingStripColor = keyof typeof TRADING_STRIP_COLOR;

const WEEKDAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

/** Next 09:30 ET weekday open, in ET minutes-since-midnight + day-of-week
 * terms (the SAME representation nowEtMinutes/nowEtDayOfWeek already use).
 * No market-holiday calendar is among this item's own listed source files,
 * so this is a plain weekday rule (Mon-Fri 09:30 ET) -- an honest,
 * documented simplification, not a claim of full exchange-calendar
 * accuracy (a real holiday would show as a "closed" market that ticks
 * anyway once its own scheduled tasks find nothing to do -- a known gap,
 * not a silent wrong answer). */
function nextOpenText(etMinutes: number, dayOfWeek: number): string {
  const minuteOfDay = etMinutes % (24 * 60);
  const openMin = 9 * 60 + 30;
  if (dayOfWeek >= 1 && dayOfWeek <= 5 && minuteOfDay < openMin) return "today 09:30 ET";
  let d = dayOfWeek;
  let daysAhead = 1;
  for (let i = 0; i < 7; i++) {
    d = (d + 1) % 7;
    if (d >= 1 && d <= 5) break;
    daysAhead++;
  }
  return `${daysAhead === 1 ? "tomorrow" : WEEKDAY_NAMES[d]} 09:30 ET`;
}

interface TradingStrip {
  color: TradingStripColor;
  text: string;
}

/** The one decision tree this whole item is built around -- see the task's
 * own spec: green = armed + a decision within 3min during RTH; amber =
 * readiness YELLOW; red = a decision older than 3min during RTH, or
 * readiness RED; grey = market closed. RED conditions are checked before
 * AMBER (a worse problem must never be masked by a lesser one displaying
 * instead) -- "isRth" itself comes from the SAME explicit-ET clock every
 * other RTH-gated piece of this app already uses (palette.ts's own
 * isRegularTradingHours/Scene.tsx#isRth), never a second clock source. */
function buildTradingStrip(trading: TradingStatus | undefined): TradingStrip {
  if (!trading) return { color: "grey", text: "Trading status unavailable" };
  const etMinutes = nowEtMinutes();
  const dayOfWeek = nowEtDayOfWeek();
  const { readiness, core } = trading;

  if (!isRegularTradingHours(etMinutes, dayOfWeek)) {
    const safeV = core.safe?.verdict ?? "?";
    const boldV = core.bold?.verdict ?? "?";
    return {
      color: "grey",
      text: `MARKET CLOSED · next open ${nextOpenText(etMinutes, dayOfWeek)} · last close: safe ${safeV} / bold ${boldV}`,
    };
  }

  const lastTickIso = [core.safe?.tsEt ?? null, core.bold?.tsEt ?? null].filter((v): v is string => !!v).sort().pop() ?? null;
  const ageMin = minutesSinceEvidence(lastTickIso ?? "");
  const bothArmed = !!core.safe?.armed && !!core.bold?.armed;
  const engineBarSpy = core.safe?.engineBarSpy ?? core.bold?.engineBarSpy ?? null;
  const vix = core.safe?.vix ?? core.bold?.vix ?? null;
  const safeV = core.safe?.verdict ?? "?";
  const boldV = core.bold?.verdict ?? "?";
  // Whichever account has an action string at all (both tick off the same
  // trigger bar, so they're almost always identical -- prefer safe, same
  // "first available" convention the rest of this function already uses).
  const engineAction = core.safe?.action ?? core.bold?.action ?? null;
  const engineActionReason = core.safe?.actionReason ?? core.bold?.actionReason ?? null;
  // HQ-POSITION-TRUTH (2026-09-15): a real open leg from lib/hq-positions.ts
  // (exit-state.json truth, independent of the per-tick action ledger)
  // ALWAYS outranks the generic engine-action clause below -- root cause
  // this fixes: the strip fell back to "holding"/flat the moment the
  // engine's action ledger stopped logging ENTER_* (~2 min post-entry) even
  // while the broker position stayed open for hours.
  const safePositionClause = formatPositionClause("safe", trading.position?.safe);
  const boldPositionClause = formatPositionClause("bold", trading.position?.bold);
  const positionClause = [safePositionClause, boldPositionClause].filter((c): c is string => !!c).join(" · ");

  let color: TradingStripColor;
  if (readiness.verdict === "RED" || ageMin === null || ageMin > 3) {
    color = "red";
  } else if (readiness.verdict === "YELLOW") {
    color = "amber";
  } else if (bothArmed && ageMin <= 3) {
    color = "green";
  } else {
    color = "amber";
  }

  const readinessPart = readiness.reasonDetail && readiness.verdict !== "GREEN"
    ? `readiness ${readiness.verdict} (${readiness.reasonDetail})`
    : `readiness ${readiness.verdict}`;

  // "SPY" here is now the LIVE tape (sight-beacon, ~1min-fresh), not the
  // engine's decision bar -- the whole point of this item: J was reading a
  // 09:30 bar's close as "current price" while the tape had already moved
  // up to $1.89. `engine <action-reason>` (only shown when the engine isn't
  // simply holding on a fresh tick) makes the SKIP/HOLD distinction visible
  // instead of collapsing everything into an undifferentiated "HOLD".
  const liveLine = formatLiveSpyLine(trading.market.live);
  const engineClause = positionClause
    ? ` · ${positionClause}`
    : engineAction && engineAction !== "HOLD" && engineActionReason
      ? ` · engine: ${engineActionReason}`
      : "";

  const text = `MARKET OPEN · engine ticking ${hhmmFromEtIso(lastTickIso)} ET · safe ${safeV} / bold ${boldV} · `
    + `${liveLine} (bar ${engineBarSpy !== null ? engineBarSpy.toFixed(2) : "?"}) · VIX ${vix !== null ? vix.toFixed(1) : "?"}`
    + `${engineClause} · ${readinessPart}`;

  return { color, text };
}

// ─── UX-1 U0 (2026-09-14): "is it working?" instrument -- J keeps asking
//     "still working right?"; per CLAUDE.md OP-25 a repeated question is a
//     missing instrument, not a query to keep re-answering. Pure function
//     off the additive `build` field (lib/station.ts#readHqBuildStatus) --
//     same "client formats, server only supplies raw facts" split every
//     other header line in this file already uses (buildTradingStrip above
//     is the same shape). The first two clauses render byte-for-byte the
//     task's own example ("HQ build · deployed 16:12 ET · building now: UX-1
//     (4 min)" / "· idle"); last-capture is appended as a third clause when
//     known -- an extra truthful fact, never a contradiction of the example. ──

function buildHqBuildLine(build: HqApiResponse["build"] | undefined): string {
  const deployed = build?.deployedAtEt ? `deployed ${build.deployedAtEt}` : "deployed ?";
  const building = build?.buildingNow
    ? `building now: ${build.buildingNow.builder} (${build.buildingNow.ageMin} min)`
    : "idle";
  const capture = build?.lastCaptureAtEt ? ` · last capture ${build.lastCaptureAtEt}` : "";
  return `HQ build · ${deployed} · ${building}${capture}`;
}

// ─── R3 event feed (CREW-2, 2026-09-14): merges the existing diff-derived
//     ticker lines (lib/useMotionEvents.ts's MotionEvent[], prose already
//     formatted for reading) with the new crew-events.jsonl rows (which
//     carry a real structured actor -- `who`, optionally `to`) into one
//     capped, avatar-chipped list. Pure functions, no component state. ────

interface FeedRow {
  key: string;
  /** "As-if-UTC" comparable epoch-ms (see comparableMsFromEtString below) --
   * sort key only, never rendered directly. */
  ms: number;
  /** Display stamp: "HH:MM" for today, "Sun 18:00" for any other day
   * (coordinator correction, 2026-09-14). */
  tsEt: string;
  actor: { emoji: string; color: string; name: string } | null;
  text: string;
}

const FEED_MAX_ROWS = 12;
const FEED_WEEKDAY_NAMES = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];

/** Best-effort actor match for a MotionEvent's already-formatted prose line
 * -- useMotionEvents.ts pushes lines starting `${p.emoji} ${p.name} ...` for
 * every persona-attributable event (fires, walks, RED/recovered). A line
 * with no persona-emoji prefix (a Station-fire summary, an idea-card
 * update, a GPU/presence toggle) legitimately has no single actor and gets
 * no chip -- never a guessed/fabricated one. */
function actorForMotionText(text: string, personas: PersonaState[]): FeedRow["actor"] {
  for (const p of personas) {
    if (text.startsWith(p.emoji)) return { emoji: p.emoji, color: p.color, name: p.name };
  }
  return null;
}

/** A crew-events.jsonl row's own `line` sometimes ALREADY embeds the actor
 * ("Coach: Gamma_Funnel_5 went Disabled"), sometimes doesn't ("8 lanes --
 * 4 GREEN..."), and `to` is set on effectively every row (the producer uses
 * it as a "who reads this" routing target, not only genuine handoffs) --
 * verified against the live file this session (both shapes seen from the
 * SAME `who`). Blindly prepending "${who} -> ${to}:" doubled the actor name
 * on the first shape ("Coach -> Gamma: Coach: ... went Disabled"). Fixed by
 * skipping the prefix when `line` already starts with it. */
function formatCrewLine(e: CrewEvent): string {
  const withPrefix = e.line.startsWith(`${e.who}:`);
  if (withPrefix) return e.line;
  if (e.to) return `${e.who} → ${e.to}: ${e.line}`;
  return `${e.who}: ${e.line}`;
}

// ─── Coordinator correction (2026-09-14): "rows must sort by ts descending
//     ACROSS sources" -- the old build just concatenated crew rows (newest-
//     first within that source) ahead of motion rows (also newest-first
//     within ITS source), so a same-timestamp BACKFILL burst of old
//     crew-events rows sat above today's more-recent motion-ticker rows.
//     Fixed with a real merge-sort on a comparable epoch-ms per row, across
//     BOTH sources. ──────────────────────────────────────────────────────

/** Today's ET calendar date as {y, mo, d} -- combined with a MotionEvent's
 * bare "HH:MM" (it carries no date at all) to make it comparable against a
 * crew-events row's full date+time. */
function etTodayYMD(nowMs: number): { y: number; mo: number; d: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date(nowMs));
  const get = (t: string) => Number(parts.find((p) => p.type === t)?.value ?? "0");
  return { y: get("year"), mo: get("month"), d: get("day") };
}

/** "As-if-UTC" comparable epoch-ms from a full "YYYY-MM-DD HH:MM[:SS]"-ish
 * string (crew-events.jsonl's ts_et) -- digits taken literally via
 * Date.UTC, not a true UTC instant, but consistently wrong by the same
 * amount as every other comparable-ms value this module produces, so
 * relative ORDER across rows is correct (same trick lib/useMotionEvents.ts's
 * own toComparableEtMs already uses for the SAME reason -- reimplemented
 * here rather than imported, since that hook is a different builder's file
 * and this merge needs to run for BOTH sources with one consistent trick). */
function comparableMsFromEtString(raw: string): number | null {
  const m = /(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2}))?/.exec(raw);
  if (!m) return null;
  const [, y, mo, d, h, mi, s] = m;
  return Date.UTC(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), s ? Number(s) : 0);
}

/** Same trick for a motion-ticker event's bare "HH:MM" -- these are live
 * diff events generated THIS browser session (useMotionEvents.ts), always
 * "today" by construction, so today's ET date is what they're combined
 * with. */
function comparableMsFromHHMM(hhmm: string, nowMs: number): number | null {
  const m = /(\d{2}):(\d{2})/.exec(hhmm);
  if (!m) return null;
  const { y, mo, d } = etTodayYMD(nowMs);
  return Date.UTC(y, mo - 1, d, Number(m[1]), Number(m[2]), 0);
}

/** "HH:MM" for a row whose as-if-UTC comparable date matches today; "Sun
 * 18:00" (weekday abbreviation) for any other day -- reads the SAME as-if-
 * UTC value back via UTC getters (never local-time getters, which would
 * silently reintroduce this box's own non-ET local time -- CLAUDE.md's
 * standing TZ lesson). */
function formatRowStamp(ms: number, nowMs: number): string {
  const d = new Date(ms);
  const hh = String(d.getUTCHours()).padStart(2, "0");
  const mm = String(d.getUTCMinutes()).padStart(2, "0");
  const today = etTodayYMD(nowMs);
  const sameDay = d.getUTCFullYear() === today.y && d.getUTCMonth() + 1 === today.mo && d.getUTCDate() === today.d;
  if (sameDay) return `${hh}:${mm}`;
  return `${FEED_WEEKDAY_NAMES[d.getUTCDay()]} ${hh}:${mm}`;
}

/** Builds the merged, capped, TRUE-chronological (newest-first, across
 * both sources) feed. crew-events.jsonl rows (structured, real `who`/`to`)
 * and the existing motion-diff ticker lines are read from the same well
 * each poll -- "what it reads today," per R3's own spec -- then sorted
 * together by real timestamp rather than concatenated by source. Every
 * " -> " separator (both sources use plain ASCII arrows) renders as "→"
 * for handoff/interaction rows, uniformly. */
function buildFeedRows(motionEvents: MotionEvent[], crewEvents: CrewEvent[], personas: PersonaState[], nowMs: number): FeedRow[] {
  const personaByName = new Map(personas.map((p) => [p.name, p]));
  // Slicing each source to FEED_MAX_ROWS before the merge is a safe upper
  // bound (the final sorted+capped output can never need MORE than
  // FEED_MAX_ROWS from either source alone) while avoiding a full-array sort
  // over crewEvents' whole (up to ~100-row) buffer every render.
  const crewRows: FeedRow[] = crewEvents.slice(-FEED_MAX_ROWS).map((e, i) => {
    const p = personaByName.get(e.who);
    const ms = comparableMsFromEtString(e.ts_et) ?? 0;
    return {
      key: `crew-${e.ts_et}-${i}`,
      ms,
      tsEt: formatRowStamp(ms, nowMs),
      actor: p ? { emoji: p.emoji, color: p.color, name: p.name } : null,
      text: formatCrewLine(e).replace(/ -> /g, " → "),
    };
  });
  const motionRows: FeedRow[] = motionEvents.slice(0, FEED_MAX_ROWS).map((ev) => {
    const ms = comparableMsFromHHMM(ev.tsEt, nowMs) ?? 0;
    return {
      key: `motion-${ev.id}`,
      ms,
      tsEt: formatRowStamp(ms, nowMs),
      actor: actorForMotionText(ev.text, personas),
      text: ev.text.replace(/ -> /g, " → "),
    };
  });
  return [...crewRows, ...motionRows].sort((a, b) => b.ms - a.ms).slice(0, FEED_MAX_ROWS);
}

interface HudProps {
  data: HqApiResponse | undefined;
  error: unknown;
  kiosk: boolean;
  isValidating: boolean;
  motionEvents: MotionEvent[];
  /** Pass G (2026-09-13, coordinator item 4): "on the ultra tier show THIS
   * device's numbers; the TV line only on the TV tier (or prefixed as a
   * second line, never alone)" -- the perf-line block below needs to know
   * which tier IT is rendering inside to pick data.perf vs data.perfOther
   * correctly; Hud.tsx previously always read data.perf regardless of
   * viewer. */
  tier: "ultra" | "tv";
  /** UX-1 U1 (2026-09-14): page.tsx's own prefers-reduced-motion match --
   * threaded in so the legend's fade uses a CSS transition only when motion
   * is allowed (an instant show/hide otherwise), same contract every other
   * reducedMotion branch in this codebase (Scene.tsx#CameraRig, etc.)
   * follows. Optional/defaulted false so this is additive, not breaking, for
   * any other caller of <Hud> that predates this prop. */
  reducedMotion?: boolean;
}

/** Pass G (2026-09-13, coordinator item 1: "split layout... world left,
 * roster right, the Grok-Bot company view J liked"): fixed right-column
 * width shared with UltraCanvasRoot.tsx/CanvasRoot.tsx, whose OWN canvas
 * container is width-constrained to `calc(100% - HUD_RIGHT_COLUMN_WIDTH)`
 * so the 3D canvas physically CANNOT render a pixel under this column --
 * solved by construction, not by the camera-angle/opacity mitigations Pass
 * F tried (which helped but never fully eliminated the collision, per that
 * pass's own honest note). One constant, three files -- exported from here
 * since this component owns the column's actual content. */
export const HUD_RIGHT_COLUMN_WIDTH = 500;

function useEtClock(): string {
  const [text, setText] = useState("--:--:--");
  useEffect(() => {
    const fmt = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    });
    const tick = () => setText(fmt.format(new Date()) + " ET");
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return text;
}

const HUD_FONT = "system-ui, -apple-system, Segoe UI, Roboto, sans-serif";
// UX-1 U1 (2026-09-14): controls legend auto-fade delay, see its own effect's comment.
const LEGEND_FADE_MS = 8000;

// ─── PANEL-2 (2026-09-14): "is it running on my PC, or is this whole thing
//     agents running on my PC? Do I really have this many active agents on
//     my PC?" -- J's verbatim question, routed to lib/hq-runtime.ts's own
//     standing instrument (data.runtime) rather than answered once and
//     forgotten. This block is the presentation layer for that field. ──────

/** Genuine UTC ISO -> "HH:MM" in America/New_York. Deliberately NOT
 * palette.ts's hhmmFromEtIso -- that function REGEX-extracts digits already
 * embedded as ET wall-clock text (built for core-decisions.jsonl's own
 * ts_et shape) and would silently read the wrong (UTC) hour off a REAL ISO
 * string like PersonaState.lastFireISO (verified by reading its own
 * implementation this session before reusing anything -- exactly the class
 * of TZ bug CLAUDE.md's standing lesson warns about). Same small
 * Intl-based helper this codebase already carries independently in
 * lib/personas.ts / lib/crew.ts / lib/hq.ts. */
function hhmmEtFromIso(iso: string | null): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return null;
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(new Date(t));
  const hh = parts.find((p) => p.type === "hour")?.value;
  const mm = parts.find((p) => p.type === "minute")?.value;
  return hh && mm ? `${hh}:${mm}` : null;
}

/** Number Ticker (https://21st.dev/dillionverma/number-ticker, "Number
 * Ticker": an animated counter that tweens from its old value to a new one
 * rather than snapping) -- hand-implemented via requestAnimationFrame over
 * plain text content (no code copied): cheaper than a CSS-driven approach
 * and trivially TV-safe (no transform/opacity/compositor layer at all, just
 * DOM text updates for a bounded ~500ms per change, matching this file's
 * own "10-foot-readability... no animations" sizing elsewhere). Skips the
 * tween entirely under reducedMotion, per this task's own instruction to
 * respect that prop on every new animation. */
function NumberTicker({ value, reducedMotion }: { value: number; reducedMotion: boolean }) {
  const [display, setDisplay] = useState(value);
  const fromRef = useRef(value);
  useEffect(() => {
    if (reducedMotion) { setDisplay(value); fromRef.current = value; return; }
    const from = fromRef.current;
    if (from === value) return;
    const start = performance.now();
    const durationMs = 500;
    let raf = 0;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / durationMs);
      const eased = 1 - (1 - t) * (1 - t); // ease-out
      setDisplay(Math.round(from + (value - from) * eased));
      if (t < 1) raf = requestAnimationFrame(tick);
      else fromRef.current = value;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, reducedMotion]);
  return <>{display}</>;
}

/** Sum of only the 6 Gamma-relevant process buckets -- deliberately NOT
 * `processes.total` (that includes hundreds of unrelated system processes:
 * svchost, conhost, steamwebhelper, Discord, etc -- a live capture this
 * session found 379 total vs ~50 in these 6 buckets). This is "live
 * processes" in the sense J asked the question, not "everything running on
 * the PC". */
function trackedProcessTotal(p: NonNullable<HqApiResponse["runtime"]>["processes"]): number {
  if (!p) return 0;
  return p.python + p.pythonw + p.ollama + p.ollama_llama_server + p.claude + p.node;
}

/** Nonzero-only breakdown, e.g. "python 2 · pythonw 16 · claude 25" -- never
 * pads with zero-count categories (nothing to say about them). */
function processBreakdown(p: NonNullable<HqApiResponse["runtime"]>["processes"]): Array<{ label: string; n: number }> {
  if (!p) return [];
  return [
    { label: "python", n: p.python },
    { label: "pythonw", n: p.pythonw },
    { label: "claude", n: p.claude },
    { label: "node", n: p.node },
    { label: "ollama", n: p.ollama },
    { label: "ollama_llama_server", n: p.ollama_llama_server },
  ].filter((row) => row.n > 0);
}

const RUNTIME_KIND_LABEL: Record<string, string> = {
  "python-script": "Python script",
  "local-llm": "Ollama",
  "claude-session": "Claude session",
  "none": "no producer",
};

/** "RUNS AS" row text for one crew card -- e.g. "Python script · this PC ·
 * last 18:21 · next ~18:51 ET" / "Ollama gamma-planner-fast · this PC GPU ·
 * next due now" / "Claude session · none · DISABLED -- ... not scheduled".
 * Reuses role.nextFire verbatim (server-computed, lib/hq-runtime.ts) rather
 * than re-deriving cadence text a third time client-side. */
function buildRunsAsLine(role: HqApiResponse["runtime"]["roles"][number] | undefined, brainModel: string | null, lastFireISO: string | null): string {
  if (!role) return "runtime unknown";
  const kindLabel = RUNTIME_KIND_LABEL[role.runtime] ?? role.runtime;
  const label = role.runtime === "local-llm" && brainModel ? `${kindLabel} ${brainModel}` : kindLabel;
  const hostLabel = role.runtime === "local-llm" && role.host === "this PC" ? "this PC GPU" : role.host;
  const lastHHMM = hhmmEtFromIso(lastFireISO);
  const lastBit = lastHHMM ? `last ${lastHHMM} · ` : "";
  return `${label} · ${hostLabel} · ${lastBit}next ${role.nextFire}`;
}

// ─── PANEL-3 (2026-09-14): LEARN tab presentation helper -- pure, no
//     component state. See lib/hq-learn.ts's own header for the 6 real
//     files behind data.learn; this file only ever renders what that module
//     already computed, never re-derives a number. ─────────────────────────

/** Chip style for a LearnedRow's `who` -- reuses the SAME persona
 * emoji/color the Crew tab already renders (PersonaState, matched by name)
 * so "Chef"/"Coach"/"Analyst" read as the same actor across both tabs.
 * "Gamma" (lib/hq-learn.ts's LearnedWho enum) matches the roster's "Gamma
 * (Manager)" by prefix, not exact string equality -- the two names differ
 * on purpose (see lib/hq-runtime.ts's own ROSTER_ORDER). "Autopsy" is not a
 * roster persona at all (trade_autopsy.py is a nightly script, not a crew
 * member with a desk), so it gets a fixed neutral chip rather than a guessed
 * match. */
const AUTOPSY_CHIP = { emoji: "🔬", color: "#8296b3" } as const;
function personaChipForLearnedWho(who: string, personas: PersonaState[]): { emoji: string; color: string } {
  if (who === "Autopsy") return AUTOPSY_CHIP;
  const match = personas.find((p) => (who === "Gamma" ? p.name.startsWith("Gamma") : p.name === who));
  return match ? { emoji: match.emoji, color: match.color } : { emoji: "❔", color: "#7f93b0" };
}

/**
 * Plain HTML overlay (not 3D text -- crisp at any TV viewing distance).
 * Sits in a fixed, full-viewport, pointer-events-none wrapper above the
 * <Canvas>; individual controls (Home link) re-enable pointer events.
 */
export default function Hud({ data, error, kiosk, isValidating, motionEvents, tier, reducedMotion = false }: HudProps) {
  const etClock = useEtClock();
  // World-2 coordinator review (2026-09-14, W6 mechanism): this page's OWN
  // live perf sample -- see lib/hq-live-perf.ts's own header and the perf
  // block below for the full "never read the shared ledger for THIS
  // device's own number" reasoning. `() => null` is the correct
  // server-snapshot (this store is never written during SSR).
  const livePerf = useSyncExternalStore(subscribeLivePerf, getLivePerf, () => null);
  // LIVE-1 item 1 (2026-09-14): "H toggles the HUD" -- ultra tier only,
  // same scoping as the free camera itself (Scene.tsx's OrbitControls/
  // keyboard fly-to). A plain top-level toggle, not threaded through
  // Scene.tsx/Canvas at all -- this component already owns its own full
  // render tree (both overlay columns), so there is nothing to coordinate
  // with the 3D scene here. Defaults visible; a page reload always starts
  // visible again (no persisted preference -- this is a per-session view
  // toggle, not a setting).
  const [hudVisible, setHudVisible] = useState(true);
  useEffect(() => {
    if (tier !== "ultra") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === "h" || e.key === "H") setHudVisible((v) => !v);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tier]);

  // UX-1 U1 (2026-09-14, external-reference convention #1 -- see
  // ENVIRONMENT-PLAN.md's own "UX conventions" header, a dismissible legend
  // that gets out of the way once the player has demonstrably started
  // driving): the controls legend fades LEGEND_FADE_MS after the FIRST real
  // user input (pointerdown/wheel/keydown), not a blind mount timer -- a
  // viewer who hasn't touched anything yet still needs to see it. "?" is a
  // manual toggle: showing it again re-arms the same fade-after-8s so it
  // never stays up forever just because it was recalled. `armed` (a plain
  // closure variable, not React state) guarantees only the FIRST input ever
  // starts the clock; every later input before the fade is a no-op, per the
  // task's own literal "fades 8s after the first user input" spec (not
  // "resets on every input"). Ultra tier only -- HARD RULES: "TV tier:
  // legend/tooltips off".
  //
  // HUD-OBSTACLE (2026-09-15): on kiosk=1 there is no operator to ever fire
  // pointerdown/wheel/keydown (real evidence: plaque-overview.png was
  // captured 03:12 ET, unattended, with the legend still fully opaque --
  // `armed` never flipped true because nothing ever touched the page). The
  // `data-hq-obstacle` fix above already keeps world labels off this bar
  // regardless, but the bar is still purely instructional chrome with no
  // one to instruct on a kiosk, so it also gets the SAME mount-triggered
  // fade clock a real first input would start -- `onFirstInput()` called
  // once at mount is the smallest change that reuses every existing rule
  // (LEGEND_FADE_MS, `armed` latching, the manual "?" re-arm) rather than a
  // second fade mechanism.
  const [legendVisible, setLegendVisible] = useState(true);
  useEffect(() => {
    if (tier !== "ultra") return;
    let armed = false;
    let fadeTimer: ReturnType<typeof setTimeout> | null = null;
    const startFadeClock = () => {
      if (fadeTimer !== null) clearTimeout(fadeTimer);
      fadeTimer = setTimeout(() => setLegendVisible(false), LEGEND_FADE_MS);
    };
    const onFirstInput = () => {
      if (armed) return;
      armed = true;
      startFadeClock();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "?") {
        setLegendVisible((v) => {
          const next = !v;
          if (next) startFadeClock(); // brought back manually -- re-arm the same auto-fade
          return next;
        });
        return;
      }
      onFirstInput();
    };
    if (kiosk) onFirstInput(); // no operator on a kiosk to ever fire a real input event
    window.addEventListener("pointerdown", onFirstInput);
    window.addEventListener("wheel", onFirstInput, { passive: true });
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onFirstInput);
      window.removeEventListener("wheel", onFirstInput);
      window.removeEventListener("keydown", onKey);
      if (fadeTimer !== null) clearTimeout(fadeTimer);
    };
  }, [tier, kiosk]);

  // UX-1 U8/U6 (2026-09-14): right panel tabs -- "Crew | Activity" (the
  // sim-game tab-strip option J offered, chosen over a stacked section: 7
  // crew cards + up to FEED_MAX_ROWS activity rows stacked would make the
  // panel very long to scroll through, and J's whole complaint was "too
  // much on screen" -- a tab keeps ONE focused list visible at a time).
  const [activePanelTab, setActivePanelTab] = useState<"crew" | "activity" | "learn">("crew");
  // PANEL-3 (2026-09-14): dev-only `?tab=learn` query hook -- lets the
  // headless capture script (hq_capture.ps1) land directly on the LEARN tab
  // for a proof screenshot without a synthetic click. Harmless in normal
  // browsing: an unrecognized or absent `tab` value leaves the default
  // ("crew") untouched, and this never writes back to the URL.
  useEffect(() => {
    try {
      const tab = new URLSearchParams(window.location.search).get("tab");
      if (tab === "crew" || tab === "activity" || tab === "learn") setActivePanelTab(tab);
    } catch {
      // URLSearchParams/window access should never crash the page
    }
  }, []);

  // U6: which persona is currently "focused" (hotkey 1-7, a crew-card
  // click, or -- once U2 lands -- a world click, ALL of which go through
  // the SAME synthetic `window` "keydown" event flyToDesk already
  // dispatches below; this listener is just one more reader of that one
  // channel, never a second focus mechanism). `id` (not just `index`)
  // increments on every event so re-focusing the SAME persona twice in a
  // row still re-triggers the scroll+glow effect below (a plain index
  // wouldn't change identity on a repeat). Ultra tier only -- hotkeys are
  // ultra-only (Scene.tsx's `ultra`-gated CameraRig listener).
  const [focusEvent, setFocusEvent] = useState<{ index: number; id: number } | null>(null);
  const focusIdRef = useRef(0);
  useEffect(() => {
    if (tier !== "ultra") return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key >= "1" && e.key <= "7") {
        focusIdRef.current += 1;
        setFocusEvent({ index: Number(e.key) - 1, id: focusIdRef.current });
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [tier]);

  // U6: external-reference convention #3 ("the panel tracks the selection")
  // -- scroll the focused persona's card to the top of the scroll region
  // (pinned under the header) and switch to the Crew tab so it's actually
  // visible. Depends ONLY on `focusEvent` (not `personas`, which is a BRAND
  // NEW array reference every SWR poll -- see page.tsx's own sceneData
  // comment on why raw `data` is unstable across polls) so this never
  // re-fires/re-scrolls on a poll that didn't change the focus, only on a
  // genuinely new focus event; it reads the latest personas/reducedMotion
  // via closure when it DOES fire, which is exactly the behavior wanted.
  const cardRefs = useRef(new Map<string, HTMLDivElement>());
  useEffect(() => {
    if (!focusEvent) return;
    const name = personas[focusEvent.index]?.name;
    if (!name) return;
    setActivePanelTab("crew");
    cardRefs.current.get(name)?.scrollIntoView({ block: "start", behavior: reducedMotion ? "auto" : "smooth" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusEvent]);

  // U6: "compact card mode (2 lines) when the viewport height < 1000 px" --
  // a plain resize listener (this is a window-chrome fact, not something
  // /api/hq ever needs to know), checked at mount so a J session that opens
  // the browser already short doesn't wait for a resize event to see it.
  const [compactPanel, setCompactPanel] = useState(false);
  useEffect(() => {
    const check = () => setCompactPanel(window.innerHeight < 1000);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

  // UX-1 U5 (2026-09-14): "when the cinematic orbit resumes after 45s idle,
  // show a 3s hint" -- lib/hq-camera-mode.ts's own header explains the
  // cross-Canvas-boundary store this reads. Scene.tsx#CameraRig's own idle-
  // timeout mode transition (mode.current = "auto") is the ONLY call site
  // that ever needs to call reportAutoOrbitResumed() -- not yet wired
  // (Scene.tsx is owned by the LAYOUT builder's in-flight rewrite this
  // pass; see this pass's own coordinator-directed sequencing note), this
  // reader half is safe to ship ahead of that one-line call site landing --
  // it simply never fires until it does.
  const autoOrbitResumedAtMs = useSyncExternalStore(subscribeAutoOrbitResumed, getAutoOrbitResumedAtMs, () => null);
  const [showAutoOrbitHint, setShowAutoOrbitHint] = useState(false);
  useEffect(() => {
    if (autoOrbitResumedAtMs === null) return;
    setShowAutoOrbitHint(true);
    const t = setTimeout(() => setShowAutoOrbitHint(false), 3000);
    return () => clearTimeout(t);
  }, [autoOrbitResumedAtMs]);

  const mode = data?.mode ?? "unknown";
  const gaming = mode === "gaming";
  // GPU-YIELD (queue item e, 2026-09-15): local brain (Ollama) inference
  // burst on the same RTX 5080 -- see lib/hq-runtime.ts#isBrainBusy for the
  // exact rule (Ollama has a loaded model AND nvidia-smi util > 50%, never
  // a bare utilization threshold, so HQ's own rendering never triggers
  // this on itself). Server-derived only, never re-computed client-side.
  const brainBusy = data?.runtime?.brain?.busy === true;
  const present = data?.presence?.present ?? null;
  const syncedText = data
    ? `Synced ${new Date(data.fetched_at).toLocaleTimeString()}${isValidating ? " -- syncing..." : ""}`
    : error
      ? `Refresh failed (${error instanceof Error ? error.message : "fetch failed"})`
      : "Loading...";
  const personas = data?.company?.personas ?? [];
  const blockedItems = data?.blocked ?? [];
  // CREW-2 (roster): one "now" reference per render, shared by the feed's
  // sort/day-prefix logic and every card's pill/next: line (lib/crew.ts's
  // functions take explicit time, never Date.now() buried inside) -- this
  // component already re-renders ~1x/sec via useEtClock's own interval, so
  // this stays fresh without a second timer.
  const nowMs = Date.now();
  // R3 (CREW-2): merged, capped, newest-first event feed -- see this file's
  // own buildFeedRows() header comment for the two sources it merges.
  const feedRows = buildFeedRows(motionEvents, data?.crewEvents ?? [], personas, nowMs);
  // Company audit badge (commit 58d0b9c6, coordinator 2026-09-13: "the
  // roster must show ghosts as ghosts") -- matched by name, the same string
  // on both sides (PersonaState.name / PersonaAudit.name). `data.audit` is
  // null on an old build or a failed audit run (fail-open) -- every lookup
  // below falls back to "no badge" rather than a fake verdict.
  const auditByName = new Map((data?.audit?.personas ?? []).map((a) => [a.name, a]));
  // PANEL-2 (2026-09-14): the standing "is it running on my PC" instrument
  // -- see lib/hq-runtime.ts's own header for the full truth this carries.
  // `handoffs` was not previously destructured by this file at all (only
  // `data?.company?.personas` was); needed now for the animated-beam
  // connector below.
  const runtime = data?.runtime;
  const roleByName = new Map((runtime?.roles ?? []).map((r) => [r.name, r]));
  // PANEL-3 (2026-09-14): the LEARN tab's own data, plus the SAME "next
  // fire" text the RUNS AS row already computes for Gamma (Manager) -- the
  // Station loop is this tab's own producer (see lib/hq-runtime.ts's
  // ROLE_CLASSIFICATION), so the empty state reuses that text rather than a
  // second "when does Station fire next" computation.
  const learn = data?.learn;
  const stationNextFire = roleByName.get("Gamma (Manager)")?.nextFire ?? "soon";
  const handoffs = data?.company?.handoffs ?? [];
  /** True iff computeHandoffs() (lib/personas.ts) reports a FRESH ("OK")
   * handoff whose `from`/`to` strings (which carry an emoji prefix, e.g.
   * "✈️ Pilot") contain the given plain persona names. Used only for the
   * 2 pairs that are BOTH real handoff entries AND adjacent in the fixed
   * roster render order (Pilot->Analyst, Analyst->Chef) -- see the crew
   * card map below. */
  const handoffFresh = (fromName: string, toName: string): boolean =>
    handoffs.some((h) => h.status === "OK" && h.from.includes(fromName) && h.to.includes(toName));

  return (
    <>
    {/* LIVE-1 item 1 (2026-09-14): "H toggles the HUD" -- both overlay
        columns below are gated on `hudVisible` (ultra tier only triggers the
        keydown listener above; TV kiosk always renders, same as before this
        pass). */}
    {hudVisible && (
    <div
      style={{
        position: "fixed", top: 0, left: 0, bottom: 0, width: `calc(100% - ${HUD_RIGHT_COLUMN_WIDTH}px)`,
        pointerEvents: "none", fontFamily: HUD_FONT, zIndex: 10, overflow: "hidden",
      }}
    >
      <style>{`
        /* "Epic animations for the folders" (2026-09-13, J via 21st.dev) --
           hand-implemented (no code copied), concepts credited per rule:
           transform/opacity/background-position ONLY (no filter:blur,
           box-shadow spreads, or backdrop-filter -- those melt the TV's
           Mali-G31 compositor). Shared here so drei's <Html>-portaled
           content elsewhere in the tree (module panels, brain plaque) can
           use the same classes -- <style> is a plain global stylesheet. */

        /* Border Beam (https://21st.dev/s/border, "Border Beam": a beam
           that travels around a card's edge) -- a rotating conic-gradient
           behind a 1px-padded wrapper; the inner panel's own background
           covers everything except that 1px ring. transform:rotate only. */
        /* J 2026-09-14 ~18:15 ET: "i asked for the scanner to be removed"
           -- the rotating conic wedge that used to live here WAS the
           scanner: inset:-100% with no overflow clip swept a ~58deg
           status-colored fan, 3x the label's own size, around EVERY plaque
           (real capture models-FINAL-preset0-2235.png: the green fans under
           Analyst/Chef/Treasurer/Scout/Coach, the cyan one over the BRAIN
           plaque, the pink one on the smart board). The 11:00 ET "spinning
           color radar looking things" pass removed the 3D rings but never
           this CSS twin. Now a STATIC 1px status-colored ring -- zero
           animation, same geometry (border replaces the 1px padding). */
        .hq-beam { position: relative; padding: 0; border: 1px solid var(--beam-color, #7ad9ff); }

        /* Shine Border (https://21st.dev/s/border, "Shine Border": a moving
           light effect that travels across the border) -- reimagined as a
           one-shot diagonal shine sweep across the panel, replayed by
           remounting the span via a changing React key prop whenever the
           row's health/state changes. transform:translateX + opacity only. */
        .hq-shine {
          position: absolute; top: -30%; bottom: -30%; left: -60%; width: 35%;
          background: linear-gradient(100deg, transparent, rgba(255,255,255,0.5), transparent);
          animation: hq-shine-sweep 0.9s ease-out;
          pointer-events: none;
        }
        @keyframes hq-shine-sweep {
          from { transform: translateX(0%); opacity: 0; }
          15% { opacity: 1; }
          to { transform: translateX(420%); opacity: 0; }
        }

        /* Meteors (a "meteor shower" pattern -- a group of beams drifting
           through a container; see e.g. magicui.design/docs/components/meteors,
           cross-listed on 21st.dev) -- a subtle decorative drift behind the
           HUD title, low-opacity so it never competes with the readable
           text on top of it. transform:translate + opacity only. */
        .hq-meteor {
          position: absolute; width: 2px; height: 46px; top: -50px; left: 0;
          background: linear-gradient(180deg, rgba(122,217,255,0.85), transparent);
          animation: hq-meteor-fall linear infinite;
        }
        @keyframes hq-meteor-fall {
          0% { transform: translate(0, 0) rotate(35deg); opacity: 0; }
          12% { opacity: 0.65; }
          85% { opacity: 0.65; }
          100% { transform: translate(150px, 130px) rotate(35deg); opacity: 0; }
        }

        /* Roster panel accent (Company Mode step 5, 2026-09-13): a GREEN
           persona row breathes gently -- opacity only, same TV-safe
           constraint as everything above. Cheap enough to run per-row
           (bounded at 7 rows max, the fixed roster size). */
        .hq-pulse { animation: hq-pulse-glow 1.8s ease-in-out infinite; }
        @keyframes hq-pulse-glow { 0%, 100% { opacity: 1; } 50% { opacity: 0.6; } }

        /* Ideas-wall card flip (LIVE-1 item 2d, 2026-09-14): IdeasWall.tsx
           applies this to every card row -- a keyed React list only ever
           MOUNTS (replaying this) a row whose id is genuinely new, an
           existing card's row is REUSED (no remount, no replay) when the
           list just shifts around it. transform + opacity only. */
        .hq-card-flip { animation: hq-card-flip-in 0.5s ease-out; transform-origin: top center; }
        @keyframes hq-card-flip-in { 0% { transform: rotateX(-85deg); opacity: 0; } 100% { transform: rotateX(0deg); opacity: 1; } }

        /* CREW-2 (roster, 2026-09-14): crew card hover/focus -- NOT bound by
           the "transform/opacity/background-position only" rule the
           continuous @keyframes classes above follow, because this only
           ever runs off a real mouse-hover/keyboard-focus event, which the
           TV kiosk (no pointer, no keyboard) can never trigger -- there is
           no always-on TV-compositor cost here to guard against. Cheap
           properties anyway (border-color/background/transform, no blur or
           shadow spread). R2: click/Enter/Space flies the camera to that
           persona's desk (Scene.tsx's own keydown listener, dispatched via
           a synthetic KeyboardEvent -- never a Scene.tsx edit). */
        .hq-crew-card { transition: border-color 0.15s ease, background 0.15s ease, transform 0.15s ease; }
        .hq-crew-card:hover { border-color: rgba(122,217,255,0.65); background: rgba(9,13,24,0.97); transform: translateX(-2px); }
        .hq-crew-card:focus-visible { outline: 2px solid #7ad9ff; outline-offset: 2px; }

        /* UX-1 U6 (2026-09-14): thin, momentum-friendly scrollbar for the
           right panel's scrollable body -- "thin scrollbar, momentum" per
           the task spec. Chromium/Edge (this dashboard's own stated target)
           reads the ::-webkit-scrollbar rules; scrollbar-width/-color is the
           standard-track equivalent, harmless where unsupported. Native
           wheel/trackpad scrolling already carries momentum in this
           Chromium target -- no extra CSS needed for that half. */
        .hq-panel-scroll { scrollbar-width: thin; scrollbar-color: rgba(122,217,255,0.35) transparent; }
        .hq-panel-scroll::-webkit-scrollbar { width: 8px; }
        .hq-panel-scroll::-webkit-scrollbar-thumb { background: rgba(122,217,255,0.35); border-radius: 4px; }
        .hq-panel-scroll::-webkit-scrollbar-track { background: transparent; }

        /* UX-1 U6: 2s focus glow ring on a crew card -- remounted via a
           changing React key (see the crew-card map's own comment) so a
           REPEAT focus of the same persona replays this, no JS timer
           needed. transform/opacity only -- this codebase's own standing
           TV-compositor rule, even though this class only ever mounts on
           the ultra tier (see this file's own hq-crew-card comment for why
           that rule is applied here anyway: consistency, not a hard need). */
        .hq-focus-glow { position: absolute; inset: -3px; border-radius: 12px; border: 2px solid #7ad9ff; pointer-events: none; animation: hq-focus-glow-fade 2s ease-out forwards; }
        @keyframes hq-focus-glow-fade { 0% { opacity: 1; } 60% { opacity: 0.9; } 100% { opacity: 0; } }

        /* PANEL-2 (2026-09-14) -- 3 concepts taken from 21st.dev, hand-
           implemented (no code copied), transform/opacity ONLY per this
           file's own standing TV-compositor rule (see .hq-beam/.hq-shine
           above). Number Ticker (the 3rd concept) needed no CSS at all --
           it is a plain requestAnimationFrame text tween, see NumberTicker(). */

        /* Animated List (https://21st.dev/@dillionverma/components/animated-list,
           "Animated List": items animate in with a slide+fade when a new one
           is added) -- applied to the Activity tab's feed rows via their
           existing stable row key (buildFeedRows above), so a genuinely NEW
           row mounts-and-plays this once; an existing row that merely shifts
           position on a re-sort is REUSED by React, never replayed -- same
           "keyed list only replays on genuine mount" contract this file
           already documents for .hq-card-flip. */
        .hq-row-in { animation: hq-row-in-slide 0.35s ease-out; }
        @keyframes hq-row-in-slide { 0% { transform: translateY(-6px); opacity: 0; } 100% { transform: translateY(0); opacity: 1; } }

        /* Animated Beam (https://21st.dev/@dillionverma/components/animated-beam,
           "Animated Beam": a beam of light traveling along a path between two
           connected elements, showing an active integration) -- scaled down
           to a short traveling dot in the gap between two ADJACENT crew
           cards, shown only while lib/personas.ts's computeHandoffs reports
           that exact handoff status OK (a real, fresh handoff -- see
           handoffFresh in the component body below), remounted via a
           changing React key whenever the handoff transitions fresh, same
           replay-via-key convention as .hq-shine/.hq-focus-glow above.
           transform:translateY + opacity only. */
        .hq-handoff-beam { position: relative; height: 12px; width: 2px; margin: 0 auto; background: rgba(122,217,255,0.15); pointer-events: none; }
        .hq-handoff-beam::after { content: ""; position: absolute; left: -2px; top: 0; width: 6px; height: 6px; border-radius: 999px; background: #7ad9ff; animation: hq-handoff-travel 1.4s ease-in-out infinite; }
        @keyframes hq-handoff-travel { 0% { transform: translateY(-2px); opacity: 0; } 30% { opacity: 1; } 70% { opacity: 1; } 100% { transform: translateY(10px); opacity: 0; } }

        /* A "live now" dot on the RUNS AS row -- reuses hq-pulse-glow's own
           opacity-breathing keyframe (already defined above, already
           TV-safe) rather than a 4th separate credited concept; only ever
           rendered while role.liveNow is true. */
        .hq-live-dot { display: inline-block; width: 6px; height: 6px; border-radius: 999px; background: #22ff88; box-shadow: none; animation: hq-pulse-glow 1.1s ease-in-out infinite; }
      `}</style>

      {/* Controls legend (UX-1 U1, 2026-09-14, reworked from LIVE-1 item 1's
          original mount-timer version -- ultra tier only, the TV kiosk has
          no OrbitControls/keyboard camera to explain, see Scene.tsx's own
          `ultra`-gated CameraRig). Bottom-CENTRE of the CANVAS area (not the
          full viewport) -- this wrapper div is already width-constrained to
          the same `calc(100% - HUD_RIGHT_COLUMN_WIDTH)` the canvas itself
          uses (UltraCanvasRoot.tsx), so `left:50%` centers against that same
          box, matching every other measurement in this wrapper (see the
          coordinate-system note this file already carries elsewhere).
          bottom:210 clears the SLIM single-line trading strip U8 (2026-09-14)
          reduced the bottom stack to (the tall multi-row event feed that used
          to sit here moved into the right panel's Activity tab -- see U8's
          own comment on the bottom-stack wrapper below). REAL-CAPTURE BUG
          FOUND AND FIXED THIS PASS (ux1-u0u1-1642.png, pre-U8): at the OLD
          bottom:195 with no explicit z-index, this legend is a DOM sibling
          that paints BEFORE the bottom-stack div in source order, so with no
          z-index on either side the later (bottom-stack) element wins the
          paint order wherever the two overlap -- with the event feed able to
          grow up to FEED_MAX_ROWS(12) rows, 195 was tuned against a
          long-retired "max 3-line ticker" and the legend was invisible,
          painted UNDER the feed, in that real capture. `zIndex` below makes
          this correct regardless of the sibling's height (never rely on DOM
          order for stacking again). Visibility is state-driven (legendVisible,
          see its own effect above) instead of a replayed CSS @keyframes
          animation -- opacity/pointerEvents toggle, with a transition only
          when motion is allowed (reducedMotion contract, same as every other
          animated piece of this file). "Glass panel" reading (external-
          reference convention #1) via a translucent background + a thin
          border, no blur/backdrop-filter -- this codebase's own standing
          TV-compositor rule (see the .hq-beam/.hq-shine style block above)
          applies regardless of tier. */}
      {tier === "ultra" && (
        <div
          // HUD-OBSTACLE (2026-09-15): world labels colliding with this bar
          // (real capture plaque-overview.png, read at 1:1: a live-agent
          // bubble + the SPY 0DTE lane label both sit under it at the
          // default overview cam) is the bug this attribute fixes --
          // LabelDeclutterManager.tsx queries every `data-hq-obstacle` node
          // once per resolve tick and nudges any label off it, WITHOUT ever
          // moving this bar itself. Only tagged while actually visible
          // (legendVisible fully hides it via opacity:0 -- see the "consider
          // auto-hiding" note in this file's own header) so a faded-out
          // legend never blocks a label from resting under its old spot.
          data-hq-obstacle={legendVisible ? "help-bar" : undefined}
          style={{
            position: "absolute", left: "50%", bottom: 210, transform: "translateX(-50%)",
            zIndex: 11,
            color: "#cfe9ff", fontSize: 14, fontFamily: HUD_FONT, whiteSpace: "nowrap",
            background: "rgba(3,4,10,0.6)", border: "1px solid rgba(122,217,255,0.28)",
            padding: "6px 18px", borderRadius: 999,
            opacity: legendVisible ? 1 : 0,
            pointerEvents: "none",
            transition: reducedMotion ? "none" : "opacity 0.4s ease",
          }}
        >
          Drag orbit &middot; Wheel zoom &middot; Right-drag pan &middot; 1&ndash;7 desks &middot; 0 overview &middot; H hide HUD &middot; ? help
        </div>
      )}

      {/* UX-1 U5 (2026-09-14): auto-orbit resume hint, 3s -- see
          autoOrbitResumedAtMs's own effect comment above for the store this
          reads and why Scene.tsx's one-line call site isn't wired yet.
          Reuses the legend's exact spot (bottom:210, centered, zIndex:11,
          same glass-panel styling) rather than a second hand-picked
          position -- the two are mutually exclusive in practice (auto-orbit
          only resumes after 45s of total idle, by which point the legend's
          own 8s-after-first-input fade has long since finished in every
          realistic session), so there is no real overlap case to design
          around. */}
      {tier === "ultra" && showAutoOrbitHint && (
        <div
          style={{
            position: "absolute", left: "50%", bottom: 210, transform: "translateX(-50%)",
            zIndex: 11,
            color: "#cfe9ff", fontSize: 14, fontFamily: HUD_FONT, whiteSpace: "nowrap",
            background: "rgba(3,4,10,0.6)", border: "1px solid rgba(122,217,255,0.28)",
            padding: "6px 18px", borderRadius: 999,
            pointerEvents: "none",
          }}
        >
          auto-orbit &middot; move the mouse to take control
        </div>
      )}

      {/* Meteors drifting behind the title (decorative only, z-index below
          the text) -- trimmed from 5 to 3 (2026-09-13, Company Mode step 5)
          to make room in the animated-DOM-element budget (cap 24) for the
          roster panel's per-GREEN-row pulses below. */}
      <div style={{ position: "absolute", top: 0, left: 0, width: 260, height: 70, overflow: "hidden" }}>
        {[0, 2.5, 5].map((delay, i) => (
          <span key={i} className="hq-meteor" style={{ left: 20 + i * 48, animationDelay: `${delay}s`, animationDuration: "6s" }} />
        ))}
      </div>

      {/* Top-left: title + ET clock + mode badge. 10-foot-readability sizing
          (2026-09-13, J: "it's just like text ... no animations"): mode
          badge bumped to ~34px per spec; title/clock bumped alongside it so
          the badge doesn't outsize its own header. */}
      {/* HUD-OBSTACLE (2026-09-15): the title/clock/mode-badge cluster is
          the "HUD title block top-left" obstacle named in the task's own
          evidence read -- see LabelDeclutterManager.tsx's own header for
          how `data-hq-obstacle` nodes get read. */}
      <div data-hq-obstacle="title-block" style={{ position: "absolute", top: 14, left: 20, display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ color: "#dff3ff", fontSize: 34, fontWeight: 800, letterSpacing: 1.5, textShadow: "0 0 14px rgba(122,217,255,0.6)" }}>
          GAMMA HQ
        </span>
        {/* LIVE-1 item 3 (2026-09-14) follow-up: a text-shadow, not a color
            change -- the sky behind this overlay now legitimately brightens
            by day (SkyDome.tsx), and this medium-gray clock text had
            nothing else to keep it readable against that brighter
            background (the title next to it already had its own glow
            shadow). A soft dark halo keeps it legible against ANY sky
            brightness, day or night, without changing its look at night. */}
        <span style={{ color: "#7f93b0", fontSize: 20, fontVariantNumeric: "tabular-nums", textShadow: "0 1px 4px rgba(0,0,0,0.7)" }}>{etClock}</span>
        <span
          style={{
            fontSize: 22, fontWeight: 700, padding: "3px 16px", borderRadius: 999,
            background: gaming ? "rgba(255,176,32,0.18)" : "rgba(34,255,136,0.14)",
            color: gaming ? "#ffb020" : "#22ff88",
            border: `2px solid ${gaming ? "#ffb020" : "#22ff88"}`,
          }}
        >
          {gaming ? "GPU RESERVED" : `mode: ${mode}`}
        </span>
        {/* GPU-YIELD (queue item e): a second, independent chip -- gaming
            and brain-busy are different causes (J playing a game vs. the
            local brain mid-inference) and can be told apart, so this never
            collapses into the mode chip above. Only rendered when NOT
            already gaming (gaming's own pause/chip already covers "HQ is
            not rendering right now" and takes visual priority). */}
        {!gaming && brainBusy && (
          <span
            style={{
              fontSize: 22, fontWeight: 700, padding: "3px 16px", borderRadius: 999,
              background: "rgba(122,217,255,0.16)", color: "#7ad9ff", border: "2px solid #7ad9ff",
            }}
          >
            brain thinking -- HQ paused
          </span>
        )}
      </div>

      {/* UX-1 U0 (2026-09-14): "is it working?" instrument, directly under
          the title/clock row (top:14 row measures ~41px tall at its 34px
          title size -- top:56 clears it with a small margin). Renders on
          BOTH tiers (HARD RULES: "TV tier: legend/tooltips off, U0 line
          on") -- this div is NOT inside a `tier === "ultra"` gate, unlike
          the legend below. Small/muted by design: a status line, not a
          headline -- see buildHqBuildLine's own header comment for the
          server-fact contract it renders. */}
      <div
        style={{
          position: "absolute", top: 56, left: 20, maxWidth: 520,
          color: "#5c7aa0", fontSize: 13, fontFamily: HUD_FONT,
          fontVariantNumeric: "tabular-nums", textShadow: "0 1px 4px rgba(0,0,0,0.7)",
          whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis",
        }}
      >
        {buildHqBuildLine(data?.build)}
      </div>

      {/* Non-kiosk only: Home link, slim */}
      {!kiosk && (
        <div style={{ position: "absolute", top: 16, right: 20, pointerEvents: "auto", display: "flex", alignItems: "center", gap: 14 }}>
          <Link href="/" style={{ color: "#7f93b0", fontSize: 13, textDecoration: "none" }}>
            &larr; Home
          </Link>
        </div>
      )}

      {/* Top-right: presence lamp (kiosk) */}
      {kiosk && (
        <div style={{ position: "absolute", top: 18, right: 20, display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              width: 9, height: 9, borderRadius: 999,
              background: present ? "#22ff88" : "#3a4560",
              boxShadow: present ? "0 0 8px #22ff88" : "none",
            }}
          />
          <span style={{ color: "#7f93b0", fontSize: 13 }}>{present ? "J is here" : "J is away"}</span>
        </div>
      )}

      {/* UX-1 U8 (2026-09-14, coordinator-relayed J verdict: "the giant wall
          of text eating the bottom third of my screen -- the activity log --
          I don't want that... keep the main page for the trading area").
          The trading strip + R3 event feed that used to anchor here both
          MOVED into the right panel (trading strip docked in its pinned
          header, activity feed in its own tab) -- see that panel's own
          comment below. Nothing overlays the world here any more except
          in-world bubbles/signs (Scene.tsx) and this file's own legend/
          tooltips, per J's literal ask. */}

      {/* Bottom-right corner: perf + synced status. Pass G (2026-09-13,
          coordinator item 4): "on the ultra tier show THIS device's
          numbers; the TV line only on the TV tier".
          World-2 coordinator review (2026-09-14, W6 mechanism, verified on
          a real capture showing "This device: 2 fps · 524x768" on J's own
          2560x1440 session): `data.perfOther` was the shared ledger's
          latest NON-TV row -- any OTHER tab (a builder's hidden Browser-
          pane preview, throttled to ~2fps by the browser while hidden)
          could out-write it, so "This device" was never actually
          guaranteed to be this device. Fixed at the source: `livePerf`
          reads lib/hq-live-perf.ts's own client-side store, published
          every ~1s directly from PerfReporter.tsx's real gl.info in THIS
          mounted Canvas -- never the ledger, never another tab's number.
          The `(capped)` suffix reads PerfReporter's own live `capped` flag
          (UltraCanvasRoot.tsx#FrameRateCap's state) directly, satisfying
          the coordinator's own literal "PerfReporter shows the cap" ask.
          The "TV: ..." line is UNCHANGED -- still `data.perf`, the
          ledger's own TV-UA-matched row (lib/hq.ts#readLatestHqPerf's
          existing isTvUa() split), which was never the broken half of
          this -- a real physical TV has no other tab to be confused with. */}
      {/* HUD-OBSTACLE (2026-09-15): the "perf/Synced text bottom-right"
          obstacle named in the task's own evidence read. */}
      <div data-hq-obstacle="perf-corner" style={{ position: "absolute", bottom: 8, right: 12, textAlign: "right" }}>
        {tier === "ultra" ? (
          <>
            {livePerf && (
              <div style={{ color: "#5c7aa0", fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
                This device: {livePerf.fps} fps{livePerf.capped ? " (capped)" : ""} · {livePerf.w}x{livePerf.h} · {livePerf.calls} calls · {livePerf.tris} tris
              </div>
            )}
            {data?.perf && (
              <div style={{ color: "#3f4f68", fontSize: 11, fontVariantNumeric: "tabular-nums" }}>
                TV: {data.perf.fps} fps · {data.perf.w}x{data.perf.h} · {data.perf.calls} calls
              </div>
            )}
          </>
        ) : (
          data?.perf && (
            <div style={{ color: "#5c7aa0", fontSize: 12, fontVariantNumeric: "tabular-nums" }}>
              TV: {data.perf.fps} fps · {data.perf.w}x{data.perf.h} · {data.perf.calls} calls
            </div>
          )
        )}
        <span style={{ color: "#4a5a78", fontSize: 11 }}>{syncedText}</span>
      </div>
    </div>
    )}

    {/* Right column (Pass G, 2026-09-13; restructured UX-1 U8/U6,
        2026-09-14). Now TWO stacked flex regions instead of one scrolling
        blob: a PINNED header (trading strip + NEEDS-J + tab strip, natural
        height, never scrolls) and a scrollable BODY below it (Crew or
        Activity, whichever tab is active) -- U6's own "pin the header,
        scroll the body" ask, and the architecture that makes U8's tab
        strip possible without the panel growing unboundedly tall. Gated on
        `hudVisible` (LIVE-1 item 1) same as the left column above. */}
    {hudVisible && (
    <div
      // HUD-OBSTACLE (2026-09-15): the "right-side panel ~x >= 1420"
      // obstacle named in the task's own evidence read -- this whole fixed
      // column, not just its content, since nothing behind it (a lane label
      // that would rest under the panel) can ever be seen anyway.
      data-hq-obstacle="right-panel"
      style={{
        position: "fixed", top: 0, right: 0, bottom: 0, width: HUD_RIGHT_COLUMN_WIDTH,
        background: "#03040a", borderLeft: "1px solid rgba(122,217,255,0.15)",
        zIndex: 10, display: "flex", flexDirection: "column", overflow: "hidden",
      }}
    >
      {/* Pinned header: trading strip + NEEDS-J + tab strip. flexShrink:0 --
          natural content height, never part of the scrolling body below. */}
      <div style={{ flexShrink: 0, display: "flex", flexDirection: "column", gap: 10, padding: "14px 20px 10px", pointerEvents: "none" }}>
        {/* UX-1 U8 (2026-09-14): trading status strip, RELOCATED here from
            the world overlay (was the "giant wall of text... bottom third
            of my screen" J flagged, alongside the event feed) and shrunk to
            <=28px tall per the coordinator's own literal cap (was ~34px at
            fontSize 20/padding "5px 20px" -- too tall for the header budget
            AND too wide a font for this column's narrower 500px width
            anyway). Same buildTradingStrip() decision tree, just smaller. */}
        {(() => {
          const strip = buildTradingStrip(data?.trading);
          const c = TRADING_STRIP_COLOR[strip.color];
          return (
            <div
              style={{
                background: "rgba(3,4,10,0.75)", border: `1px solid ${c}55`, borderRadius: 6,
                padding: "4px 10px", display: "flex", alignItems: "center", gap: 7, height: 20, boxSizing: "content-box",
              }}
            >
              <span style={{ width: 7, height: 7, borderRadius: 999, flexShrink: 0, background: c, boxShadow: `0 0 5px ${c}` }} />
              <span style={{ color: "#dff3ff", fontSize: 13, fontFamily: HUD_FONT, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                {strip.text}
              </span>
            </div>
          );
        })()}

        {/* NEEDS-J card (Company Mode step 7, 2026-09-13): read-only amber
            alert aggregating discord-outbox mentions of J, pending conductor
            proposals, and FABLE-ESCALATION queue lines -- see
            lib/hq.ts#readBlocked. Newest 3 of up to 8; hidden entirely when
            there's nothing blocked so it never occupies space on a clean day.
            U6: pinned in the header (never scrolls out of view). */}
        {blockedItems.length > 0 && (
          <div
            style={{
              background: "rgba(40,26,0,0.75)", border: "1px solid #ffb020", borderRadius: 8,
              padding: "8px 14px", flexShrink: 0,
            }}
          >
            <div style={{ color: "#ffb020", fontSize: 18, fontWeight: 800, letterSpacing: 0.5, marginBottom: 4 }}>
              NEEDS J ({blockedItems.length})
            </div>
            {blockedItems.slice(0, 3).map((item, i) => (
              <div key={`${item.source}-${item.ts ?? i}`} style={{ fontSize: 14, color: "#ffe0a3", marginTop: i === 0 ? 0 : 6, lineHeight: 1.3 }}>
                <span style={{ color: "#ffb020", fontWeight: 700 }}>[{BLOCKED_SOURCE_LABEL[item.source] ?? item.source}]</span>{" "}
                {item.text}
                <span style={{ color: "#c99457" }}> &middot; {item.age}</span>
              </div>
            ))}
          </div>
        )}

        {/* PANEL-2 (2026-09-14): the TRUTH header -- J's verbatim question
            ("is it running on my pc? do i really have this many active
            agents on my pc?") answered as DATA, not a sentence: role count
            and live-process count are two visually distinct numbers (never
            conflated into one), so "7 roles" reading next to "44
            processes" is itself the answer to "are those the same thing"
            -- roles are NOT agents. Both numeric pieces use the Number
            Ticker treatment (tweens on change instead of snapping); the
            rest is plain text, server-computed by lib/hq-runtime.ts, never
            invented here. */}
        {runtime && (
          <div
            style={{
              fontSize: 12.5, color: "#8296b3", lineHeight: 1.4, fontVariantNumeric: "tabular-nums",
              background: "rgba(3,4,10,0.55)", border: "1px solid rgba(122,217,255,0.15)", borderRadius: 6,
              padding: "5px 9px",
            }}
          >
            <span style={{ color: "#dff3ff", fontWeight: 800 }}>
              <NumberTicker value={runtime.roles.length} reducedMotion={reducedMotion} />
            </span>{" "}
            role{runtime.roles.length === 1 ? "" : "s"} (not {runtime.roles.length === 1 ? "an agent" : "agents"}) ·{" "}
            <span style={{ color: runtime.processes ? "#7ad9ff" : "#ffb020", fontWeight: 800 }}>
              {runtime.processes ? <NumberTicker value={trackedProcessTotal(runtime.processes)} reducedMotion={reducedMotion} /> : "?"}
            </span>{" "}
            live process{trackedProcessTotal(runtime.processes) === 1 ? "" : "es"} on {runtime.hostname}
            {runtime.processes && processBreakdown(runtime.processes).length > 0 && (
              <> ({processBreakdown(runtime.processes).map((r) => `${r.label} ${r.n}`).join(" · ")})</>
            )}
            {runtime.error && <span style={{ color: "#ffb020" }}> · {runtime.error}</span>}
            {/* Coordinator correction (2026-09-14): "3 of 7 roles have
                their task switched off" -- computed live from
                role.heldByQuietMode (lib/hq-runtime.ts), never a fixed
                example number. Only rendered when the count is nonzero --
                a clean evening with nothing held gets no false alarm. */}
            {(() => {
              const heldCount = runtime.roles.filter((r) => r.heldByQuietMode).length;
              if (heldCount === 0) return null;
              return (
                <>
                  <br />
                  <span style={{ color: "#ffb020", fontWeight: 800 }}>
                    <NumberTicker value={heldCount} reducedMotion={reducedMotion} />
                  </span>{" "}
                  of{" "}
                  <span style={{ fontWeight: 800 }}>
                    <NumberTicker value={runtime.roles.length} reducedMotion={reducedMotion} />
                  </span>{" "}
                  role{heldCount === 1 ? "" : "s"} held by quiet mode
                  {runtime.quietModeUntilEt ? ` until ${runtime.quietModeUntilEt} ET` : ""} (J's evening blackout, not a fault)
                </>
              );
            })()}
            <br />
            brain: {runtime.brain.model ?? "no model"} {runtime.brain.gpu ? "local GPU" : "local"} ·{" "}
            <span style={{ color: runtime.brain.state === "running" ? "#22ff88" : runtime.brain.state === "yielding" ? "#ffb020" : "#6a86b8", fontWeight: 700 }}>
              {runtime.brain.state}
            </span>
            {runtime.brain.reason && <span style={{ color: "#5c7aa0" }}> ({truncateOneLine(runtime.brain.reason, 60)})</span>}
          </div>
        )}

        {/* UX-1 U8: "Crew | Activity" tab strip -- the sim-game tab
            convention J offered as an option (over a stacked section),
            chosen because the alternative (7 crew cards + up to
            FEED_MAX_ROWS activity rows stacked) would make the panel very
            long to scroll, working against J's actual complaint ("too much
            on screen"). Pinned in the header -- it IS the navigation for
            the scrollable body below it. */}
        <div style={{ display: "flex", gap: 4, pointerEvents: "auto" }}>
          {(["crew", "activity", "learn"] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setActivePanelTab(t)}
              aria-pressed={activePanelTab === t}
              style={{
                flex: 1, padding: "6px 0", fontSize: 13, fontWeight: 700, letterSpacing: 0.4,
                textTransform: "uppercase", fontFamily: HUD_FONT, cursor: "pointer",
                border: "none", borderRadius: 6,
                color: activePanelTab === t ? "#03040a" : "#7ad9ff",
                background: activePanelTab === t ? "#7ad9ff" : "rgba(122,217,255,0.1)",
              }}
            >
              {t === "crew"
                ? "Crew"
                : t === "activity"
                  ? `Activity${feedRows.length > 0 ? ` (${feedRows.length})` : ""}`
                  // PANEL-3: count badge = learned rows today (lib/hq-learn.ts#HqLearn.learned).
                  : `Learn${learn && learn.learned.length > 0 ? ` (${learn.learned.length})` : ""}`}
            </button>
          ))}
        </div>
      </div>

      {/* Scrollable body -- flex:1 + minHeight:0 is the standard "flex
          child that actually scrolls instead of stretching its parent"
          pair; without minHeight:0 a flex item never shrinks below its own
          content's natural height, which is exactly what made the OLD
          single-region panel cut the Treasurer card at a 1440px viewport
          (J's own literal bug report, U6) -- the whole column just grew
          past the viewport instead of scrolling. Thin/momentum scrollbar
          via .hq-panel-scroll (defined in the shared <style> block above). */}
      <div className="hq-panel-scroll" style={{ flex: 1, minHeight: 0, overflowY: "auto", padding: "10px 20px 20px", pointerEvents: "none" }}>
      {activePanelTab === "crew" && personas.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 10, fontVariantNumeric: "tabular-nums" }}>
          {personas.map((p, i) => {
            const color = personaStatusColor(p.status);
            const audit = auditByName.get(p.name);
            const auditColor = auditVerdictColor(audit?.verdict);
            const auditTitle = audit
              ? `Audit ${audit.verdict}: ${audit.checks.works.evidence}`
              : "Audit: not yet run for this persona";
            const pill = deriveCrewPill(p, nowMs);
            const pillColor = CREW_PILL_COLOR[pill.kind];
            const nowLine = crewNowLine(p);
            const lastLine = crewLastLine(p);
            const nextLine = crewNextLine(p, nowMs);
            // PANEL-2 (2026-09-14): "RUNS AS" row -- see this file's own
            // buildRunsAsLine() header comment. `role` is undefined only
            // when the runtime instrument itself failed this poll
            // (lib/hq-runtime.ts fails open, never throws) or for a
            // persona name it doesn't track -- buildRunsAsLine handles
            // that honestly ("runtime unknown") rather than guessing.
            const role = roleByName.get(p.name);
            const runsAsLine = buildRunsAsLine(role, runtime?.brain.model ?? null, p.lastFireISO);
            // R2: keys "1".."7" index cameraPresets[0..6] = [Gamma, ...6
            // personas] in Scene.tsx's own fixed order -- IDENTICAL to this
            // `personas` array's own order (both come from collectCompany()).
            // A synthetic window keydown is the only integration point --
            // Scene.tsx's listener is not edited (not this builder's file).
            const flyToDesk = () => window.dispatchEvent(new KeyboardEvent("keydown", { key: String(i + 1) }));
            // U6: this card's own glow overlay only mounts while ITS index
            // is the currently-focused one -- see focusEvent's own effect
            // comment above for why `id` (not just index) is the key.
            const glowing = focusEvent?.index === i;
            // PANEL-2: Animated Beam connector -- only Pilot->Analyst and
            // Analyst->Chef are BOTH real computeHandoffs() pairs AND
            // adjacent in this fixed roster render order (see handoffFresh's
            // own comment above); every other real handoff involves a
            // non-card node ("Premarket", "_LEADERBOARD", "J ratification")
            // that has no card to draw a line to.
            const beamAfter =
              p.name === "Pilot" && handoffFresh("Pilot", "Analyst") ? "Pilot-Analyst"
              : p.name === "Analyst" && handoffFresh("Analyst", "Chef") ? "Analyst-Chef"
              : null;
            return (
              <Fragment key={p.name}>
              <div
                ref={(el) => {
                  if (el) cardRefs.current.set(p.name, el);
                  else cardRefs.current.delete(p.name);
                }}
                className={`hq-crew-card${p.status === "GREEN" ? " hq-pulse" : ""}`}
                role="button"
                tabIndex={0}
                aria-label={`Fly to ${p.name}'s desk`}
                onClick={flyToDesk}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") { e.preventDefault(); flyToDesk(); }
                }}
                // UX-1 U3 (2026-09-14): "hovering a crew card pulses that
                // persona's own sign in the world" -- see
                // lib/hq-hover-persona.ts's own header for the store this
                // publishes to and why (Scene.tsx's own consumption of it,
                // rendering the actual pulse, is not wired yet -- gated
                // behind Scene.tsx's current cross-builder freeze this pass;
                // this trigger half is harmless to ship ahead of it, same
                // "front the reader/trigger, wire the other side later"
                // shape as U5's reportAutoOrbitResumed). onMouseLeave (not
                // onPointerLeave) matches this card's own existing plain DOM
                // event handlers above (onClick/onKeyDown), not a mixed
                // event-API card.
                onMouseEnter={() => setHoveredPersonaIndex(i)}
                // Unconditional clear (not a "only if it's still me" guard,
                // unlike focusEvent's index check elsewhere in this file):
                // these cards are non-overlapping siblings in a plain block
                // list, so the DOM's own enter/leave ordering guarantees
                // this card's leave fires before any OTHER card's enter --
                // there is no race to guard against here.
                onMouseLeave={() => setHoveredPersonaIndex(null)}
                style={{
                  position: "relative", background: "rgba(3,4,10,0.93)", border: `1px solid ${color}55`,
                  borderRadius: 10, padding: "10px 12px", cursor: "pointer",
                  pointerEvents: "auto", opacity: pill.kind === "GHOST" ? 0.72 : 1,
                }}
              >
                {/* U6: 2s focus glow -- `key={focusEvent.id}` remounts (and so
                    replays) this CSS animation every focus event, including a
                    re-focus of the SAME persona, without any JS timer (see
                    the .hq-focus-glow keyframes in the shared <style> block).
                    reducedMotion: skip the animated ring entirely, a static
                    border-color bump on the card itself would be the
                    alternative but isn't worth the extra branch here -- the
                    scroll-into-view (already instant under reducedMotion)
                    is the part carrying the real information. */}
                {glowing && !reducedMotion && <span key={focusEvent.id} className="hq-focus-glow" />}
                <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
                  {/* UX-1 U1 (2026-09-14): hotkey digit, ultra tier only --
                      the keyboard 1-7 fly-to itself is ultra-only
                      (Scene.tsx's `ultra`-gated CameraRig listener), so
                      showing a digit that does nothing on the TV kiosk would
                      be a lie, not a hint. Same i+1 the card's own flyToDesk
                      already dispatches below -- one index, not a second
                      mapping to drift out of sync. */}
                  {tier === "ultra" && (
                    <span
                      aria-hidden="true"
                      style={{
                        width: 18, height: 18, borderRadius: 4, flexShrink: 0, marginTop: 1,
                        display: "flex", alignItems: "center", justifyContent: "center",
                        fontSize: 11, fontWeight: 700, fontFamily: HUD_FONT,
                        color: "#7ad9ff", background: "rgba(122,217,255,0.12)",
                        border: "1px solid rgba(122,217,255,0.4)",
                      }}
                    >
                      {i + 1}
                    </span>
                  )}
                  <span
                    style={{
                      width: 32, height: 32, borderRadius: 8, flexShrink: 0,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      fontSize: 17, background: `${p.color}2e`, border: `1px solid ${p.color}99`,
                    }}
                  >
                    {p.emoji}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <span style={{ color: "#dff3ff", fontSize: 19, fontWeight: 800, letterSpacing: 0.2, whiteSpace: "nowrap" }}>
                        {p.name}
                      </span>
                      <span
                        title={auditTitle}
                        style={{
                          pointerEvents: "auto", marginLeft: "auto", fontSize: 13, fontWeight: 800,
                          color: "#03040a", background: auditColor, borderRadius: 4,
                          padding: "1px 5px", flexShrink: 0, letterSpacing: 0.5,
                        }}
                      >
                        {audit ? audit.verdict[0] : "?"}
                      </span>
                    </div>
                    {/* U6: compact mode (viewport height < 1000px) drops
                        this role sub-line -- the goal is a real "2 lines"
                        card (name row + one status line), not a slightly
                        shorter version of the full card. */}
                    {!compactPanel && <div style={{ color: "#7f93b0", fontSize: 12.5, lineHeight: 1.3, marginTop: 1 }}>{p.role}</div>}
                  </div>
                </div>

                {compactPanel ? (
                  // U6 compact mode: ONE combined status line replaces the
                  // pill+reason row AND the now/last/next block below --
                  // pill.kind for the at-a-glance color/word, then whichever
                  // of now/last/next actually has content (in that priority
                  // order -- "what's happening" beats "what happened" beats
                  // "what's next"), never all three stacked.
                  <div style={{ marginTop: 6, fontSize: 13, color: "#9fb3cc", lineHeight: 1.35, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                    <span style={{ fontWeight: 800, color: pillColor }}>{pill.kind}</span>{" "}
                    {nowLine ?? lastLine ?? nextLine}
                  </div>
                ) : (
                <>
                <div style={{ marginTop: 8, display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                  <span
                    style={{
                      fontSize: 12, fontWeight: 800, textTransform: "uppercase", letterSpacing: 0.9,
                      padding: "2px 8px", borderRadius: 999, flexShrink: 0,
                      color: "#03040a", background: pillColor,
                    }}
                  >
                    {pill.kind}
                  </span>
                  <span style={{ fontSize: 13.5, color: "#9fb3cc", lineHeight: 1.35 }}>{pill.reason}</span>
                </div>

                {nowLine && (
                  // Coordinator correction (2026-09-14): Chef's now-line was
                  // getting hard-truncated (an ellipsis mid-number). Wraps
                  // to 2 lines instead via a webkit line-clamp -- standard
                  // in the Chromium/Edge this dashboard targets (both the
                  // ultra tier and the TV kiosk) -- rather than a 1-line
                  // ellipsis cutoff.
                  <div
                    style={{
                      fontSize: 14, color: "#cfe9ff", marginTop: 6, lineHeight: 1.35,
                      display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
                      overflow: "hidden",
                    }}
                  >
                    <span style={{ color: "#5c7aa0", fontWeight: 700 }}>now </span>{nowLine}
                  </div>
                )}
                <div style={{ fontSize: 13, color: "#8296b3", marginTop: 4, lineHeight: 1.35, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                  <span style={{ color: "#5c7aa0", fontWeight: 700 }}>last </span>{lastLine}
                </div>
                <div style={{ fontSize: 13, color: "#6c81a0", marginTop: 2, lineHeight: 1.35 }}>
                  <span style={{ color: "#5c7aa0", fontWeight: 700 }}>next </span>{nextLine}
                </div>
                {/* PANEL-2 (2026-09-14): "RUNS AS" row -- J's verbatim ask
                    ("what agent is it? is it running on my pc?") answered
                    per-card. Live dot (hq-live-dot, only while
                    role.liveNow) is the ONLY animation on this row --
                    everything else is plain text, server-computed. */}
                <div style={{ fontSize: 12.5, color: "#5c86a8", marginTop: 4, lineHeight: 1.35, display: "flex", alignItems: "center", gap: 5 }}>
                  <span style={{ color: "#46607e", fontWeight: 700, textTransform: "uppercase", letterSpacing: 0.4, fontSize: 10.5 }}>runs as</span>
                  {role?.liveNow && <span className={reducedMotion ? undefined : "hq-live-dot"} style={reducedMotion ? { width: 6, height: 6, borderRadius: 999, background: "#22ff88", display: "inline-block" } : undefined} title="plausibly mid-fire right now" />}
                  <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={role?.evidence}>{runsAsLine}</span>
                </div>
                </>
                )}
              </div>
              {beamAfter && !reducedMotion && !gaming && <div className="hq-handoff-beam" key={beamAfter} aria-hidden="true" />}
              </Fragment>
            );
          })}
        </div>
      )}

      {/* UX-1 U8: Activity tab -- the SAME merged feed (buildFeedRows above,
          crew-events.jsonl + the motion-diff ticker, unchanged sources/
          logic) that used to sit as a fixed block under the world; now a
          normal scrollable list inside this panel's own scroll region
          (this div is just a content block, no independent overflow of its
          own) at 15px rows, per the coordinator's own spec. */}
      {activePanelTab === "activity" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 3, fontVariantNumeric: "tabular-nums" }}>
          {feedRows.length > 0 ? (
            feedRows.map((row, i) => {
              const showChip = i === 0 || feedRows[i - 1].actor?.name !== row.actor?.name;
              return (
                // PANEL-2 (2026-09-14): Animated List concept (see the
                // shared <style> block's own .hq-row-in comment) -- plays
                // ONLY on a genuine new mount of this row's stable
                // `key={row.key}` (buildFeedRows above), never on a reorder
                // of an existing row. Skipped entirely under reducedMotion.
                <div key={row.key} className={reducedMotion ? undefined : "hq-row-in"} style={{ display: "flex", alignItems: "center", gap: 7, padding: "3px 0" }}>
                  <span style={{ color: "#4fd6ff", fontSize: 12, flexShrink: 0, width: 36 }}>{row.tsEt}</span>
                  <span
                    style={{
                      width: 18, height: 18, borderRadius: 5, flexShrink: 0, fontSize: 11,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      visibility: showChip && row.actor ? "visible" : "hidden",
                      background: row.actor ? `${row.actor.color}33` : "transparent",
                      border: row.actor ? `1px solid ${row.actor.color}88` : "none",
                    }}
                  >
                    {row.actor?.emoji ?? ""}
                  </span>
                  <span style={{ color: "#9fd8ff", fontSize: 15, fontFamily: HUD_FONT, lineHeight: 1.35, minWidth: 0, overflowWrap: "break-word" }}>
                    {row.text}
                  </span>
                </div>
              );
            })
          ) : (
            <div style={{ color: "#7f93b0", fontSize: 15, fontFamily: HUD_FONT }}>No events yet this session.</div>
          )}
        </div>
      )}

      {/* PANEL-3 (2026-09-14): LEARN tab -- "i want this automated trading
          agent world to be self learning, improving, and awesome as fuck"
          (J's verbatim mandate, 2026-09-14 ~18:25 ET). Real rows only, from
          lib/hq-learn.ts's own fail-open reader -- see that module's header
          for the 6 source files and why each row's numbers are the
          producer's own text, never re-derived here. Same Animated List
          row-in treatment as the Activity tab above (keyed so a genuinely
          NEW row plays the mount animation; a reorder never replays it).
          Compact mode (<1000px, same `compactPanel` flag the Crew tab
          already uses) drops the freeze caption and caps rows at 3, per
          this task's own "top line + 3 rows" spec. */}
      {activePanelTab === "learn" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8, fontVariantNumeric: "tabular-nums" }}>
          {learn && (
            <div style={{ fontSize: 12.5, color: "#8296b3", lineHeight: 1.4 }}>
              today:{" "}
              <span style={{ color: "#dff3ff", fontWeight: 800 }}>
                {learn.verdictsToday.supported + learn.verdictsToday.refuted + learn.verdictsToday.testing}
              </span>{" "}
              verdict{(learn.verdictsToday.supported + learn.verdictsToday.refuted + learn.verdictsToday.testing) === 1 ? "" : "s"}{" "}
              ({learn.verdictsToday.supported} supported &middot; {learn.verdictsToday.refuted} refuted &middot; {learn.verdictsToday.testing} testing) &middot;{" "}
              <span style={{ color: "#dff3ff", fontWeight: 800 }}>{learn.settledMechanisms}</span>{" "}
              mechanism{learn.settledMechanisms === 1 ? "" : "s"} settled
              {learn.lastLearnedAtEt && <> &middot; last learned {learn.lastLearnedAtEt} ET</>}
              {learn.error && <span style={{ color: "#ffb020" }}> &middot; {learn.error}</span>}
            </div>
          )}
          {/* CLAUDE.md config-freeze note, quoted rather than re-derived:
              trading-path params are frozen to 2026-10-30, so today's
              learning can only move SHADOW/prereg/parking state -- never
              live sizing or exits. Static doctrine text (not server data),
              the same status as this file's own "MARKET CLOSED" strip
              label elsewhere -- dropped in compact mode to stay inside the
              "top line + 3 rows" budget. */}
          {!compactPanel && (
            <div style={{ fontSize: 11.5, color: "#5c7aa0", lineHeight: 1.3 }}>
              trading-path params frozen to 2026-10-30 &mdash; today&rsquo;s learning can only move SHADOW / prereg / parking state, never live sizing or exits
            </div>
          )}
          {(!learn || learn.learned.length === 0) ? (
            <div style={{ color: "#7f93b0", fontSize: 15, fontFamily: HUD_FONT, marginTop: 4 }}>
              nothing learned yet today &mdash; next Station fire {stationNextFire}
            </div>
          ) : (
            (compactPanel ? learn.learned.slice(0, 3) : learn.learned).map((row, i) => {
              const chip = personaChipForLearnedWho(row.who, personas);
              return (
                <div
                  key={`${row.when}-${row.who}-${i}`}
                  className={reducedMotion ? undefined : "hq-row-in"}
                  style={{ display: "flex", alignItems: "flex-start", gap: 7, borderBottom: "1px solid rgba(122,217,255,0.08)", paddingBottom: 7 }}
                >
                  <span style={{ color: "#4fd6ff", fontSize: 12, flexShrink: 0, width: 34, marginTop: 1 }}>{row.when}</span>
                  <span
                    title={row.who}
                    style={{
                      width: 18, height: 18, borderRadius: 5, flexShrink: 0, fontSize: 11, marginTop: 1,
                      display: "flex", alignItems: "center", justifyContent: "center",
                      background: `${chip.color}33`, border: `1px solid ${chip.color}88`,
                    }}
                  >
                    {chip.emoji}
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ color: "#cfe9ff", fontSize: 13.5, lineHeight: 1.35 }}>{row.what}</div>
                    <div style={{ color: "#6c81a0", fontSize: 12, lineHeight: 1.3, marginTop: 2 }}>{row.changed}</div>
                  </div>
                </div>
              );
            })
          )}
        </div>
      )}
      </div>
    </div>
    )}
    </>
  );
}

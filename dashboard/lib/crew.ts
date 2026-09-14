// CREW-2 (2026-09-14): pure presentation-layer derivation for the HQ crew
// panel (Hud.tsx's roster). Ground truth lives in lib/personas.ts
// (PersonaState -- status, quietReason, recentOutput, lastFireResult,
// deliverable, lastFireISO); this file turns that evidence into the 4
// on-screen pieces J's verdict asked for: a status pill WITH a reason, and
// now:/last:/next: lines. Zero fs access, zero fetch -- safe to import from
// either a server or client module (Hud.tsx uses it client-side).
//
// J's verdict (2026-09-14, verbatim): "the little chat for the people isn't
// really intuitive... why are they on here if they're not doing anything?"
// -- the whole point of this file is that a viewer never sees a bare color
// with no explanation, and never sees invented "busy" text for a persona
// that is genuinely idle by design (RTH-gated, weekly-only, etc).

import { rosterEvidenceText, truncateOneLine } from "@/components/hq/palette";
import type { PersonaState } from "./personas";

export type CrewPillKind = "WORKING" | "WAITING" | "YIELDING" | "GHOST";

export interface CrewPill {
  kind: CrewPillKind;
  reason: string;
}

const WORKING_FALLBACK_REASON = "active — no further detail on file";

/** Classifies PersonaState.quietReason into one of 4 pill kinds via the
 * prefix convention lib/personas.ts's own R4 doc comment establishes:
 * "no producer for " -> GHOST (structurally nothing produces this
 * deliverable), "yields " -> YIELDING (deliberately, scheduled-ly idle --
 * RTH window, Sunday-only, etc), any other non-null text -> WAITING (an
 * overdue-vs-cadence message or a "Gamma_X DISABLED" fault), null ->
 * WORKING (status is GREEN and evidence is fresh -- nothing to explain).
 * Pure and deterministic: same PersonaState in, same pill out. */
export function deriveCrewPill(p: PersonaState): CrewPill {
  const reason = p.quietReason;
  if (reason === null) {
    return { kind: "WORKING", reason: crewNowLine(p) ?? WORKING_FALLBACK_REASON };
  }
  if (reason.startsWith("no producer for")) return { kind: "GHOST", reason };
  if (reason.startsWith("yields")) return { kind: "YIELDING", reason };
  return { kind: "WAITING", reason };
}

/** "now:" line -- the current unit of work, ONLY meaningful while WORKING
 * (quietReason === null). A quiet persona has no "now", only a "last" and
 * a "next" -- showing a stale recentOutput next to a WAITING/YIELDING pill
 * would contradict the pill (exactly the "random text" J flagged). */
export function crewNowLine(p: PersonaState): string | null {
  if (p.quietReason !== null) return null;
  return p.recentOutput ? truncateOneLine(p.recentOutput, 72) : null;
}

function basename(filePath: string): string {
  const parts = filePath.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || filePath;
}

/** "last:" line -- "headline · file basename · age". Always shown
 * (unlike now:), since a persona always has SOME evidence to point at even
 * while quiet -- that's the whole "why quiet" contract R4 exists for. */
export function crewLastLine(p: PersonaState): string {
  const headline = truncateOneLine(p.lastFireResult, 46);
  const age = rosterEvidenceText(p.lastFireISO);
  return `${headline} · ${basename(p.deliverable.path)} · ${age}`;
}

// ─── "next:" line -- next scheduled fire HH:MM ET when derivable from the
//     persona's own real cadence, else "event-driven: <trigger>". Dispatch
//     is by NAME over the fixed 7-persona roster (the same closed set
//     lib/personas.ts's collectors already special-case by name) rather
//     than parsing the free-text `schedule` field, which is written for
//     humans and varies in wording persona to persona. `nowMs` is an
//     explicit param, never a bare Date.now() buried inside -- matches
//     this codebase's own pure-function-of-explicit-time convention (see
//     components/hq/palette.ts#computePurposefulWalk / dayNightFactor). ───

const WEEKDAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

function pad2(n: number): string {
  return String(n).padStart(2, "0");
}

function etNowParts(nowMs: number): { minuteOfDay: number; dayOfWeek: number } {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", weekday: "short", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(new Date(nowMs));
  const get = (t: string) => parts.find((x) => x.type === t)?.value ?? "";
  const hour = Number(get("hour")) % 24;
  const minute = Number(get("minute"));
  const dayOfWeek = WEEKDAY_NAMES.findIndex((w) => w.startsWith(get("weekday")));
  return { minuteOfDay: hour * 60 + minute, dayOfWeek: dayOfWeek < 0 ? 0 : dayOfWeek };
}

/** Next HH:MM ET a daily fire at `targetHH:targetMM` lands, honoring
 * `weekdaysOnly`. */
function nextDailyFireText(targetHH: number, targetMM: number, weekdaysOnly: boolean, nowMs: number): string {
  const { minuteOfDay, dayOfWeek } = etNowParts(nowMs);
  const target = targetHH * 60 + targetMM;
  const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5;
  const label = `${pad2(targetHH)}:${pad2(targetMM)} ET`;
  if ((!weekdaysOnly || isWeekday) && minuteOfDay < target) return `today ${label}`;
  let d = dayOfWeek;
  for (let i = 1; i <= 7; i++) {
    d = (d + 1) % 7;
    if (!weekdaysOnly || (d >= 1 && d <= 5)) return i === 1 ? `tomorrow ${label}` : `${WEEKDAY_NAMES[d]} ${label}`;
  }
  return label;
}

/** Next occurrence of a WEEKLY fire on `dayOfWeekTarget` (0=Sun) at
 * HH:MM ET. */
function nextWeeklyFireText(dayOfWeekTarget: number, targetHH: number, targetMM: number, nowMs: number): string {
  const { minuteOfDay, dayOfWeek } = etNowParts(nowMs);
  const target = targetHH * 60 + targetMM;
  const label = `${pad2(targetHH)}:${pad2(targetMM)} ET`;
  if (dayOfWeek === dayOfWeekTarget && minuteOfDay < target) return `today ${label}`;
  let daysAhead = (dayOfWeekTarget - dayOfWeek + 7) % 7;
  if (daysAhead === 0) daysAhead = 7;
  return daysAhead === 1 ? `tomorrow ${label}` : `${WEEKDAY_NAMES[(dayOfWeek + daysAhead) % 7]} ${label}`;
}

/** Rolling-interval next-fire estimate for a ~every-N-minute loop:
 * lastFireISO + intervalMin, formatted HH:MM ET, when that lands in the
 * future; "due now" once it's passed (the loop is between fires, about to
 * catch up); an honest event-driven fallback when there's no lastFireISO
 * to project from at all (never a fabricated clock time from nothing). */
function nextIntervalFireText(lastFireISO: string | null, intervalMin: number, triggerLabel: string, nowMs: number): string {
  if (!lastFireISO) return `event-driven: ${triggerLabel}`;
  const lastMs = Date.parse(lastFireISO);
  if (Number.isNaN(lastMs)) return `event-driven: ${triggerLabel}`;
  const nextMs = lastMs + intervalMin * 60_000;
  if (nextMs <= nowMs) return "due now";
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(new Date(nextMs));
  const hh = parts.find((p) => p.type === "hour")?.value ?? "??";
  const mm = parts.find((p) => p.type === "minute")?.value ?? "??";
  return `~${hh}:${mm} ET`;
}

/** "next:" line (R1). Real cadence facts per persona (mirrors what each
 * lib/personas.ts collector already knows about its own schedule --
 * intentionally NOT centralized into one shared table, matching how this
 * codebase already carries the same cadence facts independently in
 * CLAUDE.md / SCHEDULED-TASKS.md / company-roster.json without one being
 * "the" parser of another). */
export function crewNextLine(p: PersonaState, nowMs: number): string {
  switch (p.name) {
    case "Scout":
      return nextDailyFireText(5, 30, false, nowMs);
    case "Pilot": {
      const { minuteOfDay, dayOfWeek } = etNowParts(nowMs);
      const isWeekday = dayOfWeek >= 1 && dayOfWeek <= 5;
      const rth = isWeekday && minuteOfDay >= 9 * 60 + 30 && minuteOfDay < 15 * 60 + 55;
      return rth
        ? nextIntervalFireText(p.lastFireISO, 1, "Gamma_HeartbeatCore", nowMs)
        : nextDailyFireText(9, 30, true, nowMs);
    }
    case "Analyst":
      return nextDailyFireText(16, 45, true, nowMs);
    case "Treasurer":
      return nextWeeklyFireText(0, 16, 0, nowMs);
    case "Coach":
      return p.deliverable.exists
        ? nextIntervalFireText(p.lastFireISO, 30, "Gamma_Station", nowMs)
        : "event-driven: sectors.json first write (CREW-RIG)";
    case "Chef":
      return nextIntervalFireText(p.lastFireISO, 30, "Station loop score pass", nowMs);
    case "Gamma (Manager)":
      return nextIntervalFireText(p.lastFireISO, 30, "Gamma_Station", nowMs);
    default:
      return "event-driven";
  }
}

/** Pill background color by KIND -- a separate axis from personaStatusColor
 * (which still drives the card border/dot, unchanged): status says "is the
 * evidence fresh/healthy", kind says "what is this persona doing about it
 * right now". The two usually agree (WORKING~GREEN, WAITING~YELLOW) but can
 * diverge on purpose (a RED/error persona still shows a WAITING pill --
 * "something needs fixing" -- not a 5th color no one asked for). */
export const CREW_PILL_COLOR: Record<CrewPillKind, string> = {
  WORKING: "#22ff88",
  WAITING: "#ffb020",
  YIELDING: "#6a86b8",
  GHOST: "#5c6b85",
};

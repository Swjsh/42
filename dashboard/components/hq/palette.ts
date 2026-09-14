// Shared palette + small deterministic helpers for the /hq space-station
// scene. Colors are plain hex strings (three.js accepts them directly on
// `color`/`emissive` props) so this file has zero three.js RUNTIME
// dependency for EVERYTHING BELOW except makeMatcapTexture()/
// makeToonGradientTexture() near the bottom (HQ v4 look pass, 2026-09-13) --
// those two are the one deliberate exception (the style brief's own
// section 5 places them here). The `three` import itself is SSR-safe (it
// only references classes/constants, same as any other module import) --
// it's calling these two functions that needs a browser, which is why both
// throw loudly rather than run silently if invoked outside one.
import * as THREE from "three";

export const PALETTE = {
  space: "#03040a",
  fogColor: "#050914",
  hubCore: "#7ad9ff",
  hubRing: "#22d3ee",
  floor: "#0c1220",
  deskDark: "#141b2e",
  corridor: "#12203a",
  amberAlert: "#ffb020",
  gamingAmber: "#ffb020",
  planet: "#16324a",
  planetRim: "#4fd6ff",
  text: "#dff3ff",
  textDim: "#7f93b0",
  // HQ v4 look pass (2026-09-13, Direction A -- Tron/Blade-Runner cold-warm
  // contrast): the EXISTING amberAlert hex promoted to a deliberate second
  // hero hue used decoratively (sky-dome horizon glow, HUD scan tint) --
  // same value, a DIFFERENT role, so alert semantics and decoration never
  // share one lookup (same reasoning as PERSONA_STATUS_COLOR vs
  // HEALTH_COLOR below: never invent a new hex when one already carries the
  // right meaning). Horizon/depth reuses the existing `corridor` hex as the
  // sky dome's mid-gradient stop.
  warmAccent: "#ffb020",
  horizonDepth: "#12203a",
  // World-2 items 2/3 (2026-09-14, additive -- Ground.tsx/SetKit.tsx#Plaza):
  // lit-daytime tones for the new ground disc / station plaza plate. Night
  // tones deliberately reuse EXISTING tokens (`floor` for the ground,
  // `deskDark` for the plaza -- lighter than the ground, per the plaza's own
  // "lighter tone" spec) rather than adding parallel night keys here.
  groundDay: "#4a5568",
  plazaDay: "#5f6f88",
} as const;

export const HEALTH_COLOR: Record<string, string> = {
  green: "#22ff88",
  amber: "#ffb020",
  red: "#ff3b3b",
  frozen: "#6a86b8",
  zombie: "#a855f7",
};

export function healthColor(health: string): string {
  return HEALTH_COLOR[health] ?? "#7f93b0";
}

// Company Mode (2026-09-13): persona status colors are a DELIBERATELY
// separate map from HEALTH_COLOR above -- lanes (what the firm trades) and
// personas (who does the work) are orthogonal axes per the research brief's
// own finding; sharing one color function between them would misstate the
// system even though both happen to use a conventional green/amber/red
// scale. Never call healthColor() on a PersonaState.status value or vice
// versa -- the enums don't even match (green/amber/red/frozen/zombie vs.
// GREEN/YELLOW/RED/IDLE).
export const PERSONA_STATUS_COLOR: Record<string, string> = {
  GREEN: "#22ff88",
  YELLOW: "#ffb020",
  RED: "#ff3b3b",
  IDLE: "#6a86b8",
};

export function personaStatusColor(status: string): string {
  return PERSONA_STATUS_COLOR[status] ?? PERSONA_STATUS_COLOR.IDLE;
}

/** "3m ago" / "2h ago" / "1d ago" -- shared by PersonaModule's nameplate and
 * Hud.tsx's roster panel so both agree on one wording (moved here 2026-09-13
 * rather than duplicated, per this file's own "small deterministic helpers"
 * remit). Not persona-specific despite the callers -- takes any ISO string
 * or null. */
export function timeAgoText(iso: string | null): string {
  if (!iso) return "never fired";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "never fired";
  const min = Math.max(0, (Date.now() - t) / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${Math.round(min)}m ago`;
  const hr = min / 60;
  if (hr < 48) return `${Math.round(hr)}h ago`;
  return `${Math.round(hr / 24)}d ago`;
}

/** Roster truth (2026-09-13, J: "never print 'never fired' / 'no output
 * yet'"): same time-ago math as timeAgoText, but evidence genuinely older
 * than 7 days becomes "quiet since <date>" -- never a fake-sounding streak
 * or status string. Used by the roster panel (Hud.tsx) and the standby
 * panel, both of which display a persona's real lastFireISO -- once
 * lib/personas.ts's collectors are fixed to always point at real evidence
 * files, "no evidence file" (a null/unparseable iso) should be rare-to-never
 * in practice, but stays honest rather than silently guessing. */
export function rosterEvidenceText(iso: string | null): string {
  if (!iso) return "no evidence file";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "no evidence file";
  const min = Math.max(0, (Date.now() - t) / 60000);
  if (min < 1) return "just now";
  if (min < 60) return `${Math.round(min)}m ago`;
  const hr = min / 60;
  if (hr < 24 * 7) return hr < 48 ? `${Math.round(hr)}h ago` : `${Math.round(hr / 24)}d ago`;
  return `quiet since ${new Date(t).toISOString().slice(0, 10)}`;
}

/** One line, <=max chars, collapsing newlines/repeated whitespace first --
 * moved here from Hud.tsx (2026-09-13, Pass B) since ActivityBubbleLayer.tsx
 * and DeskScreen.tsx now need the identical rule; Hud.tsx imports it from
 * here instead of defining its own copy. */
export function truncateOneLine(text: string | null, max: number): string {
  if (!text) return "no output yet";
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

/** Company audit badge color (commit 58d0b9c6, 2026-09-13, J: "the roster
 * must show ghosts as ghosts") -- deliberately the SAME hex values as
 * HEALTH_COLOR's green/amber/red (one PASS/WARN/FAIL meaning, no reason to
 * invent a fourth palette for it), but its own named map/function per this
 * file's own established convention (see PERSONA_STATUS_COLOR's comment on
 * why orthogonal axes never share one lookup) -- audit verdict and persona
 * "is it currently firing" status are different questions about the same
 * persona and can disagree (a persona can be GREEN/just-fired *and*
 * audit-FAIL, e.g. Treasurer this session: fired on schedule, has never
 * once produced its deliverable). */
export const AUDIT_VERDICT_COLOR: Record<string, string> = {
  PASS: "#22ff88",
  WARN: "#ffb020",
  FAIL: "#ff3b3b",
};

export function auditVerdictColor(verdict: string | undefined): string {
  return AUDIT_VERDICT_COLOR[verdict ?? ""] ?? "#7f93b0";
}

/** Every real sentence of a station-brief body, for Gamma's speech bubble
 * (Pass B, 2026-09-13; extended to ALL sentences LIVE-1 item 2d, 2026-09-14
 * -- "Gamma's thought bubble cycles the brief's sentences... instead of one
 * static line"). station_brief.md's own generator always opens with one
 * machine header line ("<ts> ET - model <name> - N cards on the board"),
 * then a blank-line separator, then hand-written prose (verified against a
 * real brief this session) -- skipping straight to the header's own first
 * "sentence" would put a timestamp dump in Gamma's mouth, not something
 * that reads as speech. Falls back to a single-element array (the RAW
 * text's first line) if no blank-line separator is found (a format change,
 * or a short/malformed brief) or no sentence-ending punctuation is found at
 * all, so this never throws -- only ever `[]` when `text` itself is empty. */
export function splitBriefSentences(text: string, maxLen = 96): string[] {
  if (!text) return [];
  const body = text.split(/\r?\n\s*\r?\n/, 2);
  const source = body.length > 1 ? body[1] : text;
  const trimmed = source.trim();
  if (!trimmed) return [];
  const matches = trimmed.match(/[^.!?]+[.!?]+(?:\s|$)/g);
  const sentences = matches && matches.length > 0 ? matches.map((s) => s.trim()).filter(Boolean) : [trimmed.split(/\r?\n/)[0]];
  return sentences.map((s) => (s.length > maxLen ? `${s.slice(0, maxLen - 1)}…` : s));
}

/** First sentence only -- a thin wrapper over splitBriefSentences, kept for
 * any caller (or future one) that only wants the opening line. */
export function firstBriefSentence(text: string, maxLen = 90): string {
  return splitBriefSentences(text, maxLen)[0] ?? "";
}

export const IDEA_STATUS_COLOR: Record<string, string> = {
  proposed: "#22d3ee",
  testing: "#ffb020",
  supported: "#22ff88",
  refuted: "#8a94a6",
  killed: "#ff3b3b",
  shipped: "#7ad9ff",
};

export function ideaStatusColor(status: string): string {
  return IDEA_STATUS_COLOR[status] ?? "#dff3ff";
}

/** A row counts as "parked" (dark module, no working animation) when its
 * STATE is one of the terminal/inactive values, or its HEALTH says frozen or
 * zombie -- see sector_rows.py's STATE_VALUES/HEALTH_VALUES; there is no
 * literal "parked" enum member on either, so this is the derived union the
 * brief's mapping table means by "state parked/killed/frozen". */
export function isParkedState(state: string, health: string): boolean {
  return (
    state === "killed" ||
    state === "dormant" ||
    state === "dead" ||
    health === "frozen" ||
    health === "zombie"
  );
}

/** xmur3 hash -> mulberry32 generator: a small, well-known, deterministic
 * seeded PRNG (public-domain algorithms, reimplemented here). Used ONLY to
 * pick a per-lane phase offset / next-walk interval at schedule time -- never
 * called inside a useFrame loop (CLAUDE.md "no Math.random per frame"). */
export function seededRandom(seed: string): () => number {
  let h = 1779033703 ^ seed.length;
  for (let i = 0; i < seed.length; i++) {
    h = Math.imul(h ^ seed.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  return function next(): number {
    h = Math.imul(h ^ (h >>> 16), 2246822519);
    h = Math.imul(h ^ (h >>> 13), 3266489917);
    h ^= h >>> 16;
    return (h >>> 0) / 4294967296;
  };
}

// ─── LIVE-1 item 2b (2026-09-14, J: "it still a 'Dead' world"): purposeful
//     walks on a rotation. A PURE, deterministic function of (persona name,
//     wall-clock ms, real board/evidence facts) -- called from BOTH
//     Scene.tsx (inside <Canvas>, to actually queue the walk on Agent.tsx)
//     AND lib/useMotionEvents.ts (outside <Canvas>, to log the SAME decision
//     as a ticker line) so the two stay in agreement without sharing React
//     state across that boundary -- the SAME "two decoupled readers of one
//     truth" pattern useMotionEvents.ts's own file header already documents
//     for the red-lane/all-hands camera triggers. Never Math.random -- a
//     per-persona PERIOD (6-10 min) and PHASE are derived once from
//     seededRandom(name), so both call sites land on the identical bucket
//     boundary for the same persona at the same wall-clock time. ───────────

export interface PurposefulWalk {
  /** True during this persona's own ~14s "walk is happening" window each
   * period -- Agent.tsx doesn't need this (it queues off `bucketKey`
   * changing, once per period, regardless), but useMotionEvents.ts uses it
   * to only log a ticker line, and Scene.tsx uses it to only show the
   * reason bubble, WHILE the walk is actually in flight. */
  active: boolean;
  destination: "ideas-wall" | "core" | "neighbor" | "lounge";
  reason: string;
  /** Changes exactly once per period -- feed this straight into Agent.tsx's
   * `walkEventKey` seen-value-diff (this file's own established queue-a-
   * walk-on-change convention), no separate timer needed there at all. */
  bucketKey: string;
}

const PURPOSEFUL_WALK_PERIOD_MIN_MS = 6 * 60_000;
const PURPOSEFUL_WALK_PERIOD_MAX_MS = 10 * 60_000;
const PURPOSEFUL_WALK_ACTIVE_MS = 14_000; // covers a full WALK_DURATION*2+pause round trip (Agent.tsx) with a little margin

export function computePurposefulWalk(
  personaName: string, nowMs: number, ideasCount: number, ownLastFireISO: string | null, neighborName: string | null,
): PurposefulWalk {
  const rng = seededRandom(personaName);
  const period = PURPOSEFUL_WALK_PERIOD_MIN_MS + rng() * (PURPOSEFUL_WALK_PERIOD_MAX_MS - PURPOSEFUL_WALK_PERIOD_MIN_MS);
  const phase = rng() * period;
  const shifted = nowMs + phase;
  const bucketIndex = Math.floor(shifted / period);
  const cyclePos = shifted - bucketIndex * period;
  const active = cyclePos < PURPOSEFUL_WALK_ACTIVE_MS;

  const ownFireMs = ownLastFireISO ? Date.parse(ownLastFireISO) : NaN;
  const firedWithinOwnPeriod = !Number.isNaN(ownFireMs) && nowMs - ownFireMs >= 0 && nowMs - ownFireMs < period;

  let destination: PurposefulWalk["destination"];
  let reason: string;
  if (ideasCount > 0 && bucketIndex % 3 === 0) {
    destination = "ideas-wall";
    reason = `reading ${ideasCount} card${ideasCount === 1 ? "" : "s"}`;
  } else if (firedWithinOwnPeriod) {
    destination = "core";
    reason = "filing fresh output";
  } else if (neighborName && bucketIndex % 3 === 1) {
    destination = "neighbor";
    reason = `handoff hop to ${neighborName}`;
  } else {
    destination = "lounge";
    reason = "coffee stop";
  }

  return { active, destination, reason, bucketKey: `${personaName}:${bucketIndex}` };
}

/** Parses a "YYYY-MM-DD HH:MM:SS ET" / "YYYY-MM-DDTHH:MM:SS..." string into a
 * comparable epoch-like number (Date.UTC of its own digits, NOT a real UTC
 * conversion -- both this and `nowEtMinutes` below are built the same way, so
 * their DELTA is a correct "minutes elapsed in ET wall-clock time" even
 * though neither value is a real UTC timestamp). Returns null if unparsable
 * ("unknown" is the honest fail-open value sector_rows.py uses). */
export function parseEtLikeMinutes(raw: string | null | undefined): number | null {
  if (!raw) return null;
  const m = /(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/.exec(raw);
  if (!m) return null;
  const [, y, mo, d, h, mi, s] = m.map(Number) as unknown as number[];
  return Date.UTC(y, mo - 1, d, h, mi, s) / 60000;
}

/** Current wall-clock time in America/New_York, expressed the same
 * Date.UTC-of-its-own-digits way as parseEtLikeMinutes so the two are
 * directly comparable. */
export function nowEtMinutes(): number {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).formatToParts(new Date());
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? "0");
  const hour = get("hour") % 24; // Intl can emit "24" for midnight in some locales
  return Date.UTC(get("year"), get("month") - 1, get("day"), hour, get("minute"), get("second")) / 60000;
}

/** 0=Sunday..6=Saturday in America/New_York -- companion to nowEtMinutes
 * above, same Intl.DateTimeFormat approach (never a naive `new
 * Date().getDay()`, which reads the BROWSER's local timezone, not ET --
 * this box's own local time is NOT ET, see CLAUDE.md's own TZ lesson).
 * Used by scheduleOnShift's Sunday-only Treasurer window. */
export function nowEtDayOfWeek(): number {
  const weekday = new Intl.DateTimeFormat("en-US", { timeZone: "America/New_York", weekday: "short" }).format(new Date());
  return ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].indexOf(weekday);
}

/** Minutes between now (ET) and a sector row's last_evidence_et -- null when
 * either side is unparsable (row says "unknown", or a clock read failed). */
export function minutesSinceEvidence(lastEvidenceEt: string): number | null {
  const then = parseEtLikeMinutes(lastEvidenceEt);
  if (then === null) return null;
  return Math.max(0, nowEtMinutes() - then);
}

/** Freshness 0..1 for corridor pulse speed -- 1 = just happened, 0 = a day or
 * more stale. Deliberately coarse (one fixed 24h scale across every lane):
 * this is an ambient/glanceable visualization, not a per-lane SLA monitor. */
export function freshness01(minutesAgo: number | null): number {
  if (minutesAgo === null) return 0;
  const clamped = Math.min(Math.max(minutesAgo, 0), 1440);
  return 1 - clamped / 1440;
}

/** ET day/night mood factor, 0 (deepest night) .. 1 (peak midday) -- Pass C
 * (2026-09-13). This is a SPACE-STATION INTERIOR, not an outdoor scene --
 * there is no literal sun to simulate, and the station's own practical
 * lights (ceiling pointLights, desk screens, beacons) stay lit 24/7 exactly
 * as an artificial installation would. What this drives is the scene's
 * AMBIENT fill only (Scene.tsx's hemisphereLight/directionalLight) -- the
 * "does the station feel like 3am or 2pm" mood, a smaller, cooler fill at
 * night vs a fuller, warmer one at midday. Smoothstep-shaped dawn (05:00-
 * 07:00) and dusk (19:00-21:00) ramps, flat 0 overnight (21:00-05:00) and
 * flat 1 midday (07:00-19:00) -- matches how an actual sunrise/sunset
 * transition reads (gradual at the edges, not linear across the whole day). */
export function dayNightFactor(etMinutes: number): number {
  const hour = (etMinutes / 60) % 24;
  const smooth = (t: number) => t * t * (3 - 2 * t); // smoothstep
  if (hour >= 7 && hour < 19) return 1;
  if (hour >= 21 || hour < 5) return 0;
  if (hour >= 5 && hour < 7) return smooth((hour - 5) / 2);
  return 1 - smooth((hour - 19) / 2); // 19..21 dusk
}

/** One persona's daily/weekly "on shift" window(s), in ET minutes-since-
 * midnight -- Pass C (2026-09-13). Grounded in CLAUDE.md's own schedule
 * table (Gamma_ScoutPremarket 05:30, Gamma_HeartbeatCore 09:30-15:55
 * weekdays, Gamma_AnalystEodReview 16:45, Gamma_TreasurerWeekly Sun 16:00,
 * Coach's several cadences spanning the day, Gamma_Station/Conductor
 * 24/7) -- NOT a literal 1:1 with the coordinator's example phrase
 * ("Premarket 08:30" names a PROCESS STAGE, not a persona in
 * company.personas; folded into Scout's own morning window here, stated as
 * an assumption rather than silently guessed). "Chef overnight" is Chef's
 * OWN window (event-driven overnight wake fires per CLAUDE.md), not a
 * separate night-only override elsewhere in this file -- see
 * scheduleOnShift's own comment for why that's sufficient by itself to
 * produce "night shift = Chef lit/busy, others resting" with no special
 * night-specific code path. */
interface ScheduleWindow {
  startMin: number;
  endMin: number;
  /** 0=Sunday..6=Saturday; omitted = every day. */
  daysOfWeek?: number[];
}
const ALWAYS_ON_SHIFT = new Set(["Gamma (Manager)"]);
const PERSONA_SCHEDULE: Record<string, ScheduleWindow[]> = {
  Scout: [{ startMin: 5 * 60, endMin: 7 * 60 }], // 05:00-07:00 (05:30 fire + the premarket handoff window)
  Coach: [{ startMin: 6 * 60, endMin: 18 * 60 }], // wide daytime gym-check presence (several cadences through the day)
  Pilot: [{ startMin: 9 * 60 + 30, endMin: 15 * 60 + 55 }], // hard market hours, matches CLAUDE.md's own rule
  Analyst: [{ startMin: 16 * 60, endMin: 18 * 60 }], // EOD review window around the 16:45 fire
  Chef: [{ startMin: 20 * 60, endMin: 24 * 60 }, { startMin: 0, endMin: 5 * 60 }], // overnight (wraps midnight)
  Treasurer: [{ startMin: 15 * 60, endMin: 17 * 60, daysOfWeek: [0] }], // Sunday only, around the 16:00 fire
};

/** Whether `personaName` is inside one of its own schedule windows right
 * now. Deliberately does NOT special-case "is it night" anywhere -- Chef's
 * window IS overnight, everyone else's is some slice of the daytime, so
 * "everyone but Chef dims at night" falls out of this table on its own,
 * with no separate day/night branch to keep in sync with dayNightFactor
 * above. Callers should still let REAL activity (a persona currently
 * `behavior === "working"`) override this -- see Scene.tsx's own comment
 * on why a genuine recent fire must never be visually contradicted by a
 * schedule assumption (the same "ghosts as ghosts, never the reverse"
 * principle the audit badges exist for). */
export function scheduleOnShift(personaName: string, etMinutes: number, dayOfWeek: number): boolean {
  if (ALWAYS_ON_SHIFT.has(personaName)) return true;
  const windows = PERSONA_SCHEDULE[personaName];
  if (!windows) return true; // no defined window -- never dim a persona this table doesn't know about
  const minuteOfDay = etMinutes % (24 * 60);
  return windows.some((w) => {
    if (w.daysOfWeek && !w.daysOfWeek.includes(dayOfWeek)) return false;
    return minuteOfDay >= w.startMin && minuteOfDay < w.endMin;
  });
}

/** Regular Trading Hours -- 09:30-15:55 ET, Mon-Fri, matching CLAUDE.md's
 * own hard market-hours rule verbatim (Rule 5/Pilot's PERSONA_SCHEDULE
 * window above uses the identical bounds; this is a standalone export
 * since LIVE-1 item 2c needs it OUTSIDE the persona-schedule-dim context --
 * Pilot's desk-pulse/point gesture, not a dim/lit decision). */
export function isRegularTradingHours(etMinutes: number, dayOfWeek: number): boolean {
  if (dayOfWeek < 1 || dayOfWeek > 5) return false;
  const minuteOfDay = etMinutes % (24 * 60);
  return minuteOfDay >= 9 * 60 + 30 && minuteOfDay < 15 * 60 + 55;
}

/** "HH:MM" from a core-decisions.jsonl `ts_et` value ("YYYY-MM-DDTHH:MM:SS",
 * no offset -- already ET wall-clock text, confirmed against the live file
 * this session, so this is a plain substring, no timezone math needed at
 * all (unlike an ISO string WITH an offset, which would need real
 * conversion). Moved here from Hud.tsx (LIVE-1 item 1 follow-up,
 * coordinator 2026-09-14) so Scene.tsx's Pilot desk-screen/pulse fix can
 * share the EXACT same stamping convention instead of duplicating the
 * regex -- both now read data.trading.core.{safe,bold}'s `tsEt` field. */
export function hhmmFromEtIso(iso: string | null): string {
  if (!iso) return "?";
  const m = /T(\d{2}):(\d{2})/.exec(iso);
  return m ? `${m[1]}:${m[2]}` : "?";
}

export function clamp01(v: number): number {
  return Math.min(1, Math.max(0, v));
}

export function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

/** Local-space (a module/desk's "front" = -Z, toward the hub) -> TRUE
 * world-space, using the same rotation a module's own room-geometry group
 * applies. Bug fix (2026-09-13, HQ v3): this must be called for anything
 * (like an Agent) that will be mounted as a SCENE-ROOT sibling, never as a
 * child already nested inside a group transformed by the same
 * center/rotationY -- doing both compounds the transform twice and lands
 * the object ~one ring-radius away from where it belongs (confirmed
 * numerically: an agent meant to sit 0.15 units from its module rendered
 * ~9.65 units away instead, when Agent was nested inside StationModule's
 * own positioned+rotated <group>). Scene.tsx now computes this once per
 * lane/persona and renders <Agent> as a top-level sibling of the room
 * geometry, not its child. */
export function localToWorld(
  center: [number, number, number], rotationY: number, local: [number, number, number],
): [number, number, number] {
  const cos = Math.cos(rotationY);
  const sin = Math.sin(rotationY);
  return [
    center[0] + local[0] * cos + local[2] * sin,
    center[1] + local[1],
    center[2] - local[0] * sin + local[2] * cos,
  ];
}

// ─── HQ v4 look pass (2026-09-13): procedural textures, all-canvas-drawn,
//     zero bundled assets (nidorx/matcaps was checked and rejected --
//     untraceable original authorship, a real license risk for a public
//     repo). Both are cached module-level singletons built ONCE on first
//     call, never per-frame/per-render, and never at module-import time
//     (canvas/DataTexture need a browser -- calling either during Next.js's
//     server render would throw "document is not defined"; both functions
//     fail loudly instead of silently returning something wrong). Only
//     ever call these from inside an r3f child of <Canvas>, which never
//     executes during SSR. ─────────────────────────────────────────────────

let _matcapTexture: THREE.CanvasTexture | null = null;

/** A single soft radial-gradient "sphere shading" matcap -- the standard
 * Bruno-Simon-portfolio-style technique: one texture lookup keyed by
 * view-space normal replaces Lambert's per-fragment N.L, at a fraction of
 * the cost on a fragment-bound mobile GPU, while giving flat unlit meshes
 * actual dimensional shading. Neutral/blue-white so `color` tinting (every
 * caller passes its own part color) reads naturally on top of it. */
export function makeMatcapTexture(): THREE.CanvasTexture {
  if (typeof document === "undefined") {
    throw new Error("makeMatcapTexture() called outside a browser -- never call this during SSR");
  }
  if (_matcapTexture) return _matcapTexture;
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("makeMatcapTexture(): 2D canvas context unavailable");
  const gradient = ctx.createRadialGradient(size * 0.35, size * 0.32, size * 0.04, size * 0.5, size * 0.5, size * 0.62);
  gradient.addColorStop(0, "#ffffff");
  gradient.addColorStop(0.22, "#cfe9ff");
  gradient.addColorStop(0.5, "#5f83a0");
  gradient.addColorStop(0.78, "#1c2c3c");
  gradient.addColorStop(1, "#05090f");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  const texture = new THREE.CanvasTexture(canvas);
  texture.needsUpdate = true;
  texture.colorSpace = THREE.SRGBColorSpace;
  _matcapTexture = texture;
  return texture;
}

export interface ScreenLine {
  text: string;
  color?: string;
  size?: number;
}

/** One 256x160 canvas + THREE.CanvasTexture pair for a desk/wall "screen"
 * mesh (Pass B, 2026-09-13: "real canvas-rendered textures... on kit
 * computer-screen meshes"). Deliberately NOT a cached module-level
 * singleton like makeMatcapTexture/makeToonGradientTexture above -- every
 * screen shows DIFFERENT content, so each DeskScreen instance owns one of
 * these for its own lifetime and calls drawScreenLines() on it only when
 * its content actually changes (never per-frame -- this is real 2D canvas
 * drawing, not free even on an idle GPU, and the brief's own budget line
 * says "regenerated on data change only"). */
export function createScreenCanvas(): { canvas: HTMLCanvasElement; texture: THREE.CanvasTexture } {
  if (typeof document === "undefined") {
    throw new Error("createScreenCanvas() called outside a browser -- never call this during SSR");
  }
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 160;
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return { canvas, texture };
}

/** Draws an optional dim header row (`title`) then `lines` top-to-bottom
 * onto `canvas`, and flags `texture` for GPU re-upload. Every caller passes
 * real evidence text (row.evidence / persona.recentOutput / idea titles --
 * never placeholder copy), truncated defensively here too since a caller's
 * own truncation budget (tuned for an Html DOM line) doesn't necessarily
 * match this canvas's fixed 256px pixel width.
 *
 * `liveStamp` (LIVE-1 item 2a, 2026-09-14, optional): a small dim "synced
 * HH:MM:SS" readout bottom-right -- DeskScreen.tsx redraws this same
 * content every 30s regardless of whether title/lines themselves changed,
 * so a screen showing genuinely unchanged real data still visibly ticks
 * (a real clock, never fabricated content) instead of reading as a frozen
 * screenshot. Omitted (every OTHER caller of this shared drawer -- none
 * currently exist besides DeskScreen.tsx, but the signature stays
 * backward-compatible) for zero layout change. */
export function drawScreenLines(canvas: HTMLCanvasElement, texture: THREE.CanvasTexture, title: string | null, lines: ScreenLine[], liveStamp?: string): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const w = canvas.width;
  const h = canvas.height;
  ctx.fillStyle = "#040a12";
  ctx.fillRect(0, 0, w, h);
  ctx.textBaseline = "top";
  let y = 10;
  if (title) {
    ctx.fillStyle = "#5f7a99";
    ctx.font = "bold 15px system-ui, sans-serif";
    ctx.fillText(title.length > 26 ? `${title.slice(0, 25)}…` : title, 12, y);
    y += 22;
    ctx.strokeStyle = "rgba(122,217,255,0.25)";
    ctx.beginPath();
    ctx.moveTo(12, y);
    ctx.lineTo(w - 12, y);
    ctx.stroke();
    y += 8;
  }
  for (const line of lines) {
    if (y > h - 16) break;
    const size = line.size ?? 18;
    ctx.fillStyle = line.color ?? "#dff3ff";
    ctx.font = `${size}px system-ui, sans-serif`;
    const maxChars = Math.floor((w - 24) / (size * 0.56));
    const text = line.text.length > maxChars ? `${line.text.slice(0, Math.max(1, maxChars - 1))}…` : line.text;
    ctx.fillText(text, 12, y);
    y += size + 8;
  }
  if (liveStamp) {
    ctx.fillStyle = "#2f3f56";
    ctx.font = "10px system-ui, sans-serif";
    ctx.textAlign = "right";
    ctx.fillText(liveStamp, w - 8, h - 14);
    ctx.textAlign = "left";
  }
  texture.needsUpdate = true;
}

let _toonGradientTexture: THREE.DataTexture | null = null;

/** 3-step toon gradient ramp (the brief's own spec) for MeshToonMaterial's
 * `gradientMap` -- a tiny 1-row RedFormat DataTexture sampled by N.L,
 * NearestFilter so the 3 bands stay crisp bands rather than blurring into a
 * smooth Lambert-like gradient (that smoothing is exactly the "flat/no
 * depth modeling" look this material swap exists to fix). WebGL2-only
 * (RedFormat), which this project already requires throughout. */
export function makeToonGradientTexture(): THREE.DataTexture {
  if (typeof document === "undefined") {
    throw new Error("makeToonGradientTexture() called outside a browser -- never call this during SSR");
  }
  if (_toonGradientTexture) return _toonGradientTexture;
  const steps = 3;
  const data = new Uint8Array(steps);
  for (let i = 0; i < steps; i++) data[i] = Math.round((i / (steps - 1)) * 255);
  const texture = new THREE.DataTexture(data, steps, 1, THREE.RedFormat);
  texture.minFilter = THREE.NearestFilter;
  texture.magFilter = THREE.NearestFilter;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;
  _toonGradientTexture = texture;
  return texture;
}

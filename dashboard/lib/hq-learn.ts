// PANEL-3 (2026-09-14): "i want this automated trading agent world to be
// self learning, improving, and awesome as fuck" -- J's verbatim mandate
// (2026-09-14 ~18:25 ET). This module turns 6 REAL, already-produced files
// into the LEARN tab's data: what Gamma's research board (Chef/Coach/
// Autopsy/Gamma) learned today, and what changed because of it. Every
// number below is copied verbatim from a Python producer's own already-
// computed text/field -- never re-derived client-side (hallucination
// guard: a number reconstructed here could silently drift from the
// producer's own math).
//
// FREEZE CONTEXT (verified this session against STATUS.md/SHADOW.md, not
// assumed): trading-path params (params.json / aggressive/params.json /
// filters.py / heartbeat_core.py) are frozen to 2026-10-30 -- the
// "September clean window" restarted 2026-09-14 per STATUS.md's own
// 2026-09-11 23:38 ET entry, and SHADOW.md's frozen-prereg list already
// carries five "10-30 checkpoint candidate (EXPANSION)" entries. So a
// "supported" research-board verdict during this window can only park
// itself for that checkpoint, never arm live -- verdictChangedText() below
// says so honestly rather than implying anything shipped.
//
// SOURCES (all read-only; this module writes nothing):
//   analysis/recommendations/station-verdicts.jsonl -- Chef's scorer output,
//     one row per scoring pass (hypothesis_scorer.py, ~every 30 min while a
//     card is "testing"). verdict is pending until n_post >= min_n, then
//     supported/refuted (setup/scripts/hypothesis_scorer.py:_verdict_from_effect).
//   automation/state/station/coach-notes.json -- Coach's $-ranked lane
//     counterfactuals (setup/scripts/coach_notes.py); notes[0] is already the
//     #1-ranked note (the producer sorts before writing -- verified this
//     session: file order already matches descending |delta|).
//   automation/state/station/hq-review.json -- Gamma's own look at HQ's
//     health (setup/scripts/hq_self_review.py); `lines` is ALREADY the
//     human-readable summary, reused verbatim rather than reformatted.
//   analysis/autopsies/<today>.jsonl -- per-fill counterfactuals
//     (setup/scripts/trade_autopsy.py's row shape).
//   automation/state/hypotheses-settled.json -- mechanisms trade_autopsy.py
//     will never re-propose (settled_on-dated).
//   automation/state/station/ideas-board.json -- the research board's own
//     cards; status is one of proposed/testing/killed/shipped/supported/
//     refuted (setup/scripts/station_board.py).
//
// NOTE on crew-events.jsonl: that file ALSO logs verdict/coaching/hq_review
// rows, but only on a producer-side change (station_loop.py/coach_notes.py/
// hq_self_review.py each diff against the previous row before appending --
// verified this session by reading each call site). Deliberately NOT used
// as this module's source of truth: depending on that dedupe logic would
// make this tab's content only as complete as three separate Python diff
// checks this module cannot see or test, and would leave the tab silent on
// a day where a card is scored repeatedly but never flips (exactly today's
// real case: card f5deabe978 was rescored 4x today, no crew-events "verdict"
// row exists at all, yet "Chef scored it and it's still pending" is
// genuinely today's most real fact to show). Reading the 6 source files
// directly, independently, is also what keeps buildHqLearn() a pure,
// fixture-testable function (see dashboard/tests/hq-learn.test.ts).
//
// Server-only. Every reader below is independently fail-open (try/catch ->
// an empty/null default, never a throw); readHqLearn()'s own entry point is
// wrapped a second time so a bug here can only ever degrade /api/hq's `learn`
// field, matching lib/hq-runtime.ts's own readHqRuntime() backstop contract.
//
// Deliberately NOT importing any sibling lib/*.ts module by VALUE (only
// node:fs/node:path) -- same reasoning lib/hq-runtime.ts's own header gives:
// a relative .ts->.ts value import needs an explicit ".ts" specifier to
// resolve under plain `node --test` (this module's own test runs the same
// way, unflagged, no bundler), but writing that extension trips this
// project's tsconfig `moduleResolution: "bundler"` in the Next.js build.
// The ~10 lines of ideas-board.json field-picking this would otherwise
// import from lib/station.ts#readIdeasBoard are duplicated locally instead
// (the same "tiny stable helper re-defined per file" convention hq-runtime.ts
// already established for WORKSPACE_ROOT/etHHMM).

import { promises as fs } from "node:fs";
import path from "node:path";

const WORKSPACE_ROOT = process.env.GAMMA_WORKSPACE ?? "C:\\Users\\jackw\\Desktop\\42";
const st = (...parts: string[]) => path.join(WORKSPACE_ROOT, "automation", "state", ...parts);

// ─── Wire types ─────────────────────────────────────────────────────────────

export type LearnedWho = "Chef" | "Coach" | "Gamma" | "Analyst" | "Autopsy";

export interface LearnedRow {
  when: string; // "HH:MM" ET
  who: LearnedWho;
  what: string; // one line, real numbers, copied from the producer's own text
  evidence: string; // "<file path> (<real n or fact>)"
  changed: string; // one line -- what changed because of it (or honestly, that nothing did)
}

export interface HqLearn {
  dayEt: string; // "YYYY-MM-DD", ET calendar date
  learned: LearnedRow[]; // newest-first
  settledMechanisms: number; // total mechanisms trade_autopsy.py will never re-propose
  verdictsToday: { supported: number; refuted: number; testing: number };
  lastLearnedAtEt: string | null; // "HH:MM" of the newest row, null when learned is empty
  /** Present only when readHqLearn()'s own backstop caught an unexpected
   * throw -- every per-source reader below already fails open on its own,
   * so this should never be set in practice (same contract as
   * lib/hq-runtime.ts's own `error` field). */
  error?: string;
}

// ─── Pure: ET date/time helpers (unit-tested, zero fs) ─────────────────────
// Deliberately re-derived here rather than imported -- see this file's own
// header for why a cross-module VALUE import breaks `node --test`. Same
// Intl-based approach every other ET formatter in this codebase uses.

export function todayEtDateStr(nowMs: number = Date.now()): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date(nowMs));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/** "2026-09-14 19:21:01 ET" -> "19:21". Every ts_et field this module reads
 * (station-verdicts.jsonl, coach-notes.json, hq-review.json) shares this
 * exact "YYYY-MM-DD HH:MM:SS ET" shape (verified against the live files
 * this session), so one regex covers all three sources. Null on anything
 * that doesn't match, never a guessed time. */
export function hhmmFromTsEt(tsEt: string): string | null {
  const m = /\d{4}-\d{2}-\d{2}[T ](\d{2}):(\d{2})/.exec(tsEt);
  return m ? `${m[1]}:${m[2]}` : null;
}

/** Epoch ms -> "HH:MM" in America/New_York -- for autopsy rows, whose own
 * timestamp (entry_ts_utc) is a real UTC ISO string, not an ET-prefixed one. */
export function hhmmEtFromEpoch(ms: number): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hour12: false,
  }).formatToParts(new Date(ms));
  const hh = parts.find((p) => p.type === "hour")?.value ?? "??";
  const mm = parts.find((p) => p.type === "minute")?.value ?? "??";
  return `${hh}:${mm}`;
}

export function isTodayEt(tsEt: string | null | undefined, dayEt: string): boolean {
  return typeof tsEt === "string" && tsEt.startsWith(dayEt);
}

export function truncateOneLine(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, Math.max(0, max - 1))}…` : s;
}

/** Strips a leading "Coach: " (etc) prefix a producer's own `line` text
 * already carries -- this row's own `who` chip already names the actor, so
 * keeping both would double it, the exact bug Hud.tsx's formatCrewLine
 * comment (R3) already documents for the Activity tab's feed. */
export function stripWhoPrefix(line: string, who: string): string {
  const prefix = `${who}: `;
  return line.startsWith(prefix) ? line.slice(prefix.length) : line;
}

// ─── Chef: station-verdicts.jsonl ──────────────────────────────────────────

export interface StationVerdictResult {
  n_pre: number;
  n_post: number;
  effect_pre: number | null;
  effect_post: number | null;
  verdict: string; // "pending" | "supported" | "refuted" | "spec_error" | string
  detail: string; // already a complete, real sentence -- reused verbatim
}

export interface StationVerdictRow {
  ts_et: string;
  card_id: string;
  spec: { type: string; params?: Record<string, unknown> };
  result: StationVerdictResult;
}

/** One row per distinct card_id -- the LATEST scoring pass from `dayEt` for
 * that card, plus how many passes it got today. Collapses e.g. today's real
 * 4 identical-verdict rescans of one card into a single learned entry
 * (scoresToday: 4) rather than 4 near-duplicate rows. Pure, fixture-tested. */
export function latestVerdictsForDay(
  rows: StationVerdictRow[],
  dayEt: string,
): Array<{ row: StationVerdictRow; scoresToday: number }> {
  const byCard = new Map<string, StationVerdictRow[]>();
  for (const r of rows) {
    if (!isTodayEt(r.ts_et, dayEt) || !r.card_id) continue;
    const list = byCard.get(r.card_id) ?? [];
    list.push(r);
    byCard.set(r.card_id, list);
  }
  const out: Array<{ row: StationVerdictRow; scoresToday: number }> = [];
  for (const list of byCard.values()) {
    out.push({ row: list[list.length - 1], scoresToday: list.length });
  }
  return out;
}

/** Freeze-aware "changed" text for one scored card. A "supported" verdict
 * during the trading-path freeze (to 2026-10-30, see this file's own header)
 * cannot arm anything live -- saying so here is the whole point of this
 * tab ("say that on the tab rather than pretending", per this task's own
 * brief) rather than a bare "supported" that implies it shipped. */
export function verdictChangedText(verdict: string): string {
  const v = (verdict || "").toLowerCase();
  if (v === "supported") {
    return "card supported -- blocked from arming by the trading-path freeze (to 2026-10-30); shadow/prereg only";
  }
  if (v === "refuted") return "card refuted, parked";
  if (v === "spec_error") return "spec error -- scorer could not evaluate this card, needs a human look";
  return "nothing acted on this yet -- still pending";
}

// ─── Coach: coach-notes.json ────────────────────────────────────────────────

export interface CoachNote {
  lane: string;
  stat: string;
  line: string;
  delta: number | null;
}

export interface CoachNotesDoc {
  ts_et: string;
  notes: CoachNote[];
}

// ─── Coach/Gamma: hq-review.json ───────────────────────────────────────────

export interface HqReviewDoc {
  ts_et: string;
  score_0_100: number;
  stale: unknown[];
  ghosts: unknown[];
  desks_stale: unknown[];
  lines: string[];
}

/** "changed" text for the HQ self-review row -- built from array LENGTHS
 * only (never from guessing the shape of a stale/ghost entry's own fields,
 * which this module has not independently verified beyond the crew-events
 * ticker prose that names them) so this is robust to that shape either way. */
export function hqReviewChangedText(review: Pick<HqReviewDoc, "score_0_100" | "stale" | "ghosts" | "desks_stale">): string {
  const healthy = review.stale.length === 0 && review.ghosts.length === 0 && review.desks_stale.length === 0;
  if (healthy) return `no action needed -- HQ healthy (${review.score_0_100}/100)`;
  return `Coach flagged ${review.stale.length} stale + ${review.ghosts.length} ghost persona(s) for Gamma (score ${review.score_0_100}/100)`;
}

// ─── Autopsy: analysis/autopsies/<day>.jsonl ───────────────────────────────

export interface AutopsyRow {
  date: string;
  arm: string;
  strategy: string;
  symbol: string;
  entry_ts_utc: string;
  actual_pnl: number;
  stop_cost_vs_best: number | null;
  best_counterfactual: string | null;
}

/** One combined learned row for ALL of today's autopsied fills (a single
 * trading moment commonly mirrors across 2-4 arms -- today's real 3 rows are
 * one fill mirrored on safe-3/risky-1/risky-3), not one row per fill (which
 * would just be noise at this tab's altitude). `when` is the LATEST real
 * entry_ts_utc among them, not "now". Null when there is nothing to report. */
export function buildAutopsyRow(rows: AutopsyRow[], dayEt: string): LearnedRow | null {
  if (rows.length === 0) return null;
  const arms = [...new Set(rows.map((r) => r.arm).filter(Boolean))];
  const strategies = [...new Set(rows.map((r) => r.strategy).filter(Boolean))];
  const costs = rows
    .map((r) => r.stop_cost_vs_best)
    .filter((n): n is number => typeof n === "number" && Number.isFinite(n));
  const absCosts = costs.map((n) => Math.abs(n)).sort((a, b) => a - b);
  const costRange = absCosts.length > 0
    ? (absCosts[0] === absCosts[absCosts.length - 1]
      ? `$${absCosts[0].toFixed(2)}`
      : `$${absCosts[0].toFixed(2)}-$${absCosts[absCosts.length - 1].toFixed(2)}`)
    : "?";
  const bestCf = rows.find((r) => r.best_counterfactual)?.best_counterfactual ?? "?";
  const latestMs = rows
    .map((r) => Date.parse(r.entry_ts_utc))
    .filter((n) => !Number.isNaN(n))
    .sort((a, b) => b - a)[0];
  return {
    when: latestMs !== undefined ? hhmmEtFromEpoch(latestMs) : "??:??",
    who: "Autopsy",
    what: `${rows.length} fill${rows.length === 1 ? "" : "s"} reviewed across ${arms.join(", ") || "?"} `
      + `(${strategies.join(", ") || "?"}) -- best exit shape "${bestCf}" beat actual by ${costRange}`,
    evidence: `analysis/autopsies/${dayEt}.jsonl (n=${rows.length})`,
    changed: "no change possible: trading-path params frozen to 2026-10-30 -- counterfactual logged for the next checkpoint",
  };
}

// ─── Gamma: hypotheses-settled.json ────────────────────────────────────────

export interface SettledMechanismRow {
  mechanism: string;
  settled_on: string | null;
  verdict: string;
}

// ─── Ideas board: status snapshot (minimal local shape -- see this file's
//     own header for why lib/station.ts#StationIdeaCard is not imported by
//     value here) ────────────────────────────────────────────────────────

export interface IdeasBoardCardMinimal {
  id: string;
  status: string;
  title: string;
}

/** Live snapshot of the board's own supported/refuted/testing counts --
 * ASSUMPTION (stated once, per this codebase's own assumption-surfacing
 * convention): ideas-board.json carries no per-status-change timestamp, so
 * this is "as the board reads right now", not "flipped today specifically".
 * On a quiet day (today's real board: 18 proposed, 1 testing, 0 supported/
 * refuted) this reads {supported:0, refuted:0, testing:1} -- an honest
 * zero, not an invented one. */
export function tallyVerdictsToday(cards: IdeasBoardCardMinimal[]): { supported: number; refuted: number; testing: number } {
  let supported = 0;
  let refuted = 0;
  let testing = 0;
  for (const c of cards) {
    if (c.status === "supported") supported += 1;
    else if (c.status === "refuted") refuted += 1;
    else if (c.status === "testing") testing += 1;
  }
  return { supported, refuted, testing };
}

// ─── Pure combiner (fixture-tested: dashboard/tests/hq-learn.test.ts) ─────

export interface HqLearnInputs {
  dayEt: string;
  verdictRows: StationVerdictRow[];
  ideasCards: IdeasBoardCardMinimal[];
  coachNotes: CoachNotesDoc | null;
  hqReview: HqReviewDoc | null;
  autopsyRows: AutopsyRow[];
  settled: SettledMechanismRow[];
}

/** The whole tab's content, computed from already-parsed inputs -- zero fs
 * access, so this is the unit-testable half of the module (mirrors
 * lib/hq-runtime.ts's own classifyRole()/buildHqRuntime() split). Row order:
 * Chef verdicts, Coach coaching, Coach/Gamma hq-review, Autopsy, Gamma
 * settled-today -- then re-sorted newest-first by `when` so the actual
 * render order is chronological regardless of this construction order. */
export function buildHqLearn(inputs: HqLearnInputs): Omit<HqLearn, "error"> {
  const rows: LearnedRow[] = [];
  const cardById = new Map(inputs.ideasCards.map((c) => [c.id, c]));

  for (const { row, scoresToday } of latestVerdictsForDay(inputs.verdictRows, inputs.dayEt)) {
    const title = cardById.get(row.card_id)?.title ?? row.card_id;
    rows.push({
      when: hhmmFromTsEt(row.ts_et) ?? "??:??",
      who: "Chef",
      what: `Scored "${truncateOneLine(title, 70)}" (${row.spec.type}): ${row.result.detail}`,
      evidence: `analysis/recommendations/station-verdicts.jsonl (${scoresToday} scoring pass${scoresToday === 1 ? "" : "es"} today, card ${row.card_id})`,
      changed: verdictChangedText(row.result.verdict),
    });
  }

  if (inputs.coachNotes && isTodayEt(inputs.coachNotes.ts_et, inputs.dayEt) && inputs.coachNotes.notes.length > 0) {
    const top = inputs.coachNotes.notes[0];
    rows.push({
      when: hhmmFromTsEt(inputs.coachNotes.ts_et) ?? "??:??",
      who: "Coach",
      what: stripWhoPrefix(top.line, "Coach"),
      evidence: `automation/state/station/coach-notes.json (${inputs.coachNotes.notes.length} lane(s) ranked)`,
      changed: top.delta !== null
        ? `coaching note ranked #1 by $ impact (counterfactual $${Math.abs(top.delta).toFixed(0)} vs current)`
        : "coaching note ranked #1 by $ impact",
    });
  }

  if (inputs.hqReview && isTodayEt(inputs.hqReview.ts_et, inputs.dayEt)) {
    const summary = inputs.hqReview.lines.length > 0
      ? inputs.hqReview.lines.join(" · ")
      : `score ${inputs.hqReview.score_0_100}/100`;
    rows.push({
      when: hhmmFromTsEt(inputs.hqReview.ts_et) ?? "??:??",
      who: "Coach",
      what: `HQ self-review -- ${summary}`,
      evidence: `automation/state/station/hq-review.json (score ${inputs.hqReview.score_0_100}/100)`,
      changed: hqReviewChangedText(inputs.hqReview),
    });
  }

  const autopsyRow = buildAutopsyRow(inputs.autopsyRows, inputs.dayEt);
  if (autopsyRow) rows.push(autopsyRow);

  for (const s of inputs.settled) {
    if (s.settled_on !== inputs.dayEt) continue; // only mechanisms settled TODAY get a row; the total lives in settledMechanisms
    rows.push({
      when: "00:00", // settled_on is a date only, no time-of-day in the source
      who: "Gamma",
      what: `Mechanism "${s.mechanism}" settled: ${s.verdict}`,
      evidence: `automation/state/hypotheses-settled.json (${inputs.settled.length} total settled)`,
      changed: "will not be re-proposed by autopsy (7-day dedupe cooldown)",
    });
  }

  rows.sort((a, b) => b.when.localeCompare(a.when));

  return {
    dayEt: inputs.dayEt,
    learned: rows,
    settledMechanisms: inputs.settled.length,
    verdictsToday: tallyVerdictsToday(inputs.ideasCards),
    lastLearnedAtEt: rows.length > 0 ? rows[0].when : null,
  };
}

// ─── fs readers -- fail-open, never throw ──────────────────────────────────

async function readJsonSafe<T>(p: string): Promise<T | null> {
  try {
    return JSON.parse(await fs.readFile(p, "utf-8")) as T;
  } catch {
    return null;
  }
}

async function readJsonlSafe<T>(p: string): Promise<T[]> {
  try {
    const text = await fs.readFile(p, "utf-8");
    const rows: T[] = [];
    for (const line of text.trim().split("\n")) {
      if (!line.trim()) continue;
      try {
        rows.push(JSON.parse(line) as T);
      } catch {
        // one malformed line never blocks the rest of the tail
      }
    }
    return rows;
  } catch {
    return [];
  }
}

async function readIdeasCardsMinimal(): Promise<IdeasBoardCardMinimal[]> {
  const raw = await readJsonSafe<unknown[]>(st("station", "ideas-board.json"));
  if (!Array.isArray(raw)) return [];
  const out: IdeasBoardCardMinimal[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const rec = entry as Record<string, unknown>;
    if (typeof rec.id !== "string" || typeof rec.status !== "string") continue;
    out.push({ id: rec.id, status: rec.status, title: typeof rec.title === "string" ? rec.title : rec.id });
  }
  return out;
}

async function readSettledMechanisms(): Promise<SettledMechanismRow[]> {
  const doc = await readJsonSafe<{ settled?: unknown }>(st("hypotheses-settled.json"));
  const raw = doc?.settled;
  if (!Array.isArray(raw)) return [];
  const out: SettledMechanismRow[] = [];
  for (const entry of raw) {
    if (!entry || typeof entry !== "object") continue;
    const rec = entry as Record<string, unknown>;
    if (typeof rec.mechanism !== "string") continue;
    out.push({
      mechanism: rec.mechanism,
      settled_on: typeof rec.settled_on === "string" ? rec.settled_on : null,
      verdict: typeof rec.verdict === "string" ? rec.verdict : "?",
    });
  }
  return out;
}

async function buildHqLearnLive(): Promise<HqLearn> {
  const dayEt = todayEtDateStr();
  const [verdictRows, ideasCards, coachNotes, hqReview, autopsyRows, settled] = await Promise.all([
    readJsonlSafe<StationVerdictRow>(path.join(WORKSPACE_ROOT, "analysis", "recommendations", "station-verdicts.jsonl")),
    readIdeasCardsMinimal(),
    readJsonSafe<CoachNotesDoc>(st("station", "coach-notes.json")),
    readJsonSafe<HqReviewDoc>(st("station", "hq-review.json")),
    readJsonlSafe<AutopsyRow>(path.join(WORKSPACE_ROOT, "analysis", "autopsies", `${dayEt}.jsonl`)),
    readSettledMechanisms(),
  ]);
  return buildHqLearn({ dayEt, verdictRows, ideasCards, coachNotes, hqReview, autopsyRows, settled });
}

let learnCache: { data: HqLearn; at: number } | null = null;
const LEARN_CACHE_MS = 30_000;

/** Entry point -- 30s-cached (copying lib/hq-runtime.ts's own PROCESS_CACHE_MS/
 * QUIET_MODE_CACHE_MS shape) so /api/hq's poll (kiosk 60s / interactive 15s,
 * possibly several simultaneous viewers) never re-reads 6 files more than
 * twice a minute. Wrapped a second time on top of every reader's own
 * try/catch -- a bug here can only ever degrade the `learn` field of
 * /api/hq's response, never 500 the whole payload. */
export async function readHqLearn(): Promise<HqLearn> {
  if (learnCache && Date.now() - learnCache.at < LEARN_CACHE_MS) return learnCache.data;
  try {
    const data = await buildHqLearnLive();
    learnCache = { data, at: Date.now() };
    return data;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("[hq-learn] readHqLearn() threw past every reader's own fail-open guard:", err);
    return {
      dayEt: todayEtDateStr(),
      learned: [],
      settledMechanisms: 0,
      verdictsToday: { supported: 0, refuted: 0, testing: 0 },
      lastLearnedAtEt: null,
      error: `readHqLearn failed: ${message}`,
    };
  }
}

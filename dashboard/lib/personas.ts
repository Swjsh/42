// Extracted verbatim from dashboard/app/api/personas/route.ts (2026-09-13,
// HQ v3 Company Mode) so /api/hq can attach the same persona roster +
// handoff pipeline as `data.company` without duplicating the collectors.
// NO BEHAVIOR CHANGE: every function below is byte-for-byte the same logic
// that lived in the route file -- same ROOT computation (process.cwd()-
// relative, not workspace.ts's WORKSPACE_ROOT, to guarantee /api/personas
// keeps reading the exact same paths it always has), same field names, same
// fail-open try/catch shape. Zero new writers -- everything here is a read.

import { promises as fs } from "fs";
import path from "path";
import { execSync } from "child_process";
// CREW-2 (2026-09-14): reused rather than re-derived -- lib/useMotionEvents.ts
// already sets the precedent for a lib/ file importing pure helpers from
// components/hq/palette.ts (zero risk of circularity: palette.ts's only
// import is "three"). Real market-hours math must stay ONE source of truth
// project-wide (CLAUDE.md's own standing TZ lesson).
import { isRegularTradingHours, nowEtDayOfWeek, nowEtMinutes } from "@/components/hq/palette";

const ROOT = path.join(process.cwd(), "..");

// ---------- helpers ----------

async function fileExists(p: string): Promise<boolean> {
  try { await fs.access(p); return true; } catch { return false; }
}

async function mtimeISO(p: string): Promise<string | null> {
  try { const s = await fs.stat(p); return s.mtime.toISOString(); } catch { return null; }
}

async function readText(p: string, maxBytes = 32 * 1024): Promise<string | null> {
  try {
    const buf = await fs.readFile(p);
    if (buf.length <= maxBytes) return buf.toString("utf8");
    const tail = buf.subarray(buf.length - maxBytes).toString("utf8");
    // Pass G nit (b) (2026-09-13, coordinator: roster snippets start
    // mid-word, e.g. "ehavior (breakers are the ..."). Root cause: the tail
    // slice above cuts at a raw BYTE offset with zero regard for line or
    // word boundaries -- any file over maxBytes had its preview start
    // wherever that offset happened to land, mid-word as often as not.
    // Fix: advance past the first line break within a short lookahead so
    // the preview starts at a real line -- in these markdown digest/
    // leaderboard files (Chef/Treasurer/Analyst) one line IS one bullet/
    // sentence, so "start at a line" and "prefer the sentence's start"
    // are the same fix here, not two. Falls back to the next space if no
    // newline appears nearby (one very long line), and to the raw tail
    // only if neither boundary exists in the lookahead -- never returns
    // empty chasing a boundary that isn't there.
    const lookahead = tail.slice(0, 200);
    const nl = lookahead.indexOf("\n");
    if (nl !== -1 && nl < tail.length - 1) return tail.slice(nl + 1) + "\n[truncated]";
    const sp = lookahead.indexOf(" ");
    if (sp !== -1) return tail.slice(sp + 1) + "\n[truncated]";
    return tail + "\n[truncated]";
  } catch { return null; }
}

async function readJson<T = unknown>(p: string): Promise<T | null> {
  try { return JSON.parse(await fs.readFile(p, "utf8")) as T; } catch { return null; }
}

async function readJsonlTail<T = unknown>(p: string, n = 5): Promise<T[]> {
  try {
    const text = await fs.readFile(p, "utf8");
    return text.trim().split("\n").slice(-n).map((line) => {
      try { return JSON.parse(line) as T; } catch { return null as unknown as T; }
    }).filter(Boolean);
  } catch { return []; }
}

async function dirListing(p: string): Promise<Array<{ name: string; mtimeISO: string; sizeBytes: number }>> {
  try {
    const items = await fs.readdir(p);
    const out = [];
    for (const name of items) {
      try {
        const s = await fs.stat(path.join(p, name));
        if (s.isFile()) out.push({ name, mtimeISO: s.mtime.toISOString(), sizeBytes: s.size });
      } catch {}
    }
    return out.sort((a, b) => b.mtimeISO.localeCompare(a.mtimeISO));
  } catch { return []; }
}

function todayET(): string {
  // ET date in YYYY-MM-DD form for path construction
  const now = new Date();
  const et = new Date(now.toLocaleString("en-US", { timeZone: "America/New_York" }));
  const y = et.getFullYear();
  const m = String(et.getMonth() + 1).padStart(2, "0");
  const d = String(et.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

/** "2026-09-13 22:51:00 ET" -> a genuine UTC ISO string (roster hotfix,
 * 2026-09-13). DST-aware: tries both plausible ET offsets (-4 EDT, -5 EST)
 * and keeps whichever one, reformatted back through the America/New_York
 * timezone, reproduces the EXACT wall-clock digits given -- a hardcoded
 * "always -4" would silently drift wrong at every DST transition (this
 * project's own setup/scripts/et_clock.py is DST-aware for the same
 * reason). Falls back to EDT (right for mid-March..early-November, which
 * covers the live trading calendar) rather than returning null -- a
 * slightly-off timestamp still beats "never fired". */
function etLikeToIso(raw: string): string | null {
  const m = /(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(raw);
  if (!m) return null;
  // m.slice(1) already drops the full-match element (index 0) -- the 6
  // remaining entries ARE [year,month,day,hour,min,sec] with no offset, so
  // this destructure must NOT have a leading skipped slot (the original
  // off-by-one shifted every value down one field and left `s` undefined,
  // which made Date.UTC(...) return NaN and threw RangeError: Invalid time
  // value inside Intl.DateTimeFormat -- caught by safeCollectCompany()'s
  // try/catch with no logging, silently degrading the ENTIRE roster to an
  // empty array; found via the console.error added to that catch block).
  const [y, mo, d, h, mi, s] = m.slice(1).map(Number);
  for (const offsetHours of [4, 5]) {
    const utcMs = Date.UTC(y, mo - 1, d, h + offsetHours, mi, s);
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", hour12: false,
    }).formatToParts(new Date(utcMs));
    const hourBack = Number(parts.find((p) => p.type === "hour")?.value) % 24;
    const minBack = Number(parts.find((p) => p.type === "minute")?.value);
    if (hourBack === h && minBack === mi) return new Date(utcMs).toISOString();
  }
  return new Date(Date.UTC(y, mo - 1, d, h + 4, mi, s)).toISOString();
}

// ─── CREW-2 R4 helpers (2026-09-14): quietReason generation. Kept local to
//     this file (not imported from components/hq/palette.ts, even though
//     lib/useMotionEvents.ts sets a precedent for lib->components/hq
//     imports) because etHHMM below needs a DIFFERENT contract than
//     palette.ts's hhmmFromEtIso -- this one converts a genuine UTC ISO
//     string (fs mtimes, Date#toISOString(), this file's own etLikeToIso()
//     output) through a REAL timezone conversion, where hhmmFromEtIso just
//     regexes ET wall-clock digits already embedded in a ts_et-style
//     string. Two different jobs, not a duplicate. ─────────────────────────

/** Real UTC ISO string -> "HH:MM" in America/New_York. Null in (or
 * unparsable) -> null out, never "??:??" baked into a sentence. */
function etHHMM(iso: string | null): string | null {
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

/** One line, collapsed whitespace, <=max chars -- local copy of palette.ts's
 * truncateOneLine (that one returns "no output yet" for empty input, which
 * is the wrong fallback for the short evidence fragments this file embeds
 * mid-sentence, e.g. a lane's `evidence` string inside a quietReason). */
function truncFor(text: string, max: number): string {
  const flat = text.replace(/\s+/g, " ").trim();
  return flat.length > max ? `${flat.slice(0, max - 1)}…` : flat;
}

/** "+$1,237" / "-$412" / "n/a" -- station-verdicts.jsonl's effect_pre/
 * effect_post are cents-precision floats; a roster line needs the headline
 * whole-dollar number, signed, thousands-separated. Null/NaN -> "n/a"
 * (never a fabricated "+$0"). */
function fmtSignedDollar(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "n/a";
  const rounded = Math.round(v);
  const sign = rounded >= 0 ? "+" : "-";
  return `${sign}$${Math.abs(rounded).toLocaleString("en-US")}`;
}

/** One crew-events.jsonl row (automation/state/station/crew-events.jsonl,
 * a NEW producer another builder -- CREW-RIG -- lands alongside this pass;
 * schema per that builder's own spec: {ts_et, who, kind, line, ref, to?},
 * capped 500 rows). Kept as a local, narrower type here rather than
 * importing one from lib/hq.ts's shared reader, since this file only ever
 * needs 4 fields off it. */
interface CrewEventLite { ts_et: string; who: string; kind: string; line: string; ref?: string; to?: string }

/** The last `n` crew-events.jsonl rows for one persona, oldest-first within
 * that slice. Reads a 200-row tail of the (≤500-row) file and filters
 * client-side rather than a second file format -- this file has no other
 * per-persona index. Fail-open to [] via readJsonlTail's own try/catch: a
 * file that doesn't exist yet (CREW-RIG hasn't landed it) is a normal
 * not-there-yet state, not an error. */
async function readCrewEventsFor(personaName: string, n = 3): Promise<CrewEventLite[]> {
  const rows = await readJsonlTail<CrewEventLite>(path.join(ROOT, "automation/state/station/crew-events.jsonl"), 200);
  return rows.filter((r) => r?.who === personaName).slice(-n);
}

export interface PersonaState {
  name: string;
  emoji: string;
  color: string;
  role: string;
  soulFile: string;
  schedule: string;
  status: "GREEN" | "YELLOW" | "RED" | "IDLE";
  lastFireISO: string | null;
  lastFireResult: string;
  deliverable: { path: string; exists: boolean; mtimeISO: string | null; ageMin: number | null };
  logTail: Array<Record<string, unknown>>;
  recentOutput: string | null;
  guardrailsDeniedTools: string[];
  /** CREW-2 R4 (2026-09-14): why is this persona quiet RIGHT NOW, in one
   * sentence a viewer can act on -- null means genuinely current (status
   * GREEN, nothing to explain). Non-null strings follow a prefix convention
   * the HUD's pill derivation (lib/crew.ts) matches on: "no producer for "
   * -> GHOST, "yields " -> YIELDING, anything else (an overdue-vs-cadence
   * or "Gamma_X DISABLED" message) -> WAITING. Never a bare status dot --
   * see CLAUDE.md HQ FACE RULES ("needs-J = decisions only" is a different
   * rule; this is "never show a color with no reason"). */
  quietReason: string | null;
}

export interface Handoff {
  from: string;
  to: string;
  status: "OK" | "STALE" | "MISSING";
  evidence: string;
  reasonIfStale: string | null;
}

export interface PersonasBoard {
  generatedAt: string;
  todayET: string;
  personas: PersonaState[];
  handoffs: Handoff[];
  scheduledTasks: {
    auditHealth: string;
    activeCount: number;
    flagCount: number;
    nextFires: Array<{ task: string; nextRun: string | null; lastRun: string | null; result: number | null }>;
  };
  status: { tail: string };
  pendingWork: {
    chefInbox: Array<{ name: string; mtimeISO: string; ageMin: number; sizeBytes: number }>;
    chefCandidates: Array<{ name: string; mtimeISO: string; sizeBytes: number }>;
    treasuryDrafts: { exists: boolean; mtimeISO: string | null; preview: string | null };
    mistakesTail: string | null;
  };
  errors: string[];
}

// ---------- per-persona collectors ----------

export async function collectScout(): Promise<PersonaState> {
  const soul = path.join(ROOT, ".claude/agents/scout.md");
  const out = path.join(ROOT, "automation/scout/state/scout_output.json");
  const log = path.join(ROOT, "automation/scout/state/scout-log.jsonl");
  const mt = await mtimeISO(out);
  const ageMin = mt ? (Date.now() - new Date(mt).getTime()) / 60000 : null;
  const logTail = await readJsonlTail<Record<string, unknown>>(log, 3);
  const last = logTail[logTail.length - 1];
  const lastFire = (last?.fired_at as string) || null;
  const data = await readJson<Record<string, unknown>>(out);
  const preview = data
    ? `regime=${(data.risk_regime_call as { verdict?: string })?.verdict || "?"} | ${(data.scout_one_line_summary as string) || ""}`
    : null;
  const status: PersonaState["status"] = lastFire && ageMin !== null && ageMin < 24 * 60 ? "GREEN" : "IDLE";
  // R4 quietReason: Scout is a once-a-day fire -- "IDLE" here just means
  // more than 24h since its last real output, not a fault by itself.
  const quietReason: PersonaState["quietReason"] = status === "GREEN"
    ? null
    : lastFire
      ? `expected daily 05:30 ET via Gamma_ScoutPremarket, last fired ${etHHMM(lastFire) ?? "?"} ET (${Math.round((ageMin ?? 0) / 60)}h ago)`
      : "no producer for automation/scout/state/scout_output.json yet";
  return {
    name: "Scout",
    emoji: "🌍",
    color: "#3b82f6",
    role: "pre-market macro / news / catalysts",
    soulFile: ".claude/agents/scout.md",
    schedule: "daily 05:30 ET",
    status,
    lastFireISO: lastFire,
    lastFireResult: (last?.risk_regime as string) || "n/a",
    deliverable: { path: "automation/scout/state/scout_output.json", exists: !!data, mtimeISO: mt, ageMin },
    logTail,
    recentOutput: preview,
    quietReason,
    guardrailsDeniedTools: ["mcp__alpaca__place_*", "production doctrine edits"],
  };
}

/** One row of automation/state/station/sectors.json's own `rows` array --
 * mirrors setup/scripts/sector_rows.py's build_sector_rows() dict shape
 * (same fields lib/hq.ts's SectorRow type already names for the OTHER
 * reader of the SAME builder, sector_rows.py --json; sectors.json is a
 * different producer -- CREW-RIG's per-fire snapshot -- so this file keeps
 * its own narrow copy rather than importing lib/hq.ts's type for 2 fields). */
interface SectorsFileRow { lane: string; state: string; last_evidence_et: string; evidence: string; health: string }
interface SectorsFile {
  ts_et?: string;
  rows?: SectorsFileRow[];
  summary_line?: string;
  task_health?: { disabled?: string[]; failed_last_run?: string[]; total?: number };
}

/** Coach re-point (CREW-2, 2026-09-14): Coach's real job moved off the
 * crypto-gym (crypto/data/scorecards/*, whose tasks are parked -- see this
 * pass's own CLAUDE.md-adjacent brief) onto the Station's sectors table,
 * which fires every 30 min, 24/7, $0, including the RTH window where the
 * LLM half of the loop yields (setup/scripts/sector_rows.py build_sector_
 * rows() via station_facts.py). The producer (CREW-RIG, a parallel builder
 * this same pass) may not have landed automation/state/station/sectors.json
 * yet -- that is an honest WAITING state, not an error, and is rendered as
 * one rather than faking a row. */
export async function collectCoach(): Promise<PersonaState> {
  const sectorsPath = path.join(ROOT, "automation/state/station/sectors.json");
  const role = "sectors + rig health: one per-lane table with evidence timestamps every fire; RED lanes and dark tasks become cards";
  const schedule = "every 30 min via the Station loop (sector_rows.py build_sector_rows, station_facts.py)";
  const [data, crewEvents] = await Promise.all([
    readJson<SectorsFile>(sectorsPath),
    readCrewEventsFor("Coach"),
  ]);

  if (!data || !Array.isArray(data.rows)) {
    const waitMsg = "sectors.json not written yet — CREW-RIG builder landing it";
    const crewLast = crewEvents[crewEvents.length - 1] ?? null;
    return {
      name: "Coach",
      emoji: "🏋️",
      color: "#22c55e",
      role,
      soulFile: ".claude/agents/coach.md",
      schedule,
      status: "IDLE",
      lastFireISO: crewLast ? etLikeToIso(crewLast.ts_et) : null,
      lastFireResult: waitMsg,
      deliverable: { path: "automation/state/station/sectors.json", exists: false, mtimeISO: null, ageMin: null },
      logTail: [],
      recentOutput: crewLast ? crewLast.line : waitMsg,
      quietReason: `no producer for automation/state/station/sectors.json yet — CREW-RIG builder landing it`,
      guardrailsDeniedTools: ["mcp__alpaca__place_*"],
    };
  }

  const mt = data.ts_et ? etLikeToIso(data.ts_et) : null;
  const ageMin = mt ? (Date.now() - new Date(mt).getTime()) / 60000 : null;
  const rows = data.rows;
  const redLane = rows.find((r) => r.health === "red") ?? null;
  const anyWarn = rows.some((r) => r.health === "amber" || r.health === "frozen" || r.health === "zombie");
  const stale = ageMin === null || ageMin > 45;
  const status: PersonaState["status"] = redLane ? "RED" : anyWarn || stale ? "YELLOW" : "GREEN";
  const firstDisabled = data.task_health?.disabled?.[0] ?? null;

  let quietReason: PersonaState["quietReason"] = null;
  if (status !== "GREEN") {
    if (redLane) quietReason = `${redLane.lane} is RED — ${truncFor(redLane.evidence, 80)}`;
    else if (firstDisabled) quietReason = `${firstDisabled} DISABLED`;
    else if (stale) quietReason = `expected every 30 min via the Station loop, last evidence ${etHHMM(mt) ?? "?"} ET`;
    else quietReason = `a lane needs attention — ${truncFor(data.summary_line ?? "see sectors table", 80)}`;
  }

  const crewLast = crewEvents[crewEvents.length - 1] ?? null;
  const crewLastIso = crewLast ? etLikeToIso(crewLast.ts_et) : null;
  const useCrewEvent = !!crewLastIso && (!mt || crewLastIso > mt);

  return {
    name: "Coach",
    emoji: "🏋️",
    color: "#22c55e",
    role,
    soulFile: ".claude/agents/coach.md",
    schedule,
    status,
    lastFireISO: useCrewEvent ? crewLastIso : mt,
    lastFireResult: data.summary_line || `${rows.length} lane(s) tracked`,
    deliverable: { path: "automation/state/station/sectors.json", exists: true, mtimeISO: mt, ageMin },
    logTail: rows as unknown as Array<Record<string, unknown>>,
    recentOutput: useCrewEvent ? crewLast!.line : (data.summary_line ?? null),
    quietReason,
    guardrailsDeniedTools: ["mcp__alpaca__place_*"],
  };
}

export async function collectPilot(): Promise<PersonaState> {
  const decisions = path.join(ROOT, "automation/state/decisions.jsonl");
  const loopState = path.join(ROOT, "automation/state/loop-state.json");
  const today = todayET();
  const tail = await readJsonlTail<Record<string, unknown>>(decisions, 5);
  const todaysDecisions = tail.filter((d) => {
    const ts = (d.fire_at as string) || (d.timestamp as string) || "";
    return ts.startsWith(today);
  });
  const mt = await mtimeISO(loopState);
  const ageMin = mt ? (Date.now() - new Date(mt).getTime()) / 60000 : null;
  const loop = await readJson<Record<string, unknown>>(loopState);
  const lastFire = (tail[tail.length - 1]?.fire_at as string) || mt;
  const status: PersonaState["status"] = ageMin !== null && ageMin < 10 ? "GREEN" : "IDLE";
  // R4 quietReason: Pilot's OWN schedule is RTH-only (Rule 5's per-account
  // hours) -- most of a 24h day it is correctly, deliberately idle. Only
  // flag it when it's quiet DURING the window it's supposed to be ticking.
  const rth = isRegularTradingHours(nowEtMinutes(), nowEtDayOfWeek());
  const quietReason: PersonaState["quietReason"] = status === "GREEN"
    ? null
    : !rth
      ? "yields 09:30-15:55 ET (RTH) — Gamma_HeartbeatCore only ticks during market hours"
      : `expected every ~1-3 min during RTH, last decision ${etHHMM(lastFire) ?? "?"} ET — check Gamma_HeartbeatCore`;
  return {
    name: "Pilot",
    emoji: "✈️",
    color: "#ef4444",
    role: "LIVE 0DTE trader (refs heartbeat.md)",
    soulFile: ".claude/agents/pilot.md",
    schedule: "every 3 min market hours via Gamma_Heartbeat",
    status,
    lastFireISO: lastFire,
    lastFireResult: `${todaysDecisions.length} decisions today`,
    deliverable: { path: "automation/state/loop-state.json", exists: !!loop, mtimeISO: mt, ageMin },
    logTail: tail,
    recentOutput: loop ? `spy=${(loop.spy as { last?: number })?.last ?? "?"} last_bar=${(loop.last_bar_timestamp as number) || "?"}` : null,
    quietReason,
    guardrailsDeniedTools: ["doctrine edits — Pilot reads heartbeat.md, cannot modify it"],
  };
}

export async function collectAnalyst(): Promise<PersonaState> {
  const log = path.join(ROOT, "analysis/eod/_analyst-log.jsonl");
  const today = todayET();
  const digest = path.join(ROOT, "analysis/eod", `${today}.md`);
  const mt = await mtimeISO(digest);
  const ageMin = mt ? (Date.now() - new Date(mt).getTime()) / 60000 : null;
  const logTail = await readJsonlTail<Record<string, unknown>>(log, 3);
  const last = logTail[logTail.length - 1];
  const exists = await fileExists(digest);
  const preview = exists ? (await readText(digest, 800))?.split("\n").slice(0, 12).join("\n") || null : null;
  const lastFireISO = (last?.fired_at as string) || mt;
  // R4 quietReason: Analyst is a once-a-weekday fire -- no digest for
  // TODAY just means its 16:45 ET window hasn't produced one yet, not that
  // Analyst has never worked (a prior day's digest, if any, is named).
  const quietReason: PersonaState["quietReason"] = exists
    ? null
    : `expected 16:45 ET weekdays via Gamma_AnalystEodReview${lastFireISO ? `, last digest ${etHHMM(lastFireISO) ?? "?"} ET on a prior day` : " — no digest on file yet"}`;
  return {
    name: "Analyst",
    emoji: "🔬",
    color: "#a855f7",
    role: "post-trade review + Chef inbox feeder",
    soulFile: ".claude/agents/analyst.md",
    schedule: "weekdays 16:45 ET via Gamma_AnalystEodReview",
    status: exists ? "GREEN" : "IDLE",
    lastFireISO,
    lastFireResult: last ? `${(last.trades_audited as number) ?? "?"} trades, ${(last.rule_breaks as number) ?? "?"} breaks, ${(last.chef_inbox_added as number) ?? "?"} queued` : "no fires yet",
    deliverable: { path: `analysis/eod/${today}.md`, exists, mtimeISO: mt, ageMin },
    logTail,
    recentOutput: preview,
    quietReason,
    guardrailsDeniedTools: ["mcp__alpaca__place_*", "production doctrine edits", "journal/trades.csv writes (read-only)"],
  };
}

/** One tail row of analysis/recommendations/station-verdicts.jsonl -- real
 * shape verified against the live file this session (card_id + spec +
 * result.{n_pre,n_post,effect_pre,effect_post,verdict,detail}). */
interface StationVerdictRow {
  ts_et?: string;
  card_id?: string;
  result?: { n_pre?: number; n_post?: number; effect_pre?: number; effect_post?: number; verdict?: string; detail?: string };
}
interface IdeaBoardCardLite { id?: string; title?: string; status?: string }

/** Chef re-point (CREW-2, 2026-09-14): Chef's OLD deliverable
 * (strategy/candidates/_LEADERBOARD.md, fed by the retired conductor-era
 * flow) has no live producer any more. Chef's REAL work is now the idea-
 * loop scorer -- every board card in automation/state/station/ideas-
 * board.json gets a runnable test via setup/scripts/hypothesis_scorer.py
 * (station_loop.py's score_testing_cards()), which fires every ~30 min
 * through the Station loop, $0, including RTH. This reads the verdicts
 * ledger it writes and joins card_id -> title against the ideas board. */
export async function collectChef(): Promise<PersonaState> {
  const verdictsPath = path.join(ROOT, "analysis/recommendations/station-verdicts.jsonl");
  const ideasPath = path.join(ROOT, "automation/state/station/ideas-board.json");
  const role = "idea-loop owner: every board card gets a runnable test and a verdict from data";
  const schedule = "every ~30 min via the Station loop (score_testing_cards, hypothesis_scorer.py)";

  const [verdictTail, ideas, crewEvents] = await Promise.all([
    readJsonlTail<StationVerdictRow>(verdictsPath, 5),
    readJson<IdeaBoardCardLite[]>(ideasPath),
    readCrewEventsFor("Chef"),
  ]);

  const last = verdictTail[verdictTail.length - 1];
  const mt = last?.ts_et ? etLikeToIso(last.ts_et) : null;
  const ageMin = mt ? (Date.now() - new Date(mt).getTime()) / 60000 : null;
  const fresh = ageMin !== null && ageMin < 45;
  const status: PersonaState["status"] = !last ? "IDLE" : fresh ? "GREEN" : ageMin !== null && ageMin < 24 * 60 ? "YELLOW" : "IDLE";

  let nowLine: string | null = null;
  if (last) {
    const card = (ideas ?? []).find((c) => c.id === last.card_id) ?? null;
    const title = card?.title ?? last.card_id ?? "unknown card";
    const nPost = last.result?.n_post ?? null;
    const minNMatch = last.result?.detail ? /min_n=(\d+)/.exec(last.result.detail) : null;
    const minN = minNMatch ? Number(minNMatch[1]) : 10;
    nowLine = `scoring "${truncFor(title, 42)}" · n_post ${nPost ?? "?"}/${minN} · pre ${fmtSignedDollar(last.result?.effect_pre)}`;
  }

  const quietReason: PersonaState["quietReason"] = fresh
    ? null
    : !last
      ? "no producer for analysis/recommendations/station-verdicts.jsonl yet"
      : `expected every ~30 min via the Station loop, last verdict ${etHHMM(mt) ?? "?"} ET`;

  const crewLast = crewEvents[crewEvents.length - 1] ?? null;
  const crewLastIso = crewLast ? etLikeToIso(crewLast.ts_et) : null;
  const useCrewEvent = !!crewLastIso && (!mt || crewLastIso > mt);

  return {
    name: "Chef",
    emoji: "👨‍🍳",
    color: "#f97316",
    role,
    soulFile: ".claude/agents/chef.md",
    schedule,
    status,
    lastFireISO: useCrewEvent ? crewLastIso : mt,
    lastFireResult: last ? `${last.result?.verdict ?? "pending"} n_pre=${last.result?.n_pre ?? "?"} n_post=${last.result?.n_post ?? "?"}` : "no fires yet",
    deliverable: { path: "analysis/recommendations/station-verdicts.jsonl", exists: !!last, mtimeISO: mt, ageMin },
    logTail: verdictTail as unknown as Array<Record<string, unknown>>,
    recentOutput: useCrewEvent ? crewLast!.line : nowLine,
    quietReason,
    guardrailsDeniedTools: ["mcp__alpaca__place_*", "production doctrine edits", "params*.json edits"],
  };
}

export async function collectTreasurer(): Promise<PersonaState> {
  const log = path.join(ROOT, "analysis/treasury/_treasurer-log.jsonl");
  const drafts = path.join(ROOT, "analysis/treasury/draft-params-changes.md");
  const mt = await mtimeISO(drafts);
  const ageMin = mt ? (Date.now() - new Date(mt).getTime()) / 60000 : null;
  const logTail = await readJsonlTail<Record<string, unknown>>(log, 3);
  const last = logTail[logTail.length - 1];
  const preview = await readText(drafts, 800);
  const status: PersonaState["status"] = last ? "GREEN" : "IDLE";
  // R4 quietReason: Treasurer's whole job is Sunday-only -- being quiet
  // Mon-Sat is correct scheduled behavior (YIELDING), not a fault; only a
  // missing Sunday review is actually overdue (WAITING).
  const quietReason: PersonaState["quietReason"] = status === "GREEN"
    ? null
    : nowEtDayOfWeek() === 0
      ? "expected Sundays 16:00 ET via Gamma_TreasurerWeekly, no review yet today"
      : "yields Mon-Sat — weekly review fires Sundays 16:00 ET via Gamma_TreasurerWeekly";
  return {
    name: "Treasurer",
    emoji: "💰",
    color: "#eab308",
    role: "risk + money management auditor",
    soulFile: ".claude/agents/treasurer.md",
    schedule: "Sundays 16:00 ET via Gamma_TreasurerWeekly",
    status,
    lastFireISO: (last?.fired_at as string) || mt,
    lastFireResult: last ? `${(last.verdict as string) || "?"} Safe=$${(last.safe_equity as number) ?? "?"} Bold=$${(last.bold_equity as number) ?? "?"}` : "no fires yet",
    deliverable: { path: "analysis/treasury/draft-params-changes.md", exists: !!preview, mtimeISO: mt, ageMin },
    logTail,
    recentOutput: preview?.split("\n").slice(0, 14).join("\n") || null,
    quietReason,
    guardrailsDeniedTools: ["mcp__alpaca__place_*", "params*.json edits (DRAFT only)"],
  };
}

export async function collectGammaManager(): Promise<PersonaState> {
  // Roster-truth fix (2026-09-13): this collector was reading
  // manager-log.jsonl (an unrelated Ollama-model-pick log) and
  // analysis/daily-brief/{today}.md (doesn't exist most days) -- neither
  // has anything to do with what "Gamma (Manager)" actually means on the
  // roster: the Station loop that fires every 30 min. J's own mapping:
  // "Gamma (Manager) = loop-ledger.jsonl last row (ts + status +
  // cards_added) and conductor-outcomes.jsonl if newer."
  const loopLedger = path.join(ROOT, "automation/state/station/loop-ledger.jsonl");
  const conductorOutcomes = path.join(ROOT, "automation/state/conductor-outcomes.jsonl");
  const [ledgerTail, outcomesTail] = await Promise.all([
    readJsonlTail<{ ts_et?: string; status?: string; reason?: string; cards_added?: number; board_size?: number }>(loopLedger, 3),
    readJsonlTail<{ fired_at?: string; task_id?: string; items_added?: number; note?: string }>(conductorOutcomes, 30),
  ]);
  const lastLedger = ledgerTail[ledgerTail.length - 1];
  // conductor-outcomes.jsonl is shared across multiple tasks -- filter to
  // the station task before comparing "if newer" against the ledger.
  const stationOutcomes = outcomesTail.filter((r) => r.task_id === "Gamma_Station");
  const lastOutcome = stationOutcomes[stationOutcomes.length - 1];

  const ledgerIso = lastLedger?.ts_et ? etLikeToIso(lastLedger.ts_et) : null;
  const outcomeIso = lastOutcome?.fired_at ?? null; // already real ISO (e.g. "...+00:00")
  const useOutcome = !!outcomeIso && (!ledgerIso || outcomeIso > ledgerIso);
  const lastFireISO = useOutcome ? outcomeIso : ledgerIso;

  const ledgerStatus = lastLedger?.status; // "ok" | "yielded" | "error" | ...
  const status: PersonaState["status"] =
    ledgerStatus === "error" ? "RED" : ledgerStatus === "yielded" ? "YELLOW" : lastFireISO ? "GREEN" : "IDLE";

  const lastFireResult = useOutcome
    ? `${lastOutcome!.task_id}${lastOutcome!.note ? ": " + lastOutcome!.note : ""} (${lastOutcome!.items_added ?? 0} items added)`
    : lastLedger
      ? `${lastLedger.status}${lastLedger.reason ? " -- " + lastLedger.reason : ""}, cards_added=${lastLedger.cards_added ?? 0}`
      : null;

  // R4 quietReason: "yielded" is Gamma's OWN Station loop deliberately
  // skipping a fire (GPU busy / RTH / gaming mode etc, per its ledger's own
  // `reason` field) -- that's the YIELDING case, not an error. "error" is a
  // genuine fault (RED). No ledger row at all is a true ghost.
  const quietReason: PersonaState["quietReason"] = status === "GREEN"
    ? null
    : status === "RED"
      ? `error${lastLedger?.reason ? ` — ${lastLedger.reason}` : ""} — check Gamma_Station`
      : status === "YELLOW"
        ? `yields${lastLedger?.reason ? ` — ${lastLedger.reason}` : ""}`
        : "no producer for automation/state/station/loop-ledger.jsonl yet";
  return {
    name: "Gamma (Manager)",
    emoji: "🎩",
    color: "#ec4899",
    role: "conductor / Station loop / J's briefing writer",
    soulFile: ".claude/agents/gamma.md (CLAUDE.md is project soul)",
    schedule: "every 30 min via the Station loop (Gamma_Station)",
    status,
    lastFireISO,
    lastFireResult: lastFireResult ?? "no fires yet",
    deliverable: { path: "automation/state/station/loop-ledger.jsonl", exists: !!lastLedger, mtimeISO: lastFireISO, ageMin: lastFireISO ? (Date.now() - new Date(lastFireISO).getTime()) / 60000 : null },
    logTail: ledgerTail,
    recentOutput: lastFireResult,
    quietReason,
    guardrailsDeniedTools: ["mcp__alpaca__place_*", "production doctrine edits"],
  };
}

// ---------- handoffs ----------

export async function computeHandoffs(): Promise<Handoff[]> {
  const today = todayET();
  const handoffs: Handoff[] = [];

  // Scout → Premarket
  const scoutOut = path.join(ROOT, "automation/scout/state/scout_output.json");
  const todayBias = path.join(ROOT, "automation/state/today-bias.json");
  const scoutMt = await mtimeISO(scoutOut);
  const biasMt = await mtimeISO(todayBias);
  let scoutToPremarketStatus: Handoff["status"] = "MISSING";
  let scoutEvidence = "no scout_output.json";
  let scoutReason: string | null = "Scout hasn't fired yet today";
  if (scoutMt && biasMt) {
    const scoutTime = new Date(scoutMt).getTime();
    const biasTime = new Date(biasMt).getTime();
    scoutToPremarketStatus = biasTime > scoutTime ? "OK" : "STALE";
    scoutEvidence = `scout @ ${scoutMt}, bias @ ${biasMt}`;
    scoutReason = scoutToPremarketStatus === "STALE" ? "today-bias.json is older than scout_output.json" : null;
  } else if (scoutMt) {
    scoutToPremarketStatus = "STALE";
    scoutEvidence = "scout_output present, no today-bias.json";
    scoutReason = "Premarket hasn't fired yet";
  }
  handoffs.push({ from: "🌍 Scout", to: "Premarket", status: scoutToPremarketStatus, evidence: scoutEvidence, reasonIfStale: scoutReason });

  // Premarket → Pilot
  const decisions = path.join(ROOT, "automation/state/decisions.jsonl");
  const decisionsMt = await mtimeISO(decisions);
  let pmToPilot: Handoff["status"] = "MISSING";
  let pmEvidence = "no decisions.jsonl";
  let pmReason: string | null = "Pilot hasn't fired today";
  if (biasMt && decisionsMt) {
    const decisionsTail = await readJsonlTail<Record<string, unknown>>(decisions, 1);
    const last = decisionsTail[0];
    const lastFire = (last?.fire_at as string) || "";
    pmToPilot = lastFire.startsWith(today) ? "OK" : "STALE";
    pmEvidence = `bias @ ${biasMt}, last decision @ ${lastFire || "?"}`;
    pmReason = pmToPilot === "STALE" ? "no decisions today yet" : null;
  }
  handoffs.push({ from: "Premarket", to: "✈️ Pilot", status: pmToPilot, evidence: pmEvidence, reasonIfStale: pmReason });

  // Pilot → Analyst
  const eod = path.join(ROOT, "analysis/eod", `${today}.md`);
  const eodMt = await mtimeISO(eod);
  let pilotToAnalyst: Handoff["status"] = "MISSING";
  let panEvidence = "no analyst digest today";
  let panReason: string | null = "Analyst hasn't fired today (fires 16:45 ET weekdays)";
  if (eodMt) {
    pilotToAnalyst = "OK";
    panEvidence = `analyst digest @ ${eodMt}`;
    panReason = null;
  }
  handoffs.push({ from: "✈️ Pilot", to: "🔬 Analyst", status: pilotToAnalyst, evidence: panEvidence, reasonIfStale: panReason });

  // Analyst → Chef inbox
  const inboxDir = path.join(ROOT, "strategy/candidates/_chef-inbox");
  const inbox = await dirListing(inboxDir);
  const recentInbox = inbox.filter((f) => f.name.startsWith(today));
  const staleInbox = inbox.filter((f) => {
    const age = (Date.now() - new Date(f.mtimeISO).getTime()) / (1000 * 60 * 60 * 24);
    return age > 7;
  });
  handoffs.push({
    from: "🔬 Analyst",
    to: "👨‍🍳 Chef inbox",
    status: recentInbox.length > 0 ? "OK" : inbox.length > 0 ? "STALE" : "MISSING",
    evidence: `${inbox.length} items total, ${recentInbox.length} from today, ${staleInbox.length} stale (>7d)`,
    reasonIfStale: staleInbox.length > 0 ? `${staleInbox.length} item(s) >7 days old in inbox — Chef should pick up` : null,
  });

  // Chef → Leaderboard
  const lb = path.join(ROOT, "strategy/candidates/_LEADERBOARD.md");
  const lbMt = await mtimeISO(lb);
  handoffs.push({
    from: "👨‍🍳 Chef",
    to: "_LEADERBOARD",
    status: lbMt ? "OK" : "MISSING",
    evidence: lbMt ? `leaderboard @ ${lbMt}` : "no leaderboard yet",
    reasonIfStale: null,
  });

  // Treasurer → J ratification
  const draftMt = await mtimeISO(path.join(ROOT, "analysis/treasury/draft-params-changes.md"));
  let trStatus: Handoff["status"] = "MISSING";
  let trEvidence = "no DRAFT changes file";
  let trReason: string | null = "Treasurer hasn't fired or has no proposed changes";
  if (draftMt) {
    const ageDays = (Date.now() - new Date(draftMt).getTime()) / (1000 * 60 * 60 * 24);
    trStatus = ageDays > 14 ? "STALE" : "OK";
    trEvidence = `draft @ ${draftMt} (${ageDays.toFixed(1)}d old)`;
    trReason = trStatus === "STALE" ? "DRAFT params changes pending >14 days without J ratification" : null;
  }
  handoffs.push({ from: "💰 Treasurer", to: "J ratification", status: trStatus, evidence: trEvidence, reasonIfStale: trReason });

  return handoffs;
}

// ---------- scheduled tasks ----------

interface AuditFlag { flag: string; task: string; note: string }
interface AuditJson {
  health?: string;
  active_registered?: number;
  flags_count?: number;
  flags?: AuditFlag[];
}

export async function getScheduledTaskStatus() {
  const audit = await readJson<AuditJson>(path.join(ROOT, "automation/state/scheduled-tasks-audit.json"));
  let nextFires: Array<{ task: string; nextRun: string | null; lastRun: string | null; result: number | null }> = [];
  try {
    const out = execSync(
      `powershell -NoProfile -NonInteractive -Command "Get-ScheduledTask -TaskName 'Gamma_*' | Where-Object { $_.State -ne 'Disabled' } | ForEach-Object { $info = $_ | Get-ScheduledTaskInfo; [PSCustomObject]@{ task = $_.TaskName; nextRun = if ($info.NextRunTime) { $info.NextRunTime.ToString('o') } else { $null }; lastRun = if ($info.LastRunTime -and $info.LastRunTime.Year -gt 2020) { $info.LastRunTime.ToString('o') } else { $null }; result = $info.LastTaskResult } } | ConvertTo-Json -Compress"`,
      { encoding: "utf8", timeout: 8000 },
    );
    nextFires = JSON.parse(out);
    if (!Array.isArray(nextFires)) nextFires = [nextFires as unknown as { task: string; nextRun: string | null; lastRun: string | null; result: number | null }];
    nextFires.sort((a, b) => (a.nextRun || "").localeCompare(b.nextRun || ""));
  } catch {
    nextFires = [];
  }
  return {
    auditHealth: audit?.health || "UNKNOWN",
    activeCount: audit?.active_registered || 0,
    flagCount: audit?.flags_count || 0,
    nextFires,
  };
}

// ---------- pending work ----------

export async function getPendingWork() {
  const inboxDir = path.join(ROOT, "strategy/candidates/_chef-inbox");
  const inbox = await dirListing(inboxDir);
  const chefInbox = inbox.map((f) => ({
    name: f.name,
    mtimeISO: f.mtimeISO,
    ageMin: (Date.now() - new Date(f.mtimeISO).getTime()) / 60000,
    sizeBytes: f.sizeBytes,
  }));

  const candidatesDir = path.join(ROOT, "strategy/candidates");
  const cands = await dirListing(candidatesDir);
  const chefCandidates = cands.filter((f) => f.name.endsWith(".md") && !f.name.startsWith("_")).slice(0, 10);

  const treasuryDraftsPath = path.join(ROOT, "analysis/treasury/draft-params-changes.md");
  const treasuryDraftsMt = await mtimeISO(treasuryDraftsPath);
  const treasuryPreview = await readText(treasuryDraftsPath, 1200);

  const mistakes = await readText(path.join(ROOT, "journal/mistakes.md"), 1500);
  const mistakesTail = mistakes ? mistakes.split("\n").slice(-30).join("\n") : null;

  return {
    chefInbox,
    chefCandidates,
    treasuryDrafts: {
      exists: !!treasuryDraftsMt,
      mtimeISO: treasuryDraftsMt,
      preview: treasuryPreview,
    },
    mistakesTail,
  };
}

/** Convenience bundle for /api/hq's `data.company` (Company Mode, 2026-09-13):
 * the 7 personas in the SAME fixed order the personas route always returned
 * (Gamma-Manager first), plus handoffs. Pure composition of the functions
 * above -- no new logic. */
export async function collectCompany(): Promise<{ personas: PersonaState[]; handoffs: Handoff[] }> {
  const [gamma, scout, coach, pilot, analyst, chef, treasurer] = await Promise.all([
    collectGammaManager(), collectScout(), collectCoach(), collectPilot(),
    collectAnalyst(), collectChef(), collectTreasurer(),
  ]);
  const personas = [gamma, scout, coach, pilot, analyst, chef, treasurer];
  const handoffs = await computeHandoffs();
  return { personas, handoffs };
}

// LIVE-AGENTS pass (2026-09-14, J: "use it to build itself ... watch it spawn
// up agents and see how they move and interact in the world"). Today Scene.tsx
// only ever animates PERSONAS (Scout/Chef/Coach/... from crew-events.jsonl) --
// real Claude Code sessions and subagents (this very session included) are
// invisible even though every tool call already writes a pulse.jsonl row
// (setup/hooks/pulse.py#record, SubagentStart -> event "spawn"). This module
// turns that ALREADY-PRODUCED file into the roster /api/hq's new `liveAgents`
// field serves.
//
// Import-light by design, same convention as lib/hq-learn.ts's own header:
// only node:fs/node:path (no sibling lib/*.ts value import, no three.js, no
// react) so the pure combiner (buildLiveAgents) stays trivially unit-testable
// via plain `node --test` and this module can never create a circular or
// SSR-unsafe dependency. The fs reader (readPulseTail) is the one function
// here that touches disk; every other export is a pure function of already-
// parsed data.
//
// TIMESTAMP HANDLING (load-bearing, see CLAUDE.md's own TZ lesson --
// "Ohio->Colorado: rig runs MT, NOT ET"): pulse.jsonl's `ts` field is a NAIVE
// local-time ISO string in the box's own local timezone (US Mountain) --
// NOT ET (ET = local+2h) and NOT UTC. This module therefore never calls
// `Date.parse` on it as if it carried a real offset; instead it parses the
// raw Y-M-D H:M:S digits into a Date.UTC-of-its-own-digits "local pseudo-ms"
// value (parseLocalTsPseudoMs), and compares that against `nowLocalPseudoMs`
// -- the CURRENT wall-clock time expressed the identical way, via this
// process's own local Date getters (getFullYear/getHours/...), which read
// the SAME local timezone the box (and therefore pulse.py's own
// dt.datetime.now()) is already in. Neither value is a real UTC instant, but
// their DELTA is a correct "seconds elapsed on this box's own clock" figure,
// the same "two values built the same wrong way are still comparable" trick
// lib/hq-learn.ts's own parseEtLikeMinutes/nowEtMinutes pair uses for ET.

import { promises as fs } from "node:fs";
import type { FileHandle } from "node:fs/promises";
import path from "node:path";

const WORKSPACE_ROOT = process.env.GAMMA_WORKSPACE ?? "C:\\Users\\jackw\\Desktop\\42";
// Matches setup/hooks/pulse.py#_PULSE's own GAMMA_PULSE_PATH override (the
// end-to-end hook tests redirect the sink there so pytest runs never append
// fake rows to production telemetry) -- this reader must honor the same
// override or it would read production data while a test suite runs.
const PULSE_PATH = process.env.GAMMA_PULSE_PATH
  || path.join(WORKSPACE_ROOT, "automation", "state", "hooks", "pulse.jsonl");

// pulse.py's own MAX_ROWS=2000/_TRIM_SLACK=400 (setup/hooks/pulse.py) caps the
// whole file at ~2400 short JSON lines -- comfortably under 512KB in
// practice. 128KB read from the tail is a generous multiple of the ~500
// lines this task asks for while never requiring a whole-file read even if a
// future change raises that cap.
const TAIL_READ_BYTES = 131072;
const TAIL_MAX_LINES = 500;

const IDLE_TIMEOUT_MS = 3 * 60_000; // "no row for 3 min = agent leaves" (task spec)
const SPAWN_WINDOW_MS = 15_000; // first ~15s of an agent's own visible life reads as "just arrived"
const COOLING_WINDOW_MS = 30_000; // last ~30s before the idle timeout reads as "about to leave"
const MAX_AGENTS = 8;
const DETAIL_MAX_CHARS = 60;

// ─── Wire types ─────────────────────────────────────────────────────────────

export type LiveAgentZone = "build" | "lab" | "ops" | "docs" | "hub";
export type LiveAgentState = "spawning" | "active" | "cooling";

export interface LiveAgent {
  id: string;
  label: string;
  firstTs: string;
  lastTs: string;
  lastDetail: string;
  state: LiveAgentState;
  /** A real walk-graph node id from dashboard/components/hq/layout.ts
   * (buildWalkGraph's own node-id convention) -- never an invented place.
   * See ZONE_NODE_ID below for the exact mapping. */
  targetZone: string;
}

export interface PulseRow {
  ts: string;
  event: string;
  session_id: string;
  agent_id: string;
  agent_type: string;
  cwd: string;
  tool: string;
  to: string;
  detail: string;
}

// ─── Pure: local-time pseudo-ms (zero fs, unit-tested) ─────────────────────

/** "2026-09-14T21:51:01" (or a space instead of "T") -> a Date.UTC-of-its-
 * own-digits pseudo-ms. Null on anything that doesn't match -- a malformed
 * row's ts must never silently become "now" (that would hide a stale agent
 * as fresh). */
export function parseLocalTsPseudoMs(ts: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/.exec(ts ?? "");
  if (!m) return null;
  const [, y, mo, d, h, mi, s] = m.map(Number);
  return Date.UTC(y, mo - 1, d, h, mi, s);
}

/** `nowMs` (a real epoch ms, e.g. Date.now() or a fixed test instant)
 * re-expressed the SAME "local digits via Date.UTC" way as
 * parseLocalTsPseudoMs, using THIS process's own local Date getters --
 * correct exactly because pulse.py's `ts` and this process both run in the
 * box's own local timezone (see this file's own header). */
export function nowLocalPseudoMs(nowMs: number = Date.now()): number {
  const d = new Date(nowMs);
  return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate(), d.getHours(), d.getMinutes(), d.getSeconds());
}

// ─── Pure: parsing + zone classification ───────────────────────────────────

/** Splits raw pulse.jsonl tail TEXT into parsed rows, skipping malformed
 * lines (a truncated first line from a byte-offset tail read, a corrupt
 * JSON row, or a row missing the fields this module needs) rather than
 * throwing -- one bad line must never blank the whole roster. Caps to the
 * last TAIL_MAX_LINES non-empty lines (defensive: readPulseTail already
 * byte-limits the read, this is a second, cheap belt-and-suspenders cap on
 * line COUNT for a caller that hands this function a larger text blob,
 * e.g. a test fixture). */
export function parsePulseLines(text: string): PulseRow[] {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const tail = lines.slice(-TAIL_MAX_LINES);
  const rows: PulseRow[] = [];
  for (const line of tail) {
    let parsed: unknown;
    try {
      parsed = JSON.parse(line);
    } catch {
      continue; // malformed JSON (or a byte-tail-truncated first line) -- skip, never throw
    }
    if (!parsed || typeof parsed !== "object") continue;
    const rec = parsed as Record<string, unknown>;
    if (typeof rec.ts !== "string" || typeof rec.event !== "string") continue;
    rows.push({
      ts: rec.ts,
      event: rec.event,
      session_id: typeof rec.session_id === "string" ? rec.session_id : "",
      agent_id: typeof rec.agent_id === "string" ? rec.agent_id : "",
      agent_type: typeof rec.agent_type === "string" ? rec.agent_type : "",
      cwd: typeof rec.cwd === "string" ? rec.cwd : "",
      tool: typeof rec.tool === "string" ? rec.tool : "",
      to: typeof rec.to === "string" ? rec.to : "",
      detail: typeof rec.detail === "string" ? rec.detail : "",
    });
  }
  return rows;
}

/** dashboard/ -> the HQ/build area; backtest/ -> research/lab; setup/ or
 * automation/ -> ops; markdown/ -> library/docs; otherwise the hub -- per
 * this task's own zone-mapping spec. Checked in this fixed priority order
 * against a path-bearing string (never against `cwd` -- only `detail`/`to`,
 * per the task's own field list) so a command that happens to mention two
 * areas resolves deterministically rather than on whichever substring the
 * regex engine finds first. Backslash-normalized first (Windows paths in
 * `detail`, e.g. "Editing hq-agents.ts" derived from a Windows path, or a
 * raw "Ran: ..." command string, may use either separator). */
const ZONE_RULES: ReadonlyArray<readonly [string, LiveAgentZone]> = [
  ["dashboard/", "build"],
  ["backtest/", "lab"],
  ["setup/", "ops"],
  ["automation/", "ops"],
  ["markdown/", "docs"],
];

export function classifyZone(text: string): LiveAgentZone {
  const norm = (text || "").replace(/\\/g, "/").toLowerCase();
  for (const [needle, zone] of ZONE_RULES) {
    if (norm.includes(needle)) return zone;
  }
  return "hub";
}

/** Real walk-graph node ids (dashboard/components/hq/layout.ts's own
 * buildWalkGraph naming) each zone resolves to -- never an invented place.
 * "build" -> the smart board wall (the HQ's own screen/build surface);
 * "lab" -> bay-desk-0 (one of the 8 real lane bays, used generically as
 * "the lab bench" for non-lane research work); "ops"/"docs" -> the two
 * named ambient hub-interior points (layout.ts's PURPOSEFUL_TARGETS,
 * "core"/"ideas-wall", already wired into buildWalkGraph as
 * "ambient-core"/"ambient-ideas-wall"); "hub" -> hub-center itself. */
export const ZONE_NODE_ID: Record<LiveAgentZone, string> = {
  build: "smart-board",
  lab: "bay-desk-0",
  ops: "ambient-core",
  docs: "ambient-ideas-wall",
  hub: "hub-center",
};

/** Where a spawning agent first appears -- hub-center (layout.ts's own HUB
 * origin), the one node every walk-graph path already routes through, so a
 * fresh arrival never needs a special-cased entry edge. */
export const ENTRY_NODE_ID = "hub-center";

function shortDetail(row: PulseRow): string {
  const raw = row.detail || row.to || row.tool || row.event || "";
  const flat = raw.replace(/\s+/g, " ").trim();
  if (!flat) return "…";
  return flat.length > DETAIL_MAX_CHARS ? `${flat.slice(0, DETAIL_MAX_CHARS - 1)}…` : flat;
}

// ─── Pure combiner (fixture-tested: dashboard/tests/hq-agents.test.ts) ─────

interface AgentAcc {
  id: string;
  label: string;
  firstTs: string;
  firstTsPseudoMs: number;
  lastTs: string;
  lastTsPseudoMs: number;
  lastDetail: string;
  zone: LiveAgentZone;
}

/** Groups rows by agent_id (a real subagent), or by session_id when
 * agent_id is "" (a main session, per pulse.py's own record() comment: "an
 * empty agent_id means the parent/main session"). Rows with neither id are
 * defensively skipped (should never happen -- pulse.py always emits at
 * least session_id -- but this module never trusts an upstream invariant it
 * hasn't itself verified against the row in hand). Keeps up to MAX_AGENTS
 * groups whose most recent row is within IDLE_TIMEOUT_MS of `nowMs`, most
 * recent first -- a group with no row inside that window has already
 * "left" and is silently omitted, matching this task's own idle-timeout
 * despawn rule. Pure: takes already-parsed rows + an explicit `nowMs`, so a
 * test can pin both without touching the filesystem or the real clock. */
export function buildLiveAgents(rows: PulseRow[], nowMs: number = Date.now()): LiveAgent[] {
  const groups = new Map<string, AgentAcc>();

  for (const row of rows) {
    const key = row.agent_id ? row.agent_id : row.session_id ? `session:${row.session_id}` : null;
    if (!key) continue;
    const tsPseudo = parseLocalTsPseudoMs(row.ts);
    if (tsPseudo === null) continue; // malformed ts -- never guess "now" for a row we can't date

    const zone = classifyZone(`${row.to} ${row.detail}`);
    const existing = groups.get(key);
    if (!existing) {
      groups.set(key, {
        id: key,
        label: row.agent_id ? (row.agent_type || "agent") : "session",
        firstTs: row.ts,
        firstTsPseudoMs: tsPseudo,
        lastTs: row.ts,
        lastTsPseudoMs: tsPseudo,
        lastDetail: shortDetail(row),
        zone,
      });
      continue;
    }
    // Rows are read from the file in append (chronological) order, but this
    // loop makes no assumption of that -- first/last are tracked by actual
    // pseudo-ms comparison, so an out-of-order tail slice still produces a
    // correct result.
    if (tsPseudo < existing.firstTsPseudoMs) {
      existing.firstTs = row.ts;
      existing.firstTsPseudoMs = tsPseudo;
    }
    if (tsPseudo >= existing.lastTsPseudoMs) {
      existing.lastTs = row.ts;
      existing.lastTsPseudoMs = tsPseudo;
      existing.lastDetail = shortDetail(row);
      // A real zone signal only ever REPLACES the stale one on a later row
      // -- a row with no path in its own detail/to (e.g. a bare "Ran: ls")
      // must never blank an agent back to "hub" just because it's the most
      // recent row seen.
      if (zone !== "hub") existing.zone = zone;
      if (row.agent_id && row.agent_type) existing.label = row.agent_type;
    }
  }

  const nowPseudo = nowLocalPseudoMs(nowMs);
  const alive = Array.from(groups.values()).filter((a) => nowPseudo - a.lastTsPseudoMs <= IDLE_TIMEOUT_MS);
  alive.sort((a, b) => b.lastTsPseudoMs - a.lastTsPseudoMs);

  return alive.slice(0, MAX_AGENTS).map((a) => {
    const age = nowPseudo - a.lastTsPseudoMs;
    const sinceFirst = nowPseudo - a.firstTsPseudoMs;
    let state: LiveAgentState = "active";
    if (sinceFirst <= SPAWN_WINDOW_MS) state = "spawning";
    else if (age >= IDLE_TIMEOUT_MS - COOLING_WINDOW_MS) state = "cooling";
    return {
      id: a.id,
      label: a.label,
      firstTs: a.firstTs,
      lastTs: a.lastTs,
      lastDetail: a.lastDetail,
      state,
      targetZone: ZONE_NODE_ID[a.zone],
    };
  });
}

// ─── fs reader -- fail-open, never throws ──────────────────────────────────

/** Reads only the TAIL of pulse.jsonl (last TAIL_READ_BYTES bytes, never the
 * whole file -- this task's own hard requirement) via a byte-offset file
 * read. Fails open to "" on any error (missing file, permission issue,
 * mid-write race with pulse.py's own append) -- buildLiveAgents/
 * parsePulseLines both already handle an empty/partial-first-line input
 * gracefully, so an empty string here degrades to an empty roster, never a
 * throw. */
export async function readPulseTail(): Promise<string> {
  let fh: FileHandle | null = null;
  try {
    const stat = await fs.stat(PULSE_PATH);
    const start = Math.max(0, stat.size - TAIL_READ_BYTES);
    const length = stat.size - start;
    if (length <= 0) return "";
    fh = await fs.open(PULSE_PATH, "r");
    const buf = Buffer.alloc(length);
    await fh.read(buf, 0, length, start);
    return buf.toString("utf-8");
  } catch {
    return "";
  } finally {
    if (fh) {
      try {
        await fh.close();
      } catch {
        // best-effort close -- a failure here must never surface past this reader
      }
    }
  }
}

/** Entry point -- reads the live pulse.jsonl tail and returns the current
 * liveAgents roster. Wrapped in its own try/catch on top of readPulseTail's
 * own fail-open guard (same belt-and-suspenders convention as
 * lib/hq-learn.ts#readHqLearn) so a bug here can only ever degrade /api/hq's
 * `liveAgents` field to an empty list plus an `error` string, never 500 the
 * whole route. */
export async function readLiveAgents(): Promise<{ agents: LiveAgent[]; error?: string }> {
  try {
    const text = await readPulseTail();
    const rows = parsePulseLines(text);
    return { agents: buildLiveAgents(rows) };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("[hq-agents] readLiveAgents() threw past readPulseTail's own fail-open guard:", err);
    return { agents: [], error: `readLiveAgents failed: ${message}` };
  }
}

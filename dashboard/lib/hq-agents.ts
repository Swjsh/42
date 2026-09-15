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

// HQ BUG-3 FIX (2026-09-15, coordinator-measured): TAIL_MAX_LINES=500 was well under
// pulse.py's own MAX_ROWS=2000/_TRIM_SLACK=400 ring cap (setup/hooks/pulse.py), so under
// heavy fan-out (commit 645b5cff doubled the row rate with a matching "done" row per
// tool completion) the last 500 rows could span LESS than ACTIVE_TOOL_GRACE_MS's 20
// minutes -- measured tonight at 500 rows / 56-60 min -- and the START row of a still-
// open long tool call fell out of the tail before its grace window closed, so the agent
// vanished mid-work. Raised to the ring cap itself (2000) so the tail can never be
// smaller than the whole ring pulse.py ever keeps on disk. Measured at current load
// (2026-09-15, python one-liner over the live file): the last 2000 rows already span
// ~7h53m (15:58:52 -> 23:51:58 local), so 2000 rows comfortably clears the 25-minute
// bar this fix targets without needing a time-based row selection instead.
export const TAIL_MAX_LINES = 2000;
// Sized from the file's own measured row length, not guessed: 2223 real rows / 716915
// bytes = 322.5 bytes/row average (python: os.path.getsize / line count, same command
// as above). 2400 rows (pulse.py's hard ceiling before a trim fires: MAX_ROWS +
// _TRIM_SLACK) * 322.5 * 1.5 safety margin = 1,160,996 bytes -- rounded up to a clean
// 1,200,000 (~1.14MB) so a byte-offset read of TAIL_MAX_LINES=2000 JSONL lines never
// truncates the first line of the intended window even if average row size drifts
// somewhat larger than tonight's measurement.
const TAIL_READ_BYTES = 1_200_000;

const IDLE_TIMEOUT_MS = 3 * 60_000; // "no row for 3 min = agent leaves" (task spec)
const SPAWN_WINDOW_MS = 15_000; // first ~15s of an agent's own visible life reads as "just arrived"
const COOLING_WINDOW_MS = 30_000; // last ~30s before the idle timeout reads as "about to leave"
const MAX_AGENTS = 8;
const DETAIL_MAX_CHARS = 60;

// HQ BUG-1 FIX (2026-09-14, coordinator-verified): pulse.jsonl used to record a tool
// STARTING (PreToolUse) but never finishing, so IDLE_TIMEOUT_MS alone made one long
// foreground tool call (real case: a 244s probe) look like the agent walked away mid-
// work. setup/hooks/gamma_doctrine.py now also fires on PostToolUse/PostToolUseFailure
// and setup/hooks/pulse.py#record_tool_done writes a matching "done" row (same
// session_id/agent_id/tool). An agent whose latest tool-start row has no later "done"
// for that same tool counts as ACTIVE for up to this long after the start, instead of
// the normal 3-minute idle rule -- long enough to cover a slow foreground command, short
// enough that a row written before this fix (which can NEVER get a completion) still
// eventually expires rather than staying "active" forever.
const ACTIVE_TOOL_GRACE_MS = 20 * 60_000;
// The one completion event pulse.py's record_tool_done ever writes (see that function's
// own docstring: success and failure both write "done" -- only the `detail` differs).
const TOOL_COMPLETION_EVENT = "done";
// The three start-edge events pulse.py#classify() ever produces for a tool call
// (SendMessage -> "message", Agent/Task/Workflow -> "spawn", everything else it tracks
// -> "act"). Anything outside this set (e.g. Stop's own "idle" row) is not a tool call
// and never opens or closes a grace window.
const TOOL_START_EVENTS = new Set(["act", "message", "spawn"]);

// ─── Wire types ─────────────────────────────────────────────────────────────

export type LiveAgentZone = "build" | "lab" | "ops" | "docs" | "hub";
export type LiveAgentState = "spawning" | "active" | "cooling";

export interface LiveAgent {
  id: string;
  label: string;
  firstTs: string;
  lastTs: string;
  lastDetail: string;
  /** The full, un-classified, un-truncated last row text (BUBBLE-FIX,
   * 2026-09-15) -- kept for debugging even after `lastDetail` becomes a
   * short classified human phrase (bubbleText.ts#liveAgentBubbleAction).
   * Flattened to one line but otherwise exactly what pulse.py wrote. */
  rawDetail: string;
  /** Full, un-truncated (up to TOOLTIP_MAX_CHARS), leak-sanitized task text
   * for the hover tooltip (AGENT-IDENTITY pass, 2026-09-15) --
   * sanitizeTaskText(rawDetail) above, computed here (not client-side) so
   * the sanitizer stays inside this fs-importing module (LiveAgents.tsx's
   * own header: never a BY-VALUE import of this file into the client
   * bundle) and the client only ever consumes the already-safe string. */
  taskDetail: string;
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

/** Where a spawning agent first appears -- "campus-gate"
 * (layout.ts#buildWalkGraph's own new entry-node leaf, wired to arm 0's
 * T-junction; CAMPUS-GATE pass, 2026-09-15, J: agents should "spawn at the
 * gate, walk the hallways ... walk out and despawn when they go quiet," not
 * spawn/leave at the hub centre). MUST stay in sync with
 * components/hq/liveAgentWalk.ts#ENTRY_NODE_ID -- this module is
 * import-free by design (see this file's own header: no sibling lib/*.ts
 * value import, no three.js, no react) so it cannot import that constant;
 * kept as an identical string literal instead, backstopped by a sync test in
 * dashboard/tests/live-agent-walk.test.ts. */
export const ENTRY_NODE_ID = "campus-gate";

// ─── Live-agent bubble action (BUBBLE-FIX, 2026-09-15) ─────────────────────
//
// DEFECT (coordinator review, 2026-09-15 00:27 ET): a live agent's bubble
// showed raw shell text like "working · Ran: cd /c/Users/jackw/Desktop/42"
// -- truncated (this module's own 60-char DETAIL_MAX_CHARS, then
// LiveAgents.tsx's own 44-char truncateOneLine) BEFORE the verb or target
// ever appeared, because setup/hooks/pulse.py#_detail only ever writes
// "Ran: " + command[:100] for Bash/PowerShell (see that function for the
// exact prefix set: "Editing <basename>" for Edit/Write/NotebookEdit/
// MultiEdit, a bare description/name for Agent/Task/Workflow, the raw
// summary/message for SendMessage). `liveAgentBubbleAction` runs BEFORE any
// of that truncation (shortDetail below calls it on the FULL row, not a
// pre-cut slice) and classifies STRUCTURALLY off pulse.py's own real
// prefixes (`row.tool`, the literal tool_name pulse.py wrote) plus the
// command's own verb/target -- never invents a specific it can't see. A
// `cd ... && ...` preamble is stripped before classifying (a real shape
// this session's own pulse.jsonl already contains: "Ran: cd
// C:/.../dashboard && grep -n ...").
//
// Deliberately INLINED here rather than in components/hq/bubbleText.ts
// (this task's own first-draft location): bubbleText.ts pulls in
// @/lib/personas + @/lib/crew via the tsconfig path alias, which Node's own
// ESM loader (no bundler) cannot resolve when this file is loaded directly
// by `node --test tests/hq-agents.test.ts` (this module's own established
// zero-relative-import convention -- see that test file's header, "the fs
// reader is exercised live instead... matching this codebase's established
// convention"). This is the ONLY consumer that needs runtime classification
// (the client, LiveAgents.tsx, only ever displays the already-classified
// `lastDetail` string this module produces) so colocating it here adds no
// new cross-file relative import and keeps the whole file plain-node-test-
// able, matching classifyZone's own existing "pure classifier lives right
// next to its one caller" convention two screens up.
export interface LiveAgentBubbleRow {
  /** The literal tool_name pulse.py wrote (row.tool) -- "Bash"/"PowerShell"/
   * "Edit"/"Write"/"NotebookEdit"/"MultiEdit"/"Agent"/"Task"/"Workflow"/
   * "SendMessage", or "" for a row this classifier doesn't specialize. */
  tool: string;
  /** pulse.py#_detail's own already-prefixed string (row.detail). */
  detail: string;
  /** pulse.py#_target's own string (row.to) -- the subagent_type/
   * description for Agent/Task, the workflow name for Workflow. */
  to: string;
}

const RAN_PREFIX = "Ran: ";
const EDITING_PREFIX = "Editing";

function basenameOf(p: string): string {
  const norm = p.replace(/\\/g, "/").replace(/\/+$/, "");
  const parts = norm.split("/");
  return parts[parts.length - 1] || p;
}

/** Strips one or more leading "cd <path> && " segments before classifying.
 * pulse.py's own 100-char cap on the FULL command means a long enough `cd`
 * path can eat the ENTIRE budget before "&&" ever appears -- when that
 * happens there is nothing left to strip and no verb to see, so this
 * returns the (still cd-prefixed) string unchanged and the caller below
 * honestly falls through to "running a command" rather than guessing. */
export function stripLeadingCd(cmd: string): string {
  let s = cmd;
  for (;;) {
    const m = /^cd\s+\S+\s*&&\s*/.exec(s);
    if (!m) break;
    s = s.slice(m[0].length);
  }
  return s.trim();
}

/** Last non-flag token of a command, basenamed -- good enough for the
 * common "<verb> [flags] <file-or-url>" shape these commands almost always
 * have. Returns null (never a guess) when no such token exists. */
function lastArgBasename(cmd: string): string | null {
  const tokens = cmd.split(/\s+/).filter(Boolean);
  for (let i = tokens.length - 1; i >= 1; i--) {
    if (!tokens[i].startsWith("-")) return basenameOf(tokens[i]);
  }
  return null;
}

// Split from READ_VERBS (BUG-2 fix, 2026-09-14): grep/rg get their own fallback phrase
// ("searching code") distinct from cat/sed/head's ("reading a file") -- per the
// coordinator's own bug report wording.
const SEARCH_VERBS = new Set(["grep", "rg"]);
const READ_VERBS = new Set(["cat", "sed", "head", "tail", "less", "more", "read"]);
const TEST_RE = /^(pytest\b|node\s+--test\b|npm\s+(run\s+)?test\b)/;
// A bare PowerShell variable assignment ("$ts = ..."), e.g. the shape seen in this
// repo's own .claude/settings.local.json launch commands. Has no recognizable verb at
// all (the "verb" token is the variable name itself), so it must never fall through to
// classifyCommand's other verb checks and must never be mistaken for a file target.
const PS_ASSIGNMENT_RE = /^\$\w+\s*=/;
const NPM_BUILD_RE = /^npm\s+run\s+build\b/;
const GIT_COMMIT_RE = /^git\s+commit\b/;
const GIT_PUSH_RE = /^git\s+push\b/;
const CURL_RE = /^curl\b/;
// A token that genuinely looks like a URL/host -- scheme-prefixed, or
// host.tld-shaped. Coordinator review (bench-live-agents-0038.png, real
// on-screen curl capture) found pulse.py's own 100-char cap can cut a curl
// command BEFORE the URL argument, leaving only a truncated quoted flag
// value (e.g. `-w "HTT`) as the "last non-flag token" -- picking THAT as
// the target produced garbled bubble text. This shape check rejects a
// non-URL leftover rather than showing it verbatim.
const URL_LIKE_RE = /^(https?:\/\/\S+|[a-z0-9.-]+\.[a-z]{2,}(:\d+)?(\/\S*)?)$/i;

// A token counts as a real file/path TARGET only when it structurally looks like one --
// never picked out of a quoted string or a regex pattern (BUG-2 fix, 2026-09-14: a
// truncated `grep -n "^import\|bubbleY = \|bubbleActionTrunc &&\|<Htm` produced the
// bubble text "working · reading |<Htm" because the old code took ANY last non-flag
// token, including a fragment of the quoted regex itself). Any of these characters
// means the token came from inside a quote or is a regex/shell metachar fragment, not a
// standalone path: quotes, the regex/shell operators `| ^ $ < > * ( ) { } [ ]`, and a
// backslash (a regex escape in this position far more often than a literal Windows path
// segment once a leading `cd ... &&` has already been stripped).
const INVALID_TARGET_CHARS_RE = /["'|^$<>*(){}[\]\\]/;

function looksLikeFileTarget(token: string | null): token is string {
  if (!token) return false;
  if (INVALID_TARGET_CHARS_RE.test(token)) return false;
  if (token.includes("/")) return true; // a real path segment
  return /^[A-Za-z0-9_.-]+\.[A-Za-z0-9]+$/.test(token); // a bare "name.ext"-shaped filename
}

/** Classifies an already cd-stripped Bash/PowerShell command string into a
 * short human action phrase. Every branch checks the command's own real
 * verb/target -- the default ("running a command") is the honest answer
 * whenever this classifier can't name anything more specific from what
 * pulse.py actually recorded (e.g. the verb itself got truncated away by
 * pulse.py's own 100-char cap, or the command is a PowerShell `$var = ...`
 * assignment with no recognizable leading verb at all). */
function classifyCommand(rawCmd: string): string {
  const cmd = stripLeadingCd(rawCmd);
  if (!cmd) return "running a command";
  // A bare `$var = ...` assignment has no recognizable verb and runs no
  // named script file, so it must NOT say "running a script" (fixed
  // 2026-09-15: the prior return value here was wrong per the phrase
  // convention -- "running a script" is reserved for a real script-file
  // invocation like python/node/pwsh -File X).
  if (PS_ASSIGNMENT_RE.test(cmd)) return "running a command";
  const verb = basenameOf((cmd.split(/\s+/)[0] || "").toLowerCase());
  if (SEARCH_VERBS.has(verb)) {
    const target = lastArgBasename(cmd);
    return looksLikeFileTarget(target) ? `searching ${target}` : "searching code";
  }
  if (READ_VERBS.has(verb)) {
    const target = lastArgBasename(cmd);
    return looksLikeFileTarget(target) ? `reading ${target}` : "reading a file";
  }
  if (TEST_RE.test(cmd)) return "running tests";
  if (NPM_BUILD_RE.test(cmd)) return "building the dashboard";
  if (GIT_COMMIT_RE.test(cmd)) return "committing";
  if (GIT_PUSH_RE.test(cmd)) return "pushing";
  if (CURL_RE.test(cmd)) {
    const urlTok = cmd.split(/\s+/).filter(Boolean).find((t) => URL_LIKE_RE.test(t));
    const cleaned = urlTok ? urlTok.replace(/^https?:\/\//, "").split("?")[0] : null;
    return cleaned ? `checking ${cleaned}` : "checking a URL";
  }
  return "running a command";
}

/** The bubble's own action phrase for a live Claude Code agent/session --
 * see this section's own header for the defect this fixes. Structural
 * (keyed off `row.tool`, the literal tool_name), never keyword-sniffing
 * pre-flattened text. */
export function liveAgentBubbleAction(row: LiveAgentBubbleRow): string {
  const detail = row.detail || "";
  switch (row.tool) {
    case "Bash":
    case "PowerShell": {
      const cmd = detail.startsWith(RAN_PREFIX) ? detail.slice(RAN_PREFIX.length) : detail;
      return cmd ? classifyCommand(cmd) : "running a command";
    }
    case "Edit":
    case "Write":
    case "NotebookEdit":
    case "MultiEdit": {
      const rest = detail.startsWith(EDITING_PREFIX) ? detail.slice(EDITING_PREFIX.length).trim() : "";
      return rest ? `editing ${basenameOf(rest)}` : "editing a file";
    }
    case "Agent":
    case "Task":
      return row.to ? `spawning ${row.to}` : "spawning an agent";
    case "Workflow":
      return row.to ? `running ${row.to}` : "running a workflow";
    default:
      // SendMessage and anything else already carries human-readable free
      // text straight from pulse.py's own _detail() -- never reclassified,
      // just passed through (the caller applies its own defensive cap).
      return detail || row.to || row.tool || "";
  }
}

// BUBBLE-FIX (2026-09-15): classify BEFORE truncating -- the old version of
// this function flattened+cut the RAW row text (e.g. "Ran: cd
// C:/Users/jackw/Desktop/42" with the actual verb/target past the 100-char
// cap pulse.py itself already applied), which is exactly what produced the
// unreadable bubble text this pass fixes. `liveAgentBubbleAction` runs on
// the row's real tool/detail/to fields (see bubbleText.ts's own header) and
// returns a short human phrase; DETAIL_MAX_CHARS still applies here purely
// as a defensive cap, never as this function's main truncation mechanism.
function shortDetail(row: PulseRow): string {
  const raw = liveAgentBubbleAction(row) || rawDetailFor(row);
  const flat = raw.replace(/\s+/g, " ").trim();
  if (!flat) return "…";
  return flat.length > DETAIL_MAX_CHARS ? `${flat.slice(0, DETAIL_MAX_CHARS - 1)}…` : flat;
}

/** The full, un-classified row text -- same fallback chain `shortDetail`
 * used before this pass, kept verbatim (flattened to one line, not cut) as
 * the `rawDetail` diagnostic field so a real row's exact original text is
 * always recoverable even once `lastDetail` is a classified phrase. */
function rawDetailFor(row: PulseRow): string {
  const raw = row.detail || row.to || row.tool || row.event || "";
  return raw.replace(/\s+/g, " ").trim();
}

// ─── Tooltip task text (HQ AGENT-IDENTITY pass, 2026-09-15) ────────────────
//
// The hover tooltip needs the FULL current task (unlike the bubble's own
// classified-and-60-char-capped shortDetail), but rawDetail is a straight,
// un-sanitized flatten of pulse.py's own row text -- the SAME shape that
// motivated BUBBLE-FIX above ("Ran: cd C:\...\42 && grep ..."). This reuses
// this file's OWN existing leak knowledge (RAN_PREFIX, stripLeadingCd)
// rather than inventing a second set of rules, and is verified by
// dashboard/tests/hq-agents.test.ts to never match
// setup/scripts/hq_probe_lib.py's own RAW_SHELL_LEAK_RE
// (`Ran:|\\|/c/Users|&&`) -- the probe only scans the rendered `bubble`
// field today (that file's own comment: "rawDetail is deliberately RAW ...
// must never feed the leak scan"), but the tooltip renders taskDetail
// on-screen too, so it must clear the exact same bar.
const TOOLTIP_MAX_CHARS = 200;
// This box's own absolute workspace path (WORKSPACE_ROOT above), in both
// its native Windows form and the git-bash "/c/Users/..." form a Bash tool
// row's own command text can carry -- stripped so a tooltip never leaks the
// operator's local machine path, matching RAW_SHELL_LEAK_RE's own
// "/c/Users" check.
const WORKSPACE_PATH_RE = /\/?[Cc]:?\/Users\/[^/]+\/Desktop\/42\/?/g;

/** Sanitizes a live agent's full raw row text (`rawDetail`) into tooltip-
 * safe display text: strips the "Ran: " prefix and any leading `cd ... &&`
 * chain (stripLeadingCd, the same helper classifyCommand above uses),
 * normalizes backslashes to forward slashes, strips this box's own
 * absolute workspace path, and replaces any remaining `&&` chain operator
 * with a plain word -- never truncates the VERB/TARGET the way the 60-char
 * shortDetail cap can, only caps at TOOLTIP_MAX_CHARS as a defensive
 * ceiling (this task's own "~200 chars" spec). Never throws on empty/
 * malformed input -- degrades to "" (caller falls back to the classified
 * bubble text) rather than showing an ellipsis-only tooltip. */
export function sanitizeTaskText(raw: string): string {
  let text = (raw || "").replace(/\s+/g, " ").trim();
  if (!text) return "";
  if (text.startsWith(RAN_PREFIX)) text = text.slice(RAN_PREFIX.length);
  text = text.replace(/\\/g, "/");
  text = stripLeadingCd(text);
  text = text.replace(WORKSPACE_PATH_RE, "");
  text = text.replace(/\s*&&\s*/g, " then ").trim();
  if (!text) return "";
  return text.length > TOOLTIP_MAX_CHARS ? `${text.slice(0, TOOLTIP_MAX_CHARS - 1)}…` : text;
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
  lastRawDetail: string;
  zone: LiveAgentZone;
  /** pseudo-ms of the most recent tool-start row that has NOT yet been closed by a
   * matching "done" row for the same tool, or null when the agent's last tool call
   * already completed (or it has never started one). See ACTIVE_TOOL_GRACE_MS above. */
  openToolTs: number | null;
  /** The tool name (row.tool) that start row belongs to -- a "done" row only closes
   * the open window when its own tool matches this, same key pulse.py's
   * record_tool_done docstring documents. */
  openToolName: string | null;
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

  // Open-tool-call tracking (HQ BUG-1 fix, see ACTIVE_TOOL_GRACE_MS above) needs start
  // and "done" rows visited in chronological order per agent, so this pass sorts the
  // whole tail by pseudo-ms first (stable: rows with an identical timestamp keep their
  // original file-append order). first/last-row tracking below still uses explicit
  // pseudo-ms comparisons rather than relying on this order, matching the existing
  // "out-of-order tail slice" guarantee this function already documented.
  const ordered = rows
    .map((row, index) => ({ row, index, tsPseudo: parseLocalTsPseudoMs(row.ts) }))
    .filter((r): r is { row: PulseRow; index: number; tsPseudo: number } => r.tsPseudo !== null)
    .sort((a, b) => a.tsPseudo - b.tsPseudo || a.index - b.index);

  for (const { row, tsPseudo } of ordered) {
    const key = row.agent_id ? row.agent_id : row.session_id ? `session:${row.session_id}` : null;
    if (!key) continue; // malformed ts already filtered out above -- never guess "now" for a row we can't date

    const zone = classifyZone(`${row.to} ${row.detail}`);
    let existing = groups.get(key);
    if (!existing) {
      existing = {
        id: key,
        label: row.agent_id ? (row.agent_type || "agent") : "session",
        firstTs: row.ts,
        firstTsPseudoMs: tsPseudo,
        lastTs: row.ts,
        lastTsPseudoMs: tsPseudo,
        lastDetail: shortDetail(row),
        lastRawDetail: rawDetailFor(row),
        zone,
        openToolTs: null,
        openToolName: null,
      };
      groups.set(key, existing);
    } else {
      // Rows are now visited in pseudo-ms order, but first/last are still tracked by
      // explicit comparison (not "the loop's current position") -- an out-of-order tail
      // slice with two equal timestamps still produces a correct result either way.
      if (tsPseudo < existing.firstTsPseudoMs) {
        existing.firstTs = row.ts;
        existing.firstTsPseudoMs = tsPseudo;
      }
      if (tsPseudo >= existing.lastTsPseudoMs) {
        existing.lastTs = row.ts;
        existing.lastTsPseudoMs = tsPseudo;
        existing.lastDetail = shortDetail(row);
        existing.lastRawDetail = rawDetailFor(row);
        // A real zone signal only ever REPLACES the stale one on a later row
        // -- a row with no path in its own detail/to (e.g. a bare "Ran: ls")
        // must never blank an agent back to "hub" just because it's the most
        // recent row seen.
        if (zone !== "hub") existing.zone = zone;
        if (row.agent_id && row.agent_type) existing.label = row.agent_type;
      }
    }

    // Close the open tool-call window when a "done" row for the SAME tool arrives;
    // open (or re-open, for the next call) one on a fresh tool-start row. A "done" for
    // a DIFFERENT tool than the one currently open is ignored -- it cannot belong to
    // this open call, and pulse.jsonl's own PreToolUse ordering means a session never
    // starts a second tool before its first one's completion is recorded.
    if (row.event === TOOL_COMPLETION_EVENT) {
      if (existing.openToolName === row.tool) {
        existing.openToolTs = null;
        existing.openToolName = null;
      }
    } else if (TOOL_START_EVENTS.has(row.event)) {
      existing.openToolTs = tsPseudo;
      existing.openToolName = row.tool;
    }
  }

  const nowPseudo = nowLocalPseudoMs(nowMs);
  const alive = Array.from(groups.values()).filter((a) =>
    a.openToolTs !== null
      ? nowPseudo - a.openToolTs <= ACTIVE_TOOL_GRACE_MS
      : nowPseudo - a.lastTsPseudoMs <= IDLE_TIMEOUT_MS,
  );
  alive.sort((a, b) => b.lastTsPseudoMs - a.lastTsPseudoMs);

  return alive.slice(0, MAX_AGENTS).map((a) => {
    const age = nowPseudo - a.lastTsPseudoMs;
    const sinceFirst = nowPseudo - a.firstTsPseudoMs;
    let state: LiveAgentState = "active";
    if (a.openToolTs !== null) {
      // A tool call is still open (no "done" row yet): the agent reads as actively
      // working for the whole grace window (bounded above in the alive filter), never
      // "cooling"/about-to-leave just because its start row is a few minutes old.
      state = sinceFirst <= SPAWN_WINDOW_MS ? "spawning" : "active";
    } else if (sinceFirst <= SPAWN_WINDOW_MS) {
      state = "spawning";
    } else if (age >= IDLE_TIMEOUT_MS - COOLING_WINDOW_MS) {
      state = "cooling";
    }
    return {
      id: a.id,
      label: a.label,
      firstTs: a.firstTs,
      lastTs: a.lastTs,
      lastDetail: a.lastDetail,
      rawDetail: a.lastRawDetail,
      taskDetail: sanitizeTaskText(a.lastRawDetail),
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
// PERF FIX (perf/hq-api pass, 2026-09-15, coordinator-measured): this reader
// did a fresh 1.2MB byte-offset read on EVERY /api/hq poll (measured ~30-45ms,
// one of this route's top-5 costs) with no cache at all -- under multiple
// simultaneous viewers polling the same tail, most of those reads returned
// bytes identical to the previous poll (pulse.jsonl only grows between real
// tool-call events, which are far less frequent than a page's own poll
// interval). Cached per (mtime, size) so an unchanged file between polls
// costs one stat(), not a 1.2MB read -- same convention as lib/hq.ts's own
// readCryptoTwinTail cache (this session's other perf fix) and
// lib/station.ts's gpuCache/ollamaCache. A cache MISS (file grew/shrank,
// or this is the first read) still does the real read; nothing here ever
// serves fabricated data, only a byte-for-byte-identical previous read.
let pulseTailCache: { key: string; text: string } | null = null;

export async function readPulseTail(): Promise<string> {
  let fh: FileHandle | null = null;
  try {
    const stat = await fs.stat(PULSE_PATH);
    const cacheKey = `${stat.mtimeMs}:${stat.size}`;
    if (pulseTailCache && pulseTailCache.key === cacheKey) return pulseTailCache.text;
    const start = Math.max(0, stat.size - TAIL_READ_BYTES);
    const length = stat.size - start;
    if (length <= 0) {
      pulseTailCache = { key: cacheKey, text: "" };
      return "";
    }
    fh = await fs.open(PULSE_PATH, "r");
    const buf = Buffer.alloc(length);
    await fh.read(buf, 0, length, start);
    const text = buf.toString("utf-8");
    pulseTailCache = { key: cacheKey, text };
    return text;
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

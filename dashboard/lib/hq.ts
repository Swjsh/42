import { promises as fs } from "node:fs";
import type { FileHandle } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";
import { paths, WORKSPACE_ROOT } from "./workspace";
import { getQuote } from "./quote";
import { describeEngineAction } from "./engine-action-pure";

const execFileAsync = promisify(execFile);

// ─── Types (mirror setup/scripts/sector_rows.py's build_sector_rows() row
//     shape byte-for-byte -- see that module's docstring for the enums and
//     the fail-open contract this reader relies on) ──────────────────────────

export interface SectorRow {
  lane: string;
  state: "armed-paper" | "shadow" | "killed" | "dormant" | "dead" | "pending" | "unknown" | string;
  arm_or_acct_alias: string;
  last_evidence_et: string;
  evidence: string;
  window_pnl: number | "n/a";
  health: "green" | "amber" | "red" | "frozen" | "zombie" | string;
  doc: string;
}

// ─── setup/scripts/sector_rows.py --json (shell, fixed argv, 60s-cached) ─────

let sectorCache: { data: { rows: SectorRow[]; say: string }; at: number } | null = null;
const SECTOR_CACHE_MS = 60_000;

/** Shells `python setup/scripts/sector_rows.py --json` -- fixed argv (no user
 * input reaches the command line), read-only, 60s-cached so the page's poll
 * (kiosk 60s / interactive 15s, possibly several simultaneous viewers) never
 * spawns python more than once a minute. Fail-open per the module contract:
 * build_sector_rows() itself never raises and never returns a row count other
 * than one-per-lane, but the PYTHON PROCESS SPAWN can still fail (venv
 * missing, timeout) -- that failure degrades to an empty row list with a
 * `say` string, never throws, so /api/hq always has something to render. */
export async function readSectorRows(): Promise<{ rows: SectorRow[]; say: string }> {
  if (sectorCache && Date.now() - sectorCache.at < SECTOR_CACHE_MS) return sectorCache.data;
  try {
    const { stdout } = await execFileAsync(
      paths.pythonExe,
      [paths.sectorRowsScript, "--json"],
      { timeout: 15000, windowsHide: true },
    );
    const parsed = JSON.parse(stdout);
    const rows: SectorRow[] = Array.isArray(parsed) ? parsed : [];
    const data = { rows, say: `${rows.length} sector row(s)` };
    sectorCache = { data, at: Date.now() };
    return data;
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    const data = { rows: [], say: `NO DATA, sector_rows failed: ${message}` };
    sectorCache = { data, at: Date.now() };
    return data;
  }
}

// ─── Plain-file extras readers -- fail-open, never throw, never fabricate ────

/** automation/state/futures/health.json : verdict ("GREEN"/"YELLOW"/"RED"),
 * the same fused liveness verdict sector_rows.py's own futures row reads. */
export async function readFuturesVerdict(): Promise<string | null> {
  try {
    const text = await fs.readFile(paths.futuresHealth, "utf-8");
    const data = JSON.parse(text) as { verdict?: unknown };
    return typeof data.verdict === "string" ? data.verdict : null;
  } catch {
    return null;
  }
}

export interface CryptoTwinTail {
  last_action: string | null;
  last_ts: string | null;
}

// PERF FIX (perf/hq-api pass, 2026-09-15, coordinator-measured): this file's
// own doc comment above called a full-file read "an acceptable cost" on the
// premise the file "has no fixed-width line index to seek from" -- true, but
// the premise that made it cheap ("60s-poll") no longer holds (/api/hq is
// polled far more often than every 60s by every HQ viewer + the TV kiosk) and
// the file itself has grown to 147MB+ (verified this session: `ls -la
// automation/state/crypto-twin/decisions.jsonl`). A full fs.readFile of a
// 147MB file on EVERY poll was measured as the single largest cost in this
// route's Promise.all (~110-150ms of a ~110ms total warm request -- i.e. it
// alone accounted for the majority of the route's latency, and plausibly
// starved node's libuv threadpool (default size 4) enough to slow down every
// other fs-based reader running in the same Promise.all). Fixed the same way
// readCoreDecisionsLatest below already handles its own large append-only
// ledger: a byte-offset tail read (last CRYPTO_TWIN_TAIL_BYTES only, never
// the whole file) via a raw FileHandle, plus a cache keyed on the file's own
// (mtimeMs, size) so a request that lands between writes (the twin ticks
// ~1/min) skips the disk read entirely instead of re-reading the same tail
// bytes. One row of this file is small (a single JSON object), so 8 KiB is
// comfortably enough to always contain at least the last complete line.
const CRYPTO_TWIN_TAIL_BYTES = 8 * 1024;
let cryptoTwinCache: { key: string; data: CryptoTwinTail } | null = null;

/** automation/state/crypto-twin/decisions.jsonl tail : action/ts_et of the
 * twin's most recent tick (~1/min, 24/7 -- see sector_rows.py's crypto-twin
 * row for the same file read the same way). Reads only the last
 * CRYPTO_TWIN_TAIL_BYTES bytes (never the whole file -- see this function's
 * own PERF FIX comment above), cached per (mtime, size) so an unchanged file
 * between polls costs one stat(), not a read. Fail-open: a missing/unreadable
 * file or a malformed tail line degrades to nulls, never a throw. */
export async function readCryptoTwinTail(): Promise<CryptoTwinTail> {
  let handle: FileHandle | undefined;
  try {
    handle = await fs.open(paths.cryptoTwinDecisions, "r");
    const stat = await handle.stat();
    const cacheKey = `${stat.mtimeMs}:${stat.size}`;
    if (cryptoTwinCache && cryptoTwinCache.key === cacheKey) return cryptoTwinCache.data;
    const start = Math.max(0, stat.size - CRYPTO_TWIN_TAIL_BYTES);
    const length = stat.size - start;
    if (length <= 0) return { last_action: null, last_ts: null };
    const buffer = Buffer.alloc(length);
    await handle.read(buffer, 0, length, start);
    const text = buffer.toString("utf-8");
    const lines = text.trim().split("\n").filter(Boolean);
    const lastLine = lines[lines.length - 1];
    if (!lastLine) return { last_action: null, last_ts: null };
    const row = JSON.parse(lastLine) as { action?: unknown; ts_et?: unknown };
    const data: CryptoTwinTail = {
      last_action: typeof row.action === "string" ? row.action : null,
      last_ts: typeof row.ts_et === "string" ? row.ts_et : null,
    };
    cryptoTwinCache = { key: cacheKey, data };
    return data;
  } catch {
    return { last_action: null, last_ts: null };
  } finally {
    await handle?.close();
  }
}

export interface KitchenSummary {
  daemon_alive: boolean | null;
  idle: boolean | null;
  current_task_id: string | null;
  failed_permanent: number | null;
}

/** automation/state/kitchen-status.json -- daemon liveness + queue shape for
 * the Kitchen R&D bench module. Same file BrainVitals-adjacent panels could
 * read; this is a new, narrower reader (only the 4 fields the HQ bench needs)
 * rather than a duplicate of a general-purpose kitchen-status reader. */
export async function readKitchenSummary(): Promise<KitchenSummary> {
  try {
    const text = await fs.readFile(paths.kitchenStatus, "utf-8");
    const data = JSON.parse(text) as {
      daemon_alive?: unknown;
      idle?: unknown;
      current_task_id?: unknown;
      queue_summary?: { by_status?: { failed_permanent?: unknown } };
    };
    const failedPermanent = data.queue_summary?.by_status?.failed_permanent;
    return {
      daemon_alive: typeof data.daemon_alive === "boolean" ? data.daemon_alive : null,
      idle: typeof data.idle === "boolean" ? data.idle : null,
      current_task_id: typeof data.current_task_id === "string" ? data.current_task_id : null,
      failed_permanent: typeof failedPermanent === "number" ? failedPermanent : null,
    };
  } catch {
    return { daemon_alive: null, idle: null, current_task_id: null, failed_permanent: null };
  }
}

// ─── tv-perf.jsonl (HQ v2, 2026-09-13): unified TV render-perf history, one
//     line per report from EITHER kiosk face's own self-probe. Capped at 200
//     lines so a 24/7 TV never grows this unbounded. ──────────────────────────

export interface TvPerfRow {
  ts_et: string;
  page: string;
  fps: number;
  calls: number;
  tris: number;
  w: number;
  h: number;
  dpr: number;
  rawDpr?: number;
  ua: string;
}

const TV_PERF_MAX_LINES = 200;

/** Pure function, no fs access: given the file's CURRENT text and one new
 * JSON line, returns the new file text capped at `maxLines`. Kept pure and
 * exported specifically so it's unit-testable -- see the tv-probe route's
 * own comment on why no test file accompanies it today (no TS/JS test
 * runner in this project; adding one is out of scope -- "no new npm deps"). */
export function capJsonlText(existingText: string, newLineJson: string, maxLines: number): string {
  const lines = existingText.split("\n").map((l) => l.trim()).filter(Boolean);
  lines.push(newLineJson);
  return lines.slice(-maxLines).join("\n") + "\n";
}

/** Appends one row to tv-perf.jsonl, capped, via the same tmp+rename atomic
 * write every other station writer in this codebase already uses. */
export async function appendTvPerfRow(row: TvPerfRow): Promise<void> {
  let existing = "";
  try {
    existing = await fs.readFile(paths.tvPerf, "utf-8");
  } catch {
    existing = "";
  }
  const nextText = capJsonlText(existing, JSON.stringify(row), TV_PERF_MAX_LINES);
  await fs.mkdir(path.dirname(paths.tvPerf), { recursive: true });
  const tmp = `${paths.tvPerf}.tmp`;
  await fs.writeFile(tmp, nextText, "utf-8");
  await fs.rename(tmp, paths.tvPerf);
}

function isTvUa(ua: string | undefined): boolean {
  return !!ua && (ua.includes("SMART-TV") || ua.includes("Tizen"));
}

/** The latest page==="hq" rows, split by UA (2026-09-13 bug fix): a PC
 * browser visit to the LAN URL (fps ~460+, Chrome/Windows) was overwriting
 * the TV's own number in the HUD, since the original version just took the
 * newest hq-page line regardless of who sent it. `perf` is now the latest
 * row whose `ua` contains "SMART-TV" or "Tizen" -- falling back to the
 * latest row of ANY origin only if no TV row exists yet at all, so the HUD
 * still shows something rather than nothing on a brand new deploy before
 * the TV has reported once. `perfOther` is the latest non-TV row (or null),
 * kept separately rather than dropped so a caller can still show "someone
 * viewed this from a desktop" without it displacing the TV's number.
 * Fail-open: a missing file or one malformed line never throws. */
export async function readLatestHqPerf(): Promise<{ perf: TvPerfRow | null; perfOther: TvPerfRow | null }> {
  try {
    const text = await fs.readFile(paths.tvPerf, "utf-8");
    const lines = text.trim().split("\n").filter(Boolean);
    let latestAny: TvPerfRow | null = null;
    let latestTv: TvPerfRow | null = null;
    let latestOther: TvPerfRow | null = null;
    for (let i = lines.length - 1; i >= 0; i--) {
      let row: TvPerfRow;
      try {
        row = JSON.parse(lines[i]) as TvPerfRow;
      } catch {
        continue; // one malformed line never blocks scanning the rest of the tail
      }
      if (row.page !== "hq") continue;
      if (!latestAny) latestAny = row;
      if (isTvUa(row.ua)) {
        if (!latestTv) latestTv = row;
      } else if (!latestOther) {
        latestOther = row;
      }
      if (latestTv && latestOther) break;
    }
    return { perf: latestTv ?? latestAny, perfOther: latestOther };
  } catch {
    return { perf: null, perfOther: null };
  }
}

// ─── "NEEDS J" card (HQ v3 Company Mode, 2026-09-13, mechanics brief §10
//     item 5): a read-only merge of three EXISTING producers, zero new
//     writers. Fail-open per source -- one missing/garbled file contributes
//     nothing, never a 500 for the whole card. ─────────────────────────────

export interface BlockedItem {
  source: "discord" | "conductor_proposal" | "queue_escalation" | "goal_blocked" | "claude_auth_canary";
  ts: string | null;
  age: string;
  text: string;
}

// Recency caps (2026-09-13 hotfix): the ORIGINAL v3 card shipped noisy --
// its discord source took every `<@J>` row (the PROSPECTOR/SENTINEL digest
// spam J muted Discord over on purpose), and the other two sources had no
// staleness check at all (6 "pending" conductor proposals dated June/July
// that nobody will ever decide; goal `[B-J]` lines surviving from a CLOSED
// goal). "Needs J" must mean a decision only J can make, right now.
const PROPOSAL_MAX_AGE_DAYS = 14;
const ESCALATION_MAX_AGE_DAYS = 14;
const DISCORD_MAX_AGE_DAYS = 7;

function daysAgo(iso: string | null): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  return Number.isNaN(t) ? null : (Date.now() - t) / 86_400_000;
}

/** "2d" / "5h" -- computed server-side (not left to the client to re-derive
 * from `ts`) so `age` is always present on the wire, matching what a
 * `curl /api/station` verification actually reads. */
function formatAge(iso: string | null): string {
  const d = daysAgo(iso);
  if (d === null) return "?";
  if (d < 1) return `${Math.max(0, Math.round(d * 24))}h`;
  return `${Math.round(d)}d`;
}

/** discord-outbox.jsonl rows only count as a J-decision using the EXACT
 * same rule the bridge itself uses to decide what reaches Discord at all --
 * `classify_outbox_row()` in setup/scripts/discord-bridge.py:
 * `j_decision = bool(row.get("j_decision"))`. Alarm/brief/digest rows
 * (PROSPECTOR, TWIN SENTINEL, etc.) never set this field, so they are
 * excluded by construction, not by a second hand-rolled content filter --
 * reusing the bridge's own rule instead of re-inventing a "looks like it
 * mentions J" heuristic is the whole point of this hotfix. Reads the last
 * 300 rows (this producer has no delivered/resolved marker in its schema,
 * so "recent" is the only available notion of "still relevant") and then
 * additionally requires age <= DISCORD_MAX_AGE_DAYS with a PARSEABLE
 * timestamp -- a qualifying row with no usable ts is excluded rather than
 * assumed fresh. */
async function readDiscordBlocked(): Promise<BlockedItem[]> {
  try {
    const text = await fs.readFile(paths.discordOutbox, "utf-8");
    const lines = text.trim().split("\n").filter(Boolean).slice(-300);
    const items: BlockedItem[] = [];
    for (const line of lines) {
      try {
        const row = JSON.parse(line) as {
          content?: string; message?: string; detail?: string; j_decision?: unknown;
          ts?: string; queued_at?: string; ts_utc?: string;
        };
        if (!row.j_decision) continue;
        const ts = row.ts ?? row.queued_at ?? row.ts_utc ?? null;
        const age = daysAgo(ts);
        if (age === null || age > DISCORD_MAX_AGE_DAYS) continue;
        const body = row.content ?? row.message ?? row.detail ?? "";
        items.push({ source: "discord", ts, age: formatAge(ts), text: body.slice(0, 140) });
      } catch {
        // one malformed line never blocks the rest
      }
    }
    return items.reverse(); // newest-first within this source
  } catch {
    return [];
  }
}

/** Pending proposals older than PROPOSAL_MAX_AGE_DAYS are excluded -- a
 * "pending" row from June/July that nobody has acted on in months is not a
 * decision anyone is about to make tonight, it's backlog. */
async function readConductorProposalsBlocked(): Promise<BlockedItem[]> {
  try {
    const text = await fs.readFile(paths.conductorProposals, "utf-8");
    const lines = text.trim().split("\n").filter(Boolean);
    const items: BlockedItem[] = [];
    for (const line of lines) {
      try {
        const row = JSON.parse(line) as { status?: string; created_at?: string; title?: string; apply?: string; proposal_id?: string };
        if (row.status !== "pending") continue;
        const age = daysAgo(row.created_at ?? null);
        if (age === null || age > PROPOSAL_MAX_AGE_DAYS) continue;
        const label = row.title || row.apply || row.proposal_id || "pending proposal";
        items.push({ source: "conductor_proposal", ts: row.created_at ?? null, age: formatAge(row.created_at ?? null), text: label.slice(0, 140) });
      } catch {
        // one malformed line never blocks the rest
      }
    }
    return items.reverse();
  } catch {
    return [];
  }
}

/** "Lines containing FABLE-ESCALATION" per the literal spec -- a simple
 * substring match, not a tag parser. A "filed YYYY-MM-DD" date embedded in
 * the line's own prose is extracted when present and must be
 * <= ESCALATION_MAX_AGE_DAYS old; an UNDATED line can't be aged at all, so
 * (per the 2026-09-13 hotfix) only the 2 most recent undated lines survive
 * (file order is this doc's only recency signal for those) rather than
 * every mention ever filed. */
async function readQueueEscalations(): Promise<BlockedItem[]> {
  try {
    const text = await fs.readFile(paths.overnightQueue, "utf-8");
    const lines = text.split("\n");
    const dated: BlockedItem[] = [];
    const undated: BlockedItem[] = [];
    for (const line of lines) {
      if (!line.includes("FABLE-ESCALATION")) continue;
      // A blockquote line (`>` after trim) is prose QUOTING or SUMMARIZING
      // something elsewhere, never the queue's own declarative item --
      // confirmed against the real file (2026-09-13 hotfix verification):
      // line 681 is `> follow-ups, ..., the live FABLE-ESCALATION,`, a
      // passing mention with no date and no actionable content of its own.
      if (line.trim().startsWith(">")) continue;
      const dateMatch = /filed (\d{4}-\d{2}-\d{2})/.exec(line);
      const ts = dateMatch ? dateMatch[1] : null;
      const item: BlockedItem = { source: "queue_escalation", ts, age: formatAge(ts), text: line.trim().slice(0, 140) };
      if (ts === null) {
        undated.push(item);
        continue;
      }
      const age = daysAgo(ts);
      if (age !== null && age <= ESCALATION_MAX_AGE_DAYS) dated.push(item);
    }
    return [...dated, ...undated.slice(-2)].reverse();
  } catch {
    return [];
  }
}

/** Reads LADDER.md's own `[~]` marker (the goal-autopilot's SINGLE current
 * pointer -- no active-goal.json exists on disk) and returns the `file:`
 * path of every active entry (in practice, at most one). A `[ ]` queued-but-
 * not-yet-opened or `[x]` closed goal is never scanned -- this is exactly
 * the mechanism that excluded GOAL-APP-REBUILD-2026-08-30's stale [B-J]
 * lines from the 2026-09-13 hotfix. */
async function readActiveGoalFiles(): Promise<string[]> {
  try {
    const text = await fs.readFile(paths.goalLadder, "utf-8");
    const files: string[] = [];
    for (const line of text.split("\n")) {
      if (!line.trim().startsWith("- [~]")) continue;
      const m = /file:\s*(\S+)/.exec(line);
      if (m) files.push(m[1]);
    }
    return files;
  } catch {
    return [];
  }
}

/** A goal file's OWN curated `## J-DECISIONS` section (not the QUEUE
 * section's `[B-J]`-annotated work items, which are a broader work list
 * where the tag is incidental) -- that section's entire stated purpose
 * ("blocked-on-J; everything else ships without asking") is exactly this
 * card's contract, so it is the single most authoritative source per goal
 * file. Only UNCHECKED `- [ ]` bullets count -- a `- [x]` there means J
 * already decided it. No per-item date exists in this free-form section, so
 * the goal's OWN nominal date (parsed from its `GOAL-<NAME>-YYYY-MM-DD`
 * filename) stands in for `ts` -- reasonable since "still active on the
 * ladder" is itself the recency signal for this source (see
 * readActiveGoalFiles), not an additional day-cutoff. */
async function readGoalBlocked(): Promise<BlockedItem[]> {
  const relFiles = await readActiveGoalFiles();
  const items: BlockedItem[] = [];
  for (const relPath of relFiles) {
    try {
      const text = await fs.readFile(path.join(WORKSPACE_ROOT, relPath), "utf-8");
      const lines = text.split("\n");
      const dateMatch = /(\d{4}-\d{2}-\d{2})/.exec(path.basename(relPath));
      const ts = dateMatch ? `${dateMatch[1]}T00:00:00Z` : null;
      let inSection = false;
      for (const raw of lines) {
        const line = raw.trim();
        if (/^##\s+J-DECISIONS/.test(line)) { inSection = true; continue; }
        if (inSection && /^##\s/.test(line)) break; // next section ends it
        if (!inSection) continue;
        const m = /^- \[ \]\s*(.+)$/.exec(line);
        if (m) items.push({ source: "goal_blocked", ts, age: formatAge(ts), text: m[1].slice(0, 140) });
      }
    } catch {
      // one bad/missing goal file never blocks the rest
    }
  }
  return items;
}

// ─── Company audit (GOAL-GAMMA-STATION-2026-09-13 item 22): setup/scripts/
//     company_audit.py's output -- per-persona works/has_goal/is_smart/
//     autonomous verdicts with quoted evidence, for the HQ roster's employee
//     badges. Read-only mirror of that script's JSON shape; this file never
//     runs the script itself (it is a scheduled/manual producer, same
//     pattern as sector_rows.py's own shell-out vs this reader split). ──────

export interface CompanyAuditCheck {
  verdict: "PASS" | "WARN" | "FAIL" | string;
  evidence: string;
}

export interface CompanyAuditQuiz {
  asked: boolean;
  id?: string;
  model?: string;
  verdict?: "PASS" | "FAIL" | string;
  answer?: string;
  wall_s?: number;
  note?: string;
}

export interface CompanyAuditPersona {
  name: string;
  role_file: string;
  objective: string;
  kpi: string;
  cadence: string;
  tasks: string[];
  deliverable: string;
  goal_ref: string;
  verdict: "PASS" | "WARN" | "FAIL" | string;
  checks: {
    works: CompanyAuditCheck;
    has_goal: CompanyAuditCheck;
    is_smart: CompanyAuditCheck;
    autonomous: CompanyAuditCheck;
  };
  quiz: CompanyAuditQuiz | null;
}

export interface CompanyAudit {
  ts_et: string;
  last_trading_day: string;
  llm_used: boolean;
  llm_model: string | null;
  llm_skip_reason: string | null;
  runtime_s: number;
  personas: CompanyAuditPersona[];
  summary: { pass: number; warn: number; fail: number; total: number };
}

/** automation/state/station/company-audit.json -- fail-open: a missing file (the
 * script hasn't run yet) or a garbled one (mid-write) reads as null, never a throw --
 * /api/hq's Promise.all must never reject over this one optional section. Path is
 * built from the already-imported WORKSPACE_ROOT rather than adding a `paths` entry,
 * since this reader is the only caller. */
export async function readCompanyAudit(): Promise<CompanyAudit | null> {
  try {
    const text = await fs.readFile(
      path.join(WORKSPACE_ROOT, "automation", "state", "station", "company-audit.json"),
      "utf-8",
    );
    const data = JSON.parse(text) as CompanyAudit;
    return data && Array.isArray(data.personas) ? data : null;
  } catch {
    return null;
  }
}

// ─── Claude CLI auth canary (5th "NEEDS J" source, 2026-09-15): setup/
//     scripts/claude_auth_canary.py runs daily at 18:00 ET (Gamma_ClaudeAuth
//     Canary) and writes automation/state/claude-auth-canary.json. Without
//     this, an expired CLI login was invisible until a scheduled AI job
//     (premarket read, conductor, EOD summary) silently degraded. Read-only,
//     mtime/size-cached the same way readCryptoTwinTail above caches its own
//     small state file. ─────────────────────────────────────────────────────

export interface ClaudeAuthCanary {
  verdict: "OK" | "EXPIRING" | "LOGGED_OUT" | "UNKNOWN" | string;
  ts_et: string | null;
  hours_left: number | null;
}

const CLAUDE_AUTH_CANARY_MAX_AGE_HOURS = 48;
let claudeAuthCanaryCache: { key: string; data: ClaudeAuthCanary | null } | null = null;

async function readClaudeAuthCanary(): Promise<ClaudeAuthCanary | null> {
  try {
    const stat = await fs.stat(paths.claudeAuthCanary);
    const cacheKey = `${stat.mtimeMs}:${stat.size}`;
    if (claudeAuthCanaryCache && claudeAuthCanaryCache.key === cacheKey) return claudeAuthCanaryCache.data;
    const text = await fs.readFile(paths.claudeAuthCanary, "utf-8");
    const row = JSON.parse(text) as { verdict?: unknown; ts_et?: unknown; hours_left?: unknown };
    const data: ClaudeAuthCanary = {
      verdict: typeof row.verdict === "string" ? row.verdict : "UNKNOWN",
      ts_et: typeof row.ts_et === "string" ? row.ts_et : null,
      hours_left: typeof row.hours_left === "number" ? row.hours_left : null,
    };
    claudeAuthCanaryCache = { key: cacheKey, data };
    return data;
  } catch {
    return null;
  }
}

/** "2026-09-15 08:52:29 ET" -> epoch ms. Not full ET-DST-aware parsing (see
 * CLAUDE.md's "TIME = et_clock, NEVER Bash TZ" rule) -- this value only
 * feeds a coarse 48h staleness gate below, never a market-hours decision, so
 * a few hours of ET/local skew from dropping the zone label is immaterial. */
function parseCanaryTsEt(tsEt: string | null): number | null {
  if (!tsEt) return null;
  const cleaned = tsEt.replace(/\s*ET\s*$/, "").replace(" ", "T");
  const t = Date.parse(cleaned);
  return Number.isNaN(t) ? null : t;
}

/** Pure core: verdict OK/UNKNOWN or a canary reading older than
 * CLAUDE_AUTH_CANARY_MAX_AGE_HOURS (canary hasn't run in >48h -- the
 * scheduled task itself died) both contribute nothing, never a fabricated
 * item. LOGGED_OUT and EXPIRING are the only verdicts that produce a card
 * row. Exported (and `nowMs` parameterized) so this decision is testable
 * against fixture JSON with no filesystem involved -- readClaudeAuthCanary
 * above is the only fs-touching half of this producer. */
export function claudeAuthCanaryToBlockedItem(
  canary: ClaudeAuthCanary | null,
  nowMs: number = Date.now(),
): BlockedItem | null {
  if (!canary) return null;
  if (canary.verdict !== "LOGGED_OUT" && canary.verdict !== "EXPIRING") return null;
  const tsMs = parseCanaryTsEt(canary.ts_et);
  if (tsMs !== null && (nowMs - tsMs) / 3_600_000 > CLAUDE_AUTH_CANARY_MAX_AGE_HOURS) return null;
  const isoTs = tsMs !== null ? new Date(tsMs).toISOString() : null;
  const text = canary.verdict === "LOGGED_OUT"
    ? "[Rig] Claude CLI logged out — scheduled AI jobs (premarket read, conductor, EOD summary) are degraded. Fix: run `claude` then /login (30 s)."
    : `[Rig] Claude CLI login expires in ${Math.max(0, Math.round(canary.hours_left ?? 0))}h — run \`claude\` then /login`;
  return { source: "claude_auth_canary", ts: isoTs, age: formatAge(isoTs), text };
}

async function readClaudeAuthCanaryBlocked(): Promise<BlockedItem[]> {
  const canary = await readClaudeAuthCanary();
  const item = claudeAuthCanaryToBlockedItem(canary);
  return item ? [item] : [];
}

/** Merges all five sources, dedupes by exact text (keeping the first/
 * newest occurrence), caps at 8. The Claude auth canary source is always
 * placed FIRST (ahead of the ts-sorted rest) -- an expired CLI login is the
 * most actionable item this card can show, not just the most recent one.
 * Each per-source reader is independently fail-open, so one bad file
 * degrades to "contributes nothing", never a 500 for the whole card. */
export async function readBlocked(): Promise<BlockedItem[]> {
  const [claudeAuth, discord, proposals, escalations, goalItems] = await Promise.all([
    readClaudeAuthCanaryBlocked(),
    readDiscordBlocked(),
    readConductorProposalsBlocked(),
    readQueueEscalations(),
    readGoalBlocked(),
  ]);
  const rest = [...goalItems, ...discord, ...proposals, ...escalations];
  rest.sort((a, b) => {
    if (a.ts && b.ts) return b.ts.localeCompare(a.ts);
    if (a.ts) return -1;
    if (b.ts) return 1;
    return 0;
  });
  const seenText = new Set<string>();
  const deduped: BlockedItem[] = [];
  for (const item of [...claudeAuth, ...rest]) {
    if (seenText.has(item.text)) continue;
    seenText.add(item.text);
    deduped.push(item);
  }
  return deduped.slice(0, 8);
}

// ─── LIVE-1 item 5 (2026-09-14, coordinator-directed mid-task addition):
//     trading status strip -- "are we ready to trade today?" answered
//     without J having to ask. Every reader below is read-only; nothing
//     under automation/state/ is ever written from this path (same
//     contract as the rest of this file). Verdict/color decisions are made
//     CLIENT-SIDE (Hud.tsx), off the SAME explicit-ET clock every other
//     RTH-aware piece of this app already uses (Scene.tsx#isRth,
//     palette.ts#isRegularTradingHours) -- this module only ever extracts
//     and lightly summarizes the raw files, never computes "is it market
//     hours" itself, so there is exactly one clock source of truth. ─────────

export interface ReadinessCheck {
  name: string;
  status: string;
  detail: string;
  critical: boolean;
}

export interface ReadinessSnapshot {
  tsEt: string | null;
  verdict: string;
  checks: ReadinessCheck[];
}

async function readReadinessFile(filePath: string, tsField: string): Promise<ReadinessSnapshot | null> {
  try {
    const text = await fs.readFile(filePath, "utf-8");
    const data = JSON.parse(text) as Record<string, unknown>;
    const rawChecks = Array.isArray(data.checks) ? data.checks : [];
    const checks: ReadinessCheck[] = rawChecks
      .filter((c): c is Record<string, unknown> => !!c && typeof c === "object")
      .map((c) => ({
        name: typeof c.name === "string" ? c.name : "?",
        status: typeof c.status === "string" ? c.status : "UNKNOWN",
        detail: typeof c.detail === "string" ? c.detail : "",
        critical: c.critical === true,
      }));
    return {
      tsEt: typeof data[tsField] === "string" ? (data[tsField] as string) : null,
      verdict: typeof data.verdict === "string" ? data.verdict : "UNKNOWN",
      checks,
    };
  } catch {
    return null;
  }
}

/** automation/state/premarket-readiness.json -- verdict + checks[], the
 * MORE CURRENT of the two readiness files (fires later in the day, covers
 * fleet reachability + engine_health + levels/bias freshness; verified
 * against the live file this session -- real field names, not guessed). */
async function readPremarketReadiness(): Promise<ReadinessSnapshot | null> {
  return readReadinessFile(paths.premarketReadiness, "ts_et");
}

/** automation/state/preopen-readiness.json -- the EARLIER (08:00-08:30 ET)
 * scheduled-task-readiness check. Same shape, different `ts` field name
 * (verified against the live file this session: `checked_at_et`, not
 * `ts_et`). */
async function readPreopenReadiness(): Promise<ReadinessSnapshot | null> {
  return readReadinessFile(paths.preopenReadiness, "checked_at_et");
}

export interface TradingReadiness {
  verdict: string;
  /** "<check name>: <check detail>", truncated to one line -- the specific
   * YELLOW/RED check that's dragging the verdict down, per this task's own
   * spec ("the readiness reason is the YELLOW/RED check's detail"). Null
   * when verdict is GREEN/UNKNOWN (nothing to explain). */
  reasonDetail: string | null;
  tsEt: string | null;
}

const READINESS_VERDICT_RANK: Record<string, number> = { GREEN: 0, UNKNOWN: 0, YELLOW: 1, RED: 2 };

/** Combines premarket + preopen into ONE verdict (the WORSE of the two --
 * either genuinely blocking trading readiness) and surfaces the specific
 * offending check's own detail text, never a fabricated summary. Fail-open
 * per source (see readReadinessFile) -- if BOTH are missing, verdict reads
 * UNKNOWN rather than a fake GREEN. */
export async function readTradingReadiness(): Promise<TradingReadiness> {
  const [premarket, preopen] = await Promise.all([readPremarketReadiness(), readPreopenReadiness()]);
  const candidates = [premarket, preopen].filter((s): s is ReadinessSnapshot => !!s);
  if (candidates.length === 0) return { verdict: "UNKNOWN", reasonDetail: null, tsEt: null };
  let worst = candidates[0];
  for (const c of candidates) {
    if ((READINESS_VERDICT_RANK[c.verdict] ?? 0) > (READINESS_VERDICT_RANK[worst.verdict] ?? 0)) worst = c;
  }
  // Only ever explain a YELLOW/RED verdict -- picking an arbitrary GREEN
  // check's own detail as the "reason" when the verdict is already GREEN
  // would be a meaningless (if harmless) non-sequitur, not a real reason.
  const offending = worst.verdict === "YELLOW" || worst.verdict === "RED"
    ? worst.checks.find((c) => c.status === worst.verdict) ?? worst.checks.find((c) => c.status !== "GREEN") ?? null
    : null;
  return {
    verdict: worst.verdict,
    reasonDetail: offending ? `${offending.name}: ${offending.detail}`.slice(0, 140) : null,
    tsEt: worst.tsEt,
  };
}

export interface CoreDecisionRow {
  tsEt: string;
  account: "safe" | "bold";
  armed: boolean;
  /** BACK-COMPAT ALIAS of engineBarSpy below -- kept so existing consumers
   * (Scene.tsx, HubInterior.tsx, Hud.tsx) that already read `.spy` keep
   * working unchanged. This is the price of the LAST CLOSED bar the engine
   * decided on, NOT a live tick -- by design (no look-ahead), it lags the
   * real tape during RTH. Prefer trading.market.live.spy for "what is SPY
   * doing right now" and engineBarSpy/action/actionReason for "what is the
   * engine's own bar-close view and why did it (not) act". */
  spy: number | null;
  /** Same value as `spy` above, explicitly named so a UI consumer can label
   * it honestly ("engine bar SPY") instead of implying it's live. */
  engineBarSpy: number | null;
  vix: number | null;
  ribbon: string | null;
  verdict: string | null;
  side: string | null;
  setup: string | null;
  /** setup/scripts/heartbeat_core.py's per-tick ledger `action` field --
   * the engine's ACTUAL disposition this tick (e.g. SKIP_STALE_TRIGGER),
   * distinct from `verdict` (the raw gate/score verdict, e.g. HOLD) -- see
   * that module's run_account() post-verdict ladder, ~L1857-1965. */
  action: string | null;
  /** Human-readable one-line explanation of `action`, from
   * lib/engine-action-pure.ts#describeEngineAction -- computed here so
   * every consumer gets the same wording without re-implementing the map. */
  actionReason: string;
}

// automation/state/core-decisions.jsonl is a large, continuously-growing
// append-only ledger (121MB+ as of 2026-09-14, one ~tick per account,
// every ~60s during RTH) -- a plain fs.readFile of the WHOLE file (the
// convention every OTHER jsonl reader in this codebase uses, e.g.
// lib/personas.ts#readJsonlTail) would read 100+MB on every single
// /api/hq poll. This reads ONLY the last CORE_DECISIONS_TAIL_BYTES via a
// byte-seek file handle instead -- at ~2-3KB/row, comfortably enough rows
// to find the latest "safe" AND "bold" row even under a burst of writes
// from one account.
const CORE_DECISIONS_TAIL_BYTES = 512 * 1024; // 512 KiB

/** Last row per account ("safe"/"bold" -- the only two values this file
 * ever carries, verified against the live 42k+-line file this session) --
 * whichever ticks most recently is the "is the engine actually ticking"
 * signal the status strip needs. Fail-open: a missing/unreadable file or
 * one malformed line never throws, degrading to null per account. */
export async function readCoreDecisionsLatest(): Promise<{ safe: CoreDecisionRow | null; bold: CoreDecisionRow | null }> {
  let handle: FileHandle | undefined;
  try {
    handle = await fs.open(paths.coreDecisions, "r");
    const stat = await handle.stat();
    const start = Math.max(0, stat.size - CORE_DECISIONS_TAIL_BYTES);
    const length = stat.size - start;
    if (length <= 0) return { safe: null, bold: null };
    const buffer = Buffer.alloc(length);
    await handle.read(buffer, 0, length, start);
    const text = buffer.toString("utf-8");
    // The FIRST line of a seeked chunk is very likely a truncated partial
    // row (the seek almost certainly landed mid-line) -- drop it when we
    // actually seeked past the start of the file; every other line is a
    // complete newline-terminated jsonl row.
    const lines = text.split("\n").slice(start > 0 ? 1 : 0).filter((l) => l.trim().length > 0);
    let safe: CoreDecisionRow | null = null;
    let bold: CoreDecisionRow | null = null;
    for (const line of lines) {
      let row: Record<string, unknown>;
      try {
        row = JSON.parse(line);
      } catch {
        continue; // one malformed/truncated line never blocks the rest
      }
      const account = row.account === "safe" || row.account === "bold" ? row.account : null;
      if (!account) continue;
      const engineBarSpy = typeof row.spy === "number" ? row.spy : null;
      const action = typeof row.action === "string" ? row.action : null;
      const parsed: CoreDecisionRow = {
        tsEt: typeof row.ts_et === "string" ? row.ts_et : "",
        account,
        armed: row.armed === true,
        spy: engineBarSpy,
        engineBarSpy,
        vix: typeof row.vix === "number" ? row.vix : null,
        ribbon: typeof row.ribbon === "string" ? row.ribbon : null,
        verdict: typeof row.verdict === "string" ? row.verdict : null,
        side: typeof row.side === "string" ? row.side : null,
        setup: typeof row.setup === "string" ? row.setup : null,
        action,
        actionReason: describeEngineAction(action),
      };
      if (account === "safe") safe = parsed; else bold = parsed;
    }
    return { safe, bold };
  } catch {
    return { safe: null, bold: null };
  } finally {
    await handle?.close();
  }
}

export interface TodayBiasSummary {
  date: string | null;
  bias: string | null;
  biasNoteFirstSentence: string | null;
}

/** automation/state/today-bias.json -- `bias_note` is a long hand-written
 * paragraph; only its first real sentence belongs in a one-line strip
 * (same "first sentence, never the raw dump" reasoning palette.ts's own
 * firstBriefSentence already uses for Gamma's speech bubble). */
export async function readTodayBiasSummary(): Promise<TodayBiasSummary | null> {
  try {
    const text = await fs.readFile(paths.todayBias, "utf-8");
    const data = JSON.parse(text) as { date?: unknown; bias?: unknown; bias_note?: unknown };
    const note = typeof data.bias_note === "string" ? data.bias_note.trim() : null;
    const m = note ? /^(.*?[.!?])(\s|$)/.exec(note) : null;
    const firstSentence = m ? m[1] : note ? note.slice(0, 140) : null;
    return {
      date: typeof data.date === "string" ? data.date : null,
      bias: typeof data.bias === "string" ? data.bias : null,
      biasNoteFirstSentence: firstSentence,
    };
  } catch {
    return null;
  }
}

function todayEtDateStr(): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

// CREW-2 (roster) coordinator correction (2026-09-14): Pilot's roster card
// was reading automation/state/loop-state.json (a stale side file the live
// deterministic engine, heartbeat_core.py, doesn't write) for both its
// "is it working" freshness AND its "N decisions today" count, so it could
// disagree with the trading strip's own "engine ticking HH:MM" line, which
// reads core-decisions.jsonl via readCoreDecisionsLatest() above. Pilot's
// roster card must read the SAME file. readCoreDecisionsLatest()'s own
// bounded 512KiB tail (comfortably enough to find the newest row per
// account, per that function's own comment) is too small to reliably count
// EVERY row from today once several hours into a ~1-tick/min RTH day (up to
// ~385 ticks/account * ~2.5KB/row ~= ~1MB/account), so this reads a larger
// (4MiB) tail instead, filters to rows whose ts_et starts with today's ET
// date, and counts + separately names genuine ENTER/EXIT trade rows (same
// /^(ENTER|EXIT)/ test Scene.tsx's own commit 81147547 already established
// against this file's real verdict vocabulary) -- never a bare stale count.
const CORE_DECISIONS_TODAY_TAIL_BYTES = 4 * 1024 * 1024; // 4 MiB

export interface CoreDecisionsToday {
  safe: { count: number; trades: CoreDecisionRow[] };
  bold: { count: number; trades: CoreDecisionRow[] };
}

/** Every core-decisions.jsonl row from TODAY (ET calendar date), split by
 * account, plus which of those rows were genuine ENTER/EXIT trade actions.
 * Fail-open: a missing/unreadable file or one malformed line never throws
 * (degrades to a 0 count, never a fabricated number). */
export async function readCoreDecisionsToday(): Promise<CoreDecisionsToday> {
  const empty: CoreDecisionsToday = { safe: { count: 0, trades: [] }, bold: { count: 0, trades: [] } };
  let handle: FileHandle | undefined;
  try {
    handle = await fs.open(paths.coreDecisions, "r");
    const stat = await handle.stat();
    const start = Math.max(0, stat.size - CORE_DECISIONS_TODAY_TAIL_BYTES);
    const length = stat.size - start;
    if (length <= 0) return empty;
    const buffer = Buffer.alloc(length);
    await handle.read(buffer, 0, length, start);
    const text = buffer.toString("utf-8");
    // Same "drop the first line if we seeked mid-file" rule as
    // readCoreDecisionsLatest above -- a seeked chunk's first line is very
    // likely a truncated partial row.
    const lines = text.split("\n").slice(start > 0 ? 1 : 0).filter((l) => l.trim().length > 0);
    const today = todayEtDateStr();
    const result: CoreDecisionsToday = { safe: { count: 0, trades: [] }, bold: { count: 0, trades: [] } };
    for (const line of lines) {
      let row: Record<string, unknown>;
      try {
        row = JSON.parse(line);
      } catch {
        continue; // one malformed/truncated line never blocks the rest
      }
      const account = row.account === "safe" || row.account === "bold" ? row.account : null;
      if (!account) continue;
      const tsEt = typeof row.ts_et === "string" ? row.ts_et : "";
      if (!tsEt.startsWith(today)) continue; // only today's rows count toward "decisions today"
      const todayEngineBarSpy = typeof row.spy === "number" ? row.spy : null;
      const todayAction = typeof row.action === "string" ? row.action : null;
      const parsed: CoreDecisionRow = {
        tsEt,
        account,
        armed: row.armed === true,
        spy: todayEngineBarSpy,
        engineBarSpy: todayEngineBarSpy,
        vix: typeof row.vix === "number" ? row.vix : null,
        ribbon: typeof row.ribbon === "string" ? row.ribbon : null,
        verdict: typeof row.verdict === "string" ? row.verdict : null,
        side: typeof row.side === "string" ? row.side : null,
        setup: typeof row.setup === "string" ? row.setup : null,
        action: todayAction,
        actionReason: describeEngineAction(todayAction),
      };
      result[account].count += 1;
      if (parsed.verdict && /^(ENTER|EXIT)/.test(parsed.verdict)) result[account].trades.push(parsed);
    }
    return result;
  } catch {
    return empty;
  } finally {
    await handle?.close();
  }
}

/** automation/state/open-bell-pinged.json -- whether TODAY's (ET calendar
 * date, computed the same explicit-Intl way as everywhere else in this
 * codebase, never the server process's own local date) open bell has
 * already been pinged. */
async function readOpenBellPingedToday(): Promise<boolean> {
  try {
    const text = await fs.readFile(paths.openBellPinged, "utf-8");
    const data = JSON.parse(text) as { date?: unknown };
    return typeof data.date === "string" && data.date === todayEtDateStr();
  } catch {
    return false;
  }
}

/** Live (~1min-fresh, real broker/yfinance REST) SPY reading -- DISTINCT
 * from CoreDecisionRow.engineBarSpy, which is the price of the last CLOSED
 * bar the engine decided on (by design, lags live -- no look-ahead). Sourced
 * from lib/quote.ts#getQuote (automation/state/sight-beacon.json), the SAME
 * beacon setup/scripts/sight_beacon.py writes every ~1min during RTH. Null
 * when the beacon is missing/unparseable (fail-open, never fabricated). */
export interface LiveMarketQuote {
  spy: number | null;
  ts_et: string | null;
  age_s: number | null;
  source: "sight-beacon";
}

export interface TradingStatus {
  readiness: TradingReadiness;
  core: { safe: CoreDecisionRow | null; bold: CoreDecisionRow | null };
  bias: TodayBiasSummary | null;
  openBellPingedToday: boolean;
  market: { live: LiveMarketQuote | null };
}

/** Combines every item-5 source into the ONE `trading` field /api/hq
 * exposes. Each piece is independently fail-open (see its own reader) --
 * one missing file degrades that piece to null/UNKNOWN, never a 500 for
 * the whole payload. */
export async function readTradingStatus(): Promise<TradingStatus> {
  const [readiness, core, bias, openBellPingedToday, quote] = await Promise.all([
    readTradingReadiness(),
    readCoreDecisionsLatest(),
    readTodayBiasSummary(),
    readOpenBellPingedToday(),
    getQuote(),
  ]);
  // getQuote()'s own staleness ("unavailable"/"stale") is a DIFFERENT axis
  // than "do we have a number at all" -- market.live.spy is null only when
  // the beacon truly has no usable price; a stale-but-present price is still
  // surfaced (with its real age_s) so the UI can label it "stale" itself
  // rather than this reader silently hiding an old-but-real number.
  const live: LiveMarketQuote | null = quote.price === null
    ? null
    : { spy: quote.price, ts_et: quote.asOfEt, age_s: quote.ageSeconds, source: "sight-beacon" };
  return { readiness, core, bias, openBellPingedToday, market: { live } };
}

// CREW-2 (roster) -- automation/state/station/crew-events.jsonl : a NEW
// producer (CREW-RIG, a parallel builder this same pass) writing one row
// per persona action/handoff, capped 500 lines. Read-only mirror, additive
// field on /api/hq (`crewEvents`) -- feeds Hud.tsx's R3 event feed AND
// lib/personas.ts's Chef/Coach "last:" fallback (a persona's own crew-event
// row, when fresher than its file deliverable). Fail-open: the file may not
// exist yet (CREW-RIG hasn't landed it), which reads as [], never a throw.

export interface CrewEvent {
  ts_et: string;
  who: string;
  kind: string;
  line: string;
  ref?: string;
  to?: string;
}

const CREW_EVENTS_READ_LIMIT = 100;

/** Last `limit` rows of crew-events.jsonl, newest-last (same tail
 * convention as every other jsonl reader in this codebase, e.g.
 * lib/personas.ts#readJsonlTail) -- the caller reverses/slices as needed. */
// ─── Coordinator-directed additive item (2026-09-14, 17:2x ET): "add a
//     `sectors` field... {ts_et, summary_line, rows}... read fail-open from
//     automation/state/station/sectors.json... keys exactly as in the file"
//     -- MODELS' hub wall panel and LAYOUT's prop threading depend on it.
//     Named `sectorsSnapshot` here (not `sectors`) since /api/hq ALREADY
//     has a `sectors` field (this route's own readSectorRows() above,
//     `{rows, say}` -- a DIFFERENT producer, sector_rows.py's live shell,
//     already consumed elsewhere): reusing that name would silently
//     collide with and break the existing field rather than add a new one.
//     Real shape confirmed against the live file this session (python -m
//     json.tool automation/state/station/sectors.json) -- row keys are
//     lane/state/arm_or_acct_alias/last_evidence_et/evidence/window_pnl/
//     health/doc, NOT the abbreviated arm/note shorthand a first guess
//     might reach for. ──────────────────────────────────────────────────

export interface SectorsSnapshotRow {
  lane: string;
  state: string;
  arm_or_acct_alias: string;
  last_evidence_et: string;
  evidence: string;
  window_pnl: number | "n/a";
  health: string;
  doc: string;
}

export interface SectorsSnapshot {
  ts_et: string;
  summary_line: string;
  rows: SectorsSnapshotRow[];
}

/** automation/state/station/sectors.json -- CREW-RIG's per-Station-fire
 * snapshot (30-min cadence, 24/7). Fail-open: a missing file (producer
 * hasn't fired yet) or a garbled one degrades to null, never a throw --
 * same contract as every other reader in this file (see this route's own
 * U7 audit comment on GET() for why that matters). */
export async function readSectorsSnapshot(): Promise<SectorsSnapshot | null> {
  try {
    const text = await fs.readFile(
      path.join(WORKSPACE_ROOT, "automation", "state", "station", "sectors.json"),
      "utf-8",
    );
    const data = JSON.parse(text) as Record<string, unknown>;
    if (!Array.isArray(data.rows)) return null;
    const rows: SectorsSnapshotRow[] = data.rows
      .filter((r): r is Record<string, unknown> => !!r && typeof r === "object")
      .map((r) => ({
        lane: typeof r.lane === "string" ? r.lane : "",
        state: typeof r.state === "string" ? r.state : "unknown",
        arm_or_acct_alias: typeof r.arm_or_acct_alias === "string" ? r.arm_or_acct_alias : "",
        last_evidence_et: typeof r.last_evidence_et === "string" ? r.last_evidence_et : "",
        evidence: typeof r.evidence === "string" ? r.evidence : "",
        window_pnl: typeof r.window_pnl === "number" ? r.window_pnl : "n/a",
        health: typeof r.health === "string" ? r.health : "unknown",
        doc: typeof r.doc === "string" ? r.doc : "",
      }));
    return {
      ts_et: typeof data.ts_et === "string" ? data.ts_et : "",
      summary_line: typeof data.summary_line === "string" ? data.summary_line : "",
      rows,
    };
  } catch {
    return null;
  }
}

export async function readCrewEvents(limit = CREW_EVENTS_READ_LIMIT): Promise<CrewEvent[]> {
  try {
    const text = await fs.readFile(
      path.join(WORKSPACE_ROOT, "automation", "state", "station", "crew-events.jsonl"),
      "utf-8",
    );
    const lines = text.trim().split("\n").filter(Boolean).slice(-limit);
    const rows: CrewEvent[] = [];
    for (const line of lines) {
      try {
        const row = JSON.parse(line) as Record<string, unknown>;
        if (typeof row.ts_et === "string" && typeof row.who === "string" && typeof row.line === "string") {
          rows.push({
            ts_et: row.ts_et,
            who: row.who,
            kind: typeof row.kind === "string" ? row.kind : "event",
            line: row.line,
            ref: typeof row.ref === "string" ? row.ref : undefined,
            to: typeof row.to === "string" ? row.to : undefined,
          });
        }
      } catch {
        // one malformed line never blocks the rest
      }
    }
    return rows;
  } catch {
    return [];
  }
}

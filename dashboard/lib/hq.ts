import { promises as fs } from "node:fs";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";
import { paths, WORKSPACE_ROOT } from "./workspace";

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

/** automation/state/crypto-twin/decisions.jsonl tail : action/ts_et of the
 * twin's most recent tick (~1/min, 24/7 -- see sector_rows.py's crypto-twin
 * row for the same file read the same way). Reads the whole file since it has
 * no fixed-width line index to seek from; the file is a research ledger, not
 * a hot path, so one full read per 60s-poll is an acceptable cost here. */
export async function readCryptoTwinTail(): Promise<CryptoTwinTail> {
  try {
    const text = await fs.readFile(paths.cryptoTwinDecisions, "utf-8");
    const lines = text.trim().split("\n").filter(Boolean);
    const lastLine = lines[lines.length - 1];
    if (!lastLine) return { last_action: null, last_ts: null };
    const row = JSON.parse(lastLine) as { action?: unknown; ts_et?: unknown };
    return {
      last_action: typeof row.action === "string" ? row.action : null,
      last_ts: typeof row.ts_et === "string" ? row.ts_et : null,
    };
  } catch {
    return { last_action: null, last_ts: null };
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
  source: "discord" | "conductor_proposal" | "queue_escalation" | "goal_blocked";
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

/** Merges all four sources, dedupes by exact text (keeping the first/
 * newest occurrence), sorts newest-first (rows with a ts sort before rows
 * without one), caps at 8. Each per-source reader is independently
 * fail-open, so one bad file degrades to "contributes nothing", never a 500
 * for the whole card. */
export async function readBlocked(): Promise<BlockedItem[]> {
  const [discord, proposals, escalations, goalItems] = await Promise.all([
    readDiscordBlocked(),
    readConductorProposalsBlocked(),
    readQueueEscalations(),
    readGoalBlocked(),
  ]);
  const all = [...goalItems, ...discord, ...proposals, ...escalations];
  all.sort((a, b) => {
    if (a.ts && b.ts) return b.ts.localeCompare(a.ts);
    if (a.ts) return -1;
    if (b.ts) return 1;
    return 0;
  });
  const seenText = new Set<string>();
  const deduped: BlockedItem[] = [];
  for (const item of all) {
    if (seenText.has(item.text)) continue;
    seenText.add(item.text);
    deduped.push(item);
  }
  return deduped.slice(0, 8);
}

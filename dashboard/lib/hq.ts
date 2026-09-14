import { promises as fs } from "node:fs";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import path from "node:path";
import { paths } from "./workspace";

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
  source: "discord" | "conductor_proposal" | "queue_escalation";
  ts: string | null;
  text: string;
}

/** discord-outbox.jsonl has NO delivered/resolved marker anywhere in its
 * schema (checked directly: 7623 rows, several shapes -- {content,source,
 * queued_at}, {ts,channel,message,source}, {ts,source,reason,detail,...} --
 * none carry a status/delivered/resolved field). So "not marked delivered/
 * resolved" reduces to "recent" here: this reads only the last 300 rows
 * (not the whole 7623-row history) and treats every one of those that
 * mentions J as still-relevant, rather than inventing a resolution state
 * this producer doesn't track. Body text comes from whichever of
 * content/message/detail is present. */
async function readDiscordBlocked(): Promise<BlockedItem[]> {
  try {
    const text = await fs.readFile(paths.discordOutbox, "utf-8");
    const lines = text.trim().split("\n").filter(Boolean).slice(-300);
    const items: BlockedItem[] = [];
    for (const line of lines) {
      try {
        const row = JSON.parse(line) as {
          content?: string; message?: string; detail?: string;
          ts?: string; queued_at?: string; ts_utc?: string;
        };
        const body = row.content ?? row.message ?? row.detail ?? "";
        if (!body.includes("<@") && !body.includes("J:")) continue;
        items.push({ source: "discord", ts: row.ts ?? row.queued_at ?? row.ts_utc ?? null, text: body.slice(0, 140) });
      } catch {
        // one malformed line never blocks the rest
      }
    }
    return items.reverse(); // newest-first within this source
  } catch {
    return [];
  }
}

async function readConductorProposalsBlocked(): Promise<BlockedItem[]> {
  try {
    const text = await fs.readFile(paths.conductorProposals, "utf-8");
    const lines = text.trim().split("\n").filter(Boolean);
    const items: BlockedItem[] = [];
    for (const line of lines) {
      try {
        const row = JSON.parse(line) as { status?: string; created_at?: string; title?: string; apply?: string; proposal_id?: string };
        if (row.status !== "pending") continue;
        const label = row.title || row.apply || row.proposal_id || "pending proposal";
        items.push({ source: "conductor_proposal", ts: row.created_at ?? null, text: label.slice(0, 140) });
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
 * substring match, not a tag parser (queue.md mixes "- [ ] FABLE-ESCALATION-
 * ..." task lines, "## FABLE-ESCALATION: ..." headings, and prose that just
 * mentions the term; all three match, which can occasionally over-include a
 * line that only references an escalation rather than declaring one -- an
 * acceptable trade for a read-only visibility card). No reliable per-line
 * timestamp field exists in this free-form doc, so "newest first" uses
 * reverse FILE order (an append-oriented queue file) as the recency proxy;
 * a "filed YYYY-MM-DD" date embedded in the line's own prose is extracted
 * as `ts` when present. */
async function readQueueEscalations(): Promise<BlockedItem[]> {
  try {
    const text = await fs.readFile(paths.overnightQueue, "utf-8");
    const lines = text.split("\n");
    const items: BlockedItem[] = [];
    for (const line of lines) {
      if (!line.includes("FABLE-ESCALATION")) continue;
      const dateMatch = /filed (\d{4}-\d{2}-\d{2})/.exec(line);
      items.push({ source: "queue_escalation", ts: dateMatch ? dateMatch[1] : null, text: line.trim().slice(0, 140) });
    }
    return items.reverse();
  } catch {
    return [];
  }
}

/** Merges all three sources, newest-first (rows with a ts sort before rows
 * without one), capped at 8. Each per-source reader is independently
 * fail-open, so one bad file degrades to "contributes nothing", never a 500
 * for the whole card. */
export async function readBlocked(): Promise<BlockedItem[]> {
  const [discord, proposals, escalations] = await Promise.all([
    readDiscordBlocked(),
    readConductorProposalsBlocked(),
    readQueueEscalations(),
  ]);
  const all = [...discord, ...proposals, ...escalations];
  all.sort((a, b) => {
    if (a.ts && b.ts) return b.ts.localeCompare(a.ts);
    if (a.ts) return -1;
    if (b.ts) return 1;
    return 0;
  });
  return all.slice(0, 8);
}

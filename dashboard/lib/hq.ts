import { promises as fs } from "node:fs";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
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

// HQ-POSITION-TRUTH (2026-09-15): thin fs adapter around lib/hq-positions-pure.ts.
// Reads the LIVE per-account position source (automation/state/fleet/<arm>/
// exit-state.json + the shared fills-ledger.jsonl) and hands already-parsed
// JSON to the pure module -- same split every other hq-*-pure.ts module in
// this directory documents (pure logic stays fs-free and node --test-able).

import fs from "node:fs/promises";
import { paths } from "./workspace";
import {
  buildAccountPositions,
  type AccountPositions,
  type FillRow,
} from "./hq-positions-pure";

// fills-ledger.jsonl is ~550KB / 1.3k rows as of 2026-09-15 and grows
// slowly (a handful of fills per trading day) -- a full read is cheap today,
// but this caps the read the same way lib/hq.ts#readCoreDecisionsLatest
// bounds core-decisions.jsonl, so a future multi-MB ledger never turns an
// /api/hq poll into a full-file read.
const FILLS_LEDGER_TAIL_BYTES = 4 * 1024 * 1024; // 4 MiB

async function readTailText(filePath: string, tailBytes: number): Promise<string> {
  const handle = await fs.open(filePath, "r");
  try {
    const stat = await handle.stat();
    const start = Math.max(0, stat.size - tailBytes);
    const length = stat.size - start;
    if (length <= 0) return "";
    const buffer = Buffer.alloc(length);
    await handle.read(buffer, 0, length, start);
    const text = buffer.toString("utf-8");
    // Same "drop a likely-truncated first line after a mid-file seek" rule
    // every other tail reader in this codebase (readCoreDecisionsLatest,
    // setup/scripts/hq_market_correlate.py's _tail_lines) already applies.
    return start > 0 ? text.split("\n").slice(1).join("\n") : text;
  } finally {
    await handle.close();
  }
}

/** Reads + parses one arm's exit-state.json. Never throws -- a missing or
 * corrupt file returns `{ data: null, error: <explicit reason> }`, which
 * buildAccountPositions surfaces as `AccountPositions.error` rather than a
 * silently-confident flat result (failure-honesty rule). */
async function readExitState(filePath: string): Promise<{ data: unknown; error: string | null }> {
  let text: string;
  try {
    text = await fs.readFile(filePath, "utf-8");
  } catch (e: unknown) {
    const code = (e as NodeJS.ErrnoException)?.code;
    return { data: null, error: code === "ENOENT" ? `exit-state file not found: ${filePath}` : `exit-state read failed: ${String(e)}` };
  }
  try {
    return { data: JSON.parse(text), error: null };
  } catch (e: unknown) {
    return { data: null, error: `exit-state JSON parse failed: ${String(e)}` };
  }
}

/** Reads + parses the full (tail-bounded) fills-ledger.jsonl into FillRow[].
 * A malformed individual line is skipped, not fatal -- same per-line
 * fail-open convention as every other jsonl reader in this codebase. A
 * missing ledger file (should never happen once the engine has fired once)
 * is reported as an explicit error, never a silent empty list. */
async function readAllFills(filePath: string): Promise<{ rows: FillRow[]; error: string | null }> {
  let text: string;
  try {
    text = await readTailText(filePath, FILLS_LEDGER_TAIL_BYTES);
  } catch (e: unknown) {
    const code = (e as NodeJS.ErrnoException)?.code;
    return { rows: [], error: code === "ENOENT" ? `fills-ledger file not found: ${filePath}` : `fills-ledger read failed: ${String(e)}` };
  }
  const rows: FillRow[] = [];
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    let raw: Record<string, unknown>;
    try {
      raw = JSON.parse(line);
    } catch {
      continue; // one malformed/truncated line never blocks the rest
    }
    const arm = typeof raw.arm === "string" ? raw.arm : null;
    const symbol = typeof raw.symbol === "string" ? raw.symbol : null;
    const side = raw.side === "buy" || raw.side === "sell" ? raw.side : null;
    const qty = typeof raw.qty === "number" ? raw.qty : null;
    const price = typeof raw.price === "number" ? raw.price : null;
    const tsEt = typeof raw.ts_et === "string" ? raw.ts_et : null;
    const dateEt = typeof raw.date_et === "string" ? raw.date_et : null;
    if (!arm || !symbol || !side || qty === null || price === null || !tsEt || !dateEt) continue;
    rows.push({
      arm,
      symbol,
      side,
      qty,
      price,
      multiplier: typeof raw.multiplier === "number" ? raw.multiplier : 100,
      ts_et: tsEt,
      date_et: dateEt,
    });
  }
  return { rows, error: null };
}

function todayEtDateStr(): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/** Per-account (safe-2/bold-2) LIVE position truth for /api/hq's
 * `trading.position` field. Both arms read in parallel; the shared fills
 * ledger is read once and reused for both (avoids reading the same file
 * twice per poll). */
export async function readHqPositions(): Promise<{ "safe-2": AccountPositions; "bold-2": AccountPositions }> {
  const todayDateEt = todayEtDateStr();
  const [safeExit, boldExit, fills] = await Promise.all([
    readExitState(paths.fleetExitState["safe-2"]),
    readExitState(paths.fleetExitState["bold-2"]),
    readAllFills(paths.fillsLedger),
  ]);
  return {
    "safe-2": buildAccountPositions(safeExit.data, safeExit.error, fills.rows, fills.error, "safe-2", todayDateEt),
    "bold-2": buildAccountPositions(boldExit.data, boldExit.error, fills.rows, fills.error, "bold-2", todayDateEt),
  };
}

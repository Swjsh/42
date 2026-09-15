// HQ-POSITION-TRUTH (2026-09-15): pure interpretation of the LIVE per-account
// position truth -- automation/state/fleet/<arm>/exit-state.json (open
// positions, one entry per OPEN option symbol, `{}` == flat -- written by
// setup/scripts/heartbeat_core.py's exit_manager) and
// automation/state/fills-ledger.jsonl (every real fill, one row per side of
// every trade -- written by the same engine). Root cause this replaces:
// dashboard/lib/workspace.ts's positionSafe/positionBold
// (current-position-{safe,bold}.json) and setup/scripts/hq_market_correlate.py's
// POSITION_PATHS both read dead files nothing writes, so HQ fell back to
// HOLD/flat the instant the engine's per-tick `action` ledger stopped
// logging ENTER_* (2 minutes into a multi-hour hold) even while a real
// broker position stayed open.
//
// Zero fs/path imports (same "pure, node --test-able without a bundler"
// split every other *-pure.ts module in this directory documents) -- the fs
// reads live in the thin adapter lib/hq-positions.ts.

/** One OPEN leg read off exit-state.json's per-symbol dict. */
export interface OpenPosition {
  symbol: string;
  side: string; // "C" | "P" as exit-state.json writes it; "?" if unreadable
  qty: number;
  entryPremium: number;
  strategy: string | null;
  hwmPremium: number | null;
  tp1Filled: boolean;
}

/** One CLOSED round trip (a FIFO buy-lot matched against a sell) realized
 * TODAY, derived from fills-ledger.jsonl. */
export interface ClosedPosition {
  symbol: string;
  qty: number;
  entry: number;
  exit: number;
  realizedUsd: number;
  exitTs: string;
}

/** Per-account position truth for /api/hq's `trading.position.<acct>` field. */
export interface AccountPositions {
  open: OpenPosition[];
  closedToday: ClosedPosition[];
  realizedTodayUsd: number;
  /** Explicit failure signal for a missing/corrupt source file -- per
   * judgment-guards failure-honesty, a read failure NEVER degrades to a
   * silent flat/null; the UI must be able to tell "confirmed flat" apart
   * from "couldn't confirm." */
  error: string | null;
}

const DEFAULT_MULTIPLIER = 100;

const emptyAccountPositions = (error: string | null = null): AccountPositions => ({
  open: [],
  closedToday: [],
  realizedTodayUsd: 0,
  error,
});

/** Parses exit-state.json's raw parsed JSON (dict keyed by option symbol,
 * `{}` == flat) into OpenPosition rows. Never throws -- a malformed entry is
 * skipped, not fatal to the rest of the dict (same fail-open-per-item
 * convention as every other reader in this codebase). Pass the file's
 * ALREADY-PARSED JSON (JSON.parse done by the fs adapter) so this stays
 * synchronous and fs-free. */
export function parseOpenPositions(exitState: unknown): OpenPosition[] {
  if (!exitState || typeof exitState !== "object" || Array.isArray(exitState)) return [];
  const out: OpenPosition[] = [];
  for (const raw of Object.values(exitState as Record<string, unknown>)) {
    if (!raw || typeof raw !== "object") continue;
    const rec = raw as Record<string, unknown>;
    const symbol = typeof rec.symbol === "string" ? rec.symbol : null;
    const entryPremium = typeof rec.entry_premium === "number" ? rec.entry_premium : null;
    const qty = typeof rec.total_qty === "number" ? rec.total_qty : null;
    // A leg missing its own identity/size fields is unusable, not a partial
    // row worth rendering -- skip it rather than guess.
    if (!symbol || entryPremium === null || qty === null) continue;
    out.push({
      symbol,
      side: typeof rec.side === "string" ? rec.side : "?",
      qty,
      entryPremium,
      strategy: typeof rec.strategy === "string" ? rec.strategy : null,
      hwmPremium: typeof rec.hwm_premium === "number" ? rec.hwm_premium : null,
      tp1Filled: rec.tp1_filled === true,
    });
  }
  return out;
}

/** One row of fills-ledger.jsonl, already parsed + shape-checked by the fs
 * adapter (lib/hq-positions.ts#readFillsForArm). */
export interface FillRow {
  arm: string;
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  multiplier: number;
  ts_et: string;
  date_et: string;
}

/** FIFO-matches TODAY's buy fills against sell fills per symbol for one arm,
 * producing closed round trips + their realized P&L. Verified against the
 * measured bold-2 round trip this task was filed against: buy 5x @0.47,
 * sell 5x @0.62 -> (0.62-0.47)*5*100 = +$75.00. */
export function computeClosedToday(
  fills: readonly FillRow[],
  arm: string,
  todayDateEt: string,
): { closed: ClosedPosition[]; realizedUsd: number } {
  const armFills = fills
    .filter((f) => f.arm === arm && f.date_et === todayDateEt)
    .slice()
    .sort((a, b) => a.ts_et.localeCompare(b.ts_et));

  const bySymbol = new Map<string, FillRow[]>();
  for (const f of armFills) {
    const list = bySymbol.get(f.symbol);
    if (list) list.push(f);
    else bySymbol.set(f.symbol, [f]);
  }

  const closed: ClosedPosition[] = [];
  let realizedUsd = 0;
  for (const [symbol, rows] of bySymbol) {
    const buyQueue: { qty: number; price: number; multiplier: number }[] = [];
    for (const row of rows) {
      const multiplier = row.multiplier > 0 ? row.multiplier : DEFAULT_MULTIPLIER;
      if (row.side === "buy") {
        buyQueue.push({ qty: row.qty, price: row.price, multiplier });
        continue;
      }
      // sell: match FIFO against open buy lots for this symbol/arm only --
      // never cross-symbol, never cross-arm (armFills already filtered).
      let remaining = row.qty;
      while (remaining > 0 && buyQueue.length > 0) {
        const lot = buyQueue[0];
        const matchQty = Math.min(remaining, lot.qty);
        const pnl = (row.price - lot.price) * matchQty * multiplier;
        realizedUsd += pnl;
        closed.push({
          symbol,
          qty: matchQty,
          entry: lot.price,
          exit: row.price,
          realizedUsd: pnl,
          exitTs: row.ts_et,
        });
        lot.qty -= matchQty;
        remaining -= matchQty;
        if (lot.qty <= 0) buyQueue.shift();
      }
      // A sell with no matching buy lot (e.g. yesterday's open carried into
      // today's ledger tail) is silently unmatched here -- computeClosedToday
      // only reasons about TODAY's own fills by design (todayDateEt filter
      // above), so a truly cross-day round trip is out of scope, not a bug.
    }
  }
  return { closed, realizedUsd };
}

/** Combines an already-parsed exit-state.json + the full fills-ledger.jsonl
 * row set into one account's position truth. `exitStateError` /
 * `fillsError` are the fs adapter's own read failures (missing/corrupt
 * file) -- surfaced verbatim as `error` rather than silently degrading to
 * an empty-but-confident flat result. */
export function buildAccountPositions(
  exitState: unknown,
  exitStateError: string | null,
  fills: readonly FillRow[],
  fillsError: string | null,
  arm: string,
  todayDateEt: string,
): AccountPositions {
  const error = exitStateError ?? fillsError;
  if (exitStateError) {
    // No usable open-position truth at all -- still attempt closedToday off
    // the fills ledger (independent source) rather than blanking everything,
    // but the error field stays set so the UI never claims confirmed-flat.
    const { closed, realizedUsd } = fillsError
      ? { closed: [], realizedUsd: 0 }
      : computeClosedToday(fills, arm, todayDateEt);
    return { open: [], closedToday: closed, realizedTodayUsd: realizedUsd, error };
  }
  const open = parseOpenPositions(exitState);
  const { closed, realizedUsd } = fillsError
    ? { closed: [], realizedUsd: 0 }
    : computeClosedToday(fills, arm, todayDateEt);
  return { open, closedToday: closed, realizedTodayUsd: realizedUsd, error };
}

/** Parses an OCC-style option symbol (e.g. "SPY260915P00757000") into a
 * short strike label ("P757") for display. Returns null (never throws /
 * guesses) if the symbol doesn't match the expected OCC shape -- callers
 * fall back to the raw symbol in that case. */
export function shortStrikeLabel(symbol: string): string | null {
  const m = /^[A-Z]+\d{6}([CP])(\d{8})$/.exec(symbol);
  if (!m) return null;
  const side = m[1];
  const strikeThousandths = Number.parseInt(m[2], 10);
  if (!Number.isFinite(strikeThousandths)) return null;
  const strike = strikeThousandths / 1000;
  const strikeTxt = Number.isInteger(strike) ? String(strike) : strike.toFixed(2);
  return `${side}${strikeTxt}`;
}

/** Legacy CurrentPosition shape (dashboard/lib/state.ts) -- kept minimal
 * (only the fields callers actually read: TradingFloor.tsx's `pos.status`/
 * `pos.symbol`/`pos.qty`) rather than importing state.ts's type directly, so
 * this pure module stays independent of that file's own import graph. */
export interface LegacyCurrentPositionShape {
  status: string | null;
  symbol?: string;
  qty?: number;
  fill_price?: number;
  stop_price?: number;
  tp1_price?: number;
  profit_lock_floor?: number;
  opened_at_et?: string;
  setup?: string;
  direction?: string;
}

/** Adapts the LIVE exit-state truth to the legacy current-position-{safe,
 * bold}.json shape dashboard/app/api/state/route.ts (the OLDER "/" floor
 * dashboard, distinct from /hq) has always exposed as `positionSafe`/
 * `positionBold` -- so that surface stops reading the dead
 * current-position-*.json files too (root cause this whole task fixes).
 * Returns `status: "flat"` when there is no open leg (never null -- null
 * previously meant "file missing/unreadable" under the old dead-file
 * reader, which this source no longer produces once exit-state.json itself
 * reads cleanly; a genuine read error surfaces via `error` instead of a
 * silently-wrong FLAT). */
export function toLegacyCurrentPosition(position: AccountPositions): LegacyCurrentPositionShape & { error: string | null } {
  if (position.error) return { status: null, error: position.error };
  if (position.open.length === 0) return { status: "flat", error: null };
  const leg = position.open.slice().sort((a, b) => b.qty - a.qty)[0];
  const direction = leg.side === "C" ? "bull" : leg.side === "P" ? "bear" : undefined;
  return {
    status: "open",
    symbol: leg.symbol,
    qty: leg.qty,
    fill_price: leg.entryPremium,
    profit_lock_floor: leg.hwmPremium ?? undefined,
    setup: leg.strategy ?? undefined,
    direction,
    error: null,
  };
}

/** One-line "IN POSITION" clause for a HOLD tick that is actually sitting on
 * an open leg -- e.g. "safe · IN PUT 3x P757 @1.08". Null when the account
 * has no open legs (caller falls back to the normal action text) or on a
 * read error (caller shows the error instead of guessing flat). */
export function formatPositionClause(label: string, position: AccountPositions | null | undefined): string | null {
  if (!position || position.error || position.open.length === 0) return null;
  // Multiple open legs (rare -- normally one symbol split TP1/runner) : show
  // the largest-qty leg, same "most material fact first" convention the
  // rest of this codebase's one-line summaries use.
  const leg = position.open.slice().sort((a, b) => b.qty - a.qty)[0];
  const dirTxt = leg.side === "C" ? "CALL" : leg.side === "P" ? "PUT" : leg.side;
  const strikeTxt = shortStrikeLabel(leg.symbol) ?? leg.symbol;
  return `${label} · IN ${dirTxt} ${leg.qty}x ${strikeTxt} @${leg.entryPremium.toFixed(2)}`;
}

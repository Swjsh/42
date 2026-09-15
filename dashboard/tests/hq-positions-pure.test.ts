// HQ-POSITION-TRUTH (2026-09-15): unit tests for lib/hq-positions-pure.ts --
// the LIVE per-account position truth (exit-state.json + fills-ledger.jsonl)
// that replaces the dead current-position-{safe,bold}.json readers.
// Run: cd dashboard && npm test

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parseOpenPositions,
  computeClosedToday,
  buildAccountPositions,
  shortStrikeLabel,
  formatPositionClause,
  toLegacyCurrentPosition,
  type FillRow,
} from "../lib/hq-positions-pure.ts";

// Real safe-2 exit-state.json snapshot (trimmed to the fields this module
// reads) captured 2026-09-15 11:09 ET -- the exact scenario this task was
// filed against: safe-2 bought 3x SPY260915P00757000 @1.08 and is STILL OPEN.
const SAFE_OPEN_EXIT_STATE = {
  SPY260915P00757000: {
    symbol: "SPY260915P00757000",
    side: "P",
    entry_premium: 1.08,
    total_qty: 3,
    tp1_filled: false,
    hwm_premium: 1.57,
    strategy: "BEARISH_REJECTION_RIDE_THE_RIBBON",
  },
};

test("open position: parses a real exit-state.json entry", () => {
  const open = parseOpenPositions(SAFE_OPEN_EXIT_STATE);
  assert.equal(open.length, 1);
  assert.deepEqual(open[0], {
    symbol: "SPY260915P00757000",
    side: "P",
    qty: 3,
    entryPremium: 1.08,
    strategy: "BEARISH_REJECTION_RIDE_THE_RIBBON",
    hwmPremium: 1.57,
    tp1Filled: false,
  });
});

test("flat: an empty {} exit-state dict yields no open positions", () => {
  assert.deepEqual(parseOpenPositions({}), []);
});

test("flat: null/non-object input never throws, yields no open positions", () => {
  assert.deepEqual(parseOpenPositions(null), []);
  assert.deepEqual(parseOpenPositions(undefined), []);
  assert.deepEqual(parseOpenPositions([1, 2, 3]), []);
  assert.deepEqual(parseOpenPositions("not json"), []);
});

test("a malformed entry (missing symbol/entry_premium/total_qty) is skipped, not fatal", () => {
  const dirty = {
    GOOD: { symbol: "SPY260915C00760000", entry_premium: 0.5, total_qty: 5 },
    BAD_NO_SYMBOL: { entry_premium: 0.5, total_qty: 5 },
    BAD_NO_QTY: { symbol: "SPY260915C00761000", entry_premium: 0.5 },
  };
  const open = parseOpenPositions(dirty);
  assert.equal(open.length, 1);
  assert.equal(open[0].symbol, "SPY260915C00760000");
});

function fill(overrides: Partial<FillRow>): FillRow {
  return {
    arm: "bold-2", symbol: "SPY260915P00755000", side: "buy", qty: 5, price: 0.47,
    multiplier: 100, ts_et: "2026-09-15T10:38:06", date_et: "2026-09-15",
    ...overrides,
  };
}

test("closed round trip: bold-2 today's real buy->sell pair realizes +$75.00", () => {
  // Real fills-ledger.jsonl rows for bold-2, 2026-09-15 (measured this
  // session): buy 5x @0.47 10:38 ET, sell 5x @0.62 10:55 ET.
  const fills: FillRow[] = [
    fill({ side: "buy", qty: 5, price: 0.47, ts_et: "2026-09-15T10:38:06" }),
    fill({ side: "sell", qty: 5, price: 0.62, ts_et: "2026-09-15T10:55:06" }),
  ];
  const { closed, realizedUsd } = computeClosedToday(fills, "bold-2", "2026-09-15");
  assert.equal(closed.length, 1);
  assert.equal(closed[0].qty, 5);
  assert.equal(closed[0].entry, 0.47);
  assert.equal(closed[0].exit, 0.62);
  assert.ok(Math.abs(closed[0].realizedUsd - 75) < 1e-6, `expected ~75, got ${closed[0].realizedUsd}`);
  assert.ok(Math.abs(realizedUsd - 75) < 1e-6);
});

test("partial TP1 fill: two sell fills against one buy lot both count, FIFO", () => {
  // Mirrors the real safe-2 2026-09-11 ledger shape: buy 3x, then TWO sell
  // fills (1x then 2x) at the same TP1 price.
  const fills: FillRow[] = [
    fill({ arm: "safe-2", symbol: "SPY260911C00766000", side: "buy", qty: 3, price: 0.45, ts_et: "2026-09-11T13:51:04", date_et: "2026-09-11" }),
    fill({ arm: "safe-2", symbol: "SPY260911C00766000", side: "sell", qty: 1, price: 0.38, ts_et: "2026-09-11T14:01:03.246", date_et: "2026-09-11" }),
    fill({ arm: "safe-2", symbol: "SPY260911C00766000", side: "sell", qty: 2, price: 0.38, ts_et: "2026-09-11T14:01:03.525", date_et: "2026-09-11" }),
  ];
  const { closed, realizedUsd } = computeClosedToday(fills, "safe-2", "2026-09-11");
  assert.equal(closed.length, 2);
  assert.equal(closed[0].qty + closed[1].qty, 3);
  assert.ok(Math.abs(realizedUsd - (0.38 - 0.45) * 3 * 100) < 1e-6);
});

test("closedToday only counts the requested arm + date, never cross-contaminates", () => {
  const fills: FillRow[] = [
    fill({ arm: "bold-2", date_et: "2026-09-15" }),
    fill({ arm: "safe-2", date_et: "2026-09-15", symbol: "SPY260915P00757000", price: 1.08 }),
    fill({ arm: "bold-2", date_et: "2026-09-14" }), // yesterday -- excluded
  ];
  const { closed } = computeClosedToday(fills, "bold-2", "2026-09-15");
  assert.equal(closed.length, 0); // the one bold-2/today fill is an unmatched buy, no sell yet
});

test("buildAccountPositions: open position, no error, empty closedToday", () => {
  const acct = buildAccountPositions(SAFE_OPEN_EXIT_STATE, null, [], null, "safe-2", "2026-09-15");
  assert.equal(acct.error, null);
  assert.equal(acct.open.length, 1);
  assert.equal(acct.open[0].symbol, "SPY260915P00757000");
  assert.deepEqual(acct.closedToday, []);
  assert.equal(acct.realizedTodayUsd, 0);
});

test("buildAccountPositions: flat {} with no error", () => {
  const acct = buildAccountPositions({}, null, [], null, "bold-2", "2026-09-15");
  assert.equal(acct.error, null);
  assert.deepEqual(acct.open, []);
});

test("buildAccountPositions: missing/corrupt exit-state surfaces an explicit error, never a silent flat", () => {
  const acct = buildAccountPositions(null, "exit-state file not found: /x/exit-state.json", [], null, "safe-2", "2026-09-15");
  assert.ok(acct.error);
  assert.match(acct.error!, /not found/);
  assert.deepEqual(acct.open, []);
});

test("buildAccountPositions: corrupt fills ledger surfaces its own error, open positions still usable", () => {
  const acct = buildAccountPositions(SAFE_OPEN_EXIT_STATE, null, [], "fills-ledger read failed: EACCES", "safe-2", "2026-09-15");
  assert.equal(acct.error, "fills-ledger read failed: EACCES");
  assert.equal(acct.open.length, 1); // open truth is independent of the ledger read
  assert.deepEqual(acct.closedToday, []);
});

test("shortStrikeLabel: parses a real OCC put/call symbol", () => {
  assert.equal(shortStrikeLabel("SPY260915P00757000"), "P757");
  assert.equal(shortStrikeLabel("SPY260915C00766000"), "C766");
});

test("shortStrikeLabel: null on an unrecognized shape, never a guess", () => {
  assert.equal(shortStrikeLabel("not-a-symbol"), null);
  assert.equal(shortStrikeLabel(""), null);
});

test("formatPositionClause: the exact scenario this task was filed against", () => {
  const acct = buildAccountPositions(SAFE_OPEN_EXIT_STATE, null, [], null, "safe-2", "2026-09-15");
  assert.equal(formatPositionClause("safe", acct), "safe · IN PUT 3x P757 @1.08");
});

test("formatPositionClause: null when flat or errored -- caller falls back, never fabricates", () => {
  const flat = buildAccountPositions({}, null, [], null, "bold-2", "2026-09-15");
  assert.equal(formatPositionClause("bold", flat), null);
  const errored = buildAccountPositions(null, "exit-state file not found", [], null, "safe-2", "2026-09-15");
  assert.equal(formatPositionClause("safe", errored), null);
  assert.equal(formatPositionClause("safe", null), null);
});

test("toLegacyCurrentPosition: open maps to the old CurrentPosition shape", () => {
  const acct = buildAccountPositions(SAFE_OPEN_EXIT_STATE, null, [], null, "safe-2", "2026-09-15");
  const legacy = toLegacyCurrentPosition(acct);
  assert.equal(legacy.status, "open");
  assert.equal(legacy.symbol, "SPY260915P00757000");
  assert.equal(legacy.qty, 3);
  assert.equal(legacy.fill_price, 1.08);
  assert.equal(legacy.direction, "bear");
  assert.equal(legacy.error, null);
});

test("toLegacyCurrentPosition: flat maps to status \"flat\", not null", () => {
  const acct = buildAccountPositions({}, null, [], null, "bold-2", "2026-09-15");
  const legacy = toLegacyCurrentPosition(acct);
  assert.equal(legacy.status, "flat");
  assert.equal(legacy.error, null);
});

test("toLegacyCurrentPosition: a read error surfaces explicitly, status stays null (not a fake FLAT)", () => {
  const acct = buildAccountPositions(null, "exit-state file not found", [], null, "safe-2", "2026-09-15");
  const legacy = toLegacyCurrentPosition(acct);
  assert.equal(legacy.status, null);
  assert.equal(legacy.error, "exit-state file not found");
});

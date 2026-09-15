// HQ-TRADE-MOMENTS (2026-09-15): unit tests for lib/hq-trade-moments-pure.ts
// -- real-fill world events (ENTER/EXIT), their one-line copy, and the
// active-window filter that drives the Pilot bubble + HUD ticker.
// Run: cd dashboard && npm test

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  buildTradeMomentEvents,
  formatTradeMomentLine,
  activeTradeMoments,
  etTsToComparableMs,
  type TradeMomentEvent,
} from "../lib/hq-trade-moments-pure.ts";
import { computeClosedToday, type FillRow, type ClosedPosition } from "../lib/hq-positions-pure.ts";

function fill(overrides: Partial<FillRow>): FillRow {
  return {
    activityId: "act-1",
    arm: "safe-2",
    symbol: "SPY260915P00757000",
    side: "buy",
    qty: 3,
    price: 1.08,
    multiplier: 100,
    ts_et: "2026-09-15T11:46:03.019510",
    date_et: "2026-09-15",
    ...overrides,
  };
}

test("buildTradeMomentEvents: a buy fill becomes an ENTER with no realized $", () => {
  const events = buildTradeMomentEvents([fill({})], []);
  assert.equal(events.length, 1);
  assert.equal(events[0].kind, "ENTER");
  assert.equal(events[0].realizedUsd, null);
  assert.equal(events[0].activityId, "act-1");
});

test("buildTradeMomentEvents: real safe-2 exit fill sums its own closed rows into one EXIT event", () => {
  // Real safe-2 2026-09-15 exit: sell 3x @0.73, closing the 1.08 entry, -$105.
  const sellFill = fill({ activityId: "exit-act-1", side: "sell", price: 0.73, ts_et: "2026-09-15T11:46:03.019" });
  const closed: ClosedPosition[] = [
    { symbol: "SPY260915P00757000", qty: 3, entry: 1.08, exit: 0.73, realizedUsd: -105, exitTs: "2026-09-15T11:46:03.019", exitActivityId: "exit-act-1" },
  ];
  const events = buildTradeMomentEvents([sellFill], closed);
  assert.equal(events.length, 1);
  assert.equal(events[0].kind, "EXIT");
  assert.equal(events[0].realizedUsd, -105);
});

test("buildTradeMomentEvents: a sell fill that FIFO-split into 2 ClosedPosition rows collapses to ONE event", () => {
  const sellFill = fill({ activityId: "split-exit", side: "sell", qty: 3 });
  const closed: ClosedPosition[] = [
    { symbol: "X", qty: 1, entry: 0.45, exit: 0.38, realizedUsd: -7, exitTs: "t", exitActivityId: "split-exit" },
    { symbol: "X", qty: 2, entry: 0.45, exit: 0.38, realizedUsd: -14, exitTs: "t", exitActivityId: "split-exit" },
  ];
  const events = buildTradeMomentEvents([sellFill], closed);
  assert.equal(events.length, 1);
  assert.ok(Math.abs(events[0].realizedUsd! - -21) < 1e-6);
});

test("buildTradeMomentEvents: an unmatched sell (cross-day carry) still emits an EXIT with realizedUsd:null, never dropped", () => {
  const events = buildTradeMomentEvents([fill({ side: "sell" })], []);
  assert.equal(events.length, 1);
  assert.equal(events[0].kind, "EXIT");
  assert.equal(events[0].realizedUsd, null);
});

test("formatTradeMomentLine: real safe-2 entry line", () => {
  const ev: TradeMomentEvent = { activityId: "a", arm: "safe-2", kind: "ENTER", symbol: "SPY260915P00757000", qty: 3, price: 1.08, tsEt: "t", realizedUsd: null };
  assert.equal(formatTradeMomentLine(ev), "safe-2 ENTER put 3x P757 @1.08");
});

test("formatTradeMomentLine: real bold-2 winning exit line (verified: buy 5x@0.47 -> sell 5x@0.62 = +$75)", () => {
  const ev: TradeMomentEvent = { activityId: "a", arm: "bold-2", kind: "EXIT", symbol: "SPY260915P00755000", qty: 5, price: 0.62, tsEt: "t", realizedUsd: 75 };
  assert.equal(formatTradeMomentLine(ev), "bold-2 EXIT @0.62 +$75");
});

test("formatTradeMomentLine: a real losing exit reads with a minus sign, never a bare magnitude", () => {
  const ev: TradeMomentEvent = { activityId: "a", arm: "safe-2", kind: "EXIT", symbol: "SPY260915P00757000", qty: 3, price: 0.73, tsEt: "t", realizedUsd: -105 };
  assert.equal(formatTradeMomentLine(ev), "safe-2 EXIT @0.73 -$105");
});

test("etTsToComparableMs: two ET wall-clock strings 75s apart diff to exactly 75000ms", () => {
  const a = etTsToComparableMs("2026-09-15T11:46:03");
  const b = etTsToComparableMs("2026-09-15T11:47:18");
  assert.equal(b - a, 75_000);
});

test("activeTradeMoments: an event inside its 75s default window is active", () => {
  const ev: TradeMomentEvent = { activityId: "a", arm: "safe-2", kind: "ENTER", symbol: "S", qty: 1, price: 1, tsEt: "2026-09-15T11:46:00", realizedUsd: null };
  const now = etTsToComparableMs("2026-09-15T11:47:00"); // 60s later
  assert.deepEqual(activeTradeMoments([ev], now), [ev]);
});

test("activeTradeMoments: an event past its window is excluded (no client-remembered repeats)", () => {
  const ev: TradeMomentEvent = { activityId: "a", arm: "safe-2", kind: "ENTER", symbol: "S", qty: 1, price: 1, tsEt: "2026-09-15T11:46:00", realizedUsd: null };
  const now = etTsToComparableMs("2026-09-15T11:48:00"); // 120s later, past the 75s default
  assert.deepEqual(activeTradeMoments([ev], now), []);
});

test("activeTradeMoments: a future-timestamped fill (clock skew) never shows as active", () => {
  const ev: TradeMomentEvent = { activityId: "a", arm: "safe-2", kind: "ENTER", symbol: "S", qty: 1, price: 1, tsEt: "2026-09-15T11:48:00", realizedUsd: null };
  const now = etTsToComparableMs("2026-09-15T11:46:00"); // "now" is BEFORE the fill's own ts
  assert.deepEqual(activeTradeMoments([ev], now), []);
});

test("activeTradeMoments: multiple active events sort newest-first", () => {
  const older: TradeMomentEvent = { activityId: "a", arm: "safe-2", kind: "ENTER", symbol: "S", qty: 1, price: 1, tsEt: "2026-09-15T11:46:00", realizedUsd: null };
  const newer: TradeMomentEvent = { activityId: "b", arm: "bold-2", kind: "ENTER", symbol: "S", qty: 1, price: 1, tsEt: "2026-09-15T11:46:30", realizedUsd: null };
  const now = etTsToComparableMs("2026-09-15T11:46:40");
  const active = activeTradeMoments([older, newer], now);
  assert.deepEqual(active.map((e) => e.activityId), ["b", "a"]);
});

test("END-TO-END with today's REAL fills-ledger.jsonl rows for bold-2 (verified against the live file this session): the entry+exit pair produces an active ENTER and EXIT bubble at a simulated 'now' inside the window, and neither shows once 'now' moves past it", () => {
  // Verbatim from automation/state/fills-ledger.jsonl, 2026-09-15: buy 5x
  // SPY260915P00755000 @0.47 at 10:38:06.135 ET, sell 5x @0.62 at
  // 10:55:06.438 ET -- the exact bold-2 round trip this whole position-truth
  // effort (2026-09-15) was originally filed against, realizing +$75.00.
  const realFills: FillRow[] = [
    { activityId: "20260915103806135::9642f234-a4c4-43e1-8a02-3c17fcd3132c", arm: "bold-2", symbol: "SPY260915P00755000", side: "buy", qty: 5, price: 0.47, multiplier: 100, ts_et: "2026-09-15T10:38:06.135388", date_et: "2026-09-15" },
    { activityId: "20260915105506438::88b1a453-52bb-4b08-a541-118e4c9bdfd6", arm: "bold-2", symbol: "SPY260915P00755000", side: "sell", qty: 5, price: 0.62, multiplier: 100, ts_et: "2026-09-15T10:55:06.438524", date_et: "2026-09-15" },
  ];
  const { closed, realizedUsd } = computeClosedToday(realFills, "bold-2", "2026-09-15");
  assert.ok(Math.abs(realizedUsd - 75) < 1e-6);
  const events = buildTradeMomentEvents(realFills, closed);
  assert.equal(events.length, 2);

  // Simulated "now" 40s after the real exit fill -- inside the 75s default
  // window (this is the "simulated now inside the window" proof the task's
  // own verify step asks for, since the real window can't be observed live
  // after market hours). The entry fill (10:38:06) is ~17min older than
  // "now" here -- correctly OUT of its own window by then, so only the
  // more-recent EXIT bubble is still active (one bubble per fill's OWN
  // window, not a shared trade-level window).
  const nowInsideWindow = etTsToComparableMs("2026-09-15T10:55:46.438524");
  const activeInWindow = activeTradeMoments(events, nowInsideWindow);
  assert.equal(activeInWindow.length, 1);
  assert.equal(activeInWindow[0].kind, "EXIT");
  assert.equal(formatTradeMomentLine(activeInWindow[0]), "bold-2 EXIT @0.62 +$75");

  // Simulated "now" right at the entry fill's own moment -- its bubble is
  // active on its own terms, independent of the exit 17 minutes later.
  const nowAtEntry = etTsToComparableMs("2026-09-15T10:38:36.135388"); // 30s after the entry fill
  const activeAtEntry = activeTradeMoments(events, nowAtEntry);
  assert.equal(activeAtEntry.length, 1);
  assert.equal(formatTradeMomentLine(activeAtEntry[0]), "bold-2 ENTER put 5x P755 @0.47");

  // 76s after the exit fill -- just past the 75s window -- neither shows.
  const nowPastWindow = etTsToComparableMs("2026-09-15T10:56:22.438524");
  assert.deepEqual(activeTradeMoments(events, nowPastWindow), []);
});

test("activeTradeMoments: an explicit custom window is honored", () => {
  const ev: TradeMomentEvent = { activityId: "a", arm: "safe-2", kind: "ENTER", symbol: "S", qty: 1, price: 1, tsEt: "2026-09-15T11:46:00", realizedUsd: null };
  const now = etTsToComparableMs("2026-09-15T11:46:50"); // 50s later
  assert.deepEqual(activeTradeMoments([ev], now, 30), []); // outside a 30s window
  assert.deepEqual(activeTradeMoments([ev], now, 60), [ev]); // inside a 60s window
});

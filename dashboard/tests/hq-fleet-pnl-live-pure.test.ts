// HQ-TRADE-MOMENTS (2026-09-15): unit tests for lib/hq-fleet-pnl-live-pure.ts
// -- per-arm TODAY P&L rolled from fills-ledger FIFO AccountPositions.
// Run: cd dashboard && npm test

import { test } from "node:test";
import assert from "node:assert/strict";
import { buildFleetPnlLive } from "../lib/hq-fleet-pnl-live-pure.ts";
import type { AccountPositions } from "../lib/hq-positions-pure.ts";

function acct(overrides: Partial<AccountPositions>): AccountPositions {
  return { open: [], closedToday: [], realizedTodayUsd: 0, error: null, ...overrides };
}

const ARM_ORDER = [
  { id: "safe-3", displayName: "FLEET-TIGHT-S (T20H)" },
  { id: "safe-2", displayName: "CORE-SAFE (46VG)" },
  { id: "risky-1", displayName: "FLEET-FULLSEND-R (V0A4)" },
  { id: "bold-2", displayName: "CORE-BOLD (U67N)" },
  { id: "risky-3", displayName: "FLEET-LOOSE-R (5H6Z)" },
];

test("buildFleetPnlLive: the real 2026-09-15 5-arm book (verified against journal/trades.csv this session)", () => {
  const positions: Record<string, AccountPositions> = {
    "safe-2": acct({ realizedTodayUsd: -105, closedToday: [{ symbol: "X", qty: 3, entry: 1.08, exit: 0.73, realizedUsd: -105, exitTs: "t", exitActivityId: "e1" }] }),
    "bold-2": acct({ realizedTodayUsd: 75, closedToday: [{ symbol: "X", qty: 5, entry: 0.47, exit: 0.62, realizedUsd: 75, exitTs: "t", exitActivityId: "e2" }] }),
    "safe-3": acct({ realizedTodayUsd: -114, closedToday: [{ symbol: "X", qty: 3, entry: 1.12, exit: 0.74, realizedUsd: -114, exitTs: "t", exitActivityId: "e3" }] }),
    "risky-1": acct({ realizedTodayUsd: -195, closedToday: [{ symbol: "X", qty: 5, entry: 1.13, exit: 0.74, realizedUsd: -195, exitTs: "t", exitActivityId: "e4" }] }),
    "risky-3": acct({ realizedTodayUsd: -190, closedToday: [{ symbol: "X", qty: 5, entry: 1.12, exit: 0.74, realizedUsd: -190, exitTs: "t", exitActivityId: "e5" }] }),
  };
  const result = buildFleetPnlLive(positions, ARM_ORDER);
  assert.equal(result.arms.length, 5);
  assert.equal(result.arms.map((a) => a.armId).join(","), "safe-3,safe-2,risky-1,bold-2,risky-3");
  assert.equal(result.arms.find((a) => a.armId === "safe-2")!.realizedUsd, -105);
  assert.equal(result.arms.find((a) => a.armId === "bold-2")!.realizedUsd, 75);
  assert.ok(Math.abs(result.bookRealizedUsd - -529) < 1e-6, `expected ~-529, got ${result.bookRealizedUsd}`);
});

test("buildFleetPnlLive: wins/losses counted per closed trade, not per arm", () => {
  const positions: Record<string, AccountPositions> = {
    "safe-2": acct({
      realizedTodayUsd: 10,
      closedToday: [
        { symbol: "X", qty: 1, entry: 1, exit: 1.1, realizedUsd: 10, exitTs: "t", exitActivityId: "w1" },
        { symbol: "X", qty: 1, entry: 1, exit: 0.9, realizedUsd: -10, exitTs: "t", exitActivityId: "l1" },
        { symbol: "X", qty: 1, entry: 1, exit: 1.1, realizedUsd: 10, exitTs: "t", exitActivityId: "w2" },
      ],
    }),
  };
  const result = buildFleetPnlLive(positions, [{ id: "safe-2", displayName: null }]);
  const row = result.arms[0];
  assert.equal(row.trades, 3);
  assert.equal(row.wins, 2);
  assert.equal(row.losses, 1);
});

test("buildFleetPnlLive: open qty sums across legs, and a read error contributes $0 to the book but still shows its own row", () => {
  const positions: Record<string, AccountPositions> = {
    "safe-2": acct({
      open: [
        { symbol: "X", side: "P", qty: 2, entryPremium: 1, strategy: null, hwmPremium: null, tp1Filled: false },
        { symbol: "Y", side: "P", qty: 3, entryPremium: 1, strategy: null, hwmPremium: null, tp1Filled: false },
      ],
    }),
    "bold-2": acct({ error: "exit-state file not found", realizedTodayUsd: 999 }), // pathological: error set but a stray number present
  };
  const result = buildFleetPnlLive(positions, [{ id: "safe-2", displayName: null }, { id: "bold-2", displayName: null }]);
  assert.equal(result.arms.find((a) => a.armId === "safe-2")!.openQty, 5);
  const errored = result.arms.find((a) => a.armId === "bold-2")!;
  assert.equal(errored.error, "exit-state file not found");
  assert.equal(result.bookRealizedUsd, 0); // the errored arm's stray 999 never counts toward the book
});

test("buildFleetPnlLive: an arm missing from positionsByArm entirely still gets a real, explicit-error row", () => {
  const result = buildFleetPnlLive({}, [{ id: "safe-2", displayName: "CORE-SAFE" }]);
  assert.equal(result.arms.length, 1);
  assert.ok(result.arms[0].error);
  assert.equal(result.bookRealizedUsd, 0);
});

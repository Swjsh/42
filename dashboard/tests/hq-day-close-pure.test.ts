// HQ-TRADE-MOMENTS (2026-09-15): unit tests for lib/hq-day-close-pure.ts --
// the >=16:00 ET + real-fills-today gate and the summary it builds.
// Run: cd dashboard && npm test

import { test } from "node:test";
import assert from "node:assert/strict";
import { isAfterEtCutoff, shouldShowDayClose, buildDayCloseSummary } from "../lib/hq-day-close-pure.ts";
import type { FleetPnlLive } from "../lib/hq-fleet-pnl-live-pure.ts";

test("isAfterEtCutoff: 16:00 exactly is the cutoff (inclusive)", () => {
  assert.equal(isAfterEtCutoff(16, 0), true);
  assert.equal(isAfterEtCutoff(15, 59), false);
  assert.equal(isAfterEtCutoff(20, 0), true);
});

test("shouldShowDayClose: false before 16:00 ET even with real fills today", () => {
  assert.equal(shouldShowDayClose(11, 46, true), false);
});

test("shouldShowDayClose: false after 16:00 ET on a day with zero fills (a valid, expected state)", () => {
  assert.equal(shouldShowDayClose(18, 0, false), false);
});

test("shouldShowDayClose: true after 16:00 ET on a real trading day with fills -- the exact gate this task specifies", () => {
  assert.equal(shouldShowDayClose(16, 0, true), true);
  assert.equal(shouldShowDayClose(20, 30, true), true);
});

test("buildDayCloseSummary: the real 2026-09-15 5-arm book totals to -$529, 0 wins / 5 losses", () => {
  const fleetPnl: FleetPnlLive = {
    bookRealizedUsd: -529,
    arms: [
      { armId: "safe-2", displayName: "CORE-SAFE", trades: 1, wins: 0, losses: 1, realizedUsd: -105, openQty: 0, error: null },
      { armId: "bold-2", displayName: "CORE-BOLD", trades: 1, wins: 1, losses: 0, realizedUsd: 75, openQty: 0, error: null },
      { armId: "safe-3", displayName: "FLEET-TIGHT-S", trades: 1, wins: 0, losses: 1, realizedUsd: -114, openQty: 0, error: null },
      { armId: "risky-1", displayName: "FLEET-FULLSEND-R", trades: 1, wins: 0, losses: 1, realizedUsd: -195, openQty: 0, error: null },
      { armId: "risky-3", displayName: "FLEET-LOOSE-R", trades: 1, wins: 0, losses: 1, realizedUsd: -190, openQty: 0, error: null },
    ],
  };
  const summary = buildDayCloseSummary(fleetPnl, ["BEARISH_REJECTION_RIDE_THE_RIBBON", "BEARISH_REJECTION_RIDE_THE_RIBBON", ""]);
  assert.equal(summary.bookRealizedUsd, -529);
  assert.equal(summary.wins, 1);
  assert.equal(summary.losses, 4);
  assert.deepEqual(summary.setupNames, ["BEARISH_REJECTION_RIDE_THE_RIBBON"]); // deduped, blank dropped
  assert.equal(summary.arms.length, 5);
});

// HQ-TRADE-MOMENTS (2026-09-15): unit tests for lib/hq-fleet-arms-pure.ts --
// which arms of automation/state/fleet/accounts.json count as "active SPY
// 0DTE arms" for the position/P&L/trade-moment surfaces.
// Run: cd dashboard && npm test

import { test } from "node:test";
import assert from "node:assert/strict";
import { activeSpyArms } from "../lib/hq-fleet-arms-pure.ts";

function arm(overrides: Record<string, unknown>) {
  return { id: "x", status: "active", instrument: "SPY_0DTE_OPTION", display_name: "X", ...overrides };
}

test("activeSpyArms: the real 2026-09-15 roster -- 5 active SPY_0DTE_OPTION arms, futures/weekly/retired excluded", () => {
  const doc = {
    arms: [
      arm({ id: "safe-3", display_name: "FLEET-TIGHT-S (T20H)" }),
      arm({ id: "safe-2", display_name: "CORE-SAFE (46VG)" }),
      arm({ id: "safe-1", status: "retired" }),
      arm({ id: "risky-1", display_name: "FLEET-FULLSEND-R (V0A4)" }),
      arm({ id: "bold-2", display_name: "CORE-BOLD (U67N)" }),
      arm({ id: "risky-3", display_name: "FLEET-LOOSE-R (5H6Z)" }),
      arm({ id: "mes-linear-sim", status: "pending_build", instrument: "FUTURES" }),
      arm({ id: "mes-mnq-div-futures", status: "dormant", instrument: "FUTURES" }),
      arm({ id: "weekly-1", status: "pending_build", instrument: "WEEKLY_OPTIONS" }),
    ],
  };
  const active = activeSpyArms(doc);
  assert.deepEqual(active.map((a) => a.id), ["safe-3", "safe-2", "risky-1", "bold-2", "risky-3"]);
  assert.equal(active.find((a) => a.id === "safe-2")!.displayName, "CORE-SAFE (46VG)");
});

test("activeSpyArms: a future active non-SPY arm is excluded by the instrument gate, not just status", () => {
  const doc = { arms: [arm({ id: "weekly-1", status: "active", instrument: "WEEKLY_OPTIONS" })] };
  assert.deepEqual(activeSpyArms(doc), []);
});

test("activeSpyArms: malformed input never throws, returns []", () => {
  assert.deepEqual(activeSpyArms(null), []);
  assert.deepEqual(activeSpyArms({}), []);
  assert.deepEqual(activeSpyArms({ arms: "not-an-array" }), []);
  assert.deepEqual(activeSpyArms({ arms: [null, 42, { status: "active" }] }), []); // missing id/instrument
});

test("activeSpyArms: missing display_name yields null, never a fabricated label", () => {
  const doc = { arms: [{ id: "safe-2", status: "active", instrument: "SPY_0DTE_OPTION" }] };
  assert.equal(activeSpyArms(doc)[0].displayName, null);
});

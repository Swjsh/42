// MARKET-TRUTH (2026-09-15): unit tests for lib/engine-action-pure.ts --
// the action-code -> human-reason mapping /api/hq now attaches to every
// CoreDecisionRow. Run: cd dashboard && npm test

import { test } from "node:test";
import assert from "node:assert/strict";
import { describeEngineAction } from "../lib/engine-action-pure.ts";

test("maps every known code from heartbeat_core.py's ledger to its real meaning", () => {
  assert.match(describeEngineAction("SKIP_STALE_TRIGGER"), /fresh trigger bar/);
  assert.match(describeEngineAction("SKIP_NO_LEVELS"), /blind/);
  assert.match(describeEngineAction("SKIP_LATE_ENTRY"), /entry-ceiling/);
  assert.match(describeEngineAction("SKIP_EARLY_ENTRY"), /entry-floor/);
  assert.match(describeEngineAction("SKIP_STALE_SIGHT"), /drifted/);
  assert.match(describeEngineAction("VETOED_BY_MODELS"), /vetoed/);
  assert.match(describeEngineAction("PERCEPTION_ONLY"), /fleet executor/);
  assert.match(describeEngineAction("HOLD"), /no entry trigger/);
});

test("maps raw ENTER_BEAR/ENTER_BULL verdict passthrough", () => {
  assert.match(describeEngineAction("ENTER_BEAR"), /bear trigger fired/);
  assert.match(describeEngineAction("ENTER_BULL"), /bull trigger fired/);
});

test("an unmapped exec-status code shows the raw code, never a guess", () => {
  assert.equal(describeEngineAction("FILLED"), "engine action: FILLED");
});

test("null/undefined/empty never throws and reads honestly", () => {
  assert.equal(describeEngineAction(null), "no action logged yet");
  assert.equal(describeEngineAction(undefined), "no action logged yet");
  assert.equal(describeEngineAction(""), "no action logged yet");
});

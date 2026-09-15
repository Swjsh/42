import { test } from "node:test";
import assert from "node:assert/strict";
import { BUBBLE_FAR_REF_DISTANCE, BUBBLE_MAX_COUNTER_SCALE, BUBBLE_NEAR_HOLD_DISTANCE, bubbleCounterScale } from "../components/hq/bubbleScale.ts";

// On-screen size = base * (1/dist) * k. With base chosen so size(FAR_REF) = 1, the
// policy is: 1 at and beyond FAR_REF (counter-scale cancels 1/dist until the cap),
// natural 1..2 between NEAR_HOLD and FAR_REF, held at 2 closer than NEAR_HOLD.
const onScreen = (dist: number) => (BUBBLE_FAR_REF_DISTANCE / dist) * bubbleCounterScale(dist);

test("far: text stays at the readable floor until the cap", () => {
  assert.equal(bubbleCounterScale(BUBBLE_FAR_REF_DISTANCE), 1);
  assert.ok(Math.abs(onScreen(50) - 1) < 1e-9);
  assert.ok(Math.abs(onScreen(60) - 1) < 1e-9);
  const capDist = BUBBLE_FAR_REF_DISTANCE * BUBBLE_MAX_COUNTER_SCALE;
  assert.equal(bubbleCounterScale(capDist * 2), BUBBLE_MAX_COUNTER_SCALE);
  assert.ok(onScreen(capDist * 2) < 1);
});

test("mid: natural drei scaling between the two references", () => {
  assert.equal(bubbleCounterScale(30), 1);
  assert.ok(onScreen(30) > 1 && onScreen(30) < 2);
  assert.ok(Math.abs(onScreen(BUBBLE_NEAR_HOLD_DISTANCE) - 2) < 1e-9);
});

test("near: held at twice the floor, never a banner", () => {
  for (const d of [15, 8, 3.5, 2.5]) assert.ok(Math.abs(onScreen(d) - 2) < 1e-9, `dist ${d}`);
  // Below the 0.12 counter-scale floor (dist < NEAR_HOLD * 0.12 = 2.28 u, camera on the lens)
  // the bubble may grow again, but never past ~5x the floor.
  assert.ok(onScreen(1) > 2 && onScreen(1) < 5);
  assert.equal(bubbleCounterScale(0), 1);
  assert.equal(bubbleCounterScale(Number.NaN), 1);
});

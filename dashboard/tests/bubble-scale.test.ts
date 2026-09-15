import { test } from "node:test";
import assert from "node:assert/strict";
import { BUBBLE_FAR_REF_DISTANCE, BUBBLE_MAX_COUNTER_SCALE, BUBBLE_NEAR_HOLD_DISTANCE, bubbleCounterScale } from "../components/hq/bubbleScale.ts";

// On-screen size = base * (1/dist) * k. With base chosen so size(FAR_REF) = 1, the
// policy is: 1 at and beyond FAR_REF (counter-scale cancels 1/dist until the cap),
// natural 1..2 between NEAR_HOLD and FAR_REF, held at 2 closer than NEAR_HOLD.
const onScreen = (dist: number) => (BUBBLE_FAR_REF_DISTANCE / dist) * bubbleCounterScale(dist);

test("far: text stays at the readable floor until the cap (item 4: cap now covers the real worst-case camera-to-agent distance, ~96.4u)", () => {
  assert.equal(bubbleCounterScale(BUBBLE_FAR_REF_DISTANCE), 1);
  assert.ok(Math.abs(onScreen(50) - 1) < 1e-9);
  assert.ok(Math.abs(onScreen(60) - 1) < 1e-9);
  // The old cap (1.7 -> 64.6u) used to let the plateau end here; confirmed
  // (Scene.tsx FREE_CAM_MAX_DISTANCE=58 + layout.ts bay-node geometry) the
  // real camera-to-agent distance can reach ~96.4u, so the plateau must
  // still hold at 80u -- this is the regression this pass's own fix covers.
  assert.ok(Math.abs(onScreen(80) - 1) < 1e-9);
  const capDist = BUBBLE_FAR_REF_DISTANCE * BUBBLE_MAX_COUNTER_SCALE;
  assert.ok(capDist >= 96.4, `cap distance ${capDist} must cover the realizable ~96.4u worst case`);
  assert.equal(bubbleCounterScale(capDist * 2), BUBBLE_MAX_COUNTER_SCALE);
  assert.ok(onScreen(capDist * 2) < 1);
});

test("mid: natural drei scaling between the two references", () => {
  assert.equal(bubbleCounterScale(30), 1);
  assert.ok(onScreen(30) > 1 && onScreen(30) < 2);
  assert.ok(Math.abs(onScreen(BUBBLE_NEAR_HOLD_DISTANCE) - 2) < 1e-9);
});

test("near: held at twice the far floor, all the way to the camera touching the character -- no floor, no banner (item 3 fix)", () => {
  for (const d of [15, 8, 3.5, 2.5, 1, 0.1, 0.01]) {
    assert.ok(Math.abs(onScreen(d) - 2) < 1e-9, `dist ${d} -> onScreen ${onScreen(d)}`);
  }
  // Before this pass, the counter-scale floored at k=0.12 below dist=2.28u,
  // so on-screen size grew UNBOUNDED as dist->0 (drei's own objectScale is
  // ~1/dist, confirmed from node_modules/@react-three/drei/web/Html.js).
  // Now k=dist/NEAR_HOLD is unconditional in this branch, so the product
  // stays exactly at the plateau for any dist>0 -- this assertion would
  // have failed under the old floored implementation (onScreen(1) was
  // ~4.56, well above 2).
  assert.equal(bubbleCounterScale(0), 1);
  assert.equal(bubbleCounterScale(Number.NaN), 1);
});

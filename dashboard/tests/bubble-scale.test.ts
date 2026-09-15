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
  // OVERVIEW-FLOOR fix (2026-09-15): FAR_REF/NEAR_HOLD moved 38/19 -> 20/10
  // (ratio held at 2) so the far plateau lands on a real readable pixel
  // value at the actual overview camera distance -- see bubbleScale.ts's
  // own header. The mid (natural-scaling) zone is now [10, 20); 15 sits
  // inside it either way.
  assert.equal(bubbleCounterScale(15), 1);
  assert.ok(onScreen(15) > 1 && onScreen(15) < 2);
  assert.ok(Math.abs(onScreen(BUBBLE_NEAR_HOLD_DISTANCE) - 2) < 1e-9);
});

test("near: held at twice the far floor, all the way to the camera touching the character -- no floor, no banner (item 3 fix)", () => {
  for (const d of [9, 5, 3.5, 2.5, 1, 0.1, 0.01]) {
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

test("overview floor: real rendered pixels at the actual default overview camera clear the >=11px readability bar (2026-09-15 declutter pass)", () => {
  // Reproduces drei's own node_modules/@react-three/drei/web/Html.js
  // non-transform scale formula: distanceFactor / (2*tan(vFOV/2)*dist).
  // distanceFactor=9 and fov=50deg (ultra tier) are fixed constants shared
  // by every hub-center label producer (Agent.tsx/GammaCharacter.tsx/
  // LiveAgents.tsx/BrainCore.tsx) -- duplicated here (not imported) so this
  // test fails loudly if either ever drifts without a matching update here.
  const DISTANCE_FACTOR = 9;
  const FOV_DEG = 50;
  const vFovRad = (FOV_DEG * Math.PI) / 180;
  const nativeScale = (dist: number) => DISTANCE_FACTOR / (2 * Math.tan(vFovRad / 2) * dist);
  const renderedPx = (fontSizePx: number, dist: number) => fontSizePx * nativeScale(dist) * bubbleCounterScale(dist);

  // Default overview camera: Scene.tsx OVERVIEW_CAM_POS, CAMERA_DIST_ULTRA
  // 45u + CAMERA_HEIGHT_ULTRA 31u from the hub-center labels.
  const OVERVIEW_DIST = Math.sqrt(45 * 45 + 31 * 31);
  assert.ok(Math.abs(OVERVIEW_DIST - 54.6) < 0.1, `expected ~54.6u, got ${OVERVIEW_DIST}`);

  // Persona/live-agent/Gamma bubbles: fontSize 24 (Agent.tsx/
  // GammaCharacter.tsx/LiveAgents.tsx).
  assert.ok(renderedPx(24, OVERVIEW_DIST) >= 11, `persona/live-agent bubble only ${renderedPx(24, OVERVIEW_DIST).toFixed(2)}px at the overview`);
  // BRAIN plaque main line: fontSize 34 (BrainCore.tsx PLAQUE_Y).
  assert.ok(renderedPx(34, OVERVIEW_DIST) >= 11, `plaque label only ${renderedPx(34, OVERVIEW_DIST).toFixed(2)}px at the overview`);

  // Root-cause regression guard: the OLD constants (38/2.6/19) gave ~6.1px
  // for the same 24px label at this exact camera -- this is the number J
  // measured from declutter-overview.png. Confirms the fix actually moved
  // the needle rather than coincidentally passing.
  const oldK = (dist: number) => (dist >= 38 ? Math.min(2.6, dist / 38) : dist >= 19 ? 1 : dist / 19);
  const oldRenderedPx = 24 * nativeScale(OVERVIEW_DIST) * oldK(OVERVIEW_DIST);
  assert.ok(Math.abs(oldRenderedPx - 6.1) < 0.2, `expected the old-constants figure to reproduce J's ~6px reading, got ${oldRenderedPx.toFixed(2)}`);
});

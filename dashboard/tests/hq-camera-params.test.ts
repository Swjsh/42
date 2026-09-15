// @ts-nocheck -- same convention as tests/hq-label-declutter.test.ts's own
// header: plain `node --test` needs the explicit ".ts" extension on a
// relative import, which the project's shared tsconfig ("bundler" module
// resolution, no allowImportingTsExtensions) would otherwise fail on during
// `next build`'s project-wide type-check. Zero effect on Node's own type
// stripping at runtime -- these tests run for real.
//
// Run: cd dashboard && node --test tests/hq-camera-params.test.ts
//
// Unit tests for lib/hq-camera-params.ts#parseCameraParams -- the pure
// parsing/validation half of the 3 deterministic capture-framing URL params
// (`?camdist=`, `?camtarget=`, `?tour=0`) Scene.tsx#CameraRig applies.
// Node walk-graph resolution and camera-position math live in CameraRig
// itself (untestable here -- inside <Canvas>, pulls in three/r3f); this
// file only locks down the string-in/validated-struct-out contract.

import { test } from "node:test";
import assert from "node:assert/strict";
import { CAM_DIST_MAX, CAM_DIST_MIN, parseCameraParams } from "../lib/hq-camera-params.ts";

function params(entries: Record<string, string>): URLSearchParams {
  return new URLSearchParams(entries);
}

test("no params at all: byte-for-byte default -- tour on, camDist/camTarget undefined", () => {
  const out = parseCameraParams(params({}));
  assert.deepEqual(out, { camDist: undefined, camTarget: undefined, tour: true });
});

test("camdist: a plain in-range number passes through unclamped", () => {
  const out = parseCameraParams(params({ camdist: "20" }));
  assert.equal(out.camDist, 20);
});

test("camdist: below the floor clamps up to CAM_DIST_MIN", () => {
  const out = parseCameraParams(params({ camdist: "1" }));
  assert.equal(out.camDist, CAM_DIST_MIN);
});

test("camdist: negative clamps up to CAM_DIST_MIN, not dropped", () => {
  const out = parseCameraParams(params({ camdist: "-40" }));
  assert.equal(out.camDist, CAM_DIST_MIN);
});

test("camdist: an absurd huge value clamps down to CAM_DIST_MAX", () => {
  const out = parseCameraParams(params({ camdist: "999999" }));
  assert.equal(out.camDist, CAM_DIST_MAX);
});

test("camdist: NaN input (non-numeric string) is ignored -> undefined", () => {
  const out = parseCameraParams(params({ camdist: "banana" }));
  assert.equal(out.camDist, undefined);
});

test("camdist: Infinity string is ignored -> undefined", () => {
  const out = parseCameraParams(params({ camdist: "Infinity" }));
  assert.equal(out.camDist, undefined);
});

test("camdist: blank value is ignored -> undefined", () => {
  const out = parseCameraParams(params({ camdist: "" }));
  assert.equal(out.camDist, undefined);
});

test("camdist: absent param is undefined, not 0 or NaN", () => {
  const out = parseCameraParams(params({}));
  assert.equal(out.camDist, undefined);
});

test("camtarget: a walk-graph node id string passes through verbatim", () => {
  const out = parseCameraParams(params({ camtarget: "bay-desk-0" }));
  assert.equal(out.camTarget, "bay-desk-0");
});

test("camtarget: campus-gate/hub-center/ambient-core ids all pass through", () => {
  for (const id of ["campus-gate", "hub-center", "ambient-core"]) {
    const out = parseCameraParams(params({ camtarget: id }));
    assert.equal(out.camTarget, id);
  }
});

test("camtarget: blank value is ignored -> undefined (caller never gets an empty-string id)", () => {
  const out = parseCameraParams(params({ camtarget: "" }));
  assert.equal(out.camTarget, undefined);
});

test("camtarget: absent param is undefined", () => {
  const out = parseCameraParams(params({}));
  assert.equal(out.camTarget, undefined);
});

test("camtarget: an id unknown to the walk graph still parses through -- resolution/ignoring happens at the caller, not here", () => {
  const out = parseCameraParams(params({ camtarget: "not-a-real-node" }));
  assert.equal(out.camTarget, "not-a-real-node");
});

test("tour: absent param defaults true (tour stays on)", () => {
  const out = parseCameraParams(params({}));
  assert.equal(out.tour, true);
});

test('tour: exactly "0" disables the tour', () => {
  const out = parseCameraParams(params({ tour: "0" }));
  assert.equal(out.tour, false);
});

test("tour: any other value (\"1\", \"false\", \"no\") leaves the tour ON -- only the literal \"0\" disables it", () => {
  for (const v of ["1", "false", "no", "off"]) {
    const out = parseCameraParams(params({ tour: v }));
    assert.equal(out.tour, true, `tour=${v} should leave the tour on`);
  }
});

test("combined: camdist + camtarget + tour=0 all parse independently in one call", () => {
  const out = parseCameraParams(params({ camdist: "36", camtarget: "hub-center", tour: "0" }));
  assert.deepEqual(out, { camDist: 36, camTarget: "hub-center", tour: false });
});

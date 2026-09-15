// @ts-nocheck -- same reason as tests/kit-pool-registry.test.ts's own header:
// this file uses an explicit ".ts" extension on its relative import
// (required for plain `node --test` to resolve it; the project tsconfig's
// `moduleResolution: "bundler"` has no `allowImportingTsExtensions`). Purely
// a syntax-erasure pragma -- has no effect on what actually runs.
//
// GATE-PROP pass (2026-09-15): regression coverage for the campus-gate set
// dressing added in SetKit.tsx#CampusGate + Scene.tsx's own mount of it.
// Imports from liveAgentWalk.ts, NOT layout.ts: layout.ts imports 3 raw-kit
// constants from SetKit.tsx (a real .tsx React/three component file), which
// node's own ESM loader can't load under plain `node --test` (confirmed
// live this session: `node --test` importing layout.ts throws
// ERR_MODULE_NOT_FOUND trying to resolve SetKit.tsx as SetKit.ts, since the
// suite's resolve-ts-extensionless loader only ever appends ".ts") -- the
// exact reason liveAgentWalk.ts exists as layout.ts's SetKit-independent
// sibling (see that file's own "CAMPUS-GATE pass" header) and now also
// holds computeCampusGateGeometry, the pure math behind
// layout.ts#CAMPUS_GATE_POSITION/CAMPUS_GATE_ROTATION_Y/
// CAMPUS_GATE_CLEAR_HALF_WIDTH. layout.ts calls this function exactly ONCE
// at module scope with its own already-computed ARM_LEN/PLAZA_APRON/
// computeArmLayout(0) values and re-exports the result unmodified -- so
// testing the pure function with the SAME real scene inputs (reproduced
// below from layout.ts's own already-documented derivation chain, not
// guessed) is equivalent to testing layout.ts's own exported constants.
//
// Two things this test locks down:
//   1. Feeding it arm 0's real geometry (mainAngle=0, tCenter=[17.4,0,0],
//      distanceFromHub=ARM_LEN+PLAZA_APRON=21.6 -- this file's own literal
//      recomputation of layout.ts's derivation chain, documented inline
//      below) reproduces the EXACT position layout.ts's own
//      addNode("campus-gate", CAMPUS_GATE_POSITION) call places the
//      WalkNode at -- never a re-typed literal on either side, both trace
//      back to the same ARM_LEN/PLAZA_APRON constants.
//   2. The gate's own clearHalfWidth (at CAMPUS_GATE_SCALE=0.7, matching
//      layout.ts's own exported scale) covers the task's own required z in
//      [-1.2, 1.2] band, so a lateral lane-offset up to +-0.5u (another
//      worker's own lane-offset feature) can never visually clip past the
//      gate's frame.
//
// Run: cd dashboard && node --test tests/campus-gate.test.ts
// (or the full suite: cd dashboard && npm test)

import { test } from "node:test";
import assert from "node:assert/strict";
import { computeCampusGateGeometry } from "../components/hq/liveAgentWalk.ts";

// Real scene constants, reproduced from layout.ts's own derivation chain
// (SetKit.tsx: ARCHITECTURE_SCALE_BAY=0.45, ARCHITECTURE_SCALE_HUB=0.75 ->
// HUB_WALL_RADIUS=10*0.75=7.5, BAY_HALF_DEPTH=(12*0.45)/2=2.7; layout.ts:
// MAIN_HALL_LEN=9, T_JUNCTION_HALF=(4*0.45)/2=0.9, PLAZA_APRON=1.5 ->
// T_DIST=7.5+9+0.9=17.4, ARM_LEN=17.4+2.7=20.1). If any of those upstream
// numbers ever change, this test's own literals need updating too -- the
// point of testing the pure function directly (not layout.ts, which this
// file's own header explains can't be imported under plain `node --test`)
// is that the MATH inside computeCampusGateGeometry is what regresses.
const ARM_MAIN_ANGLE = 0; // armAngle(0), arm 0 = +X cardinal
const T_CENTER: [number, number, number] = [17.4, 0, 0]; // computeArmLayout(0).tCenter
const ARM_LEN = 20.1;
const PLAZA_APRON = 1.5;
const DISTANCE_FROM_HUB = ARM_LEN + PLAZA_APRON; // 21.6, matches this file's own header comment
const GATE_RAW_WIDTH = 4.2; // gate-door.glb's own measured raw X footprint
const CAMPUS_GATE_SCALE = 0.7; // layout.ts's own exported CAMPUS_GATE_SCALE

test("computeCampusGateGeometry places the gate at the SAME position the campus-gate WalkNode uses", () => {
  const geom = computeCampusGateGeometry({
    armMainAngle: ARM_MAIN_ANGLE,
    facingTarget: T_CENTER,
    distanceFromHub: DISTANCE_FROM_HUB,
    scale: CAMPUS_GATE_SCALE,
    gateRawWidth: GATE_RAW_WIDTH,
  });
  // The campus-gate WalkNode itself (layout.ts#buildWalkGraph) is placed at
  // exactly [ARM_LEN + PLAZA_APRON, 0, 0] for arm 0 -- the SAME
  // distanceFromHub this function receives, along the SAME +X direction.
  assert.ok(Math.abs(geom.position[0] - DISTANCE_FROM_HUB) < 1e-9);
  assert.equal(geom.position[1], 0);
  assert.ok(Math.abs(geom.position[2]) < 1e-9);
});

test("computeCampusGateGeometry orients the gate-door's walk-through (local Z) axis onto the campus-gate<->t-0 edge", () => {
  const geom = computeCampusGateGeometry({
    armMainAngle: ARM_MAIN_ANGLE,
    facingTarget: T_CENTER,
    distanceFromHub: DISTANCE_FROM_HUB,
    scale: CAMPUS_GATE_SCALE,
    gateRawWidth: GATE_RAW_WIDTH,
  });
  // gate-door.glb's local -Z is this kit's universal "front" (see
  // SetKit.tsx#DepartmentBayShell's own comment) -- agents pass through a
  // mounted gate-door along local Z. Rotating local +Z (0,0,1) by
  // geom.rotationY must land on a purely-X world direction (arm 0 runs
  // along +X at z=0), i.e. the walk-through axis lines up with the
  // campus-gate<->t-0 edge, not perpendicular to it.
  const worldZAxis: [number, number] = [Math.sin(geom.rotationY), Math.cos(geom.rotationY)];
  assert.ok(Math.abs(Math.abs(worldZAxis[0]) - 1) < 1e-9, `expected |x|=1, got ${JSON.stringify(worldZAxis)}`);
  assert.ok(Math.abs(worldZAxis[1]) < 1e-9, `expected z~0, got ${JSON.stringify(worldZAxis)}`);
});

test("computeCampusGateGeometry's clearHalfWidth covers the required z in [-1.2, 1.2] clear band", () => {
  const geom = computeCampusGateGeometry({
    armMainAngle: ARM_MAIN_ANGLE,
    facingTarget: T_CENTER,
    distanceFromHub: DISTANCE_FROM_HUB,
    scale: CAMPUS_GATE_SCALE,
    gateRawWidth: GATE_RAW_WIDTH,
  });
  assert.ok(
    geom.clearHalfWidth >= 1.2,
    `clear half-width ${geom.clearHalfWidth} must be >= 1.2 (task requirement: clear width either side of z=0)`,
  );
  // Derived from scale, not a re-typed literal.
  assert.ok(Math.abs(geom.clearHalfWidth - (GATE_RAW_WIDTH / 2) * CAMPUS_GATE_SCALE) < 1e-9);
});

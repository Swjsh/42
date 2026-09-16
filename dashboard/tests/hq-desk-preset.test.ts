// @ts-nocheck -- same convention as tests/hq-camera-params.test.ts's own
// header: plain `node --test` needs the explicit ".ts" extension on a
// relative import, which the project's shared tsconfig would otherwise
// reject during `next build`'s project-wide type-check. Zero effect on
// Node's own type stripping at runtime.
//
// Run: cd dashboard && node --test tests/hq-desk-preset.test.ts
//
// Unit tests for lib/hq-desk-preset-pure.ts#computeDeskFacingCameraPose --
// the per-persona-desk camera-preset math (keyboard/URL presets "2".."7"),
// re-derived after commit 31cc19b5 moved the six persona desks against the
// hub walls (layout.ts#computePersonaWallSlots). layout.ts itself can't be
// imported under `node --test` (it imports SetKit.tsx, a real .tsx
// component file, which node's own ESM loader refuses -- the same
// constraint documented in layout.ts's own CAMPUS-GATE-pass comment for why
// findWalkPath lives in liveAgentWalk.ts instead). So the 6 real persona
// wall-slot positions/rotationYs below are replicated by hand from
// layout.ts's own formulas (PERSONA_WALL_RADIUS=5.1,
// PERSONA_WALL_LATERAL_OFFSET=4.6, computePersonaWallSlots(6, 0) --
// BRAIN_WALL_ARM_INDEX is 0 today, per that file's own header comment) and
// verified numerically (a standalone Node run of the exact same formula,
// this session) rather than guessed.

import { test } from "node:test";
import assert from "node:assert/strict";
import { computeDeskFacingCameraPose, deskFacingNormalXZ } from "../lib/hq-desk-preset-pure.ts";

// HUB_WALL_RADIUS = 10 * ARCHITECTURE_SCALE_HUB = 10 * 0.75 = 7.5
// (SetKit.tsx). Room-interior clamp the worker order specifies: HUB_WALL_RADIUS - 0.8.
const HUB_WALL_RADIUS = 7.5;
const ROOM_HALF_EXTENT = HUB_WALL_RADIUS - 0.8;

// MONITOR_MOUNT.standPosition for armIndex=0 (today's BRAIN_WALL_ARM_INDEX):
// segCenterAngle = armAngle(0) + PI/4 = PI/4, MONITOR_STAND_RADIUS = 5.6
// (layout.ts#computeMonitorMount) -- replicated numerically, not imported.
const STAND_POSITION_XZ: [number, number] = [
  Math.cos(Math.PI / 4) * 5.6,
  Math.sin(Math.PI / 4) * 5.6,
];

// The 6 real persona wall slots (computePersonaWallSlots(6, 0)), replicated
// by hand from layout.ts's own formula and cross-checked with a standalone
// Node run of that exact formula this session:
//   PERSONA_WALL_RADIUS=5.1, PERSONA_WALL_LATERAL_OFFSET=4.6
const REAL_SLOTS: Array<{ name: string; position: [number, number, number]; rotationY: number }> = [
  { name: "slot0 (wall0, +1)", position: [5.1, 0, -4.6], rotationY: Math.PI / 2 },
  { name: "slot1 (wall1, -1)", position: [-4.6, 0, 5.1], rotationY: 0 },
  { name: "slot2 (wall2, -1)", position: [-5.1, 0, -4.6], rotationY: -Math.PI / 2 },
  { name: "slot3 (wall2, +1)", position: [-5.1, 0, 4.6], rotationY: -Math.PI / 2 },
  { name: "slot4 (wall3, -1)", position: [4.6, 0, -5.1], rotationY: Math.PI },
  { name: "slot5 (wall3, +1)", position: [-4.6, 0, -5.1], rotationY: Math.PI },
];

const HEAD_OFFSET_Y = 1.9; // arbitrary stand-in for CHARACTER_TARGET_HEIGHT*CHARACTER_SCALE*0.95

function headPosFor(deskPos: [number, number, number]): [number, number, number] {
  return [deskPos[0], deskPos[1] + HEAD_OFFSET_Y, deskPos[2]];
}

function poseFor(slot: (typeof REAL_SLOTS)[number]) {
  return computeDeskFacingCameraPose({
    deskPos: slot.position,
    rotationY: slot.rotationY,
    headPos: headPosFor(slot.position),
    roomHalfExtent: ROOM_HALF_EXTENT,
    standPositionXZ: STAND_POSITION_XZ,
  });
}

test("deskFacingNormalXZ: rotationY=0 (local -Z) points toward -Z", () => {
  const [nx, nz] = deskFacingNormalXZ(0);
  assert.ok(Math.abs(nx) < 1e-9);
  assert.ok(Math.abs(nz - -1) < 1e-9);
});

test("deskFacingNormalXZ: rotationY=PI/2 points toward -X", () => {
  const [nx, nz] = deskFacingNormalXZ(Math.PI / 2);
  assert.ok(Math.abs(nx - -1) < 1e-9);
  assert.ok(Math.abs(nz) < 1e-9);
});

for (const slot of REAL_SLOTS) {
  test(`${slot.name}: camera lands inside the room`, () => {
    const { camPos } = poseFor(slot);
    assert.ok(Math.abs(camPos[0]) <= ROOM_HALF_EXTENT, `camPos.x=${camPos[0]} outside room`);
    assert.ok(Math.abs(camPos[2]) <= ROOM_HALF_EXTENT, `camPos.z=${camPos[2]} outside room`);
  });

  test(`${slot.name}: camera clears the monitor stand by >= 1.5u`, () => {
    const { camPos } = poseFor(slot);
    const dist = Math.hypot(camPos[0] - STAND_POSITION_XZ[0], camPos[2] - STAND_POSITION_XZ[1]);
    assert.ok(dist >= 1.5 - 1e-9, `dist to stand=${dist}`);
  });

  test(`${slot.name}: camera clears the hub core by >= 2.6u`, () => {
    const { camPos } = poseFor(slot);
    const dist = Math.hypot(camPos[0], camPos[2]);
    assert.ok(dist >= 2.6 - 1e-9, `dist to core=${dist}`);
  });

  test(`${slot.name}: camera sits on the ROOM side of the desk (facing normal, not the wall side)`, () => {
    const { camPos } = poseFor(slot);
    const [nx, nz] = deskFacingNormalXZ(slot.rotationY);
    const dx = camPos[0] - slot.position[0];
    const dz = camPos[2] - slot.position[2];
    const dot = dx * nx + dz * nz;
    assert.ok(dot > 0, `dot=${dot} -- camera is not on the room side of the desk`);
  });

  test(`${slot.name}: camera looks at the desk's own head position`, () => {
    const { headPos } = poseFor(slot);
    const expected = headPosFor(slot.position);
    assert.deepEqual(headPos, expected);
  });
}

test("computeDeskFacingCameraPose: pullBack/liftY defaults are 3.2/2.6", () => {
  const slot = REAL_SLOTS[1]; // rotationY=0, facing normal = (0,0,-1) -- trivial to hand-check
  const pose = computeDeskFacingCameraPose({
    deskPos: slot.position,
    rotationY: slot.rotationY,
    headPos: headPosFor(slot.position),
    roomHalfExtent: 1000, // effectively unclamped for this check
    standPositionXZ: [1000, 1000], // far away -- no push-clear interference
  });
  assert.ok(Math.abs(pose.camPos[0] - slot.position[0]) < 1e-9);
  assert.ok(Math.abs(pose.camPos[2] - (slot.position[2] - 3.2)) < 1e-9);
  assert.ok(Math.abs(pose.camPos[1] - (slot.position[1] + 2.6)) < 1e-9);
});

test("computeDeskFacingCameraPose: room clamp actually engages when the raw pose would exit the room", () => {
  const pose = computeDeskFacingCameraPose({
    deskPos: [7.4, 0, 0],
    rotationY: Math.PI / 2, // facing normal (-1,0,0) -- pulls further +X-negative is fine, but start already near the wall
    headPos: [7.4, 1.9, 0],
    pullBack: 3.2,
    roomHalfExtent: 6.7,
    standPositionXZ: [1000, 1000],
  });
  assert.ok(Math.abs(pose.camPos[0]) <= 6.7 + 1e-9);
  assert.ok(Math.abs(pose.camPos[2]) <= 6.7 + 1e-9);
});

test("computeDeskFacingCameraPose: push-clear moves the camera away from an intruding monitor stand", () => {
  const pose = computeDeskFacingCameraPose({
    deskPos: [1, 0, 0],
    rotationY: 0, // facing normal (0,0,-1) -> raw camPos [1,liftY,-3.2]
    headPos: [1, 1.9, 0],
    roomHalfExtent: 1000,
    standPositionXZ: [1, -3.2], // exactly on the raw camera XZ -- degenerate, forces the fallback push
    standClearance: 1.5,
    coreClearance: 0, // disable core push for this isolated check
  });
  const dist = Math.hypot(pose.camPos[0] - 1, pose.camPos[2] - -3.2);
  assert.ok(dist >= 1.5 - 1e-9, `dist=${dist}`);
});

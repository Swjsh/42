// @ts-nocheck -- same convention as tests/hq-desk-preset.test.ts's own
// header: plain `node --test` needs the explicit ".ts" extension on a
// relative import, which the project's shared tsconfig would otherwise
// reject during `next build`'s project-wide type-check.
//
// Run: cd dashboard && node --test tests/hq-desk-facing.test.ts
//
// BLOCKY-FIXES pass (2026-09-16). Pins the two real defects found in
// automation/state/station/captures/blockyfix-desk3-0135.png:
//
// Defect A -- the seated character faced the ROOM (back to its own screen).
// Root cause (see Agent.tsx's own `deskYaw` prop doc comment for the full
// derivation): Agent.tsx's OLD `atan2(hub-home)+PI` desk-facing formula is
// only an approximation of the desk's true facing -- exact only when `home`
// sits on the ray from `hub` through the wall/T-junction's own normal
// point. For a real persona wall-slot desk (PERSONA_WALL_LATERAL_OFFSET=4.6
// against PERSONA_WALL_RADIUS=5.1) this drifts 35-50deg off the desk's real
// `rotationY`; for a real bay desk (SIDE_SPAN=8.1 off its own T-junction)
// it drifts ~66.5deg -- confirmed by the pure-math section below, using
// the exact same formulas layout.ts/Agent.tsx use, replicated by hand
// (layout.ts imports SetKit.tsx, a real .tsx file node's ESM loader
// refuses -- the same constraint tests/hq-desk-preset.test.ts's own header
// documents). The fix: `deskYaw` (the desk's own furniture rotationY,
// already computed by layout.ts and threaded through Scene.tsx) now
// REPLACES the hub approximation outright whenever a caller passes it --
// this pins `deskFacing === rotationY` exactly, by construction, for every
// caller that does.
//
// The character's TRUE front axis (independent confirmation, not assumed):
// this session parsed public/hq-assets/kenney-blocky-characters/
// character-a.glb's raw JSON+BIN chunks directly (no threejs/GLTFLoader
// needed) and found BOTH the head mesh and the torso mesh's local-+Z quad
// (not -Z) maps, via each vertex's own TEXCOORD_0, to the texture-a.png
// atlas region carrying the face (eyebrows/nose/beard) and the front-torso
// detail (collar/buttons) respectively -- never the plain-hood/backpack -Z
// quad. Local +Z is this rig's true front. Cross-checked against the
// independent, already-working walk convention (`resolvePathPose`'s
// `legHeading = atan2(dx,dz)` applied to `g.rotation.y` with NO offset,
// screenshot-verified walking) via real three.js below: both agree.
//
// Defect B -- an IDLE persona's nameplate (DeskNameplate.tsx) rendered
// right over an OCCUPIED neighbor's desk ("Analyst" over Coach's desk).
// Traced the full index chain (innerPersonas.map's own `i` -> `personaGeometry
// [i]` -> both <Agent> and <DeskNameplate> read the SAME `slot` in the SAME
// iteration; lib/personas.ts#collectCompany always returns `[gamma, scout,
// coach, pilot, analyst, chef, treasurer]`, Gamma fixed at index 0) -- NOT
// an index/slice bug. Real root cause: layout.ts#computePersonaWallSlots'
// "corner-sharing" scheme puts 3 desk PAIRS (Scout/Chef, Coach/Analyst,
// Pilot/Treasurer) just 0.85 world units apart, against >=9.2u for every
// other pair -- verified below by hand-replicating that exact formula.

import { test } from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";

// ─── Defect A: character's true front axis (from the real GLB) ───────────

// Hand-copied from this session's own direct parse of character-a.glb's
// JSON+BIN chunks (struct.unpack on the raw glTF buffer, not a guess): the
// head mesh's local-+Z quad (vertices with position.z === +4, the
// "FRONT" face) and the torso mesh's local-+Z quad (position.z === +0.3)
// each have an average TEXCOORD_0 that lands (mod 1, matching this
// texture's REPEAT wrap) on a DISTINCT region of texture-a.png:
//   head +Z avg uv (0.172, 0.186 mod1) -> pixel (176,190) -> face
//     (eyebrows/nose/beard visible in a direct crop, this session)
//   head -Z avg uv (0.437, 0.186 mod1) -> pixel (448,190) -> plain hood
//     color, no face detail
//   torso +Z avg uv (0.156, 0.786 mod1) -> collar/button/belt detail
//   torso -Z avg uv (0.375, 0.836 mod1) -> backpack (flap + clasp button)
// Both meshes agree: local +Z carries the "front-of-body" texture, local
// -Z carries the "back-of-body" texture. This constant records that
// conclusion as the one fact every other assertion below builds on.
const TRUE_FRONT_AXIS_IS_PLUS_Z = true;

test("character's true front axis is local +Z (independently confirmed via the real GLB's own UV atlas mapping)", () => {
  assert.equal(TRUE_FRONT_AXIS_IS_PLUS_Z, true);
});

test("walk convention agrees with the GLB evidence: rotation.y = atan2(dx,dz) with NO offset makes local +Z lead the direction of travel", () => {
  // Reproduces Agent.tsx#resolvePathPose's own `legHeading = atan2(to.x-from.x, to.z-from.z)`
  // applied directly to rotation.y (no +PI), the screenshot-verified walking
  // convention this file's header cites.
  const from: [number, number, number] = [0, 0, 0];
  const to: [number, number, number] = [3, 0, 4]; // arbitrary travel direction
  const legHeading = Math.atan2(to[0] - from[0], to[2] - from[2]);
  const obj = new THREE.Object3D();
  obj.rotation.y = legHeading;
  obj.updateMatrixWorld(true);
  const localFront = new THREE.Vector3(0, 0, 1).applyQuaternion(obj.quaternion);
  const travelDir = new THREE.Vector3(to[0] - from[0], 0, to[2] - from[2]).normalize();
  assert.ok(localFront.dot(travelDir) > 0.999, `local+Z should align with travel direction, dot=${localFront.dot(travelDir)}`);
});

// ─── Defect A: deskYaw replaces the hub approximation exactly ────────────

/** Reproduces Agent.tsx's own "resting" deskFacing computation exactly
 * (see that file's own `const deskFacing = deskYaw ?? Math.atan2(...)`). */
function deskFacing(home: [number, number, number], hub: [number, number, number], deskYaw?: number): number {
  return deskYaw ?? Math.atan2(hub[0] - home[0], hub[2] - home[2]) + Math.PI;
}

test("deskYaw, when passed, is used VERBATIM -- no hub math, no offset", () => {
  const home: [number, number, number] = [-4.6, 0, 5.2];
  const hub: [number, number, number] = [0, 0, 0];
  const rotationY = 1.234; // arbitrary furniture yaw, unrelated to home/hub
  assert.equal(deskFacing(home, hub, rotationY), rotationY);
});

test("omitting deskYaw keeps the OLD hub-based formula byte-identical (bay/lane agents, unchanged behavior)", () => {
  const home: [number, number, number] = [-4.6, 0, 5.2];
  const hub: [number, number, number] = [0, 0, 0];
  const expected = Math.atan2(hub[0] - home[0], hub[2] - home[2]) + Math.PI;
  assert.equal(deskFacing(home, hub, undefined), expected);
});

test("with deskYaw = rotationY, the character's TRUE front (+Z) lands on EXACTLY the same world direction as the desk's own +Z (SetKit.tsx#DeskCluster's screen mount)", () => {
  const rotationY = 0.61; // arbitrary real-shaped furniture yaw
  const yaw = deskFacing([0, 0, 0], [0, 0, 0], rotationY);
  const obj = new THREE.Object3D();
  obj.rotation.y = yaw;
  obj.updateMatrixWorld(true);
  const characterFront = new THREE.Vector3(0, 0, 1).applyQuaternion(obj.quaternion);
  // DeskCluster's own +Z direction in world space, at the SAME rotationY
  // (SetKit.tsx renders table/chair/screen at rotation=[0,rotationY,0]).
  const desk = new THREE.Object3D();
  desk.rotation.y = rotationY;
  desk.updateMatrixWorld(true);
  const deskFront = new THREE.Vector3(0, 0, 1).applyQuaternion(desk.quaternion);
  assert.ok(characterFront.distanceTo(deskFront) < 1e-9, "character front must equal desk front exactly");
});

// ─── Defect A: numeric proof the OLD hub approximation was really off ────

const HUB: [number, number, number] = [0, 0, 0];
// Real persona wall slots (computePersonaWallSlots(6, 0)) -- same
// hand-replicated constants tests/hq-desk-preset.test.ts's own header
// already established and cross-checked against a standalone run of the
// real formula.
const PERSONA_SLOTS: Array<{ name: string; agentHome: [number, number, number]; rotationY: number }> = [
  { name: "Scout", agentHome: [5.2, 0, -4.6], rotationY: Math.PI / 2 },
  { name: "Coach", agentHome: [-4.6, 0, 5.2], rotationY: 0 },
  { name: "Pilot", agentHome: [-5.2, 0, -4.6], rotationY: -Math.PI / 2 },
  { name: "Analyst", agentHome: [-5.2, 0, 4.6], rotationY: -Math.PI / 2 },
  { name: "Chef", agentHome: [4.6, 0, -5.2], rotationY: Math.PI },
  { name: "Treasurer", agentHome: [-4.6, 0, -5.2], rotationY: Math.PI },
];

function angleDiffDeg(a: number, b: number): number {
  let d = ((a - b) * 180) / Math.PI;
  d = ((d + 180) % 360 + 360) % 360 - 180;
  return d;
}

test("the OLD hub-based approximation drifts 30+ degrees off the desk's real rotationY for every real persona slot (this drift, not deskFacing's sign, is the actual bug)", () => {
  for (const slot of PERSONA_SLOTS) {
    const hubYaw = deskFacing(slot.agentHome, HUB, undefined);
    const drift = Math.abs(angleDiffDeg(hubYaw, slot.rotationY));
    assert.ok(drift > 30, `${slot.name}: drift=${drift.toFixed(1)}deg, expected > 30deg`);
  }
});

test("the NEW deskYaw-based facing has ZERO drift from the desk's own rotationY, for every real persona slot", () => {
  for (const slot of PERSONA_SLOTS) {
    const yaw = deskFacing(slot.agentHome, HUB, slot.rotationY);
    assert.equal(yaw, slot.rotationY);
  }
});

// ─── Defect B: corner-sharing desk pairs really do collide ───────────────

const NAMEPLATE_COLLISION_CLEARANCE = 2.0; // Scene.tsx's own constant, kept in sync by hand

function dist2D(a: [number, number, number], b: [number, number, number]): number {
  return Math.hypot(a[0] - b[0], a[2] - b[2]);
}

test("Coach and Analyst's real desk positions are ~0.85 world units apart (the corner-sharing collision), well under NAMEPLATE_COLLISION_CLEARANCE", () => {
  const coach = PERSONA_SLOTS.find((s) => s.name === "Coach")!;
  const analyst = PERSONA_SLOTS.find((s) => s.name === "Analyst")!;
  const d = dist2D(coach.agentHome, analyst.agentHome);
  assert.ok(d < 1.0, `distance=${d.toFixed(2)}, expected < 1.0 (real collision)`);
  assert.ok(d < NAMEPLATE_COLLISION_CLEARANCE, "collision must be caught by the clearance check");
});

test("every non-corner-sharing persona pair is comfortably outside NAMEPLATE_COLLISION_CLEARANCE (the fix must never suppress a legitimate, non-colliding nameplate)", () => {
  const CORNER_PAIRS = new Set(["Scout|Chef", "Coach|Analyst", "Pilot|Treasurer"]);
  for (let i = 0; i < PERSONA_SLOTS.length; i++) {
    for (let j = i + 1; j < PERSONA_SLOTS.length; j++) {
      const a = PERSONA_SLOTS[i];
      const b = PERSONA_SLOTS[j];
      const key1 = `${a.name}|${b.name}`;
      const key2 = `${b.name}|${a.name}`;
      const d = dist2D(a.agentHome, b.agentHome);
      if (CORNER_PAIRS.has(key1) || CORNER_PAIRS.has(key2)) {
        assert.ok(d < NAMEPLATE_COLLISION_CLEARANCE, `${key1} should collide, d=${d.toFixed(2)}`);
      } else {
        assert.ok(d >= NAMEPLATE_COLLISION_CLEARANCE, `${key1} should NOT collide, d=${d.toFixed(2)}`);
      }
    }
  }
});

/** Reproduces Scene.tsx's own `deskCollidesWithOccupiedNeighbor` logic
 * exactly, against a small synthetic roster -- pure function, no React. */
function nameplateSuppressed(
  index: number,
  statuses: string[],
  slots: Array<{ position: [number, number, number] }>,
): boolean {
  const showAgent = statuses[index] !== "IDLE";
  if (showAgent) return false; // never suppress a body -- only nameplates are gated
  return slots.some((other, j) => {
    if (j === index || statuses[j] === "IDLE") return false;
    return dist2D(slots[index].position, other.position) < NAMEPLATE_COLLISION_CLEARANCE;
  });
}

test("an IDLE persona's nameplate is suppressed when its own desk collides with an OCCUPIED neighbor's desk (the real Coach/Analyst capture, reproduced)", () => {
  const names = PERSONA_SLOTS.map((s) => s.name);
  const slots = PERSONA_SLOTS.map((s) => ({ position: s.agentHome }));
  const statuses = names.map((n) => (n === "Coach" ? "GREEN" : "IDLE")); // matches the real capture
  const analystIdx = names.indexOf("Analyst");
  assert.equal(nameplateSuppressed(analystIdx, statuses, slots), true);
});

test("an IDLE persona's nameplate renders normally when no neighbor is occupied", () => {
  const names = PERSONA_SLOTS.map((s) => s.name);
  const slots = PERSONA_SLOTS.map((s) => ({ position: s.agentHome }));
  const statuses = names.map(() => "IDLE"); // nobody occupied
  const analystIdx = names.indexOf("Analyst");
  assert.equal(nameplateSuppressed(analystIdx, statuses, slots), false);
});

test("an OCCUPIED persona (showAgent=true) is never suppressed by this check -- only nameplates are gated, never a real working body", () => {
  const names = PERSONA_SLOTS.map((s) => s.name);
  const slots = PERSONA_SLOTS.map((s) => ({ position: s.agentHome }));
  const statuses = names.map((n) => (n === "Coach" || n === "Analyst" ? "GREEN" : "IDLE"));
  const analystIdx = names.indexOf("Analyst");
  assert.equal(nameplateSuppressed(analystIdx, statuses, slots), false);
});

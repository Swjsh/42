// DESK-PRESETS pass (2026-09-15): pure math for the per-persona-desk camera
// preset (keyboard/URL "2".."7"), re-derived after commit 31cc19b5 moved the
// six persona desks from the old ring (PERSONA_RING_RADIUS, one shared
// radial-from-hub direction) to layout.ts#computePersonaWallSlots (desks
// backed against the hub walls flanking each door, PERSONA_WALL_RADIUS=5.1 /
// PERSONA_WALL_LATERAL_OFFSET=4.6).
//
// Root cause of the bug this fixes (Scene.tsx#cameraPresets, pre-existing
// `dirX`/`dirZ` derived from `pos - HUB` and used as the desk's "outward"
// direction): that math was only ever valid for the OLD ring, where a
// desk's position vector FROM THE HUB ORIGIN and the desk's own facing
// normal were the same direction by construction (every desk sat on a ray
// through the origin). A wall-slot desk sits at `wallNormalPoint +-
// lateralOffset*tangent` -- offset TANGENTIALLY from that ray -- so
// `pos - HUB` no longer points along the desk's own facing axis at all;
// for the two desks sharing a wall it points into a corner or through a
// door assembly instead (exactly the "framed a door assembly rather than a
// persona desk" symptom the DESKS-AGAINST-WALLS worker's note describes).
//
// Fix: derive the camera pose from the desk's OWN facing normal
// (`rotationY`, already computed by computePersonaWallSlots and carried
// through Scene.tsx#personaGeometry), not from the hub-to-desk radial.
// `rotationY` is the same "local -Z faces this direction" convention every
// kit placement in this tree uses (see layout.ts#rotationYFacing's own
// header) -- local -Z is the direction pointing OFF the wall into the room
// (toward the hub), which is exactly the side a camera needs to stand on to
// see the desk's screen/chair/character (all mounted facing the room, per
// SetKit.tsx#DeskCluster) rather than their backs.
//
// Pure module (no React/three/DOM) so it can be unit-tested with plain
// `node --test`, the same convention lib/hq-camera-params.ts and
// components/hq/labelDeclutter.ts already established. layout.ts itself
// can't be imported under `node --test` (pulls in SetKit.tsx, a real .tsx
// component file) -- callers pass in whatever layout.ts constants this
// module needs (HUB_WALL_RADIUS, MONITOR_MOUNT.standPosition) rather than
// this module importing them itself, so it stays load-bearing-import-free.

export type Vec3 = [number, number, number];
export type Vec2 = [number, number];

export interface DeskFacingCameraPoseParams {
  /** Desk's own floor-level world position (layout.ts#PersonaWallSlot.position
   * / Scene.tsx#personaGeometry[i].position). */
  deskPos: Vec3;
  /** Desk's own facing yaw (layout.ts#PersonaWallSlot.rotationY) -- local -Z
   * points off the wall into the room, toward the hub. */
  rotationY: number;
  /** OrbitControls look-at target for this preset -- the character's own
   * head world position (Scene.tsx#cameraPresets already computes this the
   * same way for every preset; passed straight through, untouched). */
  headPos: Vec3;
  /** How far back (world units) the camera stands from the desk along the
   * desk's own facing normal, before any clamp. Default 3.2 -- close enough
   * to read the desk screen's face-on side, far enough to clear the desk's
   * own footprint and the seated character in front of it. */
  pullBack?: number;
  /** How far above the desk's own floor level (world units) the camera
   * sits. Default 2.6 -- eye-level-ish over a seated character, well under
   * BRAIN_WALL/monitor-stand geometry height. */
  liftY?: number;
  /** Room-interior clamp: the camera's |x| and |z| are each clamped to this
   * value so a desk hard against the outer wall can never place the camera
   * ON or beyond that wall. Caller passes `HUB_WALL_RADIUS - 0.8`. */
  roomHalfExtent: number;
  /** World XZ of the twin-monitor stand (layout.ts#MONITOR_MOUNT.standPosition)
   * -- the camera is pushed radially away from this point if it would
   * otherwise land closer than `standClearance`. */
  standPositionXZ: Vec2;
  /** Minimum camera distance from `standPositionXZ`. Default 1.5. */
  standClearance?: number;
  /** Minimuim camera distance from the hub's own center/core (world origin,
   * BrainCore's own ring geometry). Default 2.6. */
  coreClearance?: number;
}

export interface DeskFacingCameraPose {
  camPos: Vec3;
  headPos: Vec3;
}

const DEFAULT_PULL_BACK = 3.2;
const DEFAULT_LIFT_Y = 2.6;
const DEFAULT_STAND_CLEARANCE = 1.5;
const DEFAULT_CORE_CLEARANCE = 2.6;

/** The desk's own facing normal in the XZ plane -- local -Z of an object at
 * `rotation.y = rotationY` (three.js Y-rotation convention: local +Z maps to
 * world `(sin(theta), cos(theta))`, so local -Z maps to
 * `(-sin(theta), -cos(theta))`). Points off the wall into the room. */
export function deskFacingNormalXZ(rotationY: number): Vec2 {
  return [-Math.sin(rotationY), -Math.cos(rotationY)];
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

/** Pushes `point` radially away from `center` until it is at least `minDist`
 * away, leaving it untouched if it already clears that distance. Degenerate
 * case (point exactly on center) pushes along +X arbitrarily rather than
 * dividing by zero -- never hit by any real desk slot (every desk sits well
 * outside both the stand and the core), but kept total so the function has
 * no unhandled input. */
function pushClearOf(point: Vec2, center: Vec2, minDist: number): Vec2 {
  const dx = point[0] - center[0];
  const dz = point[1] - center[1];
  const dist = Math.hypot(dx, dz);
  if (dist >= minDist) return point;
  if (dist < 1e-9) return [center[0] + minDist, center[1]];
  const scale = minDist / dist;
  return [center[0] + dx * scale, center[1] + dz * scale];
}

/**
 * Computes a persona desk's camera preset pose: the camera stands on the
 * ROOM side of the desk (along the desk's own facing normal, away from the
 * wall it's backed against), pulled back and lifted, then clamped to stay
 * inside the room and clear of the hub's core/monitor-stand furniture.
 * `headPos` passes through unchanged (it is the OrbitControls look-at
 * target, computed identically to every other preset by the caller).
 */
export function computeDeskFacingCameraPose(p: DeskFacingCameraPoseParams): DeskFacingCameraPose {
  const pullBack = p.pullBack ?? DEFAULT_PULL_BACK;
  const liftY = p.liftY ?? DEFAULT_LIFT_Y;
  const standClearance = p.standClearance ?? DEFAULT_STAND_CLEARANCE;
  const coreClearance = p.coreClearance ?? DEFAULT_CORE_CLEARANCE;

  const [nx, nz] = deskFacingNormalXZ(p.rotationY);
  let camX = p.deskPos[0] + nx * pullBack;
  let camZ = p.deskPos[2] + nz * pullBack;
  const camY = p.deskPos[1] + liftY;

  camX = clamp(camX, -p.roomHalfExtent, p.roomHalfExtent);
  camZ = clamp(camZ, -p.roomHalfExtent, p.roomHalfExtent);

  [camX, camZ] = pushClearOf([camX, camZ], p.standPositionXZ, standClearance);
  [camX, camZ] = pushClearOf([camX, camZ], [0, 0], coreClearance);

  // Re-clamp: pushing clear of the stand/core could in principle move a
  // point back toward/past the outer wall (not exercised by any real desk
  // slot today, but the room clamp is the one invariant that must never be
  // violated regardless of what pushed the point where).
  camX = clamp(camX, -p.roomHalfExtent, p.roomHalfExtent);
  camZ = clamp(camZ, -p.roomHalfExtent, p.roomHalfExtent);

  return { camPos: [camX, camY, camZ], headPos: p.headPos };
}

"use client";

// ─── Campus-cross layout (2026-09-14, LAYOUT builder pass) ─────────────────
// J review (16:50 ET, screenshot of a bay doorway): "the doors that connect
// the main area to each little hub are not doorways or hallways or
// anything, there's a jumbled mess... the main thing only has four exits,
// so you have stuff connecting to the corner where there's no wall for it
// to connect to... You need to space this out more... it needs to look
// real. Right now it's just a bunch of shit on a circle."
//
// Root cause: the old layout (Scene.tsx's own RING_RADIUS, now removed)
// spread 8 bays around a full circle at 8 angles (45deg apart), each
// connected to the hub by a corridor running along THAT bay's own angle
// (SetKit.tsx#CorridorRun). But HubRoom (room-large.glb) only has 4 real
// doorways, one per flat wall, centered on +-X and +-Z (world axes, no
// rotation applied to the hub shell -- verified from SetKit.tsx#HubRoom's
// own call site). 4 of the 8 corridors (the ones at 45/135/225/315deg) hit
// either a bare wall face at a steep angle or the room's corner, where
// there is no opening at all -- exactly the "jumbled mess" / "no wall for
// it to connect to" / "unused corner" J is describing.
//
// Fix: an orthogonal cross. One straight main hallway per real doorway
// (+X/-X/+Z/-Z), each ending at a T-intersection, from which two side
// hallways run left/right to a bay door apiece -- 4 spines x 2 bays = 8
// bays = the 8 real lanes, every corridor meeting a real opening, zero
// unused corners.
//
// All the raw kit dimensions below were parsed directly from each GLB's own
// binary this session (read the JSON chunk, walk every mesh primitive's
// POSITION accessor min/max -- the same technique HQ-SCENE-PLAN.md's own
// verification pass used elsewhere in this file tree), not guessed or
// carried over from a comment:
//   corridor.glb            4 x 4.25 x 4   (raw XZ footprint 4x4)
//   corridor-corner.glb     4 x 4.25 x 4
//   corridor-intersection   4 x 4.05 x 4   (T_JUNCTION_HALF below)
//   corridor-wide.glb       8 x 4.25 x 8   (2x corridor.glb, CorridorRun's
//                                           own `wide` option)
//   room-small.glb          12 x 4.25 x 12 (BAY_HALF_DEPTH, SetKit.tsx)
//   room-large.glb          20 x 4.25 x 20 (HUB_WALL_RADIUS, SetKit.tsx)
//   gate-door.glb           4.2 x 4.62 x 1.4
//
// This module is pure geometry/math -- no React, no Three.js scene graph,
// no fs/network -- so SetKit.tsx (kit rendering) and Scene.tsx (the scene
// tree) can both import it with zero risk of a cycle. It imports FROM
// SetKit.tsx (the raw-kit-derived constants: HUB_WALL_RADIUS,
// BAY_HALF_DEPTH, ARCHITECTURE_SCALE_BAY), never the other way around --
// SetKit.tsx's own Plaza/TJunction/CorridorRun receive their sizes as
// props from Scene.tsx (which imports both modules freely), the same
// "receives computed dimensions as props" convention Plaza already used
// before this pass.

import { ARCHITECTURE_SCALE_BAY, BAY_HALF_DEPTH, HUB_WALL_RADIUS } from "./SetKit";
import type { WalkPlan } from "./types";

export const HUB: [number, number, number] = [0, 0, 0];

/** Raw corridor-intersection.glb / corridor.glb footprint is 4x4 (see this
 * module's own header) -- half-extent at ARCHITECTURE_SCALE_BAY, the
 * distance a spine/side-hallway must clear before it reaches a T-junction's
 * own real geometry. */
export const T_JUNCTION_HALF = (4 * ARCHITECTURE_SCALE_BAY) / 2;

/** Hub wall -> T-junction edge, drawn hallway length. "8-10u" per the
 * layout brief. */
export const MAIN_HALL_LEN = 9;
/** T-junction edge -> bay wall, drawn hallway length. "4-5u" per the
 * layout brief. */
export const SIDE_HALL_LEN = 4.5;
/** Plaza's own outer margin beyond the last real wall, both the central
 * hub circle and the 4 arm rectangles (Scene.tsx threads this into
 * SetKit.tsx#Plaza's props, which stay apron-agnostic -- see that
 * component's own comment). */
export const PLAZA_APRON = 1.5;

/** Hub center -> T-junction center, along the arm's own main (cardinal)
 * axis. */
export const T_DIST = HUB_WALL_RADIUS + MAIN_HALL_LEN + T_JUNCTION_HALF;
/** T-junction center -> bay center, along the arm's own perpendicular
 * (side-hallway) axis. */
export const SIDE_SPAN = T_JUNCTION_HALF + SIDE_HALL_LEN + BAY_HALF_DEPTH;
/** Half-length of one arm's real footprint along its own main axis (hub
 * center to the far wall of its T-junction's bays) -- Plaza's arm
 * rectangles and the outdoor-prop clearance rule are both sized from this. */
export const ARM_LEN = T_DIST + BAY_HALF_DEPTH;
/** Half-width of one arm's real footprint perpendicular to its main axis
 * (far wall of one bay, through the T-junction, to the far wall of the
 * other). */
export const ARM_HALF_WIDTH = SIDE_SPAN + BAY_HALF_DEPTH;
/** Plaza's own central circle -- hub footprint + apron only (the 4 arm
 * rectangles, sized from ARM_LEN/ARM_HALF_WIDTH above, cover the rest of
 * the union footprint -- see SetKit.tsx#Plaza). */
export const PLAZA_CENTER_RADIUS = HUB_WALL_RADIUS + PLAZA_APRON;

/** The 4 cardinal directions a hub doorway/spine can face, in the SAME
 * cos/sin(angle) convention every kit placement in this tree already uses
 * (angle 0 = +X, pi/2 = +Z, ...). armIndex 0..3 only. */
export function armAngle(armIndex: number): number {
  return (armIndex * Math.PI) / 2;
}

/** Yaw (three.js Object3D.rotation.y) that points a kit piece's own local
 * -Z axis (this kit's universal "front" -- room-large/room-small/gate-door/
 * corridor all share it, see SetKit.tsx's own placement comments) from
 * `selfXZ` toward `targetXZ`. Generalizes the old ring layout's `Math.PI/2
 * - angle` trick (only ever valid for a point on a ray through the world
 * origin) to ANY two points. Algebraic check performed this session before
 * relying on it: for selfXZ on a ray from the origin at `angle` and
 * targetXZ = the origin, this reduces EXACTLY to `Math.PI/2 - angle` (the
 * old formula) -- so every placement that used to face the hub correctly
 * still does, and this also now covers the new off-origin side hallways
 * and bays the old formula could never express. */
export function rotationYFacing(
  selfXZ: readonly [number, number, number],
  targetXZ: readonly [number, number, number],
): number {
  return Math.atan2(selfXZ[0] - targetXZ[0], selfXZ[2] - targetXZ[2]);
}

export interface ArmLayout {
  armIndex: number;
  mainAngle: number;
  /** World point where the main spine meets the hub's own wall -- also
   * where CorridorRun mounts its hub-end gate-door frame. */
  hubDoorPos: [number, number, number];
  /** T-junction center, world space. */
  tCenter: [number, number, number];
  /** Main spine's far (T-junction) end -- the T-junction's own near edge,
   * i.e. where the drawn hallway floor actually stops (the junction's own
   * kit geometry covers the rest). */
  tNearEdge: [number, number, number];
  /** Shared facing for the main spine's kit segments + the T-junction
   * piece itself -- local -Z points back toward the hub. */
  rotationY: number;
}

export function computeArmLayout(armIndex: number): ArmLayout {
  const mainAngle = armAngle(armIndex);
  const dirX = Math.cos(mainAngle);
  const dirZ = Math.sin(mainAngle);
  const hubDoorPos: [number, number, number] = [dirX * HUB_WALL_RADIUS, 0, dirZ * HUB_WALL_RADIUS];
  const tCenter: [number, number, number] = [dirX * T_DIST, 0, dirZ * T_DIST];
  const tNearEdge: [number, number, number] = [
    dirX * (T_DIST - T_JUNCTION_HALF), 0, dirZ * (T_DIST - T_JUNCTION_HALF),
  ];
  return { armIndex, mainAngle, hubDoorPos, tCenter, tNearEdge, rotationY: rotationYFacing(tCenter, HUB) };
}

// GATE-PROP pass (2026-09-15): the campus-gate walk node above has no set
// dressing -- a real-screen capture shows live agents spawning/despawning
// out of empty dark plaza floor at [21.6,0,0], "spawn at the gate" isn't
// legible to a viewer without an actual gate prop there. These constants
// are the single source both the graph node above AND SetKit.tsx's new
// `CampusGate` component read from -- never a re-typed literal in either
// place, same "one number, every consumer derives from it" discipline this
// whole file already follows (ARM_LEN/PLAZA_APRON themselves).
//
// Reuses gate-door.glb (kenney-modular-space-kit) -- the SAME asymmetric
// "4.2 wide (local X) x 4.62 tall x 1.4 deep (local Z), -Z-front" piece
// DepartmentBayShell already mounts at every bay's hub-facing wall (see
// SetKit.tsx's own header table + DepartmentBayShell's comment) -- no new
// asset, no new npm package, exactly the task's own "reuse the existing
// kit's door/arch piece at matching scale" instruction.
//
// Position: arm 0's own T-junction center (`computeArmLayout(0).tCenter`,
// NOT a re-typed [T_DIST,0,0]) offset outward by ARM_LEN+PLAZA_APRON along
// that SAME arm's own direction vector -- algebraically identical to the
// campus-gate WalkNode's old inline literal (arm 0 is the +X cardinal, so
// dirX=1/dirZ=0 collapses this to [ARM_LEN+PLAZA_APRON,0,0]), but derived
// from computeArmLayout like every other node in this graph rather than
// hand-typed.
const CAMPUS_GATE_ARM = computeArmLayout(0);

/** gate-door.glb's raw (unscaled) footprint, X=4.2 (frame width, the axis
 * that becomes the walk-through CLEAR opening once rotated per
 * CAMPUS_GATE_ROTATION_Y below) x Z=1.4 (frame depth) -- measured directly
 * from the GLB's own JSON chunk this session (`node scripts/glb_extents.mjs
 * public/hq-assets/kenney-modular-space-kit/gate-door.glb`): root AABB
 * X=[-2.1,2.1]. Matches this file's own already-documented "gate-door.glb
 * 4.2 x 4.62 x 1.4" header comment. */
const GATE_RAW_WIDTH = 4.2;

/** Scale for the campus gate's gate-door mount -- deliberately LARGER than
 * DepartmentBayShell's own ARCHITECTURE_SCALE_BAY (0.45, sized for a single
 * bay doorway): the campus gate is the whole campus's one real entrance, a
 * grander opening is architecturally appropriate, AND the task's own
 * requirement ("Leave >= 1.2 u clear width either side of z=0 so a lateral
 * lane offset ... doesn't clip") needs it. ASSUMPTION (stated, not directly
 * measured -- this session's glb_extents.mjs run reports gate-door.glb's
 * OUTER frame AABB, not the actual open-air gap net of the frame's own
 * solid posts/lintel, and the kit ships no separate "opening-only" mesh to
 * measure that against): the walkable clear gap scales with the piece's
 * own full outer width, so guaranteeing the OUTER half-width alone clears
 * 1.2u is the conservative, provably-sufficient bound (the true opening is
 * <= the outer footprint, never larger) -- CAMPUS_GATE_SCALE is picked so
 * outer half-width (GATE_RAW_WIDTH/2 * scale) is not just >=1.2 but has
 * real headroom above it (1.2/2.1 = 0.571 is the bare minimum; 0.7 clears
 * it by 22.5%), so even a generously-thick real post/lintel still leaves
 * the required clear gap. */
export const CAMPUS_GATE_SCALE = 0.7;

// GATE-PROP pass (2026-09-15): the campus-gate walk node above has no set
// dressing -- a real-screen capture shows live agents spawning/despawning
// out of empty dark plaza floor at [21.6,0,0], "spawn at the gate" isn't
// legible to a viewer without an actual gate prop there. The actual math
// lives in liveAgentWalk.ts#computeCampusGateGeometry (import-free of
// SetKit.tsx, so it's unit-testable under plain `node --test` -- see that
// function's own header for why THIS file can't be) -- called here ONCE
// with this module's own already-computed values (ARM_LEN/PLAZA_APRON/
// computeArmLayout(0)), so there is exactly one computation, never a
// second copy that could drift from the campus-gate WalkNode above.
// `distanceFromHub: ARM_LEN + PLAZA_APRON` is the SAME distance-from-hub
// the addNode("campus-gate", ...) call above already uses (arm 0 is the
// +X cardinal, so this collapses to exactly [21.6,0,0] at today's raw-kit
// dimensions -- matches this header's own stated position). Reuses
// gate-door.glb (kenney-modular-space-kit) -- the SAME asymmetric piece
// DepartmentBayShell already mounts at every bay's hub-facing wall (see
// SetKit.tsx's own header table + DepartmentBayShell's comment) -- no new
// asset, no new npm package, exactly the task's own "reuse the existing
// kit's door/arch piece at matching scale" instruction.
const CAMPUS_GATE_GEOMETRY = computeCampusGateGeometry({
  armMainAngle: CAMPUS_GATE_ARM.mainAngle,
  facingTarget: CAMPUS_GATE_ARM.tCenter,
  distanceFromHub: ARM_LEN + PLAZA_APRON,
  scale: CAMPUS_GATE_SCALE,
  gateRawWidth: GATE_RAW_WIDTH,
});
export const CAMPUS_GATE_POSITION: [number, number, number] = CAMPUS_GATE_GEOMETRY.position;
/** Yaw that puts the gate-door's own local Z axis (its walk-through axis --
 * see DepartmentBayShell's own comment: local -Z is this kit's "front",
 * agents pass through a mounted gate-door along local Z, its local X is the
 * frame's WIDTH/clear-opening axis) along the campus-gate<->t-0 walk edge
 * (world +X at z=0, today's raw dims) instead of the default local-Z==
 * world-Z bay-door orientation -- computed via the same atan2(self-target)
 * formula this file's own rotationYFacing uses, even though it
 * algebraically reduces to exactly Math.PI/2 for arm 0's own +X-axis
 * geometry. */
export const CAMPUS_GATE_ROTATION_Y = CAMPUS_GATE_GEOMETRY.rotationY;
/** Derived from CAMPUS_GATE_SCALE above (never a re-typed literal) -- the
 * guaranteed-safe lower bound on the campus gate's own clear walkable half-
 * width, in world units either side of z=0 along the rotated gate's own
 * clear-opening axis. The gate-prop test (tests/campus-gate.test.ts)
 * asserts computeCampusGateGeometry itself returns >= 1.2 for these same
 * inputs, so this and the test can never silently drift apart. */
export const CAMPUS_GATE_CLEAR_HALF_WIDTH = CAMPUS_GATE_GEOMETRY.clearHalfWidth;

export interface BaySlot {
  /** 0..7, matches `data.sectors.rows[index]` 1:1 -- 4 arms x 2 sides. */
  index: number;
  armIndex: number;
  sideIndex: 0 | 1;
  /** Bay's own center, world space. */
  position: [number, number, number];
  /** Local -Z faces back down the side hallway toward the T-junction. */
  rotationY: number;
  /** StationModule.tsx (not owned by this pass) derives its own
   * `rotationY = Math.PI/2 - angle` internally and is NOT being touched --
   * back-solved here so Scene.tsx can keep calling that exact unchanged
   * contract with an arbitrary world rotation, not just one on a ray
   * through the origin. */
  stationAngle: number;
  tCenter: [number, number, number];
  /** Bay's own doorway threshold, world space (matches
   * SetKit.tsx#DepartmentBayShell's local (0,0,-halfDepth) gate-door,
   * transformed into world space). */
  doorWorldPos: [number, number, number];
  /** Side-hallway draw span: T-junction's own edge -> this bay's wall. */
  hallFrom: [number, number, number];
  hallTo: [number, number, number];
}

export function computeBaySlot(index: number): BaySlot {
  const armIndex = Math.floor(index / 2);
  const sideIndex = (index % 2) as 0 | 1;
  const arm = computeArmLayout(armIndex);
  const perpAngle = arm.mainAngle + (sideIndex === 0 ? 1 : -1) * (Math.PI / 2);
  const pDirX = Math.cos(perpAngle);
  const pDirZ = Math.sin(perpAngle);
  const position: [number, number, number] = [
    arm.tCenter[0] + pDirX * SIDE_SPAN, 0, arm.tCenter[2] + pDirZ * SIDE_SPAN,
  ];
  const doorWorldPos: [number, number, number] = [
    position[0] - pDirX * BAY_HALF_DEPTH, 0, position[2] - pDirZ * BAY_HALF_DEPTH,
  ];
  const hallFrom: [number, number, number] = [
    arm.tCenter[0] + pDirX * T_JUNCTION_HALF, 0, arm.tCenter[2] + pDirZ * T_JUNCTION_HALF,
  ];
  return {
    index, armIndex, sideIndex, position,
    rotationY: rotationYFacing(position, arm.tCenter),
    stationAngle: Math.PI / 2 - rotationYFacing(position, arm.tCenter),
    tCenter: arm.tCenter,
    doorWorldPos,
    hallFrom,
    hallTo: doorWorldPos,
  };
}

/** All bay slots for the current lane roster, index-aligned with
 * `data.sectors.rows` -- capped at 8 (4 arms x 2 sides, the physical
 * building this layout describes; the roster is a stable 8-lane set, see
 * this module's own header). A count below 8 simply omits the tail slots
 * (an arm with only one real bay still gets its own T-junction + one side
 * hallway -- see Scene.tsx's own render loop). */
export function computeAllBaySlots(count: number): BaySlot[] {
  return Array.from({ length: Math.max(0, Math.min(count, 8)) }, (_, i) => computeBaySlot(i));
}

/** Exact polar boundary of the cross footprint (central circle, radius
 * PLAZA_CENTER_RADIUS, union 4 arm rectangles ARM_LEN long x
 * 2*ARM_HALF_WIDTH wide) at a given azimuth. A flat "r >= N" clearance rule
 * (the old ring layout's own PLAZA_RADIUS-based rule) is WRONG for this
 * cross shape -- a diagonal gap between two arms needs far less clearance
 * than an arm's own tip does, and a naive single radius either clips a bay
 * corner or pushes every diagonal-gap prop needlessly far out. Point-in-
 * rectangle math: rotate the query azimuth into arm k's own local frame
 * (0 = along the arm's own outward axis); the arm's rectangle spans local-x
 * in [0, ARM_LEN] and local-z in [-ARM_HALF_WIDTH, ARM_HALF_WIDTH], so a
 * ray from the origin exits it at whichever bound it reaches first. */
export function crossFootprintRadiusAt(azimuth: number): number {
  let best = PLAZA_CENTER_RADIUS;
  for (let armIndex = 0; armIndex < 4; armIndex++) {
    const local = azimuth - armAngle(armIndex);
    const c = Math.cos(local);
    if (c <= 0) continue; // this arm's rectangle only spans local-x >= 0 (it starts at the hub center)
    const s = Math.sin(local);
    const t = s === 0 ? ARM_LEN : Math.min(ARM_LEN / c, ARM_HALF_WIDTH / Math.abs(s));
    if (t > best) best = t;
  }
  return best;
}

/** The minimum radius an outdoor prop at this azimuth can sit at without
 * landing inside a wall -- the footprint boundary plus the plaza's own
 * apron plus a caller-chosen safety margin. */
export function minClearRadius(azimuth: number, margin: number): number {
  return crossFootprintRadiusAt(azimuth) + PLAZA_APRON + margin;
}

// ─── Persona wall segments ───────────────────────────────────────────────
// Task: "Persona desks stay in the hub along the 4 wall segments between
// doors (2-2-2-1 with Gamma at the brain wall)." The hub's 4 doorways sit
// at armAngle(0..3); the 4 WALL segments are the quarter-arcs BETWEEN them,
// centered at armAngle(k)+45deg. Gamma's own desk is handled separately by
// Scene.tsx (gammaDeskCenter, near the core, unchanged by this pass) --
// "the brain wall" is the segment nearest that facing direction, left
// without extra desks so it doesn't crowd Gamma's own; the 6 other
// personas split 2-2-2 across the remaining 3 segments, in the SAME fixed
// roster order collectCompany() already guarantees (so a persona never
// jumps segments between polls).

export const PERSONA_WALL_RADIUS = 6.5; // unchanged from the old PERSONA_RING_RADIUS
const WALL_SEGMENT_SPREAD = (18 * Math.PI) / 180; // +-18deg off a segment's own center -- clear of both flanking doorways (each segment spans 90deg)

// ─── Brain wall mount (2026-09-14, MODELS builder, coordinator-authorized
// edit -- LAYOUT's ownership of this file is released) ─────────────────────
// The smart board (SmartBoard.tsx, IdeasWall.tsx) mounts here: dead-center
// of the reserved "brain wall" segment -- the SAME segment
// computePersonaWallSlots leaves free of persona desks (Scene.tsx's own
// BRAIN_WALL_ARM_INDEX picks it, closest segment center to ARC_CENTER,
// today's value 0 -> segment 0deg..90deg, center 45deg -- Gamma's own desk,
// at ARC_CENTER~61.34deg/radius 3.4, sits inside this same segment, unmoved
// by this edit). Radius HUB_WALL_RADIUS-0.7 (near the wall, clears the
// board's own backing plate -- see computeBrainWallMount's own comment for
// the exact margin math); y=0.5 bottom-anchored
// (every kit piece's own local origin sits at its base -- see
// SmartBoard.tsx's own comment) puts the ~2.2u-tall board's top comfortably
// under the room's true ceiling (raw 4.25 * ARCHITECTURE_SCALE_HUB, ~3.19),
// clear of BrainCore's own core/glow reach (~2.1) since this sits far off
// -center, not stacked above it like the OLD WALL_POS=[0,3.4,0] did.
//
// `yaw`: rotationYFacing computes the angle that points a kit piece's own
// LOCAL -Z toward the target (every room/door/corridor piece's shared
// "front" convention) -- SmartBoard.tsx's content plane faces LOCAL +Z
// instead (its own choice, documented there), so this adds PI to correct
// for that rather than reusing rotationYFacing's raw output unmodified.
//
// A FUNCTION (not just a bare const) because `armIndex` is genuinely a
// Scene.tsx-computed value (BRAIN_WALL_ARM_INDEX, derived from ARC_CENTER)
// this file must never import (layout.ts is upstream of Scene.tsx, never
// the reverse -- see this file's own header) -- same "receives the
// arm/segment index as a parameter" convention computePersonaWallSlots
// already established just above. `BRAIN_WALL_MOUNT` below is the
// convenience const for callers that don't need a different segment,
// pinned to armIndex=0 -- MUST stay in sync with Scene.tsx's own
// BRAIN_WALL_ARM_INDEX (today both 0); if a future ARC_CENTER/
// ARC_CENTER_NUDGE change ever moves that constant, re-derive this one to
// match rather than leaving it silently stale.
export interface WallMount {
  position: [number, number, number];
  yaw: number;
  width: number;
}

export function computeBrainWallMount(armIndex: number): WallMount {
  const segCenterAngle = armAngle(armIndex) + Math.PI / 4;
  // RADIUS, second derivation (2026-09-14, real-capture-driven fix): a
  // first pass used HUB_WALL_RADIUS-0.7=6.8 (flush against the wall,
  // clearing only the board's own backing-plate depth). A real capture at
  // that radius (models-final-preset0-2148.png) showed NO board visible at
  // all. Root cause, computed (not guessed): the brain-wall segment sits
  // very close to the DEFAULT camera's own azimuth (Scene.tsx's
  // BASE_AZIMUTH, ~38.7deg, vs. this segment's 45deg center -- both derive
  // from/track ARC_CENTER) -- i.e. it is the hub's NEAR wall from that
  // camera's viewpoint. room-large.glb's walls run the full room height
  // (~3.19, ARCHITECTURE_SCALE_HUB * raw 4.25); a target close to that near
  // wall sits almost entirely in its shadow from a ~35deg-elevation camera
  // -- verified with the actual camera/wall/target geometry: line-of-sight
  // height AT the wall's own radius, for a target at radius 6.8, computes
  // to ~3.3 (barely above the 3.19 wall height, and BELOW it for anything
  // under the target's own mid-height) -- explains the miss exactly. A more
  // central target gets more clearance (the SAME math for Gamma's own desk,
  // radius 3.4, gives ~4.9) -- reads as "floating further into the room on
  // an extended mount," which is arguably a BETTER match for J's own
  // "FLOATING smart board" framing than flush-on-the-wall anyway.
  // HUB_WALL_RADIUS is kept as the reference point in this comment (not the
  // formula below) so a future reader can still find the wall's own radius.
  // FIX (2026-09-14, coordinator regression capture scale-before-mid.png vs
  // scale-verify-0106.png, after SmartBoard.tsx's BOARD_SCALE 8->11 bump):
  // radius=4.9/y=0.5 put the enlarged board's face right in the hub's
  // walking/bubble zone (GammaCharacter.tsx's bubble ~y=2.2, LiveAgents.tsx's
  // head+bubble band ~y=1.7-2.3) -- Gamma's own bubble and the chart price
  // labels painted over the board face, and the board visually rose behind
  // standing characters. Two changes, per this file's own already-verified
  // LOS math above (radius 6.8 near-wall = ~3.3 min visible Y; radius 3.4
  // near-center = ~4.9 min visible Y, roughly linear between): radius 6.3
  // (near the wall again, reads as a mounted wall screen, not a
  // floating-in-the-room panel) needs a min visible Y of roughly
  // 3.3+0.47*(6.8-6.3)=3.535 to clear the SAME near-wall occlusion the old
  // 6.8 attempt hit -- y=2.6 (bottom-anchored) puts the board's face band
  // (FACE_Y=0.27 raw * BOARD_SCALE=11 = ~2.97 above the mount, i.e. face
  // center world Y ~5.57) comfortably above both that clearance line AND
  // every character-bubble Y (~1.7-2.3), so the two no longer share the same
  // screen-space band. Reads as a screen mounted up near the wall's own top
  // rather than a floor-level panel -- verify via a fresh
  // hq_capture.ps1 pass if this segment's wall/ceiling geometry ever changes.
  // DECLUTTER builder pass (2026-09-14, real captures boardfit-close/
  // overview.png, read at 1:1): the board at radius 6.3 / y 2.6, paired
  // with SmartBoard.tsx's since-reduced BOARD_SCALE=11, had a horizontal
  // extent (raw width 0.685 * scale, ~6.85u at 11x) FAR past this
  // segment's own WallMount.width=3.3, spilling into the neighboring
  // persona-desk segments ("covers the back half of the hub"), and its
  // bottom-anchored top edge (mount y + raw height*scale) landed roughly
  // 4.8u above SetKit.tsx#HUB_CEILING_Y ("rises above the hub walls into
  // the sky"). SmartBoard.tsx's own BOARD_SCALE=9.6 comment has the full
  // math/trade-off writeup for the scale cut; this radius/y stayed put --
  // see the self-correction note right below for why.
  // SELF-CORRECTION (same session, caught by this pass's own required
  // real-capture verification, per OP-33): a first attempt here moved BOTH
  // radius (6.3->6.6, toward the wall) AND y (2.6->1.1, much lower) at
  // once. The resulting declutter-close.png/declutter-overview.png
  // captures showed the board GONE ENTIRELY -- and re-reading this
  // function's OWN comment above explains exactly why: it's the identical
  // failure mode already diagnosed here once ("a target close to the near
  // wall sits almost entirely in its shadow... radius 6.8 showed NO board
  // visible at all... line-of-sight height at the wall's own radius, for a
  // target at radius 6.8, computes to ~3.3"). Pushing radius toward the
  // wall WHILE ALSO dropping y put the board below that same LOS floor a
  // second time. Reverted radius/y to the values THIS FILE already proved
  // render correctly from the close-cam preset (6.3 / 2.6, unchanged from
  // before this pass) -- only BOARD_SCALE/BOARD_PITCH change now (see
  // SmartBoard.tsx's own comment). This keeps the board visibly LARGER
  // than the original 8x (9.6x) and modestly reduces the ceiling overshoot
  // (~4.8u -> ~3.7u, from the smaller raw height alone), but does NOT
  // achieve full ceiling containment -- see this pass's own capture
  // verification/report for the measured top-edge number. Full containment
  // at a "clearly bigger than 8x" scale needs either a taller hub ceiling
  // or a mount radius/y combination nobody has found yet that stays above
  // this camera's own LOS floor -- out of this pass's scope.
  const radius = 6.3;
  const position: [number, number, number] = [Math.cos(segCenterAngle) * radius, 2.6, Math.sin(segCenterAngle) * radius];
  return { position, yaw: rotationYFacing(position, HUB) + Math.PI, width: 3.3 };
}

/** armIndex=0 -- today's BRAIN_WALL_ARM_INDEX (Scene.tsx). See this
 * section's own header for the sync contract. */
export const BRAIN_WALL_MOUNT: WallMount = computeBrainWallMount(0);

export interface PersonaWallSlot {
  position: [number, number, number];
  rotationY: number; // faces the hub center, same -Z-front convention as every other kit placement
}

/** `brainWallArmIndex` picks the "brain wall" segment: the one starting at
 * that arm's own doorway and running to the next (i.e. segment k spans
 * armAngle(k)..armAngle(k+1), centered at armAngle(k)+45deg). Returns one
 * slot per inner persona (index 0..5, the 6 non-Gamma personas). */
export function computePersonaWallSlots(count: number, brainWallArmIndex: number): PersonaWallSlot[] {
  const brainSegment = ((brainWallArmIndex % 4) + 4) % 4;
  const otherSegments = [0, 1, 2, 3].filter((k) => k !== brainSegment);
  const out: PersonaWallSlot[] = [];
  for (let i = 0; i < count; i++) {
    const segment = otherSegments[Math.floor(i / 2) % otherSegments.length];
    const side = i % 2 === 0 ? -1 : 1;
    const segCenterAngle = armAngle(segment) + Math.PI / 4;
    const angle = segCenterAngle + side * WALL_SEGMENT_SPREAD;
    const position: [number, number, number] = [
      Math.cos(angle) * PERSONA_WALL_RADIUS, 0, Math.sin(angle) * PERSONA_WALL_RADIUS,
    ];
    out.push({ position, rotationY: rotationYFacing(position, HUB) });
  }
  return out;
}

// ─── Walk graph ──────────────────────────────────────────────────────────
// Task: "Walk graph (YOU own it): nodes = hub centre, each hub doorway,
// each T, each bay door, each bay desk, each persona desk, the smart board
// wall spot; edges = hallway centrelines; walks follow the graph (shortest
// path over this tiny graph, precomputed at layout time, no per-frame
// allocation) -- nobody ever walks through a wall again." Published here as
// the contract MOTION-2 wires Agent.tsx's own walk consumer to (that file
// is off-limits to this pass -- see WalkPlan in types.ts). The graph is, by
// construction, a TREE rooted at hub-center (every edge below either joins
// a spine's own chain or hangs a leaf off the hub) -- Dijkstra still used
// (not a tree-specific shortcut) so a future edge that adds a real cycle
// (e.g. a direct bay-to-bay shortcut) stays correct without a rewrite; the
// node count (~30) makes even the O(n^2) linear-scan priority step trivial,
// and this only ever runs when a walk TARGET changes, never per-frame.

// CAMPUS-GATE pass (2026-09-15): WalkNode/WalkGraph/findWalkPath moved to
// liveAgentWalk.ts -- see that module's own "Walk graph pathfinding" header
// for why. Short version: this file imports 3 raw-kit constants from
// SetKit.tsx (a real .tsx React/three component file), which node's own ESM
// loader refuses to load at all under plain `node --test`
// (ERR_UNKNOWN_FILE_EXTENSION, verified this pass) -- so layout.ts itself
// can never be imported by this repo's node-native test suite, and neither
// could a path-safety regression test for findWalkPath (the exact test this
// pass needs to add, per the campus-gate entry-node change below) if the
// function stayed here. findWalkPath has zero SetKit dependency -- it only
// ever touches a WalkGraph (a plain nodes/adjacency Map pair) -- so this is
// a pure, behavior-preserving code MOVE, not a rewrite. Re-exported below so
// every existing import site (Scene.tsx, LiveAgents.tsx) keeps working with
// zero edits of its own.
import { computeCampusGateGeometry, findWalkPath, type WalkGraph, type WalkNode } from "./liveAgentWalk";
export { findWalkPath };
export type { WalkGraph, WalkNode };

function dist3(a: readonly [number, number, number], b: readonly [number, number, number]): number {
  return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);
}

export interface WalkGraphInput {
  /** Scene.tsx's own `geometry` array -- every BaySlot field plus the
   * bay's own desk/seat world position, already computed there (same
   * `localToWorld(position, rotationY, seatLocal)` call every bay
   * agent/desk already uses) so this module never has to re-derive it. */
  baySlots: Array<BaySlot & { agentHome: [number, number, number] }>;
  personaSlots: Array<{ name: string; position: [number, number, number] }>;
  gammaDeskPos: [number, number, number];
  smartBoardPos: [number, number, number];
  /** Named hub-interior ambient points (the old PURPOSEFUL_TARGETS record --
   * "ideas-wall"/"core"/"lounge") -- kept as graph leaves off hub-center so
   * every walk destination this scene has ever used, not just the new
   * cross-shaped ones, resolves through the SAME single structure. */
  ambientPoints: Record<string, [number, number, number]>;
}

/** Builds the full walk graph from a layout snapshot. Pure data -- call
 * once per layout-relevant render (bay/persona positions are already
 * referentially stable across polls, see Scene.tsx's own comment on why
 * that stability matters), never inside a useFrame. */
export function buildWalkGraph(input: WalkGraphInput): WalkGraph {
  const nodes = new Map<string, WalkNode>();
  const adjacency: WalkGraph["adjacency"] = new Map();

  const addNode = (id: string, position: [number, number, number]) => {
    nodes.set(id, { id, position });
    if (!adjacency.has(id)) adjacency.set(id, []);
  };
  const addEdge = (a: string, b: string) => {
    const na = nodes.get(a);
    const nb = nodes.get(b);
    if (!na || !nb) return;
    const d = dist3(na.position, nb.position);
    adjacency.get(a)!.push({ to: b, dist: d });
    adjacency.get(b)!.push({ to: a, dist: d });
  };

  addNode("hub-center", HUB);
  for (let k = 0; k < 4; k++) {
    const arm = computeArmLayout(k);
    addNode(`hub-door-${k}`, arm.hubDoorPos);
    addNode(`t-${k}`, arm.tCenter);
    addEdge("hub-center", `hub-door-${k}`);
    addEdge(`hub-door-${k}`, `t-${k}`);
  }
  // CAMPUS-GATE pass (2026-09-15, J: agents should "spawn at the gate, walk
  // the hallways ... walk out and despawn when they go quiet" -- today they
  // spawn/leave at the hub centre, the middle of the building, not a gate).
  // Sits just past arm 0's own real footprint (ARM_LEN, this file's own
  // half-length-of-one-arm constant) plus the plaza's own apron (PLAZA_APRON,
  // same margin the plaza floor/outdoor-prop clearance already use) --
  // [21.6,0,0] at today's raw-kit dimensions, derived, never a literal.
  // Wired to arm 0's T-junction ("t-0", added just above) rather than
  // straight to the hub door: arm 0 (ZONE lab -> bay-desk-0, this session's
  // own worst-case walk) already has a paved open-plaza run from its
  // T-junction out to the apron edge, so this edge crosses open plaza floor
  // (never a wall), a real hallway hop at the SAME node granularity as every
  // other edge this graph already has.
  addNode("campus-gate", CAMPUS_GATE_POSITION);
  addEdge("campus-gate", "t-0");
  input.baySlots.forEach((slot) => {
    addNode(`bay-door-${slot.index}`, slot.doorWorldPos);
    addNode(`bay-desk-${slot.index}`, slot.agentHome);
    addEdge(`t-${slot.armIndex}`, `bay-door-${slot.index}`);
    addEdge(`bay-door-${slot.index}`, `bay-desk-${slot.index}`);
  });
  input.personaSlots.forEach((p) => {
    addNode(`persona-${p.name}`, p.position);
    addEdge("hub-center", `persona-${p.name}`);
  });
  addNode("gamma-desk", input.gammaDeskPos);
  addEdge("hub-center", "gamma-desk");
  addNode("smart-board", input.smartBoardPos);
  addEdge("hub-center", "smart-board");
  Object.entries(input.ambientPoints).forEach(([name, pos]) => {
    addNode(`ambient-${name}`, pos);
    addEdge("hub-center", `ambient-${name}`);
  });

  return { nodes, adjacency };
}

/** Builds a WalkPlan (the contract Agent.tsx's own walk consumer reads once
 * MOTION-2 wires it up there -- see types.ts#WalkPlan) from a graph path.
 * `purpose`/`dwellS`/`dwellAnim` are the caller's own business-logic choice
 * (e.g. computePurposefulWalk's `reason`); this function only does the
 * geometry, falling back to a direct 1-point "waypoint" at `fallback` if
 * the graph search came back empty rather than producing an invalid plan. */
export function toWalkPlan(
  waypoints: [number, number, number][] | null,
  fallback: [number, number, number],
  purpose: string,
  dwellS: number,
  dwellAnim: WalkPlan["dwellAnim"],
): WalkPlan {
  return {
    waypoints: waypoints && waypoints.length > 0 ? waypoints : [fallback],
    purpose,
    dwellS,
    dwellAnim,
  };
}

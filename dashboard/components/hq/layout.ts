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

export interface WalkNode {
  id: string;
  position: [number, number, number];
}

interface WalkEdgeEntry {
  to: string;
  dist: number;
}

export interface WalkGraph {
  nodes: Map<string, WalkNode>;
  adjacency: Map<string, WalkEdgeEntry[]>;
}

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
  const adjacency = new Map<string, WalkEdgeEntry[]>();

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

/** Dijkstra over the walk graph -- see this section's own header for why a
 * full shortest-path search (rather than a tree-only shortcut) is used
 * despite the graph's current tree shape. Returns world-space waypoints
 * from `fromId` to `toId` inclusive, or null if either id is unknown or
 * unreachable (fails open to the caller, which should fall back to a
 * direct line rather than throw -- same "never crash on a missing node"
 * discipline as every other lookup in this tree). */
export function findWalkPath(graph: WalkGraph, fromId: string, toId: string): [number, number, number][] | null {
  const start = graph.nodes.get(fromId);
  const goal = graph.nodes.get(toId);
  if (!start || !goal) return null;
  if (fromId === toId) return [start.position];

  const dist = new Map<string, number>([[fromId, 0]]);
  const prev = new Map<string, string>();
  const visited = new Set<string>();

  for (;;) {
    let current: string | null = null;
    let currentDist = Infinity;
    for (const [id, d] of dist) {
      if (!visited.has(id) && d < currentDist) {
        current = id;
        currentDist = d;
      }
    }
    if (current === null || current === toId) break;
    visited.add(current);
    for (const edge of graph.adjacency.get(current) ?? []) {
      if (visited.has(edge.to)) continue;
      const candidate = currentDist + edge.dist;
      if (candidate < (dist.get(edge.to) ?? Infinity)) {
        dist.set(edge.to, candidate);
        prev.set(edge.to, current);
      }
    }
  }
  if (!dist.has(toId)) return null;

  const path: string[] = [toId];
  let cursor = toId;
  while (cursor !== fromId) {
    const parent = prev.get(cursor);
    if (!parent) return null; // unreachable -- fail open, never throw
    path.push(parent);
    cursor = parent;
  }
  path.reverse();
  return path.map((id) => graph.nodes.get(id)!.position);
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

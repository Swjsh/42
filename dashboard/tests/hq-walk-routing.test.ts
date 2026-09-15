// @ts-nocheck -- same reason as tests/campus-gate.test.ts's own header: this
// file uses an explicit ".ts" extension on its relative import (required for
// plain `node --test` to resolve it; the project tsconfig's
// `moduleResolution: "bundler"` has no `allowImportingTsExtensions`). Purely
// a syntax-erasure pragma -- has no effect on what actually runs.
//
// WALK-ROUTING pass (2026-09-15): regression coverage for the fix to a live
// bug J watched happen -- a red-health ("alert") lane agent ("Futures", bay
// index 2) paced "from the middle straight to its cube through walls, no
// walkway, no doors". Root cause (Agent.tsx's own `behavior === "alert"`
// branch): the pace point used to be computed straight toward the hub
// center along the home->hub line, which for a BAY agent cuts through that
// bay's own SIDE wall -- the bay's real door sits on a DIFFERENT wall,
// facing its side hallway/T-junction (layout.ts#computeBaySlot's own
// `doorWorldPos`), not on the home->hub diagonal. Every other queued walk
// (arrival/allhands/purposeful/eventWalk) had the same class of bug: a raw
// 2-point `[home, legTo]` straight leg with no graph routing at all.
//
// Fix: Agent.tsx now accepts an optional `walkGraph` (routes every legacy
// 2-point walk AND the "arriving" hub->home leg through
// liveAgentWalk.ts#routeViaGraph, the SAME graph/algorithm LiveAgents.tsx
// already trusts) and an optional `alertPacePoint` (Scene.tsx passes each
// bay's own `doorWorldPos`, replacing the toward-hub formula for bay
// agents only -- personas, whose home->hub line never crosses a wall, keep
// the original formula).
//
// layout.ts itself CANNOT be imported here -- it imports 3 raw-kit
// constants from SetKit.tsx (a real .tsx React/three component file), which
// node's own ESM loader refuses to load at all under plain `node --test`
// (see tests/campus-gate.test.ts's own header for the confirmed
// ERR_MODULE_NOT_FOUND). This file instead reproduces layout.ts's own
// documented derivation chain with plain literals (same technique
// tests/campus-gate.test.ts already uses) to build a SYNTHETIC WalkGraph
// with the exact same topology buildWalkGraph() produces, and exercises the
// real `routeViaGraph`/`findWalkPath` against it.
//
// Real scene constants (layout.ts's own derivation, reproduced verbatim
// from that file's header comments and tests/campus-gate.test.ts's own
// already-verified copy):
//   ARCHITECTURE_SCALE_BAY = 0.45, HUB_WALL_RADIUS = 7.5 (SetKit.tsx)
//   T_JUNCTION_HALF = (4*0.45)/2 = 0.9
//   MAIN_HALL_LEN = 9, SIDE_HALL_LEN = 4.5, BAY_HALF_DEPTH = (12*0.45)/2 = 2.7
//   T_DIST = HUB_WALL_RADIUS + MAIN_HALL_LEN + T_JUNCTION_HALF = 17.4
//   SIDE_SPAN = T_JUNCTION_HALF + SIDE_HALL_LEN + BAY_HALF_DEPTH = 8.1
//
// Run: cd dashboard && node --test tests/hq-walk-routing.test.ts
// (or the full suite: cd dashboard && npm test)

import { test } from "node:test";
import assert from "node:assert/strict";
import { routeViaGraph, findWalkPath, type WalkGraph, type WalkNode } from "../components/hq/liveAgentWalk.ts";

const HUB_WALL_RADIUS = 7.5;
const T_JUNCTION_HALF = 0.9;
const MAIN_HALL_LEN = 9;
const SIDE_HALL_LEN = 4.5;
const BAY_HALF_DEPTH = 2.7;
const T_DIST = HUB_WALL_RADIUS + MAIN_HALL_LEN + T_JUNCTION_HALF; // 17.4
const SIDE_SPAN = T_JUNCTION_HALF + SIDE_HALL_LEN + BAY_HALF_DEPTH; // 8.1

function armAngle(armIndex: number): number {
  return (armIndex * Math.PI) / 2;
}

interface ArmLayout {
  mainAngle: number;
  hubDoorPos: [number, number, number];
  tCenter: [number, number, number];
}

function computeArmLayout(armIndex: number): ArmLayout {
  const mainAngle = armAngle(armIndex);
  const dirX = Math.cos(mainAngle);
  const dirZ = Math.sin(mainAngle);
  return {
    mainAngle,
    hubDoorPos: [dirX * HUB_WALL_RADIUS, 0, dirZ * HUB_WALL_RADIUS],
    tCenter: [dirX * T_DIST, 0, dirZ * T_DIST],
  };
}

interface SyntheticBaySlot {
  index: number;
  armIndex: number;
  position: [number, number, number];
  doorWorldPos: [number, number, number];
  agentHome: [number, number, number];
  /** Bay-local unit axes in world XZ -- width (parallel to the arm's own
   * main/cardinal axis) and depth (parallel to the side-hallway/perpendicular
   * axis, door at depth=-BAY_HALF_DEPTH). Same axes layout.ts's own
   * `rotationYFacing(position, tCenter)` encodes as a single yaw -- kept as
   * two explicit unit vectors here instead so the regression test below can
   * project a world point onto them directly without re-deriving a rotation
   * matrix. */
  localWidthAxis: [number, number];
  localDepthAxis: [number, number];
}

/** Reproduces layout.ts#computeBaySlot's own math (position, doorWorldPos)
 * for a synthetic 8-bay roster (4 arms x 2 sides), matching that function's
 * exact formula. */
function computeBaySlot(index: number): SyntheticBaySlot {
  const armIndex = Math.floor(index / 2);
  const sideIndex = index % 2;
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
  // Desk sits deeper in the bay than its own center, away from the door --
  // an honest approximation (real agentHome comes from Scene.tsx's own
  // localToWorld(seatLocal) call, not reproduced here) that only needs to
  // sit strictly further from the door than `position` for this file's own
  // "stays inside the bay's square" assertion to be meaningful.
  const agentHome: [number, number, number] = [
    position[0] + pDirX * (BAY_HALF_DEPTH * 0.4), 0, position[2] + pDirZ * (BAY_HALF_DEPTH * 0.4),
  ];
  return {
    index, armIndex, position, doorWorldPos, agentHome,
    localWidthAxis: [Math.cos(arm.mainAngle), Math.sin(arm.mainAngle)],
    localDepthAxis: [pDirX, pDirZ],
  };
}

const BAY_SLOTS = Array.from({ length: 8 }, (_, i) => computeBaySlot(i));
const PERSONA_NAMES = ["gamma", "pilot", "chef"];

/** Builds a synthetic WalkGraph with the SAME node ids/topology
 * buildWalkGraph() produces (layout.ts) -- hub-center, hub-door-k/t-k per
 * arm, bay-door-N/bay-desk-N per bay, persona-<name>, all wired with the
 * same edges that function creates. */
function buildSyntheticGraph(): WalkGraph {
  const nodes = new Map<string, WalkNode>();
  const adjacency = new Map<string, { to: string; dist: number }[]>();
  const addNode = (id: string, position: [number, number, number]) => {
    nodes.set(id, { id, position });
    if (!adjacency.has(id)) adjacency.set(id, []);
  };
  const addEdge = (a: string, b: string) => {
    const na = nodes.get(a)!;
    const nb = nodes.get(b)!;
    const d = Math.hypot(na.position[0] - nb.position[0], na.position[2] - nb.position[2]);
    adjacency.get(a)!.push({ to: b, dist: d });
    adjacency.get(b)!.push({ to: a, dist: d });
  };

  addNode("hub-center", [0, 0, 0]);
  for (let k = 0; k < 4; k++) {
    const arm = computeArmLayout(k);
    addNode(`hub-door-${k}`, arm.hubDoorPos);
    addNode(`t-${k}`, arm.tCenter);
    addEdge("hub-center", `hub-door-${k}`);
    addEdge(`hub-door-${k}`, `t-${k}`);
  }
  BAY_SLOTS.forEach((slot) => {
    addNode(`bay-door-${slot.index}`, slot.doorWorldPos);
    addNode(`bay-desk-${slot.index}`, slot.agentHome);
    addEdge(`t-${slot.armIndex}`, `bay-door-${slot.index}`);
    addEdge(`bay-door-${slot.index}`, `bay-desk-${slot.index}`);
  });
  PERSONA_NAMES.forEach((name, i) => {
    addNode(`persona-${name}`, [i * 2 - 2, 0, 3]);
    addEdge("hub-center", `persona-${name}`);
  });

  return { nodes, adjacency };
}

test("bay-desk-2 (Futures) -> hub-center routes through bay-door-2, t-1, hub-door-1 in order", () => {
  const graph = buildSyntheticGraph();
  const path = findWalkPath(graph, "bay-desk-2", "hub-center");
  assert.ok(path, "expected a path");

  // Recover which node id each waypoint corresponds to (findWalkPath returns
  // positions, not ids) by matching against the graph's own node positions --
  // exact match is safe here since every synthetic node has a distinct
  // position and findWalkPath returns THOSE SAME position tuples verbatim.
  const idFor = (pos: [number, number, number]): string | undefined => {
    for (const [id, node] of graph.nodes) {
      if (node.position[0] === pos[0] && node.position[2] === pos[2]) return id;
    }
    return undefined;
  };
  const ids = path!.map(idFor);
  assert.deepEqual(ids, ["bay-desk-2", "bay-door-2", "t-1", "hub-door-1", "hub-center"]);
});

test("alert pace point: doorWorldPos keeps the desk->door segment inside the bay's own square, the old toward-hub formula does not", () => {
  const slot = BAY_SLOTS[2]; // Futures, armIndex 1
  const projectLocal = (worldPoint: [number, number, number]): { width: number; depth: number } => {
    const rel: [number, number] = [worldPoint[0] - slot.position[0], worldPoint[2] - slot.position[2]];
    return {
      width: rel[0] * slot.localWidthAxis[0] + rel[1] * slot.localWidthAxis[1],
      depth: rel[0] * slot.localDepthAxis[0] + rel[1] * slot.localDepthAxis[1],
    };
  };

  // NEW behavior: alertPacePoint = slot.doorWorldPos, and Agent.tsx's own
  // updated formula paces the FULL home->door distance (not capped) --
  // both endpoints of the pace leg must stay within the bay's own
  // BAY_HALF_DEPTH=2.7 square on both axes.
  const homeLocal = projectLocal(slot.agentHome);
  const doorLocal = projectLocal(slot.doorWorldPos);
  assert.ok(Math.abs(homeLocal.width) <= BAY_HALF_DEPTH + 1e-6);
  assert.ok(Math.abs(homeLocal.depth) <= BAY_HALF_DEPTH + 1e-6);
  assert.ok(Math.abs(doorLocal.width) <= BAY_HALF_DEPTH + 1e-6);
  assert.ok(Math.abs(doorLocal.depth) <= BAY_HALF_DEPTH + 1e-6);
  // The door itself sits exactly on the depth boundary (the real doorway
  // wall), never on the width boundary -- confirms doorLocal is actually
  // testing the DOOR wall, not some other edge of the square.
  assert.ok(Math.abs(Math.abs(doorLocal.depth) - BAY_HALF_DEPTH) < 1e-6);

  // OLD (regression) behavior: Agent.tsx's original formula paced toward
  // HUB=[0,0,0] from `home`, capped at min(3.4, dist*0.4).
  const HUB: [number, number, number] = [0, 0, 0];
  const homeToHubDist = Math.hypot(HUB[0] - slot.agentHome[0], HUB[2] - slot.agentHome[2]);
  const paceDist = Math.min(3.4, homeToHubDist * 0.4);
  const dirX = (HUB[0] - slot.agentHome[0]) / homeToHubDist;
  const dirZ = (HUB[2] - slot.agentHome[2]) / homeToHubDist;
  const oldDoorPos: [number, number, number] = [
    slot.agentHome[0] + dirX * paceDist, 0, slot.agentHome[2] + dirZ * paceDist,
  ];
  const oldLocal = projectLocal(oldDoorPos);
  // This is the regression this test pins: the OLD pace point exits the
  // bay's own square along the WIDTH axis (a real, non-door side wall),
  // while staying inside on the depth axis -- i.e. it walks through the
  // side wall, not out the door.
  assert.ok(Math.abs(oldLocal.width) > BAY_HALF_DEPTH, `expected old formula to exit width bound, got ${oldLocal.width}`);
  assert.ok(Math.abs(oldLocal.depth) <= BAY_HALF_DEPTH + 1e-6, `expected old formula to stay within depth bound, got ${oldLocal.depth}`);
});

test("persona desk -> neighbor persona desk always routes via hub-center, never a straight chord", () => {
  const graph = buildSyntheticGraph();
  const path = findWalkPath(graph, "persona-gamma", "persona-pilot");
  assert.ok(path);
  assert.equal(path!.length, 3, "expected exactly 3 waypoints: gamma -> hub-center -> pilot");
  const hubCenter = graph.nodes.get("hub-center")!.position;
  assert.deepEqual(path![1], hubCenter);
});

test("routeViaGraph: bay-desk-2 home to hub ambient point round-trips through the same door/T-junction chain", () => {
  const graph = buildSyntheticGraph();
  const routed = routeViaGraph(graph, BAY_SLOTS[2].agentHome, [0, 0, 0]);
  assert.ok(routed.length >= 2);
  // First and last points are the exact caller-supplied endpoints (never
  // snapped to the nearest node) -- routeViaGraph's own documented contract.
  assert.deepEqual(routed[0], BAY_SLOTS[2].agentHome);
  assert.deepEqual(routed[routed.length - 1], [0, 0, 0]);
  // Interior waypoints pass through the bay's own door -- never a straight
  // chord through the bay's side wall.
  const passesThroughDoor = routed.some(
    (p) => Math.hypot(p[0] - BAY_SLOTS[2].doorWorldPos[0], p[2] - BAY_SLOTS[2].doorWorldPos[2]) < 0.01,
  );
  assert.ok(passesThroughDoor);
});

test("routeViaGraph collapses duplicate endpoints and never returns fewer than 2 points", () => {
  const graph = buildSyntheticGraph();
  // from/to both essentially AT hub-center: nearest-node for both endpoints
  // is the SAME node ("hub-center") -- routeViaGraph's own documented
  // "same nearest node" shortcut returns the direct 2-point [from, to] leg
  // rather than inserting a redundant middle waypoint.
  const same = routeViaGraph(graph, [0.01, 0, 0], [-0.01, 0, 0]);
  assert.equal(same.length, 2);

  // A real cross-room route (bay desk to a persona desk) must still return
  // at least 2 points and must not repeat a waypoint that collapses to the
  // same position as its neighbor (the 0.05u de-dup tolerance).
  const cross = routeViaGraph(graph, BAY_SLOTS[0].agentHome, graph.nodes.get("persona-chef")!.position);
  assert.ok(cross.length >= 2);
  for (let i = 1; i < cross.length; i++) {
    const d = Math.hypot(cross[i][0] - cross[i - 1][0], cross[i][2] - cross[i - 1][2]);
    assert.ok(d > 1e-6, `duplicate consecutive waypoint at index ${i}`);
  }
});

test("routeViaGraph falls back to a direct 2-point leg on an empty graph", () => {
  const empty: WalkGraph = { nodes: new Map(), adjacency: new Map() };
  const result = routeViaGraph(empty, [1, 0, 2], [5, 0, 9]);
  assert.deepEqual(result, [[1, 0, 2], [5, 0, 9]]);
});

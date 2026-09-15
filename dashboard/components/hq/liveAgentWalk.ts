// LIVE-AGENTS pass, coordinator-directed fix (2026-09-14, browser verification
// of e990319f found 2 defects): the walk-decision and stand-slot math pulled
// OUT of LiveAgents.tsx into their own pure, react/three-free module so both
// can be unit-tested with plain `node --test` (mirrors layout.ts's own
// "pure geometry/math, no React, no Three.js" convention -- see that file's
// header for why this split matters: LiveAgents.tsx itself needs a DOM/GL
// context via react-three-fiber's hooks, which `node --test` cannot provide).
//
// DEFECT 2 ROOT CAUSE (stuck leave, e990319f): the original effect gated
// EVERY destination change -- both ordinary in-life retargeting AND the
// final leave-to-entry walk -- behind ONE shared `seenDest.current ===
// activeDest` latch. If an agent's most recently classified zone had
// already resolved to "hub" (lib/hq-agents.ts#ZONE_NODE_ID.hub, which is
// the SAME node id as ENTRY_NODE_ID -- a live agent with no dashboard/
// backtest/setup/automation/markdown path in its recent tool calls
// classifies to the hub), `seenDest.current` already held that exact
// string. When the server later dropped the agent and `leaving` flipped
// true, the newly-computed destination ALSO evaluated to that same string
// -- the guard read this as "nothing changed" and silently skipped the
// walk-kickoff (and therefore the despawn-on-arrival it would have
// scheduled), permanently stranding the avatar in its last "working" pose
// with `leaving` true forever (which is exactly what fed the diagnostic's
// "leaving" label at a frozen position).
//
// FIX: `decideNextWalk` below treats "leaving" as its OWN one-shot trigger
// (`leaveTriggered`), completely independent of `seenTarget` (the ordinary-
// retargeting latch) -- a leave decision is made from `leaving` alone and
// can never be suppressed by a coincidental string match with an earlier
// ordinary destination. A hard per-avatar leave timeout is layered on top
// in LiveAgents.tsx itself (defense in depth -- this module's own pure
// function is proven correct by the tests below, but a timeout backstop
// means no *other*, yet-undiscovered stall can strand an avatar forever
// either).
//
// DEFECT 1 (stacking): `computeStandSlot` gives every agent sharing a
// destination node a distinct point on a small ring around it, indexed by
// a STABLE sort order (lexicographic by id) so a given agent's slot never
// jumps around as other agents in the same group arrive/leave elsewhere in
// the roster -- only removing/adding IDS WITHIN that same group can shift
// indices, which is the correct, expected behavior (a fresh member joining
// a crowded zone should redistribute the ring, not overlap the newcomer on
// an existing occupant).

// CAMPUS-GATE pass (2026-09-15, J: agents should "spawn at the gate, walk
// the hallways to the area they're working in ... walk out and despawn when
// they go quiet" -- today both this constant and lib/hq-agents.ts's own copy
// read "hub-center", the middle of the building, not a gate). Moved to a new
// walk-graph leaf node, "campus-gate" (layout.ts#buildWalkGraph, wired to
// arm 0's T-junction, a real open-plaza hallway hop -- see that function's
// own comment for the exact derivation). MUST stay in sync with
// lib/hq-agents.ts#ENTRY_NODE_ID -- that module is import-free by design
// (see its own header: no sibling lib/*.ts value import, no three.js, no
// react, so its fs-reading pure combiner stays trivially unit-testable and
// can never create a circular/SSR-unsafe dependency), so it cannot import
// this constant; a plain string literal kept identical is the correct
// solution here, backstopped by a sync test in
// dashboard/tests/live-agent-walk.test.ts.
export const ENTRY_NODE_ID = "campus-gate";

// GATE-PROP pass (2026-09-15): pure geometry for the campus-gate set-
// dressing prop (SetKit.tsx#CampusGate) -- lives HERE, not layout.ts,
// despite the caller (layout.ts) owning every input value, for the SAME
// reason findWalkPath/WalkGraph were moved here in the CAMPUS-GATE pass
// above: layout.ts imports 3 raw-kit constants from SetKit.tsx (a real
// .tsx component file), which node's own ESM loader can't load at all
// under plain `node --test` (confirmed this session: ERR_MODULE_NOT_FOUND
// trying to resolve SetKit.tsx as SetKit.ts, since the test suite's
// resolve-ts-extensionless loader only ever appends ".ts") -- so a
// regression test for the gate's own placement math needs this function
// import-free of layout.ts, taking every input as a plain number/tuple
// instead. layout.ts calls this once (module scope) with its own already-
// computed ARM_LEN/PLAZA_APRON/computeArmLayout(0) values and re-exports
// the result, so there is exactly ONE computation, never two independent
// copies that could drift.
export interface CampusGateGeometry {
  /** World position, world-Y always 0 (this scene's floor plane). */
  position: [number, number, number];
  /** Yaw that puts the gate-door kit piece's own local Z axis (its walk-
   * through axis -- see SetKit.tsx#DepartmentBayShell's own comment: local
   * -Z is "front", agents pass through a mounted gate-door along local Z)
   * onto the position<->facingTarget line, computed via the exact same
   * atan2 formula layout.ts#rotationYFacing already uses for every other
   * kit placement in this tree (self=position, target=facingTarget). */
  rotationY: number;
  /** (gateRawWidth / 2) * scale -- the guaranteed-safe lower bound on the
   * gate's own clear walkable half-width either side of its own local
   * z=0 centerline (see layout.ts's own CAMPUS_GATE_SCALE header for why
   * the OUTER footprint half-width is the conservative, provably-
   * sufficient bound: the true opening is always <= it, never larger). */
  clearHalfWidth: number;
}

export function computeCampusGateGeometry(params: {
  /** Arm direction, radians (layout.ts#computeArmLayout's own `mainAngle`,
   * `armAngle(armIndex)` -- 0 = +X, matching this tree's cos/sin
   * convention). */
  armMainAngle: number;
  /** World point the gate's local -Z should face toward (layout.ts wires
   * this to the SAME arm's own T-junction center, `tCenter`, matching the
   * walk edge the campus-gate WalkNode itself has to "t-0"). */
  facingTarget: [number, number, number];
  /** Distance from the hub (world origin) along `armMainAngle` to the gate
   * itself -- layout.ts passes `ARM_LEN + PLAZA_APRON`, the SAME distance
   * the campus-gate WalkNode's own position already uses (that module's
   * own header explains the derivation), never re-derived here. */
  distanceFromHub: number;
  /** Scale factor applied to the gate-door.glb kit piece. */
  scale: number;
  /** gate-door.glb's raw (unscaled) X footprint -- 4.2 at today's kit
   * (layout.ts's own CAMPUS_GATE_SCALE header cites the glb_extents.mjs
   * measurement this number comes from). */
  gateRawWidth: number;
}): CampusGateGeometry {
  const { armMainAngle, facingTarget, distanceFromHub, scale, gateRawWidth } = params;
  const position: [number, number, number] = [
    Math.cos(armMainAngle) * distanceFromHub,
    0,
    Math.sin(armMainAngle) * distanceFromHub,
  ];
  const rotationY = Math.atan2(position[0] - facingTarget[0], position[2] - facingTarget[2]);
  const clearHalfWidth = (gateRawWidth / 2) * scale;
  return { position, rotationY, clearHalfWidth };
}

// ─── Walk graph pathfinding (moved from layout.ts, CAMPUS-GATE pass) ───────
// layout.ts imports 3 raw-kit constants from SetKit.tsx (a real .tsx
// React/three component file). Verified this pass: node's own ESM loader
// refuses to load ANY .tsx file at all under plain `node --test`
// (`ERR_UNKNOWN_FILE_EXTENSION`, thrown before TS type-stripping or JSX
// parsing even begin) -- so layout.ts itself can never be imported by this
// repo's node-native test suite, no matter what it exports. findWalkPath has
// zero SetKit dependency of its own -- it only ever touches a WalkGraph (a
// plain nodes/adjacency Map pair) -- so moving JUST this pure function (and
// its own WalkNode/WalkGraph/WalkEdgeEntry support types, likewise
// SetKit-free) to this already node-testable, react/three-free module makes
// it possible to prove the path-safety regression test below (every
// ZONE_NODE_ID reachable from campus-gate) against the REAL algorithm,
// rather than a hand-reimplemented copy that could silently drift from it.
// A pure, behavior-preserving code MOVE, not a rewrite -- layout.ts
// re-exports all three names from this module unchanged, so every existing
// import site (Scene.tsx, LiveAgents.tsx) keeps working with zero edits.

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

/** Dijkstra over the walk graph -- a full shortest-path search (rather than
 * a tree-only shortcut) despite the graph's current tree shape, so a future
 * edge that adds a real cycle (e.g. a direct bay-to-bay shortcut) stays
 * correct without a rewrite; the node count (~30) makes even the O(n^2)
 * linear-scan priority step trivial, and this only ever runs when a walk
 * TARGET changes, never per-frame. Returns world-space waypoints from
 * `fromId` to `toId` inclusive, or null if either id is unknown or
 * unreachable (fails open to the caller, which should fall back to a direct
 * line rather than throw -- same "never crash on a missing node" discipline
 * as every other lookup in this tree). */
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

// ─── Retarget out-and-back fix (CONVOY-STACK v13, 2026-09-15) ─────────────
//
// ROOT CAUSE (lane snap, probe 20260915T140056Z): a mid-walk retarget
// (LiveAgents.tsx's own decision effect) has always called
// `findWalkPath(walkGraph, currentNode.current, decision.dest)` --
// `currentNode.current` names this WALK's own ORIGIN node (only ever
// advances on arrival, per the TELEPORT FIX comment right above that call
// site), never wherever the avatar has actually walked to SINCE. On a
// walk-graph that is a tree (this module's own findWalkPath header), the
// unique path from that stale origin to a NEW target can require walking
// back out to a shared junction (t-0 in the probe's own report) the avatar
// had ALREADY passed on its way to the OLD target, then back in the other
// direction -- an out-and-back detour that is, from the graph's point of
// view, perfectly correct (it IS the shortest path from the ORIGIN node),
// but wrong for an avatar that is no longer AT that origin. Splicing the
// avatar's real `livePos` in as waypoint 0 (the existing TELEPORT FIX)
// keeps the RENDERED start point correct, but every INTERIOR waypoint
// after it still reflects the origin-relative route -- so the avatar
// visually walks forward, then reverses hard through the very corridor
// segment it just came from. `applyLaneOffsets`'s own per-segment
// perpendicular (this file, below) flips sign across that reversal,
// producing the reported ~0.71u lateral snap on top of the direction
// reversal itself.
//
// FIX: `findRetargetPath` considers TWO candidate routes whenever the
// avatar is actively walking (not resting) at retarget time -- the
// existing "BEHIND" route (unchanged: from `currentNode`, the walk's
// origin) and a new "AHEAD" route (from `walkDest`, the walk's own
// NOT-YET-REACHED destination, i.e. the next real graph node in the
// avatar's current direction of travel) -- and picks whichever gives the
// SHORTER TOTAL distance once each is prefixed by the avatar's own
// straight-line distance from its live position to that route's starting
// node. A target genuinely behind the avatar (on the arc it already
// walked) still correctly routes back through `currentNode`; a target
// reachable by continuing forward (or through a junction ahead) no longer
// detours through where the avatar already was. This is a bounded,
// two-candidate comparison, not a general replan -- `findWalkPath` itself
// is unmodified and still the single source of truth for any given
// origin->target route.
export function findRetargetPath(
  graph: WalkGraph,
  currentNode: string,
  walkDest: string,
  livePos: readonly [number, number, number],
  target: string,
  isWalking: boolean,
): [number, number, number][] | null {
  const behindPath = findWalkPath(graph, currentNode, target);
  // Resting (not actively walking), or already at/approaching the same
  // node the walk's own origin and destination agree on -- no ambiguity,
  // the existing behind-only route is correct and the only one meaningful.
  if (!isWalking || walkDest === currentNode) return behindPath;

  const aheadPath = findWalkPath(graph, walkDest, target);
  if (!aheadPath) return behindPath;
  if (!behindPath) return aheadPath;

  const currentNodePos = graph.nodes.get(currentNode)?.position;
  const walkDestPos = graph.nodes.get(walkDest)?.position;
  if (!currentNodePos || !walkDestPos) return behindPath; // defensive -- an unknown node id fails open to the existing route

  const straightLineDist = (a: readonly [number, number, number], b: readonly [number, number, number]): number =>
    Math.hypot(a[0] - b[0], a[2] - b[2]);

  const totalBehind = straightLineDist(livePos, currentNodePos) + pathDistance(behindPath);
  const totalAhead = straightLineDist(livePos, walkDestPos) + pathDistance(aheadPath);
  return totalAhead < totalBehind ? aheadPath : behindPath;
}

// ─── Leave-timeout derivation (CAMPUS-GATE pass, 2026-09-15) ───────────────
//
// LiveAgents.tsx's own LEAVE_HARD_TIMEOUT_S is a defense-in-depth backstop
// (see that file's own comment): if a leaving avatar never despawns through
// the normal walk-arrival path, this ceiling force-despawns it wherever it
// currently is (LiveAgentAvatar#fireDespawn on timeout) -- so it must never
// be shorter than the SLOWEST real walk out could possibly take, or a
// long-hallway leave would vanish mid-corridor instead of completing its
// walk. Moving campus-gate away from the hub centre (this pass) lengthens
// every walk-out versus the old hub-center entry, so a stale hand-picked
// literal (the old value was tuned against hub-center-as-entry, never
// re-derived here) is exactly the kind of guess this codebase's own
// "no hardcoded values, derive them" convention forbids. This sweep instead
// walks EVERY node the graph actually contains (a strict superset of the 5
// real ZONE_NODE_ID targets lib/hq-agents.ts can emit today -- correct even
// if a future zone mapping adds a 6th node this file never has to know
// about) and returns the single longest real walk-graph distance back to
// `entryNodeId`, in walk-seconds at `walkSpeedUPerS` -- the caller then adds
// its own fixed safety margin on top (LiveAgents.tsx: LEAVE_TIMEOUT_MARGIN_S
// below). A node the graph can't route back to `entryNodeId` from
// (findWalkPath returns null) contributes nothing to this sweep -- CATCHING
// that case is the path-safety regression test's own job (dashboard/tests/
// live-agent-walk.test.ts), not this function's; a silently-skipped
// unreachable node here would otherwise hide exactly the defect that test
// exists to catch.
export const LEAVE_TIMEOUT_MARGIN_S = 10;

export function computeMaxPathDurationS(graph: WalkGraph, entryNodeId: string, walkSpeedUPerS: number): number {
  let maxDist = 0;
  for (const nodeId of graph.nodes.keys()) {
    if (nodeId === entryNodeId) continue;
    const path = findWalkPath(graph, nodeId, entryNodeId);
    if (!path) continue;
    maxDist = Math.max(maxDist, pathDistance(path));
  }
  return maxDist / walkSpeedUPerS;
}

export function pathDistance(wp: ReadonlyArray<readonly [number, number, number]>): number {
  let total = 0;
  for (let i = 0; i < wp.length - 1; i++) {
    total += Math.hypot(wp[i + 1][0] - wp[i][0], wp[i + 1][2] - wp[i][2]);
  }
  return total;
}

// ─── Graph-routed helper for legacy/persona walks (WALK-ROUTING pass, 2026-09-15) ──
//
// ROOT CAUSE this fixes (established by reading Agent.tsx/Scene.tsx this
// pass): every walk this file's own findWalkPath/WalkGraph machinery was
// built for is used by LiveAgents.tsx (live Claude subagents) only.
// Agent.tsx's OWN walk kinds (roundtrip/arrival/allhands/purposeful/
// eventWalk, plus the "alert" pacing branch) all still build a raw 2-point
// `[home, legTo]` straight-line leg (see that file's own "toHub" branch and
// the module-scope alert-phase math) -- correct only when home/hub/legTo
// happen to sit on a line that never crosses a wall, which is NOT true for
// a bay agent whose "alert" pace point was computed straight toward the hub
// center rather than toward its own bay door (the reported "Futures" bug:
// a lane bay agent pacing clean through its own bay's side wall). This
// helper gives Agent.tsx a single, tested way to turn ANY (from, to) pair
// into a real graph-routed waypoint list, exactly the same graph/algorithm
// LiveAgents.tsx already trusts -- never a second, hand-rolled router.
/** Routes from `from` to `to` via the walk graph: finds the graph node
 * nearest each endpoint, runs `findWalkPath` between those two nodes, and
 * returns `[from, ...pathNodes, to]` with any duplicate consecutive point
 * (within 0.05 world units -- the same "already there" tolerance this
 * file's own retarget/reconcile logic uses elsewhere) collapsed. If both
 * endpoints round to the SAME nearest node, this returns `[from, to]`
 * directly rather than `[from, node, to]` -- inserting the node in that
 * case would be a needless mid-air detour through a single point that is
 * not actually between `from` and `to` (e.g. both endpoints are already
 * inside the same bay, near the same bay-desk node); the two-point result
 * is a straight local hop, which is the correct, wall-safe behavior for
 * "already in the same room" since Agent.tsx only ever calls this for
 * pairs whose own within-room straight line was already known-safe (the
 * caller decides room-safety; this function only decides GRAPH TRAVERSAL
 * between different rooms/nodes). Falls back to the direct 2-point leg
 * `[from, to]` if either endpoint has no nearest node at all (an empty
 * graph) or `findWalkPath` cannot connect the two nodes -- fails open,
 * never throws, matching this file's own findWalkPath convention. */
export function routeViaGraph(
  graph: WalkGraph,
  from: readonly [number, number, number],
  to: readonly [number, number, number],
): [number, number, number][] {
  const fallback: [number, number, number][] = [[...from] as [number, number, number], [...to] as [number, number, number]];
  if (graph.nodes.size === 0) return fallback;

  const nearestNode = (p: readonly [number, number, number]): string | null => {
    let bestId: string | null = null;
    let bestDist = Infinity;
    for (const node of graph.nodes.values()) {
      const d = Math.hypot(node.position[0] - p[0], node.position[2] - p[2]);
      if (d < bestDist) { bestDist = d; bestId = node.id; }
    }
    return bestId;
  };

  const fromNode = nearestNode(from);
  const toNode = nearestNode(to);
  if (!fromNode || !toNode) return fallback;
  if (fromNode === toNode) return fallback;

  const graphPath = findWalkPath(graph, fromNode, toNode);
  if (!graphPath) return fallback;

  const near = (a: readonly [number, number, number], b: readonly [number, number, number]): boolean =>
    Math.hypot(a[0] - b[0], a[2] - b[2]) < 0.05;

  const full: [number, number, number][] = [[...from] as [number, number, number]];
  for (const p of graphPath) {
    const last = full[full.length - 1];
    if (!near(last, p)) full.push([...p] as [number, number, number]);
  }
  const toPoint: [number, number, number] = [...to] as [number, number, number];
  if (!near(full[full.length - 1], toPoint)) full.push(toPoint);

  return full.length >= 2 ? full : fallback;
}

/** Position + facing at fractional progress `t` (0..1) along a multi-leg
 * path -- a simplified sibling of Agent.tsx#resolvePathPose (no corner-yaw-
 * slerp blend; a live-agent worker's path is short enough that a small
 * facing snap at a corner is an acceptable, honest simplification for this
 * separate, smaller component). */
export function poseAlongPath(
  waypoints: ReadonlyArray<readonly [number, number, number]>,
  t: number,
): { position: [number, number, number]; facing: number } {
  if (waypoints.length === 0) return { position: [0, 0, 0], facing: 0 };
  if (waypoints.length === 1) return { position: [...waypoints[0]], facing: 0 };
  const legDist: number[] = [];
  let total = 0;
  for (let i = 0; i < waypoints.length - 1; i++) {
    const d = Math.hypot(waypoints[i + 1][0] - waypoints[i][0], waypoints[i + 1][2] - waypoints[i][2]);
    legDist.push(d);
    total += d;
  }
  const targetDist = Math.min(1, Math.max(0, t)) * total;
  let cum = 0;
  let legIndex = legDist.length - 1;
  for (let i = 0; i < legDist.length; i++) {
    if (targetDist <= cum + legDist[i] || i === legDist.length - 1) {
      legIndex = i;
      break;
    }
    cum += legDist[i];
  }
  const d = legDist[legIndex] || 0.0001;
  const localT = Math.min(1, Math.max(0, (targetDist - cum) / d));
  const from = waypoints[legIndex];
  const to = waypoints[legIndex + 1];
  const position: [number, number, number] = [
    from[0] + (to[0] - from[0]) * localT,
    from[1],
    from[2] + (to[2] - from[2]) * localT,
  ];
  const facing = Math.atan2(to[0] - from[0], to[2] - from[2]);
  return { position, facing };
}

// ─── Walk decision (DEFECT 2 fix) ──────────────────────────────────────────

export interface WalkDecisionInput {
  leaving: boolean;
  targetNodeId: string;
  currentNode: string;
  /** Last destination this avatar was actually commanded toward via the
   * ORDINARY (non-leaving) retargeting path -- null before the first one.
   * Never consulted for a leaving decision (see this module's own header
   * for why sharing one latch across both purposes was the bug). */
  seenTarget: string | null;
  /** Whether the one-shot leave-walk (or immediate leave-settle) has
   * already been kicked off for this avatar's CURRENT leaving episode. */
  leaveTriggered: boolean;
  /** TELEPORT FIX (2026-09-15, coordinator probe 20260915T070024Z):
   * whether this avatar is still mid-walk (has not yet physically arrived
   * at `currentNode`) at the moment this decision is made. `currentNode`
   * only ever advances to a walk's destination ON ARRIVAL (LiveAgents.tsx's
   * own useFrame) -- while a walk is in flight it still names the ORIGIN
   * the avatar departed from. Probe evidence: two sessions each walking
   * away from a node had their server-reported target flip back to that
   * SAME origin node before arrival (a real target-classifier flap, not a
   * client bug) -- e.g. tick 298->299 (dt 0.48s): session
   * a06954b44dcea322f was mid-walk toward "ambient-core" (pos [15.24,0],
   * still short of arrival) when its target flipped back to "bay-desk-0",
   * the node `currentNode` had NEVER left (the walk toward ambient-core
   * hadn't completed) -- pos jumped straight to bay-desk-0's stand point
   * [18.30,8.20], 8.75u in 0.48s (18.2 u/s vs. the ~0.7 u/s WALK_SPEED
   * band). Same tick, session:dcc3d160...a8b2 mid-walk toward "bay-desk-0"
   * (pos [17.40,3.47]) had ITS target flip back to "ambient-core"
   * (currentNode, never having left it) and jumped 17.8u in 0.48s (35.4
   * u/s) straight to [-0.03,-0.09]. Without `isWalking`, the `currentNode
   * === targetNodeId` check below can't distinguish "genuinely resting
   * there already" (safe to snap in place) from "mid-flight from there,
   * about to be told to go right back" (must walk, not snap) -- defaulting
   * to false preserves every existing settle/walk call site that only
   * ever decided while at rest. */
  isWalking?: boolean;
}

export type WalkDecision =
  | { action: "none" }
  | { action: "settle"; dest: string; despawn: boolean }
  | { action: "walk"; dest: string; despawn: boolean };

/** Pure decision: given the current inputs, what should this avatar do
 * right now? Called once per relevant prop change (LiveAgents.tsx's own
 * effect) -- never per-frame. `leaving` is checked FIRST and independently
 * of `seenTarget`/ordinary retargeting, so a leave can never be silently
 * absorbed by a coincidental destination-string match (DEFECT 2's exact
 * mechanism). */
export function decideNextWalk(input: WalkDecisionInput): WalkDecision {
  const { leaving, targetNodeId, currentNode, seenTarget, leaveTriggered, isWalking = false } = input;
  if (leaving) {
    if (leaveTriggered) return { action: "none" };
    if (currentNode === ENTRY_NODE_ID && !isWalking) return { action: "settle", dest: ENTRY_NODE_ID, despawn: true };
    return { action: "walk", dest: ENTRY_NODE_ID, despawn: true };
  }
  if (seenTarget === targetNodeId) return { action: "none" };
  // TELEPORT FIX: `currentNode === targetNodeId` alone used to mean "already
  // there, just snap" -- but while mid-walk, `currentNode` still names the
  // ORIGIN of the in-flight walk (it only advances on arrival), so this was
  // true whenever the target flipped back to where the avatar departed from
  // moments ago, snapping it across the map instead of walking it back. Only
  // take the instant-settle shortcut when truly at rest.
  if (currentNode === targetNodeId && !isWalking) return { action: "settle", dest: targetNodeId, despawn: false };
  return { action: "walk", dest: targetNodeId, despawn: false };
}

// ─── Stand-slot ring offset (DEFECT 1 fix) ─────────────────────────────────

export const STAND_RING_RADIUS = 0.9;
// BUBBLE-FIX (2026-09-15): coordinator's real Edge-kiosk capture
// (bench-live-agents-0038.png, 00:38 ET) measured two stacked bubbles at
// y~586px and y~604px -- only ~18px apart, touching/overlapping -- from
// this 0.22u step. ~18px/0.22u implies ~82 px per world-unit at that
// framing; raised to 0.75u (>=~60px separation at the same framing, more
// than 3x the old gap) so 2+ stacked bubbles read as a clearly separated
// short list instead of a smear. UNVERIFIED against a fresh capture by
// this pass (no browser/screenshot tool available here) -- the coordinator
// checks this visually.
export const STAND_BUBBLE_Y_STEP = 0.75;

/** A deterministic point on a small ring around a shared destination node,
 * so agents converging on the SAME zone never occupy the exact same point.
 * `groupIds` should be every agent currently resting/heading at that same
 * node (any stable set); this function sorts them itself so the caller
 * never has to pre-sort, and a group of size <=1 gets a zero offset (no
 * need to nudge a lone occupant off-center). Returns both the XZ offset and
 * the stable slot INDEX (0-based within the sorted group) so a caller can
 * also stagger the bubble height by the same index. Radius is intentionally
 * small (0.9u default) relative to every real zone this maps to (bays are
 * ~12u across, the hub ~13-16u across per layout.ts's own raw-kit
 * dimensions) -- not a collision-checked placement (this module has no
 * room-geometry data at all), but small enough to stay clear of a wall in
 * every zone this task's zone mapping actually uses. */
// ─── Roster reconcile (BUBBLE-FIX, 2026-09-15) ─────────────────────────────
//
// Extracted from LiveAgents.tsx's own `setDisplayed` updater so the exact
// "one id replaced by another id in the SAME poll, same target" scenario the
// coordinator flagged (aa69 dropped + 7252/this session added in one
// /api/hq response) can be proven correct with a plain `node --test`
// (react/three-free, matching this module's own established convention --
// see this file's header). ROOT CAUSE FINDING for that report: this
// reconcile function, taken alone, was ALREADY correct (see the test suite
// alongside this function) -- the real bug was one layer up, in
// app/hq/page.tsx's `sceneData` memo never listing `data.liveAgents` in its
// own inclusion-list key, so a poll where every OTHER listed field happened
// to be unchanged silently kept `LiveAgents`'s own `agents` prop pinned to
// the stale array (fixed in that file, same commit). This function is kept
// pure and exported anyway -- it is the one piece of this reconcile that
// COULD have hidden that class of bug, and now has a regression test
// proving it does not.
export interface RosterReconcileEntry {
  id: string;
  leaving: boolean;
}

/** Diffs `incoming` (this poll's full roster) against `prev` (currently
 * displayed): every incoming id is added or updated via `buildDisplayed`
 * (never marked leaving, even if it was previously -- an agent that
 * reappears has come back); any id in `prev` NOT in `incoming` this poll,
 * and not already marked leaving, is flipped to `leaving: true` in place
 * (only its `leaving` field changes, the rest of its display record is
 * preserved) so its own avatar can walk itself out instead of popping out
 * of existence. Order-independent and safe to call on every poll,
 * including one where `incoming` is empty (transient fetch glitch) or
 * where an id drops out and a DIFFERENT id appears in the very same call --
 * both branches below run unconditionally on their own pass over the data,
 * never on a superseded snapshot. */
export function reconcileLiveAgentRoster<A extends { id: string }, D extends RosterReconcileEntry>(
  prev: ReadonlyMap<string, D>,
  incoming: readonly A[],
  buildDisplayed: (agent: A, existing: D | undefined) => D,
): Map<string, D> {
  const next = new Map(prev);
  const seen = new Set<string>();
  for (const a of incoming) {
    seen.add(a.id);
    next.set(a.id, buildDisplayed(a, next.get(a.id)));
  }
  for (const [id, d] of next) {
    if (!seen.has(id) && !d.leaving) {
      next.set(id, { ...d, leaving: true });
    }
  }
  return next;
}

// ─── Diag-write guard (DIAG-GHOST FIX, 2026-09-15) ─────────────────────────
//
// ROOT CAUSE (coordinator probe 20260915T072901Z, RTX 5080 hardware, 60fps):
// LiveAgents.tsx's useFrame runs, every frame, in this order: (1) the arrival
// check, which on the first frame with progress>=1 calls fireDespawn() --
// synchronously deleting this avatar's window.__hqLiveAgents diag entry via
// LiveAgents.tsx's own handleDespawned, then scheduling the React
// setDisplayed() removal -- and (2) an UNCONDITIONAL tail-end
// `diagStore.set(liveAgentId, {...})` that used to run every frame
// regardless of whether despawn just fired THIS SAME frame. React's actual
// unmount (which stops useFrame from running again) only lands on a LATER
// render, so every frame between "despawn fired" and "React actually
// unmounts" re-wrote the entry that was just deleted -- and the LAST such
// write, from the final frame before unmount, was never cleaned up again
// (nothing else ever calls diagStore.delete for that id). Result: a
// permanent ghost row frozen at the avatar's arrival position forever, even
// though its real React/Three node was already gone -- exactly what probe
// 20260915T072901Z recorded for session a094022ec6e8790ff (leaving at
// ~64.5s, arrived at hub-center ~67.0s, still present with despawn_ms null
// at the window's own end ~248s later).
//
// FIX: gate the tail-end diagStore write on this predicate. Once an avatar
// has despawned (this frame or any earlier one), it must never publish
// another diag snapshot -- the delete that already ran then sticks.
export function shouldWriteLiveAgentDiag(despawned: boolean): boolean {
  return !despawned;
}

// ─── Lane offset (CONVOY-STACK fix, 2026-09-15; CONVOY-STACK v2, same day) ─
//
// ROOT CAUSE (probe 20260915T081521Z/20260915T082114Z, real-GPU headless
// run): every avatar that is already live when the page mounts starts its
// FIRST walk from the exact same point (ENTRY_NODE_ID's own node position --
// see the mount effect that seeds `group.current` there) toward whatever
// findWalkPath returns for its own target. Every one of those real walks
// leaves campus-gate through the SAME first hallway leg (there is only one
// corridor out of the gate -- layout.ts#buildWalkGraph's own T-junction
// wiring), so two or more agents converging on that shared leg get BYTE-
// IDENTICAL waypoint lists for the overlap, and `poseAlongPath` places them
// at the exact same XZ point for the whole shared segment, not just a brief
// coincidence at t=0 (measured: 64/540 ticks with walking agents <0.3u
// apart; all 4 live agents recorded AT [18.25,0] simultaneously mid-walk).
// Standing slots already get their own per-destination ring separation
// (computeStandSlot) -- there was no equivalent separation for the WALKING
// leg of a path.
//
// V1 FIX (this same day, superseded below): a permanent per-id lateral lane
// offset on every interior waypoint, using a CONTINUOUS string-hash mapped
// to [-1, 1]. A follow-up real-GPU probe (20260915T084211Z) found this
// insufficient: two real ids (a93582c1, ab416fc0) hashed to nearly the same
// continuous value (0.01u apart, nowhere near the 0.7u stand-slot bar), and
// separately, every agent present at page load starts its walk in the SAME
// React effect pass -- same wall-clock instant, same waypoints, same speed
// -- so with only a near-identical perpendicular nudge they still render in
// lockstep (identical x every tick; probe measured 54/54 multi-walker ticks
// with a pair under 0.3u).
//
// V2 FIX (this pass): two independent, complementary mechanisms, matching
// the coordinator's own required outcome (any two same-time walkers stay
// >=0.7u apart, the same bar as stand slots, except transiently at a
// corridor crossing):
//   1. STAGGER (see computeBatchStaggerDelays below) -- agents that begin a
//      walk from the same node in the same reconcile batch/poll get a
//      stable-order start delay of STAGGER_DELAY_S each. This is the
//      PRIMARY guarantee: two same-batch walkers on an IDENTICAL straight
//      path segment are exactly `STAGGER_DELAY_S * WALK_SPEED` apart in
//      arc-length at every shared instant (1.05u at the default 1.5s/0.7u/s
//      -- comfortably over the 0.7u bar), by simple algebra: position(t) =
//      poseAlongPath(path, (t - delay)/duration), so two agents on the same
//      path differ in progress by exactly `(delay_j - delay_i)` seconds of
//      travel = `WALK_SPEED * |delay_j - delay_i|` units of arc length. On
//      a STRAIGHT segment, arc-length separation equals Euclidean
//      separation exactly -- the bound is provable there. It is NOT
//      provable through a sharp corner (chord < arc near a bend), which is
//      exactly the "except transiently where corridors cross" carve-out in
//      the required outcome -- not a gap in this fix, a named exception to
//      it.
//   2. DISCRETE LANES (this section, below) -- replaces the V1 continuous
//      hash with a small FIXED set of lane values (LANE_VALUES), so two ids
//      either land on the exact SAME lane (fine -- the stagger's temporal
//      separation still applies whenever they're both genuinely walking) or
//      on one of only 2 other values, at least LANE_STEP_U apart -- never a
//      near-miss. Kept alongside the stagger (not skipped) for two reasons
//      the stagger alone cannot cover: (a) a MID-LIFE retarget (an agent
//      that changes target zone after it has already settled somewhere) has
//      no batch to stagger against -- if it happens to share a corridor leg
//      with another agent already walking, only the lane offset separates
//      them; (b) discrete lanes remove the near-collision failure mode this
//      v1 postmortem is actually about, independent of whatever the
//      stagger does. The endpoints are still never touched (see
//      `applyLaneOffsets`'s own doc) so this cannot perturb the existing
//      stand-slot ring placement (DEFECT 1's own fix) or the despawn
//      destination.
export const LANE_STEP_U = 0.45;
/** Fixed, discrete lane values -- deliberately NOT a continuous range. Two
 * ids either collide exactly (harmless: the stagger's temporal separation
 * still applies to any pair that is actually walking at the same time) or
 * land LANE_STEP_U apart -- there is no near-miss value between these three
 * a hash could land on. */
export const LANE_VALUES: readonly number[] = [0, LANE_STEP_U, -LANE_STEP_U];

/** Deterministic, roster-independent per-id lane INDEX into `LANE_VALUES`
 * (same plain string-hash shape this tree already uses elsewhere for
 * stable derived-from-id values, e.g. KitAgent.tsx's own laneSeed) --
 * `Math.abs` + modulo, so it is always a valid array index regardless of
 * the hash's sign. */
export function laneIndexForId(id: string, laneCount: number = LANE_VALUES.length): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = (h * 31 + id.charCodeAt(i)) | 0;
  }
  return Math.abs(h) % laneCount;
}

/** This id's fixed lane offset (one of `LANE_VALUES`). */
export function laneValueForId(id: string): number {
  return LANE_VALUES[laneIndexForId(id)];
}

/** Nudges every INTERIOR waypoint of `waypoints` (indices 1..length-2)
 * sideways, perpendicular to its local path direction, by this id's fixed
 * `laneValueForId(id)`. The FIRST waypoint (a caller's own live current
 * position -- see LiveAgents.tsx's own `livePos`, so a mid-walk retarget
 * still starts exactly where the avatar visually is) and the LAST waypoint
 * (the caller's own stand-slot-nudged destination, or the raw despawn node
 * position -- either way, a value this function must never further
 * perturb) are always returned unchanged. A waypoint list shorter than 3
 * points has no interior leg at all (a direct one-hop path) and is
 * returned unchanged too -- there is no shared corridor segment to
 * separate. LANE_STEP_U is capped well inside every real corridor's own 4u
 * raw XZ footprint (layout.ts#buildWalkGraph's own corridor.glb/
 * corridor-intersection.glb footprint comment), so a nudged waypoint always
 * stays on walkable floor. */
// CORNER-SAFE LANE OFFSET fix (CONVOY-STACK v13, 2026-09-15, probe
// 20260915T140056Z): the ORIGINAL perpendicular here was derived from the
// single chord `next - prev` spanning EACH waypoint -- correct and
// continuous on an ordinary corridor (consecutive chords barely rotate
// between waypoints), but on a sharp corner or a near-180-degree reversal
// (RETARGET OUT-AND-BACK's own out-and-back shape, findRetargetPath's own
// header above), that chord's direction can itself flip by close to 180
// degrees between one interior waypoint and the next -- its perpendicular
// flips sign right along with it, so the offset point jumps from one side
// of the centerline to the other in a SINGLE waypoint step (the reported
// ~0.71u lateral snap). `poseAlongPath` interpolates LINEARLY between
// waypoints by arc-length progress, so a discontinuity baked into the
// waypoints themselves becomes a real per-frame rendered displacement
// spike the instant a walker's progress crosses that vertex.
//
// FIX: each interior waypoint's offset direction is now the MITER
// BISECTOR of its own INCOMING (`wp - prev`) and OUTGOING (`next - wp`)
// segment directions (their two individual perpendiculars, summed and
// re-normalized) rather than either chord alone -- this varies smoothly as
// the local turn angle varies smoothly, so an ordinary shallow corridor
// bend (where incoming and outgoing directions are close) looks nearly
// identical to the old chord-based result, but a sharp corner no longer
// flips instantly: it rotates continuously through the turn instead. The
// offset MAGNITUDE is always exactly `laneValueForId(id)` (never scaled
// up, satisfying "clamped to LANE magnitude" verbatim -- no miter-length
// blowup at a sharp angle). For a genuine REVERSAL (incoming and outgoing
// directions more than ~150 degrees apart -- the bisector itself becomes
// numerically unstable there, since the two perpendiculars nearly cancel),
// the offset collapses to exactly 0 at that one waypoint: the walker
// passes directly through the centerline at the turn's own apex and
// re-expands to the full lane offset on the segments either side of it,
// rather than attempting any sided offset through a point where "which
// side" isn't well-defined.
const CORNER_REVERSAL_COS_MAX = -Math.cos(Math.PI / 6); // -150 degrees from straight-ahead (cos(180-150)=cos30)

function laneOffsetDirection(prev: readonly [number, number, number], wp: readonly [number, number, number], next: readonly [number, number, number]): [number, number] {
  const inX = wp[0] - prev[0];
  const inZ = wp[2] - prev[2];
  const inLen = Math.hypot(inX, inZ) || 1;
  const outX = next[0] - wp[0];
  const outZ = next[2] - wp[2];
  const outLen = Math.hypot(outX, outZ) || 1;
  const dirInX = inX / inLen;
  const dirInZ = inZ / inLen;
  const dirOutX = outX / outLen;
  const dirOutZ = outZ / outLen;
  const turnCos = dirInX * dirOutX + dirInZ * dirOutZ; // 1 = straight, -1 = full reversal
  if (turnCos < CORNER_REVERSAL_COS_MAX) return [0, 0]; // near-reversal: collapse to the centerline
  const perpInX = -dirInZ;
  const perpInZ = dirInX;
  const perpOutX = -dirOutZ;
  const perpOutZ = dirOutX;
  const bisectorX = perpInX + perpOutX;
  const bisectorZ = perpInZ + perpOutZ;
  const bisectorLen = Math.hypot(bisectorX, bisectorZ);
  if (bisectorLen < 1e-6) return [0, 0]; // the two perpendiculars nearly cancel -- same near-reversal case, guarded independently of the angle check above for numerical safety
  return [bisectorX / bisectorLen, bisectorZ / bisectorLen];
}

export function applyLaneOffsets(
  waypoints: ReadonlyArray<readonly [number, number, number]>,
  id: string,
): [number, number, number][] {
  if (waypoints.length < 3) return waypoints.map((wp) => [...wp] as [number, number, number]);
  const offset = laneValueForId(id);
  return waypoints.map((wp, i) => {
    if (i === 0 || i === waypoints.length - 1) return [...wp] as [number, number, number];
    const [dirX, dirZ] = laneOffsetDirection(waypoints[i - 1], wp, waypoints[i + 1]);
    return [wp[0] + dirX * offset, wp[1], wp[2] + dirZ * offset];
  });
}

// ─── Batch stagger (CONVOY-STACK v2, 2026-09-15) ───────────────────────────
//
// See the lane-offset section above for the full root-cause + design
// writeup. This is mechanism 1 (the PRIMARY separation guarantee): every id
// beginning a walk from the same node in the same reconcile poll (LiveAgents
// .tsx's own "newly added this poll" batch for a fresh spawn, or "newly
// flipped leaving this poll" batch for a mass departure) gets a stable-order
// start delay, so same-batch walkers are never at the same progress along
// an identical path at the same wall-clock instant.
export const STAGGER_DELAY_S = 1.5;

/** Given a batch of ids all beginning a walk from the SAME origin node in
 * the same reconcile poll, returns each id's stable 0-based ORDER within
 * that batch: 0 for the first (sorted) id, 1 for the second, and so on.
 * Sorted lexicographically by id -- the same stable-order convention every
 * other group-based function in this module already uses (see
 * computeStandSlot's own sorted group). Pure and roster-order-independent:
 * calling this with the same set of ids (any input order, duplicates
 * collapsed) always assigns the same order to the same id. The single
 * source of truth both `computeBatchStaggerDelays` (timing) and
 * `computeWaitPoint` (CONVOY-STACK v3's own positioning) build on, so the
 * two can never disagree about which id is "first". */
export function computeBatchOrder(ids: readonly string[]): Map<string, number> {
  const sorted = [...new Set(ids)].sort();
  return new Map(sorted.map((id, i) => [id, i]));
}

/** Given a batch of ids all beginning a walk from the SAME origin node in
 * the same reconcile poll, returns each id's stable stagger delay in
 * seconds: 0 for the first (sorted) id, STAGGER_DELAY_S for the second, and
 * so on -- `computeBatchOrder(ids)` scaled by STAGGER_DELAY_S. */
export function computeBatchStaggerDelays(ids: readonly string[]): Map<string, number> {
  const order = computeBatchOrder(ids);
  return new Map(Array.from(order.entries()).map(([id, i]) => [id, i * STAGGER_DELAY_S]));
}

// ─── Wait point (CONVOY-STACK v3, 2026-09-15) ──────────────────────────────
//
// ROOT CAUSE (probe 20260915T085943Z): computeWaitPoint (v2) placed a
// delayed avatar using `laneValueForId(id)` -- a discrete hash into only 3
// values (LANE_VALUES). Two same-batch ids landing in the SAME hash bucket
// (1-in-3 per pair) get the IDENTICAL wait point -- confirmed live:
// session:5385... and ae892a7f7e3cf5a51, both "spawning" toward
// ambient-core, sat at the exact same [21.65,0.45] at t=7.5s. A per-id HASH
// can never guarantee separation among a KNOWN, already-ordered batch --
// only the batch's own stable ORDER can (the same reasoning that already
// drove `computeBatchStaggerDelays` away from a hash for the stagger delay
// itself).
//
// FIX: derive the wait point from `batchIndex` (this id's own
// computeBatchOrder position), not from a hash of its id at all. A
// zigzagging LATERAL lane (perpendicular to the corridor, alternating
// +/-: 0, +1, -1, +2, -2, ... x WAIT_LANE_STEP_U) covers the first
// WAIT_LANE_COUNT batch members with GUARANTEED >=WAIT_LANE_STEP_U pairwise
// separation (every pairwise gap between two of the 5 positions
// {0,+-0.73,+-1.46} is an exact multiple of 0.73u -- verified by the
// pairwise-difference table in this pass's own test file) while staying
// within the gate's own +-1.47u opening (2*WAIT_LANE_STEP_U = 1.46 < 1.47,
// so even the two most-extreme lanes never clip a wall). A batch bigger
// than WAIT_LANE_COUNT (the roster caps at 8; more than 5 concurrent
// waiters is a rare, extreme case) overflows into an extra ROW, offset
// backward along the corridor's own axis (away from `next`, i.e. away from
// the destination -- still on the walkable corridor floor, never off the
// gate node) by WAIT_ALONG_STEP_U per row. Because `perp` and `dir` are
// orthogonal unit vectors, two points that differ in EITHER lane OR row (or
// both) are separated by at least min(WAIT_LANE_STEP_U, WAIT_ALONG_STEP_U)
// -- see this pass's own test file for the full pairwise proof across every
// index pair in an 8-member batch.
export const WAIT_LANE_STEP_U = 0.73; // 2x stays inside the gate's own +-1.47u opening
export const WAIT_LANE_COUNT = 5; // positions 0, +-1, +-2 (all within +-1.47u)
export const WAIT_ALONG_STEP_U = 0.8; // overflow-row spacing, backward along the corridor

/** This batch index's lateral (perpendicular) lane offset: a zigzag
 * 0, +1, -1, +2, -2, ... pattern in units of WAIT_LANE_STEP_U, cycling every
 * WAIT_LANE_COUNT indices (see this section's own header for the pairwise
 * separation proof). */
export function waitLaneOffsetForIndex(batchIndex: number, laneCount: number = WAIT_LANE_COUNT): number {
  const lane = ((batchIndex % laneCount) + laneCount) % laneCount;
  if (lane === 0) return 0;
  const magnitude = Math.ceil(lane / 2);
  const sign = lane % 2 === 1 ? 1 : -1;
  return sign * magnitude * WAIT_LANE_STEP_U;
}

/** This batch index's along-path "row" offset (0 for the first
 * WAIT_LANE_COUNT indices, 1 for the next WAIT_LANE_COUNT, ...), in units of
 * WAIT_ALONG_STEP_U -- see this section's own header. */
export function waitAlongOffsetForIndex(batchIndex: number, laneCount: number = WAIT_LANE_COUNT): number {
  return Math.floor(Math.max(0, batchIndex) / laneCount) * WAIT_ALONG_STEP_U;
}

/** The visual "waiting for my stagger slot" point: `origin` nudged
 * perpendicular to the direction toward `next` (the first real hallway
 * waypoint the avatar will walk toward once its delay elapses) by this
 * avatar's own `batchIndex`-derived lane, and backward along that same
 * direction by its own row (see `waitLaneOffsetForIndex`/
 * `waitAlongOffsetForIndex` above for the full derivation and separation
 * proof -- CONVOY-STACK v3, replacing v2's id-hash approach, which could not
 * guarantee separation within an already-known, already-ordered batch).
 * Used only to render a delayed avatar's stationary pose -- without this,
 * every same-batch avatar waiting out its stagger would render stacked
 * exactly on the shared origin node (the first waypoint is deliberately
 * left unoffset by `applyLaneOffsets` for path-continuity reasons -- see
 * that function's own doc). Falls back to `origin` unmodified if `origin`
 * and `next` coincide (no real direction to be perpendicular to). */
export function computeWaitPoint(
  origin: readonly [number, number, number],
  next: readonly [number, number, number],
  batchIndex: number,
): [number, number, number] {
  const dx = next[0] - origin[0];
  const dz = next[2] - origin[2];
  const len = Math.hypot(dx, dz);
  if (len < 1e-9) return [...origin] as [number, number, number];
  const dirX = dx / len;
  const dirZ = dz / len;
  const perpX = -dirZ;
  const perpZ = dirX;
  const lateral = waitLaneOffsetForIndex(batchIndex);
  const along = waitAlongOffsetForIndex(batchIndex);
  return [
    origin[0] + perpX * lateral - dirX * along,
    origin[1],
    origin[2] + perpZ * lateral - dirZ * along,
  ];
}

export function computeStandSlot(
  groupIds: readonly string[],
  id: string,
  radius: number = STAND_RING_RADIUS,
): { offset: [number, number]; index: number; groupSize: number } {
  const sorted = [...new Set(groupIds)].sort();
  const index = Math.max(0, sorted.indexOf(id));
  const groupSize = Math.max(1, sorted.length);
  if (groupSize <= 1) return { offset: [0, 0], index: 0, groupSize };
  const angle = (2 * Math.PI * index) / groupSize;
  return { offset: [Math.cos(angle) * radius, Math.sin(angle) * radius], index, groupSize };
}

// ─── Stable stand-slot assignment (CONVOY-STACK v5, 2026-09-15) ───────────
//
// ROOT CAUSE (all-state displacement audit, probe 20260915T095436Z):
// `computeStandSlot` (above) derives BOTH an id's index AND the angle's own
// denominator (`groupSize`) from the CURRENT sorted membership of a zone --
// so when ANY resident of that zone arrives or departs, every OTHER
// resident's index and/or angle can shift, even though THEY did not move.
// Combined with CONVOY-STACK v3's own per-frame correction (LiveAgents.tsx
// useFrame, `if (phase.current === "working" ...) { standPointFor(...) }`,
// which exists specifically to apply a CHANGED offset instantly, every
// frame, to keep two avatars from colliding) this produces a real, visible
// SNAP the instant a sibling's membership in the SAME zone changes -- the
// reported 0.90u jumps (0.90 == the OLD STAND_RING_RADIUS) are exactly
// `computeStandSlot`'s own angle recomputing around a new groupSize
// denominator.
//
// FIX: STABLE slot assignment, tracked by the reconcile layer
// (LiveAgents.tsx's own `slotAssignmentsRef`) rather than re-derived from
// scratch every render. `updateStableSlotAssignments` is the pure reducer:
// given the PREVIOUS per-zone assignment and the CURRENT membership, an id
// that was ALREADY assigned to a zone keeps that EXACT index for as long as
// it stays a member of that SAME zone -- no renumbering, ever, regardless
// of who else joins or leaves. A newcomer (first appearance in a zone, or a
// retarget from a different zone -- its old zone's slot is simply absent
// from that zone's next membership, and therefore freed) takes the LOWEST
// index not currently in use in that zone. A departure (id absent from a
// zone's membership this call) frees its index without touching anyone
// else's.
//
// `stableSlotOffset` derives the on-screen offset from the index ALONE,
// against a FIXED capacity (STAND_SLOT_CAPACITY, never the current
// membership size) -- this is the second half of the stability guarantee:
// even `computeStandSlot`'s OWN index-preservation would still shift an
// existing resident's ANGLE if the angle's denominator (groupSize) kept
// changing as siblings joined. A fixed denominator means an id's angle is a
// pure function of its own (now-stable) index -- it can only ever be
// recomputed to the SAME value.
export const STAND_SLOT_CAPACITY = 8; // matches the live-agent roster cap (lib/hq-agents.ts)
// 2*R*sin(pi/STAND_SLOT_CAPACITY) must stay >=0.7u for the worst case (two
// ADJACENT indices on the full 8-slot ring): 2*0.95*sin(pi/8) = 0.727u.
export const STABLE_STAND_RADIUS = 0.95;

/** This STABLE index's on-screen [x,z] offset, on a ring of `capacity`
 * evenly-spaced positions -- unlike `computeStandSlot`, the denominator is
 * the FIXED `capacity`, never the current occupant count, so this can only
 * ever return the SAME value for the SAME index (see this section's own
 * header for why that fixed-denominator property is required, not just the
 * index stability). */
export function stableSlotOffset(
  index: number,
  radius: number = STABLE_STAND_RADIUS,
  capacity: number = STAND_SLOT_CAPACITY,
): [number, number] {
  const angle = (2 * Math.PI * index) / Math.max(1, capacity);
  return [Math.cos(angle) * radius, Math.sin(angle) * radius];
}

/** Pure reducer for the stable per-zone slot assignment described above.
 * `membership` is this reconcile's CURRENT zone -> resident-ids map (every
 * currently-displayed id, grouped exactly as LiveAgents.tsx's own
 * `standSlots` memo already groups them -- by EFFECTIVE destination,
 * ENTRY_NODE_ID while leaving, targetNodeId otherwise). Returns a brand-new
 * Map-of-Maps (never mutates `prev`, per this tree's own immutability
 * convention) where each zone's assignment is rebuilt from that zone's
 * OWN prior assignment (if any) plus this round's membership -- a zone with
 * no residents this round is simply absent from the result (nothing to
 * leak). Deterministic given the same (prev, membership) pair: a tie among
 * multiple simultaneously-new ids in one zone is broken by sorting their
 * ids, the same stable-order convention every other batch function in this
 * module already uses. */
export function updateStableSlotAssignments(
  prev: ReadonlyMap<string, ReadonlyMap<string, number>>,
  membership: ReadonlyMap<string, readonly string[]>,
): Map<string, Map<string, number>> {
  const next = new Map<string, Map<string, number>>();
  for (const [zoneKey, rawIds] of membership) {
    const uniqueIds = [...new Set(rawIds)];
    const prevZone = prev.get(zoneKey);
    const zoneAssign = new Map<string, number>();
    const used = new Set<number>();
    // Keep every id already assigned to THIS zone at its EXACT prior index.
    for (const id of uniqueIds) {
      const priorIndex = prevZone?.get(id);
      if (priorIndex !== undefined) {
        zoneAssign.set(id, priorIndex);
        used.add(priorIndex);
      }
    }
    // Newcomers (genuinely new to this zone this round) take the lowest
    // free index, in sorted-id order for a deterministic tie-break.
    const newcomers = uniqueIds.filter((id) => !zoneAssign.has(id)).sort();
    for (const id of newcomers) {
      let idx = 0;
      while (used.has(idx)) idx++;
      zoneAssign.set(id, idx);
      used.add(idx);
    }
    next.set(zoneKey, zoneAssign);
  }
  return next;
}

// ─── Follow distance / car-following (CONVOY-STACK v6, 2026-09-15) ────────
//
// ROOT CAUSE (walker_separation FAIL, probe 20260915T101532Z): 66/147
// multi-walker ticks (44.9%) under the required 0.7u bar, 64 of them ONE
// pair (session:5385..., adf9d977a499f1486), both leaving toward
// campus-gate, that walked the ENTIRE ~32s shared corridor 0.18u apart in
// the SAME lane (z=-0.45 for both). The lane is still chosen from a
// per-id hash (LANE_VALUES, 3 buckets -- see `laneValueForId` above) --
// two ids landing in the same bucket (1-in-3 per pair) get IDENTICAL lane
// offsets on the SAME corridor, and CONVOY-STACK v2/v3's batch stagger only
// covers agents starting a walk from the SAME node in the SAME reconcile
// poll -- two leavers departing from DIFFERENT stand slots (different
// zones, or the same zone at different moments) merge onto the shared
// gate-bound corridor with no timing relationship to each other at all, so
// the stagger cannot separate them. The v5 build only "passed" because
// those two particular ids happened to hash to different lanes -- a
// coincidence, not a guarantee.
//
// FIX: FOLLOW DISTANCE (car-following), the general solution for a shared
// corridor -- independent of lane assignment or batch timing, this holds
// for ANY two walkers converging on the same lane at any time. Each
// avatar, every frame, checks whether another currently-walking avatar
// heading the SAME direction, toward the SAME destination, and in
// (approximately) the SAME lane is AHEAD of it; if the gap to that walker
// is under FOLLOW_GAP_U, this avatar's forward advance for the frame is
// capped so the gap never drops below FOLLOW_GAP_U -- it slows or holds,
// never teleports, never reverses (LiveAgents.tsx's own `applyFollowCap`
// call site, in useFrame, is where this is wired to the live per-frame
// position update).
//
// SIMPLIFICATION, stated plainly rather than left implicit: the spec's own
// language ("whose current segment is the same graph edge") describes a
// graph-edge-id-based check; `findWalkPath`'s own return type here is a
// plain world-space waypoint list (positions only, no retained node ids --
// see that function's own header), and threading node ids through the
// whole per-avatar path/lane-offset pipeline to build a true edge-id match
// would be a materially larger change. This implementation instead detects
// "same corridor, same direction, ahead-or-level" purely geometrically --
// same eventual destination (`destKey`, a cheap pre-filter: every leaving
// avatar already shares ENTRY_NODE_ID, exactly the original bug's own
// shape), heading vectors nearly parallel (FOLLOW_HEADING_COS_MIN -- this
// is ALSO the head-on-pass guardrail: two walkers moving in roughly
// OPPOSITE directions, e.g. one arriving and one leaving, never satisfy
// this and so never yield to each other, by construction, regardless of
// how close they pass), and Euclidean proximity.
//
// CONVOY-STACK v7 (2026-09-15, probe 20260915T113020Z): v6's own first cut
// additionally required a small LATERAL offset from self's own heading
// line (a "same lane" check) before two walkers would follow each other at
// all -- but LANE_VALUES (0, +-0.45u) puts adjacent lanes only 0.45u apart,
// BELOW the 0.7u bar, and two walkers in ADJACENT lanes (a legitimate,
// frequent outcome of the lane hash) never triggered following at all,
// so they walked the entire corridor ABREAST, 0.45-0.68u apart -- the v6
// build only "passed" its own narrower probe runs by lane-assignment luck,
// the same class of false confidence v6 itself replaced (the id-hash
// lane's own near-miss problem, one level up).
//
// FIX (coordinator's own option (A), chosen because it guarantees the bar
// regardless of geometry -- a lane-based tolerance is only ever as good as
// the lane math it depends on, and option (B), widening the lanes, still
// requires per-corridor floor-width verification that shifts with every
// future layout change): drop the lateral/lane check entirely. A walker
// now counts as "the car ahead" whenever it is ahead-or-level (the
// existing `forward >= 0` tie-break, unchanged) AND currently within
// FOLLOW_GAP_U of `self` in straight Euclidean distance -- regardless of
// which lane either one is nominally on. The practical effect is
// single-file-on-approach: two walkers converging within the gap radius
// fall into a queue (one slows until the gap opens along its OWN heading,
// exactly `applyFollowCap`'s existing mechanism, unchanged) rather than
// two parallel, permanently-too-close lanes. Lane assignment
// (`laneValueForId`/`applyLaneOffsets`) is kept for its own cosmetic
// value (a converging queue still reads as "lanes" visually thanks to the
// path-level nudge) but no longer does any of the SEPARATION-GUARANTEE
// work -- that is now this function's job alone, unconditionally.
export const FOLLOW_GAP_U = 0.8;
export const FOLLOW_HEADING_COS_MIN = 0.7; // ~<=45 degrees off-heading still counts as "the same direction"; opposite-direction (head-on) pairs sit at dot ~= -1, far below this, and so never yield to each other -- see this section's own header

export interface WalkerSnapshot {
  id: string;
  /** World-space XZ position. */
  position: readonly [number, number];
  /** Unit-length XZ heading (facing direction), matching poseAlongPath's
   * own `facing` convention (atan2(dx, dz), i.e. this vector is
   * [sin(facing), cos(facing)]). */
  heading: readonly [number, number];
  /** This walker's current walk destination (graph node id) -- the cheap
   * "are we even converging on the same place" pre-filter. */
  destKey: string;
  /** MUTUAL-HOLD DEADLOCK fix (v12): this walker's own progress fraction
   * (0..1) along its CURRENT path, as of the frame this snapshot was taken
   * -- optional and defaults to 0 when absent (every pre-v12 snapshot
   * construction, in this file's own tests and any other caller, stays
   * valid with no changes required) so `resolveMutualHoldWinner` below has
   * a deterministic "who's further along" signal without requiring every
   * caller to be touched. See that function's own header for why this is
   * the precedence signal, not e.g. distance-to-destination. */
  progress?: number;
}

export interface CarAheadResult {
  other: WalkerSnapshot;
  /** World-space distance `other` is ahead of `self`, projected onto
   * self's own heading (always >= 0 -- see findCarAhead's own tie-break
   * for the only case this is computed as exactly 0). */
  forwardGap: number;
}

/** Finds the nearest "car ahead" of `self` among `others` -- see this
 * section's own header for the full geometric definition and the v6->v7
 * change (same `destKey`, near-parallel heading, ahead-or-level, and
 * -- v7 -- within FOLLOW_GAP_U in straight Euclidean distance,
 * REGARDLESS of lane). Ties at (near) equal forward progress are broken
 * deterministically by id -- the lexicographically LARGER id treats the
 * smaller as "ahead" -- so exactly one of a tied pair ever yields, never
 * both (which could otherwise have both slow down for nothing, or neither
 * yield at all). Returns null if nobody currently qualifies -- in
 * particular, two walkers heading in roughly OPPOSITE directions (a
 * head-on pass) never qualify, no matter how close, because
 * `headingDot < FOLLOW_HEADING_COS_MIN` rejects them first. */
export function findCarAhead(self: WalkerSnapshot, others: readonly WalkerSnapshot[]): CarAheadResult | null {
  let best: CarAheadResult | null = null;
  for (const other of others) {
    if (other.id === self.id) continue;
    if (other.destKey !== self.destKey) continue;
    const headingDot = self.heading[0] * other.heading[0] + self.heading[1] * other.heading[1];
    if (headingDot < FOLLOW_HEADING_COS_MIN) continue;
    const dx = other.position[0] - self.position[0];
    const dz = other.position[1] - self.position[1];
    const forward = dx * self.heading[0] + dz * self.heading[1];
    const isAhead = forward > 1e-6 || (Math.abs(forward) <= 1e-6 && self.id > other.id);
    if (!isAhead) continue;
    // v7: Euclidean proximity, not lane membership -- an adjacent-lane
    // walker (0.45u lateral, LANE_VALUES's own step) that is level with or
    // just ahead of self is exactly the reported bug (two walkers abreast,
    // 0.45-0.68u apart, NEVER triggering the v6 lane-tolerance check) and
    // must qualify here.
    const euclideanDist = Math.hypot(dx, dz);
    if (euclideanDist >= FOLLOW_GAP_U) continue;
    const forwardGap = Math.max(0, forward);
    if (!best || forwardGap < best.forwardGap) best = { other, forwardGap };
  }
  return best;
}

// ─── Mutual-hold deadlock + starvation guard (CONVOY-STACK v12, 2026-09-15) ─
//
// ROOT CAUSE (long_holds, probe 20260915T130317Z): findCarAhead's own
// "ahead-or-level, near-parallel heading, within FOLLOW_GAP_U" test is
// evaluated INDEPENDENTLY from each walker's own point of view. Two walkers
// converging from different stand slots onto the SAME first corridor leg
// (a batch leave through a shared zone's own hub-center ring, the probe's
// own exact shape) can each have a POSITIVE forward projection of the
// other -- i.e. BOTH findCarAhead(A, [B]) and findCarAhead(B, [A]) return
// non-null, genuinely (not a near-zero tie; each really does read the
// other as "ahead-or-level" from its own heading). applyFollowCap then
// caps BOTH of them below FOLLOW_GAP_U, using the OTHER's one-frame-stale,
// itself-also-frozen registry entry -- a stable mutual lock, confirmed by
// the probe as a genuine ~36s hold, not a render pause (this file's own
// v11 pause-clamp fix does not touch this: neither avatar had a delta
// anomaly, both simply capped each other to zero net advance every real
// frame). The EXISTING id tie-break inside findCarAhead only ever fires
// at an EXACT forward===0 tie -- it was never meant to, and cannot, resolve
// a genuine BOTH-see-each-other-ahead configuration where forward is
// meaningfully positive on both sides.
//
// FIX (deadlock-proof by construction, not a timeout-only band-aid):
// 1. PRECEDENCE (`resolveMutualHoldWinner`): whenever `findCarAhead(self,
//    others)` returns non-null AND `findCarAhead(carAhead.other,
//    [self])` ALSO returns non-null (i.e. each treats the other as ahead
//    -- reusing findCarAhead itself for the reverse check, rather than a
//    parallel geometry function, keeps this single-source-of-truth and
//    automatically symmetric even off a one-frame-stale snapshot of
//    either side), exactly one of the pair is chosen to proceed: whichever
//    is FURTHER ALONG its own path (`progress`, this file's own
//    `WalkerSnapshot` addition -- closer to being out of everyone's way),
//    tie-broken by the lexicographically LOWER id (mirrors findCarAhead's
//    own tie-break convention). The loser's own `carAhead` is left
//    unchanged (it still yields, normally); the winner's own `carAhead` is
//    set to null by the CALLER (LiveAgents.tsx's useFrame) for that frame,
//    i.e. the winner proceeds exactly as if nothing were ahead of it --
//    this is also what satisfies requirement 3 ("the one proceeding
//    ignores yielders that are yielding to it"): a walker that IS the
//    other's own registered car-ahead never gets capped by that same
//    other walker once it has won precedence against it.
// 2. STARVATION (`shouldBreakStarvation`): a general safety net for any
//    OTHER long-hold shape this precedence rule doesn't cover (e.g. a
//    genuinely one-directional follow against a car ahead that is itself
//    stuck for unrelated reasons) -- if a walker has been actively capped
//    (findCarAhead non-null AND its applied distance did not advance) for
//    more than STARVATION_HOLD_S of its own pause-immune sim time, it
//    stops waiting and proceeds at full (uncapped) speed for that frame.
//    The per-frame INCREMENTAL distance accumulation (v6, unmodified) means
//    this is still bounded by WALK_SPEED*dt per frame -- never a snap, only
//    a walker that finally stops waiting.

export const STARVATION_HOLD_S = 3; // sim seconds -- generous enough that ordinary, resolving follow-caps never trip it, tight enough to bound worst-case hold time well under the probe's own ~36s observed stall

/** Deterministically resolves which of two MUTUALLY-ahead walkers proceeds
 * (see this section's own header for when this applies): whichever has the
 * HIGHER `progress` (further along its own path) wins; a progress tie (or
 * either/both snapshots predating the v12 `progress` field, defaulting to
 * 0) falls back to the lexicographically LOWER id -- mirrors
 * findCarAhead's own tie-break convention. Pure and symmetric: both
 * callers, even reading a one-frame-stale copy of one side, always compute
 * the identical winner from the same two snapshots. */
export function resolveMutualHoldWinner(a: WalkerSnapshot, b: WalkerSnapshot): string {
  const pa = a.progress ?? 0;
  const pb = b.progress ?? 0;
  if (pa !== pb) return pa > pb ? a.id : b.id;
  return a.id < b.id ? a.id : b.id;
}

/** True once a walker has been actively held (capped with no net advance)
 * for longer than `thresholdS` of its own accumulated sim time -- past
 * this point LiveAgents.tsx's own useFrame stops applying the follow cap
 * for that frame regardless of cause, rather than risk an unbounded wait.
 * See this section's own header for the full "why a timeout-only guard is
 * still needed even with the mutual-hold precedence fix" reasoning
 * (precedence only resolves the specific mutual-ahead shape; this covers
 * everything else). */
export function shouldBreakStarvation(stalledS: number, thresholdS: number = STARVATION_HOLD_S): boolean {
  return stalledS > thresholdS;
}

/** GATE CO-SPAWN OVERLAP fix (CONVOY-STACK v10, 2026-09-15, probe
 * 20260915T131840Z): true whenever some OTHER currently-walking avatar
 * (`selfId` itself is always excluded) sits within `gapU` of `point` in
 * straight Euclidean distance. Used to hold a freshly-spawning avatar at a
 * wait-lane point rather than letting it start walking from the gate node
 * itself while another walker is still right there.
 *
 * ROOT CAUSE this exists to cover: `computeBatchStaggerDelays` (this file,
 * above) is computed separately per RECONCILE POLL over only that poll's
 * own newly-spawning ids -- by design, so a later poll's roster diff can't
 * retroactively renumber an earlier poll's already-running stagger. Two
 * avatars that spawn in DIFFERENT (even directly consecutive) polls each
 * land at batch-order index 0 of their own poll and so both get delay 0 --
 * correct in isolation, but it means neither one carries any memory of the
 * OTHER poll's spawn, so LiveAgents.tsx's own decision effect sends both
 * straight into their walk from the identical unoffset gate point
 * (`wp[0] = livePos = entryPos` when there is no stagger delay to hold
 * against) with zero relative separation. `findCarAhead`'s own follow-cap
 * would normally resolve this once both are registered and moving, but it
 * cannot prevent the INITIAL overlap -- by the time both have published a
 * frame to `walkerFollowRegistry`, they have already rendered on top of
 * each other for at least that first frame, and if their real-world spawn
 * moments are close enough, they can stay in a near-perfect lockstep tie
 * for the whole corridor (findCarAhead's own tie-break, `self.id >
 * other.id`, does resolve *which* of the two yields, but only once there is
 * something measurable to resolve -- it can't retroactively un-overlap a
 * frame that already rendered both at the same point).
 *
 * FIX (this function + its LiveAgents.tsx call site): pre-empt the overlap
 * entirely rather than relying on the reactive follow-cap to clean it up --
 * a spawning avatar checks, every frame it hasn't yet started moving,
 * whether the gate point is still occupied by anyone else currently
 * walking, and holds at its own wait-lane point (the existing
 * `computeWaitPoint` zigzag, reused verbatim) for as long as it is. This is
 * independent of, and in addition to, the existing per-poll stagger delay
 * -- it is the general "queue at the gate" mechanism the per-poll stagger
 * was never able to be on its own, since it has no visibility across polls. */
export function isPointOccupied(
  point: readonly [number, number],
  selfId: string,
  others: readonly WalkerSnapshot[],
  gapU: number = FOLLOW_GAP_U,
): boolean {
  for (const other of others) {
    if (other.id === selfId) continue;
    const dx = other.position[0] - point[0];
    const dz = other.position[1] - point[1];
    if (Math.hypot(dx, dz) < gapU) return true;
  }
  return false;
}

// HQ-PAUSE TELEPORT fix (CONVOY-STACK v11, 2026-09-15, probe
// 20260915T124705Z): r3f's `useFrame(state, delta)` reports `delta` as the
// REAL wall-clock gap since the previous frame -- almost always one
// vsync-ish tick (~1/60s), but UltraCanvasRoot's own GPU-YIELD pause
// (`paused = gaming || hidden || brainBusy`, that file's own logic, NOT
// touched here) can suspend the frameloop entirely for real seconds at a
// time (the probe's own case: a 28.6s Station local-model run). The FIRST
// `useFrame` tick after resume then reports a `delta` equal to the WHOLE
// suspended wall-clock gap (~14s in the probe's own sample window), not one
// frame's worth -- every piece of this file's own per-frame accounting that
// multiplies `delta` by a rate (WALK_SPEED, the sidestep ramp rate, the
// leave-timeout extension accumulator) or that stamps/reads a raw wall-clock
// timestamp (`performance.now()`, `state.clock.elapsedTime`) for a
// SCHEDULE/threshold check treats that one abnormal frame as if the avatar
// had been walking/waiting/leaving continuously through the whole gap --
// exactly the reported 10.72u/9.74u jumps (`WALK_SPEED * delta` with
// `delta` ~= 14s instead of ~1/60s) and the risk of a leave hard-timeout
// firing on resume for an avatar that was never actually stalled, just
// paused along with everything else.
//
// FIX: every piece of LiveAgents.tsx's own per-frame accounting is driven
// off ONE shared per-avatar accumulated "sim time" (see that file's own
// `simTimeRef`), which itself only ever advances by this function's
// CLAMPED delta each real frame -- never the raw one. A real pause of any
// length is therefore indistinguishable, from every consumer's point of
// view, from a single slightly-slow frame (`MAX_FRAME_DT_S` worth): motion
// resumes from the exact frozen pose at normal speed, wait/stagger
// schedules and the leave hard-timeout simply don't advance during the
// gap (so a long pause can never force-despawn an agent that was mid-walk,
// nor let a wait/stagger delay silently expire during the freeze), and the
// avatar's own effective arrival time is pushed back by exactly the paused
// duration -- never skipped ahead.
export const MAX_FRAME_DT_S = 0.1; // ~6 frames' worth at 60fps -- generous headroom over a normal tick, small enough that no consumer can mistake a real pause for continuous motion/elapsed time

/** Clamps a raw `useFrame` `delta` (or any other single-frame wall-clock
 * gap) to `maxDt` before it is used for ANY rate-based accounting (a
 * distance, a ramp, an accumulator) or before it is added into an
 * accumulated "sim time" used for a schedule/threshold check -- see this
 * section's own header for the full root-cause writeup. Non-finite or
 * negative input (a defensive guard against a malformed/mocked clock) is
 * treated as 0, never NaN/negative propagation into a distance or timer. */
export function clampFrameDelta(delta: number, maxDt: number = MAX_FRAME_DT_S): number {
  if (!Number.isFinite(delta) || delta <= 0) return 0;
  return Math.min(delta, maxDt);
}

/** Given this avatar's UNCAPPED candidate cumulative distance-traveled for
 * this frame (elapsed*WALK_SPEED, before any following logic), the
 * distance it was ACTUALLY at as of the previous frame
 * (`prevAppliedDistance` -- the "never reverse" floor), and the car ahead
 * (if any, from `findCarAhead`), returns this frame's ACTUAL distance to
 * advance to. If there is no car ahead, or the gap already clears
 * `gapU`, this is just the candidate (never less than `prevAppliedDistance`
 * -- time only moves forward). If the gap is under `gapU`, the candidate is
 * reduced by exactly the shortfall (`gapU - forwardGap`) -- a local-linear
 * approximation that is exact for a straight corridor segment and a very
 * close approximation for the small per-frame deltas this runs at -- and
 * still never allowed to fall below `prevAppliedDistance` (holds in place
 * rather than reversing if the car ahead is already too close to fully
 * satisfy the gap this frame). */
export function applyFollowCap(
  candidateDistance: number,
  prevAppliedDistance: number,
  carAhead: CarAheadResult | null,
  gapU: number = FOLLOW_GAP_U,
): number {
  if (!carAhead || carAhead.forwardGap >= gapU) {
    return Math.max(prevAppliedDistance, candidateDistance);
  }
  const reduction = gapU - carAhead.forwardGap;
  return Math.max(prevAppliedDistance, candidateDistance - reduction);
}

// ─── Keep-right passing / head-on sidestep (CONVOY-STACK v8, 2026-09-15) ──
//
// ROOT CAUSE (walker_separation FAIL by rule but min 0.07u, probe
// 20260915T114713Z): findCarAhead's own FOLLOW_HEADING_COS_MIN gate
// (v6/v7) correctly excludes head-on pairs from the follow-distance
// mechanism (which is only meaningful for same-direction traffic) --
// exactly what prevents the deadlock the coordinator flagged as a risk.
// But excluding them from FOLLOW also means NOTHING makes two opposite-
// direction walkers avoid each other at all -- two avatars in the SAME
// lane, heading toward each other, walk straight through one another
// (observed: 0.65u apart, then 0.07u one tick later, i.e. mid-pass-through).
//
// FIX: KEEP-RIGHT PASSING. When `findOncoming` detects another walker
// heading roughly OPPOSITE (headingDot < HEAD_ON_COS_MAX) and within
// FOLLOW_GAP_U laterally, this avatar's own lateral offset (perpendicular
// to its CURRENT heading, toward its OWN right -- `rightOf`) ramps toward
// SIDESTEP_TARGET_U at a bounded rate (`rampSidestepOffset`, never a snap)
// -- and back toward 0 once no longer needed, the same ramp, same rate. On
// a straight corridor with two walkers starting in the SAME lane (the
// reported bug's own shape), each shifting SIDESTEP_TARGET_U (0.4u) toward
// its own right moves them in OPPOSITE lateral directions (heading
// opposite implies "right" points opposite ways too), clearing a combined
// 2*SIDESTEP_TARGET_U = 0.8u = FOLLOW_GAP_U. This is deliberately a
// PERPENDICULAR, render-time-only nudge on top of the existing path
// interpolation -- never touches `progress`/distance-traveled accounting
// (LiveAgents.tsx's own useFrame adds it to the already-computed path
// position, the same "offset on top of the interpolated pose" shape
// applyLaneOffsets/computeWaitPoint already use elsewhere in this file) --
// so it can never interact with arrival, following, or the mid-walk
// slot-drift fix.
//
// NARROW-CORRIDOR FALLBACK: this module has no true per-edge corridor-
// width metadata (see applyLaneOffsets's own header on why threading real
// graph-edge identity through the pipeline was rejected as a materially
// larger change back in v6 -- the same tradeoff applies here). Rather than
// fabricate a width figure, the caller (LiveAgents.tsx) passes through its
// OWN already-computed, already-trusted `walkable` state (true only when
// `findWalkPath` found a REAL graph route, never the straight-line
// fallback) as `corridorTrusted`. When untrusted, `computeSidestepPlan`
// never offsets either walker sideways at all -- instead the
// LEXICOGRAPHICALLY LOWER id (deterministic, no coordination needed) is
// told to pause (hold its forward advance) until the oncoming walker
// clears, exactly the "lower-id walker pausing briefly at a wider point"
// the spec asked for, minus the "wider point" framing this module has no
// way to locate -- a documented, honest simplification, not a fabrication.
export const HEAD_ON_COS_MAX = -0.5; // heading dot below this = "roughly opposite direction"
export const SIDESTEP_TARGET_U = 0.4; // each walker's own shift; 2x clears FOLLOW_GAP_U on a shared straight lane
export const SIDESTEP_RATE_U_PER_S = 0.6; // bounded lateral speed -- gradual ramp, never a snap
export const SIDESTEP_DETECTION_RADIUS_U = 2.5; // Euclidean range to start/keep reacting to an oncoming walker, well ahead of an actual collision

/** This heading's own "right" direction (a walker facing `heading` sees
 * this vector pointing to their right) -- rotates `heading` by -90 degrees
 * in the XZ plane. Two walkers heading in roughly opposite directions have
 * roughly OPPOSITE "right" vectors too, which is exactly what makes
 * "each shift toward your own right" separate a head-on pair rather than
 * push them the same way. */
export function rightOf(heading: readonly [number, number]): [number, number] {
  return [heading[1], -heading[0]];
}

/** Finds the nearest (by lateral distance) walker `self` is on a head-on
 * approach with: heading roughly OPPOSITE (`headingDot < HEAD_ON_COS_MAX`),
 * within `SIDESTEP_DETECTION_RADIUS_U` in straight Euclidean distance (both
 * approaching AND just-passed pairs qualify -- the ramp-back-to-0 after
 * passing is what makes the avatar drift back to its lane, not an early
 * cutoff here), and within `FOLLOW_GAP_U` laterally (already-clear lanes
 * need no sidestep at all). Returns null if nobody qualifies. Unlike
 * `findCarAhead`, this does NOT filter by `destKey` -- an arriving and a
 * leaving avatar realistically target different nodes, and a head-on pass
 * must still avoid them. */
export function findOncoming(self: WalkerSnapshot, others: readonly WalkerSnapshot[]): WalkerSnapshot | null {
  let best: WalkerSnapshot | null = null;
  let bestLateral = Infinity;
  for (const other of others) {
    if (other.id === self.id) continue;
    const headingDot = self.heading[0] * other.heading[0] + self.heading[1] * other.heading[1];
    if (headingDot >= HEAD_ON_COS_MAX) continue;
    const dx = other.position[0] - self.position[0];
    const dz = other.position[1] - self.position[1];
    const dist = Math.hypot(dx, dz);
    if (dist >= SIDESTEP_DETECTION_RADIUS_U) continue;
    const lateral = Math.abs(dx * -self.heading[1] + dz * self.heading[0]);
    if (lateral >= FOLLOW_GAP_U) continue;
    if (lateral < bestLateral) {
      bestLateral = lateral;
      best = other;
    }
  }
  return best;
}

export interface SidestepPlan {
  /** The lateral offset (toward self's own right) this avatar's own ramp
   * should target this frame -- 0 when no sidestep is needed/possible. */
  offsetTargetU: number;
  /** True only in the narrow-corridor fallback, and only for the
   * lexicographically LOWER id of the oncoming pair -- LiveAgents.tsx
   * should hold this avatar's forward advance (same shape as
   * applyFollowCap's own "hold at prevAppliedDistance") while true. */
  pauseForOncoming: boolean;
}

/** Pure decision: given `self`, the current oncoming candidates, and
 * whether this avatar's OWN current corridor segment is on a real,
 * graph-verified path (`corridorTrusted` -- see this section's own header
 * for why LiveAgents.tsx's existing `walkable` state is used for this),
 * decides this frame's sidestep target and whether this avatar must
 * instead pause. See this section's own header for the full reasoning. */
export function computeSidestepPlan(
  self: WalkerSnapshot,
  others: readonly WalkerSnapshot[],
  corridorTrusted: boolean,
): SidestepPlan {
  const oncoming = findOncoming(self, others);
  if (!oncoming) return { offsetTargetU: 0, pauseForOncoming: false };
  if (corridorTrusted) return { offsetTargetU: SIDESTEP_TARGET_U, pauseForOncoming: false };
  return { offsetTargetU: 0, pauseForOncoming: self.id < oncoming.id };
}

/** Ramps `current` toward `target` at a bounded rate (`rateUPerS`) over
 * this frame's own `dt` -- never overshoots, never a discontinuous jump.
 * The single mechanism behind BOTH "gradually shift to pass" (target > 0)
 * and "drift back to lane" (target back to 0) -- same function, same rate,
 * just a different target. */
export function rampSidestepOffset(current: number, target: number, rateUPerS: number = SIDESTEP_RATE_U_PER_S, dt: number = 0): number {
  const maxStep = rateUPerS * dt;
  const delta = target - current;
  if (Math.abs(delta) <= maxStep) return target;
  return current + Math.sign(delta) * maxStep;
}

// SIDESTEP-ON-REVERSAL SNAP fix (CONVOY-STACK v13, 2026-09-15, probe
// 20260915T140056Z, verified by direct numerical reproduction against this
// module's own real functions before this fix, not just reasoned about):
// LiveAgents.tsx's own useFrame recomputes its render-time lateral nudge
// EVERY frame as `rightOf([sin(facing), cos(facing)]) * sidestepOffsetRef
// .current` -- a fresh DIRECTION (`right`, perpendicular to THIS frame's
// `facing`) times a ramped MAGNITUDE (`rampSidestepOffset`, a scalar).
// `facing` is piecewise-constant within a path segment and jumps
// instantly the moment `progress` crosses from one segment to the next
// (an unavoidable, normal property of polyline interpolation, true at
// every corner, not just a reversal) -- ordinarily harmless, since an
// ordinary corner only rotates `right` by a modest angle and
// `sidestepOffsetRef.current` is usually 0 (no active head-on pass). But
// on a near-180-degree reversal (RETARGET OUT-AND-BACK's own out-and-back
// shape) WHILE `sidestepOffsetRef.current` is nonzero (an active pass, or
// mid-ramp toward/away from one), `right` itself flips to point almost
// the OPPOSITE way -- the render-time nudge, `right * magnitude`, jumps
// discontinuously by up to `2 * magnitude` in a SINGLE frame (confirmed:
// a reversal + a held 0.4u sidestep magnitude produces an ~0.80u one-frame
// jump under the OLD scalar-magnitude/fresh-direction approach, closely
// matching the probe's own reported ~0.71-0.9u snap), even though the
// underlying `position` (from `poseAlongPath`) itself never jumps at
// all -- this is a purely RENDER-layer discontinuity, layered on top of an
// already-continuous walk.
//
// FIX: track the render-time nudge as a full 2D VECTOR, rate-limited by
// EUCLIDEAN distance toward its own target vector (`right(facing) *
// magnitude`) every frame -- reusing the exact same `SIDESTEP_RATE_U_PER_S`
// rate `rampSidestepOffset` already uses, per the coordinator's own "reuse
// rampSidestepOffset's rate" instruction. Whatever CAUSES `right` to flip
// (a reversal, a sharp corner, an ordinary sidestep engaging or
// disengaging) no longer matters: the applied vector can only ever move a
// bounded EUCLIDEAN distance per frame, so it takes real time to swing
// from one side to the other instead of teleporting across.
export function rampVectorOffset(
  current: readonly [number, number],
  target: readonly [number, number],
  rateUPerS: number = SIDESTEP_RATE_U_PER_S,
  dt: number = 0,
): [number, number] {
  const dx = target[0] - current[0];
  const dz = target[1] - current[1];
  const dist = Math.hypot(dx, dz);
  const maxStep = rateUPerS * dt;
  if (dist <= maxStep || dist === 0) return [target[0], target[1]];
  const scale = maxStep / dist;
  return [current[0] + dx * scale, current[1] + dz * scale];
}

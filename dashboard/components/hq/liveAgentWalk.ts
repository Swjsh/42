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

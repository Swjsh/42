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

export const ENTRY_NODE_ID = "hub-center"; // mirrors lib/hq-agents.ts#ENTRY_NODE_ID (layout.ts's own HUB origin)

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
  const { leaving, targetNodeId, currentNode, seenTarget, leaveTriggered } = input;
  if (leaving) {
    if (leaveTriggered) return { action: "none" };
    if (currentNode === ENTRY_NODE_ID) return { action: "settle", dest: ENTRY_NODE_ID, despawn: true };
    return { action: "walk", dest: ENTRY_NODE_ID, despawn: true };
  }
  if (seenTarget === targetNodeId) return { action: "none" };
  if (currentNode === targetNodeId) return { action: "settle", dest: targetNodeId, despawn: false };
  return { action: "walk", dest: targetNodeId, despawn: false };
}

// ─── Stand-slot ring offset (DEFECT 1 fix) ─────────────────────────────────

export const STAND_RING_RADIUS = 0.9;
export const STAND_BUBBLE_Y_STEP = 0.22;

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

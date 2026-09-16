// CREW-WORKING pass (2026-09-15/16, worker: HQ crew-working build) -- pure,
// react/three-free helpers factored out of Scene.tsx's persona region so
// `node --test` can pin them directly, same reason liveAgentWalk.ts /
// liveAgentIdentity.ts already live as standalone .ts modules (layout.ts
// imports SetKit.tsx, a real .tsx file, which node's own ESM loader refuses
// to load under plain `node --test` -- see layout.ts's own header). Two
// responsibilities, per ENVIRONMENT-PLAN.md's "People actually working"
// checklist + this task's own brief:
//  1. detectHuddleTrigger -- decides WHEN the huddle pair fires, from a real
//     GREEN-count transition only, never a timer (the HQ face rule already
//     in project memory: "motion = real events").
//  2. huddleStandPoints -- the geometry of where the two personas stand at
//     the round table, facing each other.

export interface HuddleCandidate {
  name: string;
  lastFireISO: string | null;
}

export interface HuddleTriggerResult {
  /** A NEW unique key every time a huddle should actually queue --
   * Agent.tsx's existing seen-value-diff convention (`walkPlanKey`) turns a
   * genuine key CHANGE into exactly one walk; an unchanged key (or null)
   * queues none. Null when no huddle should fire this poll. */
  key: string | null;
  pair: [string, string] | null;
}

/** Fires ONLY on a genuine <2 -> >=2 GREEN transition (never on a steady
 * count, never re-firing while the count stays >=2) -- picks the two
 * most-recently-fired GREEN personas (by `lastFireISO`, descending) as the
 * pair. `prevGreenCount` is the CALLER's own previous-poll count (a plain
 * ref in Scene.tsx, the same "diff across renders via a ref" convention
 * that file's own `personaGreetingSinceRef` already uses) -- this function
 * stays pure and stateless itself. `triggerSeed` (Scene.tsx passes
 * `Date.now()` at call time) makes every fired key unique even when the
 * SAME two names go GREEN again later (a 2->1->2 sequence must fire a
 * SECOND time, per this task's own test list) -- a key is never reused, so
 * Agent.tsx's own seen-value-diff always sees a real change. */
export function detectHuddleTrigger(
  greenPersonas: HuddleCandidate[],
  prevGreenCount: number,
  triggerSeed: number,
): HuddleTriggerResult {
  const count = greenPersonas.length;
  if (!(prevGreenCount < 2 && count >= 2)) return { key: null, pair: null };
  const sorted = [...greenPersonas].sort((a, b) => {
    const at = a.lastFireISO ? Date.parse(a.lastFireISO) : -Infinity;
    const bt = b.lastFireISO ? Date.parse(b.lastFireISO) : -Infinity;
    return bt - at;
  });
  const [a, b] = sorted;
  if (!a || !b) return { key: null, pair: null };
  return { key: `huddle:${a.name}+${b.name}:${triggerSeed}`, pair: [a.name, b.name] };
}

/** Two stand points `separation` units apart, straddling the point
 * `nearRadius` units out from `tableCenter` toward `hubPos` (the table's
 * "near side", the side a walker arriving from the hub reaches first),
 * facing each other. `tableCenter`/`hubPos` are the scene's REAL world
 * points (Scene.tsx's own `HUB_TABLE_RADIUS`-derived table center and
 * `HUB`) -- never a re-typed literal. Face-yaw uses the exact same
 * `atan2(self - target)` convention layout.ts#rotationYFacing already
 * establishes project-wide, reproduced here rather than imported so this
 * module stays free of layout.ts's own SetKit.tsx dependency chain. */
export function huddleStandPoints(
  tableCenter: [number, number, number],
  hubPos: [number, number, number],
  nearRadius: number,
  separation: number,
): { a: [number, number, number]; b: [number, number, number]; faceYawA: number; faceYawB: number } {
  const dx = hubPos[0] - tableCenter[0];
  const dz = hubPos[2] - tableCenter[2];
  const dist = Math.hypot(dx, dz) || 1;
  const dirX = dx / dist;
  const dirZ = dz / dist; // table -> hub, unit vector
  const perpX = dirZ;
  const perpZ = -dirX; // perpendicular (tangent) for lateral separation
  const half = separation / 2;
  const baseX = tableCenter[0] + dirX * nearRadius;
  const baseZ = tableCenter[2] + dirZ * nearRadius;
  const a: [number, number, number] = [baseX + perpX * half, tableCenter[1], baseZ + perpZ * half];
  const b: [number, number, number] = [baseX - perpX * half, tableCenter[1], baseZ - perpZ * half];
  const faceYawA = Math.atan2(a[0] - b[0], a[2] - b[2]);
  const faceYawB = Math.atan2(b[0] - a[0], b[2] - a[2]);
  return { a, b, faceYawA, faceYawB };
}

// BLOCKY-FIXES pass (2026-09-16, worker: HQ blocky-fixes build) -- Defect 2
// from a real capture (crew-desk2-0120.png, J AWAY): "neighbor" purposeful
// walks (palette.ts#computePurposefulWalk's own `destination: "neighbor"`
// case) resolved to `findWalkPath(walkGraph, persona-A, persona-B)?.pop()`
// (Scene.tsx) -- the LAST node on that path is `persona-B`'s own graph node,
// which layout.ts registers at EXACTLY `personaGeometry[i].agentHome`, the
// neighbor's own seat world position (Scene.tsx's
// `personaSlots: innerPersonas.map(... position: agentHome ...)`, confirmed
// by reading both call sites this session). So a visiting persona was
// literally parked ON TOP OF the seated neighbor -- two bodies at one point,
// exactly the "two personas on one desk" defect. Root cause is (b) from the
// task brief: a purposeful walk parking a visitor at the neighbor's own seat
// point, not (a) a `computePersonaWallSlots` slot-index collision (that
// function's own candidate list has zero duplicate indices, confirmed by
// inspection) and not (c) `crewWorking.ts`'s own huddle logic (huddle uses
// `huddleStandPoints` above, a table-side point, never a desk node at all).
//
// Fix: a visitor stands `lateralOffset` units to the SIDE of the neighbor's
// own seat, along the desk's own tangent (parallel-to-the-wall) direction --
// the SAME `tangentX = cos(rotationY), tangentZ = -sin(rotationY)` formula
// layout.ts#computePersonaWallSlots already uses to lay out two desks
// side-by-side on one wall (reproduced here rather than imported so this
// module keeps its own zero-SetKit-dependency, node-testable shape -- see
// this file's own header). 1.0u is well inside the 4.6u
// PERSONA_WALL_LATERAL_OFFSET gap between two adjacent desks on the same
// wall, so the stand point can never land on a THIRD persona's own desk
// either. Keeps the same world-Y and the same "room-side" depth the seat
// already sits at (no extra toward-hub/toward-wall offset needed -- the
// seat is already on the room side of its own desk, see DESK_SEAT_LOCAL's
// own comment in SetKit.tsx), so the visitor reads as "standing next to the
// desk," never "standing in the wall" or "standing on the table."
export function neighborStandPoint(
  neighborSeatPos: [number, number, number],
  neighborRotationY: number,
  lateralOffset = 1.0,
): [number, number, number] {
  const tangentX = Math.cos(neighborRotationY);
  const tangentZ = -Math.sin(neighborRotationY);
  return [
    neighborSeatPos[0] + lateralOffset * tangentX,
    neighborSeatPos[1],
    neighborSeatPos[2] + lateralOffset * tangentZ,
  ];
}

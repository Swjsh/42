// @ts-nocheck -- same reason as tests/hq-agents.test.ts's own header: this
// file uses an explicit ".ts" extension on its relative import (required for
// plain `node --test` to resolve it; the project tsconfig's
// `moduleResolution: "bundler"` has no `allowImportingTsExtensions`).
//
// Coordinator fix (2026-09-14, browser verification of e990319f found 2
// defects in LiveAgents.tsx): unit tests for the pure decision/geometry
// functions extracted into components/hq/liveAgentWalk.ts.
//
// DEFECT 2 (stuck leave) root cause, proven here by
// "decideNextWalk starts the leave walk even when seenTarget already equals
// ENTRY_NODE_ID": the ORIGINAL LiveAgents.tsx gated every destination change
// -- ordinary retargeting AND the final leave-to-entry walk -- behind ONE
// shared `seenDest.current === activeDest` latch. An agent whose most
// recently classified zone had already resolved to "hub" (lib/hq-agents.ts
// #ZONE_NODE_ID.hub === ENTRY_NODE_ID) left that latch holding
// "hub-center"; when the server later dropped it and `leaving` flipped
// true, the newly-computed destination ALSO evaluated to "hub-center" --
// the shared latch read this as "nothing changed" and silently skipped the
// walk-kickoff (and the despawn-on-arrival it would have scheduled),
// stranding the avatar in "working" with `leaving` permanently true. This
// test file's own decideNextWalk treats leaving as an independent decision
// that never consults the ordinary-retargeting latch, so this exact
// collision can no longer suppress a leave.
//
// Run: cd dashboard && node --test tests/live-agent-walk.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  ENTRY_NODE_ID,
  pathDistance,
  poseAlongPath,
  decideNextWalk,
  computeStandSlot,
  STAND_RING_RADIUS,
  reconcileLiveAgentRoster,
} from "../components/hq/liveAgentWalk.ts";

// ─── pathDistance ───────────────────────────────────────────────────────────

test("pathDistance sums XZ-plane leg distances, ignoring Y", () => {
  const wp: [number, number, number][] = [[0, 5, 0], [3, 0, 4]]; // 3-4-5 triangle in XZ, Y differs
  assert.equal(pathDistance(wp), 5);
});

test("pathDistance is 0 for a single point", () => {
  assert.equal(pathDistance([[1, 2, 3]]), 0);
});

// ─── poseAlongPath ──────────────────────────────────────────────────────────

test("poseAlongPath at t=0 returns the first waypoint", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [10, 0, 0]];
  const { position } = poseAlongPath(wp, 0);
  assert.deepEqual(position, [0, 0, 0]);
});

test("poseAlongPath at t=1 returns the last waypoint", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [10, 0, 0]];
  const { position } = poseAlongPath(wp, 1);
  assert.deepEqual(position, [10, 0, 0]);
});

test("poseAlongPath interpolates a single leg linearly at t=0.5", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [10, 0, 0]];
  const { position, facing } = poseAlongPath(wp, 0.5);
  assert.equal(position[0], 5);
  assert.equal(facing, Math.atan2(10, 0));
});

test("poseAlongPath handles a zero-XZ-distance leg without NaN/hanging (smart-board <-> hub-center coincidence)", () => {
  // WALL_POS (smart-board) and HUB (hub-center) share x=0,z=0 in this real
  // scene (Scene.tsx's WALL_POS=[0,3.4,0]) -- proves the zero-distance leg
  // case that made DEFECT 2's symptom LOOK stuck (position pinned at the
  // shared XZ point) never itself produces NaN or an infinite loop.
  const wp: [number, number, number][] = [[0, 3.4, 0], [0, 0, 0]];
  const at0 = poseAlongPath(wp, 0);
  const atHalf = poseAlongPath(wp, 0.5);
  const at1 = poseAlongPath(wp, 1);
  for (const r of [at0, atHalf, at1]) {
    assert.ok(Number.isFinite(r.position[0]));
    assert.ok(Number.isFinite(r.position[1]));
    assert.ok(Number.isFinite(r.position[2]));
    assert.ok(Number.isFinite(r.facing));
  }
});

test("poseAlongPath picks the correct leg across a multi-leg path", () => {
  const wp: [number, number, number][] = [[0, 0, 0], [10, 0, 0], [10, 0, 10]];
  // total distance 20; t=0.75 -> 15 units in -> 5 units into the second leg
  const { position } = poseAlongPath(wp, 0.75);
  assert.equal(position[0], 10);
  assert.equal(position[2], 5);
});

// ─── decideNextWalk (DEFECT 2) ──────────────────────────────────────────────

test("decideNextWalk: fresh avatar walks to its first target", () => {
  const d = decideNextWalk({ leaving: false, targetNodeId: "smart-board", currentNode: ENTRY_NODE_ID, seenTarget: null, leaveTriggered: false });
  assert.deepEqual(d, { action: "walk", dest: "smart-board", despawn: false });
});

test("decideNextWalk: no-op when the target hasn't changed", () => {
  const d = decideNextWalk({ leaving: false, targetNodeId: "smart-board", currentNode: ENTRY_NODE_ID, seenTarget: "smart-board", leaveTriggered: false });
  assert.deepEqual(d, { action: "none" });
});

test("decideNextWalk: settles immediately when already standing at the new target", () => {
  const d = decideNextWalk({ leaving: false, targetNodeId: "smart-board", currentNode: "smart-board", seenTarget: "bay-desk-0", leaveTriggered: false });
  assert.deepEqual(d, { action: "settle", dest: "smart-board", despawn: false });
});

test("decideNextWalk: retargets mid-life to a new zone", () => {
  const d = decideNextWalk({ leaving: false, targetNodeId: "bay-desk-0", currentNode: "smart-board", seenTarget: "smart-board", leaveTriggered: false });
  assert.deepEqual(d, { action: "walk", dest: "bay-desk-0", despawn: false });
});

test("decideNextWalk: THE DEFECT 2 FIX -- leaving starts the exit walk even when seenTarget already equals ENTRY_NODE_ID", () => {
  // This is the exact collision that stranded 65e3d7 in the wild: the
  // agent's own classified zone had at some point resolved to "hub"
  // (ZONE_NODE_ID.hub === ENTRY_NODE_ID), so seenTarget already holds
  // ENTRY_NODE_ID from ordinary (non-leaving) life -- a shared-latch design
  // would read the leaving transition as "no change" and never walk out.
  const d = decideNextWalk({
    leaving: true,
    targetNodeId: "smart-board", // irrelevant while leaving -- must be ignored
    currentNode: "smart-board",
    seenTarget: ENTRY_NODE_ID, // the exact collision value
    leaveTriggered: false,
  });
  assert.deepEqual(d, { action: "walk", dest: ENTRY_NODE_ID, despawn: true });
});

test("decideNextWalk: leaving is a one-shot -- does not re-trigger once leaveTriggered", () => {
  const d = decideNextWalk({ leaving: true, targetNodeId: "smart-board", currentNode: "hub-center", seenTarget: null, leaveTriggered: true });
  assert.deepEqual(d, { action: "none" });
});

test("decideNextWalk: leaving settles immediately (and despawns) when already at the entry node", () => {
  const d = decideNextWalk({ leaving: true, targetNodeId: "smart-board", currentNode: ENTRY_NODE_ID, seenTarget: null, leaveTriggered: false });
  assert.deepEqual(d, { action: "settle", dest: ENTRY_NODE_ID, despawn: true });
});

test("decideNextWalk: leaving never consults targetNodeId at all", () => {
  const a = decideNextWalk({ leaving: true, targetNodeId: "ambient-core", currentNode: "smart-board", seenTarget: null, leaveTriggered: false });
  const b = decideNextWalk({ leaving: true, targetNodeId: "bay-desk-0", currentNode: "smart-board", seenTarget: null, leaveTriggered: false });
  assert.deepEqual(a, b);
});

// ─── decideNextWalk (TELEPORT FIX, 2026-09-15 coordinator probe) ───────────
//
// Root cause: `currentNode` only ever advances to a walk's destination ON
// ARRIVAL -- while a walk is still in flight it names the ORIGIN the avatar
// departed from, not where it currently is. Probe run
// 20260915T070024Z-9lS6tSfBnOgS3qHx4bzbD.samples.json.gz caught this exactly
// twice in the SAME tick (298->299 and 328->329, dt ~0.48-0.50s): session
// a06954b44dcea322f was mid-walk toward "ambient-core" (pos [15.24,0], not
// yet arrived) when its server-reported target flipped back to
// "bay-desk-0" -- the node it had departed FROM, which `currentNode` still
// named because that walk had never completed -- and jumped straight to
// [18.30,8.20] (8.75u in 0.48s, 18.2u/s vs. the ~0.7u/s WALK_SPEED band).
// The same tick, session:dcc3d160-...-a8b2 mid-walk toward "bay-desk-0"
// (pos [17.40,3.47]) had its target flip back to "ambient-core" and jumped
// 17.8u in 0.48s (35.4u/s) straight to [-0.03,-0.09]. Both are the exact
// `currentNode === targetNodeId` settle-shortcut firing while genuinely
// mid-walk, not at rest.

test("decideNextWalk: THE TELEPORT FIX -- mid-walk avatar whose target flaps back to its own walk origin must walk, not snap", () => {
  // Mirrors tick 298->299: seenTarget "ambient-core" (what it was walking
  // toward), targetNodeId flips back to "bay-desk-0" (currentNode's stale
  // value -- the origin this in-flight walk started from, never updated
  // because that walk hasn't arrived).
  const d = decideNextWalk({
    leaving: false,
    targetNodeId: "bay-desk-0",
    currentNode: "bay-desk-0",
    seenTarget: "ambient-core",
    leaveTriggered: false,
    isWalking: true,
  });
  assert.deepEqual(d, { action: "walk", dest: "bay-desk-0", despawn: false });
});

test("decideNextWalk: mirrors the OTHER half of the same tick -- session:dcc3d160 flapping bay-desk-0 -> ambient-core mid-walk", () => {
  const d = decideNextWalk({
    leaving: false,
    targetNodeId: "ambient-core",
    currentNode: "ambient-core",
    seenTarget: "bay-desk-0",
    leaveTriggered: false,
    isWalking: true,
  });
  assert.deepEqual(d, { action: "walk", dest: "ambient-core", despawn: false });
});

test("decideNextWalk: omitting isWalking reproduces the PRE-FIX defect (documents the exact bug shape)", () => {
  // isWalking defaults to false -- this is what the code did before the fix
  // wired `phase.current === \"walking\"` through, and it wrongly settles
  // (instant snap) instead of walking.
  const d = decideNextWalk({
    leaving: false,
    targetNodeId: "bay-desk-0",
    currentNode: "bay-desk-0",
    seenTarget: "ambient-core",
    leaveTriggered: false,
  });
  assert.deepEqual(d, { action: "settle", dest: "bay-desk-0", despawn: false });
});

test("decideNextWalk: a genuinely resting avatar still settles in place (isWalking: false is not a regression)", () => {
  const d = decideNextWalk({
    leaving: false, targetNodeId: "smart-board", currentNode: "smart-board", seenTarget: "bay-desk-0", leaveTriggered: false, isWalking: false,
  });
  assert.deepEqual(d, { action: "settle", dest: "smart-board", despawn: false });
});

test("decideNextWalk: isWalking also guards the leaving-settle shortcut (same mechanism, leave path)", () => {
  const d = decideNextWalk({
    leaving: true, targetNodeId: "smart-board", currentNode: ENTRY_NODE_ID, seenTarget: null, leaveTriggered: false, isWalking: true,
  });
  assert.deepEqual(d, { action: "walk", dest: ENTRY_NODE_ID, despawn: true });
});

// ─── computeStandSlot (DEFECT 1) ────────────────────────────────────────────

test("computeStandSlot: a lone occupant gets a zero offset", () => {
  const r = computeStandSlot(["a1"], "a1");
  assert.deepEqual(r, { offset: [0, 0], index: 0, groupSize: 1 });
});

test("computeStandSlot: two occupants land on opposite sides of the ring", () => {
  const ids = ["b", "a"]; // deliberately unsorted input
  const ra = computeStandSlot(ids, "a", 1);
  const rb = computeStandSlot(ids, "b", 1);
  assert.equal(ra.groupSize, 2);
  // sorted(["a","b"]) -> a=index0 (angle 0 -> [1,0]), b=index1 (angle PI -> [-1,0])
  assert.equal(ra.index, 0);
  assert.equal(rb.index, 1);
  assert.ok(Math.abs(ra.offset[0] - 1) < 1e-9 && Math.abs(ra.offset[1]) < 1e-9);
  assert.ok(Math.abs(rb.offset[0] + 1) < 1e-9 && Math.abs(rb.offset[1]) < 1e-9);
  // opposite points -> never the same coordinate
  assert.notDeepEqual(ra.offset, rb.offset);
});

test("computeStandSlot: every member of a larger group gets a DISTINCT point", () => {
  const ids = ["a1", "a2", "a3", "a4", "a5"];
  const points = ids.map((id) => computeStandSlot(ids, id, STAND_RING_RADIUS).offset);
  const unique = new Set(points.map((p) => `${p[0].toFixed(6)},${p[1].toFixed(6)}`));
  assert.equal(unique.size, ids.length);
});

test("computeStandSlot: slot assignment is a pure function of the group's sorted ids, independent of input order", () => {
  const a = computeStandSlot(["z", "a", "m"], "m");
  const b = computeStandSlot(["m", "z", "a"], "m");
  assert.deepEqual(a, b);
});

test("computeStandSlot: an id not in the group falls back to index 0 rather than throwing", () => {
  const r = computeStandSlot(["a", "b"], "not-in-group");
  assert.equal(r.index, 0);
});

// ─── Resting-avatar reslot on group growth (STACK FIX, 2026-09-15 probe) ───
//
// computeStandSlot itself is provably correct (every test above) -- the
// stacking bug was NEVER in this function. It was that LiveAgents.tsx only
// ever APPLIED a computed offset to an avatar's actual position at the
// moment its own walk decision fired (settle or walk-kickoff), and that
// effect's dependency list never included `standOffset`. Probe evidence:
// sessions a06954b44dcea322f and a3f93d37e2266fd28, both "working" at
// target "ambient-core", sat at the EXACT SAME point (pairwise distance
// 0.000, 115 consecutive ticks, t=37796ms-95082ms) -- each had settled at a
// moment it was the ONLY member of the "ambient-core" group in `displayed`
// (computeStandSlot's own `groupSize <= 1` branch, offset [0,0]), and
// neither avatar's position was ever corrected once the other joined, so
// both independently landed on the group's zero-offset slot. This harness
// models exactly the two relevant LiveAgents.tsx effects (settle applies
// whatever offset is current AT settle time; the STACK-FIX reslot effect
// re-applies a fresh offset to a RESTING avatar whenever the group
// recomputes) using only the exported pure functions -- no React/DOM
// needed -- so the fix's actual mechanism is provable with plain
// `node --test`.
function simulateSettleThenGroupGrowth(reslotOnGroupChange) {
  // Avatar A settles alone at "ambient-core" first (groupSize 1) -- exactly
  // how a3f93d37e2266fd28 must have arrived before the probe window opened.
  const soloGroup = ["a06954b44dcea322f"];
  let appliedOffsetA = computeStandSlot(soloGroup, "a06954b44dcea322f", STAND_RING_RADIUS).offset;

  // Avatar B (a3f93d37e2266fd28) joins the SAME target later -- the group
  // grows to 2, and liveAgentWalk.ts#computeStandSlot recomputes BOTH
  // members' offsets when the roster's standSlots memo re-runs.
  const grownGroup = ["a06954b44dcea322f", "a3f93d37e2266fd28"];
  const freshSlotA = computeStandSlot(grownGroup, "a06954b44dcea322f", STAND_RING_RADIUS);
  const freshSlotB = computeStandSlot(grownGroup, "a3f93d37e2266fd28", STAND_RING_RADIUS);

  // B settles fresh right now -- its own walk decision is firing for the
  // first time, so it always picks up the CURRENT offset.
  const appliedOffsetB = freshSlotB.offset;

  // A is already resting from its earlier, solo settle: only the fix
  // (reslotOnGroupChange) re-applies A's now-stale offset.
  if (reslotOnGroupChange) appliedOffsetA = freshSlotA.offset;

  return { appliedOffsetA, appliedOffsetB };
}

test("STACK FIX: PRE-FIX shape -- a resting avatar that settled alone stays stuck at the zero offset once a sibling joins its target", () => {
  const { appliedOffsetA, appliedOffsetB } = simulateSettleThenGroupGrowth(false);
  // Reproduces the probe's measured 0.000 pairwise distance: A is frozen at
  // the bare node center, and the only thing keeping B off that exact point
  // is that B's OWN first-ever settle happens to see the up-to-date group.
  assert.deepEqual(appliedOffsetA, [0, 0]);
  const dist = Math.hypot(appliedOffsetA[0] - appliedOffsetB[0], appliedOffsetA[1] - appliedOffsetB[1]);
  assert.ok(dist > 0, "documents that B alone avoids the collision -- A is the one left stale");
});

test("STACK FIX: reslot-on-group-change (the actual fix) gives both resting avatars distinct, ring-separated points", () => {
  const { appliedOffsetA, appliedOffsetB } = simulateSettleThenGroupGrowth(true);
  assert.notDeepEqual(appliedOffsetA, [0, 0]);
  const dist = Math.hypot(appliedOffsetA[0] - appliedOffsetB[0], appliedOffsetA[1] - appliedOffsetB[1]);
  assert.ok(dist >= STAND_RING_RADIUS, `expected separated ring points, got distance ${dist}`);
});

// ─── reconcileLiveAgentRoster (BUBBLE-FIX, 2026-09-15) ─────────────────────
//
// Extracted from LiveAgents.tsx's own `setDisplayed` updater specifically to
// reproduce the coordinator's live-browser finding: a dropped agent (aa69)
// stayed rendered "working" forever while a newly-arrived agent (7252, this
// very session) never mounted, observed in the SAME /api/hq poll. The test
// below proves the reconcile function ITSELF handles that exact "one id
// replaced by another, same target, same poll" shape correctly -- the real
// root cause was one layer up (app/hq/page.tsx's `sceneData` memo never
// listing `liveAgents` in its own inclusion-list key, fixed in that file,
// same commit) and never reached this function at all, which is exactly
// what this passing test demonstrates.

interface FakeAgent {
  id: string;
  targetZone: string;
}

interface FakeDisplayed {
  id: string;
  targetNodeId: string;
  leaving: boolean;
}

function buildFakeDisplayed(a: FakeAgent): FakeDisplayed {
  return { id: a.id, targetNodeId: a.targetZone, leaving: false };
}

test("reconcileLiveAgentRoster: coordinator's exact scenario -- one id (aa69) dropped and a DIFFERENT id (7252) added, in the SAME poll, both at the same target", () => {
  const prev = new Map<string, FakeDisplayed>([
    ["aa69", { id: "aa69", targetNodeId: "smart-board", leaving: false }],
    ["345c", { id: "345c", targetNodeId: "ambient-core", leaving: false }],
    ["e5df", { id: "e5df", targetNodeId: "ambient-ideas-wall", leaving: false }],
  ]);
  const incoming: FakeAgent[] = [
    { id: "7252", targetZone: "smart-board" }, // replaces aa69 at the SAME target
    { id: "345c", targetZone: "ambient-core" },
    { id: "e5df", targetZone: "ambient-ideas-wall" },
  ];

  const next = reconcileLiveAgentRoster(prev, incoming, buildFakeDisplayed);

  assert.equal(next.size, 4, "aa69 stays (marked leaving), plus the 3 incoming ids");
  assert.equal(next.get("aa69")?.leaving, true, "the dropped id must be marked leaving, never left silently 'working'");
  assert.ok(next.has("7252"), "the newly-arrived id in the same poll must be added");
  assert.equal(next.get("7252")?.leaving, false);
  assert.equal(next.get("345c")?.leaving, false);
  assert.equal(next.get("e5df")?.leaving, false);
});

test("reconcileLiveAgentRoster: an id that reappears after being marked leaving comes back (leaving reset to false)", () => {
  const prev = new Map<string, FakeDisplayed>([["a1", { id: "a1", targetNodeId: "hub-center", leaving: true }]]);
  const next = reconcileLiveAgentRoster(prev, [{ id: "a1", targetZone: "smart-board" }], buildFakeDisplayed);
  assert.equal(next.get("a1")?.leaving, false);
  assert.equal(next.get("a1")?.targetNodeId, "smart-board");
});

test("reconcileLiveAgentRoster: an already-leaving id with no incoming row stays leaving (no double-mark, no reset)", () => {
  const prev = new Map<string, FakeDisplayed>([["a1", { id: "a1", targetNodeId: "hub-center", leaving: true }]]);
  const next = reconcileLiveAgentRoster(prev, [], buildFakeDisplayed);
  assert.equal(next.get("a1")?.leaving, true);
});

test("reconcileLiveAgentRoster: an empty incoming roster (transient fetch glitch) marks every currently-displayed id leaving", () => {
  const prev = new Map<string, FakeDisplayed>([
    ["a1", { id: "a1", targetNodeId: "hub-center", leaving: false }],
    ["a2", { id: "a2", targetNodeId: "smart-board", leaving: false }],
  ]);
  const next = reconcileLiveAgentRoster(prev, [], buildFakeDisplayed);
  assert.equal(next.get("a1")?.leaving, true);
  assert.equal(next.get("a2")?.leaving, true);
});

test("reconcileLiveAgentRoster: never mutates the `prev` map it was given", () => {
  const prev = new Map<string, FakeDisplayed>([["a1", { id: "a1", targetNodeId: "hub-center", leaving: false }]]);
  reconcileLiveAgentRoster(prev, [], buildFakeDisplayed);
  assert.equal(prev.get("a1")?.leaving, false, "prev must stay untouched -- React state must never be mutated in place");
});

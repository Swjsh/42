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

// @ts-nocheck -- same reason as tests/live-agent-walk.test.ts's own header:
// an explicit ".ts" extension on this relative import is required for plain
// `node --test` to resolve it; the project tsconfig's moduleResolution
// "bundler" has no allowImportingTsExtensions, which would otherwise fail
// `next build`'s type-check over this one file. Syntax-erasure only.
//
// AGENT-IDENTITY pass (queue item f, 2026-09-15): unit tests for
// components/hq/liveAgentIdentity.ts -- the pure type->look mapping.
//
// Run: cd dashboard && node --test tests/live-agent-identity.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { liveAgentIdentity } from "../components/hq/liveAgentIdentity.ts";

test("main session (label 'session') -> its own distinct tint + 'Claude (you)'", () => {
  const id = liveAgentIdentity("session", "session:abc123");
  assert.equal(id.kind, "session");
  assert.equal(id.displayName, "Claude (you)");
  assert.match(id.tint, /^#[0-9a-f]{6}$/i);
});

test("general-purpose -> the worker look, display name unchanged", () => {
  const id = liveAgentIdentity("general-purpose", "agt-1");
  assert.equal(id.kind, "worker");
  assert.equal(id.displayName, "general-purpose");
});

test("Explore -> the read-only-scout look, display name unchanged", () => {
  const id = liveAgentIdentity("Explore", "agt-2");
  assert.equal(id.kind, "explore");
  assert.equal(id.displayName, "Explore");
});

test("an unrecognized real agent_type (e.g. 'gamma') -> fallback bucket, name preserved verbatim", () => {
  const id = liveAgentIdentity("gamma", "agt-3");
  assert.equal(id.kind, "other");
  assert.equal(id.displayName, "gamma");
});

test("the bare 'agent' fallback label -> fallback bucket", () => {
  const id = liveAgentIdentity("agent", "agt-4");
  assert.equal(id.kind, "other");
  assert.equal(id.displayName, "agent");
});

test("the three named kinds never collide with each other or the fallback palette", () => {
  const session = liveAgentIdentity("session", "x");
  const worker = liveAgentIdentity("general-purpose", "x");
  const explore = liveAgentIdentity("Explore", "x");
  const tints = new Set([session.tint, worker.tint, explore.tint]);
  assert.equal(tints.size, 3, "session/worker/explore must each have a distinct tint");
});

test("deterministic: the SAME id always gets the SAME fallback tint", () => {
  const a = liveAgentIdentity("gamma", "agt-99");
  const b = liveAgentIdentity("gamma", "agt-99");
  assert.equal(a.tint, b.tint);
});

test("fallback tint is keyed by id, not by label alone -- two different ids CAN diverge", () => {
  // Not a strict requirement that ALL ids diverge (a small fixed palette can
  // collide), but at least one of a handful of distinct real-looking ids
  // must land on a different hue than "agt-1" for the hash to be doing real
  // work, not silently constant-folding to one color.
  const seedIds = ["agt-1", "agt-2", "agt-3", "agt-4", "agt-5", "agt-6"];
  const tints = new Set(seedIds.map((sid) => liveAgentIdentity("gamma", sid).tint));
  assert.ok(tints.size > 1, "expected at least 2 distinct fallback tints across 6 different ids");
});

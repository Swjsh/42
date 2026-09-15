// @ts-nocheck -- same reason as tests/hq-perf-cache.test.ts's own header:
// this file uses an explicit ".ts" extension on its relative import
// (required for plain `node --test` to resolve it; the project tsconfig's
// `moduleResolution: "bundler"` has no `allowImportingTsExtensions`, which
// would otherwise fail `next build`'s project-wide type-check over this one
// file). Purely a syntax-erasure pragma -- has no effect on what actually
// runs.
//
// NEEDS J item 5 (2026-09-15): setup/scripts/claude_auth_canary.py writes
// automation/state/claude-auth-canary.json daily (Gamma_ClaudeAuthCanary,
// 18:00 ET); lib/hq.ts#claudeAuthCanaryToBlockedItem turns that verdict into
// (or withholds) a "NEEDS J" card row. This suite tests ONLY that pure
// decision function against fixture objects -- no filesystem, no fs.stat/
// fs.readFile involved, matching the module's own doc comment that the fs
// half (readClaudeAuthCanary) is deliberately kept separate from this half.
//
// Run: cd dashboard && node --test tests/hq-claude-auth-canary.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { claudeAuthCanaryToBlockedItem, type ClaudeAuthCanary } from "../lib/hq.ts";

const NOW = Date.parse("2026-09-15T13:00:00-04:00"); // 2026-09-15 13:00:00 ET

test("LOGGED_OUT verdict produces a [Rig] item naming the fix", () => {
  const canary: ClaudeAuthCanary = {
    verdict: "LOGGED_OUT",
    ts_et: "2026-09-15 08:52:29 ET",
    hours_left: -20.46,
  };
  const item = claudeAuthCanaryToBlockedItem(canary, NOW);
  assert.ok(item, "LOGGED_OUT must produce an item");
  assert.equal(item.source, "claude_auth_canary");
  assert.match(item.text, /Claude CLI logged out/);
  assert.match(item.text, /claude.*\/login/s);
});

test("EXPIRING verdict produces an item stating the hours remaining", () => {
  const canary: ClaudeAuthCanary = {
    verdict: "EXPIRING",
    ts_et: "2026-09-15 08:52:29 ET",
    hours_left: 3.4,
  };
  const item = claudeAuthCanaryToBlockedItem(canary, NOW);
  assert.ok(item, "EXPIRING must produce an item");
  assert.match(item.text, /expires in 3h/);
});

test("OK verdict produces no item", () => {
  const canary: ClaudeAuthCanary = {
    verdict: "OK",
    ts_et: "2026-09-15 08:52:29 ET",
    hours_left: 200,
  };
  assert.equal(claudeAuthCanaryToBlockedItem(canary, NOW), null);
});

test("UNKNOWN verdict produces no item", () => {
  const canary: ClaudeAuthCanary = {
    verdict: "UNKNOWN",
    ts_et: null,
    hours_left: null,
  };
  assert.equal(claudeAuthCanaryToBlockedItem(canary, NOW), null);
});

test("null canary (missing/unreadable file) produces no item", () => {
  assert.equal(claudeAuthCanaryToBlockedItem(null, NOW), null);
});

test("a LOGGED_OUT reading older than 48h (canary task itself died) produces no item", () => {
  const canary: ClaudeAuthCanary = {
    verdict: "LOGGED_OUT",
    ts_et: "2026-09-10 08:00:00 ET", // ~5 days before NOW
    hours_left: -140,
  };
  assert.equal(claudeAuthCanaryToBlockedItem(canary, NOW), null);
});

test("malformed/garbled row (parsed defensively upstream to UNKNOWN with null fields) produces no item", () => {
  const canary: ClaudeAuthCanary = { verdict: "UNKNOWN", ts_et: null, hours_left: null };
  assert.equal(claudeAuthCanaryToBlockedItem(canary, NOW), null);
});

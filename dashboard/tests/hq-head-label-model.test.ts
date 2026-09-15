// @ts-nocheck -- same reason as tests/live-agent-walk.test.ts's own header:
// an explicit ".ts" extension on this relative import is required for plain
// `node --test` to resolve it; the project tsconfig's moduleResolution
// "bundler" has no allowImportingTsExtensions, which would otherwise fail
// `next build`'s type-check over this one file. Syntax-erasure only.
//
// HEAD-LABELS pass (LABELS worker, 2026-09-15): unit tests for
// components/hq/headLabelModel.ts -- the pure glyph/dot/truncation helpers
// behind the compact head label (name + model-tier glyph + status dot;
// long action/status text moved to hover/click, see Agent.tsx/
// LiveAgents.tsx/GammaCharacter.tsx's new HeadLabel.tsx mount + this file's
// own header for the ENVIRONMENT-PLAN.md part C source citations).
//
// NOTE ON FILE NAME: originally authored as headLabel.ts/HeadLabel.tsx --
// renamed to headLabelModel.ts (this test file renamed to match) after the
// TWIN-MONITORS-DESKS deploy failed on this Windows box's case-insensitive
// filesystem, where "headLabel.ts" and "HeadLabel.tsx" collide under
// Next/TS's forceConsistentCasingInFileNames. HeadLabel.tsx (the React
// component) keeps its own name -- only the pure module moved.
//
// Run: cd dashboard && node --import ./tests/resolve-ts-extensionless.loader.mjs --test tests/hq-head-label-model.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { modelGlyph, statusDotColor, truncateName } from "../components/hq/headLabelModel.ts";

test("modelGlyph: python-script -> gear, title includes producer text when given", () => {
  const noProducer = modelGlyph("python-script");
  assert.equal(noProducer.glyph, "⚙");
  assert.equal(noProducer.title, "Python / deterministic script");

  const withProducer = modelGlyph("python-script", "heartbeat_core.py (deterministic, $0) via Gamma_HeartbeatCore");
  assert.equal(withProducer.glyph, "⚙");
  assert.match(withProducer.title, /heartbeat_core\.py/);
});

test("modelGlyph: local-llm -> house, title includes the real model name when given", () => {
  const noModel = modelGlyph("local-llm");
  assert.equal(noModel.glyph, "🏠");
  assert.equal(noModel.title, "Local model (Ollama)");

  const withModel = modelGlyph("local-llm", null, "qwen3:14b");
  assert.equal(withModel.glyph, "🏠");
  assert.match(withModel.title, /qwen3:14b/);
});

test("modelGlyph: claude-session parses a case-insensitive sonnet/opus/haiku token out of producer text", () => {
  const sonnet = modelGlyph("claude-session", "run-analyst-eod.ps1: brain-routed Claude fallback (Sonnet tier)");
  assert.equal(sonnet.glyph, "⚡");

  const opus = modelGlyph("claude-session", "Gamma_Conductor (opus judgment, Anthropic)");
  assert.equal(opus.glyph, "✨");

  const haiku = modelGlyph("claude-session", "cheap HAIKU pass for routine triage");
  assert.equal(haiku.glyph, "🍃");
});

test("modelGlyph: claude-session hover title is the literal producer string, tier parsed or not", () => {
  const producer = "run-treasurer-weekly.ps1, brain-routed via _brain.ps1, via Gamma_TreasurerWeekly";
  const r = modelGlyph("claude-session", producer);
  assert.equal(r.title, producer);
  // No sonnet/opus/haiku token in this real producer string -> generic glyph, never a guessed tier.
  assert.equal(r.glyph, "✦");
});

test("modelGlyph: never invents a tier for empty/missing producer text", () => {
  const noText = modelGlyph("claude-session", null);
  assert.equal(noText.glyph, "✦");
  assert.equal(noText.title, "Claude session");

  const emptyText = modelGlyph("claude-session", "");
  assert.equal(emptyText.glyph, "✦");

  const unrelatedText = modelGlyph("claude-session", "brain-routed Claude fallback only on failure");
  assert.equal(unrelatedText.glyph, "✦");
});

test("modelGlyph: claude-live (ephemeral Claude Code sessions, no model field at all) is always the generic glyph + honest 'tier unknown'", () => {
  const r = modelGlyph("claude-live");
  assert.equal(r.glyph, "✦");
  assert.equal(r.title, "Claude · tier unknown");
});

test("modelGlyph: unknown/none falls back to '?' and never fabricates a title", () => {
  const bare = modelGlyph("none");
  assert.equal(bare.glyph, "?");
  assert.equal(bare.title, "unknown runtime");

  const withEvidence = modelGlyph("none", "no producer on file");
  assert.equal(withEvidence.glyph, "?");
  assert.equal(withEvidence.title, "no producer on file");
});

test("statusDotColor: persona axis reuses PERSONA_STATUS_COLOR, unknown falls back to IDLE", () => {
  assert.equal(statusDotColor("persona", "GREEN"), "#22ff88");
  assert.equal(statusDotColor("persona", "YELLOW"), "#ffb020");
  assert.equal(statusDotColor("persona", "RED"), "#ff3b3b");
  assert.equal(statusDotColor("persona", "IDLE"), "#6a86b8");
  assert.equal(statusDotColor("persona", "bogus"), statusDotColor("persona", "IDLE"));
});

test("statusDotColor: lane axis reuses HEALTH_COLOR, unknown falls back to the dim gray", () => {
  assert.equal(statusDotColor("lane", "green"), "#22ff88");
  assert.equal(statusDotColor("lane", "amber"), "#ffb020");
  assert.equal(statusDotColor("lane", "red"), "#ff3b3b");
  assert.equal(statusDotColor("lane", "bogus"), "#7f93b0");
});

test("statusDotColor: explicit passes an already-resolved hex straight through", () => {
  assert.equal(statusDotColor("explicit", "#38bdf8"), "#38bdf8");
});

test("truncateName: caps at 14 chars by default, ellipsis counts against the budget", () => {
  assert.equal(truncateName("Pilot"), "Pilot");
  assert.equal(truncateName("A".repeat(14)), "A".repeat(14));
  const long = truncateName("A".repeat(20));
  assert.equal(long.length, 14);
  assert.ok(long.endsWith("…"));
});

test("truncateName: caller-supplied max is honored", () => {
  const cut = truncateName("general-purpose", 10);
  assert.equal(cut.length, 10);
  assert.ok(cut.endsWith("…"));
});

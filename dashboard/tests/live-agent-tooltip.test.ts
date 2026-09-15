// @ts-nocheck -- same reason as tests/bubble-text-live-agent.test.ts's own
// header: an explicit ".ts" extension on this relative import is required
// for plain `node --test` to resolve it; the project tsconfig's
// moduleResolution "bundler" has no allowImportingTsExtensions, which would
// otherwise fail `next build`'s type-check over this one file. Syntax-
// erasure only.
//
// AGENT-IDENTITY pass (queue item f, 2026-09-15): unit tests for
// lib/hq-agents.ts#sanitizeTaskText -- the hover-tooltip sanitizer. The bar
// this must clear (this task's own spec + setup/scripts/hq_probe_lib.py's
// own RAW_SHELL_LEAK_RE): output must never contain "Ran:", a backslash,
// "/c/Users", or "&&" -- the exact leaks BUBBLE-FIX (2026-09-15) already
// fixed for the short bubble phrase, now checked for the FULL tooltip text
// too. Fixtures are real shapes lifted from tests/bubble-text-live-agent.test.ts
// (itself lifted from this session's own pulse.jsonl), per this project's
// "only use names that appear in the real detail string" rule.
//
// Run: cd dashboard && node --test tests/live-agent-tooltip.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { sanitizeTaskText } from "../lib/hq-agents.ts";

// The exact regex hq_probe_lib.py's own check_bubbles() flags a leak with --
// kept as a literal copy (not imported, Python<->TS can't share a regex)
// so a change to either side's rule is caught by a failing test, not a
// silent divergence.
const RAW_SHELL_LEAK_RE = /Ran:|\\|\/c\/Users|&&/;

test("strips the 'Ran: ' prefix", () => {
  assert.equal(sanitizeTaskText("Ran: npm test -- --run"), "npm test -- --run");
});

test("real shape: cd <path> && grep ... -- cd preamble stripped, no leak survives", () => {
  const out = sanitizeTaskText(
    "Ran: cd C:/Users/jackw/Desktop/42/dashboard && grep -n \"LiveAgents\\b\" components/hq/Scene.tsx",
  );
  assert.equal(RAW_SHELL_LEAK_RE.test(out), false, `leak survived in: ${out}`);
  assert.match(out, /grep/);
  assert.match(out, /Scene\.tsx/);
});

test("real shape: Windows backslash path -> forward slashes, no backslash survives", () => {
  const out = sanitizeTaskText("Editing C:\\Users\\jackw\\Desktop\\42\\dashboard\\lib\\hq-agents.ts");
  assert.equal(RAW_SHELL_LEAK_RE.test(out), false, `leak survived in: ${out}`);
  assert.match(out, /hq-agents\.ts/);
});

test("real shape: git-bash /c/Users form -> workspace path stripped, no leak survives", () => {
  const out = sanitizeTaskText("Ran: cd /c/Users/jackw/Desktop/42 && git status");
  assert.equal(RAW_SHELL_LEAK_RE.test(out), false, `leak survived in: ${out}`);
});

test("a bare cd whose path alone ate the whole 100-char budget -> degrades honestly, no leak survives", () => {
  const out = sanitizeTaskText("Ran: cd /c/Users/jackw/Desktop/42");
  assert.equal(RAW_SHELL_LEAK_RE.test(out), false, `leak survived in: ${out}`);
});

test("multiple && chain operators all get replaced", () => {
  const out = sanitizeTaskText("Ran: cd /repo && npm run build && npm test");
  assert.equal(RAW_SHELL_LEAK_RE.test(out), false, `leak survived in: ${out}`);
  assert.match(out, /then/);
});

test("empty/whitespace-only input degrades to empty string, never an ellipsis-only tooltip", () => {
  assert.equal(sanitizeTaskText(""), "");
  assert.equal(sanitizeTaskText("   "), "");
});

test("caps at 200 chars with a trailing ellipsis", () => {
  const long = "Ran: " + "a".repeat(300);
  const out = sanitizeTaskText(long);
  assert.ok(out.length <= 200, `expected <=200 chars, got ${out.length}`);
  assert.ok(out.endsWith("…"));
});

test("plain human text (SendMessage-shaped) passes through unchanged, no leak introduced", () => {
  assert.equal(
    sanitizeTaskText("Add LiveAgents reconciliation bug to BUBBLE-FIX"),
    "Add LiveAgents reconciliation bug to BUBBLE-FIX",
  );
});

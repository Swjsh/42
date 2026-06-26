"use strict";

// Smoke test for the build-intent regex — mirrors server.js line 282 exactly.
// Run: node gamma-companion/smoke-voice.js
// Must exit 0 with all PASS lines.

// --- source: server.js line 282-283 ---
const BUILD_INTENT_RE =
  /(^|[.;!?,]\s+|\b(?:please|hey gamma|gamma|can you|could you|go|now|then)[,:]?\s+)(build|create|add|fix|make|write|implement|change|update|refactor|run|test|check|analy[sz]e|research|improve|set up|wire|remove|delete|investigate|patch|backtest|port|debug|optimi[sz]e|ship|generate)\b/i;

function isBuildIntent(message) {
  return BUILD_INTENT_RE.test(String(message || ""));
}

// ---------------------------------------------------------------------------

const SHOULD_MATCH = [
  "build a smoke test",
  "create a validator",
  "fix the bug",
  "delete the old file",
  "please fix this",
  "please build a new module",
  "can you create a chart",
  "could you fix the regression",
  "gamma, build a new module",
  "hey gamma, delete the stale state",
  "go implement the handler",
  "now ship the change",
  "then run the backtest",
  "looks good. now fix the edge case",
  "done! create the smoke test next",
];

const SHOULD_NOT_MATCH = [
  "what did you build",
  "how do I fix this",
  "when did you create that",
  "why does this delete fail",
  "did you fix it",
  "have you tried to build it",
  "I wonder if you should build that",
  "so you want to fix",
];

let passed = 0;
let failed = 0;

function assert(label, result, expected) {
  if (result === expected) {
    console.log(`  PASS  ${label}`);
    passed++;
  } else {
    console.error(`  FAIL  ${label}  (got ${result}, want ${expected})`);
    failed++;
  }
}

console.log("\n=== BUILD_INTENT_RE smoke test ===\n");

console.log("-- imperatives (expect match=true) --");
for (const msg of SHOULD_MATCH) {
  assert(`"${msg}"`, isBuildIntent(msg), true);
}

console.log("\n-- questions / ambiguous (expect match=false) --");
for (const msg of SHOULD_NOT_MATCH) {
  assert(`"${msg}"`, isBuildIntent(msg), false);
}

console.log(`\n${passed} passed, ${failed} failed`);

if (failed > 0) {
  process.exit(1);
}

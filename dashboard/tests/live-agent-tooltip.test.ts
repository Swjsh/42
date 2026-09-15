// @ts-nocheck -- same reason as tests/bubble-text-live-agent.test.ts's own
// header: an explicit ".ts" extension on this relative import is required
// for plain `node --test` to resolve it; the project tsconfig's
// moduleResolution "bundler" has no allowImportingTsExtensions, which would
// otherwise fail `next build`'s type-check over this one file. Syntax-
// erasure only.
//
// AGENT-IDENTITY pass (queue item f, 2026-09-15), hardened to IDENTITY v2
// same day: unit tests for lib/hq-agents.ts#sanitizeTaskText/buildTaskDetail
// -- the hover-tooltip sanitizer. The bar this must clear (this task's own
// spec + setup/scripts/hq_probe_lib.py's own RAW_SHELL_LEAK_RE): output
// must never contain "Ran:", a backslash, "/c/Users", or "&&" -- the exact
// leaks BUBBLE-FIX (2026-09-15) already fixed for the short bubble phrase.
//
// IDENTITY v2 (coordinator-reported leak on 7e6095eb): v1's sanitizer only
// stripped THIS box's own hardcoded repo path -- a live tooltip read
// `python "C:/Users/jackw/AppData/Local/Temp/claude/x/scratchpad/p.py"`,
// an absolute path OUTSIDE the repo (a scratchpad temp dir) that never
// matched. The v2 cases below are the coordinator's own exact reported
// shapes plus the general drive-letter/MSYS/username assertions the fix
// must clear for ANY absolute path, not just the repo's own.
//
// Run: cd dashboard && node --test tests/live-agent-tooltip.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { sanitizeTaskText, buildTaskDetail, liveAgentBubbleAction } from "../lib/hq-agents.ts";

// The exact regex hq_probe_lib.py's own check_bubbles() flags a leak with --
// kept as a literal copy (not imported, Python<->TS can't share a regex)
// so a change to either side's rule is caught by a failing test, not a
// silent divergence.
const RAW_SHELL_LEAK_RE = /Ran:|\\|\/c\/Users|&&/;

/** IDENTITY v2's own broader bar, beyond RAW_SHELL_LEAK_RE: no username,
 * no drive-letter-colon-slash of ANY letter (not just C:), no literal
 * "Users" segment. Asserted on every v2 fixture below. */
function assertNoPathLeak(out: string, label: string): void {
  assert.equal(RAW_SHELL_LEAK_RE.test(out), false, `${label}: RAW_SHELL_LEAK_RE matched in: ${out}`);
  assert.doesNotMatch(out, /Users/, `${label}: "Users" survived in: ${out}`);
  assert.doesNotMatch(out, /[A-Za-z]:\//, `${label}: a drive-letter path survived in: ${out}`);
  assert.doesNotMatch(out, /jackw/i, `${label}: username survived in: ${out}`);
  assert.doesNotMatch(out, /&&/, `${label}: "&&" survived in: ${out}`);
}

test("strips the 'Ran: ' prefix", () => {
  assert.equal(sanitizeTaskText("Ran: npm test -- --run"), "npm test -- --run");
});

test("real shape: cd <path> && grep ... -- cd preamble stripped, no leak survives", () => {
  const out = sanitizeTaskText(
    "Ran: cd C:/Users/jackw/Desktop/42/dashboard && grep -n \"LiveAgents\\b\" components/hq/Scene.tsx",
  );
  assertNoPathLeak(out, "cd&&grep");
  assert.match(out, /grep/);
  assert.match(out, /Scene\.tsx/);
});

test("real shape: Windows backslash path -> forward slashes, no backslash survives", () => {
  const out = sanitizeTaskText("Editing C:\\Users\\jackw\\Desktop\\42\\dashboard\\lib\\hq-agents.ts");
  assertNoPathLeak(out, "backslash-path");
  assert.match(out, /hq-agents\.ts/);
});

test("real shape: git-bash /c/Users form -> workspace path stripped, no leak survives", () => {
  const out = sanitizeTaskText("Ran: cd /c/Users/jackw/Desktop/42 && git status");
  assertNoPathLeak(out, "msys-cd");
});

test("a bare cd whose path alone ate the whole 100-char budget -> degrades honestly, no leak survives", () => {
  const out = sanitizeTaskText("Ran: cd /c/Users/jackw/Desktop/42");
  assertNoPathLeak(out, "bare-cd");
});

test("multiple && chain operators all get replaced", () => {
  const out = sanitizeTaskText("Ran: cd /repo && npm run build && npm test");
  assertNoPathLeak(out, "multi-chain");
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

// ─── IDENTITY v2: the coordinator's own exact reported shapes ──────────────

test("v2 REGRESSION: the exact coordinator-reported leak -- python + quoted Temp scratchpad path", () => {
  const out = sanitizeTaskText(
    'python "C:/Users/jackw/AppData/Local/Temp/claude/x/scratchpad/p.py"',
  );
  assertNoPathLeak(out, "temp-scratchpad");
  // the basename survives, tagged as a temp path per this task's own
  // "<temp>/file.py" spec -- never a bare directory-less guess.
  assert.match(out, /<temp>\/p\.py/);
  assert.match(out, /python/);
});

test('v2: cd "C:\\Users\\jackw\\Desktop\\42" && npm test -- quoted Windows drive path, cd chain fully stripped', () => {
  const out = sanitizeTaskText('cd "C:\\Users\\jackw\\Desktop\\42" && npm test');
  assertNoPathLeak(out, "quoted-drive-cd");
  assert.match(out, /npm test/);
});

test("v2: Ran: powershell -File D:\\Gamma\\x.ps1 -- non-C: drive letter also scrubbed", () => {
  const out = sanitizeTaskText("Ran: powershell -File D:\\Gamma\\x.ps1");
  assertNoPathLeak(out, "d-drive");
  assert.match(out, /x\.ps1/);
});

test("v2: bare MSYS path with no cd/Ran wrapper at all", () => {
  const out = sanitizeTaskText("/c/Users/jackw/Desktop/42/setup/scripts/a.py");
  assertNoPathLeak(out, "bare-msys");
  assert.match(out, /a\.py/);
});

test("v2: relative paths are left ALONE -- no false-positive on a path containing '/a/' mid-string", () => {
  // Guards scrubAbsolutePaths' own token-anchoring: a naive global regex for
  // MSYS "/x/..." would also match the "/a/" substring inside a perfectly
  // normal relative path like this one.
  assert.equal(sanitizeTaskText("Editing components/a/b.ts"), "Editing components/a/b.ts");
});

test("v2: %TEMP%-style env-var path is scrubbed too", () => {
  const out = sanitizeTaskText("Ran: type %TEMP%\\claude\\scratch\\p.py");
  assertNoPathLeak(out, "env-temp");
  assert.match(out, /<temp>\/p\.py/);
});

test("v2: ~/... home-relative path is scrubbed too", () => {
  const out = sanitizeTaskText("Ran: cat ~/notes/todo.md");
  assertNoPathLeak(out, "home-path");
  assert.match(out, /todo\.md/);
});

// ─── buildTaskDetail: phrase-first composition ─────────────────────────────

test("buildTaskDetail: phrase leads, fuller sanitized detail follows when it adds information", () => {
  const phrase = liveAgentBubbleAction({ tool: "Bash", detail: 'Ran: python "C:/Users/jackw/AppData/Local/Temp/claude/x/scratchpad/p.py"', to: "" });
  assert.equal(phrase, "running a command"); // classifyCommand doesn't know "python" -- honest fallback, per liveAgentBubbleAction's own contract
  const out = buildTaskDetail(phrase, 'Ran: python "C:/Users/jackw/AppData/Local/Temp/claude/x/scratchpad/p.py"');
  assertNoPathLeak(out, "buildTaskDetail-phrase-first");
  assert.ok(out.startsWith("running a command"), `expected the phrase FIRST, got: ${out}`);
  assert.match(out, /<temp>\/p\.py/);
});

test("buildTaskDetail: identical phrase and sanitized detail collapse to one copy, never doubled", () => {
  const out = buildTaskDetail("Add LiveAgents reconciliation bug to BUBBLE-FIX", "Add LiveAgents reconciliation bug to BUBBLE-FIX");
  assert.equal(out, "Add LiveAgents reconciliation bug to BUBBLE-FIX");
});

test("buildTaskDetail: empty raw detail -- phrase alone, no dangling separator", () => {
  assert.equal(buildTaskDetail("running a command", ""), "running a command");
});

test("buildTaskDetail: caps combined output at 200 chars", () => {
  const out = buildTaskDetail("running a command", "Ran: " + "a".repeat(300));
  assert.ok(out.length <= 200, `expected <=200 chars, got ${out.length}`);
});

// ─── Bubble text itself (not just the tooltip) never leaks a path either ───

test("v2: the BUBBLE phrase for the coordinator's own leaked command never contains the path", () => {
  const phrase = liveAgentBubbleAction({
    tool: "Bash",
    detail: 'Ran: python "C:/Users/jackw/AppData/Local/Temp/claude/x/scratchpad/p.py"',
    to: "",
  });
  assertNoPathLeak(phrase, "bubble-phrase-python");
});

test("v2: the BUBBLE phrase for a PowerShell drive-letter script run never contains the path", () => {
  const phrase = liveAgentBubbleAction({ tool: "PowerShell", detail: "Ran: powershell -File D:\\Gamma\\x.ps1", to: "" });
  assertNoPathLeak(phrase, "bubble-phrase-powershell");
});

test("v2: the BUBBLE phrase for a bare MSYS-path command never contains the path", () => {
  const phrase = liveAgentBubbleAction({ tool: "Bash", detail: "Ran: /c/Users/jackw/Desktop/42/setup/scripts/a.py", to: "" });
  assertNoPathLeak(phrase, "bubble-phrase-msys");
});

// @ts-nocheck -- same reason as tests/hq-agents.test.ts's own header: an
// explicit ".ts" extension on this relative import is required for plain
// `node --test` to resolve it (Node's own ESM loader, unlike a bundler,
// never extension-guesses); the project tsconfig's moduleResolution
// "bundler" has no allowImportingTsExtensions, which would otherwise fail
// `next build`'s type-check over this one file. Syntax-erasure only.
//
// BUBBLE-FIX (2026-09-15): unit tests for lib/hq-agents.ts#liveAgentBubbleAction
// -- the classifier that turns pulse.py's own already-prefixed row text
// ("Ran: <cmd>", "Editing <path>", ...) into a short human action phrase
// BEFORE any truncation happens (see that function's own header, and
// shortDetail() which now calls it). Colocated with hq-agents.ts rather
// than components/hq/bubbleText.ts (this task's own first-draft location)
// because that file pulls in @/lib/personas + @/lib/crew via the tsconfig
// path alias, which Node's own loader cannot resolve without a bundler --
// see hq-agents.ts's own header comment on this function for the full
// reasoning. Several cases below are real shapes lifted from this
// session's own automation/state/hooks/pulse.jsonl (the cd&&grep case, the
// PowerShell script case, the truncated curl case) rather than invented
// fixtures, per this task's own "only use names that appear in the real
// detail string" rule.
//
// Run: cd dashboard && node --test tests/bubble-text-live-agent.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { liveAgentBubbleAction, type LiveAgentBubbleRow } from "../lib/hq-agents.ts";

function row(overrides: Partial<LiveAgentBubbleRow>): LiveAgentBubbleRow {
  return { tool: "Bash", detail: "", to: "", ...overrides };
}

test("Bash grep -> reading <basename>", () => {
  assert.equal(
    liveAgentBubbleAction(row({ detail: "Ran: grep -n \"LiveAgent\" components/hq/types.ts" })),
    "reading types.ts",
  );
});

test("real shape: cd <path> && grep ... -> the cd preamble is stripped before classifying", () => {
  assert.equal(
    liveAgentBubbleAction(row({
      detail: "Ran: cd C:/Users/jackw/Desktop/42/dashboard && grep -n \"LiveAgents\\b\" components/hq/Scene.tsx",
    })),
    "reading Scene.tsx",
  );
});

test("real shape: a bare cd with the verb truncated away by pulse.py's own 100-char cap", () => {
  // Exactly the DEFECT example from the coordinator's own review: the cd
  // path alone eats the whole 100-char budget, so no "&&"/verb is visible
  // at all -- the honest answer is the generic fallback, never a guess.
  assert.equal(
    liveAgentBubbleAction(row({ detail: "Ran: cd /c/Users/jackw/Desktop/42" })),
    "running a command",
  );
});

test("Bash cat -> reading <basename>", () => {
  assert.equal(liveAgentBubbleAction(row({ detail: "Ran: cat automation/state/hooks/pulse.jsonl" })), "reading pulse.jsonl");
});

test("Bash pytest -> running tests", () => {
  assert.equal(liveAgentBubbleAction(row({ detail: "Ran: pytest setup/hooks/test_doctrine_hooks.py -x" })), "running tests");
});

test("Bash npm test -> running tests", () => {
  assert.equal(liveAgentBubbleAction(row({ detail: "Ran: npm test -- --run" })), "running tests");
});

test("Bash node --test -> running tests", () => {
  assert.equal(liveAgentBubbleAction(row({ detail: "Ran: node --test tests/bubble-scale.test.ts" })), "running tests");
});

test("Bash npm run build -> building the dashboard", () => {
  assert.equal(liveAgentBubbleAction(row({ detail: "Ran: npm run build" })), "building the dashboard");
});

test("Bash git commit -> committing", () => {
  assert.equal(liveAgentBubbleAction(row({ detail: "Ran: git commit -m \"fix(hq): bubble text\"" })), "committing");
});

test("Bash git push -> pushing", () => {
  assert.equal(liveAgentBubbleAction(row({ detail: "Ran: git push origin main" })), "pushing");
});

test("Bash curl -> checking <host or path tail>", () => {
  assert.equal(liveAgentBubbleAction(row({ detail: "Ran: curl -s -o /dev/null -w \"%{http_code}\" http://127.0.0.1:3000/hq" })), "checking 127.0.0.1:3000/hq");
});

test("Bash unknown verb -> running a command (never invents a specific)", () => {
  assert.equal(liveAgentBubbleAction(row({ detail: "Ran: python setup/scripts/commit_scoped.py --help" })), "running a command");
});

test("real shape: PowerShell script (no leading verb this classifier recognizes) -> running a command", () => {
  assert.equal(
    liveAgentBubbleAction(row({
      tool: "PowerShell",
      detail: "Ran: $s = for ($i=0; $i -lt 7; $i++) { Start-Sleep -Seconds 4; \"$((Get-Date",
    })),
    "running a command",
  );
});

test("real shape: PowerShell $var = assignment -> running a command (never guesses a verb)", () => {
  assert.equal(
    liveAgentBubbleAction(row({
      tool: "PowerShell",
      detail: "Ran: $f = 'C:\\Users\\jackw\\Desktop",
    })),
    "running a command",
  );
});

test("real shape: curl truncated before the URL (only a cut quoted flag value survives) -> checking a URL, never garbled text", () => {
  assert.equal(
    liveAgentBubbleAction(row({ detail: 'Ran: curl -s -o /dev/null -w "HTT' })),
    "checking a URL",
  );
});

test("PowerShell git push still classifies the same as Bash", () => {
  assert.equal(liveAgentBubbleAction(row({ tool: "PowerShell", detail: "Ran: git push origin main" })), "pushing");
});

test("Edit -> editing <basename>", () => {
  assert.equal(liveAgentBubbleAction(row({ tool: "Edit", detail: "Editing dashboard/lib/hq-agents.ts" })), "editing hq-agents.ts");
});

test("Write with a bare 'Editing' (no path) -> editing a file", () => {
  assert.equal(liveAgentBubbleAction(row({ tool: "Write", detail: "Editing" })), "editing a file");
});

test("Agent spawn -> spawning <type>", () => {
  assert.equal(liveAgentBubbleAction(row({ tool: "Agent", detail: "Fix bubble text", to: "general-purpose" })), "spawning general-purpose");
});

test("Task with no `to` -> spawning an agent (never invents a type)", () => {
  assert.equal(liveAgentBubbleAction(row({ tool: "Task", detail: "", to: "" })), "spawning an agent");
});

test("Workflow -> running <name>", () => {
  assert.equal(liveAgentBubbleAction(row({ tool: "Workflow", detail: "nightly-eod", to: "nightly-eod" })), "running nightly-eod");
});

test("SendMessage passes its own human text through unchanged", () => {
  assert.equal(
    liveAgentBubbleAction(row({ tool: "SendMessage", detail: "Add LiveAgents reconciliation bug to BUBBLE-FIX" })),
    "Add LiveAgents reconciliation bug to BUBBLE-FIX",
  );
});

test("an unrecognized tool with no detail falls back to `to` then `tool`", () => {
  assert.equal(liveAgentBubbleAction(row({ tool: "", detail: "", to: "" })), "");
});

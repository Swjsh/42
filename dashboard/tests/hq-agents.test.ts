// @ts-nocheck -- same reason as tests/hq-learn.test.ts's own header: this
// file uses an explicit ".ts" extension on its relative import (required for
// plain `node --test` to resolve it; the project tsconfig's
// `moduleResolution: "bundler"` has no `allowImportingTsExtensions`, which
// would otherwise fail `next build`'s project-wide type-check over this one
// file). Purely a syntax-erasure pragma -- has no effect on what actually
// runs.
//
// LIVE-AGENTS pass (2026-09-14): unit tests for lib/hq-agents.ts's PURE
// functions -- the fs reader (readPulseTail/readLiveAgents) is exercised
// live instead, via a real `curl /api/hq` proof against the running
// dashboard (this task's own build-proof step), matching this codebase's
// established convention (see tests/hq-learn.test.ts's own header).
//
// Run: cd dashboard && node --test tests/hq-agents.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parseLocalTsPseudoMs,
  nowLocalPseudoMs,
  parsePulseLines,
  classifyZone,
  classifyPersona,
  buildLiveAgents,
  liveAgentBubbleAction,
  ZONE_NODE_ID,
  PERSONA_NODE_ID,
  TAIL_MAX_LINES,
  type PulseRow,
} from "../lib/hq-agents.ts";

// ─── parseLocalTsPseudoMs / nowLocalPseudoMs ───────────────────────────────

test("parseLocalTsPseudoMs parses pulse.py's own naive-local 'T'-separated shape", () => {
  assert.equal(parseLocalTsPseudoMs("2026-09-14T21:51:01"), Date.UTC(2026, 8, 14, 21, 51, 1));
});

test("parseLocalTsPseudoMs also accepts a space separator", () => {
  assert.equal(parseLocalTsPseudoMs("2026-09-14 21:51:01"), Date.UTC(2026, 8, 14, 21, 51, 1));
});

test("parseLocalTsPseudoMs returns null for an unparseable string, never a guess", () => {
  assert.equal(parseLocalTsPseudoMs("not a timestamp"), null);
  assert.equal(parseLocalTsPseudoMs(""), null);
});

test("nowLocalPseudoMs uses the box's own LOCAL Date getters, not UTC ones", () => {
  // Pin a real epoch instant, then independently reconstruct what
  // nowLocalPseudoMs SHOULD produce using the same local-getter approach
  // this test runs under -- proves the function reads getFullYear/getHours/
  // etc (whatever local zone this test process itself runs in), never
  // getUTCFullYear/getUTCHours, matching pulse.py's own dt.datetime.now()
  // (also local-timezone, never UTC).
  const fixedMs = Date.parse("2026-09-14T21:51:01.000Z");
  const d = new Date(fixedMs);
  const expected = Date.UTC(d.getFullYear(), d.getMonth(), d.getDate(), d.getHours(), d.getMinutes(), d.getSeconds());
  assert.equal(nowLocalPseudoMs(fixedMs), expected);
});

// ─── parsePulseLines ────────────────────────────────────────────────────────

test("parsePulseLines parses well-formed JSONL rows", () => {
  const text = [
    '{"ts":"2026-09-14T21:51:01","event":"act","session_id":"s1","agent_id":"a1","agent_type":"general-purpose","cwd":"C:\\\\42","tool":"Bash","to":"","detail":"Ran: ls"}',
    '{"ts":"2026-09-14T21:51:05","event":"spawn","session_id":"s1","agent_id":"","agent_type":"","cwd":"C:\\\\42","tool":"Agent","to":"gamma","detail":"drive"}',
  ].join("\n");
  const rows = parsePulseLines(text);
  assert.equal(rows.length, 2);
  assert.equal(rows[0].agent_id, "a1");
  assert.equal(rows[1].to, "gamma");
});

test("parsePulseLines skips a malformed line (truncated tail read, corrupt JSON) without throwing", () => {
  const text = [
    '{"ts":"2026-09-14T21:51:00","event":"act","session_id":"s1","agent_id":"","agent_type":"","cwd":"","tool":"","to":"","detail":""}',
    'garbage not json at all',
    '{"ts":"2026-09-14T21:51:0', // byte-offset-truncated first line simulation
    '{"ts":"2026-09-14T21:51:02","event":"act","session_id":"s1","agent_id":"","agent_type":"","cwd":"","tool":"","to":"","detail":""}',
  ].join("\n");
  const rows = parsePulseLines(text);
  assert.equal(rows.length, 2);
});

test("parsePulseLines drops a row missing required string fields (ts/event)", () => {
  const text = '{"event":"act","session_id":"s1"}\n{"ts":"2026-09-14T21:51:00"}';
  assert.equal(parsePulseLines(text).length, 0);
});

test("parsePulseLines caps to the last TAIL_MAX_LINES lines even given a much larger blob", () => {
  const total = TAIL_MAX_LINES + 200;
  const many = Array.from({ length: total }, (_, i) =>
    `{"ts":"2026-09-14T21:51:${String(i % 60).padStart(2, "0")}","event":"act","session_id":"s1","agent_id":"","agent_type":"","cwd":"","tool":"","to":"","detail":"${i}"}`,
  ).join("\n");
  const rows = parsePulseLines(many);
  assert.equal(rows.length, TAIL_MAX_LINES);
  // the last row of the tail must be the LAST row of the input, never an
  // earlier one -- proves the cap keeps the tail, not the head.
  assert.equal(rows[rows.length - 1].detail, String(total - 1));
});

// ─── classifyZone ───────────────────────────────────────────────────────────

test("classifyZone maps dashboard/ to build", () => {
  assert.equal(classifyZone("Editing dashboard/lib/hq-agents.ts"), "build");
});

test("classifyZone maps backtest/ to lab", () => {
  assert.equal(classifyZone("Ran: pytest backtest/tests/test_x.py"), "lab");
});

test("classifyZone maps setup/ and automation/ to ops", () => {
  assert.equal(classifyZone("Editing setup/scripts/foo.ps1"), "ops");
  assert.equal(classifyZone("Editing automation/state/x.json"), "ops");
});

test("classifyZone maps markdown/ to docs", () => {
  assert.equal(classifyZone("Editing markdown/doctrine/LESSONS-LEARNED.md"), "docs");
});

test("classifyZone falls back to hub with no known path", () => {
  assert.equal(classifyZone("Ran: git status"), "hub");
  assert.equal(classifyZone(""), "hub");
});

test("classifyZone normalizes Windows backslashes before matching", () => {
  assert.equal(classifyZone("Editing C:\\Users\\jackw\\Desktop\\42\\dashboard\\lib\\hq.ts"), "build");
});

test("classifyZone precedence: dashboard/ wins over backtest/ when both appear", () => {
  assert.equal(classifyZone("compare dashboard/lib/x.ts against backtest/lib/y.py"), "build");
});

// ─── buildLiveAgents ────────────────────────────────────────────────────────

// A LOCAL (not UTC/"Z") construction, deliberately -- nowLocalPseudoMs derives
// its pseudo-ms from `new Date(nowMs)`'s own LOCAL getters (see that
// function's own doc comment), so NOW must be built the same way every row's
// literal "2026-09-14T21:5x:xx" ts strings are meant to compare against:
// local wall-clock 21:52:00, whatever timezone this test process itself runs
// in. Using a "...Z" (UTC) instant here instead would silently shift by this
// machine's own UTC offset and break every age/spawn/cooling comparison
// below in a way that depends on which timezone happens to run the test.
const NOW = new Date(2026, 8, 14, 21, 52, 0).getTime();

function row(overrides: Partial<PulseRow>): PulseRow {
  return {
    ts: "2026-09-14T21:51:00",
    event: "act",
    session_id: "s1",
    agent_id: "",
    agent_type: "",
    cwd: "",
    tool: "Bash",
    to: "",
    detail: "",
    ...overrides,
  };
}

test("buildLiveAgents groups by agent_id when present", () => {
  const rows = [
    row({ agent_id: "a1", agent_type: "general-purpose", tool: "Edit", ts: "2026-09-14T21:51:00", detail: "Editing dashboard/x.ts" }),
    row({ agent_id: "a1", agent_type: "general-purpose", tool: "Edit", ts: "2026-09-14T21:51:30", detail: "Editing dashboard/y.ts" }),
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents.length, 1);
  assert.equal(agents[0].id, "a1");
  assert.equal(agents[0].label, "general-purpose");
  // BUBBLE-FIX (2026-09-15): lastDetail is now a classified human phrase
  // (liveAgentBubbleAction, this same module), not the raw flattened
  // string -- rawDetail below carries the original verbatim text.
  assert.equal(agents[0].lastDetail, "editing y.ts");
  assert.equal(agents[0].rawDetail, "Editing dashboard/y.ts");
  assert.equal(agents[0].targetZone, ZONE_NODE_ID.build);
});

test("buildLiveAgents groups a main session (empty agent_id) by session_id", () => {
  const rows = [row({ agent_id: "", session_id: "s9", ts: "2026-09-14T21:51:00" })];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents.length, 1);
  assert.equal(agents[0].id, "session:s9");
  assert.equal(agents[0].label, "session");
});

test("buildLiveAgents keeps a main session and its subagent as SEPARATE entries", () => {
  const rows = [
    row({ agent_id: "", session_id: "s1", ts: "2026-09-14T21:51:00", detail: "Ran: git status" }),
    row({ agent_id: "a1", session_id: "s1", agent_type: "general-purpose", ts: "2026-09-14T21:51:10", detail: "Editing backtest/z.py" }),
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents.length, 2);
  const ids = agents.map((a) => a.id).sort();
  assert.deepEqual(ids, ["a1", "session:s1"]);
});

test("buildLiveAgents maps zone from the MOST RECENT matching row, not blanked by a later hub-only row", () => {
  const rows = [
    row({ agent_id: "a1", ts: "2026-09-14T21:51:00", detail: "Editing markdown/doctrine/x.md" }),
    row({ agent_id: "a1", ts: "2026-09-14T21:51:30", detail: "Ran: git status" }), // no path -- must not blank the zone back to hub
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].targetZone, ZONE_NODE_ID.docs);
});

test("buildLiveAgents excludes an agent idle for more than 3 minutes (tool call closed, not open)", () => {
  // A "done" row closes the tool call started at 21:48:00, so the HQ BUG-1 20-min grace
  // window never applies here -- this is testing the plain post-completion idle rule,
  // not an open call (see the dedicated open-tool-call tests further below).
  const rows = [
    row({ agent_id: "a1", event: "act", ts: "2026-09-14T21:48:00" }), // 4 min before NOW (21:52:00)
    row({ agent_id: "a1", event: "done", ts: "2026-09-14T21:48:01" }),
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents.length, 0);
});

test("buildLiveAgents keeps an agent last seen just under the 3-minute idle window", () => {
  const rows = [row({ agent_id: "a1", ts: "2026-09-14T21:49:05" })]; // 2:55 before NOW
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents.length, 1);
});

test("buildLiveAgents marks state 'spawning' for an agent first seen within the last 15s", () => {
  const rows = [row({ agent_id: "a1", ts: "2026-09-14T21:51:50" })]; // 10s before NOW
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].state, "spawning");
});

test("buildLiveAgents marks state 'cooling' close to the idle timeout (tool call closed, not open)", () => {
  const rows = [
    row({ agent_id: "a1", event: "act", ts: "2026-09-14T21:49:00" }), // first seen 3:00 before NOW -- long past the spawn window
    row({ agent_id: "a1", event: "done", ts: "2026-09-14T21:49:01" }), // closes the tool call started above
    row({ agent_id: "a1", event: "act", tool: "Edit", ts: "2026-09-14T21:49:24" }),
    row({ agent_id: "a1", event: "done", tool: "Edit", ts: "2026-09-14T21:49:25" }), // last seen 2:35 (155s) before NOW -- inside the last 30s of the 3min budget (>=150s)
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].state, "cooling");
});

test("buildLiveAgents marks state 'active' otherwise", () => {
  const rows = [
    row({ agent_id: "a1", ts: "2026-09-14T21:50:50" }), // first seen 70s ago
    row({ agent_id: "a1", ts: "2026-09-14T21:51:30" }), // last seen 30s ago -- neither spawning nor cooling
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].state, "active");
});

test("buildLiveAgents caps at 8 agents, most recent first", () => {
  const rows = Array.from({ length: 12 }, (_, i) =>
    row({ agent_id: `a${i}`, ts: `2026-09-14T21:51:${String(i).padStart(2, "0")}` }),
  );
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents.length, 8);
  // most recent (highest index -> latest ts) first
  assert.equal(agents[0].id, "a11");
  assert.equal(agents[7].id, "a4");
});

test("buildLiveAgents skips a row with neither agent_id nor session_id", () => {
  const rows = [row({ agent_id: "", session_id: "" })];
  assert.equal(buildLiveAgents(rows, NOW).length, 0);
});

test("buildLiveAgents skips a row with an unparseable ts rather than treating it as 'now'", () => {
  const rows = [row({ agent_id: "a1", ts: "not-a-timestamp" })];
  assert.equal(buildLiveAgents(rows, NOW).length, 0);
});

test("buildLiveAgents tracks firstTs/lastTs correctly across out-of-order rows", () => {
  const rows = [
    row({ agent_id: "a1", ts: "2026-09-14T21:51:30" }),
    row({ agent_id: "a1", ts: "2026-09-14T21:51:00" }), // arrives "out of order" relative to the row above
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].firstTs, "2026-09-14T21:51:00");
  assert.equal(agents[0].lastTs, "2026-09-14T21:51:30");
});

// ─── HQ BUG-1: open tool-call grace window (2026-09-14) ────────────────────
//
// Real case this section reproduces: agent a797be574c57d1381 had a 244s gap
// (23:30:32 -> 23:34:36 local) running a foreground probe. pulse.jsonl only
// ever wrote the PreToolUse start row, never a completion, so the plain
// 3-min IDLE_TIMEOUT_MS rule alone read the agent as having left mid-work.

test("buildLiveAgents keeps an open (no 'done' row) tool call ACTIVE past the normal 3-min idle window", () => {
  const rows = [
    // start row only, 4 min before NOW (21:52:00) -- would be excluded entirely under
    // the old plain-3-min rule, and would read "cooling" even if the cutoff were bumped
    // without also fixing the STATE computation.
    row({ agent_id: "a1", event: "act", tool: "Bash", ts: "2026-09-14T21:48:00", detail: "Ran: long_probe.py" }),
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents.length, 1);
  assert.equal(agents[0].state, "active");
});

test("buildLiveAgents still despawns an open tool call once the 20-min grace cap elapses", () => {
  const rows = [
    row({ agent_id: "a1", event: "act", tool: "Bash", ts: "2026-09-14T21:31:59" }), // 20:01 before NOW -- just past the cap
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents.length, 0);
});

test("buildLiveAgents keeps an open tool call alive right up to the 20-min grace cap", () => {
  const rows = [
    row({ agent_id: "a1", event: "act", tool: "Bash", ts: "2026-09-14T21:32:01" }), // 19:59 before NOW -- just inside the cap
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents.length, 1);
  assert.equal(agents[0].state, "active");
});

test("buildLiveAgents closes the grace window on a matching 'done' row, reverting to the normal 3-min idle rule", () => {
  const rows = [
    row({ agent_id: "a1", event: "act", tool: "Bash", ts: "2026-09-14T21:45:00", detail: "Ran: long_probe.py" }),
    row({ agent_id: "a1", event: "done", tool: "Bash", ts: "2026-09-14T21:45:05", detail: "" }),
  ];
  // The done row is 6:55 before NOW -- well past the 3-min idle window, and the tool
  // call is closed, so the 20-min grace no longer applies: the agent must be gone.
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents.length, 0);
});

test("buildLiveAgents 'done' row only closes the window for the SAME tool name", () => {
  const rows = [
    row({ agent_id: "a1", event: "act", tool: "Bash", ts: "2026-09-14T21:48:00" }),
    // a "done" for a different tool must not close Bash's still-open window
    row({ agent_id: "a1", event: "done", tool: "Edit", ts: "2026-09-14T21:48:01" }),
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents.length, 1);
  assert.equal(agents[0].state, "active");
});

test("buildLiveAgents: a row written before this fix (no completion ever coming) still expires via the 20-min cap, not forever", () => {
  // Simulates historical pulse.jsonl data written before PostToolUse existed: a start
  // row with literally no possibility of a matching "done" ever arriving. The 20-min
  // cap is exactly the mechanism that prevents such an agent from reading as
  // permanently active.
  const rows = [row({ agent_id: "old-agent", event: "act", tool: "Bash", ts: "2026-09-14T21:00:00" })]; // 52 min stale
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents.length, 0);
});

// ─── HQ BUG-3: tail must cover the open-tool grace window (2026-09-15) ─────
//
// Real defect (coordinator-measured, 2026-09-15 01:55 ET): TAIL_MAX_LINES was 500, but
// commit 645b5cff's "done" row per tool completion roughly doubled the row rate, so
// under heavy fan-out the last 500 rows spanned LESS than ACTIVE_TOOL_GRACE_MS's 20
// minutes (measured tonight: 500 rows / ~56-60 min at lighter load, worse under fan-
// out). Once a still-open long tool call's START row falls out of the tail entirely,
// buildLiveAgents never even sees it -- the agent vanishes mid-work, no matter how
// generous the in-memory grace window is. This reproduces that shape end-to-end
// (parsePulseLines' own line cap, not just buildLiveAgents given a small hand-built
// array) with the open row 900 lines from the tail end -- past the OLD 500-line cap,
// inside the NEW 2000-line one.

function tsAtSeconds(totalSeconds: number): string {
  const hh = Math.floor(totalSeconds / 3600);
  const mm = Math.floor((totalSeconds % 3600) / 60);
  const ss = totalSeconds % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return `2026-09-14T${pad(hh)}:${pad(mm)}:${pad(ss)}`;
}

test("buildLiveAgents keeps an open tool call active when its start row is 900 lines back and 15 min old", () => {
  const NOW_SECONDS = 21 * 3600 + 52 * 60; // 21:52:00, same wall-clock NOW as the suite above
  const TARGET_SECONDS = NOW_SECONDS - 15 * 60; // 21:37:00 -- 15 min old, inside the 20-min grace

  const before = Array.from({ length: 100 }, (_, i) =>
    JSON.stringify({
      ts: tsAtSeconds(TARGET_SECONDS - 300 - i),
      event: "act",
      session_id: "old-noise",
      agent_id: "old-noise",
      agent_type: "general-purpose",
      cwd: "",
      tool: "Bash",
      to: "",
      detail: "Ran: ls",
    }),
  );
  const target = JSON.stringify({
    ts: tsAtSeconds(TARGET_SECONDS),
    event: "act",
    session_id: "s1",
    agent_id: "a1",
    agent_type: "general-purpose",
    cwd: "",
    tool: "Bash",
    to: "",
    detail: "Ran: long_probe.py", // no matching "done" row anywhere -- still open
  });
  // 899 rows after the target -> the target sits exactly 900 lines from the tail end
  // (itself + 899 after it), well past the OLD TAIL_MAX_LINES=500 cap.
  const after = Array.from({ length: 899 }, (_, i) =>
    JSON.stringify({
      ts: tsAtSeconds(TARGET_SECONDS + 1 + i),
      event: "act",
      session_id: "filler",
      agent_id: "filler",
      agent_type: "general-purpose",
      cwd: "",
      tool: "Bash",
      to: "",
      detail: "Ran: ls",
    }),
  );

  const text = [...before, target, ...after].join("\n");
  const rows = parsePulseLines(text);
  // Nothing truncated at 1000 total lines (comfortably under TAIL_MAX_LINES=2000) --
  // proves the tail-selection step itself didn't drop the target row before
  // buildLiveAgents ever saw it.
  assert.equal(rows.length, before.length + 1 + after.length);

  const agents = buildLiveAgents(rows, new Date(2026, 8, 14, 21, 52, 0).getTime());
  const a1 = agents.find((a) => a.id === "a1");
  assert.ok(a1, "agent a1's still-open tool call must survive the tail read");
  assert.equal(a1.state, "active");
});

// ─── HQ BUG-2: liveAgentBubbleAction / classifyCommand target sniffing ─────
//
// Real defect (coordinator review): a truncated grep pattern produced the
// bubble text "working · reading |<Htm" because the old classifier took the
// last non-flag token unconditionally, even a fragment pulled from inside a
// quoted regex.

test("liveAgentBubbleAction falls back to 'searching code' on a grep target from inside a quoted regex (exact reported string)", () => {
  const action = liveAgentBubbleAction({
    tool: "Bash",
    detail:
      'Ran: cd "...\\dashboard" && grep -n "^import\\|bubbleY = \\|bubbleActionTrunc &&\\|<Htm',
    to: "",
  });
  assert.equal(action, "searching code");
});

test("liveAgentBubbleAction names a real grep target when one is present", () => {
  const action = liveAgentBubbleAction({ tool: "Bash", detail: "Ran: grep -n foo dashboard/lib/hq-agents.ts", to: "" });
  assert.equal(action, "searching hq-agents.ts");
});

test("liveAgentBubbleAction falls back to 'reading a file' for cat/sed/head with no real target", () => {
  for (const verb of ["cat", "sed", "head"]) {
    const action = liveAgentBubbleAction({ tool: "Bash", detail: `Ran: ${verb} "$(weird | pipe)"`, to: "" });
    assert.equal(action, "reading a file", `verb=${verb}`);
  }
});

test("liveAgentBubbleAction names a real cat/head target when one is present", () => {
  const action = liveAgentBubbleAction({ tool: "Bash", detail: "Ran: head -n 20 setup/hooks/pulse.py", to: "" });
  assert.equal(action, "reading pulse.py");
});

test("liveAgentBubbleAction classifies a PowerShell '$var = ...' assignment without inventing a target", () => {
  // Fixed 2026-09-15: this asserted "running a script", but a bare `$var =
  // ...` assignment invokes no actual script file -- "running a script" is
  // reserved for a real script-file invocation (python/node/pwsh -File X).
  // Corrected alongside the same bug fix in lib/hq-agents.ts's
  // PS_ASSIGNMENT_RE branch (see tests/bubble-text-live-agent.test.ts's own
  // two cases for the same shape).
  const action = liveAgentBubbleAction({
    tool: "PowerShell",
    detail: 'Ran: $ts = "C:\\Program Files\\Tailscale\\tailscale.exe"; & $ts status',
    to: "",
  });
  assert.equal(action, "running a command");
});

test("liveAgentBubbleAction still classifies a curl command by its URL, unaffected by the target-sniffing fix", () => {
  const action = liveAgentBubbleAction({ tool: "Bash", detail: "Ran: curl -s http://localhost:9222/json/version", to: "" });
  assert.equal(action, "checking localhost:9222/json/version");
});

test("liveAgentBubbleAction falls back to 'checking a URL' when curl's own target got truncated away", () => {
  const action = liveAgentBubbleAction({
    tool: "Bash",
    detail: 'Ran: curl -s -o /dev/null -w "HTT',
    to: "",
  });
  assert.equal(action, "checking a URL");
});

// ─── classifyPersona (PERSONA-VISIT pass, 2026-09-15) ──────────────────────

test("classifyPersona maps Scout's own evidence files", () => {
  assert.equal(classifyPersona("Ran: cat automation/scout/state/scout_output.json")?.id, "Scout");
  assert.equal(classifyPersona("Ran: tail automation/scout/state/scout-feed-summary.json")?.id, "Scout");
});

test("classifyPersona maps Coach's own evidence files", () => {
  assert.equal(classifyPersona("Ran: cat automation/state/station/sectors.json")?.id, "Coach");
  assert.equal(classifyPersona("Ran: cat automation/state/station/coach-notes.json")?.id, "Coach");
});

test("classifyPersona maps Pilot's own evidence files", () => {
  assert.equal(classifyPersona("Ran: tail automation/state/core-decisions.jsonl")?.id, "Pilot");
});

test("classifyPersona maps Analyst's own evidence files", () => {
  assert.equal(classifyPersona("Ran: cat analysis/eod/2026-09-15.md")?.id, "Analyst");
  assert.equal(classifyPersona("Ran: cat journal/mistakes.md")?.id, "Analyst");
});

test("classifyPersona maps Treasurer's own evidence files", () => {
  assert.equal(classifyPersona("Ran: cat analysis/treasury/draft-params-changes.md")?.id, "Treasurer");
});

test("classifyPersona maps Chef's own evidence files", () => {
  assert.equal(classifyPersona("Ran: ls strategy/candidates/_chef-inbox")?.id, "Chef");
  assert.equal(classifyPersona("Ran: cat strategy/candidates/_LEADERBOARD.md")?.id, "Chef");
});

test("classifyPersona maps Gamma's own station evidence files", () => {
  assert.equal(classifyPersona("Ran: tail automation/state/station/crew-events.jsonl")?.id, "Gamma");
  assert.equal(classifyPersona("Ran: cat automation/state/station/loop-ledger.jsonl")?.id, "Gamma");
});

test("classifyPersona returns null for a row with no persona evidence", () => {
  assert.equal(classifyPersona("Editing dashboard/lib/hq-agents.ts"), null);
  assert.equal(classifyPersona("Ran: git status"), null);
});

test("classifyPersona normalizes Windows backslashes before matching", () => {
  assert.equal(classifyPersona("Ran: cat C:\\Users\\jackw\\Desktop\\42\\journal\\mistakes.md")?.id, "Analyst");
});

// ─── PULSE-WIDEN pass (2026-09-15): setup/hooks/pulse.py now populates `to` for
// Bash/PowerShell rows and caps `detail` at 240 chars with a trailing '\u2026' marker
// instead of the old bare 100-char cut. ────────────────────────────────────────────────

test("buildLiveAgents classifies via `to` when a long command's persona filename was cut out of `detail`", () => {
  // detail is truncated (240-char cap + marker) before the filename ever appears, but
  // pulse.py's own `to` extraction still found it in the FULL command -- classifyPersona
  // must catch this via the `to`+`detail` concatenation resolveTargetKey already builds.
  const rows = [
    row({
      agent_id: "a1",
      ts: "2026-09-14T21:51:50",
      tool: "Bash",
      to: "automation/scout/state/scout-feed-summary.json",
      detail: "Ran: python -c \"print(open('automation/scout/state/scout-feed-summary.json').read()" + "x".repeat(200) + "\u2026",
    }),
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].targetZone, PERSONA_NODE_ID.Scout);
  assert.equal(agents[0].interaction?.personaId, "Scout");
});

test("isTruncatedBashDetail (via resolveTargetKey/buildLiveAgents) treats the new '\u2026' marker as truncated, not a coarse-zone signal", () => {
  // No persona-evidence filename anywhere in this row, and detail was cut with the new
  // marker -- must fall back to null/hub, never trust the fragment sitting at the cut.
  const rows = [
    row({
      agent_id: "a1",
      ts: "2026-09-14T21:51:50",
      tool: "Bash",
      to: "",
      detail: "Ran: " + "x".repeat(240) + "\u2026",
    }),
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].interaction, null);
});

// ─── buildLiveAgents: persona targeting + interaction field ────────────────

test("buildLiveAgents targets a persona's own walk-graph node on a single matching row", () => {
  const rows = [row({ agent_id: "a1", ts: "2026-09-14T21:51:50", detail: "Ran: cat automation/state/station/sectors.json" })];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].targetZone, PERSONA_NODE_ID.Coach);
  assert.deepEqual(agents[0].interaction, { personaId: "Coach", phrase: "reading Coach's sector rows" });
});

test("buildLiveAgents targets gamma-desk for Gamma's own station evidence", () => {
  const rows = [row({ agent_id: "a1", ts: "2026-09-14T21:51:50", detail: "Ran: tail automation/state/station/crew-events.jsonl" })];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].targetZone, PERSONA_NODE_ID.Gamma);
  assert.equal(agents[0].targetZone, "gamma-desk");
});

test("buildLiveAgents interaction is null for a plain coarse-zone target", () => {
  const rows = [row({ agent_id: "a1", ts: "2026-09-14T21:51:50", detail: "Editing dashboard/lib/x.ts" })];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].interaction, null);
  assert.equal(agents[0].targetZone, ZONE_NODE_ID.build);
});

// ─── Stickiness: >=2 consecutive rows OR >=20s hold before retargeting ─────

test("buildLiveAgents does NOT retarget on a single alternating row (ping-pong guard)", () => {
  const rows = [
    row({ agent_id: "a1", ts: "2026-09-14T21:51:00", detail: "Editing dashboard/x.ts" }), // claims build immediately (cold start)
    row({ agent_id: "a1", ts: "2026-09-14T21:51:05", detail: "Ran: cat automation/state/station/sectors.json" }), // 1 candidate row, 5s later -- not enough
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].targetZone, ZONE_NODE_ID.build);
});

test("buildLiveAgents retargets after 2 CONSECUTIVE rows for the new target", () => {
  const rows = [
    row({ agent_id: "a1", ts: "2026-09-14T21:51:00", detail: "Editing dashboard/x.ts" }),
    row({ agent_id: "a1", ts: "2026-09-14T21:51:05", detail: "Ran: cat automation/state/station/sectors.json" }), // candidate #1
    row({ agent_id: "a1", ts: "2026-09-14T21:51:08", detail: "Ran: cat automation/state/station/coach-notes.json" }), // candidate #2 (same persona key) -- unseats
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].targetZone, PERSONA_NODE_ID.Coach);
});

test("buildLiveAgents retargets after a >=20s hold even on a single candidate row", () => {
  const rows = [
    row({ agent_id: "a1", ts: "2026-09-14T21:51:00", detail: "Editing dashboard/x.ts" }),
    row({ agent_id: "a1", ts: "2026-09-14T21:51:25", detail: "Ran: cat automation/state/station/sectors.json" }), // 25s later -- past the 20s hold
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].targetZone, PERSONA_NODE_ID.Coach);
});

test("buildLiveAgents: a non-consecutive candidate resets its own counter (real ping-pong never accumulates)", () => {
  const rows = [
    row({ agent_id: "a1", ts: "2026-09-14T21:51:00", detail: "Editing dashboard/x.ts" }), // claims build
    row({ agent_id: "a1", ts: "2026-09-14T21:51:02", detail: "Ran: cat automation/state/station/sectors.json" }), // Coach candidate #1
    row({ agent_id: "a1", ts: "2026-09-14T21:51:04", detail: "Editing dashboard/y.ts" }), // back to build -- resets Coach's candidate count
    row({ agent_id: "a1", ts: "2026-09-14T21:51:06", detail: "Ran: cat automation/state/station/sectors.json" }), // Coach candidate #1 again (not #2)
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].targetZone, ZONE_NODE_ID.build);
});

test("buildLiveAgents: interaction.phrase reflects the STABLE target, not a still-pending candidate row", () => {
  const rows = [
    row({ agent_id: "a1", ts: "2026-09-14T21:51:00", detail: "Ran: cat automation/state/station/sectors.json" }), // claims Coach immediately (cold start)
    row({ agent_id: "a1", ts: "2026-09-14T21:51:05", detail: "Editing dashboard/x.ts" }), // 1 build candidate row -- not enough to unseat
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents[0].targetZone, PERSONA_NODE_ID.Coach);
  assert.deepEqual(agents[0].interaction, { personaId: "Coach", phrase: "reading Coach's sector rows" });
});

// ─── TARGET-FLICKER regression (2026-09-15) ────────────────────────────────
//
// Exact real pulse rows replayed from automation/state/hooks/pulse.jsonl for agent
// a44e2083ea0c251df (2026-09-15T08:01:20 - 08:02:58 local, non-secret shell commands only),
// the agent the hidden probe run 20260915T140056Z-7G3Tke9dNabbLbhLlZxfJ.samples.json.gz
// caught flickering persona-Scout -> ambient-core -> persona-Scout. Root cause: two
// CONSECUTIVE "ls .../grep -i scout" / "ls -la ... | head" listing rows each merely mention
// "automation/" while hunting for the Scout evidence file -- before this fix that satisfied
// TARGET_STICKY_MIN_ROWS as two genuine "zone:ops" signal rows and unseated the already-
// established persona:Scout target. Replayed incrementally (one buildLiveAgents call per
// growing prefix, mirroring the probe's own per-sample snapshots) so the regression this
// guards is "never dips to ambient-core at ANY point", not just the final row's outcome.
const FLICKER_REPLAY_ROWS: PulseRow[] = [
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "spawn", tool: "", to: "general-purpose", ts: "2026-09-15T08:01:20", detail: "subagent started" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "act", tool: "Bash", ts: "2026-09-15T08:01:25", detail: "Ran: python -c \"print(open('automation/state/scout-feed-summary.json',encoding='utf-8').read()[:300])\"" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "done", tool: "Bash", ts: "2026-09-15T08:01:28", detail: "failed" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "act", tool: "Bash", ts: "2026-09-15T08:01:30", detail: "Ran: ls automation/state | grep -i scout" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "done", tool: "Bash", ts: "2026-09-15T08:01:32", detail: "ok" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "act", tool: "Bash", ts: "2026-09-15T08:01:35", detail: "Ran: ls -la automation/state/ | head -20" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "done", tool: "Bash", ts: "2026-09-15T08:01:39", detail: "ok" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "act", tool: "Bash", ts: "2026-09-15T08:01:47", detail: "Ran: find C:/Users/jackw/Desktop/42 -name \"*scout*feed*\" -o -name \"*feed*scout*\" 2>/dev/null | head -10" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "done", tool: "Bash", ts: "2026-09-15T08:01:53", detail: "ok" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "act", tool: "Bash", ts: "2026-09-15T08:01:56", detail: "Ran: python -c \"print(open('automation/scout/state/scout-feed-summary.json',encoding='utf-8').read()[:300" }), // real row: truncated by pulse.py's own 100-char cap, still contains the full filename before the cut
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "done", tool: "Bash", ts: "2026-09-15T08:02:00", detail: "ok" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "act", tool: "Bash", ts: "2026-09-15T08:02:03", detail: "Ran: python -c \"import time; time.sleep(15)\"" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "done", tool: "Bash", ts: "2026-09-15T08:02:22", detail: "ok" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "act", tool: "Bash", ts: "2026-09-15T08:02:25", detail: "Ran: python -c \"print(len(open('automation/scout/state/scout-feed-summary.json',encoding='utf-8').read())" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "done", tool: "Bash", ts: "2026-09-15T08:02:29", detail: "ok" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "act", tool: "Bash", ts: "2026-09-15T08:02:32", detail: "Ran: python -c \"import time; time.sleep(15)\"" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "done", tool: "Bash", ts: "2026-09-15T08:02:51", detail: "ok" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "act", tool: "Bash", ts: "2026-09-15T08:02:54", detail: "Ran: python -c \"import json; d=json.load(open('automation/scout/state/scout-feed-summary.json',encoding='" }),
  row({ agent_id: "a44e2083ea0c251df", agent_type: "general-purpose", event: "done", tool: "Bash", ts: "2026-09-15T08:02:58", detail: "ok" }),
];

const REPLAY_NOW = new Date(2026, 8, 15, 8, 3, 0).getTime();

test("TARGET-FLICKER regression: replayed real pulse rows for a44e2083ea0c251df never leave persona-Scout once claimed", () => {
  let sawRealTarget = false;
  for (let i = 1; i <= FLICKER_REPLAY_ROWS.length; i++) {
    const agents = buildLiveAgents(FLICKER_REPLAY_ROWS.slice(0, i), REPLAY_NOW);
    const zone = agents[0]?.targetZone;
    if (zone === PERSONA_NODE_ID.Scout) sawRealTarget = true;
    if (sawRealTarget) {
      assert.equal(
        zone,
        PERSONA_NODE_ID.Scout,
        `row ${i} (${FLICKER_REPLAY_ROWS[i - 1].ts} ${FLICKER_REPLAY_ROWS[i - 1].detail}) flickered target to ${zone}`
      );
    }
  }
  assert.equal(sawRealTarget, true, "fixture never actually claimed persona-Scout -- test would be vacuous");
});

test("TARGET-FLICKER regression: final state is persona-Scout with the real evidence phrase", () => {
  const agents = buildLiveAgents(FLICKER_REPLAY_ROWS, REPLAY_NOW);
  assert.equal(agents[0].targetZone, PERSONA_NODE_ID.Scout);
  assert.equal(agents[0].interaction?.personaId, "Scout");
});

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
  buildLiveAgents,
  ZONE_NODE_ID,
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

test("parsePulseLines caps to the last 500 lines even given a much larger blob", () => {
  const many = Array.from({ length: 700 }, (_, i) =>
    `{"ts":"2026-09-14T21:51:${String(i % 60).padStart(2, "0")}","event":"act","session_id":"s1","agent_id":"","agent_type":"","cwd":"","tool":"","to":"","detail":"${i}"}`,
  ).join("\n");
  const rows = parsePulseLines(many);
  assert.equal(rows.length, 500);
  // the last row of the tail must be the LAST row of the input, never an
  // earlier one -- proves the cap keeps the tail, not the head.
  assert.equal(rows[rows.length - 1].detail, "699");
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
    row({ agent_id: "a1", agent_type: "general-purpose", ts: "2026-09-14T21:51:00", detail: "Editing dashboard/x.ts" }),
    row({ agent_id: "a1", agent_type: "general-purpose", ts: "2026-09-14T21:51:30", detail: "Editing dashboard/y.ts" }),
  ];
  const agents = buildLiveAgents(rows, NOW);
  assert.equal(agents.length, 1);
  assert.equal(agents[0].id, "a1");
  assert.equal(agents[0].label, "general-purpose");
  assert.equal(agents[0].lastDetail, "Editing dashboard/y.ts");
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

test("buildLiveAgents excludes an agent idle for more than 3 minutes", () => {
  const rows = [row({ agent_id: "a1", ts: "2026-09-14T21:48:00" })]; // 4 min before NOW (21:52:00)
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

test("buildLiveAgents marks state 'cooling' close to the idle timeout", () => {
  const rows = [
    row({ agent_id: "a1", ts: "2026-09-14T21:49:00" }), // first seen 3:00 before NOW -- long past the spawn window
    row({ agent_id: "a1", ts: "2026-09-14T21:49:25" }), // last seen 2:35 (155s) before NOW -- inside the last 30s of the 3min budget (>=150s)
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

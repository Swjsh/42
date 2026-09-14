// @ts-nocheck -- this file intentionally uses explicit ".ts" extensions on
// its relative imports (required for plain `node --test` to resolve them --
// verified this session, Node's ESM loader does NOT auto-resolve
// extensionless TS-to-TS specifiers). The project tsconfig.json's shared
// `moduleResolution: "bundler"` does not have `allowImportingTsExtensions`
// enabled (out of this builder's scope to change -- shared by every other
// builder in this checkout), which would otherwise fail `next build`'s
// project-wide type-check (TS5097) over this one file. `@ts-nocheck` is
// scoped to exactly this file and has zero effect on Node's own type
// stripping at runtime (a purely syntax-erasure step, indifferent to this
// pragma) -- the tests below still run for real, see the header below.
// PANEL-2 (2026-09-14): unit tests for lib/hq-runtime.ts's PURE functions
// only (CSV parsing + role classification) -- the fs/child_process readers
// are exercised live instead (curl proof against the real route), matching
// this codebase's existing convention (lib/hq.ts's own capJsonlText is the
// precedent: "pure function... specifically so it's unit-testable").
//
// No test runner existed in dashboard/package.json at the time this was
// written (checked first, per this task's own instruction) -- Node 24 runs
// TypeScript natively (type-stripping, unflagged since Node 23.6), so this
// runs directly via `node --test dashboard/tests/hq-runtime.test.ts` with no
// added dependency. lib/hq-runtime.ts's own header explains why its pure
// half never imports anything path-aliased ("@/...") or fs-touching: that is
// exactly what keeps this runnable without a bundler.
//
// Run: cd dashboard && node --test tests/hq-runtime.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  parseCsvLine,
  parseTasklistCsv,
  countProcessImages,
  classifyRole,
  type RosterPersonaFixture,
} from "../lib/hq-runtime.ts";
import type { PersonaState } from "../lib/personas.ts";

// ─── parseCsvLine ───────────────────────────────────────────────────────────

test("parseCsvLine splits a plain quoted CSV row", () => {
  const fields = parseCsvLine('"python.exe","31276","Console","1","4,220 K"');
  assert.deepEqual(fields, ["python.exe", "31276", "Console", "1", "4,220 K"]);
});

test("parseCsvLine does not split on a comma embedded inside a quoted field", () => {
  // tasklist's own real shape: Mem Usage commonly exceeds 1MB, e.g. "331,024 K".
  // A naive split(",") would misparse this into 6 fields instead of 5.
  const fields = parseCsvLine('"claude.exe","2168","Console","1","331,024 K"');
  assert.equal(fields.length, 5);
  assert.equal(fields[4], "331,024 K");
});

test("parseCsvLine preserves a space inside an unquoted-looking image name", () => {
  // Real tasklist output for Ollama's tray process: the image name itself
  // contains a literal space ("ollama app.exe"), which must survive intact.
  const fields = parseCsvLine('"ollama app.exe","4832","Console","1","54,428 K"');
  assert.equal(fields[0], "ollama app.exe");
});

// ─── parseTasklistCsv ───────────────────────────────────────────────────────

test("parseTasklistCsv extracts image names and skips blank lines", () => {
  const fixture = [
    '"System Idle Process","0","Services","0","8 K"',
    "",
    '"python.exe","31276","Console","1","4,220 K"',
    '"claude.exe","2168","Console","1","331,024 K"',
    "   ",
  ].join("\r\n");
  const images = parseTasklistCsv(fixture);
  assert.deepEqual(images, ["System Idle Process", "python.exe", "claude.exe"]);
});

test("parseTasklistCsv returns an empty array for empty input, never throws", () => {
  assert.deepEqual(parseTasklistCsv(""), []);
  assert.deepEqual(parseTasklistCsv("\r\n\r\n"), []);
});

// ─── countProcessImages ─────────────────────────────────────────────────────

test("countProcessImages counts by exact, case-insensitive image name", () => {
  const images = [
    "pythonw.exe", "pythonw.exe", "PYTHONW.EXE",
    "python.exe",
    "claude.exe", "claude.exe", "claude.exe",
    "node.exe",
    "svchost.exe", "svchost.exe",
  ];
  const counts = countProcessImages(images);
  assert.equal(counts.pythonw, 3);
  assert.equal(counts.python, 1);
  assert.equal(counts.claude, 3);
  assert.equal(counts.node, 1);
  assert.equal(counts.total, images.length);
});

test("countProcessImages never lets 'ollama.exe' false-positive as ollama_llama_server (substring collision: o-LLAMA)", () => {
  // Real live capture this session: ollama.exe + "ollama app.exe" running,
  // zero ollama_llama_server.exe. A `.includes('llama')` classifier would
  // wrongly count both of the former as the latter, since "ollama" itself
  // contains the substring "llama".
  const images = ["ollama.exe", "ollama app.exe"];
  const counts = countProcessImages(images);
  assert.equal(counts.ollama, 2);
  assert.equal(counts.ollama_llama_server, 0);
});

test("countProcessImages counts a real ollama_llama_server.exe when it is actually present", () => {
  const counts = countProcessImages(["ollama.exe", "ollama_llama_server.exe"]);
  assert.equal(counts.ollama, 1);
  assert.equal(counts.ollama_llama_server, 1);
});

// ─── classifyRole ───────────────────────────────────────────────────────────

const NOW = Date.parse("2026-09-14T22:21:00.000Z"); // 18:21 ET (EDT, UTC-4)

function persona(overrides: Partial<PersonaState>): PersonaState {
  return {
    name: "Pilot", emoji: "x", color: "#fff", role: "", soulFile: "", schedule: "",
    status: "GREEN", lastFireISO: null, lastFireResult: "",
    deliverable: { path: "", exists: true, mtimeISO: null, ageMin: null },
    logTail: [], recentOutput: null, guardrailsDeniedTools: [], quietReason: null,
    ...overrides,
  };
}

const pilotRoster: RosterPersonaFixture = {
  name: "Pilot", cadence: "every 1 min, 09:30-15:55 ET wd via Gamma_HeartbeatCore",
  tasks: ["Gamma_HeartbeatCore"],
};

test("classifyRole: fresh evidence + a live process of the right kind -> liveNow true, 'mid-fire' evidence", () => {
  const role = classifyRole(
    "Pilot", pilotRoster, new Set(),
    persona({ name: "Pilot", lastFireISO: new Date(NOW - 60_000).toISOString() }), // 1 min ago
    { python: 2, pythonw: 3, ollama: 0, ollama_llama_server: 0, claude: 5, node: 2, total: 20 },
    NOW,
  );
  assert.equal(role.runtime, "python-script");
  assert.equal(role.host, "this PC");
  assert.equal(role.liveNow, true);
  assert.match(role.evidence, /plausibly mid-fire/);
});

test("classifyRole: stale evidence -> liveNow false, 'scheduled, last ran' evidence, never claims the process belongs to this role", () => {
  const role = classifyRole(
    "Pilot", pilotRoster, new Set(),
    persona({ name: "Pilot", lastFireISO: new Date(NOW - 20 * 60_000).toISOString() }), // 20 min ago
    { python: 2, pythonw: 3, ollama: 0, ollama_llama_server: 0, claude: 5, node: 2, total: 20 },
    NOW,
  );
  assert.equal(role.liveNow, false);
  assert.match(role.evidence, /scheduled, last ran/);
  assert.match(role.evidence, /not attributable to this role alone/);
});

test("classifyRole: a task confirmed DISABLED reports host 'none' and a DISABLED nextFire, regardless of process counts", () => {
  const role = classifyRole(
    "Analyst",
    { name: "Analyst", cadence: "16:45 ET weekdays via Gamma_AnalystEodReview", tasks: ["Gamma_AnalystEodReview"] },
    new Set(["Gamma_AnalystEodReview"]),
    persona({ name: "Analyst", lastFireISO: new Date(NOW - 60_000).toISOString() }),
    { python: 0, pythonw: 0, ollama: 0, ollama_llama_server: 0, claude: 25, node: 6, total: 300 },
    NOW,
  );
  assert.equal(role.host, "none");
  assert.equal(role.liveNow, false);
  assert.match(role.nextFire, /^DISABLED/);
  assert.match(role.evidence, /DISABLED in Task Scheduler/);
});

test("classifyRole: a persona with only SOME of its tasks disabled is not treated as fully dark", () => {
  const role = classifyRole(
    "Gamma (Manager)",
    { name: "Gamma (Manager)", cadence: "every 30 min via Gamma_Station", tasks: ["Gamma_Station", "Gamma_Conductor"] },
    new Set(["Gamma_Conductor"]), // only the Conductor half is disabled
    persona({ name: "Gamma (Manager)", lastFireISO: new Date(NOW - 60_000).toISOString() }),
    { python: 0, pythonw: 0, ollama: 1, ollama_llama_server: 0, claude: 0, node: 0, total: 50 },
    NOW,
  );
  assert.equal(role.host, "this PC");
  assert.equal(role.liveNow, true);
  assert.equal(role.runtime, "local-llm");
});

const zeroCounts = { python: 0, pythonw: 0, ollama: 0, ollama_llama_server: 0, claude: 0, node: 0, total: 0 };

test("classifyRole: missing roster fixture (fs read failed) degrades honestly instead of throwing", () => {
  const role = classifyRole("Pilot", null, new Set(), null, zeroCounts, NOW);
  assert.equal(role.name, "Pilot");
  assert.match(role.schedule, /unknown/);
  assert.equal(role.liveNow, false);
  assert.equal(role.evidence, "no fire on file yet");
});

test("classifyRole: a null process table (tasklist spawn failed) is reported as unknown, never silently folded into 'no fire on file'", () => {
  const role = classifyRole("Pilot", pilotRoster, new Set(), persona({ name: "Pilot" }), null, NOW);
  assert.equal(role.evidence, "process table unavailable this poll -- last evidence ? ET");
});

test("classifyRole: an unknown persona name never throws, degrades to runtime 'none'", () => {
  const role = classifyRole("Nobody", null, new Set(), null, zeroCounts, NOW);
  assert.equal(role.runtime, "none");
  assert.equal(role.host, "none");
});

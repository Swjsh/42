// @ts-nocheck -- same reason as tests/hq-agents.test.ts's own header: this
// file uses explicit ".ts" extensions on its relative imports (required for
// plain `node --test` to resolve them; the project tsconfig's
// `moduleResolution: "bundler"` has no `allowImportingTsExtensions`, which
// would otherwise fail `next build`'s project-wide type-check over this one
// file). Purely a syntax-erasure pragma -- has no effect on what actually
// runs.
//
// PERF FIX (perf/hq-api pass, 2026-09-15, coordinator-directed): /api/hq's
// warm latency was dominated by three readers that either read a large file
// in full on every poll (lib/hq.ts#readCryptoTwinTail -- a 147MB+ file, just
// to get its last line) or shelled out / re-read a bounded tail with no
// cache at all (lib/station.ts#readOllamaPs, lib/hq-agents.ts#readPulseTail).
// This file proves the fix for each:
//   1. readCryptoTwinTail / readPulseTail: a cache keyed on the file's own
//      (mtimeMs, size) -- unchanged file between polls costs one stat(), not
//      a read; a real file change (new mtime+size) always re-reads.
//   2. readOllamaPs: a plain TTL cache -- two calls inside the TTL window
//      return the SAME object (proves no second `ollama ps` spawn); a call
//      after the TTL expires returns a NEW object (proves it refetched).
//
// GAMMA_WORKSPACE / GAMMA_PULSE_PATH are read ONCE, at module-load time
// (lib/workspace.ts#WORKSPACE_ROOT, lib/hq-agents.ts's own PULSE_PATH), and
// lib/hq.ts's own internal `import ... from "./workspace"` resolves to
// Node's ESM module cache independent of any query string THIS file's own
// import specifier carries -- so unlike a module with no such shared
// dependency, changing GAMMA_WORKSPACE mid-file and re-importing would NOT
// actually repoint lib/hq.ts at a new workspace after the first import. Both
// env vars are therefore set exactly ONCE, at the top of this file, to ONE
// throwaway temp workspace used by every test below; each test mutates the
// FILE CONTENTS (never the path) between assertions instead. No production
// file is ever touched by this suite.
//
// Run: cd dashboard && node --test tests/hq-perf-cache.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";

const workspace = await fs.mkdtemp(path.join(os.tmpdir(), "hq-perf-cache-"));
process.env.GAMMA_WORKSPACE = workspace;

const decisionsPath = path.join(workspace, "automation", "state", "crypto-twin", "decisions.jsonl");
await fs.mkdir(path.dirname(decisionsPath), { recursive: true });

const pulsePath = path.join(workspace, "pulse.jsonl");
process.env.GAMMA_PULSE_PATH = pulsePath;

// Imported ONCE, after both env vars are already set -- see this file's own
// header for why a later re-import can't repoint lib/hq.ts at a different
// workspace anyway.
const { readCryptoTwinTail } = await import("../lib/hq.ts");
const { readPulseTail } = await import("../lib/hq-agents.ts");
const { readOllamaPs } = await import("../lib/station.ts");

// ─── lib/hq.ts#readCryptoTwinTail -- (mtime, size)-keyed cache ─────────────

test("readCryptoTwinTail: unchanged file hits the cache (same object); a real change invalidates it", async () => {
  await fs.writeFile(decisionsPath, '{"action":"HOLD","ts_et":"2026-09-15 00:00:00 ET"}\n');

  const first = await readCryptoTwinTail();
  assert.equal(first.last_action, "HOLD");

  const second = await readCryptoTwinTail();
  // Identity, not just equality: a real second read would allocate a NEW
  // object even with identical content -- only a cache HIT returns the
  // exact same reference.
  assert.strictEqual(first, second, "unchanged (mtime,size) must hit the cache, not re-read");

  // Append a genuinely new row -- both mtime AND size change.
  await fs.appendFile(decisionsPath, '{"action":"BUY","ts_et":"2026-09-15 00:01:00 ET"}\n');
  const third = await readCryptoTwinTail();

  assert.notStrictEqual(second, third, "a changed file must never serve the stale cached object");
  assert.equal(third.last_action, "BUY", "must reflect the NEW last line, never a fabricated/stale value");
});

// ─── lib/hq-agents.ts#readPulseTail -- (mtime, size)-keyed cache ───────────
//
// readPulseTail returns a plain string (a primitive has no identity to
// assert on), so this proves caching the same way readCryptoTwinTail's own
// object-identity test does it structurally: force the file back to the
// EXACT SAME (mtimeMs, size) it had after the first read (via fs.utimes,
// after overwriting with same-length-but-different content) and confirm the
// second call still returns the FIRST call's content -- a real re-read would
// return the new content instead. Then grow the file for real and confirm
// the tail DOES update, so this isn't just "the file never changes" masking
// a broken cache.

test("readPulseTail: cache is keyed on (mtime,size) -- unchanged key stays cached, a real change refetches", async () => {
  const rowA = JSON.stringify({ ts: "2026-09-15T00:00:00", event: "act", session_id: "s1" });
  await fs.writeFile(pulsePath, rowA + "\n");
  // Pin mtime to a whole-millisecond Date up front -- Windows/NTFS utimes
  // rounds sub-ms fractions, so setting it explicitly ONCE here (rather than
  // trusting whatever sub-ms mtime the raw writeFile produced) guarantees
  // the SECOND fs.utimes call below (using this same rounded value) lands on
  // an mtimeMs that is bit-for-bit reproducible, not a fixture flake.
  const pinnedMtime = new Date(Math.floor(Date.now()));
  await fs.utimes(pulsePath, pinnedMtime, pinnedMtime);
  const statAfterA = await fs.stat(pulsePath);

  const first = await readPulseTail();
  assert.match(first, /s1/);

  // Overwrite with a SAME-BYTE-LENGTH but different row, then force mtime
  // back to the exact value it had after writing rowA -- if the cache is
  // truly keyed on (mtime,size) and both are now identical to what the
  // first read saw, a correct implementation must return the FIRST read's
  // text, not re-read this new content.
  const rowB = JSON.stringify({ ts: "2026-09-15T00:00:00", event: "act", session_id: "s2" });
  assert.equal(rowB.length, rowA.length, "test fixture bug: rows must be byte-identical length");
  await fs.writeFile(pulsePath, rowB + "\n");
  await fs.utimes(pulsePath, statAfterA.atime, statAfterA.mtime);
  const statAfterB = await fs.stat(pulsePath);
  assert.equal(statAfterB.mtimeMs, statAfterA.mtimeMs, "test fixture bug: mtime forcing did not take");
  assert.equal(statAfterB.size, statAfterA.size);

  const second = await readPulseTail();
  assert.equal(second, first, "identical (mtime,size) must serve the cached tail, never re-read");
  assert.doesNotMatch(second, /s2/, "must not silently pick up new-on-disk bytes the cache key says are unchanged");

  // Now a REAL change (file grows) -- must refetch.
  await fs.appendFile(pulsePath, JSON.stringify({ ts: "2026-09-15T00:00:05", event: "act", session_id: "s3" }) + "\n");
  const third = await readPulseTail();
  assert.match(third, /s3/, "a grown file must be re-read, never serve a stale cached tail");
});

// ─── lib/station.ts#readOllamaPs -- plain TTL cache ────────────────────────
//
// No `ollama` binary is expected in this test environment -- readOllamaPs's
// own fail-open catch still runs (and still caches) on that ENOENT, so the
// TTL behavior is exercised exactly the same way it would be for a real
// success: object identity distinguishes a cache hit (same reference) from a
// refetch (a new object, even though the fail-open VALUE is identical
// either way).

test("readOllamaPs: caches inside the TTL window (same object), refetches once it expires (new object)", async () => {
  const first = await readOllamaPs();
  const second = await readOllamaPs();
  assert.strictEqual(first, second, "a call inside the TTL window must hit the cache, not spawn again");

  // Matches lib/station.ts's own OLLAMA_CACHE_MS (2000ms) -- comfortably
  // past it so this isn't racing the boundary.
  await new Promise((resolve) => setTimeout(resolve, 2200));
  const third = await readOllamaPs();
  assert.notStrictEqual(second, third, "past the TTL, the cache must refetch rather than serve a stale object forever");
});

// ─── perf/hq-api pass (2026-09-15) additions -- lib/personas.ts ────────────
//
// safeCollectCompany() (app/api/hq/route.ts) -> collectCompany() is /api/hq's
// largest remaining warm-latency source after the fix above (measured this
// pass: ~40-100ms of a ~56ms median poll). Profiling (temporary console.time
// wraps, removed before commit) found the cost was NOT any one collector's
// own logic -- collectScout/Coach/Analyst/Chef/Treasurer/GammaManager each
// cost <1ms in isolation -- but two specific reads with no cache at all:
//   1. computeHandoffs()'s dirListing() on strategy/candidates/_chef-inbox
//      (200+ files): the original loop stat'd every file SEQUENTIALLY,
//      ~12-18ms warm by itself -- the single largest cost found anywhere in
//      the whole safeCollectCompany() graph.
//   2. collectPilot()'s two calls into lib/hq.ts's readCoreDecisionsLatest/
//      readCoreDecisionsToday, each an independent seeked read of a 120MB+
//      append-only ledger with no cache in hq.ts (out of this pass's scope
//      to edit) -- ~10-15ms warm.
// Both are now (mtimeMs,size)-keyed caches, matching this file's own
// pre-existing house pattern above. This section proves each, plus the
// shared readJson/readJsonlTail/readText helpers every OTHER collector in
// personas.ts routes through, all of which got the same treatment for free.
//
// Run: cd dashboard && node --import ./tests/resolve-ts-extensionless.loader.mjs --test tests/hq-perf-cache.test.ts

// Reuses the SAME `workspace` this file already created at the top (and
// already pointed GAMMA_WORKSPACE at) rather than a second temp dir --
// lib/workspace.ts's WORKSPACE_ROOT is `process.env.GAMMA_WORKSPACE ?? ...`
// evaluated ONCE at lib/hq.ts's own module-load time (already imported
// above, before this section runs), so reassigning the env var here would
// NOT repoint that already-frozen constant (same reasoning this file's own
// header already gives for why every env var is set exactly once). lib/
// personas.ts computes its OWN ROOT as path.join(process.cwd(), "..")
// (deliberately independent of WORKSPACE_ROOT -- see that file's header) --
// chdir'ing into a "dashboard" subdirectory of the SAME workspace, before
// personas.ts is first imported, makes personas.ts's ROOT resolve to the
// identical directory lib/hq.ts's readCoreDecisionsLatest/Today (called
// THROUGH readCoreDecisionsCached, never re-implemented) already reads via
// paths.coreDecisions.
const personasWorkspace = workspace;
const personasDashboardDir = path.join(personasWorkspace, "dashboard");
await fs.mkdir(personasDashboardDir, { recursive: true });
const originalCwd = process.cwd();
process.chdir(personasDashboardDir);
const {
  readJson: personasReadJson,
  readJsonlTail: personasReadJsonlTail,
  readText: personasReadText,
  dirListing: personasDirListing,
  readCoreDecisionsCached,
} = await import("../lib/personas.ts");
process.chdir(originalCwd); // restore -- nothing else in this file depends on cwd

// ─── readJson -- (mtime,size)-keyed cache ──────────────────────────────────

test("personas readJson: unchanged file hits the cache (same object); a real change invalidates it", async () => {
  const p = path.join(personasWorkspace, "readjson-fixture.json");
  await fs.writeFile(p, JSON.stringify({ v: 1 }));

  const first = await personasReadJson(p);
  assert.deepEqual(first, { v: 1 });
  const second = await personasReadJson(p);
  assert.strictEqual(first, second, "unchanged (mtime,size) must hit the cache, not re-parse");

  await fs.writeFile(p, JSON.stringify({ v: 2, extra: "padding-changes-size" }));
  const third = await personasReadJson(p);
  assert.notStrictEqual(second, third, "a changed file must never serve the stale cached object");
  assert.deepEqual(third, { v: 2, extra: "padding-changes-size" }, "must reflect the NEW content, never fabricated/stale");
});

test("personas readJson: a missing file returns null every call and is never cached as a false negative", async () => {
  const p = path.join(personasWorkspace, "readjson-missing.json");
  const first = await personasReadJson(p);
  assert.equal(first, null);
  await fs.writeFile(p, JSON.stringify({ arrived: true }));
  const second = await personasReadJson(p);
  assert.deepEqual(second, { arrived: true }, "a file that shows up later must be read, never stuck on a cached miss");
});

// ─── readJsonlTail -- (mtime,size)-keyed cache, keyed per (path,n) ─────────

test("personas readJsonlTail: unchanged file hits the cache; append invalidates it; distinct `n` values stay independent", async () => {
  const p = path.join(personasWorkspace, "readjsonltail-fixture.jsonl");
  await fs.writeFile(p, [{ i: 1 }, { i: 2 }, { i: 3 }].map((r) => JSON.stringify(r)).join("\n") + "\n");

  const firstN2 = await personasReadJsonlTail(p, 2);
  assert.deepEqual(firstN2, [{ i: 2 }, { i: 3 }]);
  const secondN2 = await personasReadJsonlTail(p, 2);
  assert.strictEqual(firstN2, secondN2, "unchanged (mtime,size) must hit the cache for the same n");

  // A different `n` against the SAME unchanged file must not reuse the n=2
  // cache entry -- proves the cache key includes n, not just the path.
  const n3 = await personasReadJsonlTail(p, 3);
  assert.deepEqual(n3, [{ i: 1 }, { i: 2 }, { i: 3 }]);

  await fs.appendFile(p, JSON.stringify({ i: 4 }) + "\n");
  const thirdN2 = await personasReadJsonlTail(p, 2);
  assert.notStrictEqual(secondN2, thirdN2, "a grown file must be re-read, never serve a stale cached tail");
  assert.deepEqual(thirdN2, [{ i: 3 }, { i: 4 }]);
});

// ─── readText -- (mtime,size)-keyed cache, keyed per (path,maxBytes) ───────

test("personas readText: unchanged file hits the cache; a real change invalidates it", async () => {
  const p = path.join(personasWorkspace, "readtext-fixture.md");
  await fs.writeFile(p, "hello world");

  const first = await personasReadText(p, 800);
  assert.equal(first, "hello world");
  const second = await personasReadText(p, 800);
  assert.strictEqual(first, second, "unchanged (mtime,size) must hit the cache, not re-read the file");

  await fs.writeFile(p, "goodbye world, now longer");
  const third = await personasReadText(p, 800);
  assert.notStrictEqual(second, third);
  assert.equal(third, "goodbye world, now longer");
});

// ─── dirListing -- directory-(mtime,size)-keyed cache, PARALLEL stat ───────
//
// This is the fix for the ~12-18ms chef-inbox cost this pass profiled: the
// original implementation stat'd every directory entry in a sequential
// for-await loop; this proves BOTH halves -- the cache (repeat calls against
// an unchanged directory return the identical array) AND correctness (a
// newly-added file is picked up, never masked by a stale cached listing).

test("personas dirListing: unchanged directory hits the cache (same array); adding a file invalidates it", async () => {
  const dir = await fs.mkdtemp(path.join(personasWorkspace, "dirlisting-"));
  await fs.writeFile(path.join(dir, "a.md"), "a");
  await fs.writeFile(path.join(dir, "b.md"), "b");

  const first = await personasDirListing(dir);
  assert.equal(first.length, 2);
  const second = await personasDirListing(dir);
  assert.strictEqual(first, second, "an unchanged directory must hit the cache, not re-stat every entry");

  await fs.writeFile(path.join(dir, "c.md"), "c");
  const third = await personasDirListing(dir);
  assert.notStrictEqual(second, third, "a directory that gained an entry must never serve a stale listing");
  assert.equal(third.length, 3, "the newly-added file must actually appear, never silently dropped for cache freshness");
});

// ─── readCoreDecisionsCached -- wraps lib/hq.ts's own readCoreDecisionsLatest/
//     readCoreDecisionsToday (never reimplemented) with a cache on THEIR
//     source file's own (mtimeMs,size), since those two functions have no
//     cache of their own and hq.ts is out of this pass's scope to edit. ────

test("personas readCoreDecisionsCached: unchanged core-decisions.jsonl hits the cache; a new tick invalidates it and reflects the real new row", async () => {
  const coreDecisionsPath = path.join(personasWorkspace, "automation", "state", "core-decisions.jsonl");
  await fs.mkdir(path.dirname(coreDecisionsPath), { recursive: true });
  const rowSafe1 = { ts_et: `${todayEtForCoreDecisions()}T10:00:00`, account: "safe", verdict: "HOLD" };
  await fs.writeFile(coreDecisionsPath, JSON.stringify(rowSafe1) + "\n");

  const first = await readCoreDecisionsCached();
  assert.equal(first.core.safe?.verdict, "HOLD");
  const second = await readCoreDecisionsCached();
  assert.strictEqual(first, second, "unchanged (mtime,size) must hit the cache, not re-seek-and-reread the ledger");

  const rowSafe2 = { ts_et: `${todayEtForCoreDecisions()}T10:01:00`, account: "safe", verdict: "ENTER" };
  await fs.appendFile(coreDecisionsPath, JSON.stringify(rowSafe2) + "\n");
  const third = await readCoreDecisionsCached();
  assert.notStrictEqual(second, third, "a genuine new tick must never be masked by a stale cached read");
  assert.equal(third.core.safe?.verdict, "ENTER", "must reflect the real newest row, never a fabricated/stale value");
});

function todayEtForCoreDecisions(): string {
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(new Date());
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

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

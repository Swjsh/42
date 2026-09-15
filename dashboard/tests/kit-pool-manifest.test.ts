// Manifest regression test for the pool registrations added in b224a186 and
// 5d5c4ec8 (hub chairs x6 + bay second-chairs x8 into the DeskCluster pool,
// craters x5 + craterLarge x3 in Ground.tsx, wall cables x3 in
// HubInterior.tsx, supportsHigh x2 in BaseProps.tsx) plus the earlier
// DeskCluster/CeilingLight pooling in SetKit.tsx itself.
//
// This is a STATIC SOURCE SCAN, not a render test: it asserts each mount
// site's source text still calls `usePooledKitProps(...)` for the expected
// GLB path -- so a future edit that swaps a pooled `usePooledKitProps(...)`
// call back to an un-pooled `<KitProp .../>` mount (silently regressing the
// draw-call fix these commits shipped) fails this test even though nothing
// crashes and nothing renders visibly wrong.
//
// Run: cd dashboard && node --test tests/kit-pool-manifest.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import { promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DASHBOARD_ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const HQ_DIR = path.join(DASHBOARD_ROOT, "components", "hq");

async function readSource(file: string): Promise<string> {
  return fs.readFile(path.join(HQ_DIR, file), "utf8");
}

/** Finds every `usePooledKitProps(<arg0>, ...)` call in `source` and returns
 * the raw first-argument expression text for each -- e.g.
 * `KIT_PATHS.furniture.chair` or `CABLES_PATH`. Deliberately a plain regex
 * scan (not a real parser) -- proportionate for a manifest test whose job is
 * "does this call still exist with this argument", not full AST analysis. */
function findPooledPropsArgs(source: string): string[] {
  const calls: string[] = [];
  const re = /usePooledKitProps\(\s*([^,]+?)\s*,/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(source)) !== null) {
    calls.push(m[1].trim());
  }
  return calls;
}

/** Resolves a symbol used as usePooledKitProps' first arg back to the GLB
 * path it constitutes, for the small closed set this manifest cares about
 * (either a direct `KIT_PATHS....` member-access expression, used verbatim,
 * or a local `const NAME = "...glb"` -- e.g. HubInterior.tsx's own
 * CABLES_PATH -- resolved by scanning the same file's top-level consts). */
function resolveLocalPathConst(source: string, symbol: string): string | undefined {
  const re = new RegExp(`const\\s+${symbol}\\s*=\\s*"([^"]+)"`);
  const m = re.exec(source);
  return m?.[1];
}

test("SetKit.tsx: DeskCluster registers table + chair, HubRoom registers CeilingLight, via the pool API", async () => {
  const source = await readSource("SetKit.tsx");
  const args = findPooledPropsArgs(source);
  assert.ok(args.includes("KIT_PATHS.furniture.table"), "DeskCluster's table mount must call usePooledKitProps(KIT_PATHS.furniture.table, ...)");
  assert.ok(args.includes("KIT_PATHS.furniture.chair"), "DeskCluster's chair mount must call usePooledKitProps(KIT_PATHS.furniture.chair, ...)");
  assert.ok(args.includes("KIT_PATHS.lights"), "HubRoom/DepartmentBayShell's CeilingLight mount must call usePooledKitProps(KIT_PATHS.lights, ...)");
});

test("HubInterior.tsx: hub chairs pool into KIT_PATHS.furniture.chair, wall cables pool into CABLES_PATH", async () => {
  const source = await readSource("HubInterior.tsx");
  const args = findPooledPropsArgs(source);
  assert.ok(args.includes("KIT_PATHS.furniture.chair"), "hub chairs must call usePooledKitProps(KIT_PATHS.furniture.chair, ...) -- un-pooling this regresses 5d5c4ec8");
  assert.ok(args.includes("CABLES_PATH"), "wall cables must call usePooledKitProps(CABLES_PATH, ...) -- un-pooling this regresses 5d5c4ec8");

  const cablesPath = resolveLocalPathConst(source, "CABLES_PATH");
  assert.equal(cablesPath, "/hq-assets/kenney-modular-space-kit/cables.glb", "CABLES_PATH must still point at the real cables GLB");
});

test("BayInterior.tsx: bay second-chairs pool into the SAME KIT_PATHS.furniture.chair pool as the hub", async () => {
  const source = await readSource("BayInterior.tsx");
  const args = findPooledPropsArgs(source);
  assert.ok(args.includes("KIT_PATHS.furniture.chair"), "bay second-chairs must call usePooledKitProps(KIT_PATHS.furniture.chair, ...) -- un-pooling this regresses 5d5c4ec8");
});

test("Ground.tsx: craters and craterLarge both pool AND both mount an InstancedKitPool consumer", async () => {
  const source = await readSource("Ground.tsx");
  const args = findPooledPropsArgs(source);
  assert.ok(args.includes("KIT_PATHS.terrain.crater"), "craters must call usePooledKitProps(KIT_PATHS.terrain.crater, ...) -- un-pooling this regresses 5d5c4ec8");
  assert.ok(args.includes("KIT_PATHS.terrain.craterLarge"), "craterLarge must call usePooledKitProps(KIT_PATHS.terrain.craterLarge, ...) -- un-pooling this regresses 5d5c4ec8");

  // The registration alone is inert without a matching <InstancedKitPool>
  // consumer actually mounted somewhere -- guard that too.
  assert.match(source, /<InstancedKitPool\s+path=\{KIT_PATHS\.terrain\.crater\}/, "an InstancedKitPool must consume the crater pool");
  assert.match(source, /<InstancedKitPool\s+path=\{KIT_PATHS\.terrain\.craterLarge\}/, "an InstancedKitPool must consume the craterLarge pool");
});

test("BaseProps.tsx: supportsHigh pools AND mounts an InstancedKitPool consumer", async () => {
  const source = await readSource("BaseProps.tsx");
  const args = findPooledPropsArgs(source);
  assert.ok(args.includes("KIT_PATHS.baseProps.supportsHigh"), "supportsHigh must call usePooledKitProps(KIT_PATHS.baseProps.supportsHigh, ...) -- un-pooling this regresses 5d5c4ec8");
  assert.match(source, /<InstancedKitPool\s+path=\{KIT_PATHS\.baseProps\.supportsHigh\}/, "an InstancedKitPool must consume the supportsHigh pool");
});

test("every pool registration in the manifest has a matching InstancedKitPool mount somewhere in components/hq", async () => {
  // Cross-file check: a usePooledKitProps registration with no corresponding
  // <InstancedKitPool> anywhere renders nothing -- collect every
  // (path-expr, variant) pair registered vs every one consumed, across the
  // whole directory, and assert the registered set is a subset of the
  // consumed set for the paths this manifest cares about.
  const files = await fs.readdir(HQ_DIR);
  const tsxFiles = files.filter((f) => f.endsWith(".tsx"));
  const sources = new Map<string, string>();
  for (const f of tsxFiles) sources.set(f, await fs.readFile(path.join(HQ_DIR, f), "utf8"));

  const allSource = Array.from(sources.values()).join("\n");
  const consumedPathArgs = new Set<string>();
  const poolRe = /<InstancedKitPool\s+path=\{([^}]+)\}/g;
  let m: RegExpExecArray | null;
  while ((m = poolRe.exec(allSource)) !== null) consumedPathArgs.add(m[1].trim());

  const expectedManifest = [
    "KIT_PATHS.furniture.chair",
    "KIT_PATHS.furniture.table",
    "KIT_PATHS.lights",
    "KIT_PATHS.terrain.crater",
    "KIT_PATHS.terrain.craterLarge",
    "KIT_PATHS.baseProps.supportsHigh",
    "CABLES_PATH",
  ];
  for (const expr of expectedManifest) {
    assert.ok(consumedPathArgs.has(expr), `expected an <InstancedKitPool path={${expr}} .../> mount somewhere in components/hq`);
  }
});

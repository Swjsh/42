// GATE-PROP-OPEN pass (2026-09-15): regression coverage for the fix to the
// GATE-PROP pass (commit a3a446c9) -- a real-screen capture showed the
// campus gate reading as SHUT because gate-door.glb's "native" variant (the
// SAME shared pool the 8 bay doors + hallway doors already use) renders
// BOTH the frame AND a separate "door" leaf mesh that fills the opening.
// The fix: CampusGate now registers into its OWN "frame-only" variant,
// consumed by a NEW <InstancedKitPool ... excludeMeshNames={["door"]} />
// mount, so only the campus gate drops the leaf -- bay/hallway doors are
// untouched.
//
// This is a plain Node test (no react-three-fiber render harness in this
// repo -- see kit-pool-manifest.test.ts's own header for why every other
// InstancedKitPool regression test in this suite is a static source scan
// rather than an actual render), split into two parts:
//   1. A from-scratch, dependency-free GLB reader (same "parse the binary
//      directly" approach as dashboard/scripts/glb_extents.mjs, not
//      imported from it since that script is a CLI entrypoint with no
//      exports) that proves gate-door.glb really does ship the frame and
//      the door leaf as two SEPARATE mesh primitives -- the fact the fix
//      in SetKit.tsx#InstancedKitPool's excludeMeshNames depends on.
//   2. A static source scan (SetKit.tsx) proving: CampusGate registers
//      under "frame-only" (not "native"), a matching frame-only pool is
//      mounted excluding mesh "door", and the bay-door/hallway-door
//      "native" registrations are UNCHANGED (still both present, still
//      unfiltered) -- so a future edit that quietly reverts CampusGate to
//      "native" (re-shutting the gate) or that widens the exclusion onto
//      the shared "native" pool (silently un-doing every OTHER gate-door
//      mount) fails this test even though nothing crashes.
//
// Run: cd dashboard && node --test tests/campus-gate-open.test.ts
// (or the full suite: cd dashboard && npm test)

import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync, promises as fs } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const DASHBOARD_ROOT = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const GATE_DOOR_GLB = path.join(DASHBOARD_ROOT, "public", "hq-assets", "kenney-modular-space-kit", "gate-door.glb");
const SET_KIT_TSX = path.join(DASHBOARD_ROOT, "components", "hq", "SetKit.tsx");

const GLB_MAGIC = 0x46546c67; // "glTF"
const CHUNK_TYPE_JSON = 0x4e4f534a; // "JSON"

/** Minimal .glb JSON-chunk reader -- glTF binary layout is a 12-byte header
 * plus length-prefixed chunks (Khronos glTF 2.0 spec); this test only needs
 * the JSON chunk's own `nodes`/`meshes` arrays (names + parent/child shape),
 * never accessor/buffer data, so it stops there rather than pulling in a
 * full loader. */
function readGlbJson(filePath: string): any {
  const buf = readFileSync(filePath);
  if (buf.length < 12 || buf.readUInt32LE(0) !== GLB_MAGIC) {
    throw new Error(`${filePath}: not a valid .glb (bad magic at byte 0)`);
  }
  const totalLength = buf.readUInt32LE(8);
  let offset = 12;
  while (offset < totalLength) {
    const chunkLength = buf.readUInt32LE(offset);
    const chunkType = buf.readUInt32LE(offset + 4);
    if (chunkType === CHUNK_TYPE_JSON) {
      const data = buf.subarray(offset + 8, offset + 8 + chunkLength);
      return JSON.parse(data.toString("utf8"));
    }
    offset += 8 + chunkLength;
  }
  throw new Error(`${filePath}: no JSON chunk found`);
}

test("gate-door.glb ships the frame and the door leaf as two SEPARATE mesh-bearing nodes", () => {
  const json = readGlbJson(GATE_DOOR_GLB);
  const nodes: any[] = json.nodes ?? [];
  const meshes: any[] = json.meshes ?? [];

  const meshBearingNodes = nodes.filter((n) => n.mesh !== undefined);
  assert.equal(meshBearingNodes.length, 2, "expected exactly 2 mesh-bearing nodes (frame + door leaf) in gate-door.glb");

  const rootNode = meshBearingNodes.find((n) => (n.children ?? []).length > 0);
  const leafNode = meshBearingNodes.find((n) => n !== rootNode);
  assert.ok(rootNode, "expected a root frame node with children");
  assert.ok(leafNode, "expected a child door-leaf node");
  assert.ok((rootNode.children ?? []).includes(nodes.indexOf(leafNode)), "the door leaf node must be a CHILD of the frame node");

  const leafMeshName = meshes[leafNode.mesh]?.name;
  assert.equal(leafMeshName, "door", "the door-leaf mesh primitive must be named \"door\" -- SetKit.tsx#GATE_DOOR_LEAF_MESH_NAMES depends on this exact name");

  const rootMeshName = meshes[rootNode.mesh]?.name;
  assert.notEqual(rootMeshName, "door", "the frame's own mesh must NOT be named \"door\" (or excludeMeshNames would drop the frame too)");
});

async function readSetKitSource(): Promise<string> {
  return fs.readFile(SET_KIT_TSX, "utf8");
}

test("CampusGate registers into its OWN \"frame-only\" gate-door variant, not the shared \"native\" one", async () => {
  const source = await readSetKitSource();
  const campusGateBody = source.slice(source.indexOf("export function CampusGate("), source.indexOf("\ninterface DeskClusterProps"));
  assert.match(
    campusGateBody,
    /usePooledKitProps\(\s*KIT_PATHS\.architecture\.gateDoor\s*,\s*"frame-only"\s*,\s*placements\s*\)/,
    "CampusGate must register via usePooledKitProps(KIT_PATHS.architecture.gateDoor, \"frame-only\", placements) -- registering under \"native\" would re-share the leaf-bearing bay/hallway-door pool and re-shut the gate",
  );
});

test("HubRoom mounts a frame-only InstancedKitPool for gate-door.glb that excludes the door-leaf mesh", async () => {
  const source = await readSetKitSource();
  assert.match(
    source,
    /<InstancedKitPool[\s\S]{0,200}?path=\{KIT_PATHS\.architecture\.gateDoor\}[\s\S]{0,200}?variant="frame-only"[\s\S]{0,200}?excludeMeshNames=\{GATE_DOOR_LEAF_MESH_NAMES\}/,
    "expected an <InstancedKitPool path={KIT_PATHS.architecture.gateDoor} variant=\"frame-only\" excludeMeshNames={GATE_DOOR_LEAF_MESH_NAMES} /> mount",
  );
  assert.match(
    source,
    /GATE_DOOR_LEAF_MESH_NAMES\s*=\s*\[\s*"door"\s*\]/,
    "GATE_DOOR_LEAF_MESH_NAMES must resolve to the exact GLB mesh name (\"door\") gate-door.glb's leaf primitive uses",
  );
});

test("the bay-door and hallway-door \"native\" gate-door registrations are UNCHANGED -- still 2, still unfiltered", async () => {
  const source = await readSetKitSource();
  const nativeGateDoorRegs = source.match(/usePooledKitProps\(\s*KIT_PATHS\.architecture\.gateDoor\s*,\s*"native"\s*,/g) ?? [];
  assert.equal(
    nativeGateDoorRegs.length,
    2,
    "expected exactly 2 usePooledKitProps(KIT_PATHS.architecture.gateDoor, \"native\", ...) call sites (DepartmentBayShell's bay door + CorridorRun's hallway door) -- a count drift here means a bay/hallway door mount was accidentally moved off the shared pool",
  );

  const nativeGateDoorPool = source.match(/<InstancedKitPool\s+path=\{KIT_PATHS\.architecture\.gateDoor\}\s+variant="native"[^/]*\/>/);
  assert.ok(nativeGateDoorPool, "expected the original <InstancedKitPool path={KIT_PATHS.architecture.gateDoor} variant=\"native\" .../> mount to still exist");
  assert.doesNotMatch(
    nativeGateDoorPool![0],
    /excludeMeshNames/,
    "the shared \"native\" gate-door pool must NEVER gain excludeMeshNames -- that would silently remove the door leaf from every bay/hallway door too, not just the campus gate",
  );
});

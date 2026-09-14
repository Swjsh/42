#!/usr/bin/env node
"use strict";

// ─── GLB extents measuring tool (2026-09-14, HALLWAY-FIX builder) ──────────
// Task: the campus-cross hallways (SetKit.tsx#CorridorRun) render with their
// walls standing ACROSS the walkway instead of along it (J: "the walls are
// the wrong way -- how are those going to contain anything?"). The existing
// code (and a prior pass's own comment in SetKit.tsx) assumed every
// Modular-Space-Kit architecture piece shares gate-door/room's "-Z is front"
// convention. That convention is easy to eyeball for an ASYMMETRIC piece
// (gate-door.glb is 4.2 wide x 1.4 deep -- obviously thin along its facing
// axis) but the corridor pieces are logged as roughly SQUARE footprints
// (corridor 4x4, corridor-wide 8x8, corner 4x4, intersection 4x4) -- for a
// square piece "which axis is -Z front" is NOT visually self-evident from an
// overall bounding box alone, and that prior comment was never actually
// backed by a per-node measurement. This script measures instead of
// assuming: it walks each GLB's real node hierarchy (accumulating every
// node's own translation/rotation/scale into a world matrix -- a flat
// accessor min/max read WITHOUT applying node transforms would silently
// mis-report the axes for any mesh sitting under a rotated node, which is
// exactly the kind of authoring choice that would explain a "square"
// footprint hiding a real long axis) and reports:
//   1. the whole-piece root-space AABB (min/max/size per axis) -- confirms
//      floor Y (should start at/near 0 for a flush floor) and overall
//      footprint.
//   2. EVERY mesh-bearing node's own root-space AABB + name -- since a
//      corridor's walls are two distinct elongated sub-meshes, their
//      individual bounding boxes reveal which axis they run LONG along
//      (the travel/open axis) and which axis they sit at the EXTREMES of
//      (the wall axis) even when the piece's overall footprint is square.
//
// Pure Node.js, zero npm dependencies -- binary glTF (.glb) is a tiny format
// (12-byte header + length-prefixed JSON/BIN chunks, see the Khronos glTF
// 2.0 spec) and everything needed (accessor min/max, node TRS/matrix) is
// already plain JSON once that chunk is parsed; a full glTF loader (three.js
// GLTFLoader etc.) would pull in a WebGL/DOM-shaped API this simple offline
// read has no use for.
//
// Usage: node dashboard/scripts/glb_extents.mjs <file.glb> [<file2.glb> ...]

import { readFileSync } from "node:fs";

const GLB_MAGIC = 0x46546c67; // "glTF"
const CHUNK_TYPE_JSON = 0x4e4f534a; // "JSON"
const CHUNK_TYPE_BIN = 0x004e4942; // "BIN\0"

/** Parses a .glb file's JSON chunk (and returns the BIN chunk too, for the
 * no-min/max fallback path below). Throws loudly on a malformed file --
 * never silently returns partial data (this project's own failure-honesty
 * rule: a measuring tool that lies about its input is worse than one that
 * crashes). */
function readGlb(path) {
  const buf = readFileSync(path);
  if (buf.length < 12 || buf.readUInt32LE(0) !== GLB_MAGIC) {
    throw new Error(`${path}: not a valid .glb (bad magic at byte 0)`);
  }
  const totalLength = buf.readUInt32LE(8);
  let offset = 12;
  let json = null;
  let bin = null;
  while (offset < totalLength) {
    const chunkLength = buf.readUInt32LE(offset);
    const chunkType = buf.readUInt32LE(offset + 4);
    const chunkData = buf.subarray(offset + 8, offset + 8 + chunkLength);
    if (chunkType === CHUNK_TYPE_JSON) json = JSON.parse(chunkData.toString("utf8"));
    else if (chunkType === CHUNK_TYPE_BIN) bin = chunkData;
    offset += 8 + chunkLength;
  }
  if (!json) throw new Error(`${path}: no JSON chunk found`);
  return { json, bin };
}

// ─── Minimal column-major mat4 (matches glTF's own storage convention and
// three.js's Matrix4 layout -- verified against three.js's own compose()
// source before relying on it here, not reconstructed from memory) ────────
function mat4Identity() {
  return [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
}

/** Returns a*b (b applied first, then a) -- the standard scene-graph
 * accumulation order: world = parentWorld * childLocal. */
function mat4Multiply(a, b) {
  const out = new Array(16).fill(0);
  for (let c = 0; c < 4; c++) {
    for (let r = 0; r < 4; r++) {
      let sum = 0;
      for (let k = 0; k < 4; k++) sum += a[k * 4 + r] * b[c * 4 + k];
      out[c * 4 + r] = sum;
    }
  }
  return out;
}

function mat4FromTRS(t, r, s) {
  const [x, y, z, w] = r;
  const x2 = x + x, y2 = y + y, z2 = z + z;
  const xx = x * x2, xy = x * y2, xz = x * z2;
  const yy = y * y2, yz = y * z2, zz = z * z2;
  const wx = w * x2, wy = w * y2, wz = w * z2;
  const sx = s[0], sy = s[1], sz = s[2];
  return [
    (1 - (yy + zz)) * sx, (xy + wz) * sx, (xz - wy) * sx, 0,
    (xy - wz) * sy, (1 - (xx + zz)) * sy, (yz + wx) * sy, 0,
    (xz + wy) * sz, (yz - wx) * sz, (1 - (xx + yy)) * sz, 0,
    t[0], t[1], t[2], 1,
  ];
}

function nodeLocalMatrix(node) {
  if (node.matrix) return node.matrix;
  const t = node.translation ?? [0, 0, 0];
  const r = node.rotation ?? [0, 0, 0, 1];
  const s = node.scale ?? [1, 1, 1];
  return mat4FromTRS(t, r, s);
}

function mat4TransformPoint(m, p) {
  const [x, y, z] = p;
  return [
    m[0] * x + m[4] * y + m[8] * z + m[12],
    m[1] * x + m[5] * y + m[9] * z + m[13],
    m[2] * x + m[6] * y + m[10] * z + m[14],
  ];
}

const COMPONENT_BYTES = { 5120: 1, 5121: 1, 5122: 2, 5123: 2, 5125: 4, 5126: 4 };
const TYPE_COMPONENTS = { SCALAR: 1, VEC2: 2, VEC3: 3, VEC4: 4, MAT4: 16 };

/** Fallback for the (spec-legal but rare) case an exporter omitted
 * POSITION's min/max: reads the raw buffer and computes it directly rather
 * than silently skipping the mesh. Only handles the float/VEC3 case
 * (the only one any POSITION accessor in practice ever uses). */
function computeAccessorMinMaxFromBuffer(json, bin, accessor) {
  if (accessor.componentType !== 5126 || accessor.type !== "VEC3") {
    throw new Error(`unsupported POSITION accessor shape (componentType=${accessor.componentType}, type=${accessor.type})`);
  }
  const bufferView = json.bufferViews[accessor.bufferView];
  const byteStride = bufferView.byteStride || TYPE_COMPONENTS.VEC3 * COMPONENT_BYTES[5126];
  const base = (bufferView.byteOffset || 0) + (accessor.byteOffset || 0);
  const min = [Infinity, Infinity, Infinity];
  const max = [-Infinity, -Infinity, -Infinity];
  for (let i = 0; i < accessor.count; i++) {
    const o = base + i * byteStride;
    for (let c = 0; c < 3; c++) {
      const v = bin.readFloatLE(o + c * 4);
      if (v < min[c]) min[c] = v;
      if (v > max[c]) max[c] = v;
    }
  }
  return { min, max };
}

/** Generic full-accessor reader (every component, not just min/max) -- needed
 * for the wall-axis analysis below, which has to look at REAL triangle
 * geometry, not just a bounding box (see this file's own header: the
 * corridor pieces are single merged meshes with square footprints, so an
 * overall AABB genuinely cannot tell wall-axis from open-axis). Handles the
 * componentTypes glTF actually uses for POSITION (5126 FLOAT) and indices
 * (5121/5123/5125 U8/U16/U32) -- the only ones any of these kit assets need. */
function readComponent(buf, offset, componentType) {
  switch (componentType) {
    case 5120: return buf.readInt8(offset);
    case 5121: return buf.readUInt8(offset);
    case 5122: return buf.readInt16LE(offset);
    case 5123: return buf.readUInt16LE(offset);
    case 5125: return buf.readUInt32LE(offset);
    case 5126: return buf.readFloatLE(offset);
    default: throw new Error(`unknown componentType ${componentType}`);
  }
}

function readAccessorFull(json, bin, accessorIdx) {
  const acc = json.accessors[accessorIdx];
  const numComponents = TYPE_COMPONENTS[acc.type];
  const compSize = COMPONENT_BYTES[acc.componentType];
  const bufferView = json.bufferViews[acc.bufferView];
  const byteStride = bufferView.byteStride || numComponents * compSize;
  const base = (bufferView.byteOffset || 0) + (acc.byteOffset || 0);
  const out = new Array(acc.count);
  for (let i = 0; i < acc.count; i++) {
    const o = base + i * byteStride;
    const comp = new Array(numComponents);
    for (let c = 0; c < numComponents; c++) comp[c] = readComponent(bin, o + c * compSize, acc.componentType);
    out[i] = numComponents === 1 ? comp[0] : comp;
  }
  return out;
}

function vec3Sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
function vec3Cross(a, b) {
  return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
}

/** The real disambiguator for a square-footprint piece: classifies every
 * triangle by its face normal. A floor/ceiling triangle's normal points
 * mostly along Y (up/down) -- excluded via the `any > 0.35` gate. What's
 * left are wall-like (near-vertical-surface) triangles; a wall panel
 * spanning the Y-Z plane at a fixed X (the geometry of a corridor's SIDE
 * wall, running the full length of the travel axis) has a normal pointing
 * along X, and a wall panel spanning X-Y at fixed Z has a normal along Z.
 * Summing AREA (not triangle count -- a few big panels should outweigh many
 * tiny bevel/trim triangles) per axis tells us directly which axis the solid
 * material blocks: that's the WALL axis; the other horizontal axis is the
 * open/travel axis a hallway must be laid out along. */
function analyzeWallAxis(positions, indices) {
  // T-JUNCTION follow-up (2026-09-14, coordinator: "the intersection piece
  // is a symmetric 4-way; a T needs its outward opening closed -- check it
  // against the geometry"): axis totals alone (wallAreaX/wallAreaZ) can't
  // answer "which of the 4 sides is open" -- a piece could have walls on
  // BOTH +Z and -Z (a real corridor, both sides "facing Z") or on only ONE
  // of them (a dead-end). Bucket by SIGN too, via each wall-like triangle's
  // own centroid position on its dominant axis -- a triangle sitting near
  // x=+2 with a normal facing X contributes to the "+X side has wall
  // material" bucket, not just "the X axis has wall material" in general.
  let wallAreaX = 0, wallAreaZ = 0, horizArea = 0, otherArea = 0;
  const bySide = { xPos: 0, xNeg: 0, zPos: 0, zNeg: 0 };
  for (let i = 0; i + 2 < indices.length; i += 3) {
    const a = positions[indices[i]], b = positions[indices[i + 1]], c = positions[indices[i + 2]];
    const normal = vec3Cross(vec3Sub(b, a), vec3Sub(c, a));
    const len = Math.hypot(normal[0], normal[1], normal[2]);
    if (len < 1e-9) continue; // degenerate triangle
    const area = 0.5 * len;
    const nx = Math.abs(normal[0] / len), ny = Math.abs(normal[1] / len), nz = Math.abs(normal[2] / len);
    if (ny > 0.35) { horizArea += area; continue; }
    const centroid = [(a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3, (a[2] + b[2] + c[2]) / 3];
    if (nx > nz * 1.05) {
      wallAreaX += area;
      if (centroid[0] >= 0) bySide.xPos += area; else bySide.xNeg += area;
    } else if (nz > nx * 1.05) {
      wallAreaZ += area;
      if (centroid[2] >= 0) bySide.zPos += area; else bySide.zNeg += area;
    } else {
      otherArea += area;
    }
  }
  return { wallAreaX, wallAreaZ, horizArea, otherArea, bySide };
}

function measure(path) {
  const { json, bin } = readGlb(path);
  const sceneIdx = json.scene ?? 0;
  const scene = json.scenes?.[sceneIdx];
  if (!scene) throw new Error(`${path}: no default scene`);
  const nodes = json.nodes ?? [];
  const meshes = json.meshes ?? [];
  const accessors = json.accessors ?? [];

  const globalMin = [Infinity, Infinity, Infinity];
  const globalMax = [-Infinity, -Infinity, -Infinity];
  const perNode = [];
  const wallAxis = { wallAreaX: 0, wallAreaZ: 0, horizArea: 0, otherArea: 0, bySide: { xPos: 0, xNeg: 0, zPos: 0, zNeg: 0 } };

  function visit(nodeIdx, parentMatrix, ancestry) {
    const node = nodes[nodeIdx];
    const local = nodeLocalMatrix(node);
    const world = mat4Multiply(parentMatrix, local);
    const label = node.name ?? `#${nodeIdx}`;
    const path2 = ancestry ? `${ancestry}/${label}` : label;
    if (node.mesh !== undefined) {
      const mesh = meshes[node.mesh];
      mesh.primitives.forEach((prim, primIdx) => {
        const posIdx = prim.attributes.POSITION;
        if (posIdx === undefined) return;
        const acc = accessors[posIdx];
        const { min, max } = acc.min && acc.max ? { min: acc.min, max: acc.max } : computeAccessorMinMaxFromBuffer(json, bin, acc);
        const [minx, miny, minz] = min;
        const [maxx, maxy, maxz] = max;
        const corners = [
          [minx, miny, minz], [maxx, miny, minz], [minx, maxy, minz], [minx, miny, maxz],
          [maxx, maxy, minz], [maxx, miny, maxz], [minx, maxy, maxz], [maxx, maxy, maxz],
        ];
        const nodeMin = [Infinity, Infinity, Infinity];
        const nodeMax = [-Infinity, -Infinity, -Infinity];
        for (const c of corners) {
          const wc = mat4TransformPoint(world, c);
          for (let i = 0; i < 3; i++) {
            if (wc[i] < globalMin[i]) globalMin[i] = wc[i];
            if (wc[i] > globalMax[i]) globalMax[i] = wc[i];
            if (wc[i] < nodeMin[i]) nodeMin[i] = wc[i];
            if (wc[i] > nodeMax[i]) nodeMax[i] = wc[i];
          }
        }
        perNode.push({
          nodePath: path2,
          meshName: mesh.name ?? `mesh#${node.mesh}`,
          primIdx,
          min: nodeMin,
          max: nodeMax,
          size: [nodeMax[0] - nodeMin[0], nodeMax[1] - nodeMin[1], nodeMax[2] - nodeMin[2]],
        });

        // Wall-axis analysis (see analyzeWallAxis's own header) -- full
        // vertex positions transformed into root space, plus this
        // primitive's own index buffer (or the implicit 0,1,2.. sequence
        // glTF specifies for a non-indexed primitive).
        const mode = prim.mode ?? 4; // default TRIANGLES per spec
        if (mode === 4) {
          const rawPositions = readAccessorFull(json, bin, posIdx);
          const worldPositions = rawPositions.map((p) => mat4TransformPoint(world, p));
          const indices = prim.indices !== undefined
            ? readAccessorFull(json, bin, prim.indices)
            : worldPositions.map((_, i) => i);
          const a = analyzeWallAxis(worldPositions, indices);
          wallAxis.wallAreaX += a.wallAreaX;
          wallAxis.wallAreaZ += a.wallAreaZ;
          wallAxis.horizArea += a.horizArea;
          wallAxis.otherArea += a.otherArea;
          wallAxis.bySide.xPos += a.bySide.xPos;
          wallAxis.bySide.xNeg += a.bySide.xNeg;
          wallAxis.bySide.zPos += a.bySide.zPos;
          wallAxis.bySide.zNeg += a.bySide.zNeg;
        }
      });
    }
    for (const child of node.children ?? []) visit(child, world, path2);
  }

  for (const rootIdx of scene.nodes) visit(rootIdx, mat4Identity(), "");

  const size = [globalMax[0] - globalMin[0], globalMax[1] - globalMin[1], globalMax[2] - globalMin[2]];
  return { path, globalMin, globalMax, size, perNode, wallAxis };
}

function fmt(n) {
  return n.toFixed(3).padStart(8);
}

function report(path) {
  const r = measure(path);
  console.log(`\n=== ${path} ===`);
  console.log(`root-space AABB  min=[${r.globalMin.map(fmt)} ]  max=[${r.globalMax.map(fmt)} ]`);
  console.log(`size             X=${r.size[0].toFixed(3)}  Y(height)=${r.size[1].toFixed(3)}  Z=${r.size[2].toFixed(3)}`);
  console.log(`floor Y starts at ${r.globalMin[1].toFixed(3)} (should be ~0 for a flush floor)`);
  const xzRatio = r.size[0] / r.size[2];
  console.log(`X/Z ratio ${xzRatio.toFixed(3)} (~1.0 = square footprint -- long axis NOT determinable from the overall box alone, see wall-axis analysis below)`);
  const { wallAreaX, wallAreaZ, horizArea, otherArea, bySide } = r.wallAxis;
  console.log(`-- wall-axis analysis (triangle-normal area sums, see analyzeWallAxis's own header) --`);
  console.log(`  horizontal (floor/ceiling-like, |ny|>0.35) area = ${horizArea.toFixed(3)}`);
  console.log(`  wall-like area facing X (blocks X movement)    = ${wallAreaX.toFixed(3)}`);
  console.log(`  wall-like area facing Z (blocks Z movement)    = ${wallAreaZ.toFixed(3)}`);
  if (otherArea > 1e-6) console.log(`  unclassified/diagonal area = ${otherArea.toFixed(3)}`);
  const margin = 1.3;
  let verdict;
  if (wallAreaX > wallAreaZ * margin && wallAreaX > 0.01) verdict = "WALLS BLOCK X -> OPEN/TRAVEL AXIS IS Z";
  else if (wallAreaZ > wallAreaX * margin && wallAreaZ > 0.01) verdict = "WALLS BLOCK Z -> OPEN/TRAVEL AXIS IS X";
  else verdict = "SYMMETRIC (walls on all 4 sides, or no vertical wall geometry at all -- e.g. an open junction/floor-only piece)";
  console.log(`  VERDICT: ${verdict}`);
  // Per-side breakdown -- answers "which of the 4 faces actually has wall
  // material" (see analyzeWallAxis's own header). A near-zero bucket on one
  // side of an axis that otherwise shows real wall area means that SPECIFIC
  // side is open (no wall), even though the piece's whole-axis total looked
  // "symmetric" against the opposite axis.
  console.log(`-- per-side wall area (open if near zero) --`);
  console.log(`  +X = ${bySide.xPos.toFixed(3)}   -X = ${bySide.xNeg.toFixed(3)}   +Z = ${bySide.zPos.toFixed(3)}   -Z = ${bySide.zNeg.toFixed(3)}`);
  const sideOpenThreshold = 0.5;
  const openSides = [];
  if (bySide.xPos < sideOpenThreshold) openSides.push("+X");
  if (bySide.xNeg < sideOpenThreshold) openSides.push("-X");
  if (bySide.zPos < sideOpenThreshold) openSides.push("+Z");
  if (bySide.zNeg < sideOpenThreshold) openSides.push("-Z");
  console.log(`  OPEN sides (wall area < ${sideOpenThreshold}): ${openSides.length > 0 ? openSides.join(", ") : "none -- fully enclosed on all 4 sides"}`);
  console.log(`-- per mesh-bearing node (root-space) --`);
  for (const n of r.perNode) {
    console.log(
      `  "${n.nodePath}" / ${n.meshName}#${n.primIdx}  ` +
      `min=[${n.min.map(fmt)} ]  max=[${n.max.map(fmt)} ]  ` +
      `size=[X=${n.size[0].toFixed(3)} Y=${n.size[1].toFixed(3)} Z=${n.size[2].toFixed(3)}]`,
    );
  }
  return r;
}

const files = process.argv.slice(2);
if (files.length === 0) {
  console.error("usage: node dashboard/scripts/glb_extents.mjs <file.glb> [<file2.glb> ...]");
  process.exit(1);
}
for (const f of files) {
  try {
    report(f);
  } catch (err) {
    console.error(`\n=== ${f} ===\nFAILED: ${err instanceof Error ? err.message : String(err)}`);
    process.exitCode = 1;
  }
}

// @ts-nocheck -- same reason as tests/hq-agents.test.ts's own header: this
// file uses an explicit ".ts" extension on its relative import (required for
// plain `node --test` to resolve it; the project tsconfig's
// `moduleResolution: "bundler"` has no `allowImportingTsExtensions`). Purely
// a syntax-erasure pragma -- has no effect on what actually runs.
//
// Regression tests for components/hq/kitPoolRegistry.ts -- the pure,
// react-free pieces of SetKit.tsx's cross-tree InstancedKitPool registry
// (extracted this pass; see that module's own header for the "why"). Guards
// against a future edit silently un-pooling a prop (registerPlacements/
// unregisterPlacements) or breaking an instance's world transform
// (composePlacementMatrix / ceilingLightWorldQuaternion) -- the gap the
// worker who shipped 5d5c4ec8 (pooling hub chairs/bay second-chairs/
// craters/craterLarge/wall cables/supportsHigh) left open: that commit
// added zero tests, only `npx tsc --noEmit`.
//
// Run: cd dashboard && node --test tests/kit-pool-registry.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import * as THREE from "three";
import {
  poolRegistry,
  makePoolKey,
  registerPlacements,
  unregisterPlacements,
  composePlacementMatrix,
  ceilingLightWorldQuaternion,
  subscribePool,
  getPoolVersion,
  type PoolPlacement,
} from "../components/hq/kitPoolRegistry.ts";

function assertMatrixAlmostEqual(a: THREE.Matrix4, b: THREE.Matrix4, epsilon = 1e-9, message?: string): void {
  const ae = a.elements;
  const be = b.elements;
  for (let i = 0; i < 16; i++) {
    assert.ok(
      Math.abs(ae[i] - be[i]) < epsilon,
      `${message ?? "matrix mismatch"} at element ${i}: ${ae[i]} vs ${be[i]}`,
    );
  }
}

// ─── (a) registry: N placements under one key, tints separate pools, unregister removes exactly one ───

test("registerPlacements: N placements under one key produce one pool with N instances", () => {
  const key = makePoolKey("/hq-assets/test/widget.glb", `native-${Math.random()}`);
  const placements: PoolPlacement[] = [
    { id: "w-1", position: [0, 0, 0], rotation: [0, 0, 0], scale: 1 },
    { id: "w-2", position: [1, 0, 0], rotation: [0, Math.PI / 2, 0], scale: 1 },
    { id: "w-3", position: [2, 0, 0], rotation: [0, Math.PI, 0], scale: 1 },
  ];
  registerPlacements(key, placements);
  const pool = poolRegistry.get(key);
  assert.ok(pool, "pool should exist after registration");
  assert.equal(pool!.size, 3, "pool should hold exactly the 3 registered instances");
  for (const p of placements) assert.ok(pool!.has(p.id), `pool should contain instance ${p.id}`);
});

test("registerPlacements: different tints (variant) produce SEPARATE pools for the same path", () => {
  const path = `/hq-assets/test/tinted-${Math.random()}.glb`;
  const nativeKey = makePoolKey(path, "native");
  const tintedKey = makePoolKey(path, "tinted");
  registerPlacements(nativeKey, [{ id: "n-1", position: [0, 0, 0], rotation: [0, 0, 0], scale: 1 }]);
  registerPlacements(tintedKey, [{ id: "t-1", position: [0, 0, 0], rotation: [0, 0, 0], scale: 1 }]);

  assert.notEqual(nativeKey, tintedKey, "native and tinted variants must key to different pools");
  const nativePool = poolRegistry.get(nativeKey);
  const tintedPool = poolRegistry.get(tintedKey);
  assert.equal(nativePool!.size, 1);
  assert.equal(tintedPool!.size, 1);
  assert.ok(!nativePool!.has("t-1"), "native pool must not see the tinted pool's instance");
  assert.ok(!tintedPool!.has("n-1"), "tinted pool must not see the native pool's instance");
});

test("unregisterPlacements: removes exactly one instance, leaves siblings under the same key intact", () => {
  const key = makePoolKey(`/hq-assets/test/remove-${Math.random()}.glb`, "native");
  const placements: PoolPlacement[] = [
    { id: "r-1", position: [0, 0, 0], rotation: [0, 0, 0], scale: 1 },
    { id: "r-2", position: [1, 0, 0], rotation: [0, 0, 0], scale: 1 },
    { id: "r-3", position: [2, 0, 0], rotation: [0, 0, 0], scale: 1 },
  ];
  registerPlacements(key, placements);
  assert.equal(poolRegistry.get(key)!.size, 3);

  unregisterPlacements(key, [placements[1]]); // remove only "r-2"

  const pool = poolRegistry.get(key)!;
  assert.equal(pool.size, 2, "exactly one instance should have been removed");
  assert.ok(pool.has("r-1"), "r-1 must survive");
  assert.ok(!pool.has("r-2"), "r-2 must be gone");
  assert.ok(pool.has("r-3"), "r-3 must survive");
});

test("register/unregister notify subscribers so useSyncExternalStore-style consumers re-render", () => {
  const key = makePoolKey(`/hq-assets/test/notify-${Math.random()}.glb`, "native");
  let notifications = 0;
  const unsubscribe = subscribePool(() => {
    notifications += 1;
  });
  const before = getPoolVersion();
  registerPlacements(key, [{ id: "n-1", position: [0, 0, 0], rotation: [0, 0, 0], scale: 1 }]);
  unregisterPlacements(key, [{ id: "n-1", position: [0, 0, 0], rotation: [0, 0, 0], scale: 1 }]);
  unsubscribe();

  assert.equal(notifications, 2, "one notification per register call and per unregister call");
  assert.equal(getPoolVersion(), before + 2, "version counter advances once per notify");
});

// ─── (b) instance matrix == THREE.Object3D-composed matrix within 1e-9 ────

test("composePlacementMatrix (Euler rotation): matches THREE.Object3D's own composed matrix", () => {
  const position: [number, number, number] = [3.5, -1.25, 7.0];
  const rotation: [number, number, number] = [0, Math.PI / 3, 0];
  const scale = 2.0;

  const got = composePlacementMatrix({ id: "cmp-1", position, rotation, scale });

  const obj = new THREE.Object3D();
  obj.position.set(...position);
  obj.rotation.set(rotation[0], rotation[1], rotation[2]);
  obj.scale.set(scale, scale, scale);
  obj.updateMatrix();

  assertMatrixAlmostEqual(got, obj.matrix, 1e-9, "Euler-rotation placement matrix");
});

test("composePlacementMatrix (explicit quaternion): matches THREE.Object3D's own composed matrix", () => {
  const position: [number, number, number] = [-2.0, 4.25, 0.5];
  const quaternion = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI / 5);
  const scale = 1.35;

  const got = composePlacementMatrix({ id: "cmp-2", position, quaternion, scale });

  const obj = new THREE.Object3D();
  obj.position.set(...position);
  obj.quaternion.copy(quaternion);
  obj.scale.set(scale, scale, scale);
  obj.updateMatrix();

  assertMatrixAlmostEqual(got, obj.matrix, 1e-9, "quaternion placement matrix");
});

test("registerPlacements stores the SAME composed matrix a caller would compute directly", () => {
  const key = makePoolKey(`/hq-assets/test/matrix-store-${Math.random()}.glb`, "native");
  const placement: PoolPlacement = { id: "m-1", position: [1, 2, 3], rotation: [0, Math.PI / 4, 0], scale: 1.5 };
  registerPlacements(key, [placement]);
  const stored = poolRegistry.get(key)!.get("m-1")!.matrix;
  const expected = composePlacementMatrix(placement);
  assertMatrixAlmostEqual(stored, expected, 1e-9, "stored pool matrix");
});

// ─── (c) ceilingLightWorldQuaternion == Ry(rotationY) * Rx(PI); naive Euler differs for y != 0 ───

test("ceilingLightWorldQuaternion equals the nested-group composition Ry(rotationY) * Rx(PI)", () => {
  for (const yaw of [0, Math.PI / 6, Math.PI / 2, Math.PI, (3 * Math.PI) / 2, -Math.PI / 3]) {
    const got = ceilingLightWorldQuaternion(yaw);

    const ry = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), yaw);
    const rx = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI);
    const expected = ry.clone().multiply(rx); // apply Rx first, then Ry -- nested-group order

    assert.ok(got.angleTo(expected) < 1e-9, `yaw=${yaw}: expected Ry*Rx composition, angle diff=${got.angleTo(expected)}`);
  }
});

test("ceilingLightWorldQuaternion differs from the naive Euler [PI, y, 0] whenever y != 0 (guards the original bug)", () => {
  // yaw=PI is deliberately excluded: two perpendicular-axis 180-degree
  // rotations anticommute (Rx(PI)Ry(PI) = -Ry(PI)Rx(PI)), and a quaternion
  // and its negation represent the IDENTICAL rotation (double cover) -- so
  // Ry*Rx and Rx*Ry coincide at exactly that one angle. Every other yaw
  // below genuinely discriminates the two orderings, which is the bug this
  // guards.
  for (const yaw of [Math.PI / 6, Math.PI / 2, (3 * Math.PI) / 2, -Math.PI / 3]) {
    const correct = ceilingLightWorldQuaternion(yaw);
    const naive = new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI, yaw, 0));
    assert.ok(
      correct.angleTo(naive) > 1e-6,
      `yaw=${yaw}: naive Euler[PI,y,0] should NOT match the correct nested-group quaternion (this is the bug the rewrite fixed)`,
    );
  }
});

test("ceilingLightWorldQuaternion at yaw=0 matches BOTH forms (they only diverge when y != 0)", () => {
  const correct = ceilingLightWorldQuaternion(0);
  const naive = new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI, 0, 0));
  assert.ok(correct.angleTo(naive) < 1e-9, "at yaw=0 the Ry component is identity, so both forms must agree");
});

test("ceilingLightWorldQuaternion returns a FRESH quaternion each call (never a shared mutable instance)", () => {
  const a = ceilingLightWorldQuaternion(Math.PI / 4);
  const b = ceilingLightWorldQuaternion(Math.PI / 4);
  assert.notEqual(a, b, "two calls must return distinct objects");
  a.set(0, 0, 0, 1);
  assert.ok(b.angleTo(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), Math.PI / 4).multiply(
    new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI, 0, 0)),
  )) < 1e-9, "mutating the first return value must not affect the second");
});

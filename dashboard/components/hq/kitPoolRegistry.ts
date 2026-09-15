// P3 perf pass follow-up (regression-test pass, 2026-09-15): the pure,
// react-free pieces of SetKit.tsx's cross-tree InstancedKitPool registry
// (module-scope Map + version-counter subscribe/notify, the PoolPlacement ->
// THREE.Matrix4 composition, and ceilingLightWorldQuaternion's real
// quaternion multiply) pulled OUT into their own module so they can be unit
// tested with plain `node --test` -- mirrors liveAgentWalk.ts's own "pure
// math, no React" convention (see that file's header). SetKit.tsx's
// `usePooledKitProps`/`InstancedKitPool` (React hooks, JSX, useGLTF) still
// own all React-specific behavior and now just call into this module --
// ZERO behavior change, proven by `npx tsc --noEmit` on both touched files
// plus a before/after diff review (the useEffect/useLayoutEffect bodies,
// the depsKey computation, and the JSX render are all untouched; only the
// module-scope Map/Set/counter and the two pure functions moved).
//
// Run: cd dashboard && node --test tests/kit-pool-registry.test.ts

import * as THREE from "three";

export interface PoolPlacement {
  /** Stable across re-renders for the SAME logical instance (the caller's
   * own useId() + a per-item suffix) -- the registry keys on this, never
   * array index. */
  id: string;
  position: [number, number, number];
  /** Euler XYZ (three.js default order). Mutually exclusive with
   * `quaternion`; exactly one of the two must be given. */
  rotation?: [number, number, number];
  /** Precomposed world quaternion -- for a placement whose rotation is a
   * composition of axes the default XYZ Euler order can't express directly
   * (see `ceilingLightWorldQuaternion` below). Mutually exclusive with
   * `rotation`. */
  quaternion?: THREE.Quaternion;
  scale: number;
}

export interface PoolInstance {
  matrix: THREE.Matrix4;
}

export type PoolKey = string; // `${glbPath}::${variant}`

export function makePoolKey(path: string, variant: string): PoolKey {
  return `${path}::${variant}`;
}

export const poolRegistry = new Map<PoolKey, Map<string, PoolInstance>>();
const poolListeners = new Set<() => void>();
let poolVersion = 0;

export function notifyPool(): void {
  poolVersion += 1;
  poolListeners.forEach((l) => l());
}
export function subscribePool(cb: () => void): () => void {
  poolListeners.add(cb);
  return () => poolListeners.delete(cb);
}
export function getPoolVersion(): number {
  return poolVersion;
}

const _poolPos = new THREE.Vector3();
const _poolQuat = new THREE.Quaternion();
const _poolEuler = new THREE.Euler();
const _poolScale = new THREE.Vector3();

/** Composes a placement's world matrix -- `compose(position,
 * quaternion-from-Euler(rotation) OR the given quaternion, uniform scale)`.
 * Reuses scratch THREE objects (same convention as the rest of this file's
 * math) -- the RETURNED Matrix4 is a fresh instance (`.compose` allocates
 * into a new Matrix4 here, never a shared one), so callers can safely stash
 * it. */
export function composePlacementMatrix(p: PoolPlacement): THREE.Matrix4 {
  const q = p.quaternion ?? _poolQuat.setFromEuler(_poolEuler.set(p.rotation![0], p.rotation![1], p.rotation![2]));
  return new THREE.Matrix4().compose(
    _poolPos.set(p.position[0], p.position[1], p.position[2]),
    q,
    _poolScale.set(p.scale, p.scale, p.scale),
  );
}

/** Registers a batch of placements under `key`, overwriting any existing
 * instance with the same `id`. Creates the pool Map on first use. Notifies
 * subscribers exactly once per call (never once per placement). */
export function registerPlacements(key: PoolKey, placements: PoolPlacement[]): void {
  let pool = poolRegistry.get(key);
  if (!pool) {
    pool = new Map();
    poolRegistry.set(key, pool);
  }
  for (const p of placements) {
    pool.set(p.id, { matrix: composePlacementMatrix(p) });
  }
  notifyPool();
}

/** Removes exactly the given placement ids from `key`'s pool (a no-op for
 * any id not currently present). Notifies subscribers exactly once per
 * call. */
export function unregisterPlacements(key: PoolKey, placements: PoolPlacement[]): void {
  const live = poolRegistry.get(key);
  if (live) for (const p of placements) live.delete(p.id);
  notifyPool();
}

// CeilingLight's own fixed local orientation (always `rotation={[Math.PI, 0,
// 0]}` before pooling) composed with a fresh per-call Y-axis quaternion --
// see PoolPlacement's own `quaternion` field header for why a single Euler
// triple can't express this (the WRONG multiplication order whenever
// rotationY != 0). `.multiply` runs on the fresh per-call quaternion, never
// mutating this shared local-orientation constant.
const _ceilingLightYAxis = new THREE.Vector3(0, 1, 0);
const CEILING_LIGHT_LOCAL_QUAT = new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI, 0, 0));

/** The real nested-group composition `Ry(rotationY) * Rx(Math.PI)` -- apply
 * the fixture's own local flip first, THEN the parent bay's Y rotation,
 * matching how two nested `<group rotation=[...]>` transforms actually
 * multiply. Returns a fresh Quaternion each call. */
export function ceilingLightWorldQuaternion(rotationY: number): THREE.Quaternion {
  return new THREE.Quaternion().setFromAxisAngle(_ceilingLightYAxis, rotationY).multiply(CEILING_LIGHT_LOCAL_QUAT);
}

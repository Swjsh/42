// SCENE-AUDIT pass (2026-09-15, worker: BUILD "would a human accept this
// room" audit -- J: "the object was placed on the screen, checkbox, move
// on... doors, walls, put the computer up against the wall, not inside the
// wall"). Root problem this file exists to fix: every existing hq_live_probe
// check asks "is X present / are the numbers in range", never "is this
// PHYSICALLY PLAUSIBLE" -- a desk half-buried in a wall, a live agent
// pacing straight through a wall, and a screen facing away from the camera
// all PASSED every check that existed before this pass (see
// markdown/doctrine/FRONTEND-OPS.md's "HQ scene acceptance" rubric,
// appended 2026-09-15, items 2-4, which this module implements).
//
// Two halves, split deliberately so the geometry math stays unit-testable
// with plain `node --test` (see dashboard/tests/hq-scene-audit.test.ts):
//   1. PURE GEOMETRY (no THREE, no window, no React) -- wall-slab
//      construction with door gaps cut out, AABB/segment intersection,
//      penetration depth, screen-facing cosine, and the check_* functions
//      that turn those primitives into a PASS/FAIL/NO-DATA verdict (same
//      verdict contract setup/scripts/hq_probe_lib.py's own check_* family
//      already uses). These never import "three" or layout.ts/SetKit.tsx at
//      the TOP LEVEL -- tests/hq-walk-routing.test.ts already discovered
//      that layout.ts transitively imports SetKit.tsx (a .tsx file), which
//      node's own ESM loader refuses outright (ERR_UNKNOWN_FILE_EXTENSION)
//      -- a static top-level import here would poison EVERY test in this
//      file, not just the ones that need live-scene geometry. Browser-only
//      code below reaches those modules via a LAZY `await import(...)`
//      instead, which node's loader never has to resolve unless the
//      function is actually called (it isn't, under node --test).
//   2. BROWSER TRAVERSAL (installSceneAuditHooks) -- walks the live
//      window.__hqScene (exposed by hq-motion-diag.ts#exposeSceneForDiag,
//      same `?diag=1` gate) for objects tagged `userData.hqKind` (see the
//      tagging convention added to SetKit.tsx/TwinMonitors.tsx/
//      DeskScreen.tsx/BaySign.tsx), expands InstancedMesh per-instance
//      matrices into world AABBs (a pool's OWN bounding box would cover
//      every instance ever placed -- useless for "is THIS ONE desk inside
//      a wall"), and calls the pure check_* functions above. Exposes
//      `window.__hqSceneAudit()` (one-shot static report: walls, screens,
//      desks) and `window.__hqSceneAuditWalkers()` (cheap per-tick walker
//      XZ snapshot, meant to be polled <=4x/s by a caller building a track
//      over time) for setup/scripts/hq_live_probe.py's `--plausibility`
//      family to read via Playwright's page.evaluate().
//
// Zero cost when disabled: installSceneAuditHooks() is a no-op unless
// `?diag=1` is on the URL (same isMotionDiagEnabled() gate hq-motion-diag.ts
// already uses) -- a normal viewer's tab never runs any of this.

/** Same `?diag=1` gate hq-motion-diag.ts#isMotionDiagEnabled already
 * establishes -- reimplemented as one line here (not imported) so this
 * file's own top level stays free of any import that resolves differently
 * under plain `node --test` (needs a ".ts" suffix) than under tsc/webpack
 * (TS5097 -- "allowImportingTsExtensions" is not enabled in this project),
 * matching this codebase's own "tiny local duplication over a cross-file
 * dependency" convention (see e.g. TwinMonitors.tsx/DeskScreen.tsx's own
 * duplicated etStamp() helper). No caching (unlike the original) --
 * this module calls it exactly once, from installSceneAuditHooks(). */
function diagFlagEnabled(): boolean {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("diag") === "1";
}

// ─── Pure types ─────────────────────────────────────────────────────────
export type Vec3 = [number, number, number];
export type Vec2 = [number, number];

export interface AABB {
  min: Vec3;
  max: Vec3;
}

export interface WallSlab {
  id: string;
  aabb: AABB;
}

export type WallSide = "+x" | "-x" | "+z" | "-z";

export interface DoorSpec {
  wall: WallSide;
  halfWidth: number;
}

export interface ObjectAabb {
  id: string;
  label: string;
  aabb: AABB;
}

export interface ScreenInfo {
  id: string;
  label: string;
  position: Vec3;
  /** World-space unit normal -- the direction the screen's face points. */
  normal: Vec3;
  /** false for informational-only screens (desk monitors, bay signs) --
   * these are reported but never gate the check's PASS/FAIL, per this
   * pass's own task instructions ("desk screens/bay signs are
   * informational, not FAIL, say why in the report"). */
  readable: boolean;
}

/** A screen face already projected into 2D viewport-pixel space for this
 * frame (SCREEN-KEEP-OUT pass, 2026-09-15) -- same coordinate convention as
 * the DOM label rects hq_live_probe.py's `.hq-beam` query already captures
 * (x,y = top-left corner, CSS pixels). Computed browser-side (needs the
 * live camera's real projection matrix + current viewport size, see
 * computeScreenViewportRect below), consumed by the PURE
 * checkLabelScreenOverlap so the actual FAIL/PASS math stays unit-testable
 * without three.js or a DOM. */
export interface ScreenViewportRect {
  id: string;
  label: string;
  readable: boolean;
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface ViewportLabelRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface CameraInfo {
  position: Vec3;
}

export interface WalkerTrack {
  id: string;
  points: Array<{ t: number; pos: Vec2 }>;
}

export interface CheckResult {
  verdict: "PASS" | "FAIL" | "NO-DATA";
  detail: Record<string, unknown>;
}

// ─── Pure geometry ──────────────────────────────────────────────────────

/** Builds the 4 wall slabs of an axis-aligned-after-rotation rectangular
 * room, cutting a door-width gap out of any wall named in `doors`. Every
 * room this scene places (the hub, all 8 bays) rotates only in multiples of
 * 90deg -- computeBaySlot/computeArmLayout's own rotationYFacing always
 * resolves to a cardinal angle for this cross-shaped layout (verified by
 * inspection of layout.ts: every bay position shares either its X or its Z
 * coordinate with its own T-junction center, which is exactly the condition
 * under which atan2 in rotationYFacing collapses to a multiple of PI/2) --
 * so treating the rotated room as a plain axis-aligned box in WORLD space is
 * exact, not an approximation, for every room this codebase actually
 * places. A non-cardinal rotationY still produces a (loose) axis-aligned
 * bound around the true rotated footprint rather than throwing -- safe
 * (never under-reports a wall), just not tight for that hypothetical case. */
export function buildRoomWallSlabs(opts: {
  id: string;
  center: Vec2;
  rotationY: number;
  halfExtentLocalX: number;
  halfExtentLocalZ: number;
  thickness: number;
  height: number;
  doors: DoorSpec[];
}): WallSlab[] {
  const { id, center, rotationY, halfExtentLocalX, halfExtentLocalZ, thickness, height, doors } = opts;
  const cos = Math.cos(rotationY);
  const sin = Math.sin(rotationY);
  // Matches three.js's own Y-axis rotation convention (and layout.ts's own
  // rotationYFacing/localToWorld usage elsewhere in this tree): world = R(y) * local.
  const toWorld = (lx: number, lz: number): Vec2 => [center[0] + lx * cos + lz * sin, center[1] + (-lx * sin + lz * cos)];

  const wallDefs: Array<{ key: WallSide; fixed: "x" | "z"; fixedVal: number; spanHalf: number }> = [
    { key: "+x", fixed: "x", fixedVal: halfExtentLocalX, spanHalf: halfExtentLocalZ },
    { key: "-x", fixed: "x", fixedVal: -halfExtentLocalX, spanHalf: halfExtentLocalZ },
    { key: "+z", fixed: "z", fixedVal: halfExtentLocalZ, spanHalf: halfExtentLocalX },
    { key: "-z", fixed: "z", fixedVal: -halfExtentLocalZ, spanHalf: halfExtentLocalX },
  ];

  const slabs: WallSlab[] = [];
  for (const w of wallDefs) {
    const door = doors.find((d) => d.wall === w.key);
    const segments: Vec2[] = door
      ? ([[-w.spanHalf, -door.halfWidth], [door.halfWidth, w.spanHalf]] as Vec2[]).filter(([lo, hi]) => hi - lo > 1e-6)
      : [[-w.spanHalf, w.spanHalf]];
    segments.forEach(([lo, hi], i) => {
      const sign = w.fixedVal >= 0 ? 1 : -1;
      const fixedLo = w.fixedVal - (sign * thickness) / 2;
      const fixedHi = w.fixedVal + (sign * thickness) / 2;
      const corners: Vec2[] =
        w.fixed === "x"
          ? [toWorld(fixedLo, lo), toWorld(fixedLo, hi), toWorld(fixedHi, lo), toWorld(fixedHi, hi)]
          : [toWorld(lo, fixedLo), toWorld(hi, fixedLo), toWorld(lo, fixedHi), toWorld(hi, fixedHi)];
      const xs = corners.map((c) => c[0]);
      const zs = corners.map((c) => c[1]);
      slabs.push({
        id: `${id}-wall-${w.key}-${i}`,
        aabb: { min: [Math.min(...xs), 0, Math.min(...zs)], max: [Math.max(...xs), height, Math.max(...zs)] },
      });
    });
  }
  return slabs;
}

export function aabbsOverlap(a: AABB, b: AABB, margin = 0): boolean {
  return (
    a.min[0] - margin <= b.max[0] + margin &&
    a.max[0] + margin >= b.min[0] - margin &&
    a.min[1] - margin <= b.max[1] + margin &&
    a.max[1] + margin >= b.min[1] - margin &&
    a.min[2] - margin <= b.max[2] + margin &&
    a.max[2] + margin >= b.min[2] - margin
  );
}

/** 0 if not overlapping; else the shallowest of the 3 axis overlaps -- the
 * minimum distance a wall-penetrating object would need to move along ANY
 * single axis to no longer overlap. That "shallowest push-out" number is
 * exactly "how far into the wall does it clip", the evidence J asked for
 * ("the object was placed on the screen, checkbox, move on" -- this is the
 * number that turns "clipping" from a vibe into a measurement). */
export function aabbPenetrationDepth(a: AABB, b: AABB): number {
  const ox = Math.min(a.max[0], b.max[0]) - Math.max(a.min[0], b.min[0]);
  const oy = Math.min(a.max[1], b.max[1]) - Math.max(a.min[1], b.min[1]);
  const oz = Math.min(a.max[2], b.max[2]) - Math.max(a.min[2], b.min[2]);
  if (ox <= 0 || oy <= 0 || oz <= 0) return 0;
  return Math.min(ox, oy, oz);
}

export function aabbDistance(a: AABB, b: AABB): number {
  const dx = Math.max(a.min[0] - b.max[0], b.min[0] - a.max[0], 0);
  const dy = Math.max(a.min[1] - b.max[1], b.min[1] - a.max[1], 0);
  const dz = Math.max(a.min[2] - b.max[2], b.min[2] - a.max[2], 0);
  return Math.hypot(dx, dy, dz);
}

/** Segment-vs-AABB intersection in the XZ (floor) plane, via the standard
 * slab method (parametrize the segment 0..1, clip against each axis's
 * [min,max] slab). Proper clipping, not "does either endpoint land inside
 * the box" -- a walker striding clean THROUGH a thin wall between two
 * sampled ticks has both endpoints outside the wall's thin AABB, which an
 * endpoint-containment test would miss entirely (exactly the class of bug
 * this check exists to catch -- see checkWalkerWallCross's own header). */
export function segmentIntersectsAabbXZ(p1: Vec2, p2: Vec2, aabb: AABB): boolean {
  let tmin = 0;
  let tmax = 1;
  const d: Vec2 = [p2[0] - p1[0], p2[1] - p1[1]];
  const lo: Vec2 = [aabb.min[0], aabb.min[2]];
  const hi: Vec2 = [aabb.max[0], aabb.max[2]];
  for (let axis = 0; axis < 2; axis++) {
    const p = axis === 0 ? p1[0] : p1[1];
    const dd = d[axis];
    if (Math.abs(dd) < 1e-9) {
      if (p < lo[axis] || p > hi[axis]) return false;
      continue;
    }
    let t0 = (lo[axis] - p) / dd;
    let t1 = (hi[axis] - p) / dd;
    if (t0 > t1) [t0, t1] = [t1, t0];
    tmin = Math.max(tmin, t0);
    tmax = Math.min(tmax, t1);
    if (tmin > tmax) return false;
  }
  return true;
}

function vecSub(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}
function vecNormalize(v: Vec3): Vec3 {
  const l = Math.hypot(v[0], v[1], v[2]) || 1;
  return [v[0] / l, v[1] / l, v[2] / l];
}
function vecDot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

/** cos(angle) between a screen's face normal and the direction from the
 * screen to the viewer. 1 = dead-on face-first, 0 = edge-on (unreadable),
 * negative = facing AWAY from the viewer (the "pitched, back to camera"
 * failure mode J flagged). */
export function screenFacingCosine(normalWorld: Vec3, screenPos: Vec3, viewerPos: Vec3): number {
  return vecDot(vecNormalize(normalWorld), vecNormalize(vecSub(viewerPos, screenPos)));
}

function wrapAngleRad(a: number): number {
  let x = a % (2 * Math.PI);
  if (x > Math.PI) x -= 2 * Math.PI;
  if (x < -Math.PI) x += 2 * Math.PI;
  return x;
}

// ─── check_* -- pure verdict functions, same PASS/FAIL/NO-DATA contract as
// setup/scripts/hq_probe_lib.py's own check_* family. ──────────────────────

export function checkWallPenetration(objects: ObjectAabb[], slabs: WallSlab[], toleranceU = 0.05): CheckResult {
  if (objects.length === 0 || slabs.length === 0) {
    return { verdict: "NO-DATA", detail: { reason: "no furniture/screen objects or no wall slabs supplied", objectCount: objects.length, wallCount: slabs.length } };
  }
  const violations: Array<{ objectId: string; label: string; wallId: string; depthU: number }> = [];
  for (const obj of objects) {
    for (const slab of slabs) {
      const depth = aabbPenetrationDepth(obj.aabb, slab.aabb);
      if (depth > toleranceU) violations.push({ objectId: obj.id, label: obj.label, wallId: slab.id, depthU: Math.round(depth * 1000) / 1000 });
    }
  }
  return {
    verdict: violations.length > 0 ? "FAIL" : "PASS",
    detail: { checked: objects.length, wallCount: slabs.length, toleranceU, violations: violations.slice(0, 20) },
  };
}

export function checkWalkerWallCross(tracks: WalkerTrack[], slabs: WallSlab[]): CheckResult {
  if (slabs.length === 0) return { verdict: "NO-DATA", detail: { reason: "no wall slabs supplied" } };
  if (tracks.length === 0) return { verdict: "NO-DATA", detail: { reason: "no walker tracks this run" } };
  const violations: Array<{ walkerId: string; from: Vec2; to: Vec2; wallId: string }> = [];
  let segmentsChecked = 0;
  for (const track of tracks) {
    for (let i = 1; i < track.points.length; i++) {
      const a = track.points[i - 1].pos;
      const b = track.points[i].pos;
      segmentsChecked += 1;
      for (const slab of slabs) {
        if (segmentIntersectsAabbXZ(a, b, slab.aabb)) {
          violations.push({ walkerId: track.id, from: a, to: b, wallId: slab.id });
          break;
        }
      }
    }
  }
  if (segmentsChecked === 0) return { verdict: "NO-DATA", detail: { reason: "no walker had 2+ position samples this run" } };
  return {
    verdict: violations.length > 0 ? "FAIL" : "PASS",
    detail: { segmentsChecked, violationCount: violations.length, violations: violations.slice(0, 20) },
  };
}

export function checkScreenFacing(screens: ScreenInfo[], liveCamera: CameraInfo, topDownCamera: CameraInfo, minCos = 0.5): CheckResult {
  if (screens.length === 0) return { verdict: "NO-DATA", detail: { reason: "no screens supplied" } };
  const evaluated = screens.map((s) => ({
    id: s.id,
    label: s.label,
    readable: s.readable,
    liveCos: Math.round(screenFacingCosine(s.normal, s.position, liveCamera.position) * 1000) / 1000,
    topDownCos: Math.round(screenFacingCosine(s.normal, s.position, topDownCamera.position) * 1000) / 1000,
  }));
  const readableFails = evaluated.filter((e) => e.readable && e.liveCos < minCos);
  return {
    verdict: readableFails.length > 0 ? "FAIL" : "PASS",
    detail: {
      minCos,
      screens: evaluated,
      note: "desk-screen/bay-sign entries carry readable:false -- informational only, never gate this verdict (task scope: only TwinMonitors/hub panels must be readable from the default camera)",
    },
  };
}

/** Back-wall clearance band, u: a desk genuinely backed against a wall
 * (DESKS-AGAINST-WALLS pass) should sit CLOSE to it (0.2-0.6u, "against it,
 * not floating away") -- the OLD blanket "clearance >= 1.0u from ANY wall"
 * rule (still the default below, `backWallBandU` undefined) would FAIL a
 * correctly-placed against-the-wall desk on its own near wall, which is
 * exactly backwards from what "backed against the wall" means. */
export interface WallBand {
  min: number;
  max: number;
}

export function checkDeskClearance(
  desks: ObjectAabb[],
  slabs: WallSlab[],
  allFurniture: ObjectAabb[],
  minClearanceU = 1.0,
  backWallBandU?: WallBand,
): CheckResult {
  if (desks.length === 0) return { verdict: "NO-DATA", detail: { reason: "no desks supplied" } };
  const violations: Array<{ id: string; issue: string; valueU: number }> = [];
  for (const desk of desks) {
    let minWallDist = Infinity;
    for (const slab of slabs) minWallDist = Math.min(minWallDist, aabbDistance(desk.aabb, slab.aabb));
    if (Number.isFinite(minWallDist)) {
      if (backWallBandU) {
        // The nearest wall IS this desk's own back wall by construction (it
        // was placed to sit close to exactly one) -- band-check that one,
        // then require every OTHER wall (chair-side, side walls) to still
        // clear the normal minClearanceU, same "real obstacle" bar as
        // before.
        if (minWallDist < backWallBandU.min) {
          violations.push({ id: desk.id, issue: "back edge closer than the wall band's own minimum (reads as INSIDE the wall)", valueU: Math.round(minWallDist * 1000) / 1000 });
        } else if (minWallDist > backWallBandU.max) {
          violations.push({ id: desk.id, issue: "back edge further than the wall band's own maximum (reads as floating, not backed against the wall)", valueU: Math.round(minWallDist * 1000) / 1000 });
        }
        for (const slab of slabs) {
          const dist = aabbDistance(desk.aabb, slab.aabb);
          if (dist > minWallDist + 1e-6 && dist < minClearanceU) {
            violations.push({ id: desk.id, issue: `closer than min clearance ${minClearanceU}u to wall ${slab.id} (not its own back wall)`, valueU: Math.round(dist * 1000) / 1000 });
          }
        }
      } else if (minWallDist < minClearanceU) {
        violations.push({ id: desk.id, issue: "closer than min wall clearance", valueU: Math.round(minWallDist * 1000) / 1000 });
      }
    }
    for (const other of allFurniture) {
      if (other.id === desk.id) continue;
      // A chair pulled up to its own desk is SUPPOSED to have its AABB
      // touch/overlap the desk's -- that's a real, physically plausible
      // furniture arrangement, not clipping. Excluding "chair" from this
      // overlap sub-check specifically was a real false-positive found by
      // this pass's own first live probe run (16/16 desks flagged for
      // "overlapping" their own chair) -- only a desk overlapping ANOTHER
      // desk or a non-chair prop still fails. Real desks stay axis-aligned
      // (DESKS-AGAINST-WALLS: every yaw is a multiple of 90deg by
      // construction) so an AABB overlap test is exact here, never the
      // 45deg-inflated false positive the old diagonal-corner layout hit.
      if (other.label === "chair") continue;
      if (aabbsOverlap(desk.aabb, other.aabb)) violations.push({ id: desk.id, issue: `overlaps ${other.id}`, valueU: 0 });
    }
  }
  return { verdict: violations.length > 0 ? "FAIL" : "PASS", detail: { checked: desks.length, minClearanceU, backWallBandU, violations: violations.slice(0, 20) } };
}

/** INDEPENDENT expected yaw for a desk sitting near one of the HUB's own
 * real walls (DESKS-AGAINST-WALLS pass, J: "put the object... against the
 * wall"). Deliberately does NOT call layout.ts#computePersonaWallSlots or
 * read its rotationY -- that would make checkDeskOrientation tautological
 * (a desk always "passes" by construction if the expected value is just
 * whatever the layout code itself already computed for it, the exact gap
 * this pass's own task named: "not matches the layout's own yaw"). Instead
 * this re-derives the nearest wall from RAW POSITION alone, via the SAME
 * axis-aligned-square Chebyshev model buildHubSlabs already uses, and
 * returns the yaw that makes the desk's own local-Z axis perpendicular to
 * that wall (long axis parallel to it) -- a desk sitting on the room's
 * DIAGONAL (the old DESK-RING/DESK-ROWS corner model) computes a nearest
 * wall whose own normal is 45deg off the desk's real placement angle, and
 * correctly FAILs this check even though it "matched" a layout-derived
 * target under the old tautological pairing. */
export function nearestHubWallYaw(position: Vec3): number {
  const absX = Math.abs(position[0]);
  const absZ = Math.abs(position[2]);
  let wallArmAngle: number;
  if (absX >= absZ) {
    wallArmAngle = position[0] >= 0 ? 0 : Math.PI;
  } else {
    wallArmAngle = position[2] >= 0 ? Math.PI / 2 : (3 * Math.PI) / 2;
  }
  // Same identity layout.ts's own header documents: rotationYFacing(a point
  // on a ray through the origin, HUB) reduces exactly to PI/2 - angle.
  return Math.PI / 2 - wallArmAngle;
}

/** How close (Chebyshev, matching the square-room model) a position must be
 * to the HUB's own outer wall before nearestHubWallYaw's "which wall is
 * this desk backed against" classification is trusted -- desks genuinely
 * near the room's center (Gamma's own hub desk, radius 3.4) have no real
 * "nearest wall" in the backed-against-it sense and must fall back to a
 * looser heuristic instead (see computeSceneAuditReport's own caller). */
export const HUB_WALL_ADJACENCY_BAND_U = 3.0;

/** Verifies every desk's yaw is within `tolDeg` of ITS OWN expected facing
 * (caller supplies the pairing -- see computeExpectedDeskYaw below for how
 * the live-scene traversal derives it from layout.ts). */
export function checkDeskOrientation(desks: Array<{ id: string; actualYaw: number; targetYaw: number }>, tolDeg = 10): CheckResult {
  if (desks.length === 0) return { verdict: "NO-DATA", detail: { reason: "no desks supplied" } };
  const violations = desks
    .map((d) => ({ id: d.id, diffDeg: Math.round((wrapAngleRad(d.actualYaw - d.targetYaw) * 180) / Math.PI * 10) / 10 }))
    .filter((d) => Math.abs(d.diffDeg) > tolDeg);
  return { verdict: violations.length > 0 ? "FAIL" : "PASS", detail: { tolDeg, checked: desks.length, violations } };
}

// ─── SEATED-POSE-AUDIT pass (2026-09-16) ────────────────────────────────
// Task: "people actually working" measured, not eyeballed -- every persona
// whose /api/hq status is GREEN/IDLE/YELLOW (RED paces, walking is exempt
// for that tick) should be sitting AT its own desk, facing its own screen,
// not floating/clipping through the chair. Split the same way every other
// check in this file is: a PURE per-sample verdict function below (no
// THREE/window, unit-testable), fed by a BROWSER-side expected-seat lookup
// (computeSeatedPoseExpectedReport, near installSceneAuditHooks) and by
// setup/scripts/hq_live_probe.py's own sampling of window.__hqMotion.agents
// (Agent.tsx's EXISTING recordAgentSample call, LiveAgents/Agent/KitAgent
// are off-limits to this pass so this reuses that already-published x/y/z
// rather than adding new instrumentation there).
//
// KNOWN GAP, stated rather than faked (OP-33/failure-honesty): Agent.tsx's
// recordAgentSample only ever published `{id,x,y,z,clipSpeed}` -- no body
// YAW and no exact animation-clip name, and this pass's own scope excludes
// editing Agent.tsx/KitAgent.tsx to add either. `checkSeatedPose` below
// therefore verdicts POSITION (XZ-plane distance to the expected seat) and
// HEIGHT (Y vs the expected seat-pan height) for real, and reports yaw/clip
// as their own NO-DATA sub-verdicts with the reason stated -- never a
// fabricated PASS on data this rig doesn't expose. See hq_probe_lib.py's
// own check_seated_pose (setup/scripts side) for how the two are combined
// into one per-persona steady-state verdict.
export interface SeatedPoseExpected {
  /** World-space seat point (SetKit.tsx#BAY_SEAT_LOCAL through the SAME
   * layout.ts#computePersonaWallSlots slot + palette.ts#localToWorld the
   * live scene itself uses -- see computeSeatedPoseExpectedReport below). */
  seat: Vec3;
  /** Desk/screen-facing yaw, radians -- Agent.tsx's own `deskYaw` prop,
   * which Scene.tsx passes as `slot.rotationY` unchanged (BLOCKY-FIXES,
   * commit 1333a8f6). */
  yaw: number;
  wallSlotIndex: number;
}

export interface SeatedPoseSample {
  name: string;
  /** /api/hq `company.personas[].status` -- "RED" is exempt (pacing, not
   * seated, by design). */
  status: string;
  /** True on any tick the walker hook (or another live signal) reports
   * this persona mid-walk -- exempt for that tick, not a FAIL. */
  walking?: boolean;
  /** One tick's worth of window.__hqMotion.agents position for this
   * persona id (Agent.tsx's laneSeed === persona.name for a resident
   * desk agent, same convention check_page_api_parity already relies on
   * elsewhere in this probe). Absent entirely = no motion-diag sample
   * this tick (?diag=1 off, or the persona hasn't rendered a frame yet). */
  pos?: Vec3;
}

export const SEATED_POS_TOL_U = 0.25;
export const SEATED_Y_TOL_U = 0.1;
/** Chair seat-pan height, world units -- see setup/scripts/hq_probe_lib.py's
 * own SEATED_SEAT_HEIGHT_U for the full glb_extents.mjs derivation (this
 * constant is duplicated, not imported, across the TS/Python boundary same
 * as every other probe threshold pair in this codebase). chair.glb's root
 * AABB height is 0.550 (a single fused mesh -- no separate seat-pan
 * sub-node exists to measure directly), scaled by FURNITURE_SCALE=2.0 and
 * this task's own 0.40-0.45 seat-pan-fraction estimate (midpoint 0.42):
 * 0.550 * 2.0 * 0.42 = 0.462. */
export const SEATED_SEAT_HEIGHT_U = 0.462;

/** Pure per-sample seated-pose verdict for ONE persona -- steady-state
 * aggregation (>=4/5 like every other check_* in this file's Python
 * sibling) is hq_probe_lib.py's own job, not this function's; this judges
 * a single already-resolved sample against its expected seat. */
export function checkSeatedPose(
  samples: SeatedPoseSample[],
  expectedByName: Record<string, SeatedPoseExpected>,
  posTolU = SEATED_POS_TOL_U,
  yTolU = SEATED_Y_TOL_U,
  seatHeightU = SEATED_SEAT_HEIGHT_U,
): CheckResult {
  if (samples.length === 0) return { verdict: "NO-DATA", detail: { reason: "no samples supplied" } };
  const evidence: Record<string, unknown> = {};
  let anyFail = false;
  let anyJudged = false;
  for (const s of samples) {
    if (s.status === "RED") {
      evidence[s.name] = { verdict: "EXEMPT", reason: "RED paces, seated pose does not apply" };
      continue;
    }
    if (s.walking) {
      evidence[s.name] = { verdict: "EXEMPT", reason: "walking this tick" };
      continue;
    }
    const expected = expectedByName[s.name];
    if (!expected) {
      evidence[s.name] = { verdict: "NO-DATA", reason: "no expected seat (not in the wall-slot roster, e.g. Gamma)" };
      continue;
    }
    if (!s.pos) {
      evidence[s.name] = { verdict: "NO-DATA", reason: "no window.__hqMotion position sample this tick" };
      continue;
    }
    const posErrorU = Math.hypot(s.pos[0] - expected.seat[0], s.pos[2] - expected.seat[2]);
    const yErrorU = Math.abs(s.pos[1] - seatHeightU);
    const posOk = posErrorU <= posTolU;
    const yOk = yErrorU <= yTolU;
    anyJudged = true;
    const verdict = posOk && yOk ? "PASS" : "FAIL";
    if (verdict === "FAIL") anyFail = true;
    evidence[s.name] = {
      verdict,
      pos_error_u: Math.round(posErrorU * 1000) / 1000,
      y_error_u: Math.round(yErrorU * 1000) / 1000,
      pos_ok: posOk,
      y_ok: yOk,
      // Stated gap, not a fabricated verdict -- see this section's own
      // header comment for why yaw/clip aren't measured here.
      yaw_error_deg: "NO-DATA (Agent.tsx does not publish body yaw)",
      clip: "NO-DATA (Agent.tsx does not publish the exact animation-clip name)",
      expected_seat: expected.seat,
      actual_pos: s.pos,
    };
  }
  if (!anyJudged) return { verdict: "NO-DATA", detail: { reason: "every persona this tick was exempt or had no data", evidence } };
  return { verdict: anyFail ? "FAIL" : "PASS", detail: { posTolU, yTolU, seatHeightU, evidence } };
}

/** Fraction of `screen`'s own area covered by its intersection with `label`
 * -- "how much of the SCREEN does this label sit on", not the reverse (a
 * huge label barely clipping a small screen's corner should read as a
 * small violation of the screen's readability, not a small violation of
 * the label). Both rects share the SAME 2D viewport-pixel space (top-left
 * x,y convention) -- no unit conversion needed, unlike the 3D AABB checks
 * above. Returns 0 for zero/negative-area screens (never divides by 0). */
export function rectOverlapFractionOfScreen(label: ViewportLabelRect, screen: ScreenViewportRect): number {
  const screenArea = screen.width * screen.height;
  if (screenArea <= 0) return 0;
  const ix0 = Math.max(label.x, screen.x);
  const iy0 = Math.max(label.y, screen.y);
  const ix1 = Math.min(label.x + label.width, screen.x + screen.width);
  const iy1 = Math.min(label.y + label.height, screen.y + screen.height);
  const iw = ix1 - ix0;
  const ih = iy1 - iy0;
  if (iw <= 0 || ih <= 0) return 0;
  return (iw * ih) / screenArea;
}

/** SCREEN-KEEP-OUT pass (2026-09-15) -- the sub-check hq_live_probe.py's own
 * check_label_legibility docstring explicitly named as a stated, not
 * silently skipped, follow-up ("does not check label-vs-screen-face
 * overlap"). A world label (a persona bubble, a HoloChart plaque, the
 * BRAIN plaque) drifting across a screen's own face reads as visual
 * clutter ON TOP of readable content -- the monitors worker's own real-
 * capture observation named exactly this (Gamma's head label covering the
 * IDEAS BOARD title). FAILs any label/READABLE-screen pair whose overlap
 * exceeds `maxFrac` of the screen's own area -- informational screens (desk
 * monitors, bay signs, `readable: false`) are reported but never gate the
 * verdict, same convention checkScreenFacing already established. NO-DATA
 * with no screens or no labels supplied (never a false PASS on zero
 * evidence, matching every other check_* in this module). */
export function checkLabelScreenOverlap(
  labels: readonly ViewportLabelRect[],
  screens: readonly ScreenViewportRect[],
  maxFrac = 0.1,
): CheckResult {
  if (screens.length === 0) return { verdict: "NO-DATA", detail: { reason: "no screens supplied" } };
  if (labels.length === 0) return { verdict: "NO-DATA", detail: { reason: "no labels supplied" } };

  const violations: Array<{ screenId: string; screenLabel: string; overlapFrac: number }> = [];
  for (const screen of screens) {
    let worst = 0;
    for (const label of labels) {
      worst = Math.max(worst, rectOverlapFractionOfScreen(label, screen));
    }
    if (screen.readable && worst > maxFrac) {
      violations.push({ screenId: screen.id, screenLabel: screen.label, overlapFrac: Math.round(worst * 1000) / 1000 });
    }
  }
  return {
    verdict: violations.length > 0 ? "FAIL" : "PASS",
    detail: {
      maxFrac,
      screenCount: screens.length,
      labelCount: labels.length,
      violations,
      note: "informational screens (readable:false -- desk monitors, bay signs) are reported via raw screen data but never gate this verdict, same convention checkScreenFacing already uses",
    },
  };
}

// ─── Live-scene constants ───────────────────────────────────────────────
// Plain literals (never imported from SetKit.tsx -- see this file's own
// header for why a static import would break `node --test`). Each is
// derived from that file's OWN already-documented raw-kit numbers, restated
// here rather than re-measured:
//   HUB_WALL_RADIUS = 10 * ARCHITECTURE_SCALE_HUB(0.75) = 7.5
//   room-large raw height 4.25 * 0.75 = 3.1875
//   BAY_HALF_DEPTH = (12 * ARCHITECTURE_SCALE_BAY(0.45)) / 2 = 2.7
//   room-small raw height 4.25 * 0.45 = 1.9125
//   gate-door.glb raw width 4.2 (layout.ts's own GATE_RAW_WIDTH)
const HUB_HALF_EXTENT = 7.5;
const HUB_WALL_HEIGHT = 4.25 * 0.75;
const HUB_DOOR_HALF_WIDTH = (4.2 * 0.75) / 2;
const BAY_HALF_EXTENT = 2.7;
const BAY_WALL_HEIGHT = 4.25 * 0.45;
const BAY_DOOR_HALF_WIDTH = (4.2 * 0.45) / 2;
/** ASSUMPTION (stated, not measured from a GLB this pass -- none of the
 * modular-kit wall pieces ship a "thickness" dimension distinct from their
 * footprint in the header table this file's siblings already documented):
 * a generic thin-wall thickness generous enough to catch real clipping
 * (J's fixed desk-in-wall bug penetrated by ~1u, see the regression test)
 * without false-flagging furniture placed close-but-clear of a wall. */
const WALL_THICKNESS = 0.3;

export { HUB_HALF_EXTENT, HUB_WALL_HEIGHT, HUB_DOOR_HALF_WIDTH, BAY_HALF_EXTENT, BAY_WALL_HEIGHT, BAY_DOOR_HALF_WIDTH, WALL_THICKNESS };

export function buildHubSlabs(): WallSlab[] {
  return buildRoomWallSlabs({
    id: "hub",
    center: [0, 0],
    rotationY: 0,
    halfExtentLocalX: HUB_HALF_EXTENT,
    halfExtentLocalZ: HUB_HALF_EXTENT,
    thickness: WALL_THICKNESS,
    height: HUB_WALL_HEIGHT,
    doors: [
      { wall: "+x", halfWidth: HUB_DOOR_HALF_WIDTH },
      { wall: "-x", halfWidth: HUB_DOOR_HALF_WIDTH },
      { wall: "+z", halfWidth: HUB_DOOR_HALF_WIDTH },
      { wall: "-z", halfWidth: HUB_DOOR_HALF_WIDTH },
    ],
  });
}

/** One bay's own 4 walls, door on local -Z (matches
 * SetKit.tsx#DepartmentBayShell's own "gate-door sits at local -Z, the
 * hub-facing edge" convention). `rotationY` right-angle-only per this
 * file's buildRoomWallSlabs header. */
export function buildBaySlabs(id: string, center: Vec2, rotationY: number): WallSlab[] {
  return buildRoomWallSlabs({
    id,
    center,
    rotationY,
    halfExtentLocalX: BAY_HALF_EXTENT,
    halfExtentLocalZ: BAY_HALF_EXTENT,
    thickness: WALL_THICKNESS,
    height: BAY_WALL_HEIGHT,
    doors: [{ wall: "-z", halfWidth: BAY_DOOR_HALF_WIDTH }],
  });
}

// ─── Browser traversal (never runs under node --test -- reached only via
// window.__hqSceneAudit()/__hqSceneAuditWalkers(), themselves only wired up
// by installSceneAuditHooks() when `?diag=1` is set). ──────────────────────

interface TaggedObject3D {
  userData?: { hqKind?: string; hqLabel?: string; hqFaceLocalNormal?: Vec3; hqInformational?: boolean };
  isInstancedMesh?: boolean;
  count?: number;
  matrixWorld?: unknown;
  geometry?: { boundingBox?: unknown; computeBoundingBox?: () => void };
  getMatrixAt?: (i: number, out: unknown) => void;
  getWorldPosition?: (out: unknown) => unknown;
  updateWorldMatrix?: (updateParents: boolean, updateChildren: boolean) => void;
  traverse: (cb: (o: TaggedObject3D) => void) => void;
}

async function loadThree() {
  // Dynamic on purpose -- see this file's own header for why a static
  // top-level `import * as THREE from "three"` here would be fine for
  // node's loader (three ships plain ESM/CJS, no .tsx involved) but is kept
  // dynamic anyway for symmetry with the layout.ts import below, and so
  // this module has ZERO side effects at import time in any environment.
  return import("three");
}

async function loadLayout() {
  // Lazy: layout.ts imports SetKit.tsx (a .tsx file) at its own top level,
  // which breaks plain `node --test` if resolved eagerly -- see this file's
  // header. Only ever called from inside installSceneAuditHooks()'s
  // returned closures, which node --test never invokes.
  return import("../components/hq/layout");
}

async function loadPalette() {
  // palette.ts's own top-level imports are plain ("three" + no .tsx), so a
  // static top-level import here would actually be safe under `node --test`
  // -- kept dynamic anyway for the SAME symmetry/zero-side-effect-at-import
  // reason loadThree() above already states, not because it's required.
  return import("../components/hq/palette");
}

function extractYawFromMatrix(THREE: typeof import("three"), matrix: InstanceType<typeof import("three").Matrix4>): number {
  const pos = new THREE.Vector3();
  const quat = new THREE.Quaternion();
  const scale = new THREE.Vector3();
  matrix.decompose(pos, quat, scale);
  const euler = new THREE.Euler().setFromQuaternion(quat, "YXZ");
  return euler.y;
}

/** SCREEN-KEEP-OUT pass: projects a world-space AABB's 8 corners through
 * the live camera (real THREE.Camera instance off window.__hqCamera --
 * project() needs the actual object, not just its position) and returns
 * the bounding rect of those 8 projected points in viewport CSS pixels
 * (top-left convention, matching hq_live_probe.py's own `.hq-beam` DOM
 * rect capture). Using the world AABB's corners (rather than the screen
 * mesh's own tighter local-space rect) is deliberately the SAME
 * approximation checkWallPenetration etc. already make for a billboarded
 * plane -- a slightly larger, axis-aligned bound around the true rotated
 * rectangle, never a tight fit but never an UNDER-report either, which is
 * the safe direction for a "don't let a label sit here" keep-out zone.
 * Returns null if any corner fails to project (camera not ready) or the
 * viewport has zero area. */
function projectAabbToViewportRect(
  THREE: typeof import("three"),
  aabb: AABB,
  camera: unknown,
  viewportW: number,
  viewportH: number,
): { x: number; y: number; width: number; height: number } | null {
  if (viewportW <= 0 || viewportH <= 0) return null;
  const cam = camera as InstanceType<typeof THREE.Camera> | undefined;
  if (!cam || !(cam as unknown as { isCamera?: boolean }).isCamera) return null;
  const [minX, minY, minZ] = aabb.min;
  const [maxX, maxY, maxZ] = aabb.max;
  const corners: Vec3[] = [
    [minX, minY, minZ], [maxX, minY, minZ], [minX, maxY, minZ], [minX, minY, maxZ],
    [maxX, maxY, minZ], [maxX, minY, maxZ], [minX, maxY, maxZ], [maxX, maxY, maxZ],
  ];
  let pxMin = Infinity;
  let pxMax = -Infinity;
  let pyMin = Infinity;
  let pyMax = -Infinity;
  const v = new THREE.Vector3();
  for (const [x, y, z] of corners) {
    v.set(x, y, z).project(cam);
    if (!Number.isFinite(v.x) || !Number.isFinite(v.y)) return null;
    const px = ((v.x + 1) / 2) * viewportW;
    const py = ((1 - v.y) / 2) * viewportH;
    pxMin = Math.min(pxMin, px);
    pxMax = Math.max(pxMax, px);
    pyMin = Math.min(pyMin, py);
    pyMax = Math.max(pyMax, py);
  }
  return { x: pxMin, y: pyMin, width: pxMax - pxMin, height: pyMax - pyMin };
}

/** SCREEN-KEEP-OUT PER-TICK FIX (2026-09-16, probe 20260916T012329Z
 * label_vs_screen_overlap FAIL under a MOVING camera, twin-monitor-101/102
 * at overlapFrac 0.19/0.30). ROOT CAUSE (confirmed by reading
 * hq_live_probe.py's own compute_plausibility_verdicts, not a runtime
 * declutter bug): screenViewportRects is computed exactly ONCE, from a
 * single `window.__hqSceneAudit()` call BEFORE the label-sampling loop
 * begins -- that function's own docstring says "the static scene geometry
 * doesn't change tick-to-tick, so one snapshot is sufficient", which is
 * true of the screens' WORLD position but false of their PROJECTED
 * VIEWPORT RECT: the full probe run does not pass `?tour=0`, so the camera
 * auto-orbits/drifts for the whole run, and a screen's on-screen position
 * moves every tick right along with it. Labels are sampled at 4x/s across
 * the whole window, so by the time a later tick's label rect is compared
 * against the FIRST tick's screen rect, the two are checking two different
 * camera poses against each other -- exactly the kind of stale-obstacle
 * mismatch the runtime keep-out (LabelDeclutterManager.tsx's own
 * `readScreenObstacleRects`, which re-reads screens fresh every tick)
 * never has, because it always acts on the CURRENT frame.
 *
 * FIX: this lightweight sibling of computeSceneAuditReport does ONLY the
 * screen-projection half of that function (screens are a small, fixed-size
 * set -- 2 readable TwinMonitors + a handful of informational desk/bay
 * screens -- so re-running this every plausibility tick is cheap, unlike
 * re-running the full wall/desk/furniture traversal), so
 * hq_live_probe.py's own per-tick label-sampling loop can pair each tick's
 * label rects with that SAME tick's screen rects instead of one frozen
 * snapshot. Exposed as `window.__hqSceneAuditScreens` (installed alongside
 * the existing hooks, same `?diag=1` gate) -- a build that predates this
 * fix simply lacks the hook, and the Python side falls back to the old
 * one-shot `screenViewportRects` from `__hqSceneAudit()` in that case
 * (never a hard failure, see hq_live_probe.py's own comment at the call
 * site). Zero change to `computeSceneAuditReport`'s own screen traversal
 * logic -- this is the same projection math, just callable on its own. */
function computeScreenViewportRectsSync(
  THREE: typeof import("three"),
  scene: TaggedObject3D,
  camera: unknown,
  viewportW: number,
  viewportH: number,
): ScreenViewportRect[] {
  const screenViewportRects: ScreenViewportRect[] = [];
  const box3 = new THREE.Box3();
  let counter = 0;
  scene.traverse((obj) => {
    if (obj.userData?.hqKind !== "screen") return;
    const label = obj.userData?.hqLabel ?? "screen";
    obj.updateWorldMatrix?.(true, false);
    box3.setFromObject(obj as unknown as InstanceType<typeof THREE.Object3D>);
    if (box3.isEmpty()) return;
    const aabb: AABB = { min: [box3.min.x, box3.min.y, box3.min.z], max: [box3.max.x, box3.max.y, box3.max.z] };
    const id = `${label}-${counter++}`;
    const readable = !obj.userData?.hqInformational;
    const rect = projectAabbToViewportRect(THREE, aabb, camera, viewportW, viewportH);
    if (rect) screenViewportRects.push({ id, label, readable, ...rect });
  });
  return screenViewportRects;
}

async function computeScreenViewportRectsReport(): Promise<Record<string, unknown>> {
  const scene = (window as unknown as { __hqScene?: TaggedObject3D }).__hqScene;
  const camera = (window as unknown as { __hqCamera?: unknown }).__hqCamera;
  const gl = (window as unknown as { __hqGl?: { domElement?: { clientWidth?: number; clientHeight?: number } } }).__hqGl;
  if (!scene) return { ok: false, reason: "window.__hqScene is not set -- ?diag=1 missing or scene not mounted yet" };
  const THREE = await loadThree();
  const viewportW = gl?.domElement?.clientWidth || (typeof window !== "undefined" ? window.innerWidth : 0);
  const viewportH = gl?.domElement?.clientHeight || (typeof window !== "undefined" ? window.innerHeight : 0);
  return { ok: true, screenViewportRects: computeScreenViewportRectsSync(THREE, scene, camera, viewportW, viewportH) };
}

async function computeSceneAuditReport(): Promise<Record<string, unknown>> {
  const scene = (window as unknown as { __hqScene?: TaggedObject3D }).__hqScene;
  const camera = (window as unknown as { __hqCamera?: { position?: { x: number; y: number; z: number } } }).__hqCamera;
  const gl = (window as unknown as { __hqGl?: { domElement?: { clientWidth?: number; clientHeight?: number } } }).__hqGl;
  if (!scene) return { ok: false, reason: "window.__hqScene is not set -- ?diag=1 missing or scene not mounted yet" };

  const THREE = await loadThree();
  const layout = await loadLayout();

  const viewportW = gl?.domElement?.clientWidth || (typeof window !== "undefined" ? window.innerWidth : 0);
  const viewportH = gl?.domElement?.clientHeight || (typeof window !== "undefined" ? window.innerHeight : 0);

  const furniture: ObjectAabb[] = [];
  const screens: ScreenInfo[] = [];
  const screenViewportRects: ScreenViewportRect[] = [];
  const doors: ObjectAabb[] = [];
  const deskCandidates: Array<{ id: string; position: Vec3; yaw: number }> = [];
  let counter = 0;
  const box3 = new THREE.Box3();
  const geomBox = new THREE.Box3();
  const m4 = new THREE.Matrix4();
  const worldM4 = new THREE.Matrix4();
  const vPos = new THREE.Vector3();
  const vNormal = new THREE.Vector3();

  scene.traverse((obj) => {
    const kind = obj.userData?.hqKind;
    if (!kind) return;
    const label = obj.userData?.hqLabel ?? kind;

    if (obj.isInstancedMesh && obj.getMatrixAt && obj.geometry && obj.matrixWorld) {
      if (!obj.geometry.boundingBox) obj.geometry.computeBoundingBox?.();
      if (!obj.geometry.boundingBox) return;
      geomBox.copy(obj.geometry.boundingBox as InstanceType<typeof THREE.Box3>);
      const count = obj.count ?? 0;
      for (let i = 0; i < count; i++) {
        obj.getMatrixAt(i, m4);
        worldM4.multiplyMatrices(obj.matrixWorld as InstanceType<typeof THREE.Matrix4>, m4);
        box3.copy(geomBox).applyMatrix4(worldM4);
        const aabb: AABB = { min: [box3.min.x, box3.min.y, box3.min.z], max: [box3.max.x, box3.max.y, box3.max.z] };
        const id = `${label}-${counter++}-${i}`;
        if (kind === "furniture") {
          furniture.push({ id, label, aabb });
          if (label === "desk") {
            const center = new THREE.Vector3();
            box3.getCenter(center);
            deskCandidates.push({ id, position: [center.x, center.y, center.z], yaw: extractYawFromMatrix(THREE, m4) });
          }
        } else if (kind === "door") {
          doors.push({ id, label, aabb });
        }
      }
      return;
    }

    obj.updateWorldMatrix?.(true, false);
    box3.setFromObject(obj as unknown as InstanceType<typeof THREE.Object3D>);
    if (box3.isEmpty()) return;
    const aabb: AABB = { min: [box3.min.x, box3.min.y, box3.min.z], max: [box3.max.x, box3.max.y, box3.max.z] };
    const id = `${label}-${counter++}`;
    if (kind === "screen") {
      obj.getWorldPosition?.(vPos);
      const localNormal = obj.userData?.hqFaceLocalNormal ?? [0, 0, 1];
      vNormal.set(localNormal[0], localNormal[1], localNormal[2]);
      vNormal.transformDirection(obj.matrixWorld as InstanceType<typeof THREE.Matrix4>);
      const readable = !obj.userData?.hqInformational;
      screens.push({
        id,
        label,
        position: [vPos.x, vPos.y, vPos.z],
        normal: [vNormal.x, vNormal.y, vNormal.z],
        readable,
      });
      const rect = projectAabbToViewportRect(THREE, aabb, camera, viewportW, viewportH);
      if (rect) screenViewportRects.push({ id, label, readable, ...rect });
    } else if (kind === "furniture") {
      furniture.push({ id, label, aabb });
    } else if (kind === "door") {
      doors.push({ id, label, aabb });
    }
  });

  const baySlots = layout.computeAllBaySlots(8);
  const slabs: WallSlab[] = [
    ...buildHubSlabs(),
    ...baySlots.flatMap((slot) => buildBaySlabs(`bay-${slot.index}`, [slot.position[0], slot.position[2]], slot.rotationY)),
  ];

  // Desk-orientation pairing (DESKS-AGAINST-WALLS pass, made INDEPENDENT of
  // layout.ts's own output -- see nearestHubWallYaw's own header for why the
  // old "ask layout.ts what this slot's rotationY should be" pairing was
  // tautological): a bay desk still pairs against its OWN bay's rotationY
  // (bay walls are rotated per-bay, not axis-aligned in world space, so a
  // from-scratch geometric derivation isn't practical here without also
  // reading each bay's own rotation -- out of this pass's scope, bay
  // desk orientation is unchanged); a desk near one of the HUB's own real
  // (axis-aligned, world-space) walls gets the fully independent
  // nearestHubWallYaw treatment instead; anything else (Gamma's own hub
  // desk, near the core, backed against nothing) keeps the old "faces
  // toward or away from hub center" heuristic.
  const deskOrientationInput = deskCandidates.map((d) => {
    let nearestBay: { dist: number; rotationY: number } | null = null;
    for (const slot of baySlots) {
      const dist = Math.hypot(d.position[0] - slot.position[0], d.position[2] - slot.position[2]);
      if (!nearestBay || dist < nearestBay.dist) nearestBay = { dist, rotationY: slot.rotationY };
    }
    if (nearestBay && nearestBay.dist < 2.2) {
      return { id: d.id, actualYaw: d.yaw, targetYaw: nearestBay.rotationY };
    }
    const chebyshevWallDist = HUB_HALF_EXTENT - Math.max(Math.abs(d.position[0]), Math.abs(d.position[2]));
    if (chebyshevWallDist >= 0 && chebyshevWallDist < HUB_WALL_ADJACENCY_BAND_U) {
      return { id: d.id, actualYaw: d.yaw, targetYaw: nearestHubWallYaw(d.position) };
    }
    const towardHub = layout.rotationYFacing(d.position, layout.HUB);
    const diffToward = Math.abs(wrapAngleRad(d.yaw - towardHub));
    const diffAway = Math.abs(wrapAngleRad(d.yaw - (towardHub + Math.PI)));
    const targetYaw = diffToward <= diffAway ? towardHub : towardHub + Math.PI;
    return { id: d.id, actualYaw: d.yaw, targetYaw };
  });

  const liveCamera: CameraInfo = camera?.position ? { position: [camera.position.x, camera.position.y, camera.position.z] } : { position: [0, 10, 14] };
  // Synthetic top-down camera -- no such preset exists (Scene.tsx's own
  // ?preset= list has none; J reached top-down by manually orbiting) --
  // task's own instruction: "no preset needed", evaluate a synthetic
  // straight-down vector at a fixed height above hub center.
  const topDownCamera: CameraInfo = { position: [0, 60, 0] };

  const desks = deskCandidates.map((d) => {
    const bboxHalf = 0.6; // approximate desk half-footprint for the synthetic AABB used by wall_penetration/clearance below -- the REAL AABB for these same objects is already in `furniture`, this is only used to re-key desks out of that list.
    return { id: d.id, label: "desk", aabb: { min: [d.position[0] - bboxHalf, 0, d.position[2] - bboxHalf], max: [d.position[0] + bboxHalf, 1.2, d.position[2] + bboxHalf] } as AABB };
  });
  const deskAabbs = furniture.filter((f) => f.label === "desk");
  const deskSource = deskAabbs.length ? deskAabbs : desks;

  const wallPenetration = checkWallPenetration([...furniture, ...screens.map((s) => ({ id: s.id, label: s.label, aabb: { min: s.position, max: s.position } }))], slabs);
  const screenFacing = checkScreenFacing(screens, liveCamera, topDownCamera);
  // DESKS-AGAINST-WALLS pass: split desks into "backed against a real HUB
  // wall" (same Chebyshev classification checkDeskOrientation's own pairing
  // above uses, keyed by id via deskCandidates rather than re-measuring) vs
  // everything else (bay desks, Gamma's own hub desk) -- the FIRST group
  // wants the tight 0.2-0.6u back-wall band (see checkDeskClearance's own
  // header for why a blanket >=1.0u would wrongly FAIL a correctly-placed
  // against-the-wall desk); the SECOND group keeps the original >=1.0u-from-
  // any-wall rule unchanged, matching every bay-desk test already pinned.
  const deskPositionById = new Map(deskCandidates.map((d) => [d.id, d.position] as const));
  const HUB_BACK_WALL_BAND: WallBand = { min: 0.15, max: 0.7 }; // generous real-capture tolerance around the 0.2-0.6u design ask
  const hubWallDesks: ObjectAabb[] = [];
  const otherDesks: ObjectAabb[] = [];
  for (const d of deskSource) {
    const pos = deskPositionById.get(d.id);
    const chebyshevWallDist = pos ? HUB_HALF_EXTENT - Math.max(Math.abs(pos[0]), Math.abs(pos[2])) : -Infinity;
    if (chebyshevWallDist >= 0 && chebyshevWallDist < HUB_WALL_ADJACENCY_BAND_U) hubWallDesks.push(d);
    else otherDesks.push(d);
  }
  const deskClearanceHub = checkDeskClearance(hubWallDesks, slabs, furniture, 1.0, HUB_BACK_WALL_BAND);
  const deskClearanceOther = checkDeskClearance(otherDesks, slabs, furniture);
  const deskClearance: CheckResult =
    deskClearanceHub.verdict === "NO-DATA" ? deskClearanceOther :
    deskClearanceOther.verdict === "NO-DATA" ? deskClearanceHub :
    {
      verdict: deskClearanceHub.verdict === "FAIL" || deskClearanceOther.verdict === "FAIL" ? "FAIL" : "PASS",
      detail: { hub: deskClearanceHub.detail, other: deskClearanceOther.detail },
    };
  const deskOrientation = checkDeskOrientation(deskOrientationInput);

  return {
    ok: true,
    wallPenetration,
    screenFacing,
    deskClearance,
    deskOrientation,
    // SCREEN-KEEP-OUT pass: this frame's own screen viewport rects, for
    // setup/scripts/hq_live_probe.py to combine with its OWN `.hq-beam` DOM
    // label rects via window.__hqSceneAuditLabelScreenOverlap() below --
    // exposed raw (not pre-joined with labels) since the static report is
    // captured once while label rects are sampled repeatedly over the run.
    screenViewportRects,
    raw: {
      furnitureCount: furniture.length, screenCount: screens.length, doorCount: doors.length,
      wallSlabCount: slabs.length, deskCount: deskCandidates.length,
      viewport: { width: viewportW, height: viewportH },
    },
  };
}

const walkerPositionSamples: Map<string, Array<{ t: number; pos: Vec2 }>> = new Map();
const WALKER_SAMPLE_CAP = 400;

/** Cheap per-tick walker XZ snapshot -- meant to be called by the Python
 * probe at <=4x/s (per this pass's own task spec) over the run, accumulating
 * into a module-scope history it can hand back as tracks for
 * checkWalkerWallCross. Reads window.__hqLiveAgents (LiveAgents.tsx's own
 * existing diag export, already proven live by hq_probe_lib.py's other
 * checks) rather than traversing the scene graph for SkinnedMesh ancestors
 * -- LiveAgents/Agent/GammaCharacter are off-limits to this pass per the
 * task brief, but they ALREADY publish id+pos on window.__hqLiveAgents for
 * every other check in this probe to read, so this reuses that existing
 * contract instead of adding new tagging to files this pass cannot touch. */
function computeWalkerSnapshot(): Record<string, unknown> {
  const pageAgents = (window as unknown as { __hqLiveAgents?: Array<{ id: string; pos?: Vec2 }> }).__hqLiveAgents ?? [];
  const t = performance.now();
  for (const a of pageAgents) {
    if (!a.id || !a.pos) continue;
    const arr = walkerPositionSamples.get(a.id) ?? [];
    arr.push({ t, pos: a.pos });
    if (arr.length > WALKER_SAMPLE_CAP) arr.shift();
    walkerPositionSamples.set(a.id, arr);
  }
  return {
    tracks: Array.from(walkerPositionSamples.entries()).map(([id, points]) => ({ id, points: [...points] })),
  };
}

/** Builds the SAME hub+bay wall-slab set computeSceneAuditReport uses and
 * runs checkWalkerWallCross against a caller-supplied track list -- kept as
 * its OWN window hook (rather than folding into computeSceneAuditReport)
 * because walker tracks accumulate over the WHOLE run (via repeated
 * computeWalkerSnapshot polls) while the static geometry only needs
 * capturing once; the Python probe calls this ONE extra time at the end of
 * its run with the full accumulated track list. Single source of truth for
 * "what counts as a wall" either way -- both hooks call buildHubSlabs/
 * buildBaySlabs, never a second copy of the geometry. */
async function computeWalkerWallCrossReport(tracks: WalkerTrack[]): Promise<CheckResult> {
  const layout = await loadLayout();
  const baySlots = layout.computeAllBaySlots(8);
  const slabs: WallSlab[] = [
    ...buildHubSlabs(),
    ...baySlots.flatMap((slot: { index: number; position: Vec3; rotationY: number }) =>
      buildBaySlabs(`bay-${slot.index}`, [slot.position[0], slot.position[2]], slot.rotationY),
    ),
  ];
  return checkWalkerWallCross(tracks, slabs);
}

/** Expected seat position + desk-facing yaw for each of /api/hq's own
 * `company.personas` (excluding index 0, Gamma, who has no wall slot --
 * see Scene.tsx's `allPersonas[0]`/`innerPersonas` convention), derived
 * from the SAME layout.ts#computePersonaWallSlots + palette.ts#localToWorld
 * calls Scene.tsx itself uses to place `<DeskCluster>`/`<Agent
 * deskYaw={slot.rotationY}>` -- never a second, independently-guessed
 * geometry. `personaNames` must be passed by the caller in /api/hq's own
 * order (hq_live_probe.py already fetches that JSON for other checks) --
 * this function never re-derives the roster itself.
 *
 * BAY_SEAT_LOCAL=[0,0,0.1] and BRAIN_WALL_ARM_INDEX=0 are hardcoded here
 * rather than imported: SetKit.tsx (BAY_SEAT_LOCAL's real source) and
 * Scene.tsx (BRAIN_WALL_ARM_INDEX's real source) are both off-limits to
 * this pass. Scene.tsx's own `personaSeatLocal = ultra ? BAY_SEAT_LOCAL :
 * TV_PERSONA_SEAT_LOCAL` picks BAY_SEAT_LOCAL whenever `?tier=ultra` is
 * set -- hq_live_probe.py's DEFAULT_URL always sets it -- and
 * BAY_SEAT_LOCAL = [0,0, BAY_DESK_OFFSET_Z(0.8) + DESK_SEAT_LOCAL[2](-0.35 *
 * FURNITURE_SCALE(2.0) = -0.7)] = [0,0,0.1] (SetKit.tsx's own constants,
 * read not guessed). BRAIN_WALL_ARM_INDEX=0 is "today's" value per
 * layout.ts's own BRAIN_WALL_MOUNT/MONITOR_MOUNT constants, which already
 * duplicate this exact literal for the identical off-limits-file reason --
 * this is a third, consistent duplication, not a new convention. */
async function computeSeatedPoseExpectedReport(personaNames: string[]): Promise<Record<string, SeatedPoseExpected>> {
  const layout = await loadLayout();
  const palette = await loadPalette();
  const inner = personaNames.slice(1);
  const count = Math.max(inner.length, 1);
  const BRAIN_WALL_ARM_INDEX = 0;
  const BAY_SEAT_LOCAL: Vec3 = [0, 0, 0.1];
  const slots = layout.computePersonaWallSlots(count, BRAIN_WALL_ARM_INDEX);
  const out: Record<string, SeatedPoseExpected> = {};
  inner.forEach((name: string, i: number) => {
    const slot = slots[i % slots.length];
    out[name] = {
      seat: palette.localToWorld(slot.position, slot.rotationY, BAY_SEAT_LOCAL),
      yaw: slot.rotationY,
      wallSlotIndex: i,
    };
  });
  return out;
}

let installed = false;

/** Wires window.__hqSceneAudit / window.__hqSceneAuditWalkers /
 * window.__hqSceneAuditWalkerCheck behind the SAME `?diag=1` gate every
 * other diag hook in this tree uses. Call once at module scope from a
 * canvas-root file (see UltraCanvasRoot.tsx's own import) -- idempotent,
 * matching installEarlyErrorCapture()'s convention. */
export function installSceneAuditHooks(): void {
  if (typeof window === "undefined" || installed) return;
  if (!diagFlagEnabled()) return;
  installed = true;
  (window as unknown as { __hqSceneAudit?: () => Promise<Record<string, unknown>> }).__hqSceneAudit = computeSceneAuditReport;
  (window as unknown as { __hqSceneAuditWalkers?: () => Record<string, unknown> }).__hqSceneAuditWalkers = computeWalkerSnapshot;
  (window as unknown as { __hqSceneAuditWalkerCheck?: (tracks: WalkerTrack[]) => Promise<CheckResult> }).__hqSceneAuditWalkerCheck = computeWalkerWallCrossReport;
  // SCREEN-KEEP-OUT PER-TICK FIX -- see computeScreenViewportRectsReport's
  // own header. Cheap enough to call every plausibility tick (4x/s), unlike
  // __hqSceneAudit's full wall/desk/furniture traversal.
  (window as unknown as { __hqSceneAuditScreens?: () => Promise<Record<string, unknown>> }).__hqSceneAuditScreens = computeScreenViewportRectsReport;
  // SEATED-POSE-AUDIT pass -- see computeSeatedPoseExpectedReport's own
  // header. Takes the caller's /api/hq persona-name order (hq_live_probe.py
  // already fetches that JSON) rather than re-deriving the roster here.
  (window as unknown as { __hqSceneAuditSeatedPose?: (personaNames: string[]) => Promise<Record<string, SeatedPoseExpected>> }).__hqSceneAuditSeatedPose = computeSeatedPoseExpectedReport;
}

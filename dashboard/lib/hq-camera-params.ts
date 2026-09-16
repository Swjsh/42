// CAM-PARAMS pass (2026-09-15): pure URL-param parsing for the 3 deterministic
// capture-framing overrides Scene.tsx#CameraRig applies (ultra tier only --
// see that file's own `?camdist=`/`?cam=`/`?preset=` header comments for the
// established "one-shot URL override parks the camera in userFree" pattern
// this extends). Split into its own lib module (no React/three import) so it
// can be unit-tested with plain `node --test` the same way labelDeclutter.ts
// is -- CameraRig itself can't be imported standalone (lives inside <Canvas>,
// pulls in three/@react-three/fiber).
//
// Motivation (orchestrator, 2026-09-15): `setup/scripts/hq_capture.ps1
// -Frames` sequences can't prove a walk-out today because the kiosk camera
// tours (the "auto" cinematic orbit + director vignette panning already in
// CameraRig) between frames, and avatars are tiny at the default overview
// distance. `?camdist`/`?camtarget`/`?tour=0` let a capture script frame a
// deterministic, still shot instead.

/** Ultra tier's own free-camera zoom bounds (Scene.tsx's
 * FREE_CAM_MIN_DISTANCE/FREE_CAM_MAX_DISTANCE) -- re-exported here as the
 * single source of truth for `camdist`'s clamp so Scene.tsx imports these
 * instead of keeping a second, possibly-drifting pair of literals. */
export const CAM_DIST_MIN = 6;
export const CAM_DIST_MAX = 58;

export interface CameraParams {
  /** Validated, clamped camera distance from its target, in world units.
   * `undefined` when `?camdist=` is absent, not a finite number, or blank. */
  camDist?: number;
  /** Raw `?camtarget=` value -- a walk-graph node id (e.g. "campus-gate",
   * "hub-center", "bay-desk-0", "ambient-core"), resolved against the real
   * WalkGraph by the caller (this module has no graph to check against).
   * `undefined` when the param is absent or blank; an id that turns out not
   * to exist in the graph is the CALLER's responsibility to ignore (this
   * function can't know). */
  camTarget?: string;
  /** `false` only when `?tour=0` is present (exact string "0") -- disables
   * the automatic cinematic orbit/vignette so the camera holds still.
   * `true` (tour ON, today's default behavior) for every other value or a
   * missing param, so a bare page load stays byte-for-byte unchanged. */
  tour: boolean;
}

/** Parses the 3 camera-framing URL params from a real `URLSearchParams`
 * (or any object exposing the same `.get()`). Pure -- no DOM/window access,
 * no side effects, safe to unit-test directly. */
export function parseCameraParams(searchParams: Pick<URLSearchParams, "get">): CameraParams {
  const camDist = parseCamDist(searchParams.get("camdist"));
  const camTarget = parseCamTarget(searchParams.get("camtarget"));
  const tour = searchParams.get("tour") !== "0";
  return { camDist, camTarget, tour };
}

function parseCamDist(raw: string | null): number | undefined {
  if (raw === null || raw.trim() === "") return undefined;
  const n = Number(raw);
  // Number("") is 0, not NaN -- already excluded by the blank check above.
  // Number.isFinite also rejects NaN/Infinity/-Infinity from a malformed or
  // absurd input, matching this task's "NaN/negative/absurd -> ignored"
  // requirement for anything Number() can't make sense of; a genuinely
  // out-of-range finite value (negative, or past the ceiling) is clamped
  // below instead of dropped, same as the pre-existing `?camdist=` behavior
  // this pass preserves byte-for-byte.
  if (!Number.isFinite(n)) return undefined;
  return Math.min(CAM_DIST_MAX, Math.max(CAM_DIST_MIN, n));
}

function parseCamTarget(raw: string | null): string | undefined {
  if (raw === null) return undefined;
  const trimmed = raw.trim();
  return trimmed === "" ? undefined : trimmed;
}

/** MONITORS-READABLE pass (2026-09-15): pure predicate for the `?tour=0`
 * bug fix -- a bare `?tour=0` (no `camdist`/`camtarget`/`cam`) must land on
 * the SAME overview pose `?camdist=48`-style captures already prove
 * correct (Scene.tsx#CameraRig's own tour effect writes OVERVIEW_CAM_POS/
 * DEFAULT_LOOKAT when this returns `true`, then parks either way); when any
 * other override is present, that override's OWN effect already wrote a
 * real pose, so this returns `false` and the tour effect only parks
 * without touching position -- never fighting `?camdist=`/`?camtarget=`/
 * `?cam=`. `hasRawCamParam` is the caller's own `searchParams.get("cam")
 * !== null` check -- `cam` has no place in `CameraParams` (it's 6 raw
 * numbers fully replacing position+target, parsed/validated in its own
 * effect, not this module) so the presence check stays the caller's job;
 * this function only combines it with the two params this module DOES
 * parse. */
/** `hasRawPoseParam` = the caller saw a raw `?cam=` OR `?preset=` in the URL.
 * 2026-09-16 fix: the first version only checked `?cam=`, so
 * `?tour=0&preset=N` snapped to the overview and silently ignored the preset
 * -- every "close-up" capture after e5a0bf99 was really the overview
 * (crew-desk2-0110.png == crew-hub-0110.png == overview), and the
 * DESK-PRESETS worker's "preset framed a door" report was this bug. */
export function shouldParkTourAtOverview(params: Pick<CameraParams, "camDist" | "camTarget">, hasRawPoseParam: boolean): boolean {
  return params.camDist === undefined && params.camTarget === undefined && !hasRawPoseParam;
}

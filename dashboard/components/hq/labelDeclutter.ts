// ─── Screen-space label declutter (2026-09-14, DECLUTTER builder pass) ─────
// J review (real captures automation/state/station/captures/boardfit-*.png,
// read at 1:1): "BRAIN · wrote brief" (BrainCore.tsx's own plaque) cuts into
// a Coach bubble and a general-purpose live-agent bubble at the hub center;
// at the close cam the plaque sits between two general-purpose bubbles, and
// bubbles draw over the board face. ROOT CAUSE (confirmed by reading every
// label producer before writing this file): each of BrainCore.tsx's
// plaques, Agent.tsx's persona/lane bubbles, GammaCharacter.tsx's bubble,
// and LiveAgents.tsx's bubbles independently projects its OWN world anchor
// to screen space (via drei's <Html>) with its own camera-distance
// scale/fade -- none of them know about any of the others, so any cluster
// at the hub center overlaps whatever the mount heights happen to be.
//
// This module is the PURE half of the fix: given a frame's worth of label
// screen-space rects (already projected + measured by the caller), decide
// a vertical pixel offset + opacity for each one so overlaps resolve
// without ever moving a label sideways or reflowing text. Zero DOM, zero
// three.js, zero React -- unit-testable in plain `node --test`, and
// reusable from the one shared hook (useLabelDeclutter.ts) every label
// producer registers through.
//
// ALGORITHM (greedy, priority-then-distance order): sort every rect by
// `priority` ascending (lower number = higher precedence, i.e. this label
// keeps its resting position first) then by `distance` ascending (nearer
// to the camera wins a same-priority tie) then by `id` (fully deterministic
// tie-break so two calls with identical input NEVER produce different
// output -- this is what makes the label's on-screen position STABLE frame
// to frame, the "no jitter" requirement). Walk that order; for each label,
// try nudging along EACH axis independently in fixed NUDGE_STEP_PX
// increments until its (offset) rect no longer overlaps any ALREADY-PLACED
// (higher-precedence) rect -- then take whichever axis cleared the
// collision with the SMALLER total displacement (coordinator fix,
// 2026-09-15: a vertical-only nudge could not resolve two labels sitting
// side by side in the SAME row within a small cap -- e.g. two ~26px-tall,
// ~140px-wide bubbles offset mostly in X need ~140px of vertical travel to
// clear fully, but often far less horizontal travel, since the real-world
// overlap that trips this is usually two ADJACENT columns, not a dead-on
// stack). If NEITHER axis clears within `maxNudgePx`, the smaller-
// displacement axis is still used (closest to resolved) and the label
// fades instead of stacking forever (brief's own "beyond the cap,
// lower-priority labels fade" rule). A label is nudged along exactly ONE
// axis, never both -- diagonal nudges would make the stack read as
// scattered rather than an intentional list.

export interface LabelRect {
  /** Stable identity across frames (e.g. "persona:Coach", "live:abc123",
   * "plaque:brain", "lane:Futures") -- used only for the final tie-break,
   * never for lookup, so any string works as long as it's the same string
   * for the same label every frame. */
  id: string;
  /** Precedence tier. Lower number wins a collision (keeps offset 0 first).
   * Callers should use PRIORITY.* below rather than hand-rolled numbers, so
   * every producer agrees on the same 4 tiers. */
  priority: number;
  /** Camera distance in world units -- the ONLY same-priority tie-break
   * ("nearest-to-camera keeps its place"). */
  distance: number;
  /** Screen-space rect BEFORE any declutter offset, in CSS pixels, resting
   * top-left convention (x,y = top-left corner). */
  x: number;
  y: number;
  width: number;
  height: number;
  /** Optional order-preservation group (LEVEL-ORDER fix, 2026-09-15). Labels
   * sharing the same `orderGroup` carry a real, meaningful vertical rank
   * (e.g. a SPY price -- a level plaque and the last-close plaque both
   * belong to the same "things positioned by price" family) that the
   * collision-avoidance nudge below must never invert: a real capture
   * (hq-close-1653.png) showed "757.44 RESISTANCE" pushed BELOW "757.38 ·
   * last close" even though 757.44 > 757.38 -- the generic resolver has no
   * notion of price, only of pixel overlap, so a same-priority nudge could
   * freely reorder two plaques whose relative position the viewer reads as
   * meaningful. Omit both `orderGroup` and `orderKey` for a label with no
   * such constraint (every existing caller/behavior is unchanged). */
  orderGroup?: string;
  /** Rank within `orderGroup` -- SMALLER orderKey must never end up with a
   * LARGER final screen-space y (further down) than a label with a LARGER
   * orderKey in the same group, after collision offsets are applied. See
   * `enforceGroupOrder` below for the exact guarantee. */
  orderKey?: number;
  /** LEGIBLE-LABELS fix (2026-09-16, real probe FAIL U5: "live-agent head
   * label not legible on the default view" -- a live agent standing at its
   * core stand slot in the camera->monitor sightline had its head label
   * faded to 0 by the SCREEN-KEEP-OUT HARDENING above, because a capped
   * nudge could not clear the screen rect within `maxNudgePx`). ROOT CAUSE:
   * the screen keep-out (see `ObstacleRect.isScreen`'s own header) is
   * correct for DECORATIVE labels -- a level plaque or lane sign quietly
   * fading rather than occluding the monitor face is the right call -- but
   * for an "answer-bearing" label (a live agent's own identity, a persona's
   * head label, a desk nameplate, the BRAIN plaque) fading is not an
   * acceptable outcome: the whole point of the label is to say WHO this is,
   * and a legible-but-elsewhere label beats an invisible one every time.
   * When true, `resolveLabelOffsets` below gives this label a much larger
   * nudge budget (MUST_STAY_LEGIBLE_MAX_NUDGE_PX, not the caller's
   * `maxNudgePx`) and tries the vertical axis, then the lateral axis, at
   * that larger budget BEFORE falling back to the normal smaller-
   * displacement axis choice -- and never fades this label to 0/fadeOpacity
   * for a screen (or any) obstacle collision, even if the larger nudge still
   * doesn't fully clear (best-effort placement beats invisibility). Default
   * undefined/false preserves every existing label's exact prior behavior
   * (decorative labels still fade past the cap, screens still win a
   * collision, nothing about non-flagged labels changes). */
  mustStayLegible?: boolean;
}

/** A fixed DOM rect the resolver must never place a label on top of, but
 * which the resolver itself never moves -- the HUD's own overlays (help
 * bar, title block, right panel, perf/Synced corner) registered via
 * `data-hq-obstacle` (see LabelDeclutterManager.tsx's own header) rather
 * than a world Html label. Same screen-space/CSS-pixel convention as
 * `LabelRect`, minus `priority`/`distance` -- an obstacle always outranks
 * every label (it is seeded into the resolver's `placed` list ahead of
 * anything in `rects`) and is never itself nudged or included in the
 * output map, so callers don't need to special-case "this id has no
 * offset." */
export interface ObstacleRect {
  /** Stable identity, purely for debugging -- never looked up. */
  id: string;
  x: number;
  y: number;
  width: number;
  height: number;
  /** SCREEN-KEEP-OUT HARDENING (2026-09-16, real probe FAIL:
   * label_vs_screen_overlap on twin-monitor-101/102, worst labels "Coach"
   * and "Claude (you)" at overlapFrac 0.19/0.30). ROOT CAUSE: a label that
   * cannot fully clear an obstacle within `maxNudgePx` fades to the
   * generic `fadeOpacity` (0.35 default) -- fine for two COLLIDING LABELS
   * (a deprioritized bubble staying dimly visible is the intended look),
   * but hq_probe_lib.py's own check_label_screen_overlap only excludes a
   * label below LABEL_LEGIBILITY_MIN_OPACITY (0.05): 0.35 is well above
   * that floor, so a capped-nudge label pinned against a big/close screen
   * mesh (a real monitor's projected rect is often far larger than the
   * default 60px cap can clear in one axis -- see this file's own
   * DEFAULT_MAX_NUDGE_PX) stays a counted violation even though the
   * resolver "did its best". Screens are strictly worse to occlude than
   * another bubble (they're the readable content this whole pass exists
   * to protect), so this flag makes resolveLabelOffsets fade a
   * still-colliding label to opacity 0 instead of `fadeOpacity` -- but
   * ONLY when the obstacle it failed to clear is a screen, never for a
   * generic HUD panel (`[data-hq-obstacle]`), which keeps the pre-existing
   * "pinned against an obstacle past the cap fades to fadeOpacity" test
   * and behavior unchanged for that case. Set by
   * LabelDeclutterManager.tsx's `readScreenObstacleRects` only. */
  isScreen?: boolean;
}

export interface LabelOffset {
  /** Horizontal pixel nudge (positive = further right). Mutually exclusive
   * with `dy` -- a label is nudged along exactly ONE axis (whichever
   * clears the collision with the smaller total displacement -- see this
   * file's own header), never both, so it never drifts diagonally. 0 for a
   * label that never collided, or one nudged along `dy` instead. */
  dx: number;
  /** Vertical pixel nudge (positive = further down). See `dx`'s own
   * comment for the "exactly one axis" rule. */
  dy: number;
  /** 1 normally; drops to the caller's `fadeOpacity` once the CHOSEN axis's
   * offset has been clamped at `maxNudgePx` and the label is STILL
   * colliding at the cap (fades instead of stacking further). */
  opacity: number;
}

/** Precedence tiers, per the brief: "live-agent bubbles and Gamma > persona
 * bubbles > plaque > lane labels." Lower number = kept in place first. */
export const PRIORITY = {
  LIVE_AGENT: 0,
  GAMMA: 0,
  PERSONA: 1,
  PLAQUE: 2,
  LANE: 3,
} as const;

export const DEFAULT_MAX_NUDGE_PX = 60;
export const DEFAULT_FADE_OPACITY = 0.35;
const NUDGE_STEP_PX = 6;

// LEGIBLE-LABELS fix (2026-09-16) -- see `LabelRect.mustStayLegible`'s own
// header for the full evidence. This budget is deliberately far larger than
// the tallest realistic on-screen obstacle (a projected TwinMonitors screen
// rect at the overview camera distance, per this file's own capture
// evidence, rarely exceeds a few hundred px) so a flagged label almost
// always finds room above/beside the glass rather than merely getting
// closer and still fading -- see the resolver's own "best-effort placement
// beats invisibility" fallback below for the rare case it still can't.
export const MUST_STAY_LEGIBLE_MAX_NUDGE_PX = 600;

// LEGIBILITY-FLOOR fix (2026-09-15, real-probe evidence: hq_live_probe.py
// --plausibility, label_legibility FAIL 20 violation(s), first violation
// `{'text': '757.38 · last close', 'height_px': 7.77}`). HoloChart's level/
// last-close/trade-marker plaques (drei `<Html>` with a plain
// `distanceFactor`, no counter-scale floor the way Agent.tsx/
// GammaCharacter.tsx/LiveAgents.tsx's head bubbles already have via
// bubbleScale.ts) shrink without bound as the overview camera pulls back --
// at that distance a human sees unreadable noise, not information. Any
// registered label this resolver measures below MIN_LEGIBLE_PX is faded to
// opacity 0 UNCONDITIONALLY, same "never unmounted" convention every other
// fade in this file already uses (the DOM node stays mounted/measurable --
// callers needing "is legibility hiding me" for a summary-plaque fallback
// read this same floor via isBelowLegibilityFloor, not a second signal).
// This is independent of, and applied AFTER, the collision-avoidance
// dx/dy/opacity above -- a label can be too small to read even with zero
// collisions.
// Pinned to the SAME value as setup/scripts/hq_probe_lib.py's own
// LABEL_MIN_HEIGHT_PX (12.0, PROBE-13's pre-existing size gate) rather than
// the round "11px" first named for this fix -- the probe's own
// check_label_legibility FAILs on `h < LABEL_MIN_HEIGHT_PX`, and this
// runtime floor exists specifically to make that check PASS; a 1px gap
// between the two constants would leave a dead band (11-12px) this fix
// renders as "legible" while the probe still calls it a violation. One
// floor, two enforcement points, always in agreement.
export const MIN_LEGIBLE_PX = 12;

/** True when a measured label height (CSS px, as read from the label's own
 * `measureRef.getBoundingClientRect()`) falls below the floor every
 * registered label is held to. Exported so callers (HoloChart's summary-
 * plaque fallback) can react to the SAME threshold this resolver enforces,
 * never a second hand-tuned number. */
export function isBelowLegibilityFloor(heightPx: number, floorPx: number = MIN_LEGIBLE_PX): boolean {
  return heightPx < floorPx;
}

// ─── Screen keep-out (2026-09-16, probe 20260916T005621Z label_vs_screen_
// overlap FAIL) ──────────────────────────────────────────────────────────
//
// ROOT CAUSE: commit 77e8308f ("screen keep-out and label_vs_screen_overlap
// audit") shipped the CHECK (hq-scene-audit.ts#checkLabelScreenOverlap,
// hq_probe_lib.py) but never actually wired a runtime keep-out -- that
// commit's own diff touches labelDeclutter.ts/LabelDeclutterManager.tsx
// only for the UNRELATED legibility-floor fix in the same pass. The
// resolver's own `ObstacleRect` mechanism (above) already handles "a
// fixed rect always outranks every label, regardless of priority" --
// correctly, per this file's own pre-existing tests -- but
// LabelDeclutterManager.tsx only ever fed it `[data-hq-obstacle]` DOM HUD
// overlays (help bar, panels), never the two readable TwinMonitors screens.
// Gamma's own head label and a live agent's label were therefore never
// nudged clear of either screen at all -- not "nudged but insufficiently",
// literally never checked against them.
//
// FIX: `ndcCornersToViewportRect` here is the pure half (mirrors
// hq-scene-audit.ts's own `projectAabbToViewportRect` exactly, so the
// runtime keep-out and the offline probe check agree on what "the
// screen's own rect" means) -- LabelDeclutterManager.tsx's own new
// `readScreenObstacleRects` (three.js/scene-traversal half, not pure, not
// unit-tested here) calls a real THREE.Camera's `.project()` to get each
// screen's NDC corners, then this function turns those into a viewport
// pixel rect and LabelDeclutterManager.tsx passes it into
// `resolveLabelOffsets`'s existing `obstacles` argument -- no change to
// the resolver's own precedence rules (screens already outrank every
// label, priority included, the same way any other obstacle does).
export function ndcCornersToViewportRect(
  ndcCorners: ReadonlyArray<readonly [number, number]>,
  viewportW: number,
  viewportH: number,
): { x: number; y: number; width: number; height: number } | null {
  if (viewportW <= 0 || viewportH <= 0 || ndcCorners.length === 0) return null;
  let pxMin = Infinity;
  let pxMax = -Infinity;
  let pyMin = Infinity;
  let pyMax = -Infinity;
  for (const [nx, ny] of ndcCorners) {
    if (!Number.isFinite(nx) || !Number.isFinite(ny)) return null;
    const px = ((nx + 1) / 2) * viewportW;
    const py = ((1 - ny) / 2) * viewportH;
    pxMin = Math.min(pxMin, px);
    pxMax = Math.max(pxMax, px);
    pyMin = Math.min(pyMin, py);
    pyMax = Math.max(pyMax, py);
  }
  return { x: pxMin, y: pyMin, width: pxMax - pxMin, height: pyMax - pyMin };
}

// COLD-START SNAP FIX (2026-09-15, real-GPU probe evidence: samples file
// 20260915T090312Z-Da6D81TEcI6kH8JvM85Db.samples.json.gz). Root cause: the
// manager (LabelDeclutterManager.tsx) unconditionally lerps a label's
// applied on-screen offset toward this tick's resolved target by
// SMOOTH_FACTOR (0.4) EVERY tick, including the very first tick a label
// goes from "not colliding" (applied offset ~0) to "needs a nudge" (a fresh,
// non-zero target). On that first tick only 40% of the needed separation is
// actually applied -- e.g. a target dy of 22px (a typical bubble height)
// only moves 8.8px, which is not enough to clear the probe's 15%-of-
// smaller-rect overlap threshold, so the pair stays visibly overlapping
// on-screen for 1-2 more ticks (100-200ms) until the lerp converges.
// Evidence this is the mechanism, not a resolver bug or a scale/back-calc
// error: every overlap in the probe run is a single- or double-tick
// transient (run lengths [1,2,1,1,1,1] across 120 ticks, never a sustained
// run) and every one lines up with a tick where the label's natural
// position jumped 400+ CSS px between samples (the scene's own opening
// camera flythrough) -- exactly the "went from clear to colliding in one
// tick" case this smoothing under-applies for. Measured label width was
// stable to +/-0.04px across all 120 ticks, ruling out an ancestor-scale
// back-calculation error as the driver (that would show up as width churn
// correlated with the overlap ticks; it doesn't).
//
// Fix: smoothLabelOffset (below) snaps straight to the full target on a
// label's first nudging tick (previous applied offset ~0, new target
// non-zero) instead of lerping from zero -- eliminates the under-applied-
// offset window entirely for brand-new collisions. Once a label already
// carries a non-zero offset, smoothing still applies exactly as before (an
// already-nudged label's target drifting a little, e.g. a neighbor walking,
// still lerps instead of snapping) -- this preserves the ORIGINAL reason
// smoothing exists (never snap an already-placed stack for a 1px jitter),
// it only removes the lag on the transition INTO a collision.
const SMOOTH_SNAP_EPSILON_PX = 0.5;

export interface SmoothedOffset {
  dx: number;
  dy: number;
}

/**
 * Blends a label's previously-applied screen-space offset toward this
 * tick's resolved target. Pure function -- see this file's own
 * "COLD-START SNAP FIX" note above for why a brand-new collision (no prior
 * offset) snaps straight to `targetDx/targetDy` instead of lerping by
 * `smoothFactor` like every subsequent tick does.
 */
export function smoothLabelOffset(
  prevDx: number,
  prevDy: number,
  targetDx: number,
  targetDy: number,
  smoothFactor: number,
): SmoothedOffset {
  const hadPriorOffset = Math.abs(prevDx) > SMOOTH_SNAP_EPSILON_PX || Math.abs(prevDy) > SMOOTH_SNAP_EPSILON_PX;
  const needsOffset = Math.abs(targetDx) > SMOOTH_SNAP_EPSILON_PX || Math.abs(targetDy) > SMOOTH_SNAP_EPSILON_PX;
  const factor = !hadPriorOffset && needsOffset ? 1 : smoothFactor;
  return {
    dx: prevDx + (targetDx - prevDx) * factor,
    dy: prevDy + (targetDy - prevDy) * factor,
  };
}

// NEVER-LERP-INTO-OVERLAP FIX (DECLUTTER v2, 2026-09-15, real-GPU probe
// evidence: samples file 20260915T092455Z-ryajHEnIzll03dXEfn-AQ.samples
// .json.gz, 580 ticks / 290s with the cold-start-snap fix already deployed
// -- 12dd177a/build ryajHEnIzll03dXEfn-AQ). label_overlap was STILL FAIL at
// 63/580 ticks (10.9%), but the shape changed from v1: overlaps are no
// longer confined to the intro flythrough -- they're isolated single-tick
// blips spread across the whole run (Chef/Treasurer alone: 19/580 ticks,
// at ticks 4, 9, 112, 266, 297, 327, 348, 377, ...). Chef's own screen
// position keeps drifting 100+ px over tens of seconds even mid-run (e.g.
// t=62.8s (559.8,542.7) -> t=63.3s (580.5,513.7), a ~35px single-tick
// move) -- the OVERVIEW CAMERA never stops moving, so a label that already
// carries a non-zero offset (past the v1 cold-start-snap fix, which only
// covers the FIRST nudging tick) keeps re-targeting every tick as the
// camera drifts, and `smoothLabelOffset`'s SMOOTH_FACTOR=0.4 lerp lags
// that continuously-moving target by ~1-3 ticks -- during which the
// PARTIALLY-applied offset can itself sit inside a neighbor's rect even
// though the FULLY-resolved target (which the resolver already proved
// collision-free against every other label this tick) would not.
//
// Fix: never let the lerped (smoothed) candidate leave a label inside a
// collision that the resolver's own target already avoids. Per label per
// tick: if the smoothed candidate's rect overlaps ANY other label's
// target-resolved rect this tick AND the raw target rect does not, skip
// the lerp and snap straight to the target (same escape hatch the v1
// cold-start fix already uses, just gated on a different condition).
// Otherwise lerp exactly as `smoothLabelOffset` already does -- this
// keeps the "don't snap the whole stack for a 1px jitter" behavior for
// every tick where lagging behind the target was never actually visible.
export interface OverlapRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

/**
 * `smoothLabelOffset` plus one more guard: if the ordinary lerped
 * (smoothed) candidate would overlap any rect in `otherRects` while the
 * raw resolver `targetDx/targetDy` would not, returns the target directly
 * instead of the lerped value. `otherRects` should be every OTHER label's
 * natural rect already shifted by ITS OWN resolved target offset for this
 * tick (i.e. where the resolver has already proven every label ends up
 * with zero mutual overlap) -- see this file's own "NEVER-LERP-INTO-
 * OVERLAP FIX" note above for why that's the right collision surface to
 * test the lerped candidate against, and `LabelDeclutterManager.tsx`'s own
 * call site for how that array is built once per tick from
 * `resolveLabelOffsets`'s output. Pure function -- zero DOM/React/three.js,
 * unit-testable in plain `node --test` exactly like `smoothLabelOffset`.
 */
export function smoothLabelOffsetAvoidingOverlap(
  rect: OverlapRect,
  prevDx: number,
  prevDy: number,
  targetDx: number,
  targetDy: number,
  smoothFactor: number,
  otherRects: readonly OverlapRect[],
): SmoothedOffset {
  const lerped = smoothLabelOffset(prevDx, prevDy, targetDx, targetDy, smoothFactor);

  const overlapsAny = (dx: number, dy: number): boolean =>
    otherRects.some((o) =>
      rectsOverlap(rect.x + dx, rect.y + dy, rect.width, rect.height, o.x, o.y, o.width, o.height),
    );

  if (overlapsAny(lerped.dx, lerped.dy) && !overlapsAny(targetDx, targetDy)) {
    return { dx: targetDx, dy: targetDy };
  }
  return lerped;
}

export function rectsOverlap(
  ax: number, ay: number, aw: number, ah: number,
  bx: number, by: number, bw: number, bh: number,
): boolean {
  return ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by;
}

interface PlacedLabel {
  rect: LabelRect;
  dx: number;
  dy: number;
  /** True only for a placed entry seeded from an `ObstacleRect` whose own
   * `isScreen` was set -- see `ObstacleRect.isScreen`'s own comment for why
   * this makes resolveLabelOffsets fade a still-colliding label fully to 0
   * rather than the generic `fadeOpacity`. False for every real label and
   * every non-screen (HUD) obstacle. */
  isScreenObstacle?: boolean;
}

function overlapsAnyPlaced(
  rect: LabelRect, dx: number, dy: number, placed: readonly PlacedLabel[],
): boolean {
  return placed.some((p) =>
    rectsOverlap(
      rect.x + dx, rect.y + dy, rect.width, rect.height,
      p.rect.x + p.dx, p.rect.y + p.dy, p.rect.width, p.rect.height,
    ),
  );
}

/** Walks ONE axis in fixed `NUDGE_STEP_PX` increments until `rect` (nudged
 * by the growing offset on that axis alone) no longer overlaps any placed
 * label, or the cap is hit. Returns the offset reached and whether it
 * actually cleared every collision. */
function resolveAxis(
  rect: LabelRect, placed: readonly PlacedLabel[], axis: "x" | "y", maxNudgePx: number,
): { value: number; cleared: boolean } {
  let d = 0;
  const collides = (dd: number) =>
    axis === "x" ? overlapsAnyPlaced(rect, dd, 0, placed) : overlapsAnyPlaced(rect, 0, dd, placed);
  while (d < maxNudgePx && collides(d)) d += NUDGE_STEP_PX;
  const finalD = Math.min(d, maxNudgePx);
  return { value: finalD, cleared: !collides(finalD) };
}

/**
 * Resolves overlaps for one frame's worth of label rects. Pure: same input
 * always produces the same output (see this file's own header for why that
 * determinism is exactly what keeps a label's position stable across
 * frames rather than jittering). O(n^2) in the label count -- this scene's
 * own roster caps at roughly 20 simultaneous labels (8 lanes + 6 personas +
 * up to 8 live agents + 1 plaque + 1 Gamma, rarely all visible/overlapping
 * at once), trivial at that size, called at most 10x/s (see
 * useLabelDeclutter.ts's own throttle).
 *
 * `obstacles` (2026-09-15, HUD-OBSTACLE pass): fixed DOM rects seeded into
 * `placed` BEFORE any real label, at max precedence -- a label overlapping
 * one is nudged away exactly like it would be for a higher-priority label,
 * on whichever axis clears cheaper, and fades past `maxNudgePx` same as
 * any other capped label. Obstacles are never added to `out` (nothing to
 * offset) and never appear in `placed` for a later label to "keep its
 * place" against -- they simply always win a collision.
 */
export function resolveLabelOffsets(
  rects: readonly LabelRect[],
  maxNudgePx: number = DEFAULT_MAX_NUDGE_PX,
  fadeOpacity: number = DEFAULT_FADE_OPACITY,
  obstacles: readonly ObstacleRect[] = [],
  legibilityFloorPx: number = MIN_LEGIBLE_PX,
): Map<string, LabelOffset> {
  const order = [...rects].sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority;
    if (a.distance !== b.distance) return a.distance - b.distance;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });

  const placed: PlacedLabel[] = obstacles.map((o) => ({
    rect: { id: o.id, priority: -1, distance: 0, x: o.x, y: o.y, width: o.width, height: o.height },
    dx: 0,
    dy: 0,
    isScreenObstacle: o.isScreen === true,
  }));
  const out = new Map<string, LabelOffset>();

  for (const rect of order) {
    if (!overlapsAnyPlaced(rect, 0, 0, placed)) {
      placed.push({ rect, dx: 0, dy: 0 });
      out.set(rect.id, { dx: 0, dy: 0, opacity: 1 });
      continue;
    }

    // LEGIBLE-LABELS fix (2026-09-16, see `LabelRect.mustStayLegible`'s own
    // header): an answer-bearing label gets its own much larger nudge
    // budget and a strict "vertical, then lateral" resolution order --
    // never the normal smaller-displacement axis race -- and is never
    // faded for failing to clear, even at that larger budget (best-effort
    // placement beats invisibility). Every other label keeps the exact
    // pre-existing algorithm below, byte-for-byte.
    let axis: "x" | "y";
    let chosen: { value: number; cleared: boolean };
    let dx: number;
    let dy: number;
    let opacity: number;

    if (rect.mustStayLegible) {
      const yTry = resolveAxis(rect, placed, "y", MUST_STAY_LEGIBLE_MAX_NUDGE_PX);
      if (yTry.cleared) {
        axis = "y";
        chosen = yTry;
      } else {
        const xTry = resolveAxis(rect, placed, "x", MUST_STAY_LEGIBLE_MAX_NUDGE_PX);
        if (xTry.cleared) {
          axis = "x";
          chosen = xTry;
        } else {
          // Neither axis fully cleared even at the larger budget -- take
          // whichever got closer (smaller residual overlap is still a
          // better outcome than the untried axis) and stay fully opaque
          // per this label's own "never fade" contract.
          axis = yTry.value <= xTry.value ? "y" : "x";
          chosen = axis === "y" ? yTry : xTry;
        }
      }
      dx = axis === "x" ? chosen.value : 0;
      dy = axis === "y" ? chosen.value : 0;
      opacity = 1;
      placed.push({ rect, dx, dy });
    } else {
      const yTry = resolveAxis(rect, placed, "y", maxNudgePx);
      const xTry = resolveAxis(rect, placed, "x", maxNudgePx);
      // Prefer whichever axis actually CLEARED the collision; between two
      // that both cleared (or neither did), take the smaller displacement --
      // ties go to Y (this file's own historical default, and the natural
      // read for a stack of bubbles above one head). See this file's own
      // header for why the axis choice matters for the real overview-camera
      // side-by-side case this fix targets.
      if (yTry.cleared && xTry.cleared) axis = yTry.value <= xTry.value ? "y" : "x";
      else if (yTry.cleared) axis = "y";
      else if (xTry.cleared) axis = "x";
      else axis = yTry.value <= xTry.value ? "y" : "x";

      chosen = axis === "y" ? yTry : xTry;
      dx = axis === "x" ? chosen.value : 0;
      dy = axis === "y" ? chosen.value : 0;
      placed.push({ rect, dx, dy });
      // SCREEN-KEEP-OUT HARDENING (see ObstacleRect.isScreen's own header):
      // a label that is STILL colliding with a screen specifically after the
      // capped nudge fades all the way to 0, never the generic fadeOpacity --
      // partial-opacity clutter sitting on a readable monitor face is still a
      // counted violation downstream (hq_probe_lib.py's opacity>=0.05 floor),
      // so "did its best" is not good enough for THIS obstacle kind. A label
      // that only failed to clear another LABEL, or a non-screen (HUD)
      // obstacle, keeps the original fadeOpacity behavior unchanged.
      opacity = 1;
      if (!chosen.cleared) {
        const stillOverlapsScreen = placed.some(
          (p) =>
            p.isScreenObstacle &&
            rectsOverlap(rect.x + dx, rect.y + dy, rect.width, rect.height, p.rect.x + p.dx, p.rect.y + p.dy, p.rect.width, p.rect.height),
        );
        opacity = stillOverlapsScreen ? 0 : fadeOpacity;
      }
    }
    out.set(rect.id, { dx, dy, opacity });
  }

  enforceGroupOrder(rects, out);

  // LEGIBILITY-FLOOR: applied last, unconditionally, over whatever the
  // collision pass above decided -- see this file's own MIN_LEGIBLE_PX
  // header. A label under the floor is unreadable regardless of whether it
  // collided with anything, so this always wins over a `1` collision-clear
  // opacity but never fights the fade-past-cap value (both express "don't
  // show this" the same way).
  if (legibilityFloorPx > 0) {
    for (const r of rects) {
      if (r.height < legibilityFloorPx) {
        const existing = out.get(r.id) ?? { dx: 0, dy: 0, opacity: 1 };
        out.set(r.id, { ...existing, opacity: 0 });
      }
    }
  }

  return out;
}

/** LEVEL-ORDER fix (2026-09-15) -- see `LabelRect.orderGroup`'s own comment
 * for the real-capture evidence this patches. Pure post-pass over the
 * collision resolver's own output: within each `orderGroup`, walks labels
 * ascending by `orderKey` and clamps each one's final screen-space top (`y +
 * dy`) to never sit above (i.e. never end up with a SMALLER y than) the
 * previous, lower-ranked label's own final BOTTOM (`y + dy + height`) -- a
 * monotonic floor, exactly mirroring how `resolveAxis` already only ever
 * pushes a label AWAY (never pulls one closer), so this never fights the
 * collision-avoidance nudges, only tops them up when the two passes would
 * otherwise disagree on order. Mutates nothing outside the group; a label
 * with no orderGroup/orderKey (or a NaN/undefined key) is left exactly as
 * the collision pass already set it.
 *
 * OCCLUSION fix (2026-09-15, real capture hq-final2.png, read at 1:1):
 * this pass used to floor on the previous label's final TOP, not its
 * BOTTOM -- "never end up ABOVE" was enforced, but "never end up
 * OVERLAPPING" was not. Two price plaques of different heights (the
 * compact ~24px level plaque vs. the taller ~40px `.hq-beam` last-close
 * plaque, both same x column) could legally satisfy the old floor
 * (finalY_lower >= finalY_higher) while their rects still intersected,
 * because the floor never accounted for the higher-ranked plaque's own
 * height -- exactly the capture: "757.38 · last close" landed with its
 * top AT (not below) "757.44 RESISTANCE"'s top, so the taller last-close
 * box covered the shorter level plaque's lower half ("757.4" was all that
 * remained readable). The existing unit tests only ever asserted
 * `finalY <= finalY` (order), never rect non-intersection, so this
 * shipped without a red test -- see the new
 * "never end up with intersecting final rects" test below, which does
 * assert non-intersection and would have caught it. */
function enforceGroupOrder(rects: readonly LabelRect[], out: Map<string, LabelOffset>): void {
  const groups = new Map<string, LabelRect[]>();
  for (const r of rects) {
    if (r.orderGroup === undefined || r.orderKey === undefined || !Number.isFinite(r.orderKey)) continue;
    const arr = groups.get(r.orderGroup);
    if (arr) arr.push(r);
    else groups.set(r.orderGroup, [r]);
  }
  for (const arr of groups.values()) {
    const ordered = [...arr].sort((a, b) => {
      if (a.orderKey !== b.orderKey) return (a.orderKey as number) - (b.orderKey as number);
      return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
    });
    let floor = -Infinity;
    for (const r of ordered) {
      const off = out.get(r.id) ?? { dx: 0, dy: 0, opacity: 1 };
      const finalY = r.y + off.dy;
      if (finalY < floor) {
        out.set(r.id, { ...off, dy: off.dy + (floor - finalY) });
        floor += r.height;
      } else {
        floor = finalY + r.height;
      }
    }
  }
}

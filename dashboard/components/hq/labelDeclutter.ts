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

function rectsOverlap(
  ax: number, ay: number, aw: number, ah: number,
  bx: number, by: number, bw: number, bh: number,
): boolean {
  return ax < bx + bw && ax + aw > bx && ay < by + bh && ay + ah > by;
}

interface PlacedLabel {
  rect: LabelRect;
  dx: number;
  dy: number;
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
  }));
  const out = new Map<string, LabelOffset>();

  for (const rect of order) {
    if (!overlapsAnyPlaced(rect, 0, 0, placed)) {
      placed.push({ rect, dx: 0, dy: 0 });
      out.set(rect.id, { dx: 0, dy: 0, opacity: 1 });
      continue;
    }

    const yTry = resolveAxis(rect, placed, "y", maxNudgePx);
    const xTry = resolveAxis(rect, placed, "x", maxNudgePx);
    // Prefer whichever axis actually CLEARED the collision; between two
    // that both cleared (or neither did), take the smaller displacement --
    // ties go to Y (this file's own historical default, and the natural
    // read for a stack of bubbles above one head). See this file's own
    // header for why the axis choice matters for the real overview-camera
    // side-by-side case this fix targets.
    let axis: "x" | "y";
    if (yTry.cleared && xTry.cleared) axis = yTry.value <= xTry.value ? "y" : "x";
    else if (yTry.cleared) axis = "y";
    else if (xTry.cleared) axis = "x";
    else axis = yTry.value <= xTry.value ? "y" : "x";

    const chosen = axis === "y" ? yTry : xTry;
    const dx = axis === "x" ? chosen.value : 0;
    const dy = axis === "y" ? chosen.value : 0;
    placed.push({ rect, dx, dy });
    out.set(rect.id, { dx, dy, opacity: chosen.cleared ? 1 : fadeOpacity });
  }

  return out;
}

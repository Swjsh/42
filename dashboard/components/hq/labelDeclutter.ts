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
// to frame, the "no jitter" requirement). Walk that order; each label is
// nudged straight down in fixed NUDGE_STEP_PX increments until its
// (offset) rect no longer overlaps any ALREADY-PLACED (higher-precedence)
// rect. Beyond `maxNudgePx` the offset clamps there and the label's own
// opacity drops to `fadeOpacity` instead of stacking forever (brief's own
// "beyond the cap, lower-priority labels fade" rule).

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

export interface LabelOffset {
  /** Vertical pixel nudge to apply on top of the label's own resting
   * screen position (positive = further down the screen). 0 for a label
   * that never collided with anything higher-precedence. */
  dy: number;
  /** 1 normally; drops to the caller's `fadeOpacity` once `dy` has been
   * clamped at `maxNudgePx` (this label is still colliding even at the cap,
   * so it fades instead of stacking further). */
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

/**
 * Resolves overlaps for one frame's worth of label rects. Pure: same input
 * always produces the same output (see this file's own header for why that
 * determinism is exactly what keeps a label's position stable across
 * frames rather than jittering). O(n^2) in the label count -- this scene's
 * own roster caps at roughly 20 simultaneous labels (8 lanes + 6 personas +
 * up to 8 live agents + 1 plaque + 1 Gamma, rarely all visible/overlapping
 * at once), trivial at that size, called at most 10x/s (see
 * useLabelDeclutter.ts's own throttle).
 */
export function resolveLabelOffsets(
  rects: readonly LabelRect[],
  maxNudgePx: number = DEFAULT_MAX_NUDGE_PX,
  fadeOpacity: number = DEFAULT_FADE_OPACITY,
): Map<string, LabelOffset> {
  const order = [...rects].sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority;
    if (a.distance !== b.distance) return a.distance - b.distance;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });

  const placed: { rect: LabelRect; dy: number }[] = [];
  const out = new Map<string, LabelOffset>();

  for (const rect of order) {
    let dy = 0;
    while (
      dy < maxNudgePx &&
      placed.some((p) =>
        rectsOverlap(
          rect.x, rect.y + dy, rect.width, rect.height,
          p.rect.x, p.rect.y + p.dy, p.rect.width, p.rect.height,
        ),
      )
    ) {
      dy += NUDGE_STEP_PX;
    }
    const clamped = dy >= maxNudgePx;
    const finalDy = Math.min(dy, maxNudgePx);
    placed.push({ rect, dy: finalDy });
    out.set(rect.id, { dy: finalDy, opacity: clamped ? fadeOpacity : 1 });
  }

  return out;
}

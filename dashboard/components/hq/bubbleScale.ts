// ---------------------------------------------------------------------------
// Head-bubble on-screen size policy (coordinator, 2026-09-14 20:1x ET). drei's
// `distanceFactor` scales an <Html> by 1/dist, so a bubble sized to read at
// the default overview turns into a banner inside the hub. This piecewise CSS
// counter-scale, applied to the wrapper div drei does not own, keeps the text
// between the far floor (~9.5 px on J's 2560x1440 at BUBBLE_FAR_REF_DISTANCE,
// measured on hq-20260914-1725.png) and twice that up close. Pure so it can be
// unit-tested and shared by Agent.tsx + GammaCharacter.tsx.
// ---------------------------------------------------------------------------
export const BUBBLE_FAR_REF_DISTANCE = 38;
export const BUBBLE_MAX_COUNTER_SCALE = 1.7;
export const BUBBLE_NEAR_HOLD_DISTANCE = 19;
export function bubbleCounterScale(dist: number): number {
  if (!Number.isFinite(dist) || dist <= 0) return 1;
  if (dist >= BUBBLE_FAR_REF_DISTANCE) return Math.min(BUBBLE_MAX_COUNTER_SCALE, dist / BUBBLE_FAR_REF_DISTANCE);
  if (dist >= BUBBLE_NEAR_HOLD_DISTANCE) return 1;
  return Math.max(0.12, dist / BUBBLE_NEAR_HOLD_DISTANCE);
}

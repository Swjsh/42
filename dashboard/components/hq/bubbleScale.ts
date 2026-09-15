// ---------------------------------------------------------------------------
// Head-bubble on-screen size policy (coordinator, 2026-09-14 20:1x ET). drei's
// `distanceFactor` scales an <Html> by objectScale(camera,dist)*distanceFactor,
// where objectScale (drei/web/Html.js's own FOV-based helper) is proportional
// to 1/dist -- so the raw on-screen size is ~ k(dist)/dist for this counter-
// scale k. A bubble sized to read at the default overview turns into a
// banner up close unless k grows to cancel that 1/dist term. This piecewise
// CSS counter-scale, applied to the wrapper div drei does not own, keeps the
// text between the far floor (~9.5 px on J's 2560x1440 at
// BUBBLE_FAR_REF_DISTANCE, measured on hq-20260914-1725.png) and twice that
// up close. Pure so it can be unit-tested and shared by Agent.tsx +
// GammaCharacter.tsx + LiveAgents.tsx.
//
// BUBBLE-FIX (2026-09-15, coordinator review item 3): the near branch used
// to be `Math.max(0.12, dist / BUBBLE_NEAR_HOLD_DISTANCE)` -- a hard floor
// at k=0.12. Below dist = NEAR_HOLD*0.12 = 2.28u that floor stops scaling
// with `dist`, so on-screen size ~ 0.12/dist grows WITHOUT BOUND as the
// camera keeps closing in (confirmed: drei's own objectScale really is
// ~1/dist, verified from node_modules/@react-three/drei/web/Html.js's own
// `scale = distanceFactor === undefined ? 1 : objectScale(...) * distanceFactor`
// line). Removing the floor and letting k = dist/NEAR_HOLD run all the way
// to dist->0 makes on-screen size ~ (dist/NEAR_HOLD)/dist = 1/NEAR_HOLD --
// CONSTANT for every dist in (0, NEAR_HOLD), i.e. the ~19px plateau now
// holds all the way to the camera touching the character, never growing
// into a banner.
//
// Item 4 (far cap) CONFIRMED, not just theoretical: Scene.tsx's own
// FREE_CAM_MAX_DISTANCE (camera-to-ORBIT-TARGET distance) is 58u, and
// layout.ts's own node geometry (HUB_WALL_RADIUS 7.5 + MAIN_HALL_LEN 9 +
// T_JUNCTION_HALF 0.9 = T_DIST 17.4; SIDE_SPAN = T_JUNCTION_HALF +
// SIDE_HALL_LEN(4.5) + BAY_HALF_DEPTH(2.7) = 8.1) puts every bay node --
// the ONLY live-agent zone far from the hub, and also every keyboard 1-7
// camera-fly-to target -- at radius sqrt(17.4^2+8.1^2) ~= 19.19u from the
// hub, with two diametrically opposite bays up to 2*19.19 ~= 38.39u apart.
// Worst realizable case: camera at its own max 58u from an orbit target
// sitting at one bay, looking straight through it at a live agent standing
// at the OPPOSITE bay -- camera-to-AGENT distance up to 58+38.39 ~= 96.4u,
// well past the OLD cap distance of FAR_REF*1.7 = 64.6u. Raised
// BUBBLE_MAX_COUNTER_SCALE to 2.6 (96.4/38 = 2.537, rounded up for margin)
// so the far plateau holds across the full realizable camera range instead
// of the bubble shrinking below its own floor past 64.6u.
// ---------------------------------------------------------------------------
export const BUBBLE_FAR_REF_DISTANCE = 38;
export const BUBBLE_MAX_COUNTER_SCALE = 2.6;
export const BUBBLE_NEAR_HOLD_DISTANCE = 19;
export function bubbleCounterScale(dist: number): number {
  if (!Number.isFinite(dist) || dist <= 0) return 1;
  if (dist >= BUBBLE_FAR_REF_DISTANCE) return Math.min(BUBBLE_MAX_COUNTER_SCALE, dist / BUBBLE_FAR_REF_DISTANCE);
  if (dist >= BUBBLE_NEAR_HOLD_DISTANCE) return 1;
  return dist / BUBBLE_NEAR_HOLD_DISTANCE;
}

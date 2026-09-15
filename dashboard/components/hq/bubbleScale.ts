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
// at the OPPOSITE bay -- camera-to-AGENT distance up to 58+38.39 ~= 96.4u.
// BUBBLE_MAX_COUNTER_SCALE must keep FAR_REF*scale >= 96.4 for whatever
// FAR_REF is chosen below (see the OVERVIEW-FLOOR fix immediately after).
//
// OVERVIEW-FLOOR FIX (2026-09-15, HQ declutter pass): the ~9.5px "far
// floor" this file claimed was NEVER actually pinned to a real pixel value
// -- it was just "whatever drei's native scale happens to be AT
// FAR_REF_DISTANCE", and nobody had solved that back out to real CSS
// pixels for the ACTUAL default overview camera. Read drei's own
// node_modules/@react-three/drei/web/Html.js#objectScale this session:
// non-transform-mode scale = distanceFactor / (2*tan(vFOV/2)*dist). Every
// hub-center label uses distanceFactor=9 (Agent.tsx/GammaCharacter.tsx/
// LiveAgents.tsx/BrainCore.tsx, unchanged); the ultra-tier default overview
// camera (Scene.tsx OVERVIEW_CAM_POS = CAMERA_DIST_ULTRA 45u +
// CAMERA_HEIGHT_ULTRA 31u, fov 50 from UltraCanvasRoot.tsx) sits
// sqrt(45^2+31^2) ~= 54.6u from the hub-center labels. Old FAR_REF=38 put
// the "far plateau" constant at distanceFactor/(2*tan(25deg)*38) ~= 0.254,
// i.e. a 24px persona/live-agent bubble (Agent.tsx/GammaCharacter.tsx/
// LiveAgents.tsx's own fontSize) rendered at ~24*0.254 ~= 6.1px on screen
// at ANY distance >= 38u including the 54.6u overview -- matching J's
// measured ~6px exactly. The "9.5px" in this file's own prior comment was
// never verified against this camera; it was aspirational, not enforced.
//
// FIX: halve both reference distances (38->20, 19->10, ratio held at
// exactly 2 -- the stated "near holds at twice the far floor" invariant is
// unchanged) so the far plateau's constant becomes
// distanceFactor/(2*tan(25deg)*20) ~= 0.482, giving a 24px label ~11.6px on
// screen at every distance >= 20u (the overview's 54.6u included) and a
// 34px plaque (BrainCore.tsx's PLAQUE_Y) ~16.4px -- both clear the >=11px
// floor this pass targets. BUBBLE_MAX_COUNTER_SCALE raised from 2.6 to 5.0
// so the cap distance (FAR_REF*scale = 20*5.0 = 100) still covers the same
// 96.4u worst case with margin (was 38*2.6=98.8 -- same coverage, just
// re-based on the new FAR_REF). The close-camera preset (`?cam=13,10,13`,
// ~20.3u from the hub) sits almost exactly AT the new FAR_REF boundary,
// where the far branch's frozen value and the mid-zone's natural value
// agree by construction (continuous at dist=FAR_REF) -- so close-camera
// on-screen size is unchanged (~11.1px before, ~11.6px after: a <0.5px
// difference from sitting a hair inside the (now closer) far branch
// instead of the mid branch, not a visible regression).
// ---------------------------------------------------------------------------
export const BUBBLE_FAR_REF_DISTANCE = 20;
export const BUBBLE_MAX_COUNTER_SCALE = 5.0;
export const BUBBLE_NEAR_HOLD_DISTANCE = 10;
export function bubbleCounterScale(dist: number): number {
  if (!Number.isFinite(dist) || dist <= 0) return 1;
  if (dist >= BUBBLE_FAR_REF_DISTANCE) return Math.min(BUBBLE_MAX_COUNTER_SCALE, dist / BUBBLE_FAR_REF_DISTANCE);
  if (dist >= BUBBLE_NEAR_HOLD_DISTANCE) return 1;
  return dist / BUBBLE_NEAR_HOLD_DISTANCE;
}

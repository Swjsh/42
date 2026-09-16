"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { useThrottledFrame } from "./useThrottledFrame";
import { isRegularTradingHours, makeMatcapTexture, nowEtDayOfWeek, nowEtMinutes, seededRandom, truncateOneLine } from "./palette";
import { ALERT_PACE_SPEED, CLIP_TABLE, IDLE_VARIANTS, KitAgentBody, NATIVE_WALK_CLIP_MPS, WALK_SPEED, WORKING_VARIANTS, clipCadenceRatio, type KitAnimState } from "./KitAgent";
import { CHARACTER_SCALE, CHARACTER_TARGET_HEIGHT } from "./SetKit";
import { recordAgentSample } from "@/lib/hq-motion-diag";
// MOTION-2 V2 (2026-09-14): type-only -- LAYOUT's own walk-graph contract
// (see that interface's own doc comment in types.ts). Never a value import
// (types.ts re-exports several other modules' types but no runtime code of
// its own), so this cannot create a circular runtime dependency.
import type { WalkPlan } from "./types";
// WALK-ROUTING pass (2026-09-15): same type-only + pure-function import
// discipline as the WalkPlan import above -- liveAgentWalk.ts is
// react/three-free (see that file's own header), so this cannot create a
// circular or SSR-unsafe dependency. `routeViaGraph` is the one new runtime
// import; `WalkGraph` is type-only (the prop's own declared type below).
import { routeViaGraph, type WalkGraph } from "./liveAgentWalk";
import { bubbleCounterScale } from "./bubbleText";
import { PRIORITY } from "./labelDeclutter";
import { mergeRefs, useLabelDeclutter } from "./useLabelDeclutter";
import HeadLabel from "./HeadLabel";
import { modelGlyph as computeModelGlyph } from "./headLabelModel";
import { useIsKiosk } from "./LiveAgents";

export type AgentBehavior = "working" | "idle" | "alert" | "frozen";
// MOTION-2 V2: "waypoints" added -- a walk driven by a real LAYOUT-supplied
// WalkPlan (N waypoints from the walk graph) instead of the legacy
// home<->single-point kinds below. Every existing kind keeps its EXACT
// current meaning/behavior -- see resolvePathPose's own comment for why
// routing them all through the same generalized path machinery is provably
// a no-op for a 2-point path.
export type AgentWalkKind = "roundtrip" | "arrival" | "allhands" | "purposeful" | "waypoints";
export type AgentPresenceMode = "greet" | "patrol";

interface AgentProps {
  laneSeed: string;
  home: [number, number, number];
  hub: [number, number, number];
  /** BLOCKY-FIXES pass (2026-09-16, Defect A): the seated character's own
   * desk-facing yaw, taken DIRECTLY from the desk's own furniture rotation
   * (layout.ts#PersonaWallSlot.rotationY / BaySlot.rotationY -- the SAME
   * value SetKit.tsx#DeskCluster already renders its table/chair/screen at,
   * see that component's own docstring). When given, this REPLACES the
   * `atan2(hub-home)+Math.PI` hub-approximation below outright (never
   * blended/averaged with it) -- that approximation only equals the desk's
   * true facing when `home` sits exactly on the ray from `hub` through the
   * wall/T-junction's own normal point, which breaks down hard for a
   * persona wall-slot desk (PERSONA_WALL_LATERAL_OFFSET=4.6 against
   * PERSONA_WALL_RADIUS=5.1 -- a lateral offset comparable to the radius
   * itself, not a small perturbation): numerically verified this pass (see
   * tests/hq-desk-facing.test.ts) that `atan2(hub-home)+PI` lands
   * 35-50deg off the desk's real `rotationY` for every one of today's 6
   * persona slots -- enough to put a room-side camera almost level with the
   * character's shoulder instead of squarely behind, which is what let
   * capture automation/state/station/captures/blockyfix-desk3-0135.png
   * show Coach's FACE (confirmed via the character GLB's own UV atlas: the
   * local +Z quad, both on `character-a.glb`'s head AND torso meshes, maps
   * to the face/collar texture region, never the plain-hood/backpack -Z
   * quad -- local +Z is this rig's true front, independent of any
   * hub-relative reasoning) from a camera meant to stand behind him.
   * `rotationY` is exact BY CONSTRUCTION (DeskCluster's own table/chair/
   * screen are rendered at this exact yaw -- see SetKit.tsx), so passing it
   * here makes the seated character's front axis land on EXACTLY the same
   * world direction as the screen it's meant to be looking at, with zero
   * hub-geometry approximation. Omitted (bay/lane agents, unchanged) keeps
   * today's already-screenshot-verified hub-based formula -- this prop is
   * additive, never a behavior change for any caller that doesn't pass it. */
  deskYaw?: number;
  behavior: AgentBehavior;
  accentColor: string;
  reducedMotion: boolean;
  /** Changing this value queues exactly ONE walk (see WalkKind below). The
   * first value ever seen (mount) SEEDS silently -- matching the
   * seen-id-diff convention Courier.tsx/HandoffCourier.tsx already use --
   * so a page load never fires a burst of walks. Pass the raw data value
   * that identifies the triggering event (e.g. a persona's own
   * lastFireISO) -- the parent never needs to hand-roll its own diffing. */
  walkEventKey?: string | null;
  /** "roundtrip" = home -> a fixed side-approach point near the hub -> home
   * (used when a walk is a brief errand); "arrival" = hub -> home, once,
   * ending in "working" (a persona that just fired walking in from the
   * manager and sitting down); "allhands" = home -> ring around the core
   * (idle clip, facing the core) for ALLHANDS_HUB_PAUSE seconds -> home,
   * queued only via `allHandsEventKey` below, never via `walkKind` itself
   * (that prop stays each persona's OWN individual-arrival kind; the two
   * trigger channels are independent so one persona firing doesn't get
   * mistaken for a company-wide event or vice versa). Default "roundtrip". */
  walkKind?: AgentWalkKind;
  /** Company Mode all-hands event (Pass B, 2026-09-13): pass
   * `data.brief.mtime_ms` here (personas only -- lane Agents omit this) --
   * a genuine change after mount queues exactly ONE "allhands" walk,
   * independent of `walkEventKey`/`walkKind` above (that pair keeps
   * driving each persona's own lastFireISO-triggered arrival walk
   * unaffected). Same seen-value-diff seeding convention as every other
   * event trigger in this file. */
  allHandsEventKey?: string | null;
  /** Item 2b (LIVE-1, 2026-09-14): pass palette.ts#computePurposefulWalk's
   * own `bucketKey` here (personas only) -- a THIRD independent seen-value-
   * diff channel (never confused with `walkEventKey`'s arrival trigger or
   * `allHandsEventKey`'s company-wide trigger), changing exactly once per
   * this persona's own 6-10min period. Always queues kind "purposeful"
   * (see `purposefulTarget` below for the destination). */
  purposefulWalkEventKey?: string | null;
  /** Item 2c (LIVE-1, 2026-09-14): Pilot-only "stands and points at the
   * wall screen" on a genuine ENTER/EXIT decision -- a value change (same
   * seen-value-diff convention as every other trigger in this file) holds
   * `animState` at "thinking" (the closest real clip to pointing) for
   * POINT_HOLD_S seconds, then releases back to the normal behavior-driven
   * pose automatically. Every caller except Pilot's own persona Agent
   * omits this, zero behavior change. */
  pointEventKey?: string | null;
  /** Item 2b (LIVE-1, 2026-09-14): the real world point a "purposeful"
   * walk (see palette.ts#computePurposefulWalk) walks to -- ideas wall /
   * core / a neighbor's desk / a hub lounge spot, all computed by Scene.tsx
   * from real data. Read ONLY at the instant a queued "purposeful" walk
   * actually starts (captured into a ref, same as `activeWalkKind` below)
   * so a mid-walk prop change (the parent recomputing on a later poll)
   * never yanks the destination out from under an agent already walking
   * there. Omitted by every non-purposeful caller. */
  purposefulTarget?: [number, number, number] | null;
  /** INTERACT-2 (I2, 2026-09-14): "walk to persona X" for a NAMED real event
   * -- a crew-events.jsonl row (Chef verdict / Coach sectors|task_health),
   * Scout's own mtime, a new Analyst/Treasurer file, or the day's first
   * post-close core-decision (see Scene.tsx's own eventWalk derivation for
   * each). A FOURTH independent seen-value-diff channel, never confused with
   * `purposefulWalkEventKey`'s own 6-10min rotation -- reuses that SAME
   * "purposeful" phase machinery (toHub/atHub-facing-target/toHome, the
   * PURPOSEFUL_PAUSE dwell) rather than inventing a new walk kind, since the
   * only real difference is WHICH real event chose the destination. If both
   * channels change in the exact same render, this effect (declared after
   * the purposeful one) wins the shared `pendingWalk` slot -- the same rare,
   * low-stakes collision this file's other multi-channel triggers already
   * accept, now favoring the more specific named event. */
  eventWalkEventKey?: string | null;
  /** The real world point `eventWalkEventKey`'s walk goes to (Gamma's desk
   * area, Pilot's desk, Chef's desk, ...) -- same snapshot-at-walk-start
   * discipline as `purposefulTarget`. Falls back to `approach` if a caller
   * somehow queues the key with no target (defensive; Scene.tsx always
   * pairs the two). */
  eventWalkTarget?: [number, number, number] | null;
  /** MOTION-2 V2 (2026-09-14): a FIFTH independent seen-value-diff trigger
   * channel, same convention as the four above -- a genuine change queues
   * kind "waypoints" (see `walkPlan` below for the payload). Until LAYOUT's
   * scene-side producer passes this, no caller sets it and this component's
   * behavior is byte-identical to today. */
  walkPlanKey?: string | null;
  /** MOTION-2 V2: the WalkPlan a queued "waypoints" walk follows -- read
   * live (not snapshotted early) at the instant the walk actually starts,
   * same discipline as `eventWalkTarget` above. See types.ts#WalkPlan's own
   * doc comment for the field contract. */
  walkPlan?: WalkPlan | null;
  /** J 2026-09-13 ("nearest agent turns to the viewer / night-patrol dim"
   * on presence flipping): "greet" holds the resting-state facing at
   * `facingYaw` instead of the idle look-around; "patrol" dims the visor.
   * Only ever set on ONE statically-chosen agent (Scene.tsx picks the lane
   * nearest the fixed camera) -- undefined everywhere else, zero cost. */
  presenceMode?: AgentPresenceMode;
  facingYaw?: number;
  /** Pass C schedule state (2026-09-13): 0..1, same visual lever as
   * presenceMode="patrol"'s 0.35 (head-beacon/visor dim) -- the lower of
   * the two ever applies (Math.min), so an off-shift AND night-patrolling
   * agent doesn't double-dim into invisibility. Callers only ever pass a
   * value below 1 when the persona is BOTH outside its own schedule window
   * AND not currently showing real activity (behavior !== "working") --
   * see Scene.tsx's own comment on why real data must never be visually
   * contradicted by a schedule assumption. Default 1 (every lane Agent
   * omits this -- schedules are a persona-only concept). */
  scheduleDim?: number;
  /** Ultra tier only (HQ kit rebuild, 2026-09-13): renders a real rigged
   * Kenney Mini Character (KitAgent.tsx) instead of the procedural
   * capsule/visor body below. Every position/walk-phase computation in this
   * file is UNCHANGED and tier-agnostic -- only the returned body JSX
   * branches. Defaults false (TV tier keeps the existing cheap body,
   * unchanged -- see StationModule.tsx's identical tier-branch reasoning:
   * real GLB meshes would blow the Mali-G31's draw-call budget). */
  ultra?: boolean;
  /** PEOPLE pass (2026-09-14, J: "little bubbles above their heads of the
   * action they are doing"): one-line ACTION text (never prefixed with the
   * name -- this component's own bubble JSX bolds `laneSeed` itself) for
   * when this agent is NOT mid-walk -- the caller derives this from real
   * evidence via bubbleText.ts (persona pill / lane state+evidence), the
   * SAME two sources Hud.tsx's roster panel already reads. Null/undefined
   * renders no bubble at all (never a fabricated placeholder) -- see
   * ActivityBubbleLayer.tsx's now-deleted identical convention. */
  bubbleText?: string | null;
  /** PEOPLE pass: the reason text for the ROTATIONAL 6-10min "purposeful"
   * walk (palette.ts#computePurposefulWalk) -- read LIVE at the instant the
   * walk starts, same snapshot discipline as `purposefulTarget`. Ignored
   * unless THIS channel (not `eventWalkReason` below) is what actually
   * queued the walk -- see `eventWalkPending` for the same
   * target/purpose-selecting split this file already uses. */
  purposefulReason?: string;
  /** PEOPLE pass: the reason text for a NAMED eventWalk (the hub-exchange
   * visitor's own real crew-event line, or one of the 4 other named-event
   * walks) -- read LIVE at the instant the walk starts, same snapshot
   * discipline as `eventWalkTarget`. Every OTHER walk kind has one true,
   * invariant reason this component supplies itself ("arrival" -> "back to
   * the desk", "allhands" -> "all-hands at the core", "waypoints" -> the
   * plan's own `purpose` field) and ignores both purpose props entirely. */
  eventWalkReason?: string;
  /** PEOPLE pass: company-audit verdict letter chip (personas only) --
   * mirrors PersonaModule.tsx's now-deleted badge (`audit.verdict[0]`,
   * PASS/WARN/FAIL colored via auditVerdictColor). Undefined renders no
   * chip (a lane agent, or a persona /api/hq predates the audit for). */
  auditVerdict?: string;
  /** HEAD-LABELS pass (2026-09-15): the model-tier glyph char shown after
   * this agent's name (headLabelModel.ts#modelGlyph's `.glyph`) -- Scene.tsx
   * computes this per call site (gear for every lane/bay agent, the real
   * classified runtime for a persona via `data.runtime.roles`). Undefined
   * falls back to modelGlyph("none")'s "?" -- never a guessed tier. */
  modelGlyph?: string;
  /** Hover title for `modelGlyph` -- the literal evidence string
   * (modelGlyph's `.title`), never invented copy. */
  modelGlyphTitle?: string;
  /** DECLUTTER pass (2026-09-14): which precedence tier this agent's own
   * head bubble registers at with the shared screen-space declutter system
   * (labelDeclutter.ts's own PRIORITY -- "persona bubbles > lane labels" per
   * the brief). Scene.tsx passes PRIORITY.PERSONA for the 6 hub personas;
   * every lane/bay caller omits this and gets the default (PRIORITY.LANE),
   * matching this component's own dual persona/lane use (see this file's
   * own header). */
  bubblePriority?: number;
  /** WALK-ROUTING pass (2026-09-15, J: an alert lane agent was seen "running
   * from the middle straight to its cube through walls, no walkway, no
   * doors"): the walk graph (Scene.tsx's own `walkGraph`, built once via
   * layout.ts#buildWalkGraph -- the SAME graph LiveAgents.tsx already
   * trusts) -- when provided, every walk this component queues (the legacy
   * 2-point roundtrip/allhands/purposeful/eventWalk kinds, AND the one-way
   * "arriving" hub->home leg) is routed THROUGH it via
   * liveAgentWalk.ts#routeViaGraph instead of a raw straight line, so no
   * walk can cut through a wall the graph itself routes around doors/
   * hallways for. Omitted (undefined) preserves the exact old straight-line
   * behavior -- every caller that has not been updated yet (there should be
   * none after this pass, but the fallback costs nothing) keeps working
   * unchanged. */
  walkGraph?: WalkGraph;
  /** WALK-ROUTING pass: overrides the `alert` behavior's own pace point
   * (see that branch below). The OLD formula paced along the straight
   * home->hub line, 40% of the way (capped 3.4u) -- correct only for a
   * persona pacing inside the open hub interior, but WRONG for a lane bay
   * agent, whose real "step outside and pace by the door" point is the
   * bay's own doorWorldPos (layout.ts#computeBaySlot), which sits along the
   * bay's SIDE-HALLWAY axis, not the home->hub diagonal -- pacing toward
   * the hub center from a bay desk walks straight through that bay's own
   * side wall (the exact bug reported live: "Futures is running... through
   * walls"). Scene.tsx passes `slot.doorWorldPos` for every bay agent;
   * persona agents (already hub-interior, home->hub line never crosses a
   * wall) omit this and keep the original formula. */
  alertPacePoint?: [number, number, number];
}

const HUB_PAUSE = 1.5;
// INTERACT-2 (I3, 2026-09-14): 60 -> 25s -- "everyone turns toward the hub
// wall for ~25s" (spec). BrainCore.tsx's own all-hands pulse window is a
// SEPARATE constant (not owned by this file); this only shortens how long
// each persona's own Agent body stands at the core facing it.
const ALLHANDS_HUB_PAUSE = 25;
const POINT_HOLD_S = 7; // item 2c (LIVE-1): how long Pilot holds the "point" gesture after a fresh ENTER/EXIT
const PURPOSEFUL_PAUSE = 4; // item 2b (LIVE-1): dwell at the destination -- long enough for the reason bubble/ticker line to read
// World-2 MOTION-FIX (2026-09-14, J: "the people are running like 100mph"):
// WALK_DURATION (a fixed 4.5s for EVERY walk regardless of distance -- a
// ~14-unit hub trip at 4.5s is ~3 u/s, a sprint for this character's own
// on-screen height) is GONE -- replaced by distance/WALK_SPEED (imported
// from KitAgent.tsx, the single source of truth also driving that file's own
// ultra-tier clip-speed derivation; see its comment for the real-world-pace
// math). MIN_WALK_LEG_S is a defensive floor only (a degenerate near-zero
// distance would otherwise read as a snap) -- real hub/approach distances
// are always well above it. WALK_EASE_S is the ease-in/ease-out window at
// each end of a leg (see easedWalkProgress below) -- a FIXED real-time
// window regardless of total leg duration, so a short errand's ease never
// swallows its whole walk.
const MIN_WALK_LEG_S = 0.8;
// MOTION-2 (2026-09-14, J: "cut it in half speed-wise"): 0.3 -> 0.4 -- a
// slower cruise speed (see KitAgent.tsx#WALK_SPEED) reads best with a
// proportionally slightly longer ease window at each end, so leaving/
// arriving at rest never feels like it snaps into the (now slower) cruise
// speed instantly.
const WALK_EASE_S = 0.4;
// MOTION-2: TV-tier procedural capsule-body leg-swing base rate, tuned at
// NATIVE_WALK_CLIP_MPS (1.4 u/s, KitAgent.tsx's own reference pace) --
// scaled by the SAME clipCadenceRatio formula that file's CLIP_TABLE uses
// for the rigged ultra-tier clips (see that function's own comment): a pure
// linear scale-down with WALK_SPEED/ALERT_PACE_SPEED would read as this
// body's legs swinging in slow motion at the new slower speeds, the exact
// bug clipCadenceRatio exists to avoid -- one shared mental model for "how
// fast should limbs move at this translation speed" across both tiers.
const NATIVE_SWING_HZ = 8;
// World-2 item 5 (2026-09-14, J: "futures is running because it's on alert...
// it's just running in place, which is weird"): a real pace between the desk
// and the hub-facing door -- see the `behavior === "alert"` branch's own
// comment for the full distance/speed derivation. ALERT_PACE_SPEED now lives
// in / derives from KitAgent.tsx (see its own comment) -- imported above,
// not redefined here, so this file's translation speed and that file's
// clip-speed multiplier can never drift apart.
const ALERT_PACE_PAUSE_S = 2.5; // was 1.5 -- a real pause, not a tap-and-go
// MOTION-2 V2: "smooth turn at each corner (yaw slerp over ~0.25s, no
// snapping)" (spec) -- see resolvePathPose's own comment for the mechanism.
const CORNER_TURN_S = 0.25;
// MOTION-2 V3 (J: "a little bit of LOGIC to their movement" -- never a
// fire-drill look): the last SECONDS the dwell of a "waypoints" walk holds
// before departing -- see the atHub branch's own nod logic below.
const DWELL_NOD_S = 1;
// MOTION-2 V3: no two agents start a walk within this many seconds of each
// other -- see `lastGlobalWalkStartT` below for the mechanism.
const WALK_START_STAGGER_S = 4;
// PEOPLE pass (P2, 2026-09-14): bubble geometry/behavior constants.
// ULTRA_HEAD_Y is DERIVED from SetKit.tsx's own exported constants (never a
// second hardcoded magic number) -- it reproduces KitAgent.tsx's own
// head-beacon math (`CHARACTER_RAW_HEIGHT[bodyId] * 0.95`, then scaled by
// `characterScale(bodyId)`) which is body-INDEPENDENT once simplified:
// `raw * 0.95 * (TARGET*SCALE/raw)` cancels `raw` entirely, leaving
// `0.95 * TARGET * SCALE` for every one of the 3 bundled bodies. TV_HEAD_Y is
// a plain tuned constant (the procedural capsule body has no SetKit
// height/scale system at all -- its visor sits at a hand-placed y=0.78,
// radius 0.1).
const ULTRA_HEAD_Y = CHARACTER_TARGET_HEIGHT * CHARACTER_SCALE * 0.95;
const TV_HEAD_Y = 0.9;
const BUBBLE_HEAD_GAP = 0.3;
// Brief's own "max ~36 chars" LITTLE-bubble budget applies to the WHOLE
// rendered line (bold name + " · " + action) -- this is the action's own
// share of that budget, sized so even the longest persona name on the
// roster ("Treasurer", 9 chars) plus the separator still fits comfortably.
const BUBBLE_ACTION_MAX_CHARS = 26;
// Beyond this camera distance a bubble fades to opacity 0 (never unmounts --
// see updateBubbleFade below) so a wide overview never turns into a text
// cloud, matching the brief's own "nearest bubbles always readable" rule.
const BUBBLE_FADE_DISTANCE = 80;
// Coordinator fix (2026-09-14 19:5x ET, read off ux1-reframe-default.png at
// 1:1): UX-1's overview re-frame moved the default camera to ~45-58 u, past
// the old 42 u fade, so EVERY head bubble vanished at the view J lands on --
// the fade is now 80 u, and below the reference distance where 24 px text
// measured ~9-10 px on J's 2560x1440 (the 19:26 ET frame, camera ~38 u) the
// bubble keeps drei's distanceFactor scaling, while beyond it a CSS
// counter-scale of dist/38 (capped) holds the text at that readable floor
// instead of letting it shrink into a dot. Transform-only, per the TV
// compositor rule; applied to the wrapper drei does not own.
// Size policy constants + bubbleCounterScale live in bubbleText.ts (shared with GammaCharacter).
type WalkPhase = "resting" | "toHub" | "atHub" | "toHome" | "arriving";
type AlertPacePhase = "toDoor" | "atDoor" | "toDesk" | "atDesk";

/** Trapezoidal-velocity walk progress: ramps up over `easeS` seconds,
 * cruises at constant speed, ramps down over `easeS` seconds at the far end
 * -- a FIXED real-time ease window regardless of total leg duration (unlike
 * a proportional smoothstep, whose ease would swallow a short leg's entire
 * duration). Integrated analytically so distance covered still sums to
 * exactly the full leg in `total` seconds -- WALK_SPEED stays the real
 * AVERAGE speed of the walk, not just its peak cruise speed. Pure function,
 * zero allocation, called from the per-frame throttled callback below. */
function easedWalkProgress(elapsed: number, total: number, easeS: number): number {
  if (total <= 0 || elapsed >= total) return 1;
  if (elapsed <= 0) return 0;
  const e = Math.min(easeS, total / 2); // never let the two ease windows overlap on a very short leg
  const v = 1 / (total - e); // cruise "speed" in progress-units/second
  if (elapsed <= e) return (v * elapsed * elapsed) / (2 * e);
  if (elapsed >= total - e) {
    const r = total - elapsed;
    return 1 - (v * r * r) / (2 * e);
  }
  return (v * e) / 2 + v * (elapsed - e);
}

/** Total distance along a multi-leg path (sum of consecutive-point
 * distances, XZ-plane only -- every walk in this file stays at one fixed Y).
 * Called once per walk-start (never per-frame), so its small per-call
 * allocation is a one-time cost, not a hot-path one. */
function pathTotalDistance(waypoints: [number, number, number][]): number {
  let total = 0;
  for (let i = 0; i < waypoints.length - 1; i++) {
    total += Math.hypot(waypoints[i + 1][0] - waypoints[i][0], waypoints[i + 1][2] - waypoints[i][2]);
  }
  return total;
}

/** Shortest-path angle interpolation -- equivalent to slerp for a single
 * Y-axis rotation (this file only ever rotates agents about Y). Wraps the
 * raw a->b difference into [-PI, PI] first so a corner near the +-PI seam
 * (e.g. 170deg -> -170deg) blends the SHORT way instead of spinning the long
 * way around. */
function slerpAngle(a: number, b: number, t: number): number {
  const twoPi = Math.PI * 2;
  const diff = (((b - a + Math.PI) % twoPi) + twoPi) % twoPi - Math.PI;
  return a + diff * t;
}

/** MOTION-2 V2 -- resolves (position, facing) at fractional distance-
 * progress `pathT` (0..1, ALREADY eased -- see easedWalkProgress) along a
 * multi-leg path, with a short yaw-slerp blend at each INTERIOR corner
 * (never at the path's own first leg, which has no previous heading to
 * blend from -- that leg keeps this file's existing "turn before moving"
 * behavior for free, since easedWalkProgress's own ramp-up keeps `pathT`
 * near 0, hence translation near-zero, for the first fraction of a second
 * regardless). Translation itself stays at CONSTANT speed along interior
 * legs (`pathT` maps linearly to distance-along-path except at the whole
 * path's own two ends, where easedWalkProgress supplies the ease) -- only
 * the FACING gets a corner transition, decoupled entirely from position, so
 * a walker's turn never shows up as a speed change.
 *
 * Provably a no-op for today's existing 2-point walks (roundtrip/allhands/
 * purposeful/eventWalk): with exactly one leg, the loop below always picks
 * legIndex 0, legLocalT reduces to exactly `pathT`, position reduces to
 * exactly `lerp(waypoints[0], waypoints[1], pathT)`, and the `legIndex > 0`
 * guard means the corner-slerp branch never runs -- byte-identical to the
 * single-leg math this replaced.
 *
 * Called from the throttled (20Hz) frame callback, same allocation class as
 * this file's existing per-tick temporaries (e.g. the alert-pace branch's
 * own `doorPos` literal) -- not the true per-rAF hot path.
 */
function resolvePathPose(
  waypoints: [number, number, number][],
  pathT: number,
  walkSpeed: number,
): { position: [number, number, number]; facing: number } {
  const legCount = waypoints.length - 1;
  if (legCount <= 0) return { position: waypoints[0] ?? [0, 0, 0], facing: 0 };
  const legDist: number[] = [];
  let total = 0;
  for (let i = 0; i < legCount; i++) {
    const d = Math.hypot(waypoints[i + 1][0] - waypoints[i][0], waypoints[i + 1][2] - waypoints[i][2]);
    legDist.push(d);
    total += d;
  }
  const targetDist = pathT * total;
  let cum = 0;
  let legIndex = legCount - 1; // default: last leg -- also correctly covers pathT>=1
  for (let i = 0; i < legCount; i++) {
    if (targetDist <= cum + legDist[i] || i === legCount - 1) { legIndex = i; break; }
    cum += legDist[i];
  }
  const d = legDist[legIndex];
  const legLocalT = d > 0 ? Math.min(1, Math.max(0, (targetDist - cum) / d)) : 1;
  const from = waypoints[legIndex];
  const to = waypoints[legIndex + 1];
  const position: [number, number, number] = [
    from[0] + (to[0] - from[0]) * legLocalT,
    from[1],
    from[2] + (to[2] - from[2]) * legLocalT,
  ];
  const legHeading = Math.atan2(to[0] - from[0], to[2] - from[2]);
  let facing = legHeading;
  if (legIndex > 0) {
    const legLocalDist = legLocalT * d;
    const turnBlendDist = Math.min(walkSpeed * CORNER_TURN_S, d);
    if (legLocalDist < turnBlendDist) {
      const prevFrom = waypoints[legIndex - 1];
      const prevHeading = Math.atan2(from[0] - prevFrom[0], from[2] - prevFrom[2]);
      const blend = turnBlendDist > 0 ? legLocalDist / turnBlendDist : 1;
      facing = slerpAngle(prevHeading, legHeading, blend);
    }
  }
  return { position, facing };
}

/** MOTION-2 V2 -- maps a WalkPlan's `dwellAnim` onto one of KitAgent.tsx's
 * EXISTING animation states (types.ts#WalkPlan's own doc comment: "which of
 * Agent.tsx's existing animation states to hold" -- no new clip names
 * invented). "interact" = arms on the desk/board (CLIP_TABLE's
 * interact-right clip); "point" = the SAME pose this file's own
 * `pointEventKey` mechanism already uses; "idle" = a slow look, not the
 * fully-neutral seated idle. */
function dwellAnimState(dwellAnim: WalkPlan["dwellAnim"]): KitAnimState {
  if (dwellAnim === "interact") return "resting-working-type";
  if (dwellAnim === "point") return "thinking";
  return "resting-idle-look";
}

// MOTION-2 V3 (J: "a little bit of LOGIC to their movement" -- the room
// should never look like a fire drill): MODULE scope, not component state --
// every mounted <Agent> instance (all 13+ lanes/personas) shares this ONE
// variable, so "no two agents start a walk within WALK_START_STAGGER_S of
// each other" holds ACROSS the whole room, not just within one agent's own
// walk history. A plain mutable number, updated imperatively from inside the
// throttled frame callback below -- zero allocation, and safe under JS's
// single-threaded execution (whichever instance's callback happens to run
// first in a given animation frame wins the read-then-write race
// deterministically, no lock needed). Starts at -Infinity so the very first
// walk any agent ever takes is never held up waiting for a "previous" walk
// that never happened.
let lastGlobalWalkStartT = -Infinity;

/**
 * One little procedural bot: capsule body, visor sphere (doubles as the
 * head-lamp -- emissive, no extra mesh needed), backpack box, two swinging
 * leg cylinders. Behavior state machine per the HQ-visuals brief: working
 * (bob + typing arms) / idle (slow breathing) / alert (paces its module, red
 * "!" overhead) / frozen (gaming mode -- no motion at all).
 *
 * Walks are EVENT-TRIGGERED only (J 2026-09-13: "it still needs a lot of
 * work to make it look real ... they need MEANING" -- the original design
 * had a working/idle agent walk to the hub and back on a random 20-60s
 * timer; deleted entirely). A parent passes `walkEventKey` (some real data
 * value -- a card id+status, a persona's lastFireISO) and this component
 * walks exactly once whenever that value genuinely changes after mount.
 * Breathing/idle look-around are NOT "random wander" in the sense J meant
 * (no timer, no destination) and stay as-is.
 */
export default function Agent({
  laneSeed, home, hub, deskYaw, behavior, accentColor, reducedMotion, walkEventKey, walkKind, allHandsEventKey, purposefulWalkEventKey, pointEventKey, purposefulTarget, eventWalkEventKey, eventWalkTarget, walkPlanKey, walkPlan, presenceMode, facingYaw,
  scheduleDim = 1,
  ultra = false,
  bubbleText, purposefulReason, eventWalkReason, auditVerdict,
  modelGlyph: modelGlyphChar, modelGlyphTitle,
  bubblePriority = PRIORITY.LANE,
  walkGraph, alertPacePoint,
}: AgentProps) {
  const group = useRef<THREE.Group>(null);
  const legL = useRef<THREE.Mesh>(null);
  const legR = useRef<THREE.Mesh>(null);
  const armL = useRef<THREE.Mesh>(null);
  const armR = useRef<THREE.Mesh>(null);
  const visorMat = useRef<THREE.MeshLambertMaterial>(null);

  // Coarse, DISCRETE walking/resting flag -- a plain useState (not a ref)
  // because it only needs to change a handful of times per walk (at the
  // exact phase transitions below), the same "state for discrete moments,
  // refs for continuous per-frame math" split BrainCore.tsx already uses for
  // its own `pulsing` flag. Ultra tier only consumes this (see `animState`
  // below); the TV tier's procedural body ignores it entirely.
  const [walking, setWalking] = useState(false);
  // Item 2a (LIVE-1, 2026-09-14): seated variety -- cycles among
  // IDLE_VARIANTS/WORKING_VARIANTS on its own per-instance 10-24s timer (see
  // the throttled callback below, MOTION-2 V3: was 8-20s -- "calmer
  // cadence"), instead of always showing the same "sit" clip. `useState`
  // (not a ref) because KitAgentBody's own clip crossfade is driven by
  // `animState` CHANGING as a REACT PROP -- a ref mutation alone would never
  // re-render KitAgentBody with the new value. Costs one extra re-render
  // every 10-24s per agent, the same "state for discrete moments" tradeoff
  // this file already makes for `walking` below.
  const [variantIdx, setVariantIdx] = useState(0);
  const nextVariantAt = useRef(0);
  const [pointing, setPointing] = useState(false);
  // World-2 item 5: mirrors `alertPhase.current`'s pause sub-phases into
  // React state, the SAME "a ref mutation alone would never re-render
  // KitAgentBody with the new value" reason `walking`/`variantIdx`/
  // `pointing` above are all useState rather than refs -- `alertPhase`
  // itself stays a ref (continuous per-frame position/rotation math), this
  // is only the discrete "which clip should ultra tier show" signal.
  const [alertPaused, setAlertPaused] = useState(false);
  // MOTION-2 V2: which KitAnimState a "waypoints" walk's dwell should hold
  // (see dwellAnimState) -- `useState` for the SAME "a ref mutation alone
  // never re-renders KitAgentBody" reason `walking`/`pointing`/`variantIdx`
  // above are all state, not refs. Declared here (not near the other V2
  // refs further down) because `animState` below reads it synchronously --
  // a `const` declared after that read would be a temporal-dead-zone error.
  const [dwelling, setDwelling] = useState<KitAnimState | null>(null);
  const pool = behavior === "working" ? WORKING_VARIANTS : IDLE_VARIANTS;
  const animState: KitAnimState =
    behavior === "alert" ? (alertPaused ? "alert-pause" : "alert")
    // MOTION-2 V2: `dwelling` (set only during a "waypoints" walk's atHub
    // phase, see dwellAnimState) outranks the generic walking/pointing/pool
    // states below -- a dwell has a SPECIFIC, plan-chosen pose to show.
    : dwelling ? dwelling
    : walking ? "walking" : pointing ? "thinking" : pool[variantIdx % pool.length];
  const patrolDim = Math.min(presenceMode === "patrol" ? 0.35 : 1, scheduleDim);

  const matcap = useMemo(() => makeMatcapTexture(), []);
  const rng = useMemo(() => seededRandom(laneSeed), [laneSeed]);
  // Radius 1.8->3.2 (Pass B, 2026-09-13): this point doubles as the
  // all-hands "ring around the core" stand now (ALLHANDS_HUB_PAUSE below) --
  // 1.8 sat INSIDE BrainCore's own ring geometry (~2.24 world radius after
  // its 1.15 group scale), which would have clipped through the core for a
  // 60s stand. 3.2 clears that with margin and stays well inside the
  // persona ring's own 6.5 radius. No live caller used the old "roundtrip"
  // brief-errand radius before this pass (lane agents don't walk; personas
  // only ever used "arrival", which never reads `approach` at all -- see
  // the "arriving" phase branch below), so this is a safe, unobserved
  // change, not a tuned value regressing something already shipped.
  const approach = useMemo(() => {
    const angle = rng() * Math.PI * 2;
    return [hub[0] + Math.cos(angle) * 3.2, home[1], hub[2] + Math.sin(angle) * 3.2] as [number, number, number];
  }, [rng, hub, home]);

  const phase = useRef<WalkPhase>("resting");
  const phaseStart = useRef(0);
  // World-2 MOTION-FIX, updated MOTION-2 V2: computed ONCE at walk-start
  // (see the pendingWalk consumption block below) -- toHub and toHome always
  // cover the SAME total path distance (the same waypoints, reversed -- see
  // `outboundPath`/`returnPath` below), and "arriving" is a single leg, so
  // one duration value covers whichever leg(s) a given walk actually plays.
  // WALK-ROUTING pass (2026-09-15): "arriving" now shares the SAME
  // outboundPath/resolvePathPose machinery as "toHub" (see the pendingWalk
  // consumption block below) instead of its own fixed-facing single lerp --
  // routed through `walkGraph` when provided, so a hub->home arrival can no
  // longer cut through a wall either. resolvePathPose's own "first leg has
  // no previous heading to blend from" behavior (see that function's own
  // comment) reproduces the exact old "turn before moving" feel for free:
  // facing snaps to the new leg's heading immediately, and
  // easedWalkProgress's ramp-up keeps actual translation near-zero for the
  // first fraction of a second regardless. The old `walkFacing` ref this
  // comment used to describe is gone -- there is no longer a second,
  // separate facing mechanism to keep in sync with resolvePathPose's.
  const walkLegDuration = useRef(MIN_WALK_LEG_S);
  // World-2 item 5: independent state machine for the alert pace (door <->
  // desk) -- separate from `phase` above (the roundtrip/arrival/allhands/
  // purposeful machine), never active at the same time since the alert
  // branch below returns early before reaching that other logic.
  // alertPhaseStart starts at -1 (a "never started" sentinel, distinct from
  // a legitimate elapsedTime of 0) so the FIRST frame this agent ever goes
  // alert seeds the clock from the current `t` instead of computing a
  // bogus elapsed time against a stale 0.
  const alertPhase = useRef<AlertPacePhase>("toDoor");
  const alertPhaseStart = useRef(-1);
  // Which AgentWalkKind is actually IN PROGRESS (set when a queued walk
  // starts, read by the atHub branch below to pick its pause duration/
  // facing/animState) -- distinct from the `walkKind` PROP, which for
  // personas is permanently "arrival" (their own individual trigger) even
  // while an "allhands" walk (a completely separate trigger) is what's
  // actually playing.
  const activeWalkKind = useRef<AgentWalkKind>("roundtrip");
  // Item 2b (LIVE-1): captured from the `purposefulTarget` PROP at the
  // instant a "purposeful" walk actually starts -- see that prop's own
  // comment for why this must be a snapshot, not a live read, of a value
  // that can change out from under a mid-walk agent otherwise.
  const activeTarget = useRef<[number, number, number] | null>(null);
  // MOTION-2 V2: the WalkPlan actually driving the CURRENT "waypoints" walk
  // (snapshotted at walk-start, same discipline as `activeTarget` above),
  // and the resolved outbound/return paths every kind now walks through
  // (see resolvePathPose) -- for the legacy 2-point kinds this is just
  // `[home, target]`/its reverse, computed at walk-start same as before.
  const activePlan = useRef<WalkPlan | null>(null);
  const outboundPath = useRef<[number, number, number][]>([home, home]);
  const returnPath = useRef<[number, number, number][]>([home, home]);
  // MOTION-2 V3: fires the end-of-dwell nod exactly once per dwell (a ref,
  // not state, since it's read-and-set inside the same per-frame branch that
  // already calls setDwelling -- no separate re-render trigger needed).
  const nodded = useRef(false);
  // PEOPLE pass (P2): the CURRENT walk's human-readable reason, snapshotted
  // at walk-start (same instant as activeTarget/activePlan above) and
  // cleared when the walk ends -- see the walk-start/walk-end branches
  // below. `useState` (not a ref): this text feeds the Html bubble's own
  // rendered children, which must re-render when it changes, the same
  // "state for discrete moments" reason `walking`/`dwelling`/`pointing`
  // above are all state rather than refs.
  const [activePurpose, setActivePurpose] = useState<string | null>(null);
  const isKiosk = useIsKiosk();
  // PEOPLE pass: DOM ref to the bubble's own wrapper div, so the per-frame
  // hook can fade it by DIRECT style mutation (never React state -- an
  // opacity ramp every frame would re-render this component's whole JSX
  // tree 60x/s for zero visual gain over a plain style write) -- same
  // "refs for continuous per-frame work" convention as `visorMat` above.
  const bubbleWrapRef = useRef<HTMLDivElement>(null);
  // Scratch vector for updateBubbleFade's own camera-distance calc -- one
  // instance per mounted Agent, reused every frame, zero per-frame
  // allocation (matches ActivityBubbleLayer.tsx's now-deleted identical
  // `_camPos`/`_candPos` module-scope scratch-vector convention, just
  // instance-scoped here since each Agent fades its OWN bubble independently).
  const bubbleDelta = useMemo(() => new THREE.Vector3(), []);

  // Event-triggered walk queue (replaces the old random 20-60s timer, J
  // 2026-09-13). `seenWalkKey` seeds silently on the first value seen after
  // mount -- same convention as Courier.tsx's `seenIds`/HandoffCourier.tsx's
  // `seenOk` -- so a page load never fires a walk for state that already
  // existed. Only a GENUINE change after that queues one.
  const seenWalkKey = useRef<string | null | undefined>(undefined);
  const pendingWalk = useRef<AgentWalkKind | null>(null);
  useEffect(() => {
    if (walkEventKey === null || walkEventKey === undefined) return;
    if (seenWalkKey.current === undefined) {
      seenWalkKey.current = walkEventKey;
      return;
    }
    if (walkEventKey === seenWalkKey.current) return;
    seenWalkKey.current = walkEventKey;
    pendingWalk.current = walkKind ?? "roundtrip";
  }, [walkEventKey, walkKind]);

  // All-hands event trigger (Pass B, 2026-09-13) -- a SEPARATE seen-value
  // diff from the one above, so a persona's own arrival walk and a
  // company-wide all-hands walk can never be confused for each other. If
  // both happen to change in the exact same render, this effect (declared
  // second) wins the shared `pendingWalk` slot -- a rare, low-stakes
  // collision (one visual walk is skipped that tick, never a crash).
  const seenAllHandsKey = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (allHandsEventKey === null || allHandsEventKey === undefined) return;
    if (seenAllHandsKey.current === undefined) {
      seenAllHandsKey.current = allHandsEventKey;
      return;
    }
    if (allHandsEventKey === seenAllHandsKey.current) return;
    seenAllHandsKey.current = allHandsEventKey;
    pendingWalk.current = "allhands";
  }, [allHandsEventKey]);

  // Item 2b (LIVE-1, 2026-09-14) -- purposeful-walk trigger, a THIRD
  // independent seen-value-diff channel (same convention, same low-stakes
  // shared-`pendingWalk`-slot collision note as the all-hands effect above).
  const seenPurposefulKey = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (purposefulWalkEventKey === null || purposefulWalkEventKey === undefined) return;
    if (seenPurposefulKey.current === undefined) {
      seenPurposefulKey.current = purposefulWalkEventKey;
      return;
    }
    if (purposefulWalkEventKey === seenPurposefulKey.current) return;
    seenPurposefulKey.current = purposefulWalkEventKey;
    pendingWalk.current = "purposeful";
  }, [purposefulWalkEventKey]);

  // INTERACT-2 (I2, 2026-09-14) -- named-event walk trigger, a FOURTH
  // independent seen-value-diff channel. `eventWalkPending` records that
  // THIS channel (not the rotational purposeful-walk one) is the reason
  // `pendingWalk.current` is "purposeful", so the consumption block below
  // reads `eventWalkTarget` instead of `purposefulTarget` for this walk.
  const seenEventWalkKey = useRef<string | null | undefined>(undefined);
  const eventWalkPending = useRef(false);
  useEffect(() => {
    if (eventWalkEventKey === null || eventWalkEventKey === undefined) return;
    if (seenEventWalkKey.current === undefined) {
      seenEventWalkKey.current = eventWalkEventKey;
      return;
    }
    if (eventWalkEventKey === seenEventWalkKey.current) return;
    seenEventWalkKey.current = eventWalkEventKey;
    eventWalkPending.current = true;
    pendingWalk.current = "purposeful";
  }, [eventWalkEventKey]);

  // MOTION-2 V2 (2026-09-14) -- WalkPlan trigger, a FIFTH independent
  // seen-value-diff channel (same convention, same low-stakes shared-
  // `pendingWalk`-slot collision note as the channels above). `walkPlan`
  // itself is read LIVE inside the throttled frame callback at walk-start,
  // not snapshotted here -- same discipline as `eventWalkTarget`.
  const seenWalkPlanKey = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (walkPlanKey === null || walkPlanKey === undefined) return;
    if (seenWalkPlanKey.current === undefined) {
      seenWalkPlanKey.current = walkPlanKey;
      return;
    }
    if (walkPlanKey === seenWalkPlanKey.current) return;
    seenWalkPlanKey.current = walkPlanKey;
    pendingWalk.current = "waypoints";
  }, [walkPlanKey]);

  // Item 2c (LIVE-1, 2026-09-14) -- Pilot-only "stands and points" trigger,
  // a THIRD independent seen-value-diff channel (never confused with the
  // walk-queue triggers above -- this one holds a POSE, it never queues a
  // walk). `pendingPoint` (a ref, set here) is consumed inside the throttled
  // frame callback below, the same "effects outside the frame loop can only
  // set an intent flag; the frame loop itself owns the real THREE clock"
  // split CameraRig (Scene.tsx) uses for its own OrbitControls hand-off.
  const seenPointKey = useRef<string | null | undefined>(undefined);
  const pendingPoint = useRef(false);
  useEffect(() => {
    if (pointEventKey === null || pointEventKey === undefined) return;
    if (seenPointKey.current === undefined) {
      seenPointKey.current = pointEventKey;
      return;
    }
    if (pointEventKey === seenPointKey.current) return;
    seenPointKey.current = pointEventKey;
    pendingPoint.current = true;
  }, [pointEventKey]);
  const pointUntil = useRef(0);

  // Set initial position once -- everything after this is imperative ref
  // mutation, never React state, so an agent's motion never triggers a
  // React re-render of the tree above it.
  useEffect(() => {
    group.current?.position.set(...home);
  }, [home]);

  // PEOPLE pass P1 fix (MOTION-3, 2026-09-14, J: "fluid movement" -- the
  // scanner/orbs asks are Hud.tsx/Corridor.tsx/Courier.tsx, this is the
  // third leg, "the people" themselves). ROOT CAUSE (confirmed by reading
  // this hook before touching it): the ENTIRE pose write -- g.position.set,
  // g.rotation.y, leg-swing rotation.x, the alert-pace sub-phase math --
  // lived inside `useThrottledFrame(cb, 20)`, i.e. this callback only ran
  // ~20x/s while UltraCanvasRoot's FrameRateCap renders at 60fps. A walker's
  // mesh therefore held ONE position for ~3 consecutive rendered frames, then
  // jumped ~0.035 world units (WALK_SPEED*1/20s) on the 4th -- stepped
  // motion, especially visible against the continuously-orbiting camera.
  // Verified this is NOT a fixed-dt-accumulator bug (the kind this file's
  // own task brief warned to watch for): every formula below --
  // easedWalkProgress, resolvePathPose, every Math.sin/atan2 leg/bob/visor
  // term -- is a pure function of the ABSOLUTE clock time `t` (or a
  // `t - phaseStart.current` delta recomputed FRESH each call), never an
  // accumulated per-tick step. That means the fix is purely a SAMPLING-RATE
  // change: split this one callback into (1) a plain per-frame `useFrame`
  // below that owns every continuous pose write (position/rotation/leg-swing/
  // visor-pulse/bubble-fade), evaluated with 60fps's own real elapsedTime
  // every rendered frame, and (2) this throttled 20Hz hook, kept for exactly
  // the discrete/rare work the task brief named: seated-variant picks, the
  // "point" pose timer, and the handful of React setState calls
  // (setWalking/setDwelling/setPointing/setAlertPaused/setVariantIdx) a
  // continuous 60Hz loop should not be tripping every frame. Every
  // transition check below is the SAME absolute-time comparison the original
  // single callback used (`elapsed >= walkLegDuration.current` is exactly
  // `easedWalkProgress(...) >= 1`, per that function's own early-return) --
  // this hook only decides WHEN a phase boundary was crossed; the per-frame
  // hook below independently (and redundantly, on purpose) computes the same
  // boundary every frame to draw the continuous position, so a transition
  // landing up to one throttled tick (<=50ms) after the character visually
  // reaches it is invisible -- CLIP_TABLE/animState don't visibly desync at
  // that latency. recordAgentSample deliberately moved OUT of this hook (see
  // the per-frame hook's own comment) -- proving frame-to-frame distinctness
  // needs a sample taken every RENDERED frame, which a 20Hz hook cannot
  // produce by construction.
  useThrottledFrame((t) => {
    if (!group.current) return;

    if (behavior === "frozen") return; // hold whatever pose it already had (a queued walk waits)

    // Item 2a (LIVE-1): pick a new seated-pose variant on this agent's own
    // seeded range, so a room full of agents doesn't sync up. MOTION-2 V3
    // (spec: "working cycles between typing and reading at a calmer cadence,
    // each state >= 6s"): 8-20s -> 10-24s -- the floor already cleared 6s,
    // but J's own "calmer" word plus the room-wide half-speed pass this
    // session both point the same direction, so the whole range moves up,
    // not just the floor. Runs unconditionally (cheap scalar check) --
    // harmless while walking/alert, since `animState` above only reads
    // `variantIdx` in the resting branch; the timer keeps ticking in the
    // background so the NEXT time this agent sits back down it doesn't
    // always reopen on variant 0.
    if (t >= nextVariantAt.current) {
      nextVariantAt.current = t + 10 + rng() * 14; // 10-24s
      const poolLen = pool.length;
      let next = Math.floor(rng() * poolLen);
      if (poolLen > 1 && next === variantIdx) next = (next + 1) % poolLen;
      setVariantIdx(next);
    }

    // Item 2c (LIVE-1): consume a pending "point" trigger -- holds the pose
    // for POINT_HOLD_S seconds, then releases on its own.
    if (pendingPoint.current) {
      pendingPoint.current = false;
      pointUntil.current = t + POINT_HOLD_S;
      setPointing(true);
    } else if (pointing && t >= pointUntil.current) {
      setPointing(false);
    }

    if (behavior === "alert") {
      // Continuous position/rotation/leg-swing for this branch now lives in
      // the per-frame hook below -- this half only detects the two pace-leg
      // boundaries (toDoor/toDesk, each `paceDuration` long) and the two
      // pause boundaries (atDoor/atDesk, each ALERT_PACE_PAUSE_S long) to
      // flip `alertPhase.current`/fire `setAlertPaused`. Distance/pace-
      // duration formulas duplicated from the per-frame hook ON PURPOSE
      // (see this hook's own class comment) -- cheap trig, executed 20x/s.
      // WALK-ROUTING pass: same `alertPacePoint` override as the per-frame
      // hook below -- duplicated formula, so this MUST stay in sync with
      // that hook's own paceDist/paceDuration derivation or the two halves
      // disagree about when a pace leg ends.
      const paceTarget = alertPacePoint ?? hub;
      const homeToTargetDist = Math.hypot(paceTarget[0] - home[0], paceTarget[2] - home[2]) || 0.001;
      const paceDist = alertPacePoint ? homeToTargetDist : Math.min(3.4, homeToTargetDist * 0.4);
      const paceDuration = Math.max(0.6, paceDist / ALERT_PACE_SPEED);
      if (alertPhaseStart.current < 0) alertPhaseStart.current = t;
      const elapsed = t - alertPhaseStart.current;
      if (alertPhase.current === "toDoor" && elapsed >= paceDuration) {
        alertPhase.current = "atDoor"; alertPhaseStart.current = t; setAlertPaused(true);
      } else if (alertPhase.current === "atDoor" && elapsed >= ALERT_PACE_PAUSE_S) {
        alertPhase.current = "toDesk"; alertPhaseStart.current = t; setAlertPaused(false);
      } else if (alertPhase.current === "toDesk" && elapsed >= paceDuration) {
        alertPhase.current = "atDesk"; alertPhaseStart.current = t; setAlertPaused(true);
      } else if (alertPhase.current === "atDesk" && elapsed >= ALERT_PACE_PAUSE_S) {
        alertPhase.current = "toDoor"; alertPhaseStart.current = t; setAlertPaused(false);
      }
      return; // alert has no walk-queue/phase-machine business below
    }

    // Consume a queued walk (see the effect above) -- the ONLY way `phase`
    // ever leaves "resting" now. reducedMotion discards it silently rather
    // than animating (matches Courier.tsx/HandoffCourier.tsx's own
    // reducedMotion handling).
    if (pendingWalk.current) {
      if (reducedMotion) {
        pendingWalk.current = null;
        eventWalkPending.current = false;
      } else if (laneSeed === "Pilot" && isRegularTradingHours(nowEtMinutes(), nowEtDayOfWeek())) {
        // MOTION-2 V3: Pilot never leaves its desk during RTH (CLAUDE.md's
        // 09:30-15:55 ET market-hours window) -- discarded, not deferred, so
        // a trigger that fires mid-session doesn't suddenly walk hours later
        // once the window closes. Checked here (not left to whichever
        // caller happens to gate its own trigger) so this holds as a real
        // backstop even if a future caller forgets to; an in-progress walk
        // (phase.current !== "resting") is never interrupted by this --
        // only a not-yet-started QUEUED walk is dropped.
        pendingWalk.current = null;
        eventWalkPending.current = false;
      } else if (
        phase.current === "resting" &&
        // MOTION-2 V3 (J: "a little bit of LOGIC to their movement" -- never
        // a fire-drill look): module-scope stagger shared by EVERY Agent
        // instance (see lastGlobalWalkStartT's own comment) -- if another
        // agent anywhere started a walk within the last
        // WALK_START_STAGGER_S, this one simply waits (pendingWalk.current
        // stays set, re-checked next throttled tick) instead of starting
        // alongside it.
        t - lastGlobalWalkStartT >= WALK_START_STAGGER_S
      ) {
        lastGlobalWalkStartT = t;
        activeWalkKind.current = pendingWalk.current;
        // Item 2b (LIVE-1) / INTERACT-2 (I2): snapshot the destination NOW,
        // not a live prop read later. A "purposeful" walk queued by THIS
        // render's eventWalk trigger reads eventWalkTarget; the rotational
        // 6-10min trigger reads purposefulTarget as before. Both fall back
        // to the generic `approach` point if the parent somehow queued with
        // no target (defensive, should never happen given Scene.tsx always
        // pairs a trigger with its own target).
        activeTarget.current = pendingWalk.current === "purposeful"
          ? (eventWalkPending.current ? (eventWalkTarget ?? approach) : (purposefulTarget ?? approach))
          : null;
        // MOTION-2 V2: snapshot the WalkPlan the SAME way (live prop read,
        // not the effect-time value -- see the prop's own comment).
        activePlan.current = pendingWalk.current === "waypoints" ? (walkPlan ?? null) : null;
        // PEOPLE pass (P2/P4): snapshot the human-readable REASON this walk
        // is happening, same live-read-at-start discipline as activeTarget/
        // activePlan above -- and the SAME eventWalkPending-vs-rotational
        // split activeTarget already uses, since both "purposeful" triggers
        // share this one walk kind. "arrival"/"allhands" carry one true,
        // invariant meaning per AgentWalkKind's own doc comment, so they
        // need no external prop; "waypoints" reads the plan's own real
        // `purpose`. When neither purpose prop is wired yet (Scene.tsx's
        // own wiring lands in a follow-up commit) this is honestly null,
        // never a fabricated reason.
        setActivePurpose(
          pendingWalk.current === "waypoints" ? (activePlan.current?.purpose ?? null)
          : pendingWalk.current === "arrival" ? "back to the desk"
          : pendingWalk.current === "allhands" ? "all-hands at the core"
          : pendingWalk.current === "purposeful"
            ? (eventWalkPending.current ? (eventWalkReason ?? null) : (purposefulReason ?? null))
          : null,
        );
        eventWalkPending.current = false;
        const startPhase = pendingWalk.current === "arrival" ? "arriving" : "toHub";
        phase.current = startPhase;
        phaseStart.current = t;
        pendingWalk.current = null;
        setWalking(true);
        setDwelling(null);
        nodded.current = false;
        if (startPhase === "arriving") {
          // WALK-ROUTING pass: "arriving" is still a one-way hub->home trip
          // with no dwell/return, but now routed through `walkGraph` (when
          // provided) via the SAME resolvePathPose machinery "toHub" uses --
          // see resolvePathPose's own comment for why this is provably a
          // no-op for the un-routed (walkGraph undefined) 2-point case.
          outboundPath.current = walkGraph ? routeViaGraph(walkGraph, hub, home) : [hub, home];
          walkLegDuration.current = Math.max(MIN_WALK_LEG_S, pathTotalDistance(outboundPath.current) / WALK_SPEED);
        } else if (activeWalkKind.current === "waypoints" && activePlan.current) {
          // MOTION-2 V2: a real N-point path (LAYOUT's own walk-graph
          // route) instead of a single straight leg -- see resolvePathPose's
          // own comment for how this generalizes the toHub/atHub/toHome
          // machinery below. Defensive prepend: `waypoints` is documented as
          // "a real path" but not guaranteed to literally start at this
          // agent's OWN current `home` -- only prepend when it doesn't
          // already, so this works under either convention.
          const first = activePlan.current.waypoints[0];
          const startsAtHome = !!first && Math.hypot(first[0] - home[0], first[2] - home[2]) < 0.05;
          outboundPath.current = startsAtHome ? activePlan.current.waypoints : [home, ...activePlan.current.waypoints];
          walkLegDuration.current = Math.max(MIN_WALK_LEG_S, pathTotalDistance(outboundPath.current) / WALK_SPEED);
        } else {
          // Legacy 2-point kinds (roundtrip/allhands/purposeful/eventWalk) --
          // "a straight line IS a 2-waypoint plan" (spec): routed through the
          // SAME resolvePathPose machinery below, mathematically identical
          // to the old direct-lerp behavior when `walkGraph` is absent (see
          // that function's own no-op-for-2-points proof). WALK-ROUTING pass
          // (2026-09-15): when `walkGraph` IS provided, the raw `[home,
          // legTo]` 2-point leg is replaced by `routeViaGraph`'s real
          // hallway/door route -- this is the fix for the reported "Futures
          // ran straight through its own wall" bug (that walk is this exact
          // kind, "purposeful"/"roundtrip"/allhands all sharing this one
          // branch).
          const legTo = activeWalkKind.current === "purposeful" && activeTarget.current ? activeTarget.current : approach;
          outboundPath.current = walkGraph ? routeViaGraph(walkGraph, home, legTo) : [home, legTo];
          walkLegDuration.current = Math.max(MIN_WALK_LEG_S, pathTotalDistance(outboundPath.current) / WALK_SPEED);
        }
      }
    }

    // Phase-BOUNDARY transitions only from here down -- the per-frame hook
    // below independently recomputes the SAME `elapsed`/pause-vs-threshold
    // comparisons every rendered frame to draw the continuous position; this
    // throttled (20Hz) half exists only to catch the moment a boundary is
    // crossed and flip `phase.current`/fire the rare setState calls. See
    // this hook's own opening comment for why a transition landing up to one
    // throttled tick late is invisible.
    if (phase.current === "arriving") {
      if (t - phaseStart.current >= walkLegDuration.current) {
        phase.current = "resting"; setWalking(false); setActivePurpose(null);
      }
    } else if (phase.current === "toHub") {
      if (t - phaseStart.current >= walkLegDuration.current) {
        phase.current = "atHub";
        phaseStart.current = t;
        // All-hands stand / waypoints dwell: "idle clip" per the spec --
        // drop the ultra tier's `walking` animState flag for the duration of
        // the stand, restored when it ends (see the atHub branch below).
        if (activeWalkKind.current === "allhands" || activeWalkKind.current === "waypoints") setWalking(false);
        if (activeWalkKind.current === "waypoints" && activePlan.current) {
          setDwelling(dwellAnimState(activePlan.current.dwellAnim));
        }
      }
    } else if (phase.current === "atHub") {
      if (activeWalkKind.current === "waypoints" && activePlan.current) {
        // MOTION-2 V3 (J: "the dwell must read as doing something"): a small
        // head nod in the LAST DWELL_NOD_S seconds -- a clear "wrapped up,
        // about to leave" tell. `nodded` guards this to a single setState
        // call per dwell. Math.max(0, ...) so a dwellS shorter than
        // DWELL_NOD_S still nods immediately rather than never nodding.
        const dwellS = activePlan.current.dwellS;
        if (!nodded.current && t - phaseStart.current >= Math.max(0, dwellS - DWELL_NOD_S)) {
          nodded.current = true;
          setDwelling("resting-idle-nod");
        }
      }
      const pauseSeconds =
        activeWalkKind.current === "allhands" ? ALLHANDS_HUB_PAUSE
        : activeWalkKind.current === "purposeful" ? PURPOSEFUL_PAUSE
        : activeWalkKind.current === "waypoints" ? (activePlan.current?.dwellS ?? PURPOSEFUL_PAUSE)
        : HUB_PAUSE;
      if (t - phaseStart.current >= pauseSeconds) {
        phase.current = "toHome";
        phaseStart.current = t;
        // MOTION-2 V2: return leg -- the SAME path, reversed (computed once
        // here, not per-frame; total distance is unchanged under reversal so
        // walkLegDuration stays correct as-is for legacy kinds too).
        returnPath.current = outboundPath.current.slice().reverse();
        if (activeWalkKind.current === "allhands" || activeWalkKind.current === "waypoints") setWalking(true);
        if (activeWalkKind.current === "waypoints") setDwelling(null);
      }
    } else if (phase.current === "toHome") {
      if (t - phaseStart.current >= walkLegDuration.current) {
        phase.current = "resting";
        activeTarget.current = null;
        activePlan.current = null;
        setActivePurpose(null);
      }
    }
  }, 20);

  // PEOPLE pass P1 fix: CONTINUOUS pose integration -- position, rotation/
  // facing, leg swing, the visor pulse, and the bubble's own camera-distance
  // fade -- runs here, every rendered frame, via a plain useFrame (no
  // throttle). Every formula below is copied VERBATIM from the throttled
  // callback above (see its own comment for the split rationale and the
  // proof this is a pure sampling-rate change, not a behavior change): same
  // easedWalkProgress/resolvePathPose calls, same Math.sin/atan2 terms, same
  // refs. `state.clock.elapsedTime` is r3f's own real per-frame clock (never
  // `Date.now()`), so every walker in the room reads the identical `t` a
  // rendered frame actually happened at.
  useFrame((state) => {
    if (!group.current) return;
    const g = group.current;
    if (behavior === "frozen") return;
    const t = state.clock.elapsedTime;

    if (behavior === "alert") {
      // WALK-ROUTING pass (2026-09-15): `alertPacePoint` (Scene.tsx passes
      // `slot.doorWorldPos` for bay agents) overrides the pace target and
      // its facing direction -- see this prop's own doc comment on
      // AgentProps for the full root-cause writeup (a bay agent's real
      // "step to the door" point sits along its own side-hallway axis, not
      // the straight home->hub diagonal, which used to pace it through the
      // bay's own side wall). Personas (no override) keep the exact
      // original toward-hub formula -- always safe there since the hub
      // interior has no wall between a persona desk and the hub center.
      const paceTarget = alertPacePoint ?? hub;
      const homeToTargetDist = Math.hypot(paceTarget[0] - home[0], paceTarget[2] - home[2]) || 0.001;
      const paceDist = alertPacePoint ? homeToTargetDist : Math.min(3.4, homeToTargetDist * 0.4);
      const dirX = (paceTarget[0] - home[0]) / homeToTargetDist;
      const dirZ = (paceTarget[2] - home[2]) / homeToTargetDist;
      const doorPos: [number, number, number] = [home[0] + dirX * paceDist, home[1], home[2] + dirZ * paceDist];
      const paceDuration = Math.max(0.6, paceDist / ALERT_PACE_SPEED);
      // alertPhaseStart.current is seeded by the throttled hook above on the
      // FIRST tick this agent ever goes alert (its own -1 sentinel); a
      // not-yet-seeded read here (the handful of frames before that first
      // throttled tick fires) falls back to elapsed=0 rather than a bogus
      // negative-infinity gap.
      const elapsed = alertPhaseStart.current < 0 ? 0 : t - alertPhaseStart.current;
      // WALK-ROUTING pass: renamed from `facingHub` -- with `alertPacePoint`
      // set, this points toward the bay's own door, not the hub; the
      // geometry (atan2 of the same dirX/dirZ) is otherwise unchanged.
      const facingPaceTarget = Math.atan2(dirX, dirZ);

      if (alertPhase.current === "toDoor") {
        const p = easedWalkProgress(elapsed, paceDuration, WALK_EASE_S);
        g.position.set(home[0] + (doorPos[0] - home[0]) * p, home[1], home[2] + (doorPos[2] - home[2]) * p);
        g.rotation.y = facingPaceTarget;
      } else if (alertPhase.current === "atDoor") {
        g.position.set(doorPos[0], doorPos[1], doorPos[2]);
        g.rotation.y = facingPaceTarget; // "looking toward the hub/door" -- doorPos sits ON the home->target line
      } else if (alertPhase.current === "toDesk") {
        const p = easedWalkProgress(elapsed, paceDuration, WALK_EASE_S);
        g.position.set(doorPos[0] + (home[0] - doorPos[0]) * p, home[1], doorPos[2] + (home[2] - doorPos[2]) * p);
        g.rotation.y = facingPaceTarget + Math.PI; // facing the direction of travel (away from the target, back toward the desk)
      } else {
        g.position.set(home[0], home[1], home[2]);
        g.rotation.y = facingPaceTarget; // pause at the desk end, turned back to look toward the hub/door
      }

      const moving = alertPhase.current === "toDoor" || alertPhase.current === "toDesk";
      const swing = moving ? Math.sin(t * NATIVE_SWING_HZ * clipCadenceRatio(ALERT_PACE_SPEED, NATIVE_WALK_CLIP_MPS)) * 0.5 : 0;
      if (legL.current) legL.current.rotation.x = swing;
      if (legR.current) legR.current.rotation.x = -swing;
      recordAgentSample({ id: laneSeed, x: g.position.x, y: g.position.y, z: g.position.z, clipSpeed: CLIP_TABLE.alert.speed });
      const patrolDimAlert = Math.min(presenceMode === "patrol" ? 0.35 : 1, scheduleDim);
      if (visorMat.current) visorMat.current.emissiveIntensity = (1.4 + Math.sin(t * 3) * 0.2) * patrolDimAlert;
      updateBubbleFade(g, state.camera);
      return;
    }

    if (phase.current === "arriving") {
      // One-way hub -> home (a persona that just fired, walking in from the
      // manager and sitting down to work) -- ends in "resting", never
      // returns to the hub the way a roundtrip does. WALK-ROUTING pass:
      // routed via `outboundPath.current` (set to the graph-routed leg, or
      // the raw [hub, home] fallback, at walk-start above) through the SAME
      // resolvePathPose machinery "toHub" uses just below -- see that
      // function's own comment for why this reproduces the exact old
      // "turn before moving, constant facing for the whole leg" feel when
      // the path is still just 2 points.
      const p = easedWalkProgress(t - phaseStart.current, walkLegDuration.current, WALK_EASE_S);
      const pose = resolvePathPose(outboundPath.current, p, WALK_SPEED);
      g.rotation.y = pose.facing;
      g.position.set(...pose.position);
    } else if (phase.current === "toHub") {
      // MOTION-2 V2: resolvePathPose walks the (possibly multi-leg) outbound
      // path -- see that function's own comment; reduces to exactly today's
      // single-leg lerp+fixed-facing for every existing 2-point kind.
      const p = easedWalkProgress(t - phaseStart.current, walkLegDuration.current, WALK_EASE_S);
      const pose = resolvePathPose(outboundPath.current, p, WALK_SPEED);
      g.rotation.y = pose.facing;
      g.position.set(...pose.position);
    } else if (phase.current === "atHub") {
      const pathEnd = outboundPath.current[outboundPath.current.length - 1] ?? approach;
      g.position.set(...pathEnd);
      // All-hands stand: face the core precisely (spec: "facing core") --
      // roundtrip's brief 1.5s touch never bothered with facing, but a
      // 60s stand reads wrong looking anywhere else. Same atan2(dx,dz)
      // convention as `greeterFacingYaw` above. A "purposeful" stop (item
      // 2b) faces its own destination point the SAME way -- reading a card
      // wall or filing at the core looks wrong facing some other direction.
      if (activeWalkKind.current === "allhands") {
        g.rotation.y = Math.atan2(hub[0] - approach[0], hub[2] - approach[2]);
      } else if (activeWalkKind.current === "purposeful") {
        g.rotation.y = Math.atan2(hub[0] - pathEnd[0], hub[2] - pathEnd[2]);
      } else if (activeWalkKind.current === "waypoints" && activePlan.current) {
        // MOTION-2 V2: face the plan's own faceYaw if given, else the
        // heading the agent arrived WITH (resolvePathPose at pathT=1 is
        // exactly the final leg's own heading) -- never the "purposeful"
        // convention of facing back toward the hub, since a waypoint walk's
        // destination usually isn't the hub at all.
        g.rotation.y = activePlan.current.faceYaw ?? resolvePathPose(outboundPath.current, 1, WALK_SPEED).facing;
      }
    } else if (phase.current === "toHome") {
      const p = easedWalkProgress(t - phaseStart.current, walkLegDuration.current, WALK_EASE_S);
      const pose = resolvePathPose(returnPath.current, p, WALK_SPEED);
      g.rotation.y = pose.facing;
      g.position.set(...pose.position);
    } else {
      // resting -- bob (working = brisker, idle = slower/shallower)
      const bobAmp = behavior === "working" ? 0.05 : 0.025;
      const bobSpeed = behavior === "working" ? 4 : 1.4;
      g.position.set(home[0], home[1] + Math.sin(t * bobSpeed) * bobAmp, home[2]);
      // World-4 fix (P6, 2026-09-14, J: "the bottom bays show characters not
      // facing their desks"): see the original fix's own comment (git
      // history) -- desk-facing is `atan2(hub-home) + PI`, never a leftover
      // walk heading. BLOCKY-FIXES pass (2026-09-16, Defect A): `deskYaw`
      // (the desk's own furniture rotation, exact by construction -- see
      // this prop's own doc comment above) now REPLACES this hub-based
      // approximation whenever the caller has it, which is every persona
      // wall-slot desk today; bay/lane agents (no `deskYaw` passed) keep
      // this exact formula unchanged.
      const deskFacing = deskYaw ?? Math.atan2(hub[0] - home[0], hub[2] - home[2]) + Math.PI;
      if (behavior === "working") {
        if (armL.current) armL.current.rotation.x = Math.sin(t * 10) * 0.35;
        if (armR.current) armR.current.rotation.x = Math.sin(t * 10 + Math.PI) * 0.35;
        g.rotation.y = deskFacing;
      } else if (presenceMode === "greet") {
        // J 2026-09-13: "nearest agent turns to the viewer" on presence ==
        // here -- holds a fixed facing instead of the idle look-around.
        g.rotation.y = facingYaw ?? 0;
      } else {
        // Slow "look around", centered on `deskFacing` (this character's own
        // desk direction, not world-absolute 0).
        g.rotation.y = deskFacing + Math.sin(t * 0.15) * 0.3;
      }
    }

    const walkingNow = phase.current === "toHub" || phase.current === "toHome" || phase.current === "arriving";
    if (walkingNow) {
      // MOTION-2: NATIVE_SWING_HZ*clipCadenceRatio(WALK_SPEED, ...) replaces
      // the old bare "8" (tuned at the pre-halving 1.4 u/s WALK_SPEED) --
      // see NATIVE_SWING_HZ's own comment for the slow-motion-legs mechanism
      // this avoids.
      const swing = Math.sin(t * NATIVE_SWING_HZ * clipCadenceRatio(WALK_SPEED, NATIVE_WALK_CLIP_MPS)) * 0.5;
      if (legL.current) legL.current.rotation.x = swing;
      if (legR.current) legR.current.rotation.x = -swing;
    } else if (legL.current && legR.current) {
      legL.current.rotation.x = 0;
      legR.current.rotation.x = 0;
    }

    // World-2 MOTION-FIX diag (?diag=1 only -- no-ops otherwise, see
    // hq-motion-diag.ts's own header), relocated from the throttled hook to
    // HERE (P1 fix, 2026-09-14): proving "consecutive rendered frames show
    // distinct positions" needs a sample taken every rendered frame -- a
    // 20Hz-throttled sample can only ever show distinctness between
    // throttled ticks, which was never the bug (position obviously differs
    // 50ms apart; the bug was 3 RENDERED frames in between holding still).
    recordAgentSample({ id: laneSeed, x: g.position.x, y: g.position.y, z: g.position.z, clipSpeed: CLIP_TABLE[animState].speed });

    // "Night patrol" dim (J 2026-09-13: presence == away) + Pass C schedule
    // dim (2026-09-13: off-shift persona, only when not genuinely working)
    // -- cuts the visor's own emissive glow, the cheapest possible "quieter
    // right now" tell (no new material, no opacity/blend cost). Whichever
    // reason is stronger wins (Math.min), never double-dimmed.
    const patrolDim = Math.min(presenceMode === "patrol" ? 0.35 : 1, scheduleDim);
    if (visorMat.current) visorMat.current.emissiveIntensity = (1.4 + Math.sin(t * 3) * 0.2) * patrolDim;

    updateBubbleFade(g, state.camera);
  });

  /** PEOPLE pass (P2): opacity-only camera-distance fade for this agent's
   * own bubble -- direct DOM style mutation (never React state/props), same
   * "refs for continuous per-frame work, state for discrete moments"
   * convention as `visorMat` above. A no-op before the bubble's first
   * render (`bubbleWrapRef.current` null pre-mount, or when there's no text
   * to show at all -- see the JSX below). */
  function updateBubbleFade(g: THREE.Group, camera: THREE.Camera): void {
    const el = bubbleWrapRef.current;
    if (!el) return;
    bubbleDelta.set(g.position.x - camera.position.x, g.position.y - camera.position.y, g.position.z - camera.position.z);
    const dist = bubbleDelta.length();
    el.style.opacity = dist > BUBBLE_FADE_DISTANCE ? "0" : "1";
    // Coordinator follow-up (read off polish1-p1-camclose.png, 20:11 ET):
    // inside the hub (~3-4 u) drei's 1/dist scaling blew a "little" bubble up
    // to ~75 px. Piecewise counter-scale: beyond the far reference the floor
    // above; between BUBBLE_MAX_SIZE_DISTANCE and the reference, natural
    // scaling (9.5 -> 19 px on J's 1440p); closer than that, hold ~19 px --
    // twice the far floor, never a banner.
    const k = bubbleCounterScale(dist);
    el.style.transform = Math.abs(k - 1) > 0.01 ? `scale(${k.toFixed(3)})` : "";
  }

  // PEOPLE pass (P2): while a walk carries its own real reason, that reason
  // IS the bubble (P4 -- "every existing walk must carry a human-readable
  // purpose in its bubble"); otherwise fall back to the caller's own
  // evidence-backed `bubbleText`. Null when NEITHER has anything real to
  // say -- the bubble renders nothing rather than inventing copy.
  const bubbleAction = activePurpose ?? bubbleText ?? null;
  const bubbleActionTrunc = bubbleAction ? truncateOneLine(bubbleAction, BUBBLE_ACTION_MAX_CHARS) : null;
  const bubbleY = (ultra ? ULTRA_HEAD_Y : TV_HEAD_Y) + BUBBLE_HEAD_GAP;

  // DECLUTTER pass: registers this agent's own bubble anchor (group position
  // + the fixed vertical bubbleY offset -- exact, not approximate, since a
  // pure Y-axis rotation never moves a point already offset only along Y --
  // see useLabelDeclutter.ts's own call-site convention) with the shared
  // resolver. `laneSeed` is stable for the lifetime of this mounted agent
  // (a lane name or persona name never changes underneath the same slot),
  // so it's a safe declutter id. Registered unconditionally (cheap -- a
  // `useEffect` + module Map write) even on ticks with no visible bubble;
  // the manager itself skips any wrapperRef whose element isn't mounted.
  const declutterId = `${bubblePriority === PRIORITY.PERSONA ? "persona" : "lane"}:${laneSeed}`;
  const declutterWorldPos = useMemo(
    () => (): [number, number, number] => {
      const g = group.current;
      return g ? [g.position.x, g.position.y + bubbleY, g.position.z] : [0, 0, 0];
    },
    [bubbleY],
  );
  const { wrapperRef: declutterRef, measureRef: declutterMeasureRef } = useLabelDeclutter(declutterId, bubblePriority, declutterWorldPos);

  return (
    <group ref={group}>
      {ultra ? (
        // Kit rebuild bug fix (2026-09-13, world pass A): `ultra`/`animState`
        // were computed above but NEVER READ here -- this branch never
        // existed, so every agent rendered the procedural body regardless of
        // tier. Caught from the first real screenshot, not the build (an
        // unused local never fails `tsc` with this project's tsconfig).
        // Suspense-scoped (see BrainCore.tsx's identical fix + comment) so a
        // still-loading character body never unmounts anything else.
        <Suspense fallback={null}>
          <KitAgentBody laneSeed={laneSeed} animState={animState} accentColor={accentColor} patrolDim={patrolDim} frozen={behavior === "frozen"} />
        </Suspense>
      ) : (
        <>
          {/* Legs/body/arms/backpack -- procedural matcap (HQ v4 look pass,
              2026-09-13): one texture lookup replaces Lambert's per-fragment
              N.L at the same cost class, giving these little bots actual
              dimensional shading instead of flat color blocks. The visor
              below stays Lambert+emissive unchanged -- it's meant to glow,
              not be shaded by a matcap. TV tier only (see `ultra` branch
              above) -- unchanged from every prior pass. */}
          <mesh ref={legL} position={[-0.09, 0.18, 0]}>
            <cylinderGeometry args={[0.045, 0.045, 0.32, 6]} />
            <meshMatcapMaterial matcap={matcap} color="#1b2436" />
          </mesh>
          <mesh ref={legR} position={[0.09, 0.18, 0]}>
            <cylinderGeometry args={[0.045, 0.045, 0.32, 6]} />
            <meshMatcapMaterial matcap={matcap} color="#1b2436" />
          </mesh>
          {/* Body (capsule) */}
          <mesh position={[0, 0.5, 0]}>
            <capsuleGeometry args={[0.14, 0.32, 4, 8]} />
            <meshMatcapMaterial matcap={matcap} color="#232d44" />
          </mesh>
          {/* Arms */}
          <mesh ref={armL} position={[-0.19, 0.55, 0]}>
            <cylinderGeometry args={[0.035, 0.035, 0.28, 6]} />
            <meshMatcapMaterial matcap={matcap} color="#232d44" />
          </mesh>
          <mesh ref={armR} position={[0.19, 0.55, 0]}>
            <cylinderGeometry args={[0.035, 0.035, 0.28, 6]} />
            <meshMatcapMaterial matcap={matcap} color="#232d44" />
          </mesh>
          {/* Backpack */}
          <mesh position={[0, 0.5, -0.13]}>
            <boxGeometry args={[0.16, 0.22, 0.08]} />
            <meshMatcapMaterial matcap={matcap} color="#141b2e" />
          </mesh>
          {/* Visor / head-lamp */}
          <mesh position={[0, 0.78, 0.09]}>
            <sphereGeometry args={[0.1, 10, 8]} />
            <meshLambertMaterial ref={visorMat} color={accentColor} emissive={accentColor} emissiveIntensity={1.4} toneMapped={false} />
          </mesh>
        </>
      )}

      {/* HEAD-LABELS pass (2026-09-15, J: "labels are too big and wordy...
          above each head show only: name + a model-tier icon + a colored
          status dot. Long status text belongs in hover/click") -- replaces
          the old always-wordy "<name> · <action text>" bubble (PEOPLE pass,
          2026-09-14) with the compact HeadLabel (headLabelModel.ts/HeadLabel.tsx;
          see ENVIRONMENT-PLAN.md's "Design pass 2026-09-15" part C for the
          sourced label conventions). Renders UNCONDITIONALLY now -- the
          name/dot/glyph are always real for a visible character, unlike the
          old gate on `bubbleActionTrunc` (which only existed because the
          FORMER label had nothing else to show without an action string).
          `detail` folds the former action text + audit-verdict letter into
          one hover-only string (Two Point Hospital convention, part C
          source 5) rather than an always-on chip; `detailKey` still keys
          the shared `.hq-shine` one-shot sweep so a genuine change still
          reads as motion even though the wordy text no longer floats. */}
      <Html position={[0, bubbleY, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
        {/* DECLUTTER pass: a NEW outer wrapper the shared resolver owns
            (transform/opacity only, vertical-nudge + fade-beyond-cap) --
            deliberately separate from `bubbleWrapRef` just inside it,
            which keeps doing its own camera-distance scale/fade exactly
            as before (see labelDeclutter.ts's own header for why these
            must be two different DOM nodes). */}
        <div ref={declutterRef} style={{ transformOrigin: "50% 100%" }}>
          <div ref={mergeRefs(bubbleWrapRef, declutterMeasureRef)} style={{ position: "relative", transformOrigin: "50% 100%", pointerEvents: isKiosk ? "none" : "auto" }}>
            <HeadLabel
              name={laneSeed}
              glyph={modelGlyphChar ?? computeModelGlyph("none").glyph}
              glyphTitle={modelGlyphTitle ?? computeModelGlyph("none").title}
              dotColor={accentColor}
              accentColor={accentColor}
              detail={
                bubbleActionTrunc
                  ? auditVerdict
                    ? `${bubbleActionTrunc} (audit: ${auditVerdict})`
                    : bubbleActionTrunc
                  : auditVerdict
                    ? `audit: ${auditVerdict}`
                    : null
              }
              detailKey={`${bubbleActionTrunc ?? ""}|${auditVerdict ?? ""}`}
              interactive={!isKiosk}
            />
          </div>
        </div>
      </Html>
    </group>
  );
}

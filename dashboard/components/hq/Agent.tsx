"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { useThrottledFrame } from "./useThrottledFrame";
import { makeMatcapTexture, seededRandom } from "./palette";
import { ALERT_PACE_SPEED, CLIP_TABLE, IDLE_VARIANTS, KitAgentBody, WALK_SPEED, WORKING_VARIANTS, type KitAnimState } from "./KitAgent";
import { recordAgentSample } from "@/lib/hq-motion-diag";

export type AgentBehavior = "working" | "idle" | "alert" | "frozen";
export type AgentWalkKind = "roundtrip" | "arrival" | "allhands" | "purposeful";
export type AgentPresenceMode = "greet" | "patrol";

interface AgentProps {
  laneSeed: string;
  home: [number, number, number];
  hub: [number, number, number];
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
const WALK_EASE_S = 0.3;
// World-2 item 5 (2026-09-14, J: "futures is running because it's on alert...
// it's just running in place, which is weird"): a real pace between the desk
// and the hub-facing door -- see the `behavior === "alert"` branch's own
// comment for the full distance/speed derivation. ALERT_PACE_SPEED now lives
// in / derives from KitAgent.tsx (see its own comment) -- imported above,
// not redefined here, so this file's translation speed and that file's
// clip-speed multiplier can never drift apart.
const ALERT_PACE_PAUSE_S = 2.5; // was 1.5 -- a real pause, not a tap-and-go
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
  laneSeed, home, hub, behavior, accentColor, reducedMotion, walkEventKey, walkKind, allHandsEventKey, purposefulWalkEventKey, pointEventKey, purposefulTarget, eventWalkEventKey, eventWalkTarget, presenceMode, facingYaw,
  scheduleDim = 1,
  ultra = false,
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
  // IDLE_VARIANTS/WORKING_VARIANTS on its own per-instance 8-20s timer (see
  // the throttled callback below), instead of always showing the same "sit"
  // clip. `useState` (not a ref) because KitAgentBody's own clip crossfade
  // is driven by `animState` CHANGING as a REACT PROP -- a ref mutation
  // alone would never re-render KitAgentBody with the new value. Costs one
  // extra re-render every 8-20s per agent, the same "state for discrete
  // moments" tradeoff this file already makes for `walking` below.
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
  const pool = behavior === "working" ? WORKING_VARIANTS : IDLE_VARIANTS;
  const animState: KitAnimState =
    behavior === "alert" ? (alertPaused ? "alert-pause" : "alert") : walking ? "walking" : pointing ? "thinking" : pool[variantIdx % pool.length];
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
  // World-2 MOTION-FIX: computed ONCE at walk-start (see the pendingWalk
  // consumption block below) -- toHub and toHome always cover the SAME
  // straight-line distance (the same two points, reversed), and "arriving"
  // is a single leg, so one duration value covers whichever leg(s) a given
  // walk actually plays. walkFacing is recomputed at EACH leg's own start
  // (toHub/arriving in the consumption block, toHome at the atHub->toHome
  // transition) since the two legs of a roundtrip face opposite ways --
  // this is the "turn before moving" lever: rotation snaps to the new
  // heading the instant a leg starts, and since easedWalkProgress's ramp-up
  // keeps actual translation near-zero for the first fraction of a second,
  // the visible result reads as "turns, then departs" without a separate
  // turn-only sub-phase.
  const walkLegDuration = useRef(MIN_WALK_LEG_S);
  const walkFacing = useRef(0);
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

  useThrottledFrame((t) => {
    if (!group.current) return;
    const g = group.current;

    if (behavior === "frozen") return; // hold whatever pose it already had (a queued walk waits)

    // Item 2a (LIVE-1): pick a new seated-pose variant every 8-20s (this
    // agent's own seeded range, so a room full of agents doesn't sync up).
    // Runs unconditionally (cheap scalar check) -- harmless while walking/
    // alert, since `animState` above only reads `variantIdx` in the
    // resting branch; the timer keeps ticking in the background so the
    // NEXT time this agent sits back down it doesn't always reopen on
    // variant 0.
    if (t >= nextVariantAt.current) {
      nextVariantAt.current = t + 8 + rng() * 12; // 8-20s
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
      // World-2 item 5 (2026-09-14, J: "it's just running in place, which is
      // weird"): a real PACE between the desk and the hub-facing door,
      // replacing the old sub-1-unit local-X sway. Reuses `home`/`hub`
      // (already passed in, no new prop needed) -- walking along that same
      // line by a clamped distance approximates "to the door and back" for
      // both ring families this component serves: a lane bay's door sits on
      // the hub-facing wall exactly along this radial line (see
      // SetKit.tsx's BAY_HALF_DEPTH/gate-door placement -- home is near the
      // module's own local origin, the door ~2.7u toward the hub), and a
      // tighter persona desk gets a proportionally shorter pace (the *0.4
      // clamp) so it never reaches into BrainCore's own ring geometry.
      const homeToHubDist = Math.hypot(hub[0] - home[0], hub[2] - home[2]) || 0.001;
      const paceDist = Math.min(3.4, homeToHubDist * 0.4);
      const dirX = (hub[0] - home[0]) / homeToHubDist;
      const dirZ = (hub[2] - home[2]) / homeToHubDist;
      const doorPos: [number, number, number] = [home[0] + dirX * paceDist, home[1], home[2] + dirZ * paceDist];
      // World-2 MOTION-FIX: ALERT_PACE_SPEED now a real <=1.0 u/s brisk-walk
      // pace (imported from KitAgent.tsx, was a local 2.0 u/s jog) -- the
      // Math.max(0.6, ...) floor is defensive only, for a very tight persona
      // desk's clamped paceDist.
      const paceDuration = Math.max(0.6, paceDist / ALERT_PACE_SPEED);

      if (alertPhaseStart.current < 0) alertPhaseStart.current = t;
      const elapsed = t - alertPhaseStart.current;
      const facingHub = Math.atan2(dirX, dirZ);

      if (alertPhase.current === "toDoor") {
        const p = easedWalkProgress(elapsed, paceDuration, WALK_EASE_S);
        g.position.set(home[0] + (doorPos[0] - home[0]) * p, home[1], home[2] + (doorPos[2] - home[2]) * p);
        g.rotation.y = facingHub;
        if (p >= 1) { alertPhase.current = "atDoor"; alertPhaseStart.current = t; setAlertPaused(true); }
      } else if (alertPhase.current === "atDoor") {
        g.position.set(doorPos[0], doorPos[1], doorPos[2]);
        g.rotation.y = facingHub; // "looking toward the hub" -- doorPos sits ON the home->hub line
        if (elapsed >= ALERT_PACE_PAUSE_S) { alertPhase.current = "toDesk"; alertPhaseStart.current = t; setAlertPaused(false); }
      } else if (alertPhase.current === "toDesk") {
        const p = easedWalkProgress(elapsed, paceDuration, WALK_EASE_S);
        g.position.set(doorPos[0] + (home[0] - doorPos[0]) * p, home[1], doorPos[2] + (home[2] - doorPos[2]) * p);
        g.rotation.y = facingHub + Math.PI; // facing the direction of travel (away from hub, back toward the desk)
        if (p >= 1) { alertPhase.current = "atDesk"; alertPhaseStart.current = t; setAlertPaused(true); }
      } else {
        g.position.set(home[0], home[1], home[2]);
        g.rotation.y = facingHub; // pause at the desk end, turned back to look toward the hub
        if (elapsed >= ALERT_PACE_PAUSE_S) { alertPhase.current = "toDoor"; alertPhaseStart.current = t; setAlertPaused(false); }
      }

      const moving = alertPhase.current === "toDoor" || alertPhase.current === "toDesk";
      // World-2 MOTION-FIX: leg-swing frequency scaled down proportionally
      // to ALERT_PACE_SPEED's own 2.0->0.9 u/s reduction (0.9/2.0 = 0.45,
      // 9*0.45~=4) so the TV tier's procedural stride cadence still roughly
      // matches how fast the body is actually translating -- an estimate,
      // same honesty convention as this file's other tuned constants, not a
      // measured gait-cycle rate.
      const swing = moving ? Math.sin(t * 4) * 0.5 : 0;
      if (legL.current) legL.current.rotation.x = swing;
      if (legR.current) legR.current.rotation.x = -swing;
      // World-2 MOTION-FIX diag (?diag=1 only -- no-ops otherwise, see
      // hq-motion-diag.ts's own header): alert pacing returns early, so it
      // needs its own record call rather than falling through to the shared
      // one below.
      recordAgentSample({ id: laneSeed, x: g.position.x, y: g.position.y, z: g.position.z, clipSpeed: CLIP_TABLE.alert.speed });
      return;
    }

    // Consume a queued walk (see the effect above) -- the ONLY way `phase`
    // ever leaves "resting" now. reducedMotion discards it silently rather
    // than animating (matches Courier.tsx/HandoffCourier.tsx's own
    // reducedMotion handling).
    if (pendingWalk.current) {
      if (reducedMotion) {
        pendingWalk.current = null;
        eventWalkPending.current = false;
      } else if (phase.current === "resting") {
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
        eventWalkPending.current = false;
        const startPhase = pendingWalk.current === "arrival" ? "arriving" : "toHub";
        phase.current = startPhase;
        phaseStart.current = t;
        pendingWalk.current = null;
        setWalking(true);
        // World-2 MOTION-FIX: distance-based duration + facing, computed
        // ONCE here at walk-start (see walkLegDuration/walkFacing's own
        // comment by their ref declarations above) -- "arriving" is
        // hub->home; every other kind starts toHub, home->(purposeful
        // target or approach).
        const legFrom = startPhase === "arriving" ? hub : home;
        const legTo = startPhase === "arriving"
          ? home
          : (activeWalkKind.current === "purposeful" && activeTarget.current ? activeTarget.current : approach);
        const dist = Math.hypot(legTo[0] - legFrom[0], legTo[2] - legFrom[2]);
        walkLegDuration.current = Math.max(MIN_WALK_LEG_S, dist / WALK_SPEED);
        walkFacing.current = Math.atan2(legTo[0] - legFrom[0], legTo[2] - legFrom[2]);
      }
    }
    const walkTarget = activeWalkKind.current === "purposeful" && activeTarget.current ? activeTarget.current : approach;

    if (phase.current === "arriving") {
      // One-way hub -> home (a persona that just fired, walking in from the
      // manager and sitting down to work) -- ends in "resting", never
      // returns to the hub the way a roundtrip does.
      const p = easedWalkProgress(t - phaseStart.current, walkLegDuration.current, WALK_EASE_S);
      g.rotation.y = walkFacing.current; // "turn before moving" -- see the ref's own comment
      g.position.set(
        hub[0] + (home[0] - hub[0]) * p,
        home[1],
        hub[2] + (home[2] - hub[2]) * p,
      );
      if (p >= 1) { phase.current = "resting"; setWalking(false); }
    } else if (phase.current === "toHub") {
      const p = easedWalkProgress(t - phaseStart.current, walkLegDuration.current, WALK_EASE_S);
      g.rotation.y = walkFacing.current;
      g.position.set(
        home[0] + (walkTarget[0] - home[0]) * p,
        home[1],
        home[2] + (walkTarget[2] - home[2]) * p,
      );
      if (p >= 1) {
        phase.current = "atHub";
        phaseStart.current = t;
        // All-hands stand: "idle clip" per the spec -- drop the ultra
        // tier's `walking` animState flag for the duration of the ring
        // stand, restored when it ends (see the atHub branch below).
        if (activeWalkKind.current === "allhands") setWalking(false);
      }
    } else if (phase.current === "atHub") {
      g.position.set(...walkTarget);
      // All-hands stand: face the core precisely (spec: "facing core") --
      // roundtrip's brief 1.5s touch never bothered with facing, but a
      // 60s stand reads wrong looking anywhere else. Same atan2(dx,dz)
      // convention as `greeterFacingYaw` above. A "purposeful" stop (item
      // 2b) faces its own destination point the SAME way -- reading a card
      // wall or filing at the core looks wrong facing some other direction.
      if (activeWalkKind.current === "allhands") {
        g.rotation.y = Math.atan2(hub[0] - approach[0], hub[2] - approach[2]);
      } else if (activeWalkKind.current === "purposeful") {
        g.rotation.y = Math.atan2(hub[0] - walkTarget[0], hub[2] - walkTarget[2]);
      }
      const pauseSeconds = activeWalkKind.current === "allhands" ? ALLHANDS_HUB_PAUSE : activeWalkKind.current === "purposeful" ? PURPOSEFUL_PAUSE : HUB_PAUSE;
      if (t - phaseStart.current >= pauseSeconds) {
        phase.current = "toHome";
        phaseStart.current = t;
        // World-2 MOTION-FIX: return leg -- same distance as toHub (computed
        // once at walk-start above, walkLegDuration is unchanged), reversed
        // facing ("turn before moving" for the trip home too).
        walkFacing.current = Math.atan2(home[0] - walkTarget[0], home[2] - walkTarget[2]);
        if (activeWalkKind.current === "allhands") setWalking(true);
      }
    } else if (phase.current === "toHome") {
      const p = easedWalkProgress(t - phaseStart.current, walkLegDuration.current, WALK_EASE_S);
      g.rotation.y = walkFacing.current;
      g.position.set(
        walkTarget[0] + (home[0] - walkTarget[0]) * p,
        home[1],
        walkTarget[2] + (home[2] - walkTarget[2]) * p,
      );
      if (p >= 1) { phase.current = "resting"; activeTarget.current = null; }
    } else {
      // resting -- bob (working = brisker, idle = slower/shallower)
      const bobAmp = behavior === "working" ? 0.05 : 0.025;
      const bobSpeed = behavior === "working" ? 4 : 1.4;
      g.position.set(home[0], home[1] + Math.sin(t * bobSpeed) * bobAmp, home[2]);
      // World-4 fix (P6, 2026-09-14, J: "the bottom bays show characters not
      // facing their desks"): this branch used to leave `g.rotation.y`
      // whatever the LAST walk phase set it to -- for "working"
      // specifically, that meant NO assignment here at all, so it kept
      // `walkFacing` (set during "arriving"/"toHome", `atan2(home-hub)`,
      // the WALKING direction hub->home) forever. That value is off by
      // exactly Math.PI from "face away from hub, toward the desk", the
      // established convention this file's own alert-phase pacing already
      // uses two branches up (`facingHub + Math.PI`) and GammaCharacter.tsx
      // uses too (`rotationY + Math.PI`) -- confirmed by the formulas
      // themselves, not just a look: `walkFacing = atan2(home-hub)` and
      // `facingHub = atan2(hub-home)` are exact opposites, so
      // `facingHub + PI` (the correct desk-facing value) equals
      // `atan2(home-hub)` PLUS Math.PI, i.e. `walkFacing + Math.PI` -- the
      // one term this branch never added. A seated/idle character now gets
      // a real, per-frame desk-facing base instead of an unset leftover.
      const deskFacing = Math.atan2(hub[0] - home[0], hub[2] - home[2]) + Math.PI;
      if (behavior === "working") {
        if (armL.current) armL.current.rotation.x = Math.sin(t * 10) * 0.35;
        if (armR.current) armR.current.rotation.x = Math.sin(t * 10 + Math.PI) * 0.35;
        g.rotation.y = deskFacing;
      } else if (presenceMode === "greet") {
        // J 2026-09-13: "nearest agent turns to the viewer" on presence ==
        // here -- holds a fixed facing instead of the idle look-around.
        // Scene.tsx picks exactly one static agent for this; everyone else
        // never receives `presenceMode` and is unaffected.
        g.rotation.y = facingYaw ?? 0;
      } else {
        // Slow "look around", now centered on `deskFacing` (was centered on
        // world-absolute 0 -- wrong for every bay/persona whose own
        // rotationY isn't 0, the SAME class of bug as the "working" case
        // above) instead of swaying around a fixed world direction that
        // ignores which way this character's own desk actually faces.
        g.rotation.y = deskFacing + Math.sin(t * 0.3) * 0.5;
      }
    }

    const walking = phase.current === "toHub" || phase.current === "toHome" || phase.current === "arriving";
    if (walking) {
      const swing = Math.sin(t * 8) * 0.5;
      if (legL.current) legL.current.rotation.x = swing;
      if (legR.current) legR.current.rotation.x = -swing;
    } else if (legL.current && legR.current) {
      legL.current.rotation.x = 0;
      legR.current.rotation.x = 0;
    }

    // World-2 MOTION-FIX diag (?diag=1 only -- no-ops otherwise, see
    // hq-motion-diag.ts's own header): every agent's world position + the
    // clip speed KitAgent.tsx would be playing for its current animState,
    // once per throttled tick (20Hz) -- position.set above already
    // finalized this frame's value by this point regardless of which phase
    // branch ran.
    recordAgentSample({ id: laneSeed, x: g.position.x, y: g.position.y, z: g.position.z, clipSpeed: CLIP_TABLE[animState].speed });

    // "Night patrol" dim (J 2026-09-13: presence == away) + Pass C schedule
    // dim (2026-09-13: off-shift persona, only when not genuinely working)
    // -- cuts the visor's own emissive glow, the cheapest possible "quieter
    // right now" tell (no new material, no opacity/blend cost). Whichever
    // reason is stronger wins (Math.min), never double-dimmed.
    const patrolDim = Math.min(presenceMode === "patrol" ? 0.35 : 1, scheduleDim);
    if (visorMat.current) visorMat.current.emissiveIntensity = (1.4 + Math.sin(t * 3) * 0.2) * patrolDim;
  }, 20);

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
    </group>
  );
}

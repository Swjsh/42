"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { useThrottledFrame } from "./useThrottledFrame";
import { makeMatcapTexture, seededRandom } from "./palette";
import { KitAgentBody, type KitAnimState } from "./KitAgent";

export type AgentBehavior = "working" | "idle" | "alert" | "frozen";
export type AgentWalkKind = "roundtrip" | "arrival" | "allhands";
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

const WALK_DURATION = 4.5;
const HUB_PAUSE = 1.5;
const ALLHANDS_HUB_PAUSE = 60;
type WalkPhase = "resting" | "toHub" | "atHub" | "toHome" | "arriving";

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
  laneSeed, home, hub, behavior, accentColor, reducedMotion, walkEventKey, walkKind, allHandsEventKey, presenceMode, facingYaw,
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
  const animState: KitAnimState = behavior === "alert" ? "alert" : walking ? "walking" : behavior === "working" ? "resting-working" : "resting-idle";
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
  const paceOffset = useRef(0);
  // Which AgentWalkKind is actually IN PROGRESS (set when a queued walk
  // starts, read by the atHub branch below to pick its pause duration/
  // facing/animState) -- distinct from the `walkKind` PROP, which for
  // personas is permanently "arrival" (their own individual trigger) even
  // while an "allhands" walk (a completely separate trigger) is what's
  // actually playing.
  const activeWalkKind = useRef<AgentWalkKind>("roundtrip");

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

    if (behavior === "alert") {
      // Pace back and forth across the module -- local X sway, no scheduled
      // hub trip while alert (it's busy).
      paceOffset.current = Math.sin(t * 0.9) * 0.9;
      g.position.set(home[0] + paceOffset.current, home[1], home[2]);
      const swing = Math.sin(t * 9) * 0.5;
      if (legL.current) legL.current.rotation.x = swing;
      if (legR.current) legR.current.rotation.x = -swing;
      return;
    }

    // Consume a queued walk (see the effect above) -- the ONLY way `phase`
    // ever leaves "resting" now. reducedMotion discards it silently rather
    // than animating (matches Courier.tsx/HandoffCourier.tsx's own
    // reducedMotion handling).
    if (pendingWalk.current) {
      if (reducedMotion) {
        pendingWalk.current = null;
      } else if (phase.current === "resting") {
        activeWalkKind.current = pendingWalk.current;
        phase.current = pendingWalk.current === "arrival" ? "arriving" : "toHub";
        phaseStart.current = t;
        pendingWalk.current = null;
        setWalking(true);
      }
    }

    if (phase.current === "arriving") {
      // One-way hub -> home (a persona that just fired, walking in from the
      // manager and sitting down to work) -- ends in "resting", never
      // returns to the hub the way a roundtrip does.
      const p = Math.min(1, (t - phaseStart.current) / WALK_DURATION);
      g.position.set(
        hub[0] + (home[0] - hub[0]) * p,
        home[1],
        hub[2] + (home[2] - hub[2]) * p,
      );
      if (p >= 1) { phase.current = "resting"; setWalking(false); }
    } else if (phase.current === "toHub") {
      const p = Math.min(1, (t - phaseStart.current) / WALK_DURATION);
      g.position.set(
        home[0] + (approach[0] - home[0]) * p,
        home[1],
        home[2] + (approach[2] - home[2]) * p,
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
      g.position.set(...approach);
      // All-hands stand: face the core precisely (spec: "facing core") --
      // roundtrip's brief 1.5s touch never bothered with facing, but a
      // 60s stand reads wrong looking anywhere else. Same atan2(dx,dz)
      // convention as `greeterFacingYaw` above.
      if (activeWalkKind.current === "allhands") {
        g.rotation.y = Math.atan2(hub[0] - approach[0], hub[2] - approach[2]);
      }
      const pauseSeconds = activeWalkKind.current === "allhands" ? ALLHANDS_HUB_PAUSE : HUB_PAUSE;
      if (t - phaseStart.current >= pauseSeconds) {
        phase.current = "toHome";
        phaseStart.current = t;
        if (activeWalkKind.current === "allhands") setWalking(true);
      }
    } else if (phase.current === "toHome") {
      const p = Math.min(1, (t - phaseStart.current) / WALK_DURATION);
      g.position.set(
        approach[0] + (home[0] - approach[0]) * p,
        home[1],
        approach[2] + (home[2] - approach[2]) * p,
      );
      if (p >= 1) { phase.current = "resting"; }
    } else {
      // resting -- bob (working = brisker, idle = slower/shallower)
      const bobAmp = behavior === "working" ? 0.05 : 0.025;
      const bobSpeed = behavior === "working" ? 4 : 1.4;
      g.position.set(home[0], home[1] + Math.sin(t * bobSpeed) * bobAmp, home[2]);
      if (behavior === "working") {
        if (armL.current) armL.current.rotation.x = Math.sin(t * 10) * 0.35;
        if (armR.current) armR.current.rotation.x = Math.sin(t * 10 + Math.PI) * 0.35;
      } else if (presenceMode === "greet") {
        // J 2026-09-13: "nearest agent turns to the viewer" on presence ==
        // here -- holds a fixed facing instead of the idle look-around.
        // Scene.tsx picks exactly one static agent for this; everyone else
        // never receives `presenceMode` and is unaffected.
        g.rotation.y = facingYaw ?? 0;
      } else {
        g.rotation.y = Math.sin(t * 0.3) * 0.5; // slow "look around"
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

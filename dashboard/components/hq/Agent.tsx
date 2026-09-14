"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import { useThrottledFrame } from "./useThrottledFrame";
import { makeMatcapTexture, seededRandom } from "./palette";
import { KitAgentBody, type KitAnimState } from "./KitAgent";

export type AgentBehavior = "working" | "idle" | "alert" | "frozen";
export type AgentWalkKind = "roundtrip" | "arrival";
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
   * manager and sitting down). Default "roundtrip". */
  walkKind?: AgentWalkKind;
  /** J 2026-09-13 ("nearest agent turns to the viewer / night-patrol dim"
   * on presence flipping): "greet" holds the resting-state facing at
   * `facingYaw` instead of the idle look-around; "patrol" dims the visor.
   * Only ever set on ONE statically-chosen agent (Scene.tsx picks the lane
   * nearest the fixed camera) -- undefined everywhere else, zero cost. */
  presenceMode?: AgentPresenceMode;
  facingYaw?: number;
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
  laneSeed, home, hub, behavior, accentColor, reducedMotion, walkEventKey, walkKind, presenceMode, facingYaw,
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
  const patrolDim = presenceMode === "patrol" ? 0.35 : 1;

  const matcap = useMemo(() => makeMatcapTexture(), []);
  const rng = useMemo(() => seededRandom(laneSeed), [laneSeed]);
  const approach = useMemo(() => {
    const angle = rng() * Math.PI * 2;
    return [hub[0] + Math.cos(angle) * 1.8, home[1], hub[2] + Math.sin(angle) * 1.8] as [number, number, number];
  }, [rng, hub, home]);

  const phase = useRef<WalkPhase>("resting");
  const phaseStart = useRef(0);
  const paceOffset = useRef(0);

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
      if (p >= 1) { phase.current = "atHub"; phaseStart.current = t; }
    } else if (phase.current === "atHub") {
      g.position.set(...approach);
      if (t - phaseStart.current >= HUB_PAUSE) { phase.current = "toHome"; phaseStart.current = t; }
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

    // "Night patrol" dim (J 2026-09-13: presence == away) -- cuts the
    // visor's own emissive glow, the cheapest possible "quieter without J
    // here" tell (no new material, no opacity/blend cost).
    const patrolDim = presenceMode === "patrol" ? 0.35 : 1;
    if (visorMat.current) visorMat.current.emissiveIntensity = (1.4 + Math.sin(t * 3) * 0.2) * patrolDim;
  }, 20);

  return (
    <group ref={group}>
      {/* Legs/body/arms/backpack -- procedural matcap (HQ v4 look pass,
          2026-09-13): one texture lookup replaces Lambert's per-fragment
          N.L at the same cost class, giving these little bots actual
          dimensional shading instead of flat color blocks. The visor below
          stays Lambert+emissive unchanged -- it's meant to glow, not be
          shaded by a matcap. */}
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
    </group>
  );
}

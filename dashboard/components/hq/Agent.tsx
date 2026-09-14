"use client";

import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { useThrottledFrame } from "./useThrottledFrame";
import { seededRandom } from "./palette";

export type AgentBehavior = "working" | "idle" | "alert" | "frozen";

interface AgentProps {
  laneSeed: string;
  home: [number, number, number];
  hub: [number, number, number];
  behavior: AgentBehavior;
  accentColor: string;
  reducedMotion: boolean;
}

const WALK_DURATION = 4.5;
const HUB_PAUSE = 1.5;
type WalkPhase = "resting" | "toHub" | "atHub" | "toHome";

/**
 * One little procedural bot: capsule body, visor sphere (doubles as the
 * head-lamp -- emissive, no extra mesh needed), backpack box, two swinging
 * leg cylinders. Behavior state machine per the HQ-visuals brief: working
 * (bob + typing arms) / idle (slow breathing) / alert (paces its module, red
 * "!" overhead) / frozen (gaming mode -- no motion at all). Every 20-60s
 * (seeded per lane, picked ONLY at schedule time -- never Math.random inside
 * useFrame) a working/idle agent walks to the hub and back, the "running
 * around" J asked for.
 */
export default function Agent({ laneSeed, home, hub, behavior, accentColor, reducedMotion }: AgentProps) {
  const group = useRef<THREE.Group>(null);
  const legL = useRef<THREE.Mesh>(null);
  const legR = useRef<THREE.Mesh>(null);
  const armL = useRef<THREE.Mesh>(null);
  const armR = useRef<THREE.Mesh>(null);
  const visorMat = useRef<THREE.MeshLambertMaterial>(null);

  const rng = useMemo(() => seededRandom(laneSeed), [laneSeed]);
  const approach = useMemo(() => {
    const angle = rng() * Math.PI * 2;
    return [hub[0] + Math.cos(angle) * 1.8, home[1], hub[2] + Math.sin(angle) * 1.8] as [number, number, number];
  }, [rng, hub, home]);

  const phase = useRef<WalkPhase>("resting");
  const phaseStart = useRef(0);
  // `useMemo` (not `useRef(20 + rng() * 40)` directly) so rng() is called
  // exactly once: a hook's initial-value ARGUMENT is still evaluated on
  // every render even when the hook ignores it after mount, which would
  // otherwise advance the PRNG stream on every poll for no reason.
  const initialWalkDelay = useMemo(() => 20 + rng() * 40, [rng]);
  const nextWalkAt = useRef(initialWalkDelay);
  const paceOffset = useRef(0);

  // Set initial position once -- everything after this is imperative ref
  // mutation, never React state, so an agent's motion never triggers a
  // React re-render of the tree above it.
  useEffect(() => {
    group.current?.position.set(...home);
  }, [home]);

  useThrottledFrame((t) => {
    if (!group.current) return;
    const g = group.current;

    if (behavior === "frozen") return; // hold whatever pose it already had

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

    // working/idle: bob in place, and occasionally walk to the hub and back.
    if (!reducedMotion && phase.current === "resting" && t >= nextWalkAt.current) {
      phase.current = "toHub";
      phaseStart.current = t;
    }

    if (phase.current === "toHub") {
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
      if (p >= 1) {
        phase.current = "resting";
        nextWalkAt.current = t + 20 + rng() * 40;
      }
    } else {
      // resting -- bob (working = brisker, idle = slower/shallower)
      const bobAmp = behavior === "working" ? 0.05 : 0.025;
      const bobSpeed = behavior === "working" ? 4 : 1.4;
      g.position.set(home[0], home[1] + Math.sin(t * bobSpeed) * bobAmp, home[2]);
      if (behavior === "working") {
        if (armL.current) armL.current.rotation.x = Math.sin(t * 10) * 0.35;
        if (armR.current) armR.current.rotation.x = Math.sin(t * 10 + Math.PI) * 0.35;
      } else {
        g.rotation.y = Math.sin(t * 0.3) * 0.5; // slow "look around"
      }
    }

    const walking = phase.current === "toHub" || phase.current === "toHome";
    if (walking) {
      const swing = Math.sin(t * 8) * 0.5;
      if (legL.current) legL.current.rotation.x = swing;
      if (legR.current) legR.current.rotation.x = -swing;
    } else if (legL.current && legR.current) {
      legL.current.rotation.x = 0;
      legR.current.rotation.x = 0;
    }

    if (visorMat.current) visorMat.current.emissiveIntensity = 1.4 + Math.sin(t * 3) * 0.2;
  }, 20);

  return (
    <group ref={group}>
      {/* Legs -- Lambert everywhere below (cheap N.L diffuse, no PBR sampling
          -- the real TV's Mali-G31 is fragment-bound and hates per-pixel
          lights, so Standard's roughness/metalness terms are pure waste
          here). The alert "!" indicator moved to the module's own label
          (StationModule.tsx) instead of a second floating Html per agent --
          keeps the page's total Html overlay count well under budget. */}
      <mesh ref={legL} position={[-0.09, 0.18, 0]}>
        <cylinderGeometry args={[0.045, 0.045, 0.32, 6]} />
        <meshLambertMaterial color="#1b2436" />
      </mesh>
      <mesh ref={legR} position={[0.09, 0.18, 0]}>
        <cylinderGeometry args={[0.045, 0.045, 0.32, 6]} />
        <meshLambertMaterial color="#1b2436" />
      </mesh>
      {/* Body (capsule) */}
      <mesh position={[0, 0.5, 0]}>
        <capsuleGeometry args={[0.14, 0.32, 4, 8]} />
        <meshLambertMaterial color="#232d44" />
      </mesh>
      {/* Arms */}
      <mesh ref={armL} position={[-0.19, 0.55, 0]}>
        <cylinderGeometry args={[0.035, 0.035, 0.28, 6]} />
        <meshLambertMaterial color="#232d44" />
      </mesh>
      <mesh ref={armR} position={[0.19, 0.55, 0]}>
        <cylinderGeometry args={[0.035, 0.035, 0.28, 6]} />
        <meshLambertMaterial color="#232d44" />
      </mesh>
      {/* Backpack */}
      <mesh position={[0, 0.5, -0.13]}>
        <boxGeometry args={[0.16, 0.22, 0.08]} />
        <meshLambertMaterial color="#141b2e" />
      </mesh>
      {/* Visor / head-lamp */}
      <mesh position={[0, 0.78, 0.09]}>
        <sphereGeometry args={[0.1, 10, 8]} />
        <meshLambertMaterial ref={visorMat} color={accentColor} emissive={accentColor} emissiveIntensity={1.4} toneMapped={false} />
      </mesh>
    </group>
  );
}

"use client";

import { useEffect, useMemo, useRef } from "react";
import { useGLTF, useAnimations } from "@react-three/drei";
import * as THREE from "three";
import { clone as cloneSkeleton } from "three/examples/jsm/utils/SkeletonUtils.js";
import {
  KIT_PATHS, CHARACTER_BODY_IDS, CHARACTER_RAW_HEIGHT, characterScale,
  pickCharacterBody, tintObjectMaterials, type CharacterBodyId,
} from "./SetKit";

// ─── HQ kit rebuild (2026-09-13) -- real rigged Kenney Mini Characters ──────
// replacing Agent.tsx's procedural capsule/visor body. ULTRA TIER ONLY (see
// Agent.tsx's own tier branch -- the TV tier keeps the existing procedural
// body unchanged). Agent.tsx still owns ALL position/walk-phase state
// (unchanged) and now also derives a coarse animation-state that drives
// which baked clip plays here -- see the CLIP_TABLE export below, which
// doubles as this file's own documentation of the event->clip mapping.

export type KitAnimState = "resting-idle" | "resting-working" | "walking" | "alert" | "thinking";

/** Event -> clip mapping (also quoted verbatim in the final task report).
 * Every clip name is verified present on all 3 bodies via manifest.json's
 * own per-character animation list -- no per-body existence guard needed
 * ("interact-right" confirmed present on character-male-b, the body Gamma
 * uses, by parsing the GLB's own JSON chunk this session -- not assumed
 * from the pack's generic marketing copy). `thinking` (Pass B, 2026-09-13):
 * Gamma's own state when brainVitals.gpu.util_pct > 30 -- the kit's
 * "interact" gesture reads as "working at the console" better than
 * `sit`+`resting-working`'s arm-typing loop (which GammaCharacter.tsx
 * doesn't use -- Gamma isn't a Kenney character with typing arms, she gets
 * the pack's own gesture clip instead). */
export const CLIP_TABLE: Record<KitAnimState, { clip: string; speed: number }> = {
  "resting-idle": { clip: "sit", speed: 0.7 },
  "resting-working": { clip: "sit", speed: 1.15 },
  walking: { clip: "walk", speed: 1.0 },
  alert: { clip: "walk", speed: 1.6 },
  thinking: { clip: "interact-right", speed: 0.8 },
};

interface KitAgentBodyProps {
  /** Any stable per-instance string (lane name, persona name) -- deterministically
   * picks one of the 3 bundled bodies, same convention as palette.ts#seededRandom. */
  laneSeed: string;
  animState: KitAnimState;
  /** Health/status color. Kept OFF the body's own atlas material by default
   * (a real character should read as a person, not a solid-color mannequin
   * -- see HQ-SCENE-PLAN.md) and instead drives a small head-mounted
   * emissive bead, the direct functional replacement for the old procedural
   * Agent's glowing visor sphere. A faint (12%) body tint is layered too --
   * enough to feel "branded" without erasing the kit's own coloring. */
  accentColor: string;
  /** "Night patrol" dim (Scene.tsx's presenceMode=="patrol") -- same role as
   * the old visor's emissiveIntensity dim, applied to the head-beacon here. */
  patrolDim?: number;
  /** gaming mode / hidden tab: freezes the mixer via timeScale=0 (holds
   * whatever pose was already playing) rather than a special clip. */
  frozen?: boolean;
  /** Pass B (2026-09-13): Gamma is a SPECIFIC body ("male-b" per the brief),
   * not whichever one pickCharacterBody's seed hash happens to land on --
   * bypasses that hash entirely when set. Every other caller (lane/persona
   * Agents) omits this and keeps the deterministic-per-seed pick unchanged. */
  forceBodyId?: CharacterBodyId;
}

const HEAD_BEACON_RADIUS = 0.045;

/**
 * One rigged Kenney Mini Character: `useGLTF` (drei caches by path -- the 3
 * bodies are parsed once total, however many of the 14 lane/persona agents
 * end up sharing them) + `SkeletonUtils.clone` per mounted instance (a plain
 * `.clone()` does NOT deep-clone a skinned mesh's skeleton/bone hierarchy --
 * multiple instances would fight over one shared skeleton and animate in
 * lockstep; SkeletonUtils.clone is the standard three.js fix, already used
 * across the r3f ecosystem for exactly this) + `useAnimations` crossfaded to
 * the clip `CLIP_TABLE[animState]` names. `useAnimations` runs its own
 * internal `useFrame(mixer.update)` (confirmed by reading drei's source this
 * session, not assumed) -- `mixer.timeScale` is therefore the correct,
 * minimal lever for both "working looks brisker than idle" (speed from
 * CLIP_TABLE) and "frozen" (timeScale 0, holds the current pose exactly
 * where gaming mode caught it, same intent as the old procedural body's
 * early-return-on-frozen).
 */
export function KitAgentBody({ laneSeed, animState, accentColor, patrolDim = 1, frozen = false, forceBodyId }: KitAgentBodyProps) {
  const bodyId = useMemo(() => forceBodyId ?? pickCharacterBody(laneSeed), [laneSeed, forceBodyId]);
  const path = KIT_PATHS.characters[bodyId];
  // useDraco=false EXPLICITLY -- see SetKit.tsx#KitProp's own comment (same
  // drei default, verified from source, kept off outright).
  const { scene, animations } = useGLTF(path, false);

  // Skinned clone -- one per mounted instance, never re-run unless the
  // source scene reference itself changes (i.e. never, after first load).
  const cloned = useMemo(() => cloneSkeleton(scene), [scene]);
  const { actions, mixer } = useAnimations(animations, cloned);

  const beaconMat = useRef<THREE.MeshStandardMaterial>(null);
  const scale = characterScale(bodyId);
  const headY = CHARACTER_RAW_HEIGHT[bodyId] * 0.95;

  // Faint body tint, applied once per (cloned, accentColor) pair -- see
  // tintObjectMaterials's own comment on why this stays subtle.
  useEffect(() => {
    const clonedMaterials = tintObjectMaterials(cloned, accentColor, 0.12);
    return () => clonedMaterials.forEach((m) => m.dispose());
  }, [cloned, accentColor]);

  // Crossfade to the target clip whenever animState changes.
  const currentAction = useRef<THREE.AnimationAction | null>(null);
  useEffect(() => {
    const { clip } = CLIP_TABLE[animState];
    const next = actions[clip] ?? actions.idle ?? null;
    if (!next || next === currentAction.current) return;
    next.reset().fadeIn(0.3).play();
    currentAction.current?.fadeOut(0.3);
    currentAction.current = next;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [animState, actions]);

  // Speed/freeze lever -- see the component doc comment above for why
  // `mixer.timeScale` (not per-action pause) is the correct mechanism.
  useEffect(() => {
    mixer.timeScale = frozen ? 0 : CLIP_TABLE[animState].speed;
  }, [mixer, frozen, animState]);

  useEffect(() => {
    if (beaconMat.current) beaconMat.current.emissiveIntensity = 1.4 * patrolDim;
  }, [patrolDim]);

  return (
    <group scale={scale}>
      <primitive object={cloned} />
      {/* Head-mounted status beacon -- the old visor's functional
          replacement (see the prop doc comment). Position is a STATIC
          fraction of the body's own raw bounding height, not a bone lookup
          -- close enough at rest/sit/walk (the head stays near the bbox top
          through all three baked clips), and trivially nudgeable. */}
      <mesh position={[0, headY, 0.06]}>
        <sphereGeometry args={[HEAD_BEACON_RADIUS, 10, 8]} />
        <meshStandardMaterial
          ref={beaconMat}
          color={accentColor}
          emissive={accentColor}
          emissiveIntensity={1.4 * patrolDim}
          toneMapped={false}
        />
      </mesh>
    </group>
  );
}

CHARACTER_BODY_IDS.forEach((id) => useGLTF.preload(KIT_PATHS.characters[id], false));

export type { CharacterBodyId };

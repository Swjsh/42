"use client";

import { useEffect, useMemo, useRef } from "react";
import { useGLTF, useAnimations } from "@react-three/drei";
import * as THREE from "three";
import { clone as cloneSkeleton } from "three/examples/jsm/utils/SkeletonUtils.js";
import {
  KIT_PATHS, CHARACTER_BODY_IDS, CHARACTER_RAW_HEIGHT, CHARACTER_TARGET_HEIGHT, characterScale,
  pickCharacterBody, tintObjectMaterials, type CharacterBodyId,
} from "./SetKit";

// ─── HQ kit rebuild (2026-09-13) -- real rigged Kenney character bodies ─────
// replacing Agent.tsx's procedural capsule/visor body. ULTRA TIER ONLY (see
// Agent.tsx's own tier branch -- the TV tier keeps the existing procedural
// body unchanged). Agent.tsx still owns ALL position/walk-phase state
// (unchanged) and now also derives a coarse animation-state that drives
// which baked clip plays here -- see the CLIP_TABLE export below, which
// doubles as this file's own documentation of the event->clip mapping.
//
// BLOCKY-CHARACTERS swap (2026-09-15, J: "I don't like the current ones" --
// Mini Characters' thin straight-arm rig read as "walking sticks"). Body
// source is now Kenney's "Blocky Characters" (SetKit.tsx#CHARACTER_PACK) --
// same useGLTF + SkeletonUtils.clone + useAnimations pipeline below, no
// pipeline change needed. Every CLIP_TABLE name this file references
// (sit/emote-no/emote-yes/interact-right/interact-left/walk/idle) was
// re-verified present on the new pack by parsing each chosen GLB's own JSON
// chunk this session (all 4 bodies share one identical animation list and
// rig -- Kenney ships one shared skeleton across every "Blocky Characters"
// letter, only the texture atlas differs) -- zero substitute clips needed,
// unlike the Mini Characters pack's seated-pose gaps documented below.

export type KitAnimState =
  | "resting-idle" | "resting-idle-look" | "resting-idle-nod"
  | "resting-working" | "resting-working-type" | "resting-working-type-alt"
  | "walking" | "alert" | "alert-pause" | "thinking";

/** Event -> clip mapping (also quoted verbatim in the final task report).
 * Every clip name is verified present on all 4 BLOCKY-CHARACTERS bodies
 * (2026-09-15 pass) via a direct per-GLB JSON-chunk parse -- no per-body
 * existence guard needed ("interact-right" confirmed present on
 * character-b, the body Gamma uses, same way). `thinking` (Pass B, 2026-09-13):
 * Gamma's own state when brainVitals.gpu.util_pct > 30 -- the kit's
 * "interact" gesture reads as "working at the console" better than
 * `sit`+`resting-working`'s arm-typing loop (which GammaCharacter.tsx
 * doesn't use -- Gamma isn't a Kenney character with typing arms, she gets
 * the pack's own gesture clip instead).
 *
 * LIVE-1 item 2a (2026-09-14, J: "it still a 'Dead' world" -- seated
 * employees must never freeze): the (retired) Mini Characters pack's full
 * 31-clip list (BLOCKY-CHARACTERS' own list is 27 clips, manifest.json)
 * has exactly one literal seated pose ("sit") -- no "type"/"stretch" clip
 * exists to seat-lock onto, so the -look/-nod/-type/-type-alt variants below
 * are the closest honest substitutes from the REAL clip set rather than a
 * fabricated animation name: "emote-no"/"emote-yes" (head shake/nod) read as
 * "checking something / acknowledging" for the idle pool, "interact-right"/
 * "interact-left" (the same gesture `thinking` above already uses, mirrored)
 * read as "typing at the console" for the working pool. Agent.tsx cycles
 * IDLE_VARIANTS/WORKING_VARIANTS on its own per-instance 8-20s timer.
 */

// ─── World-2 MOTION-FIX (2026-09-14, J: "the people are running like 100mph"
// -- Agent.tsx's old WALK_DURATION=4.5s covered EVERY walk regardless of
// distance; a ~14-unit hub trip at 4.5s is ~3 u/s, roughly 6 body-heights/s
// for this character's own on-screen height -- a dead sprint, not a walk).
// Real walking pace, DERIVED from SetKit.tsx's own CHARACTER_TARGET_HEIGHT
// (never a hand-picked magic number) so a future height-target change keeps
// this correct automatically: an average adult walks ~1.4 m/s. Deliberately
// NOT also scaled by CHARACTER_SCALE (self-correction, this session -- the
// first version of this constant did, landing at ~1.8 u/s, over this file's
// own proof bar): SetKit.tsx's own comment on CHARACTER_SCALE calls it a
// purely COSMETIC legibility bump ("closer default camera... characters
// reading small... 1.25x lands every body at 2.25 world units, legible...")
// -- it does not re-scale the desks/hub/corridors (FURNITURE_SCALE,
// ARCHITECTURE's 0.45x/0.5x are independent constants), so a character
// walking FASTER just because it was drawn bigger would cover the
// FIXED-SCALE room unrealistically fast relative to that room, even while
// looking "normal" relative to its own inflated body. CHARACTER_TARGET_HEIGHT
// (1.8, "this task's own spec" per SetKit.tsx) is the character's real,
// story-accurate height -- an ordinary adult -- so pace is keyed to that,
// matching the scene's own established "1 world unit ~= 1m" convention
// (this file's neighbor ALERT_PACE_SPEED comment) directly. Single source
// of truth for BOTH Agent.tsx's translation-duration math AND this file's
// own CLIP_TABLE walk/alert speeds below -- "the clip speed follows the
// translation speed, never the other way round" (spec). Exported (not
// Agent-local) specifically to avoid a circular Agent.tsx<->KitAgent.tsx
// import -- Agent.tsx already imports FROM this file, never the reverse.
const REAL_HUMAN_WALK_MPS = 1.4;
const REAL_HUMAN_HEIGHT_M = 1.8; // CHARACTER_TARGET_HEIGHT's own real-world reference
// MOTION-2 (2026-09-14, J 16:50 ET: "they're still moving a little fast...
// cut it in half speed-wise"): a deliberate STYLISTIC slowdown from the real-
// world-derived pace above, kept as its OWN named multiplier rather than
// folded into REAL_HUMAN_WALK_MPS -- that constant stays an honest "average
// adult walks 1.4 m/s" fact (re-usable as-is if anything else ever needs the
// true figure); HQ_PACE_FACTOR is the one place J's "too fast for this many
// agents on one small floor" judgment call lives.
const HQ_PACE_FACTOR = 0.5;
export const WALK_SPEED = (REAL_HUMAN_WALK_MPS * CHARACTER_TARGET_HEIGHT * HQ_PACE_FACTOR) / REAL_HUMAN_HEIGHT_M; // u/s -- 0.7 exactly while CHARACTER_TARGET_HEIGHT stays 1.8

// World-2 item 5's alert pace, a real BRISK WALK -- comfortably under
// WALK_SPEED so "hurrying to the door" still reads as urgent walking, never
// running. MOTION-2: 0.9 -> 0.5 (same HQ_PACE_FACTOR-driven halving as
// WALK_SPEED above, applied directly since this was already a bare tuned
// literal, not a derived formula).
export const ALERT_PACE_SPEED = 0.5; // u/s

// Kenney Mini Characters' "walk" clip is an in-place loop -- Agent.tsx has
// always driven translation itself via g.position, independent of the GLTF,
// and manifest.json documents no root-motion translation track on this
// clip -- so there is no baked stride to measure programmatically. This is
// a TUNED-AND-VISUALLY-VERIFIED estimate (Browser-pane check against the
// real WALK_SPEED above, this session) of the pace the "walk" clip's own
// foot-cycle rate implies at mixer speed 1.0, in the SAME honest-estimate
// convention this file's neighbor ALERT_PACE_SPEED comment used to use.
// Not measured ground truth -- re-tune here if a future body swap changes
// the baked clip.
// Exported (MOTION-2): Agent.tsx's own TV-tier procedural leg-swing needs
// this SAME reference pace for its own cadence formula (see clipCadenceRatio
// below) -- one shared baseline instead of two files each hand-tuning
// against a different assumed "native" speed.
export const NATIVE_WALK_CLIP_MPS = 1.4;

// MOTION-2 (2026-09-14, J: "cut it in half speed-wise... a little bit of
// LOGIC to their movement"): halving WALK_SPEED/ALERT_PACE_SPEED above and
// naively keeping clip speed = translationSpeed/NATIVE_WALK_CLIP_MPS (pure
// linear, the ORIGINAL World-2 MOTION-FIX formula) would ALSO halve the walk
// clip's own leg-cadence -- which reads as the exact SAME full-length stride
// played back in slow motion, not a genuinely slower/shorter-strided walk. A
// real human walking slower shortens STRIDE more than it slows leg-swing
// TEMPO (gait research's "dynamic similarity" finding: cadence scales
// roughly with sqrt(speed), stride length absorbs most of the rest). This
// rig has no root motion/foot IK to get a literal ground-truth stride from
// (Agent.tsx drives translation externally, independent of the baked clip --
// see this file's own top-of-file comment), so sqrt is the honest, general
// fix: it keeps cadence closer to natural at low translation speeds instead
// of collapsing 1:1 with it, while still returning EXACTLY 1.0 (today's
// already-tuned native pace, zero change) when translationSpeed equals
// nativeClipMps. Exported so Agent.tsx's procedural TV-tier leg-swing uses
// the identical formula (see its own NATIVE_SWING_HZ comment) -- one
// consistent mental model for "how fast should limbs move at this
// translation speed" across both tiers, never two independently-tuned ones.
export function clipCadenceRatio(translationSpeed: number, nativeClipMps: number): number {
  return Math.sqrt(translationSpeed / nativeClipMps);
}

export const CLIP_TABLE: Record<KitAnimState, { clip: string; speed: number }> = {
  "resting-idle": { clip: "sit", speed: 0.7 },
  "resting-idle-look": { clip: "emote-no", speed: 0.8 },
  "resting-idle-nod": { clip: "emote-yes", speed: 0.8 },
  "resting-working": { clip: "sit", speed: 1.15 },
  "resting-working-type": { clip: "interact-right", speed: 1.0 },
  "resting-working-type-alt": { clip: "interact-left", speed: 1.0 },
  // MOTION-2: clipCadenceRatio (sqrt-based, see its own comment above)
  // replaces the ORIGINAL World-2 MOTION-FIX's pure-linear
  // speed/nativeClipMps ratio -- still derived from WALK_SPEED/
  // ALERT_PACE_SPEED (never a hardcoded multiplier), just no longer
  // proportional 1:1, so a slow walk reads as an unhurried walk instead of
  // the native-pace clip in slow motion.
  walking: { clip: "walk", speed: clipCadenceRatio(WALK_SPEED, NATIVE_WALK_CLIP_MPS) },
  alert: { clip: "walk", speed: clipCadenceRatio(ALERT_PACE_SPEED, NATIVE_WALK_CLIP_MPS) },
  // World-2 item 5 (2026-09-14): the alert pace's pause at each end
  // (Agent.tsx's own "atDoor"/"atDesk" sub-phases) needs a genuinely
  // STANDING pose, not the walk clip held mid-stride -- "idle" (verified
  // present on all 3 bodies via manifest.json's own per-character animation
  // list, already used as KitAgentBody's own actions-lookup fallback below)
  // is the pack's real standing-idle clip, distinct from "sit" (a SEATED
  // pose, wrong here -- the agent is standing at a door/desk mid-pace, not
  // sitting down).
  "alert-pause": { clip: "idle", speed: 1.0 },
  thinking: { clip: "interact-right", speed: 0.8 },
};

/** Cycled by Agent.tsx's own per-instance timer -- see that file's own
 * comment for why this is a `useState` (not a ref): KitAgentBody's clip
 * crossfade is driven by `animState` CHANGING as a prop, so the index that
 * picks among these must trigger a real re-render, not just per-frame ref
 * bookkeeping. */
export const IDLE_VARIANTS: KitAnimState[] = ["resting-idle", "resting-idle-look", "resting-idle-nod"];
export const WORKING_VARIANTS: KitAnimState[] = ["resting-working", "resting-working-type", "resting-working-type-alt"];

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

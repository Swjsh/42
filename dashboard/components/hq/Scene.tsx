"use client";

import { memo, Suspense, useEffect, useMemo, useRef, useState } from "react";
import { useThree, useFrame } from "@react-three/fiber";
import * as THREE from "three";
import type { HqApiResponse, SectorRow } from "./types";
import type { PersonaState } from "@/lib/personas";
import type { AgentBehavior } from "./Agent";
import Agent from "./Agent";
import BrainCore from "./BrainCore";
import StationModule from "./StationModule";
import PersonaModule from "./PersonaModule";
import HandoffCourier from "./HandoffCourier";
import Corridor from "./Corridor";
import IdeasWall from "./IdeasWall";
import Courier from "./Courier";
import Starfield from "./Starfield";
import SkyDome from "./SkyDome";
import PmremEnvironment from "./PmremEnvironment";
import EffectsStack from "./EffectsStack";
import GammaCharacter from "./GammaCharacter";
import ActivityBubbleLayer, { type ActivityBubbleCandidate } from "./ActivityBubbleLayer";
import { dayNightFactor, freshness01, healthColor, isParkedState, lerp, localToWorld, minutesSinceEvidence, nowEtDayOfWeek, nowEtMinutes, PALETTE, personaStatusColor, rosterEvidenceText, scheduleOnShift, truncateOneLine, type ScreenLine } from "./palette";
import { BAY_DESK_OFFSET_Z, BAY_HALF_DEPTH, BAY_SEAT_LOCAL, CorridorRun, DeskCluster, HubRoom, HUB_WALL_RADIUS } from "./SetKit";

export type HqTier = "ultra" | "tv";

interface SceneProps {
  data: HqApiResponse | undefined;
  reducedMotion: boolean;
  /** Default "tv" (not "ultra"): CanvasRoot.tsx (the existing TV-tier
   * wrapper) never passes this prop -- only the new UltraCanvasRoot.tsx
   * does. Defaulting to the cheap tier is the safe failure direction if
   * this prop is ever omitted. */
  tier?: HqTier;
}

const HUB: [number, number, number] = [0, 0, 0];
// Kit rebuild (2026-09-13, HQ-SCENE-PLAN.md): 9.8 -> 14. The hub is now a
// real `room-large` shell (SetKit.tsx#HubRoom, radius 7.5) that must clear
// PERSONA_RING_RADIUS (6.5, below) with margin, plus a ~4-unit corridor gap
// (2 kit segments) to each bay's own room-small shell (radius 2.7) --
// 7.5+4+2.7=14.2, rounded down slightly.
const RING_RADIUS = 14;
const WALL_POS: [number, number, number] = [0, 3.4, 0];
const BASE_AZIMUTH = Math.atan2(16, 20);
// World pass A (2026-09-13, first real screenshot -- gaming mode ended):
// the proportional 38/19 guess from the kit-rebuild pass under-filled the
// frame (~55% width, matching J's own "reads small" complaint) -- pulled
// in and lowered against the ACTUAL station footprint (outer bay edge at
// RING_RADIUS+BAY_HALF_DEPTH~=16.7): at dist=27/height=11 (distance from
// origin 29.16, elevation angle atan(11/27)=22.1 deg, a "touch lower" than
// the old 26.6 deg per the ask), the station's angular half-extent
// (atan(16.7/29.16)=29.8 deg) fills ~87% of the horizontal half-FOV
// (atan(tan(21deg)*16:9 aspect)=34.35 deg -- three.js fov is VERTICAL, not
// horizontal, confirmed from the PerspectiveCamera docs before doing this
// math) -- verify against the next screenshot, adjust distance first if
// still off (moving the whole camera, not the FOV, keeps perspective
// distortion the same as the already-approved 3/4 diorama look).
// Pass F (2026-09-13, coordinator's real-monitor capture, 1920x1080): the
// old 27/11 pair (tuned blind against a 2560x1440 headless emulation, never
// against the real monitor) left dead sky above the dome and cut the front
// bays off at the bottom -- a camera 11 units up looking at y=1.9 from 27
// away sits at an 18.6deg depression angle (atan((11-1.9)/27)), spending
// the TOP ~6deg of the 50deg vertical FOV on empty sky above the station's
// own ~3-4-unit height. 22/7.5 (paired with DEFAULT_LOOKAT's y 1.9->1.4
// below) drops the depression angle to ~13.6deg and moves 5 units closer --
// a more level, larger-in-frame view. Unverified beyond the coordinator's
// own capture_hq.ps1 re-check this pass; nudge further if still off.
const CAMERA_DIST = 22;
const CAMERA_HEIGHT = 7.5;
// Module-level (stable-forever) constants, never inline array literals, for
// anything fed into a useMemo dependency array below -- an inline `[0, 0,
// -0.15]` literal is a NEW array every render and would silently defeat the
// "geometry stays referentially stable across polls" guarantee this file's
// own comments already call out as load-bearing for the TV kiosk (an
// unstable dependency resets a mid-walk agent back to its desk on every
// single SWR poll, not just on a real data change).
const TV_LANE_SEAT_LOCAL: [number, number, number] = [0, 0, -0.15];
const TV_PERSONA_SEAT_LOCAL: [number, number, number] = [0, 0, -0.1];
// Composition pass (2026-09-13): modules on a wide ARC facing the camera --
// not a full 360deg ring, where half of them would sit hidden behind the
// hub from this fixed 3/4 view. Module position uses cos->x/sin->z while
// the camera's own azimuth uses sin->x/cos->z (see CameraRig below), so the
// module-space angle that faces the camera most directly is (90deg -
// BASE_AZIMUTH) -- the arc is centered there, spanning ~230deg so all 8
// modules stay generally camera-facing and spread across the 16:9 frame.
const ARC_CENTER = Math.PI / 2 - BASE_AZIMUTH;
// Pass F (2026-09-13): tried 200 here to pull Crypto twin/Futures (the
// labels still grazing the roster column after the framing fix alone) back
// toward center -- REVERTED after a real re-capture showed it made that
// SAME collision WORSE, not better (both labels landed further into the
// roster column, not less). The angular-compression reasoning that
// predicted the opposite was wrong about the actual screen-space direction
// -- rather than keep guessing blindly against a 43s-per-iteration real
// capture loop, left at the original 230 and documented as a known
// remaining issue (see StationModule.tsx's label styling / Hud.tsx's
// roster opacity for the mitigations that DID verifiably help) rather than
// risk a third blind swing.
const ARC_SPAN = (230 * Math.PI) / 180;
// Company Mode (2026-09-13): a second, smaller, FIXED ring for the 6
// non-manager personas (item 10 of the spec -- "keep the two rings visually
// distinct"), inside the lane ring's radius 9.8 so it reads as "the org
// chart nested inside the departments it runs." Gamma (Manager), persona[0]
// in collectCompany()'s fixed order, is NOT drawn here -- it becomes
// BrainCore's own manager nameplate/status instead (no 7th desk).
// Layout hygiene fix (2026-09-13, J: "persona nameplates must not sit
// inside the hub plaque area") -- 4.5 put persona Html labels too close to
// BrainCore's own plaques (model plaque at y=1.75, all-hands pulse at
// y=2.4) in screen-space from the fixed 3/4 view. 6.5 is still safely
// inside the lane ring's own radius (9.8, "nested inside the departments
// it runs" per the original design intent) with real clearance from center.
const PERSONA_RING_RADIUS = 6.5;
const COURIER_REST: [number, number, number] = [-1.3, 0, 1.1];

/** health=red -> alert (overrides evidence recency); a parked lane (killed/
 * dormant/dead state or frozen/zombie health) -> idle, never "working" even
 * if its last_evidence_et happens to look recent; otherwise working when
 * evidence is recent, idle when stale. gaming mode overrides everything. */
function deriveBehavior(row: SectorRow, gaming: boolean): AgentBehavior {
  if (gaming) return "frozen";
  if (row.health === "red") return "alert";
  if (isParkedState(row.state, row.health)) return "idle";
  const minutesAgo = minutesSinceEvidence(row.last_evidence_et);
  return minutesAgo !== null && minutesAgo <= 120 ? "working" : "idle";
}

/** Grok-Bot-style "status as motion, not a badge" -- maps PersonaState.status
 * onto Agent.tsx's EXISTING working/idle/alert/frozen states verbatim, no
 * new animation code: GREEN=working (at the desk), YELLOW="acknowledging"
 * (idle's own slow look-around IS a toward-the-hub turn + bob), RED=alert
 * (pacing + the nameplate's own "!" ), IDLE=idle (resting). gaming mode
 * freezes personas exactly like lane agents. */
function derivePersonaBehavior(persona: PersonaState, gaming: boolean): AgentBehavior {
  if (gaming) return "frozen";
  if (persona.status === "RED") return "alert";
  if (persona.status === "GREEN") return "working";
  return "idle";
}

const DEFAULT_LOOKAT = new THREE.Vector3(0, 1.4, 0);
const CAMERA_FOCUS_HOLD_S = 8; // event-triggered ease (red flip, all-hands)
const CAMERA_VIGNETTE_INTERVAL_S = 90; // director vignette cadence (coordinator's own number)
const CAMERA_VIGNETTE_HOLD_S = 6;

interface CameraRigProps {
  reducedMotion: boolean;
  rows: SectorRow[];
  geometry: Array<{ position: [number, number, number] }>;
  briefMtimeMs: number | null;
}

/**
 * Fixed 3/4 elevated view sized to fit the whole ring, with a slow +-12deg
 * azimuth drift so the station feels alive (Pass D, 2026-09-13: widened
 * from +-8deg/period-0.05 -- "cinematic slow orbit" reads as too subtle to
 * notice at the old amplitude). Camera POSITION always stays on this same
 * orbit path -- only the LOOKAT point eases toward something, never the
 * camera's own trajectory, which keeps every focus moment a simple pan/
 * tilt rather than risking a dolly move landing on a bad angle.
 *
 * Two event triggers ease the lookAt toward a real world position for
 * CAMERA_FOCUS_HOLD_S seconds, then release back to the default hub point:
 * (1) a lane's health flipping to red (the SAME real signal
 * useMotionEvents.ts's own ticker line fires off, read independently here
 * per that file's own documented reasoning for why Scene.tsx/CameraRig and
 * the HUD ticker are two decoupled readers of one truth, not two sources);
 * (2) station-brief.md's mtime changing (the same field driving the
 * all-hands event) -- the camera looks to the core exactly when 6 personas
 * are converging on it. When neither is active, a deterministic "director
 * vignette" every CAMERA_VIGNETTE_INTERVAL_S seconds briefly looks at the
 * next bay in rotation (Math.floor(elapsedTime/interval), NEVER
 * Math.random per frame -- this file's own standing rule) so a passive
 * viewer sees different parts of the station over time even with nothing
 * eventful happening. reducedMotion holds everything at the default lookAt
 * with zero drift, matching every other reducedMotion branch in this file.
 */
function CameraRig({ reducedMotion, rows, geometry, briefMtimeMs }: CameraRigProps) {
  const { camera } = useThree();
  const lookAtCurrent = useRef(new THREE.Vector3(0, 1.4, 0));
  const focusGoal = useRef<THREE.Vector3 | null>(null);
  const focusUntil = useRef(0);
  const prevRedLanes = useRef<Set<string>>(new Set());
  const seenBriefMtime = useRef<number | null | undefined>(undefined);
  const lastVignetteBucket = useRef(-1);

  useFrame((state) => {
    const t = state.clock.elapsedTime;

    if (!reducedMotion) {
      // Trigger 1: a lane's health just became red -- look at it.
      const nowRed = new Set(rows.filter((r) => r.health === "red").map((r) => r.lane));
      for (const lane of nowRed) {
        if (!prevRedLanes.current.has(lane)) {
          const idx = rows.findIndex((r) => r.lane === lane);
          const pos = geometry[idx]?.position;
          if (pos) {
            focusGoal.current = new THREE.Vector3(pos[0], 1.6, pos[2]);
            focusUntil.current = t + CAMERA_FOCUS_HOLD_S;
          }
        }
      }
      prevRedLanes.current = nowRed;

      // Trigger 2: a genuinely new station brief -- look at the core
      // (matches the all-hands congregation Agent.tsx/BrainCore.tsx drive
      // off the same field). Seeds silently on the first value seen, same
      // convention as every other event trigger in this codebase.
      if (briefMtimeMs !== null && briefMtimeMs !== undefined) {
        if (seenBriefMtime.current === undefined) {
          seenBriefMtime.current = briefMtimeMs;
        } else if (briefMtimeMs !== seenBriefMtime.current) {
          seenBriefMtime.current = briefMtimeMs;
          focusGoal.current = new THREE.Vector3(0, 2.2, 0);
          focusUntil.current = t + CAMERA_FOCUS_HOLD_S;
        }
      }

      // Director vignette -- only when nothing above has claimed focus.
      if ((!focusGoal.current || t >= focusUntil.current) && rows.length > 0) {
        const bucket = Math.floor(t / CAMERA_VIGNETTE_INTERVAL_S);
        if (bucket !== lastVignetteBucket.current) {
          lastVignetteBucket.current = bucket;
          const idx = bucket % rows.length;
          const pos = geometry[idx]?.position;
          if (pos) {
            focusGoal.current = new THREE.Vector3(pos[0], 1.6, pos[2]);
            focusUntil.current = t + CAMERA_VIGNETTE_HOLD_S;
          }
        }
      }

      if (focusGoal.current && t >= focusUntil.current) focusGoal.current = null;
    }

    const target = reducedMotion ? DEFAULT_LOOKAT : focusGoal.current ?? DEFAULT_LOOKAT;
    lookAtCurrent.current.lerp(target, reducedMotion ? 1 : 0.03);

    const drift = reducedMotion ? 0 : (Math.PI / 15) * Math.sin(t * 0.035);
    const azimuth = BASE_AZIMUTH + drift;
    camera.position.set(Math.sin(azimuth) * CAMERA_DIST, CAMERA_HEIGHT, Math.cos(azimuth) * CAMERA_DIST);
    // Look ABOVE the hub's own center (y=0) so the whole station -- hub,
    // modules, and the elevated ideas wall at y=3.4 -- settles into the
    // lower ~80% of frame, leaving the top clear for the HUD (title/mode
    // badge) instead of the two overlapping (unaffected by focus easing --
    // lookAtCurrent only ever moves a modest distance off this baseline).
    camera.lookAt(lookAtCurrent.current);
  });
  return null;
}

/**
 * Scene composition: hub + one module per sector row arranged on a ring,
 * each connected to the hub by a corridor, plus the ideas wall, the courier,
 * and background dressing. All per-poll derived state (behavior, freshness,
 * angle) is computed here via useMemo/plain calls -- never inside a
 * useFrame -- so a new /api/hq payload only re-renders this tree, it never
 * changes what each child's OWN useFrame throttle is doing mid-animation.
 *
 * World pass A REAL bug fix (2026-09-13): `React.memo` here is the piece
 * that actually MATTERS from page.tsx's `sceneData` stabilization -- making
 * a PROP VALUE referentially stable does nothing on its own; React still
 * re-renders a plain (non-memoized) component every time ITS PARENT
 * re-renders, regardless of whether that specific prop changed. Scene.tsx's
 * parent (HqView in app/hq/page.tsx) re-renders every SWR poll (`data`/
 * `isValidating` from useSWR are fresh objects even when nothing scene-
 * relevant changed) -- without this memo, EVERY StationModule/Agent/
 * Corridor/PersonaModule/BrainCore/EffectsStack/PmremEnvironment/~20
 * <Html> instance in this tree still re-rendered on every single poll,
 * which is what was cascading into the two confirmed drei/postprocessing
 * library bugs this session found and fixed (GodRays, Environment -- both
 * run expensive/stateful effects with NO dependency array, i.e. on every
 * parent render, not just when their own props change). `memo`'s default
 * shallow comparison is correct here specifically BECAUSE `data` is now the
 * stable `sceneData` reference from page.tsx -- comparing this component's
 * OWN three props (`data`, `reducedMotion`, `tier`) by reference is exactly
 * right once the caller guarantees `data` doesn't change unless its content
 * does.
 */
function Scene({ data, reducedMotion, tier = "tv" }: SceneProps) {
  const ultra = tier === "ultra";
  const coreMeshRef = useRef<THREE.Mesh>(null);
  // World pass A REAL bug fix #3 (2026-09-13, root-caused via a capture-
  // phase window 'error' listener injected right after navigation -- the
  // earlier bubble-phase listener never fired, which is WHY this looked
  // "unexplained" earlier this session; something upstream (react-three-
  // fiber's own frameloop error handling) must call stopPropagation/
  // preventDefault during the bubble phase, so only a capture listener
  // sees it). Full stack this time (not the truncated CDP one-liner):
  //   at eo.update (a3cd4a83-...js:227)   <- postprocessing's GodRaysEffect
  //   at eQ.render (a3cd4a83-...js:401)   <- EffectPass.render()
  //   at A.render  (a3cd4a83-...js:45)    <- EffectComposer.render()
  // b79b7286 (r3f) is only the CALLER, exactly as suspected earlier -- the
  // actual throw is `<something>.parent` inside the `postprocessing` npm
  // package's GodRaysEffect.update(), which resolves its "sun" object's
  // world position by walking `.parent`.
  //
  // Root cause: <GodRays sun={coreMeshRef}> resolves the ref via
  // `useMemo(() => new GodRaysEffect(camera, resolveRef(props.sun), props),
  // [camera, props])` (EffectsStack.tsx). `props` is a fresh object every
  // render, so this useMemo reconstructs the whole effect on EVERY render
  // of <GodRays>. On React's very FIRST render of this tree, refs have not
  // committed yet -- `coreMeshRef.current` is unconditionally null during
  // that first render, no matter where GodRays sits in the tree -- so the
  // FIRST GodRaysEffect is always built with a null light source. Before
  // `memo(EffectsStack)` (this session, earlier fix), the next SWR-poll
  // re-render reconstructed the effect again and accidentally "healed" it
  // once `coreMeshRef.current` was populated -- masking this bug as
  // "sometimes clean for a while." After memoizing EffectsStack (to stop
  // that same churn from tearing down GodRays' render targets every poll),
  // nothing ever forces a second render, so the null-sun effect now
  // crashes on every single postprocessing frame, from frame 1, forever --
  // exactly what a fresh tab-10 test showed within ~10-20s of load, no
  // poll needed. Fix: delay EffectsStack's FIRST mount by one render tick
  // via `coreReady`, flipped true in a useEffect (which only runs AFTER
  // the first commit has attached coreMeshRef.current to BrainCore's real
  // mesh) -- so GodRays' actual first-ever render always sees a valid sun.
  const [coreReady, setCoreReady] = useState(false);
  useEffect(() => {
    setCoreReady(true);
  }, []);
  const rows = data?.sectors.rows ?? [];
  const gaming = (data?.mode ?? "work") === "gaming";
  const dimFactor = gaming ? 0.35 : 1;

  // Pass C (2026-09-13): ET day/night mood + persona schedule state. Read
  // fresh on every ACTUAL Scene render (no useMemo) -- Scene is memo()'d
  // and now only re-renders on a genuine data change (every 15-60s in
  // kiosk mode thanks to page.tsx's stable sceneData), which is plenty
  // precise for a mood value that only needs to move gradually over hours;
  // a fresh clock read every poll beats a stale one cached at mount forever.
  const etMinutesNow = nowEtMinutes();
  const dayOfWeekNow = nowEtDayOfWeek();
  const nightFactor = dayNightFactor(etMinutesNow);
  const nightMult = lerp(0.5, 1, nightFactor);

  // Geometry (angle/position per ring slot) is memoized on COUNT alone, not
  // on the `rows` array reference -- `rows` is a fresh array every SWR poll
  // even when its content is identical, and `sectors.py`'s row order is
  // fixed (one row per lane, same order every call). Keeping position/hub
  // referentially stable across polls matters: Agent/StationModule feed
  // them into useMemo/useEffect dependency arrays, and an unstable
  // reference there would reset a mid-walk agent back to its desk on every
  // single poll instead of only reacting to real data changes.
  // Kit rebuild: the ultra tier's real chair sits at BAY_SEAT_LOCAL (inside
  // a <DeskCluster> offset BAY_DESK_OFFSET_Z back from the module's own
  // local origin -- see StationModule.tsx), NOT the old -0.15 tuned for the
  // TV tier's bare procedural desk box. TV tier is unchanged.
  const seatLocal = ultra ? BAY_SEAT_LOCAL : TV_LANE_SEAT_LOCAL;

  const slotCount = Math.max(rows.length, 1);
  const geometry = useMemo(
    () =>
      Array.from({ length: slotCount }, (_, i) => {
        const t = slotCount > 1 ? i / (slotCount - 1) : 0.5;
        const angle = ARC_CENTER - ARC_SPAN / 2 + t * ARC_SPAN;
        const position: [number, number, number] = [Math.cos(angle) * RING_RADIUS, 0, Math.sin(angle) * RING_RADIUS];
        const rotationY = Math.PI / 2 - angle;
        // Bug fix (2026-09-13): computed here and passed to <Agent> as a
        // TRUE scene-root sibling of <StationModule> (never nested inside
        // StationModule's own positioned+rotated <group>) -- see
        // palette.ts#localToWorld's own comment for why nesting it there
        // silently placed every agent ~one ring-radius from its desk.
        const agentHome = localToWorld(position, rotationY, seatLocal);
        return { angle, position, rotationY, agentHome };
      }),
    [slotCount, seatLocal],
  );

  // One accent moment (2026-09-13): when the brain is genuinely busy
  // (GPU util > 30%), corridor pulses run faster -- BrainCore does the
  // matching "brighter rings" half of this internally from the same
  // utilPct prop it already receives.
  const utilPct = data?.brainVitals.gpu.util_pct ?? null;
  const corridorSpeedBoost = utilPct !== null && utilPct > 30 ? 1 + Math.min(1, (utilPct - 30) / 70) * 0.9 : 1;

  // Presence greeter (J 2026-09-13: "nearest agent turns to the viewer /
  // night-patrol dim"): a STATIC pick (camera never orbits, only drifts
  // +-8deg, negligible for "which slot is nearest") of the lane slot
  // closest to the camera's rest position -- lanes, not personas, because a
  // persona's own <Agent> can be hidden entirely while IDLE (see the
  // draw-call budget guard below) and would make an unreliable greeter.
  const nearestLaneIndex = useMemo(() => {
    if (geometry.length === 0) return -1;
    const camX = Math.sin(BASE_AZIMUTH) * CAMERA_DIST;
    const camZ = Math.cos(BASE_AZIMUTH) * CAMERA_DIST;
    let bestI = 0;
    let bestD = Infinity;
    geometry.forEach((slot, i) => {
      const dx = slot.position[0] - camX;
      const dz = slot.position[2] - camZ;
      const d = dx * dx + dz * dz;
      if (d < bestD) { bestD = d; bestI = i; }
    });
    return bestI;
  }, [geometry]);
  // Yaw so the agent's own +Z front (see Agent.tsx's visor mesh) points at
  // the camera's rest position -- a one-time geometric calculation (never
  // per-frame), visually UNVERIFIED without eyes on the real scene (Browser
  // pane is off-limits while J is gaming on the PC's own GPU per the
  // 2026-09-13 gaming-mode note) -- a wrong sign here is a purely cosmetic,
  // easily eyeballed-and-flipped fix, never a functional one.
  const nearestLaneSlot = nearestLaneIndex >= 0 ? geometry[nearestLaneIndex] : null;
  const greeterFacingYaw = nearestLaneSlot
    ? Math.atan2(
        Math.sin(BASE_AZIMUTH) * CAMERA_DIST - nearestLaneSlot.position[0],
        Math.cos(BASE_AZIMUTH) * CAMERA_DIST - nearestLaneSlot.position[2],
      )
    : 0;
  const present = data?.presence?.present ?? null;
  const greeterPresenceMode = present === null ? undefined : present ? "greet" : "patrol";

  // Company Mode: personas[0] is always Gamma (Manager) per collectCompany()'s
  // fixed order -- everyone else gets an inner-ring desk. Geometry memoized
  // on COUNT alone (always 6 in practice), same referential-stability reason
  // as the lane ring above.
  const personaSeatLocal = ultra ? BAY_SEAT_LOCAL : TV_PERSONA_SEAT_LOCAL;
  const allPersonas = data?.company?.personas ?? [];
  const innerPersonas = allPersonas.slice(1);
  const personaSlotCount = Math.max(innerPersonas.length, 1);
  const personaGeometry = useMemo(
    () =>
      Array.from({ length: personaSlotCount }, (_, i) => {
        const t = personaSlotCount > 1 ? i / (personaSlotCount - 1) : 0.5;
        const angle = ARC_CENTER - ARC_SPAN / 2 + t * ARC_SPAN;
        const position: [number, number, number] = [Math.cos(angle) * PERSONA_RING_RADIUS, 0, Math.sin(angle) * PERSONA_RING_RADIUS];
        const rotationY = Math.PI / 2 - angle;
        const agentHome = localToWorld(position, rotationY, personaSeatLocal);
        return { position, rotationY, agentHome };
      }),
    [personaSlotCount, personaSeatLocal],
  );

  // Handoff endpoint labels ("🌍 Scout", "Premarket", "_LEADERBOARD", "J
  // ratification"...) don't all name an actual desk -- only some match a
  // persona. Resolve by stripping a leading emoji and matching the START of
  // the label against a persona name (so "Chef inbox" matches "Chef"); any
  // unmatched label (a process stage like "Premarket", or "J ratification"
  // naming J himself, who has no desk) falls back to the hub, since those
  // conceptually route through the manager.
  const personaPositions = useMemo(() => {
    const map: Record<string, [number, number, number]> = {};
    innerPersonas.forEach((p, i) => {
      map[p.name] = (personaGeometry[i] ?? personaGeometry[0]).position;
    });
    return map;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [innerPersonas.map((p) => p.name).join("|"), personaGeometry]);

  // Gamma's own desk (Pass B, 2026-09-13): fixed angle/radius near the
  // core, not part of either ring loop -- she doesn't walk, doesn't rotate
  // through a slot index. ARC_CENTER matches every other module's "faces
  // the camera most directly" angle; GAMMA_RADIUS sits just outside
  // BrainCore's ring geometry (~2.24 world radius) and well inside the
  // persona ring (6.5) -- the same "just outside the core" band Agent.tsx's
  // all-hands ring (radius 3.2) now stands in too.
  const GAMMA_RADIUS = 3.4;
  const gammaDeskCenter: [number, number, number] = [Math.cos(ARC_CENTER) * GAMMA_RADIUS, 0, Math.sin(ARC_CENTER) * GAMMA_RADIUS];
  const gammaRotationY = Math.PI / 2 - ARC_CENTER;

  // Company audit (commit 58d0b9c6, coordinator 2026-09-13: "the roster
  // must show ghosts as ghosts") -- matched by name onto PersonaState.
  // `data.audit` is included in page.tsx's sceneData content key, so this
  // reference is stable across no-op polls same as everything else here.
  const auditByName = useMemo(() => new Map((data?.audit?.personas ?? []).map((a) => [a.name, a] as const)), [data?.audit]);

  // Activity bubbles (Pass B, "what they are doing," 2026-09-13) -- one
  // candidate per WORKING lane/persona, text from real evidence only:
  // lanes get health+state+evidence (RED gets a "!" prefix and `urgent`,
  // which ActivityBubbleLayer uses to always outrank non-urgent bubbles at
  // the same camera distance), personas get recentOutput or a
  // rosterEvidenceText "quiet since..." fallback -- the SAME two text
  // sources Hud.tsx's roster panel already reads, so the in-scene bubble
  // and the flat HUD panel never disagree about what a persona is doing.
  // Parked lanes / IDLE personas are excluded entirely (candidates with no
  // Agent body shouldn't get a bubble hovering over nothing). Bubble Y is
  // agentHome's own Y + 2.0 -- above a 1.8-unit-tall character's head,
  // clear of StationModule's doorway nameplate (y=2.3) and PersonaModule's
  // nameplate (its own Html, unaffected).
  const activityCandidates: ActivityBubbleCandidate[] = useMemo(() => {
    const out: ActivityBubbleCandidate[] = [];
    rows.forEach((row, i) => {
      if (isParkedState(row.state, row.health)) return;
      const slot = geometry[i] ?? geometry[0];
      const pos: [number, number, number] = [slot.agentHome[0], slot.agentHome[1] + 2.0, slot.agentHome[2]];
      const text = row.health === "red"
        ? truncateOneLine(`! ${row.evidence}`, 60)
        : truncateOneLine(`${row.state} · ${row.evidence}`, 60);
      out.push({ key: `lane:${row.lane}`, position: pos, text, urgent: row.health === "red" });
    });
    innerPersonas.forEach((p, i) => {
      if (p.status === "IDLE") return;
      const slot = personaGeometry[i] ?? personaGeometry[0];
      const pos: [number, number, number] = [slot.agentHome[0], slot.agentHome[1] + 2.0, slot.agentHome[2]];
      const text = p.recentOutput ? truncateOneLine(p.recentOutput, 60) : truncateOneLine(rosterEvidenceText(p.lastFireISO), 60);
      out.push({ key: `persona:${p.name}`, position: pos, text, urgent: p.status === "RED" });
    });
    return out;
  }, [rows, geometry, innerPersonas, personaGeometry]);

  const resolveHandoffPosition = (label: string): [number, number, number] => {
    const stripped = label.replace(/^[^\w]+/u, "").trim();
    const match = Object.keys(personaPositions).find((name) => stripped.startsWith(name));
    if (match) return personaPositions[match];
    return HUB;
  };

  return (
    <>
      {/* HQ v2 perf pass: Mali-G31 (the real TV's GPU) is fragment-bound and
          hates per-pixel lights -- ONE hemisphereLight + ONE directionalLight
          for the entire scene, zero pointLights anywhere (module health tint
          now comes from emissive floor-edge strips, not a per-module light;
          see StationModule.tsx). */}
      <color attach="background" args={[PALETTE.space]} />
      <fog attach="fog" args={[PALETTE.fogColor, 20, 62]} />
      {/* Pass C (2026-09-13): ET day/night mood, ambient fill ONLY -- this
          is a space-station interior, not outdoors, so the station's own
          practical lights (ceiling pointLights, beacons, desk screens)
          never dim with the clock, exactly as a real installation's
          artificial lighting wouldn't. nightMult floors at 0.5 (never
          pitch black -- a mood shift, not a blackout) and only multiplies
          the SAME two lights the pre-Pass-C perf budget already spent. */}
      <hemisphereLight args={["#3a4a7a", "#04040a", 0.55 * nightMult * dimFactor]} />
      {/* Ultra tier: this directional light also casts real shadows
          (module/agent meshes opt in via castShadow/receiveShadow below) --
          the TV tier's identical light stays shadow-free (shadows={false}
          on CanvasRoot's <Canvas> makes castShadow a no-op there anyway,
          so this prop is harmless to set unconditionally). */}
      <directionalLight
        position={[6, 10, 4]}
        intensity={0.55 * nightMult * dimFactor}
        castShadow={ultra}
        shadow-mapSize={[2048, 2048]}
        shadow-camera-near={1}
        shadow-camera-far={40}
        shadow-camera-left={-14}
        shadow-camera-right={14}
        shadow-camera-top={14}
        shadow-camera-bottom={-14}
      />

      <CameraRig reducedMotion={reducedMotion} rows={rows} geometry={geometry} briefMtimeMs={data?.brief.mtime_ms ?? null} />
      {/* Suspense-scoped (world pass A bug fix, see BrainCore.tsx) -- the
          HDRI load suspends too, and is a SIBLING of BrainCore/EffectsStack
          here, not a descendant; without its own boundary it would ALSO
          bubble to <Canvas>'s single built-in one and unmount them. */}
      {ultra && (
        <Suspense fallback={null}>
          <PmremEnvironment />
        </Suspense>
      )}
      {ultra && coreReady && <EffectsStack coreMeshRef={coreMeshRef} />}
      <SkyDome />
      <Starfield reducedMotion={reducedMotion} />

      {/* Kit rebuild (2026-09-13, HQ-SCENE-PLAN.md): the hub's real
          `room-large` shell, ultra tier only -- sits at the scene root (HUB
          is the origin) so BrainCore/the persona ring/the ideas wall all
          land inside it unchanged. Suspense-scoped (world pass A bug fix,
          see BrainCore.tsx) so a still-loading hub shell never unmounts
          BrainCore/EffectsStack, which are SIBLINGS here, not descendants. */}
      {ultra && (
        <Suspense fallback={null}>
          <HubRoom />
        </Suspense>
      )}

      <BrainCore
        utilPct={data?.brainVitals.gpu.util_pct ?? null}
        memUsedMib={data?.brainVitals.gpu.mem_used_mib ?? null}
        memTotalMib={data?.brainVitals.gpu.mem_total_mib ?? null}
        modelName={data?.brainVitals.models[0]?.name ?? null}
        manager={allPersonas[0] ?? null}
        briefMtimeMs={data?.brief.mtime_ms ?? null}
        gaming={gaming}
        dimFactor={dimFactor}
        reducedMotion={reducedMotion}
        ultra={ultra}
        coreMeshRef={coreMeshRef}
      />

      {/* Gamma's own character + desk + speech bubble (Pass B, 2026-09-13)
          -- ultra tier only, same reasoning as every other real-kit-geometry
          piece in this scene (TV tier keeps BrainCore's plaque-only
          depiction, no draw-call budget for a 15th character body). */}
      {ultra && (
        <GammaCharacter
          deskCenter={gammaDeskCenter}
          rotationY={gammaRotationY}
          accentColor={allPersonas[0]?.color ?? PALETTE.hubCore}
          briefText={data?.brief.text ?? ""}
          briefMtimeMs={data?.brief.mtime_ms ?? null}
          utilPct={data?.brainVitals.gpu.util_pct ?? null}
          modelName={data?.brainVitals.models[0]?.name ?? null}
          gaming={gaming}
        />
      )}

      {rows.map((row, i) => {
        const slot = geometry[i] ?? geometry[0];
        const behavior = deriveBehavior(row, gaming);
        return (
          <group key={row.lane}>
            <Corridor
              from={slot.position}
              to={HUB}
              freshness={freshness01(minutesSinceEvidence(row.last_evidence_et))}
              speedBoost={corridorSpeedBoost}
              reducedMotion={reducedMotion}
            />
            {/* Kit rebuild: real corridor.glb segments -- WALL to WALL
                (hub's outer wall at HUB_WALL_RADIUS to the bay's near wall
                at RING_RADIUS-BAY_HALF_DEPTH), both along the SAME angle
                `slot.position` already sits on. World pass A fix
                (2026-09-13, caught from the first real screenshot): the
                original version ran center-to-center (HUB to
                slot.position), which clips straight through both rooms'
                interiors instead of filling only the gap between their
                walls -- the pulse sprite above still travels the full
                center-to-center line unchanged (Corridor.tsx), only the
                real kit geometry's span changed. Ultra tier only. */}
            {ultra && (
              <Suspense fallback={null}>
                <CorridorRun
                  from={[Math.cos(slot.angle) * HUB_WALL_RADIUS, 0, Math.sin(slot.angle) * HUB_WALL_RADIUS]}
                  to={[Math.cos(slot.angle) * (RING_RADIUS - BAY_HALF_DEPTH), 0, Math.sin(slot.angle) * (RING_RADIUS - BAY_HALF_DEPTH)]}
                />
              </Suspense>
            )}
            <StationModule
              position={slot.position}
              angle={slot.angle}
              row={row}
              behavior={behavior}
              reducedMotion={reducedMotion}
              dimFactor={dimFactor}
              ultra={ultra}
            />
            {/* Scene-root sibling, NOT nested inside StationModule -- see the
                agentHome comment above. Lane agents never walk anymore (no
                event cleanly attributes a card to one lane -- see
                Courier.tsx's own comment on why card-status events route
                there instead); `presenceMode`/`facingYaw` are set on
                exactly one statically-chosen lane (nearestLaneIndex). */}
            <Agent
              laneSeed={row.lane}
              home={slot.agentHome}
              hub={HUB}
              behavior={behavior}
              accentColor={healthColor(row.health)}
              reducedMotion={reducedMotion}
              presenceMode={i === nearestLaneIndex ? greeterPresenceMode : undefined}
              facingYaw={i === nearestLaneIndex ? greeterFacingYaw : undefined}
              ultra={ultra}
            />
          </group>
        );
      })}

      {/* Company Mode: inner persona ring -- Gamma (Manager) excluded (it's
          BrainCore itself); each persona gets a slim nameplate + its own
          Agent as a scene-root sibling (same positioning fix as the lane
          ring -- Agent must never be nested inside a positioned parent). */}
      {innerPersonas.map((persona, i) => {
        const slot = personaGeometry[i] ?? personaGeometry[0];
        const behavior = derivePersonaBehavior(persona, gaming);
        // Draw-call budget guard (2026-09-13): each <Agent> is 7 meshes (see
        // Agent.tsx), so 6 inner personas can add up to 42 draw calls on top
        // of the 8 lane modules' own agents -- the last confirmed real TV
        // report (fps=29, 116 calls, pre-Company-Mode) leaves little
        // headroom against the ~130-call soft ceiling. A persona with raw
        // status IDLE (never fired, or nothing recent) draws its nameplate
        // only -- an empty desk is an honest depiction of "idle", not a
        // missing feature -- while GREEN/YELLOW/RED keep their agent body.
        // Gate on the raw status, not `behavior`: derivePersonaBehavior()
        // maps BOTH YELLOW and IDLE to the same "idle" Agent animation, and
        // YELLOW ("acknowledging") must keep its body.
        const showAgent = persona.status !== "IDLE";
        // Pilot's desk screen (Pass B, 2026-09-13): "SPY price + last
        // decision (or lane row's last_evidence line if no SPY field -- do
        // NOT add a new data producer)". There is no SPY-specific field
        // anywhere on HqApiResponse (checked this session) -- Pilot's own
        // recentOutput already IS "spy=<price> last_bar=<ts>" whenever
        // Pilot has fired (verified against a live /api/hq response this
        // session), so reading it directly satisfies the ask with zero new
        // producers; the "lane row" fallback in the brief doesn't map
        // cleanly onto a persona (Pilot isn't a sectors.row), so the honest
        // equivalent fallback is the SAME rosterEvidenceText "quiet
        // since..." text every other persona's bubble/roster line already
        // uses when recentOutput is empty.
        // Pass C schedule state (2026-09-13): only dims when BOTH outside
        // this persona's own window AND not genuinely working right now --
        // real activity always wins over a schedule assumption (see
        // scheduleOnShift's own comment). "Night shift = Chef lit/busy,
        // others resting" falls straight out of PERSONA_SCHEDULE's own
        // table (Chef's window IS overnight) -- no separate night branch.
        const offSchedule = !scheduleOnShift(persona.name, etMinutesNow, dayOfWeekNow) && behavior !== "working";
        const isPilot = persona.name === "Pilot";
        const pilotScreenLines: ScreenLine[] | undefined = isPilot
          ? [
              { text: persona.recentOutput ? truncateOneLine(persona.recentOutput, 30) : "no output yet", color: "#7ad9ff", size: 18 },
              { text: rosterEvidenceText(persona.lastFireISO), size: 14 },
            ]
          : undefined;
        return (
          <group key={persona.name}>
            <PersonaModule position={slot.position} persona={persona} behavior={behavior} audit={auditByName.get(persona.name)} />
            {/* Kit rebuild: persona desks get the SAME real DeskCluster as
                the lane bays (SetKit.tsx), offset+rotated identically --
                ultra tier only, no room shell (personas already sit inside
                HubRoom). Rendered regardless of `showAgent` -- an empty desk
                for an IDLE persona is honest, matching the lane/agent
                convention below it. */}
            {ultra && (
              <Suspense fallback={null}>
                <group position={slot.position} rotation={[0, slot.rotationY, 0]}>
                  <group position={[0, 0, BAY_DESK_OFFSET_Z]}>
                    <DeskCluster accentColor={personaStatusColor(persona.status)} screenTitle={isPilot ? "PILOT" : undefined} screenLines={pilotScreenLines} />
                  </group>
                </group>
              </Suspense>
            )}
            {showAgent && (
              <Agent
                laneSeed={persona.name}
                home={slot.agentHome}
                hub={HUB}
                behavior={behavior}
                accentColor={personaStatusColor(persona.status)}
                reducedMotion={reducedMotion}
                // J 2026-09-13 (d): "a persona lastFireISO advancing -> that
                // persona walks from the hub to its desk and sits down
                // working". Agent's own seen-value-diff seeds silently on
                // first mount, so this never fires a walk for a persona
                // that was already showing a lastFireISO on page load.
                walkEventKey={persona.lastFireISO}
                walkKind="arrival"
                // All-hands event (Pass B, 2026-09-13): "on new station-brief
                // mtime, 6 personas walk to hub, ring around core for 60s...
                // walk back". Every inner persona reads the SAME key
                // (brief.mtime_ms) so all 6 queue the SAME walk on the SAME
                // poll -- independent of each persona's own arrival trigger
                // above (see Agent.tsx's own comment on the two channels).
                allHandsEventKey={data?.brief.mtime_ms != null ? String(data.brief.mtime_ms) : null}
                scheduleDim={offSchedule ? 0.35 : 1}
                ultra={ultra}
              />
            )}
          </group>
        );
      })}
      <HandoffCourier
        handoffs={data?.company?.handoffs ?? []}
        resolvePosition={resolveHandoffPosition}
        restPosition={COURIER_REST}
        reducedMotion={reducedMotion || gaming}
      />

      <IdeasWall cards={data?.ideas.cards ?? []} position={WALL_POS} dimFactor={dimFactor} />
      <Courier cards={data?.ideas.cards ?? []} hub={HUB} wall={WALL_POS} reducedMotion={reducedMotion || gaming} />

      {ultra && !gaming && <ActivityBubbleLayer candidates={activityCandidates} />}
    </>
  );
}

export default memo(Scene);

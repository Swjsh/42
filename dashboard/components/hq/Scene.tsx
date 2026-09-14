"use client";

import { memo, Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { useThree, useFrame } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import * as THREE from "three";
import { recordCameraSample } from "@/lib/hq-motion-diag";
import type { HqApiResponse, SectorRow, CoreDecisionRow } from "./types";
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
import Planet from "./Planet";
import Ground from "./Ground";
import Rocks from "./Rocks";
import BaseProps from "./BaseProps";
import PmremEnvironment from "./PmremEnvironment";
import EffectsStack from "./EffectsStack";
import GammaCharacter from "./GammaCharacter";
import ActivityBubbleLayer, { type ActivityBubbleCandidate } from "./ActivityBubbleLayer";
import { computePurposefulWalk, dayNightFactor, freshness01, healthColor, hhmmFromEtIso, isParkedState, isRegularTradingHours, lerp, localToWorld, minutesSinceEvidence, nowEtDayOfWeek, nowEtMinutes, PALETTE, personaStatusColor, rosterEvidenceText, scheduleOnShift, truncateOneLine, type ScreenLine } from "./palette";
import { BAY_DESK_OFFSET_Z, BAY_HALF_DEPTH, BAY_SEAT_LOCAL, CHARACTER_SCALE, CHARACTER_TARGET_HEIGHT, CorridorRun, DeskCluster, HubRoom, HUB_WALL_RADIUS, Plaza } from "./SetKit";
// World-2 coordinator review (2026-09-14, "GAMMA'S BUBBLE... must derive it
// from the same truth as the panel"): the SAME pure function Hud.tsx's own
// crew-panel "next:" line already uses for Gamma, reused here (not
// reimplemented) so GammaCharacter.tsx's bubble text is guaranteed
// identical, never just independently similar. Zero fs/fetch (this file's
// own header) -- safe to import client-side same as Hud.tsx already does.
import { crewNextLine } from "@/lib/crew";

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
// World-2 item 3(a) (2026-09-14): the plaza floor plate (SetKit.tsx#Plaza)
// covers the hub + every bay + the corridor gaps between them -- outer bay
// edge sits at RING_RADIUS+BAY_HALF_DEPTH (~16.7), plus 1.5u of margin so
// the plate's own edge lip doesn't clip through a bay's outer wall.
const PLAZA_RADIUS = RING_RADIUS + BAY_HALF_DEPTH + 1.5;
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
// LIVE-1 item 1 (2026-09-14, J: "i need to be able to move around and see,
// i cant really see"): ultra tier's OWN closer default. TV tier's
// CAMERA_DIST/CAMERA_HEIGHT above are UNCHANGED (this pass is ultra-tier
// only, matching every other `ultra` branch in this file) -- the real
// physical TV's framing was tuned across Pass A/F/G against real captures
// and this task never asks for it to move.
// World-2 coordinator review (2026-09-14, "THE OVERVIEW IS NOT AN OVERVIEW...
// the hub fills the frame and the bays are cut off at the edges, so the
// connected building you built is invisible"): LIVE-1's 16/5.5 pair (above,
// superseded) was tuned back when the station was just a hub + floating
// pods with nothing between them -- once W2/W3 (this same pass) added a
// real ground/plaza and 7 real hallways, that same close distance put the
// camera effectively INSIDE the hub's own open doorway, unable to show the
// very connectivity those items were built to prove. Pulled back to
// distance=28 (within "26-30u"), elevation~=35deg (within "32-38deg") --
// height = 28*tan(35deg)~=19.6 -- so hub + all 7 bays + the plaza edge fit
// in frame together. This is ALSO the key-"0" overview pose (OVERVIEW_CAM_POS
// below is computed FROM these same two constants) and the free camera's
// own auto-orbit distance (CameraRig's "auto" mode reads these directly) --
// changing them here satisfies "make key 0 land there" by construction, not
// a separate edit. Fly-to presets 1-7 (per-desk, computed independently in
// `cameraPresets` below) are untouched.
const CAMERA_DIST_ULTRA = 28;
const CAMERA_HEIGHT_ULTRA = 19.6;
// One reusable scratch vector for CameraRig's per-frame desired-position
// math (module scope, never per-frame allocation -- same discipline as
// StationModule.tsx's `_screenColor` / ActivityBubbleLayer.tsx's `_camPos`).
// Safe as a shared singleton: written and consumed synchronously within one
// useFrame callback, never held across a frame boundary.
const _desiredCamPos = new THREE.Vector3();
// Free-camera tuning (LIVE-1 item 1). minDistance/maxDistance bound how far
// OrbitControls can zoom; maxPolarAngle keeps the camera from ever dipping
// below the floor -- derived from camera.y = target.y + distance*cos(phi)
// with target.y=1.4 (DEFAULT_LOOKAT below): at the FARTHEST zoom, camera.y
// hits 0 (the floor) at phi~=91.8deg; 89.5deg leaves a real margin while
// still letting the camera get close to eye-level with the station at any
// closer distance (at distance=6, the same 89.5deg barely changes camera.y
// at all).
// World-2 item 1 (2026-09-14, J: "when I scroll out, a black circle just
// appears and takes over everything"): 45 -> 36. Root cause was the far
// clip plane (CanvasRoot.tsx/UltraCanvasRoot.tsx, now far=400), not this
// value on its own -- but SkyDome.tsx's dome radius is 70, so the OLD
// 45-unit max zoom could still put the camera up to 45+70=115u from the
// dome's far wall, needing an implausibly large far plane to cover every
// case. Tightening the max zoom to 36 (36+70=106, comfortable under the new
// far=400) also keeps the station itself filling a sane share of the frame
// at full zoom-out, per this same item's "floor or background" ask -- a
// station that shrinks to a speck before the dome even clips reads just as
// broken as the black disc itself.
const FREE_CAM_MIN_DISTANCE = 6;
const FREE_CAM_MAX_DISTANCE = 36;
const FREE_CAM_MAX_POLAR_ANGLE = (89.5 * Math.PI) / 180;
const FREE_CAM_FLIGHT_S = 1.2; // keyboard 0-7 fly-to duration
const FREE_CAM_IDLE_RESUME_S = 45; // auto-orbit resumes this long after the user's last input
const FREE_CAM_AUTO_EASE = 0.05; // camera.position/controls.target lerp factor while the cinematic orbit drives -- imperceptible during steady continuous drift, and the SAME mechanism that makes a 45s-idle resume read as an "ease back" rather than a snap
// "0 = overview" -- a fixed pose (no drift term, i.e. the auto-orbit's own
// t=0 position) at the new ultra default distance/height, computed once
// since every input is a compile-time constant.
const OVERVIEW_CAM_POS: [number, number, number] = [
  Math.sin(BASE_AZIMUTH) * CAMERA_DIST_ULTRA,
  CAMERA_HEIGHT_ULTRA,
  Math.cos(BASE_AZIMUTH) * CAMERA_DIST_ULTRA,
];
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
// Pass G nit (a) (2026-09-13, coordinator: "the far-left lane labels are cut
// by the canvas edge... nudge the camera azimuth or ring"). Decoupled from
// BASE_AZIMUTH on purpose -- the camera's own orbit position/lookAt/drift
// stay completely untouched, only the module arc rotates a further N deg
// around the SAME center. Geometry (camera at BASE_AZIMUTH~=38.7deg,
// looking at origin) puts the arc's t=1 end (angle ~166deg) very close to
// the screen's true leftmost bearing (~141deg) and the t=0 end (~-63.7deg)
// close to the screen's true rightmost bearing (~-38.7deg) -- a positive
// nudge here pushes BOTH ends away from their respective screen extremes'
// close side, pulling t=1's clipped label inward; it also pushes t=0
// slightly closer to the right edge, which the Pass G item-1 layout split
// already made a clean clip (not a collision) rather than a problem. A 6deg
// first guess (real capture, hq-world-G-shadowtest.png) visibly revealed
// one more character of the clipped label ("on-SPY 0DTE)" -> "non-SPY
// 0DTE)") but wasn't conclusively fully clear -- 10deg here as the one
// follow-up per this same file's own no-blind-repeated-guessing discipline
// (ARC_SPAN, Pass F). Verify via the final real capture; if still clipped,
// document honestly rather than guess a third angle.
const ARC_CENTER_NUDGE = (10 * Math.PI) / 180;
const ARC_CENTER = Math.PI / 2 - BASE_AZIMUTH + ARC_CENTER_NUDGE;
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
// INTERACT-2 (I2 a/b, 2026-09-14): how long a hub-exchange bubble (Chef's
// verdict line / Coach's sectors line + Gamma's ack) stays visible after the
// real crew-events.jsonl row's own ts_et -- roughly the eventWalk's own
// round-trip time (WALK_DURATION*2+PURPOSEFUL_PAUSE in Agent.tsx, ~13s), a
// UI display-duration constant of the SAME class as FADE_SECONDS
// (ActivityBubbleLayer.tsx) / PURPOSEFUL_PAUSE (Agent.tsx) -- the window's
// ORIGIN is always a real event timestamp, never a fabricated ambient timer.
const EVENT_BUBBLE_WINDOW_MIN = 2;
// Gamma's deterministic per-kind ack -- mirrors lib/dialogue.ts#GAMMA_CREW_ACK
// verbatim. Kept as a local copy rather than an import: that module also
// exports fs-touching server readers (getLatestSpeech), and a "use client"
// file must never take a VALUE import from a module with a node:fs import at
// module scope (see dialogue.ts's own getLatestSpeech-vs-LatestSpeech split,
// the established safe precedent this file already follows for every other
// server-only type it consumes via `import type`).
const GAMMA_CREW_ACK: Record<string, string> = {
  verdict: "logged -- it stays on the board until n_post clears the bar",
  sectors: "on it -- flagging anything red to the board",
  task_health: "on it -- disabled/failed tasks go on the board",
  hq_review: "noted -- thanks for keeping an eye on us",
};
// Item 2b (LIVE-1, 2026-09-14): fixed ground-level destinations for
// palette.ts#computePurposefulWalk's non-neighbor destinations. "ideas-wall"
// targets near the hub's own center (WALL_POS itself is [0,3.4,0] -- the
// wall is MOUNTED above the hub, not out on the floor, matching Courier.tsx's
// own hub->wall carry path) rather than literally under WALL_POS, so a
// persona visiting doesn't stand exactly atop the courier's own rest spot or
// BrainCore's center. "core"/"lounge" are distinct hub-interior points, clear
// of BrainCore's ring geometry (~2.58 world radius) and Gamma's own desk
// (radius 3.4, angle ARC_CENTER).
const PURPOSEFUL_TARGETS: Record<"ideas-wall" | "core" | "lounge", [number, number, number]> = {
  "ideas-wall": [1.1, 0, -0.7],
  core: [-1.2, 0, -1.6],
  lounge: [-2.2, 0, 1.7],
};

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

interface CameraPreset {
  /** World position of the character's own head (top-of-head, body-scale-
   * independent -- see cameraPresets' own comment in Scene() below). This is
   * the OrbitControls `target` a keyboard 1-7 fly-to lands on. */
  headPos: [number, number, number];
  /** Where the camera itself eases to for that preset. */
  camPos: [number, number, number];
}

interface CameraRigProps {
  reducedMotion: boolean;
  rows: SectorRow[];
  geometry: Array<{ position: [number, number, number] }>;
  briefMtimeMs: number | null;
  /** LIVE-1 item 1 (2026-09-14): free camera is ultra-tier only, same
   * convention as every other `ultra` branch in this file -- the TV tier
   * never mounts <OrbitControls> and this component's behavior is BYTE-
   * IDENTICAL to before this pass when false. */
  ultra: boolean;
  /** Keys "1".."7" index into this array (cameraPresets[0] = key "1", per
   * Scene.tsx's own [Gamma, ...6 personas] fixed order) -- see that
   * component's own comment for how each entry is derived. */
  cameraPresets: CameraPreset[];
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
function CameraRig({ reducedMotion, rows, geometry, briefMtimeMs, ultra, cameraPresets }: CameraRigProps) {
  const { camera } = useThree();
  const lookAtCurrent = useRef(new THREE.Vector3(0, 1.4, 0));
  const focusGoal = useRef<THREE.Vector3 | null>(null);
  const focusUntil = useRef(0);
  const prevRedLanes = useRef<Set<string>>(new Set());
  const seenBriefMtime = useRef<number | null | undefined>(undefined);
  const lastVignetteBucket = useRef(-1);

  // ─── LIVE-1 item 1 (2026-09-14, ultra tier only): free camera ───────────
  // Three modes, a plain ref (never React state -- changes every frame
  // during a flight/idle-countdown and must never trigger a re-render):
  //   "auto"     -- the cinematic orbit below drives the camera every frame,
  //                 BYTE-IDENTICAL mechanism to before this pass.
  //   "userFree" -- OrbitControls owns the camera outright (the user is
  //                 dragging/zooming, or within FREE_CAM_IDLE_RESUME_S of
  //                 their last input) -- this component touches nothing.
  //   "flying"   -- a FREE_CAM_FLIGHT_S eased hand-authored move to a
  //                 keyboard-preset desk/overview pose.
  // drei's <OrbitControls> registers its own `controls.update()` at
  // useFrame priority -1 (verified from its shipped source this session,
  // not assumed) -- i.e. it runs BEFORE this component's own (default-
  // priority) useFrame every single frame. In "auto" mode that ordering
  // means: OrbitControls recomputes its internal spherical state from
  // whatever camera.position/controls.target this component set LAST frame
  // (a true no-op with zero pending user delta -- three.js's OrbitControls
  // always re-derives spherical FROM the camera's current position each
  // call, it does not cache a separate authoritative position), and THEN
  // this component makes the frame's real, authoritative move -- so the
  // final state each frame is always this component's, with no fighting
  // and no need to toggle `controls.enabled` (which would also silence the
  // pointer listeners that must stay live for the user to interrupt the
  // orbit in the first place).
  const mode = useRef<"auto" | "userFree" | "flying">("auto");
  const idleSince = useRef<number | null>(null);
  const lastElapsed = useRef(0);
  const controlsRef = useRef<OrbitControlsImpl>(null);
  const flight = useRef<{
    fromPos: THREE.Vector3; fromTarget: THREE.Vector3;
    toPos: THREE.Vector3; toTarget: THREE.Vector3; start: number;
  } | null>(null);

  // Initial OrbitControls target -- set ONCE imperatively after mount,
  // never as a `target=` JSX prop: this component re-renders on every
  // genuine Scene data change (same cadence as every other piece of this
  // tree), and a JSX `target` prop would silently SNAP the live orbit
  // target back to the hub on each of those re-renders, fighting every
  // imperative `.lerp()`/flight mutation this file makes to it below.
  useEffect(() => {
    controlsRef.current?.target.set(DEFAULT_LOOKAT.x, DEFAULT_LOOKAT.y, DEFAULT_LOOKAT.z);
  }, []);

  // World-2 item 1 (2026-09-14): `?camdist=NN` (ultra tier only) sets the
  // INITIAL free-camera distance -- lets a headless capture script (which
  // cannot drive the mouse) prove the zoomed-out view without real user
  // input. Read once from the URL at mount, never a reactive searchParams
  // hook -- this component lives inside <Canvas> and the value never needs
  // to change after first paint. Parking `mode` in "userFree" with
  // `idleSince` left null (see the mode state machine's own top-of-file
  // comment) holds the camera at this exact pose indefinitely -- the SAME
  // steady state a real mid-drag user already gets -- so a 35s capture
  // settle window never eases back toward the normal auto-orbit distance
  // before the screenshot fires.
  useEffect(() => {
    if (!ultra) return;
    const controls = controlsRef.current;
    if (!controls) return;
    const raw = new URLSearchParams(window.location.search).get("camdist");
    const n = raw !== null ? Number(raw) : NaN;
    if (!Number.isFinite(n)) return;
    const dist = Math.min(FREE_CAM_MAX_DISTANCE, Math.max(FREE_CAM_MIN_DISTANCE, n));
    camera.position.set(Math.sin(BASE_AZIMUTH) * dist, CAMERA_HEIGHT_ULTRA, Math.cos(BASE_AZIMUTH) * dist);
    controls.target.set(DEFAULT_LOOKAT.x, DEFAULT_LOOKAT.y, DEFAULT_LOOKAT.z);
    camera.lookAt(controls.target);
    mode.current = "userFree";
    idleSince.current = null;
  }, [ultra, camera]);

  // Keyboard fly-to: "1".."7" = cameraPresets[0..6] (Scene.tsx's own fixed
  // [Gamma, ...6 personas] order), "0" = the fixed overview pose. A window-
  // level listener -- this component is mounted INSIDE <Canvas>, but
  // `window` is the same real DOM window either way, no special r3f
  // bridging needed. A missing preset (roster not loaded yet, or fewer
  // than 7 personas -- a real, common fail-open shape elsewhere in this
  // file) is silently ignored, never a crash. Modifier-chorded presses
  // (browser zoom, etc.) are skipped so this never fights a real shortcut.
  useEffect(() => {
    if (!ultra) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || e.metaKey || e.ctrlKey || e.altKey) return;
      const controls = controlsRef.current;
      if (!controls) return;
      let dest: CameraPreset | null = null;
      if (e.key === "0") {
        dest = { camPos: OVERVIEW_CAM_POS, headPos: [DEFAULT_LOOKAT.x, DEFAULT_LOOKAT.y, DEFAULT_LOOKAT.z] };
      } else if (e.key >= "1" && e.key <= "7") {
        dest = cameraPresets[Number(e.key) - 1] ?? null;
      }
      if (!dest) return;
      flight.current = {
        fromPos: camera.position.clone(),
        fromTarget: controls.target.clone(),
        toPos: new THREE.Vector3(...dest.camPos),
        toTarget: new THREE.Vector3(...dest.headPos),
        start: lastElapsed.current,
      };
      mode.current = "flying";
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [ultra, cameraPresets, camera]);

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    lastElapsed.current = t;
    const controls = controlsRef.current;

    if (ultra && controls) {
      if (mode.current === "flying" && flight.current) {
        const f = flight.current;
        const p = Math.min(1, (t - f.start) / FREE_CAM_FLIGHT_S);
        const eased = p * p * (3 - 2 * p); // smoothstep
        camera.position.lerpVectors(f.fromPos, f.toPos, eased);
        controls.target.lerpVectors(f.fromTarget, f.toTarget, eased);
        camera.lookAt(controls.target);
        if (p >= 1) {
          mode.current = "userFree";
          idleSince.current = t;
          flight.current = null;
        }
        return;
      }
      if (mode.current === "userFree") {
        const idleForS = idleSince.current === null ? 0 : t - idleSince.current;
        if (idleSince.current === null || idleForS < FREE_CAM_IDLE_RESUME_S) return; // OrbitControls owns the camera, untouched
        mode.current = "auto"; // idle timeout elapsed -- fall through and ease back below
      }
    }

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
    const dist = ultra ? CAMERA_DIST_ULTRA : CAMERA_DIST;
    const height = ultra ? CAMERA_HEIGHT_ULTRA : CAMERA_HEIGHT;
    _desiredCamPos.set(Math.sin(azimuth) * dist, height, Math.cos(azimuth) * dist);
    // Look ABOVE the hub's own center (y=0) so the whole station -- hub,
    // modules, and the elevated ideas wall at y=3.4 -- settles into the
    // lower ~80% of frame, leaving the top clear for the HUD (title/mode
    // badge) instead of the two overlapping (unaffected by focus easing --
    // lookAtCurrent only ever moves a modest distance off this baseline).
    if (ultra && controls) {
      // Eased, never snapped -- see this function's own top-of-file
      // comment: imperceptible during steady continuous drift (the desired
      // position barely moves frame to frame), and the SAME mechanism that
      // makes a 45s-idle resume from an arbitrary OrbitControls-parked
      // position read as a graceful ease back.
      camera.position.lerp(_desiredCamPos, FREE_CAM_AUTO_EASE);
      controls.target.lerp(lookAtCurrent.current, FREE_CAM_AUTO_EASE);
      camera.lookAt(controls.target);
    } else {
      camera.position.copy(_desiredCamPos);
      camera.lookAt(lookAtCurrent.current);
    }

    // World-2 MOTION-FIX diag (?diag=1 only -- no-ops otherwise, see
    // hq-motion-diag.ts's own header): camera position/target + r3f's own
    // reported `delta`, sampled once camera.position/controls.target are
    // finalized for this frame -- ultra tier only (this is the only branch
    // with a real user-drivable OrbitControls to diagnose).
    if (ultra && controls) {
      recordCameraSample({
        delta,
        camX: camera.position.x, camY: camera.position.y, camZ: camera.position.z,
        targetX: controls.target.x, targetY: controls.target.y, targetZ: controls.target.z,
      });
    }
  });

  // Ultra tier only -- see this component's own top-of-file comment for the
  // full hand-off mechanism. `onStart`/`onEnd` fire on drag AND wheel-zoom
  // (three.js's OrbitControls dispatches both from the same 'start'/'end'
  // events), matching "pauses the moment the user interacts" for either.
  // `enableDamping` is the standard smoothing three.js ships with; NOT
  // toggling `enabled` is deliberate -- see the top-of-file comment on why
  // that would also silence the pointer listeners that must stay live.
  if (!ultra) return null;
  return (
    <OrbitControls
      ref={controlsRef}
      makeDefault
      enableDamping
      dampingFactor={0.08}
      minDistance={FREE_CAM_MIN_DISTANCE}
      maxDistance={FREE_CAM_MAX_DISTANCE}
      maxPolarAngle={FREE_CAM_MAX_POLAR_ANGLE}
      onStart={() => {
        mode.current = "userFree";
        idleSince.current = null;
      }}
      onEnd={() => {
        idleSince.current = lastElapsed.current;
      }}
    />
  );
}

const EXPOSURE_NIGHT = 1.35; // unchanged from UltraCanvasRoot.tsx's original one-time onCreated value
const EXPOSURE_DAY = 1.0; // coordinator's own number -- "day ~1.0 exposure"
// World-2 coordinator review (2026-09-14, DAYTIME BLOWOUT root cause (c) of
// 3): PmremEnvironment.tsx's real HDRI feeds every PBR material's
// reflections via THREE.Scene.environmentIntensity (three 0.184, default 1,
// verified present in this project's installed three/src/scenes/Scene.js
// before using it) -- unconditionally at full strength regardless of time
// of day, on top of the sky/lights already being much brighter by day.
// Scaled down to ~0.3 by day (night keeps the default 1 -- reflections
// should read strongly against a dark station).
const ENV_INTENSITY_NIGHT = 1;
const ENV_INTENSITY_DAY = 0.3;

interface ExposureSyncProps {
  dayFactor: number;
}

/**
 * LIVE-1 item 2 follow-up (coordinator 2026-09-14): "the tan architecture
 * is blown out in daylight (exposure 1.35 + bloom threshold 0.78 were
 * tuned for the night look). Scale exposure... with the same nightFactor."
 * UltraCanvasRoot.tsx sets `gl.toneMappingExposure = 1.35` exactly ONCE,
 * inside `onCreated` (fires at canvas construction, never again) -- fine
 * for the night mood it was tuned against, wrong once item 3 made daytime
 * genuinely bright under the SAME fixed exposure. This tiny component is
 * the reactive owner of that value instead: `useThree()` for the real
 * THREE.WebGLRenderer, one throttled useFrame writing a plain scalar
 * property (zero resource cost, nothing like Bloom's GPU-resource
 * reconstruction risk -- see EffectsStack.tsx's own comment for why THAT
 * one needs ref indirection and this one doesn't). Deliberately NOT folded
 * into CameraRig, which already carries enough unrelated complexity: a
 * small single-purpose component mounted as its own <ExposureSync> JSX
 * sibling, matching this file's existing convention (CameraRig,
 * EffectsStack) of small focused subcomponents driving one concern each.
 * Ultra tier only (mounted `{ultra && ...}` in Scene's return) -- the TV
 * tier's CanvasRoot.tsx never sets ACESFilmicToneMapping or a non-default
 * exposure at all, so this must never touch that renderer.
 */
function ExposureSync({ dayFactor }: ExposureSyncProps) {
  const { gl, scene } = useThree();
  const lastCheckAtS = useRef(-Infinity); // -Infinity: first frame applies immediately, no 1s wait at a wrong exposure
  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (t - lastCheckAtS.current < 1) return;
    lastCheckAtS.current = t;
    gl.toneMappingExposure = lerp(EXPOSURE_NIGHT, EXPOSURE_DAY, dayFactor);
    // World-2 coordinator review: same reactive-value-via-imperative-write
    // discipline as the exposure line above (never a prop on
    // PmremEnvironment's own <Environment> -- see that file's own comment
    // on why a reactive prop there would reopen the GodRays-class teardown/
    // reapply bug this whole HQ tree already paid to fix once).
    scene.environmentIntensity = lerp(ENV_INTENSITY_NIGHT, ENV_INTENSITY_DAY, dayFactor);
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
  // INTERACT-2 (I2 f, 2026-09-14): "the day's FIRST core-decisions row at/
  // after 15:55 ET" -- a monotonic ref (never React state; mutated in plain
  // render-time code below, not an effect, matching this file's own
  // dayFactorRef "latest ref" convention two screens down) holding the ET
  // calendar date of the last qualifying row seen. Stays null until the
  // first such row this mount ever observes, then holds that SAME date
  // string for the rest of the day (no further mutation until a genuinely
  // NEW day's row arrives) -- exactly the stable-until-a-real-change shape
  // Agent.tsx's own eventWalk seen-value-diff needs to fire exactly once.
  const pilotPostCloseKeyRef = useRef<string | null>(null);
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
  // World-3 polish pass (2026-09-14, coordinator: "verify the night look...
  // add a dev-only ?hour=22 override on dayNightFactor if none exists --
  // never in production paths"): read once per render (cheap, same "fresh
  // read every render" cadence etMinutesNow above already uses) -- ONLY
  // overrides the value FED INTO dayNightFactor()'s own hour computation.
  // `etMinutesNow` itself is UNTOUCHED, so isRegularTradingHours/persona
  // scheduling below keep reading the real wall clock always -- this is a
  // visual-mood-only test hook, same class of thing as CameraRig's own
  // established `?camdist=` override (that one lives in CameraRig, which
  // this pass does not own; this one lives here, in Scene()'s own general
  // body, which this pass does). Absent or out-of-range -> real clock,
  // byte-identical to before this override existed.
  const hourOverrideRaw = typeof window !== "undefined" ? new URLSearchParams(window.location.search).get("hour") : null;
  const hourOverride = hourOverrideRaw !== null ? Number(hourOverrideRaw) : NaN;
  const etMinutesForMood = Number.isFinite(hourOverride) && hourOverride >= 0 && hourOverride <= 23 ? hourOverride * 60 : etMinutesNow;
  const nightFactor = dayNightFactor(etMinutesForMood);
  const nightMult = lerp(0.5, 1, nightFactor);
  // World-2 coordinator review (2026-09-14, "DAYTIME BLOWOUT... the whole
  // hub is washed-out orange with no wall edges"): root cause (b) of 3 --
  // hemisphereLight/directionalLight only ever scaled INTENSITY by
  // nightMult, never their own COLORS, so the ambient fill stayed literal
  // night-navy (#3a4a7a sky / #04040a ground) even at full noon, fighting
  // the now-bright day sky dome (SkyDome.tsx's own dayFactor blend) and the
  // PBR materials' environment reflections for the scene's "what time is
  // it" read. Lerped the SAME nightFactor every other day/night mechanism
  // in this file already uses, memoized (not per-frame -- Scene() only
  // re-renders on a genuine poll, matching SkyDome's own rebake cadence).
  const hemiSkyColor = useMemo(() => new THREE.Color("#3a4a7a").lerp(new THREE.Color("#cfe3ff"), nightFactor).getStyle(), [nightFactor]);
  const hemiGroundColor = useMemo(() => new THREE.Color("#04040a").lerp(new THREE.Color("#8a7a60"), nightFactor).getStyle(), [nightFactor]);
  const sunColor = useMemo(() => new THREE.Color("#dce8ff").lerp(new THREE.Color("#fff4e0"), nightFactor).getStyle(), [nightFactor]);
  // World-2 coordinator polish (2026-09-14, "HORIZON SEAM... a pale sky
  // sliver over a near-black far ground, meeting in a hard curved edge --
  // reads like a planet rim"): root cause -- fog (below) was a FIXED
  // near-black (`PALETTE.fogColor`, "#050914") regardless of time of day,
  // so Ground.tsx's disc (fog-affected, unlike SkyDome which explicitly
  // opts OUT via fog={false}) faded to near-black at its own fog-far
  // distance while the dome's own unfogged horizon band read much lighter
  // by day -- a real color mismatch drawn right where the flat ground disc
  // geometrically intersects the spherical dome (both share ~radius 70),
  // reading as a hard circular seam. Lerped toward a pale-blue day tone
  // that matches SkyDome.tsx's own DAY_DEPTH region (that file's
  // horizon-band color at midday) so the two converge; Ground.tsx's own
  // material has no `fog={false}` override, so its color (and its grid
  // texture, per the SAME mechanism) already fades toward THIS color by
  // distance for free once the color itself agrees with the dome.
  // World-3 environment pass (2026-09-14, J: "grey abyss"): was lerping to a
  // pale sky-blue (#a9c9e3) -- root cause #3 of 3 (ENVIRONMENT-PLAN.md) --
  // by day, everything past the plaza was one flat pale wall with nothing
  // else in view. Target now matches SkyDome's own new DAY_DEPTH stop (deep
  // indigo, never pale) so the two still agree at the horizon seam exactly
  // like before this pass (same mechanism, just a darker target).
  const fogColor = useMemo(() => new THREE.Color(PALETTE.fogColor).lerp(new THREE.Color("#1c3355"), nightFactor).getStyle(), [nightFactor]);
  // LIVE-1 item 2 follow-up (coordinator 2026-09-14): the SAME nightFactor
  // exposed to EffectsStack.tsx (Bloom threshold) and ExposureSync (tone-
  // mapping exposure) below via a ref, never a reactive prop -- see
  // EffectsStack.tsx's own comment on why. A plain per-render assignment
  // (not a useEffect) is deliberate: the ref's CONTENTS should reflect
  // every render's freshly-computed value immediately, only its identity
  // needs to stay stable, and this is the standard "latest ref" pattern.
  const dayFactorRef = useRef(nightFactor);
  dayFactorRef.current = nightFactor;
  // Item 2c (LIVE-1, 2026-09-14): Pilot's desk-pulse/point gesture is
  // gated to Regular Trading Hours only, same ET clock read as everything
  // else in this function (never a separate/stale one).
  const isRth = isRegularTradingHours(etMinutesNow, dayOfWeekNow);

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
  // INTERACT-2 (I2 a/b, 2026-09-14): "Chef/Coach walks to Gamma at the hub
  // wall" -- 70% of the way from the hub center to Gamma's own desk, so the
  // visitor stands near her without literally overlapping her chair.
  const gammaHubMeet: [number, number, number] = [gammaDeskCenter[0] * 0.7, 0, gammaDeskCenter[2] * 0.7];
  // Latest Chef "verdict" / Coach "sectors"|"task_health"|"hq_review" row
  // from crew-events.jsonl (CREW-2's own additive field, newest-last tail
  // order per lib/hq.ts#readCrewEvents' own doc comment) -- feeds both the
  // eventWalk trigger below (per persona) and the two-bubble hub exchange.
  // "hq_review" (observed live 2026-09-14, not in this task's original kind
  // list) is Coach's own HQ-health self-review, also routed `"to":"Gamma"`
  // in the real row -- included here rather than left dark, same "every
  // real row gets a real interaction" intent as the other two kinds.
  const crewEvents = data?.crewEvents ?? [];
  const latestChefVerdict = [...crewEvents].reverse().find((e) => e.who === "Chef" && e.kind === "verdict") ?? null;
  const latestCoachSectors = [...crewEvents].reverse().find((e) => e.who === "Coach" && (e.kind === "sectors" || e.kind === "task_health" || e.kind === "hq_review")) ?? null;

  // INTERACT-2 (I2 c-f, 2026-09-14): the remaining four named-event walks
  // -- each a (source persona -> trigger key, target) pair, looked up by
  // the SOURCE persona's own name in the per-persona loop below. (d) Scout's
  // own scout_output.json mtime (already wired on the roster); (c) a new
  // Analyst EOD digest (desks.Analyst.path changing); (e) a new treasury
  // file (desks.Treasurer.path changing); (f) the day's first
  // core-decisions row at/after 15:55 ET (pilotPostCloseKeyRef above).
  const findPersonaHome = (name: string): [number, number, number] | undefined => {
    const idx = innerPersonas.findIndex((p) => p.name === name);
    return idx >= 0 ? (personaGeometry[idx] ?? personaGeometry[0]).agentHome : undefined;
  };
  const scoutMtimeKey = innerPersonas.find((p) => p.name === "Scout")?.deliverable.mtimeISO ?? undefined;
  const analystDigestKey = data?.desks?.Analyst?.path ?? undefined;
  const treasuryFileKey = data?.desks?.Treasurer?.path ?? undefined;
  const latestCoreAny = ([data?.trading?.core?.safe, data?.trading?.core?.bold] as const)
    .filter((r): r is CoreDecisionRow => !!r && !!r.tsEt)
    .sort((a, b) => a.tsEt.localeCompare(b.tsEt))
    .pop() ?? null;
  if (latestCoreAny && hhmmFromEtIso(latestCoreAny.tsEt) >= "15:55") {
    const d = latestCoreAny.tsEt.slice(0, 10);
    if (pilotPostCloseKeyRef.current !== d) pilotPostCloseKeyRef.current = d;
  }
  const pilotPostCloseKey = pilotPostCloseKeyRef.current ?? undefined;
  const NAMED_EVENT_WALKS: Record<string, { key: string | undefined; target: [number, number, number] | undefined }> = {
    Scout: { key: scoutMtimeKey, target: findPersonaHome("Pilot") },
    Analyst: { key: analystDigestKey, target: findPersonaHome("Chef") },
    Treasurer: { key: treasuryFileKey, target: gammaHubMeet },
    Pilot: { key: pilotPostCloseKey, target: findPersonaHome("Analyst") },
  };

  // LIVE-1 item 1 (2026-09-14): keyboard fly-to targets for keys "1".."7" --
  // the SAME fixed [Gamma, ...6 personas] order collectCompany() already
  // guarantees (allPersonas[0] is always Gamma; innerPersonas is everyone
  // else, both established above). headPos is the character's own top-of-
  // head world position: agentHome (feet/floor level, same point Agent.tsx
  // seats a character at) plus a body-INDEPENDENT offset -- KitAgent.tsx's
  // own head-beacon sits at `CHARACTER_RAW_HEIGHT[bodyId] * 0.95` in LOCAL
  // space, and characterScale() is exactly
  // `CHARACTER_TARGET_HEIGHT*CHARACTER_SCALE / CHARACTER_RAW_HEIGHT[bodyId]`
  // -- the per-body raw height cancels out of (local head Y) * (scale)
  // algebraically, leaving one constant for every body, not a per-body
  // lookup (this asset pack's own rig keeps the head near the bbox top
  // through sit/rest/walk alike, per KitAgent.tsx's own comment, so this is
  // valid for a SEATED desk character too). camPos is an ADAPTIVE pull-back
  // rather than a fixed "6 units outward": the persona ring (radius 6.5)
  // sits only ~1 unit inside the hub's own wall (HUB_WALL_RADIUS 7.5, see
  // SetKit.tsx#ARCHITECTURE_SCALE_HUB) so a naive outward offset would
  // clip through it -- pull OUTWARD only when there's real clearance before
  // that wall (Gamma's close-to-core desk, radius 3.4), INWARD otherwise
  // (every persona desk), which also keeps the inward case well clear of
  // BrainCore's own ring geometry (~2.58 world radius) and Gamma's desk
  // (radius 3.4). Not memoized -- cheap (<=7 iterations of scalar math),
  // matching this file's own convention of only memoizing what feeds a
  // CHILD's dependency array where referential stability changes behavior
  // (gammaDeskCenter itself, two lines up, is likewise a plain per-render
  // const).
  const cameraPresets: CameraPreset[] = (() => {
    const headOffset = CHARACTER_TARGET_HEIGHT * CHARACTER_SCALE * 0.95;
    const deskPositions: [number, number, number][] = [];
    if (allPersonas[0]) deskPositions.push(gammaDeskCenter);
    innerPersonas.forEach((_, i) => {
      const slot = personaGeometry[i] ?? personaGeometry[0];
      deskPositions.push(slot.agentHome);
    });
    return deskPositions.map((pos): CameraPreset => {
      const headPos: [number, number, number] = [pos[0], pos[1] + headOffset, pos[2]];
      const deskRadius = Math.hypot(pos[0] - HUB[0], pos[2] - HUB[2]);
      const dirX = deskRadius > 0.001 ? (pos[0] - HUB[0]) / deskRadius : 0;
      const dirZ = deskRadius > 0.001 ? (pos[2] - HUB[2]) / deskRadius : 1;
      const outwardRoom = HUB_WALL_RADIUS - 1.0 - deskRadius;
      const pull = outwardRoom > 2.5 ? Math.min(3.5, outwardRoom) : -Math.min(2.5, Math.max(0.5, deskRadius - 1.5));
      const camPos: [number, number, number] = [headPos[0] + dirX * pull, headPos[1] + 4.2, headPos[2] + dirZ * pull];
      return { headPos, camPos };
    });
  })();

  // Item 2b (LIVE-1, 2026-09-14): one purposeful-walk decision per inner
  // persona, computed fresh each render from the SAME pure function
  // lib/useMotionEvents.ts's ticker line uses (see that function's own
  // comment for why this must stay a pure, shared, deterministic
  // calculation rather than local state). `nowMsForWalks` is read ONCE per
  // render (not per persona) so all 6 personas' bucket math agrees on
  // "now" even though Scene.tsx isn't inside a useFrame loop here -- fine
  // precision for a 6-10min cadence. Neighbor = the next persona in the
  // SAME fixed roster order collectCompany() guarantees, wrapping -- a
  // stable, deterministic "who's nearby" pick with zero extra data needed.
  const nowMsForWalks = Date.now();
  const ideasCount = data?.ideas.cards.length ?? 0;
  const purposefulWalks = innerPersonas.map((persona, i) => {
    const neighbor = innerPersonas.length > 1 ? innerPersonas[(i + 1) % innerPersonas.length] : null;
    const walk = computePurposefulWalk(persona.name, nowMsForWalks, ideasCount, persona.lastFireISO, neighbor?.name ?? null);
    const target: [number, number, number] =
      walk.destination === "neighbor" && neighbor
        ? (personaGeometry[(i + 1) % innerPersonas.length] ?? personaGeometry[0]).agentHome
        : PURPOSEFUL_TARGETS[walk.destination as "ideas-wall" | "core" | "lounge"] ?? PURPOSEFUL_TARGETS.lounge;
    return { walk, target };
  });

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
      // I3 (INTERACT-2, 2026-09-14): "each person's bubble shows their own
      // one-line status (recentOutput or their desk headline)" -- desk
      // headline is a new, more targeted fallback ahead of the generic
      // "quiet since..." evidence text, since it names the SAME real
      // source the persona's own desk screen shows.
      const deskHeadline = data?.desks?.[p.name]?.headline;
      const text = p.recentOutput
        ? truncateOneLine(p.recentOutput, 60)
        : deskHeadline
          ? truncateOneLine(deskHeadline, 60)
          : truncateOneLine(rosterEvidenceText(p.lastFireISO), 60);
      out.push({ key: `persona:${p.name}`, position: pos, text, urgent: p.status === "RED" });
    });
    // Item 2b (LIVE-1, 2026-09-14): "each walk gets... a speech bubble with
    // the reason" -- positioned AT the destination (not tracking the
    // walker's own mid-flight position, which would need a per-frame
    // update this poll-driven list doesn't have) so it reads as "<name> is
    // over there, doing <reason>" for the ~14s the walk is actually active.
    purposefulWalks.forEach(({ walk, target }, i) => {
      if (!walk.active) return;
      const p = innerPersonas[i];
      const destLabel = walk.destination === "ideas-wall" ? "ideas wall" : walk.destination === "core" ? "core" : walk.destination === "neighbor" ? "neighbor" : "lounge";
      const pos: [number, number, number] = [target[0], target[1] + 2.0, target[2]];
      out.push({ key: `walk:${p.name}`, position: pos, text: truncateOneLine(`${p.name} -> ${destLabel}: ${walk.reason}`, 60), urgent: false });
    });
    // INTERACT-2 (I2 a/b, 2026-09-14): the Chef/Coach -> Gamma hub exchange
    // -- two bubbles per active event (the visitor's own real crew-event
    // line, Gamma's deterministic ack). Active for EVENT_BUBBLE_WINDOW_MIN
    // minutes after the row's own real ts_et.
    const hubExchanges: Array<{ persona: string; event: (typeof crewEvents)[number] }> = [];
    if (latestChefVerdict) hubExchanges.push({ persona: "Chef", event: latestChefVerdict });
    if (latestCoachSectors) hubExchanges.push({ persona: "Coach", event: latestCoachSectors });
    hubExchanges.forEach(({ persona: name, event }) => {
      const ageMin = minutesSinceEvidence(event.ts_et);
      if (ageMin === null || ageMin >= EVENT_BUBBLE_WINDOW_MIN) return;
      const visitorPos: [number, number, number] = [gammaHubMeet[0], gammaHubMeet[1] + 2.0, gammaHubMeet[2]];
      out.push({ key: `hubevent:${name}`, position: visitorPos, text: truncateOneLine(event.line, 60), urgent: false });
      const ackPos: [number, number, number] = [gammaDeskCenter[0], 2.0, gammaDeskCenter[2]];
      out.push({ key: "hubevent:gamma-ack", position: ackPos, text: truncateOneLine(GAMMA_CREW_ACK[event.kind] ?? "logged, thanks", 60), urgent: false });
    });
    // INTERACT-2 (I2 c-f, 2026-09-14): a matching destination bubble for
    // each of the remaining four named-event walks -- same
    // EVENT_BUBBLE_WINDOW_MIN activeness window, each keyed off the SAME
    // real age signal that gates its own walk trigger above.
    const namedBubbles: Array<{ key: string; ageMin: number | null; targetPos: [number, number, number] | undefined; text: string }> = [
      {
        key: "namedwalk:Analyst",
        ageMin: data?.desks?.Analyst?.ageMin ?? null,
        targetPos: findPersonaHome("Chef"),
        text: `Analyst -> Chef: your queue: ${data?.desks?.Analyst?.headline ?? "new digest"}`,
      },
      {
        key: "namedwalk:Scout",
        ageMin: innerPersonas.find((p) => p.name === "Scout")?.deliverable.ageMin ?? null,
        targetPos: findPersonaHome("Pilot"),
        text: "Scout -> Pilot: fresh catalyst read",
      },
      {
        key: "namedwalk:Treasurer",
        ageMin: data?.desks?.Treasurer?.ageMin ?? null,
        targetPos: gammaHubMeet,
        text: `Treasurer -> Gamma: ${data?.desks?.Treasurer?.headline ?? "new report"}`,
      },
      {
        key: "namedwalk:Pilot",
        ageMin: latestCoreAny && hhmmFromEtIso(latestCoreAny.tsEt) >= "15:55" ? minutesSinceEvidence(latestCoreAny.tsEt) : null,
        targetPos: findPersonaHome("Analyst"),
        text: "Pilot -> Analyst: day's decisions in, handing off",
      },
    ];
    namedBubbles.forEach(({ key, ageMin, targetPos, text }) => {
      if (ageMin === null || ageMin >= EVENT_BUBBLE_WINDOW_MIN || !targetPos) return;
      const pos: [number, number, number] = [targetPos[0], targetPos[1] + 2.0, targetPos[2]];
      out.push({ key, position: pos, text: truncateOneLine(text, 60), urgent: false });
    });
    return out;
  }, [
    rows, geometry, innerPersonas, personaGeometry, purposefulWalks, crewEvents,
    latestChefVerdict, latestCoachSectors, gammaHubMeet, gammaDeskCenter, data?.desks,
    data?.trading?.core?.safe?.tsEt, data?.trading?.core?.bold?.tsEt,
  ]);

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
      {/* World-3 environment pass (2026-09-14): near 20->40, far 62->70 --
          pushed OUT so the new regolith/craters/rocks (Ground.tsx, Rocks.tsx)
          actually stay visible instead of vanishing right past the plaza
          edge; far stays aligned to Ground/SkyDome's own shared radius (70,
          same alignment principle the original 62-vs-70 pairing already
          used) so the horizon-seam blend this scene depends on still holds. */}
      <fog attach="fog" args={[fogColor, 40, 70]} />
      {/* Pass C (2026-09-13): ET day/night mood, ambient fill ONLY -- this
          is a space-station interior, not outdoors, so the station's own
          practical lights (ceiling pointLights, beacons, desk screens)
          never dim with the clock, exactly as a real installation's
          artificial lighting wouldn't. nightMult floors at 0.5 (never
          pitch black -- a mood shift, not a blackout) and only multiplies
          the SAME two lights the pre-Pass-C perf budget already spent. */}
      <hemisphereLight args={[hemiSkyColor, hemiGroundColor, 0.55 * nightMult * dimFactor]} />
      {/* Ultra tier: this directional light also casts real shadows
          (module/agent meshes opt in via castShadow/receiveShadow below) --
          the TV tier's identical light stays shadow-free (shadows={false}
          on CanvasRoot's <Canvas> makes castShadow a no-op there anyway,
          so this prop is harmless to set unconditionally). */}
      {/* Pass G item 2, RULED OUT (2026-09-13). Tested the coordinator's own
          shadow hypothesis two ways: (1) source-code check -- meshbasic.
          glsl.js (three 0.184, this repo's node_modules) shows
          MeshBasicMaterial's fragment shader includes ZERO shadow chunks,
          and SkyDome's mesh never sets receiveShadow (Object3D default is
          false) -- "shadow lands on the sky dome" is structurally
          impossible here, verified from source, not guessed. (2) real
          capture with castShadow forced false scene-wide (hq-world-
          G-shadowtest.png) -- the arch was PIXEL-IDENTICAL in shape/size/
          position with every shadow in the scene off, ruling out ANY
          shadow mechanism (not just the sky-dome-specific one), including
          HubRoom self-shadowing its own concave interior. Combined with
          Pass G's earlier emissive+rotation null results, three independent
          real tests now agree: not lighting, not facing, not shadows --
          left as a likely genuine mesh-silhouette gap, flagged for direct
          inspection next pass. castShadow restored to `ultra` (real
          shadows back on for floors/desks -- this toggle was scene-wide and
          never should ship disabled). */}
      <directionalLight
        color={sunColor}
        position={[6, 10, 4]}
        intensity={0.55 * nightMult * dimFactor}
        castShadow={ultra}
        shadow-mapSize={[2048, 2048]}
        shadow-camera-near={1}
        shadow-camera-far={40}
        // World-3 environment pass (2026-09-14), E4 "shadows from the sun on
        // rocks and base": -14/14 -> -22/22. The OLD frustum (28x28,
        // centered on the light's implicit (0,0,0) target) stopped just
        // short of Scene.tsx's own PLAZA_RADIUS (~18.2) -- nothing past the
        // plaza edge (craters, boulders, dishes, the rover) could ever
        // receive a shadow at all, regardless of their own receiveShadow
        // prop, since the shadow CAMERA never rendered that area into the
        // depth map in the first place. Widened just enough to cover the
        // plaza + the nearest ring of new terrain (craters start at
        // radius=20, Ground.tsx) -- NOT out to the full ~60-radius rock
        // field, which would spread the same fixed 2048x2048 map thin
        // enough to visibly blockify the close, load-bearing shadows
        // (desks/walls/characters) that matter far more than a shadow on a
        // distant decorative rock.
        shadow-camera-left={-22}
        shadow-camera-right={22}
        shadow-camera-top={22}
        shadow-camera-bottom={-22}
      />

      <CameraRig
        reducedMotion={reducedMotion}
        rows={rows}
        geometry={geometry}
        briefMtimeMs={data?.brief.mtime_ms ?? null}
        ultra={ultra}
        cameraPresets={cameraPresets}
      />
      {/* LIVE-1 item 2 follow-up (2026-09-14): renderer-exposure half of the
          day/night exposure+threshold pair -- see ExposureSync's own
          comment. Ultra tier only, same gate as EffectsStack below (the TV
          tier's renderer never gets a non-default exposure at all). */}
      {ultra && <ExposureSync dayFactor={nightFactor} />}
      {/* Suspense-scoped (world pass A bug fix, see BrainCore.tsx) -- the
          HDRI load suspends too, and is a SIBLING of BrainCore/EffectsStack
          here, not a descendant; without its own boundary it would ALSO
          bubble to <Canvas>'s single built-in one and unmount them. */}
      {ultra && (
        <Suspense fallback={null}>
          <PmremEnvironment />
        </Suspense>
      )}
      {ultra && coreReady && <EffectsStack coreMeshRef={coreMeshRef} dayFactorRef={dayFactorRef} />}
      {/* Item 3 (LIVE-1, 2026-09-14): the sky now tracks the SAME
          day/night factor the hemisphere/directional lights already use --
          see SkyDome.tsx's own comment for the root cause this fixes. */}
      <SkyDome dayFactor={nightFactor} />
      <Starfield reducedMotion={reducedMotion} dayFactor={nightFactor} />
      {/* World-3 environment pass (2026-09-14): the background planet/moon --
          see Planet.tsx's own top comment + ENVIRONMENT-PLAN.md. Both tiers
          (single unlit draw call, same cost class as SkyDome/Starfield). */}
      <Planet reducedMotion={reducedMotion} />
      {/* World-2 item 2 (2026-09-14, J: "there needs to be some sort of
          floor or background... right now it's just infinite directions"):
          a large ground disc under the whole scene, both tiers (cheap --
          one draw call, same cost class as SkyDome/Starfield). Same
          dayFactor as the sky/lights so the horizon never seams. */}
      <Ground dayFactor={nightFactor} ultra={ultra} />
      {/* World-3 environment pass (2026-09-14), E2/E3: instanced rock field +
          boulders (ultra-gated inside Rocks.tsx itself) and the exterior
          base props ring (dishes/solar/landing-pad/rover/containers/pipes/
          lights/antenna, tier-split inside BaseProps.tsx itself). Both
          components own their own `ultra` branching so Scene.tsx doesn't
          need a second `{ultra && ...}` wrapper here. */}
      <Rocks ultra={ultra} />
      <BaseProps ultra={ultra} dayFactor={nightFactor} reducedMotion={reducedMotion} />
      {/* World-2 item 4 (2026-09-14, J: "the spinning color radar looking
          things can go... noisy" + HQ face rule "motion = events with a
          ticker"): ServiceDrones removed entirely (component file deleted
          too) -- it had no event source, just a timer-driven orbit, exactly
          the ungrounded ambient motion the face rule forbids. */}

      {/* Kit rebuild (2026-09-13, HQ-SCENE-PLAN.md): the hub's real
          `room-large` shell, ultra tier only -- sits at the scene root (HUB
          is the origin) so BrainCore/the persona ring/the ideas wall all
          land inside it unchanged. Suspense-scoped (world pass A bug fix,
          see BrainCore.tsx) so a still-loading hub shell never unmounts
          BrainCore/EffectsStack, which are SIBLINGS here, not descendants. */}
      {/* World-2 item 3(a) (2026-09-14): the plaza floor plate under
          hub+corridors+bays -- see SetKit.tsx#Plaza's own comment. No
          Suspense needed (pure procedural geometry, no useGLTF load). */}
      {ultra && <Plaza radius={PLAZA_RADIUS} dayFactor={nightFactor} />}

      {ultra && (
        <Suspense fallback={null}>
          <HubRoom dayFactor={nightFactor} />
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
      {ultra && (() => {
        // World-2 coordinator review ("de-overlap the hub"): active under
        // the SAME EVENT_BUBBLE_WINDOW_MIN age check the activityCandidates
        // memo's own hubExchanges.forEach uses above -- reimplemented here
        // (not reading the memo's output) since this needs to run OUTSIDE
        // that memo, off `latestChefVerdict`/`latestCoachSectors` (already
        // computed once per render above, before the memo).
        const isGammaExchangeActive = [latestChefVerdict, latestCoachSectors].some((event) => {
          if (!event) return false;
          const ageMin = minutesSinceEvidence(event.ts_et);
          return ageMin !== null && ageMin < EVENT_BUBBLE_WINDOW_MIN;
        });
        return (
        <GammaCharacter
          deskCenter={gammaDeskCenter}
          rotationY={gammaRotationY}
          accentColor={allPersonas[0]?.color ?? PALETTE.hubCore}
          lastRow={data?.brainVitals.lastRow ?? null}
          nextLine={allPersonas[0] ? crewNextLine(allPersonas[0], Date.now()) : null}
          suppressBubble={isGammaExchangeActive}
          briefText={data?.brief.text ?? ""}
          briefMtimeMs={data?.brief.mtime_ms ?? null}
          utilPct={data?.brainVitals.gpu.util_pct ?? null}
          modelName={data?.brainVitals.models[0]?.name ?? null}
          gaming={gaming}
        />
        );
      })()}

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
                  angle={slot.angle}
                  dayFactor={nightFactor}
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
              dayFactor={nightFactor}
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
        // Pilot's desk screen: see the isPilot block below (item 1
        // follow-up, 2026-09-14) for the CURRENT mechanism -- superseded
        // the original Pass B (2026-09-13) recentOutput-based design, then
        // Item 2c's decisions.jsonl-based design; this comment previously
        // described both, now stale, removed rather than left misleading.
        // Pass C schedule state (2026-09-13): only dims when BOTH outside
        // this persona's own window AND not genuinely working right now --
        // real activity always wins over a schedule assumption (see
        // scheduleOnShift's own comment). "Night shift = Chef lit/busy,
        // others resting" falls straight out of PERSONA_SCHEDULE's own
        // table (Chef's window IS overnight) -- no separate night branch.
        const offSchedule = !scheduleOnShift(persona.name, etMinutesNow, dayOfWeekNow) && behavior !== "working";
        const isPilot = persona.name === "Pilot";
        // Item 1 follow-up (LIVE-1, coordinator 2026-09-14): Pilot's desk
        // screen used to read persona.logTail -- the tail of
        // automation/state/decisions.jsonl, the RETIRED LLM heartbeat's own
        // ledger (lib/personas.ts#collectPilot), which kept showing a stale
        // Friday row once the live engine stopped writing that file. The
        // LIVE engine (heartbeat_core.py) writes automation/state/
        // core-decisions.jsonl instead -- already on the wire as
        // data.trading.core.{safe,bold} (lib/hq.ts#readCoreDecisionsLatest,
        // the SAME byte-seek tail reader item 5's trading strip already
        // uses -- one row per account, per the coordinator's own "per
        // account" ask). Per the coordinator's explicit instruction: this
        // screen and the pulse badge below never read decisions.jsonl
        // again -- both accounts' rows come exclusively from data.trading.
        // Item 2b (LIVE-1): this persona's own purposeful-walk decision,
        // computed once above alongside every other inner persona's.
        const purposeful = purposefulWalks[i];
        const safeDecision = isPilot ? (data?.trading?.core.safe ?? null) : null;
        const boldDecision = isPilot ? (data?.trading?.core.bold ?? null) : null;
        // "isTradeAction" gates the "stands and points" gesture + the pulse
        // badge's hotter-red color. A genuine ENTER_BEAR/ENTER_BULL verdict
        // on EITHER account counts -- verified against the live 42k-row
        // core-decisions.jsonl this session: HOLD / SKIP_* / ERROR /
        // ENTER_BEAR / ENTER_BULL is the FULL verdict vocabulary (no EXIT_*
        // verdict ever appears -- exits are logged by a separate ledger
        // this screen doesn't read), so the /^(ENTER|EXIT)/ test below
        // matches real data, not a guessed one.
        const safeIsTrade = !!safeDecision?.verdict && /^(ENTER|EXIT)/.test(safeDecision.verdict);
        const boldIsTrade = !!boldDecision?.verdict && /^(ENTER|EXIT)/.test(boldDecision.verdict);
        const isTradeAction = safeIsTrade || boldIsTrade;
        // The pulse badge fires off whichever account ticked MOST recently
        // (tsEt string-sorts correctly -- "YYYY-MM-DDTHH:MM:SS", no offset,
        // same format readCoreDecisionsLatest already documents), matching
        // "pulses on every heartbeat minute" from either engine.
        const latestDecision = ([safeDecision, boldDecision].filter((d): d is CoreDecisionRow => !!d).sort((a, b) => a.tsEt.localeCompare(b.tsEt)).pop()) ?? null;
        const decisionText = latestDecision ? `${latestDecision.verdict ?? "?"} @ ${hhmmFromEtIso(latestDecision.tsEt)} ET` : null;
        const decisionTimeEt = latestDecision?.tsEt ?? null;
        const decisionAction = latestDecision?.verdict ?? null;
        const accountScreenLine = (label: string, row: CoreDecisionRow | null): ScreenLine => {
          if (!row) return { text: `${label}: no data`, color: "#5f7a99", size: 14 };
          const sideTxt = row.side === "C" ? " CALL" : row.side === "P" ? " PUT" : "";
          const rowIsTrade = !!row.verdict && /^(ENTER|EXIT)/.test(row.verdict);
          return {
            text: truncateOneLine(`${label} ${row.verdict ?? "?"}${sideTxt} ${hhmmFromEtIso(row.tsEt)}`, 32),
            color: rowIsTrade ? "#ffb020" : "#7ad9ff",
            size: 15,
          };
        };
        const pilotScreenLines: ScreenLine[] | undefined = isPilot
          ? [accountScreenLine("SAFE", safeDecision), accountScreenLine("BOLD", boldDecision)]
          : undefined;
        // INTERACT-2 (I1, 2026-09-14): every non-Pilot desk shows real work
        // too -- lib/desk-content.ts's own reader per role, keyed by the
        // EXACT persona.name string lib/personas.ts's collectors already
        // use. Pilot keeps its dedicated core-decisions wiring above,
        // never duplicated here (data.desks has no "Pilot" entry at all).
        const deskInfo = !isPilot ? data?.desks?.[persona.name] : undefined;
        const deskScreenLines: ScreenLine[] | undefined = deskInfo
          ? [
              { text: truncateOneLine(deskInfo.headline, 32), color: deskInfo.stale ? "#ffb020" : "#dff3ff", size: 15 },
              { text: truncateOneLine(deskInfo.sub, 32), color: "#7ad9ff", size: 13 },
              {
                text: deskInfo.ageMin === null ? "age unknown" : `${Math.round(deskInfo.ageMin)}m ago${deskInfo.stale ? " (stale)" : ""}`,
                color: deskInfo.stale ? "#ffb020" : "#5f7a99",
                size: 12,
              },
            ]
          : undefined;
        // INTERACT-2 (I2 a/b): Chef's own station-verdicts.jsonl scoring /
        // Coach's own sectors.json summary walks that ONE persona to Gamma
        // at the hub -- see Agent.tsx's own eventWalk channel comment for
        // why this reuses the "purposeful" phase machinery under a
        // dedicated trigger rather than the 6-10min rotation's own one.
        // Every other persona passes undefined for both props (no-op, see
        // Agent.tsx's own null/undefined guard).
        const hubEvent = persona.name === "Chef" ? latestChefVerdict : persona.name === "Coach" ? latestCoachSectors : null;
        // INTERACT-2 (I2 c-f): every OTHER named-event walk (Scout->Pilot,
        // Analyst->Chef, Treasurer->Gamma, Pilot->Analyst) resolves from the
        // NAMED_EVENT_WALKS lookup above by this persona's own name -- only
        // ever set when BOTH a trigger key and a real target resolved.
        const namedWalk = NAMED_EVENT_WALKS[persona.name];
        const eventWalkKeyFinal = hubEvent ? hubEvent.ts_et : namedWalk?.target ? namedWalk.key : undefined;
        const eventWalkTargetFinal = hubEvent ? gammaHubMeet : namedWalk?.target;
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
                    <DeskCluster
                      accentColor={personaStatusColor(persona.status)}
                      screenTitle={isPilot ? "PILOT" : deskInfo ? persona.name.toUpperCase() : undefined}
                      screenLines={isPilot ? pilotScreenLines : deskScreenLines}
                    />
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
                // Item 2b (LIVE-1): "every persona takes one named walk
                // every 6-10 min" -- see palette.ts#computePurposefulWalk.
                purposefulWalkEventKey={purposeful.walk.bucketKey}
                purposefulTarget={purposeful.target}
                // INTERACT-2 (I2 a-f): Chef/Coach -> Gamma at the hub on a
                // real crew-event row, OR one of the four other named-event
                // walks (Scout->Pilot, Analyst->Chef, Treasurer->Gamma,
                // Pilot->Analyst) resolved above. undefined for any persona
                // with neither -- zero behavior change (Agent.tsx's own
                // null/undefined guard on this channel).
                eventWalkEventKey={eventWalkKeyFinal}
                eventWalkTarget={eventWalkTargetFinal}
                // Item 2c (LIVE-1): Pilot-only "stands and points at the
                // wall screen" -- a genuine ENTER/EXIT decision (seen-value-
                // diff on action+timestamp, same convention as every other
                // trigger here) holds Agent's animState at "thinking" (the
                // closest real clip to pointing -- see KitAgent.tsx's own
                // CLIP_TABLE comment) for a few seconds. Every other
                // persona (and a non-trade Pilot tick) passes undefined,
                // zero behavior change.
                pointEventKey={isPilot && isTradeAction ? `${decisionAction}@${decisionTimeEt}` : undefined}
                scheduleDim={offSchedule ? 0.35 : 1}
                ultra={ultra}
              />
            )}
            {/* Item 2c (LIVE-1): Pilot's desk pulse -- RTH-only (CLAUDE.md's
                own 09:30-15:55 ET market-hours window), a rotating .hq-beam
                (Hud.tsx's shared style) that stays lit the whole session and
                replays its one-shot .hq-shine sweep (keyed on the decision
                itself) each time a fresh heartbeat tick lands -- "pulses on
                every heartbeat minute" per the ask. Amber for a HOLD/SKIP
                tick, a hotter red for a genuine ENTER/EXIT. */}
            {isPilot && isRth && decisionText && (
              <Html position={[slot.position[0], 2.7, slot.position[2]]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
                <div className="hq-beam" style={{ "--beam-color": isTradeAction ? "#ff3b3b" : "#ffb020" } as CSSProperties}>
                  <div
                    style={{
                      position: "relative", overflow: "hidden",
                      background: "rgba(3,4,10,0.82)", color: isTradeAction ? "#ffdede" : "#ffe9c2",
                      fontFamily: "system-ui, sans-serif", fontSize: 16, fontWeight: 700,
                      padding: "4px 14px", borderRadius: 7, whiteSpace: "nowrap",
                    }}
                  >
                    <span key={decisionText} className="hq-shine" />
                    PILOT {decisionText}
                  </div>
                </div>
              </Html>
            )}
          </group>
        );
      })}
      {/* I4 (INTERACT-2, 2026-09-14): the anonymous courier bot is retired
          -- see HandoffCourier.tsx's own header comment. Only the STALE/
          MISSING dashed-line markers remain, so no reducedMotion/rest
          position is needed here any more. */}
      <HandoffCourier
        handoffs={data?.company?.handoffs ?? []}
        resolvePosition={resolveHandoffPosition}
      />

      <IdeasWall cards={data?.ideas.cards ?? []} position={WALL_POS} dimFactor={dimFactor} />
      <Courier cards={data?.ideas.cards ?? []} hub={HUB} wall={WALL_POS} reducedMotion={reducedMotion || gaming} />

      {ultra && !gaming && <ActivityBubbleLayer candidates={activityCandidates} />}
    </>
  );
}

export default memo(Scene);

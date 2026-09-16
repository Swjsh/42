"use client";

import { memo, Suspense, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import type { CSSProperties } from "react";
import { useThree, useFrame } from "@react-three/fiber";
import type { ThreeEvent } from "@react-three/fiber";
import { Html, OrbitControls } from "@react-three/drei";
import type { OrbitControls as OrbitControlsImpl } from "three-stdlib";
import * as THREE from "three";
import { recordCameraSample } from "@/lib/hq-motion-diag";
// CAM-PARAMS pass (2026-09-15): pure parsing/validation for `?camdist=`/
// `?camtarget=`/`?tour=0` -- CAM_DIST_MIN/CAM_DIST_MAX replace this file's
// own former FREE_CAM_MIN_DISTANCE/FREE_CAM_MAX_DISTANCE literals below (one
// source of truth for the clamp, shared with the unit-testable parser).
import { CAM_DIST_MAX, CAM_DIST_MIN, parseCameraParams, shouldParkTourAtOverview } from "@/lib/hq-camera-params";
import { computeDeskFacingCameraPose } from "@/lib/hq-desk-preset-pure";
// UX-1 U5 (2026-09-14): reports the exact frame the cinematic auto-orbit
// resumes after FREE_CAM_IDLE_RESUME_S of user idle -- Hud.tsx (outside
// <Canvas>) subscribes to this SAME external store to show a brief "camera
// is moving again" hint at the moment it actually happens, never a fixed
// timer independently re-derived on the Hud side (which could drift out of
// sync with CameraRig's own real idle math below).
import { reportAutoOrbitResumed } from "@/lib/hq-camera-mode";
// UX-1 U3 (2026-09-14): the Hud-side half of the crew-card-hover-pulses-the-
// world-marker mechanism -- see that file's own header for the full
// mechanism/index-agreement writeup (index 0 = Gamma, 1-6 = innerPersonas
// 0-5, the SAME fixed order cameraPresets below already uses).
import { getHoveredPersonaIndex, subscribeHoveredPersonaIndex } from "@/lib/hq-hover-persona";
import type { HqApiResponse, SectorRow, CoreDecisionRow, WalkPlan } from "./types";
import { formatPositionClause, type AccountPositions } from "@/lib/hq-positions-pure";
// HQ-TRADE-MOMENTS (2026-09-15): "the world visibly REACTS to real trade
// events" -- Pilot's desk screen (the one existing "speech bubble" surface
// this persona already has, see the isPilot block below) shows the most
// recent active trade moment when one exists, ahead of the SAFE/BOLD
// decision lines it normally shows. data.trading.tradeMoments is already
// server-side windowed (lib/hq-trade-moments-pure.ts#activeTradeMoments) --
// this component never re-derives the window client-side, so a page reload
// mid-window still shows it and a reload past it never resurrects it.
import { formatTradeMomentLine, type TradeMomentEvent } from "@/lib/hq-trade-moments-pure";
import type { PersonaId } from "@/lib/hq-agents";
import type { PersonaState } from "@/lib/personas";
import type { AgentBehavior } from "./Agent";
import Agent from "./Agent";
import DeskNameplate from "./DeskNameplate";
import { modelGlyph } from "./headLabelModel";
import BrainCore from "./BrainCore";
import StationModule from "./StationModule";
import HandoffCourier from "./HandoffCourier";
import IdeasWall from "./IdeasWall";
import Starfield from "./Starfield";
import SkyDome from "./SkyDome";
import Planet from "./Planet";
import Ground from "./Ground";
import Rocks from "./Rocks";
import BaseProps from "./BaseProps";
import PmremEnvironment from "./PmremEnvironment";
import EffectsStack from "./EffectsStack";
import GammaCharacter from "./GammaCharacter";
// LIVE-AGENTS pass (2026-09-14): real Claude Code sessions/subagents (pulse.
// jsonl, via lib/hq-agents.ts server-side) walking the SAME walk graph
// personas already use -- see that file's own header.
import LiveAgents from "./LiveAgents";
import LabelDeclutterManager from "./LabelDeclutterManager";
import { PRIORITY } from "./labelDeclutter";
import { laneBubbleAction, personaBubbleAction } from "./bubbleText";
import { liveAgentIdentity } from "./liveAgentIdentity";
import { computePurposefulWalk, dayNightFactor, healthColor, hhmmFromEtIso, isParkedState, isRegularTradingHours, lerp, localToWorld, minutesSinceEvidence, nowEtDayOfWeek, nowEtMinutes, PALETTE, personaStatusColor, purposefulWalkTriggerKey, scheduleOnShift, truncateOneLine, type ScreenLine } from "./palette";
import { BAY_DESK_OFFSET_Z, BAY_SEAT_LOCAL, BAY_SEAT_LOCAL_BAY, CampusGate, CHARACTER_SCALE, CHARACTER_TARGET_HEIGHT, CorridorRun, DeskCluster, HubRoom, HUB_WALL_RADIUS, Plaza, TJunction } from "./SetKit";
// LAYOUT builder pass (2026-09-14, campus-cross rebuild): pure geometry/math
// module (no React/Three deps) shared with SetKit.tsx -- see that module's
// own header for why the dependency runs this direction only (layout.ts ->
// SetKit.tsx's raw-kit constants), never the reverse.
import {
  ARM_HALF_WIDTH, ARM_LEN, armAngle, buildWalkGraph, CAMPUS_GATE_POSITION, CAMPUS_GATE_ROTATION_Y, CAMPUS_GATE_SCALE,
  computeAllBaySlots, computeArmLayout, computePersonaWallSlots, findWalkPath, HUB_TABLE_RADIUS, MONITOR_MOUNT, PLAZA_APRON, PLAZA_CENTER_RADIUS,
  toWalkPlan,
  type ArmLayout, type WalkGraph,
} from "./layout";
// CREW-WORKING pass (2026-09-15/16): pure huddle-pair helpers -- see that
// module's own header for why they live outside this .tsx file (node --test
// importability, same reason liveAgentWalk.ts/liveAgentIdentity.ts do).
import { detectHuddleTrigger, huddleStandPoints, neighborStandPoint, type HuddleCandidate } from "./crewWorking";
// World-2 coordinator review (2026-09-14, "GAMMA'S BUBBLE... must derive it
// from the same truth as the panel"): the SAME pure function Hud.tsx's own
// crew-panel "next:" line already uses for Gamma, reused here (not
// reimplemented) so GammaCharacter.tsx's bubble text is guaranteed
// identical, never just independently similar. Zero fs/fetch (this file's
// own header) -- safe to import client-side same as Hud.tsx already does.
// UX-1 U3 (2026-09-14): deriveCrewPill/crewNowLine/CREW_PILL_COLOR -- the
// EXACT SAME evidence-backed derivation Hud.tsx's own crew panel and
// bubbleText.ts's personaBubbleAction already read, so the world hover
// tooltip's "name . pill . now-line" can never disagree with the flat
// panel's own pill for the same persona (the task's own "same persona data
// the panel uses" requirement).
import { crewNextLine, deriveCrewPill, crewNowLine, CREW_PILL_COLOR } from "@/lib/crew";

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
// HEAD-LABELS pass (2026-09-15): every lane bay is the SAME deterministic
// Python engine (never an LLM) -- computed once at module scope rather than
// per-row-per-render.
const BAY_MODEL_GLYPH = modelGlyph("python-script");
// LAYOUT builder pass (2026-09-14, campus-cross rebuild replacing the old
// 8-way ring, J: "the doors... jumbled mess... space this out... it needs
// to look real"). All bay/hallway/T-junction geometry now comes from
// layout.ts (ARM_LEN/ARM_HALF_WIDTH/computeAllBaySlots/computeArmLayout) --
// see that module's own header for the full root-cause + fix writeup and
// the exact parsed kit dimensions it's built from. `ARMS` is a MODULE-level
// constant (every input is compile-time-fixed, no dynamic data) rather than
// a per-render useMemo -- the 4 main spines + T-junctions never change
// shape, only the 8 bays (indexed by `rows`) carry live data.
const ARMS: ArmLayout[] = [0, 1, 2, 3].map((k) => computeArmLayout(k));
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
// UX-1 (2026-09-14, coordinator: "the default/preset-0 overview crops the
// two nearest bays... pull back/up so all 8 bays+4 hallways+plaza cross fit
// with margin"). LAYOUT's own 32/22 pair above (comment preserved in git
// history) was tuned by proportional scaling (bay reach grew ~1.14x, so
// distance/height were scaled ~1.14x too) -- a reasonable-sounding heuristic
// that turns out NOT to be the same thing as verifying the real frustum
// angle to every worst-case corner, which this pass actually computed
// (scratchpad camera-frustum-vs-corner-position math, per-corner
// angle-from-forward-axis test, vfov=50deg, aspect=(2560-500)/1440 -- the
// canvas minus Hud's own 500px right column, hq_capture.ps1's real
// 2560x1440 kiosk window): at 32/22, the true worst corner (a bay's own
// far-far corner, verified via layout.ts's actual computeBaySlot geometry --
// ARM_LEN=20.1 x ARM_HALF_WIDTH=10.8, radius 22.8) already clips at
// margin_v=-8.75deg -- confirming the original bug report
// (layout-default-1726.png) was real and NOT fixed by LAYOUT's own pass.
// Worse: the task's own "plaza cross" also has to fit, and Plaza's arm
// rectangles extend PLAZA_APRON (1.5u) past ARM_LEN/ARM_HALF_WIDTH on every
// side (radius 24.9) -- the proportional-scaling comment never accounted
// for the apron at all.
//
// Fix: solved the SAME frustum math for a distance/height pair that clears
// every one of the 8 bays' far corners AND all 4 plaza-arm corners with real
// margin, at the SAME ~34.5deg elevation angle this pose was already tuned
// to (so the "look" -- how steep the diorama angle reads -- is unchanged,
// only the pull-back distance grows): 45/31 -> margin_v=+1.75deg,
// margin_h=+6.34deg (worst case: a plaza-arm corner's own top edge, y=4.25,
// the room-small/room-large kit's real wall height), elevation 34.6deg (was
// 34.5deg), 3D orbit-distance ~53.9u.
//
// SECOND bug found by the same math, pre-dating this pass: the old 32/22
// pose's own 3D orbit-distance from OrbitControls' target (0,1.4,0) is
// sqrt(32^2+20.6^2)~=38.1u -- already PAST the old FREE_CAM_MAX_DISTANCE=36
// ceiling below. Since OrbitControls.update() (drei, runs at useFrame
// priority -1, BEFORE this component's own per-frame write -- see CameraRig
// itself for the verified ordering) unconditionally clamps its internal
// spherical radius to [minDistance, maxDistance] every single frame, key
// "0" was ALREADY snapping the camera back to distance 36 the instant a
// flight finished and mode handed off to "userFree" -- a real, currently-
// shipping violate of this same task's own U5 "no snap" rule, independent
// of the framing bug above. FREE_CAM_MAX_DISTANCE raised to 58 (new orbit-
// distance 53.9u + ~4u of real user zoom-out headroom past the default
// pose, same proportional relationship the old 32/22-vs-36 pair intended)
// fixes both at once. No automated check anywhere in the repo pins "36"
// as a literal value (verified via a repo-wide grep before changing this)
// -- only this file's own now-superseded comment and two other files'
// comments referencing `?camdist=36` as a manual proof checkpoint; the
// checkpoint concept itself (a max-zoom-out visual check) is unaffected by
// which number the ceiling actually is.
const CAMERA_DIST_ULTRA = 45;
const CAMERA_HEIGHT_ULTRA = 31;
// One reusable scratch vector for CameraRig's per-frame desired-position
// math (module scope, never per-frame allocation -- same discipline as
// StationModule.tsx's `_screenColor` / ActivityBubbleLayer.tsx's `_camPos`).
// Safe as a shared singleton: written and consumed synchronously within one
// useFrame callback, never held across a frame boundary.
const _desiredCamPos = new THREE.Vector3();
// UX-1 U2 (2026-09-14): the established synthetic-KeyboardEvent bridge
// (Hud.tsx's own flyToDesk uses the identical mechanism to cross the DOM/
// Canvas boundary) -- CameraRig's own `onKey` listener below is a pure
// string match via resolveCameraPresetKey with no way to tell a real
// keypress from a dispatched one, so this reaches the exact same fly-to
// code path a real "1".."7"/"bay0".."bay7" press would. Module-scope (not a
// useCallback) -- stateless, referenced fresh from an inline per-row/
// per-persona onClick below (a per-RENDER closure, not a per-FRAME one --
// this file's own zero-per-frame-allocation rule targets useFrame, and this
// only ever runs on a genuine user click).
function dispatchPresetKey(key: string): void {
  window.dispatchEvent(new KeyboardEvent("keydown", { key }));
}
// UX-1 U2: shared hover-cursor bookkeeping for every clickable group below
// (bay/persona/hub) -- a module-scope ENTER/LEAVE depth counter rather than
// each group unconditionally setting cursor="pointer"/"auto" on its own
// over/out. r3f's per-object pointerover/pointerout firing order across two
// ADJACENT clickable meshes is not guaranteed (the pointer can be reported
// entering B before it finishes leaving A) -- a naive per-object reset can
// stick the cursor on "auto" while the pointer is still visually over a
// sibling clickable object. A shared depth counter stays correct under
// either ordering: it only returns to "auto" once EVERY currently-hovered
// clickable has reported leaving.
let _hoverDepth = 0;
function _onClickableEnter(): void {
  _hoverDepth++;
  if (typeof document !== "undefined") document.body.style.cursor = "pointer";
}
function _onClickableLeave(): void {
  _hoverDepth = Math.max(0, _hoverDepth - 1);
  if (_hoverDepth === 0 && typeof document !== "undefined") document.body.style.cursor = "auto";
}
interface ClickableGroupHandlers {
  onClick?: (e: ThreeEvent<MouseEvent>) => void;
  onPointerOver?: (e: ThreeEvent<PointerEvent>) => void;
  onPointerOut?: (e: ThreeEvent<PointerEvent>) => void;
}
// UX-1 U2/U3: ONE shared factory for the ~15 clickable-group prop sets below
// (8 bays, 6 personas, Gamma, the hub) instead of near-identical inline
// object literals repeated at every call site -- returns `{}` (spread to a
// no-op) on the TV tier, same "render identically, only interactivity
// differs" convention this file's own `{ultra && ...}` branches already use
// everywhere else, but as a prop-spread here since StationModule/Agent/
// DeskCluster/BrainCore themselves must keep rendering on BOTH tiers
// unchanged -- only whether the WRAPPING group is interactive should differ.
function clickableGroupProps(ultra: boolean, presetKey: string, onEnter: () => void, onLeave: () => void): ClickableGroupHandlers {
  if (!ultra) return {};
  return {
    onClick: (e) => {
      e.stopPropagation();
      dispatchPresetKey(presetKey);
    },
    onPointerOver: (e) => {
      e.stopPropagation();
      _onClickableEnter();
      onEnter();
    },
    onPointerOut: (e) => {
      e.stopPropagation();
      _onClickableLeave();
      onLeave();
    },
  };
}
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
// UX-1 (2026-09-14): 36 -> 58 -- see CAMERA_DIST_ULTRA/CAMERA_HEIGHT_ULTRA's
// own comment above for the full derivation (the overview pose's own real
// 3D orbit-distance from target must stay UNDER this ceiling or
// OrbitControls' per-frame clamp snaps the camera back the instant a flight
// to "0" finishes -- true of the OLD 32/22 pose too, sqrt(32^2+20.6^2)~=38.1
// already past the old 36 ceiling: a real, pre-existing snap bug this same
// change also fixes). 58+70 (SkyDome's own dome radius, per this comment's
// own math above) = 128, still comfortably under far=400.
const FREE_CAM_MIN_DISTANCE = CAM_DIST_MIN;
const FREE_CAM_MAX_DISTANCE = CAM_DIST_MAX;
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
// follow-up per this same file's own no-blind-repeated-guessing discipline.
// Verify via the final real capture; if still clipped, document honestly
// rather than guess a third angle.
const ARC_CENTER_NUDGE = (10 * Math.PI) / 180;
// BLOCKY-FIXES pass (2026-09-16, Defect B): see the `deskCollidesWithOccupiedNeighbor`
// call site's own comment (innerPersonas.map, below) for the full derivation --
// layout.ts#computePersonaWallSlots' corner-sharing desk pairs land exactly
// 0.85 world units apart (verified numerically), against >=9.2u for every
// other pair.
// CORNER-DESKS pass (2026-09-16, BUILD worker): layout.ts's own
// PERSONA_WALL_RADIUS/PERSONA_WALL_LATERAL_OFFSET moved this session
// (5.1/4.6 -> 5.14/3.73) to close the real >=1.5u edge-to-edge desk gap
// J's capture caught (crew-desk2-0120.png) -- the 3 corner-sharing pairs'
// center-to-center distance moved from 0.85u to 1.994u. Checked against
// this constant before touching it (task's own instruction: remove the
// workaround only if no two desks are within 2.0u any more): 1.994u is
// STILL just under 2.0u, so this workaround stays ACTIVE -- removing it
// now would let two nameplates that sit 1.994u apart (visually close,
// even though their DESKS no longer touch per the new >=1.5u edge gap)
// render on top of each other again. Left in place, unchanged.
const NAMEPLATE_COLLISION_CLEARANCE = 2.0;
// ARC_CENTER is still "the direction that faces the camera most directly"
// -- Gamma's own desk (gammaDeskCenter below, UNCHANGED by this pass) and
// BrainCore both anchor off it. ARC_SPAN (the old 230deg lane-ring arc this
// constant used to pair with) is GONE -- the campus-cross rebuild
// (layout.ts) replaced that whole ring placement, so the arc-span tuning
// history that used to live here no longer applies to anything.
const ARC_CENTER = Math.PI / 2 - BASE_AZIMUTH + ARC_CENTER_NUDGE;
// LAYOUT builder pass (2026-09-14): "Persona desks stay in the hub along
// the 4 wall segments between doors (2-2-2-1 with Gamma at the brain
// wall)." Wall segment k spans armAngle(k)..armAngle(k+1) (centered on
// armAngle(k)+45deg) -- picks whichever segment's own center sits angularly
// closest to ARC_CENTER as "the brain wall" (reserved: Gamma's own desk
// stays near the core, UNCHANGED, so that segment gets zero extra desks
// rather than crowding hers), leaving the other 3 segments for the 6 inner
// personas at 2 apiece (layout.ts#computePersonaWallSlots).
function normalizeAngle(a: number): number {
  const twoPi = Math.PI * 2;
  return ((a % twoPi) + twoPi) % twoPi;
}
const BRAIN_WALL_ARM_INDEX = Math.round(normalizeAngle(ARC_CENTER - Math.PI / 4) / (Math.PI / 2)) % 4;
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
// "ideas-wall" (TWIN-MONITORS pass, 2026-09-15, BUILD worker): re-pointed
// again, from the old SmartBoard's own near-wall spot to
// layout.ts#MONITOR_MOUNT.walkTarget -- the new floor-standing twin-monitor
// stand's own pre-computed "stand toward the hub by MONITOR_WALK_INSET"
// point, so a persona visiting "the ideas wall" still ends up standing in
// front of whichever real display currently occupies that corner (never a
// re-typed literal that could drift from the stand's own position).
const PURPOSEFUL_TARGETS: Record<"ideas-wall" | "core" | "lounge", [number, number, number]> = {
  "ideas-wall": MONITOR_MOUNT.walkTarget,
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
  /** LAYOUT builder pass (2026-09-14): `?preset=bay0`..`?preset=bay7`
   * (Scene.tsx's own fixed `geometry`/`rows` order) -- additive, no
   * keyboard binding (the numeric "0".."7" namespace is already fully
   * spoken for by the overview + 7 persona desks) -- see
   * resolveCameraPresetKey's own `bay` branch. */
  bayPresets: CameraPreset[];
  /** `?preset=hall0`..`?preset=hall3`, one per main spine (Scene.tsx's own
   * `ARMS` order) -- same URL-only, no-keyboard-binding convention as
   * `bayPresets`. */
  hallPresets: CameraPreset[];
  /** CAM-PARAMS pass (2026-09-15): `?camtarget=<walk-graph node id>`
   * resolves against this SAME graph LiveAgents.tsx already walks agents
   * through (Scene.tsx's own `walkGraph`, built once via
   * layout.ts#buildWalkGraph) -- never a second, parallel position lookup. */
  walkGraph: WalkGraph;
}

/** Shared by the keyboard "0".."7" fly-to handler AND the `?preset=` mount
 * hook below -- "0" = the fixed overview pose, "1".."7" index
 * `cameraPresets[0..6]` (Scene.tsx's own fixed [Gamma, ...6 personas]
 * order), "bayN" (N=0..7, URL-only, see CameraRigProps' own comment) index
 * `bayPresets[N]`. Factored out (2026-09-14, P4) so the URL hook can never
 * drift from what pressing the real key does -- every call site resolves
 * the SAME destination through this one function, not several
 * independently-maintained copies of the same lookup. */
function resolveCameraPresetKey(
  key: string, cameraPresets: CameraPreset[], bayPresets: CameraPreset[], hallPresets: CameraPreset[],
): CameraPreset | null {
  if (key === "0") return { camPos: OVERVIEW_CAM_POS, headPos: [DEFAULT_LOOKAT.x, DEFAULT_LOOKAT.y, DEFAULT_LOOKAT.z] };
  if (key >= "1" && key <= "7") return cameraPresets[Number(key) - 1] ?? null;
  const bayMatch = /^bay([0-7])$/.exec(key);
  if (bayMatch) return bayPresets[Number(bayMatch[1])] ?? null;
  const hallMatch = /^hall([0-3])$/.exec(key);
  if (hallMatch) return hallPresets[Number(hallMatch[1])] ?? null;
  return null;
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
function CameraRig({ reducedMotion, rows, geometry, briefMtimeMs, ultra, cameraPresets, bayPresets, hallPresets, walkGraph }: CameraRigProps) {
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
  // CAM-PARAMS pass (2026-09-15): folded `?camtarget=<walk-graph node id>`
  // into this SAME effect -- the target must be resolved before the camera
  // POSITION is computed from it. `?camdist` alone still behaves byte-for-
  // byte as before (targetPos falls back to DEFAULT_LOOKAT's own x/z, which
  // are both 0, so `targetPos[0] + sin*dist` / `targetPos[2] + cos*dist`
  // reduce to the exact old `sin*dist`/`cos*dist` formula). An unknown
  // `?camtarget` id (not in walkGraph.nodes) is silently ignored -- falls
  // back to DEFAULT_LOOKAT, same "fail open, never crash" convention as
  // every other URL-param branch in this file (resolveCameraPresetKey's
  // missing-preset case, etc). `parseCameraParams` (lib/hq-camera-params.ts)
  // owns the pure validation/clamp so it's independently unit-testable.
  useEffect(() => {
    if (!ultra) return;
    const controls = controlsRef.current;
    if (!controls) return;
    const params = parseCameraParams(new URLSearchParams(window.location.search));
    if (params.camDist === undefined && params.camTarget === undefined) return;
    const targetNode = params.camTarget ? walkGraph.nodes.get(params.camTarget) : undefined;
    const targetPos: [number, number, number] = targetNode
      ? targetNode.position
      : [DEFAULT_LOOKAT.x, DEFAULT_LOOKAT.y, DEFAULT_LOOKAT.z];
    const dist = params.camDist ?? CAMERA_DIST_ULTRA;
    camera.position.set(
      targetPos[0] + Math.sin(BASE_AZIMUTH) * dist,
      CAMERA_HEIGHT_ULTRA,
      targetPos[2] + Math.cos(BASE_AZIMUTH) * dist,
    );
    controls.target.set(targetPos[0], targetPos[1], targetPos[2]);
    camera.lookAt(controls.target);
    mode.current = "userFree";
    idleSince.current = null;
  }, [ultra, camera, walkGraph]);

  // CAM-PARAMS pass (2026-09-15): `?tour=0` holds the camera perfectly
  // still -- parks it in the SAME "userFree" + `idleSince = null` state
  // every other one-shot capture override above already uses (never times
  // out back to "auto" -- see the mode state machine's own idle-resume
  // branch below), so a headless capture sequence never lands a frame
  // mid-drift-orbit or mid-director-vignette-pan. Its own effect (not
  // folded into the camdist/camtarget effect above) since `?tour=0` is
  // valid entirely on its own with neither of those params set, and
  // ordering after that effect means it parks the mode AFTER whatever
  // position/target camdist/camtarget already established this same mount,
  // never fighting them. Absent (or any value other than the literal
  // string "0"), this effect no-ops -- byte-for-byte unchanged default.
  useEffect(() => {
    if (!ultra) return;
    const controls = controlsRef.current;
    if (!controls) return;
    const searchParams = new URLSearchParams(window.location.search);
    const params = parseCameraParams(searchParams);
    if (params.tour) return;
    // BUG FIX (2026-09-15, orchestrator captures design-default-1910.png
    // [broken -- inside the hub, near the core/arms] vs
    // design-default-camdist-1940.png [correct overview, via &camdist=48]):
    // `?tour=0` ALONE parked the camera in userFree with NO position write
    // -- it just froze wherever the Canvas' own initial camera happened to
    // be, which is nowhere near the overview pose. `?camdist=`/`?camtarget=`
    // (effect above) and `?cam=` (effect below) each write a real pose
    // before parking; this one didn't. Fix: when NEITHER of those other
    // overrides is present, write the exact SAME pose key "0" already
    // resolves to (OVERVIEW_CAM_POS/DEFAULT_LOOKAT, see
    // resolveCameraPresetKey above) before parking, so a bare `?tour=0`
    // capture matches the proven `?camdist=48` framing byte-for-byte
    // instead of landing inside the hub. Guarded off when camdist/camtarget
    // already ran (never fight that effect's own pose) -- `?cam=`'s own
    // effect is declared AFTER this one, so it still wins if both are
    // present together, same "last-declared override wins" ordering the
    // preset effect below already relies on.
    // `?preset=` counts as a pose param too (2026-09-16): the preset effect
    // below is declared AFTER this one and must win -- see
    // hq-camera-params.ts#shouldParkTourAtOverview's own comment.
    if (shouldParkTourAtOverview(params, searchParams.get("cam") !== null || searchParams.get("preset") !== null)) {
      camera.position.set(...OVERVIEW_CAM_POS);
      controls.target.set(DEFAULT_LOOKAT.x, DEFAULT_LOOKAT.y, DEFAULT_LOOKAT.z);
      camera.lookAt(controls.target);
    }
    mode.current = "userFree";
    idleSince.current = null;
  }, [ultra, camera]);

  // HALLWAY-FIX builder pass (2026-09-14): `?cam=x,y,z,tx,ty,tz` (ultra tier
  // only, dev/capture only) -- an arbitrary camera pose for a headless
  // capture script when no named `?preset=` reaches the shot needed. This
  // pass needs a T-junction from directly above and from inside the
  // junction itself, neither of which any existing preset (0-7, bayN,
  // hallN) frames -- see this task's own "add a dev-only ?cam= override in
  // CameraRig, minimal edit" allowance. SAME `mode.current = "userFree"` /
  // `idleSince = null` parking pattern as `?camdist=` directly above (holds
  // the exact pose indefinitely, never eases back before the capture
  // script's own settle window fires) -- kept as its own effect rather than
  // folded into `?camdist=` since it takes 6 raw numbers and fully replaces
  // both position AND target instead of just scaling one existing distance.
  useEffect(() => {
    if (!ultra) return;
    const controls = controlsRef.current;
    if (!controls) return;
    const raw = new URLSearchParams(window.location.search).get("cam");
    if (raw === null) return;
    const parts = raw.split(",").map(Number);
    if (parts.length !== 6 || parts.some((n) => !Number.isFinite(n))) return;
    const [x, y, z, tx, ty, tz] = parts;
    camera.position.set(x, y, z);
    controls.target.set(tx, ty, tz);
    camera.lookAt(controls.target);
    mode.current = "userFree";
    idleSince.current = null;
  }, [ultra, camera]);

  // World-4 (2026-09-14, P4): `?preset=N` (0-7, ultra tier only, dev/
  // capture only) -- lands the camera exactly where pressing key N would,
  // for a headless capture script that cannot drive the keyboard. Driven
  // through the SAME `flight.current`/"flying" mode machinery the real
  // keyboard handler uses below -- via `resolveCameraPresetKey`, not a
  // second, independently-written destination lookup -- so this can never
  // resolve to a different pose than the key itself would. The 1.2s eased
  // flight settles well inside hq_capture.ps1's own 35s SettleSec window.
  //
  // BUG FIX (same session, caught from a real capture:
  // world4-preset2-1937.png landed at the plain overview, not Pilot's
  // desk): `cameraPresets` is built fresh from `allPersonas` (Scene.tsx's
  // own IIFE below, not memoized) which is EMPTY until the first
  // `/api/hq` response lands -- a plain `[ultra, camera]` dependency array
  // (the `?camdist=NN` effect's own pattern, copied blindly) fires this
  // effect at FIRST mount, almost always before that fetch resolves, so
  // `cameraPresets[1]` (preset "2") was reliably undefined and the whole
  // effect silently no-op'd via `if (!dest) return`. `?camdist=NN` never
  // hit this because IT never reads `cameraPresets` at all. Fixed by
  // depending on `cameraPresets.length` too (0 -> 7 the moment real
  // persona data lands, a plain number so React's own dependency-array
  // comparison actually catches the change, unlike the ARRAY reference,
  // which is new every render regardless) so this effect re-evaluates once
  // real data exists, and a `firedRef` guard so it still only EVER
  // triggers one flight (never re-snaps the camera back on a later poll
  // once the user may have taken over).
  const presetFired = useRef(false);
  useEffect(() => {
    if (!ultra || presetFired.current) return;
    const controls = controlsRef.current;
    if (!controls) return;
    const raw = new URLSearchParams(window.location.search).get("preset");
    if (raw === null) return;
    // LAYOUT builder pass: bay presets are ready as soon as `geometry` is
    // (rows count alone, no persona fetch needed) -- waiting on EITHER
    // array being non-empty (not requiring both) lets `?preset=bay0` land
    // even on a render where personas haven't resolved yet.
    if (cameraPresets.length === 0 && bayPresets.length === 0 && hallPresets.length === 0) return;
    presetFired.current = true;
    const dest = resolveCameraPresetKey(raw, cameraPresets, bayPresets, hallPresets);
    if (!dest) return;
    flight.current = {
      fromPos: camera.position.clone(),
      fromTarget: controls.target.clone(),
      toPos: new THREE.Vector3(...dest.camPos),
      toTarget: new THREE.Vector3(...dest.headPos),
      start: lastElapsed.current,
    };
    mode.current = "flying";
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ultra, camera, cameraPresets.length, bayPresets.length, hallPresets.length]);

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
      // U5 (2026-09-14, coordinator: "Esc stops orbit"): the SAME hand-off
      // OrbitControls' own onStart already performs on a real drag/wheel
      // (mode -> userFree, idleSince cleared so FREE_CAM_IDLE_RESUME_S
      // restarts counting from now) -- a keyboard-only escape hatch for
      // "stop moving the camera", no drag required. Checked before
      // resolveCameraPresetKey (Escape never matches a preset anyway, so
      // this is purely additive, not a priority override of anything real).
      if (e.key === "Escape") {
        mode.current = "userFree";
        idleSince.current = lastElapsed.current;
        return;
      }
      const dest = resolveCameraPresetKey(e.key, cameraPresets, bayPresets, hallPresets);
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
  }, [ultra, cameraPresets, bayPresets, hallPresets, camera]);

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
        // U5 (2026-09-14): fires the SAME frame the orbit actually resumes --
        // Hud.tsx reads this transient timestamp via subscribeAutoOrbitResumed
        // to show a brief hint ("camera moving again") right when it happens,
        // never a second independently-timed countdown that could drift from
        // this real one.
        reportAutoOrbitResumed();
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
  // PERSONA-VISIT pass (2026-09-15, queue item g): "on arrival at a persona
  // zone, the persona's bubble shows a short acknowledgement for ~4s ...
  // must not replace the persona's own status for longer than that". Real
  // per-frame ARRIVAL detection lives inside Agent.tsx's own useFrame
  // movement code, which this pass is explicitly barred from touching (see
  // this task's own "DO NOT change walking/slot/follow/wait logic" rule) --
  // so this uses the same server-computed signal LiveAgents.tsx already
  // renders from (`data.liveAgents[].interaction`, lib/hq-agents.ts's own
  // stable, stickiness-debounced target) as a wall-clock-gated proxy: the
  // first render where a given live agent id's interaction names THIS
  // persona starts a 4s window (keyed by agent id, so a different agent
  // targeting the same persona later restarts its own window rather than
  // reusing a stale timestamp). A plain ref (not state) -- display-only
  // side table, never a reason to re-render on its own; read once per
  // render inside the persona map below, same convention as every other
  // *Ref in this file.
  const personaGreetingSinceRef = useRef<Map<PersonaId, { agentId: string; sinceMs: number }>>(new Map());
  // CREW-WORKING pass (2026-09-15/16): huddle-pair state, same "plain ref,
  // mutated in render-time code, read the same render" convention as
  // `personaGreetingSinceRef` immediately above (a room-wide fact detected
  // ONCE per poll here, never duplicated per-persona the way Agent.tsx's own
  // seen-value-diff triggers are). `prevGreenCountRef` is the count from the
  // LAST render (crewWorking.ts#detectHuddleTrigger only fires on a genuine
  // <2 -> >=2 crossing); `activeHuddleRef` holds the currently (or most
  // recently) triggered pair + its own unique key, which Agent.tsx's
  // existing `walkPlanKey` seen-value-diff turns into exactly one walk.
  const prevGreenCountRef = useRef(0);
  const activeHuddleRef = useRef<{ key: string; pair: [string, string] } | null>(null);
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

  // UX-1 U3 (2026-09-14): which world target (if any) the cursor is
  // currently hovering -- a plain useState (not a ref), same "state for
  // discrete moments" convention this whole file already uses (walking/
  // dwelling/pointing in Agent.tsx, coreReady above): hover start/stop are
  // discrete pointer events, not continuous per-frame values, and the
  // tooltip's own rendered children must re-render when this changes.
  // Discriminated union (never a bare index) so "gamma" doesn't need to
  // fake a lane/persona index that doesn't apply to her.
  const [hoveredTarget, setHoveredTarget] = useState<
    { kind: "bay"; index: number } | { kind: "persona"; index: number } | { kind: "gamma" } | null
  >(null);
  // UX-1 U3: the OTHER half of the hover-pulse mechanism -- Hud.tsx's own
  // crew-card onMouseEnter/onMouseLeave publish here (lib/hq-hover-
  // persona.ts, already committed); this is the Canvas-side consumer.
  // useSyncExternalStore (not a plain read) because this store changes from
  // OUTSIDE React's own render cycle (a DOM event handler in Hud.tsx,
  // sibling to this whole <Canvas> tree, not a parent/child) -- the same
  // cross-Canvas-boundary external-store pattern this codebase already uses
  // for hq-live-perf.ts/hq-first-frame.ts/hq-camera-mode.ts. Index 0 =
  // Gamma, 1-6 = innerPersonas[0..5] -- see that store's own header for why
  // this fixed offset needs no separate lookup table.
  const hudHoveredIndex = useSyncExternalStore(subscribeHoveredPersonaIndex, getHoveredPersonaIndex);

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
  // Kit rebuild: the ultra tier's real chair sits at BAY_SEAT_LOCAL_BAY
  // (inside a <DeskCluster> offset BAY_DESK_OFFSET_Z_BAY back from the
  // module's own local origin -- see StationModule.tsx), NOT the old -0.15
  // tuned for the TV tier's bare procedural desk box. TV tier is unchanged.
  // DESK-ROWS pass (2026-09-15): BAY_SEAT_LOCAL_BAY (not the shared
  // BAY_SEAT_LOCAL persona desks/Gamma's own desk still use) -- keeps this
  // agentHome in sync with StationModule.tsx's own desk offset fix
  // (audit desk_clearance) without moving any hub-side desk's own seat.
  const seatLocal = ultra ? BAY_SEAT_LOCAL_BAY : TV_LANE_SEAT_LOCAL;

  const slotCount = Math.max(rows.length, 1);
  // LAYOUT builder pass (2026-09-14, campus-cross rebuild): each bay's own
  // position/rotation now comes from layout.ts#computeAllBaySlots (4 arms x
  // 2 sides, every corridor meeting a real hub doorway) instead of a point
  // on the old 8-way ring -- see that module's own header for the full
  // writeup. `agentHome` is still computed the SAME way (localToWorld from
  // this slot's own position/rotationY) so the "scene-root sibling, never
  // nested" fix that comment used to describe stays exactly as true as it
  // always was, just fed different input geometry.
  const geometry = useMemo(
    () =>
      computeAllBaySlots(slotCount).map((slot) => ({
        ...slot,
        agentHome: localToWorld(slot.position, slot.rotationY, seatLocal),
      })),
    [slotCount, seatLocal],
  );

  // One accent moment (2026-09-13): when the brain is genuinely busy (GPU
  // util > 30%), BrainCore runs its own "brighter rings" pulse faster from
  // this same value. (PEOPLE pass, 2026-09-14: the matching corridor-pulse
  // half of this comment -- `corridorSpeedBoost`, fed to the now-deleted
  // `<Corridor>` -- is gone with Corridor.tsx; `utilPct` itself is still
  // read below by BrainCore and the alert/thinking derivations.)
  const utilPct = data?.brainVitals.gpu.util_pct ?? null;

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
  // World-4 fix (P3, 2026-09-14): hoisted so BrainCore's wall line and
  // GammaCharacter's speech bubble read the IDENTICAL "next:" value (both
  // used to call crewNextLine independently -- harmless in practice since
  // it's a pure function of `nowMs`, but a single shared value is strictly
  // safer and is what "derive from the same source" (P3) actually asks
  // for). `Date.now()` read once here, same as this file's pre-existing
  // per-render (never per-frame) clock-read convention.
  const managerNextLine = allPersonas[0] ? crewNextLine(allPersonas[0], Date.now()) : null;
  const innerPersonas = allPersonas.slice(1);
  const personaSlotCount = Math.max(innerPersonas.length, 1);
  // LAYOUT builder pass (2026-09-14): "Persona desks stay in the hub along
  // the 4 wall segments between doors" -- see BRAIN_WALL_ARM_INDEX's own
  // comment above for the segment-picking logic. DESK-RING pass (2026-09-15,
  // BUILD worker): PERSONA_WALL_RADIUS moved 6.5 -> 4.1 (layout.ts's own
  // header has the full derivation -- the table's VISIBLE center now lands
  // at radius 5.5, clear of HUB_WALL_RADIUS=7.5) -- the camera-preset "pull"
  // math further down (deskRadius/outwardRoom) is a generic function of
  // whatever this radius is, so it still needs no manual change, just a
  // smaller `outwardRoom` input; verified the branch/clamp still keeps the
  // camera well inside the wall at the new radius (see that math's own
  // inline comment).
  const personaGeometry = useMemo(
    () =>
      computePersonaWallSlots(personaSlotCount, BRAIN_WALL_ARM_INDEX).map((slot) => ({
        position: slot.position,
        rotationY: slot.rotationY,
        agentHome: localToWorld(slot.position, slot.rotationY, personaSeatLocal),
      })),
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

  // LAYOUT builder pass (2026-09-14): the walk graph (layout.ts's own
  // "Walk graph" section) -- nodes for every real destination this scene
  // walks a persona to (hub doorways/T-junctions/bay doors+desks, persona
  // desks, Gamma's own hub-meet spot, the smart board, the 3 ambient
  // hub-interior points) plus every hallway/hub-interior edge between
  // them. `eventWalk`/`computePurposefulWalk`'s OWN destinations below now
  // resolve THROUGH this graph (findPersonaHome, the
  // ideas-wall/core/lounge/neighbor lookups) instead of a second,
  // separately-maintained set of position lookups -- the single structure
  // the task asks for, not a parallel one that could drift from it.
  // Agent.tsx's own walk consumer still only takes ONE final target point
  // today (MOTION-2 owns wiring it to the FULL `waypoints` array -- see
  // types.ts#WalkPlan's own header); every lookup below still resolves to
  // the exact same point it always did for every CURRENT trigger (all
  // hub-interior, a single hop), so this is a safe, additive foundation,
  // not a behavior change. Memoized on the same referentially-stable
  // building blocks as everything else in this file (geometry/
  // personaGeometry are already stable across a no-op poll; gammaHubMeet is
  // a fresh array every render but numerically constant, so its two scalar
  // components -- not the array reference -- are the dependency, same
  // convention BaySign.tsx's own worldPosVec memo already uses).
  // CREW-WORKING pass (2026-09-15/16): the round table's real world center --
  // SAME derivation as computeMonitorMount above (the table sits at the
  // brain wall's own 45deg segment-center angle, HUB_TABLE_RADIUS out from
  // HUB, per layout.ts#HUB_TABLE_RADIUS's own header) -- and the SAME value
  // HubInterior.tsx#TABLE_CENTER derives (that file is off-limits to this
  // pass; this reproduces its formula from the two constants that already
  // live here, never a re-typed literal position).
  const tableCenter: [number, number, number] = useMemo(() => {
    const segCenterAngle = armAngle(BRAIN_WALL_ARM_INDEX) + Math.PI / 4;
    return [Math.cos(segCenterAngle) * HUB_TABLE_RADIUS, 0, Math.sin(segCenterAngle) * HUB_TABLE_RADIUS];
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // BRAIN_WALL_ARM_INDEX/HUB_TABLE_RADIUS are both module-level constants
  const walkGraph = useMemo(
    () =>
      buildWalkGraph({
        baySlots: geometry,
        personaSlots: innerPersonas.map((p, i) => ({
          name: p.name,
          position: (personaGeometry[i] ?? personaGeometry[0]).agentHome,
        })),
        gammaDeskPos: gammaHubMeet,
        tableCenterPos: tableCenter,
        // TWIN-MONITORS pass (2026-09-15): the "smart-board" walk-graph node
        // (lib/hq-agents.ts#ZONE_NODE_ID's "build" zone target) used to sit
        // at WALL_POS itself (y=3.4 -- a point up on the wall, not a floor
        // position an agent can stand at). Re-pointed to the new stand's own
        // walk target (layout.ts#MONITOR_MOUNT.walkTarget, y=0, ~1.2u toward
        // the hub from the stand) so a "build zone" walk actually lands on
        // real floor in front of whichever display now occupies the corner.
        smartBoardPos: MONITOR_MOUNT.walkTarget,
        ambientPoints: PURPOSEFUL_TARGETS,
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [geometry, personaGeometry, innerPersonas.map((p) => p.name).join("|"), gammaHubMeet[0], gammaHubMeet[2]],
  );
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
  const findPersonaHome = (name: string): [number, number, number] | undefined =>
    walkGraph.nodes.get(`persona-${name}`)?.position;
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
    // DESK-PRESETS pass (2026-09-15): each entry now also carries the
    // desk's own facing `rotationY` where one exists (every persona desk --
    // `null` for Gamma's own desk, whose preset math below is UNCHANGED,
    // per this pass' own scope: only the persona-wall-slot desks moved in
    // commit 31cc19b5, Gamma's desk did not). Carrying rotationY alongside
    // the position (instead of re-deriving it from `pos` further down) is
    // the whole fix -- see lib/hq-desk-preset-pure.ts's own header for why
    // `pos - HUB` stopped being a valid stand-in for "the desk's own facing
    // direction" once persona desks moved off the ring.
    const deskEntries: Array<{ pos: [number, number, number]; rotationY: number | null }> = [];
    if (allPersonas[0]) deskEntries.push({ pos: gammaDeskCenter, rotationY: null });
    innerPersonas.forEach((_, i) => {
      const slot = personaGeometry[i] ?? personaGeometry[0];
      deskEntries.push({ pos: slot.agentHome, rotationY: slot.rotationY });
    });
    return deskEntries.map(({ pos, rotationY }): CameraPreset => {
      const headPos: [number, number, number] = [pos[0], pos[1] + headOffset, pos[2]];
      if (rotationY !== null) {
        // Persona wall-slot desk -- derive the pose from the desk's OWN
        // facing normal (see lib/hq-desk-preset-pure.ts), not the hub
        // radial the Gamma-desk branch below still uses.
        return computeDeskFacingCameraPose({
          deskPos: pos,
          rotationY,
          headPos,
          roomHalfExtent: HUB_WALL_RADIUS - 0.8,
          standPositionXZ: [MONITOR_MOUNT.standPosition[0], MONITOR_MOUNT.standPosition[2]],
        });
      }
      const deskRadius = Math.hypot(pos[0] - HUB[0], pos[2] - HUB[2]);
      const dirX = deskRadius > 0.001 ? (pos[0] - HUB[0]) / deskRadius : 0;
      const dirZ = deskRadius > 0.001 ? (pos[2] - HUB[2]) / deskRadius : 1;
      const outwardRoom = HUB_WALL_RADIUS - 1.0 - deskRadius;
      // World-4 fix (P4/P6, 2026-09-14, real capture world4-preset4-2005.png:
      // a preset-4 flight landed the camera looking at the desk screen's
      // BACK -- a dark, featureless panel, no headline/sub/age text visible
      // at all). Root cause: this branch pulled the camera INWARD (toward
      // the hub) whenever there wasn't 2.5+ units of outward room -- true
      // for every inner-ring persona desk (outwardRoom lands at/near 0 for
      // PERSONA_RING_RADIUS=6.5 against HUB_WALL_RADIUS-1.0). Once P6's own
      // Agent.tsx fix (this same session) made a resting character correctly
      // face AWAY from the hub -- the established convention this file's
      // own GammaCharacter.tsx/Agent.tsx alert-phase already use elsewhere,
      // and DeskCluster's screen is mounted facing that SAME seated
      // character (see SetKit.tsx#DeskCluster) -- a camera parked on the
      // HUB side (this branch's old negative pull) sits BEHIND both the
      // character and the screen relative to their shared facing, so it can
      // only ever see their backs. Fixed to pull OUTWARD instead (same side
      // the character/screen now face), but capped far more conservatively
      // than the >2.5-outwardRoom branch's own up-to-3.5 -- 0.6 is the
      // largest step that still clears HUB_WALL_RADIUS by a real margin
      // (deskRadius 6.5 + 0.6 = 7.1, HUB_WALL_RADIUS 7.5) even at
      // outwardRoom's worst real value (0) -- verified against the room-wall
      // radius directly, not the old 3.5's untested assumption for this
      // branch. UNVERIFIED beyond that math: this specific change was not
      // re-confirmed against a fresh capture (this session's own capture
      // budget was already spent on P1/P2/P3/P6 verification) -- flag for a
      // follow-up capture next session if the screen still doesn't read.
      const pull = outwardRoom > 2.5 ? Math.min(3.5, outwardRoom) : Math.min(0.6, Math.max(0.2, outwardRoom + 0.6));
      const camPos: [number, number, number] = [headPos[0] + dirX * pull, headPos[1] + 4.2, headPos[2] + dirZ * pull];
      return { headPos, camPos };
    });
  })();

  // LAYOUT builder pass (2026-09-14, campus-cross rebuild, PROOF
  // requirement: "two bay presets... look through the door at the desk"):
  // one preset per lane bay, additive alongside the existing "0".."7"
  // persona/overview keys -- reachable via `?preset=bay0`..`?preset=bay7`
  // (resolveCameraPresetKey's own `bay` prefix branch below), index-aligned
  // with `geometry`/`rows`.
  //
  // Bug fix (2 real captures, layout-bay0-1741.png and -1748.png): a
  // ground-level shot standing on the doorway's own centerline, at any
  // standoff distance tried, looked straight through BaySign's own bright,
  // unlit, toneMapped=false door sign (mounted just inside the door,
  // StationModule.tsx/BaySign.tsx, not this pass' own) -- a plane that size
  // at head height dominates a level sightline down a hallway no matter how
  // far back the camera stands. Rather than keep guessing standoff/lateral
  // numbers against a 40s-per-iteration real-capture loop, switched to the
  // SAME proven elevated-3/4-angle formula the persona desk presets above
  // already use successfully (UP well above the sign's own y=2.3, looking
  // DOWN at the desk) -- the sign ends up low in frame, read as part of the
  // room instead of blocking the shot.
  const BAY_PRESET_STANDOFF = 3.0; // horizontal pull-back, outward through the door
  const BAY_PRESET_HEIGHT = 4.4; // clears BaySign's own y=2.3 with real margin
  const bayPresets: CameraPreset[] = geometry.map((slot): CameraPreset => {
    const dx = slot.tCenter[0] - slot.position[0];
    const dz = slot.tCenter[2] - slot.position[2];
    const dlen = Math.hypot(dx, dz) || 1;
    const outX = dx / dlen;
    const outZ = dz / dlen;
    const headPos: [number, number, number] = [slot.agentHome[0], slot.agentHome[1] + 0.9, slot.agentHome[2]];
    const camPos: [number, number, number] = [
      slot.doorWorldPos[0] + outX * BAY_PRESET_STANDOFF, BAY_PRESET_HEIGHT, slot.doorWorldPos[2] + outZ * BAY_PRESET_STANDOFF,
    ];
    return { headPos, camPos };
  });

  // LAYOUT builder pass: one preset per main spine, PROOF requirement's own
  // "one hallway close-up" -- reachable via `?preset=hall0`..`?preset=hall3`
  // (resolveCameraPresetKey's own `hall` prefix branch below).
  //
  // Bug fix (real capture layout-hall0-1758.png, UNVERIFIED past this point
  // -- this session's 7-capture budget was spent, see this pass' own final
  // report): looking back toward the hub doorway put the hub's own OPEN
  // interior (persona desks sat just inside it at the time, PERSONA_WALL_
  // RADIUS=6.5 vs the wall at HUB_WALL_RADIUS=7.5, only 1u past the
  // threshold -- DESK-RING pass 2026-09-15 later moved this to 4.1, see
  // layout.ts's own header; the "open interior visible through a doorway"
  // finding this comment documents is unaffected either way) in the
  // sightline beyond that opening -- an open doorway doesn't block the
  // view, so the shot read as "inside the hub" rather than "a hallway."
  // Flipped to look the OTHER way (toward the T-junction, away from the
  // hub) and moved the camera to just past the hub's own doorway instead of
  // the spine's midpoint, so the corridor's own rails/floor/kit segments
  // recede down the frame ahead of the camera -- the standard "vanishing
  // point down a corridor" composition -- with the T-junction/bay doors as
  // the far focal point instead of an open doorway that reads as "not a
  // hallway, a room."
  const HALL_PRESET_ENTRY = 2.0; // just past the hub's own doorway, into the hallway
  const HALL_PRESET_LATERAL = 0.7; // off the centerline (both rails visible, not straddled)
  const hallPresets: CameraPreset[] = ARMS.map((arm): CameraPreset => {
    const dirX = Math.cos(arm.mainAngle);
    const dirZ = Math.sin(arm.mainAngle);
    const perp = arm.mainAngle + Math.PI / 2;
    const sideX = Math.cos(perp) * HALL_PRESET_LATERAL;
    const sideZ = Math.sin(perp) * HALL_PRESET_LATERAL;
    const camPos: [number, number, number] = [
      arm.hubDoorPos[0] + dirX * HALL_PRESET_ENTRY + sideX, 1.6, arm.hubDoorPos[2] + dirZ * HALL_PRESET_ENTRY + sideZ,
    ];
    const headPos: [number, number, number] = [arm.tNearEdge[0], 1.5, arm.tNearEdge[2]];
    return { headPos, camPos };
  });

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
  // PERSONA-VISIT pass (2026-09-15): the ~4s acknowledgement-bubble window
  // for each persona currently being visited by a live agent (see
  // personaGreetingSinceRef's own header above for why this is a wall-clock
  // proxy rather than real arrival detection). Recomputed each render from
  // the CURRENT liveAgents list + the ref's own prior state -- a persona
  // absent from this map this render either has no visitor right now, or
  // its window has already expired, either way `personaBubbleAction`'s
  // normal evidence-backed pill takes over unmodified.
  const PERSONA_GREETING_WINDOW_MS = 4000;
  const personaGreetingText = new Map<PersonaId, string>();
  for (const liveAgent of data?.liveAgents ?? []) {
    if (!liveAgent.interaction) continue;
    const personaId = liveAgent.interaction.personaId;
    const prior = personaGreetingSinceRef.current.get(personaId);
    const sinceMs = prior && prior.agentId === liveAgent.id ? prior.sinceMs : nowMsForWalks;
    personaGreetingSinceRef.current.set(personaId, { agentId: liveAgent.id, sinceMs });
    if (nowMsForWalks - sinceMs <= PERSONA_GREETING_WINDOW_MS) {
      const identity = liveAgentIdentity(liveAgent.label, liveAgent.id);
      personaGreetingText.set(personaId, `↔ ${identity.displayName}`);
    }
  }
  const ideasCount = data?.ideas.cards.length ?? 0;
  // CREW-WORKING pass (2026-09-15/16, item 4): huddle pair -- fires ONLY on
  // a real <2 -> >=2 GREEN transition (crewWorking.ts#detectHuddleTrigger),
  // never a timer. `prevGreenCountRef`/`activeHuddleRef` are mutated here,
  // in plain render-time code, the SAME convention `personaGreetingSinceRef`
  // above already uses (never a useEffect -- this file has no per-frame
  // hook of its own to defer into, and every other cross-render diff in
  // this component already works this way).
  const greenNow: HuddleCandidate[] = innerPersonas
    .filter((p) => p.status === "GREEN")
    .map((p) => ({ name: p.name, lastFireISO: p.lastFireISO }));
  const huddleTrigger = detectHuddleTrigger(greenNow, prevGreenCountRef.current, nowMsForWalks);
  prevGreenCountRef.current = greenNow.length;
  if (huddleTrigger.key && huddleTrigger.pair) {
    activeHuddleRef.current = { key: huddleTrigger.key, pair: huddleTrigger.pair };
  }
  const activeHuddle = activeHuddleRef.current;
  // 1.2u apart (task spec) straddling the table's near (hub-facing) side,
  // HUB_TABLE_RADIUS(2.1) minus 1.0 so the pair stands just inside the
  // table's own radius, not out in the open room.
  const huddleSpots = activeHuddle ? huddleStandPoints(tableCenter, HUB, HUB_TABLE_RADIUS - 1.0, 1.2) : null;
  const purposefulWalks = innerPersonas.map((persona, i) => {
    const neighborIndex = innerPersonas.length > 1 ? (i + 1) % innerPersonas.length : -1;
    const neighbor = neighborIndex >= 0 ? innerPersonas[neighborIndex] : null;
    const walk = computePurposefulWalk(persona.name, nowMsForWalks, ideasCount, persona.lastFireISO, neighbor?.name ?? null);
    // LAYOUT builder pass: both branches now resolve through walkGraph
    // instead of a separate PURPOSEFUL_TARGETS-only lookup + a direct
    // personaGeometry read -- see walkGraph's own comment above.
    //
    // BLOCKY-FIXES pass (2026-09-16): the "neighbor" case used to be
    // `findWalkPath(walkGraph, persona-A, persona-B)?.pop()` -- the LAST
    // node on that path is `persona-B`'s own walk-graph node, registered at
    // EXACTLY the neighbor's own seat position (layout.ts's
    // `addNode(persona-${p.name}, p.position)`, fed
    // `innerPersonas.map(... position: agentHome ...)` below -- i.e. the
    // neighbor's own chair). A visiting persona was parked ON the seated
    // neighbor -- two bodies at one point, the real "two personas on one
    // desk" defect a live capture caught (crew-desk2-0120.png). Fixed by
    // standing 1.0u to the SIDE of the neighbor's seat instead
    // (crewWorking.ts#neighborStandPoint, same tangent formula
    // computePersonaWallSlots already uses to space two desks on one wall)
    // -- `personaGeometry[neighborIndex]` (defined below in this same
    // render, one hub-interior leaf per persona) has both the seat position
    // AND the desk's own rotationY this needs.
    const fallback = findPersonaHome(persona.name) ?? HUB;
    const neighborGeom = neighborIndex >= 0 ? personaGeometry[neighborIndex] : undefined;
    const target: [number, number, number] =
      walk.destination === "neighbor" && neighbor && neighborGeom
        ? neighborStandPoint(neighborGeom.agentHome, neighborGeom.rotationY)
        : walk.destination === "neighbor"
          ? fallback
          : walkGraph.nodes.get(`ambient-${walk.destination}`)?.position ?? PURPOSEFUL_TARGETS.lounge;
    return { walk, target };
  });

  // Company audit (commit 58d0b9c6, coordinator 2026-09-13: "the roster
  // must show ghosts as ghosts") -- matched by name onto PersonaState.
  // `data.audit` is included in page.tsx's sceneData content key, so this
  // reference is stable across no-op polls same as everything else here.
  const auditByName = useMemo(() => new Map((data?.audit?.personas ?? []).map((a) => [a.name, a] as const)), [data?.audit]);

  // HEAD-LABELS pass (2026-09-15): each persona's real model-tier glyph,
  // from `data.runtime.roles` (lib/hq-runtime.ts#HqRoleRuntime -- the SAME
  // classified runtime/producer facts Hud.tsx's TRUTH header already
  // reads), matched by name. Computed once per poll, not per-persona-per-
  // render, so 6 personas re-rendering doesn't re-derive this 6 times.
  // `runtime`/`producer` are read live (never guessed) -- see
  // headLabelModel.ts#modelGlyph's own doc comment for what each runtime
  // kind maps to and why `claude-session`'s tier is only ever parsed from
  // this real `producer` string.
  const modelGlyphByPersona = useMemo(
    () => new Map((data?.runtime?.roles ?? []).map((r) => [r.name, modelGlyph(r.runtime, r.producer)] as const)),
    [data?.runtime?.roles],
  );

  // PEOPLE pass (P2/P3, 2026-09-14): the old activityCandidates memo (a
  // separate ranked/fading bubble LAYER feeding the now-deleted
  // ActivityBubbleLayer.tsx) is gone -- each bubble now lives INSIDE its own
  // walker (Agent.tsx/GammaCharacter.tsx's own <Html> child, travels with
  // the mesh) instead of a fixed-point overlay. What that memo computed is
  // now computed WHERE it's consumed: `laneBubbleAction`/`personaBubbleAction`
  // (bubbleText.ts, real evidence only -- same two sources Hud.tsx's roster
  // panel reads) inline per row/persona below, and this small helper for the
  // rotational purposeful-walk's destination label (unchanged wording from
  // the old memo).
  const purposefulDestLabel = (destination: (typeof purposefulWalks)[number]["walk"]["destination"]): string =>
    destination === "ideas-wall" ? "ideas wall" : destination === "core" ? "core" : destination === "neighbor" ? "neighbor" : "lounge";

  // INTERACT-2 (I2 c-f)'s 4 named-event-walk reason phrases, by SOURCE
  // persona name -- unchanged wording from the old memo's `namedBubbles`
  // array, just re-shaped as "-> destination · reason" (no leading persona
  // name: Agent.tsx's own bubble JSX already bolds `laneSeed` as that name,
  // so repeating it here would read "Scout · Scout -> Pilot: ..."). Freshness
  // gating (the old ageMin >= EVENT_BUBBLE_WINDOW_MIN check) is no longer
  // needed here -- Agent.tsx snapshots this text ONLY at the instant its own
  // eventWalkEventKey trigger actually fires (the real gate), not on a
  // separate re-evaluated timer.
  const NAMED_WALK_REASON: Record<string, string> = {
    Scout: "-> Pilot · fresh catalyst read",
    Analyst: `-> Chef · your queue: ${data?.desks?.Analyst?.headline ?? "new digest"}`,
    Treasurer: `-> Gamma · ${data?.desks?.Treasurer?.headline ?? "new report"}`,
    Pilot: "-> Analyst · day's decisions in, handing off",
  };

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
        bayPresets={bayPresets}
        hallPresets={hallPresets}
        walkGraph={walkGraph}
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
          Suspense needed (pure procedural geometry, no useGLTF load).
          LAYOUT builder pass (campus-cross rebuild): now a union footprint
          (central hub circle + 4 arm slabs), sized from layout.ts's own
          exported dimensions -- all three already apron-inclusive. */}
      {/* DECLUTTER pass (2026-09-14): mounted EXACTLY ONCE, anywhere inside
          this <Canvas> tree -- resolves screen-space overlaps for every
          registered label (persona/lane bubbles, Gamma, live agents, the
          BrainCore plaque) via the shared registry (useLabelDeclutter.ts).
          Renders nothing (`return null`), tier-agnostic (registration is a
          no-op with zero visible labels on the TV tier, so this is safe to
          always mount). */}
      <LabelDeclutterManager />

      {ultra && (
        <Plaza
          centerRadius={PLAZA_CENTER_RADIUS}
          armLen={ARM_LEN + PLAZA_APRON}
          armHalfWidth={ARM_HALF_WIDTH + PLAZA_APRON}
          dayFactor={nightFactor}
        />
      )}

      {ultra && (
        <Suspense fallback={null}>
          <HubRoom dayFactor={nightFactor} />
        </Suspense>
      )}

      {/* UX-1 U2 (2026-09-14): "clicking the hub flies to the overview" --
          BrainCore renders on BOTH tiers (unchanged), so the click/hover
          wrapper uses the SAME conditional clickableGroupProps(ultra, ...)
          pattern as the bay/persona groups above, not the Gamma IIFE's
          unconditional form. Key "0" = the fixed wide overview pose
          (resolveCameraPresetKey's own literal "0" branch) -- distinct from
          Gamma's own key "1" above. */}
      <group {...clickableGroupProps(ultra, "0", () => setHoveredTarget(null), () => setHoveredTarget(null))}>
      <BrainCore
        utilPct={data?.brainVitals.gpu.util_pct ?? null}
        memUsedMib={data?.brainVitals.gpu.mem_used_mib ?? null}
        memTotalMib={data?.brainVitals.gpu.mem_total_mib ?? null}
        modelName={data?.brainVitals.models[0]?.name ?? null}
        manager={allPersonas[0] ?? null}
        briefMtimeMs={data?.brief.mtime_ms ?? null}
        // World-4 fix (P3, 2026-09-14): the SAME loop-ledger row + "next:"
        // line GammaCharacter's own bubble reads below (`managerNextLine`,
        // hoisted so both consumers see the identical value) -- see
        // BrainCore.tsx's own wallStatusLine comment for why this replaces
        // the old modelName-presence "BRAIN IDLE" fallback.
        lastRow={data?.brainVitals.lastRow ?? null}
        nextLine={managerNextLine}
        // BRAIN-TRUTH fix (2026-09-15) -- the Ollama-`ollama ps`-verified
        // truth Hud.tsx's side panel already reads (data.runtime.brain
        // .busy), now the plaque's own sole "thinking" source too. See
        // BrainCore.tsx's own `brainBusy` prop comment for the full
        // root-cause this replaces.
        brainBusy={data?.runtime.brain.busy ?? false}
        gaming={gaming}
        dimFactor={dimFactor}
        reducedMotion={reducedMotion}
        ultra={ultra}
        coreMeshRef={coreMeshRef}
        // MODELS builder S2 pass (2026-09-14, coordinator-authorized edit):
        // real data for HubInterior.tsx's sectors+trading wall panel --
        // BrainCore.tsx forwards both straight through, no re-derivation
        // here. sectorsSnapshot is genuinely null before CREW-RIG's first
        // Station fire (lib/hq.ts#readSectorsSnapshot's own fail-open
        // contract); `data.trading` is the existing item-5 strip payload,
        // non-optional on HqApiResponse but `data` itself can be undefined
        // during initial load.
        sectorsSnapshot={data?.sectorsSnapshot ?? null}
        trading={data?.trading ?? null}
      />
      </group>

      {/* Gamma's own character + desk + speech bubble (Pass B, 2026-09-13)
          -- ultra tier only, same reasoning as every other real-kit-geometry
          piece in this scene (TV tier keeps BrainCore's plaque-only
          depiction, no draw-call budget for a 15th character body). */}
      {ultra && (() => {
        // PEOPLE pass (P2, 2026-09-14): find WHICH hub-exchange event (if
        // any) is still fresh (same EVENT_BUBBLE_WINDOW_MIN age check the
        // old activityCandidates memo's hubExchanges.forEach used) -- not
        // just a boolean, since GammaCharacter now needs the event's own
        // `kind` to look up its real ack line (GAMMA_CREW_ACK above) rather
        // than merely hiding her bubble while one is active.
        const activeGammaExchange = [latestChefVerdict, latestCoachSectors].find((event) => {
          if (!event) return false;
          const ageMin = minutesSinceEvidence(event.ts_et);
          return ageMin !== null && ageMin < EVENT_BUBBLE_WINDOW_MIN;
        }) ?? null;
        return (
        // UX-1 U2/U3 (2026-09-14): this whole IIFE is already `{ultra && ...}`-
        // gated by its own caller, so the handlers below are unconditional
        // (no clickableGroupProps ternary needed -- this branch never
        // reaches the TV tier at all). Key "1" = cameraPresets[0] = Gamma's
        // own preset (she's a persona/character like any other for this
        // purpose, per the original U2 spec's own "character" wording) --
        // distinct from key "0" (the wide hub overview, wired on BrainCore
        // below), matching how clicking any OTHER character flies to THEIR
        // own preset rather than a generic wide shot.
        <group {...clickableGroupProps(true, "1", () => setHoveredTarget({ kind: "gamma" }), () => setHoveredTarget((cur) => (cur?.kind === "gamma" ? null : cur)))}>
          <GammaCharacter
            deskCenter={gammaDeskCenter}
            rotationY={gammaRotationY}
            accentColor={allPersonas[0]?.color ?? PALETTE.hubCore}
            lastRow={data?.brainVitals.lastRow ?? null}
            nextLine={managerNextLine}
            ackOverride={activeGammaExchange ? (GAMMA_CREW_ACK[activeGammaExchange.kind] ?? "logged, thanks") : null}
            briefText={data?.brief.text ?? ""}
            briefMtimeMs={data?.brief.mtime_ms ?? null}
            utilPct={data?.brainVitals.gpu.util_pct ?? null}
            modelName={data?.brainVitals.models[0]?.name ?? null}
            gaming={gaming}
            brainBusy={data?.runtime.brain.busy ?? false}
          />
        </group>
        );
      })()}

      {/* LAYOUT builder pass (2026-09-14, campus-cross rebuild): the
          hallway SKELETON -- 4 main spines (hub doorway -> T-junction) +
          their T-junction pieces -- rendered ONCE per arm, independent of
          `rows` (a spine is shared by both of its arm's bays, so it must
          not be drawn twice, once per bay, the way the old per-lane loop
          implicitly did). `ARMS` is the module-level constant above (fixed
          geometry, never recomputed). See layout.ts's own header for why
          every one of these 4 hallways now meets a real hub doorway. */}
      {ultra && ARMS.map((arm) => (
        <Suspense key={arm.armIndex} fallback={null}>
          <CorridorRun from={arm.hubDoorPos} to={arm.tNearEdge} dayFactor={nightFactor} wide />
          <TJunction position={arm.tCenter} rotationY={arm.rotationY} dayFactor={nightFactor} />
        </Suspense>
      ))}

      {/* GATE-PROP pass (2026-09-15): set dressing for the live-agent walk
          graph's own "campus-gate" node (layout.ts#buildWalkGraph) -- see
          SetKit.tsx#CampusGate's own header. Position/rotation/scale all
          come from layout.ts (derived from ARM_LEN/PLAZA_APRON, never a
          literal here); registers into HubRoom's already-mounted gate-door
          InstancedKitPool, so this adds zero new draw calls. Ultra tier
          only, matching every other architecture piece on this arm. */}
      {ultra && (
        <Suspense fallback={null}>
          <CampusGate position={CAMPUS_GATE_POSITION} rotationY={CAMPUS_GATE_ROTATION_Y} scale={CAMPUS_GATE_SCALE} />
        </Suspense>
      )}

      {rows.map((row, i) => {
        const slot = geometry[i] ?? geometry[0];
        const behavior = deriveBehavior(row, gaming);
        // PEOPLE pass (P2/P3): the old ambient-pulse `<Corridor>` (2 hops,
        // bay -> T-junction -> hub doorway) is REMOVED per J's own "the
        // traveling orbs can go too" -- Corridor.tsx itself is deleted
        // below this commit's own file list; this bay's real hallway
        // GEOMETRY (`<CorridorRun>`, a completely different component --
        // walls/floor/kit pieces, not a moving pulse) is untouched. A
        // parked lane gets no bubble at all (matches the old
        // ActivityBubbleLayer's own isParkedState exclusion).
        const laneBubble = isParkedState(row.state, row.health) ? null : laneBubbleAction(row);
        return (
          <group key={row.lane}>
            {/* Side hallway -- this bay's own T-junction edge to its own
                door. `doorAtFrom={false}`: a T-junction has no door, only
                the two real building entrances (hub doorway, bay doorway)
                do -- see CorridorRun's own comment. Ultra tier only. */}
            {ultra && (
              <Suspense fallback={null}>
                <CorridorRun from={slot.hallFrom} to={slot.hallTo} dayFactor={nightFactor} doorAtFrom={false} />
              </Suspense>
            )}
            {/* UX-1 U2/U3 (2026-09-14): ONE inner group wraps ONLY the
                clickable content (module+agent), deliberately NOT the outer
                `<group key={row.lane}>` -- that outer group is also the
                CorridorRun's own sibling above, and the task's own "clicking
                empty ground does nothing" rule means the hallway floor must
                stay non-interactive. Handlers spread conditionally (ultra
                only, matching every other interactive-only piece in this
                file -- StationModule/Agent themselves still render
                unconditionally on both tiers, byte-identical to before this
                pass, only whether THIS wrapper is clickable changes).
                onPointerOut's setHoveredTarget only clears when it's still
                THIS bay showing -- see hoveredTarget's own declaration
                comment for why an unconditional clear would be a real bug
                (adjacent clickable siblings, unordered over/out). */}
            <group
              {...clickableGroupProps(
                ultra,
                `bay${i}`,
                () => setHoveredTarget({ kind: "bay", index: i }),
                () => setHoveredTarget((cur) => (cur?.kind === "bay" && cur.index === i ? null : cur)),
              )}
            >
              <StationModule
                position={slot.position}
                angle={slot.stationAngle}
                row={row}
                behavior={behavior}
                reducedMotion={reducedMotion}
                dimFactor={dimFactor}
                ultra={ultra}
                dayFactor={nightFactor}
              />
              {/* Scene-root sibling, NOT nested inside StationModule -- see the
                  agentHome comment above. Lane agents never walk anymore (no
                  event cleanly attributes a card to one lane -- see the
                  (deleted) Courier.tsx's own comment on why card-status
                  events route there instead); `presenceMode`/`facingYaw` are
                  set on exactly one statically-chosen lane (nearestLaneIndex).
                  `bubbleText` is this lane's own little head-bubble (P2) --
                  `${state} · ${evidence}`, "!" prefixed when health is red,
                  the SAME wording ActivityBubbleLayer used to show at a fixed
                  floating point -- now it travels with the walker instead. */}
              <Agent
                laneSeed={row.lane}
                home={slot.agentHome}
                hub={HUB}
                // BLOCKY-FIXES pass (2026-09-16, Defect A): `slot.rotationY`
                // is the bay's OWN furniture yaw (layout.ts#computeBaySlot,
                // the exact angle DeskCluster's table/chair/screen already
                // render at) -- passed straight through as `deskYaw` so the
                // seated character's front axis lands on the SAME world
                // direction as its own screen, not the `atan2(hub-home)+PI`
                // approximation (Agent.tsx's own `deskYaw` doc comment has
                // the numeric proof: a bay sits SIDE_SPAN=8.1 off its own
                // T-junction, so "hub direction from this bay" and "this
                // bay's own facing" diverge by ~66.5deg here, not the small
                // perturbation the old hub-only formula assumed).
                deskYaw={slot.rotationY}
                behavior={behavior}
                accentColor={healthColor(row.health)}
                reducedMotion={reducedMotion}
                presenceMode={i === nearestLaneIndex ? greeterPresenceMode : undefined}
                facingYaw={i === nearestLaneIndex ? greeterFacingYaw : undefined}
                ultra={ultra}
                bubbleText={laneBubble}
                // HEAD-LABELS pass (2026-09-15): every lane/bay is the
                // deterministic Python engine (heartbeat_core.py + the
                // watcher/gym fleet) -- always the gear glyph, never a
                // guessed LLM tier.
                modelGlyph={BAY_MODEL_GLYPH.glyph}
                modelGlyphTitle={BAY_MODEL_GLYPH.title}
                // WALK-ROUTING pass (2026-09-15): every walk this agent
                // queues is now routed through the real hallway/door graph
                // (`walkGraph`, already memoized above for LiveAgents.tsx);
                // `alertPacePoint` = this bay's own door (layout.ts
                // #computeBaySlot's `doorWorldPos`), replacing the old
                // toward-hub-center pace point that cut straight through
                // this bay's own side wall on a red-health ("alert") lane --
                // the reported "Futures ran through walls" bug.
                walkGraph={walkGraph}
                alertPacePoint={slot.doorWorldPos}
              />
            </group>
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
        // BLOCKY-FIXES pass (2026-09-16, Defect B): real capture
        // blockyfix-desk3-0135.png showed "Analyst" ✦'s nameplate floating
        // right over Coach's OCCUPIED desk. Traced the full chain (this
        // component's own `innerPersonas.map` index `i` -> `personaGeometry
        // [i]` -> both the <Agent> below AND <DeskNameplate> read the SAME
        // `slot` from the SAME iteration, and lib/personas.ts#collectCompany
        // always returns `[gamma, scout, coach, pilot, analyst, chef,
        // treasurer]` -- Gamma fixed at index 0, so `allPersonas.slice(1)`
        // never drifts) -- NOT an index/slice bug, every persona's nameplate
        // already anchors at ITS OWN slot. Real root cause, found by
        // computing actual world distances between all 6 persona homes:
        // layout.ts#computePersonaWallSlots' own "2-2-2-1, corner-sharing"
        // scheme (each wall's "high corner" desk and the NEXT wall's "low
        // corner" desk are built to sit at the SAME shared hub corner) lands
        // 3 desk PAIRS just 0.85 world units apart -- Scout/Chef, Coach/
        // Analyst, Pilot/Treasurer (verified numerically, not assumed; see
        // tests/hq-desk-facing.test.ts) -- against a ~9.2-13.9u gap for
        // every non-corner-sharing pair. That geometry lives in layout.ts
        // (out of this pass' scope -- would also move every other consumer
        // of PERSONA_WALL_RADIUS/PERSONA_WALL_LATERAL_OFFSET). Mitigated
        // here instead, at the one place that's actually broken for the
        // viewer: an IDLE persona's nameplate never renders when its own
        // desk sits within `NAMEPLATE_COLLISION_CLEARANCE` of another
        // persona's CURRENTLY-OCCUPIED desk -- comfortably above the 0.85u
        // real collision distance, comfortably below the ~9.2u normal
        // spacing, so this can never suppress a nameplate that isn't
        // actually about to read as sitting on someone else's desk.
        const deskCollidesWithOccupiedNeighbor =
          !showAgent &&
          innerPersonas.some((other, j) => {
            if (j === i || other.status === "IDLE") return false;
            const otherSlot = personaGeometry[j] ?? personaGeometry[0];
            const dx = slot.position[0] - otherSlot.position[0];
            const dz = slot.position[2] - otherSlot.position[2];
            return Math.hypot(dx, dz) < NAMEPLATE_COLLISION_CLEARANCE;
          });
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
        // CREW-WORKING pass (item 4): this persona's own huddle waypoints,
        // routed through the real walk graph's new "hub-table" node
        // (layout.ts#buildWalkGraph) -- undefined for the 4+ personas NOT in
        // `activeHuddle.pair` this poll (Agent.tsx's own null/undefined
        // guard on `walkPlanKey` already treats that as zero behavior
        // change). `huddleWalkPlanKey` is the pair's SHARED trigger value
        // (crewWorking.ts#detectHuddleTrigger's own unique key) -- both
        // agents queue their own walk off the exact same real transition.
        const isHuddleA = activeHuddle?.pair[0] === persona.name;
        const isHuddleB = activeHuddle?.pair[1] === persona.name;
        const huddleWalkPlanKey = activeHuddle && (isHuddleA || isHuddleB) ? activeHuddle.key : undefined;
        let huddleWalkPlan: WalkPlan | undefined;
        if (activeHuddle && huddleSpots && (isHuddleA || isHuddleB)) {
          const mySpot = isHuddleA ? huddleSpots.a : huddleSpots.b;
          const myYaw = isHuddleA ? huddleSpots.faceYawA : huddleSpots.faceYawB;
          const path = findWalkPath(walkGraph, `persona-${persona.name}`, "hub-table");
          const plan = toWalkPlan(
            path && path.length > 0 ? [...path.slice(0, -1), mySpot] : null,
            mySpot,
            `huddle · ${activeHuddle.pair[0]} + ${activeHuddle.pair[1]}`,
            60,
            "idle",
          );
          huddleWalkPlan = { ...plan, faceYaw: myYaw };
        }
        const safeDecision = isPilot ? (data?.trading?.core.safe ?? null) : null;
        const boldDecision = isPilot ? (data?.trading?.core.bold ?? null) : null;
        // HQ-POSITION-TRUTH (2026-09-15): the LIVE exit-state.json truth,
        // independent of core-decisions.jsonl -- see lib/hq-positions.ts.
        const safePosition = isPilot ? (data?.trading?.position?.safe ?? null) : null;
        const boldPosition = isPilot ? (data?.trading?.position?.bold ?? null) : null;
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
        const accountScreenLine = (
          label: string,
          row: CoreDecisionRow | null,
          position: AccountPositions | null,
        ): ScreenLine => {
          // HQ-POSITION-TRUTH (2026-09-15): a real open leg ALWAYS outranks
          // the generic verdict/action text -- root cause this fixes: this
          // screen showed HOLD (flat-looking) the moment the engine's own
          // action ledger stopped logging ENTER_* while the broker position
          // stayed open for hours (position truth is independent of that
          // ledger; see lib/hq-positions.ts).
          const posClause = formatPositionClause(label, position);
          if (posClause) {
            return { text: truncateOneLine(posClause, 32), color: "#ffb020", size: 15 };
          }
          if (!row) return { text: `${label}: no data`, color: "#5f7a99", size: 14 };
          const sideTxt = row.side === "C" ? " CALL" : row.side === "P" ? " PUT" : "";
          const rowIsTrade = !!row.verdict && /^(ENTER|EXIT)/.test(row.verdict);
          // MARKET-TRUTH (2026-09-15): `verdict` alone (e.g. HOLD) hid WHY --
          // a HOLD caused by SKIP_STALE_TRIGGER looks identical to a normal
          // no-setup HOLD. Show the engine's real per-tick action code
          // whenever it differs from the verdict, still inside the SAME
          // 32-char budget truncateOneLine already enforced here (no new
          // declutter exposure -- same box, denser truth).
          const actionTxt = row.action && row.action !== row.verdict ? ` (${row.action})` : "";
          return {
            text: truncateOneLine(`${label} ${row.verdict ?? "?"}${sideTxt}${actionTxt} ${hhmmFromEtIso(row.tsEt)}`, 32),
            color: rowIsTrade ? "#ffb020" : "#7ad9ff",
            size: 15,
          };
        };
        // HQ-TRADE-MOMENTS (2026-09-15): active trade moments (already
        // windowed server-side) always outrank the generic SAFE/BOLD
        // decision lines -- a real fill is the most material thing Pilot
        // can be showing right now. Capped at 2 lines (this screen's own
        // existing 2-line budget) newest-first; falls back to the
        // pre-existing SAFE/BOLD lines the instant no fill is inside its
        // own active window (never a stale trade moment held client-side).
        const activeTradeMoments: TradeMomentEvent[] = isPilot ? (data?.trading?.tradeMoments ?? []) : [];
        const pilotScreenLines: ScreenLine[] | undefined = isPilot
          ? activeTradeMoments.length > 0
            ? activeTradeMoments.slice(0, 2).map((ev): ScreenLine => ({
                text: truncateOneLine(formatTradeMomentLine(ev), 32),
                color: ev.kind === "EXIT" && ev.realizedUsd !== null && ev.realizedUsd < 0 ? "#ff6b6b" : "#ffb020",
                size: 15,
              }))
            : [accountScreenLine("SAFE", safeDecision, safePosition), accountScreenLine("BOLD", boldDecision, boldPosition)]
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
        // PEOPLE pass (P2/P4, 2026-09-14): the reason text for whichever
        // "purposeful"-kind walk this persona might take -- Agent.tsx reads
        // whichever of these two actually fired (its own eventWalkPending
        // ref, the SAME split that already picks the TARGET a few lines up).
        // hubEvent's own real crew-event line becomes the visitor's bubble
        // while it stands at Gamma's desk (spec: "the visitor's line becomes
        // that visitor's own walk purpose") -- never a second floating
        // bubble at a fixed point.
        const eventWalkReasonFinal = hubEvent
          ? `-> Gamma · ${hubEvent.line}`
          : namedWalk?.target
            ? NAMED_WALK_REASON[persona.name]
            : undefined;
        const purposefulReasonFinal = `-> ${purposefulDestLabel(purposeful.walk.destination)} · ${purposeful.walk.reason}`;
        // Idle/working bubble text -- lib/crew.ts's own evidence-backed pill
        // (deriveCrewPill), the SAME derivation Hud.tsx's roster panel uses,
        // so the 3D bubble and the flat panel can never disagree (P2 spec).
        // PERSONA-VISIT pass: a live-agent acknowledgement wins for its own
        // short ~4s window (personaGreetingText, computed once above from
        // real pulse-row evidence) -- otherwise the normal evidence-backed
        // pill, unmodified. Content-only override (never touches walkKind/
        // walkEventKey/any movement prop below), matching this task's own
        // "only choose the TARGET node and add bubble content" boundary.
        const personaBubble = personaGreetingText.get(persona.name as PersonaId) ?? personaBubbleAction(persona, nowMsForWalks);
        return (
          <group
            key={persona.name}
            {...clickableGroupProps(
              ultra,
              String(i + 2),
              () => setHoveredTarget({ kind: "persona", index: i }),
              () => setHoveredTarget((cur) => (cur?.kind === "persona" && cur.index === i ? null : cur)),
            )}
          >
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
                      position={slot.position}
                      rotationY={slot.rotationY}
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
                // BLOCKY-FIXES pass (2026-09-16, Defect A): `slot.rotationY`
                // is this persona wall-desk's OWN furniture yaw
                // (layout.ts#computePersonaWallSlots, the exact angle
                // SetKit.tsx#DeskCluster's table/chair/screen already
                // render at) -- see Agent.tsx's own `deskYaw` prop doc
                // comment for the full derivation (character GLB's true
                // front axis + the numeric proof this hub-approximation was
                // ~35-50deg off for every persona slot, root-causing the
                // real capture that showed Coach's face to a camera meant
                // to stand behind him).
                deskYaw={slot.rotationY}
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
                // Item 2b (LIVE-1), re-gated CREW-WORKING pass (2026-09-15/16,
                // per the HQ face rule "motion = real events"):
                // `purposeful.walk.bucketKey` used to fire this trigger on a
                // fixed 6-10min CLOCK regardless of whether anything real
                // happened to this persona -- a fabricated event. Replaced
                // with palette.ts#purposefulWalkTriggerKey, which only
                // changes on a genuine lastFireISO/status change (Agent.tsx's
                // existing seen-value-diff convention does the rest); when it
                // DOES fire, `computePurposefulWalk`'s own destination/reason
                // (`purposeful.target`/`purposefulReasonFinal` below) still
                // pick WHERE/WHY, unchanged.
                purposefulWalkEventKey={purposefulWalkTriggerKey(persona.name, persona.lastFireISO, persona.status)}
                purposefulTarget={purposeful.target}
                purposefulReason={purposefulReasonFinal}
                // INTERACT-2 (I2 a-f): Chef/Coach -> Gamma at the hub on a
                // real crew-event row, OR one of the four other named-event
                // walks (Scout->Pilot, Analyst->Chef, Treasurer->Gamma,
                // Pilot->Analyst) resolved above. undefined for any persona
                // with neither -- zero behavior change (Agent.tsx's own
                // null/undefined guard on this channel).
                eventWalkEventKey={eventWalkKeyFinal}
                eventWalkTarget={eventWalkTargetFinal}
                eventWalkReason={eventWalkReasonFinal}
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
                // PEOPLE pass (P2/P3): this persona's own little head-bubble
                // (idle/working text) + the audit-verdict letter chip that
                // used to live on the now-deleted PersonaModule's nameplate
                // (its own NAME moved into the bubble too -- `laneSeed`
                // above already IS `persona.name`, so Agent.tsx's bubble
                // JSX bolds it for free, no separate prop needed).
                bubbleText={personaBubble}
                auditVerdict={auditByName.get(persona.name)?.verdict}
                // HEAD-LABELS pass (2026-09-15): this persona's real
                // classified runtime (modelGlyphByPersona, derived from
                // data.runtime.roles above) -- undefined for a persona the
                // roster fixture doesn't classify (falls back to Agent.tsx's
                // own "?" default, never a guessed tier).
                modelGlyph={modelGlyphByPersona.get(persona.name)?.glyph}
                modelGlyphTitle={modelGlyphByPersona.get(persona.name)?.title}
                bubblePriority={PRIORITY.PERSONA}
                // WALK-ROUTING pass (2026-09-15): personas are hub-interior
                // (home->hub/ambient-point lines never cross a wall today),
                // so this doesn't fix a visible bug for them the way the bay
                // agent's `alertPacePoint` above does -- but it makes the
                // no-wall invariant STRUCTURAL rather than "happens to be
                // true of today's hub layout", per this pass's actual scope
                // ("every resident-agent walk ... follow the walk graph").
                // No `alertPacePoint` override -- personas never go
                // "alert" (only lane bays derive that behavior).
                walkGraph={walkGraph}
                // CREW-WORKING pass (item 4): undefined for every persona not
                // in `activeHuddle.pair` this poll -- zero behavior change
                // (Agent.tsx's own null/undefined guard on `walkPlanKey`).
                walkPlanKey={huddleWalkPlanKey}
                walkPlan={huddleWalkPlan}
              />
            )}
            {/* U4 usability fix (2026-09-16): the IDLE counterpart to the
                <Agent> mount just above -- an empty desk still needs a
                legible nameplate answering "what is this persona doing?"
                (see DeskNameplate.tsx's own header for the FAIL this
                fixes). `deriveCrewPill` is the SAME quiet-reason/next-fire
                derivation Hud.tsx's roster panel and the hover panel below
                already use, so this label's hover text can never disagree
                with either. */}
            {!showAgent && !deskCollidesWithOccupiedNeighbor && (
              <DeskNameplate
                name={persona.name}
                position={slot.position}
                glyph={modelGlyphByPersona.get(persona.name)?.glyph ?? "?"}
                glyphTitle={modelGlyphByPersona.get(persona.name)?.title ?? "unclassified"}
                detail={deriveCrewPill(persona, nowMsForWalks).reason}
                detailKey={`${persona.status}|${deriveCrewPill(persona, nowMsForWalks).reason}`}
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

      <IdeasWall cards={data?.ideas.cards ?? []} fleetPnl={data?.trading?.fleetPnl ?? null} position={WALL_POS} dimFactor={dimFactor} />

      {/* LIVE-AGENTS pass (2026-09-14) -- real Claude Code sessions/
          subagents, up to 8, walking the SAME walk graph (`walkGraph`,
          built just above) the persona eventWalk/purposeful-walk machinery
          already uses. Ultra tier only (real KitAgentBody characters, see
          LiveAgents.tsx's own header); TV tier renders nothing here. */}
      <LiveAgents agents={data?.liveAgents ?? []} walkGraph={walkGraph} ultra={ultra} reducedMotion={reducedMotion} />
      {/* PEOPLE pass (P3, 2026-09-14, J: "the traveling orbs can go too"):
          the hub's anonymous courier bot + the card-status "glowing orb up
          to the smart board" it used to fly are REMOVED -- Courier.tsx
          itself is deleted (its props kept `void`-only right up to this
          commit so this exact mount could compile away cleanly). Card
          events still reach the world through Chef's own bubble (the
          hub-exchange `eventWalkReason` wiring above) and the smart board's
          own content -- the event isn't lost, only the orb. ActivityBubbleLayer
          (the separate floating-bubble LAYER) is gone too -- see every
          <Agent>/<GammaCharacter> mount above, each now carries its OWN
          bubble instead. */}

      {/* UX-1 U3 (2026-09-14, "hovering character/bay shows tooltip
          (name.pill.now-line) near cursor"): ONE shared tooltip driven by
          `hoveredTarget` (set by the bay/persona/gamma onPointerOver/Out
          handlers above) instead of one per clickable group -- cheaper (a
          single <Html> mount/unmount as the pointer moves between targets,
          not 15 permanently-mounted ones) and there is only ever one
          hovered target at a time anyway. `pointerEvents:"none"` (same
          convention as every other informational Html overlay in this file
          -- BaySign's close-up label, the Pilot desk-pulse above) so the
          tooltip itself can never block the hover/click it's describing.
          Name/pill/now-line come from the SAME lib/crew.ts derivation
          Hud.tsx's own roster panel reads (deriveCrewPill/crewNowLine) for
          personas/Gamma, and the identical row fields Hud.tsx's panel shows
          for a lane -- this can never disagree with the flat panel. */}
      {ultra && hoveredTarget && (() => {
        let name: string;
        let pillLabel: string;
        let nowLine: string;
        let color: string;
        let pos: [number, number, number];
        if (hoveredTarget.kind === "bay") {
          const row = rows[hoveredTarget.index];
          const slot = geometry[hoveredTarget.index] ?? geometry[0];
          if (!row || !slot) return null;
          name = row.lane;
          pillLabel = row.state;
          nowLine = row.evidence;
          color = healthColor(row.health);
          pos = [slot.position[0], 3.0, slot.position[2]];
        } else {
          const persona = hoveredTarget.kind === "gamma" ? allPersonas[0] : innerPersonas[hoveredTarget.index];
          if (!persona) return null;
          const slotPos = hoveredTarget.kind === "gamma" ? gammaDeskCenter : (personaGeometry[hoveredTarget.index] ?? personaGeometry[0])?.position;
          if (!slotPos) return null;
          const pill = deriveCrewPill(persona, nowMsForWalks);
          name = persona.name;
          pillLabel = pill.kind;
          nowLine = crewNowLine(persona) ?? pill.reason;
          color = CREW_PILL_COLOR[pill.kind];
          pos = [slotPos[0], 2.3, slotPos[2]];
        }
        return (
          <Html position={pos} center distanceFactor={9} style={{ pointerEvents: "none" }}>
            <div
              style={{
                background: "rgba(3,4,10,0.88)", border: `1px solid ${color}`, borderRadius: 7,
                padding: "6px 12px", fontFamily: "system-ui, sans-serif", whiteSpace: "nowrap",
                color: "#dff3ff",
              }}
            >
              <div style={{ fontSize: 14, fontWeight: 700 }}>
                {name} <span style={{ color, fontWeight: 600 }}>· {pillLabel}</span>
              </div>
              <div style={{ fontSize: 12, color: "#9fb8d6", marginTop: 2 }}>{truncateOneLine(nowLine, 42)}</div>
            </div>
          </Html>
        );
      })()}

      {/* UX-1 U3 ("hovering a crew card pulses that persona's own in-world
          sign/marker"): consumes hudHoveredIndex (lib/hq-hover-persona.ts,
          published by Hud.tsx's crew card onMouseEnter/Leave) -- index 0 =
          Gamma, 1-6 = innerPersonas[0..5], the SAME fixed order Hud.tsx's
          own crew list (data.company.personas, Gamma included at [0]) and
          this file's own cameraPresets already agree on. PersonaModule.tsx
          (which used to render a real nameplate mesh here) is deleted --
          every persona's only in-world marker today is Agent's own Html
          bubble, so this renders as an ADDITIONAL small Html glow next to
          that marker rather than touching Agent.tsx/GammaCharacter.tsx
          (both outside this task's Scene.tsx-only scope). transform/opacity
          ONLY in the pulse keyframe below -- this file's own established
          TV-compositor-safe rule (see the .hq-beam/.hq-shine header
          comment in Hud.tsx this file already follows for the Pilot desk
          pulse above) -- reducedMotion swaps the looping pulse for a static
          ring, same convention as every other reducedMotion branch here. */}
      {ultra && hudHoveredIndex !== null && (() => {
        const pos = hudHoveredIndex === 0 ? gammaDeskCenter : (personaGeometry[hudHoveredIndex - 1] ?? personaGeometry[0])?.position;
        if (!pos) return null;
        return (
          // Html PORTALS its children into the real page DOM (verified
          // established precedent: the Pilot desk-pulse above already
          // relies on this to reference Hud.tsx's global `.hq-beam`/
          // `.hq-shine` classes from inside <Canvas>) -- so a plain <style>
          // tag as a CHILD here works correctly and, unlike a bare <style>
          // as a direct sibling in Scene()'s own return, is never
          // misinterpreted by r3f's reconciler as a THREE-namespace lookup
          // (every lowercase JSX tag OUTSIDE an <Html> boundary within
          // <Canvas> is one; a bare `<style>` there throws "Style is not
          // part of the THREE namespace"). Scoped to only mount while
          // actually hovered (matches this whole block's own conditional)
          // -- a rare, human-driven event, not a hot path, so the
          // mount/unmount cost of the stylesheet fragment itself is
          // negligible. `key={hudHoveredIndex}` remounts (and so replays)
          // this whole block, animation included, on every index change --
          // the SAME "replay via a changing React key" mechanism
          // `.hq-shine` above already uses.
          <Html key={hudHoveredIndex} position={[pos[0], 2.0, pos[2]]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
            <style>{`
              @keyframes hq-hover-pulse-anim {
                0% { transform: scale(0.6); opacity: 0.9; }
                100% { transform: scale(1.6); opacity: 0; }
              }
            `}</style>
            <div
              style={{
                width: 34, height: 34, borderRadius: "50%",
                border: "2px solid #7ad9ff",
                animation: reducedMotion ? undefined : "hq-hover-pulse-anim 1.1s ease-out infinite",
                opacity: reducedMotion ? 0.7 : undefined,
              }}
            />
          </Html>
        );
      })()}
    </>
  );
}

export default memo(Scene);

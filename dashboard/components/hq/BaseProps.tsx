"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import { PALETTE, lerp } from "./palette";
import { KIT_PATHS, KitProp, InstancedKitPool, usePooledKitProps } from "./SetKit";
import { minClearRadius } from "./layout";

// ─── W2 (2026-09-14, WORLD-6 builder): 3 reputable-source CC0 pieces --
// self-contained model paths (same "own local path, not a new SetKit.tsx
// KIT_PATHS entry" convention HubInterior.tsx/SmartBoard.tsx already use for
// their own self-contained pieces) so this stays a zero-contention add on a
// file SetKit.tsx doesn't own. Provenance + raw-bounds measurements (via
// dashboard/scripts/glb_extents.mjs, this session) are recorded in
// public/hq-assets/manifest.json's own `props` entries; see LICENSES.md's
// "Update 2026-09-14 (WORLD-6 builder, W2 asset hunt)" for the full
// candidates-opened-and-rejected disclosure.
const SHUTTLE_PATH = "/hq-assets/polypizza-quaternius/shuttle.glb";
const SCIFI_COMPUTER_PATH = "/hq-assets/polypizza-quaternius/scifi-computer.glb";
const PIPES_PANEL_PATH = "/hq-assets/polypizza-quaternius/pipes-panel.glb";
useGLTF.preload(SHUTTLE_PATH, false);
useGLTF.preload(SCIFI_COMPUTER_PATH, false);
useGLTF.preload(PIPES_PANEL_PATH, false);

// ─── E3, World-3 environment pass (2026-09-14, J: "grey abyss... space theme
// or a park or something real") ─────────────────────────────────────────────
// Base props ringing the plaza: dishes, a solar array, a landing pad, a
// rover, containers/barrels, pipes, perimeter lights, one antenna mast.
// Heavy (real-GLB) pieces are ultra-tier only, matching every other real-
// kit-geometry piece in this tree; the antenna mast + landing pad (both
// cheap procedural geometry, no GLB) render on BOTH tiers -- "TV tier gets
// sky+ground+planet+a few props" per this pass's own brief.
//
// LAYOUT builder pass (2026-09-14, campus-cross rebuild): the old flat
// "radius >= 19.5" clearance rule was correct for the old CIRCULAR plaza
// (a single radius really was the whole boundary) but is WRONG for the new
// orthogonal cross -- an arm's own tip needs real clearance while a
// diagonal gap between two arms needs almost none, so a single number
// either clips a bay corner or needlessly pushes every diagonal-gap prop
// far out. `minClearRadius(azimuth, margin)` (layout.ts) computes the
// TRUE boundary at each prop's own azimuth instead of assuming one radius
// fits every direction -- verified this session (a standalone arithmetic
// check mirroring layout.ts's own formula) that 3 of the 9 positions below
// (rover, containers, all 4 pipes) actually landed INSIDE the new
// footprint at their old radius (by 3.6-4.3u) even though the other 6
// (both dishes, solar, landing pad, perimeter, antenna) still cleared with
// real margin -- exactly the "some directions need much more room than
// others" case a flat rule can't express. Only the 3 that were actually
// unsafe were changed (`Math.max(<original literal>, minClearRadius(...))`
// -- never a blind bump on props that already verifiably cleared).

const PLANET_AZIMUTH = Math.atan2(16, 20) + Math.PI; // mirrors Planet.tsx's own constant -- dishes face this direction
const _deg = (d: number) => (d * Math.PI) / 180;

function polar(azimuthDeg: number, radius: number, y = 0): [number, number, number] {
  const a = _deg(azimuthDeg);
  return [Math.cos(a) * radius, y, Math.sin(a) * radius];
}

/** Same "interior lamps dim by day, never fully off" shape as
 * SetKit.tsx#interiorLampFactor (not exported there, so reimplemented here
 * rather than reached into another file's private helper) -- outdoor
 * beacons stay a bit more visible by day than interior room lamps do
 * (lerp target 0.3 vs that file's 0.15), since these read as distinct
 * colored signal lights, not general room lighting. */
function outdoorLampFactor(dayFactor: number): number {
  return lerp(1, 0.3, dayFactor);
}

// ─── Satellite dishes -- 2, angled toward the planet ───────────────────────
function SatelliteDishes({ dayFactor }: { dayFactor: number }) {
  const lampFactor = outdoorLampFactor(dayFactor);
  const emissive = useMemo(() => ({ color: PALETTE.warmAccent, intensity: 0.5 * lampFactor }), [lampFactor]);
  return (
    <>
      <KitProp
        path={KIT_PATHS.baseProps.satelliteDish}
        scale={2.2}
        position={polar(205, 26)}
        rotation={[0, PLANET_AZIMUTH, 0]}
        tint={PALETTE.warmAccent}
        tintStrength={0.1}
        emissive={emissive}
        castShadow
        receiveShadow
      />
      <KitProp
        path={KIT_PATHS.baseProps.satelliteDishLarge}
        scale={2.4}
        position={polar(233, 28)}
        rotation={[0, PLANET_AZIMUTH, 0]}
        tint={PALETTE.warmAccent}
        tintStrength={0.1}
        emissive={emissive}
        castShadow
        receiveShadow
      />
    </>
  );
}

// ─── Solar array -- a row-instanced field of procedural panels on real kit
// support legs (this pack has no dedicated solar-panel piece -- see
// manifest.json's own note on kenney-space-kit/structure.glb). Panels are a
// single thin tilted box each -- cheap, no texture, a dark blue-black
// "photovoltaic" tone with a little metalness for a subtle specular read. ──
const SOLAR_ROWS = 2;
const SOLAR_COLS = 4;
const SOLAR_SPACING = 2.6;
const SOLAR_ORIGIN = polar(90, 26);

// PERF-3 (2026-09-15): the 2 supportsHigh legs pooled (own pool key, this
// file is BaseProps.tsx's own singleton mount with no wrapping transform --
// grepped Scene.tsx's own call site, no group ancestor -- so world coords
// below are genuine world-space, same reasoning as this file's other pools).
// Evidence: "Mesh_supports_high x2, Mesh_supports_high_1 x2".
const SUPPORTS_HIGH_PLACEMENTS = [
  { id: "solar-support-1", position: [SOLAR_ORIGIN[0] - SOLAR_SPACING * 1.8, 0, SOLAR_ORIGIN[2] - 0.5] as [number, number, number], rotation: [0, 0, 0] as [number, number, number], scale: 1.6 },
  { id: "solar-support-2", position: [SOLAR_ORIGIN[0] + SOLAR_SPACING * 1.8, 0, SOLAR_ORIGIN[2] + SOLAR_ROWS * SOLAR_SPACING] as [number, number, number], rotation: [0, 0, 0] as [number, number, number], scale: 1.6 },
];

function SolarArray() {
  usePooledKitProps(KIT_PATHS.baseProps.supportsHigh, "native", SUPPORTS_HIGH_PLACEMENTS);
  const panels = useMemo(() => {
    const out: [number, number, number][] = [];
    for (let r = 0; r < SOLAR_ROWS; r++) {
      for (let c = 0; c < SOLAR_COLS; c++) {
        out.push([
          SOLAR_ORIGIN[0] + (c - (SOLAR_COLS - 1) / 2) * SOLAR_SPACING,
          1.1,
          SOLAR_ORIGIN[2] + r * SOLAR_SPACING * 1.4,
        ]);
      }
    }
    return out;
  }, []);
  return (
    <group>
      <InstancedKitPool path={KIT_PATHS.baseProps.supportsHigh} variant="native" castShadow />
      {panels.map((pos, i) => (
        <mesh key={i} position={pos} rotation={[_deg(-25), 0, 0]} castShadow receiveShadow>
          <boxGeometry args={[2.1, 0.06, 1.3]} />
          <meshStandardMaterial color="#0d1c2e" roughness={0.35} metalness={0.55} />
        </mesh>
      ))}
    </group>
  );
}

// ─── Landing pad -- procedural disc + an emissive light ring (no real
// THREE.Light -- see PerimeterLights' own comment on this tree's light
// budget discipline; the ring READS as lit via emissive alone). ────────────
function LandingPad({ dayFactor }: { dayFactor: number }) {
  const lampFactor = outdoorLampFactor(dayFactor);
  const ringColor = useMemo(() => new THREE.Color(PALETTE.warmAccent), []);
  const pos = polar(270, 27);
  return (
    <group position={pos}>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]} receiveShadow>
        <circleGeometry args={[5, 32]} />
        <meshStandardMaterial color="#3a3428" roughness={0.95} metalness={0.05} />
      </mesh>
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.02, 0]}>
        <ringGeometry args={[4.3, 4.6, 48]} />
        <meshStandardMaterial color={ringColor} emissive={ringColor} emissiveIntensity={0.7 * lampFactor} toneMapped={false} />
      </mesh>
    </group>
  );
}

// ─── Shuttle -- W2 (2026-09-14): "a shuttle parked on the landing pad" per
// the task's own suggested category, real CC0 GLB (Quaternius, via
// poly.pizza's own static CDN -- see this file's own top-of-file comment).
// Parked, static -- no motion (HQ face rule: this piece has no event source
// to animate off, matching Rover's own reasoning directly below). Sits at
// the EXACT same position LandingPad places its own disc at (polar(270,27),
// duplicated rather than threaded as a prop -- LandingPad's own `pos` is a
// local const, not exported, same "tiny local duplication over cross-file
// coupling" convention this file already uses for outdoorLampFactor). ──────
const SHUTTLE_SCALE = 0.55;
// rawBounds (glb_extents.mjs, this session): 10.382w x 1.859h x 9.209d,
// floor Y=-0.145 -- the model's own lowest vertex sits BELOW its local
// origin (an authoring quirk, not a bug in this file), so a flush landing
// needs +0.145*scale of Y correction or the hull clips into the pad disc.
const SHUTTLE_FLOOR_CORRECTION = 0.145 * SHUTTLE_SCALE;

function Shuttle({ dayFactor }: { dayFactor: number }) {
  const pos = polar(270, 27);
  const lampFactor = outdoorLampFactor(dayFactor);
  return (
    <>
      <KitProp
        path={SHUTTLE_PATH}
        scale={SHUTTLE_SCALE}
        position={[pos[0], SHUTTLE_FLOOR_CORRECTION, pos[2]]}
        rotation={[0, _deg(35), 0]}
        castShadow
        receiveShadow
      />
      {/* W3: contact glow, reads as the shuttle's own landing lights washing
          the pad under it. */}
      <GroundGlow position={pos} radius={3.4} color={PALETTE.warmAccent} opacity={0.06 * lampFactor} />
    </>
  );
}

// ─── Server annex -- W2 (2026-09-14): "sci-fi consoles/servers" per the
// task's own suggested category. Originally scoped for the hub's own
// "second wall" (the task brief's literal suggestion); relocated here
// instead after checking the actual geometry -- every open radius on the
// hub's brain-wall segment either collides with Gamma's own desk (radius
// 3.4, angle ~61deg -- not this builder's file to move) or repeats the
// EXACT radius-6.8-is-invisible-from-the-default-camera failure
// layout.ts#computeBrainWallMount's own header already documents (and fixed
// once, for the smart board, by pulling it in to radius 4.9); the hub's
// other 3 wall segments are live persona-desk territory other builders are
// concurrently editing this session. An exterior cluster, using the SAME
// minClearRadius safety math every other azimuth-placed piece in this file
// already uses, is the zero-contention choice. ONE scifi-computer.glb plus
// one pipes-panel.glb greeble behind it -- was 2 console instances at first
// draft (a "small server bank" read), cut to 1 after a coordinator draw-
// call-budget flag (2026-09-14 ~19:2x ET, real capture
// hq-20260914-1725.png: 1093/1100 calls): scifi-computer.glb has 5
// primitives (glb_extents.mjs's own JSON-chunk inspection this session), so
// the 2nd instance alone cost 5 draw calls for a repeated prop. ───────────
const SERVER_ANNEX_AZIMUTH = 320; // clear gap between the nearest pipe (285deg) and the antenna mast (340deg)

function ServerAnnex({ dayFactor }: { dayFactor: number }) {
  const lampFactor = outdoorLampFactor(dayFactor);
  const emissive = useMemo(() => ({ color: PALETTE.warmAccent, intensity: 0.4 * lampFactor }), [lampFactor]);
  const radius = minClearRadius(_deg(SERVER_ANNEX_AZIMUTH), 1.5);
  const base = polar(SERVER_ANNEX_AZIMUTH, radius);
  return (
    <group position={base} rotation={[0, _deg(SERVER_ANNEX_AZIMUTH + 180), 0]}>
      {/* Scifi Computer -- rawBounds 0.580w x 2.079h x 0.644d, floor Y~=0
          (flush, no correction needed), tinted amber to match this file's
          own outdoor-beacon accent. */}
      <KitProp
        path={SCIFI_COMPUTER_PATH} scale={0.85} position={[0, 0, 0]}
        tint={PALETTE.warmAccent} tintStrength={0.12} emissive={emissive} castShadow receiveShadow
      />
      {/* Pipes Panel -- rawBounds 0.514w x 1.585h x 0.093d, origin at
          VERTICAL CENTER (min/max Y = -0.792/+0.792 -- a wall-mount panel
          authored around its own middle, not its base): position.y below is
          the panel's own MIDDLE height, not a floor offset. */}
      <KitProp
        path={PIPES_PANEL_PATH} scale={0.9} position={[0, 0.71, -0.32]}
        tint={PALETTE.warmAccent} tintStrength={0.12} emissive={emissive} castShadow receiveShadow
      />
      {/* W3: contact glow under the console. */}
      <GroundGlow position={[0, 0, 0]} radius={0.9} color={PALETTE.warmAccent} opacity={0.08 * lampFactor} />
    </group>
  );
}

// ─── Rover -- parked, static (no motion: J's own HQ face rule -- "motion =
// events with a ticker", this rover has no event source, so it never moves). ─
function Rover() {
  // LAYOUT builder pass: 21 alone landed inside the new cross footprint at
  // this exact azimuth (verified -- see this file's own top comment) --
  // Math.max keeps the ORIGINAL literal as a floor rather than silently
  // dropping it, so this only ever moves outward, never in.
  const radius = Math.max(21, minClearRadius(_deg(150), 1.5));
  return (
    <KitProp
      path={KIT_PATHS.baseProps.rover}
      scale={2.4}
      position={polar(150, radius)}
      rotation={[0, _deg(150 + 90), 0]}
      castShadow
      receiveShadow
    />
  );
}

// ─── Containers + barrels -- a small cluster, "by a corridor" (the plaza's
// own outer edge, nearest the lane ring's own corridor gaps). ──────────────
function ContainersAndBarrels() {
  // LAYOUT builder pass: 21 alone landed inside the new cross footprint at
  // this exact azimuth (verified -- see this file's own top comment); the
  // 3 pieces below offset a small ~1.8-2.6u from `base`, well inside the
  // margin this bump adds, so they clear too, not just the anchor point.
  const base = polar(60, Math.max(21, minClearRadius(_deg(60), 1.5)));
  return (
    <group>
      <KitProp path={KIT_PATHS.baseProps.container} scale={2.0} position={[base[0], 0, base[2]]} rotation={[0, _deg(40), 0]} castShadow receiveShadow />
      <KitProp path={KIT_PATHS.baseProps.container} scale={2.0} position={[base[0] + 2.6, 0, base[2] + 1.1]} rotation={[0, _deg(20), 0]} castShadow receiveShadow />
      <KitProp path={KIT_PATHS.baseProps.barrels} scale={2.0} position={[base[0] - 1.8, 0, base[2] + 1.6]} rotation={[0, _deg(75), 0]} castShadow receiveShadow />
    </group>
  );
}

// ─── Pipes -- a handful of straight/corner segments tangent to the plaza's
// own outer edge, greeble only (no functional meaning). ────────────────────
const PIPE_AZIMUTHS = [15, 105, 195, 285];

function PipesAlongEdge() {
  return (
    <>
      {PIPE_AZIMUTHS.map((az, i) => {
        // LAYOUT builder pass: 19.5 alone landed inside the new cross
        // footprint at all 4 of these azimuths (verified -- see this
        // file's own top comment) -- these sit closest to an arm's own
        // tip (15/105/195/285deg are each only 15deg off an arm's own
        // centerline), so they needed the largest bump of the 3 unsafe
        // groups.
        const radius = Math.max(19.5, minClearRadius(_deg(az), 1.5));
        return (
          <KitProp
            key={az}
            path={i % 2 === 0 ? KIT_PATHS.baseProps.pipeStraight : KIT_PATHS.baseProps.pipeCorner}
            scale={1.8}
            position={polar(az, radius)}
            rotation={[0, _deg(az + 90), 0]}
            castShadow
          />
        );
      })}
    </>
  );
}

// ─── W3 (2026-09-14): static additive light cone -- "raise the look without
// ambient motion" (this pass's own 2-technique budget). ConeGeometry's own
// default orientation (apex at local +height/2, base at local -height/2,
// verified against three.js's own source this session, not assumed) already
// points the WIDE end down when centered with its apex at the fixture and
// base at the ground -- no rotation needed. Deliberately faint (opacity
// capped low, additive, depthWrite=false) so it reads as a soft volumetric
// hint, never a solid visible cone shape; scales with the SAME
// outdoorLampFactor(dayFactor) curve the fixture's own emissive intensity
// already uses, so the cone is a DATA readout (real light state), not a
// decorative loop -- zero useFrame, built once per dayFactor change. ───────
function LightCone({ apexY, radius, color, opacity }: { apexY: number; radius: number; color: string; opacity: number }) {
  if (opacity <= 0.002) return null; // fully faded (bright daylight) -- skip the draw call entirely
  return (
    <mesh position={[0, apexY / 2, 0]} raycast={() => null}>
      <coneGeometry args={[radius, apexY, 14, 1, true]} />
      <meshBasicMaterial
        color={color} transparent opacity={opacity} side={THREE.DoubleSide}
        depthWrite={false} toneMapped={false} blending={THREE.AdditiveBlending}
      />
    </mesh>
  );
}

/** W3, second technique -- a flat additive "contact glow" disc flush on the
 * ground under a hero prop, selling "this is a real, lit object sitting
 * here" (a cheap, static stand-in for real contact-shadow/bounce lighting --
 * this scene's own standing cost discipline rules out a real light per prop,
 * see PerimeterLights' own comment). Zero motion, day/night-aware via the
 * same lampFactor every other outdoor glow in this file already uses. */
function GroundGlow({ position, radius, color, opacity }: { position: [number, number, number]; radius: number; color: string; opacity: number }) {
  if (opacity <= 0.002) return null;
  return (
    <mesh position={[position[0], position[1] + 0.015, position[2]]} rotation={[-Math.PI / 2, 0, 0]} raycast={() => null}>
      <circleGeometry args={[radius, 24]} />
      <meshBasicMaterial color={color} transparent opacity={opacity} depthWrite={false} toneMapped={false} blending={THREE.AdditiveBlending} />
    </mesh>
  );
}

// ─── Perimeter lights -- 8 posts (procedural cylinder) + a real kaykit
// `lights.gltf` head each, per task spec ("base perimeter lights (kaykit
// lights) at ~8 posts"). Emissive-only, like SetKit.tsx#CeilingLight -- "no
// dynamic THREE.Light attached" is this tree's own standing cost discipline
// (Scene.tsx's HQ-v2-perf-pass comment); the glow reads through the kit
// piece's own emissive tint instead of a real point light. ─────────────────
const PERIMETER_COUNT = 8;
const PERIMETER_RADIUS = 33;

function PerimeterLights({ dayFactor }: { dayFactor: number }) {
  const lampFactor = outdoorLampFactor(dayFactor);
  const emissive = useMemo(() => ({ color: PALETTE.warmAccent, intensity: 0.9 * lampFactor }), [lampFactor]);
  const posts = useMemo(
    () => Array.from({ length: PERIMETER_COUNT }, (_, i) => polar((360 / PERIMETER_COUNT) * i, PERIMETER_RADIUS)),
    [],
  );
  return (
    <>
      {posts.map((pos, i) => (
        <group key={i} position={pos}>
          <mesh position={[0, 0.9, 0]} castShadow>
            <cylinderGeometry args={[0.06, 0.08, 1.8, 6]} />
            <meshStandardMaterial color={PALETTE.deskDark} roughness={0.7} metalness={0.3} />
          </mesh>
          <KitProp path={KIT_PATHS.lights} scale={0.9} position={[0, 1.85, 0]} rotation={[Math.PI, 0, 0]} emissive={emissive} />
          <LightCone apexY={1.75} radius={0.6} color={PALETTE.warmAccent} opacity={0.1 * lampFactor} />
        </group>
      ))}
    </>
  );
}

// ─── Antenna mast -- one landmark, a slow blinking red light. The ONE
// exception to "no ambient timer-driven motion" (HQ face rule): the rule's
// own carve-out is explicit -- "event-free ambience is OK ONLY for lights".
// reducedMotion freezes the blink at a fixed mid-brightness (same "motion
// stops, the state cue doesn't" split Starfield.tsx/StationModule.tsx's own
// beacons already use) rather than going fully dark or fully lit. ──────────
function AntennaMast({ reducedMotion }: { reducedMotion: boolean }) {
  const lightRef = useRef<THREE.Mesh>(null);
  const matRef = useRef<THREE.MeshStandardMaterial>(null);
  const pos = polar(340, 38);

  useFrame((state) => {
    const mat = matRef.current;
    if (!mat) return;
    if (reducedMotion) {
      mat.emissiveIntensity = 1.2;
      return;
    }
    // Slow blink -- a sharpened sine so it reads as a discrete pulse (a real
    // beacon) rather than a smooth breathing glow.
    const t = state.clock.elapsedTime;
    const raw = Math.sin(t * 1.6);
    mat.emissiveIntensity = raw > 0.7 ? 2.2 : 0.15;
  });

  return (
    <group position={pos}>
      <mesh position={[0, 3, 0]} castShadow>
        <cylinderGeometry args={[0.05, 0.09, 6, 6]} />
        <meshStandardMaterial color={PALETTE.deskDark} roughness={0.6} metalness={0.35} />
      </mesh>
      <mesh ref={lightRef} position={[0, 6.15, 0]}>
        <sphereGeometry args={[0.16, 12, 10]} />
        <meshStandardMaterial ref={matRef} color="#ff3b3b" emissive="#ff3b3b" emissiveIntensity={1.2} toneMapped={false} />
      </mesh>
    </group>
  );
}

interface BasePropsProps {
  ultra: boolean;
  dayFactor: number;
  reducedMotion: boolean;
}

/** All exterior base props (E3) -- see this file's own top comment for the
 * tier split. Mounted from Scene.tsx alongside Rocks/Ground, outside the
 * plaza. */
export default function BaseProps({ ultra, dayFactor, reducedMotion }: BasePropsProps) {
  return (
    <>
      {/* Both tiers -- cheap procedural geometry, no GLB load. */}
      <LandingPad dayFactor={dayFactor} />
      <AntennaMast reducedMotion={reducedMotion} />
      {/* Ultra tier only -- real kit GLBs, "the heavier set" per this pass's
          own brief (matches HubRoom/DeskCluster/Plaza's own ultra-only gate
          in Scene.tsx). */}
      {ultra && (
        <>
          <SatelliteDishes dayFactor={dayFactor} />
          <SolarArray />
          <Rover />
          <ContainersAndBarrels />
          <PipesAlongEdge />
          <PerimeterLights dayFactor={dayFactor} />
          {/* W2 (2026-09-14): shuttle on the landing pad + exterior server
              annex -- see each component's own header comment. */}
          <Shuttle dayFactor={dayFactor} />
          <ServerAnnex dayFactor={dayFactor} />
        </>
      )}
    </>
  );
}

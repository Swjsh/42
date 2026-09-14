"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { PALETTE, lerp } from "./palette";
import { KIT_PATHS, KitProp } from "./SetKit";

// ─── E3, World-3 environment pass (2026-09-14, J: "grey abyss... space theme
// or a park or something real") ─────────────────────────────────────────────
// Base props ringing the plaza: dishes, a solar array, a landing pad, a
// rover, containers/barrels, pipes, perimeter lights, one antenna mast.
// Every position below sits at radius >=19.5, clearing Scene.tsx's own
// PLAZA_RADIUS (~18.2) with margin -- structurally outside the hub/bay/
// corridor footprint (all <=~18.2) regardless of the dynamic per-row bay
// angles computed in Scene.tsx, so nothing here can block a doorway. Heavy
// (real-GLB) pieces are ultra-tier only, matching every other real-kit-
// geometry piece in this tree; the antenna mast + landing pad (both cheap
// procedural geometry, no GLB) render on BOTH tiers -- "TV tier gets
// sky+ground+planet+a few props" per this pass's own brief.

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

function SolarArray() {
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
      <KitProp path={KIT_PATHS.baseProps.supportsHigh} scale={1.6} position={[SOLAR_ORIGIN[0] - SOLAR_SPACING * 1.8, 0, SOLAR_ORIGIN[2] - 0.5]} castShadow />
      <KitProp path={KIT_PATHS.baseProps.supportsHigh} scale={1.6} position={[SOLAR_ORIGIN[0] + SOLAR_SPACING * 1.8, 0, SOLAR_ORIGIN[2] + SOLAR_ROWS * SOLAR_SPACING]} castShadow />
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

// ─── Rover -- parked, static (no motion: J's own HQ face rule -- "motion =
// events with a ticker", this rover has no event source, so it never moves). ─
function Rover() {
  return (
    <KitProp
      path={KIT_PATHS.baseProps.rover}
      scale={2.4}
      position={polar(150, 21)}
      rotation={[0, _deg(150 + 90), 0]}
      castShadow
      receiveShadow
    />
  );
}

// ─── Containers + barrels -- a small cluster, "by a corridor" (the plaza's
// own outer edge, nearest the lane ring's own corridor gaps). ──────────────
function ContainersAndBarrels() {
  const base = polar(60, 21);
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
      {PIPE_AZIMUTHS.map((az, i) => (
        <KitProp
          key={az}
          path={i % 2 === 0 ? KIT_PATHS.baseProps.pipeStraight : KIT_PATHS.baseProps.pipeCorner}
          scale={1.8}
          position={polar(az, 19.5)}
          rotation={[0, _deg(az + 90), 0]}
          castShadow
        />
      ))}
    </>
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
        </>
      )}
    </>
  );
}

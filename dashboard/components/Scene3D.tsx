"use client";

import { Canvas, useFrame } from "@react-three/fiber";
import { Float, MeshReflectorMaterial } from "@react-three/drei";
import { EffectComposer, Bloom } from "@react-three/postprocessing";
import { useEffect, useRef, useMemo, useState } from "react";
import * as THREE from "three";

// =============================================================================
// Lightweight reflector + single-pass bloom re-enabled with conservative
// settings (low-res render target, no mipmap blur, threshold 0.85). Earlier
// context-loss issues came from HUGE settings (blur 200x80 @ 512²+mipmap
// chain). At these settings the GPU footprint is small enough to survive
// hot-reload chains.
// =============================================================================

// =============================================================================
// AMBIENT 3D TRADING FLOOR
//
// Pure procedural geometry — no GLBs, no asset pipeline. Two seated trader
// silhouettes at desks, monitor walls, reflective floor, city glow, fog, bloom.
// Sits behind the dashboard UI; characters are environmental, not the focus.
// =============================================================================

const PALETTE = {
  bgFog: "#040808",
  monitorCyan: "#3ad6c8",
  monitorGreen: "#5ce58a",
  warmAccent: "#ffb066",
  rimLight: "#7accff",
  charcoal: "#0d1413",
  desk: "#1a1d1f",
  chair: "#0a0c0e",
  skinTone: "#3a3a44",
  jacketGojo: "#0e1418",
  jacketItadori: "#241814",
};

// =============================================================================
// MONITOR — emissive plane that subtly flickers and scrolls a fake-data texture
// =============================================================================

interface MonitorProps {
  position: [number, number, number];
  rotation?: [number, number, number];
  width?: number;
  height?: number;
  color: string;
  seed?: number;
}

function Monitor({
  position,
  rotation = [0, 0, 0],
  width = 1.2,
  height = 0.7,
  color,
  seed = 0,
}: MonitorProps) {
  const matRef = useRef<THREE.MeshStandardMaterial>(null);
  const dataLineRef = useRef<THREE.Mesh>(null);

  useFrame((state) => {
    const t = state.clock.elapsedTime + seed;
    if (matRef.current) {
      // Subtle flicker — emissive intensity drifts
      const flicker = 1.3 + Math.sin(t * 2.3) * 0.06 + Math.sin(t * 7.1) * 0.03;
      matRef.current.emissiveIntensity = flicker;
    }
    if (dataLineRef.current) {
      // Fake "data line" scrolls slowly across the monitor
      dataLineRef.current.position.y =
        ((t * 0.18 + seed * 0.3) % 1) * height - height / 2;
    }
  });

  return (
    <group position={position} rotation={rotation}>
      {/* Bezel */}
      <mesh>
        <boxGeometry args={[width + 0.06, height + 0.06, 0.04]} />
        <meshStandardMaterial color="#08090a" roughness={0.7} metalness={0.4} />
      </mesh>
      {/* Screen */}
      <mesh position={[0, 0, 0.025]}>
        <planeGeometry args={[width, height]} />
        <meshStandardMaterial
          ref={matRef}
          color={color}
          emissive={color}
          emissiveIntensity={1.3}
          toneMapped={false}
        />
      </mesh>
      {/* Scrolling "data line" — one bright accent on the screen */}
      <mesh ref={dataLineRef} position={[0, 0, 0.027]}>
        <planeGeometry args={[width * 0.94, 0.012]} />
        <meshBasicMaterial color="#ffffff" transparent opacity={0.6} toneMapped={false} />
      </mesh>
      {/* Stand */}
      <mesh position={[0, -height / 2 - 0.12, -0.02]}>
        <boxGeometry args={[0.18, 0.16, 0.04]} />
        <meshStandardMaterial color="#0a0c0d" roughness={0.6} />
      </mesh>
    </group>
  );
}

// =============================================================================
// MONITOR WALL — stack of monitors at one desk
// =============================================================================

interface MonitorWallProps {
  position: [number, number, number];
  rotation?: [number, number, number];
  primary: string;
  secondary: string;
  seedOffset?: number;
}

function MonitorWall({
  position,
  rotation = [0, 0, 0],
  primary,
  secondary,
  seedOffset = 0,
}: MonitorWallProps) {
  return (
    <group position={position} rotation={rotation}>
      {/* Center main monitor */}
      <Monitor
        position={[0, 0.55, 0]}
        width={1.5}
        height={0.85}
        color={primary}
        seed={seedOffset}
      />
      {/* Left wing — angled slightly inward */}
      <Monitor
        position={[-1.05, 0.5, 0.12]}
        rotation={[0, 0.32, 0]}
        width={0.95}
        height={0.7}
        color={secondary}
        seed={seedOffset + 1.7}
      />
      {/* Right wing */}
      <Monitor
        position={[1.05, 0.5, 0.12]}
        rotation={[0, -0.32, 0]}
        width={0.95}
        height={0.7}
        color={secondary}
        seed={seedOffset + 3.1}
      />
      {/* Small lower-left monitor */}
      <Monitor
        position={[-0.7, -0.18, 0.06]}
        width={0.6}
        height={0.4}
        color={primary}
        seed={seedOffset + 5.5}
      />
      {/* Small lower-right monitor */}
      <Monitor
        position={[0.7, -0.18, 0.06]}
        width={0.6}
        height={0.4}
        color={secondary}
        seed={seedOffset + 6.9}
      />
    </group>
  );
}

// =============================================================================
// DESK — wide dark surface with subtle gloss + edge LED strip
// =============================================================================

interface DeskProps {
  position: [number, number, number];
  width?: number;
  depth?: number;
  ledColor: string;
}

function Desk({ position, width = 3.4, depth = 1.4, ledColor }: DeskProps) {
  return (
    <group position={position}>
      {/* Top */}
      <mesh receiveShadow>
        <boxGeometry args={[width, 0.06, depth]} />
        <meshStandardMaterial
          color={PALETTE.desk}
          roughness={0.35}
          metalness={0.5}
        />
      </mesh>
      {/* Front edge LED strip */}
      <mesh position={[0, -0.02, depth / 2 + 0.001]}>
        <boxGeometry args={[width * 0.96, 0.012, 0.01]} />
        <meshStandardMaterial
          color={ledColor}
          emissive={ledColor}
          emissiveIntensity={1.6}
          toneMapped={false}
        />
      </mesh>
      {/* Left leg */}
      <mesh position={[-width / 2 + 0.1, -0.45, 0]}>
        <boxGeometry args={[0.06, 0.85, depth * 0.85]} />
        <meshStandardMaterial color={PALETTE.charcoal} roughness={0.6} />
      </mesh>
      {/* Right leg */}
      <mesh position={[width / 2 - 0.1, -0.45, 0]}>
        <boxGeometry args={[0.06, 0.85, depth * 0.85]} />
        <meshStandardMaterial color={PALETTE.charcoal} roughness={0.6} />
      </mesh>
      {/* Keyboard suggestion */}
      <mesh position={[0, 0.04, depth / 2 - 0.35]}>
        <boxGeometry args={[1.0, 0.02, 0.32]} />
        <meshStandardMaterial color="#06080a" roughness={0.8} />
      </mesh>
      {/* Mouse */}
      <mesh position={[0.65, 0.045, depth / 2 - 0.32]}>
        <boxGeometry args={[0.08, 0.025, 0.13]} />
        <meshStandardMaterial color="#0a0d0f" roughness={0.7} />
      </mesh>
      {/* Mug — small warm accent */}
      <mesh position={[-1.2, 0.13, depth / 2 - 0.2]}>
        <cylinderGeometry args={[0.07, 0.07, 0.18, 16]} />
        <meshStandardMaterial
          color="#1a1a1c"
          emissive={PALETTE.warmAccent}
          emissiveIntensity={0.15}
          roughness={0.4}
        />
      </mesh>
    </group>
  );
}

// =============================================================================
// CHAIR — ergonomic profile, low-poly
// =============================================================================

function Chair({ position }: { position: [number, number, number] }) {
  return (
    <group position={position}>
      {/* Seat */}
      <mesh position={[0, 0, 0]}>
        <boxGeometry args={[0.55, 0.08, 0.55]} />
        <meshStandardMaterial color={PALETTE.chair} roughness={0.6} />
      </mesh>
      {/* Backrest */}
      <mesh position={[0, 0.45, -0.24]}>
        <boxGeometry args={[0.55, 0.95, 0.07]} />
        <meshStandardMaterial color={PALETTE.chair} roughness={0.6} />
      </mesh>
      {/* Center column */}
      <mesh position={[0, -0.3, 0]}>
        <cylinderGeometry args={[0.04, 0.04, 0.5, 12]} />
        <meshStandardMaterial color="#161819" roughness={0.5} metalness={0.6} />
      </mesh>
      {/* Five-star base */}
      <mesh position={[0, -0.55, 0]}>
        <cylinderGeometry args={[0.32, 0.32, 0.04, 5]} />
        <meshStandardMaterial color="#0a0c0d" roughness={0.5} metalness={0.5} />
      </mesh>
    </group>
  );
}

// =============================================================================
// TRADER FIGURE — stylized seated silhouette
//
// Capsule torso + sphere head + simple arms. Subtle anime-cyberpunk influence
// via a single emissive accent line (collar/jacket trim). Sits at desk,
// breathes, types, occasionally glances. Deliberately not character-accurate —
// these are ambient agents, not heroes.
// =============================================================================

interface TraderProps {
  position: [number, number, number];
  jacketColor: string;
  hairColor: string;
  accentColor: string;
  seed?: number;
}

function Trader({
  position,
  jacketColor,
  hairColor,
  accentColor,
  seed = 0,
}: TraderProps) {
  const torsoRef = useRef<THREE.Group>(null);
  const headRef = useRef<THREE.Group>(null);
  const leftArmRef = useRef<THREE.Group>(null);
  const rightArmRef = useRef<THREE.Group>(null);

  useFrame((state) => {
    const t = state.clock.elapsedTime + seed;

    // Breathing — gentle Y scale on torso
    if (torsoRef.current) {
      const breath = 1 + Math.sin(t * 1.2) * 0.012;
      torsoRef.current.scale.y = breath;
      // Tiny posture shift
      torsoRef.current.rotation.z = Math.sin(t * 0.21) * 0.015;
    }

    // Head — rare glance (sin-noised), subtle bob
    if (headRef.current) {
      const glance = Math.sin(t * 0.18 + seed) * Math.sin(t * 0.07);
      headRef.current.rotation.y = glance * 0.18;
      headRef.current.rotation.x = Math.sin(t * 0.9) * 0.018;
    }

    // Typing — arms make small back-and-forth motions on X axis,
    // slightly out of phase
    if (leftArmRef.current) {
      leftArmRef.current.rotation.x =
        -0.9 + Math.sin(t * 6.2 + seed * 1.7) * 0.06;
    }
    if (rightArmRef.current) {
      rightArmRef.current.rotation.x =
        -0.9 + Math.sin(t * 6.4 + seed * 1.7 + 1.2) * 0.06;
    }
  });

  return (
    <group position={position}>
      {/* Hips/lower body — under desk, suggested only */}
      <mesh position={[0, -0.05, 0]}>
        <boxGeometry args={[0.42, 0.18, 0.4]} />
        <meshStandardMaterial color={jacketColor} roughness={0.7} />
      </mesh>

      {/* Torso group — breathes */}
      <group ref={torsoRef} position={[0, 0.32, -0.04]}>
        {/* Torso — capsule */}
        <mesh>
          <capsuleGeometry args={[0.22, 0.36, 6, 12]} />
          <meshStandardMaterial color={jacketColor} roughness={0.7} />
        </mesh>
        {/* Accent collar trim — single emissive line, subtle anime/cyberpunk read */}
        <mesh position={[0, 0.18, 0.16]} rotation={[0.2, 0, 0]}>
          <torusGeometry args={[0.15, 0.008, 8, 24, Math.PI * 1.1]} />
          <meshStandardMaterial
            color={accentColor}
            emissive={accentColor}
            emissiveIntensity={1.2}
            toneMapped={false}
          />
        </mesh>

        {/* Head group — glances around */}
        <group ref={headRef} position={[0, 0.42, 0]}>
          {/* Head */}
          <mesh>
            <sphereGeometry args={[0.16, 16, 16]} />
            <meshStandardMaterial color={PALETTE.skinTone} roughness={0.65} />
          </mesh>
          {/* Hair cap */}
          <mesh position={[0, 0.06, -0.01]}>
            <sphereGeometry
              args={[0.17, 16, 16, 0, Math.PI * 2, 0, Math.PI * 0.55]}
            />
            <meshStandardMaterial color={hairColor} roughness={0.55} />
          </mesh>
          {/* Eye glow (suggestion of monitor reflection on glasses/eyes) */}
          <mesh position={[-0.05, 0.0, 0.14]}>
            <sphereGeometry args={[0.018, 8, 8]} />
            <meshBasicMaterial color={accentColor} toneMapped={false} />
          </mesh>
          <mesh position={[0.05, 0.0, 0.14]}>
            <sphereGeometry args={[0.018, 8, 8]} />
            <meshBasicMaterial color={accentColor} toneMapped={false} />
          </mesh>
        </group>

        {/* Left arm — typing */}
        <group ref={leftArmRef} position={[-0.22, 0.05, 0.05]}>
          <mesh position={[0, -0.18, 0.18]} rotation={[0, 0, 0.05]}>
            <capsuleGeometry args={[0.06, 0.36, 4, 8]} />
            <meshStandardMaterial color={jacketColor} roughness={0.7} />
          </mesh>
          {/* Forearm */}
          <mesh position={[0, -0.32, 0.32]} rotation={[1.0, 0, 0]}>
            <capsuleGeometry args={[0.055, 0.28, 4, 8]} />
            <meshStandardMaterial color={jacketColor} roughness={0.7} />
          </mesh>
        </group>

        {/* Right arm — typing */}
        <group ref={rightArmRef} position={[0.22, 0.05, 0.05]}>
          <mesh position={[0, -0.18, 0.18]} rotation={[0, 0, -0.05]}>
            <capsuleGeometry args={[0.06, 0.36, 4, 8]} />
            <meshStandardMaterial color={jacketColor} roughness={0.7} />
          </mesh>
          <mesh position={[0, -0.32, 0.32]} rotation={[1.0, 0, 0]}>
            <capsuleGeometry args={[0.055, 0.28, 4, 8]} />
            <meshStandardMaterial color={jacketColor} roughness={0.7} />
          </mesh>
        </group>
      </group>
    </group>
  );
}

// =============================================================================
// CITY SKYLINE — distant emissive plane with blinking window pixels
// =============================================================================

function CitySkyline() {
  const matRef = useRef<THREE.ShaderMaterial>(null);

  // Procedural "windows" via shader — cheap, no texture asset
  const shader = useMemo(
    () => ({
      uniforms: { uTime: { value: 0 } },
      vertexShader: `
        varying vec2 vUv;
        void main() {
          vUv = uv;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        varying vec2 vUv;
        uniform float uTime;
        float hash(vec2 p) {
          return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
        }
        void main() {
          // City silhouette — taller buildings cluster in the middle
          float skyline = 0.55
            + 0.20 * sin(vUv.x * 12.0)
            + 0.12 * sin(vUv.x * 31.0 + 1.3)
            + 0.08 * sin(vUv.x * 57.0);
          float buildingMask = step(vUv.y, skyline);

          // Window grid
          vec2 grid = vec2(220.0, 80.0);
          vec2 cell = floor(vUv * grid);
          float window = hash(cell);
          float lit = step(0.78, window);

          // Slow blink for ~3% of windows
          float blink = step(0.97, hash(cell + 13.0));
          float blinkPhase = step(0.5, fract(uTime * 0.4 + hash(cell) * 5.0));
          float windowOn = lit * (1.0 - blink * blinkPhase);

          vec3 windowColor = mix(
            vec3(1.0, 0.75, 0.4),  // warm
            vec3(0.4, 0.85, 1.0),  // cool
            hash(cell + 7.0)
          );

          // Sky gradient — deep navy fading to black
          vec3 sky = mix(vec3(0.02, 0.03, 0.06), vec3(0.0), vUv.y);
          vec3 building = vec3(0.015, 0.02, 0.025);
          vec3 col = mix(sky, building, buildingMask);
          col += windowColor * windowOn * buildingMask * 1.4;

          // Soft horizon haze
          col += vec3(0.05, 0.12, 0.18) * smoothstep(0.55, 0.45, vUv.y) * 0.18;

          gl_FragColor = vec4(col, 1.0);
        }
      `,
    }),
    []
  );

  useFrame((state) => {
    if (matRef.current) {
      matRef.current.uniforms.uTime.value = state.clock.elapsedTime;
    }
  });

  return (
    <mesh position={[0, 2.0, -14]}>
      <planeGeometry args={[34, 8]} />
      <shaderMaterial
        ref={matRef}
        uniforms={shader.uniforms}
        vertexShader={shader.vertexShader}
        fragmentShader={shader.fragmentShader}
      />
    </mesh>
  );
}

// =============================================================================
// CAMERA RIG — slow drift to keep the scene feeling alive
// =============================================================================

function CameraRig() {
  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const cam = state.camera;
    // Tiny orbital drift around the focal point
    const driftX = Math.sin(t * 0.08) * 0.18;
    const driftY = Math.sin(t * 0.06) * 0.06;
    cam.position.x = 0 + driftX;
    cam.position.y = 2.4 + driftY;
    cam.position.z = 5.8;
    cam.lookAt(0, 0.4, -3);
  });
  return null;
}

// =============================================================================
// BACK-WALL MONITOR BANK — grid of small dim screens flanking the city window
// =============================================================================

interface BackWallMonitorBankProps {
  side: "left" | "right";
}

function BackWallMonitorBank({ side }: BackWallMonitorBankProps) {
  const sign = side === "left" ? -1 : 1;
  // 4 columns x 2 rows of monitors flanking the city window
  const cols = 4;
  const rows = 2;
  const cellW = 1.0;
  const cellH = 0.6;
  const gapX = 0.16;
  const gapY = 0.14;
  const startX = sign * 9.5;
  const startY = 1.6;

  // Pre-compute deterministic color + brightness mix
  const cells = useMemo(() => {
    const out: Array<{
      x: number;
      y: number;
      color: string;
      brightness: number;
    }> = [];
    const palette = [
      PALETTE.monitorCyan,
      PALETTE.monitorGreen,
      PALETTE.monitorCyan,
      PALETTE.warmAccent,
      PALETTE.monitorGreen,
      "#ff6b6b", // bear-red accent monitor
      PALETTE.monitorCyan,
      PALETTE.monitorGreen,
    ];
    for (let r = 0; r < rows; r++) {
      for (let c = 0; c < cols; c++) {
        const i = r * cols + c;
        // Stagger columns outward from center
        const colOffset = sign * (c * (cellW + gapX));
        const rowOffset = -r * (cellH + gapY);
        out.push({
          x: startX + colOffset,
          y: startY + rowOffset,
          color: palette[(i + (side === "left" ? 0 : 3)) % palette.length],
          brightness: 0.5 + ((i * 37) % 40) / 100, // 0.5 - 0.9
        });
      }
    }
    return out;
  }, [sign, side]);

  return (
    <group>
      {cells.map((cell, i) => (
        <mesh
          key={`${side}-${i}`}
          position={[cell.x, cell.y, -7.5]}
          rotation={[0, sign * -Math.PI * 0.18, 0]}
        >
          <planeGeometry args={[cellW, cellH]} />
          <meshStandardMaterial
            color={cell.color}
            emissive={cell.color}
            emissiveIntensity={cell.brightness}
            toneMapped={false}
          />
        </mesh>
      ))}
    </group>
  );
}

// =============================================================================
// SCENE CONTENTS
// =============================================================================

function SceneContents() {
  return (
    <>
      {/* Atmospheric fog — pulls the city back, hides the seam */}
      <fog attach="fog" args={[PALETTE.bgFog, 6, 20]} />
      <color attach="background" args={[PALETTE.bgFog]} />

      {/* Lights ----------------------------------------------------------- */}
      {/* Soft fill so silhouettes aren't pitch black */}
      <ambientLight intensity={0.18} color="#5a7a8a" />

      {/* Cool overhead — moonlight-through-skylight feel */}
      <directionalLight
        position={[2, 6, 2]}
        intensity={0.35}
        color={PALETTE.rimLight}
      />

      {/* Warm wall accent — single sodium-lamp-style point light off-camera */}
      <pointLight
        position={[-5, 1.8, -2]}
        intensity={2.5}
        color={PALETTE.warmAccent}
        distance={9}
        decay={2.0}
      />

      {/* Monitor wash — strong cyan from where the screens face the traders */}
      <pointLight
        position={[-2.0, 1.2, -1.6]}
        intensity={3.0}
        color={PALETTE.monitorCyan}
        distance={5}
        decay={2.0}
      />
      <pointLight
        position={[2.4, 1.2, -1.6]}
        intensity={2.6}
        color={PALETTE.monitorGreen}
        distance={5}
        decay={2.0}
      />

      {/* Floor — lightweight reflector. Resolution 256 + small blur means a
          single ~1MB render target (vs the 16MB of the original 512² + 200px
          blur). Reflects the monitor glow back up onto the desks for the
          signature cyberpunk wet-floor look. */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.55, 0]}>
        <planeGeometry args={[40, 30]} />
        <MeshReflectorMaterial
          blur={[60, 20]}
          resolution={256}
          mixBlur={0.6}
          mixStrength={1.4}
          mirror={0.45}
          color="#070a0c"
          roughness={0.55}
          metalness={0.55}
          depthScale={0.4}
        />
      </mesh>

      {/* Back wall — dark, with subtle vertical seam panels */}
      <mesh position={[0, 1.5, -8]}>
        <planeGeometry args={[40, 8]} />
        <meshStandardMaterial
          color="#06090b"
          roughness={0.9}
          metalness={0.1}
        />
      </mesh>

      {/* City skyline visible through suggested "window" */}
      <CitySkyline />

      {/* Window frame — thin bezel suggesting we're looking through glass */}
      <mesh position={[0, 2.0, -7.92]}>
        <planeGeometry args={[18, 4.5]} />
        <meshBasicMaterial color="#000000" transparent opacity={0.0} />
      </mesh>
      <mesh position={[0, 4.3, -7.85]}>
        <boxGeometry args={[18.2, 0.06, 0.04]} />
        <meshStandardMaterial color="#0c0f12" />
      </mesh>
      <mesh position={[0, -0.3, -7.85]}>
        <boxGeometry args={[18.2, 0.06, 0.04]} />
        <meshStandardMaterial color="#0c0f12" />
      </mesh>

      {/* Ceiling LED grid — three parallel strips, data-center vibe */}
      {[-1.4, 0, 1.4].map((zOffset, i) => (
        <Float
          key={`ceil-${i}`}
          speed={0.3 + i * 0.07}
          rotationIntensity={0}
          floatIntensity={0.05}
        >
          <mesh position={[0, 4.1, -3 + zOffset]}>
            <boxGeometry args={[6, 0.03, 0.06]} />
            <meshStandardMaterial
              color={PALETTE.monitorCyan}
              emissive={PALETTE.monitorCyan}
              emissiveIntensity={1.2}
              toneMapped={false}
            />
          </mesh>
        </Float>
      ))}

      {/* Back-wall monitor banks — flanks the city window with rows of dim
          colored screens. Conveys "live trading floor with banks of data"
          without adding meaningful GPU cost (just static emissive planes). */}
      <BackWallMonitorBank side="left" />
      <BackWallMonitorBank side="right" />

      {/* PRIMARY DESK (center) — Gojo-equivalent, cyan-dominant */}
      <Desk position={[-1.8, 0, -3]} ledColor={PALETTE.monitorCyan} />
      <Chair position={[-1.8, 0.05, -2.05]} />
      <MonitorWall
        position={[-1.8, 0.85, -3.55]}
        primary={PALETTE.monitorCyan}
        secondary={PALETTE.monitorGreen}
        seedOffset={0}
      />
      <Trader
        position={[-1.8, 0.18, -2.08]}
        jacketColor={PALETTE.jacketGojo}
        hairColor="#e8ecef"
        accentColor={PALETTE.monitorCyan}
        seed={0}
      />

      {/* SECONDARY DESK — Itadori-equivalent, green-dominant */}
      <Desk position={[2.2, 0, -3.2]} ledColor={PALETTE.monitorGreen} />
      <Chair position={[2.2, 0.05, -2.25]} />
      <MonitorWall
        position={[2.2, 0.85, -3.75]}
        primary={PALETTE.monitorGreen}
        secondary={PALETTE.monitorCyan}
        seedOffset={2.5}
      />
      <Trader
        position={[2.2, 0.18, -2.28]}
        jacketColor={PALETTE.jacketItadori}
        hairColor="#d04848"
        accentColor={PALETTE.monitorGreen}
        seed={1.7}
      />

      <CameraRig />
    </>
  );
}

// =============================================================================
// PUBLIC EXPORT
// =============================================================================

export default function Scene3D() {
  // Track the wrapper's pixel dimensions ourselves and pass them to Canvas
  // explicitly. R3F v9's internal ResizeObserver misses the initial measure
  // when the parent uses dynamic flex layouts, leaving the canvas at the
  // default 300x150. Driving size from our own observer avoids that race.
  const wrapRef = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const sync = () => {
      const r = el.getBoundingClientRect();
      if (r.width > 0 && r.height > 0) {
        setSize({ w: r.width, h: r.height });
      }
    };
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return (
    <div
      ref={wrapRef}
      style={{ position: "absolute", inset: 0, width: "100%", height: "100%" }}
    >
      {size && (
        <Canvas
          // Key on size so the Canvas fully remounts when size changes.
          // R3F v9's internal measure system can miss the initial frame when
          // the parent is already final-sized; remounting with a size-derived
          // key guarantees a fresh setup at the right dimensions every time.
          key={`${size.w}x${size.h}`}
          shadows={false}
          dpr={[1, 1.5]}
          camera={{ position: [0, 2.4, 5.8], fov: 32, near: 0.1, far: 60 }}
          style={{ width: size.w, height: size.h, display: "block" }}
          onCreated={(state) => {
            // Belt-and-suspenders: explicitly set the renderer size
            // immediately on creation to bypass any measure race.
            state.setSize(size.w, size.h);
          }}
        >
          <SceneContents />
          <EffectComposer multisampling={0} enableNormalPass={false}>
            <Bloom
              intensity={0.55}
              luminanceThreshold={0.78}
              luminanceSmoothing={0.4}
              mipmapBlur={false}
            />
          </EffectComposer>
        </Canvas>
      )}
    </div>
  );
}

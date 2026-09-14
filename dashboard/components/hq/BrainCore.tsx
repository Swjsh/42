"use client";

import { useRef } from "react";
import type { CSSProperties } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import { clamp01, lerp, PALETTE } from "./palette";

interface BrainCoreProps {
  utilPct: number | null;
  memUsedMib: number | null;
  memTotalMib: number | null;
  modelName: string | null;
  gaming: boolean;
  dimFactor: number;
  reducedMotion: boolean;
}

const GAUGE_WIDTH = 1.8;

/**
 * Central hub -- Gamma's "brain core". Sphere + two counter-rotating rings +
 * an additive glow sprite (intensity scales with GPU util) + a memory gauge
 * bar + an <Html> plaque (never drei <Text>, which would fetch a font).
 * Continuous motion (rotation, flicker) is computed directly from
 * state.clock.elapsedTime -- cheap scalar math, no throttling needed.
 */
export default function BrainCore({
  utilPct, memUsedMib, memTotalMib, modelName, gaming, dimFactor, reducedMotion,
}: BrainCoreProps) {
  const coreMat = useRef<THREE.MeshStandardMaterial>(null);
  const ringA = useRef<THREE.Mesh>(null);
  const ringB = useRef<THREE.Mesh>(null);
  const ringAMat = useRef<THREE.MeshBasicMaterial>(null);
  const ringBMat = useRef<THREE.MeshBasicMaterial>(null);
  const glowMat = useRef<THREE.SpriteMaterial>(null);

  const utilFrac = clamp01((utilPct ?? 0) / 100);
  const memFrac = memUsedMib && memTotalMib ? clamp01(memUsedMib / memTotalMib) : 0;
  // One accent moment (2026-09-13): when the brain is genuinely busy (GPU
  // util > 30%), the rings brighten -- Scene.tsx pairs this with faster
  // corridor pulses from the same utilPct reading.
  const ringBoost = utilFrac > 0.3 ? 1 + Math.min(1, (utilFrac - 0.3) / 0.7) * 0.7 : 1;

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const spin = reducedMotion ? 0 : t;
    if (ringA.current) ringA.current.rotation.z = spin * 0.35;
    if (ringB.current) ringB.current.rotation.x = spin * -0.28;

    const flicker = Math.sin(t * 2.1) * 0.06;
    const baseGlow = lerp(0.7, 2.6, utilFrac) * dimFactor;
    if (coreMat.current) coreMat.current.emissiveIntensity = baseGlow + flicker;
    if (glowMat.current) glowMat.current.opacity = clamp01(0.35 + utilFrac * 0.5) * dimFactor;
    if (ringAMat.current) ringAMat.current.color.set(PALETTE.hubRing).multiplyScalar(ringBoost * dimFactor);
    if (ringBMat.current) ringBMat.current.color.set("#7ad9ff").multiplyScalar(ringBoost * dimFactor);
  });

  const gaugeColor = memFrac > 0.85 ? "#ff3b3b" : memFrac > 0.6 ? "#ffb020" : "#22ff88";

  return (
    <group scale={1.15}>
      {/* Core sphere -- Lambert (cheap N.L diffuse, no PBR/roughness sampling)
          keeps the same emissive/emissiveIntensity animation path Standard
          had, at a fraction of the fragment cost on a weak mobile GPU. */}
      <mesh>
        <sphereGeometry args={[1.05, 20, 16]} />
        <meshLambertMaterial
          ref={coreMat}
          color={PALETTE.hubCore}
          emissive={PALETTE.hubCore}
          emissiveIntensity={1}
          toneMapped={false}
        />
      </mesh>

      {/* Counter-rotating rings -- thickened (was 0.02-0.025 tube radius,
          near-invisible/aliased with antialias off) and opaque (no blend
          cost) per the TV-crispness pass; brighten together as the "one
          accent moment" when the brain is busy (ringBoost, see above). */}
      <mesh ref={ringA} rotation={[Math.PI / 2.4, 0, 0]}>
        <torusGeometry args={[1.55, 0.05, 8, 48]} />
        <meshBasicMaterial ref={ringAMat} color={PALETTE.hubRing} toneMapped={false} />
      </mesh>
      <mesh ref={ringB} rotation={[0, 0, Math.PI / 3]}>
        <torusGeometry args={[1.95, 0.04, 8, 48]} />
        <meshBasicMaterial ref={ringBMat} color="#7ad9ff" toneMapped={false} />
      </mesh>

      {/* Additive glow sprite -- camera-facing, cheap */}
      <sprite scale={[3.6, 3.6, 1]}>
        <spriteMaterial ref={glowMat} color={PALETTE.hubCore} transparent opacity={0.5} depthWrite={false} blending={THREE.AdditiveBlending} />
      </sprite>

      {/* Memory gauge: background + fill, anchored left */}
      <group position={[0, -1.6, 0]}>
        <mesh>
          <boxGeometry args={[GAUGE_WIDTH, 0.09, 0.05]} />
          <meshBasicMaterial color="#0e1626" transparent opacity={0.9} />
        </mesh>
        <mesh position={[-GAUGE_WIDTH / 2 + (GAUGE_WIDTH * Math.max(memFrac, 0.02)) / 2, 0, 0.01]}>
          <boxGeometry args={[GAUGE_WIDTH * Math.max(memFrac, 0.02), 0.09, 0.05]} />
          <meshBasicMaterial color={gaugeColor} toneMapped={false} />
        </mesh>
        <Html position={[0, -0.22, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
          <div style={{ color: "#7f93b0", fontSize: 16, fontFamily: "system-ui, sans-serif", whiteSpace: "nowrap" }}>
            MEM {memUsedMib ?? "?"}/{memTotalMib ?? "?"} MiB
          </div>
        </Html>
      </group>

      {/* Model plaque -- 10-foot-readability sizing (2026-09-13): ~34px, the
          brain's own status line, must read clearly across a room on the 4K
          panel. Wrapped in .hq-beam (Border Beam, see Hud.tsx's shared
          <style>) since this is the hub's own HUD-adjacent plaque. */}
      <Html position={[0, 1.75, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
        <div className="hq-beam" style={{ "--beam-color": "#7ad9ff", borderRadius: 8 } as CSSProperties}>
          <div
            style={{
              color: "#dff3ff", fontSize: 34, fontWeight: 700, fontFamily: "system-ui, sans-serif",
              background: "rgba(3,4,10,0.7)", padding: "4px 20px", borderRadius: 7,
              whiteSpace: "nowrap",
            }}
          >
            {modelName || "BRAIN IDLE"}
          </div>
        </div>
      </Html>

      {/* Gaming-mode plaque */}
      {gaming && (
        <Html position={[0, 3.0, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
          <div
            style={{
              color: "#ffb020", fontSize: 18, fontWeight: 700, fontFamily: "system-ui, sans-serif",
              background: "rgba(40,26,0,0.75)", padding: "6px 18px", borderRadius: 8,
              border: "1px solid #ffb020", whiteSpace: "nowrap", letterSpacing: 0.5,
              boxShadow: "0 0 18px rgba(255,176,32,0.5)",
            }}
          >
            GPU RESERVED -- J IS GAMING
          </div>
        </Html>
      )}
    </group>
  );
}

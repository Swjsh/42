"use client";

import { useRef } from "react";
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
  const glowMat = useRef<THREE.SpriteMaterial>(null);

  const utilFrac = clamp01((utilPct ?? 0) / 100);
  const memFrac = memUsedMib && memTotalMib ? clamp01(memUsedMib / memTotalMib) : 0;

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const spin = reducedMotion ? 0 : t;
    if (ringA.current) ringA.current.rotation.z = spin * 0.35;
    if (ringB.current) ringB.current.rotation.x = spin * -0.28;

    const flicker = Math.sin(t * 2.1) * 0.06;
    const baseGlow = lerp(0.7, 2.6, utilFrac) * dimFactor;
    if (coreMat.current) coreMat.current.emissiveIntensity = baseGlow + flicker;
    if (glowMat.current) glowMat.current.opacity = clamp01(0.35 + utilFrac * 0.5) * dimFactor;
  });

  const gaugeColor = memFrac > 0.85 ? "#ff3b3b" : memFrac > 0.6 ? "#ffb020" : "#22ff88";

  return (
    <group>
      {/* Core sphere */}
      <mesh>
        <sphereGeometry args={[1.05, 24, 18]} />
        <meshStandardMaterial
          ref={coreMat}
          color={PALETTE.hubCore}
          emissive={PALETTE.hubCore}
          emissiveIntensity={1}
          roughness={0.35}
          metalness={0.2}
          toneMapped={false}
        />
      </mesh>

      {/* Counter-rotating rings */}
      <mesh ref={ringA} rotation={[Math.PI / 2.4, 0, 0]}>
        <torusGeometry args={[1.55, 0.025, 8, 64]} />
        <meshBasicMaterial color={PALETTE.hubRing} transparent opacity={0.75 * dimFactor} toneMapped={false} />
      </mesh>
      <mesh ref={ringB} rotation={[0, 0, Math.PI / 3]}>
        <torusGeometry args={[1.95, 0.02, 8, 64]} />
        <meshBasicMaterial color="#7ad9ff" transparent opacity={0.5 * dimFactor} toneMapped={false} />
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
          <div style={{ color: "#7f93b0", fontSize: 12, fontFamily: "system-ui, sans-serif", whiteSpace: "nowrap" }}>
            MEM {memUsedMib ?? "?"}/{memTotalMib ?? "?"} MiB
          </div>
        </Html>
      </group>

      {/* Model plaque */}
      <Html position={[0, 1.7, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
        <div
          style={{
            color: "#dff3ff", fontSize: 14, fontFamily: "system-ui, sans-serif",
            background: "rgba(3,4,10,0.55)", padding: "3px 12px", borderRadius: 6,
            border: "1px solid rgba(122,217,255,0.35)", whiteSpace: "nowrap",
          }}
        >
          {modelName || "BRAIN IDLE"}
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

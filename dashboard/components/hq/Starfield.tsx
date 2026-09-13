"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { PALETTE } from "./palette";

const STAR_COUNT = 900;

/**
 * Background dressing: one Points cloud (single draw call) drifting slowly,
 * plus a distant planet sphere with a cheap atmosphere rim (a slightly
 * larger back-facing transparent sphere, not a custom fresnel shader --
 * simpler to build and maintain, and the brief explicitly allows either).
 */
export default function Starfield({ reducedMotion }: { reducedMotion: boolean }) {
  const points = useRef<THREE.Points>(null);
  const planetGroup = useRef<THREE.Group>(null);

  const positions = useMemo(() => {
    const arr = new Float32Array(STAR_COUNT * 3);
    // Deterministic layout (fixed seed math, not Math.random) so the field
    // never reshuffles on re-render -- a simple low-discrepancy-ish spread.
    for (let i = 0; i < STAR_COUNT; i++) {
      const a = i * 2.399963; // golden-angle-ish spread
      const r = 30 + (i % 37) * 1.6;
      const h = ((i * 13) % 60) - 30;
      arr[i * 3] = Math.cos(a) * r;
      arr[i * 3 + 1] = h;
      arr[i * 3 + 2] = Math.sin(a) * r;
    }
    return arr;
  }, []);

  useFrame((state) => {
    if (reducedMotion) return;
    const t = state.clock.elapsedTime;
    if (points.current) points.current.rotation.y = t * 0.006;
    if (planetGroup.current) planetGroup.current.rotation.y = t * 0.03;
  });

  return (
    <group>
      <points ref={points}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        </bufferGeometry>
        <pointsMaterial color="#bcd7ff" size={0.12} sizeAttenuation transparent opacity={0.75} />
      </points>

      <group ref={planetGroup} position={[-14, 6, -20]}>
        <mesh>
          <sphereGeometry args={[3.2, 24, 20]} />
          <meshStandardMaterial color={PALETTE.planet} roughness={0.9} metalness={0.05} />
        </mesh>
        <mesh>
          <sphereGeometry args={[3.42, 24, 20]} />
          <meshBasicMaterial
            color={PALETTE.planetRim}
            transparent
            opacity={0.18}
            side={THREE.BackSide}
            depthWrite={false}
          />
        </mesh>
      </group>
    </group>
  );
}

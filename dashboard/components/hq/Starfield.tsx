"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { PALETTE, makeMatcapTexture } from "./palette";

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
  const matcap = useMemo(() => makeMatcapTexture(), []);

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

      {/* World pass A (2026-09-13, J's own screenshot complaint: "huge
          black planet disc"): meshLambertMaterial only shades from the
          scene's own hemisphere+directional light, so the planet's
          hub-facing side (which those lights barely reach at this
          position/angle) read as flat black -- a "black hole", not a lit
          world. Swapped to the SAME procedural matcap every other hero
          surface in this scene already uses (BrainCore, characters):
          camera-facing pseudo-shading that is NEVER fully black on any
          side, zero new cost (matcap is a cached module-level singleton).
          Also moved further off-center/back and shrunk (radius 3.2->2.1,
          position pulled to a screen-corner-ish spot) so it reads as
          background dressing behind the station, not a dominant disc
          competing with it -- both purely COSMETIC, unverified beyond this
          screenshot pass, easy to nudge again. */}
      <group ref={planetGroup} position={[-26, 13, -34]}>
        <mesh>
          <sphereGeometry args={[2.1, 24, 18]} />
          <meshMatcapMaterial matcap={matcap} color={PALETTE.planet} />
        </mesh>
        <mesh>
          <sphereGeometry args={[2.28, 24, 20]} />
          <meshBasicMaterial
            color={PALETTE.planetRim}
            transparent
            opacity={0.32}
            side={THREE.BackSide}
            depthWrite={false}
            toneMapped={false}
          />
        </mesh>
      </group>
    </group>
  );
}

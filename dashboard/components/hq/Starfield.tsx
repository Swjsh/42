"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

const STAR_COUNT = 900;

interface StarfieldProps {
  reducedMotion: boolean;
  /** World-2 item 2 (2026-09-14, "Ground.tsx" item -- "Starfield stays but
   * must be night-only if it is not already"): 0 (deepest night) .. 1 (peak
   * midday), the SAME dayNightFactor() value SkyDome.tsx/Scene.tsx's own
   * lights already use. Stars fade out by day (a real station plaza under a
   * bright sky doesn't show stars) and back in at night. Defaults to 1 (day
   * -- hidden), the same "safer to hide something extra than show something
   * stuck" default direction SkyDome.tsx's own `dayFactor` prop documents. */
  dayFactor?: number;
}

/**
 * Background dressing: one Points cloud (single draw call) drifting slowly.
 * Used to also carry a distant planet sphere -- dropped Pass G-2 (2026-09-13,
 * see the comment at its old JSX site in git history / this file's blame):
 * read as "basically black" at its on-screen size even with matcap shading.
 */
export default function Starfield({ reducedMotion, dayFactor = 1 }: StarfieldProps) {
  const points = useRef<THREE.Points>(null);
  const mat = useRef<THREE.PointsMaterial>(null);

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
    // Day/night fade runs every frame regardless of reducedMotion -- that
    // flag freezes the slow ROTATION drift below, it was never meant to
    // freeze visibility itself (same split StationModule.tsx's beacon
    // blink/reducedMotion handling uses: motion stops, the real state cue
    // doesn't).
    // World-3 environment pass (2026-09-14, "visible day AND night (fainter
    // by day)"): floored at 0.12 instead of hitting exactly 0 -- root cause
    // #1 of the "grey abyss" report (ENVIRONMENT-PLAN.md) was this literally
    // going fully invisible at ANY daytime dayFactor, so the one texture
    // element behind the station vanished for the 12 daytime hours straight.
    // An airless sky has no atmosphere to wash stars out even at local noon.
    if (mat.current) mat.current.opacity = 0.12 + (1 - dayFactor) * 0.63;
    if (reducedMotion) return;
    const t = state.clock.elapsedTime;
    if (points.current) points.current.rotation.y = t * 0.006;
  });

  return (
    <group>
      <points ref={points}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        </bufferGeometry>
        <pointsMaterial ref={mat} color="#bcd7ff" size={0.12} sizeAttenuation transparent opacity={0.75} />
      </points>

      {/* Pass G-2 (2026-09-13, coordinator: "make the planet not a pure
          black disc (it is one now at the top of the frame) -- lit
          terminator or drop it"). World pass A's earlier matcap fix (see
          git history) swapped meshLambertMaterial for a camera-facing
          matcap specifically because it's never FULLY (0,0,0) black -- but
          makeMatcapTexture()'s own gradient is dark navy-to-near-black
          past its small top-left highlight (palette.ts: stops "#1c2c3c" at
          0.78, "#05090f" at 1.0), and PALETTE.planet ("#16324a") is itself
          a dark navy base color -- at this small an on-screen size, most of
          the visible disc still reads as "basically black" even though no
          single pixel is literal (0,0,0). Dropping it (the coordinator's
          own offered fallback) rather than building and tuning a real lit-
          terminator shader blind, with zero capture budget left to verify
          a second guess -- the scene keeps its stars + the SkyDome's own
          warmed gradient (see that file) for background interest. Group
          ref (planetGroup) and its rotation in useFrame below are now
          dead and removed together with this JSX. */}
    </group>
  );
}

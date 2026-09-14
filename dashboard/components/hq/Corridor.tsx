"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { lerp, PALETTE } from "./palette";

interface CorridorProps {
  from: [number, number, number];
  to: [number, number, number];
  freshness: number; // 0..1, 1 = just happened -- drives pulse speed
  speedBoost?: number; // >1 when the brain core is busy (GPU util > 30%)
  reducedMotion: boolean;
}

/**
 * World-2 item 3(c) (2026-09-14, J: "what I think are supposed to be
 * hallways for the people aren't really connected at all"): the wire tube
 * that used to run from every module to the hub is REMOVED entirely -- it
 * was a 0.06-radius cylinder with no width/floor/walls, reading as a cable,
 * not a hallway, and it duplicated (at the wrong visual weight)
 * SetKit.tsx#CorridorRun's own real floor-strip + kit-corridor geometry,
 * which is what now actually connects the hub to each bay (ultra tier).
 * What stays: the traveling pulse -- a small floor-hugging light (y+0.03,
 * not the old tube-center height) whose travel speed is still proportional
 * to how fresh that lane's last evidence is (fresh = fast), unconditional
 * on both tiers exactly as before (the TV tier's own cheap floor already
 * gives this a surface to hug -- see StationModule.tsx's TV-tier branch).
 */
export default function Corridor({ from, to, freshness, speedBoost = 1, reducedMotion }: CorridorProps) {
  const pulse = useRef<THREE.Mesh>(null);
  const speed = lerp(0.04, 0.5, freshness) * speedBoost; // cycles per second

  useFrame((state) => {
    if (!pulse.current || reducedMotion) return;
    const frac = (state.clock.elapsedTime * speed) % 1;
    pulse.current.position.set(
      from[0] + (to[0] - from[0]) * frac,
      from[1] + 0.03,
      from[2] + (to[2] - from[2]) * frac,
    );
  });

  return (
    <mesh ref={pulse} position={[from[0], from[1] + 0.03, from[2]]}>
      <sphereGeometry args={[0.09, 8, 6]} />
      <meshBasicMaterial color={PALETTE.hubRing} toneMapped={false} />
    </mesh>
  );
}

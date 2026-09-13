"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";
import { lerp, PALETTE } from "./palette";

interface CorridorProps {
  from: [number, number, number];
  to: [number, number, number];
  freshness: number; // 0..1, 1 = just happened -- drives pulse speed
  reducedMotion: boolean;
}

const UP = new THREE.Vector3(0, 1, 0);

/**
 * A static tube connecting a module to the hub, carrying one animated pulse
 * sprite whose travel speed is proportional to how fresh that lane's last
 * evidence is (fresh = fast). The tube's orientation quaternion is computed
 * ONCE via useMemo (not per frame); only the pulse's scalar position lerps
 * every tick, no vector allocation in the hot path.
 */
export default function Corridor({ from, to, freshness, reducedMotion }: CorridorProps) {
  const pulse = useRef<THREE.Mesh>(null);
  const speed = lerp(0.04, 0.5, freshness); // cycles per second

  const { length, midpoint, quaternion } = useMemo(() => {
    const dx = to[0] - from[0];
    const dy = to[1] - from[1];
    const dz = to[2] - from[2];
    const len = Math.sqrt(dx * dx + dy * dy + dz * dz) || 0.001;
    const dir = new THREE.Vector3(dx, dy, dz).normalize();
    const q = new THREE.Quaternion().setFromUnitVectors(UP, dir);
    return {
      length: len,
      midpoint: [(from[0] + to[0]) / 2, (from[1] + to[1]) / 2, (from[2] + to[2]) / 2] as [number, number, number],
      quaternion: q,
    };
  }, [from, to]);

  useFrame((state) => {
    if (!pulse.current || reducedMotion) return;
    const frac = (state.clock.elapsedTime * speed) % 1;
    pulse.current.position.set(
      from[0] + (to[0] - from[0]) * frac,
      from[1] + (to[1] - from[1]) * frac + 0.15,
      from[2] + (to[2] - from[2]) * frac,
    );
  });

  return (
    <group>
      <mesh position={midpoint} quaternion={quaternion}>
        <cylinderGeometry args={[0.035, 0.035, length, 6, 1, true]} />
        <meshBasicMaterial color={PALETTE.corridor} transparent opacity={0.55} side={THREE.DoubleSide} />
      </mesh>
      <mesh ref={pulse} position={from}>
        <sphereGeometry args={[0.07, 8, 6]} />
        <meshBasicMaterial color={PALETTE.hubRing} toneMapped={false} />
      </mesh>
    </group>
  );
}

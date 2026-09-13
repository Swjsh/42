"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import type { SectorRow } from "./types";
import type { AgentBehavior } from "./Agent";
import Agent from "./Agent";
import { healthColor, isParkedState, PALETTE } from "./palette";

interface StationModuleProps {
  position: [number, number, number];
  angle: number;
  row: SectorRow;
  behavior: AgentBehavior;
  reducedMotion: boolean;
  dimFactor: number;
  hubPosition: [number, number, number];
}

/** Local-space (module "front" = -Z, toward the hub) -> world-space, using
 * the SAME rotation this module's group applies (see rotationY below) --
 * computed with plain trig, not a matrix/quaternion, since it's only ever
 * called at render time for a couple of fixed offsets, never per frame. */
function localToWorld(
  center: [number, number, number], rotationY: number, local: [number, number, number],
): [number, number, number] {
  const cos = Math.cos(rotationY);
  const sin = Math.sin(rotationY);
  return [
    center[0] + local[0] * cos + local[2] * sin,
    center[1] + local[1],
    center[2] - local[0] * sin + local[2] * cos,
  ];
}

export default function StationModule({
  position, angle, row, behavior, reducedMotion, dimFactor, hubPosition,
}: StationModuleProps) {
  const beaconRef = useRef<THREE.Mesh>(null);
  const screenMat = useRef<THREE.MeshBasicMaterial>(null);
  const lightRef = useRef<THREE.PointLight>(null);

  const parked = isParkedState(row.state, row.health);
  const color = healthColor(row.health);
  const rotationY = Math.PI / 2 - angle;
  // Memoized on [position, rotationY] (both stable across polls -- see
  // Scene.tsx's geometry memo) so Agent's own home-position effect only
  // fires on a real geometry change, never on every poll's fresh row data.
  const agentHome = useMemo(() => localToWorld(position, rotationY, [0, 0, -0.15]), [position, rotationY]);
  const moduleDim = (parked ? 0.35 : 1) * dimFactor;

  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (screenMat.current) {
      const flicker = row.health === "red" ? Math.sin(t * 9) * 0.15 : Math.sin(t * 2) * 0.05;
      screenMat.current.opacity = Math.max(0.15, (0.85 + flicker) * moduleDim);
    }
    if (lightRef.current) lightRef.current.intensity = 1.1 * moduleDim;
    if (beaconRef.current && row.health === "red" && !reducedMotion) {
      beaconRef.current.rotation.y = t * 2.2;
    }
  });

  return (
    <group position={position} rotation={[0, rotationY, 0]}>
      {/* Floor slab */}
      <mesh position={[0, -0.05, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[3.2, 2.8]} />
        <meshStandardMaterial color={PALETTE.floor} roughness={0.85} />
      </mesh>

      {/* Screen wall (emissive panel, faces -Z toward hub/agent) */}
      <mesh position={[0, 0.9, 1.15]} rotation={[0, Math.PI, 0]}>
        <planeGeometry args={[2.0, 1.15]} />
        <meshBasicMaterial ref={screenMat} color={color} transparent opacity={0.8} toneMapped={false} />
      </mesh>

      {/* Desk */}
      <mesh position={[0, 0.28, 0.55]}>
        <boxGeometry args={[1.5, 0.5, 0.55]} />
        <meshStandardMaterial color={PALETTE.deskDark} roughness={0.6} />
      </mesh>

      {/* Door beacon -- hub-facing edge */}
      <mesh ref={beaconRef} position={[0, 0.9, -1.35]}>
        <sphereGeometry args={[0.11, 10, 8]} />
        <meshBasicMaterial color={row.health === "red" ? "#ff3b3b" : color} toneMapped={false} />
      </mesh>

      {/* Ambient tint -- short-range, contained to this module */}
      <pointLight ref={lightRef} position={[0, 1.3, 0.2]} color={color} intensity={1.1} distance={4.2} decay={2} />

      {/* Label */}
      <Html position={[0, 1.85, 1.15]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
        <div
          style={{
            fontFamily: "system-ui, sans-serif", fontSize: 13, color: "#dff3ff",
            background: "rgba(3,4,10,0.6)", padding: "4px 10px", borderRadius: 6,
            border: `1px solid ${color}88`, whiteSpace: "nowrap", textAlign: "center",
            opacity: parked ? 0.6 : 1,
          }}
        >
          <div style={{ fontWeight: 700 }}>{row.lane}</div>
          <div style={{ fontSize: 11, color: "#7f93b0" }}>{row.arm_or_acct_alias}</div>
          <div style={{ fontSize: 11 }}>
            <span style={{ color: typeof row.window_pnl === "number" ? (row.window_pnl >= 0 ? "#22ff88" : "#ff3b3b") : "#7f93b0" }}>
              {typeof row.window_pnl === "number" ? row.window_pnl.toFixed(0) : row.window_pnl}
            </span>
            {"  ·  "}
            {row.state}
            {parked && <span style={{ color: "#ffb020", fontWeight: 700 }}> · PARKED</span>}
          </div>
        </div>
      </Html>

      <Agent
        laneSeed={row.lane}
        home={agentHome}
        hub={hubPosition}
        behavior={behavior}
        accentColor={color}
        reducedMotion={reducedMotion}
      />
    </group>
  );
}

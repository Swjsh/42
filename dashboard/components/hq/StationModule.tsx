"use client";

import { useMemo, useRef } from "react";
import type { CSSProperties } from "react";
import { useFrame } from "@react-three/fiber";
import { Html, MeshReflectorMaterial } from "@react-three/drei";
import * as THREE from "three";
import type { SectorRow } from "./types";
import type { AgentBehavior } from "./Agent";
import { healthColor, isParkedState, makeToonGradientTexture, PALETTE } from "./palette";

const _screenColor = new THREE.Color();

interface StationModuleProps {
  position: [number, number, number];
  angle: number;
  row: SectorRow;
  behavior: AgentBehavior;
  reducedMotion: boolean;
  dimFactor: number;
  /** Ultra tier (HQ-ULTRA-TIER-BRIEF.md): floor -> MeshReflectorMaterial
   * (config forked from the repo's own proven dashboard/components/
   * Scene3D.tsx, resolution raised from 256->512 since a 5080 has far more
   * headroom than that scene's original budget), desk -> meshStandardMaterial.
   * TV tier's meshToonMaterial path is completely unchanged. */
  ultra?: boolean;
}

export default function StationModule({
  position, angle, row, behavior, reducedMotion, dimFactor, ultra = false,
}: StationModuleProps) {
  const beaconRef = useRef<THREE.Mesh>(null);
  const screenMat = useRef<THREE.MeshBasicMaterial>(null);
  const edgeMat = useRef<THREE.MeshBasicMaterial>(null);
  const gradientMap = useMemo(() => makeToonGradientTexture(), []);

  const parked = isParkedState(row.state, row.health);
  const color = healthColor(row.health);
  const rotationY = Math.PI / 2 - angle;
  const moduleDim = (parked ? 0.35 : 1) * dimFactor;

  // Health tint is now BAKED INTO brightness (opaque, unlit MeshBasicMaterial
  // colors), not a real light -- Mali-G31 (the real TV's GPU) is
  // fragment-bound and a per-module pointLight was the single biggest
  // lighting cost in the scene. `_screenColor` is a SHARED scratch THREE.Color
  // (module scope, one instance for all 8 StationModules) -- safe because
  // each use sets it and immediately copies it into a material within the
  // same synchronous callback, never held across a frame boundary.
  useFrame((state) => {
    const t = state.clock.elapsedTime;
    const flicker = row.health === "red" ? Math.sin(t * 9) * 0.15 : Math.sin(t * 2) * 0.05;
    const brightness = Math.max(0.15, (0.85 + flicker) * moduleDim);
    if (screenMat.current) screenMat.current.color.copy(_screenColor.set(color)).multiplyScalar(brightness);
    if (edgeMat.current) edgeMat.current.color.copy(_screenColor.set(color)).multiplyScalar(brightness);
    if (beaconRef.current && row.health === "red" && !reducedMotion) {
      beaconRef.current.rotation.y = t * 2.2;
    }
  });

  return (
    <group position={position} rotation={[0, rotationY, 0]}>
      {/* Floor slab. TV tier: toon-shaded (HQ v4 look pass, 2026-09-13) --
          a 3-step gradientMap gives actual depth-band shading instead of
          Lambert's flat N.L tone, same cost class. Ultra tier: a real
          reflector (config forked from Scene3D.tsx's proven settings,
          resolution raised for a 5080's headroom) -- reflects the
          screen/edge-strip emissive glow back up for the "wet floor"
          sci-fi look, receives the scene's real shadow. */}
      <mesh position={[0, -0.05, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow={ultra}>
        <planeGeometry args={[3.2, 2.8]} />
        {ultra ? (
          <MeshReflectorMaterial
            blur={[60, 20]} resolution={512} mixBlur={0.6} mixStrength={1.4} mirror={0.45}
            color={PALETTE.floor} roughness={0.55} metalness={0.55} depthScale={0.4}
          />
        ) : (
          <meshToonMaterial color={PALETTE.floor} gradientMap={gradientMap} />
        )}
      </mesh>

      {/* Emissive floor-edge strip, hub-facing side -- TV tier only
          (2026-09-13, J: "colored floor 'wedges' that read as broken
          geometry" on the ultra-tier screenshot). This thin unlit plane
          sits 5mm above the floor; on the TV's flat toon floor that reads
          as a clean neon trim, but on ultra's MeshReflectorMaterial +
          N8AO it double-reflects and seams against the mirror floor into
          exactly the "wedge" artifact J flagged -- removed there rather
          than fought, since the desk/screen color + reflector tint already
          carry the same health signal without it. TV tier is unchanged. */}
      {!ultra && (
        <mesh position={[0, -0.005, -1.35]} rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[3.0, 0.14]} />
          <meshBasicMaterial ref={edgeMat} color={color} toneMapped={false} />
        </mesh>
      )}

      {/* Screen wall (emissive panel, faces -Z toward hub/agent) -- opaque
          now (was transparent): cuts overdraw/blend cost on the TV's weak
          GPU with no real visual loss for a "screen". Health-tint brightness
          animates via color intensity instead of opacity (see useFrame). */}
      <mesh position={[0, 0.9, 1.15]} rotation={[0, Math.PI, 0]}>
        <planeGeometry args={[2.0, 1.15]} />
        <meshBasicMaterial ref={screenMat} color={color} toneMapped={false} />
      </mesh>

      {/* Desk -- TV tier: toon-shaded, same gradientMap as the floor above.
          Ultra tier: meshStandardMaterial (roughness/metalness), real
          light + PMREM response instead of the toon ramp. */}
      <mesh position={[0, 0.28, 0.55]} castShadow={ultra} receiveShadow={ultra}>
        <boxGeometry args={[1.5, 0.5, 0.55]} />
        {ultra ? (
          <meshStandardMaterial color={PALETTE.deskDark} roughness={0.4} metalness={0.5} />
        ) : (
          <meshToonMaterial color={PALETTE.deskDark} gradientMap={gradientMap} />
        )}
      </mesh>

      {/* Door beacon -- hub-facing edge */}
      <mesh ref={beaconRef} position={[0, 0.9, -1.35]}>
        <sphereGeometry args={[0.11, 10, 8]} />
        <meshBasicMaterial color={row.health === "red" ? "#ff3b3b" : color} toneMapped={false} />
      </mesh>

      {/* Label -- one Html per module (8 total across the scene); the ALERT
          state now folds in here instead of a second floating Html per
          agent, keeping the page's total Html overlay count well under
          budget. 10-foot-readability sizing (2026-09-13): lane name ~30px
          bold, one ~26px status line (P&L colored + state), arm alias
          demoted to a small abbreviation line -- everything else here was
          "just like text ... no animations" at the old 13px on a 4K panel
          viewed across a room. Wrapped in .hq-beam (a Border-Beam-style
          rotating edge glow) and carries a .hq-shine one-shot sweep,
          replayed via `key={row.health}` whenever health changes -- see
          Hud.tsx's shared <style> for both, credited to their 21st.dev
          sources there. */}
      <Html position={[0, 1.95, 1.15]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
        <div className="hq-beam" style={{ "--beam-color": color, borderRadius: 8 } as CSSProperties}>
          <div
            style={{
              position: "relative", overflow: "hidden",
              fontFamily: "system-ui, sans-serif", color: "#dff3ff",
              background: "rgba(3,4,10,0.75)", padding: "6px 16px", borderRadius: 7,
              whiteSpace: "nowrap", textAlign: "center",
              opacity: parked ? 0.6 : 1,
            }}
          >
            <span key={row.health} className="hq-shine" />
            <div style={{ fontSize: 30, fontWeight: 800, lineHeight: 1.15 }}>{row.lane}</div>
            <div style={{ fontSize: 26, color: "#7f93b0", marginBottom: 2 }}>{row.arm_or_acct_alias}</div>
            <div style={{ fontSize: 26, fontWeight: 600 }}>
              <span style={{ color: typeof row.window_pnl === "number" ? (row.window_pnl >= 0 ? "#22ff88" : "#ff3b3b") : "#7f93b0" }}>
                {typeof row.window_pnl === "number" ? row.window_pnl.toFixed(0) : row.window_pnl}
              </span>
              {"  ·  "}
              {row.state}
              {parked && <span style={{ color: "#ffb020", fontWeight: 800 }}> · PARKED</span>}
              {behavior === "alert" && <span style={{ color: "#ff3b3b", fontWeight: 800 }}> · ⚠ ALERT</span>}
            </div>
          </div>
        </div>
      </Html>
    </group>
  );
}

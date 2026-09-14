"use client";

import { useMemo, useRef } from "react";
import type { CSSProperties } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
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
}

export default function StationModule({
  position, angle, row, behavior, reducedMotion, dimFactor,
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
      {/* Floor slab -- toon-shaded (HQ v4 look pass, 2026-09-13): a 3-step
          gradientMap gives the floor actual depth-band shading instead of
          Lambert's single flat N.L tone, same cost class. */}
      <mesh position={[0, -0.05, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[3.2, 2.8]} />
        <meshToonMaterial color={PALETTE.floor} gradientMap={gradientMap} />
      </mesh>

      {/* Emissive floor-edge strip, hub-facing side -- REPLACES the old
          per-module pointLight as the "ambient health tint" signal. Thick
          (not 1-px), opaque, unlit -- reads as a neon floor trim. */}
      <mesh position={[0, -0.005, -1.35]} rotation={[-Math.PI / 2, 0, 0]}>
        <planeGeometry args={[3.0, 0.14]} />
        <meshBasicMaterial ref={edgeMat} color={color} toneMapped={false} />
      </mesh>

      {/* Screen wall (emissive panel, faces -Z toward hub/agent) -- opaque
          now (was transparent): cuts overdraw/blend cost on the TV's weak
          GPU with no real visual loss for a "screen". Health-tint brightness
          animates via color intensity instead of opacity (see useFrame). */}
      <mesh position={[0, 0.9, 1.15]} rotation={[0, Math.PI, 0]}>
        <planeGeometry args={[2.0, 1.15]} />
        <meshBasicMaterial ref={screenMat} color={color} toneMapped={false} />
      </mesh>

      {/* Desk -- toon-shaded, same gradientMap as the floor above */}
      <mesh position={[0, 0.28, 0.55]}>
        <boxGeometry args={[1.5, 0.5, 0.55]} />
        <meshToonMaterial color={PALETTE.deskDark} gradientMap={gradientMap} />
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
            <div style={{ fontSize: 15, color: "#7f93b0", marginBottom: 2 }}>{row.arm_or_acct_alias}</div>
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

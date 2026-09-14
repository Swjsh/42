"use client";

import { Suspense, useMemo, useRef } from "react";
import type { CSSProperties } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import type { SectorRow } from "./types";
import type { AgentBehavior } from "./Agent";
import { healthColor, isParkedState, makeToonGradientTexture, PALETTE, truncateOneLine, type ScreenLine } from "./palette";
import { BAY_CEILING_Y, BAY_DESK_OFFSET_Z, BAY_HALF_DEPTH, DepartmentBayShell, DeskCluster } from "./SetKit";

const _screenColor = new THREE.Color();

interface StationModuleProps {
  position: [number, number, number];
  angle: number;
  row: SectorRow;
  behavior: AgentBehavior;
  reducedMotion: boolean;
  dimFactor: number;
  /** Ultra tier (HQ kit rebuild, 2026-09-13, HQ-SCENE-PLAN.md): the
   * primitive floor/screen-wall/desk geometry is replaced by real CC0 GLB
   * pieces (`DepartmentBayShell`+`DeskCluster`, from SetKit.tsx) -- TV
   * tier's procedural path below is completely unchanged, kept because real
   * indexed GLB meshes would blow the Mali-G31's draw-call budget (this
   * task's own explicit TV-tier rule). */
  ultra?: boolean;
}

export default function StationModule({
  position, angle, row, behavior, reducedMotion, dimFactor, ultra = false,
}: StationModuleProps) {
  const beaconRef = useRef<THREE.Mesh>(null);
  const beaconMat = useRef<THREE.MeshBasicMaterial>(null);
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
    // World-2 item 4 (2026-09-14, J: "the spinning color radar looking
    // things can go... they're just noisy"): the beacon no longer rotates --
    // a static door light that only BLINKS (opacity pulse, ~1Hz) while this
    // lane is genuinely red; steady/fully-opaque otherwise, and steady
    // (never mid-pulse) under reducedMotion too, same "freeze at a
    // representative state" convention every other reducedMotion branch in
    // this file uses.
    if (beaconMat.current) {
      beaconMat.current.opacity =
        row.health === "red" && !reducedMotion ? 0.35 + 0.65 * (0.5 + 0.5 * Math.sin(t * Math.PI * 2)) : 1;
    }
  });

  // Kit rebuild (2026-09-13, HQ-SCENE-PLAN.md) -- ultra tier ONLY, TV tier
  // below is 100% byte-identical to before this pass. Real geometry's
  // hub-facing wall sits at -halfDepth (see SetKit.tsx#DepartmentBayShell);
  // the beacon/label (kept -- see the plan doc's "what stays procedural"
  // section) move from the OLD 2.8-deep floor's -1.35/1.15 offsets to match.
  const bayHalfDepth = BAY_HALF_DEPTH;

  // Bay desk screen (Pass B, 2026-09-13): "each bay screen=lane name+window
  // P&L+health" -- real canvas texture on the DeskCluster's computer-screen
  // mesh, built entirely from `row` (no new data producer). Health line
  // reuses `color` (already computed above from row.health) so the screen
  // and the module's own beacon/label agree on the same hex.
  const pnlText = typeof row.window_pnl === "number" ? `P&L ${row.window_pnl >= 0 ? "+" : ""}${row.window_pnl.toFixed(0)}` : `P&L ${row.window_pnl}`;
  const screenLines: ScreenLine[] = [
    { text: pnlText, color: typeof row.window_pnl === "number" ? (row.window_pnl >= 0 ? "#22ff88" : "#ff3b3b") : "#7f93b0", size: 20 },
    { text: `${row.state} · ${row.health}`, color, size: 16 },
    { text: truncateOneLine(row.evidence, 34), size: 13 },
  ];

  return (
    <group position={position} rotation={[0, rotationY, 0]}>
      {!ultra ? (
        <>
          {/* Floor slab -- TV tier: toon-shaded (HQ v4 look pass,
              2026-09-13), a 3-step gradientMap gives actual depth-band
              shading instead of Lambert's flat N.L tone, same cost class. */}
          <mesh position={[0, -0.05, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[3.2, 2.8]} />
            <meshToonMaterial color={PALETTE.floor} gradientMap={gradientMap} />
          </mesh>

          {/* Emissive floor-edge strip, hub-facing side -- TV tier only
              (2026-09-13, J: "colored floor 'wedges' that read as broken
              geometry" on the ultra-tier screenshot -- removed there, kept
              here since the TV's flat toon floor never produced the
              double-reflection seam that caused it). */}
          <mesh position={[0, -0.005, -1.35]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[3.0, 0.14]} />
            <meshBasicMaterial ref={edgeMat} color={color} toneMapped={false} />
          </mesh>

          {/* Screen wall (emissive panel, faces -Z toward hub/agent) --
              opaque (cuts overdraw/blend cost on the TV's weak GPU).
              Health-tint brightness animates via color intensity (useFrame). */}
          <mesh position={[0, 0.9, 1.15]} rotation={[0, Math.PI, 0]}>
            <planeGeometry args={[2.0, 1.15]} />
            <meshBasicMaterial ref={screenMat} color={color} toneMapped={false} />
          </mesh>

          {/* Desk -- toon-shaded, same gradientMap as the floor above. */}
          <mesh position={[0, 0.28, 0.55]}>
            <boxGeometry args={[1.5, 0.5, 0.55]} />
            <meshToonMaterial color={PALETTE.deskDark} gradientMap={gradientMap} />
          </mesh>
        </>
      ) : (
        <>
          {/* Real CC0 kit geometry replaces the floor/screen-wall/desk
              primitives above -- see HQ-SCENE-PLAN.md. Suspense-scoped
              (world pass A bug fix, see BrainCore.tsx's identical fix) so a
              still-loading bay never unmounts anything outside itself. */}
          <Suspense fallback={null}>
            <DepartmentBayShell />
            <group position={[0, 0, BAY_DESK_OFFSET_Z]}>
              <DeskCluster accentColor={color} screenTitle={row.lane} screenLines={screenLines} />
            </group>
          </Suspense>

          {/* World pass A (2026-09-13): "each bay interior tinted by its
              health color from an emissive floor strip + a small colored
              point light" -- RE-ADDED for ultra (was TV-only; the double-
              reflection "wedge" that got it pulled from ultra was a
              MeshReflectorMaterial-floor artifact, and ultra's floor is now
              real kit geometry, not a reflector, so that artifact no longer
              applies). Strip sits just inside the real room's hub-facing
              wall; the point light is a SMALL, falloff-limited warm-tinted
              health accent, not the room's main light (see HubRoom/bay
              ceiling pointLights below for that). */}
          <mesh position={[0, 0.01, -bayHalfDepth + 0.3]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[3.6, 0.2]} />
            <meshBasicMaterial ref={edgeMat} color={color} toneMapped={false} />
          </mesh>
          <pointLight
            position={[0, 1.1, BAY_DESK_OFFSET_Z * 0.4]}
            color={color}
            intensity={2.2}
            distance={4.5}
            decay={2}
          />
          {/* Warm-white ceiling pointLight -- "lit like a set", one per bay
              (~8 total, well within a 5080's budget). Distance-limited so
              8 bays' lights never bleed heavily into each other or the hub. */}
          <pointLight position={[0, BAY_CEILING_Y, BAY_DESK_OFFSET_Z * 0.5]} color="#ffe9c2" intensity={3.5} distance={6} decay={2} />
        </>
      )}

      {/* Door beacon -- hub-facing edge; the doorway itself (position
          matches DepartmentBayShell's gate-door on the ultra tier). World-2
          item 4: static (no rotation) -- see the useFrame above for the
          blink-when-red opacity mechanism. */}
      <mesh ref={beaconRef} position={[0, 0.9, ultra ? -bayHalfDepth + 0.08 : -1.35]}>
        <sphereGeometry args={[0.11, 10, 8]} />
        <meshBasicMaterial ref={beaconMat} color={row.health === "red" ? "#ff3b3b" : color} transparent toneMapped={false} />
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
          sources there. Ultra tier: repositioned above the doorway (like a
          department sign over the entrance) instead of the TV's over-the-
          screen spot -- the kit bay is bigger and deeper than the old 2.8u
          floor plane, and the desk/screen cluster now occupies that space. */}
      <Html
        position={ultra ? [0, 2.3, -bayHalfDepth + 0.4] : [0, 1.95, 1.15]}
        center
        distanceFactor={9}
        style={{ pointerEvents: "none" }}
      >
        {/* Pass G (2026-09-13, coordinator item 5: "parked lanes quiet --
            currently carry the biggest labels in the frame; parked = dim,
            small, grey; active/armed lanes keep the weight"): a parked
            label previously only dropped to 0.6 opacity at the SAME big
            font size + the same rotating .hq-beam border + the same
            one-shot .hq-shine sweep on health change -- all three read as
            "look at me," the opposite of quiet. Parked now skips the beam/
            shine entirely (a plain, static, small box) and drops font size
            ~45% + opacity to 0.45 + text color to a flat grey, matching
            "small and grey" literally rather than just dimmer at full
            size. Active/armed lanes are BYTE-IDENTICAL to before this
            edit -- only the parked branch changed. */}
        {parked ? (
          <div
            style={{
              fontFamily: "system-ui, sans-serif", color: "#5c7aa0",
              background: "rgba(3,4,10,0.6)", padding: "4px 10px", borderRadius: 6,
              whiteSpace: "nowrap", textAlign: "center", opacity: 0.45,
            }}
          >
            <div style={{ fontSize: ultra ? 20 : 17, fontWeight: 600, lineHeight: 1.15 }}>{row.lane}</div>
            <div style={{ fontSize: ultra ? 16 : 14 }}>{row.state} · PARKED</div>
          </div>
        ) : (
        <div className="hq-beam" style={{ "--beam-color": color, borderRadius: 8 } as CSSProperties}>
          <div
            style={{
              position: "relative", overflow: "hidden",
              fontFamily: "system-ui, sans-serif", color: "#dff3ff",
              background: "rgba(3,4,10,0.75)", padding: "6px 16px", borderRadius: 7,
              whiteSpace: "nowrap", textAlign: "center",
            }}
          >
            <span key={row.health} className="hq-shine" />
            <div style={{ fontSize: ultra ? 38 : 30, fontWeight: 800, lineHeight: 1.15 }}>{row.lane}</div>
            {/* Ultra tier (world pass A, 2026-09-13): "one line lane name +
                one status line" -- the arm-alias abbreviation line is
                dropped here (kept on TV, unchanged) to hit that 2-line
                spec at a bigger, readable size instead of 3 shrinking lines. */}
            {!ultra && <div style={{ fontSize: 26, color: "#7f93b0", marginBottom: 2 }}>{row.arm_or_acct_alias}</div>}
            <div style={{ fontSize: ultra ? 32 : 26, fontWeight: 600 }}>
              <span style={{ color: typeof row.window_pnl === "number" ? (row.window_pnl >= 0 ? "#22ff88" : "#ff3b3b") : "#7f93b0" }}>
                {typeof row.window_pnl === "number" ? row.window_pnl.toFixed(0) : row.window_pnl}
              </span>
              {"  ·  "}
              {row.state}
              {behavior === "alert" && <span style={{ color: "#ff3b3b", fontWeight: 800 }}> · ⚠ ALERT</span>}
            </div>
          </div>
        </div>
        )}
      </Html>
    </group>
  );
}

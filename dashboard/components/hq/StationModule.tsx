"use client";

import { Suspense, useMemo, useRef } from "react";
import type { CSSProperties } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import type { SectorRow } from "./types";
import type { AgentBehavior } from "./Agent";
import { healthColor, isParkedState, lerp, makeToonGradientTexture, PALETTE, truncateOneLine, type ScreenLine } from "./palette";
import { BAY_CEILING_Y, BAY_DESK_OFFSET_Z, BAY_HALF_DEPTH, DepartmentBayShell, DeskCluster } from "./SetKit";
import BaySign from "./BaySign";
import BayInterior from "./BayInterior";

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
  /** World-2 coordinator review (2026-09-14, DAYTIME BLOWOUT): 0 (night)..1
   * (day), the SAME dayNightFactor() value every other day/night mechanism
   * in this tree already uses -- fades this bay's own interior pointLights
   * toward ~15% by day (SetKit.tsx's own `interiorLampFactor`, HubRoom uses
   * the identical curve), same "interior lamps off in daylight" reasoning.
   * Defaults to 1 (day, dimmer) -- a missing prop should never read as a
   * lamp left blazing at full night brightness. */
  dayFactor?: number;
}

export default function StationModule({
  // World-2 coordinator review (LABEL DIET): `behavior` is now unused --
  // the label's own "⚠ ALERT" text is gone (the door beacon's blink is the
  // alert signal now), and nothing else in this component ever read it.
  // Renamed with the SAME underscore convention CanvasRoot.tsx/BrainCore.tsx
  // already use for their own unused props, kept in the signature only
  // because Scene.tsx's call site still passes it.
  position, angle, row, behavior: _behavior, reducedMotion, dimFactor, ultra = false, dayFactor = 1,
}: StationModuleProps) {
  const lampFactor = lerp(1, 0.15, dayFactor);
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
  // World-4 fix (P2, 2026-09-14): the in-world sign's anchor -- the SAME
  // spot "above the doorway" the old always-visible Html label already used
  // (see that block's own comment below). Memoized on the SAME
  // referentially-stable `bayHalfDepth` Scene.tsx's own geometry memo
  // already guarantees stays stable across polls (see Scene.tsx's own
  // comment on why that stability matters).
  // POLISH-1 P2 fix (2026-09-14): the WORLD-space twin this used to also
  // compute (`signWorldPos`) fed ONLY BaySign's own close-up Html detail
  // label's distance-fade check -- removed there (see BaySign.tsx's own P2
  // header: that label duplicated the wall sign's own text AND the head
  // bubble's, "three copies of the same name" in a real capture tonight),
  // so `localToWorld`/`rotationY`/`position` are no longer needed here for
  // this purpose.
  const signLocalPos = useMemo<[number, number, number]>(() => [0, 2.3, -bayHalfDepth + 0.4], [bayHalfDepth]);

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
            <DepartmentBayShell position={position} rotationY={rotationY} />
            <group position={[0, 0, BAY_DESK_OFFSET_Z]}>
              <DeskCluster position={position} rotationY={rotationY} accentColor={color} screenTitle={row.lane} screenLines={screenLines} />
            </group>
            {/* S3 bay-interiors pass (2026-09-14, MODELS builder): 2nd
                chair+screen, container corner, interior lane sign, floor mat
                -- see BayInterior.tsx's own header for the draw-call budget
                and why the sign is a plane pair, not a GLB. Same Suspense
                boundary as the shell/desk above (own useGLTF calls, same
                world-pass-A "never let a still-loading piece unmount a
                sibling" reasoning). */}
            <BayInterior accentColor={color} laneName={row.lane} row={row} />
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
          {/* World-2 coordinator review (2026-09-14, DAYTIME BLOWOUT): both
              bay pointLights fade toward ~15% by day (`lampFactor`, same
              curve as SetKit.tsx#HubRoom's identical fix) -- the health-
              accent light keeps signaling health color at night when it
              actually needs to stand out; by day the door beacon/floor-edge
              strip (unfaded, both already health-tinted) carry that same
              signal against plenty of ambient light instead. */}
          <pointLight
            position={[0, 1.1, BAY_DESK_OFFSET_Z * 0.4]}
            color={color}
            intensity={2.2 * lampFactor}
            distance={4.5}
            decay={2}
          />
          {/* Warm-white ceiling pointLight -- "lit like a set", one per bay
              (~8 total, well within a 5080's budget). Distance-limited so
              8 bays' lights never bleed heavily into each other or the hub. */}
          <pointLight position={[0, BAY_CEILING_Y, BAY_DESK_OFFSET_Z * 0.5]} color="#ffe9c2" intensity={3.5 * lampFactor} distance={6} decay={2} />
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

      {/* World-4 fix (P2, 2026-09-14): ultra tier gets a REAL in-world sign
          (BaySign.tsx -- a canvas-textured mesh flush on the bay's own
          hub-facing wall, health color on its edge, foreshortens with real
          perspective like the rest of the kit) instead of the always-on
          screen-space Html plaque that used to "hover mid-air" regardless
          of distance. TV tier is BYTE-IDENTICAL to before this pass (see
          its own Html block just below) -- draw-call budget doesn't have
          room for 2 more meshes per bay there (P5's own ~130-call soft
          ceiling). */}
      {ultra && (
        <BaySign
          position={signLocalPos}
          laneName={row.lane}
          stateWord={row.state}
          color={color}
          dimFactor={dimFactor}
        />
      )}

      {/* Label -- TV tier only past this pass (see BaySign.tsx for ultra's
          own replacement) -- one Html per module; the ALERT state folds in
          here instead of a second floating Html per agent, keeping the
          page's total Html overlay count well under budget.
          10-foot-readability sizing (2026-09-13): lane name ~30px bold, one
          ~26px status line (P&L colored + state), arm alias demoted to a
          small abbreviation line -- everything else here was "just like
          text ... no animations" at the old 13px on a 4K panel viewed
          across a room. Wrapped in .hq-beam (a Border-Beam-style rotating
          edge glow) and carries a .hq-shine one-shot sweep, replayed via
          `key={row.health}` whenever health changes -- see Hud.tsx's shared
          <style> for both, credited to their 21st.dev sources there. */}
      {!ultra && (
      <Html
        position={[0, 1.95, 1.15]}
        center
        distanceFactor={9}
        style={{ pointerEvents: "none" }}
      >
        {/* World-2 coordinator review (2026-09-14, LABEL DIET: "the frame
            carries ~20 floating labels... J called it chaotic"): parked =
            name only at 60% opacity (was name + "{state} · PARKED" at
            0.45); live = name + state on ONE line (was a 2-3 line stack
            with P&L, arm alias, and an "ALERT" suffix). The dropped detail
            (P&L, arm alias, full evidence text) still lives on the bay's
            own desk screen (`screenLines` above, DeskCluster/DeskScreen) --
            this floating overhead label is the glanceable-overview surface,
            the desk screen is the approach-for-detail one. The door
            beacon's own blink (see the useFrame above) is now the alert
            signal -- no separate "⚠ ALERT" text needed here too. */}
        {parked ? (
          <div
            style={{
              fontFamily: "system-ui, sans-serif", color: "#5c7aa0",
              background: "rgba(3,4,10,0.6)", padding: "4px 10px", borderRadius: 6,
              whiteSpace: "nowrap", textAlign: "center", opacity: 0.6,
            }}
          >
            <div style={{ fontSize: 17, fontWeight: 600, lineHeight: 1.15 }}>{row.lane}</div>
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
            <div style={{ fontSize: 26, fontWeight: 800, lineHeight: 1.15 }}>
              {row.lane}
              <span style={{ fontWeight: 600, color: "#7f93b0" }}> · {row.state}</span>
            </div>
          </div>
        </div>
        )}
      </Html>
      )}
    </group>
  );
}

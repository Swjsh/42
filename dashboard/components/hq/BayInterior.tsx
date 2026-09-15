"use client";

import { useEffect, useId, useMemo } from "react";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import type { SectorRow } from "./types";
import { KIT_PATHS, KitProp, FURNITURE_SCALE, BAY_DESK_OFFSET_Z, BAY_HALF_DEPTH, BAY_SEAT_LOCAL, usePooledKitProps } from "./SetKit";
import { localToWorld } from "./palette";

// W2 (2026-09-14, WORLD-6 builder): plant-small.glb (Kenney Furniture Kit,
// public/hq-assets/kenney-furniture-kit/) was downloaded for "interior
// plants" and originally placed one-per-bay here, but REMOVED after a
// coordinator draw-call-budget flag (2026-09-14 ~19:2x ET, real capture
// hq-20260914-1725.png: 1093/1100 calls): the raw GLB has 2 primitives
// (glb_extents.mjs's own JSON-chunk inspection this session), and 8 bays x
// 2 = 16 draw calls for a plant small enough to be barely visible at any
// camera preset was the worst value-per-draw-call item in this pass -- cut
// first. The file stays on disk (manifest.json/LICENSES.md still record
// it) in case a future pass wants ONE cheap accent placement instead of
// eight; see HubInterior.tsx's own potted-plant.glb placement for the
// budget-kept "interior plants" delivery instead.

// ─── S3 bay interiors pass (2026-09-14, MODELS builder) ────────────────────
// "each lane bay gets a believable workstation": a second chair + second
// screen (a real P&L bar-gauge, not a line-text repeat of the desk's own
// screen), a container corner, an interior wall sign naming the lane
// (BaySign.tsx itself stays the OUTSIDE sign, untouched), and a floor mat.
// Ultra tier only (mounted from StationModule.tsx inside its own existing
// `{ultra && ...}` Suspense block -- one additive import + one additive JSX
// line there; StationModule.tsx confirmed NOT concurrently modified by the
// LAYOUT builder before that edit landed -- git status clean, mtime hours
// stale, see this pass's own commit note).
//
// The interior sign is a canvas-textured plane pair (backing + face), the
// SAME proven technique BaySign.tsx already uses for the exterior sign --
// deliberately NOT a GLB (e.g. structure-panel.glb, downloaded but unused
// elsewhere): that piece's own raw shape (a flat 0.85x0.125x0.85 tile, i.e.
// a floor/ceiling panel) and this project's own established "which face is
// front" ambiguity (see SmartBoard.tsx's own FRONT_Z comment) make its wall
// orientation a real guess this component has no capture cycle budgeted to
// verify; a plane's orientation is unambiguous by construction.
//
// One ceiling light per bay already exists (DepartmentBayShell, SetKit.tsx)
// -- not duplicated here, matches the brief's own "one ceiling light" (not
// "one more").
//
// Draw-call budget: 2nd chair(1) + 2nd screen body+face(2) + container(1) +
// wall sign backing+face(2) + floor mat+ring(2) = 8 meshes/bay x 8 bays =
// 64, comfortably under the ~120-extra-draw-call budget for all 8 bays.

const DESK_TOP_HEIGHT = 0.4 * FURNITURE_SCALE; // table.glb raw height 0.4 -- same formula as SetKit.tsx's own (unexported) constant

function createGaugeCanvas(width: number, height: number): { canvas: HTMLCanvasElement; texture: THREE.CanvasTexture } {
  if (typeof document === "undefined") {
    throw new Error("createGaugeCanvas() called outside a browser -- never call this during SSR");
  }
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return { canvas, texture };
}

/** Draws a small horizontal P&L bar gauge -- real current-value data (the
 * SAME `row.window_pnl` StationModule.tsx's own desk-screen text already
 * shows), never a fabricated time series. The brief's "static lane chart
 * texture... if cheap" -- no time-series field exists on SectorRow (verified
 * by reading lib/hq.ts this session), so a bar gauge of the one real scalar
 * this data actually has is the honest cheap chart, not invented history. */
function drawPnlGauge(canvas: HTMLCanvasElement, texture: THREE.CanvasTexture, windowPnl: number | "n/a", health: string): void {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const w = canvas.width;
  const h = canvas.height;
  ctx.fillStyle = "#040a12";
  ctx.fillRect(0, 0, w, h);

  ctx.fillStyle = "#5f7a99";
  ctx.font = "bold 13px system-ui, sans-serif";
  ctx.textBaseline = "top";
  ctx.fillText("LANE P&L", 8, 8);

  const midY = 52;
  const barHalfW = w / 2 - 12;
  ctx.strokeStyle = "rgba(122,217,255,0.25)";
  ctx.beginPath();
  ctx.moveTo(w / 2, midY - 14);
  ctx.lineTo(w / 2, midY + 14);
  ctx.stroke();

  if (typeof windowPnl === "number") {
    const scale = 200; // world units per full-bar-width -- a fixed, documented reference, not tuned to any one lane
    const frac = Math.max(-1, Math.min(1, windowPnl / scale));
    const barW = Math.abs(frac) * barHalfW;
    const positive = windowPnl >= 0;
    ctx.fillStyle = positive ? "#22ff88" : "#ff3b3b";
    ctx.fillRect(positive ? w / 2 : w / 2 - barW, midY - 9, barW, 18);

    ctx.fillStyle = positive ? "#22ff88" : "#ff3b3b";
    ctx.font = "bold 20px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText(`${positive ? "+" : ""}${windowPnl.toFixed(0)}`, w / 2, midY + 20);
    ctx.textAlign = "left";
  } else {
    ctx.fillStyle = "#7f93b0";
    ctx.font = "16px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.fillText("n/a", w / 2, midY - 2);
    ctx.textAlign = "left";
  }

  ctx.fillStyle = "#2f3f56";
  ctx.font = "11px system-ui, sans-serif";
  ctx.fillText(health.toUpperCase(), 8, h - 18);
  texture.needsUpdate = true;
}

interface BayInteriorProps {
  accentColor: string;
  laneName: string;
  row: SectorRow;
  /** PERF-3 (2026-09-15): this component's own placements were previously
   * pure-local JSX, correct because StationModule.tsx mounts it inside its
   * own `<group position={position} rotation={[0, rotationY, 0]}>` (see
   * that file's own render). The pooled chair below can't rely on that
   * parent transform (InstancedKitPool renders from a single mount point
   * with no per-caller group ancestor -- same reasoning DeskCluster's own
   * pooled table/chair already documents), so this bay's own
   * position/rotationY are threaded through explicitly to fold into the
   * pool's world-space matrix via localToWorld -- the identical pattern
   * DeskCluster uses for its table/chair. */
  position: [number, number, number];
  rotationY: number;
}

export default function BayInterior({ accentColor, laneName, row, position, rotationY }: BayInteriorProps) {
  // Second screen -- computer-screen.glb again (drei caches by path, so
  // this is zero extra parse cost beyond DeskCluster's own instance),
  // retextured with the P&L gauge instead of the desk screen's line text.
  const { scene: screenScene } = useGLTF(KIT_PATHS.furniture.computerScreen, false);
  const screenClone = useMemo(() => screenScene.clone(true), [screenScene]);
  const { canvas: gaugeCanvas, texture: gaugeTexture } = useMemo(() => createGaugeCanvas(160, 112), []);
  const gaugeMat = useMemo(() => new THREE.MeshBasicMaterial({ map: gaugeTexture, toneMapped: false }), [gaugeTexture]);

  useEffect(() => {
    screenClone.traverse((obj) => {
      if (obj instanceof THREE.Mesh) obj.material = gaugeMat;
    });
  }, [screenClone, gaugeMat]);

  const contentKey = `${row.window_pnl}|${row.health}`;
  useEffect(() => {
    drawPnlGauge(gaugeCanvas, gaugeTexture, row.window_pnl, row.health);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gaugeCanvas, gaugeTexture, contentKey]);

  useEffect(() => () => {
    gaugeTexture.dispose();
    gaugeMat.dispose();
  }, [gaugeTexture, gaugeMat]);

  // Interior lane-name sign's own canvas -- separate from the gauge above.
  const { canvas: signCanvas, texture: signTexture } = useMemo(() => createGaugeCanvas(220, 96), []);
  useEffect(() => {
    const ctx = signCanvas.getContext("2d");
    if (!ctx) return;
    ctx.fillStyle = "#040a12";
    ctx.fillRect(0, 0, signCanvas.width, signCanvas.height);
    ctx.fillStyle = accentColor;
    ctx.fillRect(0, 0, signCanvas.width, 4);
    ctx.fillStyle = "#dff3ff";
    ctx.font = "bold 24px system-ui, sans-serif";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    const short = laneName.includes(" (") ? laneName.slice(0, laneName.indexOf(" (")) : laneName;
    ctx.fillText(short.length > 14 ? `${short.slice(0, 13)}…` : short, signCanvas.width / 2, signCanvas.height / 2 + 2);
    signTexture.needsUpdate = true;
  }, [signCanvas, signTexture, laneName, accentColor]);
  useEffect(() => () => signTexture.dispose(), [signTexture]);

  // Second chair -- beside the existing one (BAY_SEAT_LOCAL), same facing.
  // PERF-3 (2026-09-15): routed through the existing cross-tree chair pool
  // (SetKit.tsx#usePooledKitProps, "native" variant -- same pool key
  // DeskCluster's own chair already registers into, rendered by HubRoom's
  // single <InstancedKitPool> mount) instead of a bare KitProp -- this was
  // an un-instanced draw call per bay (x8) on top of DeskCluster's own
  // already-pooled chair (evidence: "chair_1 x14" == 8 bay second-chairs +
  // 6 HubInterior.tsx hub chairs, the other un-pooled chair source).
  const seatId = useId();
  const secondSeat: [number, number, number] = [BAY_SEAT_LOCAL[0] + 0.9, BAY_SEAT_LOCAL[1], BAY_SEAT_LOCAL[2]];
  const chairPlacements = useMemo(
    () => [{
      id: `bay-2nd-chair-${seatId}`,
      position: localToWorld(position, rotationY, secondSeat),
      rotation: [0, rotationY + Math.PI, 0] as [number, number, number],
      scale: FURNITURE_SCALE,
    }],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [seatId, position, rotationY, secondSeat[0], secondSeat[1], secondSeat[2]],
  );
  usePooledKitProps(KIT_PATHS.furniture.chair, "native", chairPlacements);
  // Second screen -- a smaller secondary monitor at the desk's far edge.
  // table.glb is only 2.2 world units wide (FURNITURE_SCALE 2.0 x raw 1.1);
  // the desk's OWN screen already spans X [-0.8,0.8] at its native scale
  // (raw 0.8 x FURNITURE_SCALE 2.0) -- a second full-size screen beside it
  // would overlap by ~0.65 units (checked against the GLB's own parsed
  // bounds, not eyeballed). SECOND_SCREEN_SCALE keeps this one small enough
  // (0.44 wide) to clear that edge with a small, believable overhang past
  // the table's own X=1.1 edge -- a crowded-desk detail, not a bug.
  const SECOND_SCREEN_SCALE = 0.55;
  // Y = DESK_TOP_HEIGHT unchanged regardless of SECOND_SCREEN_SCALE -- the
  // GLB's own local origin sits at ITS bottom (raw Y min 0, same convention
  // as every other kit piece), so this places its base on the table surface
  // whatever its own scale is; only the model's own proportions shrink.
  const secondScreenPos: [number, number, number] = [1.15, DESK_TOP_HEIGHT, BAY_DESK_OFFSET_Z + 0.55 * FURNITURE_SCALE];
  // Container corner -- back-left of the room, clear of the door (-Z) and
  // the desk cluster; room half-extent is BAY_HALF_DEPTH (2.7), 1.9 offset
  // leaves margin on both axes.
  const containerPos: [number, number, number] = [-1.9, 0, BAY_HALF_DEPTH * 0.55];
  // Interior wall sign -- side wall (local +X, flush against it, facing
  // -X back into the room), naming the lane; BaySign.tsx itself keeps the
  // hub-facing (-Z) exterior sign unchanged.
  const wallSignPos: [number, number, number] = [BAY_HALF_DEPTH - 0.05, 1.7, BAY_DESK_OFFSET_Z * 0.6];

  return (
    <>
      <primitive object={screenClone} position={secondScreenPos} rotation={[0, Math.PI, 0]} scale={SECOND_SCREEN_SCALE} />

      <KitProp
        path={KIT_PATHS.baseProps.container}
        scale={1.7}
        position={containerPos}
        rotation={[0, 0.6, 0]}
        castShadow
        receiveShadow
        tint={accentColor}
        tintStrength={0.08}
      />

      {/* Interior lane sign -- backing (health-colored edge) + canvas face,
          BaySign.tsx's own "edge-lit, not filled" convention, flush on the
          side wall facing back into the room (-X). */}
      <mesh position={wallSignPos} rotation={[0, -Math.PI / 2, 0]}>
        <planeGeometry args={[0.82, 0.36]} />
        <meshBasicMaterial color={accentColor} toneMapped={false} />
      </mesh>
      <mesh position={[wallSignPos[0] - 0.006, wallSignPos[1], wallSignPos[2]]} rotation={[0, -Math.PI / 2, 0]}>
        <planeGeometry args={[0.75, 0.3]} />
        <meshBasicMaterial map={signTexture} toneMapped={false} />
      </mesh>

      {/* Floor mat -- under the desk/chair footprint, a subtle accent-tinted
          rectangle + ring just above the real floor. */}
      <mesh position={[0, 0.006, BAY_DESK_OFFSET_Z]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[2.6, 2.2]} />
        <meshBasicMaterial color={accentColor} transparent opacity={0.1} toneMapped={false} />
      </mesh>
      <mesh position={[0, 0.007, BAY_DESK_OFFSET_Z]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[1.32, 1.36, 32]} />
        <meshBasicMaterial color={accentColor} transparent opacity={0.25} toneMapped={false} />
      </mesh>
    </>
  );
}

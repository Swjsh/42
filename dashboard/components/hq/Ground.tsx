"use client";

import { useMemo } from "react";
import * as THREE from "three";
import { PALETTE } from "./palette";

// ─── World-2 item 2 (2026-09-14, J: "when I scroll out, a black circle just
// appears and takes over everything... there needs to be some sort of floor
// or background or something to this, because right now it's just infinite
// directions") ────────────────────────────────────────────────────────────
// A large ground disc so the station reads as sitting ON something instead
// of floating in a starfield with nothing below it. Radius matches
// SkyDome.tsx's own dome radius (70) -- big enough that the visible edge
// (if the camera could ever see it, which it can't past Scene.tsx's own
// fog far=62) reads as "the horizon", not a literal disc edge.

const RADIUS = 70;
const SEGMENTS = 64;
// One CanvasTexture tile repeated across the whole disc -- ~4.4 world units
// per tile at this repeat count, a plausible "plaza paving" scale next to
// the station's own ~14-unit ring radius.
const TILE_REPEAT = 32;

let _groundTexture: THREE.CanvasTexture | null = null;

/** Procedural tile/grid texture -- runtime CanvasTexture, zero bundled
 * assets, same "cached module-level singleton, built once, never per-frame"
 * convention as palette.ts#makeMatcapTexture/makeToonGradientTexture (see
 * that file's own top-of-file comment for why this pattern lives outside
 * palette.ts here instead: this one is Ground-specific and RepeatWrapping/
 * tiled, unlike the shared matcap/gradient helpers other components also
 * consume). A dark regolith base with faint grid seams -- subtle by design
 * (a strong grid would read as a sci-fi holodeck floor, not a dim exterior
 * plaza/regolith surface at night). */
function makeGroundTexture(): THREE.CanvasTexture {
  if (typeof document === "undefined") {
    throw new Error("makeGroundTexture() called outside a browser -- never call this during SSR");
  }
  if (_groundTexture) return _groundTexture;
  const size = 128;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("makeGroundTexture(): 2D canvas context unavailable");

  // Base fill, plain white so `color`/`map` multiply cleanly -- the material
  // instance owns the actual night/day tint (see Ground() below), this
  // texture only ever contributes the tile-seam DETAIL.
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, size, size);

  // Faint seam lines around the tile edge, deterministic (fixed geometry,
  // not Math.random -- this runs once at texture-build time, not per frame,
  // but stays deterministic anyway so reloads never reshuffle the look).
  ctx.strokeStyle = "rgba(0,0,0,0.35)";
  ctx.lineWidth = 3;
  ctx.strokeRect(1.5, 1.5, size - 3, size - 3);
  // A soft darker vignette toward the tile edges so seams read as a subtle
  // panel gap rather than a hard bright line under strong exposure.
  const vignette = ctx.createRadialGradient(size / 2, size / 2, size * 0.2, size / 2, size / 2, size * 0.5);
  vignette.addColorStop(0, "rgba(0,0,0,0)");
  vignette.addColorStop(1, "rgba(0,0,0,0.18)");
  ctx.fillStyle = vignette;
  ctx.fillRect(0, 0, size, size);

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(TILE_REPEAT, TILE_REPEAT);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  _groundTexture = texture;
  return texture;
}

interface GroundProps {
  /** Same 0 (night) .. 1 (day) factor SkyDome.tsx/Scene.tsx's hemisphere
   * light already use (dayNightFactor()'s return value) -- blends this
   * disc's own base tone the identical way SkyDome blends its zenith/depth
   * stops, so the horizon (where dome meets ground) never seams: both read
   * the same time of day. */
  dayFactor?: number;
  /** Ultra tier only: real shadows fall on this disc (StationModule/HubRoom
   * castShadow meshes). TV tier's Canvas has shadows={false} scene-wide, so
   * this prop is harmless there either way -- gated anyway to match every
   * other `receiveShadow`/`castShadow` prop in this tree's own convention. */
  ultra?: boolean;
}

/** Ground tone stops -- night reuses the SAME dark floor tone
 * StationModule.tsx's TV-tier floor slab already uses (PALETTE.floor), so a
 * TV-tier bay's own floor and the ground around it agree without a visible
 * seam; `groundDay` is a new additive palette token (see palette.ts) for the
 * lit-plaza tone at midday. */
const GROUND_NIGHT = new THREE.Color(PALETTE.floor);
const GROUND_DAY = new THREE.Color(PALETTE.groundDay);
const _groundColor = new THREE.Color();

export default function Ground({ dayFactor = 1, ultra = false }: GroundProps) {
  const texture = useMemo(() => makeGroundTexture(), []);
  // Re-blended only when dayFactor genuinely changes (same cadence as
  // SkyDome's own useMemo-on-dayFactor rebake -- Scene.tsx's ET clock only
  // moves gradually, no per-frame cost here).
  const color = useMemo(() => _groundColor.copy(GROUND_NIGHT).lerp(GROUND_DAY, dayFactor).clone(), [dayFactor]);

  return (
    <mesh position={[0, -0.06, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow={ultra}>
      <circleGeometry args={[RADIUS, SEGMENTS]} />
      <meshStandardMaterial map={texture} color={color} roughness={1} metalness={0} />
    </mesh>
  );
}

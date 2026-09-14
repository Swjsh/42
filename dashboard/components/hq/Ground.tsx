"use client";

import { useMemo } from "react";
import * as THREE from "three";
import { PALETTE, seededRandom } from "./palette";
import { KIT_PATHS, KitProp } from "./SetKit";

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
// World-3 environment pass (2026-09-14, J: "grey abyss... regolith ground"):
// 32 -> 8. The OLD crisp black grid-line tile (below) read as an obvious
// repeating pattern at almost any repeat count -- a hard straight line is
// recognizable even tiled sparsely. This new texture is a SOFT mottled
// blotch pattern instead (no straight edges anywhere in the source tile), so
// a much lower repeat count both keeps more texel detail near the station
// AND is far less noticeable as "the same tile again" than the old grid ever
// was, even before accounting for the softness itself.
const TILE_REPEAT = 8;

let _groundTexture: THREE.CanvasTexture | null = null;

/** Procedural regolith texture -- runtime CanvasTexture, zero bundled
 * assets, same "cached module-level singleton, built once, never per-frame"
 * convention as palette.ts#makeMatcapTexture/makeToonGradientTexture (see
 * that file's own top-of-file comment for why this pattern lives outside
 * palette.ts here instead: this one is Ground-specific and RepeatWrapping/
 * tiled, unlike the shared matcap/gradient helpers other components also
 * consume). Replaces the OLD crisp grid-tile look (World-2, 2026-09-14 AM)
 * with mottled dust/grain blotches -- one of the 3 "grey abyss" root causes
 * (ENVIRONMENT-PLAN.md): a crisp repeating grid under a flat pale fog read
 * as an obviously artificial, featureless plain, not a natural surface. */
function makeGroundTexture(): THREE.CanvasTexture {
  if (typeof document === "undefined") {
    throw new Error("makeGroundTexture() called outside a browser -- never call this during SSR");
  }
  if (_groundTexture) return _groundTexture;
  const size = 256;
  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("makeGroundTexture(): 2D canvas context unavailable");

  // Base fill, plain white so `color`/`map` multiply cleanly -- the material
  // instance owns the actual night/day tint (see Ground() below), this
  // texture only ever contributes mottled GRAIN detail.
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, size, size);

  // Deterministic LCG (fixed seed, never Math.random -- this file's own
  // standing convention, matches Planet.tsx's identical approach) driving
  // ~220 soft dark/light blotches of varying size -- a mottled dust look
  // with no straight edge anywhere, unlike the old grid this replaces.
  let seed = 918273;
  const rand = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  ctx.globalCompositeOperation = "multiply";
  for (let i = 0; i < 160; i++) {
    const cx = rand() * size;
    const cy = rand() * size;
    const r = 4 + rand() * 14;
    const shade = 0.72 + rand() * 0.24; // dark blotches only, stays multiply-safe
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    grad.addColorStop(0, `rgba(0,0,0,${1 - shade})`);
    grad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalCompositeOperation = "screen";
  for (let i = 0; i < 60; i++) {
    const cx = rand() * size;
    const cy = rand() * size;
    const r = 2 + rand() * 6;
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    grad.addColorStop(0, "rgba(255,255,255,0.10)");
    grad.addColorStop(1, "rgba(255,255,255,0)");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalCompositeOperation = "source-over";

  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(TILE_REPEAT, TILE_REPEAT);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  _groundTexture = texture;
  return texture;
}

// ─── Craters (E2) ───────────────────────────────────────────────────────────
// 8 fixed, deterministic craters outside the plaza -- real kit GLBs
// (kenney-space-kit/crater.glb + craterLarge.glb), individually placed
// (KitProp, matching every other small-count prop-placement convention in
// this tree -- see SetKit.tsx#HubRoom's 4 ceiling lights) rather than
// instanced, since 8 is far below where InstancedMesh's setup cost would pay
// for itself (Rocks.tsx uses real instancing for the 150-300-count rock
// field, where it matters).
interface CraterSpec {
  angle: number;
  radius: number;
  large: boolean;
  scale: number;
  rotation: number;
}
const CRATER_MIN_RADIUS = 20; // clears Scene.tsx's own PLAZA_RADIUS (~18.2)
const CRATER_MAX_RADIUS = 52; // stays mostly inside the fog-clear band (Scene.tsx fog near=40) with a few reaching into the haze for depth
const CRATER_COUNT = 8;
const craterRng = seededRandom("hq-ground-craters-v1");
const CRATERS: CraterSpec[] = Array.from({ length: CRATER_COUNT }, (_, i) => ({
  angle: craterRng() * Math.PI * 2,
  radius: CRATER_MIN_RADIUS + craterRng() * (CRATER_MAX_RADIUS - CRATER_MIN_RADIUS),
  large: i % 3 === 0,
  scale: 2.2 + craterRng() * 2.4,
  rotation: craterRng() * Math.PI * 2,
}));

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
    <>
      <mesh position={[0, -0.06, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow={ultra}>
        <circleGeometry args={[RADIUS, SEGMENTS]} />
        <meshStandardMaterial map={texture} color={color} roughness={1} metalness={0} />
      </mesh>
      {/* World-3 environment pass (E2): craters, both tiers -- cheap (8
          small GLBs, no instancing needed at this count) and part of "TV
          tier gets sky+ground+planet+a few props" per this pass's own
          brief. Sit right at the ground plane (y=-0.03, a hair above the
          disc itself to avoid z-fighting, matching this file's own -0.06
          ground-offset convention). */}
      {CRATERS.map((c, i) => (
        <KitProp
          key={i}
          path={c.large ? KIT_PATHS.terrain.craterLarge : KIT_PATHS.terrain.crater}
          scale={c.scale}
          position={[Math.cos(c.angle) * c.radius, -0.03, Math.sin(c.angle) * c.radius]}
          rotation={[0, c.rotation, 0]}
          receiveShadow={ultra}
        />
      ))}
    </>
  );
}

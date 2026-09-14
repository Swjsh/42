"use client";

import { useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import * as THREE from "three";

// ─── World-3 environment pass (2026-09-14, J: "it looks like the background
// is a grey abyss... why not a space theme or a park or something real")
// ────────────────────────────────────────────────────────────────────────
// A large background planet/moon -- see ENVIRONMENT-PLAN.md for the full
// external-reference pass this was built against. Pass G-2 (2026-09-13,
// see Starfield.tsx's own history/blame) dropped an EARLIER planet attempt
// because a camera-facing matcap sphere read as "basically black" at its
// on-screen size: matcap+Lambert shading both depend on SCENE light actually
// reaching the surface, and this scene deliberately runs a dim ambient fill
// (module health tint comes from emissive strips, not per-pixel light -- see
// Scene.tsx's own HQ-v2-perf-pass comment). This build sidesteps that
// failure mode at the root: MeshBasicMaterial (unlit, zero dependency on
// scene lighting -- same family as SkyDome.tsx's own sky sphere) sampling a
// CanvasTexture with the lit/dark gradient BAKED IN, so brightness is
// guaranteed by the texture itself, not by how much scene light lands here --
// which is physically the right call anyway: a real distant sun-lit body
// doesn't dim because a nearby space station's ambient fill is low.

const TEX_W = 256;
const TEX_H = 128;
let _planetTexture: THREE.CanvasTexture | null = null;

function smooth01(t: number): number {
  const c = Math.min(1, Math.max(0, t));
  return c * c * (3 - 2 * c);
}

/** Equirectangular-style gradient on the sphere's own default UVs (u =
 * longitude 0..1, v = latitude 0..1) -- NOT a physically traced terminator,
 * a deliberate low-poly-game-art shortcut (the same shorthand the
 * RenderHub/Kenney-style background planets in ENVIRONMENT-PLAN.md's
 * references use): a soft lit-to-dark sweep across one longitude band (the
 * only band ever actually on camera -- this is a fixed background prop, see
 * PLANET_AZIMUTH below), plus scattered dark crater speckle and 2 larger
 * dark "mare" blotches so the disc reads as a surface, not a flat gradient
 * ball. Built ONCE (module-level cache, same convention as palette.ts's own
 * makeMatcapTexture/makeToonGradientTexture) -- never per-frame, and never at
 * SSR time (throws loudly if invoked outside a browser, matching every other
 * canvas-texture helper in this tree). */
function makePlanetTexture(): THREE.CanvasTexture {
  if (typeof document === "undefined") {
    throw new Error("makePlanetTexture() called outside a browser -- never call this during SSR");
  }
  if (_planetTexture) return _planetTexture;
  const canvas = document.createElement("canvas");
  canvas.width = TEX_W;
  canvas.height = TEX_H;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("makePlanetTexture(): 2D canvas context unavailable");

  const lit = new THREE.Color("#9fb8c9");
  const dark = new THREE.Color("#0d1826");
  const tmp = new THREE.Color();
  const img = ctx.createImageData(TEX_W, TEX_H);
  for (let y = 0; y < TEX_H; y++) {
    const v = y / TEX_H; // 0 (top pole) .. 1 (bottom pole)
    const latShade = 1 - Math.abs(v - 0.5) * 0.6; // dimmer near poles
    for (let x = 0; x < TEX_W; x++) {
      const u = x / TEX_W; // 0..1 longitude
      // World-3 Pass 1 real-capture correction (2026-09-14, env-e2e3-1750.png):
      // the camera only ever sees roughly ONE hemisphere of this sphere (the
      // side facing back toward the station, a fixed relative angle -- see
      // PLANET_FACING_ROTATION below), and the first cut's narrow lit band
      // (full brightness only across 15% of longitude) mostly missed that
      // visible hemisphere, reading as "basically dark" all over again --
      // the SAME class of failure Pass G-2 already hit once with a matcap.
      // Widened so ~70% of longitude reads clearly lit (full brightness
      // across a 0.4-0.6 plateau, CENTERED on u=0.5 -- three.js's default
      // equirect UV maps u=0.5 to local +X exactly, verified against its own
      // shipped SphereGeometry source this session, matching
      // PLANET_FACING_ROTATION's own derivation below which points local +X
      // at the camera). Generous enough that even a small facing-rotation
      // error still shows real brightness, not a knife-edge terminator that
      // has to land exactly right.
      const litT = smooth01((u - 0.15) / 0.25) * (1 - smooth01((u - 0.6) / 0.25));
      tmp.copy(dark).lerp(lit, Math.min(1, litT) * latShade);
      const idx = (y * TEX_W + x) * 4;
      img.data[idx] = Math.round(tmp.r * 255);
      img.data[idx + 1] = Math.round(tmp.g * 255);
      img.data[idx + 2] = Math.round(tmp.b * 255);
      img.data[idx + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);

  // Crater speckle + mare blotches, drawn as soft dark circles ON TOP of the
  // baked gradient (canvas 2D radial-gradient draws, not a per-pixel loop --
  // cheap, ~45 draws total, run once). Deterministic LCG (fixed seed, never
  // Math.random -- this tree's own standing convention) so the texture never
  // reshuffles across reloads.
  let seed = 1234567;
  const rand = () => {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    return seed / 0x7fffffff;
  };
  ctx.globalCompositeOperation = "multiply";
  for (let i = 0; i < 46; i++) {
    const cx = rand() * TEX_W;
    const cy = rand() * TEX_H;
    const r = 2 + rand() * 6;
    const shade = 0.55 + rand() * 0.3;
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    grad.addColorStop(0, `rgba(0,0,0,${1 - shade})`);
    grad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.arc(cx, cy, r, 0, Math.PI * 2);
    ctx.fill();
  }
  for (let i = 0; i < 3; i++) {
    const cx = TEX_W * (0.12 + rand() * 0.3);
    const cy = TEX_H * (0.3 + rand() * 0.4);
    const r = 12 + rand() * 9;
    const grad = ctx.createRadialGradient(cx, cy, 0, cx, cy, r);
    grad.addColorStop(0, "rgba(0,0,0,0.32)");
    grad.addColorStop(1, "rgba(0,0,0,0)");
    ctx.fillStyle = grad;
    ctx.beginPath();
    ctx.ellipse(cx, cy, r, r * 0.6, 0, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalCompositeOperation = "source-over";

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.needsUpdate = true;
  _planetTexture = texture;
  return texture;
}

// Placement -- well inside SkyDome.tsx's own radius (70) so it never clips
// the dome, well beyond the station's own footprint (Scene.tsx's
// PLAZA_RADIUS ~=18.2). Azimuth mirrors Scene.tsx's own `BASE_AZIMUTH + PI`
// (the far side of the origin from the camera's fixed overview position, so
// the planet sits roughly BEHIND the hub from the default view) -- hardcoded
// rather than imported from Scene.tsx to keep this decorative prop from
// depending on the camera's own tuning constants; if BASE_AZIMUTH ever moves,
// re-check this placement against a fresh capture rather than assuming it
// still tracks (same "verify, don't assume" discipline Scene.tsx's own
// camera comments already use throughout).
const BASE_AZIMUTH = Math.atan2(16, 20); // mirrors Scene.tsx's own BASE_AZIMUTH
const PLANET_AZIMUTH = BASE_AZIMUTH + Math.PI;
// World-3 Pass 1 correction: the sphere's own lit-band CENTER (texture
// u=0.5 exactly, by construction of the litT formula above) sits at local
// +X on the sphere's default equirect UVs -- three.js SphereGeometry maps
// u=0 to local -X, u=0.25 to +Z, u=0.5 to +X, u=0.75 to -Z, verified from three's own shipped
// BufferGeometry source this session) must point from the planet's position
// back toward the origin/camera, since that's the ONE hemisphere the camera
// ever actually sees (camera and planet sit on opposite sides of the origin
// at BASE_AZIMUTH / BASE_AZIMUTH+PI). Solving `Ry(rotation) * (1,0,0) ==
// -normalize(planetPosition)` for `rotation` (three's Ry: x'=x*cosR+z*sinR,
// z'=-x*sinR+z*cosR -- the SAME convention Scene.tsx's own `Math.PI/2 -
// angle` module-facing formula already uses, cross-checked against that
// formula's own worked example before trusting this one) gives the
// closed-form below rather than a guessed constant.
const PLANET_FACING_ROTATION = Math.atan2(-Math.cos(BASE_AZIMUTH), Math.sin(BASE_AZIMUTH));
const PLANET_DISTANCE = 58;
// World-3 Pass 1 real-capture correction (2026-09-14, env-e1-1734.png): H=16
// put the WHOLE disc above the visible frame (only a sliver of its bottom
// rim showed at the very top edge) -- the ultra camera pitches down roughly
// 33deg from its own 19.6-unit height, and this scene's frame only spans
// roughly 12-54deg below horizontal, so anything near-level with the camera
// is off-screen above the top edge, not "low on the horizon" at all. Dropped
// to ground level so its elevation-from-camera lands inside that visible
// window instead of guessed a second time blind -- verify against the next
// real capture, nudge further if still clipped.
const PLANET_HEIGHT = 0;
const PLANET_RADIUS = 14;

interface PlanetProps {
  reducedMotion: boolean;
}

/** One low-poly-game-art background planet/moon -- both tiers (TV tier gets
 * sky+ground+planet+a few props per this pass's own brief; this is a single
 * unlit draw call, same cost class as SkyDome/Starfield, so it's never
 * ultra-gated). See this file's own top comment for why MeshBasicMaterial +
 * a baked CanvasTexture is the fix for Pass G-2's "basically black" failure. */
export default function Planet({ reducedMotion }: PlanetProps) {
  const texture = useMemo(() => makePlanetTexture(), []);
  const mesh = useRef<THREE.Mesh>(null);
  const position = useMemo<[number, number, number]>(
    () => [Math.sin(PLANET_AZIMUTH) * PLANET_DISTANCE, PLANET_HEIGHT, Math.cos(PLANET_AZIMUTH) * PLANET_DISTANCE],
    [],
  );

  // Slow rotation, ADDED on top of the fixed facing offset -- reducedMotion
  // freezes the drift (holds at the correct facing) rather than the object
  // itself, matching Starfield.tsx's own established day/night-vs-motion
  // split. The drift is slow enough (0.004 rad/s ~= 0.23deg/s) that it never
  // meaningfully un-faces the lit side within any one viewing session.
  useFrame((state) => {
    if (!mesh.current) return;
    mesh.current.rotation.y = PLANET_FACING_ROTATION + (reducedMotion ? 0 : state.clock.elapsedTime * 0.004);
  });

  return (
    <mesh ref={mesh} position={position} rotation={[0, PLANET_FACING_ROTATION, 0]} renderOrder={-9}>
      <sphereGeometry args={[PLANET_RADIUS, 32, 24]} />
      {/* fog=false: an airless background body sits beyond this scene's own
          atmosphere-less haze, matching SkyDome's own fog exemption -- see
          ENVIRONMENT-PLAN.md item 2 ("sky stays black-to-deep-indigo... this
          is an airless body"). */}
      <meshBasicMaterial map={texture} fog={false} toneMapped={false} />
    </mesh>
  );
}

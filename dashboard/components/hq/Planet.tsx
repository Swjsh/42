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
//
// Polish pass (2026-09-14, coordinator, after J saw env-planetfix-1804.png:
// "reads as a giant pale dome hovering over the base, flat-lit, sharp lower
// edge, no limb"): (1) shrunk to ~40% apparent diameter and moved off-axis
// so it no longer sits centered over the hub; (2) the terminator/lit side
// now derives from the SCENE'S OWN directional-light direction (Scene.tsx's
// `position={[6,10,4]}`) instead of just facing the camera -- a real fixed
// relationship between "which way is the sun" and "which side is lit",
// mirrored here (not imported) the same way PLANET_AZIMUTH already mirrors
// Scene.tsx's BASE_AZIMUTH; (3) per-vertex limb darkening (bright facing the
// camera, dimmer toward the silhouette) computed once from the geometry
// itself -- the same "bake it into vertex colors once, never per-frame"
// technique SkyDome.tsx already uses for ITS gradient; (4) a second, larger
// BackSide sphere with an inverted (bright-at-the-edge) fresnel gradient for
// a thin atmospheric rim glow, additive-blended; (5) subtle sine-layered
// latitude banding in the texture so the surface isn't a flat gradient.

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
 * references use): a soft lit-to-dark sweep across one longitude band
 * (centered exactly on u=0.5 -- see PLANET_FACING_ROTATION below for why
 * that specific value matters), plus subtle sine-layered latitude bands
 * (polish-pass item 5 -- "not a flat gradient"), scattered dark crater
 * speckle, and 2 larger dark "mare" blotches. Built ONCE (module-level
 * cache, same convention as palette.ts's own makeMatcapTexture/
 * makeToonGradientTexture) -- never per-frame, and never at SSR time (throws
 * loudly if invoked outside a browser, matching every other canvas-texture
 * helper in this tree). */
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
  // Polish-pass CORRECTION (2026-09-14, real capture env-polish-day-1830.png:
  // "planet body reads as basically invisible, only the additive rim glow
  // shows" -- the SAME class of failure this whole file exists to avoid, see
  // this file's own top comment on Pass G-2). Root cause: two independently-
  // reasonable multiplicative dimming factors (this texture's own terminator
  // AND bakeLimbDarkening's camera-facing falloff) COMPOUND on whichever
  // vertices the camera actually sees -- 0.5 lit x 0.5 limb-bright = 0.25,
  // dark enough to vanish against the even-darker sky at this object's now-
  // small on-screen size. Lightened from near-black (#0d1826) so the
  // "dark" terminator side alone can never multiply down to invisible.
  const dark = new THREE.Color("#1c3040");
  const tmp = new THREE.Color();
  const img = ctx.createImageData(TEX_W, TEX_H);
  for (let y = 0; y < TEX_H; y++) {
    const v = y / TEX_H; // 0 (top pole) .. 1 (bottom pole)
    const latShade = 1 - Math.abs(v - 0.5) * 0.6; // dimmer near poles
    // Polish-pass item 5: 2 layered sines at different latitude frequencies
    // -- a subtle (+-5%) brightness ripple so the surface reads as banded
    // terrain/cloud structure rather than a single smooth gradient. Kept
    // deliberately faint (0.05/0.03 amplitude) -- "subtle mottling", not a
    // literal gas-giant stripe pattern.
    const bandRipple = 0.05 * Math.sin(v * 26 + 1.3) + 0.03 * Math.sin(v * 11 - 0.4);
    for (let x = 0; x < TEX_W; x++) {
      const u = x / TEX_W; // 0..1 longitude
      // Wide, forgiving lit band (~70% of longitude, full brightness across
      // a 0.4-0.6 plateau CENTERED on u=0.5 -- three.js's default equirect
      // UV maps u=0.5 to local +X exactly, verified against its own shipped
      // SphereGeometry source this session, matching PLANET_FACING_ROTATION's
      // own derivation below which points local +X at the scene's sun).
      // Polish-pass CORRECTION: floored at 0.2 (was 0) -- even the "fully
      // dark" longitude now blends 20% toward the lit color, so a small
      // sun/camera misalignment (the visible hemisphere isn't always
      // perfectly sun-facing once the planet's OWN position is off-axis,
      // item 1) can never land purely on the near-black dark stop.
      const litT = 0.2 + 0.8 * smooth01((u - 0.15) / 0.25) * (1 - smooth01((u - 0.6) / 0.25));
      tmp.copy(dark).lerp(lit, Math.min(1, Math.max(0, litT + bandRipple)) * latShade);
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

// ─── Placement (polish pass, 2026-09-14) ────────────────────────────────────
// Item 1: "~40% apparent diameter, lower-left of frame, never centered over
// the hub, never cropped by the top". RADIUS cut to 0.4x the previous value
// (angular size scales ~linearly with radius/distance at this range: verify
// atan(5.6/58)=5.5deg vs the old atan(14/58)=13.6deg, ratio 0.406 -- matches
// "~40%" directly). Azimuth offset by +35deg from the old dead-center-behind-
// the-hub placement -- derived (not guessed) from the camera's own local
// "right" vector at its default pose (right = forward x up, forward =
// direction from BASE_AZIMUTH's camera position toward the origin): a
// POSITIVE azimuth offset here maps to the camera's LEFT on screen (full
// derivation in this pass's own session notes -- flip the sign if a real
// capture ever shows it drifted right instead, this is geometry worked out
// on paper, not read off a render). HEIGHT dropped further (0 -> -4) to bias
// it lower in frame (smaller elevation-from-camera angle change happens to
// move it toward center/lower, per this same file's own earlier H=16->0
// correction logic).
const BASE_AZIMUTH = Math.atan2(16, 20); // mirrors Scene.tsx's own BASE_AZIMUTH
// World-4 fix (2026-09-14, P1: "PLANET is cut in half by the horizon at the
// default pose... its height was left at 0 after a depthWrite bug hunt"):
// H=0 (the prior pass's deliberately-conservative "reliably visible" choice,
// see the superseded comment this replaces) puts the disc's CENTER almost
// exactly on Ground.tsx's own y=-0.06 plane -- at this camera's elevated
// look-down angle that reads as "sliced by the ground/fog line", exactly
// the bug. Fixed with real camera-basis projection math (not another blind
// guess): built the camera's actual right/up/forward vectors from
// CAMERA_DIST_ULTRA/CAMERA_HEIGHT_ULTRA/BASE_AZIMUTH + DEFAULT_LOOKAT
// (Scene.tsx's own values, mirrored here same as every other constant in
// this file), verified the method against a known point (DEFAULT_LOOKAT
// itself projects to screen-center within rounding), then solved for a
// world position landing at normalized screen coords (x=-0.71, y=0.81 of
// 1 = frame edge) -- comfortably in the upper-left third, ~0.12 (one
// planet-radius) of clearance below the top edge AND ~0.27 above the
// scene's own fog midpoint (computed from the real `<fog args={[..,40,70]}>`
// in Scene.tsx: at this camera's pitch, the ground-hit ray crosses 50% fog
// around normalized-y~=0.45, i.e. this is the practical "horizon" a fogged,
// airless-body scene like this one actually renders, not the geometric
// eye-level line, which sits entirely off-screen above the frame at this
// camera's ~33deg down-pitch and can never be "seen" without something in
// frame trivially satisfying "above" it). Solved azimuth offset came out to
// ~35deg -- independent confirmation of the EARLIER (pre-correction) 35deg
// guess this file's own history already tried and eased back from without
// ever re-verifying against a capture; kept at the math-derived value this
// time. Distance-from-origin (64) and height (3) both chosen off that same
// solved ray, then nudged to clear Rocks.tsx's own FIELD_MAX_RADIUS=60 and
// craters' max radius=52 (real values read from those files this session,
// not assumed) so the disc reads as a distant background body, never
// occluded by or overlapping the terrain field. Verify against the next
// real capture (both the default pose and `?camdist=36`, which lowers the
// camera's pitch and was checked separately this session -- the same
// position keeps clearing both frame edges there too, with more margin).
const PLANET_LEFT_OFFSET = (35 * Math.PI) / 180;
const PLANET_AZIMUTH = BASE_AZIMUTH + Math.PI + PLANET_LEFT_OFFSET;
const PLANET_DISTANCE = 64;
// Real capture (world4-p1p3-default-1849.png) confirmed the disc fully
// clear of the top edge, upper-left, off the hub, horizon clearance
// generous -- but the TOP margin alone measured tight (~10-15px of 1440,
// the RIM_RADIUS_MULT glow eating into the slack this file's own trig
// didn't originally budget for). 3 -> 2.4 trades a little of that generous
// bottom/horizon slack for more top margin, same ray, no other constant
// touched.
const PLANET_HEIGHT = 2.4;
// Slightly smaller than the pre-fix 5.6 (P1: "same size or slightly
// smaller") -- also directly helps the top/horizon clearance math above,
// since a smaller angular radius needs less slack on both sides at once.
const PLANET_RADIUS = 4.8;

// Item 2: the terminator now faces the scene's REAL sun direction, not the
// camera. Scene.tsx's directional light sits at `position={[6,10,4]}` (a
// THREE.DirectionalLight's rays travel FROM its position TOWARD its target,
// default (0,0,0) -- so light arrives at any point in the scene, including
// way out at the planet, from the same parallel (6,10,4) direction, exactly
// what "directional" means). SUN_AZIMUTH mirrors that position's horizontal
// (x,z) components through the SAME atan2(x,z) convention BASE_AZIMUTH
// itself already uses. The closed-form rotation solve is identical in
// shape to this file's own original (camera-facing) derivation, just fed a
// different target azimuth -- see that derivation's own comment (git
// history) for the worked Ry(rotation)*(1,0,0) algebra this reuses.
const SUN_AZIMUTH = Math.atan2(6, 4);
const PLANET_FACING_ROTATION = Math.atan2(-Math.cos(SUN_AZIMUTH), Math.sin(SUN_AZIMUTH));

// Item 3 (limb darkening) + item 4 (rim glow) both need "which direction is
// the camera, roughly, relative to this fixed background prop" -- computed
// once from the camera's own DEFAULT overview pose (Scene.tsx's
// CAMERA_DIST_ULTRA=28 / CAMERA_HEIGHT_ULTRA=19.6, mirrored not imported,
// same reasoning as BASE_AZIMUTH above). A fixed background prop is only
// ever really seen from roughly this one relative angle (the free-camera
// orbit/zoom moves the VIEWER, not this math's own precision requirement --
// this is a cheap, deliberate approximation for a decorative object, not a
// real-time view-dependent shader).
const _cameraDefaultPos = new THREE.Vector3(Math.sin(BASE_AZIMUTH) * 28, 19.6, Math.cos(BASE_AZIMUTH) * 28);
const _yAxis = new THREE.Vector3(0, 1, 0);

function planetWorldPosition(): THREE.Vector3 {
  return new THREE.Vector3(Math.sin(PLANET_AZIMUTH) * PLANET_DISTANCE, PLANET_HEIGHT, Math.cos(PLANET_AZIMUTH) * PLANET_DISTANCE);
}

/** Local-space (i.e. BEFORE the mesh's own PLANET_FACING_ROTATION is
 * applied) direction toward the camera's default position -- used to bake
 * limb darkening on the planet body (rotated geometry) below. World-space
 * view dir rotated by the INVERSE of the mesh's own Y rotation via three's
 * own `Vector3.applyAxisAngle` (a verified library primitive, not hand-
 * rolled trig -- lower risk than re-deriving another rotation matrix by
 * hand for this second, independent use). */
function localViewDirection(): THREE.Vector3 {
  const worldView = _cameraDefaultPos.clone().sub(planetWorldPosition()).normalize();
  return worldView.applyAxisAngle(_yAxis, -PLANET_FACING_ROTATION);
}

/** Bakes per-vertex limb-darkening colors onto a sphere geometry: bright
 * (near white) where the local normal faces the camera, darkening toward
 * the silhouette edge -- `pow(facing, 0.6)` keeps most of the visible disc
 * fairly even and concentrates the falloff in the outer rim, matching how
 * limb darkening actually reads (not a uniform vignette). Combines with
 * `map` multiplicatively via `vertexColors` on the material (same
 * multiply-together convention Ground.tsx's own `color`+`map` pair uses). */
function bakeLimbDarkening(geometry: THREE.SphereGeometry, localView: THREE.Vector3): void {
  const pos = geometry.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  const n = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    n.set(pos.getX(i), pos.getY(i), pos.getZ(i)).normalize();
    const facing = Math.max(0, n.dot(localView));
    // Polish-pass CORRECTION: floor 0.35 -> 0.65 -- this factor MULTIPLIES
    // the texture's own terminator brightness (see makePlanetTexture's own
    // matching correction note), and two independent 0..1 dimming factors
    // compounded is what made the body read as invisible in the first real
    // capture of this pass. Real limb darkening is a mild effect (the disc
    // stays fairly even, only the outer sliver visibly dims) -- 0.65 is
    // closer to that than the original 0.35 ever was.
    const brightness = 0.65 + 0.35 * Math.pow(facing, 0.6);
    colors[i * 3] = brightness;
    colors[i * 3 + 1] = brightness;
    colors[i * 3 + 2] = brightness;
  }
  geometry.setAttribute("color", new THREE.BufferAttribute(colors, 3));
}

const RIM_RADIUS_MULT = 1.14;
const RIM_COLOR = new THREE.Color("#4fd6ff"); // PALETTE.planetRim's own hex -- reused, not reinvented

/** Bakes an inverted fresnel (bright at the silhouette edge, transparent
 * facing the camera) onto a LARGER sphere's vertex colors+alpha -- the
 * "atmosphere glow" technique (an outer BackSide shell, additive-blended)
 * used throughout three.js's own community examples for exactly this look.
 * Deliberately NOT rotated to the sun direction -- a rim/atmosphere glow is
 * a view-dependent optical effect (scattering toward the viewer), not a
 * lit-vs-dark-hemisphere one, so it uses world-space normals directly
 * (this mesh's own rotation stays 0) against the SAME camera view direction
 * localViewDirection() computes for the body, just without the inverse-
 * rotation step (nothing to un-rotate here). */
function buildRimGeometry(): THREE.SphereGeometry {
  const geo = new THREE.SphereGeometry(PLANET_RADIUS * RIM_RADIUS_MULT, 32, 24);
  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 4); // rgba -- alpha carries the fresnel falloff
  const worldView = _cameraDefaultPos.clone().sub(planetWorldPosition()).normalize();
  const n = new THREE.Vector3();
  for (let i = 0; i < pos.count; i++) {
    n.set(pos.getX(i), pos.getY(i), pos.getZ(i)).normalize();
    const facing = Math.max(0, n.dot(worldView));
    const rim = Math.pow(1 - facing, 2.2); // bright at grazing angles, ~0 facing the camera dead-on
    colors[i * 4] = RIM_COLOR.r;
    colors[i * 4 + 1] = RIM_COLOR.g;
    colors[i * 4 + 2] = RIM_COLOR.b;
    colors[i * 4 + 3] = rim * 0.55; // capped -- "thin", never a solid halo
  }
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 4));
  return geo;
}

interface PlanetProps {
  reducedMotion: boolean;
}

/** One low-poly-game-art background planet/moon -- both tiers (TV tier gets
 * sky+ground+planet+a few props per this pass's own brief; 2 unlit draw
 * calls total -- body + rim glow -- same cost class as SkyDome/Starfield).
 * See this file's own top comment for the polish-pass mechanism list. */
export default function Planet({ reducedMotion }: PlanetProps) {
  const texture = useMemo(() => makePlanetTexture(), []);
  const bodyGeometry = useMemo(() => {
    const geo = new THREE.SphereGeometry(PLANET_RADIUS, 32, 24);
    bakeLimbDarkening(geo, localViewDirection());
    return geo;
  }, []);
  const rimGeometry = useMemo(() => buildRimGeometry(), []);
  const mesh = useRef<THREE.Mesh>(null);
  const position = useMemo<[number, number, number]>(() => {
    const p = planetWorldPosition();
    return [p.x, p.y, p.z];
  }, []);

  // Slow rotation, ADDED on top of the fixed sun-facing offset --
  // reducedMotion freezes the drift (holds at the correct facing) rather
  // than the object itself, matching Starfield.tsx's own established
  // day/night-vs-motion split. The drift is slow enough (0.004 rad/s ~=
  // 0.23deg/s) that it never meaningfully un-faces the lit side within any
  // one viewing session. The rim glow mesh is NOT rotated (see
  // buildRimGeometry's own comment -- view-dependent, not sun-dependent).
  useFrame((state) => {
    if (!mesh.current) return;
    mesh.current.rotation.y = PLANET_FACING_ROTATION + (reducedMotion ? 0 : state.clock.elapsedTime * 0.004);
  });

  return (
    <group position={position}>
      {/* Rim glow -- drawn FIRST (more negative renderOrder) so the opaque
          body below overdraws it wherever they overlap in screen space,
          leaving only the silhouette-edge glow visible (both meshes skip
          depthWrite -- item 4, "must stay behind everything" -- so their
          relative compositing is controlled purely by this draw sequence,
          not the depth buffer, exactly matching SkyDome.tsx's own
          depthWrite={false} convention this file should have matched from
          the start). */}
      <mesh geometry={rimGeometry} renderOrder={-9.2}>
        <meshBasicMaterial vertexColors transparent depthWrite={false} fog={false} toneMapped={false} blending={THREE.AdditiveBlending} side={THREE.BackSide} />
      </mesh>
      <mesh ref={mesh} geometry={bodyGeometry} rotation={[0, PLANET_FACING_ROTATION, 0]} renderOrder={-9.1}>
        {/* fog=false: an airless background body sits beyond this scene's
            own atmosphere-less haze, matching SkyDome's own fog exemption.
            World-3 Pass 2 ROOT CAUSE fix (2026-09-14, env-polish-day2-
            1845.png: the whole body vanished): depthWrite={false} here
            (the coordinator's own literal suggestion for item 4, "stays
            behind everything") backfired for a DISCRETE positioned object
            (unlike SkyDome's infinite backdrop sphere, where it's correct):
            this mesh draws EARLY (renderOrder -9.1) and, with no depth
            written, leaves the depth buffer untouched at its own pixels --
            so ANY normal opaque geometry drawn LATER (Ground.tsx's disc,
            default renderOrder=0, depthWrite=true) simply painted over it
            at every pixel where their SCREEN-SPACE footprints overlapped,
            regardless of which was actually closer. A real, ~90-unit-away
            discrete object is exactly what the depth buffer is FOR --
            depthWrite restored to its default (true) so normal z-testing
            (not draw-order guessing) is what keeps this "behind everything
            closer" and correctly VISIBLE everywhere nothing closer exists,
            satisfying the coordinator's own stated goal more reliably than
            their literal suggested mechanism did. renderOrder stays low
            anyway (harmless, and keeps it grouped with the other backdrop
            draws). vertexColors multiplies the limb-darkening bake onto the
            map texture. */}
        <meshBasicMaterial map={texture} vertexColors fog={false} toneMapped={false} />
      </mesh>
    </group>
  );
}

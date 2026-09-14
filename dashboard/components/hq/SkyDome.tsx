"use client";

import { useMemo } from "react";
import * as THREE from "three";
import { PALETTE } from "./palette";

// Beyond the scene's own fog far (20 -> 62, see Scene.tsx) so the dome sits
// past the fogged region entirely -- but the dome's own material disables
// fog (see below), so this radius only needs to be "big enough to fully
// enclose the ring/camera", not a fog-avoidance number in its own right.
const RADIUS = 70;

/** Vertex-color sky gradient -- dark at both poles (zenith looking up,
 * nadir looking down), a warm-tinted band right at the equator/horizon.
 * `1 - |y|/R` peaks at 1 exactly at the horizon and falls to 0 at either
 * pole; the warm mix is then capped to the narrow top 35% of that range so
 * this reads as a horizon GLOW (Tron/Blade-Runner cold-warm direction, HQ
 * v4 style brief section 3) rather than a literal daytime sky -- the warm
 * hue must stay a background accent, never compete with the scene's own
 * foreground cyan/amber accents. */
function buildSkyGeometry(): THREE.SphereGeometry {
  // Layout hygiene fix (2026-09-13, J: "sky dome silhouette visible as a
  // dark octagon at the top") -- 24 width segments was faceted enough to
  // show as a visible polygon silhouette at the horizon from inside a
  // BackSide sphere; 48/32 is the brief's own stated floor and reads as a
  // smooth gradient instead. Still a single 1-draw-call mesh either way.
  const geo = new THREE.SphereGeometry(RADIUS, 48, 32);
  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  const zenith = new THREE.Color(PALETTE.space);
  const depth = new THREE.Color(PALETTE.horizonDepth);
  const warm = new THREE.Color(PALETTE.warmAccent);
  const tmp = new THREE.Color();
  for (let i = 0; i < pos.count; i++) {
    const y = pos.getY(i);
    const skyT = 1 - Math.min(1, Math.abs(y) / RADIUS); // 1 at horizon, 0 at either pole
    tmp.copy(zenith).lerp(depth, Math.min(1, skyT * 1.4));
    const horizonBand = Math.max(0, skyT - 0.65) / 0.35; // only the closest 35% to horizon
    tmp.lerp(warm, horizonBand * 0.4); // capped mix -- a glow, not a solid amber band
    colors[i * 3] = tmp.r;
    colors[i * 3 + 1] = tmp.g;
    colors[i * 3 + 2] = tmp.b;
  }
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return geo;
}

/**
 * Backdrop dressing (HQ v4 look pass, 2026-09-13): a single BackSide sphere
 * with baked-in vertex colors, `meshBasicMaterial vertexColors` -- no
 * fragment shader, no texture, 1 draw call. Fixes the "empty void"
 * backdrop tell (the style brief's #7): today's #03040a background reads
 * as nothing at all behind the sparse starfield; this gives it actual
 * depth and a horizon. `fog={false}` is load-bearing -- without it, the
 * scene's own fog (far=62, well inside this dome's r=70) would render the
 * ENTIRE dome as flat fog color regardless of its vertex colors, silently
 * defeating the whole point. Mounted in Scene.tsx behind <Starfield>.
 */
export default function SkyDome() {
  const geometry = useMemo(() => buildSkyGeometry(), []);

  return (
    <mesh geometry={geometry} renderOrder={-10}>
      <meshBasicMaterial vertexColors side={THREE.BackSide} depthWrite={false} fog={false} toneMapped={false} />
    </mesh>
  );
}

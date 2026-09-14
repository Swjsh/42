"use client";

import { useMemo } from "react";
import * as THREE from "three";
import { PALETTE } from "./palette";

// Beyond the scene's own fog far (20 -> 62, see Scene.tsx) so the dome sits
// past the fogged region entirely -- but the dome's own material disables
// fog (see below), so this radius only needs to be "big enough to fully
// enclose the ring/camera", not a fog-avoidance number in its own right.
const RADIUS = 70;

// LIVE-1 item 3 (2026-09-14, J: "it is day now and the frame is still dim
// orange"): root cause, found by reading every day/night-relevant path in
// this tree before touching anything -- Scene.tsx's own ET clock
// (nowEtMinutes/dayNightFactor, both explicit `Intl` America/New_York
// conversions, grepped this session for any `.getHours()`/local-time
// shortcut and found none) is NOT stuck; hemisphereLight/directionalLight
// already scale correctly to ~1.0x by midday (Scene.tsx's own `nightMult`).
// This dome, however, was ALWAYS a STATIC warm/dark gradient (Pass G-2,
// 2026-09-13) -- built once via vertex colors baked at construction time,
// never wired to the clock AT ALL -- so the sky read identically dim-warm
// at 09:00 ET as at 02:00 ET, dominating the frame regardless of what the
// station's own (correctly-scaling) interior lights were doing. Fixed by
// blending TWO gradients (still-dark night, brighter-blue day) by the SAME
// dayFactor Scene.tsx already computes, re-baked into the vertex colors
// whenever it changes (cheap -- one CPU pass over ~3000 vertices, done at
// most once per Scene re-render, i.e. the same 15-60s poll cadence
// nightMult itself already updates on, never per-frame).
const NIGHT_ZENITH = PALETTE.horizonDepth; // "#12203a" -- UNCHANGED from before this pass, so night keeps its exact prior look
const NIGHT_DEPTH = PALETTE.horizonDepth;
const DAY_ZENITH = "#4a7fb0";
const DAY_DEPTH = "#bcd9ee";

/** Vertex-color sky gradient -- dark-to-bright at both poles depending on
 * `dayFactor` (zenith looking up, nadir looking down), a tinted band right
 * at the equator/horizon (warm at night, a much lighter kiss of it by day --
 * a bright noon sky's horizon reads pale/white, not amber). `1 - |y|/R`
 * peaks at 1 exactly at the horizon and falls to 0 at either pole; the
 * accent mix is capped to the narrow top 35% of that range so this reads as
 * a horizon GLOW (Tron/Blade-Runner cold-warm direction, HQ v4 style brief
 * section 3) rather than a literal photographic sky -- the accent hue must
 * stay a background note, never compete with the scene's own foreground
 * cyan/amber accents. */
function buildSkyGeometry(dayFactor: number): THREE.SphereGeometry {
  // Layout hygiene fix (2026-09-13, J: "sky dome silhouette visible as a
  // dark octagon at the top") -- 24 width segments was faceted enough to
  // show as a visible polygon silhouette at the horizon from inside a
  // BackSide sphere; 48/32 is the brief's own stated floor and reads as a
  // smooth gradient instead. Still a single 1-draw-call mesh either way.
  const geo = new THREE.SphereGeometry(RADIUS, 48, 32);
  const pos = geo.attributes.position;
  const colors = new Float32Array(pos.count * 3);
  // Pass G-2 (2026-09-13): zenith base color PALETTE.space ("#03040a", near-
  // black) -> PALETTE.horizonDepth ("#12203a", dark navy). Root cause of the
  // hub's black arch, confirmed by a real camera raycast (not guessed): the
  // ray passed through HubRoom entirely (an intentional open-top diorama,
  // "the bays have no roofs either") and hit THIS sphere's own BackSide
  // surface directly (dist=88.75, chain=[(Mesh) < (Scene)], material=
  // MeshBasicMaterial -- an exact match for this component), at a Y high
  // enough that skyT sits near 0 (pole region, outside the horizon glow
  // band) -- so the arch WAS this gradient's own darkest stop, correctly
  // rendered, just too close to the scene's own #03040a background/void
  // color to read as sky rather than a hole. horizonDepth is still clearly
  // the DARKEST stop in the gradient (skyT=0 still lerps toward it, never
  // fully replaces the mid/horizon tones), so the "dark at zenith, warm at
  // horizon" shape this pass's own capture already approved is unchanged --
  // only the floor is lifted from near-black to a dark, clearly-sky navy.
  // LIVE-1 item 3: zenith/depth now LERP between the night and day stops by
  // `dayFactor` (0 = night, matching the prior static PALETTE.horizonDepth
  // pair exactly; 1 = the new brighter-blue midday pair) -- the warm accent
  // stays the SAME hue at every hour (PALETTE.warmAccent, this scene's own
  // established horizon-glow color) but its mix CAP shrinks by day (a
  // bright noon horizon reads pale, not amber).
  const zenith = new THREE.Color(NIGHT_ZENITH).lerp(new THREE.Color(DAY_ZENITH), dayFactor);
  const depth = new THREE.Color(NIGHT_DEPTH).lerp(new THREE.Color(DAY_DEPTH), dayFactor);
  const warm = new THREE.Color(PALETTE.warmAccent);
  const warmCap = lerpNum(0.4, 0.12, dayFactor);
  const tmp = new THREE.Color();
  for (let i = 0; i < pos.count; i++) {
    const y = pos.getY(i);
    const skyT = 1 - Math.min(1, Math.abs(y) / RADIUS); // 1 at horizon, 0 at either pole
    tmp.copy(zenith).lerp(depth, Math.min(1, skyT * 1.4));
    const horizonBand = Math.max(0, skyT - 0.65) / 0.35; // only the closest 35% to horizon
    tmp.lerp(warm, horizonBand * warmCap); // capped mix -- a glow, not a solid band
    colors[i * 3] = tmp.r;
    colors[i * 3 + 1] = tmp.g;
    colors[i * 3 + 2] = tmp.b;
  }
  geo.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  return geo;
}

function lerpNum(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

interface SkyDomeProps {
  /** LIVE-1 item 3 (2026-09-14): 0 (deepest night) .. 1 (peak midday) --
   * pass Scene.tsx's own `nightFactor` (dayNightFactor()'s return value;
   * see that function's own doc comment for why it's named "night" but
   * reads as a DAY-brightness scalar) straight through, the SAME value
   * already driving hemisphereLight/directionalLight, so the sky and the
   * station's own ambient fill always agree about what time it is.
   * Defaults to 1 (full day -- the brighter, safer default if ever omitted)
   * rather than 0, since a missing prop reading as "stuck at night" is
   * exactly the bug this pass exists to fix. */
  dayFactor?: number;
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
export default function SkyDome({ dayFactor = 1 }: SkyDomeProps) {
  // Re-baked (not per-frame -- a plain useMemo keyed on `dayFactor`, which
  // only changes on a genuine Scene re-render, the same 15-60s poll cadence
  // nightMult itself already updates the lights on) whenever the day/night
  // value moves, so the sky's own mood tracks the same clock the station's
  // ambient fill already does.
  const geometry = useMemo(() => buildSkyGeometry(dayFactor), [dayFactor]);

  return (
    <mesh geometry={geometry} renderOrder={-10}>
      <meshBasicMaterial vertexColors side={THREE.BackSide} depthWrite={false} fog={false} toneMapped={false} />
    </mesh>
  );
}

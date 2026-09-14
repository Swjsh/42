"use client";

import { useEffect, useState } from "react";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import Scene from "./Scene";
import PerfReporter from "./PerfReporter";
import { HUD_RIGHT_COLUMN_WIDTH } from "./Hud";
import type { HqApiResponse } from "./types";
import { exposeSceneForDiag, installEarlyErrorCapture } from "@/lib/hq-motion-diag";

// Item 26 diag: module scope -- runs once at import time, before <Canvas>
// (and therefore r3f's own frameloop) ever mounts. See the function's own
// comment in hq-motion-diag.ts for why capture-phase + always-on.
installEarlyErrorCapture();

interface CanvasRootProps {
  data: HqApiResponse | undefined;
  reducedMotion: boolean;
  lanKiosk: boolean;
  /** Coordinator 2026-09-13: "record... the HUD perf line (fps/calls/tris
   * ...from PerfReporter)" per pass -- PerfReporter's old `enabled={lanKiosk}`
   * gate never fires for a `?kiosk=1` localhost test tab (lanKiosk requires
   * a non-localhost hostname), only for a real LAN viewer. `kiosk` is
   * page.tsx's broader boolean (`?kiosk=1` OR lanKiosk) already used for
   * poll interval/Hud gating -- widening PerfReporter to the same boundary
   * lets a manual `?kiosk=1` test session report real numbers too, without
   * spamming the probe endpoint for a plain interactive dev tab (neither
   * kiosk flag is set there). */
  kiosk: boolean;
}

const MAX_BUFFER_WIDTH = 1920;
// HQ v2 (2026-09-13): the real TV reports devicePixelRatio 1.25 (Tizen 9 /
// SamsungBrowser scales its 1536x749 CSS viewport up from a 1920x936 device
// buffer) -- capping dpr at 1 was rendering 1536x749 and letting the panel
// upscale ~2.5x, which is the "pixelated" J saw. Clamping to [1, 1.25]
// matches the device's own reported ratio (crisp on THIS TV) while never
// going below native 1x on any screen; the >1920-wide scale-down below is
// unrelated and can still legitimately push the effective dpr under 1 on a
// very wide, low-dpr viewport (kept as-is).
const MAX_DPR = 1.25;

function computeDpr(): number {
  const dpr = Math.min(Math.max(window.devicePixelRatio || 1, 1), MAX_DPR);
  // Pass G (2026-09-13): the canvas container is now calc(100% -
  // HUD_RIGHT_COLUMN_WIDTH) wide (see the split-layout div below), not the
  // full window -- subtracting it here keeps this buffer-width cap
  // matched to the canvas's ACTUAL rendered width instead of over-counting
  // by 500px of a column it no longer occupies. Floored at a sane minimum
  // so a pathologically narrow window (well below any real TV/monitor)
  // never divides by a near-zero width.
  const cssWidth = Math.max(window.innerWidth - HUD_RIGHT_COLUMN_WIDTH, 320) || MAX_BUFFER_WIDTH;
  const bufferWidth = cssWidth * dpr;
  return bufferWidth <= MAX_BUFFER_WIDTH ? dpr : MAX_BUFFER_WIDTH / cssWidth;
}

/**
 * Item 26 ROOT CAUSE (2026-09-14, TV-tier flat-environment investigation --
 * verified against react-three-fiber's own installed source, not guessed):
 * `PerfReporter.tsx` (mounted below, unconditionally, on BOTH tiers)
 * registers three `useFrame` callbacks at explicit non-zero priorities
 * (-Infinity, 1.5, 2 -- see that file's own Pass F comment: needed for
 * accurate `gl.info.render.calls/triangles` accounting across a multi-pass
 * renderer). Reading r3f 9.6.1's own bundled source
 * (node_modules/@react-three/fiber/dist/events-*.esm.js, function
 * `update()`): `if (!state.internal.priority && state.gl.render)
 * state.gl.render(state.scene, state.camera)` -- ANY priority useFrame
 * registration anywhere in the tree flips `state.internal.priority` truthy
 * for the WHOLE canvas, which SKIPS r3f's own automatic default render call
 * on the theory that a priority subscriber has taken over rendering. On the
 * ultra tier that theory holds: `EffectsStack.tsx` mounts its own priority-1
 * `useFrame` that renders the scene through its postprocessing composer. TV
 * tier mounts no composer -- so the moment `<PerfReporter>` mounts, NOTHING
 * at any priority ever calls `gl.render(scene, camera)` again, forever.
 * Live proof this pass via a diag-gated `window.__hqScene/__hqCamera/__hqGl`
 * hook (hq-motion-diag.ts#exposeSceneForDiag): `useFrame` subscribers kept
 * running fine the whole time (CameraRig moved the camera to the exact
 * correct TV orbit position every check), `gl.info.render.calls` stayed at
 * 0 and the canvas read back fully transparent (0,0,0,0) at every sampled
 * pixel, an always-on capture-phase `window` error listener
 * (hq-motion-diag.ts#installEarlyErrorCapture, installed before <Canvas>
 * ever mounts) caught zero errors (this is not a crash, it is r3f
 * INTENTIONALLY skipping its own render call), and a single MANUAL
 * `gl.render(scene, camera)` issued from the console succeeded instantly
 * with 58 draw calls and painted the correct sky/ground/planet gradient --
 * proving the scene/materials/camera were never broken, only the automatic
 * render call was silently suppressed. With nothing ever painted, the
 * canvas stays transparent and the wrapping div's own flat
 * `background:"#03040a"` (== PALETTE.space, the exact RGB(3,4,10) sampled
 * in the original capture) shows through naked, indistinguishable from "the
 * environment is broken". Fix: `<ManualRender>` below is TV tier's
 * equivalent of ultra's `EffectsStack` -- the ONE priority subscriber that
 * actually renders the scene, at the SAME priority (1) PerfReporter's own
 * comments already document as "EffectComposer's own priority-1 render" for
 * its stat reads at 1.5/2 to key off of; this makes "something renders at
 * priority 1" a tier-independent invariant instead of an ultra-only one.
 *
 * A SEPARATE, secondary bug fixed the same pass while diagnosing this one:
 * this component used to flip `frameloop` to "never" via a one-shot
 * `document.hidden` check with no retry (added fe6275fb, the very first HQ
 * commit, undocumented rationale). Confirmed live: `document.hidden` reads
 * `true` for the lifetime of an automation-driven Browser-pane session
 * (already documented by commit b561e458's own PerfReporter investigation,
 * and by hq_capture.ps1's own header comment, "the Browser pane hides tabs
 * and pauses the canvas"), which parked `frameloop` at "never" with no
 * later visibilitychange event ever firing to correct a check that was
 * wrong from the very first read -- a real, independently fixable footgun
 * even though it was not what the original flat-color capture showed (that
 * capture came from a real, visible kiosk window, unaffected by this).
 * `frameloop` is now pinned to the constant "always" -- TV tier is a
 * dedicated kiosk/capture target, never a normal multi-tab browsing
 * session, and the browser's own native backgrounding rAF throttle already
 * saves cycles on a genuinely backgrounded tab without this fragile,
 * unrecoverable manual toggle.
 *
 * TV-budgeted <Canvas> wrapper otherwise unchanged: drawing-buffer capped
 * at ~1920px wide (dpr<=1, scaled down further on very wide viewports), no
 * antialias, no shadows, powerPreference "low-power", and a context-lost
 * overlay that reloads the page after 5s. Everything <Scene> needs before
 * it's safe to run on a TV SoC lives here, not scattered across the scene
 * components.
 */
function ManualRender() {
  const { gl, scene, camera } = useThree();
  useFrame(() => {
    gl.render(scene, camera);
  }, 1);
  return null;
}

export default function CanvasRoot({ data, reducedMotion, lanKiosk: _lanKiosk, kiosk }: CanvasRootProps) {
  const [dpr, setDpr] = useState(() => (typeof window !== "undefined" ? computeDpr() : 1));
  const [contextLost, setContextLost] = useState(false);

  useEffect(() => {
    const onResize = () => setDpr(computeDpr());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  return (
    // Pass G (2026-09-13, coordinator item 1): same split-layout width
    // constraint as UltraCanvasRoot.tsx -- see that file's own comment for
    // the full mechanism.
    <div style={{ position: "fixed", top: 0, left: 0, bottom: 0, width: `calc(100% - ${HUD_RIGHT_COLUMN_WIDTH}px)`, background: "#03040a" }}>
      <Canvas
        dpr={dpr}
        frameloop="always"
        shadows={false}
        // HQ v4 look pass (2026-09-13): MSAA turned on -- ARM's own docs
        // call 4x MSAA "almost free" on tile-based GPUs like the Mali-G31
        // (resolved in on-chip tile memory, unlike immediate-mode desktop
        // GPUs) -- the single highest-confidence fix for the "jaggy PS2"
        // tell, verify via tv-perf.jsonl TV rows: fps should barely move.
        gl={{ antialias: true, powerPreference: "low-power", alpha: false }}
        // World-2 item 1 (2026-09-14, J: "when I scroll out, a black circle
        // just appears and takes over everything"): far 90 -> 400. Root
        // cause -- this fixed TV camera sits sqrt(22^2+7.5^2)~=23.2 units
        // from the origin (Scene.tsx CAMERA_DIST/CAMERA_HEIGHT) and
        // SkyDome.tsx's BackSide sphere has radius 70, fog={false} -- the
        // dome's far wall (up to ~23.2+70=93.2u away) sat PAST the old far=90
        // clip plane, so the renderer's raw clear color (near-black, no
        // fog/dome to paint over it) showed through as a disc where the dome
        // should have been. 400 sits comfortably beyond any real distance in
        // this scene (dome radius 70 plus the largest possible camera
        // distance) with headroom for future tuning.
        camera={{ fov: 42, near: 0.5, far: 400 }}
        onCreated={(state) => {
          // Item 26 diag (2026-09-14, TV-tier flat-environment investigation):
          // ?diag=1 only -- see hq-motion-diag.ts#exposeSceneForDiag's own
          // comment. No-ops on a plain kiosk tab (no query param).
          exposeSceneForDiag(state.scene, state.camera, state.gl);
          const canvas = state.gl.domElement;
          canvas.addEventListener("webglcontextlost", (e) => {
            e.preventDefault();
            setContextLost(true);
            window.setTimeout(() => window.location.reload(), 5000);
          });
        }}
      >
        <Scene data={data} reducedMotion={reducedMotion} />
        {/* Item 26 fix -- see this file's own top-of-file root-cause
            comment: PerfReporter's priority useFrame hooks silently disable
            r3f's automatic render call, and TV tier has no EffectComposer
            (unlike ultra's EffectsStack) to pick up the slack. Mounted
            unconditionally, same as PerfReporter itself. */}
        <ManualRender />
        <PerfReporter enabled={kiosk} />
      </Canvas>

      {contextLost && (
        <div
          style={{
            position: "fixed", inset: 0, background: "rgba(3,4,10,0.92)", color: "#dff3ff",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: 20, fontFamily: "system-ui, sans-serif", zIndex: 50,
          }}
        >
          Reconnecting...
        </div>
      )}
    </div>
  );
}

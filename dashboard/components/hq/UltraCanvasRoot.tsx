"use client";

import { memo, useEffect, useState } from "react";
import { Canvas } from "@react-three/fiber";
import * as THREE from "three";
import Scene from "./Scene";
import StandbyPanel from "./StandbyPanel";
import PerfReporter from "./PerfReporter";
import { HUD_RIGHT_COLUMN_WIDTH } from "./Hud";
import type { HqApiResponse } from "./types";

interface UltraCanvasRootProps {
  data: HqApiResponse | undefined;
  reducedMotion: boolean;
  /** Pass B (2026-09-13): PerfReporter was never mounted on this tier at
   * all before this pass (CanvasRoot.tsx's TV tier had it, this one
   * didn't) -- the coordinator's per-pass report now needs real fps/calls/
   * tris numbers from here too, since screenshots never reach disk. See
   * CanvasRoot.tsx's own comment on why `kiosk` (not `lanKiosk`) is the
   * right gate. */
  kiosk: boolean;
}

/**
 * PC/monitor <Canvas> wrapper (HQ ultra tier, 2026-09-13, HQ-ULTRA-TIER-
 * BRIEF.md) -- a FORK of CanvasRoot.tsx, not a tier-branch inside it, per
 * the brief's own section 6 item 1: the TV tier's config (dpr<=1.25,
 * antialias:true, powerPreference:"low-power", shadows off, dim-but-keep-
 * rendering during gaming) and this tier's config (dpr up to 2, antialias
 * OFF because SMAA replaces it in the post stack, powerPreference:
 * "high-performance", real soft shadows, FULLY STOP rendering during
 * gaming) are different enough in kind, not just degree, to warrant
 * separate top-level components -- while <Scene> itself stays the ONE
 * shared component (with `tier` passed through) so the v3 motion/event
 * logic never forks into two copies that could drift.
 *
 * Hard rule (brief section 7): the ultra tier must fully STOP the render
 * loop -- frameloop "never", not just dim -- the instant `data.mode ===
 * "gaming"` OR the tab is hidden, auto-resuming otherwise. A full PBR +
 * N8AO + DoF + GodRays stack is exactly the load that competes with a game
 * on the same GPU; the TV tier's existing dim-and-keep-rendering behavior
 * is fine there (a cheap, already-idle mobile GPU) but must NOT be
 * inherited here by accident.
 */
/** World pass A: memoized alongside Scene.tsx's own memo (see that file's
 * comment for the full mechanism) -- defense in depth, one more layer that
 * skips work when page.tsx's stable `sceneData` hasn't actually changed. */
function UltraCanvasRoot({ data, reducedMotion, kiosk }: UltraCanvasRootProps) {
  const gaming = data?.mode === "gaming";
  const [hidden, setHidden] = useState(false);
  const [contextLost, setContextLost] = useState(false);

  useEffect(() => {
    const onVis = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", onVis);
    onVis();
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  const paused = gaming || hidden;
  const frameloop = paused ? "never" : "always";

  return (
    // Pass G (2026-09-13, coordinator item 1: "the 3D canvas gets the left
    // ~74% of the viewport... nothing can sit under the roster after
    // that"): width constrained to calc(100% - HUD_RIGHT_COLUMN_WIDTH)
    // instead of the old full-viewport inset:0 -- the canvas DOM element's
    // own bounding rect is what drei's <Html> positions labels relative
    // to, so a narrower container makes it STRUCTURALLY impossible for a
    // 3D-projected label to land under Hud.tsx's solid right column,
    // rather than relying on camera framing / opacity to avoid it (Pass
    // F's approach, which helped but never fully worked). r3f's own
    // ResizeObserver on the canvas element updates `camera.aspect`
    // automatically when this width changes -- no separate aspect-ratio
    // code needed here.
    <div style={{ position: "fixed", top: 0, left: 0, bottom: 0, width: `calc(100% - ${HUD_RIGHT_COLUMN_WIDTH}px)`, background: "#03040a" }}>
      {/* Standby state (2026-09-13 -- J: "wtf is this slop" on the old
          dim-the-whole-3D-scene-and-overlay-a-giant-plaque approach). That
          is GONE: while paused the canvas is fully HIDDEN
          (visibility:hidden, not just dimmed -- it isn't rendering at all,
          frameloop is "never") and StandbyPanel is the only thing on
          screen, a purpose-built HTML panel with real roster/needs-J/vitals
          data, not a degraded view of the 3D scene. */}
      <div style={{ position: "absolute", inset: 0, visibility: paused ? "hidden" : "visible" }}>
        <Canvas
          dpr={[1, 2]}
          frameloop={frameloop}
          shadows="soft"
          gl={{ antialias: false, powerPreference: "high-performance", alpha: false }}
          // World pass A (2026-09-13, first real screenshot): fov 42->50 --
          // one lever alongside Scene.tsx's own closer/lower camera to fill
          // more of the 16:9 frame; camera stays the shared position/lookAt
          // logic in Scene.tsx#CameraRig, only this tier's fov differs (TV's
          // CanvasRoot.tsx camera prop is untouched).
          camera={{ fov: 50, near: 0.5, far: 90 }}
          onCreated={(state) => {
            // "Light it like a set: exposure up" -- set directly on the real
            // THREE.WebGLRenderer via onCreated (fires once, not per-frame),
            // rather than relying on unverified `gl` PROP-object semantics
            // for a property three.js applies post-construction, not at
            // constructor time. ACESFilmicToneMapping is the standard
            // "cinematic" curve (rolls off highlights instead of clipping
            // them white) that exposure/bloom tuning is normally built
            // around; explicit rather than assumed. toneMappingExposure's
            // initial 1.35 (LIVE-1 item 2 follow-up, 2026-09-14) is now only
            // the FIRST-PAINT value, matching Scene.tsx#ExposureSync's own
            // EXPOSURE_NIGHT constant -- that component overwrites this
            // property reactively from its very first useFrame onward,
            // scaling it down toward 1.0 by day so the architecture no
            // longer blows out once daylight is genuinely bright (item 3).
            state.gl.toneMapping = THREE.ACESFilmicToneMapping;
            state.gl.toneMappingExposure = 1.35;
            const canvas = state.gl.domElement;
            canvas.addEventListener("webglcontextlost", (e) => {
              e.preventDefault();
              setContextLost(true);
              window.setTimeout(() => window.location.reload(), 5000);
            });
          }}
        >
          <Scene data={data} reducedMotion={reducedMotion} tier="ultra" />
          {/* firstReportMs 30s (not PerfReporter's own 10s default) -- see
              that component's own comment: ultra tier's async GLTF/Suspense
              loading storm needs longer than 10s to settle before a "steady
              state" sample means anything. */}
          <PerfReporter enabled={kiosk} firstReportMs={30_000} />
        </Canvas>
      </div>

      {paused && <StandbyPanel data={data} />}

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

export default memo(UltraCanvasRoot);

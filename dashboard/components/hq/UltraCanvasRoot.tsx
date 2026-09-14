"use client";

import { useEffect, useState } from "react";
import { Canvas } from "@react-three/fiber";
import Scene from "./Scene";
import StandbyPanel from "./StandbyPanel";
import type { HqApiResponse } from "./types";

interface UltraCanvasRootProps {
  data: HqApiResponse | undefined;
  reducedMotion: boolean;
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
export default function UltraCanvasRoot({ data, reducedMotion }: UltraCanvasRootProps) {
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
    <div style={{ position: "fixed", inset: 0, background: "#03040a" }}>
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
          camera={{ fov: 42, near: 0.5, far: 90 }}
          onCreated={(state) => {
            const canvas = state.gl.domElement;
            canvas.addEventListener("webglcontextlost", (e) => {
              e.preventDefault();
              setContextLost(true);
              window.setTimeout(() => window.location.reload(), 5000);
            });
          }}
        >
          <Scene data={data} reducedMotion={reducedMotion} tier="ultra" />
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

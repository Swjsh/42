"use client";

import { useEffect, useState } from "react";
import { Canvas } from "@react-three/fiber";
import Scene from "./Scene";
import PerfReporter from "./PerfReporter";
import type { HqApiResponse } from "./types";

interface CanvasRootProps {
  data: HqApiResponse | undefined;
  reducedMotion: boolean;
  lanKiosk: boolean;
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
  const cssWidth = window.innerWidth || MAX_BUFFER_WIDTH;
  const bufferWidth = cssWidth * dpr;
  return bufferWidth <= MAX_BUFFER_WIDTH ? dpr : MAX_BUFFER_WIDTH / cssWidth;
}

/**
 * TV-budgeted <Canvas> wrapper: drawing-buffer capped at ~1920px wide
 * (dpr<=1, scaled down further on very wide viewports), no antialias, no
 * shadows, powerPreference "low-power", frameloop paused whenever the page
 * is hidden (document.hidden), and a context-lost overlay that reloads the
 * page after 5s. Everything <Scene> needs before it's safe to run on a TV
 * SoC lives here, not scattered across the scene components.
 */
export default function CanvasRoot({ data, reducedMotion, lanKiosk }: CanvasRootProps) {
  const [dpr, setDpr] = useState(() => (typeof window !== "undefined" ? computeDpr() : 1));
  const [frameloop, setFrameloop] = useState<"always" | "never">("always");
  const [contextLost, setContextLost] = useState(false);

  useEffect(() => {
    const onResize = () => setDpr(computeDpr());
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  useEffect(() => {
    const onVis = () => setFrameloop(document.hidden ? "never" : "always");
    document.addEventListener("visibilitychange", onVis);
    onVis();
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  return (
    <div style={{ position: "fixed", inset: 0, background: "#03040a" }}>
      <Canvas
        dpr={dpr}
        frameloop={frameloop}
        shadows={false}
        gl={{ antialias: false, powerPreference: "low-power", alpha: false }}
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
        <Scene data={data} reducedMotion={reducedMotion} />
        <PerfReporter enabled={lanKiosk} />
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

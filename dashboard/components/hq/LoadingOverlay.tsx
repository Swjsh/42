"use client";

import { useEffect, useRef, useState } from "react";
import { useProgress } from "@react-three/drei";

interface LoadingOverlayProps {
  /** True once the tier is resolved AND webgl2===true (page.tsx's own
   * gate) -- i.e. a <Canvas> is actually about to mount/has mounted. Before
   * that there is nothing to report progress on yet, so this overlay shows
   * a static "starting..." 0% rather than a premature ready state. */
  canvasMounted: boolean;
  /** True once page.tsx has resolved that NO canvas will EVER mount this
   * session (webgl2 === false -> the HqFallback path). Caught in review
   * before this ever reached a build: without this, `canvasMounted` stays
   * permanently false on that path, so BOTH the progress-ready check and
   * the safety timeout below (which only arms `if (canvasMounted)`) would
   * never fire -- the overlay would sit on top of HqFallback forever. This
   * flag lets `ready` go true immediately on that path instead, reusing
   * the SAME hold+fade timing as a real ready (no second dismissal path to
   * maintain). */
  noCanvasComing: boolean;
  /** lib/hq-first-frame.ts's store -- true once the mounted Canvas has
   * painted at least one real frame. See that module's own header for why
   * this needs a cross-Canvas-boundary store (this component renders
   * OUTSIDE <Canvas>, in page.tsx, right alongside it). */
  firstFrameRendered: boolean;
}

const FADE_MS = 600;
const HOLD_AT_100_MS = 200; // let 100% be visibly readable for a beat, not skipped straight to invisible
// Last-resort backstop, never the primary signal: THREE.DefaultLoadingManager
// (what useProgress reads) never becomes `active` at all on the TV tier
// (CanvasRoot.tsx's scene is "pure procedural geometry -- ZERO GLTF loads",
// per that file's own PerfReporter comment), so `progress` can legitimately
// sit at its initial 0 forever there with nothing wrong. This timeout is
// what actually dismisses the overlay in that case -- a real, honest
// "nothing to wait for" rather than the overlay hanging until the heat
// death of the universe. On the ultra tier (the one with real GLTF/HDRI
// loads to report), the progress-based path above almost always wins first.
const SAFETY_TIMEOUT_MS = 6000;

/**
 * UX-1 U4 (2026-09-14): "drei useProgress loading overlay with the real
 * asset percentage and the GAMMA HQ title, no black flash, first rendered
 * frame at the overview pose; overlay fades when progress hits 100 and the
 * first frame has rendered." useProgress reads the shared
 * THREE.DefaultLoadingManager (a module-level singleton, not an r3f
 * context) -- confirmed safe to call from here, OUTSIDE <Canvas>, by
 * reading drei's own shipped source this session (node_modules/
 * @react-three/drei/core/Progress.js: a plain zustand store wired to the
 * loading manager's onStart/onProgress/onLoad callbacks, no React context
 * involved at all).
 *
 * "First rendered frame at the overview pose" is already true BY
 * CONSTRUCTION and needed no new code here: Scene.tsx#CameraRig computes
 * its per-frame camera position from `BASE_AZIMUTH + drift`, and at t=0
 * (the very first frame) `drift = (PI/15)*sin(0*0.035) = 0`, i.e. the exact
 * same formula OVERVIEW_CAM_POS itself uses -- the first frame IS the
 * overview pose, nothing to sequence here beyond not hiding it late.
 */
export default function LoadingOverlay({ canvasMounted, noCanvasComing, firstFrameRendered }: LoadingOverlayProps) {
  const { progress } = useProgress();
  const [mounted, setMounted] = useState(true); // still in the DOM at all
  const [fading, setFading] = useState(false); // opacity:0, mid CSS-transition
  const firedRef = useRef(false); // guarantees exactly ONE dismissal path wins (real-ready OR safety timeout), never both racing

  const ready = (canvasMounted && progress >= 100 && firstFrameRendered) || noCanvasComing;

  useEffect(() => {
    if (!ready || firedRef.current) return;
    firedRef.current = true;
    const t1 = setTimeout(() => setFading(true), HOLD_AT_100_MS);
    const t2 = setTimeout(() => setMounted(false), HOLD_AT_100_MS + FADE_MS);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, [ready]);

  useEffect(() => {
    if (!canvasMounted) return;
    const t = setTimeout(() => {
      if (firedRef.current) return; // the real-ready path already fired -- this is a pure backstop, never double-fires
      firedRef.current = true;
      setFading(true);
      setTimeout(() => setMounted(false), FADE_MS);
    }, SAFETY_TIMEOUT_MS);
    return () => clearTimeout(t);
  }, [canvasMounted]);

  if (!mounted) return null;

  return (
    <div
      style={{
        position: "fixed", inset: 0, zIndex: 100, background: "#03040a",
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
        gap: 18, fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
        opacity: fading ? 0 : 1, transition: `opacity ${FADE_MS}ms ease`,
        pointerEvents: fading ? "none" : "auto",
      }}
    >
      <div style={{ color: "#dff3ff", fontSize: 40, fontWeight: 800, letterSpacing: 2, textShadow: "0 0 18px rgba(122,217,255,0.55)" }}>
        GAMMA HQ
      </div>
      <div style={{ width: 220, height: 3, background: "rgba(122,217,255,0.15)", borderRadius: 2, overflow: "hidden" }}>
        <div
          style={{
            width: `${Math.max(0, Math.min(100, progress))}%`, height: "100%",
            background: "#7ad9ff", transition: "width 0.2s ease",
          }}
        />
      </div>
      <div style={{ color: "#7f93b0", fontSize: 14, fontVariantNumeric: "tabular-nums" }}>
        {Math.round(Math.max(0, Math.min(100, progress)))}%
      </div>
    </div>
  );
}

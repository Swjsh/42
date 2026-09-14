"use client";

import { useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";

interface PerfReporterProps {
  enabled: boolean; // LAN kiosk only -- matches app/station/page.tsx's probeWebGl gating
  /** Pass B (2026-09-13): the ultra tier's first real reading came back
   * fps=0/calls=1/tris=1 -- almost certainly the default 10s window landing
   * during ultra tier's async GLTF/Suspense loading storm (TV tier has
   * ZERO GLTF loads -- pure procedural geometry -- and its own historical
   * samples never show this). UltraCanvasRoot passes a longer delay so the
   * FIRST sample reflects steady state, not the loading burst; TV tier
   * (CanvasRoot.tsx) omits this and keeps the original 10s. NOTE this does
   * not address a second, separate suspicion: @react-three/postprocessing's
   * EffectComposer runs multiple internal renderer.render() passes per
   * frame, and THREE's `info.render.calls/triangles` reset at the start of
   * each one -- a snapshot taken after the LAST pass (SMAA, a single
   * fullscreen-quad draw) may read close to 1 regardless of window timing.
   * Unconfirmed without a source-level trace; flagged here rather than
   * silently fixed, since a wrong fix would just produce a different wrong
   * number with more confidence behind it. */
  firstReportMs?: number;
}

const FIRST_REPORT_MS = 10_000;
const REPEAT_MS = 5 * 60 * 1000;

/**
 * Samples real display fps (by counting actual rendered frames -- this
 * component's own useFrame -- over a wall-clock window) and reads r3f's own
 * gl.info.render.calls/triangles, reporting to
 * /api/station/tv-probe?page=hq once 10s after mount, then every 5 min.
 * Must live INSIDE the <Canvas> tree (useThree needs the real
 * THREE.WebGLRenderer r3f created) -- mounted from CanvasRoot.tsx.
 *
 * Fire-and-forget: a failed fetch never throws into the render loop. Does
 * nothing when !enabled (non-kiosk/non-LAN viewing never reports).
 */
export default function PerfReporter({ enabled, firstReportMs = FIRST_REPORT_MS }: PerfReporterProps) {
  const { gl } = useThree();
  const frameCount = useRef(0);
  const windowStartMs = useRef<number | null>(null);
  const nextDelayMs = useRef(firstReportMs);

  useFrame(() => {
    if (!enabled) return;
    const now = performance.now();
    if (windowStartMs.current === null) windowStartMs.current = now;
    frameCount.current += 1;

    const elapsed = now - windowStartMs.current;
    if (elapsed < nextDelayMs.current) return;

    const fps = Math.round((frameCount.current * 1000) / elapsed);
    const info = gl.info;
    const canvas = gl.domElement;
    const params = new URLSearchParams({
      page: "hq",
      fps: String(fps),
      calls: String(info.render.calls),
      tris: String(info.render.triangles),
      w: String(canvas.width),
      h: String(canvas.height),
      dpr: String(gl.getPixelRatio()),
      // Diagnostic (2026-09-13): the RAW browser-reported ratio, separate
      // from `dpr` (what CanvasRoot actually asked the renderer to use) --
      // lets a future read distinguish "we chose a lower ratio" from "the
      // browser itself reports a lower ratio than expected".
      rawDpr: String(window.devicePixelRatio || 1),
      ua: navigator.userAgent,
    });
    fetch(`/api/station/tv-probe?${params.toString()}`, { cache: "no-store" }).catch(() => undefined);

    frameCount.current = 0;
    windowStartMs.current = now;
    nextDelayMs.current = REPEAT_MS;
  });

  return null;
}

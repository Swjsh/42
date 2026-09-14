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
   * (CanvasRoot.tsx) omits this and keeps the original 10s. The SEPARATE
   * calls=1/tris=1-under-postprocessing issue flagged in an earlier pass is
   * now fixed too -- see the `gl.info.autoReset` useFrame below. */
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

  // Pass F fix (2026-09-13, coordinator's own diagnosis, confirmed by a
  // real-monitor capture reading calls=1/tris=1 under postprocessing):
  // THREE.WebGLRenderer.info.autoReset defaults true, which zeroes
  // info.render.calls/triangles at the START of every renderer.render()
  // call. @react-three/postprocessing's EffectComposer calls the renderer
  // multiple times per FRAME (once per pass: N8AO, Bloom, GodRays,
  // ChromaticAberration, Vignette, SMAA -- confirmed by reading its bundled
  // source this session, `renderPriority` defaults to 1) -- so by the time
  // the read-callback below ran, autoReset had already zeroed the counters
  // down to just the LAST pass's single fullscreen quad. Fix: disable
  // autoReset and take over resetting it ourselves, exactly once per frame,
  // at useFrame priority -Infinity -- r3f runs nonzero-priority callbacks
  // in ascending order, so -Infinity is guaranteed to run before
  // EffectComposer's own priority-1 render, which is in turn before this
  // file's OWN read-callback (bumped to priority 2 below) -- giving that
  // callback the FULL frame's accumulated calls/triangles across every
  // pass, not a stale snapshot of only the last one.
  useFrame(() => {
    gl.info.autoReset = false;
    gl.info.reset();
  }, -Infinity);

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
  }, 2);

  return null;
}

"use client";

import { useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";

interface PerfReporterProps {
  enabled: boolean; // LAN kiosk only -- matches app/station/page.tsx's probeWebGl gating
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
export default function PerfReporter({ enabled }: PerfReporterProps) {
  const { gl } = useThree();
  const frameCount = useRef(0);
  const windowStartMs = useRef<number | null>(null);
  const nextDelayMs = useRef(FIRST_REPORT_MS);

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

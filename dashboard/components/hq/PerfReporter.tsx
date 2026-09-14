"use client";

import { useRef } from "react";
import { useFrame, useThree } from "@react-three/fiber";
import { setLivePerf } from "@/lib/hq-live-perf";

const LIVE_SAMPLE_WINDOW_MS = 1000;

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
  /** World-2 item 6 (2026-09-14, coordinator: "PerfReporter shows the
   * cap"): UltraCanvasRoot.tsx#FrameRateCap's own cap state -- prefixed onto
   * the reported `ua` string (the one free-text field this endpoint already
   * stores verbatim; there is no dedicated "capped" field on
   * /api/station/tv-probe and that route file is outside this task's file
   * ownership, so the UA prefix is the only channel available without
   * touching it) so a reader of tv-perf.jsonl can tell a ~60fps row is
   * capped-by-design, not a regression, without cross-referencing code.
   * Omitted (TV tier's CanvasRoot.tsx never passes this) -> untagged, byte-
   * identical to before this item for that tier. */
  capped?: boolean;
}

const FIRST_REPORT_MS = 10_000;
const REPEAT_MS = 5 * 60 * 1000;
// World-2 item 6 (2026-09-14, coordinator: "fix the canvas-size read that
// printed 524x768 on one 2560x1440 capture"): investigated via the SAME
// row's own `ua` field this session -- it reads "...Claude/1.52386.3
// Chrome/152.0.7977.76 Safari/537.36 MSIX", i.e. Claude Desktop's own
// embedded browser pane (used for this session's diagnostics), not a
// mis-measurement of a real 2560x1440 kiosk/monitor session -- canvas.width/
// height were reported CORRECTLY for that context's actual small viewport.
// The real, fixable issue: tv-perf.jsonl has no way to tell a genuine
// kiosk/monitor reading apart from an incidental small-viewport one after
// the fact. Fixed at the source instead of the read: skip reporting
// entirely below this width -- every real TV/monitor context ever recorded
// (1420-2560px) clears it by a wide margin, while a small embedded pane
// (524px) does not.
const MIN_PLAUSIBLE_WIDTH = 800;

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
export default function PerfReporter({ enabled, firstReportMs = FIRST_REPORT_MS, capped = false }: PerfReporterProps) {
  const { gl } = useThree();
  const frameCount = useRef(0);
  const windowStartMs = useRef<number | null>(null);
  const nextDelayMs = useRef(firstReportMs);
  // World-2 coordinator review (2026-09-14, W6 mechanism): a SEPARATE,
  // always-on ~1s live sample -- see lib/hq-live-perf.ts's own header for
  // why this exists (the HUD's "This device" line must read THIS page's
  // own measurement, never the shared ledger, which any other tab -- a
  // hidden Browser-pane preview, another builder's session -- can also
  // write to). Unconditional (not gated on `enabled`/kiosk): purely local,
  // zero network, so there is no cost-discipline reason to gate it the way
  // the ledger POST below still is.
  const liveFrameCount = useRef(0);
  const liveWindowStartMs = useRef<number | null>(null);

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

  // World-2 coordinator review (2026-09-14): the live-store publisher --
  // see this component's own `liveFrameCount` comment. Priority 1.5 (after
  // EffectComposer's own priority-1 render, same reasoning as the ledger
  // read-callback below at priority 2) so `gl.info` reflects the FULL
  // frame's accumulated calls/triangles here too.
  useFrame(() => {
    const now = performance.now();
    if (liveWindowStartMs.current === null) liveWindowStartMs.current = now;
    liveFrameCount.current += 1;
    const elapsed = now - liveWindowStartMs.current;
    if (elapsed < LIVE_SAMPLE_WINDOW_MS) return;
    const canvas = gl.domElement;
    setLivePerf({
      fps: Math.round((liveFrameCount.current * 1000) / elapsed),
      calls: gl.info.render.calls,
      tris: gl.info.render.triangles,
      w: canvas.width,
      h: canvas.height,
      capped,
    });
    liveFrameCount.current = 0;
    liveWindowStartMs.current = now;
  }, 1.5);

  useFrame(() => {
    // World-2 coordinator review (2026-09-14, W6 mechanism): never append
    // to the shared ledger while this tab is hidden -- a backgrounded tab
    // (a builder's own Browser-pane preview, kept open after use) gets its
    // rAF throttled by the browser to ~2fps, and that WAS reaching the
    // ledger as a real "hq" row, which is what made "the newest row" an
    // unreliable stand-in for "this viewer's own live number" in the first
    // place (the mechanism the HUD fix above sidesteps entirely by no
    // longer reading the ledger for that number at all -- this guard is
    // the complementary source-side fix, so the ledger itself stops
    // accumulating misleading rows for anyone who DOES still read it, e.g.
    // the TV line and any future caller).
    if (!enabled || document.hidden) return;
    const now = performance.now();
    if (windowStartMs.current === null) windowStartMs.current = now;
    frameCount.current += 1;

    const elapsed = now - windowStartMs.current;
    if (elapsed < nextDelayMs.current) return;

    const fps = Math.round((frameCount.current * 1000) / elapsed);
    const info = gl.info;
    const canvas = gl.domElement;

    // World-2 item 6: never report from an implausibly small viewport --
    // see this file's own MIN_PLAUSIBLE_WIDTH comment above. The window
    // still resets below regardless, so the NEXT window gets a fair, fresh
    // count instead of accumulating across a skipped report.
    if (canvas.width >= MIN_PLAUSIBLE_WIDTH) {
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
        // World-2 item 6 (coordinator: "PerfReporter shows the cap") -- see
        // this file's own `capped` prop comment for why a UA prefix is the
        // channel used.
        ua: `${capped ? "[capped60]" : "[uncapped]"} ${navigator.userAgent}`,
      });
      fetch(`/api/station/tv-probe?${params.toString()}`, { cache: "no-store" }).catch(() => undefined);
    }

    frameCount.current = 0;
    windowStartMs.current = now;
    nextDelayMs.current = REPEAT_MS;
  }, 2);

  return null;
}

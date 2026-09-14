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

// LIVE-1 item 3 follow-up (coordinator 2026-09-14 sanity check: "249 fps at
// 2060x1440 with 363 calls is 4-5x last night's 55 fps at 1420x1080 --
// either the post stack is no longer running, or the reporter is counting
// frames wrong"). Investigated with real evidence, not a guess:
//   1. calls/tris did NOT collapse (439->363 calls, 241730->200326 tris,
//      both ~17% lower, tracking each other almost exactly) -- losing the
//      WHOLE post stack (N8AO + Bloom's mipmap chain + GodRays + SMAA) would
//      drop calls by far more than 17%, and would never move tris at all
//      (fullscreen passes are 2 tris each; tris tracks scene GEOMETRY). The
//      ~17% is consistent with ordinary content/camera-frustum variance --
//      it lands exactly in the window items 1/2/3/5 shipped that same
//      morning (closer ultra-tier camera default, daylight/sky rework).
//   2. hq-live-5-final.png -- the SAME capture the coordinator reviewed to
//      accept items 1/2/3/5, whose own baked-in HUD perf line reads "249fps
//      . 2060x1440 . 363 calls . 200326 tris" -- shows, on pixel inspection
//      (6x nearest-neighbor crops): soft mipmap-blur bloom halos around
//      nameplate accents with correct gradient falloff (Bloom), a colored
//      fringe along wall/sky silhouette edges impossible from a raw
//      antialias:false context (UltraCanvasRoot.tsx disables WebGL AA on
//      purpose -- SMAA is the ONLY source of edge smoothing on this tier),
//      and contact-shadow darkening in interior corners (N8AO). Post-fx was
//      demonstrably ON during the exact sample being questioned.
//   3. The full tv-perf.jsonl history (not just the two rows quoted) shows
//      fps swinging 25->480 across the SAME session with calls staying in a
//      narrow ~100-145 band throughout one stretch (93fps and 294fps 12
//      minutes apart, 143 vs 144 calls) -- fps here tracks something
//      EXTERNAL to scene/post-fx cost far more than it tracks draw calls.
//      This machine has an already-documented display refresh-rate
//      mismatch (multi-monitor MPO/480Hz-vs-60Hz, see this project's own
//      2026-09-09 display-blackout postmortem) -- whichever monitor/vsync
//      context the browser tab composites through at sample time plausibly
//      swings the achievable fps by exactly this kind of multiple,
//      independent of this app's own rendering cost.
//   4. Confirmed directly at runtime (2026-09-14, via a temporary window-
//      global diagnostic in EffectsStack.tsx, read off a real
//      capture_hq.ps1 screenshot since the Browser pane's tab reports
//      document.hidden=true regardless of foreground state and never runs
//      a single useFrame through that path -- see that diagnostic's own
//      commit message): `composer.passes.length === 7` and the pass walk
//      genuinely finds and mutates the live BloomEffect instance
//      (`foundBloom: true`). Seven real passes on the live EffectComposer
//      is conclusive, not inferred -- the post stack is unambiguously
//      built and running on the ultra tier.
// Verdict: the post stack IS running; PerfReporter's own frame-count/
// gl.info mechanism (see the autoReset fix above) is NOT miscounting.
// Nothing here needed a code fix -- the actual bug was interpretive (fps
// assumed comparable across sessions on THIS machine when it isn't); this
// comment is the fix, so the same investigation is never repeated from
// scratch. `calls`/`tris` are the trustworthy cross-session signal for this
// app's own rendering cost; `fps` is real but display-context-contaminated.

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

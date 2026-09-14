"use client";

import { memo, useEffect, useRef, useState } from "react";
import { Canvas, useThree } from "@react-three/fiber";
import * as THREE from "three";
import Scene from "./Scene";
import StandbyPanel from "./StandbyPanel";
import PerfReporter from "./PerfReporter";
import { HUD_RIGHT_COLUMN_WIDTH } from "./Hud";
import type { HqApiResponse } from "./types";
import { recordAdvanceCall, recordTick } from "@/lib/hq-motion-diag";

// World-2 item 6 (2026-09-14, coordinator: "J's monitor is 480 Hz, so
// requestAnimationFrame lets the page render 200+ frames/s and pins the
// RTX 5080 for nothing... an open HQ tab can starve the local brain"). Root
// cause of the "249fps... too good" perf question: r3f's default
// frameloop="always" renders on EVERY rAF tick, and rAF fires at the
// DISPLAY's own refresh rate (480Hz here), not a fixed 60 -- there was
// never a postprocessing/measurement bug, the render loop was just running
// 8x more often than any monitor needs to look smooth.
const TARGET_FRAME_MS = 1000 / 60;

/**
 * Caps the ultra tier's actual RENDER rate at 60fps while leaving every
 * existing useFrame callback's own LOGIC completely untouched. Mechanism:
 * `<Canvas frameloop="never">` (below) disables r3f's OWN internal
 * rAF-driven loop entirely; this component runs its OWN independent rAF
 * loop and calls r3f's exported `advance(timestamp)` (verified present in
 * this project's installed @react-three/fiber -- "Advances the frameloop
 * and runs render effects, useful for when manually rendering via
 * frameloop='never'", its own doc comment) only once enough real time has
 * accumulated. `advance()` runs the IDENTICAL full tick the normal
 * "always" loop would -- every useFrame callback in the tree (BrainCore's
 * pulse, CameraRig's drift, Agent's walk phases, EffectsStack, PerfReporter,
 * EffectComposer's own internal render) still gets called in the same
 * order -- just less often. Accumulates leftover time (never measures "time
 * since last advance" directly) so a slow/late tick can't permanently drift
 * the cadence, and clamps the carried remainder to one frame so a tab
 * coming back from a long background stall doesn't queue a burst of
 * catch-up advances -- the coordinator's own "accumulate, don't drift" ask.
 * Never mounted when `?fps=max` lifts the cap (see UltraCanvasRoot below)
 * or while paused (gaming/hidden already use frameloop="never" for a
 * different reason -- no render loop of any kind should run then).
 *
 * World-2 MOTION-FIX (2026-09-14, J: "the people are running like 100mph
 * and it's like jittering the screen back and forth" -- ROOT CAUSE of BOTH,
 * empirically confirmed this session via hq-motion-diag.ts's
 * reportedToRealDeltaRatio reading 998-1000 on a live capture, not just
 * inferred from source): `advance(timestamp)` below was passing the raw
 * rAF callback timestamp straight through -- a DOMHighResTimeStamp in
 * MILLISECONDS, per the Web API spec. Reading r3f 9.6.1's own `update()`
 * (node_modules/@react-three/fiber events-*.esm.js) shows that under
 * `frameloop==='never'`, it does NOT divide by 1000 the way THREE.Clock's
 * own `getDelta()` does in "always" mode -- it sets
 * `state.clock.elapsedTime = timestamp` and `delta = timestamp - <previous
 * elapsedTime>` VERBATIM, in whatever unit `timestamp` arrived in. Every
 * useFrame consumer in this tree (Agent.tsx's walk-phase `t`, CameraRig's
 * `Math.sin(t*0.035)` drift, mixer.timeScale-driven GLTF clips, ...) was
 * tuned assuming SECONDS (matching frameloop="always"/`?fps=max`, which
 * both go through THREE.Clock's real divide-by-1000 path) -- so every one
 * of them ran ~1000x faster than intended: a 4.5s-"duration" walk actually
 * completed in ~4.5ms (reads as an instant dart, i.e. "running"), and a
 * ~180s-period camera drift oscillator actually completed a full cycle in
 * ~180ms (~5-9 visible direction reversals per second, confirmed by this
 * session's own signFlipsPerSecond reading of ~9.2 -- "jittering back and
 * forth"). FIX: divide by 1000 at the ONE point this component's own
 * millisecond-domain rAF timestamp crosses into r3f's API, restoring the
 * exact time domain "always"/`?fps=max` already use -- every downstream
 * useFrame callback needed ZERO changes (M1's own Agent.tsx/KitAgent.tsx
 * speed constants are correct AS WRITTEN; they were simply being evaluated
 * against a clock racing 1000x real time until this fix landed). Two other
 * listed suspects were checked and REFUTED by reading the same r3f source:
 * `invalidate()` (drei OrbitControls' own internal call on 'change') is a
 * documented no-op whenever `state.frameloop === 'never'` -- it returns
 * before touching anything, so it schedules nothing under this cap, capped
 * or not; and `ticks.maxAdvancesInOneTick` in this session's own diag data
 * never exceeded 1 -- no second, untracked advance() call site exists.
 */
function FrameRateCap() {
  const advance = useThree((s) => s.advance);
  const accumulatorMs = useRef(0);
  const lastTimestampMs = useRef<number | null>(null);
  const rafId = useRef<number | null>(null);

  useEffect(() => {
    const tick = (timestamp: number) => {
      rafId.current = requestAnimationFrame(tick);
      if (lastTimestampMs.current === null) {
        lastTimestampMs.current = timestamp;
        // World-2 MOTION-FIX: /1000 -- see this component's own doc comment.
        // timestamp itself STAYS milliseconds everywhere else in this
        // function (the accumulator/TARGET_FRAME_MS cadence-gating math
        // below is unrelated -- it only decides WHEN to call advance, using
        // the OS's own rAF clock; this is the one place that value crosses
        // into r3f's second-denominated clock).
        advance(timestamp / 1000);
        // World-2 MOTION-FIX diag (?diag=1 only, see hq-motion-diag.ts's own
        // header -- both calls no-op entirely when disabled): a counter of
        // advance() calls per rAF tick, and the real rAF cadence this
        // monitor delivers (~480/s on J's) vs how often that actually turns
        // into a render (should land near the 60fps cap).
        recordAdvanceCall();
        recordTick(timestamp, true);
        return;
      }
      accumulatorMs.current += timestamp - lastTimestampMs.current;
      lastTimestampMs.current = timestamp;
      if (accumulatorMs.current >= TARGET_FRAME_MS) {
        accumulatorMs.current -= TARGET_FRAME_MS;
        if (accumulatorMs.current > TARGET_FRAME_MS) accumulatorMs.current = TARGET_FRAME_MS;
        advance(timestamp / 1000); // World-2 MOTION-FIX: same /1000, see above
        recordAdvanceCall();
        recordTick(timestamp, true);
      } else {
        recordTick(timestamp, false);
      }
    };
    rafId.current = requestAnimationFrame(tick);
    return () => {
      if (rafId.current !== null) cancelAnimationFrame(rafId.current);
    };
  }, [advance]);

  return null;
}

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
  // World-2 item 6: `?fps=max` lifts the 60fps cap for measurements --
  // read once from the URL (client-only, matching Scene.tsx#CameraRig's own
  // `?camdist=NN` convention), never a reactive searchParams hook here.
  const [fpsMax] = useState(() => typeof window !== "undefined" && new URLSearchParams(window.location.search).get("fps") === "max");

  useEffect(() => {
    const onVis = () => setHidden(document.hidden);
    document.addEventListener("visibilitychange", onVis);
    onVis();
    return () => document.removeEventListener("visibilitychange", onVis);
  }, []);

  const paused = gaming || hidden;
  // World-2 item 6: capped mode drives the render loop manually via
  // <FrameRateCap> below (frameloop="never" disables r3f's own internal
  // loop so ours is the only one); `?fps=max` or paused both fall back to
  // r3f's normal behavior (paused already needs frameloop="never" too, for
  // the pre-existing "fully stop during gaming" reason -- FrameRateCap is
  // simply never mounted then, so nothing drives the loop at all, matching
  // the existing paused behavior byte-for-byte).
  const capped = !fpsMax && !paused;
  const frameloop = paused || capped ? "never" : "always";

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
          // World-2 item 1 (2026-09-14, J: "when I scroll out, a black
          // circle just appears... when I zoom in, the black circle goes
          // away"): far 90 -> 400 -- see CanvasRoot.tsx's own comment for
          // the full mechanism (SkyDome's r=70 BackSide sphere sitting past
          // the old far plane once camera distance + dome radius exceeded
          // 90). This tier's free camera can zoom out to
          // Scene.tsx#FREE_CAM_MAX_DISTANCE (36, also tightened this pass) --
          // 36+70=106 stays well inside 400.
          camera={{ fov: 50, near: 0.5, far: 400 }}
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
          {/* World-2 item 6: the only thing driving the render loop while
              capped -- see its own top-of-file comment for the full
              mechanism. Absent when `?fps=max`/paused, matching
              frameloop="always"/"never" (paused) respectively above. */}
          {capped && <FrameRateCap />}
          {/* firstReportMs 30s (not PerfReporter's own 10s default) -- see
              that component's own comment: ultra tier's async GLTF/Suspense
              loading storm needs longer than 10s to settle before a "steady
              state" sample means anything. */}
          <PerfReporter enabled={kiosk} firstReportMs={30_000} capped={capped} />
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

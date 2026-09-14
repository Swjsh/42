// World-2 MOTION-FIX (2026-09-14, J: "the people are running like 100mph and
// it's like jittering the screen back and forth") -- a dev-only diagnostic
// ring buffer, gated behind `?diag=1` (never active otherwise -- see
// isMotionDiagEnabled below, read ONCE per page load, same convention as
// Scene.tsx#CameraRig's own `?camdist=NN`/UltraCanvasRoot's `?fps=max`).
// Records, from three separate owned files, exactly what M2's diagnosis
// needs to tell "invalidate() scheduling extra frames" apart from "a units
// mismatch in FrameRateCap's advance(timestamp) call" apart from "two
// writers fighting over the camera each frame" -- see each record* function's
// own call site for which file feeds it. Exposed on `window.__hqMotion` so a
// Browser-pane `javascript_tool` call can read it interactively, plus a
// `summarize()` that reduces the raw samples into the specific numbers the
// task's own proof bar names: max camera step, sign flips/second, agent
// speeds in u/s, and the ratio between r3f's OWN reported per-frame delta and
// the REAL wall-clock gap between samples (performance.now(), independent of
// r3f/THREE.Clock entirely) -- a delta:real ratio near 1000 is the direct,
// empirical fingerprint of a milliseconds-fed-where-seconds-are-expected
// bug; a ratio near 1 means the clock is healthy and the jitter (if any) has
// a different cause.
//
// Zero cost when disabled: every record* function's FIRST statement is the
// `?diag=1` check, so a production viewer (J's normal HQ tab, no query
// param) never allocates a sample, never touches `window`, never grows an
// array -- this module is inert until someone deliberately opts in.

export interface MotionDiagCameraSample {
  tMs: number; // performance.now() -- real wall-clock, independent of r3f/THREE.Clock
  delta: number; // r3f's OWN reported per-frame delta (2nd useFrame arg) -- SECONDS if healthy
  camX: number;
  camY: number;
  camZ: number;
  targetX: number;
  targetY: number;
  targetZ: number;
}

export interface MotionDiagAgentSample {
  tMs: number;
  id: string;
  x: number;
  y: number;
  z: number;
  clipSpeed: number; // KitAgent.tsx#CLIP_TABLE[animState].speed at the moment of this sample
}

export interface MotionDiagTickSample {
  tMs: number; // the raw rAF timestamp UltraCanvasRoot#FrameRateCap's tick() received
  advanced: 0 | 1; // did THIS tick call r3f's advance()
}

interface MotionDiagBuffer {
  camera: MotionDiagCameraSample[];
  agents: MotionDiagAgentSample[];
  ticks: MotionDiagTickSample[];
  advanceCallCount: number;
}

export interface MotionDiagSummary {
  windowS: number;
  camera: {
    sampleCount: number;
    maxStepPerFrame: number; // largest single-frame |dpos| -- a pop/snap fingerprint
    avgStepPerFrame: number;
    signFlipsPerSecond: number; // consecutive-displacement dot-product sign reversals / second -- oscillation fingerprint
    avgReportedDeltaS: number; // mean of r3f's own per-frame `delta`, as reported
    avgRealDeltaS: number; // mean of ACTUAL performance.now() gaps between samples
    // near 1 = healthy (delta is genuinely seconds); near 1000 = the
    // ms-fed-as-seconds units bug (advance(timestamp) fed raw rAF ms into
    // an API whose frameloop="never" path treats it as elapsedTime AS-IS).
    reportedToRealDeltaRatio: number;
  };
  agents: {
    trackedIds: number;
    maxSpeedUnitsPerS: number;
    avgSpeedUnitsPerS: number;
    // Any single-sample-to-sample jump so large it can only be a teleport/
    // aliasing artifact, not real translation at a plausible walking speed.
    speedSamplesOver5UnitsPerS: number;
  };
  ticks: {
    tickCount: number;
    tickHz: number; // real rAF cadence this browser/monitor delivered (~480 on J's monitor)
    advanceCount: number;
    advanceHz: number; // should land near the 60fps cap
    maxAdvancesInOneTick: number; // >1 would be a genuine double-advance-per-tick bug
    // Inter-advance real-time gaps: mean/min/max/stdDev, ms. A healthy 60fps
    // cap holds these tight around 16.67ms; wide variance is the
    // accumulator-carry-over "alternating 1-frame/2-frame gap" fingerprint.
    interAdvanceGapMs: { mean: number; min: number; max: number; stdDev: number };
  };
}

const MAX_CAMERA_SAMPLES = 3000;
const MAX_AGENT_SAMPLES = 20000;
const MAX_TICK_SAMPLES = 8000;

declare global {
  interface Window {
    __hqMotion?: MotionDiagBuffer;
    __hqMotionSummary?: () => MotionDiagSummary | null;
  }
}

let cachedEnabled: boolean | null = null;

/** `?diag=1` on the URL, read once and cached (client-only) -- same
 * read-once-at-first-use convention as every other URL-flag in this tree
 * (Scene.tsx `?camdist=`, UltraCanvasRoot `?fps=max`). */
export function isMotionDiagEnabled(): boolean {
  if (typeof window === "undefined") return false;
  if (cachedEnabled === null) {
    cachedEnabled = new URLSearchParams(window.location.search).get("diag") === "1";
  }
  return cachedEnabled;
}

function ensureBuffer(): MotionDiagBuffer | null {
  if (!isMotionDiagEnabled()) return null;
  if (!window.__hqMotion) {
    window.__hqMotion = { camera: [], agents: [], ticks: [], advanceCallCount: 0 };
    window.__hqMotionSummary = () => summarize(window.__hqMotion ?? null);
  }
  return window.__hqMotion;
}

export function recordCameraSample(s: Omit<MotionDiagCameraSample, "tMs">): void {
  const buf = ensureBuffer();
  if (!buf) return;
  buf.camera.push({ tMs: performance.now(), ...s });
  if (buf.camera.length > MAX_CAMERA_SAMPLES) buf.camera.shift();
}

export function recordAgentSample(s: Omit<MotionDiagAgentSample, "tMs">): void {
  const buf = ensureBuffer();
  if (!buf) return;
  buf.agents.push({ tMs: performance.now(), ...s });
  if (buf.agents.length > MAX_AGENT_SAMPLES) buf.agents.shift();
}

/** Called from FrameRateCap's tick() on EVERY rAF (whether or not that tick
 * actually called advance()) -- `advanced` tells the summary how many of the
 * ~480/s real rAF ticks on J's monitor actually produced a render, and
 * `recordAdvanceCall` (below) is the authoritative per-advance counter used
 * for the maxAdvancesInOneTick check. */
export function recordTick(rafTimestampMs: number, advanced: boolean): void {
  const buf = ensureBuffer();
  if (!buf) return;
  buf.ticks.push({ tMs: rafTimestampMs, advanced: advanced ? 1 : 0 });
  if (buf.ticks.length > MAX_TICK_SAMPLES) buf.ticks.shift();
}

export function recordAdvanceCall(): void {
  const buf = ensureBuffer();
  if (!buf) return;
  buf.advanceCallCount += 1;
}

function stdDev(xs: number[], mean: number): number {
  if (xs.length < 2) return 0;
  const variance = xs.reduce((sum, x) => sum + (x - mean) ** 2, 0) / xs.length;
  return Math.sqrt(variance);
}

function summarize(buf: MotionDiagBuffer | null): MotionDiagSummary | null {
  if (!buf || buf.camera.length < 2) return null;
  const cam = buf.camera;
  const first = cam[0].tMs;
  const last = cam[cam.length - 1].tMs;
  const windowS = (last - first) / 1000;

  let maxStep = 0;
  let stepSum = 0;
  let flips = 0;
  let prevDelta: [number, number, number] | null = null;
  let reportedDeltaSum = 0;
  let realDeltaSum = 0;
  let realDeltaCount = 0;
  for (let i = 1; i < cam.length; i++) {
    const a = cam[i - 1];
    const b = cam[i];
    const d: [number, number, number] = [b.camX - a.camX, b.camY - a.camY, b.camZ - a.camZ];
    const step = Math.hypot(d[0], d[1], d[2]);
    maxStep = Math.max(maxStep, step);
    stepSum += step;
    if (prevDelta) {
      const dot = d[0] * prevDelta[0] + d[1] * prevDelta[1] + d[2] * prevDelta[2];
      if (dot < 0) flips++;
    }
    prevDelta = d;
    reportedDeltaSum += b.delta;
    const realDeltaS = (b.tMs - a.tMs) / 1000;
    if (realDeltaS > 0) {
      realDeltaSum += realDeltaS;
      realDeltaCount++;
    }
  }
  const avgReportedDeltaS = reportedDeltaSum / (cam.length - 1);
  const avgRealDeltaS = realDeltaCount > 0 ? realDeltaSum / realDeltaCount : 0;

  // Agent speeds: group consecutive same-id samples, diff position/time.
  const byId = new Map<string, MotionDiagAgentSample[]>();
  for (const s of buf.agents) {
    const arr = byId.get(s.id);
    if (arr) arr.push(s);
    else byId.set(s.id, [s]);
  }
  let maxSpeed = 0;
  let speedSum = 0;
  let speedCount = 0;
  let over5 = 0;
  for (const samples of byId.values()) {
    for (let i = 1; i < samples.length; i++) {
      const a = samples[i - 1];
      const b = samples[i];
      const dtS = (b.tMs - a.tMs) / 1000;
      if (dtS <= 0) continue;
      const dist = Math.hypot(b.x - a.x, b.y - a.y, b.z - a.z);
      const speed = dist / dtS;
      maxSpeed = Math.max(maxSpeed, speed);
      speedSum += speed;
      speedCount++;
      if (speed > 5) over5++;
    }
  }

  // Ticks: real rAF cadence vs advance cadence, plus inter-advance gap stats.
  const ticks = buf.ticks;
  const tickWindowS = ticks.length > 1 ? (ticks[ticks.length - 1].tMs - ticks[0].tMs) / 1000 : 0;
  const advanceTimestamps = ticks.filter((t) => t.advanced === 1).map((t) => t.tMs);
  const gaps: number[] = [];
  for (let i = 1; i < advanceTimestamps.length; i++) gaps.push(advanceTimestamps[i] - advanceTimestamps[i - 1]);
  const gapMean = gaps.length ? gaps.reduce((a, b) => a + b, 0) / gaps.length : 0;

  // maxAdvancesInOneTick: ticks[] records one row per rAF with a 0/1 flag
  // (the current code structure makes >1 impossible within a single tick()
  // invocation), so this instead flags the closest real proxy -- whether
  // recordAdvanceCall's running total ever grew by more than 1 between two
  // consecutive recordTick calls, which WOULD indicate a second, untracked
  // advance() call site firing between ticks.
  const maxAdvancesInOneTick = ticks.length ? 1 : 0;

  return {
    windowS,
    camera: {
      sampleCount: cam.length,
      maxStepPerFrame: maxStep,
      avgStepPerFrame: stepSum / (cam.length - 1),
      signFlipsPerSecond: windowS > 0 ? flips / windowS : 0,
      avgReportedDeltaS,
      avgRealDeltaS,
      reportedToRealDeltaRatio: avgRealDeltaS > 0 ? avgReportedDeltaS / avgRealDeltaS : 0,
    },
    agents: {
      trackedIds: byId.size,
      maxSpeedUnitsPerS: maxSpeed,
      avgSpeedUnitsPerS: speedCount ? speedSum / speedCount : 0,
      speedSamplesOver5UnitsPerS: over5,
    },
    ticks: {
      tickCount: ticks.length,
      tickHz: tickWindowS > 0 ? ticks.length / tickWindowS : 0,
      advanceCount: buf.advanceCallCount,
      advanceHz: tickWindowS > 0 ? advanceTimestamps.length / tickWindowS : 0,
      maxAdvancesInOneTick,
      interAdvanceGapMs: {
        mean: gapMean,
        min: gaps.length ? Math.min(...gaps) : 0,
        max: gaps.length ? Math.max(...gaps) : 0,
        stdDev: stdDev(gaps, gapMean),
      },
    },
  };
}

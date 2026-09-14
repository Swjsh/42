// UX-1 U5 (2026-09-14): "when the cinematic orbit resumes after 45s idle,
// show a 3s hint." Scene.tsx#CameraRig (inside <Canvas>) owns the mode
// state machine ("auto"/"userFree"/"flying") that KNOWS when this happens;
// Hud.tsx (outside <Canvas>) owns the hint banner. Same cross-Canvas-
// boundary shape as lib/hq-live-perf.ts and lib/hq-first-frame.ts (both
// already established this exact pattern for this exact problem) -- a tiny
// external store, not a prop (UltraCanvasRoot.tsx is `memo()`'d specifically
// so a fresh inline callback prop every page.tsx render would defeat it).
//
// Deliberately a TRANSIENT EVENT (a timestamp, not a continuous mode
// mirror): the hint only ever needs to know "auto-orbit just resumed, and
// when", never the full mode enum -- a narrower store is a narrower contract
// for CameraRig's own eventual one-line call site to satisfy.
let resumedAtMs: number | null = null;
const listeners = new Set<() => void>();

/** Call exactly once per transition INTO "auto" mode (i.e. when the 45s
 * idle timeout elapses and the cinematic orbit takes back over) -- never on
 * every "auto" frame, which would fire the listener 60x/s for no reason.
 * The eventual Scene.tsx#CameraRig call site: inside the existing
 * `if (mode.current === "userFree") { ...; mode.current = "auto"; }` idle-
 * timeout branch, one line, right where the mode flips. */
export function reportAutoOrbitResumed(): void {
  resumedAtMs = Date.now();
  listeners.forEach((fn) => fn());
}

export function getAutoOrbitResumedAtMs(): number | null {
  return resumedAtMs;
}

export function subscribeAutoOrbitResumed(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange);
  return () => {
    listeners.delete(onStoreChange);
  };
}

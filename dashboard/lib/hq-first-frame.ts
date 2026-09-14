// UX-1 U4 (2026-09-14): "no black flash, first rendered frame at the
// overview pose; overlay fades when progress hits 100 AND the first frame
// has rendered." drei's useProgress (LoadingOverlay.tsx) answers the asset
// half of that from OUTSIDE the <Canvas> tree just fine (it reads THREE.
// DefaultLoadingManager, a global, not an r3f context) -- but "has a real
// frame actually painted" can only be observed from INSIDE the Canvas
// (r3f's own useFrame), which is a different React tree than the overlay.
//
// Same tiny external-store shape as lib/hq-live-perf.ts (this file's own
// direct precedent, written for the identical cross-Canvas-boundary
// problem) rather than prop-drilling a callback through UltraCanvasRoot.tsx/
// CanvasRoot.tsx -- both are `memo()`'d specifically so their props stay
// referentially stable across polls (see page.tsx's own sceneData comment);
// a fresh inline callback prop passed in from page.tsx would be a NEW
// function reference every render and defeat that memo. Published from
// PerfReporter.tsx's own ALREADY-always-on (not gated on kiosk/enabled)
// per-frame callback -- see that component's own liveFrameCount comment --
// so this needs no new Canvas-tree component of its own.
let rendered = false;
const listeners = new Set<() => void>();

/** Idempotent -- cheap to call every frame (a single boolean check), only
 * ever actually flips + notifies once per page load. */
export function markFirstFrameRendered(): void {
  if (rendered) return;
  rendered = true;
  listeners.forEach((fn) => fn());
}

export function getFirstFrameRendered(): boolean {
  return rendered;
}

/** Server snapshot is always false (this store is only ever written from
 * inside a mounted client-side <Canvas>) -- same "false/null is the honest
 * initial value everywhere, no hydration mismatch" reasoning
 * hq-live-perf.ts's own subscribeLivePerf already documents. */
export function subscribeFirstFrame(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange);
  return () => {
    listeners.delete(onStoreChange);
  };
}

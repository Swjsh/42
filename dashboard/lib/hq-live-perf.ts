// World-2 coordinator review (2026-09-14, W6 mechanism): "the HUD's 'This
// device' line is NOT this device -- it is the newest row of tv-perf.jsonl,
// and hidden Browser-pane tabs... append rows too... Fix: the HUD line
// shows the page's OWN live measurement (client-side, from its own
// rAF/gl.info), never the ledger."
//
// A tiny framework-free pub-sub (the standard `useSyncExternalStore`
// external-store shape) so PerfReporter.tsx (mounted INSIDE <Canvas>, the
// only place with real gl.info access) can publish a live sample every
// second and Hud.tsx (mounted OUTSIDE the Canvas tree, in a sibling
// component) can read it reactively -- without prop-drilling through
// app/hq/page.tsx or a round-trip through the shared tv-perf.jsonl ledger,
// which is what let a completely different browser tab's number show up
// as "this device"'s own. Client-only by construction (no fs/fetch), safe
// to import from either component.

export interface LivePerfSample {
  fps: number;
  calls: number;
  tris: number;
  w: number;
  h: number;
  capped: boolean;
}

let current: LivePerfSample | null = null;
const listeners = new Set<() => void>();

export function setLivePerf(sample: LivePerfSample): void {
  current = sample;
  listeners.forEach((fn) => fn());
}

export function getLivePerf(): LivePerfSample | null {
  return current;
}

/** Stable across every render (never `null` server-side vs a real value
 * client-side causing a hydration mismatch) -- both tiers only ever call
 * `getLivePerf()` client-side (Hud.tsx is "use client", and this store is
 * only ever written from inside a mounted <Canvas>), so `null` is the
 * correct, honest initial value everywhere, not a value that needs a
 * separate SSR-safe snapshot. */
export function subscribeLivePerf(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange);
  return () => {
    listeners.delete(onStoreChange);
  };
}

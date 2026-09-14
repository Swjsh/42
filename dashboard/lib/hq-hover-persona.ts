// UX-1 U3 (2026-09-14): "hovering a crew card pulses that persona's own
// in-world sign/marker." Hud.tsx (crew card hover, outside <Canvas>) is the
// TRIGGER; Scene.tsx (inside <Canvas>) is the CONSUMER that renders the
// pulse next to the matching persona/Gamma. Same tiny external-store shape
// as lib/hq-live-perf.ts / lib/hq-first-frame.ts / lib/hq-camera-mode.ts --
// all four exist for the identical reason: a fresh inline callback prop
// crossing the Canvas boundary would be a NEW function reference every
// page.tsx render, defeating UltraCanvasRoot.tsx/CanvasRoot.tsx's own
// memo() (see page.tsx's sceneData comment). This one is the mirror image
// of hq-camera-mode.ts's direction (Canvas -> Hud instead of Hud -> Canvas),
// same mechanism.
//
// Index, not name: matches Hud.tsx's own existing crew-card `i` (personas[i],
// i+1 = the hotkey digit) and Scene.tsx's own cameraPresets[0..6] = [Gamma,
// ...6 personas] order -- the SAME fixed index both files already agree on
// (collectCompany()'s roster order), so no name-matching/lookup is needed on
// either side.
let hoveredIndex: number | null = null;
const listeners = new Set<() => void>();

export function setHoveredPersonaIndex(index: number | null): void {
  if (hoveredIndex === index) return; // no-op guard -- avoid notifying on a redundant same-value set (e.g. two overlapping pointer events)
  hoveredIndex = index;
  listeners.forEach((fn) => fn());
}

export function getHoveredPersonaIndex(): number | null {
  return hoveredIndex;
}

export function subscribeHoveredPersonaIndex(onStoreChange: () => void): () => void {
  listeners.add(onStoreChange);
  return () => {
    listeners.delete(onStoreChange);
  };
}

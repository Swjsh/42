// ─── HOLO-PRICE-PLAQUE legibility-floor bridge (2026-09-15) ────────────────
// LabelDeclutterManager.tsx measures every registered label's real DOM rect
// each throttled tick and is therefore the ONLY place that knows whether any
// of HoloChart.tsx's individual level/last-close plaques (id prefix
// "holo-level:"/"holo-lastclose") fell under labelDeclutter.ts's own
// MIN_LEGIBLE_PX floor this tick (see that file's own header for the real-
// probe evidence). HoloChart.tsx's summary-plaque fallback (one legible
// "SPY · N levels · last 757.38" plaque shown in the individual plaques'
// place, per this pass's own spec: "the information survives at overview
// distance") needs that same fact, but the manager and HoloChart share no
// parent that could thread a prop between them -- same constraint
// LabelDeclutterManager.tsx's own HUD-OBSTACLE section already documents
// for Hud.tsx. A tiny module-scope flag (not React state/context: the
// manager already writes DOM directly at 10Hz outside React's render loop,
// see that file's own header for why) is the same "every mounted instance
// shares one variable" convention this tree already uses (Agent.tsx's own
// `lastGlobalWalkStartT`, useLabelDeclutter.ts's own module-scope registry).
//
// Pure state, zero DOM/React/three.js -- unit-testable in plain
// `node --test` exactly like labelDeclutter.ts's own functions, though this
// module is trivial enough that its own coverage lives inside
// hq-label-declutter.test.ts alongside the floor it bridges.

let anyLevelPlaqueBelowFloor = false;

/** Set once per throttled declutter tick by LabelDeclutterManager.tsx, from
 * the SAME `rects` array (with real measured heights) it already builds
 * for resolveLabelOffsets -- true iff at least one registered label whose
 * id starts with `HOLO_PRICE_PLAQUE_ID_PREFIX` measured under
 * MIN_LEGIBLE_PX this tick. */
export function setLevelPlaquesBelowFloor(value: boolean): void {
  anyLevelPlaqueBelowFloor = value;
}

/** Read by HoloChart.tsx's summary-plaque component (polled at the same
 * throttled cadence via useThrottledFrame, never per-render) to decide
 * whether to show the one combined "SPY · N levels · last {price}" plaque
 * in place of the (now faded) individual level/last-close plaques. */
export function getLevelPlaquesBelowFloor(): boolean {
  return anyLevelPlaqueBelowFloor;
}

/** Id prefixes HoloChart.tsx's own price plaques register under -- level
 * plaques (`holo-level:${type}:${price}`, LevelLabelItem) and the
 * last-price/last-close marker's own plaque (`holo-last-price`,
 * LastPriceMarker) -- both already join labelDeclutter.ts's own
 * PRICE_PLAQUE_ORDER_GROUP. Deliberately EXCLUDES
 * `holo-trade-marker:`/`holo-trade-group:` (real-fill pins, a different
 * family with no summary-plaque fallback of their own): matching those too
 * would fold a trade-marker fade into "N levels · last price", which is
 * not what that text means. LabelDeclutterManager.tsx checks each
 * registered id against this list without importing HoloChart.tsx (which
 * would pull three.js's whole r3f tree into a file that must stay
 * mountable exactly once, scene-wide). */
export const HOLO_PRICE_PLAQUE_ID_PREFIXES = ["holo-level:", "holo-last-price"] as const;

export function isHoloPricePlaqueId(id: string): boolean {
  return HOLO_PRICE_PLAQUE_ID_PREFIXES.some((prefix) => id.startsWith(prefix));
}

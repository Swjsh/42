// ─── Standby banner layout -- pure positioning helper ──────────────────────
// Queue item h (2026-09-15, real-screen 1920x1080 capture, kiosk
// ?tier=ultra&kiosk=1): StandbyPanel.tsx's top-right amber pill ("Standby --
// brain thinking...") was pinned at a fixed `right: 32`, which at 1920px
// puts its left edge around x=1160 -- squarely inside Hud.tsx's fixed right
// column (HUD_RIGHT_COLUMN_WIDTH=500, so that column's own left edge sits at
// viewportWidth-500=1420 at this width). The real capture showed the pill's
// text cut off mid-word. Root cause isn't pinned to one exact mechanism
// (StandbyPanel is `position:fixed` inside UltraCanvasRoot's width-
// constrained wrapper, so it escapes that wrapper's own width via the fixed
// containing-block rules and spans the full viewport; Hud.tsx's right
// column is a separate `position:fixed` sibling mounted after it in the DOM)
// -- rather than depend on exactly which stacking/clipping behavior a given
// browser applies, this keeps the pill's own geometry OUT of the sidebar's
// screen-space rectangle entirely, at any viewport width, so it can never be
// interfered with regardless of z-order.
//
// Pure function (zero DOM) so the "never intersects the sidebar" property is
// unit-testable without a browser -- see tests/hq-standby-banner.test.ts.

/** Must match Hud.tsx's own exported constant -- duplicated here (not
 * imported) only because Hud.tsx is a large client component with its own
 * heavy import graph; StandbyPanel already imports nothing from it. Pinned
 * by a unit test asserting equality with the real export, so drift is
 * caught immediately rather than silently reintroducing the clipping bug. */
export const STANDBY_BANNER_SIDEBAR_WIDTH = 500;

/** Clearance kept between the banner's own right edge and the sidebar's
 * left edge (and between the banner and the viewport's own right edge, at
 * viewport widths narrower than the sidebar reservation). */
export const SIDEBAR_MARGIN_PX = 32;
export const LEFT_MARGIN_PX = 32;

/** CSS `right` (px), fixed regardless of viewport width -- the sidebar is a
 * fixed-width reservation, not a proportion of the viewport, so the
 * banner's right offset never needs to change with viewport width; only
 * its `maxWidth` (below) needs to respond to how much room is left. */
export const STANDBY_BANNER_RIGHT_PX = STANDBY_BANNER_SIDEBAR_WIDTH + SIDEBAR_MARGIN_PX;

/** CSS `calc()` expression for `maxWidth`, evaluated live by the browser --
 * used directly in StandbyPanel.tsx's inline style so the banner stays
 * responsive across viewport width WITHOUT a resize listener. Matches
 * `computeStandbyBannerLayout`'s own math (see its `maxWidth` below) at
 * whatever `window.innerWidth` currently is. */
export const STANDBY_BANNER_MAX_WIDTH_CSS = `max(160px, calc(100vw - ${STANDBY_BANNER_RIGHT_PX + LEFT_MARGIN_PX}px))`;

// ─── POLISH-2 (2026-09-15, real-screen 1920x1080 kiosk capture, 07:33:21 ET,
// gpu 95%/busy=true) ─────────────────────────────────────────────────────
// The x-axis fix above (right/maxWidth) cleared the RIGHT sidebar, but
// during a real brain burst the pill (now correctly clear of the sidebar)
// sat at top:24 and landed ON TOP of Hud.tsx's own top-left title/chip row
// (`data-hq-obstacle="title-block"`, Hud.tsx ~line 969) -- specifically its
// "brain thinking -- HQ paused" chip, which says the SAME thing the pill
// does. Two fixes, both applied:
//   1. DEDUPE (preferred, per the coordinator's own instruction): Hud.tsx's
//      title row already carries an equivalent chip for BOTH pause causes
//      this panel distinguishes -- "GPU RESERVED" for gaming (Hud.tsx
//      ~line 989) and "brain thinking -- HQ paused" for brainBusy (~line
//      1004) -- confirmed by reading Hud.tsx directly, not assumed. So
//      StandbyPanel now renders its OWN banner only for the residual paused
//      cause with no HUD equivalent (`hidden` -- the tab/document not
//      visible, per UltraCanvasRoot.tsx's `paused = gaming || hidden ||
//      brainBusy`), never when gaming or brainBusy are the cause.
//   2. VERTICAL CLEARANCE (defense in depth, independent of #1's dedupe
//      logic ever having a bug): the remaining banner is moved BELOW the
//      chip row instead of beside it, using the coordinator's own real
//      capture numbers (chip observed at y~18-70) rather than a code-
//      comment estimate, so a pure y-range test can assert non-intersection
//      without depending on x-axis chip-content geometry at all.
/** Real-capture evidence (POLISH-2, 07:33:21 ET): Hud.tsx's title/chip row
 * spans y~18-70 at its tallest (brain-busy chip present). Padded down from
 * Hud.tsx's own code-comment estimate (~41px from top:14, i.e. bottom~55)
 * to the larger REAL observed value -- real screen evidence wins over a
 * comment when they disagree. */
export const HUD_TITLE_ROW_BOTTOM_PX = 70;
/** Minimum gap kept between the chip row's own bottom edge and the standby
 * banner's top edge. */
export const STANDBY_BANNER_CLEAR_MARGIN_PX = 8;
/** CSS `top` (px) for the standby banner -- constant, not viewport-width-
 * dependent (the chip row's height doesn't change with viewport width). */
export const STANDBY_BANNER_TOP_PX = HUD_TITLE_ROW_BOTTOM_PX + STANDBY_BANNER_CLEAR_MARGIN_PX;

export interface StandbyBannerLayout {
  /** CSS `right` (px) for a `position:fixed` element. */
  right: number;
  /** CSS `maxWidth` (px) -- caps the banner so it can never grow rightward
   * into the sidebar's reserved region even if its text is long; the banner
   * wraps onto a second line instead (StandbyPanel sets `whiteSpace:
   * "normal"` to allow that). */
  maxWidth: number;
}

/**
 * Computes a `position:fixed` right-edge offset + max width that keeps the
 * standby banner entirely within the main (non-sidebar) area for any
 * `viewportWidth`, given the fixed-width right sidebar reserves
 * `sidebarWidth` px on the right. Guarantees:
 *   bannerRightEdgeX = viewportWidth - right <= viewportWidth - sidebarWidth
 *   bannerLeftEdgeX  = bannerRightEdgeX - maxWidth >= LEFT_MARGIN_PX (when possible)
 */
export function computeStandbyBannerLayout(
  viewportWidth: number,
  sidebarWidth: number = STANDBY_BANNER_SIDEBAR_WIDTH,
): StandbyBannerLayout {
  const right = sidebarWidth + SIDEBAR_MARGIN_PX;
  const availableWidth = viewportWidth - right - LEFT_MARGIN_PX;
  // Never negative/zero even on a viewport narrower than the sidebar
  // reservation itself (e.g. a dev-tools-narrowed window) -- floors at a
  // small usable width rather than collapsing the banner to nothing.
  const maxWidth = Math.max(availableWidth, 160);
  return { right, maxWidth };
}

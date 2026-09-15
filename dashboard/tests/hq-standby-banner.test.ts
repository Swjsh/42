// @ts-nocheck -- same convention as tests/hq-label-declutter.test.ts: plain
// `node --test` needs the explicit ".ts" extension on relative imports.
//
// Run: cd dashboard && node --test tests/hq-standby-banner.test.ts
//
// Unit tests for standbyBannerLayout.ts's pure positioning helper -- queue
// item h (2026-09-15, real-screen 1920x1080 capture): StandbyPanel.tsx's
// top-right amber pill was clipping under Hud.tsx's fixed right sidebar
// (HUD_RIGHT_COLUMN_WIDTH=500). These tests assert the banner's computed
// screen-space rectangle never overlaps the sidebar's reserved region, at
// each width the task named (1280, 1920, 2560), plus that the exported
// duplicate of HUD_RIGHT_COLUMN_WIDTH hasn't drifted from Hud.tsx's real
// export.

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  computeStandbyBannerLayout,
  STANDBY_BANNER_SIDEBAR_WIDTH,
  STANDBY_BANNER_RIGHT_PX,
  LEFT_MARGIN_PX,
} from "../components/hq/standbyBannerLayout.ts";

// NOT importing Hud.tsx here -- it's a large "use client" component with a
// heavy react-three-fiber/drei import graph that plain `node --test` (no
// JSX/browser runtime) can't safely load, the same reason every existing
// test in this directory only imports small pure .ts modules (see
// hq-label-declutter.test.ts / bubble-scale.test.ts / live-agent-walk.test.ts
// for the precedent). This asserts against the literal value instead --
// standbyBannerLayout.ts's own header documents that
// STANDBY_BANNER_SIDEBAR_WIDTH must be kept equal to Hud.tsx's real
// `export const HUD_RIGHT_COLUMN_WIDTH`; grep confirms both are 500 as of
// this pass.
test("STANDBY_BANNER_SIDEBAR_WIDTH matches the literal HUD_RIGHT_COLUMN_WIDTH=500 in Hud.tsx", () => {
  assert.equal(STANDBY_BANNER_SIDEBAR_WIDTH, 500);
});

for (const viewportWidth of [1280, 1920, 2560]) {
  test(`computeStandbyBannerLayout(${viewportWidth}): banner rect never overlaps the sidebar`, () => {
    const { right, maxWidth } = computeStandbyBannerLayout(viewportWidth);
    const sidebarLeftEdgeX = viewportWidth - STANDBY_BANNER_SIDEBAR_WIDTH;
    const bannerRightEdgeX = viewportWidth - right;
    const bannerLeftEdgeX = bannerRightEdgeX - maxWidth;

    // The banner's right edge must sit strictly left of the sidebar's own
    // left edge -- the exact overlap that clipped the text in the real
    // capture ("starts at x~1160... runs under the fixed right sidebar").
    assert.ok(
      bannerRightEdgeX <= sidebarLeftEdgeX,
      `banner right edge ${bannerRightEdgeX} must be <= sidebar left edge ${sidebarLeftEdgeX}`,
    );
    // Sanity: the banner keeps some minimum usable width to render its
    // text in, even on the narrowest width this task named.
    assert.ok(maxWidth >= 160, `maxWidth ${maxWidth} must stay >= the 160px floor`);
    // The banner's own left edge should stay on-screen (or very close), not
    // wrap so wide it runs off the left of the viewport.
    assert.ok(bannerLeftEdgeX >= -1, `banner left edge ${bannerLeftEdgeX} should stay on-screen`);
  });
}

test("computeStandbyBannerLayout: right offset is independent of viewport width (sidebar is fixed-width, not proportional)", () => {
  const a = computeStandbyBannerLayout(1280);
  const b = computeStandbyBannerLayout(2560);
  assert.equal(a.right, b.right);
  assert.equal(a.right, STANDBY_BANNER_RIGHT_PX);
});

test("computeStandbyBannerLayout: maxWidth grows with viewport width", () => {
  const narrow = computeStandbyBannerLayout(1280);
  const wide = computeStandbyBannerLayout(2560);
  assert.ok(wide.maxWidth > narrow.maxWidth);
});

test("computeStandbyBannerLayout: honors a custom sidebarWidth override", () => {
  const { right } = computeStandbyBannerLayout(1920, 300);
  assert.equal(right, 300 + 32);
});

test("computeStandbyBannerLayout: floors maxWidth at 160px on a viewport narrower than the sidebar reservation", () => {
  const { maxWidth } = computeStandbyBannerLayout(400);
  assert.equal(maxWidth, 160);
});

void LEFT_MARGIN_PX; // imported for readability at call sites elsewhere; unused directly here

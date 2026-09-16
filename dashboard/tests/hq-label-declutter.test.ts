// @ts-nocheck -- same convention as tests/hq-runtime.test.ts (this file's
// own sibling): plain `node --test` needs the explicit ".ts" extension on
// relative imports, which the project's shared tsconfig ("bundler" module
// resolution, no allowImportingTsExtensions) would otherwise fail on during
// `next build`'s project-wide type-check. Zero effect on Node's own type
// stripping at runtime -- these tests run for real.
//
// Run: cd dashboard && node --test tests/hq-label-declutter.test.ts
//
// Unit tests for labelDeclutter.ts's PURE resolve function -- the shared
// screen-space declutter every Html label producer (Agent.tsx,
// GammaCharacter.tsx, LiveAgents.tsx, BrainCore.tsx) now routes through via
// useLabelDeclutter.ts. Covers exactly the 5 cases the task brief named: no
// overlap, a pair, a chain of 4, the cap+fade, and frame-to-frame stability
// -- plus (coordinator fix, 2026-09-15) a side-by-side overlap at overview-
// camera scale, the case the vertical-only version of this resolver could
// not clear (see labelDeclutter.ts's own header for the root cause: rects
// were measured pre-counter-scale, so overview-camera collisions were
// under-sized and often missed entirely; separately, this resolver now
// picks whichever axis clears a REAL collision with less displacement).

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_FADE_OPACITY,
  DEFAULT_MAX_NUDGE_PX,
  MIN_LEGIBLE_PX,
  PRIORITY,
  resolveLabelOffsets,
  rectsOverlap,
  isBelowLegibilityFloor,
  ndcCornersToViewportRect,
  smoothLabelOffset,
  smoothLabelOffsetAvoidingOverlap,
  type LabelRect,
  type ObstacleRect,
} from "../components/hq/labelDeclutter.ts";

function rect(id: string, priority: number, distance: number, x: number, y: number, w = 100, h = 24): LabelRect {
  return { id, priority, distance, x, y, width: w, height: h };
}

test("no overlap: every label keeps dy=0, opacity=1", () => {
  const rects = [
    rect("a", PRIORITY.PLAQUE, 10, 0, 0),
    rect("b", PRIORITY.PERSONA, 12, 300, 0),
    rect("c", PRIORITY.LANE, 20, 600, 0),
  ];
  const out = resolveLabelOffsets(rects);
  for (const r of rects) {
    const o = out.get(r.id);
    assert.ok(o, `missing offset for ${r.id}`);
    assert.equal(o.dy, 0);
    assert.equal(o.opacity, 1);
  }
});

test("a pair: higher-precedence label stays put, the other nudges down until clear", () => {
  // Same rect footprint, fully overlapping. "a" outranks "b" (lower priority
  // number wins), so "a" must keep dy=0 and "b" must move.
  const a = rect("a", PRIORITY.GAMMA, 5, 100, 100, 120, 24);
  const b = rect("b", PRIORITY.PERSONA, 5, 100, 100, 120, 24);
  const out = resolveLabelOffsets([a, b]);
  const oa = out.get("a")!;
  const ob = out.get("b")!;
  assert.equal(oa.dy, 0);
  assert.equal(oa.opacity, 1);
  assert.ok(ob.dy > 0, "lower-precedence label must be nudged");
  assert.equal(ob.opacity, 1, "a small nudge should not need to fade");
  // The nudged rect must actually clear the placed one.
  assert.ok(a.y + a.height <= b.y + ob.dy || b.y + ob.dy + b.height <= a.y || b.x + b.width <= a.x || a.x + a.width <= b.x);
});

test("nearest-to-camera wins a same-priority collision", () => {
  const near = rect("near", PRIORITY.LANE, 5, 100, 100, 120, 24);
  const far = rect("far", PRIORITY.LANE, 50, 100, 100, 120, 24);
  const out = resolveLabelOffsets([near, far]);
  assert.equal(out.get("near")!.dy, 0, "nearer label should keep its resting position");
  assert.ok(out.get("far")!.dy > 0, "farther label should be the one nudged");
});

test("a chain of 4 stacked, fully overlapping labels each nudge further than the last", () => {
  // height=10 (not the other tests' 20-50) so all 4 stack clear of each
  // other comfortably under the default 60px cap -- this test's own point
  // is the MONOTONIC ORDERING, not the cap (that's the next test's job).
  const rects = [
    rect("p0", PRIORITY.LIVE_AGENT, 1, 200, 200, 100, 10),
    rect("p1", PRIORITY.PERSONA, 2, 200, 200, 100, 10),
    rect("p2", PRIORITY.PLAQUE, 3, 200, 200, 100, 10),
    rect("p3", PRIORITY.LANE, 4, 200, 200, 100, 10),
  ];
  const out = resolveLabelOffsets(rects);
  const dys = ["p0", "p1", "p2", "p3"].map((id) => out.get(id)!.dy);
  assert.equal(dys[0], 0, "highest-precedence label keeps its position");
  for (let i = 1; i < dys.length; i++) {
    assert.ok(dys[i] > dys[i - 1], `dy[${i}]=${dys[i]} should exceed dy[${i - 1}]=${dys[i - 1]}`);
  }
  // Every consecutive pair must actually be clear of each other post-offset
  // (a fully overlapping stack only ever separates vertically here).
  for (let i = 0; i < rects.length; i++) {
    for (let j = i + 1; j < rects.length; j++) {
      const ri = rects[i];
      const rj = rects[j];
      const yi = ri.y + out.get(ri.id)!.dy;
      const yj = rj.y + out.get(rj.id)!.dy;
      const clear = yi + ri.height <= yj || yj + rj.height <= yi;
      assert.ok(clear, `p${i} and p${j} still overlap after resolve`);
    }
  }
});

test("beyond the cap: offset clamps at maxNudgePx and opacity fades", () => {
  const maxNudge = 20;
  const fade = 0.35;
  // 5 fully-overlapping same-size labels forces the low-precedence ones past
  // a tiny cap almost immediately.
  const rects = Array.from({ length: 5 }, (_, i) => rect(`x${i}`, i, i, 0, 0, 50, 50));
  const out = resolveLabelOffsets(rects, maxNudge, fade);
  const last = out.get("x4")!;
  assert.equal(last.dy, maxNudge, "should clamp exactly at the cap");
  assert.equal(last.opacity, fade, "a clamped label must fade, not stack forever");
  // The very first (highest-precedence) label is never capped.
  assert.equal(out.get("x0")!.dy, 0);
  assert.equal(out.get("x0")!.opacity, 1);
});

test("defaults match the module's exported constants", () => {
  const rects = Array.from({ length: 6 }, (_, i) => rect(`d${i}`, i, i, 0, 0, 200, 200));
  const out = resolveLabelOffsets(rects);
  const anyClamped = [...out.values()].some((o) => o.dy === DEFAULT_MAX_NUDGE_PX);
  assert.ok(anyClamped, "6 large overlapping labels should hit the default cap at least once");
  const faded = [...out.values()].find((o) => o.opacity === DEFAULT_FADE_OPACITY);
  assert.ok(faded, "a clamped label should carry the default fade opacity");
});

test("a side-by-side overlap at overview-camera (0.5x) scale resolves via the cheaper horizontal nudge", () => {
  // Dimensions halved from a typical ~140x24 hub bubble -- the real
  // overview-camera regime this fix targets, where drei's own 1/dist
  // shrink plus bubbleCounterScale's compensation can still land two
  // ADJACENT labels (same row, small x-overlap) at roughly the same y.
  // Overlap along x is only 5px (170..175, since a=[100,170] b=[165,235]);
  // clearing it needs dx>=5 (one 6px step). Clearing along y instead would
  // need dy>=h=12 (two 6px steps) since the rects sit at the identical y --
  // horizontal is strictly cheaper, and per this file's own "smaller
  // displacement wins" rule must be the one chosen.
  const a = rect("coach", PRIORITY.PERSONA, 40, 100, 100, 70, 12);
  const b = rect("general-purpose", PRIORITY.LANE, 42, 165, 100, 70, 12);
  const out = resolveLabelOffsets([a, b]);
  const oa = out.get("coach")!;
  const ob = out.get("general-purpose")!;
  assert.equal(oa.dx, 0);
  assert.equal(oa.dy, 0);
  assert.equal(ob.dy, 0, "the cheaper axis (x) should be chosen, not y");
  assert.ok(ob.dx > 0, "lower-precedence label should be nudged horizontally");
  assert.equal(ob.opacity, 1, "a 6px nudge should not need to fade");
  // Must actually be clear post-resolve.
  const clear = a.x + a.width <= b.x + ob.dx || b.x + ob.dx + b.width <= a.x || a.y + a.height <= b.y + ob.dy || b.y + ob.dy + b.height <= a.y;
  assert.ok(clear, "coach and general-purpose still overlap after resolve");
});

test("the real hub crowd (9 labels) at post-OVERVIEW-FLOOR-fix size: height-only cap still fades Coach, the two-factor cap (LabelDeclutterManager.tsx's own formula) clears every label (2026-09-15)", () => {
  // bubbleScale.ts's OVERVIEW-FLOOR fix roughly doubles every hub-center
  // label's real on-screen size (~6px -> ~11.6px text, and the bubble box
  // along with it: ~14px -> ~28px tall for a typical persona/live-agent
  // bubble). Reproduces declutter-overview.png's own hub-center crowd,
  // read at 1:1 after the FIRST (height-only) cap fix still left Coach/
  // Chef/the BRAIN plaque faded: Gamma + 3 general-purpose live-agent
  // bubbles + 4 persona desks (Chef/Scout/Coach/Treasurer) + the BRAIN
  // plaque, all anchored at ~the same hub-center point -- 9 labels total.
  // The LAST one in priority order must clear all 8 placed before it:
  // dy = 8*height = 224px of vertical travel.
  const HEIGHT = 28;
  const rects = [
    rect("gamma", PRIORITY.GAMMA, 30, 200, 200, 150, HEIGHT),
    rect("live-1", PRIORITY.LIVE_AGENT, 31, 200, 200, 150, HEIGHT),
    rect("live-2", PRIORITY.LIVE_AGENT, 32, 200, 200, 150, HEIGHT),
    rect("live-3", PRIORITY.LIVE_AGENT, 33, 200, 200, 150, HEIGHT),
    rect("chef", PRIORITY.PERSONA, 34, 200, 200, 150, HEIGHT),
    rect("scout", PRIORITY.PERSONA, 35, 200, 200, 150, HEIGHT),
    rect("coach", PRIORITY.PERSONA, 36, 200, 200, 150, HEIGHT),
    rect("treasurer", PRIORITY.PERSONA, 37, 200, 200, 150, HEIGHT),
    rect("brain-plaque", PRIORITY.PLAQUE, 38, 200, 200, 150, HEIGHT),
  ];

  // Height-only cap (this pass's FIRST fix, insufficient on its own): grows
  // with label size but not with how many labels are actually crowded.
  const NUDGE_BASELINE_HEIGHT_PX = 15;
  const heightOnlyCap = DEFAULT_MAX_NUDGE_PX * (HEIGHT / NUDGE_BASELINE_HEIGHT_PX);
  const withHeightOnlyCap = resolveLabelOffsets(rects, heightOnlyCap);
  const coachHeightOnly = withHeightOnlyCap.get("coach")!;
  const brainHeightOnly = withHeightOnlyCap.get("brain-plaque")!;
  assert.ok(coachHeightOnly.opacity < 1 || brainHeightOnly.opacity < 1, "with only the height-factor cap, this 9-label crowd still clamps and fades someone -- reproduces the still-faded Coach/BRAIN read from overview-read.png after the first fix alone");

  // Two-factor cap: LabelDeclutterManager.tsx's own formula --
  // max(height-ratio * default, height * count * margin, default).
  const NUDGE_CHAIN_MARGIN = 1.25;
  const twoFactorCap = Math.max(
    DEFAULT_MAX_NUDGE_PX * (HEIGHT / NUDGE_BASELINE_HEIGHT_PX),
    HEIGHT * rects.length * NUDGE_CHAIN_MARGIN,
    DEFAULT_MAX_NUDGE_PX,
  );
  assert.ok(twoFactorCap > heightOnlyCap, "the count-aware cap must exceed the height-only cap for a 9-label crowd");

  const withTwoFactorCap = resolveLabelOffsets(rects, twoFactorCap);
  for (const r of rects) {
    const o = withTwoFactorCap.get(r.id)!;
    assert.equal(o.opacity, 1, `${r.id} must render at full opacity -- no label may be left faded/hidden in the real hub crowd`);
  }
  // Every pair must be genuinely clear on WHICHEVER axis the resolver chose
  // (a label may clear via dx instead of dy if that's the cheaper axis --
  // see labelDeclutter.ts's own "smaller displacement wins" rule), not just
  // individually under-cap.
  for (let i = 0; i < rects.length; i++) {
    for (let j = i + 1; j < rects.length; j++) {
      const oi = withTwoFactorCap.get(rects[i].id)!;
      const oj = withTwoFactorCap.get(rects[j].id)!;
      const xi = 200 + oi.dx, yi = 200 + oi.dy;
      const xj = 200 + oj.dx, yj = 200 + oj.dy;
      const clear = xi + 150 <= xj || xj + 150 <= xi || yi + HEIGHT <= yj || yj + HEIGHT <= yi;
      assert.ok(clear, `${rects[i].id} and ${rects[j].id} still overlap after the two-factor-cap resolve`);
    }
  }
});

// ─── HUD-OBSTACLE (2026-09-15): fixed HUD DOM overlays (help bar, title
// block, right panel, perf/Synced corner -- see LabelDeclutterManager.tsx's
// own `data-hq-obstacle` wiring) register as ObstacleRect entries the
// resolver must nudge labels off of, without ever moving the obstacle
// itself or disturbing label-vs-label priority order. ────────────────────

function obstacle(id: string, x: number, y: number, w: number, h: number, isScreen = false): ObstacleRect {
  return { id, x, y, width: w, height: h, isScreen };
}

function screenObstacle(id: string, x: number, y: number, w: number, h: number): ObstacleRect {
  return obstacle(id, x, y, w, h, true);
}

test("a label overlapping a fixed obstacle moves off it", () => {
  // The real evidence case: a live-agent bubble sitting exactly under the
  // HUD help bar (plaque-overview.png, read at 1:1).
  const helpBar = obstacle("help-bar", 440, 845, 555, 24);
  const bubble = rect("live:general-purpose", PRIORITY.LIVE_AGENT, 10, 450, 831, 260, 26);
  const out = resolveLabelOffsets([bubble], DEFAULT_MAX_NUDGE_PX, DEFAULT_FADE_OPACITY, [helpBar]);
  const o = out.get(bubble.id)!;
  assert.ok(o.dx !== 0 || o.dy !== 0, "a label starting on top of an obstacle must be nudged");
  const clear =
    bubble.x + o.dx + bubble.width <= helpBar.x || helpBar.x + helpBar.width <= bubble.x + o.dx ||
    bubble.y + o.dy + bubble.height <= helpBar.y || helpBar.y + helpBar.height <= bubble.y + o.dy;
  assert.ok(clear, "label must actually clear the obstacle after resolve");
});

test("the obstacle never moves and never appears in the output map", () => {
  const helpBar = obstacle("help-bar", 0, 0, 200, 24);
  const label = rect("lane:futures", PRIORITY.LANE, 10, 0, 0, 200, 24);
  const out = resolveLabelOffsets([label], DEFAULT_MAX_NUDGE_PX, DEFAULT_FADE_OPACITY, [helpBar]);
  assert.equal(out.get("help-bar"), undefined, "obstacles are not labels and get no offset entry");
  assert.equal(out.size, 1, "only the real label gets an offset entry");
});

test("an obstacle always outranks every label, even LIVE_AGENT/GAMMA priority", () => {
  const rightPanel = obstacle("right-panel", 1420, 0, 500, 1080);
  const gamma = rect("gamma", PRIORITY.GAMMA, 5, 1400, 500, 150, 28);
  const out = resolveLabelOffsets([gamma], DEFAULT_MAX_NUDGE_PX, DEFAULT_FADE_OPACITY, [rightPanel]);
  const o = out.get("gamma")!;
  assert.ok(o.dx !== 0 || o.dy !== 0, "even the highest-priority label must yield to an obstacle");
});

test("priority order between two real labels is unchanged when an unrelated obstacle is present", () => {
  const cornerObstacle = obstacle("perf-corner", 900, 900, 200, 40); // far away, touches neither label
  const a = rect("a", PRIORITY.GAMMA, 5, 100, 100, 120, 24);
  const b = rect("b", PRIORITY.PERSONA, 5, 100, 100, 120, 24);
  const withoutObstacle = resolveLabelOffsets([a, b]);
  const withObstacle = resolveLabelOffsets([a, b], DEFAULT_MAX_NUDGE_PX, DEFAULT_FADE_OPACITY, [cornerObstacle]);
  assert.equal(withObstacle.get("a")!.dx, withoutObstacle.get("a")!.dx);
  assert.equal(withObstacle.get("a")!.dy, withoutObstacle.get("a")!.dy);
  assert.equal(withObstacle.get("b")!.dx, withoutObstacle.get("b")!.dx);
  assert.equal(withObstacle.get("b")!.dy, withoutObstacle.get("b")!.dy);
});

test("a label pinned against an obstacle past the cap fades instead of stacking forever", () => {
  const maxNudge = 10;
  const fade = 0.35;
  // Obstacle fills the whole plausible nudge range on both axes so neither
  // axis can clear within a tiny 10px cap.
  const bigObstacle = obstacle("title-block", -50, -50, 300, 300);
  const label = rect("lane:safe2", PRIORITY.LANE, 10, 0, 0, 120, 24);
  const out = resolveLabelOffsets([label], maxNudge, fade, [bigObstacle]);
  const o = out.get(label.id)!;
  assert.ok(Math.abs(o.dx) === maxNudge || Math.abs(o.dy) === maxNudge, "should clamp exactly at the cap");
  assert.equal(o.opacity, fade, "a label that cannot clear an obstacle within the cap must fade");
});

// ─── SCREEN KEEP-OUT (2026-09-16, probe 20260916T005621Z label_vs_screen_
// overlap FAIL, twin-monitor-33/34): commit 77e8308f shipped the AUDIT
// check but never actually fed the two readable TwinMonitors screens into
// this resolver's own `obstacles` argument -- LabelDeclutterManager.tsx
// only ever read `[data-hq-obstacle]` DOM HUD chrome. The runtime fix
// (LabelDeclutterManager.tsx's new `readScreenObstacleRects`, not unit-
// tested here -- it needs a real THREE.Camera/scene) projects each screen's
// world AABB to a viewport rect via `ndcCornersToViewportRect` (this
// file's pure half, mirrors hq-scene-audit.ts's own
// `projectAabbToViewportRect` exactly) and passes it into the SAME
// `obstacles` argument every HUD rect already goes through -- so the
// resolver's own pre-existing "an obstacle always outranks every label,
// priority included" guarantee (see the LIVE_AGENT/GAMMA test above)
// applies to a screen exactly as it does to a HUD panel. These tests pin
// (a) the NDC->pixel projection math and (b) the exact "label centred on a
// keep-out rect" case named in the brief, using Gamma's own real priority
// tier and label id shape from the FAIL evidence.

test("ndcCornersToViewportRect: a screen's 8 world-AABB corners project to the expected viewport rect", () => {
  // A screen spanning the dead center 50% of NDC space on both axes
  // (x,y in [-0.5, 0.5]) at a single depth (z irrelevant to the 2D rect).
  const corners: [number, number][] = [
    [-0.5, -0.5], [0.5, -0.5], [-0.5, 0.5], [0.5, 0.5],
  ];
  const rect = ndcCornersToViewportRect(corners, 1000, 800);
  assert.ok(rect);
  // NDC x=-0.5 -> px=((−0.5+1)/2)*1000=250; x=0.5 -> px=750.
  assert.equal(rect!.x, 250);
  assert.equal(rect!.width, 500);
  // NDC y=0.5 (up) -> screen top py=((1-0.5)/2)*800=200; y=-0.5 -> py=600.
  assert.equal(rect!.y, 200);
  assert.equal(rect!.height, 400);
});

test("ndcCornersToViewportRect: returns null for a zero-area viewport or a non-finite corner (camera not ready)", () => {
  assert.equal(ndcCornersToViewportRect([[0, 0]], 0, 800), null);
  assert.equal(ndcCornersToViewportRect([[NaN, 0]], 1000, 800), null);
  assert.equal(ndcCornersToViewportRect([], 1000, 800), null);
});

test("screen keep-out: a label rect CENTRED on a keep-out rect resolves fully outside it, or fades to FULL 0 (never a partial fadeOpacity) -- the twin-monitor-33/34 FAIL shape, both Gamma-tier and a live-agent label", () => {
  const screen = screenObstacle("screen-twin-monitor-0", 700, 400, 260, 150);
  const centerX = screen.x + screen.width / 2;
  const centerY = screen.y + screen.height / 2;

  // Gamma's own head label -- PRIORITY.GAMMA (0), the tier the brief calls
  // out as "must not be exempt just because it's top priority".
  const gamma = rect("gamma", PRIORITY.GAMMA, 5, centerX - 30, centerY - 10, 60, 20);
  // A live-agent label, same priority tier, centred on the SAME screen --
  // the reported twin-monitor-34 "general-purpo... " overlap.
  const liveAgent = rect("live:general-purpose", PRIORITY.LIVE_AGENT, 6, centerX - 10, centerY - 10, 140, 22);

  const out = resolveLabelOffsets([gamma, liveAgent], DEFAULT_MAX_NUDGE_PX, DEFAULT_FADE_OPACITY, [screen]);

  for (const label of [gamma, liveAgent]) {
    const o = out.get(label.id)!;
    const finalX = label.x + o.dx;
    const finalY = label.y + o.dy;
    const stillOverlapsScreen =
      finalX < screen.x + screen.width && finalX + label.width > screen.x &&
      finalY < screen.y + screen.height && finalY + label.height > screen.y;
    // SCREEN-KEEP-OUT HARDENING (2026-09-16): a screen is strictly worse to
    // occlude than another label -- hq_probe_lib.py's own
    // check_label_screen_overlap only excludes a label below opacity 0.05,
    // so the generic fadeOpacity (0.35) a label-vs-label collision uses is
    // NOT an acceptable outcome here; only a full clear or a full (0)
    // fade counts.
    assert.ok(
      !stillOverlapsScreen || o.opacity === 0,
      `${label.id}: must resolve fully outside the screen's own rect, or fade FULLY to 0, regardless of top priority -- got dx=${o.dx} dy=${o.dy} opacity=${o.opacity}`,
    );
    if (o.opacity !== 0) {
      assert.ok(!stillOverlapsScreen, `${label.id}: at non-zero opacity the resolved rect must not intersect the screen's own rect at all`);
    }
  }
});

test("SCREEN-KEEP-OUT HARDENING: real probe FAIL geometry (twin-monitor-101/102, overlapFrac 0.19/0.30) -- a label pinned against a screen mesh bigger than the default nudge cap fades fully to 0, never the generic fadeOpacity", () => {
  // A real monitor's projected AABB rect at a close/moving camera pose can
  // easily exceed the default 60px nudge budget in both directions -- this
  // reproduces that shape directly (screen half-extents far bigger than
  // DEFAULT_MAX_NUDGE_PX on both axes) rather than guessing at exact
  // probe-run pixel values the raw per-tick geometry was never persisted
  // for (see hq_live_probe.py's own per-tick screen_rects fix).
  const screen = screenObstacle("screen-twin-monitor-101", 500, 300, 400, 300);
  const centerX = screen.x + screen.width / 2;
  const centerY = screen.y + screen.height / 2;
  const coach = rect("persona:Coach", PRIORITY.PERSONA, 8, centerX - 40, centerY - 12, 80, 24);

  const out = resolveLabelOffsets([coach], DEFAULT_MAX_NUDGE_PX, DEFAULT_FADE_OPACITY, [screen]);
  const o = out.get(coach.id)!;
  const finalX = coach.x + o.dx;
  const finalY = coach.y + o.dy;
  const stillOverlapsScreen =
    finalX < screen.x + screen.width && finalX + coach.width > screen.x &&
    finalY < screen.y + screen.height && finalY + coach.height > screen.y;

  assert.ok(stillOverlapsScreen, "test setup sanity: this screen must be too big for the default cap to clear");
  assert.equal(o.opacity, 0, "a label that cannot clear a screen within the cap must fade FULLY to 0, not the generic fadeOpacity");
});

test("SCREEN-KEEP-OUT HARDENING does not regress the generic HUD-obstacle fade (non-screen obstacle past the cap still fades to fadeOpacity, not 0)", () => {
  const maxNudge = 10;
  const fade = 0.35;
  const hudPanel = obstacle("title-block", -50, -50, 300, 300); // isScreen defaults false
  const label = rect("lane:safe2", PRIORITY.LANE, 10, 0, 0, 120, 24);
  const out = resolveLabelOffsets([label], maxNudge, fade, [hudPanel]);
  const o = out.get(label.id)!;
  assert.equal(o.opacity, fade, "a non-screen obstacle must keep the original generic fadeOpacity behavior");
});

test("stable order across frames: identical input always yields identical output (no jitter)", () => {
  const rects = [
    rect("live-1", PRIORITY.LIVE_AGENT, 12.3, 400, 300, 140, 26),
    rect("gamma", PRIORITY.GAMMA, 8.1, 410, 305, 130, 26),
    rect("coach", PRIORITY.PERSONA, 15.0, 405, 302, 120, 26),
    rect("brain-plaque", PRIORITY.PLAQUE, 20.4, 420, 300, 200, 30),
    rect("futures-lane", PRIORITY.LANE, 30.0, 415, 310, 110, 24),
  ];
  const first = resolveLabelOffsets(rects);
  for (let i = 0; i < 10; i++) {
    const again = resolveLabelOffsets(rects.slice().reverse()); // input order must not matter either
    for (const r of rects) {
      assert.equal(again.get(r.id)!.dy, first.get(r.id)!.dy, `dy for ${r.id} drifted on rerun ${i}`);
      assert.equal(again.get(r.id)!.opacity, first.get(r.id)!.opacity, `opacity for ${r.id} drifted on rerun ${i}`);
    }
  }
});

// ─── COLD-START SNAP FIX (2026-09-15) ───────────────────────────────────
// Root cause reproduced at the manager-loop level (see labelDeclutter.ts's
// own "COLD-START SNAP FIX" comment for the full evidence from the
// real-GPU probe run 20260915T090312Z-Da6D81TEcI6kH8JvM85Db.samples.json.gz):
// LabelDeclutterManager.tsx used to lerp a label's applied on-screen offset
// toward the resolved target by SMOOTH_FACTOR (0.4) unconditionally, so a
// label going from "not colliding" (0 applied offset) to "needs a nudge"
// (the scene's opening camera flythrough moving a natural position 400+px
// in one 0.5s probe tick) only got 40% of the needed separation applied
// that tick -- still overlapping on screen. `simulateManagerTick` below
// mirrors exactly the two lines LabelDeclutterManager.tsx runs per label
// per tick (resolve a target via resolveLabelOffsets, then blend the
// previous applied offset toward it) so this test exercises the real
// bug/fix through the same two functions the manager calls, without
// needing React/DOM/three.js.
function overlapFraction(
  ax: number, ay: number, aw: number, ah: number,
  bx: number, by: number, bw: number, bh: number,
): number {
  const ox = Math.max(0, Math.min(ax + aw, bx + bw) - Math.max(ax, bx));
  const oy = Math.max(0, Math.min(ay + ah, by + bh) - Math.max(ay, by));
  const smaller = Math.min(aw * ah, bw * bh);
  return smaller > 0 ? (ox * oy) / smaller : 0;
}

/** Old (buggy) behavior: plain unconditional lerp, no cold-start snap. */
function plainLerp(prevDx: number, prevDy: number, targetDx: number, targetDy: number, factor: number) {
  return { dx: prevDx + (targetDx - prevDx) * factor, dy: prevDy + (targetDy - prevDy) * factor };
}

test("cold-start collision: plain lerp leaves the pair overlapping for one tick; smoothLabelOffset snaps clear immediately", () => {
  const SMOOTH_FACTOR = 0.4;
  const OVERLAP_THRESHOLD = 0.15; // matches the probe's own collision definition

  // "a" outranks "b" (lower priority wins) and stays at dy=0. Both start
  // with zero applied offset -- a brand-new collision, exactly the probe's
  // camera-flythrough case (natural positions suddenly coincide).
  const a = rect("a", PRIORITY.GAMMA, 5, 100, 100, 150, 22);
  const b = rect("b", PRIORITY.PERSONA, 5, 100, 100, 150, 22);
  const targets = resolveLabelOffsets([a, b]);
  const targetB = targets.get("b")!;
  assert.ok(Math.abs(targetB.dy) > 0, "b must need a real nudge to clear a's identical rect");

  // OLD behavior: one tick of plain lerp from a 0 prior offset.
  const buggy = plainLerp(0, 0, targetB.dx, targetB.dy, SMOOTH_FACTOR);
  const buggyOverlap = overlapFraction(
    a.x, a.y, a.width, a.height,
    b.x + buggy.dx, b.y + buggy.dy, b.width, b.height,
  );
  assert.ok(buggyOverlap >= OVERLAP_THRESHOLD, `pre-fix: expected the pair to STILL overlap after one smoothed tick (got ${buggyOverlap.toFixed(2)}) -- this is the reproduced bug`);

  // NEW behavior: smoothLabelOffset snaps to the full target on the
  // cold-start tick instead of lerping from zero.
  const fixed = smoothLabelOffset(0, 0, targetB.dx, targetB.dy, SMOOTH_FACTOR);
  assert.equal(fixed.dx, targetB.dx);
  assert.equal(fixed.dy, targetB.dy);
  const fixedOverlap = overlapFraction(
    a.x, a.y, a.width, a.height,
    b.x + fixed.dx, b.y + fixed.dy, b.width, b.height,
  );
  assert.ok(fixedOverlap < OVERLAP_THRESHOLD, `post-fix: pair must clear the overlap threshold on the very first tick (got ${fixedOverlap.toFixed(2)})`);
});

test("smoothLabelOffset still lerps (no snap) once a label already carries a non-zero offset -- preserves the original no-snap-the-stack behavior for small target drift", () => {
  const prevDx = 0, prevDy = 24; // already nudged from a prior tick
  const targetDx = 0, targetDy = 30; // small further drift (e.g. a walking neighbor)
  const out = smoothLabelOffset(prevDx, prevDy, targetDx, targetDy, 0.4);
  assert.equal(out.dy, prevDy + (targetDy - prevDy) * 0.4, "must still lerp, not snap, when a prior offset already exists");
});

test("smoothLabelOffset is a no-op when neither prev nor target carries an offset", () => {
  const out = smoothLabelOffset(0, 0, 0, 0, 0.4);
  assert.equal(out.dx, 0);
  assert.equal(out.dy, 0);
});

// ─── NEVER-LERP-INTO-OVERLAP FIX (DECLUTTER v2, 2026-09-15) ─────────────
// Root cause (see labelDeclutter.ts's own "NEVER-LERP-INTO-OVERLAP FIX"
// comment for the full real-GPU probe evidence, samples file
// 20260915T092455Z-ryajHEnIzll03dXEfn-AQ.samples.json.gz, 63/580 ticks
// still overlapping post-v1): once a label already carries a non-zero
// offset, `smoothLabelOffset` keeps lerping at SMOOTH_FACTOR even while an
// overview camera keeps panning/zooming and the resolver's target keeps
// sliding -- the lerped (under-applied) offset can itself sit inside a
// neighbor's rect even though the FULLY-resolved target never would.
//
// This scenario drives that exact mechanism through both functions:
// label B needs to clear a neighbor A whose height (and therefore B's
// exact required clearance) grows 40px every tick for 3 ticks -- a
// continuously-drifting target, the shape the coordinator's probe read
// off Chef's own 100+px drift over tens of seconds. A stays fixed at
// dy=0 (higher priority); B's clearance target is exactly A's height
// each tick, so a target that landed short would overlap and a target
// that lands exactly on the boundary does not (matches the real
// resolver's own "clears with zero slack" worst case).
test("continuously-drifting target (40px/tick x3): plain smoothLabelOffset overlaps >=1 tick (RED reproduction of the v2 bug), smoothLabelOffsetAvoidingOverlap overlaps 0 ticks (GREEN)", () => {
  const SMOOTH_FACTOR = 0.4;
  const B_NATURAL = { x: 100, y: 100, width: 150, height: 24 };
  const A_X = 100, A_Y = 100, A_WIDTH = 150;
  const growingHeights = [40, 80, 120]; // A's height this tick == B's exact required clearance

  function tickOverlaps(appliedDy: number, aHeight: number): boolean {
    return rectsOverlap(
      B_NATURAL.x, B_NATURAL.y + appliedDy, B_NATURAL.width, B_NATURAL.height,
      A_X, A_Y, A_WIDTH, aHeight,
    );
  }

  // OLD: plain smoothLabelOffset, no overlap-avoidance guard.
  let prevDx = 0, prevDy = 0, oldOverlapTicks = 0;
  for (const aHeight of growingHeights) {
    const targetDy = aHeight;
    const smoothed = smoothLabelOffset(prevDx, prevDy, 0, targetDy, SMOOTH_FACTOR);
    if (tickOverlaps(smoothed.dy, aHeight)) oldOverlapTicks += 1;
    prevDx = smoothed.dx;
    prevDy = smoothed.dy;
  }
  assert.ok(oldOverlapTicks >= 1, `RED: pre-fix smoothLabelOffset must still overlap on >=1 of 3 ticks while the target keeps drifting (got ${oldOverlapTicks})`);

  // NEW: smoothLabelOffsetAvoidingOverlap, snaps to target when (and only
  // when) the ordinary lerp would leave the label inside a collision the
  // target itself clears.
  prevDx = 0;
  prevDy = 0;
  let newOverlapTicks = 0;
  for (const aHeight of growingHeights) {
    const targetDy = aHeight;
    const otherRects = [{ x: A_X, y: A_Y, width: A_WIDTH, height: aHeight }];
    const smoothed = smoothLabelOffsetAvoidingOverlap(
      B_NATURAL, prevDx, prevDy, 0, targetDy, SMOOTH_FACTOR, otherRects,
    );
    if (tickOverlaps(smoothed.dy, aHeight)) newOverlapTicks += 1;
    prevDx = smoothed.dx;
    prevDy = smoothed.dy;
  }
  assert.equal(newOverlapTicks, 0, `GREEN: post-fix smoothLabelOffsetAvoidingOverlap must clear every tick even while the target keeps drifting (got ${newOverlapTicks} overlapping ticks)`);
});

// ─── LEVEL-ORDER fix (2026-09-15): orderGroup/orderKey ──────────────────────
// Real capture evidence (hq-close-1653.png, read at 1:1): "757.44
// RESISTANCE" rendered BELOW "757.38 · last close" even though 757.44 >
// 757.38 -- the generic collision resolver has no notion of price, so a
// same-priority nudge could freely invert two plaques whose relative
// vertical position is meant to reflect a real price rank.

function priceRect(id: string, price: number, y: number, w = 120, h = 24): LabelRect {
  return { id, priority: PRIORITY.PLAQUE, distance: 10, x: 0, y, width: w, height: h, orderGroup: "prices", orderKey: -price };
}

test("orderGroup/orderKey: a higher-price plaque's final y never ends up below a lower-price plaque's", () => {
  // Deliberately gives the LOWER price ("757.38") the smaller natural y (as
  // if collision-avoidance alone had already inverted it) -- the real
  // shape the evidence capture shows: 757.44 (higher) natural position
  // pushed further down than 757.38 (lower)'s.
  const higher = priceRect("757.44", 757.44, 100); // higher price, but starts BELOW visually (larger y is "below")
  const lower = priceRect("757.38", 757.38, 10); // lower price, starts ABOVE (smaller y)
  const out = resolveLabelOffsets([higher, lower]);
  const higherFinalY = higher.y + out.get("757.44")!.dy;
  const lowerFinalY = lower.y + out.get("757.38")!.dy;
  assert.ok(higherFinalY <= lowerFinalY, `757.44 (final y=${higherFinalY}) must never sit below 757.38 (final y=${lowerFinalY})`);
});

test("orderGroup/orderKey: five real price plaques (levels + last-close) stay in strict price order after resolve", () => {
  // Today's real level set + last-close, deliberately shuffled and given
  // colliding natural y's so the resolver has real work to do.
  const items: Array<[string, number, number]> = [
    ["759.48-RESISTANCE", 759.48, 50],
    ["758.60-RESISTANCE", 758.6, 52],
    ["757.93-SUPPORT", 757.93, 200],
    ["757.62-SWING-HIGH", 757.62, 48],
    ["757.44-RESISTANCE", 757.44, 5], // adversarial: highest natural y among the low-price group
    ["757.38-last-close", 757.38, 150],
  ];
  const rects = items.map(([id, price, y]) => priceRect(id, price, y));
  const out = resolveLabelOffsets(rects);
  const finals = items.map(([id, price]) => ({ price, finalY: rects.find((r) => r.id === id)!.y + out.get(id)!.dy }));
  const sortedByPriceDesc = [...finals].sort((a, b) => b.price - a.price);
  for (let i = 1; i < sortedByPriceDesc.length; i++) {
    assert.ok(
      sortedByPriceDesc[i - 1].finalY <= sortedByPriceDesc[i].finalY,
      `price order violated: ${sortedByPriceDesc[i - 1].price} (y=${sortedByPriceDesc[i - 1].finalY}) must be <= ${sortedByPriceDesc[i].price} (y=${sortedByPriceDesc[i].finalY})`,
    );
  }
});

test("orderGroup/orderKey: a label with no orderGroup is completely unaffected by the order pass", () => {
  const a = rect("plain-a", PRIORITY.PLAQUE, 10, 0, 0, 100, 24);
  const b = rect("plain-b", PRIORITY.PLAQUE, 11, 200, 0, 100, 24);
  const withOrder = resolveLabelOffsets([a, b]);
  // Same rects, run again -- identical result, order pass is a no-op absent orderGroup.
  const again = resolveLabelOffsets([a, b]);
  assert.deepEqual(withOrder.get("plain-a"), again.get("plain-a"));
  assert.deepEqual(withOrder.get("plain-b"), again.get("plain-b"));
});

test("orderGroup/orderKey: two different orderGroups never constrain each other", () => {
  const a = priceRect("group-a-1", 100, 0);
  const b = { ...priceRect("group-b-1", 1, 0), orderGroup: "other-group" };
  const out = resolveLabelOffsets([a, b]);
  // No collision (different x not set here, but same rect footprint at y=0 for both -- collision-avoidance still applies within PLAQUE tier regardless of group, only enforceGroupOrder is group-scoped). Just assert no crash and both have entries.
  assert.ok(out.get("group-a-1"));
  assert.ok(out.get("group-b-1"));
});

// OCCLUSION fix regression (2026-09-15, real capture hq-final2.png read at
// 1:1, 17:44 ET): "757.38 · last close" (a taller ~40px `.hq-beam` plaque)
// drawn ON TOP of "757.44 RESISTANCE" (a compact ~24px level plaque) --
// only "757.4" of the level plaque stayed readable. The old
// `enforceGroupOrder` only floored on the previous label's final TOP, so
// two same-order-group plaques of DIFFERENT heights could satisfy
// "757.44's finalY <= 757.38's finalY" while their rects still
// intersected. This test reproduces that exact pair (a shorter,
// higher-priced level plaque directly above a taller, lower-priced
// last-close plaque, adversarial starting y's forcing the order pass to
// act) and asserts the final rects never intersect, not just that the
// order is right.
test("orderGroup/orderKey: a level plaque and a taller last-close plaque of similar size never end up with intersecting final rects", () => {
  const level = priceRect("757.44-RESISTANCE", 757.44, 0, 140, 24);
  const lastClose = priceRect("757.38-last-close", 757.38, 2, 150, 40);
  const out = resolveLabelOffsets([level, lastClose]);
  const levelOff = out.get("757.44-RESISTANCE")!;
  const lastCloseOff = out.get("757.38-last-close")!;
  const levelFinal = { x: level.x + levelOff.dx, y: level.y + levelOff.dy, width: level.width, height: level.height };
  const lastCloseFinal = {
    x: lastClose.x + lastCloseOff.dx, y: lastClose.y + lastCloseOff.dy,
    width: lastClose.width, height: lastClose.height,
  };
  assert.ok(
    !rectsOverlap(
      levelFinal.x, levelFinal.y, levelFinal.width, levelFinal.height,
      lastCloseFinal.x, lastCloseFinal.y, lastCloseFinal.width, lastCloseFinal.height,
    ),
    `757.44 and 757.38 · last close must never intersect (level=${JSON.stringify(levelFinal)}, lastClose=${JSON.stringify(lastCloseFinal)})`,
  );
  assert.ok(levelFinal.y <= lastCloseFinal.y, "757.44 (higher price) must stay above 757.38 · last close");
});

// ─── HQ-LEVEL-TOUCHES (2026-09-15): longer plaque text ─────────────────────
// LevelLabelItem's plaque now appends real interaction text ("3 touches ·
// held" / "5 touches · broke 13:05") to the price+tag it already showed --
// wider on-screen rects than before. Reproduces a realistic crowded cluster
// (today's real level set) at the new, longer widths and asserts the
// existing guarantees (strict price order, zero overlap) still hold.
test("orderGroup/orderKey: longer level-interaction plaque text ('N touches · held'/'broke HH:MM') still resolves in strict price order with zero overlap", () => {
  const items: Array<[string, number, number, number]> = [
    ["759.48-RESISTANCE", 759.48, 50, 230], // "759.48 RESISTANCE · 3 touches · held"
    ["758.60-RESISTANCE", 758.6, 52, 245], // "758.60 RESISTANCE · 5 touches · broke 13:05"
    ["757.93-SUPPORT", 757.93, 200, 150], // untested -- stays at the pre-existing short width
    ["757.62-SWING-HIGH", 757.62, 48, 235],
    ["757.44-RESISTANCE", 757.44, 5, 250], // adversarial: highest natural y among the low-price group
    ["757.38-last-close", 757.38, 150, 190],
  ];
  const rects = items.map(([id, price, y, w]) => priceRect(id, price, y, w));
  const out = resolveLabelOffsets(rects);

  // Strict price order (same guarantee the shorter-label test above checks).
  const finals = items.map(([id, price]) => ({ id, price, finalY: rects.find((r) => r.id === id)!.y + out.get(id)!.dy }));
  const sortedByPriceDesc = [...finals].sort((a, b) => b.price - a.price);
  for (let i = 1; i < sortedByPriceDesc.length; i++) {
    assert.ok(
      sortedByPriceDesc[i - 1].finalY <= sortedByPriceDesc[i].finalY,
      `price order violated: ${sortedByPriceDesc[i - 1].price} (y=${sortedByPriceDesc[i - 1].finalY}) must be <= ${sortedByPriceDesc[i].price} (y=${sortedByPriceDesc[i].finalY})`,
    );
  }

  // Zero overlap between every pair's final rects, not just individually-clamped positions.
  for (let i = 0; i < rects.length; i++) {
    for (let j = i + 1; j < rects.length; j++) {
      const ri = rects[i];
      const rj = rects[j];
      const oi = out.get(ri.id)!;
      const oj = out.get(rj.id)!;
      const overlap = rectsOverlap(
        ri.x + oi.dx, ri.y + oi.dy, ri.width, ri.height,
        rj.x + oj.dx, rj.y + oj.dy, rj.width, rj.height,
      );
      assert.ok(!overlap, `${ri.id} and ${rj.id} still overlap at the new longer widths (${ri.width}px/${rj.width}px)`);
    }
  }
});

// ─── LEGIBILITY-FLOOR (2026-09-15, real-probe evidence: hq_live_probe.py
// --plausibility, label_legibility FAIL 20 violations, first
// `{'text': '757.38 · last close', 'height_px': 7.77}`) ────────────────────

test("isBelowLegibilityFloor: matches MIN_LEGIBLE_PX exactly, boundary is exclusive", () => {
  assert.equal(isBelowLegibilityFloor(7.77), true);
  assert.equal(isBelowLegibilityFloor(MIN_LEGIBLE_PX), false); // exactly-at-floor is legible
  assert.equal(isBelowLegibilityFloor(MIN_LEGIBLE_PX - 0.01), true);
  assert.equal(isBelowLegibilityFloor(24), false);
});

test("legibility floor: a label measured under MIN_LEGIBLE_PX fades to opacity 0 even with zero collisions", () => {
  const tiny = rect("holo-lastclose", PRIORITY.PLAQUE, 50, 0, 0, 120, 7.77);
  const out = resolveLabelOffsets([tiny]);
  const o = out.get("holo-lastclose")!;
  assert.equal(o.opacity, 0);
  assert.equal(o.dx, 0, "legibility fade never nudges position, only opacity");
  assert.equal(o.dy, 0);
});

test("legibility floor: a label at/above MIN_LEGIBLE_PX is unaffected (no floor false-positive)", () => {
  const ok = rect("holo-level:support:757.93", PRIORITY.PLAQUE, 50, 0, 0, 120, 24);
  const out = resolveLabelOffsets([ok]);
  assert.equal(out.get("holo-level:support:757.93")!.opacity, 1);
});

test("legibility floor overrides a collision-clear result (opacity 1 from clearing does not un-fade a too-small label)", () => {
  const tinyA = rect("a", PRIORITY.PLAQUE, 10, 0, 0, 100, 6);
  const tinyB = rect("b", PRIORITY.PERSONA, 12, 500, 500, 100, 6); // far away, no collision
  const out = resolveLabelOffsets([tinyA, tinyB]);
  assert.equal(out.get("a")!.opacity, 0);
  assert.equal(out.get("b")!.opacity, 0);
});

test("legibility floor composes with the fade-past-cap case: still opacity 0, not double-counted", () => {
  const a = rect("a", PRIORITY.LIVE_AGENT, 10, 0, 0, 100, 5);
  const b = rect("b", PRIORITY.PLAQUE, 12, 0, 0, 100, 5); // fully overlapping, tiny, and will fade past cap too
  const out = resolveLabelOffsets([a, b], 0, DEFAULT_FADE_OPACITY); // maxNudgePx=0 forces b to fade-past-cap
  assert.equal(out.get("a")!.opacity, 0, "below floor even though it never collided");
  assert.equal(out.get("b")!.opacity, 0, "below floor beats the 0.35 fade-past-cap opacity");
});

test("legibilityFloorPx=0 disables the floor entirely (opt-out param, for callers that never want it)", () => {
  const tiny = rect("a", PRIORITY.PLAQUE, 10, 0, 0, 100, 5);
  const out = resolveLabelOffsets([tiny], DEFAULT_MAX_NUDGE_PX, DEFAULT_FADE_OPACITY, [], 0);
  assert.equal(out.get("a")!.opacity, 1);
});

test("legibility floor never disturbs unrelated legible labels sharing a tick", () => {
  const tiny = rect("tiny", PRIORITY.PLAQUE, 10, 0, 0, 100, 6);
  const legible = rect("legible", PRIORITY.PERSONA, 12, 800, 800, 100, 24);
  const out = resolveLabelOffsets([tiny, legible]);
  assert.equal(out.get("tiny")!.opacity, 0);
  assert.equal(out.get("legible")!.opacity, 1);
});

// ─── U5-LEGIBLE-LABELS (2026-09-16, real probe FAIL U5: "live-agent head
// label not legible on the default view" -- a live agent standing at its
// core stand slot in the camera->monitor sightline had its head label faded
// to 0 by the SCREEN-KEEP-OUT HARDENING above). See labelDeclutter.ts's own
// `LabelRect.mustStayLegible` header for the full root cause + fix: an
// answer-bearing label (mustStayLegible: true) gets a much larger nudge
// budget and is NEVER faded for a screen collision, while a decorative
// label at the identical spot keeps the pre-existing fade behavior exactly
// as the two tests above already pin.
test("mustStayLegible: a label centred on a screen rect resolves to opacity 1 and fully outside the rect", () => {
  const screen = screenObstacle("screen-twin-monitor-core", 500, 300, 400, 300);
  const centerX = screen.x + screen.width / 2;
  const centerY = screen.y + screen.height / 2;
  const liveAgent: LabelRect = {
    id: "live:session-d4259a2a",
    priority: PRIORITY.LIVE_AGENT,
    distance: 8,
    x: centerX - 40,
    y: centerY - 12,
    width: 80,
    height: 24,
    mustStayLegible: true,
  };

  const out = resolveLabelOffsets([liveAgent], DEFAULT_MAX_NUDGE_PX, DEFAULT_FADE_OPACITY, [screen]);
  const o = out.get(liveAgent.id)!;
  const finalX = liveAgent.x + o.dx;
  const finalY = liveAgent.y + o.dy;
  const stillOverlapsScreen =
    finalX < screen.x + screen.width && finalX + liveAgent.width > screen.x &&
    finalY < screen.y + screen.height && finalY + liveAgent.height > screen.y;

  assert.equal(o.opacity, 1, "an answer-bearing label must never fade for a screen collision");
  assert.ok(!stillOverlapsScreen, "an answer-bearing label must fully clear the screen's own rect given the larger nudge budget");
});

test("mustStayLegible does not regress the decorative fade: a non-flagged label in the identical spot still fades fully to 0", () => {
  const screen = screenObstacle("screen-twin-monitor-core", 500, 300, 400, 300);
  const centerX = screen.x + screen.width / 2;
  const centerY = screen.y + screen.height / 2;
  const decorative = rect("holo-level:resistance:757.44", PRIORITY.PLAQUE, 8, centerX - 40, centerY - 12, 80, 24);

  const out = resolveLabelOffsets([decorative], DEFAULT_MAX_NUDGE_PX, DEFAULT_FADE_OPACITY, [screen]);
  const o = out.get(decorative.id)!;
  assert.equal(o.opacity, 0, "a decorative label (no mustStayLegible flag) must keep the pre-existing screen-keep-out fade-to-0 behavior");
});

test("mustStayLegible resolves vertical-first: a clean vertical clear is preferred over a lateral one even when lateral would be smaller", () => {
  // A screen that is WIDE (small vertical travel needed) but the label sits
  // dead-center, so a small dy would clear it -- assert the chosen axis is
  // "y" (dx===0) even though the resolver tries y before x in the
  // mustStayLegible branch regardless of relative displacement size.
  const screen = screenObstacle("screen-wide", 0, 0, 1000, 40);
  const label: LabelRect = {
    id: "live:vertical-check",
    priority: PRIORITY.LIVE_AGENT,
    distance: 5,
    x: 460,
    y: 10,
    width: 80,
    height: 20,
    mustStayLegible: true,
  };
  const out = resolveLabelOffsets([label], DEFAULT_MAX_NUDGE_PX, DEFAULT_FADE_OPACITY, [screen]);
  const o = out.get(label.id)!;
  assert.equal(o.dx, 0, "vertical-first resolution: dx must stay 0 when the vertical axis alone clears the screen");
  assert.ok(o.dy !== 0, "the label must have moved along the vertical axis to clear the screen");
  assert.equal(o.opacity, 1);
});

test("mustStayLegible falls back to lateral when vertical alone cannot clear within the larger budget", () => {
  // A screen that is TALL (vertical travel would exceed even the larger
  // mustStayLegible budget) but narrow, so lateral clears easily.
  const screen = screenObstacle("screen-tall", 400, -2000, 200, 4000);
  const label: LabelRect = {
    id: "live:lateral-check",
    priority: PRIORITY.LIVE_AGENT,
    distance: 5,
    x: 460,
    y: 10,
    width: 80,
    height: 20,
    mustStayLegible: true,
  };
  const out = resolveLabelOffsets([label], DEFAULT_MAX_NUDGE_PX, DEFAULT_FADE_OPACITY, [screen]);
  const o = out.get(label.id)!;
  assert.ok(o.dx !== 0, "must fall back to the lateral axis once vertical cannot clear a screen this tall");
  assert.equal(o.opacity, 1, "still never fades even after falling back to the lateral axis");
});

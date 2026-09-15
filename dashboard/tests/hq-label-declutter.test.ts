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
  PRIORITY,
  resolveLabelOffsets,
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

function obstacle(id: string, x: number, y: number, w: number, h: number): ObstacleRect {
  return { id, x, y, width: w, height: h };
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

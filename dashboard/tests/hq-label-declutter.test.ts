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
// overlap, a pair, a chain of 4, the cap+fade, and frame-to-frame stability.

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  DEFAULT_FADE_OPACITY,
  DEFAULT_MAX_NUDGE_PX,
  PRIORITY,
  resolveLabelOffsets,
  type LabelRect,
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

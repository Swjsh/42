"use client";

// ─── Screen-space label declutter -- resolver half ─────────────────────────
// Mounted EXACTLY ONCE, anywhere inside <Canvas> (Scene.tsx). Every throttled
// tick (10Hz -- text labels don't need 60Hz collision resolution, and this
// keeps the O(n^2) rect-overlap pass and n getBoundingClientRect() reflows
// well off the render-critical path): for every label in the shared
// registry (useLabelDeclutter.ts), measures its CURRENT natural (un-nudged)
// screen rect, asks labelDeclutter.ts's pure resolver for this frame's
// offsets, smooths each label's own vertical nudge toward that target (a
// plain lerp -- prevents a one-frame rect jitter, e.g. a walking character's
// bubble moving 1px, from snapping the WHOLE stack instantly), and writes
// the result straight to that label's own wrapper div's `transform`/
// `opacity` (never React state -- an every-tick re-render of N label
// components for a pixel nudge would be the exact anti-pattern every other
// per-frame effect in this tree already avoids, see Agent.tsx's own
// `updateBubbleFade` for the precedent).
//
// Renders nothing itself (`return null`) -- it is pure side effect, the
// same shape as Agent.tsx's own module-scope `lastGlobalWalkStagger`
// bookkeeping, just promoted to a real mounted component since it needs
// r3f's per-frame camera/clock access.

import { useThrottledFrame } from "./useThrottledFrame";
import { useThree } from "@react-three/fiber";
import * as THREE from "three";
import { useRef } from "react";
import { resolveLabelOffsets, smoothLabelOffsetAvoidingOverlap, DEFAULT_MAX_NUDGE_PX, DEFAULT_FADE_OPACITY, MIN_LEGIBLE_PX, type LabelRect, type ObstacleRect, type OverlapRect } from "./labelDeclutter";
import { getLabelRegistry } from "./useLabelDeclutter";
import { isMotionDiagEnabled } from "../../lib/hq-motion-diag";
import { isHoloPricePlaqueId, setLevelPlaquesBelowFloor } from "./legibilityFloor";

// TICK-COST DIAG (DECLUTTER v2, 2026-09-15): read-only perf sample so the
// "should this move to per-frame?" question from the coordinator's fix
// request can be answered with a real number instead of a guess. Same
// `?diag=1` gate as every other diag hook in this tree (hq-motion-diag.ts)
// -- zero cost on a normal viewer (the flag read is cached, and the
// performance.now() calls below are two cheap timestamps, not a new
// per-tick allocation). Exposes a small rolling window on
// `window.__hqDeclutterPerf` for a Browser-pane read, not a re-render.
declare global {
  interface Window {
    __hqDeclutterPerf?: { lastMs: number; avgMs: number; maxMs: number; samples: number };
  }
}
let perfSampleCount = 0;
let perfTotalMs = 0;
let perfMaxMs = 0;
function recordTickCost(ms: number): void {
  perfSampleCount += 1;
  perfTotalMs += ms;
  perfMaxMs = Math.max(perfMaxMs, ms);
  window.__hqDeclutterPerf = {
    lastMs: ms,
    avgMs: perfTotalMs / perfSampleCount,
    maxMs: perfMaxMs,
    samples: perfSampleCount,
  };
}

// HUD-OBSTACLE (2026-09-15): fixed HUD DOM overlays (help bar, title block,
// right panel, perf/Synced corner -- see Hud.tsx's own `data-hq-obstacle`
// attributes) are STATIC, non-React-managed nodes from this module's point
// of view -- there is no ref registry for them the way world labels join
// through useLabelDeclutter.ts, since Hud.tsx and this manager have no
// shared parent that could thread refs between them, and a plain DOM
// attribute query is the cheapest way to stay decoupled (Hud.tsx never
// needs to import or know about the declutter system at all, just tag its
// own overlay nodes). Read via querySelectorAll ONCE per throttled tick
// (10Hz, same cadence as the label rects themselves) -- obstacles never
// move (they're all `position: fixed`/`absolute` HUD chrome), so a fresh
// read every tick is correct-by-construction rather than a perf concern:
// this is at most 4 getBoundingClientRect calls at 10Hz, negligible next to
// the O(n^2) label resolve already running here.
const OBSTACLE_SELECTOR = "[data-hq-obstacle]";

function readObstacleRects(): ObstacleRect[] {
  if (typeof document === "undefined") return [];
  const nodes = document.querySelectorAll<HTMLElement>(OBSTACLE_SELECTOR);
  const out: ObstacleRect[] = [];
  nodes.forEach((el, i) => {
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return; // not laid out / hidden this tick
    out.push({ id: el.getAttribute("data-hq-obstacle") || `obstacle-${i}`, x: r.left, y: r.top, width: r.width, height: r.height });
  });
  return out;
}

// OVERVIEW-FLOOR fix (2026-09-15): bubbleScale.ts's own fix roughly doubles
// every hub-center label's real on-screen size (the ~6px overview floor
// this pass targets was undersized by ~1.9x). A label that is bigger also
// needs MORE room to nudge clear of a same-priority neighbor -- the old
// fixed DEFAULT_MAX_NUDGE_PX(60) cap is exactly why Coach's bubble (read at
// 1:1 from declutter-overview.png) gave up and faded instead of clearing
// Gamma's: at the bigger post-fix label size, 60px of travel is no longer
// enough headroom for two ~28px-tall boxes to fully separate plus margin.
// Scale the cap by the tallest measured rect THIS TICK against the
// original ~15px baseline height the 60px default was tuned against (a
// 24px-font single-line bubble's own line-height at the OLD, undersized
// ~6-8px rendered scale) -- never shrinks below the default, only grows
// when labels render bigger than that baseline.
const NUDGE_BASELINE_HEIGHT_PX = 15;

// SECOND FIX (same pass, read live from overview-read.png at 1:1 after the
// first height-only cap landed): Coach/Chef/the BRAIN plaque were STILL
// faded. Root cause -- the height-only formula only budgets for a SINGLE
// same-priority neighbor to clear, but labelDeclutter.ts's own worst case
// (see its "chain of 4" test) is every LOWER-precedence label needing to
// clear EVERY already-placed one stacked before it: the i-th label (0-
// indexed within its collision) needs dy up to i*height. The real overview
// hub crowds up to ~9 labels at once (Gamma + up to 3 live-agent bubbles +
// 4 persona desks [Chef/Scout/Coach/Treasurer] + 1 BRAIN plaque), so the
// LAST one in priority order can need up to 8*height of travel -- the
// height-only cap (a small constant multiple of ONE label's height) was
// never going to cover that. Budget by both dimensions: height (bigger
// label = more per-step room needed) AND how many labels are actually
// registered this tick (more labels = a longer worst-case chain), so a
// quiet scene keeps the tight, unchanged-close-cam-friendly default while
// a crowded hub actually gets enough room for every label to clear.
const NUDGE_CHAIN_MARGIN = 1.25; // headroom above the exact worst-case chain length

const TICK_HZ = 10;
// Smoothing factor per tick (not per second -- ticks are already fixed at
// 10Hz via useThrottledFrame) -- 0.4 settles a fresh target in ~3-4 ticks
// (~300-400ms), fast enough to read as responsive, slow enough that a
// walking character's own small per-tick rect drift never reads as a snap.
const SMOOTH_FACTOR = 0.4;

export default function LabelDeclutterManager(): null {
  // Scratch vector, reused every tick -- zero per-tick allocation (matches
  // Agent.tsx/LiveAgents.tsx's own `bubbleDelta` scratch-vector convention).
  const scratch = useRef(new THREE.Vector3());

  // useThree() gives one-time access to the live camera/gl-size getters;
  // reading `.getState()` inside the frame callback (rather than
  // destructuring camera/size here) keeps this component from re-rendering
  // when either changes -- same "read the store imperatively" discipline
  // as every other per-frame hook in this file tree.
  const store = useThree((s) => s);

  useThrottledFrame((t) => {
    const registry = getLabelRegistry();
    if (registry.size === 0) return;
    const diagOn = isMotionDiagEnabled();
    const perfStart = diagOn ? performance.now() : 0;
    const { camera, size } = store;
    const camPos = camera.position;

    const rects: LabelRect[] = [];
    const measured = new Map<string, { naturalX: number; naturalY: number; width: number; height: number; scale: number }>();

    for (const entry of registry.values()) {
      const wrapperEl = entry.wrapperRef.current;
      const measureEl = entry.measureRef.current;
      if (!wrapperEl || !measureEl) continue;
      // ROOT-CAUSE FIX (see RegisteredLabel.measureRef's own comment):
      // SIZE/POSITION come from `measureEl` (the label's own inner,
      // already-scaled bubble/plaque node) -- its own getBoundingClientRect
      // reflects any transform ON IT (bubbleCounterScale), which the OUTER
      // `wrapperEl` could never see since a descendant's transform doesn't
      // resize an ancestor's layout box. `wrapperEl` is used ONLY to derive
      // the ancestor (drei distanceFactor) scale we must divide by to turn
      // a desired SCREEN-pixel offset into the right LOCAL transform units
      // for `wrapperEl` itself (translate on an ancestor of measureEl still
      // composes correctly regardless of measureEl's own extra scale).
      const wrapperRect = wrapperEl.getBoundingClientRect();
      const measureRect = measureEl.getBoundingClientRect();
      if (measureRect.width === 0 && measureRect.height === 0) continue; // not yet laid out this tick
      const offsetWidth = wrapperEl.offsetWidth || wrapperRect.width || 1;
      const ancestorScale = offsetWidth > 0 ? wrapperRect.width / offsetWidth : 1;
      const prevScreenDx = entry.lastLocalDx * ancestorScale;
      const prevScreenDy = entry.lastLocalDy * ancestorScale;
      const naturalX = measureRect.left - prevScreenDx;
      const naturalY = measureRect.top - prevScreenDy;

      const rawPos = entry.getWorldPos();
      const wx = Array.isArray(rawPos) ? rawPos[0] : rawPos.x;
      const wy = Array.isArray(rawPos) ? rawPos[1] : rawPos.y;
      const wz = Array.isArray(rawPos) ? rawPos[2] : rawPos.z;
      scratch.current.set(wx, wy, wz);
      const distance = scratch.current.distanceTo(camPos);

      measured.set(entry.id, { naturalX, naturalY, width: measureRect.width, height: measureRect.height, scale: ancestorScale });
      rects.push({
        id: entry.id, priority: entry.priority, distance, x: naturalX, y: naturalY, width: measureRect.width, height: measureRect.height,
        orderGroup: entry.orderGroup, orderKey: entry.orderKey,
      });
    }

    if (rects.length === 0) {
      if (diagOn) recordTickCost(performance.now() - perfStart);
      setLevelPlaquesBelowFloor(false);
      return;
    }

    // LEGIBILITY-FLOOR bridge (see legibilityFloor.ts's own header): this
    // is the ONE place in the tree that measures every price plaque's REAL
    // on-screen height each tick, so it is also the one place that can
    // tell HoloChart.tsx's summary-plaque fallback whether any of its own
    // individual plaques just got faded for being too small to read.
    setLevelPlaquesBelowFloor(rects.some((r) => isHoloPricePlaqueId(r.id) && r.height < MIN_LEGIBLE_PX));
    // See this file's own header (NUDGE_BASELINE_HEIGHT_PX + the SECOND FIX
    // note above it): grow the nudge cap by BOTH how much bigger the
    // tallest label this tick is than the tuned baseline, AND how many
    // labels are actually registered (the real worst-case chain length,
    // since labelDeclutter.ts's own resolver can need the LAST label in
    // priority order to clear every one placed before it). Never shrinks
    // below the default -- a quiet scene with 1-2 labels keeps the exact
    // close-camera behavior this pass must not regress.
    const tallestHeight = rects.reduce((max, r) => Math.max(max, r.height), 0);
    const heightRatio = tallestHeight > NUDGE_BASELINE_HEIGHT_PX ? tallestHeight / NUDGE_BASELINE_HEIGHT_PX : 1;
    const worstCaseChainPx = tallestHeight * rects.length * NUDGE_CHAIN_MARGIN;
    const maxNudgePx = Math.max(DEFAULT_MAX_NUDGE_PX * heightRatio, worstCaseChainPx, DEFAULT_MAX_NUDGE_PX);
    const obstacles = readObstacleRects();
    const offsets = resolveLabelOffsets(rects, maxNudgePx, DEFAULT_FADE_OPACITY, obstacles);

    // NEVER-LERP-INTO-OVERLAP FIX (see labelDeclutter.ts's own header on
    // `smoothLabelOffsetAvoidingOverlap` for the full evidence + mechanism):
    // build, once per tick, every label's TARGET-resolved rect (its natural
    // rect shifted by the resolver's own dx/dy for this tick -- the
    // resolver has already proven these are mutually collision-free) plus
    // every static obstacle rect, so each label's smoothing step below can
    // test its lerped candidate against where everyone else is actually
    // settling this tick, not just against last tick's positions.
    const targetPlacedRects: (OverlapRect & { id: string })[] = rects.map((r) => {
      const o = offsets.get(r.id) ?? { dx: 0, dy: 0, opacity: 1 };
      return { id: r.id, x: r.x + o.dx, y: r.y + o.dy, width: r.width, height: r.height };
    });
    const obstacleRectsOnly: OverlapRect[] = obstacles.map((o) => ({ x: o.x, y: o.y, width: o.width, height: o.height }));

    for (const entry of registry.values()) {
      const m = measured.get(entry.id);
      const el = entry.wrapperRef.current;
      if (!m || !el) continue;
      const target = offsets.get(entry.id) ?? { dx: 0, dy: 0, opacity: 1 };
      const prevScreenDx = entry.lastLocalDx * m.scale;
      const prevScreenDy = entry.lastLocalDy * m.scale;
      const others: OverlapRect[] = obstacleRectsOnly.concat(
        targetPlacedRects.filter((p) => p.id !== entry.id),
      );
      const { dx: smoothedScreenDx, dy: smoothedScreenDy } = smoothLabelOffsetAvoidingOverlap(
        { x: m.naturalX, y: m.naturalY, width: m.width, height: m.height },
        prevScreenDx, prevScreenDy, target.dx, target.dy, SMOOTH_FACTOR, others,
      );
      const localDx = m.scale > 0 ? smoothedScreenDx / m.scale : 0;
      const localDy = m.scale > 0 ? smoothedScreenDy / m.scale : 0;
      entry.lastLocalDx = localDx;
      entry.lastLocalDy = localDy;
      el.style.transform = Math.abs(localDx) > 0.5 || Math.abs(localDy) > 0.5
        ? `translate(${localDx.toFixed(2)}px, ${localDy.toFixed(2)}px)`
        : "";
      el.style.opacity = target.opacity.toFixed(2);
    }

    if (diagOn) recordTickCost(performance.now() - perfStart);
    void size; // referenced for clarity/future use (screen-bound clamping); not needed by the algorithm today
    void t;
  }, TICK_HZ);

  return null;
}

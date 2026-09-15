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
import { resolveLabelOffsets, type LabelRect } from "./labelDeclutter";
import { getLabelRegistry } from "./useLabelDeclutter";

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
    const { camera, size } = store;
    const camPos = camera.position;

    const rects: LabelRect[] = [];
    const measured = new Map<string, { naturalX: number; naturalY: number; width: number; height: number; scale: number }>();

    for (const entry of registry.values()) {
      const el = entry.wrapperRef.current;
      if (!el) continue;
      const domRect = el.getBoundingClientRect();
      if (domRect.width === 0 && domRect.height === 0) continue; // not yet laid out this tick
      const offsetWidth = el.offsetWidth || domRect.width || 1;
      // Ancestor (drei distanceFactor) scale -- translateY on THIS wrapper
      // doesn't affect its own offsetWidth, so this ratio isolates purely
      // the ancestor's scale even after we've already applied our own
      // transform on a prior tick. See this file's own header.
      const ancestorScale = offsetWidth > 0 ? domRect.width / offsetWidth : 1;
      const prevScreenDy = entry.lastLocalDy * ancestorScale;
      const naturalX = domRect.left;
      const naturalY = domRect.top - prevScreenDy;

      const rawPos = entry.getWorldPos();
      const wx = Array.isArray(rawPos) ? rawPos[0] : rawPos.x;
      const wy = Array.isArray(rawPos) ? rawPos[1] : rawPos.y;
      const wz = Array.isArray(rawPos) ? rawPos[2] : rawPos.z;
      scratch.current.set(wx, wy, wz);
      const distance = scratch.current.distanceTo(camPos);

      measured.set(entry.id, { naturalX, naturalY, width: domRect.width, height: domRect.height, scale: ancestorScale });
      rects.push({ id: entry.id, priority: entry.priority, distance, x: naturalX, y: naturalY, width: domRect.width, height: domRect.height });
    }

    if (rects.length === 0) return;
    const offsets = resolveLabelOffsets(rects);

    for (const entry of registry.values()) {
      const m = measured.get(entry.id);
      const el = entry.wrapperRef.current;
      if (!m || !el) continue;
      const target = offsets.get(entry.id) ?? { dy: 0, opacity: 1 };
      const targetScreenDy = target.dy;
      const prevScreenDy = entry.lastLocalDy * m.scale;
      const smoothedScreenDy = prevScreenDy + (targetScreenDy - prevScreenDy) * SMOOTH_FACTOR;
      const localDy = m.scale > 0 ? smoothedScreenDy / m.scale : 0;
      entry.lastLocalDy = localDy;
      el.style.transform = Math.abs(localDy) > 0.5 ? `translateY(${localDy.toFixed(2)}px)` : "";
      el.style.opacity = target.opacity.toFixed(2);
    }

    void size; // referenced for clarity/future use (screen-bound clamping); not needed by the algorithm today
    void t;
  }, TICK_HZ);

  return null;
}

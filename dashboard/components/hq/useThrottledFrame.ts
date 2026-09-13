"use client";

import { useRef } from "react";
import { useFrame } from "@react-three/fiber";

/**
 * Calls `callback(elapsedTime, dt)` at most `hz` times per second, gated off
 * the frame clock's own elapsedTime (never `Date.now()`/`performance.now()`
 * allocations, never per-frame object creation). This is the "frameloop
 * always + skip frames via a clock accumulator" throttle the TV performance
 * budget calls for, factored into one hook so every component that needs
 * throttled STATE-MACHINE logic (Agent, Courier) doesn't hand-roll the same
 * ref+comparison. Cheap continuous math (rotation = t * speed) doesn't need
 * this at all -- it's fine to compute every RAF tick directly from
 * state.clock.elapsedTime in a plain useFrame.
 */
export function useThrottledFrame(
  callback: (elapsedTime: number, dt: number) => void,
  hz: number,
): void {
  const last = useRef(0);
  const interval = 1 / hz;
  useFrame((state) => {
    const t = state.clock.elapsedTime;
    if (t - last.current < interval) return;
    const dt = t - last.current;
    last.current = t;
    callback(t, dt);
  });
}

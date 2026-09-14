"use client";

import { useRef, useState } from "react";
import type { CSSProperties } from "react";
import { useThree } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import { useThrottledFrame } from "./useThrottledFrame";

export interface ActivityBubbleCandidate {
  key: string;
  position: [number, number, number];
  /** null = nothing to show right now (parked lane, IDLE persona, etc) --
   * excluded from every ranking below, never rendered as an empty bubble. */
  text: string | null;
  /** RED health/status -- always outranks a non-urgent bubble at the same
   * distance, per the brief's "RED -> '!'+reason" callout getting its own
   * priority, not just its own text prefix. */
  urgent?: boolean;
}

interface ActivityBubbleLayerProps {
  candidates: ActivityBubbleCandidate[];
}

const FADE_SECONDS = 20;
const MAX_VISIBLE = 6;
const _camPos = new THREE.Vector3();
const _candPos = new THREE.Vector3();

/**
 * Pass B ("what they are doing", 2026-09-13): one Html bubble per working
 * character, text sourced entirely from real evidence -- Scene.tsx builds
 * `candidates` from row.evidence / persona.recentOutput, never invented
 * copy. This layer owns exactly the presentation-layer rules the brief
 * spells out: a bubble shows for FADE_SECONDS after its OWN text last
 * changed (re-showing on change, per the spec), and only the MAX_VISIBLE
 * nearest-to-camera bubbles among those still "fresh" actually render, so
 * a packed scene never buries the viewer in floating text. All per-frame
 * work below is plain ref bookkeeping (this file's own "state for discrete
 * moments, refs for continuous" convention, matching Agent.tsx/BrainCore.tsx)
 * -- the one React state (`visibleKeys`) only updates when the VISIBLE SET
 * itself actually changes, not every throttled tick.
 */
export default function ActivityBubbleLayer({ candidates }: ActivityBubbleLayerProps) {
  const { camera } = useThree();
  const lastTextRef = useRef<Map<string, string>>(new Map());
  const showUntilRef = useRef<Map<string, number>>(new Map());
  const [visibleKeys, setVisibleKeys] = useState<Set<string>>(new Set());

  useThrottledFrame((elapsedTime) => {
    for (const c of candidates) {
      if (!c.text) continue;
      if (lastTextRef.current.get(c.key) !== c.text) {
        lastTextRef.current.set(c.key, c.text);
        showUntilRef.current.set(c.key, elapsedTime + FADE_SECONDS);
      }
    }

    _camPos.copy(camera.position);
    const fresh = candidates.filter((c) => c.text && (showUntilRef.current.get(c.key) ?? 0) > elapsedTime);
    fresh.sort((a, b) => {
      if (!!a.urgent !== !!b.urgent) return a.urgent ? -1 : 1;
      _candPos.set(a.position[0], a.position[1], a.position[2]);
      const da = _camPos.distanceToSquared(_candPos);
      _candPos.set(b.position[0], b.position[1], b.position[2]);
      const db = _camPos.distanceToSquared(_candPos);
      return da - db;
    });

    const next = new Set(fresh.slice(0, MAX_VISIBLE).map((c) => c.key));
    setVisibleKeys((prev) => {
      if (prev.size === next.size && [...prev].every((k) => next.has(k))) return prev;
      return next;
    });
  }, 5);

  const visible = candidates.filter((c) => c.text && visibleKeys.has(c.key));

  return (
    <>
      {visible.map((c) => (
        <Html key={c.key} position={c.position} center distanceFactor={9} style={{ pointerEvents: "none" }}>
          <div
            className="hq-beam"
            style={{ "--beam-color": c.urgent ? "#ff3b3b" : "#22d3ee", borderRadius: 6 } as CSSProperties}
          >
            <div
              style={{
                fontFamily: "system-ui, sans-serif", color: c.urgent ? "#ffdede" : "#dff3ff",
                fontSize: 19, fontWeight: c.urgent ? 800 : 500,
                background: c.urgent ? "rgba(60,10,10,0.82)" : "rgba(3,4,10,0.72)",
                padding: "4px 12px", borderRadius: 5, whiteSpace: "nowrap",
              }}
            >
              {c.text}
            </div>
          </div>
        </Html>
      ))}
    </>
  );
}

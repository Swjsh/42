"use client";

import { useEffect, useMemo, useRef } from "react";
import type { CSSProperties } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import { createScreenCanvas, drawScreenLines } from "./palette";

// ─── World-4 fix (2026-09-14, P2: "FLOATING LANE LABELS... still hover
// mid-air in the overview... replace with IN-WORLD SIGNS") ─────────────────
// Root cause: StationModule.tsx's only signage was a single always-visible
// <Html> plaque -- drei's Html is a screen-space DOM overlay whose
// `distanceFactor` keeps it a CONSTANT apparent size regardless of world
// distance, which is exactly what reads as "hovering", disconnected from
// the geometry it's meant to label. Fix: a REAL mesh (a canvas-textured
// plane, the same "draw once on content change" technique DeskScreen.tsx
// already uses for desk screens) mounted flush on the bay's own hub-facing
// wall -- it shrinks/foreshortens with real perspective like every other
// piece of the set, so it reads as a sign ON the building, not a label
// floating in front of it. The OLD always-visible Html label is kept
// (parked/live styling both preserved byte-for-byte) but demoted to a
// close-up DETAIL overlay that only fades in within FADE_FAR world units of
// the camera -- see the useFrame below for the zero-allocation distance
// check. Design references (3 choices): ENVIRONMENT-PLAN.md's own World-4
// section -- dark edge-lit panel body, health color on a thin border only
// (never a filled wash), short high-contrast text.

const SIGN_WIDTH = 1.7;
const SIGN_HEIGHT = 0.85;
const SIGN_BORDER = 0.07;

// Fade band for the close-up detail label: full opacity within FADE_NEAR
// world units of the camera, zero beyond FADE_FAR, linear in between --
// "the Html label only fades in when the camera is within ~14u" (P2).
const FADE_NEAR = 11;
const FADE_FAR = 14;
const FADE_NEAR_SQ = FADE_NEAR * FADE_NEAR;
const FADE_FAR_SQ = FADE_FAR * FADE_FAR;

interface BaySignProps {
  /** Local position within the bay's own already-positioned+rotated group
   * (StationModule.tsx's call site) -- the SAME anchor the old Html label
   * used, so the sign lands exactly where "above the doorway" was already
   * tuned. */
  position: [number, number, number];
  /** The SAME anchor point in WORLD space, precomputed once by the caller
   * (StationModule.tsx already has `position`/`rotationY` and reuses
   * palette.ts#localToWorld, the same helper Scene.tsx uses for agent
   * homes) -- passed in rather than recomputed here so this component's own
   * useFrame distance check never allocates a Vector3 per frame. */
  worldPosition: [number, number, number];
  laneName: string;
  stateWord: string;
  color: string;
  parked: boolean;
  dimFactor: number;
}

/**
 * One in-world department sign: a health-colored border plane + a
 * canvas-texture face (lane name + state word, redrawn ONLY when that
 * content string changes -- never per-frame, matching DeskScreen.tsx's own
 * discipline) mounted on the bay's hub-facing wall, plus the previously-
 * always-visible Html detail label demoted to a distance-gated close-up
 * overlay (opacity driven by a ref mutation in useFrame, never React state
 * -- zero re-renders from camera movement).
 */
export default function BaySign({ position, worldPosition, laneName, stateWord, color, parked, dimFactor }: BaySignProps) {
  const { canvas, texture } = useMemo(() => createScreenCanvas(), []);

  // First capture (world4-p2-default-1908.png) showed drawScreenLines' own
  // `title` row (15px, muted #5f7a99 -- tuned for a close-up desk screen,
  // DeskScreen.tsx's only prior caller) reading as basically blank at real
  // sign-reading distance. Fixed by NOT using the title slot at all: both
  // the (shortened) lane name and the state word go through `lines`
  // instead, where size/color are both this caller's own choice -- "lane
  // name (short), state word" (P2) as two equally-legible rows, not a
  // header + a body.
  const shortLane = laneName.includes(" (") ? laneName.slice(0, laneName.indexOf(" (")) : laneName;
  const contentKey = `${shortLane}::${stateWord}::${color}`;
  useEffect(() => {
    drawScreenLines(canvas, texture, null, [
      { text: shortLane, color: "#dff3ff", size: 34 },
      { text: stateWord.toUpperCase(), color, size: 28 },
    ]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvas, texture, contentKey]);

  useEffect(() => () => texture.dispose(), [texture]);

  // Module-scope-equivalent scratch: ONE Vector3 per mounted sign (8 bays,
  // built once on mount, never recreated) -- the useFrame below reads it
  // every frame via distanceToSquared (a plain scalar return, no
  // allocation) rather than constructing a fresh Vector3 each tick.
  const worldPosVec = useMemo(
    () => new THREE.Vector3(worldPosition[0], worldPosition[1], worldPosition[2]),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [worldPosition[0], worldPosition[1], worldPosition[2]],
  );
  const detailRef = useRef<HTMLDivElement>(null);

  useFrame((state) => {
    const el = detailRef.current;
    if (!el) return;
    const distSq = state.camera.position.distanceToSquared(worldPosVec);
    const opacity =
      distSq <= FADE_NEAR_SQ ? 1 : distSq >= FADE_FAR_SQ ? 0 : 1 - (Math.sqrt(distSq) - FADE_NEAR) / (FADE_FAR - FADE_NEAR);
    el.style.opacity = String(opacity * dimFactor);
  });

  return (
    <group position={position} rotation={[0, Math.PI, 0]}>
      {/* Health-colored border: a slightly larger opaque plane BEHIND the
          canvas face, read as a thin lit edge -- "edge-lit, not filled"
          (ENVIRONMENT-PLAN.md World-4 reference pass). */}
      <mesh position={[0, 0, -0.008]}>
        <planeGeometry args={[SIGN_WIDTH + SIGN_BORDER, SIGN_HEIGHT + SIGN_BORDER]} />
        <meshBasicMaterial color={color} toneMapped={false} />
      </mesh>
      <mesh>
        <planeGeometry args={[SIGN_WIDTH, SIGN_HEIGHT]} />
        <meshBasicMaterial map={texture} toneMapped={false} />
      </mesh>

      {/* Close-up detail label -- BYTE-IDENTICAL styling to the old
          always-visible plaque (parked vs live), only now gated by
          `opacity` (ref-driven, set in the useFrame above, never a React
          re-render) instead of being permanently on screen. `pointerEvents:
          "none"` already made it non-interactive, so a near-zero opacity
          fully "hides" it without an extra visibility toggle. */}
      <Html position={[0, 0, 0.02]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
        <div ref={detailRef} style={{ opacity: 0 }}>
          {parked ? (
            <div
              style={{
                fontFamily: "system-ui, sans-serif", color: "#5c7aa0",
                background: "rgba(3,4,10,0.6)", padding: "4px 10px", borderRadius: 6,
                whiteSpace: "nowrap", textAlign: "center",
              }}
            >
              <div style={{ fontSize: 20, fontWeight: 600, lineHeight: 1.15 }}>{laneName}</div>
            </div>
          ) : (
            <div className="hq-beam" style={{ "--beam-color": color, borderRadius: 8 } as CSSProperties}>
              <div
                style={{
                  fontFamily: "system-ui, sans-serif", color: "#dff3ff",
                  background: "rgba(3,4,10,0.75)", padding: "6px 16px", borderRadius: 7,
                  whiteSpace: "nowrap", textAlign: "center",
                }}
              >
                <div style={{ fontSize: 32, fontWeight: 800, lineHeight: 1.15 }}>
                  {laneName}
                  <span style={{ fontWeight: 600, color: "#7f93b0" }}> · {stateWord}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </Html>
    </group>
  );
}

"use client";

import { useEffect, useMemo } from "react";
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
// floating in front of it.
//
// ─── POLISH-1 P2 fix (2026-09-14, coordinator, real capture tonight --
// "three copies of the same name") ──────────────────────────────────────
// The pass above ALSO kept the old always-visible Html label alive here, as
// a close-up "detail" overlay (opacity-faded in within ~11-14 world units of
// the camera) -- confirmed against a real capture this session
// (polish1-p2-bay0-before.png, `?preset=bay0`): the close-up view showed the
// wall sign's own canvas text ("SPY 0DTE co... / ARMED-PAPER"), THIS
// component's own close-up Html directly on top of it ("SPY 0DTE core ·
// armed-paper", `.hq-beam`-bordered), AND the lane agent's own head bubble
// above both (Agent.tsx, "SPY 0DTE core · armed-paper · go-live gat...") --
// three simultaneous copies of the identical name+state, the redundant one
// being THIS component's own close-up label (the wall-sign mesh below
// already carries the lane name + state word via its own canvas texture,
// and the head bubble already carries name + live action -- neither needs a
// third Html duplicating either). Removed outright, along with the
// now-dead distance-fade machinery that existed only to drive its opacity
// (`worldPosition` prop, `FADE_NEAR`/`FADE_FAR`, the per-frame
// distanceToSquared check, `detailRef`) and the now-unused `parked` prop
// (the wall sign mesh itself was never parked-aware -- only the removed
// close-up label branched on it). `dimFactor` -- previously read ONLY by
// the removed label's own opacity -- is kept and now applied to this
// component's own two meshes instead, so "GPU RESERVED -- J IS GAMING"
// still dims the wall sign rather than silently leaving it at full
// brightness once the Html it used to drive is gone.

const SIGN_WIDTH = 1.7;
const SIGN_HEIGHT = 0.85;
const SIGN_BORDER = 0.07;

interface BaySignProps {
  /** Local position within the bay's own already-positioned+rotated group
   * (StationModule.tsx's call site) -- the SAME anchor the old Html label
   * used, so the sign lands exactly where "above the doorway" was already
   * tuned. */
  position: [number, number, number];
  laneName: string;
  stateWord: string;
  color: string;
  /** Dims this sign's own two meshes during "GPU RESERVED -- J IS GAMING"
   * mode -- the SAME dimFactor every other hub/bay surface fades under
   * (BrainCore's glow sprite, HoloChart's whole group, StationModule's own
   * moduleDim). See this file's own POLISH-1 P2 header for why this moved
   * here from the now-removed close-up label. */
  dimFactor: number;
}

/**
 * One in-world department sign: a health-colored border plane + a
 * canvas-texture face (lane name + state word, redrawn ONLY when that
 * content string changes -- never per-frame, matching DeskScreen.tsx's own
 * discipline) mounted on the bay's hub-facing wall.
 */
export default function BaySign({ position, laneName, stateWord, color, dimFactor }: BaySignProps) {
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

  return (
    <group position={position} rotation={[0, Math.PI, 0]}>
      {/* Health-colored border: a slightly larger opaque plane BEHIND the
          canvas face, read as a thin lit edge -- "edge-lit, not filled"
          (ENVIRONMENT-PLAN.md World-4 reference pass). */}
      <mesh position={[0, 0, -0.008]}>
        <planeGeometry args={[SIGN_WIDTH + SIGN_BORDER, SIGN_HEIGHT + SIGN_BORDER]} />
        <meshBasicMaterial color={color} toneMapped={false} transparent opacity={dimFactor} />
      </mesh>
      {/* SCENE-AUDIT pass (2026-09-15): informational screen tag -- bay
          signs are explicitly out of this pass's readability-FAIL scope
          (task: "desk screens/bay signs are informational, not FAIL"). */}
      <mesh userData={{ hqKind: "screen", hqLabel: "bay-sign", hqFaceLocalNormal: [0, 0, 1], hqInformational: true }}>
        <planeGeometry args={[SIGN_WIDTH, SIGN_HEIGHT]} />
        <meshBasicMaterial map={texture} toneMapped={false} transparent opacity={dimFactor} />
      </mesh>
    </group>
  );
}

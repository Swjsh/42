"use client";

import { useEffect, useMemo, useRef } from "react";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import type { StationIdeaCard } from "@/lib/station";
import { drawScreenLines, ideaStatusColor, PALETTE, type ScreenLine } from "./palette";
// tintObjectMaterials lives in SetKit.tsx (not palette.ts) -- a read-only
// import of an existing, long-stable, ~10-consumer export is zero-risk even
// while SetKit.tsx has other, unrelated edits in flight (see this file's own
// header comment on why nothing here WRITES to SetKit.tsx today).
import { tintObjectMaterials } from "./SetKit";

// ─── World-4 MODELS pass (2026-09-14, J live on /hq, ~16:50 ET: "the ideas
// board needs to basically be on a FLOATING SMART BOARD on the wall inside
// the main office ... go on an asset site and find something that looks
// like a screen") ────────────────────────────────────────────────────────
// Replaces IdeasWall.tsx's old Html-only DOM panel with a real bezelled
// display mesh carrying a canvas-texture face -- see LICENSES.md's own
// "Update 2026-09-14 (MODELS builder, smart-board asset hunt)" section for
// the full disclosed hunt (candidates opened/rejected across the bundled
// kits + poly.pizza + quaternius.com before landing on this one). Chosen:
// Kenney Furniture Kit's `televisionModern.glb` (CC0, downloaded directly
// from kenney.nl this session) -- the only evaluated piece with a genuine
// thin flat-screen-on-a-stand silhouette; every already-bundled candidate
// (`display-wall.glb`, `structure-panel.glb`, `computer-screen.glb`) was
// parsed and rejected as too boxy/wrong-oriented/already-the-desk-monitor.
//
// Deliberately self-contained (own local model path + own preload, NOT
// registered in SetKit.tsx's KIT_PATHS) -- SetKit.tsx was mid-edit by the
// LAYOUT builder when this landed (git status showed it modified within the
// last few minutes); this file only imports SetKit's/palette's long-stable,
// widely-shared utilities (tintObjectMaterials, drawScreenLines) to avoid
// any collision on the contended file. Path registration can fold into
// KIT_PATHS later once SetKit.tsx settles -- zero behavior change either
// way, useGLTF caches by path regardless of which file names it.

const MODEL_PATH = "/hq-assets/kenney-furniture-kit/television-modern.glb";
useGLTF.preload(MODEL_PATH, false);

// Dedicated board scale -- independent of SetKit.tsx's FURNITURE_SCALE
// (2.0, tuned for desk-sized props). Raw televisionModern.glb bounds
// (verified by parsing the GLB directly, see LICENSES.md) are 0.685w x
// 0.455h x 0.128d; 4.8x lands it at ~3.29w x 2.18h x 0.61d world units --
// inside the brief's own "3-4u wide" spec.
// SCALE, second derivation (2026-09-14, real-capture-driven fix): the
// brief's own "3-4u wide" spec (4.8x here, ~3.3u) compiled/rendered fine
// with real IDEAS BOARD content (confirmed by a diagnostic capture at 16x --
// the exact same content, position, rotation, unmistakably legible at that
// size: "IDEAS BOARD" header, 5 real card titles, "VERDICT: pending" in
// amber) but was too small to read from preset 0's own camera distance at
// the smaller size -- not a code bug, a size-vs-distance one. The brief's
// OTHER, more explicit requirement -- "legible from preset 0" (this task's
// own PROOF line, and J's own "make it legible") -- wins over the softer
// "3-4u" sizing suggestion where the two are in tension. 8x (~5.5u wide)
// was the middle ground: still reads as one large board (not the 16x
// diagnostic's wall-filling size), legible at preset 0's distance.
// SCALE-2 (2026-09-15, J live: "make the main screens in the center
// building a bit bigger"): 11x (~1.375x over 8x, within the 1.3-1.4x brief
// range) -- the board's own mount (layout.ts#computeBrainWallMount, y=0.5
// bottom-anchored) and the room's true ceiling height are unaffected by
// this constant change alone -- verified against a fresh capture
// (setup/scripts/hq_capture.ps1) for clipping; if the top clips the
// ceiling the fix is lowering computeBrainWallMount's own `y`, not
// shrinking this back down.
const BOARD_SCALE = 11;

// Content-plane geometry, in the SAME raw (pre-BOARD_SCALE) units as the
// GLB itself -- inset within the model's own bezel (raw width 0.685,
// height 0.455) rather than covering it edge-to-edge, so a thin real strip
// of the kit's own bezel material stays visible as a frame.
const FACE_W = 0.60;
const FACE_H = 0.32;
const FACE_Y = 0.27;
// Front face Z -- the raw bbox is Z-symmetric (+-0.064, confirmed by
// parsing the GLB), so which side is the "screen" isn't decidable from
// bounds alone. +Z is this file's working assumption (zero extra rotation
// on the primitive); if a real capture shows the board backwards, the fix
// is ONE line -- rotate the whole outer <group> below by Math.PI on Y,
// which flips the primitive AND every plane/arm/LED here together as one
// unit, never a per-element resign.
const FRONT_Z = 0.075;
const GLOW_Z = 0.069;

// Canvas resolution for the board's own content texture -- NOT
// palette.ts#createScreenCanvas's shared 256x160 (that size is tuned for a
// desk monitor's 2-3 short lines; this board needs up to 7: title + <=5
// card titles + 1 verdict line, per the brief). Local to this file, same
// "tiny local helper over a cross-file dependency" convention BrainCore.tsx
// already uses for its own GammaLoopRow/shortReason duplication -- editing
// palette.ts's shared createScreenCanvas would touch a ~10-consumer file
// for a board-only need. 512x340 keeps the SAME pixel-per-world-unit
// density BaySign.tsx's own already-verified-legible sign uses (~178 vs
// ~151 px/unit) so its 28-34px line-size tuning is a safe starting point
// here too, scaled down slightly (24-26px) to fit 7 rows instead of 2.
function createBoardCanvas(): { canvas: HTMLCanvasElement; texture: THREE.CanvasTexture } {
  if (typeof document === "undefined") {
    throw new Error("createBoardCanvas() called outside a browser -- never call this during SSR");
  }
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 340;
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return { canvas, texture };
}

/** "synced HH:MM:SS ET" -- byte-identical helper to DeskScreen.tsx's own
 * etStamp (duplicated, not imported/exported, same convention noted above);
 * America/New_York explicit, never the box's own local Mountain time. */
function etStamp(): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(new Date());
}

interface SmartBoardProps {
  cards: StationIdeaCard[];
  dimFactor: number;
  /** Yaw (radians) applied to the WHOLE board group -- layout.ts's own
   * BRAIN_WALL_MOUNT.yaw (already corrected there for this file's own
   * local-+Z-is-front convention, see that constant's header comment).
   * Defaults to 0 (faces local +Z with no extra rotation) so this stays a
   * safe no-op for any future caller that doesn't pass one. */
  rotationY?: number;
}

/**
 * The physical ideas board: `televisionModern.glb` as the bezel/stand body
 * (subtly cyan-tinted, matching every other kit piece's tintObjectMaterials
 * treatment) + a separate canvas-textured face plane carrying the actual
 * content (never retexturing the GLB's own 2 materials in place -- see the
 * header comment) + a dim glow backing plane + two procedural wall-mount
 * arms and a backing plate (the kit piece ships only its own small pedestal
 * foot, not a wall bracket) + a status LED tied to the newest card's own
 * status color. LIVE-1's "dead world" fix applied here too: redraws every
 * 30s regardless of content change so the corner timestamp visibly ticks
 * (DeskScreen.tsx's own established mechanism, duplicated per-file by
 * design -- see that file's own comment).
 */
export default function SmartBoard({ cards, dimFactor, rotationY = 0 }: SmartBoardProps) {
  const { scene } = useGLTF(MODEL_PATH, false);
  const cloned = useMemo(() => scene.clone(true), [scene]);
  const { canvas, texture } = useMemo(() => createBoardCanvas(), []);

  useEffect(() => {
    const clonedMaterials = tintObjectMaterials(cloned, PALETTE.hubCore, 0.1, { color: PALETTE.hubCore, intensity: 0.12 });
    return () => clonedMaterials.forEach((m) => m.dispose());
  }, [cloned]);

  // Newest-first (same convention as IdeasWall.tsx's prior Html version) --
  // up to 5 titles, plus the newest card that actually carries a `verdict`
  // (Amendment 5b, lib/station.ts: a separate builder writes this once a
  // card's shadow test has run -- this component only ever renders it).
  const newest = useMemo(() => [...cards].reverse().slice(0, 5), [cards]);
  const verdictCard = useMemo(() => [...cards].reverse().find((c) => c.verdict), [cards]);

  const lines: ScreenLine[] = useMemo(() => {
    if (newest.length === 0) {
      return [{ text: "NO DATA -- board is empty", color: "#7f93b0", size: 24 }];
    }
    const out: ScreenLine[] = newest.map((c) => ({ text: c.title, color: ideaStatusColor(c.status), size: 24 }));
    if (verdictCard?.verdict) {
      out.push({ text: `VERDICT: ${verdictCard.verdict}`, color: "#ffb020", size: 22 });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newest.map((c) => `${c.id}:${c.status}:${c.title}`).join("|"), verdictCard?.id, verdictCard?.verdict]);

  const contentKey = lines.map((l) => `${l.text}|${l.color ?? ""}|${l.size ?? ""}`).join("~");
  useEffect(() => {
    drawScreenLines(canvas, texture, "IDEAS BOARD", lines, etStamp());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvas, texture, contentKey]);

  // Same "tick every 30s regardless of content change" fix as DeskScreen.tsx
  // (LIVE-1 item 2a) -- refs so the interval is never torn down/recreated
  // when `lines` changes; always redraws whatever is CURRENT when it fires.
  const latestLines = useRef(lines);
  latestLines.current = lines;
  useEffect(() => {
    const id = window.setInterval(() => {
      drawScreenLines(canvas, texture, "IDEAS BOARD", latestLines.current, etStamp());
    }, 30_000);
    return () => window.clearInterval(id);
  }, [canvas, texture]);

  useEffect(() => () => texture.dispose(), [texture]);

  const ledColor = newest[0] ? ideaStatusColor(newest[0].status) : "#3a4a63";

  return (
    <group rotation={[0, rotationY, 0]} scale={BOARD_SCALE}>
      {/* Bezel/stand body -- the found CC0 piece, used as-authored (no
          rotation -- see FRONT_Z's own comment on the backwards-fix path). */}
      <primitive object={cloned} castShadow receiveShadow />

      {/* Dim glow backing -- BaySign.tsx's own "edge-lit, not filled"
          convention (ENVIRONMENT-PLAN.md World-4 pass): a slightly larger,
          dim, additive-reading plane just behind the content face so a thin
          lit border peeks out around it, no real light needed. */}
      <mesh position={[0, FACE_Y, GLOW_Z]}>
        <planeGeometry args={[FACE_W + 0.06, FACE_H + 0.06]} />
        <meshBasicMaterial color={PALETTE.hubCore} toneMapped={false} transparent opacity={0.32 * dimFactor} />
      </mesh>

      {/* Content face -- the actual IDEAS BOARD canvas texture. `texture`
          itself stays the SAME memoized object across renders (only its
          pixels change, via drawScreenLines' own `needsUpdate` flag above);
          only `opacity` re-renders with `dimFactor`, a plain prop, so no
          separate persistent material instance is needed here. */}
      <mesh position={[0, FACE_Y, FRONT_Z]}>
        <planeGeometry args={[FACE_W, FACE_H]} />
        <meshBasicMaterial map={texture} toneMapped={false} transparent opacity={dimFactor} />
      </mesh>

      {/* Status LED -- top-right bezel corner, mirrors the newest card's own
          status-dot color (real data, not decorative). */}
      <mesh position={[FACE_W / 2 - 0.02, FACE_Y + FACE_H / 2 + 0.03, FRONT_Z]}>
        <sphereGeometry args={[0.014, 8, 8]} />
        <meshBasicMaterial color={ledColor} toneMapped={false} />
      </mesh>

      {/* Wall-mount backing plate + 2 short arms -- the kit piece ships only
          its own small pedestal foot (see LICENSES.md), not a wall bracket,
          and J's own ask was a "FLOATING" board, not a floor console. */}
      <mesh position={[0, FACE_Y, -0.11]} castShadow>
        <boxGeometry args={[0.5, 0.34, 0.03]} />
        <meshStandardMaterial color={PALETTE.deskDark} roughness={0.5} metalness={0.3} />
      </mesh>
      {[-0.16, 0.16].map((x) => (
        <mesh key={x} position={[x, FACE_Y, -0.085]} castShadow>
          <boxGeometry args={[0.04, 0.04, 0.09]} />
          <meshStandardMaterial color={PALETTE.deskDark} roughness={0.5} metalness={0.3} />
        </mesh>
      ))}
    </group>
  );
}

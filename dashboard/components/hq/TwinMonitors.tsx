"use client";

import { useEffect, useMemo, useRef } from "react";
import { Billboard } from "@react-three/drei";
import * as THREE from "three";
import type { StationIdeaCard } from "@/lib/station";
import type { FleetPnlLive } from "@/lib/hq-fleet-pnl-live-pure";
import { drawScreenLines, ideaStatusColor, PALETTE, type ScreenLine } from "./palette";

// ─── TWIN-MONITORS pass (2026-09-15, BUILD worker, J top-down feedback:
// "two large flat monitors, side by side, in the brain-wall corner...
// facing the camera and readable... crooked and unreadable" [about the old
// SmartBoard.tsx]) ──────────────────────────────────────────────────────
// Replaces SmartBoard.tsx (kept on disk/git-history, unmounted -- IdeasWall
// no longer renders it) with a floor-standing pedestal + two flat screens
// that BILLBOARD to the active camera every frame (drei's own <Billboard>,
// which re-orients via a lookAt-style rotation, not an animated spin/loop --
// camera-driven orientation is explicitly allowed under the HQ face rules,
// see CLAUDE.md's own "no TV wake, motion=events" lesson: this reacts to
// the VIEWER's camera, not an autonomous idle animation). Root cause the old
// board could never fully fix: a WALL-MOUNTED, pitched panel reads correctly
// from exactly one fixed viewing angle -- this scene has TWO very different
// ones in active use (the default ~38.7deg-azimuth/~35deg-elevation orbit,
// AND a genuine top-down preset), and no single fixed pitch serves both
// (see layout.ts's own TWIN-MONITORS header + ENVIRONMENT-PLAN.md's Design
// pass 2026-09-15, section B, for the full geometry writeup). A billboarded
// flat pair is flat-on to the orbit camera AND lies face-up to a top-down
// one, by construction, with zero per-viewport special-casing.
//
// Geometry (all in world units, matching this scene's 1u~=1m convention):
// each screen 2.0w x 1.2h, 0.2u gap between them (2.2u total footprint,
// comfortably inside the 45deg corner's available wall run -- see
// layout.ts#MONITOR_STAND_RADIUS's own collision-check comment), bottom
// edge at y=1.5 (so the SCREEN CENTER lands at 1.5+1.2/2=2.1, below a
// standing character's own eye height ~1.6-1.7 the way a real wall display
// mounts per ENVIRONMENT-PLAN.md section B's source 1). Content canvas
// 512px wide (spec: ">=28px text in a 512-wide canvas, <=6 lines per
// screen, headline scale only") -- reuses palette.ts#drawScreenLines
// (generic over canvas size, already proven by SmartBoard.tsx's own 512x340
// canvas) rather than a third copy of the same drawing loop.
//
// Draw-call budget (task ceiling: <=8 new meshes, the old SmartBoard's own
// ~7 + 2): pedestal (1 combined post+base box) + per-screen bezel box (2)
// + per-screen content plane (2) + ONE shared glow-backing plane spanning
// both screens+gap (1, the same "edge-lit, not filled" convention
// BaySign.tsx/SmartBoard.tsx already use, sized once rather than per-screen
// to stay under budget) = 6 meshes total, 1 under the +2 ceiling.

// MONITORS-READABLE pass (2026-09-15, orchestrator captures design-default-
// 1910.png/design-topdown-1910.png): at the ~48u overview camdist a 2.0u
// screen measured ~100px wide with ~8px text -- structurally unreadable
// regardless of content, and the BRAIN plaque sat directly over this same
// screen region (see the LABELS-pass fix in BrainCore.tsx, same session,
// which shrinks that plaque and is most of the fix for the overlap; the
// size bump below is the rest -- bigger glass + bigger text). Sized up
// 60% (2.0->3.2w / 1.2->1.8h) -- top edge lands at SCREEN_BOTTOM_Y(1.2) +
// 1.8 = 3.0u, under SetKit.tsx's true room ceiling (raw 4.25 *
// ARCHITECTURE_SCALE_HUB(0.75) ~= 3.19u per layout.ts's own
// computeBrainWallMount header) with a ~0.19u margin -- the group's
// <Billboard> can only pitch the panel MORE vertical toward the default
// orbit's elevation (~35deg) than the worst-case fully-upright pose used
// for this calc, so 3.0u is a safe upper bound, not a typical one. Bottom
// dropped 1.5->1.2 to buy back some of that headroom (pedestal shrinks by
// the same 0.3u). Angular footprint at the new width, MONITOR_STAND_RADIUS
// 5.6 (layout.ts): atan((2*OFFSET_X+3.2)/2 / 5.6) ~= 31deg either side of
// the 45deg segment center -- this is the FIXED PEDESTAL's own thin post
// (0.3u wide, effectively 0 angular width) that stays put; only the
// billboarded GLASS sweeps that arc, well clear of the desk ring (centred
// r5.5 on segments 1-3, this stand sits on the free segment 0) and clear
// of HubInterior's cable greeble in height (cables are a floor-level
// greeble; the glass floats at y 1.2-3.0) even though its 28deg angle now
// falls inside the glass's angular sweep -- no radial/vertical overlap.
const SCREEN_WIDTH = 3.2;
const SCREEN_HEIGHT = 1.8;
const SCREEN_GAP = 0.25;
const SCREEN_BOTTOM_Y = 1.2;
const SCREEN_CENTER_Y = SCREEN_BOTTOM_Y + SCREEN_HEIGHT / 2;
const SCREEN_OFFSET_X = (SCREEN_WIDTH + SCREEN_GAP) / 2;
const BEZEL_MARGIN = 0.05;
const CONTENT_Z = 0.035;
const GLOW_Z = 0.03;
const BEZEL_DEPTH = 0.05;

const PEDESTAL_HEIGHT = SCREEN_BOTTOM_Y - 0.05;
const PEDESTAL_WIDTH = 0.3;
const PEDESTAL_BASE_DEPTH = 0.4;
// MONITORS-READABLE pass: palette.ts#drawScreenLines' own header (small
// desk screens, DeskScreen.tsx/HubInterior.tsx) was legible at 15px; on
// TwinMonitors' much bigger 3.2u glass at overview distance the same
// header measured illegible in a real capture while the 64px body lines
// below it read fine (monitors-overview-1948.png). 36 -- clearly bigger
// than the desk-screen default, still small enough to read as a header
// row rather than competing with the 64px body content for attention.
const MONITOR_TITLE_SIZE = 36;

function createMonitorCanvas(): { canvas: HTMLCanvasElement; texture: THREE.CanvasTexture } {
  if (typeof document === "undefined") {
    throw new Error("createMonitorCanvas() called outside a browser -- never call this during SSR");
  }
  const canvas = document.createElement("canvas");
  // MONITORS-READABLE pass: 512x288 -> 768x432 (matches the new 3.2x1.8
  // screen aspect exactly, same 1.778 ratio as before) so the headline-
  // scale text below (size>=56, spec floor 64 on the biggest line) has
  // physical canvas pixels to render into rather than being upscaled soft.
  canvas.width = 768;
  canvas.height = 432;
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return { canvas, texture };
}

/** "synced HH:MM:SS ET" -- byte-identical convention to
 * DeskScreen.tsx/SmartBoard.tsx's own duplicated helper (this file's own
 * copy, same "tiny local duplication over a cross-file dependency"
 * discipline already established in this tree). */
function etStamp(): string {
  return new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).format(new Date());
}

/** One flat screen: bezel body (a plain box, no GLB -- the "flat monitor"
 * silhouette needs no more geometry than that) + a canvas-textured content
 * plane, redrawn on content change and every 30s regardless (LIVE-1's
 * "dead world" fix, same mechanism DeskScreen.tsx/SmartBoard.tsx already
 * use) so the corner timestamp visibly ticks. */
function FlatScreen({ x, title, lines, dimFactor }: { x: number; title: string; lines: ScreenLine[]; dimFactor: number }) {
  const { canvas, texture } = useMemo(() => createMonitorCanvas(), []);
  const contentKey = lines.map((l) => `${l.text}|${l.color ?? ""}|${l.size ?? ""}`).join("~");
  useEffect(() => {
    drawScreenLines(canvas, texture, title, lines, etStamp(), MONITOR_TITLE_SIZE);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvas, texture, title, contentKey]);

  const latestLines = useRef(lines);
  const latestTitle = useRef(title);
  latestLines.current = lines;
  latestTitle.current = title;
  useEffect(() => {
    const id = window.setInterval(() => {
      drawScreenLines(canvas, texture, latestTitle.current, latestLines.current, etStamp(), MONITOR_TITLE_SIZE);
    }, 30_000);
    return () => window.clearInterval(id);
  }, [canvas, texture]);

  useEffect(() => () => texture.dispose(), [texture]);

  return (
    <group position={[x, 0, 0]}>
      {/* Bezel body -- flat box, dark, faintly metallic. */}
      <mesh position={[0, 0, -BEZEL_DEPTH / 2]} castShadow>
        <boxGeometry args={[SCREEN_WIDTH, SCREEN_HEIGHT, BEZEL_DEPTH]} />
        <meshStandardMaterial color={PALETTE.deskDark} roughness={0.5} metalness={0.3} />
      </mesh>
      {/* Content face. SCENE-AUDIT tag: this is the ONE screen family this
          pass's task explicitly requires to be readable ("two large flat
          monitors... facing the camera and readable") -- hqInformational
          stays unset (readable:true) so hq-scene-audit.ts's screen_facing
          check actually gates on it. Local normal +Z, the plane's own
          default front face; the parent <Billboard> re-orients the WHOLE
          group (this mesh included) to face whichever camera is active
          every frame, so the traversal's world-transformed normal is
          exactly the camera-facing direction by construction. */}
      <mesh position={[0, 0, CONTENT_Z]} userData={{ hqKind: "screen", hqLabel: "twin-monitor", hqFaceLocalNormal: [0, 0, 1] }}>
        <planeGeometry args={[SCREEN_WIDTH - BEZEL_MARGIN * 2, SCREEN_HEIGHT - BEZEL_MARGIN * 2]} />
        <meshBasicMaterial map={texture} toneMapped={false} transparent opacity={dimFactor} />
      </mesh>
    </group>
  );
}

interface TwinMonitorsProps {
  cards: StationIdeaCard[];
  fleetPnl: FleetPnlLive | null;
  dimFactor: number;
  /** Stand's floor position (layout.ts#MONITOR_MOUNT.standPosition). */
  position: [number, number, number];
  /** Yaw for the FIXED (non-billboarded) pedestal only -- the screen pair
   * re-orients to the camera independently via <Billboard>. */
  standYaw: number;
}

export default function TwinMonitors({ cards, fleetPnl, dimFactor, position, standYaw }: TwinMonitorsProps) {
  // LEFT screen -- the same IDEAS BOARD content SmartBoard.tsx used to show
  // (newest-first), same source of truth (lib/station.ts's own
  // StationIdeaCard, never a second reader). MONITORS-READABLE pass: capped
  // 5 titles -> 2 (+ 1 verdict line = <=3 data lines, per this pass's own
  // "headline-scale content only" spec) and bumped size 30/28 -> 64 (spec
  // floor) -- at 5 lines of body text this screen was never going to read
  // at any plausible viewing distance; fewer, bigger lines is the fix, not
  // a smaller font.
  const newest = useMemo(() => [...cards].reverse().slice(0, 2), [cards]);
  const verdictCard = useMemo(() => [...cards].reverse().find((c) => c.verdict), [cards]);
  const ideasLines: ScreenLine[] = useMemo(() => {
    if (newest.length === 0) {
      return [{ text: "NO DATA -- board is empty", color: "#7f93b0", size: 56 }];
    }
    const out: ScreenLine[] = newest.map((c) => ({ text: c.title, color: ideaStatusColor(c.status), size: 64 }));
    if (verdictCard?.verdict) {
      out.push({ text: `VERDICT: ${verdictCard.verdict}`, color: "#ffb020", size: 64 });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [newest.map((c) => `${c.id}:${c.status}:${c.title}`).join("|"), verdictCard?.id, verdictCard?.verdict]);

  // RIGHT screen -- "FLEET P&L (gross)": the EXACT same data/derivation
  // Hud.tsx's own fleet-P&L panel reads (data.trading.fleetPnl, built by
  // lib/hq-fleet-pnl-live-pure.ts's fills-ledger FIFO math) -- never a
  // second computation, per this task's own "reuse the exact same
  // derivation, never a second one" instruction. MONITORS-READABLE pass:
  // same 5->2 arms + BOOK total (<=3 data lines) / 26-28 -> 64px bump as
  // the ideas screen, same reasoning.
  const pnlLines: ScreenLine[] = useMemo(() => {
    if (!fleetPnl || fleetPnl.arms.length === 0) {
      return [{ text: "no fleet data", color: "#7f93b0", size: 56 }];
    }
    const rows = fleetPnl.arms.slice(0, 2).map((a): ScreenLine => {
      if (a.error) return { text: `${a.armId}: unavailable`, color: "#7f93b0", size: 64 };
      const sign = a.realizedUsd >= 0 ? "+" : "-";
      return {
        text: `${a.armId} ${sign}$${Math.abs(Math.round(a.realizedUsd))} (${a.trades}t)`,
        color: a.realizedUsd > 0 ? "#22ff88" : a.realizedUsd < 0 ? "#ff6b6b" : "#7f93b0",
        size: 64,
      };
    });
    const bookSign = fleetPnl.bookRealizedUsd >= 0 ? "+" : "-";
    rows.push({
      text: `BOOK ${bookSign}$${Math.abs(Math.round(fleetPnl.bookRealizedUsd))}`,
      color: fleetPnl.bookRealizedUsd > 0 ? "#22ff88" : fleetPnl.bookRealizedUsd < 0 ? "#ff6b6b" : "#dff3ff",
      size: 64,
    });
    return rows;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fleetPnl?.bookRealizedUsd, fleetPnl?.arms.map((a) => `${a.armId}:${a.realizedUsd}:${a.trades}:${a.error ?? ""}`).join("|")]);

  return (
    <group position={position}>
      {/* Pedestal -- fixed yaw, never billboards (a floor stand shouldn't
          swivel with the camera). One combined post+base box, per this
          file's own draw-call budget. */}
      <mesh position={[0, PEDESTAL_HEIGHT / 2, 0]} rotation={[0, standYaw, 0]} castShadow receiveShadow>
        <boxGeometry args={[PEDESTAL_WIDTH, PEDESTAL_HEIGHT, PEDESTAL_BASE_DEPTH]} />
        <meshStandardMaterial color={PALETTE.deskDark} roughness={0.6} metalness={0.35} />
      </mesh>

      {/* Screen pair -- ONE Billboard group so both screens always move as a
          single rigid unit (never splayed independently), re-orienting to
          whichever camera is active every frame. lockX/Y/Z all false: a
          full re-orient is what makes this read flat-on from the default
          orbit camera AND lie face-up under the top-down preset -- a
          locked-axis billboard (e.g. Y-only) would only solve one of the
          two views. */}
      <Billboard position={[0, SCREEN_CENTER_Y, 0]} follow lockX={false} lockY={false} lockZ={false}>
        {/* Shared glow backing -- BaySign.tsx/SmartBoard.tsx's own
            "edge-lit, not filled" convention: one dim additive plane behind
            BOTH screens (spanning the gap too) so a thin lit border reads
            around the pair without a per-screen glow mesh (draw-call
            budget). */}
        <mesh position={[0, 0, GLOW_Z]}>
          <planeGeometry args={[SCREEN_OFFSET_X * 2 + SCREEN_WIDTH, SCREEN_HEIGHT + 0.08]} />
          <meshBasicMaterial color={PALETTE.hubCore} toneMapped={false} transparent opacity={0.28 * dimFactor} />
        </mesh>
        <FlatScreen x={-SCREEN_OFFSET_X} title="IDEAS BOARD" lines={ideasLines} dimFactor={dimFactor} />
        <FlatScreen x={SCREEN_OFFSET_X} title="FLEET P&L (GROSS)" lines={pnlLines} dimFactor={dimFactor} />
      </Billboard>
    </group>
  );
}

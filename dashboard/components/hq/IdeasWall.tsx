"use client";

import { Html } from "@react-three/drei";
import type { StationIdeaCard } from "@/lib/station";
import { ideaStatusColor } from "./palette";

interface IdeasWallProps {
  cards: StationIdeaCard[];
  position: [number, number, number];
  dimFactor: number;
}

/**
 * A holographic panel near the hub listing the newest <=5 idea cards. Text
 * is DOM via <Html> (never drei <Text>, which fetches a font -- forbidden at
 * runtime on the TV). The backing plane mesh (0.06 opacity, essentially
 * invisible) was dropped in the TV-perf pass -- pure overdraw cost for zero
 * visible value; the Html div's own background carries the panel look. Still
 * Html (never a canvas texture) after the World-4 legibility pass below --
 * hitting the size/contrast bar didn't need one, and DOM has zero per-frame
 * redraw cost to guard against by construction (there's no texture to
 * accidentally redraw every frame).
 *
 * World-4 fix (2026-09-14, P3: "make the IDEAS BOARD panel legible at
 * preset 0" -- the old 260px-wide panel at a flat 12px was, by design,
 * built for a close-up read, not "legible from the default overview
 * distance" this task actually asks for). Sized per this codebase's own
 * established 10-foot-readability family (StationModule's bay labels
 * 26-32px, BrainCore's plaque 34px, gauge caption 26px) instead of
 * reinventing a scale, and per this file's own ENVIRONMENT-PLAN.md
 * World-4 reference pass: dark edge-lit panel body (unchanged), a capped
 * accent BAR across the top (not a uniform border -- the "segmented/
 * bracketed" hologram-panel reading from that pass's references) in the
 * neutral hub-cyan accent this panel's own sibling plaques already use
 * (never a health color -- 5 different cards have no single health to
 * show), and fewer/bigger lines over cramming more rows in.
 */
export default function IdeasWall({ cards, position, dimFactor }: IdeasWallProps) {
  const newest = [...cards].reverse().slice(0, 5);

  return (
    <group position={position}>
      {/* Local +0.7 (not a WALL_POS change in Scene.tsx): the panel's own
          DOM box grew taller with the bigger font below, and `center`-ing a
          taller Html box on the SAME anchor point pushes its bottom edge
          further down toward BrainCore's plaque stack -- shifting just this
          local offset up keeps every OTHER WALL_POS consumer (Courier's
          flight target, palette.ts's "ideas-wall" purposeful-walk target)
          byte-identical. */}
      <Html position={[0, 0.7, 0.02]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
        <div
          style={{
            width: 460, fontFamily: "system-ui, sans-serif", color: "#dff3ff",
            background: "rgba(3,4,10,0.8)", border: "1px solid rgba(122,217,255,0.25)",
            borderTop: "3px solid #7ad9ff", borderRadius: 8, padding: "10px 18px 14px", opacity: dimFactor,
          }}
        >
          <div style={{ fontSize: 20, fontWeight: 800, color: "#7ad9ff", marginBottom: 8, letterSpacing: 1.5 }}>IDEAS BOARD</div>
          {newest.length === 0 ? (
            <div style={{ fontSize: 22, color: "#7f93b0" }}>NO DATA -- board is empty</div>
          ) : (
            newest.map((c) => (
              // LIVE-1 item 2d (2026-09-14): "the ideas wall cards flip when
              // a new card lands" -- `.hq-card-flip` (Hud.tsx's shared
              // style) replays its mount animation ONLY when this exact
              // `key` (c.id) is genuinely new to the DOM; an existing card
              // shifting position in the list re-uses its node (React's own
              // keyed-list reconciliation) and never replays it.
              <div key={c.id} className="hq-card-flip" style={{ fontSize: 28, marginBottom: 6, display: "flex", gap: 10, alignItems: "baseline" }}>
                <span style={{ width: 12, height: 12, borderRadius: 999, background: ideaStatusColor(c.status), flexShrink: 0 }} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {c.title.length > 70 ? c.title.slice(0, 67) + "..." : c.title}
                </span>
              </div>
            ))
          )}
        </div>
      </Html>
    </group>
  );
}

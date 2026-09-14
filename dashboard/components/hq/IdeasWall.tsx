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
 * A holographic panel near the hub listing the newest <=6 idea cards. Text
 * is DOM via <Html> (never drei <Text>, which fetches a font -- forbidden at
 * runtime on the TV). The backing plane mesh (0.06 opacity, essentially
 * invisible) was dropped in the TV-perf pass -- pure overdraw cost for zero
 * visible value; the Html div's own background carries the panel look.
 */
export default function IdeasWall({ cards, position, dimFactor }: IdeasWallProps) {
  const newest = [...cards].reverse().slice(0, 6);

  return (
    <group position={position}>
      <Html position={[0, 0, 0.02]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
        <div
          style={{
            width: 260, fontFamily: "system-ui, sans-serif", color: "#dff3ff",
            background: "rgba(3,4,10,0.55)", border: "1px solid rgba(122,217,255,0.3)",
            borderRadius: 8, padding: "8px 12px", opacity: dimFactor,
          }}
        >
          <div style={{ fontSize: 12, color: "#7f93b0", marginBottom: 4, letterSpacing: 1 }}>IDEAS BOARD</div>
          {newest.length === 0 ? (
            <div style={{ fontSize: 12, color: "#7f93b0" }}>NO DATA -- board is empty</div>
          ) : (
            newest.map((c) => (
              // LIVE-1 item 2d (2026-09-14): "the ideas wall cards flip when
              // a new card lands" -- `.hq-card-flip` (Hud.tsx's shared
              // style) replays its mount animation ONLY when this exact
              // `key` (c.id) is genuinely new to the DOM; an existing card
              // shifting position in the list re-uses its node (React's own
              // keyed-list reconciliation) and never replays it.
              <div key={c.id} className="hq-card-flip" style={{ fontSize: 12, marginBottom: 3, display: "flex", gap: 6, alignItems: "baseline" }}>
                <span style={{ width: 7, height: 7, borderRadius: 999, background: ideaStatusColor(c.status), flexShrink: 0 }} />
                <span style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {c.title.length > 44 ? c.title.slice(0, 41) + "..." : c.title}
                </span>
              </div>
            ))
          )}
        </div>
      </Html>
    </group>
  );
}

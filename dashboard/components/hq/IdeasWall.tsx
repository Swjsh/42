"use client";

import type { StationIdeaCard } from "@/lib/station";
import SmartBoard from "./SmartBoard";

interface IdeasWallProps {
  cards: StationIdeaCard[];
  position: [number, number, number];
  dimFactor: number;
}

// ─── World-4 MODELS pass (2026-09-14, J live on /hq: "the ideas board needs
// to basically be on a FLOATING SMART BOARD on the wall inside the main
// office") -- supersedes the prior Html-only DOM panel (kept verbatim in
// git history) with a real bezelled display mesh (SmartBoard.tsx) carrying
// a canvas-texture face. The Html version's own reasoning ("DOM has zero
// per-frame redraw cost") is still true but no longer the point: J's ask was
// explicitly for a PHYSICAL MODEL that reads as a board on the wall, which a
// screen-space DOM overlay -- constant apparent size regardless of world
// distance, exactly what reads as "hovering" -- structurally cannot be. ────

/** Local offset, relative to Scene.tsx's own WALL_POS prop (today [0,3.4,0]
 * -- NOT changed here, per this task's own instruction to use today's
 * position and leave a clear constant for the LAYOUT builder to re-point
 * once a real hub-wall mount point is exported from Scene.tsx/layout.ts).
 *
 * WALL_POS itself turns out to be unusable AS-IS for a real mesh: it sits at
 * world Y=3.4, above HUB_CEILING_Y (SetKit.tsx, ~2.79 -- itself already a
 * 0.4 margin below the room-large.glb shell's own true ceiling, raw height
 * 4.25 * ARCHITECTURE_SCALE_HUB 0.75 = 3.19) -- a solid board there would
 * poke through the hub's own ceiling mesh. Its X/Z (0,0) is hub-CENTER,
 * directly through BrainCore's own core sphere/glow sprite (~2.1 world-unit
 * reach) if lowered to a sane mounting height instead.
 *
 * This offset relocates the board to world [0, 0.5, -6.9]: radius 6.9 from
 * hub center (inside HUB_WALL_RADIUS=7.5, ~0.6 clear of the wall for the
 * mount arms), straight back along -Z (angle 270 deg) -- inside the ~130deg
 * arc Scene.tsx's own ARC_CENTER/ARC_SPAN(230deg)/PERSONA_RING_RADIUS(6.5)
 * geometry leaves genuinely empty (no persona desk, no lane corridor: both
 * rings are confined to the SAME 230deg front arc, read directly from
 * Scene.tsx this session, not guessed), and well outside the all-hands
 * ring-around-the-core radius (3.2). Bottom-anchored at world Y=0.5 (the
 * model's own local origin sits at its base, per every other kit piece's
 * convention) puts the top at ~2.68 -- clear of HUB_CEILING_Y with margin.
 *
 * TODO(LAYOUT): once a real "brain wall" position/angle is exported from
 * Scene.tsx or layout.ts, either re-point WALL_POS itself to sit flush
 * against it (and zero this offset out), or ping MODELS with the new
 * constant name -- this number was derived from today's geometry, not
 * hardcoded blind. Exported so Courier.tsx (the small bot that visibly
 * "carries" a card from the hub up to the wall on every new/changed idea
 * card) can fly to the board's REAL position instead of the old bare
 * WALL_POS -- see that file's own import of this constant. */
export const SMART_BOARD_LOCAL_OFFSET: [number, number, number] = [0, -2.9, -6.9];

export default function IdeasWall({ cards, position, dimFactor }: IdeasWallProps) {
  return (
    <group position={position}>
      <group position={SMART_BOARD_LOCAL_OFFSET}>
        <SmartBoard cards={cards} dimFactor={dimFactor} />
      </group>
    </group>
  );
}

"use client";

import type { StationIdeaCard } from "@/lib/station";
import { BRAIN_WALL_MOUNT } from "./layout";
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

// Scene.tsx's own WALL_POS value ([0,3.4,0], unchanged by this pass) -- a
// duplicated literal, not an import, because Scene.tsx imports THIS module
// (IdeasWall -> SmartBoard is one leg of its render tree) and WALL_POS is a
// module-scope `const` there, not exported; importing it back would risk a
// cycle. Same "tiny local duplication over a cross-file dependency"
// convention this file tree already uses elsewhere (BrainCore.tsx's own
// GammaLoopRow/shortReason, etc.) -- if Scene.tsx's WALL_POS value ever
// changes, this needs a matching update (Courier.tsx's own `wall` prop
// already carries the REAL current value at runtime, so only this literal,
// used purely to compute a group offset below, needs re-syncing by hand).
const WALL_POS_SCENE_VALUE: [number, number, number] = [0, 3.4, 0];

/** Local offset, relative to Scene.tsx's own WALL_POS prop -- the board's
 * REAL mount point is layout.ts#BRAIN_WALL_MOUNT (added 2026-09-14,
 * coordinator-authorized edit, once LAYOUT's campus-cross rebuild made the
 * OLD interim position -- world [0,0.5,-6.9], this session's own earlier
 * empty-arc derivation -- obsolete: that arc no longer exists in the new
 * layout). BRAIN_WALL_MOUNT already accounts for the hub's real ceiling
 * height and BrainCore's core/glow reach (see its own header comment in
 * layout.ts) -- this file only computes the OFFSET from WALL_POS needed to
 * land there, since Scene.tsx's `<IdeasWall position={WALL_POS}>` call
 * still wraps this component's whole output in that anchor. */
export const SMART_BOARD_LOCAL_OFFSET: [number, number, number] = [
  BRAIN_WALL_MOUNT.position[0] - WALL_POS_SCENE_VALUE[0],
  BRAIN_WALL_MOUNT.position[1] - WALL_POS_SCENE_VALUE[1],
  BRAIN_WALL_MOUNT.position[2] - WALL_POS_SCENE_VALUE[2],
];

export default function IdeasWall({ cards, position, dimFactor }: IdeasWallProps) {
  return (
    <group position={position}>
      <group position={SMART_BOARD_LOCAL_OFFSET}>
        <SmartBoard cards={cards} dimFactor={dimFactor} rotationY={BRAIN_WALL_MOUNT.yaw} />
      </group>
    </group>
  );
}

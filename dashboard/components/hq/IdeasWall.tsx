"use client";

import type { StationIdeaCard } from "@/lib/station";
import type { FleetPnlLive } from "@/lib/hq-fleet-pnl-live-pure";
import { MONITOR_MOUNT } from "./layout";
import TwinMonitors from "./TwinMonitors";

interface IdeasWallProps {
  cards: StationIdeaCard[];
  fleetPnl: FleetPnlLive | null;
  position: [number, number, number];
  dimFactor: number;
}

// ─── World-4 MODELS pass (2026-09-14, J live on /hq: "the ideas board needs
// to basically be on a FLOATING SMART BOARD on the wall inside the main
// office") -- originally replaced the prior Html-only DOM panel with a
// bezelled display mesh (SmartBoard.tsx). SUPERSEDED by the TWIN-MONITORS
// pass (2026-09-15, J top-down feedback: "crooked and unreadable... two
// large flat monitors, side by side... facing the camera"): SmartBoard.tsx
// is kept on disk/git-history, unmounted -- this file now mounts
// TwinMonitors.tsx instead, at layout.ts#MONITOR_MOUNT (a floor-standing
// pair that billboards to the active camera every frame, see that
// component's own header for why a fixed wall-pitch could never serve both
// the default orbit camera AND a top-down preset at once). ────────────────

// Scene.tsx's own WALL_POS value ([0,3.4,0], unchanged by this pass) -- a
// duplicated literal, not an import, because Scene.tsx imports THIS module
// (IdeasWall -> TwinMonitors is one leg of its render tree) and WALL_POS is
// a module-scope `const` there, not exported; importing it back would risk
// a cycle. Same "tiny local duplication over a cross-file dependency"
// convention this file tree already uses elsewhere.
const WALL_POS_SCENE_VALUE: [number, number, number] = [0, 3.4, 0];

/** Local offset, relative to Scene.tsx's own WALL_POS prop, landing at
 * layout.ts#MONITOR_MOUNT.standPosition (a FLOOR point, y=0 -- unlike the
 * old SMART_BOARD_LOCAL_OFFSET this replaces, which mounted at y=2.6 on the
 * wall). Scene.tsx's `<IdeasWall position={WALL_POS}>` call still wraps
 * this component's whole output in that anchor, so this only computes the
 * offset needed to land at the real mount point. */
export const MONITOR_STAND_LOCAL_OFFSET: [number, number, number] = [
  MONITOR_MOUNT.standPosition[0] - WALL_POS_SCENE_VALUE[0],
  MONITOR_MOUNT.standPosition[1] - WALL_POS_SCENE_VALUE[1],
  MONITOR_MOUNT.standPosition[2] - WALL_POS_SCENE_VALUE[2],
];

export default function IdeasWall({ cards, fleetPnl, position, dimFactor }: IdeasWallProps) {
  return (
    <group position={position}>
      <group position={MONITOR_STAND_LOCAL_OFFSET}>
        <TwinMonitors cards={cards} fleetPnl={fleetPnl} dimFactor={dimFactor} position={[0, 0, 0]} standYaw={MONITOR_MOUNT.standYaw} />
      </group>
    </group>
  );
}

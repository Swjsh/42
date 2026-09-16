"use client";

import { useGLTF } from "@react-three/drei";
import { KitProp } from "./SetKit";

// ─── COMMAND-CENTER pass (2026-09-16, HUB-LAYOUT-PROPS worker) ─────────────
// J's ask: "make the floating 2 large monitors a bit bigger... maybe add a
// few more things." ENVIRONMENT-PLAN.md's own "Command-center pass
// 2026-09-16" section D shortlisted 6 unreferenced GLBs from the bundled
// kits to dress the hub as an ops room. Re-checked against KIT_PATHS
// (SetKit.tsx) before writing anything here -- 4 of those 6
// (computer-screen.glb/computer.glb/chair.glb/display-wall.glb) are ALREADY
// wired: every persona wall desk already renders a computer + computer-
// screen via SetKit.tsx#DeskCluster (unconditional, not content-gated), and
// display-wall.glb already has 2 live instances (HubInterior.tsx's
// SectorsTradingPanel/VitalsPanel). Section D's own "add a screen to desks
// missing one" gap does not exist in the current tree -- this file adds
// only the two GENUINELY unreferenced pieces (grep-verified: `structure-
// panel.glb`/`plant-small.glb` have zero call sites outside SetKit.tsx's
// own KIT_PATHS table before this pass). Section D's "3rd display-wall on
// the opposite wall" is a J-taste call per this pass's own instructions --
// deliberately NOT built here.
//
// SELF-CORRECTION (real hq_live_probe.py run, this session): a first
// placement (structure panels at r4.7/+-9deg off the monitor segment's own
// 45deg center, plants at r4.0 flanking HUB_TABLE_RADIUS) looked clear by
// hand-checked math against the table/pedestal/cables/wall-panels -- but
// the LIVE probe's own desk_clearance check FAILed 3/3: both structure
// panels and one plant actually overlapped GAMMA'S OWN DESK (SetKit.tsx's
// "desk" pool, checkDeskClearance in lib/hq-scene-audit.ts), a real object
// this pass's hand math never modeled. Root cause: Gamma's desk (Scene.tsx
// GAMMA_RADIUS=3.4, angle~61.34deg) sits on a NON-axis-aligned yaw
// (~28.66deg, per DeskCluster's own localToWorld chain), so its real
// world-space AABB is a diagonal box reaching from roughly (1.05,3.16) to
// (3.56,5.27) -- much closer to the 45deg monitor segment than a naive
// "Gamma is at 61deg, I'm at 45deg" glance suggests. Every position below
// was RE-DERIVED against Gamma's real AABB (computed via this same
// localToWorld formula, not guessed) plus every other object in the
// segment (hub table, 6 chairs, monitor pedestal, cable clusters, the 2
// display-wall panels, the room wall, both door aisles) via a
// brute-force grid search (this session's own scratch script, not
// eyeballed), and RE-VERIFIED by a second hq_live_probe.py run after this
// fix -- see this pass's own final report for the quoted PASS line.
//
// Draw calls: 2 structure-panel (1 mesh each) + 2 plant-small (2 mesh
// primitives each, per glb_extents.mjs) = 4 objects / 6 draw calls,
// comfortably under the ceiling budget.
const STRUCTURE_PANEL_PATH = "/hq-assets/kenney-space-station-kit/structure-panel.glb";
const PLANT_SMALL_PATH = "/hq-assets/kenney-furniture-kit/plant-small.glb";
useGLTF.preload(STRUCTURE_PANEL_PATH, false);
useGLTF.preload(PLANT_SMALL_PATH, false);

function polar(radius: number, angleDeg: number): [number, number, number] {
  const a = (angleDeg * Math.PI) / 180;
  return [Math.cos(a) * radius, 0, Math.sin(a) * radius];
}

// ─── Structure-panel pair -- low console/counter accent near the monitor
// stand, moved OUT toward the wall (r6.5, vs. the stand's own r5.6) and
// skewed to angles 37deg/20deg (vs. the stand's 45deg segment-center) so
// both clear the stand's own pedestal AND stay on the side AWAY from
// Gamma's desk AABB (which reaches down to ~46.7deg at its nearest
// corner) -- margins verified this session (grid search, half-extent
// 0.425 at scale 1.0): 37deg position clears the wall by 0.575u, the
// pedestal by 0.66u, cable28 by 0.61u; 20deg position clears cable12/28 by
// 0.54u each, the sectors-panel by 1.3u; the two panels clear each other
// by 1.07u. All >=0.3u, all pinned in tests/hq-hub-layout.test.ts.
const STRUCTURE_PANEL_RADIUS = 6.5;
const STRUCTURE_PANEL_ANGLES_DEG = [37, 20];
const STRUCTURE_PANEL_SCALE = 1.0;

// ─── Small-plant pair on the table's one open flank (the low-angle side,
// AWAY from Gamma's desk, which occupies the high-angle side of this
// segment) -- section D's direct answer to "add a few more things" /
// HubInterior.tsx#HubPlants' own draw-call-budget note about staying at
// one existing instance. plant-small.glb is a DIFFERENT, distinct asset
// from that existing potted-plant.glb (raw 0.095w x 0.14h x 0.095d, ~4x
// scale per section D to read as a real plant, ~0.38-0.56u world size).
// Both positions found by the same grid search as the panels above
// (half-extent 0.19 at scale 4.0): r4.19/31.5deg clears every chair,
// the hub table, Gamma's desk AABB, and both structure panels by >=0.33u;
// r3.55/25.6deg clears the same set (including the FIRST plant) by
// >=0.33u. A true symmetric flanking pair (one on each side of the table)
// is NOT achievable here -- Gamma's desk AABB and the chair ring together
// consume the entire high-angle side of this segment; both plants sit on
// the one side that's actually open.
const PLANT_RADII = [4.19, 3.55];
const PLANT_ANGLES_DEG = [31.5, 25.6];
const PLANT_SCALE = 4.0;

export default function HubProps() {
  const panelPositions = STRUCTURE_PANEL_ANGLES_DEG.map((a) => polar(STRUCTURE_PANEL_RADIUS, a));
  const plantPositions = PLANT_RADII.map((r, i) => polar(r, PLANT_ANGLES_DEG[i]));

  return (
    <group>
      {panelPositions.map((pos, i) => (
        <KitProp
          key={`structure-panel-${i}`}
          path={STRUCTURE_PANEL_PATH}
          scale={STRUCTURE_PANEL_SCALE}
          position={pos}
          receiveShadow
          hqKind="furniture"
          hqLabel="console-accent"
        />
      ))}
      {plantPositions.map((pos, i) => (
        <KitProp
          key={`plant-small-${i}`}
          path={PLANT_SMALL_PATH}
          scale={PLANT_SCALE}
          position={pos}
          rotation={[0, i * Math.PI, 0]}
          castShadow
          receiveShadow
          hqKind="furniture"
          hqLabel="plant"
        />
      ))}
    </group>
  );
}

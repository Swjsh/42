"use client";

import { useEffect, useMemo } from "react";
import { useGLTF } from "@react-three/drei";
import * as THREE from "three";
import type { SectorsSnapshot, TradingStatus } from "@/lib/hq";
import { drawScreenLines, PALETTE, type ScreenLine } from "./palette";
import { KIT_PATHS, KitProp, FURNITURE_SCALE } from "./SetKit";
import HoloChart from "./HoloChart";

// ─── S2 hub interior pass (2026-09-14, MODELS builder) ─────────────────────
// "the hub needs to look real": a central round table + chairs for the
// all-hands, TWO real wall panels (sectors+trading -- the brief's originally
// -specced second board, real data via `sectorsSnapshot`/`trading` props,
// threaded Scene.tsx->BrainCore->here by this builder per coordinator
// direction 2026-09-14 ~17:22/17:30 ET (LAYOUT's own ownership of
// Scene.tsx/layout.ts released before that threading landed) -- and
// brain/GPU vitals, added first while those props didn't exist yet and kept
// as a distinct third panel per the coordinator's own call), cables along
// the wall base, and a lit floor ring marking the all-hands gathering
// radius. Mounted from BrainCore.tsx (this builder's own file, already
// rendered once at the hub center) -- NOT from Scene.tsx's own render tree
// directly; see this component's own placement comment for the counter-
// scale needed because BrainCore's own return wraps everything in
// <group scale={1.15}>. Panel/table/cable ANGLES were re-derived a second
// time (still 2026-09-14) once LAYOUT's campus-cross rebuild (layout.ts)
// replaced the old 8-way-ring hub this section originally targeted -- see
// BRAIN_SEGMENT_CENTER_DEG's own comment below for the current geometry.
//
// Self-contained model paths (table-large.glb, cables.glb) rather than new
// SetKit.tsx KIT_PATHS entries -- both files are ALREADY on disk (manifest.json
// lists them, downloaded in an earlier pass) but were never wired into
// KIT_PATHS; SetKit.tsx itself was mid-edit by the LAYOUT builder for most of
// this session (git status / mtime both confirmed), so this avoids adding to
// that contention. `KIT_PATHS.furniture.chair`/`FURNITURE_SCALE`/`KitProp`
// are read-only imports of long-stable, ~10-consumer exports -- safe
// regardless of LAYOUT's own unrelated edits elsewhere in that file.

const TABLE_LARGE_PATH = "/hq-assets/kenney-space-station-kit/table-large.glb";
const CABLES_PATH = "/hq-assets/kenney-modular-space-kit/cables.glb";
useGLTF.preload(TABLE_LARGE_PATH, false);
useGLTF.preload(CABLES_PATH, false);

// W2 (2026-09-14, WORLD-6 builder): "interior plants" -- real CC0 GLB
// (Kenney Furniture Kit, via kenney.nl's own zip -- see this file's own
// placement comment on HubPlants below for the radius reasoning).
const POTTED_PLANT_PATH = "/hq-assets/kenney-furniture-kit/potted-plant.glb";
useGLTF.preload(POTTED_PLANT_PATH, false);

// All positions below are WORLD-space (1:1 with Scene.tsx's own units) --
// see BrainCoreVitalsPanel's/HubInterior's own counter-scale wrapper.

// World-4 MODELS S2 pass, RE-DERIVED (2026-09-14, coordinator-authorized
// edit): the OLD "empty ~130deg arc" this file's own constants below were
// originally built against no longer exists -- LAYOUT's campus-cross
// rebuild (layout.ts) replaced the 8-way ring with 4 cardinal doorways and
// "persona desks along the 4 wall segments between doors, 2-2-2-1 with
// Gamma at the brain wall." Every position below now anchors to that SAME
// reserved "brain wall" segment layout.ts#BRAIN_WALL_MOUNT uses (center
// angle 45deg, spanning armAngle(0)=0deg..armAngle(1)=90deg -- see
// layout.ts's own header for why armIndex=0 today) instead of the old
// straight-back -Z axis.
const BRAIN_SEGMENT_CENTER_DEG = 45;

// RADII, second derivation (2026-09-14, real-capture-driven fix -- see
// layout.ts#computeBrainWallMount's own header for the full root-cause: the
// brain-wall segment is the hub's NEAR wall from the default camera, whose
// walls run the full room height, so anything flush against it sits in that
// wall's own shadow from a ~35deg-elevation view). Every radius below was
// pulled inward from this file's FIRST pass (which put the board at 6.8,
// panels at 6.8, cables at 6.7 -- all invisible in the real capture) toward
// the SAME line-of-sight-clearance math layout.ts now uses, and re-checked
// against each other for overlap at the new, closer radii.
const CHAIR_RADIUS = 1.2; // was 1.85 -- tightened so the table+chairs footprint clears the board's own front face (see TABLE_CENTER's own comment)
const CHAIR_COUNT = 6;

/** Round table + 6 chairs for the all-hands, radius 2.5 on the SAME
 * segment-center angle (45deg) the smart board itself sits on (now radius
 * 4.9, layout.ts#BRAIN_WALL_MOUNT) -- reads as a meeting table facing the
 * wall board. Table+chairs reach ~2.5+1.2+0.3(chair footprint)=4.0 outward;
 * the board's own front face reaches ~4.9-0.36=4.54 inward -- 0.54 clear.
 * Overlaps the all-hands ring-around-the-core floor marking (radius 3.2)
 * at this one angle -- accepted as a minor cosmetic overlap (a thin floor
 * ring partly under a table leg), not a walk-blocking one: the ring is
 * decorative geometry, not a collider. */
const TABLE_CENTER: [number, number, number] = [
  Math.cos((BRAIN_SEGMENT_CENTER_DEG * Math.PI) / 180) * 2.5,
  0,
  Math.sin((BRAIN_SEGMENT_CENTER_DEG * Math.PI) / 180) * 2.5,
];
const TABLE_SCALE = FURNITURE_SCALE * 0.85; // slightly under desk-scale so 6 chairs fit comfortably

// WORLD-6 (2026-09-14, W1): table-large.glb raw bbox 1.4w x 0.4h x 0.9d
// (GLB-parsed via dashboard/scripts/glb_extents.mjs this session) -- top
// surface at world Y = 0.4 * TABLE_SCALE, the HoloChart's own mount height
// below.
const TABLE_TOP_Y = 0.4 * TABLE_SCALE;

/** Cables greeble along the hub's inner wall base -- pulled in to radius 5.5
 * (from 6.7) for the same camera-visibility reason as everything else here;
 * cables.glb's own raw ~1.9x2.1 floor-cluster footprint (verified by
 * parsing the GLB directly) reads as conduit junctions, not a continuous
 * cable run, at any radius -- moving inward changes nothing about what the
 * asset itself looks like. */
const CABLE_ANGLES_DEG = [12, 45, 78];
const CABLE_RADIUS = 5.5;
const CABLE_SCALE = 0.34;

/** Floor ring marking the all-hands gathering radius (3.2, the SAME number
 * BrainCore's own pulse/ring-around-the-core comment already establishes --
 * a real, functional marking, not decoration invented from nothing). */
const GATHER_RING_RADIUS = 3.2;

function deg(d: number): number {
  return (d * Math.PI) / 180;
}

function createVitalsCanvas(): { canvas: HTMLCanvasElement; texture: THREE.CanvasTexture } {
  if (typeof document === "undefined") {
    throw new Error("createVitalsCanvas() called outside a browser -- never call this during SSR");
  }
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 176;
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return { canvas, texture };
}

interface VitalsPanelProps {
  utilPct: number | null;
  memUsedMib: number | null;
  memTotalMib: number | null;
  modelName: string | null;
}

/** Third hub wall panel -- `display-wall.glb` (already downloaded, never
 * wired into any component before this pass -- see SetKit.tsx's own
 * KIT_PATHS.furniture comment), retextured with GPU/model vitals: real data
 * BrainCore.tsx already receives as props. Coordinator call (2026-09-14,
 * after this panel was already built against the data on hand): stays
 * alongside SectorsTradingPanel below (the originally-specced "sectors
 * summary + trading strip" board, now that `sectorsSnapshot`/`trading` are
 * threaded), not replaced by it -- two real, distinct pieces of hub status,
 * two panels. */
function VitalsPanel({ utilPct, memUsedMib, memTotalMib, modelName }: VitalsPanelProps) {
  const { scene } = useGLTF(KIT_PATHS.furniture.displayWall, false);
  const cloned = useMemo(() => scene.clone(true), [scene]);
  const { canvas, texture } = useMemo(() => createVitalsCanvas(), []);
  const faceMat = useMemo(() => new THREE.MeshBasicMaterial({ map: texture, toneMapped: false }), [texture]);

  useEffect(() => {
    cloned.traverse((obj) => {
      if (obj instanceof THREE.Mesh) obj.material = faceMat;
    });
  }, [cloned, faceMat]);

  const memFrac = memUsedMib && memTotalMib ? memUsedMib / memTotalMib : null;
  const lines: ScreenLine[] = useMemo(() => {
    const out: ScreenLine[] = [
      { text: modelName ?? "no model loaded", color: "#dff3ff", size: 20 },
      { text: `GPU ${utilPct !== null ? `${Math.round(utilPct)}%` : "?"}`, color: (utilPct ?? 0) > 60 ? "#ffb020" : "#22ff88", size: 22 },
      {
        text: `MEM ${memUsedMib ?? "?"}/${memTotalMib ?? "?"} MiB`,
        color: memFrac !== null && memFrac > 0.85 ? "#ff3b3b" : "#7ad9ff",
        size: 18,
      },
    ];
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modelName, utilPct, memUsedMib, memTotalMib]);

  const contentKey = `${modelName ?? ""}|${utilPct ?? ""}|${memUsedMib ?? ""}|${memTotalMib ?? ""}`;
  useEffect(() => {
    drawScreenLines(canvas, texture, "BRAIN VITALS", lines);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvas, texture, contentKey]);

  useEffect(() => () => {
    texture.dispose();
    faceMat.dispose();
  }, [texture, faceMat]);

  // display-wall.glb raw bbox 0.4w x 0.461h x 0.384d (GLB-parsed, see
  // manifest.json) -- 2.6x lands it ~1.04w x 1.20h x 1.00d, a believable
  // second monitor-sized panel, distinct from the 3.3u-wide smart board.
  const scale = 2.6;
  return (
    <group scale={scale}>
      <primitive object={cloned} />
      <mesh position={[0, 0.24, 0.18]}>
        <planeGeometry args={[0.30, 0.20]} />
        <primitive object={faceMat} attach="material" />
      </mesh>
    </group>
  );
}

interface SectorsTradingPanelProps {
  sectorsSnapshot: SectorsSnapshot | null;
  trading: TradingStatus | null;
}

const READINESS_COLOR: Record<string, string> = { GREEN: "#22ff88", YELLOW: "#ffb020", RED: "#ff3b3b", UNKNOWN: "#7f93b0" };

/** Second hub wall panel -- the brief's ORIGINAL ask: sectors summary +
 * trading strip, as a real second board (a second `display-wall.glb`
 * instance). `sectorsSnapshot`/`trading` are optional/nullable props
 * threaded from Scene.tsx by the LAYOUT builder (coordinator, 2026-09-14
 * ~17:22 ET) -- both render an honest "waiting" placeholder when null
 * (`sectorsSnapshot` is genuinely null before CREW-RIG's first Station fire,
 * per lib/hq.ts#readSectorsSnapshot's own fail-open contract) rather than
 * fabricated numbers, and this panel simply renders whatever these props
 * currently are -- it does not poll or fetch on its own. */
function SectorsTradingPanel({ sectorsSnapshot, trading }: SectorsTradingPanelProps) {
  const { scene } = useGLTF(KIT_PATHS.furniture.displayWall, false);
  const cloned = useMemo(() => scene.clone(true), [scene]);
  const { canvas, texture } = useMemo(() => createVitalsCanvas(), []);
  const faceMat = useMemo(() => new THREE.MeshBasicMaterial({ map: texture, toneMapped: false }), [texture]);

  useEffect(() => {
    cloned.traverse((obj) => {
      if (obj instanceof THREE.Mesh) obj.material = faceMat;
    });
  }, [cloned, faceMat]);

  // Prefer whichever of safe/bold core has a row (both are null before the
  // engine's first tick of the day) -- same "first available, not always
  // safe" convention Scene.tsx's own pilotScreenLines construction uses.
  const core = trading?.core?.safe ?? trading?.core?.bold ?? null;
  const lines: ScreenLine[] = useMemo(() => {
    const out: ScreenLine[] = [];
    if (sectorsSnapshot) {
      out.push({ text: sectorsSnapshot.summary_line, color: "#dff3ff", size: 17 });
      const redCount = sectorsSnapshot.rows.filter((r) => r.health === "red").length;
      out.push({ text: `${sectorsSnapshot.rows.length} lanes, ${redCount} red`, color: redCount > 0 ? "#ff3b3b" : "#22ff88", size: 16 });
    } else {
      out.push({ text: "sectors: waiting for first fire", color: "#7f93b0", size: 16 });
    }
    if (trading) {
      out.push({
        text: `readiness ${trading.readiness.verdict}`,
        color: READINESS_COLOR[trading.readiness.verdict] ?? "#7f93b0",
        size: 18,
      });
      out.push({
        text: core ? `SPY ${core.spy ?? "?"} · VIX ${core.vix ?? "?"}` : "SPY/VIX: no core tick yet",
        color: "#7ad9ff",
        size: 16,
      });
    } else {
      out.push({ text: "trading: no data", color: "#7f93b0", size: 16 });
    }
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sectorsSnapshot?.ts_et, sectorsSnapshot?.summary_line, trading?.readiness.verdict, trading?.readiness.tsEt, core?.spy, core?.vix]);

  const contentKey = lines.map((l) => `${l.text}|${l.color ?? ""}`).join("~");
  useEffect(() => {
    drawScreenLines(canvas, texture, "SECTORS + TRADING", lines);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canvas, texture, contentKey]);

  useEffect(() => () => {
    texture.dispose();
    faceMat.dispose();
  }, [texture, faceMat]);

  // Same scale/content-plane geometry as VitalsPanel -- both are the SAME
  // display-wall.glb piece, two independent instances.
  const scale = 2.6;
  return (
    <group scale={scale}>
      <primitive object={cloned} />
      <mesh position={[0, 0.24, 0.18]}>
        <planeGeometry args={[0.30, 0.20]} />
        <primitive object={faceMat} attach="material" />
      </mesh>
    </group>
  );
}

interface HubInteriorProps {
  utilPct: number | null;
  memUsedMib: number | null;
  memTotalMib: number | null;
  modelName: string | null;
  sectorsSnapshot: SectorsSnapshot | null;
  trading: TradingStatus | null;
  /** WORLD-6 (2026-09-14, W1): "GPU RESERVED -- J IS GAMING" dim state --
   * BrainCore.tsx already receives this for its own glow sprite/memory
   * gauge; threaded one level further here so HoloChart's own materials
   * dim consistently with every other hub surface instead of staying at
   * full brightness while the rest of the room dims. */
  dimFactor: number;
}

/**
 * Everything "hub looks real" beyond BrainCore's own core/rings/plaques:
 * a round meeting table + 6 chairs, THREE wall panels (sectors+trading,
 * brain/GPU vitals, and the smart board mounted separately via IdeasWall.tsx
 * -- see each panel's own comment), wall-base cable greeble, and a lit floor
 * ring at the all-hands gathering radius. Mounted as a sibling inside
 * BrainCore's own <group scale={1.15}> -- see this component's own outer
 * <group scale={1/1.15}>, which cancels that parent scale so every position
 * constant above is genuine WORLD-space units, matching Scene.tsx's own
 * convention (and IdeasWall.tsx's sibling SmartBoard, which sits OUTSIDE
 * BrainCore's scaled group and needs no such correction).
 *
 * Panel angles, RE-DERIVED TWICE (2026-09-14): first onto the brain-wall
 * segment (center 45deg, spans 0deg..90deg -- see BRAIN_SEGMENT_CENTER_DEG's
 * own comment above) at radius 6.8, matching the board's own first-pass
 * radius; a real capture (models-final-preset0-2148.png) showed NOTHING at
 * that radius (same near-wall occlusion layout.ts#computeBrainWallMount's
 * own header now explains in full) -- radius dropped to 4.3 (angles
 * 15deg/75deg, still symmetric-ish around the board's own 45deg, still
 * clear of the doorways at 0deg/90deg) for the SAME line-of-sight-clearance
 * reason the board itself moved to radius 4.9. Both panel groups apply
 * `facingHubRotationY` -- WITHOUT it, a panel's own content plane (built
 * facing local +Z with zero rotation, see VitalsPanel/SectorsTradingPanel)
 * would face world +Z regardless of where around the hub it sits, a real
 * bug caught while re-deriving this section, not by a capture.
 */
/** One potted plant flanking the round table, on the hub-center side (radius
 * ~1.75 from hub center, well inside the table's own radius 2.5) -- clear of
 * Gamma's own desk (radius 3.4, angle ~61.34deg, computed in Scene.tsx, not
 * this file) and clear of the smart board/wall panels (radius 4.3-4.9), the
 * two other "don't collide with" zones in this segment. rawBounds (glb_
 * extents.mjs, this session) 0.212w x 0.654h x 0.241d, floor Y=0 (flush) --
 * PLANT_SCALE picked to read as a real floor plant (~0.85 world units tall)
 * next to the table's own 0.68-tall top surface.
 *
 * ONE instance, not a flanking pair -- coordinator draw-call-budget flag
 * (2026-09-14 ~19:2x ET, real capture hq-20260914-1725.png: 1093/1100
 * calls): potted-plant.glb has 3 primitives (glb_extents.mjs's own
 * JSON-chunk inspection this session), so a 2nd instance costs 3 more draw
 * calls for a duplicate decorative object -- cut to 1 alongside this pass's
 * other budget trims (see BaseProps.tsx/BayInterior.tsx's own notes). */
const PLANT_SCALE = 1.3;
const PLANT_INNER_RADIUS = 1.75;
const PLANT_TANGENT_OFFSET = 0.55;

function HubPlants() {
  const angleRad = deg(BRAIN_SEGMENT_CENTER_DEG);
  const radial: [number, number] = [Math.cos(angleRad), Math.sin(angleRad)];
  const tangent: [number, number] = [-Math.sin(angleRad), Math.cos(angleRad)];
  const pos: [number, number, number] = [
    radial[0] * PLANT_INNER_RADIUS + tangent[0] * PLANT_TANGENT_OFFSET,
    0,
    radial[1] * PLANT_INNER_RADIUS + tangent[1] * PLANT_TANGENT_OFFSET,
  ];
  return <KitProp path={POTTED_PLANT_PATH} scale={PLANT_SCALE} position={pos} rotation={[0, 1.7, 0]} castShadow receiveShadow />;
}

function facingHubRotationY(position: readonly [number, number, number]): number {
  // Mirrors layout.ts#rotationYFacing(position, HUB) + PI (HUB=[0,0,0], so
  // that reduces to this) -- not imported, since layout.ts is pure
  // geometry/math with no dependency on this file, and this is a 1-line
  // formula, not worth a cross-file coupling for.
  return Math.atan2(position[0], position[2]) + Math.PI;
}

export default function HubInterior({ utilPct, memUsedMib, memTotalMib, modelName, sectorsSnapshot, trading, dimFactor }: HubInteriorProps) {
  return (
    <group scale={1 / 1.15}>
      {/* Round table + chairs */}
      <group position={TABLE_CENTER}>
        <KitProp path={TABLE_LARGE_PATH} scale={TABLE_SCALE} receiveShadow />
        {Array.from({ length: CHAIR_COUNT }, (_, i) => {
          const theta = (i * (2 * Math.PI)) / CHAIR_COUNT;
          const pos: [number, number, number] = [Math.sin(theta) * CHAIR_RADIUS, 0, Math.cos(theta) * CHAIR_RADIUS];
          return <KitProp key={i} path={KIT_PATHS.furniture.chair} scale={FURNITURE_SCALE} position={pos} rotation={[0, theta, 0]} castShadow />;
        })}
      </group>

      {/* W1 -- the holographic SPY chart, floating above the round table's
          own top surface (TABLE_TOP_Y). facingYaw mirrors the same
          facingHubRotationY() the two wall panels below already use, so the
          ribbon's local +X (time axis) reads left-right from the default/
          preset-1 camera the same way -- see HoloChart.tsx's own header. */}
      <HoloChart
        origin={[TABLE_CENTER[0], TABLE_TOP_Y + 0.03, TABLE_CENTER[2]]}
        facingYaw={facingHubRotationY(TABLE_CENTER)}
        dimFactor={dimFactor}
      />

      {/* Sectors + trading -- the brief's ORIGINALLY-specced second board,
          angle 15deg. */}
      {(() => {
        const pos: [number, number, number] = [Math.cos(deg(15)) * 4.3, 1.0, Math.sin(deg(15)) * 4.3];
        return (
          <group position={pos} rotation={[0, facingHubRotationY(pos), 0]}>
            <SectorsTradingPanel sectorsSnapshot={sectorsSnapshot} trading={trading} />
          </group>
        );
      })()}

      {/* Brain/GPU vitals -- the third panel, angle 75deg. */}
      {(() => {
        const pos: [number, number, number] = [Math.cos(deg(75)) * 4.3, 1.0, Math.sin(deg(75)) * 4.3];
        return (
          <group position={pos} rotation={[0, facingHubRotationY(pos), 0]}>
            <VitalsPanel utilPct={utilPct} memUsedMib={memUsedMib} memTotalMib={memTotalMib} modelName={modelName} />
          </group>
        );
      })()}

      {/* Wall-base cable greeble */}
      {CABLE_ANGLES_DEG.map((d) => (
        <KitProp
          key={d}
          path={CABLES_PATH}
          scale={CABLE_SCALE}
          position={[Math.cos(deg(d)) * CABLE_RADIUS, 0, Math.sin(deg(d)) * CABLE_RADIUS]}
          rotation={[0, deg(d), 0]}
          receiveShadow
        />
      ))}

      {/* W2 (2026-09-14): interior plants flanking the table. */}
      <HubPlants />

      {/* All-hands gathering ring -- floor marking, dim emissive, no light. */}
      <mesh position={[0, 0.006, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <ringGeometry args={[GATHER_RING_RADIUS - 0.04, GATHER_RING_RADIUS + 0.04, 64]} />
        <meshBasicMaterial color={PALETTE.hubRing} toneMapped={false} transparent opacity={0.3} />
      </mesh>
    </group>
  );
}

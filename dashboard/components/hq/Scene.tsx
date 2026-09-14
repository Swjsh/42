"use client";

import { useMemo } from "react";
import { useThree, useFrame } from "@react-three/fiber";
import type { HqApiResponse, SectorRow } from "./types";
import type { AgentBehavior } from "./Agent";
import BrainCore from "./BrainCore";
import StationModule from "./StationModule";
import Corridor from "./Corridor";
import IdeasWall from "./IdeasWall";
import Courier from "./Courier";
import Starfield from "./Starfield";
import { freshness01, isParkedState, minutesSinceEvidence, PALETTE } from "./palette";

interface SceneProps {
  data: HqApiResponse | undefined;
  reducedMotion: boolean;
}

const HUB: [number, number, number] = [0, 0, 0];
const RING_RADIUS = 9.8;
const WALL_POS: [number, number, number] = [0, 3.4, 0];
const BASE_AZIMUTH = Math.atan2(16, 20);
const CAMERA_DIST = 26.5;
const CAMERA_HEIGHT = 13;
// Composition pass (2026-09-13): modules on a wide ARC facing the camera --
// not a full 360deg ring, where half of them would sit hidden behind the
// hub from this fixed 3/4 view. Module position uses cos->x/sin->z while
// the camera's own azimuth uses sin->x/cos->z (see CameraRig below), so the
// module-space angle that faces the camera most directly is (90deg -
// BASE_AZIMUTH) -- the arc is centered there, spanning ~230deg so all 8
// modules stay generally camera-facing and spread across the 16:9 frame.
const ARC_CENTER = Math.PI / 2 - BASE_AZIMUTH;
const ARC_SPAN = (230 * Math.PI) / 180;

/** health=red -> alert (overrides evidence recency); a parked lane (killed/
 * dormant/dead state or frozen/zombie health) -> idle, never "working" even
 * if its last_evidence_et happens to look recent; otherwise working when
 * evidence is recent, idle when stale. gaming mode overrides everything. */
function deriveBehavior(row: SectorRow, gaming: boolean): AgentBehavior {
  if (gaming) return "frozen";
  if (row.health === "red") return "alert";
  if (isParkedState(row.state, row.health)) return "idle";
  const minutesAgo = minutesSinceEvidence(row.last_evidence_et);
  return minutesAgo !== null && minutesAgo <= 120 ? "working" : "idle";
}

/** Fixed 3/4 elevated view sized to fit the whole ring, with a slow +-8deg
 * azimuth drift so the station feels alive. reducedMotion holds the drift at
 * zero (camera stays put) without skipping the positioning itself. */
function CameraRig({ reducedMotion }: { reducedMotion: boolean }) {
  const { camera } = useThree();
  useFrame((state) => {
    const drift = reducedMotion ? 0 : (Math.PI / 22.5) * Math.sin(state.clock.elapsedTime * 0.05);
    const azimuth = BASE_AZIMUTH + drift;
    camera.position.set(Math.sin(azimuth) * CAMERA_DIST, CAMERA_HEIGHT, Math.cos(azimuth) * CAMERA_DIST);
    // Look ABOVE the hub's own center (y=0) so the whole station -- hub,
    // modules, and the elevated ideas wall at y=3.4 -- settles into the
    // lower ~80% of frame, leaving the top clear for the HUD (title/mode
    // badge) instead of the two overlapping.
    camera.lookAt(0, 1.9, 0);
  });
  return null;
}

/**
 * Scene composition: hub + one module per sector row arranged on a ring,
 * each connected to the hub by a corridor, plus the ideas wall, the courier,
 * and background dressing. All per-poll derived state (behavior, freshness,
 * angle) is computed here via useMemo/plain calls -- never inside a
 * useFrame -- so a new /api/hq payload only re-renders this tree, it never
 * changes what each child's OWN useFrame throttle is doing mid-animation.
 */
export default function Scene({ data, reducedMotion }: SceneProps) {
  const rows = data?.sectors.rows ?? [];
  const gaming = (data?.mode ?? "work") === "gaming";
  const dimFactor = gaming ? 0.35 : 1;

  // Geometry (angle/position per ring slot) is memoized on COUNT alone, not
  // on the `rows` array reference -- `rows` is a fresh array every SWR poll
  // even when its content is identical, and `sectors.py`'s row order is
  // fixed (one row per lane, same order every call). Keeping position/hub
  // referentially stable across polls matters: Agent/StationModule feed
  // them into useMemo/useEffect dependency arrays, and an unstable
  // reference there would reset a mid-walk agent back to its desk on every
  // single poll instead of only reacting to real data changes.
  const slotCount = Math.max(rows.length, 1);
  const geometry = useMemo(
    () =>
      Array.from({ length: slotCount }, (_, i) => {
        const t = slotCount > 1 ? i / (slotCount - 1) : 0.5;
        const angle = ARC_CENTER - ARC_SPAN / 2 + t * ARC_SPAN;
        const position: [number, number, number] = [Math.cos(angle) * RING_RADIUS, 0, Math.sin(angle) * RING_RADIUS];
        return { angle, position };
      }),
    [slotCount],
  );

  // One accent moment (2026-09-13): when the brain is genuinely busy
  // (GPU util > 30%), corridor pulses run faster -- BrainCore does the
  // matching "brighter rings" half of this internally from the same
  // utilPct prop it already receives.
  const utilPct = data?.brainVitals.gpu.util_pct ?? null;
  const corridorSpeedBoost = utilPct !== null && utilPct > 30 ? 1 + Math.min(1, (utilPct - 30) / 70) * 0.9 : 1;

  return (
    <>
      {/* HQ v2 perf pass: Mali-G31 (the real TV's GPU) is fragment-bound and
          hates per-pixel lights -- ONE hemisphereLight + ONE directionalLight
          for the entire scene, zero pointLights anywhere (module health tint
          now comes from emissive floor-edge strips, not a per-module light;
          see StationModule.tsx). */}
      <color attach="background" args={[PALETTE.space]} />
      <fog attach="fog" args={[PALETTE.fogColor, 20, 62]} />
      <hemisphereLight args={["#3a4a7a", "#04040a", 0.55 * dimFactor]} />
      <directionalLight position={[6, 10, 4]} intensity={0.55 * dimFactor} />

      <CameraRig reducedMotion={reducedMotion} />
      <Starfield reducedMotion={reducedMotion} />

      <BrainCore
        utilPct={data?.brainVitals.gpu.util_pct ?? null}
        memUsedMib={data?.brainVitals.gpu.mem_used_mib ?? null}
        memTotalMib={data?.brainVitals.gpu.mem_total_mib ?? null}
        modelName={data?.brainVitals.models[0]?.name ?? null}
        gaming={gaming}
        dimFactor={dimFactor}
        reducedMotion={reducedMotion}
      />

      {rows.map((row, i) => {
        const slot = geometry[i] ?? geometry[0];
        return (
          <group key={row.lane}>
            <Corridor
              from={slot.position}
              to={HUB}
              freshness={freshness01(minutesSinceEvidence(row.last_evidence_et))}
              speedBoost={corridorSpeedBoost}
              reducedMotion={reducedMotion}
            />
            <StationModule
              position={slot.position}
              angle={slot.angle}
              row={row}
              behavior={deriveBehavior(row, gaming)}
              reducedMotion={reducedMotion}
              dimFactor={dimFactor}
              hubPosition={HUB}
            />
          </group>
        );
      })}

      <IdeasWall cards={data?.ideas.cards ?? []} position={WALL_POS} dimFactor={dimFactor} />
      <Courier cards={data?.ideas.cards ?? []} hub={HUB} wall={WALL_POS} reducedMotion={reducedMotion || gaming} />
    </>
  );
}

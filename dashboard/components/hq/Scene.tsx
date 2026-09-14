"use client";

import { useMemo, useRef } from "react";
import { useThree, useFrame } from "@react-three/fiber";
import type * as THREE from "three";
import type { HqApiResponse, SectorRow } from "./types";
import type { PersonaState } from "@/lib/personas";
import type { AgentBehavior } from "./Agent";
import Agent from "./Agent";
import BrainCore from "./BrainCore";
import StationModule from "./StationModule";
import PersonaModule from "./PersonaModule";
import HandoffCourier from "./HandoffCourier";
import Corridor from "./Corridor";
import IdeasWall from "./IdeasWall";
import Courier from "./Courier";
import Starfield from "./Starfield";
import SkyDome from "./SkyDome";
import PmremEnvironment from "./PmremEnvironment";
import EffectsStack from "./EffectsStack";
import { freshness01, healthColor, isParkedState, localToWorld, minutesSinceEvidence, PALETTE, personaStatusColor } from "./palette";

export type HqTier = "ultra" | "tv";

interface SceneProps {
  data: HqApiResponse | undefined;
  reducedMotion: boolean;
  /** Default "tv" (not "ultra"): CanvasRoot.tsx (the existing TV-tier
   * wrapper) never passes this prop -- only the new UltraCanvasRoot.tsx
   * does. Defaulting to the cheap tier is the safe failure direction if
   * this prop is ever omitted. */
  tier?: HqTier;
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
// Company Mode (2026-09-13): a second, smaller, FIXED ring for the 6
// non-manager personas (item 10 of the spec -- "keep the two rings visually
// distinct"), inside the lane ring's radius 9.8 so it reads as "the org
// chart nested inside the departments it runs." Gamma (Manager), persona[0]
// in collectCompany()'s fixed order, is NOT drawn here -- it becomes
// BrainCore's own manager nameplate/status instead (no 7th desk).
// Layout hygiene fix (2026-09-13, J: "persona nameplates must not sit
// inside the hub plaque area") -- 4.5 put persona Html labels too close to
// BrainCore's own plaques (model plaque at y=1.75, all-hands pulse at
// y=2.4) in screen-space from the fixed 3/4 view. 6.5 is still safely
// inside the lane ring's own radius (9.8, "nested inside the departments
// it runs" per the original design intent) with real clearance from center.
const PERSONA_RING_RADIUS = 6.5;
const COURIER_REST: [number, number, number] = [-1.3, 0, 1.1];

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

/** Grok-Bot-style "status as motion, not a badge" -- maps PersonaState.status
 * onto Agent.tsx's EXISTING working/idle/alert/frozen states verbatim, no
 * new animation code: GREEN=working (at the desk), YELLOW="acknowledging"
 * (idle's own slow look-around IS a toward-the-hub turn + bob), RED=alert
 * (pacing + the nameplate's own "!" ), IDLE=idle (resting). gaming mode
 * freezes personas exactly like lane agents. */
function derivePersonaBehavior(persona: PersonaState, gaming: boolean): AgentBehavior {
  if (gaming) return "frozen";
  if (persona.status === "RED") return "alert";
  if (persona.status === "GREEN") return "working";
  return "idle";
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
export default function Scene({ data, reducedMotion, tier = "tv" }: SceneProps) {
  const ultra = tier === "ultra";
  const coreMeshRef = useRef<THREE.Mesh>(null);
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
        const rotationY = Math.PI / 2 - angle;
        // Bug fix (2026-09-13): computed here and passed to <Agent> as a
        // TRUE scene-root sibling of <StationModule> (never nested inside
        // StationModule's own positioned+rotated <group>) -- see
        // palette.ts#localToWorld's own comment for why nesting it there
        // silently placed every agent ~one ring-radius from its desk.
        const agentHome = localToWorld(position, rotationY, [0, 0, -0.15]);
        return { angle, position, agentHome };
      }),
    [slotCount],
  );

  // One accent moment (2026-09-13): when the brain is genuinely busy
  // (GPU util > 30%), corridor pulses run faster -- BrainCore does the
  // matching "brighter rings" half of this internally from the same
  // utilPct prop it already receives.
  const utilPct = data?.brainVitals.gpu.util_pct ?? null;
  const corridorSpeedBoost = utilPct !== null && utilPct > 30 ? 1 + Math.min(1, (utilPct - 30) / 70) * 0.9 : 1;

  // Presence greeter (J 2026-09-13: "nearest agent turns to the viewer /
  // night-patrol dim"): a STATIC pick (camera never orbits, only drifts
  // +-8deg, negligible for "which slot is nearest") of the lane slot
  // closest to the camera's rest position -- lanes, not personas, because a
  // persona's own <Agent> can be hidden entirely while IDLE (see the
  // draw-call budget guard below) and would make an unreliable greeter.
  const nearestLaneIndex = useMemo(() => {
    if (geometry.length === 0) return -1;
    const camX = Math.sin(BASE_AZIMUTH) * CAMERA_DIST;
    const camZ = Math.cos(BASE_AZIMUTH) * CAMERA_DIST;
    let bestI = 0;
    let bestD = Infinity;
    geometry.forEach((slot, i) => {
      const dx = slot.position[0] - camX;
      const dz = slot.position[2] - camZ;
      const d = dx * dx + dz * dz;
      if (d < bestD) { bestD = d; bestI = i; }
    });
    return bestI;
  }, [geometry]);
  // Yaw so the agent's own +Z front (see Agent.tsx's visor mesh) points at
  // the camera's rest position -- a one-time geometric calculation (never
  // per-frame), visually UNVERIFIED without eyes on the real scene (Browser
  // pane is off-limits while J is gaming on the PC's own GPU per the
  // 2026-09-13 gaming-mode note) -- a wrong sign here is a purely cosmetic,
  // easily eyeballed-and-flipped fix, never a functional one.
  const nearestLaneSlot = nearestLaneIndex >= 0 ? geometry[nearestLaneIndex] : null;
  const greeterFacingYaw = nearestLaneSlot
    ? Math.atan2(
        Math.sin(BASE_AZIMUTH) * CAMERA_DIST - nearestLaneSlot.position[0],
        Math.cos(BASE_AZIMUTH) * CAMERA_DIST - nearestLaneSlot.position[2],
      )
    : 0;
  const present = data?.presence?.present ?? null;
  const greeterPresenceMode = present === null ? undefined : present ? "greet" : "patrol";

  // Company Mode: personas[0] is always Gamma (Manager) per collectCompany()'s
  // fixed order -- everyone else gets an inner-ring desk. Geometry memoized
  // on COUNT alone (always 6 in practice), same referential-stability reason
  // as the lane ring above.
  const allPersonas = data?.company?.personas ?? [];
  const innerPersonas = allPersonas.slice(1);
  const personaSlotCount = Math.max(innerPersonas.length, 1);
  const personaGeometry = useMemo(
    () =>
      Array.from({ length: personaSlotCount }, (_, i) => {
        const t = personaSlotCount > 1 ? i / (personaSlotCount - 1) : 0.5;
        const angle = ARC_CENTER - ARC_SPAN / 2 + t * ARC_SPAN;
        const position: [number, number, number] = [Math.cos(angle) * PERSONA_RING_RADIUS, 0, Math.sin(angle) * PERSONA_RING_RADIUS];
        const rotationY = Math.PI / 2 - angle;
        const agentHome = localToWorld(position, rotationY, [0, 0, -0.1]);
        return { position, agentHome };
      }),
    [personaSlotCount],
  );

  // Handoff endpoint labels ("🌍 Scout", "Premarket", "_LEADERBOARD", "J
  // ratification"...) don't all name an actual desk -- only some match a
  // persona. Resolve by stripping a leading emoji and matching the START of
  // the label against a persona name (so "Chef inbox" matches "Chef"); any
  // unmatched label (a process stage like "Premarket", or "J ratification"
  // naming J himself, who has no desk) falls back to the hub, since those
  // conceptually route through the manager.
  const personaPositions = useMemo(() => {
    const map: Record<string, [number, number, number]> = {};
    innerPersonas.forEach((p, i) => {
      map[p.name] = (personaGeometry[i] ?? personaGeometry[0]).position;
    });
    return map;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [innerPersonas.map((p) => p.name).join("|"), personaGeometry]);

  const resolveHandoffPosition = (label: string): [number, number, number] => {
    const stripped = label.replace(/^[^\w]+/u, "").trim();
    const match = Object.keys(personaPositions).find((name) => stripped.startsWith(name));
    if (match) return personaPositions[match];
    return HUB;
  };

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
      {/* Ultra tier: this directional light also casts real shadows
          (module/agent meshes opt in via castShadow/receiveShadow below) --
          the TV tier's identical light stays shadow-free (shadows={false}
          on CanvasRoot's <Canvas> makes castShadow a no-op there anyway,
          so this prop is harmless to set unconditionally). */}
      <directionalLight
        position={[6, 10, 4]}
        intensity={0.55 * dimFactor}
        castShadow={ultra}
        shadow-mapSize={[2048, 2048]}
        shadow-camera-near={1}
        shadow-camera-far={40}
        shadow-camera-left={-14}
        shadow-camera-right={14}
        shadow-camera-top={14}
        shadow-camera-bottom={-14}
      />

      <CameraRig reducedMotion={reducedMotion} />
      {ultra && <PmremEnvironment />}
      {ultra && <EffectsStack coreMeshRef={coreMeshRef} />}
      <SkyDome />
      <Starfield reducedMotion={reducedMotion} />

      <BrainCore
        utilPct={data?.brainVitals.gpu.util_pct ?? null}
        memUsedMib={data?.brainVitals.gpu.mem_used_mib ?? null}
        memTotalMib={data?.brainVitals.gpu.mem_total_mib ?? null}
        modelName={data?.brainVitals.models[0]?.name ?? null}
        manager={allPersonas[0] ?? null}
        briefMtimeMs={data?.brief.mtime_ms ?? null}
        gaming={gaming}
        dimFactor={dimFactor}
        reducedMotion={reducedMotion}
        ultra={ultra}
        coreMeshRef={coreMeshRef}
      />

      {rows.map((row, i) => {
        const slot = geometry[i] ?? geometry[0];
        const behavior = deriveBehavior(row, gaming);
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
              behavior={behavior}
              reducedMotion={reducedMotion}
              dimFactor={dimFactor}
              ultra={ultra}
            />
            {/* Scene-root sibling, NOT nested inside StationModule -- see the
                agentHome comment above. Lane agents never walk anymore (no
                event cleanly attributes a card to one lane -- see
                Courier.tsx's own comment on why card-status events route
                there instead); `presenceMode`/`facingYaw` are set on
                exactly one statically-chosen lane (nearestLaneIndex). */}
            <Agent
              laneSeed={row.lane}
              home={slot.agentHome}
              hub={HUB}
              behavior={behavior}
              accentColor={healthColor(row.health)}
              reducedMotion={reducedMotion}
              presenceMode={i === nearestLaneIndex ? greeterPresenceMode : undefined}
              facingYaw={i === nearestLaneIndex ? greeterFacingYaw : undefined}
            />
          </group>
        );
      })}

      {/* Company Mode: inner persona ring -- Gamma (Manager) excluded (it's
          BrainCore itself); each persona gets a slim nameplate + its own
          Agent as a scene-root sibling (same positioning fix as the lane
          ring -- Agent must never be nested inside a positioned parent). */}
      {innerPersonas.map((persona, i) => {
        const slot = personaGeometry[i] ?? personaGeometry[0];
        const behavior = derivePersonaBehavior(persona, gaming);
        // Draw-call budget guard (2026-09-13): each <Agent> is 7 meshes (see
        // Agent.tsx), so 6 inner personas can add up to 42 draw calls on top
        // of the 8 lane modules' own agents -- the last confirmed real TV
        // report (fps=29, 116 calls, pre-Company-Mode) leaves little
        // headroom against the ~130-call soft ceiling. A persona with raw
        // status IDLE (never fired, or nothing recent) draws its nameplate
        // only -- an empty desk is an honest depiction of "idle", not a
        // missing feature -- while GREEN/YELLOW/RED keep their agent body.
        // Gate on the raw status, not `behavior`: derivePersonaBehavior()
        // maps BOTH YELLOW and IDLE to the same "idle" Agent animation, and
        // YELLOW ("acknowledging") must keep its body.
        const showAgent = persona.status !== "IDLE";
        return (
          <group key={persona.name}>
            <PersonaModule position={slot.position} persona={persona} behavior={behavior} />
            {showAgent && (
              <Agent
                laneSeed={persona.name}
                home={slot.agentHome}
                hub={HUB}
                behavior={behavior}
                accentColor={personaStatusColor(persona.status)}
                reducedMotion={reducedMotion}
                // J 2026-09-13 (d): "a persona lastFireISO advancing -> that
                // persona walks from the hub to its desk and sits down
                // working". Agent's own seen-value-diff seeds silently on
                // first mount, so this never fires a walk for a persona
                // that was already showing a lastFireISO on page load.
                walkEventKey={persona.lastFireISO}
                walkKind="arrival"
              />
            )}
          </group>
        );
      })}
      <HandoffCourier
        handoffs={data?.company?.handoffs ?? []}
        resolvePosition={resolveHandoffPosition}
        restPosition={COURIER_REST}
        reducedMotion={reducedMotion || gaming}
      />

      <IdeasWall cards={data?.ideas.cards ?? []} position={WALL_POS} dimFactor={dimFactor} />
      <Courier cards={data?.ideas.cards ?? []} hub={HUB} wall={WALL_POS} reducedMotion={reducedMotion || gaming} />
    </>
  );
}

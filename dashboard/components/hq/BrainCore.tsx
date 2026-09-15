"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, RefObject } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import type { PersonaState } from "@/lib/personas";
import type { SectorsSnapshot, TradingStatus } from "@/lib/hq";
import { clamp01, lerp, makeMatcapTexture, PALETTE, personaStatusColor } from "./palette";
import { ReactorGreeble } from "./SetKit";
import HubInterior from "./HubInterior";
import { PRIORITY } from "./labelDeclutter";
import { mergeRefs, useLabelDeclutter } from "./useLabelDeclutter";
import { bubbleCounterScale } from "./bubbleText";

/** Mirrors GammaCharacter.tsx's own local `GammaLoopRow` shape (that file's
 * own comment: "the SAME loop-ledger row the crew panel's own pill
 * ultimately traces back to"). Duplicated here rather than imported --
 * both are small "use client" leaf components and this codebase's own
 * convention (see lib/crew.ts's etHHMM vs GammaCharacter.tsx's hhmmEt) is a
 * tiny local type/helper over a new cross-file dependency for a 3-field
 * shape. */
interface GammaLoopRow {
  ts_et: string;
  status: string;
  reason: string;
}

interface BrainCoreProps {
  utilPct: number | null;
  memUsedMib: number | null;
  memTotalMib: number | null;
  modelName: string | null;
  manager: PersonaState | null;
  briefMtimeMs: number | null;
  /** World-4 fix (2026-09-14, P3: "the wall's status line derive from the
   * same source" as the crew panel's pill and Gamma's own speech bubble).
   * The SAME `data.brainVitals.lastRow` / `crewNextLine(...)` values
   * Scene.tsx already threads into GammaCharacter -- passed in from the
   * SAME call site (never re-derived) so the wall can never read a
   * different truth than the bubble two meters away from it. */
  lastRow: GammaLoopRow | null;
  nextLine: string | null;
  gaming: boolean;
  dimFactor: number;
  reducedMotion: boolean;
  /** Ultra tier (2026-09-13, HQ-ULTRA-TIER-BRIEF.md): swaps the core
   * sphere to meshPhysicalMaterial (clearcoat, PMREM reflections) instead
   * of the TV tier's matcap. `coreMeshRef` is attached to that sphere's
   * own <mesh> regardless of tier -- EffectsStack's GodRays reads it as
   * the scene's one "sun" object, and it's harmless/unused when GodRays
   * isn't mounted (tv tier). */
  ultra?: boolean;
  coreMeshRef?: RefObject<THREE.Mesh | null>;
  /** S2 hub-interior pass (2026-09-14, MODELS builder): the originally-
   * specced "sectors summary + trading strip" second wall panel needs this
   * real data -- neither was threaded here before today (coordinator,
   * 2026-09-14 ~17:22 ET: "sectorsSnapshot" lands on /api/hq via commit
   * b149fd00; "trading" is the existing strip payload; LAYOUT threads both
   * from Scene.tsx in its next slice"). Optional + nullable so THIS
   * component and HubInterior.tsx keep compiling/rendering (with an honest
   * "waiting for first fire" placeholder, never fabricated numbers) against
   * Scene.tsx's CURRENT call site, which doesn't pass these yet. */
  sectorsSnapshot?: SectorsSnapshot | null;
  trading?: TradingStatus | null;
}

const GAUGE_WIDTH = 1.8;
const PULSE_DURATION_MS = 10_000;
// Same threshold + gate GammaCharacter.tsx uses for its own "thinking"
// bubble -- see that file's own comment on why BOTH a busy GPU and the
// ledger's `status==="ok"` are required (a util spike alone, during a
// yielded/RTH window, must never read as "thinking").
const THINKING_UTIL_THRESHOLD = 30;

// ─── Plaque on-screen size (2026-09-15, worker fix -- overview-read.png
// capture: the "BRAIN · wrote brief" plaque measured ~5px tall at the
// default overview camera while every other hub label sits ~12px, commit
// 23f4c6a4). Root cause: the P1 fix below (POLISH-1, 2026-09-14) only ever
// clamped these Html's counter-scale to `min(1, camDist/preset0Dist)` --
// i.e. AT the overview camera (camDist == preset0Dist, BrainCore mounts at
// Scene.tsx's own overview default) the factor is exactly 1, so the plaque
// got NO extra scaling and fell back to drei's raw
// `distanceFactor/(2*tan(fov/2)*dist)` term, which this codebase's own
// bubbleScale.ts header derives as ~0.177 at that camera for
// distanceFactor=9 -- a 34px plaque font landing at ~6px, matching the
// ~5px capture. It never adopted bubbleScale.ts's `bubbleCounterScale`
// (BUBBLE_FAR_REF_DISTANCE 20 / NEAR_HOLD 10 / MAX_COUNTER_SCALE 5), which
// every OTHER hub label (Agent.tsx, GammaCharacter.tsx) already uses and
// which pins a real floor (~0.482 at dist>=20u, giving the same 34px font
// ~16.4px at the overview's ~54.6u).
//
// Fix: swap the clamp for `bubbleCounterScale(dist)` -- the same shared
// policy, same DOM-nesting composition with drei's own scale (Html.js:
// `el` (drei's scale) > styles-div (`center` transform) > this component's
// own ref child) POLISH-1 already relied on. It keeps POLISH-1's close-range
// intent too: bubbleCounterScale's near branch holds a bounded plateau
// (dist/NEAR_HOLD_DISTANCE, capped, never unbounded) rather than growing
// into a banner as the camera approaches, same "never blow up close" goal.


// Outer core-group scale (the `<group scale={...}>` wrapping the sphere/
// rings/plaques below) -- named so the useFrame math above can convert each
// Html's own LOCAL y into the real world-Y `bubbleCounterScale` needs,
// without a second hardcoded "1.15" ever drifting from the JSX below.
const CORE_GROUP_SCALE = 1.15;
// Each plaque/label's own local Y (pre-CORE_GROUP_SCALE) -- shared between
// its <Html position=...> and the clamp-factor call for it below, so the two
// can never disagree.
const GAUGE_GROUP_Y = -1.6;
// POLISH-3 (2026-09-15, real-capture, camdist=36 07:46:56 ET): was -0.22 --
// real evidence showed the MEM text partly clipped by the BRAIN plaque's own
// lower edge at that overview framing (bubbleCounterScale grows a label's
// on-screen footprint substantially at long camera distance -- see
// LabelDeclutterManager.tsx's own "OVERVIEW-FLOOR fix" note -- so a world-
// space gap that reads as generous up close can still read as touching once
// both labels are counter-scaled up at overview zoom). -0.34 adds further
// real clearance below the gauge bar (away from PLAQUE_Y, which sits above
// the core); paired with the label's own small transparent padding below
// (belt-and-suspenders "min gap" for the declutter resolver's own rect
// overlap check, per the coordinator's own suggested fix shape).
const GAUGE_LABEL_Y = -0.34; // relative to GAUGE_GROUP_Y
// PLAQUE_Y/PULSE_PLAQUE_Y/GAMING_PLAQUE_Y raised (2026-09-14, coordinator
// regression capture scale-verify-0106.png): old PLAQUE_Y=1.75 -> world
// 1.75*CORE_GROUP_SCALE(1.15)=2.0125, landing squarely in the live-agent
// bubble band (GammaCharacter.tsx's own bubbleWorld = seatWorld +
// CHARACTER_TARGET_HEIGHT(1.8) + 0.4 = ~2.2; LiveAgents.tsx's
// ULTRA_HEAD_Y=1.71 + its own bubble offset lands in the same ~2.0-2.3
// range) -- the real capture showed the "BRAIN * wrote brief" plaque
// literally painted mid-word over the "session" agent's own bubble at the
// hub center. +0.65 to each keeps the same relative stack (plaque < pulse <
// gaming) while clearing that band with margin (new PLAQUE_Y world =
// 2.4*1.15=2.76, > 2.3 by 0.46).
const PLAQUE_Y = 2.4;
const PULSE_PLAQUE_Y = 3.4;
const GAMING_PLAQUE_Y = 4.1;

/** First token of a loop-ledger `reason`, e.g. "rth_window" from
 * "rth_window (weekday 09:30-15:55 ET)" -- byte-identical helper to
 * GammaCharacter.tsx's own `shortReason` (duplicated, not imported, same
 * "tiny local helper over a cross-file dependency" convention noted on
 * `GammaLoopRow` above). */
function shortReason(reason: string): string {
  const m = /^[^\s(]+/.exec(reason.trim());
  return m ? m[0] : reason;
}

/** "rth_window" -> "RTH" for the wall's own compact style; any OTHER real
 * yield reason this ledger might ever carry is shown verbatim (uppercased)
 * rather than guessing a second abbreviation -- never invent a label for a
 * reason this file hasn't actually seen. */
function reasonAbbrev(reason: string): string {
  const short = shortReason(reason);
  return short === "rth_window" ? "RTH" : short.toUpperCase();
}

function hhmmEt(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "America/New_York" });
}

/** P3 fix (2026-09-14, "BRAIN IDLE" contradicting the crew panel's YIELDING
 * and Gamma's own bubble -- three surfaces disagreeing, one of them false):
 * the wall's own status line, gated in the SAME order as GammaCharacter.tsx's
 * bubbleText (yielded -> error -> thinking -> wrote-brief -> quiet), off the
 * SAME `lastRow`/`nextLine`/`utilPct`/`briefMtimeMs` fields -- never the
 * `modelName`-presence heuristic the old "BRAIN IDLE" fallback used, which
 * conflated "no model currently loaded" with "the manager is doing nothing"
 * (false during a deliberately-scheduled RTH yield). Bubble-cycling "read a
 * brief sentence" text is deliberately dropped here -- that's chat filler
 * appropriate to a speech bubble, not a status wall. */
function brainWallStatusLine(lastRow: GammaLoopRow | null, nextLine: string | null, thinking: boolean, briefMtimeMs: number | null): string {
  if (lastRow?.status === "yielded") {
    const next = nextLine ? (nextLine.endsWith(" ET") ? nextLine.slice(0, -3) : nextLine) : null;
    return `BRAIN · yielding (${reasonAbbrev(lastRow.reason)})${next ? ` · next ${next}` : ""}`;
  }
  if (lastRow?.status === "error") return "BRAIN · error";
  if (thinking) return "BRAIN · thinking…";
  if (briefMtimeMs) return `BRAIN · wrote brief ${hhmmEt(briefMtimeMs)}`;
  return "BRAIN · quiet";
}

/**
 * Central hub -- Gamma's "brain core". Sphere + two counter-rotating rings +
 * an additive glow sprite (intensity scales with GPU util) + a memory gauge
 * bar + an <Html> plaque (never drei <Text>, which would fetch a font).
 * Continuous motion (rotation, flicker) is computed directly from
 * state.clock.elapsedTime -- cheap scalar math, no throttling needed.
 */
export default function BrainCore({
  // World-2 item 4 (2026-09-14): `reducedMotion` is now unused -- the only
  // two things it gated (ring-spin speed, the pulse's extra rotation) are
  // both removed below, and everything left in this component (core-color
  // flicker, glow-sprite breathing) was never gated by it to begin with.
  // Renamed with the SAME underscore convention CanvasRoot.tsx already uses
  // for its own unused `lanKiosk` prop, kept in the signature only because
  // Scene.tsx's call site (and BrainCoreProps) still pass it.
  // World-4 fix (P3): the WALL's own status line (`wallStatusLine` below)
  // stopped reading `modelName` -- derived from `lastRow`/`nextLine`/
  // `briefMtimeMs` instead, never a model-loaded check. `modelName` itself
  // is back in use as of the S2 hub-interior pass (2026-09-14, MODELS
  // builder): HubInterior's own second wall panel (VitalsPanel) shows it --
  // real data this component already receives, reused rather than
  // threading a new prop through Scene.tsx for it.
  utilPct, memUsedMib, memTotalMib, modelName, manager, briefMtimeMs, lastRow, nextLine, gaming, dimFactor, reducedMotion: _reducedMotion,
  ultra = false, coreMeshRef, sectorsSnapshot = null, trading = null,
}: BrainCoreProps) {
  const coreMat = useRef<THREE.MeshMatcapMaterial | THREE.MeshPhysicalMaterial>(null);
  const matcap = useMemo(() => makeMatcapTexture(), []);
  const glowMat = useRef<THREE.SpriteMaterial>(null);
  // P1 fix -- plaque-scale-clamp wrapper refs, one per Html this fix covers
  // (see bubbleCounterScale fix's own header above). Each is the actual rendered
  // wrapper div (the ".hq-beam" div for 3 of the 4; the gauge label has no
  // beam wrapper, so its own <div> gets the ref directly) -- null whenever
  // that Html isn't currently mounted (pulse/gaming are conditional),
  // guarded the same way coreMat/glowMat already are below.
  const gaugeLabelRef = useRef<HTMLDivElement>(null);
  const plaqueRef = useRef<HTMLDivElement>(null);
  const pulseRef = useRef<HTMLDivElement>(null);
  const gamingRef = useRef<HTMLDivElement>(null);
  // DECLUTTER pass (2026-09-14): only the main status plaque registers --
  // it's the one the real captures (boardfit-overview/close.png) showed
  // cutting into "Coach"/"general-purpose" bubbles at the hub center; the
  // pulse/gaming plaques are rare/conditional overlays, out of this pass's
  // own scope (smallest-correct-change). World position is static (PLAQUE_Y
  // scaled by this component's own outer CORE_GROUP_SCALE, matching
  // bubbleCounterScale's own worldY convention just above).
  const { wrapperRef: declutterRef, measureRef: declutterMeasureRef } = useLabelDeclutter(
    "brain-plaque",
    PRIORITY.PLAQUE,
    () => [0, PLAQUE_Y * CORE_GROUP_SCALE, 0] as [number, number, number],
  );
  // Queue item h (2026-09-15, real-screen 1920x1080 capture): the MEM gauge
  // readout (below the core, GAUGE_GROUP_Y+GAUGE_LABEL_Y) sat directly under
  // a persona speech bubble ("Scout -- scanning 5 feeds...") near the hub --
  // it never joined the declutter system the plaque above already uses, so
  // the resolver had no idea it existed and never nudged either label clear.
  // PRIORITY.LANE (lowest precedence) -- it is a minor ambient readout, not
  // a plaque or a live conversation bubble, so it should be the one that
  // yields/fades if the hub gets crowded, matching the tier ordering
  // labelDeclutter.ts's own header documents ("live-agent bubbles and Gamma
  // > persona bubbles > plaque > lane labels"). NOT wrapped in .hq-beam --
  // that class is reserved for the Border Beam treatment on real plaques;
  // this stays the plain text node it always was, per the task's own "don't
  // add hq-beam to tiny ticks" guidance.
  const { wrapperRef: gaugeDeclutterRef, measureRef: gaugeDeclutterMeasureRef } = useLabelDeclutter(
    "brain-gauge",
    PRIORITY.LANE,
    () => [0, (GAUGE_GROUP_Y + GAUGE_LABEL_Y) * CORE_GROUP_SCALE, 0] as [number, number, number],
  );
  // POLISH-3 (2026-09-15, real-GPU probe: automation/state/station/hq-probe-
  // runs/20260915T114713Z-n6xD1qb0i4bfCDjMZ9s9l.samples.json.gz) --
  // label_overlap FAILed on "general-purpose"/"Claude (you)" live-agent
  // bubbles vs "STATION BRIEF -- ALL HANDS" (35 ticks/16 segments, up to
  // 2.5s runs). ROOT CAUSE: this pulse plaque was left out of the 2026-09-14
  // DECLUTTER pass entirely (see the comment on `declutterRef` above --
  // "only the main status plaque registers... the pulse/gaming plaques are
  // rare/conditional overlays, out of this pass's own scope") -- it renders
  // a real .hq-beam plaque (same visual weight as the always-on status
  // plaque just above it) but the resolver had no registered rect for it,
  // so it could never be nudged away from a live-agent bubble drifting
  // through the hub, or vice versa. PRIORITY.PLAQUE (same tier the main
  // status plaque already uses, per the coordinator's own "whatever
  // BrainCore's plaque uses" instruction) -- a fixed board announcement
  // should keep its resting position while live bubbles nudge around it,
  // not the other way around. Same wrapperRef/measureRef pattern as every
  // other registrant in this file. Conditional on `pulsing` (this plaque
  // only exists then) -- registering/unregistering on mount/unmount is
  // exactly what useLabelDeclutter.ts's own cleanup already handles (see
  // its header: "a label that unmounts and remounts... starts fresh").
  const { wrapperRef: pulseDeclutterRef, measureRef: pulseDeclutterMeasureRef } = useLabelDeclutter(
    "brain-pulse-plaque",
    PRIORITY.PLAQUE,
    () => [0, PULSE_PLAQUE_Y * CORE_GROUP_SCALE, 0] as [number, number, number],
  );

  const utilFrac = clamp01((utilPct ?? 0) / 100);
  const memFrac = memUsedMib && memTotalMib ? clamp01(memUsedMib / memTotalMib) : 0;
  // Same gate as GammaCharacter.tsx's own `thinking` -- see THINKING_UTIL_THRESHOLD's comment.
  const thinking = lastRow?.status === "ok" && (utilPct ?? 0) > THINKING_UTIL_THRESHOLD;
  const wallStatusLine = brainWallStatusLine(lastRow, nextLine, thinking, briefMtimeMs);

  // All-hands pulse (Company Mode step 6, 2026-09-13): fires ~10s of
  // doubled ring speed + a plaque when station-brief.md's mtime
  // (data.brief.mtime_ms, already exposed on /api/hq) changes to a
  // genuinely NEW value -- chosen over analysis/daily-brief/{today}.md
  // per the coordinator's own instruction to "pick the one the data
  // already exposes; state which." The first value seen on mount is a
  // seed, not a trigger, matching the seen-id-diff rule Courier.tsx and
  // HandoffCourier.tsx already use to avoid animating on initial page load.
  const prevBriefMtime = useRef<number | null | undefined>(undefined);
  const [pulsing, setPulsing] = useState(false);

  useEffect(() => {
    if (briefMtimeMs === null || briefMtimeMs === undefined) return;
    if (prevBriefMtime.current === undefined) {
      prevBriefMtime.current = briefMtimeMs;
      return;
    }
    if (briefMtimeMs === prevBriefMtime.current) return;
    prevBriefMtime.current = briefMtimeMs;
    setPulsing(true);
    const timer = window.setTimeout(() => setPulsing(false), PULSE_DURATION_MS);
    return () => window.clearTimeout(timer);
  }, [briefMtimeMs]);

  useFrame((state) => {
    const t = state.clock.elapsedTime;

    const flicker = Math.sin(t * 2.1) * 0.06;
    // World pass A (2026-09-13): floor raised 0.7->1.15 -- "cyan core glow
    // strong enough to bloom" even at IDLE (util=0), not only when the GPU
    // is genuinely busy. Paired with EffectsStack.tsx's lowered Bloom
    // luminanceThreshold (0.92->0.78): a color channel at ~1.15x a hue like
    // hubCore's blue/cyan (already close to 1.0 in its brightest channel)
    // now crosses that threshold, while normal lit materials (which stay
    // under ~0.9 after tone mapping even with the exposure bump below)
    // still don't -- keeps bloom SELECTIVE, not global.
    const baseGlow = lerp(1.15, 2.6, utilFrac) * dimFactor;
    // meshMatcapMaterial has no emissive/emissiveIntensity (HQ v4 look pass,
    // 2026-09-13) -- the same "brighter = busier" animation scales the
    // material's own `color` instead. World-2 item 4 (2026-09-14, J: "the
    // spinning color radar looking things can go... they don't really make
    // a lot of sense, and they're just noisy"): the two counter-rotating
    // rings this useFrame used to also drive (rotation + a busy-brightening
    // color multiply) are REMOVED outright -- core sphere + vitals text
    // stay, and this component now has zero rotation anywhere, only the
    // brightness flicker/glow-sprite breathing below.
    if (coreMat.current) coreMat.current.color.set(PALETTE.hubCore).multiplyScalar(baseGlow + flicker);
    if (glowMat.current) glowMat.current.opacity = clamp01(0.35 + utilFrac * 0.5) * dimFactor;

    // bubbleCounterScale fix (see header comment above) -- camera position
    // is read once per frame (state.camera has no parent transform in this
    // tree, so .position IS its real world position); worldY per plaque is
    // its own local Y * CORE_GROUP_SCALE (this component's own outer
    // <group> scale), and every plaque's world X/Z stay 0 (BrainCore's own
    // mount in Scene.tsx carries no position offset), so `dist` below is the
    // true camera-to-plaque distance bubbleCounterScale expects.
    const camX = state.camera.position.x;
    const camY = state.camera.position.y;
    const camZ = state.camera.position.z;
    if (gaugeLabelRef.current) {
      const worldY = (GAUGE_GROUP_Y + GAUGE_LABEL_Y) * CORE_GROUP_SCALE;
      const k = bubbleCounterScale(Math.hypot(camX, camY - worldY, camZ));
      gaugeLabelRef.current.style.transform = `scale(${k})`;
    }
    if (plaqueRef.current) {
      const worldY = PLAQUE_Y * CORE_GROUP_SCALE;
      const k = bubbleCounterScale(Math.hypot(camX, camY - worldY, camZ));
      plaqueRef.current.style.transform = `scale(${k})`;
    }
    if (pulseRef.current) {
      const worldY = PULSE_PLAQUE_Y * CORE_GROUP_SCALE;
      const k = bubbleCounterScale(Math.hypot(camX, camY - worldY, camZ));
      pulseRef.current.style.transform = `scale(${k})`;
    }
    if (gamingRef.current) {
      const worldY = GAMING_PLAQUE_Y * CORE_GROUP_SCALE;
      const k = bubbleCounterScale(Math.hypot(camX, camY - worldY, camZ));
      gamingRef.current.style.transform = `scale(${k})`;
    }
  });

  const gaugeColor = memFrac > 0.85 ? "#ff3b3b" : memFrac > 0.6 ? "#ffb020" : "#22ff88";

  return (
    <group scale={CORE_GROUP_SCALE}>
      {/* Kit rebuild (2026-09-13, HQ-SCENE-PLAN.md): "brain core = a glowing
          reactor built from kit pieces + emissive core" -- 4 pipe/pipe-bend
          props radiating from the EXISTING sphere/rings (kept unchanged,
          they ARE the "glowing core"; this is dressing around it, ultra
          tier only -- TV tier's draw-call budget doesn't have room).
          World pass A bug fix (2026-09-13, caught from a real console
          error -- "Cannot read properties of null (reading 'parent')",
          repeating on every Canvas remount): ReactorGreeble's useGLTF calls
          suspend, and WITHOUT a local boundary that bubbles up to <Canvas>'s
          own single built-in Suspense (confirmed by reading r3f's source
          this session), unmounting THIS ENTIRE <group> -- including
          `coreMeshRef`'s mesh -- while it loads. EffectsStack's GodRays
          reads `coreMeshRef.current.parent` every frame; a frame landing
          during that unmount window crashes. `<Suspense fallback={null}>`
          scoped to JUST this piece keeps the core sphere/rings mounted and
          stable regardless of kit-asset load timing. */}
      {ultra && (
        <Suspense fallback={null}>
          <ReactorGreeble />
        </Suspense>
      )}

      {/* S2 hub-interior pass (2026-09-14, MODELS builder): round table +
          chairs, second (vitals) wall panel, cable greeble, gathering-ring
          floor marking -- see HubInterior.tsx's own header comment for why
          this mounts here (not Scene.tsx) and for its outer counter-scale
          (cancels this group's own scale={1.15} above so its position
          constants stay genuine world-space units). Ultra tier only, same
          real-kit-geometry budget reasoning as ReactorGreeble just above. */}
      {ultra && (
        <Suspense fallback={null}>
          <HubInterior
            utilPct={utilPct}
            memUsedMib={memUsedMib}
            memTotalMib={memTotalMib}
            modelName={modelName}
            sectorsSnapshot={sectorsSnapshot}
            trading={trading}
            dimFactor={dimFactor}
          />
        </Suspense>
      )}

      {/* Core sphere -- TV tier: procedural matcap (HQ v4 look pass,
          2026-09-13), one texture lookup replacing Lambert's per-fragment
          N.L at the same cost class. Ultra tier (HQ-ULTRA-TIER-BRIEF.md):
          meshPhysicalMaterial with clearcoat + PMREM env reflections --
          "the single biggest fidelity jump in the whole brief". Both
          branches share the same `color` brightness animation (useFrame
          above) and the same coreMeshRef (GodRays' one "sun" object). */}
      <mesh ref={coreMeshRef} castShadow={ultra} receiveShadow={ultra}>
        <sphereGeometry args={[1.05, ultra ? 48 : 20, ultra ? 36 : 16]} />
        {ultra ? (
          <meshPhysicalMaterial ref={coreMat} color={PALETTE.hubCore} clearcoat={1} clearcoatRoughness={0.15} roughness={0.25} metalness={0.1} envMapIntensity={1.4} toneMapped={false} />
        ) : (
          <meshMatcapMaterial ref={coreMat} matcap={matcap} color={PALETTE.hubCore} toneMapped={false} />
        )}
      </mesh>

      {/* World-2 item 4 (2026-09-14, J: "the spinning color radar looking
          things can go"): the two counter-rotating rings that used to sit
          here are REMOVED -- core sphere + vitals text stay, static. */}

      {/* Additive glow sprite -- camera-facing, cheap */}
      <sprite scale={[3.6, 3.6, 1]}>
        <spriteMaterial ref={glowMat} color={PALETTE.hubCore} transparent opacity={0.5} depthWrite={false} blending={THREE.AdditiveBlending} />
      </sprite>

      {/* Memory gauge: background + fill, anchored left */}
      <group position={[0, GAUGE_GROUP_Y, 0]}>
        <mesh>
          <boxGeometry args={[GAUGE_WIDTH, 0.09, 0.05]} />
          <meshBasicMaterial color="#0e1626" transparent opacity={0.9} />
        </mesh>
        <mesh position={[-GAUGE_WIDTH / 2 + (GAUGE_WIDTH * Math.max(memFrac, 0.02)) / 2, 0, 0.01]}>
          <boxGeometry args={[GAUGE_WIDTH * Math.max(memFrac, 0.02), 0.09, 0.05]} />
          <meshBasicMaterial color={gaugeColor} toneMapped={false} />
        </mesh>
        <Html position={[0, GAUGE_LABEL_Y, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
          <div ref={gaugeDeclutterRef} style={{ transformOrigin: "50% 100%" }}>
            {/* POLISH-3: transparent vertical padding inflates THIS div's own
                measured rect (the resolver reads size from `measureRef`'s
                real getBoundingClientRect -- see useLabelDeclutter.ts's own
                header) without changing anything visible -- a "min gap" the
                declutter resolver's strict rect-overlap check now honors
                even for a near-touch against the plaque above, not only a
                true pixel overlap. */}
            <div ref={mergeRefs(gaugeLabelRef, gaugeDeclutterMeasureRef)} style={{ color: "#7f93b0", fontSize: 26, fontFamily: "system-ui, sans-serif", whiteSpace: "nowrap", padding: "10px 0" }}>
              MEM {memUsedMib ?? "?"}/{memTotalMib ?? "?"} MiB
            </div>
          </div>
        </Html>
      </group>

      {/* Model plaque -- 10-foot-readability sizing (2026-09-13): ~34px, the
          brain's own status line, must read clearly across a room on the 4K
          panel. Wrapped in .hq-beam (Border Beam, see Hud.tsx's shared
          <style>) since this is the hub's own HUD-adjacent plaque. */}
      <Html position={[0, PLAQUE_Y, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
        {/* DECLUTTER pass: outer wrapper the shared resolver owns (vertical
            nudge + fade-beyond-cap), kept separate from `plaqueRef`'s own
            existing bubbleCounterScale close-camera scale-clamp -- see
            Agent.tsx's identical two-wrapper convention/comment. */}
        <div ref={declutterRef} style={{ transformOrigin: "50% 100%" }}>
        <div ref={mergeRefs(plaqueRef, declutterMeasureRef)} className="hq-beam" style={{ "--beam-color": "#7ad9ff", borderRadius: 8 } as CSSProperties}>
          <div
            style={{
              color: "#dff3ff", fontSize: 34, fontWeight: 700, fontFamily: "system-ui, sans-serif",
              background: "rgba(3,4,10,0.7)", padding: "4px 20px", borderRadius: 7,
              whiteSpace: "nowrap", textAlign: "center",
            }}
          >
            {/* World-4 fix (P3): was `{modelName || "BRAIN IDLE"}` -- a
                model-loaded check, not a manager-activity one, so it read
                "IDLE" during a deliberate RTH yield. `wallStatusLine` above
                derives from the identical loop-ledger row the crew panel's
                pill and Gamma's own bubble already read, so this can no
                longer disagree with either. */}
            <div>{wallStatusLine}</div>
            {/* Manager caption (Company Mode item 9, 2026-09-13): one added
                line naming the hub as the "Gamma (Manager)" persona, with
                its own live status color -- no 8th desk, the hub itself is
                persona #7's home. */}
            {manager && (
              <div style={{ fontSize: 26, fontWeight: 600, color: personaStatusColor(manager.status), marginTop: 2 }}>
                {manager.emoji} {manager.name}
              </div>
            )}
          </div>
        </div>
        </div>
      </Html>

      {/* All-hands pulse plaque -- shown for PULSE_DURATION_MS after a new
          station-brief.md mtime is seen (see the effect above); paired with
          the additive ring-speed boost in useFrame. */}
      {pulsing && (
        // Raised from 2.4 (2026-09-13 layout-hygiene pass): the model
        // plaque directly below grew taller once its manager-caption line
        // was bumped 15px->26px for the roster-label-size floor, so this
        // needs more clearance to stay a clean stack, not an overlap.
        <Html position={[0, PULSE_PLAQUE_Y, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
          {/* DECLUTTER pass (POLISH-3): outer wrapper the shared resolver
              owns, kept separate from `pulseRef`'s own existing
              bubbleCounterScale close-camera scale-clamp -- see the main
              plaque's identical two-wrapper convention/comment above. */}
          <div ref={pulseDeclutterRef} style={{ transformOrigin: "50% 100%" }}>
          <div ref={mergeRefs(pulseRef, pulseDeclutterMeasureRef)} className="hq-beam" style={{ "--beam-color": manager?.color ?? PALETTE.hubRing, borderRadius: 8 } as CSSProperties}>
            <div
              style={{
                color: "#fff2fa", fontSize: 20, fontWeight: 800, fontFamily: "system-ui, sans-serif",
                background: "rgba(40,10,30,0.78)", padding: "6px 20px", borderRadius: 7,
                whiteSpace: "nowrap", letterSpacing: 0.5,
              }}
            >
              📋 STATION BRIEF — ALL HANDS
            </div>
          </div>
          </div>
        </Html>
      )}

      {/* Gaming-mode plaque */}
      {gaming && (
        <Html position={[0, GAMING_PLAQUE_Y, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
          <div
            ref={gamingRef}
            style={{
              color: "#ffb020", fontSize: 18, fontWeight: 700, fontFamily: "system-ui, sans-serif",
              background: "rgba(40,26,0,0.75)", padding: "6px 18px", borderRadius: 8,
              border: "1px solid #ffb020", whiteSpace: "nowrap", letterSpacing: 0.5,
              boxShadow: "0 0 18px rgba(255,176,32,0.5)",
            }}
          >
            GPU RESERVED -- J IS GAMING
          </div>
        </Html>
      )}
    </group>
  );
}

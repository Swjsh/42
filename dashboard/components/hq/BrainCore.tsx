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
  });

  const gaugeColor = memFrac > 0.85 ? "#ff3b3b" : memFrac > 0.6 ? "#ffb020" : "#22ff88";

  return (
    <group scale={1.15}>
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
      <group position={[0, -1.6, 0]}>
        <mesh>
          <boxGeometry args={[GAUGE_WIDTH, 0.09, 0.05]} />
          <meshBasicMaterial color="#0e1626" transparent opacity={0.9} />
        </mesh>
        <mesh position={[-GAUGE_WIDTH / 2 + (GAUGE_WIDTH * Math.max(memFrac, 0.02)) / 2, 0, 0.01]}>
          <boxGeometry args={[GAUGE_WIDTH * Math.max(memFrac, 0.02), 0.09, 0.05]} />
          <meshBasicMaterial color={gaugeColor} toneMapped={false} />
        </mesh>
        <Html position={[0, -0.22, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
          <div style={{ color: "#7f93b0", fontSize: 26, fontFamily: "system-ui, sans-serif", whiteSpace: "nowrap" }}>
            MEM {memUsedMib ?? "?"}/{memTotalMib ?? "?"} MiB
          </div>
        </Html>
      </group>

      {/* Model plaque -- 10-foot-readability sizing (2026-09-13): ~34px, the
          brain's own status line, must read clearly across a room on the 4K
          panel. Wrapped in .hq-beam (Border Beam, see Hud.tsx's shared
          <style>) since this is the hub's own HUD-adjacent plaque. */}
      <Html position={[0, 1.75, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
        <div className="hq-beam" style={{ "--beam-color": "#7ad9ff", borderRadius: 8 } as CSSProperties}>
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
      </Html>

      {/* All-hands pulse plaque -- shown for PULSE_DURATION_MS after a new
          station-brief.md mtime is seen (see the effect above); paired with
          the additive ring-speed boost in useFrame. */}
      {pulsing && (
        // Raised from 2.4 (2026-09-13 layout-hygiene pass): the model
        // plaque directly below grew taller once its manager-caption line
        // was bumped 15px->26px for the roster-label-size floor, so this
        // needs more clearance to stay a clean stack, not an overlap.
        <Html position={[0, 2.8, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
          <div className="hq-beam" style={{ "--beam-color": manager?.color ?? PALETTE.hubRing, borderRadius: 8 } as CSSProperties}>
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
        </Html>
      )}

      {/* Gaming-mode plaque */}
      {gaming && (
        <Html position={[0, 3.5, 0]} center distanceFactor={9} style={{ pointerEvents: "none" }}>
          <div
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

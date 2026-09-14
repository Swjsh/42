"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties, RefObject } from "react";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import * as THREE from "three";
import type { PersonaState } from "@/lib/personas";
import { clamp01, lerp, makeMatcapTexture, PALETTE, personaStatusColor } from "./palette";
import { ReactorGreeble } from "./SetKit";

interface BrainCoreProps {
  utilPct: number | null;
  memUsedMib: number | null;
  memTotalMib: number | null;
  modelName: string | null;
  manager: PersonaState | null;
  briefMtimeMs: number | null;
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
}

const GAUGE_WIDTH = 1.8;
const PULSE_DURATION_MS = 10_000;

/**
 * Central hub -- Gamma's "brain core". Sphere + two counter-rotating rings +
 * an additive glow sprite (intensity scales with GPU util) + a memory gauge
 * bar + an <Html> plaque (never drei <Text>, which would fetch a font).
 * Continuous motion (rotation, flicker) is computed directly from
 * state.clock.elapsedTime -- cheap scalar math, no throttling needed.
 */
export default function BrainCore({
  utilPct, memUsedMib, memTotalMib, modelName, manager, briefMtimeMs, gaming, dimFactor, reducedMotion,
  ultra = false, coreMeshRef,
}: BrainCoreProps) {
  const coreMat = useRef<THREE.MeshMatcapMaterial | THREE.MeshPhysicalMaterial>(null);
  const matcap = useMemo(() => makeMatcapTexture(), []);
  const ringA = useRef<THREE.Mesh>(null);
  const ringB = useRef<THREE.Mesh>(null);
  const ringAMat = useRef<THREE.MeshBasicMaterial>(null);
  const ringBMat = useRef<THREE.MeshBasicMaterial>(null);
  const glowMat = useRef<THREE.SpriteMaterial>(null);

  const utilFrac = clamp01((utilPct ?? 0) / 100);
  const memFrac = memUsedMib && memTotalMib ? clamp01(memUsedMib / memTotalMib) : 0;
  // One accent moment (2026-09-13): when the brain is genuinely busy (GPU
  // util > 30%), the rings brighten -- Scene.tsx pairs this with faster
  // corridor pulses from the same utilPct reading.
  const ringBoost = utilFrac > 0.3 ? 1 + Math.min(1, (utilFrac - 0.3) / 0.7) * 0.7 : 1;

  // All-hands pulse (Company Mode step 6, 2026-09-13): fires ~10s of
  // doubled ring speed + a plaque when station-brief.md's mtime
  // (data.brief.mtime_ms, already exposed on /api/hq) changes to a
  // genuinely NEW value -- chosen over analysis/daily-brief/{today}.md
  // per the coordinator's own instruction to "pick the one the data
  // already exposes; state which." The first value seen on mount is a
  // seed, not a trigger, matching the seen-id-diff rule Courier.tsx and
  // HandoffCourier.tsx already use to avoid animating on initial page load.
  const prevBriefMtime = useRef<number | null | undefined>(undefined);
  const pulseActive = useRef(false);
  const pulseEndAtMs = useRef(0);
  const pulseExtraA = useRef(0);
  const pulseExtraB = useRef(0);
  const [pulsing, setPulsing] = useState(false);

  useEffect(() => {
    if (briefMtimeMs === null || briefMtimeMs === undefined) return;
    if (prevBriefMtime.current === undefined) {
      prevBriefMtime.current = briefMtimeMs;
      return;
    }
    if (briefMtimeMs === prevBriefMtime.current) return;
    prevBriefMtime.current = briefMtimeMs;
    pulseActive.current = true;
    pulseEndAtMs.current = performance.now() + PULSE_DURATION_MS;
    setPulsing(true);
    const timer = window.setTimeout(() => setPulsing(false), PULSE_DURATION_MS);
    return () => window.clearTimeout(timer);
  }, [briefMtimeMs]);

  useFrame((state, delta) => {
    const t = state.clock.elapsedTime;
    const spin = reducedMotion ? 0 : t;

    // Pulse rotation is ADDITIVE (an extra angle accumulated via delta),
    // never a multiply on `spin` -- multiplying the elapsed-time-based
    // formula below would snap the rings to a new angle the instant the
    // pulse starts or ends. Accumulating keeps both transitions smooth:
    // "doubled ring speed" becomes base rate + an equal extra rate while
    // the pulse is active, and holds its position afterward (a harmless
    // fixed phase offset, not a jump).
    if (pulseActive.current) {
      if (!reducedMotion && performance.now() < pulseEndAtMs.current) {
        pulseExtraA.current += delta * 0.35;
        pulseExtraB.current += delta * -0.28;
      } else {
        pulseActive.current = false;
      }
    }

    if (ringA.current) ringA.current.rotation.z = spin * 0.35 + pulseExtraA.current;
    if (ringB.current) ringB.current.rotation.x = spin * -0.28 + pulseExtraB.current;

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
    // 2026-09-13) -- the same "brighter = busier" animation now scales the
    // material's own `color` instead, the identical THREE.Color.set(hex).
    // multiplyScalar(factor) pattern already used everywhere else in this
    // file (ring materials) and in StationModule.tsx's screen/edge tint.
    if (coreMat.current) coreMat.current.color.set(PALETTE.hubCore).multiplyScalar(baseGlow + flicker);
    if (glowMat.current) glowMat.current.opacity = clamp01(0.35 + utilFrac * 0.5) * dimFactor;
    if (ringAMat.current) ringAMat.current.color.set(PALETTE.hubRing).multiplyScalar(ringBoost * dimFactor);
    if (ringBMat.current) ringBMat.current.color.set("#7ad9ff").multiplyScalar(ringBoost * dimFactor);
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

      {/* Counter-rotating rings -- thickened (was 0.02-0.025 tube radius,
          near-invisible/aliased with antialias off) and opaque (no blend
          cost) per the TV-crispness pass; brighten together as the "one
          accent moment" when the brain is busy (ringBoost, see above). */}
      <mesh ref={ringA} rotation={[Math.PI / 2.4, 0, 0]}>
        <torusGeometry args={[1.55, 0.05, 8, 48]} />
        <meshBasicMaterial ref={ringAMat} color={PALETTE.hubRing} toneMapped={false} />
      </mesh>
      <mesh ref={ringB} rotation={[0, 0, Math.PI / 3]}>
        <torusGeometry args={[1.95, 0.04, 8, 48]} />
        <meshBasicMaterial ref={ringBMat} color="#7ad9ff" toneMapped={false} />
      </mesh>

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
            <div>{modelName || "BRAIN IDLE"}</div>
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

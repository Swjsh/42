"use client";

import { Suspense } from "react";
import type { CSSProperties } from "react";
import { Html } from "@react-three/drei";
import { KitAgentBody, type KitAnimState } from "./KitAgent";
import { BAY_DESK_OFFSET_Z, BAY_SEAT_LOCAL, CHARACTER_TARGET_HEIGHT, DeskCluster } from "./SetKit";
import { firstBriefSentence, localToWorld, type ScreenLine } from "./palette";

interface GammaCharacterProps {
  /** Desk-cluster center + facing, in the SAME [position, rotationY] shape
   * Scene.tsx already computes for every bay/persona slot (never a new
   * layout convention). Gamma does not walk (she IS the core's manager,
   * fixed at her own desk beside it -- see Scene.tsx's placement comment
   * for the angle/radius choice), so this is the only positioning this
   * component needs. */
  deskCenter: [number, number, number];
  rotationY: number;
  accentColor: string;
  briefText: string;
  briefMtimeMs: number | null;
  utilPct: number | null;
  modelName: string | null;
  gaming: boolean;
}

const THINKING_UTIL_THRESHOLD = 30;

/**
 * Pass B (2026-09-13): "Gamma is a distinct character... at the core desk
 * with an HTML speech bubble". A small standalone component rather than
 * reusing Agent.tsx -- Gamma never walks (Agent's whole state machine is
 * walk-phase plumbing this character doesn't need) and needs her own
 * speech-bubble content logic Agent.tsx has no notion of. Body is FORCED to
 * "character-male-b" (the brief's own spec) via KitAgentBody's
 * `forceBodyId`, bypassing the deterministic-per-seed pick every other
 * character uses -- Gamma is not "a random lane's agent," she's a specific
 * person. Reuses the exact same DeskCluster/BAY_SEAT_LOCAL/
 * BAY_DESK_OFFSET_Z convention every bay and persona desk already uses, so
 * her desk looks like a real desk among the others, not a bespoke prop.
 */
export default function GammaCharacter({
  deskCenter, rotationY, accentColor, briefText, briefMtimeMs, utilPct, modelName, gaming,
}: GammaCharacterProps) {
  const thinking = (utilPct ?? 0) > THINKING_UTIL_THRESHOLD;
  const animState: KitAnimState = thinking ? "thinking" : "resting-working";
  const bubbleText = thinking ? `thinking... ${modelName ?? "model"}` : firstBriefSentence(briefText, 96) || "quiet -- no brief written yet";

  const seatWorld = localToWorld(deskCenter, rotationY, BAY_SEAT_LOCAL);
  const bubbleWorld: [number, number, number] = [seatWorld[0], seatWorld[1] + CHARACTER_TARGET_HEIGHT + 0.4, seatWorld[2]];

  // Gamma's own desk screen -- station-brief metadata (mtime -> "updated
  // Xm ago" reads better here than raw text, which the speech bubble
  // already carries). Kept intentionally short; DeskScreen truncates
  // defensively regardless.
  const screenLines: ScreenLine[] = [
    { text: modelName ?? "no model", color: "#7ad9ff", size: 20 },
    { text: thinking ? "status: THINKING" : "status: idle", color: thinking ? "#ffb020" : "#22ff88", size: 16 },
    { text: briefMtimeMs ? `brief updated ${new Date(briefMtimeMs).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })}` : "no brief yet", size: 14 },
  ];

  return (
    <>
      <group position={deskCenter} rotation={[0, rotationY, 0]}>
        <group position={[0, 0, BAY_DESK_OFFSET_Z]}>
          <Suspense fallback={null}>
            <DeskCluster accentColor={accentColor} screenTitle="GAMMA" screenLines={screenLines} />
          </Suspense>
        </group>
      </group>

      <group position={seatWorld} rotation={[0, rotationY + Math.PI, 0]}>
        <Suspense fallback={null}>
          <KitAgentBody
            laneSeed="gamma-manager"
            forceBodyId="character-male-b"
            animState={animState}
            accentColor={accentColor}
            frozen={gaming}
          />
        </Suspense>
      </group>

      {/* Speech bubble -- 30px, max 2 lines per the brief's own spec.
          `key={bubbleText}` replays the shared .hq-shine sweep (Hud.tsx's
          <style>) whenever the line actually changes, the same "flag a
          change, don't just silently update" tell every other status
          plaque in this scene already uses. */}
      <Html position={bubbleWorld} center distanceFactor={9} style={{ pointerEvents: "none" }}>
        <div className="hq-beam" style={{ "--beam-color": accentColor, borderRadius: 10 } as CSSProperties}>
          <div
            style={{
              position: "relative", overflow: "hidden",
              fontFamily: "system-ui, sans-serif", color: "#dff3ff", fontSize: 30, fontWeight: 600,
              background: "rgba(3,4,10,0.8)", padding: "8px 18px", borderRadius: 9,
              maxWidth: 560, textAlign: "center", lineHeight: 1.25,
              display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflowWrap: "break-word",
            }}
          >
            <span key={bubbleText} className="hq-shine" />
            {bubbleText}
          </div>
        </div>
      </Html>
    </>
  );
}

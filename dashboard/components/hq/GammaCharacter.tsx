"use client";

import { Suspense, useEffect, useMemo, useRef, useState } from "react";
import { Html } from "@react-three/drei";
import { useFrame } from "@react-three/fiber";
import { bubbleCounterScale } from "./bubbleText";
import { KitAgentBody, type KitAnimState } from "./KitAgent";
import { BAY_DESK_OFFSET_Z, BAY_SEAT_LOCAL, CHARACTER_TARGET_HEIGHT, DeskCluster } from "./SetKit";
import { localToWorld, splitBriefSentences, truncateOneLine, type ScreenLine } from "./palette";
import { PRIORITY } from "./labelDeclutter";
import { mergeRefs, useLabelDeclutter } from "./useLabelDeclutter";
import HeadLabel from "./HeadLabel";
import { modelGlyph } from "./headLabelModel";
import { useIsKiosk } from "./LiveAgents";

interface GammaLoopRow {
  ts_et: string;
  status: string;
  reason: string;
}

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
  /** World-2 coordinator review (2026-09-14, "GAMMA'S BUBBLE says
   * 'thinking… model' while the crew panel says YIELDING (rth_window) and
   * the wall says BRAIN IDLE -- three surfaces disagreeing, one of them
   * false"): `data.brainVitals.lastRow` -- the SAME loop-ledger row the
   * crew panel's own pill ultimately traces back to (PersonaState's
   * quietReason is derived from this identical ledger upstream, in
   * lib/personas.ts). This is now the PRIMARY truth for the bubble text --
   * see this component's own bubbleText derivation below. */
  lastRow: GammaLoopRow | null;
  /** Same computation as Hud.tsx's own crew-panel "next:" line for Gamma
   * (`lib/crew.ts#crewNextLine`) -- passed in from Scene.tsx rather than
   * recomputed here so the bubble's own "next ~HH:MM" is GUARANTEED
   * identical to the panel's, not just independently similar. */
  nextLine: string | null;
  /** PEOPLE pass (2026-09-14) -- replaces the old `suppressBubble: boolean`
   * (which HID Gamma's bubble entirely while a hub-exchange visitor was at
   * her desk, relying on ActivityBubbleLayer's own now-deleted
   * "hubevent:gamma-ack" floating bubble to show her ack instead -- "nothing
   * floating at a fixed point in space" is this pass's own explicit rule).
   * Non-null while Scene.tsx's own Chef/Coach -> Gamma hub exchange is
   * active: her ONE bubble shows this deterministic ack
   * (lib/dialogue.ts#GAMMA_CREW_ACK) instead of the normal thinking/brief
   * cycle below -- still exactly one bubble at her desk, never two. Null the
   * rest of the time (her own status/brief text shows as before). */
  ackOverride: string | null;
  /** BRAIN-TRUTH fix (2026-09-15) -- see BrainCore.tsx's own `brainBusy`
   * prop comment for the full root-cause. Same field (`data.runtime.brain
   * .busy`), same Ollama-`ollama ps`-verified truth, now the sole source
   * for this bubble's own "thinking" text too, replacing the local
   * gpu_util_pct-vs-THINKING_UTIL_THRESHOLD re-derivation below. */
  brainBusy: boolean;
}
// PEOPLE pass (P2): same "little bubble" char budget spirit as Agent.tsx's
// own BUBBLE_ACTION_MAX_CHARS, sized a bit larger since "Gamma" (5 chars) is
// shorter than this roster's longest name ("Treasurer") -- leaves the same
// approximate total-line-width the brief's own "max ~36 chars" spec names.
const GAMMA_BUBBLE_ACTION_MAX_CHARS = 30;

/** First token of a loop-ledger `reason` string, e.g. "rth_window" from
 * "rth_window (weekday 09:30-15:55 ET)" -- the coordinator's own "<reason
 * short>" spec for the yielding bubble. */
function shortReason(reason: string): string {
  const m = /^[^\s(]+/.exec(reason.trim());
  return m ? m[0] : reason;
}

function hhmmEt(ms: number): string {
  return new Date(ms).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "America/New_York" });
}

/**
 * Pass B (2026-09-13): "Gamma is a distinct character... at the core desk
 * with an HTML speech bubble". A small standalone component rather than
 * reusing Agent.tsx -- Gamma never walks (Agent's whole state machine is
 * walk-phase plumbing this character doesn't need) and needs her own
 * speech-bubble content logic Agent.tsx has no notion of. Body is FORCED to
 * a specific pack body ("character-b" under the BLOCKY-CHARACTERS pack,
 * 2026-09-15 -- was "character-male-b" under the retired Mini Characters
 * pack, see SetKit.tsx#CHARACTER_PACK) via KitAgentBody's
 * `forceBodyId`, bypassing the deterministic-per-seed pick every other
 * character uses -- Gamma is not "a random lane's agent," she's a specific
 * person. Reuses the exact same DeskCluster/BAY_SEAT_LOCAL/
 * BAY_DESK_OFFSET_Z convention every bay and persona desk already uses, so
 * her desk looks like a real desk among the others, not a bespoke prop.
 */
export default function GammaCharacter({
  deskCenter, rotationY, accentColor, briefText, briefMtimeMs, utilPct: _utilPct, modelName, gaming,
  lastRow, nextLine, ackOverride, brainBusy,
}: GammaCharacterProps) {
  // BRAIN-TRUTH fix (2026-09-15) -- see this file's own `brainBusy` prop
  // comment. No longer a local gpu_util_pct-vs-threshold re-derivation;
  // `brainBusy` IS `data.runtime.brain.busy`, the Ollama-`ollama ps`-
  // verified truth Hud.tsx's side panel already reads, so the two can no
  // longer disagree the way the real capture caught them doing.
  const thinking = brainBusy;
  const isKiosk = useIsKiosk();
  const animState: KitAnimState = thinking ? "thinking" : "resting-working";

  // Item 2d (LIVE-1, 2026-09-14, J: "it still a 'Dead' world"): cycle EVERY
  // real sentence of the brief, one every 20s, instead of freezing on the
  // first one forever. Resets to sentence 0 whenever a genuinely NEW brief
  // lands (briefMtimeMs changing -- the same field BrainCore's own all-hands
  // pulse and Scene.tsx's CameraRig focus-trigger already key off) so a
  // fresh brief always opens at its own beginning rather than wherever the
  // PREVIOUS brief's rotation happened to be.
  const sentences = useMemo(() => splitBriefSentences(briefText, 96), [briefText]);
  const [sentenceIdx, setSentenceIdx] = useState(0);
  useEffect(() => {
    setSentenceIdx(0);
  }, [briefMtimeMs]);
  useEffect(() => {
    if (sentences.length <= 1) return;
    const id = window.setInterval(() => setSentenceIdx((i) => (i + 1) % sentences.length), 20_000);
    return () => window.clearInterval(id);
  }, [sentences.length]);
  // World-2 coordinator review (2026-09-14): the bubble's PRIMARY truth is
  // now the loop-ledger row, matching the crew panel exactly --
  // "yielded"/"error" always win outright (never overridden by a stray
  // util spike or leftover brief text), "ok" falls through to the existing
  // thinking/brief-cycling behavior (both already true, non-contradictory
  // facts once "yielded"/"error" can no longer leak through as "thinking").
  let bubbleText: string;
  if (ackOverride) {
    // PEOPLE pass: a hub-exchange visitor (Chef/Coach) is AT her desk this
    // instant -- her own bubble becomes the ack, outranking even a genuine
    // error/yield state for the ~2min exchange window (Scene.tsx's own
    // EVENT_BUBBLE_WINDOW_MIN), matching "Gamma's ack stays on Gamma's
    // bubble" from this pass's own brief.
    bubbleText = ackOverride;
  } else if (lastRow?.status === "yielded") {
    bubbleText = `yielding · ${shortReason(lastRow.reason)}${nextLine ? ` · next ~${nextLine}` : ""}`;
  } else if (lastRow?.status === "error") {
    bubbleText = `error: ${truncateOneLine(lastRow.reason, 60)}`;
  } else if (thinking) {
    bubbleText = `thinking... ${modelName ?? "model"}`;
  } else if (sentences.length > 0) {
    bubbleText = sentences[sentenceIdx % sentences.length];
  } else if (briefMtimeMs) {
    bubbleText = `wrote the brief ${hhmmEt(briefMtimeMs)}`;
  } else {
    bubbleText = "quiet -- no brief written yet";
  }

  const seatWorld = localToWorld(deskCenter, rotationY, BAY_SEAT_LOCAL);
  const bubbleWorld: [number, number, number] = [seatWorld[0], seatWorld[1] + CHARACTER_TARGET_HEIGHT + 0.4, seatWorld[2]];
  // DECLUTTER pass: Gamma never walks -- bubbleWorld is stable per render,
  // so the getter can just close over it directly (no ref indirection
  // needed the way a moving Agent/LiveAgentAvatar requires).
  // U5-LEGIBLE-LABELS (2026-09-16): Gamma's own head label is answer-
  // bearing (identity, not decoration) -- see labelDeclutter.ts's own
  // `LabelRect.mustStayLegible` header.
  const { wrapperRef: declutterRef, measureRef: declutterMeasureRef } = useLabelDeclutter("gamma", PRIORITY.GAMMA, () => bubbleWorld, undefined, true);
  // Same on-screen size policy as every other head bubble (bubbleText.ts#
  // bubbleCounterScale): ref mutation in useFrame, never React state.
  const bubbleWrapRef = useRef<HTMLDivElement>(null);
  useFrame((state) => {
    const el = bubbleWrapRef.current;
    if (!el) return;
    const c = state.camera.position;
    const dist = Math.hypot(bubbleWorld[0] - c.x, bubbleWorld[1] - c.y, bubbleWorld[2] - c.z);
    const k = bubbleCounterScale(dist);
    el.style.transform = Math.abs(k - 1) > 0.01 ? `scale(${k.toFixed(3)})` : "";
  });

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
            <DeskCluster position={deskCenter} rotationY={rotationY} accentColor={accentColor} screenTitle="GAMMA" screenLines={screenLines} />
          </Suspense>
        </group>
      </group>

      <group position={seatWorld} rotation={[0, rotationY + Math.PI, 0]}>
        <Suspense fallback={null}>
          <KitAgentBody
            laneSeed="gamma-manager"
            forceBodyId="character-b"
            animState={animState}
            accentColor={accentColor}
            frozen={gaming}
          />
        </Suspense>
      </group>

      {/* HEAD-LABELS pass (2026-09-15, J: "labels are too big and wordy") --
          compact label (dot + "Gamma" + house glyph for her local Ollama
          brain) replaces the old always-on "Gamma · <line>" bubble.
          `bubbleText`'s own derivation above is UNCHANGED (yielding/error/
          thinking/brief-sentence-cycling) -- it now shows on HOVER only
          (HeadLabel's `detail`), including while a hub-exchange visitor's
          ack is active (`ackOverride` already folds into `bubbleText`
          upstream, so this still reads as "one bubble, never two").
          `detailKey={line}` still replays the shared `.hq-shine` sweep
          whenever the line actually changes -- motion still means events
          even though the text itself no longer floats permanently. */}
      {(() => {
        const line = truncateOneLine(bubbleText, GAMMA_BUBBLE_ACTION_MAX_CHARS);
        const { glyph, title: glyphTitle } = modelGlyph("local-llm", null, modelName);
        return (
        <Html position={bubbleWorld} center distanceFactor={9} style={{ pointerEvents: "none" }}>
          {/* DECLUTTER pass: outer wrapper the shared resolver owns, kept
              separate from `bubbleWrapRef`'s own camera-distance scale --
              see Agent.tsx's identical convention/comment. */}
          <div ref={declutterRef} style={{ transformOrigin: "50% 100%" }}>
          <div ref={mergeRefs(bubbleWrapRef, declutterMeasureRef)} style={{ position: "relative", transformOrigin: "50% 100%", pointerEvents: isKiosk ? "none" : "auto" }}>
            <HeadLabel
              name="Gamma"
              glyph={glyph}
              glyphTitle={glyphTitle}
              dotColor={accentColor}
              accentColor={accentColor}
              detail={line}
              detailKey={line}
              interactive={!isKiosk}
            />
          </div>
          </div>
        </Html>
        );
      })()}
    </>
  );
}

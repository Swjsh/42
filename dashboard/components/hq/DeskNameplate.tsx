"use client";

// ─── U4 usability fix (2026-09-16, USABILITY-FIXES worker) ─────────────────
// Real run (hq_live_probe.py --usability, commit ca5d7813) FAILed U4: "Pilot,
// Analyst" (both IDLE this run) had no persona head label on/near the
// default view -- Scene.tsx's own `showAgent = persona.status !== "IDLE"`
// (see that file's own comment just above the gate) hides the whole <Agent>
// mount, HeadLabel included, for an IDLE persona. That gate is honest --
// "an empty desk for an IDLE persona is honest" per Scene.tsx's own comment
// -- but honest must not mean invisible: an empty desk still needs to answer
// "what is this persona doing?" This component is the answer for the
// `!showAgent` branch: a small nameplate anchored at the desk itself (no
// character body), same HeadLabel.tsx look every other label in this scene
// already uses, registered with the SAME declutter manager every other
// label joins (useLabelDeclutter) so it never overlaps another label.
//
// Reuses HeadLabel.tsx verbatim rather than forking its markup -- the only
// new logic here is WHERE it's anchored (a fixed desk position, not a
// walking character's live group.position) and what `detail` shows (the
// persona's own quiet reason / next fire, from lib/crew.ts#deriveCrewPill --
// the SAME derivation Hud.tsx's roster panel and Scene.tsx's own hover
// panel already use, so all three surfaces agree).

import { useMemo, useRef } from "react";
import * as THREE from "three";
import { useFrame } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import HeadLabel from "./HeadLabel";
import { useLabelDeclutter } from "./useLabelDeclutter";
import { PRIORITY } from "./labelDeclutter";
import { CHARACTER_SCALE, CHARACTER_TARGET_HEIGHT } from "./SetKit";
// Same kiosk detection Agent.tsx's own HeadLabel mount already uses (no
// pointer on a kiosk display -- disables hover, matching every other label
// in this scene), read directly here rather than threaded through Scene.tsx
// as a prop this component's only caller doesn't otherwise need.
import { useIsKiosk } from "./LiveAgents";
// U4 usability FOLLOW-UP fix (2026-09-16, same worker, same pass): the
// first version of this component shipped WITHOUT the camera-distance
// counter-scale every other label producer in this file's own family
// applies (Agent.tsx#updateBubbleFade, LiveAgents.tsx, GammaCharacter.tsx,
// BrainCore.tsx, HoloChart.tsx -- all import this exact function). Root
// cause, confirmed by a direct repro against the live page: at the
// overview camera's real distance, drei's plain `distanceFactor` shrinks
// this label's natural size below LabelDeclutterManager's own
// legibility-floor pass (labelDeclutter.ts's unconditional "height <
// legibilityFloorPx -> opacity 0" rule) -- caught it measuring 11.1px
// (repro: check_usability_u4 against a live capture showed
// `{"h": 11.1, "opacity": 0, "visible": false}` for Pilot's own nameplate)
// -- the scene was genuinely too small here, not a check bug. Every other
// label in this codebase holds a floor size via bubbleCounterScale
// regardless of distance; this component simply never wired that in.
import { bubbleCounterScale } from "./bubbleText";

const BUBBLE_FADE_DISTANCE = 80; // same floor Agent.tsx's own bubble fade uses

// Same head-height formula Agent.tsx's own ULTRA_HEAD_Y/BUBBLE_HEAD_GAP use
// (see that file's own comment) -- a nameplate over an EMPTY desk sits at
// the exact head height a character WOULD occupy at that desk, so the
// label doesn't jump vertically the moment the persona goes GREEN/YELLOW/
// RED and the real <Agent> (with its own HeadLabel at this same Y) mounts.
const NAMEPLATE_HEAD_Y = CHARACTER_TARGET_HEIGHT * CHARACTER_SCALE * 0.95 + 0.3;

export interface DeskNameplateProps {
  /** Persona name, used verbatim as the declutter id (`persona:${name}`) --
   * the SAME id Agent.tsx registers under for this persona (see that file's
   * own `declutterId`), which is safe here because the two are mutually
   * exclusive: Scene.tsx only mounts ONE of {Agent, DeskNameplate} per
   * persona per render, gated on the same `showAgent` boolean. */
  name: string;
  /** Fixed desk position (persona's own slot.position) -- unlike Agent.tsx's
   * `group.current.position`, there is no walking body to track here. */
  position: [number, number, number];
  glyph: string;
  glyphTitle: string;
  /** The persona's own real quiet reason / next-fire text (deriveCrewPill's
   * `reason`), shown on hover -- never a fabricated "idle" placeholder. */
  detail: string;
  detailKey: string;
}

/**
 * Desk nameplate for an IDLE persona whose <Agent> body is not rendered --
 * see this file's own header for the root cause + fix. Deliberately gray
 * (dotColor/accentColor #7f93b0, matching CREW_PILL_COLOR's own "no strong
 * status" tone) so it reads as "present but quiet," never confused with a
 * GREEN/YELLOW/RED persona's own colored label.
 */
export default function DeskNameplate({ name, position, glyph, glyphTitle, detail, detailKey }: DeskNameplateProps) {
  const isKiosk = useIsKiosk();
  const interactive = !isKiosk;
  const headWorldPos = useMemo(
    (): [number, number, number] => [position[0], position[1] + NAMEPLATE_HEAD_Y, position[2]],
    [position],
  );
  const declutterId = `persona:${name}`;
  const declutterWorldPos = useMemo(() => () => headWorldPos, [headWorldPos]);
  // U5-LEGIBLE-LABELS (2026-09-16): a desk nameplate is answer-bearing
  // (identity, not decoration) -- see labelDeclutter.ts's own
  // `LabelRect.mustStayLegible` header.
  const { wrapperRef: declutterRef, measureRef: declutterMeasureRef } = useLabelDeclutter(declutterId, PRIORITY.PERSONA, declutterWorldPos, undefined, true);

  // Camera-distance fade + counter-scale -- identical policy to every other
  // label producer's own updateBubbleFade (see this file's own import
  // header for the FAIL this fixes). `bubbleWrapRef` is the SAME inner
  // element `declutterMeasureRef` also measures (mergeRefs below), matching
  // Agent.tsx's own two-different-purposes-one-element convention: the
  // declutter manager measures/offsets this element's OUTER wrapper, while
  // this per-frame effect owns the element's own opacity/transform, exactly
  // as useLabelDeclutter.ts's own header describes the split.
  const bubbleWrapRef = useRef<HTMLDivElement | null>(null);
  const bubbleDelta = useMemo(() => new THREE.Vector3(), []);
  useFrame((state) => {
    const el = bubbleWrapRef.current;
    if (!el) return;
    bubbleDelta.set(
      headWorldPos[0] - state.camera.position.x,
      headWorldPos[1] - state.camera.position.y,
      headWorldPos[2] - state.camera.position.z,
    );
    const dist = bubbleDelta.length();
    el.style.opacity = dist > BUBBLE_FADE_DISTANCE ? "0" : "1";
    const k = bubbleCounterScale(dist);
    el.style.transform = Math.abs(k - 1) > 0.01 ? `scale(${k.toFixed(3)})` : "";
  });

  return (
    <Html position={headWorldPos} center distanceFactor={9} style={{ pointerEvents: "none" }}>
      <div ref={declutterRef} style={{ transformOrigin: "50% 100%" }}>
        <div
          ref={(el) => {
            bubbleWrapRef.current = el;
            declutterMeasureRef.current = el;
          }}
          style={{ position: "relative", transformOrigin: "50% 100%", pointerEvents: interactive ? "auto" : "none" }}
        >
          <HeadLabel
            name={name}
            glyph={glyph}
            glyphTitle={glyphTitle}
            dotColor="#7f93b0"
            accentColor="#7f93b0"
            detail={detail}
            detailKey={detailKey}
            interactive={interactive}
          />
        </div>
      </div>
    </Html>
  );
}

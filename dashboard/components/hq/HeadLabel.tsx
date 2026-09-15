"use client";

import { useState } from "react";
import type { CSSProperties } from "react";
import { truncateName } from "./headLabelModel";

export interface HeadLabelProps {
  /** Real name/id shown above the head -- truncated here (not by the
   * caller) so every call site agrees on the same 14-char budget. */
  name: string;
  /** One plain glyph char (headLabelModel.ts#modelGlyph's `.glyph`) -- no
   * Anthropic logo/wordmark, per ENVIRONMENT-PLAN.md part C. */
  glyph: string;
  /** Hover title for the glyph -- the literal evidence string
   * (modelGlyph's `.title`), never invented copy. */
  glyphTitle: string;
  /** Discord-style status dot color (headLabelModel.ts#statusDotColor). */
  dotColor: string;
  /** `.hq-beam` accent ring color -- same field every bubble already used
   * (persona/lane status color, a live agent's tint, Gamma's accentColor). */
  accentColor: string;
  /** The FULL detail line the compact label no longer shows inline --
   * shown only on hover (desktop) per J: "long status text belongs in
   * hover/click, not floating over the scene." Null renders no hover
   * content at all (nothing to say), matching this scene's existing
   * "never a fabricated line" rule. */
  detail: string | null;
  /** Changes only when a REAL event lands (a new bubble action, a new
   * audit verdict, ...) -- replays the shared `.hq-shine` one-shot sweep,
   * so motion still means events per the HQ "no TV wake, motion=events"
   * house rule even though the wordy text itself no longer floats. */
  detailKey: string;
  /** False on a kiosk display (no pointer) -- disables the hover handlers
   * entirely, matching LiveAgents.tsx's existing `isKiosk` convention. */
  interactive: boolean;
  onHoverChange?: (hovered: boolean) => void;
}

/**
 * Compact head label: [dot] NAME [glyph], one row, bold high-contrast
 * outlined name (Among Us legibility convention, ENVIRONMENT-PLAN.md part C
 * source 3) -- replaces the old wordy "<name> · <action text>" bubble in
 * Agent.tsx / LiveAgents.tsx / GammaCharacter.tsx. The former action/status
 * text is still reachable: `detail` renders as a hover-only tooltip
 * (desktop, non-kiosk) using the exact tooltip shape LiveAgents.tsx already
 * shipped for `taskDetail`. Click-to-focus is unchanged and lives entirely
 * outside this component (Scene.tsx's own `hoveredTarget` panel) -- this
 * component adds no click handler of its own, per this pass's own scope.
 *
 * Deliberately DOM-only -- callers keep owning the outer `<Html>` +
 * `declutterRef`/`bubbleWrapRef` (or `declutterMeasureRef`) wrappers exactly
 * as before; the declutter manager measures those, not this component, so
 * this file must never itself become the measured/positioned root.
 */
export default function HeadLabel({ name, glyph, glyphTitle, dotColor, accentColor, detail, detailKey, interactive, onHoverChange }: HeadLabelProps) {
  const [hovered, setHovered] = useState(false);
  const shownName = truncateName(name);

  return (
    <div
      style={{ position: "relative" }}
      onMouseEnter={
        interactive
          ? () => {
              setHovered(true);
              onHoverChange?.(true);
            }
          : undefined
      }
      onMouseLeave={
        interactive
          ? () => {
              setHovered(false);
              onHoverChange?.(false);
            }
          : undefined
      }
    >
      <div className="hq-beam" style={{ "--beam-color": accentColor, borderRadius: 6 } as CSSProperties}>
        <div
          style={{
            position: "relative", overflow: "hidden",
            fontFamily: "system-ui, sans-serif", color: "#dff3ff", fontSize: 22,
            background: "rgba(3,4,10,0.78)", padding: "2px 8px", borderRadius: 5,
            whiteSpace: "nowrap", display: "flex", alignItems: "center", gap: 6,
          }}
        >
          <span key={detailKey} className="hq-shine" />
          {/* Discord-style status dot (ENVIRONMENT-PLAN.md part C source 1)
              -- ~1/4-1/3 of the label's own text height, per that source's
              own avatar-dot proportion. */}
          <span
            aria-hidden
            style={{ width: 8, height: 8, borderRadius: "50%", background: dotColor, flex: "0 0 auto", boxShadow: "0 0 3px rgba(0,0,0,0.6)" }}
          />
          <b
            style={{
              fontWeight: 800,
              textShadow: "0 1px 0 #000, 0 -1px 0 #000, 1px 0 0 #000, -1px 0 0 #000",
            }}
          >
            {shownName}
          </b>
          <span title={glyphTitle} style={{ fontSize: 16, lineHeight: 1 }}>
            {glyph}
          </span>
        </div>
      </div>
      {/* Speech-bubble tail -- same shape/positioning every prior bubble
          used (Agent.tsx/LiveAgents.tsx/GammaCharacter.tsx), kept so the
          silhouette above a character's head stays visually consistent. */}
      <div
        style={{
          position: "absolute", left: "50%", bottom: -4, width: 8, height: 8,
          transform: "translateX(-50%) rotate(45deg)",
          background: "rgba(3,4,10,0.78)",
          borderRight: `1px solid ${accentColor}`, borderBottom: `1px solid ${accentColor}`,
        }}
      />
      {/* Hover-only detail (Two Point Hospital convention, part C source 5:
          "name-only... revealed on hover rather than always-on"). Absolute
          + pointerEvents:none, out of flow, so it can never perturb the
          declutter manager's own getBoundingClientRect() measurement of the
          label box above (same reasoning LiveAgents.tsx's own taskDetail
          tooltip already relied on). */}
      {hovered && interactive && detail ? (
        <div
          style={{
            position: "absolute", left: "50%", bottom: "calc(100% + 10px)",
            transform: "translateX(-50%)", pointerEvents: "none",
            maxWidth: 340, width: "max-content",
            fontFamily: "system-ui, sans-serif", color: "#dff3ff", fontSize: 20,
            background: "rgba(3,4,10,0.92)", border: `1px solid ${accentColor}`,
            borderRadius: 6, padding: "6px 10px",
            whiteSpace: "normal", wordBreak: "break-word", lineHeight: 1.35,
          }}
        >
          {detail}
        </div>
      ) : null}
    </div>
  );
}

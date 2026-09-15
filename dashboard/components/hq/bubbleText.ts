// PEOPLE pass (P2, 2026-09-14, J: "little bubbles above their heads of the
// action they are doing"). Pure text derivation for the ONE little bubble
// Agent.tsx/GammaCharacter.tsx render above every character's head --
// deliberately the ONLY place this text gets composed, so the 3D bubble,
// Hud.tsx's flat roster panel, and any future reader all agree on what a
// persona/lane is doing right now. Every function here is a pure function
// of already-real evidence (lib/crew.ts's own pill derivation, a lane's own
// SectorRow fields) -- NEVER fabricated copy, matching this pass's own
// "text from real data only" rule. Kept import-light (no fs/fetch) so it is
// safely callable from a client component (Agent.tsx/Scene.tsx) and remains
// unit-testable in isolation (each export is a deterministic function of its
// arguments, no hidden clock/module state).

import type { PersonaState } from "@/lib/personas";
import { deriveCrewPill, crewNowLine, type CrewPill } from "@/lib/crew";

// A defensive cap only -- Agent.tsx/GammaCharacter.tsx truncate again to
// their own render budget (BUBBLE_ACTION_MAX_CHARS / the 2-line clamp) via
// palette.ts#truncateOneLine; this just stops a pathological upstream string
// (a multi-KB preview blob) from ever reaching that far.
const ACTION_SAFETY_CAP = 140;

function cap(s: string): string {
  return s.length > ACTION_SAFETY_CAP ? `${s.slice(0, ACTION_SAFETY_CAP - 1)}…` : s;
}

/** Turns one evidence-backed CrewPill (lib/crew.ts#deriveCrewPill) into the
 * bubble's own action phrase -- exported separately from
 * `personaBubbleAction` so a caller that already computed the pill (Hud.tsx's
 * roster panel does, every render) never has to re-derive it. WORKING shows
 * the live now-line (pill.reason already IS that, per deriveCrewPill's own
 * construction); DONE collapses "fired HH:MM ET · next ..." down to just the
 * forward-looking half ("done · next ..."); WAITING/YIELDING/GHOST prefix
 * the pill's own reason with its kind so the bubble reads as a full sentence
 * ("waiting · next open 09:30 ET") instead of a bare fragment. */
export function pillBubbleAction(pill: CrewPill): string {
  switch (pill.kind) {
    case "WORKING":
      return cap(pill.reason);
    case "DONE": {
      const m = /next (.+)$/.exec(pill.reason);
      return cap(m ? `done · next ${m[1]}` : `done · ${pill.reason}`);
    }
    case "WAITING":
      return cap(`waiting · ${pill.reason}`);
    case "YIELDING":
      return cap(`yielding · ${pill.reason}`);
    case "GHOST":
      return cap(`ghost · ${pill.reason}`);
    default:
      return cap(pill.reason);
  }
}

/** Persona action text straight from a PersonaState -- derives the pill
 * itself (lib/crew.ts#deriveCrewPill) so a caller with no pill in hand yet
 * (Scene.tsx's own activityCandidates memo, today, computes text ad hoc)
 * only needs the persona + `nowMs`. Same evidence lib/crew.ts's
 * `crewNowLine`/`deriveCrewPill` already feed the flat roster panel --
 * the 3D bubble and the HUD panel can never disagree about what a persona
 * is doing, because both read the identical derivation. */
export function personaBubbleAction(p: PersonaState, nowMs: number): string {
  // deriveCrewPill's own WORKING branch already calls crewNowLine internally
  // and falls back to a generic reason if it's null -- re-deriving here
  // (rather than hand-rolling the same fallback) keeps this file's only
  // real logic in ONE place (pillBubbleAction) instead of two. `crewNowLine`
  // is re-exported below (not called directly here) for a caller that wants
  // the raw now-line text without the WAITING/YIELDING/GHOST prefixing.
  return pillBubbleAction(deriveCrewPill(p, nowMs));
}

/** Lane agent action text -- identical wording rule to Scene.tsx's existing
 * activityCandidates derivation (a RED lane's evidence gets a "!" prefix,
 * everything else reads "<state> · <evidence>"). Takes a narrow structural
 * slice (not the full SectorRow type) so this file never needs to import
 * lib/hq.ts. */
export function laneBubbleAction(row: { state: string; evidence: string; health: string }): string {
  return cap(row.health === "red" ? `! ${row.evidence}` : `${row.state} · ${row.evidence}`);
}

export { crewNowLine, deriveCrewPill };
export type { CrewPill };

// Head-bubble on-screen size policy lives in bubbleScale.ts (import-free so node --test can load it).
export { BUBBLE_FAR_REF_DISTANCE, BUBBLE_MAX_COUNTER_SCALE, BUBBLE_NEAR_HOLD_DISTANCE, bubbleCounterScale } from "./bubbleScale";

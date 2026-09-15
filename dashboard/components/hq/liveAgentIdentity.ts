// LIVE-AGENTS identity pass (queue item f, 2026-09-15): a distinct visual
// look per agent TYPE + a short display name for the bubble header. Pure,
// react/three-free (same "no sibling value import" convention as
// liveAgentWalk.ts's own header) so it stays plain-`node --test`-able and
// carries zero risk of pulling lib/hq-agents.ts's fs import into the client
// bundle (see LiveAgents.tsx's own header on why that import must stay
// type-only).
//
// Input is deliberately narrow: lib/hq-agents.ts#buildLiveAgents already
// resolves each row to `label` ("session" for the main session -- an empty
// agent_id, per that module's own comment -- else the real pulse.py
// agent_type string, "agent" as ITS OWN bare fallback when agent_type came
// back empty). No model name is ever available here (PulseRow carries no
// such field -- see hq-agents.ts's own wire type) and this module never
// invents one.
//
// HEAD-LABELS pass (2026-09-15): now imports headLabelModel.ts's pure
// `modelGlyph` for the identity's own glyph/glyphTitle fields below --
// still react/three-COMPONENT-free (headLabelModel.ts only reads palette.ts's
// plain color-map consts, no JSX/hooks), so this stays `node --test`-able.

import { modelGlyph } from "./headLabelModel";

export type LiveAgentTypeKind = "session" | "worker" | "explore" | "other";

export interface LiveAgentIdentity {
  kind: LiveAgentTypeKind;
  /** Feeds KitAgentBody's own `accentColor` prop (head-beacon color + a
   * faint 12% body tint, both ALREADY-EXISTING geometry -- see KitAgent.tsx
   * -- so a per-type look costs zero added draw calls) and the bubble's
   * `--beam-color` border. */
  tint: string;
  /** Short, human name for the bubble header -- replaces the raw label
   * string so the header and any future name label can never show two
   * different things for the same agent. */
  displayName: string;
  /** HEAD-LABELS pass (2026-09-15): the model-tier glyph shown after the
   * name in the compact head label (headLabelModel.ts#modelGlyph). Every live
   * agent gets the SAME generic "claude-live" glyph regardless of `kind`
   * (session/worker/explore/other) -- pulse.jsonl rows carry no model
   * name at all (see this file's own header), so this module never
   * invents a Sonnet/Opus/Haiku tier for one. */
  glyph: string;
  /** Hover title for `glyph` -- literal, honest "tier unknown" text. */
  glyphTitle: string;
}

// Real pulse.jsonl agent_type values seen in production (2026-09-15 tail:
// "general-purpose" x1681, "" x312 [-> "session"/"agent"], "gamma" x18,
// "Explore" x18 -- see automation/state/hooks/pulse.jsonl). "gamma" and any
// other named subagent_type this project adds later fall through to the
// deterministic "other" bucket below rather than getting a hand-picked slot
// each -- the spec asks for "a small deterministic map," not one branch per
// persona.
const SESSION_TINT = "#38bdf8"; // the main Claude Code session -- distinct blue/cyan "this is you" accent
const WORKER_TINT = "#a3e635"; // general-purpose -- ordinary worker, lime/green
const EXPLORE_TINT = "#facc15"; // Explore -- read-only scout, amber/yellow

// Fallback palette for every OTHER agent_type (custom subagent_type like
// "gamma", or the bare "agent" fallback for an empty agent_type) -- kept
// distinct from the three named tints above so a fallback-bucket agent
// never gets mistaken for session/worker/explore. Cycled by a deterministic
// hash of the agent's own stable id (never arrival order, never Math.random)
// so the SAME agent id keeps the SAME color across polls/re-renders/re-
// mounts, and two different concurrent "other"-type agents usually land on
// different hues.
const OTHER_PALETTE = ["#fb923c", "#f472b6", "#34d399", "#c084fc"];

/** Deterministic (never Date.now()/Math.random) string hash -- same FNV-ish
 * shape as this codebase's other seeded-pick helpers (SetKit.tsx's own
 * pickCharacterBody uses an equivalent pattern on `laneSeed`). */
function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (h * 31 + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

/** Maps a live agent's server-classified `label` (lib/hq-agents.ts's own
 * `LiveAgent.label`) + its stable `id` to a deterministic look. Type ->
 * look, per this task's own design: main session gets its own accent,
 * general-purpose gets the "worker" look, Explore gets the "read-only
 * scout" look, and every other real or future agent_type falls through to
 * a deterministic (never random) fallback bucket keyed off the agent's own
 * id so it still reads as visually distinct from its siblings. */
export function liveAgentIdentity(label: string, id: string): LiveAgentIdentity {
  const { glyph, title: glyphTitle } = modelGlyph("claude-live");
  if (label === "session") {
    return { kind: "session", tint: SESSION_TINT, displayName: "Claude (you)", glyph, glyphTitle };
  }
  if (label === "general-purpose") {
    return { kind: "worker", tint: WORKER_TINT, displayName: "general-purpose", glyph, glyphTitle };
  }
  if (label === "Explore") {
    return { kind: "explore", tint: EXPLORE_TINT, displayName: "Explore", glyph, glyphTitle };
  }
  const displayName = label || "agent";
  const tint = OTHER_PALETTE[hashString(id || displayName) % OTHER_PALETTE.length];
  return { kind: "other", tint, displayName, glyph, glyphTitle };
}

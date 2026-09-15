// HEAD-LABELS pass (LABELS worker, 2026-09-15) -- pure, react/component-free
// helpers for the compact per-character head label (name + model-tier glyph
// + status dot; long action/status text moved to hover/click per J: "labels
// are too big and wordy"). See dashboard/components/hq/ENVIRONMENT-PLAN.md
// "## Design pass 2026-09-15 (J top-down feedback)" part C for the sourced
// label conventions this implements: Discord's dot-color mapping (source 1),
// Among Us's bold-outline name legibility + char-cap truncation (source 3),
// Two Point Hospital's hover-only detail with an always-on name (source 5),
// and the plain-glyph model-tier table (lightning=Sonnet, sparkle/crown=
// Opus, leaf=Haiku, house=local Ollama, gear=Python/cron, question mark=
// unknown -- deliberately NO Anthropic logo/wordmark, trademark-protected
// per that section's own citation).
//
// Kept import-light (only palette.ts's plain color-map consts, no React/
// three usage at call time) so this stays `node --test`-able in isolation,
// matching this codebase's other pure-logic modules (bubbleText.ts,
// liveAgentIdentity.ts, liveAgentWalk.ts).

import { HEALTH_COLOR, PERSONA_STATUS_COLOR } from "./palette";

/** The four real runtime shapes a head label's model glyph can represent,
 * per lib/hq-runtime.ts#HqRoleRuntimeKind plus one extra: "claude-live" for
 * an ephemeral Claude Code session/subagent (LiveAgents.tsx) -- those carry
 * NO model name at all (see liveAgentIdentity.ts's own header on why), so
 * they are deliberately a DIFFERENT kind from a classified `claude-session`
 * role (Analyst/Treasurer), which at least has a real `producer` string to
 * read. Conflating the two would risk inventing a tier for a live agent
 * that has no evidence for one. */
export type ModelGlyphKind = "python-script" | "local-llm" | "claude-session" | "claude-live" | "none";

export interface GlyphResult {
  glyph: string;
  /** Hover/title text explaining the glyph. NEVER invented -- always the
   * literal source string this project already has evidence for (a role's
   * real `producer` text, Gamma's real `brain.model`, or the honest
   * "tier unknown" label for a live agent with no model field at all). */
  title: string;
}

const TIER_GLYPH: Record<"sonnet" | "opus" | "haiku", string> = {
  sonnet: "⚡", // lightning bolt
  opus: "✨", // sparkle
  haiku: "🍃", // leaf
};

/** Case-insensitive single-token tier scan over a claude-session role's own
 * `producer` free text (lib/hq-runtime.ts's ROLE_CLASSIFICATION strings --
 * e.g. Gamma_Conductor's "opus judgment" aside). Only ever called for the
 * `claude-session` kind (never `local-llm`, whose producer text can ALSO
 * mention "opus" in an unrelated aside without that making the local brain
 * an Opus model) -- see modelGlyph's own switch below. Returns null rather
 * than guessing when the text names no tier -- "never invents a tier for
 * empty producer text" is a graded test case in hq-head-label.test.ts. */
function parseTier(producerText: string | null | undefined): "sonnet" | "opus" | "haiku" | null {
  if (!producerText) return null;
  const m = /\b(sonnet|opus|haiku)\b/i.exec(producerText);
  return m ? (m[1].toLowerCase() as "sonnet" | "opus" | "haiku") : null;
}

/**
 * Maps a runtime kind (+ optional real evidence text) to the compact glyph
 * shown immediately after a head label's name, per ENVIRONMENT-PLAN.md part
 * C's model-tier table. `producerText` is read ONLY for `claude-session`
 * (a classified role's real `producer` string, e.g. Analyst/Treasurer);
 * `modelName` is read ONLY for `local-llm` (Gamma's real
 * `data.runtime.brain.model`). Both optional, never fabricated when absent.
 */
export function modelGlyph(kind: ModelGlyphKind, producerText?: string | null, modelName?: string | null): GlyphResult {
  switch (kind) {
    case "python-script":
      return {
        glyph: "⚙", // gear
        title: producerText ? `Python / deterministic script -- ${producerText}` : "Python / deterministic script",
      };
    case "local-llm":
      return {
        glyph: "🏠", // house
        title: modelName ? `Local model (Ollama) -- ${modelName}` : "Local model (Ollama)",
      };
    case "claude-session": {
      const tier = parseTier(producerText);
      return {
        glyph: tier ? TIER_GLYPH[tier] : "✦", // generic sparkle when the producer text names no tier
        // Hover shows the LITERAL producer string regardless of whether a
        // tier was parsed out of it -- per this pass's own brief, the
        // source text is the truth, the glyph is only a hint.
        title: producerText ?? "Claude session",
      };
    }
    case "claude-live":
      return { glyph: "✦", title: "Claude · tier unknown" };
    case "none":
    default:
      return { glyph: "?", title: producerText ?? "unknown runtime" };
  }
}

/** Which enum a status-dot value belongs to -- persona statuses
 * (GREEN/YELLOW/RED/IDLE) and lane health (green/amber/red/frozen/zombie)
 * are disjoint axes (palette.ts's own PERSONA_STATUS_COLOR/HEALTH_COLOR
 * comment: never share one lookup), and a live agent has neither field --
 * it hands in an already-resolved hex via "explicit". */
export type DotStatusKind = "persona" | "lane" | "explicit";

/** Discord-style status dot color (ENVIRONMENT-PLAN.md part C, source 1) --
 * reuses palette.ts's own color maps rather than a new hex value, so a head
 * label's dot always agrees with every other surface reading the same
 * status field (Hud.tsx's roster panel, a bay's own accent ring). */
export function statusDotColor(kind: DotStatusKind, value: string): string {
  if (kind === "persona") return PERSONA_STATUS_COLOR[value] ?? PERSONA_STATUS_COLOR.IDLE;
  if (kind === "lane") return HEALTH_COLOR[value] ?? "#7f93b0";
  return value; // "explicit" -- value IS already a resolved hex color
}

/** Among Us-style name cap (ENVIRONMENT-PLAN.md part C, source 3 recommends
 * 12-14 chars here vs. Among Us's own bare 10, since our label also carries
 * a glyph + dot). The ellipsis itself counts against `max` so the returned
 * string is never longer than `max`. */
export function truncateName(name: string, max = 14): string {
  const flat = name.trim();
  if (flat.length <= max) return flat;
  return `${flat.slice(0, Math.max(1, max - 1))}…`;
}

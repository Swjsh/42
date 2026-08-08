// Shared types for the Gamma App (/gamma route group). Deliberately has ZERO
// runtime imports (no node:fs, no node:child_process) so it is safe to import
// from both server modules (lib/gamma-app.ts, app/api/gamma/route.ts) and the
// "use client" page/components -- a client component must never pull in a
// module that touches Node builtins, or the browser bundle build breaks.

export type StateWord = "TRADING" | "RESEARCHING" | "STANDING BY";

/** Mirrors gamma_hq.py's `_build_view_dict()` --json output field-for-field.
 * Null when the Python shell-out itself failed (missing venv, script error,
 * timeout) -- the rest of the Gamma App still renders without it. */
export interface PresenceView {
  now_et_label: string;
  state_word: StateWord;
  goal_line: string;
  todays_focus: string;
  tape_headline: string;
  tape_segments: Array<{ account: string; n: number; pnl: number }>;
  right_now: string | null;
  /** `explain` is one real, honest sentence built from the same
   * *-shadow-progress.json fields `have`/`need` were derived from (see
   * gamma_hq.py's `_clock_explain`) -- surfaced only in the MONEY tile's
   * expanded state. */
  clocks: Array<{ label: string; have: number | null; need: number; extra: string; explain: string }>;
  wants: string[];
  recent_ships: string[];
}

export type ActivityEventType = "commit" | "narrative" | "trade" | "shadow_fill";

export interface ActivityEvent {
  type: ActivityEventType;
  /** True UTC instant as an ISO string -- always a real timestamp, never a guess. */
  atIso: string;
  title: string;
  subtitle?: string;
  /** "up" (win/bull/green) | "down" (loss/bear/red) | undefined (neutral). */
  tone?: "up" | "down";
  /** Extra real detail beyond the one-line title -- e.g. a commit's full body
   * (git log %b), a trade row's remaining CSV fields. Undefined when the
   * source genuinely has nothing more to say (never fabricated to fill
   * space). Shown on hover/expand, never invented. */
  detail?: string;
}

export interface WantItem {
  id: string;
  priority: number;
  text: string;
}

export interface ThisWeekItem {
  id: string;
  priority: string;
  text: string;
  /** Real "depends:"/"status:" clauses parsed from the same queue.md line,
   * when present -- never fabricated. Undefined when the line carried none. */
  detail?: string;
}

export interface GammaAppView {
  fetchedAt: string;
  presence: PresenceView | null;
  activity: ActivityEvent[];
  wants: WantItem[];
  thisWeek: ThisWeekItem[];
}

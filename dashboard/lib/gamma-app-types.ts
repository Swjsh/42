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
  clocks: Array<{ label: string; have: number | null; need: number; extra: string }>;
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
}

export interface GammaAppView {
  fetchedAt: string;
  presence: PresenceView | null;
  activity: ActivityEvent[];
  wants: WantItem[];
  thisWeek: ThisWeekItem[];
}

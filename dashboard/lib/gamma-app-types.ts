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

/** Real per-arm P&L for the Money tile's progress bars -- one row per active
 * fleet arm (see lib/fleet-pnl.ts), always 5 rows, never omitted even when an
 * arm traded zero times today. targetLow/targetHigh are J's per-account
 * $100-200/day band (CLAUDE.md 2026-08-07 correction: PER ACCOUNT, not
 * book-wide). */
export interface FleetArmPnl {
  armId: string;
  displayName: string;
  todayPnl: number;
  todayTrades: number;
  targetLow: number;
  targetHigh: number;
  weekPnl: number;
  allTimePnl: number;
}

export type ActivityEventType = "commit" | "narrative" | "trade" | "shadow_fill";

export interface ActivityEvent {
  type: ActivityEventType;
  /** True UTC instant as an ISO string -- always a real timestamp, never a guess. */
  atIso: string;
  /** Short, plain-English "ad tile" title (e.g. "Fixed a bug", "Won on
   * Bullish reclaim ride the ribbon") -- always visible, never jargon. */
  headline: string;
  /** One clean supporting line under the headline, always visible while the
   * card is collapsed (e.g. the humanized commit subject, "SPY $773 call —
   * +$614"). Undefined when the headline already says everything. */
  description?: string;
  /** "up" (win/bull/green) | "down" (loss/bear/red) | undefined (neutral). */
  tone?: "up" | "down";
  /** The full technical breakdown -- e.g. a commit's untruncated subject +
   * hash + body, a trade's entry/exit prices and hold time. Revealed only
   * when the card is clicked open. Undefined when the source genuinely has
   * nothing more to say (never fabricated to fill space). */
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
  /** Optional so existing empty-view literals (e.g. the page's pre-load
   * placeholder) don't need updating -- buildGammaAppView always populates
   * this with 5 real rows once the API actually responds. */
  fleetPnl?: FleetArmPnl[];
}

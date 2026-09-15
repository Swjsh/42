// HQ-TRADE-MOMENTS (2026-09-15): day-close summary gating + shape. Shows
// once (after 16:00 ET, i.e. the 15:55 ET EOD-flatten task plus a buffer)
// on a real session day that actually had fills -- "before 16:00 it must
// not appear" per the task spec. A session day with zero fills (weekend,
// holiday, kill-switch day) never shows a fabricated all-zero summary
// either: `hasAnyFillsToday` is the caller's own real signal (fleet P&L's
// arms all reporting trades:0 with no read error), not a guessed calendar.

import type { FleetPnlLive } from "./hq-fleet-pnl-live-pure";

/** After the given ET hour:minute cutoff (default 16:00, the task's own
 * spec) -- plain integer comparison, no Date/timezone math (the caller
 * supplies real ET wall-clock hour/minute, same convention palette.ts's
 * nowEtMinutes/isRegularTradingHours already use elsewhere in this app). */
export function isAfterEtCutoff(hourEt: number, minuteEt: number, cutoffHour = 16, cutoffMinute = 0): boolean {
  return hourEt * 60 + minuteEt >= cutoffHour * 60 + cutoffMinute;
}

/** The one gate this whole feature is built around: day-close shows iff
 * it's past the ET cutoff AND at least one arm actually traded today. Both
 * conditions required -- a quiet post-close evening with zero fills (a
 * valid, expected state per the "sitting out is a valid day" doctrine)
 * never shows a fabricated all-zero summary; a busy morning before the
 * cutoff never shows a summary either, even with fills already in hand. */
export function shouldShowDayClose(hourEt: number, minuteEt: number, hasAnyFillsToday: boolean): boolean {
  return hasAnyFillsToday && isAfterEtCutoff(hourEt, minuteEt);
}

export interface DayCloseSummary {
  bookRealizedUsd: number;
  wins: number;
  losses: number;
  arms: FleetPnlLive["arms"];
  setupNames: string[];
}

/** Builds the day-close summary payload from the same FleetPnlLive the live
 * P&L panel already renders (one source of truth, no second P&L
 * computation) plus the day's distinct setup name(s) (journal/trades.csv's
 * own `setup` column, since fills-ledger.jsonl carries no strategy/setup
 * field -- see hq-fleet-pnl-live.ts's adapter for where these strings come
 * from; this pure function just dedupes+sorts whatever the caller found). */
export function buildDayCloseSummary(fleetPnl: FleetPnlLive, setupNamesRaw: readonly string[]): DayCloseSummary {
  const wins = fleetPnl.arms.reduce((sum, a) => sum + a.wins, 0);
  const losses = fleetPnl.arms.reduce((sum, a) => sum + a.losses, 0);
  const setupNames = [...new Set(setupNamesRaw.filter((s) => s.trim().length > 0))].sort();
  return {
    bookRealizedUsd: fleetPnl.bookRealizedUsd,
    wins,
    losses,
    arms: fleetPnl.arms,
    setupNames,
  };
}

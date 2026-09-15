// MARKET-TRUTH (2026-09-15): pure formatters for the market.live quote +
// per-account engine bar/action, shared by the HUD trading strip, the hub
// wall SPY plaque, and Pilot's desk screen. Zero fs/path/workspace imports
// (same split lib/hq-chart-pure.ts documents) so this is directly
// `node --test`-able without a bundler.

import type { LiveMarketQuote } from "./hq";

/** "live 759.40 · 20s" / "live 759.40 · 3m12s (stale)" / "live: unavailable".
 * `staleAfterS` mirrors lib/quote.ts's own STALE_AFTER_S (180s) -- kept as a
 * parameter (default 180) rather than a second hardcoded copy of that
 * constant, so a caller can pass the real one if it ever changes. */
export function formatLiveSpyLine(live: LiveMarketQuote | null, staleAfterS = 180): string {
  if (!live || live.spy === null) return "live SPY: unavailable";
  const price = live.spy.toFixed(2);
  if (live.age_s === null) return `live ${price}`;
  const stale = live.age_s > staleAfterS ? " (stale)" : "";
  const ageTxt = live.age_s < 60 ? `${Math.round(live.age_s)}s` : `${Math.floor(live.age_s / 60)}m${Math.round(live.age_s % 60)}s`;
  return `live ${price} · ${ageTxt}${stale}`;
}

/** Short "engine bar" clause contrasting the engine's last-closed-bar price
 * against the live tape -- e.g. "engine bar 760.76" -- only worth showing
 * next to a live price so the viewer can see the lag, never standalone. */
export function formatEngineBarClause(engineBarSpy: number | null): string {
  return engineBarSpy === null ? "engine bar: n/a" : `engine bar ${engineBarSpy.toFixed(2)}`;
}

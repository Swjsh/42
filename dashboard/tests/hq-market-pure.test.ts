// MARKET-TRUTH (2026-09-15): unit tests for lib/hq-market-pure.ts -- the
// live-quote + engine-bar formatters the HUD trading strip and the hub wall
// SPY plaque both now use. Run: cd dashboard && npm test

import { test } from "node:test";
import assert from "node:assert/strict";
import { formatLiveSpyLine, formatEngineBarClause } from "../lib/hq-market-pure.ts";
import type { LiveMarketQuote } from "../lib/hq.ts";

function quote(overrides: Partial<LiveMarketQuote> = {}): LiveMarketQuote {
  return { spy: 759.4, ts_et: "09:36:01", age_s: 20, source: "sight-beacon", ...overrides };
}

test("formats a fresh live quote with sub-minute age", () => {
  assert.equal(formatLiveSpyLine(quote({ age_s: 20 })), "live 759.40 · 20s");
});

test("formats a fresh live quote with minute-scale age", () => {
  assert.equal(formatLiveSpyLine(quote({ age_s: 95 })), "live 759.40 · 1m35s");
});

test("flags an age beyond the stale threshold", () => {
  assert.equal(formatLiveSpyLine(quote({ age_s: 200 }), 180), "live 759.40 · 3m20s (stale)");
});

test("null quote or null price degrades to an honest unavailable line, never a guess", () => {
  assert.equal(formatLiveSpyLine(null), "live SPY: unavailable");
  assert.equal(formatLiveSpyLine(quote({ spy: null })), "live SPY: unavailable");
});

test("engine bar clause formats a real number and n/a for null, never fabricates", () => {
  assert.equal(formatEngineBarClause(760.75), "engine bar 760.75");
  assert.equal(formatEngineBarClause(null), "engine bar: n/a");
});

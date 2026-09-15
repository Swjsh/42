// WORLD-6 (2026-09-14, W1): unit tests for lib/hq-chart-pure.ts -- the pure
// half of lib/hq-chart-data.ts (the fs-touching getHoloChartData() is
// exercised live instead, via `curl /api/hq-chart` against the real files --
// same convention this dashboard's one prior test file (hq-runtime.test.ts)
// already established, and the same reason: no bundler/mocking layer here,
// so only the pure half is unit-testable without a live server).
//
// Imports from lib/hq-chart-pure.ts directly (NOT lib/hq-chart-data.ts,
// which imports the real lib/chart-data.ts#getChartData value -- that
// module's own "./workspace" specifier is extensionless, which Node's
// native ESM loader cannot resolve without a bundler; see hq-chart-pure.ts's
// own header for the full reasoning, confirmed by reproducing the
// ERR_MODULE_NOT_FOUND this split avoids).
//
// Run: cd dashboard && node --test tests/hq-chart-data.test.ts

import { test } from "node:test";
import assert from "node:assert/strict";
import {
  chartTimeToEtDateStr,
  filterToLatestSessionDate,
  atIsoToChartTime,
  nearestBarIndex,
  dedupeTradeMarkers,
  filterLevelsNearRange,
  isWeekdayEt,
  computeSessionStatusLabel,
  buildIntradayCandles,
  type HoloLevel,
  type IntradayTick,
} from "../lib/hq-chart-pure.ts";
import type { ChartBar, ChartTradeMarker } from "../lib/chart-data.ts";
// Extensionless (not "../lib/time.ts") -- lib/time.ts has zero imports of
// its own so this is a leaf specifier; keeping it extensionless (unlike the
// two .ts-suffixed imports above, kept as-is/pre-existing) avoids TS5097
// under this repo's `moduleResolution: "bundler"` tsconfig (no
// allowImportingTsExtensions) while still resolving under `npm test`'s own
// tests/resolve-ts-extensionless.loader.mjs hook (retries a bare relative
// specifier with ".ts" appended -- see that file's own header).
import { isMarketHoursET } from "../lib/time";

function bar(time: number, overrides: Partial<ChartBar> = {}): ChartBar {
  return { time, open: 760, high: 761, low: 759, close: 760.5, ...overrides };
}

// ─── chartTimeToEtDateStr ───────────────────────────────────────────────────

test("chartTimeToEtDateStr reads the ET digits encoded as UTC, not a real UTC date", () => {
  // 2026-09-14 14:00:00 encoded AS UTC (etDigitsToChartTime's own convention).
  const t = Date.UTC(2026, 8, 14, 14, 0, 0) / 1000;
  assert.equal(chartTimeToEtDateStr(t), "2026-09-14");
});

test("chartTimeToEtDateStr handles a late-session bar just before midnight UTC-encoding", () => {
  const t = Date.UTC(2026, 8, 14, 23, 55, 0) / 1000;
  assert.equal(chartTimeToEtDateStr(t), "2026-09-14");
});

// ─── filterToLatestSessionDate ──────────────────────────────────────────────

test("filterToLatestSessionDate keeps only the newest distinct ET date", () => {
  const bars: ChartBar[] = [
    bar(Date.UTC(2026, 8, 11, 15, 55, 0) / 1000),
    bar(Date.UTC(2026, 8, 11, 15, 55, 0) / 1000 + 1), // still 09-11, contrived
    bar(Date.UTC(2026, 8, 14, 9, 30, 0) / 1000),
    bar(Date.UTC(2026, 8, 14, 9, 35, 0) / 1000),
    bar(Date.UTC(2026, 8, 14, 15, 55, 0) / 1000),
  ];
  const { date, bars: kept } = filterToLatestSessionDate(bars);
  assert.equal(date, "2026-09-14");
  assert.equal(kept.length, 3);
  assert.ok(kept.every((b) => chartTimeToEtDateStr(b.time) === "2026-09-14"));
});

test("filterToLatestSessionDate returns null/[] for an empty bar list, never throws", () => {
  const { date, bars } = filterToLatestSessionDate([]);
  assert.equal(date, null);
  assert.deepEqual(bars, []);
});

// ─── atIsoToChartTime ────────────────────────────────────────────────────────

test("atIsoToChartTime converts a real UTC instant to the ET-digits-as-UTC encoding (EDT, UTC-4)", () => {
  // journal/trades.csv real row this session: entry 2026-09-14 14:01:06 ET.
  // parseBareTimestampInZone would produce this true UTC instant for that
  // wall-clock ET time during EDT (UTC-4): 18:01:06Z.
  const atIso = new Date(Date.UTC(2026, 8, 14, 18, 1, 6)).toISOString();
  const chartTime = atIsoToChartTime(atIso);
  const expected = Date.UTC(2026, 8, 14, 14, 1, 6) / 1000;
  assert.equal(chartTime, expected);
});

test("atIsoToChartTime returns null for an unparsable string, never throws", () => {
  assert.equal(atIsoToChartTime("not a date"), null);
});

// ─── nearestBarIndex ─────────────────────────────────────────────────────────

test("nearestBarIndex finds the closest bar by |time delta|", () => {
  const bars: ChartBar[] = [bar(1000), bar(1300), bar(1600), bar(1900)];
  assert.equal(nearestBarIndex(bars, 1000), 0);
  assert.equal(nearestBarIndex(bars, 1450), 1); // 150 away from 1300, 150 from 1600 -> first wins (not strictly less)
  assert.equal(nearestBarIndex(bars, 1620), 2);
  assert.equal(nearestBarIndex(bars, 5000), 3);
});

test("nearestBarIndex returns null for an empty bar list", () => {
  assert.equal(nearestBarIndex([], 1000), null);
});

// ─── dedupeTradeMarkers ──────────────────────────────────────────────────────

function trade(atIso: string, overrides: Partial<ChartTradeMarker> = {}): ChartTradeMarker {
  return { atIso, side: "entry", direction: "call", price: 0.39, setup: "ribbon_ride", note: null, pnl: null, ...overrides };
}

test("dedupeTradeMarkers collapses same-minute/side/direction/price rows into one, counting them", () => {
  // Real shape this session: 4 fleet-arm fills of the SAME 763C entry within
  // seconds of each other (14:01:06 / 14:01:08 / 14:01:10).
  const rows: ChartTradeMarker[] = [
    trade("2026-09-14T18:01:06.000Z"),
    trade("2026-09-14T18:01:08.000Z"),
    trade("2026-09-14T18:01:10.000Z"),
  ];
  const out = dedupeTradeMarkers(rows);
  assert.equal(out.length, 1);
  assert.equal(out[0].count, 3);
  assert.equal(out[0].atIso, rows[0].atIso); // first occurrence wins position
});

test("dedupeTradeMarkers keeps distinct minutes/sides/directions separate", () => {
  const rows: ChartTradeMarker[] = [
    trade("2026-09-14T18:01:06.000Z", { side: "entry" }),
    trade("2026-09-14T18:02:07.000Z", { side: "exit", price: 0.4 }),
    trade("2026-09-14T14:01:08.000Z", { side: "entry", direction: "put" }),
  ];
  const out = dedupeTradeMarkers(rows);
  assert.equal(out.length, 3);
  assert.ok(out.every((m) => m.count === 1));
});

// ─── filterLevelsNearRange ───────────────────────────────────────────────────

function level(price: number, type: HoloLevel["type"] = "support"): HoloLevel {
  return { price, type, tag: type.toUpperCase(), source: "test" };
}

test("filterLevelsNearRange excludes a level far outside today's traded range", () => {
  // Real shape this session: session range ~757-763, levels at 748.09 and
  // 774.71 sit 9-12 dollars away -- both should be excluded.
  const levels = [level(748.09), level(757.44), level(761.32), level(774.71, "resistance")];
  const out = filterLevelsNearRange(levels, 757.77, 762.72);
  const prices = out.map((l) => l.price).sort((a, b) => a - b);
  assert.deepEqual(prices, [757.44, 761.32]);
});

test("filterLevelsNearRange widens the band on a wide-range day (60% of range, floor $2)", () => {
  const levels = [level(700), level(750), level(800)];
  // range 750, band = max(2, 0.6*100) = 60 -> [640,860] roughly for a 100-wide range
  const out = filterLevelsNearRange(levels, 700, 800);
  assert.equal(out.length, 3); // all within [700-60,800+60]
});

test("filterLevelsNearRange respects an explicit band override", () => {
  const levels = [level(757), level(760), level(770)];
  const out = filterLevelsNearRange(levels, 758, 762, 1);
  const prices = out.map((l) => l.price).sort((a, b) => a - b);
  assert.deepEqual(prices, [757, 760]); // 770 is 8 away, band=1 excludes it
});

// ─── HOLOCHART-TRUTH (2026-09-15): isMarketHoursET boundary + isWeekdayEt +
//     computeSessionStatusLabel -- the root-cause fix for the stale
//     "SPY · <yesterday> session · closed" label during live RTH. ──────────

test("isMarketHoursET: 09:29:59 ET is before the open (RTH edge)", () => {
  // 2026-09-15 is a real Tuesday (matches et_clock.py's own read this
  // session: "2026-09-15 10:35:50 Tuesday EDT"). EDT = UTC-4.
  const d = new Date(Date.UTC(2026, 8, 15, 13, 29, 59)); // 09:29:59 EDT
  assert.equal(isMarketHoursET(d), false);
});

test("isMarketHoursET: 09:31:00 ET is inside RTH", () => {
  const d = new Date(Date.UTC(2026, 8, 15, 13, 31, 0)); // 09:31:00 EDT
  assert.equal(isMarketHoursET(d), true);
});

test("isWeekdayEt: Tuesday 2026-09-15 is a weekday", () => {
  assert.equal(isWeekdayEt("2026-09-15"), true);
});

test("isWeekdayEt: Saturday 2026-09-12 is not a weekday", () => {
  assert.equal(isWeekdayEt("2026-09-12"), false);
});

test("isWeekdayEt: Sunday 2026-09-13 is not a weekday", () => {
  assert.equal(isWeekdayEt("2026-09-13"), false);
});

test("isWeekdayEt: malformed input fails closed (never RTH on garbage)", () => {
  assert.equal(isWeekdayEt("not-a-date"), false);
});

test("computeSessionStatusLabel: bars ARE today's and it's RTH -> open/live", () => {
  const { status, label } = computeSessionStatusLabel("2026-09-15", "2026-09-15", true, true);
  assert.equal(status, "open");
  assert.equal(label, "SPY · 2026-09-15 session · live");
});

test("computeSessionStatusLabel: THE BUG CASE -- bars stuck on yesterday, RTH, live tick fresh -> open, explicit no-intraday-bars caption (never claims yesterday is today)", () => {
  const { status, label } = computeSessionStatusLabel("2026-09-14", "2026-09-15", true, true);
  assert.equal(status, "open");
  assert.equal(label, "SPY · live (no intraday bars)");
  assert.ok(!label.includes("2026-09-14"), "must never present yesterday's date as the current session");
});

test("computeSessionStatusLabel: bars stale, RTH, but live NOT fresh -> honestly closed, labeled with the real bars date", () => {
  const { status, label } = computeSessionStatusLabel("2026-09-14", "2026-09-15", true, false);
  assert.equal(status, "closed");
  assert.equal(label, "SPY · 2026-09-14 session · closed");
});

test("computeSessionStatusLabel: after hours (not RTH) -> closed regardless of live freshness", () => {
  const { status, label } = computeSessionStatusLabel("2026-09-15", "2026-09-15", false, true);
  assert.equal(status, "closed");
  assert.equal(label, "SPY · 2026-09-15 session · closed");
});

test("computeSessionStatusLabel: weekend -- caller passes isRth=false (isWeekdayEt gate) even with a fresh live tick -> closed", () => {
  // Simulates hq-chart-data.ts's own call site: isRth = isMarketHoursET(now) && isWeekdayEt(today).
  // On a Saturday, isWeekdayEt("2026-09-12") is false, so isRth is false
  // regardless of the wall-clock time-of-day component.
  const today = "2026-09-12"; // Saturday
  const isRth = true /* pretend isMarketHoursET() said yes */ && isWeekdayEt(today);
  assert.equal(isRth, false);
  const { status } = computeSessionStatusLabel("2026-09-11", today, isRth, true);
  assert.equal(status, "closed");
});

test("computeSessionStatusLabel: no bars at all, but live is fresh -> open, no-intraday-bars caption", () => {
  const { status, label } = computeSessionStatusLabel(null, "2026-09-15", true, true);
  assert.equal(status, "open");
  assert.equal(label, "SPY · live (no intraday bars)");
});

test("computeSessionStatusLabel: no bars at all and no live -> honest no-data", () => {
  const { status, label } = computeSessionStatusLabel(null, "2026-09-15", true, false);
  assert.equal(status, "no-data");
  assert.equal(label, "SPY · no local session data");
});

// ─── buildIntradayCandles ───────────────────────────────────────────────────

function tick(hh: number, mm: number, ss: number, price: number, date = "2026-09-15"): IntradayTick {
  return { tsEt: `${date}T${String(hh).padStart(2, "0")}:${String(mm).padStart(2, "0")}:${String(ss).padStart(2, "0")}`, price };
}

test("buildIntradayCandles: empty input -> no bars, not partial", () => {
  const { bars, lastBarPartial } = buildIntradayCandles([], 600);
  assert.equal(bars.length, 0);
  assert.equal(lastBarPartial, false);
});

test("buildIntradayCandles: first bar -- single tick at session open becomes an O=H=L=C candle", () => {
  const { bars } = buildIntradayCandles([tick(9, 30, 5, 600)], 600);
  assert.equal(bars.length, 1);
  assert.deepEqual(bars[0], {
    time: Math.floor(Date.UTC(2026, 8, 15, 9, 30, 0) / 1000),
    open: 600,
    high: 600,
    low: 600,
    close: 600,
  });
});

test("buildIntradayCandles: multiple ticks in one 5m window fold into one OHLC bar", () => {
  const ticks = [
    tick(9, 30, 5, 600), // open
    tick(9, 31, 0, 602), // high
    tick(9, 32, 0, 598), // low
    tick(9, 34, 30, 601), // close
  ];
  const { bars } = buildIntradayCandles(ticks, 600);
  assert.equal(bars.length, 1);
  assert.equal(bars[0].open, 600);
  assert.equal(bars[0].high, 602);
  assert.equal(bars[0].low, 598);
  assert.equal(bars[0].close, 601);
});

test("buildIntradayCandles: gaps -- a quiet bucket with zero ticks is OMITTED, never fabricated", () => {
  const ticks = [
    tick(9, 30, 0, 600), // bucket 09:30
    // bucket 09:35 has no ticks at all
    tick(9, 41, 0, 605), // bucket 09:40
  ];
  const { bars } = buildIntradayCandles(ticks, 650);
  assert.equal(bars.length, 2); // NOT 3 -- no fabricated 09:35 bar
  const times = bars.map((b) => b.time - Math.floor(Date.UTC(2026, 8, 15, 0, 0, 0) / 1000));
  assert.equal(times[0], 9 * 3600 + 30 * 60);
  assert.equal(times[1], 9 * 3600 + 40 * 60);
});

test("buildIntradayCandles: dedupe -- exact duplicate (tsEt, price) ticks (e.g. two accounts sharing a core_tick_id) count once", () => {
  const ticks = [tick(9, 30, 5, 600), tick(9, 30, 5, 600), tick(9, 30, 5, 600)];
  const { bars } = buildIntradayCandles(ticks, 600);
  assert.equal(bars.length, 1);
  assert.equal(bars[0].open, 600);
  assert.equal(bars[0].close, 600);
});

test("buildIntradayCandles: ticks outside 09:30-16:00 ET (pre-market/post-close) are excluded", () => {
  const ticks = [tick(8, 0, 0, 590), tick(9, 30, 0, 600), tick(16, 5, 0, 620)];
  const { bars } = buildIntradayCandles(ticks, 600);
  assert.equal(bars.length, 1);
  assert.equal(bars[0].open, 600);
});

test("buildIntradayCandles: last bar is partial when now is still inside its 5m window", () => {
  const ticks = [tick(9, 30, 0, 600), tick(9, 52, 0, 610)];
  // now = 09:53 -- still inside the 09:50-09:55 bucket
  const { lastBarPartial } = buildIntradayCandles(ticks, 9 * 60 + 53);
  assert.equal(lastBarPartial, true);
});

test("buildIntradayCandles: last bar is NOT partial once its 5m window has fully elapsed", () => {
  const ticks = [tick(9, 30, 0, 600), tick(9, 52, 0, 610)];
  // now = 09:56 -- the 09:50-09:55 bucket has closed even with no new tick
  const { lastBarPartial } = buildIntradayCandles(ticks, 9 * 60 + 56);
  assert.equal(lastBarPartial, false);
});

test("buildIntradayCandles: DST-safe -- bare ET digits parse identically regardless of the calendar date's own DST state (no Date-timezone conversion involved)", () => {
  // 2026-11-01 is the Sunday DST-fallback date in the US; using it here
  // proves the bucketer never routes through a real timezone conversion
  // that a DST boundary could corrupt -- it is pure digit arithmetic.
  const ticks = [tick(9, 30, 0, 600, "2026-11-02"), tick(9, 33, 0, 603, "2026-11-02")];
  const { bars } = buildIntradayCandles(ticks, 600);
  assert.equal(bars.length, 1);
  assert.equal(bars[0].time, Math.floor(Date.UTC(2026, 10, 2, 9, 30, 0) / 1000));
  assert.equal(bars[0].high, 603);
});

test("buildIntradayCandles: sample matching core-decisions.jsonl's real ts_et shape ('YYYY-MM-DDTHH:MM:SS', no zone) parses correctly", () => {
  const ticks: IntradayTick[] = [
    { tsEt: "2026-09-15T10:51:04", price: 756.925 },
    { tsEt: "2026-09-15T10:52:03", price: 756.925 }, // different account, same tick's spy -- caller dedupes by core_tick_id upstream
  ];
  const { bars } = buildIntradayCandles(ticks, 660);
  assert.equal(bars.length, 1); // both land in the 10:50-10:55 bucket
  assert.equal(bars[0].close, 756.925);
});

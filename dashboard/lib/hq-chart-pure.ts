// WORLD-6 (2026-09-14, W1): the PURE half of lib/hq-chart-data.ts -- no fs,
// no node:child_process, no path-aliased ("@/...") imports, and (the part
// that actually matters for `node --test`) no RUNTIME import of anything
// that itself has an extensionless relative import in its own graph. Split
// out from hq-chart-data.ts specifically so this file is directly
// executable by Node's native TypeScript stripping with zero bundler --
// same reasoning lib/hq-runtime.ts's own header already documents for its
// identical split. The one import below (`ChartBar`/`ChartTradeMarker` from
// "./chart-data") is `import type` only -- fully erased by type-stripping,
// never a real module-resolution attempt at runtime, so it does NOT pull in
// chart-data.ts's own extensionless "./workspace" import chain the way a
// value import would (verified this session: swapping this to a value
// import reproduces exactly the ERR_MODULE_NOT_FOUND a bare `node --test`
// hits on lib/chart-data.ts's own "./workspace" specifier).
//
// See dashboard/tests/hq-chart-data.test.ts for the unit tests, and
// lib/hq-chart-data.ts for the fs-touching assembly that calls these.

import type { ChartBar, ChartTradeMarker } from "./chart-data";

export interface HoloLevel {
  price: number;
  type: "support" | "resistance";
  /** Short display label, e.g. "SUPPORT" / "RESISTANCE" -- never the raw
   * machine `label` field (e.g. "SHELF_747.29_748.89_2026-09-14"), which
   * reads as noise at hologram-legible font sizes. */
  tag: string;
  source: string;
}

/** ChartBar.time (see lib/chart-data.ts's own etDigitsToChartTime) encodes
 * the literal ET wall-clock digits a bar happened at, stored AS a
 * UTCTimestamp -- it is NOT a true UTC instant. Derives that same "YYYY-MM-DD"
 * ET date string from one, using UTC getters (matching the encoding, never
 * a real timezone conversion, which would double-convert). */
export function chartTimeToEtDateStr(time: number): string {
  const d = new Date(time * 1000);
  const y = d.getUTCFullYear();
  const mo = String(d.getUTCMonth() + 1).padStart(2, "0");
  const day = String(d.getUTCDate()).padStart(2, "0");
  return `${y}-${mo}-${day}`;
}

/** Keeps only the bars from the LATEST distinct ET date present -- "the
 * session", never the 1-2-trading-day window lib/chart-data.ts's own
 * loadRecentBars keeps for its DOM chart's continuity purpose. Bars are
 * chronologically ascending on input (getChartData's own contract), so the
 * last bar's date is the latest by construction; still walks to build the
 * filtered array defensively rather than assuming a contiguous tail. */
export function filterToLatestSessionDate(bars: ChartBar[]): { date: string | null; bars: ChartBar[] } {
  if (bars.length === 0) return { date: null, bars: [] };
  const date = chartTimeToEtDateStr(bars[bars.length - 1].time);
  return { date, bars: bars.filter((b) => chartTimeToEtDateStr(b.time) === date) };
}

/** True UTC instant (ISO, e.g. a trade's atIso) -> the SAME
 * ET-wall-clock-digits-as-UTCTimestamp encoding ChartBar.time uses, so the
 * two become directly comparable. Never a plain Date.parse()/1000 -- that
 * would compare a REAL UTC instant against ET digits stored as fake UTC,
 * silently off by the ET UTC offset (4-5h) and landing trades off the
 * visible session entirely. Never throws -- returns null on an unparsable
 * input (fail open, matches every other timestamp helper in this tree). */
export function atIsoToChartTime(atIso: string): number | null {
  const ms = Date.parse(atIso);
  if (!Number.isFinite(ms)) return null;
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York", hour12: false,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  }).formatToParts(new Date(ms));
  const get = (type: string): number => Number(parts.find((p) => p.type === type)?.value ?? 0);
  const hour = get("hour") % 24; // Intl can emit "24" for midnight in some locales
  return Math.floor(Date.UTC(get("year"), get("month") - 1, get("day"), hour, get("minute"), get("second")) / 1000);
}

/** Nearest bar index by |time delta|, or null when `bars` is empty. Bars are
 * 5-minute-spaced, so a trade a few seconds off its bar's own timestamp
 * still resolves to the right one; this is a plain linear scan (session bar
 * counts top out around 78 -- irrelevant cost either way, never called in a
 * hot loop). */
export function nearestBarIndex(bars: ChartBar[], chartTime: number): number | null {
  if (bars.length === 0) return null;
  let best = 0;
  let bestDelta = Math.abs(bars[0].time - chartTime);
  for (let i = 1; i < bars.length; i++) {
    const delta = Math.abs(bars[i].time - chartTime);
    if (delta < bestDelta) {
      best = i;
      bestDelta = delta;
    }
  }
  return best;
}

/** Same-minute + same side/direction/price rows collapse into ONE marker --
 * today's real trades.csv has the identical BULLISH_RECLAIM_RIDE_THE_RIBBON
 * 763C fill logged once per fleet arm (safe-3, risky-1, risky-3), 1-4
 * seconds apart; without this, the chart would show 3-4 stacked/overlapping
 * pins for what a viewer should read as one setup event. `count` preserves
 * how many rows actually deduped, so nothing is hidden, only merged for
 * legibility. Order-preserving (first occurrence per bucket wins position),
 * matches the input's own chronological order. */
export function dedupeTradeMarkers(trades: ChartTradeMarker[]): Array<ChartTradeMarker & { count: number }> {
  const buckets = new Map<string, { marker: ChartTradeMarker; count: number }>();
  const order: string[] = [];
  for (const t of trades) {
    const ms = Date.parse(t.atIso);
    const minuteBucket = Number.isFinite(ms) ? Math.floor(ms / 60_000) : t.atIso;
    // MARKER-COLLIDE fix (2026-09-15): `account` joined the bucket key so
    // two DIFFERENT accounts filling the same setup/price/minute (a real
    // shape today: safe-2 and bold-2 both traded BEARISH_REJECTION_RIDE_THE
    // _RIBBON in the same 5-minute bar) are never merged into one marker --
    // merging them would erase exactly the per-account distinction
    // HoloChart.tsx's own TradeMarkers now needs to label/stack each one
    // separately. A missing/null account still dedupes against other
    // missing/null-account rows exactly as before (pre-account-column
    // journal rows), so this is additive, not a behavior change for that
    // case -- see the "keeps distinct accounts separate" test below.
    const key = `${t.side}:${t.direction}:${t.price}:${minuteBucket}:${t.account ?? ""}`;
    const existing = buckets.get(key);
    if (existing) {
      existing.count += 1;
    } else {
      buckets.set(key, { marker: t, count: 1 });
      order.push(key);
    }
  }
  return order.map((key) => {
    const entry = buckets.get(key)!;
    return { ...entry.marker, count: entry.count };
  });
}

// --- session status/label (HOLOCHART-TRUTH, 2026-09-15) --------------------
//
// ROOT CAUSE this fixes (dashboard/lib/hq-chart-data.ts:200, pre-fix): session
// status was `date === todayET() && isMarketHoursET(now) ? "open" : "closed"`
// where `date` is filterToLatestSessionDate's own output -- the latest ET
// date PRESENT IN backtest/data/spy_5m_*.csv. That file is written ONCE per
// day, AFTER close (confirmed this session: newest file
// spy_5m_2026-05-19_2026-09-14.csv, mtime 2026-09-14 14:16 MT / last row
// "2026-09-14 15:55:00-04:00", zero 2026-09-15 rows, while `python
// setup/scripts/et_clock.py` read "2026-09-15 10:35:50 EDT market_hours=True"
// the same session) -- so during TODAY's live RTH, before that once-daily
// writer runs again, `date` is still YESTERDAY, the equality fails, and
// status falls through to "closed" even though the market is open. The
// sight-beacon (automation/state/sight-beacon.json, refreshed ~1min) already
// has today's real tick the whole time -- this module's job is to use it.

/** ISO "YYYY-MM-DD" -> true if that calendar date is a Mon-Fri (weekday) in
 * the SAME calendar the string already encodes -- pure, no Date/timezone
 * involved beyond `Date.UTC`'s own deterministic weekday math on already-ET
 * digits (same "digits as UTC" convention etDigitsToChartTime/
 * chartTimeToEtDateStr use elsewhere in this file). Never throws; malformed
 * input reads as non-weekday (fail closed -- never claim RTH on garbage). */
export function isWeekdayEt(dateStr: string): boolean {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr);
  if (!m) return false;
  const [, y, mo, d] = m.map(Number);
  const day = new Date(Date.UTC(y, mo - 1, d)).getUTCDay(); // 0=Sun..6=Sat
  return day >= 1 && day <= 5;
}

export interface SessionStatusLabel {
  status: "open" | "closed" | "no-data";
  label: string;
}

/**
 * Pure decision table for the session caption -- decouples the BARS file's
 * own (once-daily) freshness from the LIVE tick's (once-a-minute) freshness,
 * which the pre-fix code conflated by gating status on bars-date equality
 * alone.
 *
 * - `barsDate`: filterToLatestSessionDate's own output (the ET date of the
 *   newest bar actually on hand) -- null means the local CSV had zero bars.
 * - `today`: todayET(now).
 * - `isRth`: true only Mon-Fri AND within the 09:30-16:00 ET window (the
 *   caller is responsible for combining isMarketHoursET(now) with
 *   isWeekdayEt(today) -- see hq-chart-data.ts's own call site).
 * - `liveFresh`: true only when the sight-beacon's own tick is dated `today`
 *   (in ET) AND under STALE_AFTER_S=180 seconds old -- computed by the
 *   caller from `chart.live`, entirely independent of `barsDate`.
 *
 * Four honest outcomes, never a 5th silently-wrong one:
 *   1. no bars at all                              -> "no-data"
 *   2. bars ARE today's AND it's RTH                -> "open", "... live"
 *   3. bars are STALE but it's RTH AND live is fresh -> "open", explicit
 *      "no intraday bars" caption (this is the fix's core case -- never
 *      silently present yesterday's bars as if they were today's)
 *   4. everything else (after hours, weekend, or RTH with no fresh live
 *      tick either) -> "closed", labeled with the bars' own real date
 */
export function computeSessionStatusLabel(
  barsDate: string | null,
  today: string,
  isRth: boolean,
  liveFresh: boolean,
): SessionStatusLabel {
  if (barsDate === null) {
    return liveFresh
      ? { status: "open", label: "SPY · live (no intraday bars)" }
      : { status: "no-data", label: "SPY · no local session data" };
  }
  const barsAreToday = barsDate === today;
  if (barsAreToday && isRth) {
    return { status: "open", label: `SPY · ${barsDate} session · live` };
  }
  if (!barsAreToday && isRth && liveFresh) {
    return { status: "open", label: "SPY · live (no intraday bars)" };
  }
  return { status: "closed", label: `SPY · ${barsDate} session · closed` };
}

/** Only levels within `band` dollars of [low, high] survive -- a level ten
 * dollars outside today's actual traded range would otherwise force the
 * ribbon's own vertical scale to stretch to accommodate a plane nobody will
 * ever see price approach today, or render as an absurdly distant floating
 * line. `band` defaults to the larger of $2 or 60% of the day's own range,
 * so a quiet low-range day still shows its nearest levels while a wide day
 * doesn't drag in ones genuinely far away. Every excluded level is still
 * present in automation/state/key-levels.json and this module's own
 * `readKeyLevels()` output -- this filter is a DISPLAY decision, not a data
 * loss. */
export function filterLevelsNearRange(levels: HoloLevel[], low: number, high: number, band?: number): HoloLevel[] {
  const pad = band ?? Math.max(2, (high - low) * 0.6);
  return levels.filter((l) => l.price >= low - pad && l.price <= high + pad);
}

// --- today's intraday 5m candle builder (HOLOCHART-INTRADAY, 2026-09-15) ---
//
// ROOT CAUSE this fixes: HoloChart plots backtest/data/spy_5m_*.csv, which
// (per findNewestBarsFile's own comment in lib/chart-data.ts) is written
// ONCE per day, after the close -- so during live RTH it is always showing
// YESTERDAY's candles, even though commit cc8261bd made the session LABEL
// honest about it ("SPY · live (no intraday bars)"). Survey this session
// found no persisted intraday-bars cache anywhere on disk (heartbeat_core.py
// fetches Alpaca 5Min bars fresh over REST every tick but never writes them
// out; automation/state/sight-beacon.json holds only the latest single
// tick, overwritten in place, zero history). The one on-disk source with
// real per-minute history for today is automation/state/core-decisions.jsonl
// -- one row per account per engine tick (~1/min/account during RTH), each
// carrying `spy` (the engine's current SPY read at that tick) and `ts_et`
// (bare ET digits, e.g. "2026-09-15T10:52:03", NO zone suffix -- same
// convention BARE_TS_RE below and chart-data.ts's own parseWallClockDigits
// already assume elsewhere in this codebase). Two accounts ("safe"/"bold")
// share the SAME engine tick (same core_tick_id, same `spy` value) roughly
// once a minute -- the caller (hq-chart-data.ts) dedupes by core_tick_id
// before calling buildIntradayCandles, but this function also defensively
// collapses back-to-back identical (tsEt, price) pairs so a caller that
// forgets to dedupe still gets a sane result rather than a doubled-up bar.
//
// This is TICK data (one point per minute-ish), not true 5m OHLCV bars --
// each candle's open/high/low/close are honestly the open/high/low/close of
// the *engine-tick samples that landed in that 5-minute window*, not of
// every second of real intra-bar price action. That is the correct honest
// reading of what this source actually is (never fabricated finer-grained
// movement); a bucket with only one tick in it necessarily has
// open===high===low===close.

/** One engine-tick sample: a bare ET timestamp + the SPY read at that tick.
 * `tsEt` uses the exact bare-digits convention core-decisions.jsonl's own
 * ts_et field already writes (no zone suffix -- the digits ARE ET). */
export interface IntradayTick {
  tsEt: string;
  price: number;
}

// --- stale-carryover tick filtering (HOLOCHART-INTRADAY-2, 2026-09-15) ----
//
// ROOT CAUSE this fixes: the FIRST few engine ticks of a session (typically
// 09:30-09:35 ET) can be logged BEFORE the engine has a genuinely fresh
// closed 5m bar to decide on -- heartbeat_core.py marks these rows
// `action: "SKIP_STALE_TRIGGER"` (setup/scripts/heartbeat_core.py:1858) or
// `action: "SKIP_STALE_SIGHT"` (:1934), and in both cases the `spy` field on
// that row is the PRIOR session's carried-over last close, not a real
// today's-session read. Verified live this session: 2026-09-15's real
// core-decisions rows from 09:30:04-09:35:04 all carry
// action=SKIP_STALE_TRIGGER and spy=761.27/760.755 (2026-09-14's own close
// range), while the sight-beacon's real ticks at the same wall-clock minutes
// read 759.89 (09:31) / 758.86 (09:34) -- genuinely different, lower prices.
// Un-filtered, these rows fabricated a fake 09:30 candle at yesterday's
// price level. The first GENUINE row that session was 09:36:02
// (action=HOLD, spy=758.925).

/** Engine action codes whose `spy` field is known to be a carried-over
 * PRIOR-session bar close, never today's real price -- see this section's
 * own header. */
const STALE_CARRYOVER_ACTIONS = new Set(["SKIP_STALE_TRIGGER", "SKIP_STALE_SIGHT"]);

/** True when a tick should be EXCLUDED from the intraday candle series
 * because it is a stale prior-session carryover, not a real today's price.
 *
 * Prefers the explicit engine `action` code whenever present -- this is the
 * authoritative signal heartbeat_core.py itself writes for exactly this
 * condition. Only when `action` is missing/empty (an older row shape that
 * predates the action field, or a row this reader couldn't classify) does
 * this fall back to a heuristic: a tick timestamped before 09:36 ET whose
 * price is EXACTLY `priorSessionClose` (the prior session's own last closed
 * bar) is almost certainly the same carried-over stale read under a shape
 * this function can't otherwise recognize. `priorSessionClose === null`
 * disables the fallback entirely -- this function never guesses without a
 * real prior close to compare against (fail-open toward KEEPING the tick,
 * never toward silently dropping real data). */
export function isStaleCarryoverTick(
  tick: { tsEt: string; price: number; action?: string | null },
  priorSessionClose: number | null,
): boolean {
  if (typeof tick.action === "string" && tick.action.length > 0) {
    return STALE_CARRYOVER_ACTIONS.has(tick.action);
  }
  if (priorSessionClose === null) return false;
  const w = parseBareEtDigits(tick.tsEt);
  if (!w) return false;
  return minutesOfDay(w) < 9 * 60 + 36 && tick.price === priorSessionClose;
}

interface BareEtDigits {
  y: number;
  mo: number;
  d: number;
  hh: number;
  mm: number;
  ss: number;
}

// Deliberately the SAME shape/behavior as chart-data.ts's own (unexported)
// parseWallClockDigits -- duplicated rather than imported because this
// module is intentionally import-free of chart-data.ts's VALUE exports (see
// this file's own header: a value import would pull in chart-data.ts's
// extensionless "./workspace" chain, breaking `node --test`).
const BARE_ET_TS_RE = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2}):(\d{2})/;

/** Parses a "YYYY-MM-DD[T ]HH:MM:SS" prefix as literal ET wall-clock digits
 * -- NEVER routes through `new Date(str)` (which would parse against this
 * process's OWN local timezone -- Mountain on this box per CLAUDE.md's
 * "Bash TZ broken" lesson -- silently skewing every bucket by 1-2h). Pure
 * string/regex digit extraction is what makes this DST-safe: there is no
 * timezone conversion step for a DST boundary to corrupt. Never throws;
 * returns null on anything that doesn't match (fail-open, matches every
 * other timestamp helper in this file). */
function parseBareEtDigits(raw: string): BareEtDigits | null {
  const m = BARE_ET_TS_RE.exec(raw.trim());
  if (!m) return null;
  const [, y, mo, d, hh, mm, ss] = m.map(Number);
  return { y, mo, d, hh, mm, ss };
}

/** Same encoding chart-data.ts's own etDigitsToChartTime uses: the literal
 * ET wall-clock digits, stored AS a UTCTimestamp (a *display* timestamp,
 * directly comparable against every other ChartBar.time in this codebase --
 * never a real UTC instant). */
function bareEtDigitsToChartTime(w: BareEtDigits): number {
  return Math.floor(Date.UTC(w.y, w.mo - 1, w.d, w.hh, w.mm, w.ss) / 1000);
}

function minutesOfDay(w: BareEtDigits): number {
  return w.hh * 60 + w.mm;
}

const RTH_OPEN_MIN = 9 * 60 + 30; // 09:30 ET
const RTH_CLOSE_MIN = 16 * 60; // 16:00 ET (exclusive)
const BUCKET_MIN = 5;

export interface IntradayCandleResult {
  bars: ChartBar[];
  /** True when `bars[bars.length - 1]` is still an OPEN (accumulating) 5m
   * window as of `nowMinutesOfDay` -- i.e. fewer than 5 minutes have
   * elapsed since that bucket's start. Callers should render this bar
   * distinctly (e.g. a lighter/hollow candle) rather than as a closed bar.
   * False when there are no bars at all. */
  lastBarPartial: boolean;
}

/**
 * Buckets a chronologically-ordered (or unordered -- this function sorts
 * defensively) series of per-tick SPY samples into today's 09:30-16:00 ET
 * 5-minute candles. Only emits a bar for a bucket that actually has >=1
 * tick in it -- a quiet stretch with no engine ticks produces a GAP in the
 * output array, never a fabricated flat candle carried forward from the
 * prior bucket's close (this codebase's standing "never fabricate" rule).
 *
 * `nowMinutesOfDay` is the caller's current ET minutes-of-day (09:30 ET =
 * 570), used ONLY to decide `lastBarPartial` -- never to filter which
 * ticks/buckets are included.
 */
export function buildIntradayCandles(ticks: IntradayTick[], nowMinutesOfDay: number): IntradayCandleResult {
  interface Parsed {
    chartTime: number;
    bucketStartMin: number;
    /** This tick's own ET calendar date (y/mo/d only), used to derive its
     * bucket's ChartBar.time directly -- never back-computed from chartTime
     * via modulo (which would need explicit negative-remainder handling to
     * be correct, and duplicates work this already-parsed data has). */
    y: number;
    mo: number;
    d: number;
    price: number;
  }
  const parsed: Parsed[] = [];
  for (const t of ticks) {
    if (!Number.isFinite(t.price)) continue;
    const w = parseBareEtDigits(t.tsEt);
    if (!w) continue;
    const min = minutesOfDay(w);
    if (min < RTH_OPEN_MIN || min >= RTH_CLOSE_MIN) continue; // outside the RTH session -- never plotted
    const bucketStartMin = min - (min % BUCKET_MIN);
    parsed.push({ chartTime: bareEtDigitsToChartTime(w), bucketStartMin, y: w.y, mo: w.mo, d: w.d, price: t.price });
  }
  // Sort ascending by real chart time -- core-decisions.jsonl rows arrive in
  // append order (already ascending) but this defends against a caller
  // handing an unsorted or multi-account-interleaved slice.
  parsed.sort((a, b) => a.chartTime - b.chartTime);

  // Defensive dedupe of exact back-to-back (time, price) duplicates -- the
  // caller is expected to already dedupe by core_tick_id, but a caller that
  // doesn't should still get a correct result, not a doubled first/last tick.
  const deduped: Parsed[] = [];
  for (const p of parsed) {
    const prev = deduped[deduped.length - 1];
    if (prev && prev.chartTime === p.chartTime && prev.price === p.price) continue;
    deduped.push(p);
  }

  interface Bucket {
    startMin: number;
    open: number;
    high: number;
    low: number;
    close: number;
  }
  const buckets = new Map<number, Bucket>();
  const order: number[] = [];
  for (const p of deduped) {
    let b = buckets.get(p.bucketStartMin);
    if (!b) {
      b = { startMin: p.bucketStartMin, open: p.price, high: p.price, low: p.price, close: p.price };
      buckets.set(p.bucketStartMin, b);
      order.push(p.bucketStartMin);
    } else {
      if (p.price > b.high) b.high = p.price;
      if (p.price < b.low) b.low = p.price;
      b.close = p.price; // deduped array is time-ascending, so last write wins honestly
    }
  }
  // order[] was built in first-seen order, which (since `deduped` is
  // time-ascending) is already ascending by startMin -- no extra sort needed.

  // A bucket's own ChartBar.time is derived from its startMin against
  // TODAY's own calendar date -- taken from the first tick that landed in
  // it (all ticks in one session share the same ET calendar date by
  // construction, since RTH never crosses midnight ET).
  const bars: ChartBar[] = order.map((startMin) => {
    const b = buckets.get(startMin)!;
    // Any tick that fell in this bucket carries the right ET calendar date
    // (bucket counts top out around 78/day, so this small scan is
    // irrelevant cost) -- the bucket's own display time is that date at
    // startMin, encoded via the SAME digits-as-UTCTimestamp convention
    // bareEtDigitsToChartTime uses everywhere else in this file.
    const anyTick = deduped.find((p) => p.bucketStartMin === startMin)!;
    const bucketTime = Math.floor(
      Date.UTC(anyTick.y, anyTick.mo - 1, anyTick.d, Math.floor(startMin / 60), startMin % 60, 0) / 1000,
    );
    return { time: bucketTime, open: b.open, high: b.high, low: b.low, close: b.close };
  });

  const lastBarPartial = order.length > 0 && nowMinutesOfDay < order[order.length - 1] + BUCKET_MIN;
  return { bars, lastBarPartial };
}

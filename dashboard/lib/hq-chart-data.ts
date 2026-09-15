// WORLD-6 (2026-09-14, W1 -- "the signature piece"): data layer for the
// holographic SPY chart floating above the hub's round table (HoloChart.tsx).
// REAL data only, three local, already-produced sources -- zero new
// producers, zero network requests, zero fabrication:
//
//   1. backtest/data/spy_5m_*.csv (via lib/chart-data.ts#getChartData, the
//      SAME reader that already powers /api/gamma-chart -- reused verbatim,
//      not re-implemented, per this project's own Research & Reuse rule).
//      This is the FINEST bar resolution that exists locally: no
//      backtest/data/spy_1m_*.csv file exists in this repo (checked this
//      session -- `ls backtest/data/spy_1m_*.csv` -> no match), so 5-minute
//      is the honest answer to "1-min or finest available".
//   2. automation/state/key-levels.json -- the engine's real key levels
//      (MAP.md#SEE: "the level set every entry decision is tied to"),
//      refreshed every 5m RTH by refresh_levels_intraday.py.
//   3. journal/trades.csv (via the SAME getChartData() call, which already
//      reads it) -- today's REAL fills only, never a decision-log attempt
//      that got skipped. Doctrine C1 (LESSONS-LEARNED.md): "real-fills is
//      the only WR authority" -- this is why trades.csv wins over grepping
//      automation/state/core-decisions.jsonl for a verdict-only ENTER/EXIT
//      row: the CORE account (safe/bold) skipped its own 14:00 ET
//      BULLISH_RECLAIM_RIDE_THE_RIBBON attempt on SKIP_MIN_PREMIUM_FLOOR
//      today (verified this session by reading the live file), but three
//      FLEET arms (safe-3, risky-1, risky-3) actually filled the same setup
//      one minute later -- trades.csv has that real fill, core-decisions.jsonl
//      alone would show only the skip.
//
// Every reader below is independently fail-open (mirrors lib/hq.ts's own
// per-source contract) -- one missing/garbled file degrades only its own
// piece of the response, never throws, and getHoloChartData() itself can
// never throw: a caller that gets `ok:false` has a genuine `error` string,
// never a fabricated empty-looking success.
//
// The PURE half of this module (no fs, unit-tested directly) lives in
// ./hq-chart-pure -- see that file's own header for why it's a separate
// module (Node's native `node --test` runner needs it importable without
// pulling in lib/chart-data.ts's own extensionless "./workspace" chain).

import { promises as fs } from "node:fs";
import type { FileHandle } from "node:fs/promises";
import { paths } from "./workspace";
import { todayET, isMarketHoursET, formatET } from "./time";
import { getChartData, type ChartBar, type ChartTradeMarker } from "./chart-data";
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
} from "./hq-chart-pure";

// Same threshold setup/scripts/sight_beacon.py itself documents
// (STALE_AFTER_S = 180) -- a beacon tick older than this is untrustworthy
// for every consumer, this one included.
const STALE_AFTER_S = 180;

// ─── wire types (shared with the client component via `import type`, which
//     is erased at compile time -- no fs-touching code ever reaches the
//     browser bundle; same convention this tree already uses for
//     HubInteriorProps' `import type { SectorsSnapshot, TradingStatus }
//     from "@/lib/hq"`). ───────────────────────────────────────────────────

export type { HoloLevel };

export interface HoloTradeMarker {
  /** True UTC instant (ISO) -- see atIsoToChartTime's own header for why
   * this must NOT be compared directly against ChartBar.time. */
  atIso: string;
  /** Same encoding as ChartBar.time (ET wall-clock digits stored AS a
   * UTCTimestamp) -- directly comparable/plottable against `bars[].time`. */
  chartTime: number;
  /** Nearest bar's index into the `bars` array this response also carries,
   * or null if there are no bars to anchor against. Computed here (not by
   * the client) since it already has both arrays in hand in one pass. */
  barIndex: number | null;
  side: "entry" | "exit";
  direction: "call" | "put";
  /** The real option premium (entry_px/exit_px) -- NOT a SPY price. Label
   * only, never a Y-axis value on the SPY ribbon (chart-data.ts's own
   * ChartTradeMarker carries the identical warning). */
  price: number;
  setup: string;
  note: string | null;
  pnl: number | null;
  /** How many individual journal rows deduped into this one marker (e.g.
   * the same trigger filling across safe-3/risky-1/risky-3 within the same
   * minute) -- see dedupeTradeMarkers' own header. Never fewer than 1. */
  count: number;
}

export interface HoloChartData {
  ok: boolean;
  /** Present only when `ok` is false, or when a non-fatal source degraded
   * (e.g. key-levels.json missing) -- failure honesty per this codebase's
   * own standing rule: a partial/degraded read says so, never silently. */
  error?: string;
  session: {
    /** YYYY-MM-DD (ET) of the bars actually shown, or null if the local CSV
     * has no bars at all. */
    date: string | null;
    status: "open" | "closed" | "no-data";
    /** "SPY · 2026-09-14 session · closed" -- ready to render verbatim. */
    label: string;
  };
  /** The session's own bars only (never the 1-2-day window
   * lib/chart-data.ts#getChartData keeps for its own DOM-chart purpose) --
   * see filterToLatestSessionDate. */
  bars: ChartBar[];
  priceRange: { low: number; high: number } | null;
  /** Only levels within a band of the session's own traded range -- see
   * filterLevelsNearRange's own header for why a level ten dollars outside
   * today's range is omitted rather than drawn absurdly far off the ribbon. */
  levels: HoloLevel[];
  lastClose: { price: number; chartTime: number; barIndex: number } | null;
  /** Live sight-beacon point, only when fresh enough to honestly call it
   * "live" (same STALE_AFTER_S=180 convention setup/scripts/sight_beacon.py
   * itself documents) -- null otherwise, never a stale number relabeled. */
  live: { price: number; ageSeconds: number } | null;
  trades: HoloTradeMarker[];
  generatedAt: string;
}

// ─── automation/state/key-levels.json ───────────────────────────────────────

interface RawKeyLevel {
  price?: unknown;
  type?: unknown;
  tier?: unknown;
  source?: unknown;
}

const SOURCE_TAG: Record<string, string> = {
  daily_context_shelf: "SHELF",
  premarket_low: "PML",
  premarket_high: "PMH",
  intraday_rth_low: "RTH LOW",
  intraday_rth_high: "RTH HIGH",
  intraday_swing_low: "SWING LOW",
  intraday_swing_high: "SWING HIGH",
};

function tagFor(type: string, source: string): string {
  return SOURCE_TAG[source] ?? (type === "resistance" ? "RESISTANCE" : "SUPPORT");
}

/** Reads automation/state/key-levels.json -- the engine's real level set
 * (MAP.md#SEE). Only `tier === "Active"` levels count (a pruned/expired tier
 * is not a level the engine is currently tied to). Fail-open: a missing or
 * malformed file degrades to []. */
async function readKeyLevels(): Promise<HoloLevel[]> {
  try {
    const text = await fs.readFile(paths.keyLevels, "utf-8");
    const data = JSON.parse(text) as { levels?: unknown };
    if (!Array.isArray(data.levels)) return [];
    const out: HoloLevel[] = [];
    for (const raw of data.levels as RawKeyLevel[]) {
      if (!raw || typeof raw !== "object") continue;
      const price = typeof raw.price === "number" && Number.isFinite(raw.price) ? raw.price : null;
      const type = raw.type === "support" || raw.type === "resistance" ? raw.type : null;
      const tier = typeof raw.tier === "string" ? raw.tier : "";
      const source = typeof raw.source === "string" ? raw.source : "";
      if (price === null || type === null || tier !== "Active") continue;
      out.push({ price, type, tag: tagFor(type, source), source });
    }
    return out;
  } catch {
    return [];
  }
}

// ─── automation/state/core-decisions.jsonl (today's engine ticks) ─────────
//
// See hq-chart-pure.ts's own "today's intraday 5m candle builder" header for
// the full root-cause + source-choice reasoning (survey done this session:
// no persisted intraday-bars cache exists anywhere on disk; core-decisions
// is the one file with real per-minute history for today). This reader is
// intentionally separate from lib/hq.ts's own readCoreDecisionsToday() --
// that function's `trades` array holds ONLY genuine ENTER/EXIT rows (see its
// own comment), which is exactly the wrong subset here: we need every tick's
// `spy` read (mostly HOLD rows) to reconstruct a price series, not just the
// rare trade rows. Same bounded-tail-read convention as that function (never
// a full fs.readFile of this large, continuously-growing file).
const CORE_DECISIONS_TICKS_TAIL_BYTES = 4 * 1024 * 1024; // 4 MiB -- same size hq.ts's readCoreDecisionsToday uses

/** Reads automation/state/core-decisions.jsonl, keeps only today's (ET
 * calendar date) rows, and collapses the two accounts' rows down to ONE tick
 * per engine core_tick_id (both accounts share the same `spy` read for a
 * shared tick -- see hq-chart-pure.ts's own header). Fail-open: a
 * missing/unreadable file or a malformed line degrades to [], never throws. */
async function readTodayEngineTicks(): Promise<IntradayTick[]> {
  let handle: FileHandle | undefined;
  try {
    handle = await fs.open(paths.coreDecisions, "r");
    const stat = await handle.stat();
    const start = Math.max(0, stat.size - CORE_DECISIONS_TICKS_TAIL_BYTES);
    const length = stat.size - start;
    if (length <= 0) return [];
    const buffer = Buffer.alloc(length);
    await handle.read(buffer, 0, length, start);
    const text = buffer.toString("utf-8");
    // Same "drop the first line if we seeked mid-file" rule as hq.ts's own
    // core-decisions readers -- a seeked chunk's first line is very likely a
    // truncated partial row.
    const lines = text.split("\n").slice(start > 0 ? 1 : 0).filter((l) => l.trim().length > 0);
    const today = todayET(new Date());
    const seenTickIds = new Set<string>();
    const ticks: IntradayTick[] = [];
    for (const line of lines) {
      let row: Record<string, unknown>;
      try {
        row = JSON.parse(line);
      } catch {
        continue; // one malformed/truncated line never blocks the rest
      }
      const tsEt = typeof row.ts_et === "string" ? row.ts_et : "";
      if (!tsEt.startsWith(today)) continue; // only today's rows
      const price = typeof row.spy === "number" && Number.isFinite(row.spy) ? row.spy : null;
      if (price === null) continue;
      // Dedupe by core_tick_id (shared across accounts for the same engine
      // tick) when present; falls back to the (tsEt, price) pair itself so a
      // row missing core_tick_id still contributes rather than being
      // silently dropped.
      const tickId = typeof row.core_tick_id === "string" ? row.core_tick_id : `${tsEt}:${price}`;
      if (seenTickIds.has(tickId)) continue;
      seenTickIds.add(tickId);
      ticks.push({ tsEt, price });
    }
    return ticks;
  } catch {
    return [];
  } finally {
    await handle?.close();
  }
}

// ─── assembly ────────────────────────────────────────────────────────────

/** Everything HoloChart.tsx needs, assembled server-side. Never throws --
 * any unexpected failure degrades to `{ok:false, error, session:{status:
 * "no-data"}, bars:[], ...}` (an honest empty series), matching this task's
 * own explicit contract ("fail-open to an empty series with an `error`
 * field, never throws"). */
export async function getHoloChartData(): Promise<HoloChartData> {
  const emptySession: HoloChartData["session"] = { date: null, status: "no-data", label: "SPY · no local session data" };
  try {
    const [chart, levelsAll] = await Promise.all([getChartData(), readKeyLevels()]);
    const { date: csvDate, bars: csvBars } = filterToLatestSessionDate(chart.bars);

    const now = new Date();
    const today = todayET(now);
    // RTH gate -- weekday AND within the 09:30-16:00 ET window. Deliberately
    // NOT the shared isMarketHoursET(now) alone (that helper carries no
    // day-of-week check of its own -- see lib/time.ts) so a Saturday box
    // clock reading a Mon-Fri-shaped time-of-day never gets read as "open"
    // here.
    const isRth = isMarketHoursET(now) && isWeekdayEt(today);
    // The live sight-beacon tick's own freshness, entirely decoupled from
    // `date` (the BARS file's date) -- see computeSessionStatusLabel's own
    // header for why conflating the two was the root cause of the stale
    // "yesterday session · closed" label during live RTH.
    const liveChartTime = chart.live ? atIsoToChartTime(chart.live.atIso) : null;
    const liveEtDate = liveChartTime !== null ? chartTimeToEtDateStr(liveChartTime) : null;
    const liveFresh = chart.live !== null && chart.live.ageSeconds < STALE_AFTER_S && liveEtDate === today;
    const live = liveFresh ? { price: chart.live!.price, ageSeconds: chart.live!.ageSeconds } : null;

    // ── today's REAL intraday candles (HOLOCHART-INTRADAY, 2026-09-15) ──
    // Only attempted during RTH -- outside RTH the CSV (written once, after
    // close) already has today's full session by the time anyone's asking,
    // and pre/post-market engine ticks outside 09:30-16:00 ET are excluded
    // by buildIntradayCandles anyway. See hq-chart-pure.ts's own header for
    // the full source-choice reasoning.
    let intradayBars: ChartBar[] = [];
    let intradayPartialLast = false;
    if (isRth) {
      const ticks = await readTodayEngineTicks();
      if (ticks.length > 0) {
        const [hh, mm] = formatET(now).split(":").map(Number);
        const nowMinutesOfDay = hh * 60 + mm;
        const built = buildIntradayCandles(ticks, nowMinutesOfDay);
        intradayBars = built.bars;
        intradayPartialLast = built.lastBarPartial;
      }
    }
    const usingIntraday = intradayBars.length > 0;
    const date = usingIntraday ? today : csvDate;
    const bars = usingIntraday ? intradayBars : csvBars;

    if (bars.length === 0) {
      const { status, label } = computeSessionStatusLabel(null, today, isRth, liveFresh);
      return {
        ok: true,
        error: "no local SPY bars found (backtest/data/spy_5m_*.csv missing or empty, and no today's engine ticks in core-decisions.jsonl)",
        session: { date: null, status, label },
        bars: [],
        priceRange: null,
        levels: [],
        lastClose: null,
        live,
        trades: [],
        generatedAt: new Date().toISOString(),
      };
    }

    // A genuine today's-intraday series overrides the honest-but-stale
    // "SPY · live (no intraday bars)" caption computeSessionStatusLabel
    // would otherwise compute from the (stale) CSV date -- this label is
    // truthful precisely because `bars` really are today's, built moments
    // ago from the engine's own ticks, never fabricated.
    const { status, label } = usingIntraday
      ? { status: "open" as const, label: `SPY · today · live${intradayPartialLast ? " (forming)" : ""}` }
      : computeSessionStatusLabel(date, today, isRth, liveFresh);
    const session = { date, status, label };

    let low = Infinity;
    let high = -Infinity;
    for (const b of bars) {
      if (b.low < low) low = b.low;
      if (b.high > high) high = b.high;
    }
    const priceRange = { low, high };
    const levels = filterLevelsNearRange(levelsAll, low, high);

    const lastBar = bars[bars.length - 1];
    const lastClose = { price: lastBar.close, chartTime: lastBar.time, barIndex: bars.length - 1 };

    // `live` was already computed above (decoupled from `session.date` --
    // see its own comment) so it stays valid even when the bars file is
    // stale to yesterday but the sight-beacon tick is genuinely today's.

    const deduped = dedupeTradeMarkers(chart.trades);
    const trades: HoloTradeMarker[] = deduped
      .map((t) => {
        const chartTime = atIsoToChartTime(t.atIso);
        if (chartTime === null) return null;
        // Trades outside today's own session bars (a stale trades.csv row,
        // or a bar file that hasn't caught up yet) are dropped rather than
        // plotted off the visible ribbon -- filterToLatestSessionDate above
        // is the single source of truth for "today's" bar window.
        if (chartTimeToEtDateStr(chartTime) !== date) return null;
        return {
          atIso: t.atIso,
          chartTime,
          barIndex: nearestBarIndex(bars, chartTime),
          side: t.side,
          direction: t.direction,
          price: t.price,
          setup: t.setup,
          note: t.note,
          pnl: t.pnl,
          count: t.count,
        };
      })
      .filter((t): t is HoloTradeMarker => t !== null);

    return {
      ok: true,
      session,
      bars,
      priceRange,
      levels,
      lastClose,
      live,
      trades,
      generatedAt: new Date().toISOString(),
    };
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return {
      ok: false,
      error: `getHoloChartData failed: ${message}`,
      session: emptySession,
      bars: [],
      priceRange: null,
      levels: [],
      lastClose: null,
      live: null,
      trades: [],
      generatedAt: new Date().toISOString(),
    };
  }
}

// Re-exported so a consumer only needs one import line for the wire type +
// the reader.
export type { ChartBar };

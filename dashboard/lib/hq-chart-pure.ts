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
    const key = `${t.side}:${t.direction}:${t.price}:${minuteBucket}`;
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

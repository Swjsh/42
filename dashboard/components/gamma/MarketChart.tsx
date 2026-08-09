"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import {
  createChart,
  createSeriesMarkers,
  CandlestickSeries,
  LineSeries,
  ColorType,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
  type UTCTimestamp,
  type CandlestickData,
  type MouseEventParams,
} from "lightweight-charts";
import { LineChart } from "lucide-react";
import type { ChartData, ChartTradeMarker } from "@/lib/chart-data";

const REFRESH_MS = 30_000;

async function fetcher(url: string): Promise<ChartData> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as ChartData;
}

interface Palette {
  border: string;
  borderMid: string;
  text3: string;
  up: string;
  down: string;
  cyan: string;
}

function readPalette(): Palette {
  const styles = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string): string => styles.getPropertyValue(name).trim() || fallback;
  return {
    border: v("--border", "rgba(255,255,255,0.08)"),
    borderMid: v("--border-mid", "rgba(255,255,255,0.12)"),
    text3: v("--text-3", "#8b97af"),
    up: v("--up", "#22c55e"),
    down: v("--down", "#ef4444"),
    cyan: v("--cyan", "#22d3ee"),
  };
}

/** Lightweight Charts always renders time in UTC -- it has no timezone
 * option (verified against its own type declarations). `atIso` is a true
 * UTC instant; this converts it to the ET wall-clock digits SPY actually
 * printed, floors to the enclosing 5-minute bar, then encodes those digits
 * AS a UTCTimestamp -- the same "display timestamp" trick lib/chart-data.ts
 * uses for the bars themselves, so a trade marker lands on the real candle
 * it happened during, regardless of the viewer's OS timezone. */
function barTimeForIso(atIso: string): UTCTimestamp {
  const d = new Date(atIso);
  const parts = new Intl.DateTimeFormat("en-US", {
    timeZone: "America/New_York",
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).formatToParts(d);
  const get = (type: string): number => Number(parts.find((p) => p.type === type)?.value ?? 0);
  const hour = get("hour") % 24;
  const flooredMinute = Math.floor(get("minute") / 5) * 5;
  return Math.floor(Date.UTC(get("year"), get("month") - 1, get("day"), hour, flooredMinute, 0) / 1000) as UTCTimestamp;
}

function fmtPnl(pnl: number): string {
  const sign = pnl > 0 ? "+" : pnl < 0 ? "-" : "";
  return `${sign}$${Math.abs(pnl).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
}

function fmtAge(ageSeconds: number): string {
  if (ageSeconds < 90) return `${ageSeconds}s ago`;
  return `${Math.round(ageSeconds / 60)}m ago`;
}

function tradeMarker(t: ChartTradeMarker, palette: Palette): SeriesMarker<Time> {
  const time = barTimeForIso(t.atIso);
  if (t.side === "entry") {
    return {
      time,
      position: t.direction === "call" ? "belowBar" : "aboveBar",
      color: palette.cyan,
      shape: t.direction === "call" ? "arrowUp" : "arrowDown",
      text: "IN",
    };
  }
  const won = t.pnl !== null && t.pnl > 0;
  const lost = t.pnl !== null && t.pnl < 0;
  return {
    time,
    position: won ? "aboveBar" : "belowBar",
    color: won ? palette.up : lost ? palette.down : palette.text3,
    shape: "circle",
    text: t.pnl !== null ? `OUT ${fmtPnl(t.pnl)}` : "OUT",
  };
}

interface CalloutState {
  trades: ChartTradeMarker[];
  x: number;
  y: number;
}

/**
 * THE MARKET CHART -- a real SPY 5m candlestick chart (lightweight-charts,
 * TradingView's own open-source library) with REAL trade markers layered on
 * top: as Gamma enters/exits a real position, the fill shows up on the
 * chart at its real bar, colored by real outcome, and a small pulsing dot
 * extends the last closed candle with the freshest known live price. Every
 * candle traces to backtest/data/spy_5m_*.csv, every marker to
 * journal/trades.csv, the live dot to automation/state/sight-beacon.json --
 * see lib/chart-data.ts. Nothing here is invented: a trade with no journaled
 * note shows only its setup name and P&L, never a fabricated explanation.
 *
 * Self-contained: fetches its own /api/gamma-chart on a 30s interval, fails
 * open to a clear "no chart data" placeholder, and needs no props to mount.
 */
export default function MarketChart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const liveSeriesRef = useRef<ISeriesApi<"Line"> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);
  const tradesByBarTimeRef = useRef<Map<number, ChartTradeMarker[]>>(new Map());
  const [callout, setCallout] = useState<CalloutState | null>(null);

  const { data, error, isLoading } = useSWR<ChartData>("/api/gamma-chart", fetcher, {
    refreshInterval: REFRESH_MS,
    keepPreviousData: true,
  });

  // Mount the chart once. Reads unchanging (page-load-time) values off the
  // real CSS custom properties in app/globals.css -- never hardcoded colors.
  useEffect(() => {
    if (!containerRef.current) return;
    const palette = readPalette();

    const chart = createChart(containerRef.current, {
      autoSize: true,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: palette.text3,
      },
      grid: {
        vertLines: { color: palette.border },
        horzLines: { color: palette.border },
      },
      crosshair: { mode: CrosshairMode.Normal },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: palette.borderMid },
      rightPriceScale: { borderColor: palette.borderMid },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: palette.up,
      downColor: palette.down,
      borderVisible: false,
      wickUpColor: palette.up,
      wickDownColor: palette.down,
    });

    const liveSeries = chart.addSeries(LineSeries, {
      lineVisible: false,
      pointMarkersVisible: true,
      pointMarkersRadius: 4,
      color: palette.cyan,
      lastValueVisible: true,
      priceLineVisible: false,
      crosshairMarkerVisible: false,
    });

    const markers = createSeriesMarkers<Time>(candleSeries, []);

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    liveSeriesRef.current = liveSeries;
    markersRef.current = markers;

    // Hover a bar that has a trade attached -> show the real journaled
    // callout ("Gamma's narration"). Subscribed once; reads the latest
    // trades out of a ref so it never closes over stale data.
    const handleCrosshairMove = (param: MouseEventParams<Time>): void => {
      if (!param.time || !param.point) {
        setCallout(null);
        return;
      }
      const bucket = tradesByBarTimeRef.current.get(param.time as number);
      if (!bucket || bucket.length === 0) {
        setCallout(null);
        return;
      }
      setCallout({ trades: bucket, x: param.point.x, y: param.point.y });
    };
    chart.subscribeCrosshairMove(handleCrosshairMove);

    return () => {
      chart.unsubscribeCrosshairMove(handleCrosshairMove);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      liveSeriesRef.current = null;
      markersRef.current = null;
    };
  }, []);

  // Push fresh data into the chart whenever a poll returns something new.
  useEffect(() => {
    if (!data) return;
    const candleSeries = candleSeriesRef.current;
    const liveSeries = liveSeriesRef.current;
    const markersPlugin = markersRef.current;
    if (!candleSeries || !liveSeries || !markersPlugin) return;

    const palette = readPalette();

    const candleData: CandlestickData<Time>[] = data.bars.map((b) => ({
      time: b.time as UTCTimestamp,
      open: b.open,
      high: b.high,
      low: b.low,
      close: b.close,
    }));
    candleSeries.setData(candleData);

    if (data.live) {
      const liveTime = barTimeForIso(data.live.atIso);
      liveSeries.setData([{ time: liveTime, value: data.live.price }]);
    } else {
      liveSeries.setData([]);
    }

    const byBarTime = new Map<number, ChartTradeMarker[]>();
    for (const t of data.trades) {
      const bucket = byBarTime.get(barTimeForIso(t.atIso) as number) ?? [];
      bucket.push(t);
      byBarTime.set(barTimeForIso(t.atIso) as number, bucket);
    }
    tradesByBarTimeRef.current = byBarTime;

    const markers = data.trades
      .map((t) => tradeMarker(t, palette))
      .sort((a, b) => (a.time as number) - (b.time as number));
    markersPlugin.setMarkers(markers);

    if (data.bars.length > 0) chartRef.current?.timeScale().fitContent();
  }, [data]);

  const noData = !isLoading && (!data || data.bars.length === 0);
  const containerWidth = containerRef.current?.clientWidth ?? 800;

  return (
    <div className="flex flex-col gap-3">
      <header className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <LineChart size={15} style={{ color: "var(--text-3)" }} aria-hidden />
          <span className="text-[11px] font-semibold uppercase tracking-[0.16em]" style={{ color: "var(--text-3)" }}>
            SPY · 5m
          </span>
        </div>
        {data?.live && (
          <div className="flex items-center gap-2 text-xs" style={{ color: "var(--text-2)" }}>
            <span className="live-dot" style={{ background: "var(--cyan)", boxShadow: "0 0 10px var(--cyan)" }} />
            <span style={{ color: "var(--text-1)" }}>${data.live.price.toFixed(2)}</span>
            <span style={{ color: "var(--text-4)" }}>{fmtAge(data.live.ageSeconds)}</span>
          </div>
        )}
      </header>

      <div className="relative w-full" style={{ height: 360 }}>
        <div ref={containerRef} className="h-full w-full" />

        {noData && (
          <div className="absolute inset-0 flex items-center justify-center text-sm" style={{ color: "var(--text-4)" }}>
            {error ? "Chart data unavailable — check back shortly" : "No chart data available"}
          </div>
        )}

        {callout && (
          <div
            className="pointer-events-none absolute z-10 max-w-xs rounded-md px-3 py-2 text-xs"
            style={{
              left: Math.min(callout.x + 12, Math.max(0, containerWidth - 240)),
              top: Math.max(callout.y - 12, 0),
              background: "var(--bg-overlay)",
              border: "1px solid var(--border-mid)",
              boxShadow: "var(--shadow-sm)",
            }}
          >
            {callout.trades.map((t, i) => {
              const toneColor =
                t.side === "entry" ? "var(--cyan)" : t.pnl !== null && t.pnl > 0 ? "var(--up)" : t.pnl !== null && t.pnl < 0 ? "var(--down)" : "var(--text-2)";
              return (
                <div key={i} className={i > 0 ? "mt-2 border-t pt-2" : ""} style={{ borderColor: "var(--border)" }}>
                  <div style={{ color: toneColor, fontWeight: 600 }}>
                    {t.side === "entry"
                      ? `Entered here — ${t.setup}`
                      : `Exited — ${t.setup}${t.pnl !== null ? ` (${fmtPnl(t.pnl)})` : ""}`}
                  </div>
                  <div style={{ color: "var(--text-3)" }}>
                    {t.direction.toUpperCase()} @ ${t.price.toFixed(2)}
                  </div>
                  {t.note && (
                    <div className="mt-1" style={{ color: "var(--text-2)" }}>
                      {t.note}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      <p className="text-[11px]" style={{ color: "var(--text-4)" }}>
        ▲/▼ entry (call/put) · ● exit (green win / red loss) · hover a marked bar for the real note
      </p>
    </div>
  );
}

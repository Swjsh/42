"use client";

import { useEffect, useRef, useState } from "react";

interface Props {
  data: any;
}

declare global {
  interface Window {
    TradingView?: any;
  }
}

// =============================================================================
// MAIN — image as background, live-data overlays on the static panels
// =============================================================================

export default function TradingFloor({ data }: Props) {
  return (
    <div
      className="relative w-full h-full overflow-hidden"
      style={{
        backgroundImage: "url(/trade-floor.png)",
        backgroundSize: "100% 100%",
        backgroundPosition: "center",
        backgroundRepeat: "no-repeat",
        backgroundColor: "#040806",
      }}
    >
      <PanelMasks />
      <TopBar data={data} />
      <LeftPanel data={data} />
      <CenterChart data={data} />
    </div>
  );
}

// Solid masks placed under each live panel. Slightly larger than the panels
// so any anti-aliasing/edge gradient on the image's panels is hidden too.
function PanelMasks(): JSX.Element {
  const mask: React.CSSProperties = {
    position: "absolute",
    background: "#040b08",
    pointerEvents: "none",
    zIndex: 0,
  };
  return (
    <>
      {/* top bar live regions (agent count + clock) */}
      <div style={{ ...mask, left: "11.5%", top: "1.0%", width: "11%", height: "5.5%" }} />
      <div style={{ ...mask, right: "0.5%", top: "1.0%", width: "12%", height: "5.5%" }} />
      {/* Left panel — slim (lines up with chart) */}
      <div style={{ ...mask, left: "3.0%", top: "10.5%", width: "23.5%", height: "44%" }} />
      {/* Center SPY chart */}
      <div style={{ ...mask, left: "26.2%", top: "10.5%", width: "42.5%", height: "44%" }} />
      {/* Right side — knock out static Floor Status + Market Time + plaque */}
      <div style={{ ...mask, left: "68.4%", top: "10.5%", width: "12.5%", height: "44%" }} />
    </>
  );
}

// =============================================================================
// SHARED STYLES
// =============================================================================

const PANEL_BG = "linear-gradient(180deg, #061410 0%, #081a14 100%)";
const PANEL_BORDER = "1px solid rgba(60,180,110,0.30)";
const PANEL_GLOW =
  "0 0 28px rgba(40,200,120,0.10), inset 0 0 0 1px rgba(60,120,80,0.10)";

const headerStyle: React.CSSProperties = {
  fontSize: "0.78em",
  fontWeight: 700,
  letterSpacing: "0.18em",
  color: "#7ee0a8",
  textTransform: "uppercase",
};

const fontStack =
  "'JetBrains Mono', 'IBM Plex Mono', ui-monospace, Menlo, monospace";

// =============================================================================
// TOP BAR — overlays the dynamic agent count + clock
// =============================================================================

interface TopBarProps {
  data: any;
}

function TopBar({ data }: TopBarProps): JSX.Element {
  const dialogue = data?.dialogue;
  const activeCount =
    (dialogue?.agents?.heartbeat?.active ? 1 : 0) +
    (dialogue?.agents?.day_trader?.active ? 1 : 0) +
    (dialogue?.agents?.review?.active ||
    dialogue?.agents?.premarket?.active ||
    dialogue?.agents?.eod?.active
      ? 1
      : 0);

  const [time, setTime] = useState("--:--:--");
  useEffect(() => {
    const tick = () => {
      const t = new Date().toLocaleTimeString("en-US", {
        hour12: false,
        timeZone: "America/New_York",
      });
      setTime(t);
    };
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <>
      <div
        style={{
          position: "absolute",
          left: "11.5%",
          top: "1.0%",
          height: "5.5%",
          width: "11%",
          display: "flex",
          alignItems: "center",
          paddingLeft: 8,
          fontFamily: fontStack,
          fontSize: "clamp(10px, 0.95vw, 14px)",
          color: "#cfead6",
          fontWeight: 500,
          letterSpacing: "0.02em",
          background: "transparent",
          pointerEvents: "none",
          zIndex: 2,
        }}
      >
        <span style={{ color: "#2ecc71", marginRight: 8 }}>•</span>
        Live Floor · {activeCount} Agents
      </div>

      <div
        style={{
          position: "absolute",
          right: "0.5%",
          top: "1.0%",
          height: "5.5%",
          width: "12%",
          display: "flex",
          alignItems: "center",
          justifyContent: "flex-end",
          paddingRight: 12,
          fontFamily: fontStack,
          fontSize: "clamp(11px, 1.0vw, 16px)",
          color: "#fbbf24",
          fontWeight: 700,
          letterSpacing: "0.05em",
          fontVariantNumeric: "tabular-nums",
          background: "transparent",
          pointerEvents: "none",
          zIndex: 2,
        }}
      >
        <span
          style={{
            color: "#7a9a85",
            fontSize: "0.7em",
            letterSpacing: "0.18em",
            marginRight: 10,
          }}
        >
          PIXEL LAYER
        </span>
        {time} EST
      </div>
    </>
  );
}

// =============================================================================
// LEFT PANEL — Market Outlook + Watchlist + News Feed (slim, matches chart h)
// =============================================================================

interface PanelProps {
  data: any;
}

function LeftPanel({ data }: PanelProps): JSX.Element {
  const todayBias = data?.todayBias;
  const dialogue = data?.dialogue;
  const bias: string | null = todayBias?.bias ?? null;
  const isBull = bias?.toLowerCase().includes("bull") ?? false;
  const isBear = bias?.toLowerCase().includes("bear") ?? false;
  const biasColor = isBull ? "#2ecc71" : isBear ? "#ef4444" : "#fbbf24";
  const biasArrow = isBull ? "▲" : isBear ? "▼" : "◆";

  const tomorrowHint: string | null =
    dialogue?.agents?.review?.speech ??
    dialogue?.agents?.eod?.speech ??
    dialogue?.agents?.premarket?.speech ??
    null;
  const segments = tomorrowHint
    ? tomorrowHint.split(/\s*\|\s*/).filter(Boolean).slice(0, 2)
    : [];

  const predictions: Array<{ outcome?: string | null }> =
    todayBias?.falsifiable_predictions ?? [];
  const passed = predictions.filter((p) => p.outcome === "PASS").length;
  const failed = predictions.filter((p) => p.outcome === "FAIL").length;
  const untested = predictions.filter((p) => p.outcome === "UNTESTED").length;

  const spy: number | null = data?.loopState?.spy_price ?? null;
  const cb = data?.circuitBreaker;
  const startEq = cb?.starting_equity_today;
  const curEq = cb?.current_equity;
  const pnlPct =
    startEq != null && curEq != null && startEq !== 0
      ? ((curEq - startEq) / startEq) * 100
      : null;
  const setup: string | null = data?.loopState?.setup_detected ?? null;
  const ribbon: string | null = data?.loopState?.ribbon?.order ?? null;
  const tradesToday = data?.tradesToday ?? 0;

  interface WatchRow {
    ticker: string;
    status: string;
    statusColor: string;
    value: string;
  }
  const watchlist: WatchRow[] = [
    {
      ticker: "SPY",
      status:
        pnlPct != null
          ? `${pnlPct >= 0 ? "+" : ""}${pnlPct.toFixed(2)}%`
          : "HOLD",
      statusColor:
        pnlPct != null && pnlPct >= 0
          ? "#2ecc71"
          : pnlPct != null
            ? "#ef4444"
            : "#fbbf24",
      value: spy != null ? `$${spy.toFixed(2)}` : "—",
    },
    {
      ticker: "RBN",
      status: ribbon ? ribbon.slice(0, 4) : "MIX",
      statusColor:
        ribbon === "BULLISH"
          ? "#2ecc71"
          : ribbon === "BEARISH"
            ? "#ef4444"
            : "#fbbf24",
      value:
        data?.loopState?.ribbon?.spread != null
          ? `${data.loopState.ribbon.spread}¢`
          : "—",
    },
    {
      ticker: "SET",
      status: setup ? "ARMED" : "FLAT",
      statusColor: setup ? "#2ecc71" : "#7a9a85",
      value: setup
        ? setup.replace(/_/g, " ").slice(0, 9).toUpperCase()
        : `${tradesToday}/3`,
    },
  ];

  return (
    <div
      style={{
        position: "absolute",
        left: "3.0%",
        top: "10.5%",
        width: "23.5%",
        height: "44%",
        background: PANEL_BG,
        border: PANEL_BORDER,
        borderRadius: 6,
        boxShadow: PANEL_GLOW,
        padding: "1.1% 1.2%",
        fontFamily: fontStack,
        color: "#cfead6",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        pointerEvents: "none",
        zIndex: 2,
      }}
    >
      {/* TOP ROW: Market Outlook (left) + Watchlist (right) */}
      <div style={{ display: "flex", gap: "6%", flex: 1, minHeight: 0 }}>
        <div style={{ flex: "0 0 56%", display: "flex", flexDirection: "column" }}>
          <div style={headerStyle}>MARKET OUTLOOK</div>
          <div
            style={{
              marginTop: "0.3em",
              fontSize: "clamp(15px, 1.55vw, 24px)",
              fontWeight: 800,
              color: biasColor,
              letterSpacing: "0.04em",
              lineHeight: 1.05,
            }}
          >
            {biasArrow} {(bias ?? "PENDING").toUpperCase()}
          </div>
          <div
            style={{
              marginTop: "0.5em",
              fontSize: "clamp(9px, 0.78vw, 13px)",
              color: "#cfead6",
              lineHeight: 1.5,
            }}
          >
            {segments.length > 0 ? (
              segments.map((s, i) => (
                <div key={i} style={{ marginBottom: 1 }}>
                  {s}
                </div>
              ))
            ) : (
              <div style={{ color: "#5a7a65", fontStyle: "italic" }}>
                awaiting bias…
              </div>
            )}
          </div>
          <div style={{ marginTop: "auto", paddingTop: "0.4em" }}>
            <div style={headerStyle}>SETUPS</div>
            <div
              style={{
                marginTop: 2,
                fontSize: "clamp(11px, 1.0vw, 16px)",
                fontWeight: 700,
                fontVariantNumeric: "tabular-nums",
              }}
            >
              <span style={{ color: "#2ecc71" }}>{passed}P</span>
              <span style={{ color: "#3a5a44", margin: "0 5px" }}>/</span>
              <span style={{ color: "#ef4444" }}>{failed}F</span>
              <span style={{ color: "#3a5a44", margin: "0 5px" }}>/</span>
              <span style={{ color: "#fbbf24" }}>{untested}U</span>
            </div>
          </div>
        </div>

        <div
          style={{ flex: "0 0 38%", display: "flex", flexDirection: "column" }}
        >
          <div style={headerStyle}>WATCHLIST</div>
          <div
            style={{
              marginTop: "0.4em",
              display: "flex",
              flexDirection: "column",
              gap: "0.4em",
            }}
          >
            {watchlist.map((r) => (
              <div
                key={r.ticker}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  fontSize: "clamp(8px, 0.72vw, 12px)",
                }}
              >
                <span
                  style={{ color: "#cfead6", fontWeight: 700, width: "26%" }}
                >
                  {r.ticker}
                </span>
                <span
                  style={{
                    color: r.statusColor,
                    fontWeight: 700,
                    width: "34%",
                    fontSize: "0.92em",
                  }}
                >
                  {r.status}
                </span>
                <span
                  style={{
                    color: "#cfead6",
                    fontVariantNumeric: "tabular-nums",
                    marginLeft: "auto",
                    textAlign: "right",
                  }}
                >
                  {r.value}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// CENTER CHART — TradingView widget with EMA ribbon
// =============================================================================

function CenterChart({ data }: PanelProps): JSX.Element {
  const setup: string | null = data?.loopState?.setup_detected ?? null;

  return (
    <div
      style={{
        position: "absolute",
        left: "26.2%",
        top: "10.5%",
        width: "42.5%",
        height: "44%",
        background: PANEL_BG,
        border: PANEL_BORDER,
        borderRadius: 6,
        boxShadow: PANEL_GLOW,
        padding: "0.8% 0.9%",
        fontFamily: fontStack,
        color: "#cfead6",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        zIndex: 2,
      }}
    >
      {/* HEADER */}
      <div
        style={{
          display: "flex",
          alignItems: "baseline",
          justifyContent: "space-between",
          flexShrink: 0,
          paddingBottom: "0.4em",
        }}
      >
        <div>
          <span
            style={{
              fontSize: "clamp(15px, 1.4vw, 22px)",
              fontWeight: 800,
              color: "#cfead6",
              letterSpacing: "0.02em",
            }}
          >
            SPY
          </span>
          <span
            style={{
              marginLeft: 10,
              fontSize: "clamp(8px, 0.65vw, 11px)",
              color: "#7a9a85",
              letterSpacing: "0.18em",
            }}
          >
            5m · EMA RIBBON
          </span>
        </div>
        {setup && (
          <span
            style={{
              fontSize: "clamp(9px, 0.7vw, 12px)",
              padding: "2px 8px",
              background: "rgba(251,191,36,0.18)",
              border: "1px solid #fbbf24",
              color: "#fbbf24",
              fontWeight: 700,
              letterSpacing: "0.08em",
              borderRadius: 3,
            }}
          >
            ⚡ {setup.replace(/_/g, " ").toUpperCase()}
          </span>
        )}
      </div>

      {/* TRADINGVIEW WIDGET */}
      <div
        style={{
          flex: 1,
          background: "#0a0f1c",
          border: "1px solid rgba(60,180,110,0.18)",
          borderRadius: 3,
          overflow: "hidden",
          minHeight: 0,
        }}
      >
        <TradingViewWidget />
      </div>
    </div>
  );
}

// =============================================================================
// TRADINGVIEW WIDGET — SPY 5m with EMA ribbon (8/21/55) + volume
// =============================================================================

function TradingViewWidget(): JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string>(
    `tv_${Math.random().toString(36).slice(2, 10)}`,
  );

  useEffect(() => {
    const id = widgetIdRef.current;

    const renderWidget = () => {
      if (!window.TradingView || !containerRef.current) return;
      containerRef.current.innerHTML = `<div id="${id}" style="height:100%;width:100%"></div>`;
      // eslint-disable-next-line @typescript-eslint/no-new
      new window.TradingView.widget({
        autosize: true,
        symbol: "AMEX:SPY",
        interval: "5",
        timezone: "America/New_York",
        theme: "dark",
        style: "1",
        locale: "en",
        toolbar_bg: "#0a0f1c",
        enable_publishing: false,
        hide_top_toolbar: true,
        hide_legend: false,
        hide_side_toolbar: true,
        save_image: false,
        container_id: id,
        backgroundColor: "#0a0f1c",
        gridColor: "rgba(80,140,100,0.06)",
        withdateranges: false,
        allow_symbol_change: false,
        // EMA RIBBON: 8/21/55 + volume
        studies: [
          "MAExp@tv-basicstudies",
          "MAExp@tv-basicstudies",
          "MAExp@tv-basicstudies",
          "Volume@tv-basicstudies",
        ],
        studies_overrides: {
          "moving average exponential.length": 8,
          "moving average exponential.plot.color": "#22d3ee",
          "moving average exponential.plot.linewidth": 2,
        },
        overrides: {
          "paneProperties.background": "#0a0f1c",
          "paneProperties.vertGridProperties.color": "rgba(80,140,100,0.05)",
          "paneProperties.horzGridProperties.color": "rgba(80,140,100,0.05)",
          "scalesProperties.textColor": "#7a9a85",
          "mainSeriesProperties.candleStyle.upColor": "#2ecc71",
          "mainSeriesProperties.candleStyle.downColor": "#ef4444",
          "mainSeriesProperties.candleStyle.borderUpColor": "#2ecc71",
          "mainSeriesProperties.candleStyle.borderDownColor": "#ef4444",
          "mainSeriesProperties.candleStyle.wickUpColor": "#2ecc71",
          "mainSeriesProperties.candleStyle.wickDownColor": "#ef4444",
        },
      });
    };

    if (window.TradingView) {
      renderWidget();
      return;
    }

    const existing = document.querySelector<HTMLScriptElement>(
      'script[src="https://s3.tradingview.com/tv.js"]',
    );
    if (existing) {
      existing.addEventListener("load", renderWidget);
      return () => existing.removeEventListener("load", renderWidget);
    }

    const script = document.createElement("script");
    script.src = "https://s3.tradingview.com/tv.js";
    script.async = true;
    script.onload = renderWidget;
    document.head.appendChild(script);
  }, []);

  return (
    <div
      ref={containerRef}
      style={{ width: "100%", height: "100%" }}
    >
      <div
        style={{
          display: "grid",
          placeItems: "center",
          height: "100%",
          color: "#5a7a65",
          fontSize: 11,
          fontFamily: fontStack,
        }}
      >
        loading SPY chart…
      </div>
    </div>
  );
}

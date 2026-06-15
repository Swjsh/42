"use client";

import React, { useEffect, useRef, useState } from "react";

// React 19 + @types/react 19 removed the global JSX namespace.
// Alias to React.JSX.Element so existing function signatures stay intact.
type JSXElement = React.JSX.Element;

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
      <RightPanel data={data} />
    </div>
  );
}

// Solid masks placed under each live panel. Slightly larger than the panels
// so any anti-aliasing/edge gradient on the image's panels is hidden too.
function PanelMasks(): JSXElement {
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

function TopBar({ data }: TopBarProps): JSXElement {
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

function LeftPanel({ data }: PanelProps): JSXElement {
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
  const scanMode: string = data?.loopState?.scan_mode ?? "COOL";
  const scanColor =
    scanMode === "HOT" ? "#ef4444" : scanMode === "BASE" ? "#fbbf24" : "#5a7a65";

  // Key levels sorted by proximity to current price (Active + Carry only)
  const levels: any[] = (data?.keyLevels?.levels ?? [])
    .filter((l: any) => l.tier === "Active" || l.tier === "Carry")
    .sort(
      (a: any, b: any) =>
        Math.abs(a.price - (spy ?? 0)) - Math.abs(b.price - (spy ?? 0)),
    )
    .slice(0, 5);

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
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 0 }}>
            <div style={headerStyle}>MARKET OUTLOOK</div>
            <div style={{ display: "flex", alignItems: "center", gap: 4, marginLeft: "auto" }}>
              <span style={{ width: 5, height: 5, borderRadius: "50%", background: scanColor, flexShrink: 0 }} />
              <span style={{ ...headerStyle, fontSize: "0.62em", color: scanColor }}>{scanMode}</span>
            </div>
          </div>
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
              color: "#8aa898",
              lineHeight: 1.4,
            }}
          >
            {segments.length > 0 ? (
              <div>
                {segments[0].length > 60
                  ? segments[0].slice(0, 60) + "…"
                  : segments[0]}
              </div>
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
          <div style={headerStyle}>LEVELS</div>
          <div
            style={{
              marginTop: "0.4em",
              display: "flex",
              flexDirection: "column",
              gap: "0.35em",
            }}
          >
            {levels.length === 0 ? (
              <div style={{ color: "#5a7a65", fontSize: "clamp(8px, 0.68vw, 11px)", fontStyle: "italic" }}>
                no levels
              </div>
            ) : (
              levels.map((lv: any) => {
                const isRes   = lv.type === "resistance";
                const isCarry = lv.tier === "Carry";
                const dot     = isCarry ? "#3b82f6" : isRes ? "#ef4444" : "#2ecc71";
                const dist    = spy != null ? lv.price - spy : null;
                const distStr = dist != null
                  ? `${dist >= 0 ? "+" : ""}${dist.toFixed(1)}`
                  : "";
                const distColor =
                  dist == null ? "#5a7a65" : dist >= 0 ? "#ef4444" : "#2ecc71";
                return (
                  <div
                    key={lv.price}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 5,
                      fontSize: "clamp(8px, 0.68vw, 11px)",
                    }}
                  >
                    <span
                      style={{
                        width: 5,
                        height: 5,
                        borderRadius: "50%",
                        background: dot,
                        flexShrink: 0,
                      }}
                    />
                    <span
                      style={{
                        color: "#cfead6",
                        fontWeight: 700,
                        fontVariantNumeric: "tabular-nums",
                        flex: 1,
                      }}
                    >
                      {lv.price.toFixed(2)}
                    </span>
                    <span
                      style={{
                        color: distColor,
                        fontVariantNumeric: "tabular-nums",
                        fontWeight: 600,
                        textAlign: "right",
                      }}
                    >
                      {distStr}
                    </span>
                  </div>
                );
              })
            )}
          </div>

          {/* ribbon state below levels */}
          <div style={{ marginTop: "auto", paddingTop: "0.4em", borderTop: "1px solid rgba(60,180,110,0.12)" }}>
            <div style={headerStyle}>RIBBON</div>
            <div style={{
              marginTop: 2,
              display: "flex",
              alignItems: "center",
              gap: 6,
              fontSize: "clamp(9px, 0.8vw, 13px)",
              fontWeight: 700,
            }}>
              <span style={{
                color: ribbon === "BULLISH" ? "#2ecc71" : ribbon === "BEARISH" ? "#ef4444" : "#fbbf24",
              }}>
                {ribbon ? ribbon.slice(0, 4) : "MIX"}
              </span>
              {data?.loopState?.ribbon?.spread != null && (
                <span style={{ color: "#5a7a65", fontSize: "0.85em", fontWeight: 400 }}>
                  {data.loopState.ribbon.spread}¢
                </span>
              )}
              {setup && (
                <span style={{ color: "#fbbf24", fontSize: "0.72em", marginLeft: "auto" }}>⚡</span>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// CENTER CHART — TradingView widget with EMA ribbon
// =============================================================================

function CenterChart({ data }: PanelProps): JSXElement {
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

function TradingViewWidget(): JSXElement {
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

// =============================================================================
// RIGHT PANEL — Scan mode / Daily P&L / Kill switch / Position
// =============================================================================

function RightPanel({ data }: PanelProps): JSXElement {
  const cb = data?.circuitBreaker;
  const startEq: number | null =
    cb?.starting_equity_today ?? cb?.starting_equity ?? null;
  const curEq: number | null = cb?.current_equity ?? null;
  const dailyLimit: number | null = cb?.daily_loss_limit ?? null;

  const pnlRaw =
    startEq != null && curEq != null ? curEq - startEq : null;
  const drawdown = pnlRaw != null && pnlRaw < 0 ? -pnlRaw : 0;
  const killPct =
    dailyLimit != null && dailyLimit > 0 ? drawdown / dailyLimit : 0;
  const killBarColor =
    killPct >= 0.8 ? "#ef4444" : killPct >= 0.5 ? "#fbbf24" : "#2ecc71";

  const scanMode: string = data?.loopState?.scan_mode ?? "COOL";
  const scanColor =
    scanMode === "HOT" ? "#ef4444" : scanMode === "BASE" ? "#fbbf24" : "#5a7a65";

  const pos = data?.currentPosition;
  const posOpen =
    pos?.status === "open" || (pos?.symbol && pos?.qty && pos.qty !== 0);

  const pnlColor =
    pnlRaw == null ? "#5a7a65" : pnlRaw >= 0 ? "#2ecc71" : "#ef4444";
  const pnlSign = pnlRaw == null ? "" : pnlRaw >= 0 ? "+" : "−";
  const pnlAbs = pnlRaw == null ? null : Math.abs(pnlRaw);
  const pnlPct =
    startEq != null && startEq !== 0 && pnlRaw != null
      ? (pnlRaw / startEq) * 100
      : null;

  return (
    <div
      style={{
        position: "absolute",
        left: "68.4%",
        top: "10.5%",
        width: "12.5%",
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
        gap: "0.55em",
        overflow: "hidden",
        pointerEvents: "none",
        zIndex: 2,
      }}
    >
      {/* SCAN MODE */}
      <div>
        <div style={headerStyle}>SCAN</div>
        <div style={{
          marginTop: 3,
          display: "flex",
          alignItems: "center",
          gap: 6,
          fontSize: "clamp(12px, 1.15vw, 18px)",
          fontWeight: 800,
          color: scanColor,
          letterSpacing: "0.06em",
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: "50%",
            background: scanColor, flexShrink: 0,
            boxShadow: `0 0 6px ${scanColor}`,
          }} />
          {scanMode}
        </div>
      </div>

      {/* DAILY P&L */}
      <div style={{ borderTop: "1px solid rgba(60,180,110,0.14)", paddingTop: "0.55em" }}>
        <div style={headerStyle}>P&amp;L TODAY</div>
        <div style={{
          marginTop: 3,
          fontSize: "clamp(13px, 1.25vw, 20px)",
          fontWeight: 800,
          color: pnlColor,
          fontVariantNumeric: "tabular-nums",
          letterSpacing: "0.03em",
          lineHeight: 1.1,
        }}>
          {pnlAbs != null ? `${pnlSign}$${pnlAbs.toFixed(0)}` : "—"}
        </div>
        {pnlPct != null && (
          <div style={{
            fontSize: "clamp(8px, 0.68vw, 11px)",
            color: pnlColor,
            opacity: 0.75,
            fontVariantNumeric: "tabular-nums",
            marginTop: 1,
          }}>
            {pnlSign}{Math.abs(pnlPct).toFixed(1)}%
          </div>
        )}
      </div>

      {/* KILL SWITCH */}
      <div style={{ borderTop: "1px solid rgba(60,180,110,0.14)", paddingTop: "0.55em" }}>
        <div style={headerStyle}>KILL SWITCH</div>
        <div style={{
          marginTop: 4,
          height: 4,
          background: "rgba(255,255,255,0.07)",
          borderRadius: 2,
          overflow: "hidden",
        }}>
          <div style={{
            height: "100%",
            width: `${Math.min(killPct * 100, 100).toFixed(1)}%`,
            background: killBarColor,
            borderRadius: 2,
            transition: "width 0.6s ease, background 0.3s",
          }} />
        </div>
        <div style={{
          marginTop: 3,
          display: "flex",
          justifyContent: "space-between",
          fontSize: "clamp(7px, 0.58vw, 9px)",
          color: "#5a7a65",
          fontVariantNumeric: "tabular-nums",
        }}>
          <span style={{ color: killBarColor }}>
            −${drawdown.toFixed(0)}
          </span>
          <span>/ ${dailyLimit != null ? dailyLimit.toFixed(0) : "—"}</span>
        </div>
      </div>

      {/* POSITION */}
      <div style={{ borderTop: "1px solid rgba(60,180,110,0.14)", paddingTop: "0.55em", flex: 1 }}>
        <div style={headerStyle}>POSITION</div>
        {!posOpen ? (
          <div style={{
            marginTop: 4,
            fontSize: "clamp(8px, 0.68vw, 11px)",
            color: "#5a7a65",
            fontStyle: "italic",
          }}>
            flat
          </div>
        ) : (
          <div style={{
            marginTop: 4,
            display: "flex",
            flexDirection: "column",
            gap: "0.32em",
          }}>
            <div style={{
              fontSize: "clamp(10px, 0.9vw, 14px)",
              fontWeight: 800,
              color: "#fbbf24",
              letterSpacing: "0.04em",
            }}>
              {pos.symbol ?? "—"}
            </div>
            {[
              { label: "qty",   val: pos.qty ?? "—" },
              { label: "fill",  val: pos.fill_price != null ? `$${Number(pos.fill_price).toFixed(2)}` : "—" },
              { label: "floor", val: pos.profit_lock_floor != null ? `$${Number(pos.profit_lock_floor).toFixed(2)}` : "—" },
            ].map(({ label, val }) => (
              <div key={label} style={{
                display: "flex",
                justifyContent: "space-between",
                fontSize: "clamp(7px, 0.62vw, 10px)",
                fontVariantNumeric: "tabular-nums",
              }}>
                <span style={{ color: "#5a7a65" }}>{label}</span>
                <span style={{ color: "#cfead6", fontWeight: 600 }}>{String(val)}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

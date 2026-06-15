"use client";

import { useEffect, useRef } from "react";

interface Props {
  data: any;
}

declare global {
  interface Window {
    TradingView?: any;
  }
}

export default function ChartPanel({ data }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetIdRef = useRef<string>(
    `tv_${Math.random().toString(36).slice(2, 10)}`,
  );

  useEffect(() => {
    const id = widgetIdRef.current;
    const renderWidget = () => {
      if (!window.TradingView || !containerRef.current) return;
      containerRef.current.innerHTML = `<div id="${id}" style="height:100%"></div>`;
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
        gridColor: "rgba(255,255,255,0.04)",
        withdateranges: false,
        allow_symbol_change: false,
        studies: ["Volume@tv-basicstudies"],
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

  const setup: string | null = data?.loopState?.setup_detected ?? null;
  const triggerFired: boolean = !!data?.loopState?.trigger_fired;

  return (
    <section
      className="tour-card flex flex-col p-4 min-h-0"
      data-accent="violet"
    >
      <div className="flex items-center justify-between mb-3 flex-shrink-0">
        <div className="flex items-center gap-3">
          <span className="eyebrow violet">SPY · 5-min · Live</span>
          {setup ? (
            <span
              className="font-mono"
              style={{
                fontSize: 11,
                color: "var(--text-2)",
                letterSpacing: "0.05em",
              }}
            >
              setup{" "}
              <span style={{ color: "var(--amber)", fontWeight: 700 }}>
                {setup}
              </span>
              {triggerFired && (
                <span
                  className="live-dot"
                  style={{
                    display: "inline-block",
                    marginLeft: 8,
                    verticalAlign: "middle",
                  }}
                />
              )}
              {triggerFired && (
                <span
                  style={{
                    color: "var(--up)",
                    fontWeight: 700,
                    marginLeft: 4,
                  }}
                >
                  TRIGGER FIRED
                </span>
              )}
            </span>
          ) : (
            <span
              className="font-mono"
              style={{
                fontSize: 11,
                color: "var(--text-3)",
                letterSpacing: "0.05em",
              }}
            >
              no setup detected
            </span>
          )}
        </div>
        <span
          className="font-mono"
          style={{
            fontSize: 10,
            color: "var(--text-4)",
            letterSpacing: "0.05em",
          }}
        >
          AMEX:SPY · 5m
        </span>
      </div>

      <div
        ref={containerRef}
        className="flex-1 min-h-0"
        style={{
          background: "var(--bg-base)",
          border: "1px solid var(--border)",
          borderRadius: "var(--radius)",
          overflow: "hidden",
        }}
      >
        <div
          className="grid place-items-center h-full"
          style={{ color: "var(--text-3)", fontSize: 13 }}
        >
          loading chart…
        </div>
      </div>
    </section>
  );
}

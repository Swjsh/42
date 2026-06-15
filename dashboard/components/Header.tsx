"use client";

import { useEffect, useState } from "react";
import { formatET } from "@/lib/time";

interface Props {
  data: any;
  error: boolean;
}

export default function Header({ data, error }: Props) {
  const [clock, setClock] = useState<string>("--:--:--");

  useEffect(() => {
    const tick = () => setClock(formatET());
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const mode: string = data?.mode?.mode ?? "loading";
  const isOnline = mode === "live-paper" || mode === "live";
  const ping =
    data?.fetched_at && data?.loopState?.last_updated
      ? Math.abs(
          new Date(data.fetched_at).getTime() -
            new Date(data.loopState.last_updated).getTime(),
        )
      : null;

  const pingText =
    ping == null
      ? "—"
      : ping > 60_000
        ? `${Math.floor(ping / 60_000)}m stale`
        : `${Math.floor(ping / 1000)}s`;

  const statusColor = error
    ? "var(--down)"
    : isOnline
      ? "var(--up)"
      : "var(--amber)";
  const statusText = error ? "OFFLINE" : isOnline ? "LIVE" : "PAUSED";

  return (
    <header
      className="tour-card flex items-center justify-between px-5 py-3"
      data-accent="cyan"
      style={{ flexShrink: 0 }}
    >
      <div className="flex items-center gap-3">
        <div
          className="grid place-items-center"
          style={{
            width: 32,
            height: 32,
            borderRadius: 8,
            background: "linear-gradient(135deg, #22d3ee 0%, #a78bfa 100%)",
            color: "#050810",
            fontFamily: "var(--font-space-grotesk), sans-serif",
            fontWeight: 800,
            fontSize: 16,
            boxShadow: "0 0 24px rgba(34,211,238,0.4)",
            letterSpacing: "-0.04em",
          }}
        >
          γ
        </div>
        <div className="flex flex-col">
          <span
            className="font-display"
            style={{
              fontSize: 17,
              fontWeight: 700,
              color: "var(--text-1)",
              lineHeight: 1,
            }}
          >
            Gamma
          </span>
          <span
            className="font-mono"
            style={{
              fontSize: 12,
              fontWeight: 600,
              letterSpacing: "0.18em",
              textTransform: "uppercase",
              color: "var(--text-3)",
              marginTop: 3,
            }}
          >
            The Trade House
          </span>
        </div>
      </div>

      <div className="flex items-center gap-3">
        <div
          className="inline-flex items-center gap-2"
          style={{
            padding: "5px 12px",
            borderRadius: 999,
            background: `color-mix(in srgb, ${statusColor} 14%, transparent)`,
            border: `1px solid color-mix(in srgb, ${statusColor} 40%, transparent)`,
          }}
        >
          <span
            className={isOnline && !error ? "live-dot" : ""}
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: statusColor,
              boxShadow: !error && isOnline ? `0 0 10px ${statusColor}` : "none",
            }}
          />
          <span
            className="font-mono"
            style={{
              fontSize: 13,
              fontWeight: 700,
              letterSpacing: "0.1em",
              color: statusColor,
              textTransform: "uppercase",
            }}
          >
            {statusText}
          </span>
        </div>

        <span
          className="font-mono"
          style={{
            fontSize: 13,
            color: "var(--text-3)",
            letterSpacing: "0.05em",
          }}
        >
          PING <span style={{ color: "var(--text-1)" }}>{pingText}</span>
        </span>

        <div
          style={{
            width: 1,
            height: 20,
            background: "var(--border)",
            margin: "0 4px",
          }}
        />

        <span
          className="font-mono tabular-nums"
          style={{
            fontSize: 18,
            fontWeight: 600,
            color: "var(--amber)",
            letterSpacing: "0.02em",
          }}
        >
          {clock}
          <span
            style={{
              fontSize: 13,
              color: "var(--text-3)",
              marginLeft: 6,
              fontWeight: 500,
            }}
          >
            ET
          </span>
        </span>
      </div>
    </header>
  );
}

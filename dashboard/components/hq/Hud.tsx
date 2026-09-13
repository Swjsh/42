"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import type { HqApiResponse } from "./types";

interface HudProps {
  data: HqApiResponse | undefined;
  error: unknown;
  kiosk: boolean;
  isValidating: boolean;
}

function useEtClock(): string {
  const [text, setText] = useState("--:--:--");
  useEffect(() => {
    const fmt = new Intl.DateTimeFormat("en-US", {
      timeZone: "America/New_York",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    });
    const tick = () => setText(fmt.format(new Date()) + " ET");
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return text;
}

const HUD_FONT = "system-ui, -apple-system, Segoe UI, Roboto, sans-serif";

/**
 * Plain HTML overlay (not 3D text -- crisp at any TV viewing distance).
 * Sits in a fixed, full-viewport, pointer-events-none wrapper above the
 * <Canvas>; individual controls (Home link) re-enable pointer events.
 */
export default function Hud({ data, error, kiosk, isValidating }: HudProps) {
  const etClock = useEtClock();
  const mode = data?.mode ?? "unknown";
  const gaming = mode === "gaming";
  const present = data?.presence?.present ?? null;
  const syncedText = data
    ? `Synced ${new Date(data.fetched_at).toLocaleTimeString()}${isValidating ? " -- syncing..." : ""}`
    : error
      ? `Refresh failed (${error instanceof Error ? error.message : "fetch failed"})`
      : "Loading...";
  const brief = data?.brief.text || "NO DATA -- no brief written yet";

  return (
    <div style={{ position: "fixed", inset: 0, pointerEvents: "none", fontFamily: HUD_FONT, zIndex: 10 }}>
      <style>{`
        @keyframes hq-ticker-scroll {
          from { transform: translateX(100vw); }
          to { transform: translateX(-100%); }
        }
      `}</style>

      {/* Top-left: title + ET clock + mode badge */}
      <div style={{ position: "absolute", top: 16, left: 20, display: "flex", alignItems: "center", gap: 12 }}>
        <span style={{ color: "#dff3ff", fontSize: 22, fontWeight: 700, letterSpacing: 2, textShadow: "0 0 12px rgba(122,217,255,0.6)" }}>
          GAMMA HQ
        </span>
        <span style={{ color: "#7f93b0", fontSize: 15, fontVariantNumeric: "tabular-nums" }}>{etClock}</span>
        <span
          style={{
            fontSize: 12, padding: "2px 10px", borderRadius: 999,
            background: gaming ? "rgba(255,176,32,0.18)" : "rgba(34,255,136,0.14)",
            color: gaming ? "#ffb020" : "#22ff88",
            border: `1px solid ${gaming ? "#ffb020" : "#22ff88"}`,
          }}
        >
          {gaming ? "GPU RESERVED" : `mode: ${mode}`}
        </span>
      </div>

      {/* Non-kiosk only: Home link, slim */}
      {!kiosk && (
        <div style={{ position: "absolute", top: 16, right: 20, pointerEvents: "auto", display: "flex", alignItems: "center", gap: 14 }}>
          <Link href="/" style={{ color: "#7f93b0", fontSize: 13, textDecoration: "none" }}>
            &larr; Home
          </Link>
        </div>
      )}

      {/* Top-right: presence lamp (kiosk) */}
      {kiosk && (
        <div style={{ position: "absolute", top: 18, right: 20, display: "flex", alignItems: "center", gap: 8 }}>
          <span
            style={{
              width: 9, height: 9, borderRadius: 999,
              background: present ? "#22ff88" : "#3a4560",
              boxShadow: present ? "0 0 8px #22ff88" : "none",
            }}
          />
          <span style={{ color: "#7f93b0", fontSize: 13 }}>{present ? "J is here" : "J is away"}</span>
        </div>
      )}

      {/* Bottom ticker: scrolling brief text */}
      <div
        style={{
          position: "absolute", left: 0, right: 0, bottom: 34, height: 26,
          overflow: "hidden", background: "rgba(3,4,10,0.55)", borderTop: "1px solid rgba(122,217,255,0.15)",
          borderBottom: "1px solid rgba(122,217,255,0.15)",
        }}
      >
        <div
          style={{
            whiteSpace: "nowrap", color: "#9fd8ff", fontSize: 13, lineHeight: "26px",
            display: "inline-block", animation: "hq-ticker-scroll 55s linear infinite",
          }}
        >
          {brief}
        </div>
      </div>

      {/* Bottom-right corner: synced status */}
      <div style={{ position: "absolute", bottom: 8, right: 12 }}>
        <span style={{ color: "#4a5a78", fontSize: 11 }}>{syncedText}</span>
      </div>
    </div>
  );
}

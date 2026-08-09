"use client";

import useSWR from "swr";
import type { Quote } from "@/lib/quote";

const REFRESH_MS = 15_000;

async function fetcher(url: string): Promise<Quote> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as Quote;
}

function formatChange(change: number | null, changePct: number | null): string | null {
  if (change === null || changePct === null) return null;
  const sign = change >= 0 ? "+" : "";
  return `${sign}${change.toFixed(2)} (${sign}${changePct.toFixed(2)}%)`;
}

/**
 * THE LIVE MARKET PRICE -- a compact ticker reading the NEVER-BLIND sight
 * beacon (automation/state/sight-beacon.json via /api/gamma-quote) every 15s.
 * Honest by construction: labeled "as of HH:MM:SS ET" (never "live tick"),
 * and visually dims + ambers when the underlying snapshot is stale (>180s,
 * matching sight_beacon.py's own STALE_AFTER_S convention).
 */
export default function QuoteTicker() {
  const { data, error } = useSWR<Quote>("/api/gamma-quote", fetcher, {
    refreshInterval: REFRESH_MS,
    keepPreviousData: true,
  });

  if (error && !data) {
    return (
      <div
        className="flex items-center gap-2 rounded-[var(--radius)] border px-3 py-1.5 text-xs"
        style={{ borderColor: "var(--border)", background: "var(--bg-card)", color: "var(--text-4)" }}
      >
        SPY quote unavailable
      </div>
    );
  }

  if (!data || data.price === null) {
    return (
      <div
        className="flex items-center gap-2 rounded-[var(--radius)] border px-3 py-1.5"
        style={{ borderColor: "var(--border)", background: "var(--bg-card)" }}
      >
        <span className="skeleton-bar h-3.5 w-28 rounded-sm" />
      </div>
    );
  }

  const isStale = data.staleness === "stale";
  const changeLabel = formatChange(data.change, data.changePct);
  const changeColor = data.change === null ? "var(--text-3)" : data.change >= 0 ? "var(--up)" : "var(--down)";

  return (
    <div
      className="flex items-center gap-3 rounded-[var(--radius)] border px-3 py-1.5 text-xs transition-opacity"
      style={{
        borderColor: isStale ? "rgba(245, 158, 11, 0.35)" : "var(--border)",
        background: isStale ? "var(--amber-soft)" : "var(--bg-card)",
        opacity: isStale ? 0.85 : 1,
      }}
      title={
        isStale && data.ageSeconds !== null
          ? `Stale beacon -- last written ${data.ageSeconds}s ago (>180s = untrustworthy)`
          : undefined
      }
    >
      <span
        className="h-2 w-2 shrink-0 rounded-full"
        style={{
          background: isStale ? "var(--amber)" : "var(--up)",
          boxShadow: isStale ? "0 0 8px var(--amber)" : "0 0 8px var(--up)",
        }}
        aria-hidden
      />
      <span className="font-mono font-semibold" style={{ color: "var(--text-1)" }}>
        SPY {data.price.toFixed(2)}
      </span>
      {changeLabel && (
        <span className="font-mono" style={{ color: changeColor }}>
          {changeLabel}
        </span>
      )}
      <span style={{ color: isStale ? "var(--amber)" : "var(--text-4)" }}>
        as of {data.asOfEt ?? "—"} ET{isStale ? " · stale" : ""}
      </span>
    </div>
  );
}

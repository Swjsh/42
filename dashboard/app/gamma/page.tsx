"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import PresenceHeader from "@/components/gamma/PresenceHeader";
import ActivityFeed from "@/components/gamma/ActivityFeed";
import MoneyView from "@/components/gamma/MoneyView";
import WantsCards from "@/components/gamma/WantsCards";
import ThisWeekCard from "@/components/gamma/ThisWeekCard";
import type { GammaAppView } from "@/lib/gamma-app-types";

const REFRESH_MS = 20_000;

const EMPTY_VIEW: GammaAppView = {
  fetchedAt: new Date(0).toISOString(),
  presence: null,
  activity: [],
  wants: [],
  thisWeek: [],
};

/**
 * THE GAMMA APP -- Gamma's one true presence surface (2026-08-08). Not a
 * metrics wall: a colleague's status page. Sections in order: presence
 * header (identity + live state + first-person "what I'm doing right now"),
 * the live activity stream (centerpiece), the money view (goal/tape/clocks),
 * wants, and this week's plan. Polls /api/gamma every 20s and updates state
 * in place -- never a full reload, never a layout jump (every section
 * already renders its full shape with placeholders before the first fetch
 * resolves, so real data only ever swaps text/widths, not structure).
 */
export default function GammaAppPage() {
  const [view, setView] = useState<GammaAppView>(EMPTY_VIEW);
  const [nowMs, setNowMs] = useState<number>(() => Date.now());
  const [lastError, setLastError] = useState<string | null>(null);
  const [lastOkAt, setLastOkAt] = useState<Date | null>(null);
  const hasLoaded = useRef(false);

  const refresh = useCallback(async () => {
    try {
      const res = await fetch("/api/gamma", { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as GammaAppView;
      setView(data);
      setNowMs(Date.now());
      setLastError(null);
      setLastOkAt(new Date());
      hasLoaded.current = true;
    } catch (err) {
      // Fail open -- keep showing the last good frame, just flag staleness in the footer.
      setLastError(err instanceof Error ? err.message : "fetch failed");
    }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, REFRESH_MS);
    return () => clearInterval(id);
  }, [refresh]);

  return (
    <main className="h-screen w-full overflow-y-auto" style={{ fontFamily: "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif" }}>
      <div className="mx-auto flex max-w-5xl flex-col gap-10 px-5 py-12 sm:px-8 sm:py-16">
        <PresenceHeader presence={view.presence} />

        <div className="grid grid-cols-1 gap-10 lg:grid-cols-[1.3fr_1fr] lg:items-start">
          <ActivityFeed events={view.activity} nowMs={nowMs} />
          <div className="flex flex-col gap-10">
            <MoneyView presence={view.presence} />
            <WantsCards wants={view.wants} />
            <ThisWeekCard items={view.thisWeek} />
          </div>
        </div>

        <footer className="border-t pt-4 text-xs" style={{ borderColor: "var(--border)", color: "var(--text-4)" }}>
          {lastError
            ? `Last refresh failed (${lastError}) — showing last good data`
            : lastOkAt
              ? `Synced ${lastOkAt.toLocaleTimeString()} · refreshes every 20s`
              : "Loading…"}
        </footer>
      </div>
    </main>
  );
}

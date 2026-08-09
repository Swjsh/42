"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { Activity, DollarSign, HandHeart, ListChecks, LineChart } from "lucide-react";
import PresenceHeader from "@/components/gamma/PresenceHeader";
import ActivityFeed from "@/components/gamma/ActivityFeed";
import MoneyView from "@/components/gamma/MoneyView";
import WantsCards from "@/components/gamma/WantsCards";
import ThisWeekCard from "@/components/gamma/ThisWeekCard";
import Tile from "@/components/gamma/Tile";
import GammaPresence from "@/components/gamma/GammaPresence";
import MarketChart from "@/components/gamma/MarketChart";
import type { GammaAppView } from "@/lib/gamma-app-types";

const REFRESH_MS = 20_000;

const EMPTY_VIEW: GammaAppView = {
  fetchedAt: new Date(0).toISOString(),
  presence: null,
  activity: [],
  wants: [],
  thisWeek: [],
};

async function fetcher(url: string): Promise<GammaAppView> {
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return (await res.json()) as GammaAppView;
}

function pnlTone(headline: string | undefined): string {
  if (!headline) return "var(--text-2)";
  if (headline.includes("net +")) return "var(--up)";
  if (headline.includes("net -")) return "var(--down)";
  return "var(--text-2)";
}

function SkeletonTile({ label }: { label: string }) {
  return (
    <div
      className="flex items-center gap-3 overflow-hidden rounded-[var(--radius-lg)] border px-4"
      style={{ background: "var(--bg-card)", borderColor: "var(--border)", minHeight: 52 }}
    >
      <div className="skeleton-bar h-4 w-4 shrink-0 rounded-full" />
      <div className="skeleton-bar h-3 w-24 shrink-0" />
      <span className="sr-only">{label} loading</span>
      <div className="skeleton-bar ml-auto h-3 w-32 shrink-0" />
    </div>
  );
}

/**
 * THE GAMMA APP -- Gamma's one true presence surface (2026-08-09 redesign
 * pass: live quote, chart + trade narration, talk-to-Gamma, per-arm P&L).
 * Not a metrics wall: a colleague's status page. Sections in order: presence
 * header (identity + live state + first-person "what I'm doing right now" +
 * the live SPY quote, always expanded), then a real-time pairing of Gamma's
 * own presence/chat unit (self-fetching, wired to the live gamma-companion
 * server) next to the SPY chart (real bars + real trade markers + hover
 * narration -- "Gamma pointing at the chart"), then the original four
 * collapsible Tiles: live activity (centerpiece, capped to 10, open by
 * default), money (real per-arm progress bars, open by default), wants
 * (closed by default), this week (closed by default). Polls /api/gamma
 * every 20s via SWR (refreshInterval + keepPreviousData) -- unchanged data
 * never re-renders/re-animates, an open tile never re-collapses on a poll
 * tick, scroll position never jumps.
 */
export default function GammaAppPage() {
  const [nowMs, setNowMs] = useState<number>(() => Date.now());
  const { data, error, isValidating } = useSWR<GammaAppView>("/api/gamma", fetcher, {
    refreshInterval: REFRESH_MS,
    keepPreviousData: true,
  });

  const hasLoaded = data !== undefined;
  const view = data ?? EMPTY_VIEW;

  // Tick the "relative time" clock independently of the data poll, so
  // "3m ago" labels keep advancing between fetches without touching `view`.
  useEffect(() => {
    const id = setInterval(() => setNowMs(Date.now()), 15_000);
    return () => clearInterval(id);
  }, []);

  const [lastOkAt, setLastOkAt] = useState<Date | null>(null);
  useEffect(() => {
    if (data) setLastOkAt(new Date());
  }, [data]);

  return (
    <main className="gamma-app h-screen w-full overflow-y-auto">
      <div className="mx-auto flex max-w-[1240px] flex-col gap-8 px-5 py-12 sm:px-8 sm:py-16">
        <PresenceHeader presence={view.presence} />

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.6fr)] lg:items-start">
          <GammaPresence />
          <Tile
            id="chart"
            icon={LineChart}
            title="Chart"
            defaultOpen
            summary="SPY 5m + real fills"
          >
            <MarketChart />
          </Tile>
        </div>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] lg:items-start">
          {hasLoaded ? (
            <Tile
              id="activity"
              icon={Activity}
              title="Live activity"
              defaultOpen
              badge={{ text: `${view.activity.length} today` }}
              summary={view.activity[0]?.headline ?? "—"}
            >
              <ActivityFeed events={view.activity} nowMs={nowMs} />
            </Tile>
          ) : (
            <SkeletonTile label="Live activity" />
          )}

          <div className="flex flex-col gap-6">
            {hasLoaded ? (
              <Tile
                id="money"
                icon={DollarSign}
                title="Money"
                defaultOpen
                summary={
                  <span style={{ color: pnlTone(view.presence?.tape_headline) }}>
                    {view.presence?.tape_headline ?? "—"}
                  </span>
                }
              >
                <MoneyView presence={view.presence} />
              </Tile>
            ) : (
              <SkeletonTile label="Money" />
            )}

            {hasLoaded ? (
              <Tile
                id="wants"
                icon={HandHeart}
                title="I want"
                defaultOpen={false}
                badge={{ text: `${view.wants.length} open` }}
                summary={view.wants[0]?.text ?? "—"}
              >
                <WantsCards wants={view.wants} />
              </Tile>
            ) : (
              <SkeletonTile label="I want" />
            )}

            {hasLoaded ? (
              <Tile
                id="thisweek"
                icon={ListChecks}
                title="This week"
                defaultOpen={false}
                badge={{ text: `${view.thisWeek.length} queued` }}
                summary={view.thisWeek[0]?.text ?? "—"}
              >
                <ThisWeekCard items={view.thisWeek} />
              </Tile>
            ) : (
              <SkeletonTile label="This week" />
            )}
          </div>
        </div>

        <footer className="border-t pt-4 text-xs" style={{ borderColor: "var(--border)", color: "var(--text-4)" }}>
          {error
            ? `Last refresh failed (${error instanceof Error ? error.message : "fetch failed"}) — showing last good data`
            : lastOkAt
              ? `Synced ${lastOkAt.toLocaleTimeString()} · refreshes every 20s${isValidating ? " · syncing…" : ""}`
              : "Loading…"}
        </footer>
      </div>
    </main>
  );
}

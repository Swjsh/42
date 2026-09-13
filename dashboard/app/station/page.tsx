"use client";

import { Suspense, useCallback, useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import Link from "next/link";
import { Radio, ArrowLeft } from "lucide-react";
import BrainVitals, { type BrainVitalsData } from "@/components/station/BrainVitals";
import IdeaCard, { type CardAction } from "@/components/station/IdeaCard";
import TalkToGamma from "@/components/station/TalkToGamma";
import type { StationIdeaCard, StationPresence } from "@/lib/station";

interface StationApiResponse {
  fetched_at: string;
  ideas: { cards: StationIdeaCard[]; count: number };
  brief: { text: string; mtime_ms: number | null };
  brainVitals: BrainVitalsData;
  presence: StationPresence | null;
}

const fetcher = (url: string): Promise<StationApiResponse> =>
  fetch(url, { cache: "no-store" }).then((r) => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  });

function StationView() {
  const searchParams = useSearchParams();
  const kiosk = searchParams.get("kiosk") === "1";
  // Interactive viewing polls fast (J might just clicked a button); a TV
  // nobody is touching polls slower (amendments 2 + 4, reconciled: kiosk = a
  // read-only glance surface, not a live control panel).
  const refreshMs = kiosk ? 60_000 : 10_000;

  const { data, error, isValidating } = useSWR<StationApiResponse>("/api/station", fetcher, {
    refreshInterval: refreshMs,
    keepPreviousData: true,
  });

  const [actionError, setActionError] = useState<string | null>(null);

  const onAction = useCallback(async (cardId: string, action: CardAction, note: string) => {
    const res = await fetch("/api/station/action", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ card_id: cardId, action, note }),
    });
    const body = await res.json().catch(() => null);
    if (!res.ok || !body?.ok) {
      const msg = body?.error || `HTTP ${res.status}`;
      setActionError(msg);
      throw new Error(msg);
    }
  }, []);

  const cards = data?.ideas.cards ?? [];
  const sortedCards = [...cards].reverse(); // newest first

  return (
    <main className="mx-auto min-h-screen max-w-5xl px-5 py-6 sm:px-8">
      {!kiosk && (
        <div className="mb-4 flex items-center justify-between">
          <Link href="/" className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
            <ArrowLeft className="size-4" />
            Home
          </Link>
          <p className="text-xs text-muted-foreground">
            {error
              ? `Refresh failed (${error instanceof Error ? error.message : "fetch failed"})`
              : data
                ? `Synced ${new Date(data.fetched_at).toLocaleTimeString()}${isValidating ? " -- syncing..." : ""}`
                : "Loading..."}
          </p>
        </div>
      )}

      <div className="mb-5 flex items-center gap-2">
        <Radio className="size-5 text-foreground" />
        <h1 className="text-xl font-semibold text-foreground">Gamma's Station</h1>
        {data?.presence && (
          <span className="ml-auto text-xs text-muted-foreground">
            {data.presence.present ? "J is here" : "J is away"} ({Math.round(data.presence.idle_s)}s idle)
          </span>
        )}
      </div>

      {data && (
        <div className="flex flex-col gap-5">
          <BrainVitals data={data.brainVitals} />

          <div className="rounded-lg border border-border bg-card p-4">
            <p className="mb-1 text-sm font-semibold text-foreground">Latest brief</p>
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">
              {data.brief.text || "NO DATA -- no brief written yet"}
            </p>
          </div>

          <div>
            <p className="mb-2 text-sm font-semibold text-foreground">
              Ideas board ({data.ideas.count})
            </p>
            {actionError && <p className="mb-2 text-xs text-destructive">{actionError}</p>}
            {sortedCards.length === 0 ? (
              <p className="text-sm text-muted-foreground">NO DATA -- board is empty</p>
            ) : (
              <div className="space-y-2">
                {sortedCards.map((c) => (
                  <IdeaCard key={c.id} card={c} kiosk={kiosk} onAction={onAction} />
                ))}
              </div>
            )}
          </div>

          {!kiosk && <TalkToGamma />}
        </div>
      )}
    </main>
  );
}

export default function StationPage() {
  return (
    <Suspense fallback={<main className="p-8 text-sm text-muted-foreground">Loading Station...</main>}>
      <StationView />
    </Suspense>
  );
}

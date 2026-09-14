"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import Link from "next/link";
import { Radio, ArrowLeft } from "lucide-react";
import BrainVitals, { type BrainVitalsData } from "@/components/station/BrainVitals";
import IdeaCard, { type CardAction } from "@/components/station/IdeaCard";
import TalkToGamma from "@/components/station/TalkToGamma";
import type { StationFace, StationIdeaCard, StationPresence, TvCapability } from "@/lib/station";
import type { BlockedItem } from "@/lib/hq";
import { probeWebGl } from "@/lib/webgl-probe";
import { useKioskWatchdog, kioskErrorRetry } from "@/lib/useKioskWatchdog";
// timeAgoText has zero three.js dependency by design (see its own file's
// header comment: "can be imported from the 2D fallback too") -- reused
// here rather than re-implementing the same "3m ago" formatter a third time.
import { timeAgoText } from "@/components/hq/palette";

const BLOCKED_SOURCE_LABEL: Record<string, string> = {
  discord: "Discord",
  conductor_proposal: "Proposal",
  queue_escalation: "Escalation",
};

interface StationApiResponse {
  fetched_at: string;
  ideas: { cards: StationIdeaCard[]; count: number };
  brief: { text: string; mtime_ms: number | null };
  brainVitals: BrainVitalsData;
  presence: StationPresence | null;
  tvProbe: TvCapability | null;
  face: StationFace | null;
  build_id: string | null;
  blocked: BlockedItem[];
}

const fetcher = (url: string): Promise<StationApiResponse> =>
  fetch(url, { cache: "no-store" }).then((r) => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  });

function StationView() {
  const searchParams = useSearchParams();
  // J (2026-09-13): the TV's address is just http://<pc-lan-ip>/station. Any view reached through the
  // LAN address (i.e. via station_serve.py, never localhost) is the kiosk glance surface; the query
  // string still works. Decided after mount so the server-rendered HTML never mismatches on hydration.
  const [lanKiosk, setLanKiosk] = useState(false);
  useEffect(() => {
    const host = window.location.hostname;
    setLanKiosk(!(host === "localhost" || host === "127.0.0.1" || host === "::1"));
  }, []);
  const kiosk = searchParams.get("kiosk") === "1" || lanKiosk;
  // Interactive viewing polls fast (J might just clicked a button); a TV
  // nobody is touching polls slower (amendments 2 + 4, reconciled: kiosk = a
  // read-only glance surface, not a live control panel).
  const refreshMs = kiosk ? 60_000 : 10_000;

  const { data, error, isValidating } = useSWR<StationApiResponse>("/api/station", fetcher, {
    refreshInterval: refreshMs,
    keepPreviousData: true,
    onErrorRetry: kioskErrorRetry,
  });

  // Liveness watchdog (kiosk only) -- see lib/useKioskWatchdog.ts.
  useKioskWatchdog("/api/station", kiosk, data?.fetched_at);

  // The TV answers the WebGL question itself (J 2026-09-13: "typing in the TV is a
  // pain"): once per LAN page load, probe WebGL1/2 + fps and report it to
  // /api/station/tv-probe (GET -- the LAN page server forwards GET/HEAD only).
  useEffect(() => {
    if (!lanKiosk) return;
    let cancelled = false;
    probeWebGl()
      .then((r) => {
        if (cancelled) return;
        const q = new URLSearchParams({
          webgl1: r.webgl1 ? "1" : "0",
          webgl2: r.webgl2 ? "1" : "0",
          fps: String(r.fps),
          w: String(r.width),
          h: String(r.height),
          dpr: String(r.dpr),
          gl: r.renderer,
          ua: r.ua,
        });
        return fetch(`/api/station/tv-probe?${q.toString()}`, { cache: "no-store" });
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [lanKiosk]);

  // Follow face.json: when the configured TV path differs from this page, go there.
  // Lets the face flip (/station -> /hq) with a one-line file edit, no remote typing.
  useEffect(() => {
    const target = data?.face?.tv_path;
    if (!lanKiosk || !target || target === window.location.pathname) return;
    window.location.assign(target);
  }, [lanKiosk, data?.face?.tv_path]);

  // A rebuild lands on the TV unattended: reload when the server's build id changes
  // from the one this page first saw (kiosk only -- never yank a page J is typing in).
  const firstBuildId = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    const id = data?.build_id;
    if (id === undefined) return;
    if (firstBuildId.current === undefined) {
      firstBuildId.current = id;
      return;
    }
    if (kiosk && id && firstBuildId.current && id !== firstBuildId.current) window.location.reload();
  }, [kiosk, data?.build_id]);

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

      {data?.tvProbe && (
        <p className="mb-3 text-xs text-muted-foreground">
          TV browser: WebGL2 {data.tvProbe.webgl2 ? "OK" : "NOT AVAILABLE"} · WebGL1{" "}
          {data.tvProbe.webgl1 ? "OK" : "NOT AVAILABLE"} · {data.tvProbe.fps} fps · {data.tvProbe.width}x
          {data.tvProbe.height} @{data.tvProbe.dpr}x · {/tizen/i.test(data.tvProbe.ua) ? "Tizen" : data.tvProbe.ua.slice(0, 40)}
          {data.tvProbe.renderer ? ` · ${data.tvProbe.renderer.slice(0, 60)}` : ""} · reported {data.tvProbe.ts_et}
        </p>
      )}

      {data && (
        <div className="flex flex-col gap-5">
          <BrainVitals data={data.brainVitals} />

          <div className="rounded-lg border border-border bg-card p-4">
            <p className="mb-1 text-sm font-semibold text-foreground">Latest brief</p>
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">
              {data.brief.text || "NO DATA -- no brief written yet"}
            </p>
          </div>

          {/* NEEDS-J card (Company Mode step 7, 2026-09-13) -- the /hq HUD's
              matching section; hidden entirely when nothing's blocked. Same
              read-only aggregator (lib/hq.ts#readBlocked) as /api/hq. */}
          {data.blocked.length > 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/15 p-4">
              <p className="mb-2 text-sm font-semibold text-amber-400">
                NEEDS J ({data.blocked.length})
              </p>
              <div className="space-y-1.5">
                {data.blocked.slice(0, 3).map((item, i) => (
                  <p key={`${item.source}-${item.ts ?? i}`} className="text-xs text-amber-200/90">
                    <span className="font-semibold text-amber-400">[{BLOCKED_SOURCE_LABEL[item.source] ?? item.source}]</span>{" "}
                    {item.text} <span className="text-amber-200/60">&middot; {timeAgoText(item.ts)}</span>
                  </p>
                ))}
              </div>
            </div>
          )}

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

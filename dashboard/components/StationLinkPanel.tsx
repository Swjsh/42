"use client";

import Link from "next/link";
import useSWR from "swr";

// Compact "Gamma Station" panel/link for the home page (interactivity
// amendment, 2026-09-13: "a face for gamma... plus a compact panel/link on
// the home page"). Mirrors LiveWatchPanel/KitchenPanel's retro terminal
// palette so it reads as a sibling panel, not a bolted-on card. Polls the
// SAME /api/station route the full /station page uses (10s here is fine --
// this is a glance-only summary, not the interactive surface).
const MONO = "'JetBrains Mono','IBM Plex Mono',ui-monospace,Menlo,monospace";
const G = {
  card: "rgba(4,18,9,0.96)",
  border: "rgba(0,180,70,0.18)",
  green: "#00d46a",
  yellow: "#ffc340",
  dim: "#2a4a35",
  label: "#3d6b4d",
  text: "#d8f0e0",
  textBright: "#edfaef",
};

interface StationSummary {
  ideas: { count: number };
  brainVitals: { mode: string; lastRow: { status: string } | null };
}

const fetcher = (url: string): Promise<StationSummary> => fetch(url, { cache: "no-store" }).then((r) => r.json());

export default function StationLinkPanel() {
  const { data } = useSWR<StationSummary>("/api/station", fetcher, { refreshInterval: 15_000 });
  const status = data?.brainVitals.lastRow?.status ?? null;
  const dot = status === "ok" ? G.green : status === "error" ? "#ff4455" : G.yellow;

  return (
    <Link
      href="/station"
      className="block rounded-md p-2.5 text-[11px] transition-colors hover:brightness-110"
      style={{ background: G.card, border: `1px solid ${G.border}`, fontFamily: MONO, color: G.text }}
    >
      <div className="flex items-center gap-1.5">
        <span className="inline-block size-1.5 rounded-full" style={{ background: dot }} />
        <span style={{ color: G.textBright, fontWeight: 700, letterSpacing: "0.05em" }}>GAMMA STATION</span>
      </div>
      <div className="mt-1" style={{ color: G.label }}>
        {data ? `${data.ideas.count} ideas · mode ${data.brainVitals.mode}` : "loading..."}
      </div>
    </Link>
  );
}

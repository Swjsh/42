"use client";
import useSWR from "swr";

/** Loose payload type: the cockpit payload is produced by setup/scripts/gamma_home.py.
 *  Components narrow the sections they use; everything is optional and may be missing. */
export type CockpitPayload = Record<string, any> & {
  generated_et?: string;
  built_at_et?: string;
  today?: string;
};

const fetcher = async (url: string) => {
  const r = await fetch(url, { cache: "no-store" });
  if (!r.ok) throw new Error(`${url} -> ${r.status}`);
  return (await r.json()) as CockpitPayload;
};

/** One source of truth for every cockpit component: /api/cockpit, refreshed every 30 s. */
export function useCockpit() {
  const { data, error, isLoading, mutate } = useSWR<CockpitPayload>("/api/cockpit", fetcher, {
    refreshInterval: 30_000,
    revalidateOnFocus: true,
  });
  return { data, error, isLoading, refresh: mutate };
}

/** Companion (127.0.0.1:4317) is reached through the same-origin proxy /companion/*. */
export const COMPANION = "/companion";

/** Human age from an ISO stamp; "NO DATA" when absent. */
export function ageLabel(iso?: string | null): string {
  if (!iso) return "NO DATA";
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return "NO DATA";
  const m = Math.max(0, Math.round((Date.now() - t) / 60000));
  if (m < 1) return "just now";
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} h ago`;
  return `${Math.round(h / 24)} d ago`;
}

export function fmtUsd(n?: number | null, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "NO DATA";
  const sign = n < 0 ? "-" : "";
  return `${sign}$${Math.abs(n).toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

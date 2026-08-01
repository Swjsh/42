"use client";

import useSWR from "swr";
import Office from "@/components/Office";
import AutoresearchPanel from "@/components/AutoresearchPanel";
import KitchenPanel from "@/components/KitchenPanel";
import LiveWatchPanel from "@/components/LiveWatchPanel";
import type { KitchenStatus } from "@/lib/state";

interface StatePayload {
  kitchenStatus?: KitchenStatus | null;
}

const fetcher = (url: string): Promise<unknown> =>
  fetch(url, { cache: "no-store" }).then((r) => r.json());

export default function Page() {
  const { data } = useSWR("/api/state", fetcher, {
    refreshInterval: 3000,
    revalidateOnFocus: true,
  });

  const kitchen = (data as StatePayload | undefined)?.kitchenStatus ?? null;

  return (
    <main className="flex h-screen overflow-hidden relative">
      <div className="w-[220px] flex-shrink-0 flex flex-col min-h-0 p-3 gap-3">
        <LiveWatchPanel />
        <AutoresearchPanel />
      </div>
      <div className="flex-1 min-h-0 p-3 pl-0 flex items-center justify-center">
        <Office data={data} />
      </div>
      <div className="w-[200px] flex-shrink-0 flex flex-col min-h-0 p-3 pl-0">
        <KitchenPanel kitchen={kitchen} />
      </div>
    </main>
  );
}

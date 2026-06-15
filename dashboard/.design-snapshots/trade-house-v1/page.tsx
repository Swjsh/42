"use client";

import useSWR from "swr";
import Office from "@/components/Office";
import AutoresearchPanel from "@/components/AutoresearchPanel";

const fetcher = (url: string) =>
  fetch(url, { cache: "no-store" }).then((r) => r.json());

export default function Page() {
  const { data } = useSWR("/api/state", fetcher, {
    refreshInterval: 3000,
    revalidateOnFocus: true,
  });

  return (
    <main className="flex h-screen overflow-hidden">
      <div className="w-[420px] flex-shrink-0 flex flex-col min-h-0 p-3">
        <AutoresearchPanel />
      </div>
      <div className="flex-1 min-h-0 p-3 pl-0 flex items-center justify-center">
        <Office data={data} />
      </div>
    </main>
  );
}

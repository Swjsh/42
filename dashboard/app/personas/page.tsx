"use client";

import React from "react";
import useSWR from "swr";
import PersonasDesk, { type PersonasBoard } from "@/components/PersonasDesk";

const fetcher = (url: string): Promise<PersonasBoard> =>
  fetch(url, { cache: "no-store" }).then((r) => r.json() as Promise<PersonasBoard>);

const LOADING_STYLE: React.CSSProperties = {
  minHeight: "100vh",
  background: "#040806",
  color: "#7ee0a8",
  display: "grid",
  placeItems: "center",
  fontFamily: "var(--font-jetbrains-mono), monospace",
  fontSize: 12,
  letterSpacing: "0.18em",
};

export default function PersonasPage(): React.JSX.Element {
  const { data, error, isLoading } = useSWR<PersonasBoard>("/api/personas", fetcher, {
    refreshInterval: 10000,
    revalidateOnFocus: true,
  });

  if (isLoading || !data) {
    return (
      <main style={LOADING_STYLE}>
        {error ? `FETCH ERROR · ${String(error)}` : "BOOTING COMMAND DECK…"}
      </main>
    );
  }

  return <PersonasDesk data={data} />;
}

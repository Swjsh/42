"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import type { HqApiResponse } from "@/components/hq/types";
import HqFallback from "@/components/hq/HqFallback";
import Hud from "@/components/hq/Hud";
import CanvasRoot from "@/components/hq/CanvasRoot";

const fetcher = (url: string): Promise<HqApiResponse> =>
  fetch(url, { cache: "no-store" }).then((r) => {
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  });

function HqView() {
  const searchParams = useSearchParams();

  // Same convention as /station: any view reached through the LAN address
  // (not localhost) is the kiosk glance surface, decided after mount so the
  // server-rendered HTML never mismatches on hydration.
  const [lanKiosk, setLanKiosk] = useState(false);
  useEffect(() => {
    const host = window.location.hostname;
    setLanKiosk(!(host === "localhost" || host === "127.0.0.1" || host === "::1"));
  }, []);
  const kiosk = searchParams.get("kiosk") === "1" || lanKiosk;
  const refreshMs = kiosk ? 60_000 : 15_000;

  const { data, error, isValidating } = useSWR<HqApiResponse>("/api/hq", fetcher, {
    refreshInterval: refreshMs,
    keepPreviousData: true,
  });

  // Follow face.json: when the configured TV path differs from this page, go
  // there. Lets the face flip (/hq -> /station) with a one-line file edit.
  useEffect(() => {
    const target = data?.face?.tv_path;
    if (!lanKiosk || !target || target === window.location.pathname) return;
    window.location.assign(target);
  }, [lanKiosk, data?.face?.tv_path]);

  // A rebuild lands on the TV unattended: reload when the server's build id
  // changes from the one this page first saw (kiosk only).
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

  // WebGL2 gate -- decided after mount, never assumed. null = still checking
  // (brief loading state), false = HqFallback, true = mount the Canvas.
  const [webgl2, setWebgl2] = useState<boolean | null>(null);
  useEffect(() => {
    try {
      const canvas = document.createElement("canvas");
      setWebgl2(!!canvas.getContext("webgl2"));
    } catch {
      setWebgl2(false);
    }
  }, []);

  const [reducedMotion, setReducedMotion] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const update = () => setReducedMotion(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  return (
    <div style={{ position: "fixed", inset: 0, overflow: "hidden", background: "#03040a" }}>
      {webgl2 === false ? (
        <HqFallback data={data} error={error} />
      ) : webgl2 === true ? (
        <>
          <CanvasRoot data={data} reducedMotion={reducedMotion} lanKiosk={lanKiosk} />
          <Hud data={data} error={error} kiosk={kiosk} isValidating={isValidating} />
        </>
      ) : (
        <div style={{ color: "#7f93b0", padding: 24, fontFamily: "system-ui, sans-serif" }}>
          Loading Gamma HQ...
        </div>
      )}
    </div>
  );
}

export default function HqPage() {
  return (
    <Suspense fallback={<div style={{ padding: 24, color: "#7f93b0", background: "#03040a" }}>Loading Gamma HQ...</div>}>
      <HqView />
    </Suspense>
  );
}

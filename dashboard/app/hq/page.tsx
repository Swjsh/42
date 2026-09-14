"use client";

import { Suspense, useEffect, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { useSearchParams } from "next/navigation";
import useSWR from "swr";
import type { HqApiResponse } from "@/components/hq/types";
import HqFallback from "@/components/hq/HqFallback";
import Hud from "@/components/hq/Hud";
import CanvasRoot from "@/components/hq/CanvasRoot";
import UltraCanvasRoot from "@/components/hq/UltraCanvasRoot";
import LoadingOverlay from "@/components/hq/LoadingOverlay";
import { useKioskWatchdog, kioskErrorRetry } from "@/lib/useKioskWatchdog";
import { useMotionEvents } from "@/lib/useMotionEvents";
import { getFirstFrameRendered, subscribeFirstFrame } from "@/lib/hq-first-frame";

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
    onErrorRetry: kioskErrorRetry,
  });

  // Liveness watchdog (kiosk only): a frozen /hq is a frozen board on the
  // wall forever -- see lib/useKioskWatchdog.ts for the full rationale
  // (2026-09-13: the TV went silent for an unknown reason, first suspect a
  // dashboard-restart poll landing during the brief downtime window plus
  // SWR's own uncapped exponential backoff -- kioskErrorRetry above
  // addresses that half, this hook is the belt-and-suspenders other half).
  useKioskWatchdog("/api/hq", kiosk, data?.fetched_at);

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

  // Tier (HQ v4 ultra-tier plumbing, 2026-09-13, J: "dont use my tv as a
  // constraint im fine showing it on my monitor with epic graphics"):
  // ?tier=ultra|tv overrides; otherwise default ultra UNLESS the UA is the
  // real TV (SMART-TV/Tizen), which always gets the cheap tier regardless
  // of query string -- decided after mount, same SSR-mismatch-avoidance
  // reasoning as webgl2/lanKiosk above. `navigator.userAgent` is
  // client-only, so this can never be "proven" via a server-side curl --
  // it's a per-browser decision, verified by code path + a screenshot once
  // gaming mode is off, not by hitting the API.
  const [tier, setTier] = useState<"ultra" | "tv" | null>(null);
  useEffect(() => {
    const q = searchParams.get("tier");
    if (q === "ultra" || q === "tv") {
      setTier(q);
      return;
    }
    const isRealTv = /SMART-TV|Tizen/i.test(navigator.userAgent);
    setTier(isRealTv ? "tv" : "ultra");
  }, [searchParams]);

  // "They need MEANING" (J 2026-09-13): a small log of what real event just
  // caused an agent to move -- see lib/useMotionEvents.ts. Computed here
  // (not inside Scene.tsx) because Hud.tsx, the only consumer, lives
  // outside the <Canvas>.
  const motionEvents = useMotionEvents(data);

  // UX-1 U4 (2026-09-14): cross-Canvas-boundary "did a real frame paint
  // yet" signal -- see lib/hq-first-frame.ts's own header for why this
  // can't just be a prop. `() => false` is the correct SSR snapshot (this
  // store is only ever written from inside a mounted client-side <Canvas>,
  // same reasoning as the sibling hq-live-perf.ts store already uses).
  const firstFrameRendered = useSyncExternalStore(subscribeFirstFrame, getFirstFrameRendered, () => false);

  // World pass A REAL bug fix (2026-09-13): `data` gets a BRAND NEW object
  // reference every SWR poll (refreshInterval 15-60s) even when nothing the
  // 3D scene cares about changed -- `fetched_at`/`perf`/`perfOther` carry
  // their own timestamps that update every poll regardless. A fresh `data`
  // reference cascades a full re-render of the ENTIRE Scene.tsx tree (every
  // StationModule/Agent/Corridor/PersonaModule/BrainCore/EffectsStack/
  // PmremEnvironment/~20 <Html> instances), and this session found TWO
  // confirmed cases (GodRays inside EffectsStack.tsx, Environment inside
  // PmremEnvironment.tsx -- both now React.memo'd) where a drei/
  // postprocessing library component does expensive/stateful work in an
  // effect with NO dependency array, i.e. on every single render of its
  // parent, not just when ITS OWN props change. Mechanical bisection this
  // session confirmed the crash pattern is NOT a Pass-A regression (HEAD,
  // pre-Pass-A, shows the identical error) and specifically correlates with
  // the poll boundary, not initial load -- consistent with "re-render
  // cascade triggers a library-internal bug", not a mount/unmount race.
  // `sceneData` is a STABLE reference across polls whose payload (limited to
  // exactly the fields Scene.tsx and its descendants read) is unchanged --
  // an inclusion list, not an exclusion list, so a new API field Scene
  // never reads can't accidentally destabilize this by omission. Hud.tsx
  // keeps reading the RAW `data` (unchanged below) so "Synced HH:MM:SS"
  // and the perf line stay live -- only the Canvas-tree prop is stabilized.
  const sceneDataRef = useRef<HqApiResponse | undefined>(undefined);
  const sceneDataKeyRef = useRef<string>("");
  const sceneData = useMemo(() => {
    if (!data) return undefined;
    const key = JSON.stringify({
      mode: data.mode,
      presence: data.presence,
      brainVitalsUtil: data.brainVitals.gpu.util_pct,
      brainVitalsMem: [data.brainVitals.gpu.mem_used_mib, data.brainVitals.gpu.mem_total_mib],
      models: data.brainVitals.models,
      briefText: data.brief.text,
      briefMtime: data.brief.mtime_ms,
      sectors: data.sectors.rows,
      company: data.company,
      ideas: data.ideas.cards,
      blocked: data.blocked,
      // Pass B (2026-09-13): Scene.tsx now reads data.audit (company audit
      // badges on personas) -- included here per this memo's own
      // inclusion-list contract ("a new API field Scene never reads can't
      // accidentally destabilize this by omission" -- the inverse is also
      // true: a field Scene DOES read must be listed, or its reference
      // would stay stale across a real content change).
      audit: data.audit,
    });
    if (key === sceneDataKeyRef.current && sceneDataRef.current) return sceneDataRef.current;
    sceneDataKeyRef.current = key;
    sceneDataRef.current = data;
    return data;
  }, [data]);

  return (
    <div style={{ position: "fixed", inset: 0, overflow: "hidden", background: "#03040a" }}>
      {/* UX-1 U4 (2026-09-14): always mounted (any webgl2/tier state) so
          there is never a gap between the plain-text loading fallback below
          and a styled overlay -- ONE continuous covering layer from first
          paint until the scene is genuinely ready, "no black flash" in the
          literal sense of never showing raw unstyled text OR bare bg either.
          canvasMounted=false (webgl2 unresolved, or the false/fallback
          branch) just means "nothing to report progress on yet" -- the
          overlay's own safety timeout still applies once a Canvas DOES
          mount, see LoadingOverlay.tsx's own header. */}
      <LoadingOverlay
        canvasMounted={webgl2 === true && tier !== null}
        noCanvasComing={webgl2 === false}
        firstFrameRendered={firstFrameRendered}
      />
      {webgl2 === false ? (
        <HqFallback data={data} error={error} />
      ) : webgl2 === true && tier === "tv" ? (
        <>
          <CanvasRoot data={sceneData} reducedMotion={reducedMotion} lanKiosk={lanKiosk} kiosk={kiosk} />
          <Hud data={data} error={error} kiosk={kiosk} isValidating={isValidating} motionEvents={motionEvents} tier="tv" reducedMotion={reducedMotion} />
        </>
      ) : webgl2 === true && tier === "ultra" ? (
        <>
          <UltraCanvasRoot data={sceneData} reducedMotion={reducedMotion} kiosk={kiosk} />
          <Hud data={data} error={error} kiosk={kiosk} isValidating={isValidating} motionEvents={motionEvents} tier="ultra" reducedMotion={reducedMotion} />
        </>
      ) : (
        <div style={{ color: "#7f93b0", padding: 24, fontFamily: "system-ui, sans-serif" }}>
          Loading Gamma HQ...
        </div>
      )}
    </div>
  );
}

// UX-1 U4 (2026-09-14): this OUTERMOST Suspense boundary (required by
// useSearchParams() in the App Router) resolves BEFORE HqView -- and
// therefore LoadingOverlay -- ever mounts, so it can never show real
// progress (no component tree, no THREE.DefaultLoadingManager activity
// yet). Real-capture evidence this pass (ux1-u4-seq-1749.png-01..03) showed
// this exact fallback holding the screen for several real seconds on a
// cold kiosk browser start, THEN LoadingOverlay's own styled title+bar
// taking over -- a visible STYLE swap partway through the load, not a
// black flash, but not "one continuous experience" either. Reskinned to
// the same title treatment/background so the two stages read as one
// sequence, not two different loading screens.
const OUTER_FALLBACK = (
  <div
    style={{
      position: "fixed", inset: 0, background: "#03040a",
      display: "flex", alignItems: "center", justifyContent: "center",
      fontFamily: "system-ui, -apple-system, Segoe UI, Roboto, sans-serif",
    }}
  >
    <div style={{ color: "#dff3ff", fontSize: 40, fontWeight: 800, letterSpacing: 2, textShadow: "0 0 18px rgba(122,217,255,0.55)" }}>
      GAMMA HQ
    </div>
  </div>
);

export default function HqPage() {
  return (
    <Suspense fallback={OUTER_FALLBACK}>
      <HqView />
    </Suspense>
  );
}

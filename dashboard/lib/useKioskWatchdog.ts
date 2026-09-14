"use client";

import { useEffect, useRef } from "react";

const STALE_MS = 180_000;
const CHECK_INTERVAL_MS = 30_000;
const ERROR_RETRY_DELAY_MS = 10_000;

/**
 * Kiosk liveness watchdog (2026-09-13, HQ v3 -- the TV's /hq page went
 * silent at 20:38:15 ET with no error logged, right inside a dashboard
 * restart window; SWR's default exponential error backoff has no cap, so a
 * poll that happens to land during the few seconds a restart takes down the
 * server can balloon into a multi-minute-or-longer retry gap with nobody
 * there to hit reload). A TV kiosk page going quiet shows a frozen board on
 * the wall forever -- three defenses, active ONLY when `enabled` (kiosk):
 *
 *   (a) pass this module's onErrorRetry into useSWR (call site does this
 *       directly -- see app/hq/page.tsx / app/station/page.tsx) to cap SWR's
 *       own backoff at a constant 10s, unlimited retries.
 *   (b) this hook's 30s interval checks how long it's been since the last
 *       SUCCESSFUL fetch (the caller reports that via `hasData` flipping
 *       true whenever a new payload lands); past 180s, it probes `apiUrl`
 *       directly and reloads ONLY if that probe itself succeeds --
 *       reloading into a dead server would hand the browser its own error
 *       page, which has no retry loop of its own and would kill the page's
 *       JS for good.
 *   (c) a window 'error'/'unhandledrejection' listener runs the same
 *       probe-then-reload path after a 10s grace period, catching an
 *       uncaught render/runtime exception the poll loop itself wouldn't see.
 */
export function useKioskWatchdog(apiUrl: string, enabled: boolean, successSignal: unknown): void {
  const lastSuccessAt = useRef(Date.now());

  // `successSignal` must be a value that CHANGES on every successful poll
  // (e.g. the payload's own `fetched_at` string) -- NOT a plain `!!data`
  // boolean. With `keepPreviousData: true`, `data` stays truthy forever
  // after the first fetch even while later polls are failing, so a boolean
  // signal would update `lastSuccessAt` exactly once and never again,
  // silently defeating the whole staleness check.
  useEffect(() => {
    if (successSignal !== undefined && successSignal !== null) lastSuccessAt.current = Date.now();
  }, [successSignal]);

  useEffect(() => {
    if (!enabled) return;

    const probeThenReload = () => {
      fetch(apiUrl, { cache: "no-store" })
        .then((r) => {
          if (r.ok) window.location.reload();
        })
        .catch(() => undefined); // server still down -- next tick/listener tries again
    };

    const intervalId = window.setInterval(() => {
      if (Date.now() - lastSuccessAt.current > STALE_MS) probeThenReload();
    }, CHECK_INTERVAL_MS);

    const onWindowError = () => {
      window.setTimeout(probeThenReload, ERROR_RETRY_DELAY_MS);
    };
    window.addEventListener("error", onWindowError);
    window.addEventListener("unhandledrejection", onWindowError);

    return () => {
      window.clearInterval(intervalId);
      window.removeEventListener("error", onWindowError);
      window.removeEventListener("unhandledrejection", onWindowError);
    };
  }, [enabled, apiUrl]);
}

/** Constant-delay (10s), unlimited-retry SWR onErrorRetry -- caps the
 * default exponential backoff so a brief server restart never balloons the
 * retry gap. Pass directly as useSWR's `onErrorRetry` option. */
export function kioskErrorRetry(
  _err: unknown,
  _key: string,
  _config: unknown,
  revalidate: (opts: { retryCount: number }) => void,
  { retryCount }: { retryCount: number },
): void {
  window.setTimeout(() => revalidate({ retryCount }), 10_000);
}

"use client";

import { useEffect, useState } from "react";

/** Shape is a reasonable assumption, not yet confirmed against a real file
 * (the curator agent downloading dashboard/public/hq-assets/ was still
 * running as of this pass) -- narrow/adjust on first contact with the real
 * manifest.json rather than trusting this blind. Each character/prop entry
 * names a GLB path (served statically from /hq-assets/... since it lives
 * under public/) plus the clip names actually present in that GLB, so
 * callers never hardcode a clip name that might not exist in the real
 * download. */
export interface HqAssetManifest {
  characters?: Array<{
    id: string;
    glb: string; // e.g. "/hq-assets/quaternius/character-a.glb"
    clips?: { idle?: string; walk?: string; sit?: string; alert?: string };
    scale?: number;
  }>;
  props?: Array<{ id: string; glb: string; scale?: number }>;
  hdri?: { file: string } | null;
}

let cached: HqAssetManifest | null | undefined; // undefined = not fetched yet

/** Fetches the STATIC public file directly (no API route -- it's served
 * from public/hq-assets/manifest.json like any other static asset), caches
 * the result for the page's lifetime, and fails open to null on a 404 or
 * parse error -- absent-manifest is the expected, common case (asset
 * download not finished / not yet approved), never an error to surface. */
export function useHqAssetManifest(): HqAssetManifest | null {
  const [manifest, setManifest] = useState<HqAssetManifest | null>(cached ?? null);

  useEffect(() => {
    if (cached !== undefined) return;
    let cancelled = false;
    fetch("/hq-assets/manifest.json", { cache: "no-store" })
      .then((r) => (r.ok ? r.json() : null))
      .catch(() => null)
      .then((m: HqAssetManifest | null) => {
        cached = m;
        if (!cancelled) setManifest(m);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return manifest;
}

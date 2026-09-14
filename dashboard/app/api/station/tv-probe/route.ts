import { NextResponse } from "next/server";
import { mkdir, rename, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { paths } from "@/lib/workspace";
import { nowEtStamp } from "@/lib/time";
import type { TvCapability } from "@/lib/station";
import { appendTvPerfRow } from "@/lib/hq";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const MAX_UA_LEN = 200;
const MAX_RENDERER_LEN = 120;

function flag(v: string | null): boolean {
  return v === "1" || v === "true";
}

function int(v: string | null, lo: number, hi: number): number {
  const n = Number.parseInt(v ?? "", 10);
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : 0;
}

function num(v: string | null, lo: number, hi: number, dflt: number): number {
  const n = Number.parseFloat(v ?? "");
  return Number.isFinite(n) ? Math.min(hi, Math.max(lo, n)) : dflt;
}

/** Printable ASCII only, clamped -- the value is shown on the face and written to disk. */
function text(v: string | null, max: number): string {
  return (v ?? "").replace(/[^\x20-\x7e]/g, "").slice(0, max);
}

/**
 * GET /api/station/tv-probe?page=station|hq&webgl1=1&webgl2=1&fps=58&calls=..&tris=..&w=1920&h=1080&dpr=1&gl=...&ua=...
 * The TV browser reports its own rendering capability/performance once per
 * page load of a LAN kiosk view. GET, not POST, because the LAN page server
 * (setup/scripts/station_serve.py) forwards GET/HEAD only.
 *
 * `page` defaults to "station" -- back-compat with the original probe
 * (app/station/page.tsx's probeWebGl): writes tv-capability.json exactly as
 * before, one small validated/clamped object, no free text beyond
 * printable-ASCII UA/renderer strings.
 *
 * `page=hq` (HQ v2, 2026-09-13, app/hq/page.tsx's <PerfReporter>) additionally
 * carries `calls`/`tris` -- r3f's own gl.info.render.calls/triangles -- and
 * does NOT touch tv-capability.json (the HQ page already knows it has
 * WebGL2; that capability file is /station's own canary result).
 *
 * EVERY report, regardless of page, also appends one line to tv-perf.jsonl
 * (capped at 200 lines, dashboard/lib/hq.ts#appendTvPerfRow) -- a unified
 * render-performance history across both kiosk faces. Never calls a model,
 * never reads a credential, never touches any other file.
 */
export async function GET(request: Request) {
  const q = new URL(request.url).searchParams;
  const page = text(q.get("page"), 16) || "station";
  const fps = int(q.get("fps"), 0, 480);
  const w = int(q.get("w"), 0, 16384);
  const h = int(q.get("h"), 0, 16384);
  const dpr = num(q.get("dpr"), 0.1, 8, 1);
  const ua = text(q.get("ua"), MAX_UA_LEN);

  if (page !== "hq") {
    const row: TvCapability = {
      ts_et: nowEtStamp(),
      webgl1: flag(q.get("webgl1")),
      webgl2: flag(q.get("webgl2")),
      fps, width: w, height: h, dpr,
      renderer: text(q.get("gl"), MAX_RENDERER_LEN),
      ua,
    };
    try {
      await mkdir(dirname(paths.tvCapability), { recursive: true });
      const tmp = `${paths.tvCapability}.tmp`;
      await writeFile(tmp, JSON.stringify(row, null, 2) + "\n", "utf-8");
      await rename(tmp, paths.tvCapability);
    } catch (e) {
      return NextResponse.json(
        { ok: false, error: `failed to write tv-capability.json: ${e instanceof Error ? e.message : String(e)}` },
        { status: 500 },
      );
    }
    await appendTvPerfRow({ ts_et: row.ts_et, page: "station", fps, calls: 0, tris: 0, w, h, dpr, ua }).catch(() => undefined);
    return NextResponse.json({ ok: true, saved: row }, { headers: { "Cache-Control": "no-store" } });
  }

  const ts_et = nowEtStamp();
  const calls = int(q.get("calls"), 0, 100_000);
  const tris = int(q.get("tris"), 0, 50_000_000);
  const rawDpr = num(q.get("rawDpr"), 0.1, 8, dpr);
  try {
    await appendTvPerfRow({ ts_et, page: "hq", fps, calls, tris, w, h, dpr, rawDpr, ua });
  } catch (e) {
    return NextResponse.json(
      { ok: false, error: `failed to write tv-perf.jsonl: ${e instanceof Error ? e.message : String(e)}` },
      { status: 500 },
    );
  }
  return NextResponse.json(
    { ok: true, saved: { ts_et, page: "hq", fps, calls, tris, w, h, dpr, rawDpr, ua } },
    { headers: { "Cache-Control": "no-store" } },
  );
}

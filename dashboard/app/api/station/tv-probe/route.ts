import { NextResponse } from "next/server";
import { mkdir, rename, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { paths } from "@/lib/workspace";
import { nowEtStamp } from "@/lib/time";
import type { TvCapability } from "@/lib/station";

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
 * GET /api/station/tv-probe?webgl1=1&webgl2=1&fps=58&w=1920&h=1080&dpr=1&gl=...&ua=...
 * The TV browser reports its own rendering capability once per page load of the
 * LAN kiosk view (app/station/page.tsx). GET, not POST, because the LAN page
 * server (setup/scripts/station_serve.py) forwards GET/HEAD only. The ONLY effect
 * is overwriting automation/state/station/tv-capability.json with one small
 * object -- every field validated and clamped, no free text beyond a
 * printable-ASCII user agent / renderer string. Never calls a model, never reads
 * a credential, never touches any other file.
 */
export async function GET(request: Request) {
  const q = new URL(request.url).searchParams;
  const row: TvCapability = {
    ts_et: nowEtStamp(),
    webgl1: flag(q.get("webgl1")),
    webgl2: flag(q.get("webgl2")),
    fps: int(q.get("fps"), 0, 480),
    width: int(q.get("w"), 0, 16384),
    height: int(q.get("h"), 0, 16384),
    dpr: num(q.get("dpr"), 0.1, 8, 1),
    renderer: text(q.get("gl"), MAX_RENDERER_LEN),
    ua: text(q.get("ua"), MAX_UA_LEN),
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

  return NextResponse.json({ ok: true, saved: row }, { headers: { "Cache-Control": "no-store" } });
}

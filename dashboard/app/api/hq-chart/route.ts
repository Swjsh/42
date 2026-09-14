import { NextResponse } from "next/server";
import { getHoloChartData } from "@/lib/hq-chart-data";

export const dynamic = "force-dynamic";
export const revalidate = 0;

/**
 * GET /api/hq-chart -- the holographic SPY chart's own data source
 * (components/hq/HoloChart.tsx). No user input is read anywhere on this
 * path (no searchParams, no body) and nothing under automation/state/ or
 * journal/ is ever written from here -- read-only, same contract as
 * /api/hq and /api/gamma-chart.
 *
 * lib/hq-chart-data.ts#getHoloChartData() already never throws (every
 * source it reads is independently fail-open, and the whole function is
 * itself wrapped) -- this route's own try/catch is a backstop only, mirror
 * of /api/hq/route.ts's own "belt and suspenders" GET() wrapper, so even an
 * unforeseen failure (e.g. JSON serialization) degrades to a 200 with an
 * honest `ok:false` + `error` body instead of a 500.
 */
export async function GET() {
  try {
    const data = await getHoloChartData();
    return NextResponse.json(data, { headers: { "Cache-Control": "no-store, max-age=0" } });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.error("[/api/hq-chart] GET() threw past getHoloChartData()'s own fail-open guard:", err);
    return NextResponse.json(
      {
        ok: false,
        error: `hq_chart_route_failed: ${message}`,
        session: { date: null, status: "no-data", label: "SPY · no local session data" },
        bars: [],
        priceRange: null,
        levels: [],
        lastClose: null,
        live: null,
        trades: [],
        generatedAt: new Date().toISOString(),
      },
      { status: 200, headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  }
}

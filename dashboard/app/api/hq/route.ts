import { NextResponse } from "next/server";
import {
  readIdeasBoard,
  readStationBrief,
  readStationConfig,
  readStationMode,
  readLedgerTail,
  readPresence,
  readPlannerSpeed,
  readGpuVitals,
  readOllamaPs,
  readFaceConfig,
  readBuildId,
} from "@/lib/station";
import {
  readSectorRows,
  readFuturesVerdict,
  readCryptoTwinTail,
  readKitchenSummary,
} from "@/lib/hq";

export const dynamic = "force-dynamic";
export const revalidate = 0;

/**
 * GET /api/hq -- everything the /hq three.js space-station page renders,
 * read server-side. Read-only: this route never writes anything (mirrors
 * /api/station/route.ts's own contract). No credential file is read here or
 * anywhere in lib/hq.ts.
 *
 * Reuses every existing /api/station reader verbatim (lib/station.ts) rather
 * than duplicating them -- the only new readers are lib/hq.ts's four
 * (sector_rows.py shell + 3 plain-file extras), all additive, zero new
 * producers per the HQ-visuals brief's own subtraction doctrine.
 */
export async function GET() {
  const [
    ideas,
    brief,
    config,
    mode,
    ledger,
    presence,
    plannerSpeed,
    gpu,
    models,
    sectors,
    futuresVerdict,
    cryptoTail,
    kitchen,
    face,
    buildId,
  ] = await Promise.all([
    readIdeasBoard(),
    readStationBrief(),
    readStationConfig(),
    readStationMode(),
    readLedgerTail(10),
    readPresence(),
    readPlannerSpeed(),
    readGpuVitals(),
    readOllamaPs(),
    readSectorRows(),
    readFuturesVerdict(),
    readCryptoTwinTail(),
    readKitchenSummary(),
    readFaceConfig(),
    readBuildId(),
  ]);

  const lastRow = ledger.length > 0 ? ledger[ledger.length - 1] : null;

  return NextResponse.json(
    {
      fetched_at: new Date().toISOString(),
      mode,
      presence,
      brainVitals: {
        model: config.model ?? null,
        gpu,
        models: models.models,
        modelsOk: models.ok,
        plannerSpeed,
        lastRow,
        fireTimeline: ledger,
      },
      ideas: { cards: ideas, count: ideas.length },
      brief: { text: brief.text, mtime_ms: brief.mtimeMs },
      sectors: { rows: sectors.rows, say: sectors.say },
      extras: {
        futures_verdict: futuresVerdict,
        crypto: { last_action: cryptoTail.last_action, last_ts: cryptoTail.last_ts },
        kitchen: {
          daemon_alive: kitchen.daemon_alive,
          idle: kitchen.idle,
          current_task_id: kitchen.current_task_id,
          failed_permanent: kitchen.failed_permanent,
        },
      },
      face,
      build_id: buildId,
    },
    { headers: { "Cache-Control": "no-store, max-age=0" } },
  );
}

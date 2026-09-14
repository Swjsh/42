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
  readHqBuildStatus,
} from "@/lib/station";
import {
  readSectorRows,
  readFuturesVerdict,
  readCryptoTwinTail,
  readKitchenSummary,
  readLatestHqPerf,
  readBlocked,
  readCompanyAudit,
  readTradingStatus,
  readCrewEvents,
  readSectorsSnapshot,
} from "@/lib/hq";
import { collectCompany, type PersonaState, type Handoff } from "@/lib/personas";
// INTERACT-2 (I1, 2026-09-14): per-desk real-work content -- see
// lib/desk-content.ts's own header for the fail-open contract per source.
import { readDesksSnapshot } from "@/lib/desk-content";
// PANEL-2 (2026-09-14): "is it running on my PC, or is this whole thing
// agents running on my PC?" -- see lib/hq-runtime.ts's own header for the
// full truth this establishes. Additive only.
import { readHqRuntime } from "@/lib/hq-runtime";
// PANEL-3 (2026-09-14): "make the LEARNING VISIBLE" (J's verbatim mandate)
// -- see lib/hq-learn.ts's own header for the 6 real source files this
// turns into the LEARN tab's rows. Additive only, 30s-cached internally.
import { readHqLearn } from "@/lib/hq-learn";

/** Unlike every other reader in this route's Promise.all, collectCompany()
 * has no internal try/catch (personas/route.ts's OWN top-level GET() is
 * what originally caught its errors) -- calling it bare here would let one
 * bad collector reject this route's whole Promise.all and 500 the ENTIRE
 * /api/hq payload, not just the company section. Wrapped so a company-data
 * failure degrades to empty arrays instead. */
async function safeCollectCompany(): Promise<{ personas: PersonaState[]; handoffs: Handoff[] }> {
  try {
    return await collectCompany();
  } catch (err) {
    // Failure honesty (2026-09-13 fix): this was a bare silent catch --
    // a real exception here degrades the whole roster to an empty array
    // with ZERO trace of why, which is exactly what let a genuine bug go
    // undiagnosed via curl alone. Logged with context now, never swallowed.
    console.error("[/api/hq] collectCompany() threw, roster degraded to empty:", err);
    return { personas: [], handoffs: [] };
  }
}

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
 *
 * UX-1 U7 (2026-09-14): CREW-2 saw one transient 500 in ~35 polls. Audited
 * every reader this Promise.all touches this pass -- lib/hq.ts (all 893
 * lines, every exported function), lib/station.ts (all, pre-U0), lib/
 * desk-content.ts (all 347 lines), and lib/personas.ts's collectCompany()
 * dependency graph end to end (collectScout/Coach/Pilot/Analyst/Chef/
 * Treasurer/GammaManager + computeHandoffs + every helper: fileExists/
 * mtimeISO/readText/readJson/readJsonlTail/dirListing/etLikeToIso/etHHMM) --
 * every fs/execFile call already sits inside its own try/catch, every
 * catch degrades to null/[]/a fail-open default, and every property access
 * on a freshly-JSON.parse'd value happens INSIDE that same try block (so
 * even a literal `null`/non-object JSON body -- valid JSON, `data.field`
 * throws a TypeError -- is still caught, not just a JSON.parse SyntaxError).
 * No un-caught throw found. UNVERIFIED beyond that: this audit could not
 * reproduce the original transient 500, so the specific mechanism CREW-2
 * saw is not confirmed fixed by a single named line -- what this pass adds
 * is the belt-and-suspenders backstop below, so "never 500 for a missing/
 * partial file" is a hard guarantee (any future regression, or a
 * Node/Next.js-internal edge case this audit didn't anticipate, degrades
 * to a 200 with an honest error marker) rather than resting on "we checked
 * every file we could find." Proof this pass: 200/200 over 60 polls
 * (`for i in $(seq 60); do curl -s -o NUL -w "%{http_code}\n" ...`).
 */
export async function GET() {
  try {
    return await buildHqResponse();
  } catch (err) {
    // The backstop itself -- NOT the expected path (every reader below is
    // independently fail-open per this function's own header audit). Logged
    // loudly with context (never a silent catch, per this codebase's own
    // standing failure-honesty rule) so a future occurrence is diagnosable
    // from the server's own stderr, not just "the roster went blank."
    console.error("[/api/hq] GET() threw past every reader's own fail-open guard -- backstop response returned, this should never happen:", err);
    return NextResponse.json(
      { error: "hq_route_failed", fetched_at: new Date().toISOString() },
      { status: 200, headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  }
}

async function buildHqResponse() {
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
    perfResult,
    company,
    blocked,
    audit,
    trading,
    crewEvents,
    desks,
    build,
    sectorsSnapshot,
    learn,
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
    readLatestHqPerf(),
    safeCollectCompany(),
    readBlocked(),
    readCompanyAudit(),
    // LIVE-1 item 5 (2026-09-14, coordinator-directed): trading status
    // strip -- read server-side only, never from the browser (this whole
    // route already is server-side; see lib/hq.ts#readTradingStatus for
    // the fail-open contract per source file).
    readTradingStatus(),
    // CREW-2 (roster) -- crew-events.jsonl, additive: feeds Hud.tsx's event
    // feed (R3) and (via lib/personas.ts's own separate read) the roster's
    // per-persona "last:" fallback. See lib/hq.ts#readCrewEvents.
    readCrewEvents(),
    // INTERACT-2 (I1) -- per-desk real-work content, additive.
    readDesksSnapshot(),
    // UX-1 U0 (2026-09-14) -- "is it working?" build instrument, additive.
    readHqBuildStatus(),
    // Coordinator-directed (2026-09-14, 17:2x ET) -- MODELS' hub wall panel
    // + LAYOUT's prop threading, additive. See lib/hq.ts#readSectorsSnapshot
    // for why this is named `sectorsSnapshot` and not `sectors` (the latter
    // already exists above, a different producer).
    readSectorsSnapshot(),
    // PANEL-3 (2026-09-14) -- "make the LEARNING VISIBLE" instrument,
    // additive. See lib/hq-learn.ts for the 6 real files this reads and the
    // freeze-aware (to 2026-10-30) "changed" text each row carries.
    readHqLearn(),
  ]);

  const lastRow = ledger.length > 0 ? ledger[ledger.length - 1] : null;

  // PANEL-2 (2026-09-14): sequential, not folded into the Promise.all above --
  // it depends on company.personas / config.model / models.models / gpu.ok,
  // all of which must already be resolved. Reuses those four results rather
  // than re-fetching any of them (see lib/hq-runtime.ts's own HqRuntimeInputs
  // doc comment); the only NEW read inside is a 30s-cached `tasklist` shell.
  const runtime = await readHqRuntime({
    personas: company.personas,
    brainModel: config.model ?? null,
    ollamaModelsLoaded: models.models.map((m) => m.name),
    gpuOk: gpu.ok,
  });

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
      perf: perfResult.perf,
      perfOther: perfResult.perfOther,
      company,
      blocked,
      audit,
      trading,
      // CREW-2 (roster) -- additive, see lib/hq.ts#readCrewEvents.
      crewEvents,
      // INTERACT-2 -- additive, see lib/desk-content.ts.
      desks,
      // UX-1 U0 (2026-09-14) -- additive, see lib/station.ts#readHqBuildStatus.
      build,
      // Coordinator-directed (2026-09-14) -- additive, see
      // lib/hq.ts#readSectorsSnapshot. Null until CREW-RIG's
      // sectors.json producer has fired at least once.
      sectorsSnapshot,
      // PANEL-2 (2026-09-14) -- additive, see lib/hq-runtime.ts. Answers "is
      // it running on my PC, or is this whole thing agents running on my
      // PC?" from measured process counts + per-role runtime classification,
      // never invented prose.
      runtime,
      // PANEL-3 (2026-09-14) -- additive, see lib/hq-learn.ts. What Gamma's
      // research board learned today and what changed because of it, from 6
      // real files only; fail-open (an `error` field appears only if every
      // per-source reader's own fail-open guard was somehow bypassed).
      learn,
      // I3: explicit alias for brief.mtime_ms -- surfaces the SAME real
      // mtime as a readable ISO string so the all-hands trigger has a
      // self-explanatory field name on the wire (brief.mtime_ms already
      // drives it; this adds no new read, just a derived rename).
      briefWrittenAt: brief.mtimeMs !== null ? new Date(brief.mtimeMs).toISOString() : null,
    },
    { headers: { "Cache-Control": "no-store, max-age=0" } },
  );
}

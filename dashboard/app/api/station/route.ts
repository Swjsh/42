import { NextResponse } from "next/server";
import {
  readIdeasBoard,
  readStationBrief,
  readStationConfig,
  readStationMode,
  readLedgerTail,
  readPresence,
  readPlannerSpeed,
  readBrainQuiz,
  readGpuVitals,
  readOllamaPs,
  readTvCapability,
  readFaceConfig,
  readBuildId,
} from "@/lib/station";

export const dynamic = "force-dynamic";
export const revalidate = 0;

/**
 * GET /api/station -- everything the /station page renders, read server-side
 * from automation/state/station/* (paths anchored via lib/workspace.ts's
 * WORKSPACE_ROOT). Read-only: this route never writes anything (the action/
 * ask routes are the only writers). No credential file is read here or
 * anywhere in this module -- station.ts's readers are the full list of what
 * this route touches.
 *
 * The "Brain vitals" panel (J amendment 4, 2026-09-13: "the face must SHOW
 * the brain working") is the one section that shells out (nvidia-smi / ollama
 * ps, fixed argv, no user input, 5s-cached GPU probe) -- every other section
 * is a plain file read.
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
    quiz,
    gpu,
    models,
    tvProbe,
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
    readBrainQuiz(),
    readGpuVitals(),
    readOllamaPs(),
    readTvCapability(),
    readFaceConfig(),
    readBuildId(),
  ]);

  const lastRow = ledger.length > 0 ? ledger[ledger.length - 1] : null;

  return NextResponse.json(
    {
      fetched_at: new Date().toISOString(),
      ideas: { cards: ideas, count: ideas.length },
      brief: { text: brief.text, mtime_ms: brief.mtimeMs },
      brainVitals: {
        model: config.model ?? null,
        mode,
        lastRow,
        fireTimeline: ledger,
        gpu,
        models: models.models,
        modelsOk: models.ok,
        modelsSay: models.say,
        plannerSpeed,
        quiz,
      },
      presence,
      tvProbe,
      face,
      build_id: buildId,
    },
    { headers: { "Cache-Control": "no-store, max-age=0" } },
  );
}

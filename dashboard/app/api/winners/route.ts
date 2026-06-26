import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const RECO = path.join(process.cwd(), "..", "analysis", "recommendations");
const CONSOLIDATION_PATH = path.join(RECO, "elite-consolidation.json");
const PHASE5_PATH = path.join(RECO, "mass-grind-phase5-summary.json");

export interface WinnerSetup {
  setup: string;
  best_label: string;
  n_variations: number;
  expectancy: number;
  edge_capture: number;
  qpf: number | null;
  edge_over_null: number | null;
  null_max: number | null;
  wf: number | null;
  n_trades: number | null;
  score: number;
}

interface WinnersResponse {
  available: boolean;
  generated?: string;
  total_p4_elites?: number;
  distinct_setups?: number;
  top_setups: WinnerSetup[];
  caveats: string[];
  p5_survivors?: number | null;
  p5_total?: number | null;
  fetched_at: string;
  error?: string;
}

export async function GET(): Promise<NextResponse<WinnersResponse>> {
  try {
    const raw = await fs.readFile(CONSOLIDATION_PATH, "utf-8");
    const j = JSON.parse(raw) as {
      generated?: string;
      total_p4_elites?: number;
      distinct_setups?: number;
      top_setups?: WinnerSetup[];
      caveats?: string[];
    };
    let p5_survivors: number | null = null;
    let p5_total: number | null = null;
    try {
      const p5 = JSON.parse(await fs.readFile(PHASE5_PATH, "utf-8")) as { p5_survivors?: number; p4_elites?: number };
      p5_survivors = p5.p5_survivors ?? null;
      p5_total = p5.p4_elites ?? null;
    } catch {
      /* phase 5 not run yet */
    }
    return NextResponse.json(
      {
        available: true,
        generated: j.generated,
        total_p4_elites: j.total_p4_elites,
        distinct_setups: j.distinct_setups,
        top_setups: j.top_setups ?? [],
        caveats: j.caveats ?? [],
        p5_survivors,
        p5_total,
        fetched_at: new Date().toISOString(),
      },
      { headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  } catch (err: unknown) {
    const error = err instanceof Error ? err.message : "consolidation not generated yet";
    return NextResponse.json(
      { available: false, top_setups: [], caveats: [], fetched_at: new Date().toISOString(), error },
      { headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  }
}

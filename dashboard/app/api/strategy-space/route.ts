import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const REGISTRY_PATH = path.join(
  process.cwd(),
  "..",
  "analysis",
  "backtests",
  "STRATEGY-SPACE-REGISTRY.jsonl",
);

// Grind progress is sharded: each parallel strike-shard writes its own
// mass-grind-progress-<shard>.jsonl. Read the union of all of them.
const RECO_DIR = path.join(
  process.cwd(),
  "..",
  "analysis",
  "recommendations",
);
const GRIND_PROGRESS_RE = /^mass-grind-progress.*\.jsonl$/;
// Validation funnel outputs (phase 2 -> 3 -> 4), one file per shard worker.
const FUNNEL_RE = /^mass-grind-funnel-.*\.jsonl$/;

interface GrindSummary {
  tested: number;
  PROMOTE: number;
  HOLD: number;
  DEAD: number;
}

interface GrindResultRow {
  label?: string;
  edge_capture?: number | null;
  wf?: number | null;
  op16_reject?: boolean;
  expectancy?: number | null;
  n?: number | null;
  error?: string;
}

export interface GrindBanger {
  label: string;
  edge_capture: number;
  wf: number;
  expectancy: number | null;
  n: number | null;
}

export interface GrindMatrixCell {
  strike: string;
  stop: string;
  best_ec: number | null;
  verdict: string;
  tested: number;
}

// Validation funnel: each banger flows phase 2 (cross-quarter) -> 3 (live-realizable)
// -> 4 (beats the random-entry null = proven signal alpha).
export interface FunnelSummary {
  reviewed: number;
  elite: number;   // PASS-P4
  strong: number;  // PASS-P3
  robust: number;  // PASS-P2
  stop: number;    // STOP-P2
}

export interface FunnelElite {
  label: string;
  expectancy: number;
  edge_capture: number;
  qpf: number;
  null_max: number | null;
  edge_over_null: number | null;
}

interface FunnelRow {
  label?: string;
  phase_reached?: number;
  verdict?: string;
  expectancy?: number | null;
  edge_capture?: number | null;
  qpf?: number | null;
  p4_null?: { null_max?: number | null; edge_over_null?: number | null } | null;
}

async function readFunnelData(dir: string, re: RegExp): Promise<{
  summary: FunnelSummary;
  elites: FunnelElite[];
}> {
  const summary: FunnelSummary = { reviewed: 0, elite: 0, strong: 0, robust: 0, stop: 0 };
  const elites: FunnelElite[] = [];
  try {
    const files = (await fs.readdir(dir)).filter((f) => re.test(f));
    const parts = await Promise.all(
      files.map((f) => fs.readFile(path.join(dir, f), "utf-8").catch(() => "")),
    );
    for (const line of parts.join("\n").split("\n")) {
      const t = line.trim();
      if (!t) continue;
      let r: FunnelRow;
      try {
        r = JSON.parse(t) as FunnelRow;
      } catch {
        continue;
      }
      summary.reviewed += 1;
      const phase = r.phase_reached ?? 0;
      if (phase >= 4) summary.elite += 1;
      else if (phase === 3) summary.strong += 1;
      else if (phase === 2) summary.robust += 1;
      else summary.stop += 1;
      if (phase >= 4 && r.label) {
        elites.push({
          label: r.label,
          expectancy: r.expectancy ?? 0,
          edge_capture: r.edge_capture ?? 0,
          qpf: r.qpf ?? 0,
          null_max: r.p4_null?.null_max ?? null,
          edge_over_null: r.p4_null?.edge_over_null ?? null,
        });
      }
    }
  } catch {
    /* funnel not present yet */
  }
  elites.sort((a, b) => (b.edge_over_null ?? 0) - (a.edge_over_null ?? 0));
  return { summary, elites };
}

const GRIND_STRIKES = ["OTM-4", "OTM-3", "OTM-2", "OTM-1", "ATM", "ITM-1", "ITM-2"];
const GRIND_STOPS = ["stop-8", "stop-20", "stop-50"];

async function readGrindData(dir: string, re: RegExp): Promise<{
  summary: GrindSummary;
  bangers: GrindBanger[];
  matrix: GrindMatrixCell[];
}> {
  const summary: GrindSummary = { tested: 0, PROMOTE: 0, HOLD: 0, DEAD: 0 };
  const bangers: GrindBanger[] = [];
  const cellMap = new Map<string, { best_ec: number | null; tested: number }>();

  try {
    const files = (await fs.readdir(dir)).filter((f) => re.test(f));
    const parts = await Promise.all(
      files.map((f) => fs.readFile(path.join(dir, f), "utf-8").catch(() => "")),
    );
    const raw = parts.join("\n");
    for (const line of raw.split("\n")) {
      const t = line.trim();
      if (!t) continue;
      summary.tested += 1;
      const r = JSON.parse(t) as GrindResultRow;
      const ec = r.edge_capture;
      if (r.error || ec === null || ec === undefined) {
        summary.DEAD += 1;
      } else if (ec >= 771 && (r.wf ?? 0) >= 0.7 && !r.op16_reject) {
        summary.PROMOTE += 1;
        if (r.label) {
          bangers.push({ label: r.label, edge_capture: ec, wf: r.wf ?? 0, expectancy: r.expectancy ?? null, n: r.n ?? null });
        }
      } else if (ec >= 0) {
        summary.HOLD += 1;
      } else {
        summary.DEAD += 1;
      }
      // Matrix: aggregate best EC per (strike, stop) cell
      if (r.label) {
        const parts = r.label.split(":");
        if (parts.length >= 4) {
          const cellKey = `${parts[0]}:${parts[3]}`;
          const prev = cellMap.get(cellKey) ?? { best_ec: null, tested: 0 };
          const newBestEc = ec !== null && ec !== undefined
            ? prev.best_ec !== null ? Math.max(prev.best_ec, ec) : ec
            : prev.best_ec;
          cellMap.set(cellKey, { best_ec: newBestEc, tested: prev.tested + 1 });
        }
      }
    }
  } catch {
    /* file not present yet */
  }

  bangers.sort((a, b) => b.edge_capture - a.edge_capture);

  const matrix: GrindMatrixCell[] = [];
  for (const s of GRIND_STRIKES) {
    for (const stop of GRIND_STOPS) {
      const key = `${s}:${stop}`;
      const cell = cellMap.get(key) ?? { best_ec: null, tested: 0 };
      const best_ec = cell.best_ec;
      let verdict = "UNTESTED";
      if (best_ec !== null) {
        if (best_ec >= 771) verdict = "PROMOTE";
        else if (best_ec >= 0) verdict = "HOLD";
        else verdict = "DEAD";
      }
      matrix.push({ strike: s, stop: stop.replace("stop", ""), best_ec, verdict, tested: cell.tested });
    }
  }

  return { summary, bangers, matrix };
}

interface RegistryRow {
  combo_id: string;
  dims: {
    structure?: string;
    strike?: string;
    sizing?: string;
    direction?: string;
    gates?: string;
    exit?: string;
    conditions?: string;
  };
  result?: Record<string, unknown>;
  verdict: string;
  account?: string | null;
  tested_at?: string;
  source?: string;
  notes?: string;
}

interface StrategySpaceResponse {
  fetched_at: string;
  available: boolean;
  rows: RegistryRow[];
  summary: Record<string, number>;
  grind: GrindSummary;
  grind_total: number;
  grind_bangers: GrindBanger[];
  grind_matrix: GrindMatrixCell[];
  funnel: FunnelSummary;
  funnel_elites: FunnelElite[];
  error?: string;
}

export async function GET(): Promise<NextResponse<StrategySpaceResponse>> {
  try {
    const raw = await fs.readFile(REGISTRY_PATH, "utf-8");
    const rows: RegistryRow[] = raw
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean)
      .map((l) => JSON.parse(l) as RegistryRow);
    const summary: Record<string, number> = {};
    for (const r of rows) {
      summary[r.verdict] = (summary[r.verdict] ?? 0) + 1;
    }
    const { summary: grind, bangers: grind_bangers, matrix: grind_matrix } = await readGrindData(RECO_DIR, GRIND_PROGRESS_RE);
    const { summary: funnel, elites: funnel_elites } = await readFunnelData(RECO_DIR, FUNNEL_RE);
    let grind_total = 3360;
    try {
      grind_total = (JSON.parse(await fs.readFile(path.join(RECO_DIR, "mass-grind-total.json"), "utf-8")) as { total?: number }).total ?? 3360;
    } catch {
      /* fall back to the original matrix size */
    }
    return NextResponse.json(
      { fetched_at: new Date().toISOString(), available: true, rows, summary, grind, grind_total, grind_bangers, grind_matrix, funnel, funnel_elites },
      { headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  } catch (err: unknown) {
    const error = err instanceof Error ? err.message : "unknown read failure";
    return NextResponse.json(
      {
        fetched_at: new Date().toISOString(),
        available: false,
        rows: [],
        summary: {},
        grind: { tested: 0, PROMOTE: 0, HOLD: 0, DEAD: 0 },
        grind_total: 3360,
        grind_bangers: [],
        grind_matrix: [],
        funnel: { reviewed: 0, elite: 0, strong: 0, robust: 0, stop: 0 },
        funnel_elites: [],
        error,
      },
      { headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  }
}

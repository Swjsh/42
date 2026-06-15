import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const REPORT_PATH = path.join(
  process.cwd(),
  "..",
  "backtest",
  "autoresearch",
  "_state",
  "watchdog_report.json",
);

interface ModeBaseline {
  n_trades?: number;
  win_rate?: number;
  total_pnl?: number;
  sharpe_daily?: number;
  wl_ratio?: number | null;
  max_drawdown?: number;
  expectancy?: number;
}

interface KeepRecord {
  iter: number;
  param: string;
  old: unknown;
  new: unknown;
  delta_sharpe: number;
  delta_pnl: number;
  val_sharpe: number;
  val_pnl: number;
  val_wr: number;
}

interface RejectionRecord {
  iter: number;
  param: string;
  new: unknown;
  val_pnl: number;
  val_sharpe: number;
  val_wr: number;
  rejected_because: string;
}

interface ModeReport {
  mode: string;
  state_exists: boolean;
  iterations: number;
  keeps: number;
  reverts: number;
  keep_rate: number;
  last_batch_keeps: number;
  last_batch_reverts: number;
  train_baseline: ModeBaseline;
  validate_baseline: ModeBaseline;
  top_keeps: KeepRecord[];
  notable_rejections: RejectionRecord[];
  dead_end_params: string[];
  changed_params: Record<string, { from: unknown; to: unknown }>;
  issues: string[];
}

interface WatchdogReport {
  generated_at: string;
  healthy: boolean;
  overall_iterations: number;
  overall_keeps: number;
  overall_keep_rate: number;
  issues: string[];
  modes: ModeReport[];
}

interface AutoresearchApiResponse {
  fetched_at: string;
  available: boolean;
  report?: WatchdogReport;
  process?: { running: boolean };
  error?: string;
}

export async function GET(): Promise<NextResponse<AutoresearchApiResponse>> {
  try {
    const raw = await fs.readFile(REPORT_PATH, "utf-8");
    const report = JSON.parse(raw) as WatchdogReport;
    return NextResponse.json(
      {
        fetched_at: new Date().toISOString(),
        available: true,
        report,
      },
      { headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  } catch (err: unknown) {
    const error = err instanceof Error ? err.message : "unknown read failure";
    return NextResponse.json(
      {
        fetched_at: new Date().toISOString(),
        available: false,
        error,
      },
      { headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  }
}

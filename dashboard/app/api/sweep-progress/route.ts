import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";
export const revalidate = 0;

const PROGRESS_PATH = path.join(
  process.cwd(),
  "..",
  "backtest",
  "autoresearch",
  "_state",
  "weekend-progress.json",
);

const LOCK_PATH = path.join(
  process.cwd(),
  "..",
  "backtest",
  "autoresearch",
  "_state",
  "weekend-research.lock",
);

interface WaveRecord {
  wave: string;
  modes: string[];
  experiment: string;
  objective: string;
  iterations: number;
  started_at: string;
  ended_at?: string;
  elapsed_min?: number;
  notes?: string;
}

interface CurrentWave {
  wave: string;
  modes: string[];
  experiment: string;
  objective: string;
  iterations: number;
  started_at: string;
  notes?: string;
}

interface WeekendProgress {
  started_at: string;
  stop_at: string;
  pid: number;
  waves_total: number;
  waves_done: number;
  current_wave: CurrentWave | null;
  waves: WaveRecord[];
  finished_at?: string;
  total_elapsed_hours?: number;
}

interface SweepProgressApiResponse {
  fetched_at: string;
  available: boolean;
  running: boolean;
  progress?: WeekendProgress;
  budget_remaining_hours?: number;
  pct_complete?: number;
  error?: string;
}

async function readProgress(): Promise<WeekendProgress | null> {
  try {
    const raw = await fs.readFile(PROGRESS_PATH, "utf-8");
    // PowerShell 5.1's `Out-File -Encoding utf8` emits a BOM; strip it.
    const cleaned = raw.replace(/^﻿/, "");
    return JSON.parse(cleaned) as WeekendProgress;
  } catch {
    return null;
  }
}

async function isRunning(): Promise<boolean> {
  try {
    await fs.access(LOCK_PATH);
    return true;
  } catch {
    return false;
  }
}

export async function GET(): Promise<NextResponse<SweepProgressApiResponse>> {
  const fetchedAt = new Date().toISOString();
  const running = await isRunning();
  const progress = await readProgress();

  if (!progress) {
    return NextResponse.json(
      {
        fetched_at: fetchedAt,
        available: false,
        running,
        error: "weekend-progress.json not found yet",
      },
      { headers: { "Cache-Control": "no-store, max-age=0" } },
    );
  }

  const stopAt = new Date(progress.stop_at).getTime();
  const now = Date.now();
  const budgetRemainingMs = stopAt - now;
  const budgetRemainingHours = Math.max(0, budgetRemainingMs / (1000 * 60 * 60));
  const pctComplete = progress.waves_total > 0
    ? Math.round((progress.waves_done / progress.waves_total) * 100)
    : 0;

  return NextResponse.json(
    {
      fetched_at: fetchedAt,
      available: true,
      running,
      progress,
      budget_remaining_hours: Math.round(budgetRemainingHours * 100) / 100,
      pct_complete: pctComplete,
    },
    { headers: { "Cache-Control": "no-store, max-age=0" } },
  );
}

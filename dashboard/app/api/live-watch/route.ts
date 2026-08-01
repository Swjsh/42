import { NextResponse } from "next/server";
import { paths } from "@/lib/workspace";
import { readJson } from "@/lib/state";

// WS7 LIVE WATCH: serve automation/state/live-watch.json (written every minute during
// RTH by setup/scripts/live_watch.py, single CLOSED marker otherwise). Read-only pass-
// through — the watcher owns the schema; the panel renders whatever schema_version=1
// carries. Same force-dynamic/no-cache pattern as /api/state.
export const dynamic = "force-dynamic";
export const revalidate = 0;

export interface LiveWatchFile {
  schema_version?: number;
  written_at_et?: string;
  market_state?: "RTH" | "CLOSED";
  note?: string;
  spy?: { last?: number | null; source?: string } | null;
  in_trade_count?: number;
  arms?: Record<string, LiveWatchArm>;
  theta_clock?: { ts_et?: string; n_positions?: number } | null;
  errors?: string[];
}

export interface LiveWatchArm {
  display_name?: string;
  execution?: string;
  in_trade?: boolean | null;
  position?: LiveWatchPosition | LiveWatchPosition[] | null;
  last_decision?: {
    verdict?: string | null;
    reason?: string | null;
    ts_et?: string | null;
    age_min?: number | null;
  } | null;
  kill_switch?: {
    present?: boolean;
    tripped?: boolean | null;
    reason?: string | null;
  } | null;
  status?: string;
}

export interface LiveWatchPosition {
  symbol?: string;
  right?: string | null;
  strike?: number | null;
  qty?: number | null;
  entry_premium?: number | null;
  mid?: number | null;
  mid_source?: string;
  unrealized_pnl_usd?: number | null;
  unrealized_pnl_pct?: number | null;
  stop_mode?: string | null;
  stop_premium?: number | null;
  trigger_level?: number | null;
  dist_to_stop_pct?: number | null;
  dist_to_stop_level_pts?: number | null;
  tp_phase?: string | null;
  tp_target_premium?: number | null;
  dist_to_tp_pct?: number | null;
  hwm_premium?: number | null;
  hwm_gain_pct?: number | null;
  profit_lock_armed?: boolean | null;
  time_in_trade_min?: number | null;
}

export async function GET() {
  const data = await readJson<LiveWatchFile>(paths.liveWatch);
  return NextResponse.json({
    fetched_at: new Date().toISOString(),
    available: data !== null,
    watch: data,
  });
}

import { NextResponse } from "next/server";
import { paths } from "@/lib/workspace";
import { readJson } from "@/lib/state";

// WS7 LIVE WATCH: serve automation/state/live-watch.json (written every minute during
// RTH by setup/scripts/live_watch.py, single CLOSED marker otherwise). Read-only pass-
// through — the watcher owns the schema; the panel renders whatever schema_version=1
// carries. Same force-dynamic/no-cache pattern as /api/state.
export const dynamic = "force-dynamic";
export const revalidate = 0;

// WS8→WS7 READ-SIDE MERGE (2026-08-01, Next-Twelve #11): trendline-watch.json (WS8,
// written by backtest/autoresearch/trendline_watch.py) and live-watch.json (WS7, written
// by setup/scripts/live_watch.py) are two separate producers/files — live_watch.py is
// owned by another lane tonight, so this merges trendline data into the API RESPONSE
// only, never onto disk and never by editing live_watch.py. trendline-watch.json's own
// `_merge_note` names this exact contract: "READ this file and embed this payload under
// an additive 'trendlines' key. One writer per state file -- this producer never writes
// live-watch.json." `trendlines` below is populated by THIS route at request time, not
// by the live-watch.json file itself — see GET().
export interface TrendlineLine {
  kind?: string; // "support" | "resistance"
  flavor?: string; // "wick" | "body"
  tier?: string;
  status?: string; // "TESTING" | "BROKEN" | ...
  current_value?: number | null;
  break_level?: number | null;
  respect_count?: number;
  violations?: number;
  slope_per_bar?: number;
  summary?: string;
}

export interface TrendlineEvent {
  type?: string; // "break" | "retest"
  ts_et?: string;
  date_et?: string;
  kind?: string;
  flavor?: string;
  tier?: string;
  level?: number | null;
  summary?: string;
}

export interface TrendlineWatchFile {
  schema_version?: number;
  ts_et?: string;
  live_state_ts_et?: string;
  live_state_date_et?: string;
  n_total?: number;
  n_active?: number;
  last_close?: number | null;
  active_lines?: TrendlineLine[];
  nearest_active?: (TrendlineLine & { distance_dollars?: number | null; side?: string }) | null;
  last_break?: TrendlineEvent | null;
  last_retest?: TrendlineEvent | null;
  premarket_line?: string;
}

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
  // Additive, API-layer-injected (NOT part of the raw live-watch.json file on disk) —
  // see the WS8→WS7 READ-SIDE MERGE note above.
  trendlines?: TrendlineWatchFile | null;
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
  // Independent read, independent failure mode: trendline-watch.json missing/stale/
  // garbled must never affect availability of the live-watch payload itself (fail-open,
  // matches this route's existing readJson-returns-null-on-any-error contract).
  const trendlines = await readJson<TrendlineWatchFile>(paths.trendlineWatch);
  const watch: LiveWatchFile | null = data ? { ...data, trendlines } : data;
  return NextResponse.json({
    fetched_at: new Date().toISOString(),
    available: data !== null,
    watch,
  });
}

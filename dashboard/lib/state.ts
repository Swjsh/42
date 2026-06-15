import { promises as fs } from "node:fs";

export type RibbonOrder = "BULLISH" | "BEARISH" | "MIXED" | "FLAT";
export type ScanMode = "HOT" | "BASE" | "COOL";

export interface SpyBar {
  open: number;
  high: number;
  low: number;
  close: number;
  bar_time: string;
  bar_closes: string;
}

export interface Ribbon {
  fast_ema: number;
  pivot_ema: number;
  slow_ema: number;
  fast_conviction_ema?: number;
  slow_conviction_ema?: number;
  order: RibbonOrder;
  spread: number;
  bullish_ticks_consecutive?: number;
  bearish_ticks_consecutive?: number;
}

export interface LoopState {
  last_updated: string;
  spy_price: number;
  spy_bar: SpyBar;
  ribbon: Ribbon;
  sma_50?: number;
  price_vs_sma50?: string;
  volume_current_bar?: number;
  key_levels?: Record<string, string>;
  setup_detected?: string | null;
  direction?: string | null;
  trigger_fired?: boolean;
  trigger_fired_at?: string | null;
  trigger_bar?: string | null;
  trade_active?: boolean;
  pending_order?: Record<string, unknown> | null;
  notes?: string;
  scan_mode?: ScanMode;
  alerts?: Record<string, unknown>;
}

export interface KeyLevel {
  price: number;
  type: string;
  secondary_type?: string;
  tier: "Active" | "Carry" | "Reference";
  source: string;
  verified_at: string;
  expires_at: string;
  reasoning: string;
  color: string;
  style: "solid" | "dashed";
  entity_id: string | null;
  draw_needed?: boolean;
}

export interface KeyLevelsFile {
  schema_version: number;
  protocol_version: string;
  as_of: string;
  for_session: string;
  session_recap: Record<string, unknown>;
  levels: KeyLevel[];
  vix_context?: Record<string, unknown>;
}

export interface TodayBias {
  date: string;
  bias: "bullish" | "bearish" | "neutral";
  bias_note: string;
  no_trade: boolean;
  no_trade_windows: { start_et: string; end_et: string; reason: string }[];
  key_levels?: Record<string, unknown>;
  gap_context?: Record<string, number | string>;
  vix_at_open: number | null;
  vix_bias: string;
  updated_at: string;
}

export interface CircuitBreaker {
  tripped: boolean;
  tripped_at: string | null;
  tripped_reason: string | null;
  starting_equity_today: number;
  current_equity: number;
  daily_loss_limit_dollars: number;
  max_drawdown_today_dollars: number;
  max_drawdown_today_pct: number;
  last_reset: string;
}

export interface ModeFile {
  mode: "live-paper" | "paused" | "live";
  last_changed: string;
  changed_by: string;
  reason: string;
}

export interface CurrentPosition {
  status: string | null;
  contract?: string;
  contracts?: number;
  entry_price?: number;
  stop?: number;
  target?: number;
  opened_at?: string;
}

export type AgentKey =
  | "premarket"
  | "heartbeat"
  | "day_trader"
  | "eod"
  | "review";

export interface AgentState {
  active: boolean;
  speech: string | null;
  last_active_at: string | null;
}

export interface DialogueFile {
  updated_at: string;
  claude_status: string;
  claude_reasoning: string;
  agents: Record<AgentKey, AgentState>;
  ticker_speech?: string | null;
}

export async function readJson<T>(p: string): Promise<T | null> {
  try {
    const text = await fs.readFile(p, "utf-8");
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

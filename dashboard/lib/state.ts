import { promises as fs } from "node:fs";

// ─── Loop State ───────────────────────────────────────────────────────────────

export interface LoopState {
  schema_version: number;
  session_id: string;
  last_change_at: string;
  last_change_reason: string;
  last_bar_timestamp: number;
  current_mode: "BASE" | "HOT" | "COOL";
  writes_today: number;
  ticks_today: number;
  spy: { last: number | null; session_high: number | null; session_low: number | null } | null;
  vix_cache: {
    value: number | null;
    prior_value: number | null;
    dir: "rising" | "falling" | "flat" | "cached" | null;
    fetched_at: string | null;
  } | null;
  ribbon: {
    fast: number;
    pivot: number;
    slow: number;
    spread_cents: number;
    stack: "BULL" | "BEAR" | "MIXED";
  } | null;
  htf_15m: { stack: string; spread_cents?: number } | null;
  last_filter_score: {
    bear: number;
    bear_blockers: number[];
    bull: number;
    bull_blockers: number[];
  } | null;
  developing_setup: {
    name: string;
    trigger: string;
    score: number;
    score_max: number;
    blockers?: number[];
  } | null;
  first_entry_lock: unknown[];
  next_tick_model: "haiku" | "sonnet";
}

// ─── Key Levels ───────────────────────────────────────────────────────────────

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
  levels: KeyLevel[];
}

// ─── Today Bias ───────────────────────────────────────────────────────────────

export interface TodayBias {
  date: string;
  bias: "bullish" | "bearish" | "neutral";
  bias_note: string;
  falsifiable_predictions: Array<{
    claim: string;
    outcome: string | null;
    confidence: number;
  }>;
  vix_at_open: number | null;
  vix_prior: number | null;
  vix_bias: string;
  iv_regime: string;
  news_calendar: {
    events_today: Array<{ event: string; time_et: string; severity: string }>;
    no_trade_window: Array<{ start_et: string; end_et: string; event: string }>;
    stale: boolean;
  };
  daily_loss_budget_dollars: number;
  daily_loss_budget_bold_dollars: number;
  safe_equity_bod_pending?: boolean;
  safe_equity_assumed?: number;
  bold_equity?: number;
  updated_at: string;
}

// ─── Circuit Breaker ──────────────────────────────────────────────────────────

export interface CircuitBreaker {
  tripped: boolean;
  tripped_at?: string | null;
  tripped_reason?: string | null;
  // safe schema
  starting_equity_today?: number;
  current_equity?: number;
  daily_loss_limit_dollars?: number;
  daily_loss_limit_pct?: number;
  // bold/aggressive schema
  equity_start_of_day?: number;
  equity_current?: number;
  loss_pct?: number;
  SAFE_EQUITY_BOD_PENDING?: boolean;
}

// ─── Current Position ─────────────────────────────────────────────────────────

export interface CurrentPosition {
  status: string | null;
  symbol?: string;
  qty?: number;
  fill_price?: number;
  stop_price?: number;
  tp1_price?: number;
  profit_lock_floor?: number;
  opened_at_et?: string;
  setup?: string;
  direction?: string;
}

// ─── Kitchen Status ───────────────────────────────────────────────────────────

export interface KitchenStatus {
  updated_at_et: string;
  daemon_pid: number | null;
  daemon_alive: boolean;
  idle: boolean;
  current_task_id: string | null;
  queue_summary: {
    by_status: {
      completed: number;
      pending: number;
      failed_permanent: number;
    };
  };
  today_cost_usd_paid_tier: number;
  today_cost_cap_usd: number;
}

// ─── Decision Tick ────────────────────────────────────────────────────────────

export interface DecisionTick {
  tick_id?: number;
  date: string;
  time_et: string;
  account_id?: "safe" | "bold";
  action: string;
  position_status?: string;
  bull_score?: number;
  bear_score?: number;
  spy?: number;
  vix?: number;
  vix_dir?: string;
  ribbon_stack?: string;
  ribbon_spread_cents?: number;
  reason?: string;
  symbol?: string;
  runner_unrealized_pl?: number;
}

// ─── Dialogue ─────────────────────────────────────────────────────────────────

export interface AgentState {
  active: boolean;
  speech: string | null;
  last_active_at: string | null;
}

export interface DialogueFile {
  updated_at: string;
  claude_status: string;
  claude_reasoning: string;
  agents: Record<string, AgentState>;
  ticker_speech?: string | null;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

export async function readJson<T>(p: string): Promise<T | null> {
  try {
    const text = await fs.readFile(p, "utf-8");
    return JSON.parse(text) as T;
  } catch {
    return null;
  }
}

export async function readJsonlTail(filePath: string, n = 15): Promise<DecisionTick[]> {
  try {
    const text = await fs.readFile(filePath, "utf-8");
    const lines = text.trim().split("\n").filter(Boolean);
    const tail = lines.slice(-n);
    return tail
      .map((line) => {
        try {
          return JSON.parse(line) as DecisionTick;
        } catch {
          return null;
        }
      })
      .filter((x): x is DecisionTick => x !== null);
  } catch {
    return [];
  }
}

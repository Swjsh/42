"""Canonical JSON schema for EOD Deep-Dive output.

This file is the SCHEMA SOURCE OF TRUTH. Every downstream projection
(markdown, html, journal sections, sessions.jsonl) reads only the
EodDeepDive dataclass — no parallel data paths.

Versioning: schema_version is bumped on breaking changes. Backwards-compat
loader in `_state/eod_deep_loaders/` for past sessions.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional, Any
import datetime as dt
import json


SCHEMA_VERSION = "eod-deep-v1"


# === The 12 categories ===

@dataclass
class CategoryScore:
    """One category's analysis output."""
    score: float                       # 0-100
    evidence: dict[str, Any]           # raw data the score is computed from
    narrative: str                     # 1-3 paragraph human-readable summary
    actions: list[dict[str, Any]] = field(default_factory=list)
    # actions schema: [{"type": "queue_for_grinder|log_lesson|update_doctrine|spawn_task",
    #                   "priority": "HIGH|MED|LOW",
    #                   "details": {...}}]


# === Trade-level records ===

@dataclass
class Fill:
    time_et: str           # "HH:MM:SS"
    side: str              # "buy" | "sell"
    qty: int
    price: float
    source: str            # "engine_heartbeat" | "engine_watcher" | "j_manual" | "j_real_money"
    reason: str            # "entry" | "tp1" | "scale_out" | "runner_target" | "trail_stop" | "ribbon_flip_exit" | "time_stop"
    order_id: Optional[str] = None
    slippage_cents: Optional[int] = None


@dataclass
class EngineDecision:
    """One heartbeat tick or watcher fire that drove a decision."""
    time_et: str
    tick_or_fire_id: int
    decision: str            # "ENTER_BULL" | "ENTER_BEAR" | "EXIT_TP1" | "EXIT_RUNNER" | "HOLD" | "HOLD_DEV" | "SKIP"
    reasoning: str           # the human-readable reason
    raw_state: dict[str, Any] = field(default_factory=dict)


@dataclass
class Counterfactual:
    """What WOULD have happened under an alternative doctrine/management."""
    name: str                # "perfect_hindsight" | "v14_doctrine" | "j_anchor_4_29" | "stepped_pl"
    pnl_dollars: float
    method: str              # narrative description
    delta_vs_actual: float   # +/- vs realized


@dataclass
class TradeRecord:
    id: str                  # "trade_1", etc.
    setup_name: str
    direction: str           # "long" | "short"
    underlying: str          # "SPY"
    expiry_date: str         # "2026-05-14"
    strike: float
    option_type: str         # "C" | "P"
    fills: list[Fill]

    # computed
    entry_price: float
    avg_exit_price: float
    qty_entered: int
    qty_exited: int
    qty_outstanding: int                # if still open at EOD (should be 0 for 0DTE)
    pnl_dollars_realized: float
    pnl_dollars_unrealized: float
    pnl_pct_on_capital: float
    hold_minutes: int

    # quality
    triggers_fired: list[str]
    setup_score: str                    # "10/11"
    doctrine_compliance_score: float    # 0-100, how well doctrine was followed for THIS trade
    rule_breaks: list[str]              # empty if clean
    journaled_before_entry: bool

    # engine narrative
    engine_decisions: list[EngineDecision]

    # counterfactuals (the secret sauce for J-edge tracking + doctrine optimization)
    counterfactuals: list[Counterfactual] = field(default_factory=list)


# === Top-level day record ===

@dataclass
class EodDeepDive:
    """Canonical day record. ONE per trading day."""

    # === Identity ===
    schema_version: str = SCHEMA_VERSION
    date: str = ""                                          # "YYYY-MM-DD"
    generated_at_et: str = ""                               # ISO timestamp when this was generated
    rule_version_active: str = ""                           # "v15"

    # === Macro context ===
    market_session_summary: dict[str, Any] = field(default_factory=dict)
    # {open_price, close_price, high, low, range, vix_open, vix_close,
    #  regime_predicted, regime_actual, news_catalyst_primary}

    # === Account ===
    account_equity_start: float = 0.0
    account_equity_end: float = 0.0
    day_pnl_dollars: float = 0.0
    day_pnl_pct: float = 0.0
    day_trade_count: int = 0
    daily_loss_budget_used_pct: float = 0.0                 # vs -50% kill switch

    # === Trades ===
    trades: list[TradeRecord] = field(default_factory=list)

    # === The 12 categories ===
    categories: dict[str, CategoryScore] = field(default_factory=dict)
    # keys: execution, detection, edge, doctrine, risk, process,
    #       macro, technical, engine_health, watcher_fleet, lessons, tomorrow

    # === Aggregate scores ===
    process_score: float = 0.0                              # weighted avg of categories
    edge_capture_pct: float = 0.0                           # actual P&L / perfect-hindsight P&L

    # === Research handoffs (feed into backtest/autoresearch) ===
    research_handoffs: dict[str, Any] = field(default_factory=dict)
    # {doctrine_candidates_for_grinder: [list],
    #  drift_check: {engine_pnl_vs_backtest_expected, verdict},
    #  fixes_shipped_today: [list],
    #  anchor_day_addition: bool,
    #  opra_backfill_queue: [list]}

    # === Forward look ===
    tomorrow_setup: dict[str, Any] = field(default_factory=dict)
    # {key_levels_carry, scheduled_events, developing_setups, expected_regime}


# === Standard category keys ===

CATEGORY_KEYS = [
    "execution",
    "detection",
    "edge",
    "doctrine",
    "risk",
    "process",
    "macro",
    "technical",
    "engine_health",
    "watcher_fleet",
    "lessons",
    "forensics",   # Phase 2.3 NEW — separate from `lessons` (which is L## candidates)
    "tomorrow",
]


# === Category weights for aggregate process_score ===
# Total = 1.0. Forensics gets weight; some others compress slightly.

CATEGORY_WEIGHTS = {
    "execution":     0.12,
    "detection":     0.08,
    "edge":          0.13,
    "doctrine":      0.13,  # process > P&L per CLAUDE.md
    "risk":          0.10,
    "process":       0.05,
    "macro":         0.05,
    "technical":     0.05,
    "engine_health": 0.05,
    "watcher_fleet": 0.05,
    "lessons":       0.04,
    "forensics":     0.10,  # NEW Phase 2.3: heavy weight (real evidence loop)
    "tomorrow":      0.05,
}
assert abs(sum(CATEGORY_WEIGHTS.values()) - 1.0) < 1e-9, "weights must sum to 1.0"


# === Serialization helpers ===

def to_dict(d: EodDeepDive) -> dict:
    """Convert dataclass to plain dict for JSON serialization."""
    return asdict(d)


def to_json(d: EodDeepDive, indent: int = 2) -> str:
    """Serialize to pretty-printed JSON."""
    def _default(o):
        if isinstance(o, (dt.date, dt.datetime, dt.time)):
            return o.isoformat()
        if hasattr(o, "to_pylist"):  # pandas-ish
            return o.to_pylist()
        return str(o)
    return json.dumps(to_dict(d), indent=indent, default=_default)


def compute_process_score(d: EodDeepDive) -> float:
    """Weighted aggregate of category scores."""
    total = 0.0
    for key, weight in CATEGORY_WEIGHTS.items():
        cat = d.categories.get(key)
        if cat is None:
            continue
        total += cat.score * weight
    return round(total, 1)

"""Pydantic v2 models for Project Gamma's load-bearing state files.

ONE MODEL PER FILE. Each model documents (in its docstring) WHICH file it
guards and WHICH consumers depend on it, so the model is the single source of
truth for "what fields must this file carry".

DESIGN RULES (all models obey these):
  * ``model_config = ConfigDict(extra="allow")`` -- these files legitimately
    carry prose ``_doc`` essays, ``_*_doc`` per-knob rationale, audit logs, and
    diagnostic keys. We assert the REQUIRED consumed fields exist; we do NOT
    ban extras.
  * Required fields = only those a consumer reads and would silently break on
    if absent (the bug class this whole package kills). Everything else is
    ``Optional`` with a default, so a producer adding/removing a diagnostic key
    never trips the contract.
  * Nested objects that consumers index into (``spy.last``, ``vix_cache.value``,
    ``ribbon.stack``) get their own sub-models so a renamed sub-key also fails
    loudly -- not just a renamed top-level key.

Field types are intentionally permissive where the live data is heterogeneous
(e.g. ``loop-state.last_filter_score.bear_blockers`` holds ``int`` indices in
the safe file but ``str`` reason-codes in the aggressive file -- so it is typed
``List[Any]``).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# --------------------------------------------------------------------------- #
# Shared base
# --------------------------------------------------------------------------- #


class _StateModel(BaseModel):
    """Base for every state-file model: allow extra keys (doc/diagnostic)."""

    model_config = ConfigDict(extra="allow")


# --------------------------------------------------------------------------- #
# params.json  (canonical config -- the most-read file in the system)
# --------------------------------------------------------------------------- #


class ParamsModel(_StateModel):
    """Contract for ``automation/state/params.json`` (Gamma-Safe canonical config).

    Consumers (partial, the load-bearing ones):
      * ``automation/prompts/heartbeat.md`` -- the live Safe trading loop reads
        every exit/entry/VIX/gate knob below on every tick.
      * ``backtest/lib/filters.py`` / ``orchestrator.py`` / ``simulator_real.py``
        -- the backtest engine reads the same knobs (Operating Principle 4:
        live and backtest must not drift).
      * ``automation/prompts/premarket.md`` Step 1a -- pins ``rule_version`` and
        kills the day on mismatch.

    Only fields that a consumer indexes by name are required here. The 29 ``_doc``
    / ``_*_section`` prose keys ride along via ``extra='allow'``.
    """

    # --- identity / pin ---
    schema_version: int
    rule_version: str

    # --- exits (heartbeat exit-management + simulator) ---
    premium_stop_pct: float
    premium_stop_pct_bear: float
    tp1_qty_fraction: float
    runner_max_premium_pct: float
    time_stop_et: str

    # --- entry window ---
    entry_no_trade_before_et: str
    entry_no_trade_after_et: str

    # --- the 6 gate knobs (filter triggers) ---
    filter_9_vol_multiplier: float
    filter_10_min_triggers_bear: int
    filter_10_min_triggers_bull: int
    filter_10_level_tied_required: bool
    ribbon_min_spread_cents: int
    midday_trendline_gate: bool

    # --- strike selection tiers ---
    strike_offset_itm: int
    max_premium_per_contract: float
    position_sizing_tiers: List[Dict[str, Any]]
    v15_strike_offset_per_tier: List[Dict[str, Any]]
    v15_max_premium_pct_of_account: List[Dict[str, Any]]

    # --- VIX thresholds (filters 8a/8b) ---
    vix_entry_thresholds: Dict[str, Any]
    vix_iv_regime_bands: Dict[str, Any]

    # --- risk / kill-switch ---
    per_trade_risk_cap_pct: float
    daily_loss_kill_switch_pct: float
    min_contracts: int


class AggressiveParamsModel(_StateModel):
    """Contract for ``automation/state/aggressive/params.json`` (Gamma-Bold config).

    Consumer: ``automation/prompts/aggressive/heartbeat.md`` (the Bold trading
    loop) + the aggressive backtest sweeps in ``backtest/autoresearch/agg_*``.

    Schema diverges from Safe (C9 "dual-account symmetry trap"): Bold adds
    ``premium_stop_pct_bull``, ``require_bearish_fill_bar``, and several
    ``block_*`` knobs; it has NO ``vix_bear_hard_cap``. This model encodes the
    Bold-specific required surface. ``extra='allow'`` covers the rest.
    """

    schema_version: int
    rule_version: str

    # exits (Bold uses bull+bear+generic stops)
    premium_stop_pct: float
    premium_stop_pct_bear: float
    premium_stop_pct_bull: float
    tp1_qty_fraction: float
    runner_max_premium_pct: float
    time_stop_et: str

    # entry window
    entry_no_trade_before_et: str
    entry_no_trade_after_et: str

    # gate knobs
    filter_9_vol_multiplier: float
    filter_10_min_triggers_bear: int
    filter_10_min_triggers_bull: int
    filter_10_level_tied_required: bool
    ribbon_min_spread_cents: int

    # Bold-specific confirmation gate (J-ratified 2026-06-17)
    require_bearish_fill_bar: bool

    # strike selection
    strike_offset_itm: int
    max_premium_per_contract: float
    position_sizing_tiers: List[Dict[str, Any]]

    # VIX
    vix_entry_thresholds: Dict[str, Any]
    vix_iv_regime_bands: Dict[str, Any]

    # risk
    per_trade_risk_cap_pct: float
    daily_loss_kill_switch_pct: float
    min_contracts: int


# --------------------------------------------------------------------------- #
# loop-state.json  (per-tick heartbeat working state)
# --------------------------------------------------------------------------- #


class _SpyState(_StateModel):
    """Live SPY snapshot inside loop-state. Heartbeat reads ``last`` every tick."""

    last: float
    session_high: Optional[float] = None
    session_low: Optional[float] = None


class _VixCache(_StateModel):
    """Cached VIX inside loop-state. Heartbeat reads ``value`` + ``dir`` for filters 8a/8b."""

    value: Optional[float] = None
    prior_value: Optional[float] = None
    dir: Optional[str] = None
    fetched_at: Optional[str] = None


class _RibbonState(_StateModel):
    """EMA ribbon snapshot inside loop-state. Heartbeat reads ``stack`` + ``spread_cents``."""

    fast: Optional[float] = None
    pivot: Optional[float] = None
    slow: Optional[float] = None
    spread_cents: Optional[float] = None
    stack: str


class _FirstEntryLock(_StateModel):
    """One entry in ``first_entry_lock[]`` -- a setup already traded today.

    Heartbeat reads ``setup_name`` to enforce Rule: no second entry on a setup
    that already stopped out today (``first_entry_after_stop_blocked``).
    """

    setup_name: str
    entered_at_et: Optional[str] = None
    exited_at_et: Optional[str] = None
    exit_reason: Optional[str] = None
    qty: Optional[float] = None
    pnl_dollars: Optional[float] = None


class LoopStateModel(_StateModel):
    """Contract for ``automation/state/loop-state.json`` (+ ``aggressive/`` variant).

    Consumers:
      * ``automation/prompts/heartbeat.md`` (+ aggressive) -- reads/writes this
        every tick: ``spy``, ``vix_cache``, ``ribbon``, ``first_entry_lock``,
        ``current_mode`` (HOT/BASE/COOL throttle), ``next_tick_model``.
      * Self-healing ``_shared.ps1#Repair-StateFiles`` validates ``schema_version``
        + ``session_id`` before/after each invocation.

    ``first_entry_lock`` is the load-bearing list (re-entry suppression). The
    two account variants differ only in extra keys (aggressive adds
    ``macro_pre_event_bias``), handled by ``extra='allow'``.
    """

    schema_version: int
    session_id: str
    current_mode: str
    spy: _SpyState
    vix_cache: _VixCache
    ribbon: _RibbonState
    first_entry_lock: List[_FirstEntryLock]

    # nullable working fields the heartbeat reads but tolerates absent
    htf_15m: Optional[Any] = None
    developing_setup: Optional[Dict[str, Any]] = None
    last_filter_score: Optional[Dict[str, Any]] = None
    next_tick_model: Optional[str] = None


# --------------------------------------------------------------------------- #
# current-position.json / current-position-bold.json
# --------------------------------------------------------------------------- #


class PositionModel(_StateModel):
    """Contract for the position state files.

    Files:
      * ``automation/state/current-position.json`` (Safe)
      * ``automation/state/current-position-bold.json`` (Bold)

    Consumers: heartbeat exit-management + ``gamma-status`` skill + EOD flatten.
    The KEY invariant this guards: ``status`` is a REQUIRED key but NULLABLE --
    when flat it is ``null``. Many consumers branch on ``status is None`` to mean
    "flat"; if a producer dropped the key entirely, ``.get('status')`` and an
    explicit ``['status']`` would diverge. Requiring the key (value may be null)
    forces producers to always emit it. All position detail keys (symbol, qty,
    entry, stop, ...) ride along via ``extra='allow'`` because they are only
    present when a position is open.
    """

    status: Optional[str] = Field(
        ...,
        description="Position lifecycle status; null when flat. Key MUST be present.",
    )


# --------------------------------------------------------------------------- #
# circuit-breaker.json  (Safe) and aggressive/circuit-breaker.json (Bold)
# --------------------------------------------------------------------------- #


class CircuitBreakerModel(_StateModel):
    """Contract for ``automation/state/circuit-breaker.json`` (SAFE breaker).

    Consumers: Safe heartbeat kill-switch gate + premarket re-arm + gamma-status.
    Safe schema vocabulary (see the file's ``_schema_note`` for the SAFE->BOLD
    field-name mapping -- C9 symmetry trap):
      ``tripped``, ``starting_equity_today``, ``current_equity``,
      ``daily_loss_limit_dollars``, ``daily_loss_limit_pct``.

    ``tripped`` is the one field BOTH breakers share; the Safe gate also reads
    the equity + limit fields to compute drawdown.
    """

    tripped: bool
    starting_equity_today: float
    current_equity: float
    daily_loss_limit_dollars: float
    daily_loss_limit_pct: float

    tripped_at: Optional[str] = None
    tripped_reason: Optional[str] = None


class AggressiveCircuitBreakerModel(_StateModel):
    """Contract for ``automation/state/aggressive/circuit-breaker.json`` (BOLD breaker).

    Consumer: Bold heartbeat kill-switch gate + premarket re-arm.
    Bold schema uses a DIVERGENT vocabulary from Safe (do NOT unify -- the live
    gates read these exact keys):
      ``tripped`` (shared), ``equity_start_of_day``, ``equity_current``,
      ``loss_pct`` (realized loss %, not a limit), ``trip_reason``,
      ``tripped_at_et``.

    Modeling both Safe and Bold breakers separately is deliberate (C9): a single
    shared model would force one vocabulary and reintroduce the cross-account
    null-read bug the ``_schema_note`` warns about.
    """

    tripped: bool
    equity_start_of_day: float
    equity_current: float
    loss_pct: float

    session_id: Optional[str] = None
    trip_reason: Optional[str] = None
    tripped_at_et: Optional[str] = None


# --------------------------------------------------------------------------- #
# today-bias.json  (premarket -> heartbeat handoff)
# --------------------------------------------------------------------------- #


class _NewsCalendar(_StateModel):
    """News-calendar block in today-bias. Heartbeat reads ``no_trade_window`` +
    ``events_today`` for the macro hard-veto gate."""

    events_today: List[Any]
    no_trade_window: List[Any]
    size_modifier_windows: Optional[List[Any]] = None
    stale: Optional[bool] = None


class TodayBiasModel(_StateModel):
    """Contract for ``automation/state/today-bias.json``.

    Producer: ``automation/prompts/premarket.md`` (08:30 ET).
    Consumers: heartbeat (both accounts) reads:
      * ``safe_equity_confirmed`` / ``bold_equity`` -- live BOD equity for sizing
        + kill-switch math (gate ``SAFE_EQUITY_BOD_PENDING``).
      * ``bias`` -- macro bias inheritance.
      * ``key_levels`` -- premarket level set.
      * ``news_calendar`` -- macro hard-veto windows.
      * ``daily_loss_budget_dollars`` / ``day_trades_remaining`` -- risk display.

    ``safe_equity_confirmed`` is the canonical "did premarket confirm live
    equity yet" signal -- a silent ``None`` here previously let the heartbeat
    size off a stale number. Required now.
    """

    date: str
    bias: str
    key_levels: Dict[str, Any]
    news_calendar: _NewsCalendar

    safe_equity_confirmed: Optional[float] = Field(
        ...,
        description="Live Safe BOD equity confirmed by premarket; null until confirmed. Key MUST be present.",
    )
    bold_equity: Optional[float] = Field(
        ...,
        description="Live Bold BOD equity; null until confirmed. Key MUST be present.",
    )

    daily_loss_budget_dollars: Optional[float] = None
    day_trades_remaining: Optional[int] = None


# --------------------------------------------------------------------------- #
# key-levels.json  (premarket-computed level set)
# --------------------------------------------------------------------------- #


class LevelModel(_StateModel):
    """One entry in ``key-levels.json#levels[]``.

    Consumers: heartbeat level-interaction scoring + ``draw_shape`` charting.
    Required fields are the ones the scorer indexes: ``price``, ``type``,
    ``tier``. ``role`` is nullable (only set for flipped levels), ``strength``
    is optional (added by level_source.py tier->stars mapping, may be absent on
    older rows -- see L142/C26 in the Lessons index).
    """

    price: float
    type: str
    tier: str

    role: Optional[str] = None
    label: Optional[str] = None
    strength: Optional[Any] = None
    entity_id: Optional[str] = None


class KeyLevelsModel(_StateModel):
    """Contract for ``automation/state/key-levels.json``.

    Producer: premarket level audit (08:30) + EOD review.
    Consumers: heartbeat (level proximity / rejection / reclaim triggers) +
    ``chart_drawings`` sync. The load-bearing field is ``levels[]`` -- a silent
    ``None`` (renamed key) would blind every level-based trigger. Each row is
    validated by :class:`LevelModel`.
    """

    schema_version: int
    for_session: str
    levels: List[LevelModel]


# --------------------------------------------------------------------------- #
# JSONL ledger row models (append-only)
# --------------------------------------------------------------------------- #


class DecisionRowModel(_StateModel):
    """Contract for one row of ``automation/state/decisions.jsonl`` (+ aggressive).

    Producer: heartbeat (one row per tick). Consumers: EOD-summary grader,
    analyst pattern miner, ``heartbeat-decision-trace`` skill.
    Required = the fields graders/miners index on every row: ``tick_id``,
    ``date``, ``action``. Everything else (scores, prices, reason) is optional
    so older-schema rows in this long-lived append-only ledger still validate.

    ``account_id`` (``"safe"`` / ``"bold"``) is optional ON THE MODEL so the
    long-lived ledger's pre-enforcement rows (the ~90% audited absent on
    2026-06-18) still validate, BUT the canonical writer
    (:func:`backtest.lib.ledger.append_decision`) now STAMPS it on every NEW row
    by default-from-target-file (base ``decisions.jsonl`` -> ``"safe"``,
    ``aggressive/`` ledger -> ``"bold"``). So new rows always carry it; the EOD /
    weekly group-by-account consumers' "default-by-file" fallback only ever has to
    cover legacy rows. (BP-ACCOUNT-ID-ENFORCE.)
    """

    tick_id: int
    date: str
    action: str

    account_id: Optional[str] = None
    time_et: Optional[str] = None
    bull_score: Optional[float] = None
    bear_score: Optional[float] = None
    setup_name: Optional[str] = None
    trigger: Optional[str] = None
    reason: Optional[str] = None


class WatcherObservationRowModel(_StateModel):
    """Contract for one row of ``automation/state/watcher-observations.jsonl``.

    Producer: the unified watcher layer (WATCH_ONLY shadow observations).
    Consumers: ``watcher-promotion-gates`` / ``watcher-fleet-status`` skills +
    promotion analysis.

    This ledger carries TWO row dialects that coexist (append-only history):
      1. Per-signal rows: have ``watcher_name`` + ``setup_name`` + entry/stop.
      2. Aggregate tick rows: have ``watcher_signals[]`` + ``action`` (newer
         MNQ/unified-layer format).
    Both share ``observed_at``. So ``observed_at`` is the only required field;
    the dialect-specific keys are optional. This is intentional -- the contract
    asserts every row is a timestamped observation, and tolerates both shapes
    rather than rejecting valid historical rows.
    """

    observed_at: str

    # dialect 1 (per-signal)
    watcher_name: Optional[str] = None
    setup_name: Optional[str] = None
    direction: Optional[str] = None
    triggers_fired: Optional[List[Any]] = None

    # dialect 2 (aggregate tick)
    watcher_signals: Optional[List[Any]] = None
    action: Optional[str] = None
    mode: Optional[str] = None

"""j_intent_logic -- PURE decision core for J-called conditional trades.

WHY THIS EXISTS (automation/overnight/queue.md ## J-INTENT-EXECUTOR, J-called
2026-07-15 13:30 ET): J: "you are too slow to decide then implement and making
LLM calls for logic." Today's J-called 752P took ~16 min to arm through a
hand-written one-off watcher that had a stale-bar bug (it evaluated 5m bars
from BEFORE the watcher was even started). Claude's only job at trade time is
now to translate J's sentence into an intent JSON in automation/state/
j-intents.json (<60s, one turn, zero ongoing LLM calls); `j_intent_executor.py`
polls that file and runs the rest of the lifecycle deterministically.

THIS MODULE holds every decision that can be expressed as a pure function of
(intent, bar-history, wall-clock time) -- trigger detection, invalidation,
chart-stop exit-signal, and the ARMED_AT stale-bar guard. It imports nothing
that touches a network, a broker, or the filesystem beyond a single CSV reader
used by the replay test fixture loader. That split (mirrors fast_path_executor.
py's evaluate_alert / heartbeat_core's pure-vs-actuator split, and exit_manager.
py's own "PURE decision core" docstring) is what makes the acceptance-gate
replay test in backtest/tests/test_j_intent_executor_replay.py a provable
statement about LIVE behavior rather than a parallel reimplementation that
could silently drift: `j_intent_executor.py`'s poll loop calls the EXACT SAME
`evaluate_trigger` / `evaluate_invalidation` / `evaluate_chart_stop` /
`is_bar_stale` functions defined here, bar by bar, as new completed bars
arrive live.

BAR-CLOSE CONVENTION (load-bearing -- read before touching trigger logic)
---------------------------------------------------------------------------
Alpaca's bar timestamp is the bar's START. But J's own vocabulary (and the
2026-07-15 journal: "13:15 ET bar: o=752.09 h=752.255 l=751.78 c=751.785")
names a bar by its CLOSE time -- "the 13:15 bar" is the bar that STARTED at
13:10 and CLOSED at 13:15 (verified against the real Alpaca IEX feed: the OHLC
J quoted is the bar with t=2026-07-15T17:10:00Z = 13:10 ET start). Every
function in this module keys off `Bar.close_et` (start + 5min), NEVER
`Bar.start_et`, specifically so this off-by-one-bar ambiguity can never bite
the trigger/stale-bar logic the way it apparently bit today's one-off watcher.

ARMED_AT STALE-BAR GUARD (the exact bug this build exists to fix)
---------------------------------------------------------------------------
`is_bar_stale(bar_close_et, armed_at_et)` is True whenever a bar's CLOSE
happened AT OR BEFORE the moment the intent was armed. Only bars that closed
STRICTLY AFTER arming are eligible evidence for a trigger or invalidation.
`replay_intent_over_bars` enforces this on every bar before evaluating
anything else -- a stale bar can never fire a trigger, no matter what its OHLC
looks like.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

BAR_MINUTES = 5

# Intent lifecycle -- EXACT enum from the queue spec. Do not add states here;
# supplementary detail (why a state was reached) goes in a sibling field
# (e.g. "reason", "risk_gate_code") on the intent record, never a new status.
STATUS_ARMED = "armed"
STATUS_TRIGGERED = "triggered"
STATUS_FILLED = "filled"
STATUS_EXITED = "exited"
STATUS_INVALIDATED = "invalidated"
STATUS_EXPIRED = "expired"
TERMINAL_STATUSES = frozenset({STATUS_EXITED, STATUS_INVALIDATED, STATUS_EXPIRED})


# ============================================================ bar model ====
@dataclass(frozen=True)
class Bar:
    """One completed 5m SPY bar. Immutable (coding-style: never mutate)."""

    start_et: datetime  # naive ET, bar START (Alpaca convention)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def close_et(self) -> datetime:
        """The bar's CLOSE time -- what J/the journal mean by 'the HH:MM bar'.
        See module docstring's BAR-CLOSE CONVENTION section."""
        return self.start_et + timedelta(minutes=BAR_MINUTES)

    @property
    def is_red(self) -> bool:
        return self.close < self.open

    @property
    def is_green(self) -> bool:
        return self.close > self.open


def parse_bar_ts(value: Any) -> datetime:
    """Parse a naive ET timestamp from a CSV row or a live-fetched bar. Accepts
    'YYYY-MM-DD HH:MM:SS', 'YYYY-MM-DDTHH:MM:SS', or an already-naive datetime."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    s = str(value).strip()
    if s.endswith("Z"):
        s = s[:-1]
    s = s.replace("T", " ")
    if len(s) == 16:  # 'YYYY-MM-DD HH:MM' -> add seconds
        s += ":00"
    return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")


def bar_from_row(row: dict) -> Bar:
    """Build a Bar from a CSV DictReader row (fixtures) or an equivalent dict
    (live REST). Missing/unparseable volume defaults to 0 rather than failing
    the whole bar -- volume is never consulted by trigger/invalidation logic."""
    try:
        vol = float(row.get("volume", 0) or 0)
    except (TypeError, ValueError):
        vol = 0.0
    return Bar(
        start_et=parse_bar_ts(row["timestamp_et"]),
        open=float(row["open"]),
        high=float(row["high"]),
        low=float(row["low"]),
        close=float(row["close"]),
        volume=vol,
    )


def load_bars_csv(path: Path) -> list[Bar]:
    """Load a committed fixture (timestamp_et,open,high,low,close,volume) into
    chronologically-sorted Bars. Used by the acceptance-gate replay test; the
    live executor builds the equivalent list from Alpaca REST responses via
    `bar_from_row` on each {timestamp_et,open,high,low,close,volume} dict."""
    bars: list[Bar] = []
    with Path(path).open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            bars.append(bar_from_row(row))
    bars.sort(key=lambda b: b.start_et)
    return bars


# ============================================================ ARMED_AT guard
def is_bar_stale(bar_close_et: datetime, armed_at_et: datetime) -> bool:
    """TRUE iff `bar_close_et` is at/before `armed_at_et` -- i.e. this bar's
    close was already known AT (or before) the moment the intent was armed, so
    it carries zero NEW information and must never be allowed to fire a fresh
    trigger or invalidation. This is the exact guard today's one-off watcher
    was missing (queue: 'it evaluated bars from BEFORE arming -- never
    reintroduce'). Strict `<=`: a bar closing in the SAME instant as arming is
    still treated as pre-existing knowledge, not fresh evidence."""
    return bar_close_et <= armed_at_et


def parse_et(value: str) -> datetime:
    """Parse an intent's 'created_et' / 'expiry_et' style naive-ET string.
    Accepts full timestamps ('2026-07-15T12:56:00') or a bare 'HH:MM'/'HH:MM:SS'
    time-of-day (paired separately with a date by the caller when needed)."""
    s = str(value).strip()
    if "T" in s or " " in s or "-" in s:
        return parse_bar_ts(s)
    parts = s.split(":")
    hh = int(parts[0])
    mm = int(parts[1]) if len(parts) > 1 else 0
    ss = int(parts[2]) if len(parts) > 2 else 0
    # Time-of-day only -- caller must combine with a date; return a sentinel
    # datetime on 1900-01-01 so comparisons against a same-day-combined value
    # never accidentally match. Callers needing time-of-day semantics should
    # use `combine_today` instead of calling parse_et directly on "HH:MM".
    return datetime(1900, 1, 1, hh, mm, ss)


def combine_today(date_et: datetime, hhmm: str) -> datetime:
    """Combine a date (from any ET datetime) with an 'HH:MM'[:SS] string."""
    parts = str(hhmm).strip().split(":")
    hh = int(parts[0])
    mm = int(parts[1]) if len(parts) > 1 else 0
    ss = int(parts[2]) if len(parts) > 2 else 0
    return date_et.replace(hour=hh, minute=mm, second=ss, microsecond=0)


# ============================================================ pure evaluators
def evaluate_trigger(trigger: dict, bar: Bar) -> bool:
    """Bar-level trigger test for a COMPLETED-BAR trigger type. Fail-closed:
    an unknown/malformed type or a spec missing its required level(s) never
    fires (returns False), it does not raise.

    "level_reject_confirmed_close" -- J's 2026-07-15 752P shape: the bar TAGS
      the level (high >= tag_level) and CLOSES back below the confirm level
      (close < confirm_close_below); require_red_bar (default True) also
      demands close < open, so a bar that tags-and-recovers green never fires.

    "level_reclaim_confirmed_close" -- the mirror bullish shape: bar TAGS the
      level from above (low <= tag_level) and CLOSES back above the confirm
      level (close > confirm_close_above); require_green_bar (default True)
      demands close > open.

    "live_bid_cross" is NOT evaluated here -- it is not bar-based (see
    `evaluate_live_bid_cross`); a bar-replay caller that encounters this type
    on a bar-triggered intent gets False (never a spurious bar-based fire).
    """
    ttype = str(trigger.get("type", ""))
    if ttype == "level_reject_confirmed_close":
        tag = trigger.get("tag_level")
        confirm = trigger.get("confirm_close_below")
        if tag is None or confirm is None:
            return False
        ok = bar.high >= float(tag) and bar.close < float(confirm)
        if trigger.get("require_red_bar", True):
            ok = ok and bar.is_red
        return ok
    if ttype == "level_reclaim_confirmed_close":
        tag = trigger.get("tag_level")
        confirm = trigger.get("confirm_close_above")
        if tag is None or confirm is None:
            return False
        ok = bar.low <= float(tag) and bar.close > float(confirm)
        if trigger.get("require_green_bar", True):
            ok = ok and bar.is_green
        return ok
    return False


def evaluate_live_bid_cross(trigger: dict, side: str, live_price: Optional[float]) -> bool:
    """live_bid_cross mode: fires the instant the live underlying price
    crosses tag_level, no completed-bar wait. side='P' (bear) crosses DOWN
    through tag_level (live_price <= tag_level); side='C' (bull) crosses UP
    through it. Generalizes the memory'd "aggressive live trigger: Bold enters
    on live bid crossing the level, not a closed bar" rule to any J-called
    intent that explicitly opts into type=live_bid_cross. False on missing
    inputs (fail-closed)."""
    if str(trigger.get("type", "")) != "live_bid_cross":
        return False
    tag = trigger.get("tag_level")
    if tag is None or live_price is None:
        return False
    return float(live_price) <= float(tag) if side == "P" else float(live_price) >= float(tag)


def evaluate_invalidation(invalidation: dict, bar: Bar) -> bool:
    """True iff this bar's close breaches the stated invalidation level(s).
    `invalidation` may carry EITHER close_above OR close_below (never both in
    practice, but both are honored if present -- an OR, matching 'stand down
    if the line reclaims OR breaks', a rare but valid dual-invalidation)."""
    if not invalidation:
        return False
    above = invalidation.get("close_above")
    if above is not None and bar.close > float(above):
        return True
    below = invalidation.get("close_below")
    if below is not None and bar.close < float(below):
        return True
    return False


def chart_stop_trigger_level(intent: dict) -> Optional[float]:
    """The numeric level from this intent's exits.chart_stop (whichever of
    close_above/close_below is set). None when absent/malformed."""
    cs = (intent.get("exits") or {}).get("chart_stop") or {}
    if cs.get("close_above") is not None:
        return float(cs["close_above"])
    if cs.get("close_below") is not None:
        return float(cs["close_below"])
    return None


def evaluate_chart_stop(intent: dict, bar: Bar, structure_stop_hit_fn) -> bool:
    """Chart-stop exit-SIGNAL test for a bar. Delegates the actual close-vs-
    level comparison to `structure_stop_hit_fn(side, trigger_level, close)` --
    the caller passes `exit_manager._structure_stop_hit` so this replay-tested
    signal and the LIVE position-management stop (exit_manager.plan_exit_
    actions, which also calls _structure_stop_hit) can never drift (gamma-sync
    doctrine: ONE implementation of 'is the chart stop hit', never two).
    side='P' fires on close > level, side='C' fires on close < level -- for
    the 2026-07-15 752P: chart stop = 5m close > 752.26."""
    level = chart_stop_trigger_level(intent)
    if level is None:
        return False
    return bool(structure_stop_hit_fn(intent.get("side"), level, bar.close))


# ============================================================ replay engine
@dataclass(frozen=True)
class ReplayTrace:
    """One bar's evaluation outcome -- the audit trail a replay/live run keeps
    so 'why did/didn't this fire' is always answerable from the record."""

    bar_close_et: datetime
    stale: bool = False
    invalidation_hit: bool = False
    trigger_hit: bool = False
    chart_stop_hit: bool = False
    expired: bool = False


@dataclass(frozen=True)
class ReplayResult:
    triggered_at: Optional[datetime] = None
    invalidated_at: Optional[datetime] = None
    exit_signal_at: Optional[datetime] = None
    expired: bool = False
    trace: tuple = field(default_factory=tuple)

    @property
    def status(self) -> str:
        if self.exit_signal_at is not None:
            return STATUS_EXITED
        if self.triggered_at is not None:
            return STATUS_FILLED
        if self.invalidated_at is not None:
            return STATUS_INVALIDATED
        if self.expired:
            return STATUS_EXPIRED
        return STATUS_ARMED


def replay_intent_over_bars(
    intent: dict,
    bars: list[Bar],
    armed_at_et: datetime,
    *,
    expiry_et: Optional[datetime] = None,
    structure_stop_hit_fn=None,
) -> ReplayResult:
    """PURE bar-by-bar walk of ONE intent's lifecycle signal: stale-guard ->
    (pre-trigger) invalidation-or-trigger -> (post-trigger) chart-stop exit
    signal. This is the SAME function the live poll loop drives one new bar at
    a time (see j_intent_executor.py's `_advance_intent_on_new_bar`), so a
    passing replay test is a provable statement about live signal timing, not
    a parallel reimplementation.

    `structure_stop_hit_fn` defaults to a local close_above/close_below
    comparison equivalent to exit_manager._structure_stop_hit when the caller
    does not want the exit_manager dependency (e.g. a logic-only unit test);
    the live executor and the acceptance-gate test both pass the REAL
    exit_manager._structure_stop_hit so there is zero drift risk on the path
    that actually matters.
    """
    if structure_stop_hit_fn is None:
        def structure_stop_hit_fn(side, level, close):  # noqa: ANN001
            if level is None or close is None:
                return False
            return (close < level) if side == "C" else (close > level)

    trigger_spec = intent.get("trigger") or {}
    invalidation_spec = intent.get("invalidation") or {}

    triggered_at: Optional[datetime] = None
    invalidated_at: Optional[datetime] = None
    exit_signal_at: Optional[datetime] = None
    expired = False
    trace: list[ReplayTrace] = []

    for bar in sorted(bars, key=lambda b: b.start_et):
        bclose = bar.close_et

        if is_bar_stale(bclose, armed_at_et):
            trace.append(ReplayTrace(bclose, stale=True))
            continue

        if triggered_at is None and invalidated_at is None:
            if expiry_et is not None and bclose > expiry_et:
                expired = True
                trace.append(ReplayTrace(bclose, expired=True))
                break
            if evaluate_invalidation(invalidation_spec, bar):
                invalidated_at = bclose
                trace.append(ReplayTrace(bclose, invalidation_hit=True))
                break  # terminal -- a J-called intent does not get a second life
            if evaluate_trigger(trigger_spec, bar):
                triggered_at = bclose
                trace.append(ReplayTrace(bclose, trigger_hit=True))
                continue  # keep walking bars to also resolve the exit signal
            trace.append(ReplayTrace(bclose))
            continue

        if triggered_at is not None and exit_signal_at is None:
            hit = evaluate_chart_stop(intent, bar, structure_stop_hit_fn)
            trace.append(ReplayTrace(bclose, chart_stop_hit=hit))
            if hit:
                exit_signal_at = bclose
                break
            continue

        break  # fully resolved (triggered + exited) -- nothing more to evaluate

    return ReplayResult(
        triggered_at=triggered_at,
        invalidated_at=invalidated_at,
        exit_signal_at=exit_signal_at,
        expired=expired,
        trace=tuple(trace),
    )


# ============================================================ intent helpers
REQUIRED_INTENT_FIELDS = ("id", "created_et", "account", "side", "trigger",
                          "sizing", "exits", "status")


def validate_intent(intent: dict) -> Optional[str]:
    """Structural validation. Returns an error string, or None when valid.
    Deliberately permissive on VALUES (a bad numeric level is a research-time
    mistake, not a schema violation) but strict on SHAPE -- a malformed intent
    must never silently no-op its way into 'armed but unevaluable'."""
    if not isinstance(intent, dict):
        return "intent must be a dict"
    for field_name in REQUIRED_INTENT_FIELDS:
        if field_name not in intent:
            return f"missing required field {field_name!r}"
    if intent["account"] not in ("safe", "bold"):
        return f"account must be 'safe' or 'bold', got {intent['account']!r}"
    if intent["side"] not in ("P", "C"):
        return f"side must be 'P' or 'C', got {intent['side']!r}"
    if not isinstance(intent["trigger"], dict) or "type" not in intent["trigger"]:
        return "trigger must be a dict with a 'type' key"
    if intent["trigger"]["type"] not in (
        "level_reject_confirmed_close", "level_reclaim_confirmed_close", "live_bid_cross",
    ):
        return f"unknown trigger.type {intent['trigger']['type']!r}"
    if not isinstance(intent["exits"], dict):
        return "exits must be a dict"
    if intent["status"] not in (
        STATUS_ARMED, STATUS_TRIGGERED, STATUS_FILLED, STATUS_EXITED,
        STATUS_INVALIDATED, STATUS_EXPIRED,
    ):
        return f"unknown status {intent['status']!r}"
    return None


def new_intent_id(now_et: datetime, slug: str = "put") -> str:
    """id convention: j-intent-YYYYMMDD-HHMMSS-<slug>. Deterministic given
    (now_et, slug) so tests can assert exact ids."""
    return f"j-intent-{now_et.strftime('%Y%m%d-%H%M%S')}-{slug}"

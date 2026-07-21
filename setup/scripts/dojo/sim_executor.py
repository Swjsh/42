"""dojo/sim_executor.py -- SIM-ONLY trade execution for DOJO replay sessions.

Fills J-directed trades from HISTORICAL option data (never live, never a broker), then
walks each open position forward via the REAL exit_manager decision core
(backtest/lib/exit_manager_walk.py -- the byte-identical mechanism the live engine runs,
built + faithfulness-tested 2026-07-17/20) using THAT ARM's own exit profile. See
markdown/specs/DOJO-ARCHITECTURE-DECISION.md `sim_executor.py (Agent C)` for the frozen
contract. session.py (frozen -- not edited by this build) calls exactly:

    sim_executor.arm_directive(session_id, directive, dojo_dir=DOJO_DIR)          -> None
    sim_executor.advance_session(session_id, bar_et, bars_df, dojo_dir=DOJO_DIR)  -> list[dict]

HARD FENCE: no alpaca/broker/place_order import anywhere in this module (guard-tested,
backtest/tests/test_dojo_no_broker.py). Every position is a DojoPosition persisted at
dojo_dir/sessions/<session_id>-positions.json -- never a broker order, never a git op.

ARM NAMING (load-bearing, confirmed against the already-written whisper/directive guard
tests -- backtest/tests/test_dojo_whisper.py, test_dojo_directive.py): the dojo package
uses the SAME short core-account aliases heartbeat_core.py's own `ACCOUNTS` dict uses --
"safe"/"bold" -- NOT accounts.json's "safe-2"/"bold-2" ids. Fleet arms keep their real
accounts.json id ("safe-3"/"risky-1"/"risky-3"). `_resolve_arm_cfg` below is the single
place that reconciles the two; a directive's `arms` list is never mutated to the
canonical id, so `DojoPosition.arm` always matches what J said and what whisper/directive
already render, and `accounts_arm_id` carries the canonical accounts.json id alongside it.

WHY walk_exit_manager IS RE-CALLED EVERY STEP (not resumed): walk_exit_manager is a PURE,
side-effect-free function that walks an ENTIRE opt_df from entry to resolution (or to the
end of the data it was given) -- it has no notion of "advance one more bar." Calling it
fresh each `advance_session` tick with the option series truncated to <= the current bar
is deterministic and idempotent (same inputs -> same legs), so this module simply re-walks
from entry through "now" every tick and diffs against what it already recorded
(`last_advanced_bar_et`) to find NEWLY-fired legs this step. The one wrinkle: when fed a
truncated series, walk_exit_manager force-closes at the LAST available bar
("data_exhausted_force_close") if nothing has resolved yet -- exactly correct for a
one-shot full-day replay, WRONG for an incremental tick (it would force-close every open
position on every single step). This module therefore always strips that phantom leg;
a position only ever closes here via a REAL exit_manager decision (TP1+trail, stop,
ribbon_flip, structure_stop, time_stop) that itself falls within the fed bar range --
which is exactly the same event that would have closed it live.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any, Mapping, Optional
from zoneinfo import ZoneInfo

import pandas as pd

# --- path setup (mirrors session.py / clock.py / futures_edge3_sim.py pattern). Added
# defensively so this module works BOTH when found via `from dojo import sim_executor`
# (package-qualified) and via the bare `import sim_executor` session.py's cmd_directive /
# cmd_step / cmd_close actually call -- see build report for the sys.path gap this works
# around (session.py's own path loop adds "backtest"/"setup/scripts"/"automation/state/
# fleet", never "setup/scripts/dojo" itself, so a bare sibling import only resolves once
# *some* module already sitting on sys.path pulls this directory in; self-registering here
# costs nothing and fixes it for every import path).
_THIS_DIR = Path(__file__).resolve().parent               # .../setup/scripts/dojo
_ROOT = _THIS_DIR.parents[2]                               # .../42
for _p in (_THIS_DIR, _ROOT / "backtest", _ROOT / "setup" / "scripts",
           _ROOT / "automation" / "state" / "fleet"):
    _ap = str(_p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import bar_at_or_after, load_contract_bars, option_symbol  # noqa: E402
from lib import pricing as bs_pricing  # noqa: E402
import fleet_executor  # noqa: E402  -- reuse _exit_shape_dict / exit_patch / tier logic. Pure
# Python (importlib-loaded strategies/risk_gate/strike_selection by absolute path -- see
# fleet_executor.py's own docstring); no alpaca/broker import anywhere in its graph
# (verified 2026-07-20 building this module -- test_dojo_no_broker.py pins it).

ET = ZoneInfo("America/New_York")
DATA_DIR = _ROOT / "backtest" / "data"
POSITIONS_SUFFIX = "-positions.json"

# Mirrors setup/scripts/heartbeat_core.py::ACCOUNTS's short-name -> fleet-arm-id mapping.
# NOT imported from there directly -- heartbeat_core.py IS the live trading engine module
# and pulls in far more than this 2-line table; re-declaring it here keeps this module's
# import graph sim-only. If heartbeat_core.py's ACCOUNTS dict ever adds a third account or
# renames an id, update both (drift risk disclosed, not hidden).
CORE_ARM_ALIASES: dict[str, str] = {"safe": "safe-2", "bold": "bold-2"}

CORE_SAFE_PARAMS = "automation/state/params.json"
DEFAULT_TIME_STOP_ET = "15:50"
DEFAULT_MIN_CONTRACTS = 3
DEFAULT_SYNTHETIC_VIX = 15.0  # disclosed fallback when even the VIX cache can't cover trade_date
_FILENAME_RANGE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(?:_merged)?\.csv$")


# =====================================================================================
# DojoPosition -- the sim-only position record. Never a broker order.
# =====================================================================================
@dataclass
class DojoPosition:
    """ONE sim-executed leg of a J-directed dojo trade, for ONE arm. Immutable-by-convention
    at construction (arm_directive builds it once); advance_session mutates the persisted
    dict form in place (positions.json), never this dataclass directly -- matches
    ExitState's own "dict is the wire format, dataclass is the constructor" split
    (automation/state/fleet/exit_manager.py) elsewhere in this codebase."""
    position_id: str
    directive_id: str
    session_id: str
    arm: str                      # dojo-standard id: "safe" | "bold" | "safe-3" | "risky-1" | "risky-3"
    accounts_arm_id: str          # canonical accounts.json id ("safe-2"/"bold-2" for core)
    symbol: str
    side: str                     # "C" | "P"
    strike: int
    qty: int
    open_qty: int
    entry_time_et: str            # naive ET isoformat
    entry_premium: float
    price_source: str             # "opra_5m" | "bs_synthetic" | "no_fill"
    is_synthetic: bool
    exit_shape: dict
    strategy: str
    trigger_level: Optional[float]
    structure_stop_enabled: bool
    time_stop_et: str             # "HH:MM"
    status: str = "OPEN"          # "OPEN" | "CLOSED" | "NO_FILL" | "ERROR"
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    exit_reason: Optional[str] = None
    exit_time_et: Optional[str] = None
    legs: list = field(default_factory=list)
    last_advanced_bar_et: Optional[str] = None
    note: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "DojoPosition":
        return DojoPosition(**{k: d.get(k) for k in DojoPosition.__dataclass_fields__})


# =====================================================================================
# small generic helpers
# =====================================================================================
def _field(obj: Any, name: str, default: Any = None) -> Any:
    """Attribute-or-mapping-key read that works on a dataclass instance, a plain dict, or
    a SimpleNamespace -- directive.py's real DojoDirective type may not exist yet when
    this module is exercised standalone (see whisper.py's own guard tests, which hit the
    identical situation for engine_step.DojoDecision)."""
    if obj is None:
        return default
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _now_et_iso() -> str:
    return datetime.now(ET).isoformat()


def _strip_tz(value: datetime) -> datetime:
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(ET).replace(tzinfo=None)
    return value


def _to_naive_et_series(series: pd.Series) -> pd.Series:
    if not pd.api.types.is_datetime64_any_dtype(series):
        series = pd.to_datetime(series)
    if getattr(series.dt, "tz", None) is not None:
        series = series.dt.tz_convert(ET).dt.tz_localize(None)
    return series


def _cursor_to_naive_et(value: Any) -> datetime:
    """Robust cursor parser: accepts a TV replay epoch (int/float, via dojo.clock -- the
    SAME resolver session.py/clock.py use, so an epoch cursor threaded straight through a
    directive resolves identically to the step loop), a tz-aware/naive datetime (the real
    DojoDirective.cursor_et shape per test_dojo_directive.py), or an ISO string."""
    if isinstance(value, (int, float)):
        try:
            from dojo import clock as _clock  # noqa: PLC0415
        except ImportError:
            import clock as _clock  # noqa: PLC0415
        return _strip_tz(_clock.resolve_cursor(value))
    if isinstance(value, datetime):
        return _strip_tz(value)
    if isinstance(value, str):
        return _strip_tz(datetime.fromisoformat(value))
    raise ValueError(f"cannot parse directive cursor_et value {value!r}")


def _normalize_side(raw: Any) -> str:
    s = str(raw).strip().upper()
    if s in ("C", "CALL", "BULL", "BULLISH", "LONG"):
        return "C"
    if s in ("P", "PUT", "BEAR", "BEARISH", "SHORT"):
        return "P"
    raise ValueError(f"cannot normalize directive side {raw!r} to C/P")


def _parse_hhmm(value: Any) -> dt_time:
    if isinstance(value, dt_time):
        return value
    parts = str(value).split(":")
    return dt_time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)


def _trigger_level_from(directive: Any) -> Optional[float]:
    """Best-effort numeric chart level for the structure-stop reference. Checked against
    the REAL directive.py fixture shape (test_dojo_directive.py's VALID_RAW):
    trigger={"type": ..., "tag_level": 600.0, "confirm_close_above": 600.5},
    invalidation={"close_below": 599.0}. `tag_level` is preferred (it is the SAME level
    the live path's rejection_level/trigger_level threads through exit_manager -- "the
    level the entry fired against", per heartbeat_core.py:1611-1617); invalidation keys are
    the documented fallback. Absent/unrecognised shape -> None (falls back to "premium"
    stop mode, never crashes)."""
    def _scan(d: Any, keys: tuple[str, ...]) -> Optional[float]:
        if isinstance(d, (int, float)):
            return float(d)
        if isinstance(d, Mapping):
            for k in keys:
                v = d.get(k)
                if isinstance(v, (int, float)):
                    return float(v)
        return None

    trig = _field(directive, "trigger")
    lvl = _scan(trig, ("tag_level", "level", "price", "value"))
    if lvl is not None:
        return lvl
    inval = _field(directive, "invalidation")
    return _scan(inval, ("close_below", "close_above", "level", "price", "value"))


# =====================================================================================
# dated cache-file selection (SPY 5m / VIX 5m) -- generic glob-by-date-range picker.
# =====================================================================================
def _pick_dated_cache(glob_pattern: str, trade_date: date) -> Optional[Path]:
    """Among files matching `<prefix>_<start>_<end>[_merged].csv`, prefer one whose
    [start, end] covers trade_date (most specific/latest start wins on ties); if none
    covers it, fall back to the file with the largest end date (best-effort, never a hard
    failure -- the caller (BS-synthetic fallback path) discloses when this happens)."""
    covering: list[tuple[date, date, Path]] = []
    any_file: list[tuple[date, Path]] = []
    for p in DATA_DIR.glob(glob_pattern):
        m = _FILENAME_RANGE_RE.search(p.name)
        if not m:
            continue
        start = date.fromisoformat(m.group(1))
        end = date.fromisoformat(m.group(2))
        any_file.append((end, p))
        if start <= trade_date <= end:
            covering.append((start, end, p))
    if covering:
        covering.sort(key=lambda t: t[0])  # latest (largest) start = most specific
        return covering[-1][2]
    if any_file:
        any_file.sort(key=lambda t: t[0])
        return any_file[-1][1]
    return None


_SPY_CACHE: dict[date, Optional[pd.DataFrame]] = {}


def _load_spy_5m_for_date(trade_date: date) -> Optional[pd.DataFrame]:
    if trade_date in _SPY_CACHE:
        return _SPY_CACHE[trade_date]
    path = _pick_dated_cache("spy_5m_*.csv", trade_date)
    if path is None:
        _SPY_CACHE[trade_date] = None
        return None
    df = pd.read_csv(path)
    df["timestamp_et"] = _to_naive_et_series(df["timestamp_et"])
    day = df.loc[df["timestamp_et"].dt.date == trade_date]
    rth = day.loc[(day["timestamp_et"].dt.time >= dt_time(9, 30))
                   & (day["timestamp_et"].dt.time < dt_time(16, 0))]
    result = rth.sort_values("timestamp_et").reset_index(drop=True)
    _SPY_CACHE[trade_date] = result if not result.empty else None
    return _SPY_CACHE[trade_date]


_VIX_CACHE: dict[date, Optional[pd.DataFrame]] = {}


def _load_vix_5m_for_date(trade_date: date) -> Optional[pd.DataFrame]:
    if trade_date in _VIX_CACHE:
        return _VIX_CACHE[trade_date]
    path = _pick_dated_cache("vix_5m_*.csv", trade_date)
    if path is None:
        _VIX_CACHE[trade_date] = None
        return None
    df = pd.read_csv(path)
    df["timestamp_et"] = _to_naive_et_series(df["timestamp_et"])
    result = df.sort_values("timestamp_et").reset_index(drop=True)
    _VIX_CACHE[trade_date] = result
    return result


def _vix_at(vix_df: Optional[pd.DataFrame], when_et: datetime) -> float:
    if vix_df is None:
        return DEFAULT_SYNTHETIC_VIX
    eligible = vix_df.loc[vix_df["timestamp_et"] <= when_et]
    if eligible.empty:
        return DEFAULT_SYNTHETIC_VIX
    return float(eligible.iloc[-1]["close"])


def _spot_at(spy_df: pd.DataFrame, cursor_et_naive: datetime) -> Optional[float]:
    eligible = spy_df.loc[spy_df["timestamp_et"] <= cursor_et_naive]
    if eligible.empty:
        return None
    return float(eligible.iloc[-1]["close"])


# =====================================================================================
# option data -- real OPRA 5-min cache first, BS-synthetic fallback FLAGGED (never
# silent), per Free-Kitchen-Plan-B doctrine (markdown/planning/FREE-AGENT-PLAN-B-KITCHEN.md
# -- "Black-Scholes synthetic layer flagged is_synthetic for ranking-only, never WR
# authority"). Every synthetic row also carries `price_source="bs_synthetic"`.
# =====================================================================================
def _synthesize_option_bars(spy_day_bars: pd.DataFrame, strike: int, side: str,
                             trade_date: date) -> pd.DataFrame:
    vix_df = _load_vix_5m_for_date(trade_date)
    rows = []
    is_call = side == "C"
    for _, r in spy_day_bars.iterrows():
        ts = r["timestamp_et"]
        ts_py = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        spot = float(r["close"])
        vix = _vix_at(vix_df, ts_py)
        iv = bs_pricing.vix_to_iv(vix)
        tte = bs_pricing.time_to_expiry_years(ts_py)
        price, _delta = bs_pricing.black_scholes(spot, float(strike), iv, tte, is_call=is_call)
        price = max(0.01, round(float(price), 4))
        rows.append({"timestamp_et": ts_py, "open": price, "high": price, "low": price,
                      "close": price, "volume": 0, "vwap": price, "trade_count": 0})
    return pd.DataFrame(rows)


def _load_option_series(symbol: str, side: str, strike: int, trade_date: date,
                         spy_df: pd.DataFrame) -> tuple[pd.DataFrame, str, bool]:
    """(opt_df, price_source, is_synthetic). Real OPRA 5-min cache
    (backtest/data/options/{symbol}.csv, via option_pricing_real.load_contract_bars) is
    authority; BS-synthetic (backtest/lib/pricing.py) is the disclosed ranking-only
    fallback when that contract was never cached for this date."""
    real = load_contract_bars(symbol)
    if real is not None and not real.empty:
        df = real.copy()
        df["timestamp_et"] = _to_naive_et_series(df["timestamp_et"])
        return df.sort_values("timestamp_et").reset_index(drop=True), "opra_5m", False
    day_bars = spy_df.loc[spy_df["timestamp_et"].dt.date == trade_date]
    synth = _synthesize_option_bars(day_bars, strike, side, trade_date)
    return synth, "bs_synthetic", True


# =====================================================================================
# accounts.json / exit-shape resolution (reuses fleet_executor -- never reinvents)
# =====================================================================================
_ACCOUNTS_CACHE: Optional[dict] = None
_PARAMS_CACHE: dict[str, dict] = {}


def _accounts() -> dict:
    global _ACCOUNTS_CACHE
    if _ACCOUNTS_CACHE is None:
        _ACCOUNTS_CACHE = json.loads(fleet_executor.ACCOUNTS_PATH.read_text(encoding="utf-8"))
    return _ACCOUNTS_CACHE


def _params_for(relpath: str) -> dict:
    if relpath not in _PARAMS_CACHE:
        _PARAMS_CACHE[relpath] = json.loads((_ROOT / relpath).read_text(encoding="utf-8"))
    return _PARAMS_CACHE[relpath]


def _resolve_arm_cfg(arm_id: str) -> tuple[dict, str]:
    """(accounts.json arm entry, canonical accounts.json id). `arm_id` is the dojo-
    standard id a directive carries -- "safe"/"bold" for the core accounts (see
    CORE_ARM_ALIASES) or a fleet arm's real accounts.json id ("safe-3"/"risky-1"/
    "risky-3") verbatim. Fails LOUD on an unrecognised id (C14 -- never a silent skip),
    even though directive.py's own parse_and_validate is meant to have already rejected
    this upstream; this module is defense-in-depth, and is exercised standalone in its
    own tests without directive.py in the loop."""
    canonical = CORE_ARM_ALIASES.get(arm_id, arm_id)
    for a in _accounts().get("arms", []):
        if a.get("id") == canonical:
            return a, canonical
    raise ValueError(
        f"dojo directive targets unknown arm id {arm_id!r} "
        f"(no accounts.json arm and no CORE_ARM_ALIASES entry matched {canonical!r})"
    )


def _time_stop_et_for(arm_cfg: Mapping[str, Any]) -> str:
    cfg_source = arm_cfg.get("config_source")
    if isinstance(cfg_source, str) and cfg_source.endswith(".json"):
        try:
            return str(_params_for(cfg_source).get("time_stop_et", DEFAULT_TIME_STOP_ET))
        except (OSError, json.JSONDecodeError):
            pass
    # Fleet arms carry no own time_stop_et (accounts.json has none) -- share v15.3 gate
    # doctrine's core-Safe value, matching replay_today_eval.py's own documented convention.
    return str(_params_for(CORE_SAFE_PARAMS).get("time_stop_et", DEFAULT_TIME_STOP_ET))


def _structure_stop_enabled() -> bool:
    return bool(_params_for(CORE_SAFE_PARAMS).get("structure_stop_enabled", False))


def _resolve_exit_shape(arm_cfg: Mapping[str, Any], strategy_name: str,
                         directive_exits: Any) -> dict:
    """3-layer merge, all reused: (1) strategies.py REGISTRY shape for `strategy_name`
    (default ribbon_ride -- directive.py's frozen schema carries no `strategy` field, so
    every dojo directive rides the flagship edge unless a future field says otherwise);
    (2) the arm's OWN accounts.json params_patch.exit_patch (fleet_executor._exit_shape_dict
    -- byte-identical to the live merge); (3) THIS directive's session-level `exits`
    override (validated against the exact same EXIT_PATCH_ALLOWED_KEYS vocabulary), which
    wins last -- J's live-session instruction is the most specific layer."""
    strat = fleet_executor.strategies.by_name(strategy_name) or fleet_executor.strategies.RIBBON_RIDE
    base = fleet_executor._exit_shape_dict(strat, arm_cfg)
    if directive_exits:
        patch = fleet_executor._validate_exit_patch(str(arm_cfg.get("id", "?")), directive_exits)
        base = {**base, **patch}
    return base


def _strike_for(arm_cfg: Mapping[str, Any], spot: float, side: str) -> int:
    tiers = fleet_executor._tiers_for_arm(arm_cfg)
    equity = float(arm_cfg.get("starting_equity", 2000.0))
    return fleet_executor.strike_selection.pick_strike(spot, equity, side, tiers)


def _qty_for(directive: Any, arm_id: str) -> int:
    sizing = _field(directive, "sizing")
    if isinstance(sizing, Mapping):
        per_arm = sizing.get(arm_id)
        if isinstance(per_arm, (int, float)):
            return max(1, int(per_arm))
        qty = sizing.get("qty")
        if isinstance(qty, (int, float)):
            return max(1, int(qty))
    elif isinstance(sizing, (int, float)):
        return max(1, int(sizing))
    return DEFAULT_MIN_CONTRACTS


# =====================================================================================
# positions.json persistence
# =====================================================================================
def _positions_path(session_id: str, dojo_dir: Path) -> Path:
    return Path(dojo_dir) / "sessions" / f"{session_id}{POSITIONS_SUFFIX}"


def _load_positions(session_id: str, dojo_dir: Path) -> dict:
    p = _positions_path(session_id, dojo_dir)
    if not p.exists():
        return {}
    raw = json.loads(p.read_text(encoding="utf-8"))
    return raw.get("positions", {})


def _save_positions(session_id: str, dojo_dir: Path, positions: dict) -> None:
    p = _positions_path(session_id, dojo_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {"session_id": session_id, "updated_et": _now_et_iso(), "positions": positions}
    p.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")


# =====================================================================================
# PUBLIC CONTRACT -- exactly what session.py calls
# =====================================================================================
def arm_directive(session_id: str, directive: Any, dojo_dir: Path) -> None:
    """Persist the directed entry as a pending/armed sim position -- ONE DojoPosition per
    targeted arm, each carrying THAT arm's own exit profile. Fills from historical option
    data at the directive's cursor (5-min OPRA cache; BS-synthetic fallback FLAGGED, never
    silent). Never raises on a single arm's failure -- each arm is independent, so one bad
    arm (unknown id, no data) is recorded as a NO_FILL/ERROR position with a disclosed
    `note`, not a crash that drops every other arm in the same directive."""
    dojo_dir = Path(dojo_dir)
    directive_id = _field(directive, "id") or f"{session_id}-{_now_et_iso()}"
    arms_raw = _field(directive, "arms") or []
    if isinstance(arms_raw, str):
        arms_raw = [arms_raw]
    side = _normalize_side(_field(directive, "side"))
    strategy_name = str(_field(directive, "strategy", "ribbon_ride") or "ribbon_ride")
    cursor_et_naive = _cursor_to_naive_et(_field(directive, "cursor_et"))
    trade_date = cursor_et_naive.date()
    trigger_level = _trigger_level_from(directive)
    directive_exits = _field(directive, "exits")
    note = _field(directive, "note")
    structure_enabled = _structure_stop_enabled()

    spy_df = _load_spy_5m_for_date(trade_date)
    spot = _spot_at(spy_df, cursor_et_naive) if spy_df is not None else None

    positions = _load_positions(session_id, dojo_dir)
    for arm_id in arms_raw:
        pos_id = f"{directive_id}-{arm_id}"
        try:
            arm_cfg, canonical = _resolve_arm_cfg(arm_id)
            if spy_df is None or spot is None:
                positions[pos_id] = DojoPosition(
                    position_id=pos_id, directive_id=directive_id, session_id=session_id,
                    arm=arm_id, accounts_arm_id=canonical, symbol="", side=side, strike=0,
                    qty=0, open_qty=0, entry_time_et=cursor_et_naive.isoformat(),
                    entry_premium=0.0, price_source="no_fill", is_synthetic=False,
                    exit_shape={}, strategy=strategy_name, trigger_level=trigger_level,
                    structure_stop_enabled=structure_enabled,
                    time_stop_et=_time_stop_et_for(arm_cfg), status="NO_FILL",
                    note=f"no SPY 5m bars available for {trade_date} -- cannot price this directive",
                ).to_dict()
                continue
            qty = _qty_for(directive, arm_id)
            strike = _strike_for(arm_cfg, spot, side)
            symbol = option_symbol(trade_date, strike, side)
            opt_df, price_source, is_synth = _load_option_series(symbol, side, strike, trade_date, spy_df)
            fill = bar_at_or_after(opt_df, cursor_et_naive) if opt_df is not None and not opt_df.empty else None
            if fill is None:
                positions[pos_id] = DojoPosition(
                    position_id=pos_id, directive_id=directive_id, session_id=session_id,
                    arm=arm_id, accounts_arm_id=canonical, symbol=symbol, side=side,
                    strike=strike, qty=qty, open_qty=qty,
                    entry_time_et=cursor_et_naive.isoformat(), entry_premium=0.0,
                    price_source=price_source, is_synthetic=is_synth, exit_shape={},
                    strategy=strategy_name, trigger_level=trigger_level,
                    structure_stop_enabled=structure_enabled,
                    time_stop_et=_time_stop_et_for(arm_cfg), status="NO_FILL",
                    note=(f"no option bar at/after cursor {cursor_et_naive.isoformat()} for "
                          f"{symbol} (source={price_source}) -- directive not filled"),
                ).to_dict()
                continue
            exit_shape = _resolve_exit_shape(arm_cfg, strategy_name, directive_exits)
            pos = DojoPosition(
                position_id=pos_id, directive_id=directive_id, session_id=session_id,
                arm=arm_id, accounts_arm_id=canonical, symbol=symbol, side=side,
                strike=strike, qty=qty, open_qty=qty,
                entry_time_et=fill.timestamp_et.isoformat(), entry_premium=round(fill.vwap, 4),
                price_source=price_source, is_synthetic=is_synth, exit_shape=exit_shape,
                strategy=strategy_name, trigger_level=trigger_level,
                structure_stop_enabled=structure_enabled, time_stop_et=_time_stop_et_for(arm_cfg),
                status="OPEN", note=note,
            )
            positions[pos_id] = pos.to_dict()
        except Exception as exc:  # noqa: BLE001 -- deliberate: one arm's failure must never
            # silently drop the whole multi-arm directive (C7/OP-33) OR crash the session
            # loop; recorded as a visible ERROR position with the reason, never swallowed.
            positions[pos_id] = {
                "position_id": pos_id, "directive_id": directive_id, "session_id": session_id,
                "arm": arm_id, "status": "ERROR", "note": f"arm_directive failed: {exc}",
            }
    _save_positions(session_id, dojo_dir, positions)


def advance_session(session_id: str, bar_et: datetime, bars_df: pd.DataFrame,
                     dojo_dir: Path) -> list[dict]:
    """Advance every OPEN position one bar via walk_exit_manager (see module docstring for
    why this re-walks from entry each call). Returns the list of NEWLY-fired sim events
    this step (fills/TP1/stop/trail/flat); session.py appends these verbatim into the
    session ledger's `sim_events`. Persists updated positions.json. `bars_df` is used
    directly as the exit walk's `five_min_spy_df` (the SAME bars the engine itself is
    stepping through -- preserves the lockstep invariant), always re-sliced to <= bar_et
    here regardless of how much of the day the caller's frame already contains (no-
    look-ahead, C6)."""
    dojo_dir = Path(dojo_dir)
    bar_et_naive = _strip_tz(bar_et)
    positions = _load_positions(session_id, dojo_dir)
    if not positions:
        return []

    spy_df = bars_df.copy()
    if "timestamp_et" not in spy_df.columns:
        raise ValueError("advance_session: bars_df must carry a timestamp_et column")
    spy_df["timestamp_et"] = _to_naive_et_series(spy_df["timestamp_et"])
    spy_df = spy_df.sort_values("timestamp_et").reset_index(drop=True)
    spy_slice = spy_df.loc[spy_df["timestamp_et"] <= bar_et_naive]

    events: list[dict] = []
    for pid, pos in positions.items():
        if pos.get("status") != "OPEN":
            continue
        entry_dt = datetime.fromisoformat(pos["entry_time_et"])
        trade_date = entry_dt.date()
        opt_df, _src, _synth = _load_option_series(
            pos["symbol"], pos["side"], pos["strike"], trade_date, spy_df)
        opt_slice = opt_df.loc[opt_df["timestamp_et"] <= bar_et_naive] if opt_df is not None else None
        if opt_slice is None or opt_slice.empty:
            continue

        ribbon_tick_df = _ribbon_aligned_to(spy_slice, opt_slice)
        result = walk_exit_manager(
            symbol=pos["symbol"], side=pos["side"], entry_time_et=entry_dt,
            entry_premium=pos["entry_premium"], qty=pos["qty"], exit_shape=pos["exit_shape"],
            structure_stop_enabled=pos["structure_stop_enabled"], trigger_level=pos["trigger_level"],
            strategy=pos["strategy"], time_stop_et=_parse_hhmm(pos["time_stop_et"]),
            opt_df=opt_slice, ribbon_tick_df=ribbon_tick_df, five_min_spy_df=spy_slice,
        )

        last_seen = (datetime.fromisoformat(pos["last_advanced_bar_et"])
                     if pos.get("last_advanced_bar_et") else None)
        new_legs = [lg for lg in result.legs
                    if lg.reason != "data_exhausted_force_close"
                    and (last_seen is None or lg.ts_et > last_seen)]

        for lg in new_legs:
            pos["open_qty"] = int(pos["open_qty"]) - lg.qty
            pos["realized_pnl"] = round(float(pos["realized_pnl"]) + lg.leg_pnl, 2)
            leg_row = {"kind": lg.kind, "qty": lg.qty, "fill_price": lg.fill_price,
                       "reason": lg.reason, "stage": lg.stage, "ts_et": lg.ts_et.isoformat(),
                       "leg_pnl": lg.leg_pnl}
            pos["legs"].append(leg_row)
            events.append({
                "position_id": pid, "directive_id": pos["directive_id"], "arm": pos["arm"],
                "accounts_arm_id": pos.get("accounts_arm_id"), "symbol": pos["symbol"],
                "side": pos["side"], **leg_row,
                "position_status": pos["status"], "open_qty": pos["open_qty"],
                "realized_pnl": pos["realized_pnl"],
            })

        genuinely_resolved = (
            result.resolved and result.exit_reason != "data_exhausted_force_close"
            and result.exit_time_et is not None and result.exit_time_et <= bar_et_naive
        )
        if genuinely_resolved:
            pos["status"] = "CLOSED"
            pos["exit_reason"] = result.exit_reason
            pos["exit_time_et"] = result.exit_time_et.isoformat()
            pos["unrealized_pnl"] = 0.0
            events.append({
                "position_id": pid, "directive_id": pos["directive_id"], "arm": pos["arm"],
                "accounts_arm_id": pos.get("accounts_arm_id"), "symbol": pos["symbol"],
                "side": pos["side"], "kind": "POSITION_CLOSED", "stage": "closed",
                "reason": result.exit_reason, "qty": 0, "fill_price": None,
                "ts_et": result.exit_time_et.isoformat(), "leg_pnl": 0.0,
                "position_status": "CLOSED", "open_qty": pos["open_qty"],
                "realized_pnl": pos["realized_pnl"],
            })
        elif int(pos["open_qty"]) > 0:
            last_close = float(opt_slice.iloc[-1]["close"])
            pos["unrealized_pnl"] = round((last_close - float(pos["entry_premium"]))
                                           * int(pos["open_qty"]) * 100.0, 2)
        pos["last_advanced_bar_et"] = bar_et_naive.isoformat()

    _save_positions(session_id, dojo_dir, positions)
    return events


def _ribbon_aligned_to(spy_slice: pd.DataFrame, opt_slice: pd.DataFrame) -> Optional[pd.DataFrame]:
    """A 'stack' column per opt_slice row, backward-as-of from spy_slice's ribbon state (if
    engine_step's bars_df carries one) -- mirrors replay_today_eval.build_ribbon_1min's own
    convention. Absent 'stack' -> None (walk_exit_manager degrades to ribbon_flip_back never
    firing; TP1/stop/structure-stop/time-stop are all unaffected, disclosed here rather than
    silently assumed)."""
    if "stack" not in spy_slice.columns or opt_slice.empty:
        return None
    left = opt_slice[["timestamp_et"]].sort_values("timestamp_et")
    right = spy_slice[["timestamp_et", "stack"]].sort_values("timestamp_et")
    merged = pd.merge_asof(left, right, on="timestamp_et", direction="backward")
    return merged.reset_index(drop=True)

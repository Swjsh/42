"""crypto_twin_core.py -- the CRYPTO TWIN: 24/7 mechanism-validation training ground.

J requirement 2026-07-10 (see markdown/planning/CRYPTO-TWIN-TRAINING-GROUND.md, the spec
this file follows exactly). Runs the SAME shape of pipeline the SPY engine runs -- SEE
(bars) -> DECIDE (ribbon+level trigger) -> gate (risk_gate) -> ACT (place) -> manage
(exit_manager) -> journal -- against BTC/USD on Alpaca crypto PAPER, 24/7, in a fully
separate state namespace (automation/state/crypto-twin/). This validates the MECHANISM
(does the pipeline plumbing work, end to end, on live-moving data, at any hour) and
NEVER the edge (whether any setup is profitable) -- the twin's P&L is a health metric
only and must never enter any edge scorecard (see the spec doc's "Kill criteria").

REUSE, never fork (HARD RAILS):
  * exit_manager.ExitState / plan_exit_actions -- imported verbatim from
    automation/state/fleet/exit_manager.py. % exits map 1:1 onto a spot price (structure
    stop = close through the twin's own level, catastrophe cap = % adverse move, TP1 =
    partial sell + ratchet-to-BE, trailing runner = chandelier off HWM) -- exactly the
    SS-B shape, just percentages recalibrated for spot-BTC volatility instead of options
    premium (see TwinConfig.exit_shape's docstring for the specific numbers + why).
  * risk_gate.check_order -- imported from backtest/lib/risk_gate.py. Crypto qty is
    fractional (BTC), but check_order's qty/premium math assumes whole option contracts
    (qty must be a positive integer; notional = premium*qty*100). Rather than fork the
    function to accept fractional qty, this module presents it with a WHOLE-NUMBER PROXY
    UNIT (qty=cfg.min_contracts, premium=notional_usd/min_contracts/100) so check_order's
    REAL branches (kill-switch / PDT / NOT_FLAT / MIN_CONTRACTS / RISK_CAP) genuinely
    execute against the twin's real numbers -- "min-qty analog preserved so risk_gate
    paths execute" per the spec doc's mapping table. This proxy is INDEPENDENT of the
    actual broker order (see B1a note below): the real order uses entry_qty_btc(cfg) --
    a fixed BTC qty, not a notional/premium-derived amount -- so the risk_gate proxy
    unit never reaches the broker either way.
  * crypto.lib.{bar,bar_reader,ribbon,levels,kill_switch} -- the ribbon/level/structure
    detectors ("bars are bars"). See crypto_twin_signal.py / crypto_twin_levels.py for
    which pieces plug in where.
  * heartbeat_core.py is NOT imported and NOT edited this session (another crew owns its
    stale-trigger ordering fix tonight) -- its SEE/DECIDE stages are SPY-RTH-options-
    entangled (pandas RTH filtering, engine_cli's 15 SPY-specific gates, PDT, option
    premium economics) and do not cleanly generalize to a 24/7 spot instrument; forcing a
    fake bar_ctx through engine_cli would either no-op every gate or require faking
    option fields that don't exist for a spot position. What deserves LATER extraction
    (T3/T4, not this session): heartbeat_core's `_log`/ledger-write pattern and its
    veto-snapshot rendering are generic enough to share -- flagged here, not touched.

Config: entry-window gates are OFF (24/7, no RTH concept). max_hold_hours=6 is the
flatten backstop (mirrors EOD-flatten's role, fires several times/day on a 5-min cadence
instead of once/day). Kill-switch is UTC-day anchored via crypto.lib.kill_switch (already
a pure, tested, latching daily-loss primitive -- reused, not reimplemented).

B1a UNIT-LOT MODE (2026-07-11, markdown/planning/TWIN-PROGRAM.md): entries now buy a FIXED
INTEGER count of BTC "units" (TwinConfig.units_per_entry, default 3 -- see its docstring)
instead of a notional dollar amount, so ExitState.from_entry sees a REAL integer qty and
runs the EXACT production int-floor tp1/runner split (2 TP + 1 runner, CLAUDE.md Rule 6),
not an approximation. The old EXIT_UNITS=1000 wide-granularity proxy is retired -- it never
actually exercised the int-floor arithmetic (1000*0.667 floors with negligible rounding
loss vs the real 3-contract edge production runs on).

B3 PASSIVE-LIMIT ENTRY A/B (2026-07-14, queue TWIN-B3-ENTRY-MANAGER-LIVE / EDGE-1):
run_tick's entry placement now routes through place_entry_ab, which deterministically
alternates LIVE entries between the legacy marketable path (place_entry, byte-identical)
and entry_manager's (T-W5) passive-limit machinery run live -- real resting limits,
real cancels, real fill-quality measurement to entry-quality.json. Mechanism-only
measurement per twin doctrine; full design + graduation bar for SPY in
crypto_twin_entry_quality.py's module docstring. WATCH mode and every direct
place_entry caller (twin_gauntlet, tests) are unaffected.

B1b SCENARIO SCHEDULER additions (same date): run_tick gained two additive, backward-
compatible kwargs -- `trigger_level_offset_pct` (a RELATIVE override so a forced structure-
stop scenario can plant its trigger_level just above the tick's own just-fetched price
without a second bars/price fetch) and `scenario_tag` (threaded into place_entry's journal
rows + the persisted position record + this tick's decision row, so a scenario position's
WHOLE lifecycle stays taggable). Both default None -- every pre-B1b caller is byte-identical.
The scheduler itself lives in the sibling module crypto_twin_scenarios.py, which is the
ONLY intended caller of these two kwargs; crypto_twin_health.py's wrapper now calls THAT
module instead of this one directly (see crypto_twin_scenarios.run_scenario_tick).

BUGFIXES caught while wiring B1b (both were LATENT -- no position had ever lived long
enough to trip them, since n_orders_lifetime was 0 before this session):
  * manage_positions passed `now_et=now_utc.time()` to exit_manager.plan_exit_actions --
    the RAW UTC clock's time-of-day, compared against the ET-labeled TIME_STOP_ET (15:50)
    constant. Any position open when UTC's wall-clock (not ET) crossed 15:50 would have
    been spuriously force-closed once per UTC day, unrelated to any real ET boundary. Fixed
    to `et_clock.et_now(now_utc=now_utc).time()` (the already-imported, DST-aware converter
    this file just wasn't using for this one call site).
  * run_tick never threaded its own just-computed `price` (== the latest CLOSED 5m bar's
    close) into manage_positions' `last_closed_close` -- meaning stop_mode="structure"
    positions could NEVER exit via the dedicated chart-level branch in production; they
    silently fell through to the catastrophe-cap-in-structure-mode branch, time-stop, or
    max-hold instead. Fixed by passing `last_closed_close=price` (mirrors
    automation/state/fleet/exit_actuator.manage_tick's own real wiring of the same
    parameter -- the twin had simply never adopted it).

B6 EXIT-FILL CAPTURE (2026-07-23, queue TWIN-B6-SIM-FRICTION-CALIBRATION): a real gap found
while scoping B6 -- entries already poll_fill() + journal a FILLED row with the true
filled_avg_price (place_entry, TWIN-B3's entry-quality machinery), but SELL_PARTIAL/SELL_ALL
never did the same: the CLOSED/MANAGED journal row's "broker" field was always the raw PLACE
response (status="pending_new", filled_avg_price=null) -- the true exit fill price was placed
but never captured anywhere, so exit-side friction (structure_stop/runner_stop/cat_cap slippage
vs the trigger price named in `a.reason`) was silently un-measurable. Fixed: manage_positions
now polls the SAME broker.poll_fill() helper after a live SELL_PARTIAL/SELL_ALL and journals an
additive "EXIT_FILLED" row (expected_price parsed from `a.reason`'s "kind @ price" convention,
fill_price, time_to_fill_sec, slippage_bps) alongside the existing CLOSED/MANAGED row -- purely
additive telemetry, zero change to close_failed/dec.closes_position control flow (poll failures
fail open, same fail-open contract as the entry-side poll). Calibration reader:
setup/scripts/crypto_twin_friction_calibration.py.
"""
from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))  # so `crypto.lib.*` (namespace package, no crypto/__init__.py) resolves
for _p in ("automation/state/fleet", "backtest/lib", "setup/scripts"):
    sys.path.insert(0, str(REPO / _p))

from et_clock import et_now  # noqa: E402
import exit_manager as em  # noqa: E402
import risk_gate as rg  # noqa: E402

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.bar_reader import closed_bars_only, last_closed_bar  # noqa: E402
from crypto.lib.kill_switch import KillSwitchState, initial_state as ks_initial, tick as ks_tick  # noqa: E402

import crypto_twin_broker as broker  # noqa: E402
import crypto_twin_entry_quality as eq  # noqa: E402  -- TWIN-B3: passive-limit A/B (see place_entry_ab)
import crypto_twin_levels as tl  # noqa: E402
import crypto_twin_signal as sig  # noqa: E402

TWIN_DIR = REPO / "automation" / "state" / "crypto-twin"
DECISIONS_PATH = TWIN_DIR / "decisions.jsonl"
JOURNAL_PATH = TWIN_DIR / "journal.jsonl"
EXIT_STATE_PATH = TWIN_DIR / "exit-state.json"
BREAKER_PATH = TWIN_DIR / "breaker.json"

CRYPTO_SYMBOL = "BTC/USD"


# --- config ---------------------------------------------------------------------------
@dataclass(frozen=True)
class TwinConfig:
    """The twin's full runtime config. Every field has a doctrine-traceable default so a
    bare `TwinConfig()` is a safe, complete, production-shaped twin -- no caller needs to
    know the internals to run one correctly.
    """
    symbol: str = CRYPTO_SYMBOL
    granularity_seconds: int = 300               # 5m, matches SPY's primary cadence
    bar_limit: int = 400                          # enough for ribbon_slow=48 warmup + 2 UTC days
    notional_usd: float = 200.0                   # HARD RAILS: "~$200/entry" -- B1a NOTE
                                                    # (2026-07-11): this is now ONLY the risk_gate
                                                    # PROXY notional (see _risk_gate_check's
                                                    # whole-number-proxy docstring) -- the REAL
                                                    # broker order size is units_per_entry *
                                                    # unit_qty_btc (entry_qty_btc()) below. The two
                                                    # are intentionally independent: risk_gate's
                                                    # mechanism-fidelity doesn't need to track the
                                                    # unit-lot's exact dollar size.
    max_hold_hours: float = 6.0                   # flatten backstop (EOD-flatten analog)
    account_label: str = "twin"
    state_dir: Path = TWIN_DIR                    # injectable for tests; PRODUCTION DEFAULT below

    # risk_gate proxy (see module docstring: "min-qty analog preserved so risk_gate paths execute")
    min_contracts: int = 1
    per_trade_risk_cap_pct: float = 0.30           # mirrors Rule 6 Safe cap
    daily_loss_kill_switch_pct: float = 0.30       # mirrors Rule 5 Safe cap, UTC-day anchored
    starting_equity: float = 2000.0                # synthetic/local seed; broker equity preferred once configured (C11)

    # UNIT-LOT MODE (B1a, 2026-07-11, markdown/planning/TWIN-PROGRAM.md): every entry buys a
    # FIXED INTEGER count of BTC "units" -- never a notional/price-dependent amount -- so
    # exit_manager.from_entry sees a real integer qty=units_per_entry and runs the EXACT
    # production int-floor split: int(3 * tp1_qty_fraction=0.667) = 2 tp1 units, 1 runner unit
    # (CLAUDE.md Rule 6's "min 3 contracts: 2 TP + 1 runner"), verified empirically this
    # session (3*0.667 = 2.0010000000000003 in IEEE754 -- comfortably above the 2.0 floor
    # boundary, no rounding-to-1 risk). unit_qty_btc is the BTC size of ONE unit -- picked
    # 2026-07-11 from the live BTC/USD close read this session ($64,178.06, via
    # `python -m crypto_twin_broker`) so that units_per_entry units cost roughly $150-250:
    # 3 * 0.0008 BTC = 0.0024 BTC ~= $154.03 at that price. STATED, not silently derived.
    # The broker layer (crypto_twin_broker.place_crypto_order / market_sell_crypto) is the
    # ONLY place units get translated to a real BTC qty (see entry_qty_btc() and
    # manage_positions' SELL_PARTIAL conversion) -- everything above that boundary
    # (exit_manager, the B1b scenario scoreboard) works in whole units, exactly mirroring how
    # production works in whole option contracts.
    units_per_entry: int = 3
    unit_qty_btc: float = 0.0008

    # exit_shape (passed to exit_manager.ExitState.from_entry) -- percentages recalibrated
    # from options-premium scale to spot-BTC scale so EVERY exit stage (structure stop,
    # catastrophe cap, TP1, trail, runner-target) has a REALISTIC chance to fire within a
    # max_hold_hours window during a live soak -- production's option-premium percentages
    # (tp1=+30-40%, trail=12.5%, runner_target=250%) would make TP1/trail/runner
    # essentially unreachable on spot BTC's actual volatility and the twin would just ride
    # to max-hold every single time, defeating "exit engine behavior on REAL paper fills"
    # mechanism validation. These are MECHANISM-CALIBRATION numbers, not an edge claim --
    # never cited as a BTC trading parameter, only as "wide enough to prove the code path
    # fires." stop_mode="structure": the twin's own nearest level is the primary
    # invalidation (chart-stop-primary doctrine), catastrophe_stop_pct left at
    # exit_manager's own -0.50 default (omitted here so it's read from the module, not
    # re-typed) covers the structure-mode fallback + the true tail-risk cap.
    exit_shape: dict = field(default_factory=lambda: {
        "stop_mode": "structure",
        "premium_stop_pct": -0.03,       # -3%: the PREMIUM-mode fallback when no level is in range
        "tp1_premium_pct": 0.015,        # +1.5%
        "tp1_qty_fraction": 0.667,       # reuses the live vwap_continuation fraction (an already-
                                          # validated, real production value, not invented)
        "profit_lock_mode": "trailing",
        "trail_pct": 0.01,               # 1%
        "profit_lock_arm_pct": 0.005,    # +0.5%
        "runner_target_pct": 0.03,       # +3%
    })

    # TWIN-B3 (2026-07-14, queue TWIN-B3-ENTRY-MANAGER-LIVE / EDGE-1): passive-limit entry
    # A/B measurement knobs -- see crypto_twin_entry_quality.py's module docstring for the
    # full mechanism + parameter provenance. patience=3 and policy="cancel" are entry-2's
    # frozen pre-registration values (entry_manager.py, T-W5) reused verbatim;
    # poll_seconds is the live poll cadence WITHIN one twin tick (3 polls x 20s ~= 60s
    # resting window -- mechanism-calibration, injectable to 0 in tests);
    # limit_fraction=0.5 rests the limit at mid-spread (non-marketable by construction).
    passive_patience_polls: int = 3
    passive_poll_seconds: float = 20.0
    passive_limit_fraction: float = 0.5


def _assert_twin_namespace(cfg: TwinConfig) -> None:
    """Runtime backstop for the namespace-isolation guarantee (the static AST test in
    backtest/tests/test_crypto_twin_core.py checks the SOURCE; this checks a live cfg).
    Refuses to proceed if a caller ever constructs a TwinConfig pointed outside this
    namespace -- the --force-entry test flag's only real safety rail (besides being
    unreachable from anything but this module's own CLI)."""
    norm = str(cfg.state_dir).replace("\\", "/")
    if not norm.endswith("automation/state/crypto-twin"):
        raise ValueError(f"crypto_twin_core: refusing non-twin state_dir {cfg.state_dir!r}")


def entry_qty_btc(cfg: TwinConfig) -> float:
    """The EXACT BTC amount ONE entry buys: units_per_entry fixed integer UNITS *
    unit_qty_btc (a small fixed BTC quantum) -- see TwinConfig's docstring (B1a,
    2026-07-11) for how the quantum was picked. Buying this PRECISE qty (never a
    notional/price-dependent amount) guarantees the held position is exactly
    units_per_entry units, so ExitState.from_entry's int-floor split runs against the
    REAL held size, not an approximation."""
    return round(cfg.units_per_entry * cfg.unit_qty_btc, 8)


def get_open_position(cfg: TwinConfig) -> Optional[dict]:
    """PUBLIC accessor: the persisted position record for cfg.symbol (None if flat).
    Lets a sibling module (crypto_twin_scenarios.py) inspect position/scenario state
    without reaching into the private _load_positions()."""
    return _load_positions(cfg).get(cfg.symbol)


def read_breaker_tripped(cfg: TwinConfig) -> Optional[bool]:
    """Best-effort READ of the last-persisted breaker.json's `tripped` flag, without
    recomputing/ticking the breaker (that needs live equity/creds -- see load_breaker).
    None when no breaker.json exists yet (fresh account, never ticked). Used by
    crypto_twin_scenarios.py's scheduling gate ("skip when the breaker is tripped") --
    at most one 5-min tick stale, the same tolerance crypto_twin_health.py's own glance
    reads already accept for the identical fact."""
    p = _breaker_path(cfg)
    if not p.exists():
        return None
    try:
        return bool(json.loads(p.read_text(encoding="utf-8")).get("tripped", False))
    except (OSError, json.JSONDecodeError):
        return None


# --- bar plumbing -----------------------------------------------------------------------
def _to_bar(raw: dict, granularity_seconds: int) -> Bar:
    ts = datetime.fromisoformat(str(raw["t"]).replace("Z", "+00:00"))
    return Bar(open_time=ts, open=float(raw["o"]), high=float(raw["h"]), low=float(raw["l"]),
              close=float(raw["c"]), volume=float(raw.get("v", 0.0)),
              granularity_seconds=granularity_seconds, source="alpaca")


def fetch_closed_bars(cfg: TwinConfig, *, now_utc: Optional[datetime] = None,
                      raw_bars: Optional[list[dict]] = None) -> tuple[list[Bar], dict]:
    """SEE stage: fetch + convert + closed-bar-filter (C6). `raw_bars` is injectable for
    tests/replay (skips the network call); production callers omit it.

    Returns (closed_bars, meta) where meta carries the bar_reader.ClosedBarResult verdict
    for the decision row (never silently swallows a stale/no-data tick)."""
    now = now_utc or datetime.now(timezone.utc)
    if raw_bars is None:
        raw_bars = broker.fetch_crypto_bars(cfg.symbol, granularity_seconds=cfg.granularity_seconds,
                                            limit=cfg.bar_limit)
    all_bars = tuple(_to_bar(r, cfg.granularity_seconds) for r in raw_bars)
    from crypto.lib.bar import BarSeries
    series = BarSeries(symbol=cfg.symbol, granularity_seconds=cfg.granularity_seconds,
                       source="alpaca", bars=all_bars)
    result = last_closed_bar(series, now)
    closed = closed_bars_only(series, now)
    meta = {"verdict": result.verdict, "bars_rejected_as_in_progress": result.bars_rejected_as_in_progress,
           "last_closed_ts": result.last_closed.open_time.isoformat() if result.last_closed else None}
    return list(closed.bars), meta


# --- breaker (UTC-day kill-switch) -------------------------------------------------------
def _breaker_path(cfg: TwinConfig) -> Path:
    return cfg.state_dir / "breaker.json"


def load_breaker(cfg: TwinConfig, *, now_utc: datetime, current_equity: float) -> KillSwitchState:
    """Load-or-roll today's UTC-day breaker. Equity CARRIES FORWARD day to day (like a
    real account compounds); a new UTC day starts a fresh (untripped) latch seeded at the
    prior day's ending equity, or cfg.starting_equity on first-ever run."""
    p = _breaker_path(cfg)
    today = now_utc.strftime("%Y-%m-%d")
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        if raw.get("utc_date") == today:
            return KillSwitchState(account_id=cfg.account_label,
                                   start_of_day_equity=float(raw["start_of_day_equity"]),
                                   threshold_pct=cfg.daily_loss_kill_switch_pct,
                                   tripped=bool(raw.get("tripped", False)),
                                   tripped_at_equity=raw.get("tripped_at_equity"),
                                   min_equity_seen=float(raw.get("min_equity_seen", current_equity)))
        sod = float(raw.get("current_equity", raw.get("start_of_day_equity", cfg.starting_equity)))
    else:
        sod = cfg.starting_equity
    return ks_initial(cfg.account_label, sod, cfg.daily_loss_kill_switch_pct)


def save_breaker(cfg: TwinConfig, state: KillSwitchState, *, now_utc: datetime, current_equity: float) -> None:
    p = _breaker_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "utc_date": now_utc.strftime("%Y-%m-%d"), "account_id": state.account_id,
        "start_of_day_equity": state.start_of_day_equity, "current_equity": current_equity,
        "threshold_pct": state.threshold_pct, "tripped": state.tripped,
        "tripped_at_equity": state.tripped_at_equity, "min_equity_seen": state.min_equity_seen,
    }, indent=2), encoding="utf-8")


# --- exit-state persistence (mirrors fleet's exit_actuator.py load/save shape) -----------
def _load_positions(cfg: TwinConfig) -> dict[str, dict]:
    p = cfg.state_dir / "exit-state.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8")) or {}
    except (OSError, json.JSONDecodeError):
        return {}


def _save_positions(cfg: TwinConfig, positions: dict[str, dict]) -> None:
    p = cfg.state_dir / "exit-state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(positions, indent=2), encoding="utf-8")


# --- journal --------------------------------------------------------------------------
def _journal(cfg: TwinConfig, event: str, **fields) -> None:
    p = cfg.state_dir / "journal.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts_utc": datetime.now(timezone.utc).isoformat(), "event": event, "twin": True, **fields}
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


# --- decisions.jsonl (T1) ---------------------------------------------------------------
def _decision_row(cfg: TwinConfig, *, now_utc: datetime, armed: bool, price: Optional[float],
                  verdict: sig.TwinVerdict, levels: Optional[tl.TwinLevelSet],
                  risk_decision: Optional[rg.RiskDecision], breaker_state: Optional[KillSwitchState],
                  position_status: str, exit_pass: list, action: str,
                  scenario: Optional[str] = None,
                  entry_mode: Optional[str] = None) -> dict:
    """SAME KEY SET as automation/state/core-decisions.jsonl (ts_et, account, armed, spy,
    ribbon, spread_cents, vix, htf_15m, verdict, side, setup, triggers, reason,
    trigger_level_exact, exit_pass, action) + "twin": true per the task spec, PLUS
    additive twin-only fields (ts_utc, symbol, price, levels, risk_gate, breaker,
    session_date_utc, position_status) carrying the honest crypto-native values.

    Deliberate DEVIATIONS from a byte-literal copy (documented, not accidental):
      * "spy" holds the BTC/USD price (legacy key name kept for schema/structural
        compat with any future generic decisions.jsonl reader); "price" is the same
        value under an honest name -- both present, never conflated with real SPY data
        (the "symbol"/"twin" fields make the row unambiguous to any consumer).
      * "spread_cents" holds the ribbon spread in DOLLARS (BTC has no cents-scale
        meaning) -- key name kept for schema compat, unit documented here.
      * "vix" is always null (no crypto analog) and "htf_15m" is always null (no
        higher-timeframe confirmation stage in this v1 -- flagged as a natural T3/T4
        addition, not silently faked).
      * "side" is "bull"/"bear"/null (not "C"/"P" -- those literally mean call/put
        options, which don't exist for a spot position; a generic `side is not None`
        check behaves identically either way).
      * bear_score/bull_score are OMITTED (not scored 0-10/0-11 the way engine_cli's
        rules-engine setups are) -- mirrors the codebase's OWN existing precedent for
        extra-setup/watcher-pattern verdicts, which already omit these two keys rather
        than print a fabricated score (see heartbeat_core._veto_snapshot's 2026-07-09 fix).

    B1b ADDITIVE field: "scenario" (2026-07-11) -- the scenario branch name (e.g.
    "ENTRY_TP1_TRAIL") tagging this row, or None for an organic tick. `scenario` param
    default None so every pre-B1b caller (i.e. every call site except
    crypto_twin_scenarios.run_scenario_tick) is unaffected.

    B3 ADDITIVE field: "entry_mode" (2026-07-14) -- "passive"/"marketable" when this tick
    attempted an entry (the A/B cohort, see place_entry_ab), else None. Default None so
    every pre-B3 caller is unaffected.
    """
    lvl_dict = None
    if levels is not None:
        lvl_dict = {
            "prior_day_high": levels.prior_day_high.price if levels.prior_day_high else None,
            "prior_day_low": levels.prior_day_low.price if levels.prior_day_low else None,
            "prior_day_close": levels.prior_day_close.price if levels.prior_day_close else None,
            "intraday_high": levels.intraday_high.price if levels.intraday_high else None,
            "intraday_low": levels.intraday_low.price if levels.intraday_low else None,
        }
    return {
        "ts_et": et_now().isoformat(),
        "ts_utc": now_utc.isoformat(),
        "account": cfg.account_label,
        "twin": True,
        "symbol": cfg.symbol,
        "armed": armed,
        "spy": price,
        "price": price,
        "ribbon": verdict.ribbon_stack,
        "spread_cents": verdict.ribbon_spread,
        "vix": None,
        "htf_15m": None,
        "verdict": verdict.verdict,
        "side": verdict.side,
        "setup": verdict.setup,
        "triggers": verdict.triggers,
        "reason": verdict.reason,
        "trigger_level_exact": verdict.trigger_level_exact,
        "exit_pass": exit_pass,
        "action": action,
        "session_date_utc": levels.session_date_utc if levels is not None else None,
        "levels": lvl_dict,
        "risk_gate": ({"code": risk_decision.code, "reason": risk_decision.reason}
                     if risk_decision is not None else None),
        "breaker": ({"tripped": breaker_state.tripped,
                    "start_of_day_equity": breaker_state.start_of_day_equity,
                    "min_equity_seen": breaker_state.min_equity_seen}
                   if breaker_state is not None else None),
        "position_status": position_status,
        "scenario": scenario,
        "entry_mode": entry_mode,
    }


def log_decision(cfg: TwinConfig, row: dict) -> None:
    p = cfg.state_dir / "decisions.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


# --- risk_gate wiring ---------------------------------------------------------------------
def _risk_gate_check(cfg: TwinConfig, *, equity: float, sod_equity: float,
                     kill_switch_tripped: bool, position_status: str, setup_name: str) -> rg.RiskDecision:
    """Presents risk_gate.check_order with the whole-number proxy unit described in the
    module docstring: qty=min_contracts, premium=notional_usd/min_contracts/100 so that
    premium*qty*100 == notional_usd exactly -- check_order's REAL branch logic executes
    (kill-switch / NOT_FLAT / MIN_CONTRACTS / RISK_CAP), it just never sees a fractional
    BTC qty (which it would reject outright as UNREADABLE_INPUT -- options-contract-count
    convention, not a crypto convention)."""
    premium_proxy = cfg.notional_usd / cfg.min_contracts / 100.0
    return rg.check_order(
        account=cfg.account_label, equity=equity, start_of_day_equity=sod_equity,
        proposed_qty=cfg.min_contracts, premium=premium_proxy, setup_name=setup_name,
        current_position_status=position_status, day_trades_used_5d=0,  # PDT: N/A, crypto is not a security
        kill_switch_tripped=kill_switch_tripped, prior_stops_today=[],
        params={"per_trade_risk_cap_pct": cfg.per_trade_risk_cap_pct,
               "daily_loss_kill_switch_pct": cfg.daily_loss_kill_switch_pct,
               "min_contracts": cfg.min_contracts})


_REASON_PRICE_RE = re.compile(r"@\s*([0-9]+(?:\.[0-9]+)?)")


def _parse_reason_price(reason: Optional[str]) -> Optional[float]:
    """Extract the trigger price from exit_manager's "kind @ price" reason convention
    (e.g. "structure_stop @ 64314.98", "runner_stop @ 64191.71", "premium_stop @ 64186.49").
    Returns None for reasons with no embedded price (time_stop_15:50, max_hold_flatten,
    ribbon_flip_back, chaos_drill_restore) -- those have no single trigger level to diff
    a fill against, so slippage is genuinely undefined for them, not zero."""
    if not reason:
        return None
    m = _REASON_PRICE_RE.search(reason)
    return float(m.group(1)) if m else None


def _journal_exit_fill(cfg: TwinConfig, *, creds: dict, order_id: Optional[str],
                       kind: str, reason: Optional[str], scenario: Optional[str],
                       entry_price: Optional[float] = None,
                       btc_qty: Optional[float] = None) -> None:
    """B6 friction calibration (TWIN-B6-SIM-FRICTION-CALIBRATION): poll the REAL exit fill
    (same broker.poll_fill() helper place_entry already uses on the entry side) and journal
    an additive "EXIT_FILLED" row -- expected_price (parsed from `reason`), fill_price,
    latency, and slippage_bps (positive = fill better than the reason-stated trigger price
    for a sell, i.e. filled ABOVE the stop/target level; negative = worse/gapped-through).
    Fail-open by design: any exception here is swallowed -- this function runs AFTER the
    real sell order has already been placed and journaled (CLOSED/MANAGED), so a failure
    to capture calibration telemetry must never mask or retry the underlying exit.

    REALIZED P&L (2026-07-26, TWIN-PNL): when `entry_price` and `btc_qty` are supplied, this
    row also carries `realized_usd` / `realized_pct` for the leg just sold. Until now NO row
    in the entire journal carried a P&L field of any kind -- 96 closed round trips with no
    recoverable outcome (the CLOSED row's `broker` blob is the raw PLACE response, whose
    filled_avg_price is null). Long/spot only, so the sign convention is simply
    (exit - entry); if a short leg ever exists (perps), this must become side-aware.
    """
    if not order_id:
        return
    try:
        t0 = time.monotonic()
        fill = broker.poll_fill(creds, order_id, attempts=4, sleep_sec=1.5)
        latency = round(time.monotonic() - t0, 3)
        fill_price = fill.get("filled_avg_price")
        expected_price = _parse_reason_price(reason)
        slippage_bps = None
        if fill_price and expected_price:
            slippage_bps = round((float(fill_price) - expected_price) / expected_price * 10_000.0, 4)
        realized_usd = realized_pct = None
        if fill_price and entry_price:
            try:
                ep, xp = float(entry_price), float(fill_price)
                if ep > 0:
                    realized_pct = round((xp - ep) / ep * 100.0, 6)
                    if btc_qty:
                        realized_usd = round((xp - ep) * float(btc_qty), 6)
            except (TypeError, ValueError):
                pass  # never let P&L arithmetic break exit telemetry
        _journal(cfg, "EXIT_FILLED", symbol=cfg.symbol, order_id=order_id, kind=kind,
                reason=reason, scenario=scenario, expected_price=expected_price,
                fill_price=fill_price, time_to_fill_sec=latency, slippage_bps=slippage_bps,
                fill_status=fill.get("status"), entry_price=entry_price, btc_qty=btc_qty,
                realized_usd=realized_usd, realized_pct=realized_pct)
    except Exception as e:  # noqa: BLE001 -- fail-open telemetry, see docstring
        _journal(cfg, "EXIT_FILLED_CAPTURE_ERROR", symbol=cfg.symbol, order_id=order_id,
                error=f"{type(e).__name__}: {e}")


# --- exit management (T2) -- mirrors fleet's exit_actuator.manage_tick shape -------------
def _make_ribbon_flip_fn(ribbon_stack: Optional[str]):
    if not ribbon_stack:
        return None

    def fn(symbol: str, side: str) -> bool:
        return ribbon_stack == ("BULL" if side == "P" else "BEAR")
    return fn


def manage_positions(cfg: TwinConfig, *, creds: Optional[dict], now_utc: datetime, live: bool,
                     ribbon_stack: Optional[str] = None,
                     last_closed_close: Optional[float] = None) -> list[dict]:
    """ONE exit-management tick over every twin position. MAX-HOLD is checked FIRST (a
    duration guard exit_manager has no concept of -- its time_stop_et is a wall-clock
    time-of-day, not an elapsed-hours check, so this is deliberately a separate guard
    layered in front, mirroring how EOD-flatten is its own backstop task in production
    rather than part of exit_manager itself). Everything else is exit_manager's real walk.

    Returns [] with no broker calls when `creds` is None (T2 blocked -- see run_tick).

    UNIT-LOT MODE (B1a): `open_qty` passed to plan_exit_actions is cfg.units_per_entry
    (the FULL integer unit count, e.g. 3) -- same pattern the retired EXIT_UNITS proxy
    used: exit_manager's internal accounting always thinks in the ORIGINAL full-size
    unit count, while the REAL broker-reported open_qty (read fresh from get_crypto_
    position_qty every iteration) is what actually gets sold. A SELL_PARTIAL's units
    (a.qty, e.g. 2) convert to BTC via a straight multiply against the fixed quantum
    (units * unit_qty_btc) -- deterministic, not a fraction of whatever the broker
    happens to currently report -- while a SELL_ALL always sweeps the REAL current
    open_qty (never a computed unit count), so no fractional BTC dust is ever stranded
    even if the entry fill differed by a satoshi from the nominal entry_qty_btc().

    ET BUGFIX (2026-07-11): now_et is derived via et_clock.et_now(now_utc=now_utc),
    NOT a raw now_utc.time() -- see module docstring's "BUGFIXES" note. Passing the
    UTC clock's own time-of-day into a parameter exit_manager compares against the
    ET-labeled TIME_STOP_ET (15:50) constant would spuriously force-close any position
    still open when UTC (not ET) crossed 15:50, once per day, with no relation to any
    real ET boundary.
    """
    positions = _load_positions(cfg)
    if not positions:
        return []
    results: list[dict] = []
    changed = False
    flip_fn = _make_ribbon_flip_fn(ribbon_stack)
    now_et_time = et_now(now_utc=now_utc).time()
    for symbol, rec in list(positions.items()):
        st = em.ExitState.from_dict(rec["exit_state"])
        entered_at = datetime.fromisoformat(rec["entered_at_utc"])
        elapsed_h = (now_utc - entered_at).total_seconds() / 3600.0
        scenario = rec.get("scenario")
        if creds is None:
            results.append({"symbol": symbol, "action": "BLOCKED_NO_ACCOUNT",
                            "reason": "no dedicated twin account configured -- see secrets.json.example"})
            continue
        open_qty = broker.get_crypto_position_qty(creds, symbol)
        if open_qty <= 0:
            del positions[symbol]
            changed = True
            results.append({"symbol": symbol, "open_qty": 0, "action": "FLAT_PRUNED"})
            _journal(cfg, "CLOSED", symbol=symbol, reason="broker shows flat", scenario=scenario)
            continue
        if elapsed_h >= cfg.max_hold_hours:
            res = broker.close_all_crypto(creds, symbol=symbol, live=live)
            if live and (res.get("_error") or res.get("_refused")):
                # Same failed-close guard as the SELL_ALL path below: never delete the
                # record while the broker still holds the position -- retry next tick.
                results.append({"symbol": symbol, "open_qty": open_qty,
                                "action": "CLOSE_FAILED_RETRY",
                                "elapsed_hours": round(elapsed_h, 2), "broker": res})
                _journal(cfg, "CLOSE_FAILED", symbol=symbol, reason="max_hold_flatten",
                        elapsed_hours=round(elapsed_h, 2), broker=res, scenario=scenario)
                continue
            del positions[symbol]
            changed = True
            results.append({"symbol": symbol, "open_qty": open_qty, "action": "MAX_HOLD_FLATTEN",
                            "elapsed_hours": round(elapsed_h, 2), "broker": res})
            _journal(cfg, "CLOSED", symbol=symbol, reason="max_hold_flatten",
                    elapsed_hours=round(elapsed_h, 2), broker=res, scenario=scenario)
            continue
        hilo = broker.get_crypto_quote_hilo(cfg.symbol, creds=creds)
        if hilo is None:
            results.append({"symbol": symbol, "open_qty": open_qty, "action": "HOLD", "reason": "no_quote"})
            continue
        best, worst = hilo
        flip = bool(flip_fn(symbol, st.side)) if flip_fn else False
        dec = em.plan_exit_actions(st, best_premium=best, worst_premium=worst, open_qty=cfg.units_per_entry,
                                   now_et=now_et_time, ribbon_flip_back=flip,
                                   last_closed_5m_close=last_closed_close)
        rec["exit_state"] = dec.state.to_dict()
        changed = True
        executed = []
        close_failed = False
        for a in dec.actions:
            if a.kind in ("SELL_PARTIAL", "SELL_ALL"):
                if a.kind == "SELL_PARTIAL":
                    units_sold = a.qty
                    btc_qty = round(units_sold * cfg.unit_qty_btc, 8)  # deterministic unit->BTC
                else:
                    # SELL_ALL: exit_manager's own a.qty always echoes the open_qty
                    # PARAMETER this tick was called with (cfg.units_per_entry, the
                    # ORIGINAL full unit count) -- it has no notion of "TP1 already sold
                    # part of this position". The TRUE remaining unit count is derivable
                    # from `st` (the PRE-tick state, read before dec was computed, still
                    # in scope): runner_qty if TP1 had already filled by the START of this
                    # tick, else the full total_qty. LABEL-ONLY correction -- btc_qty
                    # (what actually gets sold) is still sourced from the REAL broker
                    # open_qty below (C11), unaffected either way.
                    units_sold = st.runner_qty if st.tp1_filled else st.total_qty
                    btc_qty = open_qty  # SELL_ALL always sweeps the REAL remaining broker qty
                res = broker.market_sell_crypto(creds, symbol=symbol, qty=btc_qty, live=live) if live \
                    else {"_skipped": "WATCH"}
                if a.kind == "SELL_ALL" and live and (res.get("_error") or res.get("_refused")):
                    # The CLOSE itself failed at the broker. Caught LIVE 2026-07-15 03:58
                    # UTC (TWIN-B3 first passive rep): the pre-fix code deleted the
                    # position record anyway, orphaning REAL broker holdings with no
                    # exit-managed record (C11 violation). Flag it; the record is KEPT
                    # below (pre-tick state restored) so the next tick retries the exit.
                    close_failed = True
                executed.append({"kind": a.kind, "units": units_sold, "btc_qty": btc_qty, "stage": a.stage,
                                 "reason": a.reason, "broker": res})
                # SELL_ALL genuinely ends this position's lifecycle -> "CLOSED" (not lumped
                # under "MANAGED"), so a reader scanning journal.jsonl for the full
                # placed->filled->managed->closed trail finds a real CLOSED row for every
                # exit path (structure stop / catastrophe cap / runner target / time stop),
                # not just the max-hold backstop. A broker-rejected SELL_ALL journals
                # CLOSE_FAILED instead -- loud, and never fakes a CLOSED that didn't happen.
                event = ("MANAGED" if a.kind == "SELL_PARTIAL"
                         else ("CLOSE_FAILED" if close_failed else "CLOSED"))
                _journal(cfg, event, symbol=symbol,
                        kind=a.kind, units=units_sold, btc_qty=btc_qty, stage=a.stage, reason=a.reason,
                        broker=res, scenario=scenario,
                        # TWIN-PNL 2026-07-26: stamp the entry price on the exit row so realized
                        # P&L stays reconstructible even when the EXIT_FILLED poll below fails
                        # (fail-open telemetry must not be the ONLY place outcome data lives).
                        entry_price=getattr(st, "entry_premium", None))
                # B6 friction calibration: capture the REAL exit fill (additive telemetry
                # only -- see _journal_exit_fill docstring; never runs on a close_failed/
                # unaccepted order, never affects close_failed/dec.closes_position above).
                if live and not close_failed and res.get("id"):
                    _journal_exit_fill(cfg, creds=creds, order_id=res.get("id"), kind=a.kind,
                                       reason=a.reason, scenario=scenario,
                                       entry_price=getattr(st, "entry_premium", None),
                                       btc_qty=btc_qty)
            elif a.kind == "RATCHET_STOP":
                executed.append({"kind": "RATCHET_STOP", "stage": a.stage,
                                 "new_stop_premium": a.new_stop_premium, "reason": a.reason})
        if dec.closes_position:
            if close_failed:
                # Restore the PRE-tick exit state so the whole exit decision re-runs
                # (and re-sells) cleanly on the next tick -- never delete the record
                # while the broker still holds the position. (SELL_PARTIAL failure
                # reconcile is the T-AUDIT-03/F7 class, tracked separately -- this
                # guards the path that just orphaned real holdings.)
                rec["exit_state"] = st.to_dict()
                results.append({"symbol": symbol, "open_qty": open_qty, "action": "CLOSE_FAILED_RETRY",
                                "actions": executed, "mode": "LIVE" if live else "WATCH"})
                continue
            del positions[symbol]
        results.append({"symbol": symbol, "open_qty": open_qty, "best": best, "worst": worst,
                        "tp1_filled": dec.state.tp1_filled, "runner_stop": dec.state.runner_stop_premium,
                        "actions": executed, "mode": "LIVE" if live else "WATCH"})
    if changed:
        _save_positions(cfg, positions)
    return results


# --- placement (T2) ----------------------------------------------------------------------
def place_entry(cfg: TwinConfig, *, creds: dict, side: str, price: float,
                trigger_level: Optional[float], live: bool,
                now_utc: Optional[datetime] = None,
                scenario_tag: Optional[str] = None) -> dict:
    """BUY-only (Alpaca crypto is cash/long-only -- no short leg exists to express a
    "bear" verdict as a position; see run_tick for how ENTER_BEAR is logged-but-skipped).

    UNIT-LOT MODE (B1a): places a market order sized by the EXACT qty entry_qty_btc(cfg)
    returns (units_per_entry * unit_qty_btc BTC) -- NOT notional -- so the held position
    is precisely units_per_entry units, never a price-dependent approximation. Then
    registers the position with the REAL exit_manager.ExitState.from_entry(qty=
    cfg.units_per_entry, ...) (structure mode when trigger_level is available, matching
    production's chart-stop-primary doctrine) -- so from_entry's int-floor split runs
    against the real held size.

    `now_utc` is injectable (defaults to real wall-clock) so tests can pin entered_at_utc
    and deterministically fast-forward past max_hold_hours -- mirrors run_tick/
    fetch_closed_bars's same injectable-clock pattern.

    `scenario_tag` (B1b, None for every organic entry) is threaded into the PLACED/FILLED
    journal rows and the persisted position record (position["scenario"]) so the whole
    lifecycle stays taggable -- see crypto_twin_scenarios.py."""
    now = now_utc or datetime.now(timezone.utc)
    qty_btc = entry_qty_btc(cfg)
    order = broker.place_crypto_order(creds, symbol=cfg.symbol, side="buy",
                                      qty=qty_btc, order_type="market", live=live)
    _journal(cfg, "PLACED", symbol=cfg.symbol, side=side, units=cfg.units_per_entry,
            unit_qty_btc=cfg.unit_qty_btc, qty_btc=qty_btc, price=price,
            trigger_level=trigger_level, scenario=scenario_tag, order=order, live=live)
    if not live or order.get("_error") or order.get("_refused") or order.get("_skipped"):
        return {"placed": False, "order": order}
    order_id = order.get("id")
    fill = broker.poll_fill(creds, order_id, attempts=4, sleep_sec=1.5) if order_id else \
        {"filled": False, "status": "unknown"}
    _journal(cfg, "FILLED", symbol=cfg.symbol, order_id=order_id, units=cfg.units_per_entry,
            scenario=scenario_tag, fill=fill)
    entry_price = fill.get("filled_avg_price") or price
    st = em.ExitState.from_entry(symbol=cfg.symbol, side="C", entry_premium=float(entry_price),
                                 qty=cfg.units_per_entry, exit_shape=cfg.exit_shape, strategy="crypto_twin",
                                 trigger_level=trigger_level, structure_stop_enabled=True)
    positions = _load_positions(cfg)
    positions[cfg.symbol] = {"exit_state": st.to_dict(), "entered_at_utc": now.isoformat(),
                             "side": side, "order_id": order_id, "scenario": scenario_tag}
    _save_positions(cfg, positions)
    return {"placed": True, "order": order, "fill": fill, "exit_state": st.to_dict()}


# --- TWIN-B3: A/B entry dispatcher (passive-limit graduation, EDGE-1) ---------------------
def _register_passive_position(cfg: TwinConfig, *, res: dict, side: str,
                               trigger_level: Optional[float], scenario_tag: Optional[str],
                               ab_index: Optional[int], now: datetime) -> dict:
    """Mirror of place_entry's post-fill tail for a PASSIVE fill: journal FILLED, build
    the REAL exit_manager.ExitState off the actual fill price, persist the position."""
    fill_price = float(res["fill_price"])
    _journal(cfg, "FILLED", symbol=cfg.symbol, order_id=res.get("order_id"),
            units=cfg.units_per_entry, scenario=scenario_tag, fill=res.get("fill"),
            entry_mode="passive", ab_index=ab_index)
    st = em.ExitState.from_entry(symbol=cfg.symbol, side="C", entry_premium=fill_price,
                                 qty=cfg.units_per_entry, exit_shape=cfg.exit_shape,
                                 strategy="crypto_twin", trigger_level=trigger_level,
                                 structure_stop_enabled=True)
    positions = _load_positions(cfg)
    positions[cfg.symbol] = {"exit_state": st.to_dict(), "entered_at_utc": now.isoformat(),
                             "side": side, "order_id": res.get("order_id"),
                             "scenario": scenario_tag, "entry_mode": "passive"}
    _save_positions(cfg, positions)
    return {"placed": True, "order": res.get("order"), "fill": res.get("fill"),
            "exit_state": st.to_dict(), "entry_mode": "passive", "ab_index": ab_index}


def _journal_entry_quality(cfg: TwinConfig, attempt: Optional[dict]) -> None:
    """ONE tier-tagged, mechanism-only journal line per completed A/B attempt (twin
    doctrine: never an edge claim -- these are transaction-mechanics numbers)."""
    if not attempt:
        return
    _journal(cfg, "ENTRY_QUALITY", tier="LIVE", mechanism="entry_quality",
            **{k: attempt.get(k) for k in (
                "cohort", "ab_index", "outcome", "scenario", "order_id",
                "limit_price", "baseline_ask", "baseline_bid", "fill_price",
                "time_to_fill_sec", "improvement_usd_per_btc", "improvement_bps",
                "polls_used", "sim_fill_divergence", "race_fill", "fallback_reason")})


def place_entry_ab(cfg: TwinConfig, *, creds: dict, side: str, price: float,
                   trigger_level: Optional[float], live: bool,
                   now_utc: Optional[datetime] = None,
                   scenario_tag: Optional[str] = None,
                   entry_mode_override: Optional[str] = None) -> dict:
    """TWIN-B3 (EDGE-1 graduation): the A/B entry dispatcher. Alternates every LIVE entry
    attempt between the legacy MARKETABLE path (place_entry, byte-identical) and the
    PASSIVE-limit path (crypto_twin_entry_quality.place_passive_entry -- entry_manager's
    T-W5 machinery run live), deterministically off entry-quality.json's persisted
    ab_counter (even -> marketable, odd -> passive; tagged per order). Every completed
    attempt is folded into entry-quality.json + one ENTRY_QUALITY journal row.

    WATCH mode (live=False) routes straight to place_entry WITHOUT burning an A/B index
    (no real order happens, so counting it would distort alternation).

    `entry_mode_override` ("passive"|"marketable") is VERIFICATION-ONLY (mirrors
    run_tick's own force_entry flag): forces the cohort without consuming an ab_index --
    reachable only via run_tick's `--force-entry-mode` CLI flag.

    FAIL-OPEN: any unexpected passive-path exception (or an expected fallback: no quote,
    order rejected) falls through to the marketable path so the twin still enters; the
    fallback is recorded under the passive cohort's `fallbacks` counter."""
    now = now_utc or datetime.now(timezone.utc)
    if not live:
        result = place_entry(cfg, creds=creds, side=side, price=price, trigger_level=trigger_level,
                             live=live, now_utc=now, scenario_tag=scenario_tag)
        return {**result, "entry_mode": "marketable", "ab_index": None}

    if entry_mode_override in ("passive", "marketable"):
        cohort, ab_index = entry_mode_override, None
    else:
        cohort, ab_index = eq.allocate_cohort(cfg.state_dir)

    fallback_reason: Optional[str] = None
    if cohort == "passive":
        try:
            res = eq.place_passive_entry(
                creds=creds, symbol=cfg.symbol, qty_btc=entry_qty_btc(cfg),
                units=cfg.units_per_entry, unit_qty_btc=cfg.unit_qty_btc, side=side,
                price=price, trigger_level=trigger_level, scenario_tag=scenario_tag,
                ab_index=ab_index, live=live, patience_polls=cfg.passive_patience_polls,
                poll_seconds=cfg.passive_poll_seconds, limit_fraction=cfg.passive_limit_fraction,
                journal=lambda event, **f: _journal(cfg, event, **f))
        except Exception as e:  # noqa: BLE001 -- fail-open: the twin must still enter
            res = {"outcome": "fallback", "fallback_reason": f"passive_error:{type(e).__name__}: {e}"}
        base_attempt = {"cohort": "passive", "ab_index": ab_index, "scenario": scenario_tag,
                        "signal_price": price, "order_id": res.get("order_id"),
                        "limit_price": res.get("limit_price"),
                        "baseline_ask": res.get("baseline_ask"),
                        "baseline_bid": res.get("baseline_bid"),
                        "polls_used": res.get("polls_used"),
                        "sim_fill_divergence": res.get("sim_fill_divergence")}
        if res["outcome"] == "filled":
            attempt = eq.record_attempt(cfg.state_dir, {
                **base_attempt, "outcome": "filled", "fill_price": res["fill_price"],
                "time_to_fill_sec": res.get("time_to_fill_sec"),
                "race_fill": res.get("race_fill")},
                journal=lambda event, **f: _journal(cfg, event, **f))
            _journal_entry_quality(cfg, attempt)
            return _register_passive_position(cfg, res=res, side=side, trigger_level=trigger_level,
                                              scenario_tag=scenario_tag, ab_index=ab_index, now=now)
        if res["outcome"] == "missed":
            attempt = eq.record_attempt(cfg.state_dir, {
                **base_attempt, "outcome": "missed",
                "time_resting_sec": res.get("time_resting_sec"),
                "partial_flattened": res.get("partial_flattened")},
                journal=lambda event, **f: _journal(cfg, event, **f))
            _journal_entry_quality(cfg, attempt)
            _journal(cfg, "ENTRY_MISSED", symbol=cfg.symbol, order_id=res.get("order_id"),
                    entry_mode="passive", ab_index=ab_index, scenario=scenario_tag,
                    limit_price=res.get("limit_price"), baseline_ask=res.get("baseline_ask"))
            return {"placed": False, "missed": True, "entry_mode": "passive",
                    "ab_index": ab_index, "passive": res}
        # outcome == "fallback" -- record it, then take the marketable path below
        fallback_reason = res.get("fallback_reason")
        attempt = eq.record_attempt(cfg.state_dir,
                                    {**base_attempt, "outcome": "fallback",
                                     "fallback_reason": fallback_reason},
                                    journal=lambda event, **f: _journal(cfg, event, **f))
        _journal_entry_quality(cfg, attempt)

    # MARKETABLE cohort (or passive fallback): the pre-B3 path, plus measurement.
    baseline_quote = broker.get_crypto_quote_hilo(cfg.symbol, creds=creds)
    baseline_ask = baseline_quote[0] if baseline_quote else price
    baseline_bid = baseline_quote[1] if baseline_quote else None
    t0 = time.monotonic()
    result = place_entry(cfg, creds=creds, side=side, price=price, trigger_level=trigger_level,
                         live=live, now_utc=now, scenario_tag=scenario_tag)
    fill_price = None
    if result.get("placed"):
        try:
            fill_price = float(result.get("fill", {}).get("filled_avg_price") or 0) or None
        except (TypeError, ValueError):
            fill_price = None
    attempt = eq.record_attempt(cfg.state_dir, {
        "cohort": "marketable", "ab_index": ab_index, "scenario": scenario_tag,
        "signal_price": price, "baseline_ask": baseline_ask, "baseline_bid": baseline_bid,
        "outcome": "filled" if result.get("placed") else "failed",
        "fill_price": fill_price,
        "time_to_fill_sec": round(time.monotonic() - t0, 3) if result.get("placed") else None,
        "fallback_from_passive": fallback_reason,
        "order_id": (result.get("order") or {}).get("id")},
        journal=lambda event, **f: _journal(cfg, event, **f))
    _journal_entry_quality(cfg, attempt)
    return {**result, "entry_mode": "marketable", "ab_index": ab_index,
            **({"fallback_from_passive": fallback_reason} if fallback_reason else {})}


# --- the tick (T1 + T2) -------------------------------------------------------------------
def run_tick(cfg: TwinConfig = TwinConfig(), *, live: bool = False,
            force_entry: Optional[str] = None, now_utc: Optional[datetime] = None,
            raw_bars: Optional[list[dict]] = None,
            trigger_level_offset_pct: Optional[float] = None,
            scenario_tag: Optional[str] = None,
            entry_mode_override: Optional[str] = None) -> dict:
    """ONE full twin tick: SEE -> DECIDE -> gate -> ACT -> manage -> journal -> log.
    Always writes a decisions.jsonl row (mirrors "persist EVERY tick", never conditional
    on ENTER). `force_entry` ("bull"/"bear") is TEST-ONLY: bypasses scoring to exercise
    the placement path on demand -- refuses outside a twin-namespaced cfg (see
    _assert_twin_namespace) and is never reachable except via this function's own
    `--force-entry` CLI flag.

    B1b additions (2026-07-11) -- both default None, so every pre-B1b caller (every call
    site except crypto_twin_scenarios.run_scenario_tick) is byte-identical to before:
      trigger_level_offset_pct: when set (only meaningful together with force_entry),
        OVERRIDES the normal nearest-real-level trigger_level lookup with
        `price * (1 + offset)`, computed HERE from the price this tick already fetched --
        no second bars/price fetch needed. Lets a scenario plant a synthetic trigger_level
        just above/below spot (e.g. ENTRY_STRUCTURE_STOP) without inventing a fake level.
      scenario_tag: threaded into place_entry's journal rows, the persisted position
        record, and this tick's own decision row (see `row_scenario` below) so a scenario
        position's WHOLE lifecycle stays taggable in decisions.jsonl/journal.jsonl.

    B3 addition (2026-07-14) -- defaults None, every pre-B3 caller byte-identical:
      entry_mode_override: VERIFICATION-ONLY (mirrors force_entry) -- forces the A/B
        cohort ("passive"|"marketable") without consuming an ab_index. Reachable only
        via this function's own `--force-entry-mode` CLI flag; production alternation
        comes from entry-quality.json's persisted counter (see place_entry_ab).
    """
    _assert_twin_namespace(cfg)
    now = now_utc or datetime.now(timezone.utc)

    # Captured BEFORE manage_positions runs (which may delete the position record this
    # very tick) -- the fallback so a CLOSING tick's decision row still reports which
    # scenario branch it just closed (see row_scenario below).
    scenario_before = _load_positions(cfg).get(cfg.symbol, {}).get("scenario")

    bars, bar_meta = fetch_closed_bars(cfg, now_utc=now, raw_bars=raw_bars)
    if not bars or bar_meta["verdict"] != "ok":
        verdict = sig.TwinVerdict("HOLD", None, None,
                                  reason=f"bar feed not ok: {bar_meta.get('verdict')}")
        row = _decision_row(cfg, now_utc=now, armed=live, price=None, verdict=verdict, levels=None,
                            risk_decision=None, breaker_state=None, position_status="unknown",
                            exit_pass=[], action="HOLD_BAD_BARS", scenario=None)
        log_decision(cfg, row)
        return row

    levels = tl.build_level_set(bars, now)
    price = bars[-1].close

    if force_entry in ("bull", "bear"):
        lvl = tl.nearest_directional_level(levels.all_levels, price, side=force_entry)
        if trigger_level_offset_pct is not None:
            resolved_trigger = round(price * (1.0 + trigger_level_offset_pct), 2)
        else:
            resolved_trigger = lvl.price if lvl else None
        verdict = sig.TwinVerdict(f"ENTER_{force_entry.upper()}", force_entry, "FORCE_ENTRY_TEST_FLAG",
                                  triggers=["force_entry_cli_flag"],
                                  reason="--force-entry test flag (bypasses scoring; T2 verification only)",
                                  trigger_level_exact=resolved_trigger,
                                  ribbon_stack="N/A", ribbon_spread=0.0, stack_bars=0)
    else:
        verdict = sig.evaluate(bars, levels)

    account_block_reason: Optional[str] = None
    try:
        creds = broker.get_twin_creds()
    except (FileNotFoundError, KeyError):
        creds = None
        account_block_reason = "BLOCKED_NO_ACCOUNT"
    except broker.CryptoNotApprovedError as e:
        creds = None
        account_block_reason = f"BLOCKED_CRYPTO_NOT_APPROVED: {e}"

    equity = cfg.starting_equity
    if creds is not None:
        acct = broker.get_account(creds)
        if not acct.get("_error"):
            equity = float(acct.get("equity", equity) or equity)

    breaker_state = load_breaker(cfg, now_utc=now, current_equity=equity)
    breaker_state = ks_tick(breaker_state, equity)
    save_breaker(cfg, breaker_state, now_utc=now, current_equity=equity)

    ribbon_stack = verdict.ribbon_stack if verdict.ribbon_stack != "N/A" else None
    exit_pass = manage_positions(cfg, creds=creds, now_utc=now, live=live, ribbon_stack=ribbon_stack,
                                 last_closed_close=price)

    positions = _load_positions(cfg)
    position_status = "open" if cfg.symbol in positions else "flat"
    risk_decision = None
    action = verdict.verdict if verdict.verdict != "HOLD" else "HOLD"
    entry_mode: Optional[str] = None

    if verdict.verdict.startswith("ENTER") and position_status == "flat":
        risk_decision = _risk_gate_check(cfg, equity=equity, sod_equity=breaker_state.start_of_day_equity,
                                         kill_switch_tripped=breaker_state.tripped,
                                         position_status=position_status,
                                         setup_name=verdict.setup or "CRYPTO_TWIN")
        if verdict.side == "bear":
            action = "SKIP_NO_SHORT_CRYPTO"  # Alpaca crypto is cash/long-only -- see place_entry docstring
        elif not risk_decision.allowed:
            action = f"BLOCKED_{risk_decision.code}"
        elif creds is None:
            action = account_block_reason or "BLOCKED_NO_ACCOUNT"
        else:
            result = place_entry_ab(cfg, creds=creds, side=verdict.side, price=price,
                                    trigger_level=verdict.trigger_level_exact, live=live, now_utc=now,
                                    scenario_tag=scenario_tag, entry_mode_override=entry_mode_override)
            entry_mode = result.get("entry_mode")
            if result.get("placed"):
                action = "ENTERED"
            elif result.get("missed"):
                # TWIN-B3: a passive limit that rested its full patience window and was
                # cancelled -- a MEASURED abandonment, not a failure. The scenario
                # scheduler treats it like any non-ENTERED tick (branch retried later).
                action = "PASSIVE_ENTRY_MISSED"
            else:
                action = "ENTRY_ATTEMPT_FAILED"
    elif position_status == "open":
        action = "MANAGED"

    # scenario tag for the row: the tag we were just handed IF an entry genuinely placed
    # this tick, else whatever was captured before management ran (covers HOLD/MANAGED
    # ticks on an already-open scenario position, and the tick that just closed one).
    row_scenario = scenario_tag if (scenario_tag is not None and action == "ENTERED") else scenario_before
    row = _decision_row(cfg, now_utc=now, armed=live, price=price, verdict=verdict, levels=levels,
                        risk_decision=risk_decision, breaker_state=breaker_state,
                        position_status=position_status, exit_pass=exit_pass, action=action,
                        scenario=row_scenario, entry_mode=entry_mode)
    log_decision(cfg, row)
    return row


# --- CLI ------------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Crypto Twin -- 24/7 mechanism-validation tick")
    parser.add_argument("--live", action="store_true", help="place real paper orders (default WATCH)")
    parser.add_argument("--force-entry", choices=["bull", "bear"], default=None,
                        help="TEST ONLY: bypass scoring and force an entry verdict")
    parser.add_argument("--force-entry-mode", choices=["passive", "marketable"], default=None,
                        help="VERIFICATION ONLY (TWIN-B3): force the A/B entry cohort for this "
                             "tick without consuming an ab_index (production alternation comes "
                             "from entry-quality.json's counter)")
    parser.add_argument("--ticks", type=int, default=1, help="number of ticks to run")
    args = parser.parse_args(argv)

    for i in range(max(1, args.ticks)):
        row = run_tick(live=args.live, force_entry=args.force_entry,
                      entry_mode_override=args.force_entry_mode)
        print(json.dumps(row, indent=2 if args.ticks == 1 else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""repeatability_decompose_2026_08_04.py -- LENS 4 "MAKE SURE WE CAN DO IT AGAIN".

THE QUESTION (J, verbatim intent): +$3,617.19 on 2026-08-04 was the best day on record by
~6.8x. How much of it is something we CONTROL (config / sizing / exits shipped the night
before) and how much of it is a generous tape? And does the same configuration BLEED on a
hard day?

WHAT THIS MODULE IS
-------------------
A per-arm, per-tick COUNTERFACTUAL ADMISSION replay that answers "what would the SAME tape
have paid under a DIFFERENT config", using:
  * ENTRY POPULATION  -- the REAL live decision ledgers (automation/state/fleet/<arm>/
    decisions.jsonl and automation/state/core-decisions.jsonl). NOT a re-derived signal
    stream. This is the single biggest sim-fidelity win available: the entry layer is not
    modelled at all, it is REPLAYED. Every tick already records (a) what setup the shared
    signal offered, (b) whether the arm's OWN gate passed, and (c) whether flatness was the
    only thing blocking it ("risk_gate denied: ... position already open").
  * EXIT LAYER        -- the REAL production exit core (automation/state/fleet/exit_manager.py
    plan_exit_actions) driven tick-by-tick by lib.exit_manager_walk.walk_exit_manager, on
    REAL 1-minute OPRA bars (backtest/data/highres via tools/_option_bars_1min_cache.py).
    Same primitives bold_fullhist_replay.py / fleet_arm_replay.py use -- imported, not
    copy-pasted.
  * GROUND TRUTH      -- automation/state/fills-ledger.jsonl FIFO round trips
    (automation/state/fleet/fills_fifo.py), the broker-verified P&L.

THE FLAT-STATE MACHINE (why this is a replay and not a guess)
-------------------------------------------------------------
Sequential one-position admission per arm is the whole game on a day like this: risky-1 and
risky-3 spent 09:46-10:37 ET holding vwap_continuation positions, and their ledgers show they
were offered the BULLISH_RECLAIM_RIDE_THE_RIBBON signal at 09:58-10:12 and refused it for one
reason only -- "position already open". Deleting the vwap entries (the yesterday-config lane)
therefore does NOT simply subtract their P&L: it FREES the arm to take the 09:58 ribbon ride
that safe-3/bold-2 took for +$373/+$614. A naive subtract-the-removed-trades decomposition
would have reported the vwap fix as worth ~2x what it is actually worth. The machine models
this by walking every tick in order and re-deciding admission against a simulated flat state.

ADMISSIBILITY IS READ OFF THE LEDGER, NEVER RE-DERIVED
------------------------------------------------------
A tick is ADMISSIBLE for an arm iff the ledger shows the arm's own gate said yes:
  * action starts with "ENTER"                          -> gate passed, arm entered
  * reason contains "position already open"             -> gate passed, only flatness blocked
Everything else (gate: requires confluence/sequence, no qualifying setup, no signal, killed)
is the arm's own machinery refusing, and is left refusing. A tick whose LIVE PLACEMENT was
refused for any reason OTHER than SKIP_DUPLICATE_CLAIM (SKIP_LATE_ENTRY, quote failures, PDT)
is also inadmissible in EVERY lane -- those are config-independent structural/time gates the
live tape already demonstrated. This is deliberately CONSERVATIVE: it can never invent an
entry the live gate would not have made.

THE 180-SECOND ENTRY CLAIM (modelled, because it is what actually paced 2026-08-04's morning)
----------------------------------------------------------------------------------------------
`fleet_live.ENTRY_CLAIM_TTL_SEC` / `heartbeat_core.ENTRY_CLAIM_TTL_SEC` = 180s, keyed on
(arm, SYMBOL). It is why risky-3's seven 09:46-09:57 ENTER_BULL ticks became FOUR fills: 09:46
claims 762C (09:48/09:49 refused, same symbol, inside TTL); 09:50 is a NEW symbol (763C) so it
places; 09:53 is inside 763C's TTL and is refused; 09:54 and 09:57 each clear the prior claim
by >180s. Without this the replay re-enters on every freed tick and manufactures P&L that the
production idempotency guard would have refused -- measured at +$942 of pure artifact on the
parity lane before it was modelled (found 2026-08-04 building this, not assumed).

CONFIG AXES (the four things that were newly live 2026-08-04)
--------------------------------------------------------------
  vwap_emission      FIX2 un-deadened vwap_continuation emission (import-dead since
                     2026-06-25, ZERO rows in 3,865 -- 2026-08-04 was its first live session).
                     False = yesterday.
  bold_core_offset   V15_BOLD_CORE_TIERS $2K-$10K row. 0 = ATM (today, ATM-TIER-EXTENSION-
                     2K-10K), -2 = OTM-2 (yesterday). Applies to bold-2/safe-3/risky-1/
                     risky-3; safe-2 is on V15_SAFE_TIERS and is UNAFFECTED.
  block_elite_bull   True = yesterday (blocks ELITE + level_reclaim BULL on the two CORES
                     only -- fleet_rest arms structurally never enforced GATE_ORDER, per
                     GATE-PROVENANCE-CENSUS-2026-07-09).
  anchor_to_fill     SHIP A. True = today (exit thresholds anchored to the real fill),
                     False = yesterday (anchored to entry_px, the marketable limit).

STRIKE RESOLUTION FOR THE COUNTERFACTUAL LANE
----------------------------------------------
Every arm traded ATM today (offset 0), so the live `strike` on each decision row IS
round(spot) at that tick -- the ATM anchor is observed, not modelled. OTM-2 for a CALL is
`round(spot) - (-2)` = live_strike + 2 (crypto/lib/strike_selection.pick_strike's own
formula). Puts would be live_strike - 2; today's tape is 100% calls and the runner asserts it.

ENTRY-PREMIUM CONVENTION FOR A CONTRACT WE DID NOT TRADE (disclosed, measured, not invented)
---------------------------------------------------------------------------------------------
For the ACTUAL contract at an ACTUAL entry we use the REAL broker fill. For a counterfactual
contract we take that minute's real OPRA close and multiply by the EXECUTION-COST RATIO
measured on the SAME tick for the contract we DID trade (real_fill / opra_close_same_minute).
That transfers the observed cross/slippage cost instead of assuming a frictionless fill.
When no paired live fill exists on that tick (a purely counterfactual admission, e.g. the
09:58 ribbon ride risky-3 could not take), the ratio falls back to the arm's own median ratio
for the day, and the row is flagged `exec_ratio_source="arm_median"`.

WHAT THIS DOES NOT MODEL (named, not hidden)
---------------------------------------------
  * Re-sizing under a cheaper OTM-2 contract. Live qty is held CONSTANT across lanes. Today's
    qtys were set by recency-RED clamps and FULL_SEND min-size floors, not by the risk cap, so
    a cheaper contract would not have raised them -- but a marginal case could. Conservative
    direction: it cannot inflate the counterfactual.
  * PDT accrual differences between lanes. Every lane stays under 3 day-trades/arm except
    where noted in the output's `pdt_note`.
  * Level-feed differences (the IEX-tail refresher fix). The counterfactual lane reuses the
    SAME trigger_levels the live tape produced, so this ship's contribution is NOT isolated
    here and is reported as UNMODELLED.
This module writes ONLY to analysis/deep-research/. It touches no trading-path file.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(BACKTEST / "lib"), str(BACKTEST / "tools"),
           str(REPO / "automation" / "state" / "fleet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.et_frame import FRAME_ET_V2  # noqa: E402
import engine_fullhist_replay as efr  # noqa: E402
from _option_bars_1min_cache import fetch_1min_cached  # noqa: E402
from fills_fifo import mine_real_arm_fills  # noqa: E402

FLEET_ARMS = ("safe-3", "risky-1", "risky-3")
CORE_ARMS = ("safe-2", "bold-2")
ALL_ARMS = CORE_ARMS + FLEET_ARMS
# safe-2 rides V15_SAFE_TIERS (ATM through $10K), untouched by ATM-TIER-EXTENSION-2K-10K.
BOLD_CORE_TIER_ARMS = frozenset({"bold-2", "safe-3", "risky-1", "risky-3"})
MIN_ENTRY_PREMIUM = 0.30           # automation/state/params.json + aggressive/params.json
DEFAULT_TIME_STOP = dt.time(15, 50)
FLAT_BLOCK_MARKER = "position already open"
VWAP_SETUPS = frozenset({"VWAP_CONTINUATION", "vwap_continuation"})
# fleet_live.ENTRY_CLAIM_TTL_SEC == heartbeat_core.ENTRY_CLAIM_TTL_SEC == 180, keyed (arm, symbol)
ENTRY_CLAIM_TTL_SEC = 180
# placement refusals that are NOT the claim guard are config-independent structural gates.
# "not_enter" is NOT a refusal -- it is the placement stub written on every non-ENTER tick
# (including the HOLD rows whose only blocker was flatness), so it must never gate admission.
CLAIM_SKIP_REASON = "SKIP_DUPLICATE_CLAIM"
NON_REFUSAL_PLACEMENT_REASONS = frozenset({"not_enter", ""})


# ---------------------------------------------------------------------------
# pure helpers (unit-tested -- see backtest/tests/test_repeatability_decompose_2026_08_04.py)
# ---------------------------------------------------------------------------
def otm2_strike(atm_strike: int, side: str) -> int:
    """OTM-2 strike from the ATM anchor, mirroring strike_selection.pick_strike's formula
    (BULL calls: strike = round(spot) - offset; BEAR puts: round(spot) + offset; offset=-2)."""
    if side == "C":
        return int(atm_strike) + 2
    if side == "P":
        return int(atm_strike) - 2
    raise ValueError(f"side must be 'C' or 'P', got {side!r}")


def occ_symbol(date_et: str, strike: int, side: str) -> str:
    """SPY OCC symbol for a 0DTE contract on date_et (ISO) at `strike`."""
    y, m, d = date_et.split("-")
    return f"SPY{y[2:]}{m}{d}{side}{int(strike) * 1000:08d}"


def tick_is_admissible(action: Optional[str], reason: Optional[str],
                       placement_reason: Optional[str] = None,
                       placed: Optional[bool] = None) -> bool:
    """The arm's OWN gate said yes on this tick: it either entered, or the only refusal was
    flatness. Anything else (its own gate, no signal, kill) stays refused.

    A live placement refusal that is NOT the 180s claim guard (SKIP_LATE_ENTRY, no-quote,
    PDT) is a config-INDEPENDENT structural gate and makes the tick inadmissible in every
    lane -- the live tape already proved the engine would not place there."""
    reason_txt = str(placement_reason or "")
    if (placed is False and reason_txt not in NON_REFUSAL_PLACEMENT_REASONS
            and CLAIM_SKIP_REASON not in reason_txt):
        return False
    if action and str(action).startswith("ENTER"):
        return True
    return FLAT_BLOCK_MARKER in (reason or "")


def claim_blocks(claims: dict, symbol: str, ts: dt.datetime,
                 ttl_sec: int = ENTRY_CLAIM_TTL_SEC) -> bool:
    """Mirror of fleet_live._claim_active / heartbeat_core._claim_active: an unexpired claim
    on this EXACT symbol refuses the entry outright. `claims` maps arm-scoped symbol -> the
    datetime the claim was written (claims are per-arm single-slot: writing a new symbol's
    claim overwrites the previous one, so only the LATEST claim can ever be active)."""
    last = claims.get("_symbol")
    if last is None or last != symbol:
        return False
    age = (ts - claims["_at"]).total_seconds()
    return 0 <= age < ttl_sec


def setup_allowed(setup: Optional[str], *, vwap_emission: bool) -> bool:
    """Under a config with FIX2 reverted, vwap_continuation never reaches strategies[]."""
    if setup is None:
        return False
    if not vwap_emission and setup in VWAP_SETUPS:
        return False
    return True


def core_elite_bull_blocked(quality: Optional[str], triggers, *, block_elite_bull: bool) -> bool:
    """gates.py gate #3: block when tier==ELITE and 'level_reclaim' in triggers (VIX band
    [0,25) -- 2026-08-04 ran VIX 15.57-16.42, inside the band on every tick, verified from
    the regime library, so the band is satisfied by construction for this date)."""
    if not block_elite_bull:
        return False
    return str(quality).upper() == "ELITE" and "level_reclaim" in (triggers or [])


def exec_cost_ratio(real_fill: float, opra_close: float) -> Optional[float]:
    """Observed execution cost as a multiplicative ratio on the same minute's OPRA close."""
    if not opra_close or opra_close <= 0 or not real_fill or real_fill <= 0:
        return None
    return real_fill / opra_close


def limit_anchor(entry_premium: float, live_limit: Optional[float],
                 live_fill: Optional[float], same_contract: bool) -> float:
    """The pre-SHIP-A exit anchor: the marketable limit (`fleet_broker.marketable_limit_price`
    = ask + entry_cross_buffer) rather than the true fill.

    BUG THIS EXISTS TO PREVENT (found + fixed 2026-08-04 building this harness, not assumed):
    on a lane that ALSO changes the strike, the live `entry_px` belongs to the ATM contract
    and is nonsense as an anchor for the OTM-2 contract -- anchoring a $0.42 option's exit
    state to $1.41 made the runner stop resolve ABOVE the entry and the walk booked fake
    PROFIT on a stop-out (YESTERDAY lane reported +$630 with six positive 'premium_stop'
    exits before this was caught). The cross buffer is a CENTS-level constant, so it is
    transferred ADDITIVELY (limit - fill on the paired live contract), never as a ratio.
    Raises on an anchor outside [0.5x, 2.0x] of the entry premium -- a loud failure beats a
    silently profitable stop-out."""
    if same_contract and live_limit:
        anchor = float(live_limit)
    elif live_limit and live_fill and live_limit > 0 and live_fill > 0:
        anchor = round(entry_premium + max(0.0, float(live_limit) - float(live_fill)), 4)
    else:
        anchor = float(entry_premium)
    if not (0.5 * entry_premium <= anchor <= 2.0 * entry_premium):
        raise ValueError(
            f"exit anchor {anchor} is outside [0.5x, 2.0x] of entry premium {entry_premium} "
            "-- a cross-contract anchor leak (see limit_anchor docstring)")
    return anchor


# ---------------------------------------------------------------------------
# config + row types
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LaneConfig:
    name: str
    vwap_emission: bool = True
    bold_core_offset: int = 0          # 0 = ATM (today), -2 = OTM-2 (yesterday)
    block_elite_bull: bool = False
    anchor_to_fill: bool = True
    hybrid: bool = True                # see HYBRID REPLAY below
    note: str = ""


# HYBRID REPLAY (the fidelity decision that makes this artifact quotable, 2026-08-04)
# -----------------------------------------------------------------------------------
# `hybrid=True` lanes take the REAL broker P&L and the REAL exit timestamp for any entry that
# matches a live round trip (same arm, same symbol, entry within +/-2 min), and simulate ONLY
# the entries that are genuinely counterfactual. Rationale: the ONLY thing the exit walk was
# needed for on an unchanged trade is a number the broker already knows exactly, and letting
# the sim answer it instead injects its 1-min-close sampling error into the FLAT-STATE MACHINE
# -- a sim exit even 4 minutes early frees the arm to take an entry the live engine held,
# manufacturing a whole extra round trip. Measured, not assumed: the all-simulated lane put
# SIM_TODAY at $4,342.33 against a real $3,624.00 (+19.8%) with three arms' entry COUNTS wrong;
# hybrid reproduces the day exactly and confines sim error to the counterfactual rows, which is
# the only place it is unavoidable. SIM_PURE_TODAY is retained precisely so that error stays
# MEASURED and quoted rather than hidden.
LANES: tuple[LaneConfig, ...] = (
    LaneConfig("SIM_PURE_TODAY", hybrid=False,
               note="all-simulated parity probe -- measures the exit-walk's own error vs broker"),
    LaneConfig("TODAY", note="baseline: today's config (hybrid -- reproduces the broker day)"),
    LaneConfig("REV_ELITE_GATE", block_elite_bull=True, note="leave-one-out: SHIP B reverted"),
    LaneConfig("REV_ATM_TIER", bold_core_offset=-2, note="leave-one-out: ATM-TIER-EXTENSION reverted"),
    LaneConfig("REV_VWAP_FIX", vwap_emission=False, note="leave-one-out: FIX2 vwap emission reverted"),
    # SHIP A moves ONLY the exit anchor on trades that really happened, so the hybrid lane --
    # which takes the broker's own answer for those -- is structurally blind to it and always
    # returns a 0.00 delta. Its effect is measurable ONLY as an all-simulated PAIR
    # (SIM_PURE_TODAY vs SIM_PURE_REV_SHIP_A), where the common-mode exit-walk bias cancels.
    LaneConfig("SIM_PURE_REV_SHIP_A", anchor_to_fill=False, hybrid=False,
               note="pair with SIM_PURE_TODAY -- the ONLY frame that can price SHIP A"),
    LaneConfig("YESTERDAY", vwap_emission=False, bold_core_offset=-2, block_elite_bull=True,
               anchor_to_fill=False, note="all four reverted -- the config that was live 2026-08-03"),
)


@dataclass
class Tick:
    ts: dt.datetime                 # naive ET
    arm: str
    setup: Optional[str]
    quality: Optional[str]
    triggers: list
    admissible: bool
    strike: Optional[int]
    side: Optional[str]
    qty: Optional[int]
    trigger_level: Optional[float]
    exit_shape: dict = field(default_factory=dict)
    structure_stop_enabled: bool = False
    entry_px_limit: Optional[float] = None   # marketable limit (pre-SHIP-A anchor)
    live_premium: Optional[float] = None     # the live mid the arm's OWN plan priced this tick at
    live_placed: bool = False


# ---------------------------------------------------------------------------
# ledger loading
# ---------------------------------------------------------------------------
def _naive_et(ts_str: str) -> dt.datetime:
    return dt.datetime.fromisoformat(ts_str).replace(tzinfo=None)


def _jsonl(path: Path, date_et: str, ts_key: str = "ts_et") -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get(ts_key, ""))[:10] == date_et:
                out.append(row)
    return out


def _exit_shape_from_placement(pl: dict) -> dict:
    """The exit shape the LIVE plan actually resolved for this entry (registry shape merged
    with the arm's exit_patch by fleet_executor._exit_shape_dict) -- taken verbatim from the
    placement payload rather than re-derived, so per-arm patches cannot drift."""
    shape = {
        "tp1_premium_pct": pl.get("tp1_premium_pct"),
        "tp1_qty_fraction": pl.get("tp1_qty_fraction"),
        "premium_stop_pct": pl.get("premium_stop_pct"),
        "profit_lock_mode": pl.get("profit_lock_mode"),
        "stop_mode": pl.get("stop_mode"),
    }
    for k in ("trail_pct", "runner_target_pct", "profit_lock_arm_pct",
              "profit_lock_arm_scope", "catastrophe_stop_pct", "pre_tp1_be_floor_arm_pct"):
        if pl.get(k) is not None:
            shape[k] = pl[k]
    return {k: v for k, v in shape.items() if v is not None}


def shared_trigger_levels(date_et: str) -> dict[str, float]:
    """core_tick_id -> trigger_level, joined across ALL fleet arms.

    WHY THIS JOIN EXISTS: the arms trade off ONE shared signal (build_shared_signal.py), so a
    level is a property of the SIGNAL, not of the arm. But a per-arm ledger row only carries
    `trigger_level` on the ENTER path -- the HOLD row an arm writes when flatness blocked it
    has `trigger_level: null` even for a level-tied ribbon ride. Without this join a
    counterfactual admission (the whole point of the vwap-revert lane: risky-1/risky-3 WERE
    offered the 09:58 ELITE ribbon and refused it only because a vwap position was open)
    would resolve stop_mode to "premium" instead of the structure stop the live plan used,
    and would be priced under the wrong exit contract."""
    out: dict[str, float] = {}
    for arm in FLEET_ARMS:
        for r in _jsonl(REPO / "automation" / "state" / "fleet" / arm / "decisions.jsonl", date_et):
            ctid, lvl = r.get("core_tick_id"), r.get("trigger_level")
            if ctid and lvl is not None:
                out.setdefault(str(ctid), float(lvl))
    return out


def load_fleet_ticks(arm: str, date_et: str,
                     shared_levels: Optional[dict] = None) -> list[Tick]:
    rows = _jsonl(REPO / "automation" / "state" / "fleet" / arm / "decisions.jsonl", date_et)
    shared_levels = shared_levels or {}
    ticks: list[Tick] = []
    # the LAST placed ENTER's shape is reused for counterfactual admissions on ticks that
    # never produced a placement payload (the arm was blocked by flatness, so no plan was
    # built); keyed by setup so a ribbon shape is never applied to a vwap admission.
    shape_by_setup: dict[str, tuple[dict, bool]] = {}
    for r in sorted(rows, key=lambda x: x["ts_et"]):
        pl = r.get("placement") or {}
        setup = r.get("setup_name")
        shape = _exit_shape_from_placement(pl) if pl.get("symbol") else {}
        struct = str(pl.get("stop_mode", "")).lower() == "structure"
        if shape and setup:
            shape_by_setup[setup] = (shape, struct)
        elif setup in shape_by_setup:
            shape, struct = shape_by_setup[setup]
        ticks.append(Tick(
            ts=_naive_et(r["ts_et"]), arm=arm, setup=setup,
            quality=r.get("quality"), triggers=[],
            admissible=tick_is_admissible(r.get("action"), r.get("reason"),
                                          pl.get("reason"), pl.get("placed")),
            strike=r.get("strike"), side=r.get("side"), qty=r.get("qty"),
            trigger_level=(r.get("trigger_level")
                           if r.get("trigger_level") is not None
                           else shared_levels.get(str(r.get("core_tick_id")))),
            exit_shape=shape,
            structure_stop_enabled=struct,
            entry_px_limit=pl.get("entry_px"),
            live_premium=r.get("premium"),
            live_placed=bool(pl.get("symbol") and pl.get("placed") is not False),
        ))
    # backfill shapes for early ticks whose setup only got a placement payload later
    for t in ticks:
        if not t.exit_shape and t.setup in shape_by_setup:
            t.exit_shape, t.structure_stop_enabled = shape_by_setup[t.setup]
    return ticks


def load_core_ticks(arm: str, date_et: str) -> list[Tick]:
    """Core arms (safe-2 / bold-2). core-decisions.jsonl carries the VERDICT + trigger set but
    no placement payload; the placed entries (strike/qty/fill) come from the fills ledger, and
    the exit shape from strategies.RIBBON_RIDE merged with the account's params, exactly as
    heartbeat_core registers it."""
    account = {"safe-2": "safe", "bold-2": "bold"}[arm]
    rows = [r for r in _jsonl(REPO / "automation" / "state" / "core-decisions.jsonl", date_et)
            if r.get("account") == account]
    fills = {r["entry_ts_et"][11:16]: r for r in mine_real_arm_fills(arm) if r["date"] == date_et}
    params_path = (REPO / "automation" / "state" / "params.json" if account == "safe"
                   else REPO / "automation" / "state" / "aggressive" / "params.json")
    params = json.loads(params_path.read_text(encoding="utf-8"))
    import strategies as fleet_strategies  # noqa: E402  (automation/state/fleet on sys.path)
    shape = fleet_strategies.RIBBON_RIDE.exit.to_dict()
    struct = bool(params.get("structure_stop_enabled", False))
    ticks: list[Tick] = []
    for r in sorted(rows, key=lambda x: x["ts_et"]):
        ts = _naive_et(r["ts_et"])
        verdict = str(r.get("verdict") or "")
        f = fills.get(ts.strftime("%H:%M"))
        ticks.append(Tick(
            ts=ts, arm=arm, setup=r.get("setup"), quality=_core_quality(r),
            triggers=list(r.get("triggers") or []),
            admissible=verdict.startswith("ENTER"),
            strike=(int(f["symbol"][-8:-3]) if f else None),
            side=r.get("side") or "C",
            qty=(int(f["qty"]) if f else None),
            trigger_level=r.get("trigger_level_exact"),
            exit_shape=shape, structure_stop_enabled=struct,
            entry_px_limit=None,
            live_placed=bool(f),
        ))
    return ticks


def _core_quality(row: dict) -> str:
    """core-decisions rows carry the tier inside `reason` ('... (tier ELITE)')."""
    reason = str(row.get("reason") or "")
    for tier in ("ELITE", "STRONG", "BASE", "SUPER"):
        if f"tier {tier}" in reason:
            return tier
    return ""


# ---------------------------------------------------------------------------
# market data
# ---------------------------------------------------------------------------
class OptCache:
    def __init__(self, date_et: str, ribbon_lookup: pd.DataFrame, spy_5m: pd.DataFrame):
        self.date_et = date_et
        self.ribbon_lookup = ribbon_lookup
        self.spy_5m = spy_5m
        self._bars: dict[str, Optional[pd.DataFrame]] = {}
        self._ribbon: dict[str, pd.DataFrame] = {}

    def bars(self, symbol: str) -> Optional[pd.DataFrame]:
        if symbol not in self._bars:
            df, _src = fetch_1min_cached(symbol, self.date_et)
            self._bars[symbol] = df
            if df is not None:
                self._ribbon[symbol] = efr.ribbon_tick_df_for(df, self.ribbon_lookup)
        return self._bars[symbol]

    def ribbon(self, symbol: str) -> Optional[pd.DataFrame]:
        self.bars(symbol)
        return self._ribbon.get(symbol)

    def close_at(self, symbol: str, ts: dt.datetime) -> Optional[float]:
        """Real OPRA close on the minute containing `ts` (or the last bar at/before it)."""
        df = self.bars(symbol)
        if df is None or df.empty:
            return None
        m = df[df["timestamp_et"] <= pd.Timestamp(ts).floor("min")]
        if m.empty:
            return None
        return float(m.iloc[-1]["close"])


def load_spy(date_et: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Newest rolling 5m SPY file, RTH rows for `date_et`, plus the continuous ribbon lookup
    (warmup preserved across the full file, exactly as engine_fullhist_replay builds it)."""
    files = sorted((BACKTEST / "data").glob("spy_5m_2026-05-19_*.csv"))
    if not files:
        raise FileNotFoundError("no rolling spy_5m file found")
    df = pd.read_csv(files[-1])
    df.columns = [c.lower() for c in df.columns]
    tcol = "timestamp_et" if "timestamp_et" in df.columns else df.columns[0]
    df["timestamp_et"] = pd.to_datetime(df[tcol], utc=True).dt.tz_convert(
        "America/New_York").dt.tz_localize(None)
    df = df.sort_values("timestamp_et").reset_index(drop=True)
    ribbon_lookup = efr.build_ribbon_lookup(df)
    day = df[df["timestamp_et"].dt.date == dt.date.fromisoformat(date_et)]
    day = day[(day["timestamp_et"].dt.time >= dt.time(9, 30))
              & (day["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    return day, ribbon_lookup


# ---------------------------------------------------------------------------
# the replay
# ---------------------------------------------------------------------------
def match_live_roundtrip(roundtrips: list[dict], symbol: str, ts: dt.datetime,
                         window_min: int = 2) -> Optional[dict]:
    """The live round trip this admission IS, or None if it is genuinely counterfactual.
    Matched on symbol + entry within +/-`window_min` (the decision tick and the broker fill
    timestamp differ by seconds-to-a-minute; the claim guard makes a same-symbol collision
    inside 2 minutes impossible, so the match is unambiguous)."""
    best, best_gap = None, None
    for r in roundtrips:
        if r["symbol"] != symbol:
            continue
        gap = abs((_naive_et(r["entry_ts_et"]) - ts).total_seconds())
        if gap <= window_min * 60 and (best_gap is None or gap < best_gap):
            best, best_gap = r, gap
    return best


def replay_arm(arm: str, date_et: str, lane: LaneConfig, ticks: list[Tick],
               cache: OptCache, real_fill_by_minute: dict, arm_median_ratio: float,
               real_roundtrips: Optional[list[dict]] = None) -> dict:
    real_roundtrips = real_roundtrips or []
    trades: list[dict] = []
    open_until: Optional[dt.datetime] = None
    claims: dict = {}
    for t in ticks:
        if open_until is not None and t.ts < open_until:
            continue
        if not t.admissible:
            continue
        if not setup_allowed(t.setup, vwap_emission=lane.vwap_emission):
            continue
        if arm in CORE_ARMS and core_elite_bull_blocked(
                t.quality, t.triggers, block_elite_bull=lane.block_elite_bull):
            continue
        if t.strike is None or t.side is None or not t.qty:
            continue  # no resolvable contract on this tick (never a live plan) -- skip loudly below
        offset = lane.bold_core_offset if arm in BOLD_CORE_TIER_ARMS else 0
        strike = t.strike if offset == 0 else otm2_strike(t.strike, t.side)
        symbol = occ_symbol(date_et, strike, t.side)
        if claim_blocks(claims, symbol, t.ts):
            continue

        matched = match_live_roundtrip(real_roundtrips, symbol, t.ts) if lane.hybrid else None
        if matched is not None:
            trades.append({
                "ts": t.ts.isoformat(), "symbol": symbol, "setup": t.setup, "quality": t.quality,
                "qty": int(matched["qty"]), "entry_premium": float(matched["entry_premium"]),
                "exit_anchor": float(matched["entry_premium"]), "exec_ratio_source": "real_broker_fill",
                "exit_reason": "REAL_BROKER_ROUNDTRIP",
                "exit_ts": matched["exit_ts_et"], "pnl": round(float(matched["real_pnl"]), 2),
                "source": "real", "legs": [],
            })
            claims = {"_symbol": symbol, "_at": t.ts}
            open_until = _naive_et(matched["exit_ts_et"])
            continue

        opt = cache.bars(symbol)
        if opt is None or opt.empty:
            trades.append({"ts": t.ts.isoformat(), "symbol": symbol, "skip": "no_opra_bars"})
            continue
        opra_close = cache.close_at(symbol, t.ts)
        if opra_close is None:
            trades.append({"ts": t.ts.isoformat(), "symbol": symbol, "skip": "no_opra_bar_at_tick"})
            continue

        live = real_fill_by_minute.get(t.ts.strftime("%H:%M"))
        ratio_source = "paired_live_fill"
        if live and offset == 0:
            entry_premium = float(live["entry_premium"])
        elif offset == 0 and t.live_premium:
            # UNCHANGED strike, no paired fill (the arm was blocked by flatness): the arm's own
            # ledger row already carries the live mid its plan priced this exact contract at.
            # That beats OPRA-close x median-ratio -- verified against 2026-08-04's real fills,
            # where ledger `premium` lands within ~2c of the eventual fill (safe-3 09:58
            # 1.38/1.38, risky-3 09:50 1.46/1.46, risky-3 09:46 1.77/1.75).
            entry_premium, ratio_source = float(t.live_premium), "arm_own_ledger_mid"
        else:
            ratio = None
            if live:
                ratio = exec_cost_ratio(float(live["entry_premium"]),
                                        cache.close_at(occ_symbol(date_et, t.strike, t.side), t.ts) or 0.0)
            if ratio is None:
                ratio, ratio_source = arm_median_ratio, "arm_median"
            entry_premium = round(opra_close * ratio, 2)
        if entry_premium < MIN_ENTRY_PREMIUM:
            trades.append({"ts": t.ts.isoformat(), "symbol": symbol,
                           "skip": "min_entry_premium_floor", "premium": entry_premium})
            continue

        anchor = (entry_premium if lane.anchor_to_fill else
                  limit_anchor(entry_premium, t.entry_px_limit,
                               (float(live["entry_premium"]) if live else None),
                               same_contract=(offset == 0)))
        res = walk_exit_manager(
            symbol=symbol, side=t.side, entry_time_et=t.ts, entry_premium=anchor,
            qty=int(t.qty), exit_shape=t.exit_shape or {},
            structure_stop_enabled=t.structure_stop_enabled,
            trigger_level=t.trigger_level, strategy=t.setup or "",
            time_stop_et=DEFAULT_TIME_STOP,
            opt_df=opt, ribbon_tick_df=cache.ribbon(symbol), five_min_spy_df=cache.spy_5m,
            opt_df_resolution="1min", frame=FRAME_ET_V2)
        # SHIP A only moves the EXIT thresholds' anchor; the cash actually paid is always the
        # real fill, so P&L is re-based off `entry_premium` regardless of the anchor used.
        pnl = sum((lg.fill_price - entry_premium) * lg.qty * 100 for lg in res.legs)
        if res.legs and sum(lg.qty for lg in res.legs) < int(t.qty):
            # unresolved remainder marked out at the last bar (mirrors EOD flatten)
            rem = int(t.qty) - sum(lg.qty for lg in res.legs)
            pnl += (float(opt.iloc[-1]["close"]) - entry_premium) * rem * 100
        trades.append({
            "ts": t.ts.isoformat(), "symbol": symbol, "setup": t.setup, "quality": t.quality,
            "qty": int(t.qty), "entry_premium": entry_premium, "exit_anchor": anchor,
            "exec_ratio_source": ratio_source,
            "exit_reason": res.exit_reason,
            "exit_ts": res.exit_time_et.isoformat() if res.exit_time_et else None,
            "pnl": round(pnl, 2),
            "legs": [{"kind": lg.kind, "qty": lg.qty, "px": lg.fill_price, "stage": lg.stage}
                     for lg in res.legs],
        })
        claims = {"_symbol": symbol, "_at": t.ts}
        open_until = res.exit_time_et or (t.ts + dt.timedelta(hours=6))
    filled = [x for x in trades if "pnl" in x]
    return {"arm": arm, "lane": lane.name, "n_entries": len(filled),
            "net": round(sum(x["pnl"] for x in filled), 2),
            "skips": [x for x in trades if "skip" in x], "trades": trades}


def run(date_et: str) -> dict:
    spy_5m, ribbon_lookup = load_spy(date_et)
    cache = OptCache(date_et, ribbon_lookup, spy_5m)
    ticks_by_arm = {}
    for arm in CORE_ARMS:
        ticks_by_arm[arm] = load_core_ticks(arm, date_et)
    shared_levels = shared_trigger_levels(date_et)
    for arm in FLEET_ARMS:
        ticks_by_arm[arm] = load_fleet_ticks(arm, date_et, shared_levels)

    real_by_arm, ratio_by_arm, rt_by_arm = {}, {}, {}
    for arm in ALL_ARMS:
        rts = [r for r in mine_real_arm_fills(arm) if r["date"] == date_et]
        rt_by_arm[arm] = rts
        real_by_arm[arm] = {r["entry_ts_et"][11:16]: r for r in rts}
        ratios = []
        for r in rts:
            c = cache.close_at(r["symbol"], _naive_et(r["entry_ts_et"]))
            got = exec_cost_ratio(float(r["entry_premium"]), c or 0.0)
            if got:
                ratios.append(got)
        ratio_by_arm[arm] = round(statistics.median(ratios), 6) if ratios else 1.0

    out = {"date_et": date_et, "lanes": {},
           "real_broker": {a: round(sum(r["real_pnl"] for r in mine_real_arm_fills(a)
                                        if r["date"] == date_et), 2) for a in ALL_ARMS},
           "exec_cost_ratio_median_by_arm": ratio_by_arm}
    out["real_broker"]["TOTAL"] = round(sum(v for k, v in out["real_broker"].items()), 2)
    for lane in LANES:
        per_arm = {}
        for arm in ALL_ARMS:
            per_arm[arm] = replay_arm(arm, date_et, lane, ticks_by_arm[arm], cache,
                                      real_by_arm[arm], ratio_by_arm[arm], rt_by_arm[arm])
        total = round(sum(v["net"] for v in per_arm.values()), 2)
        out["lanes"][lane.name] = {
            "config": {"vwap_emission": lane.vwap_emission,
                       "bold_core_offset": lane.bold_core_offset,
                       "block_elite_bull": lane.block_elite_bull,
                       "anchor_to_fill": lane.anchor_to_fill},
            "note": lane.note, "total": total,
            "per_arm": {a: {"net": v["net"], "n": v["n_entries"]} for a, v in per_arm.items()},
            "detail": per_arm,
        }
    out["parity"] = parity_block(out)
    return out


def parity_block(out: dict) -> dict:
    """Both parity reads, so neither can be quietly assumed.

    TODAY (hybrid)          -- must reproduce the broker day EXACTLY. If it does not, the
                               admission machine itself is wrong and no lane is quotable.
    SIM_PURE_TODAY (walk)   -- the exit walk's own standalone error. This is the honest error
                               bar on every counterfactual row, since counterfactual entries
                               have no broker answer and must be simulated."""
    real = out["real_broker"]
    rows = {}
    for arm in ALL_ARMS:
        h = out["lanes"]["TODAY"]["per_arm"][arm]
        p = out["lanes"]["SIM_PURE_TODAY"]["per_arm"][arm]
        r = real[arm]
        rows[arm] = {"real": r, "hybrid": h["net"], "hybrid_err": round(h["net"] - r, 2),
                     "sim_pure": p["net"], "sim_pure_err": round(p["net"] - r, 2),
                     "sim_pure_pct_err": (round(100 * (p["net"] - r) / abs(r), 1) if r else None),
                     "n_real": h["n"], "n_sim_pure": p["n"]}
    th, tp, tr = (out["lanes"]["TODAY"]["total"], out["lanes"]["SIM_PURE_TODAY"]["total"],
                  real["TOTAL"])
    return {"per_arm": rows, "total_real": tr, "total_hybrid": th, "total_sim_pure": tp,
            "hybrid_abs_err": round(th - tr, 2),
            "sim_pure_abs_err": round(tp - tr, 2),
            "sim_pure_pct_err": round(100 * (tp - tr) / abs(tr), 2),
            "gate": "PASS" if abs(th - tr) <= 1.0 else "FAIL",
            "known_residual": (
                "walk_exit_manager point-samples 1-min OPRA CLOSES; the live exit_actuator "
                "samples the running quote, so live can trip a stop/trail on an intra-minute "
                "print the closes never show. Confirmed on 2026-08-04: the pure walk holds "
                "risky-3's 09:50 763C to 09:56 (live 09:52) and safe-2's 12:28 769C to 13:51 "
                "(live 13:23) -- each a freed tick the flat-state machine then spends on an "
                "extra entry the live engine never made. This is exactly why counterfactual "
                "lanes are hybrid and why sim_pure_pct_err is the error bar on the rows that "
                "cannot be."),
            }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--date", default="2026-08-04")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    res = run(args.date)
    print(f"REAL BROKER  total ${res['real_broker']['TOTAL']:,.2f}   "
          + "  ".join(f"{a}=${res['real_broker'][a]:,.0f}" for a in ALL_ARMS))
    base = res["lanes"]["TODAY"]["total"]
    for name, lane in res["lanes"].items():
        d = lane["total"] - base
        print(f"{name:<16} total ${lane['total']:>10,.2f}   vs TODAY {d:>+10,.2f}   "
              + "  ".join(f"{a}={lane['per_arm'][a]['net']:,.0f}({lane['per_arm'][a]['n']})"
                          for a in ALL_ARMS))
    p = res["parity"]
    print(f"PARITY gate={p['gate']}  hybrid_err=${p['hybrid_abs_err']:,.2f}  "
          f"sim_pure_err=${p['sim_pure_abs_err']:,.2f} ({p['sim_pure_pct_err']:+.1f}%)")
    if args.out:
        Path(args.out).write_text(json.dumps(res, indent=1, default=str), encoding="utf-8")
        print("wrote", args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

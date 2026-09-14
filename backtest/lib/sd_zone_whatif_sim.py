"""sd_zone_whatif_sim.py -- pure simulation core for the SD-ZONE WHAT-IF shadow lane
(named `_sim`, not `sd_zone_whatif`, to avoid a basename collision with the CLI orchestrator
`setup/scripts/sd_zone_whatif.py` -- both would otherwise be importable as bare module
`sd_zone_whatif` depending on sys.path order, found live while smoke-testing this build).
(GOAL-SD-LIQUIDITY-ZONES-2026-09-11 item f, built 2026-09-14).

WHY THIS EXISTS: `backtest/tools/trigger_anchor_class_read.py --sd-zone` only ever labels
REAL ENGINE fills as in_zone/out_of_zone -- on a day the engine took zero SPY trades (e.g.
2026-09-14: SPY bounced clean off the 757.88-758.58 demand zone at 11:06 and ran to 760.80,
0 engine fills), that reader produces zero evidence. This module PLAYS the zone itself:
zone -> wait for the return -> confirmation -> hypothetical entry -> walk the SAME production
exit-stack decision core (`backtest.lib.exit_manager_walk.walk_exit_manager`) any real engine
position would use, across a small pre-registered grid of confirmation rules, exit shapes and
strikes. See `analysis/recommendations/prereg-sd-zone-anchor-promotion-2026-09-12.md` section 9
for the frozen rule set this module implements verbatim.

SCOPE, PURE vs I/O: this module is the PURE simulation core (touch/confirmation detection,
strike math, sizing, one-leg walk-through) -- it takes already-loaded DataFrames/dicts and
callables, never does its own network I/O or file I/O. The CLI orchestrator
(`setup/scripts/sd_zone_whatif.py`) does the fetching/caching/writing and calls into this
module. Guard #1 (backtest/tests/test_sd_zone_whatif.py): this module never imports
heartbeat_core / build_shared_signal / fleet_broker / exit_actuator / any order-placing
module, and never writes key-levels.json / params*.json / any automation/state/fleet/* file
-- it only READS `automation/state/fleet/strategies.py#RIBBON_RIDE` (the exit-shape
constant) and `automation/state/fleet/exit_manager.py` (via walk_exit_manager, transitively,
read-only) for the SAME reasons `exit_manager_walk.py` itself does.

DISCLOSED SIMPLIFICATIONS (read before trusting a number from this lane):
  1. RIBBON_FLIP EXIT STAGE IS INERT HERE. `walk_exit_manager`'s `ribbon_tick_df` parameter
     needs the SAME row cadence as `opt_df` (1-minute here); this build does not compute a
     1-minute ribbon series, so every call passes `ribbon_tick_df=None` -- the ribbon-flip
     exit stage can never fire (structure_stop / catastrophe / TP1 / trail / time_stop all
     stay fully wired). Per L243 (ribbon flip is a lagging exit), this is a minor loss.
  2. ARM $ FIGURES ARE LINEARLY SCALED, not independently re-walked. Each cell is walked
     ONCE at `CANONICAL_QTY` to get a clean per-contract $ figure (exit_manager's TP1/ladder
     fractions are qty-invariant in RATIO, so the canonical walk's per-contract P&L times an
     arm's own qty is exact modulo per-leg share-count rounding, negligible at
     `CANONICAL_QTY`). A true qty-specific walk per arm was judged not worth 5x the walker
     calls for a shadow/diagnostic lane; disclosed, not hidden.
  3. NO RE-ENTRY VARIANT. The prereg's grid names a `reentry=1` variant (one re-entry into a
     zone after a same-day stop) as a possible extension; this build implements only the
     baseline (`reentry=0`: a zone is touched/traded at most once per day). Every ledger row
     carries `reentry_variant: 0` so a future extension is additive, not a silent gap.
  4. ARM SIZING FORMULA is `max(min_contracts, floor(equity * risk_pct / (entry_premium *
     100)))` -- the plain-English reading of CLAUDE.md Rule 6, not a byte-for-byte port of
     `risk_gate.py`'s live check (out of scope for a $0 diagnostic script; disclosed, not
     claimed as parity).

Frozen rule set (verbatim, prereg section 9):
  Directions: demand zone -> CALL; supply zone -> PUT. Entry gate 09:35 ET, hard time stop
  15:40 ET, one open position at a time per (confirmation, exit_variant, strike) cell, no
  re-entry into the same zone after a stop that day (reentry=0 baseline, see #3 above).
  Confirmations: touch_close, structure_shift (PRIMARY), wick_reject.
  Exits: ribbon_ride (production RIBBON_RIDE shape), zone_to_zone (TP1 at nearest opposing
  zone edge, sell 2/3, same chandelier runner knobs).
  Strikes: ATM, OTM-1, OTM-2, ITM-1.
  Grid = 3 confirmations x 2 exits x 4 strikes = 24 cells per touch event.
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "crypto" / "lib", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
if str(REPO) not in sys.path:
    # REPO root on sys.path so `backtest.lib.structure_shift` resolves via Python's implicit
    # namespace-package mechanism (no backtest/__init__.py exists). This is REQUIRED, not a
    # style choice: structure_shift.py's own body does `from .filters import ...` (a relative,
    # package-context import) -- if THIS module instead imported it bare (`import
    # structure_shift` with only backtest/lib on sys.path, the dual-import-fallback pattern
    # used elsewhere in this codebase), that inner relative import raises "attempted relative
    # import with no known parent package" the first time a confirmation actually runs.
    # Found live building this module's own guard tests (backtest/tests/test_sd_zone_whatif.py).
    sys.path.insert(0, str(REPO))

from strike_selection import atm_strike  # noqa: E402
import strategies as _strategies  # noqa: E402

try:
    from .exit_manager_walk import walk_exit_manager  # noqa: E402
except ImportError:
    from exit_manager_walk import walk_exit_manager  # noqa: E402

# --------------------------------------------------------------------------- frozen grid

CONFIRMATIONS: tuple[str, ...] = ("touch_close", "structure_shift", "wick_reject")
PRIMARY_CONFIRMATION = "structure_shift"
EXIT_VARIANTS: tuple[str, ...] = ("ribbon_ride", "zone_to_zone")
PRIMARY_EXIT = "ribbon_ride"
STRIKE_LABELS: tuple[str, ...] = ("ATM", "OTM-1", "OTM-2", "ITM-1")
PRIMARY_STRIKE = "ATM"
# Signed offset per strike_selection.py's convention: negative = OTM, positive = ITM,
# applied via pick_strike's own formula (atm -/+ offset by side) -- see strike_for_label.
_STRIKE_OFFSETS: dict[str, int] = {"ATM": 0, "OTM-1": -1, "OTM-2": -2, "ITM-1": 1}

ARM_IDS: tuple[str, ...] = ("safe-2", "bold-2", "safe-3", "risky-1", "risky-3")
# risk_pct / min_contracts per CLAUDE.md Rule 6 (Safe 30% / 3 min; Bold 50% / 5 min) --
# every current arm is either a Safe-sizing or Bold/risky-sizing cell (accounts.json's
# grid.sizing_profiles). See disclosure #4 above.
_ARM_RISK_PROFILE: dict[str, tuple[float, int]] = {
    "safe-2": (0.30, 3), "safe-3": (0.30, 3),
    "bold-2": (0.50, 5), "risky-1": (0.50, 5), "risky-3": (0.50, 5),
}

ENTRY_GATE_ET = dt.time(9, 35)
HARD_TIME_STOP_ET = dt.time(15, 40)
CANONICAL_QTY = 300  # see disclosure #2

MAX_ROWS_WARN = 400


# --------------------------------------------------------------------------- pure helpers

def strike_for_label(spot: float, label: str, side: str) -> int:
    """Strike for a grid label, reusing strike_selection.atm_strike + its signed-offset/
    side-flip formula (see module docstring: this is NOT an equity-tier lookup -- the
    label IS the axis)."""
    if label not in _STRIKE_OFFSETS:
        raise ValueError(f"unknown strike label {label!r}")
    offset = _STRIKE_OFFSETS[label]
    atm = atm_strike(spot)
    return atm + offset if side == "P" else atm - offset


def zone_set_as_of(snapshots: list[dict], when: dt.datetime) -> tuple[list[dict], str]:
    """The LAST intraday snapshot with as_of <= `when` (no look-ahead, C6). `snapshots` is
    a list of {"as_of": iso-str, "zones": [...]}. Returns (zones, lookahead_caveat).

    SINGLE-SNAPSHOT (EOD-ONLY) DAY -- special-cased per the prereg's own rule: an
    end-of-day archive's `as_of` is, BY CONSTRUCTION, always later than any intraday touch
    it would otherwise be asked to cover (the daily archive is written at end-of-day) -- so
    a strict `as_of <= when` filter would make it inapplicable to literally every row and
    silently produce zero evidence for that day. Instead: when exactly ONE snapshot exists
    for the day, it is used for the WHOLE DAY regardless of its own as_of, and EVERY row
    that day is labeled `eod_snapshot_only` (a real look-ahead caveat the caller/reader must
    see, not silently absorbed) -- never blended with a `no_snapshot_before_touch` empty
    read. With TWO OR MORE snapshots (real intraday coverage), the strict `as_of <= when`
    rule applies with no caveat; `no_snapshot_before_touch` covers only the genuine case of
    a touch before the EARLIEST of several real intraday captures."""
    if not snapshots:
        return [], "no_snapshot_before_touch"
    if len(snapshots) == 1:
        return snapshots[0].get("zones") or [], "eod_snapshot_only"
    eligible = [s for s in snapshots if _parse_iso(s["as_of"]) <= when]
    if not eligible:
        return [], "no_snapshot_before_touch"
    best = max(eligible, key=lambda s: _parse_iso(s["as_of"]))
    return best.get("zones") or [], ""


def _parse_iso(s: str) -> dt.datetime:
    ts = pd.Timestamp(s)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.to_pydatetime()


def touch_hit(zone: dict, bar: dict) -> bool:
    """1-min bar low enters [low,high] (demand) / high enters it (supply) -- literal
    frozen definition (prereg section 9). 'liquidity'-kind zones (a naming heuristic
    third bucket sd_zones_producer.classify_zones can emit at spot==mid) are not
    directional S/D bases and are excluded from touches here."""
    if zone["kind"] == "demand":
        return zone["low"] <= bar["low"] <= zone["high"]
    if zone["kind"] == "supply":
        return zone["low"] <= bar["high"] <= zone["high"]
    return False


def find_touch_events(bars_1m: list[dict], snapshot_lookup: Callable[[dt.datetime], tuple[list[dict], str]],
                       gate_open: dt.time = ENTRY_GATE_ET, hard_stop: dt.time = HARD_TIME_STOP_ET
                       ) -> list[dict]:
    """First touch of each zone during [gate_open, hard_stop). `bars_1m`: list of
    {ts: datetime, open, high, low, close} sorted ascending. `snapshot_lookup(ts)` resolves
    the no-look-ahead zone set active at `ts` (see zone_set_as_of). One touch event per
    zone per day (reentry=0 baseline, disclosure #3): once a zone (keyed by its rounded
    low/high/kind) has produced a touch event, later bars never re-touch it."""
    touched_keys: set[tuple] = set()
    events: list[dict] = []
    for bar in bars_1m:
        t = bar["ts"].time()
        if t < gate_open or t >= hard_stop:
            continue
        zones, caveat = snapshot_lookup(bar["ts"])
        for z in zones:
            key = (round(z["low"], 2), round(z["high"], 2), z["kind"])
            if key in touched_keys:
                continue
            if touch_hit(z, bar):
                touched_keys.add(key)
                events.append({
                    "touch_ts": bar["ts"], "zone": z, "lookahead_caveat": caveat,
                })
    return events


# --------------------------------------------------------------------------- confirmations

def confirm_touch_close(bars_5m: list[dict], zone: dict, touch_ts: dt.datetime,
                         hard_stop: dt.time = HARD_TIME_STOP_ET) -> Optional[dt.datetime]:
    """First 5-min bar (ts >= touch_ts) whose CLOSE crosses back beyond the zone's far
    edge: above zone.high for demand, below zone.low for supply. Returns that bar's close
    time (ts + 5min), or None if it never fires before the hard time stop."""
    far = zone["high"] if zone["kind"] == "demand" else zone["low"]
    for row in bars_5m:
        if row["ts"] < touch_ts or row["ts"].time() >= hard_stop:
            continue
        ok = (row["close"] > far) if zone["kind"] == "demand" else (row["close"] < far)
        if ok:
            return row["ts"] + dt.timedelta(minutes=5)
    return None


def confirm_wick_reject(bars_5m: list[dict], zone: dict, touch_ts: dt.datetime,
                         hard_stop: dt.time = HARD_TIME_STOP_ET) -> Optional[dt.datetime]:
    """First 5-min bar (ts >= touch_ts) whose extreme sits in the zone AND whose close is
    in the favourable 50% of its own bar range."""
    for row in bars_5m:
        if row["ts"] < touch_ts or row["ts"].time() >= hard_stop:
            continue
        rng = row["high"] - row["low"]
        if rng <= 0:
            continue
        mid = (row["high"] + row["low"]) / 2.0
        if zone["kind"] == "demand":
            in_zone = zone["low"] <= row["low"] <= zone["high"]
            favorable = row["close"] >= mid
        else:
            in_zone = zone["low"] <= row["high"] <= zone["high"]
            favorable = row["close"] <= mid
        if in_zone and favorable:
            return row["ts"] + dt.timedelta(minutes=5)
    return None


def confirm_structure_shift(bars_5m_df: pd.DataFrame, zone: dict, touch_ts: dt.datetime,
                             hard_stop: dt.time = HARD_TIME_STOP_ET, k: int = 3
                             ) -> Optional[dt.datetime]:
    """PRIMARY variant. Scans candidate bar_idx values (ts >= touch_ts) forward, calling
    the ALREADY-RATIFIED `backtest.lib.structure_shift.detect_structure_shift_bull/bear`
    at each one (level = the zone's confirmation edge: zone.high for a demand reclaim,
    zone.low for a supply rejection). The first bar_idx that resolves counts as confirmed
    -- its own close time is the confirmation timestamp (mirrors StructureShift's own
    'confirmed_at_idx always equals bar_idx' framing)."""
    # Absolute package-qualified import (see the REPO sys.path note at module top) -- NOT the
    # dual try-relative/bare-absolute pattern used elsewhere in this codebase, because
    # structure_shift.py's OWN body does a package-relative `from .filters import ...`
    # internally; a bare top-level import of this module breaks THAT inner import.
    from backtest.lib.structure_shift import detect_structure_shift_bull, detect_structure_shift_bear

    level = zone["high"] if zone["kind"] == "demand" else zone["low"]
    ts_col = bars_5m_df["timestamp_et"]
    for idx in range(len(bars_5m_df)):
        ts = ts_col.iloc[idx]
        ts_py = ts.to_pydatetime() if hasattr(ts, "to_pydatetime") else ts
        if ts_py < touch_ts or ts_py.time() >= hard_stop:
            continue
        if zone["kind"] == "demand":
            hit = detect_structure_shift_bull(bars_5m_df, idx, [level], k=k)
        else:
            hit = detect_structure_shift_bear(bars_5m_df, idx, [level], k=k)
        if hit is not None:
            return ts_py + dt.timedelta(minutes=5)
    return None


_CONFIRM_FNS = {
    "touch_close": confirm_touch_close,
    "wick_reject": confirm_wick_reject,
}


def run_confirmation(name: str, bars_5m: list[dict], bars_5m_df: pd.DataFrame, zone: dict,
                      touch_ts: dt.datetime, hard_stop: dt.time = HARD_TIME_STOP_ET
                      ) -> Optional[dt.datetime]:
    if name == "structure_shift":
        return confirm_structure_shift(bars_5m_df, zone, touch_ts, hard_stop)
    fn = _CONFIRM_FNS.get(name)
    if fn is None:
        raise ValueError(f"unknown confirmation {name!r}")
    return fn(bars_5m, zone, touch_ts, hard_stop)


def entry_ts_after(bars_1m: list[dict], confirmed_ts: dt.datetime) -> Optional[dt.datetime]:
    """Next 1-min bar OPEN at/after `confirmed_ts` -- the entry timing rule."""
    for bar in bars_1m:
        if bar["ts"] >= confirmed_ts:
            return bar["ts"]
    return None


# --------------------------------------------------------------------------- zone_to_zone target

def pick_zone_to_zone_target(zones: list[dict], zone: dict) -> Optional[float]:
    """Nearest OPPOSING-kind zone edge beyond the touched zone, in the favourable
    direction: for a demand touch (CALL), the nearest supply zone's LOW edge above
    zone.high; for a supply touch (PUT), the nearest demand zone's HIGH edge below
    zone.low. None if no opposing zone exists (TP1 stays unreachable -- see
    tp1_pct_for_zone_to_zone)."""
    if zone["kind"] == "demand":
        candidates = [z["low"] for z in zones if z["kind"] == "supply" and z["low"] > zone["high"]]
        return min(candidates) if candidates else None
    candidates = [z["high"] for z in zones if z["kind"] == "demand" and z["high"] < zone["low"]]
    return max(candidates) if candidates else None


# --------------------------------------------------------------------------- sizing

def size_qty(entry_premium: float, equity: float, arm_id: str) -> int:
    """max(min_contracts, floor(equity*risk_pct / (entry_premium*100))) -- see disclosure
    #4. `equity` is injected by the caller (accounts.json's starting_equity per arm) so
    this module never reads that file itself."""
    risk_pct, min_contracts = _ARM_RISK_PROFILE[arm_id]
    if entry_premium is None or entry_premium <= 0:
        return min_contracts
    by_cap = int((equity * risk_pct) // (entry_premium * 100.0))
    return max(min_contracts, by_cap)


# --------------------------------------------------------------------------- leg walk

def walk_ribbon_ride(*, contract: str, side: str, entry_ts: dt.datetime, entry_premium: float,
                      zone: dict, opt_df: pd.DataFrame, five_min_spy_df: pd.DataFrame):
    exit_shape = _strategies.RIBBON_RIDE.exit.to_dict()
    trigger_level = zone["high"] if zone["kind"] == "demand" else zone["low"]
    return walk_exit_manager(
        symbol=contract, side=side, entry_time_et=entry_ts, entry_premium=entry_premium,
        qty=CANONICAL_QTY, exit_shape=exit_shape, structure_stop_enabled=True,
        trigger_level=trigger_level, strategy="ribbon_ride", time_stop_et=HARD_TIME_STOP_ET,
        opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=five_min_spy_df,
    )


def tp1_pct_for_zone_to_zone(*, target: Optional[float], side: str, entry_premium: float,
                              entry_ts: dt.datetime, bars_1m: list[dict],
                              opt_1m_df: pd.DataFrame, hard_stop: dt.time = HARD_TIME_STOP_ET
                              ) -> tuple[float, Optional[dt.datetime]]:
    """Scans SPY 1-min bars from entry to the hard stop for the first minute SPY trades
    at/through `target`; prices TP1 off the option's own 1-min bar OPEN at that minute
    (never Black-Scholes). Returns (tp1_premium_pct, reached_ts); tp1_premium_pct=99.0
    (unreachable, mirrors RIBBON_RIDE's own runner_target_pct convention) when `target`
    is None or never reached -- the walk then behaves as stop/trail/time_stop only, TP1
    never fires."""
    if target is None:
        return 99.0, None
    for bar in bars_1m:
        if bar["ts"] < entry_ts or bar["ts"].time() >= hard_stop:
            continue
        reached = (bar["high"] >= target) if side == "C" else (bar["low"] <= target)
        if not reached:
            continue
        opt_rows = opt_1m_df[opt_1m_df["timestamp_et"] >= bar["ts"]]
        if opt_rows.empty:
            continue
        opt_open = float(opt_rows.iloc[0]["open"])
        return round(opt_open / entry_premium - 1.0, 4), bar["ts"]
    return 99.0, None


def walk_zone_to_zone(*, contract: str, side: str, entry_ts: dt.datetime, entry_premium: float,
                       zone: dict, all_zones: list[dict], bars_1m: list[dict],
                       opt_df: pd.DataFrame, five_min_spy_df: pd.DataFrame):
    target = pick_zone_to_zone_target(all_zones, zone)
    tp1_pct, reached_ts = tp1_pct_for_zone_to_zone(
        target=target, side=side, entry_premium=entry_premium, entry_ts=entry_ts,
        bars_1m=bars_1m, opt_1m_df=opt_df)
    base = _strategies.RIBBON_RIDE.exit.to_dict()
    exit_shape = dict(base)
    exit_shape["tp1_premium_pct"] = tp1_pct
    exit_shape["tp1_qty_fraction"] = 0.667
    far_edge = (zone["low"] - 0.10) if zone["kind"] == "demand" else (zone["high"] + 0.10)
    result = walk_exit_manager(
        symbol=contract, side=side, entry_time_et=entry_ts, entry_premium=entry_premium,
        qty=CANONICAL_QTY, exit_shape=exit_shape, structure_stop_enabled=True,
        trigger_level=far_edge, strategy="ribbon_ride", time_stop_et=HARD_TIME_STOP_ET,
        opt_df=opt_df, ribbon_tick_df=None, five_min_spy_df=five_min_spy_df,
    )
    return result, {"target": target, "reached_ts": reached_ts.isoformat() if reached_ts else None,
                     "tp1_premium_pct": tp1_pct}

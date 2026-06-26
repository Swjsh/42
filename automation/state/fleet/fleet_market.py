"""fleet_market -- producer-side market fetch + the VWAP_CONTINUATION detector pass.

FIX2 (2026-06-25): build_shared_signal emits a `strategies[]` set so plan_all sees EVERY
validated edge independently, not just the single ribbon verdict the core ledger carries.
The ribbon side is re-keyed from the core row (build_shared_signal does that). The VWAP side
is the LARGE part: nothing on the live producer chain runs the VWAP detector, and it cannot
be reconstructed from the scalar core-ledger row (no bar series). So this module fetches the
session bars and runs detect_vwap_continuation_setup per tick.

UN-BLOCKABLE BY DESIGN: it reuses heartbeat_core's EXACT direct-Alpaca-REST path
(_fetch_spy_5m / _fetch_vix) -- NO TradingView / MCP / CDP dependency (matches the
beacon/core path). heartbeat_core is IMPORTED, never modified (its fetchers are lifted
read-only); importing it only inserts sys.path entries + reconfigures stdout (benign).

Pure read; no order placement; fail-safe (returns None on any fetch/detector miss so the
producer simply omits the VWAP strategy rather than crashing or guessing).
"""
from __future__ import annotations

import sys
from datetime import datetime, time as dt_time
from pathlib import Path
from typing import Any, Optional

FLEET_DIR = Path(__file__).resolve().parent
REPO_ROOT = FLEET_DIR.parents[2]

# backtest/lib (BarContext, watcher) + setup/scripts (heartbeat_core) on path.
for _p in ("backtest/lib", "setup/scripts"):
    _full = str(REPO_ROOT / _p)
    if _full not in sys.path:
        sys.path.insert(0, _full)

RTH_OPEN = dt_time(9, 30)
RTH_CLOSE = dt_time(16, 0)


def _lazy_imports():
    """Import the heavy deps lazily so importing fleet_market never costs pandas/yfinance
    unless a VWAP pass is actually requested (and so a missing dep degrades to None, not a
    producer crash). Returns (heartbeat_core, BarContext, detect_vwap_continuation_setup)
    or (None, None, None) on any import failure."""
    try:
        import heartbeat_core as hc  # un-blockable fetchers (NOT modified)
        from filters import BarContext
        from watchers.vwap_continuation_watcher import detect_vwap_continuation_setup
        return hc, BarContext, detect_vwap_continuation_setup
    except Exception:
        return None, None, None


def _rth_today(df, today) -> Any:
    """RTH rows for `today`, renamed timestamp->timestamp_et, sorted -- the full session
    frame the VWAP detector needs (it computes its OWN session VWAP off prior_bars)."""
    try:
        d = df.rename(columns={"timestamp": "timestamp_et"})
        ts = d["timestamp_et"]
        mask = (ts.dt.date == today) & (ts.dt.time >= RTH_OPEN) & (ts.dt.time < RTH_CLOSE)
        rth = d.loc[mask].sort_values("timestamp_et").reset_index(drop=True)
        return rth if not rth.empty else None
    except Exception:
        return None


def vwap_strategy_block(
    now: datetime,
    *,
    put_needs_rising_vix: bool = False,
    realized_vol_floor_bps: float = 0.0,
) -> Optional[dict]:
    """Run the VWAP_CONTINUATION detector for the current tick off live session bars.

    Returns a strategy-set entry dict (the FIX2 contract) when the detector fires:
        {"name": "vwap_continuation", "side": "C"|"P", "setup": "VWAP_CONTINUATION",
         "triggers": [...], "quality": "BASE", "est_premium": None, "spot": <last close>}
    or None when it does not fire (warmup / outside window / already-fired / no data).

    Direction maps long->C (calls), short->P (puts). Pure: no I/O beyond the read fetch,
    no order placement. Any failure (no creds, empty bars, import error) returns None so
    the producer simply omits the VWAP strategy this tick (never blocks the ribbon read)."""
    hc, BarContext, detect = _lazy_imports()
    if hc is None or BarContext is None or detect is None:
        return None
    try:
        df = hc._fetch_spy_5m()
    except Exception:
        return None
    if df is None or len(df) == 0:
        return None

    today = now.date()
    rth = _rth_today(df, today)
    if rth is None or len(rth) < 4:  # detector needs TREND_BARS(3)+1
        return None

    try:
        vix_now, vix_prior = hc._fetch_vix()
    except Exception:
        vix_now, vix_prior = 0.0, 0.0

    last = rth.iloc[-1]
    ctx = BarContext(
        bar_idx=len(rth) - 1,
        timestamp_et=last["timestamp_et"].to_pydatetime(),
        bar=last,
        prior_bars=rth,                 # FULL session RTH frame (detector reads its own VWAP)
        ribbon_now=None,                # VWAP detector does not read ribbon/level fields
        ribbon_history=[],
        vix_now=float(vix_now or 0.0),
        vix_prior=float(vix_prior or 0.0),
        vol_baseline_20=0.0,
        range_baseline_20=0.0,
        levels_active=[],
        multi_day_levels=[],
        htf_15m_stack=None,
    )
    try:
        sig = detect(ctx, put_needs_rising_vix=put_needs_rising_vix,
                     realized_vol_floor_bps=realized_vol_floor_bps)
    except Exception:
        return None
    if sig is None:
        return None

    side = "C" if sig.direction == "long" else "P"
    return {
        "name": "vwap_continuation",
        "side": side,
        "setup": sig.setup_name,                       # "VWAP_CONTINUATION"
        "triggers": list(sig.triggers_fired or []),
        "quality": "BASE",
        "est_premium": None,                           # runner fetches the real option mid
        "spot": float(last["close"]),
    }

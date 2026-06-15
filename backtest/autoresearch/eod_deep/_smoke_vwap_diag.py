"""DIAG: instrument vwap_rejection_detector to see WHICH filter rejects each bar today.

Run after _smoke_watchers.py to find the chokepoint. If vwap_watcher silent-skips
every bar today, find out why."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(REPO / "backtest"))

from autoresearch.eod_deep.modules._bar_features import compute_ribbon_cached
from lib.vwap_rejection_detector import (
    VwapRejectionParams,
    compute_session_vwap,
    _vol_baseline_20,
    _within_time_gate,
)


def diag_vwap(bar, bar_idx, spy_bars, ribbon_state, params):
    """Return tuple: (passed, reason_failed, diagnostics_dict)."""
    bar_time = bar["timestamp_et"]
    if not hasattr(bar_time, "time"):
        return False, "no_time", {}
    bar_t = bar_time.time()
    if not _within_time_gate(bar_t, params):
        return False, "time_gate", {"bar_t": str(bar_t)}

    if bar_idx < params.lookback_bars + 1:
        return False, "insufficient_history", {"bar_idx": bar_idx}

    bar_close = float(bar["close"])
    vwap_now = compute_session_vwap(spy_bars, bar_idx)
    if vwap_now != vwap_now:
        return False, "vwap_nan", {}
    distance = abs(bar_close - vwap_now)
    if distance > params.proximity_dollars:
        return False, "vwap_distance", {"vwap": vwap_now, "close": bar_close, "distance": distance, "threshold": params.proximity_dollars}

    bar_open = float(bar["open"])
    body_dollars = abs(bar_close - bar_open)
    if body_dollars < params.body_min_cents:
        return False, "body_too_small", {"body": body_dollars, "threshold": params.body_min_cents}

    bar_volume = float(bar["volume"])
    vol_base = _vol_baseline_20(spy_bars, bar_idx)
    if vol_base <= 0:
        return False, "no_vol_baseline", {}
    vol_ratio = bar_volume / vol_base
    if bar_volume < params.vol_mult * vol_base:
        return False, "vol_too_low", {"vol_ratio": vol_ratio, "threshold": params.vol_mult}

    # Check rejection footprint
    bear_rej_idx = None
    bull_rej_idx = None
    bar_date = bar_time.date()
    start = max(0, bar_idx - params.lookback_bars)
    for j in range(start, bar_idx):
        prior = spy_bars.iloc[j]
        prior_ts = prior["timestamp_et"]
        if not hasattr(prior_ts, "date") or prior_ts.date() != bar_date:
            continue
        prior_high = float(prior["high"])
        prior_low = float(prior["low"])
        prior_close = float(prior["close"])
        vwap_prior = compute_session_vwap(spy_bars, j)
        if vwap_prior != vwap_prior:
            continue
        if prior_high > vwap_prior and prior_close < vwap_prior:
            bear_rej_idx = j
        if prior_low < vwap_prior and prior_close > vwap_prior:
            bull_rej_idx = j

    if bear_rej_idx is None and bull_rej_idx is None:
        return False, "no_rejection_footprint", {"vwap": vwap_now, "lookback_start_idx": start}

    # Tie-break
    if bear_rej_idx is not None and bull_rej_idx is not None:
        if bear_rej_idx > bull_rej_idx:
            bull_rej_idx = None
        elif bull_rej_idx > bear_rej_idx:
            bear_rej_idx = None
        else:
            return False, "ambiguous_rejection", {}

    if bear_rej_idx is not None:
        direction = "short"
        if bar_close > vwap_now:
            return False, "current_bar_wrong_side", {"direction": direction, "close": bar_close, "vwap": vwap_now}
    else:
        direction = "long"
        if bar_close < vwap_now:
            return False, "current_bar_wrong_side", {"direction": direction, "close": bar_close, "vwap": vwap_now}

    if params.require_ribbon_agreement:
        if ribbon_state is None:
            return False, "no_ribbon_state", {}
        stack = str(ribbon_state.get("stack", "WARMUP"))
        spread_cents = float(ribbon_state.get("spread_cents", 0.0))
        if spread_cents < params.ribbon_min_spread_cents:
            return False, "ribbon_compressed", {"spread": spread_cents, "threshold": params.ribbon_min_spread_cents}
        if direction == "short" and stack != "BEAR":
            return False, "ribbon_disagrees", {"direction": direction, "stack": stack}
        if direction == "long" and stack != "BULL":
            return False, "ribbon_disagrees", {"direction": direction, "stack": stack}

    return True, "PASS", {"direction": direction}


def main():
    today_csv = REPO / "backtest" / "data" / "spy_5m_2026-05-08_2026-05-14.csv"
    df = pd.read_csv(today_csv)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    if df["timestamp_et"].dt.tz is not None:
        df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)

    today_rth = df[
        (df["timestamp_et"].dt.date == pd.Timestamp("2026-05-14").date()) &
        (df["timestamp_et"].dt.time >= pd.Timestamp("09:30").time()) &
        (df["timestamp_et"].dt.time < pd.Timestamp("16:00").time())
    ].reset_index(drop=True)

    full_master_csv = REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-12.csv"
    master = pd.read_csv(full_master_csv)
    master["timestamp_et"] = pd.to_datetime(master["timestamp_et"])
    if master["timestamp_et"].dt.tz is not None:
        master["timestamp_et"] = master["timestamp_et"].dt.tz_localize(None)
    multi_day = pd.concat([master, today_rth], ignore_index=True).drop_duplicates(subset=["timestamp_et"], keep="last").sort_values("timestamp_et").reset_index(drop=True)
    multi_ribbon = compute_ribbon_cached(multi_day)

    p = VwapRejectionParams()

    failure_reasons = {}
    pass_bars = []

    for _, bar in today_rth.iterrows():
        ix = multi_day.index[multi_day["timestamp_et"] == bar["timestamp_et"]]
        if len(ix) == 0:
            continue
        multi_idx = int(ix[0])
        rb = multi_ribbon.iloc[multi_idx]
        ribbon_state = {
            "fast": float(rb["fast"]),
            "pivot": float(rb["pivot"]),
            "slow": float(rb["slow"]),
            "stack": str(rb["ribbon_stack"]),
            "spread_cents": float(rb["ribbon_spread_cents"]),
        }
        passed, reason, diag = diag_vwap(bar, multi_idx, multi_day, ribbon_state, p)
        failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
        if passed:
            pass_bars.append((str(bar["timestamp_et"])[11:16], diag))

    print("VWAP filter chokepoint per-bar:")
    for r, n in sorted(failure_reasons.items(), key=lambda x: -x[1]):
        print(f"  {r}: {n}/{len(today_rth)}")

    if pass_bars:
        print(f"\nBars that PASSED ({len(pass_bars)}):")
        for t, d in pass_bars:
            print(f"  {t}: {d}")
    else:
        print("\nNo bars passed all filters today.")

    # Show first 8 ribbon spreads on today's bars to confirm magnitude
    print("\nFirst 12 today RTH bars — ribbon spread + body + vol + vwap distance:")
    for i, (_, bar) in enumerate(today_rth.iterrows()):
        if i >= 12:
            break
        ix = multi_day.index[multi_day["timestamp_et"] == bar["timestamp_et"]]
        if len(ix) == 0:
            continue
        multi_idx = int(ix[0])
        rb = multi_ribbon.iloc[multi_idx]
        vwap_now = compute_session_vwap(multi_day, multi_idx)
        body = abs(float(bar["close"]) - float(bar["open"]))
        vol_base = _vol_baseline_20(multi_day, multi_idx)
        vol_ratio = float(bar["volume"]) / vol_base if vol_base > 0 else 0
        distance = abs(float(bar["close"]) - vwap_now) if vwap_now == vwap_now else -1
        print(f"  {str(bar['timestamp_et'])[11:16]}: spread={rb['ribbon_spread_cents']:.1f}c body=${body:.2f} vol_x={vol_ratio:.2f} d_to_vwap=${distance:.2f} stack={rb['ribbon_stack']}")


if __name__ == "__main__":
    main()

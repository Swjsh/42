"""F8 flat-VIX targeted analysis — Chef research (2026-05-19).

Key insight from f8_vix_decline_threshold_sweep.py:
    - "Flat" VIX (within +-0.05 deadband) blocked 13,328 bars vs. only 526 truly "falling" bars.
    - The production F8 requires vd == "rising" (strict), meaning flat is treated as blocked.
    - On 2026-05-19: 66 of 76 RTH bars had VIX decline < 0.25 (noise-level),
      and 0 bars had decline > 0.50. These were classified as "flat" but also blocked.

Two targeted fixes to evaluate:
    A. Allow flat VIX: change F8 to pass if vix_now > 17.30 AND vd IN {rising, flat}
       This is a minimal patch — flat = no strong directional change.

    B. Allow flat OR noise-falling (< 0.25): pass if vix_now > 17.30 AND
       (vd == "rising" OR (vd == "flat") OR decline_from_session_high < 0.25)
       This directly addresses the 2026-05-19 scenario.

Critical guard: on 5/05, 5/06, 5/07 — what was the VIX behavior?
    5/05: VIX was declining (market recovered — volatility regime change IS valid block)
    5/06: ?
    5/07: ?

We analyze the VIX direction profile on each loser day to understand if flat-VIX
unlocks would be dangerous there.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backtest.lib.filters import vix_direction, VIX_BEAR_THRESHOLD, VIX_RISING_DEADBAND

DATA_DIR = ROOT / "backtest" / "data"
VIX_BEAR_THRESHOLD_F8 = VIX_BEAR_THRESHOLD  # 17.30
WR_PROXY_BARS = 3
WR_PROXY_DROP = 0.50

J_WINNER_DATES = {"2026-04-29", "2026-05-01", "2026-05-04"}
J_LOSER_DATES  = {"2026-05-05", "2026-05-06", "2026-05-07"}
J_OBSERVED_DATE = {"2026-05-19"}


def _load_aligned() -> tuple[pd.DataFrame, pd.Series]:
    spy = pd.read_csv(DATA_DIR / "spy_5m_2025-01-01_2026-05-15.csv")
    vix = pd.read_csv(DATA_DIR / "vix_5m_2025-01-01_2026-05-15.csv")
    # extend
    try:
        spy_ext = pd.read_csv(DATA_DIR / "spy_5m_2026-05-08_2026-05-19.csv")
        vix_ext = pd.read_csv(DATA_DIR / "vix_5m_2026-05-08_2026-05-19.csv")
        spy = pd.concat([spy, spy_ext], ignore_index=True)
        vix = pd.concat([vix, vix_ext], ignore_index=True)
    except Exception as e:
        print(f"Warning: extension load failed: {e}")

    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"], utc=True)
    vix["timestamp_et"] = pd.to_datetime(vix["timestamp_et"], utc=True, errors="coerce")
    if vix["timestamp_et"].isna().all():
        vix["timestamp_et"] = pd.to_datetime(vix["timestamp_et"]).dt.tz_localize("UTC")

    spy = spy.drop_duplicates(subset=["timestamp_et"]).sort_values("timestamp_et").reset_index(drop=True)
    vix = vix.drop_duplicates(subset=["timestamp_et"]).sort_values("timestamp_et").reset_index(drop=True)

    # Normalize timestamps to int64 nanoseconds for monotonic guarantee
    spy["ts_ns"] = spy["timestamp_et"].astype("int64")
    vix["ts_ns"] = vix["timestamp_et"].astype("int64")

    # Use merge_asof (forward-fill) — both must be sorted by key
    spy = spy.sort_values("ts_ns").reset_index(drop=True)
    vix_slim = vix[["ts_ns", "close"]].rename(columns={"close": "vix_close"}).sort_values("ts_ns")
    vix_slim = vix_slim.drop_duplicates(subset=["ts_ns"])
    merged = pd.merge_asof(spy, vix_slim, on="ts_ns", direction="backward")
    aligned = merged["vix_close"].reset_index(drop=True)
    aligned.index = range(len(spy))

    spy["date_str"] = spy["timestamp_et"].apply(_date_str)
    return spy, aligned


def _date_str(ts: pd.Timestamp) -> str:
    if ts.tzinfo is not None:
        ts = ts.tz_convert("US/Eastern")
    return ts.strftime("%Y-%m-%d")


def _is_rth_bear_window(ts: pd.Timestamp) -> bool:
    import datetime as dt
    if ts.tzinfo is not None:
        ts = ts.tz_convert("US/Eastern")
    t = ts.time()
    return dt.time(9, 35) <= t < dt.time(15, 55)


def _spy_drops_after(spy_df: pd.DataFrame, idx: int, n_bars: int, threshold: float) -> bool:
    end_idx = min(idx + n_bars + 1, len(spy_df))
    future = spy_df["close"].iloc[idx + 1: end_idx]
    if len(future) == 0:
        return False
    entry_close = float(spy_df["close"].iloc[idx])
    return (entry_close - float(future.min())) >= threshold


def _analyze_loser_day_vix_profile(
    date_str: str,
    spy_df: pd.DataFrame,
    vix_aligned: pd.Series,
) -> dict:
    """Break down VIX direction profile for a loser day."""
    mask = spy_df["date_str"] == date_str
    day_idx = spy_df.index[mask].tolist()

    profile = {
        "date": date_str,
        "bars_scanned": 0,
        "bars_above_vix_threshold": 0,
        "rising": 0,
        "flat": 0,
        "falling": 0,
        "flat_bars_wr_proxy": 0,
        "flat_bars_total": 0,
        "vix_open": None,
        "vix_close": None,
        "vix_max": None,
        "vix_min": None,
    }
    vix_vals = []

    for idx in day_idx:
        if idx < 2:
            continue
        ts = spy_df["timestamp_et"].iloc[idx]
        if not _is_rth_bear_window(ts):
            continue
        profile["bars_scanned"] += 1
        vix_now = vix_aligned.iloc[idx]
        vix_prior = vix_aligned.iloc[idx - 1]
        if pd.isna(vix_now) or pd.isna(vix_prior):
            continue
        vix_vals.append(float(vix_now))
        if vix_now > VIX_BEAR_THRESHOLD_F8:
            profile["bars_above_vix_threshold"] += 1
        vd = vix_direction(vix_now, vix_prior)
        profile[vd] += 1
        if vd == "flat" and vix_now > VIX_BEAR_THRESHOLD_F8:
            profile["flat_bars_total"] += 1
            if _spy_drops_after(spy_df, idx, WR_PROXY_BARS, WR_PROXY_DROP):
                profile["flat_bars_wr_proxy"] += 1

    if vix_vals:
        profile["vix_open"] = round(vix_vals[0], 3)
        profile["vix_close"] = round(vix_vals[-1], 3)
        profile["vix_max"] = round(max(vix_vals), 3)
        profile["vix_min"] = round(min(vix_vals), 3)
        profile["vix_range"] = round(max(vix_vals) - min(vix_vals), 3)

    if profile["flat_bars_total"] > 0:
        profile["flat_bars_wr_pct"] = round(
            profile["flat_bars_wr_proxy"] / profile["flat_bars_total"], 3
        )
    else:
        profile["flat_bars_wr_pct"] = None

    return profile


def _count_fix_unlocks_per_day(
    date_str: str,
    spy_df: pd.DataFrame,
    vix_aligned: pd.Series,
    fix: str,  # "flat_only" | "flat_or_noise25"
) -> dict:
    """Count how many bars are unlocked for a specific day under Fix A or B."""
    mask = spy_df["date_str"] == date_str
    day_idx = spy_df.index[mask].tolist()
    unlocked = 0
    unlocked_wins = 0

    for idx in day_idx:
        if idx < 5:
            continue
        ts = spy_df["timestamp_et"].iloc[idx]
        if not _is_rth_bear_window(ts):
            continue
        vix_now = vix_aligned.iloc[idx]
        vix_prior = vix_aligned.iloc[idx - 1]
        if pd.isna(vix_now) or pd.isna(vix_prior):
            continue
        if vix_now <= VIX_BEAR_THRESHOLD_F8:
            continue

        vd = vix_direction(vix_now, vix_prior)
        # Original: only rising passes
        orig_pass = (vd == "rising")

        if fix == "flat_only":
            new_pass = vd in {"rising", "flat"}
        elif fix == "flat_or_noise25":
            # Compute 5-bar session high for decline measure
            start = max(0, idx - 5)
            session_high = float(vix_aligned.iloc[start: idx + 1].dropna().max())
            decline = session_high - float(vix_now)
            new_pass = vd in {"rising", "flat"} or decline < 0.25
        else:
            new_pass = orig_pass

        if new_pass and not orig_pass:
            unlocked += 1
            if _spy_drops_after(spy_df, idx, WR_PROXY_BARS, WR_PROXY_DROP):
                unlocked_wins += 1

    return {
        "date": date_str,
        "fix": fix,
        "unlocked": unlocked,
        "unlocked_wins": unlocked_wins,
        "wr": round(unlocked_wins / unlocked, 3) if unlocked > 0 else None,
    }


def run():
    print("Loading data...")
    spy_df, vix_aligned = _load_aligned()
    all_dates = sorted(spy_df["date_str"].unique())
    print(f"  {len(all_dates)} trading days ({all_dates[0]} to {all_dates[-1]})")

    # === Loser day VIX profiles ===
    print("\n=== Loser day VIX profiles ===")
    loser_profiles = {}
    for d in sorted(J_LOSER_DATES):
        if d not in all_dates:
            print(f"  {d}: NOT IN DATASET")
            continue
        p = _analyze_loser_day_vix_profile(d, spy_df, vix_aligned)
        loser_profiles[d] = p
        print(f"\n  {d}:")
        print(f"    VIX open={p['vix_open']} max={p['vix_max']} min={p['vix_min']} close={p['vix_close']} range={p.get('vix_range',0):.3f}")
        print(f"    Direction breakdown: rising={p['rising']} flat={p['flat']} falling={p['falling']} of {p['bars_scanned']} bars")
        print(f"    Flat bars above threshold: {p['flat_bars_total']} (WR proxy: {p['flat_bars_wr_pct']})")

    # === Winner day VIX profiles ===
    print("\n=== Winner day VIX profiles ===")
    winner_profiles = {}
    for d in sorted(J_WINNER_DATES):
        if d not in all_dates:
            print(f"  {d}: NOT IN DATASET")
            continue
        p = _analyze_loser_day_vix_profile(d, spy_df, vix_aligned)
        winner_profiles[d] = p
        print(f"\n  {d}:")
        print(f"    VIX open={p['vix_open']} max={p['vix_max']} min={p['vix_min']} close={p['vix_close']} range={p.get('vix_range',0):.3f}")
        print(f"    Direction breakdown: rising={p['rising']} flat={p['flat']} falling={p['falling']} of {p['bars_scanned']} bars")
        print(f"    Flat bars above threshold: {p['flat_bars_total']} (WR proxy: {p['flat_bars_wr_pct']})")

    # === 2026-05-19 profile ===
    print("\n=== 2026-05-19 (observed trigger day) ===")
    may19_profile = _analyze_loser_day_vix_profile("2026-05-19", spy_df, vix_aligned)
    print(f"    VIX open={may19_profile['vix_open']} max={may19_profile['vix_max']} min={may19_profile['vix_min']} close={may19_profile['vix_close']}")
    print(f"    Direction: rising={may19_profile['rising']} flat={may19_profile['flat']} falling={may19_profile['falling']}")
    print(f"    Flat bars above threshold: {may19_profile['flat_bars_total']} (WR: {may19_profile['flat_bars_wr_pct']})")

    # === Fix A vs B on all key dates ===
    print("\n=== Fix A (flat allowed) vs Fix B (flat+noise25) on key dates ===")
    fix_results = {}
    for fix in ["flat_only", "flat_or_noise25"]:
        print(f"\n  Fix: {fix}")
        fix_results[fix] = {}
        for d in sorted(J_LOSER_DATES | J_WINNER_DATES | J_OBSERVED_DATE):
            if d not in all_dates:
                continue
            r = _count_fix_unlocks_per_day(d, spy_df, vix_aligned, fix)
            fix_results[fix][d] = r
            tag = "LOSER" if d in J_LOSER_DATES else ("WINNER" if d in J_WINNER_DATES else "TRIGGER")
            print(f"    {d} [{tag}]: unlocked={r['unlocked']} wins={r['unlocked_wins']} wr={r['wr']}")

    # === Global aggregate for each fix ===
    print("\n=== Global aggregate Fix A vs Fix B ===")
    for fix in ["flat_only", "flat_or_noise25"]:
        total_ul = 0
        total_wins = 0
        loser_ul = 0
        winner_ul = 0
        for d in all_dates:
            r = _count_fix_unlocks_per_day(d, spy_df, vix_aligned, fix)
            total_ul += r["unlocked"]
            total_wins += r["unlocked_wins"]
            if d in J_LOSER_DATES:
                loser_ul += r["unlocked"]
            if d in J_WINNER_DATES:
                winner_ul += r["unlocked"]
        wr = round(total_wins / total_ul, 3) if total_ul > 0 else 0
        print(f"\n  {fix}:")
        print(f"    Total newly unlocked: {total_ul}  WR proxy: {wr}")
        print(f"    Loser-day unlocked: {loser_ul}")
        print(f"    Winner-day unlocked: {winner_ul}")
        fix_results[fix]["_aggregate"] = {
            "total_unlocked": total_ul,
            "total_wins": total_wins,
            "wr": wr,
            "loser_day_total": loser_ul,
            "winner_day_total": winner_ul,
            "loser_guard_intact": loser_ul == 0,
        }

    # Save
    out = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "loser_day_vix_profiles": loser_profiles,
        "winner_day_vix_profiles": winner_profiles,
        "may19_vix_profile": may19_profile,
        "fix_comparison": fix_results,
    }
    out_path = ROOT / "analysis" / "recommendations" / "f8_flat_vix_analysis.json"
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2, default=str)
    print(f"\nResults written: {out_path}")
    return out


if __name__ == "__main__":
    run()

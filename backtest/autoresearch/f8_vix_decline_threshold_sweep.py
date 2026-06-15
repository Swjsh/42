"""F8 VIX decline threshold sweep — Chef research (2026-05-19).

Research question:
    F8 currently blocks bear entries when VIX direction == "falling" (any 1-bar decline
    beyond a 0.05-point deadband). On 2026-05-19, VIX drifted 22bps lower all session
    while SPY fell $3+. F8 blocked all bear entries after 10:24 ET.

    What is the optimal threshold so that noise-level VIX drifts don't block valid
    bear sessions, while genuine VIX collapses (volatility regime change) still block?

Algorithm:
    For each threshold T in [0.0, 0.25, 0.50, 0.75, 1.00]:
        Modified F8 rule:
          OLD: pass if vix_now > 17.30 AND vix_direction(now, prior) == "rising"
          NEW: pass if vix_now > 17.30 AND (vix_rising OR vix_decline_from_session_ref <= T)
               where vix_decline_from_session_ref = max(vix_last_N_bars) - vix_now

        For each 5m bar in the full 16-month dataset:
          1. Compute the original F8 result (T=0.0, current production behavior)
          2. Compute new F8 result for threshold T
          3. Track: would this bar have been an additional bear entry under new rule?
          4. Use next-3-bar SPY price action as WR proxy: did SPY drop >= $0.50?

    Critical guard: on J's known loser days (5/05, 5/06, 5/07), count any ADDITIONAL
    bear trades unlocked by each threshold (these are harmful if the engine adds trades).
    On J's winner days (4/29, 5/01, 5/04), count beneficial unlocks.

Output: analysis/recommendations/f8_vix_decline_sweep.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import numpy as np

# ── project root ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from backtest.lib.filters import vix_direction, VIX_BEAR_THRESHOLD, VIX_RISING_DEADBAND

# ── constants ─────────────────────────────────────────────────────────────────
THRESHOLDS = [0.0, 0.25, 0.50, 0.75, 1.00]  # VIX must decline MORE than this to block
LOOKBACK_BARS = 5   # how many prior bars to look back for session-high VIX reference
WR_PROXY_BARS = 3   # bars forward to check if SPY dropped (WR proxy)
WR_PROXY_DROP = 0.50  # SPY must drop >= $0.50 in next N bars to count as "win"
VIX_BEAR_THRESHOLD_F8 = VIX_BEAR_THRESHOLD  # 17.30

# J's key trade days
J_WINNER_DATES = {"2026-04-29", "2026-05-01", "2026-05-04"}
J_LOSER_DATES  = {"2026-05-05", "2026-05-06", "2026-05-07"}
J_OBSERVED_DATE = {"2026-05-19"}  # the triggering observation

# ── data loading ──────────────────────────────────────────────────────────────
DATA_DIR = ROOT / "backtest" / "data"

def _load_spy_vix(spy_csv: str, vix_csv: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    spy = pd.read_csv(DATA_DIR / spy_csv)
    vix = pd.read_csv(DATA_DIR / vix_csv)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"], utc=True)
    # VIX timestamps may or may not have tz — normalize
    vix["timestamp_et"] = pd.to_datetime(vix["timestamp_et"], utc=True, errors="coerce")
    if vix["timestamp_et"].isna().all():
        # Try without utc
        vix["timestamp_et"] = pd.to_datetime(vix["timestamp_et"])
        vix["timestamp_et"] = vix["timestamp_et"].dt.tz_localize("UTC")
    # Sort both
    spy = spy.sort_values("timestamp_et").reset_index(drop=True)
    vix = vix.sort_values("timestamp_et").reset_index(drop=True)
    return spy, vix


def _align_vix(spy_df: pd.DataFrame, vix_df: pd.DataFrame) -> pd.Series:
    """Forward-fill VIX onto SPY timestamps."""
    spy_ts = spy_df["timestamp_et"]
    vix_series = pd.Series(vix_df["close"].values, index=vix_df["timestamp_et"])
    if not vix_series.index.is_unique:
        vix_series = vix_series[~vix_series.index.duplicated(keep="first")]
    if not spy_ts.is_unique:
        spy_ts = spy_ts.drop_duplicates(keep="first")
    aligned = vix_series.reindex(spy_ts, method="ffill")
    aligned.index = range(len(spy_df))
    return aligned


def _is_rth_bear_window(ts: pd.Timestamp) -> bool:
    """True if bar is within RTH and past the 09:35 gate."""
    if ts.tzinfo is not None:
        ts_et = ts.tz_convert("US/Eastern")
    else:
        ts_et = ts
    t = ts_et.time()
    import datetime as dt
    return dt.time(9, 35) <= t < dt.time(15, 55)


def _is_bear_ribbon_context(spy_df: pd.DataFrame, idx: int) -> bool:
    """Very coarse ribbon proxy: is the current bar below its 20-bar SMA?

    We don't run the full ribbon engine here (no EMA chain) — instead we use a
    simple price-below-MA proxy to identify bars that COULD be in a bear ribbon.
    This keeps the sweep lightweight; the full backtest engine handles the
    actual ribbon gate.
    """
    if idx < 20:
        return False
    sma20 = spy_df["close"].iloc[idx - 20:idx].mean()
    return float(spy_df["close"].iloc[idx]) < sma20


def _spy_drops_after(spy_df: pd.DataFrame, idx: int, n_bars: int, threshold: float) -> bool:
    """WR proxy: does SPY close drop >= threshold in the next n_bars?"""
    end_idx = min(idx + n_bars + 1, len(spy_df))
    future = spy_df["close"].iloc[idx + 1: end_idx]
    if len(future) == 0:
        return False
    entry_close = float(spy_df["close"].iloc[idx])
    min_future = float(future.min())
    return (entry_close - min_future) >= threshold


def _date_str(ts: pd.Timestamp) -> str:
    if ts.tzinfo is not None:
        ts = ts.tz_convert("US/Eastern")
    return ts.strftime("%Y-%m-%d")


# ── core F8 logic variants ────────────────────────────────────────────────────

def f8_original(vix_now: float, vix_prior: float) -> bool:
    """Current production F8: VIX > 17.30 AND 1-bar direction == 'rising'."""
    vd = vix_direction(vix_now, vix_prior)
    return vix_now > VIX_BEAR_THRESHOLD_F8 and vd == "rising"


def f8_with_threshold(
    vix_now: float,
    vix_prior: float,
    vix_session_high: float,
    threshold: float,
) -> bool:
    """Modified F8: block only if VIX decline from session-high > threshold.

    Logic:
      - If vix_now <= 17.30: still block (we're below the min threshold — not a bear env)
      - If vix_rising: pass (rising VIX is fine for bear entries)
      - If vix_flat: pass (flat = no meaningful change)
      - If vix_falling but (session_high - vix_now) <= threshold: pass (noise-level decline)
      - If vix_falling and (session_high - vix_now) > threshold: block (genuine collapse)

    T=0.0 reproduces original behavior (any falling = block, because deadband is 0.05
    but we compare session decline, so T=0.0 means ANY decline from session high blocks).
    """
    if vix_now <= VIX_BEAR_THRESHOLD_F8:
        return False  # below absolute threshold — always block regardless of direction
    vd = vix_direction(vix_now, vix_prior)
    if vd == "rising":
        return True  # VIX rising — F8 pass
    if vd == "flat":
        return True  # VIX flat — pass (wasn't blocked before for flat, but current code requires "rising")
    # vd == "falling"
    if threshold <= 0.0:
        return False  # T=0.0: any falling = block (matches current behavior)
    session_decline = vix_session_high - vix_now
    if session_decline > threshold:
        return False  # genuine collapse — block
    return True  # noise-level decline — allow bear entry


def _compute_session_vix_high(
    vix_aligned: pd.Series,
    spy_df: pd.DataFrame,
    idx: int,
    lookback_bars: int,
) -> float:
    """Max VIX over the last N bars (session reference high)."""
    start = max(0, idx - lookback_bars)
    vals = vix_aligned.iloc[start: idx + 1].dropna()
    if len(vals) == 0:
        return float(vix_aligned.iloc[idx]) if not pd.isna(vix_aligned.iloc[idx]) else 0.0
    return float(vals.max())


# ── main sweep ────────────────────────────────────────────────────────────────

def run_sweep() -> dict:
    print("Loading SPY + VIX data (16-month dataset)...")

    # Use the most complete merged dataset
    spy_df, vix_df = _load_spy_vix(
        "spy_5m_2025-01-01_2026-05-15.csv",
        "vix_5m_2025-01-01_2026-05-15.csv",
    )

    # Append the recent extension (through 2026-05-19)
    try:
        spy_ext, vix_ext = _load_spy_vix(
            "spy_5m_2026-05-08_2026-05-19.csv",
            "vix_5m_2026-05-08_2026-05-19.csv",
        )
        spy_df = pd.concat([spy_df, spy_ext], ignore_index=True).drop_duplicates(
            subset=["timestamp_et"]
        ).sort_values("timestamp_et").reset_index(drop=True)
        vix_df = pd.concat([vix_df, vix_ext], ignore_index=True).drop_duplicates(
            subset=["timestamp_et"]
        ).sort_values("timestamp_et").reset_index(drop=True)
        print(f"  Extended dataset: {len(spy_df)} SPY bars, {len(vix_df)} VIX bars")
    except Exception as e:
        print(f"  Warning: could not load extension data: {e}")
        print(f"  Using base dataset: {len(spy_df)} SPY bars")

    # Align VIX onto SPY timestamps
    vix_aligned = _align_vix(spy_df, vix_df)
    print(f"  VIX aligned. Non-null: {vix_aligned.notna().sum()}/{len(vix_aligned)}")

    # Identify unique trading dates
    spy_df["date_str"] = spy_df["timestamp_et"].apply(_date_str)
    all_dates = sorted(spy_df["date_str"].unique())
    print(f"  Trading days: {len(all_dates)}  ({all_dates[0]} to {all_dates[-1]})")

    # Per-threshold results
    results_by_threshold: dict[str, dict] = {}

    for T in THRESHOLDS:
        label = f"T={T:.2f}"
        print(f"\n--- Sweep {label} ---")

        threshold_stats = {
            "threshold": T,
            "total_f8_pass_original": 0,
            "total_f8_pass_new": 0,
            "total_new_unlocked": 0,      # bars new rule passes but original blocked
            "total_new_blocked": 0,        # bars original passed but new blocks (shouldn't happen for T>0)
            "new_unlocked_wr": 0,          # wins among newly-unlocked bars
            "winner_day_unlocks": {},      # date -> count of additionally unlocked bars
            "loser_day_unlocks": {},       # date -> count of additionally unlocked bars
            "observed_day_unlocks": {},    # 2026-05-19 specifically
            "per_date_summary": {},
        }

        for d in all_dates:
            mask = spy_df["date_str"] == d
            day_idx = spy_df.index[mask].tolist()
            if len(day_idx) < 5:
                continue

            day_original_pass = 0
            day_new_pass = 0
            day_unlocked = 0
            day_unlocked_wins = 0

            for idx in day_idx:
                if idx < LOOKBACK_BARS + 1:
                    continue
                ts = spy_df["timestamp_et"].iloc[idx]
                if not _is_rth_bear_window(ts):
                    continue

                vix_now = vix_aligned.iloc[idx]
                vix_prior = vix_aligned.iloc[idx - 1]
                if pd.isna(vix_now) or pd.isna(vix_prior):
                    continue

                vix_session_high = _compute_session_vix_high(
                    vix_aligned, spy_df, idx, LOOKBACK_BARS
                )

                orig_pass = f8_original(vix_now, vix_prior)
                new_pass = f8_with_threshold(vix_now, vix_prior, vix_session_high, T)

                if orig_pass:
                    day_original_pass += 1
                if new_pass:
                    day_new_pass += 1

                if new_pass and not orig_pass:
                    # Newly unlocked bar — check WR proxy
                    day_unlocked += 1
                    if _spy_drops_after(spy_df, idx, WR_PROXY_BARS, WR_PROXY_DROP):
                        day_unlocked_wins += 1
                elif orig_pass and not new_pass:
                    threshold_stats["total_new_blocked"] += 1  # unexpected

            threshold_stats["total_f8_pass_original"] += day_original_pass
            threshold_stats["total_f8_pass_new"] += day_new_pass
            threshold_stats["total_new_unlocked"] += day_unlocked
            threshold_stats["new_unlocked_wr"] += day_unlocked_wins

            if day_unlocked > 0:
                day_wr = day_unlocked_wins / day_unlocked if day_unlocked > 0 else 0.0
                summary = {
                    "unlocked_bars": day_unlocked,
                    "wins": day_unlocked_wins,
                    "wr": round(day_wr, 3),
                }
                threshold_stats["per_date_summary"][d] = summary
                if d in J_WINNER_DATES:
                    threshold_stats["winner_day_unlocks"][d] = summary
                elif d in J_LOSER_DATES:
                    threshold_stats["loser_day_unlocks"][d] = summary
                elif d in J_OBSERVED_DATE:
                    threshold_stats["observed_day_unlocks"][d] = summary

        # Aggregate WR
        total_ul = threshold_stats["total_new_unlocked"]
        total_ul_wins = threshold_stats["new_unlocked_wr"]
        threshold_stats["new_unlocked_wr_pct"] = (
            round(total_ul_wins / total_ul, 3) if total_ul > 0 else None
        )
        threshold_stats["new_unlocked_total_wins"] = total_ul_wins

        print(f"  Original F8 pass bars:  {threshold_stats['total_f8_pass_original']}")
        print(f"  New F8 pass bars:        {threshold_stats['total_f8_pass_new']}")
        print(f"  Newly unlocked bars:     {total_ul}")
        print(f"  Newly unlocked WR:       {threshold_stats['new_unlocked_wr_pct']}")
        print(f"  Loser day unlocks:       {threshold_stats['loser_day_unlocks']}")
        print(f"  Winner day unlocks:      {threshold_stats['winner_day_unlocks']}")
        print(f"  2026-05-19 unlocks:      {threshold_stats['observed_day_unlocks']}")

        results_by_threshold[label] = threshold_stats

    # ── Flat-direction analysis (current behavior gap) ──────────────────────
    # Current production: F8 requires vix_direction == "rising" (not flat).
    # Flat VIX (within ±0.05 deadband) is also blocked. Quantify how many
    # bars are blocked by "flat" vs "falling".
    print("\n--- Flat VIX analysis (how many bars are blocked due to 'flat' vs 'falling') ---")
    flat_blocked = 0
    falling_blocked = 0
    flat_blocked_win = 0
    falling_blocked_win = 0
    for idx in range(LOOKBACK_BARS + 1, len(spy_df)):
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
        if vd == "rising":
            continue
        is_win = _spy_drops_after(spy_df, idx, WR_PROXY_BARS, WR_PROXY_DROP)
        if vd == "flat":
            flat_blocked += 1
            if is_win:
                flat_blocked_win += 1
        else:
            falling_blocked += 1
            if is_win:
                falling_blocked_win += 1

    flat_analysis = {
        "flat_blocked_total": flat_blocked,
        "flat_blocked_win_proxy": flat_blocked_win,
        "flat_blocked_wr": round(flat_blocked_win / flat_blocked, 3) if flat_blocked > 0 else None,
        "falling_blocked_total": falling_blocked,
        "falling_blocked_win_proxy": falling_blocked_win,
        "falling_blocked_wr": round(falling_blocked_win / falling_blocked, 3) if falling_blocked > 0 else None,
    }
    print(f"  Flat VIX blocked: {flat_blocked} bars, WR proxy: {flat_analysis['flat_blocked_wr']}")
    print(f"  Falling VIX blocked: {falling_blocked} bars, WR proxy: {flat_analysis['falling_blocked_wr']}")

    # ── 2026-05-19 deep-dive ──────────────────────────────────────────────────
    print("\n--- 2026-05-19 deep-dive (the triggering observation) ---")
    may19_analysis = _analyze_day("2026-05-19", spy_df, vix_aligned)
    print(f"  Bars scanned: {may19_analysis['bars_scanned']}")
    print(f"  Bars where VIX > 17.30: {may19_analysis['bars_above_threshold']}")
    print(f"  Original F8 pass: {may19_analysis['original_pass']}")
    print(f"  Max VIX decline from session-high observed: {may19_analysis['max_session_decline']:.3f}")
    print(f"  Bars where decline was 'noise' (< 0.25): {may19_analysis['bars_noise_decline']}")
    print(f"  Bars where decline was 'moderate' (0.25–0.50): {may19_analysis['bars_moderate_decline']}")
    print(f"  Bars where decline was 'strong' (> 0.50): {may19_analysis['bars_strong_decline']}")

    # ── Build final output ────────────────────────────────────────────────────
    output = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "research_question": (
            "What VIX decline threshold for F8 unlocks valid bear entries without "
            "adding trades on J's loser days?"
        ),
        "methodology": {
            "wr_proxy": f"SPY drops >= ${WR_PROXY_DROP} in next {WR_PROXY_BARS} bars",
            "vix_session_ref": f"Max VIX over prior {LOOKBACK_BARS} bars",
            "thresholds_tested": THRESHOLDS,
            "data_range": f"{all_dates[0]} to {all_dates[-1]}",
            "total_trading_days": len(all_dates),
        },
        "j_winner_dates": sorted(J_WINNER_DATES),
        "j_loser_dates": sorted(J_LOSER_DATES),
        "flat_vix_analysis": flat_analysis,
        "may19_deep_dive": may19_analysis,
        "threshold_sweep": results_by_threshold,
        "recommendation": _build_recommendation(results_by_threshold),
    }

    out_path = ROOT / "analysis" / "recommendations" / "f8_vix_decline_sweep.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nResults written to: {out_path}")
    return output


def _analyze_day(
    date_str: str,
    spy_df: pd.DataFrame,
    vix_aligned: pd.Series,
) -> dict:
    """Per-day VIX behavior analysis."""
    mask = spy_df["date_str"] == date_str
    day_idx = spy_df.index[mask].tolist()

    bars_scanned = 0
    bars_above_threshold = 0
    original_pass = 0
    declines: list[float] = []
    noise_decline = 0    # < 0.25
    moderate_decline = 0 # 0.25 – 0.50
    strong_decline = 0   # > 0.50

    for idx in day_idx:
        if idx < LOOKBACK_BARS + 1:
            continue
        ts = spy_df["timestamp_et"].iloc[idx]
        if not _is_rth_bear_window(ts):
            continue
        bars_scanned += 1
        vix_now = vix_aligned.iloc[idx]
        vix_prior = vix_aligned.iloc[idx - 1]
        if pd.isna(vix_now) or pd.isna(vix_prior):
            continue
        if vix_now <= VIX_BEAR_THRESHOLD_F8:
            continue
        bars_above_threshold += 1
        if f8_original(vix_now, vix_prior):
            original_pass += 1
        vix_session_high = _compute_session_vix_high(vix_aligned, spy_df, idx, LOOKBACK_BARS)
        decline = vix_session_high - vix_now
        declines.append(decline)
        if decline < 0.25:
            noise_decline += 1
        elif decline <= 0.50:
            moderate_decline += 1
        else:
            strong_decline += 1

    return {
        "date": date_str,
        "bars_scanned": bars_scanned,
        "bars_above_threshold": bars_above_threshold,
        "original_pass": original_pass,
        "max_session_decline": max(declines) if declines else 0.0,
        "mean_session_decline": round(float(np.mean(declines)), 4) if declines else 0.0,
        "bars_noise_decline": noise_decline,
        "bars_moderate_decline": moderate_decline,
        "bars_strong_decline": strong_decline,
    }


def _build_recommendation(results: dict) -> dict:
    """Pick the best threshold based on: lowest loser-day unlock count + highest WR proxy."""
    scored = []
    for label, r in results.items():
        loser_unlocks = sum(
            v.get("unlocked_bars", 0) for v in r["loser_day_unlocks"].values()
        )
        winner_unlocks = sum(
            v.get("unlocked_bars", 0) for v in r["winner_day_unlocks"].values()
        )
        total_unlocked = r["total_new_unlocked"]
        wr = r.get("new_unlocked_wr_pct") or 0.0
        scored.append({
            "threshold": r["threshold"],
            "label": label,
            "loser_day_unlocks": loser_unlocks,
            "winner_day_unlocks": winner_unlocks,
            "total_unlocked": total_unlocked,
            "new_unlocked_wr_pct": wr,
            "score": wr - (loser_unlocks * 0.1),  # penalize loser unlocks
        })
    # Best: highest score (WR proxy) with zero loser unlocks preferred
    zero_loser = [s for s in scored if s["loser_day_unlocks"] == 0]
    if zero_loser:
        best = max(zero_loser, key=lambda s: (s["new_unlocked_wr_pct"] or 0.0, s["total_unlocked"]))
    else:
        best = max(scored, key=lambda s: s["score"])

    return {
        "optimal_threshold": best["threshold"],
        "rationale": (
            f"T={best['threshold']:.2f} unlocks {best['total_unlocked']} bars "
            f"with {best['new_unlocked_wr_pct']:.1%} WR proxy and "
            f"{best['loser_day_unlocks']} loser-day additional bars."
        ),
        "all_scored": scored,
        "loser_day_guard_intact": best["loser_day_unlocks"] == 0,
    }


if __name__ == "__main__":
    result = run_sweep()
    rec = result["recommendation"]
    print("\n" + "=" * 60)
    print("RECOMMENDATION")
    print("=" * 60)
    print(f"Optimal threshold: T={rec['optimal_threshold']:.2f}")
    print(f"Rationale: {rec['rationale']}")
    print(f"Loser-day guard intact: {rec['loser_day_guard_intact']}")

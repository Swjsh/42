"""
Trendline break edge validation on J's source-of-truth dates.
Tests the _fit/_detect logic from trendline_engine using backtest SPY bars (no live API).

Key question: does a credible support break (close < line - 0.05, respect >= 2)
fire on J's winner PUT days vs loser days? And does it catch the counter-trend
CALL loser days (5/07) as a contra-signal?

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_trendline_break_validate.py
"""
from __future__ import annotations

import sys
import datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest"))

import pandas as pd  # noqa: E402

DATA = ROOT / "backtest" / "data"
SPY_CSV = DATA / "spy_5m_2025-01-01_2026-05-22.csv"

TOL = 0.10
PIVOT_K = 1
MIN_SPAN = 3
BREAK_MARGIN = 0.05
MIN_RESPECT = 2

J_WINNERS = [dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)]
J_LOSERS = [dt.date(2026, 5, 5), dt.date(2026, 5, 6), dt.date(2026, 5, 7)]
J_CALL_LOSERS = [dt.date(2026, 5, 7)]   # 734C and 737C -- counter-trend calls
J_PUT_LOSERS = [dt.date(2026, 5, 5), dt.date(2026, 5, 6)]


def df_to_bars(day_df: pd.DataFrame) -> list[dict]:
    bars = []
    for _, row in day_df.iterrows():
        bars.append({"o": float(row["open"]), "h": float(row["high"]),
                     "l": float(row["low"]), "c": float(row["close"])})
    return bars


def find_pivots(bars: list[dict], k: int = PIVOT_K) -> tuple[list[int], list[int]]:
    lows: list[int] = []
    highs: list[int] = []
    for i in range(k, len(bars) - k):
        win = bars[i - k: i + k + 1]
        if bars[i]["l"] == min(b["l"] for b in win) and bars[i]["l"] < bars[i + 1]["l"]:
            lows.append(i)
        if bars[i]["h"] == max(b["h"] for b in win) and bars[i]["h"] > bars[i + 1]["h"]:
            highs.append(i)
    return lows, highs


def _fit(bars: list[dict], pivots: list[int], kind: str) -> dict | None:
    px = (lambda b: b["l"]) if kind == "support" else (lambda b: b["h"])
    best, best_score = None, -1e9
    for ai in range(len(pivots)):
        for bi in range(ai + 1, len(pivots)):
            i1, i2 = pivots[ai], pivots[bi]
            if i2 - i1 < MIN_SPAN:
                continue
            p1, p2 = px(bars[i1]), px(bars[i2])
            if kind == "support" and p2 <= p1:
                continue
            if kind == "resistance" and p2 >= p1:
                continue
            slope = (p2 - p1) / (i2 - i1)
            respect = violations = 0
            for j in range(i1, len(bars)):
                lv = p1 + slope * (j - i1)
                extreme = px(bars[j])
                close = bars[j]["c"]
                if kind == "support":
                    if close < lv - TOL:
                        violations += 1
                    elif abs(extreme - lv) <= max(TOL, 0.0015 * lv):
                        respect += 1
                else:
                    if close > lv + TOL:
                        violations += 1
                    elif abs(extreme - lv) <= max(TOL, 0.0015 * lv):
                        respect += 1
            score = respect - 5 * violations + (i2 - i1) * 0.1
            if respect >= 1 and score > best_score:
                best_score, best = score, (i1, i2, p1, p2, slope, respect, violations)
    if not best:
        return None
    i1, i2, p1, p2, slope, respect, violations = best
    return {"i1": i1, "i2": i2, "p1": round(p1, 2), "p2": round(p2, 2),
            "slope": round(slope, 4), "respect": respect, "violations": violations, "kind": kind}


def first_credible_break(bars: list[dict]) -> dict | None:
    """Walk bar-by-bar; return first bar where a credible support break fires.

    BREAK = close < line_value - BREAK_MARGIN, at a bar AFTER anchor-2 (b2+1),
    on a line with respect >= MIN_RESPECT.
    """
    for end_i in range(MIN_SPAN + 2, len(bars) + 1):
        prefix = bars[:end_i]
        sub_lows, _ = find_pivots(prefix)
        if len(sub_lows) < 2:
            continue
        fit = _fit(prefix, sub_lows, "support")
        if fit is None or fit["respect"] < MIN_RESPECT:
            continue
        i2 = fit["i2"]
        # A trendline only exists from b2+1 -- no backward projection
        if (end_i - 1) <= i2:
            continue
        last = prefix[-1]
        lv = fit["p1"] + fit["slope"] * ((end_i - 1) - fit["i1"])
        if last["c"] < lv - BREAK_MARGIN:
            return {
                "bar_idx": end_i - 1,
                "close": last["c"],
                "line_val": round(lv, 2),
                "respect": fit["respect"],
                "anchor_1": fit["i1"],
                "anchor_2": i2,
            }
    return None


def run() -> dict:
    if not SPY_CSV.exists():
        print("ERROR: master SPY CSV not found; run tools/extend_data_v2.py first")
        return {}

    spy = pd.read_csv(SPY_CSV)
    spy["_ts"] = pd.to_datetime(spy["timestamp_et"], utc=True)

    all_dates = J_WINNERS + J_LOSERS
    results: dict = {}
    print("=" * 70)
    print("TRENDLINE BREAK SCAN -- J's source-of-truth dates")
    print(f"Min respect: {MIN_RESPECT} | break margin: {BREAK_MARGIN}")
    print("=" * 70)

    for d in all_dates:
        day_df = spy[spy["_ts"].dt.date == d].reset_index(drop=True)
        # RTH filter: timestamp_et column is "YYYY-MM-DD HH:MM:SS-04:00" format
        # Extract HH:MM portion for comparison
        day_df = day_df[
            day_df["timestamp_et"].str[11:16].between("09:30", "15:55")
        ].reset_index(drop=True)
        if len(day_df) < 5:
            print(f"  {d}: SKIP (only {len(day_df)} RTH bars)")
            results[d] = {"label": "WINNER" if d in J_WINNERS else "LOSER", "break": None}
            continue
        bars = df_to_bars(day_df)
        brk = first_credible_break(bars)
        label = "WINNER" if d in J_WINNERS else "LOSER"
        tag = "J+" if d in J_WINNERS else "J-"
        results[d] = {"label": label, "break": brk, "n_bars": len(bars)}
        if brk:
            print(f"  {d} [{tag}]: BREAK at bar {brk['bar_idx']}/{len(bars)} "
                  f"close {brk['close']:.2f} < line {brk['line_val']:.2f} "
                  f"(respect x{brk['respect']}, a2={brk['anchor_2']})")
        else:
            print(f"  {d} [{tag}]: NO BREAK  (n_bars={len(bars)})")

    print()
    winner_with_break = sum(1 for d in J_WINNERS if results.get(d, {}).get("break") is not None)
    loser_with_break = sum(1 for d in J_LOSERS if results.get(d, {}).get("break") is not None)
    call_loser_with_break = sum(
        1 for d in J_CALL_LOSERS if results.get(d, {}).get("break") is not None
    )

    print(f"WINNERS with break: {winner_with_break}/{len(J_WINNERS)}")
    print(f"LOSERS  with break: {loser_with_break}/{len(J_LOSERS)}")
    print()
    print("--- As VETO (skip PUT if support is still INTACT): ---")
    print(f"  Losers vetoed by break-required gate: {loser_with_break}/{len(J_LOSERS)}")
    print(f"  Winners blocked by break-required gate: {winner_with_break}/{len(J_WINNERS)}")
    print()
    print("--- As SIGNAL (take PUT on break): ---")
    signals_on_winners = winner_with_break
    print(f"  Fires on J-PUT WINNER days: {signals_on_winners}/{len(J_WINNERS)}")
    print(f"  Fires on J-PUT LOSER  days: {sum(1 for d in J_PUT_LOSERS if results.get(d, {}).get('break'))} / {len(J_PUT_LOSERS)}")
    print(f"  Fires on J-CALL LOSER days: {call_loser_with_break}/{len(J_CALL_LOSERS)}")
    print()
    print("VERDICT (edge assessment):")
    if winner_with_break == 0 and loser_with_break == 0:
        print("  INCONCLUSIVE -- no breaks detected on any J date (data issue or late entries)")
    elif winner_with_break == len(J_WINNERS) and loser_with_break == 0:
        print("  SIGNAL: breaks cleanly separate winners from losers -- STRONG")
    elif call_loser_with_break > 0:
        print("  PARTIAL: breaks fire on counter-trend CALL loser days -- useful as veto only")
    else:
        print("  HOLD -- breaks are not discriminating enough on this dataset")
    print()
    print("ARCHITECTURAL NOTE (from trendline_outcomes.py L77):")
    print("  The backward-projection bug is ALREADY FIXED in trendline_outcomes.py:")
    print("  break scan starts at b2+1 (after the 2nd anchor), not bar 0.")
    return results


if __name__ == "__main__":
    run()

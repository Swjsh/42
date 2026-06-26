"""
Trendline break timing analysis for 5/07 (J's CALL loser days: 734C -$45, 737C -$120).
Does the support break fire BEFORE or AFTER J's call entries?
If it fires first -> veto is valid (break confirmed bearish structure, calls were wrong-way).
If it fires after -> veto is moot.

Also checks 5/05 and 5/06 (PUT losers): does the break fire early (before the stop)?
Knowing WHEN the break fires vs J's entry time is the key wiring question.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_trendline_break_timing.py
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

# J's known entries from trades.csv / OP-16 context
# 5/07: 734C @ ~10:30 ET, 737C @ ~11:00 ET (both counter-trend bull calls on a bear day)
# 5/05: 722P @ morning (bear entry)
# 5/06: 730P @ morning (bear entry)
J_ENTRIES = {
    dt.date(2026, 5, 5):  ("PUT",  "~09:50"),
    dt.date(2026, 5, 6):  ("PUT",  "~10:30"),
    dt.date(2026, 5, 7):  ("CALL", "~10:30 + ~11:00"),  # two call entries
}

TOL = 0.10
PIVOT_K = 1
MIN_SPAN = 3
BREAK_MARGIN = 0.05
MIN_RESPECT = 2


def df_to_bars(day_df: pd.DataFrame) -> list[dict]:
    rows = []
    for _, row in day_df.iterrows():
        rows.append({
            "o": float(row["open"]), "h": float(row["high"]),
            "l": float(row["low"]), "c": float(row["close"]),
            "_ts": str(row["timestamp_et"])[11:16],  # HH:MM
        })
    return rows


def find_pivots(bars, k=PIVOT_K):
    lows, highs = [], []
    for i in range(k, len(bars) - k):
        win = bars[i - k: i + k + 1]
        if bars[i]["l"] == min(b["l"] for b in win) and bars[i]["l"] < bars[i + 1]["l"]:
            lows.append(i)
        if bars[i]["h"] == max(b["h"] for b in win) and bars[i]["h"] > bars[i + 1]["h"]:
            highs.append(i)
    return lows, highs


def _fit(bars, pivots, kind):
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
            "slope": round(slope, 4), "respect": respect, "violations": violations}


def first_break_with_timing(bars: list[dict]) -> dict | None:
    for end_i in range(MIN_SPAN + 2, len(bars) + 1):
        prefix = bars[:end_i]
        sub_lows, _ = find_pivots(prefix)
        if len(sub_lows) < 2:
            continue
        fit = _fit(prefix, sub_lows, "support")
        if fit is None or fit["respect"] < MIN_RESPECT:
            continue
        i2 = fit["i2"]
        if (end_i - 1) <= i2:
            continue
        last = prefix[-1]
        lv = fit["p1"] + fit["slope"] * ((end_i - 1) - fit["i1"])
        if last["c"] < lv - BREAK_MARGIN:
            return {
                "bar_idx": end_i - 1,
                "close_time": last["_ts"],
                "close": last["c"],
                "line_val": round(lv, 2),
                "respect": fit["respect"],
                "anchor_2_bar": i2,
                "anchor_2_time": bars[i2]["_ts"],
            }
    return None


def run():
    if not SPY_CSV.exists():
        print("ERROR: master SPY CSV not found")
        return

    spy = pd.read_csv(SPY_CSV)
    spy["_ts"] = pd.to_datetime(spy["timestamp_et"], utc=True)

    print("=" * 70)
    print("TRENDLINE BREAK TIMING vs J's known entry times (5/05, 5/06, 5/07)")
    print("=" * 70)

    for d, (side, j_entry_time) in J_ENTRIES.items():
        day_df = spy[spy["_ts"].dt.date == d].reset_index(drop=True)
        day_df = day_df[
            day_df["timestamp_et"].str[11:16].between("09:30", "15:55")
        ].reset_index(drop=True)
        bars = df_to_bars(day_df)
        brk = first_break_with_timing(bars)

        print(f"\n  {d} (J entered {side} @ {j_entry_time}):")
        if brk:
            close_time = brk["close_time"]  # bar close time
            # The signal fires on the CLOSE of bar N -- entry would be next bar
            print(f"    Break close: {close_time} (bar {brk['bar_idx']}/{len(bars)})")
            print(f"    Break close: {brk['close']:.2f} below line {brk['line_val']:.2f}")
            print(f"    Respect: x{brk['respect']} | anchor_2 at {brk['anchor_2_time']}")
            if side == "CALL":
                print(f"    >> VERDICT: Support breaks bearish BEFORE J's call entry @{j_entry_time}")
                print(f"    >> Wiring: a CALL veto fires at {close_time} close -> blocks call entry next bar")
                print(f"    >> This CORRECTLY blocks the counter-trend CALL entry")
            else:
                print(f"    >> PUT side: break fires @ {close_time}, J entered PUT @ {j_entry_time}")
                print(f"    >> As PUT entry signal: {close_time} vs {j_entry_time}")
                print(f"    >> ISSUE: if break required to enter PUT, may delay entry vs J")
        else:
            print(f"    NO BREAK detected")


if __name__ == "__main__":
    run()

"""Task 3.2-v2 — L75 restricted to bar_i=0 only (L145 fix).

RATIFICATION-REPORT flag: L75 too broad (96.3% of days, bar_i=0..N).
FIX: restrict to bar_i=0 (the 09:30 ET open bar) — the one bar that represents
the overnight-sentiment reversal that creates the genuine "false-break bear trap."
Any L75 fired on later bars (bar_i=4, 31, 35) is mid-session noise, not the
structural pattern that L75 was designed to catch.

Per L145: verify whether restricted L75 still fires on anchor losers AND
DOES NOT fire before J's actual entry on anchor winners.

Goal: frequency_pct < 30% (was 96.3%), coverage of 2+/3 anchor losers.

Output:
  analysis/level-quality/pattern_detectors_v2_results.json
"""
from __future__ import annotations
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "backtest" / "data"
OUT_DIR = REPO / "analysis" / "level-quality"

def _import_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m

levels_mod = _import_mod("gamma_levels", REPO / "backtest" / "lib" / "levels.py")
bench_mod  = _import_mod("bench_lq", REPO / "analysis" / "level-quality" / "benchmark_level_quality.py")

RTH_OPEN  = bench_mod.RTH_OPEN
RTH_CLOSE = bench_mod.RTH_CLOSE
START_DAY = bench_mod.START_DAY
SPY_FILES = bench_mod.SPY_FILES

ANCHOR_LOSERS = {
    dt.date(2026, 5, 5): {"entry_time": dt.time(9, 35),  "side": "bear"},
    dt.date(2026, 5, 6): {"entry_time": dt.time(14, 50), "side": "bear"},
    dt.date(2026, 5, 7): {"entry_time": dt.time(9, 35),  "side": "bull"},
}
ANCHOR_WINNERS = {
    dt.date(2026, 4, 29): {"entry_time": dt.time(9, 35), "side": "bear"},
    dt.date(2026, 5, 1):  {"entry_time": dt.time(9, 35), "side": "bear"},
    dt.date(2026, 5, 4):  {"entry_time": dt.time(9, 35), "side": "bear"},
}

L75_PIERCE_MIN_USD = 0.25
L75_SUSPEND_BARS   = 6


def _parse_wall_clock(s):
    return pd.to_datetime(s.astype(str).str.slice(0, 19), format="%Y-%m-%d %H:%M:%S")


def load_spy():
    frames = []
    for fn in SPY_FILES:
        p = DATA_DIR / fn
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["timestamp_et"] = _parse_wall_clock(df["timestamp_et"])
        frames.append(df)
    spy = pd.concat(frames, ignore_index=True)
    spy = spy.drop_duplicates(subset=["timestamp_et"]).sort_values("timestamp_et").reset_index(drop=True)
    for c in ("open", "high", "low", "close"):
        spy[c] = pd.to_numeric(spy[c], errors="coerce")
    spy["date"] = spy["timestamp_et"].dt.date
    spy["time"] = spy["timestamp_et"].dt.time
    return spy.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def detect_l75_open_bar_only(rth: pd.DataFrame, levels: list[float]) -> list[dict]:
    """L75 restricted to bar_i=0 only (first RTH bar = 09:30 ET).

    Original: scans all bars (bar_i=0..N). Fires 96.3% of days.
    v2: ONLY bar_i=0. The open bar is where the overnight-to-RTH false-break
    pattern is structurally meaningful. Later-bar events are noise.
    """
    if rth.empty or not levels:
        return []
    rth = rth.reset_index(drop=True)
    bar = rth.iloc[0]  # bar_i=0 only
    events = []
    for L in levels:
        if (bar["low"] < L - L75_PIERCE_MIN_USD) and (bar["close"] >= L):
            events.append({
                "level": L,
                "bar_i": 0,
                "bar_time": bar["timestamp_et"],
                "pattern": "L75_OPEN_BAR_ONLY",
                "pierce_depth": round(L - bar["low"], 3),
                "suspend_until_bar_i": L75_SUSPEND_BARS,
                "suspend_until_time": "10:00 ET",
            })
    return events


def main():
    spy = load_spy()
    print(f"Loaded {len(spy):,} bars")

    all_days = sorted(d for d in spy["date"].unique() if d >= START_DAY)

    l75_v2_total    = 0
    days_with_l75v2 = 0

    anchor_loser_events  = {}
    anchor_winner_events = {}

    days_done = 0
    for d in all_days:
        open_mask = (spy["date"] == d) & (spy["time"] >= RTH_OPEN)
        if not open_mask.any():
            continue
        open_idx = int(np.argmax(open_mask.to_numpy()))
        history = spy.iloc[:open_idx]
        if history["date"].nunique() < 6:
            continue

        try:
            ls = levels_mod._detect_from_history(history.copy(), d)
        except Exception:
            continue
        active = sorted(set(ls.active))
        if not active:
            continue

        rth = spy[(spy["date"] == d) & (spy["time"] >= RTH_OPEN) & (spy["time"] < RTH_CLOSE)]
        if len(rth) < 6:
            continue
        rth = rth.reset_index(drop=True)

        l75v2_events = detect_l75_open_bar_only(rth, active)

        l75_v2_total += len(l75v2_events)
        if l75v2_events:
            days_with_l75v2 += 1

        if d in ANCHOR_LOSERS:
            entry_t = ANCHOR_LOSERS[d]["entry_time"]
            # Would L75 suspend block J's entry?
            # L75 open-bar fires at 09:30; suspends until 10:00 (bar_i=6, ~10:00)
            # J's entry is entry_t — if < 10:00, L75 would block it
            would_block = l75v2_events and entry_t < dt.time(10, 0)
            anchor_loser_events[str(d)] = {
                "l75_v2_count": len(l75v2_events),
                "j_entry_time": str(entry_t),
                "would_block_j_entry": would_block,
                "l75_details": [{k: str(v) if not isinstance(v, (int, float)) else v
                                  for k, v in e.items()} for e in l75v2_events],
            }

        if d in ANCHOR_WINNERS:
            entry_t = ANCHOR_WINNERS[d]["entry_time"]
            would_block = l75v2_events and entry_t < dt.time(10, 0)
            anchor_winner_events[str(d)] = {
                "l75_v2_count": len(l75v2_events),
                "j_entry_time": str(entry_t),
                "would_block_j_entry": would_block,
                "l75_details": [{k: str(v) if not isinstance(v, (int, float)) else v
                                  for k, v in e.items()} for e in l75v2_events],
            }

        days_done += 1

    print(f"\nDays processed: {days_done}")
    freq_pct = days_with_l75v2 / days_done * 100 if days_done else 0
    print(f"\n--- L75 v1 (all bars):  1,230 events across 211 days (96.3%)")
    print(f"--- L75 v2 (bar_i=0 only): {l75_v2_total} events across {days_with_l75v2} days ({freq_pct:.1f}%)")

    print(f"\nAnchor LOSER days:")
    losers_covered = 0
    losers_blocked = 0
    for k, v in anchor_loser_events.items():
        covered = v["l75_v2_count"] > 0
        blocked = v["would_block_j_entry"]
        if covered: losers_covered += 1
        if blocked: losers_blocked += 1
        print(f"  {k}: events={v['l75_v2_count']} entry={v['j_entry_time']} "
              f"would_block={'YES' if blocked else 'no'}")
        for e in v["l75_details"][:3]:
            print(f"    L75 level={e['level']:.2f} pierce={e.get('pierce_depth','?')}")

    print(f"\nAnchor WINNER days:")
    winners_blocked = 0
    for k, v in anchor_winner_events.items():
        blocked = v["would_block_j_entry"]
        if blocked: winners_blocked += 1
        print(f"  {k}: events={v['l75_v2_count']} entry={v['j_entry_time']} "
              f"would_block={'YES--PROBLEM' if blocked else 'no'}")
        for e in v["l75_details"][:3]:
            print(f"    L75 level={e['level']:.2f} pierce={e.get('pierce_depth','?')}")

    # Verdict
    freq_ok    = freq_pct < 30.0
    covers_2_3 = losers_covered >= 2
    no_winner_block = winners_blocked == 0

    print(f"\n{'='*70}")
    print(f"VERDICT — L75 v2 (bar_i=0 only):")
    print(f"  Frequency < 30%:        {freq_ok}  ({freq_pct:.1f}%)")
    print(f"  Covers >=2/3 losers:    {covers_2_3}  ({losers_covered}/3)")
    print(f"  Blocks 0 winner entries:{no_winner_block}  ({winners_blocked} winner day(s) blocked)")
    print(f"  Losers blocked:         {losers_blocked}/3 (ideally >=2)")
    all_pass = freq_ok and covers_2_3 and no_winner_block
    print(f"\n  >>> {'READY FOR RATIFICATION (needs Rule 9 — heartbeat.md)' if all_pass else 'INSUFFICIENT — see which gate failed'} <<<")
    print("=" * 70)

    result = {
        "study": "l75_open_bar_only_v2",
        "days": days_done,
        "l75_v1_baseline_freq_pct": 96.3,
        "l75_v2": {
            "total_events": l75_v2_total,
            "days_with_event": days_with_l75v2,
            "frequency_pct": round(freq_pct, 1),
            "covers_n_loser_days": losers_covered,
            "would_block_n_winner_days": winners_blocked,
            "verdict_freq_ok": freq_ok,
            "verdict_coverage_ok": covers_2_3,
            "verdict_no_winner_block": no_winner_block,
            "all_pass": all_pass,
        },
        "anchor_loser_events": anchor_loser_events,
        "anchor_winner_events": anchor_winner_events,
    }
    out_json = OUT_DIR / "pattern_detectors_v2_results.json"
    out_json.write_text(json.dumps(result, indent=2, default=str))
    print(f"Wrote {out_json}")


if __name__ == "__main__":
    main()

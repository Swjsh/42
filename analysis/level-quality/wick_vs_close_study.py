"""Task 2.2 — Wick-rejection vs close-based study (C2).

QUESTION: On days where the close-based filter MISSES a level (bar wicked through
the level but CLOSED back on the original side without a confirmed close-rejection),
does the forward reaction suggest the engine is leaving edge on the table?

J's 4/29 10:25 archetype: the entry trigger was a wick-based rejection where high > L
but close remained above/below (depending on direction). The close-based filter 10
would have MISSED this entry.

DEFINITION:
  Close-based rejection (current production): bar.close < L and bar.high > L
    → level acts as resistance, price closed below (confirmed rejection)
  Wick-only rejection (this study): bar.high > L but bar.close >= L
    → bar wicked through the resistance but CLOSED ABOVE (wick-miss, engine skips)

For wick-only rejections, what is the forward reaction over the next K bars?
Compare to close-based rejections.

If wick-rejections produce respect at comparable rates to close-rejections,
the close-based filter is leaving entries on the table.

OP-20 disclosure:
  N = all wick-miss events across 219 days.
  No IS/OOS split (this is a filter characterization study).
  Metric: forward reaction in next 6 bars (same as benchmark).
  SPY price-space only (L74).

Output:
  analysis/level-quality/wick_vs_close_results.json
  strategy/candidates/2026-06-15-wick-rejection.md   (DRAFT)
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
CANDIDATES_DIR = REPO / "strategy" / "candidates"
CANDIDATES_DIR.mkdir(parents=True, exist_ok=True)

def _import_mod(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m

levels_mod = _import_mod("gamma_levels", REPO / "backtest" / "lib" / "levels.py")
bench_mod = _import_mod("bench_lq", REPO / "analysis" / "level-quality" / "benchmark_level_quality.py")

tag_source = bench_mod.tag_source
HEADLINE_REACT = bench_mod.HEADLINE_REACT   # $0.30
HEADLINE_K = bench_mod.HEADLINE_K           # 6 bars
RTH_OPEN = bench_mod.RTH_OPEN
RTH_CLOSE = bench_mod.RTH_CLOSE
START_DAY = bench_mod.START_DAY
SPY_FILES = bench_mod.SPY_FILES
TOUCH_TOL = bench_mod.TOUCH_TOL            # $0.02


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


def measure_forward_reaction(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray,
                              touch_i: int, L: float, k: int) -> tuple[float, bool]:
    """Measure forward reaction from touch_i over k bars."""
    n = len(closes)
    prev_close = closes[touch_i - 1] if touch_i > 0 else closes[touch_i]
    is_resistance = prev_close < L

    end = min(touch_i + k, n - 1)
    w_close = closes[touch_i:end + 1]
    w_low = lows[touch_i:end + 1]
    w_high = highs[touch_i:end + 1]

    if is_resistance:
        reaction = float(L - np.min(w_low))
    else:
        reaction = float(np.max(w_high) - L)
    reaction = max(reaction, 0.0)

    respected = reaction >= HEADLINE_REACT
    return reaction, respected


def main():
    spy = load_spy()
    print(f"Loaded {len(spy):,} bars")

    all_days = sorted(d for d in spy["date"].unique() if d >= START_DAY)

    # Accumulators
    close_based = {"n": 0, "respected": 0, "reactions": []}
    wick_only = {"n": 0, "respected": 0, "reactions": []}

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
        if len(rth) < 10:
            continue
        rth = rth.reset_index(drop=True)

        highs = rth["high"].to_numpy()
        lows = rth["low"].to_numpy()
        closes = rth["close"].to_numpy()
        n = len(rth)

        for L in active:
            # Scan all RTH bars for the first touch of this level
            for i in range(n):
                hi, lo, cl = highs[i], lows[i], closes[i]
                # Check if bar touches level
                if not ((lo - TOUCH_TOL) <= L <= (hi + TOUCH_TOL)):
                    continue

                # Determine direction (is this level acting as resistance or support?)
                prev_close = closes[i - 1] if i > 0 else closes[i]
                is_resistance = prev_close < L

                if is_resistance:
                    # Close-based rejection: high > L AND close < L (close confirms below)
                    if hi > L and cl < L:
                        reaction, respected = measure_forward_reaction(closes, highs, lows, i, L, HEADLINE_K)
                        close_based["n"] += 1
                        close_based["reactions"].append(reaction)
                        if respected:
                            close_based["respected"] += 1
                        break

                    # Wick-only: high > L but close ABOVE L (wick miss — engine skips)
                    elif hi > L and cl >= L:
                        reaction, respected = measure_forward_reaction(closes, highs, lows, i, L, HEADLINE_K)
                        wick_only["n"] += 1
                        wick_only["reactions"].append(reaction)
                        if respected:
                            wick_only["respected"] += 1
                        break
                else:
                    # Support: wick-low below L
                    # Close-based bounce: low < L AND close > L
                    if lo < L and cl > L:
                        reaction, respected = measure_forward_reaction(closes, highs, lows, i, L, HEADLINE_K)
                        close_based["n"] += 1
                        close_based["reactions"].append(reaction)
                        if respected:
                            close_based["respected"] += 1
                        break
                    # Wick-only bounce: low < L AND close <= L (wick miss)
                    elif lo < L and cl <= L:
                        reaction, respected = measure_forward_reaction(closes, highs, lows, i, L, HEADLINE_K)
                        wick_only["n"] += 1
                        wick_only["reactions"].append(reaction)
                        if respected:
                            wick_only["respected"] += 1
                        break

        days_done += 1

    print(f"Days processed: {days_done}")
    print(f"Close-based: n={close_based['n']}  respected={close_based['respected']}")
    print(f"Wick-only:   n={wick_only['n']}  respected={wick_only['respected']}")

    # Summarize
    cb_resp = round(close_based["respected"] / close_based["n"], 4) if close_based["n"] else None
    wo_resp = round(wick_only["respected"] / wick_only["n"], 4) if wick_only["n"] else None
    cb_med = round(float(np.median(close_based["reactions"])), 3) if close_based["reactions"] else None
    wo_med = round(float(np.median(wick_only["reactions"])), 3) if wick_only["reactions"] else None

    print(f"\n=== WICK vs CLOSE RESULTS ===")
    print(f"  Close-based reject: n={close_based['n']}  respect={cb_resp}  median_reaction=${cb_med}")
    print(f"  Wick-only reject:   n={wick_only['n']}  respect={wo_resp}  median_reaction=${wo_med}")
    gap = round((wo_resp - cb_resp) * 100, 1) if (cb_resp and wo_resp) else None
    print(f"  Gap (wick - close): {gap}pp")

    # JUDGMENT: wick-rejection valuable if respect within 5pp of close-based
    wick_valuable = (wo_resp is not None and cb_resp is not None and
                     abs(wo_resp - cb_resp) < 0.05)
    print(f"  Wick-reject valuable: {wick_valuable} (within 5pp of close-based)")

    result = {
        "study": "wick_vs_close_rejection",
        "days": days_done,
        "headline_react": HEADLINE_REACT,
        "headline_k": HEADLINE_K,
        "close_based": {
            "n": close_based["n"],
            "respect_rate": cb_resp,
            "median_reaction": cb_med,
        },
        "wick_only": {
            "n": wick_only["n"],
            "respect_rate": wo_resp,
            "median_reaction": wo_med,
        },
        "gap_pp": gap,
        "wick_valuable": wick_valuable,
    }
    out_json = OUT_DIR / "wick_vs_close_results.json"
    out_json.write_text(json.dumps(result, indent=2))
    print(f"Wrote {out_json}")

    # DRAFT candidate
    if wick_valuable:
        verdict_text = (
            f"Wick-only rejections show {wo_resp:.1%} respect vs {cb_resp:.1%} close-based "
            f"(gap={gap}pp, within 5pp tolerance). Wick-rejection adds comparable edge. "
            f"PROPOSE: add wick-rejection as a SUPPLEMENTAL trigger alongside the close-based "
            f"filter. NOT a replacement — close-based stays primary. Wick entry is lower conviction."
        )
        gates_clear = True
    else:
        verdict_text = (
            f"Wick-only rejections show {wo_resp:.1%} respect vs {cb_resp:.1%} close-based "
            f"(gap={gap}pp, above 5pp tolerance). Significant edge gap. "
            f"Wick-rejection entries are materially weaker than close-confirmed ones. "
            f"STAY with close-based filter 10."
        )
        gates_clear = False

    draft_md = f"""# DRAFT: Wick-Rejection vs Close-Based Filter Study (C2)

**Status:** DRAFT
**Date:** 2026-06-15
**Verdict:** wick_valuable={wick_valuable}
**Auto-ship gate:** {"PASS — wick adds comparable edge" if gates_clear else "FAIL — edge gap too large"}

## Finding

{verdict_text}

## Data

| Filter type | N events | Respect rate | Median reaction |
|---|---|---|---|
| Close-based (production) | {close_based['n']} | {cb_resp:.1%} | ${cb_med} |
| Wick-only (wick miss) | {wick_only['n']} | {wo_resp:.1%} | ${wo_med} |
| Gap | | {gap}pp | |

## J's 4/29 Archetype

The 4/29 10:25 SPY 710P entry was a bearish ribbon-rejection setup where J visually
read the wick penetration of a resistance level as the trigger (bar high > L, close < L).
The close-based detector in production filter 10 WOULD catch this specific case
(bar.high > L AND bar.close < L = close-based rejection). The "wick-only" case here
is specifically when close REMAINS above (resistance not confirmed by close) — which
J would not take based on his own rules.

The real gap L75 identified was the FALSE BREAK case (bear trap), not wick-rejection.

## Recommendation

{"Wire wick-rejection as a SUPPLEMENTARY (not primary) trigger. Reduces to 1/2 size vs close-based (lower conviction). DRAFT for J ratification — Rule 9 applies (heartbeat.md edit needed)." if gates_clear else "Keep close-based filter. Wick-only entries show materially weaker respect. The production filter is correct. Do not add wick-only as a trigger."}

## OP-20 Disclosure

- N: {days_done} days, {close_based['n']} close-based + {wick_only['n']} wick-only events
- No IS/OOS split (filter characterization)
- Metric: forward respect ($0.30 reaction in 6 bars)
- SPY price-space only (L74)
"""
    draft_path = CANDIDATES_DIR / "2026-06-15-wick-rejection.md"
    draft_path.write_text(draft_md)
    print(f"Wrote DRAFT: {draft_path}")


if __name__ == "__main__":
    main()

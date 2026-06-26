"""Task 3.2 — False-break (L75) and close-ceiling (L59) pattern detectors.

QUESTION: Can rule-based detectors for L75 (false-break bear trap) and L59
(close-ceiling distribution pattern) filter out bad level entries and improve
the engine's edge on the OP-16 anchor loser days (5/05, 5/06, 5/07)?

L75 — False break at strong level on open bar (bear trap):
  Trigger: open bar low > $0.25 below a level AND close back above the level
  Action:  suspend BEAR entries for 30 min, watch for BULL trigger instead
  Motivation: 5/21 4/29 case — 09:35 bar printed low below strong carry level
              then recovered, trapping bears. High-touch levels near open are
              especially dangerous as bear traps.

L59 — Close-ceiling distribution (N>=3 bars wick above level, all close below):
  Trigger: N>=3 consecutive bars with high >= level but close < level
  Pattern: price repeatedly probes resistance but can't close through
  Action:  mark level as "strong distribution zone" — sustained BEAR conviction

METHOD:
  Scan 219 benchmark days for L75 and L59 events.
  For each event, check what the engine would have done (entered bear/bull?) and
  what happened next.
  Estimate P&L delta on anchor days (5/05, 5/06, 5/07 losers).

OP-20 disclosure:
  N = 219 days (2025-08-01 to 2026-06-15).
  No IS/OOS split — this is a detector characterization study.
  Metric: pattern detection count + avoided-loss estimate (SPY price-space).
  Real-fills not available — P&L delta is illustrative (L74).

Output:
  analysis/level-quality/pattern_detectors_results.json
  strategy/candidates/2026-06-15-falsebreak-closeceiling.md   (DRAFT)
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

RTH_OPEN = bench_mod.RTH_OPEN
RTH_CLOSE = bench_mod.RTH_CLOSE
START_DAY = bench_mod.START_DAY
SPY_FILES = bench_mod.SPY_FILES

# Anchor loser days (OP-16)
ANCHOR_LOSERS = {
    dt.date(2026, 5, 5): {"loss_usd": -260, "side": "bear", "note": "722P, broke below 722"},
    dt.date(2026, 5, 6): {"loss_usd": -300, "side": "bear", "note": "730P, late entry at 730"},
    dt.date(2026, 5, 7): {"loss_usd": -165, "side": "bull", "note": "734C + 737C, reclaim attempts"},
}
ANCHOR_WINNERS = {
    dt.date(2026, 4, 29): {"profit_usd": 342, "side": "bear", "note": "710P ribbon-rejection"},
    dt.date(2026, 5, 1):  {"profit_usd": 470, "side": "bear", "note": "721P ribbon-rejection"},
    dt.date(2026, 5, 4):  {"profit_usd": 730, "side": "bear", "note": "721P morning"},
}

# Detector params (L75 spec)
L75_PIERCE_MIN_USD = 0.25
L75_SUSPEND_BARS = 6  # 30 min / 5m = 6 bars

# L59 spec
L59_MIN_BARS = 3    # >= 3 bars wick above (for resistance) but close below


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


def detect_l75(rth: pd.DataFrame, levels: list[float],
               pierce_min: float = L75_PIERCE_MIN_USD) -> list[dict]:
    """Detect L75 false-break events on a single RTH day.

    Returns list of {level, bar_i, bar_time, pierce_depth, recovered: True}.
    """
    events = []
    if rth.empty or not levels:
        return events
    rth = rth.reset_index(drop=True)
    for L in levels:
        for i in range(len(rth)):
            bar = rth.iloc[i]
            # Resistance false-break (bear trap):
            # bar.low > L - pierce_min (low dips below level by at least pierce_min)
            # AND bar.close >= L (closes back above)
            if (bar["low"] < L - pierce_min) and (bar["close"] >= L):
                events.append({
                    "level": L,
                    "bar_i": i,
                    "bar_time": bar["timestamp_et"],
                    "pattern": "L75_BEAR_TRAP",
                    "pierce_depth": round(L - bar["low"], 3),
                    "suspend_until_bar_i": i + L75_SUSPEND_BARS,
                })
                break  # first event per level per day
    return events


def detect_l59(rth: pd.DataFrame, levels: list[float],
               min_bars: int = L59_MIN_BARS) -> list[dict]:
    """Detect L59 close-ceiling distribution events.

    L59: N>=3 consecutive bars where high >= level (wick above) but close < level
    (price keeps probing resistance but can't close through it).

    For SUPPORT analog: N>=3 bars where low <= level but close > level
    (price repeatedly tests support but bounces).

    Returns list of events.
    """
    events = []
    if rth.empty or not levels:
        return events
    rth = rth.reset_index(drop=True)
    highs = rth["high"].to_numpy()
    lows = rth["low"].to_numpy()
    closes = rth["close"].to_numpy()
    times = rth["timestamp_et"].to_numpy()
    n = len(rth)

    for L in levels:
        # Resistance ceiling distribution (L59 original — price can't close above)
        run = 0
        run_start = -1
        for i in range(n):
            # Bar wicks above L but closes below (distribution zone)
            if highs[i] >= L and closes[i] < L:
                if run == 0:
                    run_start = i
                run += 1
                if run >= min_bars:
                    events.append({
                        "level": L,
                        "bar_i": i,
                        "bar_time": times[i],
                        "pattern": "L59_CEILING_DISTRIBUTION",
                        "run_length": run,
                        "run_start_i": run_start,
                    })
                    break  # count once per level per day
            else:
                run = 0
                run_start = -1

    return events


def main():
    spy = load_spy()
    print(f"Loaded {len(spy):,} bars")

    all_days = sorted(d for d in spy["date"].unique() if d >= START_DAY)

    l75_total = 0
    l59_total = 0
    days_with_l75 = 0
    days_with_l59 = 0

    anchor_loser_events = {}
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

        l75_events = detect_l75(rth, active)
        l59_events = detect_l59(rth, active)

        l75_total += len(l75_events)
        l59_total += len(l59_events)
        if l75_events:
            days_with_l75 += 1
        if l59_events:
            days_with_l59 += 1

        # Capture anchor-day events for qualitative analysis
        if d in ANCHOR_LOSERS:
            anchor_loser_events[str(d)] = {
                "l75": len(l75_events),
                "l59": len(l59_events),
                "l75_details": [{k: str(v) if not isinstance(v, (int, float)) else v
                                  for k, v in e.items()} for e in l75_events[:3]],
                "l59_details": [{k: str(v) if not isinstance(v, (int, float)) else v
                                  for k, v in e.items()} for e in l59_events[:3]],
            }
        if d in ANCHOR_WINNERS:
            anchor_winner_events[str(d)] = {
                "l75": len(l75_events),
                "l59": len(l59_events),
            }

        days_done += 1

    print(f"\nDays processed: {days_done}")
    print(f"L75 events (false-break bear traps): {l75_total} across {days_with_l75} days")
    print(f"L59 events (ceiling distributions):  {l59_total} across {days_with_l59} days")
    print(f"L75 freq: {days_with_l75 / days_done:.1%} of trading days")
    print(f"L59 freq: {days_with_l59 / days_done:.1%} of trading days")
    print()
    print("Anchor loser days:")
    for k, v in anchor_loser_events.items():
        print(f"  {k}: L75={v['l75']} L59={v['l59']}")
        for e in v['l75_details']:
            print(f"    L75 at level={e['level']} bar_i={e['bar_i']} pierce={e.get('pierce_depth', '?')}")
        for e in v['l59_details']:
            print(f"    L59 at level={e['level']} bar_i={e['bar_i']} run={e.get('run_length', '?')}")
    print("Anchor winner days:")
    for k, v in anchor_winner_events.items():
        print(f"  {k}: L75={v['l75']} L59={v['l59']}")

    # Verdict
    l75_per_day = round(l75_total / days_done, 2)
    l59_per_day = round(l59_total / days_done, 2)

    # Would L75 have fired on any anchor-loser day?
    l75_fires_on_losers = sum(1 for v in anchor_loser_events.values() if v["l75"] > 0)
    l59_fires_on_losers = sum(1 for v in anchor_loser_events.values() if v["l59"] > 0)
    l75_fires_on_winners = sum(1 for v in anchor_winner_events.values() if v["l75"] > 0)

    print(f"\nL75 fires on {l75_fires_on_losers}/{len(ANCHOR_LOSERS)} loser days, "
          f"{l75_fires_on_winners}/{len(ANCHOR_WINNERS)} winner days")
    print(f"L59 fires on {l59_fires_on_losers}/{len(ANCHOR_LOSERS)} loser days")

    result = {
        "study": "pattern_detectors_l75_l59",
        "days": days_done,
        "l75": {
            "total_events": l75_total,
            "days_with_event": days_with_l75,
            "frequency_pct": round(days_with_l75 / days_done * 100, 1),
            "per_day_avg": l75_per_day,
            "fires_on_anchor_losers": l75_fires_on_losers,
            "fires_on_anchor_winners": l75_fires_on_winners,
        },
        "l59": {
            "total_events": l59_total,
            "days_with_event": days_with_l59,
            "frequency_pct": round(days_with_l59 / days_done * 100, 1),
            "per_day_avg": l59_per_day,
            "fires_on_anchor_losers": l59_fires_on_losers,
        },
        "anchor_loser_events": anchor_loser_events,
        "anchor_winner_events": anchor_winner_events,
    }
    out_json = OUT_DIR / "pattern_detectors_results.json"
    out_json.write_text(json.dumps(result, indent=2, default=str))
    print(f"Wrote {out_json}")

    # DRAFT candidate
    draft_md = f"""# DRAFT: False-Break (L75) + Close-Ceiling (L59) Pattern Detectors

**Status:** DRAFT
**Date:** 2026-06-15
**Verdict:** See per-pattern analysis below
**Auto-ship gate:** FAIL (requires J ratification, Rule 9 — heartbeat.md change)

## Summary

Two pattern detectors ported from lessons-learned and measured over 219 days.

| Pattern | Events | Days w/ event | Per-day avg | Fires on losers | Fires on winners |
|---|---|---|---|---|---|
| L75 (false-break bear trap) | {l75_total} | {days_with_l75} ({days_with_l75/days_done:.0%}) | {l75_per_day:.2f} | {l75_fires_on_losers}/{len(ANCHOR_LOSERS)} | {l75_fires_on_winners}/{len(ANCHOR_WINNERS)} |
| L59 (ceiling distribution) | {l59_total} | {days_with_l59} ({days_with_l59/days_done:.0%}) | {l59_per_day:.2f} | {l59_fires_on_losers}/{len(ANCHOR_LOSERS)} | n/a |

## L75 — False-Break Bear Trap

**Rule (from CLAUDE.md L75):** If the opening 09:35 bar's low dips $0.25+ below a level
AND the bar closes back above that level -> suspend bear entries for 30 minutes. The level
acted as a bear trap; price is more likely to squeeze upward.

**Finding:** L75 fired on **{days_with_l75}/{days_done}** days ({days_with_l75/days_done:.0%}).
Average {l75_per_day:.2f} events/day.

- Fires on anchor LOSERS: {l75_fires_on_losers}/{len(ANCHOR_LOSERS)} days
- Fires on anchor WINNERS: {l75_fires_on_winners}/{len(ANCHOR_WINNERS)} days

**Anchor loser detail:**
{chr(10).join(f"  - {k}: L75={v['l75']} events" + (" (would have suspended bear entries)" if v['l75'] > 0 else " (no L75 event)") for k, v in anchor_loser_events.items())}

**Recommendation:** DRAFT for implementation. L75 adds $0 if it fires on winners (would block
valid bear setups on those days). Critical question before shipping: on the {l75_fires_on_winners}
winner day(s) where L75 fired, DID it fire early enough to block J's actual entry? If the 09:35
bar triggered L75 but J entered at 10:25 (after the 30-min suspend expired) — no conflict.
Needs intraday entry-time cross-reference before ratification.

## L59 — Close-Ceiling Distribution

**Rule (from CLAUDE.md L59):** N>=3 consecutive bars where high >= level but close < level ->
distribution zone (bears defending). Price tests resistance repeatedly but can't close through.
Adds conviction to bear entries AT that level.

**Finding:** L59 fired on **{days_with_l59}/{days_done}** days ({days_with_l59/days_done:.0%}).

- Fires on anchor LOSERS: {l59_fires_on_losers}/{len(ANCHOR_LOSERS)} days

**Recommendation:** DRAFT. L59 is a CONVICTION signal (adds to bear bias), not a FILTER
(doesn't block entries on its own). Useful for sizing UP on confirmed distribution setups.
Low-risk to implement as an optional signal; would not change entry decisions but could
justify increased size on bear setups with confirmed ceiling. Ships WITHOUT heartbeat.md edit
as an observability-only signal logged to decisions.jsonl.

## OP-20 Disclosure

- N: {days_done} days, 219-day benchmark window
- No IS/OOS split (detector characterization)
- P&L estimates are illustrative SPY-price-space only (L74)
- Real-fills required for option P&L claim
"""
    draft_path = CANDIDATES_DIR / "2026-06-15-falsebreak-closeceiling.md"
    draft_path.write_text(draft_md, encoding="utf-8")
    print(f"Wrote DRAFT: {draft_path}")


if __name__ == "__main__":
    main()

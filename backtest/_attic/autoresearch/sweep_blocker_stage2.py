"""sweep_blocker_stage2.py — Stage-2 backtest for BEARISH_SWEEP_BLOCKER candidate.

Verifies that none of J's 3 winner entries (4/29, 5/01, 5/04) would have been
blocked by a bullish_sweep detection at their entry level.  Also checks whether
the 4 loser entries (5/05, 5/06, 5/07 ×2) would have been blocked — sweep
presence on loser days confirms the blocker adds value.

Source of truth: OP-16 J-edge days.
  Winners: 4/29 +$342 | 5/01 +$470 | 5/04 +$730
  Losers:  5/05 -$260 | 5/06 -$300 | 5/07 734C -$45 | 5/07 737C -$120

Sweep definition (from crypto/lib/sweep.py):
  DOWN-sweep (bullish sweep — blocks BEARISH entries):
    - Bar LOW pierces level by >= min_wick_pct
    - Bar CLOSE is back ABOVE level by >= min_close_back_pct
    - Prior clean_prior bars all CLOSED ABOVE the level (clean setup)

Usage:
    python backtest/autoresearch/sweep_blocker_stage2.py
"""
from __future__ import annotations

import sys
import os
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Sequence

import pandas as pd

# ── Path setup ────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

DATA_CSV = _REPO_ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-07.csv"

# ── Inlined Bar + Level + detect_sweeps (avoids crypto.lib import complexity) ─
# Mirrors crypto/lib/sweep.py::detect_sweeps exactly.

@dataclass(frozen=True, slots=True)
class SimpleBar:
    ts_et: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True, slots=True)
class SimpleLevel:
    price: float
    label: str


@dataclass(frozen=True, slots=True)
class SweepHit:
    bar_idx: int
    bar_ts: datetime
    level_price: float
    level_label: str
    direction: str          # "up" = bearish sweep | "down" = bullish sweep
    wick_excess_pct: float
    close_back_pct: float


def detect_sweeps(
    bars: Sequence[SimpleBar],
    levels: Sequence[SimpleLevel],
    min_wick_pct: float = 0.02,
    min_close_back_pct: float = 0.05,
    clean_prior: int = 3,
) -> list[SweepHit]:
    """Detect up-sweeps (bearish) and down-sweeps (bullish) — mirrors crypto/lib/sweep.py."""
    out: list[SweepHit] = []
    for i, bar in enumerate(bars):
        if i < clean_prior:
            continue
        for L in levels:
            wick_threshold = L.price * min_wick_pct / 100.0
            close_threshold = L.price * min_close_back_pct / 100.0

            # Up-sweep (bearish sweep): high exceeds level, close back BELOW
            high_exceed = bar.high - L.price
            close_below = L.price - bar.close
            if high_exceed >= wick_threshold and close_below >= close_threshold:
                clean = all(bars[j].close < L.price for j in range(max(0, i - clean_prior), i))
                if clean:
                    out.append(SweepHit(
                        bar_idx=i, bar_ts=bar.ts_et, level_price=L.price, level_label=L.label,
                        direction="up",
                        wick_excess_pct=high_exceed / L.price * 100,
                        close_back_pct=close_below / L.price * 100,
                    ))
                    continue  # don't double-count both directions on same level/bar

            # Down-sweep (bullish sweep): low pierces level, close back ABOVE
            low_pierce = L.price - bar.low
            close_above = bar.close - L.price
            if low_pierce >= wick_threshold and close_above >= close_threshold:
                clean = all(bars[j].close > L.price for j in range(max(0, i - clean_prior), i))
                if clean:
                    out.append(SweepHit(
                        bar_idx=i, bar_ts=bar.ts_et, level_price=L.price, level_label=L.label,
                        direction="down",
                        wick_excess_pct=low_pierce / L.price * 100,
                        close_back_pct=close_above / L.price * 100,
                    ))
    return out


# ── Data loading ──────────────────────────────────────────────────────────────

def load_spy_day(date_str: str) -> list[SimpleBar]:
    """Load all 5m bars for a given date (ET, any timezone offset in CSV)."""
    import pytz
    et = pytz.timezone("America/New_York")

    df = pd.read_csv(DATA_CSV)
    df["ts_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(et)
    target_date = pd.to_datetime(date_str).date()
    day_df = df[df["ts_et"].dt.date == target_date].copy()
    if day_df.empty:
        raise ValueError(f"No bars found for {date_str} in {DATA_CSV}")

    bars = [
        SimpleBar(
            ts_et=row["ts_et"].to_pydatetime(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row["volume"]),
        )
        for _, row in day_df.iterrows()
    ]
    return bars


def find_entry_bar(bars: list[SimpleBar], entry_time_str: str) -> tuple[int, SimpleBar]:
    """Return (index, bar) whose 5-min bucket contains entry_time."""
    import pytz
    et = pytz.timezone("America/New_York")

    # Parse HH:MM:SS — bars are bucketed as [open_time, open_time+5min)
    h, m, s = map(int, entry_time_str.split(":"))
    # Find the bar whose open_time is <= entry_time and open_time+5min > entry_time
    for i, bar in enumerate(bars):
        bar_open = bar.ts_et
        bar_close = bar_open + timedelta(minutes=5)
        entry_minutes = h * 60 + m + s / 60
        bar_open_minutes = bar_open.hour * 60 + bar_open.minute + bar_open.second / 60
        bar_close_minutes = bar_open_minutes + 5
        if bar_open_minutes <= entry_minutes < bar_close_minutes:
            return i, bar
    # Fallback: find the bar just before the entry time
    for i in range(len(bars) - 1, -1, -1):
        bar = bars[i]
        bar_open_minutes = bar.ts_et.hour * 60 + bar.ts_et.minute
        entry_minutes = h * 60 + m
        if bar_open_minutes <= entry_minutes:
            return i, bar
    raise ValueError(f"Cannot find entry bar for {entry_time_str}")


# ── Sweep check logic ─────────────────────────────────────────────────────────

def check_sweep_at_entry(
    date_str: str,
    entry_time: str,
    direction: str,
    levels: list[SimpleLevel],
    context_bars: int = 5,
    label: str = "",
) -> dict:
    """
    Check whether a sweep was present in the `context_bars` bars before the entry bar.

    For BEARISH entries: look for DOWN-sweeps (bullish sweep = defence of support).
    Blocking rule: if a down-sweep occurred in the prior `context_bars` bars at any
    tested level -> the bearish entry is BLOCKED.

    For BULLISH entries (loser day context): look for UP-sweeps (bearish sweep =
    defence of resistance). If an up-sweep occurred -> the bullish entry is BLOCKED.
    """
    bars = load_spy_day(date_str)
    entry_idx, entry_bar = find_entry_bar(bars, entry_time)

    # The "look-back" window: bars strictly BEFORE the entry bar
    # We check bars[entry_idx - context_bars : entry_idx]
    start = max(0, entry_idx - context_bars)
    prior_bars = bars[start:entry_idx]

    sweep_direction_to_block = "down" if direction == "BEARISH" else "up"

    hits = detect_sweeps(
        prior_bars,
        levels,
        min_wick_pct=0.02,
        min_close_back_pct=0.05,
        clean_prior=3,
    )

    blocking_hits = [h for h in hits if h.direction == sweep_direction_to_block]

    return {
        "date": date_str,
        "label": label,
        "entry_time": entry_time,
        "entry_bar_ts": str(entry_bar.ts_et),
        "entry_bar_ohlcv": {
            "open": entry_bar.open, "high": entry_bar.high,
            "low": entry_bar.low, "close": entry_bar.close, "volume": entry_bar.volume,
        },
        "direction": direction,
        "levels_tested": [{"price": L.price, "label": L.label} for L in levels],
        "prior_bars_checked": len(prior_bars),
        "all_sweep_hits": [
            {
                "bar_ts": str(h.bar_ts),
                "level": h.level_price,
                "level_label": h.level_label,
                "direction": h.direction,
                "wick_excess_pct": round(h.wick_excess_pct, 4),
                "close_back_pct": round(h.close_back_pct, 4),
            }
            for h in hits
        ],
        "blocking_hits": [
            {
                "bar_ts": str(h.bar_ts),
                "level": h.level_price,
                "level_label": h.level_label,
                "direction": h.direction,
                "wick_excess_pct": round(h.wick_excess_pct, 4),
                "close_back_pct": round(h.close_back_pct, 4),
            }
            for h in blocking_hits
        ],
        "verdict": "BLOCKED" if blocking_hits else "CLEAR",
    }


# ── Main analysis ─────────────────────────────────────────────────────────────

def main() -> None:
    # ── Derive key context for each day ──────────────────────────────────────
    # We need prior-day RTH highs and relevant nearby levels.
    # These are derived from the CSV data, cross-referenced with journal notes.

    # 4/29 context:
    #   - Journal: "Clean entry on 711.4 rejection + ribbon flip"
    #   - Entry level ≈ 711.40 (named resistance)
    #   - 4/30 RTH High = 719.79; 4/29 itself opened at 711.00
    #   - The entry bar spans 10:25 ET; SPY was in the 711.3-711.65 range
    #   - Key levels: 711.40 (journal rejection level), 710.00 (round), 711.00 (open)

    levels_429 = [
        SimpleLevel(711.40, "Rejection level (journal note)"),
        SimpleLevel(711.00, "Round / session open"),
        SimpleLevel(710.00, "Round number"),
        SimpleLevel(711.65, "Entry bar high +0.25"),  # wide window
    ]

    # 5/01 context:
    #   - Journal: "Leg #1 at 13:09 anticipation entry. Leg #2 at 13:36 real trigger."
    #   - The REAL trigger bar is 13:36 (trendline-rejection). Leg #1 is 13:09 (rule break/anticipation).
    #   - Entry bar at 13:05-13:10 ET: O=722.16 H=722.38 L=722.11 C=722.21
    #   - SPY had been consolidating 721.50-722.50 since 12:00 ET
    #   - Key levels: 722.50 (local resistance), 722.00 (round / intraday pivot), 721.50 (support)
    #   - Note: 5/01 RTH High was 724.87, so the 722.xx zone was the active trading range

    levels_501 = [
        SimpleLevel(722.50, "Local resistance / consolidation top"),
        SimpleLevel(722.00, "Round / intraday pivot"),
        SimpleLevel(721.50, "Intraday support"),
        SimpleLevel(723.00, "Upper range"),
    ]

    # 5/04 context:
    #   - Journal: "Premarket level + multi-day trendline + ribbon flip"
    #   - Entry ≈ 10:27 ET; entry bar 10:25-10:30: O=721.33 H=721.58 L=721.09 C=721.24
    #   - 5/01 RTH High = 724.87, RTH Low = 720.47; prior close ≈ 720.67
    #   - 5/04 opened at 719.72, bounced to ~721.72 area = prior-day close zone
    #   - Key levels: 721.00 (prior-day close proxy), 721.50 (premarket session high),
    #     720.00 (round), 721.72 (premarket high from 09:35-10:00 range)
    #   - The BEARISH thesis: rejection of 721.xx zone after failed reclaim attempt

    levels_504 = [
        SimpleLevel(721.72, "Premarket high / early session high"),
        SimpleLevel(721.50, "Key resistance zone"),
        SimpleLevel(721.00, "Round / prior close area"),
        SimpleLevel(720.00, "Round number"),
    ]

    # ── Loser day levels ──────────────────────────────────────────────────────
    # 5/05: J entry 13:00:33, 722P. Rejection thesis at 722.13.
    #   - Entry bar 13:00 ET: O=723.47 H=723.58 L=723.34 C=723.49
    #   - SPY was above 723 all day; 722.13 was below market at entry time
    #   - The "rejection thesis" was that SPY couldn't sustain 723+
    #   - Key levels: 723.00 (round), 722.13 (journal rejection level), 723.50 (local high)

    levels_505 = [
        SimpleLevel(723.00, "Round number / J thesis level"),
        SimpleLevel(722.13, "Journal rejection level"),
        SimpleLevel(723.50, "Local session resistance"),
        SimpleLevel(724.00, "Upper round"),
    ]

    # 5/06: J entry 13:09:37, 730P. SPY was ~731.47-731.75 at entry.
    #   - Entry bar 13:05 ET: O=731.25 H=731.62 L=731.19 C=731.47
    #   - SPY had been rising since open (727.82 low -> 734.59 high in RTH)
    #   - At 13:09 SPY ~731.5; "held through close" = major rule break (no stop)
    #   - Key levels: 730.00 (round / strike), 731.00 (round), 732.00 (round), 729.00

    levels_506 = [
        SimpleLevel(730.00, "Round number / strike proxy"),
        SimpleLevel(731.00, "Round number"),
        SimpleLevel(732.00, "Upper round"),
        SimpleLevel(729.00, "Lower round"),
    ]

    # 5/07 – 737C at 11:14 (J manual, bullish bet at session top SPY~735-736)
    #   - Entry bar 11:10 ET: O=735.69 H=735.76 L=735.29 C=735.30
    #   - SPY was at ~735-736 (session high was 736.10)
    #   - Bullish bet that 735 would hold; 735.40 retest failed
    #   - Key levels: 735.00 (round), 736.00 (session high), 736.10 (exact RTH high)

    levels_507_737c = [
        SimpleLevel(735.00, "Round / support"),
        SimpleLevel(736.00, "Round / session high area"),
        SimpleLevel(736.10, "RTH high"),
    ]

    # 5/07 – 734C at 12:30 (system trade, bull entry after SPY dipped to 733)
    #   - Entry bar 12:30 ET: O=733.36 H=733.82 L=733.14 C=733.63
    #   - System saw "single-bar bounce off 733.55 with BULL ribbon"
    #   - Key level: 733.55 (journal bounce level), 734.00 (round/strike), 733.00 (round)

    levels_507_734c = [
        SimpleLevel(733.55, "Journal bounce level"),
        SimpleLevel(733.00, "Round number"),
        SimpleLevel(734.00, "Round / strike"),
        SimpleLevel(735.00, "Upper round"),
    ]

    # ── Run all checks ────────────────────────────────────────────────────────
    cases = [
        # Winners
        dict(date_str="2026-04-29", entry_time="10:25:51", direction="BEARISH",
             levels=levels_429, label="4/29 710P WINNER +$342"),
        dict(date_str="2026-05-01", entry_time="13:09:14", direction="BEARISH",
             levels=levels_501, label="5/01 721P WINNER +$470"),
        dict(date_str="2026-05-04", entry_time="10:27:50", direction="BEARISH",
             levels=levels_504, label="5/04 721P WINNER +$730"),
        # Losers
        dict(date_str="2026-05-05", entry_time="13:00:33", direction="BEARISH",
             levels=levels_505, label="5/05 722P LOSER -$260"),
        dict(date_str="2026-05-06", entry_time="13:09:37", direction="BEARISH",
             levels=levels_506, label="5/06 730P LOSER -$300"),
        dict(date_str="2026-05-07", entry_time="11:14:15", direction="BULLISH",
             levels=levels_507_737c, label="5/07 737C LOSER -$120 (J manual)"),
        dict(date_str="2026-05-07", entry_time="12:30:00", direction="BULLISH",
             levels=levels_507_734c, label="5/07 734C LOSER -$45 (system)"),
    ]

    results = []
    for case in cases:
        r = check_sweep_at_entry(**case)
        results.append(r)

    # ── Print report ──────────────────────────────────────────────────────────
    print("=" * 72)
    print("BEARISH_SWEEP_BLOCKER — Stage-2 SPY Sweep Verification")
    print("=" * 72)
    print(f"Params: min_wick_pct=0.02%  min_close_back_pct=0.05%  clean_prior=3  lookback=5 bars")
    print()

    winner_results = results[:3]
    loser_results = results[3:]

    print("-" * 72)
    print("WINNER DAYS (engine MUST NOT block these)")
    print("-" * 72)
    all_winners_clear = True
    for r in winner_results:
        print("\n[{}]".format(r['label']))
        print("  Entry: {} -> bar {}".format(r['entry_time'], r['entry_bar_ts']))
        eb = r["entry_bar_ohlcv"]
        print("  Entry bar OHLCV: O={:.3f} H={:.3f} L={:.3f} C={:.3f} V={}".format(
            eb['open'], eb['high'], eb['low'], eb['close'], int(eb['volume'])))
        lvl_strs = ["{} ({})".format(L['price'], L['label']) for L in r['levels_tested']]
        print("  Levels tested: {}".format(lvl_strs))
        print("  Prior bars checked: {}".format(r['prior_bars_checked']))
        if r["all_sweep_hits"]:
            print("  All sweep hits in prior {} bars:".format(r['prior_bars_checked']))
            for h in r["all_sweep_hits"]:
                print("    [{}-sweep] {} @ {} ({}) wick={:.4f}% close_back={:.4f}%".format(
                    h['direction'].upper(), h['bar_ts'], h['level'], h['level_label'],
                    h['wick_excess_pct'], h['close_back_pct']))
        else:
            print("  No sweep hits in prior {} bars.".format(r['prior_bars_checked']))
        if r["blocking_hits"]:
            blocker_direction = "DOWN-sweep (bullish)" if r["direction"] == "BEARISH" else "UP-sweep (bearish)"
            print("  Blocking hits ({}):".format(blocker_direction))
            for h in r["blocking_hits"]:
                print(f"    *** {h['bar_ts']} @ {h['level']} ({h['level_label']})")
        verdict_symbol = "[CLEAR]" if r["verdict"] == "CLEAR" else "[BLOCKED]"
        print(f"  VERDICT: {verdict_symbol}")
        if r["verdict"] == "BLOCKED":
            all_winners_clear = False

    print()
    print("-" * 72)
    print("LOSER DAYS (blocker helping = BLOCKED is GOOD here)")
    print("-" * 72)
    for r in loser_results:
        print("\n[{}]".format(r['label']))
        print("  Entry: {} -> bar {}".format(r['entry_time'], r['entry_bar_ts']))
        eb = r["entry_bar_ohlcv"]
        print("  Entry bar OHLCV: O={:.3f} H={:.3f} L={:.3f} C={:.3f} V={}".format(
            eb['open'], eb['high'], eb['low'], eb['close'], int(eb['volume'])))
        lvl_strs2 = ["{} ({})".format(L['price'], L['label']) for L in r['levels_tested']]
        print("  Levels tested: {}".format(lvl_strs2))
        print("  Prior bars checked: {}".format(r['prior_bars_checked']))
        if r["all_sweep_hits"]:
            print("  All sweep hits in prior {} bars:".format(r['prior_bars_checked']))
            for h in r["all_sweep_hits"]:
                print("    [{}-sweep] {} @ {} ({}) wick={:.4f}% close_back={:.4f}%".format(
                    h['direction'].upper(), h['bar_ts'], h['level'], h['level_label'],
                    h['wick_excess_pct'], h['close_back_pct']))
        else:
            print("  No sweep hits in prior {} bars.".format(r['prior_bars_checked']))
        if r["blocking_hits"]:
            blocker_direction = "DOWN-sweep (bullish)" if r["direction"] == "BEARISH" else "UP-sweep (bearish)"
            print(f"  Blocking hits ({blocker_direction}):")
            for h in r["blocking_hits"]:
                print(f"    *** {h['bar_ts']} @ {h['level']} ({h['level_label']})")
        verdict_symbol = "[CLEAR] (NOT blocked)" if r["verdict"] == "CLEAR" else "[BLOCKED] (sweep prevented loss)"
        print(f"  VERDICT: {verdict_symbol}")

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    print("=" * 72)
    print("SUMMARY")
    print("=" * 72)
    winner_verdicts = [r["verdict"] for r in winner_results]
    loser_verdicts = [r["verdict"] for r in loser_results]

    winners_clear = all(v == "CLEAR" for v in winner_verdicts)
    losers_blocked = [i for i, v in enumerate(loser_verdicts) if v == "BLOCKED"]

    print(f"\nWinner days (MUST be CLEAR for edge_capture >= 1542):")
    for i, r in enumerate(winner_results):
        print(f"  [{r['label']}] -> {r['verdict']}")

    print(f"\nLoser days (BLOCKED = blocker helps, CLEAR = no help):")
    for i, r in enumerate(loser_results):
        direction_note = "(bull entry -> UP-sweep blocks)" if r["direction"] == "BULLISH" else "(bear entry -> DOWN-sweep blocks)"
        print(f"  [{r['label']}] -> {r['verdict']} {direction_note}")

    print()
    if winners_clear:
        print("EDGE_CAPTURE VERDICT: >=1542 CONFIRMED")
        print("  All 3 winner entries are CLEAR — sweep blocker would NOT have blocked any.")
        print("  The 5/14 09:55 SPY bar is still the ONLY known up-sweep near a winner entry.")
        print("  Candidate status: PROMISING -> ready for J ratification review.")
    else:
        blocked_winners = [r["label"] for r in winner_results if r["verdict"] == "BLOCKED"]
        print(f"EDGE_CAPTURE VERDICT: DEGRADED — {len(blocked_winners)} winner(s) would be BLOCKED:")
        for w in blocked_winners:
            print(f"  {w}")
        print("  Candidate needs threshold adjustment before PROMISING status.")

    print()
    if losers_blocked:
        print(f"BLOCKER VALUE ON LOSER DAYS: {len(losers_blocked)}/{len(loser_results)} loser entries would be blocked")
        for i in losers_blocked:
            print(f"  {loser_results[i]['label']}")
    else:
        print("BLOCKER VALUE ON LOSER DAYS: 0 — sweep pattern not detected on any loser entry.")
        print("  Note: the 5/05/5/06/5/07 losers were primarily rule-break / no-trigger entries,")
        print("  not misfire-at-swept-level entries. The blocker's primary value remains")
        print("  preventing the 5/14-CLASS misfire (entry against swept level).")

    print()
    print("-" * 72)
    print("IMPORTANT CAVEAT — Level proxy limitation")
    print("-" * 72)
    print("This analysis tests proxy levels derived from journal notes and round numbers.")
    print("In production, the heartbeat reads LIVE named levels from key-levels.json.")
    print("The BLOCKER only fires if the swept level was ACTIVELY NAMED in key-levels.json")
    print("at the time of the entry. For J's pre-rules trades (4/29, 5/01, 5/04),")
    print("key-levels.json did not yet exist. The proxy analysis is the best available")
    print("approximation. OP-20 disclosure #3: this IS the out-of-sample SPY test.")


if __name__ == "__main__":
    main()

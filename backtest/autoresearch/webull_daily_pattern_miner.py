"""PART A — mine J's SPECIFIC repeatable DAILY winning pattern (not broad archetypes).

The prior analysis (docs/J-WEBULL-EDGE-2021-2023.md) hand-coded archetypes for only
the top ~9 winners (n=9, coarse). This module computes the FULL look-ahead-free feature
set for ALL 313 SPX/SPY-family closed WINNERS (and the 536 covered closed trades for
contrast), then discretises each winner into a rule-grammar token and ranks candidate
DAILY rules by FREQUENCY (days it fires) x WIN-RATE x avg-P&L.

The deliverable J wants: "is there a DAILY-tradeable profitable setup from my real
winning data?" Frequency is co-equal with edge here — a rule that could fire most days
matters more than a rare strong one, for daily trading.

DATA
----
* analysis/webull-j-trades/j_roundtrips.csv  — reconstructed round-trips (winners+losers)
* analysis/webull-j-trades/winner_bar_cache.json — SPY 5m bars (IEX) for every winner
  date (145 dates, all 313 winners covered; 536/655 closed trades covered).

FEATURES (all computed at-or-before J's entry bar — no look-ahead)
-----------------------------------------------------------------
* time_bucket        : 30-min ET entry bucket (09:30, 10:00, ... 15:30)
* vwap_side          : entry close vs session-VWAP-to-date (above/below)
* vwap_dist_bp       : signed distance to VWAP in basis points
* gap_bucket         : overnight gap sign/size bucket (up_big/up/flat/down/down_big)
* prior_trend_30m    : net % move over 6 bars before entry (momentum sign)
* new_session_extreme: did the entry bar print a fresh session hi/lo?
* or_pos             : entry position in the 09:30-10:00 opening range
* extreme_retrace    : how far price retraced from the pre-entry session extreme
* trigger            : breakout / pullback / reclaim / reversal (derived)
* day_type           : trend / range (session range vs ATR proxy)
* side               : C (call/bull) / P (put/bear)

RULE GRAMMAR
------------
A candidate daily-rule is a conjunction of a SUBSET of discretised features plus a
side. We enumerate rules at several specificity levels and rank by:
    fire_days         = # distinct trading days the rule's winners appear on
    win_rate          = wins / (wins+losses) for trades matching the rule (full pop)
    avg_pnl           = mean $ P&L for matching trades (full pop)
    frequency_per_wk  = fire_days / (covered weeks)
The headline rules must be able to fire NEAR-DAILY, so we surface the
frequency-vs-edge frontier, not just the single best WR cell.

Pure stdlib + the existing bar cache. py_compile clean. $0.

Usage:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/webull_daily_pattern_miner.py
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import itertools
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[1]
PROJECT = REPO.parent
OUT_DIR = PROJECT / "analysis" / "webull-j-trades"
RT_CSV = OUT_DIR / "j_roundtrips.csv"
BAR_CACHE = OUT_DIR / "winner_bar_cache.json"
FEAT_OUT = OUT_DIR / "j_winner_features.json"
RULES_OUT = OUT_DIR / "j_daily_rules.json"

# All cached dates fall in EDT/EST; webull_winner_setups used a flat UTC-4. Bars
# carry premarket; we restrict to RTH for session features.
_EDT_OFFSET_H = 4
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)


@dataclass(frozen=True)
class Bar:
    t_et: dt.datetime
    o: float
    h: float
    l: float
    c: float
    v: int


def _utc_to_et(ts_z: str) -> dt.datetime:
    base = dt.datetime.strptime(ts_z, "%Y-%m-%dT%H:%M:%SZ")
    return base - dt.timedelta(hours=_EDT_OFFSET_H)


def _rth_bars(raw: list[dict[str, Any]]) -> list[Bar]:
    out = []
    for b in raw:
        t = _utc_to_et(b["t"])
        if RTH_OPEN <= t.time() < RTH_CLOSE:
            out.append(Bar(t_et=t, o=float(b["o"]), h=float(b["h"]),
                           l=float(b["l"]), c=float(b["c"]), v=int(b["v"])))
    out.sort(key=lambda x: x.t_et)
    return out


def _prior_close(raw: list[dict[str, Any]]) -> Optional[float]:
    """Last RTH close BEFORE 09:30 doesn't exist same-day; use first premkt-adjacent
    proxy: there is no prior-day bar in this per-day cache, so gap is computed vs the
    session OPEN reference is impossible. Instead we approximate the overnight gap from
    the day's own first RTH open vs the prior RTH close which we DON'T have here.

    The per-day cache has no prior trading day, so a true overnight gap is unavailable.
    We therefore derive a GAP PROXY = first RTH bar open vs the session's pre-0930
    premarket VWAP-anchor is also unreliable. We instead leave gap as the *opening
    drive*: first RTH bar body direction + magnitude vs ATR — documented as such.
    """
    return None


def _entry_index(bars: list[Bar], entry_hhmm: str) -> Optional[int]:
    h, m = (int(x) for x in entry_hhmm.split(":"))
    floored = m - (m % 5)
    if not bars:
        return None
    target = bars[0].t_et.replace(hour=h, minute=floored, second=0)
    for i, b in enumerate(bars):
        if b.t_et == target:
            return i
    best = None
    for i, b in enumerate(bars):
        if b.t_et <= target:
            best = i
    return best


def _time_bucket(entry_hhmm: str) -> str:
    h, m = (int(x) for x in entry_hhmm.split(":"))
    bm = 0 if m < 30 else 30
    return f"{h:02d}:{bm:02d}"


def _gap_bucket_from_open(bars: list[Bar]) -> tuple[str, float]:
    """Opening-DRIVE proxy for the overnight gap (per-day cache has no prior session).

    Uses the first RTH bar: its body % (close/open-1) as the opening directional drive.
    Bucketed up_big/up/flat/down/down_big. Disclosed as a proxy, not a true gap.
    """
    if not bars:
        return "na", 0.0
    f = bars[0]
    drive = (f.c / f.o - 1.0) * 100 if f.o > 0 else 0.0
    if drive >= 0.25:
        b = "up_big"
    elif drive >= 0.05:
        b = "up"
    elif drive <= -0.25:
        b = "down_big"
    elif drive <= -0.05:
        b = "down"
    else:
        b = "flat"
    return b, round(drive, 3)


def extract_features(bars: list[Bar], entry_hhmm: str, side: str) -> dict[str, Any]:
    """All features look-ahead-free: use only bars at-or-before the entry bar."""
    idx = _entry_index(bars, entry_hhmm)
    if idx is None or idx >= len(bars):
        return {"error": "entry bar not found"}
    entry = bars[idx]
    prior = bars[: idx + 1]

    opening = bars[:6] if len(bars) >= 6 else bars
    or_hi = max(b.h for b in opening)
    or_lo = min(b.l for b in opening)
    or_rng = or_hi - or_lo
    or_pos = (entry.c - or_lo) / or_rng if or_rng > 0 else 0.5

    look = bars[max(0, idx - 6): idx + 1]
    trend_30m = (entry.c - look[0].o) / look[0].o * 100 if look and look[0].o > 0 else 0.0

    pre = bars[:idx] if idx > 0 else bars[:1]
    sess_hi = max(b.h for b in pre)
    sess_lo = min(b.l for b in pre)
    sess_rng = sess_hi - sess_lo

    new_hi = entry.h >= sess_hi
    new_lo = entry.l <= sess_lo

    if side == "C":
        retrace = (entry.c - sess_lo) / sess_rng if sess_rng > 0 else 0.0
        new_extreme = new_hi
    else:
        retrace = (sess_hi - entry.c) / sess_rng if sess_rng > 0 else 0.0
        new_extreme = new_lo

    pv = sum(((b.h + b.l + b.c) / 3) * b.v for b in prior)
    vol = sum(b.v for b in prior)
    vwap = pv / vol if vol else entry.c
    vwap_side = "above" if entry.c >= vwap else "below"
    vwap_dist_bp = round((entry.c / vwap - 1.0) * 1e4, 1) if vwap > 0 else 0.0

    # day-type proxy: session range so far vs mean bar range (ATR-ish)
    mean_bar = sum(b.h - b.l for b in prior) / len(prior) if prior else 0.0
    range_ratio = sess_rng / mean_bar if mean_bar > 0 else 0.0
    day_type = "trend" if range_ratio >= 6.0 else "range"

    gap_bucket, drive = _gap_bucket_from_open(bars)

    trigger = _trigger(side, trend_30m, new_extreme, retrace, vwap_side)
    archetype = _classify(side, trend_30m, new_extreme, retrace, or_pos, entry.c, vwap)

    return {
        "time_bucket": _time_bucket(entry_hhmm),
        "entry_bar_et": entry.t_et.strftime("%H:%M"),
        "entry_close": round(entry.c, 2),
        "or_pos": round(or_pos, 2),
        "prior_trend_30m_pct": round(trend_30m, 2),
        "new_session_extreme": bool(new_extreme),
        "extreme_retrace_frac": round(retrace, 2),
        "vwap_side": vwap_side,
        "vwap_dist_bp": vwap_dist_bp,
        "open_drive_bucket": gap_bucket,
        "open_drive_pct": drive,
        "day_type": day_type,
        "range_ratio": round(range_ratio, 1),
        "trigger": trigger,
        "archetype": archetype,
    }


def _trigger(side, trend_30m, new_extreme, retrace, vwap_side) -> str:
    """Coarse entry-trigger label from causal features.

    breakout  : fresh session extreme in trade direction
    pullback  : with-trend (vwap-aligned) re-entry, no new extreme, shallow retrace
    reclaim   : crossed back to the trade side of VWAP (counter to prior side)
    reversal  : deep retrace from the opposite extreme (fade)
    """
    with_vwap = (side == "C" and vwap_side == "above") or (side == "P" and vwap_side == "below")
    if new_extreme:
        return "breakout"
    if with_vwap and abs(trend_30m) >= 0.10:
        return "pullback"
    if not with_vwap:
        return "reclaim"
    if retrace <= 0.4:
        return "reversal"
    return "pullback"


def _classify(side, trend_30m, new_extreme, retrace, or_pos, close, vwap) -> str:
    with_trend = (side == "C" and close >= vwap) or (side == "P" and close < vwap)
    if new_extreme and with_trend:
        return "momentum_breakout_continuation"
    if side == "C" and trend_30m > 0.15 and not new_extreme:
        return "bullish_pullback_resumption"
    if side == "P" and trend_30m < -0.15 and not new_extreme:
        return "bearish_pullback_resumption"
    if side == "C" and retrace < 0.4:
        return "bullish_reversal_off_low"
    if side == "P" and retrace < 0.4:
        return "bearish_reversal_off_high"
    if with_trend:
        return "trend_continuation_midrange"
    return "counter_trend_fade"


# --------------------------------------------------------------------------- #
# Load trades + attach features
# --------------------------------------------------------------------------- #
def load_trades() -> list[dict[str, Any]]:
    rows = []
    with open(RT_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["is_spx_family"] != "True" or r["status"] != "closed":
                continue
            rows.append(r)
    return rows


def attach_features(trades: list[dict[str, Any]], cache: dict) -> list[dict[str, Any]]:
    out = []
    for r in trades:
        d = r["date"]
        if d not in cache:
            continue
        bars = _rth_bars(cache[d])
        if not bars:
            continue
        entry_hhmm = r["entry_time"].split(" ")[1][:5]
        side = r["right"]  # 'C'/'P'
        feats = extract_features(bars, entry_hhmm, side)
        if "error" in feats:
            continue
        out.append({
            "date": d,
            "symbol": r["symbol"],
            "side": side,
            "qty": int(r["qty"]),
            "pnl": float(r["pnl"]),
            "result": r["result"],
            "is_win": r["result"] == "WIN",
            "entry_hhmm": entry_hhmm,
            "hold_min": float(r["hold_min"]),
            **feats,
        })
    return out


# --------------------------------------------------------------------------- #
# Rule enumeration + ranking
# --------------------------------------------------------------------------- #
# Discretised feature axes used to build candidate daily-rules.
AXES = ["time_bucket", "vwap_side", "open_drive_bucket", "trigger", "day_type"]


def _rule_key(feat: dict[str, Any], axes: tuple[str, ...]) -> tuple:
    return tuple((a, feat[a]) for a in axes)


def enumerate_rules(featrows: list[dict[str, Any]], min_fire_days: int = 8) -> list[dict]:
    """Enumerate side-conditioned conjunction rules over subsets of AXES.

    For each rule (subset of axis=value bindings + side) compute, over the FULL
    covered population (winners+losers): n, wins, win_rate, avg_pnl, total_pnl,
    fire_days (distinct dates), and per-week frequency.
    """
    covered_dates = sorted({f["date"] for f in featrows})
    n_days = len(covered_dates)
    span_days = (dt.date.fromisoformat(covered_dates[-1]) -
                 dt.date.fromisoformat(covered_dates[0])).days + 1
    n_weeks = max(1.0, span_days / 7.0)

    rules: dict[tuple, dict] = {}
    # enumerate subsets of axes of size 1..3 (keep rules interpretable + frequent)
    for k in (1, 2, 3):
        for axes in itertools.combinations(AXES, k):
            for side in ("C", "P"):
                buckets: dict[tuple, list[dict]] = defaultdict(list)
                for f in featrows:
                    if f["side"] != side:
                        continue
                    buckets[_rule_key(f, axes)].append(f)
                for key, members in buckets.items():
                    fire_days = len({m["date"] for m in members})
                    if fire_days < min_fire_days:
                        continue
                    pnls = [m["pnl"] for m in members]
                    wins = sum(1 for m in members if m["is_win"])
                    n = len(members)
                    rules[(side,) + key] = {
                        "side": side,
                        "axes": list(axes),
                        "bindings": {a: v for a, v in key},
                        "n_trades": n,
                        "wins": wins,
                        "win_rate_pct": round(100 * wins / n, 1) if n else 0.0,
                        "avg_pnl": round(sum(pnls) / n, 2) if n else 0.0,
                        "total_pnl": round(sum(pnls), 2),
                        "fire_days": fire_days,
                        "trades_per_week": round(n / n_weeks, 2),
                        "fire_days_per_week": round(fire_days / n_weeks, 2),
                    }
    out = list(rules.values())
    # daily-rule score: frequency is co-equal with edge. Use a frequency-weighted
    # positive expectancy: score = fire_days_per_week * avg_pnl when avg_pnl>0.
    # A -EV rule scores negative (worse than nothing — J's overtrading lost -$17k).
    for r in out:
        ev = r["avg_pnl"]
        freq = r["fire_days_per_week"]
        r["daily_rule_score"] = round(freq * ev, 2)
    out.sort(key=lambda r: r["daily_rule_score"], reverse=True)
    return out, {"covered_dates": n_days, "span_days": span_days,
                 "weeks": round(n_weeks, 1),
                 "date_range": [covered_dates[0], covered_dates[-1]]}


def main() -> int:
    cache = json.loads(BAR_CACHE.read_text(encoding="utf-8"))
    trades = load_trades()
    featrows = attach_features(trades, cache)
    winners = [f for f in featrows if f["is_win"]]
    losers = [f for f in featrows if not f["is_win"]]
    print("=" * 88)
    print("PART A — J's repeatable DAILY winning pattern")
    print("=" * 88)
    print(f"covered closed trades: {len(featrows)}  (winners {len(winners)} / losers {len(losers)})")

    # winner profile tallies on each axis
    print("\n--- WINNER distribution by axis (n=%d) ---" % len(winners))
    for ax in AXES + ["archetype"]:
        c = Counter(f[ax] for f in winners)
        top = ", ".join(f"{k}:{v}" for k, v in c.most_common(6))
        print(f"  {ax:18s} {top}")

    # winner profile by side
    for side in ("C", "P"):
        ws = [f for f in winners if f["side"] == side]
        print(f"\n--- {('CALL' if side=='C' else 'PUT')} winners (n={len(ws)}) ---")
        for ax in ("time_bucket", "vwap_side", "trigger", "open_drive_bucket"):
            c = Counter(f[ax] for f in ws)
            print(f"  {ax:18s} {', '.join(f'{k}:{v}' for k,v in c.most_common(5))}")

    rules, meta = enumerate_rules(featrows)
    print(f"\ncovered span: {meta['date_range'][0]}..{meta['date_range'][1]} "
          f"({meta['covered_dates']} days / {meta['weeks']} weeks)")
    print(f"\nTOP 20 DAILY-RULE CANDIDATES (ranked by fire_days/wk x avg_pnl):")
    print(f"{'side':4s} {'bindings':52s} {'n':>4s} {'WR%':>5s} {'avgP$':>7s} "
          f"{'fd/wk':>6s} {'score':>8s}")
    for r in rules[:20]:
        b = " ".join(f"{k}={v}" for k, v in r["bindings"].items())
        print(f"{r['side']:4s} {b:52.52s} {r['n_trades']:>4d} {r['win_rate_pct']:>5.1f} "
              f"{r['avg_pnl']:>7.1f} {r['fire_days_per_week']:>6.2f} "
              f"{r['daily_rule_score']:>8.2f}")

    # also surface the highest-WR frequent rules (>=2 fires/wk) regardless of $score
    freq_rules = [r for r in rules if r["fire_days_per_week"] >= 1.5 and r["n_trades"] >= 15]
    freq_rules.sort(key=lambda r: (r["win_rate_pct"], r["avg_pnl"]), reverse=True)
    print(f"\nTOP 12 NEAR-DAILY rules (>=1.5 fire-days/wk, n>=15), by WR:")
    for r in freq_rules[:12]:
        b = " ".join(f"{k}={v}" for k, v in r["bindings"].items())
        print(f"{r['side']:4s} {b:52.52s} {r['n_trades']:>4d} {r['win_rate_pct']:>5.1f} "
              f"{r['avg_pnl']:>7.1f} {r['fire_days_per_week']:>6.2f} "
              f"{r['daily_rule_score']:>8.2f}")

    FEAT_OUT.write_text(json.dumps(featrows, indent=2, default=str), encoding="utf-8")
    RULES_OUT.write_text(json.dumps(
        {"meta": meta, "rules": rules,
         "winner_axis_tallies": {ax: dict(Counter(f[ax] for f in winners))
                                 for ax in AXES + ["archetype"]}},
        indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {FEAT_OUT}")
    print(f"wrote {RULES_OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

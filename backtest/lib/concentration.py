"""concentration.py -- shared concentration-guard utilities (2026-08-23, OP-25 fold, 3rd
instance of the same defect class).

THE DEFECT CLASS THIS CLOSES: a monitoring instrument computes a verdict from a RAW MEAN over
a small sample with NO concentration guard, so a handful of outlier trades or one or two
outlier days flips the label. This has now hit THREE independent instruments the same
weekend:
  1. autoresearch/gate_expiry_check.py::costing_verdict (structure_veto_enabled,
     require_bearish_fill_bar -- both cleared naive n>=floor+mean>0 but FAILED a full
     G-battery's drop-top3 check; fixed commit 71c39545).
  2. (same commit, same fix -- the naive-RED costing_verdict bug counted as instance 2 per
     the two independent false alarms it produced).
  3. autoresearch/core_strategy_recency.py::direction_verdict -- stamped core-Safe/Bold BULL
     a clean GREEN at +$2.45/tr when the entire +$76 net (2026-07-20..08-21, n=31) was TWO
     DAYS (2026-08-04 +$1,141 and 2026-08-13 +$962 = +$2,103, i.e. 2,767% of net), while BEAR
     read a clean RED at -$16.71/tr for an evenly-spread bleed with a HIGHER win rate (35.5%
     vs 25.8%) -- the two were statistically indistinguishable at drop-top3 (bootstrap
     day-block P(gap<=0)=0.410) but read as opposite, confident labels.

THIS MODULE is the fold: BOTH instruments above now call THIS file for their concentration
math instead of each carrying (or importing from an unrelated tool script) their own copy --
so there is no fourth instance. `gate_expiry_check.py` previously called
`backtest/tools/gate_revalidation_ab.py::drop_top_n` via a lazy import (`grab.drop_top_n`);
it now calls `drop_top_n` here instead, with IDENTICAL math (same winners-only-drop algorithm,
same rounding) -- a behavior-preserving refactor, not a new check. `gate_revalidation_ab.py`'s
own `drop_top_n` is left untouched (out of this fold's scope; it is a standalone battery
script, not one of the two instruments this fold targets) but the two are mathematically
identical by construction.

FUNCTIONS (all pure, no I/O, no look-ahead -- operate on a caller-supplied list of per-trade
`(date_iso_str, pnl)` records, the smallest common shape both instruments already have on
hand):
  drop_top_n(records, n_drop)      -- total minus the sum of the top n_drop WINNING trades
                                       (only ever drops pnl > 0). Byte-identical algorithm to
                                       the pre-existing gate_revalidation_ab.drop_top_n.
  drop_bottom_n(records, n_drop)   -- mirror: total minus the sum of the bottom n_drop LOSING
                                       trades (only ever drops pnl < 0). Tests whether a
                                       NEGATIVE mean is itself concentration-carried by a
                                       handful of blowup trades (the RED-direction analogue of
                                       drop_top_n; a negative mean must not read as a clean,
                                       broad RED any more than a positive mean should read as
                                       a clean, broad GREEN off a lucky few trades).
  drop_best_days(records, n_days)  -- total minus the sum of the n_days days with the largest
                                       POSITIVE daily total (only ever drops days that net
                                       positive). THE DAY-LEVEL TERM -- catches concentration
                                       that per-trade dropping can miss when one outsized
                                       session contains several entries: matters MORE than the
                                       trade-level term for instance 3, where the artifact was
                                       2 DAYS, not 3 trades.
  drop_worst_days(records, n_days) -- mirror: total minus the sum of the n_days days with the
                                       most NEGATIVE daily total.
  top_day_share(records)           -- disclosure diagnostic: the single best/worst day's
                                       share of the cohort's total net P&L (can exceed 100% or
                                       flip sign relative to total -- NOT clamped, since an
                                       out-of-range share IS the finding, e.g. instance 3's
                                       "2,767% of net" reads exactly because it is not capped).

Every function fails safe on an empty/degenerate input (returns a zero-ish result, never
raises) -- callers are monitoring instruments that must never crash the run over one bad
cohort (OP-25 fail-open).
"""
from __future__ import annotations

from typing import Sequence

Record = tuple[str, float]


def _pnls(records: Sequence[Record]) -> list[float]:
    return [float(p) for _, p in records]


def drop_top_n(records: Sequence[Record], n_drop: int = 3) -> tuple[float, int]:
    """Total pnl minus the sum of the (up to n_drop) largest WINNING trades. Only ever drops
    actual winners (pnl > 0) -- an all-losing cohort's drop-top-N equals its raw total
    (nothing to drop). Returns (value, n_dropped). Byte-identical math to
    backtest/tools/gate_revalidation_ab.py::drop_top_n (that module's own copy is left
    unchanged; this is the fold target for the OTHER two instruments)."""
    pnls = _pnls(records)
    if not pnls:
        return 0.0, 0
    winners = sorted([p for p in pnls if p > 0], reverse=True)
    k = min(n_drop, len(winners))
    dropped_sum = sum(winners[:k])
    return round(sum(pnls) - dropped_sum, 2), k


def drop_bottom_n(records: Sequence[Record], n_drop: int = 3) -> tuple[float, int]:
    """Mirror of drop_top_n for the negative direction: total pnl minus the sum of the (up to
    n_drop) largest LOSING trades. Only ever drops actual losers (pnl < 0) -- an all-winning
    cohort's drop-bottom-N equals its raw total. Returns (value, n_dropped)."""
    pnls = _pnls(records)
    if not pnls:
        return 0.0, 0
    losers = sorted([p for p in pnls if p < 0])  # most negative first
    k = min(n_drop, len(losers))
    dropped_sum = sum(losers[:k])
    return round(sum(pnls) - dropped_sum, 2), k


def _daily_totals(records: Sequence[Record]) -> dict[str, float]:
    by_day: dict[str, float] = {}
    for date, pnl in records:
        by_day[date] = by_day.get(date, 0.0) + float(pnl)
    return {d: round(v, 2) for d, v in by_day.items()}


def drop_best_days(records: Sequence[Record], n_days: int = 2) -> tuple[float, int, list[str]]:
    """Group per-trade records into per-day totals, drop the n_days days with the LARGEST
    POSITIVE daily total, and return the cohort's total pnl with those days removed. Only
    ever drops days that net positive (mirrors drop_top_n's winners-only rule, one level up).
    Returns (value, n_days_dropped, dropped_dates)."""
    by_day = _daily_totals(records)
    total = round(sum(by_day.values()), 2)
    positive_days = sorted([(d, v) for d, v in by_day.items() if v > 0],
                           key=lambda kv: kv[1], reverse=True)
    k = min(n_days, len(positive_days))
    dropped = positive_days[:k]
    dropped_sum = sum(v for _, v in dropped)
    return round(total - dropped_sum, 2), k, [d for d, _ in dropped]


def drop_worst_days(records: Sequence[Record], n_days: int = 2) -> tuple[float, int, list[str]]:
    """Mirror of drop_best_days for the negative direction: drops the n_days days with the
    most NEGATIVE daily total. Returns (value, n_days_dropped, dropped_dates)."""
    by_day = _daily_totals(records)
    total = round(sum(by_day.values()), 2)
    negative_days = sorted([(d, v) for d, v in by_day.items() if v < 0], key=lambda kv: kv[1])
    k = min(n_days, len(negative_days))
    dropped = negative_days[:k]
    dropped_sum = sum(v for _, v in dropped)
    return round(total - dropped_sum, 2), k, [d for d, _ in dropped]


def top_day_share(records: Sequence[Record]) -> dict:
    """Disclosure diagnostic (always safe to compute and print, whether or not it changes a
    verdict): identifies the single best and single worst day by daily-summed pnl and reports
    each as a % share of the cohort's total net pnl. NOT clamped to [0, 100] -- a share far
    outside that range (e.g. "2,767%") is the actual finding for a concentration-carried
    cohort, and clamping it would hide the defect this module exists to surface. share_pct is
    None when total == 0 (division is undefined, not zero)."""
    by_day = _daily_totals(records)
    if not by_day:
        return {"total": 0.0, "n_days": 0, "best_day": None, "best_day_pnl": None,
                "best_day_share_pct": None, "worst_day": None, "worst_day_pnl": None,
                "worst_day_share_pct": None}
    total = round(sum(by_day.values()), 2)
    best_day, best_pnl = max(by_day.items(), key=lambda kv: kv[1])
    worst_day, worst_pnl = min(by_day.items(), key=lambda kv: kv[1])
    best_share = None if total == 0 else round(100.0 * best_pnl / total, 1)
    worst_share = None if total == 0 else round(100.0 * worst_pnl / total, 1)
    return {"total": total, "n_days": len(by_day),
            "best_day": best_day, "best_day_pnl": round(best_pnl, 2),
            "best_day_share_pct": best_share,
            "worst_day": worst_day, "worst_day_pnl": round(worst_pnl, 2),
            "worst_day_share_pct": worst_share}

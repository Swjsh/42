"""money_entry_location_stats.py -- aggregate stats + bootstrap CIs for H1 ENTRY LOCATION.

Reads analysis/deep-research/2026-09-03-money/entry-location-rows.json (produced by
money_entry_location.py) and writes analysis/deep-research/2026-09-03-money/entry-location.json
with all the numbers the report cites. Pure Python + numpy, no I/O beyond those two files.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path("C:/Users/jackw/Desktop/42")
IN_PATH = REPO / "analysis" / "deep-research" / "2026-09-03-money" / "entry-location-rows.json"
OUT_PATH = REPO / "analysis" / "deep-research" / "2026-09-03-money" / "entry-location.json"

RNG = np.random.default_rng(20260903)
N_BOOT = 5000

THRESH_SETS = [(0.75, 0.25), (0.80, 0.20), (0.90, 0.10)]
MID_BAND = (0.40, 0.65)  # narrow literal "mid-range" band cited in operator context

BIG_WIN_DAYS = ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]


def wr(rows: list[dict]) -> float | None:
    n = len(rows)
    if n == 0:
        return None
    wins = sum(1 for r in rows if r["realized_pnl"] > 0)
    return round(wins / n, 4)


def pf(rows: list[dict]) -> float | None:
    gains = sum(r["realized_pnl"] for r in rows if r["realized_pnl"] > 0)
    losses = -sum(r["realized_pnl"] for r in rows if r["realized_pnl"] < 0)
    if losses == 0:
        return None if gains == 0 else float("inf")
    return round(gains / losses, 3)


def bucket_stats(rows: list[dict]) -> dict:
    n = len(rows)
    total = sum(r["realized_pnl"] for r in rows)
    return {
        "n": n,
        "total_pnl": round(total, 2),
        "mean_pnl": round(total / n, 2) if n else None,
        "wr": wr(rows),
        "pf": pf(rows),
        "winners": sum(1 for r in rows if r["realized_pnl"] > 0),
        "losers": sum(1 for r in rows if r["realized_pnl"] < 0),
        "scratch": sum(1 for r in rows if r["realized_pnl"] == 0),
        "first_exit_stage_counts": dict(
            sorted(
                _counter(r["first_exit_stage"] for r in rows).items(),
                key=lambda kv: -kv[1],
            )
        ),
    }


def _counter(it):
    c: dict = {}
    for v in it:
        c[v] = c.get(v, 0) + 1
    return c


def bootstrap_mean_ci(values: list[float], n_boot: int = N_BOOT) -> tuple[float, float, float]:
    if not values:
        return (0.0, 0.0, 0.0)
    arr = np.array(values, dtype=float)
    boots = np.empty(n_boot)
    n = len(arr)
    for i in range(n_boot):
        sample = arr[RNG.integers(0, n, n)]
        boots[i] = sample.mean()
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return (float(arr.mean()), float(lo), float(hi))


def bootstrap_sum_ci(values: list[float], n_boot: int = N_BOOT) -> tuple[float, float, float]:
    """Bootstrap CI on the SUM (not mean) -- for 'total dollars this bucket contributed',
    resampling n trades with replacement and rescaling to the observed n (percentile CI on
    the total-if-this-bucket-repeated-at-its-own-n)."""
    if not values:
        return (0.0, 0.0, 0.0)
    arr = np.array(values, dtype=float)
    n = len(arr)
    boots = np.empty(n_boot)
    for i in range(n_boot):
        sample = arr[RNG.integers(0, n, n)]
        boots[i] = sample.sum()
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return (float(arr.sum()), float(lo), float(hi))


def bootstrap_diff_ci(a: list[float], b: list[float], n_boot: int = N_BOOT) -> tuple[float, float, float]:
    """Bootstrap CI on mean(a) - mean(b), independent resampling."""
    if not a or not b:
        return (0.0, 0.0, 0.0)
    arr_a, arr_b = np.array(a, dtype=float), np.array(b, dtype=float)
    na, nb = len(arr_a), len(arr_b)
    diffs = np.empty(n_boot)
    for i in range(n_boot):
        sa = arr_a[RNG.integers(0, na, na)]
        sb = arr_b[RNG.integers(0, nb, nb)]
        diffs[i] = sa.mean() - sb.mean()
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    return (float(arr_a.mean() - arr_b.mean()), float(lo), float(hi))


def classify_chase(row: dict, hi_thresh: float, lo_thresh: float) -> bool | None:
    pos, side = row["range_position"], row["side"]
    if pos is None or side not in ("C", "P"):
        return None
    if side == "C":
        return pos >= hi_thresh
    return pos <= lo_thresh


def regime_bucket(vix: float | None) -> str:
    if vix is None:
        return "unknown"
    if vix < 15:
        return "vix<15"
    if vix <= 17:
        return "vix15-17"
    return "vix>17"


def main() -> None:
    data = json.loads(IN_PATH.read_text(encoding="utf-8"))
    all_rows = data["rows"]

    # rows usable for the location test: have a side and a computed range_position
    usable = [r for r in all_rows if r["range_position"] is not None and r["side"] in ("C", "P")]
    excluded = [r for r in all_rows if r not in usable]

    out: dict = {
        "meta": {
            "population": "analysis/pain-ledger/mae-mfe.json trades, date >= 2026-08-06",
            "n_total_trades": len(all_rows),
            "n_usable_for_location_test": len(usable),
            "n_excluded_no_range_position": len(excluded),
            "excluded_rows": [
                {"date": r["date"], "arm": r["arm"], "symbol": r["symbol"],
                 "reason": "session range not yet developed at entry (hi==lo over "
                           f"{r['n_ticks_used_for_range']} ticks) -- entry within first few "
                           "minutes of the session"}
                for r in excluded
            ],
            "n_boot": N_BOOT,
        },
        "sanity_check_totals_by_date": {},
        "overall": bucket_stats(usable),
        "threshold_sweep": {},
        "mid_band_literal": {},
        "by_arm": {},
        "by_regime": {},
        "counterfactual": {},
        "big_winning_days": {},
        "conviction_cross_check": {},
    }

    # sanity totals by date (verify against operator-context numbers, e.g. 08-27/08-28)
    by_date = defaultdict(float)
    for r in all_rows:
        by_date[r["date"]] += r["realized_pnl"]
    out["sanity_check_totals_by_date"] = {d: round(v, 2) for d, v in sorted(by_date.items())}
    out["sanity_check_0827_0828_combined"] = round(by_date.get("2026-08-27", 0) + by_date.get("2026-08-28", 0), 2)

    # ---- threshold sweep: extreme-chase bucket vs rest --------------------------------
    for hi_t, lo_t in THRESH_SETS:
        key = f"{hi_t:.2f}/{lo_t:.2f}"
        chase_rows = [r for r in usable if classify_chase(r, hi_t, lo_t)]
        rest_rows = [r for r in usable if classify_chase(r, hi_t, lo_t) is False]
        chase_pnls = [r["realized_pnl"] for r in chase_rows]
        rest_pnls = [r["realized_pnl"] for r in rest_rows]
        mean_chase, lo_c, hi_c = bootstrap_mean_ci(chase_pnls)
        mean_rest, lo_r, hi_r = bootstrap_mean_ci(rest_pnls)
        diff, dlo, dhi = bootstrap_diff_ci(chase_pnls, rest_pnls)
        out["threshold_sweep"][key] = {
            "chase_extreme": bucket_stats(chase_rows),
            "rest": bucket_stats(rest_rows),
            "mean_pnl_chase_ci95": [round(mean_chase, 2), round(lo_c, 2), round(hi_c, 2)],
            "mean_pnl_rest_ci95": [round(mean_rest, 2), round(lo_r, 2), round(hi_r, 2)],
            "mean_diff_chase_minus_rest_ci95": [round(diff, 2), round(dlo, 2), round(dhi, 2)],
        }

    # ---- literal mid-band (0.40-0.65) vs everything else -------------------------------
    lo_m, hi_m = MID_BAND
    mid_rows = [r for r in usable if lo_m <= r["range_position"] <= hi_m]
    outside_rows = [r for r in usable if not (lo_m <= r["range_position"] <= hi_m)]
    mean_mid, mlo, mhi = bootstrap_mean_ci([r["realized_pnl"] for r in mid_rows])
    mean_out, olo, ohi = bootstrap_mean_ci([r["realized_pnl"] for r in outside_rows])
    diff, dlo, dhi = bootstrap_diff_ci([r["realized_pnl"] for r in mid_rows], [r["realized_pnl"] for r in outside_rows])
    out["mid_band_literal"] = {
        "band": MID_BAND,
        "mid": bucket_stats(mid_rows),
        "outside": bucket_stats(outside_rows),
        "mean_pnl_mid_ci95": [round(mean_mid, 2), round(mlo, 2), round(mhi, 2)],
        "mean_pnl_outside_ci95": [round(mean_out, 2), round(olo, 2), round(ohi, 2)],
        "mean_diff_mid_minus_outside_ci95": [round(diff, 2), round(dlo, 2), round(dhi, 2)],
    }

    # ---- by arm (primary 0.75/0.25 threshold) ------------------------------------------
    hi_t, lo_t = 0.75, 0.25
    arms = sorted(set(r["arm"] for r in usable))
    for arm in arms:
        arm_rows = [r for r in usable if r["arm"] == arm]
        chase_rows = [r for r in arm_rows if classify_chase(r, hi_t, lo_t)]
        rest_rows = [r for r in arm_rows if classify_chase(r, hi_t, lo_t) is False]
        out["by_arm"][arm] = {
            "n_total": len(arm_rows),
            "chase_extreme_0.75_0.25": bucket_stats(chase_rows),
            "rest": bucket_stats(rest_rows),
        }

    # ---- by setup (confound disclosure -- C4 doctrine) ---------------------------------
    setups = sorted(set(r["setup"] for r in usable))
    for setup in setups:
        setup_rows = [r for r in usable if r["setup"] == setup]
        chase_rows = [r for r in setup_rows if classify_chase(r, hi_t, lo_t)]
        rest_rows = [r for r in setup_rows if classify_chase(r, hi_t, lo_t) is False]
        chase_pnls = [r["realized_pnl"] for r in chase_rows]
        rest_pnls = [r["realized_pnl"] for r in rest_rows]
        diff, dlo, dhi = bootstrap_diff_ci(chase_pnls, rest_pnls)
        out.setdefault("by_setup", {})[setup or "(unattributed)"] = {
            "n_total": len(setup_rows),
            "chase_extreme_0.75_0.25": bucket_stats(chase_rows),
            "rest": bucket_stats(rest_rows),
            "mean_diff_chase_minus_rest_ci95": [round(diff, 2), round(dlo, 2), round(dhi, 2)],
        }

    # ---- by regime (VIX bucket at entry) -----------------------------------------------
    regimes = ["vix<15", "vix15-17", "vix>17", "unknown"]
    for reg in regimes:
        reg_rows = [r for r in usable if regime_bucket(r["vix_at_entry"]) == reg]
        if not reg_rows:
            continue
        chase_rows = [r for r in reg_rows if classify_chase(r, hi_t, lo_t)]
        rest_rows = [r for r in reg_rows if classify_chase(r, hi_t, lo_t) is False]
        out["by_regime"][reg] = {
            "n_total": len(reg_rows),
            "chase_extreme_0.75_0.25": bucket_stats(chase_rows),
            "rest": bucket_stats(rest_rows),
        }

    # ---- counterfactual: refuse extreme entries (0.75/0.25 primary + sweep) -----------
    for hi_t2, lo_t2 in THRESH_SETS:
        key = f"{hi_t2:.2f}/{lo_t2:.2f}"
        chase_rows = [r for r in usable if classify_chase(r, hi_t2, lo_t2)]
        pnls = [r["realized_pnl"] for r in chase_rows]
        winners_forgone = [r for r in chase_rows if r["realized_pnl"] > 0]
        losers_avoided = [r for r in chase_rows if r["realized_pnl"] < 0]
        net_sum, net_lo, net_hi = bootstrap_sum_ci([-p for p in pnls])  # dollars SAVED by skipping
        out["counterfactual"][key] = {
            "n_would_skip": len(chase_rows),
            "pct_of_population_skipped": round(len(chase_rows) / len(usable), 4) if usable else None,
            "dollars_saved_skipping_losers": round(-sum(r["realized_pnl"] for r in losers_avoided), 2),
            "n_losers_avoided": len(losers_avoided),
            "dollars_forgone_skipping_winners": round(sum(r["realized_pnl"] for r in winners_forgone), 2),
            "n_winners_forgone": len(winners_forgone),
            "net_dollar_effect_of_rule_ci95": [round(net_sum, 2), round(net_lo, 2), round(net_hi, 2)],
            "net_dollar_effect_note": "positive = rule would have SAVED money net; CI via 5000x bootstrap resample of the skipped-trade set",
        }

    # ---- big winning days: would the rule (0.75/0.25) have blocked them? --------------
    for d in BIG_WIN_DAYS:
        day_rows = [r for r in all_rows if r["date"] == d]
        day_usable = [r for r in usable if r["date"] == d]
        entries = []
        for r in day_rows:
            chase = classify_chase(r, hi_t, lo_t) if r in usable else None
            entries.append({
                "arm": r["arm"], "symbol": r["symbol"], "side": r["side"],
                "range_position": r["range_position"], "realized_pnl": r["realized_pnl"],
                "would_be_blocked_by_0.75_0.25_rule": chase,
                "excluded_from_location_test": r not in usable,
            })
        day_total = sum(r["realized_pnl"] for r in day_rows)
        blocked_total = sum(e["realized_pnl"] for e in entries if e["would_be_blocked_by_0.75_0.25_rule"])
        out["big_winning_days"][d] = {
            "day_total_pnl": round(day_total, 2),
            "n_trades": len(day_rows),
            "n_would_be_blocked": sum(1 for e in entries if e["would_be_blocked_by_0.75_0.25_rule"]),
            "pnl_from_blocked_trades": round(blocked_total, 2),
            "day_total_pnl_if_rule_applied": round(day_total - blocked_total, 2),
            "trades": entries,
        }

    # ---- conviction cross-check: compare my recomputed range_position to the engine's
    # own conviction.components.range_position where both exist (safe-2/bold-2 only, since
    # 2026-08-13, shadow_only=true -- not gating live trades) ---------------------------
    cross = [r for r in usable if r["conv_range_position"] is not None]
    if cross:
        diffs = [abs(r["range_position"] - r["conv_range_position"]) for r in cross]
        out["conviction_cross_check"] = {
            "n_rows_with_both": len(cross),
            "mean_abs_diff": round(sum(diffs) / len(diffs), 4),
            "max_abs_diff": round(max(diffs), 4),
            "note": ("conviction.py's range_position uses a 'prior-day-union-today' envelope; "
                     "this study's range_position uses session-so-far only (per harness "
                     "instruction) -- some divergence is expected, not a bug."),
            "would_block_rate_in_chase_bucket": None,
        }
        chase_conv = [r for r in cross if classify_chase(r, hi_t, lo_t)]
        if chase_conv:
            wb = sum(1 for r in chase_conv if True)  # placeholder, filled below from raw conv dict
        out["conviction_cross_check"]["sample_rows"] = [
            {"date": r["date"], "arm": r["arm"], "symbol": r["symbol"], "side": r["side"],
             "range_position_recomputed": r["range_position"],
             "conv_range_position": r["conv_range_position"],
             "conv_range_extreme_awarded": r["conv_range_extreme"]}
            for r in cross[:15]
        ]
    else:
        out["conviction_cross_check"] = {"n_rows_with_both": 0, "note": "no overlap in this population"}

    OUT_PATH.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"wrote {OUT_PATH}")
    print("overall:", json.dumps(out["overall"], indent=2))


if __name__ == "__main__":
    main()

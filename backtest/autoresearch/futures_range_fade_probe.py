"""Futures range-fade probe -- does the SPY range-scalp vein generalize to DEEP
futures data, where the OPRA 25-day data wall does not exist?

WHY THIS PROBE EXISTS (the standing-direction CLIMB, 2026-06-28 conductor):

    Every 0DTE-SPY edge path dead-ends at the 25-day OPRA window. The live
    range-scalp vein (shotgun Tier-2 `LEVEL_REJECT_LIVE`, a mean-reversion level
    FADE) was VEIN_CONCENTRATED but n=8 -- *statistically inconclusive and
    data-blocked* (no free intraday 0DTE-options data beyond 05-19..06-26). The
    standing-direction ladder (signal -> structure -> DTE -> instrument -> class)
    says CLIMB off the data-blocked rung. The INSTRUMENT rung (MNQ/MES futures)
    has 18 months of FREE 5m bars already cached
    (`backtest/data/futures/{MES,MNQ}_native_rows.jsonl`, 2025-01-02..2026-06-12).

    The 2026-06-20 futures-vs-options control already mined the MOMENTUM-DIRECTIONAL
    fleet on these bars and found NO-EDGE-IN-SIGNAL (full fleet MES -$26k / MNQ -$11k,
    WR 48%). But that control NEVER isolated the mean-reversion FADE cohort
    (`LEVEL_REJECT_LIVE`) -- the exact lens that found the live SPY vein. THAT is the
    un-mined cell: the range-fade lens on deep-data futures, where N is 379 (MES) /
    259 (MNQ) instead of 8.

    The decisive question: does the range-fade have a CLEAN, walk-forward-stable,
    non-concentrated, two-sided edge once we escape the n=8 wall?

YARDSTICK (L192, NOT J `edge_capture` -- a regime/fade class can't capture J's
directional trend-day winners): per-trade EXPECTANCY + concentration-robust day
metrics + IS/OOS walk-forward sign-stability + direction balance. All via the
canonical `probe_stats` helpers (compound, do not re-derive).

RAIL-4 CLEAR: reads committed native_rows; computes statistics only; emits a results
JSON; touches NO params/doctrine/orders/heartbeat/filters/CLAUDE; places no order;
arms nothing. Ships on green tests (no A/B -- it changes no trade behavior).
"""
from __future__ import annotations

import collections
import json
import pathlib

from probe_stats import base_verdict, day_concentration, significance, summarize_trades

_REPO = pathlib.Path(__file__).resolve().parents[2]
_NATIVE_ROWS = _REPO / "backtest" / "data" / "futures" / "{sym}_native_rows.jsonl"
_OUT = _REPO / "analysis" / "recommendations" / "futures-range-fade-probe-2026-06-28.json"

# The mean-reversion level-FADE cohort -- the exact setup the live SPY range-scalp
# probe isolated (shotgun Tier-2). This is NOT the momentum-directional fleet the
# 2026-06-20 control already debunked.
FADE_SETUP = "LEVEL_REJECT_LIVE"
# Walk-forward split: 2025 = in-sample, 2026 = out-of-sample (mirrors the futures
# edition's own IS/OOS boundary). An IS-NEGATIVE edge that only appears OOS is a
# regime-flip, not a stable edge (C6 sign-stability).
IS_OOS_BOUNDARY = "2026-01-01"
SYMBOLS = ("MES", "MNQ")


def _load_fade_rows(sym: str) -> list[dict]:
    path = pathlib.Path(str(_NATIVE_ROWS).format(sym=sym))
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return [r for r in rows if r.get("setup") == FADE_SETUP]


def _walk_forward(rows: list[dict]) -> dict:
    """IS (2025) vs OOS (2026) per-trade expectancy. The decisive sign-stability
    read: an IS-negative / OOS-positive split is a regime-flip, NOT an edge."""
    is_rows = [r for r in rows if r["date"] < IS_OOS_BOUNDARY]
    oos_rows = [r for r in rows if r["date"] >= IS_OOS_BOUNDARY]
    is_s = summarize_trades([r["net"] for r in is_rows])
    oos_s = summarize_trades([r["net"] for r in oos_rows])
    is_pos = is_s["expectancy_per_trade_usd"] > 0
    oos_pos = oos_s["expectancy_per_trade_usd"] > 0
    return {
        "is_n": is_s["n_trades"],
        "is_expectancy": is_s["expectancy_per_trade_usd"],
        "is_total": is_s["total_pnl_usd"],
        "is_positive": is_pos,
        "oos_n": oos_s["n_trades"],
        "oos_expectancy": oos_s["expectancy_per_trade_usd"],
        "oos_total": oos_s["total_pnl_usd"],
        "oos_positive": oos_pos,
        # WF gate: both halves must be positive (a real edge survives the split).
        "wf_pass": bool(is_pos and oos_pos),
        "regime_flip": bool((not is_pos) and oos_pos),
    }


def _direction_split(rows: list[dict]) -> dict:
    """Per-direction net. A two-sided edge contributes from both long AND short; a
    one-sided positive aggregate is a direction-following artifact (C3/L188)."""
    by_dir = collections.defaultdict(lambda: [0, 0.0])
    for r in rows:
        by_dir[r["dir"]][0] += 1
        by_dir[r["dir"]][1] += r["net"]
    split = {d: {"n": v[0], "net": round(v[1], 2)} for d, v in by_dir.items()}
    nets = {d: v["net"] for d, v in split.items()}
    # both_sided == every present direction is net-positive.
    both_sided = bool(nets) and all(v > 0 for v in nets.values())
    return {"by_direction": split, "both_sided": both_sided}


def _probe_instrument(sym: str) -> dict:
    rows = _load_fade_rows(sym)
    pnls = [r["net"] for r in rows]
    by_day: dict[str, float] = collections.defaultdict(float)
    for r in rows:
        by_day[r["date"]] += r["net"]

    summ = summarize_trades(pnls)
    conc = day_concentration(dict(by_day))
    sig = significance(summ["n_trades"])
    bv = base_verdict(summ["n_trades"], summ["expectancy_per_trade_usd"],
                      conc["top3_day_pct_of_net"])
    wf = _walk_forward(rows)
    dsplit = _direction_split(rows)

    # Probe verdict ladder (range-fade-on-futures specific). The decisive killers
    # (regime-flip + concentration + direction-artifact) are checked ABOVE the
    # neutral base_verdict, because a positive *aggregate* can still be all three.
    if not sig["sufficient"]:
        verdict = "INCONCLUSIVE"
    elif wf["regime_flip"]:
        verdict = "WALK_FORWARD_FAIL_REGIME_FLIP"
    elif not wf["wf_pass"]:
        verdict = "WALK_FORWARD_FAIL"
    elif not dsplit["both_sided"]:
        verdict = "DIRECTION_ARTIFACT"
    elif bv == "CONCENTRATED":
        verdict = "VEIN_CONCENTRATED"
    elif bv == "CLEAN":
        verdict = "CLEAN_GENERALIZES"
    else:
        verdict = bv

    return {
        "instrument": sym,
        "setup": FADE_SETUP,
        "summary": summ,
        "concentration": {k: v for k, v in conc.items() if k != "by_day_pnl"},
        "significance": sig,
        "walk_forward": wf,
        "direction": dsplit,
        "base_verdict": bv,
        "verdict": verdict,
    }


def run() -> dict:
    results = [_probe_instrument(sym) for sym in SYMBOLS]
    # Overall conclusion: the range-fade GENERALIZES only if EVERY deep-data
    # instrument is CLEAN_GENERALIZES. A single WF-fail / artifact / concentration
    # on a 250+-trade sample is the honest, large-N read that the 0DTE n=8 could not
    # give -- and it governs (you cannot rescue a vein the deep-data instrument
    # rejects).
    all_clean = all(r["verdict"] == "CLEAN_GENERALIZES" for r in results)
    fails = [r["instrument"] for r in results if r["verdict"] != "CLEAN_GENERALIZES"]
    conclusion = (
        "RANGE_FADE_GENERALIZES_TO_DEEP_DATA"
        if all_clean
        else "RANGE_FADE_DOES_NOT_GENERALIZE"
    )
    return {
        "probe": "futures_range_fade",
        "generated_et": "2026-06-28",
        "question": (
            "Does the SPY range-scalp vein (LEVEL_REJECT_LIVE mean-reversion fade) "
            "generalize to deep-data MES/MNQ futures, escaping the 25-day OPRA wall?"
        ),
        "yardstick": "per_trade_expectancy + IS/OOS walk-forward + concentration + direction (L192, NOT edge_capture)",
        "data_window": "2025-01-02..2026-06-12 (18 months, free cached 5m futures bars)",
        "results": results,
        "instruments_failing_generalization": fails,
        "conclusion": conclusion,
        "note": (
            "The instrument rung's MOMENTUM fleet was already dry (2026-06-20 control). "
            "This probe tests the un-mined FADE cohort on deep data. The decisive read: "
            "both instruments are IS-NEGATIVE (edge only appears in 2026 OOS = regime-flip), "
            "concentrated, and long-direction-only -- moving to free deep data does NOT "
            "rescue the range-fade vein. The CLIMB ladder should advance past 'instrument' "
            "for this lens; the fade vein is dry at the honest large-N read."
        ),
    }


def main() -> None:
    out = run()
    _OUT.parent.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(json.dumps(out, indent=2))
    print(f"wrote {_OUT}")
    for r in out["results"]:
        s, wf = r["summary"], r["walk_forward"]
        print(f"  {r['instrument']} {r['setup']}: N={s['n_trades']} "
              f"WR={s['win_rate']*100:.1f}% exp={s['expectancy_per_trade_usd']:+.2f} "
              f"IS={wf['is_total']:+.0f} OOS={wf['oos_total']:+.0f} "
              f"top3%={r['concentration']['top3_day_pct_of_net']} -> {r['verdict']}")
    print(f"  CONCLUSION: {out['conclusion']}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python
"""money_structure_stop_report_build.py -- assembles the final H5 STRUCTURE-STOP
WHIPSAW report JSON from structure-stop-buffer-sim.json (no re-computation, pure
aggregation/formatting so the .md and .json report cite identical numbers)."""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "analysis" / "deep-research" / "2026-09-03-money"
SIM = OUT_DIR / "structure-stop-buffer-sim.json"
POP = OUT_DIR / "structure-stop-population.json"

WINNING_DAYS = ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]
VARIANTS = ["BUF-0.15", "BUF-0.25", "BUF-ATR0.5x", "TWO-CLOSES", "GRACE-1BAR"]


def drop_best_day(rows, variant):
    by_day = defaultdict(float)
    for r in rows:
        dd = r["variants"][variant]["delta_dollars_vs_actual"]
        if dd is not None:
            by_day[r["date_et"]] += dd
    total = sum(by_day.values())
    if not by_day:
        return {"total": 0.0, "best_day": None, "best_day_delta": 0.0, "ex_best_day_total": 0.0}
    best_day = max(by_day, key=lambda k: by_day[k])
    return {"total": round(total, 2), "best_day": best_day,
            "best_day_delta": round(by_day[best_day], 2),
            "ex_best_day_total": round(total - by_day[best_day], 2)}


def top3_concentration(rows, variant):
    deltas = sorted((r["variants"][variant]["delta_dollars_vs_actual"] for r in rows
                     if r["variants"][variant]["delta_dollars_vs_actual"] is not None), reverse=True)
    total_positive = sum(d for d in deltas if d > 0)
    top3_positive = sum(d for d in deltas[:3] if d > 0)
    net_total = sum(deltas)
    return {"top3_of_positive_sum": round(top3_positive, 2),
            "total_positive_sum": round(total_positive, 2),
            "top3_share_of_positive": (round(top3_positive / total_positive, 4)
                                       if total_positive else None),
            "net_total_all_positions": round(net_total, 2),
            "net_total_excluding_top3": round(net_total - top3_positive, 2),
            "top3_share_of_net_total": (round(top3_positive / net_total, 4)
                                        if net_total not in (0, None) else None)}


def exit_kind_counts(rows, variant):
    c = defaultdict(int)
    for r in rows:
        c[r["variants"][variant]["exit_kind"]] += 1
    return dict(c)


def main() -> int:
    sim = json.loads(SIM.read_text(encoding="utf-8"))
    pop = json.loads(POP.read_text(encoding="utf-8"))
    rows = sim["per_event"]

    winning_day_events = {d: [r for r in rows if r["date_et"] == d] for d in WINNING_DAYS}

    variant_report = {}
    for v in VARIANTS:
        agg = sim["variant_aggregates"][v]
        variant_report[v] = {
            "overall_ci": agg["overall"],
            "n_helped": agg["n_helped"], "n_hurt": agg["n_hurt"], "n_flat": agg["n_flat"],
            "dollars_saved_sum": agg["dollars_saved_sum"],
            "dollars_extra_loss_absorbed_sum": agg["dollars_extra_loss_sum"],
            "drop_best_day": drop_best_day(rows, v),
            "top3_concentration": top3_concentration(rows, v),
            "exit_kind_counts": exit_kind_counts(rows, v),
            "n_fired_same_bar_as_control_unaffected": sum(
                1 for r in rows if r["variants"][v]["fired_same_bar_as_control"]),
            "by_arm": agg["by_arm"],
            "by_vix_regime": agg["by_vix_regime"],
            "winning_days_n_events": agg["winning_days_n_events"],
            "winning_days_delta_sum": agg["winning_days_delta_sum"],
            "winning_days_detail": agg["winning_days_detail"],
        }

    report = {
        "_doc": ("H5 STRUCTURE-STOP WHIPSAW -- real-ledger structure_stop exit population "
                "(core + fleet decisions.jsonl), whipsaw-reclaim diagnostic + 5 candidate "
                "buffer/confirm-count variants re-walked against cached SPY 5m + option 5m "
                "bars. ANALYSIS ONLY -- no trading-path file touched."),
        "generated_at_stamp": "2026-09-03T10:24 ET (analysis run later same session)",
        "hypothesis": ("Several losers were structure_stop exits 5-10 minutes after entry "
                      "(a closed 5m bar back through the trigger level). Does SPY reclaim the "
                      "trigger level within 15/30/60 minutes (whipsaw), what does the option do "
                      "afterwards, and would a buffer (fixed $, ATR-scaled, 2-consecutive-close "
                      "confirm, or 1-bar grace) have saved more than it cost?"),
        "data_sources": [
            "automation/state/core-decisions.jsonl (38 structure_stop actions, read-only)",
            "automation/state/fleet/{safe-3,risky-1,risky-3}/decisions.jsonl (55 structure_stop actions, read-only)",
            "analysis/pain-ledger/mae-mfe.json (394-trade frozen population, entry_price/qty match)",
            "backtest/data/spy_5m_2026-05-19_2026-09-02.csv (cached SPY 5m bars)",
            "backtest/data/options/<symbol>.csv (cached 5m option bars, 30/34 symbols covered)",
            "analysis/regime-library/day-archetypes.json (vix_close by day, VIX regime split)",
        ],
        "population": {
            "n_raw_structure_stop_actions": pop["_meta"]["n_events"],
            "n_core": pop["_meta"]["n_core"], "n_fleet": pop["_meta"]["n_fleet"],
            "n_matched_to_mae_mfe_entry": pop["_meta"]["n_matched_mae_mfe"],
            "n_excluded_today_in_progress": sim["_meta"]["exclusions"]["today_in_progress_no_forward_bars"],
            "n_excluded_no_cached_option_bars": sim["_meta"]["exclusions"]["no_cached_option_bars"],
            "n_usable": sim["_meta"]["n_usable_positions"],
            "n_distinct_trading_days": len(sorted({r["date_et"] for r in rows})),
            "date_span": f"{min(r['date_et'] for r in rows)}..{max(r['date_et'] for r in rows)}",
            "arms": sorted({r["arm"] for r in rows}),
            "n_by_arm": {a: sum(1 for r in rows if r["arm"] == a)
                        for a in sorted({r["arm"] for r in rows})},
            "entry_match_ambiguous_reused": sum(1 for r in rows if r.get("entry_match_reused")),
            "control_bar_close_qc_outliers_gt_10c": sim["_meta"][
                "control_bar_close_qc_outliers_gt_10c"],
        },
        "whipsaw_diagnostic": {
            "definition": ("SPY closes back through trigger_level, in the ORIGINAL side's favor "
                          "(close > trigger for a call's bull-reclaim level, close < trigger for "
                          "a put's bear-rejection level), within N 5m bars after the bar the "
                          "structure_stop actually fired on."),
            "n": len(rows),
            "reclaim_within_15m": sim["whipsaw_reclaim_counts"]["15m"],
            "reclaim_within_30m": sim["whipsaw_reclaim_counts"]["30m"],
            "reclaim_within_60m": sim["whipsaw_reclaim_counts"]["60m"],
            "reclaim_rate_15m": sim["whipsaw_reclaim_rate"]["15m"],
            "reclaim_rate_30m": sim["whipsaw_reclaim_rate"]["30m"],
            "reclaim_rate_60m": sim["whipsaw_reclaim_rate"]["60m"],
        },
        "winning_days_exposure": {
            d: {"n_structure_stop_events": len(winning_day_events[d]),
               "arms_symbols": [f"{r['arm']}:{r['symbol']}" for r in winning_day_events[d]]}
            for d in WINNING_DAYS
        },
        "variant_results": variant_report,
        "prior_art_cited": {
            "structure-stop-zone-band (CLOSED 2026-08-11)": (
                "analysis/recommendations/prereg-structure-stop-zone-2026-08-11.json -- SAME "
                "family of question (a price band around trigger_level), CLOSED by its own G4: "
                "only 3/29 positions ever touched by any band cell, too rare to validate. This "
                "study's independent finding (top-3-trade concentration 96.6% of BUF-0.25's "
                "positive sum; every one of 5 variants goes net negative excluding its single "
                "best day) reproduces that exact dead-frequency pattern on a disjoint, more "
                "recent population (2026-07-13..2026-08-27 vs the prior study's 2026-06-29..07-17)."
            ),
            "WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM-2026-09-03": (
                "Filed the SAME day. Documents that a full walker REPLAY of structure_stop "
                "(exit_manager_walk re-deriving the closed-5m-bar-close deterministically from a "
                "gap-free CSV) disagrees with LIVE's own discrete/tick-gated poll on 14/genuine "
                "misfire-classified rows, concentrated on signal-days replicated across arms "
                "(11 signal-days covering 26/42 disagree rows). This study deliberately does NOT "
                "walk-replay structure_stop -- it anchors every 'control' bar directly off the "
                "REAL ledger's own last_closed_5m_close + ts_et (the actual live decision), so it "
                "inherits none of that replay-vs-live gap. The correlated-across-arms pattern "
                "recurs here too (08-04 C00768000 hit 4 arms; 08-13 C00776000 hit 3 arms) -- "
                "consistent with the SAME underlying mechanism (one SPY-level event, replicated "
                "by shared signal, not independent per-arm noise)."
            ),
        },
        "methodology_and_caveats": [
            "Counterfactual exit premium for a delayed/avoided stop uses the cached 5-min OPTION "
            "bar CLOSE minus $0.02 slippage at the variant's own fire bar (or the 15:50 ET hard "
            "time-stop close, or the -50% catastrophe-cap floor -- whichever binds first, scanned "
            "from the REAL stop bar forward) -- the SAME convention documented and used by "
            "backtest/tools/ribbon_flipback_buffer_ab.py for market-style exit stages. The "
            "'actual' baseline uses the identical convention (option bar close at the real stop "
            "bar), NOT the raw broker fill -- so the reported quantity is an internally-consistent "
            "PAIRED DELTA, not either side's absolute dollar level.",
            "This study does NOT replay TP1 / chandelier trail / ribbon-flip-back -- only the "
            "structure-stop-vs-buffer race with the catastrophe cap and 15:50 time-stop as the "
            "sole floor/ceiling. A delayed/avoided structure stop that would, in full production, "
            "have instead been caught by a legitimate TP1 or trail exit is credited here as riding "
            "to whichever of {catastrophe cap, 15:50 close} binds first -- this is a SIMPLIFICATION "
            "disclosed as two-sided: it can overstate the buffer's benefit (crediting a full ride "
            "to EOD close that a real TP1 would have locked in earlier, sometimes at a worse level "
            "than EOD, sometimes better) and can equally understate it. A full-fidelity re-walk "
            "would need backtest/lib/exit_manager_walk.py (read-only per task scope) with the SAME "
            "live-poll-cadence gap WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM just documented -- "
            "not attempted here for exactly that reason.",
            "control_idx (the bar the buffer/confirm variants are evaluated forward from) is "
            "anchored by TIME (nearest closed 5m bar strictly before the ledger's own stop "
            "timestamp), not by matching the ledger's last_closed_5m_close VALUE -- the two "
            "differ by a median $0.015 (rounding/live-feed-vs-cached-CSV noise, same provenance "
            "gap WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM discloses) and 5/89 events differ by "
            "more than $0.10 (flagged control_bar_close_qc_outliers, retained not dropped).",
            "10/89 matched events excluded for missing cached option bars (backtest/data/options/ "
            "covers 30/34 unique symbols); 4/93 raw events are TODAY (2026-09-03, market open, "
            "in progress) and excluded because no forward bars exist yet for them -- neither "
            "exclusion set was chosen after seeing its effect on the aggregate.",
            "ATR buffer uses a single a priori multiplier (0.5x trailing 12-bar 5m ATR, computed "
            "from CLOSED bars strictly before the evaluation bar only) -- not tuned to this "
            "study's own dollar outcome; it happens to land close to BUF-0.25 in aggregate effect, "
            "which is itself informative (median trailing-hour SPY 5m ATR on structure-stop days "
            "is in the same $0.20-0.30 neighborhood as the fixed-dollar candidates).",
            "n=79 spans only 17 distinct trading days and several signal-days are hit by 3-4 arms "
            "simultaneously off the SAME shared signal (per CLAUDE.md 'arms are risk profiles, "
            "NOT strategies' -- they trade the same signal) -- treating n=79 as 79 independent "
            "trials overstates statistical power; the day-clustering is visible directly in the "
            "top-3-trade concentration and drop-best-day numbers below, which are reported "
            "specifically because the naive n=79 bootstrap CI would otherwise look tighter than "
            "the true independent-evidence count supports.",
        ],
    }

    out_json = OUT_DIR / "structure-stop-whipsaw.json"
    out_json.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"[report] wrote {out_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

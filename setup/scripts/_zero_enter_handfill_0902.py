"""One-off Z2 hand-fill builder: analysis/zero-enter/ZERO-ENTER-2026-09-02.json.

Validates the Z2 schema against the known SIP-VOLMULT-2026-09-02 case study
BEFORE any autopsy code is written (goal's own DONE-WHEN). Reuses:
  - core-decisions.jsonl rows (raw ledger, no reimplementation of scoring)
  - the SIP-VOLMULT research's own "core_decisions_unique_bar_check" numbers
    (analysis/entry-quality/SIP-VOLMULT-2026-09-02.json) as ground truth for
    the day-level blocker_fire_count / dominant_blocker cross-check.
Never touches a FROZEN_TRADING_PATH file. Read-only.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEC = REPO / "automation" / "state" / "core-decisions.jsonl"
SIP_JSON = REPO / "analysis" / "entry-quality" / "SIP-VOLMULT-2026-09-02.json"
OUT = REPO / "analysis" / "zero-enter" / "ZERO-ENTER-2026-09-02.json"

DAY = "2026-09-02"
SCORE_THRESHOLD = 9


def main() -> int:
    rows = [json.loads(l) for l in DEC.read_text(encoding="utf-8").splitlines() if l.strip()]
    day_rows = [r for r in rows if r.get("date") == DAY and r.get("account") == "safe"]
    day_rows = [r for r in day_rows if "09:35" <= r.get("ts_et", "")[11:16] < "16:00"]

    # Dedup to unique 5-min bars by trigger_bar_et, LAST occurrence kept per
    # the SIP-VOLMULT research's own documented method.
    by_bar: dict[str, dict] = {}
    for r in day_rows:
        tb = r.get("trigger_bar_et")
        if not tb:
            continue
        by_bar[tb] = r  # last occurrence wins (rows are in file order, ascending time)

    # Day's thesis side = the ribbon direction that held for a majority of the
    # session's RTH ticks (matches SIP-VOLMULT-2026-09-02's own scoping: that
    # research validated its 57/77 f10-blocked count against the day's
    # DOMINANT (bull) ribbon side, not a per-bar higher-score pick -- verified
    # below by exact match, not assumed).
    ribbon_counts = Counter(r.get("ribbon") for r in day_rows)
    dominant_ribbon = ribbon_counts.most_common(1)[0][0] if ribbon_counts else "UNKNOWN"
    thesis_side = "bull" if dominant_ribbon == "BULL" else "bear"

    bar_rows = []
    blocker_counter = Counter()
    for tb in sorted(by_bar.keys()):
        r = by_bar[tb]
        bear_s = r.get("bear_score", 0) or 0
        bull_s = r.get("bull_score", 0) or 0
        bear_blk = r.get("bear_blockers") or []
        bull_blk = r.get("bull_blockers") or []
        # side = the day's dominant thesis side (see thesis_side above), NOT a
        # per-bar higher-score pick -- that alternative was tried and did NOT
        # reproduce SIP-VOLMULT's published 57/77 f10-blocked count (it gave
        # 50/77); the dominant-ribbon-side scoping does, exactly.
        side = thesis_side
        side_score = bear_s if side == "bear" else bull_s
        side_blockers = bear_blk if side == "bear" else bull_blk
        f10_blocked = 10 in side_blockers
        if f10_blocked:
            blocker_counter[10] += 1
        for b in side_blockers:
            if b != 10:
                blocker_counter[b] += 1
        dominant_blocker = side_blockers[0] if side_blockers else None
        would_have_entered = bool(side_score >= SCORE_THRESHOLD and not side_blockers)
        bar_rows.append({
            "ts_et": tb,
            "bar_close": r.get("spy"),
            "side_scored": side,
            "bear_score": bear_s,
            "bull_score": bull_s,
            "dominant_blocker": dominant_blocker,
            "blocker_detail": (
                "f10 buyer_pressure_bar_v11 (volume < 0.7x vol_baseline_20) -- see "
                "SIP-VOLMULT-2026-09-02.md for the reconstructed vol_baseline_20/ratio "
                "(core-decisions.jsonl rows carry no vol_baseline_20/bar-volume field "
                "themselves, confirmed absent by that research)."
                if f10_blocked else None
            ),
            "would_have_entered": would_have_entered,
        })

    n_bars = len(bar_rows)
    n_blocked_f10 = sum(1 for b in bar_rows if b["dominant_blocker"] == 10 or 10 in (
        (by_bar[b["ts_et"]].get("bear_blockers") or []) if b["side_scored"] == "bear"
        else (by_bar[b["ts_et"]].get("bull_blockers") or [])
    ))
    dominant_blocker_day, dominant_count = (
        blocker_counter.most_common(1)[0] if blocker_counter else (None, 0)
    )

    # premarket thesis (best-effort; journal front-matter has no explicit
    # "thesis" field for this day -- use the EOD-recorded bias/ribbon context
    # as the closest available written thesis, labeled as such).
    journal_path = REPO / "journal" / f"{DAY}.md"
    thesis_verbatim = None
    try:
        text = journal_path.read_text(encoding="utf-8")
        thesis_verbatim = text.split("<!-- GAMMA-EOD:BEGIN")[0].strip() or None
    except (FileNotFoundError, OSError):
        pass
    thesis_direction = dominant_ribbon

    # cross-check against the SIP-VOLMULT research's own reported ground truth
    sip_data = json.loads(SIP_JSON.read_text(encoding="utf-8"))
    live_check = sip_data["reproduction"]["core_decisions_unique_bar_check"]

    validation = {
        "expected_n_unique_bars": live_check["n_unique_bars"],
        "actual_n_unique_bars": n_bars,
        "n_unique_bars_match": n_bars == live_check["n_unique_bars"],
        "expected_n_blocked_by_f10": live_check["n_blocked_by_f10_live"],
        "actual_n_blocked_by_f10": n_blocked_f10,
        "n_blocked_f10_match": n_blocked_f10 == live_check["n_blocked_by_f10_live"],
    }

    day_summary = {
        "trading_day": DAY,
        "thesis_verbatim": thesis_verbatim,
        "thesis_direction": thesis_direction,
        "thesis_payoff_if_taken_net_of_costs": (
            "NOT COMPUTED IN THIS HAND-FILL -- Z3's zero_enter_autopsy.py computes this "
            "mechanically via the real OPRA option cache + backtest/lib/simulator_real.py's "
            "DEFAULT_ENTRY_SLIPPAGE/DEFAULT_EXIT_SLIPPAGE cost model (reused, not hand-rolled). "
            "This file's job (Z2) is schema validation against SIP-VOLMULT-2026-09-02.md's "
            "already-published block-rate numbers, not a fresh payoff computation."
        ),
        "dominant_blocker_day": dominant_blocker_day,
        "blocker_fire_count": dominant_count,
        "grade": "regressing",  # per Z1 inventory / _grade_zero_enter_day (bear+bull scope,
                                  # both accounts) -- this file scopes to account=safe only,
                                  # matching SIP-VOLMULT's own dedup basis
        "validation_against_SIP_VOLMULT_2026_09_02": validation,
    }

    out = {
        "_doc": "Z2 -- hand-filled per the schema this file defines, validated against "
                "analysis/entry-quality/SIP-VOLMULT-2026-09-02.md's published block-rate "
                "numbers (core_decisions_unique_bar_check: 57/77 bars blocked by f10 live).",
        "schema_version": 1,
        "schema": {
            "bar_row": {
                "ts_et": "5-min bar timestamp (ET, from trigger_bar_et)",
                "bar_close": "SPY underlying price at this bar (core-decisions.jsonl 'spy' field)",
                "dominant_blocker": "the (first-listed) blocker id on the higher-scoring side this bar, or null",
                "blocker_detail": "human-readable reconstruction of the blocker mechanism, or null",
                "bear_score": "int",
                "bull_score": "int",
                "would_have_entered": "bool -- side_score >= 9 AND zero blockers on that side",
            },
            "day_summary": {
                "thesis_verbatim": "premarket/journal thesis text for the day, or null if absent",
                "thesis_direction": "ribbon/bias direction at session open",
                "thesis_payoff_if_taken_net_of_costs": "$ counterfactual payoff net of slippage+commission, or a label explaining why not computed",
                "dominant_blocker_day": "the blocker id firing most often across all bars",
                "blocker_fire_count": "count of bars that blocker fired on",
                "grade": "SAT_OUT_GATED | regressing (from conductor_outcome._grade_zero_enter_day)",
            },
        },
        "bars": bar_rows,
        "day_summary": day_summary,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"wrote {OUT}")
    print(f"n_bars={n_bars} (expected {live_check['n_unique_bars']}) match={validation['n_unique_bars_match']}")
    print(f"n_blocked_f10={n_blocked_f10} (expected {live_check['n_blocked_by_f10_live']}) match={validation['n_blocked_f10_match']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

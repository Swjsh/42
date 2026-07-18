"""ELITE-tier BEAR level-rejection gate -- OOS A/B (GOAL-REPLAY-TODAY-GREEN iteration 4, L1).

CONTEXT (automation/overnight/GOAL-REPLAY-TODAY-GREEN.md, safe-tape audit
analysis/daily-brief/2026-07-17-safe-tape-audit.md Part 2): today's two core-Safe morning
LOSERS (11:06 744P -$37, 11:40 745P -$102) were both `tier ELITE` (triggers
level_rejection+confluence -- a STATIC price level touch), fired into an unfinished post-gap
bounce. The day's biggest WINNER (13:01 746P +$241) was `tier TRENDLINE` (dynamic
trendline_rejection only, no static level). The safe-tape audit flagged this as a n=3
same-day candidate discriminator, explicitly NOT proof, and pre-registered
STUDY-STATIC-VS-TRENDLINE-REJECT-BOUNCE-PHASE for full-history validation. THIS script is
that validation, generalized per the task's SCOPE REFINEMENT: rather than inventing an
ex-ante "bounce phase" classifier (the day-type trend/chop classifier already FAILED
2026-07-15, analysis/recommendations/daytype-gate-result.md -- 3/3 variants KILL, p_null
0.58-0.99), the lever is defined structurally and provably ex-ante:

LEVER: gate ALL BEAR-side (PUT) ELITE-tier entries of BEARISH_REJECTION_RIDE_THE_RIBBON /
BULLISH_RECLAIM_RIDE_THE_RIBBON. "ELITE" (backtest/lib/orchestrator.py:1186-1189) requires
`has_confluence` (confluence trigger) OR `has_sequence` (sequence_rejection trigger) OR
both -- and BOTH of those are, by construction, IMPOSSIBLE without a matched static price
level: `detect_confluence(rejection_level, ...)` (lib/filters.py:741) returns None whenever
`rejection_level is None`, and `sequence_rejected` is only computed from a `level_state`
looked up FROM `rejection_level` (lib/filters.py:1390-1398, mirrored bull-side 1124-1131).
So "ELITE-tier bear entry" and "static-level-anchored bear entry with a confirming
trigger" are the SAME set, not an approximation of it -- zero invented proxy, zero
lookahead (every field used is known at signal time), zero day-level classification.

This is also the precise structural mirror of an already-LIVE, already-ratified gate:
`block_elite_bull` (params.json, VIX[0,25) i.e. effectively unconditional) already blocks
ELITE-tier BULL (CALL) entries. There is currently NO bear-side equivalent -- this study
tests completing that symmetric pair, not inventing a new gate class.

CANDIDATE: block ELITE-tier PUT entries (post-hoc trade removal, matching the established
`block_level_rejection` precedent's own validation methodology -- level_rejection_gate_sweep.py
mines a real production gate exactly this way before it was ever wired).
CONTROL: current production Safe config (block_elite_bull ON, block_level_rejection ON
[LEVEL tier only -- this is precisely the gap ELITE-tier trades fall through today],
entry_bar_body_pct_min 0.2, block_bull_1100_1200 ON, vix_bear_hard_cap 23.0, chart-stop-
primary -50% catastrophe caps both sides, tp1_qty_fraction 0.8, profit_lock fixed arm+5%,
strike ATM (V15_SAFE_TIERS <$10K), real OPRA fills).

WF form: analysis/recommendations/WF-GATE-METHODOLOGY-2026-07-16.md
`ab_delta_per_trade_v2026_07_16` (+ AMENDMENT 1). IS=2025 calendar year, OOS=2026 YTD
(through 2026-07-08, the latest date with a matched spy_5m/vix_5m file pair -- 6+ months
OOS). Reports the gate-cohort-normalized WF (n = count of the affected/removed ELITE-bear
trades, matching directional_gate_battery.py's compute_wf/G3 convention -- the closer
structural analog, since this IS a single-gate block study) AND, disclosed, the
full-population-normalized alternative (n = all control trades that period, matching
level_rejection_gate_sweep.py's own convention) -- both forms are live in this codebase,
neither superseded the other in the frozen note, so both are reported per the note's own
"state the WF form used" mandatory disclosure.

5 ratification gates + BH-FDR (single candidate -- degenerates to a plain one-sided
threshold at alpha=0.10, disclosed, not hidden) + anchor (OP-16 J_WINNERS/J_LOSERS,
lib.anchor_check) + sub-window stability + a random-removal placebo null (20 seeds,
same-count random PUT-trade removal, add-one empirical p_null -- the WF-GATE note's
"control sanity" disclosure applied to a gate study) + drop-top-3 concentration check
(fable-too-good hunt).

Run: backtest/.venv/Scripts/python.exe backtest/tools/elite_bear_level_reject_gate_ab.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import pandas as pd  # noqa: E402

from lib.orchestrator import run_backtest  # noqa: E402
from lib.anchor_check import anchor_no_regression  # noqa: E402
from autoresearch.j_edge_tracker import J_WINNERS, J_LOSERS  # noqa: E402

DATA = REPO / "data"
SPY_FILE = DATA / "spy_5m_2025-01-01_2026-07-08.csv"
VIX_FILE = DATA / "vix_5m_2025-01-01_2026-07-08.csv"

OUT_JSON = REPO.parent / "analysis" / "recommendations" / "elite-bear-level-reject-gate-ab-2026-07-17.json"
OUT_MD = REPO.parent / "analysis" / "recommendations" / "elite-bear-level-reject-gate-ab-2026-07-17.md"

IS_START, IS_END = dt.date(2025, 1, 2), dt.date(2025, 12, 31)
OOS_START, OOS_END = dt.date(2026, 1, 2), dt.date(2026, 7, 8)

IS_SUB_WINDOWS = [
    ("IS_H1_2025", dt.date(2025, 1, 2), dt.date(2025, 6, 30)),
    ("IS_H2_2025", dt.date(2025, 7, 1), dt.date(2025, 12, 31)),
]
OOS_SUB_WINDOWS = [
    ("OOS_Q1_2026", dt.date(2026, 1, 2), dt.date(2026, 3, 31)),
    ("OOS_Q2_2026", dt.date(2026, 4, 1), dt.date(2026, 6, 30)),
    ("OOS_Q3_2026_partial", dt.date(2026, 7, 1), dt.date(2026, 7, 8)),
]

ANCHOR_WIN_DATES = {t["date"] for t in J_WINNERS}
ANCHOR_LOSE_DATES = {t["date"] for t in J_LOSERS}

BH_ALPHA = 0.10
N_NULL_SEEDS = 20

# =============================================================================
# FAITHFUL CURRENT-PRODUCTION SAFE CONFIG (automation/state/params.json, read 2026-07-17
# after-hours; live-verified equity $1,724.53 mcp__alpaca__get_account_info PA3DHPT7KIQE).
# Hand-built (not auto-loaded via runner.run_with_params) because that helper's
# direct_passthrough allowlist does not cover several live keys (profit_lock_mode/trail,
# strike tier, min_premium_for_level_tiers) -- same reason every prior ratified-gate
# sweep in this codebase (elite_subtier_sweep.py, level_rejection_gate_sweep.py,
# safe_quality_sizing_ab.py) hand-builds its own BASE dict rather than round-tripping
# params.json. Departs from those OLDER dicts where production doctrine has since moved
# (v15.1 removed the 11:30-12:00 blackout and added a 15:00 ET entry cutoff instead;
# 2026-06-18 moved premium stops to -50% catastrophe caps under chart-stop-primary;
# tp1_qty_fraction raised 0.667->0.8 on Safe 2026-06-28) -- each divergence is cited
# inline against its params.json source line.
# =============================================================================
SAFE_BASE = dict(
    use_real_fills=True,
    strike_offset=0,                              # V15_SAFE_TIERS ATM <$10K (crypto/lib/strike_selection.py)
    premium_stop_pct_bear=-0.50, premium_stop_pct_bull=-0.50,  # params.json premium_stop_pct(_bear) -0.5, chart-stop-primary catastrophe cap
    tp1_premium_pct=0.5, tp1_qty_fraction=0.8,     # params.json tp1_premium_pct 0.5, tp1_qty_fraction 0.8 (Safe, raised 2026-06-28)
    runner_target_premium_pct=2.5,                 # params.json runner_max_premium_pct 2.5
    level_stop_buffer_dollars=0.5,                 # params.json chart_stop_buffer_dollars 0.5
    time_stop_minutes_before_close=20,             # params.json time_stop_et "15:40"
    profit_lock_threshold_pct=0.05,                # params.json v15_profit_lock_threshold_pct
    profit_lock_stop_offset_pct=0.0,                # absent from params.json -> default 0.0 (never wired live, per iteration-3 finding)
    profit_lock_mode="fixed",                       # params.json v15_profit_lock_mode (orchestrator default already matches)
    profit_lock_trail_pct=0.125,                    # params.json v15_profit_lock_trail_pct (unused while mode=fixed; passed for disclosure)
    f9_vol_mult=0.7,                                # params.json filter_9_vol_multiplier
    min_triggers_bear=1, min_triggers_bull=2,       # params.json filter_10_min_triggers_bear/bull
    no_trade_before=dt.time(9, 35),                 # params.json entry_no_trade_before_et
    no_trade_window=(dt.time(15, 0), dt.time(16, 0)),  # v15.1 entry cutoff: params.json entry_no_trade_after_et "15:00" (mapped to a blackout-to-close window; orchestrator has no separate "after" kwarg)
    block_level_rejection=True,                     # params.json block_level_rejection (LEVEL tier only -- the gap this study targets)
    block_elite_bull=True, block_elite_bull_vix_low=0.0, block_elite_bull_vix_high=25.0,  # params.json block_elite_bull + vix band (2026-06-18 extension)
    entry_bar_body_pct_min=0.2,                     # params.json entry_bar_body_pct_min
    block_bull_1100_1200=True,                      # params.json block_bull_1100_1200
    midday_trendline_gate=False,                    # params.json midday_trendline_gate (Gate C, currently off)
    min_ribbon_momentum_cents=None,                 # params.json min_ribbon_momentum_cents null (Gate A disabled)
    max_ribbon_duration_bars=999,                   # params.json max_ribbon_duration_bars 999 (Gate B disabled)
    vix_bear_hard_cap=23.0,                          # params.json vix_bear_hard_cap
    per_trade_risk_cap_pct=0.30,                     # Rule 6, Safe
    enable_bullish=True,                             # params.json enable_bullish / OP-16
    min_premium_for_level_tiers=0.3,                 # params.json min_entry_premium (ENTRY-1 floor; orchestrator only models it for LEVEL+ tiers, disclosed gap -- affects both arms equally)
    initial_equity=1724.53,                          # live-verified 2026-07-17 after-hours, mcp__alpaca__get_account_info
)


def classify_tier(triggers: list[str]) -> str:
    """Matches backtest/lib/orchestrator.py:1186-1219 inline tier logic exactly (also the
    convention independently re-implemented in elite_subtier_sweep.py, level_rejection_gate_sweep.py,
    safe_quality_sizing_ab.py -- consistent across every prior tier study in this codebase)."""
    trig = set(triggers or [])
    has_conf = "confluence" in trig
    has_seq = "sequence_rejection" in trig or "sequence_reclaim" in trig
    has_flip = "ribbon_flip" in trig
    has_level = any(t in ("level_rejection", "level_reclaim") for t in trig)
    has_trendline = "trendline_rejection" in trig
    n = len(trig)
    if (has_conf and has_flip) or n >= 3:
        return "SUPER"
    elif has_conf or has_seq:
        return "ELITE"
    elif has_level:
        return "LEVEL"
    elif has_trendline:
        return "TRENDLINE"
    else:
        return "BASE"


def is_side(t) -> str:
    return str(getattr(t, "side", "P")).upper()


def is_target(t) -> bool:
    """The candidate's blocking predicate: BEAR (PUT) side, ELITE tier."""
    return is_side(t) in ("P", "PUT", "BEAR") and classify_tier(t.triggers_fired) == "ELITE"


def entry_date(t) -> dt.date:
    et = t.entry_time_et
    if hasattr(et, "date"):
        return et.date()
    return dt.date.fromisoformat(str(et)[:10])


def run_period(spy_df, vix_df, start, end):
    return run_backtest(spy_df, vix_df, start_date=start, end_date=end, **SAFE_BASE)


def split_control_candidate(trades):
    removed = [t for t in trades if is_target(t)]
    kept = [t for t in trades if not is_target(t)]
    return removed, kept


def pnl(trades) -> float:
    return round(sum(t.dollar_pnl for t in trades), 2)


def window_delta(all_trades, removed_ids, start, end) -> tuple[float, float, int]:
    """base_pnl, delta, n_removed for one date window (removed_ids = id() set of removed trades)."""
    in_win = [t for t in all_trades if start <= entry_date(t) <= end]
    base = pnl(in_win)
    removed_here = [t for t in in_win if id(t) in removed_ids]
    delta = -pnl(removed_here)
    return base, delta, len(removed_here)


def one_sided_p_mean_gt_0(xs: list[float]):
    n = len(xs)
    if n < 2:
        return None
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    sd = var ** 0.5
    if sd == 0:
        return 0.0 if mean > 0 else 1.0
    t = mean / (sd / math.sqrt(n))
    return 0.5 * math.erfc(t / math.sqrt(2))


def bh_fdr_single(p, alpha=BH_ALPHA):
    """N=1 test: BH-FDR threshold degenerates to alpha*1/1 = alpha (disclosed, not hidden)."""
    if p is None:
        return {"p": None, "threshold": alpha, "significant": False,
                "note": "p undefined (n<2)"}
    return {"p": round(p, 5), "threshold": alpha, "significant": p <= alpha,
            "note": "single-candidate BH-FDR degenerates to a plain one-sided test at alpha"}


def main() -> int:
    print("[elite-bear-gate-ab] loading data...", flush=True)
    spy_df = pd.read_csv(SPY_FILE)
    vix_df = pd.read_csv(VIX_FILE)
    print(f"[elite-bear-gate-ab] spy rows={len(spy_df)} range={spy_df['timestamp_et'].min()}..{spy_df['timestamp_et'].max()}", flush=True)

    print("[elite-bear-gate-ab] running IS 2025...", flush=True)
    is_r = run_period(spy_df, vix_df, IS_START, IS_END)
    print(f"[elite-bear-gate-ab] IS n_trades={len(is_r.trades)}", flush=True)

    print("[elite-bear-gate-ab] running OOS 2026 YTD...", flush=True)
    oos_r = run_period(spy_df, vix_df, OOS_START, OOS_END)
    print(f"[elite-bear-gate-ab] OOS n_trades={len(oos_r.trades)}", flush=True)

    is_removed, is_kept = split_control_candidate(is_r.trades)
    oos_removed, oos_kept = split_control_candidate(oos_r.trades)

    is_base_pnl, oos_base_pnl = pnl(is_r.trades), pnl(oos_r.trades)
    is_cand_pnl, oos_cand_pnl = pnl(is_kept), pnl(oos_kept)
    is_delta = round(is_cand_pnl - is_base_pnl, 2)   # = -pnl(is_removed)
    oos_delta = round(oos_cand_pnl - oos_base_pnl, 2)

    n_is_removed, n_oos_removed = len(is_removed), len(oos_removed)
    n_is_base, n_oos_base = len(is_r.trades), len(oos_r.trades)

    print(f"[elite-bear-gate-ab] IS  base={is_base_pnl:+.0f} removed_n={n_is_removed} removed_pnl={pnl(is_removed):+.0f} delta={is_delta:+.0f}", flush=True)
    print(f"[elite-bear-gate-ab] OOS base={oos_base_pnl:+.0f} removed_n={n_oos_removed} removed_pnl={pnl(oos_removed):+.0f} delta={oos_delta:+.0f}", flush=True)

    # ---- WF, both forms disclosed ----
    def wf_gate_cohort_norm():
        if is_delta == 0 or n_is_removed == 0 or n_oos_removed == 0:
            return None, "N/A structural (is_delta=0 or n_is_removed=0 or n_oos_removed=0)"
        wf = (oos_delta / n_oos_removed) / (is_delta / n_is_removed)
        return round(wf, 3), "gate-cohort-normalized (directional_gate_battery.py convention, n=affected/removed trades)"

    def wf_full_population_norm():
        if is_delta == 0 or n_is_base == 0 or n_oos_base == 0:
            return None, "N/A structural (is_delta=0 or n_is_base=0 or n_oos_base=0)"
        wf = (oos_delta / n_oos_base) / (is_delta / n_is_base)
        return round(wf, 3), "full-population-normalized (level_rejection_gate_sweep.py convention, n=all control trades that period)"

    wf_gate, wf_gate_note = wf_gate_cohort_norm()
    wf_pop, wf_pop_note = wf_full_population_norm()

    # ---- anchor: OP-16 J_WINNERS / J_LOSERS (all in OOS period) ----
    oos_removed_ids = {id(t) for t in oos_removed}
    anchor_base_win = pnl([t for t in oos_r.trades if entry_date(t).isoformat() in ANCHOR_WIN_DATES])
    anchor_cand_win = pnl([t for t in oos_kept if entry_date(t).isoformat() in ANCHOR_WIN_DATES])
    anchor_base_lose = pnl([t for t in oos_r.trades if entry_date(t).isoformat() in ANCHOR_LOSE_DATES])
    anchor_cand_lose = pnl([t for t in oos_kept if entry_date(t).isoformat() in ANCHOR_LOSE_DATES])
    anchor_removed_on_winners = [t for t in oos_removed if entry_date(t).isoformat() in ANCHOR_WIN_DATES]
    anchor_removed_on_losers = [t for t in oos_removed if entry_date(t).isoformat() in ANCHOR_LOSE_DATES]
    anchor_ok_winners = anchor_no_regression(anchor_base_win, anchor_cand_win, tolerance_pct=0.10)
    anchor_ok_losers = (anchor_cand_lose >= anchor_base_lose)  # candidate should not make loser days WORSE either (never blocks a loser->winner flip we'd want)

    # ---- sub-window stability ----
    is_sw_rows, oos_sw_rows = [], []
    n_is_hurt = 0
    for name, s, e in IS_SUB_WINDOWS:
        base, delta, n = window_delta(is_r.trades, {id(t) for t in is_removed}, s, e)
        hurt = delta < 0
        if hurt:
            n_is_hurt += 1
        is_sw_rows.append({"window": name, "base_pnl": base, "delta": round(delta, 2), "n_removed": n, "hurt": hurt})
    n_oos_hurt = 0
    for name, s, e in OOS_SUB_WINDOWS:
        base, delta, n = window_delta(oos_r.trades, oos_removed_ids, s, e)
        hurt = delta < 0
        if hurt:
            n_oos_hurt += 1
        oos_sw_rows.append({"window": name, "base_pnl": base, "delta": round(delta, 2), "n_removed": n, "hurt": hurt})
    sub_window_stable = (n_is_hurt == 0) and (n_oos_hurt <= 1)

    # ---- BH-FDR (single test) on the removed-cohort's OWN pnl (test mean<0 via -pnl mean>0) ----
    oos_removed_neg_pnls = [-t.dollar_pnl for t in oos_removed]
    p_val = one_sided_p_mean_gt_0(oos_removed_neg_pnls)
    bh = bh_fdr_single(p_val)

    # ---- concentration: drop top-3 removed trades by |pnl|, recompute OOS delta ----
    oos_removed_sorted = sorted(oos_removed, key=lambda t: -abs(t.dollar_pnl))
    drop_top3 = oos_removed_sorted[3:]
    oos_delta_drop_top3 = round(-pnl(drop_top3), 2)

    # ---- random-removal placebo null (20 seeds, same-count PUT removal from full control pop) ----
    is_puts = [t for t in is_r.trades if is_side(t) in ("P", "PUT", "BEAR")]
    oos_puts = [t for t in oos_r.trades if is_side(t) in ("P", "PUT", "BEAR")]
    rng = random.Random(20260717)
    null_oos_deltas = []
    for _seed in range(N_NULL_SEEDS):
        if len(oos_puts) >= n_oos_removed and n_oos_removed > 0:
            sample = rng.sample(oos_puts, n_oos_removed)
            null_oos_deltas.append(-pnl(sample))
    if null_oos_deltas:
        n_ge = sum(1 for d in null_oos_deltas if d >= oos_delta)
        p_null = (n_ge + 1) / (len(null_oos_deltas) + 1)
        null_mean = round(sum(null_oos_deltas) / len(null_oos_deltas), 2)
    else:
        p_null, null_mean = None, None

    # ---- 5 gates ----
    g1_oos_positive = oos_delta > 0
    g2_wf = wf_gate is not None and wf_gate >= 0.70
    g3_sub_window_stable = sub_window_stable
    g4_anchor_no_regression = anchor_ok_winners and anchor_ok_losers
    g5_bh_survivor = bh["significant"]
    evidence_n_advisory = n_oos_removed >= 15

    all_5_pass = g1_oos_positive and g2_wf and g3_sub_window_stable and g4_anchor_no_regression and g5_bh_survivor
    if is_delta <= 0 and oos_delta <= 0:
        ladder_verdict = "FAIL"
    elif is_delta <= 0 and oos_delta > 0:
        ladder_verdict = "INSUFFICIENT_REGIME_SHIFT"
    elif g2_wf:
        ladder_verdict = "PASS" if all_5_pass else "FAIL"
    else:
        ladder_verdict = "FAIL"

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "wf_form": "ab_delta_per_trade_v2026_07_16",
        "candidate": "block BEAR-side (PUT) ELITE-tier entries of ribbon_ride (BEARISH_REJECTION/BULLISH_RECLAIM) -- structural mirror of live block_elite_bull",
        "control": "current production Safe config (SAFE_BASE dict, faithful to automation/state/params.json read 2026-07-17)",
        "data": {"spy_file": SPY_FILE.name, "vix_file": VIX_FILE.name,
                  "is_window": [str(IS_START), str(IS_END)], "oos_window": [str(OOS_START), str(OOS_END)]},
        "is": {"base_pnl": is_base_pnl, "n_base": n_is_base, "n_removed": n_is_removed,
               "removed_pnl": pnl(is_removed), "candidate_pnl": is_cand_pnl, "delta": is_delta},
        "oos": {"base_pnl": oos_base_pnl, "n_base": n_oos_base, "n_removed": n_oos_removed,
                "removed_pnl": pnl(oos_removed), "candidate_pnl": oos_cand_pnl, "delta": oos_delta},
        "wf_gate_cohort_normalized": {"value": wf_gate, "note": wf_gate_note},
        "wf_full_population_normalized": {"value": wf_pop, "note": wf_pop_note},
        "sub_window_stability": {"is_windows": is_sw_rows, "oos_windows": oos_sw_rows,
                                  "n_is_hurt": n_is_hurt, "n_oos_hurt": n_oos_hurt, "stable": sub_window_stable},
        "anchor": {
            "j_winners_dates": sorted(ANCHOR_WIN_DATES), "j_losers_dates": sorted(ANCHOR_LOSE_DATES),
            "base_pnl_on_winner_days": anchor_base_win, "candidate_pnl_on_winner_days": anchor_cand_win,
            "base_pnl_on_loser_days": anchor_base_lose, "candidate_pnl_on_loser_days": anchor_cand_lose,
            "n_removed_on_winner_days": len(anchor_removed_on_winners),
            "n_removed_on_loser_days": len(anchor_removed_on_losers),
            "anchor_no_regression_winners": anchor_ok_winners,
            "anchor_no_regression_losers_not_worsened": anchor_ok_losers,
        },
        "bh_fdr": bh,
        "concentration_check": {
            "oos_removed_trades_sorted_by_abs_pnl": [
                {"date": entry_date(t).isoformat(), "pnl": t.dollar_pnl} for t in oos_removed_sorted[:5]
            ],
            "oos_delta_excluding_top3_by_magnitude": oos_delta_drop_top3,
            "still_positive_ex_top3": oos_delta_drop_top3 > 0,
        },
        "random_removal_placebo_null": {
            "n_seeds": N_NULL_SEEDS, "seed_base": 20260717,
            "null_oos_delta_mean": null_mean, "real_oos_delta": oos_delta,
            "p_null_add_one": round(p_null, 4) if p_null is not None else None,
            "note": "20 seeds, same-count random PUT-trade removal from the full OOS control population (any tier) -- tests whether removing ANY n_oos_removed put trades looks this good, or whether the ELITE-tier selection specifically matters.",
        },
        "gates": {
            "1_oos_positive": g1_oos_positive,
            "2_wf_ge_070_gate_cohort_form": g2_wf,
            "3_sub_window_stable": g3_sub_window_stable,
            "4_anchor_no_regression": g4_anchor_no_regression,
            "5_bh_fdr_survivor": g5_bh_survivor,
            "evidence_n_advisory_pass": evidence_n_advisory,
        },
        "verdict_ladder": ladder_verdict,
        "all_5_gates_pass": all_5_pass,
        "final_verdict": "SHIP" if (all_5_pass and ladder_verdict == "PASS") else ("PARK_INSUFFICIENT_REGIME_SHIFT" if ladder_verdict == "INSUFFICIENT_REGIME_SHIFT" else "NO_SHIP"),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\n[elite-bear-gate-ab] wrote {OUT_JSON}", flush=True)

    write_markdown(out)
    print(f"[elite-bear-gate-ab] wrote {OUT_MD}", flush=True)

    print("\n[elite-bear-gate-ab] ==== VERDICT ====", flush=True)
    print(json.dumps(out["gates"], indent=2), flush=True)
    print(f"Ladder: {ladder_verdict}  All-5: {all_5_pass}  FINAL: {out['final_verdict']}", flush=True)
    return 0


def write_markdown(out: dict) -> None:
    lines = []
    lines.append("# ELITE-tier BEAR level-rejection gate -- OOS A/B (GOAL-REPLAY-TODAY-GREEN iter 4, L1)")
    lines.append("")
    lines.append(f"Generated: {out['generated_at']}. Runner: `backtest/tools/elite_bear_level_reject_gate_ab.py`.")
    lines.append(f"WF form: `{out['wf_form']}` (analysis/recommendations/WF-GATE-METHODOLOGY-2026-07-16.md).")
    lines.append("")
    lines.append(f"**Candidate:** {out['candidate']}")
    lines.append(f"**Control:** {out['control']}")
    lines.append("")
    lines.append(f"IS window {out['data']['is_window']}, OOS window {out['data']['oos_window']} "
                 f"({out['data']['spy_file']} / {out['data']['vix_file']}).")
    lines.append("")
    lines.append("## Per-period")
    lines.append("")
    lines.append("| period | base pnl | n_base | n_removed | removed pnl | candidate pnl | delta |")
    lines.append("|---|--:|--:|--:|--:|--:|--:|")
    for label, d in (("IS 2025", out["is"]), ("OOS 2026 YTD", out["oos"])):
        lines.append(f"| {label} | ${d['base_pnl']:,.0f} | {d['n_base']} | {d['n_removed']} | "
                     f"${d['removed_pnl']:,.0f} | ${d['candidate_pnl']:,.0f} | ${d['delta']:+,.0f} |")
    lines.append("")
    lines.append(f"WF (gate-cohort norm): **{out['wf_gate_cohort_normalized']['value']}** ({out['wf_gate_cohort_normalized']['note']})")
    lines.append("")
    lines.append(f"WF (full-population norm, disclosed alt): {out['wf_full_population_normalized']['value']} ({out['wf_full_population_normalized']['note']})")
    lines.append("")
    lines.append("## Gates")
    lines.append("")
    for k, v in out["gates"].items():
        lines.append(f"- `{k}`: **{v}**")
    lines.append("")
    lines.append(f"BH-FDR: p={out['bh_fdr'].get('p')}, threshold={out['bh_fdr'].get('threshold')}, "
                 f"significant={out['bh_fdr'].get('significant')} -- {out['bh_fdr'].get('note')}")
    lines.append("")
    lines.append("## Anchor (OP-16 J_WINNERS / J_LOSERS)")
    lines.append("")
    a = out["anchor"]
    lines.append(f"- Winner days: base=${a['base_pnl_on_winner_days']:,.0f} candidate=${a['candidate_pnl_on_winner_days']:,.0f} "
                 f"(n_removed={a['n_removed_on_winner_days']}) -- anchor_no_regression={a['anchor_no_regression_winners']}")
    lines.append(f"- Loser days: base=${a['base_pnl_on_loser_days']:,.0f} candidate=${a['candidate_pnl_on_loser_days']:,.0f} "
                 f"(n_removed={a['n_removed_on_loser_days']}) -- not_worsened={a['anchor_no_regression_losers_not_worsened']}")
    lines.append("")
    lines.append("## Sub-window stability")
    lines.append("")
    lines.append("| window | base pnl | delta | n_removed | hurt |")
    lines.append("|---|--:|--:|--:|:--:|")
    for row in out["sub_window_stability"]["is_windows"] + out["sub_window_stability"]["oos_windows"]:
        lines.append(f"| {row['window']} | ${row['base_pnl']:,.0f} | ${row['delta']:+,.0f} | {row['n_removed']} | {row['hurt']} |")
    lines.append("")
    lines.append("## Concentration check (fable-too-good hunt)")
    lines.append("")
    c = out["concentration_check"]
    lines.append(f"Top-5 OOS removed trades by |pnl|: {c['oos_removed_trades_sorted_by_abs_pnl']}")
    lines.append(f"OOS delta excluding top-3 by magnitude: ${c['oos_delta_excluding_top3_by_magnitude']:+,.0f} "
                 f"(still positive: {c['still_positive_ex_top3']})")
    lines.append("")
    lines.append("## Random-removal placebo null")
    lines.append("")
    n = out["random_removal_placebo_null"]
    lines.append(f"{n['n_seeds']} seeds, same-count random PUT removal. Null mean OOS delta=${n['null_oos_delta_mean']}, "
                 f"real candidate OOS delta=${n['real_oos_delta']}, p_null(add-one)={n['p_null_add_one']}.")
    lines.append(f"{n['note']}")
    lines.append("")
    lines.append(f"## VERDICT: {out['verdict_ladder']} (all-5-gates={out['all_5_gates_pass']}) -- **{out['final_verdict']}**")
    lines.append("")
    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

"""Guard for late_entry_ceiling_realfills.py (Q2 forensic, 2026-07-23): episode-grouping
logic (group_episodes -- <=3min gap, per-account separation), the compute_verdict
operationalization of the frozen pre-reg's 'clearly positive'/'negative or flat' prose, and
the live entry_no_trade_after_et / time_stop_et guards this study's methodology depends on.
The shared replay core (exit_manager.plan_exit_actions via walk_exit_manager) is covered
elsewhere in this codebase.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "tools"))

import late_entry_ceiling_realfills as le  # noqa: E402


# ---------------------------------------------------------------------------------------------
# group_episodes -- <=3min same-account collapse; different accounts never merge
# ---------------------------------------------------------------------------------------------
def _row(ts, account, spy=700.0, trigger=None):
    return {"ts": ts, "account": account, "spy": spy, "trigger_level": trigger}


def test_group_episodes_collapses_within_3min_same_account():
    rows = [_row("2026-07-01T15:36:03", "safe"), _row("2026-07-01T15:37:03", "safe"),
            _row("2026-07-01T15:38:03", "safe")]
    eps = le.group_episodes(rows)
    assert len(eps) == 1
    assert eps[0]["n_fires"] == 3


def test_group_episodes_splits_on_gap_over_3min():
    rows = [_row("2026-07-01T15:36:03", "safe"), _row("2026-07-01T15:40:04", "safe")]
    eps = le.group_episodes(rows)
    assert len(eps) == 2, "180s+ gap must start a NEW episode, not extend the old one"


def test_group_episodes_exactly_3min_gap_still_same_episode():
    rows = [_row("2026-07-01T15:36:00", "safe"), _row("2026-07-01T15:39:00", "safe")]
    eps = le.group_episodes(rows)
    assert len(eps) == 1, "exactly 180s must still count as <=3min (inclusive boundary)"


def test_group_episodes_never_merges_across_accounts():
    rows = [_row("2026-07-01T15:36:03", "safe"), _row("2026-07-01T15:36:04", "bold")]
    eps = le.group_episodes(rows)
    assert len(eps) == 2
    assert {e["account"] for e in eps} == {"safe", "bold"}


def test_group_episodes_carries_first_recovered_trigger_level():
    rows = [_row("2026-07-01T15:36:03", "safe", trigger=None),
            _row("2026-07-01T15:37:03", "safe", trigger=737.68),
            _row("2026-07-01T15:38:03", "safe", trigger=None)]
    eps = le.group_episodes(rows)
    assert eps[0]["trigger_level"] == 737.68


# ---------------------------------------------------------------------------------------------
# compute_verdict -- operationalizes the pre-reg's KEEP/MOVE_TO_X/RETEST_INSUFFICIENT_N prose
# ---------------------------------------------------------------------------------------------
def _replayed(n, pnl_each, win_frac=None, base_date="2026-07-01"):
    """n rows, each with the SAME date+time (so n_distinct_signal_buckets==1) unless caller
    varies it -- tests should construct their own distinct-bucket spread where relevant."""
    out = []
    for i in range(n):
        d = f"2026-07-{(i % 28) + 1:02d}"
        out.append({"pnl": pnl_each, "date": d, "episode_first_block_et": f"{d}T15:3{i%6}:00"})
    return out


def test_compute_verdict_insufficient_n_below_floor():
    rows = _replayed(5, 100.0)
    v = le.compute_verdict(rows)
    assert v["verdict"] == "RETEST_INSUFFICIENT_N"
    assert v["n"] == 5


def test_compute_verdict_keep_when_negative():
    rows = _replayed(20, -10.0)
    v = le.compute_verdict(rows)
    assert v["total_pnl"] < 0
    assert v["verdict"] == "KEEP"


def test_compute_verdict_keep_when_flat_and_not_significant():
    """Reproduces the actual 2026-07-23 real-run shape: small positive aggregate, low
    win rate, high p-value -> KEEP, not MOVE_TO_X, even though the raw sign is positive."""
    rows = []
    # 16 distinct-bucket losers of -20, 5 distinct-bucket winners of +150 -> positive aggregate,
    # win_rate well under 0.45, large spread -> p should NOT clear 0.25
    for i in range(16):
        d = f"2026-06-{i+1:02d}"
        rows.append({"pnl": -20.0, "date": d, "episode_first_block_et": f"{d}T15:36:00"})
    for i in range(5):
        d = f"2026-07-{i+1:02d}"
        rows.append({"pnl": 150.0, "date": d, "episode_first_block_et": f"{d}T15:36:00"})
    v = le.compute_verdict(rows)
    assert v["total_pnl"] > 0
    assert v["win_rate"] < 0.45
    assert v["verdict"] == "KEEP", "positive sign alone must not be enough to MOVE_TO_X"


def test_compute_verdict_move_to_x_when_clearly_positive():
    rows = []
    for i in range(20):
        d = f"2026-06-{i+1:02d}"
        rows.append({"pnl": 50.0 + i, "date": d, "episode_first_block_et": f"{d}T15:36:00"})
    v = le.compute_verdict(rows)
    assert v["win_rate"] == 1.0
    assert v["verdict"] == "MOVE_TO_X"


def test_compute_verdict_distinct_signal_bucket_floor_overrides_raw_n():
    """21 raw legs but only e.g. 10 distinct (date,time) buckets (heavily mirrored across
    accounts) must still count as insufficient-n on the DISTINCT-signal basis."""
    rows = []
    for i in range(21):
        bucket = i % 10  # only 10 distinct buckets no matter how many raw legs
        d = f"2026-07-{bucket+1:02d}"
        rows.append({"pnl": 10.0, "date": d, "episode_first_block_et": f"{d}T15:36:00"})
    v = le.compute_verdict(rows)
    assert v["n"] == 21
    assert v["n_distinct_date_time_signal_buckets"] == 10
    assert v["verdict"] == "RETEST_INSUFFICIENT_N"


def test_one_sided_p_mean_gt_0_none_below_n2():
    assert le.one_sided_p_mean_gt_0([5.0]) is None
    assert le.one_sided_p_mean_gt_0([]) is None


def test_one_sided_p_mean_gt_0_small_for_strongly_positive():
    xs = [10.0, 12.0, 11.0, 9.0, 13.0, 10.5, 11.5]
    p = le.one_sided_p_mean_gt_0(xs)
    assert p is not None and p < 0.01


def test_one_sided_p_mean_gt_0_large_for_negative_sample():
    xs = [-10.0, -12.0, -11.0, -9.0]
    p = le.one_sided_p_mean_gt_0(xs)
    assert p is not None and p > 0.9, "mean is strongly negative -> p(mean>0) must be near 1"


# ---------------------------------------------------------------------------------------------
# LIVE-VALUE GUARDS -- this study's methodology depends on these staying put
# ---------------------------------------------------------------------------------------------
def test_time_stop_et_matches_live_params():
    assert le.TIME_STOP_ET == dt.time(15, 40)


def test_live_entry_no_trade_after_et_still_15_00_both_accounts():
    """The gate under review must not have moved out from under this study without a fresh
    pre-registration -- mirrors test_money_path_2026_07_01.py::TestEntryCeiling's own guard."""
    for rel in ("automation/state/params.json", "automation/state/aggressive/params.json"):
        p = REPO / rel
        d = json.loads(p.read_text(encoding="utf-8"))
        assert d["entry_no_trade_after_et"] == "15:00", f"{rel} drifted from 15:00"
        assert d["time_stop_et"] == "15:40", f"{rel} time_stop_et drifted from 15:40"


# ---------------------------------------------------------------------------------------------
# FROZEN pre-registration -- episode population hash must still match what's on disk
# ---------------------------------------------------------------------------------------------
def test_prereg_file_exists_and_pins_expected_shape():
    prereg_path = REPO / "analysis" / "recommendations" / "late-entry-ceiling-realfills-prereg-2026-07-23.json"
    assert prereg_path.exists()
    preg = json.loads(prereg_path.read_text(encoding="utf-8"))
    assert preg["version"] == 1
    assert preg["population"]["n_episodes"] == 21
    assert preg["verdict_rule"]["options"] == ["KEEP", "MOVE_TO_X", "RETEST_INSUFFICIENT_N"]


def test_real_run_output_matches_disclosed_verdict_vocabulary():
    out_path = REPO / "analysis" / "recommendations" / "late-entry-ceiling-realfills-2026-07-23.json"
    if not out_path.exists():
        return
    d = json.loads(out_path.read_text(encoding="utf-8"))
    assert d["verdict"] in ("KEEP", "MOVE_TO_X", "RETEST_INSUFFICIENT_N")
    assert d["population"]["n_excluded"] == 0
    # sanity: per-account totals must sum to the headline total
    acct_total = round(sum(v["total_pnl"] for v in d["per_account"].values()), 2)
    assert acct_total == d["headline"]["total_pnl"]

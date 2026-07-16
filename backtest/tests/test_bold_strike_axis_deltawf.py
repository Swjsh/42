"""Guard: bold_strike_axis_deltawf.py's delta-WF computation (2026-07-16).

Pins the frozen Option-B form from analysis/recommendations/WF-GATE-METHODOLOGY-2026-07-16.md
("A/B-delta WF, per-trade normalized") against a SYNTHETIC fixture with known is/oos deltas ->
known WF_delta + known 4-rung verdict-ladder outcome, so a future edit to compute_delta_wf() or
ladder_verdict() that silently changes the gate's math gets caught immediately -- no OPRA data,
no network, no real cohort, pure arithmetic on hand-built episode-outcome dicts.

Covers ALL 4 verdict-ladder rungs (per the frozen methodology note):
  1. is_delta_mean > 0  and WF_delta >= 0.70            -> PASS
  2. is_delta_mean > 0  and WF_delta <  0.70             -> FAIL
  3. is_delta_mean <= 0 and oos_delta_mean <= 0          -> FAIL
  4. is_delta_mean <= 0 and oos_delta_mean >  0          -> INSUFFICIENT_REGIME_SHIFT

Plus: the mandatory control-sanity cell (candidate==control -> every delta is exactly 0, ladder
must degenerate to FAIL, never a false PASS), the WF>=0.70 boundary itself, the "only one side
trades" pairing rule (untraded side enters at pnl=0), and the reproduction_check() diff helper
this script uses to prove its replay reproduces bold-strike-axis-2026-07-15.json's own numbers.

Run: backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_bold_strike_axis_deltawf.py
"""
from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
_TOOLS = BACKTEST / "tools"
_FLEET = ROOT / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(ROOT), str(_TOOLS), str(_FLEET)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bold_strike_axis_deltawf as dwf  # noqa: E402

IS_DATE = dt.date(2025, 6, 1)     # < OOS_BOUNDARY (2026-01-01) -- IS
OOS_DATE = dt.date(2026, 2, 1)    # >= OOS_BOUNDARY -- OOS


def _mk_outcomes(cand_pnls_is: list[float], cand_pnls_oos: list[float],
                 ctrl_pnls_is: list[float] | None = None,
                 ctrl_pnls_oos: list[float] | None = None) -> tuple[dict, dict]:
    """Builds (cand_outcomes, ctrl_outcomes) episode dicts. Default: control never trades any
    episode (pnl=0 via traded=False) -- the simplest way to make delta_i == cand_pnl_i directly,
    matching the methodology's 'only one side trades -> that side's pnl, other side 0' rule."""
    n_is, n_oos = len(cand_pnls_is), len(cand_pnls_oos)
    ctrl_is = ctrl_pnls_is if ctrl_pnls_is is not None else [0.0] * n_is
    ctrl_oos = ctrl_pnls_oos if ctrl_pnls_oos is not None else [0.0] * n_oos
    ctrl_is_traded = ctrl_pnls_is is not None
    ctrl_oos_traded = ctrl_pnls_oos is not None
    cand, ctrl = {}, {}
    idx = 0
    for p in cand_pnls_is:
        cand[idx] = {"pnl": p, "date": IS_DATE, "traded": True, "skip_reason": None}
        ctrl[idx] = {"pnl": ctrl_is[idx], "date": IS_DATE, "traded": ctrl_is_traded, "skip_reason": None}
        idx += 1
    for p in cand_pnls_oos:
        local_idx = idx - n_is
        cand[idx] = {"pnl": p, "date": OOS_DATE, "traded": True, "skip_reason": None}
        ctrl[idx] = {"pnl": ctrl_oos[local_idx], "date": OOS_DATE, "traded": ctrl_oos_traded, "skip_reason": None}
        idx += 1
    return cand, ctrl


# =================================================================================================
# 1. LADDER RUNG 1 -- PASS (is_delta_mean > 0, WF_delta >= 0.70)
# =================================================================================================
def test_ladder_pass_is_positive_wf_above_bar():
    cand, ctrl = _mk_outcomes(cand_pnls_is=[10.0, 10.0, 10.0, 10.0], cand_pnls_oos=[8.0, 8.0, 8.0, 8.0])
    r = dwf.compute_delta_wf(cand, ctrl)
    assert r["is_delta_mean"] == 10.0
    assert r["oos_delta_mean"] == 8.0
    assert r["wf_delta"] == 0.8            # (8/4)/(10/4) = 0.8 >= 0.70
    assert r["ladder_verdict"] == "PASS"
    assert r["gate_pass"] is True


def test_ladder_verdict_direct_pass():
    assert dwf.ladder_verdict(10.0, 8.0, 0.8) == "PASS"


def test_wf_exactly_at_070_bar_passes():
    """Boundary: WF_delta == 0.70 exactly must PASS (frozen form is >=, not >)."""
    assert dwf.ladder_verdict(10.0, 7.0, 0.70) == "PASS"


# =================================================================================================
# 2. LADDER RUNG 2 -- FAIL (is_delta_mean > 0, WF_delta < 0.70)
# =================================================================================================
def test_ladder_fail_is_positive_wf_below_bar():
    cand, ctrl = _mk_outcomes(cand_pnls_is=[10.0, 10.0, 10.0, 10.0], cand_pnls_oos=[5.0, 5.0, 5.0, 5.0])
    r = dwf.compute_delta_wf(cand, ctrl)
    assert r["is_delta_mean"] == 10.0
    assert r["wf_delta"] == 0.5             # (5/4)/(10/4) = 0.5 < 0.70
    assert r["ladder_verdict"] == "FAIL"
    assert r["gate_pass"] is False


def test_wf_just_below_070_bar_fails():
    assert dwf.ladder_verdict(10.0, 6.999, 0.6999) == "FAIL"


# =================================================================================================
# 3. LADDER RUNG 3 -- FAIL (is_delta_mean <= 0, oos_delta_mean <= 0): candidate never improved
# =================================================================================================
def test_ladder_fail_is_negative_oos_negative():
    cand, ctrl = _mk_outcomes(cand_pnls_is=[-5.0, -5.0], cand_pnls_oos=[-3.0, -3.0])
    r = dwf.compute_delta_wf(cand, ctrl)
    assert r["is_delta_mean"] == -5.0
    assert r["oos_delta_mean"] == -3.0
    assert r["wf_delta"] is None            # is_delta_mean <= 0 -> never divides
    assert r["ladder_verdict"] == "FAIL"
    assert r["gate_pass"] is False


def test_ladder_verdict_direct_both_negative():
    assert dwf.ladder_verdict(-5.0, -3.0, None) == "FAIL"


def test_ladder_fail_is_exactly_zero_oos_zero():
    """is_delta_mean == 0 is <=0 by the frozen form -- must NOT be treated as PASS-eligible."""
    assert dwf.ladder_verdict(0.0, 0.0, None) == "FAIL"


# =================================================================================================
# 4. LADDER RUNG 4 -- INSUFFICIENT_REGIME_SHIFT (is_delta_mean <= 0, oos_delta_mean > 0)
# =================================================================================================
def test_ladder_insufficient_regime_shift():
    cand, ctrl = _mk_outcomes(cand_pnls_is=[-5.0, -5.0], cand_pnls_oos=[8.0, 8.0])
    r = dwf.compute_delta_wf(cand, ctrl)
    assert r["is_delta_mean"] == -5.0
    assert r["oos_delta_mean"] == 8.0
    assert r["wf_delta"] is None
    assert r["ladder_verdict"] == "INSUFFICIENT_REGIME_SHIFT"
    assert r["gate_pass"] is False           # parked, never auto-passes


def test_ladder_verdict_direct_regime_shift():
    assert dwf.ladder_verdict(-1.0, 0.01, None) == "INSUFFICIENT_REGIME_SHIFT"


def test_this_run_reproduces_bold_atm_regime_shift_finding():
    """Live-data regression pin: the 2026-07-16 real run found ATM/OTM-1/ITM-1/ITM-2 ALL land in
    INSUFFICIENT_REGIME_SHIFT vs OTM-3 (Bold's IS 2025 window is worse than OTM-3 for every
    candidate; the 2026 OOS recovery is what drives the original near-miss). This unit test pins
    the SHAPE of that finding (is<=0, oos>0 -> parked, not PASS) using the exact numbers recorded
    in the real scorecard, independent of re-fetching OPRA data."""
    # analysis/recommendations/bold-strike-axis-deltawf-readjudication-2026-07-16.json, ATM cell
    assert dwf.ladder_verdict(-0.6295, 35.9534, None) == "INSUFFICIENT_REGIME_SHIFT"
    # ITM-2 cell -- largest-magnitude IS drag among the 4 candidates
    assert dwf.ladder_verdict(-47.3684, 87.0189, None) == "INSUFFICIENT_REGIME_SHIFT"


# =================================================================================================
# 5. CONTROL-SANITY CELL -- candidate == control must degenerate, never false-PASS
# =================================================================================================
def test_control_sanity_self_comparison_degenerates_to_fail():
    cand, ctrl = _mk_outcomes(cand_pnls_is=[10.0, -20.0, 5.0], cand_pnls_oos=[8.0, -3.0])
    # Point control at the SAME dict object contents as candidate -> every delta is exactly 0.
    ctrl_self = {i: dict(v) for i, v in cand.items()}
    r = dwf.compute_delta_wf(cand, ctrl_self)
    assert r["is_delta_mean"] == 0.0
    assert r["oos_delta_mean"] == 0.0
    assert r["wf_delta"] is None
    assert r["ladder_verdict"] == "FAIL"     # never a false PASS on a self-comparison
    assert r["gate_pass"] is False


# =================================================================================================
# 6. PAIRING RULE -- "episodes where only one side trades enter its side at pnl, other side at 0"
# =================================================================================================
def test_pairing_candidate_only_trades():
    """Candidate trades, control does not (floor-skip) -> delta = candidate pnl - 0."""
    cand = {0: {"pnl": 12.0, "date": IS_DATE, "traded": True, "skip_reason": None}}
    ctrl = {0: {"pnl": 0.0, "date": IS_DATE, "traded": False, "skip_reason": "floor_skip"}}
    r = dwf.compute_delta_wf(cand, ctrl)
    assert r["n_shared_episodes"] == 1
    assert r["n_cand_only"] == 1
    assert r["n_ctrl_only"] == 0
    assert r["is_delta_sum"] == 12.0


def test_pairing_control_only_trades():
    """Control trades, candidate does not -> delta = 0 - control pnl (negative for candidate)."""
    cand = {0: {"pnl": 0.0, "date": IS_DATE, "traded": False, "skip_reason": "no_local_bars"}}
    ctrl = {0: {"pnl": 20.0, "date": IS_DATE, "traded": True, "skip_reason": None}}
    r = dwf.compute_delta_wf(cand, ctrl)
    assert r["n_ctrl_only"] == 1
    assert r["n_cand_only"] == 0
    assert r["is_delta_sum"] == -20.0


def test_pairing_neither_trades_excluded_from_shared_set():
    """Neither side trades -> episode contributes nothing and is excluded from the shared set
    entirely (delta=0 either way, but it carries zero pairing information)."""
    cand = {0: {"pnl": 0.0, "date": IS_DATE, "traded": False, "skip_reason": "no_local_bars"},
            1: {"pnl": 5.0, "date": IS_DATE, "traded": True, "skip_reason": None}}
    ctrl = {0: {"pnl": 0.0, "date": IS_DATE, "traded": False, "skip_reason": "no_local_bars"},
            1: {"pnl": 0.0, "date": IS_DATE, "traded": False, "skip_reason": "floor_skip"}}
    r = dwf.compute_delta_wf(cand, ctrl)
    assert r["n_shared_episodes"] == 1      # episode 0 (neither traded) excluded


def test_pairing_both_trade():
    cand = {0: {"pnl": 30.0, "date": IS_DATE, "traded": True, "skip_reason": None}}
    ctrl = {0: {"pnl": 10.0, "date": IS_DATE, "traded": True, "skip_reason": None}}
    r = dwf.compute_delta_wf(cand, ctrl)
    assert r["n_both_traded"] == 1
    assert r["is_delta_sum"] == 20.0        # 30 - 10


# =================================================================================================
# 7. STRUCTURAL EDGE CASES -- empty IS or OOS half (conservative: FAIL, never a silent PASS)
# =================================================================================================
def test_no_is_episodes_at_all_is_conservative_fail():
    cand, ctrl = _mk_outcomes(cand_pnls_is=[], cand_pnls_oos=[8.0, 8.0])
    r = dwf.compute_delta_wf(cand, ctrl)
    assert r["n_is"] == 0
    assert r["is_delta_mean"] is None
    assert r["ladder_verdict"] == "FAIL"


def test_no_oos_episodes_at_all_is_conservative_fail():
    cand, ctrl = _mk_outcomes(cand_pnls_is=[10.0, 10.0], cand_pnls_oos=[])
    r = dwf.compute_delta_wf(cand, ctrl)
    assert r["n_oos"] == 0
    assert r["oos_delta_mean"] is None
    assert r["ladder_verdict"] == "FAIL"
    assert r["wf_delta"] is None            # n_oos=0 guard in compute_delta_wf


# =================================================================================================
# 8. reproduction_check() -- diffs this script's re-derived trades against the ORIGINAL scorecard
# =================================================================================================
def test_reproduction_check_match():
    floor_stats = {"n_traded": 239, "total_pnl_traded": 1984.2, "floor_clearance_rate": 0.9795}
    original_cell = {"n": 239, "total": 1984.2, "floor_clearance_rate": 0.9795}
    rc = dwf.reproduction_check("ATM", floor_stats, original_cell)
    assert rc["n_match"] is True
    assert rc["total_match"] is True
    assert rc["reproduced"] is True


def test_reproduction_check_n_mismatch_caught():
    floor_stats = {"n_traded": 238, "total_pnl_traded": 1984.2, "floor_clearance_rate": 0.9795}
    original_cell = {"n": 239, "total": 1984.2, "floor_clearance_rate": 0.9795}
    rc = dwf.reproduction_check("ATM", floor_stats, original_cell)
    assert rc["n_match"] is False
    assert rc["reproduced"] is False


def test_reproduction_check_total_mismatch_caught():
    floor_stats = {"n_traded": 239, "total_pnl_traded": 1990.0, "floor_clearance_rate": 0.9795}
    original_cell = {"n": 239, "total": 1984.2, "floor_clearance_rate": 0.9795}
    rc = dwf.reproduction_check("ATM", floor_stats, original_cell)
    assert rc["total_match"] is False
    assert rc["reproduced"] is False


# =================================================================================================
# 9. GATE BAR CONSTANT -- pins the frozen 0.70 value (CLAUDE.md OP-11's bar text is unchanged)
# =================================================================================================
def test_wf_gate_bar_is_070():
    assert dwf.WF_GATE_BAR == 0.70


def test_wf_form_label_matches_frozen_methodology():
    assert dwf.WF_FORM == "ab_delta_per_trade_v2026_07_16"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

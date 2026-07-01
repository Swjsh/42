"""Guard for the bull-unblock STRUCTURAL wide-window (full-history) probe.

Closes the #1-project-thread carry-forward the 2026-07-01 range-scalp frame-audit
named: the bull-frontier "25-day OPRA wall" was the SAME misread as range-scalp.
SLICE-2 (946530f) declared the structural bull lever (min_triggers_bull 2->1) NOT
proposable at n=8 (+$76 gross, INCONCLUSIVE) on a 25-day window. Re-run over the
FULL 2025-01..2026-06-18 master (533 days, real OPRA fills): the added cohort is
n=82 (pooled net +$608) but IS-2025 net -$300 / OOS-2026 net +$907 -> the signs
FLIP -> FAILS_WALK_FORWARD_SIGN_FLIP (also FRAGILE_TO_SLIPPAGE breakeven 0.012c,
215% day-concentrated). The 25-day +$76 was a slice of the 2026-only OOS tail, not
a real edge. Bull frontier confirmed edge-gated for the RIGHT (data-rich) reason.

FAST ($0, no 2-min probe re-run):
  1. the pure verdict ladder (all rungs + non-vacuous bite),
  2. the committed golden finding (reads the result JSON),
  3. the frame-audit anti-regression: the probe must point at the FULL master (not
     a 25-day recent CSV) so the "n<10 data-blocked" mistake cannot silently return.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))
_BT = _REPO / "backtest"
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

from autoresearch.bull_unblock_structural_widewindow_probe import (  # noqa: E402
    classify_wide_verdict,
    FULL_SPY_CSV,
    FULL_VIX_CSV,
    WINDOW_START,
    WINDOW_END,
    OOS_START,
    OUT_PATH,
)

# The committed finding's exact ladder inputs (from the 2026-07-01 full-history run).
_COMMITTED = dict(
    pooled_sufficient=True,             # added n=82 >= 10
    pooled_net_positive=True,           # pooled net +$607.58 (driven entirely by OOS)
    both_splits_sufficient=True,        # IS n=54, OOS n=28 both >= 10
    both_splits_positive=False,         # IS -$5.55/tr NEGATIVE, OOS +$32.4 positive -> sign flip
    slippage_survives_realistic=False,  # breakeven 0.0123 < 0.05
    concentrated=True,                  # top-3 days 215.3% of net
)


# --- 1. pure verdict ladder ---------------------------------------------------

def test_committed_inputs_give_walk_forward_sign_flip():
    assert classify_wide_verdict(**_COMMITTED) == "FAILS_WALK_FORWARD_SIGN_FLIP"


def test_ladder_all_rungs():
    def base(**over):
        d = dict(
            pooled_sufficient=True, pooled_net_positive=True,
            both_splits_sufficient=True, both_splits_positive=True,
            slippage_survives_realistic=True, concentrated=False,
        )
        d.update(over)
        return classify_wide_verdict(**d)

    assert base(pooled_sufficient=False) == "STILL_INCONCLUSIVE_AFTER_WIDENING"
    assert base(pooled_net_positive=False) == "BLOCK_CORRECTLY_REMOVES_LOSERS_ON_FULL_HISTORY"
    assert base(both_splits_sufficient=False) == "POOLED_POSITIVE_SPLIT_TOO_THIN"
    assert base(both_splits_positive=False) == "FAILS_WALK_FORWARD_SIGN_FLIP"
    assert base(slippage_survives_realistic=False) == "DIES_ON_SLIPPAGE"
    assert base(concentrated=True) == "POSITIVE_BUT_CONCENTRATED"
    assert base() == "UNBLOCK_ADDS_EDGE_PROPOSE_ON_WIDE_HISTORY"


def test_precedence_significance_before_everything():
    # too few added trades outranks any downstream disqualification (can't judge on noise).
    assert classify_wide_verdict(
        pooled_sufficient=False, pooled_net_positive=True,
        both_splits_sufficient=True, both_splits_positive=False,
        slippage_survives_realistic=False, concentrated=True,
    ) == "STILL_INCONCLUSIVE_AFTER_WIDENING"


def test_precedence_net_negative_before_walk_forward():
    # a net-negative pooled cohort is KEEP even if the (meaningless) split flags vary.
    assert classify_wide_verdict(
        pooled_sufficient=True, pooled_net_positive=False,
        both_splits_sufficient=True, both_splits_positive=True,
        slippage_survives_realistic=True, concentrated=False,
    ) == "BLOCK_CORRECTLY_REMOVES_LOSERS_ON_FULL_HISTORY"


def test_bite_committed_finding_flips_to_propose_when_robust():
    """NON-VACUOUS BITE: the committed finding fails for a REAL reason (walk-forward
    sign flip + slippage + concentration), not a hardcoded reject. Fixing the three
    genuine defects -- holding significance + pooled-positive fixed -- must PROPOSE."""
    robust = dict(_COMMITTED)
    robust["both_splits_positive"] = True
    robust["slippage_survives_realistic"] = True
    robust["concentrated"] = False
    assert classify_wide_verdict(**robust) == "UNBLOCK_ADDS_EDGE_PROPOSE_ON_WIDE_HISTORY"
    # and re-introducing ANY single defect alone re-disqualifies (proves each flag bites).
    assert classify_wide_verdict(**{**robust, "both_splits_positive": False}) == "FAILS_WALK_FORWARD_SIGN_FLIP"
    assert classify_wide_verdict(**{**robust, "slippage_survives_realistic": False}) == "DIES_ON_SLIPPAGE"
    assert classify_wide_verdict(**{**robust, "concentrated": True}) == "POSITIVE_BUT_CONCENTRATED"


# --- 2. committed golden finding (reads the result JSON) -----------------------

@pytest.mark.skipif(not OUT_PATH.exists(), reason="wide-window result JSON not present")
def test_golden_result_json_is_walk_forward_sign_flip():
    d = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    assert d["verdict"] == "FAILS_WALK_FORWARD_SIGN_FLIP"
    pooled = d["added_bull_cohort_pooled"]
    # data-widening WORKED: added n far past the n=8 wall that "blocked" the thread.
    assert pooled["n"] >= 10
    assert pooled["significance"]["sufficient"] is True
    # the honest killer: IS and OOS expectancy disagree in SIGN (regime artifact).
    wf = d["walk_forward"]
    assert wf["is_expectancy_usd"] < 0, "IS-2025 must be negative (the 2-trigger req removes losers in-sample)"
    assert wf["oos_expectancy_usd"] > 0, "OOS-2026 alone is positive -> the 25-day +$76 was this tail"
    assert wf["both_positive"] is False
    # and it would also die on slippage / be concentrated (belt-and-suspenders).
    assert wf["slippage_survives_realistic"] is False
    assert pooled["day_concentration"]["top3_day_pct_of_net"] > 150.0
    # block_elite_bull was held FIXED so this isolates ONLY the structural lever.
    assert "held FIXED" in d["block_elite_bull"]


# --- 3. frame-audit anti-regression -------------------------------------------

def test_probe_uses_full_master_not_25day_csv():
    """The whole point: the probe must run over the FULL master, not a 25-day recent
    CSV. If a future edit re-narrows it, the 'n<10 data-blocked' conclusion returns."""
    assert (WINDOW_END - WINDOW_START).days > 365
    assert WINDOW_START < OOS_START < WINDOW_END
    assert FULL_SPY_CSV.exists(), f"missing full SPY master {FULL_SPY_CSV.name}"
    assert FULL_VIX_CSV.exists(), f"missing full VIX master {FULL_VIX_CSV.name}"
    # and they must NOT be the retired 25-day recent CSV (the SLICE-2 window).
    assert "2026-05-19" not in FULL_SPY_CSV.name
    assert "2026-05-19" not in FULL_VIX_CSV.name


def test_full_master_covers_wide_history():
    """The master CSV must genuinely span the wide window (guards against a truncated
    file silently shrinking the sample back toward the n=8 wall)."""
    import pandas as pd

    head = pd.read_csv(FULL_SPY_CSV, usecols=["timestamp_et"], nrows=1)
    tail = pd.read_csv(FULL_SPY_CSV, usecols=["timestamp_et"]).iloc[-1]
    first = pd.to_datetime(head["timestamp_et"].iloc[0], utc=True).date()
    last = pd.to_datetime(tail["timestamp_et"], utc=True).date()
    assert first <= dt.date(2025, 1, 3)
    assert last >= dt.date(2026, 6, 17)

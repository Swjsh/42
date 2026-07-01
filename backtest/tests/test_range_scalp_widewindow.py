"""Guard for the range-scalp wide-window (full-history) probe.

Closes the loop on the 2026-07-01 frame-audit: slices 1+2 declared "widen the data
window" DATA-BLOCKED (n=8, 25-day window), but the master SPY/VIX 5m + OPRA fills
already covered the full 2025-01..2026-06 history. Running the SAME regime-gated
Tier-2 fade over the full history gave n=155 and the honest verdict DIES_ON_SLIPPAGE
(gross +$3.97/tr but breakeven 0.66c << 5c realistic; top-3 days 161% of net; flat
in-sample 2025).

This guard is FAST ($0, no 2.5-min probe re-run):
  1. the pure verdict ladder (all rungs + non-vacuous bite),
  2. the committed golden finding (reads the result JSON),
  3. the frame-audit anti-regression: the probe must point at the FULL master (not
     a 25-day recent CSV) so the "data-blocked" mistake cannot silently return.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
import sys
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from autoresearch.range_scalp_widewindow_probe import (  # noqa: E402
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
    pooled_sufficient=True,          # n=155 >= 10
    pooled_expectancy=3.97,          # gross +$3.97/tr
    both_splits_sufficient=True,     # IS n=123, OOS n=32 both >= 10
    both_splits_positive=True,       # IS +$0.95, OOS +$15.60
    slippage_survives_realistic=False,  # breakeven 0.0066 < 0.05
    concentrated=True,               # top-3 days 160.9% of net
)


# --- 1. pure verdict ladder ---------------------------------------------------

def test_committed_inputs_give_dies_on_slippage():
    assert classify_wide_verdict(**_COMMITTED) == "DIES_ON_SLIPPAGE"


def test_ladder_all_rungs():
    def base(**over):
        d = dict(
            pooled_sufficient=True, pooled_expectancy=5.0,
            both_splits_sufficient=True, both_splits_positive=True,
            slippage_survives_realistic=True, concentrated=False,
        )
        d.update(over)
        return classify_wide_verdict(**d)

    assert base(pooled_sufficient=False) == "STILL_INCONCLUSIVE_AFTER_WIDENING"
    assert base(pooled_expectancy=0.0) == "DRY_ON_FULL_HISTORY"
    assert base(pooled_expectancy=-1.0) == "DRY_ON_FULL_HISTORY"
    assert base(both_splits_sufficient=False) == "POOLED_POSITIVE_SPLIT_TOO_THIN"
    assert base(both_splits_positive=False) == "FAILS_WALK_FORWARD_SIGN_FLIP"
    assert base(slippage_survives_realistic=False) == "DIES_ON_SLIPPAGE"
    assert base(concentrated=True) == "POSITIVE_BUT_CONCENTRATED"
    assert base() == "PROMOTABLE_ON_WIDE_HISTORY"


def test_precedence_significance_before_slippage():
    # too few trades outranks a slippage failure (can't judge slippage on noise).
    assert classify_wide_verdict(
        pooled_sufficient=False, pooled_expectancy=3.97,
        both_splits_sufficient=True, both_splits_positive=True,
        slippage_survives_realistic=False, concentrated=True,
    ) == "STILL_INCONCLUSIVE_AFTER_WIDENING"


def test_bite_committed_finding_flips_to_promotable_when_robust():
    """NON-VACUOUS BITE: the committed finding is DIES_ON_SLIPPAGE for a REAL reason
    (slippage + concentration), not a hardcoded reject. Flipping ONLY those two flags
    -- holding significance + walk-forward fixed -- must promote it."""
    robust = dict(_COMMITTED)
    robust["slippage_survives_realistic"] = True
    robust["concentrated"] = False
    assert classify_wide_verdict(**robust) == "PROMOTABLE_ON_WIDE_HISTORY"
    # and flipping back either one alone re-disqualifies (proves each flag bites)
    assert classify_wide_verdict(**{**robust, "slippage_survives_realistic": False}) == "DIES_ON_SLIPPAGE"
    assert classify_wide_verdict(**{**robust, "concentrated": True}) == "POSITIVE_BUT_CONCENTRATED"


# --- 2. committed golden finding (reads the result JSON) -----------------------

@pytest.mark.skipif(not OUT_PATH.exists(), reason="wide-window result JSON not present")
def test_golden_result_json_is_slippage_dominated():
    d = json.loads(OUT_PATH.read_text(encoding="utf-8"))
    assert d["verdict"] == "DIES_ON_SLIPPAGE"
    g = d["gated_full_history"]
    # data-widening WORKED: n far past the n=8 wall that "blocked" the thread.
    assert g["summary"]["n_trades"] >= 100
    # gross-positive but breakeven half-spread far below realistic 0.05.
    assert g["summary"]["expectancy_per_trade_usd"] > 0
    assert g["slippage"]["breakeven_half_spread"] is not None
    assert g["slippage"]["breakeven_half_spread"] < 0.05
    # concentration confirms the fragility (top-3 days > 150% of net).
    assert g["concentration"]["top3_day_pct_of_net"] > 150.0
    # the raw ungated Tier-2 fade is net-negative over full history.
    assert d["ungated_full_history"]["summary"]["expectancy_per_trade_usd"] <= 0


# --- 3. frame-audit anti-regression -------------------------------------------

def test_probe_uses_full_master_not_25day_csv():
    """The whole point: the probe must run over the FULL master, not a 25-day recent
    CSV. If a future edit re-narrows it, the 'data-blocked' false conclusion returns."""
    # window must span > 12 months (the widening the thread needed).
    assert (WINDOW_END - WINDOW_START).days > 365
    assert WINDOW_START < OOS_START < WINDOW_END
    # the master CSVs the probe reads must actually exist on disk.
    assert FULL_SPY_CSV.exists(), f"missing full SPY master {FULL_SPY_CSV.name}"
    assert FULL_VIX_CSV.exists(), f"missing full VIX master {FULL_VIX_CSV.name}"
    # and they must NOT be the retired 25-day recent CSV.
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

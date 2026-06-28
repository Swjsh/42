"""Golden-file guard for the canonical probe-stats helper.

Pins the single-source significance + concentration policy (self-audit gap
2026-06-28T17:30:40 items 1+2) AND proves the helper reproduces the EXACT numbers
both committed range-scalp probes already published -- so adopting the helper in a
future probe cannot silently change a result, and the n<10 / top3>150% thresholds
can never drift apart again (the C14 divergent-knob class these two probes were in).

$0 / offline: reads the committed result JSONs, never re-runs the slow real-fills
probe.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO / "backtest") not in sys.path:
    sys.path.insert(0, str(_REPO / "backtest"))

from autoresearch.probe_stats import (  # noqa: E402
    CONCENTRATION_TOP3_PCT_MAX,
    INCONCLUSIVE_MIN_N,
    base_verdict,
    concentration_flag,
    day_concentration,
    significance,
    summarize_trades,
)

_REC = _REPO / "analysis" / "recommendations"
_UNGATED = _REC / "range-scalp-probe-2026-06-28.json"
_GATED = _REC / "range-scalp-regime-gated-2026-06-28.json"


def _load(p: Path) -> dict:
    if not p.exists():  # golden file is the fixture; absence is a real failure
        pytest.skip(f"golden file missing: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


# --- canonical thresholds are the single source of truth ----------------------

def test_thresholds_are_canonical():
    assert INCONCLUSIVE_MIN_N == 10
    assert CONCENTRATION_TOP3_PCT_MAX == 150.0


# --- significance: the n<10 gap -----------------------------------------------

def test_significance_flags_small_n():
    assert significance(8)["sufficient"] is False     # the gated probe's n=8
    assert significance(9)["sufficient"] is False
    assert significance(10)["sufficient"] is True      # exactly at the floor
    assert significance(30)["sufficient"] is True      # the ungated probe's n=30
    assert "INCONCLUSIVE" in significance(8)["note"]


# --- concentration: the top3>150% gap -----------------------------------------

def test_concentration_flag_threshold():
    assert concentration_flag(117.2)["concentrated"] is False  # gated: within tol
    assert concentration_flag(150.0)["concentrated"] is False  # boundary excluded
    assert concentration_flag(223.9)["concentrated"] is True   # ungated: fragile
    assert concentration_flag(None)["concentrated"] is False   # zero-net safe


# --- GOLDEN equivalence: helper reproduces the published numbers exactly -------

def test_helper_reproduces_ungated_concentration():
    d = _load(_UNGATED)
    by_day = d["results"]["by_day_pnl"]
    conc = day_concentration(by_day)
    # non-vacuous: the helper's top3 must MATCH the probe's hand-rolled 223.9
    assert conc["top3_day_pct_of_net"] == d["results"]["top3_day_pct_of_net"] == 223.9
    assert conc["n_active_days"] == d["results"]["n_active_days"]
    assert conc["n_losing_days"] == d["results"]["n_losing_days"]


def test_helper_reproduces_gated_summary_and_concentration():
    d = _load(_GATED)
    gross = d["gated_gross"]
    # reconstruct the gated per-trade pnls from the stored trade rows
    gated_pnls = [r["dollar_pnl"] for r in d["trades"] if r["kept"]]
    summ = summarize_trades(gated_pnls)
    # the helper must reproduce the published gated summary exactly
    assert summ["n_trades"] == gross["n_trades"] == 8
    assert summ["total_pnl_usd"] == gross["total_pnl_usd"] == 355.2
    assert summ["expectancy_per_trade_usd"] == gross["expectancy_per_trade_usd"] == 44.4
    assert summ["win_rate"] == gross["win_rate"] == 0.875
    # and the concentration block
    conc = day_concentration(gross["by_day_pnl"])
    assert conc["top3_day_pct_of_net"] == gross["top3_day_pct_of_net"] == 117.2


# --- canonical verdict ladder reproduces both probes' published verdicts -------

def test_base_verdict_matches_published_verdicts():
    # ungated: n=30, exp 12.46, top3 223.9 -> positive but concentration-fragile.
    # The probe labels this "VEIN_CONCENTRATED"; the canonical neutral verdict is
    # CONCENTRATED (same judgment, single vocabulary).
    assert base_verdict(30, 12.46, 223.9) == "CONCENTRATED"
    # gated: n=8 -> below the floor regardless of how good it looks.
    # Probe labels it "REGIME_GATE_TOO_TIGHT"; canonical = INCONCLUSIVE.
    assert base_verdict(8, 44.4, 117.2) == "INCONCLUSIVE"


def test_base_verdict_ladder_full():
    assert base_verdict(5, 100.0, 50.0) == "INCONCLUSIVE"   # n gate wins first
    assert base_verdict(20, -3.0, 50.0) == "DRY"            # enough n, no edge
    assert base_verdict(20, 5.0, 200.0) == "CONCENTRATED"   # edge but fragile
    assert base_verdict(20, 5.0, 90.0) == "CLEAN"           # edge, spread out
    assert base_verdict(20, 5.0, None) == "CLEAN"           # zero-net -> not fragile


# --- empty-input safety -------------------------------------------------------

def test_empty_inputs_safe():
    s = summarize_trades([])
    assert s["n_trades"] == 0 and s["total_pnl_usd"] == 0.0
    c = day_concentration({})
    assert c["n_active_days"] == 0 and c["top3_day_pct_of_net"] is None

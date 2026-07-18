"""Guard: armability primitive + promoter disclosure (G7, 2026-07-07 Fable gap-audit).

The primitive answers 'can this account afford the minimum position for a candidate edge at
its current per-trade risk budget'. The promoter disclosure surfaces it per promoted cell so
chef stops promoting edges the accounts can't trade (ITM-2 unaffordable / 2DTE 1.6-lots<3).

Run: cd backtest && python -m pytest tests/test_armability.py -v
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
LIB = REPO / "backtest" / "lib"
AUTORES = REPO / "backtest" / "autoresearch"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod  # register so @dataclass can resolve cls.__module__
    spec.loader.exec_module(mod)
    return mod


def _arm():
    return _load("armability", LIB / "armability.py")


# --------------------------------------------------------------------------- primitive
def test_armable_when_floor_fits_budget():
    a = _arm().armability(0.30, 2000.0, risk_frac=0.30)  # budget 600, per-lot 30, min-lot 90
    assert a.armable is True
    assert a.budget == 600.0
    assert a.min_lot_cost == 90.0
    assert a.max_affordable_lots == 20


def test_unaffordable_when_floor_exceeds_budget():
    a = _arm().armability(3.00, 2000.0, risk_frac=0.30)  # per-lot 300, min-lot 900 > 600
    assert a.armable is False
    assert a.max_affordable_lots == 2  # 600 // 300


def test_exact_boundary_is_armable():
    # premium 2.00 -> per-lot 200 -> min-lot 600 == budget 600 -> armable (<=, not <)
    a = _arm().armability(2.00, 2000.0, risk_frac=0.30)
    assert a.min_lot_cost == 600.0 and a.budget == 600.0
    assert a.armable is True


def test_fractional_lots_floored_below_min():
    # the audit's 2DTE case: budget 600, premium 3.75 -> 1.6 lots floored to 1 < 3 floor
    a = _arm().armability(3.75, 2000.0, risk_frac=0.30)
    assert a.max_affordable_lots == 1
    assert a.armable is False


def test_breakeven_premium():
    assert _arm().breakeven_premium(2000.0, risk_frac=0.30) == 2.0  # 600 / (3*100)


def test_min_1_single_exit_shape_is_armable():
    # single-exit shape (min 1): premium 3.75, budget 600 -> 1 lot fits -> armable (D5)
    a = _arm().armability(3.75, 2000.0, risk_frac=0.30, min_contracts=1)
    assert a.armable is True


def test_invalid_inputs_raise():
    am = _arm()
    bad = [
        (0.5, 0, 0.3),      # equity <= 0
        (0.0, 2000, 0.3),   # premium <= 0
        (0.5, 2000, 0.0),   # risk_frac <= 0
        (0.5, 2000, 1.5),   # risk_frac > 1
    ]
    for prem, eq, rf in bad:
        with pytest.raises(ValueError):
            am.armability(prem, eq, risk_frac=rf)


def test_disclosure_builder_shape():
    am = _arm()
    d = am.account_armability_disclosure({"Gamma-Safe-2": {"equity": 2000.0, "risk_frac": 0.30}})
    acct = d["accounts"]["Gamma-Safe-2"]
    assert acct["budget"] == 600.0
    assert acct["max_affordable_premium_for_floor"] == 2.0
    assert len(acct["sweep"]) == len(am.PREMIUM_SWEEP)


# --------------------------------------------------------------------------- promoter wiring
def test_promoter_scorecard_carries_armability(tmp_path):
    pp = _load("pipeline_promoter", AUTORES / "pipeline_promoter.py")
    scorecard = {"best": {"combo": {"strike_offset": 2}}}
    pp._write_promote_scorecard("shotgun_scalper", {"wf_ratio": 0.8}, scorecard,
                                flag_key=None, exec_armed=False, recs_dir=tmp_path)
    out = json.loads((tmp_path / "promote_shotgun_scalper.json").read_text(encoding="utf-8"))
    assert "armability" in out, "promote scorecard must carry the G7 armability disclosure"
    arm = out["armability"]
    assert "accounts" in arm and "Gamma-Safe-2" in arm["accounts"]
    assert arm["accounts"]["Gamma-Safe-2"]["max_affordable_premium_for_floor"] > 0

"""Guards for setup/scripts/fee_recalibration.py.

THE central test is the first one. This instrument exists to check go_live_gate's cost
model against real broker charges, so it has to reproduce that model EXACTLY -- rates and
formula. My first cut mirrored the rates but wrote `ceil(2x)` where the gate writes
`2*ceil(x)`, under-counted OCC by $0.46 across 47 trades, and flipped the instrument's own
verdict from CONSERVATIVE to "OPTIMISTIC -- investigate immediately". A validator that does
not reproduce the thing it validates is reporting on itself.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


fr = _load("fee_recalibration_g", SCRIPTS / "fee_recalibration.py")
glg = _load("go_live_gate_g", SCRIPTS / "go_live_gate.py")


@pytest.mark.parametrize("qty,px", [(3, 0.78), (1, 0.05), (10, 2.50), (5, 1.13), (2, 0.31)])
def test_predictor_reproduces_the_gates_own_fee_formula(qty, px):
    """THE test. Same trade through both paths must agree to the cent."""
    row = [{"date": "2026-08-03", "qty": qty, "exit_px_avg": px}]
    mine = fr.predict(row, per_trade_ceiling=True)
    ex_cat = mine["OCC"] + mine["ORF"] + mine["TAF"] + mine["REG"]
    assert ex_cat == pytest.approx(glg.fee_ex_cat(qty, px), abs=1e-9), (
        "fee_recalibration no longer reproduces go_live_gate.fee_ex_cat -- it is reporting "
        "on its own arithmetic, not on the gate's"
    )


def test_rates_match_the_gate_exactly():
    """The rates are duplicated deliberately so drift FAILS rather than silently follows."""
    assert fr.FEE_RATES == glg.FEE_RATES


def test_per_leg_ceiling_is_not_the_same_as_ceiling_the_pair():
    """The exact confusion that caused the bug -- pinned so nobody 'simplifies' it back."""
    rate, qty = fr.FEE_RATES["occ_per_contract"], 3
    assert 2 * fr.ceil_cents(rate * qty) != fr.ceil_cents(2 * rate * qty)


def test_daily_ceiling_never_exceeds_per_trade_ceiling():
    """Fewer ceiling operations can only round up fewer times. If this inverts, the two
    branches have been swapped."""
    rows = [{"date": "2026-08-03", "qty": 3, "exit_px_avg": 0.78},
            {"date": "2026-08-03", "qty": 2, "exit_px_avg": 1.10},
            {"date": "2026-08-04", "qty": 5, "exit_px_avg": 0.44}]
    pt = fr.predict(rows, per_trade_ceiling=True)
    pd_ = fr.predict(rows, per_trade_ceiling=False)
    for k in ("OCC", "ORF", "TAF", "REG"):
        assert pd_[k] <= pt[k] + 1e-9, f"{k}: daily rounding exceeded per-trade rounding"


def test_cat_is_per_trading_day_not_per_trade():
    rows = [{"date": "2026-08-03", "qty": 1, "exit_px_avg": 1.0},
            {"date": "2026-08-03", "qty": 1, "exit_px_avg": 1.0},
            {"date": "2026-08-04", "qty": 1, "exit_px_avg": 1.0}]
    assert fr.predict(rows)["CAT"] == pytest.approx(2 * fr.FEE_RATES["cat_per_arm_day"])


def test_empty_rows_predict_zero_not_a_crash():
    p = fr.predict([])
    assert all(v == 0 for v in p.values())


def test_direction_wording_flags_an_optimistic_model_loudly():
    """A model that UNDER-states cost flatters the gate. That must not read as neutral."""
    src = (SCRIPTS / "fee_recalibration.py").read_text(encoding="utf-8")
    assert "investigate immediately" in src
    assert "CONSERVATIVE" in src


def test_module_never_writes_fee_rates():
    """READ the rates, never rewrite them -- correcting the model mid-window makes
    criterion 1 easier to pass (OP-11).

    Asked via the AST, not a substring count. `FEE_RATES[` appears legitimately a dozen
    times as READS inside predict(), so a text search cannot tell a read from a write --
    my first cut counted occurrences and failed on the module's own correct code. Third
    time tonight a string search was asked a question only the parser can answer.
    """
    import ast

    tree = ast.parse((SCRIPTS / "fee_recalibration.py").read_text(encoding="utf-8"))
    writes = []
    for node in ast.walk(tree):
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)):
            targets = [node.target]
        for tgt in targets:
            base = tgt
            while isinstance(base, ast.Subscript):
                base = base.value
            if isinstance(base, ast.Name) and base.id == "FEE_RATES":
                # the module-level literal definition is the one legal write
                if not (isinstance(node, ast.Assign) and node.col_offset == 0):
                    writes.append(node.lineno)
    assert not writes, f"FEE_RATES is written at line(s) {writes}"

    for forbidden in ("FEE_RATES.update", "FEE_RATES.pop", "FEE_RATES.clear"):
        assert forbidden not in (SCRIPTS / "fee_recalibration.py").read_text(encoding="utf-8")

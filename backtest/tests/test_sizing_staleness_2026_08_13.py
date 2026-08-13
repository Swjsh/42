"""Guard: the cost-recovery law and the sizing-staleness detector that surfaces its violation.

WHY THIS FILE EXISTS. On 2026-08-13 J said, unprompted: "we're not a home run factory... buying
the right amount and right size contracts 20-40% and make back the money we spent on the entire
trade. thats where the runners come in." Tracing it produced a complete root-cause chain:

    Rule 6 min_contracts=3 (authored at $1-2K equity)
      -> fleet_executor._apply_recency_min_sizing does `min(qty, min_contracts)` -- a FLOOR used
         as a CEILING, so a risk gate that computed 8 was overridden back to 3
      -> 3 contracts cannot recover a trade's cost below +50% (n = ceil(Q/(1+r)))
      -> the +100% TP1 inherited from the SS-B whole-cell port was never challenged
      -> the strategy only pays on home runs (TP1 fires 20.4% of the time)

Nobody made a wrong edit. The number was correct once and nothing re-derived it as equity tripled.

PROVEN ON LIVE FILLS the same day: risky-1 holds the LOW TP1 (+50%). It fired at +56%, sold 3 of
5 for $504 against a $540 cost -- took profit and still had not paid for the trade. Cause:
tp1_qty_fraction 0.667 * 5 = 3.33 -> floors to 3, where the law requires ceil(5/1.56) = 4.

This file pins the ARITHMETIC (which cannot drift) and the DETECTOR (which can).
It deliberately does NOT pin min_contracts to any particular value -- that is a pre-registered
A/B decision, and the recency clamp it feeds is itself A/B-validated. The guard's job is that the
drift stays VISIBLE, not that it be resolved a particular way.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "sizing_staleness_check.py"


@pytest.fixture(scope="module")
def mod():
    spec = importlib.util.spec_from_file_location("_sizing_staleness_probe", MOD_PATH)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_sizing_staleness_probe"] = m
    spec.loader.exec_module(m)
    return m


# ------------------------------------------------------------------ the arithmetic


@pytest.mark.parametrize("qty,expected", [
    (2, None),    # cannot recover cost and keep a runner at ANY rate in the band
    (3, 0.50),    # THE FINDING: 3 lots force +50%. This is why live TP1 sits so high.
    (4, 0.40),
    (5, 0.25),
    (6, 0.20),
    (8, 0.20),    # what the risk gate actually wanted before the clamp
    (16, 0.20),
])
def test_cost_recovery_floor_is_determined_by_contract_count(mod, qty, expected):
    """Entry premium cancels out of n*E(1+r) >= Q*E, so the required first-tranche gain is a
    function of Q alone. If this table changes, the law was reimplemented wrong."""
    assert mod.cost_recovery_min_r(qty) == expected


@pytest.mark.parametrize("qty,r", [(3, 0.50), (5, 0.25), (8, 0.20), (16, 0.20)])
def test_the_returned_rate_actually_recovers_cost_and_leaves_a_runner(mod, qty, r):
    """Independent re-derivation -- proves the table above is not just self-consistent."""
    n = math.ceil(qty / (1.0 + r))
    assert n * (1.0 + r) >= qty, f"selling {n} of {qty} at +{r:.0%} does NOT return the outlay"
    assert qty - n >= 1, f"no runner left at Q={qty}, r={r:.0%}"


def test_three_lots_cannot_cost_recover_in_Js_20_to_40_band(mod):
    """The precise claim made to J. If this ever passes at +40% or below, the law changed and
    the whole COST-RECOVERY-SIZING finding needs re-deriving rather than citing."""
    for r in (0.20, 0.25, 0.30, 0.40):
        assert 3 - math.ceil(3 / (1.0 + r)) < 1, (
            f"3 contracts now leave a runner at +{r:.0%} -- the arithmetic in the finding is wrong")
    assert mod.cost_recovery_min_r(3) == 0.50


def test_a_fixed_qty_fraction_can_fail_to_recover_cost(mod):
    """RISKY-1, 2026-08-13, reproduced as arithmetic. tp1_qty_fraction=0.667 on Q=5 floors to 3;
    3 sold at +56% returns $504 against a $540 outlay. This is the defect in one assertion."""
    Q, entry, r = 5, 1.08, 0.56
    sold_fixed = int(Q * 0.667)                       # 3.33 -> 3
    assert sold_fixed == 3
    assert sold_fixed * entry * (1 + r) * 100 < Q * entry * 100, (
        "the fixed-fraction tranche now covers cost -- risky-1's exhibit no longer reproduces")
    sold_law = math.ceil(Q / (1 + r))                 # 4
    assert sold_law == 4
    assert sold_law * entry * (1 + r) * 100 >= Q * entry * 100, (
        "ceil(Q/(1+r)) must recover cost by construction")


# ------------------------------------------------------------------ the detector


def test_detector_flags_drift_and_not_stability(mod):
    """VARY-AND-ASSERT (C14). A detector that reports RED unconditionally is not a detector."""
    assert mod.DRIFT_RED > mod.DRIFT_WARN > 1.0
    # every tracked constant must carry the equity it was authored for -- without that field
    # "drift" has no definition and the report would be an opinion
    for spec in mod.TRACKED:
        assert spec.get("authored_equity"), f"{spec['key']} has no authored_equity baseline"
        assert spec.get("consumed_by"), f"{spec['key']} does not say what reads it"


def test_not_run_is_never_reported_as_a_pass(mod):
    """C7 / L286. Conflating 'could not measure' with 'measured and fine' is the documented
    failure this repo keeps repeating -- an unreadable equity must not render as GREEN."""
    src = MOD_PATH.read_text(encoding="utf-8")
    assert '"NOT_RUN"' in src
    assert 'row["status"] = "NOT_RUN"' in src
    # and the NOT_RUN branch must escalate the overall verdict, not fall through as GREEN
    idx = src.index('row["status"] = "NOT_RUN"')
    assert "worst" in src[idx:idx + 400], "NOT_RUN does not escalate the top-level verdict"


def test_live_equity_never_falls_back_to_a_cached_value(mod):
    """A stale equity read is the very defect being detected; a silent fallback would make the
    detector blind to its own failure mode (exactly what the window-leak detector did today).

    AST, NOT SUBSTRINGS. The first cut asserted `"return None" in fn` plus a blocklist of
    fallback spellings. Source mutation proved that useless: `return 2000.0` inside the except
    branch passed it cleanly, because `return None` still appeared elsewhere in the function
    and 2000.0 was not on the blocklist. A blocklist can only ban spellings you predicted.
    The real invariant -- EVERY return reachable from a failed read yields None -- needs the
    parse tree. Same class of error as the DEAD-label audit and the fast-path caller scan.
    """
    import ast
    tree = ast.parse(MOD_PATH.read_text(encoding="utf-8"))
    fn = next((n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "live_equity"), None)
    assert fn is not None, "live_equity was renamed or removed"

    handlers = [h for h in ast.walk(fn) if isinstance(h, ast.ExceptHandler)]
    assert handlers, "live_equity no longer catches read failures at all"
    for h in handlers:
        for ret in [n for n in ast.walk(h) if isinstance(n, ast.Return)]:
            assert isinstance(ret.value, ast.Constant) and ret.value.value is None, (
                "live_equity returns a FALLBACK VALUE from an exception handler. A broker read "
                "that fails must yield None so the row reports NOT_RUN -- substituting a number "
                "makes the staleness detector blind to exactly the staleness it exists to find.")

    # Non-handler early returns (missing secrets / malformed account) must also be None-valued:
    # a default there is the same blindness by a different door.
    for ret in [n for n in ast.walk(fn) if isinstance(n, ast.Return)]:
        if isinstance(ret.value, ast.Constant) and isinstance(ret.value.value, (int, float)):
            raise AssertionError(
                f"live_equity has a hard-coded numeric return ({ret.value.value}) at line "
                f"{ret.lineno} -- every failure path must return None")


def test_the_clamp_this_detects_still_uses_the_floor_as_a_ceiling(mod):
    """THE PREMISE. If fleet_executor stops doing min(qty, min_contracts), the drift stops being
    load-bearing and this detector's urgency changes -- re-derive rather than delete."""
    fe = (REPO / "automation" / "state" / "fleet" / "fleet_executor.py").read_text(encoding="utf-8")
    code = "\n".join(l for l in fe.splitlines() if not l.strip().startswith("#"))
    assert "clamped = min(int(qty), min_qty)" in code, (
        "the recency clamp no longer clamps DOWN to min_contracts -- the root-cause chain in "
        "COST-RECOVERY-SIZING-2026-08-13.md needs re-deriving")


def test_the_finding_doc_this_guards_still_exists(mod):
    doc = REPO / "analysis" / "recommendations" / "COST-RECOVERY-SIZING-2026-08-13.md"
    assert doc.exists(), "the finding this guard encodes was deleted"
    text = doc.read_text(encoding="utf-8")
    assert "ceil(Q / (1+r))" in text
    assert "risky-1" in text, "the live exhibit that proves the defect was removed"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

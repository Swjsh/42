"""Guard: a triggered STOP pays slippage; only a resting LIMIT fills exactly (2026-08-12).

THE BUG. simulator_real.py charged `- exit_slippage` on market exits but filled the premium stop,
the post-TP1 breakeven stop and the aggressive-runner stop at their EXACT stop price with none:

    fill.runner_exit_premium = runner_stop_premium     # pre-TP1 premium stop
    cons_price               = runner_stop_premium     # post-TP1 BE stop (conservative runner)
    aggr_price               = runner_stop_premium     # post-TP1 stop (aggressive runner)

That is wrong on its own terms -- a stop is a TRIGGER, not a resting limit; when price trades
through it you sell at market, and live does literally that via fleet_broker.market_sell.

WHY IT MATTERED MORE THAN IT LOOKS. It made the harness NON-MONOTONIC IN SLIPPAGE. P&L on such a
trade was proportional to a slippage-INFLATED entry against a slippage-FREE exit, so *lowering*
slippage made those trades WORSE. Predicted 0.30 x 0.01 x 2 x 100 = $0.60; observed -$0.60 on
every one. Consequences:

  * There is no single "pessimism" number for the 2c default -- the SIGN of the 2c-vs-1c bias
    depends on each cell's exit mix. Same script, same trades: +$39.60 on a premium-stop arm vs
    +$548.80 on a market-exit arm. An earlier claim in this repo that "2c errs conservative" was
    FALSE and had to be retracted; this test exists partly so that claim cannot quietly return.
  * The worst-hit studies were the EXIT-TUNING sweeps -- sweep_regime_chandelier went 24/24 cells
    worse -- i.e. exactly the studies that chose the live exit parameters.
  * Re-baselining slippage 2c -> 1c on top of an asymmetric fill model would have baked the
    non-monotonicity in permanently. Hence: fix first, re-baseline second.

WHAT MUST NEVER ROT
  * All three stop fills pay exit_slippage.
  * The TP1 resting limit still fills EXACTLY -- a real resting limit does. Charging it slippage
    would be the opposite error.
  * Exit fills never go non-positive (the max(0.01, ...) floor).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]

# BOTH siblings. simulator_real_trailing.py carried the identical bug at its own lines 294/383/408
# and was fixed in the same commit. Guarding only the file where a bug was first noticed is how
# L294 recurs -- copy-pasted siblings break identically, so the guard must cover the CLASS.
SIMS = {
    "simulator_real": REPO / "backtest" / "lib" / "simulator_real.py",
    "simulator_real_trailing": REPO / "backtest" / "lib" / "simulator_real_trailing.py",
}
SRC = SIMS["simulator_real"].read_text(encoding="utf-8")


def _code_lines(path: Path | None = None) -> list[str]:
    """Source with comment-only lines removed, so a comment quoting the OLD buggy form (this file
    and both simulators do) can never satisfy or break a source assertion."""
    text = SRC if path is None else path.read_text(encoding="utf-8")
    return [ln for ln in text.splitlines() if not ln.strip().startswith("#")]


# ------------------------------------------------------------------ the three stop fills


@pytest.mark.parametrize("sim", sorted(SIMS))
@pytest.mark.parametrize("assignee", [
    "fill.runner_exit_premium",   # pre-TP1 premium stop
    "cons_price",                 # post-TP1 breakeven stop, conservative runner
    "aggr_price",                 # post-TP1 stop, aggressive runner
])
def test_no_stop_fills_at_the_exact_stop_price(sim, assignee):
    """THE REGRESSION. `X = runner_stop_premium` with no slippage term is the bug -- in all three
    places it appeared, in BOTH simulators."""
    bad = re.compile(rf"^\s*{re.escape(assignee)}\s*=\s*runner_stop_premium\s*$")
    hits = [ln for ln in _code_lines(SIMS[sim]) if bad.match(ln)]
    assert not hits, (
        f"{sim}: {assignee} fills at the exact stop with no slippage again: {hits}. A triggered "
        "stop sells at market (live: fleet_broker.market_sell) and must pay exit_slippage.")


@pytest.mark.parametrize("sim", sorted(SIMS))
def test_all_three_stop_fills_subtract_exit_slippage(sim):
    code = "\n".join(_code_lines(SIMS[sim]))
    n = code.count("max(0.01, runner_stop_premium - exit_slippage)")
    assert n == 3, (
        f"{sim}: expected 3 slippage-paying stop fills (premium stop, conservative BE stop, "
        f"aggressive stop), found {n}")


@pytest.mark.parametrize("sim", sorted(SIMS))
def test_stop_fills_keep_the_positive_price_floor(sim):
    """A deep stop minus slippage must not produce a zero or negative fill price."""
    for ln in _code_lines(SIMS[sim]):
        if "runner_stop_premium - exit_slippage" in ln:
            assert "max(0.01," in ln, f"{sim}: missing the positive-price floor: {ln.strip()}"


def test_both_simulators_exist_so_the_sibling_cannot_be_silently_dropped():
    """If a sibling is renamed or removed this must fail loudly rather than quietly shrinking its
    own coverage (L292: a monitor's scope rots like the thing it monitors)."""
    for name, path in SIMS.items():
        assert path.exists(), f"{name} missing at {path} -- re-point this guard deliberately"


# ------------------------------------------------------------------ the limit that SHOULD be exact


def test_the_tp1_resting_limit_still_fills_exactly():
    """Scope guard, and the other half of being correct. A resting TP1 limit DOES fill at its
    price -- charging it slippage would be the mirror-image error of the bug we just fixed."""
    code = "\n".join(_code_lines())
    assert "tp1_fire_premium = tp1_premium_fallback" in code, (
        "the TP1 resting limit no longer fills exactly -- if that was deliberate it needs its own "
        "prereg; a resting limit is not a stop")


def test_market_exits_still_pay_slippage():
    """The half that was always right must stay right."""
    code = "\n".join(_code_lines())
    assert code.count("max(0.01, opt_bar.close - exit_slippage)") >= 5


# ------------------------------------------------------------------ monotonicity, the real property


def test_lower_slippage_can_never_make_the_TP1_plus_BE_runner_trade_worse():
    """The real invariant, as arithmetic rather than source text.

    IMPORTANT -- the non-monotonicity is NOT in a plain premium stop. My first cut of this test
    modelled `exit = stop_px` and found the old code perfectly monotonic, because an absolute stop
    price does not scale with the entry. Working out why that failed is the whole mechanism:

    it needs an exit price that is PROPORTIONAL to the slippage-inflated entry. The TP1-limit +
    breakeven-runner shape is exactly that, and both legs were slippage-free:

        entry  = base + slip                        (entry always pays slippage)
        TP1    = entry * (1 + tp1_pct)              -> profit = entry * tp1_pct  ... grows with slip
        BE stop= entry                              -> profit = 0                ... never negative

    So inflating slippage inflated the TP1 target off an inflated base and the runner leg could
    never lose. Lowering slippage made the trade WORSE. With the production shape
    (tp1_pct 0.30, tp1 qty 2, runner qty 1) that is 0.30 x 0.01 x 2 x 100 = $0.60 -- the figure the
    re-baseline predicted a priori and then observed on every such trade.

    Under the fix the BE stop pays slippage, so the runner leg loses exactly `slip` per contract,
    which restores the correct sign.
    """
    base, tp1_pct, tp1_qty, run_qty = 1.00, 0.30, 2, 1

    def pnl(slip: float, buggy: bool) -> float:
        entry = base + slip
        tp1_leg = (entry * (1 + tp1_pct) - entry) * tp1_qty * 100      # resting limit: exact, correct
        be_exit = entry if buggy else max(0.01, entry - slip)          # STOP: must pay slippage
        run_leg = (be_exit - entry) * run_qty * 100
        return tp1_leg + run_leg

    fixed_2c, fixed_1c = pnl(0.02, False), pnl(0.01, False)
    buggy_2c, buggy_1c = pnl(0.02, True), pnl(0.01, True)

    assert buggy_1c < buggy_2c, "sanity: the old model really was non-monotonic in slippage"
    assert round(buggy_2c - buggy_1c, 2) == 0.60, (
        "the reproduction no longer matches the $0.60 the re-baseline predicted and observed")
    assert fixed_1c > fixed_2c, (
        "lower slippage still hurts under the fixed model -- the asymmetry is not actually closed")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

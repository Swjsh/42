"""Guard for backtest/tools/safe_vix_conditional_sizing_ab.py's vix_regime() classification --
the one piece of genuinely new logic in that research script (everything else is reused from
safe_quality_sizing_ab.py). Cheap, non-vacuous coverage of the regime-band boundaries so a future
edit to REGIME_BANDS can't silently misclassify entries without a test noticing.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

from safe_vix_conditional_sizing_ab import vix_regime, REGIME_BANDS  # noqa


def test_regime_bands_match_future_improvements_doc():
    # markdown/planning/FUTURE-IMPROVEMENTS.md:130 -- BULL<17.5, NEUTRAL 17.5-22, VOLATILE>=22
    assert REGIME_BANDS["BULL"] == (0.0, 17.5)
    assert REGIME_BANDS["NEUTRAL"] == (17.5, 22.0)
    assert REGIME_BANDS["VOLATILE"][0] == 22.0


def test_bull_regime_classification():
    assert vix_regime(12.0) == "BULL"
    assert vix_regime(17.49) == "BULL"


def test_neutral_regime_classification():
    assert vix_regime(17.5) == "NEUTRAL"  # inclusive lower bound
    assert vix_regime(20.0) == "NEUTRAL"
    assert vix_regime(21.99) == "NEUTRAL"


def test_volatile_regime_classification():
    assert vix_regime(22.0) == "VOLATILE"  # inclusive lower bound
    assert vix_regime(35.0) == "VOLATILE"


def test_none_input_returns_none():
    assert vix_regime(None) is None


def test_boundaries_are_mutually_exclusive_and_exhaustive():
    # Every value from 0 to 50 in 0.1 steps must classify to exactly one regime, no gaps/overlaps.
    v = 0.0
    while v <= 50.0:
        regime = vix_regime(round(v, 1))
        assert regime is not None, f"vix={v} classified as None -- gap in bands"
        v += 0.1

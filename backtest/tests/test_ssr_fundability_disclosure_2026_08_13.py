"""Guard: the SSR shadow's arming bar must disclose that its P&L is scored on unfundable size.

THE DEFECT (2026-08-13). ssr-shadow-progress.json reported total_pnl_usd 15,831.81 over 8 round
trips -- $1,979/trip -- and that figure feeds `arming_bar`. It is scored on FULL-SIZE NQ
(point_value 20.0) and GC (100.0), because CONFIGS are keyed "NQ"/"GC" and get_ssr resolves
those to the full contracts. One full NQ at ~29,850 is ~$597,000 notional; the shadow trades
qty=3, so ~$1.79M. The book behind the program holds ~$5,500 -- a ratio of ~326x.

The number is arithmetically correct and operationally impossible. Same class as everything else
found today: a figure that is internally consistent while measuring something the system cannot
actually do.

DELIBERATELY NOT FIXED BY SWITCHING THE INSTRUMENT. spec_version is ssr-v1 and 8 round trips are
already scored at full size; changing point_value mid-study would mix units inside one ledger,
which is worse than the disclosure. Switching CONFIGS to MNQ/MGC is ssr-v2 and needs its own
decision plus a recompute of history from the recorded points.

Separately worth remembering: the same scorecard's own null shows management contributes only
$3,048 of the $15,832 -- 80.7% of it is short beta over a 4-day NQ decline.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SSR = REPO / "setup" / "scripts" / "ssr_shadow.py"


@pytest.fixture(scope="module")
def ssr():
    sys.path.insert(0, str(REPO / "backtest"))
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    spec = importlib.util.spec_from_file_location("_ssr_probe", SSR)
    m = importlib.util.module_from_spec(spec)
    sys.modules["_ssr_probe"] = m
    spec.loader.exec_module(m)
    return m


def test_fundability_block_exists_and_scales_correctly(ssr):
    """THE DISCLOSURE. Both NQ->MNQ and GC->MGC are exactly 10x, so the micro equivalent is
    total/10."""
    f = ssr._fundability(15831.81)
    assert f["point_value_ratio"] == 10.0
    assert f["micro_equivalent_total_pnl_usd_approx"] == pytest.approx(1583.18, abs=0.01)
    for key in ("scored_on", "book_can_fund", "why_it_matters", "to_fix_properly", "approximation"):
        assert f.get(key), f"fundability lost its {key} field"


def test_the_ratio_matches_the_actual_instrument_registry(ssr):
    """VARY-AND-ASSERT. If the registry's point values change, a hardcoded 10.0 silently lies.
    This re-derives it from the registry rather than trusting the constant."""
    from futures.ssr.ssr_instruments import get_ssr
    for full, micro in ssr.MICRO_OF.items():
        a, b = get_ssr(full).point_value, get_ssr(micro).point_value
        assert a / b == ssr._FULL_TO_MICRO_POINT_RATIO, (
            f"{full}/{micro} point-value ratio is {a/b}, but _FULL_TO_MICRO_POINT_RATIO is "
            f"{ssr._FULL_TO_MICRO_POINT_RATIO} -- the disclosed micro equivalent is now wrong")


def test_progress_carries_the_disclosure(ssr):
    """It must ride ON the arming scorecard. A disclosure in a separate file nobody reads is
    not a disclosure."""
    p = ssr.compute_progress([])
    assert "fundability" in p, "compute_progress no longer emits the fundability block"
    assert "arming_bar" in p


def test_the_spec_version_was_NOT_bumped_by_this_disclosure(ssr):
    """Scope discipline: this is additive reporting, not a spec change. If someone switches the
    instrument, spec_version must move to ssr-v2 AND history must be recomputed -- at which
    point this guard should be re-derived, not deleted quietly."""
    assert ssr.SPEC_VERSION == "ssr-v1", (
        f"SPEC_VERSION is {ssr.SPEC_VERSION}. If the instrument was switched to MNQ/MGC, the 8 "
        "existing full-size round trips must be recomputed from their recorded points or the "
        "ledger mixes units.")


def test_configs_are_still_the_full_contracts(ssr):
    """Pins the premise. When this starts failing because CONFIGS moved to MNQ/MGC, the
    disclosure has been superseded by a real fix -- update it in that commit."""
    keys = set(ssr.CONFIGS)
    assert keys == {"NQ", "GC"}, (
        f"CONFIGS keys are now {sorted(keys)}. If they are micros, the fundability disclosure is "
        "obsolete and spec_version should have moved to ssr-v2.")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

"""Guard: the SSR shadow's arming bar must disclose that its P&L is scored on fundable size.

THE DEFECT (2026-08-13). ssr-shadow-progress.json reported total_pnl_usd 15,831.81 over 8 round
trips -- $1,979/trip -- and that figure fed `arming_bar`. It was scored on FULL-SIZE NQ
(point_value 20.0) and GC (100.0), because CONFIGS were keyed "NQ"/"GC" and get_ssr resolved
those to the full contracts. One full NQ at ~29,850 was ~$597,000 notional; the shadow traded
qty=3, so ~$1.79M. The book behind the program held ~$5,500 -- a ratio of ~326x.

The number was arithmetically correct and operationally impossible. Same class as everything
else found that day: a figure that is internally consistent while measuring something the
system cannot actually do.

DELIBERATELY NOT FIXED THAT DAY BY SWITCHING THE INSTRUMENT. spec_version stayed ssr-v1 and the
already-scored round trips were left alone; changing point_value mid-study would have mixed
units inside one ledger, which is worse than the disclosure. This file originally pinned that
DEFERRED state (SPEC_VERSION=="ssr-v1", CONFIGS=={"NQ","GC"}) and its own docstrings said, in so
many words: "when this starts failing because CONFIGS moved to MNQ/MGC, the disclosure has been
superseded by a real fix -- update it in that commit, don't delete it quietly."

RESPEC LANDED (2026-08-23, spec_version="ssr-v2"): setup/scripts/ssr_shadow.py's CONFIGS now key
on MNQ/MGC (verified 1/10th point value each -- backtest/futures/instruments.py,
backtest/futures/ssr/ssr_instruments.py). Per the ORIGINAL DEFECT's own "needs its own decision
plus a recompute of history from the recorded points" clause: history was NOT recomputed in
place (that would mix units) -- instead the pre-respec round trips are retained verbatim,
labeled spec_version ssr-v1, and excluded from the arming bar as `legacy_evidence` (a FRESH
forward clock for ssr-v2). Full mechanism + the exhaustive respec guard suite:
backtest/tests/test_ssr_shadow_v2_respec.py. This file is UPDATED (not deleted) to pin the new
state, exactly as its own prior version instructed.

Separately worth remembering (2026-08-13 finding, still true): beats_null was FALSE then and is
UNCHANGED by the respec -- switching contract size is a SIZING fix, not an EXIT-QUALITY fix.
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


def test_fundability_block_exists_and_reports_notional_vs_equity(ssr):
    """THE DISCLOSURE, POST-RESPEC. _fundability now takes (total_pnl_usd,
    latest_close_by_config) and recomputes REAL notional at qty=3 under the live (micro)
    CONFIGS against this book's own recorded equity -- no more static hand-typed snapshot."""
    f = ssr._fundability(150.0, {"MNQ": 29387.75, "MGC": 4680.60})
    for key in ("scored_on", "per_config", "equity_usd", "equity_source",
               "combined_worst_case_notional_usd", "combined_notional_to_equity_ratio",
               "still_leveraged_by_design", "why_it_matters"):
        assert key in f, f"fundability lost its {key} field in the ssr-v2 respec"
    assert set(f["per_config"]) == {"MNQ", "MGC"}
    assert f["per_config"]["MNQ"]["point_value"] == pytest.approx(2.0)
    assert f["per_config"]["MGC"]["point_value"] == pytest.approx(10.0)
    assert f["any_price_missing"] is False
    assert f["combined_notional_to_equity_ratio"] > 0


def test_fundability_is_fail_open_with_no_price_data():
    """compute_progress (and therefore _fundability) is called in many tests/contexts with no
    latest_close_by_config -- must never crash, must disclose the gap rather than fabricate a
    notional figure (C7)."""
    import ssr_shadow as _live
    f = _live._fundability(0.0, {})
    assert f["any_price_missing"] is True
    assert f["combined_worst_case_notional_usd"] is None


def test_the_ratio_matches_the_actual_instrument_registry(ssr):
    """VARY-AND-ASSERT. If the registry's point values change, a hardcoded ratio would
    silently lie. This re-derives it live from the registry via LEGACY_CONFIG_ALIASES rather
    than trusting a bare module-level constant (the pre-respec version of this test trusted
    `_FULL_TO_MICRO_POINT_RATIO`, a constant that no longer exists -- `_fundability` now
    derives this per-config, see `point_value_ratio_vs_full_size` in its output)."""
    from futures.ssr.ssr_instruments import get_ssr
    for micro, full in ssr.LEGACY_CONFIG_ALIASES.items():
        a, b = get_ssr(full).point_value, get_ssr(micro).point_value
        assert a / b == pytest.approx(10.0), (
            f"{full}/{micro} point-value ratio is {a / b}, expected 10.0 -- the disclosed "
            "micro equivalent in _fundability's point_value_ratio_vs_full_size is now wrong")


def test_progress_carries_the_disclosure(ssr):
    """It must ride ON the arming scorecard. A disclosure in a separate file nobody reads is
    not a disclosure."""
    p = ssr.compute_progress([])
    assert "fundability" in p, "compute_progress no longer emits the fundability block"
    assert "arming_bar" in p
    assert "legacy_evidence" in p, "the ssr-v2 respec must also carry the fresh-clock disclosure"


def test_the_spec_version_WAS_bumped_by_the_2026_08_23_respec(ssr):
    """SUPERSEDES this file's own prior pin (which asserted SPEC_VERSION=="ssr-v1" and told
    the next editor to update this test, not delete it, when the instrument switched). The
    instrument DID switch (RESPEC, 2026-08-23) -- spec_version must now be ssr-v2, and the
    pre-respec round trips must be excluded from arming (see legacy_evidence, and the full
    guard suite in test_ssr_shadow_v2_respec.py)."""
    assert ssr.SPEC_VERSION == "ssr-v2", (
        f"SPEC_VERSION is {ssr.SPEC_VERSION}, expected ssr-v2 -- the 2026-08-23 respec to "
        "MNQ/MGC must carry a spec_version bump so pre-respec round trips can be told apart "
        "from post-respec ones (see compute_round_trips' spec_version field).")


def test_configs_are_now_the_micro_contracts(ssr):
    """SUPERSEDES this file's own prior pin (CONFIGS=={"NQ","GC"}). The fundability
    disclosure this file exists to guard has been resolved by the respec -- CONFIGS must now
    key on the micro contracts, never the full-size ones."""
    keys = set(ssr.CONFIGS)
    assert keys == {"MNQ", "MGC"}, (
        f"CONFIGS keys are {sorted(keys)}, expected {{'MGC', 'MNQ'}} -- the ssr-v2 respec "
        "requires CONFIGS to key on the fundable micro contracts.")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

"""Guards for setup/scripts/direction_symmetry_audit.py (2026-08-09).

This instrument exists because J had to notice a config asymmetry in prose that no surface
reported. Its failure mode is therefore NOT crashing -- it is going quietly GREEN while the
asymmetry is still there, which would be worse than not having it. These pin the two things
that would cause that: the direction-pairing logic, and the phantom detector.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "setup" / "scripts" / "direction_symmetry_audit.py"


def _load():
    spec = importlib.util.spec_from_file_location("direction_symmetry_audit", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["direction_symmetry_audit"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def test_script_exists():
    assert SCRIPT.exists()


def test_detects_an_asymmetric_pair_and_names_the_harder_side():
    """A raw number pair is not a finding until it says WHICH side it makes harder."""
    m = _load()
    rows = m.paired_knobs({"filter_10_min_triggers_bull": 2, "filter_10_min_triggers_bear": 1})
    assert len(rows) == 1
    assert rows[0]["bull_value"] == 2 and rows[0]["bear_value"] == 1
    assert "harder to ENTER bull" in rows[0]["note"]


def test_symmetric_pair_is_not_flagged():
    m = _load()
    assert m.paired_knobs({"filter_10_min_triggers_bull": 1,
                           "filter_10_min_triggers_bear": 1}) == []


def test_booleans_are_not_treated_as_numeric_asymmetry():
    """True/False are not a magnitude comparison; flagging them would be noise."""
    m = _load()
    assert m.paired_knobs({"block_bull_thing": True, "block_bear_thing": False}) == []


def test_vix_cap_asymmetry_names_the_narrower_window():
    m = _load()
    rows = m.paired_knobs({"vix_bull_hard_cap": 18.0, "vix_bear_hard_cap": 23.0})
    assert rows and "bull" in rows[0]["note"] and "narrower" in rows[0]["note"]


def test_phantom_detector_catches_a_doc_without_its_knob():
    """THE regression guard. _vix_bull_hard_cap_doc describes a live-sounding bull VIX gate;
    the knob exists nowhere. It was reported to J as a real constraint twice in one hour."""
    m = _load()
    rows = m.phantom_documented_knobs({"_vix_bull_hard_cap_doc": "blocks calls at VIX>=18",
                                       "vix_bear_hard_cap": 23.0})
    phantoms = [r for r in rows if r["classification"] == "PHANTOM"]
    assert len(phantoms) == 1
    assert phantoms[0]["target"] == "vix_bull_hard_cap"


def test_phantom_detector_does_not_cry_wolf_on_trial_notes():
    """_block_elite_bull_trial2_doc documents a TRIAL of the live block_elite_bull key, not a
    missing gate. A detector that flags the repo's own annotation convention gets ignored --
    and an ignored detector is how the real phantom survives."""
    m = _load()
    rows = m.phantom_documented_knobs({"_block_elite_bull_trial2_doc": "trial notes",
                                       "block_elite_bull": False})
    assert [r["classification"] for r in rows] == ["TRIAL_NOTE"]
    assert rows[0]["documents_live_key"] == "block_elite_bull"


def test_doc_whose_knob_exists_is_silent():
    m = _load()
    assert m.phantom_documented_knobs({"_block_elite_bull_doc": "x",
                                       "block_elite_bull": True}) == []


def test_run_on_live_config_is_not_green_while_known_asymmetries_stand():
    """Anti-complacency pin. As of 2026-08-09 the live config carries filter_10 2-vs-1 and
    macro 10-vs-7. If this ever returns GREEN, either those were genuinely fixed (in which
    case update this test deliberately) or the detector broke -- and a silently-broken
    symmetry audit is worse than none."""
    m = _load()
    out = m.run()
    assert out["traffic_light"] in ("GREEN", "YELLOW", "RED")
    if out["traffic_light"] == "GREEN":
        pytest.fail("audit went GREEN -- verify the asymmetries were actually fixed rather "
                    "than the detector silently failing, then update this guard on purpose")
    assert out["not_a_proposal"].startswith("Descriptive only")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

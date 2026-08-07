"""Guard (2026-08-07, LANE 4 week-close): regime_attribution self-heals a
missing target day by invoking the archetype-library builder ONCE, then keeps
the honest UNTAGGED fallback if the rebuild fails.

Root cause pinned: the library is only rebuilt premarket (Gamma_RegimeStamp
06:40 ET), so the 17:45 ET Gamma_RegimeAttribution fire never found the target
day -> structurally UNTAGGED every session (08-05, 08-06 verified).

RED-proof: revert setup/scripts/regime_attribution.py to its pre-fix version
-> both tests fail (AttributeError: module has no _rebuild_library_once).
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import regime_attribution as ra  # noqa: E402


def test_selfheal_attempts_rebuild_on_missing_target(monkeypatch):
    calls: list[int] = []
    lib = {"2026-08-06": {"archetype": "range-chop"}}
    monkeypatch.setattr(ra, "load_library", lambda: dict(lib))
    monkeypatch.setattr(ra, "day_pnl_map",
                        lambda: ({"2026-08-07": 100.0}, {"2026-08-07": []}))
    monkeypatch.setattr(ra, "_rebuild_library_once",
                        lambda: (calls.append(1), False)[1])
    rep = ra.build_report("2026-08-07")
    assert calls == [1], "self-heal rebuild was not attempted on a missing target day"
    assert rep["status"] == "UNTAGGED", "failed rebuild must keep the honest UNTAGGED fallback"


def test_selfheal_uses_rebuilt_library(monkeypatch):
    state = {"n": 0}
    lib_before = {"2026-08-06": {"archetype": "range-chop"}}
    lib_after = {"2026-08-06": {"archetype": "range-chop"},
                 "2026-08-07": {"archetype": "gap-go"}}

    def fake_load():
        state["n"] += 1
        return dict(lib_before if state["n"] == 1 else lib_after)

    monkeypatch.setattr(ra, "load_library", fake_load)
    monkeypatch.setattr(ra, "day_pnl_map",
                        lambda: ({"2026-08-07": 100.0}, {"2026-08-07": []}))
    monkeypatch.setattr(ra, "_rebuild_library_once", lambda: True)
    rep = ra.build_report("2026-08-07")
    assert rep["status"] == "OK", f"expected OK after successful rebuild, got {rep['status']}"
    assert rep["archetype"] == "gap-go"


def test_no_rebuild_when_target_present(monkeypatch):
    """The self-heal must NOT fire when the library already has the day
    (premarket-stamped historical grades stay untouched, zero extra builds)."""
    calls: list[int] = []
    lib = {"2026-08-06": {"archetype": "range-chop"}}
    monkeypatch.setattr(ra, "load_library", lambda: dict(lib))
    monkeypatch.setattr(ra, "day_pnl_map",
                        lambda: ({"2026-08-06": 50.0}, {"2026-08-06": []}))
    monkeypatch.setattr(ra, "_rebuild_library_once",
                        lambda: (calls.append(1), True)[1])
    rep = ra.build_report("2026-08-06")
    assert rep["status"] == "OK"
    assert calls == [], "rebuild must not run when the target day is already tagged"

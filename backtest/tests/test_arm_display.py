"""Guard for setup/scripts/arm_display.py -- the display_name resolver added 2026-07-17
(J: "i dont like how the arms are named currently" -- safe-1/safe-2/safe-3/risky-1/risky-3/
bold-2 carries no meaning and safe-1/safe-2 sharing ONE broker account caused a real
double-count). Arm ids stay the load-bearing key everywhere; this module ONLY resolves a
READ-SURFACE label. Proves: every label shape existing surfaces use resolves correctly,
resolution is fail-open on garbage input, and the resolver reads the REAL accounts.json
(not a hand-rolled copy) so a future arm addition can't silently drift out of sync.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_arm_display.py -q
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))


def _load(name: str, relpath: str):
    path = os.path.join(ROOT, *relpath.split("/"), f"{name}.py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


ad = _load("arm_display", "setup/scripts")

ACCOUNTS_PATH = Path(ROOT) / "automation" / "state" / "fleet" / "accounts.json"


def _real_accounts() -> dict:
    return json.loads(ACCOUNTS_PATH.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# display_name_for_arm_id -- resolves against the REAL accounts.json
# ---------------------------------------------------------------------------

class TestDisplayNameForArmId:
    def test_known_arms_resolve_to_their_pinned_display_names(self):
        expected = {
            # last4s refreshed 2026-08-03/04: J deleted+rebuilt every paper account at
            # $5,000, so the old KIQE/AT40/OB0Q/8G19/X15Q accounts no longer exist. Names
            # are last4-of-live-account by construction (ARM-DISPLAY-NAMES.md); the pins
            # follow accounts.json, which was live-probe verified per arm.
            "safe-2": "CORE-SAFE (46VG)",
            "bold-2": "CORE-BOLD (U67N)",
            "safe-3": "FLEET-TIGHT-S (T20H)",
            "risky-1": "FLEET-FULLSEND-R (V0A4)",  # renamed 2026-07-31 (full-send arm, e28d210c)
            "risky-3": "FLEET-LOOSE-R (5H6Z)",
            "safe-1": "RETIRED (=CORE-SAFE acct 46VG)",
            "mes-mnq-div-futures": "FUTURES-DIV (dormant, 3759)",
        }
        ad._arms(refresh=True)
        for arm_id, name in expected.items():
            assert ad.display_name_for_arm_id(arm_id) == name, arm_id

    def test_unknown_arm_id_falls_back_to_the_raw_id(self):
        assert ad.display_name_for_arm_id("does-not-exist-9000") == "does-not-exist-9000"

    def test_every_arm_in_real_accounts_json_has_a_non_empty_display_name(self):
        """Every arm currently declared in accounts.json must resolve to something OTHER
        than a bare fallback of itself missing entirely -- i.e. display_name is actually
        set on every arm (not just the active ones), so this file never silently drifts as
        new arms are added."""
        accounts = _real_accounts()
        missing = [a["id"] for a in accounts["arms"] if not a.get("display_name")]
        assert not missing, f"arm(s) with no display_name set: {missing}"


# ---------------------------------------------------------------------------
# display_name_for_label -- the label shapes existing read surfaces actually emit
# ---------------------------------------------------------------------------

class TestDisplayNameForLabel:
    def test_core_short_labels(self):
        ad._arms(refresh=True)
        assert ad.display_name_for_label("safe") == "CORE-SAFE (46VG)"
        assert ad.display_name_for_label("bold") == "CORE-BOLD (U67N)"

    def test_core_prefixed_labels_from_fill_funnel(self):
        assert ad.display_name_for_label("core:safe") == "CORE-SAFE (46VG)"
        assert ad.display_name_for_label("core:bold") == "CORE-BOLD (U67N)"

    def test_fleet_prefixed_labels_from_fill_funnel(self):
        assert ad.display_name_for_label("fleet:safe-3") == "FLEET-TIGHT-S (T20H)"
        assert ad.display_name_for_label("fleet:risky-1") == "FLEET-FULLSEND-R (V0A4)"

    def test_bare_arm_id_passthrough(self):
        assert ad.display_name_for_label("safe-2") == "CORE-SAFE (46VG)"

    def test_crypto_twin_labels(self):
        assert ad.display_name_for_label("crypto-twin") == "CRYPTO-TWIN"
        assert ad.display_name_for_label("twin") == "CRYPTO-TWIN"

    def test_unknown_label_passes_through_unchanged(self):
        assert ad.display_name_for_label("some-future-thing") == "some-future-thing"

    def test_empty_and_non_string_input_fail_open(self):
        assert ad.display_name_for_label("") == ""
        assert ad.display_name_for_label(None) is None


# ---------------------------------------------------------------------------
# fail-open on a broken accounts.json (never crash a read surface)
# ---------------------------------------------------------------------------

class TestFailOpen:
    def test_missing_accounts_json_fails_open(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ad, "ACCOUNTS_PATH", tmp_path / "does-not-exist.json")
        ad._arms(refresh=True)
        assert ad.display_name_for_arm_id("safe-2") == "safe-2"
        # restore the real cache for any test running after this one
        ad._arms(refresh=True)

    def test_corrupt_accounts_json_fails_open(self, tmp_path, monkeypatch):
        bad = tmp_path / "accounts.json"
        bad.write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr(ad, "ACCOUNTS_PATH", bad)
        ad._arms(refresh=True)
        assert ad.display_name_for_arm_id("safe-2") == "safe-2"
        ad._arms(refresh=True)

"""RECENCY-CONDITIONED MIN-SIZING (2026-07-10 ship) -- guards for
fleet_executor._recency_verdict / _apply_recency_min_sizing and their wiring into all 3
_qty_for call sites (plan_entry, _plan_from_strategies' FIX2 path, plan_all's side-block
fallback path).

A/B: analysis/recommendations/recency-sizing-ab.json (policy_dominates=true, 8 REAL
fleet-fill trading days 2026-06-29..2026-07-09, total -$1,274 -> -$793, worst day -$388 ->
-$297, point-in-time verdicts / no look-ahead leak). Staged mechanism:
analysis/recommendations/recency-sizing-proposal.json. Only the RED->floor branch ships
(the A/B's own ALL_RED_CAVEAT: every sampled day verdicted RED, so YELLOW/GREEN
differentiation is unproven and deliberately NOT implemented here).

Runs under pytest OR standalone (`python test_recency_min_sizing.py`), mirroring
test_structure_stop_wiring.py's tmp_path/monkeypatch shim.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]  # automation/state/fleet/<this file> -> repo root
FLEET = REPO / "automation" / "state" / "fleet"
sys.path.insert(0, str(FLEET))

import fleet_executor as fx  # noqa: E402

SIZING = [{"equity_min": 0, "equity_max": 1e9, "base_qty": 5, "elite_qty": 5}]
PARAMS_ON = {"position_sizing_tiers": SIZING, "min_contracts": 3, "recency_min_size_enabled": True}
PARAMS_OFF = {"position_sizing_tiers": SIZING, "min_contracts": 3}  # flag absent -> default False
ARM = {"id": "safe-loose", "gate_override": {}}


def _write_recency(tmp_path, any_red, confirmed):
    p = tmp_path / "recency-confirmation.json"
    p.write_text(json.dumps({"headline": {"any_red": any_red,
                                          "edges_confirmed_on_recent": confirmed}}),
                encoding="utf-8")
    return p


# === _recency_verdict: tri-state reader of the SAME field the capital gates read ============
def test_recency_verdict_red_when_any_red_true(tmp_path):
    p = _write_recency(tmp_path, any_red=True, confirmed=False)
    assert fx._recency_verdict(p) == "RED"


def test_recency_verdict_green_when_confirmed_and_not_red(tmp_path):
    p = _write_recency(tmp_path, any_red=False, confirmed=True)
    assert fx._recency_verdict(p) == "GREEN"


def test_recency_verdict_yellow_when_neither(tmp_path):
    p = _write_recency(tmp_path, any_red=False, confirmed=False)
    assert fx._recency_verdict(p) == "YELLOW"


def test_recency_verdict_red_wins_if_both_true(tmp_path):
    """any_red is checked FIRST -- a malformed producer state (both true) still reads RED,
    the conservative direction (mirrors recency_check.append_status's own state derivation)."""
    p = _write_recency(tmp_path, any_red=True, confirmed=True)
    assert fx._recency_verdict(p) == "RED"


def test_recency_verdict_fails_open_missing_file(tmp_path):
    assert fx._recency_verdict(tmp_path / "does-not-exist.json") == "YELLOW"


def test_recency_verdict_fails_open_malformed_json(tmp_path):
    p = tmp_path / "bad.json"
    p.write_text("{not valid json", encoding="utf-8")
    assert fx._recency_verdict(p) == "YELLOW"


def test_recency_verdict_fails_open_headline_not_a_dict(tmp_path):
    p = tmp_path / "weird.json"
    p.write_text(json.dumps({"headline": "not-a-dict"}), encoding="utf-8")
    assert fx._recency_verdict(p) == "YELLOW"


def test_recency_verdict_fails_open_root_not_a_dict(tmp_path):
    p = tmp_path / "list.json"
    p.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
    assert fx._recency_verdict(p) == "YELLOW"


# === _apply_recency_min_sizing: the sizing decision (unit-level, monkeypatched path) =========
def test_apply_clamps_on_red(tmp_path, monkeypatch):
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", _write_recency(tmp_path, True, False))
    qty, note = fx._apply_recency_min_sizing(5, "ribbon_ride", PARAMS_ON)
    assert qty == 3
    assert note == "qty clamped 5->3: recency RED"


def test_apply_unchanged_on_green(tmp_path, monkeypatch):
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", _write_recency(tmp_path, False, True))
    qty, note = fx._apply_recency_min_sizing(5, "ribbon_ride", PARAMS_ON)
    assert qty == 5 and note is None


def test_apply_unchanged_on_yellow(tmp_path, monkeypatch):
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", _write_recency(tmp_path, False, False))
    qty, note = fx._apply_recency_min_sizing(5, "ribbon_ride", PARAMS_ON)
    assert qty == 5 and note is None


def test_apply_unchanged_when_flag_absent(tmp_path, monkeypatch):
    """RED verdict but the flag key is ABSENT (default False) -> byte-identical, no clamp."""
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", _write_recency(tmp_path, True, False))
    qty, note = fx._apply_recency_min_sizing(5, "ribbon_ride", PARAMS_OFF)
    assert qty == 5 and note is None


def test_apply_unchanged_when_flag_explicitly_false(tmp_path, monkeypatch):
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", _write_recency(tmp_path, True, False))
    params = {**PARAMS_ON, "recency_min_size_enabled": False}
    qty, note = fx._apply_recency_min_sizing(5, "ribbon_ride", params)
    assert qty == 5 and note is None


def test_apply_unchanged_for_vwap_continuation_even_when_red_and_enabled(tmp_path, monkeypatch):
    """Scope: ribbon_ride ONLY -- vwap_continuation passes through untouched even with the
    flag on and a RED verdict (task: 'do NOT touch vwap_continuation sizing')."""
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", _write_recency(tmp_path, True, False))
    qty, note = fx._apply_recency_min_sizing(5, "vwap_continuation", PARAMS_ON)
    assert qty == 5 and note is None


def test_apply_unchanged_when_qty_is_none(tmp_path, monkeypatch):
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", _write_recency(tmp_path, True, False))
    qty, note = fx._apply_recency_min_sizing(None, "ribbon_ride", PARAMS_ON)
    assert qty is None and note is None


def test_apply_missing_recency_file_fails_open_unchanged(tmp_path, monkeypatch):
    """flag ON but the recency file does not exist -> fail-open (YELLOW) -> normal sizing,
    never a block, never a clamp."""
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", tmp_path / "does-not-exist.json")
    qty, note = fx._apply_recency_min_sizing(5, "ribbon_ride", PARAMS_ON)
    assert qty == 5 and note is None


def test_apply_no_note_when_qty_already_at_or_below_floor(tmp_path, monkeypatch):
    """qty already <= min_contracts on a RED verdict -> min() leaves it alone (a ceiling,
    never a floor-RAISE), and no clamp_note fires (nothing actually changed)."""
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", _write_recency(tmp_path, True, False))
    qty, note = fx._apply_recency_min_sizing(3, "ribbon_ride", PARAMS_ON)
    assert qty == 3 and note is None
    qty2, note2 = fx._apply_recency_min_sizing(2, "ribbon_ride", PARAMS_ON)
    assert qty2 == 2 and note2 is None  # below floor already -> untouched, never raised


# === wired end-to-end through the 3 real _qty_for call sites (non-vacuous bites) =============
def _fix2_signal(name, side="P", setup="BEARISH_REJECTION_RIDE_THE_RIBBON"):
    return {"spot": 600.0, "strategies": [
        {"name": name, "side": side, "setup": setup, "triggers": ["t1", "t2"],
         "quality": "BASE", "est_premium": None, "spot": 600.0}]}


def test_plan_all_fix2_path_clamps_ribbon_on_red(tmp_path, monkeypatch):
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", _write_recency(tmp_path, True, False))
    plans = fx.plan_all(ARM, _fix2_signal("ribbon_ride"), 2000.0, PARAMS_ON)
    enter = [p for p in plans if p.action == "ENTER"]
    assert len(enter) == 1 and enter[0].qty == 3
    assert "qty clamped 5->3: recency RED" in enter[0].reason


def test_plan_all_fix2_path_vwap_continuation_unaffected_on_red(tmp_path, monkeypatch):
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", _write_recency(tmp_path, True, False))
    plans = fx.plan_all(ARM, _fix2_signal("vwap_continuation", setup="VWAP_CONTINUATION"),
                        2000.0, PARAMS_ON)
    enter = [p for p in plans if p.action == "ENTER"]
    assert len(enter) == 1 and enter[0].qty == 5
    assert "clamped" not in enter[0].reason


def test_plan_all_side_block_fallback_clamps_on_red(tmp_path, monkeypatch):
    """No strategies[] key -> the v1 bear/bull side-block fallback loop inside plan_all."""
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", _write_recency(tmp_path, True, False))
    sig = {"spot": 600.0,
           "bear": {"passed": True, "triggers_fired": ["t1", "t2"],
                    "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON"},
           "bull": {"passed": False}}
    plans = fx.plan_all(ARM, sig, 2000.0, PARAMS_ON)
    enter = [p for p in plans if p.action == "ENTER"]
    assert len(enter) == 1 and enter[0].qty == 3
    assert "qty clamped 5->3: recency RED" in enter[0].reason


def test_plan_entry_clamps_on_red(tmp_path, monkeypatch):
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", _write_recency(tmp_path, True, False))
    sig = {"spot": 600.0, "production_action": "ENTER_BEAR",
          "bear": {"passed": True, "triggers_fired": ["t1", "t2"],
                    "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON"},
          "bull": {"passed": False}}
    plan = fx.plan_entry(ARM, sig, 2000.0, PARAMS_ON)
    assert plan.action == "ENTER" and plan.qty == 3
    assert "qty clamped 5->3: recency RED" in plan.reason


def test_plan_entry_green_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", _write_recency(tmp_path, False, True))
    sig = {"spot": 600.0, "production_action": "ENTER_BEAR",
          "bear": {"passed": True, "triggers_fired": ["t1", "t2"],
                    "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON"},
          "bull": {"passed": False}}
    plan = fx.plan_entry(ARM, sig, 2000.0, PARAMS_ON)
    assert plan.action == "ENTER" and plan.qty == 5


def test_plan_all_flag_off_byte_identical(tmp_path, monkeypatch):
    """vary-and-assert (C14): with the flag OFF, a RED-verdict recency file produces a plan
    byte-identical (every field) to a flag-off run against NO recency file at all -- proves
    this ships as a true no-op until armed."""
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", _write_recency(tmp_path, True, False))
    with_red_file = fx.plan_all(ARM, _fix2_signal("ribbon_ride"), 2000.0, PARAMS_OFF)

    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", tmp_path / "does-not-exist.json")
    without_file = fx.plan_all(ARM, _fix2_signal("ribbon_ride"), 2000.0, PARAMS_OFF)

    assert len(with_red_file) == len(without_file) == 1
    a, b = with_red_file[0], without_file[0]
    for field in ("arm_id", "action", "side", "setup_name", "strike", "qty", "quality",
                  "reason", "strategy", "exit_shape", "trigger_level"):
        assert getattr(a, field) == getattr(b, field), (
            f"{field} differs with flag off: {getattr(a, field)!r} vs {getattr(b, field)!r}")
    assert a.qty == 5  # tier value, never clamped while the flag is off


def test_plan_all_missing_recency_file_end_to_end_unchanged(tmp_path, monkeypatch):
    monkeypatch.setattr(fx, "RECENCY_CONFIRMATION_PATH", tmp_path / "does-not-exist.json")
    plans = fx.plan_all(ARM, _fix2_signal("ribbon_ride"), 2000.0, PARAMS_ON)
    enter = [p for p in plans if p.action == "ENTER"]
    assert len(enter) == 1 and enter[0].qty == 5  # fail-open: never clamps on a missing file


# === live params files: the flag actually shipped, with the documented shape =================
def test_live_params_both_files_carry_the_flag_true_with_doc():
    for path, expected_min in ((fx.PARAMS_SAFE, 3), (fx.PARAMS_BOLD, 5)):
        params = json.loads(path.read_text(encoding="utf-8"))
        assert params.get("recency_min_size_enabled") is True, f"{path} must ship the flag armed"
        assert isinstance(params.get("_recency_min_size_enabled_doc"), str) and \
            len(params["_recency_min_size_enabled_doc"]) > 40, f"{path} missing the _doc sibling"
        assert params.get("min_contracts") == expected_min


if __name__ == "__main__":
    import tempfile

    class _MP:
        def __init__(self):
            self._undo = []
        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)
        def undo(self):
            for obj, name, old in reversed(self._undo):
                setattr(obj, name, old)
            self._undo = []

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        mp = _MP()
        argn = t.__code__.co_varnames[: t.__code__.co_argcount]
        try:
            with tempfile.TemporaryDirectory() as td:
                kw = {}
                if "tmp_path" in argn:
                    kw["tmp_path"] = Path(td)
                if "monkeypatch" in argn:
                    kw["monkeypatch"] = mp
                t(**kw)
            print(f"PASS  {t.__name__}"); passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}"); failed += 1
        finally:
            mp.undo()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)

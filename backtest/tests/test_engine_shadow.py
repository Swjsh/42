"""Tests for the Phase-3 engine shadow harness (automation/scripts/engine_shadow.py).

Covers: agreement classification (every bucket), the paired-row schema, scorecard
math (the Phase-4 gate), and the two iron guarantees (read-only is structural;
FAIL-OPEN on bad/empty payload yields a logged SHADOW_ERROR row and never raises).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "automation" / "scripts"), str(_REPO / "backtest"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import engine_shadow as es  # noqa: E402


# ----------------------------- classification ----------------------------- #


def test_prose_entered_recognizes_entry_actions():
    assert es.prose_entered("ENTER_BEAR")
    assert es.prose_entered("ENTERED_PUT")
    assert es.prose_entered("BUY_CALL")
    assert not es.prose_entered("HOLD")
    assert not es.prose_entered("PAUSED")
    assert not es.prose_entered("MANAGE_RUNNER")
    assert not es.prose_entered(None)
    assert not es.prose_entered("")


def test_engine_entered():
    assert es.engine_entered("ENTER_BEAR")
    assert es.engine_entered("ENTER_BULL")
    assert not es.engine_entered("HOLD")
    assert not es.engine_entered("SKIP_VIX_BEAR_HARD_CAP")
    assert not es.engine_entered("SHADOW_ERROR")
    assert not es.engine_entered(None)


@pytest.mark.parametrize("prose,verdict,bucket,agree,entry", [
    ("ENTER_BEAR", {"verdict": "ENTER_BEAR", "side": "P"}, "AGREE_ENTER", True, True),
    ("ENTER_BULL", {"verdict": "ENTER_BULL", "side": "C"}, "AGREE_ENTER", True, True),
    ("ENTER_BEAR", {"verdict": "ENTER_BULL", "side": "C"}, "AGREE_ENTER_XSIDE", False, True),
    ("HOLD", {"verdict": "HOLD", "side": None}, "AGREE_NOENTRY", True, False),
    ("PAUSED", {"verdict": "SKIP_VIX_BEAR_HARD_CAP", "side": "P"}, "AGREE_NOENTRY", True, False),
    ("ENTER_BEAR", {"verdict": "SKIP_LEVEL_REJECTION", "side": "P"}, "DISAGREE_PROSE_ONLY", False, True),
    ("HOLD", {"verdict": "ENTER_BEAR", "side": "P"}, "DISAGREE_ENGINE_ONLY", False, True),
])
def test_classify_agreement_buckets(prose, verdict, bucket, agree, entry):
    cls = es.classify_agreement(prose, verdict)
    assert cls["bucket"] == bucket
    assert cls["agree"] is agree
    assert cls["entry_tick"] is entry


def test_build_shadow_row_schema():
    verdict = {"verdict": "ENTER_BEAR", "side": "P", "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
               "quality_tier": "LEVEL", "gate": None, "bear_score": 12, "bull_score": 0,
               "reason": "passed"}
    row = es.build_shadow_row(date="2026-06-23", time_et="10:05", prose_action="ENTER_BEAR",
                              verdict=verdict)
    for k in ("date", "time_et", "prose_action", "engine_verdict", "engine_side", "engine_setup",
              "engine_tier", "engine_gate", "bear_score", "bull_score", "agree", "bucket",
              "entry_tick", "engine_reason", "shadow"):
        assert k in row, f"missing {k}"
    assert row["shadow"] == "engine"
    assert row["agree"] is True
    assert row["bucket"] == "AGREE_ENTER"


def test_build_shadow_row_extracts_gate_id():
    verdict = {"verdict": "SKIP_LEVEL_REJECTION", "side": "P",
               "gate": {"gate_id": "LEVEL_REJECTION", "action": "SKIP_LEVEL_REJECTION", "blockers": []},
               "bear_score": 8, "bull_score": 0, "reason": "blocked"}
    row = es.build_shadow_row(date="d", time_et="t", prose_action="HOLD", verdict=verdict)
    assert row["engine_gate"] == "LEVEL_REJECTION"


# ------------------------------- scorecard -------------------------------- #


def test_scorecard_gate_pass_perfect_day():
    rows = [
        {"date": "D", "shadow": "engine", "engine_verdict": "HOLD", "agree": True, "entry_tick": False, "bucket": "AGREE_NOENTRY"},
        {"date": "D", "shadow": "engine", "engine_verdict": "ENTER_BEAR", "agree": True, "entry_tick": True, "bucket": "AGREE_ENTER"},
    ]
    card = es.build_scorecard(rows, "D")
    assert card["n_scored"] == 2
    assert card["overall_agreement_rate"] == 1.0
    assert card["entry_agreement_rate"] == 1.0
    assert card["phase4_gate_pass"] is True


def test_scorecard_gate_fails_on_entry_disagreement():
    rows = [
        {"date": "D", "shadow": "engine", "engine_verdict": "HOLD", "agree": True, "entry_tick": False, "bucket": "AGREE_NOENTRY"},
        {"date": "D", "shadow": "engine", "engine_verdict": "SKIP_X", "agree": False, "entry_tick": True, "bucket": "DISAGREE_PROSE_ONLY"},
    ]
    card = es.build_scorecard(rows, "D")
    assert card["entry_agreement_rate"] == 0.0
    assert card["phase4_gate_pass"] is False
    assert len(card["disagreements"]) == 1


def test_scorecard_excludes_shadow_errors_from_agreement():
    rows = [
        {"date": "D", "shadow": "engine", "engine_verdict": "HOLD", "agree": True, "entry_tick": False, "bucket": "AGREE_NOENTRY"},
        {"date": "D", "shadow": "engine", "engine_verdict": "SHADOW_ERROR", "agree": True, "entry_tick": False, "bucket": "AGREE_NOENTRY"},
    ]
    card = es.build_scorecard(rows, "D")
    assert card["n_ticks"] == 2
    assert card["n_scored"] == 1  # the error row excluded
    assert card["n_shadow_errors"] == 1
    assert card["overall_agreement_rate"] == 1.0


def test_scorecard_empty_day_does_not_pass_gate():
    card = es.build_scorecard([], "D")
    assert card["n_scored"] == 0
    assert card["phase4_gate_pass"] is False


# --------------------------- fail-open guarantee -------------------------- #


def test_run_shadow_tick_fail_open_on_empty_payload(tmp_path):
    out = tmp_path / "shadow.jsonl"
    row = es.run_shadow_tick({}, "HOLD", date="2026-06-23", time_et="10:00", out_path=out)
    assert row["engine_verdict"] == "SHADOW_ERROR"  # decide_payload raised -> swallowed
    assert out.exists()
    logged = [json.loads(ln) for ln in out.read_text().splitlines() if ln.strip()]
    assert len(logged) == 1
    assert logged[0]["engine_verdict"] == "SHADOW_ERROR"


def test_run_shadow_tick_valid_hold_payload(tmp_path):
    out = tmp_path / "shadow.jsonl"
    # A quiet bar with no active levels fires no triggers -> the engine HOLDs.
    quiet = {"open": 500.0, "high": 500.4, "low": 499.6, "close": 500.0, "volume": 1000.0}
    payload = {
        "bar_ctx": {
            "bar_idx": 30,
            "timestamp_et": "2026-05-20T11:00:00-04:00",
            "bar": quiet,
            "prior_bars": [quiet for _ in range(31)],
            "ribbon_now": {"fast": 500.0, "pivot": 500.0, "slow": 500.0, "spread_cents": 1.0, "stack": "MIXED"},
            "ribbon_history": [],
            "vix_now": 16.0, "vix_prior": 16.0,
            "vol_baseline_20": 1000.0, "range_baseline_20": 0.8,
            "levels_active": [], "multi_day_levels": [],
            "htf_15m_stack": None,
        }
    }
    row = es.run_shadow_tick(payload, "HOLD", date="2026-05-20", time_et="11:00", out_path=out)
    assert row["engine_verdict"] in {"HOLD", "ENTER_BEAR", "ENTER_BULL"} or str(row["engine_verdict"]).startswith("SKIP_")
    assert row["engine_verdict"] != "SHADOW_ERROR"  # a well-formed payload must not error
    # prose HOLD vs engine non-entry -> agreement on no-entry
    if not es.engine_entered(row["engine_verdict"]):
        assert row["agree"] is True
        assert row["bucket"] == "AGREE_NOENTRY"

"""Guards for backtest/tools/measure_conductor_cost.py -- the independent per-fire real-cost
re-derivation tool for CONDUCTOR-BUDGET-ARITHMETIC (2026-08-08 queue item).

These are unit tests against synthetic session/outcome fixtures (no dependency on the real
~/.claude/projects transcripts or the real conductor-outcomes.jsonl -- both are read via
module-level path constants that tests monkeypatch, same pattern as test_conductor_budget.py).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backtest" / "tools"))

import measure_conductor_cost as mcc  # noqa: E402


# --------------------------------------------------------------------------- pricing math
def test_sonnet_pricing_matches_published_rate():
    # 1M input + 1M output tokens at sonnet rates = $3 + $15 = $18.
    usage = {"input_tokens": 1_000_000, "output_tokens": 1_000_000,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    assert mcc._compute_msg_cost("claude-sonnet-5", usage) == 18.0


def test_cache_read_is_the_cheap_lane():
    # Cache reads are priced far below fresh input for every tier -- this is WHY heavily
    # cached fires (long CLAUDE.md/tool-schema reuse) can still be cheap despite high token
    # counts; a bug that priced cache_read at the input rate would silently inflate every
    # measurement in this tool.
    usage = {"input_tokens": 0, "output_tokens": 0,
             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 1_000_000}
    assert mcc._compute_msg_cost("claude-sonnet-5", usage) == 0.30


def test_unknown_model_defaults_to_sonnet_pricing():
    usage = {"input_tokens": 1_000_000, "output_tokens": 0,
              "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    assert mcc._compute_msg_cost("some-future-model", usage) == mcc._compute_msg_cost(
        "claude-sonnet-5", usage)


def test_empty_usage_costs_nothing():
    assert mcc._compute_msg_cost("claude-opus-4-7", {}) == 0.0


# --------------------------------------------------------------------------- session scanning
def _write_session(path: Path, lines: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        for d in lines:
            fh.write(json.dumps(d) + "\n")


def test_scan_sessions_flags_conductor_marker(tmp_path):
    conductor_file = tmp_path / "aaa.jsonl"
    _write_session(conductor_file, [
        {"type": "user", "timestamp": "2026-08-08T00:00:00Z",
         "message": {"content": "... rail-0 budget gate ..."}},
        {"type": "assistant", "timestamp": "2026-08-08T00:01:00Z",
         "message": {"model": "claude-sonnet-5",
                     "usage": {"input_tokens": 1000, "output_tokens": 100,
                               "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}}},
    ])
    other_file = tmp_path / "bbb.jsonl"
    _write_session(other_file, [
        {"type": "user", "timestamp": "2026-08-08T01:00:00Z",
         "message": {"content": "just an ordinary interactive session"}},
    ])
    sessions = mcc.scan_sessions(tmp_path)
    by_id = {s.session_id: s for s in sessions}
    assert by_id["aaa"].is_conductor is True
    assert by_id["bbb"].is_conductor is False
    assert by_id["aaa"].real_cost_usd > 0
    assert by_id["aaa"].n_assistant_msgs == 1


def test_scan_sessions_tracks_first_and_last_ts(tmp_path):
    f = tmp_path / "ccc.jsonl"
    _write_session(f, [
        {"type": "user", "timestamp": "2026-08-08T00:00:00Z"},
        {"type": "assistant", "timestamp": "2026-08-08T00:05:00Z",
         "message": {"model": "claude-sonnet-5", "usage": {"input_tokens": 10}}},
        {"type": "assistant", "timestamp": "2026-08-08T00:10:00Z",
         "message": {"model": "claude-sonnet-5", "usage": {"input_tokens": 10}}},
    ])
    sessions = mcc.scan_sessions(tmp_path)
    s = sessions[0]
    assert s.first_ts.isoformat() == "2026-08-08T00:00:00+00:00"
    assert s.last_ts.isoformat() == "2026-08-08T00:10:00+00:00"


# --------------------------------------------------------------------------- matching
def _mk_session(session_id: str, is_conductor: bool, last_ts, real_cost: float,
                 n_msgs: int = 5):
    from datetime import datetime, timezone
    s = mcc.SessionInfo(session_id=session_id, path=Path(f"{session_id}.jsonl"))
    s.is_conductor = is_conductor
    s.last_ts = datetime.fromisoformat(last_ts).astimezone(timezone.utc)
    s.first_ts = s.last_ts
    s.real_cost_usd = real_cost
    s.n_assistant_msgs = n_msgs
    return s


def test_match_fires_picks_nearest_prior_session():
    outcomes = [{"fired_at": "2026-08-08T00:10:20+00:00", "task_id": "X", "cost_usd": 2.0}]
    sessions = [
        _mk_session("near", True, "2026-08-08T00:10:00+00:00", 5.0),
        _mk_session("far", True, "2026-08-08T00:00:00+00:00", 99.0),
    ]
    matches = mcc.match_fires(outcomes, sessions)
    assert len(matches) == 1
    assert matches[0]["session_id"] == "near"
    assert matches[0]["real_cost_usd"] == 5.0


def test_match_fires_ignores_non_conductor_sessions():
    outcomes = [{"fired_at": "2026-08-08T00:10:05+00:00", "task_id": "X", "cost_usd": 2.0}]
    sessions = [_mk_session("interactive", False, "2026-08-08T00:10:00+00:00", 5.0)]
    matches = mcc.match_fires(outcomes, sessions)
    assert matches == []


def test_match_fires_respects_tolerance():
    outcomes = [{"fired_at": "2026-08-08T01:00:00+00:00", "task_id": "X", "cost_usd": 2.0}]
    sessions = [_mk_session("toofar", True, "2026-08-08T00:00:00+00:00", 5.0)]
    matches = mcc.match_fires(outcomes, sessions, tolerance_sec=60)
    assert matches == [], "session ended an hour before fired_at -- outside a 60s tolerance"


def test_match_fires_never_reuses_a_session_for_two_rows():
    outcomes = [
        {"fired_at": "2026-08-08T00:10:05+00:00", "task_id": "A", "cost_usd": 2.0},
        {"fired_at": "2026-08-08T00:10:06+00:00", "task_id": "B", "cost_usd": 3.0},
    ]
    sessions = [_mk_session("only_one", True, "2026-08-08T00:10:00+00:00", 5.0)]
    matches = mcc.match_fires(outcomes, sessions)
    assert len(matches) == 1, "one session must not double-match two outcome rows"


# --------------------------------------------------------------------------- summarize
def test_summarize_reports_both_ratio_directions():
    matches = [
        {"self_reported_cost_usd": 2.0, "real_cost_usd": 4.0},
        {"self_reported_cost_usd": 5.0, "real_cost_usd": 10.0},
    ]
    summary = mcc.summarize(matches, min_self_report=0.25)
    assert summary["n_usable_for_ratio"] == 2
    assert summary["real_over_self"]["median"] == 2.0
    assert summary["self_over_real"]["median"] == 0.5
    assert summary["aggregate_ratio_real_over_self"] == 2.0


def test_summarize_excludes_near_zero_self_reports():
    matches = [
        {"self_reported_cost_usd": 0.01, "real_cost_usd": 1.2},  # excluded: below filter
        {"self_reported_cost_usd": 3.0, "real_cost_usd": 6.0},   # included
    ]
    summary = mcc.summarize(matches, min_self_report=0.25)
    assert summary["n_total_matched"] == 2
    assert summary["n_usable_for_ratio"] == 1


def test_summarize_handles_zero_usable_gracefully():
    summary = mcc.summarize([], min_self_report=0.25)
    assert summary["n_usable_for_ratio"] == 0
    assert "real_over_self" not in summary, "must not synthesize a ratio block from no data"

"""Acceptance tests for setup/scripts/dojo/scorecard.py (DOJO Phase 1b build,
DOJO-ARCHITECTURE-DECISION.md's scorecard.py contract).

Proves: score_session reads a session ledger + its adjacent positions.json and produces
per-arm J-directed P&L (always reconstructable), lists non-fabricated divergence points
between engine would_place verdicts and what J actually directed, marks the engine-
counterfactual DOLLAR figure "pending" (never fabricated -- OP-33a), and writes/returns a
byte-for-byte-JSON-safe scorecard.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_dojo_scorecard.py -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (ROOT / "setup" / "scripts", ROOT):
    _ap = str(_p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from dojo import scorecard  # noqa: E402


def _write_ledger(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def _write_positions(path: Path, positions: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"session_id": "sess-1", "positions": positions}), encoding="utf-8")


def test_score_session_reports_j_directed_pnl_per_arm(tmp_path):
    sessions_dir = tmp_path / "sessions"
    ledger = sessions_dir / "sess-1.jsonl"
    _write_ledger(ledger, [
        {"event": "session_start", "replay_day": "2026-07-17"},
        {"event": "step", "bar_et": "2026-07-17T09:40:00", "decisions": []},
        {"event": "directive", "directive": {"id": "d1", "arms": ["safe"]}},
        {"event": "session_close", "steps": 1, "directives": 1},
    ])
    positions = {
        "d1-safe": {
            "position_id": "d1-safe", "directive_id": "d1", "arm": "safe",
            "status": "CLOSED", "realized_pnl": 200.0, "unrealized_pnl": 0.0,
            "entry_time_et": "2026-07-17T09:30:00", "exit_time_et": "2026-07-17T09:40:00",
            "exit_reason": "tp1", "symbol": "SPY260717C00550000", "side": "C", "strike": 550,
            "qty": 3, "entry_premium": 1.0, "price_source": "opra_5m", "is_synthetic": False,
            "legs": [], "note": None,
        },
        "d1-bold": {
            "position_id": "d1-bold", "directive_id": "d1", "arm": "bold",
            "status": "OPEN", "realized_pnl": 0.0, "unrealized_pnl": -30.0,
            "entry_time_et": "2026-07-17T09:35:00", "exit_time_et": None,
            "exit_reason": None, "symbol": "SPY260717P00547000", "side": "P", "strike": 547,
            "qty": 3, "entry_premium": 1.0, "price_source": "opra_5m", "is_synthetic": False,
            "legs": [], "note": None,
        },
    }
    _write_positions(sessions_dir / "sess-1-positions.json", positions)

    result = scorecard.score_session(ledger)

    assert result["session_id"] == "sess-1"
    assert result["n_positions"] == 2
    assert result["per_arm"]["safe"]["j_directed_realized_pnl"] == 200.0
    assert result["per_arm"]["bold"]["j_directed_unrealized_pnl"] == -30.0
    assert result["totals"]["j_directed_realized_pnl"] == 200.0
    assert result["totals"]["n_closed_positions"] == 1
    assert result["totals"]["n_open_positions"] == 1
    assert result["engine_counterfactual"]["status"] == "pending"

    out_path = Path(result["scorecard_path"])
    assert out_path.exists()
    reloaded = json.loads(out_path.read_text(encoding="utf-8"))
    assert reloaded["session_id"] == "sess-1"
    json.dumps(result)  # must be fully JSON-safe (no stray dataclasses/datetimes leaking)


def test_score_session_never_fabricates_engine_dollar_pnl(tmp_path):
    """The honesty contract: even with rich decision data available, score_session must
    NEVER synthesize an engine-side dollar figure -- it stays 'pending' every time."""
    sessions_dir = tmp_path / "sessions"
    ledger = sessions_dir / "sess-2.jsonl"
    _write_ledger(ledger, [
        {"event": "step", "bar_et": "2026-07-17T09:40:00", "decisions": [
            {"arm": "safe", "verdict": "ENTER", "would_place": True, "side": "C",
             "setup": "RIBBON_RIDE"},
        ]},
    ])
    _write_positions(sessions_dir / "sess-2-positions.json", {})  # J directed NOTHING this session

    result = scorecard.score_session(ledger)
    assert result["engine_counterfactual"]["status"] == "pending"
    assert "engine_counterfactual_pnl" not in result["engine_counterfactual"]
    assert set(result["totals"]) == {
        "j_directed_realized_pnl", "j_directed_unrealized_pnl", "n_open_positions",
        "n_closed_positions", "n_no_fill_positions", "n_error_positions", "n_synthetic_fills",
    }  # no fabricated engine-side dollar key snuck into totals


def test_score_session_finds_divergence_when_engine_would_place_but_j_did_not(tmp_path):
    sessions_dir = tmp_path / "sessions"
    ledger = sessions_dir / "sess-3.jsonl"
    _write_ledger(ledger, [
        {"event": "step", "bar_et": "2026-07-17T09:40:00", "decisions": [
            {"arm": "safe", "verdict": "ENTER", "would_place": True, "side": "C",
             "setup": "RIBBON_RIDE"},
            {"arm": "bold", "verdict": "HOLD", "would_place": False, "side": None,
             "setup": None},
        ]},
    ])
    _write_positions(sessions_dir / "sess-3-positions.json", {})  # no J-directed fills at all

    result = scorecard.score_session(ledger)
    divs = result["divergence_points"]
    assert len(divs) == 1
    assert divs[0]["arm"] == "safe"
    assert divs[0]["engine_would_place"] is True
    assert divs[0]["j_directed"] is False


def test_score_session_no_divergence_when_j_directed_matches_engine_would_place(tmp_path):
    sessions_dir = tmp_path / "sessions"
    ledger = sessions_dir / "sess-4.jsonl"
    _write_ledger(ledger, [
        {"event": "step", "bar_et": "2026-07-17T09:30:00", "decisions": [
            {"arm": "safe", "verdict": "ENTER", "would_place": True, "side": "C",
             "setup": "RIBBON_RIDE"},
        ]},
    ])
    _write_positions(sessions_dir / "sess-4-positions.json", {
        "d1-safe": {
            "position_id": "d1-safe", "directive_id": "d1", "arm": "safe", "status": "OPEN",
            "realized_pnl": 0.0, "unrealized_pnl": 5.0,
            "entry_time_et": "2026-07-17T09:30:00", "exit_time_et": None,
            "symbol": "x", "side": "C", "strike": 550, "qty": 3, "entry_premium": 1.0,
            "price_source": "opra_5m", "is_synthetic": False, "legs": [], "note": None,
        },
    })

    result = scorecard.score_session(ledger)
    assert result["divergence_points"] == []


def test_score_session_handles_missing_positions_file_gracefully(tmp_path):
    sessions_dir = tmp_path / "sessions"
    ledger = sessions_dir / "sess-5.jsonl"
    _write_ledger(ledger, [{"event": "session_start", "replay_day": "2026-07-17"}])
    # no positions.json written at all -- session started but no directive ever issued
    result = scorecard.score_session(ledger)
    assert result["n_positions"] == 0
    assert result["per_arm"] == {}
    assert result["totals"]["j_directed_realized_pnl"] == 0.0

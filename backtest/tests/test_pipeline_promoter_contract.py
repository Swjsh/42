"""Guards for the rewritten pipeline_promoter output contract (2026-07-01).

PIPELINE-AUDIT-2026-07-01 break #2 fix: the promoter must never again write a
params key nothing reads. Contract under guard:

  1. Dispatcher-backed watcher + gates pass -> the roster's REAL enable-flag key
     ('<flag>_enabled': true) lands in the FIXTURE params file (WATCH only);
     extra_setup_exec_armed and the dead '*_stage5_cleared' key are NEVER written.
  2. Non-dispatcher watcher + gates pass -> a pending WIRE-DETECTOR-<watcher>
     proposal row in the fixture proposals ledger; params file untouched.
  3. Stale scorecard (> MAX_SCORECARD_AGE_DAYS) is still refused.
  4. Schema fix (audit break (d)): _check_gates evaluates the REAL fresh stage5
     file (best/all_results shape) instead of failing closed on it.

ALL filesystem writes go to tmp_path fixtures — never live state (the promoter's
keyword overrides exist exactly for this).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

from autoresearch.pipeline_promoter import (  # noqa: E402
    _check_gates,
    check_and_promote,
    read_dispatcher_roster,
)

FRESH_STAGE5 = REPO / "analysis" / "recommendations" / "shotgun-scalper-stage5.json"
DISPATCH_SOURCE = REPO / "setup" / "scripts" / "setup_dispatch.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _passing_stage5_scorecard() -> dict:
    """Minimal fresh-schema (stage5) scorecard that clears all 5 gates."""
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "best": {
            "combo": {"tp_premium_pct": 1.5, "stop_premium_pct": -0.35},
            "wide_pnl": 18000.0,
            "sharpe": 4.5,
            "n_trades": 1200,
            "expectancy": 15.0,
            "dir_score": 3,
            "quarter_pnl": {
                "2025-Q1": 2700.0, "2025-Q2": 4100.0,
                "2025-Q3": 2700.0, "2025-Q4": 3000.0,
                "2026-Q1": 2800.0, "2026-Q2": 2800.0,
            },
            "walk_forward": {
                "train_pnl": 12500.0,
                "test_pnl": 5600.0,        # raw 0.448; per-quarter (5600/2)/(12500/4)=0.896
                "train_positive_quarters": 4,
                "test_positive_quarters": 2,
                "passed": True,
            },
            "concentration": {"top5_pct": 0.16, "passed": True},
        },
        "all_results": [],
    }


@pytest.fixture()
def sandbox(tmp_path: Path) -> dict:
    """Tmp-dir fixture files the promoter writes to instead of live state."""
    recs = tmp_path / "recs"
    recs.mkdir()
    params = tmp_path / "params.json"
    params.write_text(json.dumps({"existing_key": 1}), encoding="utf-8")
    proposals = tmp_path / "conductor-proposals.jsonl"
    outbox = tmp_path / "discord-outbox.jsonl"
    return {"recs": recs, "params": params, "proposals": proposals, "outbox": outbox,
            "tmp": tmp_path}


def _write_scorecard(sandbox: dict, script_name: str, scorecard: dict) -> None:
    (sandbox["recs"] / f"{script_name}.json").write_text(
        json.dumps(scorecard), encoding="utf-8")


def _promote(sandbox: dict, script_name: str, watcher: str) -> bool:
    return check_and_promote(
        script_name, watcher,
        recs_dir=sandbox["recs"],
        params_paths=[sandbox["params"]],
        proposals_path=sandbox["proposals"],
        discord_outbox=sandbox["outbox"],
    )


# ---------------------------------------------------------------------------
# Roster reading
# ---------------------------------------------------------------------------

def test_roster_read_from_live_dispatch_source() -> None:
    """The roster parser must find the known dispatcher entries + their real flag keys."""
    roster = read_dispatcher_roster()
    assert roster.get("vwap_continuation") == "j_vwap_cont_enabled", roster
    assert roster.get("gap_and_go") == "gap_and_go_enabled", roster
    assert roster.get("double_bottom_base_quiet") == "db_base_quiet_enabled", roster
    # shotgun_scalper / sniper_level_break have NO dispatcher (audit break #2b)
    assert "shotgun_scalper" not in roster
    assert "sniper_level_break" not in roster


def test_roster_fails_closed_on_unreadable_source(tmp_path: Path) -> None:
    """Unreadable dispatch source -> {} -> everything routes to proposals, no params write."""
    assert read_dispatcher_roster(tmp_path / "nope.py") == {}


# ---------------------------------------------------------------------------
# Contract 1: dispatcher-backed watcher -> WATCH flag in fixture params
# ---------------------------------------------------------------------------

def test_dispatcher_watcher_writes_watch_flag_to_fixture_params(sandbox: dict) -> None:
    _write_scorecard(sandbox, "gap_and_go_stage5", _passing_stage5_scorecard())
    ok = _promote(sandbox, "gap_and_go_stage5", "gap_and_go")
    assert ok is True

    params = json.loads(sandbox["params"].read_text(encoding="utf-8"))
    assert params.get("gap_and_go_enabled") is True, params
    assert params.get("existing_key") == 1  # untouched neighbors
    # WATCH only — exec-arm is a validation-gated step, NEVER the promoter's
    assert "extra_setup_exec_armed" not in params
    # The dead legacy key must be GONE from the contract
    assert "gap_and_go_stage5_cleared" not in params
    # No WIRE-DETECTOR proposal for a wired watcher
    assert not sandbox["proposals"].exists() or \
        "WIRE-DETECTOR" not in sandbox["proposals"].read_text(encoding="utf-8")
    # promote scorecard records the wiring
    promo = json.loads((sandbox["recs"] / "promote_gap_and_go.json").read_text(encoding="utf-8"))
    assert promo["dispatcher_wired"] is True
    assert promo["watch_flag_key"] == "gap_and_go_enabled"
    assert promo["exec_armed"] is False


# ---------------------------------------------------------------------------
# Contract 2: non-dispatcher watcher -> proposal row, NO params write
# ---------------------------------------------------------------------------

def test_unwired_watcher_files_proposal_and_never_touches_params(sandbox: dict) -> None:
    _write_scorecard(sandbox, "shotgun_scalper_stage5", _passing_stage5_scorecard())
    before = sandbox["params"].read_text(encoding="utf-8")
    ok = _promote(sandbox, "shotgun_scalper_stage5", "shotgun_scalper")
    assert ok is True

    # params byte-identical — no dead key, no flag
    assert sandbox["params"].read_text(encoding="utf-8") == before

    rows = [json.loads(l) for l in
            sandbox["proposals"].read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows) == 1
    row = rows[0]
    assert row["title"] == "WIRE-DETECTOR-shotgun_scalper"
    assert row["source"] == "pipeline_promoter"
    assert row["status"] == "pending"
    assert row["kind"] == "wiring"
    # scorecard evidence travels with the work item
    assert row["scorecard_evidence"]["wide_pnl"] == 18000.0
    assert row["gates"]["all_gates_passed"] is True

    # idempotent: second fire does not duplicate the pending row
    ok2 = _promote(sandbox, "shotgun_scalper_stage5", "shotgun_scalper")
    assert ok2 is True
    rows2 = [l for l in sandbox["proposals"].read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(rows2) == 1


# ---------------------------------------------------------------------------
# Contract 3: stale scorecard still refused
# ---------------------------------------------------------------------------

def test_stale_scorecard_refused(sandbox: dict) -> None:
    stale = _passing_stage5_scorecard()
    stale["generated_at"] = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    _write_scorecard(sandbox, "gap_and_go_stage5", stale)
    before = sandbox["params"].read_text(encoding="utf-8")
    ok = _promote(sandbox, "gap_and_go_stage5", "gap_and_go")
    assert ok is False
    assert sandbox["params"].read_text(encoding="utf-8") == before
    assert not sandbox["proposals"].exists()


def test_failing_gates_block_and_do_not_write(sandbox: dict) -> None:
    bad = _passing_stage5_scorecard()
    bad["best"]["dir_score"] = 1  # anchor gate fails
    _write_scorecard(sandbox, "gap_and_go_stage5", bad)
    before = sandbox["params"].read_text(encoding="utf-8")
    ok = _promote(sandbox, "gap_and_go_stage5", "gap_and_go")
    assert ok is False
    assert sandbox["params"].read_text(encoding="utf-8") == before
    assert not sandbox["proposals"].exists()


# ---------------------------------------------------------------------------
# Contract 4: schema fix — gates evaluate the REAL fresh stage5 file
# ---------------------------------------------------------------------------

def test_check_gates_reads_real_fresh_stage5_schema() -> None:
    """Audit break (d): stage5 writes best/all_results; the legacy promoter read
    top-level walk_forward/best_keeper and ALWAYS failed closed on fresh files."""
    scorecard = json.loads(FRESH_STAGE5.read_text(encoding="utf-8"))
    passed, details = _check_gates(scorecard)
    assert details["wf_passed"] is True
    # per-quarter normalized: (5680.95/2)/(12658.8/4) ~= 0.898
    assert details["wf_ratio"] == pytest.approx(0.898, abs=0.01), details
    assert "per-quarter" in details.get("wf_ratio_normalization", "")
    assert details["directional_score"] == 3
    assert details["top5_pct"] == pytest.approx(0.163, abs=0.001)
    assert details["sub_window_stable"] is True
    assert passed is True, details


def test_check_gates_legacy_schema_still_supported() -> None:
    """Old-shape scorecards (top-level walk_forward + best_keeper) must not regress."""
    legacy = {
        "walk_forward": {
            "passed": True, "train_pnl": 4000.0, "test_pnl": 3200.0,
            "test_positive_quarters": 2, "total_test_quarters": 2,
        },
        "best_keeper": {"directional_score": 3, "top5_pct": 0.35},
    }
    passed, details = _check_gates(legacy)
    assert passed is True, details
    assert details["wf_ratio"] == pytest.approx(0.80, abs=0.001)

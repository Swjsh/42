"""Guards for the 2026-07-01 twin crash-loops (kitchen stage5 poison pill +
watcher_grader KeyError 'direction').

Root causes being guarded:

  1. STAGE5 POISON PILL — kitchen_daemon._run_pipeline_scorecard called
     mod.main() bare, so stage5's argparse read the DAEMON's sys.argv (which
     contains 'run' from run-kitchen-daemon-keepalive.ps1) -> SystemExit(2).
     SystemExit is NOT an Exception subclass, so it escaped the task-runner
     catch and killed the daemon 1-7s after every claim. The task was
     priority=high + self-regenerating, so every keepalive restart re-claimed
     it first: 10 daemon deaths on 2026-07-01 alone.
     Fixes guarded: (a) explicit argv=[] passed to scorecard entry points,
     (b) SystemExit contained at both the scorecard runner and the dispatch loop.

  2. GRADER KEYERROR — lib.watchers.runner.grade_observation indexed
     obs["direction"]; rows logged without it crashed the whole grader batch
     for 3 straight trading days (362/584 observations left ungraded).
     Fixes guarded: (a) grade_observation returns the row untouched when
     direction is missing/invalid, (b) watcher_grader counts + logs
     'skipped N direction-less rows'.

  3. PROMOTER STALENESS — pipeline_promoter._read_scorecard's dash-variant
     fallback resolved to a stale 2026-05-16 scorecard; the freshness guard
     must refuse scorecards older than MAX_SCORECARD_AGE_DAYS.
"""

from __future__ import annotations

import importlib
import json
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST), str(REPO), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)


# ─── 1. Stage5 poison pill ──────────────────────────────────────────────────


def test_stage5_main_ignores_polluted_sys_argv(monkeypatch) -> None:
    """stage5.main(argv=[]) must never parse the caller's sys.argv.

    Regression signature: argparse sees 'run' -> SystemExit(2).
    """
    from autoresearch import shotgun_scalper_stage5 as stage5

    # Simulate the daemon's process argv ('kitchen_daemon.py run')
    monkeypatch.setattr(sys, "argv", ["kitchen_daemon.py", "run"])
    # No keepers -> main returns 1 early without writing any output files
    monkeypatch.setattr(stage5, "_read_keepers", lambda _p: [])

    try:
        rc = stage5.main(argv=[])
    except SystemExit as exc:  # pragma: no cover - the regression path
        pytest.fail(f"stage5.main(argv=[]) raised SystemExit({exc.code}) "
                    "with polluted sys.argv — argparse is reading sys.argv again")
    assert rc == 1  # no-keepers early exit, not an argparse death


def test_daemon_scorecard_runner_passes_explicit_argv(monkeypatch) -> None:
    """_run_pipeline_scorecard must call main(argv=[]) — a bare main() call
    (argv=None) re-creates the poison pill. The fake module below behaves like
    argparse: it dies with SystemExit(2) unless given an explicit argv.
    """
    daemon = importlib.import_module("kitchen_daemon")

    received: dict = {}

    fake = types.ModuleType("autoresearch.fake_argv_probe_stage5")

    def _main(argv=None):
        received["argv"] = argv
        if argv is None:
            # argparse-with-None reads sys.argv -> SystemExit(2) on 'run'
            raise SystemExit(2)
        return 0

    fake.main = _main
    monkeypatch.setitem(sys.modules, "autoresearch.fake_argv_probe_stage5", fake)

    result = daemon._run_pipeline_scorecard({"script_name": "fake_argv_probe_stage5"})
    assert received.get("argv") == [], (
        f"daemon passed argv={received.get('argv')!r} to the scorecard main; "
        "must be [] so the daemon's own sys.argv never leaks into argparse"
    )
    assert result["ok"] is True, f"clean scorecard run reported not-ok: {result}"


def test_daemon_scorecard_runner_survives_systemexit(monkeypatch) -> None:
    """A scorecard module that calls sys.exit must fail the TASK, not the daemon."""
    daemon = importlib.import_module("kitchen_daemon")

    fake = types.ModuleType("autoresearch.fake_exploding_stage5")

    def _main(argv=None):
        raise SystemExit(2)

    fake.main = _main
    monkeypatch.setitem(sys.modules, "autoresearch.fake_exploding_stage5", fake)

    try:
        result = daemon._run_pipeline_scorecard({"script_name": "fake_exploding_stage5"})
    except SystemExit:  # pragma: no cover - the regression path
        pytest.fail("SystemExit escaped _run_pipeline_scorecard — this is the "
                    "exact 2026-07-01 daemon-death mechanism")
    assert result["ok"] is False
    assert "SystemExit" in str(result.get("error", ""))


def test_daemon_dispatch_loop_catches_systemexit() -> None:
    """The main-loop dispatch must contain SystemExit too (belt-and-braces:
    grinder/LLM task paths can also raise it). Source-level guard because the
    loop body is not independently callable.
    """
    src = (REPO / "setup" / "scripts" / "kitchen_daemon.py").read_text(encoding="utf-8")
    dispatch = src[src.index("EXCEPTION in dispatch") - 2000: src.index("EXCEPTION in dispatch")]
    assert "except SystemExit" in dispatch, (
        "kitchen_daemon main-loop dispatch no longer catches SystemExit — "
        "a task sys.exit will kill the daemon again"
    )


# ─── 2. Grader direction tolerance ──────────────────────────────────────────


def _future_bars() -> pd.DataFrame:
    return pd.DataFrame({
        "timestamp_et": pd.to_datetime(["2026-06-30 10:05", "2026-06-30 10:10"]),
        "high": [600.5, 601.0],
        "low": [599.5, 600.0],
    })


def test_grade_observation_tolerates_missing_direction() -> None:
    """A row without 'direction' must be returned un-graded, never KeyError."""
    from lib.watchers.runner import grade_observation

    obs = {
        # no 'direction' key — the exact shape that crashed the grader 3 days running
        "watcher_name": "some_watcher",
        "entry_price": 600.0,
        "stop_price": 599.0,
        "tp1_price": 601.0,
        "runner_price": 602.0,
        "would_be_outcome": None,
    }
    try:
        out = grade_observation(obs, _future_bars())
    except KeyError as exc:  # pragma: no cover - the regression path
        pytest.fail(f"grade_observation raised KeyError({exc}) on a "
                    "direction-less row — 2026-07-01 grader crash is back")
    assert out["would_be_outcome"] is None  # left ungraded, not mis-graded


def test_grade_observation_rejects_invalid_direction() -> None:
    """Garbage directions are also skipped (not silently graded as long)."""
    from lib.watchers.runner import grade_observation

    obs = {
        "direction": "sideways",
        "entry_price": 600.0,
        "stop_price": 599.0,
        "tp1_price": 601.0,
        "runner_price": 602.0,
        "would_be_outcome": None,
    }
    out = grade_observation(obs, _future_bars())
    assert out["would_be_outcome"] is None


def test_watcher_grader_counts_directionless_rows(monkeypatch, tmp_path, capsys) -> None:
    """watcher_grader.main must skip + count direction-less rows and print the
    summary line 'skipped N direction-less rows' instead of crashing.
    """
    from autoresearch import watcher_grader as wg

    obs_log = tmp_path / "watcher-observations.jsonl"
    summary = tmp_path / "watcher-summary.json"
    rows = [
        {   # direction-less, ungraded — previously fatal
            "watcher_name": "w1",
            "bar_timestamp_et": "2026-06-30T10:00:00",
            "entry_price": 600.0, "stop_price": 599.0,
            "tp1_price": 601.0, "runner_price": 602.0,
            "would_be_outcome": None, "would_be_pnl_dollars": None,
        },
        {   # already graded — untouched
            "watcher_name": "w2",
            "direction": "long",
            "bar_timestamp_et": "2026-06-30T10:05:00",
            "entry_price": 600.0, "stop_price": 599.0,
            "tp1_price": 601.0, "runner_price": 602.0,
            "would_be_outcome": "stopped", "would_be_pnl_dollars": -100.0,
        },
    ]
    obs_log.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(wg, "OBS_LOG", obs_log)
    monkeypatch.setattr(wg, "SUMMARY", summary)

    rc = wg.main()
    out = capsys.readouterr().out
    assert rc == 0
    assert "skipped 1 direction-less rows" in out, (
        f"expected the skip-summary line in grader stdout, got:\n{out}"
    )
    assert summary.exists()


# ─── 3. Promoter scorecard freshness ────────────────────────────────────────


def _scorecard_payload(generated_at: str) -> str:
    return json.dumps({
        "generated_at": generated_at,
        "walk_forward": {"passed": True, "train_pnl": 100.0, "test_pnl": 90.0},
        "best_keeper": {"directional_score": 3, "top5_pct": 0.3},
    })


def test_promoter_refuses_stale_scorecard(monkeypatch, tmp_path) -> None:
    """_read_scorecard must refuse scorecards older than MAX_SCORECARD_AGE_DAYS —
    the dash-variant fallback once resolved to a stale 2026-05-16 file.
    """
    from autoresearch import pipeline_promoter as pp

    monkeypatch.setattr(pp, "RECS_DIR", tmp_path)

    stale_ts = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    # Only the dash-variant fallback exists, and it is stale
    (tmp_path / "shotgun-scalper-stage5.json").write_text(
        _scorecard_payload(stale_ts), encoding="utf-8")

    assert pp._read_scorecard("shotgun_scalper_stage5") is None, (
        "promoter accepted a 30-day-old scorecard — freshness guard is gone"
    )


def test_promoter_accepts_fresh_scorecard(monkeypatch, tmp_path) -> None:
    """Fresh scorecards still load (guard must not fail closed on good data)."""
    from autoresearch import pipeline_promoter as pp

    monkeypatch.setattr(pp, "RECS_DIR", tmp_path)

    fresh_ts = datetime.now(timezone.utc).isoformat()
    (tmp_path / "shotgun_scalper_stage5.json").write_text(
        _scorecard_payload(fresh_ts), encoding="utf-8")

    sc = pp._read_scorecard("shotgun_scalper_stage5")
    assert sc is not None
    assert sc["generated_at"] == fresh_ts

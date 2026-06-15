"""Tests for crypto/benchmarks/gym_harvester.py.

Each test feeds a synthetic JSONL fixture and exercises a single rule plus the
dedup boundary. Uses tmp_path to avoid touching real scorecards/queue.md files.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# Make sibling module importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.benchmarks import gym_harvester as gh


@pytest.fixture
def isolated_paths(tmp_path, monkeypatch):
    """Redirect all module-level paths into a temp dir so tests don't touch real data."""
    grinder = tmp_path / "grinder.jsonl"
    history = tmp_path / "history.jsonl"
    latest = tmp_path / "latest.json"
    state = tmp_path / "harvester-state.json"
    seen = tmp_path / "harvester-seen-keys.json"
    log = tmp_path / "harvester-log.jsonl"
    queue = tmp_path / "queue.md"

    # Seed queue.md with the same skeleton the real file uses so the inserters
    # have the SWARM-BACKFILL anchor to target.
    queue.write_text(
        "# OVERNIGHT TASK QUEUE\n"
        "\n"
        "---\n"
        "\n"
        "## CRITICAL\n"
        "(empty)\n"
        "\n"
        "## SWARM-BACKFILL\n"
        "\n"
        "- [x] SWARM-BACKFILL-90D :: existing :: status:completed\n"
        "\n"
        "## OTHER\n"
        "\n"
        "- [x] OTHER-1 :: prior :: status:completed\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(gh, "GRINDER_PATH", grinder)
    monkeypatch.setattr(gh, "HISTORY_PATH", history)
    monkeypatch.setattr(gh, "LATEST_PATH", latest)
    monkeypatch.setattr(gh, "STATE_PATH", state)
    monkeypatch.setattr(gh, "SEEN_KEYS_PATH", seen)
    monkeypatch.setattr(gh, "HARVESTER_LOG_PATH", log)
    monkeypatch.setattr(gh, "QUEUE_PATH", queue)

    return {
        "grinder": grinder,
        "history": history,
        "latest": latest,
        "state": state,
        "seen": seen,
        "log": log,
        "queue": queue,
    }


# -- Helpers ------------------------------------------------------------------
def _now_iso(offset_min: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=offset_min)).isoformat()


def _write_grinder(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _grinder_iteration(
    *,
    started_at: str | None = None,
    foot_gun: bool = False,
    bar_open: str = "2026-05-17T22:40:00+00:00",
    rsi: float = 50.0,
    v02_disagreements: int = 0,
    v02_worst_pct: float = 0.0,
    v02_bar_open: str = "2026-05-17T22:00:00+00:00",
) -> dict:
    started = started_at or _now_iso(-10)
    rec = {
        "started_at": started,
        "symbol": "BTC-USD",
        "granularity": 300,
        "results": {
            "v01_live": {
                "fetched_at": started,
                "naive_last_bar_open": bar_open,
                "naive_last_bar_seconds_until_close": 60.0 if foot_gun else -60.0,
                "filtered_last_closed_open": bar_open,
                "bars_rejected_as_in_progress": 1 if foot_gun else 0,
                "foot_gun_caught_this_fetch": foot_gun,
                "ohlc_delta_naive_minus_filtered": (
                    {"open": 1.0, "high": 1.0, "low": 1.0, "close": -600.0,
                     "volume": -0.5} if foot_gun else None
                ),
                "pass": True,
            },
            "v02_parity": {
                "checked_at": started,
                "disagreements_above_tolerance": v02_disagreements,
                "price_tolerance_pct": 0.05,
                "disagreements": (
                    [{"open_time": v02_bar_open,
                      "worst_pct": v02_worst_pct}]
                    if v02_disagreements > 0 else []
                ),
                "pass": v02_disagreements == 0,
            },
            "v03_indicators_live": {
                "rsi_14_last": rsi,
                "last_close": 78000.0,
                "pass": True,
            },
        },
    }
    return rec


def _latest_with(
    *,
    v07_bars_above_3x: int = 5,
    v08_status: str = "MIXED",
    v08_spread: float = 50.0,
    v08_dist: dict | None = None,
    v14_examples: list[dict] | None = None,
    v15_violations: list[dict] | None = None,
) -> dict:
    return {
        "summary": {
            "started_at": _now_iso(-1),
            "overall_pass": True,
        },
        "runs": [
            {
                "name": "v07_volume.live",
                "ok": True,
                "result": {
                    "closed_bars": 200,
                    "bars_above_3x": v07_bars_above_3x,
                },
            },
            {
                "name": "v08_ribbon.live",
                "ok": True,
                "result": {
                    "last": {"spread": v08_spread, "status": v08_status},
                    "status_distribution": v08_dist or {"BULL": 30, "BEAR": 30, "MIXED": 40},
                },
            },
            {
                "name": "v14_sweep.live",
                "ok": True,
                "result": {
                    "sweep_hits": len(v14_examples or []),
                    "examples": v14_examples or [],
                },
            },
            {
                "name": "v15_three_source_parity.live",
                "ok": True,
                "result": {
                    "checked_at": _now_iso(-1),
                    "violations_count": len(v15_violations or []),
                    "violations": v15_violations or [],
                },
            },
        ],
    }


# -- Rule-level tests ---------------------------------------------------------
def test_foot_gun_rule_appends_row(isolated_paths):
    rec = _grinder_iteration(foot_gun=True, bar_open="2026-05-17T22:40:00+00:00")
    _write_grinder(isolated_paths["grinder"], [rec])

    stats = gh.harvest(hours=24)

    assert stats.candidates_new == 1
    assert stats.candidates_appended_to_queue == 1
    assert stats.by_rule.get("EDGE_FOOT_GUN_CAUGHT") == 1

    text = isolated_paths["queue"].read_text(encoding="utf-8")
    assert "HARVEST-FOOTGUN-" in text
    assert "EDGE_FOOT_GUN_CAUGHT" in text
    assert "2026-05-17T22:40:00+00:00" in text


def test_source_disagreement_rule_appends_row(isolated_paths):
    # v02 is KNOWN_FLAKY_LIVE_SOURCE (OP-26 carve-out) — disagreements must NOT be queued.
    rec = _grinder_iteration(
        v02_disagreements=1,
        v02_worst_pct=0.075,
        v02_bar_open="2026-05-17T22:00:00+00:00",
    )
    _write_grinder(isolated_paths["grinder"], [rec])

    # v15 three-source violations in latest.json ARE queued — three-way
    # coinbase/yfinance/alpaca mismatch is a different failure mode from v02 timing jitter.
    isolated_paths["latest"].write_text(
        json.dumps(_latest_with(
            v15_violations=[{"open_time": "2026-05-17T22:00:00+00:00"}],
        )),
        encoding="utf-8",
    )

    stats = gh.harvest(hours=24)

    # v02 carve-out: grinder record scanned but 0 candidates from v02.
    # v15 violation from latest.json: 1 candidate queued.
    assert stats.candidates_new == 1
    assert stats.by_rule.get("EDGE_SOURCE_DISAGREEMENT") == 1

    text = isolated_paths["queue"].read_text(encoding="utf-8")
    assert "HARVEST-SRCDISAGREE-" in text
    assert "2026-05-17T22:00:00+00:00" in text


def test_rsi_extreme_rule_appends_for_oversold_and_overbought(isolated_paths):
    rec_low = _grinder_iteration(started_at="2026-05-17T20:00:00+00:00", rsi=15.0)
    rec_high = _grinder_iteration(started_at="2026-05-17T21:00:00+00:00", rsi=85.5)
    _write_grinder(isolated_paths["grinder"], [rec_low, rec_high])

    # Use a wide window so the synthetic timestamps fall inside.
    stats = gh.harvest(hours=24 * 365)

    assert stats.by_rule.get("EDGE_RSI_EXTREME") == 2

    text = isolated_paths["queue"].read_text(encoding="utf-8")
    assert "oversold" in text
    assert "overbought" in text


def test_volume_spike_rule_appends_row(isolated_paths):
    isolated_paths["latest"].write_text(
        json.dumps(_latest_with(v07_bars_above_3x=22)),
        encoding="utf-8",
    )

    stats = gh.harvest(hours=24)

    assert stats.by_rule.get("EDGE_VOLUME_SPIKE") == 1
    text = isolated_paths["queue"].read_text(encoding="utf-8")
    assert "HARVEST-VOLSPIKE-" in text
    assert "bars_above_3x=22" in text


def test_ribbon_flip_rule_appends_row(isolated_paths):
    isolated_paths["latest"].write_text(
        json.dumps(_latest_with(
            v08_status="BULL",
            v08_spread=150.0,
            v08_dist={"BULL": 30, "BEAR": 10, "MIXED": 60},
        )),
        encoding="utf-8",
    )

    stats = gh.harvest(hours=24)

    assert stats.by_rule.get("EDGE_RIBBON_FLIP") == 1
    text = isolated_paths["queue"].read_text(encoding="utf-8")
    assert "HARVEST-RIBBONFLIP-" in text
    assert "MIXED -> BULL" in text


def test_sweep_detected_rule_appends_row(isolated_paths):
    isolated_paths["latest"].write_text(
        json.dumps(_latest_with(
            v14_examples=[
                {"bar_idx": 195, "level": 78000, "dir": "down",
                 "wick_excess_pct": 0.12, "close_back_pct": 0.099},
                # second example below 0.05 threshold — should be filtered.
                {"bar_idx": 6, "level": 78000, "dir": "down",
                 "wick_excess_pct": 0.03, "close_back_pct": 0.02},
            ],
        )),
        encoding="utf-8",
    )

    stats = gh.harvest(hours=24)

    assert stats.by_rule.get("EDGE_SWEEP_DETECTED") == 1
    text = isolated_paths["queue"].read_text(encoding="utf-8")
    assert "HARVEST-SWEEP-" in text
    assert "level=78000" in text


def test_regression_fail_rule_appends_critical_row(isolated_paths):
    rec = {
        "started_at": _now_iso(-30),
        "overall_pass": False,
        "passed": 28,
        "stages": 30,
        "per_stage": {
            "v01_closed_bar.live": True,
            "v02_source_parity": False,
            "v15_three_source_parity.live": False,
        },
    }
    isolated_paths["history"].write_text(json.dumps(rec) + "\n", encoding="utf-8")

    stats = gh.harvest(hours=24)

    assert stats.by_rule.get("EDGE_REGRESSION_FAIL") == 1
    text = isolated_paths["queue"].read_text(encoding="utf-8")
    assert "HARVEST-REGFAIL-" in text
    assert "(CRIT)" in text
    # Critical rows must land above the SWARM-BACKFILL section.
    crit_idx = text.index("HARVEST-REGFAIL-")
    swarm_idx = text.index("## SWARM-BACKFILL")
    assert crit_idx < swarm_idx


def test_dedup_blocks_second_identical_run(isolated_paths):
    rec = _grinder_iteration(foot_gun=True, bar_open="2026-05-17T22:40:00+00:00")
    _write_grinder(isolated_paths["grinder"], [rec])

    stats_1 = gh.harvest(hours=24)
    assert stats_1.candidates_new == 1
    assert stats_1.candidates_appended_to_queue == 1

    queue_text_after_1 = isolated_paths["queue"].read_text(encoding="utf-8")
    rows_before = queue_text_after_1.count("HARVEST-FOOTGUN-")

    # Run again with the EXACT same fixture — must not produce a duplicate.
    stats_2 = gh.harvest(hours=24)
    assert stats_2.candidates_new == 0
    assert stats_2.candidates_appended_to_queue == 0
    assert stats_2.candidates_skipped_dup == 1

    queue_text_after_2 = isolated_paths["queue"].read_text(encoding="utf-8")
    rows_after = queue_text_after_2.count("HARVEST-FOOTGUN-")
    assert rows_before == rows_after, "second harvest must not append duplicate rows"


def test_dry_run_does_not_modify_queue(isolated_paths):
    rec = _grinder_iteration(foot_gun=True, bar_open="2026-05-17T22:40:00+00:00")
    _write_grinder(isolated_paths["grinder"], [rec])

    queue_before = isolated_paths["queue"].read_text(encoding="utf-8")

    stats = gh.harvest(hours=24, dry_run=True)

    assert stats.candidates_new == 1
    assert stats.candidates_appended_to_queue == 0
    # Queue.md untouched.
    assert isolated_paths["queue"].read_text(encoding="utf-8") == queue_before
    # No seen-keys persisted on a dry run, so a real run should still fire.
    assert not isolated_paths["seen"].exists() or "[]" in isolated_paths["seen"].read_text(encoding="utf-8") or isolated_paths["seen"].read_text(encoding="utf-8") == ""


def test_existing_queue_row_blocks_dup_even_if_seen_keys_wiped(isolated_paths):
    rec = _grinder_iteration(foot_gun=True, bar_open="2026-05-17T22:40:00+00:00")
    _write_grinder(isolated_paths["grinder"], [rec])

    # First run appends the row.
    gh.harvest(hours=24)
    assert isolated_paths["queue"].read_text(encoding="utf-8").count("HARVEST-FOOTGUN-") == 1

    # Wipe seen-keys to simulate corruption / missing state.
    isolated_paths["seen"].unlink()

    # Second run should still dedup based on the existing queue row.
    stats = gh.harvest(hours=24)
    assert stats.candidates_appended_to_queue == 0
    assert stats.candidates_skipped_already_in_queue == 1
    assert isolated_paths["queue"].read_text(encoding="utf-8").count("HARVEST-FOOTGUN-") == 1

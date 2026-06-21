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
    harvest_archive = tmp_path / "queue-harvest-archive.md"

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
    monkeypatch.setattr(gh, "QUEUE_HARVEST_ARCHIVE_PATH", harvest_archive)

    return {
        "grinder": grinder,
        "history": history,
        "latest": latest,
        "state": state,
        "seen": seen,
        "log": log,
        "queue": queue,
        "harvest_archive": harvest_archive,
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
    # A DETERMINISTIC (.offline) stage failed → genuine reproducible regression → CRITICAL.
    rec = {
        "started_at": _now_iso(-30),
        "overall_pass": False,
        "passed": 28,
        "stages": 30,
        "per_stage": {
            "v01_closed_bar.live": True,
            "v03_indicators.offline": False,
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


def test_regression_fail_suppressed_when_only_live_stages_fail(isolated_paths):
    # GUARD (OP-25): a live-data-source outage fails every `.live` + flaky stage at
    # once and self-heals — environmental, NOT a code regression. Must NOT emit a
    # CRITICAL (this is the harvester false-CRITICAL flood foot-gun).
    rec = {
        "started_at": _now_iso(-30),
        "overall_pass": False,
        "passed": 74,
        "stages": 88,
        "per_stage": {
            "v01_closed_bar.offline": True,
            "v01_closed_bar.live": False,
            "v02_source_parity": False,
            "v03_indicators.live": False,
            "v05_levels.live": False,
            "v15_three_source_parity.live": False,
        },
    }
    isolated_paths["history"].write_text(json.dumps(rec) + "\n", encoding="utf-8")

    stats = gh.harvest(hours=24)

    assert stats.by_rule.get("EDGE_REGRESSION_FAIL") is None
    assert stats.candidates_appended_to_queue == 0
    text = isolated_paths["queue"].read_text(encoding="utf-8")
    assert "HARVEST-REGFAIL-" not in text


def test_regression_fail_emits_when_per_stage_missing(isolated_paths):
    # Conservative: an unexplained overall_pass=false with no per_stage breakdown
    # cannot be classified as environmental → still flag CRITICAL.
    rec = {
        "started_at": _now_iso(-30),
        "overall_pass": False,
        "passed": 0,
        "stages": 0,
    }
    isolated_paths["history"].write_text(json.dumps(rec) + "\n", encoding="utf-8")

    stats = gh.harvest(hours=24)

    assert stats.by_rule.get("EDGE_REGRESSION_FAIL") == 1
    text = isolated_paths["queue"].read_text(encoding="utf-8")
    assert "HARVEST-REGFAIL-" in text


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


# -- Retention-cap tests (OP-22 compound-don't-accumulate) --------------------
def _harvest_row(short: str, ts_id: str, pri: str = "LOW") -> str:
    return (
        f"- [ ] HARVEST-{short}-{ts_id} ({pri}) :: synthetic catalogue row :: "
        f"key=EDGE_X:{ts_id} :: depends:none :: status:queued"
    )


def _queue_with_harvest_rows(n: int, extra_tail: str = "") -> str:
    rows = "\n".join(
        _harvest_row("REGIMEEXT", f"20260620-{100000 + i:06d}") for i in range(n)
    )
    return (
        "# OVERNIGHT TASK QUEUE\n\n---\n\n"
        "## CRITICAL\n(empty)\n\n"
        f"{gh.SECTION_HARVESTED_HDR}\n\n"
        f"{rows}\n{extra_tail}"
    )


def test_prune_harvested_section_noop_under_cap():
    text = _queue_with_harvest_rows(3)
    new_text, archived = gh._prune_harvested_section(text, cap=15)
    assert archived == []
    assert new_text == text


def test_prune_harvested_section_keeps_newest_archives_oldest():
    # Rows are inserted newest-first, so the FIRST `cap` rows are kept.
    text = _queue_with_harvest_rows(20)
    new_text, archived = gh._prune_harvested_section(text, cap=15)
    assert len(archived) == 5
    # The 5 oldest (last in document order) are archived.
    assert all("HARVEST-REGIMEEXT-20260620-1000" in r for r in archived)
    kept = [ln for ln in new_text.splitlines() if ln.startswith("- [ ] HARVEST-")]
    assert len(kept) == 15
    # The newest (index 0) is kept; the oldest (index 19) is gone.
    assert "20260620-100000" in new_text  # newest kept
    assert "20260620-100019" not in new_text  # oldest pruned
    assert "20260620-100019" in archived[-1]


def test_prune_preserves_non_harvest_lines():
    tail = (
        "\n### T-GYM-20260619 HIGH gym-session RED for 2026-06-19\n\n"
        "**Audits failing:**\n- chart-data-verify (RED): 0 bars checked\n"
    )
    text = _queue_with_harvest_rows(20, extra_tail=tail)
    new_text, archived = gh._prune_harvested_section(text, cap=15)
    assert len(archived) == 5
    # The free-text T-GYM block must survive untouched.
    assert "### T-GYM-20260619 HIGH gym-session RED" in new_text
    assert "chart-data-verify (RED): 0 bars checked" in new_text


def test_harvest_enforces_cap_and_writes_archive(isolated_paths, monkeypatch):
    # Pre-seed a queue already over a small cap, with NO new candidates this fire.
    monkeypatch.setattr(gh, "HARVESTED_SECTION_CAP", 2)
    isolated_paths["queue"].write_text(_queue_with_harvest_rows(5), encoding="utf-8")

    stats = gh.harvest(hours=24)

    assert stats.candidates_archived == 3
    text = isolated_paths["queue"].read_text(encoding="utf-8")
    kept = [ln for ln in text.splitlines() if ln.startswith("- [ ] HARVEST-")]
    assert len(kept) == 2
    # Archive file written with the 3 overflow rows verbatim.
    arch = isolated_paths["harvest_archive"].read_text(encoding="utf-8")
    assert arch.count("- [ ] HARVEST-REGIMEEXT-") == 3
    assert "over cap (2)" in arch


def test_cap_never_prunes_critical_regfail(isolated_paths, monkeypatch):
    # A deterministic .offline regression fires a CRITICAL row; even with the cap
    # set to 0 the CRITICAL section (separate from HARVESTED-FROM-GYM) is untouched.
    monkeypatch.setattr(gh, "HARVESTED_SECTION_CAP", 0)
    rec = {
        "started_at": _now_iso(-30),
        "overall_pass": False,
        "passed": 28,
        "stages": 30,
        "per_stage": {"v03_indicators.offline": False},
    }
    isolated_paths["history"].write_text(json.dumps(rec) + "\n", encoding="utf-8")

    gh.harvest(hours=24)

    text = isolated_paths["queue"].read_text(encoding="utf-8")
    assert "HARVEST-REGFAIL-" in text  # CRITICAL row survives the cap
    assert "(CRIT)" in text

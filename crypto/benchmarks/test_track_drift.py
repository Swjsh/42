"""Tests for crypto/benchmarks/track_drift.py.

Guard for the CRYPTO-GYM-V02-V12-FOLLOWUP root-cause fix (2026-07-14): v02's
strict 2-source (coinbase/yfinance) parity check legitimately disagrees when
yfinance settles late (v15_three_source_parity.py docstring, ~11-20% grinder
drift rate observed). v15 runs the SAME comparison as a true 2-of-3 quorum vote
across 3 sources and is the documented outer-layer ratifier. These tests prove:
  1. A v02 dip ratified by a healthy v15 is informational-only -- does NOT
     appear in `blocking_alerts` and does NOT flip `overall_health` to RED.
  2. A v02 dip WITHOUT v15 ratification (v15 also degraded / genuine 3-way
     disagreement) still blocks -- this is a real data-quality problem and
     must still gate health. The fix must not blanket-suppress v02.
  3. An unrelated stage's degradation (e.g. a deterministic dispatch-logic
     stage) still blocks regardless of v02/v15 status -- the fix is scoped to
     v02 specifically, not a general alert-softening.
  4. The grinder-level `source_parity_drift_24h` alert is similarly demoted
     only when >=90% of the drifting iterations are same-iteration ratified
     by v15's per-iteration quorum pass.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from crypto.benchmarks import track_drift as td


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def _history_row(started_at: datetime, per_stage: dict, overall_pass: bool = True) -> dict:
    return {"started_at": _iso(started_at), "overall_pass": overall_pass, "per_stage": per_stage,
            "passed": sum(1 for v in per_stage.values() if v), "stages": len(per_stage)}


def test_v02_dip_ratified_by_v15_is_informational_only(tmp_path):
    now = datetime.now(timezone.utc)
    history_path = tmp_path / "history.jsonl"
    grinder_path = tmp_path / "grinder.jsonl"

    # 10 fires in the last 24h: v02 fails 4/10 (60% pass, well under 95% threshold),
    # v15 passes 10/10 (100%, healthy quorum ratifier), everything else clean.
    rows = []
    for i in range(10):
        ts = now - timedelta(hours=i)
        v02_ok = i % 3 != 0  # 4 fails, 6 passes -> 60% (below 95% alert threshold)
        rows.append(_history_row(ts, {
            "v02_source_parity": v02_ok,
            "v15_three_source_parity.live": True,
            "v01_closed_bar.offline": True,
        }, overall_pass=True))
    _write_jsonl(history_path, rows)
    _write_jsonl(grinder_path, [])

    report = td.build_report(history_path, grinder_path)

    v02_alerts = [a for a in report["alerts"] if "v02_source_parity" in a]
    assert len(v02_alerts) == 1, f"expected exactly one v02 alert, got {v02_alerts}"
    assert "RATIFIED" in v02_alerts[0]
    assert v02_alerts[0] not in report["blocking_alerts"], (
        "v15-ratified v02 dip must NOT be a blocking alert"
    )
    assert report["overall_health"] == "GREEN", (
        f"overall_health must stay GREEN when the only alert is a v15-ratified v02 "
        f"dip; got RED with blocking_alerts={report['blocking_alerts']}"
    )


def test_v02_dip_without_v15_ratification_still_blocks(tmp_path):
    now = datetime.now(timezone.utc)
    history_path = tmp_path / "history.jsonl"
    grinder_path = tmp_path / "grinder.jsonl"

    # v02 AND v15 both degraded -- a genuine 3-way disagreement, not a
    # single-provider artifact. Must still gate health RED.
    rows = []
    for i in range(10):
        ts = now - timedelta(hours=i)
        both_ok = i % 3 != 0
        rows.append(_history_row(ts, {
            "v02_source_parity": both_ok,
            "v15_three_source_parity.live": both_ok,
        }, overall_pass=True))
    _write_jsonl(history_path, rows)
    _write_jsonl(grinder_path, [])

    report = td.build_report(history_path, grinder_path)

    assert report["overall_health"] == "RED", (
        "v02 dip WITHOUT v15 ratification (v15 also degraded) must still block"
    )
    assert any("v02_source_parity" in a for a in report["blocking_alerts"])


def test_unrelated_stage_degradation_still_blocks(tmp_path):
    now = datetime.now(timezone.utc)
    history_path = tmp_path / "history.jsonl"
    grinder_path = tmp_path / "grinder.jsonl"

    # v02/v15 both perfectly healthy; an unrelated deterministic stage fails.
    # The fix must be scoped to v02 -- everything else keeps gating normally.
    rows = []
    for i in range(10):
        ts = now - timedelta(hours=i)
        other_ok = i % 3 != 0
        rows.append(_history_row(ts, {
            "v02_source_parity": True,
            "v15_three_source_parity.live": True,
            "v53_setup_dispatch.live": other_ok,
        }, overall_pass=other_ok))
    _write_jsonl(history_path, rows)
    _write_jsonl(grinder_path, [])

    report = td.build_report(history_path, grinder_path)

    assert report["overall_health"] == "RED"
    assert any("v53_setup_dispatch.live" in a for a in report["blocking_alerts"])
    assert not any("v02" in a for a in report["alerts"]), "v02 should not alert when 100% healthy"


def test_grinder_source_parity_drift_ratified_is_informational(tmp_path):
    now = datetime.now(timezone.utc)
    history_path = tmp_path / "history.jsonl"
    grinder_path = tmp_path / "grinder.jsonl"
    _write_jsonl(history_path, [])

    # 40% of iterations show v02 drift (> the 30% alert threshold), but v15's
    # same-iteration quorum vote passes on every one of those -- ratified.
    rows = []
    for i in range(20):
        ts = now - timedelta(minutes=i)
        has_drift = i % 5 == 0  # 4/20 = 20%... bump to exceed 30% below
        rows.append({
            "started_at": _iso(ts),
            "results": {
                "v02_parity": {"disagreements_above_tolerance": 1 if i % 2 == 0 else 0},
                "v15_parity": {"pass": True},
            },
        })
    _write_jsonl(grinder_path, rows)

    report = td.build_report(history_path, grinder_path)

    parity = report["source_parity_drift_24h"]
    assert parity["drift_rate_pct"] > 30
    assert parity["iters_with_drift_ratified_by_v15"] == parity["iters_with_drift"]
    assert not any("v02 source parity drift" in a for a in report["blocking_alerts"])
    assert any("RATIFIED" in a for a in report["alerts"])


def test_grinder_source_parity_drift_unratified_blocks(tmp_path):
    now = datetime.now(timezone.utc)
    history_path = tmp_path / "history.jsonl"
    grinder_path = tmp_path / "grinder.jsonl"
    _write_jsonl(history_path, [])

    # Same drift rate, but v15 does NOT ratify (genuine 3-way disagreement).
    rows = []
    for i in range(20):
        ts = now - timedelta(minutes=i)
        rows.append({
            "started_at": _iso(ts),
            "results": {
                "v02_parity": {"disagreements_above_tolerance": 1 if i % 2 == 0 else 0},
                "v15_parity": {"pass": False},
            },
        })
    _write_jsonl(grinder_path, rows)

    report = td.build_report(history_path, grinder_path)

    parity = report["source_parity_drift_24h"]
    assert parity["drift_rate_pct"] > 30
    assert parity["iters_with_drift_ratified_by_v15"] == 0
    assert any("v02 source parity drift" in a for a in report["blocking_alerts"])

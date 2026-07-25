"""Guard tests for backtest/tools/engulfing_at_local_cluster_detector.py -- the grid
adapter for the SHIPPED `engulfing_at_local_cluster` registry rule (ENGULFING-AT-
STRUCTURE-TRIGGER's real-fills replay confirmation, queue.md).

Three properties this suite enforces:
  1. ZERO-FORK: the grid module's shipped-config cell (touch3|body0.40|tol0.20) must
     be BYTE-IDENTICAL to the live registry predicate at every bar, not just the anchors
     -- if this ever regresses (someone edits one but not the other), this test REDs.
  2. C6 CAUSALITY: detect_bar at index t must not change when bars strictly after t
     are mutated (RED-proofed: same discipline as test_engulfing_at_structure.py).
  3. ANCHOR FIRE: both of J's live exhibits fire (bearish 2026-07-23 10:40, bullish
     2026-07-21 11:05) on the shipped cell, matching the registry's own declared
     anchors on `engulfing_at_local_cluster` (registry.py PatternRule.anchors).
"""
from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date, time as dtime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

_ROOT = Path(__file__).resolve().parents[2]
for _p in ("backtest", "backtest/tools"):
    _ap = str(_ROOT / _p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

import engulfing_at_local_cluster_detector as det  # noqa: E402
from crypto.lib.bar import Bar  # noqa: E402
from backtest.lib.patterns.registry import (  # noqa: E402
    _engulfing_at_local_cluster_predicate, REGISTRY_BY_NAME,
)

SHIPPED = det.Cell(min_touches=3, min_body_dollars=0.40, tolerance=0.20)
DATA_DIR = _ROOT / "backtest" / "data"


def _find_freshest_csv() -> Path:
    import re
    pattern = re.compile(r"^spy_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})(?:_\w+)?\.csv$")
    candidates = []
    for p in DATA_DIR.glob("spy_5m_*.csv"):
        m = pattern.match(p.name)
        if m:
            candidates.append((m.group(2), m.group(1), p))
    candidates.sort(key=lambda c: (c[0], c[1]))
    latest_end = candidates[-1][0]
    tied = sorted((c for c in candidates if c[0] == latest_end), key=lambda c: c[1])
    return tied[0][2]


@pytest.fixture(scope="module")
def real_ctx():
    csv_path = _find_freshest_csv()
    df = pd.read_csv(csv_path)
    ts = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York")
    df = df.assign(timestamp_et=ts, date=ts.dt.date, time_et=ts.dt.time)
    mask = (df["time_et"] >= dtime(9, 30)) & (df["time_et"] < dtime(16, 0))
    df = df.loc[mask].reset_index(drop=True)
    bars = tuple(
        Bar(open_time=r.timestamp_et.to_pydatetime(), open=float(r.open), high=float(r.high),
            low=float(r.low), close=float(r.close), volume=float(r.volume),
            granularity_seconds=300, source="test")
        for r in df.itertuples(index=False)
    )
    ctx = det.build_context(bars)
    return df, ctx


def _bar_index(df: pd.DataFrame, d: str, t: str) -> int:
    dd = date.fromisoformat(d)
    tt = dtime.fromisoformat(t + ":00")
    m = (df["date"] == dd) & (df["time_et"] == tt)
    hits = np.flatnonzero(m.to_numpy())
    assert len(hits) == 1, f"anchor bar {d} {t} not found or ambiguous"
    return int(hits[0])


# ── 1. zero-fork: shipped cell byte-identical to the live registry predicate ─────────
def test_shipped_cell_matches_registry_predicate(real_ctx):
    df, ctx = real_ctx
    mismatches = []
    for t in range(1, len(ctx.bars)):
        a = det.detect_bar(ctx, t, SHIPPED)
        b = _engulfing_at_local_cluster_predicate(ctx, t)
        if a != b:
            mismatches.append((t, a, b))
    assert not mismatches, f"{len(mismatches)} mismatches vs live registry predicate, e.g. {mismatches[:3]}"


def test_shipped_config_flag():
    assert SHIPPED.is_shipped_config()
    assert not det.Cell(min_touches=4, min_body_dollars=0.40, tolerance=0.20).is_shipped_config()
    assert not det.Cell(min_touches=3, min_body_dollars=0.60, tolerance=0.20).is_shipped_config()
    assert not det.Cell(min_touches=3, min_body_dollars=0.40, tolerance=0.15).is_shipped_config()


# ── 2. C6 causality: mutating bars strictly after t must not change detect_bar(t) ────
def test_causal_c6_mutating_future_bars_does_not_change_result(real_ctx):
    df, ctx = real_ctx
    d, t_et = "2026-07-23", "10:40"
    t = _bar_index(df, d, t_et)
    baseline = det.detect_bar(ctx, t, SHIPPED)
    assert baseline is not None and baseline["bias"] == "bearish"

    mutated_bars = list(ctx.bars)
    for j in range(t + 1, min(t + 20, len(mutated_bars))):
        b = mutated_bars[j]
        mutated_bars[j] = Bar(open_time=b.open_time, open=b.open + 5.0, high=b.high + 5.0,
                               low=b.low + 5.0, close=b.close + 5.0, volume=b.volume,
                               granularity_seconds=b.granularity_seconds, source=b.source)
    mutated_ctx = det.build_context(tuple(mutated_bars))
    mutated = det.detect_bar(mutated_ctx, t, SHIPPED)
    assert mutated == baseline, "detect_bar(t) changed after mutating only bars > t -- C6 violation"


# ── 3. both live anchors fire on the shipped cell, matching registry's own declared
#      anchors on the engulfing_at_local_cluster PatternRule ──────────────────────────
def test_both_anchors_fire_on_shipped_cell(real_ctx):
    df, ctx = real_ctx
    bear_idx = _bar_index(df, "2026-07-23", "10:40")
    bull_idx = _bar_index(df, "2026-07-21", "11:05")
    bear_hit = det.detect_bar(ctx, bear_idx, SHIPPED)
    bull_hit = det.detect_bar(ctx, bull_idx, SHIPPED)
    assert bear_hit is not None and bear_hit["bias"] == "bearish"
    assert bull_hit is not None and bull_hit["bias"] == "bullish"


def test_registry_rule_declares_matching_anchors():
    rule = REGISTRY_BY_NAME["engulfing_at_local_cluster"]
    assert rule.anchors, "engulfing_at_local_cluster should carry its verified anchors"
    by_key = {(a["date"], a["time_et"]): a for a in rule.anchors}
    assert by_key[("2026-07-23", "10:40")]["bias"] == "bearish"
    assert by_key[("2026-07-23", "10:40")]["expected_fire"] is True
    assert by_key[("2026-07-21", "11:05")]["bias"] == "bullish"
    assert by_key[("2026-07-21", "11:05")]["expected_fire"] is True


# ── 4. grid construction ──────────────────────────────────────────────────────────────
def test_build_grid_cell_count_and_shipped_membership():
    axes = {"min_touches": [3, 4], "min_body_dollars": [0.0, 0.40, 0.60, 0.80],
            "tolerance": [0.15, 0.20]}
    grid = det.build_grid(axes)
    assert len(grid) == 16
    assert any(c.is_shipped_config() for c in grid)
    ids = {c.cell_id() for c in grid}
    assert len(ids) == len(grid), "cell_id collision in grid"

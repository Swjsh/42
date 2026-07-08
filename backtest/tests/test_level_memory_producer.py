"""Guard: level_memory shadow producer selection (V1, engine-vision build 2026-07-08).

The producer surfaces multi-day MEMORY levels to a SHADOW key (not the live entry feed). This
pins the selection logic: >= MIN_MEMORY filter, dedup-into-zones (strongest wins — no wall of
pivots), TOP_N cap, and ONE structural role per price (no contradictory-role bug).
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
if str(REPO / "backtest") not in sys.path:
    sys.path.insert(0, str(REPO / "backtest"))


def _prod():
    spec = importlib.util.spec_from_file_location(
        "level_memory_producer", REPO / "setup" / "scripts" / "level_memory_producer.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["level_memory_producer"] = m
    spec.loader.exec_module(m)
    return m


def _lvl(price, role, mem):
    from lib.watchers.level_memory import Level
    return Level(price=price, role=role, memory_score=mem, touches=int(mem // 2), wicks=1,
                 bars_consolidated=10, role_flips=1, first_seen_idx=0, last_touch_idx=5)


def test_min_memory_filter():
    prod = _prod()
    raw = [_lvl(750.0, "resistance", 50.0), _lvl(745.0, "support", 5.0)]  # 5 < MIN_MEMORY
    out = prod.select_levels(raw)
    assert all(o["memory_score"] >= prod.MIN_MEMORY for o in out)
    assert 745.0 not in [o["price"] for o in out]


def test_dedup_into_zone_keeps_strongest():
    prod = _prod()
    raw = [_lvl(746.7, "support", 151.0), _lvl(746.3, "support", 107.0)]  # within DEDUP_EPS
    out = prod.select_levels(raw)
    assert len(out) == 1 and out[0]["memory_score"] == 151.0  # strongest wins the zone


def test_top_n_cap():
    prod = _prod()
    raw = [_lvl(700.0 + i * 2, "support", 100.0 - i) for i in range(30)]  # 30 well-spaced levels
    out = prod.select_levels(raw)
    assert len(out) <= prod.TOP_N


def test_role_preserved_one_per_price():
    prod = _prod()
    raw = [_lvl(747.4, "support", 120.0), _lvl(748.8, "resistance", 111.0)]
    out = prod.select_levels(raw)
    roles = {o["price"]: o["role"] for o in out}
    assert roles[747.4] == "support" and roles[748.8] == "resistance"
    prices = [o["price"] for o in out]
    assert len(prices) == len(set(prices))  # one role per price

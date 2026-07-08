"""Guard: confluence_producer.build_zones (2026-07-08). Stacks structural sources into scored
zones (captures J's 745.39 = memory+trendline+wick_low) without re-inflating to noise."""
from __future__ import annotations
import importlib.util, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[2]


def _load():
    p = REPO / "setup" / "scripts"
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
    spec = importlib.util.spec_from_file_location("confluence_producer", p / "confluence_producer.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["confluence_producer"] = m
    spec.loader.exec_module(m)
    return m


def _p(price, source, w=30.0):
    return {"price": price, "source": source, "weight": w, "meta": ""}


def test_captures_stacked_745_confluence():
    prod = _load()
    pts = [_p(744.40, "memory", 74), _p(744.23, "trendline", 41), _p(745.21, "wick_low", 25),
           _p(747.70, "gap_magnet", 40),   # lone, far -> not a zone
           _p(730.00, "memory", 50)]        # lone single-source -> not a zone
    zones = prod.build_zones(pts, band=0.85, min_sources=2, top_n=8)
    z745 = [z for z in zones if 744.0 <= z["center"] <= 745.3]
    assert z745, "J's 745 confluence zone must be surfaced"
    assert z745[0]["n_sources"] == 3
    assert set(z745[0]["sources"]) == {"memory", "trendline", "wick_low"}
    assert not any(abs(z["center"] - 730.0) <= 0.85 for z in zones)   # lone single-source excluded


def test_min_sources_and_cap():
    prod = _load()
    lone = [_p(700 + i, "memory") for i in range(20)]      # all single-source, spread
    assert prod.build_zones(lone, min_sources=2) == []
    many = []
    for i in range(12):
        many.append(_p(700 + i * 3, "memory"))
        many.append(_p(700 + i * 3 + 0.1, "trendline"))   # 12 two-source clusters
    assert len(prod.build_zones(many, top_n=8)) <= 8

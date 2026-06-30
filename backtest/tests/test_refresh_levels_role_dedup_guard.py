"""GUARD (2026-06-30 #17a) — refresh_levels_intraday must never feed the engine a level whose
role flip-flops with spot, and must collapse the SAME logical level written by different prefixed
writers (INTRADAY_/PMH_/PML_) to ONE entry.

ROOT CAUSES this pins (so they cannot silently rot, C7):
  #1 role was assigned by transient price-vs-spot at compute time -> a premarket HIGH flipped
     resistance->support the moment price ran above it; two refresh runs at different spots left the
     SAME logical price carrying BOTH roles (self_check.check_level_integrity RED).
     FIX: role is now SEMANTIC (premarket_high/rth_high/swing_high -> resistance; *_low -> support),
     STABLE across the session regardless of spot.
  #2 dedup only stripped INTRADAY_ labels, so the non-prefixed curated PMH_/PML_ writers piled up
     6-9x at one price. FIX: dedup key strips INTRADAY_/PMH_/PML_ so all writers of one logical
     level collapse.

Asserts (per the task): (i) the producer logic yields NO price with contradictory ceiling+floor
roles on a synthetic input (incl. the exact flip-flop geometry: PMH with spot ABOVE it); (ii) dedup
collapses duplicate PMH_/PML_ writers to one entry. self_check is the live consumer — assert its
integrity check is GREEN on normalized output (close the producer/consumer contract).

$0, pure-Python, no network.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "refresh_levels_intraday", REPO / "setup" / "scripts" / "refresh_levels_intraday.py")
rli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rli)

_sc_spec = importlib.util.spec_from_file_location(
    "self_check", REPO / "setup" / "scripts" / "self_check.py")
sc = importlib.util.module_from_spec(_sc_spec)
_sc_spec.loader.exec_module(sc)

_CEIL = {"resistance", "broken_to_support"}
_FLOOR = {"support", "broken_to_resistance"}


def _roles_by_price(levels):
    by = {}
    for lv in levels:
        if str(lv.get("tier", "")).lower() == "expired":
            continue
        by.setdefault(round(float(lv["price"]), 2), set()).add(lv.get("role"))
    return by


def _assert_no_contradiction(levels):
    for price, roles in _roles_by_price(levels).items():
        assert not ((roles & _CEIL) and (roles & _FLOOR)), \
            f"price {price} carries BOTH ceiling and floor roles: {roles}"


# (i) — NO contradictory roles, incl. the exact flip-flop geometry --------------------------------

def test_pmh_role_is_stable_resistance_with_spot_above():
    """The 06-30 BROKEN signature: a premarket HIGH with spot ABOVE it. Price-side role would call
    it support (it ran through); the curated copy still says resistance -> contradiction. Semantic
    role pins it RESISTANCE either way -> ONE polarity, no contradiction."""
    polluted = [
        {"price": 741.81, "role": "resistance", "type": "resistance",
         "label": "PMH_2026-06-30", "source": "premarket_high", "tier": "Active"},
        {"price": 741.81, "role": "support", "type": "support",
         "label": "INTRADAY_PMH_2026-06-30", "source": "premarket_high", "tier": "Active"},
    ]
    out = rli._normalize_levels(polluted, spot=746.65)   # spot ABOVE the PMH (the live geometry)
    _assert_no_contradiction(out)
    assert all(lv["role"] == "resistance" for lv in out)


def test_pml_role_is_stable_support_with_spot_below():
    """Mirror: a premarket LOW with spot BELOW it. Price-side would flip it to resistance; semantic
    role keeps it support."""
    polluted = [
        {"price": 741.61, "role": "support", "type": "support",
         "label": "PML_2026-06-30", "source": "premarket_low", "tier": "Active"},
        {"price": 741.61, "role": "resistance", "type": "resistance",
         "label": "INTRADAY_PML_2026-06-30", "source": "premarket_low", "tier": "Active"},
    ]
    out = rli._normalize_levels(polluted, spot=735.0)    # spot BELOW the PML
    _assert_no_contradiction(out)
    assert all(lv["role"] == "support" for lv in out)


def test_mixed_session_no_contradiction_any_price():
    """A realistic mixed set (PMH + PML + RTH high/low + swing) at a single spot: assert the WHOLE
    normalized feed has no price carrying both polarities, and each role matches its source."""
    spot = 744.0
    src_levels = [
        ("PMH_2026-06-30", 741.81, "premarket_high", "resistance"),
        ("PML_2026-06-30", 741.61, "premarket_low", "support"),   # near PMH but distinct semantic
        ("INTRADAY_RTH_HIGH_2026-06-30", 748.0, "intraday_rth_high", "resistance"),
        ("INTRADAY_RTH_LOW_2026-06-30", 740.9, "intraday_rth_low", "support"),
        ("INTRADAY_SWING_LOW_2026-06-30", 743.2, "intraday_swing_low", "support"),
        ("DOUBLE_BOTTOM_RTH_LOW", 743.35, "double_session_low", "resistance"),  # audit-mapped
    ]
    levels = [{"price": p, "role": "x", "type": "x", "label": lab, "source": s, "tier": "Active"}
              for lab, p, s, _ in src_levels]
    out = rli._normalize_levels(levels, spot=spot)
    _assert_no_contradiction(out)
    got = {round(lv["price"], 2): lv["role"] for lv in out}
    for _, price, _, expect in src_levels:
        # near-equal prices may collapse; only assert role for prices that survived as a key.
        if round(price, 2) in got:
            assert got[round(price, 2)] == expect, f"{price} -> {got[round(price, 2)]} != {expect}"


# (ii) — dedup collapses duplicate PMH_/PML_ writers ----------------------------------------------

def test_dedup_collapses_pmh_prefix_writers():
    """8 curated PMH_ copies at one price -> ONE entry (root cause #2: PMH_ was not stripped before,
    so they piled up; INTRADAY-only dedup missed them)."""
    dupes = [{"price": 741.81, "role": "resistance", "type": "resistance",
              "label": "PMH_2026-06-30", "source": "premarket_high", "tier": "Active"}
             for _ in range(8)]
    out = rli._normalize_levels(dupes, spot=736.0)
    assert len(out) == 1 and out[0]["role"] == "resistance"


def test_dedup_collapses_pml_prefix_writers():
    dupes = [{"price": 734.52, "role": "support", "type": "support",
              "label": "PML_2026-06-29", "source": "premarket_low", "tier": "Active"}
             for _ in range(7)]
    out = rli._normalize_levels(dupes, spot=746.0)
    assert len(out) == 1 and out[0]["role"] == "support"


def test_dedup_collapses_pmh_with_intraday_twin():
    """The curated PMH_<date> and its INTRADAY_PMH twin at the same logical price collapse via the
    prefix-stripped key — one premarket high, not two."""
    levels = [
        {"price": 741.81, "role": "resistance", "type": "resistance",
         "label": "PMH_2026-06-30", "source": "premarket_high", "tier": "Active"},
        {"price": 741.81, "role": "resistance", "type": "resistance",
         "label": "INTRADAY_PMH_2026-06-30", "source": "premarket_high", "tier": "Active"},
    ]
    out = rli._normalize_levels(levels, spot=740.0)
    assert len(out) == 1
    assert out[0]["label"] == "PMH_2026-06-30"   # curated (non-INTRADAY) wins the tiebreak


def test_distinct_dates_do_not_overcollapse():
    """PMH from two DIFFERENT sessions (738.10 vs 741.81) must NOT collapse — different logical
    levels, different stripped keys (date suffix differs) and prices > ROLE_EPSILON apart."""
    levels = [
        {"price": 738.10, "role": "resistance", "type": "resistance",
         "label": "PMH_2026-06-29", "source": "premarket_high", "tier": "Active"},
        {"price": 741.81, "role": "resistance", "type": "resistance",
         "label": "PMH_2026-06-30", "source": "premarket_high", "tier": "Active"},
    ]
    out = rli._normalize_levels(levels, spot=740.0)
    assert len(out) == 2


# producer/consumer contract: self_check GREEN on normalized output -------------------------------

def test_self_check_green_after_normalize(tmp_path):
    """BITE + contract: the polluted INPUT trips self_check.check_level_integrity (RED); the
    normalized output clears it — proving normalize is what fixes the live signature."""
    polluted = [
        {"price": 741.81, "role": "resistance", "type": "resistance",
         "label": "PMH_2026-06-30", "source": "premarket_high", "tier": "Active"},
        {"price": 741.81, "role": "support", "type": "support",
         "label": "INTRADAY_PMH_2026-06-30", "source": "premarket_high", "tier": "Active"},
        {"price": 741.61, "role": "support", "type": "support",
         "label": "PML_2026-06-30", "source": "premarket_low", "tier": "Active"},
        {"price": 741.61, "role": "resistance", "type": "resistance",
         "label": "INTRADAY_PML_2026-06-30", "source": "premarket_low", "tier": "Active"},
    ]
    f = tmp_path / "k.json"
    f.write_text(json.dumps({"levels": polluted}), encoding="utf-8")
    assert sc.check_level_integrity(path=f) != []          # input is BROKEN (the bite)
    fixed = rli._normalize_levels(polluted, spot=746.0)
    f.write_text(json.dumps({"levels": fixed}), encoding="utf-8")
    assert sc.check_level_integrity(path=f) == []          # normalized is GREEN

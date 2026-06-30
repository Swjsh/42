"""Regression guard for the intraday level feed — the ONLY real shippable win of the
2026-06-29 missed-setups mission (markdown/research/MISSED-SETUPS-POSTMORTEM-2026-06-29.md).

THE BUG (J live-flagged 2026-06-29): key-levels.json was frozen at the 08:30 premarket
draw. Price ran to a new intraday high (739.90) but the engine's top near-price resistance
was still the stale PMH (738.10), so it logged rejection_level=None and was BLIND to the
live structure. `refresh_levels_intraday.py` fixes it by upserting live RTH high/low.

This guard pins that fix so it cannot silently rot (C7). It ALSO absorbs the lasting intent
of the rejected validator-inbox item `v_dual_rejection_starved_without_level` (pin the
frozen-key-levels root cause) WITHOUT building the detectors the post-mortem's own redundancy
backtest rejected as mirages-in-aggregate (DUAL_REJECTION redundant; double-bottom washes out).

$0, pure-Python, no network (df is injected via the refresh(df=) seam).
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
MOD_PATH = REPO / "setup" / "scripts" / "refresh_levels_intraday.py"

_spec = importlib.util.spec_from_file_location("refresh_levels_intraday", MOD_PATH)
rli = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rli)

# self_check is the live consumer that REDs on contradictory roles — assert the producer's
# output actually satisfies it (close the producer/consumer contract, not just unit logic).
_SC_PATH = REPO / "setup" / "scripts" / "self_check.py"
_sc_spec = importlib.util.spec_from_file_location("self_check", _SC_PATH)
sc = importlib.util.module_from_spec(_sc_spec)
_sc_spec.loader.exec_module(sc)


# Bars: (hm, high, low, close, volume). Last RTH close == spot (df["close"].iloc[-1]).
def _make_df(rth_bars, pre_bars=()):
    today = rli.et_now().strftime("%Y-%m-%d")
    rows = []
    for hm, hi, lo, cl, vol in list(pre_bars) + list(rth_bars):
        rows.append({"date": today, "hm": hm, "high": hi, "low": lo,
                     "close": cl, "volume": vol})
    return pd.DataFrame(rows)


# RTH high (739.90) ABOVE last close (736.00) — the exact 06-29 geometry.
_RTH = [
    ("09:35", 738.0, 736.0, 737.5, 1000),
    ("09:45", 739.9, 738.0, 738.5, 2000),   # <- live intraday high
    ("09:55", 738.5, 736.5, 737.0, 3000),
    ("10:05", 737.5, 735.5, 736.0, 2500),   # <- last close == spot 736.0
]
_PRE = [("09:00", 738.1, 737.0, 737.8, 500)]  # stale PMH 738.10 (the frozen top)


@pytest.fixture
def _state(tmp_path, monkeypatch):
    kl = tmp_path / "key-levels.json"
    bias = tmp_path / "today-bias.json"
    bias.write_text(json.dumps({"key_levels": {}}), encoding="utf-8")
    monkeypatch.setattr(rli, "KEY_LEVELS", kl)
    monkeypatch.setattr(rli, "TODAY_BIAS", bias)
    return kl, bias


def _active_resistances(kl_path, band=12.0):
    data = json.loads(kl_path.read_text(encoding="utf-8"))
    spot = data["spot_at_compute"]
    return sorted({lv["price"] for lv in data["levels"]
                   if lv["role"] == "resistance" and abs(lv["price"] - spot) <= band})


# --- pure logic ----------------------------------------------------------------

def test_swing_levels_detects_pivots():
    rth = _make_df([
        ("09:35", 737, 736, 736.5, 1),
        ("09:40", 738, 735, 737.0, 1),
        ("09:45", 740, 734, 739.0, 1),   # pivot high 740 + pivot low 734
        ("09:50", 739, 735, 738.0, 1),
        ("09:55", 738, 736, 737.0, 1),
        ("10:00", 737, 737, 737.0, 1),
    ])
    sh, sl = rli._swing_levels(rth)
    assert sh == 740.0 and sl == 734.0


def test_swing_levels_too_few_bars():
    assert rli._swing_levels(_make_df(_RTH[:3])) == (None, None)


def test_level_role_by_side():
    assert rli._level(740.0, 736.0, "x", "s", "2026-06-29T10:00:00-04:00")["role"] == "resistance"
    assert rli._level(730.0, 736.0, "x", "s", "2026-06-29T10:00:00-04:00")["role"] == "support"


# --- THE load-bearing regression guard -----------------------------------------

def test_live_rth_high_above_spot_becomes_active_resistance(_state):
    """The fix: a live intraday high above spot is upserted as ACTIVE resistance —
    the engine is no longer blind to it (the 06-29 missed-setup root cause)."""
    kl, _ = _state
    out = rli.refresh(df=_make_df(_RTH, _PRE))
    assert out["ok"] is True
    assert 739.9 in _active_resistances(kl)
    labels = {lv["label"].split("_2026")[0] for lv in json.loads(kl.read_text())["levels"]}
    assert "INTRADAY_RTH_HIGH" in labels and "INTRADAY_RTH_LOW" in labels


def test_frozen_levels_bug_would_be_caught(_state):
    """BITE: seed the FROZEN state (only the stale PMH 738.10) — the engine is blind to
    739.90. After refresh, 739.90 is active. Proves the guard is non-vacuous: pre-fix the
    assertion above would FAIL."""
    kl, _ = _state
    frozen = {"schema_version": 1, "spot_at_compute": 736.0, "levels": [
        {"price": 738.1, "role": "resistance", "type": "resistance",
         "label": "PMH_FROZEN", "tier": "Active"}]}
    kl.write_text(json.dumps(frozen), encoding="utf-8")
    assert 739.9 not in _active_resistances(kl)          # frozen: blind
    rli.refresh(df=_make_df(_RTH, _PRE))
    assert 739.9 in _active_resistances(kl)              # refreshed: sees it


def test_idempotent_no_intraday_duplication(_state):
    kl, _ = _state
    rli.refresh(df=_make_df(_RTH, _PRE))
    rli.refresh(df=_make_df(_RTH, _PRE))
    levels = json.loads(kl.read_text())["levels"]
    n_high = sum(1 for lv in levels if lv["label"].startswith("INTRADAY_RTH_HIGH"))
    assert n_high == 1


def test_preserves_non_intraday_levels(_state):
    """Structural/premarket levels (Carry, etc.) survive the additive upsert."""
    kl, _ = _state
    seed = {"schema_version": 1, "levels": [
        {"price": 731.0, "role": "support", "type": "support",
         "label": "CARRY_DAILY", "tier": "Active", "source": "structural"}]}
    kl.write_text(json.dumps(seed), encoding="utf-8")
    rli.refresh(df=_make_df(_RTH, _PRE))
    labels = {lv["label"] for lv in json.loads(kl.read_text())["levels"]}
    assert "CARRY_DAILY" in labels


def test_empty_bars_fail_open():
    assert rli.refresh(df=pd.DataFrame())["ok"] is False


# --- 2026-06-30 contradictory-role / duplication fix (drain the live BROKEN flag) ----------
# self_check.check_level_integrity REDs when one price carries BOTH a ceiling and a floor role,
# or appears >2x. The live key-levels.json was polluted: 741.81 x9, 741.61 x7, each as BOTH a
# curated resistance AND an INTRADAY support. _normalize_levels enforces one-polarity-role-per-
# price + price-dedup at the producer so the engine can never read contradictory structure.

def test_normalize_collapses_contradictory_roles_to_one_polarity():
    """The exact live shape: a curated resistance + an INTRADAY support at the SAME price.
    With spot above, both resolve to support; collapse to a single entry -> no contradiction."""
    polluted = ([{"price": 741.81, "role": "resistance", "type": "resistance",
                  "label": "PMH_2026-06-30", "tier": "Active"} for _ in range(6)]
                + [{"price": 741.81, "role": "support", "type": "support",
                   "label": "INTRADAY_PMH_2026-06-30", "tier": "Active"}])
    out = rli._normalize_levels(polluted, spot=745.0)   # 741.81 < spot -> support
    assert len(out) == 1
    assert out[0]["role"] == out[0]["type"] == "support"
    assert out[0]["label"] == "PMH_2026-06-30"          # curated survivor (exact-price tiebreak)


def test_normalize_collapses_heavy_duplicates():
    dupes = [{"price": 741.81, "role": "resistance", "type": "resistance",
              "label": "PMH_X", "tier": "Active"} for _ in range(8)]
    out = rli._normalize_levels(dupes, spot=736.0)       # 741.81 > spot -> resistance
    assert len(out) == 1 and out[0]["role"] == "resistance"


def test_normalize_preserves_expired_untouched():
    levels = [{"price": 730.0, "role": "support", "tier": "expired", "label": "OLD"},
              {"price": 740.0, "role": "support", "tier": "Active", "label": "A"}]
    out = rli._normalize_levels(levels, spot=736.0)
    active = [lv for lv in out if str(lv.get("tier", "")).lower() != "expired"]
    expired = [lv for lv in out if str(lv.get("tier", "")).lower() == "expired"]
    assert len(active) == 1 and active[0]["role"] == "resistance"   # 740 > 736 -> resistance
    assert len(expired) == 1 and expired[0]["role"] == "support"    # expired passes through


def test_refresh_output_passes_level_integrity_check(_state):
    """INTEGRATION (producer/consumer contract): seed a curated SUPPORT at the same price the
    live RTH high (resistance) lands on -> pre-fix the engine reads 739.9 as BOTH. The producer
    must emit a file self_check.check_level_integrity accepts."""
    kl, _ = _state
    seed = {"schema_version": 1, "levels": [
        {"price": 739.9, "role": "support", "type": "support",
         "label": "STALE_SUPPORT", "tier": "Active"}]}
    kl.write_text(json.dumps(seed), encoding="utf-8")
    rli.refresh(df=_make_df(_RTH, _PRE))                 # spot 736.0; RTH high 739.9 -> resistance
    assert sc.check_level_integrity(path=kl) == []
    at = [lv for lv in json.loads(kl.read_text())["levels"] if abs(lv["price"] - 739.9) <= 0.10]
    assert len(at) == 1 and at[0]["role"] == "resistance"


def test_bite_pre_normalize_contradiction_is_real(tmp_path):
    """BITE (non-vacuous): the producer's INPUT genuinely contains the contradiction the
    self-check flags, and _normalize_levels is what clears it. Neuter the normalize step and
    the RED returns -> the guard is doing real work."""
    polluted = [
        {"price": 741.81, "role": "resistance", "type": "resistance", "label": "PMH_X", "tier": "Active"},
        {"price": 741.81, "role": "support", "type": "support", "label": "INTRADAY_PMH_X", "tier": "Active"},
    ]
    f = tmp_path / "k.json"
    f.write_text(json.dumps({"levels": polluted}), encoding="utf-8")
    assert sc.check_level_integrity(path=f) != []        # input contradicts (the bite)
    fixed = rli._normalize_levels(polluted, spot=745.0)
    f.write_text(json.dumps({"levels": fixed}), encoding="utf-8")
    assert sc.check_level_integrity(path=f) == []        # normalized clears it
    assert len(fixed) == 1

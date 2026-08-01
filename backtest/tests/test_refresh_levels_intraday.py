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
# Volumes are realistic 5m SPY magnitudes (2026-07-27 degeneracy guard: DEGENERACY_MIN_BARS=3,
# DEGENERACY_MIN_VOLUME=10,000 — these fixtures must clear both bars to test the INTENDED
# behavior of the code they exercise; the guard's OWN refusal path gets its own dedicated
# guard fixtures below, deliberately built thin).
_RTH = [
    ("09:35", 738.0, 736.0, 737.5, 100_000),
    ("09:45", 739.9, 738.0, 738.5, 200_000),   # <- live intraday high
    ("09:55", 738.5, 736.5, 737.0, 300_000),
    ("10:05", 737.5, 735.5, 736.0, 250_000),   # <- last close == spot 736.0
]
# stale PMH 738.10 (the frozen top) — 3 bars (clears DEGENERACY_MIN_BARS), realistic volume.
_PRE = [
    ("08:00", 736.5, 735.5, 736.0, 40_000),
    ("08:30", 737.5, 736.0, 737.0, 35_000),
    ("09:00", 738.1, 737.0, 737.8, 45_000),
]


@pytest.fixture
def _state(tmp_path, monkeypatch):
    kl = tmp_path / "key-levels.json"
    bias = tmp_path / "today-bias.json"
    bias.write_text(json.dumps({"key_levels": {}}), encoding="utf-8")
    monkeypatch.setattr(rli, "KEY_LEVELS", kl)
    monkeypatch.setattr(rli, "TODAY_BIAS", bias)
    # Isolation fix (2026-08-01, conductor-weekend): this file's tests exercise the intraday
    # RTH/PMH/memory-merge logic with SYNTHETIC df fixtures, but refresh() also unconditionally
    # unions REAL multi-week shelf zones from daily_context.py (module-level global, WS1 v2
    # 2026-07-27). That makes every _state-based test's PASS/FAIL depend on today's actual live
    # SPY price action -- a synthetic PMH at 749.5 silently collided with a real shelf zone at
    # 748.66-750.26 and the intraday level lost the dedup tie (weight 5 shelf > weight 2
    # intraday), dropping the INTRADAY_PMH label the test asserted on
    # (test_refresh_flag_on_injects_memory, first observed red 2026-08-01, root cause: no test
    # here ever isolated the real daily_context call). daily_context=None is an
    # already-supported fail-open path (`if daily_context is not None:` in refresh()) -- shelf
    # zones have their own dedicated coverage in test_level_compiler_v2_guards.py, so disabling
    # them here makes this file deterministic without losing shelf test coverage anywhere.
    monkeypatch.setattr(rli, "daily_context", None)
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
    """The exact live shape: a curated PMH + its INTRADAY PMH twin at the SAME price. Role is now
    by SEMANTIC source (2026-06-30 root-cause #1 fix) -> a premarket HIGH is structurally RESISTANCE
    no matter where spot wanders (was: price-side, which flip-flopped to support once price ran
    through it -> the contradiction). Both collapse to ONE resistance entry -> no contradiction."""
    polluted = ([{"price": 741.81, "role": "resistance", "type": "resistance",
                  "label": "PMH_2026-06-30", "source": "premarket_high", "tier": "Active"} for _ in range(6)]
                + [{"price": 741.81, "role": "support", "type": "support",
                   "label": "INTRADAY_PMH_2026-06-30", "source": "premarket_high", "tier": "Active"}])
    out = rli._normalize_levels(polluted, spot=745.0)   # spot ABOVE the PMH; semantic role ignores that
    assert len(out) == 1
    assert out[0]["role"] == out[0]["type"] == "resistance"   # PMH is structurally a ceiling, stable
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


# =====================================================================================
# G11 LEVEL-MEMORY MERGE WIRE (2026-07-09) — HANDOFF-2026-07-09-G11-LEVEL-MEMORY-WIRE.md
# The shadow multi-day memory map (key-levels-memory.json) had ZERO live consumers (D1 audit
# Finding #4). This wire UNIONS its high-conviction near-price levels into key-levels.json so
# heartbeat_core._read_levels finally sees J's multi-day flip levels. Additive, fail-open,
# flag-gated (params.level_memory_live_merge). These guards pin: flag on injects near-price +
# role-stable; flag off byte-identical; missing map no-op; cap/score/window respected;
# premarket levels never dropped.
# =====================================================================================

# 8 in-window (score>=60, within +/-1.5% of spot 747.5) + 3 that MUST be excluded.
_MEM_LEVELS = [
    {"price": 747.93, "role": "resistance", "type": "resistance", "label": "MEMORY_RES_76",
     "memory_score": 76.0, "touches": 42, "role_flips": 10, "tier": "Active",
     "flipped_at": "2026-07-07T14:55:00-04:00", "source": "level_memory"},
    {"price": 747.13, "role": "resistance", "type": "resistance", "label": "MEMORY_RES_132",
     "memory_score": 132.0, "touches": 76, "role_flips": 18, "tier": "Active",
     "flipped_at": "2026-07-08T09:30:00-04:00", "source": "level_memory"},
    {"price": 746.49, "role": "resistance", "type": "resistance", "label": "MEMORY_RES_142",
     "memory_score": 142.0, "tier": "Active", "source": "level_memory"},
    {"price": 748.78, "role": "resistance", "type": "resistance", "label": "MEMORY_RES_111",
     "memory_score": 111.0, "tier": "Active", "source": "level_memory"},
    {"price": 745.34, "role": "resistance", "type": "resistance", "label": "MEMORY_RES_96",
     "memory_score": 96.0, "tier": "Active", "source": "level_memory"},
    {"price": 744.38, "role": "support", "type": "support", "label": "MEMORY_SUP_98",
     "memory_score": 98.0, "tier": "Active", "source": "level_memory"},
    {"price": 742.89, "role": "support", "type": "support", "label": "MEMORY_SUP_75",
     "memory_score": 75.0, "tier": "Active", "source": "level_memory"},
    {"price": 740.46, "role": "support", "type": "support", "label": "MEMORY_SUP_79",
     "memory_score": 79.0, "tier": "Active", "source": "level_memory"},
    # --- must be EXCLUDED ---
    {"price": 732.84, "role": "support", "type": "support", "label": "MEMORY_SUP_149",
     "memory_score": 149.0, "tier": "Active", "source": "level_memory"},     # out of +/-1.5%
    {"price": 747.40, "role": "resistance", "type": "resistance", "label": "MEMORY_LOWSCORE",
     "memory_score": 40.0, "tier": "Active", "source": "level_memory"},      # score < 60
    {"price": 747.20, "role": "resistance", "type": "resistance", "label": "MEMORY_REFTIER",
     "memory_score": 200.0, "tier": "Reference", "source": "level_memory"},  # tier != Active
]
_NOW = "2026-07-09T09:05:00-04:00"


def _write_mem(tmp_path, monkeypatch, levels=None):
    p = tmp_path / "key-levels-memory.json"
    p.write_text(json.dumps({"levels": _MEM_LEVELS if levels is None else levels}), encoding="utf-8")
    monkeypatch.setattr(rli, "MEMORY_MAP", p)
    return p


def _set_flag(tmp_path, monkeypatch, value):
    p = tmp_path / "params.json"
    if value is not None:
        p.write_text(json.dumps({"level_memory_live_merge": value}), encoding="utf-8")
    monkeypatch.setattr(rli, "PARAMS", p)   # value None -> non-existent path
    return p


# --- flag reader ----------------------------------------------------------------
def test_memory_merge_enabled_true(tmp_path, monkeypatch):
    _set_flag(tmp_path, monkeypatch, True)
    assert rli._memory_merge_enabled() is True


def test_memory_merge_enabled_false_and_absent(tmp_path, monkeypatch):
    _set_flag(tmp_path, monkeypatch, False)
    assert rli._memory_merge_enabled() is False
    _set_flag(tmp_path, monkeypatch, None)   # missing params file -> fail-off
    assert rli._memory_merge_enabled() is False


# --- _merge_memory_levels selection ---------------------------------------------
def test_merge_selects_nearest_three_per_side_incl_both_j_levels(tmp_path, monkeypatch):
    """DIRECTIONAL BALANCE (2026-07-27): _MEM_LEVELS has only 2 candidates ABOVE spot
    (747.93, 748.78) and 6 BELOW — capped independently at 3-per-side, so this yields
    2 above (both, pool exhausted) + 3 nearest below = 5, NOT the old nearest-6-overall
    (which would have picked 5 below + 1 above, still lopsided, and dropped 745.34).
    This is the exact failure class the change fixes: a side-blind nearest-N can starve
    the thinner side even when it has qualifying candidates."""
    _write_mem(tmp_path, monkeypatch)
    out = rli._merge_memory_levels([], spot=747.5, now_iso=_NOW)
    mem = [lv for lv in out if lv["source"] == "level_memory"]
    prices = sorted(lv["price"] for lv in mem)
    assert len(mem) == 5                                   # 2 above (pool-limited) + 3 below (cap)
    assert 747.13 in prices and 747.93 in prices           # BOTH J-called levels kept (ACCEPTANCE)
    assert 746.49 in prices and 748.78 in prices
    assert 745.34 in prices                                # 3rd-nearest below now included (was dropped pre-fix)
    assert 744.38 not in prices and 742.89 not in prices and 740.46 not in prices  # beyond the per-side cap
    assert 732.84 not in prices                            # out of +/-1.5% window
    assert 747.40 not in prices                            # score < 60
    assert 747.20 not in prices                            # tier != Active
    j = next(lv for lv in mem if lv["price"] == 747.93)    # provenance + EOD expiry carried
    assert j["role"] == "resistance" and j["source"] == "level_memory"
    assert j["expires_at"] == "2026-07-09T16:00:00-04:00"
    assert j["memory_score"] == 76.0 and j["flipped_at"] == "2026-07-07T14:55:00-04:00"


def test_merge_missing_map_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(rli, "MEMORY_MAP", tmp_path / "does-not-exist.json")
    seed = [{"price": 741.61, "role": "support", "label": "PML", "tier": "Active", "source": "premarket_low"}]
    out = rli._merge_memory_levels(list(seed), spot=747.5, now_iso=_NOW)
    assert out == seed                                     # untouched, no crash (fail-open)


def test_merge_strips_prior_memory_then_reinjects(tmp_path, monkeypatch):
    _write_mem(tmp_path, monkeypatch)
    stale = [{"price": 999.0, "role": "resistance", "label": "MEMORY_STALE",
              "tier": "Active", "source": "level_memory"}]
    out = rli._merge_memory_levels(list(stale), spot=747.5, now_iso=_NOW)
    assert not any(lv["price"] == 999.0 for lv in out)     # prior memory stripped (idempotent)
    assert any(lv["price"] == 747.13 for lv in out)        # fresh re-injected


def test_merge_preserves_premarket_levels(tmp_path, monkeypatch):
    _write_mem(tmp_path, monkeypatch)
    pm = [{"price": 741.61, "role": "support", "label": "PML_2026-06-30",
           "tier": "Active", "source": "premarket_low"},
          {"price": 747.5, "role": "resistance", "label": "INTRADAY_PMH_2026-07-09",
           "tier": "Active", "source": "premarket_high"}]
    out = rli._merge_memory_levels(list(pm), spot=747.5, now_iso=_NOW)
    labels = {lv["label"] for lv in out}
    assert "PML_2026-06-30" in labels and "INTRADAY_PMH_2026-07-09" in labels  # never dropped


# --- role stability through the normalizer --------------------------------------
def test_normalize_keeps_level_memory_resistance_below_spot():
    """The bite: a memory RESISTANCE below spot must NOT flip to support (the price-relative
    fallback would). Only the level_memory branch preserves the stored structural role."""
    mem = [{"price": 747.13, "role": "resistance", "type": "resistance",
            "label": "MEMORY_RES_132", "tier": "Active", "source": "level_memory"}]
    out = rli._normalize_levels(mem, spot=747.5)           # spot ABOVE the level
    assert len(out) == 1 and out[0]["role"] == out[0]["type"] == "resistance"


def test_normalize_non_memory_still_price_relative():
    """Byte-identical for non-memory sources: a generic level below spot is still support."""
    lv = [{"price": 747.13, "role": "resistance", "type": "resistance",
           "label": "GENERIC", "tier": "Active", "source": "structural"}]
    out = rli._normalize_levels(lv, spot=747.5)
    assert out[0]["role"] == "support"                     # unchanged pre-G11 behavior


# --- refresh() end-to-end: flag on vs off ---------------------------------------
def _mixed_df():
    # premarket + 4 RTH bars; extremes chosen NOT within 0.10 of any memory pick; last close = spot 747.5.
    # Realistic volumes (2026-07-27 degeneracy guard, see _RTH/_PRE note above).
    pre = [("08:00", 746.0, 744.5, 745.5, 20_000),
           ("08:30", 747.0, 745.5, 746.5, 25_000),
           ("09:00", 749.5, 743.5, 748.0, 30_000)]
    rth = [("09:35", 748.0, 747.0, 747.6, 100_000),
           ("09:40", 748.5, 747.2, 747.8, 100_000),
           ("09:45", 747.9, 743.9, 744.5, 100_000),
           ("09:50", 747.8, 747.1, 747.5, 100_000)]   # last close == spot 747.5
    return _make_df(rth, pre)


def test_refresh_flag_on_injects_memory(tmp_path, monkeypatch, _state):
    kl, _ = _state
    _write_mem(tmp_path, monkeypatch)
    _set_flag(tmp_path, monkeypatch, True)
    out = rli.refresh(df=_mixed_df())
    assert out["ok"] and out["memory_merged"] == 5   # directional balance: 2 above (pool-limited) + 3 below
    data = json.loads(kl.read_text())
    prices = {lv["price"] for lv in data["levels"] if lv.get("source") == "level_memory"}
    assert 747.13 in prices and 747.93 in prices           # ACCEPTANCE: both J levels in the live file
    # premarket-derived INTRADAY levels survive alongside (additive)
    labels = {lv["label"].split("_2026")[0] for lv in data["levels"]}
    assert "INTRADAY_PMH" in labels


def test_refresh_flag_off_byte_identical(tmp_path, monkeypatch, _state):
    """Flag off: memory map present but NEVER merged -> zero level_memory entries -> byte-identical."""
    kl, _ = _state
    _write_mem(tmp_path, monkeypatch)
    _set_flag(tmp_path, monkeypatch, False)
    out = rli.refresh(df=_mixed_df())
    assert out["memory_merged"] == 0
    data = json.loads(kl.read_text())
    assert not any(lv.get("source") == "level_memory" for lv in data["levels"])


def test_refresh_flag_on_missing_map_no_crash(tmp_path, monkeypatch, _state):
    kl, _ = _state
    monkeypatch.setattr(rli, "MEMORY_MAP", tmp_path / "nope.json")
    _set_flag(tmp_path, monkeypatch, True)
    out = rli.refresh(df=_mixed_df())
    assert out["ok"] and out["memory_merged"] == 0         # fail-open no-op, feed intact

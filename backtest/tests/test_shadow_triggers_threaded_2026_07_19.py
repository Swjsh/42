"""Guard: shadow_triggers_fired threaded from engine_cli.decide_payload all the way
to setup/scripts/heartbeat_core.py's core-decisions.jsonl row (queue.md
TRENDLINE-FIXES-2026-07-17 item 4, filed after today's J-called trendline break was
invisible in the ledger -- the FIRST live validation point for trendline_reclaim had
no visibility surface).

WHAT THIS PINS (mirrors test_trigger_level_exact_provenance.py's methodology exactly):

  PART 1 -- SOURCE OF TRUTH: decide_payload's new "shadow_triggers_fired" key equals
  score.bull.shadow_triggers_fired (filters.BullishSetupResult, LOGGED-ONLY per
  test_bull_trendline_wick_reclaim_shadow_only.py) -- non-vacuous (a bar+level combo
  that fires BOTH shadow triggers vs one that fires neither), AND every scored/routed
  field (verdict/side/setup_name/triggers_fired/quality_tier/gate/reason) stays
  byte-identical regardless -- shadow detection must never leak into routing.

  PART 2 -- CORE LANE: setup/scripts/heartbeat_core.py's run_account() stamps
  "shadow_triggers_fired" into the core-decisions.jsonl row straight from the verdict,
  None-safe (missing key / legacy verdict shape -> [], never a crash), and it is an
  EMISSION-ONLY addition -- the LOGGED row differs only in this one new key.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_shadow_triggers_threaded_2026_07_19.py -q
"""
from __future__ import annotations

import datetime as dt
import importlib
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
BACKTEST = ROOT / "backtest"
_SCRIPTS = ROOT / "setup" / "scripts"
for _p in (str(BACKTEST), str(ROOT), str(_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.engine.engine_cli import decide_payload  # noqa: E402

# =============================================================================
# PART 1 -- SOURCE OF TRUTH: decide_payload's "shadow_triggers_fired" ==
# score.bull.shadow_triggers_fired, with zero effect on any scored/routed field.
# Reuses the EXACT fixture construction from
# test_bull_trendline_wick_reclaim_shadow_only.py (both shadow detectors fire on
# variant A via a descending-pivot trendline break + a wick-tolerant level reclaim;
# neither fires on variant B), but drives it through the FULL JSON payload boundary
# (decide_payload), not evaluate_bullish_setup directly -- proving the wiring survives
# the score_bar -> _derive_routing -> base-dict assembly path this build touched.
# =============================================================================

# NOTE: "bear_score"/"bear_blockers" are deliberately EXCLUDED here. The A/B fixtures
# differ in levels_active ([96.50] vs []) to drive the bull-side shadow triggers (same
# convention as test_bull_trendline_wick_reclaim_shadow_only.py); that level presence
# also legitimately feeds bear-side proximity scoring (a real, independent scoring
# input, not a shadow-trigger leak) -- e.g. bear_score is 5 in variant A vs 4 in
# variant B purely from the extra level candidate, same as it would be with the
# shadow-trigger code deleted entirely. The routing-relevant proof (bear never WINS
# in either variant, and every bull/routing field below is untouched) is what this
# guard exists to pin.
_BEHAVIOR_KEYS = (
    "verdict", "side", "setup_name", "bull_score",
    "bull_blockers", "triggers_fired", "rejection_level",
    "quality_tier", "gate", "reason",
)

# Isolate filter 11 (trigger-count/level-tied gate) on the bull side, same as the
# shadow-only guard -- the outcome (bull.passed False, blocked=[11]) is unambiguous
# and doesn't depend on constructing a realistic ribbon/VIX/spread context.
_DISABLE_ALL_BUT_FILTER_11 = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]


def _descending_pivot_bars(pivots: dict[int, float], n: int = 62,
                            baseline_high: float = 95.20) -> list[dict]:
    rows = []
    for i in range(n):
        if i < 2:
            rows.append({"open": 90.0, "high": 90.3, "low": 89.8, "close": 90.1, "volume": 100000})
            continue
        wpos = i - 2
        if wpos in pivots:
            hv = pivots[wpos]
            rows.append({"open": hv - 0.5, "high": hv, "low": hv - 0.7, "close": hv - 0.3, "volume": 100000})
        else:
            rows.append({"open": 94.9, "high": baseline_high, "low": 94.7, "close": 94.9, "volume": 100000})
    return rows


def _payload(bar: dict, levels_active: list[float]) -> dict:
    prior_bars = _descending_pivot_bars({5: 100.00, 20: 99.00, 35: 98.00})
    return {
        "bar_ctx": {
            "bar_idx": 62, "timestamp_et": "2026-05-01T13:35:00",
            "bar": bar, "prior_bars": prior_bars,
            "ribbon_now": None, "ribbon_history": [],
            "vix_now": 15.0, "vix_prior": 15.0,
            "vol_baseline_20": 100_000.0, "range_baseline_20": 0.5,
            "levels_active": levels_active, "multi_day_levels": [],
            "htf_15m_stack": "BULL", "level_states": {},
        },
        "score_params": {
            "bull_kwargs": {"disable_filters": _DISABLE_ALL_BUT_FILTER_11},
            # Filter 7 (bear side) is volume_divergence_failed, which indexes
            # ctx.prior_bars.iloc[ctx.bar_idx] -- this fixture's prior_bars only covers
            # bull-trendline construction (bar_idx == len(prior_bars), i.e. the trigger
            # bar deliberately lives OUTSIDE prior_bars, same convention
            # test_bull_trendline_wick_reclaim_shadow_only.py uses). Disabling just
            # filter 7 avoids that out-of-bounds read; filter 10 (min_triggers) stays
            # ACTIVE so the bear side is still genuinely gated (no artificial pass).
            "bear_kwargs": {"disable_filters": [7]},
        },
    }


# Variant A: BOTH shadow triggers fire (trendline_reclaim via the descending-pivot
# breakout; wick_reclaim via level=96.50, wick-tolerant). detect_level_reclaim does
# NOT fire (close 96.45 is not > 96.50) so triggers_fired stays empty despite 2
# shadow detections -- the sharpest possible non-contamination proof.
_BAR_A = {"open": 96.00, "high": 96.60, "low": 95.90, "close": 96.45, "volume": 500_000}
# Variant B: neither shadow trigger fires (flat bar, no active level).
_BAR_B = {"open": 96.00, "high": 96.05, "low": 95.95, "close": 96.00, "volume": 500_000}


def test_decide_payload_forwards_bull_shadow_triggers_fired_non_vacuous():
    result_a = decide_payload(_payload(_BAR_A, [96.50]))
    result_b = decide_payload(_payload(_BAR_B, []))

    assert result_a["shadow_triggers_fired"] == ["trendline_reclaim", "wick_reclaim"], (
        f"fixture must fire BOTH shadow triggers via the full decide_payload path; "
        f"got {result_a['shadow_triggers_fired']}"
    )
    assert result_b["shadow_triggers_fired"] == [], (
        f"fixture must fire NEITHER shadow trigger; got {result_b['shadow_triggers_fired']}"
    )


def test_decide_payload_shadow_triggers_do_not_affect_any_scored_or_routed_field():
    """THE zero-behavior-change proof, replayed at the decide_payload boundary: every
    verdict/routing key stays byte-identical between the shadow-firing and
    shadow-silent variant -- only shadow_triggers_fired itself differs."""
    result_a = decide_payload(_payload(_BAR_A, [96.50]))
    result_b = decide_payload(_payload(_BAR_B, []))

    for key in _BEHAVIOR_KEYS:
        assert result_a[key] == result_b[key], (
            f"{key!r} must be byte-identical regardless of shadow-trigger presence: "
            f"A={result_a[key]!r} vs B={result_b[key]!r}"
        )
    # Sharpest form: triggers_fired empty in both, even though 2 shadow triggers fired in A.
    assert result_a["triggers_fired"] == [], (
        f"triggers_fired must stay empty even though shadow triggers fired "
        f"(contamination): {result_a['triggers_fired']!r}"
    )
    assert result_a["verdict"] == "HOLD" and result_b["verdict"] == "HOLD", (
        "control: neither side should win (bull blocked by filter 11 in isolation, "
        "bear never constructed to pass) -- if this drifts the fixture needs updating, "
        "not the assertion"
    )


def test_decide_payload_shadow_triggers_fired_empty_when_bull_disabled():
    """score.bull is None when enable_bullish=false -- must default to [] cleanly,
    never crash on a None attribute access."""
    payload = _payload(_BAR_A, [96.50])
    payload["score_params"]["enable_bullish"] = False
    result = decide_payload(payload)
    assert result["bull_score"] is None
    assert result["shadow_triggers_fired"] == []


# =============================================================================
# PART 2 -- CORE LANE: setup/scripts/heartbeat_core.py's run_account() stamps
# shadow_triggers_fired from the verdict into the LOGGED core-decisions.jsonl row.
# Mirrors test_trigger_level_exact_provenance.py's _wire_run_account harness exactly.
# =============================================================================


@pytest.fixture()
def hc():
    return importlib.import_module("heartbeat_core")


def _wire_run_account(hc, monkeypatch, now, verdict):
    payload = {"bar_ctx": {
        "timestamp_et": now.strftime("%Y-%m-%d %H:%M:%S"),
        "bar": {"close": 620.0},
        "ribbon_now": {"stack": "BEAR_STACK", "spread_cents": 45.0},
        "vix_now": 17.2, "vix_prior": 17.3, "htf_15m_stack": "BEAR",
        "levels_active": [],
    }}
    monkeypatch.setattr(hc, "_et_now", lambda: now)
    monkeypatch.setattr(hc, "_fetch_spy_5m", lambda: None)
    monkeypatch.setattr(hc, "_build_payload", lambda df, p, **k: payload)
    monkeypatch.setattr(hc, "_engine_verdict", lambda p: dict(verdict))
    monkeypatch.setattr(hc, "CORE_MANAGES_EXITS", False)
    monkeypatch.setattr(hc, "CORE_PLACES_ORDERS", True)
    monkeypatch.setattr(hc, "_execute", lambda *a, **k: {"status": "WOULD_PLACE"})
    monkeypatch.setattr(hc, "_free_model_eval", lambda *a, **k: {"veto": False})
    logged: list = []
    monkeypatch.setattr(hc, "_log", lambda rec: logged.append(rec))
    monkeypatch.setitem(sys.modules, "setup_dispatch",
                        types.SimpleNamespace(dispatch_extra_setups=lambda *a, **k: []))
    return logged


def test_run_account_stamps_shadow_triggers_fired_from_verdict(hc, monkeypatch):
    verdict = {"verdict": "HOLD", "side": None, "setup_name": None,
              "bear_score": 3, "bull_score": 8, "triggers_fired": [], "reason": "test",
              "rejection_level": None, "shadow_triggers_fired": ["trendline_reclaim", "wick_reclaim"]}
    logged = _wire_run_account(hc, monkeypatch, dt.datetime(2026, 7, 19, 13, 35), verdict)
    rec = hc.run_account("safe")
    assert rec["shadow_triggers_fired"] == ["trendline_reclaim", "wick_reclaim"]
    assert logged and logged[-1]["shadow_triggers_fired"] == ["trendline_reclaim", "wick_reclaim"], (
        "the LOGGED core-decisions.jsonl row must carry it too"
    )


def test_run_account_shadow_triggers_fired_none_safe_when_verdict_lacks_it(hc, monkeypatch):
    """None-safe legacy compatibility: a verdict shaped like an older engine_cli output
    (no "shadow_triggers_fired" key at all) -> [] on the ledger row, never a crash."""
    verdict = {"verdict": "HOLD", "side": None, "setup_name": None,
              "bear_score": 3, "bull_score": 1, "triggers_fired": [], "reason": "no setup"}
    _wire_run_account(hc, monkeypatch, dt.datetime(2026, 7, 19, 13, 35), verdict)
    rec = hc.run_account("safe")
    assert rec["shadow_triggers_fired"] == []


def test_run_account_shadow_triggers_fired_is_emission_only(hc, monkeypatch):
    """vary-and-assert: every OTHER key in the logged row is byte-identical whether or
    not shadow_triggers_fired is present in the verdict -- pure data-emission addition."""
    verdict_without = {"verdict": "HOLD", "side": None, "setup_name": None,
                      "bear_score": 3, "bull_score": 1, "triggers_fired": [], "reason": "no setup"}
    logged_without = _wire_run_account(hc, monkeypatch, dt.datetime(2026, 7, 19, 13, 35), verdict_without)
    rec_without = hc.run_account("safe")

    verdict_with = {**verdict_without, "shadow_triggers_fired": ["wick_reclaim"]}
    logged_with = _wire_run_account(hc, monkeypatch, dt.datetime(2026, 7, 19, 13, 35), verdict_with)
    rec_with = hc.run_account("safe")

    for key in ("verdict", "side", "setup", "bear_score", "bull_score", "triggers",
                "reason", "trigger_level_exact", "spy", "ribbon", "spread_cents", "vix", "htf_15m"):
        assert rec_without[key] == rec_with[key], (
            f"{key!r} must be byte-identical: {rec_without[key]!r} vs {rec_with[key]!r}"
        )
    assert rec_without["shadow_triggers_fired"] == []
    assert rec_with["shadow_triggers_fired"] == ["wick_reclaim"]
    assert logged_without and logged_with
    assert logged_without[-1]["shadow_triggers_fired"] == []
    assert logged_with[-1]["shadow_triggers_fired"] == ["wick_reclaim"]


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))

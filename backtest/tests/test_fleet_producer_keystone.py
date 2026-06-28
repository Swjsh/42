"""KEYSTONE guard — the bold-fleet producer's looser-than-production property.

WHY THIS EXISTS (BOLD-FLEET-PRODUCER-KEYSTONE, the highest-leverage fleet contract):
The single most consequential behaviour of the entire bold paper fleet is that a
*gated-but-A+* signal — one production HELD because a downstream gate vetoed it — must
still emit ``passed=true`` on the BOLD perception, so the looser fleet arms can take the
A+ setup production's tight gates blocked. The original keystone BUG (workflow w2dnmn1pr,
2026-06-24) was the inverse: ``passed`` derived ONLY from production ``action=='ENTER_*'``
off the SAFE ledger, so a gated HOLD emitted ``passed=false`` on every tick and EVERY
fleet arm was inert — the fleet could only ever be TIGHTER than production, never looser.

The fix shipped LIVE 2026-06-25 (``SCORING_PEAK_LIVE=True`` + ``USE_CORE_LEDGER=True`` +
the dual-perception ``signal['bold']`` block off ``_bold_passed_blocks``), but it had NO
guard in the curated suite. A regression — flipping ``SCORING_PEAK_LIVE`` back to False,
breaking ``passed_scoring_peak``'s threshold/trigger logic, or breaking the BOLD-ledger
read — would silently revert the whole fleet to INERT (the original keystone bug) with the
gate green. This guard pins the contract so that can't happen silently.

RAIL-4 CLEAR: test-only; imports + reads the producer, mutates NOTHING in production;
changes no params/doctrine/orders. ENGINE-BENEFIT authoring (OP-22/OP-26) — ships on green.

This is the WATCH-validation parity slice the STATUS named: it reproduces "a gated 11/11
emits passed=true" end-to-end through the live ``build()`` and BITE-tests that the inert
revert (flag off) is caught.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- import the fleet producer (lives outside backtest/, alongside the fleet) ---
_REPO = Path(__file__).resolve().parents[2]
_FLEET = _REPO / "automation" / "state" / "fleet"
for _p in (str(_FLEET), str(_REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_shared_signal as bss  # noqa: E402

# DST-aware-equivalent fixed ET offset for deterministic fixtures (matches the sibling
# fleet test convention; the producer parses the ts_et string, not the tz object).
ET = timezone(timedelta(hours=-4))


# =============================================================================
# A. passed_scoring_peak — the unit contract (the looser-than-production rule)
# =============================================================================
def test_gated_aplus_bull_passes_the_keystone_property():
    """Production HOLD + score at the bull peak (9/11) + a real entry-trigger fired ->
    passed=True. THIS is the keystone: the loose arms see the A+ production's gate blocked."""
    assert bss.passed_scoring_peak("bull", "HOLD", 9, "level_reclaim", True) is True


def test_gated_aplus_bear_passes_at_its_own_threshold():
    """Bear peak is 8 (bear_score is /10, asymmetric from bull's 9/11). HOLD + 8 + entry-
    trigger -> True; one below (7) -> False. Pins the asymmetric thresholds."""
    assert bss.passed_scoring_peak("bear", "HOLD", 8, "level_rejection", True) is True
    assert bss.passed_scoring_peak("bear", "HOLD", 7, "level_rejection", True) is False


def test_score_without_a_fired_trigger_is_blocked():
    """The quality gate that stops pure-score over-emission: a peak score with NO fired
    trigger does NOT pass (else the loose arms would fire on every high-score chop tick)."""
    assert bss.passed_scoring_peak("bull", "HOLD", 11, None, False) is False
    assert bss.passed_scoring_peak("bull", "HOLD", 11, "level_reclaim", False) is False


def test_score_with_non_entry_trigger_is_blocked():
    """A fired trigger that is NOT in ENTRY_TRIGGERS (e.g. trendline_rejection — seen on the
    real 2026-06-26 rows) does NOT satisfy the quality gate. Pins the trigger allowlist."""
    assert "trendline_rejection" not in bss.ENTRY_TRIGGERS
    assert bss.passed_scoring_peak("bull", "HOLD", 11, "trendline_rejection", True) is False


def test_below_threshold_is_blocked_even_with_entry_trigger():
    """Score below the peak -> blocked regardless of trigger (it is not an A+ setup)."""
    assert bss.passed_scoring_peak("bull", "HOLD", 8, "level_reclaim", True) is False


def test_production_enter_always_passes_regardless_of_score():
    """If production itself ENTERED this side, passed is True even with score 0 / no trigger
    (the arm can still filter it further; it never enters when production held — only looser)."""
    assert bss.passed_scoring_peak("bull", "ENTER_BULL", 0, None, False) is True
    assert bss.passed_scoring_peak("bear", "ENTER_BEAR", 0, None, False) is True


def test_entry_trigger_allowlist_is_the_known_set():
    """Pin the exact ENTRY_TRIGGERS set — adding/removing one changes which gated setups the
    fleet can take, so a silent edit here must RED this guard (it is a live-behaviour knob)."""
    assert bss.ENTRY_TRIGGERS == frozenset({
        "level_reclaim", "ribbon_flip", "sequence_reclaim", "multi_day_confluence",
        "confluence", "level_rejection", "sequence_rejection",
    })
    assert bss.BULL_PEAK_THRESHOLD == 9
    assert bss.BEAR_PEAK_THRESHOLD == 8


# =============================================================================
# B. build() dual-perception — the keystone reproduced end to end
# =============================================================================
def _seed_two_rows(tmp_path, monkeypatch, *, today, safe_verdict, bold_verdict,
                   bold_bull_score, bold_triggers, ts="11:00:00"):
    """Write a 2-row core-decisions.jsonl (one safe, one bold) and point the producer at it.

    The SAFE row drives top-level production-faithful bear/bull; the BOLD row drives the
    dual-perception signal['bold'] via _bold_passed_blocks. Both fresh + non-blind so build()
    reaches the dual-perception path (not the beacon / no-decision stub)."""
    core = tmp_path / "core-decisions.jsonl"
    base = {"spy": 600.0, "ribbon": "BEAR", "spread_cents": 30, "vix": 15.0,
            "htf_15m": "BEAR", "side": "C", "bear_score": 4}
    safe = {**base, "ts_et": f"{today}T{ts}", "account": "safe",
            "verdict": safe_verdict, "setup": None, "bull_score": 2,
            "triggers": [], "action": safe_verdict}
    bold = {**base, "ts_et": f"{today}T{ts}", "account": "bold",
            "verdict": bold_verdict, "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
            "bull_score": bold_bull_score, "triggers": bold_triggers, "action": bold_verdict}
    core.write_text(json.dumps(safe) + "\n" + json.dumps(bold) + "\n", encoding="utf-8")
    monkeypatch.setattr(bss, "CORE_DECISIONS", core)
    monkeypatch.setattr(bss, "OUT", tmp_path / "shared-signal.json")
    monkeypatch.setattr(bss, "BEACON", tmp_path / "no-beacon.json")  # force the ledger path


def test_gated_bold_aplus_passes_while_production_holds(tmp_path, monkeypatch):
    """THE KEYSTONE, end to end: production HELD the bull (safe verdict=HOLD) but the BOLD
    perception saw an A+ reclaim (score 10/11 + level_reclaim) -> signal['bold']['bull']
    .passed is True while the production-faithful top-level signal['bull'].passed stays False.
    This is exactly 'a gated 11/11 emits passed=true' for the loose arms."""
    now = datetime(2026, 6, 26, 11, 2, tzinfo=bss.ET)  # aware ET_TZ — exercises the real producer now-path
    today = now.strftime("%Y-%m-%d")
    _seed_two_rows(tmp_path, monkeypatch, today=today, safe_verdict="HOLD",
                   bold_verdict="HOLD", bold_bull_score=10, bold_triggers=["level_reclaim"])
    sig = bss.build(now=now, scoring_peak=True, emit_strategies=False, run_vwap=False)
    assert sig["bull"]["passed"] is False, "top-level must stay production-faithful (HOLD)"
    assert sig["bold"]["bull"]["passed"] is True, "loose arms must SEE the gated A+ reclaim"
    assert sig.get("scoring_peak_live") is True


def test_scoring_peak_off_reverts_fleet_to_inert_BITE(tmp_path, monkeypatch):
    """BITE TEST (non-vacuous): with scoring_peak False the SAME gated A+ produces NO bold
    block and a production-faithful False -> the fleet is INERT (the original keystone bug).
    Proves this guard genuinely catches a SCORING_PEAK_LIVE=False regression."""
    now = datetime(2026, 6, 26, 11, 2, tzinfo=bss.ET)  # aware ET_TZ — exercises the real producer now-path
    today = now.strftime("%Y-%m-%d")
    _seed_two_rows(tmp_path, monkeypatch, today=today, safe_verdict="HOLD",
                   bold_verdict="HOLD", bold_bull_score=10, bold_triggers=["level_reclaim"])
    sig = bss.build(now=now, scoring_peak=False, emit_strategies=False, run_vwap=False)
    assert "bold" not in sig, "flag off -> no dual perception -> loose arms get nothing"
    assert sig["bull"]["passed"] is False


def test_bold_score_without_entry_trigger_does_not_pass(tmp_path, monkeypatch):
    """A high BOLD score but only a non-entry trigger (trendline_rejection) -> bold does NOT
    pass (the quality gate holds through the full build() path, not just the unit fn)."""
    now = datetime(2026, 6, 26, 11, 2, tzinfo=bss.ET)  # aware ET_TZ — exercises the real producer now-path
    today = now.strftime("%Y-%m-%d")
    _seed_two_rows(tmp_path, monkeypatch, today=today, safe_verdict="HOLD",
                   bold_verdict="HOLD", bold_bull_score=11,
                   bold_triggers=["trendline_rejection"])
    sig = bss.build(now=now, scoring_peak=True, emit_strategies=False, run_vwap=False)
    assert sig["bold"]["bull"]["passed"] is False


def test_strategies_derive_from_looser_bold_perception(tmp_path, monkeypatch):
    """The producer-consumer unlock: when the BOLD perception passed a side production held,
    the emitted strategies[] ribbon_ride entry derives from the LOOSER perception -> the loose
    arms actually receive a plan-able entry (top-level stays production-faithful)."""
    now = datetime(2026, 6, 26, 11, 2, tzinfo=bss.ET)  # aware ET_TZ — exercises the real producer now-path
    today = now.strftime("%Y-%m-%d")
    _seed_two_rows(tmp_path, monkeypatch, today=today, safe_verdict="HOLD",
                   bold_verdict="HOLD", bold_bull_score=10, bold_triggers=["level_reclaim"])
    sig = bss.build(now=now, scoring_peak=True, emit_strategies=True, run_vwap=False)
    ribbon = [s for s in sig.get("strategies", []) if s["name"] == "ribbon_ride"]
    assert len(ribbon) == 1 and ribbon[0]["side"] == "C", \
        "loose arms must get the ribbon_ride 'C' entry the gated A+ implies"
    assert sig["bull"]["passed"] is False  # top-level unchanged


def test_production_enter_top_level_still_passes(tmp_path, monkeypatch):
    """Sanity / no-regression: when production DID enter, the top-level block still passes
    (the keystone only ADDS looser bold passes, never removes production-faithful ones)."""
    now = datetime(2026, 6, 26, 11, 2, tzinfo=bss.ET)  # aware ET_TZ — exercises the real producer now-path
    today = now.strftime("%Y-%m-%d")
    _seed_two_rows(tmp_path, monkeypatch, today=today, safe_verdict="ENTER_BULL",
                   bold_verdict="ENTER_BULL", bold_bull_score=10,
                   bold_triggers=["level_reclaim"])
    sig = bss.build(now=now, scoring_peak=True, emit_strategies=False, run_vwap=False)
    assert sig["bull"]["passed"] is True
    assert sig["production_action"] == "ENTER_BULL"

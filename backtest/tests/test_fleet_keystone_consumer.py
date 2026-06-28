"""KEYSTONE CONSUMER guard -- the producer->consumer link the keystone fix depends on.

WHY THIS EXISTS (BOLD-FLEET-PRODUCER-KEYSTONE, the signal-vs-consumer parity slice).
``test_fleet_producer_keystone.py`` proves the *producer* (``build_shared_signal.build``)
emits ``signal['bold']['bull'].passed == True`` for a gated-but-A+ setup. But emitting a
passed block is only HALF the keystone: the bold paper fleet only actually TRADES that
signal if the live CONSUMER -- ``fleet_executor.plan_entry`` -- turns the ``signal['bold']``
block into an ``ENTER`` plan for a loose arm. There was NO fast guard on that link: the
producer test never calls ``plan_entry``, and the only end-to-end proof (``replay_fleet_arms.py``)
is a heavy standalone backtest script outside the curated pytest suite, so a regression that
left the fleet INERT at the *consumer* (e.g. ``_perception_for_arm`` stops routing a bold arm
to ``signal['bold']``, or ``_chosen_side`` stops reading ``passed``) would ship green.

This guard closes that link end to end, fast, offline ($0): a synthetic gated-A+ BOLD
core-decisions row -> the REAL ``build()`` (dual-perception) -> the REAL
``fleet_executor.plan_entry`` for a LOOSE bold arm -> must ``ENTER``; a TIGHT arm on the same
signal must still ``HOLD`` (the keystone makes the fleet looser, not indiscriminate); a SAFE
arm must read the production-faithful ``signal['safe']`` and ``HOLD`` (perception-source
confound fix); and -- the BITE -- with ``scoring_peak=False`` the SAME row drives the loose
arm to ``HOLD`` (the chain reverts to the original inert keystone bug, caught at the consumer).

RAIL-4 CLEAR: test-only. Imports + reads the producer and consumer, mutates NOTHING in
production (monkeypatches the producer's file paths to a tmp_path), changes no
params/doctrine/orders, places no order. ENGINE-BENEFIT authoring (OP-22/OP-26) -- ships on green.

Arms are constructed SYNTHETICALLY here (not read from the live accounts.json) so this guards
the CONSUMER CONTRACT independently of the current roster -- the keystone build's remaining
slices re-tier accounts.json (slice 4), and this guard must keep holding across that edit.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- import the fleet producer + consumer (both live outside backtest/) ---
_REPO = Path(__file__).resolve().parents[2]
_FLEET = _REPO / "automation" / "state" / "fleet"
for _p in (str(_FLEET), str(_REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_shared_signal as bss  # noqa: E402
import fleet_executor as fx  # noqa: E402

# Fixed ET offset for deterministic fixtures (the producer parses the ts_et string).
ET = timezone(timedelta(hours=-4))

# Synthetic arms -- the CONSUMER contract, independent of the live roster.
# loose bold arm: min_triggers=1, no direction lock, no elite requirement -> takes a bare A+.
LOOSE_BOLD = {"id": "risky-3", "gate_override": {"min_triggers": 1}, "starting_equity": 2000.0}
# tight bold arm: min_triggers=2 + require ELITE -> only an elite A+ gets through.
TIGHT_BOLD = {"id": "risky-1",
              "gate_override": {"min_triggers": 2, "require_confluence_or_sequence": True},
              "starting_equity": 2000.0}
# safe arm: reads signal['safe'] (production-faithful), NOT signal['bold'].
SAFE_ARM = {"id": "safe-1", "gate_override": {"min_triggers": 1}, "starting_equity": 2000.0}


def _seed_two_rows(tmp_path, monkeypatch, *, today, bold_bull_score, bold_triggers,
                   safe_verdict="HOLD", bold_verdict="HOLD", ts="11:00:00"):
    """Write a 2-row core-decisions.jsonl (safe + bold) and point the producer at it.

    Mirrors test_fleet_producer_keystone._seed_two_rows: the SAFE row drives the
    production-faithful top-level + signal['safe']; the BOLD row drives signal['bold'].
    Both fresh + non-blind so build() reaches the dual-perception path."""
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


def _build(tmp_path, monkeypatch, *, scoring_peak, bold_bull_score=10,
           bold_triggers=("level_reclaim",)):
    now = datetime(2026, 6, 26, 11, 2, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    _seed_two_rows(tmp_path, monkeypatch, today=today,
                   bold_bull_score=bold_bull_score, bold_triggers=list(bold_triggers))
    return bss.build(now=now, scoring_peak=scoring_peak, emit_strategies=False, run_vwap=False)


# =============================================================================
# The producer->consumer link, end to end.
# =============================================================================
def test_keystone_signal_drives_loose_arm_to_enter(tmp_path, monkeypatch):
    """THE CONSUMER KEYSTONE: a gated A+ (production HELD) emits signal['bold'].bull.passed
    -> the REAL fleet_executor.plan_entry for a LOOSE bold arm turns it into an ENTER 'C'.
    This is the link that makes the bold fleet actually trade the gated A+ -- the half the
    producer test does not exercise."""
    sig = _build(tmp_path, monkeypatch, scoring_peak=True)
    assert sig["bold"]["bull"]["passed"] is True  # producer half (re-pinned for context)

    params = fx._params_for(LOOSE_BOLD)
    plan = fx.plan_entry(LOOSE_BOLD, sig, equity=2000.0, params=params)
    assert plan.action == "ENTER", f"loose arm must ENTER the keystone signal, got {plan.reason}"
    assert plan.side == "C"
    assert plan.qty == 8, "bold [2000,10000) base tier qty"  # consumer sized off the real tiers
    assert plan.quality == "BASE"


def test_keystone_signal_tight_arm_still_holds(tmp_path, monkeypatch):
    """The keystone makes the fleet LOOSER, not indiscriminate: a TIGHT arm
    (require_confluence_or_sequence) on a NON-elite A+ (two plain entry-triggers, no
    confluence/sequence) still HOLDs -- the consumer's selectivity gate bites on the
    keystone signal exactly as designed."""
    sig = _build(tmp_path, monkeypatch, scoring_peak=True,
                 bold_triggers=("level_reclaim", "level_rejection"))
    assert sig["bold"]["bull"]["passed"] is True
    assert sig["bold"]["bull"]["confluence"] is False  # not elite

    params = fx._params_for(TIGHT_BOLD)
    plan = fx.plan_entry(TIGHT_BOLD, sig, equity=2000.0, params=params)
    assert plan.action == "HOLD"
    assert "confluence" in plan.reason.lower() or "elite" in plan.reason.lower()


def test_elite_keystone_signal_drives_tight_arm_to_enter(tmp_path, monkeypatch):
    """Completeness for the pair above: when the keystone signal IS elite (a confluence
    trigger fired) the SAME tight arm ENTERs -- proving the HOLD above is genuine selectivity,
    not a broken producer->consumer chain. Pins that the elite flag flows producer->consumer."""
    sig = _build(tmp_path, monkeypatch, scoring_peak=True,
                 bold_triggers=("multi_day_confluence", "level_reclaim"))
    assert sig["bold"]["bull"]["passed"] is True
    assert sig["bold"]["bull"]["confluence"] is True  # producer set the ELITE flag

    params = fx._params_for(TIGHT_BOLD)
    plan = fx.plan_entry(TIGHT_BOLD, sig, equity=2000.0, params=params)
    assert plan.action == "ENTER", f"elite A+ must clear the tight gate, got {plan.reason}"
    assert plan.side == "C"
    assert plan.quality == "ELITE"


def test_safe_arm_reads_safe_perception_not_bold(tmp_path, monkeypatch):
    """Perception-source confound fix, proven at the CONSUMER: a SAFE arm on the dual-perception
    signal reads signal['safe'] (production-faithful HOLD) and HOLDs -- it does NOT pick up the
    looser signal['bold'] pass. A regression that routed a safe arm to the bold block would make
    it ENTER here."""
    sig = _build(tmp_path, monkeypatch, scoring_peak=True)
    assert sig["bold"]["bull"]["passed"] is True   # bold DID pass
    assert sig["safe"]["bull"]["passed"] is False  # safe stays production-faithful

    params = fx._params_for(SAFE_ARM)
    plan = fx.plan_entry(SAFE_ARM, sig, equity=2000.0, params=params)
    assert plan.action == "HOLD", "safe arm must read its production-faithful perception"
    assert "no qualifying setup" in plan.reason.lower()


def test_scoring_peak_off_loose_arm_inert_BITE(tmp_path, monkeypatch):
    """BITE (non-vacuous): with scoring_peak=False the producer emits NO 'bold' block, so the
    loose arm's _perception_for_arm falls back to the production-faithful top-level (HOLD) ->
    plan_entry HOLDs. Proves this guard genuinely catches the SCORING_PEAK_LIVE=False revert
    AT THE CONSUMER (the fleet goes inert), not just at the producer."""
    sig = _build(tmp_path, monkeypatch, scoring_peak=False)
    assert "bold" not in sig

    params = fx._params_for(LOOSE_BOLD)
    plan = fx.plan_entry(LOOSE_BOLD, sig, equity=2000.0, params=params)
    assert plan.action == "HOLD", "flag off -> loose arm gets no bold pass -> INERT"
    assert "no qualifying setup" in plan.reason.lower()

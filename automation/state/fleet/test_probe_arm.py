"""PROBE ARM (2026-07-10 ship, amended TWICE same-session) -- guards for the champion/
challenger cohort-block-bypass arm.

J directive 2026-07-10: "6 arms and nothing took a trade... why isn't 1 arm set to take
riskier trades? we have 3 risky and 3 bold." Diagnosis: every fleet arm's gate_override only
ADDS selectivity on top of an already passed=True shared-signal tick -- it can never rescue a
passed=False tick, however loose. The cohort/tier gates baked into build_shared_signal.py's
passed-derivation (mirroring heartbeat_core.py's GATE_KEYS) therefore apply UNIFORMLY to
every arm. Fix: risky-3 (accounts.json top-level "probe_arm") trades ONE specific, gate-
provenance-reviewed blocked cohort at min_contracts + a nearer strike, via signal['probe']
(build_shared_signal._probe_passed_blocks).

AMENDMENT 1 (automation/state/participation-cascade.json evidence): min_entry_premium --
NOT the cohort gates -- is the real #1 blocker (18 of 31 arm-events on 07-10 alone) because
the fleet's far-OTM/bold sizing tiers price their natural 0DTE contracts under the $0.30
floor. The floor stays FULLY INTACT (never bypassed); PROBE_STRIKE_TIERS gives probe's own
contracts a nearer (ATM-class) strike so they clear it on their own merits.

AMENDMENT 2 (markdown/audits/GATE-PROVENANCE-SWEEP-2026-07-10.md, commit 54d5840): a
rigorous, pre-registered, hash-pinned, 19/19-test-covered per-gate audit landed and
NARROWED the bypass to an explicit allowlist:
  - block_elite_bull: KEEP (SS-B revalidation: n=28, -$560.00 -> -$3,873.60, ~6.9x WORSE
    under the SAME exit shape probe's own ribbon_ride entries use). NOT bypassed.
  - SKIP_BULL_1100_1200: REVALIDATE (thin n=11 IS/n=1 OOS, pre-SS-B, first genuinely-live
    SUPER-tier block since ratification). Bypassed -- the ONLY bypassed verdict.
  - block_bull_ribbon_flip: independently reconfirmed (3rd audit) ABSENT/unarmed. No
    bypass built for it (never was -- this build's own generic trigger-name check never
    hardcoded this gate name).
PROBE_ALLOWED_VERDICTS = {"SKIP_BULL_1100_1200"} exactly. Everything else -- including
block_elite_bull's SKIP_ELITE_* verdicts -- is explicitly NOT bypassed.

Four layers, mirroring test_fix2_strategies_emit.py's A/B split:
  A. build_shared_signal: passed_probe_cohort / _probe_passed_blocks (the producer).
  B. fleet_executor: _is_probe_active / _cohort_tag / _probe_plan / plan_all wiring (consumer).
  C. fleet_live: the persisted daily-cap counter + decide_arm end-to-end (kill-switch,
     premium floor, and every other existing rail still binds on a probe-sourced plan).
  D. Strike override: PROBE_STRIKE_TIERS produces a nearer strike than the arm's own bold/
     OTM table, and (amendment 1's named acceptance fixture) a far-OTM contract that
     floor-skips at its natural premium while the SAME tick's probe (nearer-strike) contract
     clears the floor and enters.

Runs under pytest OR standalone (`python test_probe_arm.py`), mirroring
test_recency_min_sizing.py / test_fix2_strategies_emit.py's shims.
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import build_shared_signal as bss
import fleet_executor as fx
import fleet_live as fl

ET = timezone(timedelta(hours=-4))

SIZING = [{"equity_min": 0, "equity_max": 1e9, "base_qty": 8, "elite_qty": 12}]
PARAMS = {"position_sizing_tiers": SIZING, "min_contracts": 3}

# The 4 real fleet_rest arms (accounts.json shapes, trimmed to what plan_all reads).
SAFE_1 = {"id": "safe-1", "gate_override": {"min_triggers": 1}}
SAFE_3 = {"id": "safe-3", "gate_override": {"min_triggers": 2, "require_confluence_or_sequence": True}}
RISKY_1 = {"id": "risky-1", "gate_override": {"min_triggers": 2, "require_confluence_or_sequence": True}}
RISKY_3 = {"id": "risky-3", "gate_override": {"min_triggers": 1}}
ALL_FLEET_ARMS = [SAFE_1, SAFE_3, RISKY_1, RISKY_3]

PROBE_CFG = {"enabled": True, "arm_id": "risky-3", "daily_cap": 3}
PROBE_CFG_OFF = {"enabled": False, "arm_id": "risky-3", "daily_cap": 3}

# THE bypassable fixture: the real 11:21-11:23 ET 07-10 evidence (core-decisions.jsonl,
# account=safe) -- SKIP_BULL_1100_1200, SUPER tier (level_reclaim+ribbon_flip+confluence,
# bull_score=11 the ceiling), spot=752.67. Gate-provenance-sweep verdict: REVALIDATE.
WINDOW_BLOCKED_SIGNAL = {
    "spot": 752.67,
    "bull": {"passed": False, "score": 11, "triggers_fired": [], "setup_name": None},
    "bear": {"passed": False, "score": 4, "triggers_fired": [], "setup_name": None},
    "strategies": [],  # scoring-peak ALSO missed this tick (bold independently hit the floor)
    "probe": {
        "bull": {"passed": True, "score": 11,
                 "triggers_fired": ["level_reclaim", "ribbon_flip", "confluence"],
                 "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
                 "blocked_verdict": "SKIP_BULL_1100_1200", "trigger_level_exact": 752.49},
        "bear": {"passed": False, "score": 4, "triggers_fired": [], "setup_name": None,
                 "blocked_verdict": None, "trigger_level_exact": None},
    },
}

# THE non-bypassable fixture: the real 11:51-11:55 ET 07-10 evidence -- SKIP_ELITE_BULL_
# LEVEL_RECLAIM (BOTH safe AND bold got this verdict; block_elite_bull's VIX band covered
# both accounts that tick). triggers=['level_reclaim','confluence'] -- the ELITE tier (no
# ribbon_flip). Gate-provenance-sweep verdict: KEEP (freshly re-proven ~6.9x worse under
# SS-B, n=28). An ELITE signal must stay blocked for EVERY arm including the probe.
ELITE_BLOCKED_SIGNAL = {
    "spot": 752.43,
    "bull": {"passed": False, "score": 11, "triggers_fired": [], "setup_name": None},
    "bear": {"passed": False, "score": 4, "triggers_fired": [], "setup_name": None},
    "strategies": [],
    "probe": {
        "bull": {"passed": False, "score": 11, "triggers_fired": [], "setup_name": None,
                 "blocked_verdict": None, "trigger_level_exact": None},
        "bear": {"passed": False, "score": 4, "triggers_fired": [], "setup_name": None,
                 "blocked_verdict": None, "trigger_level_exact": None},
    },
}


# === A. build_shared_signal: passed_probe_cohort / _probe_passed_blocks (producer) ==========
def test_probe_cohort_bypasses_only_bull_1100_1200():
    """The ONLY bypassable verdict (gate-provenance-sweep: REVALIDATE)."""
    assert bss.passed_probe_cohort("SKIP_BULL_1100_1200", "ribbon_flip", True) is True
    assert bss.passed_probe_cohort("SKIP_BULL_1100_1200", "level_reclaim", True) is True


def test_probe_cohort_does_not_bypass_block_elite_bull():
    """block_elite_bull's SS-B revalidation (SAME session): KEEP, ~6.9x worse under the
    exit shape probe's own ribbon_ride entries use (n=28, -$560 -> -$3,873.60). NEVER
    bypassed, regardless of how real the trigger is."""
    assert bss.passed_probe_cohort("SKIP_ELITE_BULL_LEVEL_RECLAIM", "level_reclaim", True) is False
    assert bss.passed_probe_cohort("SKIP_ELITE_BEAR_LEVEL_REJECTION", "level_rejection", True) is False


def test_probe_cohort_does_not_bypass_other_cohort_gates():
    """Only SKIP_BULL_1100_1200 is on the allowlist -- every other cohort/tier verdict,
    including ones that LOOK like plausible time-of-day bypass candidates, is excluded
    (SKIP_CONF_LVL_REC_AFTERNOON was independently proven a stale-bar-echo artifact by the
    gate-provenance sweep, not a live signal at all -- doubly wrong to bypass)."""
    assert bss.passed_probe_cohort("SKIP_CONF_LVL_REC_AFTERNOON", "confluence", True) is False
    assert bss.passed_probe_cohort("SKIP_LEVEL_REJECTION", "level_rejection", True) is False
    assert bss.passed_probe_cohort("SKIP_BULL_MORNING_AGG", "confluence", True) is False


def test_probe_cohort_respects_stale_trigger_time_gate():
    """SKIP_STALE_TRIGGER (the 07-10 09:31-09:35 evidence: an overnight trigger
    re-evaluated as stale) is a genuine time-gate -- not on the allowlist, never bypassed."""
    assert bss.passed_probe_cohort("SKIP_STALE_TRIGGER", "level_reclaim", True) is False


def test_probe_cohort_respects_early_and_late_entry():
    assert bss.passed_probe_cohort("SKIP_EARLY_ENTRY", "level_reclaim", True) is False
    assert bss.passed_probe_cohort("SKIP_LATE_ENTRY", "level_reclaim", True) is False


def test_probe_cohort_respects_structure_veto_and_data_integrity():
    assert bss.passed_probe_cohort("SKIP_STRUCTURE_VETO", "ribbon_flip", True) is False
    assert bss.passed_probe_cohort("SKIP_TICK_ENTRY_TAKEN", "level_reclaim", True) is False
    assert bss.passed_probe_cohort("SKIP_BAD_INPUT", "level_reclaim", True) is False
    assert bss.passed_probe_cohort("SKIP_NO_DATA", "level_reclaim", True) is False


def test_probe_cohort_hold_or_no_trigger_never_passes():
    assert bss.passed_probe_cohort("HOLD", None, False) is False
    assert bss.passed_probe_cohort(None, None, False) is False
    assert bss.passed_probe_cohort("SKIP_BULL_1100_1200", "not_a_real_trigger", True) is False
    assert bss.passed_probe_cohort("SKIP_BULL_1100_1200", "level_reclaim", False) is False


def _seed_core(tmp_path, monkeypatch, *, account, verdict, action, setup, side, triggers,
               today, bull_score=11, bear_score=4, ts="11:21:03"):
    core = tmp_path / "core-decisions.jsonl"
    row = {"ts_et": f"{today}T{ts}-04:00", "account": account, "spy": 752.67,
           "ribbon": "BULL", "spread_cents": 37.3, "vix": 15.83, "htf_15m": "BULL",
           "verdict": verdict, "side": side, "setup": setup,
           "bear_score": bear_score, "bull_score": bull_score, "triggers": triggers,
           "action": action}
    core.write_text(json.dumps(row) + "\n", encoding="utf-8")
    monkeypatch.setattr(bss, "CORE_DECISIONS", core)
    monkeypatch.setattr(bss, "OUT", tmp_path / "shared-signal.json")
    monkeypatch.setattr(bss, "BEACON", tmp_path / "no-beacon.json")


def test_probe_passed_blocks_tags_the_bull_side_with_blocked_verdict(tmp_path, monkeypatch):
    now = datetime(2026, 7, 10, 11, 21, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    _seed_core(tmp_path, monkeypatch, account="bold", verdict="SKIP_BULL_1100_1200",
              action="SKIP_BULL_1100_1200", setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
              side="C", triggers=["level_reclaim", "ribbon_flip", "confluence"], today=today)
    blocks = bss._probe_passed_blocks(today, now)
    assert blocks["bull"]["passed"] is True
    assert blocks["bull"]["blocked_verdict"] == "SKIP_BULL_1100_1200"
    assert blocks["bull"]["setup_name"] == "BULLISH_RECLAIM_RIDE_THE_RIBBON"
    # bear must NOT leak True from the same row (side discrimination via row['side']=='C').
    assert blocks["bear"]["passed"] is False
    assert blocks["bear"]["blocked_verdict"] is None


def test_probe_passed_blocks_elite_verdict_never_passes(tmp_path, monkeypatch):
    """block_elite_bull's verdict on the BOLD ledger -- KEEP, must never surface as passed."""
    now = datetime(2026, 7, 10, 11, 51, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    _seed_core(tmp_path, monkeypatch, account="bold", verdict="SKIP_ELITE_BULL_LEVEL_RECLAIM",
              action="SKIP_ELITE_BULL_LEVEL_RECLAIM", setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
              side="C", triggers=["level_reclaim", "confluence"], today=today, ts="11:51:04")
    blocks = bss._probe_passed_blocks(today, now)
    assert blocks["bull"]["passed"] is False
    assert blocks["bull"]["blocked_verdict"] is None


def test_probe_passed_blocks_side_discrimination_bear(tmp_path, monkeypatch):
    now = datetime(2026, 7, 10, 11, 21, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    # SKIP_BULL_1100_1200 is bull-only in production, but the pure function only cares about
    # the allowlist + row['side'] -- prove bear-side discrimination generically.
    _seed_core(tmp_path, monkeypatch, account="bold", verdict="SKIP_BULL_1100_1200",
              action="SKIP_BULL_1100_1200", setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
              side="P", triggers=["level_reclaim", "ribbon_flip", "confluence"], today=today,
              bull_score=3, bear_score=9)
    blocks = bss._probe_passed_blocks(today, now)
    assert blocks["bear"]["passed"] is True
    assert blocks["bull"]["passed"] is False


def test_probe_passed_blocks_stale_trigger_never_passes(tmp_path, monkeypatch):
    """Mirrors the LITERAL 07-10 09:31-09:35 evidence row: verdict says ENTER_BULL (tier
    SUPER) but action is SKIP_STALE_TRIGGER -- must stay blocked (not on the allowlist,
    and _map_core_row collapses it to a bare "HOLD" which is never in the allowlist either)."""
    now = datetime(2026, 7, 10, 9, 31, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    _seed_core(tmp_path, monkeypatch, account="bold", verdict="ENTER_BULL",
              action="SKIP_STALE_TRIGGER", setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
              side="C", triggers=["level_reclaim", "ribbon_flip", "confluence"], today=today,
              ts="09:31:04")
    blocks = bss._probe_passed_blocks(today, now)
    assert blocks["bull"]["passed"] is False
    assert blocks["bear"]["passed"] is False


def test_probe_passed_blocks_no_row_is_empty(tmp_path, monkeypatch):
    now = datetime(2026, 7, 10, 11, 21, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    monkeypatch.setattr(bss, "CORE_DECISIONS", tmp_path / "does-not-exist.jsonl")
    blocks = bss._probe_passed_blocks(today, now)
    assert blocks["bull"]["passed"] is False and blocks["bear"]["passed"] is False


def _seed_core_both(tmp_path, monkeypatch, today, *, safe_verdict, safe_action,
                    bold_verdict, bold_action, setup, side, triggers,
                    bull_score=11, bear_score=4, ts_h_m="11:21"):
    """Seed BOTH safe+bold rows for the SAME tick (production always writes them paired,
    one heartbeat_core call per account -- see the real core-decisions.jsonl evidence: every
    ts_et has a 'safe' row immediately followed by a 'bold' row). build()'s main body (where
    do_probe's _probe_passed_blocks -- BOLD-sourced, same as _bold_passed_blocks -- actually
    runs) is only reached when the TOP-LEVEL safe-sourced row resolves, so a probe test needs
    a safe row present even when only the bold row's verdict is under test."""
    core = tmp_path / "core-decisions.jsonl"
    rows = [
        {"ts_et": f"{today}T{ts_h_m}:03-04:00", "account": "safe", "spy": 752.67,
         "ribbon": "BULL", "spread_cents": 37.3, "vix": 15.83, "htf_15m": "BULL",
         "verdict": safe_verdict, "side": side, "setup": setup,
         "bear_score": bear_score, "bull_score": bull_score, "triggers": triggers,
         "action": safe_action},
        {"ts_et": f"{today}T{ts_h_m}:05-04:00", "account": "bold", "spy": 752.67,
         "ribbon": "BULL", "spread_cents": 37.3, "vix": 15.83, "htf_15m": "BULL",
         "verdict": bold_verdict, "side": side, "setup": setup,
         "bear_score": bear_score, "bull_score": bull_score, "triggers": triggers,
         "action": bold_action},
    ]
    core.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(bss, "CORE_DECISIONS", core)
    monkeypatch.setattr(bss, "OUT", tmp_path / "shared-signal.json")
    monkeypatch.setattr(bss, "BEACON", tmp_path / "no-beacon.json")


def test_build_emits_probe_block_end_to_end(tmp_path, monkeypatch):
    """build(probe_cohort=True) on a tick where SAFE got SKIP_BULL_1100_1200 (the real 07-10
    11:21 shape -- Safe-only gate) ALSO carries signal['probe'] (BOLD-sourced, same ledger
    _bold_passed_blocks already uses) with the bypass, even though the top-level/production-
    mirror block (SAFE-sourced) stays passed=False."""
    now = datetime(2026, 7, 10, 11, 21, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    _seed_core_both(tmp_path, monkeypatch, today,
                    safe_verdict="SKIP_BULL_1100_1200", safe_action="SKIP_BULL_1100_1200",
                    bold_verdict="SKIP_BULL_1100_1200", bold_action="SKIP_BULL_1100_1200",
                    setup="BULLISH_RECLAIM_RIDE_THE_RIBBON", side="C",
                    triggers=["level_reclaim", "ribbon_flip", "confluence"])
    sig = bss.build(now=now, emit_strategies=False, run_vwap=False, probe_cohort=True)
    assert sig["bull"]["passed"] is False  # production-mirror stays honest (SAFE also blocked)
    assert sig["probe"]["bull"]["passed"] is True
    assert sig["probe"]["bull"]["blocked_verdict"] == "SKIP_BULL_1100_1200"


def test_build_emits_no_pass_for_elite_blocked_tick(tmp_path, monkeypatch):
    """The SAME build() plumbing on an ELITE-blocked tick (both accounts) emits probe.bull.
    passed=False -- the KEEP-verdicted gate never surfaces through this pipeline."""
    now = datetime(2026, 7, 10, 11, 51, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    _seed_core_both(tmp_path, monkeypatch, today,
                    safe_verdict="SKIP_ELITE_BULL_LEVEL_RECLAIM",
                    safe_action="SKIP_ELITE_BULL_LEVEL_RECLAIM",
                    bold_verdict="SKIP_ELITE_BULL_LEVEL_RECLAIM",
                    bold_action="SKIP_ELITE_BULL_LEVEL_RECLAIM",
                    setup="BULLISH_RECLAIM_RIDE_THE_RIBBON", side="C",
                    triggers=["level_reclaim", "confluence"], ts_h_m="11:51")
    sig = bss.build(now=now, emit_strategies=False, run_vwap=False, probe_cohort=True)
    assert sig["probe"]["bull"]["passed"] is False


def test_build_no_probe_key_when_disabled(tmp_path, monkeypatch):
    """probe_cohort=False (or PROBE_COHORT_LIVE=False) -> byte-identical revert, no 'probe' key."""
    now = datetime(2026, 7, 10, 11, 21, tzinfo=ET)
    today = now.strftime("%Y-%m-%d")
    _seed_core(tmp_path, monkeypatch, account="bold", verdict="SKIP_BULL_1100_1200",
              action="SKIP_BULL_1100_1200", setup="BULLISH_RECLAIM_RIDE_THE_RIBBON",
              side="C", triggers=["level_reclaim", "ribbon_flip", "confluence"], today=today)
    sig = bss.build(now=now, emit_strategies=False, run_vwap=False, probe_cohort=False)
    assert "probe" not in sig


def test_build_probe_empty_on_blind_beacon_fallback(tmp_path, monkeypatch):
    """The NEVER-BLIND beacon fallback path also emits a (harmless, empty) probe block when
    do_probe is set -- schema stays consistent across every build() branch."""
    now = datetime(2026, 7, 10, 11, 21, tzinfo=ET)
    monkeypatch.setattr(bss, "CORE_DECISIONS", Path(tempfile.mkdtemp()) / "missing.jsonl")
    monkeypatch.setattr(bss, "OUT", Path(tempfile.mkdtemp()) / "shared-signal.json")
    beacon_path = Path(tempfile.mkdtemp()) / "sight-beacon.json"
    beacon_path.write_text(json.dumps({"ok": True, "spy": 752.0, "ribbon_stack": "BULL",
                                       "spread_cents": 30.0, "ts_et": now.strftime("%Y-%m-%dT%H:%M:%S"),
                                       "data_source": "test"}), encoding="utf-8")
    monkeypatch.setattr(bss, "BEACON", beacon_path)
    sig = bss.build(now=now, emit_strategies=True, run_vwap=False, probe_cohort=True)
    assert sig["source"] == "derived-from-beacon-NEVER-BLIND"
    assert sig["probe"] == {"bull": dict(bss._PROBE_EMPTY), "bear": dict(bss._PROBE_EMPTY)}


# === B. fleet_executor: _is_probe_active / _cohort_tag / _probe_plan / plan_all =============
def test_is_probe_active_requires_enabled_and_matching_id():
    assert fx._is_probe_active(RISKY_3, PROBE_CFG) is True
    assert fx._is_probe_active(SAFE_1, PROBE_CFG) is False
    assert fx._is_probe_active(RISKY_3, PROBE_CFG_OFF) is False
    assert fx._is_probe_active(RISKY_3, None) is False
    assert fx._is_probe_active(RISKY_3, {}) is False


def test_cohort_tag_strips_skip_prefix_and_lowercases():
    assert fx._cohort_tag("SKIP_BULL_1100_1200") == "bull_1100_1200"
    assert fx._cohort_tag(None) == "unknown"
    assert fx._cohort_tag("") == "unknown"


def test_plan_all_flag_off_byte_identical_across_all_fleet_arms():
    """vary-and-assert: the SAME cohort-blocked signal through all 4 real fleet arms, with
    probe_cfg simply OMITTED (every existing call site) -- must equal the SAME call with
    probe_cfg explicitly disabled, AND equal calling plan_all with no probe kwargs at all
    (the pre-ship signature). Zero ENTER anywhere -- the whole point of the diagnosis."""
    for arm in ALL_FLEET_ARMS:
        omitted = fx.plan_all(arm, WINDOW_BLOCKED_SIGNAL, 2000.0, PARAMS)
        explicit_off = fx.plan_all(arm, WINDOW_BLOCKED_SIGNAL, 2000.0, PARAMS, probe_cfg=PROBE_CFG_OFF)
        assert omitted == explicit_off, arm["id"]
        assert not any(p.action == "ENTER" for p in omitted), arm["id"]


def test_plan_all_probe_fires_for_named_arm_only_others_byte_identical():
    """THE core proof: same tick, probe_cfg ON, across all 4 arms. Only risky-3 gets a
    cohort-bypass ENTER; the other 3 are BYTE-IDENTICAL to the flag-off baseline (their
    OWN gate_override still sees passed=False top-level/strategies=[] and correctly HOLDs --
    this mechanism does not loosen anyone else's gate)."""
    baseline = {arm["id"]: fx.plan_all(arm, WINDOW_BLOCKED_SIGNAL, 2000.0, PARAMS) for arm in ALL_FLEET_ARMS}
    with_probe = {arm["id"]: fx.plan_all(arm, WINDOW_BLOCKED_SIGNAL, 2000.0, PARAMS, probe_cfg=PROBE_CFG)
                  for arm in ALL_FLEET_ARMS}
    for arm_id in ("safe-1", "safe-3", "risky-1"):
        assert with_probe[arm_id] == baseline[arm_id], f"{arm_id} must be untouched by the probe flag"
    risky3_plans = with_probe["risky-3"]
    enters = [p for p in risky3_plans if p.action == "ENTER"]
    assert len(enters) == 1
    p = enters[0]
    assert p.side == "C" and p.strategy == "ribbon_ride"
    assert p.reason == "PROBE_ARM cohort=bull_1100_1200"


def test_plan_all_probe_never_fires_on_elite_blocked_signal_for_any_arm():
    """AMENDMENT 2's explicit acceptance requirement: 'an ELITE signal must still be blocked
    for ALL arms including the probe.' block_elite_bull is KEEP-verdicted -- not on the
    allowlist -- so signal['probe'] itself never carries passed=True for it (see section A),
    and even if it somehow did, PROBE_ALLOWED_VERDICTS would still refuse it here too
    (defense in depth: this test exercises the consumer path directly)."""
    for arm in ALL_FLEET_ARMS:
        plans = fx.plan_all(arm, ELITE_BLOCKED_SIGNAL, 2000.0, PARAMS, probe_cfg=PROBE_CFG)
        assert not any(p.action == "ENTER" for p in plans), arm["id"]


def test_plan_all_probe_min_size_clamp_ignores_sizing_tiers():
    """qty is HARD-CLAMPED to min_contracts regardless of what the account's own sizing
    tiers/elite_qty would otherwise assign (SIZING gives elite_qty=12 here)."""
    params = {**PARAMS, "min_contracts": 3}
    plans = fx.plan_all(RISKY_3, WINDOW_BLOCKED_SIGNAL, 2000.0, params, probe_cfg=PROBE_CFG)
    enter = next(p for p in plans if p.action == "ENTER")
    assert enter.qty == 3

    params5 = {**PARAMS, "min_contracts": 5}  # e.g. bold-side min_contracts
    plans5 = fx.plan_all(RISKY_3, WINDOW_BLOCKED_SIGNAL, 2000.0, params5, probe_cfg=PROBE_CFG)
    enter5 = next(p for p in plans5 if p.action == "ENTER")
    assert enter5.qty == 5  # tracks min_contracts, never the 8/12 sizing tier


def test_plan_all_probe_daily_cap_enforced():
    plans_ok = fx.plan_all(RISKY_3, WINDOW_BLOCKED_SIGNAL, 2000.0, PARAMS,
                           probe_cfg=PROBE_CFG, probe_entries_today=2)
    assert any(p.action == "ENTER" for p in plans_ok)

    plans_capped = fx.plan_all(RISKY_3, WINDOW_BLOCKED_SIGNAL, 2000.0, PARAMS,
                               probe_cfg=PROBE_CFG, probe_entries_today=3)
    assert not any(p.action == "ENTER" for p in plans_capped)
    assert any("daily cap reached" in p.reason for p in plans_capped)
    assert any("PROBE_ARM cohort=bull_1100_1200" in p.reason for p in plans_capped)


def test_plan_all_probe_scope_ribbon_ride_only():
    """A non-ribbon setup_name in the probe block (e.g. a VWAP-family name) is never probed
    -- vwap_continuation is a live REST detector with no core-gate cohort to bypass."""
    sig = {**WINDOW_BLOCKED_SIGNAL, "probe": {
        "bull": {"passed": True, "score": 11, "triggers_fired": ["level_reclaim"],
                 "setup_name": "VWAP_CONTINUATION", "blocked_verdict": "SKIP_BULL_1100_1200",
                 "trigger_level_exact": None},
        "bear": {"passed": False, "score": 0, "triggers_fired": [], "setup_name": None,
                 "blocked_verdict": None, "trigger_level_exact": None},
    }}
    plans = fx.plan_all(RISKY_3, sig, 2000.0, PARAMS, probe_cfg=PROBE_CFG)
    assert not any(p.action == "ENTER" for p in plans)


def test_plan_all_probe_does_not_double_fire_when_normal_path_enters():
    sig = dict(WINDOW_BLOCKED_SIGNAL)
    sig["strategies"] = [{"name": "ribbon_ride", "side": "C",
                          "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
                          "triggers": ["level_reclaim", "ribbon_flip", "confluence"],
                          "quality": "ELITE", "est_premium": None, "spot": 752.67}]
    plans = fx.plan_all(RISKY_3, sig, 2000.0, PARAMS, probe_cfg=PROBE_CFG)
    enters = [p for p in plans if p.action == "ENTER"]
    assert len(enters) == 1
    assert not enters[0].reason.startswith("PROBE_ARM")  # the NORMAL entry, not a probe one


def test_plan_all_probe_no_signal_probe_key_is_a_noop():
    sig = {"spot": 600.0, "strategies": []}  # no 'probe' key at all (flag-off producer)
    plans = fx.plan_all(RISKY_3, sig, 2000.0, PARAMS, probe_cfg=PROBE_CFG)
    assert plans == []


def test_07_10_fixture_flag_off_none_flag_on_risky3_only():
    """THE named acceptance test: the 07-10 SKIP_BULL_1100_1200 fixture produces a probe
    entry plan where flag-off (probe_cfg absent) produces none, ONLY on risky-3."""
    for arm in ALL_FLEET_ARMS:
        before = fx.plan_all(arm, WINDOW_BLOCKED_SIGNAL, 2000.0, PARAMS)
        assert not any(p.action == "ENTER" for p in before), f"{arm['id']} pre-ship must be all-HOLD"

    after_other_3 = [fx.plan_all(a, WINDOW_BLOCKED_SIGNAL, 2000.0, PARAMS, probe_cfg=PROBE_CFG)
                     for a in (SAFE_1, SAFE_3, RISKY_1)]
    assert not any(p.action == "ENTER" for plans in after_other_3 for p in plans)

    after_probe = fx.plan_all(RISKY_3, WINDOW_BLOCKED_SIGNAL, 2000.0, PARAMS, probe_cfg=PROBE_CFG)
    assert any(p.action == "ENTER" for p in after_probe)


# === C. fleet_live: persisted daily-cap counter + decide_arm end-to-end rails ================
def test_load_probe_count_fresh_persist_and_reset_next_session(tmp_path, monkeypatch):
    monkeypatch.setattr(fl, "FLEET_DIR", tmp_path)
    now1 = datetime(2026, 7, 10, 11, 21, tzinfo=ET)
    assert fl._load_probe_count("risky-3", now1) == {"date": "2026-07-10", "count": 0}
    fl._record_probe_entry("risky-3", now1)
    fl._record_probe_entry("risky-3", now1)
    c = fl._load_probe_count("risky-3", now1)
    assert c["count"] == 2

    now2 = datetime(2026, 7, 13, 9, 31, tzinfo=ET)  # next session (Monday)
    assert fl._load_probe_count("risky-3", now2) == {"date": "2026-07-13", "count": 0}


REAL_PARAMS = {"position_sizing_tiers": SIZING, "min_contracts": 3,
               "per_trade_risk_cap_pct": 0.5, "daily_loss_kill_switch_pct": 0.5,
               "min_entry_premium": 0.3}
RISKY_3_FULL = {"id": "risky-3", "gate_override": {"min_triggers": 1},
                "account_number": "PA31WIU8X15Q"}


def test_decide_arm_probe_entry_allowed_end_to_end():
    decision, exit_shape = fl.decide_arm(
        RISKY_3_FULL, WINDOW_BLOCKED_SIGNAL, equity=2000.0, flat=True, day_trades=0,
        killed=False, sod_equity=2000.0, prior_stops=[], params=REAL_PARAMS,
        premium_override=0.35, probe_cfg=PROBE_CFG, probe_entries_today=0,
    )
    assert decision.action == "ENTER_BULL"
    assert decision.qty == 3
    assert decision.risk_code == "ALLOW"
    assert decision.reason == "PROBE_ARM cohort=bull_1100_1200"
    assert exit_shape["stop_mode"] == "structure"  # SS-B exit shape UNCHANGED


def test_decide_arm_probe_never_allows_on_elite_blocked_signal():
    decision, _ = fl.decide_arm(
        RISKY_3_FULL, ELITE_BLOCKED_SIGNAL, equity=2000.0, flat=True, day_trades=0,
        killed=False, sod_equity=2000.0, prior_stops=[], params=REAL_PARAMS,
        premium_override=0.35, probe_cfg=PROBE_CFG, probe_entries_today=0,
    )
    assert decision.action == "HOLD"


def test_decide_arm_probe_still_respects_premium_floor():
    decision, _ = fl.decide_arm(
        RISKY_3_FULL, WINDOW_BLOCKED_SIGNAL, equity=2000.0, flat=True, day_trades=0,
        killed=False, sod_equity=2000.0, prior_stops=[], params=REAL_PARAMS,
        premium_override=0.11, probe_cfg=PROBE_CFG, probe_entries_today=0,
    )
    assert decision.action == "HOLD"
    assert decision.risk_code == "SKIP_MIN_PREMIUM_FLOOR"


def test_decide_arm_probe_still_respects_kill_switch():
    decision, _ = fl.decide_arm(
        RISKY_3_FULL, WINDOW_BLOCKED_SIGNAL, equity=2000.0, flat=True, day_trades=0,
        killed=True, sod_equity=2000.0, prior_stops=[], params=REAL_PARAMS,
        premium_override=0.35, probe_cfg=PROBE_CFG, probe_entries_today=0,
    )
    assert decision.action == "HOLD"
    assert decision.risk_code == "KILL_SWITCH"


def test_decide_arm_probe_still_respects_not_flat_one_position():
    decision, _ = fl.decide_arm(
        RISKY_3_FULL, WINDOW_BLOCKED_SIGNAL, equity=2000.0, flat=False, day_trades=0,
        killed=False, sod_equity=2000.0, prior_stops=[], params=REAL_PARAMS,
        premium_override=0.35, probe_cfg=PROBE_CFG, probe_entries_today=0,
    )
    assert decision.action == "HOLD"
    assert decision.risk_code == "NOT_FLAT"


def test_decide_arm_probe_daily_cap_at_boundary():
    at_cap, _ = fl.decide_arm(
        RISKY_3_FULL, WINDOW_BLOCKED_SIGNAL, equity=2000.0, flat=True, day_trades=0,
        killed=False, sod_equity=2000.0, prior_stops=[], params=REAL_PARAMS,
        premium_override=0.35, probe_cfg=PROBE_CFG, probe_entries_today=3,
    )
    assert at_cap.action == "HOLD"
    under_cap, _ = fl.decide_arm(
        RISKY_3_FULL, WINDOW_BLOCKED_SIGNAL, equity=2000.0, flat=True, day_trades=0,
        killed=False, sod_equity=2000.0, prior_stops=[], params=REAL_PARAMS,
        premium_override=0.35, probe_cfg=PROBE_CFG, probe_entries_today=2,
    )
    assert under_cap.action == "ENTER_BULL"


def test_decide_arm_non_probe_arm_untouched_by_probe_cfg():
    """decide_arm for a NON-probe arm, with probe_cfg present and the SAME cohort-blocked
    signal, produces a plain HOLD (no PROBE_ARM plan synthesized) -- the flag is arm-scoped."""
    safe1 = {"id": "safe-1", "gate_override": {"min_triggers": 1}, "account_number": "PA3DHPT7KIQE"}
    decision, _ = fl.decide_arm(
        safe1, WINDOW_BLOCKED_SIGNAL, equity=2000.0, flat=True, day_trades=0,
        killed=False, sod_equity=2000.0, prior_stops=[], params=REAL_PARAMS,
        premium_override=0.35, probe_cfg=PROBE_CFG, probe_entries_today=0,
    )
    assert decision.action == "HOLD"


# === D. Strike override (amendment 1): probe prices NEARER than the arm's own bold/OTM table
def test_probe_strike_is_nearer_than_arms_own_bold_tier():
    """risky-3's OWN sizing table (bold/OTM, _tiers_for_arm) would pick a far-OTM strike;
    the probe plan's strike (PROBE_STRIKE_TIERS) is nearer to spot -- the exact mechanism the
    amendment asks for, verified as a strike DELTA, not just 'some strike got picked'."""
    plans = fx.plan_all(RISKY_3, WINDOW_BLOCKED_SIGNAL, 2000.0, PARAMS, probe_cfg=PROBE_CFG)
    probe_entry = next(p for p in plans if p.action == "ENTER")
    spot = WINDOW_BLOCKED_SIGNAL["spot"]
    atm = round(spot)
    normal_tiers = fx._tiers_for_arm(RISKY_3)  # risky-3 -> V15_BOLD_TIERS (far OTM)
    normal_strike = fx.strike_selection.pick_strike(spot, 2000.0, "C", normal_tiers)
    assert abs(probe_entry.strike - atm) < abs(normal_strike - atm), (
        "probe strike must be nearer to spot than the arm's own bold/OTM strike")
    assert probe_entry.strike == atm  # at $2K equity PROBE_STRIKE_TIERS resolves to exactly ATM
    assert normal_strike != atm       # sanity: the arm's own tier really is NOT atm (OTM-2)


def test_probe_strike_tiers_independent_of_v15_safe_tiers_object():
    """PROBE_STRIKE_TIERS is a STANDALONE table (values match V15_SAFE_TIERS today by
    coincidence of doctrine, not by reference) -- a future safe-arm-only tier retune must
    not silently also move probe's strike."""
    assert fx.PROBE_STRIKE_TIERS is not fx.strike_selection.V15_SAFE_TIERS
    assert fx.PROBE_STRIKE_TIERS == fx.strike_selection.V15_SAFE_TIERS  # same VALUES today


def test_amendment_fixture_far_otm_floor_skips_probe_nearer_strike_enters():
    """THE amendment's named acceptance fixture: the 07-10 SUPER signal at 11:2x blocked by
    SKIP_BULL_1100_1200 -- a NORMAL arm's far-OTM contract prices at $0.07 (correctly
    floor-skips, the floor itself untouched) while the SAME tick's probe (nearer
    PROBE_STRIKE_TIERS strike) contract realistically prices >= $0.30 and produces a real
    entry plan. premium_override simulates each plan's OWN broker-quoted mid for ITS OWN
    strike (exactly how fleet_live.py's premium-prefetch works live: it quotes whichever
    strike the SELECTED plan carries)."""
    # A normal (non-probe) arm evaluated on the exact same tick: strategies[]==[] (the
    # window gate blocked it upstream) -- so there IS no normal-arm ENTER plan here at all
    # (confirms "other arms correctly floor-skip" reads as "never even reach a premium
    # check, HOLD on the cohort block itself" -- the floor is the SEPARATE, additional
    # reason a scoring-peak-rescued tick would still die).
    other_arm_plans = fx.plan_all(SAFE_1, WINDOW_BLOCKED_SIGNAL, 2000.0, PARAMS)
    assert not any(p.action == "ENTER" for p in other_arm_plans)

    # Probe's plan for the SAME tick: verify its strike is the nearer one, then run it through
    # the REAL risk gate with a premium realistic for ATM (>= floor) vs what the arm's own far
    # -OTM strike would have realistically quoted (< floor) -- proving the floor stays a live,
    # binding gate for far-OTM pricing while the probe's OWN nearer contract clears it.
    FAR_OTM_PREMIUM = 0.07   # what the arm's own bold/OTM strike would realistically quote
    NEAR_ATM_PREMIUM = 0.35  # what probe's ATM-class strike would realistically quote

    denied, _ = fl.decide_arm(
        RISKY_3_FULL, WINDOW_BLOCKED_SIGNAL, equity=2000.0, flat=True, day_trades=0,
        killed=False, sod_equity=2000.0, prior_stops=[], params=REAL_PARAMS,
        premium_override=FAR_OTM_PREMIUM, probe_cfg=PROBE_CFG, probe_entries_today=0,
    )
    assert denied.action == "HOLD" and denied.risk_code == "SKIP_MIN_PREMIUM_FLOOR", (
        "the floor must still deny a far-OTM-priced probe contract -- it is NEVER bypassed")

    allowed, _ = fl.decide_arm(
        RISKY_3_FULL, WINDOW_BLOCKED_SIGNAL, equity=2000.0, flat=True, day_trades=0,
        killed=False, sod_equity=2000.0, prior_stops=[], params=REAL_PARAMS,
        premium_override=NEAR_ATM_PREMIUM, probe_cfg=PROBE_CFG, probe_entries_today=0,
    )
    assert allowed.action == "ENTER_BULL" and allowed.risk_code == "ALLOW"
    assert allowed.strike == round(WINDOW_BLOCKED_SIGNAL["spot"])  # the nearer, ATM-class strike
    assert allowed.qty == 3


def test_amendment2_fixture_elite_signal_blocked_for_every_arm_including_probe():
    """AMENDMENT 2's explicit acceptance requirement, verified end-to-end through decide_arm
    (not just plan_all): 'an ELITE signal must still be blocked for ALL arms including the
    probe.' Uses a generous premium (0.35, would clear the floor) to isolate that the BLOCK
    is the cohort gate itself, not a premium-floor coincidence."""
    for arm in ({"id": "safe-1", "gate_override": {"min_triggers": 1}},
                {"id": "safe-3", "gate_override": {"min_triggers": 2, "require_confluence_or_sequence": True}},
                {"id": "risky-1", "gate_override": {"min_triggers": 2, "require_confluence_or_sequence": True}},
                RISKY_3_FULL):
        decision, _ = fl.decide_arm(
            arm, ELITE_BLOCKED_SIGNAL, equity=2000.0, flat=True, day_trades=0,
            killed=False, sod_equity=2000.0, prior_stops=[], params=REAL_PARAMS,
            premium_override=0.35, probe_cfg=PROBE_CFG, probe_entries_today=0,
        )
        assert decision.action == "HOLD", arm["id"]


if __name__ == "__main__":
    class _MP:
        def __init__(self):
            self._undo = []

        def setattr(self, obj, name, val):
            self._undo.append((obj, name, getattr(obj, name)))
            setattr(obj, name, val)

        def undo(self):
            for obj, name, old in reversed(self._undo):
                setattr(obj, name, old)
            self._undo = []

    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = failed = 0
    for t in tests:
        mp = _MP()
        argn = t.__code__.co_varnames[: t.__code__.co_argcount]
        try:
            with tempfile.TemporaryDirectory() as td:
                kw = {}
                if "tmp_path" in argn:
                    kw["tmp_path"] = Path(td)
                if "monkeypatch" in argn:
                    kw["monkeypatch"] = mp
                t(**kw)
            print(f"PASS  {t.__name__}")
            passed += 1
        except Exception as e:  # noqa: BLE001
            print(f"FAIL  {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
        finally:
            mp.undo()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)

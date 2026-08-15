"""Guards for the directional-gate revalidation battery (2026-07-15, J's "review EVERYTHING"
directive). Pins FIVE things:

  1. prereg hash pin -- the frozen pre-registration cannot be silently edited after freezing
     without this test REDing (same pattern as test_block_elite_bull_ssb_revalidation.py).
  2. pure mining functions (dedupe, stale-echo, downstream-double-block predicates) -- pinned
     against synthetic fixtures so a future edit can't silently change what counts as "one
     signal" or "double-blocked by another armed gate" without a test noticing.
  3. WF computation's three branches (per-trade normalized, aggregate-only, N/A-structural) and
     the BH-FDR step-up -- non-vacuous (proves the FDR cut actually filters something, not just
     that it runs).
  4. current-shape derivation -- the replay shape built from strategies.RIBBON_RIDE.exit must
     carry premium_stop_pct=-0.50 (the catastrophe cap), NEVER RIBBON_RIDE's own -0.20 flag-off
     literal (see the module docstring for why a straight pass-through would silently corrupt
     every replayed trade's in-engine stop).
  5. golden finding (once committed): the battery's OWN verdict-vs-conditions logic is
     non-vacuous, AND -- since every tested gate verdicted KEEP this run -- both live params
     files still carry their PRE-battery armed values for the 6 tested gate keys (pins the "no
     change shipped" state so a future re-run that starts silently flipping keys gets noticed).

Fast + deterministic: no network calls, no full mining/replay re-run (that is exercised by
running the module's main() directly, not by this guard suite).
"""
import json
import os
import sys

import pytest

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "backtest"))
sys.path.insert(0, os.path.join(REPO, "backtest", "tools"))
sys.path.insert(0, os.path.join(REPO, "automation", "state", "fleet"))

import directional_gate_battery as m  # noqa: E402

PREREG = os.path.join(REPO, "analysis", "recommendations",
                      "prereg-directional-gate-battery-2026-07-15.json")
RESULT = os.path.join(REPO, "analysis", "recommendations",
                      "directional-gate-battery-2026-07-15.json")
PARAMS_SAFE = os.path.join(REPO, "automation", "state", "params.json")
PARAMS_BOLD = os.path.join(REPO, "automation", "state", "aggressive", "params.json")


# ---- 1. prereg hash pin ------------------------------------------------------

def test_prereg_file_exists_and_is_frozen():
    assert os.path.exists(PREREG)
    preg = json.load(open(PREREG, encoding="utf-8"))
    assert preg["status"] == "FROZEN_PENDING_RUN"
    assert preg["version"] == 1


def test_prereg_hash_matches_hardcoded_expectation():
    """The hash baked into the runner must match what's on disk right now. If the pre-reg
    (gate list, current-config, windows, ratification bar) is edited after freezing, this REDs
    -- it does not silently re-hash and move on."""
    pf, _preg = m.preflight()
    assert pf["prereg_hash_ok"] is True
    assert pf["prereg_sha256_16_recomputed"] == m.EXPECTED_PREREG_SHA16
    assert pf["prereg_sha256_16_stored"] == m.EXPECTED_PREREG_SHA16


def test_prereg_hash_bites_on_mutation():
    """Non-vacuous: prove the hash check actually detects a change. Mutate a copy's ratification
    bar and confirm the recomputed hash diverges from the frozen expectation."""
    preg = json.load(open(PREREG, encoding="utf-8"))
    mutated = dict(preg)
    mutated["ratification_gates"] = dict(mutated["ratification_gates"])
    mutated["ratification_gates"]["2_wf_ge_070"] = "MUTATED >= 0.10"
    mutated_no_hash = {k: v for k, v in mutated.items() if k != "content_sha256_16"}
    mutated_hash = m._content_hash(mutated_no_hash)
    assert mutated_hash != m.EXPECTED_PREREG_SHA16, \
        "hash check is vacuous -- a mutated preregistration must NOT hash-match the frozen spec"


# ---- 2. pure mining functions -------------------------------------------------

def _row(ts, **kw):
    base = {"ts_et": ts, "account": "safe", "action": "SKIP_ELITE_BULL_LEVEL_RECLAIM",
            "spy": 750.0, "vix": 16.0, "triggers": ["level_reclaim", "confluence"],
            "trigger_level_exact": None}
    base.update(kw)
    return base


def test_dedupe_merges_within_gap_and_splits_beyond():
    rows = [_row("2026-07-09T09:41:00"), _row("2026-07-09T09:42:00"), _row("2026-07-09T09:45:00")]
    events = m.dedupe_into_events(rows, gap_minutes=5)
    assert len(events) == 1 and events[0]["n_ticks"] == 3

    rows2 = [_row("2026-07-09T09:41:00"), _row("2026-07-09T09:47:00")]  # 6 min > 5
    assert len(m.dedupe_into_events(rows2, gap_minutes=5)) == 2


def test_dedupe_empty_and_single():
    assert m.dedupe_into_events([]) == []
    single = m.dedupe_into_events([_row("2026-07-09T09:41:00")])
    assert len(single) == 1 and single[0]["n_ticks"] == 1


def test_stale_echo_cross_account_detection():
    entry = _row("2026-07-10T09:31:04", account="bold")
    corroborated = [{"ts_et": "2026-07-10T09:31:03", "account": "safe", "action": "SKIP_STALE_TRIGGER"}]
    stale, reason = m.is_possible_stale_echo(entry, corroborated)
    assert stale is True and "SKIP_STALE_TRIGGER" in reason

    uncorroborated = [{"ts_et": "2026-07-10T09:31:03", "account": "safe", "action": "HOLD"}]
    stale2, _ = m.is_possible_stale_echo(entry, uncorroborated)
    assert stale2 is False


def test_downstream_exclude_block_elite_bull_safe_1100_1200_window():
    """gate #5 block_bull_1100_1200 is armed on Safe -- 11:00-12:00 ET must exclude."""
    inside = _row("2026-07-09T11:15:00")
    outside = _row("2026-07-09T10:15:00")
    assert m._excl_block_elite_bull_safe(inside) is True
    assert m._excl_block_elite_bull_safe(outside) is False


def test_downstream_exclude_block_elite_bull_bold_conf_lvl_rec_afternoon():
    """gate #12 block_conf_lvl_rec_afternoon is armed on Bold -- confluence+level_reclaim AND
    >=14:00 ET must exclude; missing either condition must NOT exclude."""
    matches = _row("2026-07-09T14:05:00", triggers=["level_reclaim", "confluence"])
    wrong_time = _row("2026-07-09T13:59:00", triggers=["level_reclaim", "confluence"])
    wrong_triggers = _row("2026-07-09T14:05:00", triggers=["level_reclaim"])
    assert m._excl_block_elite_bull_bold(matches) is True
    assert m._excl_block_elite_bull_bold(wrong_time) is False
    assert m._excl_block_elite_bull_bold(wrong_triggers) is False


def test_downstream_exclude_entry_body_min_safe_vix_cap():
    """gate #15 vix_bear_hard_cap (23.0) is armed on Safe -- vix>=23.0 must exclude."""
    high_vix = _row("2026-07-09T10:00:00", vix=23.5)
    low_vix = _row("2026-07-09T10:00:00", vix=16.0)
    boundary = _row("2026-07-09T10:00:00", vix=23.0)
    assert m._excl_entry_body_min_safe(high_vix) is True
    assert m._excl_entry_body_min_safe(low_vix) is False
    assert m._excl_entry_body_min_safe(boundary) is True  # >= is inclusive


def test_excl_none_always_false():
    assert m._excl_none(_row("2026-07-09T10:00:00")) is False


# ---- 3. WF branches + BH-FDR ---------------------------------------------------

def test_compute_wf_per_trade_normalized():
    # backtest/safe_fill_bar_gate.py G3: (oos/n_oos) / (is/n_is). compute_wf rounds to 3dp, so
    # tolerance must be wider than the rounding step itself (abs=5e-4), not float-equality-tight.
    wf, note = m.compute_wf(oos_delta=-126.0, n_oos=3, is_delta=295.0, n_is=15)
    assert wf == pytest.approx((-126.0 / 3) / (295.0 / 15), abs=5e-4)
    assert "per-trade" in note


def test_compute_wf_na_structural_zero_is_delta():
    wf, note = m.compute_wf(oos_delta=144.6, n_oos=2, is_delta=0.0, n_is=0)
    assert wf is None and "N/A" in note


def test_compute_wf_aggregate_when_n_is_missing():
    wf, note = m.compute_wf(oos_delta=0.0, n_oos=0, is_delta=468.0, n_is=None)
    assert wf == pytest.approx(0.0)
    assert "AGGREGATE" in note


def test_compute_wf_na_when_zero_oos_trades_but_real_is():
    wf, note = m.compute_wf(oos_delta=0.0, n_oos=0, is_delta=363.16, n_is=26)
    assert wf is None and "N/A" in note


def test_one_sided_p_requires_at_least_2_points():
    assert m.one_sided_p_mean_gt_0([1.0]) is None
    assert m.one_sided_p_mean_gt_0([]) is None
    p = m.one_sided_p_mean_gt_0([10.0, 20.0, 30.0])
    assert p is not None and 0.0 <= p <= 1.0


def test_bh_fdr_is_non_vacuous():
    """A batch with one strong, consistent winner and several weak/negative groups must NOT
    mark everything significant -- proves the correction actually filters, not just runs."""
    tests = [
        {"gate": "strong", "p": 0.001},
        {"gate": "weak1", "p": 0.60},
        {"gate": "weak2", "p": 0.80},
        {"gate": "weak3", "p": 0.95},
        {"gate": "none", "p": None},
    ]
    out = m.bh_fdr(tests, alpha=0.10)
    by_gate = {t["gate"]: t for t in out}
    assert by_gate["strong"]["bh_significant"] is True
    assert by_gate["weak3"]["bh_significant"] is False
    assert by_gate["none"]["bh_significant"] is False   # fail-safe: no p-value never survives
    assert by_gate["none"]["bh_threshold"] is None


def test_bh_fdr_all_significant_when_all_strong():
    tests = [{"gate": f"g{i}", "p": 0.001} for i in range(4)]
    out = m.bh_fdr(tests, alpha=0.10)
    assert all(t["bh_significant"] for t in out)


# ---- 4. current-shape derivation ------------------------------------------------

def test_current_shape_uses_catastrophe_cap_not_flag_off_literal():
    """Regression guard for the exact silent-corruption bug the module docstring warns about:
    the replay harness never receives structure_stop_enabled=True, so passing RIBBON_RIDE.exit's
    own premium_stop_pct (-0.20, the flag-off emergency fallback) would wrongly tighten every
    replayed trade's in-engine stop. CURRENT_SHAPE must carry the catastrophe value instead."""
    assert m.CURRENT_SHAPE["premium_stop_pct"] == pytest.approx(-0.50)
    assert m.CURRENT_SHAPE["premium_stop_pct"] != pytest.approx(strategies_premium_stop_pct())
    assert m.CURRENT_SHAPE["tp1_premium_pct"] == pytest.approx(1.0)
    assert m.CURRENT_SHAPE["tp1_qty_fraction"] == pytest.approx(0.667)
    assert m.CURRENT_SHAPE["profit_lock_mode"] == "trailing"
    # no stop_mode/catastrophe_stop_pct keys leak through (would silently re-trigger the bug if a
    # future edit passed exit_shape.to_dict() through unmodified again)
    assert "stop_mode" not in m.CURRENT_SHAPE
    assert "catastrophe_stop_pct" not in m.CURRENT_SHAPE


def strategies_premium_stop_pct() -> float:
    import strategies
    return strategies.RIBBON_RIDE.exit.premium_stop_pct


def test_strike_for_matches_live_source_of_truth_tables():
    """crypto/lib/strike_selection V15_SAFE_TIERS/V15_BOLD_TIERS, not the vestigial
    params.json v15_strike_offset_per_tier ladder."""
    safe_call = m.strike_for(753.63, "C", "safe")
    assert safe_call == 754   # ATM: round(753.63)=754, offset 0
    bold_put = m.strike_for(753.63, "P", "bold")
    assert bold_put == 751    # OTM-3 put: 754 + (-3)


# ---- 5. golden finding (once committed) ------------------------------------------

@pytest.mark.skipif(not os.path.exists(RESULT), reason="battery result not yet committed")
def test_committed_verdicts_are_non_vacuous_function_of_conditions():
    r = json.load(open(RESULT, encoding="utf-8"))
    for gate_key in ("block_elite_bull__safe", "block_elite_bull__bold",
                      "require_bearish_fill_bar__bold", "entry_bar_body_pct_min__safe",
                      "block_conf_lvl_rec_afternoon__bold", "block_bull_1100_1200__safe"):
        res = r["results"][gate_key]
        c = res["conditions"]
        all_required = (c["1_oos_positive"] and c["2_wf_ge_070_or_waived"]
                        and c["3_sub_window_stable"] and c["4_anchor_no_regression"])
        if all_required and res["bh_significant"]:
            assert res["verdict"] == "DISABLE"
        else:
            assert res["verdict"] == "KEEP"


@pytest.mark.skipif(not os.path.exists(RESULT), reason="battery result not yet committed")
def test_committed_run_this_session_shipped_zero_disables():
    """Pins the actual 2026-07-15 finding: every tested gate's fresh OOS replay under current
    config (SS-B + ATM/OTM-3 strikes + 0.30 floor) came back non-positive-or-thin/anchor-
    unverified -- none cleared the ratification bar. If a future re-run of THIS committed result
    changes that, this test flags it for review rather than silently accepting a new verdict
    mix."""
    r = json.load(open(RESULT, encoding="utf-8"))
    verdicts = {gk: res["verdict"] for gk, res in r["results"].items()}
    disables = [gk for gk, v in verdicts.items() if v == "DISABLE"]
    assert disables == [], f"expected zero DISABLE verdicts in the committed 2026-07-15 run, got {disables}"


@pytest.mark.skipif(not (os.path.exists(RESULT) and os.path.exists(PARAMS_SAFE) and os.path.exists(PARAMS_BOLD)),
                     reason="battery result or live params files not present")
def test_live_params_unchanged_for_tested_gates_given_zero_disables():
    """Since the committed battery shipped zero DISABLE verdicts, both live params files must
    still carry their PRE-battery armed values for every gate this battery tested -- proves no
    params edit slipped in despite the KEEP verdicts. If a gate is later legitimately disabled,
    update this pin alongside that change (it is a state pin, not a policy pin)."""
    safe = json.load(open(PARAMS_SAFE, encoding="utf-8"))
    bold = json.load(open(PARAMS_BOLD, encoding="utf-8"))
    # PIN UPDATED 2026-08-14 for block_elite_bull, per this docstring's own instruction.
    # `f4890edb feat(gate): lift block_elite_bull on BOTH cores -- trade-to-learn trial 2
    # (SHIP B)` deliberately disabled it on Safe AND Bold and did not update this pin, so the
    # test sat RED and guarded nothing thereafter. Verified deliberate before moving it: the
    # lift is its own commit with a named trial, not a stray edit. The pin still binds -- it
    # now asserts the CURRENT state, so the next unannounced flip REDs again.
    assert safe.get("block_elite_bull") is False      # lifted by f4890edb (trade-to-learn 2)
    assert bold.get("block_elite_bull") is False      # lifted by f4890edb, same commit
    assert safe.get("block_bull_1100_1200") is True
    assert safe.get("entry_bar_body_pct_min") == 0.2
    assert bold.get("require_bearish_fill_bar") is True
    assert bold.get("block_conf_lvl_rec_afternoon") is True

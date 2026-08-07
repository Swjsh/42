"""Guard for backtest/tools/fleet_arm_replay.py -- the fleet-arm-faithful strike-tier +
exit-P&L replay harness (2026-08-02).

Load-bearing invariants this guard pins:

  1. INPUTS ARE REAL INPUTS (the task's own explicit requirement): changing gate_override /
     strike_tiers / exit_patch / full_send / direction_lock must actually change what gets
     replayed -- vary-and-assert in BOTH directions, not a single-sided smoke test. This is
     the whole point of the tool: it must not silently substitute the arm's own on-disk
     profile underneath a caller's override.
  2. TWO REAL BUGS this build caught and fixed, each RED-proofed here so they cannot
     silently regress:
       a. FIFO ROUND-TRIP SPLITTING: the same OCC symbol can be bought/sold/re-bought on
          the SAME day (a real risky-3 case blended two round trips into one fictional
          qty=10 anchor, replaying to +$605 against a real -$80). mine_real_arm_fills must
          treat a position returning to flat as a hard boundary.
       b. use_real_fills=True must reach run_backtest explicitly -- _params_to_kwargs has
          no mapping for it and run_backtest's own default is False.
  3. DST FRAME CORRECTNESS: SPY must be parsed wall-v1 (matching the OPRA option cache's
     own fixed-offset storage), never et-v2/DST-corrected -- crossing frames silently
     misaligns every EST-month (Nov-Mar) trade against its own option bars by up to 1 hour.
  4. ANCHOR REPRODUCTION: each of the three fleet_rest arms' auto-mined real fills must
     clear ANCHOR_PASS_THRESHOLD, so `verdict_label` stays "ANCHOR-VALIDATED" rather than
     silently degrading to "UNVALIDATED" without anyone noticing.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_fleet_arm_replay.py -q
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import json
import sys
from pathlib import Path
from unittest import mock

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
CRYPTO_LIB = REPO / "crypto" / "lib"
for _p in (REPO, BACKTEST, BACKTEST / "tools", FLEET_DIR, CRYPTO_LIB):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import fleet_arm_replay as far  # noqa: E402
import strike_selection as ss    # noqa: E402

DATA_AVAILABLE = far.SPY_FILE.exists() and far.VIX_FILE.exists()
ANCHOR_DATA_AVAILABLE = far.ANCHOR_SPY_FILE.exists() and far.FILLS_LEDGER_PATH.exists()

# A short, cheap window for population vary-and-assert tests -- these need run_backtest to
# execute, which is NOT free, so keep the window small (this is the SAME discipline
# replay_fleet_arms.py's own compute_arm_fidelity uses: "the wrapping test belongs in the
# FULL suite / CI, NOT the curated <2s pre-commit gate").
SHORT_START = dt.date(2026, 6, 1)
SHORT_END = dt.date(2026, 6, 24)


@pytest.fixture(scope="module")
def short_data():
    if not DATA_AVAILABLE:
        pytest.skip("full-history SPY/VIX data not cached")
    spy_df = pd.read_csv(far.SPY_FILE)
    vix_df = pd.read_csv(far.VIX_FILE)
    spy_df["timestamp_et"] = far.parse_timestamp_et(spy_df["timestamp_et"], frame=far.FRAME_WALL_V1)
    vix_df["timestamp_et"] = far.parse_timestamp_et(vix_df["timestamp_et"], frame=far.FRAME_ET_V2)
    mask = (spy_df["timestamp_et"].dt.date >= SHORT_START) & (spy_df["timestamp_et"].dt.date <= SHORT_END)
    return spy_df.loc[mask].reset_index(drop=True), vix_df


# ---------------------------------------------------------------------------------------- #
# 1a. GATE_OVERRIDE IS A REAL INPUT (task's explicit vary-and-assert requirement)
# ---------------------------------------------------------------------------------------- #
def test_gate_override_min_triggers_changes_the_population(short_data):
    """RED-PROOF: an UNGATED config (risky-1's actual current shape) must admit AT LEAST as
    many entries as a TIGHT config (min_triggers=2 + require ELITE) on the identical
    window/data. If this tool silently ignored gate_override and always replayed some fixed
    profile, loose and tight would produce IDENTICAL counts -- they must not."""
    spy, vix = short_data
    loose = far.ArmReplayConfig.for_arm("risky-1", gate_override={})
    tight = far.ArmReplayConfig.for_arm(
        "risky-1", gate_override={"min_triggers": 2, "require_confluence_or_sequence": True})
    loose_trades, _, _ = far.gated_population(loose, spy, vix, SHORT_START, SHORT_END)
    tight_trades, _, _ = far.gated_population(tight, spy, vix, SHORT_START, SHORT_END)
    assert len(tight_trades) <= len(loose_trades)
    assert len(tight_trades) < len(loose_trades), (
        "tight ELITE-only gate produced the SAME count as ungated on this window -- either "
        "the window has zero non-ELITE entries (re-pick SHORT_START/END) or gate_override "
        "is being silently ignored")


def test_gate_override_min_triggers_ALONE_changes_the_population(short_data):
    """Isolates JUST min_triggers (no require_confluence_or_sequence) -- the ONE genuinely
    new post-filter this tool adds inside _run_backtest_params's v15_strike_offset_per_tier
    injection path (the ELITE/confluence and direction_lock filters are reused verbatim from
    replay_fleet_arms.py and already guard-tested there). Without this test, a regression
    that broke ONLY the min_triggers injection (while ELITE filtering kept working) could
    hide behind the combined test above."""
    spy, vix = short_data
    loose = far.ArmReplayConfig.for_arm("risky-1", gate_override={})
    min3 = far.ArmReplayConfig.for_arm("risky-1", gate_override={"min_triggers": 3})
    loose_trades, _, _ = far.gated_population(loose, spy, vix, SHORT_START, SHORT_END)
    min3_trades, _, _ = far.gated_population(min3, spy, vix, SHORT_START, SHORT_END)
    assert len(min3_trades) < len(loose_trades), (
        "min_triggers=3 in isolation (no ELITE requirement) produced the SAME count as "
        "ungated -- the v15_strike_offset_per_tier injection path's min_triggers mapping "
        "into filter_10_min_triggers_bear/bull is being silently ignored")


def test_gate_override_min_confidence_benches_the_population(short_data):
    """min_confidence on the confidence-less deterministic signal must EMPTY the
    population (benched-by-design, matching replay_fleet_arms.py's own finding) --
    RED-proofed against the SAME window's non-empty ungated population."""
    spy, vix = short_data
    cfg = far.ArmReplayConfig.for_arm("risky-1", gate_override={"min_confidence": 0.5})
    trades, notes, benched = far.gated_population(cfg, spy, vix, SHORT_START, SHORT_END)
    assert benched is True
    assert trades == []
    assert any("benched by design" in n for n in notes)


# ---------------------------------------------------------------------------------------- #
# 1b. STRIKE_TIERS IS A REAL INPUT
# ---------------------------------------------------------------------------------------- #
def test_strike_tiers_override_changes_resolved_strike(short_data):
    """Same arm, same window, same equity (<$2K bracket, where the tables genuinely
    diverge) -- ONLY strike_tiers differs -- the resulting trade strikes must differ."""
    spy, vix = short_data
    equity = 1_800.0
    cfg_bold_core = far.ArmReplayConfig.for_arm("risky-1", strike_tiers="bold_core", equity=equity)
    cfg_bold = far.ArmReplayConfig.for_arm("risky-1", strike_tiers="bold", equity=equity)
    t_core, _, _ = far.gated_population(cfg_bold_core, spy, vix, SHORT_START, SHORT_END)
    t_bold, _, _ = far.gated_population(cfg_bold, spy, vix, SHORT_START, SHORT_END)
    assert t_core and t_bold, "fixture window produced zero trades -- re-pick the window"
    # NOTE: counts may legitimately differ too (use_real_fills=True gates on THAT specific
    # strike's own OPRA cache availability, and a different strike is a different contract
    # symbol that may or may not be cached) -- the invariant under test is strike, not count.
    core_strikes = {int(t.strike) for t in t_core}
    bold_strikes = {int(t.strike) for t in t_bold}
    assert core_strikes != bold_strikes, (
        "bold_core (ATM under $2K) and bold (OTM-3 under $2K) produced IDENTICAL strikes -- "
        "strike_tiers is being silently ignored")
    # bold_core's $0-2K bracket is ATM (offset 0); bold's is OTM-3 (offset -3 puts / +3 calls
    # from spot) -- bold's strikes must sit strictly farther from spot on average.
    core_dist = sum(abs(t.strike - round(t.entry_spot)) for t in t_core) / len(t_core)
    bold_dist = sum(abs(t.strike - round(t.entry_spot)) for t in t_bold) / len(t_bold)
    assert bold_dist > core_dist, (
        f"bold (OTM-3) average |strike-spot|={bold_dist:.2f} should exceed "
        f"bold_core (ATM) average={core_dist:.2f}")


def test_resolve_strike_tiers_named_tables_are_distinct():
    names = ("safe", "bold", "bold_core", "probe")
    tables = {n: far.resolve_strike_tiers(n) for n in names}
    assert tables["bold"] != tables["bold_core"], "bold and bold_core must differ (the $0-2K bracket)"
    assert tables["bold_core"] != tables["probe"], "bold_core and probe must differ ($2K-10K bracket)"
    with pytest.raises(ValueError):
        far.resolve_strike_tiers("not_a_real_table")


# ---------------------------------------------------------------------------------------- #
# 1c. EXIT_PATCH / FULL_SEND / DIRECTION_LOCK ARE REAL INPUTS
# ---------------------------------------------------------------------------------------- #
def test_exit_patch_override_changes_resolved_exit_shape():
    # risky-1 (not safe-3): safe-3's own exit_patch ({"stop_mode": "structure",
    # "profit_lock_mode": "trailing"}) is a DOCUMENTED NO-OP for ribbon_ride specifically --
    # accounts.json's own note: "for ribbon_ride this is a no-op (already the REGISTRY
    # default)". risky-1's patch (tp1_premium_pct 0.5 vs the registry's 1.0) is a REAL change
    # for this strategy, so it is the correct fixture for "does the override move anything".
    default_cfg = far.ArmReplayConfig.for_arm("risky-1")
    stripped_cfg = far.ArmReplayConfig.for_arm("risky-1", exit_patch={})
    default_shape = far.resolve_exit_shape(default_cfg)
    stripped_shape = far.resolve_exit_shape(stripped_cfg)
    assert default_shape != stripped_shape, (
        "stripping exit_patch produced the SAME exit shape as risky-1's real patched one -- "
        "exit_patch is being silently ignored")
    assert default_shape["tp1_premium_pct"] == 0.5
    assert stripped_shape["tp1_premium_pct"] == 1.0  # RIBBON_RIDE registry default
    custom_cfg = far.ArmReplayConfig.for_arm("risky-1", exit_patch={"trail_pct": 0.42})
    custom_shape = far.resolve_exit_shape(custom_cfg)
    assert custom_shape["trail_pct"] == 0.42


def test_full_send_flag_changes_qty_clamp():
    """RED-PROOF: with full_send=True, qty must clamp to min_contracts even when the
    account's own sizing tier would give more; with full_send=False (same arm, same
    gate_override otherwise), qty must NOT clamp. This is the exact mechanism the risky-1
    lane-composition investigation (same session) found applies regardless of WHICH lane
    an entry came from -- pinned here independently for this tool's own sizing path."""
    base_params = json.loads((REPO / "automation" / "state" / "aggressive" / "params.json")
                             .read_text(encoding="utf-8"))
    on_cfg = far.ArmReplayConfig.for_arm("risky-1", full_send=True, equity=2_500.0)
    off_cfg = far.ArmReplayConfig.for_arm("risky-1", full_send=False, equity=2_500.0)
    qty_on = far.resolve_qty(on_cfg, elite=True, base_params=base_params)
    qty_off = far.resolve_qty(off_cfg, elite=True, base_params=base_params)
    assert qty_on == on_cfg.min_contracts
    assert qty_off is not None and qty_off > qty_on, (
        "full_send=False must NOT clamp to min_contracts when the sizing tier allows more")


def test_direction_lock_override_filters_population(short_data):
    spy, vix = short_data
    unlocked = far.ArmReplayConfig.for_arm("risky-1", gate_override={}, direction_lock=None)
    put_only = far.ArmReplayConfig.for_arm("risky-1", gate_override={}, direction_lock="PUT_ONLY")
    t_unlocked, _, _ = far.gated_population(unlocked, spy, vix, SHORT_START, SHORT_END)
    t_put, _, _ = far.gated_population(put_only, spy, vix, SHORT_START, SHORT_END)
    assert any(getattr(t, "side", None) == "C" for t in t_unlocked), (
        "fixture window has zero call entries -- re-pick the window to make this a real test")
    assert all(getattr(t, "side", "P") == "P" for t in t_put)
    assert len(t_put) < len(t_unlocked)


# ---------------------------------------------------------------------------------------- #
# 2a. FIFO ROUND-TRIP SPLITTING BUG -- RED-PROOF
# ---------------------------------------------------------------------------------------- #
def test_mine_real_arm_fills_splits_same_day_reentries(tmp_path):
    """Exact shape of the real bug this session found: risky-3 bought/sold/re-bought/sold
    SPY260708P00741000 on 2026-07-08. Reconstructed here as a minimal fixture (real dollar
    figures from the actual ledger row) -- must produce TWO anchors, not one blended one."""
    ledger = tmp_path / "fills-ledger.jsonl"
    rows = [
        {"arm": "risky-3", "attribution": "engine", "symbol": "SPY260708P00741000",
         "side": "buy", "qty": 5.0, "price": 0.94, "ts_et": "2026-07-08T09:52:07.774592",
         "date_et": "2026-07-08"},
        {"arm": "risky-3", "attribution": "engine", "symbol": "SPY260708P00741000",
         "side": "sell", "qty": 5.0, "price": 0.78, "ts_et": "2026-07-08T10:01:06.431979",
         "date_et": "2026-07-08"},
        {"arm": "risky-3", "attribution": "engine", "symbol": "SPY260708P00741000",
         "side": "buy", "qty": 3.0, "price": 0.25, "ts_et": "2026-07-08T13:07:05.702360",
         "date_et": "2026-07-08"},
        {"arm": "risky-3", "attribution": "engine", "symbol": "SPY260708P00741000",
         "side": "buy", "qty": 2.0, "price": 0.25, "ts_et": "2026-07-08T13:07:05.826561",
         "date_et": "2026-07-08"},
        {"arm": "risky-3", "attribution": "engine", "symbol": "SPY260708P00741000",
         "side": "sell", "qty": 5.0, "price": 0.25, "ts_et": "2026-07-08T13:16:05.219405",
         "date_et": "2026-07-08"},
    ]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out = far.mine_real_arm_fills("risky-3", ledger_path=ledger)
    assert len(out) == 2, f"expected 2 split round trips, got {len(out)}: {out}"
    first, second = sorted(out, key=lambda r: r["entry_ts_et"])
    assert first["entry_premium"] == 0.94 and first["qty"] == 5 and first["real_pnl"] == -80.0
    assert second["entry_premium"] == 0.25 and second["qty"] == 5 and second["real_pnl"] == 0.0
    # the OLD (buggy) behavior would have produced ONE row: qty=10, entry_premium=0.595,
    # entry_ts=09:52 -- explicitly assert that fiction is NOT what comes out.
    assert not any(r["qty"] == 10 for r in out)
    assert not any(abs((r["entry_premium"] or 0) - 0.595) < 1e-6 for r in out)


def test_mine_real_arm_fills_excludes_manual_and_other_arms(tmp_path):
    ledger = tmp_path / "fills-ledger.jsonl"
    rows = [
        {"arm": "risky-1", "attribution": "manual", "symbol": "SPY260708P00741000",
         "side": "buy", "qty": 5.0, "price": 0.50, "ts_et": "2026-07-08T09:52:00",
         "date_et": "2026-07-08"},
        {"arm": "risky-1", "attribution": "manual", "symbol": "SPY260708P00741000",
         "side": "sell", "qty": 5.0, "price": 0.60, "ts_et": "2026-07-08T09:55:00",
         "date_et": "2026-07-08"},
        {"arm": "safe-3", "attribution": "engine", "symbol": "SPY260708P00741000",
         "side": "buy", "qty": 3.0, "price": 0.50, "ts_et": "2026-07-08T09:52:00",
         "date_et": "2026-07-08"},
        {"arm": "safe-3", "attribution": "engine", "symbol": "SPY260708P00741000",
         "side": "sell", "qty": 3.0, "price": 0.60, "ts_et": "2026-07-08T09:55:00",
         "date_et": "2026-07-08"},
    ]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert far.mine_real_arm_fills("risky-1", ledger_path=ledger) == []  # manual only, excluded
    assert len(far.mine_real_arm_fills("safe-3", ledger_path=ledger)) == 1


def test_mine_real_arm_fills_leaves_open_positions_unresolved(tmp_path):
    ledger = tmp_path / "fills-ledger.jsonl"
    rows = [
        {"arm": "risky-1", "attribution": "engine", "symbol": "SPY260708P00741000",
         "side": "buy", "qty": 5.0, "price": 0.50, "ts_et": "2026-07-08T09:52:00",
         "date_et": "2026-07-08"},
    ]
    ledger.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    assert far.mine_real_arm_fills("risky-1", ledger_path=ledger) == []


# ---------------------------------------------------------------------------------------- #
# 2b. use_real_fills=True RED-PROOF
# ---------------------------------------------------------------------------------------- #
def test_gated_population_passes_use_real_fills_true(short_data):
    """RED-PROOF: run_backtest's own default is False (backtest/lib/orchestrator.py) and
    _params_to_kwargs has no mapping for the key -- if a future edit drops the explicit
    kwarg, this test must catch it via a spy, not just via a P&L number silently drifting."""
    spy, vix = short_data
    cfg = far.ArmReplayConfig.for_arm("risky-1")
    with mock.patch("fleet_arm_replay.run_backtest", wraps=far.run_backtest) as spy_call:
        far.gated_population(cfg, spy, vix, SHORT_START, SHORT_END)
    assert spy_call.call_args.kwargs.get("use_real_fills") is True


# ---------------------------------------------------------------------------------------- #
# 3. DST FRAME CORRECTNESS
# ---------------------------------------------------------------------------------------- #
@pytest.mark.skipif(not DATA_AVAILABLE, reason="full-history SPY/VIX data not cached")
def test_load_data_uses_wall_v1_for_spy_not_et_v2():
    """RED-PROOF: parse the same raw column both ways and confirm _load_data's OWN output
    matches wall-v1, not et-v2, on a KNOWN winter day where the two conventions genuinely
    diverge (test_et_frame_guards.py's own WINTER_DAY, 2025-01-07, reused here rather than
    re-picked, so both guards agree on which day is discriminating)."""
    raw = pd.read_csv(far.SPY_FILE)
    winter_day = dt.date(2025, 1, 7)
    wall_v1 = far.parse_timestamp_et(raw["timestamp_et"], frame=far.FRAME_WALL_V1)
    et_v2 = far.parse_timestamp_et(raw["timestamp_et"], frame=far.FRAME_ET_V2)
    wall_v1_times = sorted(wall_v1[wall_v1.dt.date == winter_day].dt.time.unique())
    et_v2_times = sorted(et_v2[et_v2.dt.date == winter_day].dt.time.unique())
    assert wall_v1_times != et_v2_times, (
        "fixture no longer discriminates -- re-pick a winter day genuinely present in "
        "SPY_FILE, or the frame divergence itself has been fixed upstream")

    spy_df, _vix_df, _ribbon = far._load_data()
    loaded_times = sorted(spy_df.loc[spy_df["timestamp_et"].dt.date == winter_day, "timestamp_et"]
                          .dt.time.unique())
    assert loaded_times == wall_v1_times, (
        "_load_data's SPY frame does not match wall-v1 on a winter day -- this silently "
        "misaligns SPY bars against the OPRA option cache (same fixed-offset storage) by up "
        "to 1 hour for every EST-month trade, see et_frame.py's module docstring")


def test_symbol_side_char_parsing():
    """Pins the OCC-symbol side-char index bug found alongside the FIFO bug (a stray first
    draft used symbol[len-8], off by one from the correct symbol[-9])."""
    call = far.option_symbol(dt.date(2026, 7, 8), 741, "C")
    put = far.option_symbol(dt.date(2026, 7, 8), 741, "P")
    assert call[-9] == "C" and put[-9] == "P"
    assert len(call) == 18 and len(put) == 18


# ---------------------------------------------------------------------------------------- #
# 4. ANCHOR REPRODUCTION (real data, full suite / CI -- not the curated pre-commit gate)
# ---------------------------------------------------------------------------------------- #
@pytest.mark.skipif(not ANCHOR_DATA_AVAILABLE, reason="anchor SPY file or fills-ledger.jsonl missing")
@pytest.mark.parametrize("arm_id", ["safe-3", "risky-1", "risky-3"])
def test_anchor_pass_rate_clears_threshold(arm_id):
    """pass_rate is a FIDELITY-ONLY metric (n_pass / n_replayable, FLEET-ANCHOR-EXIT-WALK-
    FIDELITY-DRIFT fix 2026-08-07) -- n_anchors (total mined) and n_replayable (had an OPRA
    cache to attempt) are asserted SEPARATELY so a coverage gap can never again silently
    masquerade as an exit-fidelity failure the way it did pre-fix (54-68% band, root-caused
    to be ENTIRELY n_data_gap rows counted as automatic fails, not a real exit-walk bug)."""
    cfg = far.ArmReplayConfig.for_arm(arm_id)
    spy = far._load_anchor_spy()
    ribbon = far.efr.build_ribbon_lookup(spy)
    out = far.run_anchor_validation(cfg, spy, ribbon)
    assert out["n_anchors"] >= 10, f"{arm_id}: too few mined anchors ({out['n_anchors']}) to trust the rate"
    assert out["n_replayable"] >= 10, (
        f"{arm_id}: only {out['n_replayable']} of {out['n_anchors']} mined anchors had an "
        f"OPRA cache to replay against -- too few to trust the fidelity rate even though "
        f"coverage itself isn't a fidelity bug")
    assert out["pass_rate"] >= far.ANCHOR_PASS_THRESHOLD, (
        f"{arm_id}: anchor pass rate {out['pass_rate']:.0%} (over {out['n_replayable']} "
        f"replayable fills) dropped below {far.ANCHOR_PASS_THRESHOLD:.0%} -- exit-walk "
        f"fidelity regressed, or the anchor mining/replay pipeline broke silently")
    assert out["unvalidated"] is False


@pytest.mark.skipif(not ANCHOR_DATA_AVAILABLE, reason="anchor SPY file or fills-ledger.jsonl missing")
@pytest.mark.parametrize("arm_id", ["safe-3", "risky-1", "risky-3"])
def test_anchor_pass_rate_denominator_excludes_data_gaps(arm_id):
    """RED-PROOFS the exact bug this fire fixed: a data-coverage gap (missing OPRA cache /
    no SPY day for that date) must NOT be counted as an automatic anchor FAIL. Reverting
    run_anchor_validation's denominator back to `n_pass / n_anchors` (the pre-fix formula)
    makes THIS test fail because n_data_gap > 0 is real for all three arms today -- confirmed
    live (2026-08-07): safe-3 n_data_gap=7/34, risky-1=13/37, risky-3=17/54, all from
    NO_OPRA_CACHE_OR_NO_ENTRY_PREMIUM / NO_SPY_DAY rows, zero of them exit-fidelity checks."""
    cfg = far.ArmReplayConfig.for_arm(arm_id)
    spy = far._load_anchor_spy()
    ribbon = far.efr.build_ribbon_lookup(spy)
    out = far.run_anchor_validation(cfg, spy, ribbon)
    # Bookkeeping identity: every mined anchor is EITHER replayable OR a disclosed data gap.
    assert out["n_replayable"] + out["n_data_gap"] == out["n_anchors"]
    n_data_gap_rows = sum(1 for r in out["rows"] if r.get("replay_status") != "OK")
    assert n_data_gap_rows == out["n_data_gap"]
    # This arm's real fills DO include data gaps today -- if this ever goes to 0 because the
    # OPRA cache backfilled, that's fine (the assert below just stops being exercised), but
    # right now it must be > 0 or this guard isn't actually proving anything for this arm.
    assert out["n_data_gap"] > 0, (
        f"{arm_id}: expected >0 data-coverage gaps today (OPRA cache incomplete for older "
        f"real fills) -- if this now legitimately reads 0, this test's live-evidence claim "
        f"is stale and should be re-verified, not silently trusted")
    # THE bug this fire fixed: pass_rate must be computed over n_replayable, not n_anchors.
    # A data-gap-heavy arm with PERFECT fidelity on its replayable population must NOT be
    # dragged toward UNVALIDATED by rows that were never even judged.
    expected_pass_rate = round(out["n_pass"] / out["n_replayable"], 4) if out["n_replayable"] else 0.0
    assert out["pass_rate"] == expected_pass_rate
    buggy_pre_fix_rate = out["n_pass"] / out["n_anchors"]
    assert out["pass_rate"] > buggy_pre_fix_rate, (
        f"{arm_id}: fixed pass_rate ({out['pass_rate']}) should exceed what the pre-fix "
        f"all-anchors-denominator formula would have produced ({buggy_pre_fix_rate:.4f}) "
        f"whenever n_data_gap > 0 -- if it doesn't, the fix regressed")
    # opra_coverage_rate is the SEPARATE, still-visible signal for the data gap itself.
    assert out["opra_coverage_rate"] == round(out["n_replayable"] / out["n_anchors"], 4)
    assert 0.0 < out["opra_coverage_rate"] < 1.0


# ---------------------------------------------------------------------------------------- #
# 5. CONFIG DEFAULTS MATCH accounts.json (the "reproduces the arm exactly" contract)
# ---------------------------------------------------------------------------------------- #
def test_for_arm_default_matches_current_accounts_json():
    accounts = far._accounts()
    arm = far._arm(accounts, "risky-1")
    cfg = far.ArmReplayConfig.for_arm("risky-1", accounts)
    assert cfg.gate_override == (arm.get("gate_override") or {})
    assert cfg.direction_lock == arm.get("direction_lock")
    assert cfg.strike_tiers_label == "bold_core"  # current live config, see accounts.json
    assert cfg.strike_tiers == ss.V15_BOLD_CORE_TIERS
    assert cfg.full_send is True


def test_effective_arm_reflects_overrides_not_disk():
    cfg = far.ArmReplayConfig.for_arm("risky-1", gate_override={}, full_send=False)
    eff = cfg.effective_arm()
    assert "full_send" not in (eff.get("gate_override") or {})
    cfg2 = far.ArmReplayConfig.for_arm("risky-3", gate_override={"full_send": True}, full_send=True)
    eff2 = cfg2.effective_arm()
    assert eff2["gate_override"]["full_send"] is True


# ---------------------------------------------------------------------------------------- #
# 6. ATM-COVERAGE HEURISTIC -- RED-PROOF for the id-prefix-guess bug found while producing
#    the final deliverable scorecards (safe-3 uses the "bold" table by DESIGN, not "safe" --
#    a naive `arm_id.startswith("safe")` guess falsely reported its OWN unchanged real fills
#    as not covering its OWN unchanged current tier).
# ---------------------------------------------------------------------------------------- #
def test_atm_coverage_heuristic_uses_real_history_not_id_prefix_guess():
    """UPDATED 2026-08-03 (FLEET-STRIKE-TIER-ATM-EXTENSION-SAFE3): safe-3's LIVE
    accounts.json config flipped 'bold'->'bold_core' this session. ArmReplayConfig.for_arm
    reads accounts.json fresh (see its own docstring: "reproduces `arm_id` exactly as
    accounts.json has it TODAY"), so safe3_cfg now reports 'bold_core' too -- and
    PRE_BOLD_CORE_HISTORICAL_TABLE (the FROZEN record of what every real fill was actually
    priced under, deliberately NOT auto-updated when accounts.json changes -- see that
    dict's own module comment) still says safe-3's history is 'bold'/OTM-3. At safe-3's
    live equity (<$2K) the two now disagree, so this MUST flip to the same 'NOT covered'
    shape risky-1 already demonstrates below -- this is the exact mechanism this test
    exists to prove works correctly across an arm's config changing over time, not just a
    point-in-time snapshot. Was `assert ... is True` before this session."""
    safe3_cfg = far.ArmReplayConfig.for_arm("safe-3")  # table='bold_core' as of 2026-08-03
    assert safe3_cfg.strike_tiers_label == "bold_core"
    assert far._tier_predates_or_matches_anchor_history(safe3_cfg) is False, (
        "safe-3's real fills were priced under 'bold' (OTM-3 under $2K) before the "
        "2026-08-03 bold_core ship -- at its live equity (<$2K) this MUST be reported as "
        "NOT covered, mirroring risky-1/risky-3's own 2026-08-01 transition")

    risky1_cfg = far.ArmReplayConfig.for_arm("risky-1")  # table='bold_core' (ATM under $2K)
    assert far._tier_predates_or_matches_anchor_history(risky1_cfg) is False, (
        "risky-1's real fills were priced under 'bold' (OTM-3 under $2K) before the "
        "2026-08-01 bold_core ship -- at its live equity (<$2K) this MUST be reported as "
        "NOT covered")

    # UPDATED 2026-08-04 (ATM-TIER-EXTENSION-2K-10K, prereg atm-tier-extension-2k10k-
    # prereg-2026-08-03.json): the $2K-$10K bracket moved OTM-2 -> ATM, so bold_core now
    # DISAGREES with the frozen historical table there too -- an ATM-cell replay at $2.5K
    # is NOT anchor-covered anymore, and the heuristic must say so. UPDATED AGAIN
    # 2026-08-06 (per-arm KILL of that extension on risky-3, n=14/-$653): risky-3's live
    # label is now 'bold_core_pre_ext' whose $2K-10K row is OTM-2 -- MATCHING the frozen
    # fill history -- so risky-3 flips back to covered, and the ATM-vs-history divergence
    # exhibit moves to risky-1 (which KEEPS bold_core/ATM there, n=11/+$903).
    risky1_at_2_5k = dataclasses.replace(
        far.ArmReplayConfig.for_arm("risky-1"), equity=2_500.0)  # $2K-10K: bold_core=ATM vs history=OTM-2
    assert far._tier_predates_or_matches_anchor_history(risky1_at_2_5k) is False, (
        "risky-1 keeps the 2K-10K ATM extension while every real fill to date was priced "
        "OTM-2/OTM-3 there -- must be reported NOT covered")

    risky3_at_2_5k = dataclasses.replace(
        far.ArmReplayConfig.for_arm("risky-3"), equity=2_500.0)  # $2K-10K: pre_ext=OTM-2 == history
    assert risky3_at_2_5k.strike_tiers_label == "bold_core_pre_ext"
    assert far._tier_predates_or_matches_anchor_history(risky3_at_2_5k) is True, (
        "post-2026-08-06 kill, risky-3's $2K-10K band (OTM-2) matches the table its real "
        "fills were priced under -- the heuristic must recognize coverage came BACK")

    risky3_at_15k = dataclasses.replace(
        far.ArmReplayConfig.for_arm("risky-3"), equity=15_000.0)  # $10K-25K: both tables agree (OTM-1)
    assert far._tier_predates_or_matches_anchor_history(risky3_at_15k) is True, (
        "at equity in [$10K,$25K), bold and bold_core still agree (both OTM-1) -- must be covered")

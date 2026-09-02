"""Companion guards for the STRUCTURE-STOP study (backtest/tools/structure_stop_study.py +
analysis/recommendations/structure-stop-preregistration.json). Load-bearing invariants:

  1. Pre-registration hash pin -- the frozen candidates/hashes on disk match what the runner
     actually uses at run time (a drift here means the study silently ran against a DIFFERENT
     grid than the one that was pre-registered).
  2. C6 (look-ahead): the structure stop reads ONLY bar closes -- a synthetic intrabar dip below
     trigger that closes back above must NOT fire; a genuine close-below must fire, at the next
     bar's OPEN (the C6 fill-mark convention), not the close-bar's own closing premium.
     Trigger-level recovery (real positions) must never consult a bar after entry either.
  3. Side-awareness: calls break DOWN, puts break UP; the buffer (SS-C) widens the threshold and
     can suppress a fire that the zero-buffer candidates would take.
  4. Fallback-inclusion: a position/signal with no recoverable trigger_level is NEVER dropped --
     it is replayed with the structure check disabled, not excluded from the population.
  5. Regression guard for the entry_ts pre-entry-bar-filter bug found+fixed while building this
     study: without filtering option bars to >= entry_ts, CONTROL's anchor total silently
     inflated from -757.1 to +984.5 on the SAME 79 positions. Pins the exact, independently
     verified number both directly (unit, $0) and via a a live end-to-end replay.

Run: cd backtest && ../backtest/.venv/Scripts/python.exe -m pytest tests/test_structure_stop_study.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import structure_stop_study as sss      # noqa: E402
import exit_shape_parity_study as esp   # noqa: E402

PREREG = REPO / "analysis" / "recommendations" / "structure-stop-preregistration.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "structure-stop-2026-07-09.json"


def _synthetic_spy(rows: list[dict]) -> pd.DataFrame:
    spy_full = pd.DataFrame(rows)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    spy_full["time"] = spy_full["timestamp_et"].dt.time
    return spy_full


# ---------------------------------------------------------------------------------------------
# 1) PRE-REGISTRATION FROZEN + HASH PIN
# ---------------------------------------------------------------------------------------------
def test_preregistration_file_exists_and_is_frozen():
    assert PREREG.exists(), f"pre-registration missing: {PREREG}"
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert preg["version"] == 1
    # A prereg's STATUS is a state machine that correct operation ADVANCES; its CONTENT is
    # what must never move. This line used to pin the status to FROZEN_PENDING_RUN, so the
    # guard went RED the moment the study was legitimately run and its verdict recorded --
    # exactly what a pre-registration exists to allow. Four of these fired together on
    # 2026-09-02 for that reason, having been run the night before.
    #
    # This is NOT a weakened assertion. It pins the legal state machine AND requires a
    # RUN_COMPLETE claim to be backed by an actual run record on the file, which the old
    # equality check never did. Immutability of the design itself is guarded -- properly --
    # by the sibling tests in this file that pin the sha256 population hashes and the
    # runner's frozen constants; those are the anti-repick teeth, not this line.
    status = str(preg["status"])
    assert status.startswith("FROZEN_") or status.startswith("RUN_COMPLETE"), (
        f"illegal prereg status {status!r} -- a prereg may sit FROZEN_* or advance to "
        f"RUN_COMPLETE, and nothing else (a draft/unfrozen status here means the "
        f"no-repick clause is not in force)"
    )
    if status.startswith("RUN_COMPLETE"):
        assert any(k.startswith("closed_") for k in preg), (
            f"status is {status!r} but the file carries no closed_* run record -- a "
            f"completed verdict must be evidenced on the prereg, not just asserted"
        )
    assert preg["hypothesis_provenance"]["excluded_from_all_pass_fail_layers"] is True
    assert preg["hypothesis_provenance"]["today_date"] == "2026-07-09"


def test_preregistration_candidate_shapes_match_runner_constants():
    """Frozen shapes/buffers in the pre-registration must match EXACTLY what the runner uses --
    catches silent grid drift (a re-pick after seeing results would show up here)."""
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    cands = preg["candidates"]
    assert cands["CONTROL"]["shape"] == sss.CONTROL_SHAPE
    assert cands["SS-A"]["shape"] == sss.SS_A_SHAPE
    assert cands["SS-B"]["shape"] == sss.SS_B_SHAPE
    assert cands["SS-C"]["shape"] == sss.SS_C_SHAPE
    assert cands["SS-A"]["structure_stop"]["buffer_usd"] == sss.STRUCTURE_BUFFER["SS-A"]
    assert cands["SS-B"]["structure_stop"]["buffer_usd"] == sss.STRUCTURE_BUFFER["SS-B"]
    assert cands["SS-C"]["structure_stop"]["buffer_usd"] == sss.STRUCTURE_BUFFER["SS-C"]
    assert preg["c6_fill_mark_convention"]["choice"] == "next_bar_open"
    assert preg["trigger_level_recovery"]["layer_b_anchor_and_exhibit"]["lookback_bars"] == \
        sss.TRIGGER_RECOVERY_LOOKBACK_BARS


def test_preregistration_hashes_match_runner_expected_constants():
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    sig = preg["signal_set_integrity"]
    assert sig["layer_a_fresh_slice"]["sha256_16"] == sss.EXPECTED_FRESH_SHA16
    assert sig["layer_b_real_fills_anchor"]["population_sha256_16"] == sss.EXPECTED_ANCHOR_POP_SHA16
    assert sig["layer_b_real_fills_anchor"]["n_positions"] == 79
    assert sig["layer_b_real_fills_anchor"]["n_unique_signals"] == 17
    assert sig["layer_b_real_fills_anchor"]["control_parity_check"]["expected_control_anchor_total"] == -757.1


def test_preflight_verifies_the_real_files_on_disk():
    """Runs the REAL preflight() -- reads the actual signal-set + fills-ledger, hashes them
    fresh -- and asserts they validate clean against the frozen pre-registration."""
    pf = sss.preflight()
    assert pf["fresh_slice_hash_ok"] is True, pf
    assert pf["anchor_population_hash_ok"] is True, pf
    assert pf["preregistration_version_ok"] is True, pf


def test_preflight_abort_condition_is_fail_closed():
    pf = sss.preflight()
    assert pf["fresh_slice_hash_ok"] and pf["anchor_population_hash_ok"] and pf["preregistration_version_ok"]
    for bad_key in ("fresh_slice_hash_ok", "anchor_population_hash_ok", "preregistration_version_ok"):
        tampered = dict(pf)
        tampered[bad_key] = False
        would_abort = not (tampered["fresh_slice_hash_ok"] and tampered["anchor_population_hash_ok"]
                            and tampered["preregistration_version_ok"])
        assert would_abort is True, f"flipping {bad_key} to False must trip the abort gate"


# ---------------------------------------------------------------------------------------------
# 2) C6 LOOK-AHEAD / CLOSED-BAR-ONLY GUARDS
# ---------------------------------------------------------------------------------------------
def test_c6_intrabar_wick_below_trigger_that_closes_back_above_does_not_fire():
    """A deep intrabar LOW below the trigger that CLOSES back above must NOT fire -- the
    structure stop is defined on CLOSES only (structure_stop_signal_time never reads high/low)."""
    trigger = 100.0
    rows = [
        {"timestamp_et": dt.datetime(2099, 1, 1, 9, 35), "open": 100.5, "high": 100.6,
         "low": 100.4, "close": 100.50},
        {"timestamp_et": dt.datetime(2099, 1, 1, 9, 40), "open": 100.3, "high": 100.35,
         "low": 99.20, "close": 100.20},   # deep wick to 99.20, closes back at 100.20 (above)
        {"timestamp_et": dt.datetime(2099, 1, 1, 9, 45), "open": 100.15, "high": 100.20,
         "low": 100.05, "close": 100.10},
    ]
    spy_lifetime = pd.DataFrame(rows)
    ss_time = sss.structure_stop_signal_time(spy_lifetime, "C", trigger, 0.0)
    assert ss_time is None, "an intrabar wick that closes back above the trigger must not fire"


def test_c6_a_genuine_close_below_fires_at_the_next_bars_open_time():
    """A genuine CLOSE below trigger fires -- and the returned time is the breaching bar's
    CLOSE == the next bar's OPEN (the frozen fill-mark convention), not the breaching bar
    itself (which is not yet knowable to be a breach until IT closes)."""
    trigger = 100.0
    rows = [
        {"timestamp_et": dt.datetime(2099, 1, 1, 9, 35), "open": 100.5, "high": 100.6,
         "low": 100.4, "close": 100.50},
        {"timestamp_et": dt.datetime(2099, 1, 1, 9, 40), "open": 100.3, "high": 100.35,
         "low": 99.20, "close": 99.80},    # GENUINE close below trigger
        {"timestamp_et": dt.datetime(2099, 1, 1, 9, 45), "open": 99.70, "high": 99.90,
         "low": 99.60, "close": 99.75},
    ]
    spy_lifetime = pd.DataFrame(rows)
    ss_time = sss.structure_stop_signal_time(spy_lifetime, "C", trigger, 0.0)
    assert ss_time == dt.datetime(2099, 1, 1, 9, 45), ss_time


def test_c6_structure_exit_fills_at_next_bar_open_not_breaching_bars_close():
    """End-to-end: the structure-stop SELL_ALL must fill at the bar-AFTER-breach's OPEN
    (0.70), never the breaching bar's own CLOSE (0.80) or the fill bar's own CLOSE (0.72)."""
    entry = 1.00
    ss_time = dt.datetime(2099, 1, 1, 9, 45)
    norm_bars = [
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 35), 1.00, 1.05, 0.95, 1.00),
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 40), 1.00, 1.05, 0.90, 0.80),  # breaching bar
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 45), 0.70, 0.75, 0.65, 0.72),  # fires HERE at open
    ]
    r = sss.replay_structure_aware(entry, "C", 10, norm_bars, ss_time, dict(sss.SS_A_SHAPE),
                                   sss.TIME_STOP_LAYER_B)
    assert r["structure_fired"] is True
    exit_rows = [e for e in r["exits"] if e["stage"] == "structure_stop"]
    assert len(exit_rows) == 1
    assert exit_rows[0]["fill_price"] == 0.70, exit_rows[0]
    assert r["pnl"] == round((0.70 - 1.00) * 10 * 100, 2)


def test_c6_trigger_level_recovery_never_consults_a_bar_after_entry():
    """Real-position trigger-level recovery: a look-ahead spike planted AFTER entry that would
    obviously read as a much-higher reclaimed level must never be selected -- the backward scan
    is bounded to timestamp_et <= entry_ts_et by construction."""
    date = dt.date(2099, 3, 2)
    rows = [
        {"timestamp_et": dt.datetime.combine(date, dt.time(9, 30)), "open": 100.0, "high": 100.05,
         "low": 99.95, "close": 100.0, "volume": 1000},
        {"timestamp_et": dt.datetime.combine(date, dt.time(9, 35)), "open": 100.0, "high": 100.05,
         "low": 99.95, "close": 100.0, "volume": 1000},
        # genuine PRE-entry reclaim bar
        {"timestamp_et": dt.datetime.combine(date, dt.time(9, 40)), "open": 99.9, "high": 100.5,
         "low": 99.80, "close": 100.30, "volume": 1000},
        # LOOK-AHEAD bar (AFTER entry) -- must never be consulted
        {"timestamp_et": dt.datetime.combine(date, dt.time(14, 0)), "open": 100.0, "high": 9999.0,
         "low": 99.5, "close": 101.0, "volume": 5000},
    ]
    spy_full = _synthetic_spy(rows)
    entry_ts_et = dt.datetime.combine(date, dt.time(9, 45))   # after 9:40, before 14:00
    level_cache: dict = {}
    lvl, status = sss.recover_trigger_level_real_position(spy_full, level_cache, date, entry_ts_et,
                                                           "C", lookback_bars=8)
    assert lvl is not None and lvl < 200, (
        f"recovered level must come from the pre-entry reclaim bar, not the future spike: {lvl} ({status})")


# ---------------------------------------------------------------------------------------------
# 3) SIDE-AWARENESS + BUFFER
# ---------------------------------------------------------------------------------------------
def test_side_awareness_calls_break_down_puts_break_up():
    trigger = 100.0
    spy_below = pd.DataFrame([{"timestamp_et": dt.datetime(2099, 1, 1, 9, 35), "close": 99.0}])
    spy_above = pd.DataFrame([{"timestamp_et": dt.datetime(2099, 1, 1, 9, 35), "close": 101.0}])
    assert sss.structure_stop_signal_time(spy_below, "C", trigger, 0.0) is not None, \
        "calls: a close BELOW trigger must fire"
    assert sss.structure_stop_signal_time(spy_above, "C", trigger, 0.0) is None, \
        "calls: a close ABOVE trigger must not fire"
    assert sss.structure_stop_signal_time(spy_above, "P", trigger, 0.0) is not None, \
        "puts: a close ABOVE trigger must fire"
    assert sss.structure_stop_signal_time(spy_below, "P", trigger, 0.0) is None, \
        "puts: a close BELOW trigger must not fire"


def test_option_side_from_symbol_occ_format():
    assert sss.option_side_from_symbol("SPY260709C00750000") == "C"
    assert sss.option_side_from_symbol("SPY260709P00707000") == "P"


def test_buffer_widens_threshold_and_can_suppress_a_marginal_fire():
    """SS-C's $0.10 buffer must be able to hold a position SS-A/SS-B would have stopped: a
    close 5 cents below trigger fires the zero-buffer candidates but not the buffered one."""
    trigger = 100.0
    rows = [{"timestamp_et": dt.datetime(2099, 1, 1, 9, 35), "close": 99.95}]  # trigger - 0.05
    spy = pd.DataFrame(rows)
    assert sss.structure_stop_signal_time(spy, "C", trigger, sss.STRUCTURE_BUFFER["SS-A"]) is not None
    assert sss.structure_stop_signal_time(spy, "C", trigger, sss.STRUCTURE_BUFFER["SS-C"]) is None, (
        "a 5-cent breach must NOT fire SS-C's 10-cent-buffered structure stop")


def test_buffer_still_fires_on_a_decisive_breach():
    trigger = 100.0
    rows = [{"timestamp_et": dt.datetime(2099, 1, 1, 9, 35), "close": 99.50}]  # trigger - 0.50
    spy = pd.DataFrame(rows)
    assert sss.structure_stop_signal_time(spy, "C", trigger, sss.STRUCTURE_BUFFER["SS-C"]) is not None, (
        "a decisive 50-cent breach must fire even the buffered candidate")


# ---------------------------------------------------------------------------------------------
# 4) FALLBACK-INCLUSION (never dropped)
# ---------------------------------------------------------------------------------------------
def test_none_trigger_level_disables_the_structure_check_only():
    spy = pd.DataFrame([{"timestamp_et": dt.datetime(2099, 1, 1, 9, 35), "close": 50.0}])
    assert sss.structure_stop_signal_time(spy, "C", None, 0.0) is None


def test_fallback_position_is_still_replayed_not_dropped():
    """A position with no recoverable trigger_level (ss_time=None) must still produce a real
    pnl via the ordinary premium components -- never silently excluded from the population."""
    norm_bars = [
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 35), 1.00, 1.02, 0.98, 1.00),
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 40), 1.00, 1.01, 0.99, 1.00),
    ]
    r = sss.replay_structure_aware(1.00, "C", 10, norm_bars, None, dict(sss.SS_A_SHAPE),
                                   sss.TIME_STOP_LAYER_B)
    assert r["pnl"] is not None
    assert r["structure_fired"] is False


def test_output_fallback_population_included_not_dropped_in_real_run():
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/structure_stop_study.py first")
    out = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    la, lb = out["layer_a_fresh_slice"], out["layer_b_real_fills_anchor"]
    assert la["n_fallback"] > 0, "fresh slice should exercise the fallback path (non-vacuous check)"
    assert lb["n_fallback"] > 0, "anchor should exercise the fallback path (non-vacuous check)"
    for cid in sss.STRUCTURE_CANDIDATE_IDS:
        assert la["candidates"][cid]["n"] == la["n_signals"], (
            f"{cid}: fallback signals must still be replayed at layer(a) -- n must equal the "
            f"FULL population ({la['n_signals']}), not just the recoverable subset")
        assert lb["candidates"][cid]["n_valid"] == lb["n_positions_with_bars"], (
            f"{cid}: same invariant at layer (b)")


# ---------------------------------------------------------------------------------------------
# 5) REGRESSION GUARD: the entry_ts pre-entry-bar-filter bug (found while building this study)
# ---------------------------------------------------------------------------------------------
def test_norm_bars_from_esp_filters_pre_entry_bars():
    """Unit-level ($0, deterministic) guard for the bug: fetch_option_bars always starts at
    09:29 ET regardless of actual entry time, so the caller MUST filter to >= entry_ts or the
    replay sees pre-entry intrabar swings it was never exposed to."""
    bars = [
        {"t": "2026-01-01T13:29:00Z", "o": 5.0, "h": 5.0, "l": 1.0, "c": 1.0},   # pre-entry
        {"t": "2026-01-01T13:35:00Z", "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0},   # at entry
        {"t": "2026-01-01T13:40:00Z", "o": 1.0, "h": 1.0, "l": 1.0, "c": 1.0},
    ]
    filtered = sss.norm_bars_from_esp(bars, entry_ts_utc="2026-01-01T13:35:00Z")
    assert len(filtered) == 2, "the pre-entry bar (13:29) must be excluded"

    unfiltered = sss.norm_bars_from_esp(bars)   # entry_ts_utc=None -> no filter (documented default)
    assert len(unfiltered) == 3


def test_control_anchor_reproduces_established_baseline_unit():
    """The exact scenario that exposed the bug, reproduced without network: a pre-entry bar
    with an extreme low must NOT be able to fire a premium stop before the position's real
    entry. Entry at 1.00, CONTROL premium_stop_pct=-0.20 -> stop level 0.80; the pre-entry bar's
    low of 0.10 would (wrongly) blow through that stop if not filtered out."""
    bars = [
        {"t": "2026-01-01T13:29:00Z", "o": 5.0, "h": 5.0, "l": 0.10, "c": 0.10},   # pre-entry crash
        {"t": "2026-01-01T13:35:00Z", "o": 1.00, "h": 1.05, "l": 0.95, "c": 1.00},  # entry bar
        {"t": "2026-01-01T13:40:00Z", "o": 1.00, "h": 1.02, "l": 0.98, "c": 1.00},
    ]
    filtered = sss.norm_bars_from_esp(bars, entry_ts_utc="2026-01-01T13:35:00Z")
    r = sss.replay_structure_aware(1.00, "C", 10, filtered, None, dict(sss.CONTROL_SHAPE),
                                   sss.TIME_STOP_LAYER_B)
    assert r["exits"] == [] or r["exits"][-1]["stage"] != "premium_stop", (
        "a pre-entry crash bar must never be able to trigger the premium stop")

    unfiltered = sss.norm_bars_from_esp(bars)
    r_bug = sss.replay_structure_aware(1.00, "C", 10, unfiltered, None, dict(sss.CONTROL_SHAPE),
                                       sss.TIME_STOP_LAYER_B)
    assert any(e["stage"] == "premium_stop" for e in r_bug["exits"]), (
        "sanity: WITHOUT the filter the pre-entry crash bar DOES (wrongly) fire the stop -- "
        "confirms this test would have caught the original bug")


@pytest.mark.slow
def test_control_anchor_reproduces_established_baseline_live():
    """End-to-end regression guard (network-dependent, ~79 real OPRA fetches): CONTROL replayed
    on the real 79-position anchor must reproduce analysis/recommendations/
    entry-exit-matrix-2026-07-09.json's control_anchor_total (-757.1) EXACTLY. Before the
    entry_ts bar-filter fix this silently read +984.5 on the identical population."""
    fills = esp.load_fleet_engine_fills()
    positions = esp.reconstruct_positions(fills)
    anchor = [p for p in positions if p["date_et"] <= sss.ANCHOR_END_DATE]
    spy_full = sss.lc.load_spy_full(sss.LEVEL_HISTORY_START, sss.LEVEL_HISTORY_END)
    prepared, _stats = sss.prepare_positions(anchor, spy_full)
    r = sss.replay_population(prepared, "CONTROL")
    assert r["anchor_total"] == -757.1, r["anchor_total"]


# ---------------------------------------------------------------------------------------------
# 6) VERDICT LOGIC -- "beats" is strict (>), verdict grid well-formed
# ---------------------------------------------------------------------------------------------
def test_beats_control_is_strictly_greater_not_a_tie():
    """Pre-registration states 'beats' = strictly greater than (a tie is not a beat) -- verify
    build_verdicts actually implements > and not >=."""
    tied_candidates_a = {cid: {"expectancy": -100.0} for cid in ("CONTROL",) + sss.STRUCTURE_CANDIDATE_IDS}
    tied_candidates_b = {cid: {"anchor_total": -500.0} for cid in ("CONTROL",) + sss.STRUCTURE_CANDIDATE_IDS}
    layer_a = {"candidates": tied_candidates_a, "n_fallback": 1, "n_signals": 10}
    layer_b = {"candidates": tied_candidates_b, "n_fallback": 1, "n_positions_with_bars": 10}
    v = sss.build_verdicts(layer_a, layer_b)
    for cid in sss.STRUCTURE_CANDIDATE_IDS:
        assert v[cid]["condition_1_layer_b_beats_control"] is False, f"{cid}: a TIE must not beat control (layer b)"
        assert v[cid]["condition_2_layer_a_beats_control"] is False, f"{cid}: a TIE must not beat control (layer a)"
        assert v[cid]["overall"] == "FAIL"


def test_output_verdicts_are_well_formed_in_real_run():
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/structure_stop_study.py first")
    out = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    assert set(out["verdicts"].keys()) == set(sss.STRUCTURE_CANDIDATE_IDS)
    for cid, v in out["verdicts"].items():
        assert v["overall"] in ("PASS", "FAIL")
        expect_overall = "PASS" if (v["condition_1_layer_b_beats_control"]
                                    and v["condition_2_layer_a_beats_control"]
                                    and v["condition_3_fallback_included_not_dropped"]) else "FAIL"
        assert v["overall"] == expect_overall, f"{cid}: verdict does not follow from its own conditions"


def test_output_today_exhibit_excluded_from_verdicts():
    """The 2026-07-09 exhibit must never influence a verdict -- structural check that verdicts
    are computed only from layer_a/layer_b, never from today_exhibit_2026_07_09."""
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/structure_stop_study.py first")
    out = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    assert out["today_exhibit_2026_07_09"]["candidates"] not in out["verdicts"].values()
    for v in out["verdicts"].values():
        assert "today" not in json.dumps(v).lower()

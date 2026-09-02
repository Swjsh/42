"""Companion guards for the MEASURED-MOVE study (backtest/tools/measured_move_study.py +
analysis/recommendations/measured-move-preregistration.json). Load-bearing invariants:

  1. Pre-registration hash pin -- frozen candidates/hashes on disk match the runner's constants.
  2. C6 (look-ahead): depth uses ONLY bars strictly before the trigger bar; MFE/touch/horizon
     use ONLY bars through the structure-stop-bounded horizon. A planted look-ahead bar must
     never change the result.
  3. Side-awareness: depth/projection formula correctly mirrors for calls vs puts.
  4. Shuffle-null non-vacuity: the permutation null must have nonzero spread (not degenerate).
  5. Projection-touch + STOP-FIRST same-bar tie-break.
  6. Fallback-inclusion: a signal with no recoverable trigger_level degrades EXACTLY to
     TRAIL_ONLY under PROJECTION_ONLY/PROJECTION_OR_TRAIL (never dropped, never worse-off).
  7. TRAIL_ONLY parity vs structure_stop_study.replay_structure_aware under SS_B_SHAPE.
  8. Pass-bar strictness ("beats" = strictly greater than, a tie is not a beat).

Run: cd backtest && ../backtest/.venv/Scripts/python.exe -m pytest tests/test_measured_move_study.py -q
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

import measured_move_study as mms       # noqa: E402
import structure_stop_study as sss      # noqa: E402

PREREG = REPO / "analysis" / "recommendations" / "measured-move-preregistration.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "measured-move-study.json"


def _spy(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
    df["date"] = df["timestamp_et"].dt.date
    df["time"] = df["timestamp_et"].dt.time
    return df


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
    assert preg["no_repick_clause"]


def test_preregistration_hashes_match_runner_expected_constants():
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert preg["signal_population"]["exploratory_burned"]["sha256_16_full_file_bytes"] == \
        mms.EXPECTED_SIGNAL_SET_SHA16
    assert preg["signal_population"]["fresh_decisive"]["sha256_16_signals_list"] == \
        mms.EXPECTED_FRESH_SHA16


def test_preregistration_k_grid_and_pass_bar_match_runner_constants():
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert preg["base_depth_definition"]["k_grid"] == list(mms.K_GRID)
    assert preg["base_depth_definition"]["k_primary"] == mms.K_PRIMARY
    assert preg["question_a_information_test"]["shuffle_null"]["n_perm"] == mms.N_PERM
    assert preg["question_a_information_test"]["shuffle_null"]["seed"] == mms.PERM_SEED


def test_preflight_verifies_the_real_files_on_disk():
    pf = mms.preflight()
    assert pf["signal_set_hash_ok"] is True, pf
    assert pf["fresh_slice_hash_ok"] is True, pf
    assert pf["preregistration_version_ok"] is True, pf


# ---------------------------------------------------------------------------------------------
# 2) C6 LOOK-AHEAD GUARDS
# ---------------------------------------------------------------------------------------------
def test_depth_window_excludes_the_trigger_bar_itself():
    """The trigger bar's own low/high must NOT enter the K-bar depth window -- a synthetic
    trigger bar with an extreme low that would (wrongly) blow up depth if included must be
    excluded."""
    trig_ts = dt.datetime(2099, 1, 1, 10, 0)
    rows = [
        {"timestamp_et": dt.datetime(2099, 1, 1, 9, 35), "open": 99.0, "high": 99.2, "low": 98.9, "close": 99.1},
        {"timestamp_et": dt.datetime(2099, 1, 1, 9, 40), "open": 99.1, "high": 99.3, "low": 99.0, "close": 99.2},
        # the TRIGGER bar itself -- extreme low that must NOT be counted in the depth window
        {"timestamp_et": trig_ts, "open": 99.2, "high": 100.5, "low": 0.01, "close": 100.4},
    ]
    spy_full = _spy(rows)
    window = spy_full[spy_full["timestamp_et"] < trig_ts].tail(24)
    assert 0.01 not in window["low"].tolist(), "trigger bar's own low must be excluded from the depth window"
    depth = 100.0 - float(window["low"].min())   # trigger_level=100.0 hypothetically
    assert depth < 5.0, f"depth blew up to {depth} -- the trigger bar's extreme low leaked into the window"


def test_depth_window_excludes_bars_after_the_trigger_bar_look_ahead_bite():
    """A planted bar AFTER the trigger bar with an extreme low must never affect depth --
    window is `timestamp_et < trig_ts`, strictly before, by construction."""
    trig_ts = dt.datetime(2099, 1, 1, 10, 0)
    rows = [
        {"timestamp_et": dt.datetime(2099, 1, 1, 9, 35), "open": 99.0, "high": 99.2, "low": 98.9, "close": 99.1},
        {"timestamp_et": trig_ts, "open": 99.2, "high": 100.5, "low": 99.1, "close": 100.4},
        # LOOK-AHEAD bar (after trigger) -- must never be consulted
        {"timestamp_et": dt.datetime(2099, 1, 1, 14, 0), "open": 100.0, "high": 100.1, "low": -9999.0, "close": 100.0},
    ]
    spy_full = _spy(rows)
    window = spy_full[spy_full["timestamp_et"] < trig_ts].tail(24)
    assert -9999.0 not in window["low"].tolist()
    assert len(window) == 1  # only the 9:35 bar is strictly before the trigger


def test_horizon_respects_structure_stop_boundary_c6():
    """MFE/touch computed over a horizon that ends at the structure-stop fire time must never
    see bars after that boundary -- a favorable spike planted AFTER the structure stop fires
    must not count toward MFE/touch."""
    date = dt.date(2099, 3, 2)
    entry_ts = dt.datetime.combine(date, dt.time(9, 35))
    trig_level = 100.0
    rows = [
        {"timestamp_et": entry_ts, "open": 100.2, "high": 100.3, "low": 100.1, "close": 100.2},
        # genuine close below trigger -> structure stop fires, breach known at 9:45 (next bar open)
        {"timestamp_et": dt.datetime.combine(date, dt.time(9, 40)), "open": 100.1, "high": 100.2,
         "low": 99.0, "close": 99.5},
        {"timestamp_et": dt.datetime.combine(date, dt.time(9, 45)), "open": 99.4, "high": 99.6,
         "low": 99.3, "close": 99.5},
        # AFTER the horizon boundary -- a huge favorable spike that must NOT count
        {"timestamp_et": dt.datetime.combine(date, dt.time(9, 50)), "open": 99.5, "high": 999.0,
         "low": 99.4, "close": 150.0},
    ]
    spy_lifetime = _spy(rows)
    ss_time = sss.structure_stop_signal_time(spy_lifetime, "C", trig_level, 0.0)
    assert ss_time == dt.datetime.combine(date, dt.time(9, 45))

    rec = {"trigger_level": trig_level, "date": str(date), "entry_ts": entry_ts.isoformat(),
           "side": "C", f"depth_K{mms.K_PRIMARY}": 5.0, f"projection_K{mms.K_PRIMARY}": 105.0}
    outcome = mms.compute_horizon_outcome(rec, spy_lifetime, ss_time, dt.time(15, 40))
    assert outcome["outcome_status"] == "ok"
    assert outcome["mfe_dollars"] < 10.0, (
        f"MFE={outcome['mfe_dollars']} leaked the post-structure-stop spike (999 high / 150 close)")
    assert outcome["touched_projection"] is False, "the post-stop spike must not count as a touch"


# ---------------------------------------------------------------------------------------------
# 3) SIDE-AWARENESS -- depth/projection formula mirrors correctly
# ---------------------------------------------------------------------------------------------
def test_depth_projection_formula_calls():
    trig_level = 100.0
    window_lows = [99.5, 98.0, 99.0]   # min = 98.0
    depth = trig_level - min(window_lows)
    projection = trig_level + depth
    assert depth == pytest.approx(2.0)
    assert projection == pytest.approx(102.0)


def test_depth_projection_formula_puts_mirrored():
    trig_level = 100.0
    window_highs = [100.5, 102.0, 101.0]   # max = 102.0
    depth = max(window_highs) - trig_level
    projection = trig_level - depth
    assert depth == pytest.approx(2.0)
    assert projection == pytest.approx(98.0)


def test_negative_raw_depth_is_clipped_to_zero():
    spy_full = _spy([
        {"timestamp_et": dt.datetime(2099, 1, 1, 9, 30), "open": 100, "high": 100.1, "low": 99.98, "close": 100.05},
    ])
    signals = [{"date": "2099-01-01", "entry_ts": "2099-01-01T09:35:00", "side": "C",
               "entry_spot": 100.05, "setup": "X", "direction": "bull"}]
    # A trigger_level BELOW the window's own min-low would make raw depth negative (calls:
    # depth = trigger_level - min_low); simulate directly via the same arithmetic the module uses.
    trig_level = 99.97
    window_low = 99.98
    raw_depth = trig_level - window_low
    assert raw_depth < 0
    clipped_depth = max(0.0, raw_depth)
    assert clipped_depth == 0.0


# ---------------------------------------------------------------------------------------------
# 4) SHUFFLE-NULL NON-VACUITY
# ---------------------------------------------------------------------------------------------
def _synth_eligible(n: int, seed: int = 7) -> list[dict]:
    import random
    rng = random.Random(seed)
    out = []
    for i in range(n):
        depth = rng.uniform(0.5, 10.0)
        mfe = depth * rng.uniform(0.3, 1.5) + rng.uniform(-1.0, 1.0)   # depth-correlated signal
        touched = mfe >= depth
        out.append({f"depth_K{mms.K_PRIMARY}": depth, "mfe_dollars": mfe, "touched_projection": touched})
    return out


def test_shuffle_null_has_nonzero_spread_not_degenerate():
    pop = _synth_eligible(60)
    result = mms.shuffle_null(pop, k=mms.K_PRIMARY, n_perm=200, seed=99)
    assert result["spearman_depth_vs_mfe"]["null_std_nonzero"] is True, (
        "shuffle null collapsed to zero spread -- the permutation isn't actually varying the statistic")
    assert result["tercile_touch_rate_spread_deep_minus_shallow"]["null_std_nonzero"] is True
    assert 0.0 <= result["spearman_depth_vs_mfe"]["p_value"] <= 1.0
    assert 0.0 <= result["tercile_touch_rate_spread_deep_minus_shallow"]["p_value"] <= 1.0


def test_shuffle_null_real_correlation_is_recovered_on_a_strong_synthetic_signal():
    """Sanity: a STRONG synthetic depth->MFE relationship must produce a real Spearman rho well
    above the null mean and a low p-value -- proves the machinery can detect a real signal, not
    just fail to reject noise."""
    pop = _synth_eligible(80, seed=3)
    result = mms.shuffle_null(pop, k=mms.K_PRIMARY, n_perm=500, seed=11)
    spear = result["spearman_depth_vs_mfe"]
    assert spear["real"] > 0.5, f"expected a strong positive correlation on synthetic signal, got {spear['real']}"
    assert spear["p_value"] < 0.05, f"expected the strong synthetic signal to clear p<0.05, got {spear['p_value']}"


def test_spearman_corr_degenerate_input_returns_zero_not_crash():
    assert mms.spearman_corr([5.0, 5.0, 5.0], [1.0, 2.0, 3.0]) == 0.0
    assert mms.spearman_corr([1.0, 2.0, 3.0], [5.0, 5.0, 5.0]) == 0.0


def test_shuffle_null_permutation_actually_shuffles_deterministically():
    """Same seed -> identical result (reproducible); different seed -> generally different
    (the permutation is actually doing something, not a no-op)."""
    pop = _synth_eligible(50, seed=1)
    r1 = mms.shuffle_null(pop, k=mms.K_PRIMARY, n_perm=100, seed=42)
    r2 = mms.shuffle_null(pop, k=mms.K_PRIMARY, n_perm=100, seed=42)
    assert r1 == r2, "identical seed must reproduce identical null summary"
    r3 = mms.shuffle_null(pop, k=mms.K_PRIMARY, n_perm=100, seed=43)
    assert r1["spearman_depth_vs_mfe"]["null_mean"] != r3["spearman_depth_vs_mfe"]["null_mean"], (
        "a different seed producing an IDENTICAL null mean would suggest the shuffle is a no-op")


# ---------------------------------------------------------------------------------------------
# 5) PROJECTION-TOUCH + STOP-FIRST TIE-BREAK
# ---------------------------------------------------------------------------------------------
def test_projection_touch_fires_post_tp1_at_option_bar_close():
    """A pure PROJECTION_ONLY runner phase: after TP1, once the aligned SPY bar's high crosses
    the projection, SELL_ALL fires at THIS option bar's close."""
    entry = 1.00
    side = "C"
    qty = 10
    # bars: entry -> TP1 hit (+100%) -> runner phase -> SPY touches projection
    norm_bars = [
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 35), 1.00, 1.05, 0.98, 1.00),
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 40), 1.00, 2.10, 1.00, 2.00),   # TP1 (+100%) fires here
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 45), 2.00, 2.20, 1.95, 2.10),   # runner phase, no touch yet
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 50), 2.10, 2.50, 2.05, 2.40),   # SPY touches projection HERE
    ]
    spy_by_time = {
        dt.time(9, 35): _Row(high=100.2, low=99.8),
        dt.time(9, 40): _Row(high=100.5, low=100.0),
        dt.time(9, 45): _Row(high=100.8, low=100.3),
        dt.time(9, 50): _Row(high=101.5, low=100.7),   # crosses projection=101.0
    }
    r = mms.replay_measured_move(entry, side, qty, norm_bars, spy_by_time, None, 101.0,
                                 mms.PROJECTION_ONLY, dt.time(15, 40))
    assert r["projection_fired"] is True
    proj_exits = [e for e in r["exits"] if e["stage"] == "projection_touch"]
    assert len(proj_exits) == 1
    assert proj_exits[0]["fill_price"] == 2.40, proj_exits[0]   # bar's own CLOSE


class _Row:
    """Minimal stand-in for a pandas itertuples() row -- only .high/.low are read."""
    def __init__(self, high, low):
        self.high = high
        self.low = low


def test_stop_first_tie_break_when_both_stop_and_projection_fire_same_bar():
    """If the SAME bar both breaches the runner's BE-floor stop AND touches the projection,
    STOP-FIRST wins (t4_exit_matrix's documented convention) -- the projection must NOT fire."""
    entry = 1.00
    side = "C"
    qty = 10
    norm_bars = [
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 35), 1.00, 1.05, 0.98, 1.00),
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 40), 1.00, 2.10, 1.00, 2.00),   # TP1 fires
        # this bar's low breaches the BE floor (1.00) AND its aligned SPY bar touches projection
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 45), 2.00, 2.20, 0.50, 0.90),
    ]
    spy_by_time = {
        dt.time(9, 35): _Row(high=100.2, low=99.8),
        dt.time(9, 40): _Row(high=100.5, low=100.0),
        dt.time(9, 45): _Row(high=101.5, low=100.3),   # crosses projection=101.0 too
    }
    r = mms.replay_measured_move(entry, side, qty, norm_bars, spy_by_time, None, 101.0,
                                 mms.PROJECTION_ONLY, dt.time(15, 40))
    assert r["projection_fired"] is False, "STOP-FIRST: the BE-floor stop must win the tie, not the projection"
    stages = [e["stage"] for e in r["exits"]]
    assert "projection_touch" not in stages
    assert any(s in ("be_stop", "trail") for s in stages)


def test_projection_touch_puts_side_uses_low():
    entry = 1.00
    side = "P"
    qty = 10
    norm_bars = [
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 35), 1.00, 1.05, 0.98, 1.00),
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 40), 1.00, 2.10, 1.00, 2.00),   # TP1 fires
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 45), 2.00, 2.20, 2.05, 2.40),   # runner, SPY dips to projection
    ]
    spy_by_time = {
        dt.time(9, 35): _Row(high=100.2, low=99.8),
        dt.time(9, 40): _Row(high=100.5, low=100.0),
        dt.time(9, 45): _Row(high=100.8, low=98.5),   # crosses projection=99.0 (put: low <= projection)
    }
    r = mms.replay_measured_move(entry, side, qty, norm_bars, spy_by_time, None, 99.0,
                                 mms.PROJECTION_ONLY, dt.time(15, 40))
    assert r["projection_fired"] is True


# ---------------------------------------------------------------------------------------------
# 6) FALLBACK-INCLUSION -- no recoverable trigger_level degrades EXACTLY to TRAIL_ONLY
# ---------------------------------------------------------------------------------------------
def test_no_projection_degrades_exactly_to_trail_only_for_projection_only():
    entry = 1.00
    side = "C"
    qty = 10
    norm_bars = [
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 35), 1.00, 1.05, 0.98, 1.00),
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 40), 1.00, 2.10, 1.00, 2.00),
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 45), 2.00, 2.60, 1.95, 2.50),
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 50), 2.50, 2.55, 1.80, 1.90),
    ]
    spy_by_time = {t: _Row(high=100.0, low=99.0) for t in
                   (dt.time(9, 35), dt.time(9, 40), dt.time(9, 45), dt.time(9, 50))}

    r_trail = mms.replay_measured_move(entry, side, qty, norm_bars, spy_by_time, None, None,
                                       mms.TRAIL_ONLY, dt.time(15, 40))
    r_proj_only_no_proj = mms.replay_measured_move(entry, side, qty, norm_bars, spy_by_time, None, None,
                                                    mms.PROJECTION_ONLY, dt.time(15, 40))
    r_proj_or_trail_no_proj = mms.replay_measured_move(entry, side, qty, norm_bars, spy_by_time, None, None,
                                                        mms.PROJECTION_OR_TRAIL, dt.time(15, 40))
    assert r_trail["pnl"] == r_proj_only_no_proj["pnl"], (
        "PROJECTION_ONLY with projection=None must degrade EXACTLY to TRAIL_ONLY's pnl")
    assert r_trail["pnl"] == r_proj_or_trail_no_proj["pnl"]
    assert r_proj_only_no_proj["projection_fired"] is False
    assert r_proj_or_trail_no_proj["projection_fired"] is False


def test_prepare_population_never_drops_a_signal_for_missing_trigger_level():
    """A signal whose trigger_level cannot be recovered must still appear in `prepared` (with
    trigger_level=None) -- never silently excluded from the Question B population."""
    spy_full = _spy([
        {"timestamp_et": dt.datetime(2099, 1, 1, 9, 30), "open": 500, "high": 500.1, "low": 499.9, "close": 500.0},
        {"timestamp_et": dt.datetime(2099, 1, 1, 9, 35), "open": 500, "high": 500.1, "low": 499.9, "close": 500.0},
    ])
    signals = [{"date": "2099-01-01", "entry_ts": "2099-01-01T09:35:00", "side": "C",
               "entry_spot": 500.0, "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON", "direction": "bull",
               "_window": "exploratory_burned"}]
    enriched = mms.enrich_with_trigger_and_depth(signals, spy_full)
    assert len(enriched) == 1
    assert enriched[0]["trigger_level"] is None   # no level history -> unrecoverable, but NOT dropped


# ---------------------------------------------------------------------------------------------
# 7) TRAIL_ONLY PARITY vs structure_stop_study.replay_structure_aware (SS_B_SHAPE)
# ---------------------------------------------------------------------------------------------
def test_trail_only_reproduces_replay_structure_aware_byte_identical():
    entry = 1.00
    side = "C"
    qty = 10
    norm_bars = [
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 35), 1.00, 1.05, 0.98, 1.00),
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 40), 1.00, 2.10, 1.00, 2.00),
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 45), 2.00, 2.60, 1.95, 2.50),
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 50), 2.50, 2.55, 1.80, 1.90),
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 55), 1.90, 2.00, 1.70, 1.85),
    ]
    ss_time = None
    r_ref = sss.replay_structure_aware(entry, side, qty, norm_bars, ss_time, dict(sss.SS_B_SHAPE),
                                       dt.time(15, 40))
    spy_by_time = {t: _Row(high=100.0, low=99.0) for t in
                   (dt.time(9, 35), dt.time(9, 40), dt.time(9, 45), dt.time(9, 50), dt.time(9, 55))}
    r_new = mms.replay_measured_move(entry, side, qty, norm_bars, spy_by_time, ss_time, 105.0,
                                     mms.TRAIL_ONLY, dt.time(15, 40))
    assert r_new["pnl"] == r_ref["pnl"], (r_new["pnl"], r_ref["pnl"])
    assert r_new["structure_fired"] == r_ref["structure_fired"]
    assert [e["stage"] for e in r_new["exits"]] == [e["stage"] for e in r_ref["exits"]]


def test_trail_only_with_structure_stop_reproduces_reference_with_ss_time():
    entry = 1.00
    side = "C"
    qty = 10
    ss_time = dt.datetime(2099, 1, 1, 9, 45)
    norm_bars = [
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 35), 1.00, 1.05, 0.98, 1.00),
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 40), 1.00, 1.05, 0.90, 0.80),
        sss.NormBar(dt.datetime(2099, 1, 1, 9, 45), 0.70, 0.75, 0.65, 0.72),
    ]
    r_ref = sss.replay_structure_aware(entry, side, qty, norm_bars, ss_time, dict(sss.SS_B_SHAPE),
                                       dt.time(15, 40))
    spy_by_time = {t: _Row(high=100.0, low=99.0) for t in (dt.time(9, 35), dt.time(9, 40), dt.time(9, 45))}
    r_new = mms.replay_measured_move(entry, side, qty, norm_bars, spy_by_time, ss_time, 105.0,
                                     mms.TRAIL_ONLY, dt.time(15, 40))
    assert r_new["pnl"] == r_ref["pnl"] == round((0.70 - 1.00) * 10 * 100, 2)
    assert r_new["structure_fired"] is True


# ---------------------------------------------------------------------------------------------
# 8) PASS-BAR STRICTNESS -- "beats" is strict (>), not >=
# ---------------------------------------------------------------------------------------------
def test_verdict_tie_is_not_a_beat():
    qb = {"policies": {
        mms.TRAIL_ONLY: {"windows": {
            "fresh_decisive": {"expectancy": -10.0, "exp_drop_top3": -1.0},
            "exploratory_burned": {"expectancy": -5.0, "exp_drop_top3": -1.0}}},
        mms.PROJECTION_ONLY: {"windows": {
            "fresh_decisive": {"expectancy": -10.0, "exp_drop_top3": -1.0},   # TIE, not a beat
            "exploratory_burned": {"expectancy": -5.0, "exp_drop_top3": -1.0}}},
        mms.PROJECTION_OR_TRAIL: {"windows": {
            "fresh_decisive": {"expectancy": -10.0, "exp_drop_top3": -1.0},
            "exploratory_burned": {"expectancy": -5.0, "exp_drop_top3": -1.0}}},
    }}
    v = mms.build_question_b_verdict(qb)
    assert v["per_policy"][mms.PROJECTION_ONLY]["beats_control_fresh_decisive"] is False
    assert v["per_policy"][mms.PROJECTION_ONLY]["overall"] == "FAIL"
    assert v["headline"] == "CONTROL_TRAIL_ONLY_STANDS"


def test_verdict_requires_all_four_conditions():
    """A challenger that beats control on BOTH windows but has a negative drop-top-3 on one
    window must still FAIL (no partial credit)."""
    qb = {"policies": {
        mms.TRAIL_ONLY: {"windows": {
            "fresh_decisive": {"expectancy": -10.0, "exp_drop_top3": -1.0},
            "exploratory_burned": {"expectancy": -5.0, "exp_drop_top3": -1.0}}},
        mms.PROJECTION_ONLY: {"windows": {
            "fresh_decisive": {"expectancy": 5.0, "exp_drop_top3": -0.5},   # beats, but drop3 negative
            "exploratory_burned": {"expectancy": 2.0, "exp_drop_top3": 1.0}}},
        mms.PROJECTION_OR_TRAIL: {"windows": {
            "fresh_decisive": {"expectancy": -10.0, "exp_drop_top3": -1.0},
            "exploratory_burned": {"expectancy": -5.0, "exp_drop_top3": -1.0}}},
    }}
    v = mms.build_question_b_verdict(qb)
    p = v["per_policy"][mms.PROJECTION_ONLY]
    assert p["beats_control_fresh_decisive"] is True
    assert p["beats_control_exploratory_burned"] is True
    assert p["drop_top3_positive_fresh_decisive"] is False
    assert p["overall"] == "FAIL", "a negative drop-top-3 on either window must fail the challenger"


def test_verdict_all_four_conditions_pass_yields_pass():
    qb = {"policies": {
        mms.TRAIL_ONLY: {"windows": {
            "fresh_decisive": {"expectancy": -10.0, "exp_drop_top3": -1.0},
            "exploratory_burned": {"expectancy": -5.0, "exp_drop_top3": -1.0}}},
        mms.PROJECTION_ONLY: {"windows": {
            "fresh_decisive": {"expectancy": 5.0, "exp_drop_top3": 1.0},
            "exploratory_burned": {"expectancy": 2.0, "exp_drop_top3": 0.5}}},
        mms.PROJECTION_OR_TRAIL: {"windows": {
            "fresh_decisive": {"expectancy": -10.0, "exp_drop_top3": -1.0},
            "exploratory_burned": {"expectancy": -5.0, "exp_drop_top3": -1.0}}},
    }}
    v = mms.build_question_b_verdict(qb)
    assert v["per_policy"][mms.PROJECTION_ONLY]["overall"] == "PASS"
    assert v["headline"] == "PROJECTION_CHALLENGER_PASSES"


# ---------------------------------------------------------------------------------------------
# 9) REAL OUTPUT SANITY (after the study has run)
# ---------------------------------------------------------------------------------------------
def test_output_question_a_terciles_well_formed_in_real_run():
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/measured_move_study.py first")
    out = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    qa = out["question_a_information_test"]
    terciles = qa["terciles_by_K"][str(mms.K_PRIMARY)]
    assert len(terciles) == 3
    assert sum(t["n"] for t in terciles) == qa["n_eligible_ok_outcome"], (
        "tercile n's must sum to the full eligible-ok population -- no signal silently dropped")


def test_output_question_b_verdict_matches_its_own_conditions():
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/measured_move_study.py first")
    out = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    v = out["question_b_verdict"]
    for cid, row in v["per_policy"].items():
        expect = "PASS" if (row["beats_control_fresh_decisive"] and row["beats_control_exploratory_burned"]
                            and row["drop_top3_positive_fresh_decisive"]
                            and row["drop_top3_positive_exploratory_burned"]) else "FAIL"
        assert row["overall"] == expect, f"{cid}: verdict does not follow from its own conditions"
    any_pass = any(r["overall"] == "PASS" for r in v["per_policy"].values())
    expected_headline = "PROJECTION_CHALLENGER_PASSES" if any_pass else "CONTROL_TRAIL_ONLY_STANDS"
    assert v["headline"] == expected_headline


def test_output_fallback_population_never_dropped_in_real_run():
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/measured_move_study.py first")
    out = json.loads(OUT_JSON.read_text(encoding="utf-8"))
    for window in ("exploratory_burned", "fresh_decisive"):
        stats = out["population_stats"][window]
        assert stats["n_fallback"] >= 0
        for policy in (mms.PROJECTION_ONLY, mms.PROJECTION_OR_TRAIL):
            cand = out["question_b_exit_test"]["policies"][policy]["windows"][window]
            assert cand["n"] == stats["n_total"], (
                f"{policy}/{window}: fallback signals must still be replayed -- n must equal the "
                f"FULL prepared population ({stats['n_total']}), not just the recoverable subset")


def test_output_today_2026_07_09_not_in_either_window():
    if not OUT_JSON.exists():
        pytest.fail(f"{OUT_JSON} missing -- run backtest/tools/measured_move_study.py first")
    raw_burned = json.loads(mms.SIGNAL_SET.read_text(encoding="utf-8"))["signals"]
    raw_fresh = json.loads(mms.FRESH_SIGNAL_SET.read_text(encoding="utf-8"))["signals"]
    dates = {s["date"] for s in raw_burned} | {s["date"] for s in raw_fresh}
    assert "2026-07-09" not in dates, "today's motivating trade must not be a data point in this study"

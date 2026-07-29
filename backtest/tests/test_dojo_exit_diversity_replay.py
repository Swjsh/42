"""RED-proof tests for backtest/tools/dojo_exit_diversity_replay.py's win-gate logic.

Spec: markdown/specs/DOJO-AUTONOMOUS-FINETUNE.md ("THE SHIP GATE"). The critical property this
guards: a profile that "wins" only because ONE huge trade rides in its favor (a concentration
artifact -- exactly the C4/C24 failure class, and exactly what
structure-stop-reference-level-2026-07-20.json's REF-ZONE fell into: aggregate PASS but a
sub-window sign flip) must be REJECTED, while a genuine, distributed, multi-day winner that
also holds on a held-out subset must PASS. These tests exercise ONLY the pure
`evaluate_win_gate` function -- no real-cache I/O, no engine_step/sim_executor calls -- so they
run fast and RED-prove the gate math itself, independent of whether any real curriculum day
happens to produce a winning profile tonight.

Also guards the module's HARD FENCE (no broker import) and that CONTROL/RIBBON exit_patch
dicts are pulled from accounts.json verbatim, not hand-copied (a drift class this repo has hit
before, C14).

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_dojo_exit_diversity_replay.py -v
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for _p in (ROOT / "backtest" / "tools", ROOT):
    _ap = str(_p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

import dojo_exit_diversity_replay as ddr  # noqa: E402


# =====================================================================================
# fixtures -- synthetic per-episode data, no dependency on real cache dates
# =====================================================================================
CONTROL_DAY_TOTALS = {
    "2026-06-30": -20.0,
    "2026-07-02": -15.0,
    "2026-07-08": -30.0,
    "2026-07-14": -10.0,
    "2026-07-17": -25.0,
    "2026-07-20": -5.0,
}
CONTROL_TOTAL = sum(CONTROL_DAY_TOTALS.values())  # -105.0
HELD_OUT_DAYS = ["2026-07-14", "2026-07-17", "2026-07-20"]  # control held-out total = -40.0


# =====================================================================================
# condition_3 (concentration) -- the RED-proof this build was explicitly asked for
# =====================================================================================
def test_concentration_only_winner_is_rejected():
    """A profile whose aggregate beats CONTROL ONLY because of a single massive trade must be
    REJECTED (overall != SHIP_CANDIDATE) even though condition_1 (aggregate) and condition_2
    (day-majority -- the profile edges control on every OTHER day too) look fine in isolation.
    This is the exact shape structure-stop-reference-level-2026-07-20.json's REF-ZONE fell into
    (real-fills anchor total +$481.2 vs control -$900.7 -- a PASS on raw aggregate -- but
    rejected for a sub-window sign flip driven by concentration). Uses its own small local
    control fixture (rather than the module-level CONTROL_DAY_TOTALS) so the day-majority
    condition can be made to independently PASS while condition_3 independently FAILS --
    isolating exactly one failure mode per test, per this repo's one-hypothesis-per-test
    debugging discipline."""
    days = ["2026-06-30", "2026-07-02", "2026-07-08", "2026-07-14", "2026-07-17", "2026-07-20"]
    control_day_totals = {d: 40.0 for d in days}
    control_total = sum(control_day_totals.values())  # 240.0
    episodes = [
        {"day": "2026-06-30", "pnl": 45.0},   # edges control (40) on this day
        {"day": "2026-07-02", "pnl": 45.0},
        {"day": "2026-07-08", "pnl": 45.0},
        {"day": "2026-07-14", "pnl": 45.0},
        {"day": "2026-07-17", "pnl": 45.0},
        {"day": "2026-07-20", "pnl": 1000.0},  # the single anchor trade carrying the aggregate
    ]
    result = ddr.evaluate_win_gate(episodes, control_day_totals, control_total, days[-3:])

    assert result["condition_1_beats_aggregate"] is True, "sanity: aggregate genuinely beats control"
    assert result["condition_2_day_majority"] is True, "sanity: profile also edges control on every other day"
    assert result["condition_3_survives_top_trade_drop"] is False, (
        "dropping the $1000 top trade must leave the profile below control's aggregate"
    )
    assert result["overall"] == "CONTROL_HOLDS", (
        f"a single-trade-concentration profile must be REJECTED even with aggregate+day-majority "
        f"passing, got {result['overall']}"
    )


def test_genuine_multi_day_winner_passes():
    """A profile that modestly beats CONTROL on every single day (no one trade dominates),
    wins the day-majority, survives dropping its own best trade, and holds on the held-out
    subset must PASS all 4 conditions."""
    episodes = [
        {"day": "2026-06-30", "pnl": 10.0},   # control -20 -> profile wins by 30
        {"day": "2026-07-02", "pnl": 5.0},    # control -15 -> wins by 20
        {"day": "2026-07-08", "pnl": 8.0},    # control -30 -> wins by 38
        {"day": "2026-07-14", "pnl": 12.0},   # held-out; control -10 -> wins by 22
        {"day": "2026-07-17", "pnl": 6.0},    # held-out; control -25 -> wins by 31
        {"day": "2026-07-20", "pnl": 9.0},    # held-out; control -5 -> wins by 14
    ]
    result = ddr.evaluate_win_gate(episodes, CONTROL_DAY_TOTALS, CONTROL_TOTAL, HELD_OUT_DAYS)

    assert result["condition_1_beats_aggregate"] is True
    assert result["condition_2_day_majority"] is True
    assert result["condition_2_day_wins"] == 6
    assert result["condition_3_survives_top_trade_drop"] is True, (
        "dropping the single best trade (12.0) should still leave 40.0 > control's -105.0"
    )
    assert result["condition_4_holds_on_held_out"] is True, (
        "held-out total 27.0 must beat control's held-out total -40.0"
    )
    assert result["overall"] == "SHIP_CANDIDATE"


def test_day_majority_failure_rejects_even_with_higher_aggregate():
    """A profile can have a higher AGGREGATE total than control while losing on most
    individual days (one huge day carries it) -- condition_2 must independently catch this,
    distinct from condition_3's per-trade concentration check."""
    episodes = [
        {"day": "2026-06-30", "pnl": -100.0},  # loses this day (control -20)
        {"day": "2026-07-02", "pnl": -100.0},  # loses (control -15)
        {"day": "2026-07-08", "pnl": -100.0},  # loses (control -30)
        {"day": "2026-07-14", "pnl": -100.0},  # loses (control -10)
        {"day": "2026-07-17", "pnl": -100.0},  # loses (control -25)
        {"day": "2026-07-20", "pnl": 10000.0},  # wins big on the 6th day, carries the aggregate
    ]
    result = ddr.evaluate_win_gate(episodes, CONTROL_DAY_TOTALS, CONTROL_TOTAL, HELD_OUT_DAYS)
    assert result["condition_1_beats_aggregate"] is True
    assert result["condition_2_day_majority"] is False, "profile loses 5 of 6 days despite winning aggregate"
    assert result["overall"] == "CONTROL_HOLDS"


def test_held_out_failure_rejects_an_in_sample_only_winner():
    """A profile that wins convincingly on the IN-SAMPLE (non-held-out) days but is flat/worse
    on the held-out subset must be REJECTED by condition_4, even if conditions 1-3 pass."""
    episodes = [
        {"day": "2026-06-30", "pnl": 50.0},   # in-sample, big win
        {"day": "2026-07-02", "pnl": 50.0},   # in-sample, big win
        {"day": "2026-07-08", "pnl": 50.0},   # in-sample, big win
        {"day": "2026-07-14", "pnl": -50.0},  # held-out, loses (control -10)
        {"day": "2026-07-17", "pnl": -50.0},  # held-out, loses (control -25)
        {"day": "2026-07-20", "pnl": -50.0},  # held-out, loses (control -5)
    ]
    result = ddr.evaluate_win_gate(episodes, CONTROL_DAY_TOTALS, CONTROL_TOTAL, HELD_OUT_DAYS)
    assert result["condition_1_beats_aggregate"] is True
    assert result["condition_4_holds_on_held_out"] is False, (
        "held-out total -150.0 must NOT beat control's held-out total -40.0"
    )
    assert result["overall"] == "CONTROL_HOLDS"


def test_empty_episodes_never_crashes_and_never_ships():
    """No real-fills episodes for a profile (e.g. every entry landed on a BS-synthetic-only
    day) must resolve to a clean CONTROL_HOLDS, never a crash or a spurious SHIP_CANDIDATE."""
    result = ddr.evaluate_win_gate([], CONTROL_DAY_TOTALS, CONTROL_TOTAL, HELD_OUT_DAYS)
    assert result["overall"] == "CONTROL_HOLDS"
    assert result["profile_total"] == 0.0


# =====================================================================================
# exit-profile provenance -- pulled from accounts.json verbatim, not hand-copied (C14)
# =====================================================================================
def test_exit_profiles_pulled_from_live_accounts_json():
    """Pins the LIVE per-arm exit lanes. Updated 2026-07-29 when BE-FLOOR was added.

    HISTORY: this guard used to assert exactly {CONTROL, RIBBON, ZONE-RIDE} -- the state when
    every fleet arm shared one exit shape apart from a trail-width tweak. J's 2026-07-29
    directive ("all five arms still share one exit shape -- rip it apart") added a genuinely
    distinct fourth lane on risky-1: BE-FLOOR (profit_lock_mode=fixed = a breakeven floor,
    armed PRE-TP1 at +30% MFE, with a REACHABLE tp1 of 0.5 vs the registry's unreachable 1.0).
    The guard's job is unchanged -- prove the study reads the LIVE lanes and that they are
    genuinely different -- so it now pins the new set. If a lane is added/removed, update this
    list deliberately; do not delete the test.
    """
    profiles = ddr._load_exit_profiles()
    assert set(profiles.keys()) == {"CONTROL", "RIBBON", "ZONE-RIDE", "BE-FLOOR"}
    assert profiles["CONTROL"] == {}
    assert profiles["RIBBON"].get("stop_mode") == "structure"
    assert profiles["ZONE-RIDE"].get("trail_pct") == pytest.approx(0.20)
    # ZONE-RIDE must differ from RIBBON only via the trail widening (the one lever that can
    # make ZONE-RIDE diverge from CONTROL for this study's ribbon_ride-only entry population).
    assert profiles["ZONE-RIDE"].get("stop_mode") == profiles["RIBBON"].get("stop_mode")
    assert profiles["ZONE-RIDE"].get("trail_pct") != profiles["RIBBON"].get("trail_pct")
    # BE-FLOOR is the 2026-07-29 challenger lane and must be structurally distinct from the
    # trailing lanes: a FIXED (breakeven) lock armed pre-TP1, not a chandelier post-TP1.
    be = profiles["BE-FLOOR"]
    assert be.get("profit_lock_mode") == "fixed"
    assert be.get("profit_lock_arm_scope") == "full"
    assert be.get("profit_lock_arm_pct") == pytest.approx(0.30)
    assert be.get("tp1_premium_pct") == pytest.approx(0.5), (
        "the whole point is a REACHABLE tp1 -- the registry's 1.0 never fires on 0DTE, which "
        "is why the post_tp1-scoped lock stayed dead on the 2026-07-28 +56% trade")
    assert be.get("profit_lock_mode") != profiles["RIBBON"].get("profit_lock_mode")


# =====================================================================================
# DOJO-EXIT-HARNESS-BUGS bug (1) -- entry-scan scope (2026-07-21 fix)
# =====================================================================================
def test_extract_entries_scoped_to_target_day_only(monkeypatch):
    """load_day_bars() returns the FULL multi-month warmup frame BY DESIGN (its own
    docstring), but the entry-scan CURSOR loop must only walk the TARGET day's own RTH
    bars -- not every RTH bar in the whole returned frame. Pre-fix, a day=2026-06-30 call
    would also invoke engine_step.step() with a cursor dated 2026-06-29 (or earlier), the
    exact "day=2026-06-30 episode carries cursor_et=2026-05-21" defect from the VOID report
    (analysis/dojo/EXIT-DIVERSITY-2026-07-20.md, DOJO-EXIT-HARNESS-BUGS bug 1)."""
    import pandas as pd
    from datetime import datetime as _dt
    from zoneinfo import ZoneInfo

    et = ZoneInfo("America/New_York")

    def _bar(d, hh, mm):
        return {"timestamp": pd.Timestamp(_dt(2026, 6, d, hh, mm), tz=et),
                "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0, "volume": 1000}

    # two days in the SAME returned frame: 06-29 (prior day, warmup-only) + 06-30 (target)
    rows = [_bar(29, 9, 30), _bar(29, 9, 35), _bar(29, 9, 40),
            _bar(30, 9, 30), _bar(30, 9, 35), _bar(30, 9, 40)]
    synthetic_bars = pd.DataFrame(rows)
    monkeypatch.setattr(ddr.engine_step, "load_day_bars", lambda day: synthetic_bars)

    seen_cursor_dates: set[str] = set()

    def _fake_step(day, cursor, bars_df):
        seen_cursor_dates.add(cursor.date().isoformat())
        dec = ddr.engine_step.DojoDecision(
            arm="safe", side=None, verdict="HOLD", bear_score=None, bull_score=None,
            ribbon="MIXED", htf_15m=None, vix=None, triggers=(), setup=None,
            trigger_level=None, would_place=False, spy=100.0,
            cursor_et=cursor.isoformat(), context_bundle=None,
        )
        return [dec, dec]  # CORE_ACCOUNTS = ("safe", "bold") -- 2 entries expected

    monkeypatch.setattr(ddr.engine_step, "step", _fake_step)

    ribbon_df, entries, err = ddr.extract_entries_and_ribbon("2026-06-30")

    assert err is None
    assert seen_cursor_dates == {"2026-06-30"}, (
        f"entry-scan cursor loop leaked cross-day bars: saw {seen_cursor_dates}"
    )
    assert ribbon_df is not None
    assert set(ribbon_df["timestamp_et"].dt.date.astype(str)) == {"2026-06-30"}


def test_curriculum_includes_every_requested_day():
    curriculum = ddr.build_curriculum()
    dates = {c["date"] for c in curriculum}
    for d in ddr.REQUESTED_DAYS:
        assert d in dates, f"requested day {d} missing from discovered curriculum"


def test_held_out_days_are_a_chronological_tail():
    dates = ["2026-06-30", "2026-07-02", "2026-07-08", "2026-07-14", "2026-07-17", "2026-07-20"]
    held_out = ddr._held_out_days(dates)
    assert held_out == sorted(dates)[-len(held_out):]
    assert set(held_out) <= set(dates)


# =====================================================================================
# HARD FENCE -- no broker import anywhere in this module's source (mirrors the dojo
# package's own fence philosophy; static AST scan, not an import-time check, so it also
# catches an import buried inside a function body).
# =====================================================================================
_FORBIDDEN_MODULE_SUBSTRINGS = ("alpaca", "broker")


def test_no_broker_import_in_source():
    src = (ROOT / "backtest" / "tools" / "dojo_exit_diversity_replay.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        for n in names:
            low = n.lower()
            for bad in _FORBIDDEN_MODULE_SUBSTRINGS:
                assert bad not in low, f"forbidden import touching {bad!r}: {n!r}"


def test_no_git_operations_in_source():
    """No shell-out capability at all (subprocess/os.system/Popen), and no literal git-mutation
    invocation strings -- distinct from merely mentioning "git" in a docstring/comment (this
    module's own docstring documents the "no git operations" constraint in prose, which would
    false-positive a naive substring-for-'git' check)."""
    src = (ROOT / "backtest" / "tools" / "dojo_exit_diversity_replay.py").read_text(encoding="utf-8")
    assert "subprocess" not in src, "this module must never shell out (e.g. to git) -- pure sim/report only"
    assert "os.system" not in src and "Popen" not in src
    for bad in ("git commit", "git push", "git add", "git checkout", "git reset"):
        assert bad not in src.lower(), f"forbidden git-mutation invocation string found: {bad!r}"

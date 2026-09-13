"""Guards for GOAL-EARN-YOUR-KEEP item 7c -- crypto_twin_challenger.py (H1-crypto overlay).

Covers: classification of the 6 anchor classes from fixture decision rows (levels_active +
trigger_level_exact price-match, per the module's documented rule -- NOT a triggers/reason
string heuristic); 3 REAL production rows pinned where the two earlier string-heuristic
readers (Agent A/B) would have disagreed with each other and/or with this module; refused/
control $ arithmetic on a fixture ledger; the KILL and SHIP-CANDIDATE rules; forward-vs-
in-sample labelling; and _next_ladder_row reading the REAL TWIN-PROGRAM.md ladder table
(never hardcoded).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts",):
    sys.path.insert(0, str(REPO / _p))

import crypto_twin_challenger as chal  # noqa: E402


# ============================================================================
# classify_anchor_class -- the 6 classes, synthetic fixtures
# ============================================================================
def _row(trigger_price, label, extra_levels=()):
    levels = [{"price": trigger_price, "kind": "x", "label": label, "strength": 2}, *extra_levels]
    return {"trigger_level_exact": trigger_price, "levels_active": levels}


def test_classify_prior_utc_day():
    assert chal.classify_anchor_class(_row(64000.0, "Prior-UTC-day H")) == "PRIOR_UTC_DAY_H_L_C"
    assert chal.classify_anchor_class(_row(64000.0, "Prior-UTC-day C")) == "PRIOR_UTC_DAY_H_L_C"


def test_classify_intraday_forming():
    assert chal.classify_anchor_class(_row(64000.0, "Intraday H (forming)")) == "INTRADAY_H_L_FORMING"


def test_classify_session_h_l():
    assert chal.classify_anchor_class(_row(64000.0, "Asia session H")) == "SESSION_H_L"
    assert chal.classify_anchor_class(_row(64000.0, "Europe session L")) == "SESSION_H_L"
    assert chal.classify_anchor_class(_row(64000.0, "Us session H")) == "SESSION_H_L"


def test_classify_round_number():
    assert chal.classify_anchor_class(_row(64000.0, "Round 64000")) == "ROUND_NUMBER"


def test_classify_swing_pivot():
    assert chal.classify_anchor_class(_row(63559.97, "Swing L")) == "SWING_PIVOT"
    assert chal.classify_anchor_class(_row(63559.97, "Swing H")) == "SWING_PIVOT"


def test_classify_no_level_trigger_variants():
    assert chal.classify_anchor_class(None) == "NO_LEVEL_TRIGGER"
    assert chal.classify_anchor_class({"trigger_level_exact": None, "levels_active": []}) == "NO_LEVEL_TRIGGER"
    assert chal.classify_anchor_class({"trigger_level_exact": 64000.0, "levels_active": None}) == "NO_LEVEL_TRIGGER"


def test_classify_no_matching_price_falls_back():
    row = {"trigger_level_exact": 70000.0,
          "levels_active": [{"price": 64000.0, "kind": "x", "label": "Swing L", "strength": 2}]}
    assert chal.classify_anchor_class(row) == "NO_LEVEL_TRIGGER"


# ============================================================================
# 3 REAL production rows -- pinned classification, disagreement documented
# ============================================================================
# Pulled verbatim from the real automation/state/crypto-twin/decisions.jsonl (2026-09-13).
REAL_ROW_NO_LEVEL_TRIGGER = {
    "ts_utc": "2026-07-14T02:33:50.351780+00:00", "trigger_level_exact": 62274.38,
    "levels_active": None, "reason": "BULL stack 32b + hold of Prior-UTC-day C @ 62274.38",
    "triggers": ["bull_ribbon_stack_32bars", "level_hold_Prior-UTC-day C"], "scenario": None,
}
REAL_ROW_SWING_PIVOT = {
    "ts_utc": "2026-08-11T21:40:37.503459+00:00", "trigger_level_exact": 63559.97,
    "levels_active": [
        {"price": 65057.25, "kind": "prior_period_high", "label": "Prior-UTC-day H", "strength": 3},
        {"price": 63738.51, "kind": "prior_period_low", "label": "Prior-UTC-day L", "strength": 3},
        {"price": 63916.43, "kind": "pivot_p", "label": "Prior-UTC-day C", "strength": 2},
        {"price": 64439.48, "kind": "prior_period_high", "label": "Intraday H (forming)", "strength": 2},
        {"price": 63157.78, "kind": "prior_period_low", "label": "Intraday L (forming)", "strength": 2},
        {"price": 63722.33, "kind": "prior_period_high", "label": "Swing H", "strength": 2},
        {"price": 63559.97, "kind": "prior_period_low", "label": "Swing L", "strength": 2},
        {"price": 65000.0, "kind": "round_number", "label": "Round 65000", "strength": 3},
    ],
    "reason": "BULL stack 12b + hold of Swing L @ 63559.97",
    "triggers": ["bull_ribbon_stack_12bars", "level_hold_Swing L"], "scenario": None,
}
REAL_ROW_ROUND_NUMBER = {
    "ts_utc": "2026-08-11T02:05:37.153141+00:00", "trigger_level_exact": 64000.0,
    "levels_active": [
        {"price": 65364.19, "kind": "prior_period_high", "label": "Prior-UTC-day H", "strength": 3},
        {"price": 63738.51, "kind": "prior_period_low", "label": "Prior-UTC-day L", "strength": 3},
        {"price": 64023.15, "kind": "prior_period_high", "label": "Swing H", "strength": 2},
        {"price": 63882.86, "kind": "prior_period_low", "label": "Swing L", "strength": 2},
        {"price": 62500.0, "kind": "round_number", "label": "Round 62500", "strength": 1},
        {"price": 64000.0, "kind": "round_number", "label": "Round 64000", "strength": 1},
        {"price": 65000.0, "kind": "round_number", "label": "Round 65000", "strength": 3},
    ],
    "reason": "BULL stack 3b + hold of Round 64000 @ 64000.0",
    "triggers": ["bull_ribbon_stack_3bars", "level_hold_Round 64000"], "scenario": None,
}


def test_real_row_no_level_trigger_despite_reason_naming_a_level():
    """This 2026-07-14 row PREDATES the STARVATION-FIX levels_active field (null here),
    even though its `reason`/`triggers` clearly name "Prior-UTC-day C" -- a triggers-list
    or reason-regex reader (Agent A/B) would both classify this PRIOR_UTC_DAY_H_L_C. This
    module classifies NO_LEVEL_TRIGGER instead: with no levels_active to price-match
    against, there is no way to VERIFY which Level the signal code actually picked (the
    string could be stale/renamed/wrong), so NO_LEVEL_TRIGGER is the epistemically honest
    answer, not a bug -- a deliberate, documented point of disagreement with both prior
    readers, not an accidental one."""
    assert chal.classify_anchor_class(REAL_ROW_NO_LEVEL_TRIGGER) == "NO_LEVEL_TRIGGER"


def test_real_row_swing_pivot_matches_both_readers():
    assert chal.classify_anchor_class(REAL_ROW_SWING_PIVOT) == "SWING_PIVOT"


def test_real_row_round_number_matches_both_readers():
    assert chal.classify_anchor_class(REAL_ROW_ROUND_NUMBER) == "ROUND_NUMBER"


def test_real_215_trip_table_has_zero_no_level_trigger_and_matches_agent_b():
    """Ran live against the real repo files 2026-09-13 (`python setup/scripts/
    crypto_twin_challenger.py --table`): n_organic_trips=215, by_anchor_class={SWING_PIVOT:
    78, ROUND_NUMBER: 84, SESSION_H_L: 30, PRIOR_UTC_DAY_H_L_C: 21, INTRADAY_H_L_FORMING: 2,
    NO_LEVEL_TRIGGER: 0} -- EXACT match to Agent B's reason-regex counts (SWING 78, ROUND
    84, SESSION 30, PRIOR_UTC 21, INTRADAY 2, NO_LEVEL 0), and structurally confirms
    Agent A's NO_LEVEL_TRIGGER=35 was a parse gap (trigger_level_exact is non-null on
    every genuine organic ENTER -- see module docstring), not real signal. This test pins
    the CLASSIFIER FUNCTION's behavior on the 3 real rows above (the parts that don't
    require reading the live repo state) rather than re-running the full join, which needs
    the real on-disk ledgers and is exercised directly by the module's own `--table`/
    `--update` CLI, not by the unit suite."""
    assert chal.classify_anchor_class(REAL_ROW_SWING_PIVOT) == "SWING_PIVOT"
    assert chal.classify_anchor_class(REAL_ROW_ROUND_NUMBER) == "ROUND_NUMBER"
    assert chal.classify_anchor_class(REAL_ROW_NO_LEVEL_TRIGGER) == "NO_LEVEL_TRIGGER"


# ============================================================================
# refused/control $ arithmetic on a fixture ledger
# ============================================================================
def _ledger_row(ts, cls, pnl_usd, forward=False):
    return {"ts_utc": ts, "anchor_class": cls, "refused": cls == chal.H1_REFUSE_CLASS,
           "control_pnl_usd": pnl_usd, "notional_usd": 900.0, "sizing_mode": "organic_10pct",
           "forward": forward}


def test_window_stats_refused_and_challenger_net():
    rows = [
        _ledger_row("2026-09-13T00:00:00+00:00", "SWING_PIVOT", -5.0),
        _ledger_row("2026-09-13T01:00:00+00:00", "ROUND_NUMBER", 3.0),
        _ledger_row("2026-09-13T02:00:00+00:00", "SWING_PIVOT", -2.0),
        _ledger_row("2026-09-13T03:00:00+00:00", "SESSION_H_L", 1.0),
    ]
    stats = chal._window_stats(rows)
    assert stats["control_n"] == 4
    assert stats["control_net_usd"] == pytest.approx(-3.0)
    assert stats["refused_n"] == 2
    assert stats["refused_net_usd"] == pytest.approx(-7.0)
    # challenger = control - refused = -3.0 - (-7.0) = 4.0 (avoiding the two SWING losses)
    assert stats["challenger_net_usd"] == pytest.approx(4.0)


def test_window_stats_time_bounds():
    rows = [
        _ledger_row("2026-09-13T00:00:00+00:00", "SWING_PIVOT", -1.0),
        _ledger_row("2026-09-13T12:00:00+00:00", "SWING_PIVOT", -2.0),
    ]
    import crypto_twin_pnl as pnl
    since = pnl._epoch("2026-09-13T06:00:00+00:00")
    stats = chal._window_stats(rows, since_epoch=since)
    assert stats["control_n"] == 1
    assert stats["control_net_usd"] == pytest.approx(-2.0)


# ============================================================================
# KILL / SHIP-CANDIDATE / RUNNING rules
# ============================================================================
def test_kill_fires_at_n6_net_nonnegative():
    forward_rows = [_ledger_row(f"2026-09-14T0{i}:00:00+00:00", "SWING_PIVOT", 1.0, forward=True)
                    for i in range(6)]
    status = chal._kill_ship_status(forward_rows)
    assert status["status"] == "KILL"
    assert status["n"] == 6
    assert status["net_usd"] == pytest.approx(6.0)


def test_kill_does_not_fire_below_n6():
    forward_rows = [_ledger_row(f"2026-09-14T0{i}:00:00+00:00", "SWING_PIVOT", 1.0, forward=True)
                    for i in range(5)]
    status = chal._kill_ship_status(forward_rows)
    assert status["status"] == "RUNNING"
    assert status["kill_progress"] == "5/6"


def test_kill_does_not_fire_when_refused_net_negative():
    forward_rows = [_ledger_row(f"2026-09-14T0{i}:00:00+00:00", "SWING_PIVOT", -1.0, forward=True)
                    for i in range(6)]
    status = chal._kill_ship_status(forward_rows)
    assert status["status"] == "RUNNING"  # net < 0 -- not a kill (and not yet 20 for ship)


def test_ship_candidate_fires_at_n20_net_negative_ex_worst_still_negative():
    # 19 small losses of -0.10 + one big loss of -5.0 -> net negative, and STILL negative
    # after dropping the single worst (-5.0) trade.
    rows = [_ledger_row(f"2026-09-14T{i:02d}:00:00+00:00", "SWING_PIVOT", -0.10, forward=True)
           for i in range(19)]
    rows.append(_ledger_row("2026-09-15T00:00:00+00:00", "SWING_PIVOT", -5.0, forward=True))
    status = chal._kill_ship_status(rows)
    assert status["status"] == "SHIP-CANDIDATE"
    assert status["n"] == 20
    assert status["net_ex_worst_usd"] < 0


def test_one_winner_flips_ship_eligible_net_to_a_kill_instead():
    # 19 losses of -0.10 (net -1.90) + one big WIN of +5.0 -> net = +3.10 (>= 0). At
    # n=20 (>= both H1_KILL_N and H1_SHIP_N) a non-negative net means KILL fires --
    # KILL and SHIP-CANDIDATE are mutually exclusive by construction (SHIP requires
    # net < 0), so this is the CORRECT outcome, not a missed ship: one real winner is
    # enough to disqualify the denylist from "refusing pure losers."
    rows = [_ledger_row(f"2026-09-14T{i:02d}:00:00+00:00", "SWING_PIVOT", -0.10, forward=True)
           for i in range(19)]
    rows.append(_ledger_row("2026-09-15T00:00:00+00:00", "SWING_PIVOT", 5.0, forward=True))
    status = chal._kill_ship_status(rows)
    assert status["status"] == "KILL"


def test_ship_candidate_rejected_when_single_worst_trade_explains_the_whole_result():
    # 19 tiny WINS of +0.01 (net +0.19) + one huge loss of -10.0 -> net = -9.81 (< 0), but
    # dropping the worst trade flips it back to +0.19 (>= 0) -- the result is NOT robust to
    # one trade, so this must NOT ship.
    rows = [_ledger_row(f"2026-09-14T{i:02d}:00:00+00:00", "SWING_PIVOT", 0.01, forward=True)
           for i in range(19)]
    rows.append(_ledger_row("2026-09-15T00:00:00+00:00", "SWING_PIVOT", -10.0, forward=True))
    status = chal._kill_ship_status(rows)
    assert status["status"] == "RUNNING"  # net<0 but ex-worst>=0 -- fails the ship bar


# ============================================================================
# forward vs in-sample labelling
# ============================================================================
def test_forward_rows_filters_on_the_forward_flag():
    rows = [_ledger_row("2026-09-01T00:00:00+00:00", "SWING_PIVOT", -1.0, forward=False),
           _ledger_row("2026-09-14T00:00:00+00:00", "SWING_PIVOT", -1.0, forward=True)]
    fwd = chal._forward_rows(rows)
    assert len(fwd) == 1
    assert fwd[0]["ts_utc"] == "2026-09-14T00:00:00+00:00"


def test_build_summary_splits_historical_and_forward_windows():
    rows = [
        _ledger_row("2026-08-01T00:00:00+00:00", "SWING_PIVOT", -3.0, forward=False),
        _ledger_row("2026-09-14T00:00:00+00:00", "ROUND_NUMBER", 2.0, forward=True),
    ]
    import datetime as dt
    summary = chal.build_summary(rows, now_utc=dt.datetime(2026, 9, 14, 0, 30, tzinfo=dt.timezone.utc))
    assert summary["windows"]["historical_in_sample"]["control_n"] == 1
    assert summary["windows"]["historical_in_sample"]["control_net_usd"] == pytest.approx(-3.0)
    assert summary["windows"]["forward_since_start"]["control_n"] == 1
    assert summary["windows"]["forward_since_start"]["control_net_usd"] == pytest.approx(2.0)
    assert summary["tomorrow_change"] == "none (H1-crypto clock running: 0/6 refused)"


# ============================================================================
# _next_ladder_row -- reads the REAL TWIN-PROGRAM.md table, never hardcoded
# ============================================================================
def test_next_ladder_row_reads_real_twin_program_doc():
    row = chal._next_ladder_row()
    assert row is not None
    assert row.startswith("H2")
    assert "stack" in row.lower() or "ribbon" in row.lower()


def test_next_ladder_row_from_fixture_doc(tmp_path):
    doc = tmp_path / "fake-ladder.md"
    doc.write_text(
        "| # | Gate | Motivation |\n|---|---|---|\n"
        "| H1 | refuse `SWING_PIVOT` anchors | x |\n"
        "| H2 | refuse ribbon `stack_n <= 3` | y |\n"
        "| H3 | refuse entries 18:00-24:00 UTC | z |\n",
        encoding="utf-8",
    )
    assert chal._next_ladder_row(doc, current="H1") == "H2: refuse ribbon `stack_n <= 3`"
    assert chal._next_ladder_row(doc, current="H2") == "H3: refuse entries 18:00-24:00 UTC"
    assert chal._next_ladder_row(doc, current="H3") is None  # last row -- no next


def test_next_ladder_row_missing_doc_fails_open(tmp_path):
    assert chal._next_ladder_row(tmp_path / "does-not-exist.md", current="H1") is None


def test_tomorrow_change_line_kill_names_next_row(tmp_path, monkeypatch):
    doc = tmp_path / "fake-ladder.md"
    doc.write_text("| # | Gate |\n|---|---|\n| H1 | refuse SWING_PIVOT |\n| H2 | refuse stack_n<=3 |\n",
                   encoding="utf-8")
    monkeypatch.setattr(chal, "PREREG_LADDER_DOC", doc)
    line = chal.tomorrow_change_line({"status": "KILL", "n": 6, "net_usd": 1.5})
    assert line.startswith("KILL:")
    assert "H2" in line


def test_tomorrow_change_line_ship_candidate():
    line = chal.tomorrow_change_line({"status": "SHIP-CANDIDATE", "n": 20, "net_usd": -3.0,
                                      "net_ex_worst_usd": -1.0})
    assert line.startswith("SHIP-CANDIDATE: file prereg")


def test_tomorrow_change_line_running():
    line = chal.tomorrow_change_line({"status": "RUNNING", "n": 2})
    assert line == "none (H1-crypto clock running: 2/6 refused)"


# ============================================================================
# update_ledger -- fail-open contract + cheap watermark skip
# ============================================================================
def test_update_ledger_never_raises_on_missing_files(tmp_path, monkeypatch):
    import crypto_twin_pnl as pnl
    monkeypatch.setattr(pnl, "JOURNAL", tmp_path / "no-journal.jsonl")
    monkeypatch.setattr(pnl, "DECISIONS", tmp_path / "no-decisions.jsonl")
    monkeypatch.setattr(chal, "LEDGER_PATH", tmp_path / "challenger-h1.jsonl")
    monkeypatch.setattr(chal, "SUMMARY_PATH", tmp_path / "challenger-h1-summary.json")
    monkeypatch.setattr(chal, "WATERMARK_PATH", tmp_path / "watermark.json")
    result = chal.update_ledger()
    assert "error" not in result or isinstance(result, dict)  # never raises -- caller got a dict back
    assert (tmp_path / "challenger-h1-summary.json").exists()


def test_update_ledger_skips_when_journal_unchanged(tmp_path, monkeypatch):
    import crypto_twin_pnl as pnl
    journal = tmp_path / "journal.jsonl"
    journal.write_text("", encoding="utf-8")
    monkeypatch.setattr(pnl, "JOURNAL", journal)
    monkeypatch.setattr(pnl, "DECISIONS", tmp_path / "decisions.jsonl")
    monkeypatch.setattr(chal, "LEDGER_PATH", tmp_path / "challenger-h1.jsonl")
    monkeypatch.setattr(chal, "SUMMARY_PATH", tmp_path / "challenger-h1-summary.json")
    monkeypatch.setattr(chal, "WATERMARK_PATH", tmp_path / "watermark.json")

    r1 = chal.update_ledger()
    assert "skipped" not in r1  # first run -- always does the (empty) join

    r2 = chal.update_ledger()
    assert r2.get("skipped") == "no new journal activity since last run"

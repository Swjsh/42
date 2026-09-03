"""Guard suite for backtest/tools/day_type_labels.py (F5 day-type classifier prereg +
label/feature builder). See analysis/recommendations/prereg-day-type-classifier-2026-09-03.md
for the frozen label definition and feature list this module implements.

Covers:
  1. the OLS slope helper (VIX 5d/20d slope primitive)
  2. FIFO leg matching -> realized_pnl / exit_multiple_max / outcome, multi-leg AND
     single-leg exits
  3. label_for_day's five branches (paying / tax / mixed / no_trade / in_progress)
  4. the CURRENT session is ALWAYS in_progress even when it already has a book_pnl>0 and
     a qualifying >=1.3x exit -- a label must never be finalized before the session closes
  5. NO LOOK-AHEAD (required by the task brief): a 09:35 feature row for date D is
     unaffected by a corrupted tick dated D but timestamped after 09:35
  6. the 09:45 feature bucket (opening-range width/position, ribbon-flip count) reads only
     the 09:30-09:45 window and ignores a tick outside it
  7. real-repo smoke test: the four named anchor winning days (loss-size-math.md's "Big
     winning days" table) are labeled 'paying' on the actual fills-ledger.jsonl -- these
     are closed historical sessions, so this assertion is permanent, not date-sensitive
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import day_type_labels as dtl  # noqa: E402


# ---------------------------------------------------------------------------------
# 1. slope helper
# ---------------------------------------------------------------------------------
def test_slope_basic():
    assert dtl._slope([1.0, 2.0, 3.0, 4.0]) == 1.0
    assert dtl._slope([4.0, 3.0, 2.0, 1.0]) == -1.0
    assert dtl._slope([5.0]) is None          # single point -- no slope
    assert dtl._slope([]) is None


# ---------------------------------------------------------------------------------
# 2. FIFO leg matching + per-activity scoring
# ---------------------------------------------------------------------------------
def _fill(activity_id, arm, symbol, date_et, side, qty, price, ts_utc, multiplier=100):
    return {"activity_id": activity_id, "arm": arm, "symbol": symbol, "date_et": date_et,
            "side": side, "qty": qty, "price": price, "multiplier": multiplier,
            "ts_utc": ts_utc}


def test_fifo_multi_leg_tp1_and_runner_scores_correctly():
    """qty=6 bought at 1.00, TP1 sells 4 @ 2.00 (exit multiple 2.0x -- qualifies), runner
    sells 2 @ 0.50 (a partial give-back). realized_pnl = (4*2.00 + 2*0.50 - 6*1.00)*100
    = (8.00+1.00-6.00)*100 = $300.00. exit_multiple_max = 2.00/1.00 = 2.0 -> had_exit_ge
    _threshold True even though the runner leg alone would not qualify."""
    fills = [
        _fill("buy1", "safe-2", "SPY260701C00700000", "2026-07-01", "buy", 6.0, 1.00,
              "2026-07-01T13:35:00Z"),
        _fill("s1", "safe-2", "SPY260701C00700000", "2026-07-01", "sell", 4.0, 2.00,
              "2026-07-01T13:50:00Z"),
        _fill("s2", "safe-2", "SPY260701C00700000", "2026-07-01", "sell", 2.0, 0.50,
              "2026-07-01T14:10:00Z"),
    ]
    legs_index = dtl._legs_by_activity_id(fills)
    rec = legs_index["buy1"]
    assert rec["remaining"] == 0.0
    assert [l["price"] for l in rec["legs"]] == [2.00, 0.50]   # chronological order
    # recompute via the same math score_activities uses, on this one record
    proceeds = sum(l["price"] * l["qty"] for l in rec["legs"]) * rec["multiplier"]
    cost = rec["entry_price"] * sum(l["qty"] for l in rec["legs"]) * rec["multiplier"]
    assert round(proceeds - cost, 2) == 300.0
    exit_multiple_max = max(l["price"] for l in rec["legs"]) / rec["entry_price"]
    assert exit_multiple_max == 2.0
    assert exit_multiple_max >= dtl.EXIT_MULTIPLE_PAYING_THRESHOLD


def test_fifo_single_leg_stop_out_is_a_loser_no_1_3x():
    fills = [
        _fill("buy2", "bold-2", "SPY260701P00700000", "2026-07-01", "buy", 5.0, 0.40,
              "2026-07-01T15:00:00Z"),
        _fill("s1", "bold-2", "SPY260701P00700000", "2026-07-01", "sell", 5.0, 0.20,
              "2026-07-01T15:05:00Z"),
    ]
    legs_index = dtl._legs_by_activity_id(fills)
    rec = legs_index["buy2"]
    proceeds = sum(l["price"] * l["qty"] for l in rec["legs"]) * rec["multiplier"]
    cost = rec["entry_price"] * sum(l["qty"] for l in rec["legs"]) * rec["multiplier"]
    pnl = round(proceeds - cost, 2)
    assert pnl == -100.0
    exit_multiple_max = max(l["price"] for l in rec["legs"]) / rec["entry_price"]
    assert exit_multiple_max == 0.5
    assert exit_multiple_max < dtl.EXIT_MULTIPLE_PAYING_THRESHOLD


def test_fifo_open_position_has_positive_remaining():
    fills = [
        _fill("buy3", "risky-1", "SPY260903C00770000", "2026-09-03", "buy", 5.0, 1.00,
              "2026-09-03T15:00:00Z"),
        _fill("s1", "risky-1", "SPY260903C00770000", "2026-09-03", "sell", 2.0, 1.10,
              "2026-09-03T15:05:00Z"),
    ]
    legs_index = dtl._legs_by_activity_id(fills)
    rec = legs_index["buy3"]
    assert rec["remaining"] == 3.0   # still open -- NOT a closed activity


# ---------------------------------------------------------------------------------
# 3. label_for_day -- all five branches
# ---------------------------------------------------------------------------------
def test_label_for_day_paying():
    label, rule = dtl.label_for_day(book_pnl=500.0, n_winners=2, n_closed=6,
                                     had_1_3x=True, is_current_session=False)
    assert label == "paying"


def test_label_for_day_tax_requires_zero_winners():
    label, rule = dtl.label_for_day(book_pnl=-300.0, n_winners=0, n_closed=4,
                                     had_1_3x=False, is_current_session=False)
    assert label == "tax"
    # same negative book, but ONE winner among the closes -> not "every exit a stop"
    label2, _ = dtl.label_for_day(book_pnl=-50.0, n_winners=1, n_closed=4,
                                   had_1_3x=False, is_current_session=False)
    assert label2 == "mixed"


def test_label_for_day_mixed_when_paying_condition_only_half_met():
    # positive book but no exit ever reached 1.3x -- NOT paying
    label, _ = dtl.label_for_day(book_pnl=40.0, n_winners=3, n_closed=5,
                                  had_1_3x=False, is_current_session=False)
    assert label == "mixed"


def test_label_for_day_no_trade_and_in_progress():
    label, rule = dtl.label_for_day(book_pnl=0.0, n_winners=0, n_closed=0,
                                     had_1_3x=False, is_current_session=False)
    assert label == "no_trade"
    # in_progress wins over EVERY other condition, including a fully-qualifying paying day
    label2, rule2 = dtl.label_for_day(book_pnl=999.0, n_winners=5, n_closed=5,
                                       had_1_3x=True, is_current_session=True)
    assert label2 == "in_progress"
    assert rule2 == "current_session_never_finalized"


# ---------------------------------------------------------------------------------
# 4. build_labels: the CURRENT session is never finalized, even mid-build
# ---------------------------------------------------------------------------------
def test_build_labels_current_session_forced_in_progress(monkeypatch):
    fake_activities = [
        {"activity_id": "a1", "arm": "safe-2", "date_et": "2026-07-02", "entry_price": 1.0,
         "closed_qty": 5.0, "total_qty": 5.0, "still_open": False, "realized_pnl": 300.0,
         "exit_multiple_max": 1.5, "had_exit_ge_threshold": True, "outcome": "winner"},
        {"activity_id": "a2", "arm": "safe-2", "date_et": "2026-07-02", "entry_price": 1.0,
         "closed_qty": 5.0, "total_qty": 5.0, "still_open": False, "realized_pnl": 500.0,
         "exit_multiple_max": 2.0, "had_exit_ge_threshold": True, "outcome": "winner"},
    ]
    monkeypatch.setattr(dtl, "score_activities", lambda: fake_activities)
    rows, meta = dtl.build_labels(today_str="2026-07-02")
    assert len(rows) == 1
    assert rows[0]["book_pnl"] == 800.0
    assert rows[0]["had_exit_ge_1_3x"] is True
    # a day that would clearly be 'paying' by every other measure is STILL in_progress
    # because build_labels was told today_str == this date
    assert rows[0]["label"] == "in_progress"


# ---------------------------------------------------------------------------------
# 5. NO LOOK-AHEAD (required): a 09:35 feature row for date D uses no row dated D but
#    timestamped after 09:35 -- corrupt a post-cutoff tick with insane values and prove
#    the computed row is unaffected.
# ---------------------------------------------------------------------------------
def _tick(time_str, spy, vix, ribbon="BULL", context_bundle=None):
    return {"date": "IGNORED", "time": time_str, "spy": spy, "vix": vix, "ribbon": ribbon,
            "context_bundle": context_bundle}


def _minute_ticks(start_h, start_m, n, spy0, vix0, ribbon="BULL"):
    ticks = []
    for i in range(n):
        m = start_m + i
        h = start_h + m // 60
        mm = m % 60
        ticks.append(_tick(f"{h:02d}:{mm:02d}:03", spy0 + 0.01 * i, vix0 - 0.01 * i, ribbon))
    return ticks


def test_features_0935_ignores_tick_dated_after_cutoff(monkeypatch):
    prior_ticks = _minute_ticks(9, 30, 30, 700.0, 15.0)          # a full prior session
    good_today = _minute_ticks(9, 30, 6, 705.0, 16.0)            # 09:30..09:35 (6 ticks)
    corrupted_after = [_tick("09:40:00", 99999.0, 999.0, "CORRUPT")]  # after 09:35 cutoff

    by_date_clean = {"2026-06-30": prior_ticks, "2026-07-01": good_today}
    by_date_corrupt = {"2026-06-30": prior_ticks, "2026-07-01": good_today + corrupted_after}

    monkeypatch.setattr(dtl, "load_core_ticks", lambda: by_date_clean)
    rows_clean = dtl.build_features(today_str="9999-01-01")
    monkeypatch.setattr(dtl, "load_core_ticks", lambda: by_date_corrupt)
    rows_corrupt = dtl.build_features(today_str="9999-01-01")

    clean = next(r for r in rows_clean if r["date"] == "2026-07-01")["features_0935"]
    corrupt = next(r for r in rows_corrupt if r["date"] == "2026-07-01")["features_0935"]
    assert clean == corrupt
    assert clean["vix_level_0935"] == 15.95     # last tick AT/before 09:35, not the 999.0 plant
    assert clean["overnight_gap_dollars"] == round(705.0 - prior_ticks[-1]["spy"], 4)


# ---------------------------------------------------------------------------------
# 6. 09:45 feature bucket -- opening range + ribbon flips, ignores ticks outside window
# ---------------------------------------------------------------------------------
def test_features_0945_opening_range_and_ribbon_flips(monkeypatch):
    prior_ticks = _minute_ticks(9, 30, 30, 700.0, 15.0)
    # 15 ticks 09:30..09:44, ribbon flips BULL->BEAR->BULL (2 flips), spy ranges 710..712.4
    or_ticks = []
    for i in range(15):
        m = 30 + i
        rb = "BULL" if i < 5 else ("BEAR" if i < 10 else "BULL")
        or_ticks.append(_tick(f"09:{m:02d}:03", 710.0 + 0.2 * i, 16.0, rb))
    outside_window = [_tick("09:45:03", -999.0, -999.0, "SHOULD_NOT_COUNT")]  # AT 09:45, excluded

    by_date = {"2026-06-30": prior_ticks, "2026-07-01": or_ticks + outside_window}
    monkeypatch.setattr(dtl, "load_core_ticks", lambda: by_date)
    rows = dtl.build_features(today_str="9999-01-01")
    f45 = next(r for r in rows if r["date"] == "2026-07-01")["features_0945"]

    assert f45["n_ticks_in_window"] == 15
    expected_width = round((710.0 + 0.2 * 14) - 710.0, 4)
    assert f45["opening_range_width_dollars"] == expected_width
    assert f45["first_15min_ribbon_flips_count"] == 2   # BULL->BEAR, BEAR->BULL


# ---------------------------------------------------------------------------------
# 7. real-repo smoke test -- the four named anchor days are permanently 'paying'
# ---------------------------------------------------------------------------------
def test_named_anchor_days_are_paying_on_real_ledger():
    rows, meta = dtl.build_labels(today_str="1900-01-01")  # a date that can never collide
    by_date = {r["date"]: r["label"] for r in rows}
    for d in dtl.NAMED_BIG_DAYS:
        assert by_date.get(d) == "paying", f"{d} expected paying, got {by_date.get(d)}"
    assert meta["all_four_anchor_days_paying"] is True


# ---------------------------------------------------------------------------------
# 8. DAY-TYPE-FORWARD-SHADOW (queue item, added 2026-09-03) -- freeze/predict/build tests
# ---------------------------------------------------------------------------------
def _fake_cook_doc(threshold: float, direction: str = "low_is_paying",
                    feature: str = "prior_day_range_dollars") -> dict:
    """Minimal cook JSON shape (day_type_classifier_grinder.py's real output) with exactly
    the fields _freeze_or_load_forward_rule reads: best_candidate_id, verdict, and one
    candidate with fold_details (varying n_train, so the largest-n_train-fold selection is
    exercised the same way it is against the real cook file)."""
    cid = f"single_split__{feature}"
    return {
        "best_candidate_id": cid,
        "verdict": "SHADOW_CANDIDATE",
        "candidates": [{
            "candidate_id": cid, "type": "single_split", "feature": feature,
            "fold_details": [
                {"week": "2026-W27", "n_train": 20, "n_test": 3,
                 "fit_used": {"threshold": threshold - 1.0, "direction": direction,
                              "train_balanced_acc": 0.6}},
                {"week": "2026-W28", "n_train": 28, "n_test": 1,  # largest n_train -> wins
                 "fit_used": {"threshold": threshold, "direction": direction,
                              "train_balanced_acc": 0.7}},
            ],
        }],
    }


def test_forward_rule_frozen_on_first_run_and_not_reread(tmp_path, monkeypatch):
    cook_path = tmp_path / "cook.json"
    rule_path = tmp_path / "day-type-forward-rule.json"
    cook_path.write_text(json.dumps(_fake_cook_doc(threshold=5.0)), encoding="utf-8")
    monkeypatch.setattr(dtl, "COOK_JSON", cook_path)
    monkeypatch.setattr(dtl, "FORWARD_RULE_JSON", rule_path)

    first = dtl._freeze_or_load_forward_rule()
    assert first["rule"]["threshold"] == 5.0
    assert first["rule"]["feature"] == "prior_day_range_dollars"
    assert first["rule"]["direction"] == "low_is_paying"
    assert rule_path.exists()

    # simulate a LATER Kitchen cook overwriting cook.json with a wildly different rule --
    # the frozen sidecar must NEVER pick this up.
    cook_path.write_text(json.dumps(_fake_cook_doc(threshold=999.0, direction="high_is_paying",
                                                     feature="vix_level_0935")),
                          encoding="utf-8")
    second = dtl._freeze_or_load_forward_rule()
    assert second == first, "a later cook must never change the frozen forward rule"
    assert second["rule"]["threshold"] == 5.0


def test_forward_rule_freeze_is_idempotent_no_rewrite(tmp_path, monkeypatch):
    cook_path = tmp_path / "cook.json"
    rule_path = tmp_path / "day-type-forward-rule.json"
    cook_path.write_text(json.dumps(_fake_cook_doc(threshold=6.57)), encoding="utf-8")
    monkeypatch.setattr(dtl, "COOK_JSON", cook_path)
    monkeypatch.setattr(dtl, "FORWARD_RULE_JSON", rule_path)

    dtl._freeze_or_load_forward_rule()
    mtime_1 = rule_path.stat().st_mtime_ns
    content_1 = rule_path.read_text(encoding="utf-8")
    dtl._freeze_or_load_forward_rule()
    dtl._freeze_or_load_forward_rule()
    assert rule_path.stat().st_mtime_ns == mtime_1, "sidecar must not be rewritten once frozen"
    assert rule_path.read_text(encoding="utf-8") == content_1


def _session(date, label, prior_day_range_dollars, or_width=None):
    """Synthetic session row shaped like day_type_labels.run()'s per-date session dict --
    features_0945 carries a DIFFERENT value under the same key name to prove the predictor
    never reads it (no-look-ahead into the 09:45 bucket)."""
    return {
        "date": date, "label": label,
        "features_0935": {"prior_day_range_dollars": prior_day_range_dollars},
        "features_0945": {"prior_day_range_dollars": or_width if or_width is not None else -9999.0},
    }


def test_forward_shadow_prediction_uses_only_0935_feature_of_same_date():
    rule_doc = {"rule": {"feature": "prior_day_range_dollars", "threshold": 6.57,
                          "direction": "low_is_paying"},
                "first_forward_session": "2026-09-04"}
    sessions = [_session("2026-07-01", "tax", prior_day_range_dollars=5.0, or_width=999.0)]
    fw = dtl.build_forward_shadow(sessions, rule_doc)
    # 5.0 <= 6.57 -> 'trade' under low_is_paying, using the 0935 value (5.0), NOT the
    # 0945 bucket's poisoned 999.0 (which would flip nothing here anyway since predict
    # never even looks at features_0945)
    assert fw["rows"][0]["predicted"] == "trade"

    # now flip: 0935 value ABOVE threshold -> stand_down, while 0945 bucket is planted with
    # a value that WOULD predict 'trade' if it were (wrongly) read instead
    sessions2 = [_session("2026-07-01", "tax", prior_day_range_dollars=10.0, or_width=1.0)]
    fw2 = dtl.build_forward_shadow(sessions2, rule_doc)
    assert fw2["rows"][0]["predicted"] == "stand_down"


def test_forward_shadow_in_sample_flag_correct():
    rule_doc = {"rule": {"feature": "prior_day_range_dollars", "threshold": 6.57,
                          "direction": "low_is_paying"},
                "first_forward_session": "2026-09-04"}
    sessions = [
        _session("2026-09-02", "paying", prior_day_range_dollars=3.0),   # before freeze date
        _session("2026-09-03", "tax", prior_day_range_dollars=3.0),      # still before
        _session("2026-09-04", "paying", prior_day_range_dollars=3.0),   # first forward session
        _session("2026-09-08", "tax", prior_day_range_dollars=3.0),      # clearly forward
    ]
    fw = dtl.build_forward_shadow(sessions, rule_doc)
    by_date = {r["date"]: r["in_sample"] for r in fw["rows"]}
    assert by_date["2026-09-02"] is True
    assert by_date["2026-09-03"] is True
    assert by_date["2026-09-04"] is False, "first_forward_session itself must be forward, not backfill"
    assert by_date["2026-09-08"] is False
    assert fw["n_forward_sessions"] == 2


def test_forward_shadow_counts_correct_on_synthetic_table():
    rule_doc = {"rule": {"feature": "prior_day_range_dollars", "threshold": 6.57,
                          "direction": "low_is_paying"},
                "first_forward_session": "2026-09-04"}
    sessions = [
        # backfill (in_sample) -- must NEVER contribute to forward_counts
        _session("2026-08-01", "tax", prior_day_range_dollars=10.0),
        # forward: 2 tax days, one correctly predicted stand_down (12.0 > 6.57), one missed
        # (3.0 <= 6.57 -> wrongly predicted trade)
        _session("2026-09-04", "tax", prior_day_range_dollars=12.0),
        _session("2026-09-08", "tax", prior_day_range_dollars=3.0),
        # forward: 3 paying days, all correctly predicted trade (<= threshold)
        _session("2026-09-09", "paying", prior_day_range_dollars=1.0),
        _session("2026-09-10", "paying", prior_day_range_dollars=2.0),
        _session("2026-09-11", "paying", prior_day_range_dollars=6.57),  # boundary: <= is trade
        # forward but unlabeled outcome types -- excluded from rows/counts entirely
        _session("2026-09-14", "mixed", prior_day_range_dollars=1.0),
        _session("2026-09-15", "no_trade", prior_day_range_dollars=1.0),
        _session("2026-09-16", "in_progress", prior_day_range_dollars=1.0),
    ]
    fw = dtl.build_forward_shadow(sessions, rule_doc)
    counts = fw["forward_counts"]
    assert counts["tax_days_total"] == 2
    assert counts["tax_days_predicted_stand_down"] == 1
    assert counts["paying_days_total"] == 3
    assert counts["paying_days_predicted_trade"] == 3
    assert fw["n_forward_sessions"] == 5           # 2 tax + 3 paying forward rows
    assert len(fw["rows"]) == 6                    # + the one backfill tax row; mixed/no_trade/
                                                    # in_progress never enter rows at all
    assert fw["status"] == "ACCRUING"              # 5 < FORWARD_SHADOW_MIN_SESSIONS (20)


def test_forward_shadow_status_bar_met_at_20_forward_sessions():
    rule_doc = {"rule": {"feature": "prior_day_range_dollars", "threshold": 6.57,
                          "direction": "low_is_paying"},
                "first_forward_session": "2026-09-04"}
    sessions = [_session(f"2026-10-{d:02d}", "paying" if d % 2 else "tax",
                          prior_day_range_dollars=3.0)
                for d in range(1, 21)]  # 20 forward sessions, all after 2026-09-04
    fw = dtl.build_forward_shadow(sessions, rule_doc)
    assert fw["n_forward_sessions"] == 20
    assert fw["status"] == "BAR_MET_AWAITING_VERDICT"


def test_forward_shadow_build_is_deterministic_idempotent():
    rule_doc = {"rule": {"feature": "prior_day_range_dollars", "threshold": 6.57,
                          "direction": "low_is_paying"},
                "first_forward_session": "2026-09-04"}
    sessions = [
        _session("2026-08-01", "tax", prior_day_range_dollars=10.0),
        _session("2026-09-05", "paying", prior_day_range_dollars=1.0),
    ]
    fw1 = dtl.build_forward_shadow(sessions, rule_doc)
    fw2 = dtl.build_forward_shadow(sessions, rule_doc)
    assert fw1 == fw2

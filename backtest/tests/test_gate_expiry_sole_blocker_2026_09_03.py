"""Guards for the GATE-EXPIRY-SOLE-BLOCKER-MINER extension of
backtest/autoresearch/gate_expiry_check.py (queue item, built 2026-09-03).

Closes the gap flagged by analysis/recommendations/vix-bear-floor-postfix-quantification-
2026-08-04.json ("standing_watch_condition": ... "queue item filed to extend the nightly
gate-expiry instrument with this sole-blocker miner so the watch is mechanical, not
remembered") -- the 11-filter bull/bear checklist refuses via HOLD rows carrying per-door
blocker lists, not a SKIP_* action, so it had no nightly refusal-costing clock at all before
this build.

Pin, in order:
  1. sole_blocker_events selects ONLY HOLD rows whose door blocker list is EXACTLY [filt] --
     multi-blocker cascade rows must never be counted (C15).
  2. mine_sole_blockers aggregates counts correctly per door/filter/account and reuses
     postfix_gate_costing.py's DOORS + sole_blocker_rows() verbatim (no second filter copy).
  3. the 2026-09-02 fixture (bull sole-[10] fired 57x while the day's own P1 outcome won)
     surfaces filter 10 as the top bull sole blocker via sole_blocker_top5.
  4. every emitted cell/flagship-watch is stamped costing="NOT_REPLAYED" -- this miner must
     never claim a dollar figure it did not compute (no OPRA replay ran).
  5. sole_blocker_flagship_results folds the two named watches (filter-8-bear-sole,
     filter-10-bull-sole) into the SAME gate-result shape compute_newly_red/flag_status_md
     already use -- proven end-to-end: a fresh RED writes exactly one STATUS.md line, a
     persisting RED (same gate, still RED next run) writes nothing new (no re-spam).
  6. fail-open: a sole-blocker mining exception never aborts the run -- both flagship ids
     degrade to overall="ERROR" while the registry gates' own results are untouched.
  7. p1_outcome_for_event: WIN -> cost_money, LOSS -> saved_money, no same-day/side fill ->
     unknown/NONE.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from autoresearch import gate_expiry_check as gec


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# ─────────────────────────────────────────────────────────────────────────────
# 1. sole_blocker_events: exact-match-only selection
# ─────────────────────────────────────────────────────────────────────────────

def test_sole_blocker_events_excludes_multi_blocker_cascade_rows():
    holds = [
        {"ts_et": "2026-09-02T10:00:00", "verdict": "HOLD", "bull_blockers": [10]},          # sole -> counts
        {"ts_et": "2026-09-02T10:30:00", "verdict": "HOLD", "bull_blockers": [10, 11]},       # cascade -> excluded
        {"ts_et": "2026-09-02T11:00:00", "verdict": "HOLD", "bull_blockers": [7]},            # different filter
    ]
    events = gec.sole_blocker_events(holds, "bull", 10)
    assert len(events) == 1
    assert events[0]["ts_et"] == "2026-09-02T10:00:00"
    assert events[0]["side"] == "C"


def test_sole_blocker_events_clusters_close_fires_into_one_event():
    holds = [
        {"ts_et": "2026-09-02T10:00:00", "verdict": "HOLD", "bear_blockers": [8]},
        {"ts_et": "2026-09-02T10:05:00", "verdict": "HOLD", "bear_blockers": [8]},  # same cluster (<=15min)
        {"ts_et": "2026-09-02T10:30:00", "verdict": "HOLD", "bear_blockers": [8]},  # new cluster (25min gap)
    ]
    events = gec.sole_blocker_events(holds, "bear", 8)
    assert len(events) == 2
    assert events[0]["side"] == "P"


def test_sole_blocker_events_empty_when_no_match():
    holds = [{"ts_et": "2026-09-02T10:00:00", "verdict": "HOLD", "bear_blockers": [5, 8]}]
    assert gec.sole_blocker_events(holds, "bear", 8) == []


# ─────────────────────────────────────────────────────────────────────────────
# 2 & 7. p1_outcome_for_event
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_outcome_win_reads_cost_money():
    p1_by_day = {("2026-09-02", "C"): [{"entry_ts_et": "2026-09-02T13:07:07", "pnl_dollars": 50.0}]}
    ev = {"ts_et": "2026-09-02T10:00:00"}
    read, pnl = gec.p1_outcome_for_event(ev, p1_by_day, "C")
    assert read == "WIN"
    assert pnl == 50.0


def test_p1_outcome_loss_reads_saved_money():
    p1_by_day = {("2026-09-02", "P"): [{"entry_ts_et": "2026-09-02T13:07:07", "pnl_dollars": -66.0}]}
    ev = {"ts_et": "2026-09-02T10:00:00"}
    read, pnl = gec.p1_outcome_for_event(ev, p1_by_day, "P")
    assert read == "LOSS"
    assert pnl == -66.0


def test_p1_outcome_none_when_no_same_day_side_fill():
    ev = {"ts_et": "2026-09-02T10:00:00"}
    read, pnl = gec.p1_outcome_for_event(ev, {}, "C")
    assert read == "NONE"
    assert pnl is None


def test_p1_outcome_falls_back_to_last_fill_when_none_fired_after_event():
    """The event fires at 15:00, after every real fill that day -- falls back to the day's
    LAST same-side fill rather than reporting NONE, since that fill is still the day's own
    outcome, just before the refusal instead of after."""
    p1_by_day = {("2026-09-02", "C"): [
        {"entry_ts_et": "2026-09-02T09:40:00", "pnl_dollars": -10.0},
        {"entry_ts_et": "2026-09-02T10:15:00", "pnl_dollars": 30.0},
    ]}
    ev = {"ts_et": "2026-09-02T15:00:00"}
    read, pnl = gec.p1_outcome_for_event(ev, p1_by_day, "C")
    assert read == "WIN"
    assert pnl == 30.0


# ─────────────────────────────────────────────────────────────────────────────
# 3. mine_sole_blockers + top5 -- the 2026-09-02 fixture (bull sole-[10] x 57)
# ─────────────────────────────────────────────────────────────────────────────

def _bull_sole10_fixture_rows(n_events: int) -> list[dict]:
    """n_events distinct (18min-separated, so > EVENT_CLUSTER_GAP_MINUTES=15 -> never folds)
    bull sole-[10] HOLD rows within one 2026-09-02 RTH session, standing in for the real day's
    finding (SIP-VOLMULT-2026-09-02.md: blocker 10 alone refused 57 of 77 5-min bars that
    session -- consecutive blocked bars within 15min fold into ONE clustered event here, same
    as every other gate this instrument mines, so this fixture's event COUNT is deliberately
    smaller than the raw 57-bar figure; it exercises the identical clustering/selection/costing
    mechanism the real day would run through)."""
    rows = []
    for i in range(n_events):
        ts = dt.datetime(2026, 9, 2, 9, 35) + dt.timedelta(minutes=18 * i)
        rows.append({"ts_et": ts.isoformat(), "account": "safe", "verdict": "HOLD", "armed": True,
                     "bull_blockers": [10], "bull_reclaim_level_raw": 765.0})
    return rows


def test_mine_sole_blockers_09_02_fixture_surfaces_filter10_as_top_bull_blocker(tmp_path, monkeypatch):
    core_decisions = tmp_path / "core-decisions.jsonl"
    rows = _bull_sole10_fixture_rows(15)
    # a smaller, unrelated bear[5] cohort so filter 10 must clearly outrank it
    rows.append({"ts_et": "2026-09-02T11:00:00", "account": "safe", "verdict": "HOLD", "armed": True,
                 "bear_blockers": [5], "bear_rejection_level_raw": 760.0})
    _write_jsonl(core_decisions, rows)
    monkeypatch.setattr(gec, "CORE_DECISIONS", core_decisions)

    p1_by_day = {("2026-09-02", "C"): [{"entry_ts_et": "2026-09-02T13:07:07", "pnl_dollars": 20.0}]}
    report = gec.mine_sole_blockers(dt.date(2026, 9, 2), dt.date(2026, 9, 2), p1_by_day=p1_by_day)

    assert "bull_filter10_safe" in report
    cell = report["bull_filter10_safe"]
    # 18-minute spacing keeps every fire its own >15min-gap cluster -> n_events == n_rows here
    assert cell["n_events"] == 15
    assert cell["costing"] == "NOT_REPLAYED"
    assert cell["n_cost_money"] == 15  # every event's P1 lookup resolves to the same WIN fill

    top5 = gec.sole_blocker_top5(report)
    assert top5["bull"][0] == {"filter": 10, "n_events": 15}
    assert top5["bear"][0] == {"filter": 5, "n_events": 1}


def test_mine_sole_blockers_counts_per_filter_id_independently(tmp_path, monkeypatch):
    core_decisions = tmp_path / "core-decisions.jsonl"
    rows = [
        {"ts_et": "2026-09-02T10:00:00", "account": "safe", "verdict": "HOLD", "armed": True,
         "bull_blockers": [7]},
        {"ts_et": "2026-09-02T10:30:00", "account": "safe", "verdict": "HOLD", "armed": True,
         "bull_blockers": [11]},
        {"ts_et": "2026-09-02T11:00:00", "account": "safe", "verdict": "HOLD", "armed": True,
         "bull_blockers": [7]},
    ]
    _write_jsonl(core_decisions, rows)
    monkeypatch.setattr(gec, "CORE_DECISIONS", core_decisions)

    report = gec.mine_sole_blockers(dt.date(2026, 9, 2), dt.date(2026, 9, 2), p1_by_day={})
    assert report["bull_filter7_safe"]["n_events"] == 2
    assert report["bull_filter11_safe"]["n_events"] == 1
    assert "bull_filter10_safe" not in report  # never fired -> never emitted


def test_mine_sole_blockers_ignores_unarmed_rows(tmp_path, monkeypatch):
    core_decisions = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core_decisions, [
        {"ts_et": "2026-09-02T10:00:00", "account": "safe", "verdict": "HOLD", "armed": False,
         "bull_blockers": [10]},
    ])
    monkeypatch.setattr(gec, "CORE_DECISIONS", core_decisions)
    report = gec.mine_sole_blockers(dt.date(2026, 9, 2), dt.date(2026, 9, 2), p1_by_day={})
    assert report == {}


# ─────────────────────────────────────────────────────────────────────────────
# 4. NOT_REPLAYED disclosure
# ─────────────────────────────────────────────────────────────────────────────

def test_every_emitted_cell_discloses_not_replayed(tmp_path, monkeypatch):
    core_decisions = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core_decisions, _bull_sole10_fixture_rows(3))
    monkeypatch.setattr(gec, "CORE_DECISIONS", core_decisions)
    report = gec.mine_sole_blockers(dt.date(2026, 9, 2), dt.date(2026, 9, 2), p1_by_day={})
    assert report, "fixture must produce at least one cell"
    for cell in report.values():
        assert cell["costing"] == "NOT_REPLAYED"


def test_flagship_results_disclose_not_replayed_in_pnl_check():
    report = {"bull_filter10_safe": {"n_events": 5, "n_cost_money": 5, "n_saved_money": 0,
                                     "n_unknown": 0, "costing": "NOT_REPLAYED"}}
    results = gec.sole_blocker_flagship_results(report, floor=3)
    assert results["filter-10-bull-sole"]["pnl_check"]["costing"] == "NOT_REPLAYED"
    assert results["filter-8-bear-sole"]["pnl_check"]["costing"] == "NOT_REPLAYED"


# ─────────────────────────────────────────────────────────────────────────────
# 5. flagship watches: verdict thresholds + transition-only STATUS.md flagging
# ─────────────────────────────────────────────────────────────────────────────

def test_flagship_bear8_green_when_zero_events():
    """Mirrors the real post-fix finding: bear sole-[8] count is expected 0 -- must read GREEN,
    never RED/YELLOW off an empty cohort."""
    results = gec.sole_blocker_flagship_results({}, floor=10)
    assert results["filter-8-bear-sole"]["overall"] == "GREEN"
    assert results["filter-8-bear-sole"]["pnl_check"]["n_events"] == 0


def test_flagship_bull10_red_when_cost_money_over_floor():
    report = {"bull_filter10_safe": {"n_events": 30, "n_cost_money": 25, "n_saved_money": 5,
                                     "n_unknown": 0, "costing": "NOT_REPLAYED"},
              "bull_filter10_bold": {"n_events": 0, "n_cost_money": 0, "n_saved_money": 0,
                                     "n_unknown": 0, "costing": "NOT_REPLAYED"}}
    results = gec.sole_blocker_flagship_results(report, floor=10)
    r = results["filter-10-bull-sole"]
    assert r["overall"] == "RED"
    assert r["pnl_check"]["n_cost_money"] == 25
    assert "NOT_REPLAYED" not in r["pnl_check"]["reason"] or "proxy" in r["pnl_check"]["reason"]
    assert "dollar costing verdict" in r["pnl_check"]["reason"]


def test_flagship_red_threshold_gates_on_cost_money_not_raw_event_count():
    """Discriminates the RED/YELLOW gate from a raw-event-count mutation: a LARGE refused
    cohort whose P1 outcomes mostly read saved_money (few cost_money) must stay YELLOW/GREEN,
    never RED off event volume alone -- the whole point of the directional read is that
    high-frequency refusals are not automatically costly."""
    report = {"bull_filter10_safe": {"n_events": 50, "n_cost_money": 2, "n_saved_money": 48,
                                     "n_unknown": 0, "costing": "NOT_REPLAYED"}}
    results = gec.sole_blocker_flagship_results(report, floor=10)
    assert results["filter-10-bull-sole"]["overall"] == "YELLOW"


def test_flagship_bull10_yellow_when_under_floor():
    report = {"bull_filter10_safe": {"n_events": 5, "n_cost_money": 2, "n_saved_money": 3,
                                     "n_unknown": 0, "costing": "NOT_REPLAYED"}}
    results = gec.sole_blocker_flagship_results(report, floor=10)
    assert results["filter-10-bull-sole"]["overall"] == "YELLOW"


def test_flagship_watches_use_same_transition_only_status_md_flagging(tmp_path, monkeypatch):
    """Byte-identical semantics proof: fold a RED flagship result into `results`, run it
    through compute_newly_red + flag_status_md exactly like a registry gate -- one new line on
    first RED, nothing new on a persisting RED."""
    status_path = tmp_path / "STATUS.md"
    status_path.write_text("## Known broken\n\n---\n\nrest\n", encoding="utf-8")
    monkeypatch.setattr(gec, "STATUS_MD", status_path)

    report = {"bull_filter10_safe": {"n_events": 30, "n_cost_money": 25, "n_saved_money": 5,
                                     "n_unknown": 0, "costing": "NOT_REPLAYED"}}
    flagship_results = gec.sole_blocker_flagship_results(report, floor=10)

    new_red_1 = gec.compute_newly_red(flagship_results, prior_gates={})
    assert [r["id"] for r in new_red_1] == ["filter-10-bull-sole"]
    gec.flag_status_md(new_red_1)
    text1 = status_path.read_text(encoding="utf-8")
    assert text1.count("GATE-EXPIRY RED") == 1
    assert "filter-10-bull-sole" in text1

    prior_run2 = {"filter-10-bull-sole": {"overall": "RED"}, "filter-8-bear-sole": {"overall": "GREEN"}}
    new_red_2 = gec.compute_newly_red(flagship_results, prior_gates=prior_run2)
    assert new_red_2 == []
    gec.flag_status_md(new_red_2)
    text2 = status_path.read_text(encoding="utf-8")
    assert text2.count("GATE-EXPIRY RED") == 1  # no re-spam


# ─────────────────────────────────────────────────────────────────────────────
# 6. fail-open
# ─────────────────────────────────────────────────────────────────────────────

def test_load_p1_outcomes_by_day_fail_open_on_malformed_line(tmp_path):
    path = tmp_path / "trades-enriched.jsonl"
    path.write_text('not-json\n{"date": "2026-09-02", "right": "C", "entry_ts_et": "x", "pnl_dollars": 5.0}\n',
                     encoding="utf-8")
    out = gec.load_p1_outcomes_by_day(path)
    assert ("2026-09-02", "C") in out
    assert len(out[("2026-09-02", "C")]) == 1


def test_load_p1_outcomes_by_day_missing_file_returns_empty():
    assert gec.load_p1_outcomes_by_day(Path("_does_not_exist_.jsonl")) == {}


def test_mine_sole_blockers_missing_core_decisions_returns_empty(monkeypatch):
    monkeypatch.setattr(gec, "CORE_DECISIONS", Path("_also_does_not_exist_.jsonl"))
    assert gec.mine_sole_blockers(dt.date(2026, 9, 2), dt.date(2026, 9, 2), p1_by_day={}) == {}

"""Guard for GATE-EXPIRY-SOLE-BLOCKER-DOUBLE-COUNT (2026-09-03).

Filed from the sole-blocker miner's first live run: bear sole-[8] read "106 events / 14
sessions" (automation/overnight/queue.md BEAR-F8-VIX-FLOOR-COSTING-REPLAY), but
bear_filter8_safe and bear_filter8_bold both counted 53 -- byte-identical, because safe and
bold run the IDENTICAL bull/bear checklist against the SAME market data, so a refused moment
mechanically produces one HOLD row per account. The flagship watch summed the two per-account
`n_events` instead of deduping across accounts, so it reported 106 refusal episodes when the
true distinct-episode count is 53.

Pin, in order:
  1. mine_sole_blockers emits BOTH `events_raw` (per-account, unchanged -- alias of the
     pre-existing `n_events`) and `episodes_distinct` (cross-account, deduped) on every cell.
  2. Two accounts sharing the SAME refused ticks -> episodes_distinct == events_raw / 2 (half
     of the naive per-account-summed raw count), not events_raw itself.
  3. sole_blocker_flagship_results reads episodes_distinct (not a naive sum of n_events) for
     the RED/YELLOW/GREEN threshold and the newly-RED transition flag.
  4. events_raw stays fully disclosed (n_events_raw in pnl_check) -- additive, nothing hidden.
  5. Legacy/hand-built reports without the distinct fields still get a verdict (fallback to
     the old sum-based behavior) -- byte-for-byte what test_gate_expiry_sole_blocker_2026_09_03
     already pins, re-asserted here as a belt-and-suspenders check.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from autoresearch import gate_expiry_check as gec


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _shared_bear8_fixture_rows(n_episodes: int) -> list[dict]:
    """n_episodes distinct (18min-separated -> never folds, EVENT_CLUSTER_GAP_MINUTES=15)
    bear sole-[8] refusals, each producing ONE HOLD row per account (safe AND bold) at the
    IDENTICAL timestamp -- the real-world shape this fix targets: same market tick, same
    gate logic, two accounts, one refused episode."""
    rows = []
    for i in range(n_episodes):
        ts = (dt.datetime(2026, 9, 2, 9, 35) + dt.timedelta(minutes=18 * i)).isoformat()
        for account in ("safe", "bold"):
            rows.append({"ts_et": ts, "account": account, "verdict": "HOLD", "armed": True,
                         "bear_blockers": [8], "bear_rejection_level_raw": 760.0})
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# 1 & 2. distinct == half of raw when both accounts share every refused tick
# ─────────────────────────────────────────────────────────────────────────────

def test_mine_sole_blockers_distinct_is_half_of_raw_when_accounts_share_ticks(tmp_path, monkeypatch):
    core_decisions = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core_decisions, _shared_bear8_fixture_rows(10))
    monkeypatch.setattr(gec, "CORE_DECISIONS", core_decisions)

    report = gec.mine_sole_blockers(dt.date(2026, 9, 2), dt.date(2026, 9, 2), p1_by_day={})

    safe_cell = report["bear_filter8_safe"]
    bold_cell = report["bear_filter8_bold"]
    assert safe_cell["n_events"] == 10  # unchanged per-account field
    assert bold_cell["n_events"] == 10
    assert safe_cell["events_raw"] == 10
    assert bold_cell["events_raw"] == 10

    # naive sum (the OLD, double-counted read) would be 20 -- the true distinct count is 10.
    naive_sum = safe_cell["events_raw"] + bold_cell["events_raw"]
    assert naive_sum == 20
    assert safe_cell["episodes_distinct"] == 10
    assert bold_cell["episodes_distinct"] == 10
    assert safe_cell["episodes_distinct"] == naive_sum // 2
    assert bold_cell["episodes_distinct"] == naive_sum // 2


def test_mine_sole_blockers_distinct_matches_real_106_over_53_shape(tmp_path, monkeypatch):
    """Reproduces the exact live shape from the 2026-09-03 finding: 53 shared episodes ->
    106 raw account-rows (53 safe + 53 bold), 53 distinct."""
    core_decisions = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core_decisions, _shared_bear8_fixture_rows(53))
    monkeypatch.setattr(gec, "CORE_DECISIONS", core_decisions)

    # 53 episodes * 18min spacing spans >15h -- rolls past midnight into 09-03, so the window
    # must cover both calendar days (mine_sole_blockers filters rows by ts_et date, not by
    # trading-session boundaries; this fixture only cares about the count, not RTH realism).
    report = gec.mine_sole_blockers(dt.date(2026, 9, 2), dt.date(2026, 9, 3), p1_by_day={})
    raw_total = report["bear_filter8_safe"]["events_raw"] + report["bear_filter8_bold"]["events_raw"]
    assert raw_total == 106
    assert report["bear_filter8_safe"]["episodes_distinct"] == 53


def test_mine_sole_blockers_distinct_cost_saved_computed_once_not_summed(tmp_path, monkeypatch):
    """Each account's own n_cost_money/n_saved_money is still computed per-account (unchanged),
    but the *_distinct variants must reflect the deduped episode set, not a sum of the two
    per-account reads."""
    core_decisions = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core_decisions, _shared_bear8_fixture_rows(4))
    monkeypatch.setattr(gec, "CORE_DECISIONS", core_decisions)
    p1_by_day = {("2026-09-02", "P"): [{"entry_ts_et": "2026-09-02T13:07:07", "pnl_dollars": -30.0}]}

    report = gec.mine_sole_blockers(dt.date(2026, 9, 2), dt.date(2026, 9, 2), p1_by_day=p1_by_day)
    safe_cell = report["bear_filter8_safe"]
    # every event's P1 lookup resolves to the same LOSS fill -> saved_money, per-account AND
    # distinct.
    assert safe_cell["n_saved_money"] == 4          # unchanged per-account read
    assert safe_cell["n_saved_money_distinct"] == 4  # NOT 8 (would be a naive sum)
    assert safe_cell["n_cost_money_distinct"] == 0
    assert safe_cell["n_unknown_distinct"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# 3 & 4. flagship watches read the distinct count, disclose the raw sum alongside
# ─────────────────────────────────────────────────────────────────────────────

def test_flagship_reads_episodes_distinct_not_naive_account_sum():
    report = {
        "bear_filter8_safe": {"n_events": 53, "n_cost_money": 22, "n_saved_money": 25,
                              "n_unknown": 6, "costing": "NOT_REPLAYED", "events_raw": 53,
                              "episodes_distinct": 53, "n_cost_money_distinct": 22,
                              "n_saved_money_distinct": 25, "n_unknown_distinct": 6},
        "bear_filter8_bold": {"n_events": 53, "n_cost_money": 22, "n_saved_money": 25,
                              "n_unknown": 6, "costing": "NOT_REPLAYED", "events_raw": 53,
                              "episodes_distinct": 53, "n_cost_money_distinct": 22,
                              "n_saved_money_distinct": 25, "n_unknown_distinct": 6},
    }
    results = gec.sole_blocker_flagship_results(report, floor=10)
    r = results["filter-8-bear-sole"]
    # verdict-driving field reads the DISTINCT count (53), not the naive sum (106).
    assert r["pnl_check"]["n_events"] == 53
    assert r["pnl_check"]["n_episodes_distinct"] == 53
    # the raw account-row sum is still fully disclosed.
    assert r["pnl_check"]["n_events_raw"] == 106
    assert r["pnl_check"]["n_cost_money"] == 22  # distinct, not 44 (the naive double-count)
    assert r["overall"] == "RED"  # 22 >= floor 10
    assert "106 raw account-row" in r["pnl_check"]["reason"]
    assert "53 distinct episode" in r["pnl_check"]["reason"]


def test_flagship_falls_back_to_legacy_sum_when_distinct_fields_absent():
    """Belt-and-suspenders re-assertion of the pre-fix pinned behavior (also covered by
    test_gate_expiry_sole_blocker_2026_09_03.py) -- hand-built cells without the new distinct
    fields must still produce a verdict via the old sum-based path."""
    report = {"bull_filter10_safe": {"n_events": 30, "n_cost_money": 25, "n_saved_money": 5,
                                     "n_unknown": 0, "costing": "NOT_REPLAYED"},
              "bull_filter10_bold": {"n_events": 0, "n_cost_money": 0, "n_saved_money": 0,
                                     "n_unknown": 0, "costing": "NOT_REPLAYED"}}
    results = gec.sole_blocker_flagship_results(report, floor=10)
    r = results["filter-10-bull-sole"]
    assert r["overall"] == "RED"
    assert r["pnl_check"]["n_cost_money"] == 25
    assert r["pnl_check"]["n_episodes_distinct"] is None  # not available -- disclosed as such


def test_flagship_green_zero_events_still_zero_with_new_fields():
    results = gec.sole_blocker_flagship_results({}, floor=10)
    assert results["filter-8-bear-sole"]["overall"] == "GREEN"
    assert results["filter-8-bear-sole"]["pnl_check"]["n_events"] == 0
    assert results["filter-8-bear-sole"]["pnl_check"]["n_events_raw"] == 0


def test_end_to_end_shared_ticks_flagship_reads_distinct(tmp_path, monkeypatch):
    """Full path: decision rows -> mine_sole_blockers -> sole_blocker_flagship_results. 12
    shared episodes (24 raw account-rows) all WIN by P1 proxy -> distinct=12 drives RED at
    floor=10; the naive sum (24) would ALSO have read RED here, so this test's discriminating
    power is in the exact counts, not just the verdict color."""
    core_decisions = tmp_path / "core-decisions.jsonl"
    _write_jsonl(core_decisions, _shared_bear8_fixture_rows(12))
    monkeypatch.setattr(gec, "CORE_DECISIONS", core_decisions)
    p1_by_day = {("2026-09-02", "P"): [{"entry_ts_et": "2026-09-02T13:07:07", "pnl_dollars": 15.0}]}

    report = gec.mine_sole_blockers(dt.date(2026, 9, 2), dt.date(2026, 9, 2), p1_by_day=p1_by_day)
    results = gec.sole_blocker_flagship_results(report, floor=10)
    r = results["filter-8-bear-sole"]
    assert r["pnl_check"]["n_events_raw"] == 24
    assert r["pnl_check"]["n_episodes_distinct"] == 12
    assert r["pnl_check"]["n_cost_money"] == 12  # NOT 24
    assert r["overall"] == "RED"

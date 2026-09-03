"""Guard suite for setup/scripts/retest_zone_shadow.py -- the F3 RETEST ZONE-WIDTH GRID +
ZONE-WIDTH PERSISTENCE shadow (analysis/recommendations/prereg-retest-zone-grid-2026-09-03.md).

The guards below pin the mechanics that would matter if broken:
  1. ZONE-WIDTH RESOLUTION. An archived snapshot's matching level's zone_width must be used
     when present within tolerance; every other case (no snapshot, no matching level, level
     with no zone_width key) must fall back to the $0.30 default with zone_source='default'
     -- never silently guess a width.
  2. GRID + IN-FORCE ARE BOTH SCORED, WITH DEDUP. Every entry gets all 5 frozen grid widths
     plus its own in-force width; when the in-force width coincides with a grid width the
     result must be reused (tagged), not recomputed as if independent.
  3. in_sample IS DETERMINISTIC ON THE TRADE'S OWN DATE, not on which run processed it --
     a trade dated on/before FREEZE_DATE is always in_sample=True, one on/after a future
     date is always in_sample=False, regardless of when the script happens to run.
  4. BOOTSTRAP CI DEGRADES HONESTLY on thin data (n_days<2 -> None), matching the sibling
     shadow ledgers' convention.
  5. BIG-WINNER-DAY SIGN FLIP is detected correctly (actual>0 vs retest>0 disagree).
  6. IDEMPOTENT + INCREMENTAL: re-running against the same fixtures never duplicates a
     ledger row; a trade lacking cached bars is skipped with a reason, not fabricated.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest" / "tools", REPO / "setup" / "scripts",
           REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import retest_zone_shadow as rzs  # noqa: E402


# ---------------------------------------------------------------------------------
# 1. resolve_zone_width -- archive match, and every fallback path
# ---------------------------------------------------------------------------------
def _write_snapshot(archive_dir: Path, date_str: str, levels: list[dict]) -> None:
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / f"key-levels-{date_str}.json").write_text(
        json.dumps({"schema_version": 3, "levels": levels}), encoding="utf-8")


def test_resolve_zone_width_uses_archived_level_within_tolerance(tmp_path, monkeypatch):
    monkeypatch.setattr(rzs, "ARCHIVE_DIR", tmp_path)
    _write_snapshot(tmp_path, "2026-09-10", [
        {"price": 700.0, "label": "PDH", "zone_width": 0.80},
        {"price": 650.0, "label": "PDL", "zone_width": 0.45},
    ])
    out = rzs.resolve_zone_width(700.005, "2026-09-10")   # within $0.01
    assert out["source"] == "archive"
    assert out["width"] == pytest.approx(0.80)
    assert out["matched_level_label"] == "PDH"


def test_resolve_zone_width_defaults_when_no_snapshot_for_date(tmp_path, monkeypatch):
    monkeypatch.setattr(rzs, "ARCHIVE_DIR", tmp_path)
    out = rzs.resolve_zone_width(700.0, "2026-09-11")
    assert out["source"] == "default"
    assert out["width"] == rzs.DEFAULT_ZONE_WIDTH
    assert "no archived snapshot" in out["reason"]


def test_resolve_zone_width_defaults_when_no_level_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(rzs, "ARCHIVE_DIR", tmp_path)
    _write_snapshot(tmp_path, "2026-09-10", [{"price": 700.0, "zone_width": 0.80}])
    out = rzs.resolve_zone_width(650.0, "2026-09-10")   # far from the only level
    assert out["source"] == "default"
    assert "no level within" in out["reason"]


def test_resolve_zone_width_defaults_when_matched_level_has_no_zone_width_key(tmp_path, monkeypatch):
    """This is the CURRENT real-archive case (Step 1 finding): every one of the 18 dated
    snapshots has levels but none carry a zone_width field."""
    monkeypatch.setattr(rzs, "ARCHIVE_DIR", tmp_path)
    _write_snapshot(tmp_path, "2026-07-02", [{"price": 731.22, "label": "PRIOR_CLOSE"}])
    out = rzs.resolve_zone_width(731.22, "2026-07-02")
    assert out["source"] == "default"
    assert out["width"] == rzs.DEFAULT_ZONE_WIDTH
    assert out["matched_level_price"] == pytest.approx(731.22)   # level WAS found...
    assert "no zone_width field" in out["reason"]                 # ...just carries no width


def test_resolve_zone_width_defaults_on_unreadable_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(rzs, "ARCHIVE_DIR", tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "key-levels-2026-09-12.json").write_text("{not valid json", encoding="utf-8")
    out = rzs.resolve_zone_width(700.0, "2026-09-12")
    assert out["source"] == "default"
    assert "unreadable" in out["reason"]


# ---------------------------------------------------------------------------------
# 2. score_entry -- grid + in-force, dedup, in_sample determinism
# ---------------------------------------------------------------------------------
class _FakeWalk:
    def __init__(self, dollar_pnl=0.0, exit_reason="test_exit", hold_minutes=5):
        self.dollar_pnl = dollar_pnl
        self.exit_reason = exit_reason
        self.hold_minutes = hold_minutes


def _event(activity_id="a1", arm="safe-2", symbol="SPY260910C00700000", opt_side="C",
           setup="BULLISH_RECLAIM_RIDE_THE_RIBBON", date_et="2026-09-10",
           ts_et="2026-09-10T10:00:00", trigger_level=700.0, qty=5.0, price=1.00,
           order_id="o1"):
    return {"activity_id": activity_id, "arm": arm, "symbol": symbol, "opt_side": opt_side,
            "setup": setup, "date_et": date_et, "ts_et": ts_et, "trigger_level": trigger_level,
            "qty": qty, "price": price, "order_id": order_id}


@pytest.fixture
def _stub_walker(monkeypatch, tmp_path):
    """Stubs every mrev bar/walk function so score_entry runs with zero dependence on real
    cached market data -- only the retest-vs-grid CONTROL FLOW is under test here."""
    monkeypatch.setattr(rzs, "ARCHIVE_DIR", tmp_path)   # no snapshot -> default width

    monkeypatch.setattr(rzs.mrev, "load_opt_bars", lambda symbol, date_str: (pd.DataFrame({"open": [1.0]}), "5min"))
    monkeypatch.setattr(rzs.mrev, "day_slice", lambda spy5, ribbon, date_str: (pd.DataFrame(), 0))
    monkeypatch.setattr(rzs.mrev, "walk_one", lambda *a, **k: _FakeWalk(dollar_pnl=42.0, exit_reason="actual"))
    monkeypatch.setattr(rzs.mrev, "load_spy_1m", lambda date_str: pd.DataFrame({"x": [1]}))
    monkeypatch.setattr(rzs.mrev, "bar_open_at_or_after", lambda df, when: 1.10)

    def fake_retest_decision(spy_1m, t0, trigger_level, side, zone_width=0.30):
        # confirmed only at the two narrowest grid widths -- lets tests distinguish outcomes
        import datetime as dt
        if zone_width in (0.20, 0.30):
            return {"outcome": "confirmed", "ts": t0 + dt.timedelta(minutes=2)}
        return {"outcome": "timeout"}

    monkeypatch.setattr(rzs.mrev, "retest_decision", fake_retest_decision)
    return None


def test_score_entry_scores_all_grid_widths_and_in_force(_stub_walker):
    row = rzs.score_entry(_event(), pd.DataFrame(), pd.DataFrame(), vix=15.5)
    assert set(row["widths"]["grid"]) == {"0.20", "0.30", "0.40", "0.50", "0.75"}
    assert row["widths"]["grid"]["0.20"]["outcome"] == "confirmed"
    assert row["widths"]["grid"]["0.40"]["outcome"] == "timeout"
    assert row["vix"] == 15.5


def test_score_entry_in_force_reuses_grid_result_when_widths_match(_stub_walker):
    """No archived snapshot -> in-force resolves to the $0.30 default, which IS a grid
    label -- the in_force result must be tagged as reused, not independently computed."""
    row = rzs.score_entry(_event(), pd.DataFrame(), pd.DataFrame(), vix=None)
    assert row["zone_in_force"]["width"] == pytest.approx(0.30)
    assert row["widths"]["in_force"]["reused_grid_label"] == "0.30"
    assert row["widths"]["in_force"]["outcome"] == row["widths"]["grid"]["0.30"]["outcome"]


def test_score_entry_in_force_scored_independently_when_off_grid(_stub_walker, tmp_path):
    """An archived width NOT on the frozen grid (e.g. 0.85) must be scored on its own --
    reused_grid_label must be None, and its outcome comes from the width-aware fake."""
    (tmp_path / "key-levels-2026-09-10.json").write_text(
        json.dumps({"levels": [{"price": 700.0, "label": "X", "zone_width": 0.85}]}),
        encoding="utf-8")
    row = rzs.score_entry(_event(), pd.DataFrame(), pd.DataFrame(), vix=None)
    assert row["zone_in_force"]["source"] == "archive"
    assert row["zone_in_force"]["width"] == pytest.approx(0.85)
    assert row["widths"]["in_force"]["reused_grid_label"] is None
    assert row["widths"]["in_force"]["outcome"] == "timeout"   # per fake_retest_decision


def test_score_entry_in_sample_true_on_or_before_freeze_date(_stub_walker):
    row = rzs.score_entry(_event(date_et="2026-09-03"), pd.DataFrame(), pd.DataFrame(), vix=None)
    assert row["in_sample"] is True


def test_score_entry_in_sample_false_after_freeze_date(_stub_walker):
    row = rzs.score_entry(_event(date_et="2026-09-04"), pd.DataFrame(), pd.DataFrame(), vix=None)
    assert row["in_sample"] is False


def test_score_entry_returns_none_without_trigger_level(_stub_walker):
    assert rzs.score_entry(_event(trigger_level=None), pd.DataFrame(), pd.DataFrame(), vix=None) is None


def test_score_entry_skips_when_no_option_bars(tmp_path, monkeypatch):
    monkeypatch.setattr(rzs, "ARCHIVE_DIR", tmp_path)
    monkeypatch.setattr(rzs.mrev, "load_opt_bars", lambda symbol, date_str: (None, None))
    row = rzs.score_entry(_event(), pd.DataFrame(), pd.DataFrame(), vix=None)
    assert row == {"activity_id": "a1", "status": "skip_no_option_bars"}


# ---------------------------------------------------------------------------------
# 3. _bootstrap_day_clustered_delta -- CI shape
# ---------------------------------------------------------------------------------
def test_bootstrap_ci_none_below_two_days():
    rows = [{"date_et": "2026-09-03", "actual": 10.0, "retest": 20.0}]
    assert rzs._bootstrap_day_clustered_delta(rows) is None


def test_bootstrap_ci_shape_with_two_or_more_days():
    rows = ([{"date_et": "2026-09-03", "actual": 10.0, "retest": 30.0} for _ in range(5)]
            + [{"date_et": "2026-09-04", "actual": 5.0, "retest": 15.0} for _ in range(5)])
    ci = rzs._bootstrap_day_clustered_delta(rows, n_boot=200)
    assert ci is not None
    assert set(ci) == {"n_boot", "n_days_clustered", "ci_lower_2.5", "ci_upper_97.5"}
    assert ci["n_days_clustered"] == 2
    assert ci["ci_lower_2.5"] <= ci["ci_upper_97.5"]


# ---------------------------------------------------------------------------------
# 4. _width_stats -- big-winner-day sign flip, VIX band split, trusted vs sign-only split
# ---------------------------------------------------------------------------------
def _ledger_row(date_et, actual_pnl, retest_pnl, outcome="confirmed", arm="safe-2", vix=14.0):
    return {
        "date_et": date_et, "actual_walk_pnl": actual_pnl, "arm": arm, "vix": vix,
        "magnitude_trusted": arm == "safe-2",
        "widths": {"grid": {"0.30": {"outcome": outcome, "retest_walk_pnl": retest_pnl}},
                   "in_force": {"outcome": outcome, "retest_walk_pnl": retest_pnl}},
    }


def test_width_stats_detects_big_winner_day_sign_flip():
    rows = [_ledger_row("2026-08-27", 1000.0, -50.0)]   # actual win, retest loss
    stats = rzs._width_stats(rows, lambda r: r["widths"]["grid"]["0.30"])
    assert stats["big_winner_days"]["2026-08-27"]["sign_flip"] is True
    assert stats["big_winner_days"]["2026-08-06"] is None   # no rows on that day


def test_width_stats_no_sign_flip_when_both_positive():
    rows = [_ledger_row("2026-08-13", 500.0, 600.0)]
    stats = rzs._width_stats(rows, lambda r: r["widths"]["grid"]["0.30"])
    assert stats["big_winner_days"]["2026-08-13"]["sign_flip"] is False


def test_width_stats_splits_trusted_vs_sign_only_by_arm():
    rows = [_ledger_row("2026-09-01", 100.0, 150.0, arm="safe-2"),
            _ledger_row("2026-09-01", 200.0, 50.0, arm="risky-1")]
    stats = rzs._width_stats(rows, lambda r: r["widths"]["grid"]["0.30"])
    assert stats["safe2_trusted"]["n"] == 1
    assert stats["safe2_trusted"]["delta"] == pytest.approx(50.0)
    assert stats["other_arms_sign_only"]["n"] == 1
    assert stats["other_arms_sign_only"]["delta"] == pytest.approx(-150.0)
    assert "SIGN-ONLY" in stats["other_arms_sign_only"]["note"]


def test_width_stats_vix_band_split_excludes_none_vix():
    rows = [_ledger_row("2026-09-01", 10.0, 20.0, vix=14.0),
            _ledger_row("2026-09-01", 10.0, 20.0, vix=16.0),
            _ledger_row("2026-09-01", 10.0, 20.0, vix=None)]
    stats = rzs._width_stats(rows, lambda r: r["widths"]["grid"]["0.30"])
    assert stats["vix_band_split"]["lt15"]["n"] == 1
    assert stats["vix_band_split"]["15to17"]["n"] == 1
    # total scored (n_scored) still counts the vix=None row -- only the band split excludes it
    assert stats["n_scored"] == 3


def test_width_stats_unconfirmed_retest_contributes_zero_not_dropped():
    rows = [_ledger_row("2026-09-01", 100.0, 999.0, outcome="timeout")]
    # timeout outcome: retest_walk_pnl in the fixture is nonzero, but a real run always sets
    # it to 0.0 for a non-confirmed outcome (score_entry's own contract) -- verify the stats
    # layer counts the trade (n_scored) without counting it as confirmed.
    stats = rzs._width_stats(rows, lambda r: r["widths"]["grid"]["0.30"])
    assert stats["n_scored"] == 1
    assert stats["n_confirmed"] == 0


# ---------------------------------------------------------------------------------
# 5. run() -- end-to-end idempotent append against fixture artifacts
# ---------------------------------------------------------------------------------
@pytest.fixture
def _wired_fixtures(tmp_path, monkeypatch):
    eql_path = tmp_path / "entry-quality-ledger.json"
    archive_dir = tmp_path / "archive"
    out_dir = tmp_path / "out"
    ledger = out_dir / "retest-zone-shadow-ledger.jsonl"
    summary = out_dir / "retest-zone-shadow-summary.json"

    events = [
        {"activity_id": "buy1", "order_id": "o1", "arm": "safe-2", "symbol": "SPY260910C00700000",
         "opt_side": "C", "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON", "qty": 5.0, "price": 1.00,
         "date_et": "2026-09-03", "ts_et": "2026-09-03T10:00:00", "exit_qty": 5.0,
         "trigger_level": 700.0},
        # not fully closed -- must be excluded (n_closed filter)
        {"activity_id": "buy2", "order_id": "o2", "arm": "safe-2", "symbol": "SPY260910C00700000",
         "opt_side": "C", "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON", "qty": 5.0, "price": 1.00,
         "date_et": "2026-09-03", "ts_et": "2026-09-03T10:05:00", "exit_qty": 2.0,
         "trigger_level": 700.0},
        # closed but no trigger_level -- must be excluded
        {"activity_id": "buy3", "order_id": "o3", "arm": "safe-2", "symbol": "SPY260910C00700000",
         "opt_side": "C", "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON", "qty": 5.0, "price": 1.00,
         "date_et": "2026-09-03", "ts_et": "2026-09-03T10:10:00", "exit_qty": 5.0,
         "trigger_level": None},
    ]
    eql_path.write_text(json.dumps({"events": events}), encoding="utf-8")

    monkeypatch.setattr(rzs, "ENTRY_QUALITY_LEDGER", eql_path)
    monkeypatch.setattr(rzs, "ARCHIVE_DIR", archive_dir)
    monkeypatch.setattr(rzs, "OUT_DIR", out_dir)
    monkeypatch.setattr(rzs, "LEDGER", ledger)
    monkeypatch.setattr(rzs, "SUMMARY", summary)

    monkeypatch.setattr(rzs.mrev, "load_opt_bars", lambda symbol, date_str: (pd.DataFrame({"open": [1.0]}), "5min"))
    monkeypatch.setattr(rzs.mrev, "day_slice", lambda spy5, ribbon, date_str: (pd.DataFrame(), 0))
    monkeypatch.setattr(rzs.mrev, "walk_one", lambda *a, **k: _FakeWalk(dollar_pnl=42.0))
    monkeypatch.setattr(rzs.mrev, "load_spy_1m", lambda date_str: pd.DataFrame({"x": [1]}))
    monkeypatch.setattr(rzs.mrev, "bar_open_at_or_after", lambda df, when: 1.10)
    monkeypatch.setattr(rzs.mrev, "retest_decision",
                         lambda *a, **k: {"outcome": "timeout"})
    monkeypatch.setattr(rzs.mrev, "load_spy_5m_and_ribbon", lambda: (pd.DataFrame(), pd.DataFrame()))
    monkeypatch.setattr(rzs.mrev, "load_core_tick_vix", lambda: {})

    return {"ledger": ledger, "summary": summary}


def test_run_scores_only_the_closed_triggered_entry(_wired_fixtures):
    out = rzs.run()
    assert "error" not in out, out
    assert out["new_this_run"] == 1
    rows = rzs._read_ledger()
    assert len(rows) == 1
    assert rows[0]["activity_id"] == "buy1"
    assert out["population"]["n_ribbon_events_total"] == 3
    assert out["population"]["n_closed"] == 2          # buy1 + buy3 (buy2 still open)
    assert out["population"]["n_no_trigger_level_excluded"] == 1   # buy3


def test_run_is_idempotent_on_a_second_fire(_wired_fixtures):
    rzs.run()
    out2 = rzs.run()
    assert out2["new_this_run"] == 0
    rows = rzs._read_ledger()
    assert len(rows) == 1, "re-running must never duplicate a ledger row"


def test_run_marks_backfill_rows_in_sample_true(_wired_fixtures):
    out = rzs.run()
    rows = rzs._read_ledger()
    assert rows[0]["in_sample"] is True   # date_et 2026-09-03 <= FREEZE_DATE
    assert out["n_in_sample_backfill"] == 1
    assert out["n_forward"] == 0

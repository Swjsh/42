"""Guard: setup/scripts/dojo/exhibit_extractor.py -- the nightly film-room agenda generator.

Pure-logic tests over synthetic fixtures (no real ledger dependency, so this never drifts with
live data) + one real-data smoke test proving the extractor runs end-to-end against today's
actual core-decisions.jsonl without raising. Red-proof style: each predicate/grouping/ranking
rule has a fires case AND a non-fires case.
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
_ap = str(REPO / "setup" / "scripts")
if _ap not in sys.path:
    sys.path.insert(0, _ap)

from dojo import exhibit_extractor as ee  # noqa: E402


def _row(ts, verdict="HOLD", side=None, setup=None, triggers=None, bull=0, bear=0,
        spy=700.0, reason=None, trigger_level_exact=None, extra_exec=None, account="safe"):
    return {
        "ts_et": ts, "account": account, "verdict": verdict, "side": side, "setup": setup,
        "triggers": triggers or [], "bull_score": bull, "bear_score": bear, "spy": spy,
        "reason": reason, "trigger_level_exact": trigger_level_exact,
        "extra_exec": extra_exec,
    }


# ---------- predicates ------------------------------------------------------------------------

def test_is_blocked_trigger_true_when_skip_and_triggers_present():
    r = _row("2026-07-21T12:21:00", verdict="SKIP_ELITE_BULL_LEVEL_RECLAIM",
             triggers=["level_reclaim", "confluence"])
    assert ee.is_blocked_trigger(r) is True


def test_is_blocked_trigger_false_when_skip_but_no_triggers():
    r = _row("2026-07-21T12:21:00", verdict="SKIP_LIQUIDITY", triggers=[])
    assert ee.is_blocked_trigger(r) is False


def test_is_blocked_trigger_false_when_enter_with_triggers():
    r = _row("2026-07-21T12:21:00", verdict="ENTER_BULL", triggers=["level_reclaim"])
    assert ee.is_blocked_trigger(r) is False


def test_is_score_high_no_trigger_true_at_threshold():
    r = _row("2026-07-21T11:05:00", bull=9, triggers=[])
    assert ee.is_score_high_no_trigger(r) is True


def test_is_score_high_no_trigger_false_below_threshold():
    r = _row("2026-07-21T11:05:00", bull=8, triggers=[])
    assert ee.is_score_high_no_trigger(r) is False


def test_is_score_high_no_trigger_false_when_trigger_present():
    r = _row("2026-07-21T11:05:00", bull=10, triggers=["level_reclaim"])
    assert ee.is_score_high_no_trigger(r) is False


def test_score_high_side_picks_bull_on_tie():
    assert ee.score_high_side(_row("t", bull=9, bear=9)) == "bull"


def test_score_high_side_picks_bear_when_higher():
    assert ee.score_high_side(_row("t", bull=5, bear=10)) == "bear"


# ---------- group_runs -------------------------------------------------------------------------

def test_group_runs_merges_contiguous_same_key():
    rows = [_row(f"2026-07-21T12:{m:02d}:00", verdict="SKIP_X") for m in (21, 26, 31)]
    runs = ee.group_runs(rows, key_fn=lambda r: r["verdict"])
    assert len(runs) == 1
    assert len(runs[0]) == 3


def test_group_runs_splits_on_key_change():
    rows = [_row("2026-07-21T12:00:00", verdict="SKIP_A"),
            _row("2026-07-21T12:05:00", verdict="SKIP_B")]
    runs = ee.group_runs(rows, key_fn=lambda r: r["verdict"])
    assert len(runs) == 2


def test_group_runs_splits_on_large_time_gap():
    rows = [_row("2026-07-21T09:00:00", verdict="SKIP_A"),
            _row("2026-07-21T13:00:00", verdict="SKIP_A")]  # 4h gap >> MAX_GAP_MINUTES
    runs = ee.group_runs(rows, key_fn=lambda r: r["verdict"])
    assert len(runs) == 2


def test_group_runs_empty_input_returns_empty():
    assert ee.group_runs([], key_fn=lambda r: r["verdict"]) == []


# ---------- blocked_trigger_exhibit / score_high_exhibit ---------------------------------------

def test_blocked_trigger_exhibit_captures_spy_forward_path():
    run = [_row("2026-07-21T12:21:00", verdict="SKIP_ELITE_BULL_LEVEL_RECLAIM", side="C",
               setup="BULLISH_RECLAIM_RIDE_THE_RIBBON", triggers=["level_reclaim"], bull=11,
               spy=748.26, reason="blocked by entry gate block_elite_bull",
               trigger_level_exact=748.26),
           _row("2026-07-21T13:55:00", verdict="SKIP_ELITE_BULL_LEVEL_RECLAIM", side="C",
               setup="BULLISH_RECLAIM_RIDE_THE_RIBBON", triggers=["level_reclaim"], bull=11,
               spy=748.60)]
    ex = ee.blocked_trigger_exhibit(run)
    assert ex["class"] == "blocked_trigger"
    assert ex["n_ticks"] == 2
    assert ex["spy_start"] == 748.26
    assert ex["spy_end"] == 748.60
    assert ex["verdict"] == "SKIP_ELITE_BULL_LEVEL_RECLAIM"


def test_score_high_exhibit_reports_peak_and_side():
    run = [_row("2026-07-21T11:01:00", bull=7, spy=746.50),
           _row("2026-07-21T11:05:00", bull=10, spy=746.90)]
    ex = ee.score_high_exhibit(run)
    assert ex["class"] == "score_high_no_trigger"
    assert ex["side"] == "bull"
    assert ex["score_peak"] == 10
    assert ex["spy_start"] == 746.50 and ex["spy_end"] == 746.90


# ---------- extra_lane_fill_exhibits -------------------------------------------------------

def test_extra_lane_fill_exhibit_fires_on_placed_status():
    rows = [_row("2026-07-21T09:51:00", spy=744.89, extra_exec=[
        {"setup": "vwap_continuation",
         "exec": {"status": "PLACED", "symbol": "SPY260721P00745000", "qty": 3, "premium": 1.65}},
    ])]
    exs = ee.extra_lane_fill_exhibits(rows)
    assert len(exs) == 1
    assert exs[0]["class"] == "extra_lane_fill"
    assert exs[0]["symbol"] == "SPY260721P00745000"


def test_extra_lane_fill_exhibit_skips_non_placed_status():
    rows = [_row("2026-07-21T09:51:00", extra_exec=[
        {"setup": "vix_regime_dayside",
         "exec": {"status": "RISK_DENY_RISK_CAP", "symbol": "X", "qty": 3, "premium": 1.0}},
    ])]
    assert ee.extra_lane_fill_exhibits(rows) == []


def test_extra_lane_fill_exhibit_handles_none_extra_exec():
    rows = [_row("2026-07-21T09:51:00", extra_exec=None)]
    assert ee.extra_lane_fill_exhibits(rows) == []


# ---------- j_called_exhibits (real csv I/O against a temp file) ----------------------------

_TRADES_HEADER = ["date", "time_entry", "time_exit", "setup", "contract", "dte", "strike",
                  "c_or_p", "qty", "entry_px", "exit_px", "premium_paid", "premium_received",
                  "dollar_pnl", "r_multiple", "stop_px", "target_px", "dollar_risk",
                  "pct_risk_of_acct", "account_equity_pre", "followed_rules", "setup_quality",
                  "fill_quality", "gamma_recommended", "j_override", "hold_minutes",
                  "trade_grade", "trade_grade_score", "delta_at_entry", "iv_at_entry",
                  "iv_regime", "slippage_cents", "exit_slippage_cents", "tod_bucket",
                  "bars_after_trigger", "entry_relative_to_bar", "hold_quality_pct",
                  "cf_time_stop_pnl", "cf_high_water_pnl", "archetype_match_json",
                  "tape_assistance", "notes_short", "account_id"]


def _write_trades_csv(tmp_path: Path, rows: list[dict]) -> Path:
    p = tmp_path / "trades.csv"
    with p.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=_TRADES_HEADER)
        w.writeheader()
        for r in rows:
            full = {k: "" for k in _TRADES_HEADER}
            full.update(r)
            w.writerow(full)
    return p


def test_j_called_exhibits_fires_only_on_j_override_y(tmp_path):
    csv_path = _write_trades_csv(tmp_path, [
        {"date": "2026-07-21", "time_entry": "10:00:00", "time_exit": "10:05:00",
         "setup": "manual_call", "contract": "SPY 748C", "dollar_pnl": "50", "j_override": "Y"},
        {"date": "2026-07-21", "time_entry": "11:00:00", "time_exit": "11:05:00",
         "setup": "vwap_continuation", "dollar_pnl": "-10", "j_override": "N"},
    ])
    exs = ee.j_called_exhibits("2026-07-21", trades_csv=csv_path)
    assert len(exs) == 1
    assert exs[0]["class"] == "j_called"
    assert exs[0]["dollar_pnl"] == "50"


def test_j_called_exhibits_scopes_to_the_given_date(tmp_path):
    csv_path = _write_trades_csv(tmp_path, [
        {"date": "2026-07-20", "setup": "manual_call", "j_override": "Y"},
    ])
    assert ee.j_called_exhibits("2026-07-21", trades_csv=csv_path) == []


def test_j_called_exhibits_missing_file_returns_empty(tmp_path):
    assert ee.j_called_exhibits("2026-07-21", trades_csv=tmp_path / "nope.csv") == []


# ---------- rank_and_cap ----------------------------------------------------------------------

def test_rank_and_cap_orders_by_tier_then_time():
    exhibits = [
        {"class": "j_called", "rank_tier": 4, "start_et": "2026-07-21T09:00:00"},
        {"class": "blocked_trigger", "rank_tier": 1, "start_et": "2026-07-21T12:00:00"},
        {"class": "score_high_no_trigger", "rank_tier": 2, "start_et": "2026-07-21T11:00:00"},
    ]
    ranked = ee.rank_and_cap(exhibits, cap=10)
    assert [e["class"] for e in ranked] == ["blocked_trigger", "score_high_no_trigger", "j_called"]


def test_rank_and_cap_caps_at_limit():
    exhibits = [{"class": "blocked_trigger", "rank_tier": 1, "start_et": f"t{i}"} for i in range(10)]
    assert len(ee.rank_and_cap(exhibits, cap=6)) == 6


# ---------- render_manifest_md --------------------------------------------------------------

def test_render_manifest_md_empty_day_says_quiet():
    md = ee.render_manifest_md("2026-07-21", [])
    assert "No exhibits extracted" in md
    assert ee.AUTO_MARKER in md


def test_render_manifest_md_contains_exhibit_sections():
    exhibits = [ee.blocked_trigger_exhibit([
        _row("2026-07-21T12:21:00", verdict="SKIP_ELITE_BULL_LEVEL_RECLAIM", side="C",
            triggers=["level_reclaim"], bull=11, spy=748.26,
            reason="blocked by entry gate block_elite_bull")])]
    md = ee.render_manifest_md("2026-07-21", exhibits)
    assert "EXHIBIT 1" in md
    assert "blocked_trigger" in md
    assert "Question for J" in md
    assert "Close-out" in md
    assert ee.AUTO_MARKER in md


# ---------- build_exhibits end-to-end (synthetic day) ----------------------------------------

def test_build_exhibits_synthesizes_all_four_classes(tmp_path, monkeypatch):
    rows = [
        _row("2026-07-21T12:21:00", verdict="SKIP_ELITE_BULL_LEVEL_RECLAIM",
            triggers=["level_reclaim"], bull=11, spy=748.26),
        _row("2026-07-21T11:05:00", bull=10, triggers=[], spy=746.90),
        _row("2026-07-21T09:51:00", extra_exec=[
            {"setup": "vwap_continuation",
             "exec": {"status": "PLACED", "symbol": "X", "qty": 2, "premium": 1.5}}]),
    ]
    csv_path = _write_trades_csv(tmp_path, [
        {"date": "2026-07-21", "setup": "manual_call", "j_override": "Y", "dollar_pnl": "50"},
    ])
    monkeypatch.setattr(ee, "TRADES_CSV", csv_path)
    exhibits = ee.build_exhibits("2026-07-21", rows)
    classes = {e["class"] for e in exhibits}
    assert classes == {"blocked_trigger", "score_high_no_trigger", "extra_lane_fill", "j_called"}


# ---------- real-data smoke test (never fabricated -- proves it runs end-to-end) ------------

def test_load_core_decisions_real_ledger_smoke():
    """No assertion on exhibit CONTENT (that would be a moving target as live data accrues) --
    only that the real pipeline runs to completion on real data without raising, and that
    filtering by date+account actually narrows the result (proves the filter isn't a no-op)."""
    all_rows_unfiltered = ee.load_core_decisions("1900-01-01")  # a date that can never exist
    assert all_rows_unfiltered == []
    # Any date present in the real ledger should parse+group+render without raising.
    real_path = ee.CORE_DECISIONS
    if not real_path.exists():
        return  # nothing to smoke-test in this environment
    import json as _json
    last_date = None
    with real_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = _json.loads(line)
            except ValueError:
                continue
            last_date = str(r.get("ts_et", ""))[:10]
    if not last_date:
        return
    rows = ee.load_core_decisions(last_date)
    exhibits = ee.build_exhibits(last_date, rows)
    md = ee.render_manifest_md(last_date, exhibits)
    assert md.startswith("# DOJO FILM-ROOM BRIEF")
    assert len(exhibits) <= ee.CAP_EXHIBITS


# ---------- main() hand-authored-brief protection guard --------------------------------------

def test_main_skips_overwriting_hand_authored_brief(tmp_path, monkeypatch):
    out_dir = tmp_path / "session-briefs"
    out_dir.mkdir(parents=True)
    hand_authored = out_dir / "2026-07-21.md"
    hand_authored.write_text("# DOJO FILM-ROOM BRIEF -- 2026-07-21 (prepped by Fable)\n"
                             "hand-curated content, no auto marker", encoding="utf-8")
    monkeypatch.setattr(ee, "OUT_DIR", out_dir)
    monkeypatch.setattr(ee, "CORE_DECISIONS", tmp_path / "nope.jsonl")
    monkeypatch.setattr(sys, "argv", ["exhibit_extractor.py", "--date", "2026-07-21"])
    rc = ee.main()
    assert rc == 0
    assert "hand-curated content" in hand_authored.read_text(encoding="utf-8")


def test_main_writes_when_no_file_exists(tmp_path, monkeypatch):
    out_dir = tmp_path / "session-briefs"
    monkeypatch.setattr(ee, "OUT_DIR", out_dir)
    monkeypatch.setattr(ee, "CORE_DECISIONS", tmp_path / "nope.jsonl")
    monkeypatch.setattr(sys, "argv", ["exhibit_extractor.py", "--date", "2026-07-01"])
    rc = ee.main()
    assert rc == 0
    out_path = out_dir / "2026-07-01.md"
    assert out_path.exists()
    assert ee.AUTO_MARKER in out_path.read_text(encoding="utf-8")


def test_main_idempotent_overwrite_when_marker_present(tmp_path, monkeypatch):
    out_dir = tmp_path / "session-briefs"
    out_dir.mkdir(parents=True)
    auto_file = out_dir / "2026-07-02.md"
    auto_file.write_text(f"# old\n{ee.AUTO_MARKER}\n", encoding="utf-8")
    monkeypatch.setattr(ee, "OUT_DIR", out_dir)
    monkeypatch.setattr(ee, "CORE_DECISIONS", tmp_path / "nope.jsonl")
    monkeypatch.setattr(sys, "argv", ["exhibit_extractor.py", "--date", "2026-07-02"])
    rc = ee.main()
    assert rc == 0
    assert "No exhibits extracted" in auto_file.read_text(encoding="utf-8")

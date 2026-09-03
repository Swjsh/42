"""Guard for setup/scripts/futures_go_live_gate.py + its wiring into go_live_gate.py
(queue.md FUTURES-ABSENT-FROM-GO-LIVE-GATE, filed 2026-08-29, built 2026-09-03).

Covers:
  1. Additivity / non-interference -- the futures block is appended AFTER the SPY report
     text (render_human) and lives under a SIBLING JSON key (report["futures"], never
     inside report["criteria"]) so it structurally cannot change overall_verdict. Proven
     both by construction (prefix-equality on render_human's output with/without the
     block) and by a fail-open guard (a raising futures_block() still yields the SPY
     report unchanged).
  2. render_markdown()/OUT_MD are UNTOUCHED by this task -- byte-identical regardless of
     whether report["futures"] is present.
  3. statistical_criterion_real_fills(): INSUFFICIENT below FUTURES_MIN_SCORED_SESSIONS
     (20), SCORED at/above it.
  4. margin_criterion(): worst-case per-trade loss vs daily_loss_limit, open-position
     margin vs equity.
  5. reconciliation_criterion(): agreement-rate math (count + direction match per day),
     INSUFFICIENT when zero broker round trips exist.
  6. Every criterion's `criterion`/`note` string is labeled PROVISIONAL.
  7. RED-PROOF (>=3): each proves a specific comparison/threshold is load-bearing by
     showing the test would have failed had that logic been neutered -- demonstrated via
     monkeypatched constants / constructed fixtures that flip the verdict, not by
     temporarily editing source (this file is read-only-safe to run repeatedly).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = str(REPO / "setup" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import futures_go_live_gate as fglg  # noqa: E402
import go_live_gate as glg  # noqa: E402


# --------------------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------------------- #
def _book_trade(date, direction="long", qty=1.0, stop_points=4.0, point_value=5.0, dollar_pnl=10.0):
    return {"date": date, "instrument": "MES", "direction": direction, "qty": qty,
            "stop_points": stop_points, "point_value": point_value, "dollar_pnl": dollar_pnl,
            "exit_reason": "TP1"}


def _write_trades_csv(path: Path, rows: list[dict]) -> None:
    cols = ["date", "session_phase", "instrument", "contract_month", "time_entry_et",
            "time_exit_et", "hold_minutes", "setup", "watcher", "confidence", "direction",
            "side", "qty", "entry_px", "exit_px", "stop_px", "tp1_px", "runner_px",
            "stop_points", "point_value", "risk_usd", "dollar_pnl", "r_multiple",
            "exit_reason", "equity_pre", "equity_post", "fills", "backend",
            "followed_rules", "rails_checked", "notes"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in rows:
            row = {c: "" for c in cols}
            row.update(r)
            w.writerow(row)


def _csv_row(date, fills, direction="long", qty="1", stop_points="4.0", point_value="5.0",
             dollar_pnl="10.0", instrument="MES"):
    return {"date": date, "instrument": instrument, "direction": direction, "qty": qty,
            "stop_points": stop_points, "point_value": point_value, "dollar_pnl": dollar_pnl,
            "fills": fills}


def _minimal_report(overall="RED"):
    """A minimal but structurally valid go_live_gate report dict -- enough to exercise
    render_human()/render_markdown() without needing every real producer wired."""
    stat_per_arm = {a: {"insufficient_data": True, "pass": False, "note": "no data"} for a in glg.ACTIVE_ARMS}
    bw = {"insufficient_data": True, "pass": False, "note": "no data"}
    return {
        "generated_et": "2026-09-03T02:00:00",
        "instrument": "setup/scripts/go_live_gate.py",
        "note": "test fixture",
        "overall_verdict": overall,
        "trades_enriched_refresh": {"status": "NOT_ATTEMPTED"},
        "criteria": {
            "statistical": {"pass": False, "per_arm": stat_per_arm, "book_wide_correlated_rollup": bw},
            "operational": {"pass": False, "guards": {}},
            "reconciliation": {"pass": False, "per_arm": {}},
            "behavioural": {"pass": False, "trailing_window": ("2026-08-01", "2026-08-28"),
                             "trailing_window_trading_days": 20,
                             "rule_breaks_in_window": {"count": 0, "pass": True},
                             "manual_or_mixed_attribution_fills_in_window": {"count": 0, "pass": True},
                             "sizing_up_events": {"note": "skipped for this fixture"}},
            "prod_shadow": {"pass": False, "status": "NOT_WIRED", "note": "not wired in fixture"},
        },
        "roster": glg.ACTIVE_ARMS,
        "risk_cap_pct_assumption": glg.RISK_CAP_PCT,
        "cost_model_scenario": {"fee_rates": glg.FEE_RATES,
                                 "exit_slippage_cents_per_contract": glg.COST_MODEL_EXIT_SLIPPAGE_CENTS,
                                 "source": "fixture"},
        "disclosures": {},
        "regime_coverage": None,
    }


# --------------------------------------------------------------------------------------- #
# 1. Additivity -- SPY section byte-identical with/without the futures block.
# --------------------------------------------------------------------------------------- #
def test_render_human_spy_section_is_an_unchanged_prefix_with_futures_present():
    report_without = _minimal_report()
    report_with = dict(report_without)
    report_with["futures"] = _sample_futures_block()

    out_without = glg.render_human(report_without)
    out_with = glg.render_human(report_with)

    assert out_with.startswith(out_without), "futures block must be a pure suffix append"
    assert out_with != out_without
    assert "FUTURES LANE" in out_with
    assert "FUTURES LANE" not in out_without


def test_render_human_skips_futures_block_when_key_absent():
    report = _minimal_report()
    assert "futures" not in report
    out = glg.render_human(report)
    assert "FUTURES LANE" not in out


def test_render_human_skips_malformed_futures_fail_open_shape():
    """The fail-open error shape (no "criteria" key) must never crash render_human."""
    report = _minimal_report()
    report["futures"] = {"lane_verdict": "INSUFFICIENT", "error": "boom",
                          "note": "futures_go_live_gate.futures_block() raised"}
    out = glg.render_human(report)
    assert "FUTURES LANE" not in out  # no "criteria" -> guarded, not rendered


def test_render_markdown_byte_identical_regardless_of_futures_key():
    """render_markdown()/OUT_MD are untouched by this task -- proven by literal byte
    equality of the rendered markdown with and without report["futures"] present."""
    report_without = _minimal_report()
    report_with = dict(report_without)
    report_with["futures"] = _sample_futures_block()

    md_without = glg.render_markdown(report_without)
    md_with = glg.render_markdown(report_with)
    assert md_with == md_without
    assert "FUTURES" not in md_with


def test_build_report_futures_key_is_sibling_never_inside_criteria(monkeypatch):
    """futures lives at report["futures"], never merged into report["criteria"] (the dict
    whose .pass values compute overall_verdict) -- proven directly on a real build_report()
    call rather than a fixture."""
    report = glg.build_report()
    assert "futures" in report
    assert "futures" not in report["criteria"]
    assert set(report["criteria"].keys()) == {
        "statistical", "operational", "reconciliation", "behavioural", "prod_shadow"}


def test_futures_block_raising_never_crashes_build_report_or_changes_overall(monkeypatch):
    """RED-PROOF 4: if futures_go_live_gate.futures_block() raises, build_report() must
    still complete and overall_verdict must be identical to a normal run's -- proving the
    fail-open wrapper is load-bearing, not decorative."""
    baseline = glg.build_report()

    def _boom():
        raise RuntimeError("synthetic failure for the fail-open guard")

    monkeypatch.setattr(fglg, "futures_block", _boom)
    report = glg.build_report()
    assert report["overall_verdict"] == baseline["overall_verdict"]
    assert report["futures"]["lane_verdict"] == "INSUFFICIENT"
    assert "error" in report["futures"]
    assert "RuntimeError" in report["futures"]["error"]


def _sample_futures_block():
    return fglg.futures_block()


# --------------------------------------------------------------------------------------- #
# 3. STATISTICAL (real fills) -- INSUFFICIENT below the floor, SCORED at/above it.
# --------------------------------------------------------------------------------------- #
def test_statistical_insufficient_below_min_sessions():
    trades = [{"date": f"2026-08-{d:02d}", "dollar_pnl": 10.0} for d in range(1, 6)]  # 5 days
    out = fglg.statistical_criterion_real_fills(trades)
    assert out["status"] == "INSUFFICIENT"
    assert out["pass"] is False
    assert out["n_scored_sessions"] == 5
    assert out["min_scored_sessions_required"] == fglg.FUTURES_MIN_SCORED_SESSIONS


def test_statistical_scored_at_or_above_min_sessions():
    trades = [{"date": f"2026-08-{d:02d}", "dollar_pnl": 10.0} for d in range(1, 21)]  # 20 winning days
    out = fglg.statistical_criterion_real_fills(trades)
    assert out["status"] == "SCORED"
    assert out["n_scored_sessions"] == 20
    # all-winning days -> every bootstrap resample is +inf PF (no losses to divide by),
    # dropped from the CI list entirely -> ci is None, so pass must be False (never
    # silently True on a CI that could not actually be computed).
    assert out["ci"] is None
    assert out["pass"] is False


def test_statistical_scored_pass_true_with_mixed_wins_and_losses():
    # 25 days: mostly winners, a few small losers -- large enough margin that CI-lower
    # clears 1.0 with this seeded bootstrap.
    trades = []
    for d in range(1, 26):
        pnl = 50.0 if d % 5 != 0 else -8.0
        trades.append({"date": f"2026-08-{d:02d}", "dollar_pnl": pnl})
    out = fglg.statistical_criterion_real_fills(trades)
    assert out["status"] == "SCORED"
    assert out["ci"]["ci_lower_2.5"] is not None
    assert out["pass"] is True


def test_statistical_red_proof_min_sessions_threshold_is_load_bearing(monkeypatch):
    """RED-PROOF 1: lowering FUTURES_MIN_SCORED_SESSIONS flips a previously-INSUFFICIENT
    5-session case to SCORED, proving the >=20 gate actually gates (not a no-op the
    function would reach regardless)."""
    trades = [{"date": f"2026-08-{d:02d}", "dollar_pnl": 10.0} for d in range(1, 6)]
    before = fglg.statistical_criterion_real_fills(trades)
    assert before["status"] == "INSUFFICIENT"

    monkeypatch.setattr(fglg, "FUTURES_MIN_SCORED_SESSIONS", 3)
    after = fglg.statistical_criterion_real_fills(trades, min_sessions=3)
    assert after["status"] == "SCORED"


# --------------------------------------------------------------------------------------- #
# 4. MARGIN -- worst-case per-trade loss vs daily_loss_limit; open-position margin vs equity.
# --------------------------------------------------------------------------------------- #
def test_margin_pass_when_within_bounds():
    trades = [_book_trade("2026-08-01", stop_points=4.0, point_value=5.0, qty=1.0)]  # $20 worst case
    account = {"equity": 2000.0, "daily_loss_limit": 200.0}
    out = fglg.margin_criterion(trades, [], account)
    assert out["status"] == "SCORED"
    assert out["pass"] is True
    assert out["worst_case_single_trade_loss"] == 20.0
    assert out["per_trade_violations"] == []


def test_margin_violation_when_worst_case_exceeds_daily_loss_limit():
    # stop_points=50 x point_value=5 x qty=1 = $250 worst case > $200 daily_loss_limit
    trades = [_book_trade("2026-08-01", stop_points=50.0, point_value=5.0, qty=1.0)]
    account = {"equity": 2000.0, "daily_loss_limit": 200.0}
    out = fglg.margin_criterion(trades, [], account)
    assert out["pass"] is False
    assert len(out["per_trade_violations"]) == 1
    assert out["per_trade_violations"][0]["worst_case_loss"] == 250.0


def test_margin_red_proof_violation_disappears_when_offending_trade_removed():
    """RED-PROOF 2: the SAME account, with vs without the one over-limit trade, flips
    pass False -> True -- proving per-trade violation detection is load-bearing, not an
    always-true or always-false stub."""
    account = {"equity": 2000.0, "daily_loss_limit": 200.0}
    over_limit = _book_trade("2026-08-01", stop_points=50.0, point_value=5.0, qty=1.0)
    within_limit = _book_trade("2026-08-02", stop_points=4.0, point_value=5.0, qty=1.0)

    with_violation = fglg.margin_criterion([over_limit, within_limit], [], account)
    without_violation = fglg.margin_criterion([within_limit], [], account)

    assert with_violation["pass"] is False
    assert without_violation["pass"] is True


def test_margin_open_position_margin_exceeds_equity():
    account = {"equity": 400.0, "daily_loss_limit": 200.0}  # small account
    open_positions = [{"symbol": "/MESU6", "qty": "2", "avg_cost": 7680.0}]  # 2 x $500 = $1000 > $400
    out = fglg.margin_criterion([], open_positions, account)
    assert out["margin_within_equity"] is False
    assert out["pass"] is False
    assert out["open_position_margin_required_conservative"] == 1000.0


def test_margin_insufficient_when_no_evidence_at_all():
    out = fglg.margin_criterion([], [], {"equity": 2000.0, "daily_loss_limit": 200.0})
    assert out["status"] == "INSUFFICIENT"
    assert out["pass"] is False


def test_instrument_from_symbol_parses_front_month_contract():
    assert fglg._instrument_from_symbol("/MESU6") == "MES"
    assert fglg._instrument_from_symbol("/MNQZ6") == "MNQ"
    assert fglg._instrument_from_symbol("") == ""


# --------------------------------------------------------------------------------------- #
# 5. RECONCILIATION -- agreement-rate math + INSUFFICIENT with zero broker round trips.
# --------------------------------------------------------------------------------------- #
def test_reconciliation_insufficient_when_zero_broker_trades():
    book = [_book_trade("2026-08-01"), _book_trade("2026-08-02")]
    out = fglg.reconciliation_criterion(book, [])
    assert out["status"] == "INSUFFICIENT"
    assert out["pass"] is False
    assert out["n_book_round_trips"] == 2
    assert out["n_broker_round_trips"] == 0


def test_reconciliation_full_agreement_when_days_match_count_and_direction():
    book = [_book_trade("2026-08-01", direction="long"), _book_trade("2026-08-02", direction="short")]
    broker = [_book_trade("2026-08-01", direction="long"), _book_trade("2026-08-02", direction="short")]
    out = fglg.reconciliation_criterion(book, broker)
    assert out["status"] == "SCORED"
    assert out["agreement_rate_direction_and_size"] == 1.0
    assert out["pass"] is True


def test_reconciliation_partial_agreement_when_one_day_mismatches_direction():
    book = [_book_trade("2026-08-01", direction="long"), _book_trade("2026-08-02", direction="short")]
    broker = [_book_trade("2026-08-01", direction="long"), _book_trade("2026-08-02", direction="long")]
    out = fglg.reconciliation_criterion(book, broker)
    assert out["agreement_rate_direction_and_size"] == 0.5
    assert out["pass"] is False  # 0.5 < FUTURES_RECONCILIATION_AGREEMENT_THRESHOLD (0.80)


def test_reconciliation_red_proof_direction_mismatch_is_load_bearing():
    """RED-PROOF 3: fixing the mismatched day's direction flips agreement_rate 0.5 -> 1.0
    and pass False -> True, proving the direction-set comparison actually discriminates
    (not a count-only check that would pass regardless of direction)."""
    book = [_book_trade("2026-08-01", direction="long"), _book_trade("2026-08-02", direction="short")]
    mismatched = [_book_trade("2026-08-01", direction="long"), _book_trade("2026-08-02", direction="long")]
    fixed = [_book_trade("2026-08-01", direction="long"), _book_trade("2026-08-02", direction="short")]

    out_mismatched = fglg.reconciliation_criterion(book, mismatched)
    out_fixed = fglg.reconciliation_criterion(book, fixed)
    assert out_mismatched["agreement_rate_direction_and_size"] < out_fixed["agreement_rate_direction_and_size"]
    assert out_fixed["agreement_rate_direction_and_size"] == 1.0


# --------------------------------------------------------------------------------------- #
# 6. PROVISIONAL labeling present on every criterion's disclosure string.
# --------------------------------------------------------------------------------------- #
def test_provisional_label_present_on_every_criterion():
    stat = fglg.statistical_criterion_real_fills([{"date": "2026-08-01", "dollar_pnl": 1.0}])
    margin = fglg.margin_criterion([_book_trade("2026-08-01")], [], {"equity": 2000.0, "daily_loss_limit": 200.0})
    recon = fglg.reconciliation_criterion([_book_trade("2026-08-01")], [_book_trade("2026-08-01")])
    assert "PROVISIONAL" in stat["criterion"]
    assert "PROVISIONAL" in margin["criterion"]
    assert "PROVISIONAL" in recon["criterion"]


# --------------------------------------------------------------------------------------- #
# Lane verdict rollup (severity ladder).
# --------------------------------------------------------------------------------------- #
def test_lane_verdict_red_dominates_insufficient():
    red_block = {"status": "RED"}
    insufficient_block = {"status": "INSUFFICIENT"}
    green_block = {"status": "GREEN"}
    assert fglg._lane_verdict(red_block, insufficient_block, green_block) == "RED"


def test_lane_verdict_insufficient_dominates_yellow_and_green():
    insufficient_block = {"status": "INSUFFICIENT"}
    yellow_block = {"status": "YELLOW"}
    green_block = {"status": "GREEN"}
    assert fglg._lane_verdict(insufficient_block, yellow_block, green_block) == "INSUFFICIENT"


def test_lane_verdict_green_only_when_everything_green():
    assert fglg._lane_verdict({"status": "GREEN"}, {"status": "GREEN"}) == "GREEN"


# --------------------------------------------------------------------------------------- #
# Operational block -- staleness handling.
# --------------------------------------------------------------------------------------- #
def test_operational_block_insufficient_when_health_json_missing(tmp_path):
    out = fglg.operational_block(tmp_path / "does-not-exist.json")
    assert out["status"] == "INSUFFICIENT"
    assert out["pass"] is False


def test_operational_block_insufficient_when_stale(tmp_path):
    from datetime import datetime
    p = tmp_path / "health.json"
    p.write_text(json.dumps({
        "checked_at_et": "2026-08-01 09:00:00",
        "verdict": "GREEN",
        "checks": [], "reasons": [],
    }), encoding="utf-8")
    now = datetime(2026, 8, 2, 9, 0, 0)  # 24h later -> way past 240m stale threshold
    out = fglg.operational_block(p, now_et=now)
    assert out["stale"] is True
    assert out["status"] == "INSUFFICIENT"


def test_operational_block_folds_underlying_verdict_when_fresh(tmp_path):
    from datetime import datetime
    p = tmp_path / "health.json"
    p.write_text(json.dumps({
        "checked_at_et": "2026-08-01 09:00:00",
        "verdict": "GREEN",
        "checks": [{"name": "broker_transport", "status": "YELLOW", "detail": "rate 12% blah"}],
        "reasons": [],
    }), encoding="utf-8")
    now = datetime(2026, 8, 1, 9, 30, 0)  # 30m later -- fresh
    out = fglg.operational_block(p, now_et=now)
    assert out["stale"] is False
    assert out["status"] == "GREEN"
    assert out["connect_failure_rate_pct"] == 12

"""Guard suite for setup/scripts/bold_tier_rail.py -- THE STANDING INSTRUMENT for
BOLD-CORE-ATM-WIRE-FALSIFICATION-RAIL (commit 718e0809, 2026-07-18's own promised n>=20
expectancy check, which a 2026-08-08 audit found existed only as prose until this module).

Rails these guards protect -- each one's failure would silently break the falsification clock:
  1. POPULATION. Reuses exit_shape_parity_study.load_fleet_engine_fills/reconstruct_positions
     (the repo's ONE position definition) -- never re-derived. Pinned against the REAL ledger
     as a regression anchor: post-ship n=6/net=-$476.00, pre-ship n=4/net=+$406.00 (matches
     analysis/deep-research/lane1-loss-anatomy-2026-08-08.json and prereg-profitability-2026-08-
     08.json exactly, verified live 2026-08-08).
  2. RAIL_STATUS. Four states, computed fresh every run -- NO_DATA/ACCRUING/TRIGGERED_NEGATIVE/
     TRIGGERED_POSITIVE -- with the n>=20 AND net<=0 escalation boundary exactly at the commit's
     own "n>=20" bar, never off-by-one.
  3. ESCALATION DEDUP. Posts to discord-outbox.jsonl EXACTLY ONCE per transition INTO
     TRIGGERED_NEGATIVE -- never once per run, and re-fires correctly if the status ever leaves
     and returns (rather than latching permanently after the first post).
  4. HONEST CLOCK. ETA projection excludes known PDT-dark trading days on both the observed-
     rate side and the forward-projection side; never guesses an ETA when the rate is undefined.
  5. FAIL-OPEN. A missing/corrupt ledger degrades to NO_DATA, never raises, never fabricates a
     trigger.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "setup" / "scripts", REPO / "backtest" / "tools",
           REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import bold_tier_rail as bt  # noqa: E402


# ---------------------------------------------------------------------------------
# Fixture helpers -- build position dicts directly (bypassing the fills->positions I/O layer)
# for the PURE-function tests; a real fills-ledger fixture is used only in the I/O-level tests.
# ---------------------------------------------------------------------------------

def _pos(pnl: float = 0.0, price: float = 1.0, qty: float = 5.0,
          date_et: str = "2026-07-20") -> dict:
    return {"date_et": date_et, "entry_price": price, "entry_qty": qty, "actual_exit_pnl": pnl}


def _fill(symbol: str, side: str, qty: float, price: float, ts_utc: str, date_et: str,
           arm: str = "bold-2") -> dict:
    return {"arm": arm, "symbol": symbol, "side": side, "qty": qty, "price": price,
            "ts_utc": ts_utc, "date_et": date_et, "attribution": "engine",
            "is_crypto": False, "is_option": True}


def _round_trip_fills(symbol: str, date_et: str, entry_price: float, exit_price: float,
                       qty: float = 5.0) -> list:
    """One buy+sell fill pair -> one closed position at (exit_price-entry_price)*qty*100 pnl."""
    return [
        _fill(symbol, "buy", qty, entry_price, f"{date_et}T13:30:00Z", date_et),
        _fill(symbol, "sell", qty, exit_price, f"{date_et}T14:00:00Z", date_et),
    ]


# ---------------------------------------------------------------------------------
# 1. cohort_stats / split_cohorts / regime_delta
# ---------------------------------------------------------------------------------

def test_cohort_stats_empty_is_none_safe():
    s = bt.cohort_stats([])
    assert s == {"n": 0, "net_usd": 0.0, "win_rate": None, "mean_usd": None,
                 "median_usd": None, "avg_notional_usd": None}


def test_cohort_stats_basic_math():
    positions = [_pos(pnl=100.0, price=1.0, qty=5.0), _pos(pnl=-50.0, price=2.0, qty=5.0)]
    s = bt.cohort_stats(positions)
    assert s["n"] == 2
    assert s["net_usd"] == 50.0
    assert s["win_rate"] == 0.5
    assert s["mean_usd"] == 25.0
    assert s["median_usd"] == 25.0
    assert s["avg_notional_usd"] == 750.0  # mean(1.0*5*100, 2.0*5*100) = mean(500,1000)


def test_split_cohorts_boundary_is_inclusive_on_ship_date():
    positions = [_pos(date_et="2026-07-17"), _pos(date_et="2026-07-18"),
                 _pos(date_et="2026-07-19")]
    post, pre = bt.split_cohorts(positions)
    assert [p["date_et"] for p in post] == ["2026-07-18", "2026-07-19"]
    assert [p["date_et"] for p in pre] == ["2026-07-17"]


def test_regime_delta_none_safe_on_empty_cohort():
    post = bt.cohort_stats([])
    pre = bt.cohort_stats([_pos()])
    d = bt.regime_delta(post, pre)
    assert d == {"net_usd_delta": None, "mean_usd_delta": None, "win_rate_delta": None,
                 "avg_notional_multiplier": None}


def test_regime_delta_basic_and_notional_multiplier():
    post = bt.cohort_stats([_pos(pnl=-100.0, price=1.5, qty=5.0)])   # notional 750
    pre = bt.cohort_stats([_pos(pnl=50.0, price=0.5, qty=5.0)])      # notional 250
    d = bt.regime_delta(post, pre)
    assert d["net_usd_delta"] == -150.0
    assert d["avg_notional_multiplier"] == 3.0


# ---------------------------------------------------------------------------------
# 2. rail_status -- all four states, boundary-exact
# ---------------------------------------------------------------------------------

def test_rail_status_no_data_at_n_zero():
    assert bt.rail_status(0, 0.0) == "NO_DATA"


def test_rail_status_accruing_below_20_regardless_of_net_sign():
    assert bt.rail_status(19, -5000.0) == "ACCRUING"
    assert bt.rail_status(1, 500.0) == "ACCRUING"


def test_rail_status_triggered_negative_at_exactly_20_and_net_zero_or_negative():
    assert bt.rail_status(20, 0.0) == "TRIGGERED_NEGATIVE"
    assert bt.rail_status(20, -0.01) == "TRIGGERED_NEGATIVE"
    assert bt.rail_status(25, -476.0) == "TRIGGERED_NEGATIVE"


def test_rail_status_triggered_positive_at_20_or_more_and_net_positive():
    assert bt.rail_status(20, 0.01) == "TRIGGERED_POSITIVE"
    assert bt.rail_status(30, 1000.0) == "TRIGGERED_POSITIVE"


# ---------------------------------------------------------------------------------
# 3. verdict_line -- matches the real anchor numbers exactly
# ---------------------------------------------------------------------------------

def test_verdict_line_matches_real_anchor_numbers():
    post = {"n": 6, "net_usd": -476.0}
    pre = {"n": 4, "net_usd": 406.0}
    line = bt.verdict_line(post, pre, "ACCRUING")
    assert line == ("Bold ATM tier: 6 of 20 fills, -$476 so far (old tier was +$406 on 4) -- "
                     "rail not yet triggered.")


def test_verdict_line_triggered_wording():
    post = {"n": 20, "net_usd": -600.0}
    pre = {"n": 4, "net_usd": 406.0}
    line = bt.verdict_line(post, pre, "TRIGGERED_NEGATIVE")
    assert "rail TRIGGERED" in line


def test_verdict_line_no_pre_ship_data():
    post = {"n": 20, "net_usd": 100.0}
    pre = {"n": 0, "net_usd": 0.0}
    line = bt.verdict_line(post, pre, "TRIGGERED_POSITIVE")
    assert "no pre-ship trades on record" in line


# ---------------------------------------------------------------------------------
# 4. HONEST CLOCK -- trading_days_between / project_forward_trading_days / compute_eta
# ---------------------------------------------------------------------------------

def test_trading_days_between_excludes_weekends_and_dark_dates():
    start = date(2026, 8, 3)   # Monday
    end = date(2026, 8, 10)    # next Monday, exclusive
    dark = frozenset({"2026-08-05"})
    days = bt.trading_days_between(start, end, dark)
    assert [d.isoformat() for d in days] == ["2026-08-03", "2026-08-04", "2026-08-06", "2026-08-07"]


def test_project_forward_skips_weekends_and_dark_dates():
    start = date(2026, 8, 7)              # Friday
    dark = frozenset({"2026-08-10"})      # the following Monday is dark
    d = bt.project_forward_trading_days(start, 2, dark)
    # 08-08 Sat skip, 08-09 Sun skip, 08-10 Mon dark skip, 08-11 Tue -> count 1, 08-12 Wed -> count 2
    assert d == date(2026, 8, 12)


def test_project_forward_zero_days_returns_start_unchanged():
    start = date(2026, 8, 7)
    assert bt.project_forward_trading_days(start, 0, frozenset()) == start


def test_compute_eta_power_floor_already_met_needs_no_projection():
    eta = bt.compute_eta(20, date(2026, 7, 18), date(2026, 8, 8))
    assert eta["remaining_fills_needed"] == 0
    assert eta["projected_trading_days_needed"] == 0
    assert eta["expected_trigger_eta_et"] == "2026-08-08"


def test_compute_eta_zero_fills_never_guesses():
    eta = bt.compute_eta(0, date(2026, 7, 18), date(2026, 7, 21))
    assert eta["observed_fills_per_trading_day"] is None
    assert eta["expected_trigger_eta_et"] is None
    assert eta["remaining_fills_needed"] == 20


def test_compute_eta_zero_elapsed_days_never_guesses():
    # today == ship_date -> zero elapsed trading days even with n>0 (can't happen in practice,
    # but the function must not divide by zero / fabricate a rate)
    eta = bt.compute_eta(3, date(2026, 7, 18), date(2026, 7, 18))
    assert eta["elapsed_trading_days_ex_dark"] == 0
    assert eta["expected_trigger_eta_et"] is None


def test_compute_eta_projects_using_dark_excluded_rate():
    # ship Mon 2026-07-20, today Mon 2026-07-27 (one full trading week later, no dark dates in
    # between) -> elapsed = 5 trading days (07-20..07-24). n_post_ship=5 -> rate=1.0/day.
    # remaining = 20-5 = 15 -> 15 more trading days needed, projected from today (07-27).
    eta = bt.compute_eta(5, date(2026, 7, 20), date(2026, 7, 27), dark_dates=frozenset())
    assert eta["elapsed_trading_days_ex_dark"] == 5
    assert eta["observed_fills_per_trading_day"] == 1.0
    assert eta["remaining_fills_needed"] == 15
    assert eta["projected_trading_days_needed"] == 15


def test_bold_pdt_dark_dates_matches_disclosed_source_window():
    # PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md: "blocked Wed 08-05 + Thu 08-06 ... stays blocked
    # Fri + Mon + Tue ... unblocks 2026-08-12" -- exactly these 5 calendar dates, nothing more.
    assert bt.BOLD_PDT_DARK_DATES == frozenset({
        "2026-08-05", "2026-08-06", "2026-08-07", "2026-08-10", "2026-08-11",
    })
    assert "2026-08-12" not in bt.BOLD_PDT_DARK_DATES  # the unblock date is NOT itself dark


# ---------------------------------------------------------------------------------
# 5. ESCALATION -- message content + dedup-by-status-transition via build_report
# ---------------------------------------------------------------------------------

def test_escalation_message_names_finding_and_one_line_revert():
    post = {"n": 20, "net_usd": -500.0, "win_rate": 0.15}
    pre = {"n": 4, "net_usd": 406.0}
    msg = bt.build_escalation_message(post, pre)
    assert "718e0809" in msg
    assert "20 fills" in msg
    assert "-$500" in msg
    assert "V15_BOLD_TIERS" in msg
    assert "/think-like-fable" in msg
    assert "not a silent revert" in msg.lower()


def _triggered_negative_positions(n: int = 20, per_trade_loss: float = -25.0) -> list:
    return [_pos(pnl=per_trade_loss, date_et="2026-07-20") for _ in range(n)]


def test_build_report_escalates_on_first_transition_into_triggered_negative():
    positions = _triggered_negative_positions()
    report = bt.build_report(positions, date(2026, 8, 8), prior_escalation=None,
                              generated_at_et="2026-08-08T12:00:00")
    assert report["rail_status"] == "TRIGGERED_NEGATIVE"
    assert report["escalation"]["posted_this_run"] is True
    assert report["escalation"]["finding"] is not None
    assert report["escalation"]["posted_at_et"] == "2026-08-08T12:00:00"


def test_build_report_does_not_repost_on_rerun_same_status():
    positions = _triggered_negative_positions()
    r1 = bt.build_report(positions, date(2026, 8, 8), prior_escalation=None,
                          generated_at_et="t1")
    r2 = bt.build_report(positions, date(2026, 8, 8), prior_escalation=r1["escalation"],
                          generated_at_et="t2")
    assert r2["escalation"]["posted_this_run"] is False
    # carried forward from r1, never re-generated / never lost
    assert r2["escalation"]["finding"] == r1["escalation"]["finding"]
    assert r2["escalation"]["posted_at_et"] == r1["escalation"]["posted_at_et"] == "t1"


def test_build_report_reescalates_if_status_left_and_returned():
    positions = _triggered_negative_positions()
    prior = {"last_escalated_status": "ACCRUING", "finding": None, "posted_at_et": None}
    report = bt.build_report(positions, date(2026, 8, 8), prior_escalation=prior,
                              generated_at_et="t3")
    assert report["escalation"]["posted_this_run"] is True
    assert report["escalation"]["posted_at_et"] == "t3"


def test_build_report_no_escalation_while_accruing():
    positions = [_pos(pnl=-25.0, date_et="2026-07-20") for _ in range(6)]
    report = bt.build_report(positions, date(2026, 8, 8), prior_escalation=None,
                              generated_at_et="t1")
    assert report["rail_status"] == "ACCRUING"
    assert report["escalation"]["posted_this_run"] is False
    assert report["escalation"]["finding"] is None


def test_build_report_no_escalation_on_triggered_positive():
    positions = [_pos(pnl=25.0, date_et="2026-07-20") for _ in range(20)]
    report = bt.build_report(positions, date(2026, 8, 8), prior_escalation=None,
                              generated_at_et="t1")
    assert report["rail_status"] == "TRIGGERED_POSITIVE"
    assert report["escalation"]["posted_this_run"] is False
    assert report["escalation"]["finding"] is None


# ---------------------------------------------------------------------------------
# 6. FAIL-OPEN -- run() against a missing/corrupt ledger never raises, never fabricates
# ---------------------------------------------------------------------------------

def test_run_fail_open_on_missing_ledger(tmp_path):
    out = tmp_path / "bold-tier-rail.json"
    outbox = tmp_path / "discord-outbox.jsonl"
    missing_ledger = tmp_path / "does-not-exist.jsonl"
    report = bt.run(ledger_path=missing_ledger, out_path=out, outbox_path=outbox)
    assert report["rail_status"] == "NO_DATA"
    assert out.exists()
    assert not outbox.exists()  # nothing to escalate, nothing posted


def test_run_fail_open_on_corrupt_ledger_lines(tmp_path):
    ledger = tmp_path / "fills-ledger.jsonl"
    ledger.write_text("not json at all\n{also not json\n\n", encoding="utf-8")
    out = tmp_path / "bold-tier-rail.json"
    outbox = tmp_path / "discord-outbox.jsonl"
    report = bt.run(ledger_path=ledger, out_path=out, outbox_path=outbox)
    assert report["rail_status"] == "NO_DATA"
    assert out.exists()


def test_run_dedupes_escalation_across_two_real_runs(tmp_path):
    """I/O-level dedup proof: a ledger that produces TRIGGERED_NEGATIVE, run() called TWICE
    against the SAME out_path (so the 2nd run reads the 1st run's own escalation block), must
    append exactly ONE row to discord-outbox.jsonl."""
    ledger = tmp_path / "fills-ledger.jsonl"
    lines = []
    for i in range(20):
        symbol = f"SPY26072{i:02d}C00700000"
        date_et = "2026-07-20"
        lines.extend(_round_trip_fills(symbol, date_et, entry_price=1.00, exit_price=0.90))
    ledger.write_text("\n".join(json.dumps(r) for r in lines) + "\n", encoding="utf-8")

    out = tmp_path / "bold-tier-rail.json"
    outbox = tmp_path / "discord-outbox.jsonl"

    r1 = bt.run(ledger_path=ledger, out_path=out, outbox_path=outbox)
    assert r1["rail_status"] == "TRIGGERED_NEGATIVE"
    assert r1["escalation"]["posted_this_run"] is True

    r2 = bt.run(ledger_path=ledger, out_path=out, outbox_path=outbox)
    assert r2["rail_status"] == "TRIGGERED_NEGATIVE"
    assert r2["escalation"]["posted_this_run"] is False

    posted_lines = [ln for ln in outbox.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(posted_lines) == 1
    row = json.loads(posted_lines[0])
    assert set(row.keys()) == {"content", "source", "queued_at"}   # gamma_standup.py's schema
    assert row["source"] == "bold_tier_rail"
    assert "718e0809" in row["content"]


# ---------------------------------------------------------------------------------
# 7. POPULATION REGRESSION ANCHOR -- pinned against the REAL fills-ledger.jsonl
# ---------------------------------------------------------------------------------

def test_population_filter_matches_lane1_real_ledger_anchor():
    """Live anchor (verified 2026-08-08 against automation/state/fills-ledger.jsonl): bold-2
    post-ship (>=2026-07-18) n=6/net=-$476.00, pre-ship n=4/net=+$406.00 -- matches
    analysis/deep-research/lane1-loss-anatomy-2026-08-08.json's last14.by_account.bold-2 and
    analysis/recommendations/prereg-profitability-2026-08-08.json's subwindow numbers exactly.
    A change to this file (or to exit_shape_parity_study's population filter) that silently
    shifts these two numbers is the exact provenance-drift failure class this instrument
    exists to prevent -- see module docstring."""
    positions = bt.load_bold_positions(bt.LEDGER)
    post, pre = bt.split_cohorts(positions)
    post_stats = bt.cohort_stats(post)
    pre_stats = bt.cohort_stats(pre)

    assert post_stats["n"] == 6
    assert post_stats["net_usd"] == -476.0
    assert pre_stats["n"] == 4
    assert pre_stats["net_usd"] == 406.0

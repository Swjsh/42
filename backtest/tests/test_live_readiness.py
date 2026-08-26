"""Guard for setup/scripts/live_readiness.py -- the per-arm LIVE-MONEY READINESS instrument
that computes CLAUDE.md's 4-condition live threshold (>=20 trades, WR>=45%, positive
expectancy, <=2 rule breaks) per arm. Built 2026-08-18 to close ROADMAP.md Gate 2's
"criterion partially undefined" gap -- this file is what proves the instrument is not
vacuous.

WHAT THIS PINS (boundary conditions named explicitly in the build task):
  1. n_trades: 19 FAILS, 20 PASSES (>=, not >).
  2. win_rate: 44.9% FAILS, 45.0% PASSES (>=, not >).
  3. expectancy: exactly $0.00 FAILS -- the doctrine says "positive", not "non-negative".
  4. rule_breaks: 2 PASSES, 3 FAILS (<=, not <).
  5. Zero-trade arms report INSUFFICIENT, never a fabricated 0% win rate.
  6. The unattributed-rule-break path: rule-breaks.jsonl carries no arm/account key today
     (confirmed against the real ledger) -- every arm's rule_breaks criterion must come back
     None/UNKNOWN, with a note, never silently 0 or silently dropped.
  7. Arm-roster derivation: accounts.json is read fresh every call (status=='active' AND
     account_number starts with 'PA') -- retired arms and non-PA futures arms must NOT
     appear, and this must never be a hardcoded list.

Fast and offline throughout: every test either calls a pure function with synthetic dicts,
or drives build_report() against tmp_path fixture files. No live ledger under
automation/state/ is ever read by this file.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_live_readiness.py -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import live_readiness as lr  # noqa: E402


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(json.dumps(r) for r in rows)
    path.write_text(text + ("\n" if rows else ""), encoding="utf-8")


def _trip(pnl: float, ts: str, date: str | None = None) -> dict:
    """Synthetic fills_fifo-shaped round trip -- only the keys score_round_trips reads."""
    return {"real_pnl": pnl, "entry_ts_et": ts, "date": date or ts[:10]}


# ------------------------------------------------------------------------------------- #
# 1. n_trades boundary -- 19 vs 20
# ------------------------------------------------------------------------------------- #
def test_criterion_n_trades_boundary():
    assert lr.criterion_n_trades(19) is False
    assert lr.criterion_n_trades(20) is True


def test_score_round_trips_n_trades_boundary_end_to_end():
    """Same boundary, through the full scorer -- every trip is a clean win so n_trades is
    the ONLY criterion that can differ between 19 and 20 trips."""
    def make_trips(n):
        return [_trip(10.0, f"2026-06-{(i % 28) + 1:02d}T10:00:00") for i in range(n)]

    scored_19 = lr.score_round_trips(make_trips(19), 0, "0 total rule breaks logged (book-wide)")
    scored_20 = lr.score_round_trips(make_trips(20), 0, "0 total rule breaks logged (book-wide)")
    assert scored_19["criteria"]["n_trades"]["pass"] is False
    assert scored_19["overall_verdict"] == "FAIL"
    assert scored_20["criteria"]["n_trades"]["pass"] is True
    assert scored_20["overall_verdict"] == "PASS"


# ------------------------------------------------------------------------------------- #
# 2. win_rate boundary -- 44.9% vs 45.0%
# ------------------------------------------------------------------------------------- #
def test_criterion_win_rate_boundary():
    assert lr.criterion_win_rate(0.449) is False
    assert lr.criterion_win_rate(0.45) is True


def test_score_round_trips_win_rate_boundary_end_to_end():
    """20 trades, 9 wins = 45.0% exactly -> PASS. 20 trades, 8 wins = 40.0% -> FAIL.
    (Hitting 44.9% exactly needs a non-round trade count; the pure-function test above
    already pins the literal 44.9%/45.0% boundary -- this proves the wiring at a real n.)"""
    wins9 = [_trip(1.0, f"2026-06-{i + 1:02d}T10:00:00") for i in range(9)]
    losses11 = [_trip(-1.0, f"2026-06-{i + 1:02d}T11:00:00") for i in range(11)]
    scored = lr.score_round_trips(wins9 + losses11, 0, "clean")
    assert scored["win_rate"] == 0.45
    assert scored["criteria"]["win_rate"]["pass"] is True

    wins8 = [_trip(1.0, f"2026-06-{i + 1:02d}T10:00:00") for i in range(8)]
    losses12 = [_trip(-1.0, f"2026-06-{i + 1:02d}T11:00:00") for i in range(12)]
    scored2 = lr.score_round_trips(wins8 + losses12, 0, "clean")
    assert scored2["criteria"]["win_rate"]["pass"] is False


# ------------------------------------------------------------------------------------- #
# 3. expectancy exactly 0 must FAIL
# ------------------------------------------------------------------------------------- #
def test_criterion_expectancy_zero_fails():
    assert lr.criterion_expectancy(0.0) is False
    assert lr.criterion_expectancy(0.01) is True
    assert lr.criterion_expectancy(-0.01) is False


def test_score_round_trips_expectancy_exactly_zero_end_to_end():
    """20 trades, WR=50% (PASSES on its own), but every win/loss pair nets to exactly
    $0.00 mean -- expectancy must FAIL, and that alone must sink the overall verdict to
    FAIL even though n_trades and win_rate both individually pass."""
    trips = ([_trip(5.0, f"2026-06-{i + 1:02d}T10:00:00") for i in range(10)]
             + [_trip(-5.0, f"2026-06-{i + 1:02d}T11:00:00") for i in range(10)])
    scored = lr.score_round_trips(trips, 0, "clean")
    assert scored["expectancy"] == 0.0
    assert scored["criteria"]["n_trades"]["pass"] is True
    assert scored["criteria"]["win_rate"]["pass"] is True
    assert scored["criteria"]["expectancy"]["pass"] is False
    assert scored["overall_verdict"] == "FAIL"


# ------------------------------------------------------------------------------------- #
# 3b. CONCENTRATION TERM (added 2026-08-26, OP-25 fold -- mirrors gate_expiry_check.py's
#     costing_verdict fix; live_readiness.py was explicitly named as a candidate in
#     MONITORING-INSTRUMENTS-LACK-CONCENTRATION-GUARDS). A positive mean that does NOT
#     survive dropping the top-3 winning trades must downgrade PASS -> PASS_CONCENTRATED,
#     and must NEVER touch a FAIL/UNKNOWN/INSUFFICIENT verdict (downgrade-only).
# ------------------------------------------------------------------------------------- #
def test_score_round_trips_concentration_downgrades_pass():
    """20 trades: 3 big winners (+100 each) + 6 small winners (+1 each) = 9 wins (45.0% WR,
    passes), 11 losses (-27 each). Raw expectancy = 9/20 = +$0.45/tr (positive, passes) --
    but dropping the top 3 winning trades flips the cohort to -$291, so this must NOT read
    as a clean PASS."""
    wins_big = [_trip(100.0, f"2026-06-{i + 1:02d}T09:00:00") for i in range(3)]
    wins_small = [_trip(1.0, f"2026-06-{i + 4:02d}T09:00:00") for i in range(6)]
    losses = [_trip(-27.0, f"2026-06-{i + 10:02d}T10:00:00") for i in range(11)]
    trips = wins_big + wins_small + losses
    scored = lr.score_round_trips(trips, 0, "clean")
    assert scored["n_trades"] == 20
    assert scored["expectancy"] == 0.45
    assert scored["criteria"]["n_trades"]["pass"] is True
    assert scored["criteria"]["win_rate"]["pass"] is True
    assert scored["criteria"]["expectancy"]["pass"] is True
    assert scored["criteria"]["concentration"]["value"] == -291.0
    assert scored["criteria"]["concentration"]["pass"] is False
    assert scored["overall_verdict"] == "PASS_CONCENTRATED"


def test_score_round_trips_concentration_survives_stays_plain_pass():
    """20 identical +$10 winners -- dropping the top 3 still leaves +$170, comfortably
    positive, so the plain PASS (not PASS_CONCENTRATED) must be preserved. Guards against
    the concentration term over-firing on an evenly-distributed, genuinely clean book."""
    trips = [_trip(10.0, f"2026-06-{(i % 28) + 1:02d}T10:00:00") for i in range(20)]
    scored = lr.score_round_trips(trips, 0, "clean")
    assert scored["criteria"]["concentration"]["pass"] is True
    assert scored["overall_verdict"] == "PASS"


def test_score_round_trips_concentration_never_upgrades_a_fail():
    """A concentration-carried mean that ALSO fails win_rate must stay FAIL -- the
    concentration term is a downgrade-only guard, never an upgrade path."""
    wins_big = [_trip(100.0, f"2026-06-{i + 1:02d}T09:00:00") for i in range(3)]
    losses = [_trip(-10.0, f"2026-06-{i + 4:02d}T10:00:00") for i in range(17)]
    trips = wins_big + losses  # win_rate = 3/20 = 15% -- fails outright
    scored = lr.score_round_trips(trips, 0, "clean")
    assert scored["criteria"]["win_rate"]["pass"] is False
    assert scored["overall_verdict"] == "FAIL"


def test_book_wide_rollup_counts_pass_concentrated_separately():
    """arms_pass_concentrated must be counted on its own key, never silently folded into
    arms_pass (that would erase the exact distinction the verdict exists to draw)."""
    arms_out = [
        {"overall_verdict": "PASS", "n_trades": 20, "context": {"total_pnl": 10.0}},
        {"overall_verdict": "PASS_CONCENTRATED", "n_trades": 20, "context": {"total_pnl": 9.0}},
    ]
    rollup = lr._book_wide_rollup(arms_out)
    assert rollup["arms_pass"] == 1
    assert rollup["arms_pass_concentrated"] == 1


# ------------------------------------------------------------------------------------- #
# 4. rule_breaks boundary -- 2 vs 3
# ------------------------------------------------------------------------------------- #
def test_criterion_rule_breaks_boundary():
    assert lr.criterion_rule_breaks(2) is True
    assert lr.criterion_rule_breaks(3) is False
    assert lr.criterion_rule_breaks(None) is None


# ------------------------------------------------------------------------------------- #
# 5. Zero-trade arms -> INSUFFICIENT, never a fabricated 0%
# ------------------------------------------------------------------------------------- #
def test_score_round_trips_zero_trades_is_insufficient_not_zero_percent():
    scored = lr.score_round_trips([], 0, "0 total rule breaks logged (book-wide)")
    assert scored["insufficient_data"] is True
    assert scored["overall_verdict"] == "INSUFFICIENT"
    assert scored["win_rate"] is None, "must be None, never a fabricated 0.0"
    assert scored["expectancy"] is None
    assert scored["context"] is None
    assert scored["criteria"]["n_trades"]["pass"] is False
    assert scored["criteria"]["win_rate"]["pass"] is None
    assert scored["criteria"]["expectancy"]["pass"] is None


# ------------------------------------------------------------------------------------- #
# 6. Unattributed rule-break path
# ------------------------------------------------------------------------------------- #
def test_rule_breaks_for_arm_empty_ledger_is_zero_not_unknown():
    count, note = lr._rule_breaks_for_arm([], "safe-2")
    assert count == 0
    assert "empty" in note.lower()


def test_rule_breaks_for_arm_no_attribution_key_is_unknown():
    """Mirrors the REAL rule-breaks.jsonl row shape (verified 2026-08-18): no arm/account
    key anywhere on the row."""
    rows = [{
        "date": "2026-05-18", "rule_id": "RULE_3_INFRA_NAKED_PARENT",
        "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON", "trade_row": None,
        "severity": "low", "what_happened": "x", "fix_proposal": "y",
        "cost_estimate_dollars": 0, "cost_estimate_method": "n/a",
        "logged_at": "2026-05-18T16:00:02-04:00",
    }]
    count, note = lr._rule_breaks_for_arm(rows, "safe-2")
    assert count is None
    assert "book-level" in note.lower() and "unattributed" in note.lower()
    # must never silently assign it to safe-2 OR silently drop it -- the total shows up:
    assert "1 total" in note


def test_rule_breaks_for_arm_mixed_attribution_is_still_unknown():
    """One row DOES carry an arm key, one does not -- a partial guess is refused; the
    WHOLE ledger is treated as unattributable rather than half-trusted."""
    rows = [
        {"date": "2026-06-01", "rule_id": "X", "arm": "safe-2"},
        {"date": "2026-06-02", "rule_id": "Y"},
    ]
    count, note = lr._rule_breaks_for_arm(rows, "safe-2")
    assert count is None
    assert "unattributed" in note.lower()


def test_rule_breaks_for_arm_full_attribution_counts_correctly():
    """Forward-compat: IF the schema ever grows a real arm key on every row, the function
    must count precisely rather than staying stuck on UNKNOWN forever."""
    rows = [
        {"date": "2026-06-01", "rule_id": "X", "arm": "safe-2"},
        {"date": "2026-06-02", "rule_id": "Y", "arm": "bold-2"},
        {"date": "2026-06-03", "rule_id": "Z", "arm": "safe-2"},
    ]
    count, note = lr._rule_breaks_for_arm(rows, "safe-2")
    assert count == 2
    count_bold, _ = lr._rule_breaks_for_arm(rows, "bold-2")
    assert count_bold == 1


def test_score_round_trips_unattributed_rule_breaks_verdict_is_unknown_not_pass():
    """Even a PERFECT trading record (every other criterion passes) cannot reach an
    overall PASS while rule_breaks is unattributable -- CLAUDE.md's gate is a 4-condition
    AND, and this script must not overclaim the 4th condition it cannot verify."""
    trips = [_trip(50.0, f"2026-06-{(i % 28) + 1:02d}T10:00:00") for i in range(25)]
    _, note = lr._rule_breaks_for_arm([{"date": "2026-05-18", "rule_id": "X"}], "safe-2")
    scored = lr.score_round_trips(trips, None, note)
    assert scored["criteria"]["n_trades"]["pass"] is True
    assert scored["criteria"]["win_rate"]["pass"] is True
    assert scored["criteria"]["expectancy"]["pass"] is True
    assert scored["criteria"]["rule_breaks"]["pass"] is None
    assert scored["overall_verdict"] == "UNKNOWN"


# ------------------------------------------------------------------------------------- #
# 7. Arm-roster derivation -- never hardcoded
# ------------------------------------------------------------------------------------- #
def test_active_spy_arms_excludes_retired_and_futures(tmp_path):
    accounts = tmp_path / "accounts.json"
    accounts.write_text(json.dumps({"arms": [
        {"id": "fix-active-pa", "status": "active", "account_number": "PA1111111111"},
        {"id": "fix-retired-pa", "status": "retired", "account_number": "PA2222222222"},
        {"id": "fix-active-futures", "status": "active", "account_number": "5WW3333333"},
        {"id": "fix-dormant-futures", "status": "dormant", "account_number": "5WW3333333"},
    ]}), encoding="utf-8")
    roster = lr._active_spy_arms(accounts)
    assert roster == ["fix-active-pa"]


# ------------------------------------------------------------------------------------- #
# Context math -- total_pnl / median / largest win-loss / payoff ratio / consecutive losses
# ------------------------------------------------------------------------------------- #
def test_max_consecutive_losses_counts_correctly():
    # win, loss, loss, loss, win, loss -- longest streak is 3
    assert lr._max_consecutive_losses([10.0, -5.0, -5.0, -5.0, 20.0, -2.0]) == 3
    assert lr._max_consecutive_losses([10.0, 10.0, 10.0]) == 0
    assert lr._max_consecutive_losses([-1.0, -1.0]) == 2


def test_context_stats_basic_arithmetic():
    trips = [_trip(100.0, "2026-06-01T10:00:00", "2026-06-01"),
             _trip(-90.0, "2026-06-02T10:00:00", "2026-06-02"),
             _trip(50.0, "2026-06-01T11:00:00", "2026-06-01")]
    trips_sorted = sorted(trips, key=lambda t: t["entry_ts_et"])
    ctx = lr._context_stats(trips_sorted)
    assert ctx["total_pnl"] == 60.0
    assert ctx["largest_win"] == 100.0
    assert ctx["largest_loss"] == -90.0
    assert ctx["avg_win"] == 75.0  # (100+50)/2
    assert ctx["avg_loss"] == -90.0
    assert round(ctx["payoff_ratio"], 3) == round(75.0 / 90.0, 3)
    assert ctx["date_range"] == ["2026-06-01", "2026-06-02"]
    assert ctx["trading_days_represented"] == 2
    # best day is 2026-06-01 (100 + 50 = 150), which EXCEEDS total_pnl (60) since
    # 2026-06-02 was a net loss day -- share > 100% is a real, disclosed possibility.
    assert ctx["concentration"]["best_day"] == "2026-06-01"
    assert ctx["concentration"]["best_day_pnl"] == 150.0
    assert round(ctx["concentration"]["share_of_total_pnl"], 4) == round(150.0 / 60.0, 4)


def test_context_stats_zero_total_pnl_share_is_none_not_a_crash():
    trips = [_trip(10.0, "2026-06-01T10:00:00", "2026-06-01"),
             _trip(-10.0, "2026-06-02T10:00:00", "2026-06-02")]
    ctx = lr._context_stats(trips)
    assert ctx["total_pnl"] == 0.0
    assert ctx["concentration"]["share_of_total_pnl"] is None
    assert ctx["concentration"]["note"] is not None


# ------------------------------------------------------------------------------------- #
# Full wiring -- build_report() against tmp_path fixtures only, never the live ledgers
# ------------------------------------------------------------------------------------- #
def test_build_report_end_to_end_wiring(tmp_path):
    accounts = tmp_path / "accounts.json"
    accounts.write_text(json.dumps({"arms": [
        {"id": "fix-arm-a", "display_name": "FIX-A", "status": "active",
         "account_number": "PA1111111111"},
        {"id": "fix-arm-b-retired", "display_name": "FIX-B", "status": "retired",
         "account_number": "PA2222222222"},
        {"id": "fix-arm-c-futures", "display_name": "FIX-C", "status": "active",
         "account_number": "5WW3333333"},
        {"id": "fix-arm-d-empty", "display_name": "FIX-D", "status": "active",
         "account_number": "PA4444444444"},
    ]}), encoding="utf-8")

    fills = tmp_path / "fills-ledger.jsonl"
    _write_jsonl(fills, [
        {"arm": "fix-arm-a", "symbol": "SPY260801C00700000", "side": "buy", "qty": 2,
         "price": 1.00, "ts_et": "2026-08-01T10:00:00", "date_et": "2026-08-01",
         "attribution": "engine"},
        {"arm": "fix-arm-a", "symbol": "SPY260801C00700000", "side": "sell", "qty": 2,
         "price": 1.50, "ts_et": "2026-08-01T10:30:00", "date_et": "2026-08-01",
         "attribution": "engine"},
        {"arm": "fix-arm-a", "symbol": "SPY260802P00690000", "side": "buy", "qty": 3,
         "price": 0.80, "ts_et": "2026-08-02T11:00:00", "date_et": "2026-08-02",
         "attribution": "engine"},
        {"arm": "fix-arm-a", "symbol": "SPY260802P00690000", "side": "sell", "qty": 3,
         "price": 0.50, "ts_et": "2026-08-02T11:20:00", "date_et": "2026-08-02",
         "attribution": "engine"},
        # manual fill on the same arm -- must be excluded (attribution != engine), proving
        # this wiring doesn't accidentally bypass fills_fifo's own filter.
        {"arm": "fix-arm-a", "symbol": "SPY260803C00710000", "side": "buy", "qty": 1,
         "price": 1.00, "ts_et": "2026-08-03T09:00:00", "date_et": "2026-08-03",
         "attribution": "manual"},
    ])

    rule_breaks = tmp_path / "rule-breaks.jsonl"
    _write_jsonl(rule_breaks, [
        {"date": "2026-08-01", "rule_id": "RULE_TEST", "severity": "low"},
    ])

    report = lr.build_report(accounts_path=accounts, rule_breaks_path=rule_breaks,
                              fills_ledger_path=fills, now_et="2026-08-18T20:00:00")

    assert report["generated_et"] == "2026-08-18T20:00:00"
    roster = [a["arm_id"] for a in report["arms"]]
    assert roster == ["fix-arm-a", "fix-arm-d-empty"], (
        "retired + futures arms must be excluded; roster order follows accounts.json")

    arm_a = next(a for a in report["arms"] if a["arm_id"] == "fix-arm-a")
    assert arm_a["n_trades"] == 2, "the manual-attribution fill must not count as a 3rd trip"
    assert arm_a["context"]["total_pnl"] == 10.0  # +100 - 90
    assert arm_a["criteria"]["rule_breaks"]["pass"] is None
    assert "unattributed" in arm_a["criteria"]["rule_breaks"]["note"].lower()
    assert arm_a["overall_verdict"] == "UNKNOWN"

    arm_d = next(a for a in report["arms"] if a["arm_id"] == "fix-arm-d-empty")
    assert arm_d["insufficient_data"] is True
    assert arm_d["overall_verdict"] == "INSUFFICIENT"

    rollup = report["book_wide_rollup"]
    assert rollup["arms_scored"] == 2
    assert rollup["total_closed_round_trips"] == 2
    assert "CORRELATED" in rollup["_label"]


def test_build_report_writes_valid_json_shape(tmp_path):
    """Cheap smoke test that the top-level payload always has the documented keys, even on
    a roster of zero (defensive against a future empty/corrupt accounts.json fixture)."""
    accounts = tmp_path / "accounts.json"
    accounts.write_text(json.dumps({"arms": []}), encoding="utf-8")
    rule_breaks = tmp_path / "rule-breaks.jsonl"
    rule_breaks.write_text("", encoding="utf-8")
    fills = tmp_path / "fills-ledger.jsonl"
    fills.write_text("", encoding="utf-8")
    report = lr.build_report(accounts_path=accounts, rule_breaks_path=rule_breaks,
                              fills_ledger_path=fills, now_et="2026-08-18T20:00:00")
    for key in ("generated_et", "instrument", "gate_source", "thresholds", "disclosure",
                "arms", "book_wide_rollup"):
        assert key in report
    assert report["arms"] == []
    assert report["book_wide_rollup"]["arms_scored"] == 0
    # round-trip through json.dumps to prove every value is JSON-serializable
    json.dumps(report)

"""Guards for the trendline-only bypass rail.

WHY THE RAIL EXISTS: three measurements of this cohort disagree in SIGN --
PNL-ATTRIBUTION-2026-07-28 (-$1,830, WR .19, n=124), LADDER T2 2026-08-20 (-$36.79/tr,
n=137), and real fills 2026-07-02..2026-08-21 (+$14.97/tr, n=31). They measured different
windows and different definitions. The rail fixes ONE population -- real broker fills --
so the question stops being re-litigated with whichever number suits the argument.

WHAT THESE GUARDS PROTECT
  1. The rail judges on DROP-BEST-DAY, never raw net. At build time the same cohort read
     +$464 net and -$49 drop-best-day. A rail that escalated on net would have called a
     one-session cohort "profitable" -- the exact error the ATM tier rail was built to
     catch, inverted.
  2. The multi-leg join (`extra_exec`) is not dropped. Skipping it silently halves the
     cohort, and a half-sized cohort still looks like a working rail.
  3. It stays SHADOW: no order path, no params write, no live-gate import.
  4. The revert instruction stays HONEST. `trendline_bypass_scope` is backtest-only;
     production always runs "trendline_only". A rail that promises a switch which does not
     exist is worse than one that admits it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import trendline_tier_rail as R  # noqa: E402

SRC = Path(R.__file__).read_text(encoding="utf-8")
CODE = SRC.split('"""', 2)[-1]          # body only; the docstring cites files by name


def _pos(date, pnl, arm="safe-2", sym="SPY260821P00765000", ts="t"):
    return {"arm": arm, "symbol": sym, "entry_ts_utc": ts, "date_et": date,
            "actual_exit_pnl": float(pnl)}


# ---------------------------------------------------------------- concentration
def test_drop_best_day_is_computed_and_can_invert_the_headline():
    """THE trap. One session carrying the whole result must be visible, not averaged in."""
    pos = [_pos("2026-08-20", 600)] + [_pos(f"2026-08-{d:02d}", -20) for d in range(1, 8)]
    s = R.cohort_stats(pos)
    assert s["mean_usd"] > 0, "setup invalid -- raw mean should look positive"
    assert s["drop_best_day_mean_usd"] == -20.0
    assert s["top_day"] == "2026-08-20"
    assert s["top3_share_of_net"] > 1.0, "concentration >100% of net must be reportable"


def test_status_judges_on_drop_best_day_not_net():
    """A cohort that is only positive because of one session must not read as HOLDING
    on net alone -- and must not read as TRIGGERED on one bad session either."""
    big_day = [_pos("2026-08-20", 5000)] + [_pos(f"2026-07-{d:02d}", -60) for d in range(1, 25)]
    s = R.cohort_stats(big_day)
    assert s["net_usd"] > 0
    assert R.rail_status(s) == "TRIGGERED_NEGATIVE", (
        "raw net is positive but every other session loses $60 -- the rail must see that"
    )


def test_accruing_below_the_floor_and_never_triggers_early():
    s = R.cohort_stats([_pos(f"2026-08-{d:02d}", -500) for d in range(1, 6)])
    assert s["n"] == 5
    assert R.rail_status(s) == "ACCRUING", "must not verdict below n=20 however bad it looks"


def test_no_data_is_its_own_state():
    assert R.rail_status(R.cohort_stats([])) == "NO_DATA"


def test_holding_when_drop_best_day_clears_the_floor():
    s = R.cohort_stats([_pos(f"2026-07-{d:02d}", 5) for d in range(1, 26)])
    assert R.rail_status(s) == "HOLDING"


def test_the_floor_is_a_named_constant_not_a_literal():
    assert isinstance(R.DROP_BEST_MEAN_FLOOR, float)
    assert R.ESCALATION_N == 20


# ---------------------------------------------------------------- the join
def test_the_multileg_exec_path_is_present():
    assert "extra_exec" in CODE, (
        "extra_exec carries the SECOND leg of a multi-setup tick; dropping it silently "
        "halves the cohort while the rail still looks like it works"
    )
    assert 'r.get("triggers") != COHORT_TRIGGERS' in CODE
    assert R.COHORT_TRIGGERS == ["trendline_rejection"], "STRICT shape is the joinable one"


def test_it_reuses_the_shared_position_definition():
    assert "exit_shape_parity_study" in CODE and "reconstruct_positions" in CODE, (
        "positions must come from the ONE shared definition, never re-derived"
    )
    assert "entry_ts_utc" in CODE, "the (arm, symbol, entry_ts_utc) back-pointer is the join"


# ---------------------------------------------------------------- shadow-ness
def test_it_can_never_trade_or_write_params():
    for bad in ("place_option_order", "submit_order", "cancel_order",
                "params.json", "aggressive/params"):
        assert bad not in CODE, f"rail reaches a live surface: {bad}"


def test_the_only_files_it_writes_are_its_own_report_and_the_outbox():
    writes = [ln.strip() for ln in CODE.splitlines()
              if ".write_text(" in ln or '.open("a"' in ln]
    assert writes
    for ln in writes:
        assert "tmp" in ln or "outbox" in ln, f"unexpected write target: {ln}"


def test_the_report_is_written_atomically():
    assert "tmp.replace(out_path)" in CODE, "a half-written report must never be readable"


# ---------------------------------------------------------------- honesty
def test_the_revert_instruction_admits_there_is_no_live_switch():
    assert "backtest-only" in R.REVERT_INSTRUCTION
    assert "midday_trendline_gate" in R.REVERT_INSTRUCTION, (
        "the rail must name the lever that IS live-reachable, not just the one that isn't"
    )


def test_escalation_does_not_repost_on_a_held_status():
    prior = {"escalation": {"last_escalated_status": "TRIGGERED_NEGATIVE",
                            "finding": "already said", "posted_at_et": "2026-08-01T00:00:00"}}
    pos = [_pos("2026-08-20", 100)] + [_pos(f"2026-07-{d:02d}", -60) for d in range(1, 25)]
    rep = R.build_report(pos, [], generated_at_et="2026-08-21T17:00:00", prior=prior)
    assert rep["rail_status"] == "TRIGGERED_NEGATIVE"
    assert rep["escalation"]["posted_this_run"] is False, "must not repost the same state"
    assert rep["escalation"]["finding"] == "already said", "must carry the prior finding forward"


def test_escalation_fires_on_the_transition_in():
    pos = [_pos("2026-08-20", 100)] + [_pos(f"2026-07-{d:02d}", -60) for d in range(1, 25)]
    rep = R.build_report(pos, [], generated_at_et="2026-08-21T17:00:00", prior=None)
    assert rep["escalation"]["posted_this_run"] is True
    assert "midday_trendline_gate" in rep["escalation"]["finding"]


def test_report_always_carries_the_concentration_warning():
    rep = R.build_report([_pos("2026-08-20", 10)], [], generated_at_et="x")
    joined = " ".join(rep["warnings"])
    assert "drop_best_day_mean_usd" in joined and "net_usd alone" in joined


def test_same_session_comparison_is_reported_separately():
    """The cohorts span different date ranges; the raw means are not comparable until the
    rest of the book is restricted to the trendline cohort's own sessions."""
    tl = [_pos("2026-08-20", 10)]
    other = [_pos("2026-08-20", -50), _pos("2026-06-01", 900)]
    rep = R.build_report(tl, other, generated_at_et="x")
    assert rep["rest_of_book_same_sessions"]["n"] == 1
    assert rep["rest_of_book_same_sessions"]["mean_usd"] == -50.0
    assert rep["rest_of_book"]["n"] == 2


# ---------------------------------------------------------------- live anchor
def test_live_cohort_anchor_window_bounded():
    """Window-bounded to the verification date. The bold rail's anchor originally pinned
    the WHOLE growing ledger, drifted as fills arrived, and sat RED for days catching
    nothing -- 'the ledger grew' and 'the join broke' must not report identically."""
    tl, other = R.load_cohorts()
    if not tl:
        return                                   # ledger absent in this environment
    bounded = [p for p in tl if p["date_et"] <= "2026-08-21"]
    s = R.cohort_stats(bounded)
    assert s["n"] >= 31, f"trendline cohort shrank to {s['n']} through 2026-08-21 -- join broke?"
    assert other, "rest-of-book cohort empty -- the partition is wrong"

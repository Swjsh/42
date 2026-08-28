"""Guard: intervention_counter.py (TASK B2 instrument 1/3).

Pins three things:
  1. classify_round_trips's category logic (fully_engine / manual_both /
     engine_entered_manual_exit / manual_entered_engine_exit / crypto_excluded)
     against synthetic fills covering every branch.
  2. summarize()'s bucketing (all_time / since_target_start / today) and that
     it never fabricates a counterfactual P&L (C7 -- must stay null).
  3. STATUS.md escalation follows the create-if-missing pattern (2026-08-20
     outage fix): the report must land even when '## Known broken' is
     entirely absent, must not duplicate the heading when it exists, and
     must NEVER fire on a day with zero new interventions.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import intervention_counter as ic  # noqa: E402

MARKER = "## Known broken"
NO_SECTION = "## [2026-08-20 10:00 ET] a dated entry and nothing else\nfiller\n"


def _fill(activity_id, arm, symbol, side, qty, price, date_et, ts_et, attribution,
          is_crypto=False, is_option=True):
    return {
        "activity_id": activity_id, "arm": arm, "order_id": f"ord-{activity_id}",
        "symbol": symbol, "side": side, "qty": qty, "price": price, "multiplier": 100,
        "is_crypto": is_crypto, "is_option": is_option, "ts_utc": f"{date_et}T14:00:00Z",
        "ts_et": ts_et, "date_et": date_et, "attribution": attribution,
    }


def test_classify_fully_engine_is_not_an_intervention():
    fills = [
        _fill("e1", "safe-2", "SPY260828C00770000", "buy", 3, 1.0,
              "2026-08-28", "2026-08-28T09:35:00", "engine"),
        _fill("e2", "safe-2", "SPY260828C00770000", "sell", 3, 1.5,
              "2026-08-28", "2026-08-28T10:00:00", "engine"),
    ]
    out = ic.classify_round_trips(fills)
    assert len(out) == 1
    assert out[0]["category"] == "fully_engine"
    assert out[0]["is_intervention"] is False


def test_classify_manual_both():
    fills = [
        _fill("m1", "bold-2", "SPY260828P00760000", "buy", 5, 1.0,
              "2026-08-28", "2026-08-28T09:45:00", "manual"),
        _fill("m2", "bold-2", "SPY260828P00760000", "sell", 5, 0.8,
              "2026-08-28", "2026-08-28T09:51:00", "manual"),
    ]
    out = ic.classify_round_trips(fills)
    assert out[0]["category"] == "manual_both"
    assert out[0]["is_intervention"] is True


def test_classify_engine_entered_manual_exit_is_the_cuts_winners_pattern():
    """The specific risk pattern the audit named: engine opens, J closes early."""
    fills = [
        _fill("g1", "safe-2", "SPY260828C00771000", "buy", 3, 1.2,
              "2026-08-28", "2026-08-28T09:36:00", "engine"),
        _fill("g2", "safe-2", "SPY260828C00771000", "sell", 3, 1.3,
              "2026-08-28", "2026-08-28T09:40:00", "manual"),
    ]
    out = ic.classify_round_trips(fills)
    assert out[0]["category"] == "engine_entered_manual_exit"
    assert out[0]["is_intervention"] is True


def test_classify_manual_entered_engine_exit_is_flagged_anomalous():
    fills = [
        _fill("a1", "bold-2", "SPY260828P00761000", "buy", 2, 0.9,
              "2026-08-28", "2026-08-28T09:37:00", "manual"),
        _fill("a2", "bold-2", "SPY260828P00761000", "sell", 2, 1.1,
              "2026-08-28", "2026-08-28T09:42:00", "engine"),
    ]
    out = ic.classify_round_trips(fills)
    assert out[0]["category"] == "manual_entered_engine_exit"
    assert out[0]["is_intervention"] is True


def test_crypto_always_excluded_never_counted_as_spy_intervention():
    fills = [
        _fill("c1", "safe-3", "ETH/USD", "buy", 0.1, 1500.0,
              "2026-06-30", "2026-06-30T21:16:30", "manual", is_crypto=True, is_option=False),
        _fill("c2", "safe-3", "ETH/USD", "sell", 0.1, 1490.0,
              "2026-06-30", "2026-06-30T21:17:20", "manual", is_crypto=True, is_option=False),
    ]
    out = ic.classify_round_trips(fills)
    assert out[0]["category"] == "crypto_excluded"
    assert out[0]["is_intervention"] is False
    summary = ic.summarize(out)
    assert summary["all_time"]["n_round_trips"] == 0
    assert summary["crypto_excluded"]["n_round_trips"] == 1


def test_summarize_never_fabricates_counterfactual_pnl():
    fills = [
        _fill("m1", "bold-2", "SPY260828P00760000", "buy", 5, 1.0,
              "2026-08-28", "2026-08-28T09:45:00", "manual"),
        _fill("m2", "bold-2", "SPY260828P00760000", "sell", 5, 0.8,
              "2026-08-28", "2026-08-28T09:51:00", "manual"),
    ]
    summary = ic.summarize(ic.classify_round_trips(fills))
    assert summary["counterfactual_pnl"] is None
    assert "not reconstructable" in summary["counterfactual_note"].lower()


def test_summarize_buckets_today_and_target_window_correctly():
    import datetime as dt
    fills = [
        # old intervention -- counts all_time, not since_target, not today
        _fill("o1", "safe-2", "SPY260701P00742000", "buy", 5, 1.22,
              "2026-07-01", "2026-07-01T09:45:21", "manual"),
        _fill("o2", "safe-2", "SPY260701P00742000", "sell", 5, 0.79,
              "2026-07-01", "2026-07-01T09:51:35", "manual"),
        # today's intervention -- counts all three buckets
        _fill("t1", "bold-2", "SPY260828C00772000", "buy", 2, 1.0,
              "2026-08-28", "2026-08-28T10:00:00", "manual"),
        _fill("t2", "bold-2", "SPY260828C00772000", "sell", 2, 1.4,
              "2026-08-28", "2026-08-28T10:05:00", "manual"),
    ]
    now_et = dt.datetime(2026, 8, 28, 16, 20, 0)
    summary = ic.summarize(ic.classify_round_trips(fills), now_et=now_et)
    assert summary["all_time"]["n_round_trips"] == 2
    # target_start_date is 2026-09-01 -- 2026-08-28 is BEFORE it, so neither event counts yet.
    assert summary["since_target_start"]["n_round_trips"] == 0
    assert summary["today"]["n_round_trips"] == 1
    assert summary["today"]["by_arm"] == {"bold-2": 1}


def test_since_target_start_counts_an_intervention_on_or_after_target_date():
    import datetime as dt
    fills = [
        _fill("s1", "safe-2", "SPY260901C00770000", "buy", 2, 1.0,
              "2026-09-01", "2026-09-01T09:40:00", "manual"),
        _fill("s2", "safe-2", "SPY260901C00770000", "sell", 2, 0.9,
              "2026-09-01", "2026-09-01T09:44:00", "manual"),
    ]
    now_et = dt.datetime(2026, 9, 1, 16, 0, 0)
    summary = ic.summarize(ic.classify_round_trips(fills), now_et=now_et)
    assert summary["since_target_start"]["n_round_trips"] == 1
    assert summary["today"]["n_round_trips"] == 1


def test_run_end_to_end_writes_summary_json(tmp_path):
    fills_path = tmp_path / "fills-ledger.jsonl"
    rows = [
        _fill("e1", "safe-2", "SPY260828C00770000", "buy", 3, 1.0,
              "2026-08-28", "2026-08-28T09:35:00", "engine"),
        _fill("e2", "safe-2", "SPY260828C00770000", "sell", 3, 1.5,
              "2026-08-28", "2026-08-28T10:00:00", "engine"),
    ]
    fills_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    out_path = tmp_path / "summary.json"
    status_md = tmp_path / "STATUS.md"
    status_md.write_text(NO_SECTION, encoding="utf-8")
    summary = ic.run(fills_path=fills_path, out_path=out_path, status_md=status_md)
    assert out_path.exists()
    on_disk = json.loads(out_path.read_text(encoding="utf-8"))
    assert on_disk["all_time"]["n_round_trips"] == summary["all_time"]["n_round_trips"]


# --------------------------------------------------------------------------- #
# STATUS.md escalation -- mirrors test_status_known_broken_section_2026_08_20.py
# --------------------------------------------------------------------------- #

def _summary_with_one_today_intervention():
    return {
        "generated_at_et": "2026-08-28T16:20:00", "date_et": "2026-08-28",
        "today": {"n_round_trips": 1, "by_category": {"manual_both": 1},
                   "by_arm": {"safe-2": 1}, "realized_pnl": -12.0},
    }


def test_status_report_lands_even_with_no_section(tmp_path):
    p = tmp_path / "STATUS.md"
    p.write_text(NO_SECTION, encoding="utf-8")
    fired = ic._flag_status_md(_summary_with_one_today_intervention(), status_md=p)
    assert fired is True
    after = p.read_text(encoding="utf-8")
    assert MARKER in after, (
        "did not create '## Known broken' when it was missing -- the exact 2026-08-20 outage "
        "class. Recreate the section instead of returning early.")
    assert "INTERVENTION-COUNTER" in after


def test_status_report_lands_when_section_exists_and_does_not_duplicate(tmp_path):
    p = tmp_path / "STATUS.md"
    p.write_text(MARKER + "\n\n- an older escalation\n\n" + NO_SECTION, encoding="utf-8")
    ic._flag_status_md(_summary_with_one_today_intervention(), status_md=p)
    after = p.read_text(encoding="utf-8")
    assert after.count(MARKER) == 1
    assert "- an older escalation" in after
    assert "INTERVENTION-COUNTER" in after


def test_status_never_fires_on_zero_new_interventions_today(tmp_path):
    p = tmp_path / "STATUS.md"
    p.write_text(NO_SECTION, encoding="utf-8")
    zero_summary = {
        "generated_at_et": "2026-08-28T16:20:00", "date_et": "2026-08-28",
        "today": {"n_round_trips": 0, "by_category": {}, "by_arm": {}, "realized_pnl": 0.0},
    }
    fired = ic._flag_status_md(zero_summary, status_md=p)
    assert fired is False
    assert p.read_text(encoding="utf-8") == NO_SECTION


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))

"""Guards for the multi-symbol lane's journaling + status surface:
  multi/lib/journal.py        -- append-only entry/exit CSV for multi-day holds
  setup/scripts/multi_status.py -- the one-glance "how is the lane doing" report

LANE `multi-symbol`, ARM `multi-1`, account PA38EG1JTFBT. See both modules' docstrings for
the full design rationale (why a same-day schema like journal/trades.csv cannot represent a
multi-day hold, and why account equity must never stand in for this lane's P&L).

No network. No writes outside `tmp_path` -- every test points `journal.append_entry`/
`append_exit`/`open_trades`/`closed_trades` and `multi_status.build_status` at a `tmp_path`
file via their explicit `path=`/`journal_path=` keyword rather than the real
`journal/trades-multi.csv` or `automation/state/multi/*.jsonl`.

Run:  backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_multi_journal.py -q
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "setup" / "scripts")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from multi.lib import journal as mj  # noqa: E402
import multi_status as ms  # noqa: E402

ET = ZoneInfo("America/New_York")


def _et(y, mo, d, h=10, mi=0, s=0):
    return dt.datetime(y, mo, d, h, mi, s, tzinfo=ET)


# =========================================================================================
# 1. trading_sessions_held -- the Fri->Mon discriminator named explicitly in the task brief
# =========================================================================================

def test_trading_sessions_friday_to_monday_is_one_not_three():
    # 2026-08-14 is a Friday, 2026-08-17 is the following Monday: 3 calendar days apart,
    # but only ONE trading session (Sat/Sun are not sessions) elapses.
    entry = dt.date(2026, 8, 14)
    exit_ = dt.date(2026, 8, 17)
    assert (exit_ - entry).days == 3  # sanity: the naive-wrong answer really is 3
    assert mj.trading_sessions_held(entry, exit_) == 1


def test_trading_sessions_same_day_is_zero():
    d = dt.date(2026, 8, 18)
    assert mj.trading_sessions_held(d, d) == 0


def test_trading_sessions_mon_to_wed_same_week_is_two():
    assert mj.trading_sessions_held(dt.date(2026, 8, 17), dt.date(2026, 8, 19)) == 2


def test_trading_sessions_exit_before_entry_raises():
    with pytest.raises(mj.JournalError):
        mj.trading_sessions_held(dt.date(2026, 8, 17), dt.date(2026, 8, 14))


# =========================================================================================
# 2. entry + exit round trip -- links by trade_id, computes holding_period_sessions correctly
# =========================================================================================

def test_entry_exit_round_trip_links_by_trade_id_and_sessions(tmp_path):
    path = tmp_path / "trades-multi.csv"
    mj.append_entry(
        trade_id="T1", symbol="gld", contract="GLD260821C00415000", side="call",
        entry_date="2026-08-14", entry_time_et="10:05:00", entry_premium=2.10, qty=3,
        path=path,
    )
    exit_row = mj.append_exit(
        trade_id="T1", exit_date="2026-08-17", exit_time_et="11:30:00",
        exit_premium=2.45, exit_reason="tp1", path=path,
    )
    assert exit_row["trade_id"] == "T1"
    assert exit_row["row_type"] == "EXIT"
    assert exit_row["symbol"] == "GLD"  # denormalized forward from the ENTRY row
    assert exit_row["contract"] == "GLD260821C00415000"
    assert exit_row["holding_period_sessions"] == "1"  # Fri->Mon

    rows = mj.all_rows(path)
    assert len(rows) == 2
    assert rows[0]["row_type"] == "ENTRY"
    assert rows[1]["row_type"] == "EXIT"
    assert rows[0]["trade_id"] == rows[1]["trade_id"] == "T1"

    # Once exited, the trade must no longer appear as open.
    assert mj.open_trades(path) == []
    closed = mj.closed_trades(path)
    assert len(closed) == 1 and closed[0]["trade_id"] == "T1"


def test_open_trades_excludes_exited_includes_still_open(tmp_path):
    path = tmp_path / "trades-multi.csv"
    mj.append_entry(trade_id="A", symbol="QQQ", contract="QQQ260821C00600000", side="C",
                     entry_date="2026-08-17", entry_time_et="10:00:00", entry_premium=1.00,
                     qty=3, path=path)
    mj.append_entry(trade_id="B", symbol="SOFI", contract="SOFI260821P00012000", side="P",
                     entry_date="2026-08-18", entry_time_et="10:00:00", entry_premium=0.50,
                     qty=5, path=path)
    mj.append_exit(trade_id="A", exit_date="2026-08-18", exit_time_et="14:00:00",
                    exit_premium=1.20, exit_reason="tp1", path=path)

    open_now = mj.open_trades(path)
    assert len(open_now) == 1
    assert open_now[0]["trade_id"] == "B"


def test_exit_with_no_matching_entry_raises(tmp_path):
    path = tmp_path / "trades-multi.csv"
    with pytest.raises(mj.JournalError, match="no ENTRY row"):
        mj.append_exit(trade_id="GHOST", exit_date="2026-08-18", exit_time_et="10:00:00",
                        exit_premium=1.0, exit_reason="tp1", path=path)


def test_double_exit_raises(tmp_path):
    path = tmp_path / "trades-multi.csv"
    mj.append_entry(trade_id="T2", symbol="IWM", contract="IWM260821C00230000", side="C",
                     entry_date="2026-08-17", entry_time_et="10:00:00", entry_premium=1.0,
                     qty=3, path=path)
    mj.append_exit(trade_id="T2", exit_date="2026-08-18", exit_time_et="10:00:00",
                    exit_premium=1.1, exit_reason="tp1", path=path)
    with pytest.raises(mj.JournalError, match="already has an EXIT"):
        mj.append_exit(trade_id="T2", exit_date="2026-08-19", exit_time_et="10:00:00",
                        exit_premium=1.2, exit_reason="tp1", path=path)


def test_duplicate_entry_raises(tmp_path):
    path = tmp_path / "trades-multi.csv"
    mj.append_entry(trade_id="T3", symbol="BAC", contract="BAC260821C00045000", side="C",
                     entry_date="2026-08-17", entry_time_et="10:00:00", entry_premium=0.9,
                     qty=3, path=path)
    with pytest.raises(mj.JournalError, match="already has an ENTRY"):
        mj.append_entry(trade_id="T3", symbol="BAC", contract="BAC260821C00045000",
                         side="C", entry_date="2026-08-17", entry_time_et="10:05:00",
                         entry_premium=0.95, qty=3, path=path)


# =========================================================================================
# 3. pnl math -- exact numbers, both call and put (long-premium-only, same formula both sides)
# =========================================================================================

def test_pnl_math_call_exact(tmp_path):
    path = tmp_path / "trades-multi.csv"
    mj.append_entry(trade_id="CALL1", symbol="GLD", contract="GLD260821C00415000", side="C",
                     entry_date="2026-08-14", entry_time_et="10:00:00", entry_premium=2.10,
                     qty=3, path=path)
    row = mj.append_exit(trade_id="CALL1", exit_date="2026-08-17", exit_time_et="10:00:00",
                          exit_premium=2.45, exit_reason="tp1", path=path)
    # (2.45 - 2.10) * 3 * 100 = 105.00 exactly
    assert float(row["pnl_dollars"]) == pytest.approx(105.00, abs=1e-9)
    # 0.35 / 2.10 * 100 = 16.666...7
    assert float(row["pnl_pct"]) == pytest.approx(16.6667, abs=1e-3)


def test_pnl_math_put_exact_including_a_loss(tmp_path):
    path = tmp_path / "trades-multi.csv"
    mj.append_entry(trade_id="PUT1", symbol="QQQ", contract="QQQ260821P00580000", side="put",
                     entry_date="2026-08-17", entry_time_et="10:00:00", entry_premium=1.50,
                     qty=5, path=path)
    row = mj.append_exit(trade_id="PUT1", exit_date="2026-08-17", exit_time_et="14:00:00",
                          exit_premium=1.00, exit_reason="catastrophe_stop", path=path)
    # (1.00 - 1.50) * 5 * 100 = -250.00 exactly -- a long put losing money is a NEGATIVE
    # pnl, exactly like a long call would be; the formula does not flip sign on side.
    assert float(row["pnl_dollars"]) == pytest.approx(-250.00, abs=1e-9)
    assert float(row["pnl_pct"]) == pytest.approx(-33.3333, abs=1e-3)


def test_pnl_call_and_put_use_the_identical_formula(tmp_path):
    """Same entry/exit/qty numbers, only `side` differs -- P&L must be byte-identical,
    proving the long-premium-only formula never branches on call vs put."""
    path_c = tmp_path / "c.csv"
    path_p = tmp_path / "p.csv"
    mj.append_entry(trade_id="X", symbol="SPY", contract="SPY260821C00650000", side="C",
                     entry_date="2026-08-17", entry_time_et="10:00:00", entry_premium=1.0,
                     qty=2, path=path_c)
    mj.append_entry(trade_id="X", symbol="SPY", contract="SPY260821P00650000", side="P",
                     entry_date="2026-08-17", entry_time_et="10:00:00", entry_premium=1.0,
                     qty=2, path=path_p)
    row_c = mj.append_exit(trade_id="X", exit_date="2026-08-18", exit_time_et="10:00:00",
                            exit_premium=1.3, exit_reason="tp1", path=path_c)
    row_p = mj.append_exit(trade_id="X", exit_date="2026-08-18", exit_time_et="10:00:00",
                            exit_premium=1.3, exit_reason="tp1", path=path_p)
    assert row_c["pnl_dollars"] == row_p["pnl_dollars"]
    assert row_c["pnl_pct"] == row_p["pnl_pct"]


# =========================================================================================
# 4. CSV encoding -- UTF-8, no BOM, re-reads cleanly with a plain open(..., encoding='utf-8')
# =========================================================================================

def test_csv_is_utf8_no_bom_and_reads_cleanly_with_plain_open(tmp_path):
    path = tmp_path / "trades-multi.csv"
    mj.append_entry(trade_id="U1", symbol="NVDA", contract="NVDA260821C00185000", side="C",
                     entry_date="2026-08-17", entry_time_et="10:00:00", entry_premium=3.0,
                     qty=3, path=path)

    raw = path.read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "file must not carry a UTF-8 BOM"

    # The exact requirement from the task brief: a PLAIN open(..., encoding='utf-8') must
    # read the header's first cell as "trade_id", never "﻿trade_id".
    with open(path, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        first_row = next(reader)
    assert list(first_row.keys())[0] == "trade_id"
    assert first_row["trade_id"] == "U1"
    assert first_row["symbol"] == "NVDA"


def test_csv_header_matches_fieldnames_constant(tmp_path):
    path = tmp_path / "trades-multi.csv"
    mj.append_entry(trade_id="H1", symbol="AAPL", contract="AAPL260821C00230000", side="C",
                     entry_date="2026-08-17", entry_time_et="10:00:00", entry_premium=1.5,
                     qty=3, path=path)
    with open(path, "r", newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    assert header == list(mj.FIELDNAMES)


def test_stale_lock_is_taken_over_not_deadlocked(tmp_path):
    """A writer that crashed mid-append leaves a stale `.lock` file. The next append must
    take it over rather than hang forever -- this is the crash-safety half of 'atomic
    append; never corrupt the file on a crash.'"""
    path = tmp_path / "trades-multi.csv"
    lock_path = path.with_name(path.name + ".lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text("stale-pid-12345", encoding="utf-8")
    import os
    import time
    old = time.time() - (mj._LOCK_STALE_SEC + 5)
    os.utime(lock_path, (old, old))

    mj.append_entry(trade_id="S1", symbol="RIVN", contract="RIVN260821C00013000", side="C",
                     entry_date="2026-08-17", entry_time_et="10:00:00", entry_premium=0.5,
                     qty=10, path=path)
    assert not lock_path.exists()
    rows = mj.all_rows(path)
    assert len(rows) == 1 and rows[0]["trade_id"] == "S1"


# =========================================================================================
# 5. empty ledger reports honestly rather than crashing
# =========================================================================================

def test_open_trades_on_missing_file_is_empty_not_a_crash(tmp_path):
    path = tmp_path / "does-not-exist.csv"
    assert mj.open_trades(path) == []
    assert mj.closed_trades(path) == []
    assert mj.all_rows(path) == []


def test_status_on_completely_empty_state_dir_does_not_crash(tmp_path):
    params_path = tmp_path / "params.json"
    params_path.write_text(json.dumps({"shadow_only": True, "live": False,
                                       "account": {"account_number": "PA38EG1JTFBT"}}),
                            encoding="utf-8")
    status = ms.build_status(
        now=_et(2026, 8, 19, 11, 0, 0),
        params_path=params_path,
        ledger_path=tmp_path / "shadow-ledger.jsonl",       # does not exist
        cascade_path=tmp_path / "participation-cascade.jsonl",  # does not exist
        journal_path=tmp_path / "trades-multi.csv",          # does not exist
    )
    assert status["open_positions"] == []
    assert status["cascade"] is None
    assert status["top_blocking_gate"] is None
    assert status["watchlist_top"] == []
    assert status["ledger_health"]["status"] == "NO_DATA"
    assert status["realized_pnl_today_dollars"] == 0.0
    # Must render to text without raising, too.
    table = ms.format_table(status)
    assert "NO DATA" in table or "NO_DATA" in table or "no cascade rows" in table


# =========================================================================================
# 6. stale ledger is reported STALE, never silently healthy -- RED-PROOFED separately
# =========================================================================================

def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")


def test_fresh_ledger_reports_fresh(tmp_path):
    path = tmp_path / "shadow-ledger.jsonl"
    now = _et(2026, 8, 19, 13, 0, 0)
    last_ts = (now - dt.timedelta(minutes=5)).isoformat(timespec="seconds")
    _write_jsonl(path, [{"ts_et": last_ts, "symbol": "GLD"}])
    health = ms.ledger_freshness(now, path=path)
    assert health["status"] == "FRESH"
    assert health["age_minutes"] == pytest.approx(5.0, abs=0.1)


def test_stale_ledger_reports_stale_not_fresh(tmp_path):
    """RED-PROOF target: a scheduled task that silently died must never read as healthy.
    A ledger whose newest row is 3 hours old (threshold is 90 min) must report STALE."""
    path = tmp_path / "shadow-ledger.jsonl"
    now = _et(2026, 8, 19, 13, 0, 0)
    last_ts = (now - dt.timedelta(hours=3)).isoformat(timespec="seconds")
    _write_jsonl(path, [{"ts_et": last_ts, "symbol": "QQQ"}])
    health = ms.ledger_freshness(now, path=path)
    assert health["status"] == "STALE"
    assert health["age_minutes"] == pytest.approx(180.0, abs=0.1)


def test_stale_ledger_status_flows_into_full_status_report(tmp_path):
    ledger_path = tmp_path / "shadow-ledger.jsonl"
    now = _et(2026, 8, 19, 13, 0, 0)
    last_ts = (now - dt.timedelta(hours=4)).isoformat(timespec="seconds")
    _write_jsonl(ledger_path, [{"ts_et": last_ts, "symbol": "GLD", "rel_volume": 2.1,
                                "decision": "HOLD"}])
    params_path = tmp_path / "params.json"
    params_path.write_text(json.dumps({"shadow_only": True, "live": False,
                                       "account": {"account_number": "PA38EG1JTFBT"}}),
                            encoding="utf-8")
    status = ms.build_status(
        now=now, params_path=params_path, ledger_path=ledger_path,
        cascade_path=tmp_path / "participation-cascade.jsonl",
        journal_path=tmp_path / "trades-multi.csv",
    )
    assert status["ledger_health"]["status"] == "STALE"
    table = ms.format_table(status)
    assert "STALE" in table


# =========================================================================================
# 7. status output never presents account equity as lane P&L
# =========================================================================================

def test_realized_pnl_never_derived_from_equity(tmp_path):
    journal_path = tmp_path / "trades-multi.csv"
    mj.append_entry(trade_id="E1", symbol="GLD", contract="GLD260821C00415000", side="C",
                     entry_date="2026-08-17", entry_time_et="10:00:00", entry_premium=2.0,
                     qty=3, path=journal_path)
    now = _et(2026, 8, 18, 12, 0, 0)
    mj.append_exit(trade_id="E1", exit_date="2026-08-18", exit_time_et="10:00:00",
                    exit_premium=2.5, exit_reason="tp1", path=journal_path)  # +150.00

    params_path = tmp_path / "params.json"
    params_path.write_text(json.dumps({"shadow_only": True, "live": False,
                                       "account": {"account_number": "PA38EG1JTFBT"}}),
                            encoding="utf-8")

    # A deliberately huge, unrelated equity figure (as if the crypto twin had a great day) --
    # realized_pnl_today_dollars must be completely unaffected by it.
    status = ms.build_status(
        now=now, params_path=params_path,
        ledger_path=tmp_path / "shadow-ledger.jsonl",
        cascade_path=tmp_path / "participation-cascade.jsonl",
        journal_path=journal_path,
        equity_fn=lambda: 987654.32,
    )
    assert status["realized_pnl_today_dollars"] == pytest.approx(150.00, abs=1e-9)
    assert status["capital"]["account_equity_dollars"] == pytest.approx(987654.32)
    # The two numbers must never collide or be mistakable for one another.
    assert status["realized_pnl_today_dollars"] != status["capital"]["account_equity_dollars"]


def test_status_dict_carries_explicit_equity_disclosure(tmp_path):
    params_path = tmp_path / "params.json"
    params_path.write_text(json.dumps({"shadow_only": True, "live": False,
                                       "account": {"account_number": "PA38EG1JTFBT"}}),
                            encoding="utf-8")
    status = ms.build_status(
        now=_et(2026, 8, 19, 11, 0, 0), params_path=params_path,
        ledger_path=tmp_path / "shadow-ledger.jsonl",
        cascade_path=tmp_path / "participation-cascade.jsonl",
        journal_path=tmp_path / "trades-multi.csv",
        equity_fn=lambda: 9628.45,
    )
    disclosure = status["capital"]["_disclosure"]
    assert "NOT" in disclosure and "P&L" in disclosure
    assert "crypto twin" in disclosure or "shared" in disclosure.lower()


def test_formatted_table_never_labels_equity_as_pnl(tmp_path):
    params_path = tmp_path / "params.json"
    params_path.write_text(json.dumps({"shadow_only": True, "live": False,
                                       "account": {"account_number": "PA38EG1JTFBT"}}),
                            encoding="utf-8")
    status = ms.build_status(
        now=_et(2026, 8, 19, 11, 0, 0), params_path=params_path,
        ledger_path=tmp_path / "shadow-ledger.jsonl",
        cascade_path=tmp_path / "participation-cascade.jsonl",
        journal_path=tmp_path / "trades-multi.csv",
        equity_fn=lambda: 9628.45,
    )
    table = ms.format_table(status)
    assert "REALIZED P&L TODAY" in table
    assert "account equity" in table.lower()
    assert "NOT this lane's P&L" in table
    # There must be no line that presents the raw equity figure under the P&L heading.
    pnl_line = next(l for l in table.splitlines() if l.startswith("REALIZED P&L TODAY"))
    assert "9,628.45" not in pnl_line and "9628.45" not in pnl_line


# =========================================================================================
# 8. top_blocking_gate -- "why didn't it trade" in one read
# =========================================================================================

def test_top_blocking_gate_finds_largest_drop():
    cascade = {
        "funnel_universe": 40, "funnel_liquidity": 40, "funnel_attention": 15,
        "funnel_setup": 5, "evaluated": 5, "bars_ok": 5, "signal_scored": 5,
        "action_directional": 1, "risk_admitted": 1, "expiry_available": 1,
        "liquidity_ok": 1, "strike_selected": 1, "sized_ok": 1, "would_place": 1,
    }
    tbg = ms.top_blocking_gate(cascade)
    # biggest drop is liquidity(40) -> attention(15): 25 (bigger than attention->setup's 10)
    assert tbg["gate"] == "funnel_liquidity -> funnel_attention"
    assert tbg["dropped"] == 25


def test_top_blocking_gate_none_when_no_cascade():
    assert ms.top_blocking_gate(None) is None
    assert ms.top_blocking_gate({}) is None


def test_top_blocking_gate_handles_older_partial_cascade_rows():
    # An early cascade row (before the funnel stages were wired) only has evaluated/bars_ok.
    cascade = {"evaluated": 20, "bars_ok": 20, "signal_scored": 20}
    tbg = ms.top_blocking_gate(cascade)
    assert tbg["dropped"] == 0
    assert tbg["gate"] is None


# =========================================================================================
# 9. watchlist_top -- ranked by relative volume, only the LAST tick's rows
# =========================================================================================

def test_watchlist_top_uses_only_latest_tick_ranked_by_rvol(tmp_path):
    path = tmp_path / "shadow-ledger.jsonl"
    rows = [
        {"ts_et": "2026-08-20T00:30:00-04:00", "symbol": "OLD", "rel_volume": 99.0},
        {"ts_et": "2026-08-20T00:51:51-04:00", "symbol": "GLD", "rel_volume": 2.53},
        {"ts_et": "2026-08-20T00:51:51-04:00", "symbol": "AVGO", "rel_volume": 2.74},
        {"ts_et": "2026-08-20T00:51:51-04:00", "symbol": "INTC", "rel_volume": 1.31},
    ]
    _write_jsonl(path, rows)
    top = ms.read_watchlist_top(path, top_n=2)
    assert [t["symbol"] for t in top] == ["AVGO", "GLD"]  # ranked desc by rel_volume
    assert all(t["symbol"] != "OLD" for t in top)  # older tick excluded entirely


# =========================================================================================
# WP-6 (2026-08-20) -- the status surface must answer three questions it previously could not:
#   * is this lane still a live programme, or was it STOPPED?
#   * which business is it in (intraday vs the dormant multi-day model)?
#   * which named FILTER refused -- not merely which cascade stage lost symbols?
# The first matters most: after WP-4's null verdict, a status surface that still reads like a
# healthy research lane is how a dead programme gets silently re-litigated a month later.
# =========================================================================================

def _params_with(tmp_path: Path, **extra) -> Path:
    base = {
        "shadow_only": True, "live": False,
        "account": {"account_number": "PA38EG1JTFBT"},
        "mode": {"name": "intraday_v1", "same_day_exit": True, "time_stop_et": "15:50"},
    }
    base.update(extra)
    p = tmp_path / "params.json"
    p.write_text(json.dumps(base), encoding="utf-8")
    return p


def _status_at(tmp_path: Path, params_path: Path) -> dict:
    return ms.build_status(
        now=_et(2026, 8, 20, 16, 5),
        params_path=params_path,
        ledger_path=tmp_path / "ledger.jsonl",
        cascade_path=tmp_path / "cascade.jsonl",
        journal_path=tmp_path / "trades.csv",
    )


def test_stopped_lane_says_so_at_the_top_of_the_report(tmp_path):
    params = _params_with(tmp_path, lane_status={
        "state": "STOPPED_ON_NULL", "stopped_at_et": "2026-08-20",
        "verdict": "analysis/deep-research/MULTI-LANE-STAGE-A-VERDICT-2026-08-20.md"})
    status = _status_at(tmp_path, params)
    assert status["lane_status"]["state"] == "STOPPED_ON_NULL"
    table = ms.format_table(status)
    head = table.splitlines()[:8]
    assert any("LANE STOPPED" in ln for ln in head), "stopped state must be in the first lines"
    assert "MULTI-LANE-STAGE-A-VERDICT-2026-08-20.md" in table, "must point at the verdict"


def test_an_active_lane_shows_no_stopped_banner(tmp_path):
    """RED-proofs the banner: it must key off real state, not print unconditionally."""
    table = ms.format_table(_status_at(tmp_path, _params_with(tmp_path)))
    assert "LANE STOPPED" not in table


def test_mode_identity_is_reported_not_just_shadow_flags(tmp_path):
    """WP-0: 'shadow_only=True' does not say WHICH strategy is in shadow."""
    status = _status_at(tmp_path, _params_with(tmp_path))
    assert status["mode"]["name"] == "intraday_v1"
    assert status["mode"]["time_stop_et"] == "15:50"
    assert "intraday_v1" in ms.format_table(status)


def test_blocker_histogram_reports_named_filters_per_side(tmp_path):
    hist = tmp_path / "hist"
    hist.mkdir()
    (hist / "blocker-histogram-2026-08-20.json").write_text(json.dumps({
        "date": "2026-08-20", "rows_scored": 5, "would_place": 0,
        "top_blocker_bear": {"blocker": "F5:ribbon_stack", "pct_of_scored": 100.0},
        "top_blocker_bull": {"blocker": "F10:level_tied_trigger", "pct_of_scored": 100.0},
    }), encoding="utf-8")
    out = ms.read_blocker_histogram(_et(2026, 8, 20, 16, 5), hist_dir=hist)
    assert out["is_today"] is True
    assert out["top_blocker_bear"]["blocker"] == "F5:ribbon_stack"
    assert out["top_blocker_bull"]["blocker"] == "F10:level_tied_trigger"


def test_stale_histogram_is_flagged_not_passed_off_as_today(tmp_path):
    """A yesterday-shaped file read today must SAY it is yesterday's (C7: silent success is
    failure). Falling back is fine; falling back quietly is not."""
    hist = tmp_path / "hist"
    hist.mkdir()
    (hist / "blocker-histogram-2026-08-14.json").write_text(
        json.dumps({"date": "2026-08-14", "rows_scored": 3, "would_place": 0}), encoding="utf-8")
    out = ms.read_blocker_histogram(_et(2026, 8, 20, 16, 5), hist_dir=hist)
    assert out["is_today"] is False and out["date"] == "2026-08-14"


def test_missing_or_corrupt_histogram_is_none_never_an_exception(tmp_path):
    assert ms.read_blocker_histogram(_et(2026, 8, 20), hist_dir=tmp_path / "nope") is None
    hist = tmp_path / "hist"
    hist.mkdir()
    (hist / "blocker-histogram-2026-08-20.json").write_text("{not json", encoding="utf-8")
    assert ms.read_blocker_histogram(_et(2026, 8, 20), hist_dir=hist) is None

"""Regression test for daily_loss_guard -- the mechanical Rule-5 daily-loss trip.

Runnable with plain `python setup/scripts/test_daily_loss_guard.py` (no pytest dep)
or under pytest. Verifies the trip math AND every fail-safe path, because this guard
runs on the LIVE trading engine and a false trip would halt a good day.

The suite redirects dlg.LOG_DIR to a tempdir and asserts the REAL automation/state/
dir is untouched afterward -- test runs used to append fake TRIPPED/REARMED rows into
the real daily-loss-guard-{date}.jsonl audit trail (caught 2026-07-09; one such file
had even been committed to the repo).
"""
from __future__ import annotations

import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import daily_loss_guard as dlg  # noqa: E402

ET = timezone(timedelta(hours=-4))
TODAY = datetime.now(timezone.utc).astimezone(ET).strftime("%Y-%m-%d")
YESTERDAY = (datetime.now(timezone.utc).astimezone(ET) - timedelta(days=1)).strftime("%Y-%m-%d")


def _breaker(tmp: Path, *, sod, date, tripped=False, limit=0.30):
    b = {
        "tripped": tripped, "tripped_at": None, "tripped_reason": None,
        "starting_equity_today": sod, "current_equity": sod,
        "daily_loss_limit_pct": limit, "max_drawdown_today_pct": 0,
        "max_drawdown_today_dollars": 0, "last_reset": f"{date}T08:30:00-04:00",
    }
    tmp.write_text(json.dumps(b), encoding="utf-8")
    return tmp


def _patch(tmp: Path, equity):
    dlg.ACCOUNTS["safe"]["breaker"] = tmp
    if isinstance(equity, Exception):
        def boom(_a):
            raise equity
        dlg._fetch_equity = boom
    else:
        dlg._fetch_equity = lambda _a: float(equity)


def run_case(name, *, sod, date, equity, dry_run, tripped_in, limit, expect_action, expect_tripped):
    with tempfile.TemporaryDirectory() as d:
        tmp = _breaker(Path(d) / "cb.json", sod=sod, date=date, tripped=tripped_in, limit=limit)
        _patch(tmp, equity)
        res = dlg.run("safe", dry_run)
        after = json.loads(tmp.read_text())
        assert res["action"] == expect_action, f"{name}: action {res['action']} != {expect_action} ({res})"
        assert bool(after["tripped"]) == expect_tripped, f"{name}: tripped {after['tripped']} != {expect_tripped}"
        print(f"  PASS {name}: action={res['action']} tripped={after['tripped']}")


# --------------------------------------------------------------------------------------- #
# rearm() -- the 2026-07-09 root-cause fix (deterministic, LLM/CCR-independent premarket
# re-arm). Bite-tested against BOTH breaker schemas (safe: last_reset ISO datetime,
# starting_equity_today/current_equity; bold: session_id bare date,
# equity_start_of_day/equity_current) -- the exact C9 symmetry-trap the module's own
# docstring warns about. Every write goes to a tempfile, NEVER the real breaker paths.
# --------------------------------------------------------------------------------------- #

def _breaker_bold(tmp: Path, *, sod, date, tripped=False, limit=0.50):
    b = {
        "_doc": "test fixture (bold schema)",
        "daily_loss_kill_switch_pct": limit,
        "tripped": tripped,
        "session_id": date,
        "equity_start_of_day": sod,
        "equity_current": sod,
        "loss_pct": 0.0,
        "trip_reason": None,
        "tripped_at_et": None,
    }
    tmp.write_text(json.dumps(b), encoding="utf-8")
    return tmp


def _patch_account(account: str, tmp: Path, equity):
    dlg.ACCOUNTS[account]["breaker"] = tmp
    if isinstance(equity, Exception):
        def boom(_a):
            raise equity
        dlg._fetch_equity = boom
    else:
        dlg._fetch_equity = lambda _a: float(equity)


def run_rearm_case(name, *, account, sod, date, equity, dry_run, tripped_in=False,
                    expect_action, expect_date_is_today=None, expect_tripped_after=None,
                    expect_sod_after=None):
    cfg = dlg.ACCOUNTS[account]
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / "cb.json"
        if account == "safe":
            _breaker(tmp, sod=sod, date=date, tripped=tripped_in)
        else:
            _breaker_bold(tmp, sod=sod, date=date, tripped=tripped_in)
        _patch_account(account, tmp, equity)
        res = dlg.rearm(account, dry_run)
        after = json.loads(tmp.read_text())
        assert res["action"] == expect_action, f"{name}: action {res['action']} != {expect_action} ({res})"
        after_date = str(after.get(cfg["date_field"], ""))[:10]
        if expect_date_is_today is True:
            assert after_date == TODAY, f"{name}: date {after_date} != TODAY {TODAY}"
        elif expect_date_is_today is False:
            assert after_date != TODAY, f"{name}: date {after_date} unexpectedly became TODAY"
        if expect_tripped_after is not None:
            assert bool(after["tripped"]) == expect_tripped_after, \
                f"{name}: tripped {after['tripped']} != {expect_tripped_after}"
        if expect_sod_after is not None:
            assert after[cfg["sod_field"]] == expect_sod_after, \
                f"{name}: sod {after[cfg['sod_field']]} != {expect_sod_after}"
        print(f"  PASS {name}: action={res['action']} date={after_date} tripped={after['tripped']}")
        return res, after


def _log_snapshot(d: Path) -> dict:
    """name -> size of every guard audit log under d (the pollution tripwire)."""
    return {p.name: p.stat().st_size for p in d.glob("daily-loss-guard-*.jsonl")}


def _suite() -> None:
    print("daily_loss_guard regression:")
    # 1. within limit -> no trip
    run_case("within_limit", sod=2000, date=TODAY, equity=1900, dry_run=False,
             tripped_in=False, limit=0.30, expect_action="ok_within_limit", expect_tripped=False)
    # 2. breach, live -> TRIPPED + file flipped (2000 -> 1300 = -35% >= -30%)
    run_case("breach_live_trips", sod=2000, date=TODAY, equity=1300, dry_run=False,
             tripped_in=False, limit=0.30, expect_action="TRIPPED", expect_tripped=True)
    # 3. breach, dry-run -> WOULD_TRIP, file NOT flipped
    run_case("breach_dryrun_no_write", sod=2000, date=TODAY, equity=1300, dry_run=True,
             tripped_in=False, limit=0.30, expect_action="WOULD_TRIP", expect_tripped=False)
    # 4. stale SoD (yesterday) + huge loss -> NEVER trips (fail-safe)
    run_case("stale_sod_never_trips", sod=2000, date=YESTERDAY, equity=100, dry_run=False,
             tripped_in=False, limit=0.30, expect_action="skip_stale_sod", expect_tripped=False)
    # 5. equity fetch fails -> skip, no trip (fail-safe)
    run_case("fetch_fail_never_trips", sod=2000, date=TODAY, equity=ConnectionError("down"),
             dry_run=False, tripped_in=False, limit=0.30, expect_action="skip", expect_tripped=False)
    # 6. already tripped -> idempotent, stays tripped, never un-trips
    run_case("already_tripped_idempotent", sod=2000, date=TODAY, equity=1990, dry_run=False,
             tripped_in=True, limit=0.30, expect_action="already_tripped", expect_tripped=True)
    # 7. exactly at limit (-30.0%) -> trips (>= boundary)
    run_case("exact_limit_trips", sod=2000, date=TODAY, equity=1400, dry_run=False,
             tripped_in=False, limit=0.30, expect_action="TRIPPED", expect_tripped=True)

    print("daily_loss_guard.rearm() regression (2026-07-09 root-cause fix):")
    # 8. stale date (safe schema) + live fetch ok -> REARMED, date=today, tripped reset,
    #    SoD equity replaced with the fresh live read (the 2026-07-09 incident's exact fix).
    run_rearm_case("safe_stale_rearms", account="safe", sod=1512.83, date=YESTERDAY,
                    equity=1550.00, dry_run=False, tripped_in=False,
                    expect_action="REARMED", expect_date_is_today=True,
                    expect_tripped_after=False, expect_sod_after=1550.00)
    # 9. stale date + PREVIOUSLY TRIPPED (a trip carried over from an old stale day) ->
    #    rearm CLEARS the trip -- a new session must never inherit yesterday's halt.
    run_rearm_case("safe_stale_tripped_clears_on_rearm", account="safe", sod=1000.0,
                    date=YESTERDAY, equity=1600.00, dry_run=False, tripped_in=True,
                    expect_action="REARMED", expect_date_is_today=True,
                    expect_tripped_after=False)
    # 10. already armed TODAY -> no-op; _fetch_equity must NEVER be called (boom if it is) --
    #     proves rearm() is idempotent and never double-writes/re-fetches on a healthy day.
    run_rearm_case("safe_already_armed_noop", account="safe", sod=1512.83, date=TODAY,
                    equity=RuntimeError("_fetch_equity must not be called when already armed"),
                    dry_run=False, expect_action="already_armed_today",
                    expect_date_is_today=True, expect_sod_after=1512.83)
    # 11. stale date + equity fetch FAILS -> skip, fail-safe: never guesses/writes a value,
    #     date stays stale (so the next fire retries rather than silently "succeeding").
    run_rearm_case("safe_fetch_fail_never_writes", account="safe", sod=1512.83,
                    date=YESTERDAY, equity=ConnectionError("down"), dry_run=False,
                    expect_action="skip", expect_date_is_today=False,
                    expect_sod_after=1512.83)
    # 12. dry-run + stale -> WOULD_REARM, file untouched on disk.
    run_rearm_case("safe_dry_run_no_write", account="safe", sod=1512.83, date=YESTERDAY,
                    equity=1550.00, dry_run=True, expect_action="WOULD_REARM",
                    expect_date_is_today=False, expect_sod_after=1512.83)
    # 13. BOLD schema cross-check (the C9 symmetry trap: session_id bare date,
    #     equity_start_of_day/equity_current, NOT last_reset/starting_equity_today) ->
    #     proves rearm() reads/writes the correct field names per-account, not safe's.
    run_rearm_case("bold_stale_rearms_correct_schema", account="bold", sod=1963.04,
                    date=YESTERDAY, equity=1900.00, dry_run=False, tripped_in=False,
                    expect_action="REARMED", expect_date_is_today=True,
                    expect_tripped_after=False, expect_sod_after=1900.00)


def main() -> int:
    # WHY the wrapper: the audit-log path used to be inlined in run()/rearm(), so every
    # live-write case in _suite() appended fake TRIPPED/REARMED rows into the REAL
    # automation/state/daily-loss-guard-{date}.jsonl. dlg.LOG_DIR is redirected for the
    # whole suite; the two guards below prove the redirect actually captured the writes
    # AND the real state dir is unchanged after the run (catches any inlined-path revert).
    real_log_dir = dlg.LOG_DIR
    real_before = _log_snapshot(real_log_dir)
    with tempfile.TemporaryDirectory() as log_tmp:
        dlg.LOG_DIR = Path(log_tmp)
        try:
            _suite()
            actions = [json.loads(ln)["action"]
                       for p in Path(log_tmp).glob("daily-loss-guard-*.jsonl")
                       for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
            assert "TRIPPED" in actions and "REARMED" in actions, (
                f"audit-log redirect captured no TRIPPED/REARMED rows (actions={actions})"
                " -- run()/rearm() no longer write via dlg.LOG_DIR?")
            print(f"  PASS audit_log_redirect_captures_writes: actions={sorted(set(actions))}")
        finally:
            dlg.LOG_DIR = real_log_dir
    real_after = _log_snapshot(real_log_dir)
    assert real_after == real_before, (
        f"TEST POLLUTION: real state dir changed during the suite: "
        f"{real_before} -> {real_after}")
    print(f"  PASS no_pollution_of_real_state_dir: {real_log_dir}")
    print("ALL PASS")
    return 0


def test_daily_loss_guard():  # pytest entry point
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())

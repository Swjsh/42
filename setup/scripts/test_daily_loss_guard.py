"""Regression test for daily_loss_guard -- the mechanical Rule-5 daily-loss trip.

Runnable with plain `python setup/scripts/test_daily_loss_guard.py` (no pytest dep)
or under pytest. Verifies the trip math AND every fail-safe path, because this guard
runs on the LIVE trading engine and a false trip would halt a good day.
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


def main() -> int:
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
    print("ALL PASS")
    return 0


def test_daily_loss_guard():  # pytest entry point
    assert main() == 0


if __name__ == "__main__":
    sys.exit(main())

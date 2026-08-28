"""Guard: reconciliation_criterion clamps window_start to the TRUE account-creation
date, not just Alpaca's base_value_asof.

Scar (2026-08-28, TASK B3): go_live_gate.json reported safe-3 diff_vs_fee_adjusted_ledger
= -$74.27 and risky-3 = +$231.39 (both FAIL). Root-caused live: base_value_asof from
/v2/account/portfolio/history returned 2026-07-30 for every one of the 5 arms, but
/v2/account.created_at for all 5 is actually 2026-08-03T13:00-13:03Z (each paired with
a same-day $5,000 JNLC deposit) -- a 4-calendar-day undershoot (07-30/07-31 are trading
days). trades-enriched.jsonl carried real engine-attributed round trips dated 07-30/07-31
for safe-3 (+$75) and risky-3 (-$165-$110+$126-$80=-$229) that fired against the OLD,
now-defunct pre-rebuild account under the SAME arm_id -- the window clamped only to
base_value_asof wrongly included them against a broker history that is genuinely $0 for
those dates on the CURRENT account. safe-2/bold-2/risky-1 carry the identical stale
clamp but have zero engine trips in the phantom window, which is why the bug was silent
for them (not because their window was correct).

This test reproduces the exact numbers with synthetic fixtures (no network) and pins
that clamping to whichever of base_value_asof / account-creation-date is LATER excludes
the phantom-window rows and reconciles correctly.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = str(REPO / "setup" / "scripts")
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

import go_live_gate as glg  # noqa: E402


def _row(arm, date, pnl, qty=3.0, exit_px=1.0):
    return {
        "arm": arm, "date": date, "pnl_dollars": pnl, "attribution": "engine",
        "qty": qty, "exit_px_avg": exit_px,
    }


def _synthetic_hist(dates_pl: dict) -> dict:
    """Build a fake _fetch_portfolio_history()-shaped payload from {date: pl}."""
    import datetime as _dt
    timestamps, pl = [], []
    for d, p in sorted(dates_pl.items()):
        ts = int(_dt.datetime.strptime(d, "%Y-%m-%d")
                 .replace(tzinfo=glg.ET_TZ).timestamp())
        timestamps.append(ts)
        pl.append(p)
    return {"ok": True, "timestamp": timestamps, "profit_loss": pl,
            "base_value_asof": "2026-07-30"}


def test_phantom_pre_rebuild_rows_are_excluded_by_the_creation_date_clamp(tmp_path):
    """The exact safe-3 shape: a real engine trip on 07-31 (before the true rebuild)
    must NOT count toward ledger_pnl once the account-creation-date clamp is honored,
    even though base_value_asof alone (07-30) would have let it through."""
    rows = [
        _row("safe-3", "2026-07-31", 75.0),   # phantom -- pre-rebuild account
        _row("safe-3", "2026-08-03", 145.0),  # real -- on the rebuilt account
        _row("safe-3", "2026-08-04", 155.0),  # real
    ]
    dates_pl = {
        "2026-07-30": 0.0, "2026-07-31": 0.0, "2026-08-01": 0.0, "2026-08-02": 0.0,
        "2026-08-03": 145.0, "2026-08-04": 155.0,
    }
    hist = _synthetic_hist(dates_pl)

    secrets_file = tmp_path / "secrets.json"
    secrets_file.write_text('{"accounts": {"safe-3": {"key": "k", "secret": "s"}}}',
                             encoding="utf-8")

    with patch.object(glg, "_fetch_portfolio_history", return_value=hist), \
         patch.object(glg, "_fetch_account_created_date", return_value="2026-08-03"), \
         patch.object(glg, "ACTIVE_ARMS", ["safe-3"]), \
         patch.object(glg, "SECRETS_PATH", secrets_file):
        result = glg.reconciliation_criterion(rows)

    arm = result["per_arm"]["safe-3"]
    assert arm["window"][0] == "2026-08-03", (
        "window_start must clamp to the account-creation date (later than "
        "base_value_asof), not just base_value_asof alone"
    )
    assert arm["ledger_pnl_sum_engine_attributed"] == 300.0, (
        "the 07-31 phantom-window row (+$75) must be excluded from ledger_pnl"
    )
    assert arm["broker_pnl_sum"] == 300.0
    assert arm["reconciled"] is True
    assert result["pass"] is True


def test_without_the_creation_date_the_phantom_row_would_have_broken_reconciliation(tmp_path):
    """Negative control: proves the fixture actually exercises the bug -- clamping to
    base_value_asof ALONE (account-creation lookup unavailable / fails-open to None)
    reproduces the original FAIL shape."""
    rows = [
        _row("safe-3", "2026-07-31", 75.0),
        _row("safe-3", "2026-08-03", 145.0),
        _row("safe-3", "2026-08-04", 155.0),
    ]
    dates_pl = {
        "2026-07-30": 0.0, "2026-07-31": 0.0, "2026-08-01": 0.0, "2026-08-02": 0.0,
        "2026-08-03": 145.0, "2026-08-04": 155.0,
    }
    hist = _synthetic_hist(dates_pl)

    secrets_file = tmp_path / "secrets.json"
    secrets_file.write_text('{"accounts": {"safe-3": {"key": "k", "secret": "s"}}}',
                             encoding="utf-8")

    with patch.object(glg, "_fetch_portfolio_history", return_value=hist), \
         patch.object(glg, "_fetch_account_created_date", return_value=None), \
         patch.object(glg, "ACTIVE_ARMS", ["safe-3"]), \
         patch.object(glg, "SECRETS_PATH", secrets_file):
        result = glg.reconciliation_criterion(rows)

    arm = result["per_arm"]["safe-3"]
    assert arm["window"][0] == "2026-07-30"
    assert arm["ledger_pnl_sum_engine_attributed"] == 375.0, (
        "without the creation-date clamp, the phantom 07-31 row leaks into ledger_pnl "
        "-- this is the exact pre-fix bug shape"
    )
    assert arm["reconciled"] is False, (
        "375 (ledger, incl. phantom) vs 300 (broker) should NOT reconcile within tolerance"
    )

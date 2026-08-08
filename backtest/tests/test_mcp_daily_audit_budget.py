"""Guard: mcp-daily-audit's per-fire budget must stay large enough to complete a fire.

Context (2026-08-08 conductor fire, `BUDGET-ROSTER-AUDIT-MAXBUDGETUSD` queue item --
the roster-wide sweep for the "mis-sized at birth" budget class first found in
scout-premarket, see `test_scout_premarket_budget.py`).

`setup/scripts/run-mcp-daily-audit.ps1` invoked `claude` with `-MaxBudgetUsd 0.30` from the
script's creation through at least 2026-08-07. Full classification of every dated log in
`automation/state/logs/mcp-daily-audit-*.log` (42 fires, 2026-06-21..2026-08-07):
23 ok (exit=0), 10 `Error: Exceeded USD budget (0.3)` (exit=1), 6 timeout (exit=124),
3 other exit=1 -- a combined **45% failure rate**. The docstring's own "~$0.10/fire" estimate
never matched reality: round-tripping Alpaca (Safe + Bold) + TradingView MCP tools regularly
costs more than 3x that estimate. Not a regression -- mis-sized at birth, same class as
scout-premarket (0.50, ~7-8wk silent failure) and eod-flatten (1, budget-exceeded 8/10 recent
dates). This task is read-only and low-criticality (redundant with `Gamma_TvWatchdog` +
`self_check.py`'s live MCP checks), so the failures were not a trading-safety incident -- but
a health-check that silently fails ~half the time is the exact C7 "silent success is failure"
shape and defeats its own purpose (catching "a hung-but-alive MCP bridge that
Gamma_TvWatchdog cannot see").

Fix: budget 0.30 -> 0.60 (2x, matching the eod-flatten fix's 2x bump), timeout 240s -> 300s
(the 6 exit=124 timeouts all hit the old 240s ceiling). This test pins both values so a future
edit can't silently drift back toward the broken 0.30/240 pair.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "setup" / "scripts" / "run-mcp-daily-audit.ps1"

# The values that produced a 45% (19/42) fire failure rate for ~7 weeks. Never again.
KNOWN_BROKEN_BUDGET = 0.30
KNOWN_BROKEN_TIMEOUT = 240
MIN_SAFE_BUDGET = 0.60
MIN_SAFE_TIMEOUT = 300


def _read_script_text() -> str:
    assert SCRIPT.exists(), f"run-mcp-daily-audit.ps1 missing at {SCRIPT}"
    return SCRIPT.read_text(encoding="utf-8")


def _read_max_budget_usd() -> float:
    text = _read_script_text()
    m = re.search(r"-MaxBudgetUsd\s+([0-9.]+)\s*`?", text)
    assert m, "could not find -MaxBudgetUsd in run-mcp-daily-audit.ps1 -- script shape changed"
    return float(m.group(1))


def _read_timeout_sec() -> int:
    text = _read_script_text()
    m = re.search(r"-TimeoutSec\s+([0-9]+)", text)
    assert m, "could not find -TimeoutSec in run-mcp-daily-audit.ps1 -- script shape changed"
    return int(m.group(1))


def test_mcp_daily_audit_budget_is_not_the_known_broken_value():
    budget = _read_max_budget_usd()
    assert budget != KNOWN_BROKEN_BUDGET, (
        f"run-mcp-daily-audit.ps1 MaxBudgetUsd reverted to the known-broken "
        f"{KNOWN_BROKEN_BUDGET} -- this value produced 'Error: Exceeded USD budget' -> exit=1 "
        "on 10/42 dated fires (24%) across 2026-06-21..2026-08-07. See module docstring."
    )


def test_mcp_daily_audit_budget_at_least_60_cents():
    budget = _read_max_budget_usd()
    assert budget >= MIN_SAFE_BUDGET, (
        f"run-mcp-daily-audit.ps1 MaxBudgetUsd={budget} is below the {MIN_SAFE_BUDGET} floor "
        "restored 2026-08-08 -- round-tripping Alpaca (Safe+Bold) + TradingView MCP tools "
        "regularly exceeds the old 0.30 cap by 2x+."
    )


def test_mcp_daily_audit_timeout_is_not_the_known_broken_value():
    timeout = _read_timeout_sec()
    assert timeout != KNOWN_BROKEN_TIMEOUT, (
        f"run-mcp-daily-audit.ps1 TimeoutSec reverted to the known-broken "
        f"{KNOWN_BROKEN_TIMEOUT} -- this value produced exit=124 (timeout) on 6/42 dated fires "
        "(14%) across the same window. See module docstring."
    )


def test_mcp_daily_audit_timeout_at_least_300_sec():
    timeout = _read_timeout_sec()
    assert timeout >= MIN_SAFE_TIMEOUT, (
        f"run-mcp-daily-audit.ps1 TimeoutSec={timeout} is below the {MIN_SAFE_TIMEOUT} floor "
        "restored 2026-08-08 -- 6/42 dated fires hit the old 240s ceiling before completing."
    )


if __name__ == "__main__":
    sys.exit(0)

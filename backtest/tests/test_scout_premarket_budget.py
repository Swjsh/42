"""Guard: scout-premarket's per-fire budget must stay large enough to complete a fire.

Context (2026-08-06 conductor fire, RUN-PS1-HIDDEN-MASKED-EXIT self_check finding):
`setup/scripts/run-scout-premarket.ps1` invoked `claude` with `-MaxBudgetUsd 0.50` from the
script's creation (2026-06-15) through at least 2026-08-06 -- and the underlying `claude` CLI
printed `Error: Exceeded USD budget (0.5)` and exited 1 on EVERY dated log checked across that
window (2026-07-20, 07-21, 07-22, 07-23, 07-27, 07-28, 07-31, 08-03, 08-04, 08-05, 08-06).
Task Scheduler's `LastTaskResult` never saw it (the vbs launcher hop is fire-and-forget), so this
was invisible until self_check.py's masked-exit detector started reading
`run-ps1-hidden-*.log` directly. Net effect: `automation/scout/state/scout_output.json` (which
Premarket at 08:30 ET reads for macro/news bias context) went stale for at least 2 consecutive
sessions (08-05, 08-06) before this was caught -- last successful-ish write was 2026-08-04's
`status: "partial"` fire, itself already budget-starved.

Root cause named in one sentence: $0.50 was always too tight for a WebSearch-driven macro/news
scan (the comparable futures-premarket task budgets $2.00, premarket itself $3.00) -- it wasn't
a regression, it was mis-sized at birth and nobody had visibility to notice for ~7-8 weeks.

Fix: raised to $1.00 (still the 2nd-cheapest premarket-class task on the roster). This test pins
that value so a future edit can't silently drift back toward the broken $0.50 ceiling.
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "setup" / "scripts" / "run-scout-premarket.ps1"

# The value that produced a *daily* "Exceeded USD budget" exit=1 for ~7-8 weeks. Never again.
KNOWN_BROKEN_BUDGET = 0.50
MIN_SAFE_BUDGET = 1.00


def _read_max_budget_usd() -> float:
    assert SCRIPT.exists(), f"run-scout-premarket.ps1 missing at {SCRIPT}"
    text = SCRIPT.read_text(encoding="utf-8")
    m = re.search(r"-MaxBudgetUsd\s+([0-9.]+)\s*`?", text)
    assert m, "could not find -MaxBudgetUsd in run-scout-premarket.ps1 -- script shape changed"
    return float(m.group(1))


def test_scout_premarket_budget_is_not_the_known_broken_value():
    budget = _read_max_budget_usd()
    assert budget != KNOWN_BROKEN_BUDGET, (
        f"run-scout-premarket.ps1 MaxBudgetUsd reverted to the known-broken {KNOWN_BROKEN_BUDGET} "
        "-- this value caused 'Error: Exceeded USD budget' -> exit=1 EVERY DAY for ~7-8 weeks "
        "(2026-06-15..2026-08-06), invisible to Task Scheduler. See module docstring."
    )


def test_scout_premarket_budget_at_least_1_dollar():
    budget = _read_max_budget_usd()
    assert budget >= MIN_SAFE_BUDGET, (
        f"run-scout-premarket.ps1 MaxBudgetUsd={budget} is below the {MIN_SAFE_BUDGET} floor "
        "restored 2026-08-06 -- a WebSearch-driven macro/news scan needs headroom comparable to "
        "futures-premarket ($2.00) / premarket ($3.00), not heartbeat-tier ($0.25-1.00)."
    )

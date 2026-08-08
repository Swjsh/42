"""Guard: EOD-flatten's per-fire budget (both accounts) must stay large enough to complete a fire.

Context (2026-08-08 conductor fire, EOD-FLATTEN-LLM-PROMPT-EXIT1, filed 2026-08-06 by the
VBS-WRAPPER-EXIT-CODE-BLIND-SPOT 2nd-half finding): `setup/scripts/run-eod-flatten.ps1` and
`setup/scripts/run-eod-flatten-aggressive.ps1` invoked `claude` with `-MaxBudgetUsd 1` -- and
the underlying `claude` CLI printed `Error: Exceeded USD budget (1)` and exited 1 on a
recurring basis, live-verified via `automation/state/logs/eod-flatten-{aggressive-}<date>.log`:

  - eod-flatten-aggressive: exit=1 on 08-03, 08-04, 08-05, 08-06, 08-07 (5/5 dates checked)
  - eod-flatten (safe):     exit=1 on 08-05, 08-06, 08-07; exit=0 on 08-03, 08-04

NOT a realized safety incident (the deterministic `Gamma_EodFlattenCore` backstops both
accounts and fires ~3 min earlier; `engine-health.json` confirmed flat both accounts every
date checked) -- but it means the documented LLM-prompt flatten path (with its reconciliation
/ dashboard-update steps `Gamma_EodFlattenCore` does not do) was silently degraded to
backup-only on a majority of days.

Root cause named in one sentence: `eod-flatten.md` / `aggressive/eod-flatten.md` run a
tool-call-heavy retry-until-zero close loop (up to 3 attempts x ~4 MCP calls each) plus a
fill-reconciliation pass against `journal/trades.csv`, and `-MaxBudgetUsd 1` -- unchanged
since the scripts' creation -- was never enough headroom for that shape of prompt, same class
of bug as the Scout premarket budget mis-sizing (`test_scout_premarket_budget.py`,
2026-08-06): a budget cap that is enforced correctly but was wrong from birth.

Fix: raised both to $2.00 (matches futures-eod / futures-premarket, still cheap -- worst case
~$4/day for both accounts). This test pins that value so a future edit can't silently drift
either script back toward the broken $1 ceiling.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAFE_SCRIPT = ROOT / "setup" / "scripts" / "run-eod-flatten.ps1"
AGGRESSIVE_SCRIPT = ROOT / "setup" / "scripts" / "run-eod-flatten-aggressive.ps1"

# The value that produced a repeated "Exceeded USD budget" exit=1 across multiple trading
# days for both accounts. Never again.
KNOWN_BROKEN_BUDGET = 1.0
MIN_SAFE_BUDGET = 2.0


def _read_max_budget_usd(script: Path) -> float:
    assert script.exists(), f"{script.name} missing at {script}"
    text = script.read_text(encoding="utf-8")
    m = re.search(r"-MaxBudgetUsd\s+([0-9.]+)\s*`?", text)
    assert m, f"could not find -MaxBudgetUsd in {script.name} -- script shape changed"
    return float(m.group(1))


def test_eod_flatten_safe_budget_is_not_the_known_broken_value():
    budget = _read_max_budget_usd(SAFE_SCRIPT)
    assert budget != KNOWN_BROKEN_BUDGET, (
        f"run-eod-flatten.ps1 MaxBudgetUsd reverted to the known-broken {KNOWN_BROKEN_BUDGET} "
        "-- this value caused 'Error: Exceeded USD budget' -> exit=1 on 3 of 5 recent trading "
        "days (2026-08-05/06/07). See module docstring."
    )


def test_eod_flatten_safe_budget_at_least_2_dollars():
    budget = _read_max_budget_usd(SAFE_SCRIPT)
    assert budget >= MIN_SAFE_BUDGET, (
        f"run-eod-flatten.ps1 MaxBudgetUsd={budget} is below the {MIN_SAFE_BUDGET} floor "
        "restored 2026-08-08 -- the tool-call-heavy retry-until-zero close loop + fill "
        "reconciliation needs headroom comparable to futures-eod ($2.00)."
    )


def test_eod_flatten_aggressive_budget_is_not_the_known_broken_value():
    budget = _read_max_budget_usd(AGGRESSIVE_SCRIPT)
    assert budget != KNOWN_BROKEN_BUDGET, (
        f"run-eod-flatten-aggressive.ps1 MaxBudgetUsd reverted to the known-broken "
        f"{KNOWN_BROKEN_BUDGET} -- this value caused 'Error: Exceeded USD budget' -> exit=1 "
        "on 5 of 5 recent trading days (2026-08-03..08-07, every date checked). See module "
        "docstring."
    )


def test_eod_flatten_aggressive_budget_at_least_2_dollars():
    budget = _read_max_budget_usd(AGGRESSIVE_SCRIPT)
    assert budget >= MIN_SAFE_BUDGET, (
        f"run-eod-flatten-aggressive.ps1 MaxBudgetUsd={budget} is below the {MIN_SAFE_BUDGET} "
        "floor restored 2026-08-08 -- same shape of prompt as the safe-side script, needs the "
        "same headroom."
    )

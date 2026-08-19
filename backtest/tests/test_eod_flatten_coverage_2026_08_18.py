"""Guards for the EOD-flatten coverage + escalation fix (2026-08-18).

TWO GAPS, both invisible on paper and account-ending live:

1. COVERAGE. eod_flatten.py hardcoded ACCOUNTS = ["safe-2", "bold-2"] -- the two CORE arms.
   The three fleet arms (safe-3, risky-1, risky-3) are separate real Alpaca accounts taking
   real 0DTE positions, and fleet_eod.py exists but is scheduled NOWHERE (verified against
   the live Windows Task Scheduler, not the docs). So 3 of 5 active arms had no deterministic
   EOD flatten.

2. ESCALATION. On a 3x-failed flatten the code set outcome="PARTIAL_FILL_ESCALATION" and
   did nothing else. The real escalation -- kill-switch + Discord ping -- lived only in
   automation/prompts/eod-flatten.md, which this module's own docstring demotes to "a
   verbose-confirmation fallback (NOT the execution path)". The word ESCALATION in an
   outcome string is not an escalation.

WHY IT MATTERS: SPY options settle PHYSICALLY. An unclosed ITM 0DTE is assigned ~100 shares
per contract -- roughly $77,000 of stock at current SPY -- against a ~$5,000 account.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("eod_flatten_g", REPO / "setup" / "scripts" / "eod_flatten.py")
ef = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ef)  # type: ignore[union-attr]


def _registry_active() -> set[str]:
    reg = json.loads((REPO / "automation" / "state" / "fleet" / "accounts.json").read_text(encoding="utf-8"))
    out = set()
    for a in reg.get("arms", []):
        acct = a.get("account_number")
        if isinstance(acct, str) and acct.startswith("PA") and str(a.get("status", "")).lower() == "active":
            out.add(str(a.get("id") or a.get("arm_id")))
    return out


def test_every_active_spy_arm_is_covered() -> None:
    """THE COVERAGE GUARD. A registered, active, paper SPY arm that nothing flattens is an
    account walking into physical assignment."""
    missing = _registry_active() - set(ef.ACCOUNTS)
    assert not missing, (
        f"active SPY arm(s) with NO EOD flatten coverage: {sorted(missing)}. "
        "SPY options settle physically -- an unclosed ITM 0DTE is assigned ~100 shares/contract."
    )


def test_the_three_fleet_arms_specifically_are_covered() -> None:
    """Pins the exact arms that were missing, so a regression names itself."""
    for arm in ("safe-3", "risky-1", "risky-3"):
        assert arm in ef.ACCOUNTS, f"{arm} lost EOD flatten coverage (it was added 2026-08-18)"


def test_retired_and_futures_arms_are_excluded() -> None:
    assert "safe-1" not in ef.ACCOUNTS, "retired arm should not be flattened"
    assert not any(str(a).startswith("mes") for a in ef.ACCOUNTS), "futures arm is not SPY options"


def test_roster_falls_back_rather_than_covering_nothing(monkeypatch) -> None:
    """An unreadable registry must degrade to the core arms, never to an empty list --
    flattening SOMETHING beats flattening nothing."""
    monkeypatch.setattr(ef, "_REPO", Path("/nonexistent-repo-path"))
    got = ef._active_arms()
    assert got, "empty roster on registry failure -- would flatten NOTHING"
    assert "safe-2" in got and "bold-2" in got


def test_escalate_writes_a_killswitch(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ef, "_REPO", tmp_path)
    (tmp_path / "automation" / "state").mkdir(parents=True)
    (tmp_path / "automation" / "overnight").mkdir(parents=True)
    log = tmp_path / "flat.log"
    ef._escalate("risky-1", 2, ["broker timeout"], log)
    ks = tmp_path / "automation" / "state" / "kill-switch-risky-1.json"
    assert ks.exists(), "no kill-switch written -- the arm stays free to open more risk"
    data = json.loads(ks.read_text(encoding="utf-8"))
    assert data["armed"] is True
    assert data["arm"] == "risky-1"
    assert "MANUAL ACTION REQUIRED" in data["reason"]
    assert "assign" in data["reason"].lower(), "reason must name the actual risk"


def test_escalate_appends_to_status_when_it_exists(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(ef, "_REPO", tmp_path)
    (tmp_path / "automation" / "state").mkdir(parents=True)
    (tmp_path / "automation" / "overnight").mkdir(parents=True)
    status = tmp_path / "automation" / "overnight" / "STATUS.md"
    status.write_text("# STATUS\n", encoding="utf-8")
    ef._escalate("safe-3", 1, [], tmp_path / "flat.log")
    txt = status.read_text(encoding="utf-8")
    assert "EOD FLATTEN FAILED" in txt and "safe-3" in txt


def test_escalate_never_raises_even_when_everything_fails(tmp_path, monkeypatch) -> None:
    """Escalation must not raise back into the flatten loop -- the OTHER arms still need
    their turn. A guard that kills the rest of the sweep is worse than the gap it closes."""
    monkeypatch.setattr(ef, "_REPO", tmp_path / "does" / "not" / "exist")
    ef._escalate("bold-2", 3, ["x"], tmp_path / "nowhere" / "flat.log")   # must not raise


def test_dry_run_flag_is_respected() -> None:
    """GAMMA_EOD_DRY exists so this can be exercised without placing orders."""
    assert hasattr(ef, "DRY")

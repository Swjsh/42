"""Doctrine-code parity: CLAUDE.md's Rule 5/6/7 numbers + Tech-stack status lines vs the
live code/params that enforce them.

WHY THIS EXISTS (GOAL-DOCTRINE-CODE-PARITY-SWEEP-2026-09-05): the sibling exit-shape parity
test (test_exit_shape_parity_2026_09_05.py) pins CLAUDE.md's strategy-paragraph exit-shape
numbers against automation/state/fleet/strategies.py. This goal found the SAME class of drift
one level up -- in the 10 rules' numbers and the Tech-stack table's status flags -- e.g.
CLAUDE.md claimed a "hard time-stop 15:50 ET" while automation/state/params.json's
time_stop_et (the value setup/scripts/heartbeat_core.py._manage_exits actually forwards to
exit_actuator.manage_tick) measures 15:40 for both accounts. This test parses the relevant
CLAUDE.md sentences and asserts them against params.json / aggressive/params.json / the
GAMMA_FREE_MODEL_VETO env default, so a future re-drift fails here instead of surviving
another audit cycle. Full claim-by-claim inventory + verdicts: analysis/doctrine-parity/
claims-2026-09-05.json and markdown/doctrine/DOCTRINE-CODE-PARITY-2026-09-05.md.

RED-PROOF: this test is designed to FAIL against the PRE-EDIT CLAUDE.md text (which claimed
"hard time-stop 15:50 ET" -- params.time_stop_et is 15:40 on both accounts) and to PASS
against the corrected working-tree text. See test_red_proof_time_stop_against_pre_edit_text
below, which asserts the failure directly without touching the filesystem.

Run:
    cd backtest && .venv/Scripts/python.exe -m pytest tests/test_doctrine_code_parity_2026_09_05.py -q
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
PARAMS_SAFE = REPO_ROOT / "automation" / "state" / "params.json"
PARAMS_BOLD = REPO_ROOT / "automation" / "state" / "aggressive" / "params.json"


def _read_claude_md() -> str:
    return CLAUDE_MD.read_text(encoding="utf-8")


def _load_params(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _find_rule(md_text: str, n: int) -> str:
    """Extract the text of rule N (1-10) from the numbered rules list."""
    m = re.search(rf"(?m)^{n}\. \*\*.*?(?=\n\d+\. \*\*|\n\n|\Z)", md_text, re.S)
    assert m, f"could not find Rule {n} in CLAUDE.md"
    return m.group(0)


def _find_management_line(md_text: str) -> str:
    m = re.search(r"- \*\*Management:\*\*.*", md_text)
    assert m, "could not find the '- **Management:**' workflow line in CLAUDE.md"
    return m.group(0)


# --------------------------------------------------------------------------- #
# Live params values (both accounts) -- the CODE truth these claims are      #
# checked against.                                                           #
# --------------------------------------------------------------------------- #
SAFE_PARAMS = _load_params(PARAMS_SAFE)
BOLD_PARAMS = _load_params(PARAMS_BOLD)


def test_rule5_kill_switch_pct_matches_params():
    rule5 = _find_rule(_read_claude_md(), 5)
    m_safe = re.search(r"Gamma-Safe:\s*[−-](\d+)%", rule5)
    m_bold = re.search(r"Gamma-Bold:\s*[−-](\d+)%", rule5)
    assert m_safe and m_bold, f"could not parse Rule 5 pcts from: {rule5!r}"
    claimed_safe = float(m_safe.group(1)) / 100.0
    claimed_bold = float(m_bold.group(1)) / 100.0
    assert claimed_safe == pytest.approx(SAFE_PARAMS["daily_loss_kill_switch_pct"])
    assert claimed_bold == pytest.approx(BOLD_PARAMS["daily_loss_kill_switch_pct"])


def test_rule6_per_trade_cap_pct_matches_params():
    rule6 = _find_rule(_read_claude_md(), 6)
    m_safe = re.search(r"Gamma-Safe:\s*(\d+)% of account equity", rule6)
    m_bold = re.search(r"Gamma-Bold:\s*(\d+)%", rule6)
    assert m_safe and m_bold, f"could not parse Rule 6 pcts from: {rule6!r}"
    claimed_safe = float(m_safe.group(1)) / 100.0
    claimed_bold = float(m_bold.group(1)) / 100.0
    assert claimed_safe == pytest.approx(SAFE_PARAMS["per_trade_risk_cap_pct"])
    assert claimed_bold == pytest.approx(BOLD_PARAMS["per_trade_risk_cap_pct"])


def test_rule6_min_contracts_matches_params_per_account():
    """Corrected claim (2026-09-05, C02): Rule 6 must disclose Safe 3 / Bold 5, not a single
    universal '3' -- Bold's live params.min_contracts floor is measured at 5, not 3."""
    rule6 = _find_rule(_read_claude_md(), 6)
    m = re.search(r"Min contracts:\s*Safe\s*(\d+)\s*/\s*Bold\s*(\d+)", rule6)
    assert m, (
        "Rule 6 must state the per-account min-contracts split explicitly "
        f"('Min contracts: Safe N / Bold M') -- got: {rule6!r}"
    )
    claimed_safe = int(m.group(1))
    claimed_bold = int(m.group(2))
    assert claimed_safe == SAFE_PARAMS["min_contracts"]
    assert claimed_bold == BOLD_PARAMS["min_contracts"]


def test_management_time_stop_matches_params():
    """Corrected claim (2026-09-05, C09): the hard time-stop is 15:40 ET per
    params.time_stop_et (both accounts), not the stale 15:50 the pre-edit doc claimed."""
    mgmt = _find_management_line(_read_claude_md())
    m = re.search(r"hard time-stop\s+(\d{1,2}:\d{2})\s*ET", mgmt)
    assert m, f"could not find a 'hard time-stop HH:MM ET' claim in: {mgmt!r}"
    claimed = m.group(1)
    assert claimed == SAFE_PARAMS["time_stop_et"]
    assert claimed == BOLD_PARAMS["time_stop_et"]
    # And it must NOT be the stale pre-correction value.
    assert claimed != "15:50", "Rule 6/Management still claims the stale 15:50 time-stop"


def test_entry_gate_09_35_matches_params():
    md_text = _read_claude_md()
    assert "09:35 ET entry gate" in md_text
    assert SAFE_PARAMS["entry_no_trade_before_et"] == "09:35"
    assert BOLD_PARAMS["entry_no_trade_before_et"] == "09:35"


def test_free_model_veto_disabled_default():
    """CLAUDE.md's Tech-stack claim: 'Free-model veto DISABLED since 2026-08-12
    (GAMMA_FREE_MODEL_VETO defaults 0)'."""
    md_text = _read_claude_md()
    assert "Free-model veto DISABLED since 2026-08-12" in md_text
    hb = REPO_ROOT / "setup" / "scripts" / "heartbeat_core.py"
    src = hb.read_text(encoding="utf-8")
    m = re.search(
        r'FREE_MODEL_VETO_ENABLED\s*=\s*os\.environ\.get\("GAMMA_FREE_MODEL_VETO",\s*"(\d)"\)',
        src,
    )
    assert m, "could not find the GAMMA_FREE_MODEL_VETO default-read line in heartbeat_core.py"
    assert m.group(1) == "0", "the coded default no longer matches CLAUDE.md's DISABLED claim"


def test_catastrophe_cap_pct_matches_registry():
    """CLAUDE.md: 'premium stops are now -50% catastrophe caps both sides'. Live value is
    the registry's frozen catastrophe_stop_pct on ribbon_ride's ExitShape (per
    EXIT-SHAPE-TRUTH.md's vary-and-assert -- params.json's own premium_stop_pct is a
    different, currently-unreached fallback key, deliberately NOT what this asserts)."""
    strategies_dir = REPO_ROOT / "automation" / "state" / "fleet"
    sys.path.insert(0, str(strategies_dir))
    import strategies  # noqa: E402  (path insert must precede this import)

    ribbon = strategies.by_name("ribbon_ride")
    assert ribbon is not None
    md_text = _read_claude_md()
    m = re.search(r"[−-](\d+)%\s*catastrophe caps both sides", md_text)
    assert m, "could not find the '-N% catastrophe caps both sides' claim in CLAUDE.md"
    claimed = float(m.group(1)) / 100.0
    assert claimed == pytest.approx(-ribbon.exit.catastrophe_stop_pct)


def test_red_proof_time_stop_against_pre_edit_text():
    """RE-PROOF: the parser above must FAIL when fed the pre-edit sentence verbatim, proving
    this guard actually catches the drift it was built for."""
    pre_edit_mgmt_line = (
        "- **Management:** mechanical stop (never widen); TP1 chart-level OR +30% "
        "fallback, breakeven on runner; hard time-stop 15:50 ET; adding = fresh trigger, "
        "new leg."
    )
    m = re.search(r"hard time-stop\s+(\d{1,2}:\d{2})\s*ET", pre_edit_mgmt_line)
    assert m
    pre_edit_claim = m.group(1)
    assert pre_edit_claim == "15:50"  # the pre-edit claim, parsed correctly
    # And it does NOT match the live code value -- this is the actual red-proof.
    with pytest.raises(AssertionError):
        assert pre_edit_claim == SAFE_PARAMS["time_stop_et"]


def test_red_proof_min_contracts_against_pre_edit_text():
    """RE-PROOF for C02: the pre-edit Rule 6 ('Min 3 contracts', no per-account split)
    cannot even be parsed by the corrected-format regex -- proving the guard would have
    caught the omission, not just a wrong number."""
    pre_edit_rule6 = (
        "6. **Per-trade risk cap — per account:** Gamma-Safe: 30% of account equity. "
        "Gamma-Bold: 50%. Min 3 contracts (2 TP + 1 runner). Scale per "
        "[`markdown/0dte/risk-rules.md`](markdown/0dte/risk-rules.md)."
    )
    m = re.search(r"Min contracts:\s*Safe\s*(\d+)\s*/\s*Bold\s*(\d+)", pre_edit_rule6)
    assert m is None, "pre-edit text should NOT match the corrected per-account pattern"

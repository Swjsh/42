"""Guards for the 2026-08-09 cash-account parity flip (bold-2 margin_pdt -> cash_settlement).

J's directive, verbatim: "we'll not be doing margin. I always use cash accounts. I deposit a
thousand, two thousand, or whatever, and that's how much we have for the day to trade until it
settles."

Both core accounts must therefore model CASH SETTLEMENT, not margin PDT. bold-2 was the last
holdout, left on margin_pdt by a 2026-07-20 flip whose stated justification cited account
PA33W2KUAT40 -- deleted in the 2026-08-03 rebuild. It cost bold-2 four dark sessions.

What would silently rot without these pins:

1. **Parity drift.** One core account on each mode is exactly the state that produced the bug.
   If a future edit moves either account back, the fleet is asymmetric again for no reason
   anybody remembers.
2. **Provenance rot.** The old doc justified a live gate with a dead account number. A doc that
   names an account must name a LIVE one -- that is the L287 class and it recurred here.
3. **The plumbing assumption.** cash_settlement fails CLOSED without settled_cash_available /
   same_day_entries_used, which only exist because settlement_ledger resolves a per-account
   ledger. If ledger_path stops handling "bold", bold-2 silently stops trading entirely --
   a much worse failure than the one we just fixed.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SAFE_PARAMS = REPO / "automation" / "state" / "params.json"
BOLD_PARAMS = REPO / "automation" / "state" / "aggressive" / "params.json"

# Accounts deleted in the 2026-08-03 rebuild. A live doc must never justify itself with these.
DEAD_ACCOUNTS = ("PA33W2KUAT40", "PA3DHPT7KIQE", "PA3S2PYAS2WQ")


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8"))


def test_both_core_accounts_run_cash_settlement():
    """The parity pin. J trades cash accounts; both cores must model that."""
    assert _load(SAFE_PARAMS)["pdt_gate_mode"] == "cash_settlement"
    assert _load(BOLD_PARAMS)["pdt_gate_mode"] == "cash_settlement", (
        "bold-2 drifted back to margin_pdt -- that models a constraint J's real accounts will "
        "never have, and it cost 4 dark sessions the last time"
    )


def test_bold_doc_does_not_cite_a_deleted_account():
    """L287: an imperative fix expires when its declarative source still names dead state."""
    doc = _load(BOLD_PARAMS).get("_pdt_gate_mode_doc", "")
    assert doc, "bold-2 pdt_gate_mode has no provenance doc"
    for dead in DEAD_ACCOUNTS:
        assert dead not in doc or "DELETED" in doc.upper(), (
            f"doc cites {dead} without marking it deleted -- stale-provenance rot"
        )
    assert "PA3WEBXJU67N" in doc, "doc must name the LIVE bold-2 account"


def test_both_docs_carry_a_one_line_revert():
    for p in (SAFE_PARAMS, BOLD_PARAMS):
        doc = _load(p).get("_pdt_gate_mode_doc", "")
        assert "margin_pdt" in doc and "REVERT" in doc.upper(), (
            f"{p.name}: pdt_gate_mode doc must state its one-line revert"
        )


def test_same_day_roundtrip_cap_still_present_on_both():
    """cash_settlement is the primary gate; this cap is the belt-and-suspenders on top."""
    for p in (SAFE_PARAMS, BOLD_PARAMS):
        assert int(_load(p)["max_same_day_roundtrips"]) >= 1


def test_settlement_ledger_resolves_a_distinct_bold_path():
    """cash_settlement fails CLOSED without a ledger -- so 'bold' must resolve its own file."""
    import importlib.util
    import sys

    mod_path = REPO / "setup" / "scripts" / "settlement_ledger.py"
    spec = importlib.util.spec_from_file_location("settlement_ledger", mod_path)
    sl = importlib.util.module_from_spec(spec)
    sys.modules["settlement_ledger"] = sl
    spec.loader.exec_module(sl)  # type: ignore[union-attr]

    state = REPO / "automation" / "state"
    safe_path = sl.ledger_path(state, "safe")
    bold_path = sl.ledger_path(state, "bold")
    assert safe_path != bold_path, (
        "safe and bold share a settlement ledger -- one account's entries would debit the "
        "other's settled pool"
    )


def test_risk_gate_still_fails_closed_without_settlement_inputs():
    """The safety property that makes cash_settlement safe to arm at all."""
    src = (REPO / "backtest" / "lib" / "risk_gate.py").read_text(encoding="utf-8", errors="replace")
    assert "same_day_entries_used is required under pdt_gate_mode=cash_settlement" in src
    assert "settled_cash_available is required under pdt_gate_mode=cash_settlement" in src


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

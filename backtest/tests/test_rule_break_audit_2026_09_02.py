"""Guards for setup/scripts/rule_break_audit.py.

The first real run audited 495 entries and found ZERO breaks. That is either a genuinely
clean history or a detector that cannot detect -- and those look identical from the output,
which is the exact C14 dead-knob trap. So every check here is proven to FIRE on a synthetic
violation and to stay quiet on its compliant twin. A detector that has never fired is not
evidence of compliance.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
MODULE = REPO / "setup" / "scripts" / "rule_break_audit.py"

_spec = importlib.util.spec_from_file_location("rule_break_audit_g", MODULE)
assert _spec and _spec.loader
rba = importlib.util.module_from_spec(_spec)
sys.modules["rule_break_audit_g"] = rba
_spec.loader.exec_module(rba)


def entry(**kw):
    """A COMPLIANT entry. Each test breaks exactly one field, so a firing check is
    attributable to that field and nothing else."""
    base = {
        "source": "fleet", "arm_id": "safe-3", "date": "2026-09-01",
        "ts_et": "2026-09-01T14:49:03", "setup": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "side": "P", "qty": 3.0, "premium": 0.78, "equity": 5900.0,
        "stop": 0.4, "stop_mode": "structure", "trigger_level": 761.28,
        "trigger_bar_et": "2026-09-01T14:40:00", "flat": True, "killed": False,
    }
    base.update(kw)
    return base


# ---------------------------------------------------------------------------------------
# Every check fires on its own violation.
# ---------------------------------------------------------------------------------------

def test_rule_1_fires_on_an_unnamed_setup():
    found, checked = rba.check_named_setup(entry(setup="SOME_UNTESTED_IDEA"))
    assert checked and len(found) == 1
    assert found[0]["rule_id"] == "RULE_1_NAMED_SETUP"


def test_rule_1_quiet_on_every_playbook_setup():
    for s in rba.PLAYBOOK_SETUPS:
        found, checked = rba.check_named_setup(entry(setup=s))
        assert checked and found == []


def test_rule_2_fires_on_an_anticipation_entry():
    """Entered 14:42, before its own 14:40 bar closed at 14:45."""
    found, checked = rba.check_wait_for_trigger(entry(ts_et="2026-09-01T14:42:00"))
    assert checked and len(found) == 1
    assert found[0]["rule_id"] == "RULE_2_WAIT_FOR_TRIGGER"


def test_rule_2_quiet_when_the_bar_had_closed():
    found, checked = rba.check_wait_for_trigger(entry(ts_et="2026-09-01T14:45:01"))
    assert checked and found == []


def test_rule_2_is_not_checked_without_a_trigger_bar():
    """Fleet rows do not record trigger_bar_et -- that must read NOT CHECKED, not PASS."""
    found, checked = rba.check_wait_for_trigger(entry(trigger_bar_et=None))
    assert found == [] and checked is False


def test_rule_3_fires_on_a_missing_stop():
    found, checked = rba.check_defined_stop(entry(stop=None))
    assert checked and any(f["rule_id"] == "RULE_3_DEFINED_STOP" for f in found)


def test_rule_3_fires_on_structure_mode_with_no_trigger_level():
    """exit_manager.py:268 resolves this to PREMIUM mode -- the chart stop the row claims
    is not the stop that was armed."""
    found, checked = rba.check_defined_stop(entry(trigger_level=None))
    assert checked and len(found) == 1
    assert "PREMIUM" in found[0]["what_happened"]


def test_rule_3_quiet_on_premium_mode_without_a_level():
    """Premium mode legitimately has no chart level -- must not be flagged."""
    found, checked = rba.check_defined_stop(entry(stop_mode="premium", trigger_level=None))
    assert checked and found == []


def test_rule_4_fires_when_not_flat():
    found, checked = rba.check_no_adding(entry(flat=False))
    assert checked and len(found) == 1
    assert found[0]["rule_id"] == "RULE_4_NO_ADDING"


def test_rule_5_fires_on_an_entry_after_the_kill_switch():
    found, checked = rba.check_kill_switch(entry(killed=True))
    assert checked and len(found) == 1
    assert found[0]["severity"] == "high"


def test_rule_6_fires_over_the_cap():
    """3 x $2.50 x 100 = $750 on $2,000 equity = 37.5%, over a 30% cap."""
    found, checked = rba.check_risk_cap(entry(qty=3, premium=2.50, equity=2000.0), 0.30)
    assert checked and len(found) == 1
    assert "37.5%" in found[0]["what_happened"]


def test_rule_6_quiet_just_under_the_cap():
    found, checked = rba.check_risk_cap(entry(qty=3, premium=1.99, equity=2000.0), 0.30)
    assert checked and found == []


def test_rule_6_is_not_checked_without_a_resolvable_cap():
    """A guessed cap would manufacture breaks or silently clear real ones."""
    found, checked = rba.check_risk_cap(entry(), None)
    assert found == [] and checked is False


# ---------------------------------------------------------------------------------------
# "not checked" must never read as "passed".
# ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("fn,kw", [
    ("check_named_setup", {"setup": None}),
    ("check_no_adding", {"flat": None}),
    ("check_kill_switch", {"killed": None}),
])
def test_missing_inputs_report_not_checked(fn, kw):
    found, checked = getattr(rba, fn)(entry(**kw))
    assert found == [] and checked is False, "absent input must be NOT_CHECKED, never a pass"


def test_coverage_counts_separate_checked_from_not_checked():
    entries = [entry(), entry(flat=None), entry(flat=None)]
    _breaks, cov = rba.audit_entries(entries, {"per_trade_risk_cap_pct": 0.3}, None)
    assert cov["RULE_4_NO_ADDING"]["checked"] == 1
    assert cov["RULE_4_NO_ADDING"]["not_checked"] == 2


def test_report_carries_the_honesty_note_and_the_unchecked_rules():
    out = rba.run(repo=REPO, write=False)
    rep = out["report"]
    assert "NOT a statement that the window was clean" in rep["honesty_note"]
    for rule in ("RULE_7_PDT", "RULE_8_JOURNAL", "RULE_10_GAMMA_VETO"):
        assert rule in rep["rules_NOT_checked"]


def test_rules_checked_and_not_checked_are_disjoint_and_cover_all_ten():
    assert not (set(rba.RULES_CHECKED) & set(rba.RULES_NOT_CHECKED))
    numbers = {int(r.split("_")[1]) for r in
               list(rba.RULES_CHECKED) + list(rba.RULES_NOT_CHECKED)}
    assert numbers == set(range(1, 11)), f"every rule must be accounted for, got {sorted(numbers)}"


# ---------------------------------------------------------------------------------------
# ledger safety -- this writes to the file go_live_gate's criterion 4 counts.
# ---------------------------------------------------------------------------------------

def test_append_is_idempotent(tmp_path):
    """A daily re-run must not manufacture duplicate 'breaks' and fail the behavioural
    criterion on its own output."""
    led = tmp_path / "rule-breaks.jsonl"
    rows = [rba._break(entry(flat=False), "RULE_4_NO_ADDING", "high", "x")]
    assert rba._append_breaks(led, rows) == 1
    assert rba._append_breaks(led, rows) == 0
    assert len(led.read_text(encoding="utf-8").strip().splitlines()) == 1


def test_break_rows_carry_the_field_the_gate_filters_on():
    """go_live_gate._load_rule_breaks windows on `date` -- a row without it is invisible."""
    row = rba._break(entry(), "RULE_1_NAMED_SETUP", "high", "x")
    assert row["date"] == "2026-09-01"
    assert row["rule_id"] and row["severity"] and row["what_happened"]


def test_coverage_is_not_written_into_the_rule_breaks_ledger(tmp_path, monkeypatch):
    """THE trap: the gate counts EVERY parseable row with an in-window date as a break, so a
    heartbeat/coverage row written here would spuriously FAIL criterion 4. Coverage lives in
    its own file, and a clean run must leave the ledger untouched."""
    src = (REPO / "setup" / "scripts" / "rule_break_audit.py").read_text(encoding="utf-8")
    assert "_write_json(state / \"rule-break-audit.json\", report)" in src
    assert "_append_breaks" in src
    # and the only thing appended to the ledger is `breaks`
    assert "_append_breaks(state / \"rule-breaks.jsonl\", breaks)" in src


def test_clean_run_writes_no_ledger_rows(tmp_path):
    out = rba.run(repo=REPO, write=False)
    if out["report"]["breaks_found"] == 0:
        assert out["breaks"] == []


def test_run_never_raises_on_a_repo_with_no_state(tmp_path):
    """Fail-open: a missing state tree yields an empty audit, not a crash -- and the report
    must say the ledgers were unreadable rather than implying a clean zero."""
    out = rba.run(repo=tmp_path, write=False)
    assert out["report"]["entries_audited"] == 0
    assert out["report"]["core_ledger_readable"] is False


# ---------------------------------------------------------------------------------------
# binding evidence -- "0 breaks" from a rule tested at 99% of its limit and "0 breaks" from
# a rule that never had an opportunity are the same number and different claims.
# ---------------------------------------------------------------------------------------

def test_risk_cap_zero_is_informative_only_when_the_cap_was_approached():
    params = {"per_trade_risk_cap_pct": 0.30}
    near = [entry(qty=3, premium=1.95, equity=2000.0)]       # 29.2% of 30% cap -> 0.975
    far = [entry(qty=1, premium=0.10, equity=5000.0)]        # 0.2% of cap
    assert rba.binding_evidence(near, params, None)["RULE_6_RISK_CAP"]["informative"] is True
    ev = rba.binding_evidence(far, params, None)["RULE_6_RISK_CAP"]
    assert ev["informative"] is False
    assert "never approached" in ev["note"]


def test_kill_switch_zero_is_uninformative_when_it_never_tripped():
    ev = rba.binding_evidence([entry(killed=False)], {"per_trade_risk_cap_pct": 0.3}, None)
    assert ev["RULE_5_KILL_SWITCH"]["informative"] is False
    assert "says nothing about enforcement" in ev["RULE_5_KILL_SWITCH"]["note"]


def test_kill_switch_zero_becomes_informative_once_it_trips():
    ev = rba.binding_evidence([entry(killed=True)], {"per_trade_risk_cap_pct": 0.3}, None)
    assert ev["RULE_5_KILL_SWITCH"]["informative"] is True


def test_binding_evidence_is_in_the_report_and_the_honesty_note_points_at_it():
    rep = rba.run(repo=REPO, write=False)["report"]
    assert "binding_evidence" in rep
    assert "binding_evidence" in rep["honesty_note"]


def test_real_history_actually_approached_the_risk_cap():
    """Anchors the first real reading: 495 entries, max 0.99 of cap, 8 above 0.8. If a later
    change makes this zero uninformative, that is a finding, not a silent improvement."""
    rep = rba.run(repo=REPO, write=False)["report"]
    ev = rep["binding_evidence"]["RULE_6_RISK_CAP"]
    if ev["n"] > 100:
        assert ev["max_fraction_of_cap"] is not None
        assert ev["informative"] is True, (
            "the per-trade risk cap has stopped being approached in real trading -- "
            "'0 breaks' on RULE_6 no longer means the cap is binding"
        )

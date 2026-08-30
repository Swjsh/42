"""Tests for gamma_cockpit_cards.py's three 2026-08-29 additions:

  1. Goal-to-card linkage -- the active goal's next open '- [ ]' item (per
     setup/hooks/doctrine.py's goal_next_open_item/goal_expired, REUSED not
     re-parsed) is ALWAYS card rank 1 when it fires.
  2. Context-alarm cards -- a session over CONTEXT_ALARM_PCT of its
     autoCompactWindow (gamma_cockpit_army.build_army()) gets a card, UNLESS
     context_source == "unknown".
  3. autofire_safe / autofire_reason -- the field the auto-fire runner
     depends on. Default FALSE; TRUE only for a clean read-and-report card;
     unconditionally FALSE on a live-arming/secret/irreversible mention or a
     frozen-trading-path mention during the 2026-08-31 -> 2026-09-29 freeze.

Run: pytest -v setup/scripts/test_cockpit_cards_autofire.py
"""
from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

# Direct import (script is in setup/scripts, not a package) -- same pattern as
# every other setup/scripts/test_*.py file in this repo. Executing the module
# also runs its own sys.path.insert()s, so its sibling imports (et_clock,
# task_scorer, gamma_cockpit_army, doctrine) resolve exactly as they do live.
_spec = importlib.util.spec_from_file_location(
    "gamma_cockpit_cards",
    Path(__file__).parent / "gamma_cockpit_cards.py",
)
cards = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(cards)  # type: ignore[union-attr]


def _stub_other_sources(monkeypatch, tmp_path):
    """Point every card source EXCEPT active-goal at files that don't exist,
    so a test can add exactly the one other source it wants to compare the
    goal card's rank against."""
    monkeypatch.setattr(cards, "STATUS_MD", tmp_path / "STATUS.md")
    monkeypatch.setattr(cards, "UNATTENDED_HEALTH_JSON", tmp_path / "unattended-health.json")
    monkeypatch.setattr(cards, "QUIET_MODE_JSON", tmp_path / "quiet-mode.json")
    monkeypatch.setattr(cards, "QUIET_MODE_RESTORE_JSON", tmp_path / "quiet-mode-restore.json")
    # task_scorer.load_queue_text(path: Path = QUEUE) binds its default at
    # DEFINITION time, so patching the QUEUE module attribute alone would not
    # affect a no-arg call already made from gamma_cockpit_cards -- patch the
    # function itself instead.
    monkeypatch.setattr(cards.task_scorer, "load_queue_text", lambda: None)
    monkeypatch.setattr(cards.gamma_cockpit_army, "build_army", lambda: {"sessions": []})


def _write_goal(tmp_path, monkeypatch, *, expires_at_et="2099-01-01", queue_body=None):
    """Wires active-goal.json + its goal .md under tmp_path, with cards.REPO
    monkeypatched so `REPO / goal["file"]` resolves inside tmp_path."""
    monkeypatch.setattr(cards, "REPO", tmp_path)
    goal_md = tmp_path / "goal.md"
    goal_md.write_text(queue_body or (
        "# Goal Test\n\n"
        "## QUEUE\n"
        "- [x] Step 1 -- already done.\n"
        "- [ ] Step 2 -- do the actual next thing.\n"
        "- [B-J] Step 3 -- blocked on J, must never surface.\n"
    ), encoding="utf-8")
    active_goal_json = tmp_path / "active-goal.json"
    active_goal_json.write_text(json.dumps({
        "id": "GOAL-TEST-1",
        "active": True,
        "expires_at_et": expires_at_et,
        "file": "goal.md",
    }), encoding="utf-8")
    monkeypatch.setattr(cards, "ACTIVE_GOAL_JSON", active_goal_json)


# ---------------------------------------------------------------------------
# goal-to-card linkage
# ---------------------------------------------------------------------------

def test_goal_item_becomes_rank_1_outranking_a_critical_engine_health_card(tmp_path, monkeypatch):
    _stub_other_sources(monkeypatch, tmp_path)
    _write_goal(tmp_path, monkeypatch)

    # A critical RED engine-health check -- normally source 1, i.e. would sort
    # ahead of everything if the goal card were appended in source order
    # instead of always prepended.
    engine_health = tmp_path / "engine-health.json"
    engine_health.write_text(json.dumps({
        "checked_at_et": "2026-08-29 09:00:00",
        "checks": [{"name": "clock", "critical": True, "status": "RED", "detail": "stale"}],
    }), encoding="utf-8")
    monkeypatch.setattr(cards, "ENGINE_HEALTH_JSON", engine_health)

    payload = cards.build_cards(write=False)
    assert len(payload["cards"]) == 2
    assert payload["cards"][0]["id"] == "card-goal-goal-test-1"
    assert payload["cards"][0]["rank"] == 1
    assert "Step 2" in payload["cards"][0]["title"]
    assert payload["cards"][1]["id"].startswith("card-engine-")
    assert payload["cards"][1]["rank"] == 2


def test_no_goal_present_does_not_crash_and_emits_no_goal_card(tmp_path, monkeypatch):
    _stub_other_sources(monkeypatch, tmp_path)
    monkeypatch.setattr(cards, "ENGINE_HEALTH_JSON", tmp_path / "engine-health.json")
    monkeypatch.setattr(cards, "ACTIVE_GOAL_JSON", tmp_path / "active-goal.json")  # does not exist

    payload = cards.build_cards(write=False)
    assert payload["cards"] == []
    assert not any(c["id"].startswith("card-goal-") for c in payload["cards"])


def test_expired_goal_emits_no_card(tmp_path, monkeypatch):
    _stub_other_sources(monkeypatch, tmp_path)
    monkeypatch.setattr(cards, "ENGINE_HEALTH_JSON", tmp_path / "engine-health.json")
    _write_goal(tmp_path, monkeypatch, expires_at_et="2020-01-01")  # long past

    payload = cards.build_cards(write=False)
    assert payload["cards"] == []
    assert cards._cards_active_goal() == []


# ---------------------------------------------------------------------------
# context-alarm cards
# ---------------------------------------------------------------------------

def _session(session_id="sess-1", pct=90.0, source="transcript_tail+global_autoCompactWindow"):
    return {
        "session_id": session_id,
        "title": "Engine performance today",
        "name": "gamma",
        "context_pct": pct,
        "context_tokens": int(pct / 100.0 * 800_000),
        "context_limit": 800_000,
        "context_source": source,
    }


def test_context_alarm_fires_at_90_percent():
    army_payload = {"sessions": [_session(pct=90.0)]}
    out = cards._cards_context_alarm(army_payload)
    assert len(out) == 1
    assert out[0]["id"] == "card-context-sess-1"
    assert "90%" in out[0]["title"]
    assert "context_pct 90.0%" in " ".join(out[0]["why"])


def test_no_alarm_when_context_source_is_unknown():
    army_payload = {"sessions": [_session(pct=90.0, source=cards.gamma_cockpit_army.CONTEXT_UNKNOWN)]}
    out = cards._cards_context_alarm(army_payload)
    assert out == []


def test_no_alarm_below_the_85_percent_threshold():
    army_payload = {"sessions": [_session(pct=84.9)]}
    out = cards._cards_context_alarm(army_payload)
    assert out == []


# ---------------------------------------------------------------------------
# autofire_safe / autofire_reason classification
# ---------------------------------------------------------------------------

def test_default_false_for_an_ordinary_fix_it_card():
    safe, reason = cards._autofire_classification(
        title="clock is RED",
        why=["engine-health.json checked_at_et 2026-08-29 09:00"],
        objective="Restore the critical engine-health.json check 'clock' to GREEN.",
        done_when="Re-run the health check and quote the GREEN line.",
        source_path="automation/state/engine-health.json",
    )
    assert safe is False
    assert reason  # a reason is always given, never blank


def test_true_for_a_clean_read_and_report_card():
    safe, reason = cards._autofire_classification(
        title="Audit the shadow ledger",
        why=["shadow ledger has not been audited in 9 days"],
        objective="Audit analysis/prod-shadow/ledger.jsonl for the last 9 days of entries.",
        done_when="Quote the count of rows audited and any anomalies found.",
        source_path="analysis/prod-shadow/ledger.jsonl",
        today=date(2026, 8, 20),  # outside the freeze window
    )
    assert safe is True
    assert "read-and-report" in reason


def test_unconditional_false_live_arming_mention():
    safe, reason = cards._autofire_classification(
        title="Investigate live arming readiness",
        why=["J asked whether live arming is close for safe-2"],
        objective="Investigate whether live arming should be considered for the safe-2 account.",
        done_when="Summarise the findings.",
        source_path="automation/state/params.json",
    )
    assert safe is False
    assert "live arming" in reason


def test_unconditional_false_secret_mention():
    safe, reason = cards._autofire_classification(
        title="Investigate credential hygiene",
        why=["quarterly secret audit is due"],
        objective="Investigate the account's secret rotation cadence documentation.",
        done_when="Summarise what you found.",
        source_path="markdown/infra/mcp-install.md",
    )
    assert safe is False
    assert "secret" in reason


def test_unconditional_false_irreversible_mention():
    safe, reason = cards._autofire_classification(
        title="Investigate the cleanup script",
        why=["cleanup script may be destructive"],
        objective="Investigate whether this action would be irreversible before proceeding.",
        done_when="Summarise the risk.",
        source_path="setup/scripts/cleanup.py",
    )
    assert safe is False
    assert "irreversible" in reason


def test_unconditional_false_frozen_trading_path_during_freeze_window():
    safe, reason = cards._autofire_classification(
        title="Audit heartbeat_core.py",
        why=["heartbeat_core.py has not been audited this window"],
        objective="Audit setup/scripts/heartbeat_core.py for dead code.",
        done_when="Summarise findings.",
        source_path="setup/scripts/heartbeat_core.py",
        today=date(2026, 9, 5),  # inside 2026-08-31 -> 2026-09-29
    )
    assert safe is False
    assert "frozen trading path" in reason


def test_frozen_path_mention_is_fine_outside_the_freeze_window():
    safe, reason = cards._autofire_classification(
        title="Audit heartbeat_core.py",
        why=["heartbeat_core.py has not been audited this window"],
        objective="Audit setup/scripts/heartbeat_core.py for dead code.",
        done_when="Summarise findings.",
        source_path="setup/scripts/heartbeat_core.py",
        today=date(2026, 8, 20),  # before the freeze opens
    )
    assert safe is True


def test_card_constructor_always_sets_both_autofire_fields():
    c = cards._card(
        card_id="card-test-1",
        title="Something broke",
        why=["evidence line"],
        source_path="automation/overnight/STATUS.md",
        source_age_h=1.0,
    )
    assert c is not None
    assert c["autofire_safe"] is False  # the default fallback objective is a "Resolve..." action
    assert isinstance(c["autofire_reason"], str) and c["autofire_reason"]

"""GOAL-PREREG-ADJUDICATION-2026-09-03 P8 guard (2026-09-05): the four adjudication
tokens EXTEND / KILL / SHIP-CANDIDATE / NULL read as TERMINAL in prereg_hygiene, so a
written verdict never re-flags as pending; prose mentions of the same words do not."""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("prereg_hygiene", ROOT / "setup" / "scripts" / "prereg_hygiene.py")
ph = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ph)


def test_bare_tokens_are_terminal():
    for st in ("EXTEND", "KILL", "SHIP-CANDIDATE", "NULL",
               "EXTEND -- accruing on Gamma_PullbackHoldShadow, n=12/30",
               "KILL -- repeats C22 backward-looking classifier shape (L118)",
               "SHIP-CANDIDATE -- for 10-30 checkpoint",
               "NULL -- A/B ran 2026-08-09, no lift, never logged"):
        assert ph._is_pending_status(st) is False, st


def test_verdict_prefix_beats_pending_tokens_in_reason():
    # The discriminating case (RED on pre-2026-09-05 code): a verdict whose reason text
    # mentions FROZEN / NOT RUN must still read as terminal.
    assert ph._is_pending_status("KILL -- was FROZEN -- NOT RUN for 30d, superseded by risky-3 KILL") is False
    assert ph._is_pending_status("NULL -- CANDIDATE ONLY grid never run; closed as null") is False
    assert ph._is_pending_status("EXTEND -- still PENDING the forward clock (n=17/25)") is False


def test_prose_mentions_stay_pending():
    for st in ("FROZEN -- not yet run against the null",
               "PENDING: will extend the window before killing",
               "FROZEN -- NOT RUN. kill criteria: null lift"):
        assert ph._is_pending_status(st) is True, st


def test_lowercase_token_is_not_a_verdict():
    assert ph._is_pending_status("extend pending run") is True
    assert ph._is_pending_status("FROZEN -- extend") is True


def test_existing_terminal_vocab_unchanged():
    assert ph._is_pending_status("RETIRED_UNRUNNABLE_AS_FROZEN -- not a verdict") is False
    assert ph._is_pending_status("CANDIDATE ONLY. Nothing armed.") is True

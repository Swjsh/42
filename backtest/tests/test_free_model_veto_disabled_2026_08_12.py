"""Guard: NO FREE MODEL HOLDS AUTHORITY OVER AN ORDER (J directive, 2026-08-12).

J: "I don't want my money in the hands of these free agents that could mess up. I'd rather
have it in the hands of Claude that I've crafted myself."

Free models remain welcome for BRAINSTORMING — prospector, twin_review and swarm_consult are
research-side and deliberately untouched by this guard. What is forbidden is a free model
deciding whether a real order is placed.

WHY THE VETO LANE WAS DISABLED — three independent charges, each sufficient:
  1. ACCURACY: veto-only accuracy 31.2% (20 TRUE vs 44 FALSE vetoes — it blocked winners
     2.2:1 over losers). 0.0% twice. 0 of 3 consecutive runs above the required 85% bar,
     failing its own OP-32 trust gate continuously since 2026-07-31.
  2. TIMING: 2026-08-12 09:51:04 ENTER_BULL -> VETOED_BY_MODELS; 09:52:04 the IDENTICAL
     verdict -> PLACED. It cost 60 s of entry timing and let the same trade through anyway.
  3. QUORUM BUG: a lone "no" vetoes when the sibling lane crashes (qwen3 no_valid_json rate
     43%), contradicting the code's own "1 dissent allowed" comment.

WHAT MUST NEVER ROT:
  * The default is DISABLED. If someone flips the default back, this file goes RED.
  * When disabled, NO model is called — not merely ignored. A disabled lane that still pays
    an inference round trip on the hot path is the latency half of charge #2.
  * `veto` is False on every disabled result, so `run_account` can never route to
    VETOED_BY_MODELS.
  * The disabling is VISIBLE in the ledger row, never silent (C7).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import heartbeat_core as hc  # noqa: E402


def test_free_model_veto_is_disabled_by_default():
    """THE DIRECTIVE. Absent an explicit opt-in env var, no free model votes on an order."""
    assert hc.FREE_MODEL_VETO_ENABLED is False, (
        "the free-model veto is enabled by default again — J's 2026-08-12 directive is that "
        "no free model holds authority over the money path")


def test_disabled_eval_never_vetoes():
    r = hc._free_model_eval("safe", {"bar_ctx": {}}, {"verdict": "ENTER_BULL", "side": "C"})
    assert r["veto"] is False
    assert r["evaluated"] is False
    assert r.get("disabled_by_config") is True


def test_disabled_eval_calls_NO_model(monkeypatch):
    """Not merely ignoring the answer — not asking the question. A disabled lane that still
    pays an inference round trip keeps the 60 s latency cost for zero decision value."""
    called = {"n": 0}

    class _Boom:
        @staticmethod
        def call_role_json(*a, **k):
            called["n"] += 1
            raise AssertionError("a model was called while the veto lane is disabled")

    monkeypatch.setitem(sys.modules, "swarm_client", _Boom)
    r = hc._free_model_eval("safe", {"bar_ctx": {}}, {"verdict": "ENTER_BEAR", "side": "P"})
    assert called["n"] == 0, "swarm_client was invoked despite the lane being disabled"
    assert r["veto"] is False


def test_disabling_is_visible_in_the_row_not_silent():
    """C7: a lane that silently stops working is indistinguishable from one that is working.
    The ledger row must say so in words a human reading the JSONL will understand."""
    r = hc._free_model_eval("bold", {"bar_ctx": {}}, {"verdict": "ENTER_BULL", "side": "C"})
    note = str(r.get("note", "")).lower()
    assert "disabled" in note, f"the disabled state is not legible in the row: {r!r}"
    assert "gamma_free_model_veto" in note, "the row must name the re-enable lever"


def test_the_veto_branch_still_exists_for_the_enabled_path():
    """Source-level: we DISABLED the lane, we did not delete the mechanism. Re-enabling must
    be a one-flag operation, and run_account must still honour a veto when it is on."""
    src = (SCRIPTS / "heartbeat_core.py").read_text(encoding="utf-8")
    assert 'rec["action"] = "VETOED_BY_MODELS"' in src, (
        "the veto branch was deleted rather than disabled — re-enabling is no longer one flag")
    assert 'GAMMA_FREE_MODEL_VETO' in src


def test_research_side_free_model_users_are_untouched():
    """Scope guard: this directive is about the MONEY path only. Free models stay in use for
    brainstorming/research, and those scripts must still exist."""
    for name in ("free_model_audit_prospector.py", "twin_review.py",
                 "free_model_audit_swarm_consult.py"):
        assert (SCRIPTS / name).exists(), (
            f"{name} disappeared — the directive was money-path only, not a purge of "
            "free-model research tooling")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

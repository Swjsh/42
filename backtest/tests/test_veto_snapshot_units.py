"""Guard: heartbeat_core._veto_snapshot never presents an unlabeled/ambiguous numeric to the
free-model veto layer -- specifically the ribbon-width-in-cents field, which used to render
as bare `spread={cents}c`.

BUG (2026-07-15, false-veto class -- #1 participation sink per markdown/audits/
DIRECTIONAL-GATE-DEEP-RESEARCH-2026-07-15.md section 3: 55 VETOED_BY_MODELS blocks since
07-01, more than every directional gate combined). REAL incident, automation/state/
core-decisions.jsonl, ts_et=2026-07-15T14:16:27, account=bold:

  spy=754.545 ribbon=BULL spread_cents=75.14435908548194 verdict=ENTER_BEAR side=P
  setup=BEARISH_REJECTION_RIDE_THE_RIBBON bear_score=7 bull_score=8

The old prompt rendered this as `spread=75.14435908548194c`. Both free-model lanes
(ollama::qwen3:14b) read that as an OPTION BID-ASK SPREAD IN DOLLARS, not the EMA-ribbon
fast-vs-slow gap in CENTS it actually is, and vetoed with: "spread value of 75.14 is
implausibly large for SPY options (typical spreads are ~$0.10-$0.50), indicating a likely
data entry error." The trailing "c" suffix alone was insufficient disambiguation. SPY
closed the day at 753.63 -- the vetoed ENTER_BEAR was directionally CORRECT; a real winner
was blocked for a units-hallucination, not a real risk finding.

FIX: heartbeat_core._veto_snapshot now renders `ribbon_width_cents=<value>` with an
explicit, unmissable parenthetical stating the unit AND that it is NOT an option spread
(mirrored into _free_model_eval's sysmsg, and into free_model_audit_heartbeat_veto.py's
verbatim _SYSMSG copy + degraded-render fallback). PRESENTATION-ONLY: the payload key
bc['ribbon_now']['spread_cents'] and the core-decisions.jsonl `spread_cents` log field are
UNCHANGED -- this guard exercises only the rendered PROMPT STRING the free models see.

RED-PROOF (section 3 below): the SAME predicate this file uses to pass the current code is
run against a verbatim reconstruction of the pre-fix inline rendering, and is shown to FAIL
against it -- proving this guard actually discriminates the bug, not a strawman.

Run: backtest/.venv/Scripts/python.exe -m pytest backtest/tests/test_veto_snapshot_units.py -q
"""
from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPTS = _REPO / "setup" / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# The exact ambiguous token the pre-fix code emitted: "spread=" immediately followed by a
# number (with an optional trailing "c"). Deliberately narrow (not a bare "spread" keyword
# ban) so it can never false-positive on unrelated prose that happens to contain the word.
_AMBIGUOUS_SPREAD_RE = re.compile(r"\bspread=\d")


@pytest.fixture()
def hc():
    return importlib.import_module("heartbeat_core")


def _real_incident_bar_ctx() -> dict:
    """Verbatim numbers from the real 2026-07-15T14:16:27 ET bold ENTER_BEAR false-veto
    (automation/state/core-decisions.jsonl) -- not invented."""
    return {
        "bar": {"close": 754.545},
        "ribbon_now": {"stack": "BULL", "spread_cents": 75.14435908548194},
        "vix_now": 15.78,
        "vix_prior": 15.75,
        "htf_15m_stack": "BULL",
        "levels_active": [],
    }


def _real_incident_verdict() -> dict:
    return {
        "verdict": "ENTER_BEAR", "side": "P",
        "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON",
        "bear_score": 7, "bull_score": 8,
        "triggers_fired": ["trendline_rejection"],
    }


def _is_units_safe(snap: str) -> bool:
    """The predicate a veto prompt must satisfy: the ribbon-width field is labeled with its
    unit AND explicitly disclaims being an option spread, and the bare ambiguous
    `spread=<number>` token is nowhere in the string."""
    return (
        "ribbon_width_cents=" in snap
        and "CENTS" in snap
        and "NOT an option" in snap
        and not _AMBIGUOUS_SPREAD_RE.search(snap)
    )


def _pre_fix_inline_rendering(bc: dict, verdict: dict) -> str:
    """Verbatim reconstruction of the pre-2026-07-15 _veto_snapshot body -- NOT calling any
    production code, so this file's RED-proof section is testing the real historical bug
    shape, not a strawman."""
    bear, bull = verdict.get("bear_score"), verdict.get("bull_score")
    scores = " ".join(s for s in (
        f"bear={bear}/10" if bear is not None else None,
        f"bull={bull}/11" if bull is not None else None,
    ) if s)
    setup_seg = f"setup={verdict.get('setup_name')}"
    if scores:
        setup_seg += f" {scores}"
    return (f"SPY={bc['bar']['close']} ribbon={bc['ribbon_now']['stack']} "
            f"spread={bc['ribbon_now']['spread_cents']}c VIX={bc['vix_now']:.2f}(prior {bc['vix_prior']:.2f}) "
            f"HTF15m={bc['htf_15m_stack']} levels_near={bc['levels_active']} "
            f"rules_engine_says={verdict.get('verdict')} side={verdict.get('side')} "
            f"{setup_seg} triggers={verdict.get('triggers_fired')}")


# =============================================================================
# 1. Current code IS units-safe, on the real incident's exact numbers
# =============================================================================
def test_real_incident_snapshot_is_units_safe(hc):
    bc = _real_incident_bar_ctx()
    verdict = _real_incident_verdict()
    snap = hc._veto_snapshot(bc, verdict)
    assert _is_units_safe(snap), snap
    # the specific number a free model misread as a dollar spread must still be present
    # (never hide the data, just label it) -- just not in the ambiguous "spread=" form
    assert "75.14" in snap


def test_ribbon_width_label_present_generic(hc):
    bc = {"bar": {"close": 500.0}, "ribbon_now": {"stack": "BEAR", "spread_cents": 12.3},
          "vix_now": 14.0, "vix_prior": 14.1, "htf_15m_stack": "BEAR", "levels_active": []}
    verdict = {"verdict": "ENTER_BEAR", "side": "P", "setup_name": "X",
              "bear_score": 5, "bull_score": 5, "triggers_fired": []}
    snap = hc._veto_snapshot(bc, verdict)
    assert "ribbon_width_cents=12.3" in snap
    assert not _AMBIGUOUS_SPREAD_RE.search(snap)


def test_never_the_raw_ambiguous_spread_form_across_varied_inputs(hc):
    """vary-and-assert (C14): sweep several spread_cents magnitudes (including one that
    LOOKS like a plausible option-dollar-spread, e.g. 0.35) -- the ambiguous bare
    `spread=<number>` token must never appear regardless of magnitude."""
    for cents in (0.0, 0.35, 12.3, 75.14435908548194, 250.0):
        bc = {"bar": {"close": 600.0}, "ribbon_now": {"stack": "MIXED", "spread_cents": cents},
              "vix_now": 16.0, "vix_prior": 16.0, "htf_15m_stack": "MIXED", "levels_active": []}
        verdict = {"verdict": "ENTER_BULL", "side": "C", "setup_name": "Y",
                  "bear_score": 3, "bull_score": 8, "triggers_fired": ["t"]}
        snap = hc._veto_snapshot(bc, verdict)
        assert _is_units_safe(snap), f"cents={cents} -> {snap}"


# =============================================================================
# 2. Sysmsg carries the same disambiguation (belt-and-suspenders: even if a future
#    rendering tweak weakens the snapshot annotation, the system prompt still warns)
# =============================================================================
def test_sysmsg_explicitly_disclaims_option_spread(hc):
    import inspect
    src = inspect.getsource(hc._free_model_eval)
    assert "ribbon_width_cents" in src
    assert "NOT an option bid-ask spread" in src


# =============================================================================
# 3. RED-PROOF: the SAME predicate, run against the verbatim pre-fix rendering, FAILS --
#    proving this guard actually discriminates the real 2026-07-15 bug, not a strawman.
# =============================================================================
def test_red_proof_old_rendering_fails_the_units_safe_predicate():
    bc = _real_incident_bar_ctx()
    verdict = _real_incident_verdict()
    old_snap = _pre_fix_inline_rendering(bc, verdict)
    # this is EXACTLY the string the free models were shown at 2026-07-15T14:16:27 ET
    assert old_snap == (
        "SPY=754.545 ribbon=BULL spread=75.14435908548194c VIX=15.78(prior 15.75) "
        "HTF15m=BULL levels_near=[] rules_engine_says=ENTER_BEAR side=P "
        "setup=BEARISH_REJECTION_RIDE_THE_RIBBON bear=7/10 bull=8/11 "
        "triggers=['trendline_rejection']"
    )
    assert not _is_units_safe(old_snap), (
        "the pre-fix rendering unexpectedly passed the units-safe predicate -- "
        "the guard would not have caught the real 2026-07-15 false-veto bug"
    )
    assert _AMBIGUOUS_SPREAD_RE.search(old_snap), "sanity: old rendering must contain spread=<num>"


def test_red_proof_current_code_no_longer_matches_old_rendering(hc):
    """Confirms the fix actually changed behavior (not a no-op): current _veto_snapshot
    output for the identical inputs must differ from the pinned pre-fix string above."""
    bc = _real_incident_bar_ctx()
    verdict = _real_incident_verdict()
    new_snap = hc._veto_snapshot(bc, verdict)
    old_snap = _pre_fix_inline_rendering(bc, verdict)
    assert new_snap != old_snap


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))

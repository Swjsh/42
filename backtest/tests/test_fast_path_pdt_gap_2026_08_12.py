"""Guard: the fast-path order route must not go LIVE + REACHABLE without Rule 7 (2026-08-12).

FOUND while auditing risk_gate for the switch-governance class -- "is every order path governed
by the authority, or does a second surface place orders on its own terms?"

setup/scripts/fast_path_executor.py is a SECOND order-placement path. In `--mode live` it POSTs
bracket orders straight to Alpaca (:723). It imports risk_gate ZERO times and instead reimplements
most of it inline -- kill switch, per-trade risk cap, min contracts, plus its own
LIVE_DAILY_FIRE_CAP. That duplication is a known cost.

WHAT IS ACTUALLY MISSING IS RULE 7. Measured by term count:

    fast_path_executor.py :  pdt 0   day_trade 0   settlement 0
    heartbeat_core.py     :  pdt 10  day_trade 8   settlement 12
    risk_gate.py          :  pdt 28  day_trade 12  settlement 16

The primary path enforces PDT and cash-settlement heavily. The fast path enforces neither. On a
cash account (pdt_gate_mode = cash_settlement on BOTH core configs) that is the constraint that
actually binds.

WHY THIS IS A GUARD AND NOT A FIX. Three facts, all verified rather than assumed:
  1. The live sentinel automation/state/fast-path-live-enabled.flag EXISTS -- and it is a
     DELIBERATE J RATIFICATION ("Fast-path live-mode RATIFIED by J on 2026-05-18 evening (paper
     accounts)"), not an accident. Deleting it would revert J's own decision.
  2. Nothing invokes it. No scheduled task matches fast_path; the only references in other
     modules are docstrings in j_intent_executor describing it as a PATTERN.
  3. Its decisions ledger was last written 2026-05-20.
So the gap is LATENT, not live, and rewiring a ratified path unattended is the wrong trade.

WHAT THIS TEST DOES: passes while the path stays dormant, and goes RED the moment it becomes
REACHABLE (scheduled, or called by another live module) while still missing PDT. That is exactly
the moment the gap stops being theoretical -- and it is the moment nobody would otherwise notice,
which is the whole failure mode this repo keeps repeating.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FAST_PATH = REPO / "setup" / "scripts" / "fast_path_executor.py"
SENTINEL = REPO / "automation" / "state" / "fast-path-live-enabled.flag"
REGISTRY = REPO / "automation" / "state" / "SCHEDULED-TASKS.md"

PDT_TERMS = ("pdt", "day_trade", "daytrade", "settled_cash", "settlement")


def _enforces_pdt() -> bool:
    """Either it delegates to risk_gate, or it implements PDT itself. Comments do not count --
    the comment-is-not-a-consumer trap bit this session three separate times."""
    src = FAST_PATH.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
    if re.search(r"^\s*(from|import).*risk_gate", code, re.M):
        return True
    return any(t in code.lower() for t in PDT_TERMS)


def _is_scheduled() -> bool:
    if not REGISTRY.exists():
        return False
    return "fast_path_executor" in REGISTRY.read_text(encoding="utf-8")


def _live_callers() -> list[str]:
    """Non-test, non-self modules that actually IMPORT it.

    IMPORTS ONLY -- deliberately. A first cut also matched the bare string
    "fast_path_executor.py" anywhere in the file and reported two false callers:

        github_audit.py:184     "...setup/scripts/fast_path_executor.py for the canonical pattern."
        spread_executor.py:290  "...CLAUDE.md secrets rule; pattern: fast_path_executor.py)."

    Both are PROSE citing it as the credential-loading pattern -- inside a message string and a
    docstring respectively, so stripping `#` comments does not remove them. Neither invokes it.
    A file that NAMES a module is not a caller; this session hit that same confusion in the params
    ratchet, the DEAD-label audit, and here. Subprocess launches would live in a .ps1 or the task
    registry, which _is_scheduled() covers separately.
    """
    out = []
    for pat in ("setup/scripts/*.py", "automation/**/*.py"):
        for f in REPO.glob(pat):
            name = f.name
            if name in ("fast_path_executor.py", "bench_fast_path_executor.py") \
                    or name.startswith("test_"):
                continue
            try:
                src = f.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
            if re.search(r"^\s*(from|import)\s+.*\bfast_path_executor\b", code, re.M):
                out.append(name)
    return sorted(set(out))


# --------------------------------------------------------------------------- the live risk


def test_fast_path_is_not_simultaneously_LIVE_REACHABLE_and_PDT_BLIND():
    """THE ALARM. Any two of these are survivable; all three together means a reachable order
    route places trades with no Rule 7 enforcement."""
    live = SENTINEL.exists()
    reachable = _is_scheduled() or bool(_live_callers())
    pdt = _enforces_pdt()
    assert not (live and reachable and not pdt), (
        f"fast_path_executor is LIVE-enabled (sentinel={live}), REACHABLE "
        f"(scheduled={_is_scheduled()}, callers={_live_callers()}) and enforces NO PDT/settlement. "
        "It places bracket orders directly at :723 and imports risk_gate zero times. Wire PDT in "
        "(or route it through risk_gate) before it can fire, or remove the live sentinel.")


def test_the_dormancy_that_makes_this_only_latent_still_holds():
    """The finding was downgraded from CRITICAL to LATENT purely because nothing calls it. If that
    changes, the downgrade is void -- so the assumption is pinned rather than remembered."""
    assert not _is_scheduled(), (
        "fast_path_executor is now SCHEDULED. It was dormant when its missing PDT enforcement was "
        "assessed as latent; that assessment no longer holds.")
    assert not _live_callers(), (
        f"fast_path_executor gained live callers {_live_callers()} -- re-assess the PDT gap.")


def test_the_pdt_gap_is_real_and_measured_not_asserted():
    """Pins the actual observation so a future reader can tell whether it was fixed or just
    re-described. If this starts failing because PDT arrived, DELETE this test -- do not soften it."""
    src = FAST_PATH.read_text(encoding="utf-8")
    code = "\n".join(ln for ln in src.splitlines() if not ln.strip().startswith("#"))
    assert "risk_gate" not in code, (
        "fast_path_executor now references risk_gate -- good; re-point or delete this test")
    assert not any(t in code.lower() for t in ("pdt", "day_trade")), (
        "fast_path_executor now mentions PDT -- verify it ENFORCES it, then delete this test")


def test_live_mode_still_requires_the_sentinel():
    """The one gate that does hold. If live mode ever stops requiring the sentinel, the whole
    latent/live distinction above collapses."""
    src = FAST_PATH.read_text(encoding="utf-8")
    assert "fast-path-live-enabled.flag" in src
    assert "sentinel.exists()" in src, "the live-mode sentinel check was removed or renamed"


def test_it_does_still_enforce_the_rules_it_claims():
    """Scope honesty: this is NOT a wholesale risk_gate bypass. Kill switch, risk cap and min
    contracts ARE implemented inline. Only Rule 7 is absent, and overstating that would be the
    same overclaim this session already had to retract twice."""
    low = FAST_PATH.read_text(encoding="utf-8").lower()
    for term in ("kill_switch", "risk_cap", "min_contracts"):
        assert term in low, f"fast_path lost its inline {term} enforcement too -- widen the alarm"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))

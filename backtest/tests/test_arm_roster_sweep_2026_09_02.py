"""A retired arm's dependents must never again be swept by hand.

09-29 SAFETY BUNDLE component (work-order §3: "safe-2 retirement mechanics -- ACCOUNTS from
accounts.json, not hardcoded").

THE THIRD SIGHTING, in the work order's own words: risky-3's retirement (2026-08-28) silently
invalidated a prereg (`ladder-x-premium`), the cheap-contract-boost lane, and its own exit A/B
leg -- "a retired arm's dependents are not swept". This file is that sweep, automated, so the
fourth sighting cannot happen quietly.

MEASURED 2026-09-02, which is why this is not theoretical: 66 modules read accounts.json
independently and twelve carry a HARDCODED arm tuple instead. Those tuples disagree with each
other and with the registry -- `risky-3` is still named in eight of them five days after
retirement, `safe-1` in three, and `journal_calendar` omits the core pair entirely. "Which arms
are live" currently has a dozen answers. safe-2's retirement is the next one scheduled and it is
a CORE arm, so the blast radius is wider than risky-3's was.

WHAT THIS FILE DOES NOT DO, deliberately: it does not ban hardcoded rosters. A module that
backfills HISTORY legitimately needs retired arms -- their fills really happened, and excluding
them would restate history. What it bans is an UNDECLARED one. Every hardcoded roster must
appear below with a reason; a new one, or one that starts naming a retired arm without saying
why, fails. The goal is that a retirement can never be silent, not that every list becomes
dynamic.

PORTED TO main 2026-09-03 (overnight queue item
THREE-MODULES-SHOULD-READ-THE-ROSTER-DYNAMICALLY): this file and arm_roster.py lived only on
`safety-bundle-2026-09-29` when this queue item was filed. quote_recorder.py,
entry_location_shadow.py and exit_coverage_check.py -- the three TODO-DYNAMIC entries this
sweep itself named -- are converted to `arm_roster.active_arms()` in this same commit and
dropped from DECLARED_HARDCODED below; the sweep now catches a FOURTH module going hardcoded-
and-undeclared the same way it already caught heartbeat_core.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
FLEET = REPO / "automation" / "state" / "fleet"
sys.path.insert(0, str(FLEET))
import arm_roster as ar  # noqa: E402

SCAN_DIRS = (REPO / "setup" / "scripts", FLEET)
ARM_RE = re.compile(r"\b(safe|bold|risky)-\d\b")
ROSTER_NAMES = {"ARMS", "ACCOUNTS", "CORE_ARMS", "ALL_ARMS", "FLEET_ARMS", "SPY_ARMS"}

# Every module allowed to hardcode an arm roster, and WHY. A bare filename is not a reason --
# the text is what a future reader uses to decide whether a retirement affects it.
DECLARED_HARDCODED = {
    "backfill_fills_enriched.py": "HISTORICAL: backfills past fills; retired arms' fills are real data",
    "sampling_gap_ledger.py": "HISTORICAL: measures sampling gaps over past sessions",
    "sim_live_parity.py": "HISTORICAL: compares sim vs live over the full recorded window",
    "broker_fills.py": "MAPPING, not a roster: arm -> core-decisions `account` field name",
    "dress_rehearsal.py": "MAPPING, not a roster: core account label -> fleet arm id",
    "journal_calendar.py": "HISTORICAL: renders past days; fleet-only by design",
    "obsidian_vault_sync.py": "GENERATED SURFACE: renders every arm that has ever traded",
    "regime_attribution.py": "HISTORICAL: attributes past trades by regime",
    "trade_matrix_build.py": "HISTORICAL: builds the matrix over all recorded trades",
    "winner_signature.py": "HISTORICAL: signatures of past winners; retired arms' trades are real data",
    "trendline_tier_rail.py": "CORE PAIR: the two mcp_heartbeat arms, which are not roster-driven",
    # ⚠️ THE ONE THAT MATTERS FOR THIS BUNDLE ITEM, found by this very sweep.
    # heartbeat_core is the LIVE ENGINE and it hardcodes its own roster as (safe-2, bold-2).
    # It does NOT read accounts.json to decide which accounts to trade -- consistent with the
    # arming asymmetry recorded in work-order 2a: fleet arms arm via the roster's `live` flag,
    # the core pair arms via GAMMA_CORE_ARMED=1 in run-heartbeat-core.ps1 and has no `live` key
    # at all. CONSEQUENCE: setting safe-2 to status=retired in accounts.json would NOT stop the
    # core engine trading it. That is precisely the "safe-2 retirement mechanics" this bundle
    # item exists to fix, and it is why the fix is a CODE change on this branch rather than a
    # registry edit. Declared (not converted) here because converting the live engine's roster
    # is a trading-path change that belongs in the reviewed bundle merge, not in a guard.
    "heartbeat_core.py": "CORE ENGINE: hardcodes (safe-2, bold-2); retirement needs a CODE change, see queue.md SAFE-2-RETIREMENT-IS-NOT-A-REGISTRY-EDIT",
}


def _hardcoded_rosters() -> dict:
    """{filename: [arm ids]} for every module-level roster constant naming real arms.

    AST, not a regex over source text -- a comment or docstring mentioning "risky-3" is not a
    roster, and this repo has already been bitten three times in one night by substring
    searches answering questions only a parser can answer (2026-09-02 lesson).
    """
    found = {}
    for d in SCAN_DIRS:
        if not d.exists():
            continue
        for p in sorted(d.rglob("*.py")):
            if "__pycache__" in p.parts or p.name.startswith("test_"):
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
            except SyntaxError:
                continue
            for node in tree.body:                      # MODULE level only
                if not isinstance(node, ast.Assign):
                    continue
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if not any(n in ROSTER_NAMES for n in names):
                    continue
                arms = []
                for sub in ast.walk(node.value):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str) \
                            and ARM_RE.fullmatch(sub.value):
                        arms.append(sub.value)
                if arms:
                    found.setdefault(p.name, [])
                    found[p.name].extend(a for a in arms if a not in found[p.name])
    return found


# ---------------------------------------------------------------------------------------
# The sweep
# ---------------------------------------------------------------------------------------

def test_every_hardcoded_roster_is_declared_with_a_reason():
    """A NEW hardcoded roster must be justified, not merely added."""
    undeclared = sorted(set(_hardcoded_rosters()) - set(DECLARED_HARDCODED))
    assert not undeclared, (
        f"{len(undeclared)} module(s) hardcode an arm roster without a declared reason: "
        f"{undeclared}. Either read the roster via arm_roster.active_arms(), or add an entry "
        f"to DECLARED_HARDCODED saying WHY the list is static -- 'historical' and 'mapping' "
        f"are both legitimate; silence is not. This is what stops the next arm retirement "
        f"from being discovered five days late."
    )


def test_the_declarations_have_not_gone_stale():
    """A declaration for a module that no longer hardcodes anything is clutter that makes the
    real ones easier to ignore."""
    actual = set(_hardcoded_rosters())
    stale = sorted(set(DECLARED_HARDCODED) - actual)
    assert not stale, (
        f"declared as hardcoded but no longer are (remove from DECLARED_HARDCODED): {stale}"
    )


def test_the_retirement_hazard_is_enumerated_not_hidden():
    """The point of the sweep: name every module whose static roster mentions a RETIRED arm.

    This does not fail on their existence -- historical modules SHOULD name them. It fails if
    such a module is undeclared, so the list is always someone's stated decision.
    """
    retired = set(ar.retired_arms())
    if not retired:
        pytest.skip("registry lists no retired arms")
    exposed = {f: sorted(set(a) & retired) for f, a in _hardcoded_rosters().items()
               if set(a) & retired}
    for fname in exposed:
        assert fname in DECLARED_HARDCODED, (
            f"{fname} hardcodes retired arm(s) {exposed[fname]} and is undeclared"
        )
    assert exposed, (
        "no hardcoded roster names a retired arm -- if that is genuinely true the sweep has "
        "nothing to protect, which would be a surprise given risky-3 and safe-1 are retired"
    )


# ---------------------------------------------------------------------------------------
# The helper itself
# ---------------------------------------------------------------------------------------

def test_active_arms_excludes_retired_and_never_returns_empty():
    active, retired = ar.active_arms(), ar.retired_arms()
    assert active, "active_arms returned empty -- a reader would silently do nothing"
    assert not (set(active) & set(retired)), (
        f"an arm is reported both active and retired: {set(active) & set(retired)}"
    )


def test_arm_roster_matches_eod_flatten_semantics():
    """The definition was LIFTED from eod_flatten._active_arms, which runs on the live flatten
    path. If the two ever disagree, the flatten sweep and everything reading this helper are
    covering different sets of accounts -- which is exactly the class of bug this closes."""
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    try:
        import eod_flatten as ef
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"eod_flatten not importable here: {exc}")
    assert sorted(ar.active_arms()) == sorted(ef._active_arms()), (
        f"arm_roster.active_arms()={sorted(ar.active_arms())} disagrees with "
        f"eod_flatten._active_arms()={sorted(ef._active_arms())}"
    )


def test_all_spy_arms_is_a_superset_of_active_and_retired():
    everything = set(ar.all_spy_arms())
    assert set(ar.active_arms()) <= everything
    assert set(ar.retired_arms()) <= everything


def test_unreadable_registry_falls_back_to_the_core_pair(tmp_path):
    missing = tmp_path / "nope.json"
    assert ar.active_arms(missing) == list(ar.CORE_FALLBACK)
    assert ar.retired_arms(missing) == [], (
        "an unreadable registry must not CLAIM arms are retired -- saying nothing is correct"
    )


def test_futures_and_sim_arms_are_excluded(tmp_path):
    """Only accounts whose number starts with PA are SPY-options arms; the registry also
    carries futures/sim placeholders that must never reach a SPY consumer."""
    reg = tmp_path / "accounts.json"
    reg.write_text('{"arms": ['
                   '{"id": "safe-9", "status": "active", "account_number": "PA123"},'
                   '{"id": "mes-sim", "status": "active", "account_number": null},'
                   '{"id": "futures-1", "status": "active"}]}', encoding="utf-8")
    assert ar.active_arms(reg) == ["safe-9"]

"""Exit-shape parity: CLAUDE.md's ribbon_ride prose vs the live code constants.

WHY THIS EXISTS (GOAL-EXIT-SHAPE-PARITY-2026-09-05): three sources disagreed on the core
`ribbon_ride` runner exit -- automation/state/params.json's top-level exit keys
(runner_max_premium_pct=2.5, v15_profit_lock_mode="fixed", v15_profit_lock_trail_pct=0.125),
automation/state/fleet/strategies.py RIBBON_RIDE's ExitShape (runner_target_pct=99.0,
profit_lock_mode="trailing", trail_pct=0.15), and CLAUDE.md's strategy paragraph prose
("runner target 2.5x ... chandelier trailing profit-lock arms at +5% favor, trails 15% off
HWM"). Full reconciliation + real-fills evidence: markdown/0dte/EXIT-SHAPE-TRUTH.md.

This is the Rule-1 parity family (commit e11c2683, see test_killswitch_threshold_parity.py for
the sibling pattern this copies): PARSE CLAUDE.md's own numbers out of its strategy paragraph,
then assert them against the code path that actually enforces them
(automation/state/fleet/strategies.py::RIBBON_RIDE.exit). A future doc edit that re-drifts the
prose away from the code fails this test instead of becoming another silent 3-way disagreement.

RED-PROOF (this test is designed to FAIL against the PRE-EDIT CLAUDE.md text, which claimed
"runner target 2.5x" and "tp1_qty_fraction 0.8 Safe / 0.667 Bold" -- neither matches
strategies.py's runner_target_pct=99.0 / tp1_qty_fraction=0.667-for-all-arms). Run:
    git show HEAD:CLAUDE.md > /tmp/claude_pre_edit.md   # or whatever revision predates this goal
    backtest/.venv/Scripts/python.exe -m pytest \
        backtest/tests/test_exit_shape_parity_2026_09_05.py -q
to see it fail against old text, then against the corrected working-tree CLAUDE.md to see it
pass. Fail-open w.r.t. J: dev/CI assertion only, never touches the live order path.

Run:
    backtest/.venv/Scripts/python.exe -m pytest \
        backtest/tests/test_exit_shape_parity_2026_09_05.py -q
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE_MD = REPO_ROOT / "CLAUDE.md"
STRATEGIES_PATH = REPO_ROOT / "automation" / "state" / "fleet"

sys.path.insert(0, str(STRATEGIES_PATH))
import strategies  # noqa: E402  (path insert must precede this import)


# --------------------------------------------------------------------------- #
# Ground truth: the live RIBBON_RIDE ExitShape (all 4 goal arms -- safe-2,    #
# bold-2, safe-3, risky-1 -- share this registry entry; only risky-1 patches #
# tp1_premium_pct in accounts.json, which does not touch these two fields).  #
# --------------------------------------------------------------------------- #
_RIBBON = strategies.by_name("ribbon_ride")
assert _RIBBON is not None, "strategies.REGISTRY must still carry a ribbon_ride entry"

LIVE_RUNNER_TARGET_PCT = _RIBBON.exit.runner_target_pct     # 99.0 (unconstrained sentinel)
LIVE_TP1_QTY_FRACTION = _RIBBON.exit.tp1_qty_fraction       # 0.667, shared by all 4 arms
LIVE_TRAIL_PCT = _RIBBON.exit.trail_pct                     # 0.15
LIVE_PROFIT_LOCK_ARM_PCT = _RIBBON.exit.profit_lock_arm_pct  # 0.05
LIVE_CATASTROPHE_STOP_PCT = _RIBBON.exit.catastrophe_stop_pct  # -0.50

# Anything at or above this counts as CLAUDE.md-parlance "unconstrained" -- the registry's
# own docstring calls 99.0 "tgt-none"; treat any target this large as the same claim so a
# future re-tuning of the sentinel's exact value doesn't need a matching edit here.
UNCONSTRAINED_THRESHOLD = 10.0


def _read_claude_md(text: str | None = None) -> str:
    return text if text is not None else CLAUDE_MD.read_text(encoding="utf-8")


def _find_strategy_paragraph(md_text: str) -> str:
    """The one paragraph this goal is scoped to correct (starts at "Current rule version")."""
    m = re.search(r"\*\*Current rule version:.*?(?=\n\n|\Z)", md_text, re.S)
    assert m, "CLAUDE.md must still carry the 'Current rule version' strategy paragraph"
    return m.group(0)


def _parse_runner_target(paragraph: str) -> float | None:
    """Returns a finite runner-target multiple (e.g. 2.5 for 'runner target 2.5x'), or None
    if the paragraph instead claims the target is unconstrained/sentinel (no finite number
    to compare -- e.g. 'runner target UNCONSTRAINED (99.0x...)')."""
    if re.search(r"runner target\s+UNCONSTRAINED", paragraph, re.I):
        return None
    m = re.search(r"runner target\s+([\d.]+)\s*[x×]", paragraph, re.I)
    assert m, f"could not find a 'runner target N x' claim in paragraph: {paragraph!r}"
    return float(m.group(1))


def _parse_tp1_qty_fraction_claims(paragraph: str) -> dict[str, float]:
    """Returns {'ribbon_ride_all_arms': X} for the corrected phrasing, or
    {'safe': X, 'bold': Y} for the pre-edit 'N Safe / M Bold' phrasing -- either way, the
    caller decides what each claim must equal."""
    m_shared = re.search(r"tp1_qty_fraction\s+([\d.]+)\s+ribbon_ride\s+all\s+arms", paragraph, re.I)
    if m_shared:
        return {"ribbon_ride_all_arms": float(m_shared.group(1))}
    m_split = re.search(
        r"tp1_qty_fraction\s+([\d.]+)\s+Safe\s*/\s*([\d.]+)\s+Bold", paragraph, re.I
    )
    assert m_split, f"could not find a tp1_qty_fraction claim in paragraph: {paragraph!r}"
    return {"safe": float(m_split.group(1)), "bold": float(m_split.group(2))}


def test_ribbon_ride_registry_still_carries_the_shape_this_test_pins():
    """Sanity: if strategies.py's shape drifts, fail here with a clear message rather than
    a confusing downstream assertion."""
    assert LIVE_RUNNER_TARGET_PCT == pytest.approx(99.0)
    assert LIVE_TP1_QTY_FRACTION == pytest.approx(0.667)
    assert LIVE_TRAIL_PCT == pytest.approx(0.15)
    assert LIVE_PROFIT_LOCK_ARM_PCT == pytest.approx(0.05)


def test_claude_md_runner_target_matches_code_or_is_correctly_unconstrained():
    """CLAUDE.md must either state a finite runner target that matches the code, or (the
    corrected, current state) explicitly say the target is unconstrained -- never claim a
    finite number the code does not enforce."""
    paragraph = _find_strategy_paragraph(_read_claude_md())
    claimed = _parse_runner_target(paragraph)
    if claimed is None:
        # Corrected phrasing: the code must actually be unconstrained.
        assert LIVE_RUNNER_TARGET_PCT >= UNCONSTRAINED_THRESHOLD, (
            "CLAUDE.md claims the runner target is unconstrained but "
            f"strategies.py RIBBON_RIDE.exit.runner_target_pct={LIVE_RUNNER_TARGET_PCT} "
            "is a finite target -- drift in the OTHER direction."
        )
    else:
        assert claimed == pytest.approx(LIVE_RUNNER_TARGET_PCT), (
            f"CLAUDE.md claims runner target {claimed}x but "
            f"strategies.py RIBBON_RIDE.exit.runner_target_pct={LIVE_RUNNER_TARGET_PCT} "
            "-- doc/code drift (this is the exact GOAL-EXIT-SHAPE-PARITY-2026-09-05 bug)."
        )


def test_claude_md_tp1_qty_fraction_matches_code():
    """CLAUDE.md's tp1_qty_fraction claim must match the shared ribbon_ride shape (0.667 for
    every arm, not a per-account 0.8/0.667 split -- that split described a different,
    non-ribbon_ride reading)."""
    paragraph = _find_strategy_paragraph(_read_claude_md())
    claims = _parse_tp1_qty_fraction_claims(paragraph)
    if "ribbon_ride_all_arms" in claims:
        assert claims["ribbon_ride_all_arms"] == pytest.approx(LIVE_TP1_QTY_FRACTION), (
            f"CLAUDE.md claims tp1_qty_fraction {claims['ribbon_ride_all_arms']} for "
            f"ribbon_ride but strategies.py says {LIVE_TP1_QTY_FRACTION}."
        )
    else:
        # Pre-edit phrasing ("0.8 Safe / 0.667 Bold") -- fails because ribbon_ride is
        # 0.667 on BOTH accounts, not split by account.
        pytest.fail(
            "CLAUDE.md claims a per-account tp1_qty_fraction split "
            f"(safe={claims['safe']}, bold={claims['bold']}) but ribbon_ride's live shape "
            f"(strategies.py RIBBON_RIDE.exit.tp1_qty_fraction={LIVE_TP1_QTY_FRACTION}) is "
            "IDENTICAL for every arm -- this is the drifted pre-correction claim."
        )


def test_claude_md_chandelier_profit_lock_matches_code():
    """The one part of the pre-edit paragraph that was ALREADY correct: arm +5% / trail 15%
    matches strategies.py exactly (params.json's 0.125/'fixed' does not -- see
    EXIT-SHAPE-TRUTH.md). Guard it so it can't silently drift either."""
    paragraph = _find_strategy_paragraph(_read_claude_md())
    m_arm = re.search(r"arms at \+(\d+)%\s*favor", paragraph, re.I)
    m_trail = re.search(r"trails (\d+)%\s*off HWM", paragraph, re.I)
    assert m_arm and m_trail, f"could not find chandelier arm/trail claims in: {paragraph!r}"
    claimed_arm_pct = float(m_arm.group(1)) / 100.0
    claimed_trail_pct = float(m_trail.group(1)) / 100.0
    assert claimed_arm_pct == pytest.approx(LIVE_PROFIT_LOCK_ARM_PCT)
    assert claimed_trail_pct == pytest.approx(LIVE_TRAIL_PCT)


def test_red_proof_against_pre_edit_claude_md_text():
    """RE-PROOF: this test must FAIL when run against the pre-edit paragraph text (quoted
    verbatim from `git show HEAD~0:CLAUDE.md` before this goal's correction), proving the
    guard actually catches the drift it was built for, not just a tautology against
    whatever the working tree currently says."""
    pre_edit_paragraph = (
        "**Current rule version: v15.3** (Safe; ratified live 2026-06-01 · Bold on v15.2). "
        "**Chart-stop-primary** (2026-06-18): chart-level / ribbon-flip-back / chandelier "
        "profit-lock are the primary invalidation; premium stops are now −50% catastrophe "
        "caps both sides (was bear −20% / bull −8%). Per-tier strike selection — "
        "**live truth (fills-verified 2026-07-11): core Safe trades ATM** via "
        "`crypto/lib/strike_selection.py#V15_SAFE_TIERS` (hardcoded 2026-06-18, supersedes the "
        "old OTM-3/$1K / OTM-2/$2-10K ladder prose; `params.json`'s ladder is vestigial on the "
        "live core path — reconciliation: "
        "`analysis/deep-research/2026-07-11-strike-tier-reconciliation.md`), chandelier "
        "trailing profit-lock (arms at +5% favor, trails 15% off HWM), 09:35 ET entry gate, "
        "tp1_qty_fraction 0.8 Safe / 0.667 Bold (Safe raised 2026-06-28, pk-2026-06-28-001), "
        "runner target 2.5×. **Source of truth:** "
        "[`automation/state/params.json`](automation/state/params.json). Rule mismatch = "
        "kill-switch event."
    )
    claimed_runner = _parse_runner_target(pre_edit_paragraph)
    assert claimed_runner == pytest.approx(2.5)  # the pre-edit claim, parsed correctly
    # This is the actual RED-proof: the pre-edit claim does NOT match the live code.
    with pytest.raises(AssertionError):
        assert claimed_runner == pytest.approx(LIVE_RUNNER_TARGET_PCT)

    claims = _parse_tp1_qty_fraction_claims(pre_edit_paragraph)
    assert claims == {"safe": 0.8, "bold": 0.667}  # the pre-edit claim, parsed correctly
    # And the pre-edit per-account split does not equal ribbon_ride's shared 0.667 for BOTH.
    assert claims["safe"] != pytest.approx(LIVE_TP1_QTY_FRACTION)


def test_no_finite_exit_patch_secretly_overrides_runner_target_for_the_4_goal_arms():
    """vary-and-assert companion: confirm neither safe-3's nor risky-1's accounts.json
    exit_patch touches runner_target_pct/trail_pct/profit_lock_arm_pct -- if a future patch
    adds one, this test must be updated deliberately, not silently pass a now-wrong claim."""
    import json

    accounts = json.loads(
        (REPO_ROOT / "automation" / "state" / "fleet" / "accounts.json").read_text(
            encoding="utf-8"
        )
    )
    touched_runner_fields = {"runner_target_pct", "trail_pct", "profit_lock_arm_pct"}
    for arm in accounts["arms"]:
        if arm.get("id") not in {"safe-2", "bold-2", "safe-3", "risky-1"}:
            continue
        patch = (arm.get("params_patch") or {}).get("exit_patch") or {}
        overridden = touched_runner_fields & set(patch)
        assert not overridden, (
            f"arm {arm.get('id')!r} exit_patch now overrides {overridden} -- "
            "EXIT-SHAPE-TRUTH.md's 'all 4 goal arms share runner_target_pct=99.0' claim is "
            "stale; update the doc before this test is allowed to pass again."
        )

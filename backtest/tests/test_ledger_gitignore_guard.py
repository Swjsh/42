"""Graduated guard (2026-07-14 stash-drop data-loss incident + 2026-07-20 recurrence).

The live decision ledgers are continuously written, tracked-but-rarely-committed files.
On 2026-07-14 a tree-wide `git stash` + `git stash drop` in the shared checkout reverted
them to a 3-week-old commit, destroying 2026-06-27..07-13 history (recovered via
`git fsck --unreachable` -> branch recovery/stash-data-loss-2026-07-14).

Fix: the ledgers are gitignored + untracked so no routine git operation can ever touch
them again. This guard REDs if any of them becomes trackable again.

2026-07-20 SAME MECHANISM RECURRED on a different file class: circuit-breaker*.json +
today-bias.json (overwritten-in-place JSON snapshots, not append logs) were also
tracked-but-rarely-committed and got silently reverted BACKWARD to 2026-07-14 content
twice in one day by `git stash`/`checkout` operations colliding with live writers. Same
fix applied (see STATE_SNAPSHOTS below) -- a re-violated lesson graduated to code per
OP-25. See automation/overnight/queue.md STATE-FILE-REVERSION-2026-07-20.
"""
import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE_FRESHNESS_MANIFEST = REPO / "automation" / "state" / "state-freshness-manifest.json"

LEDGERS = [
    "automation/state/core-decisions.jsonl",
    "automation/state/fleet/risky-1/decisions.jsonl",
    "automation/state/fleet/risky-3/decisions.jsonl",
    "automation/state/fleet/safe-3/decisions.jsonl",
]

# 2026-07-20 STATE-FILE-REVERSION incident: same mechanism, different files. These are
# overwritten-in-place JSON snapshots (not append logs) that were last committed 2026-07-14
# but written continuously since -- a `git stash`/`checkout`/`reset` in the shared checkout
# silently reverts kill-switch state + morning bias BACKWARD to that stale snapshot.
# Reproduced live twice the same day (04:27/05:58 ET premarket, 18:40 ET mid-session).
STATE_SNAPSHOTS = [
    "automation/state/circuit-breaker.json",
    "automation/state/aggressive/circuit-breaker.json",
    "automation/state/fleet/risky-1/circuit-breaker.json",
    "automation/state/fleet/risky-3/circuit-breaker.json",
    "automation/state/fleet/safe-1/circuit-breaker.json",
    "automation/state/fleet/safe-3/circuit-breaker.json",
    "automation/state/today-bias.json",
    "automation/state/futures/today-bias.json",
]

# STATE-FILE-REVERSION-AUDIT-FOLLOWUP (2026-07-21): triage of the ~76 tracked files under
# automation/state/ whose mtime runs >3 days ahead of their last commit (script + full list
# in this fire's STATUS.md entry). These 13 are the confirmed DECISION-GATING overwritten-
# in-place hazard class (same mechanism as STATE_SNAPSHOTS above -- a git stash/checkout in
# the shared checkout can revert them backward and silently misrepresent CURRENT trailing-
# stop/breaker/level/position/intent state to a live decision path). The other ~63 flagged
# files were reviewed and judged LOWER-RISK (display/diagnostic/derived-cache surfaces whose
# reversion would show stale info, not silently misdirect an entry/exit/kill-switch/sizing
# decision) and deliberately left tracked -- not unclassified, a completed lower-priority call.
DECISION_GATING_SNAPSHOTS = [
    "automation/state/fleet/safe-2/exit-state.json",
    "automation/state/fleet/bold-2/exit-state.json",
    "automation/state/crypto-twin/breaker.json",
    "automation/state/crypto-twin/exit-state.json",
    "automation/state/crypto-twin/scenario-state.json",
    "automation/state/crypto-twin/sim-bear-scenario-state.json",
    "automation/state/crypto-twin/sim-bear-positions.json",
    "automation/state/key-levels.json",
    "automation/state/daily-context.json",
    "automation/state/sight-beacon.json",
    "automation/state/fleet/shared-signal.json",
    "automation/state/futures/mirror-shadow-state.json",
    "automation/state/futures/mirror-positions.json",
    "automation/state/j-intents.json",
]

# STATE-FRESHNESS-REVERSION-FOLLOWUP-2 (2026-08-10): the 2026-07-21 triage above missed these 6.
# state_freshness_audit.py (built 2026-07-30, a sibling detector for this exact class) caught
# them RED/YELLOW tonight -- all last-committed 2026-07-14/07-15 (the SAME stash-drop-incident
# commit as LEDGERS/STATE_SNAPSHOTS above) despite live-verified continuous rewrites since (their
# own producer logs show fresh today's-date output computed and written every 5-10min cycle, yet
# the on-disk file kept reading back as the stale 07-14/07-15 committed snapshot). Same mechanism,
# different file set -- the prior sweep's "confirmed 13" list was a partial triage, not exhaustive.
STATE_FRESHNESS_REVERSION_FOLLOWUP_2 = [
    "automation/state/key-levels-memory.json",
    "automation/state/prior-rth-close.json",
    "automation/state/trade-today.json",
    "automation/state/confluence-zones.json",
    "automation/state/ema-snapshot.json",
    "automation/state/context-bundle.json",
]


def test_decision_ledgers_are_gitignored():
    for path in LEDGERS:
        r = subprocess.run(
            ["git", "-C", str(REPO), "check-ignore", "-q", path],
            capture_output=True,
        )
        assert r.returncode == 0, (
            f"{path} is NOT gitignored -- a tree-wide git stash/reset in the shared "
            f"checkout can silently destroy its uncommitted live history again "
            f"(2026-07-14 incident). Re-add it to .gitignore and `git rm --cached` it."
        )


def test_decision_ledgers_are_untracked():
    r = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--", *LEDGERS],
        capture_output=True,
        text=True,
    )
    tracked = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert not tracked, (
        f"Still tracked in the index (gitignore alone does not untrack): {tracked}. "
        f"Run `git rm --cached <path>` for each."
    )


def test_state_snapshots_are_gitignored():
    for path in STATE_SNAPSHOTS:
        r = subprocess.run(
            ["git", "-C", str(REPO), "check-ignore", "-q", path],
            capture_output=True,
        )
        assert r.returncode == 0, (
            f"{path} is NOT gitignored -- a tree-wide git stash/checkout/reset in the "
            f"shared checkout can silently revert live kill-switch/bias state backward "
            f"to a stale committed snapshot (2026-07-20 STATE-FILE-REVERSION incident, "
            f"reproduced twice same day). Re-add it to .gitignore and `git rm --cached` it."
        )


def test_state_snapshots_are_untracked():
    r = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--", *STATE_SNAPSHOTS],
        capture_output=True,
        text=True,
    )
    tracked = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert not tracked, (
        f"Still tracked in the index (gitignore alone does not untrack): {tracked}. "
        f"Run `git rm --cached <path>` for each."
    )


def test_decision_gating_snapshots_are_gitignored():
    for path in DECISION_GATING_SNAPSHOTS:
        r = subprocess.run(
            ["git", "-C", str(REPO), "check-ignore", "-q", path],
            capture_output=True,
        )
        assert r.returncode == 0, (
            f"{path} is NOT gitignored -- a tree-wide git stash/checkout/reset in the "
            f"shared checkout can silently revert live trailing-stop/breaker/level/"
            f"position/intent state backward to a stale committed snapshot "
            f"(STATE-FILE-REVERSION-AUDIT-FOLLOWUP, 2026-07-21). Re-add it to "
            f".gitignore and `git rm --cached` it."
        )


def test_decision_gating_snapshots_are_untracked():
    r = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--", *DECISION_GATING_SNAPSHOTS],
        capture_output=True,
        text=True,
    )
    tracked = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert not tracked, (
        f"Still tracked in the index (gitignore alone does not untrack): {tracked}. "
        f"Run `git rm --cached <path>` for each."
    )


def test_state_freshness_reversion_followup_2_are_gitignored():
    for path in STATE_FRESHNESS_REVERSION_FOLLOWUP_2:
        r = subprocess.run(
            ["git", "-C", str(REPO), "check-ignore", "-q", path],
            capture_output=True,
        )
        assert r.returncode == 0, (
            f"{path} is NOT gitignored -- a tree-wide git stash/checkout/reset in the "
            f"shared checkout can silently revert this live producer's output backward "
            f"to a stale 2026-07-14/07-15 committed snapshot (state_freshness_audit.py "
            f"caught it RED/YELLOW, 2026-08-10). Re-add it to .gitignore and "
            f"`git rm --cached` it."
        )


def test_state_freshness_reversion_followup_2_are_untracked():
    r = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "--", *STATE_FRESHNESS_REVERSION_FOLLOWUP_2],
        capture_output=True,
        text=True,
    )
    tracked = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert not tracked, (
        f"Still tracked in the index (gitignore alone does not untrack): {tracked}. "
        f"Run `git rm --cached <path>` for each."
    )


# ---------------------------------------------------------------------------------------
# MANIFEST-DRIVEN GUARD (2026-08-10) -- closes the class, not just this incident's instances.
# ---------------------------------------------------------------------------------------
# Four rounds of this exact mechanism (2026-07-14, 07-20, 07-21, 08-10) were each fixed with a
# NEW hand-curated list above -- each round's triage was a snapshot, not a standing check, so
# the NEXT new live-state producer added to state-freshness-manifest.json (the repo's own
# authoritative list of continuously-rewritten decision-relevant state) could silently repeat
# the incident a 5th time with nobody noticing until engine-health.json goes RED again. This
# test reads that manifest directly and checks EVERY entry, so a future manifest addition that
# forgets the gitignore/untrack step fails HERE, at test time, instead of silently reverting
# weeks of live state first. Two entries this fire (premarket-readiness.json, news.json) were
# found by this exact cross-check -- they were RED/YELLOW in tonight's audit but missed by the
# STATE_FRESHNESS_REVERSION_FOLLOWUP_2 list above (which only captured the first 6 noticed).

def _manifest_paths() -> list[str]:
    try:
        raw = json.loads(STATE_FRESHNESS_MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []  # manifest unreadable -- nothing to check, not a guard failure
    entries = raw.get("entries") if isinstance(raw, dict) else raw
    if not isinstance(entries, list):
        return []
    return [e["path"] for e in entries if isinstance(e, dict) and e.get("path")]


def test_state_freshness_manifest_entries_are_gitignored():
    paths = _manifest_paths()
    assert paths, "state-freshness-manifest.json unreadable or empty -- check the fixture path"
    not_ignored = []
    for path in paths:
        r = subprocess.run(["git", "-C", str(REPO), "check-ignore", "-q", path], capture_output=True)
        if r.returncode != 0:
            not_ignored.append(path)
    assert not not_ignored, (
        f"These state-freshness-manifest.json entries are NOT gitignored, so a tree-wide git "
        f"stash/checkout/reset in the shared checkout can silently revert them backward to a "
        f"stale committed snapshot (the 2026-07-14/07-20/07-21/08-10 recurring incident class): "
        f"{not_ignored}. Add each to .gitignore and `git rm --cached` it."
    )


def test_state_freshness_manifest_entries_are_untracked():
    paths = _manifest_paths()
    assert paths, "state-freshness-manifest.json unreadable or empty -- check the fixture path"
    r = subprocess.run(["git", "-C", str(REPO), "ls-files", "--", *paths], capture_output=True, text=True)
    tracked = [ln for ln in r.stdout.splitlines() if ln.strip()]
    assert not tracked, (
        f"These state-freshness-manifest.json entries are still tracked in the index (gitignore "
        f"alone does not untrack): {tracked}. Run `git rm --cached <path>` for each."
    )

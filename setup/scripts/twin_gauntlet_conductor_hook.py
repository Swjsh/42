"""twin_gauntlet_conductor_hook.py -- B2b: the advisory "trading-path commit without a
twin-gauntlet pass" flag.

markdown/planning/TWIN-PROGRAM.md value stream #2: "Conductor hook: trading-path
commits without a gauntlet pass get flagged." This module IS that hook's detection
logic -- a small, pure-stdlib, fail-open check: has any commit since the last check
touched a TRADING-PATH file, and if so, does path-coverage.json (or a matching
gauntlet-last.json run) show a GREEN/PASS result for that file's mapped gauntlet
path(s) dated AFTER the commit? If not, emit ONE loud, deduplicated flag to
STATUS.md "## Known broken" + a pickable queue.md backlog item.

ADVISORY ONLY, NEVER A COMMIT-BLOCKER (fail-open by construction): run_check()
catches every exception internally and always returns a result dict rather than
raising -- nothing that calls this can be broken by it, mirrors
setup/scripts/status_retention.py's L181 fail-open contract and
setup/guard_runner_slow.py's transition-only STATUS.md flag pattern (a persisting
gap is NOT re-spammed every fire -- only a NEW implicated commit re-triggers the
flag; see the watermark's `last_flagged_head_sha` dedup key).

TWO CALL-SITES share this ONE module (and its ONE watermark file, so calling it
from both is idempotent -- whichever fires first flags; the other sees the same
head sha already flagged and no-ops):
  1. setup/scripts/run-conductor.ps1 -- the PRIMARY, frequent after-hours driver
     (invoked via Invoke-PythonHidden, same pattern as the existing L181
     status_retention.py autowire call, right before the claude launch).
  2. setup/guard_runner_slow.py -- the GUARANTEED-nightly fallback (Gamma_GuardsNightly
     fires once/night at 22:30 MT regardless of whether the conductor woke up that
     night at all -- a real reliability gap the conductor-only hook would leave open).

FILE -> PATH MAPPING (conservative = broad/inclusive; an advisory flag firing when
it technically didn't need to costs nothing, an unflagged real gap costs a
mechanism bug shipped to SPY through an unverified code path -- see
markdown/planning/TWIN-PROGRAM.md's kill criteria on config leaks / hidden
coupling). Per this session's instructions: "exit_manager -> all exit branches;
entry files -> ORGANIC_SIGNAL/entry." Orchestration-layer files that plausibly
touch BOTH entry and exit (fleet_executor/fleet_live/heartbeat_core) map to EVERY
gauntlet path rather than guessing which half of a diff changed.

Usage (standalone, for manual/testing invocation -- ALWAYS exits 0, advisory only):
    backtest\\.venv\\Scripts\\python.exe setup\\scripts\\twin_gauntlet_conductor_hook.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from et_clock import et_now  # noqa: E402
import twin_gauntlet as tg  # noqa: E402  (same crew's own module -- no B1-coupling concern)

STATUS_PATH = REPO / "automation" / "overnight" / "STATUS.md"
QUEUE_MD_PATH = REPO / "automation" / "overnight" / "queue.md"
WATERMARK_PATH = tg.TWIN_STATE / "gauntlet-conductor-watermark.json"
COVERAGE_PATH = tg.COVERAGE_PATH
GAUNTLET_LAST_PATH = tg.LAST_RESULT_PATH

# On a first-ever run (no watermark yet) look back this many commits -- bounded so
# a fresh clone / first fire never floods STATUS.md with the project's entire history.
DEFAULT_MAX_COMMITS = 50

_ALL_EXIT_PATHS = tuple(p for p in tg.PATH_REGISTRY if p != "entry")
_ALL_PATHS = tuple(tg.PATH_REGISTRY)

TRADING_PATH_FILES: dict[str, tuple[str, ...]] = {
    # exit-family: exit_manager owns every exit-lifecycle branch; exit_actuator is its
    # live wrapper (automation/state/fleet/exit_actuator.py) -- same coverage.
    "exit_manager.py": _ALL_EXIT_PATHS,
    "exit_actuator.py": _ALL_EXIT_PATHS,
    # orchestration-layer: plausibly touches entry AND exit dispatch -- map broadly.
    "fleet_executor.py": _ALL_PATHS,
    "fleet_live.py": _ALL_PATHS,
    "heartbeat_core.py": _ALL_PATHS,
    # entry-family: signal/gate files -- "entry files -> ORGANIC_SIGNAL/entry".
    "strategies.py": ("entry",),
    "build_shared_signal.py": ("entry",),
    "risk_gate.py": ("entry",),
}


# ============================================================================
# git log (injectable for tests -- see test_twin_gauntlet_conductor_hook.py)
# ============================================================================

def _default_git_log(repo_root: Path, since_sha: Optional[str], max_commits: int) -> list[dict]:
    """Real git log parser -- subprocess only (no GitPython; pure stdlib per
    Invoke-PythonHidden's system-python constraint). Returns commits OLDEST-FIRST
    (chronological), each: {"sha", "ts_utc" (iso, UTC), "subject", "files": [...]}.
    Fail-open: any git error / git not on PATH -> []  (never raises)."""
    args = ["git", "log", "--name-only", "--pretty=format:%x00COMMIT%x01%H%x01%ct%x01%s"]
    if since_sha:
        args.append(f"{since_sha}..HEAD")
    else:
        args += ["-n", str(max_commits)]
    try:
        proc = subprocess.run(args, cwd=str(repo_root), capture_output=True, text=True,
                              timeout=30, encoding="utf-8", errors="replace")
        if proc.returncode != 0:
            return []
        out = proc.stdout
    except Exception:  # noqa: BLE001 -- fail-open, never raise
        return []

    commits = []
    for block in out.split("\x00COMMIT\x01"):
        block = block.strip("\n")
        if not block:
            continue
        lines = block.splitlines()
        parts = lines[0].split("\x01")
        if len(parts) < 3:
            continue
        sha, ts_raw, subject = parts[0], parts[1], parts[2]
        try:
            ts_utc = datetime.fromtimestamp(int(ts_raw), tz=timezone.utc).isoformat()
        except (ValueError, OSError):
            continue
        files = [ln for ln in lines[1:] if ln.strip()]
        commits.append({"sha": sha, "ts_utc": ts_utc, "subject": subject, "files": files})
    commits.reverse()  # git log emits newest-first; scanning wants oldest-first
    return commits


# ============================================================================
# pure detection logic
# ============================================================================

def map_files_to_paths(files: list[str]) -> set[str]:
    """Basename-substring match (robust to directory moves/renames) against
    TRADING_PATH_FILES. Pure."""
    mapped: set[str] = set()
    for f in files:
        base = f.replace("\\", "/").rsplit("/", 1)[-1]
        if base in TRADING_PATH_FILES:
            mapped |= set(TRADING_PATH_FILES[base])
    return mapped


def detect_gap(*, commits: list[dict], watermark: dict, coverage: dict, gauntlet_last: dict) -> dict:
    """PURE (every input already loaded/injected -- no I/O here). `commits` must be
    oldest-first. Decides which mapped paths, if any, are UNCOVERED (no green
    result dated after the commit that touched them) and whether that gap is
    NEW (dedup via watermark['last_flagged_head_sha'] -- a persisting, already-
    flagged gap does not re-flag every fire)."""
    implicated: dict[str, list[dict]] = {}
    for c in commits:
        for p in map_files_to_paths(c["files"]):
            implicated.setdefault(p, []).append(c)
    if not implicated:
        return {"flag_needed": False, "implicated": {}, "newest_commit_sha": commits[-1]["sha"] if commits else None}

    newest_commit_sha = commits[-1]["sha"]
    cov_paths = (coverage or {}).get("paths") or {}
    gl_paths = (gauntlet_last or {}).get("paths") or {}
    gl_ts = (gauntlet_last or {}).get("ts_et")

    uncovered: dict[str, list[dict]] = {}
    for path_id, touching_commits in implicated.items():
        newest_touch = max(datetime.fromisoformat(c["ts_utc"]) for c in touching_commits)
        covered = False
        rec = cov_paths.get(path_id)
        if isinstance(rec, dict) and rec.get("status") == "green" and rec.get("last_updated_utc"):
            try:
                if datetime.fromisoformat(str(rec["last_updated_utc"])) > newest_touch:
                    covered = True
            except ValueError:
                pass
        if not covered and gl_paths.get(path_id) == "PASS" and gl_ts:
            # gauntlet-last.json has no per-path timestamp -- only the whole run's ts_et.
            # Conservative: an OLDER whole-run cannot vouch for a NEWER commit.
            try:
                if datetime.fromisoformat(str(gl_ts)) > newest_touch:
                    covered = True
            except ValueError:
                pass
        if not covered:
            uncovered[path_id] = touching_commits

    if not uncovered:
        return {"flag_needed": False, "implicated": implicated, "newest_commit_sha": newest_commit_sha}

    already_flagged = watermark.get("last_flagged_head_sha") == newest_commit_sha
    return {"flag_needed": not already_flagged, "implicated": uncovered, "newest_commit_sha": newest_commit_sha}


def _format_message(implicated: dict[str, list[dict]]) -> str:
    paths_s = ", ".join(sorted(implicated))
    shas = sorted({c["sha"][:7] for commits in implicated.values() for c in commits})
    shown = ", ".join(shas[:5]) + (", ..." if len(shas) > 5 else "")
    return (f"trading-path commit(s) [{shown}] have NO twin-gauntlet PASS since for mapped "
           f"path(s): {paths_s}. Run: backtest\\.venv\\Scripts\\python.exe "
           f"setup\\scripts\\twin_gauntlet.py --paths {paths_s}")


# ============================================================================
# I/O: watermark + STATUS.md / queue.md flag (advisory, fail-open, atomic)
# ============================================================================

def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2))
        os.replace(tmp, str(path))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _load_watermark(path: Path) -> dict:
    return _load_json(path)


def _save_watermark(path: Path, data: dict) -> None:
    _atomic_write_json(path, data)


def _flag_status_md(message: str, *, status_path: Path, now_et: datetime) -> None:
    """Append ONE loud line under '## Known broken' -- mirrors
    setup/guard_runner_slow.py's _flag_status_md exactly (newest-first insert,
    fail-open on a missing file/marker)."""
    try:
        text = status_path.read_text(encoding="utf-8")
    except OSError:
        return
    marker = "## Known broken"
    if marker not in text:
        return
    line = f"- [{now_et.strftime('%Y-%m-%dT%H:%M:%S')}] TWIN-GAUNTLET-GAP: {message}"
    head, _, tail = text.partition(marker + "\n")
    status_path.write_text(f"{head}{marker}\n\n{line}\n{tail.lstrip(chr(10))}", encoding="utf-8")


def _flag_queue_md(message: str, *, queue_path: Path, now_et: datetime) -> None:
    """Append ONE pickable backlog item under '## Active backlog', matching
    queue.md's established `- [ ] <id> (<priority>, tags) :: <desc> :: depends:X ::
    status:Y` convention so the conductor loop can pick it up naturally."""
    task_id = f"TWIN-GAUNTLET-GAP-{now_et.strftime('%Y%m%d-%H%M')}"
    line = (f"- [ ] {task_id} (HIGH, twin-program, advisory-not-blocking) :: {message} "
           f":: depends:none :: status:pending\n")
    try:
        text = queue_path.read_text(encoding="utf-8")
    except OSError:
        return
    marker = "## Active backlog"
    if marker in text:
        head, _, tail = text.partition(marker + "\n")
        queue_path.write_text(f"{head}{marker}\n{line}{tail}", encoding="utf-8")
    else:
        with queue_path.open("a", encoding="utf-8") as fh:
            fh.write("\n" + line)


# ============================================================================
# orchestrator
# ============================================================================

def run_check(*, repo_root: Path = REPO, now_et: Optional[datetime] = None,
             watermark_path: Path = WATERMARK_PATH, coverage_path: Path = COVERAGE_PATH,
             gauntlet_last_path: Path = GAUNTLET_LAST_PATH, status_path: Path = STATUS_PATH,
             queue_path: Path = QUEUE_MD_PATH, max_commits: int = DEFAULT_MAX_COMMITS,
             git_log_fn=None) -> dict:
    """Advisory, fail-open, NEVER a commit-blocker. Every exception is caught HERE
    (not just by callers) so this is safe to `import ...; run_check()` from
    anywhere without a try/except at the call-site (both call-sites wrap it in one
    anyway, defense in depth)."""
    now_et = now_et or et_now()
    try:
        watermark = _load_watermark(watermark_path)
        log_fn = git_log_fn or _default_git_log
        commits = log_fn(repo_root, watermark.get("last_checked_commit"), max_commits)
        if not commits:
            return {"checked": True, "flagged": False, "reason": "no new commits", "commits": 0}

        coverage = _load_json(coverage_path)
        gauntlet_last = _load_json(gauntlet_last_path)
        gap = detect_gap(commits=commits, watermark=watermark, coverage=coverage,
                         gauntlet_last=gauntlet_last)

        new_watermark = dict(watermark)
        new_watermark["last_checked_commit"] = commits[-1]["sha"]
        new_watermark["last_checked_at_et"] = now_et.isoformat()

        flagged = False
        message = None
        if gap["flag_needed"]:
            message = _format_message(gap["implicated"])
            _flag_status_md(message, status_path=status_path, now_et=now_et)
            _flag_queue_md(message, queue_path=queue_path, now_et=now_et)
            new_watermark["last_flagged_head_sha"] = gap["newest_commit_sha"]
            new_watermark["last_flagged_at_et"] = now_et.isoformat()
            flagged = True

        _save_watermark(watermark_path, new_watermark)
        return {"checked": True, "flagged": flagged, "message": message, "commits": len(commits),
               "implicated_paths": sorted(gap.get("implicated", {}))}
    except Exception as e:  # noqa: BLE001 -- ADVISORY ONLY: must never raise into a caller
        return {"checked": False, "flagged": False, "error": f"{type(e).__name__}: {e}"}


def main(argv: Optional[list[str]] = None) -> int:
    result = run_check()
    print(json.dumps(result, indent=2))
    return 0  # ALWAYS 0 -- advisory, never a blocker, even on its own internal error


if __name__ == "__main__":
    raise SystemExit(main())

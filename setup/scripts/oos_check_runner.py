"""oos_check_runner.py — nightly runner that un-strands promote_keeper proposals.

THE GAP THIS CLOSES (PIPELINE-AUDIT-2026-07-01 break #4): promote_keeper emits
proposals with eval_bar_cleared=false that WAIT for an OOS validation pass —
but contender_oos_check.py had NO scheduled runner, so proposals stranded
forever (eval_bar_cleared flipped exactly once, by hand, badly).

Each nightly fire (Gamma_OosCheck, 20:30 ET / 18:30 MT):
  1. Runs promote_keeper (emit/refresh a proposal from the newest
     contender-rank-*.json; idempotent, exits quietly when already proposed).
  2. Selects pending promote_keeper proposals (status=pending,
     eval_bar_cleared=false) whose contender_file is STILL the newest ranking
     (older proposals are superseded — validating them would mislabel, because
     contender_oos_check always validates the newest file's top entry).
  3. Runs contender_oos_check.py per selected proposal as a hidden subprocess
     (backtest venv — it loads OPRA data + runs the real-fills backtest) which
     writes analysis/recommendations/{proposal_id}-scorecard.json.
  4. When the scorecard says eval_bar_cleared=true (all 5 OP-11 gates incl.
     CONFIRM-BEFORE-CAPITAL recency), flips eval_bar_cleared + attaches the
     scorecard path on the proposal row in conductor-proposals.jsonl
     (atomic rewrite). The actuator/J can then act on a VALIDATED proposal.
  5. ALWAYS exits 0 (fail-open — a scheduler must never see a crash loop);
     every step logs to automation/state/logs/oos-check-{date}.log.

NEVER edits params.json, NEVER arms anything, NEVER places orders — it only
validates and flips the eval bar on proposal rows. Stdlib only in-process;
the heavy backtest runs in the venv subprocess.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "oos-check-runner.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "oos-check-runner.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
RECS_DIR = REPO / "analysis" / "recommendations"
PROPOSALS_FILE = REPO / "automation" / "state" / "conductor-proposals.jsonl"
LOGS_DIR = REPO / "automation" / "state" / "logs"
VENV_PY = REPO / "backtest" / ".venv" / "Scripts" / "python.exe"
OOS_CHECK = REPO / "backtest" / "autoresearch" / "contender_oos_check.py"

MAX_CHECKS_PER_FIRE = 3          # heavy backtests — bound the nightly load
SUBPROCESS_TIMEOUT_S = 5400      # 90 min per check, generous for OPRA load
CREATE_NO_WINDOW = 0x08000000    # C8: child console procs of pythonw flash on Win11

_log_path: Optional[Path] = None


def _log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).replace(microsecond=0).isoformat()} {msg}"
    print(line)
    if _log_path is not None:
        try:
            with _log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError:
            pass


def _load_proposals(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, dict):
                rows.append(obj)
        except json.JSONDecodeError:
            continue
    return rows


def newest_contender_name(recs_dir: Path) -> Optional[str]:
    files = sorted(recs_dir.glob("contender-rank-*.json"))
    return files[-1].name if files else None


def select_pending(proposals: list[dict[str, Any]], newest_contender: Optional[str]) -> list[dict[str, Any]]:
    """Pending promote_keeper proposals still eligible for OOS validation.

    Eligible = source promote_keeper, status pending, eval_bar_cleared falsy,
    AND contender_file == the newest ranking (contender_oos_check validates the
    newest file's top entry — running it for a superseded proposal would attach
    the wrong evidence). Superseded rows are logged, not validated.
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in proposals:
        pid = str(row.get("proposal_id", ""))
        if (row.get("source") != "promote_keeper"
                or row.get("status") != "pending"
                or row.get("eval_bar_cleared")
                or not pid or pid in seen):
            continue
        seen.add(pid)
        if newest_contender and row.get("contender_file") != newest_contender:
            _log(f"SKIP {pid}: contender_file={row.get('contender_file')} superseded by {newest_contender}")
            continue
        out.append(row)
    return out


def apply_cleared_scorecard(
    proposals_path: Path,
    proposal_id: str,
    scorecard_rel: str,
) -> bool:
    """Flip eval_bar_cleared=true + attach the scorecard on ONE proposal row.

    Atomic rewrite via temp file. Returns True when a row was updated.
    Immutable per-row: builds new dicts, never mutates parsed rows in place.
    """
    if not proposals_path.exists():
        return False
    lines = proposals_path.read_text(encoding="utf-8").splitlines()
    new_lines: list[str] = []
    updated = False
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError:
            new_lines.append(line)
            continue
        if (isinstance(row, dict)
                and row.get("proposal_id") == proposal_id
                and row.get("source") == "promote_keeper"
                and not row.get("eval_bar_cleared")):
            new_row = {
                **row,
                "eval_bar_cleared": True,
                "scorecard": scorecard_rel,
                "oos_validation_needed": False,
                "oos_cleared_at": datetime.now(timezone.utc).replace(microsecond=0)
                                  .isoformat().replace("+00:00", "Z"),
                "oos_cleared_by": "oos_check_runner (Gamma_OosCheck nightly)",
            }
            new_lines.append(json.dumps(new_row))
            updated = True
        else:
            new_lines.append(line)
    if updated:
        tmp = proposals_path.with_suffix(".jsonl.tmp")
        tmp.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        tmp.replace(proposals_path)
    return updated


def _run_promote_keeper() -> None:
    """Refresh proposals from the newest contender-rank (in-process, stdlib-only).

    POISON-PILL lesson (kitchen_daemon 2026-07-01): ALWAYS pass explicit argv —
    a bare main() would read THIS runner's sys.argv. SystemExit is contained.
    """
    sys.path.insert(0, str(REPO / "setup" / "scripts"))
    try:
        import promote_keeper  # noqa: E402
        rc = promote_keeper.main([])
        _log(f"promote_keeper rc={rc}")
    except SystemExit as exc:
        _log(f"promote_keeper SystemExit({exc.code}) — contained, continuing")
    except Exception as exc:  # noqa: BLE001 — fail-open
        _log(f"promote_keeper ERROR {type(exc).__name__}: {exc} — continuing")


def _run_oos_check(proposal_id: str) -> Optional[dict[str, Any]]:
    """Run contender_oos_check.py in the backtest venv, hidden; return its scorecard.

    Exit code is NOT trusted (it returns 1 on gates-fail by design; C7 — audit
    the OUTPUT): we read the scorecard JSON it writes.
    """
    if not VENV_PY.exists():
        _log(f"ERROR venv python missing: {VENV_PY}")
        return None
    cmd = [str(VENV_PY), str(OOS_CHECK), "--proposal-id", proposal_id]
    _log(f"RUN {' '.join(cmd)}")
    try:
        proc = subprocess.run(
            cmd, cwd=str(REPO), capture_output=True, text=True,
            timeout=SUBPROCESS_TIMEOUT_S,
            creationflags=CREATE_NO_WINDOW if sys.platform == "win32" else 0,
        )
        _log(f"contender_oos_check rc={proc.returncode}")
        tail = (proc.stdout or "").strip().splitlines()[-8:]
        for t in tail:
            _log(f"  | {t}")
        if proc.stderr and proc.returncode not in (0, 1):
            _log(f"  stderr: {proc.stderr.strip()[:500]}")
    except subprocess.TimeoutExpired:
        _log(f"TIMEOUT contender_oos_check for {proposal_id} after {SUBPROCESS_TIMEOUT_S}s")
        return None
    except OSError as exc:
        _log(f"SPAWN ERROR: {exc}")
        return None

    scorecard_path = RECS_DIR / f"{proposal_id}-scorecard.json"
    if not scorecard_path.exists():
        _log(f"NO scorecard written for {proposal_id} — check failed upstream")
        return None
    try:
        return json.loads(scorecard_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        _log(f"scorecard unreadable for {proposal_id}: {exc}")
        return None


def main() -> int:
    global _log_path
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    _log_path = LOGS_DIR / f"oos-check-{datetime.now(timezone.utc).date().isoformat()}.log"
    _log("=== Gamma_OosCheck fire start ===")

    try:
        # Step 1: refresh proposals from the newest ranking.
        _run_promote_keeper()

        # Step 2: select validatable pending proposals.
        newest = newest_contender_name(RECS_DIR)
        _log(f"newest contender file: {newest}")
        pending = select_pending(_load_proposals(PROPOSALS_FILE), newest)
        _log(f"pending validatable proposals: {[p.get('proposal_id') for p in pending]}")

        # Steps 3-4: validate + flip on clear.
        for row in pending[:MAX_CHECKS_PER_FIRE]:
            pid = str(row["proposal_id"])
            scorecard = _run_oos_check(pid)
            if scorecard is None:
                continue
            cleared = bool(scorecard.get("eval_bar_cleared"))
            _log(f"{pid}: eval_bar_cleared={cleared} "
                 f"failed_gates={scorecard.get('failed_gates', [])}")
            if cleared:
                rel = f"analysis/recommendations/{pid}-scorecard.json"
                if apply_cleared_scorecard(PROPOSALS_FILE, pid, rel):
                    _log(f"{pid}: proposal row FLIPPED eval_bar_cleared=true (scorecard={rel})")
                else:
                    _log(f"{pid}: WARN scorecard cleared but no proposal row updated")
    except Exception as exc:  # noqa: BLE001 — fail-open, always exit 0
        _log(f"FATAL-CONTAINED {type(exc).__name__}: {exc}")

    _log("=== Gamma_OosCheck fire end (exit 0 always) ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Persistent watcher: polls Gamma state files and DMs J on meaningful changes.

Watches:
- backtest/autoresearch/_state/weekend-progress.json -- phase transitions
- backtest/autoresearch/_state/random_search/batch_P0.jsonl -- new top candidates
- analysis/recommendations/v15.json -- v15 ratification scorecard appears
- automation/state/kill-switch -- presence triggers urgent alert
- automation/state/circuit-breaker.json -- if .tripped flips true
- automation/state/backtest-drift.json -- if drift severity is high

Writes one outbox row per transition. Bridge sends within 15s.
Idempotent: tracks last-seen state in `automation/state/.discord-watcher-state.json`
so it doesn't re-alert on restarts.

Run:
    python setup/scripts/discord-watcher.py
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT ============================================================
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# (Windows Terminal) will allocate a visible WT tab the first time the process writes
# to stdout/stderr. Redirect stdio to log files BEFORE logging.basicConfig() runs.
# See CLAUDE.md OP 27 L38 + 2026-05-16 evening foot-gun.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower() == "pythonw.exe":
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "discord-watcher.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "discord-watcher.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

import datetime as dt
import json
import logging
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
OUTBOX_PATH = STATE_DIR / "discord-outbox.jsonl"
WATCHER_STATE_PATH = STATE_DIR / ".discord-watcher-state.json"
PID_PATH = STATE_DIR / "discord-watcher.pid"

# Watched paths.
WEEKEND_PROGRESS = REPO / "backtest" / "autoresearch" / "_state" / "weekend-progress.json"
RANDOM_BATCH = REPO / "backtest" / "autoresearch" / "_state" / "random_search" / "batch_P0.jsonl"
V15_SCORECARD = REPO / "analysis" / "recommendations" / "v15.json"
V15_STRESS = REPO / "analysis" / "recommendations" / "v15-stress-test.json"
V15_WALK_FORWARD = REPO / "analysis" / "recommendations" / "v15-walk-forward.json"
V15_REFINED = REPO / "backtest" / "autoresearch" / "_state" / "seed6_refined" / "refined_params.json"
V15_J_EDGE = REPO / "analysis" / "recommendations" / "v15-j-edge.json"
KILL_SWITCH = STATE_DIR / "kill-switch"
CIRCUIT_BREAKER = STATE_DIR / "circuit-breaker.json"
DRIFT = STATE_DIR / "backtest-drift.json"

POLL_INTERVAL_SEC = 30

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def _load_user_mention() -> str:
    """Load J's user_id from .discord-config.json and format as @mention prefix."""
    cfg_path = STATE_DIR / ".discord-config.json"
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))  # BOM-tolerant
        uid = cfg.get("user_id")
        return f"<@{uid}> " if uid else ""
    except Exception:
        return ""


def queue_message(content: str, mention: bool = True) -> None:
    """Append to outbox JSONL. Bridge will send. @mention J by default per his
    2026-05-09 PM request (so notifications actually ping)."""
    prefix = _load_user_mention() if mention else ""
    row = {"queued_at": now_iso(), "content": prefix + content}
    with OUTBOX_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    logger.info("queued: %s", (prefix + content)[:80])


def load_state() -> dict:
    if WATCHER_STATE_PATH.exists():
        try:
            return json.loads(WATCHER_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "last_phase": None,
        "last_p0_completed": 0,
        "last_top_score": None,
        "v15_seen": False,
        "kill_switch_seen": False,
        "circuit_breaker_tripped_seen": False,
        "drift_severity_seen": None,
    }


def save_state(s: dict) -> None:
    tmp = WATCHER_STATE_PATH.with_suffix(WATCHER_STATE_PATH.suffix + ".tmp")
    tmp.write_text(json.dumps(s, indent=2), encoding="utf-8")
    tmp.replace(WATCHER_STATE_PATH)


def write_pid() -> None:
    import os
    PID_PATH.write_text(f"{os.getpid()}|{now_iso()}", encoding="utf-8")


def cleanup_pid() -> None:
    try:
        PID_PATH.unlink()
    except FileNotFoundError:
        pass


def _read_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _peek_top_candidate() -> tuple[int | None, float | None]:
    """Return (seed, val_pnl) of best candidate seen so far in batch_P0.jsonl."""
    if not RANDOM_BATCH.exists():
        return None, None
    best_seed = None
    best_score = float("-inf")
    with RANDOM_BATCH.open(encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                vm = rec.get("validate_metrics") or {}
                tm = rec.get("train_metrics") or {}
                val_pnl = float(vm.get("total_pnl") or 0)
                train_sh = float(tm.get("sharpe_daily") or 0)
                # Only count candidates with positive train sharpe (not regime-overfit).
                if train_sh > 0 and val_pnl > best_score:
                    best_score = val_pnl
                    best_seed = rec.get("seed")
            except Exception:
                continue
    if best_seed is None:
        return None, None
    return best_seed, best_score


def check_phase_transition(s: dict) -> None:
    progress = _read_json(WEEKEND_PROGRESS)
    if not progress:
        return
    current_phase = progress.get("phase")
    if not current_phase:
        return
    # Baseline first observation -- never alert on backfill.
    if "last_phase_initialized" not in s:
        s["last_phase"] = current_phase
        s["last_phase_initialized"] = True
        logger.info("phase baseline initialised at %s -- no alert on backfill", current_phase)
        return
    if current_phase != s.get("last_phase"):
        queue_message(f"**Weekend research:** phase `{s.get('last_phase')}` -> `{current_phase}`")
        s["last_phase"] = current_phase


def check_p0_progress(s: dict) -> None:
    """Alert at 25/50/75/100% completion milestones (only on TRUE crossings, not backfill)."""
    if not RANDOM_BATCH.exists():
        return
    completed = sum(1 for _ in RANDOM_BATCH.open(encoding="utf-8"))

    # First-run baseline: if last_p0_completed has never been set, just snapshot
    # the current count without firing any milestones. Avoids the "watcher
    # restart fires 4 alerts at once" failure mode.
    if "last_p0_completed_initialized" not in s:
        s["last_p0_completed"] = completed
        s["last_p0_completed_initialized"] = True
        logger.info("p0 baseline initialised at %d -- no alerts on backfill", completed)
        return

    last = s.get("last_p0_completed", 0)
    milestones = [15, 30, 45, 60]  # 25/50/75/100% of 60-seed batch
    for m in milestones:
        if last < m <= completed:
            seed, score = _peek_top_candidate()
            if seed is not None:
                queue_message(
                    f"**PHASE 0 progress: {completed}/60 seeds.** "
                    f"Top regime-robust candidate so far: seed {seed} val_pnl=${score:+.0f}"
                )
            else:
                queue_message(f"**PHASE 0 progress: {completed}/60 seeds.** No regime-robust candidate yet.")
    s["last_p0_completed"] = completed


def check_v15_appeared(s: dict) -> None:
    if s.get("v15_seen"):
        return
    if V15_SCORECARD.exists():
        v15 = _read_json(V15_SCORECARD) or {}
        verdict = v15.get("verdict", "UNKNOWN")
        winner = v15.get("winner") or v15.get("candidate", {})
        msg = f"**v15 SCORECARD READY** -- verdict: `{verdict}`"
        if isinstance(winner, dict) and winner.get("seed") is not None:
            seed = winner.get("seed")
            val_pnl = winner.get("validate_metrics", {}).get("total_pnl")
            train_sh = winner.get("train_metrics", {}).get("sharpe_daily")
            msg += f"\nWinner: seed {seed}, val_pnl=${val_pnl:+.0f}, train_sharpe={train_sh:+.2f}"
        msg += "\nFile: `analysis/recommendations/v15.json`"
        msg += "\n\nReply `approve v15` to ratify Monday morning, or `reject` to stay on v14."
        queue_message(msg)
        s["v15_seen"] = True


def check_v15_refinement_artifacts(s: dict) -> None:
    """Alert on completion of stress test, walk-forward, or hill-climb refinement."""
    # Stress test
    if not s.get("v15_stress_seen") and V15_STRESS.exists():
        d = _read_json(V15_STRESS) or {}
        msg = (
            f"📊 **v15 stress-test done**\n"
            f"- {d.get('n_event_days', 0)} event days replayed\n"
            f"- total P&L: **${d.get('total_pnl_across_event_days', 0):+,.0f}**\n"
            f"- {d.get('total_trades', 0)} trades, WR {int(d.get('agg_win_rate', 0)*100)}%\n"
            f"- file: `analysis/recommendations/v15-stress-test.json`"
        )
        queue_message(msg)
        s["v15_stress_seen"] = True

    # Walk-forward
    if not s.get("v15_walk_seen") and V15_WALK_FORWARD.exists():
        d = _read_json(V15_WALK_FORWARD) or {}
        n_pos = d.get("n_pos_pnl", 0)
        n_total = d.get("n_windows", 0)
        msg = (
            f"📊 **v15 walk-forward done**\n"
            f"- {n_pos}/{n_total} windows positive ({int(d.get('pos_pnl_pct', 0)*100)}%)\n"
            f"- avg window P&L: **${d.get('avg_window_pnl', 0):+,.0f}**\n"
            f"- total: **${d.get('total_pnl', 0):+,.0f}** across {d.get('total_trades', 0)} trades\n"
            f"- file: `analysis/recommendations/v15-walk-forward.json`"
        )
        queue_message(msg)
        s["v15_walk_seen"] = True

    # J-edge search (CLAUDE.md operating principle 16)
    if V15_J_EDGE.exists():
        d = _read_json(V15_J_EDGE) or {}
        # Track by edge_capture value -- alert when it CHANGES (a better candidate found)
        cur_score = d.get("winner_edge_capture", 0)
        last_score = s.get("v15_j_edge_last_score")
        if last_score is None:
            # First time we see this file -- baseline, don't alert (might be smoke test)
            s["v15_j_edge_last_score"] = cur_score
            s["v15_j_edge_first_seen_seed"] = d.get("winner_seed")
        elif cur_score != last_score:
            cap_pct = int(d.get("winner_winners_capture_pct", 0) * 100)
            baseline = d.get("baseline_v14_edge_capture", 0)
            msg = (
                f"📊 **v15-J-edge: new best candidate**\n"
                f"- seed: **{d.get('winner_seed')}**\n"
                f"- edge_capture: **${cur_score:+.0f}** (was ${last_score:+.0f}, baseline v14 ${baseline:+.0f})\n"
                f"- captures: **{cap_pct}%** of J's $1542\n"
                f"- losers added: ${d.get('winner_losers_added', 0):.0f}\n"
                f"- val_pnl tiebreak: ${d.get('winner_validate_pnl', 0):+.0f}\n"
                f"- file: `analysis/recommendations/v15-j-edge.json`"
            )
            queue_message(msg)
            s["v15_j_edge_last_score"] = cur_score

    # Hill-climb refinement
    if not s.get("v15_refined_seen") and V15_REFINED.exists():
        d = _read_json(V15_REFINED) or {}
        keeps = d.get("keeps", 0)
        reverts = d.get("reverts", 0)
        baseline_val = d.get("starting_baseline", {}).get("validate", {}).get("total_pnl", 0)
        final_score = d.get("final_score", 0)
        improvement = final_score - baseline_val
        msg = (
            f"📊 **v15 hill-climb refinement done**\n"
            f"- {keeps} keeps / {reverts} reverts ({d.get('iterations', 0)} iters)\n"
            f"- baseline val_pnl: **${baseline_val:+,.0f}**\n"
            f"- refined score:    **${final_score:+,.0f}**\n"
            f"- improvement:      **${improvement:+,.0f}**\n"
            f"- file: `_state/seed6_refined/refined_params.json`"
        )
        queue_message(msg)
        s["v15_refined_seen"] = True


def check_kill_switch(s: dict) -> None:
    exists_now = KILL_SWITCH.exists()
    if exists_now and not s.get("kill_switch_seen"):
        queue_message("**ALERT: kill-switch file appeared.** Trading halted. Investigate immediately.")
        s["kill_switch_seen"] = True
    elif not exists_now and s.get("kill_switch_seen"):
        queue_message("Kill-switch cleared.")
        s["kill_switch_seen"] = False


def check_circuit_breaker(s: dict) -> None:
    cb = _read_json(CIRCUIT_BREAKER)
    if not cb:
        return
    tripped = bool(cb.get("tripped"))
    if tripped and not s.get("circuit_breaker_tripped_seen"):
        equity = cb.get("current_equity") or 0
        start = cb.get("start_equity_today") or 0
        pnl = equity - start
        queue_message(
            f"**ALERT: circuit-breaker TRIPPED.** Today P&L ${pnl:+.0f} on start equity ${start:.0f}. "
            f"No new entries today."
        )
        s["circuit_breaker_tripped_seen"] = True
    elif not tripped and s.get("circuit_breaker_tripped_seen"):
        s["circuit_breaker_tripped_seen"] = False  # reset for next day


def check_drift(s: dict) -> None:
    d = _read_json(DRIFT)
    if not d:
        return
    sev = d.get("severity")
    if sev and sev != s.get("drift_severity_seen") and sev in ("medium", "high"):
        queue_message(f"**Backtest drift detected:** severity=`{sev}`. See `automation/state/backtest-drift.json`.")
        s["drift_severity_seen"] = sev
    elif sev == "low":
        s["drift_severity_seen"] = sev


def main() -> int:
    write_pid()
    logger.info("Discord watcher starting (poll=%ds)", POLL_INTERVAL_SEC)
    state = load_state()

    consecutive_errors = 0
    try:
        while True:
            try:
                check_phase_transition(state)
                check_p0_progress(state)
                check_v15_appeared(state)
                check_v15_refinement_artifacts(state)
                check_kill_switch(state)
                check_circuit_breaker(state)
                check_drift(state)
                save_state(state)
                consecutive_errors = 0
            except Exception as e:
                consecutive_errors += 1
                logger.exception("watcher tick error #%d", consecutive_errors)
                if consecutive_errors >= 5:
                    queue_message(f"**ALERT: discord-watcher hit {consecutive_errors} consecutive errors.** Last: {e}")
                    time.sleep(120)
                    consecutive_errors = 0
            time.sleep(POLL_INTERVAL_SEC)
    except KeyboardInterrupt:
        logger.info("Discord watcher stopped (KeyboardInterrupt)")
    finally:
        cleanup_pid()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

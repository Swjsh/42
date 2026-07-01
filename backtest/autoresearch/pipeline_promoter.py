"""Pipeline promoter — auto-promote a passing scorecard to WATCH mode in params.json.

Called by kitchen_daemon._run_pipeline_scorecard() after a terminal scorecard script
(e.g. shotgun_scalper_stage5) completes successfully.

Gates (must ALL pass for auto-promote):
  1. walk_forward.passed        — OOS test window net-positive
  2. wf_ratio >= 0.70           — test_pnl / train_pnl (OP-22 WF gate)
  3. sub_window_stable          — all test quarters net-positive
  4. anchor_no_regression       — directional_score >= 2 on J's winner days
  5. concentration_ok           — top_5_pct <= 0.50 (OP-20 gate)

On pass: writes watcher_name_stage5_cleared=true + best_combo to params.json,
         appends Discord notification to discord-outbox.jsonl,
         writes A/B scorecard to analysis/recommendations/promote_{watcher_name}.json.

Exec-arm (extra_setup_exec_armed) is NOT set by this script — that requires J (live money gate).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
RECS_DIR = REPO / "analysis" / "recommendations"
STATE_DIR = REPO / "automation" / "state"
DISCORD_OUTBOX = STATE_DIR / "discord-outbox.jsonl"
PARAMS_PATH = STATE_DIR / "params.json"
AGG_PARAMS_PATH = STATE_DIR / "aggressive" / "params.json"

# OP-22 auto-ship gates
WF_RATIO_GATE = 0.70          # test_pnl / train_pnl
MIN_DIRECTIONAL_SCORE = 2     # J's anchor days: fire in the right direction
MAX_CONCENTRATION = 0.50      # top-5 days <= 50% of total P&L
MAX_SCORECARD_AGE_DAYS = 7    # freshness guard: refuse stale scorecards (the
                              # dash-variant fallback once resolved to a 2026-05-16
                              # file — promoting on 6-week-old research is a bug)


def _et_now() -> datetime:
    now_utc = datetime.now(timezone.utc)
    y = now_utc.year
    march = datetime(y, 3, 1, tzinfo=timezone.utc)
    dst_start = (march + timedelta(days=(6 - march.weekday()) % 7 + 7)).replace(hour=7)
    nov = datetime(y, 11, 1, tzinfo=timezone.utc)
    dst_end = (nov + timedelta(days=(6 - nov.weekday()) % 7)).replace(hour=6)
    offset = -4 if (dst_start <= now_utc < dst_end) else -5
    return (now_utc + timedelta(hours=offset)).replace(tzinfo=None)


def _scorecard_age_days(path: Path, scorecard: dict) -> float:
    """Age of a scorecard in days — generated_at field if parseable, else file mtime."""
    gen = scorecard.get("generated_at")
    if gen:
        try:
            gen_dt = datetime.fromisoformat(str(gen).replace("Z", "+00:00"))
            if gen_dt.tzinfo is None:
                gen_dt = gen_dt.replace(tzinfo=timezone.utc)
            return (datetime.now(timezone.utc) - gen_dt).total_seconds() / 86400.0
        except ValueError:
            pass
    try:
        return (datetime.now(timezone.utc).timestamp() - path.stat().st_mtime) / 86400.0
    except OSError:
        return float("inf")


def _read_scorecard(script_name: str) -> Optional[dict]:
    """Read the JSON scorecard produced by the stage5 script.

    Freshness guard (2026-07-01): refuse scorecards older than
    MAX_SCORECARD_AGE_DAYS. The dash-variant fallback below can resolve to a
    stale file from a long-dead run; auto-promoting on it would ship weeks-old
    research as if it were tonight's result.
    """
    candidates = [
        RECS_DIR / f"{script_name}.json",
        RECS_DIR / f"{script_name.replace('_stage5', '-stage5')}.json",
        RECS_DIR / f"{script_name.replace('_', '-')}.json",
    ]
    for p in candidates:
        if p.exists():
            try:
                scorecard = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            age_days = _scorecard_age_days(p, scorecard)
            if age_days > MAX_SCORECARD_AGE_DAYS:
                print(
                    f"[pipeline_promoter] REFUSED stale scorecard {p.name} "
                    f"(age={age_days:.1f}d > {MAX_SCORECARD_AGE_DAYS}d freshness gate)",
                    file=sys.stderr,
                )
                continue
            return scorecard
    return None


def _check_gates(scorecard: dict) -> tuple[bool, dict]:
    """Return (gates_passed, details_dict)."""
    details: dict = {}

    # Gate 1+2: walk-forward
    wf = scorecard.get("walk_forward", {})
    wf_passed = wf.get("passed", False)
    train_pnl = float(wf.get("train_pnl", 0) or 0)
    test_pnl = float(wf.get("test_pnl", 0) or 0)
    wf_ratio = (test_pnl / train_pnl) if train_pnl > 0 else 0.0
    details["wf_passed"] = wf_passed
    details["wf_ratio"] = round(wf_ratio, 3)
    details["wf_ratio_gate"] = WF_RATIO_GATE

    # Gate 3: sub-window stability (all test quarters positive)
    test_pos_quarters = int(wf.get("test_positive_quarters", 0))
    total_test_quarters = int(wf.get("total_test_quarters", 2))
    sub_stable = test_pos_quarters == total_test_quarters and total_test_quarters > 0
    details["sub_window_stable"] = sub_stable
    details["test_positive_quarters"] = test_pos_quarters

    # Gate 4: anchor no-regression (directional_score from stage4 winners)
    best = scorecard.get("best_keeper", scorecard.get("winner", {}))
    dir_score = int(best.get("directional_score", best.get("dir_score", 0)) or 0)
    anchor_ok = dir_score >= MIN_DIRECTIONAL_SCORE
    details["anchor_no_regression"] = anchor_ok
    details["directional_score"] = dir_score

    # Gate 5: concentration
    top5_pct = float(best.get("top5_pct", best.get("concentration_top5", 1.0)) or 1.0)
    conc_ok = top5_pct <= MAX_CONCENTRATION
    details["concentration_ok"] = conc_ok
    details["top5_pct"] = round(top5_pct, 3)

    passed = wf_passed and wf_ratio >= WF_RATIO_GATE and sub_stable and anchor_ok and conc_ok
    details["all_gates_passed"] = passed
    return passed, details


def _write_discord_ping(watcher_name: str, details: dict, scorecard: dict) -> None:
    best = scorecard.get("best_keeper", scorecard.get("winner", {}))
    wide_pnl = best.get("wide_pnl", "?")
    exp = best.get("expectancy_per_trade", best.get("wide_expectancy", "?"))
    msg = (
        f"PIPELINE PROMOTE: **{watcher_name}** cleared all 5 gates.\n"
        f"WF ratio={details['wf_ratio']:.2f} (gate={WF_RATIO_GATE}) | "
        f"OOS quarters={details['test_positive_quarters']} pos | "
        f"dir_score={details['directional_score']} | "
        f"top5={details['top5_pct']:.0%} | "
        f"wide_pnl=${wide_pnl} | exp/trade=${exp}\n"
        f"Watcher flag set: {watcher_name}_stage5_cleared=true in params.json.\n"
        f"ARM to trade: add extra_setup_exec_armed['{watcher_name}']=true.\n"
        f"Scorecard: analysis/recommendations/promote_{watcher_name}.json"
    )
    event = {
        "ts": _et_now().isoformat(),
        "channel": "gamma-ops",
        "message": msg,
        "source": "pipeline_promoter",
    }
    try:
        with open(DISCORD_OUTBOX, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
    except OSError:
        pass


def _write_promote_scorecard(watcher_name: str, details: dict, scorecard: dict) -> None:
    out = {
        "promoted_at_et": _et_now().isoformat(),
        "watcher_name": watcher_name,
        "gates": details,
        "best_keeper": scorecard.get("best_keeper", scorecard.get("winner", {})),
        "walk_forward": scorecard.get("walk_forward", {}),
        "exec_armed": False,
        "note": (
            "Auto-promoted to WATCH_NOT_ARMED. "
            "Set extra_setup_exec_armed[watcher_name]=true in params.json to arm execution."
        ),
    }
    path = RECS_DIR / f"promote_{watcher_name}.json"
    RECS_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2), encoding="utf-8")


def _write_watch_flag_to_params(params_path: Path, watcher_name: str, best_combo: dict) -> None:
    """Write watcher_name_stage5_cleared=True + best_combo snapshot into params.json.

    Does NOT set extra_setup_exec_armed — that requires J (live money gate, OP-0).
    Atomic write via temp file.
    """
    if not params_path.exists():
        return
    try:
        params = json.loads(params_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    cleared_key = f"{watcher_name}_stage5_cleared"
    combo_key = f"{watcher_name}_best_combo"
    doc_key = f"_{watcher_name}_promote_doc"

    # Immutable update: build a new dict
    updated = {
        **params,
        cleared_key: True,
        combo_key: best_combo,
        doc_key: (
            f"AUTO-PROMOTED by pipeline_promoter. All 5 gates passed. "
            f"WATCH_NOT_ARMED (exec not armed). "
            f"Arm: extra_setup_exec_armed['{watcher_name}']=true."
        ),
    }

    tmp = params_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(updated, indent=2), encoding="utf-8")
    tmp.replace(params_path)


def check_and_promote(script_name: str, watcher_name: str) -> bool:
    """Entry point called by kitchen_daemon after a scorecard script runs.

    Returns True if all gates passed and the watcher was promoted.
    """
    scorecard = _read_scorecard(script_name)
    if scorecard is None:
        print(f"[pipeline_promoter] no scorecard JSON found for {script_name}", file=sys.stderr)
        return False

    passed, details = _check_gates(scorecard)

    promote_path = RECS_DIR / f"promote_{watcher_name}.json"
    RECS_DIR.mkdir(parents=True, exist_ok=True)
    promote_path.write_text(
        json.dumps({"gates_checked_at_et": _et_now().isoformat(), "gates": details, "passed": passed}, indent=2),
        encoding="utf-8",
    )

    if not passed:
        failed = [k for k, v in details.items() if k != "all_gates_passed" and v is False]
        print(f"[pipeline_promoter] {watcher_name} BLOCKED — failed gates: {failed}", file=sys.stderr)
        return False

    best_combo = scorecard.get("best_keeper", scorecard.get("winner", {}))

    # Promote to WATCH in both params files
    for p in [PARAMS_PATH, AGG_PARAMS_PATH]:
        _write_watch_flag_to_params(p, watcher_name, best_combo)

    _write_promote_scorecard(watcher_name, details, scorecard)
    _write_discord_ping(watcher_name, details, scorecard)

    print(
        f"[pipeline_promoter] PROMOTED {watcher_name} — "
        f"WF={details['wf_ratio']:.2f} dir={details['directional_score']} "
        f"top5={details['top5_pct']:.0%}",
        file=sys.stderr,
    )
    return True


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Check gates and promote a watcher")
    ap.add_argument("--script", default="shotgun_scalper_stage5")
    ap.add_argument("--watcher", default="shotgun_scalper")
    args = ap.parse_args()
    result = check_and_promote(args.script, args.watcher)
    sys.exit(0 if result else 1)

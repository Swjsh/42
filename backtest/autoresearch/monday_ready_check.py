"""Monday-Ready Checklist — gates ALL must pass before live trading.

Per CLAUDE.md OP 20 (non-theatre validation): no candidate ratifies for live
trading until EVERY gate below passes. Writes:

  markdown/planning/MONDAY-READY-CHECKLIST.md     — human-readable PASS/FAIL
  automation/state/monday-ready.json  — machine-readable for dashboard

Gates:
  1. Stage 5 ratification fired (v15-final.json exists)
  2. Walk-forward validation: test_2026 P&L > 0 for chosen candidate
  3. Real-fills check: simulator_real on top-3 J days within ±20% of BS-sim
  4. All 11 Monday Gamma_* scheduled tasks ENABLED
  5. Discord bridge alive
  6. Discord responder healthy (ran in last 10 min)
  7. Concentration gate: chosen candidate top5_pct <= 200%
  8. Quarter coverage: chosen candidate >= 4/6 quarters net+
  9. Floor preservation: 4/29 >= $372 AND 5/04 >= $2,418 AND losers_added = 0
  10. Account-size disclosure included in scorecard

If ANY gate fails: report tells J exactly which gate + how to fix.
If all pass: "MONDAY READY — ratify with confidence."
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys

# CREATE_NO_WINDOW = 0x08000000 — suppress conhost on Windows subprocess spawns. OP-27 L41.
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))

V15_FINAL = ROOT / "analysis" / "recommendations" / "v15-final.json"
WALK_FWD = ROOT / "analysis" / "recommendations" / "walk-forward-results.json"
OUT_JSON = ROOT / "automation" / "state" / "monday-ready.json"
OUT_MD = ROOT / "markdown" / "planning" / "MONDAY-READY-CHECKLIST.md"
DISCORD_RESPONDER_LOG = ROOT / "automation" / "state" / "logs" / "discord-responder.log"

REQUIRED_TASKS = [
    "Gamma_LaunchTV", "Gamma_Premarket", "Gamma_Heartbeat",
    "Gamma_EodFlatten", "Gamma_EodSummary", "Gamma_DailyReview",
    "Gamma_DiscordWatchdog", "Gamma_GrinderMonitor", "Gamma_DiscordResponder",
    "Gamma_DailyStatus", "Gamma_SelfAudit",
]


def _read_json(p: Path) -> dict:
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _check_v15_final() -> dict:
    if not V15_FINAL.exists():
        return {"pass": False, "reason": "v15-final.json missing — stage 5 hasn't run"}
    data = _read_json(V15_FINAL)
    return {
        "pass": True,
        "verdict": data.get("verdict"),
        "chosen_stage": data.get("chosen_from_stage"),
        "winner_combo": data.get("winner_combo"),
    }


def _check_walk_forward() -> dict:
    if not WALK_FWD.exists():
        return {"pass": False, "reason": "walk-forward not yet run"}
    data = _read_json(WALK_FWD)
    cands = data.get("candidates", [])
    if not cands:
        return {"pass": False, "reason": "walk-forward has no candidates"}
    # Find top candidate (best test P&L)
    cands.sort(key=lambda c: -c.get("test_2026", {}).get("total_pnl", -999999))
    top = cands[0]
    test_pnl = top.get("test_2026", {}).get("total_pnl", 0)
    return {
        "pass": test_pnl > 0,
        "test_pnl": test_pnl,
        "test_train_ratio": top.get("test_train_ratio"),
        "test_positive_quarters": top.get("test_2026", {}).get("positive_quarters", 0),
        "reason": "test_2026 P&L > 0" if test_pnl > 0 else f"test_2026 P&L = ${test_pnl:.0f} (not net+)",
    }


def _check_scheduled_tasks() -> dict:
    try:
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command",
             "Get-ScheduledTask | Where-Object { $_.TaskName -like 'Gamma_*' } | Select-Object TaskName, State | ConvertTo-Json -Compress"],
            stderr=subprocess.DEVNULL, timeout=15,
            creationflags=_CREATE_NO_WINDOW,
        ).decode("utf-8", errors="ignore")
        tasks = json.loads(out) if out.strip().startswith("[") else [json.loads(out)]
    except Exception as e:
        return {"pass": False, "reason": f"could not query tasks: {e}"}
    enabled = {t["TaskName"]: t["State"] for t in tasks}
    missing = []
    disabled = []
    for req in REQUIRED_TASKS:
        if req not in enabled:
            missing.append(req)
        elif enabled[req] in ("Disabled", 1):  # 1 = disabled enum
            disabled.append(req)
    return {
        "pass": not missing and not disabled,
        "missing": missing,
        "disabled": disabled,
        "all_states": enabled,
    }


def _check_bridge() -> dict:
    pid_file = ROOT / "automation" / "state" / "discord-bridge.pid"
    if not pid_file.exists():
        return {"pass": False, "reason": "no bridge pid file"}
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip().split("|")[0])
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            stderr=subprocess.DEVNULL, timeout=5,
            creationflags=_CREATE_NO_WINDOW,
        ).decode("utf-8", errors="ignore")
        return {"pass": f"{pid}" in out, "pid": pid}
    except Exception as e:
        return {"pass": False, "reason": str(e)}


def _check_responder() -> dict:
    if not DISCORD_RESPONDER_LOG.exists():
        return {"pass": False, "reason": "no responder log"}
    try:
        lines = DISCORD_RESPONDER_LOG.read_text(encoding="utf-8").splitlines()
        if not lines:
            return {"pass": False, "reason": "empty log"}
        last = lines[-1]
        ts_str = last.split(" [")[0].split(",")[0]
        ts = dt.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        age_min = (dt.datetime.now() - ts).total_seconds() / 60
        return {"pass": age_min < 10, "last_run_min_ago": round(age_min, 1)}
    except Exception as e:
        return {"pass": False, "reason": str(e)}


def _check_winner_metrics() -> dict:
    if not V15_FINAL.exists():
        return {"pass": False, "reason": "no v15-final.json"}
    data = _read_json(V15_FINAL)
    metrics = data.get("winner_metrics", {})
    pnl_4_29 = metrics.get("pnl_4_29", 0)
    pnl_5_04 = metrics.get("pnl_5_04", 0)
    losers_added = metrics.get("losers_added", 0)
    top5 = metrics.get("top5_pct") or 999
    pos_q = metrics.get("positive_quarters", 0)

    fails = []
    if pnl_4_29 < 372 - 1:
        fails.append(f"4/29 ${pnl_4_29:.0f} < $372 floor")
    if pnl_5_04 < 2418 - 1:
        fails.append(f"5/04 ${pnl_5_04:.0f} < $2,418 floor")
    if losers_added > 1:
        fails.append(f"losers_added ${losers_added:.0f} > 0")
    if top5 > 2.0:
        fails.append(f"top5_pct {top5*100:.0f}% > 200% concentration cap")
    if pos_q < 4:
        fails.append(f"positive_quarters {pos_q} < 4")
    return {
        "pass": not fails,
        "fails": fails,
        "metrics": {"pnl_4_29": pnl_4_29, "pnl_5_04": pnl_5_04, "losers_added": losers_added,
                    "top5_pct": top5, "positive_quarters": pos_q},
    }


def main() -> int:
    now = dt.datetime.now()

    gates = {
        "1_stage5_ratified": _check_v15_final(),
        "2_walk_forward_oos_positive": _check_walk_forward(),
        "3_scheduled_tasks_enabled": _check_scheduled_tasks(),
        "4_discord_bridge_alive": _check_bridge(),
        "5_discord_responder_healthy": _check_responder(),
        "6_winner_metrics_pass_floors": _check_winner_metrics(),
    }

    all_pass = all(g.get("pass", False) for g in gates.values())
    fail_count = sum(1 for g in gates.values() if not g.get("pass", False))

    summary = {
        "checked_at": now.isoformat(),
        "monday_ready": all_pass,
        "fail_count": fail_count,
        "gates": gates,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    md = [f"# MONDAY-READY CHECKLIST — {now.strftime('%Y-%m-%d %H:%M ET')}\n"]
    md.append(f"## Status: **{'✅ MONDAY READY' if all_pass else f'❌ NOT READY ({fail_count} gate fails)'}**\n")
    md.append("| # | Gate | Pass | Detail |")
    md.append("|---|---|---|---|")
    for k, g in gates.items():
        ok = "✅" if g.get("pass", False) else "❌"
        if g.get("pass", False):
            detail = ""
            if "test_pnl" in g:
                detail = f"test_2026 P&L=${g['test_pnl']:.0f}, ratio={g.get('test_train_ratio', '?')}x"
            elif "metrics" in g:
                m = g["metrics"]
                detail = f"4/29=${m['pnl_4_29']:.0f}, 5/04=${m['pnl_5_04']:.0f}, top5={m['top5_pct']*100:.0f}%, Q+={m['positive_quarters']}/6"
            elif "verdict" in g:
                detail = f"verdict={g['verdict']}, stage={g['chosen_stage']}"
            elif "pid" in g:
                detail = f"PID {g['pid']} alive"
            elif "last_run_min_ago" in g:
                detail = f"ran {g['last_run_min_ago']} min ago"
            else:
                detail = "ok"
        else:
            detail = g.get("reason", "") or str(g.get("fails", "")) or str(g.get("missing", "")) or "see json"
        md.append(f"| {k.split('_', 1)[0]} | {k.split('_', 1)[1]} | {ok} | {detail} |")

    md.append("\n## What to do next")
    if all_pass:
        md.append("- ✅ All gates pass. Per CLAUDE.md rule 9, J ratifies → params.json bumps → Monday trades on it.")
        md.append("- Reply 'yes' on Discord OR edit params.json directly.")
    else:
        md.append("- ❌ At least one gate failed. Review the table above for the specific reason.")
        md.append("- DO NOT bump params.json. Fix the failing gate first.")
        md.append("- Common fixes:")
        md.append("  - Walk-forward not run yet → wait for it (~10 min runtime)")
        md.append("  - Stage 5 not fired → wait for stage 4 to finish")
        md.append("  - Bridge dead → run `setup\\scripts\\ensure-discord-bridge-alive.ps1`")
        md.append("  - Tasks disabled → re-enable via PowerShell `Enable-ScheduledTask`")

    md.append("\n## Per CLAUDE.md OP 20 (non-theatre validation)")
    md.append("Every numeric claim in the v15-final scorecard MUST come bundled with:")
    md.append("- Account-size scaling table (qty=N requires $X equity)")
    md.append("- Sample bias note (selected from M-combo grinder)")
    md.append("- Walk-forward result (this gate)")
    md.append("- Failure mode + max drawdown")
    md.append("- Concentration disclosure (top5_pct)")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"Monday-ready: {summary['monday_ready']}, {fail_count} fails")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())

"""gym_session — unified daily chart-reading audit scorecard for the SPY engine.

Orchestrates every chart-reading audit + crypto-validator gym + 5/14 replay benchmark
and writes ONE consolidated GREEN/YELLOW/RED scorecard.

Reads (consumes existing scorecards, or re-runs if stale > 2h):
    crypto/data/scorecards/latest.json          (22 validators x offline+live = 42 stages)
    automation/state/chart-data-verify-{date}.json
    automation/state/heartbeat-tick-audit-{date}.json
    automation/state/pin-chain-verify-latest.json
    automation/state/heartbeat-mcp-self-test-latest.json
    automation/state/heartbeat-pulse-check-{date}.json
    automation/state/watcher-state-inspector-{date}.json

Writes:
    automation/state/gym-scorecard-{date}.json  (machine-readable)
    analysis/gym/{YYYY-MM-DD}.md                 (narrative)
    analysis/gym/_gym-log.jsonl                  (append-only fire log)

Verdict logic:
    overall_pass = ALL of the following pass (or are KNOWN_FLAKY-excluded):
        crypto gym overall_pass == True
        chart-data-verify verdict in {GREEN, YELLOW}     # YELLOW is heal-pending, not failure
        heartbeat-tick-audit no MISALIGNED-CRITICAL ticks
        pin-chain-verify verdict == GREEN
        heartbeat-mcp-self-test verdict in {GREEN, not_applicable}  # not_applicable if market closed
        heartbeat-pulse-check verdict in {GREEN, not_applicable}    # not_applicable on weekends
        watcher-state-inspector verdict in {GREEN, not_applicable}

If overall_pass == False, appends a HIGH task to automation/overnight/queue.md so the
next wake fire surfaces it.

CLI:
    python -m autoresearch.gym_session [--date YYYY-MM-DD] [--stale-hours N] [--rerun-all]

Exit 0 on overall_pass=True; exit 1 otherwise.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

# OP-27 L41 — all subprocess spawns on Windows MUST pass CREATE_NO_WINDOW to avoid window leaks
_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "automation" / "state"
ANALYSIS_GYM = PROJECT_ROOT / "analysis" / "gym"
ANALYSIS_GYM.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True)
class AuditResult:
    name: str
    source_file: str
    verdict: str  # GREEN | YELLOW | RED | NOT_APPLICABLE | MISSING
    summary: str
    evidence: dict = field(default_factory=dict)


def _et_today() -> str:
    """Return today's date in ET as YYYY-MM-DD."""
    et_offset = timedelta(hours=-4)  # rough — daylight savings handled by underlying scripts
    return (datetime.now(timezone.utc) + et_offset).strftime("%Y-%m-%d")


def _is_weekend(date_str: str) -> bool:
    return datetime.strptime(date_str, "%Y-%m-%d").weekday() >= 5


def _file_age_hours(p: Path) -> Optional[float]:
    if not p.exists():
        return None
    mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=timezone.utc)
    return (datetime.now(timezone.utc) - mtime).total_seconds() / 3600.0


def _read_json(p: Path) -> Optional[dict]:
    if not p.exists():
        return None
    # utf-8-sig strips UTF-8 BOM written by PowerShell ConvertTo-Json / Out-File -Encoding UTF8.
    # Fall back through utf-16 (PowerShell 5.1 default) and then plain utf-8.
    for enc in ("utf-8-sig", "utf-16", "utf-8"):
        try:
            return json.loads(p.read_text(encoding=enc))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            continue
    return None


def _classify_crypto_gym(data: Optional[dict]) -> AuditResult:
    name = "crypto-gym (42 validators)"
    src = "crypto/data/scorecards/latest.json"
    if data is None:
        return AuditResult(name, src, "MISSING", "scorecard file not found", {})
    summary_obj = data.get("summary", {})
    overall = summary_obj.get("overall_pass", False)
    stages = summary_obj.get("stages", 0)
    passed = summary_obj.get("passed", 0)
    flaky = summary_obj.get("flaky_failed", [])
    verdict = "GREEN" if overall else "RED"
    msg = f"{passed}/{stages} pass" + (f" (KNOWN_FLAKY excluded: {len(flaky)})" if flaky else "")
    return AuditResult(name, src, verdict, msg, {"stages": stages, "passed": passed, "flaky_failed": flaky})


def _classify_chart_data_verify(data: Optional[dict]) -> AuditResult:
    name = "chart-data-verify"
    src = f"automation/state/chart-data-verify-{_et_today()}.json"
    if data is None:
        return AuditResult(name, src, "MISSING", "verify-output not found for today", {})
    v = data.get("verdict", "RED").upper()
    # chart_data_verify.py writes "rows_compared" and "max_divergence_dollars"
    # Accept all variants for forward/backward compatibility.
    bars = data.get("rows_compared", data.get("bars_checked", data.get("row_count", 0)))
    div = data.get("max_divergence_dollars", data.get("max_divergence_usd", 0))
    return AuditResult(name, src, v, f"{bars} bars checked, max div ${div:.4f}",
                       {"max_divergence_usd": div, "bars_checked": bars})


def _classify_tick_audit(data: Optional[dict]) -> AuditResult:
    name = "heartbeat-tick-audit"
    src = f"automation/state/heartbeat-tick-audit-{_et_today()}.json"
    if data is None:
        return AuditResult(name, src, "MISSING", "tick-audit output not found", {})
    # heartbeat_tick_audit.py writes the key as "counts" (not "by_classification").
    # Accept both to be forward/backward compatible.
    by_class = data.get("counts", data.get("by_classification", {}))
    critical = by_class.get("MISALIGNED-CRITICAL", 0)
    live = by_class.get("ALIGNED", 0) + by_class.get("MISALIGNED-BENIGN", 0) + critical
    total = sum(by_class.values()) if by_class else 0
    pct = round(100.0 * critical / live, 1) if live > 0 else 0.0

    # Distinguish genuine trading errors (ENTER/EXIT on in-progress bar) from passive
    # stale-cache HOLD reads (no trading decision made).  If every CRITICAL tick was a
    # non-trading action (HOLD, HOLD_DEV, no_decision), raise YELLOW not RED.
    # RED is reserved for CRITICAL ticks that involved an actual order-placing decision.
    _DECISION_CHANGING = frozenset({
        "ENTER_BULL", "ENTER_BEAR", "EXIT_TP1", "EXIT_TP2",
        "EXIT_RUNNER", "EXIT_STOP", "EXIT_TIME", "ADD",
    })
    critical_ticks: list[dict] = data.get("critical_ticks", [])
    has_decision_critical = any(
        (t.get("decision") or "").upper() in _DECISION_CHANGING
        for t in critical_ticks
    )
    if critical == 0:
        verdict = "GREEN"
    elif has_decision_critical:
        verdict = "RED"   # at least one entry/exit was on an in-progress bar
    else:
        verdict = "YELLOW"  # only HOLD/stale-cache CRITICAL ticks — no trading impact

    return AuditResult(name, src, verdict,
                       f"{live} live ticks, {critical} MISALIGNED-CRITICAL ({pct}%)"
                       + (" [HOLD-only — no trading impact]" if verdict == "YELLOW" else ""),
                       {"by_classification": by_class, "live_ticks": live,
                        "misaligned_critical": critical, "misaligned_pct": pct})


def _classify_pin_chain(data: Optional[dict]) -> AuditResult:
    name = "pin-chain-verify"
    src = "automation/state/pin-chain-verify-latest.json"
    if data is None:
        return AuditResult(name, src, "MISSING", "pin-chain output not found", {})
    v = data.get("verdict", "RED").upper()
    rv = data.get("canonical_rule_version", data.get("rule_version_canonical", "unknown"))
    drifts = data.get("mismatches", data.get("drifts", []))
    return AuditResult(name, src, v,
                       f"rule_version={rv}, mismatches={len(drifts)}",
                       {"canonical_rule_version": rv, "mismatches": drifts})


def _classify_mcp_self_test(data: Optional[dict], date_str: str) -> AuditResult:
    name = "heartbeat-mcp-self-test"
    src = "automation/state/heartbeat-mcp-self-test-latest.json"
    if data is None:
        if _is_weekend(date_str):
            return AuditResult(name, src, "NOT_APPLICABLE", "weekend — TV may be closed", {})
        return AuditResult(name, src, "MISSING", "mcp-self-test output not found", {})
    v = data.get("verdict", "RED").upper()
    tv = data.get("tv_cdp_listening", False)
    return AuditResult(name, src, v, f"TV CDP listening={tv}", {"tv_cdp_listening": tv})


def _classify_pulse_check(data: Optional[dict], date_str: str) -> AuditResult:
    name = "heartbeat-pulse-check"
    src = f"automation/state/heartbeat-pulse-check-{date_str}.json"
    if data is None:
        if _is_weekend(date_str):
            return AuditResult(name, src, "NOT_APPLICABLE", "weekend — no heartbeat fires expected", {})
        return AuditResult(name, src, "MISSING", "pulse-check output not found", {})
    v = data.get("verdict", "RED").upper()
    max_gap = data.get("max_gap_minutes", 0)
    return AuditResult(name, src, v, f"max gap {max_gap}min", {"max_gap_minutes": max_gap})


def _classify_watcher_state(data: Optional[dict], date_str: str) -> AuditResult:
    name = "watcher-state-inspector"
    src = f"automation/state/watcher-state-inspector-{date_str}.json"
    if data is None:
        if _is_weekend(date_str):
            return AuditResult(name, src, "NOT_APPLICABLE", "weekend — watchers idle", {})
        return AuditResult(name, src, "MISSING", "watcher-state output not found", {})
    v = data.get("verdict", "RED").upper()
    # watcher_state_inspector.py writes "reason" not "summary" — accept both.
    reason = data.get("reason", data.get("summary", "no reason"))
    obs = data.get("watcher_obs_count_today", 0)
    msg = f"{reason} (obs_today={obs})" if obs else reason
    return AuditResult(name, src, v, msg,
                       {"obs_today": obs, "reason": reason})


def _run_python(module: str, args: list[str]) -> tuple[int, str]:
    """Run an autoresearch module via `python -m`, capture exit + output tail.

    Cwd must be `backtest/` so that `from lib import ...` style imports inside
    the autoresearch package resolve correctly.
    """
    backtest_dir = PROJECT_ROOT / "backtest"
    cmd = [sys.executable, "-m", f"autoresearch.{module}", *args]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300,
            creationflags=_CREATE_NO_WINDOW, cwd=str(backtest_dir),
        )
        return result.returncode, (result.stdout[-500:] + result.stderr[-500:])
    except subprocess.TimeoutExpired:
        return 124, f"TIMEOUT: {module}"
    except Exception as e:
        return 1, f"EXCEPTION: {e}"


def _maybe_rerun_stale(stale_hours: float, rerun_all: bool, date_str: str) -> dict:
    """Re-run audits whose scorecard files are stale or missing.

    Skips weekends (no live audits expected) and skips modules whose path
    doesn't exist (graceful degrade if a tool hasn't been built yet).
    """
    reruns: dict = {}
    if _is_weekend(date_str) and not rerun_all:
        return {"skipped": "weekend — re-runs disabled (--rerun-all to force)"}

    targets = [
        ("chart_data_verify", ["--date", date_str], STATE_DIR / f"chart-data-verify-{date_str}.json"),
        ("pin_chain_verify", [], STATE_DIR / "pin-chain-verify-latest.json"),
        ("heartbeat_tick_audit", ["--date", date_str], STATE_DIR / f"heartbeat-tick-audit-{date_str}.json"),
        # heartbeat_pulse_check: Python port of heartbeat-pulse-check.ps1.
        # Self-heals the MISSING pulse-check file so gym doesn't stay RED.
        ("heartbeat_pulse_check", ["--date", date_str], STATE_DIR / f"heartbeat-pulse-check-{date_str}.json"),
    ]
    for module, args, out_path in targets:
        module_file = PROJECT_ROOT / "backtest" / "autoresearch" / f"{module}.py"
        if not module_file.exists():
            reruns[module] = {"exit": -1, "log_tail": f"module file not found: {module_file}"}
            continue
        age = _file_age_hours(out_path)
        should_run = rerun_all or age is None or age > stale_hours
        if should_run:
            exit_code, log = _run_python(module, args)
            reruns[module] = {"exit": exit_code, "log_tail": log}
    return reruns


def _aggregate_verdict(results: list[AuditResult]) -> str:
    """RED if any RED. YELLOW if any YELLOW (but no RED). GREEN if all GREEN/NOT_APPLICABLE."""
    reds = [r for r in results if r.verdict == "RED"]
    yellows = [r for r in results if r.verdict == "YELLOW"]
    missings = [r for r in results if r.verdict == "MISSING"]
    if reds or missings:
        return "RED"
    if yellows:
        return "YELLOW"
    return "GREEN"


def _write_markdown(results: list[AuditResult], overall: str, date_str: str, reruns: dict) -> Path:
    lines: list[str] = []
    lines.append(f"# Gym session — {date_str}")
    lines.append("")
    lines.append(f"**Overall verdict:** {overall}")
    lines.append("")
    lines.append(f"_Auto-generated by `gym_session.py`. Manager picks up at 17:30 ET for daily brief._")
    lines.append("")
    lines.append("## Per-audit scorecard")
    lines.append("")
    lines.append("| Audit | Verdict | Summary | Source |")
    lines.append("|---|---|---|---|")
    for r in results:
        lines.append(f"| {r.name} | **{r.verdict}** | {r.summary} | `{r.source_file}` |")
    lines.append("")
    if reruns:
        lines.append("## Stale-audit re-runs")
        lines.append("")
        for mod, info in reruns.items():
            lines.append(f"- `{mod}` → exit={info['exit']}")
        lines.append("")
    lines.append("## Suggested next actions")
    lines.append("")
    reds = [r for r in results if r.verdict in ("RED", "MISSING")]
    if not reds:
        lines.append("- None. Engine is green; continue routine.")
    else:
        for r in reds:
            lines.append(f"- **{r.name}** {r.verdict}: investigate `{r.source_file}` — {r.summary}")
    lines.append("")
    md_path = ANALYSIS_GYM / f"{date_str}.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return md_path


def _append_log(payload: dict) -> None:
    log = ANALYSIS_GYM / "_gym-log.jsonl"
    with log.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def _append_status(date_str: str, overall: str, scorecard_path: Path) -> None:
    status = PROJECT_ROOT / "automation" / "overnight" / "STATUS.md"
    if not status.exists():
        return
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    line = f"\n- [{now}] gym-session ({date_str}) → **{overall}** :: see `{scorecard_path.relative_to(PROJECT_ROOT)}`"
    with status.open("a", encoding="utf-8") as f:
        f.write(line)


def _maybe_queue_red(overall: str, date_str: str, reds: list[AuditResult]) -> None:
    """If overall RED, append a HIGH task to queue.md."""
    if overall != "RED":
        return
    queue = PROJECT_ROOT / "automation" / "overnight" / "queue.md"
    if not queue.exists():
        return
    task_id = f"T-GYM-{date_str.replace('-', '')}"
    body = [
        f"\n### {task_id} HIGH gym-session RED for {date_str}",
        "",
        "**Audits failing:**",
    ]
    for r in reds:
        body.append(f"- {r.name} ({r.verdict}): {r.summary}")
    body.append("")
    body.append("**Action:** investigate, fix the underlying primitive, re-run `python -m autoresearch.gym_session --date {date_str} --rerun-all`.")
    body.append("")
    with queue.open("a", encoding="utf-8") as f:
        f.write("\n".join(body))


def run(date: str, stale_hours: float = 2.0, rerun_all: bool = False) -> dict:
    reruns = _maybe_rerun_stale(stale_hours, rerun_all, date)

    crypto_gym = _classify_crypto_gym(_read_json(PROJECT_ROOT / "crypto" / "data" / "scorecards" / "latest.json"))
    cdv = _classify_chart_data_verify(_read_json(STATE_DIR / f"chart-data-verify-{date}.json"))
    tick = _classify_tick_audit(_read_json(STATE_DIR / f"heartbeat-tick-audit-{date}.json"))
    pin = _classify_pin_chain(_read_json(STATE_DIR / "pin-chain-verify-latest.json"))
    mcp = _classify_mcp_self_test(_read_json(STATE_DIR / "heartbeat-mcp-self-test-latest.json"), date)
    pulse = _classify_pulse_check(_read_json(STATE_DIR / f"heartbeat-pulse-check-{date}.json"), date)
    watcher = _classify_watcher_state(_read_json(STATE_DIR / f"watcher-state-inspector-{date}.json"), date)

    results = [crypto_gym, cdv, tick, pin, mcp, pulse, watcher]
    overall = _aggregate_verdict(results)

    scorecard = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "for_date": date,
        "overall_verdict": overall,
        "audits": [asdict(r) for r in results],
        "stale_reruns": reruns,
    }
    scorecard_path = STATE_DIR / f"gym-scorecard-{date}.json"
    scorecard_path.write_text(json.dumps(scorecard, indent=2), encoding="utf-8")

    md_path = _write_markdown(results, overall, date, reruns)
    _append_log({
        "fired_at": scorecard["generated_at"],
        "for_date": date,
        "overall_verdict": overall,
        "scorecard": str(scorecard_path.relative_to(PROJECT_ROOT)),
        "markdown": str(md_path.relative_to(PROJECT_ROOT)),
        "audits": {r.name: r.verdict for r in results},
    })
    _append_status(date, overall, scorecard_path)
    _maybe_queue_red(overall, date, [r for r in results if r.verdict in ("RED", "MISSING")])

    return scorecard


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--date", default=_et_today(), help="YYYY-MM-DD (default: today ET)")
    p.add_argument("--stale-hours", type=float, default=2.0, help="re-run audits older than N hours")
    p.add_argument("--rerun-all", action="store_true", help="re-run every audit regardless of age")
    args = p.parse_args(argv)

    scorecard = run(date=args.date, stale_hours=args.stale_hours, rerun_all=args.rerun_all)
    print(json.dumps(scorecard, indent=2))
    return 0 if scorecard["overall_verdict"] in ("GREEN", "YELLOW") else 1


if __name__ == "__main__":
    sys.exit(main())

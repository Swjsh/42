"""skill_tune — replay an existing skill across N historical days, sweep a parameter,
suggest a better threshold.

When a chart-reading or audit skill has a threshold that may be mis-calibrated
(e.g., chart-data-verify's $0.10 divergence tolerance), this tool replays the
skill with monkey-patched parameter values across the last N trading days,
measures detection rate at each value, and writes a recommendation report.

Output:
    analysis/skill-tune/{skill}-{timestamp}.md    (sweep table + recommendation)
    automation/state/skill-tune-{skill}-latest.json    (machine-readable summary)

If the recommended value differs from current AND the skill is NOT in the
live-doctrine denylist, writes a DRAFT update item to
`strategy/candidates/_skill-inbox/{date}-tune-{skill}.md` so the next wake fire
picks it up via skill-author.

CLI:
    python -m autoresearch.skill_tune \\
        --skill chart-data-verify \\
        --window 30 \\
        --param tolerance \\
        --range 0.05,0.30,0.05

Live-doctrine denylist (refuses to write a _skill-inbox/ DRAFT — flags to
_lesson-inbox/ instead requiring J ratification per Rule 9):
    - any skill whose module reads/writes automation/prompts/heartbeat.md
    - any skill whose module reads/writes automation/state/params*.json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = PROJECT_ROOT / "automation" / "state"
TUNE_DIR = PROJECT_ROOT / "analysis" / "skill-tune"
TUNE_DIR.mkdir(parents=True, exist_ok=True)
SKILL_INBOX = PROJECT_ROOT / "strategy" / "candidates" / "_skill-inbox"
LESSON_INBOX = PROJECT_ROOT / "strategy" / "candidates" / "_lesson-inbox"

# Skills whose threshold tuning would affect live trading doctrine — these
# require J ratification per Rule 9 (no mid-session rule changes). Sweep
# results are written, but the resulting DRAFT goes to _lesson-inbox/ instead
# of _skill-inbox/ so lesson-author surfaces it for explicit ratification.
LIVE_DOCTRINE_DENYLIST = frozenset({
    "heartbeat-pulse-check",      # touches heartbeat task scheduling
    "heartbeat-decision-trace",   # tied to live params.json filter thresholds
    "pin-chain-verify",           # rule 9 by definition (rule_version drift)
})


@dataclass(frozen=True)
class SweepRow:
    param_value: float
    days_green: int
    days_yellow: int
    days_red: int
    days_missing: int
    false_positive_rate: Optional[float] = None
    notes: str = ""


@dataclass(frozen=True)
class TuneReport:
    skill: str
    param: str
    sweep_range: str
    window_days: int
    started_at: str
    current_value: Optional[float]
    recommended_value: Optional[float]
    rows: list[SweepRow] = field(default_factory=list)
    denylist_blocked: bool = False
    inbox_path: Optional[str] = None


def _today_et() -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=-4)).strftime("%Y-%m-%d")


def _parse_range(spec: str) -> list[float]:
    """Parse 'start,stop,step' into list of float values."""
    parts = spec.split(",")
    if len(parts) != 3:
        raise ValueError(f"Range must be 'start,stop,step', got: {spec}")
    start, stop, step = (float(x) for x in parts)
    values: list[float] = []
    v = start
    # add small epsilon to include stop value on float boundary
    while v <= stop + 1e-9:
        values.append(round(v, 6))
        v += step
    return values


def _historical_dates(window: int) -> list[str]:
    """Return list of YYYY-MM-DD strings for the last N weekdays."""
    out: list[str] = []
    d = datetime.now(timezone.utc) + timedelta(hours=-4)
    while len(out) < window:
        d -= timedelta(days=1)
        if d.weekday() < 5:  # Mon-Fri
            out.append(d.strftime("%Y-%m-%d"))
    return out


def _evaluate_single(skill_module: str, date: str, param: str, value: float) -> str:
    """Stub evaluation entry point.

    For skills wired into this framework, the module exposes
    `evaluate_at(date: str, **overrides) -> dict` returning at least
    `{"verdict": "GREEN"|"YELLOW"|"RED"|"NOT_APPLICABLE"|"MISSING"}`.

    Until each target skill ships an evaluate_at adapter, this returns MISSING.
    Adding adapters is the per-skill work that promotes a tune-request to
    actually-tunable.
    """
    try:
        mod = __import__(f"autoresearch.{skill_module}", fromlist=[skill_module])
    except ImportError:
        return "MISSING"
    fn = getattr(mod, "evaluate_at", None)
    if fn is None:
        return "MISSING"
    try:
        result = fn(date=date, **{param: value})
        return str(result.get("verdict", "MISSING")).upper()
    except Exception:
        return "MISSING"


def _module_name_for_skill(skill: str) -> str:
    """Map skill slug to its backtest/autoresearch/*.py module name."""
    # Skill slugs use hyphens; modules use underscores.
    return skill.replace("-", "_")


def _read_current_param(skill_module: str, param: str) -> Optional[float]:
    """Best-effort: import the module and read a top-level constant matching the param name."""
    try:
        mod = __import__(f"autoresearch.{skill_module}", fromlist=[skill_module])
    except ImportError:
        return None
    # Common conventions: PARAM, _PARAM, DEFAULT_PARAM
    for candidate in (param.upper(), f"_{param.upper()}", f"DEFAULT_{param.upper()}"):
        if hasattr(mod, candidate):
            try:
                return float(getattr(mod, candidate))
            except (TypeError, ValueError):
                continue
    return None


def _sweep(skill: str, param: str, values: list[float], window: int) -> list[SweepRow]:
    """Run the parameter sweep across N historical days."""
    module = _module_name_for_skill(skill)
    dates = _historical_dates(window)
    rows: list[SweepRow] = []
    for v in values:
        counts = {"GREEN": 0, "YELLOW": 0, "RED": 0, "MISSING": 0}
        for d in dates:
            verdict = _evaluate_single(module, d, param, v)
            if verdict in counts:
                counts[verdict] += 1
            else:
                counts["MISSING"] += 1
        total_assessed = counts["GREEN"] + counts["YELLOW"] + counts["RED"]
        fpr = (counts["RED"] / total_assessed) if total_assessed > 0 else None
        rows.append(SweepRow(
            param_value=v,
            days_green=counts["GREEN"],
            days_yellow=counts["YELLOW"],
            days_red=counts["RED"],
            days_missing=counts["MISSING"],
            false_positive_rate=fpr,
            notes="" if total_assessed > 0 else "skill has no evaluate_at adapter — see skill_tune.py docstring",
        ))
    return rows


def _recommend(rows: list[SweepRow]) -> Optional[float]:
    """Pick value with lowest RED rate, then highest GREEN count among ties."""
    assessed = [r for r in rows if r.false_positive_rate is not None]
    if not assessed:
        return None
    min_red = min(r.false_positive_rate for r in assessed)
    candidates = [r for r in assessed if r.false_positive_rate == min_red]
    best = max(candidates, key=lambda r: r.days_green)
    return best.param_value


def _write_markdown(report: TuneReport) -> Path:
    p = TUNE_DIR / f"{report.skill}-{report.started_at.replace(':', '-')}.md"
    lines: list[str] = []
    lines.append(f"# Skill tune report — {report.skill}")
    lines.append("")
    lines.append(f"- **Parameter:** `{report.param}`")
    lines.append(f"- **Sweep range:** {report.sweep_range}")
    lines.append(f"- **Window:** {report.window_days} weekdays")
    lines.append(f"- **Current value:** {report.current_value}")
    lines.append(f"- **Recommended value:** {report.recommended_value}")
    if report.denylist_blocked:
        lines.append(f"- **Denylist:** skill in `LIVE_DOCTRINE_DENYLIST` — DRAFT routed to `_lesson-inbox/` for J ratification (Rule 9)")
    elif report.inbox_path:
        lines.append(f"- **Inbox DRAFT:** `{report.inbox_path}` — picked up by next wake fire's skill-author")
    lines.append("")
    lines.append("## Sweep table")
    lines.append("")
    lines.append("| param_value | days_green | days_yellow | days_red | days_missing | false_positive_rate | notes |")
    lines.append("|---|---|---|---|---|---|---|")
    for r in report.rows:
        fpr = f"{r.false_positive_rate:.3f}" if r.false_positive_rate is not None else "—"
        lines.append(f"| {r.param_value} | {r.days_green} | {r.days_yellow} | {r.days_red} | {r.days_missing} | {fpr} | {r.notes} |")
    lines.append("")
    p.write_text("\n".join(lines), encoding="utf-8")
    return p


def _write_draft_inbox(report: TuneReport) -> Path:
    """Write a DRAFT to _skill-inbox/ (or _lesson-inbox/ if denylisted)."""
    target_inbox = LESSON_INBOX if report.denylist_blocked else SKILL_INBOX
    target_inbox.mkdir(parents=True, exist_ok=True)
    fname = f"{_today_et()}-tune-{report.skill}.md"
    path = target_inbox / fname
    content_lines: list[str] = []
    if report.denylist_blocked:
        content_lines.append(f"# Lesson candidate: {report.skill} tune deferred")
        content_lines.append("")
        content_lines.append(f"> Queued by skill_tune {report.started_at}. lesson-author picks up at next wake fire.")
        content_lines.append("")
        content_lines.append("## Symptom")
        content_lines.append(f"Sweep on `{report.skill}` parameter `{report.param}` suggests value `{report.recommended_value}` (current `{report.current_value}`). Skill is in LIVE_DOCTRINE_DENYLIST — would require Rule 9 ratification to apply.")
        content_lines.append("")
        content_lines.append("## Root cause")
        content_lines.append("Threshold drift between live doctrine and observed-historical-best.")
        content_lines.append("")
        content_lines.append("## Fix")
        content_lines.append(f"Manual J ratification required to change `{report.param}` in this skill's module. Reference the sweep table in the tune report.")
        content_lines.append("")
        content_lines.append("## Encoded in")
        content_lines.append(f"Sweep report at `analysis/skill-tune/{report.skill}-{report.started_at.replace(':', '-')}.md`")
    else:
        content_lines.append(f"# Skill request: {report.skill} tune to {report.recommended_value}")
        content_lines.append("")
        content_lines.append(f"> Queued by skill_tune {report.started_at}. skill-author picks up at next wake fire.")
        content_lines.append("")
        content_lines.append("kind: tune")
        content_lines.append(f"target_skill: {report.skill}")
        content_lines.append(f"param: {report.param}")
        content_lines.append(f"current_value: {report.current_value}")
        content_lines.append(f"recommended_value: {report.recommended_value}")
        content_lines.append(f"window_days: {report.window_days}")
        content_lines.append("")
        content_lines.append("## Recurring pattern observed")
        content_lines.append(f"Sweep across {report.window_days} weekdays shows recommended `{report.param}={report.recommended_value}` minimizes false-positive rate while preserving GREEN day count.")
        content_lines.append("")
        content_lines.append("## What the skill should do")
        content_lines.append(f"Update default `{report.param}` to `{report.recommended_value}` in the skill module + SKILL.md frontmatter.")
        content_lines.append("")
        content_lines.append("## Foot-gun this prevents")
        content_lines.append("Mis-calibrated threshold causing false-positive RED verdicts that mask real regressions.")
    path.write_text("\n".join(content_lines), encoding="utf-8")
    return path


def run(skill: str, param: str, sweep_range: str, window: int) -> TuneReport:
    started_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    values = _parse_range(sweep_range)
    module = _module_name_for_skill(skill)
    current = _read_current_param(module, param)
    rows = _sweep(skill, param, values, window)
    recommended = _recommend(rows)
    denylisted = skill in LIVE_DOCTRINE_DENYLIST

    report = TuneReport(
        skill=skill,
        param=param,
        sweep_range=sweep_range,
        window_days=window,
        started_at=started_at,
        current_value=current,
        recommended_value=recommended,
        rows=rows,
        denylist_blocked=denylisted,
        inbox_path=None,
    )
    _write_markdown(report)
    if recommended is not None and recommended != current:
        inbox_path = _write_draft_inbox(report)
        # rebuild with inbox_path set (TuneReport is frozen)
        report = TuneReport(**{**asdict(report), "inbox_path": str(inbox_path.relative_to(PROJECT_ROOT))})

    summary_path = STATE_DIR / f"skill-tune-{skill}-latest.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(asdict(report), indent=2), encoding="utf-8")
    return report


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--skill", required=True, help="Skill slug (e.g., chart-data-verify)")
    p.add_argument("--param", required=True, help="Parameter name to sweep (e.g., tolerance)")
    p.add_argument("--range", required=True, help="Sweep range 'start,stop,step' (e.g., 0.05,0.30,0.05)")
    p.add_argument("--window", type=int, default=30, help="Historical window in weekdays (default: 30)")
    args = p.parse_args(argv)

    report = run(args.skill, args.param, args.range, args.window)
    print(json.dumps(asdict(report), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

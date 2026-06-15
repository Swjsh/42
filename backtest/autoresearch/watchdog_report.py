"""Smart-watchdog reporter — reads per-mode history.jsonl + state.json, detects
stuck patterns, writes a human-readable report.

Usage:
    python -m autoresearch.watchdog_report           # write report to default path
    python -m autoresearch.watchdog_report --check   # exit 0 if healthy, 2 if stuck

Stuck detection rules:
    1. Last batch had 0 KEEPs across all modes -> "stuck" (likely gate config issue).
    2. Same mode has 0 KEEPs in 3+ consecutive batches -> "mode stuck".
    3. Validate-side sharpe deltas are consistently positive but rejected by
       hard gates -> "gates too strict for current baseline".
    4. Single param has been proposed >= N times across batches with 0 KEEPs ->
       "parameter dead-end" — proposer should be biased away.

Outputs:
    backtest/autoresearch/_state/watchdog_report.md  (human-readable)
    backtest/autoresearch/_state/watchdog_report.json (machine-readable)
    Stable so Claude can read it on each session start.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Allow `python -m autoresearch.watchdog_report` from backtest/ root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from autoresearch import config

logger = logging.getLogger(__name__)
STATE_DIR = Path(__file__).resolve().parent / "_state"
REPORT_MD = STATE_DIR / "watchdog_report.md"
REPORT_JSON = STATE_DIR / "watchdog_report.json"

# Stuck-detection thresholds
BATCH_SIZE_HEURISTIC = 10   # used for "consecutive batches" calc
STUCK_BATCHES_THRESHOLD = 3
PARAM_DEAD_END_THRESHOLD = 4
HEALTHY_KEEPS_PER_BATCH = 1


@dataclass
class ModeReport:
    mode: str
    state_exists: bool
    iterations: int = 0
    keeps: int = 0
    reverts: int = 0
    keep_rate: float = 0.0
    train_baseline: dict = field(default_factory=dict)
    validate_baseline: dict = field(default_factory=dict)
    last_n_keeps: int = 0           # KEEPs in most recent ~10 iterations
    last_n_reverts: int = 0
    consecutive_zero_keep_batches: int = 0
    top_keeps: list[dict] = field(default_factory=list)
    notable_rejections: list[dict] = field(default_factory=list)
    dead_end_params: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    starting_params: dict = field(default_factory=dict)
    final_params: dict = field(default_factory=dict)
    changed_params: dict = field(default_factory=dict)


def _read_history(mode: str) -> list[dict]:
    f = STATE_DIR / mode / "history.jsonl"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _read_state(mode: str) -> dict | None:
    f = STATE_DIR / mode / "state.json"
    if not f.exists():
        return None
    return json.loads(f.read_text(encoding="utf-8"))


def _analyse_mode(mode: str) -> ModeReport:
    state = _read_state(mode)
    history = _read_history(mode)
    rep = ModeReport(mode=mode, state_exists=state is not None)
    if state is None:
        rep.issues.append("state.json missing")
        return rep

    rep.iterations = state.get("iteration", 0)
    rep.keeps = state.get("modifications_kept", 0)
    rep.reverts = state.get("modifications_reverted", 0)
    rep.keep_rate = (rep.keeps / rep.iterations) if rep.iterations else 0.0
    rep.train_baseline = state.get("baseline_metrics", {})
    rep.validate_baseline = state.get("validate_baseline_metrics", {})
    rep.final_params = state.get("current_params", {})

    # Compare final params to mode's starting params.
    if mode in config.MODES:
        rep.starting_params = config.MODES[mode]
        for k, v in rep.final_params.items():
            start_v = rep.starting_params.get(k)
            if start_v != v:
                rep.changed_params[k] = {"from": start_v, "to": v}

    # Last "batch" KEEPs/REVERTs (most recent 10 iterations)
    recent = history[-BATCH_SIZE_HEURISTIC:]
    rep.last_n_keeps = sum(1 for h in recent if h.get("decision", {}).get("keep"))
    rep.last_n_reverts = len(recent) - rep.last_n_keeps

    # Top KEEPs (by validate sharpe delta)
    keeps = [h for h in history if h.get("decision", {}).get("keep")]
    keeps_sorted = sorted(
        keeps,
        key=lambda h: (h.get("decision", {}).get("delta_sharpe", 0), h.get("decision", {}).get("delta_pnl", 0)),
        reverse=True,
    )
    rep.top_keeps = [
        {
            "iter": h["iteration"],
            "param": h["proposal"]["param"],
            "old": h["proposal"]["old_value"],
            "new": h["proposal"]["new_value"],
            "delta_sharpe": h["decision"]["delta_sharpe"],
            "delta_pnl": h["decision"]["delta_pnl"],
            "val_sharpe": h["validate_metrics"]["sharpe_daily"],
            "val_pnl": h["validate_metrics"]["total_pnl"],
            "val_wr": h["validate_metrics"]["win_rate"],
        }
        for h in keeps_sorted[:5]
    ]

    # Notable rejections — REVERTs where validate metrics looked great
    rejections = [
        h for h in history
        if not h.get("decision", {}).get("keep")
        and h.get("validate_metrics", {}).get("sharpe_daily", 0) > 1.0
        and h.get("validate_metrics", {}).get("total_pnl", 0) > 200
    ]
    rejections_sorted = sorted(
        rejections,
        key=lambda h: h["validate_metrics"]["total_pnl"],
        reverse=True,
    )
    rep.notable_rejections = [
        {
            "iter": h["iteration"],
            "param": h["proposal"]["param"],
            "new": h["proposal"]["new_value"],
            "val_pnl": h["validate_metrics"]["total_pnl"],
            "val_sharpe": h["validate_metrics"]["sharpe_daily"],
            "val_wr": h["validate_metrics"]["win_rate"],
            "rejected_because": h["decision"]["reason"],
        }
        for h in rejections_sorted[:3]
    ]

    # Dead-end params: tried >= N times across history with 0 KEEPs
    param_attempts: dict[str, int] = {}
    param_keeps: dict[str, int] = {}
    for h in history:
        p = h.get("proposal", {}).get("param", "")
        # Multi-knob proposals join with "+"; track each.
        for sub in p.split("+"):
            param_attempts[sub] = param_attempts.get(sub, 0) + 1
            if h.get("decision", {}).get("keep"):
                param_keeps[sub] = param_keeps.get(sub, 0) + 1
    for p, n in param_attempts.items():
        if n >= PARAM_DEAD_END_THRESHOLD and param_keeps.get(p, 0) == 0:
            rep.dead_end_params.append(p)

    # Stuck detection
    if rep.iterations >= BATCH_SIZE_HEURISTIC and rep.last_n_keeps == 0:
        rep.issues.append(
            f"0 KEEPs in last {len(recent)} iterations — possible gate or search-space issue"
        )
    if rep.keeps == 0 and rep.iterations >= STUCK_BATCHES_THRESHOLD * BATCH_SIZE_HEURISTIC:
        rep.issues.append(
            f"0 KEEPs across all {rep.iterations} iterations — STUCK; review hard gates"
        )
    if len(rep.notable_rejections) >= 2:
        rep.issues.append(
            f"{len(rep.notable_rejections)} REVERTs had val sharpe > 1.0 and pnl > $200 — "
            f"hard gates may be too strict"
        )

    return rep


def build_report() -> dict:
    modes = list(config.MODES.keys())
    reports = [_analyse_mode(m) for m in modes]
    overall_keeps = sum(r.keeps for r in reports)
    overall_iters = sum(r.iterations for r in reports)
    overall_issues: list[str] = []
    for r in reports:
        for issue in r.issues:
            overall_issues.append(f"[{r.mode}] {issue}")
    healthy = overall_keeps > 0 and not any("STUCK" in i for i in overall_issues)
    return {
        "generated_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "healthy": healthy,
        "overall_iterations": overall_iters,
        "overall_keeps": overall_keeps,
        "overall_keep_rate": overall_keeps / overall_iters if overall_iters else 0,
        "issues": overall_issues,
        "modes": [
            {
                "mode": r.mode,
                "state_exists": r.state_exists,
                "iterations": r.iterations,
                "keeps": r.keeps,
                "reverts": r.reverts,
                "keep_rate": round(r.keep_rate, 3),
                "last_batch_keeps": r.last_n_keeps,
                "last_batch_reverts": r.last_n_reverts,
                "train_baseline": r.train_baseline,
                "validate_baseline": r.validate_baseline,
                "top_keeps": r.top_keeps,
                "notable_rejections": r.notable_rejections,
                "dead_end_params": r.dead_end_params,
                "changed_params": r.changed_params,
                "issues": r.issues,
            }
            for r in reports
        ],
    }


def render_markdown(rep: dict) -> str:
    lines: list[str] = []
    healthy = rep["healthy"]
    badge = "🟢 HEALTHY" if healthy else "🔴 ATTENTION NEEDED"
    lines.append(f"# Autoresearch Watchdog Report — {badge}")
    lines.append("")
    lines.append(f"_Generated: {rep['generated_at']}_")
    lines.append("")
    lines.append(f"**Total iterations:** {rep['overall_iterations']}  ·  "
                 f"**KEEPs:** {rep['overall_keeps']}  ·  "
                 f"**Keep rate:** {rep['overall_keep_rate']*100:.1f}%")
    lines.append("")

    if rep["issues"]:
        lines.append("## Issues flagged")
        for i in rep["issues"]:
            lines.append(f"- ⚠ {i}")
        lines.append("")

    for m in rep["modes"]:
        lines.append(f"## {m['mode'].upper()}")
        if not m["state_exists"]:
            lines.append("_no state file — mode hasn't been run yet_")
            lines.append("")
            continue
        lines.append(
            f"- iter={m['iterations']}, kept={m['keeps']}, reverted={m['reverts']} "
            f"(keep rate {m['keep_rate']*100:.0f}%)"
        )
        lines.append(
            f"- last batch: {m['last_batch_keeps']} KEEP / {m['last_batch_reverts']} REVERT"
        )

        if m["validate_baseline"]:
            v = m["validate_baseline"]
            lines.append(
                f"- VALIDATE baseline: {v.get('n_trades',0)} trades, "
                f"{v.get('win_rate',0)*100:.0f}% WR, "
                f"${v.get('total_pnl',0):.0f} P&L, sharpe {v.get('sharpe_daily',0):.2f}, "
                f"W/L {v.get('wl_ratio') or 0:.2f}x"
            )

        if m["top_keeps"]:
            lines.append("\n**Top KEEPs:**")
            lines.append("| iter | change | Δ sharpe | Δ P&L | val sharpe | val WR |")
            lines.append("|------|--------|----------|-------|-----------|--------|")
            for k in m["top_keeps"]:
                lines.append(
                    f"| {k['iter']} | `{k['param']}: {k['old']} -> {k['new']}` | "
                    f"{k['delta_sharpe']:+.2f} | ${k['delta_pnl']:+.0f} | "
                    f"{k['val_sharpe']:.2f} | {k['val_wr']*100:.0f}% |"
                )

        if m["notable_rejections"]:
            lines.append("\n**Notable REVERTs (good val metrics, rejected anyway):**")
            for r in m["notable_rejections"]:
                lines.append(
                    f"- iter {r['iter']}: `{r['param']} -> {r['new']}` | "
                    f"val P&L ${r['val_pnl']:.0f}, sharpe {r['val_sharpe']:.2f}, "
                    f"WR {r['val_wr']*100:.0f}% | rejected: {r['rejected_because']}"
                )

        if m["changed_params"]:
            lines.append("\n**Params that drifted from starting point:**")
            for p, ch in m["changed_params"].items():
                lines.append(f"- `{p}`: {ch['from']} -> {ch['to']}")

        if m["dead_end_params"]:
            lines.append(f"\n**Dead-end params (tried >= {PARAM_DEAD_END_THRESHOLD}x, 0 KEEPs):** "
                         + ", ".join(f"`{p}`" for p in m["dead_end_params"]))

        if m["issues"]:
            lines.append("\n**Mode issues:**")
            for i in m["issues"]:
                lines.append(f"- {i}")

        lines.append("")

    return "\n".join(lines)


def write_report(rep: dict) -> None:
    REPORT_JSON.write_text(json.dumps(rep, indent=2, default=str), encoding="utf-8")
    REPORT_MD.write_text(render_markdown(rep), encoding="utf-8")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="Exit 0 if healthy, 2 if stuck. Useful for shell scripts.")
    ap.add_argument("--print", action="store_true",
                    help="Print the markdown report to stdout in addition to writing files.")
    args = ap.parse_args()

    rep = build_report()
    write_report(rep)
    logger.info("wrote %s and %s", REPORT_MD.name, REPORT_JSON.name)

    if args.print:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
        print(render_markdown(rep))

    if args.check and not rep["healthy"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

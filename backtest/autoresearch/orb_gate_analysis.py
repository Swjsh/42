"""ORB direction + OR-range gate analysis from graded watcher observations.

Reads 391 graded ORB observations from automation/state/watcher-observations.jsonl.
Applies 4 gate scenarios and computes per-quarter P&L breakdown for each:
  1. ALL (baseline — 391 obs)
  2. LONG_ONLY — direction=="long" (274 obs)
  3. NARROW_OR — or_range <= 2.00 (all directions)
  4. NARROW_OR_LONG — or_range <= 2.00 AND direction=="long"

Writes:
  analysis/backtests/orb-gate-analysis/results.json
  analysis/backtests/orb-gate-analysis/summary.md

Per CLAUDE.md OP-27: all subprocess calls use CREATE_NO_WINDOW.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

OBS_FILE = ROOT / "automation" / "state" / "watcher-observations.jsonl"
OUT_DIR = ROOT / "analysis" / "backtests" / "orb-gate-analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUT_DIR / "results.json"
OUT_MD = OUT_DIR / "summary.md"

OR_RANGE_MAX = 2.00  # Leaderboard candidate #4 gate


def _quarter(bar_ts_str: str) -> str:
    """Return 'YYYY-QN' from an ISO timestamp string."""
    try:
        ts = bar_ts_str.replace("T", " ").split("+")[0].split("-0")[0].split("-04")[0]
        d = datetime.fromisoformat(ts.strip())
        q = (d.month - 1) // 3 + 1
        return f"{d.year}-Q{q}"
    except Exception:
        return "unknown"


def _load_orb_obs() -> list[dict]:
    lines = OBS_FILE.read_text(encoding="utf-8").splitlines()
    obs = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("watcher_name") != "orb_watcher":
            continue
        pnl = r.get("would_be_pnl_dollars")
        if pnl is None:
            continue
        obs.append(r)
    return obs


def _analyze_scenario(obs: list[dict], label: str) -> dict:
    if not obs:
        return {"label": label, "n": 0, "wr_pct": 0, "pnl": 0, "quarters": {}}

    wins = sum(1 for o in obs if (o.get("would_be_pnl_dollars") or 0) > 0)
    pnl = sum(o.get("would_be_pnl_dollars") or 0 for o in obs)
    wr = wins / len(obs) * 100 if obs else 0

    # Per-quarter
    by_q: dict[str, list[dict]] = defaultdict(list)
    for o in obs:
        q = _quarter(o.get("bar_timestamp_et", ""))
        by_q[q].append(o)

    quarters = {}
    for q in sorted(by_q):
        q_obs = by_q[q]
        q_wins = sum(1 for o in q_obs if (o.get("would_be_pnl_dollars") or 0) > 0)
        q_pnl = sum(o.get("would_be_pnl_dollars") or 0 for o in q_obs)
        quarters[q] = {
            "n": len(q_obs),
            "wins": q_wins,
            "wr_pct": round(q_wins / len(q_obs) * 100, 1),
            "pnl": round(q_pnl, 2),
        }

    pos_quarters = sum(1 for v in quarters.values() if v["pnl"] > 0)
    total_quarters = len(quarters)

    return {
        "label": label,
        "n": len(obs),
        "wins": wins,
        "wr_pct": round(wr, 1),
        "pnl": round(pnl, 2),
        "positive_quarters": f"{pos_quarters}/{total_quarters}",
        "quarters": quarters,
    }


def _outcome_breakdown(obs: list[dict]) -> dict:
    from collections import Counter
    outcomes = Counter(o.get("would_be_outcome", "unknown") for o in obs)
    pnl_by_outcome = defaultdict(float)
    for o in obs:
        pnl_by_outcome[o.get("would_be_outcome", "unknown")] += o.get("would_be_pnl_dollars") or 0
    return {
        k: {"n": outcomes[k], "pnl": round(pnl_by_outcome[k], 2)}
        for k in sorted(outcomes, key=lambda x: -outcomes[x])
    }


def main() -> None:
    print("[orb_gate_analysis] loading observations...")
    all_obs = _load_orb_obs()
    print(f"[orb_gate_analysis] loaded {len(all_obs)} graded ORB observations")

    # Scenarios
    long_only = [o for o in all_obs if o.get("direction") == "long"]
    narrow_or = [o for o in all_obs if (o.get("metadata") or {}).get("or_range", 9999) <= OR_RANGE_MAX]
    narrow_or_long = [o for o in narrow_or if o.get("direction") == "long"]

    scenarios = {
        "ALL": _analyze_scenario(all_obs, "ALL (baseline — 391 obs)"),
        "LONG_ONLY": _analyze_scenario(long_only, f"LONG_ONLY — direction==long ({len(long_only)} obs)"),
        "NARROW_OR": _analyze_scenario(narrow_or, f"NARROW_OR — or_range<={OR_RANGE_MAX} ({len(narrow_or)} obs)"),
        "NARROW_OR_LONG": _analyze_scenario(narrow_or_long, f"NARROW_OR_LONG — or_range<={OR_RANGE_MAX} AND long ({len(narrow_or_long)} obs)"),
    }

    # Outcome breakdowns
    outcome_breakdowns = {
        "ALL": _outcome_breakdown(all_obs),
        "LONG_ONLY": _outcome_breakdown(long_only),
        "NARROW_OR": _outcome_breakdown(narrow_or),
        "NARROW_OR_LONG": _outcome_breakdown(narrow_or_long),
    }

    # OR-range distribution for context
    or_ranges = [(o.get("metadata") or {}).get("or_range") for o in all_obs]
    or_ranges = [r for r in or_ranges if r is not None]
    pct_narrow = sum(1 for r in or_ranges if r <= OR_RANGE_MAX) / len(or_ranges) * 100 if or_ranges else 0
    or_range_stats = {
        "min": round(min(or_ranges), 3) if or_ranges else None,
        "max": round(max(or_ranges), 3) if or_ranges else None,
        "mean": round(sum(or_ranges) / len(or_ranges), 3) if or_ranges else None,
        "pct_narrow_2_00": round(pct_narrow, 1),
    }

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "gate_threshold": {"or_range_max": OR_RANGE_MAX, "direction_gate": "long"},
        "scenarios": scenarios,
        "outcome_breakdowns": outcome_breakdowns,
        "or_range_distribution": or_range_stats,
    }

    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[orb_gate_analysis] wrote {OUT_JSON}")

    # Markdown summary
    lines = [
        "# ORB Gate Analysis — Direction + OR-Range Gates",
        f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M ET')}",
        f"> Source: {len(all_obs)} graded ORB observations (watcher-observations.jsonl)",
        "",
        "## Scenarios",
        "",
        "| Scenario | N | WR% | P&L | Positive Qtrs |",
        "|---|---:|---:|---:|---:|",
    ]
    for key, s in scenarios.items():
        lines.append(f"| **{key}** | {s['n']} | {s['wr_pct']}% | ${s['pnl']:,.0f} | {s.get('positive_quarters','?')} |")

    lines += [
        "",
        "## Per-Quarter Breakdown",
        "",
    ]
    for key, s in scenarios.items():
        lines.append(f"### {key}: {s['label']}")
        lines.append("")
        lines.append("| Quarter | N | WR% | P&L |")
        lines.append("|---|---:|---:|---:|")
        for q, qd in sorted(s["quarters"].items()):
            sign = "+" if qd["pnl"] >= 0 else ""
            lines.append(f"| {q} | {qd['n']} | {qd['wr_pct']}% | {sign}${qd['pnl']:,.0f} |")
        lines.append("")

    lines += [
        "## OR-Range Distribution",
        f"- Min: {or_range_stats['min']}",
        f"- Max: {or_range_stats['max']}",
        f"- Mean: {or_range_stats['mean']}",
        f"- % observations with OR-range ≤ 2.00: {or_range_stats['pct_narrow_2_00']}%",
        "",
        "## Outcome Breakdowns",
    ]
    for key, bd in outcome_breakdowns.items():
        lines.append(f"\n### {key}")
        lines.append("| Outcome | N | P&L |")
        lines.append("|---|---:|---:|")
        for outcome, stats in bd.items():
            lines.append(f"| {outcome} | {stats['n']} | ${stats['pnl']:,.0f} |")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    print(f"[orb_gate_analysis] wrote {OUT_MD}")

    # Console summary
    print("\n=== ORB GATE ANALYSIS RESULTS ===")
    for key, s in scenarios.items():
        print(f"  {key:20s}: N={s['n']:3d}  WR={s['wr_pct']:5.1f}%  P&L=${s['pnl']:>8,.0f}  +Qtrs={s.get('positive_quarters','?')}")


if __name__ == "__main__":
    main()

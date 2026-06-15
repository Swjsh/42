"""V14E_BEAR_ONLY_GATE analysis from graded watcher observations.

Reads v14_enhanced_watcher graded observations and applies the bear-only gate:
  - BASE: all 505 obs (direction=long and direction=short)
  - BEAR_ONLY: direction=short (removes bull branch)
  - BEAR_HIGH_CONF: direction=short AND confidence=high

Reports P&L by confidence tier and VIX regime.
Writes:
  analysis/backtests/v14e-bear-gate/results.json
  analysis/backtests/v14e-bear-gate/summary.md
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
OUT_DIR = ROOT / "analysis" / "backtests" / "v14e-bear-gate"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUT_DIR / "results.json"
OUT_MD = OUT_DIR / "summary.md"


def _quarter(bar_ts_str: str) -> str:
    try:
        d = datetime.fromisoformat(bar_ts_str[:10])  # "YYYY-MM-DD" slice, tz-safe
        q = (d.month - 1) // 3 + 1
        return f"{d.year}-Q{q}"
    except Exception:
        return "unknown"


def _analyze_scenario(obs: list[dict], label: str) -> dict:
    if not obs:
        return {"label": label, "n": 0, "wr_pct": 0, "pnl": 0, "quarters": {}}
    wins = sum(1 for o in obs if (o.get("would_be_pnl_dollars") or 0) > 0)
    pnl = sum(o.get("would_be_pnl_dollars") or 0 for o in obs)
    wr = wins / len(obs) * 100 if obs else 0
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
    return {
        "label": label,
        "n": len(obs),
        "wins": wins,
        "wr_pct": round(wr, 1),
        "pnl": round(pnl, 2),
        "positive_quarters": f"{pos_quarters}/{len(quarters)}",
        "quarters": quarters,
    }


def _by_confidence(obs: list[dict]) -> dict:
    from collections import Counter
    conf_groups: dict[str, list[dict]] = defaultdict(list)
    for o in obs:
        conf_groups[o.get("confidence", "unknown")].append(o)
    result = {}
    for c in sorted(conf_groups):
        g = conf_groups[c]
        wins = sum(1 for o in g if (o.get("would_be_pnl_dollars") or 0) > 0)
        pnl = sum(o.get("would_be_pnl_dollars") or 0 for o in g)
        result[c] = {
            "n": len(g),
            "wr_pct": round(wins / len(g) * 100, 1),
            "pnl": round(pnl, 2),
        }
    return result


def main() -> None:
    print("[v14e_bear_gate] loading observations...")
    lines = OBS_FILE.read_text(encoding="utf-8").splitlines()
    all_obs = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("watcher_name") != "v14_enhanced_watcher":
            continue
        if r.get("would_be_pnl_dollars") is None:
            continue
        all_obs.append(r)

    # Dedup by bar_timestamp_et[:16] — one row per unique 5-min SPY bar per watcher.
    # Gamma_Heartbeat fires every 3 min; multiple ticks per bar inflate N ~2-4×. (L67)
    _seen: set[str] = set()
    _deduped: list[dict] = []
    for _o in sorted(all_obs, key=lambda x: x.get("bar_timestamp_et") or ""):
        _key = (_o.get("bar_timestamp_et") or "")[:16]
        if _key not in _seen:
            _seen.add(_key)
            _deduped.append(_o)
    all_obs = _deduped

    print(f"[v14e_bear_gate] loaded {len(all_obs)} graded v14e observations (deduped)")

    long_obs = [o for o in all_obs if o.get("direction") == "long"]
    short_obs = [o for o in all_obs if o.get("direction") == "short"]
    short_high = [o for o in short_obs if o.get("confidence") == "high"]

    scenarios = {
        "ALL": _analyze_scenario(all_obs, f"ALL (baseline, {len(all_obs)} obs)"),
        "LONG_ONLY": _analyze_scenario(long_obs, f"LONG_ONLY (bull branch, {len(long_obs)} obs — this is the DRAG)"),
        "BEAR_ONLY": _analyze_scenario(short_obs, f"BEAR_ONLY (proposed gate, {len(short_obs)} obs)"),
        "BEAR_HIGH_CONF": _analyze_scenario(short_high, f"BEAR_HIGH_CONF (best sub-tier, {len(short_high)} obs)"),
    }

    by_conf_all = _by_confidence(all_obs)
    by_conf_bear = _by_confidence(short_obs)

    # Bull metadata: score distribution
    bull_scores = []
    for o in long_obs:
        meta = o.get("metadata") or {}
        score = meta.get("bull_score") or meta.get("score")
        if score is not None:
            bull_scores.append(score)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenarios": scenarios,
        "confidence_breakdown_all": by_conf_all,
        "confidence_breakdown_bear_only": by_conf_bear,
        "bull_score_count": len(bull_scores),
        "bull_score_sample": bull_scores[:10],
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"[v14e_bear_gate] wrote {OUT_JSON}")

    lines_out = [
        "# V14E_BEAR_ONLY_GATE Analysis",
        f"> Generated: {datetime.now().strftime('%Y-%m-%d %H:%M ET')}",
        f"> Source: {len(all_obs)} graded v14_enhanced_watcher observations",
        "",
        "## Scenarios",
        "",
        "| Scenario | N | WR% | P&L | Positive Qtrs |",
        "|---|---:|---:|---:|---:|",
    ]
    for key, s in scenarios.items():
        lines_out.append(f"| **{key}** | {s['n']} | {s['wr_pct']}% | ${s['pnl']:,.0f} | {s.get('positive_quarters','?')} |")

    lines_out += ["", "## Confidence Breakdown — ALL", "", "| Confidence | N | WR% | P&L |", "|---|---:|---:|---:|"]
    for c, d in by_conf_all.items():
        lines_out.append(f"| {c} | {d['n']} | {d['wr_pct']}% | ${d['pnl']:,.0f} |")

    lines_out += ["", "## Confidence Breakdown — BEAR ONLY", "", "| Confidence | N | WR% | P&L |", "|---|---:|---:|---:|"]
    for c, d in by_conf_bear.items():
        lines_out.append(f"| {c} | {d['n']} | {d['wr_pct']}% | ${d['pnl']:,.0f} |")

    lines_out += ["", "## Per-Quarter Breakdown"]
    for key, s in scenarios.items():
        lines_out += [f"\n### {key}", "", "| Quarter | N | WR% | P&L |", "|---|---:|---:|---:|"]
        for q, qd in sorted(s["quarters"].items()):
            sign = "+" if qd["pnl"] >= 0 else ""
            lines_out.append(f"| {q} | {qd['n']} | {qd['wr_pct']}% | {sign}${qd['pnl']:,.0f} |")

    OUT_MD.write_text("\n".join(lines_out), encoding="utf-8")
    print(f"[v14e_bear_gate] wrote {OUT_MD}")

    print("\n=== V14E BEAR GATE RESULTS ===")
    for key, s in scenarios.items():
        print(f"  {key:20s}: N={s['n']:3d}  WR={s['wr_pct']:5.1f}%  P&L=${s['pnl']:>8,.0f}  +Qtrs={s.get('positive_quarters','?')}")


if __name__ == "__main__":
    main()

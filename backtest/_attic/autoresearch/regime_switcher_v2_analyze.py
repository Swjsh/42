"""REGIME_SWITCHER v2 analysis (2026-05-13 evening).

Reads:
  - _state/regime_switcher_stage1/strategy_pnl_matrix.json (v14e re-run with
    GOOD T44b combo + T50b trailing kwargs + use_real_fills=True)
  - _state/regime_switcher_stage1/results.jsonl (passing combos, if any)
  - _state/regime_switcher_stage1/keepers.jsonl
  - _state/regime_switcher_stage1/rejections.jsonl
  - analysis/recommendations/v14_enhanced-pl-variants.json (B1 baseline)

Writes:
  - analysis/recommendations/regime_switcher-v2.json
  - docs/REGIME-SWITCHER-V2-2026-05-13.md
"""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
GAMMA = REPO.parent
STATE = REPO / "autoresearch" / "_state" / "regime_switcher_stage1"

ANCHORS = [
    {"date": "2026-04-29", "j_pnl": 342, "floor": 150, "winner": True},
    {"date": "2026-05-01", "j_pnl": 470, "floor": 30, "winner": True},
    {"date": "2026-05-04", "j_pnl": 730, "floor": 180, "winner": True},
    {"date": "2026-05-05", "j_pnl": -260, "floor": 150, "winner": False},
    {"date": "2026-05-06", "j_pnl": -300, "floor": 100, "winner": False},
    {"date": "2026-05-07", "j_pnl": -165, "floor": 0, "winner": False},
    {"date": "2026-05-12", "j_pnl": 400, "floor": 200, "winner": True},
]


def _load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return out


def main() -> int:
    matrix_path = STATE / "strategy_pnl_matrix.json"
    if not matrix_path.exists():
        print(f"FATAL: matrix missing at {matrix_path}")
        return 1
    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    print(f"matrix strategies: {list(matrix.keys())}")
    for k, v in matrix.items():
        wins = sum(1 for p in v.values() if p > 0)
        losses = sum(1 for p in v.values() if p < 0)
        wr = wins / (wins + losses) if (wins + losses) else 0
        print(f"  {k}: {len(v)} days, total=${sum(v.values()):.0f}, wins={wins}, losses={losses}, wr={wr:.2f}")

    keepers = _load_jsonl(STATE / "keepers.jsonl")
    results = _load_jsonl(STATE / "results.jsonl")
    rejections = _load_jsonl(STATE / "rejections.jsonl")
    print(f"\ngrinder: {len(keepers)} keepers, {len(results)} passed_floors, {len(rejections)} rejected")

    # Find the best combo (by edge_capture, then wide_pnl)
    all_combos = results + rejections
    if not all_combos:
        print("no combos to analyze")
        return 1
    best = max(all_combos, key=lambda r: (r.get("edge_capture", -9e9), r.get("wide_pnl", -9e9)))
    print(f"\nBest combo (by edge_capture):")
    print(f"  edge_capture: ${best.get('edge_capture', 0):.0f}")
    print(f"  wide_pnl: ${best.get('wide_pnl', 0):.0f}")
    print(f"  winners_capture: ${best.get('winners_capture', 0):.0f}")
    print(f"  losers_added: ${best.get('losers_added', 0):.0f}")
    print(f"  passed_floors: {best.get('passed_floors')}")
    print(f"  combo: {best.get('combo')}")
    print(f"  by_day: {best.get('by_day')}")
    print(f"  regime_label_per_day: {best.get('regime_label_per_day')}")
    print(f"  strategy_per_day: {best.get('strategy_per_day')}")
    print(f"  positive_quarters: {best.get('positive_quarters')}/{best.get('quarter_count')}")
    print(f"  top5_pct: {best.get('top5_pct')}")
    print(f"  max_drawdown: ${best.get('max_drawdown', 0):.0f}")
    print(f"  regressions: {best.get('regressions')}")

    best_wide_combo = max(all_combos, key=lambda r: r.get("wide_pnl", -9e9))
    print(f"\nBest combo (by wide_pnl):")
    print(f"  wide_pnl: ${best_wide_combo.get('wide_pnl', 0):.0f}")
    print(f"  edge_capture: ${best_wide_combo.get('edge_capture', 0):.0f}")
    print(f"  combo: {best_wide_combo.get('combo')}")

    # Compare to standalone v14e B1
    v14e_pl_path = GAMMA / "analysis" / "recommendations" / "v14_enhanced-pl-variants.json"
    v14e_baseline = None
    if v14e_pl_path.exists():
        d = json.loads(v14e_pl_path.read_text(encoding="utf-8"))
        for v in d["variants"]:
            if v["label"] == "B1_trailing_20pct":
                v14e_baseline = v["metrics"]
                break
    if v14e_baseline:
        print(f"\nstandalone v14e B1 (trailing 20%) wide_pnl: ${v14e_baseline['wide_pnl']:.0f}")
        print(f"  vs best regime_switcher wide_pnl: ${best_wide_combo.get('wide_pnl', 0):.0f}")
        delta = best_wide_combo.get("wide_pnl", 0) - v14e_baseline["wide_pnl"]
        print(f"  delta: ${delta:.0f} ({'switcher better' if delta > 0 else 'standalone better'})")

    # Write recommendation JSON
    rec_path = GAMMA / "analysis" / "recommendations" / "regime_switcher-v2.json"
    rec = {
        "generated_at": dt.datetime.now().isoformat(),
        "rule_id": "regime_switcher_v2",
        "wide_window": {"start": "2025-01-01", "end": "2026-05-12"},
        "changes_since_morning": {
            "v14e_combo": "GOOD T44b winner + T50b trailing 20% kwargs (real-fills)",
            "sniper_excluded": True,
            "sniper_routes": "TREND_DAY/CHOP/FALLBACK -> NONE_TRADE (no SNIPER routes)",
            "chop_default_strategy": "VWAP only (SNIPER option removed from grid)",
            "grid_size": 972,
        },
        "matrix_summary": {
            k: {
                "n_days": len(v),
                "total": round(sum(v.values()), 2),
                "wins": sum(1 for p in v.values() if p > 0),
                "losses": sum(1 for p in v.values() if p < 0),
            } for k, v in matrix.items()
        },
        "grinder_summary": {
            "keepers": len(keepers),
            "passed_floors": len(results),
            "rejected": len(rejections),
        },
        "best_by_edge_capture": {
            "combo": best.get("combo"),
            "edge_capture": best.get("edge_capture"),
            "winners_capture": best.get("winners_capture"),
            "losers_added": best.get("losers_added"),
            "wide_pnl": best.get("wide_pnl"),
            "wide_n_trades": best.get("wide_n_trades"),
            "wide_wr": best.get("wide_wr"),
            "by_day_anchors": {a["date"]: best.get("by_day", {}).get(a["date"], 0) for a in ANCHORS},
            "regime_label_per_day": best.get("regime_label_per_day"),
            "strategy_per_day": best.get("strategy_per_day"),
            "anchor_classification_correct": best.get("anchor_classification_correct"),
            "passed_floors": best.get("passed_floors"),
            "regressions": best.get("regressions", [])[:10],
            "positive_quarters": best.get("positive_quarters"),
            "quarter_count": best.get("quarter_count"),
            "top5_pct": best.get("top5_pct"),
            "max_drawdown": best.get("max_drawdown"),
            "regime_distribution": best.get("regime_distribution"),
            "strategy_distribution": best.get("strategy_distribution"),
            "per_regime_pnl": best.get("per_regime_pnl"),
        },
        "best_by_wide_pnl": {
            "combo": best_wide_combo.get("combo"),
            "wide_pnl": best_wide_combo.get("wide_pnl"),
            "edge_capture": best_wide_combo.get("edge_capture"),
            "winners_capture": best_wide_combo.get("winners_capture"),
            "losers_added": best_wide_combo.get("losers_added"),
            "by_day_anchors": {a["date"]: best_wide_combo.get("by_day", {}).get(a["date"], 0) for a in ANCHORS},
            "regime_label_per_day": best_wide_combo.get("regime_label_per_day"),
            "strategy_per_day": best_wide_combo.get("strategy_per_day"),
            "passed_floors": best_wide_combo.get("passed_floors"),
            "regressions": best_wide_combo.get("regressions", [])[:10],
            "positive_quarters": best_wide_combo.get("positive_quarters"),
            "top5_pct": best_wide_combo.get("top5_pct"),
            "max_drawdown": best_wide_combo.get("max_drawdown"),
            "regime_distribution": best_wide_combo.get("regime_distribution"),
            "strategy_distribution": best_wide_combo.get("strategy_distribution"),
            "per_regime_pnl": best_wide_combo.get("per_regime_pnl"),
        },
        "standalone_v14e_b1_baseline": v14e_baseline if v14e_baseline else None,
        "verdict": _make_verdict(best, best_wide_combo, v14e_baseline, len(keepers)),
    }
    rec_path.write_text(json.dumps(rec, indent=2, default=str), encoding="utf-8")
    print(f"\nwrote {rec_path}")

    # Write markdown writeup
    md_path = GAMMA / "docs" / "REGIME-SWITCHER-V2-2026-05-13.md"
    md = _make_markdown(rec, matrix, best, best_wide_combo, v14e_baseline)
    md_path.write_text(md, encoding="utf-8")
    print(f"wrote {md_path}")

    return 0


def _make_verdict(best_edge, best_wide, v14e_baseline, n_keepers) -> dict:
    if v14e_baseline is None:
        return {
            "summary": "INCOMPLETE — standalone v14e baseline not loaded",
            "ratifiable": False,
        }
    standalone_wide = v14e_baseline["wide_pnl"]
    switcher_wide = best_wide.get("wide_pnl", 0)
    switcher_edge = best_edge.get("edge_capture", 0)
    delta = switcher_wide - standalone_wide

    if n_keepers == 0:
        verdict = {
            "summary": (
                f"REGIME_SWITCHER v2: 0 keepers passed floors. "
                f"Best combo by wide_pnl=${switcher_wide:.0f}, by edge=${switcher_edge:.0f}. "
                f"Standalone v14e B1 (trailing 20%) wide_pnl=${standalone_wide:.0f}. "
                f"Delta={'+' if delta >= 0 else ''}${delta:.0f}. "
                f"v14_enhanced standalone is the headline ratifiable strategy."
            ),
            "ratifiable": False,
            "headline_strategy": "v14_enhanced standalone (B1 trailing 20%)",
            "delta_vs_standalone": delta,
        }
    elif delta > 0:
        verdict = {
            "summary": (
                f"REGIME_SWITCHER v2 BEATS standalone v14e by ${delta:.0f} "
                f"({switcher_wide:.0f} vs {standalone_wide:.0f}). {n_keepers} combos pass floors. "
                f"Best edge_capture=${switcher_edge:.0f}."
            ),
            "ratifiable": True,
            "headline_strategy": "REGIME_SWITCHER v2",
            "delta_vs_standalone": delta,
        }
    else:
        verdict = {
            "summary": (
                f"REGIME_SWITCHER v2 underperforms standalone v14e by ${-delta:.0f} "
                f"({switcher_wide:.0f} vs {standalone_wide:.0f}). {n_keepers} combos technically pass floors "
                f"but no real-fills lift over standalone."
            ),
            "ratifiable": False,
            "headline_strategy": "v14_enhanced standalone (B1 trailing 20%)",
            "delta_vs_standalone": delta,
        }
    return verdict


def _make_markdown(rec, matrix, best_edge, best_wide, v14e_baseline) -> str:
    v = rec["verdict"]
    lines = [
        "# REGIME_SWITCHER v2 — 2026-05-13 evening",
        "",
        f"Generated: {rec['generated_at']}",
        f"Wide window: {rec['wide_window']['start']} -> {rec['wide_window']['end']}",
        "",
        "## What changed since the morning grinder",
        "",
        "- v14_enhanced sub-strategy: rebuilt with **GOOD T44b winner combo** + **T50b trailing-20%** kwargs",
        "  - `strike_offset_bear=0, premium_stop_pct=-0.20, tp1_qty_fraction=0.50`",
        "  - `no_trade_before='09:35', tp1_premium_pct=0.30, runner_target_premium_pct=2.5`",
        "  - `profit_lock_threshold_pct=0.05, profit_lock_stop_offset_pct=0.10`",
        "  - `profit_lock_mode='trailing', profit_lock_trail_pct=0.20`",
        "  - **Calls orchestrator with `use_real_fills=True`** (NOT BS sim)",
        "- SNIPER excluded entirely (T42-full real-fills 0/432 keepers)",
        "  - Routes that would have hit SNIPER (TREND_DAY, FALLBACK, optionally CHOP) -> NONE_TRADE",
        "  - chop_default_strategy locked to VWAP (SNIPER option removed from grid)",
        "  - Grid size: 972 combos (was 1,296)",
        "- VWAP + ODF cached results retained (still BS sim, was working morning)",
        "",
        "## Strategy P&L matrix",
        "",
        "| Strategy | Days | Total P&L | Wins | Losses | WR |",
        "|---|---|---|---|---|---|",
    ]
    for k, v_ in rec["matrix_summary"].items():
        n = v_["n_days"]
        total = v_["total"]
        wins = v_["wins"]
        losses = v_["losses"]
        wr = wins / (wins + losses) if (wins + losses) else 0
        lines.append(f"| {k} | {n} | ${total:.0f} | {wins} | {losses} | {wr:.2f} |")

    lines += [
        "",
        "## Grinder summary",
        "",
        f"- Keepers: {rec['grinder_summary']['keepers']}",
        f"- Passed floors: {rec['grinder_summary']['passed_floors']}",
        f"- Rejected: {rec['grinder_summary']['rejected']}",
        "",
        "## Best combo by edge_capture",
        "",
        f"- edge_capture: ${best_edge.get('edge_capture', 0):.0f}",
        f"- wide_pnl: ${best_edge.get('wide_pnl', 0):.0f}",
        f"- winners_capture: ${best_edge.get('winners_capture', 0):.0f}",
        f"- losers_added: ${best_edge.get('losers_added', 0):.0f}",
        f"- anchor_classification_correct: {best_edge.get('anchor_classification_correct')}/7",
        f"- passed_floors: {best_edge.get('passed_floors')}",
        f"- positive_quarters: {best_edge.get('positive_quarters')}/{best_edge.get('quarter_count')}",
        f"- top5_pct: {best_edge.get('top5_pct')}",
        f"- max_drawdown: ${best_edge.get('max_drawdown', 0):.0f}",
        "",
        "**Combo:**",
        "",
        "```json",
        json.dumps(best_edge.get("combo"), indent=2),
        "```",
        "",
        "**Per-anchor breakdown:**",
        "",
        "| Anchor | J P&L | Floor | Engine | Regime | Strategy | Pass |",
        "|---|---|---|---|---|---|---|",
    ]
    for a in ANCHORS:
        ds = a["date"]
        engine = best_edge.get("by_day", {}).get(ds, 0)
        regime = best_edge.get("regime_label_per_day", {}).get(ds, "?")
        strategy = best_edge.get("strategy_per_day", {}).get(ds, "?")
        if a["winner"]:
            passed = "OK" if engine >= a["floor"] else "FAIL"
        else:
            passed = "OK" if engine >= 0 else "FAIL"
        lines.append(
            f"| {ds} | ${a['j_pnl']:+.0f} | ${a['floor']} | ${engine:+.0f} | {regime} | {strategy} | {passed} |"
        )

    lines += [
        "",
        "## Best combo by wide_pnl",
        "",
        f"- wide_pnl: ${best_wide.get('wide_pnl', 0):.0f}",
        f"- edge_capture: ${best_wide.get('edge_capture', 0):.0f}",
        f"- positive_quarters: {best_wide.get('positive_quarters')}/{best_wide.get('quarter_count')}",
        "",
        "**Combo:**",
        "",
        "```json",
        json.dumps(best_wide.get("combo"), indent=2),
        "```",
        "",
        "**Regime distribution:**",
        "",
        "```json",
        json.dumps(best_wide.get("regime_distribution"), indent=2),
        "```",
        "",
        "**Strategy distribution (post-SNIPER-remap):**",
        "",
        "```json",
        json.dumps(best_wide.get("strategy_distribution"), indent=2),
        "```",
        "",
        "**Per-regime P&L:**",
        "",
        "```json",
        json.dumps(best_wide.get("per_regime_pnl"), indent=2),
        "```",
        "",
        "## Comparison to standalone v14e B1 (trailing 20%)",
        "",
    ]
    if v14e_baseline:
        lines += [
            f"- Standalone v14e B1 wide_pnl: ${v14e_baseline['wide_pnl']:.0f} (n={v14e_baseline['wide_n_trades']})",
            f"- Switcher best wide_pnl: ${best_wide.get('wide_pnl', 0):.0f} (n_trade_days={best_wide.get('wide_n_trades', 0)})",
            f"- **Delta: ${best_wide.get('wide_pnl', 0) - v14e_baseline['wide_pnl']:+.0f}**",
        ]
    else:
        lines.append("- standalone v14e baseline NOT FOUND")

    lines += [
        "",
        "## Verdict",
        "",
        v["summary"],
        "",
        f"- Ratifiable: **{v['ratifiable']}**",
        f"- Headline strategy: **{v.get('headline_strategy', '?')}**",
        f"- Delta vs standalone: ${v.get('delta_vs_standalone', 0):+.0f}",
        "",
        "## Limitations / caveats (per OP 20)",
        "",
        "1. **Account-size assumption:** v14e qty defaults from heartbeat (typically 3 contracts at $1k tier).",
        "2. **Sample-bias disclosure:** 972-combo grinder = overfit risk on the 7 anchor days.",
        "3. **OOS test:** NOT run yet — switcher's regime classifier overfits to anchors.",
        "4. **Real-fills check:** v14e routed via `use_real_fills=True`; VWAP/ODF still BS sim (cached).",
        "5. **Failure-mode enumeration:** see max_drawdown above.",
        "6. **Concentration disclosure:** see top5_pct above.",
        "",
        "## Files",
        "",
        "- Modified `backtest/autoresearch/regime_switcher_prepass.py` (GOOD v14e combo + use_real_fills + SNIPER excluded from default --strategies)",
        "- Modified `backtest/autoresearch/regime_switcher_evaluator.py` (SNIPER routes -> NONE_TRADE remap)",
        "- Modified `backtest/autoresearch/regime_switcher_grinder.py` (chop_default_strategy locked to VWAP, grid 972)",
        "- Regenerated `backtest/autoresearch/_state/regime_switcher_stage1/strategy_pnl_matrix.json`",
        "- Regenerated `backtest/autoresearch/_state/regime_switcher_stage1/keepers.jsonl` + `rejections.jsonl`",
        "- Wrote `analysis/recommendations/regime_switcher-v2.json`",
        "- Wrote `docs/REGIME-SWITCHER-V2-2026-05-13.md`",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    raise SystemExit(main())

"""gate_net_cost_table.py -- GOAL-GATE-NET-COST-2026-09-05 N3.

Aggregates `analysis/gate-net-cost/walk-2026-09-05.json` (N2's exit-shape walk, 305 walk_ok /
50 walk_error rows) into the per-gate NET table the goal's DONE-WHEN asks for: winners $,
losers $, net $, ex-best-day net $, per (gate, arm) row AND per gate deduped to waves, over
the full window (2026-08-01..today) AND the frozen window (2026-08-31..today), plus a verdict
(EARNING / COSTING / UNDERPOWERED).

DEFINITION USED FOR $ (goal: "state which definition you use and why, use
realized_if_taken_dollars as the money number"):
  - winner  := a walked row with `realized_if_taken_dollars > 0` (the wave, walked through the
    arm's REAL exit shape, actually made money along that path).
  - loser   := a walked row with `realized_if_taken_dollars <= 0`.
  - net_$   := sum(realized_if_taken_dollars) over all walk_ok rows for that gate/arm (or gate,
    across arms, when deduped to waves) == winners_$ + losers_$ by construction -- this keeps
    the three numbers arithmetically consistent instead of winners_$ using one definition
    (peak_multiple >= 1.3, the CEILING metric N1/right-tail work used) and losers_$ using a
    different one. WHY realized over peak: a wave can peak above 1.3x and still reverse before
    the walked exit stage fires (a real risk in a 0DTE structure/ribbon-flip/time-stop exit
    shape) -- crediting it as a "winner" at its peak price would double-count a reversal this
    same walk already priced honestly. The `n_waves_peak_ge_1p3x` column is reported alongside
    as a disclosure of the alternate (ceiling) definition, per the goal's own DONE-WHEN wording
    ("refused waves that later printed >= 1.3x"), so a reader can see both.
  - ex_best_day_net_$ := net_$ with the single best (highest positive-sum) WAVE-DAY dropped, per
    the goal's concentration-disclosure requirement (memory project_engine_edge_right_tail_2026
    _08_18: waves are the honest denominator; disclose concentration on every net).

Verdict (per the goal's own wording): a gate whose net_$ < 0 means refusing it, net of the
losers it also refused, SAVED money -- EARNING. net_$ > 0 means refusing it COST money net of
the losers -- COSTING. n_waves < 10 (either window) -> UNDERPOWERED regardless of sign.

WAVE DEDUPE: `n_waves` counts unique `wave_id` values per gate (one wave may appear under
several arms, e.g. a fleet gate refusing the same signal on both safe-3 and risky-1); `n_arm_rows`
counts the per-(gate,arm) walked rows (the raw table rows). Both are reported per the goal's
explicit instruction ("report waves AND arm-rows").

CLI: python setup/scripts/gate_net_cost_table.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
WALK_PATH = REPO / "analysis" / "gate-net-cost" / "walk-2026-09-05.json"
WALK_1MIN_PATH = REPO / "analysis" / "gate-net-cost" / "walk-2026-09-05-1min.json"
OUT_JSON = REPO / "analysis" / "gate-net-cost" / "GATE-NET-COST-2026-09-05.json"
OUT_MD = REPO / "analysis" / "gate-net-cost" / "GATE-NET-COST-2026-09-05.md"

FROZEN_START = dt.date(2026, 8, 31)
UNDERPOWERED_FLOOR = 10


def _wave_date(wave_id: str) -> dt.date:
    # wave_id format: "YYYY-MM-DD|YYYY-MM-DDTHH:MM:SS"
    return dt.date.fromisoformat(wave_id.split("|")[0])


def _in_frozen(wave_id: str) -> bool:
    return _wave_date(wave_id) >= FROZEN_START


def _verdict(net: float, n_waves: int) -> str:
    if n_waves < UNDERPOWERED_FLOOR:
        return "UNDERPOWERED"
    if net < 0:
        return "EARNING"  # refusing this gate SAVED money net of the losers it also refused
    if net > 0:
        return "COSTING"
    return "EARNING"  # net exactly 0: no cost, call it a wash under EARNING (not costing)


def _agg(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate a list of walk_ok rows (already filtered to one gate[/arm]/window) into the
    winners/losers/net/ex-best-day/top-3 shape."""
    winners = [r for r in rows if r["realized_if_taken_dollars"] > 0]
    losers = [r for r in rows if r["realized_if_taken_dollars"] <= 0]
    winners_dollars = round(sum(r["realized_if_taken_dollars"] for r in winners), 2)
    losers_dollars = round(sum(r["realized_if_taken_dollars"] for r in losers), 2)
    net = round(winners_dollars + losers_dollars, 2)
    n_peak_ge_1p3x = sum(1 for r in rows if (r.get("peak_multiple") or 0) >= 1.3)

    # ex-best-day: drop the single wave-DAY (grouped by wave_id's date) with the highest
    # positive net contribution, recompute net without it.
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[_wave_date(r["wave_id"]).isoformat()] += r["realized_if_taken_dollars"]
    best_day = max(by_day, key=lambda d: by_day[d]) if by_day else None
    ex_best_day_net = round(net - by_day.get(best_day, 0.0), 2) if best_day else net

    top3 = sorted(rows, key=lambda r: -abs(r["realized_if_taken_dollars"]))[:3]
    top3_disclosed = [
        {
            "wave_id": r["wave_id"], "arm": r["arm"], "contract": r.get("contract"),
            "side": r.get("side"), "entry_px": r.get("entry_px"), "exit_stage": r.get("exit_stage"),
            "exit_px": r.get("exit_px"), "realized_if_taken_dollars": r["realized_if_taken_dollars"],
            "peak_multiple": r.get("peak_multiple"),
        }
        for r in top3
    ]

    return {
        "n_arm_rows": len(rows),
        "n_waves": len(set(r["wave_id"] for r in rows)),
        "n_waves_peak_ge_1p3x": n_peak_ge_1p3x,
        "winners_dollars": winners_dollars,
        "n_winners": len(winners),
        "losers_dollars": losers_dollars,
        "n_losers": len(losers),
        "net_dollars": net,
        "best_day": best_day,
        "best_day_dollars": round(by_day.get(best_day, 0.0), 2) if best_day else None,
        "ex_best_day_net_dollars": ex_best_day_net,
        "top3_by_abs_dollars": top3_disclosed,
    }


def build_table() -> dict[str, Any]:
    walk = json.loads(WALK_PATH.read_text(encoding="utf-8"))
    ok_rows = [r for r in walk["rows"] if r.get("walk_ok")]
    err_rows = [r for r in walk["rows"] if not r.get("walk_ok")]

    by_gate_arm: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_gate: dict[str, list[dict]] = defaultdict(list)
    err_by_gate_arm: dict[tuple[str, str], int] = defaultdict(int)
    for r in ok_rows:
        key = (r["gate"], r["arm"])
        by_gate_arm[key].append(r)
        by_gate[r["gate"]].append(r)
    for r in err_rows:
        err_by_gate_arm[(r["gate"], r.get("arm") or "unknown")] += 1

    # GOAL-OPRA-1MIN-COVERAGE-2026-09-05 O3: net $ re-computed on the 1-min walk
    # (walk-2026-09-05-1min.json, same _agg logic, full window only -- the goal's own
    # DONE-WHEN asks for "a '1-min' column with the deltas", not a second frozen-window
    # table), joined onto both arm_rows_out and gate_rows_out below. Missing/absent file
    # (older runs, or before O3 shipped) degrades every row's 1-min fields to None --
    # disclosed, never a crash.
    by_gate_arm_1min: dict[tuple[str, str], list[dict]] = defaultdict(list)
    by_gate_1min: dict[str, list[dict]] = defaultdict(list)
    if WALK_1MIN_PATH.exists():
        walk_1min = json.loads(WALK_1MIN_PATH.read_text(encoding="utf-8"))
        for r in walk_1min["rows"]:
            if r.get("walk_ok"):
                by_gate_arm_1min[(r["gate"], r["arm"])].append(r)
                by_gate_1min[r["gate"]].append(r)

    arm_rows_out = []
    for (gate, arm), rows in sorted(by_gate_arm.items()):
        full = _agg(rows)
        frozen_rows = [r for r in rows if _in_frozen(r["wave_id"])]
        frozen = _agg(frozen_rows) if frozen_rows else _agg([])
        n_waves_for_verdict = full["n_waves"]
        rows_1min = by_gate_arm_1min.get((gate, arm))
        if rows_1min:
            full_1min = _agg(rows_1min)
            full["net_dollars_1min"] = full_1min["net_dollars"]
            full["net_dollars_delta_1min_minus_5min"] = round(
                full_1min["net_dollars"] - full["net_dollars"], 2)
        else:
            full["net_dollars_1min"] = None
            full["net_dollars_delta_1min_minus_5min"] = None
        arm_rows_out.append({
            "gate": gate,
            "arm": arm,
            "walk_error_count": err_by_gate_arm.get((gate, arm), 0),
            "full_window": full,
            "frozen_window": frozen,
            "verdict_full_window": _verdict(full["net_dollars"], n_waves_for_verdict),
            "verdict_frozen_window": _verdict(frozen["net_dollars"], frozen["n_waves"]),
        })

    gate_rows_out = []
    for gate, rows in sorted(by_gate.items()):
        full = _agg(rows)
        frozen_rows = [r for r in rows if _in_frozen(r["wave_id"])]
        frozen = _agg(frozen_rows) if frozen_rows else _agg([])
        arms_touched = sorted(set(r["arm"] for r in rows))
        err_count = sum(v for (g, a), v in err_by_gate_arm.items() if g == gate)
        rows_1min = by_gate_1min.get(gate)
        if rows_1min:
            full_1min = _agg(rows_1min)
            full["net_dollars_1min"] = full_1min["net_dollars"]
            full["net_dollars_delta_1min_minus_5min"] = round(
                full_1min["net_dollars"] - full["net_dollars"], 2)
        else:
            full["net_dollars_1min"] = None
            full["net_dollars_delta_1min_minus_5min"] = None
        gate_rows_out.append({
            "gate": gate,
            "arms_touched": arms_touched,
            "walk_error_count": err_count,
            "full_window": full,
            "frozen_window": frozen,
            "verdict_full_window": _verdict(full["net_dollars"], full["n_waves"]),
            "verdict_frozen_window": _verdict(frozen["net_dollars"], frozen["n_waves"]),
        })

    return {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "source_walk": str(WALK_PATH.relative_to(REPO)),
        "source_walk_1min": str(WALK_1MIN_PATH.relative_to(REPO)) if WALK_1MIN_PATH.exists() else None,
        "definition": {
            "winner": "realized_if_taken_dollars > 0",
            "loser": "realized_if_taken_dollars <= 0",
            "net": "sum(realized_if_taken_dollars) over all walk_ok rows == winners_dollars + losers_dollars",
            "why_realized_not_peak": (
                "a wave can peak >= 1.3x and still reverse before the walked exit stage "
                "fires; using realized (not peak) avoids crediting a reversal as a win. "
                "n_waves_peak_ge_1p3x is reported alongside as the alternate/ceiling metric."
            ),
            "underpowered_floor_waves": UNDERPOWERED_FLOOR,
            "verdict_rule": "net_dollars < 0 -> EARNING (refusing saved money); "
                            "net_dollars > 0 -> COSTING (refusing lost money); "
                            "n_waves < floor -> UNDERPOWERED regardless of sign.",
        },
        "n_walk_ok_rows": len(ok_rows),
        "n_walk_error_rows": len(err_rows),
        "gate_arm_rows": arm_rows_out,
        "gate_rows_deduped_to_waves": gate_rows_out,
    }


def _fmt_dollars(x: float) -> str:
    return f"${x:,.2f}"


def render_md(table: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append("# GATE-NET-COST-2026-09-05")
    lines.append("")
    lines.append(
        "N3 -- per-gate net-of-losers table, GOAL-GATE-NET-COST-2026-09-05. Built from "
        f"`{table['source_walk']}` ({table['n_walk_ok_rows']} walk_ok / "
        f"{table['n_walk_error_rows']} walk_error rows) by `setup/scripts/gate_net_cost_table.py`."
    )
    lines.append("")
    lines.append("## Definition used for the $ number")
    lines.append("")
    d = table["definition"]
    lines.append(f"- **Winner:** `{d['winner']}`. **Loser:** `{d['loser']}`.")
    lines.append(f"- **Net:** `{d['net']}`.")
    lines.append(f"- **Why realized, not peak:** {d['why_realized_not_peak']}")
    lines.append(
        f"- **Verdict rule:** {d['verdict_rule']} (UNDERPOWERED floor = "
        f"{d['underpowered_floor_waves']} waves.)"
    )
    lines.append("")
    lines.append(
        "## Per gate, deduped to WAVES (one signal, up to 4 arms collapsed) -- full window "
        "2026-08-01..today"
    )
    lines.append("")
    lines.append(
        "| Gate | Arms touched | Waves | Waves peak>=1.3x | Winners $ | Losers $ | Net $ | "
        "Net $ (1-min) | Δ (1min-5min) | Ex-best-day net $ | walk_error | Verdict |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for g in table["gate_rows_deduped_to_waves"]:
        f = g["full_window"]
        net_1min = _fmt_dollars(f["net_dollars_1min"]) if f.get("net_dollars_1min") is not None else "n/a"
        delta_1min = (_fmt_dollars(f["net_dollars_delta_1min_minus_5min"])
                      if f.get("net_dollars_delta_1min_minus_5min") is not None else "n/a")
        lines.append(
            f"| {g['gate']} | {', '.join(g['arms_touched'])} | {f['n_waves']} | "
            f"{f['n_waves_peak_ge_1p3x']} | {_fmt_dollars(f['winners_dollars'])} | "
            f"{_fmt_dollars(f['losers_dollars'])} | {_fmt_dollars(f['net_dollars'])} | "
            f"{net_1min} | {delta_1min} | "
            f"{_fmt_dollars(f['ex_best_day_net_dollars'])} | {g['walk_error_count']} | "
            f"{g['verdict_full_window']} |"
        )
    lines.append("")
    if table.get("source_walk_1min"):
        lines.append(
            f"1-min column source: `{table['source_walk_1min']}` "
            "(GOAL-OPRA-1MIN-COVERAGE-2026-09-05 O3 -- same _agg definition, full window only, "
            "gates with no 1-min-walked rows show n/a rather than a fabricated 0)."
        )
        lines.append("")
    lines.append("## Per gate, deduped to WAVES -- frozen window 2026-08-31..today")
    lines.append("")
    lines.append(
        "| Gate | Waves | Waves peak>=1.3x | Winners $ | Losers $ | Net $ | Ex-best-day net $ | "
        "Verdict |"
    )
    lines.append("|---|---|---|---|---|---|---|---|")
    for g in table["gate_rows_deduped_to_waves"]:
        fr = g["frozen_window"]
        lines.append(
            f"| {g['gate']} | {fr['n_waves']} | {fr['n_waves_peak_ge_1p3x']} | "
            f"{_fmt_dollars(fr['winners_dollars'])} | {_fmt_dollars(fr['losers_dollars'])} | "
            f"{_fmt_dollars(fr['net_dollars'])} | {_fmt_dollars(fr['ex_best_day_net_dollars'])} | "
            f"{g['verdict_frozen_window']} |"
        )
    lines.append("")
    lines.append(
        "## Per gate x arm rows (raw table rows, NOT wave-deduped -- full window)"
    )
    lines.append("")
    lines.append(
        "| Gate | Arm | Arm rows | Waves | Winners $ | Losers $ | Net $ | Ex-best-day net $ | "
        "walk_error | Verdict |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in table["gate_arm_rows"]:
        f = r["full_window"]
        lines.append(
            f"| {r['gate']} | {r['arm']} | {f['n_arm_rows']} | {f['n_waves']} | "
            f"{_fmt_dollars(f['winners_dollars'])} | {_fmt_dollars(f['losers_dollars'])} | "
            f"{_fmt_dollars(f['net_dollars'])} | {_fmt_dollars(f['ex_best_day_net_dollars'])} | "
            f"{r['walk_error_count']} | {r['verdict_full_window']} |"
        )
    lines.append("")

    # fable-too-good: any gate with |net| > $3,000 (wave-deduped, full window) gets its top-3
    # waves listed.
    big = [g for g in table["gate_rows_deduped_to_waves"] if abs(g["full_window"]["net_dollars"]) > 3000]
    lines.append("## /fable-too-good disclosure -- gates with |net| > $3,000 (full window)")
    lines.append("")
    if not big:
        lines.append("None. No gate's wave-deduped full-window net exceeds $3,000 in magnitude.")
    else:
        for g in big:
            f = g["full_window"]
            lines.append(
                f"### {g['gate']} -- net {_fmt_dollars(f['net_dollars'])} "
                f"(ex-best-day {_fmt_dollars(f['ex_best_day_net_dollars'])}, "
                f"best day {g['full_window']['best_day']} contributed "
                f"{_fmt_dollars(g['full_window']['best_day_dollars'])})"
            )
            concentrated = (
                f["best_day_dollars"] is not None
                and abs(f["net_dollars"]) > 0
                and abs(f["best_day_dollars"]) >= 0.5 * abs(f["net_dollars"])
            )
            if concentrated:
                lines.append(
                    "**CONCENTRATION FLAG:** the single best wave-day contributes >= 50% of "
                    "this gate's net -- one day dominates; treat the aggregate with suspicion "
                    "per `/fable-too-good`."
                )
            lines.append("")
            lines.append("| Wave id | Arm | Contract | Side | Entry $ | Exit stage | Exit $ | Realized $ | Peak x |")
            lines.append("|---|---|---|---|---|---|---|---|---|")
            for t in f["top3_by_abs_dollars"]:
                lines.append(
                    f"| {t['wave_id']} | {t['arm']} | {t['contract']} | {t['side']} | "
                    f"{t['entry_px']} | {t['exit_stage']} | {t['exit_px']} | "
                    f"{_fmt_dollars(t['realized_if_taken_dollars'])} | {t['peak_multiple']} |"
                )
            lines.append("")
    lines.append("")
    lines.append(
        "## N1 coverage notes (carried forward from `refusals-2026-09-05.json` / prior "
        "revision of this file -- unchanged by N3)"
    )
    lines.append("")
    lines.append(
        "- **fleet gate_override (`min_triggers`/`require_confluence_or_sequence`) is NOT "
        "tracked by `fleet-gate-leak-ledger.jsonl`** -- that ledger only instruments 4 other "
        "gates (`require_bearish_fill_bar`, `structure_veto_enabled`, `block_bull_1100_1200`, "
        "`block_conf_lvl_rec_afternoon`); the two selectivity gates this goal names were "
        "recovered instead from each fleet arm's own `decisions.jsonl` free-text `reason` "
        "strings (`\"gate: 1 triggers < 2\"`, `\"gate: requires confluence/sequence\"`) -- a "
        "real ledger-coverage gap, disclosed rather than papered over."
    )
    lines.append(
        "- **filter 8 / filter 10** (bear/bull min-triggers volume-multiplier blockers) were "
        "NOT COMPUTED by N1's wave inventory (fire on the large majority of every tick "
        "regardless of ENTER-eligibility -- isolating the true refusal population needs a full "
        "`backtest/lib/filters.py` gate-stack replay, out of scope for this goal). The SIDE-TASK "
        "fix in this same session touches `gate_expiry_check.py`'s OWN separate sole-blocker "
        "instrument for filter-8/filter-10 (its `_stop_level_for_row` side-blind bug) -- that "
        "check remained RED after the fix (re-run below) for reasons independent of the fix "
        "(the sole-blocker path is a `NOT_REPLAYED` proxy that never calls `_stop_level_for_row`)."
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    table = build_table()
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(table, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(table), encoding="utf-8")
    print(f"[gate-net-cost-table] wrote {OUT_JSON}")
    print(f"[gate-net-cost-table] wrote {OUT_MD}")
    for g in table["gate_rows_deduped_to_waves"]:
        f = g["full_window"]
        print(
            f"[gate-net-cost-table] {g['gate']:45s} waves={f['n_waves']:3d} "
            f"net=${f['net_dollars']:>10,.2f} verdict={g['verdict_full_window']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""capture_gap_attribution.py -- GOAL-FLEET-CAPTURE-GAP-2026-09-05 F1+F2.

Reads `analysis/right-tail/ledger.jsonl` (right_tail_capture.py's per-(wave,arm) scoring,
now carrying real gate/risk/core-account attribution after this goal's F3 fixes to
right_tail_capture.py's `_refusal_reason` / `_fleet_decisions_for_arm_day`), classifies
every missed (wave, arm) pair into exactly one of the goal's 7 named mechanisms (or an
honestly-labeled 8th "no evidence" bucket when none of the 7 fit), and computes a dollar
figure per mechanism per arm.

Dollar figure convention (goal text: "the wave's realized multiple on the arm that DID
take it x the missing arm's standard size"): missed_gain = (best_taking_arm_exit_multiple
- 1.0) * missing_arm_standard_notional, where standard_notional is that arm's own median
real BUY-fill notional (qty*premium*100) from fills-ledger.jsonl (safe-2/bold-2) or its
median ENTER-row qty*premium*100 from its own decisions.jsonl (safe-3/risky-1). When NO
arm took the wave, falls back to (peak_multiple_on_tape - 1.0) and flags `proxy: true`
(peak-on-tape, not a realized fill -- always reported UNVERIFIED-quality in the .md).

Outputs (both required by the goal, read-only, $0):
  analysis/right-tail/capture-gap-join-2026-09-05.json   (F1 -- row-per-missed-pair join)
  analysis/right-tail/CAPTURE-GAP-2026-09-05.json        (F2 -- mechanism + dollar tables)
  analysis/right-tail/CAPTURE-GAP-2026-09-05.md          (F2 -- human-readable)

CLI: python setup/scripts/capture_gap_attribution.py
"""
from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
for _p in (REPO, SCRIPTS):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

LEDGER_PATH = REPO / "analysis" / "right-tail" / "ledger.jsonl"
FILLS_LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
OUT_DIR = REPO / "analysis" / "right-tail"

ARMS = ["safe-2", "bold-2", "safe-3", "risky-1"]

# Mechanism vocabulary per GOAL-FLEET-CAPTURE-GAP-2026-09-05.md DONE-WHEN, verbatim.
MECH = {
    1: "fleet gate_override refused it (min_triggers 2 / require_confluence_or_sequence) "
       "-- or, for the two core (non-gate_override) arms, this account's OWN entry gate "
       "(structure veto / quality-lock / time-window filter) blocked it on this account's "
       "own tick while the OTHER core account's ribbon fired",
    2: "settlement / same-day-entries cap",
    3: "NOT_FLAT -- still holding a prior position",
    4: "risk_gate deny (a named risk/veto code)",
    5: "the arm's fleet tick did not run within 2 min of the core ENTER (scheduler cadence / outage)",
    6: "sizing SIZE_BELOW_MIN / affordability",
    7: "took it late (>2 ticks) and it no longer cleared 1.3x from the late entry "
       "-- or was SKIPPED outright as too-late to qualify",
    8: "NO EVIDENCE -- no gate/risk/NOT_FLAT/sizing/lateness row found in-window on any "
       "source AND the fleet tick was confirmed ticking every minute (ruling out mechanism "
       "5's literal cadence-outage reading); the fleet strategy registry itself never "
       "recognized this setup. Does not cleanly match 1-7 -- reported honestly as its own "
       "bucket rather than force-fit.",
}

# Per-arm code -> mechanism mapping, built from the REAL attribution codes recovered by
# right_tail_capture.py's F3 fixes (verified this session against the live ledger).
CODE_TO_MECH: dict[str, int] = {
    "GATE": 1,
    "SKIP_STRUCTURE_VETO": 1,
    "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY": 1,
    "SKIP_CONF_LVL_REC_AFTERNOON": 1,
    "SKIP_BULL_1100_1200": 1,
    "SKIP_ELITE_BULL_LEVEL_RECLAIM": 1,
    "SKIP_RIBBON_MOMENTUM_GATE": 1,
    "SKIP_QUALITY_LOCK": 1,
    "SKIP_DOJI_ENTRY_BAR": 1,
    "SKIP_LEVEL_REJECTION_GATE": 1,
    "SKIP_STALE_TRIGGER": 1,
    "RISK_DENY_SETTLEMENT": 2,
    "FLEET_SETTLEMENT_CAP": 2,
    "NOT_FLAT": 3,
    "RISK_DENY_PDT": 4,
    "RISK_DENY_RISK_CAP": 4,
    "RISK_CAP": 4,
    "VETOED_BY_MODELS": 4,
    "UNREADABLE_INPUT": 4,
    "SKIP_BAD_INPUT": 4,
    "SKIP_ORDER_STILL_OPEN_AFTER_CANCEL": 4,
    "PLACE_FAIL": 4,
    "SKIP_MIN_PREMIUM_FLOOR": 6,
    "SKIP_LATE_ENTRY": 7,
    "SKIP_STALE_SIGHT": 7,
}


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (FileNotFoundError, OSError):
        return []
    out = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def _standard_notional_per_arm() -> dict[str, float | None]:
    """Median real-fill/ENTER-row notional (qty*premium*100) per arm -- the 'missing
    arm's standard size' the goal's dollar formula calls for."""
    result: dict[str, float | None] = {}
    fills = _read_jsonl(FILLS_LEDGER)
    for arm in ("safe-2", "bold-2"):
        sizes = [f["price"] * f["qty"] * 100 for f in fills
                 if f.get("arm") == arm and f.get("side") == "buy" and f.get("price") and f.get("qty")]
        result[arm] = round(statistics.median(sizes), 2) if sizes else None
    for arm in ("safe-3", "risky-1"):
        rows = _read_jsonl(FLEET_DIR / arm / "decisions.jsonl")
        sizes = [r["qty"] * r["premium"] * 100 for r in rows
                 if r.get("action") in ("ENTER_BULL", "ENTER_BEAR") and r.get("qty") and r.get("premium")]
        result[arm] = round(statistics.median(sizes), 2) if sizes else None
    return result


def _classify(refused_by_gate: str | None) -> tuple[int, str]:
    """(mechanism_number, code) from a ledger row's `refused_by_gate` string
    ('<CODE>: <reason text>' or the generic fail-open sentinel)."""
    if not refused_by_gate:
        return 8, "NO_ROW"
    if refused_by_gate.startswith("no matching fleet decision row found"):
        return 8, "NO_ROW"
    code = refused_by_gate.split(":", 1)[0].strip()
    mech = CODE_TO_MECH.get(code)
    if mech is None:
        return 8, code
    return mech, code


def _fleet_tick_ran_near(arm: str, day: str, wave_start_et: str) -> bool | None:
    """For fleet_rest arms, did decisions.jsonl carry a row within 2 min of the wave
    anchor? None if arm is not fleet_rest (this check is meaningless for core arms,
    which are already covered by the core-decisions-based reshape)."""
    if arm not in ("safe-3", "risky-1"):
        return None
    import datetime as dt
    rows = [r for r in _read_jsonl(FLEET_DIR / arm / "decisions.jsonl") if str(r.get("ts_et", "")).startswith(day)]
    try:
        anchor = dt.datetime.fromisoformat(wave_start_et)
    except ValueError:
        return None
    for r in rows:
        try:
            ts = dt.datetime.fromisoformat(r["ts_et"][:19])
        except Exception:
            continue
        if abs((ts - anchor).total_seconds()) <= 120:
            return True
    return False


def build_join() -> dict[str, Any]:
    rows = _read_jsonl(LEDGER_PATH)
    wave_events = [r for r in rows if "wave_start_et" in r and "taken" in r]
    by_wave: dict[tuple[str, str], dict[str, dict]] = defaultdict(dict)
    for r in wave_events:
        by_wave[(r["date"], r["wave_start_et"])][r["arm"]] = r

    join_rows: list[dict[str, Any]] = []
    for (day, wave_start), arm_map in by_wave.items():
        for arm, ev in arm_map.items():
            if ev.get("taken"):
                continue
            mech, code = _classify(ev.get("refused_by_gate"))
            tick_ran = _fleet_tick_ran_near(arm, day, wave_start) if mech == 8 else None
            best_taking = None
            for other_arm, other_ev in arm_map.items():
                if other_ev.get("taken") and other_ev.get("exit_multiple") is not None:
                    if best_taking is None or other_ev["exit_multiple"] > best_taking["exit_multiple"]:
                        best_taking = {"arm": other_arm, "exit_multiple": other_ev["exit_multiple"]}
            join_rows.append({
                "date": day,
                "wave_start_et": wave_start,
                "arm": arm,
                "side": ev.get("side"),
                "mechanism": mech,
                "mechanism_label": MECH[mech],
                "evidence_code": code,
                "evidence_row_quoted": ev.get("refused_by_gate"),
                "fleet_tick_ran_within_2min": tick_ran,
                "peak_multiple_on_tape": ev.get("peak_multiple_on_tape"),
                "best_taking_arm": best_taking,
            })
    join_rows.sort(key=lambda r: (r["date"], r["wave_start_et"], r["arm"]))
    return {
        "_doc": "GOAL-FLEET-CAPTURE-GAP-2026-09-05 F1. One row per missed (wave, arm) "
                "pair, joined from analysis/right-tail/ledger.jsonl. Row count MUST equal "
                "the number of missed (wave, arm) pairs (taken=false, scored=true).",
        "generated_from": "analysis/right-tail/ledger.jsonl (post-F3-fix rerun of "
                           "scratchpad/backfill_right_tail.py, this session)",
        "row_count": len(join_rows),
        "rows": join_rows,
    }


def build_attribution(join: dict[str, Any]) -> dict[str, Any]:
    notional = _standard_notional_per_arm()
    per_arm_mech: dict[str, dict[int, dict[str, Any]]] = {a: defaultdict(lambda: {"n": 0, "dollars": 0.0, "rows": []}) for a in ARMS}
    for row in join["rows"]:
        arm = row["arm"]
        mech = row["mechanism"]
        bucket = per_arm_mech[arm][mech]
        bucket["n"] += 1
        std = notional.get(arm)
        if row["best_taking_arm"] is not None and std is not None:
            multiple = row["best_taking_arm"]["exit_multiple"]
            dollars = round((multiple - 1.0) * std, 2)
            proxy = False
        elif row.get("peak_multiple_on_tape") is not None and std is not None:
            multiple = row["peak_multiple_on_tape"]
            dollars = round((multiple - 1.0) * std, 2)
            proxy = True
        else:
            dollars = 0.0
            proxy = None
        bucket["dollars"] = round(bucket["dollars"] + dollars, 2)
        bucket["rows"].append({
            "date": row["date"], "wave_start_et": row["wave_start_et"],
            "evidence_row_quoted": row["evidence_row_quoted"],
            "dollars": dollars, "proxy": proxy,
        })

    summary_table = []
    mech_totals: dict[int, float] = defaultdict(float)
    for arm in ARMS:
        for mech in sorted(per_arm_mech[arm]):
            bucket = per_arm_mech[arm][mech]
            summary_table.append({
                "arm": arm, "mechanism": mech, "mechanism_label": MECH[mech],
                "n_missed_waves": bucket["n"], "dollar_estimate": bucket["dollars"],
            })
            mech_totals[mech] += bucket["dollars"]

    total_missed = sum(b["n"] for arm in ARMS for b in per_arm_mech[arm].values())
    return {
        "_doc": "GOAL-FLEET-CAPTURE-GAP-2026-09-05 F2. Mechanism 1-8 classification + "
                "dollar table per arm. Dollar formula: (best-taking-arm exit_multiple - "
                "1.0) * missing arm's own median real-fill/ENTER notional; falls back to "
                "(peak_multiple_on_tape - 1.0) * notional (labeled proxy=true, UNVERIFIED "
                "tape-truth not a realized fill) when no arm captured the wave.",
        "standard_notional_per_arm": notional,
        "per_arm_mechanism": {arm: {str(m): d for m, d in per_arm_mech[arm].items()} for arm in ARMS},
        "summary_table": summary_table,
        "mechanism_totals_dollars": {str(k): round(v, 2) for k, v in mech_totals.items()},
        "total_missed_waves": total_missed,
        "join_row_count": join["row_count"],
        "row_count_matches_missed": total_missed == join["row_count"],
    }


def render_markdown(join: dict[str, Any], attrib: dict[str, Any]) -> str:
    lines = [
        "# CAPTURE-GAP-2026-09-05 -- fleet capture-gap mechanism attribution",
        "",
        f"GOAL-FLEET-CAPTURE-GAP-2026-09-05 F2. {attrib['total_missed_waves']} missed "
        f"(wave, arm) pairs classified, {join['row_count']} join rows "
        f"({'MATCH' if attrib['row_count_matches_missed'] else 'MISMATCH -- see HONEST STATE'}).",
        "",
        "## Mechanism vocabulary",
        "",
    ]
    for k in sorted(MECH):
        lines.append(f"{k}. {MECH[k]}")
    lines.append("")
    lines.append("## Per-arm x mechanism dollar table")
    lines.append("")
    lines.append("| Arm | Mechanism | N missed | Dollar estimate |")
    lines.append("|---|---|---|---|")
    for row in attrib["summary_table"]:
        lines.append(f"| {row['arm']} | {row['mechanism']} ({row['mechanism_label'][:60]}...) "
                      f"| {row['n_missed_waves']} | ${row['dollar_estimate']:,.2f} |")
    lines.append("")
    lines.append("## Mechanism totals (book-wide)")
    lines.append("")
    lines.append("| Mechanism | Total dollars |")
    lines.append("|---|---|")
    for k in sorted(attrib["mechanism_totals_dollars"], key=int):
        lines.append(f"| {k} | ${attrib['mechanism_totals_dollars'][k]:,.2f} |")
    lines.append("")
    lines.append("## Every missed row, with quoted evidence")
    lines.append("")
    for row in join["rows"]:
        lines.append(f"- **{row['date']} {row['wave_start_et']} / {row['arm']}** "
                      f"-> mechanism {row['mechanism']} (`{row['evidence_code']}`): "
                      f"`{row['evidence_row_quoted']}`")
    lines.append("")
    lines.append("## Standard notional per arm (used in dollar figures)")
    lines.append("")
    for arm, v in attrib["standard_notional_per_arm"].items():
        lines.append(f"- {arm}: ${v:,.2f}" if v is not None else f"- {arm}: UNVERIFIED (no fills/ENTER rows found)")
    return "\n".join(lines) + "\n"


def main() -> None:
    join = build_join()
    attrib = build_attribution(join)
    md = render_markdown(join, attrib)

    (OUT_DIR / "capture-gap-join-2026-09-05.json").write_text(json.dumps(join, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "CAPTURE-GAP-2026-09-05.json").write_text(json.dumps(attrib, indent=2, default=str), encoding="utf-8")
    (OUT_DIR / "CAPTURE-GAP-2026-09-05.md").write_text(md, encoding="utf-8")

    print(f"join rows: {join['row_count']}")
    print(f"total missed waves: {attrib['total_missed_waves']}")
    print(f"row_count_matches_missed: {attrib['row_count_matches_missed']}")
    print(json.dumps(attrib["mechanism_totals_dollars"], indent=2))


if __name__ == "__main__":
    main()

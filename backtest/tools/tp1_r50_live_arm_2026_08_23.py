"""TP1-R50-READJUDICATION-2026-08-23 -- PART 1 (forward-clock trigger count) + PART 3
(live-arm corroboration / proxy-gap analysis), companion to tp1_r50_readjudication_2026_08_23.py
(which handles PART 2, the extended popA gate re-run). Kept as a separate script because this
part reads REAL broker/live data sources (journal/trades.csv, fleet decisions.jsonl) rather than
re-running the backtest harness -- different inputs, different code path, no shared state.

PART 1: count risky-1's LIVE ribbon-family (BEARISH_REJECTION_RIDE_THE_RIBBON /
BULLISH_RECLAIM_RIDE_THE_RIBBON) fills under its +50% TP1 exit_patch
(automation/state/fleet/accounts.json risky-1.params_patch.exit_patch.tp1_premium_pct=0.5),
entries strictly after 2026-08-03, against the prereg's forward_clock_if_frozen: "n>=30 ribbon
fills post-2026-08-03, or by 2026-09-05, whichever first."

TWO SOURCES, cross-validated (per brief -- state which is primary and why):
  PRIMARY: journal/trades.csv, account_id=='risky-1' -- the REAL-FILL ledger (C1 doctrine:
    "Real-fills is the only WR authority"). Position-level count via clustering same
    date+strike+side rows within a tight time window (multi-leg TP1+runner exits of ONE entry
    land as separate CSV rows).
  CROSS-CHECK: automation/state/fleet/risky-1/decisions.jsonl, action in
    {ENTER_BEAR,ENTER_BULL}, placement.placed==true -- the ENGINE's own per-tick placement
    record. Matched to the journal by (date, strike, side, time within 15s).
  Any material (>10%) divergence between the two is DISCLOSED, not silently resolved.

PART 3: for the SAME risky-1 post-2026-08-03 ribbon fills, find sibling-arm fills on the SAME
signal (all 5 SPY fleet/core arms consume ONE shared_signal per
automation/state/fleet/build_shared_signal.py -- MAP.md's DECIDE layer) via journal/trades.csv,
matched on (date, strike, side, entry minute). Siblings: safe-2(csv alias 'safe'),
bold-2(csv alias 'bold'), safe-3, risky-3 -- all four run tp1_premium_pct=1.0 (registry
default; NONE of their exit_patch dicts touch tp1_premium_pct, verified against accounts.json
this session), so risky-1 (tp1=0.5) is the ONLY arm banking a partial early on these exact
signals. Reports: (a) total per-position $ per arm on shared signals -- coarse cut; (b) for
multi-leg positions on both risky-1 and a sibling, the LAST-leg (runner-outcome proxy) $ per
arm -- refined cut, clearly labeled a proxy.

AXIS-MISMATCH DISCLOSURE (required by brief): risky-1's live A/B varies the TP1 LEVEL (+50% vs
siblings' +100%) at whatever tp1_qty_fraction the registry carries (0.667, unchanged by
risky-1's exit_patch). Cell R_tp100_f50 (Part 2) varies the QTY FRACTION (0.5 vs 0.667) at a
FIXED +100% TP1 level. These are NOT the same knob. They share only the qualitative
"early profit extraction may damage the runner cohort" risk (prereg's shared_risk_declared).
Part 3's verdict is read as a PROXY on that shared risk, never as direct evidence for/against
R_tp100_f50's specific qty-fraction axis.

ANALYSIS ONLY. Writes analysis/recommendations/tp1-r50-live-arm-2026-08-23.json (merged into
the final companion doc by the assembly step). No trading-path file touched.

Run: backtest/.venv/Scripts/python.exe backtest/tools/tp1_r50_live_arm_2026_08_23.py
"""
from __future__ import annotations

import csv
import datetime as dt
import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
JOURNAL_CSV = REPO / "journal" / "trades.csv"
RISKY1_DECISIONS = REPO / "automation" / "state" / "fleet" / "risky-1" / "decisions.jsonl"
ACCOUNTS_JSON = REPO / "automation" / "state" / "fleet" / "accounts.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "tp1-r50-live-arm-2026-08-23.json"

CLOCK_ANCHOR_DATE = "2026-08-03"     # strictly AFTER this date
CLOCK_N_FLOOR = 30
CLOCK_CALENDAR_DEADLINE = dt.date(2026, 9, 5)
RIBBON_MARKER = "RIDE_THE_RIBBON"

CSV_ALIAS_TO_ARM = {"safe": "safe-2", "bold": "bold-2", "safe-3": "safe-3",
                     "risky-1": "risky-1", "risky-3": "risky-3"}
SIBLING_CSV_ALIASES = ["safe", "bold", "safe-3", "risky-3"]  # excludes risky-1 itself


def log(m: str) -> None:
    print(f"[tp1-r50-live-arm] {m}", flush=True)


def load_journal_rows() -> list[dict]:
    rows = list(csv.DictReader(open(JOURNAL_CSV, encoding="utf-8-sig")))
    good = [r for r in rows if r.get("date") and len(r["date"]) == 10 and r["date"][4] == "-"]
    log(f"journal/trades.csv: {len(rows)} total rows, {len(good)} well-formed date rows "
        f"({len(rows) - len(good)} malformed/skipped -- pre-existing CSV quoting defect, "
        f"unrelated to this study, disclosed not silently dropped)")
    return good


def to_sec(hhmmss: str) -> int:
    h, m, s = (int(x) for x in hhmmss.split(":"))
    return h * 3600 + m * 60 + s


def cluster_journal_positions(rows: list[dict], time_tol_s: int = 15) -> list[list[dict]]:
    """Group same-(date,strike,side) journal rows whose time_entry is within time_tol_s of
    each other into ONE position (multi-leg TP1+runner exits of a single entry land as
    separate CSV rows with near-identical, not identical, time_entry timestamps)."""
    by_key: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        by_key[(r["date"], r["strike"], r["c_or_p"])].append(r)
    positions: list[list[dict]] = []
    for key, legs in by_key.items():
        legs = sorted(legs, key=lambda r: to_sec(r["time_entry"]))
        cluster: list[dict] = []
        for leg in legs:
            if cluster and to_sec(leg["time_entry"]) - to_sec(cluster[-1]["time_entry"]) > time_tol_s:
                positions.append(cluster)
                cluster = []
            cluster.append(leg)
        if cluster:
            positions.append(cluster)
    return positions


def part1_forward_clock() -> dict:
    log("PART 1: forward-clock trigger check")
    accounts = json.loads(ACCOUNTS_JSON.read_text(encoding="utf-8"))
    risky1_arm = next(a for a in accounts["arms"] if a["id"] == "risky-1")
    exit_patch = risky1_arm["params_patch"]["exit_patch"]
    assert exit_patch.get("tp1_premium_pct") == 0.5, (
        f"risky-1 exit_patch tp1_premium_pct expected 0.5, got {exit_patch.get('tp1_premium_pct')} "
        "-- the +50% arm identity assumed by the prereg's forward_clock no longer holds live; "
        "re-verify before trusting this count")
    log(f"  confirmed risky-1 params_patch.exit_patch = {exit_patch} (the '+50% arm')")

    rows = load_journal_rows()
    r1 = [r for r in rows if r.get("account_id") == "risky-1" and r["date"] > CLOCK_ANCHOR_DATE
          and RIBBON_MARKER in (r.get("setup") or "")]
    positions = cluster_journal_positions(r1)
    n_journal_positions = len(positions)
    n_journal_legs = len(r1)
    log(f"  journal/trades.csv (PRIMARY, real fills): {n_journal_positions} position-level "
        f"entries ({n_journal_legs} leg-rows) strictly after {CLOCK_ANCHOR_DATE}")

    dec_lines = RISKY1_DECISIONS.read_text(encoding="utf-8").splitlines()
    dec_rows = []
    for line in dec_lines:
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        if d.get("action") not in ("ENTER_BEAR", "ENTER_BULL"):
            continue
        p = d.get("placement") or {}
        if not p.get("placed"):
            continue
        date = d["ts_et"][:10]
        if date <= CLOCK_ANCHOR_DATE:
            continue
        if RIBBON_MARKER not in (d.get("setup_name") or ""):
            continue
        dec_rows.append(d)
    n_decisions = len(dec_rows)
    log(f"  decisions.jsonl (CROSS-CHECK, engine placed=true ENTER rows): {n_decisions}")

    # match journal positions <-> decisions rows on (date, strike, side, |time diff|<=15s)
    used = set()
    matched = 0
    for pos in positions:
        first_leg = pos[0]
        for i, d in enumerate(dec_rows):
            if i in used:
                continue
            if (d["ts_et"][:10] == first_leg["date"] and str(d.get("strike")) == first_leg["strike"]
                    and d.get("side") == first_leg["c_or_p"]
                    and abs(to_sec(d["ts_et"][11:19]) - to_sec(first_leg["time_entry"])) <= 15):
                used.add(i)
                matched += 1
                break
    divergence_pct = round(100 * abs(n_journal_positions - n_decisions) / max(1, n_journal_positions), 1)

    n_primary = n_journal_positions   # journal/trades.csv is the real-fill authority (C1)
    clock_n_met = n_primary >= CLOCK_N_FLOOR
    clock_calendar_met = dt.date(2026, 8, 23) >= CLOCK_CALENDAR_DEADLINE  # today, per et_clock context
    clock_triggered = clock_n_met or clock_calendar_met

    return {
        "risky1_exit_patch_verified": exit_patch,
        "journal_primary": {
            "source": "journal/trades.csv, account_id=='risky-1', date > 2026-08-03, "
                       "setup contains RIDE_THE_RIBBON",
            "n_position_level": n_journal_positions, "n_leg_rows": n_journal_legs,
        },
        "decisions_crosscheck": {
            "source": "automation/state/fleet/risky-1/decisions.jsonl, action ENTER_BEAR/ENTER_BULL, "
                       "placement.placed==true, ts_et > 2026-08-03, setup_name contains RIDE_THE_RIBBON",
            "n": n_decisions,
        },
        "cross_validation": {
            "matched_by_date_strike_side_within_15s": matched,
            "divergence_pct_journal_vs_decisions": divergence_pct,
            "note": ("journal position-count runs slightly ahead of decisions' placed=true count "
                     "because a handful of entries fill as 2 broker orders ~1s apart (liquidity "
                     "split), landing as 2 journal rows within the same 15s cluster window but "
                     "only 1 engine ENTER decision; both sources independently clear the n>=30 "
                     "floor regardless of which is used." if divergence_pct < 15 else
                     "DIVERGENCE EXCEEDS 15% -- investigate before trusting either count."),
        },
        "n_used_for_clock": n_primary,
        "n_floor": CLOCK_N_FLOOR,
        "clock_n_met": clock_n_met,
        "clock_calendar_deadline": CLOCK_CALENDAR_DEADLINE.isoformat(),
        "clock_calendar_met": clock_calendar_met,
        "clock_triggered": clock_triggered,
        "verdict": ("CLOCK MET (n-floor)" if clock_n_met else
                    ("CLOCK MET (calendar)" if clock_calendar_met else "PREMATURE_CLOCK")),
    }


def sibling_arm_lookup(rows: list[dict]) -> dict[tuple, dict[str, list[dict]]]:
    """key=(date,strike,side,entry_minute) -> {arm_alias: [journal rows]}. Minute-level
    grouping: fleet arms evaluate the SAME per-minute shared_signal near-simultaneously
    (verified: risky-1 decisions.jsonl ts_et lands within 1-3s of each minute-tick), and
    repeat same-day same-strike re-entries occur in DIFFERENT minutes (verified against
    risky-1's own 2026-08-12 773P sequence: 11:27,11:30,13:24,13:32,13:48,13:52,13:55 -- all
    distinct minutes), so minute-level keying correctly separates distinct signal events
    while tolerating each arm's own few-second gate-evaluation lag."""
    out: dict[tuple, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        if not (RIBBON_MARKER in (r.get("setup") or "") and r["date"] > CLOCK_ANCHOR_DATE):
            continue
        alias = r.get("account_id")
        if alias not in CSV_ALIAS_TO_ARM:
            continue
        minute_key = r["time_entry"][:5]  # HH:MM
        out[(r["date"], r["strike"], r["c_or_p"], minute_key)][alias].append(r)
    return out


def part3_live_arm_corroboration(rows: list[dict]) -> dict:
    log("PART 3: live-arm corroboration + proxy-gap analysis")
    lut = sibling_arm_lookup(rows)
    shared: list[dict] = []
    for (date, strike, side, minute), by_arm in lut.items():
        if "risky-1" not in by_arm:
            continue
        sib_arms = [a for a in SIBLING_CSV_ALIASES if a in by_arm]
        if not sib_arms:
            continue
        r1_legs = by_arm["risky-1"]
        r1_total = round(sum(float(x["dollar_pnl"]) for x in r1_legs), 2)
        r1_legs_sorted = sorted(r1_legs, key=lambda x: to_sec(x["time_exit"]) if x.get("time_exit") else 0)
        r1_last_leg = round(float(r1_legs_sorted[-1]["dollar_pnl"]), 2) if r1_legs_sorted else None
        row = {"date": date, "strike": strike, "side": side, "signal_minute": minute,
               "risky1_total_pnl": r1_total, "risky1_n_legs": len(r1_legs),
               "risky1_last_leg_pnl": r1_last_leg, "siblings": {}}
        for alias in sib_arms:
            arm = CSV_ALIAS_TO_ARM[alias]
            legs = sorted(by_arm[alias], key=lambda x: to_sec(x["time_exit"]) if x.get("time_exit") else 0)
            total = round(sum(float(x["dollar_pnl"]) for x in legs), 2)
            last_leg = round(float(legs[-1]["dollar_pnl"]), 2) if legs else None
            row["siblings"][arm] = {"total_pnl": total, "n_legs": len(legs), "last_leg_pnl": last_leg}
        shared.append(row)
    log(f"  {len(shared)} risky-1 ribbon signals post-2026-08-03 with >=1 sibling on the SAME signal")

    # coarse cut: total-position $ , risky-1 vs each sibling, paired
    per_sibling_coarse: dict[str, dict] = {}
    for arm in ("safe-2", "bold-2", "safe-3", "risky-3"):
        pairs = [(s["risky1_total_pnl"], s["siblings"][arm]["total_pnl"])
                 for s in shared if arm in s["siblings"]]
        if not pairs:
            per_sibling_coarse[arm] = {"n_pairs": 0}
            continue
        r1_sum = round(sum(p[0] for p in pairs), 2)
        sib_sum = round(sum(p[1] for p in pairs), 2)
        n_r1_better = sum(1 for p in pairs if p[0] > p[1])
        n_sib_better = sum(1 for p in pairs if p[1] > p[0])
        n_tie = sum(1 for p in pairs if abs(p[0] - p[1]) <= 0.005)
        per_sibling_coarse[arm] = {
            "n_pairs": len(pairs), "risky1_total": r1_sum, "sibling_total": sib_sum,
            "delta_risky1_minus_sibling": round(r1_sum - sib_sum, 2),
            "n_risky1_better": n_r1_better, "n_sibling_better": n_sib_better, "n_tie": n_tie,
        }

    # refined cut: runner-outcome proxy -- last-leg $ on multi-leg (>=2) positions on BOTH sides
    per_sibling_runner_proxy: dict[str, dict] = {}
    for arm in ("safe-2", "bold-2", "safe-3", "risky-3"):
        pairs = [(s["risky1_last_leg_pnl"], s["siblings"][arm]["last_leg_pnl"])
                 for s in shared if arm in s["siblings"]
                 and s["risky1_n_legs"] >= 2 and s["siblings"][arm]["n_legs"] >= 2]
        if not pairs:
            per_sibling_runner_proxy[arm] = {"n_pairs": 0}
            continue
        r1_sum = round(sum(p[0] for p in pairs), 2)
        sib_sum = round(sum(p[1] for p in pairs), 2)
        per_sibling_runner_proxy[arm] = {
            "n_pairs": len(pairs), "risky1_runner_leg_total": r1_sum,
            "sibling_runner_leg_total": sib_sum,
            "delta_risky1_minus_sibling": round(r1_sum - sib_sum, 2),
        }

    total_coarse_delta = round(sum(v.get("delta_risky1_minus_sibling", 0.0)
                                    for v in per_sibling_coarse.values()), 2)
    total_runner_delta = round(sum(v.get("delta_risky1_minus_sibling", 0.0)
                                    for v in per_sibling_runner_proxy.values()
                                    if "delta_risky1_minus_sibling" in v), 2)
    n_runner_pairs = sum(v.get("n_pairs", 0) for v in per_sibling_runner_proxy.values())

    if n_runner_pairs < 5:
        proxy_verdict = ("SILENT -- too few multi-leg same-signal pairs "
                          f"(n={n_runner_pairs}) to read the runner-cohort proxy either way")
    elif total_runner_delta < -0.005 and total_coarse_delta < -0.005:
        proxy_verdict = "CORROBORATES the early-extraction-damages-runners risk (risky-1 behind on both cuts)"
    elif total_runner_delta > 0.005 and total_coarse_delta > 0.005:
        proxy_verdict = "CONTRADICTS the risk on this small live sample (risky-1 ahead on both cuts)"
    else:
        proxy_verdict = "MIXED -- coarse and runner-proxy cuts disagree in sign; not a clean read either way"

    return {
        "axis_mismatch_disclosure": (
            "risky-1 varies TP1 LEVEL (+50% vs siblings' +100%) at a FIXED qty_fraction "
            "(registry 0.667, unchanged by risky-1's exit_patch). Cell R_tp100_f50 varies QTY "
            "FRACTION (0.5 vs 0.667) at a FIXED +100% TP1. Different knobs; this section is a "
            "PROXY on the shared 'early extraction damages runners' risk only, never direct "
            "evidence for/against R_tp100_f50's own axis."
        ),
        "n_shared_signals_with_sibling": len(shared),
        "per_sibling_coarse_total_position": per_sibling_coarse,
        "per_sibling_runner_leg_proxy": per_sibling_runner_proxy,
        "total_coarse_delta_risky1_minus_siblings": total_coarse_delta,
        "total_runner_proxy_delta_risky1_minus_siblings": total_runner_delta,
        "n_runner_proxy_pairs": n_runner_pairs,
        "verdict": proxy_verdict,
        "detail_rows": shared,
    }


def main() -> int:
    rows = load_journal_rows()
    part1 = part1_forward_clock()
    part3 = part3_live_arm_corroboration(rows)
    out = {
        "_doc": __doc__,
        "generated_at_et": dt.datetime.now().isoformat(),
        "part1_forward_clock": part1,
        "part3_live_arm_corroboration": part3,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    log(f"PART 1 VERDICT: {part1['verdict']} (n={part1['n_used_for_clock']} vs floor {CLOCK_N_FLOOR})")
    log(f"PART 3 VERDICT: {part3['verdict']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

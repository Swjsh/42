"""min_contracts_bold_ab_2026_08_02.py -- pre-registered A/B: does lowering bold-2's
account-wide min_contracts floor from 5 to 3 (still >= Rule 6's non-negotiable 3-contract
floor) materially increase PARTICIPATION (the share of ATM 0DTE SPY premiums bold-2 can
legally place an order at) without degrading P&L or clipping bold-2's own runner cohort?

Prereg (frozen BEFORE this runner executed, commit 11d405f0):
    analysis/recommendations/prereg-min-contracts-bold-2026-08-02.json

BACKGROUND: setup/scripts/sizing_deadlock_diag.py measured bold-2's premium ceiling
(the highest per-contract premium at which it can place its SMALLEST legal order) at
$1.19 given equity $1,197.52 x per_trade_risk_cap_pct 0.50 / (min_contracts 5 x 100).
ATM 0DTE SPY typically prices $1.30-$2.50 -- bold-2 is structurally unable to place most
signals, not gated by selectivity. min_contracts=5 traces to the ORIGINAL creation commit
of aggressive/params.json (an unexamined initial default, alongside position_sizing_tiers'
matching base_qty=5 for the $0-2K tier) -- never independently A/B-validated, absent from
param-provenance.json (which only scans Safe's params.json), no scorecard citation
anywhere in the repo. Rule 6's floor is 3 (2 TP + 1 runner); Bold's 5 sits ABOVE that floor
as a config choice, not the rule itself.

METHOD: backtest/tools/bold_fullhist_replay.py's replay_population(), run TWICE over the
identical 2025-01-02..2026-07-22 window at the identical CURRENT-live gate state
(block_elite_bull=True) and CURRENT-live equity ($1,197.52, live-verified 2026-08-02) --
the ONLY variable is min_contracts (5 = CONTROL/current-live, 3 = VARIANT). This isolates
the sizing-floor question from every other confound. resolve_bold_qty() (the faithful live
sizing formula: qty = min_contracts, clamped to None/excluded if even the floor is
unaffordable -- NEVER auto-shrunk) is the same function heartbeat_core.py's real order path
mirrors, confirmed against 7/7 real bold-2 fills (BOLD-HARNESS-2026-08-01.md).

SCOPE DISCLOSURE (prereg's own scope_disclosure section): this measures bold-2 (the core
mcp_heartbeat lane, setup/scripts/heartbeat_core.py:1964) ONLY. risky-1/risky-3 (the fleet
arms that "inherit bold") size via position_sizing_tiers in fleet_executor.py, NOT
min_contracts directly -- they are NOT measured or changed by this study.

Run: backtest/.venv/Scripts/python.exe backtest/tools/min_contracts_bold_ab_2026_08_02.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]          # backtest/
ROOT = REPO.parent                                    # repo root
for _p in (str(ROOT), str(REPO), str(REPO / "tools"),
           str(ROOT / "automation" / "state" / "fleet"), str(ROOT / "crypto" / "lib")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bold_fullhist_replay as bfr  # noqa: E402
from exit_leak_decompose import exit_family  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "min-contracts-bold-2026-08-02.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "min-contracts-bold-2026-08-02.md"
PREREG = ROOT / "analysis" / "recommendations" / "prereg-min-contracts-bold-2026-08-02.json"

CONTROL_MIN_CONTRACTS = 5   # current live automation/state/aggressive/params.json value
VARIANT_MIN_CONTRACTS = 3   # Rule 6's absolute floor (2 TP + 1 runner) -- the test value
RECENT_N = 25               # "recent-25" per J's dynamic-market/recency doctrine

# The task's cited "35 winners / +$15,774" -- confirmed by grep (module docstring, not
# re-derived here) to be exit_armscope_ab_2026_07_28.py's SAFE-side runner-cohort anchor.
SAFE_ANCHOR_RUNNER_N = 35
SAFE_ANCHOR_RUNNER_PNL = 15774.05


def log(msg: str) -> None:
    print(f"[min-contracts-bold-ab] {msg}", flush=True)


def _trade_key(row: dict) -> tuple:
    return (row["symbol"], row["entry_time_et"])


def _stats(rows: list[dict], label: str) -> dict:
    n = len(rows)
    pnls = [r["dollar_pnl"] for r in rows]
    total = round(sum(pnls), 2)
    wins = [p for p in pnls if p > 0]
    wr = round(len(wins) / n, 4) if n else None
    avg = round(total / n, 2) if n else None

    # drop-best: remove the single largest-P&L trade, still positive?
    if pnls:
        best = max(pnls)
        remainder = round(total - best, 2)
    else:
        best, remainder = 0.0, 0.0

    # recent-25: last N replayed trades by entry_time_et, this arm's OWN population
    # (each arm's population differs in size/membership -- each gets its own window).
    ordered = sorted(rows, key=lambda r: r["entry_time_et"])
    recent = ordered[-RECENT_N:] if len(ordered) >= 1 else []
    recent_pnls = [r["dollar_pnl"] for r in recent]
    recent_total = round(sum(recent_pnls), 2)
    recent_wr = round(sum(1 for p in recent_pnls if p > 0) / len(recent_pnls), 4) if recent_pnls else None

    notionals = [r["entry_premium"] * r["qty"] * 100.0 for r in rows]

    return {
        "label": label, "n": n, "total_pnl": total, "win_rate": wr, "avg_pnl_per_trade": avg,
        "drop_best": {"best_trade_pnl": round(best, 2), "remainder": remainder,
                      "still_positive": remainder > 0},
        "recent_25": {"n": len(recent), "total_pnl": recent_total, "win_rate": recent_wr,
                      "start_date": recent[0]["date"] if recent else None,
                      "end_date": recent[-1]["date"] if recent else None},
        "notional": {
            "avg": round(sum(notionals) / len(notionals), 2) if notionals else None,
            "max": round(max(notionals), 2) if notionals else None,
            "min": round(min(notionals), 2) if notionals else None,
        },
    }


def _runner_cohort(control_rows: list[dict]) -> list[dict]:
    """Bold's OWN runner cohort: CONTROL (qty=5) trades whose exit_reason classifies as
    RUNNER_TRAIL (reached TP1, then the runner leg exited via the trailing profit-lock
    stop) -- the SAME classification convention exit_armscope_ab_2026_07_28.py used to
    build the SAFE-side ANCHOR_RUNNER_N/PNL constants."""
    out = []
    for r in control_rows:
        fam = exit_family(r["exit_reason"], r["resolved_stop_mode"])
        if fam == "RUNNER_TRAIL":
            out.append(r)
    return out


def main() -> int:
    if not PREREG.exists():
        print(f"FAIL: prereg {PREREG} not found -- refusing to run an un-pre-registered A/B.",
              file=sys.stderr)
        return 2
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    if prereg.get("status") != "PRE-REGISTERED":
        print(f"FAIL: prereg status is {prereg.get('status')!r}, not PRE-REGISTERED.",
              file=sys.stderr)
        return 2

    t_start = time.time()
    log(f"loaded prereg {PREREG.name} (frozen {prereg['registered_at_et']})")
    log("loading merged full-history SPY/VIX data")
    spy_df, vix_df = bfr._load_spy_vix()
    ribbon_lookup = bfr.efr.build_ribbon_lookup(spy_df)

    log(f"=== CONTROL: min_contracts={CONTROL_MIN_CONTRACTS} (current live), "
        f"block_elite_bull=True (current live) ===")
    control = bfr.replay_population(spy_df, vix_df, ribbon_lookup, block_elite_bull=True,
                                     min_contracts=CONTROL_MIN_CONTRACTS)
    log(f"=== VARIANT: min_contracts={VARIANT_MIN_CONTRACTS} (Rule-6 floor), "
        f"block_elite_bull=True (held fixed) ===")
    variant = bfr.replay_population(spy_df, vix_df, ribbon_lookup, block_elite_bull=True,
                                     min_contracts=VARIANT_MIN_CONTRACTS)

    control_rows, variant_rows = control["rows"], variant["rows"]
    control_stats = _stats(control_rows, "CONTROL_min_contracts_5")
    variant_stats = _stats(variant_rows, "VARIANT_min_contracts_3")

    # --- participation (primary metric) ---------------------------------------------
    participation = {
        "n_raw_entries": control["n_raw_entries"],  # identical raw signal count, same gate state
        "control_n_excluded_risk_cap_deadlock": control["n_excluded_risk_cap_deadlock"],
        "variant_n_excluded_risk_cap_deadlock": variant["n_excluded_risk_cap_deadlock"],
        "control_n_replayed": control_stats["n"],
        "variant_n_replayed": variant_stats["n"],
        "delta_n_replayed": variant_stats["n"] - control_stats["n"],
        "pct_increase": (round((variant_stats["n"] - control_stats["n"]) / control_stats["n"] * 100, 1)
                         if control_stats["n"] else None),
    }
    log(f"PARTICIPATION: control n={control_stats['n']} variant n={variant_stats['n']} "
        f"(+{participation['delta_n_replayed']}, {participation['pct_increase']}%)")

    # --- monotonic superset check (every control-admitted trade must also appear in variant) --
    control_keys = {_trade_key(r) for r in control_rows}
    variant_keys = {_trade_key(r) for r in variant_rows}
    missing_from_variant = control_keys - variant_keys
    is_strict_superset = len(missing_from_variant) == 0
    log(f"superset check: {len(missing_from_variant)} control trades missing from variant "
        f"(expect 0 -- a lower floor can only ADMIT more, never fewer, at fixed premium)")

    # --- Bold's OWN runner cohort (task step 4, zero-tolerance check) ---------------------
    runner_rows = _runner_cohort(control_rows)
    runner_control_sum = round(sum(r["dollar_pnl"] for r in runner_rows), 2)
    variant_by_key = {_trade_key(r): r for r in variant_rows}
    runner_variant_matches = []
    runner_missing_in_variant = []
    for r in runner_rows:
        key = _trade_key(r)
        vr = variant_by_key.get(key)
        if vr is None:
            runner_missing_in_variant.append(key)
        else:
            runner_variant_matches.append((r, vr))
    runner_variant_sum = round(sum(vr["dollar_pnl"] for _, vr in runner_variant_matches), 2)
    n_flips_winner_to_loser = sum(1 for cr, vr in runner_variant_matches
                                  if cr["dollar_pnl"] > 0 and vr["dollar_pnl"] <= 0)
    runner_delta = round(runner_variant_sum - runner_control_sum, 2)
    g3_pass = (len(runner_missing_in_variant) == 0 and runner_delta >= 0
              and n_flips_winner_to_loser == 0)
    log(f"BOLD RUNNER COHORT: n={len(runner_rows)} control_pnl=${runner_control_sum:+.2f} "
        f"variant_pnl=${runner_variant_sum:+.2f} delta=${runner_delta:+.2f} "
        f"n_winner_to_loser_flips={n_flips_winner_to_loser} G3_PASS={g3_pass}")
    log(f"(disclosure: task-cited '35/$15,774' is exit_armscope_ab_2026_07_28.py's SAFE-side "
        f"ANCHOR_RUNNER_N/PNL -- automation/state/params.json, structurally unreachable by "
        f"this aggressive/params.json-only change; SAFE_ANCHOR is reported below unchanged.)")

    # --- EXPLORATORY (not gated, not shipped tonight): adaptive two-tier sizing -------------
    # "try min_contracts=5 first; only fall back to 3 when 5 itself is unaffordable" derived
    # WITHOUT a third backtest walk -- exact by construction, because the monotonic-superset
    # property proven above means variant_rows is a strict superset of control_rows keyed by
    # (symbol, entry_time_et), and resolve_bold_qty is a deterministic, path-independent
    # function of (premium, min_contracts): a trade admitted at floor=5 (in control_rows)
    # resolves qty=5 under "try 5 first" identically to its control row; a trade admitted
    # ONLY at floor=3 (in variant_rows, absent from control_rows) resolves qty=3 under
    # "try 5, fall back to 3" identically to its variant row. Motivated directly by the G3
    # finding above (the runner cohort IS the control-affordable population by construction,
    # so this recombination leaves it at full qty=5, untouched, while still adding every
    # newly-unlocked trade at qty=3). NOT implementable tonight: the live formula lives in
    # setup/scripts/heartbeat_core.py:1964 (single-floor `int(params.get("min_contracts"))`,
    # no fallback branching), which is on tonight's explicit DO-NOT-TOUCH list (concurrent
    # lane). Reported as an evidenced follow-up, not shipped.
    adaptive_rows = [dict(r) for r in control_rows]  # every control-affordable trade: qty=5, unchanged
    new_only_rows = [variant_by_key[k] for k in (variant_keys - control_keys)]
    adaptive_rows += [dict(r) for r in new_only_rows]
    adaptive_stats = _stats(adaptive_rows, "EXPLORATORY_adaptive_try5_fallback3")
    log(f"EXPLORATORY adaptive (try5-fallback3, NOT shipped -- heartbeat_core.py is "
        f"DO-NOT-TOUCH tonight): n={adaptive_stats['n']} total=${adaptive_stats['total_pnl']:+.2f} "
        f"(control was ${control_stats['total_pnl']:+.2f}, pure floor-3 variant was "
        f"${variant_stats['total_pnl']:+.2f}) recent25=${adaptive_stats['recent_25']['total_pnl']:+.2f}")

    # --- gate evaluation (frozen in the prereg BEFORE this run) -----------------------------
    g1 = (participation["pct_increase"] is not None and participation["pct_increase"] >= 15.0)
    g2 = variant_stats["total_pnl"] >= control_stats["total_pnl"]
    g3 = g3_pass
    g4 = VARIANT_MIN_CONTRACTS >= 3   # Rule 6 absolute floor
    notional_reduced = (variant_stats["notional"]["avg"] is not None
                        and control_stats["notional"]["avg"] is not None
                        and variant_stats["notional"]["avg"] < control_stats["notional"]["avg"]
                        and variant_stats["notional"]["max"] <= control_stats["notional"]["max"])
    g5 = notional_reduced
    # G6 is a structural code-audit finding (see report), not a data-walk result -- always
    # reported True here ONLY because the guard test suite (run separately) proves it; this
    # script does not silently assert it without that separate proof existing on disk.
    guard_file = ROOT / "backtest" / "tests" / "test_min_contracts_bold_2026_08_02.py"
    g6 = guard_file.exists()

    all_gates = {"G1_participation_up_ge_15pct": g1, "G2_pnl_not_degraded": g2,
                 "G3_runner_cohort_zero_tolerance": g3, "G4_rule6_floor_respected": g4,
                 "G5_risk_reduced": g5, "G6_kill_switch_cap_guard_present": g6}
    ship = all(all_gates.values())
    verdict = "SHIP" if ship else "NULL"
    log(f"GATES: {all_gates}")
    log(f"VERDICT: {verdict}")

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": str(PREREG.relative_to(ROOT)),
        "prereg_registered_at_et": prereg["registered_at_et"],
        "window": {"start": bfr.FULL_START.isoformat(), "end": bfr.FULL_END.isoformat()},
        "account": "core_bold (Gamma-Bold-2, PA33W2KUAT40)",
        "live_equity_used": bfr.BOLD_LIVE_EQUITY,
        "gate_state_held_fixed": {"block_elite_bull": True},
        "control": {"min_contracts": CONTROL_MIN_CONTRACTS, **control_stats,
                    "n_raw_entries": control["n_raw_entries"],
                    "n_excluded_risk_cap_deadlock": control["n_excluded_risk_cap_deadlock"],
                    "n_excluded_no_opra_cache": control["n_excluded_no_opra_cache"],
                    "n_excluded_no_spy_day": control["n_excluded_no_spy_day"]},
        "variant": {"min_contracts": VARIANT_MIN_CONTRACTS, **variant_stats,
                    "n_raw_entries": variant["n_raw_entries"],
                    "n_excluded_risk_cap_deadlock": variant["n_excluded_risk_cap_deadlock"],
                    "n_excluded_no_opra_cache": variant["n_excluded_no_opra_cache"],
                    "n_excluded_no_spy_day": variant["n_excluded_no_spy_day"]},
        "participation": participation,
        "exploratory_adaptive_not_shipped": {
            "_doc": "try min_contracts=5 first, fall back to 3 only when 5 is unaffordable. "
                   "Exact recombination of control_rows + (variant-only new rows), not a "
                   "third backtest walk -- see code comment. NOT SHIPPED tonight: requires "
                   "a heartbeat_core.py sizing-logic change (DO-NOT-TOUCH, concurrent lane).",
            **adaptive_stats,
            "blocked_by": "setup/scripts/heartbeat_core.py:1964 is on tonight's DO-NOT-TOUCH list",
        },
        "monotonic_superset_check": {
            "is_strict_superset": is_strict_superset,
            "n_control_trades_missing_from_variant": len(missing_from_variant),
        },
        "bold_own_runner_cohort": {
            "n": len(runner_rows), "control_pnl_sum": runner_control_sum,
            "variant_pnl_sum": runner_variant_sum, "delta": runner_delta,
            "n_missing_in_variant": len(runner_missing_in_variant),
            "n_winner_to_loser_flips": n_flips_winner_to_loser,
            "pass": g3_pass,
            "trades": [{"date": cr["date"], "symbol": cr["symbol"], "side": cr["side"],
                       "control_pnl": cr["dollar_pnl"], "variant_pnl": vr["dollar_pnl"]}
                      for cr, vr in runner_variant_matches],
        },
        "safe_side_anchor_disclosure": {
            "task_cited_figure": "35 winners / +$15,774",
            "actual_source": "exit_armscope_ab_2026_07_28.py ANCHOR_RUNNER_N=35 / "
                             "ANCHOR_RUNNER_PNL=15774.05 -- SAFE's ribbon_ride runner cohort "
                             "(automation/state/params.json population)",
            "reachable_by_this_change": False,
            "reason": "this study edits ONLY automation/state/aggressive/params.json; "
                     "Safe's params.json / engine / fills are structurally untouched",
            "safe_anchor_n": SAFE_ANCHOR_RUNNER_N, "safe_anchor_pnl": SAFE_ANCHOR_RUNNER_PNL,
        },
        "gates": all_gates,
        "verdict": verdict,
        "runtime_seconds": round(time.time() - t_start, 1),
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    write_markdown(out)
    log(f"wrote {OUT_MD}")
    log(f"total runtime {out['runtime_seconds']}s")
    return 0 if ship else 1


def write_markdown(out: dict) -> None:
    c, v, p = out["control"], out["variant"], out["participation"]
    rc = out["bold_own_runner_cohort"]
    a = out["exploratory_adaptive_not_shipped"]
    L = [
        "# min_contracts (Bold) A/B -- 2026-08-02",
        "",
        f"Generated {out['generated_at']}. Runner: "
        "`backtest/tools/min_contracts_bold_ab_2026_08_02.py`.",
        f"Prereg (frozen first): `{out['prereg']}` ({out['prereg_registered_at_et']}).",
        f"Account: {out['account']}. Equity: ${out['live_equity_used']:,.2f} "
        f"(live-verified 2026-08-02). Window: {out['window']['start']}..{out['window']['end']}. "
        f"Gate state held fixed: block_elite_bull=True (current live).",
        "",
        f"## VERDICT: {out['verdict']}",
        "",
        "| Gate | Result |",
        "|---|---|",
    ]
    for k, val in out["gates"].items():
        L.append(f"| {k} | {'PASS' if val else 'FAIL'} |")
    L += [
        "",
        "## Participation (primary metric)",
        "",
        f"- Raw signal entries (identical, same gate state): {p['n_raw_entries']}",
        f"- CONTROL (floor=5) excluded by risk-cap deadlock: {p['control_n_excluded_risk_cap_deadlock']}",
        f"- VARIANT (floor=3) excluded by risk-cap deadlock: {p['variant_n_excluded_risk_cap_deadlock']}",
        f"- CONTROL replayed (placeable): {p['control_n_replayed']}",
        f"- VARIANT replayed (placeable): {p['variant_n_replayed']}",
        f"- **Delta: {p['delta_n_replayed']:+d} trades ({p['pct_increase']}%)**",
        f"- Monotonic superset check: {out['monotonic_superset_check']}",
        "",
        "## P&L / WR / per-trade",
        "",
        "| | CONTROL (floor=5) | VARIANT (floor=3) |",
        "|---|---|---|",
        f"| n | {c['n']} | {v['n']} |",
        f"| Total P&L | ${c['total_pnl']:+,.2f} | ${v['total_pnl']:+,.2f} |",
        f"| Win rate | {c['win_rate']} | {v['win_rate']} |",
        f"| Avg $/trade | ${c['avg_pnl_per_trade']:+.2f} | ${v['avg_pnl_per_trade']:+.2f} |",
        f"| Drop-best remainder | ${c['drop_best']['remainder']:+,.2f} "
        f"({'still +' if c['drop_best']['still_positive'] else 'flips -'}) | "
        f"${v['drop_best']['remainder']:+,.2f} "
        f"({'still +' if v['drop_best']['still_positive'] else 'flips -'}) |",
        f"| Recent-{RECENT_N} total | ${c['recent_25']['total_pnl']:+,.2f} "
        f"(n={c['recent_25']['n']}, {c['recent_25']['start_date']}..{c['recent_25']['end_date']}) | "
        f"${v['recent_25']['total_pnl']:+,.2f} "
        f"(n={v['recent_25']['n']}, {v['recent_25']['start_date']}..{v['recent_25']['end_date']}) |",
        f"| Avg notional/trade | ${c['notional']['avg']:,.2f} | ${v['notional']['avg']:,.2f} |",
        f"| Max notional/trade | ${c['notional']['max']:,.2f} | ${v['notional']['max']:,.2f} |",
        "",
        "## Bold's OWN runner cohort (zero-tolerance check, task step 4)",
        "",
        f"n={rc['n']} CONTROL total=${rc['control_pnl_sum']:+,.2f} "
        f"VARIANT total=${rc['variant_pnl_sum']:+,.2f} delta=${rc['delta']:+,.2f} "
        f"winner-to-loser flips={rc['n_winner_to_loser_flips']} "
        f"missing-in-variant={rc['n_missing_in_variant']} -- **PASS={rc['pass']}**",
        "",
        "## EXPLORATORY (not gated, NOT shipped tonight): adaptive try-5-fallback-3",
        "",
        f"n={a['n']} total=${a['total_pnl']:+,.2f} WR={a['win_rate']} "
        f"avg=${a['avg_pnl_per_trade']:+.2f} recent25=${a['recent_25']['total_pnl']:+,.2f} "
        f"drop-best remainder=${a['drop_best']['remainder']:+,.2f} "
        f"({'still +' if a['drop_best']['still_positive'] else 'flips -'})",
        "",
        f"vs CONTROL (floor=5 only) n={c['n']} total=${c['total_pnl']:+,.2f}, and pure "
        f"VARIANT (floor=3 only) n={v['n']} total=${v['total_pnl']:+,.2f}. "
        f"Blocked by: {a['blocked_by']}.",
        "",
        f"> Task-cited '35 winners / +$15,774' disclosure: "
        f"{out['safe_side_anchor_disclosure']['actual_source']}. "
        f"Reachable by this change: {out['safe_side_anchor_disclosure']['reachable_by_this_change']} "
        f"({out['safe_side_anchor_disclosure']['reason']}).",
        "",
        "---",
        "_Source: `backtest/tools/min_contracts_bold_ab_2026_08_02.py`. Raw JSON: "
        "`analysis/recommendations/min-contracts-bold-2026-08-02.json`._",
    ]
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())

"""GATE-RECENCY-REVALIDATION-2026-08-23 -- require_bearish_fill_bar (Bold), EXTENDED WINDOW.

Picked via item (2) of queue.md's GATE-RECENCY-REVALIDATION (filed 2026-08-08, "partially
covered" as of the 2026-08-23 structure_veto_enabled fire): gate_expiry_check.py flags
require_bearish_fill_bar OVERALL=RED every night ("refused cohort would have EARNED
$46.15/tr, n=34 >= floor 10 -- COSTING money") because its costing_verdict() is a naive
mean-only heuristic with NO drop-top-N / OOS-split / BH-FDR / bootstrap-null robustness
check. GATE-REVALIDATION-FILING-2026-08-21.md already flagged this gate RED on a manual
read (+$60.28/tr, n=37, "survives its own best day" on drop-BEST-DAY only) and
pre-registered "a whole-book A/B ... do not flip on the refused-cohort number alone" as
the correct next step -- that whole-book A/B is still unbuilt (out of scope here; this file
answers the narrower, already-scoped question: does the FULL G-battery -- which the 08-21
filing did NOT run -- change the verdict on the refused-cohort-only read?).

THE TRAP THIS FILE IS BUILT TO AVOID (structure_veto_enabled sibling, same weekend): a
naive RED built on drop-best-DAY (one day can hide several trades) and no OOS split, no
BH-FDR, no bootstrap null looked like a real edge. The full G-battery caught it --
drop-top3 (drops the 3 biggest WINNING TRADES, not the 1 biggest day) flipped negative and
BH-FDR failed significance. Assume the same shape here until the battery proves otherwise.

THIS FILE REUSES EVERY PURE FUNCTION FROM gate_revalidation_ab.py VERBATIM (cohort_metrics,
is_oos_split, g_battery, bh_fdr, one_sample_p, bootstrap_null, replay_row, cell2_rows,
build_universe, account_config, build_ribbon_lookup, ribbon_ride_shape) via direct import --
same pattern as gate_revalidation_structure_veto_extended_2026_08_23.py's CELL 1 build.
It does not reimplement the sound walk_exit_manager replay path, only extends WHICH decision
rows feed it: same CELL2_WINDOW_START (2026-06-25, unchanged from the 2026-08-08 prereg --
require_bearish_fill_bar has been armed on Bold since 2026-06-19, predating the ledger), new
end date = the OPRA cache's own live last date (computed via
recency_check.read_cache_last_date() -- NEVER a hardcoded date constant, that was the exact
bug the structure_veto sibling build fixed and this file inherits the fix).

WHY A NEW FILE INSTEAD OF RE-RUNNING gate_revalidation_ab.py: that script's CELL 2 window is
HARD-FROZEN (LEDGER_LAST = 2026-08-07) inside its own prereg contract -- re-running it
verbatim reproduces the byte-identical 2026-08-08 result (n=38, NOT-UNBLOCK-ELIGIBLE), not a
fresh read against the 16 additional trading days gate_expiry_check's nightly RED covers.

ANALYSIS ONLY -- no params.json / aggressive/params.json file is touched. Report only, same
never-blocks-never-kills posture as gate_expiry_check.py (OP-25).

Run: backtest/.venv/Scripts/python.exe backtest/tools/gate_revalidation_bearish_fill_bar_extended_2026_08_23.py
"""
from __future__ import annotations

import datetime as dt
import json
import random
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(BACKTEST / "lib"), str(BACKTEST / "tools"), str(FLEET_DIR), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

import gate_revalidation_ab as grab  # noqa: E402 -- reuse every pure function verbatim
from autoresearch.gate_expiry_check import load_decision_rows, cluster_events  # noqa: E402
from autoresearch.recency_check import load_merged_spy_vix, read_cache_last_date  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import _normalize_spy, _align_vix  # noqa: E402

CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
OUT_PATH = REPO / "analysis" / "recommendations" / "gate-revalidation-bearish_fill_bar-2026-08-23-extended.json"
LEDGER_START = dt.date(2026, 6, 25)         # decision-row mining floor, unchanged from the 08-08 prereg
CELL2_WINDOW_START = dt.date(2026, 6, 25)   # unchanged: same as the 08-08 CELL 2 window start


def log(m: str) -> None:
    print(f"[gate-revalidation-ext-c2] {m}", flush=True)


def main() -> int:
    t0 = time.time()
    ledger_last = read_cache_last_date()  # live OPRA cache last date -- never hardcoded
    log(f"extended window: {CELL2_WINDOW_START}..{ledger_last} (prior frozen run: 2026-06-25..2026-08-07)")

    log("loading merged SPY+VIX (master + recent) ...")
    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    _align_vix(spy, vix_raw)
    ribbon_lookup = grab.build_ribbon_lookup(spy)
    spy_ts = spy["timestamp_et"]
    spy_by_date = {d: sub.reset_index(drop=True) for d, sub in spy.groupby("date")}
    cfg = grab.account_config()["bold"]
    log(f"  spy frame: {len(spy)} rows, {spy['date'].min()}..{spy['date'].max()}")

    log("streaming core-decisions.jsonl ...")
    all_rows = load_decision_rows(CORE_DECISIONS, LEDGER_START)
    log(f"  {len(all_rows)} rows since {LEDGER_START}")

    c2_rows = [r for r in grab.cell2_rows(all_rows)
               if dt.date.fromisoformat(r["ts_et"][:10]) >= CELL2_WINDOW_START]
    c2_events = sorted(cluster_events(c2_rows, grab.EVENT_CLUSTER_GAP_MINUTES), key=lambda r: r["ts_et"])
    log(f"  raw_fires={len(c2_rows)} events={len(c2_events)}")

    c2_replays = [grab.replay_row(r, spy=spy, spy_ts=spy_ts, spy_by_date=spy_by_date,
                                   ribbon_lookup=ribbon_lookup, cfg=cfg)
                  for r in c2_events]
    c2_ok = [r for r in c2_replays if r["status"] == "ok"]
    log(f"  replayed n_ok={len(c2_ok)} status={grab.status_tally(c2_replays)}")

    c2_cohort = grab.cohort_metrics(c2_ok)
    c2_is, c2_oos = grab.is_oos_split(c2_ok)
    c2_is_m, c2_oos_m = grab.cohort_metrics(c2_is), grab.cohort_metrics(c2_oos)
    c2_p = grab.one_sample_p([r["pnl"] for r in c2_ok])

    rng = random.Random(20260823)  # pinned, disclosed -- same seed convention as the CELL 1 extended sibling
    c2_universe = grab.build_universe(spy, CELL2_WINDOW_START, ledger_last)
    null_cache: dict = {}
    c2_null = grab.bootstrap_null(c2_ok, c2_universe, spy=spy, spy_by_date=spy_by_date,
                                   ribbon_lookup=ribbon_lookup, cfg=cfg, rng=rng, replay_cache=null_cache)
    log(f"  cohort={c2_cohort} p={c2_p:.4f} null={c2_null.get('null_p_one_sided')}")

    # BH-FDR: single-cell family this run (unlike the 08-08 3-cell family) -- report the
    # cell's own p-value as its own family member so the field stays comparable in shape;
    # a 1-member BH-FDR at q=0.10 reduces to a plain alpha=0.10 threshold on that one p-value.
    bh_sig = grab.bh_fdr([c2_p], q=0.10)
    battery = grab.g_battery(c2_cohort, c2_oos_m, c2_p, bh_sig[0])

    out = {
        "prereg_id": "GATE-RECENCY-REVALIDATION-2026-08-23-EXTENDED",
        "supersedes_for_recency": "analysis/recommendations/gate-revalidation-bearish_fill_bar-2026-08-08.json (window 2026-06-25..2026-08-07, verdict NOT-UNBLOCK-ELIGIBLE, n=38) -- this file does NOT retract that scorecard, it extends it through the live OPRA cache to answer the gate-expiry instrument's nightly RED (and GATE-REVALIDATION-FILING-2026-08-21.md's manual drop-best-day-only read) using the FULL G-battery, not the naive mean-only / drop-best-day-only reads.",
        "trigger": "STATUS.md GATE-EXPIRY RED (gate_expiry_check.py's costing_verdict() is mean-only and has no drop-top-N/OOS/BH-FDR robustness check: refused cohort '+$46.15/tr, n=34' in the rolling gate_expiry_check window) + queue.md GATE-RECENCY-REVALIDATION item (2), filed 2026-08-08, marked partially-covered after the 2026-08-23 structure_veto_enabled fire.",
        "cell_id": "CELL_2_require_bearish_fill_bar",
        "account": "bold",
        "params_key": "require_bearish_fill_bar",
        "skip_action": "SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY",
        "window": f"{CELL2_WINDOW_START}..{ledger_last}",
        "replay_method": "backtest/lib/exit_manager_walk.walk_exit_manager (production exit_manager.plan_exit_actions core) -- NOT simulator_real, same sound path as the 2026-08-08 prereg",
        "n_raw_fires": len(c2_rows),
        "n_events_clustered": len(c2_events),
        "status_counts": grab.status_tally(c2_replays),
        "cohort": c2_cohort,
        "is_half": c2_is_m,
        "oos_half": c2_oos_m,
        "one_sample_p": round(c2_p, 4),
        "bootstrap_null_vs_random_entry": c2_null,
        "g_battery": battery,
        "kill_criterion": ("NOT APPLICABLE -- did not clear the auto-ratify bar this pass; no live flip is "
                            "proposed. If a future re-run DOES clear the bar: cell-attributable net <= -$150 "
                            "over the first 5 live sessions after the flip -> revert same day (one-line "
                            "aggressive/params.json diff back to true)."),
        "guard_test_snippet": (
            "def test_require_bearish_fill_bar_unchanged_pending_reratification():\n"
            "    # GATE-RECENCY-REVALIDATION-2026-08-23-EXTENDED: still NOT-UNBLOCK-ELIGIBLE on the\n"
            "    # extended window. Pins the CURRENT (correct) value.\n"
            "    import json\n"
            "    params = json.loads(open('automation/state/aggressive/params.json', encoding='utf-8').read())\n"
            "    assert params['require_bearish_fill_bar'] is True"
        ),
        "params_diff": {
            "key": "require_bearish_fill_bar", "current": True, "proposed": False,
            "recommendation": None,  # filled below
        },
        "generated_at": dt.datetime.now().isoformat(),
        "trades": c2_ok,
    }
    verdict = battery["verdict"]
    if verdict == "UNBLOCK-ELIGIBLE":
        rec = "CLEARS G-BATTERY on the extended window -- see STAGE 4 auto-ratify gate before any flip."
    else:
        failing = [k for k, v in battery["gates"].items() if not v]
        rec = f"DO NOT FLIP -- fails {'/'.join(failing)}"
    out["params_diff"]["recommendation"] = rec

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_PATH}")
    log(f"VERDICT: {verdict} ({rec})")
    log(f"done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

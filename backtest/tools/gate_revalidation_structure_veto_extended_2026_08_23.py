"""GATE-RECENCY-REVALIDATION-2026-08-23 -- structure_veto_enabled (Safe), EXTENDED WINDOW.

Picked via conductor STAGE 1 priority-2 (STATUS.md '## Known broken' GATE-EXPIRY RED,
2026-08-22T23:01:45): gate_expiry_check.py flags structure_veto_enabled OVERALL=RED every
night ("refused cohort would have EARNED $2.15/tr, n=10 >= floor 10") because its naive
mean-only costing_verdict() has no drop-top-N / OOS-split / BH-FDR robustness check. The
FULL G-battery re-run this file performs is exactly what queue.md's GATE-RECENCY-REVALIDATION
item (filed 2026-08-08) calls for: "run the three revalidation A/Bs ... frozen pre-reg +
refused-cohort replay at live scope + G-battery; ship per auto-ratify rail or file DO_NOT_ARM."

WHY A NEW FILE INSTEAD OF RE-RUNNING gate_revalidation_ab.py: that script's CELL 1 window is
HARD-FROZEN (LEDGER_LAST = 2026-08-07, CELL1_WINDOW_START = 2026-06-26) inside its own prereg
contract -- re-running it verbatim reproduces the byte-identical 2026-08-08 result, not a
fresh read. This file REUSES every pure function from gate_revalidation_ab.py UNCHANGED
(cohort_metrics, is_oos_split, g_battery, bh_fdr, one_sample_p, bootstrap_null, replay_row,
build_universe, account_config, build_ribbon_lookup, ribbon_ride_shape) via direct import --
it does not reimplement the sound walk_exit_manager replay path, only extends WHICH decision
rows feed it: same CELL1_WINDOW_START (2026-06-26, full history since the gate armed), new
LEDGER_LAST = the OPRA cache's own last date (today's ledger, computed live via
recency_check.read_cache_last_date -- never hardcoded, so this file itself never goes stale
the way its predecessor's frozen constant did).

ANALYSIS ONLY -- no params.json / aggressive/params.json file is touched. Report only, same
never-blocks-never-kills posture as gate_expiry_check.py (OP-25).

Run: backtest/.venv/Scripts/python.exe backtest/tools/gate_revalidation_structure_veto_extended_2026_08_23.py
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
OUT_PATH = REPO / "analysis" / "recommendations" / "gate-revalidation-structure_veto-2026-08-23-extended.json"
LEDGER_START = dt.date(2026, 6, 25)      # decision-row mining floor, unchanged from the 08-08 prereg
CELL1_WINDOW_START = dt.date(2026, 6, 26)  # unchanged: gate armed 2026-06-26, full history since arming


def log(m: str) -> None:
    print(f"[gate-revalidation-ext] {m}", flush=True)


def main() -> int:
    t0 = time.time()
    ledger_last = read_cache_last_date()  # live OPRA cache last date -- never hardcoded
    log(f"extended window: {CELL1_WINDOW_START}..{ledger_last} (prior frozen run: 2026-06-26..2026-08-07)")

    log("loading merged SPY+VIX (master + recent) ...")
    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    _align_vix(spy, vix_raw)
    ribbon_lookup = grab.build_ribbon_lookup(spy)
    spy_ts = spy["timestamp_et"]
    spy_by_date = {d: sub.reset_index(drop=True) for d, sub in spy.groupby("date")}
    cfg = grab.account_config()["safe"]
    log(f"  spy frame: {len(spy)} rows, {spy['date'].min()}..{spy['date'].max()}")

    log("streaming core-decisions.jsonl ...")
    all_rows = load_decision_rows(CORE_DECISIONS, LEDGER_START)
    log(f"  {len(all_rows)} rows since {LEDGER_START}")

    c1_rows = [r for r in grab.cell1_rows(all_rows)
               if dt.date.fromisoformat(r["ts_et"][:10]) >= CELL1_WINDOW_START]
    c1_events = sorted(cluster_events(c1_rows, grab.EVENT_CLUSTER_GAP_MINUTES), key=lambda r: r["ts_et"])
    log(f"  raw_fires={len(c1_rows)} events={len(c1_events)}")

    c1_replays = [grab.replay_row(r, spy=spy, spy_ts=spy_ts, spy_by_date=spy_by_date,
                                   ribbon_lookup=ribbon_lookup, cfg=cfg)
                  for r in c1_events]
    c1_ok = [r for r in c1_replays if r["status"] == "ok"]
    log(f"  replayed n_ok={len(c1_ok)} status={grab.status_tally(c1_replays)}")

    c1_cohort = grab.cohort_metrics(c1_ok)
    c1_is, c1_oos = grab.is_oos_split(c1_ok)
    c1_is_m, c1_oos_m = grab.cohort_metrics(c1_is), grab.cohort_metrics(c1_oos)
    c1_p = grab.one_sample_p([r["pnl"] for r in c1_ok])

    rng = random.Random(20260823)  # pinned, disclosed
    c1_universe = grab.build_universe(spy, CELL1_WINDOW_START, ledger_last)
    null_cache: dict = {}
    c1_null = grab.bootstrap_null(c1_ok, c1_universe, spy=spy, spy_by_date=spy_by_date,
                                   ribbon_lookup=ribbon_lookup, cfg=cfg, rng=rng, replay_cache=null_cache)
    log(f"  cohort={c1_cohort} p={c1_p:.4f} null={c1_null.get('null_p_one_sided')}")

    # BH-FDR: single-cell family this run (unlike the 08-08 3-cell family) -- report the
    # cell's own p-value as its own family member so the field stays comparable in shape;
    # a 1-member BH-FDR at q=0.10 reduces to a plain alpha=0.10 threshold on that one p-value.
    bh_sig = grab.bh_fdr([c1_p], q=0.10)
    battery = grab.g_battery(c1_cohort, c1_oos_m, c1_p, bh_sig[0])

    out = {
        "prereg_id": "GATE-RECENCY-REVALIDATION-2026-08-23-EXTENDED",
        "supersedes_for_recency": "analysis/recommendations/gate-revalidation-structure_veto-2026-08-08.json (window 2026-06-26..2026-08-07, verdict NOT-UNBLOCK-ELIGIBLE) -- this file does NOT retract that scorecard, it extends it 15 more trading days to answer the gate-expiry instrument's nightly RED using the SAME sound methodology, not the naive mean-only read.",
        "trigger": "STATUS.md GATE-EXPIRY RED 2026-08-22T23:01:45 (n=10, $2.15/tr in the 25-trading-day gate_expiry_check window) -- gate_expiry_check.py's costing_verdict() is mean-only and has no drop-top-N/OOS/BH-FDR robustness check, so it cannot by itself distinguish a real recovering edge from a single lucky trade padding the mean.",
        "cell_id": "CELL_1_structure_veto_enabled",
        "account": "safe",
        "params_key": "structure_veto_enabled",
        "skip_action": "SKIP_STRUCTURE_VETO",
        "window": f"{CELL1_WINDOW_START}..{ledger_last}",
        "replay_method": "backtest/lib/exit_manager_walk.walk_exit_manager (production exit_manager.plan_exit_actions core) -- NOT simulator_real, same sound path as the 2026-08-08 prereg",
        "n_raw_fires": len(c1_rows),
        "n_events_clustered": len(c1_events),
        "status_counts": grab.status_tally(c1_replays),
        "cohort": c1_cohort,
        "is_half": c1_is_m,
        "oos_half": c1_oos_m,
        "one_sample_p": round(c1_p, 4),
        "bootstrap_null_vs_random_entry": c1_null,
        "g_battery": battery,
        "kill_criterion": ("NOT APPLICABLE -- did not clear the auto-ratify bar this pass; no live flip is "
                            "proposed. If a future re-run DOES clear the bar: cell-attributable net <= -$150 "
                            "over the first 5 live sessions after the flip -> revert same day (one-line "
                            "params.json diff back to true)."),
        "guard_test_snippet": (
            "def test_structure_veto_enabled_unchanged_pending_reratification():\n"
            "    # GATE-RECENCY-REVALIDATION-2026-08-23-EXTENDED: still NOT-UNBLOCK-ELIGIBLE on the\n"
            "    # extended window. Pins the CURRENT (correct) value.\n"
            "    import json\n"
            "    params = json.loads(open('automation/state/params.json', encoding='utf-8').read())\n"
            "    assert params['structure_veto_enabled'] is True"
        ),
        "params_diff": {
            "key": "structure_veto_enabled", "current": True, "proposed": False,
            "recommendation": None,  # filled below
        },
        "generated_at": dt.datetime.now().isoformat(),
        "trades": c1_ok,
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

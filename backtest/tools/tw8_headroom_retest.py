"""tw8_headroom_retest.py -- T-W8 HEADROOM + RETEST entry-candidate study.

Runs the FROZEN pre-registration (analysis/recommendations/headroom-retest-preregistration.json)
-- no re-picks, no new cells added after this file is written. Tests two candidate
entry-quality fixes for the 2026-07-09 BULLISH_RECLAIM near-miss (the fleet's entry buys
the FIRST break above a reclaimed level even when documented resistance sits directly
overhead):

  CANDIDATE H (headroom gate): SKIP signals whose distance to the next OPPOSING level
    (resistance for calls, support for puts) is below a threshold in {0.5,0.75,1.0,1.5}
    dollars of SPY. Reports kept-cohort AND skipped-cohort P&L, and a random-skip NULL
    (same kept-fraction, real signals sampled at random) so a pass requires beating
    both CONTROL and "just trading fewer signals at random".

  CANDIDATE R (retest-limit entry): instead of a market fill on the confirmation bar,
    rest a limit AT the reclaimed/rejected level for up to `patience` in {3,6} option
    bars; filled only if a later bar genuinely retests the level (SPY low<=level for
    calls, high>=level for puts); unfilled = MISSED, priced at $0 and counted in the
    denominator (T3 convention -- a real cost, never excluded).

REUSES, does not reinvent:
  * _signal_cache.py            -- exploratory signal set (load_or_build_signals)
  * t5_confirmatory_matrix.py   -- fresh-slice build/reuse (build_fresh_slice, verified not
                                    rebuilt), CONTROL_SHAPE / EXIT_A_SHAPE, TIME_STOP
  * t4_exit_matrix.py           -- _load_bars / replay / battery / band_of (the LIVE
                                    exit_manager replay engine T3/T4/T5 already validated)
  * tw8_level_context.py        -- NEW this study: lib/levels.py detector (orchestrator's
                                    exact per-day-frozen convention), trigger-bar recovery,
                                    headroom computation (C6 look-ahead safe by construction)

Both exit shapes (CONTROL + exit-A) x both windows (exploratory BURNED, fresh HONEST,
2026-07-09 excluded from both) x each candidate's own parameter grid. ANALYSIS ONLY --
writes only to analysis/recommendations/; never touches strategies.py, params.json,
waivers, or any trading-path file. $0, local OPRA cache, no network.

Run: backtest/.venv/Scripts/python.exe backtest/tools/tw8_headroom_retest.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
import statistics as st
import sys
import time as _time_mod
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "automation" / "state" / "fleet"))

import t4_exit_matrix as t4              # noqa: E402  (replay, band_of, battery, _load_bars, QTY, BANDS)
import t5_confirmatory_matrix as t5      # noqa: E402  (CONTROL_SHAPE, EXIT_A_SHAPE, TIME_STOP, fresh-slice build/reuse)
import _signal_cache as sc               # noqa: E402  (exploratory signal set: load_or_build_signals)
import tw8_level_context as lc           # noqa: E402  (level detector, trigger-bar recovery, headroom)

PREREG = REPO / "analysis" / "recommendations" / "headroom-retest-preregistration.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "headroom-retest-tw8.json"

EXPECTED_EXPLORATORY_SHA16 = "b5e8931994b9d34b"   # sha256 of RAW FILE BYTES (signal-set.json)
EXPECTED_FRESH_SHA16 = "d10e1a3a51cbf155"          # sha256 of the KEPT signals list content (t5 convention)
EXPECTED_PREREG_VERSION = 1

H_THRESHOLDS = [0.5, 0.75, 1.0, 1.5]
R_PATIENCE = [3, 6]
NULL_TRIALS = 1000
NULL_SEED = 20260709
SMALL_N_THRESHOLD = 8

TIME_STOP = t5.TIME_STOP
QTY = t4.QTY
CONTROL_SHAPE = t5.CONTROL_SHAPE
EXIT_A_SHAPE = t5.EXIT_A_SHAPE
EXIT_SHAPES = {"CONTROL": CONTROL_SHAPE, "exit-A": EXIT_A_SHAPE}

EXPLORATORY_START = sc.START
EXPLORATORY_END = sc.END
FRESH_START_WARMUP = t5.FRESH_START_WARMUP
FRESH_END = t5.FRESH_END
TODAY_EXCLUDED = dt.date(2026, 7, 9)


# ---------------------------------------------------------------------------------------------
# PREFLIGHT
# ---------------------------------------------------------------------------------------------
def preflight() -> dict:
    exp_bytes = sc.CACHE.read_bytes()
    exp_sha16 = hashlib.sha256(exp_bytes).hexdigest()[:16]

    fresh_raw = json.loads(t5.FRESH_SIGNAL_SET.read_text(encoding="utf-8"))
    fresh_payload = json.dumps(fresh_raw["signals"], sort_keys=True, default=str)
    fresh_sha16 = hashlib.sha256(fresh_payload.encode("utf-8")).hexdigest()[:16]

    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    ver = preg.get("version")

    return {
        "exploratory_sha256_16": exp_sha16,
        "exploratory_hash_ok": exp_sha16 == EXPECTED_EXPLORATORY_SHA16,
        "fresh_sha256_16": fresh_sha16,
        "fresh_hash_ok": fresh_sha16 == EXPECTED_FRESH_SHA16,
        "preregistration_version": ver,
        "preregistration_version_ok": ver == EXPECTED_PREREG_VERSION,
    }


# ---------------------------------------------------------------------------------------------
# SIGNAL PREP (level-enriched)
# ---------------------------------------------------------------------------------------------
def prepare_window(signals_enriched: list[dict]) -> tuple[list[dict], int]:
    """t4/t5's prepare_signals, extended with level context. Any date w/ no admitted entry
    (bar_time<9:35 all day etc.) already excluded upstream by tw8_level_context."""
    prepared, miss = [], 0
    for s in signals_enriched:
        bars = t4._load_bars(s)
        if not bars:
            miss += 1
            continue
        entry_premium = bars[0][1]
        if entry_premium <= 0:
            miss += 1
            continue
        prepared.append({
            "date": dt.date.fromisoformat(s["date"]), "direction": s["direction"], "side": s["side"],
            "entry_premium": entry_premium, "band": t4.band_of(entry_premium), "bars": bars,
            "trigger_level": s.get("trigger_level"),
            "next_opposing_level": s.get("next_opposing_level"),
            "headroom_dollars": s.get("headroom_dollars"),
            "level_context_status": s.get("level_context_status"),
        })
    return prepared, miss


def split_by_headroom(prepared: list[dict], threshold: float) -> tuple[list[dict], list[dict]]:
    kept, skipped = [], []
    for p in prepared:
        h = p["headroom_dollars"]
        (kept if (h is None or h >= threshold) else skipped).append(p)
    return kept, skipped


def eligible_for_r(prepared: list[dict]) -> list[dict]:
    return [p for p in prepared if p.get("trigger_level") is not None]


# ---------------------------------------------------------------------------------------------
# CANDIDATE R -- retest-limit entry
# ---------------------------------------------------------------------------------------------
def retest_fill(opt_bars: list, spy_by_time: dict, trigger_level: float, side: str,
                 patience: int) -> tuple[dict | None, int]:
    """Scan up to `patience` OPTION bars (index 0 = the recorded confirmation bar, same
    indexing convention as t3_entry_matrix.entry_fill). Filled if the SPY bar AT THE SAME
    TIMESTAMP retests trigger_level (low<=level for calls, high>=level for puts). Fill
    premium = that option bar's OPEN (frictionless). Returns (fill_or_None, n_spy_lookup_miss)."""
    pat = min(patience, len(opt_bars))
    n_lookup_miss = 0
    for i in range(pat):
        btime = opt_bars[i][0]
        row = spy_by_time.get(btime)
        if row is None:
            n_lookup_miss += 1
            continue
        touched = (row.low <= trigger_level) if side == "C" else (row.high >= trigger_level)
        if touched:
            return {"entry": opt_bars[i][1], "fill_idx": i}, n_lookup_miss
    return None, n_lookup_miss


def r_replay(eligible: list[dict], patience: int, exit_shape: dict,
             spy_by_time_cache: dict) -> tuple[list[dict], int]:
    trades = []
    n_lookup_miss_total = 0
    for p in eligible:
        spy_by_time = spy_by_time_cache[p["date"]]
        f, miss_n = retest_fill(p["bars"], spy_by_time, p["trigger_level"], p["side"], patience)
        n_lookup_miss_total += miss_n
        if f is None:
            trades.append({"date": p["date"], "direction": p["direction"], "band": p["band"],
                           "pnl": 0.0, "missed": True})
            continue
        sub = p["bars"][f["fill_idx"]:]
        r = t4.replay(f["entry"], sub, p["side"], exit_shape, TIME_STOP)
        trades.append({"date": p["date"], "direction": p["direction"], "band": p["band"],
                       "pnl": r["pnl"], "missed": False})
    return trades, n_lookup_miss_total


# ---------------------------------------------------------------------------------------------
# NULL BASELINE -- random-skip (H only)
# ---------------------------------------------------------------------------------------------
def null_distribution(pnl_pool: list[float], k: int, n_trials: int, seed: int) -> dict | None:
    n = len(pnl_pool)
    if k <= 0 or k > n:
        return None
    rng = random.Random(seed)
    idx_pool = list(range(n))
    means = []
    for _ in range(n_trials):
        sample = rng.sample(idx_pool, k)
        means.append(sum(pnl_pool[j] for j in sample) / k)
    return {
        "n_trials": n_trials, "k": k,
        "mean_of_means": round(sum(means) / len(means), 4),
        "stdev": round(st.pstdev(means), 4) if len(means) > 1 else 0.0,
        "min": round(min(means), 2), "max": round(max(means), 2),
    }


# ---------------------------------------------------------------------------------------------
# CELL METRICS
# ---------------------------------------------------------------------------------------------
def _battery_safe(trades: list[dict]) -> dict:
    return t4.battery(trades)


def h_cell(prepared: list[dict], threshold: float, exit_name: str, exit_shape: dict,
           control_all_battery: dict, exit_pnl_pool: list[float]) -> dict:
    kept, skipped = split_by_headroom(prepared, threshold)

    kept_trades = t5.replay_market(kept, exit_shape)
    kept_battery = _battery_safe(kept_trades)

    control_same_kept_trades = t5.replay_market(kept, CONTROL_SHAPE)
    control_same_kept_battery = _battery_safe(control_same_kept_trades)

    skipped_trades_ctrl = t5.replay_market(skipped, CONTROL_SHAPE)
    skipped_battery_ctrl = _battery_safe(skipped_trades_ctrl)

    n = kept_battery.get("n", 0)
    exp = kept_battery.get("expectancy")
    delta_full = (round(exp - control_all_battery["expectancy"], 2)
                  if n and control_all_battery.get("n") else None)
    delta_same = (round(exp - control_same_kept_battery["expectancy"], 2)
                  if n and control_same_kept_battery.get("n") else None)

    null = null_distribution(exit_pnl_pool, k=n, n_trials=NULL_TRIALS, seed=NULL_SEED)
    beats_null = (exp is not None and null is not None and exp > null["mean_of_means"])

    skip_n = skipped_battery_ctrl.get("n", 0)
    skip_exp = skipped_battery_ctrl.get("expectancy")
    kept_ctrl_exp = control_same_kept_battery.get("expectancy")
    skipped_net_negative = None
    if skip_n > 0 and skip_exp is not None:
        skipped_net_negative = bool(skip_exp <= 0 or (kept_ctrl_exp is not None and skip_exp < kept_ctrl_exp))

    return {
        "threshold_usd": threshold, "exit": exit_name,
        "n_total": len(prepared), "n_kept": n, "n_skipped": skip_n,
        "expectancy": exp, "total": kept_battery.get("total"), "wr": kept_battery.get("wr"),
        "control_all_population_expectancy": control_all_battery.get("expectancy"),
        "control_same_kept_subset_expectancy": kept_ctrl_exp,
        "delta_vs_control_full_population": delta_full,
        "delta_vs_control_same_subset": delta_same,
        "skipped_cohort_expectancy_under_control": skip_exp,
        "skipped_cohort_total_under_control": skipped_battery_ctrl.get("total"),
        "skipped_cohort_net_negative": skipped_net_negative,
        "null_random_skip": null,
        "beats_random_skip_null": beats_null,
        "small_n": n < SMALL_N_THRESHOLD,
    }


def r_cell(prepared: list[dict], eligible: list[dict], patience: int, exit_name: str,
           exit_shape: dict, control_all_battery: dict,
           control_same_eligible_battery: dict, spy_by_time_cache: dict) -> dict:
    trades, n_lookup_miss = r_replay(eligible, patience, exit_shape, spy_by_time_cache)
    b = _battery_safe(trades)          # expectancy INCLUDING misses ($0) -- T3 convention
    filled_only = [t for t in trades if not t.get("missed")]
    fb = _battery_safe(filled_only) if filled_only else {"n": 0, "expectancy": None}

    n = b.get("n", 0)
    exp = b.get("expectancy")
    n_missed = sum(1 for t in trades if t.get("missed"))
    delta_full = (round(exp - control_all_battery["expectancy"], 2)
                  if n and control_all_battery.get("n") else None)
    delta_same = (round(exp - control_same_eligible_battery["expectancy"], 2)
                  if n and control_same_eligible_battery.get("n") else None)

    return {
        "patience_bars": patience, "exit": exit_name,
        "n_total_window": len(prepared), "n_eligible": n, "n_no_level_context": len(prepared) - n,
        "n_filled": n - n_missed, "n_missed": n_missed,
        "fill_rate": round((n - n_missed) / n, 3) if n else None,
        "n_spy_bar_lookup_miss": n_lookup_miss,
        "expectancy_incl_misses": exp, "total_incl_misses": b.get("total"), "wr_incl_misses": b.get("wr"),
        "expectancy_filled_only": fb.get("expectancy"), "n_filled_only": fb.get("n"),
        "control_all_population_expectancy": control_all_battery.get("expectancy"),
        "control_same_eligible_subset_expectancy": control_same_eligible_battery.get("expectancy"),
        "delta_vs_control_full_population": delta_full,
        "delta_vs_control_same_subset": delta_same,
        "small_n": n < SMALL_N_THRESHOLD,
    }


# ---------------------------------------------------------------------------------------------
# WINDOW RUNNER
# ---------------------------------------------------------------------------------------------
def run_window(name: str, signals: list[dict], level_start: dt.date, level_end: dt.date) -> dict:
    t0 = _time_mod.time()
    enriched, spy_full = lc.enrich_signals(signals, level_start, level_end)
    for e in enriched:
        assert dt.date.fromisoformat(e["date"]) != TODAY_EXCLUDED, \
            f"2026-07-09 leaked into window {name} -- pre-registration violation"
    prepared, n_missing_bars = prepare_window(enriched)
    print(f"[tw8] {name}: {len(prepared)} prepared (of {len(enriched)} enriched, "
          f"{n_missing_bars} missing OPRA bars) in {_time_mod.time()-t0:.0f}s", flush=True)

    control_all_trades = t5.replay_market(prepared, CONTROL_SHAPE)
    control_all_battery = _battery_safe(control_all_trades)

    exit_pnl_pools: dict[str, list[float]] = {}
    exit_all_batteries: dict[str, dict] = {}
    for exit_name, shape in EXIT_SHAPES.items():
        if exit_name == "CONTROL":
            trades = control_all_trades
        else:
            trades = t5.replay_market(prepared, shape)
        exit_pnl_pools[exit_name] = [t["pnl"] for t in trades]
        exit_all_batteries[exit_name] = _battery_safe(trades)

    eligible = eligible_for_r(prepared)
    control_same_eligible_trades = t5.replay_market(eligible, CONTROL_SHAPE)
    control_same_eligible_battery = _battery_safe(control_same_eligible_trades)

    spy_by_time_cache: dict = {}
    for p in eligible:
        d = p["date"]
        if d not in spy_by_time_cache:
            spy_by_time_cache[d] = lc.spy_bars_by_time_for_day(spy_full, d)

    h_results: dict[str, dict] = {}
    for threshold in H_THRESHOLDS:
        h_results[str(threshold)] = {
            exit_name: h_cell(prepared, threshold, exit_name, shape, control_all_battery,
                               exit_pnl_pools[exit_name])
            for exit_name, shape in EXIT_SHAPES.items()
        }

    r_results: dict[str, dict] = {}
    for patience in R_PATIENCE:
        r_results[str(patience)] = {
            exit_name: r_cell(prepared, eligible, patience, exit_name, shape, control_all_battery,
                               control_same_eligible_battery, spy_by_time_cache)
            for exit_name, shape in EXIT_SHAPES.items()
        }

    return {
        "window_name": name,
        "n_signals_input": len(signals), "n_enriched": len(enriched),
        "n_prepared": len(prepared), "n_missing_bars": n_missing_bars,
        "n_eligible_for_r": len(eligible), "n_no_level_context": len(prepared) - len(eligible),
        "control_all": control_all_battery,
        "exit_all": exit_all_batteries,
        "control_same_eligible_subset_for_r": control_same_eligible_battery,
        "candidate_H": h_results,
        "candidate_R": r_results,
    }


# ---------------------------------------------------------------------------------------------
# VERDICTS
# ---------------------------------------------------------------------------------------------
def _bool_or_none(x) -> bool | None:
    return x if isinstance(x, bool) else None


def verdict_h(threshold: float, exit_name: str, fresh_cell: dict, exp_cell: dict) -> dict:
    fresh_pass = (fresh_cell["expectancy"] is not None and fresh_cell["delta_vs_control_full_population"] is not None
                  and fresh_cell["delta_vs_control_full_population"] > 0)
    exp_pass = (exp_cell["expectancy"] is not None and exp_cell["delta_vs_control_full_population"] is not None
                and exp_cell["delta_vs_control_full_population"] > 0)
    null_pass = fresh_cell.get("beats_random_skip_null")
    skip_pass = fresh_cell.get("skipped_cohort_net_negative")
    small_n = bool(fresh_cell["small_n"])

    components = {
        "fresh_delta_positive": fresh_pass, "exploratory_delta_positive": exp_pass,
        "beats_random_skip_null": null_pass, "skipped_cohort_net_negative": skip_pass,
    }
    if small_n or fresh_cell["n_kept"] == 0:
        overall = "INCONCLUSIVE_SMALL_N"
    elif not (fresh_pass and exp_pass and bool(null_pass) and (skip_pass is not False)):
        overall = "FAIL"
    else:
        overall = "PASS"
    reason = (f"fresh: exp=${fresh_cell['expectancy']} n_kept={fresh_cell['n_kept']} "
              f"delta={fresh_cell['delta_vs_control_full_population']} | "
              f"exploratory: exp=${exp_cell['expectancy']} delta={exp_cell['delta_vs_control_full_population']} | "
              f"null_mean={fresh_cell['null_random_skip']['mean_of_means'] if fresh_cell['null_random_skip'] else 'n/a'} "
              f"beats_null={null_pass} | skipped_net_negative={skip_pass}")
    return {"threshold_usd": threshold, "exit": exit_name, "components": components,
            "small_n": small_n, "overall": overall, "reason": reason}


def verdict_r(patience: int, exit_name: str, fresh_cell: dict, exp_cell: dict) -> dict:
    fresh_pass = (fresh_cell["expectancy_incl_misses"] is not None
                  and fresh_cell["delta_vs_control_full_population"] is not None
                  and fresh_cell["delta_vs_control_full_population"] > 0)
    exp_pass = (exp_cell["expectancy_incl_misses"] is not None
                and exp_cell["delta_vs_control_full_population"] is not None
                and exp_cell["delta_vs_control_full_population"] > 0)
    small_n = bool(fresh_cell["small_n"])
    misses_priced = fresh_cell["n_missed"] >= 0   # structural invariant, always true; real check is in pytest

    components = {"fresh_delta_positive": fresh_pass, "exploratory_delta_positive": exp_pass,
                  "misses_priced_in": misses_priced}
    if small_n or fresh_cell["n_eligible"] == 0:
        overall = "INCONCLUSIVE_SMALL_N"
    elif not (fresh_pass and exp_pass):
        overall = "FAIL"
    else:
        overall = "PASS"
    reason = (f"fresh: exp_incl_misses=${fresh_cell['expectancy_incl_misses']} "
              f"n_eligible={fresh_cell['n_eligible']} n_missed={fresh_cell['n_missed']} "
              f"fill_rate={fresh_cell['fill_rate']} delta={fresh_cell['delta_vs_control_full_population']} | "
              f"exploratory: exp_incl_misses=${exp_cell['expectancy_incl_misses']} "
              f"delta={exp_cell['delta_vs_control_full_population']}")
    return {"patience_bars": patience, "exit": exit_name, "components": components,
            "small_n": small_n, "overall": overall, "reason": reason}


def build_verdicts(exploratory: dict, fresh: dict) -> dict:
    verdicts = {"H": {}, "R": {}}
    for threshold in H_THRESHOLDS:
        tk = str(threshold)
        verdicts["H"][tk] = {
            exit_name: verdict_h(threshold, exit_name, fresh["candidate_H"][tk][exit_name],
                                  exploratory["candidate_H"][tk][exit_name])
            for exit_name in EXIT_SHAPES
        }
    for patience in R_PATIENCE:
        pk = str(patience)
        verdicts["R"][pk] = {
            exit_name: verdict_r(patience, exit_name, fresh["candidate_R"][pk][exit_name],
                                  exploratory["candidate_R"][pk][exit_name])
            for exit_name in EXIT_SHAPES
        }
    return verdicts


def build_key_findings(exploratory: dict, fresh: dict, verdicts: dict) -> list[str]:
    notes = []
    ca = fresh["control_all"]
    notes.append(
        f"Fresh-slice CONTROL baseline (n={ca.get('n')}, {fresh['window_name']}): expectancy "
        f"${ca.get('expectancy')}, WR {ca.get('wr')}, total ${ca.get('total')} -- the number every "
        f"H/R cell in the fresh window is measured against.")
    n_pass = sum(1 for fam in verdicts.values() for cells in fam.values()
                 for v in cells.values() if v["overall"] == "PASS")
    n_fail = sum(1 for fam in verdicts.values() for cells in fam.values()
                 for v in cells.values() if v["overall"] == "FAIL")
    n_incl = sum(1 for fam in verdicts.values() for cells in fam.values()
                 for v in cells.values() if v["overall"] == "INCONCLUSIVE_SMALL_N")
    notes.append(f"Verdict tally across all (candidate, parameter, exit) cells: {n_pass} PASS, "
                 f"{n_fail} FAIL, {n_incl} INCONCLUSIVE_SMALL_N (fresh window n={fresh['n_prepared']} "
                 f"is SMALL BY CONSTRUCTION -- most cells are expected to land here per the "
                 f"pre-registration's own disclosure).")
    notes.append(
        f"R eligibility (a detectable trigger_level on the recovered trigger bar): "
        f"{fresh['n_eligible_for_r']}/{fresh['n_prepared']} fresh signals, "
        f"{exploratory['n_eligible_for_r']}/{exploratory['n_prepared']} exploratory signals -- "
        f"the majority of ribbon_ride signals are admitted via ribbon_flip/sequence/confluence-only "
        f"triggers with no literal level cross on the trigger bar, and R has no defined action for those.")
    for threshold in H_THRESHOLDS:
        cell = fresh["candidate_H"][str(threshold)]["CONTROL"]
        if cell["n_kept"] > 0 and cell["n_skipped"] > 0:
            notes.append(
                f"H@${threshold} (CONTROL exit, fresh): kept {cell['n_kept']}/{cell['n_total']}, "
                f"skipped {cell['n_skipped']} with expectancy ${cell['skipped_cohort_expectancy_under_control']} "
                f"under CONTROL (net_negative={cell['skipped_cohort_net_negative']}); kept-cohort delta vs "
                f"control ${cell['delta_vs_control_full_population']}; beats random-skip null: "
                f"{cell['beats_random_skip_null']} (null mean "
                f"${cell['null_random_skip']['mean_of_means'] if cell['null_random_skip'] else 'n/a'}).")
    return notes


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    pf = preflight()
    print(f"[tw8] preflight: {pf}", flush=True)
    if not pf["exploratory_hash_ok"] or not pf["fresh_hash_ok"] or not pf["preregistration_version_ok"]:
        print("[tw8] PREFLIGHT FAILED -- aborting (no re-picks, no stale-hash runs)", file=sys.stderr)
        return 1

    exp_data = sc.load_or_build_signals()
    exp_signals = exp_data["signals"] if isinstance(exp_data, dict) else exp_data
    fresh_data = t5.build_fresh_slice()   # verifies + REUSES the existing file (never rebuilds silently)
    fresh_signals = fresh_data["signals"]

    print(f"[tw8] exploratory: {len(exp_signals)} signals ({EXPLORATORY_START}..{EXPLORATORY_END})", flush=True)
    print(f"[tw8] fresh: {len(fresh_signals)} signals ({fresh_data['kept_from']}..{fresh_data['generation_end']})",
          flush=True)

    exploratory = run_window("exploratory", exp_signals, EXPLORATORY_START, EXPLORATORY_END)
    fresh = run_window("fresh", fresh_signals, FRESH_START_WARMUP, FRESH_END)

    verdicts = build_verdicts(exploratory, fresh)
    key_findings = build_key_findings(exploratory, fresh, verdicts)
    for kf in key_findings:
        print(f"[tw8] FINDING: {kf[:160]}", flush=True)

    out = {
        "_doc": "T-W8 HEADROOM + RETEST pre-registered entry-candidate study. Confirmatory read = "
                "fresh window (2026-06-19..2026-07-08); exploratory window (2025-01-01..2026-06-18) "
                "is BURNED, directional-consistency check only. 2026-07-09 excluded from both "
                "(generated the hypothesis). ANALYSIS ONLY -- no trading-path file touched.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "preflight": pf,
        "windows": {"exploratory": exploratory, "fresh": fresh},
        "verdicts": verdicts,
        "key_findings": key_findings,
        "disclosures": [
            "Fresh window n=18 signals (~13 trading days) -- SMALL BY CONSTRUCTION, disclosed not "
            "padded (same convention as T5's fresh slice, which T-W8 reuses verbatim).",
            "qty 10 fixed; expectancy is relative-to-control, not an OP-16 account-scaled absolute.",
            "Frictionless fills; 5-min OPRA bars (touch semantics; 1-min close timing not modelled).",
            "Premium-only replay: ribbon/level/chart exits OFF -- only the two named exit shapes.",
            "ribbon_ride only (both directions); vwap_continuation not in scope.",
            "No real-fills anchor (layer b) in this study -- owed separately if any candidate PASSes.",
            "R's eligible population (signals with a detectable trigger_level) is a real subset of "
            "each window, disclosed per-window as n_eligible_for_r / n_no_level_context.",
            "H's null_random_skip samples WITHOUT replacement from the exit-shape-specific pnl pool "
            "of the FULL window population, k=n_kept, 1000 trials, seed 20260709 (frozen pre-reg).",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[tw8] wrote {OUT_JSON}", flush=True)

    print("[tw8] ===== VERDICT SUMMARY =====", flush=True)
    for fam, cells in verdicts.items():
        for pk, exits in cells.items():
            for exit_name, v in exits.items():
                print(f"[tw8] {fam}@{pk} / {exit_name}: {v['overall']}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

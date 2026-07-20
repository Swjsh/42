"""premarket_touch_credit_study.py -- PREMARKET-TOUCH-CREDIT segmentation study.

Runs the FROZEN pre-registration (analysis/recommendations/premarket-touch-credit-
preregistration.json) -- no re-picks after seeing results. Motivated by J's Monday
2026-07-20 ~09:36 ET premarket question (queue.md PREMARKET-TOUCH-CREDIT-STUDY, HIGH):
the engine gives ZERO touch-credit to premarket rejections/reclaims because level_states
touch counting starts at 09:30 RTH.

QUESTION: do RTH rejection/reclaim triggers whose OWN trigger_level had >=1 premarket
rejection/reclaim bar outperform identical triggers at levels never tested premarket --
under the SAME live exit shape (SS-B, trigger-exact, buffer 0.00 -- today's actual live
structure-stop behavior)? This is a SEGMENTATION study (population split by a new label),
NOT a shape sweep -- both groups replay under byte-identical exit logic.

REUSES, does not reinvent:
  * structure_stop_study.py  -- replay_structure_aware, structure_stop_signal_time,
    SS_B_SHAPE, TIME_STOP_LAYER_A, norm_bars_from_t4
  * tw8_level_context.py     -- frozen_level_set_for_date, load_spy_full, enrich_signals
  * lib.filters              -- detect_level_rejection / detect_level_reclaim (the EXACT
    production bar-test), reused verbatim for premarket touch detection -- zero new
    hand-picked band/proximity parameter.
  * t4_exit_matrix.py        -- _load_bars (local option-bar cache, $0, no network)
  * backtest/autoresearch/probe_stats.py -- summarize_trades, day_concentration,
    concentration_flag, significance

LAYER (b) real-fills anchor is DEFERRED this run (see the pre-reg's scope_note) -- this
is layer (a) fresh-slice only, $0, no network calls (all option bars already locally
cached).

ANALYSIS ONLY: writes only to analysis/recommendations/. Never touches strategies.py,
params.json, exit_manager.py, level_states, or any trading-path file, regardless of verdict.

Run: backtest/.venv/Scripts/python.exe backtest/tools/premarket_touch_credit_study.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
import statistics
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "tools"))
sys.path.insert(0, str(REPO / "backtest" / "autoresearch"))

import pandas as pd  # noqa: E402

import structure_stop_study as sss               # noqa: E402  (replay engine, SS_B_SHAPE)
import tw8_level_context as lc                    # noqa: E402
import t4_exit_matrix as t4                       # noqa: E402  (_load_bars, QTY)
from lib.filters import detect_level_reclaim, detect_level_rejection  # noqa: E402
import probe_stats as ps                          # noqa: E402

PREREG = REPO / "analysis" / "recommendations" / "premarket-touch-credit-preregistration.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "premarket-touch-credit-2026-07-20.json"

CANONICAL_CACHE = REPO / "analysis" / "exit-parity" / "signal-set.json"
FRESH_SET = REPO / "analysis" / "exit-parity" / "signal-set-fresh-20260619-20260708.json"

LEVEL_HISTORY_START = dt.date(2026, 5, 19)
LEVEL_HISTORY_END = dt.date(2026, 7, 17)
CANONICAL_FILTER_START = "2026-05-19"
CANONICAL_FILTER_END = "2026-07-17"

MIDPOINT_DATE = "2026-06-25"   # ~midpoint of the combined population's date span, by unique day

RANDOM_LABEL_DRAWS = 2000
SHUFFLED_LEVEL_DRAWS = 500
RNG_SEED = 20260720   # frozen in the pre-reg's spirit: fixed seed, reproducible, not re-rolled

EXPECTED_PREREG_VERSION = 1


def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------------------------
# BH-FDR -- copied verbatim (algorithm + docstring) from backtest/futures/battery.py::bh_fdr
# to avoid importing that module's swing_sim dependency chain for one 15-line pure function.
# ---------------------------------------------------------------------------------------------
def bh_fdr(pvalues: list[float], alpha: float = 0.05) -> list[bool]:
    """Benjamini-Hochberg step-up FDR. Returns a same-length list of booleans
    (True = survives at this alpha). NaN p-values never survive."""
    m = len(pvalues)
    if m == 0:
        return []
    order = sorted(range(m), key=lambda i: (float("inf") if pd.isna(pvalues[i]) else pvalues[i]))
    survive = [False] * m
    threshold_rank = 0
    for rank, idx in enumerate(order, start=1):
        p = pvalues[idx]
        if pd.isna(p):
            continue
        if p <= (rank / m) * alpha:
            threshold_rank = rank
    for rank, idx in enumerate(order, start=1):
        if rank <= threshold_rank:
            survive[idx] = True
    return survive


# ---------------------------------------------------------------------------------------------
# PREFLIGHT
# ---------------------------------------------------------------------------------------------
def preflight() -> dict:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    ver = preg.get("version")
    return {"preregistration_version": ver, "preregistration_version_ok": ver == EXPECTED_PREREG_VERSION}


# ---------------------------------------------------------------------------------------------
# COMBINED FRESH-SLICE POPULATION
# ---------------------------------------------------------------------------------------------
def load_combined_signals() -> list[dict]:
    canon = json.loads(CANONICAL_CACHE.read_text(encoding="utf-8"))
    canon_sigs = canon["signals"] if isinstance(canon, dict) else canon
    canon_filt = [s for s in canon_sigs if CANONICAL_FILTER_START <= s["date"] <= CANONICAL_FILTER_END]

    fresh = json.loads(FRESH_SET.read_text(encoding="utf-8"))
    fresh_sigs = fresh["signals"] if isinstance(fresh, dict) else fresh

    seen = set()
    combined = []
    for s in canon_filt + fresh_sigs:
        key = (s["date"], s["entry_ts"], s["side"])
        if key in seen:
            continue
        seen.add(key)
        combined.append(s)
    combined.sort(key=lambda s: (s["date"], s["entry_ts"]))
    return combined


# ---------------------------------------------------------------------------------------------
# PREMARKET TOUCH DETECTION -- reuses the EXACT production rejection/reclaim test
# ---------------------------------------------------------------------------------------------
def premarket_touch_count(spy_full: pd.DataFrame, date: dt.date, trigger_level: float, side: str) -> int:
    """Count premarket (time < 09:30 ET) 5m bars on `date` where the SAME test the RTH
    trigger detector uses fires against the singleton [trigger_level], direction-matched
    to `side` (P=rejection test, C=reclaim test). $0, no look-ahead: only bars strictly
    before 09:30 on the signal's OWN date."""
    day_bars = spy_full[(spy_full["date"] == date) & (spy_full["time"] < dt.time(9, 30))]
    count = 0
    for row in day_bars.itertuples():
        bar = pd.Series({"high": row.high, "low": row.low, "close": row.close})
        fired = (detect_level_rejection(bar, [trigger_level]) if side == "P"
                 else detect_level_reclaim(bar, [trigger_level]))
        if fired is not None:
            count += 1
    return count


def other_active_levels(level_set, trigger_level: Optional[float]) -> list[float]:
    if level_set is None or trigger_level is None:
        return []
    return [lv for lv in level_set.active if abs(lv - trigger_level) > 1e-9]


# ---------------------------------------------------------------------------------------------
# PREP + REPLAY (layer a fresh-slice, SS-B trigger-exact buffer=0.0 -- today's live shape)
# ---------------------------------------------------------------------------------------------
def prepare(signals: list[dict]) -> tuple[list[dict], dict, pd.DataFrame]:
    enriched, spy_full = lc.enrich_signals(signals, LEVEL_HISTORY_START, LEVEL_HISTORY_END)
    level_cache: dict = {}
    prepared = []
    n_no_trigger_level = 0
    n_no_bars = 0
    for s in enriched:
        trigger_level = s.get("trigger_level")
        if trigger_level is None:
            n_no_trigger_level += 1
            continue
        bars = t4._load_bars(s)
        if not bars:
            n_no_bars += 1
            continue
        entry_premium = bars[0][1]
        if entry_premium <= 0:
            n_no_bars += 1
            continue
        date = dt.date.fromisoformat(s["date"])
        entry_ts = dt.datetime.fromisoformat(s["entry_ts"])
        spy_lifetime = spy_full[(spy_full["date"] == date) & (spy_full["timestamp_et"] >= entry_ts)]
        level_set = lc.frozen_level_set_for_date(spy_full, date, level_cache)
        pm_count = premarket_touch_count(spy_full, date, trigger_level, s["side"])
        prepared.append({
            "date": s["date"], "direction": s["direction"], "side": s["side"],
            "entry_premium": entry_premium,
            "norm_bars": sss.norm_bars_from_t4(bars, date),
            "trigger_level": trigger_level,
            "spy_lifetime": spy_lifetime,
            "premarket_touch_count": pm_count,
            "touched": pm_count >= 1,
            "other_levels": other_active_levels(level_set, trigger_level),
        })
    stats = {"n_signals_total": len(signals), "n_eligible": len(prepared),
              "n_excluded_no_trigger_level": n_no_trigger_level,
              "n_excluded_no_option_bars": n_no_bars}
    return prepared, stats, spy_full


def replay_one(p: dict) -> float:
    ss_time = sss.structure_stop_signal_time(p["spy_lifetime"], p["side"], p["trigger_level"], 0.0)
    r = sss.replay_structure_aware(p["entry_premium"], p["side"], t4.QTY, p["norm_bars"],
                                    ss_time, sss.SS_B_SHAPE, sss.TIME_STOP_LAYER_A)
    return r["pnl"]


def attach_pnl(prepared: list[dict]) -> None:
    for p in prepared:
        p["pnl"] = replay_one(p)


# ---------------------------------------------------------------------------------------------
# SEGMENTATION + NULLS
# ---------------------------------------------------------------------------------------------
def segment_delta(prepared: list[dict], touched_flags: list[bool]) -> float:
    touched = [p["pnl"] for p, t in zip(prepared, touched_flags) if t]
    untouched = [p["pnl"] for p, t in zip(prepared, touched_flags) if not t]
    if not touched or not untouched:
        return 0.0
    return statistics.mean(touched) - statistics.mean(untouched)


def random_label_null(prepared: list[dict], observed_delta: float, rng: random.Random) -> dict:
    n_touched = sum(1 for p in prepared if p["touched"])
    n = len(prepared)
    null_deltas = []
    for _ in range(RANDOM_LABEL_DRAWS):
        idx = list(range(n))
        rng.shuffle(idx)
        shuffled_touched = [False] * n
        for i in idx[:n_touched]:
            shuffled_touched[i] = True
        null_deltas.append(segment_delta(prepared, shuffled_touched))
    extreme = sum(1 for d in null_deltas if abs(d) >= abs(observed_delta))
    p_value = extreme / len(null_deltas) if null_deltas else float("nan")
    return {"p_value": round(p_value, 4), "n_draws": len(null_deltas),
            "null_mean": round(statistics.mean(null_deltas), 2) if null_deltas else None,
            "null_stdev": round(statistics.pstdev(null_deltas), 2) if len(null_deltas) > 1 else None}


def shuffled_level_null(prepared: list[dict], observed_delta: float, rng: random.Random,
                         spy_full: pd.DataFrame) -> dict:
    eligible = [p for p in prepared if p["other_levels"]]
    null_deltas = []
    n_skipped_no_alt = len(prepared) - len(eligible)
    for _ in range(SHUFFLED_LEVEL_DRAWS):
        touched_flags = []
        for p in prepared:
            if not p["other_levels"]:
                touched_flags.append(p["touched"])   # no alternate level that day -- keep real label
                continue
            alt_level = rng.choice(p["other_levels"])
            date = dt.date.fromisoformat(p["date"])
            pm_count = premarket_touch_count(spy_full, date, alt_level, p["side"])
            touched_flags.append(pm_count >= 1)
        null_deltas.append(segment_delta(prepared, touched_flags))
    extreme = sum(1 for d in null_deltas if abs(d) >= abs(observed_delta))
    p_value = extreme / len(null_deltas) if null_deltas else float("nan")
    return {"p_value": round(p_value, 4), "n_draws": len(null_deltas),
            "n_signals_with_no_alt_level": n_skipped_no_alt,
            "null_mean": round(statistics.mean(null_deltas), 2) if null_deltas else None,
            "null_stdev": round(statistics.pstdev(null_deltas), 2) if len(null_deltas) > 1 else None}


# ---------------------------------------------------------------------------------------------
# VERDICT
# ---------------------------------------------------------------------------------------------
def run_segment(prepared: list[dict], rng: random.Random, spy_full: pd.DataFrame, label: str) -> dict:
    touched = [p for p in prepared if p["touched"]]
    untouched = [p for p in prepared if not p["touched"]]
    observed_delta = segment_delta(prepared, [p["touched"] for p in prepared])

    touched_summary = ps.summarize_trades([p["pnl"] for p in touched])
    untouched_summary = ps.summarize_trades([p["pnl"] for p in untouched])

    by_day: dict = {}
    for p in touched:
        by_day.setdefault(p["date"], 0.0)
        by_day[p["date"]] += p["pnl"]
    conc = ps.day_concentration(by_day)
    conc_flag = ps.concentration_flag(conc["top3_day_pct_of_net"])

    r_null = random_label_null(prepared, observed_delta, rng) if (touched and untouched) else None
    s_null = (shuffled_level_null(prepared, observed_delta, rng, spy_full)
              if (touched and untouched) else None)

    sig = ps.significance(min(len(touched), len(untouched)) if (touched and untouched) else 0, min_n=8)

    return {
        "label": label, "n_total": len(prepared), "n_touched": len(touched), "n_untouched": len(untouched),
        "observed_delta_touched_minus_untouched": round(observed_delta, 2),
        "touched_summary": touched_summary, "untouched_summary": untouched_summary,
        "touched_day_concentration": conc, "touched_concentration_flag": conc_flag,
        "random_label_null": r_null, "shuffled_level_null": s_null,
        "significance_floor": sig,
    }


def build_verdict(overall: dict, sub_windows: dict) -> dict:
    n_touched = overall["n_touched"]
    n_untouched = overall["n_untouched"]
    if n_touched == 0 or n_untouched == 0:
        return {"overall": "NO_SPLIT_POSSIBLE",
                "reason": f"n_touched={n_touched}, n_untouched={n_untouched} -- one group empty, "
                          f"cannot segment. KILL by construction."}

    p_random = overall["random_label_null"]["p_value"]
    p_shuffled = overall["shuffled_level_null"]["p_value"]
    pvals = [p_random, p_shuffled]
    survivors = bh_fdr(pvals, alpha=0.05)
    both_survive = all(survivors)

    delta_first = sub_windows["first_half"]["observed_delta_touched_minus_untouched"]
    delta_second = sub_windows["second_half"]["observed_delta_touched_minus_untouched"]
    sign_flip = (delta_first > 0) != (delta_second > 0) if (delta_first != 0 and delta_second != 0) else False

    concentrated = overall["touched_concentration_flag"]["concentrated"]
    underpowered = not overall["significance_floor"]["sufficient"]

    if not both_survive:
        overall_verdict = "KILL"
        reason = f"p_random={p_random} p_shuffled_level={p_shuffled} -- BH-FDR survivors={survivors}, not both significant."
    elif sign_flip:
        overall_verdict = "NO_SHIP_SUBWINDOW_UNSTABLE"
        reason = f"nominal significance but sub-window sign flip (first=${delta_first} second=${delta_second})."
    elif concentrated:
        overall_verdict = "NO_SHIP_CONCENTRATED"
        reason = f"nominal significance but touched-group top3-day% = {overall['touched_day_concentration']['top3_day_pct_of_net']}%."
    elif underpowered:
        overall_verdict = "INCONCLUSIVE_UNDERPOWERED"
        reason = f"directionally consistent (both nulls survive) but n_touched={n_touched}/n_untouched={n_untouched} below the n>=8 floor."
    else:
        overall_verdict = "SIGNAL"
        reason = "both nulls BH-FDR-survive, sub-window stable, not concentrated, n floor cleared."

    return {"overall": overall_verdict, "reason": reason,
            "p_random_label": p_random, "p_shuffled_level": p_shuffled,
            "bh_fdr_survivors": survivors, "sub_window_sign_flip": sign_flip,
            "sub_window_delta_first_half": delta_first, "sub_window_delta_second_half": delta_second,
            "touched_concentrated": concentrated, "underpowered": underpowered}


# ---------------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------------
def main() -> int:
    pf = preflight()
    print(f"[ptc] preflight: {pf}", flush=True)
    if not pf["preregistration_version_ok"]:
        print("[ptc] PREFLIGHT FAILED -- aborting (no re-picks, no stale-version runs)", file=sys.stderr)
        return 1

    signals = load_combined_signals()
    print(f"[ptc] combined fresh-slice population: {len(signals)} signals "
          f"({CANONICAL_FILTER_START}..{CANONICAL_FILTER_END} canonical + fresh 20260619-20260708)",
          flush=True)

    prepared, prep_stats, spy_full = prepare(signals)
    print(f"[ptc] prepared: {prep_stats}", flush=True)
    attach_pnl(prepared)

    rng = random.Random(RNG_SEED)

    overall = run_segment(prepared, rng, spy_full, "overall")
    print(f"[ptc] overall: n_touched={overall['n_touched']} n_untouched={overall['n_untouched']} "
          f"delta=${overall['observed_delta_touched_minus_untouched']} "
          f"p_random={overall['random_label_null']['p_value'] if overall['random_label_null'] else None} "
          f"p_shuffled={overall['shuffled_level_null']['p_value'] if overall['shuffled_level_null'] else None}",
          flush=True)

    dates = sorted(set(p["date"] for p in prepared))
    first_half = [p for p in prepared if p["date"] <= MIDPOINT_DATE]
    second_half = [p for p in prepared if p["date"] > MIDPOINT_DATE]
    sub_windows = {
        "first_half": run_segment(first_half, random.Random(RNG_SEED + 1), spy_full, "first_half"),
        "second_half": run_segment(second_half, random.Random(RNG_SEED + 2), spy_full, "second_half"),
    }

    bear_only = [p for p in prepared if p["direction"] == "bear"]
    bull_only = [p for p in prepared if p["direction"] == "bull"]
    by_direction = {
        "bear": run_segment(bear_only, random.Random(RNG_SEED + 3), spy_full, "bear") if bear_only else None,
        "bull": run_segment(bull_only, random.Random(RNG_SEED + 4), spy_full, "bull") if bull_only else None,
    }

    verdict = build_verdict(overall, sub_windows)
    print(f"[ptc] VERDICT: {verdict['overall']} -- {verdict['reason']}", flush=True)

    disclosures = [
        "SEGMENTATION study, not a shape sweep: TOUCHED and UNTOUCHED groups replay under the "
        "byte-identical live exit shape (SS-B, trigger-exact reference, buffer 0.00 -- confirmed "
        "live in structure-stop-zone-band-2026-07-20.json BAND-00 / structure-stop-reference-"
        "level-2026-07-20.json REF-EXACT). Only the premarket-touch LABEL differs between groups.",
        "Layer (b) real-fills anchor DEFERRED this run (pre-reg scope_note) -- this is layer (a) "
        "fresh-slice only, $0, no live network calls (option bars from local cache).",
        "Small-n disclosed IN ADVANCE (pre-reg small_n_floor): n~40 total population, touched "
        "likely a minority -- INCONCLUSIVE_UNDERPOWERED is an expected, not a failure, outcome.",
        "Premarket window restricted to 2026-05-19 onward (Alpaca-SIP-verified premarket OHLC per "
        "DATA-PROVENANCE.md) -- older signals excluded by rule to avoid an IEX/09:00-start feed "
        "provenance confound on touch counts.",
        f"Random-label null: {RANDOM_LABEL_DRAWS} draws, seed={RNG_SEED}. Shuffled-level null: "
        f"{SHUFFLED_LEVEL_DRAWS} draws per segment, same seed family -- reproducible, not re-rolled.",
        "BH-FDR (backtest/futures/battery.py::bh_fdr algorithm, copied verbatim to avoid an "
        "unrelated swing_sim import chain) applied to the 2 overall p-values; per-direction and "
        "sub-window segments reported for disclosure but not independently gated (single primary "
        "verdict per pre-reg, avoiding a multiple-comparisons fishing expedition across cuts).",
        "Frictionless fills, matching every prior study built on structure_stop_study.py's replay engine.",
        "This run NEVER touches heartbeat_core.py/level_states/params.json/any trading-path file "
        "regardless of verdict, per the item's own 'NOT a same-day wire' scope.",
    ]

    out = {
        "_doc": "PREMARKET-TOUCH-CREDIT segmentation study -- pre-registered, frozen before any "
                "replay. ANALYSIS ONLY: no trading-path file touched by this run, any verdict.",
        "generated_at": dt.datetime.now().isoformat(),
        "preregistration_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "preflight": pf,
        "population_prep": prep_stats,
        "overall": overall,
        "sub_windows": sub_windows,
        "by_direction": by_direction,
        "verdict": verdict,
        "disclosures": disclosures,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[ptc] wrote {OUT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""structure_stop_study_1min_2026_08_02.py -- STEP 2a of OPTION-BAR-RESOLUTION-BIAS-2026-08-02:
REPLICATION of structure_stop_study.py's Layer A (fresh-slice, n=18 signals) at 1-MINUTE
option-bar resolution, reproducing the ORIGINAL frozen cells (CONTROL/SS-A/SS-B/SS-C shapes,
buffers, C6 fill-mark convention, time-stop) UNCHANGED -- no new hypotheses, no threshold
sweeping, per task instruction. Layer B (the 79-position real-fills anchor) is ALREADY 1-min
per the ORIGINAL study's own disclosure ("layer (b)/exhibit are REAL 1-min Alpaca OPRA bars,
live-fetched") -- re-run here UNCHANGED (sss.run_layer_b) as a live reproducibility check, not
a resolution fix.

WHY THIS MATTERS: structure_stop_study.py's SS-B verdict (PASS -- both layers beat CONTROL) is
the live v15.3 CHART-STOP-PRIMARY flag's evidence base (chandelier trail 15% / arm +5% / tp1
100% / tp1_qty 0.667). Layer A's ORIGINAL margin over CONTROL was thin (exp $-47.34 vs
$-100.67/tr, n=18, BOTH negative) -- exactly the kind of small-n margin the resolution bias
(Step 1 of this investigation: 4/123 real positions flip stop-classification, aggregate
$1,821.75 swing, ALL in the direction of 5-min flattering P&L) could plausibly move. This
script answers: does SS-B's Layer A PASS survive honest 1-minute resolution?

REUSE (OP-22), not reinvention: structure_stop_study's own shapes/buffers/replay engine/
preflight/verdict logic (sss.*), t4_exit_matrix's band_of/QTY convention (t4.*),
tw8_level_context's level-freeze enrichment (lc.*) are all imported UNCHANGED. The ONLY new
code is the bar loader (1-min REST instead of 5-min disk cache) -- everything downstream of
"a list of (time,o,h,l,c) tuples" is the ORIGINAL, unmodified machinery.

ANALYSIS ONLY. Writes only to analysis/recommendations/. Never touches
structure_stop_study.py, exit_manager.py, params.json, or any trading-path file.

Run: backtest/.venv/Scripts/python.exe backtest/tools/structure_stop_study_1min_2026_08_02.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import structure_stop_study as sss                    # noqa: E402  (reused UNCHANGED -- shapes/buffers/replay engine)
import t4_exit_matrix as t4                             # noqa: E402  (band_of, QTY)
import tw8_level_context as lc                           # noqa: E402  (enrich_signals)
from lib.option_pricing_real import option_symbol        # noqa: E402
from _option_bars_1min_cache import fetch_1min_cached     # noqa: E402

OUT_JSON = REPO / "analysis" / "recommendations" / "structure-stop-1min-replication-2026-08-02.json"


def log(msg: str) -> None:
    print(f"[sss-1min] {msg}", flush=True)


def load_bars_1min_for_signal(sig: dict) -> tuple[Optional[list], str]:
    """1-minute equivalent of t4_exit_matrix._load_bars: SAME OTM-2 strike convention, SAME
    '>=' entry_ts inclusion (t4's own documented fill-bar convention, inherited unchanged by
    structure_stop_study's Layer A) -- only the bar SOURCE changes (1-min REST vs 5-min disk
    cache)."""
    spot = sig["entry_spot"]
    side = sig["side"]
    strike = int(round(spot)) - 2 if side == "P" else int(round(spot)) + 2
    date = dt.date.fromisoformat(sig["date"])
    symbol = option_symbol(date, strike, side)
    df, src = fetch_1min_cached(symbol, date.isoformat())
    if df is None or df.empty:
        return None, src
    entry_ts = dt.datetime.fromisoformat(sig["entry_ts"])
    ts = df["timestamp_et"]
    mask = (ts >= entry_ts) & (ts.dt.date == date)
    sub = df[mask.values]
    if sub.empty:
        return None, src
    out = []
    for _, r in sub.iterrows():
        t = r["timestamp_et"]
        out.append((t.time(), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
    return out, src


def prepare_layer_a_1min():
    raw = json.loads(sss.FRESH_SIGNAL_SET.read_text(encoding="utf-8"))
    signals = raw["signals"]
    enriched, spy_full = lc.enrich_signals(signals, sss.LEVEL_HISTORY_START, sss.LEVEL_HISTORY_END)

    prepared, n_missing_bars = [], 0
    src_counts: dict = {}
    for s in enriched:
        bars, src = load_bars_1min_for_signal(s)
        src_counts[src] = src_counts.get(src, 0) + 1
        if not bars:
            n_missing_bars += 1
            continue
        entry_premium = bars[0][1]
        if entry_premium <= 0:
            n_missing_bars += 1
            continue
        date = dt.date.fromisoformat(s["date"])
        entry_ts = dt.datetime.fromisoformat(s["entry_ts"])
        spy_lifetime = spy_full[(spy_full["date"] == date) & (spy_full["timestamp_et"] >= entry_ts)]
        prepared.append({
            "date": date, "direction": s["direction"], "side": s["side"],
            "entry_premium": entry_premium, "band": t4.band_of(entry_premium),
            "norm_bars": sss.norm_bars_from_t4(bars, date),
            "trigger_level": s.get("trigger_level"),
            "level_context_status": s.get("level_context_status"),
            "spy_lifetime": spy_lifetime,
        })
    return prepared, n_missing_bars, spy_full, src_counts


def main() -> int:
    pf = sss.preflight()
    log(f"preflight (reused unchanged, confirms this replication reads the SAME frozen signal "
        f"set + anchor population + pre-registration the original 2026-07-09 study used): {pf}")
    if not (pf["fresh_slice_hash_ok"] and pf["anchor_population_hash_ok"] and pf["preregistration_version_ok"]):
        log("PREFLIGHT FAILED -- aborting (no re-picks, no stale-hash runs)")
        return 1

    log("Layer A (fresh-slice, n=18): rebuilding at 1-minute option-bar resolution "
        "(ONLY change vs original -- same signals, same OTM-2 strike, same C6 convention)")
    prepared_a, n_missing_a, _spy_a, src_counts = prepare_layer_a_1min()
    log(f"Layer A 1-min: {len(prepared_a)} prepared, {n_missing_a} missing bars, "
        f"bar sources={src_counts}")
    layer_a_1min = sss.run_layer_a(prepared_a)
    layer_a_1min["n_missing_bars"] = n_missing_a
    layer_a_1min["bar_sources"] = src_counts

    log("Layer B (real-fills anchor, n=79): re-running UNCHANGED (sss.run_layer_b) -- ALREADY "
        "1-min in the original study; this is a live reproducibility check, not a fix")
    spy_full = sss.load_spy_full_with_today()
    layer_b_1min, _layer_b_rows = sss.run_layer_b(spy_full)

    original = json.loads(sss.OUT_JSON.read_text(encoding="utf-8"))
    layer_b_original = original["layer_b_real_fills_anchor"]
    layer_a_original = original["layer_a_fresh_slice"]

    layer_b_reproduces = all(
        abs(layer_b_1min["candidates"][cid]["anchor_total"]
            - layer_b_original["candidates"][cid]["anchor_total"]) < 0.01
        for cid in sss.ALL_CANDIDATE_IDS
    )
    log(f"Layer B reproducibility check (1-min re-run vs original persisted numbers): "
        f"{'MATCH' if layer_b_reproduces else 'DRIFT -- see detail in output JSON'}")

    verdicts_1min = sss.build_verdicts(layer_a_1min, layer_b_1min)
    verdicts_original = original["verdicts"]

    log("=== VERDICTS: ORIGINAL (5-min Layer A) vs 1-MIN REPLICATION ===")
    flags = {}
    for cid in sss.STRUCTURE_CANDIDATE_IDS:
        o = verdicts_original[cid]["overall"]
        n = verdicts_1min[cid]["overall"]
        if o == "PASS" and n == "PASS":
            flag = "CONFIRMED"
        elif o == "PASS" and n != "PASS":
            flag = "INVERTED"
        elif o != "PASS" and n == "PASS":
            flag = "NEWLY_PASSES"
        else:
            flag = "CONFIRMED_FAIL"
        flags[cid] = flag
        log(f"  {cid}: original={o} 1min={n} -> {flag}")
        log(f"     layer_a exp: original ${layer_a_original['candidates'][cid]['expectancy']} "
            f"-> 1min ${layer_a_1min['candidates'][cid]['expectancy']} "
            f"(control: original ${layer_a_original['candidates']['CONTROL']['expectancy']} "
            f"-> 1min ${layer_a_1min['candidates']['CONTROL']['expectancy']})")

    out = {
        "_doc": "STEP 2a of OPTION-BAR-RESOLUTION-BIAS-2026-08-02: structure_stop_study.py's "
                "Layer A (fresh-slice) rebuilt at 1-minute option-bar resolution, REPLICATING "
                "the ORIGINAL frozen cells (no new hypotheses, no threshold sweeping). Layer B "
                "was ALREADY 1-min in the original study (re-run here unchanged as a live "
                "reproducibility check).",
        "generated_at": dt.datetime.now().isoformat(),
        "original_scorecard": str(sss.OUT_JSON.relative_to(REPO)).replace("\\", "/"),
        "preflight": pf,
        "layer_a_1min": layer_a_1min,
        "layer_a_original_5min": layer_a_original,
        "layer_b_1min_rerun": {k: v for k, v in layer_b_1min.items() if k != "rows"},
        "layer_b_original": layer_b_original,
        "layer_b_reproducibility_check": {
            "matches_original": layer_b_reproduces,
            "note": "Layer B was already 1-min-sourced in the original study; this re-run should "
                    "reproduce it near-exactly on immutable historical bars -- a drift here would "
                    "indicate a live-data/methodology inconsistency, not a resolution effect.",
        },
        "verdicts_1min": verdicts_1min,
        "verdicts_original": verdicts_original,
        "verdict_flags": flags,
        "disclosures": [
            "Layer A rebuild changes ONLY the option-bar source (t4_exit_matrix._load_bars' "
            "5-min disk cache -> live 1-min REST via exit_shape_parity_study.fetch_option_bars, "
            "shared helper _option_bars_1min_cache.fetch_1min_cached) -- strike selection (OTM-2, "
            "t4's own convention), fill-bar inclusion ('>=' entry_ts), C6 close-based structure-"
            "stop detection (unchanged, reads 5-min SPY closes -- structure_stop is 5-min-native "
            "by v15.3 design, not part of the resolution variable under test), shapes, buffers, "
            "and time_stop (15:40 ET, TIME_STOP_LAYER_A) are IDENTICAL to the original.",
            "Layer B is UNCHANGED code (sss.run_layer_b), re-run live -- reproducibility, not a "
            "resolution fix (it was already 1-min-sourced in the original study).",
            "This is a REPLICATION, not a new search: no cell, shape, buffer, or gate was added, "
            "removed, or re-picked. Any verdict change traces ONLY to the resolution swap.",
            "The 2026-07-09 TODAY EXHIBIT (excluded from all pass/fail layers in the original "
            "study by its own design) is NOT re-run here -- it was never a gating cell.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

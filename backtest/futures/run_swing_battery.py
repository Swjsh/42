"""run_swing_battery.py -- Phase-1 MES multiday swing battery orchestrator.

FUTURES-REVIVAL-PLAN-2026-07-02.md section 2f Phase 1: does the direction
alpha in the theta-killed seed pile (RRW-short, E2 context, structure
BOS/CHoCH) survive on MES at 1-5 day swing horizons? $0, no broker, no creds.

Pipeline: load cached Databento MES 1m (verified full ETH Globex, NOT
RTH-only -- see data-versions.jsonl provenance row this run appends) ->
resample daily + 4h-of-RTH -> extend the daily series past the cache's
2026-06-12 end with a yfinance ES=F gap-fill (disclosed lower-fidelity) ->
fetch daily VIX (regime split) -> run each seed's grid through the canonical
battery (backtest/futures/battery.py) -> write one scorecard JSON per seed to
analysis/recommendations/ + a ranking summary markdown.

Run: backtest/.venv/Scripts/python.exe backtest/futures/run_swing_battery.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO / "backtest" / "futures"))

from futures.data import (  # noqa: E402
    load_continuous_csv, rth_only, resample_daily, resample_4h_rth,
    fetch_vix_daily, fetch_es_daily_gap,
)
from futures.instruments import MES  # noqa: E402
from futures.seeds import rrw_seed, e2_context_seed, structure_seed  # noqa: E402
from futures import battery  # noqa: E402

MES_CSV = REPO / "backtest" / "data" / "futures" / "MES_1m_continuous.csv"
DERIVED_DIR = REPO / "backtest" / "data" / "futures" / "derived"
REC_DIR = REPO / "analysis" / "recommendations"
DATA_VERSIONS = REPO / "analysis" / "backtests" / "data-versions.jsonl"

OOS_CUT = dt.date(2026, 1, 1)
DAILY_HORIZONS = [(1, "1d"), (3, "3d"), (5, "5d")]
H4_HORIZONS = [(2, "1d"), (6, "3d"), (10, "5d")]   # ~2 4h-of-RTH bars/day


def log(msg: str) -> None:
    print(f"[{dt.datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def md5_of(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def append_data_version(row: dict) -> None:
    DATA_VERSIONS.parent.mkdir(parents=True, exist_ok=True)
    with DATA_VERSIONS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def load_and_prepare() -> dict:
    t0 = time.time()
    log(f"loading {MES_CSV.name} ...")
    raw = load_continuous_csv(str(MES_CSV))
    span = (str(raw["timestamp_et"].min()), str(raw["timestamp_et"].max()))
    log(f"loaded {len(raw)} 1m bars, span {span}, in {time.time()-t0:.1f}s")

    # VERIFIED (not assumed): the cache is full ETH Globex, not RTH-only --
    # the plan doc's premise was wrong (confirmed 2026-07-02 by the prior
    # PHASE1-swing-battery session AND independently re-verified this session:
    # first row 18:00 ET, RTH bars are 27.7% of the total). Real overnight/
    # weekend gap bars are therefore native to this cache for its covered
    # span -- no synthetic gap modeling needed through 2026-06-12.
    maintenance_break_empty = raw["timestamp_et"].dt.time.between(dt.time(17, 0), dt.time(17, 59)).sum() == 0
    has_overnight_prints = (raw["timestamp_et"].dt.hour == 2).any()
    is_full_eth = maintenance_break_empty and has_overnight_prints
    log(f"data-shape check: 17:00-18:00 ET maintenance-break gap empty={maintenance_break_empty}, "
        f"has 02:00 ET overnight prints={has_overnight_prints} -> full ETH Globex data = {is_full_eth} "
        f"(expect True; confirms this is NOT RTH-only, contrary to the plan doc's premise)")

    daily = resample_daily(raw)
    h4 = resample_4h_rth(raw)
    rth_1m = rth_only(raw)
    DERIVED_DIR.mkdir(parents=True, exist_ok=True)
    daily.to_csv(DERIVED_DIR / "MES_daily_rth_swingbattery2.csv", index=False)
    h4.to_csv(DERIVED_DIR / "MES_4h_rth_swingbattery2.csv", index=False)
    log(f"resampled: daily={len(daily)} bars, 4h-of-RTH={len(h4)} bars")

    # Gap-fill 2026-06-12 -> now via yfinance ES=F (disclosed lower-fidelity,
    # daily-only -- the 4h structure seed does NOT get this extension).
    cache_end = daily["date"].max()
    today = dt.date.today()
    daily_ext = daily
    gap_rows = 0
    try:
        gap = fetch_es_daily_gap(str(cache_end), str(today))
        gap = gap[gap["date"] > cache_end].reset_index(drop=True)
        if not gap.empty:
            seam_prior_close = float(daily["close"].iloc[-1])
            seam_next_open = float(gap["open"].iloc[0])
            log(f"yfinance ES=F gap-fill: {len(gap)} rows, {gap['date'].min()}..{gap['date'].max()}; "
                f"seam MES-close={seam_prior_close:.2f} -> ES-open={seam_next_open:.2f} "
                f"(delta={seam_next_open - seam_prior_close:+.2f}, sanity: should be a small realistic gap)")
            daily_ext = pd.concat([daily, gap[["timestamp_et", "date", "open", "high", "low", "close", "volume"]]],
                                   ignore_index=True)
            gap_rows = len(gap)
    except Exception as e:  # noqa: BLE001 -- gap-fill is best-effort, disclosed if it fails
        log(f"yfinance ES=F gap-fill FAILED ({e!r}) -- proceeding with cache-only daily series through {cache_end}")

    log("fetching daily VIX (regime split, yfinance ^VIX) ...")
    vix_df = fetch_vix_daily("2025-01-01", str(today + dt.timedelta(days=1)))
    vix_by_date = dict(zip(vix_df["date"], vix_df["vix_close"]))
    log(f"VIX daily rows: {len(vix_df)}, {vix_df['date'].min() if len(vix_df) else None}..{vix_df['date'].max() if len(vix_df) else None}")

    md5 = md5_of(MES_CSV)
    append_data_version({
        "ran_at": dt.datetime.now().isoformat(), "symbol": "mes_futures",
        "as_of": str(today), "status": "ok", "action": "phase1_swing_battery_2",
        "source": str(MES_CSV), "md5": md5, "rows_1m": len(raw), "span_et": list(span),
        "note": ("Second independent Phase-1 swing pass (session 2026-07-09) -- reusable "
                 "swing_sim.py module + canonical scorecards at analysis/recommendations/. "
                 "Cross-references the prior 2026-07-02 PHASE1-swing-battery (DOES_NOT_TRANSFER, "
                 "commits 3c31bf2/950a3b6, undocumented in CHANGELOG until this session). "
                 "Confirmed cache is full ETH Globex (not RTH-only, contrary to the plan doc's "
                 "premise) -- gap/stop fills through 2026-06-12 use native overnight bars. "
                 "Daily series extended 2026-06-12->now via yfinance ES=F (disclosed lower-"
                 "fidelity proxy, daily-only). VIX regime split via yfinance ^VIX."),
        "derived": [str(DERIVED_DIR / "MES_daily_rth_swingbattery2.csv"),
                    str(DERIVED_DIR / "MES_4h_rth_swingbattery2.csv")],
        "yfinance_gap_fill_rows": gap_rows, "vix_rows": len(vix_df),
    })
    log(f"data-versions.jsonl row appended (md5={md5[:12]}...)")

    return {"raw": raw, "daily": daily_ext, "daily_native_only": daily, "h4": h4,
            "rth_1m": rth_1m, "vix_by_date": vix_by_date, "gap_rows": gap_rows}


def run_seed_a(ctx: dict) -> dict:
    log("Seed A (RRW-short cohort, both directions) -- generating signals on daily bars ...")
    daily = ctx["daily"]
    signals = rrw_seed.generate_signals(daily)
    log(f"  {len(signals)} signals across {signals['combo_id'].nunique() if len(signals) else 0} combos "
        f"({(signals['direction']=='short').sum() if len(signals) else 0} short / "
        f"{(signals['direction']=='long').sum() if len(signals) else 0} long)")
    grid = [{"combo_id": c} for c in signals["combo_id"].unique()] if len(signals) else \
           [{"combo_id": c["wick_frac_min"]} for c in rrw_seed.build_grid()]
    if not len(signals):
        grid = [{"combo_id": (f"rrw_w{c['wick_frac_min']}_lb{c['break_lookback_bars']}_{c['stack_filter']}")}
                for c in rrw_seed.build_grid()]
    sc = battery.score_seed("rrw_short", grid, signals, daily, MES, DAILY_HORIZONS,
                             OOS_CUT, ctx["vix_by_date"])
    log(f"  Seed A verdict: {sc['verdict']} ({sc['n_clearing_cells']}/{sc['n_cells_tested']} cells clear)")
    return sc


def run_seed_b(ctx: dict) -> dict:
    log("Seed B (E2 at-level + VWAP-aligned context) -- generating signals on daily bars ...")
    daily = ctx["daily_native_only"]  # VWAP needs intraday data; native window only (through 2026-06-12)
    vwap_by_date = e2_context_seed.compute_session_vwap_by_date(ctx["rth_1m"])
    signals = e2_context_seed.generate_signals(daily, vwap_by_date)
    log(f"  {len(signals)} signals across {signals['combo_id'].nunique() if len(signals) else 0} combos "
        f"({(signals['direction']=='short').sum() if len(signals) else 0} short / "
        f"{(signals['direction']=='long').sum() if len(signals) else 0} long)")
    grid = [{"combo_id": f"e2_tol{t}"} for t in e2_context_seed.TOL_PCT]
    sc = battery.score_seed("e2_context", grid, signals, daily, MES, DAILY_HORIZONS,
                             OOS_CUT, ctx["vix_by_date"])
    log(f"  Seed B verdict: {sc['verdict']} ({sc['n_clearing_cells']}/{sc['n_cells_tested']} cells clear)")
    return sc


def run_seed_c(ctx: dict) -> dict:
    log("Seed C (BOS/CHoCH structure, standalone entry) -- generating signals on 4h-of-RTH bars ...")
    h4 = ctx["h4"]
    signals = structure_seed.generate_signals(h4)
    log(f"  {len(signals)} signals across {signals['combo_id'].nunique() if len(signals) else 0} combos "
        f"({(signals['direction']=='short').sum() if len(signals) else 0} short / "
        f"{(signals['direction']=='long').sum() if len(signals) else 0} long)")
    grid = [{"combo_id": f"structure_w{c['window']}_{c['trade_on']}"} for c in structure_seed.build_grid()]
    sc = battery.score_seed("structure_bos_choch", grid, signals, h4, MES, H4_HORIZONS,
                             OOS_CUT, ctx["vix_by_date"])
    log(f"  Seed C verdict: {sc['verdict']} ({sc['n_clearing_cells']}/{sc['n_cells_tested']} cells clear)")
    return sc


def write_scorecard(seed_slug: str, scorecard: dict, extra_meta: dict) -> Path:
    REC_DIR.mkdir(parents=True, exist_ok=True)
    out_path = REC_DIR / f"futures-swing-{seed_slug}.json"
    payload = {
        "rule_id": f"futures-swing-{seed_slug}", "phase": "1",
        "generated_at": dt.datetime.now().isoformat(),
        "spec_origin": "markdown/futures/FUTURES-REVIVAL-PLAN-2026-07-02.md section 2f Phase 1 / 2c",
        "prior_art": {
            "note": ("A PRIOR, more granular Phase-1 battery already ran on 2026-07-02 "
                     "(commits 3c31bf2, 950a3b6) at RTH-5m-signal/ETH-5m-fill granularity "
                     "covering substantially the same RRW-short and E2-context hypotheses "
                     "(plus daily structure as a FILTER, not a standalone entry). Verdict: "
                     "DOES_NOT_TRANSFER, 0/12 test cells cleared BH-FDR. That result was never "
                     "logged to CHANGELOG.md (fixed this session). THIS scorecard is a genuinely "
                     "independent pass at DAILY/4h-of-RTH signal granularity (per this work "
                     "order's explicit spec) using the new reusable swing_sim.py module -- "
                     "cross-reference before treating any PASS here as novel."),
            "path": "backtest/futures/analysis/PHASE1-swing-battery/RESULTS.md",
            "verdict": "DOES_NOT_TRANSFER",
        },
        **extra_meta,
        **scorecard,
    }
    out_path.write_text(json.dumps(payload, indent=1, default=str), encoding="utf-8")
    return out_path


def main() -> None:
    t_start = time.time()
    ctx = load_and_prepare()

    sc_a = run_seed_a(ctx)
    sc_b = run_seed_b(ctx)
    sc_c = run_seed_c(ctx)

    meta_daily = {"bar_timeframe": "daily_rth", "instrument": "MES",
                  "oos_cut": str(OOS_CUT), "horizons": DAILY_HORIZONS,
                  "stop_mult": battery.DEFAULT_STOP_MULT, "target_mult": battery.DEFAULT_TARGET_MULT,
                  "cost_per_side_usd": battery.DEFAULT_COST_PER_SIDE_USD,
                  "daily_series_extended_via_yfinance_es_gap_fill": ctx["gap_rows"] > 0,
                  "yfinance_gap_fill_rows": ctx["gap_rows"]}
    meta_daily_native = dict(meta_daily)
    meta_daily_native["daily_series_extended_via_yfinance_es_gap_fill"] = False
    meta_daily_native["note_e2_window"] = ("Runs on the NATIVE Databento window only (through "
                                            "2026-06-12) -- VWAP needs intraday RTH data, not fetched "
                                            "for the yfinance gap period.")
    meta_h4 = {"bar_timeframe": "4h_of_rth", "instrument": "MES",
               "oos_cut": str(OOS_CUT), "horizons": H4_HORIZONS,
               "stop_mult": battery.DEFAULT_STOP_MULT, "target_mult": battery.DEFAULT_TARGET_MULT,
               "cost_per_side_usd": battery.DEFAULT_COST_PER_SIDE_USD,
               "note": "Native Databento window only (through 2026-06-12); no yfinance extension at 4h."}

    path_a = write_scorecard("rrw_short", sc_a, meta_daily)
    path_b = write_scorecard("e2_context", sc_b, meta_daily_native)
    path_c = write_scorecard("structure_bos_choch", sc_c, meta_h4)
    log(f"scorecards written: {path_a.name}, {path_b.name}, {path_c.name}")

    log(f"TOTAL runtime: {time.time()-t_start:.1f}s")
    log(f"VERDICTS -- A(rrw_short)={sc_a['verdict']}  B(e2_context)={sc_b['verdict']}  "
        f"C(structure_bos_choch)={sc_c['verdict']}")


if __name__ == "__main__":
    main()

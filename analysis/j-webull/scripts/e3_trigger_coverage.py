"""E3 — Trigger-coverage audit: do the engine's triggers fire where J made money?

Per analysis/j-webull/EXPERIMENTS.md E3 (spec'd 2026-07-01, run same evening):
    Overlay the CURRENT engine's trigger firing points on 2025-26 SPY against the
    context cells of J's 2021-23 WeBull book (542 closed SPX/SPY-family episodes).
    J's ONLY positive-expectancy context: entry <=0.1% from a prior-day level
    (PDH/PDL/PDC) + VWAP-aligned + midday (11:00-14:00 was positive; 09:30-10:00 toxic).

    Question: does the engine's current coverage already express J's profit context,
    or is there an uncovered profitable cell?

Triggers audited (the armed set as of 2026-07-01):
  * core_bear / core_bull — the production engine (BEARISH_REJECTION +
    BULLISH_RECLAIM core scoring) via run_backtest(use_real_fills=True) with live
    params.json — the REAL trigger path, all gates included.
  * vwap_continuation — watcher pure core (detect_vwap_continuation_core),
    <=10:30 ET cutoff, one/day, put VIX-gate OFF (armed default).
  * vwap_reclaim_failed_break — watcher batch core, <=10:30 ET, one/day.
  * vix_regime_dayside — watcher pure core, 09:35-11:30 ET gate, one/day,
    causal VIX trailing-median(78) + slope5 on the continuous aligned series.
  * double_bottom_base_quiet — crypto.lib.chart_patterns.double_bottom_detector on a
    30-bar sliding window, conf<0.60, VIX<20, 30-min cooldown, long-only,
    09:35-15:55 ET. NOT_NEAR_NAMED omitted (same simplification as the committed
    real-fills scan — slightly OVER-counts this watcher's coverage; disclosed).

Context cells (same axes for J rows and engine entries):
  at_level    : |dist to nearest of PDH/PDL/PDC| <= 0.10%   (J: nearest_level_dist_pct)
  vwap_aligned: bull & above VWAP, or bear & below VWAP     (J: bias x vwap_side)
  tod window  : open 09:30-10:00 | morning 10:00-11:00 | midday 11:00-14:00 | late 14:00-16:00

Method disclosures (C4/C6/C22):
  * J cells use J's OWN dataset columns (2021-23 context join, IEX VWAP approximation);
    engine cells use the rig's 2025-26 master + typical-price session VWAP. STRUCTURE is
    compared across eras, never absolutes (C22). J's per-cell P&L is his real fills.
  * All engine context features are as-of the entry bar (C6: causal cumulative VWAP,
    prior-day levels from completed prior sessions only).
  * This is a COVERAGE audit (where triggers fire), not a P&L authority for the extra
    setups — their P&L authority stays with their own real-fills scorecards (C1).
  * VWAP for the watcher replays is typical-price ((H+L+C)/3) volume-weighted session
    cumulative; the watchers' internal _session_rth_vwap may differ marginally — counts
    within a cell can shift by a few signals, cell-level conclusions do not.

Rail-4 CLEAR: research read-only. Touches NO params/doctrine/orders/heartbeat/filters.

Run:
    backtest/.venv/Scripts/python.exe analysis/j-webull/scripts/e3_trigger_coverage.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_REPO = Path(__file__).resolve().parents[3]
for _p in (str(_REPO), str(_REPO / "backtest")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backtest.lib.watchers.vwap_continuation_watcher import (  # noqa: E402
    detect_vwap_continuation_core, TREND_BARS as VC_TREND_BARS,
    ENTRY_CUTOFF as VC_CUTOFF,
)
from backtest.lib.watchers.vwap_reclaim_failed_break_watcher import (  # noqa: E402
    detect_vwap_reclaim_failed_break_core,
)
from backtest.lib.watchers.vix_regime_dayside_watcher import (  # noqa: E402
    detect_vix_regime_dayside_core, causal_vix_median, vix_slope as vix_slope_arr,
    VIX_MEDIAN_BARS, VIX_SLOPE_BARS,
)

SPY_CSV = _REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-18.csv"
VIX_CSV = _REPO / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-18.csv"
J_CSV = _REPO / "analysis" / "j-webull" / "trades-normalized.csv"
OUT_JSON = _REPO / "analysis" / "j-webull" / "E3-trigger-coverage.json"
OUT_MD = _REPO / "analysis" / "j-webull" / "E3-trigger-coverage.md"

AT_LEVEL_PCT = 0.10          # <=0.1% from PDH/PDL/PDC
WINDOW_START = dt.date(2025, 1, 2)
WINDOW_END = dt.date(2026, 6, 18)

TOD_WINDOWS = [
    ("open", dt.time(9, 30), dt.time(10, 0)),
    ("morning", dt.time(10, 0), dt.time(11, 0)),
    ("midday", dt.time(11, 0), dt.time(14, 0)),
    ("late", dt.time(14, 0), dt.time(16, 0)),
]


def tod_window(t: dt.time) -> str:
    for name, a, b in TOD_WINDOWS:
        if a <= t < b:
            return name
    return "other"


def load_naive_et(csv_path: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_path)
    df["timestamp_et"] = (
        pd.to_datetime(df["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    return df.sort_values("timestamp_et").reset_index(drop=True)


# ── Market context on the 2025-26 master ─────────────────────────────────────
def build_context(spy: pd.DataFrame, vix: pd.DataFrame):
    """Per-RTH-bar context: session cumulative VWAP, prior-day levels, aligned VIX."""
    rth = spy[
        (spy["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    rth["date"] = rth["timestamp_et"].dt.date

    # Session cumulative typical-price VWAP (causal: cumsum within day)
    tp = (rth["high"] + rth["low"] + rth["close"]) / 3.0
    vol = rth["volume"].astype(float).clip(lower=1.0)
    grp = rth.groupby("date")
    rth["vwap"] = (tp * vol).groupby(rth["date"]).cumsum() / vol.groupby(rth["date"]).cumsum()

    # Prior-day levels (from completed prior RTH sessions only — C6)
    daily = grp.agg(h=("high", "max"), l=("low", "min"))
    closes = rth.groupby("date")["close"].last()
    daily["c"] = closes
    daily = daily.sort_index()
    prior = daily.shift(1)
    lvl_map = {d: (row["h"], row["l"], row["c"]) for d, row in prior.iterrows()
               if not np.isnan(row["h"])}
    rth["pdh"] = rth["date"].map(lambda d: lvl_map.get(d, (np.nan,) * 3)[0])
    rth["pdl"] = rth["date"].map(lambda d: lvl_map.get(d, (np.nan,) * 3)[1])
    rth["pdc"] = rth["date"].map(lambda d: lvl_map.get(d, (np.nan,) * 3)[2])

    # As-of aligned VIX (continuous, causal) + trailing median(78) + slope5
    v = vix[["timestamp_et", "close"]].rename(columns={"close": "vix"})
    rth = pd.merge_asof(rth.sort_values("timestamp_et"), v.sort_values("timestamp_et"),
                        on="timestamp_et", direction="backward")
    varr = rth["vix"].to_numpy(dtype=float)
    rth["vix_med"] = causal_vix_median(varr, VIX_MEDIAN_BARS)
    rth["vix_slp"] = vix_slope_arr(varr, VIX_SLOPE_BARS)
    return rth


def bar_features(row) -> dict:
    """Context-cell features for one entry bar (direction supplied separately)."""
    c = float(row["close"])
    dists = []
    for k in ("pdh", "pdl", "pdc"):
        lv = row[k]
        if lv is not None and not (isinstance(lv, float) and np.isnan(lv)) and lv > 0:
            dists.append(abs(c / float(lv) - 1.0) * 100.0)
    at_level = bool(dists and min(dists) <= AT_LEVEL_PCT)
    return {"at_level": at_level, "close": c, "vwap": float(row["vwap"]),
            "tod": tod_window(row["timestamp_et"].time())}


def classify_entry(rth: pd.DataFrame, ts, direction: str) -> dict | None:
    """Cell of an engine entry: features at the entry bar (as-of)."""
    day = rth[rth["date"] == ts.date()]
    at_or_before = day[day["timestamp_et"] <= ts]
    if at_or_before.empty:
        return None
    row = at_or_before.iloc[-1]
    f = bar_features(row)
    aligned = (direction == "bull" and f["close"] > f["vwap"]) or \
              (direction == "bear" and f["close"] < f["vwap"])
    return {"at_level": f["at_level"], "aligned": bool(aligned), "tod": f["tod"],
            "direction": direction}


# ── Trigger replays ──────────────────────────────────────────────────────────
def core_engine_entries() -> list[dict]:
    """Production engine trigger path (design-swarm invocation shape)."""
    from backtest.lib.orchestrator import run_backtest, _params_to_kwargs
    params = json.loads((_REPO / "automation/state/params.json").read_text(encoding="utf-8"))
    spy = pd.read_csv(SPY_CSV)
    vix = pd.read_csv(VIX_CSV)
    k = _params_to_kwargs(params, account_equity=2000.0)
    res = run_backtest(spy, vix, start_date=WINDOW_START, end_date=WINDOW_END,
                       use_real_fills=True, **k)
    out = []
    for t in res.trades:
        side = getattr(t, "side", "P")
        out.append({"trigger": "core_bull" if side == "C" else "core_bear",
                    "ts": pd.Timestamp(t.entry_time_et).tz_localize(None)
                    if pd.Timestamp(t.entry_time_et).tzinfo else pd.Timestamp(t.entry_time_et),
                    "direction": "bull" if side == "C" else "bear"})
    return out


def watcher_entries(rth: pd.DataFrame) -> list[dict]:
    out: list[dict] = []
    try:
        from crypto.lib.chart_patterns import Bar, double_bottom_detector
        db_ok = True
    except ImportError:
        db_ok = False

    for d, day in rth.groupby("date"):
        day = day.reset_index(drop=True)
        n = len(day)
        if n < VC_TREND_BARS + 1:
            continue
        closes = day["close"].to_numpy(dtype=float)
        highs = day["high"].to_numpy(dtype=float)
        lows = day["low"].to_numpy(dtype=float)
        vwap = day["vwap"].to_numpy(dtype=float)
        times = [t.time() for t in day["timestamp_et"]]

        # vwap_continuation: first qualifying bar <= 10:30, one/day (put VIX gate OFF)
        for j in range(VC_TREND_BARS, n):
            if times[j] > VC_CUTOFF:
                break
            r = detect_vwap_continuation_core(closes, highs, lows, vwap, j)
            if r is not None:
                out.append({"trigger": "vwap_continuation",
                            "ts": day["timestamp_et"].iloc[j],
                            "direction": "bull" if r.side == "C" else "bear"})
                break

        # vwap_reclaim_failed_break: batch core, one/day
        r = detect_vwap_reclaim_failed_break_core(closes, highs, lows, vwap, times)
        if r is not None:
            # locate the reclaim bar: first bar matching the returned entry close after break
            # (core doesn't return the index; recover it by re-scanning closes)
            idx = None
            for j in range(VC_TREND_BARS, n):
                if times[j] > VC_CUTOFF:
                    break
                if abs(float(closes[j]) - r.entry) < 1e-9:
                    idx = j
            if idx is not None:
                out.append({"trigger": "vwap_reclaim_failed_break",
                            "ts": day["timestamp_et"].iloc[idx],
                            "direction": "bull" if r.side == "C" else "bear"})

        # vix_regime_dayside: one/day
        vixv = day["vix"].to_numpy(dtype=float)
        vmed = day["vix_med"].to_numpy(dtype=float)
        vslp = day["vix_slp"].to_numpy(dtype=float)
        r = detect_vix_regime_dayside_core(closes, highs, lows, vwap, times, vixv, vmed, vslp)
        if r is not None:
            idx = None
            for j in range(VC_TREND_BARS, n):
                if abs(float(closes[j]) - r.entry) < 1e-9 and dt.time(9, 35) <= times[j] <= dt.time(11, 30):
                    idx = j
                    break
            if idx is not None:
                out.append({"trigger": "vix_regime_dayside",
                            "ts": day["timestamp_et"].iloc[idx],
                            "direction": "bull" if r.side == "C" else "bear"})

        # double_bottom_base_quiet: sliding window, conf<0.60, VIX<20, 30-min cooldown
        if db_ok:
            last_fire = None
            for j in range(10, n):
                t = times[j]
                if t < dt.time(9, 35) or t > dt.time(15, 55):
                    continue
                if float(vixv[j]) >= 20.0:
                    continue
                ts_j = day["timestamp_et"].iloc[j]
                if last_fire is not None and (ts_j - last_fire).total_seconds() < 30 * 60:
                    continue
                w = day.iloc[max(0, j - 29): j + 1]
                bars = [Bar(open_time=pd.Timestamp(rr["timestamp_et"]).tz_localize("UTC").to_pydatetime(),
                            open=float(rr["open"]), high=float(rr["high"]), low=float(rr["low"]),
                            close=float(rr["close"]), volume=float(rr["volume"]),
                            granularity_seconds=300, source="spy_5m")
                        for _, rr in w.iterrows()]
                hit = double_bottom_detector(bars)
                if hit is None or hit.confidence >= 0.60:
                    continue
                out.append({"trigger": "double_bottom_base_quiet", "ts": ts_j,
                            "direction": "bull"})
                last_fire = ts_j
    return out


# ── J cells ──────────────────────────────────────────────────────────────────
def j_cells() -> pd.DataFrame:
    j = pd.read_csv(J_CSV, parse_dates=["entry_ts_et"])
    j = j[(j["is_family"] == True) & (j["closed"] == True) & (j["ctx_ok"] == True)].copy()  # noqa: E712
    j["at_level"] = j["nearest_level_dist_pct"].abs() <= AT_LEVEL_PCT
    j["aligned"] = ((j["bias"] == "bull") & (j["vwap_side"] == "above")) | \
                   ((j["bias"] == "bear") & (j["vwap_side"] == "below"))
    j["tod"] = j["entry_ts_et"].dt.time.map(tod_window)
    g = j.groupby(["at_level", "aligned", "tod"])["pnl"].agg(["count", "sum", "mean"])
    g.columns = ["j_n", "j_total_pnl", "j_exp_per_trade"]
    return g.round(2)


def main() -> int:
    print("[E3] loading masters + building context...")
    spy = load_naive_et(SPY_CSV)
    vix = load_naive_et(VIX_CSV)
    rth = build_context(spy, vix)

    print("[E3] replaying 4 extra-setup watchers...")
    extra = watcher_entries(rth)
    print(f"[E3] extra-setup entries: {len(extra)}")

    print("[E3] running production engine (run_backtest, real fills, full window)...")
    core = core_engine_entries()
    print(f"[E3] core engine entries: {len(core)}")

    entries = core + extra
    rows = []
    for e in entries:
        cell = classify_entry(rth, e["ts"], e["direction"])
        if cell is None:
            continue
        rows.append({"trigger": e["trigger"], **cell, "ts": str(e["ts"])})
    edf = pd.DataFrame(rows)

    jc = j_cells()

    # Matrix: cell x trigger counts
    triggers = ["core_bear", "core_bull", "vwap_continuation",
                "vwap_reclaim_failed_break", "vix_regime_dayside",
                "double_bottom_base_quiet"]
    matrix = {}
    n_engine_total = len(edf)
    for (at_lvl, aligned, tod), jrow in jc.iterrows():
        key = f"at_level={'Y' if at_lvl else 'N'}|aligned={'Y' if aligned else 'N'}|{tod}"
        sub = edf[(edf["at_level"] == at_lvl) & (edf["aligned"] == aligned) & (edf["tod"] == tod)]
        cnt = {t: int((sub["trigger"] == t).sum()) for t in triggers}
        matrix[key] = {
            "j_n": int(jrow["j_n"]), "j_total_pnl": float(jrow["j_total_pnl"]),
            "j_exp_per_trade": float(jrow["j_exp_per_trade"]),
            "engine_total": int(len(sub)),
            "engine_share_pct": round(100.0 * len(sub) / n_engine_total, 1) if n_engine_total else 0.0,
            **cnt,
        }
    # Engine cells with no J row (engine fires where J never traded)
    for (at_lvl, aligned, tod), sub in edf.groupby(["at_level", "aligned", "tod"]):
        key = f"at_level={'Y' if at_lvl else 'N'}|aligned={'Y' if aligned else 'N'}|{tod}"
        if key not in matrix:
            cnt = {t: int((sub["trigger"] == t).sum()) for t in triggers}
            matrix[key] = {"j_n": 0, "j_total_pnl": 0.0, "j_exp_per_trade": 0.0,
                           "engine_total": int(len(sub)),
                           "engine_share_pct": round(100.0 * len(sub) / n_engine_total, 1),
                           **cnt}

    # J profit cells (n>=15 and positive expectancy), coverage verdict
    profit_cells = sorted(
        [(k, v) for k, v in matrix.items() if v["j_n"] >= 15 and v["j_exp_per_trade"] > 0],
        key=lambda kv: kv[1]["j_total_pnl"], reverse=True)
    uncovered = [(k, v) for k, v in profit_cells if v["engine_total"] == 0]
    thin = [(k, v) for k, v in profit_cells if 0 < v["engine_total"] < 10]

    # The named J profit cell (at-level + aligned + midday)
    target_key = "at_level=Y|aligned=Y|midday"
    target = matrix.get(target_key, {})

    # Engine concentration in J's toxic open window
    open_cells = {k: v for k, v in matrix.items() if k.endswith("|open")}
    engine_open_share = round(sum(v["engine_share_pct"] for v in open_cells.values()), 1)

    verdict_lines = []
    if uncovered:
        top_k, top_v = uncovered[0]
        verdict_lines.append(
            f"LARGEST UNCOVERED PROFITABLE CELL: {top_k} — J n={top_v['j_n']}, "
            f"total +${top_v['j_total_pnl']:.0f}, exp +${top_v['j_exp_per_trade']:.1f}/tr; "
            f"engine entries here 2025-26: {top_v['engine_total']}.")
    elif thin:
        top_k, top_v = thin[0]
        verdict_lines.append(
            f"NO fully-uncovered profitable cell; THINNEST-covered profitable cell: {top_k} — "
            f"J exp +${top_v['j_exp_per_trade']:.1f}/tr on n={top_v['j_n']}, engine only "
            f"{top_v['engine_total']} entries ({top_v['engine_share_pct']}% of engine flow).")
    else:
        verdict_lines.append("All J profitable cells (n>=15, +exp) have >=10 engine entries — "
                             "coverage already expresses J's profit context.")
    if target:
        verdict_lines.append(
            f"J PROFIT-CELL ({target_key}): J n={target.get('j_n', 0)}, "
            f"exp ${target.get('j_exp_per_trade', 0):+.1f}/tr; engine entries: "
            f"{target.get('engine_total', 0)} ({target.get('engine_share_pct', 0)}% of engine flow).")
    verdict_lines.append(f"Engine flow in J's TOXIC open window (09:30-10:00): {engine_open_share}% "
                         f"(J there: -$35.9/tr on 24% of his volume).")

    result = {
        "experiment": "E3_trigger_coverage",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "window_2025_26": [str(WINDOW_START), str(WINDOW_END)],
        "at_level_threshold_pct": AT_LEVEL_PCT,
        "n_engine_entries_total": n_engine_total,
        "n_engine_by_trigger": {t: int((edf["trigger"] == t).sum()) for t in triggers},
        "j_population": "542 closed SPX/SPY-family ctx_ok episodes (2021-23, J's real fills)",
        "matrix": matrix,
        "j_profit_cells_n15_positive": [k for k, _ in profit_cells],
        "uncovered_profit_cells": [k for k, _ in uncovered],
        "thin_profit_cells_lt10": [k for k, _ in thin],
        "verdict": verdict_lines,
        "caveats": [
            "C22: J cells are 2021-23 SPX/SPY context; engine cells are 2025-26 SPY. Structure port only.",
            "Coverage audit ONLY — extra-setup P&L authority remains their own real-fills scorecards (C1).",
            "double_bottom replay omits NOT_NEAR_NAMED (over-counts that watcher's coverage slightly).",
            "Watcher-replay VWAP = typical-price session cumulative; marginal count drift possible vs live wrappers.",
            "core engine = run_backtest(use_real_fills=True) with live params.json (Safe) — the real gate cascade.",
        ],
        "entries_sample": rows[:50],
    }
    OUT_JSON.write_text(json.dumps(result, indent=2), encoding="utf-8")

    # Markdown
    md = ["# E3 — Trigger-coverage audit (engine 2025-26 vs J's profit context 2021-23)",
          "",
          f"> Generated {result['generated_at']} by `scripts/e3_trigger_coverage.py`. "
          f"JSON twin: `E3-trigger-coverage.json`.",
          "",
          "## Verdict", ""]
    md += [f"- {v}" for v in verdict_lines]
    md += ["", "## Coverage matrix (context cell x trigger)", "",
           "| Cell | J n | J total $ | J $/tr | Engine n | Engine % | core_bear | core_bull | vwap_cont | vwap_reclaim_fb | vix_dayside | double_bottom |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for k in sorted(matrix, key=lambda x: -matrix[x]["j_total_pnl"]):
        v = matrix[k]
        md.append(f"| {k} | {v['j_n']} | {v['j_total_pnl']:+.0f} | {v['j_exp_per_trade']:+.1f} "
                  f"| {v['engine_total']} | {v['engine_share_pct']}% | {v['core_bear']} | {v['core_bull']} "
                  f"| {v['vwap_continuation']} | {v['vwap_reclaim_failed_break']} "
                  f"| {v['vix_regime_dayside']} | {v['double_bottom_base_quiet']} |")
    md += ["", "## Engine totals by trigger", ""]
    for t, nn in result["n_engine_by_trigger"].items():
        md.append(f"- {t}: {nn}")
    md += ["", "## Caveats", ""] + [f"- {c}" for c in result["caveats"]] + [""]
    OUT_MD.write_text("\n".join(md), encoding="utf-8")

    print("\n".join(verdict_lines))
    print(f"written: {OUT_JSON.relative_to(_REPO)} + {OUT_MD.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

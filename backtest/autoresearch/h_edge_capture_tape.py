"""H — does the SIP tape in the minutes BEFORE the engine's own entries separate
its winners from its losers?

Motivation (markdown/research/BACKTESTING-PLAYBOOK.md, STRATEGY-BACKLOG.md header):
64 new signal families died to theta. The only kind of improvement that has
survived in this repo is a FILTER on an already-live edge, not a new entry
signal. This script asks whether pre-entry tape microstructure (signed-volume
share, big-print share, an absorption-ish measure, and the realized 300s
return sign) is such a filter for the engine's own 593 real journal trades
(journal/trades.csv).

Data: journal/trades.csv (date, time_entry ET, setup, c_or_p, dollar_pnl, ...).
c_or_p: C = long bias (engine wants tape flow aligned UP), P = short bias
(engine wants tape flow aligned DOWN). All features are computed strictly
from trades with t_ns <= entry_ns (no look-ahead, C6) over the 300s window
immediately preceding the recorded time_entry.

Tape source: backtest/tools/fetch_sip_tape.py (fetch_trades/fetch_quotes/
sign_trades — READ ONLY, not modified). For the 20 sessions already fully
cached as whole-day files (2026-08-10..2026-09-04), loads via
fetch_day_signed_tape() from h3_ofi_latency.py (READ ONLY) and slices, to
avoid re-fetching a whole day for a 5-minute window. All other trade dates
fetch a tight [entry-300s, entry] window directly through fetch_sip_tape's
own disk cache (idempotent, retries handled inside that module).

This file and analysis/recommendations/h-edge-capture-tape.json are the only
artifacts this script owns/writes. Another agent concurrently owns
backtest/autoresearch/h1_absorption_at_levels.py — not touched here.

Method:
  1. Coverage pass: for every trade, get the signed tape for
     [entry-300s, entry). Whole-day-cached dates load from the day file;
     others fetch the tight window via the module's own REST+cache path.
     Any trade whose window cannot be built (API failure, empty tape) is
     COUNTED and reported, never silently dropped from the denominator.
  2. Per-trade features (direction-aligned; "aligned" = signed w.r.t. the
     trade's own bias, C=+1/P=-1):
       - sv_share_60s / sv_share_300s: aligned signed-volume share of total
         volume over the trailing 60s / 300s.
       - big_share_60s / big_share_300s: share of volume from prints >= the
         day's own 95th-percentile trade size, aligned signed.
       - absorb_300s: aligned signed volume over the 300s window divided by
         |price progress in ticks| ($0.01 ticks) over that window (large
         value = a lot of aggressor volume moved price very little = classic
         "absorption"; undefined/inf when price didn't move, handled as NaN).
       - ret_sign_300s: sign of the realized 300s return, relative to trade
         direction (+1 = tape already moved WITH the trade's direction going
         into entry, -1 = engine entering against the recent move).
  3. Outcome: winner = dollar_pnl > 0 (also continuous dollar_pnl).
  4. Per setup family (BULLISH_RECLAIM_RIDE_THE_RIBBON n=337,
     BEARISH_REJECTION_RIDE_THE_RIBBON n=136, VWAP_CONTINUATION n=45, REST
     pooled) x per feature: AUC(feature -> winner), tercile mean $PnL,
     Spearman corr(feature, dollar_pnl), n.
  5. NULL: within each setup, shuffle winner labels 2,000x, recompute AUC
     each time -> report the 95th percentile of that null AUC distribution,
     so real AUC can be judged against "AUC by luck" at this n.
  6. Disclosure: total feature x setup cell count, single-regime caveat,
     conditional-population caveat (entries are pre-filtered by the engine).

No LLM calls. No tuning after seeing outcomes — features/cuts are fixed by
this file's own docstring before the run.
"""

from __future__ import annotations

import csv
import json
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from fetch_sip_tape import fetch_quotes, fetch_trades, sign_trades  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from h3_ofi_latency import fetch_day_signed_tape  # noqa: E402  (READ-ONLY reuse)

ET = ZoneInfo("America/New_York")
UTC = timezone.utc
SYMBOL = "SPY"

TRADES_CSV = Path(__file__).resolve().parents[2] / "journal" / "trades.csv"
OUT_PATH = (
    Path(__file__).resolve().parents[2]
    / "analysis"
    / "recommendations"
    / "h-edge-capture-tape.json"
)

WINDOW_SEC = 300
LOOKBACKS_SEC = [60, 300]
BIG_PRINT_PCTILE = 95.0
TICK = 0.01

# Whole-day cache already present (per task spec) -> use fetch_day_signed_tape
# instead of re-fetching a tight window.
WHOLE_DAY_CACHED = {
    "2026-08-10", "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14",
    "2026-08-17", "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21",
    "2026-08-24", "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28",
    "2026-08-31", "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
}

SETUP_BUCKETS = {
    "BULLISH_RECLAIM_RIDE_THE_RIBBON": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
    "BEARISH_REJECTION_RIDE_THE_RIBBON": "BEARISH_REJECTION_RIDE_THE_RIBBON",
    "VWAP_CONTINUATION": "VWAP_CONTINUATION",
}
REST_BUCKET = "REST_POOLED"

FEATURES = [
    "sv_share_60s",
    "sv_share_300s",
    "big_share_60s",
    "big_share_300s",
    "absorb_300s",
    "ret_sign_300s",
]

N_SHUFFLE = 2000
RNG_SEED = 42


# --------------------------------------------------------------------------------
# Journal loading
# --------------------------------------------------------------------------------


@dataclass
class Trade:
    idx: int
    date: str
    time_entry: str
    setup: str
    c_or_p: str
    dollar_pnl: float
    dir_sign: int  # +1 for C (long bias), -1 for P (short bias)


def load_trades(path: Path) -> list[Trade]:
    trades: list[Trade] = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            date = (row.get("date") or "").strip()
            time_entry = (row.get("time_entry") or "").strip()
            setup = (row.get("setup") or "").strip()
            c_or_p = (row.get("c_or_p") or "").strip().upper()
            pnl_raw = (row.get("dollar_pnl") or "").strip()
            if not date or not time_entry or c_or_p not in ("C", "P") or not pnl_raw:
                continue
            try:
                pnl = float(pnl_raw)
            except ValueError:
                continue
            dir_sign = 1 if c_or_p == "C" else -1
            trades.append(
                Trade(
                    idx=i,
                    date=date,
                    time_entry=time_entry,
                    setup=setup,
                    c_or_p=c_or_p,
                    dollar_pnl=pnl,
                    dir_sign=dir_sign,
                )
            )
    return trades


def setup_bucket(setup: str) -> str:
    return SETUP_BUCKETS.get(setup, REST_BUCKET)


def entry_ns(date: str, time_entry: str) -> int:
    y, m, d = (int(x) for x in date.split("-"))
    parts = [int(x) for x in time_entry.strip().split(":")]
    if len(parts) == 2:
        parts.append(0)  # trades.csv sometimes logs HH:MM without seconds
    hh, mm, ss = parts
    dt_et = datetime(y, m, d, hh, mm, ss, tzinfo=ET)
    dt_utc = dt_et.astimezone(UTC)
    return int(dt_utc.timestamp() * 1_000_000_000)


# --------------------------------------------------------------------------------
# Tape window retrieval (whole-day cache vs tight-window fetch)
# --------------------------------------------------------------------------------

_day_tape_cache: dict[str, pd.DataFrame] = {}


def get_window_signed_tape(date: str, entry_t_ns: int) -> pd.DataFrame:
    """Signed trade tape strictly for (entry-WINDOW_SEC, entry_t_ns]."""
    lo_ns = entry_t_ns - WINDOW_SEC * 1_000_000_000

    if date in WHOLE_DAY_CACHED:
        if date not in _day_tape_cache:
            _day_tape_cache[date] = fetch_day_signed_tape(date).signed
        signed = _day_tape_cache[date]
    else:
        entry_dt_utc = datetime.fromtimestamp(entry_t_ns / 1e9, tz=UTC)
        lo_dt_utc = datetime.fromtimestamp(lo_ns / 1e9, tz=UTC)
        trades = fetch_trades(SYMBOL, lo_dt_utc, entry_dt_utc)
        quotes = fetch_quotes(SYMBOL, lo_dt_utc, entry_dt_utc)
        signed = sign_trades(trades, quotes)

    ts = signed["t_ns"].to_numpy()
    lo_idx = np.searchsorted(ts, lo_ns, side="right")
    hi_idx = np.searchsorted(ts, entry_t_ns, side="right")
    return signed.iloc[lo_idx:hi_idx].reset_index(drop=True)


# --------------------------------------------------------------------------------
# Feature computation
# --------------------------------------------------------------------------------


def _slice_last_seconds(window: pd.DataFrame, entry_t_ns: int, seconds: int) -> pd.DataFrame:
    lo_ns = entry_t_ns - seconds * 1_000_000_000
    ts = window["t_ns"].to_numpy()
    lo_idx = np.searchsorted(ts, lo_ns, side="right")
    return window.iloc[lo_idx:].reset_index(drop=True) if lo_idx == 0 else window.iloc[lo_idx:].reset_index(drop=True)


def compute_features(window: pd.DataFrame, entry_t_ns: int, dir_sign: int) -> dict[str, float | None]:
    out: dict[str, float | None] = {f: None for f in FEATURES}
    if window.empty:
        return out

    total_vol_all = window["size"].sum()
    big_thresh = np.percentile(window["size"].to_numpy(), BIG_PRINT_PCTILE) if len(window) > 0 else None

    for sec in LOOKBACKS_SEC:
        sub = _slice_last_seconds(window, entry_t_ns, sec)
        key_sv = f"sv_share_{sec}s"
        key_big = f"big_share_{sec}s"
        if sub.empty:
            continue
        total_vol = sub["size"].sum()
        if total_vol > 0:
            aligned_signed_vol = dir_sign * sub["signed_size"].sum()
            out[key_sv] = float(aligned_signed_vol / total_vol)
        if big_thresh is not None:
            big_mask = sub["size"].to_numpy() >= big_thresh
            big_sub = sub.loc[big_mask]
            big_total = big_sub["size"].sum()
            if big_total > 0:
                aligned_big_signed = dir_sign * big_sub["signed_size"].sum()
                out[key_big] = float(aligned_big_signed / big_total)

    # absorb_300s: aligned signed volume over full window / |price progress in ticks|
    if len(window) >= 2 and total_vol_all > 0:
        px_start = float(window["price"].iloc[0])
        px_end = float(window["price"].iloc[-1])
        ticks_moved = abs(px_end - px_start) / TICK
        aligned_signed_vol_full = dir_sign * window["signed_size"].sum()
        if ticks_moved > 0:
            out["absorb_300s"] = float(aligned_signed_vol_full / ticks_moved)
        else:
            out["absorb_300s"] = None  # no price progress -> ratio undefined, not "infinite absorption"

        ret = (px_end - px_start) / px_start if px_start else 0.0
        realized_sign = 0
        if ret > 0:
            realized_sign = 1
        elif ret < 0:
            realized_sign = -1
        out["ret_sign_300s"] = float(dir_sign * realized_sign)

    return out


# --------------------------------------------------------------------------------
# Stats: AUC, shuffle null, tercile PnL, Spearman
# --------------------------------------------------------------------------------


def auc_score(feature_vals: np.ndarray, labels: np.ndarray) -> float | None:
    """Mann-Whitney U based AUC for feature -> binary label (1=winner)."""
    mask = ~np.isnan(feature_vals)
    fv = feature_vals[mask]
    lb = labels[mask]
    n1 = int((lb == 1).sum())
    n0 = int((lb == 0).sum())
    if n1 == 0 or n0 == 0:
        return None
    order = np.argsort(fv, kind="mergesort")
    ranks = np.empty(len(fv), dtype=float)
    # average ranks for ties
    sorted_vals = fv[order]
    ranks_sorted = np.empty(len(fv), dtype=float)
    i = 0
    while i < len(fv):
        j = i
        while j + 1 < len(fv) and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0
        ranks_sorted[i : j + 1] = avg_rank
        i = j + 1
    ranks[order] = ranks_sorted
    sum_ranks_pos = ranks[lb == 1].sum()
    u = sum_ranks_pos - n1 * (n1 + 1) / 2.0
    auc = u / (n1 * n0)
    return float(auc)


def shuffle_null_95th(feature_vals: np.ndarray, labels: np.ndarray, n_shuffle: int, rng: np.random.Generator) -> float | None:
    mask = ~np.isnan(feature_vals)
    fv = feature_vals[mask]
    lb = labels[mask].copy()
    n1 = int((lb == 1).sum())
    n0 = int((lb == 0).sum())
    if n1 == 0 or n0 == 0 or len(fv) < 4:
        return None
    aucs = np.empty(n_shuffle, dtype=float)
    for k in range(n_shuffle):
        shuffled = rng.permutation(lb)
        a = auc_score(fv, shuffled)
        aucs[k] = a if a is not None else 0.5
    return float(np.percentile(aucs, 95))


def tercile_pnl(feature_vals: np.ndarray, pnl_vals: np.ndarray) -> dict:
    mask = ~np.isnan(feature_vals)
    fv = feature_vals[mask]
    pv = pnl_vals[mask]
    n = len(fv)
    if n < 6:
        return {"n": int(n), "terciles": None}
    order = np.argsort(fv, kind="mergesort")
    fv_sorted_idx = order
    thirds = np.array_split(fv_sorted_idx, 3)
    result = []
    for t_idx, part in enumerate(thirds):
        result.append(
            {
                "tercile": t_idx + 1,
                "n": int(len(part)),
                "mean_pnl": float(pv[part].mean()) if len(part) else None,
                "feature_range": [float(fv[part].min()), float(fv[part].max())] if len(part) else None,
            }
        )
    return {"n": int(n), "terciles": result}


def spearman_corr(feature_vals: np.ndarray, pnl_vals: np.ndarray) -> dict:
    mask = ~np.isnan(feature_vals)
    fv = feature_vals[mask]
    pv = pnl_vals[mask]
    if len(fv) < 4:
        return {"n": int(len(fv)), "rho": None, "p": None}
    rho, p = stats.spearmanr(fv, pv)
    return {"n": int(len(fv)), "rho": float(rho), "p": float(p)}


# --------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------


def main() -> int:
    t_start = time.time()
    trades = load_trades(TRADES_CSV)
    total = len(trades)
    print(f"[h-edge-capture-tape] loaded {total} valid trades from {TRADES_CSV}", flush=True)

    rows: list[dict] = []
    failures: list[dict] = []

    for n, tr in enumerate(trades, 1):
        try:
            t_ns = entry_ns(tr.date, tr.time_entry)
            window = get_window_signed_tape(tr.date, t_ns)
            if window.empty:
                failures.append({"idx": tr.idx, "date": tr.date, "time_entry": tr.time_entry, "reason": "empty_window"})
                if n % 25 == 0 or n == total:
                    print(f"[h-edge-capture-tape] {n}/{total} processed, {len(failures)} failures so far", flush=True)
                continue
            feats = compute_features(window, t_ns, tr.dir_sign)
            row = {
                "idx": tr.idx,
                "date": tr.date,
                "setup": tr.setup,
                "bucket": setup_bucket(tr.setup),
                "c_or_p": tr.c_or_p,
                "dollar_pnl": tr.dollar_pnl,
                "winner": 1 if tr.dollar_pnl > 0 else 0,
                **feats,
            }
            rows.append(row)
        except Exception as exc:  # noqa: BLE001 - must count, never silently skip
            failures.append(
                {
                    "idx": tr.idx,
                    "date": tr.date,
                    "time_entry": tr.time_entry,
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"[h-edge-capture-tape] FAILED trade idx={tr.idx} {tr.date} {tr.time_entry}: {exc}", flush=True)
            traceback.print_exc()
        if n % 25 == 0 or n == total:
            elapsed = time.time() - t_start
            print(f"[h-edge-capture-tape] {n}/{total} processed ({elapsed:.0f}s elapsed), {len(failures)} failures so far", flush=True)

    covered = len(rows)
    print(
        f"[h-edge-capture-tape] coverage: {covered}/{total} trades covered "
        f"({total - covered} uncovered)",
        flush=True,
    )

    df = pd.DataFrame(rows)
    rng = np.random.default_rng(RNG_SEED)

    buckets = list(SETUP_BUCKETS.values()) + [REST_BUCKET]
    results: dict[str, dict] = {}
    n_cells = 0

    for bucket in buckets:
        sub = df[df["bucket"] == bucket]
        if sub.empty:
            continue
        bucket_result: dict[str, dict] = {}
        labels = sub["winner"].to_numpy()
        pnl = sub["dollar_pnl"].to_numpy()
        for feat in FEATURES:
            n_cells += 1
            fv = sub[feat].to_numpy(dtype=float)
            real_auc = auc_score(fv, labels)
            null_95 = shuffle_null_95th(fv, labels, N_SHUFFLE, rng)
            tercile = tercile_pnl(fv, pnl)
            spearman = spearman_corr(fv, pnl)
            n_valid = int((~np.isnan(fv)).sum())
            bucket_result[feat] = {
                "n_valid": n_valid,
                "auc": real_auc,
                "null_auc_95th_pctile": null_95,
                "beats_null": (real_auc is not None and null_95 is not None and real_auc > null_95),
                "tercile_pnl": tercile,
                "spearman": spearman,
            }
            print(
                f"[h-edge-capture-tape] {bucket:32s} {feat:16s} n={n_valid:4d} "
                f"AUC={real_auc if real_auc is None else round(real_auc, 4)} "
                f"null95={null_95 if null_95 is None else round(null_95, 4)} "
                f"rho={spearman['rho'] if spearman['rho'] is None else round(spearman['rho'], 4)} "
                f"p={spearman['p'] if spearman['p'] is None else round(spearman['p'], 4)}",
                flush=True,
            )
        results[bucket] = {"n": int(len(sub)), "features": bucket_result}

    any_beats_null = any(
        results[b]["features"][f]["beats_null"]
        for b in results
        for f in FEATURES
        if results[b]["features"][f]["beats_null"]
    )

    output = {
        "meta": {
            "generated_at_utc": datetime.now(tz=UTC).isoformat(),
            "trades_csv": str(TRADES_CSV),
            "window_sec": WINDOW_SEC,
            "lookbacks_sec": LOOKBACKS_SEC,
            "features": FEATURES,
            "n_shuffle": N_SHUFFLE,
            "rng_seed": RNG_SEED,
            "big_print_pctile": BIG_PRINT_PCTILE,
        },
        "coverage": {
            "total_trades": total,
            "covered_trades": covered,
            "uncovered_trades": total - covered,
            "failures": failures,
        },
        "disclosure": {
            "n_feature_x_setup_cells": n_cells,
            "single_regime_caveat": (
                "All trades are 2026-04-29..2026-09-04 (~4.5 months), a single "
                "volatility/trend regime. No claim generalizes beyond it without "
                "an out-of-regime replication."
            ),
            "conditional_population_caveat": (
                "Entries were pre-selected by the engine's own setup filters. "
                "This measures whether tape ADDS separation ON TOP of that "
                "existing filter, not whether tape alone predicts SPY moves."
            ),
            "multiple_testing_caveat": (
                f"{n_cells} feature x setup cells tested; no single-cell p-value "
                "should be read as significant without correcting for this. The "
                "shuffle null's 95th percentile is per-cell, not FWER-corrected."
            ),
        },
        "results_by_setup": results,
        "verdict": (
            "at least one feature x setup cell's real AUC exceeds its own "
            "shuffle-null 95th percentile"
            if any_beats_null
            else "NULL: no feature x setup cell's real AUC exceeds its own "
            "shuffle-null 95th percentile -- no tape feature tested separates "
            "this engine's winners from losers beyond chance at this n"
        ),
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, sort_keys=False)

    print(f"[h-edge-capture-tape] wrote {OUT_PATH}", flush=True)
    print(f"[h-edge-capture-tape] VERDICT: {output['verdict']}", flush=True)
    print(f"[h-edge-capture-tape] total elapsed: {time.time() - t_start:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

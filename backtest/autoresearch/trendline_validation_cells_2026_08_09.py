"""trendline_validation_cells_2026_08_09.py -- runs the 4 cells frozen in
`analysis/recommendations/prereg-trendline-engine-validation-2026-08-09.json`
(committed a6cd262b, BEFORE this file existed).

CELL A: what does the ALREADY-LIVE trendline_rejection bear trigger contribute, over the
        full population (not just the 2026-08-06 anecdote)? Pure measurement/attribution.
CELL B: bull-side trendline-reclaim counterfactual (the shadow trigger) -- mining +
        real-fills replay via the SAME sound pattern gate_revalidation_ab.py (2026-08-08)
        established. PROPOSE-ONLY: bull-side graduation is a different, concurrent sibling
        agent's lane (backtest/tools/bull_trendline_reclaim_graduation_2026_08_09.py) --
        this cell never ships or flips anything, see the prereg's explicit_non_ownership.
CELL C: trendline-proximity admissibility -- post-hoc correlational read over CELL A's own
        trades, using the NEW backtest/lib/trendline_detector (not filters.py's trigger).
CELL D: anchor_mode wick-vs-body A/B -- SPY-point event study, explicitly a diagnostic,
        not a $ backtest (see prereg CELL_D.explicit_scope_limit).

ANALYSIS ONLY -- no params.json / filters.py / orchestrator.py file is touched by this run.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/trendline_validation_cells_2026_08_09.py
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
import time
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (str(BACKTEST), str(BACKTEST / "lib"), str(BACKTEST / "autoresearch"),
           str(BACKTEST / "tools"), str(FLEET_DIR), str(REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from recency_check import load_merged_spy_vix  # noqa: E402
from _edgehunt_vwap_continuation import _normalize_spy, _align_vix  # noqa: E402
from lib.orchestrator import run_backtest  # noqa: E402
from lib.filters import detect_trendline_reclaim_bullish  # noqa: E402  (PURE fn, read-only call)
from lib import trendline_detector as td  # noqa: E402

from gate_expiry_check import bar_idx_for_ts  # noqa: E402
from gate_revalidation_ab import (  # noqa: E402
    one_sample_p, bh_fdr, drop_top_n, cohort_metrics, is_oos_split, g_battery,
    status_tally, account_config, build_ribbon_lookup, _replay_entry,
)

PREREG = REPO / "analysis" / "recommendations" / "prereg-trendline-engine-validation-2026-08-09.json"
PREREG_ID = "TRENDLINE-ENGINE-VALIDATION-2026-08-09"
OUT = REPO / "analysis" / "recommendations" / "trendline-engine-validation-2026-08-09.json"

TUESDAY_0804 = dt.date(2026, 8, 4)
TUESDAY_0804_BASELINE_TOTAL = 3624.00  # analysis/deep-research/EOD-2026-08-06.md week table

RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)
ENTRY_WINDOW_START = dt.time(9, 35)
ENTRY_WINDOW_END = dt.time(15, 0)

BULL_MINE_LOOKBACK_BARS = 60      # matches filters.py TRENDLINE_LOOKBACK_BARS (bear side default)
BULL_MINE_MIN_SWINGS = 3          # matches filters.py TRENDLINE_MIN_SWINGS
DEDUP_WINDOW_MINUTES = 15         # a mined bull-reclaim bar within 15min of a REAL bull trade
                                   # is excluded (would double-count an entry the engine already took)
MAX_STRIKE_STEPS = 4


def log(m: str) -> None:
    print(f"[trendline-validate] {m}", flush=True)


# --------------------------------------------------------------------------- data
def load_population() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Returns (spy_raw, vix_raw, spy_norm).

    spy_raw/vix_raw: UNTOUCHED frames straight from load_merged_spy_vix() -- the shape
    run_backtest itself expects and internally re-parses (matches every existing caller of
    run_backtest in this codebase, e.g. trendline_tod_breakdown.py -- passing an already
    tz-normalized frame or a pre-aligned VIX SERIES instead of the raw VIX DataFrame is a
    real bug, found and fixed this session: run_backtest's _align_vix_to_spy reads
    vix_df['timestamp_et'] itself, which a pre-aligned Series doesn't have).

    spy_norm: RTH-filtered, tz-naive, _normalize_spy'd -- for CELLS B/C/D's OWN mining/
    detection logic, which needs positional bar-index semantics matching filters.py's
    calling convention (mirrors gate_revalidation_ab.py's own load pattern, which never
    calls run_backtest at all and only ever uses this normalized shape).
    """
    spy_raw, vix_raw = load_merged_spy_vix()
    # BUG FOUND THIS SESSION: load_merged_spy_vix()'s own docstring claims "de-duped... by
    # (timestamp) keep-last", but the implementation is a bare pd.concat with NO
    # drop_duplicates call. The master file (thru 2026-06-18) and the rolling tail file
    # (starting 2026-05-19) genuinely overlap, so spy_raw/vix_raw as returned carry real
    # duplicate-timestamp rows. Every EXISTING caller of this loader (e.g.
    # gate_revalidation_ab.py) is accidentally protected because it immediately pipes the
    # result through _normalize_spy, which DOES drop_duplicates -- but run_backtest wants
    # the raw frame directly (see load_population's own docstring) and has no such
    # protection, so passing spy_raw straight through causes vix_aligned (deduped inside
    # orchestrator._align_vix_to_spy) to end up SHORTER than spy_df -- an out-of-bounds
    # IndexError partway through the backtest walk. Deduping here (keep last, matching the
    # docstring's stated intent) fixes the root cause rather than papering over the symptom.
    # concat order is master-then-tail, NOT chronological (the tail file starts BEFORE the
    # master's own end date, so post-dedup rows are still out of order) -- sort is required,
    # not just dedup, or orchestrator's vix reindex hits "index must be monotonic" (found
    # this session). Sort by a PARSED datetime key (not the raw string column) so a
    # timezone-offset formatting quirk across files can never silently mis-order rows; the
    # original raw timestamp_et column is left untouched for run_backtest's own re-parse.
    def _dedup_sort(df: pd.DataFrame) -> pd.DataFrame:
        key = pd.to_datetime(df["timestamp_et"], utc=True)
        out = df.assign(_sort_key=key).drop_duplicates(subset="_sort_key", keep="last")
        return out.sort_values("_sort_key").drop(columns="_sort_key").reset_index(drop=True)

    spy_raw = _dedup_sort(spy_raw)
    vix_raw = _dedup_sort(vix_raw)
    spy_norm = _normalize_spy(spy_raw)
    rth = (spy_norm["t"] >= RTH_START) & (spy_norm["t"] < RTH_END)
    return spy_raw, vix_raw, spy_norm.loc[rth].reset_index(drop=True)


# =============================================================== CELL A =====================
def cell_a(spy_raw: pd.DataFrame, vix_raw: pd.DataFrame) -> tuple[dict, "object"]:
    log("=== CELL A: live trendline_rejection attribution (full population, real fills) ===")
    t0 = time.time()
    result = run_backtest(spy_raw, vix_raw, use_real_fills=True)
    trades = result.trades
    log(f"  run_backtest: {len(trades)} trades total, {round(time.time()-t0,1)}s")

    def has_tl(t) -> bool:
        return "trendline_rejection" in (getattr(t, "triggers_fired", None) or [])

    tl_sole = [t for t in trades if has_tl(t) and len(t.triggers_fired) == 1]
    tl_cofired = [t for t in trades if has_tl(t) and len(t.triggers_fired) > 1]
    non_tl = [t for t in trades if not has_tl(t)]

    def summarize(ts: list) -> dict:
        pnls = [float(t.dollar_pnl) for t in ts]
        n = len(pnls)
        if n == 0:
            return {"n": 0, "total": 0.0, "mean": None, "wr_pct": None}
        wins = sum(1 for p in pnls if p > 0)
        return {"n": n, "total": round(sum(pnls), 2), "mean": round(sum(pnls) / n, 2),
                "wr_pct": round(100 * wins / n, 1)}

    tuesday_trades = [t for t in trades if t.entry_time_et.date() == TUESDAY_0804]
    tuesday_tl = [t for t in tuesday_trades if has_tl(t)]

    out = {
        "cell_id": "CELL_A_live_bear_trigger_attribution",
        "n_trades_total": len(trades),
        "trendline_rejection_sole_trigger": summarize(tl_sole),
        "trendline_rejection_co_fired": summarize(tl_cofired),
        "non_trendline": summarize(non_tl),
        "all_trendline_combined": summarize(tl_sole + tl_cofired),
        "tuesday_2026_08_04": {
            "all_trades": summarize(tuesday_trades),
            "trendline_trades": summarize(tuesday_tl),
            "baseline_total_from_EOD_doc": TUESDAY_0804_BASELINE_TOTAL,
        },
        "elapsed_sec": round(time.time() - t0, 1),
        "note": "Nothing to ship -- trendline_rejection is already live and unconditional; this "
                "is a full-population measurement extending the single-day EOD-2026-08-06 finding.",
    }
    log(f"  trendline sole={out['trendline_rejection_sole_trigger']} "
        f"co_fired={out['trendline_rejection_co_fired']} non_tl={out['non_trendline']}")
    return out, result


# =============================================================== CELL B =====================
def _mine_bull_reclaim_bars(spy: pd.DataFrame) -> list[dict]:
    """Pure, read-only scan calling detect_trendline_reclaim_bullish (UNMODIFIED production
    function) bar-by-bar over the full population, exactly matching orchestrator.py's own
    calling convention (prior_bars=full spy_df, bar_idx=global position -- see
    orchestrator.py:986-990)."""
    hits: list[dict] = []
    n = len(spy)
    for idx in range(BULL_MINE_LOOKBACK_BARS + 2, n):
        bar = spy.iloc[idx]
        level = detect_trendline_reclaim_bullish(
            bar, spy, idx, lookback_bars=BULL_MINE_LOOKBACK_BARS, min_swings=BULL_MINE_MIN_SWINGS,
        )
        if level is not None:
            hits.append({"bar_idx": idx, "ts_et": bar["timestamp_et"], "level": float(level)})
    return hits


def _dedupe_against_real_bull_trades(hits: list[dict], real_bull_entries: list[dt.datetime]) -> list[dict]:
    if not real_bull_entries:
        return hits
    real_sorted = sorted(real_bull_entries)
    window = dt.timedelta(minutes=DEDUP_WINDOW_MINUTES)
    out = []
    for h in hits:
        ts = h["ts_et"]
        near_real = any(abs((ts - r).total_seconds()) <= window.total_seconds() for r in real_sorted)
        if not near_real:
            out.append(h)
    return out


def cell_b(spy: pd.DataFrame, cell_a_result) -> dict:
    log("=== CELL B: bull trendline-reclaim counterfactual (mining + real-fills replay) ===")
    t0 = time.time()
    hits = _mine_bull_reclaim_bars(spy)
    log(f"  mined {len(hits)} raw bull-reclaim fires")

    real_bull_entries = [t.entry_time_et for t in cell_a_result.trades if t.side == "C"]
    cohort_bars = _dedupe_against_real_bull_trades(hits, real_bull_entries)
    log(f"  {len(cohort_bars)} remain after excluding bars within {DEDUP_WINDOW_MINUTES}min of "
        f"a REAL bull entry ({len(hits) - len(cohort_bars)} deduped)")

    # entry-window gate (matches v15.1 09:35-15:00 ET convention used elsewhere in this codebase)
    cohort_bars = [h for h in cohort_bars
                   if ENTRY_WINDOW_START <= h["ts_et"].time() <= ENTRY_WINDOW_END]
    log(f"  {len(cohort_bars)} remain after the 09:35-15:00 ET entry-window gate")

    cfg = account_config()["safe"]
    ribbon_lookup = build_ribbon_lookup(spy)
    spy_by_date = {d: sub.reset_index(drop=True) for d, sub in spy.groupby("date")}

    replays = []
    for h in cohort_bars:
        level_row = {"bull_reclaim_level_raw": h["level"]}
        out = _replay_entry(h["bar_idx"], "C", level_row, spy=spy, spy_by_date=spy_by_date,
                             ribbon_lookup=ribbon_lookup, cfg=cfg)
        out["ts_et"] = h["ts_et"].isoformat()
        replays.append(out)

    ok = [r for r in replays if r["status"] == "ok"]
    log(f"  replayed n_ok={len(ok)}/{len(replays)} status={status_tally(replays)}")

    cohort = cohort_metrics(ok)
    is_half, oos_half = is_oos_split(ok)
    is_m, oos_m = cohort_metrics(is_half), cohort_metrics(oos_half)
    pval = one_sample_p([r["pnl"] for r in ok])

    tuesday_ok = [r for r in ok if r["date"] == str(TUESDAY_0804)]
    tuesday_total = round(sum(r["pnl"] for r in tuesday_ok), 2) if tuesday_ok else 0.0

    out = {
        "cell_id": "CELL_B_bull_trendline_reclaim_counterfactual",
        "n_raw_fires": len(hits), "n_after_dedup_and_window": len(cohort_bars),
        "status_counts": status_tally(replays),
        "cohort": cohort, "is_half": is_m, "oos_half": oos_m, "one_sample_p": round(pval, 4),
        "tuesday_2026_08_04": {
            "n_counterfactual_bull_reclaim_entries": len(tuesday_ok),
            "counterfactual_total": tuesday_total,
            "would_ADD_to_baseline": "yes -- these are NEW hypothetical entries, not a change to "
                                      "any existing 08-04 trade" if tuesday_ok else "n/a -- none mined that day",
        },
        "trades_sample": ok[:10],
        "elapsed_sec": round(time.time() - t0, 1),
        "ownership_note": "PROPOSE-ONLY per prereg explicit_non_ownership -- bull-side LIVE "
                           "graduation belongs to a different, concurrently-active sibling agent "
                           "(backtest/tools/bull_trendline_reclaim_graduation_2026_08_09.py). "
                           "This agent does not flip or ship anything from this cell regardless "
                           "of the g_battery verdict below.",
    }
    return out


def _naive_et(ts: dt.datetime) -> dt.datetime:
    """run_backtest's TradeFill.entry_time_et is tz-AWARE (built from the raw, un-normalized
    spy_raw CELL A intentionally feeds it -- see load_population's docstring); `spy` (used by
    CELLS C/D) is tz-NAIVE wall-clock ET via _normalize_spy. Bridge the two the same way
    _normalize_spy itself does: convert to America/New_York, then drop tzinfo -- never a bare
    .replace(tzinfo=None), which would be silently wrong if entry_time_et's tz offset isn't
    already ET."""
    if ts.tzinfo is None:
        return ts
    return pd.Timestamp(ts).tz_convert("America/New_York").tz_localize(None).to_pydatetime()


# =============================================================== CELL C =====================
def cell_c(spy: pd.DataFrame, cell_a_result) -> dict:
    log("=== CELL C: trendline-proximity admissibility (post-hoc, new detector) ===")
    t0 = time.time()
    spy_ts = spy["timestamp_et"]
    lookback_bars = 3 * 78  # ~3 trading days at 5m, matches the timeframe-matrix study's convention

    rows = []
    for t in cell_a_result.trades:
        idx, stale = bar_idx_for_ts(spy_ts, _naive_et(t.entry_time_et))
        if idx is None or stale:
            continue
        window_start = max(0, idx - lookback_bars)
        bars = td.bars_from_dataframe(spy.iloc[window_start: idx + 1])
        lines = td.detect_trendlines(bars, anchor_mode="wick", min_touches=3,
                                      min_bars_between_touches=6, min_span_bars=6,
                                      symbol="SPY", timeframe="5m")
        state = td.trendline_state_for_decision_row(lines)
        nearest_pct = state.get("nearest_distance_pct")
        rows.append({
            "entry_time_et": t.entry_time_et.isoformat(), "pnl": float(t.dollar_pnl),
            "side": t.side, "nearest_distance_pct": nearest_pct,
        })

    with_line = [r for r in rows if r["nearest_distance_pct"] is not None]
    log(f"  {len(with_line)}/{len(rows)} trades had >=1 detectable line within lookback")
    if len(with_line) < 6:
        return {"cell_id": "CELL_C_trendline_proximity_admissibility", "n_trades_with_line": len(with_line),
                "verdict": "INCONCLUSIVE -- too few trades with a detectable line to bucket",
                "elapsed_sec": round(time.time() - t0, 1)}

    ranked = sorted(with_line, key=lambda r: abs(r["nearest_distance_pct"]))
    n = len(ranked)
    thirds = [ranked[: n // 3], ranked[n // 3: 2 * n // 3], ranked[2 * n // 3:]]
    labels = ["near", "mid", "far"]
    buckets = {}
    for label, group in zip(labels, thirds):
        pnls = [r["pnl"] for r in group]
        n_g = len(pnls)
        wins = sum(1 for p in pnls if p > 0)
        buckets[label] = {
            "n": n_g, "total": round(sum(pnls), 2),
            "mean": round(sum(pnls) / n_g, 2) if n_g else None,
            "wr_pct": round(100 * wins / n_g, 1) if n_g else None,
        }

    # Spearman(bucket-rank, pnl) + shuffle-null, reusing trend-alignment-correlation.md's method.
    import random
    rank_map = {"near": 0, "mid": 1, "far": 2}
    xs = []
    ys = []
    for label, group in zip(labels, thirds):
        for r in group:
            xs.append(rank_map[label])
            ys.append(r["pnl"])
    rho = _spearman(xs, ys)
    rng = random.Random(20260809)
    null_rhos = []
    ys_shuffled = list(ys)
    for _ in range(1000):
        rng.shuffle(ys_shuffled)
        null_rhos.append(_spearman(xs, ys_shuffled))
    null_rhos.sort()
    lo = null_rhos[int(0.05 * len(null_rhos))]
    hi = null_rhos[int(0.95 * len(null_rhos)) - 1]
    beats_null = not (lo <= rho <= hi)

    # monotonic-ish (near -> mid -> far means, <=1 adjacent inversion)
    means = [buckets[l]["mean"] for l in labels if buckets[l]["mean"] is not None]
    inversions = sum(1 for i in range(len(means) - 1) if means[i + 1] < means[i]) if len(means) >= 2 else 0

    verdict_supported = beats_null and inversions <= 1
    out = {
        "cell_id": "CELL_C_trendline_proximity_admissibility",
        "n_trades_with_line": len(with_line), "n_trades_total": len(rows),
        "buckets": buckets, "spearman_rho": round(rho, 4),
        "shuffle_null_90pct_interval": [round(lo, 4), round(hi, 4)],
        "beats_null": beats_null, "monotonic_inversions": inversions,
        "verdict": "SUPPORTED (informational -- would only qualify a Phase-2 wiring proposal, "
                    "not a live change from this cell)" if verdict_supported else "KILL",
        "elapsed_sec": round(time.time() - t0, 1),
    }
    log(f"  buckets={buckets} rho={rho:.4f} beats_null={beats_null} verdict={out['verdict']}")
    return out


def _spearman(xs: list[float], ys: list[float]) -> float:
    n = len(xs)
    if n < 2:
        return 0.0

    def _ranks(vals: list[float]) -> list[float]:
        order = sorted(range(len(vals)), key=lambda i: vals[i])
        ranks = [0.0] * len(vals)
        i = 0
        while i < len(order):
            j = i
            while j + 1 < len(order) and vals[order[j + 1]] == vals[order[i]]:
                j += 1
            avg_rank = (i + j) / 2.0 + 1.0
            for k in range(i, j + 1):
                ranks[order[k]] = avg_rank
            i = j + 1
        return ranks

    rx, ry = _ranks(xs), _ranks(ys)
    mean_rx, mean_ry = sum(rx) / n, sum(ry) / n
    num = sum((a - mean_rx) * (b - mean_ry) for a, b in zip(rx, ry))
    den = (sum((a - mean_rx) ** 2 for a in rx) * sum((b - mean_ry) ** 2 for b in ry)) ** 0.5
    return num / den if den else 0.0


# =============================================================== CELL D =====================
def cell_d(spy: pd.DataFrame) -> dict:
    log("=== CELL D: anchor_mode wick-vs-body A/B (SPY-point event study, 5m) ===")
    t0 = time.time()
    bars = td.bars_from_dataframe(spy)
    n = len(bars)
    lookback_bars = 3 * 78
    forward_bars = 12  # ~60 minutes at 5m
    warmup = lookback_bars + 2

    def run_mode(mode: str) -> dict:
        touches = []
        idx = warmup
        while idx < n - forward_bars:
            window = bars[max(0, idx - lookback_bars): idx + 1]
            lines = td.detect_trendlines(window, anchor_mode=mode, min_touches=3,
                                          min_bars_between_touches=6, min_span_bars=6,
                                          symbol="SPY", timeframe="5m")
            for ln in lines:
                if ln.status != "testing":
                    continue
                fwd_idx = idx + forward_bars
                if fwd_idx >= n:
                    continue
                touch_close, fwd_close = bars[idx].close, bars[fwd_idx].close
                favorable = (fwd_close - touch_close) if ln.kind == "support" else (touch_close - fwd_close)
                touches.append(favorable)
            idx += 3  # ~15-minute cadence, matches the timeframe-matrix study
        n_t = len(touches)
        n_resp = sum(1 for f in touches if f > 0)
        return {
            "n_touches": n_t,
            "touch_respect_rate": round(n_resp / n_t, 4) if n_t else None,
            "mean_forward_return_favorable": round(sum(touches) / n_t, 4) if n_t else None,
            "_raw_favorable": touches,
        }

    wick = run_mode("wick")
    body = run_mode("body")

    p_two_sample = _two_sample_p(wick["_raw_favorable"], body["_raw_favorable"])
    wick.pop("_raw_favorable")
    body.pop("_raw_favorable")

    worth_followup = (
        body["n_touches"] >= 15
        and body["touch_respect_rate"] is not None
        and wick["touch_respect_rate"] is not None
        and abs(body["touch_respect_rate"] - wick["touch_respect_rate"]) <= 0.10
        and (body["mean_forward_return_favorable"] or 0) > 0
    )
    out = {
        "cell_id": "CELL_D_anchor_mode_wick_vs_body_ab",
        "wick": wick, "body": body, "two_sample_p": round(p_two_sample, 4),
        "verdict": "WORTH A FOLLOW-UP PREREG" if worth_followup else "NOT WORTH PURSUING THIS PASS",
        "elapsed_sec": round(time.time() - t0, 1),
        "scope_note": "SPY-point diagnostic only, not a $ backtest -- see prereg CELL_D.explicit_scope_limit",
    }
    log(f"  wick={wick} body={body} p={p_two_sample:.4f} verdict={out['verdict']}")
    return out


def _two_sample_p(a: list[float], b: list[float]) -> float:
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return 1.0
    mean_a, mean_b = sum(a) / na, sum(b) / nb
    var_a = sum((x - mean_a) ** 2 for x in a) / (na - 1)
    var_b = sum((x - mean_b) ** 2 for x in b) / (nb - 1)
    se = (var_a / na + var_b / nb) ** 0.5
    if se == 0:
        return 1.0
    tstat = (mean_a - mean_b) / se
    return max(0.0, min(1.0, 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(tstat) / (2 ** 0.5))))))


# =============================================================== main =======================
def main() -> int:
    t_start = time.time()
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    assert prereg["prereg_id"] == PREREG_ID, "prereg id mismatch -- refusing to run against a different prereg"
    log(f"loaded frozen prereg {PREREG.name} (frozen_at_et={prereg['frozen_at_et']})")

    spy_raw, vix_raw, spy = load_population()
    log(f"population: {len(spy)} RTH rows (normalized), {spy['date'].nunique()} trading days, "
        f"{spy['date'].min()}..{spy['date'].max()}")

    a_out, a_result = cell_a(spy_raw, vix_raw)
    b_out = cell_b(spy, a_result)
    c_out = cell_c(spy, a_result)
    d_out = cell_d(spy)

    # BH-FDR across the 3 statistically-tested cells (B, C, D) -- cell A is measurement/
    # attribution only and is excluded from the family, per the prereg's stats_frozen.
    pvals = [
        b_out.get("one_sample_p", 1.0),
        1.0 if c_out.get("verdict") == "INCONCLUSIVE" else (1 - abs(c_out.get("spearman_rho", 0))),
        d_out.get("two_sample_p", 1.0),
    ]
    bh_sig = bh_fdr(pvals, q=0.10)

    b_battery = g_battery(b_out["cohort"], b_out["oos_half"], b_out["one_sample_p"], bh_sig[0])

    hard_gate = {
        "id": "G_TUESDAY_NO_REGRESSION",
        "applies_to": "CELL_B only (per prereg)",
        "cell_b_tuesday_counterfactual": b_out["tuesday_2026_08_04"],
        "verdict": "N/A -- CELL_B is PROPOSE-ONLY (see ownership_note); nothing ships from this "
                    "study so nothing can regress Tuesday 2026-08-04's live +$3,624.",
    }

    out = {
        "prereg_id": PREREG_ID, "prereg_file": str(PREREG.relative_to(REPO)).replace("\\", "/"),
        "generated_at": dt.datetime.now().isoformat(),
        "population": {"n_trading_days": int(spy["date"].nunique()),
                        "window": f"{spy['date'].min()}..{spy['date'].max()}"},
        "cell_a": a_out,
        "cell_b": {**b_out, "g_battery": b_battery},
        "cell_c": c_out,
        "cell_d": d_out,
        "bh_fdr_family": {"pvals": [round(p, 4) for p in pvals], "significant": bh_sig,
                           "cells": ["B", "C", "D"]},
        "hard_gate": hard_gate,
        "ship_rule_applied": "Per the frozen prereg's ship_rule: this is a MEASUREMENT program. "
                              "CELL_A has nothing to ship (already live). CELL_B is capped at "
                              "propose-only (different sibling's lane, in flight). CELL_C/D even "
                              "if supportive only qualify a FUTURE Phase-2 proposal. NOTHING in "
                              "this run touches params.json, filters.py, or orchestrator.py.",
        "total_elapsed_sec": round(time.time() - t_start, 1),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    log(f"wrote {OUT}")
    log(f"TOTAL elapsed: {round(time.time() - t_start, 1)}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())

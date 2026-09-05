"""MULTI-DAY (weekly) vs 0DTE clean comparison — isolates the DTE variable.

CONTEXT (chef 2026-07-07 offline R&D). THESIS: J's directional edge is real but
dies in every 0DTE options BUY on the C3 theta/premium nail. FIX (verified on
today's tape, 745P anchor): buy the NEXT-FRIDAY weekly (1-4 DTE) and hold, so the
move has DAYS to pay at a fraction of the daily theta.

This harness holds EVERYTHING constant except DTE:
  * SAME signals (one honest directional trigger: vwap_continuation, the live
    watcher port — reused byte-for-byte from _dte_expansion_sim.FAMILIES).
  * SAME strike offset (ITM-2, production tier at $2-10k) + SAME exit logic
    (TP1 +30% premium fallback, chart-stop, premium-stop -8%) across all buckets.
  * The ONLY variable: DTE = 0 (same-day) vs 1 vs 2 (weekly-ish).

Fills are REAL OPRA (day-T bars from data/options_{0,1,2}dte/), honest overnight
gap + expiry-intrinsic settlement — all reused verbatim from _dte_expansion_sim
(simulate_dte_trade / run_cell). We ADD the discipline columns the task asks for
that the parent sim summarizes differently: WR, drop-top3 per-trade, and a
RANDOM-ENTRY NULL (same strike+exit, entry bar shuffled to a random RTH bar on a
random trading day) to prove the SIGNAL — not just "long a rising tape" — carries
the edge (L172).

DATA REALITY (verified this run): the per-DTE cache stores only day-T bars; there
is NO continuous multi-day hold history for an arbitrary weekly. So DTE=2 is the
longest honest bucket available WITHOUT a new multi-week OPRA fetch. This answers
"does a longer hold help on the SAME signal" — the C3-artifact question — but a
true 4-DTE weekly needs the fetch (estimated at the end).

Pure Python, $0, no orders. Read-only market data.
  backtest/.venv/Scripts/python.exe backtest/autoresearch/multiday_dte_compare.py
"""

from __future__ import annotations

import json
import random
import statistics as stats
import sys
from pathlib import Path

import numpy as np

_HERE = Path(__file__).resolve()
_BT = _HERE.parents[1]          # backtest/
_REPO = _BT.parent
for p in (str(_BT), str(_REPO)):
    if p not in sys.path:
        sys.path.insert(0, p)

from autoresearch import _dte_expansion_sim as X  # noqa: E402

# Fixed comparison config — production tier, held constant across DTE buckets.
STRIKE_OFFSET = -2        # ITM-2 (the $2-10k production strike tier; neg = ITM)
PREMIUM_STOP = -0.08      # production -8% premium cap
TP1_PCT = 0.30            # production +30% TP1 fallback
FAMILY = "vwap_continuation"
# Extended 2026-09-05: 3/4-DTE cache backfilled 2026-07-07 (options_3dte_4dte_backfill_
# manifest.json, ok=2958/2961) and wired into _dte_expansion_sim.DTE_DIRS same-day. Per
# candidate adjudication (strategy/candidates/2026-07-07-193737-weekly-dte-not-0dte.md
# ## ADJUDICATION 2026-09-05): this was the only thing blocking the OP-16 re-score.
DTE_BUCKETS = [0, 1, 2, 3, 4]
OOS_YEAR = X.OOS_YEAR
N_NULL_ITERS = 200
RNG_SEED = 20260707

# Fail-loud coverage guard (per this task): a bucket must not silently report a result
# built on a cache that was actually missing. "Missing cache" = the entry date had no
# listed expiry mapped in that DTE's cache dir at all (X._expiry_for_entry -> None,
# counted as run_cell's cov['no_expiry_listed']) OR every signal in the bucket failed to
# fill. A few no_expiry_listed (unlisted expiries, e.g. holiday-shifted Fridays) are
# expected and reported, not fatal; total coverage collapse is fatal.
MIN_FILL_RATE_FOR_NONTRIVIAL_BUCKET = 0.0  # any successful fill is required, see raise below


class BucketCacheMissingError(RuntimeError):
    """Raised when a DTE bucket's option cache cannot back any trade (fail loudly, L07 C7)."""


def check_bucket_coverage(dte: int, cov: dict) -> None:
    """Report per-bucket coverage; raise if the cache for this bucket is effectively
    absent rather than silently producing a 0-trade or near-empty 'result'."""
    n_total = cov.get("signals", 0)
    n_filled = cov.get("filled", 0)
    n_no_expiry = cov.get("no_expiry_listed", 0)
    n_cache_miss = cov.get("cache_miss", 0)
    print(f"    [coverage] DTE={dte}: signals={n_total} filled={n_filled} "
          f"no_expiry_listed={n_no_expiry} cache_miss={n_cache_miss} "
          f"fill_rate={cov.get('fill_rate', 0.0)}")
    if n_total == 0:
        return  # no signals at all is a signal-generation fact, not a cache fact
    if n_filled == 0:
        raise BucketCacheMissingError(
            f"DTE={dte}: 0/{n_total} signals filled (no_expiry_listed={n_no_expiry}, "
            f"cache_miss={n_cache_miss}) — the option cache for this bucket is missing "
            f"or unreadable; refusing to report a fabricated/empty result for this bucket."
        )
    if n_no_expiry == n_total:
        raise BucketCacheMissingError(
            f"DTE={dte}: every one of {n_total} signal dates has no listed expiry in "
            f"this DTE's cache — the cache dir is present but empty/unindexed for this "
            f"window; refusing to report."
        )


def wr(rows) -> float:
    if not rows:
        return 0.0
    wins = sum(1 for r in rows if r.dollar_pnl > 0)
    return round(100.0 * wins / len(rows), 1)


def exp_per_trade(rows) -> float:
    return round(stats.mean(r.dollar_pnl for r in rows), 2) if rows else 0.0


def oos_rows(rows):
    return [r for r in rows if r.date[:4] == str(OOS_YEAR)]


def drop_topN_per_trade(rows, n=3) -> float | None:
    """Drop the n best DAYS (by total day pnl), then per-trade expectancy of the rest.
    Mirrors the parent sim's de-concentration (drops best DAYS, not trades)."""
    if len(rows) <= n:
        return None
    by_day: dict[str, float] = {}
    for r in rows:
        by_day[r.date] = by_day.get(r.date, 0.0) + r.dollar_pnl
    worst_days = set(sorted(by_day, key=lambda d: by_day[d], reverse=True)[:n])
    keep = [r for r in rows if r.date not in worst_days]
    return round(stats.mean(r.dollar_pnl for r in keep), 2) if keep else None


def random_entry_null(signals, spy, day_open_close, dte, *, n_iters, rng):
    """Same strike/exit machinery, but each signal's ENTRY BAR is replaced by a
    random RTH bar on a random trading day (side preserved). Re-run n_iters times;
    return (mean_null_exp, p_value) where p = P(null_exp >= real_exp).

    This isolates the SIGNAL: if a random entry into the same tape earns the same,
    the 'edge' is just being-long-a-rising-market, not the trigger (L172)."""
    # Precompute RTH bar indices per trading day for the shuffle pool.
    ts = spy["timestamp_et"]
    days = ts.dt.date.values
    times = ts.dt.time.values
    rth_mask = np.array([X.dt.time(9, 40) <= t <= X.dt.time(15, 45) for t in times])
    rth_idx = np.where(rth_mask)[0]
    if len(rth_idx) == 0:
        return None, None

    # Real expectancy (this cell) for the p-value reference.
    real_rows, _ = X.run_cell(signals, spy, day_open_close, dte,
                              strike_offset=STRIKE_OFFSET,
                              premium_stop_pct=PREMIUM_STOP, tp1_premium_pct=TP1_PCT)
    if not real_rows:
        return None, None
    real_exp = stats.mean(r.dollar_pnl for r in real_rows)

    null_means = []
    ge = 0
    from autoresearch._dte_expansion_sim import Signal  # same contract
    for _ in range(n_iters):
        shuffled = []
        for sg in signals:
            rand_bar = int(rng.choice(rth_idx))
            shuffled.append(Signal(bar_idx=rand_bar, side=sg.side,
                                   stop_level=sg.stop_level, note="null"))
        nrows, _ = X.run_cell(shuffled, spy, day_open_close, dte,
                              strike_offset=STRIKE_OFFSET,
                              premium_stop_pct=PREMIUM_STOP, tp1_premium_pct=TP1_PCT)
        if not nrows:
            continue
        nexp = stats.mean(r.dollar_pnl for r in nrows)
        null_means.append(nexp)
        if nexp >= real_exp:
            ge += 1
    if not null_means:
        return None, None
    p = round((ge + 1) / (len(null_means) + 1), 4)  # add-one smoothing
    return round(float(np.mean(null_means)), 2), p


def main() -> int:
    rng = np.random.default_rng(RNG_SEED)
    random.seed(RNG_SEED)

    print("[compare] loading SPY+VIX ...")
    spy, vix = X._load_spy_vix()
    day_open_close = X._spy_day_open_close(spy)
    # Build signals via the EXACT path used inside _dte_expansion_sim.main():
    #   days = build_day_contexts(spy); ribbon = compute_ribbon(...); detect(days,vix,spy,ribbon)
    days = X.build_day_contexts(spy)
    ribbon = X.compute_ribbon(X.pd.Series(spy["close"].values))
    detector = X.FAMILIES[FAMILY]
    signals = detector(days, vix, spy, ribbon)
    print(f"[compare] family={FAMILY} signals={len(signals)} "
          f"side={{'C':{sum(1 for s in signals if s.side=='C')},"
          f"'P':{sum(1 for s in signals if s.side=='P')}}}")
    print(f"[compare] FIXED config: ITM-2 (off={STRIKE_OFFSET}), premium_stop={PREMIUM_STOP}, "
          f"tp1={TP1_PCT}  | only DTE varies\n")

    table = []
    for dte in DTE_BUCKETS:
        rows, cov = X.run_cell(signals, spy, day_open_close, dte,
                               strike_offset=STRIKE_OFFSET,
                               premium_stop_pct=PREMIUM_STOP, tp1_premium_pct=TP1_PCT)
        check_bucket_coverage(dte, cov)
        o = oos_rows(rows)
        rec = {
            "dte": dte,
            "n": len(rows),
            "fill_rate": cov["fill_rate"],
            "wr": wr(rows),
            "exp": exp_per_trade(rows),
            "oos_n": len(o),
            "oos_exp": exp_per_trade(o),
            "oos_wr": wr(o),
            "drop3_exp": drop_topN_per_trade(rows, 3),
            "held_overnight_pct": round(100.0 * sum(1 for r in rows if r.held_overnight) / len(rows), 1) if rows else 0.0,
            "total_pnl": round(sum(r.dollar_pnl for r in rows), 0),
            "coverage": cov,
        }
        null_exp, p_null = random_entry_null(signals, spy, day_open_close, dte,
                                             n_iters=N_NULL_ITERS, rng=rng)
        rec["null_exp"] = null_exp
        rec["p_null"] = p_null
        table.append(rec)
        print(f"  DTE={dte}: n={rec['n']:3d} WR={rec['wr']:5.1f}%  exp=${rec['exp']:7.2f}  "
              f"| OOS n={rec['oos_n']:3d} exp=${rec['oos_exp']:7.2f} WR={rec['oos_wr']:5.1f}%  "
              f"| drop3=${rec['drop3_exp']}  null=${rec['null_exp']} p={rec['p_null']}  "
              f"held%={rec['held_overnight_pct']}")

    out = {
        "generated": "chef 2026-07-07 offline",
        "family": FAMILY,
        "fixed_config": {"strike_offset": STRIKE_OFFSET, "premium_stop": PREMIUM_STOP,
                         "tp1_pct": TP1_PCT},
        "window": "2025-01-02..2026-06-16",
        "oos_year": OOS_YEAR,
        "n_null_iters": N_NULL_ITERS,
        "buckets": table,
    }
    outpath = _REPO / "analysis" / "recommendations" / "multiday-dte-compare.json"
    outpath.write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\n[compare] wrote {outpath}")

    # ---- one-line read ----
    b0 = next(b for b in table if b["dte"] == 0)
    bmax = max(table, key=lambda b: (b["oos_exp"] or -1e9))
    print("\n=== READ ===")
    print(f"  0DTE OOS exp=${b0['oos_exp']}/tr (WR {b0['oos_wr']}%)  vs  "
          f"best DTE={bmax['dte']} OOS exp=${bmax['oos_exp']}/tr (WR {bmax['oos_wr']}%)")
    lift = (bmax["oos_exp"] or 0) - (b0["oos_exp"] or 0)
    print(f"  longer-DTE OOS lift on the SAME signal: ${lift:+.2f}/tr")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

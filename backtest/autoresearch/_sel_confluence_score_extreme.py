"""SELECTION test: confluence_score_extreme -- EXTREME SELECTIVITY on real 0DTE fills.

HYPOTHESIS (from J): the earlier confluence real-fills test took ALL directional reads at
conviction>=50 and was a coin-flip theta trap (-$23k/16mo, 0/6 quarters -- see the
CALIBRATION_TAG in crypto/lib/confluence.py). THIS test asks the opposite question:

    Does RUTHLESS selectivity finally clear? Enter ONLY where BOTH:
      (1) conviction is in the TOP DECILE of all directional reads (data-driven threshold,
          computed from the realized conviction distribution -- not a folklore number), AND
      (2) >= 4 confluence FACTORS agree with the bias (multiple independent confirmations).

Few, very-high-agreement entries. survivor structure (ITM-2, -8% premium stop, v15 exits).
N WILL be small -- report it honestly. It may also fail (selectivity != edge is a real
possible outcome; the confluence engine is already on record as a losing trigger).

REAL-FILLS AUTHORITY (C1): lib.simulator_real.simulate_trade_real is the only WR/P&L
authority. SPY-direction confluence != option edge (C3/L58) -- this is the OPTION-edge test.

ALL GATES MANDATORY (deterministic, no cherry-picking -- anti-pattern 2.10):
  G1 OOS(2026) per-trade expectancy > 0
  G2 positive_quarters >= 4/6
  G3 top5-day concentration < 200%
  G4 n >= 20
  G5 drop-top-5-days total P&L still > 0
  G6 beats a RANDOM-entry null (same exit/count/side mix, ~20 seeds): mean-of-nulls < strat
  G7 sign does NOT invert at chart-stop-only (premium_stop=-0.99) -- no-truncation check
  G8 IN-SAMPLE (2025) half is ALSO positive (reject the IS-neg/OOS-pos single-regime artifact)

Pure Python, $0 in the sim loop. No live orders. Markets closed.
Writes analysis/recommendations/sel-confluence_score_extreme.json.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sel_confluence_score_extreme.py
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.confluence import compute_confluence  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

OUT = ROOT / "analysis" / "recommendations" / "sel-confluence_score_extreme.json"

# ── Survivor structure (primary, per task) ──────────────────────────────────────
QTY = 3
STRIKE_OFFSET = -2          # ITM-2 (survivor)
PREMIUM_STOP_PCT = -0.08    # v15 asymmetric base; -0.99 used only for G7 no-truncation check
# v15 default exits otherwise (use_tiered_exits=True default in simulator_real).

# ── Selection params (the WHOLE point: extreme selectivity) ─────────────────────
TOP_DECILE = 0.90           # conviction threshold = 90th percentile of directional reads
MIN_FACTORS_AGREE = 4       # >= 4 confluence factors must agree with the bias
TRAIL = 60                  # trailing bars handed to confluence (matches confluence validate)
WARMUP = 12                 # bars into the day before evaluating (matches confluence validate)
COOLDOWN_MIN = 45           # anti-pattern 2.7 (no back-to-back same-setup churn)

START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)
OOS_YEAR = 2026
N_NULL_SEEDS = 20

# ── Gates ───────────────────────────────────────────────────────────────────────
BAR_N = 20
BAR_POS_Q = 4
BAR_TOP5 = 200.0


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _count_factors_agree(read) -> int:
    """How many confluence factors voted the same direction as the resolved bias."""
    if read.bias == "neutral":
        return 0
    return sum(1 for f in read.factors if f.direction == read.bias)


def _load_rth():
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
                   & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    rth["date"] = rth["timestamp_et"].dt.date
    log.info("RTH bars: %d", len(rth))

    # VIX aligned (ffill) -- for disclosure only
    vix_full["timestamp_et"] = pd.to_datetime(
        vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index)
    vix_ser = vix_full.set_index("timestamp_et")["close"] if "close" in vix_full.columns else vix_full.iloc[:, 0]
    rth_naive = rth["timestamp_et"].dt.tz_localize(None) if rth["timestamp_et"].dt.tz is not None else rth["timestamp_et"]
    vix_arr = []
    for ts in rth_naive:
        try:
            j = vix_ser.index.get_indexer([ts], method="ffill")[0]
            vix_arr.append(float(vix_ser.iloc[j]) if j >= 0 else 17.0)
        except Exception:
            vix_arr.append(17.0)
    return rth, vix_arr


def _build_bars(rth):
    bars: list[Bar] = []
    for _, r in rth.iterrows():
        ts = pd.Timestamp(r["timestamp_et"])
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        bars.append(Bar(open_time=ts.to_pydatetime().replace(tzinfo=dt.timezone.utc),
                        open=float(r["open"]), high=float(r["high"]), low=float(r["low"]),
                        close=float(r["close"]), volume=int(r.get("volume", 50000) or 50000),
                        granularity_seconds=300, source="spy"))
    return bars


def _scan_reads(rth, all_bars, vix_arr):
    """Compute a confluence read at every eligible bar; record bias/conviction/factors."""
    day_start: dict[dt.date, int] = {}
    for i, d in enumerate(rth["date"]):
        if d not in day_start:
            day_start[d] = i

    reads: list[dict] = []
    for idx in range(len(rth)):
        d = rth["date"].iloc[idx]
        i0 = day_start[d]
        if idx - i0 < WARMUP:
            continue
        trailing = all_bars[max(i0, idx - TRAIL + 1): idx + 1]
        if len(trailing) < 10:
            continue
        read = compute_confluence(trailing)
        if read.bias == "neutral":
            continue
        if read.invalidation is None:
            continue
        bar_time = all_bars[idx].open_time.replace(tzinfo=None)
        reads.append({
            "idx": idx, "date": d, "bias": read.bias, "conviction": read.conviction,
            "factors_agree": _count_factors_agree(read),
            "rejection_level": float(read.invalidation),
            "vix": round(vix_arr[idx], 1),
            "time": bar_time.strftime("%H:%M"), "bar_time": bar_time,
            "side": "C" if read.bias == "bullish" else "P",
        })
    return reads


def _select_extreme(reads):
    """Top-decile conviction (data-driven) AND >= MIN_FACTORS_AGREE factors, + cooldown."""
    convs = np.array([r["conviction"] for r in reads], float)
    thresh = float(np.quantile(convs, TOP_DECILE)) if len(convs) else 100.0
    candidates = [r for r in reads
                  if r["conviction"] >= thresh and r["factors_agree"] >= MIN_FACTORS_AGREE]
    candidates.sort(key=lambda r: r["idx"])
    selected: list[dict] = []
    last_t: dt.datetime | None = None
    for r in candidates:
        if last_t is not None and (r["bar_time"] - last_t).total_seconds() / 60.0 < COOLDOWN_MIN:
            continue
        last_t = r["bar_time"]
        selected.append(r)
    return selected, thresh


def _simulate(reads, rth, *, premium_stop):
    """Run simulate_trade_real on each selected read at survivor structure."""
    rows: list[dict] = []
    no_data = 0
    for s in reads:
        fill = simulate_trade_real(
            entry_bar_idx=s["idx"], entry_bar=rth.iloc[s["idx"]], spy_df=rth, ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["confluence_extreme", s["bias"], f"factors{s['factors_agree']}"],
            side=s["side"], qty=QTY, setup="CONFLUENCE_SCORE_EXTREME",
            premium_stop_pct=premium_stop, strike_offset=STRIKE_OFFSET)
        if fill is None or fill.dollar_pnl is None:
            no_data += 1
            continue
        rows.append({
            "date": s["date"].isoformat(), "time": s["time"], "bias": s["bias"],
            "side": s["side"], "conviction": s["conviction"], "factors_agree": s["factors_agree"],
            "vix": s["vix"], "strike": fill.strike,
            "entry_premium": round(float(fill.entry_premium), 3),
            "pnl": round(float(fill.dollar_pnl), 2),
            "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason),
        })
    return rows, no_data


def _by_day(rows):
    bd: dict[str, float] = defaultdict(float)
    for r in rows:
        bd[r["date"]] += r["pnl"]
    return bd


def _metrics(rows):
    if not rows:
        return {"n": 0}
    pnl = np.array([r["pnl"] for r in rows], float)
    n = len(rows)
    wins = int((pnl > 0).sum())
    is_rows = [r for r in rows if int(r["date"][:4]) != OOS_YEAR]
    oos_rows = [r for r in rows if int(r["date"][:4]) == OOS_YEAR]

    def _exp(rs):
        return round(float(np.mean([r["pnl"] for r in rs])), 2) if rs else None

    def _tot(rs):
        return round(float(np.sum([r["pnl"] for r in rs])), 2) if rs else 0.0

    by_q: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        by_q[_quarter(dt.date.fromisoformat(r["date"]))].append(r["pnl"])
    quarters = {q: {"n": len(v), "exp": round(sum(v) / len(v), 2), "total": round(sum(v), 2)}
                for q, v in sorted(by_q.items())}
    q_pos = sum(1 for v in quarters.values() if v["total"] > 0)

    bd = _by_day(rows)
    total = sum(bd.values())
    days_sorted = sorted(bd.values(), reverse=True)
    top5 = sum(days_sorted[:5])
    top5_pct = round(100 * top5 / total, 1) if total > 0 else None
    drop_top5 = round(total - top5, 2)

    by_side = {}
    for sd in ("C", "P"):
        s = [r["pnl"] for r in rows if r["side"] == sd]
        if s:
            by_side[sd] = {"n": len(s), "exp": round(float(np.mean(s)), 2),
                           "wr": round(100 * float((np.array(s) > 0).mean()), 1),
                           "total": round(float(np.sum(s)), 2)}

    return {
        "n": n, "wr_pct": round(100 * wins / n, 1),
        "exp_dollar": round(float(pnl.mean()), 2), "total_dollar": round(float(pnl.sum()), 2),
        "is_n": len(is_rows), "is_exp": _exp(is_rows), "is_total": _tot(is_rows),
        "oos_n": len(oos_rows), "oos_exp": _exp(oos_rows), "oos_total": _tot(oos_rows),
        "quarters": quarters, "positive_quarters": f"{q_pos}/{len(quarters)}",
        "positive_quarters_n": q_pos, "n_quarters": len(quarters),
        "top5_day_pct": top5_pct, "drop_top5_total": drop_top5,
        "drop_top5_per_trade": round(drop_top5 / max(1, n - 5 * 0), 2) if n else None,
        "by_side": by_side,
    }


def _random_null(reads, rth, selected, *, side_counts, n_per_side, seeds=N_NULL_SEEDS):
    """Random-entry null: same #entries + same side mix, drawn from the SAME pool of
    eligible directional reads (any conviction/factor count), survivor structure, premium
    stop. Returns mean OOS exp + mean overall exp across seeds + how often strat beats null."""
    # pool keyed by side -> list of read dicts
    pool = {"C": [r for r in reads if r["side"] == "C"],
            "P": [r for r in reads if r["side"] == "P"]}
    seed_exps, seed_oos_exps = [], []
    rng = random.Random(20260620)
    for _ in range(seeds):
        picks: list[dict] = []
        for sd, k in n_per_side.items():
            avail = pool.get(sd, [])
            if not avail or k <= 0:
                continue
            picks.extend(rng.sample(avail, min(k, len(avail))))
        rows, _ = _simulate(picks, rth, premium_stop=PREMIUM_STOP_PCT)
        if not rows:
            continue
        m = _metrics(rows)
        seed_exps.append(m["exp_dollar"])
        if m["oos_exp"] is not None:
            seed_oos_exps.append(m["oos_exp"])
    return {
        "seeds_run": len(seed_exps),
        "mean_exp_dollar": round(float(np.mean(seed_exps)), 2) if seed_exps else None,
        "mean_oos_exp": round(float(np.mean(seed_oos_exps)), 2) if seed_oos_exps else None,
        "exp_p10": round(float(np.percentile(seed_exps, 10)), 2) if seed_exps else None,
        "exp_p90": round(float(np.percentile(seed_exps, 90)), 2) if seed_exps else None,
    }


def main() -> int:
    rth, vix_arr = _load_rth()
    log.info("Building bars + scanning confluence reads (every eligible bar)...")
    all_bars = _build_bars(rth)
    reads = _scan_reads(rth, all_bars, vix_arr)
    log.info("Directional reads (non-neutral, eligible): %d", len(reads))

    selected, conv_thresh = _select_extreme(reads)
    n_per_side = {"C": sum(1 for s in selected if s["side"] == "C"),
                  "P": sum(1 for s in selected if s["side"] == "P")}
    log.info("Top-decile conviction threshold = %.1f ; >=%d factors agree => %d selected (C=%d P=%d)",
             conv_thresh, MIN_FACTORS_AGREE, len(selected), n_per_side["C"], n_per_side["P"])

    # ── PRIMARY run: survivor structure, -8% premium stop ──────────────────────
    rows, no_data = _simulate(selected, rth, premium_stop=PREMIUM_STOP_PCT)
    m = _metrics(rows)
    log.info("PRIMARY: n=%d exp=$%s oos_exp=$%s is_exp=$%s posQ=%s top5%%=%s",
             m.get("n"), m.get("exp_dollar"), m.get("oos_exp"), m.get("is_exp"),
             m.get("positive_quarters"), m.get("top5_day_pct"))

    # ── G7 no-truncation: same selection, chart-stop-only (-0.99) ──────────────
    rows_ct, _ = _simulate(selected, rth, premium_stop=-0.99)
    m_ct = _metrics(rows_ct)
    log.info("CHART-STOP-ONLY: n=%d exp=$%s oos_exp=$%s", m_ct.get("n"), m_ct.get("exp_dollar"), m_ct.get("oos_exp"))

    # ── G6 random-entry null ───────────────────────────────────────────────────
    null = _random_null(reads, rth, selected, side_counts=n_per_side, n_per_side=n_per_side)
    log.info("RANDOM NULL: mean_exp=$%s mean_oos_exp=$%s (%d seeds)",
             null.get("mean_exp_dollar"), null.get("mean_oos_exp"), null.get("seeds_run"))

    # ── Evaluate ALL gates deterministically ───────────────────────────────────
    oos_exp = m.get("oos_exp")
    is_exp = m.get("is_exp")
    exp_overall = m.get("exp_dollar")
    null_mean = null.get("mean_exp_dollar")
    ct_oos = m_ct.get("oos_exp")
    ct_overall = m_ct.get("exp_dollar")

    gates = {
        "G1_oos_per_trade_gt0": bool(oos_exp is not None and oos_exp > 0),
        "G2_positive_quarters_ge4": bool(m.get("positive_quarters_n", 0) >= BAR_POS_Q),
        "G3_top5_day_lt200": bool(m.get("top5_day_pct") is not None and m["top5_day_pct"] < BAR_TOP5),
        "G4_n_ge20": bool(m.get("n", 0) >= BAR_N),
        "G5_drop_top5_gt0": bool(m.get("drop_top5_total") is not None and m["drop_top5_total"] > 0),
        "G6_beats_random_null": bool(
            exp_overall is not None and null_mean is not None and exp_overall > null_mean),
        "G7_no_sign_inversion_at_chartstop": bool(
            oos_exp is not None and ct_oos is not None
            and (oos_exp > 0) == (ct_oos > 0)
            and exp_overall is not None and ct_overall is not None
            and (exp_overall > 0) == (ct_overall > 0)),
        "G8_in_sample_also_positive": bool(is_exp is not None and is_exp > 0),
    }
    clears_all = all(gates.values())
    failed = [k for k, v in gates.items() if not v]

    if clears_all:
        verdict = ("CLEARS ALL GATES -- extreme selectivity converts confluence into a real "
                   "0DTE option edge on real fills. SHIP under standing authorization; report for REVOKE.")
    elif m.get("n", 0) < BAR_N:
        verdict = (f"UNDERPOWERED -- ruthless selectivity left only n={m.get('n', 0)} trades "
                   f"(<{BAR_N}); selectivity is REAL (few, high-agreement entries) but the sample "
                   f"is too thin to assert an edge. Failed: {failed}. Selectivity != edge here.")
    else:
        verdict = (f"FAILS -- extreme selectivity does NOT clear. Failed gates: {failed}. "
                   f"Consistent with the confluence engine's on-record verdict (awareness, not alpha; "
                   f"theta trap as a trigger). Selectivity narrows N but does not manufacture option edge.")

    summary = {
        "hypothesis": "confluence_score_extreme",
        "hypothesis_long": ("EXTREME SELECTIVITY: enter ONLY top-decile conviction AND >=4 "
                            "confluence factors agree; survivor structure (ITM-2, -8% premium stop, "
                            "v15 exits); real OPRA fills. Does ruthless selectivity clear?"),
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}",
        "engine": "crypto/lib/confluence.py compute_confluence (composes structure/EMA/VWAP/candle/pattern/level)",
        "fills_authority": "lib.simulator_real.simulate_trade_real (real OPRA fills, C1)",
        "spy_vs_option": "SPY-direction confluence != option edge (C3/L58); this IS the option-edge test",
        "selection": {
            "top_decile_quantile": TOP_DECILE,
            "conviction_threshold_data_driven": round(conv_thresh, 2),
            "min_factors_agree": MIN_FACTORS_AGREE,
            "cooldown_min": COOLDOWN_MIN, "trailing_bars": TRAIL, "warmup_bars": WARMUP,
        },
        "structure": {"qty": QTY, "strike_offset": STRIKE_OFFSET, "strike_tier": "ITM-2",
                      "premium_stop_pct": PREMIUM_STOP_PCT, "exits": "v15 tiered"},
        "n_directional_reads": len(reads),
        "n_selected": len(selected),
        "selected_side_count": n_per_side,
        "n_no_opra_data": no_data,
        "metrics_primary": m,
        "metrics_chartstop_only": m_ct,
        "random_null": null,
        "gates": gates,
        "gates_failed": failed,
        "clears_all_gates": clears_all,
        "verdict": verdict,
        "DISCLOSURE": {
            "per_trade": "per-trade expectancy reported, not WR alone (OP-14)",
            "is_oos": f"IS=2025 vs OOS={OOS_YEAR} split (OP-20)",
            "concentration": "top5_day_pct + drop-top-5-days both reported (OP-20 #5)",
            "null": f"random-entry null = same #entries + side-mix from the SAME read pool, {N_NULL_SEEDS} seeds",
            "no_truncation": "G7 re-runs identical selection at chart-stop-only (-0.99) to check sign stability",
            "no_survivor_pick": "single pre-registered config; ALL 8 gates evaluated deterministically (anti-pattern 2.10)",
            "n_honesty": "extreme selectivity is EXPECTED to yield small N; reported as-is, not inflated",
        },
        "results": rows,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT)

    print("\n=== CONFLUENCE_SCORE_EXTREME -- SELECTION VERDICT ===")
    print(f"directional reads={len(reads)}  selected={len(selected)} (C={n_per_side['C']} P={n_per_side['P']})  "
          f"conv_thresh={round(conv_thresh,1)} (>= {MIN_FACTORS_AGREE} factors)")
    print(f"PRIMARY (ITM-2/-8%): n={m.get('n')} exp=${m.get('exp_dollar')} "
          f"oos_exp=${m.get('oos_exp')} is_exp=${m.get('is_exp')} "
          f"posQ={m.get('positive_quarters')} top5%={m.get('top5_day_pct')} "
          f"drop_top5=${m.get('drop_top5_total')}")
    print(f"by_side={m.get('by_side')}")
    print(f"CHART-STOP-ONLY: exp=${m_ct.get('exp_dollar')} oos_exp=${m_ct.get('oos_exp')}")
    print(f"RANDOM NULL: mean_exp=${null.get('mean_exp_dollar')} mean_oos=${null.get('mean_oos_exp')}")
    print("GATES:")
    for k, v in gates.items():
        print(f"  {'PASS' if v else 'FAIL'}  {k}")
    print(f"CLEARS ALL GATES: {clears_all}")
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

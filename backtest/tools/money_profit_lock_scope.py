"""money_profit_lock_scope.py -- H4 PROFIT-LOCK SCOPE hypothesis test (2026-09-03-money).

READ-ONLY replay. Never touches automation/state/**, params.json, exit_manager.py, or any
trading-path file. Reuses setup/scripts/pdt_blocked_counterfactual.py's `_price_via_walker`
(walker="exit_manager" -> backtest/lib/exit_manager_walk.walk_exit_manager, which ticks the
REAL production automation/state/fleet/exit_manager.py#plan_exit_actions decision core) and
its `canonical_shape`/`resolve_trigger_level` date-keyed shape resolution -- no reimplementation
of exit logic.

POPULATION: all 394 scored round trips in analysis/pain-ledger/mae-mfe.json, joined to
analysis/trades-enriched.jsonl (vix, exit_reason, trigger_level, ret_pct_of_premium,
entry_ts_et) by (date, arm, symbol) + nearest entry_ts (mae-mfe's entry_ts_utc vs
trades-enriched's entry_ts_et) -- 394/394 matched cleanly (verified before writing this file).

BARS: prefers 1-min disk cache (backtest/data/highres/<symbol>_1m_<date>.csv, CACHE-ONLY read
-- never calls _option_bars_1min_cache.fetch_1min_cached, which has a live-REST fallback this
task's hard constraints forbid), falls back to the 5-min OPRA cache
(backtest/lib/option_pricing_real.load_contract_bars, also cache-only, returns None on miss).
Trades with neither cached are SKIPPED and counted, never estimated.

CONTROL = canonical_shape(date) unchanged (profit_lock_arm_scope='post_tp1', today's live
behaviour). TREATMENT = same shape with profit_lock_arm_scope='full' (arms the chandelier at
+5% favor regardless of TP1 fill, matching profit-lock-arm-scope-prereg-2026-08-06.json's
'full' definition).

HARNESS FIDELITY: per WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md, exit_manager_walk passes
the POOLED magnitude-fidelity criterion only via arithmetic cancellation across arms -- per-arm,
ONLY safe-2 (ratio 0.96) individually passes; bold-2 (6.44), risky-1 (1.72), safe-3 (sign-
flipped -0.12) do not. This script computes deltas for every arm but the report/JSON explicitly
label safe-2 dollars TRUSTED and every other arm's dollars SIGN-ONLY, per this task's hard
instruction.

$0, no network, deterministic.
"""
from __future__ import annotations

import json
import random
import statistics as stt
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in ("setup/scripts", "backtest/tools", "backtest/lib", "automation/state/fleet"):
    full = str(REPO / _p)
    if full not in sys.path:
        sys.path.insert(0, full)

import pandas as pd  # noqa: E402
import pdt_blocked_counterfactual as pbc  # noqa: E402
from option_pricing_real import load_contract_bars  # noqa: E402

MAE_MFE = REPO / "analysis/pain-ledger/mae-mfe.json"
TRADES_ENRICHED = REPO / "analysis/trades-enriched.jsonl"
HIGHRES_DIR = REPO / "backtest/data/highres"
OUT_DIR = REPO / "analysis/deep-research/2026-09-03-money"
ET_OFFSET = timezone(timedelta(hours=-4))

WINNER_ANCHOR_DATES = {"2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"}
MFE_THRESHOLDS = (0.10, 0.15, 0.20)
TRUSTED_ARMS = {"safe-2"}  # per WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md per-arm table


def to_et_str(iso_utc: str) -> str:
    ts = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
    return ts.astimezone(ET_OFFSET).strftime("%H:%M:%S")


def load_1min_cache_only(symbol: str, date: str):
    """Cache-only reader -- NEVER fetches. Mirrors _option_bars_1min_cache.fetch_1min_cached's
    cache-hit branch, omits its live-REST fallback (network forbidden this task).

    A handful of 2026-08-05 cache files on disk carry a DIFFERENT schema
    (timestamp/trade_count/vwap instead of timestamp_et) -- the same anomaly
    WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md flagged for that date's cache. Normalized
    here (rename timestamp->timestamp_et) rather than skipped, since the underlying OHLC data
    is present and usable; disclosed, not silently patched over."""
    path = HIGHRES_DIR / f"{symbol}_1m_{date}.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        if "timestamp_et" not in df.columns and "timestamp" in df.columns:
            # alt-schema file: raw UTC ISO ("...Z") -- verified on the 2026-08-05 anomaly
            # files (13:30Z == 09:30 ET open) -- convert UTC->ET, do NOT treat as already-ET.
            ts_utc = pd.to_datetime(df["timestamp"], utc=True)
            df["timestamp_et"] = ts_utc.dt.tz_convert("America/New_York").dt.tz_localize(None)
            return df
        if "timestamp_et" not in df.columns or df.empty:
            return None
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], format="mixed").dt.tz_localize(None)
        return df
    except Exception:  # noqa: BLE001 -- malformed cache file, treat as a miss, never crash the run
        return None


def load_te_rows():
    rows = []
    with open(TRADES_ENRICHED, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("_meta"):
                continue
            rows.append(r)
    return rows


def match_te(mm_trade: dict, te_by_key: dict) -> dict | None:
    key = (mm_trade["date"], mm_trade["arm"], mm_trade["symbol"])
    cands = te_by_key.get(key, [])
    if not cands:
        return None
    if len(cands) == 1:
        return cands[0]
    t_et = datetime.fromisoformat(mm_trade["entry_ts_utc"].replace("Z", "+00:00")).astimezone(ET_OFFSET)
    best, bestdiff = None, None
    for c in cands:
        c_et = datetime.fromisoformat(c["entry_ts_et"])
        diff = abs((c_et.replace(tzinfo=None) - t_et.replace(tzinfo=None)).total_seconds())
        if bestdiff is None or diff < bestdiff:
            bestdiff, best = diff, c
    if bestdiff is not None and bestdiff < 90:
        return best
    return None


def bootstrap_ci(values: list[float], n_resamples: int = 5000, seed: int = 42):
    if not values:
        return {"mean": None, "ci_lo": None, "ci_hi": None, "n": 0}
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        means.append(sum(sample) / n)
    means.sort()
    lo_idx = int(0.025 * n_resamples)
    hi_idx = int(0.975 * n_resamples) - 1
    return {
        "mean": sum(values) / n,
        "ci_lo": means[lo_idx],
        "ci_hi": means[hi_idx],
        "n": n,
        "n_resamples": n_resamples,
    }


def vix_regime(vix):
    if vix is None:
        return "unknown"
    if vix < 15:
        return "vix<15"
    if vix <= 17:
        return "vix_15_17"
    return "vix>17"


def main():
    mm = json.load(open(MAE_MFE, encoding="utf-8"))["trades"]
    te_rows = load_te_rows()
    te_by_key: dict = {}
    for r in te_rows:
        te_by_key.setdefault((r["date"], r["arm"], r["symbol"]), []).append(r)

    spy_map = pbc.spy_by_day()

    merged = []
    n_te_unmatched = 0
    for t in mm:
        te = match_te(t, te_by_key)
        if te is None:
            n_te_unmatched += 1
        merged.append({"mm": t, "te": te})

    # ---- bar loading + walk ----
    results = []
    n_skipped_no_bars = 0
    skipped_rows = []
    for row in merged:
        t = row["mm"]
        te = row["te"] or {}
        symbol, date, arm = t["symbol"], t["date"], t["arm"]
        bars = load_1min_cache_only(symbol, date)
        bar_res = "1min"
        if bars is None or len(bars) == 0:
            bars = load_contract_bars(symbol)
            bar_res = "5min"
        if bars is None or len(bars) == 0:
            n_skipped_no_bars += 1
            skipped_rows.append({"date": date, "arm": arm, "symbol": symbol, "reason": "no_bars"})
            continue

        et_time = to_et_str(t["entry_ts_utc"])
        account = pbc.ARM2ACCOUNT.get(arm)  # None for fleet arms (safe-1/3, risky-1/3) -- disclosed
        shape = pbc.canonical_shape(date)
        trig_raw = te.get("trigger_level")
        trig = pbc.resolve_trigger_level(date, trig_raw)
        fill = {
            "entry_premium": t["entry_price"], "qty": int(t["qty"]), "symbol": symbol,
            "date": date, "entry_time": et_time, "strategy": t.get("setup") or "RIBBON",
            "account": account,
        }
        try:
            res_control = pbc._price_via_walker(
                "exit_manager", fill, shape, bars, trigger_level=trig, spy_map=spy_map)
            shape_full = dict(shape)
            shape_full["profit_lock_arm_scope"] = "full"
            res_full = pbc._price_via_walker(
                "exit_manager", fill, shape_full, bars, trigger_level=trig, spy_map=spy_map)
        except Exception as exc:  # noqa: BLE001
            n_skipped_no_bars += 1
            skipped_rows.append({"date": date, "arm": arm, "symbol": symbol,
                                  "reason": f"walk_error:{type(exc).__name__}:{exc}"})
            continue

        if "error" in res_control or "error" in res_full:
            n_skipped_no_bars += 1
            skipped_rows.append({"date": date, "arm": arm, "symbol": symbol,
                                  "reason": f"walk_error:{res_control.get('error') or res_full.get('error')}"})
            continue

        control_pnl = float(res_control["pnl"])
        full_pnl = float(res_full["pnl"])
        delta = full_pnl - control_pnl
        actual_pnl = float(t["realized_pnl"])
        sign_agree = (control_pnl >= 0) == (actual_pnl >= 0)

        results.append({
            "date": date, "arm": arm, "symbol": symbol, "setup": t.get("setup"),
            "outcome": t["outcome"], "mfe_pct": t.get("mfe_pct"), "vix": te.get("vix"),
            "regime": vix_regime(te.get("vix")), "exit_reason_recorded": te.get("exit_reason"),
            "ret_pct_of_premium": te.get("ret_pct_of_premium"), "bar_res": bar_res,
            "trigger_mode": "structure" if trig else "premium",
            "actual_pnl": actual_pnl, "control_pnl": control_pnl, "full_pnl": full_pnl,
            "delta_full_minus_control": delta, "control_walked_stage": res_control.get("walked_stage"),
            "full_walked_stage": res_full.get("walked_stage"), "control_sign_agrees_actual": sign_agree,
            "trusted_dollars": arm in TRUSTED_ARMS,
        })

    n_matched = len(results)

    # ---- harness fidelity: sign agreement overall + per arm ----
    def sign_agreement(rows):
        rows = [r for r in rows if r["control_sign_agrees_actual"] is not None]
        if not rows:
            return None
        return sum(1 for r in rows if r["control_sign_agrees_actual"]) / len(rows)

    arms = sorted({r["arm"] for r in results})
    fidelity_by_arm = {a: {"n": len([r for r in results if r["arm"] == a]),
                            "sign_agreement": sign_agreement([r for r in results if r["arm"] == a])}
                        for a in arms}
    fidelity_overall = {"n": n_matched, "sign_agreement": sign_agreement(results)}

    # ---- H1: frequency of losers with mfe_pct >= threshold that ended at cap ----
    def ended_at_cap(r):
        er = r.get("exit_reason_recorded")
        rp = r.get("ret_pct_of_premium")
        return er == "premium_stop" and rp is not None and rp <= -40.0

    losers = [r for r in results if r["outcome"] == "loser"]
    freq_table = {}
    for thr in MFE_THRESHOLDS:
        pool = [r for r in losers if (r["mfe_pct"] or 0) >= thr]
        cap_hits = [r for r in pool if ended_at_cap(r)]
        freq_table[str(thr)] = {
            "n_losers_mfe_ge_thr": len(pool),
            "n_ended_at_cap": len(cap_hits),
            "pct_ended_at_cap": (len(cap_hits) / len(pool)) if pool else None,
            "pct_of_all_losers": len(pool) / len(losers) if losers else None,
            "n_all_losers": len(losers),
        }

    # ---- H2: dollar delta full-scope vs control, per arm / per regime, bootstrap CI ----
    safe2_rows = [r for r in results if r["arm"] == "safe-2"]
    safe2_deltas = [r["delta_full_minus_control"] for r in safe2_rows]
    safe2_ci = bootstrap_ci(safe2_deltas)

    pooled_all_deltas = [r["delta_full_minus_control"] for r in results]
    pooled_ci_signonly = bootstrap_ci(pooled_all_deltas)  # NOT dollar-trusted except safe-2 subset

    per_arm = {}
    for a in arms:
        rows_a = [r for r in results if r["arm"] == a]
        deltas = [r["delta_full_minus_control"] for r in rows_a]
        per_arm[a] = {
            "n": len(rows_a),
            "total_control_pnl": round(sum(r["control_pnl"] for r in rows_a), 2),
            "total_full_pnl": round(sum(r["full_pnl"] for r in rows_a), 2),
            "total_delta": round(sum(deltas), 2),
            "n_delta_positive": sum(1 for d in deltas if d > 0),
            "n_delta_negative": sum(1 for d in deltas if d < 0),
            "n_delta_zero": sum(1 for d in deltas if d == 0),
            "bootstrap": bootstrap_ci(deltas) if a in TRUSTED_ARMS else None,
            "trusted_dollars": a in TRUSTED_ARMS,
        }

    per_regime = {}
    for reg in ("vix<15", "vix_15_17", "vix>17", "unknown"):
        rows_r = [r for r in results if r["regime"] == reg]
        rows_r_safe2 = [r for r in rows_r if r["arm"] == "safe-2"]
        deltas_safe2 = [r["delta_full_minus_control"] for r in rows_r_safe2]
        per_regime[reg] = {
            "n_all_arms": len(rows_r),
            "n_safe2": len(rows_r_safe2),
            "total_delta_all_arms_sign_only": round(sum(r["delta_full_minus_control"] for r in rows_r), 2),
            "total_delta_safe2_trusted": round(sum(deltas_safe2), 2) if rows_r_safe2 else None,
            "bootstrap_safe2": bootstrap_ci(deltas_safe2) if rows_r_safe2 else None,
        }

    # ---- top-3 concentration ----
    def top3_concentration(rows, key="delta_full_minus_control"):
        rows_sorted = sorted(rows, key=lambda r: abs(r[key]), reverse=True)
        top3 = rows_sorted[:3]
        total_abs = sum(abs(r[key]) for r in rows) or 1.0
        top3_abs = sum(abs(r[key]) for r in top3)
        return {
            "top3": [{"date": r["date"], "arm": r["arm"], "symbol": r["symbol"],
                      "delta": round(r[key], 2), "trusted_dollars": r["trusted_dollars"]}
                     for r in top3],
            "top3_share_of_total_abs_delta": top3_abs / total_abs,
        }

    concentration_all = top3_concentration(results)
    concentration_safe2 = top3_concentration(safe2_rows) if safe2_rows else None

    # ---- anchor days (would the change hurt/block the big winners) ----
    anchor_rows = [r for r in results if r["date"] in WINNER_ANCHOR_DATES]
    anchor_detail = sorted(
        [{"date": r["date"], "arm": r["arm"], "symbol": r["symbol"], "actual_pnl": r["actual_pnl"],
          "control_pnl": r["control_pnl"], "full_pnl": r["full_pnl"],
          "delta": round(r["delta_full_minus_control"], 2), "mfe_pct": r["mfe_pct"],
          "control_stage": r["control_walked_stage"], "full_stage": r["full_walked_stage"],
          "trusted_dollars": r["trusted_dollars"]} for r in anchor_rows],
        key=lambda x: (x["date"], x["arm"]))
    anchor_summary = {
        "n_rows_on_anchor_dates": len(anchor_rows),
        "n_dates_with_data": len({r["date"] for r in anchor_rows}),
        "dates_present": sorted({r["date"] for r in anchor_rows}),
        "n_hurt_full_lt_control": sum(1 for r in anchor_rows if r["full_pnl"] < r["control_pnl"]),
        "n_helped_full_gt_control": sum(1 for r in anchor_rows if r["full_pnl"] > r["control_pnl"]),
        "n_unchanged": sum(1 for r in anchor_rows if r["full_pnl"] == r["control_pnl"]),
        "total_delta_all_arms_sign_only": round(sum(r["delta_full_minus_control"] for r in anchor_rows), 2),
        "safe2_total_delta_trusted": round(sum(r["delta_full_minus_control"] for r in anchor_rows if r["arm"] == "safe-2"), 2),
    }

    out = {
        "hypothesis": "H4-PROFIT-LOCK-SCOPE",
        "generated_at_et_stamp": "2026-09-03T10:24 ET (task stamp); run executed same session",
        "population": {
            "n_mae_mfe_trades": len(mm),
            "n_te_matched": len(mm) - n_te_unmatched,
            "n_te_unmatched": n_te_unmatched,
            "n_walked": n_matched,
            "n_skipped_no_bars_or_error": n_skipped_no_bars,
            "skipped_detail": skipped_rows,
            "arms_present": arms,
        },
        "harness_fidelity_this_run": {
            "overall": fidelity_overall,
            "per_arm": fidelity_by_arm,
            "note": "control-walk pnl sign vs actual broker realized_pnl sign. Independent of, "
                    "and consistent in spirit with, WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md's "
                    "finding that only safe-2 individually clears the walker's magnitude-fidelity "
                    "bar -- dollars trusted for safe-2 ONLY, sign-only elsewhere per task instruction.",
        },
        "frequency_losers_mfe_ge_threshold_ended_at_cap": freq_table,
        "ended_at_cap_definition": "exit_reason_recorded=='premium_stop' AND ret_pct_of_premium<=-40% "
                                    "(disclosed heuristic: trades-enriched's own _meta flags exit_reason "
                                    "premium_stop as containing 65/276 mislabeled rows -- see "
                                    "exit_reason_premium_stop_suspect; median ret_pct for ALL "
                                    "premium_stop-labeled rows is only -17.08%, so the raw label alone "
                                    "is not trustworthy as 'hit the -50% catastrophe cap'. The -40 to "
                                    "-60% band contains 34/44 premium_stop rows and only 7 structure_stop "
                                    "rows -- used as a cleaner catastrophe-cap proxy).",
        "dollar_effect_safe2_trusted": {
            "bootstrap": safe2_ci,
            "total_control_pnl": round(sum(r["control_pnl"] for r in safe2_rows), 2),
            "total_full_pnl": round(sum(r["full_pnl"] for r in safe2_rows), 2),
            "total_delta": round(sum(safe2_deltas), 2),
        },
        "dollar_effect_pooled_all_arms_SIGN_ONLY": {
            "bootstrap": pooled_ci_signonly,
            "note": "INCLUDES bold-2/risky-1/risky-3/safe-1/safe-3 dollars, which per "
                    "WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md do NOT individually pass the "
                    "walker magnitude-fidelity bar. Sign/direction only -- do not cite this dollar "
                    "figure as a trustworthy magnitude.",
        },
        "per_arm": per_arm,
        "per_regime": per_regime,
        "concentration": {"all_arms": concentration_all, "safe2_only": concentration_safe2},
        "anchor_winning_days": {"summary": anchor_summary, "detail": anchor_detail},
        "trades": results,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_DIR / "profit-lock-scope.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)

    print("n_walked", n_matched, "n_skipped", n_skipped_no_bars)
    print("safe2 n", len(safe2_rows), "safe2 total delta", round(sum(safe2_deltas), 2))
    print("safe2 bootstrap", safe2_ci)
    print("fidelity overall", fidelity_overall)
    print("fidelity per arm", fidelity_by_arm)
    print("anchor summary", anchor_summary)
    print("freq table", json.dumps(freq_table, indent=2))


if __name__ == "__main__":
    main()

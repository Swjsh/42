"""Statistics for the which-Friday expiry experiment, exactly as the prereg froze them.

Prereg: analysis/recommendations/prereg-weekly-expiry-comparison-2026-08-18.json

Runs, in order:
  1. Per-arm descriptives (primary = % return on premium; win rate is SECONDARY and reported
     only for context -- the prereg forbids ranking on it, because the edge is a right tail
     and win rate would rank arms by frequency of small wins).
  2. Paired Wilcoxon signed-rank on the 3 pairwise contrasts among the weekly arms, with a
     HOLM correction across that family. MONTHLY is a descriptive control, excluded from the
     corrected family per the prereg.
  3. The RANDOM-ENTRY NULL at its MAX. This is the gate that decides whether any of this
     means anything: the same contracts, the same walk, the same arms -- but entries placed on
     RANDOM sessions instead of signal sessions. If the signal cannot beat the best of many
     random-entry draws, then the level trigger adds nothing and the expiry question is moot.
     Comparing against the null's MAX rather than its mean is deliberate: with several arms and
     many draws, beating an average null is easy by chance.
  4. Disclosures the prereg requires on every output: per-arm n, DTE, modeled spread, adverse-
     resolution and gap counts, and the zone-family concentration carried over from the
     density probe.

This file DECIDES nothing on its own -- it prints what the frozen decision rule implies.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics as st
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy import stats as sps

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest" / "lib", REPO / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import multiday_walk as mw  # noqa: E402
import option_iv_solve as ivs  # noqa: E402
import weekly_expiry_experiment as wee  # noqa: E402

LEDGER = REPO / "automation" / "state" / "weekly" / "expiry-experiment-shadow-ledger.jsonl"
OUT = REPO / "analysis" / "weekly-lane" / "expiry-experiment-report.json"
CORE_ARMS = ("SAME_WEEK", "NEXT_WEEK", "TWO_WEEKS_OUT")


def holm(pvals: dict[str, float]) -> dict[str, dict]:
    """Holm-Bonferroni step-down across the contrast family."""
    ordered = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(ordered)
    out, prev = {}, 0.0
    for i, (k, p) in enumerate(ordered):
        adj = max(prev, min(1.0, (m - i) * p))
        prev = adj
        out[k] = {"p_raw": p, "p_holm": adj, "significant_at_0.05": adj < 0.05}
    return out


def descriptives(rows: list[dict]) -> dict:
    r = [x["return_pct"] for x in rows]
    d = [x["dte_at_entry"] for x in rows]
    pnl = [x["pnl_dollars"] for x in rows]
    reasons = defaultdict(int)
    for x in rows:
        reasons[x.get("exit_reason", "?")] += 1
    return {
        "n": len(r),
        "median_dte_at_entry": st.median(d),
        "mean_return_pct": round(st.mean(r), 3),
        "median_return_pct": round(st.median(r), 3),
        "stdev_return_pct": round(st.pstdev(r), 3) if len(r) > 1 else None,
        "mean_pnl_dollars": round(st.mean(pnl), 2),
        "total_pnl_dollars": round(sum(pnl), 2),
        "_win_rate_SECONDARY": round(100.0 * sum(1 for x in r if x > 0) / len(r), 2),
        "right_tail_share_ge_30pct": round(100.0 * sum(1 for x in r if x >= 30) / len(r), 2),
        "exit_reasons": dict(sorted(reasons.items(), key=lambda kv: -kv[1])),
        "adverse_resolution_sessions": sum(x.get("adverse_resolution_sessions", 0) for x in rows),
        "gapped_through_sessions": sum(x.get("gapped_through_sessions", 0) for x in rows),
        "exited_on_expiry_day": sum(1 for x in rows if x.get("exited_on_expiry_day")),
        "expiry_fallbacks": sum(1 for x in rows if x.get("expiry_fallback")),
        "mean_abs_delta": round(st.mean([abs(x["delta"]) for x in rows]), 4),
        "mean_delta_err": round(st.mean([x["delta_err"] for x in rows]), 4),
    }


def random_entry_null(params: dict, symbols: list[str], n_per_draw: int, draws: int,
                      spread_pct: float, seed: int) -> dict:
    """Same machinery, random entry sessions. Returns the per-arm distribution of mean return."""
    rng = random.Random(seed)
    min_dte = int(params["entry"]["min_dte_at_entry"])
    shape = params["exits"]
    per_arm_draw_means: dict[str, list[float]] = defaultdict(list)

    # Build the candidate session universe from the cached contract bars themselves.
    universe: dict[str, list] = {}
    for sym in symbols:
        idx = wee.build_index(sym)
        expiries = sorted(idx)
        sessions = sorted({b.date_et
                           for e in expiries[:400]
                           for meta in idx[e]["C"][:2]
                           for b in wee.contract_bars(sym, meta["contract"])})
        universe[sym] = (idx, expiries, sessions)

    for draw in range(draws):
        arm_returns: dict[str, list[float]] = defaultdict(list)
        placed = 0
        guard = 0
        while placed < n_per_draw and guard < n_per_draw * 25:
            guard += 1
            sym = rng.choice(symbols)
            idx, expiries, sessions = universe[sym]
            if not sessions:
                continue
            entry_session = rng.choice(sessions)
            right = rng.choice(("C", "P"))
            got = {}
            for rule in CORE_ARMS:
                sel = wee.select_expiry(rule, expiries, entry_session, min_dte)
                if sel is None:
                    break
                cands = []
                for meta in idx[sel["expiry"]][right]:
                    px = wee.price_on(sym, meta["contract"], entry_session)
                    if px and px > 0:
                        cands.append({"strike": meta["strike"], "price": px,
                                      "contract": meta["contract"]})
                if not cands:
                    break
                t_years = max(sel["dte"], 1) / 365.0
                pick = ivs.pick_delta_matched(
                    cands, wee.TARGET_DELTA, spot=None or _spot_proxy(cands),
                    t_years=t_years, right=right, rate=wee.RATE,
                    div_yield=wee.DIV_YIELD.get(sym, 0.0))
                if pick is None:
                    break
                qty = max(1, int(wee.RISK_BUDGET_DOLLARS // (pick["price"] * 100.0)))
                bars = wee.contract_bars(sym, pick["contract"])
                if not bars:
                    break
                pos = mw.MultiDayPosition(
                    contract=pick["contract"], symbol=sym, side=right,
                    entry_date=entry_session, entry_mid=pick["price"], qty=qty,
                    expiry=sel["expiry"], zone_width=1.0,
                    entry_underlying=_spot_proxy(cands))
                try:
                    res = mw.walk(pos, bars, shape, spread_pct=spread_pct, params=params)
                except (mw.WalkError, ValueError):
                    break
                got[rule] = res.return_pct
            if len(got) == len(CORE_ARMS):
                for k, v in got.items():
                    arm_returns[k].append(v)
                placed += 1
        for k, v in arm_returns.items():
            if v:
                per_arm_draw_means[k].append(st.mean(v))

    return {
        k: {
            "draws": len(v),
            "null_mean_of_means": round(st.mean(v), 3) if v else None,
            "null_MAX_of_means": round(max(v), 3) if v else None,
            "null_min_of_means": round(min(v), 3) if v else None,
        }
        for k, v in sorted(per_arm_draw_means.items())
    }


def _spot_proxy(cands: list[dict]) -> float:
    """Approximate spot as the strike whose call price is closest to ATM-parity.

    The random-entry null has no recorded signal close to use as spot, so it is inferred from
    the option chain itself. Documented as an approximation: it only affects the null's strike
    choice, never the real experiment's (which uses the signal's recorded close).
    """
    return st.median([c["strike"] for c in cands])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--null-draws", type=int, default=30)
    ap.add_argument("--null-n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--spread-pct", type=float, default=0.05)
    ap.add_argument("--skip-null", action="store_true")
    args = ap.parse_args(argv)

    if not LEDGER.exists():
        print(f"ERROR: no ledger at {LEDGER} -- run weekly_expiry_experiment.py first",
              file=sys.stderr)
        return 1
    rows = [json.loads(l) for l in LEDGER.open(encoding="utf-8")]
    by_arm = defaultdict(list)
    for r in rows:
        by_arm[r["arm"]].append(r)

    desc = {a: descriptives(v) for a, v in sorted(by_arm.items())}

    # Paired contrasts: align on (signal_session, symbol, direction).
    def key(r):
        return (r["signal_session"], r["symbol"], r["direction"], r["zone_family"])
    keyed = {a: {key(r): r["return_pct"] for r in v} for a, v in by_arm.items()}

    contrasts, pvals = {}, {}
    for i, a in enumerate(CORE_ARMS):
        for b in CORE_ARMS[i + 1:]:
            shared = sorted(set(keyed[a]) & set(keyed[b]))
            xa = [keyed[a][k] for k in shared]
            xb = [keyed[b][k] for k in shared]
            diffs = [x - y for x, y in zip(xa, xb)]
            name = f"{a}_vs_{b}"
            if len(shared) < 10 or all(d == 0 for d in diffs):
                contrasts[name] = {"n_pairs": len(shared), "note": "insufficient/degenerate"}
                continue
            stat, p = sps.wilcoxon(xa, xb)
            contrasts[name] = {
                "n_pairs": len(shared),
                "median_diff_pct": round(float(np.median(diffs)), 3),
                "mean_diff_pct": round(float(np.mean(diffs)), 3),
                "wilcoxon_stat": float(stat),
            }
            pvals[name] = float(p)
    for name, h in holm(pvals).items():
        contrasts[name].update(h)

    null = None
    if not args.skip_null:
        print(f"running random-entry null: {args.null_draws} draws x {args.null_n} entries...",
              file=sys.stderr)
        params = json.loads(wee.PARAMS.read_text(encoding="utf-8"))
        symbols = sorted({r["symbol"] for r in rows})
        null = random_entry_null(params, symbols, args.null_n, args.null_draws,
                                 args.spread_pct, args.seed)

    null_verdict = {}
    if null:
        for a in CORE_ARMS:
            real = desc[a]["mean_return_pct"]
            nmax = (null.get(a) or {}).get("null_MAX_of_means")
            null_verdict[a] = {
                "real_mean_return_pct": real,
                "null_MAX_of_means": nmax,
                "beats_null_MAX": (nmax is not None and real > nmax),
            }

    report = {
        "experiment": "weekly_expiry_comparison",
        "prereg": "analysis/recommendations/prereg-weekly-expiry-comparison-2026-08-18.json",
        "primary_metric": "percent return on premium, net of modeled spread",
        "per_arm": desc,
        "contrasts_holm_corrected": contrasts,
        "random_entry_null": null,
        "null_gate": null_verdict,
        "disclosures": {
            "spread_pct_assumed": args.spread_pct,
            "intraday_path_unknown": True,
            "adverse_resolution": "sessions touching both target and stop resolved AGAINST the position",
            "quote_feed": "indicative (this account has no OPRA agreement)",
            "zone_family_concentration": "round_numbers produced ~55% of all signals (density probe)",
            "monthly_arm": "descriptive control; excluded from the Holm family per prereg",
        },
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print("\n=== PER ARM (primary: % return on premium) ===", file=sys.stderr)
    for a, d in desc.items():
        print(f"{a:14} n={d['n']:3} DTE~{d['median_dte_at_entry']:4.0f} "
              f"mean={d['mean_return_pct']:8.2f}% median={d['median_return_pct']:8.2f}% "
              f"tail>=+30%={d['right_tail_share_ge_30pct']:5.1f}% "
              f"(winrate {d['_win_rate_SECONDARY']:.0f}%)", file=sys.stderr)
    print("\n=== CONTRASTS (Holm-corrected) ===", file=sys.stderr)
    for k, v in contrasts.items():
        if "p_holm" in v:
            print(f"{k:34} n={v['n_pairs']:3} medΔ={v['median_diff_pct']:7.2f}pp "
                  f"p={v['p_raw']:.4f} p_holm={v['p_holm']:.4f} "
                  f"{'SIG' if v['significant_at_0.05'] else 'ns'}", file=sys.stderr)
    if null_verdict:
        print("\n=== RANDOM-ENTRY NULL GATE (must beat the null's MAX) ===", file=sys.stderr)
        for a, v in null_verdict.items():
            print(f"{a:14} real={v['real_mean_return_pct']:8.2f}% "
                  f"nullMAX={v['null_MAX_of_means']} -> "
                  f"{'PASS' if v['beats_null_MAX'] else 'FAIL'}", file=sys.stderr)
    print(f"\nwrote {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

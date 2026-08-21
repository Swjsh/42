"""WP-4 STAGE A — does the forked 5-minute signal predict DIRECTION on non-SPY names?

The absolute gate, run exactly as frozen in
`analysis/recommendations/prereg-multi-intraday-null-2026-08-20.json`.

WHY STAGE A NEEDS NO OPTION DATA: the gate's core question is whether the signal beats random
entry. That is a property of the SIGNAL and the UNDERLYING. Measured beforehand, intraday option
bars are ~20% covered (volume-gated), so involving them here would let a data artifact confound
the decisive test. If the trigger cannot predict direction on 5m underlying moves, no option
expression rescues it -- and we learn that cheaply.

NO LOOK-AHEAD, and it is the whole ballgame:
at every replayed bar i, levels / level-states / ATR / ribbon are derived from `bars[:i+1]`
ONLY -- the same strict-slicing discipline proven in weekly_signal_density_probe.py. Forward
returns are read from bars AFTER i and never enter the decision. A single leak here would
manufacture an edge out of nothing, which is precisely what this harness exists to prevent.

Reads only. Places no orders. Writes one JSON report.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from multi import core as mcore  # noqa: E402
from multi.lib import context as mctx  # noqa: E402
from multi.lib import creds as mc  # noqa: E402
from multi.lib import levels as mlv  # noqa: E402
from multi.lib import signal as ms  # noqa: E402

OUT = REPO / "analysis" / "multi-lane" / "intraday-null-stageA.json"
PREREG = REPO / "analysis" / "recommendations" / "prereg-multi-intraday-null-2026-08-20.json"

HORIZONS = (2, 6, 12)          # 5m bars -> 10 / 30 / 60 minutes
HEADLINE_HORIZON = 6           # frozen: 30 minutes
WARMUP = 220                   # ribbon EMAs + ATR(14) need room before the first decision


class HarnessError(RuntimeError):
    """Fail loud: an empty or short run must never be reported as a result."""


def replay_symbol(symbol: str, bars, params: dict, *, warmup: int = WARMUP) -> tuple:
    """Bar-by-bar replay. Returns (signals, n_evaluated).

    `signals` = [{i, direction, fwd_{h}...}] where every fwd_ is measured AFTER the decision bar.
    """
    closes = [float(x) for x in bars["close"].to_numpy()]
    n = len(bars)
    out, evaluated = [], 0
    max_h = max(HORIZONS)

    # Recomputing levels every bar is exact but O(n^2)-ish; refresh on a cadence and reuse
    # between refreshes. The refresh always uses STRICTLY-EARLIER bars, so this is a cost
    # optimization, never a look-ahead shortcut.
    lv_active, lv_multi, lv_at = None, None, -10**9
    LEVEL_REFRESH_BARS = 12

    for i in range(warmup, n - max_h):
        window = bars.iloc[: i + 1]                      # strictly up to and including bar i
        if lv_active is None or (i - lv_at) >= LEVEL_REFRESH_BARS:
            try:
                lv_active, lv_multi = mlv.compute_levels(window)
                lv_at = i
            except mlv.LevelError:
                continue
        if not lv_active:
            continue
        evaluated += 1
        try:
            sig = ms.build_signal(symbol, window, params=params,
                                  candidate_levels=lv_active,
                                  candidate_multi_day_levels=lv_multi)
        except (ms.SignalBuildError, ValueError):
            continue

        action = str(sig.get("action") or "HOLD").upper()
        if action not in ("ENTER_BULL", "ENTER_BEAR"):
            continue
        sign = 1.0 if action == "ENTER_BULL" else -1.0
        base = closes[i]
        if base <= 0:
            continue
        rec = {"i": i, "direction": action,
               "ts": bars.index[i].isoformat(),
               "bear_score": (sig.get("bear") or {}).get("score"),
               "bull_score": (sig.get("bull") or {}).get("score")}
        for h in HORIZONS:
            raw = 100.0 * (closes[i + h] / base - 1.0)
            rec[f"fwd_{h}"] = round(sign * raw, 5)        # signed IN THE SIGNAL'S DIRECTION
            rec[f"abs_{h}"] = round(abs(raw), 5)
        out.append(rec)
    return out, evaluated


def baseline_pool(bars, *, warmup: int = WARMUP) -> list:
    """Every eligible bar's forward returns -- the population random entries are drawn from."""
    closes = [float(x) for x in bars["close"].to_numpy()]
    n, max_h = len(bars), max(HORIZONS)
    pool = []
    for i in range(warmup, n - max_h):
        base = closes[i]
        if base <= 0:
            continue
        row = {"i": i}
        for h in HORIZONS:
            row[f"raw_{h}"] = 100.0 * (closes[i + h] / base - 1.0)
        pool.append(row)
    return pool


def random_null(pools: dict, sig_counts: dict, dir_mix: dict, draws: int, seed: int) -> dict:
    """Random entries from the SAME symbol-session population, same count, same direction mix."""
    rng = random.Random(seed)
    per_h = {h: [] for h in HORIZONS}
    symbols = [s for s in pools if pools[s]]
    if not symbols:
        raise HarnessError("no baseline pool to draw a null from")

    for _ in range(draws):
        acc = {h: [] for h in HORIZONS}
        for sym in symbols:
            k = sig_counts.get(sym, 0)
            if k <= 0:
                continue
            picks = [rng.choice(pools[sym]) for _ in range(k)]
            bull_frac = dir_mix.get(sym, 0.5)
            for p in picks:
                sign = 1.0 if rng.random() < bull_frac else -1.0
                for h in HORIZONS:
                    acc[h].append(sign * p[f"raw_{h}"])
        for h in HORIZONS:
            if acc[h]:
                per_h[h].append(st.mean(acc[h]))
    return {h: {"draws": len(v),
                "null_mean_of_means": round(st.mean(v), 5) if v else None,
                "null_MAX_of_means": round(max(v), 5) if v else None}
            for h, v in per_h.items()}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--symbols", default=None)
    ap.add_argument("--bars", type=int, default=10000)
    ap.add_argument("--draws", type=int, default=40)
    ap.add_argument("--seed", type=int, default=17)
    args = ap.parse_args(argv)

    prereg = json.loads(PREREG.read_text(encoding="utf-8"))
    syms = ([s.strip().upper() for s in args.symbols.split(",")]
            if args.symbols else list(prereg["test_symbols"]["set"]))
    min_n = int(prereg["statistics"]["min_signals_required"])

    params = mc.load_params()
    creds = mc.resolve(params)
    frames = mcore.fetch_bars_batch(creds, syms, "5Min", limit=args.bars)
    if not frames:
        raise HarnessError("no 5-minute bars returned -- refusing to report a result")

    all_sig, pools, counts, mix, evaluated = {}, {}, {}, {}, {}
    for sym in syms:
        df = frames.get(sym)
        if df is None or len(df) < WARMUP + max(HORIZONS) + 10:
            print(f"  [{sym}] skipped: {0 if df is None else len(df)} bars", file=sys.stderr)
            continue
        sigs, ev = replay_symbol(sym, df, params)
        all_sig[sym], evaluated[sym] = sigs, ev
        pools[sym] = baseline_pool(df)
        counts[sym] = len(sigs)
        bulls = sum(1 for s in sigs if s["direction"] == "ENTER_BULL")
        mix[sym] = (bulls / len(sigs)) if sigs else 0.5
        print(f"  [{sym}] {len(sigs)} signals / {ev} evaluated bars ({len(df)} bars)",
              file=sys.stderr)

    flat = [s for v in all_sig.values() for s in v]
    total = len(flat)
    if total == 0:
        print("VERDICT: ZERO signals across all symbols. Not a weak result -- no result.",
              file=sys.stderr)

    per_h = {}
    for h in HORIZONS:
        vals = [s[f"fwd_{h}"] for s in flat]
        abs_vals = [s[f"abs_{h}"] for s in flat]
        base_abs = [abs(p[f"raw_{h}"]) for v in pools.values() for p in v]
        per_h[h] = {
            "n": len(vals),
            "mean_signed_return_pct": round(st.mean(vals), 5) if vals else None,
            "median_signed_return_pct": round(st.median(vals), 5) if vals else None,
            "hit_rate_pct": round(100.0 * sum(1 for v in vals if v > 0) / len(vals), 2) if vals else None,
            "mean_abs_move_pct": round(st.mean(abs_vals), 5) if abs_vals else None,
            "baseline_abs_move_pct": round(st.mean(base_abs), 5) if base_abs else None,
        }
        if per_h[h]["mean_abs_move_pct"] and per_h[h]["baseline_abs_move_pct"]:
            per_h[h]["abs_move_lift_pct"] = round(
                100.0 * (per_h[h]["mean_abs_move_pct"] / per_h[h]["baseline_abs_move_pct"] - 1.0), 2)

    null = random_null(pools, counts, mix, args.draws, args.seed) if total else {}

    gate = {}
    for h in HORIZONS:
        real = per_h[h]["mean_signed_return_pct"]
        nmax = (null.get(h) or {}).get("null_MAX_of_means")
        gate[h] = {"real": real, "null_MAX": nmax,
                   "beats_null_MAX": (real is not None and nmax is not None and real > nmax)}

    per_symbol = {}
    for sym, sigs in all_sig.items():
        if not sigs:
            continue
        v = [s[f"fwd_{HEADLINE_HORIZON}"] for s in sigs]
        per_symbol[sym] = {"n": len(v), "mean_signed_return_pct": round(st.mean(v), 5),
                           "hit_rate_pct": round(100.0 * sum(1 for x in v if x > 0) / len(v), 2)}
    pos = sum(1 for r in per_symbol.values() if r["mean_signed_return_pct"] > 0)

    enough = total >= min_n
    beats = gate[HEADLINE_HORIZON]["beats_null_MAX"]
    half = pos >= max(1, (len(per_symbol) + 1) // 2)
    verdict = ("PASS_to_stage_B" if (enough and beats and half)
               else ("INSUFFICIENT_EVIDENCE" if not enough else "FAIL_stop_the_lane"))

    report = {
        "stage": "A_underlying",
        "prereg": PREREG.name,
        "verdict": verdict,
        "_verdict_rule": prereg["decision_rule"],
        "signals_total": total, "min_required": min_n,
        "symbols_tested": len(all_sig), "symbols_with_positive_mean": pos,
        "headline_horizon_bars": HEADLINE_HORIZON,
        "per_horizon": {str(k): v for k, v in per_h.items()},
        "random_entry_null": {str(k): v for k, v in null.items()},
        "null_gate": {str(k): v for k, v in gate.items()},
        "per_symbol_headline": per_symbol,
        "evaluated_bars": evaluated,
        "_disclosures": [
            "Stage A measures the SIGNAL on the UNDERLYING -- no option pricing, no spread, no "
            "theta. A pass here is necessary, not sufficient.",
            "No look-ahead: levels/context at bar i come from bars[:i+1] only; forward returns "
            "are read strictly after i and never enter the decision.",
            "Per-symbol results are DESCRIPTIVE and excluded from the corrected family.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    print(f"\n=== STAGE A VERDICT: {verdict} ===", file=sys.stderr)
    print(f"  signals {total} (need {min_n}) | symbols {len(all_sig)} | "
          f"positive-mean symbols {pos}/{len(per_symbol)}", file=sys.stderr)
    for h in HORIZONS:
        g, p = gate[h], per_h[h]
        print(f"  +{h:>2} bars: signed {p['mean_signed_return_pct']}% hit {p['hit_rate_pct']}% "
              f"absLift {p.get('abs_move_lift_pct')}% | nullMAX {g['null_MAX']} -> "
              f"{'BEATS' if g['beats_null_MAX'] else 'FAILS'}", file=sys.stderr)
    print(f"\nwrote {OUT}", file=sys.stderr)
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())

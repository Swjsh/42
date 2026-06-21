"""L172 RANDOM-NULL test for the premium-selling pivot winner.

THE QUESTION (L172): is a premium-selling cell's edge in the STRUCTURE / strike /
timing SELECTION, or is it generic theta harvest that ANY defined-risk condor placed
on ANY day captures? A 0DTE seller trades every cached day (no signal gate), so the
null here is: shuffle the choices the cell makes (entry time + short-offset) and see
whether the chosen cell beats the distribution of random-choice condors on the SAME
days. If the winner's expectancy sits inside the random-condor distribution, the
"edge" is just generic theta any condor harvests — NOT selection alpha.

Two nulls reported:
  NULL-A (random ENTRY-TIME): same structure/offset/wing/management, but each day's
      entry time drawn uniformly from the grid's entry times. Does the chosen entry
      time matter?
  NULL-B (random SHORT-OFFSET): same structure/entry/wing/management, short-offset
      drawn uniformly from {2,3,4} each day. Does strike selection matter?

A cell BEATS the null only if its OOS per-trade expectancy exceeds the 95th percentile
of the corresponding random distribution (one-sided, edge must be ABOVE the noise).

Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_pivot_premium_selling_null.py \
      --structure IC --entry 10:30 --offset 2 --wing 2 --pt 0.5 --stop 1.5 --iters 300
"""
from __future__ import annotations

import argparse
import datetime as dt
import random
import statistics
import sys
from pathlib import Path

_HERE = Path(__file__).resolve()
_BT = _HERE.parents[1]
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

from lib import simulator_credit as sc  # noqa: E402
import _pivot_premium_selling as piv     # noqa: E402

ENTRY_TIMES = piv.ENTRY_TIMES_ET
OFFSETS = piv.SHORT_OFFSETS
OOS_START = piv.OOS_2026_START

# ── L177 null-gate: knife-edge percentile band + multi-seed sampling floor ──
# A premium-selling cell only BEATS the null if its actual OOS expectancy sits clearly
# ABOVE the random-condor noise. L177's foot-gun: an eligibility-parity bug inflated the
# actual to ~94.8th pctile (a knife-edge that flipped PASS/FAIL on the RNG seed). So the
# gate refuses to call a near-edge result PASS — anything in [P90,P99) is INCONCLUSIVE
# (re-verify eligibility parity + add seeds), PASS needs >=P99 on every seed, and the
# whole verdict needs MIN_ITERS samples on >=MIN_SEEDS seeds or it is INCONCLUSIVE.
NULL_P90 = 0.90
NULL_P99 = 0.99
NULL_MIN_ITERS = 300
NULL_MIN_SEEDS = 2


def percentile_rank(dist: list[float], actual: float) -> float | None:
    """Fraction of the null distribution strictly below `actual` (one-sided)."""
    if not dist:
        return None
    return sum(1 for x in dist if x < actual) / len(dist)


def null_verdict(ranks: list[float], iters: int, n_seeds: int) -> tuple[str, str]:
    """Classify a premium-selling cell against its random-null percentile ranks.

    ranks: one percentile_rank() per seed (actual vs that seed's null distribution).
    Returns (verdict, reason) where verdict in {PASS, FAIL, INCONCLUSIVE}.

    INCONCLUSIVE (never PASS) when: too few iters/seeds, OR any seed lands in the
    [P90,P99) knife-edge (L177 — a parity/seed bug can flip a near-edge result), OR
    seeds straddle the decision band. PASS only when EVERY seed clears P99; FAIL only
    when EVERY seed sits below P90 (genuinely inside the noise).
    """
    if iters < NULL_MIN_ITERS or n_seeds < NULL_MIN_SEEDS or not ranks:
        return ("INCONCLUSIVE",
                f"insufficient sampling: iters={iters} (need>={NULL_MIN_ITERS}) "
                f"seeds={n_seeds} (need>={NULL_MIN_SEEDS}) ranks={len(ranks)}")
    if any(NULL_P90 <= r < NULL_P99 for r in ranks):
        return ("INCONCLUSIVE",
                f"knife-edge: a seed ranks in [{NULL_P90:.0%},{NULL_P99:.0%}) "
                "-- re-verify eligibility parity (L177) and add seeds")
    if all(r >= NULL_P99 for r in ranks):
        return ("PASS", f"actual exceeds p{NULL_P99:.0%} of the null on every seed")
    if all(r < NULL_P90 for r in ranks):
        return ("FAIL", f"actual sits inside the null noise (rank < p{NULL_P90:.0%}) on every seed")
    return ("INCONCLUSIVE", "seed-unstable: ranks straddle the p90/p99 decision band")


def _parse_time(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def _one_day_fill(structure, entry_time, short_offset, wing_width, pt_frac, stop_mult,
                  spy, d, commission):
    spy_day = spy[spy["date"] == d]
    if spy_day.empty:
        return None
    decision_dt, spot, _ = piv._spot_and_decision(spy_day, entry_time)
    if decision_dt is None or spot is None or spot <= 0:
        return None
    legs = piv._build_variant_legs(structure, spot, short_offset, wing_width)
    # L177: identical eligibility gate as production run_variant() — shared helper,
    # NOT a private legs_in_band(half_width=...) literal that can silently diverge.
    if not piv.eligible(legs, spot):
        return None
    binding_wing = wing_width + (1 if structure == "BWIC" else 0)
    f = sc.simulate_credit_trade(d, legs, decision_dt, spot, wing_width=binding_wing,
                                 structure_name=structure, contracts=1, pt_frac=pt_frac,
                                 stop_mult=stop_mult, commission_per_contract=commission)
    if f.skipped:
        return None
    return f.realized_pnl


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--structure", required=True)
    ap.add_argument("--entry", required=True)
    ap.add_argument("--offset", type=int, required=True)
    ap.add_argument("--wing", type=int, required=True)
    ap.add_argument("--pt", type=float, required=True)
    ap.add_argument("--stop", default="1.5")
    ap.add_argument("--iters", type=int, default=300)
    ap.add_argument("--commission", type=float, default=0.65)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--seeds", type=int, default=NULL_MIN_SEEDS,
                    help="number of RNG seeds (>=2 required for a PASS verdict, L177)")
    args = ap.parse_args()

    stop_mult = None if args.stop.lower() in ("none", "eod") else float(args.stop)
    entry_time = _parse_time(args.entry)

    spy = piv._load_spy_master()
    cache_dates = piv._option_cache_dates()
    day_list = sorted(cache_dates & set(spy["date"].unique()))
    oos_days = [d for d in day_list if d >= OOS_START]

    # Actual cell OOS expectancy (recompute to be self-contained).
    actual = [p for d in oos_days
              if (p := _one_day_fill(args.structure, entry_time, args.offset, args.wing,
                                     args.pt, stop_mult, spy, d, args.commission)) is not None]
    actual_exp = statistics.mean(actual) if actual else 0.0
    print(f"[null] ACTUAL cell {args.structure} {args.entry} off{args.offset} w{args.wing} "
          f"pt{args.pt} stop{args.stop}: OOS n={len(actual)} exp=${actual_exp:.2f}")

    def _null_dist(rng, draw):
        """One null distribution: `draw(rng, d)` returns this iter's per-day pnl-or-None."""
        exps = []
        for _ in range(args.iters):
            pnls = [p for d in oos_days if (p := draw(rng, d)) is not None]
            if pnls:
                exps.append(statistics.mean(pnls))
        return exps

    def _draw_entry(rng, d):
        return _one_day_fill(args.structure, rng.choice(ENTRY_TIMES), args.offset, args.wing,
                             args.pt, stop_mult, spy, d, args.commission)

    def _draw_offset(rng, d):
        return _one_day_fill(args.structure, entry_time, rng.choice(OFFSETS), args.wing,
                             args.pt, stop_mult, spy, d, args.commission)

    seeds = [args.seed + i for i in range(max(1, args.seeds))]
    for name, draw in (("NULL-A(random-entry-time)", _draw_entry),
                       ("NULL-B(random-short-offset)", _draw_offset)):
        ranks = []
        for s in seeds:
            dist = _null_dist(random.Random(s), draw)
            r = percentile_rank(dist, actual_exp)
            if r is None:
                print(f"[null] {name} seed={s}: no data")
                continue
            ranks.append(r)
            print(f"[null] {name} seed={s}: n={len(dist)} mean=${statistics.mean(dist):.2f} "
                  f"| actual=${actual_exp:.2f} pctile={r:.2%}")
        verdict, reason = null_verdict(ranks, args.iters, len(seeds))
        print(f"[null] {name} VERDICT={verdict} ({reason})")


if __name__ == "__main__":
    main()

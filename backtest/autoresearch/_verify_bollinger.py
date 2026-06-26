"""Adversarial verification of the bollinger_squeeze 13/13-P4 result (anti-pattern 2.4/2.10).

13/13 P3->P4 with drop-top5 beating the null MAX is "too good" -> verify before any claim.
Three independent checks on the headline cell (ATM/-8, tp0.3/sell66/trail0.15):

  1. SIDE SPLIT: calls vs puts P&L (IS+OOS). A pure 2025-26 bull-drift artifact would make
     money on CALLS only; a genuine breakout edge is TWO-SIDED (puts profit on down-breaks).
  2. DIRECTION-CONTROLLED NULL: random RTH bars, but side = the entry bar's OWN direction
     (call if up-bar, put if down-bar) -> a momentum-AWARE random entry. If bollinger still
     beats THIS, the squeeze pre-condition adds selection value beyond "follow the last bar".
     If it does NOT, the "edge" is just direction-vs-random-direction (the stock null's gap).
  3. STRICT null: drop-top5 vs the direction-controlled null MAX (not mean).

Pure Python, $0, read-only. Run:
  backtest/.venv/Scripts/python.exe -m autoresearch._verify_bollinger
"""
from __future__ import annotations

import datetime as dt
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

_REPO = Path(__file__).resolve().parent.parent
_ROOT = _REPO.parent
for _p in (str(_REPO), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch import runner as ar, family_detectors as fdet, family_grind as fg  # noqa: E402
from autoresearch.null_baseline import _eligible_indices, _swing_invalidation  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

# Defaults = bollinger ATM/-8 headline cell; override via argv:
#   _verify_bollinger.py [family so stop tp1 tq trail]
FAMILY = sys.argv[1] if len(sys.argv) > 1 else "bollinger_squeeze"
SO = int(sys.argv[2]) if len(sys.argv) > 2 else 0
STOP = float(sys.argv[3]) if len(sys.argv) > 3 else -0.08
TP1 = float(sys.argv[4]) if len(sys.argv) > 4 else 0.30
TQ = float(sys.argv[5]) if len(sys.argv) > 5 else 0.667
TRAIL = (None if (len(sys.argv) > 6 and sys.argv[6] in ("None", "none", "0"))
         else (float(sys.argv[6]) if len(sys.argv) > 6 else 0.15))
SEEDS = 20


def _yr_side(fills):
    by = defaultdict(lambda: [0.0, 0])
    for f in fills:
        d = fg._tdate(f)
        yr = "IS25" if d.year == 2025 else "OOS26"
        by[(yr, f.side)][0] += float(f.dollar_pnl); by[(yr, f.side)][1] += 1
    return by


def main() -> int:
    spy, vix = ar.load_data(fg.START, fg.END)
    rth = fdet.build_rth(spy)
    sigs = fdet.FAMILIES[FAMILY](rth)
    fills, m = fg.sim_cell(rth, sigs, SO, STOP, TP1, TQ, TRAIL)
    print(f"{FAMILY} so={SO} stop={STOP} tp{TP1}/sell{int(TQ*100)}/{TRAIL} cell: "
          f"n={m['n']} exp=${m['exp']} oos_exp=${m['oos_exp']} qpf={m['qpf']} "
          f"top5={m['top5_day_pct']}% maxDD=${m['max_dd']}")

    # 1. SIDE SPLIT
    calls = [float(f.dollar_pnl) for f in fills if f.side == "C"]
    puts = [float(f.dollar_pnl) for f in fills if f.side == "P"]
    print("\n[1] SIDE SPLIT (two-sided edge vs bull-drift artifact):")
    print(f"  CALLS n={len(calls)} total=${sum(calls):.0f} exp=${np.mean(calls):.1f} "
          f"wr={100*sum(1 for x in calls if x>0)/max(1,len(calls)):.0f}%")
    print(f"  PUTS  n={len(puts)} total=${sum(puts):.0f} exp=${np.mean(puts):.1f} "
          f"wr={100*sum(1 for x in puts if x>0)/max(1,len(puts)):.0f}%")
    by = _yr_side(fills)
    for k in sorted(by):
        print(f"    {k[0]} {k[1]}: total=${by[k][0]:.0f} n={by[k][1]}")

    # 2 + 3. DIRECTION-CONTROLLED NULL: random bars, side = that bar's own direction
    o = rth["open"].to_numpy(); c = rth["close"].to_numpy()
    elig = _eligible_indices(rth, fdet.FAMILY_WINDOW["bollinger_squeeze"])
    elig = [int(i) for i in elig]
    n_draw = min(len(fills), len(elig))
    per_seed = []
    for seed in range(SEEDS):
        rng = random.Random(1000 + seed)
        picks = rng.sample(elig, n_draw)
        pnl, nn = 0.0, 0
        for idx in picks:
            side = "C" if c[idx] >= o[idx] else "P"     # momentum-aware: follow THIS bar
            rej = _swing_invalidation(rth, idx, side, 12)
            f = simulate_trade_real(
                entry_bar_idx=idx, entry_bar=rth.iloc[idx], spy_df=rth, ribbon_df=None,
                rejection_level=round(float(rej), 2), triggers_fired=["dir_null"], side=side,
                qty=fg.QTY, setup="DIR_NULL", premium_stop_pct=STOP, strike_offset=SO,
                **fg._exit_kwargs(TP1, TQ, TRAIL))
            if f is None:
                continue
            pnl += float(f.dollar_pnl); nn += 1
        per_seed.append(pnl / nn if nn else 0.0)
    dmean, dmax = float(np.mean(per_seed)), float(max(per_seed))
    # drop-top5 of the signal
    by_day = defaultdict(float)
    for f in fills:
        by_day[fg._tdate(f)] += float(f.dollar_pnl)
    top5 = {d for d, _ in sorted(by_day.items(), key=lambda kv: kv[1], reverse=True)[:5]}
    kept = [f for f in fills if fg._tdate(f) not in top5]
    drop5 = sum(float(f.dollar_pnl) for f in kept) / len(kept)

    print(f"\n[2] DIRECTION-CONTROLLED NULL (momentum-aware random entry, {SEEDS} seeds):")
    print(f"  signal exp=${m['exp']}  drop_top5=${drop5:.1f}")
    print(f"  dir-null mean=${dmean:.1f}  max=${dmax:.1f}")
    print(f"  signal beats dir-null MAX:        {m['exp'] > dmax}  (edge ${m['exp']-dmax:.1f})")
    print(f"  drop_top5 beats dir-null MEAN:    {drop5 > dmean}  (edge ${drop5-dmean:.1f})")
    print(f"  drop_top5 beats dir-null MAX:     {drop5 > dmax}  (STRICT)")
    print("\nVERDICT: " + (
        "SELECTION EDGE SURVIVES the momentum-aware null -> squeeze adds value beyond direction."
        if (drop5 > dmean and m["exp"] > dmax) else
        "ARTIFACT: edge collapses vs a momentum-aware random entry -> 'breakout direction', "
        "not squeeze-selection. The stock (random-side) null overstated it."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

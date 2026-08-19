"""What IS the trigger detecting — VOLATILITY or DIRECTION?

After the expiry experiment (moot) and the timeframe variant (refuted, and backwards), the
leading hypothesis is that the level-interaction trigger marks "something is about to move"
without predicting WHICH WAY. That would explain everything observed: a ~50/50 direction split
with both sides losing on both timeframes, because every DIRECTIONAL expression of a
direction-blind signal must pay the spread and theta for nothing.

This test settles it with underlying bars alone -- no options, no fills, no modeling
assumptions. For each signal, measure the underlying's forward move over 1/3/5 sessions and
compare against the unconditional baseline of all sessions:

  * |forward move|  elevated vs baseline  -> the trigger DOES carry information about MAGNITUDE
  * signed move (in the signal's own direction) at baseline -> it carries NONE about DIRECTION

Both true together = a volatility detector wearing a directional costume, which is a
fundamentally different (and still potentially valuable) instrument than the one we built.

Significance by Mann-Whitney U (distribution-free; forward returns are fat-tailed and a t-test
would overstate confidence).
"""

from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

from scipy import stats as sps

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from weekly.lib import bars as wbars  # noqa: E402

ET = ZoneInfo("America/New_York")
OUT = REPO / "analysis" / "weekly-lane" / "signal-character-test.json"
HORIZONS = (1, 3, 5)


def forward_returns(closes: list[float], i: int, n: int) -> float | None:
    if i + n >= len(closes):
        return None
    return 100.0 * (closes[i + n] / closes[i] - 1.0)


def test_symbol(symbol: str, signals: list[dict], daily_limit: int) -> dict:
    df = wbars.fetch_daily(symbol, limit=daily_limit, min_bars=60)
    dates = [ts.date().isoformat() for ts in df.index]
    closes = [float(c) for c in df["close"]]
    idx_of = {d: i for i, d in enumerate(dates)}

    sig_by_session = {}
    for s in signals:
        sig_by_session.setdefault(s["session"], s["direction"])

    out: dict = {"symbol": symbol, "n_sessions": len(dates), "horizons": {}}
    for n in HORIZONS:
        base_abs, base_signed = [], []
        sig_abs, sig_signed = [], []
        for i, d in enumerate(dates):
            fr = forward_returns(closes, i, n)
            if fr is None:
                continue
            base_abs.append(abs(fr))
            base_signed.append(fr)
            direction = sig_by_session.get(d)
            if direction is not None:
                sig_abs.append(abs(fr))
                # Signed IN THE SIGNAL'S OWN DIRECTION: + means the trigger was right.
                sig_signed.append(fr if direction == "bullish" else -fr)
        if len(sig_abs) < 10:
            out["horizons"][f"{n}d"] = {"n_signals": len(sig_abs), "note": "too few"}
            continue
        _, p_abs = sps.mannwhitneyu(sig_abs, base_abs, alternative="greater")
        _, p_dir = sps.mannwhitneyu(sig_signed, base_signed, alternative="greater")
        out["horizons"][f"{n}d"] = {
            "n_signals": len(sig_abs),
            "n_baseline": len(base_abs),
            "abs_move_signal": round(st.mean(sig_abs), 3),
            "abs_move_baseline": round(st.mean(base_abs), 3),
            "abs_move_lift_pct": round(100.0 * (st.mean(sig_abs) / st.mean(base_abs) - 1.0), 1),
            "p_abs_greater": round(float(p_abs), 4),
            "signed_move_signal": round(st.mean(sig_signed), 3),
            "signed_move_baseline": round(st.mean(base_signed), 3),
            "p_signed_greater": round(float(p_dir), 4),
            "direction_hit_rate_pct": round(
                100.0 * sum(1 for x in sig_signed if x > 0) / len(sig_signed), 1),
        }
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--signals", required=True)
    ap.add_argument("--daily-limit", type=int, default=900)
    args = ap.parse_args(argv)

    doc = json.loads(Path(args.signals).read_text(encoding="utf-8"))
    results = [test_symbol(p["symbol"], p["signals"], args.daily_limit)
               for p in doc["per_symbol"] if p.get("signals")]
    if not results:
        print("ERROR: no symbol had signals to test.", file=sys.stderr)
        return 1

    # Pooled verdict across symbols, per horizon.
    pooled = {}
    for n in HORIZONS:
        k = f"{n}d"
        rows = [r["horizons"][k] for r in results if "abs_move_lift_pct" in r["horizons"].get(k, {})]
        if not rows:
            continue
        pooled[k] = {
            "symbols": len(rows),
            "mean_abs_lift_pct": round(st.mean([r["abs_move_lift_pct"] for r in rows]), 1),
            "symbols_with_abs_p_lt_05": sum(1 for r in rows if r["p_abs_greater"] < 0.05),
            "symbols_with_signed_p_lt_05": sum(1 for r in rows if r["p_signed_greater"] < 0.05),
            "mean_direction_hit_rate_pct": round(
                st.mean([r["direction_hit_rate_pct"] for r in rows]), 1),
        }

    payload = {
        "test": "signal_character_volatility_vs_direction",
        "signals_source": args.signals,
        "_reading": (
            "abs-move lift with p<0.05 = the trigger carries MAGNITUDE information. "
            "signed-move at baseline with direction hit rate ~50% = it carries NO DIRECTION "
            "information. Both together = a volatility detector, and every directional "
            "expression of it must lose the spread and theta."
        ),
        "pooled_by_horizon": pooled,
        "per_symbol": results,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    print(f"{'horizon':>8} {'syms':>5} {'absLift%':>9} {'absSig':>7} {'dirSig':>7} {'hit%':>6}")
    for k, v in pooled.items():
        print(f"{k:>8} {v['symbols']:>5} {v['mean_abs_lift_pct']:>9.1f} "
              f"{v['symbols_with_abs_p_lt_05']:>7} {v['symbols_with_signed_p_lt_05']:>7} "
              f"{v['mean_direction_hit_rate_pct']:>6.1f}")
    print(f"\nwrote {OUT}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""RANGE-SCALP slice 2: the regime-gate concentration test.

The decisive bounded question (conductor 2026-06-28, the named next slice of
RANGE-SCALP-REGIME-GATE-SLICE):

    The ungated Tier-2 LEVEL_REJECT probe was VEIN_CONCENTRATED — net +$373.80
    over 30 trades / 9 active days, but top-3 days = 224% of net and THREE losing
    days (-$618 combined: 2026-05-26 -196.2, 2026-06-04 -157.2, 2026-06-24 -264.6)
    are the concentration killer.

    Does an EXPLICIT regime gate — flat ribbon (spread < 30c, the doctrine's own
    RIBBON_SPREAD_MIN_CENTS trend threshold, so "below trend" == "range") AND
    VIX in [14, 20] (compressed-vol range regime) — applied per-trade and CAUSALLY
    (ribbon EMA value at the entry bar; VIX as-of the entry timestamp, L40/L44/C5/C6)
    FILTER OUT those 3 losing days while keeping the winners?

If YES (losers killed, gated expectancy still positive, concentration improved):
    -> the regime gate is the real edge boundary; promote to a candidate for the
       IS/OOS multi-combo slice.
If NO (losers survive, or expectancy goes negative, or too few survive):
    -> Tier-2 level-fade is concentration-dry even when regime-gated; record it and
       climb the search-space ladder.

This REUSES the existing real-OPRA-fills machinery (run_shotgun_day + the
range_scalp_probe loaders/combo) — it does NOT rebuild a simulator (L17/L36). The
original range_scalp_probe stays byte-identical (no regression risk).

Yardstick = per-trade expectancy + concentration-robust day metrics (NOT J
edge_capture — that directional-anchor metric structurally auto-rejects range
strategies; see _lesson-inbox/2026-06-28-directional-anchor-edgecapture...).

Slippage: the ungated probe applied none. This slice reports the gated set GROSS
and NET of a round-trip half-spread haircut (entry buy at ask, exit sell at bid)
at 0.02 and 0.05 / contract for honesty — a $12/trade gross edge that dies under
realistic slippage is not deployable.

Rail-4 CLEAR: a research probe + results JSON. Touches NO params/doctrine/orders/
heartbeat/filters/CLAUDE; places NO order; arms NOTHING.

Run:
    backtest/.venv/Scripts/python.exe -m autoresearch.range_scalp_regime_gated_probe --smoke
    backtest/.venv/Scripts/python.exe -m autoresearch.range_scalp_regime_gated_probe
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from autoresearch.shotgun_scalper_grinder import run_shotgun_day
from autoresearch.range_scalp_probe import (
    RANGE_SCALP_COMBO,
    TIER_LEVEL_REJECT,
    WINDOW_START,
    WINDOW_END,
    _load_spy,
    _trading_days,
)
from backtest.lib.ribbon import compute_ribbon, ribbon_at

# --- regime gate thresholds (doctrine-anchored, not hand-tuned) ---------------
# Flat ribbon == NOT trending. RIBBON_SPREAD_MIN_CENTS (filters.py) = 30 is the
# MINIMUM spread the engine requires to take a TREND entry, so spread < 30c is the
# engine's own definition of "not a trend" == range. We use it directly.
FLAT_SPREAD_MAX_CENTS = 30.0
VIX_RANGE_LOW = 14.0
VIX_RANGE_HIGH = 20.0

# The 3 losing days the gate must kill to defeat the concentration finding.
KNOWN_LOSING_DAYS = {"2026-05-26", "2026-06-04", "2026-06-24"}

# Round-trip slippage sensitivity (half-spread $/contract; charged on entry+exit).
SLIPPAGE_HALF_SPREADS = (0.02, 0.05)

VIX_CSV = _REPO / "backtest" / "data" / "vix_5m_2026-05-19_2026-06-26.csv"
OUT_PATH = _REPO / "analysis" / "recommendations" / "range-scalp-regime-gated-2026-06-28.json"


def _load_vix():
    import pandas as pd

    vix = pd.read_csv(VIX_CSV)
    vix["timestamp_et"] = (
        pd.to_datetime(vix["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    vix = vix.sort_values("timestamp_et").reset_index(drop=True)
    return vix


def _vix_asof(vix, ts) -> float | None:
    """VIX close as-of (last bar <= ts) — causal, no look-ahead (L40/L44/C6)."""
    import pandas as pd

    prior = vix[vix["timestamp_et"] <= ts]
    if prior.empty:
        return None
    return float(prior.iloc[-1]["close"])


def _ribbon_spread_at(spy, entry_ts) -> float | None:
    """Causal ribbon spread (cents) at the entry bar.

    EMA[i] depends only on closes[0..i], so computing over all bars up to+including
    the entry bar and reading the value at that bar is causal (no look-ahead).
    """
    upto = spy[spy["timestamp_et"] <= entry_ts]
    if len(upto) < 5:
        return None
    rib = compute_ribbon(upto["close"].reset_index(drop=True))
    state = ribbon_at(rib, len(rib) - 1)
    if state is None:
        return None
    return float(state.spread_cents)


def _summ(pnls: list[float]) -> dict:
    n = len(pnls)
    if not n:
        return {"n_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
                "expectancy_per_trade_usd": 0.0, "total_pnl_usd": 0.0,
                "median_trade_usd": 0.0, "worst_trade_usd": 0.0, "best_trade_usd": 0.0}
    wins = sum(1 for p in pnls if p > 0)
    total = round(sum(pnls), 2)
    return {
        "n_trades": n,
        "wins": wins,
        "losses": n - wins,
        "win_rate": round(wins / n, 3),
        "expectancy_per_trade_usd": round(total / n, 2),
        "total_pnl_usd": total,
        "median_trade_usd": round(statistics.median(pnls), 2),
        "worst_trade_usd": round(min(pnls), 2),
        "best_trade_usd": round(max(pnls), 2),
    }


def _concentration(by_day: dict[str, float]) -> dict:
    nz = {k: v for k, v in by_day.items() if v != 0.0}
    total = round(sum(nz.values()), 2)
    vals = sorted(nz.values(), reverse=True)
    top3_pct = round(100.0 * sum(vals[:3]) / total, 1) if total else None
    # trimmed (drop best + worst day) — concentration-robust day expectancy
    trimmed = vals[1:-1] if len(vals) > 2 else vals
    return {
        "n_active_days": len(nz),
        "n_losing_days": sum(1 for v in nz.values() if v < 0),
        "total_pnl_usd": total,
        "top3_day_pct_of_net": top3_pct,
        "median_day_usd": round(statistics.median(nz.values()), 2) if nz else 0.0,
        "trimmed_day_mean_usd": round(statistics.mean(trimmed), 2) if trimmed else 0.0,
        "trimmed_day_total_usd": round(sum(trimmed), 2) if trimmed else 0.0,
        "by_day_pnl": by_day,
    }


def run_gated_probe(start: dt.date, end: dt.date) -> dict:
    spy = _load_spy(start - dt.timedelta(days=5), end)
    vix = _load_vix()
    days = _trading_days(spy, start, end)

    opra_cache: dict = {}
    all_rows = []
    for d in days:
        for t in run_shotgun_day(d, spy, RANGE_SCALP_COMBO, opra_cache, tier_filter=TIER_LEVEL_REJECT):
            spread = _ribbon_spread_at(spy, t.entry_time_et)
            vixv = _vix_asof(vix, t.entry_time_et)
            flat_ok = spread is not None and spread < FLAT_SPREAD_MAX_CENTS
            vix_ok = vixv is not None and VIX_RANGE_LOW <= vixv <= VIX_RANGE_HIGH
            all_rows.append({
                "date": d.isoformat(),
                "entry_time_et": t.entry_time_et.isoformat(),
                "dollar_pnl": t.dollar_pnl,
                "qty": t.qty,
                "spread_cents": round(spread, 1) if spread is not None else None,
                "vix": round(vixv, 2) if vixv is not None else None,
                "flat_ok": flat_ok,
                "vix_ok": vix_ok,
                "kept": flat_ok and vix_ok,
            })

    def _by_day(rows):
        bd = {d.isoformat(): 0.0 for d in days}
        for r in rows:
            bd[r["date"]] = round(bd[r["date"]] + r["dollar_pnl"], 2)
        return bd

    ungated = all_rows
    gated = [r for r in all_rows if r["kept"]]
    ung_pnls = [r["dollar_pnl"] for r in ungated]
    gat_pnls = [r["dollar_pnl"] for r in gated]

    # slippage sensitivity on the GATED set
    slippage = {}
    for hs in SLIPPAGE_HALF_SPREADS:
        net = [r["dollar_pnl"] - 2.0 * hs * 100.0 * r["qty"] for r in gated]
        slippage[f"half_spread_{hs}"] = _summ([round(x, 2) for x in net])

    # did the gate kill the 3 losing days?
    losing_day_audit = {}
    for ld in sorted(KNOWN_LOSING_DAYS):
        before = [r for r in ungated if r["date"] == ld]
        after = [r for r in gated if r["date"] == ld]
        losing_day_audit[ld] = {
            "trades_before_gate": len(before),
            "pnl_before_gate": round(sum(r["dollar_pnl"] for r in before), 2),
            "trades_after_gate": len(after),
            "pnl_after_gate": round(sum(r["dollar_pnl"] for r in after), 2),
            "fully_filtered": len(after) == 0,
        }
    all_losers_killed = all(a["fully_filtered"] for a in losing_day_audit.values())

    gat_summ = _summ(gat_pnls)
    gat_conc = _concentration(_by_day(gated))

    # verdict
    if gat_summ["n_trades"] < 10:
        verdict = "REGIME_GATE_TOO_TIGHT"
    elif gat_summ["expectancy_per_trade_usd"] <= 0:
        verdict = "REGIME_GATE_INEFFECTIVE"
    elif not all_losers_killed:
        verdict = "REGIME_GATE_PARTIAL"
    elif slippage["half_spread_0.05"]["expectancy_per_trade_usd"] <= 0:
        verdict = "REGIME_GATE_DIES_ON_SLIPPAGE"
    else:
        verdict = "REGIME_GATE_PROMOTABLE"

    return {
        "probe": "range_scalp_tier2_regime_gated",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "verdict": verdict,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "gate": {
            "flat_ribbon_spread_max_cents": FLAT_SPREAD_MAX_CENTS,
            "vix_low": VIX_RANGE_LOW,
            "vix_high": VIX_RANGE_HIGH,
            "rationale": "spread<30c == below RIBBON_SPREAD_MIN_CENTS (engine trend "
                         "threshold) == range; VIX 14-20 == compressed-vol range regime",
        },
        "all_losers_killed": all_losers_killed,
        "losing_day_audit": losing_day_audit,
        "ungated": {**_summ(ung_pnls), **_concentration(_by_day(ungated))},
        "gated_gross": {**gat_summ, **gat_conc},
        "gated_net_of_slippage": slippage,
        "trades": all_rows,
        "method_disclosures": {
            "reuse": "run_shotgun_day(tier_filter=2) + range_scalp_probe loaders/combo; "
                     "original probe untouched (byte-identical, no regression risk)",
            "causality": "ribbon spread = EMA value at entry bar over bars<=entry (EMA[i] "
                         "depends only on closes[0..i]); VIX = as-of last bar<=entry. No look-ahead.",
            "fill_model": "Real OPRA bars via _simulate_trade_real (NO Black-Scholes).",
            "slippage": "round-trip half-spread haircut (2 * half_spread * 100 * qty) on the "
                        "gated set at 0.02 and 0.05 /contract.",
            "yardstick": "per-trade expectancy + concentration-robust day metrics (median-day, "
                         "trimmed-day-mean). J edge_capture NOT used (auto-rejects range edges).",
            "limitations": "ONE combo, no tp/stop/strike sweep, no IS/OOS. A PROMOTABLE verdict "
                           "justifies the regime-gated multi-combo + IS/OOS slice next.",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="first day only, print gate stats")
    args = ap.parse_args()

    if args.smoke:
        spy = _load_spy(WINDOW_START - dt.timedelta(days=5), WINDOW_END)
        vix = _load_vix()
        days = _trading_days(spy, WINDOW_START, WINDOW_END)
        d = days[0]
        opra_cache: dict = {}
        n_kept = 0
        trades = run_shotgun_day(d, spy, RANGE_SCALP_COMBO, opra_cache, tier_filter=TIER_LEVEL_REJECT)
        for t in trades:
            spread = _ribbon_spread_at(spy, t.entry_time_et)
            vixv = _vix_asof(vix, t.entry_time_et)
            kept = (spread is not None and spread < FLAT_SPREAD_MAX_CENTS
                    and vixv is not None and VIX_RANGE_LOW <= vixv <= VIX_RANGE_HIGH)
            n_kept += int(kept)
            print(f"SMOKE {d} {t.entry_time_et.time()}: spread={spread} vix={vixv} "
                  f"pnl={t.dollar_pnl} kept={kept}")
        print(f"SMOKE {d}: {len(trades)} trades, {n_kept} kept after gate")
        return 0

    result = run_gated_probe(WINDOW_START, WINDOW_END)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    g = result["gated_gross"]
    n05 = result["gated_net_of_slippage"]["half_spread_0.05"]
    print(f"VERDICT={result['verdict']} losers_killed={result['all_losers_killed']}")
    print(f"  UNGATED: n={result['ungated']['n_trades']} exp=${result['ungated']['expectancy_per_trade_usd']} "
          f"total=${result['ungated']['total_pnl_usd']} top3%={result['ungated']['top3_day_pct_of_net']}")
    print(f"  GATED  : n={g['n_trades']} wr={g['win_rate']} exp=${g['expectancy_per_trade_usd']} "
          f"total=${g['total_pnl_usd']} top3%={g['top3_day_pct_of_net']} losing_days={g['n_losing_days']}")
    print(f"  GATED net@0.05: exp=${n05['expectancy_per_trade_usd']} total=${n05['total_pnl_usd']}")
    print(f"written: {OUT_PATH.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

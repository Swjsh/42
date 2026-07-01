"""RANGE-SCALP slice 3 PART-1: WIDEN THE DATA WINDOW (the unblocked slice).

The frame-audit that made this possible (conductor 2026-07-01):
    Slices 1+2 concluded the regime-gated Tier-2 level-fade edge is REAL but
    n=8-INCONCLUSIVE on the recent 25-day window, and named the ONLY remaining
    lever "WIDEN THE DATA WINDOW ... so the spread<30 edge's n=8 reaches >=15-20
    for an IS/OOS split" -- then declared it DATA-BLOCKED.

    That blocker was FALSE. Both range_scalp probes pin a 25-day RECENT_SPY_CSV /
    VIX_CSV on a STALE comment ("the grinder's _runner.load_data master only covers
    through ~2026-05-22"). Verified 2026-07-01: the master SPY 5m + VIX 5m cover
    2025-01-01..2026-06-18 (533 days) and the OPRA real-fills cache holds 370 0DTE
    days (2025-01-02..2026-06-26, 8505 contract files). The data to widen the window
    ALREADY EXISTS -- the probe just hardcoded a 25-day recent CSV.

The decisive bounded question:
    Run the SAME regime-gated Tier-2 LEVEL_REJECT_LIVE fade (flat ribbon spread<30c
    AND VIX 14-20, applied per-trade + CAUSALLY) over the FULL 2025-01..2026-06-18
    history. The regime gate self-selects range-regime days, so the gated sample
    grows far past n=8 -- enough for an IS(2025) / OOS(2026) split. Does the edge:
      (a) reach statistical significance (n >= 10, ideally >= 20 per split)?
      (b) hold positive gated expectancy IN-SAMPLE **and** OUT-OF-SAMPLE?
      (c) survive realistic slippage (breakeven half-spread >= 0.05)?
      (d) de-concentrate (top-3 days no longer dominate net)?
    Only if all four hold is the range-scalp thread genuinely reopened as a
    promotable candidate; otherwise the widened data gives the HONEST verdict the
    25-day window could not.

REUSE, don't rebuild (L17/L36): run_shotgun_day + RANGE_SCALP_COMBO + TIER_LEVEL_REJECT
from range_scalp_probe; the gate constants from range_scalp_regime_gated_probe;
probe_stats for significance/concentration/slippage. Both original probes stay
byte-identical (no regression risk).

Causality (L40/L44/C6): ribbon spread = EMA value AT the entry bar (EMA[i] depends
only on closes[0..i], so a single full-frame compute + positional index is IDENTICAL
to the per-trade slice the gated probe used, just O(N) not O(N^2)); VIX = last bar
<= entry via searchsorted. No look-ahead.

Rail-4 CLEAR: a research probe + results JSON. Touches NO params/doctrine/orders/
heartbeat/filters/CLAUDE; places NO order; arms NOTHING.

Run:
    backtest/.venv/Scripts/python.exe -m autoresearch.range_scalp_widewindow_probe --smoke
    backtest/.venv/Scripts/python.exe -m autoresearch.range_scalp_widewindow_probe
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from autoresearch.shotgun_scalper_grinder import run_shotgun_day
from autoresearch.range_scalp_probe import RANGE_SCALP_COMBO, TIER_LEVEL_REJECT
from autoresearch.range_scalp_regime_gated_probe import (
    FLAT_SPREAD_MAX_CENTS,
    VIX_RANGE_LOW,
    VIX_RANGE_HIGH,
)
from autoresearch import probe_stats as ps
from backtest.lib.ribbon import compute_ribbon

# --- full-history data (verified present 2026-07-01) --------------------------
# Master SPY 5m + VIX 5m cover 2025-01-01..2026-06-18; OPRA real-fills cover to 06-26.
# We run to the SPY master last day (06-18) since a trade needs the 5m bar to exist.
FULL_SPY_CSV = _REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-06-18.csv"
FULL_VIX_CSV = _REPO / "backtest" / "data" / "vix_5m_2025-01-01_2026-06-18.csv"

WINDOW_START = dt.date(2025, 1, 2)   # first OPRA 0DTE day
WINDOW_END = dt.date(2026, 6, 18)    # SPY master last day
# IS/OOS boundary: train on 2025, test on 2026 (a clean temporal walk-forward split).
OOS_START = dt.date(2026, 1, 1)

OUT_PATH = _REPO / "analysis" / "recommendations" / "range-scalp-widewindow-2026-07-01.json"


def classify_wide_verdict(
    *,
    pooled_sufficient: bool,
    pooled_expectancy: float,
    both_splits_sufficient: bool,
    both_splits_positive: bool,
    slippage_survives_realistic: bool,
    concentrated: bool,
) -> str:
    """Pure full-history verdict ladder (extracted for bite-testing).

    The order encodes the disqualification precedence:
      1. not enough trades even pooled          -> STILL_INCONCLUSIVE_AFTER_WIDENING
      2. pooled expectancy <= 0                 -> DRY_ON_FULL_HISTORY
      3. a split is too thin to walk-forward    -> POOLED_POSITIVE_SPLIT_TOO_THIN
      4. IS/OOS disagree in sign                -> FAILS_WALK_FORWARD_SIGN_FLIP
      5. gross edge dies under realistic slippage-> DIES_ON_SLIPPAGE
      6. positive+robust but day-concentrated   -> POSITIVE_BUT_CONCENTRATED
      7. all clear                              -> PROMOTABLE_ON_WIDE_HISTORY
    """
    if not pooled_sufficient:
        return "STILL_INCONCLUSIVE_AFTER_WIDENING"
    if pooled_expectancy <= 0:
        return "DRY_ON_FULL_HISTORY"
    if not both_splits_sufficient:
        return "POOLED_POSITIVE_SPLIT_TOO_THIN"
    if not both_splits_positive:
        return "FAILS_WALK_FORWARD_SIGN_FLIP"
    if not slippage_survives_realistic:
        return "DIES_ON_SLIPPAGE"
    if concentrated:
        return "POSITIVE_BUT_CONCENTRATED"
    return "PROMOTABLE_ON_WIDE_HISTORY"


def _load_frame(csv_path: Path):
    import pandas as pd

    df = pd.read_csv(csv_path)
    df["timestamp_et"] = (
        pd.to_datetime(df["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    return df.sort_values("timestamp_et").reset_index(drop=True)


def _build_spread_lookup(spy) -> dict:
    """Full-frame causal ribbon spread, keyed by entry timestamp.

    compute_ribbon over the whole close series produces spread_cents[i] using only
    closes[0..i] (causal EMA), positionally aligned to spy's reset index -> a single
    O(N) pass replaces the gated probe's O(N^2) per-trade re-slice with the SAME
    causal value at each bar.
    """
    rib = compute_ribbon(spy["close"].reset_index(drop=True))
    out: dict = {}
    for ts, spread in zip(spy["timestamp_et"], rib["spread_cents"]):
        out[ts] = float(spread)
    return out


def _vix_asof_lookup(vix):
    """Return (sorted_ts_list, closes_list) for a searchsorted as-of lookup."""
    ts = list(vix["timestamp_et"])
    closes = list(vix["close"].astype(float))
    return ts, closes


def _vix_asof(ts_sorted, closes, ts) -> float | None:
    import bisect

    i = bisect.bisect_right(ts_sorted, ts) - 1
    if i < 0:
        return None
    return float(closes[i])


def _trading_days(spy, start: dt.date, end: dt.date) -> list[dt.date]:
    days = sorted(set(spy["timestamp_et"].dt.date.unique()))
    return [d for d in days if start <= d <= end]


def run_wide_probe(start: dt.date, end: dt.date) -> dict:
    spy = _load_frame(FULL_SPY_CSV)
    vix = _load_frame(FULL_VIX_CSV)
    spread_by_ts = _build_spread_lookup(spy)
    vts, vcl = _vix_asof_lookup(vix)
    days = _trading_days(spy, start, end)

    opra_cache: dict = {}
    all_rows = []
    for d in days:
        for t in run_shotgun_day(d, spy, RANGE_SCALP_COMBO, opra_cache, tier_filter=TIER_LEVEL_REJECT):
            spread = spread_by_ts.get(t.entry_time_et)
            vixv = _vix_asof(vts, vcl, t.entry_time_et)
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
        bd: dict = {d.isoformat(): 0.0 for d in days}
        for r in rows:
            bd[r["date"]] = round(bd[r["date"]] + r["dollar_pnl"], 2)
        return bd

    def _block(rows: list) -> dict:
        pnls = [r["dollar_pnl"] for r in rows]
        summ = ps.summarize_trades(pnls)
        conc = ps.day_concentration(_by_day(rows))
        sig = ps.significance(len(rows))
        cflag = ps.concentration_flag(conc["top3_day_pct_of_net"])
        slip = ps.slippage_sweep(rows)
        base = ps.base_verdict(len(rows), summ["expectancy_per_trade_usd"], conc["top3_day_pct_of_net"])
        return {
            "summary": summ,
            "concentration": {k: v for k, v in conc.items() if k != "by_day_pnl"},
            "significance": sig,
            "concentration_flag": cflag,
            "slippage": slip,
            "base_verdict": base,
        }

    gated = [r for r in all_rows if r["kept"]]
    ungated = all_rows
    gated_is = [r for r in gated if dt.date.fromisoformat(r["date"]) < OOS_START]
    gated_oos = [r for r in gated if dt.date.fromisoformat(r["date"]) >= OOS_START]

    g_all = _block(gated)
    g_is = _block(gated_is)
    g_oos = _block(gated_oos)

    # --- combined verdict: significance + IS/OOS sign agreement + slippage + concentration
    is_exp = g_is["summary"]["expectancy_per_trade_usd"]
    oos_exp = g_oos["summary"]["expectancy_per_trade_usd"]
    both_sufficient = g_is["significance"]["sufficient"] and g_oos["significance"]["sufficient"]
    both_positive = is_exp > 0 and oos_exp > 0
    slip_ok = g_all["slippage"]["verdict"] == "SURVIVES_REALISTIC"
    not_concentrated = not g_all["concentration_flag"]["concentrated"]

    verdict = classify_wide_verdict(
        pooled_sufficient=g_all["significance"]["sufficient"],
        pooled_expectancy=g_all["summary"]["expectancy_per_trade_usd"],
        both_splits_sufficient=both_sufficient,
        both_splits_positive=both_positive,
        slippage_survives_realistic=slip_ok,
        concentrated=g_all["concentration_flag"]["concentrated"],
    )

    return {
        "probe": "range_scalp_tier2_regime_gated_widewindow",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "verdict": verdict,
        "window": {"start": start.isoformat(), "end": end.isoformat(), "oos_start": OOS_START.isoformat()},
        "frame_audit": (
            "Slices 1+2 declared this slice DATA-BLOCKED (n=8, 25-day window). Verified "
            "2026-07-01 the master SPY/VIX 5m (2025-01-01..2026-06-18) + OPRA real-fills "
            "(370 0DTE days) already cover the full history; the probes hardcoded a 25-day "
            "recent CSV on a stale 'master ends 2026-05-22' comment. This runs the SAME "
            "regime-gated fade over the full history."
        ),
        "gate": {
            "flat_ribbon_spread_max_cents": FLAT_SPREAD_MAX_CENTS,
            "vix_low": VIX_RANGE_LOW,
            "vix_high": VIX_RANGE_HIGH,
        },
        "n_trading_days": len(days),
        "gated_full_history": g_all,
        "gated_in_sample_2025": g_is,
        "gated_out_of_sample_2026": g_oos,
        "ungated_full_history": _block(ungated),
        "walk_forward": {
            "is_expectancy_usd": is_exp,
            "oos_expectancy_usd": oos_exp,
            "both_sufficient_n": both_sufficient,
            "both_positive": both_positive,
            "slippage_survives_realistic": slip_ok,
            "not_concentrated": not_concentrated,
        },
        "method_disclosures": {
            "reuse": "run_shotgun_day(tier_filter=2) + RANGE_SCALP_COMBO + regime-gate constants + "
                     "probe_stats; both original probes byte-identical (no regression risk).",
            "causality": "ribbon spread = full-frame causal EMA indexed at entry bar (== per-trade "
                         "slice, O(N) not O(N^2)); VIX = as-of last bar<=entry via searchsorted. No look-ahead.",
            "fill_model": "Real OPRA bars via run_shotgun_day/_simulate_trade_real (NO Black-Scholes).",
            "yardstick": "per-trade expectancy + IS/OOS sign agreement + probe_stats significance/"
                         "concentration/slippage. J edge_capture NOT used (auto-rejects range edges).",
            "limitations": "ONE combo, no tp/stop/strike sweep. A PROMOTABLE verdict justifies the "
                           "multi-combo IS/OOS sweep next; any other verdict is the honest full-history "
                           "answer the 25-day window could not give.",
        },
    }


def _print(result: dict) -> None:
    g = result["gated_full_history"]["summary"]
    isb = result["gated_in_sample_2025"]["summary"]
    oosb = result["gated_out_of_sample_2026"]["summary"]
    slip = result["gated_full_history"]["slippage"]
    print(f"VERDICT={result['verdict']}  days={result['n_trading_days']}")
    print(f"  GATED full : n={g['n_trades']} wr={g['win_rate']} exp=${g['expectancy_per_trade_usd']} "
          f"total=${g['total_pnl_usd']}")
    print(f"  IS  2025   : n={isb['n_trades']} exp=${isb['expectancy_per_trade_usd']} total=${isb['total_pnl_usd']}")
    print(f"  OOS 2026   : n={oosb['n_trades']} exp=${oosb['expectancy_per_trade_usd']} total=${oosb['total_pnl_usd']}")
    print(f"  slippage   : {slip['verdict']} breakeven={slip['breakeven_half_spread']}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="run a 3-month slice (2025-01..2025-03)")
    args = ap.parse_args()

    if args.smoke:
        result = run_wide_probe(dt.date(2025, 1, 2), dt.date(2025, 3, 31))
        _print(result)
        return 0

    result = run_wide_probe(WINDOW_START, WINDOW_END)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    _print(result)
    print(f"written: {OUT_PATH.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

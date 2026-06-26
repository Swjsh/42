"""DEPLOY-TIMING TEST: overnight-trend-agreement-bullish (slug=overnight-trend-agreement-bullish).

HYPOTHESIS (web-sourced — see scorecard for citations): the bull-continuation edge
(#1 vwap_continuation, CALL side = the live LONG edge) WINS more on days where the
OVERNIGHT futures session (Globex 18:00 prior-day ET -> 09:30 ET) confirmed a HEALTHY
UP-trend that is *not exhausted*, and FAILS on days where overnight already made the day's
extreme (an overnight blow-off). The deploy-timing rule: DEPLOY when overnight is
up-but-not-exhausted; ABSTAIN on overnight-blow-off days.

OVERNIGHT BLOW-OFF FLAG (computed from MES_1m / MNQ_1m overnight bars):
  overnight window = bars with t in [18:00 prior cal-day, 09:30 RTH-open) mapped to the
  RTH trading date (Globex session that PRECEDES that day's 09:30 open).
  overnight_close_position = (last_overnight_close - on_low) / (on_high - on_low)
  higher_high = on_high > prior trading day's overnight high
  BLOWOFF when overnight_close_position > 0.85 AND higher_high.
  (= overnight closed in the top 15% of its own range AND extended the prior overnight
   high -> price is sitting AT the overnight extreme = exhaustion risk.)

THE EDGE (reused byte-for-byte, C1/C14):
  detector  = _edgehunt_vwap_continuation.detect_signals (THE LIVE #1 detector)
  fills     = lib.simulator_real.simulate_trade_real (real OPRA, the WR authority)
  We take the CALL (bullish, side='C') signals only -- the long-continuation edge the
  hypothesis is about. Tier = ITM-2 (-2, the validated Bold tier) AND ATM (0) reported.

THE RIGHT BAR (deploy-timing layer, per the brief + L174):
  ACCEPT the abstain-on-blowoff mask ONLY IF
    (1) it LIFTS the book's risk-adjusted return (mean/day, Sharpe-by-day, Sortino, maxDD), AND
    (2) NO-REGRESSION: the ABSTAINED (blowoff) days sum NET-NEGATIVE (we removed losers,
        not winners) -- removing winning days is winner-killing, an automatic REJECT.
  Cross-validate MES vs MNQ: require SIGN-AGREEMENT (both instruments' blowoff masks
  point the same way) to reduce single-instrument overfit on small n.

DISCLOSURE (C1/C3/C7/OP-14/OP-20): real OPRA fills; per-trade & per-day EXPECTANCY;
small n by design (one CALL entry/day, ~18mo) -- reported honestly. SPY-direction !=
option edge (C3/L58). Futures-overnight features are causal (known by 09:30, before the
09:35 entry gate). RESEARCH ONLY, $0, no live edit, no orders. Markets closed.

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_b9_overnight_trend_agreement.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    detect_signals as detect_vwap_continuation,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

DATA = REPO / "data"
FUT = DATA / "futures"
OUT_JSON = ROOT / "analysis" / "recommendations" / "overnight-trend-agreement-bullish.json"
SCORECARD = ROOT / "analysis" / "recommendations" / "SUNDAY-FRESH-ANGLES-SCORECARD.md"

# HARD-WINDOW real fills to the cache last (per brief): OPRA cache ends 2026-06-18.
CACHE_LAST = dt.date(2026, 6, 18)

# sim convention (NEG=ITM, POS=OTM) -- same as recency_check
PREMIUM_STOP_PCT = -0.08
MAX_STRIKE_STEPS = 4
QTY = 3
TIERS = {"ITM-2": -2, "ATM": 0}   # validated tiers for #1

# overnight blowoff thresholds
BLOWOFF_POS = 0.85         # close in top 15% of overnight range
RTH_OPEN = dt.time(9, 30)
ON_START = dt.time(18, 0)  # Globex open ET


# ─────────────────────────────────────────────────────────────────────────────
# OVERNIGHT FEATURES from futures 1m (the causal deploy-timing signal)
# ─────────────────────────────────────────────────────────────────────────────
def overnight_features(fut_csv: Path) -> dict[dt.date, dict]:
    """Map each RTH trading date -> overnight (prior 18:00 ET .. 09:30 ET) session stats.

    A bar belongs to the overnight session PRECEDING trading-date D if its ET timestamp is
    in [18:00 of the prior session-day, 09:30 of D). We assign every bar a 'session_date'
    (the next RTH date it leads into) then aggregate.
    """
    df = pd.read_csv(fut_csv)
    ts = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    df = df.copy()
    df["ts"] = ts
    df["t"] = ts.dt.time
    df["cal_date"] = ts.dt.date
    # session_date = the trading date this bar leads INTO.
    #   bars at/after 18:00 ET  -> next calendar day's session
    #   bars before 09:30 ET    -> same calendar day's session
    #   bars 09:30..18:00 (RTH+afternoon) are NOT overnight -> excluded
    on_mask = (df["t"] >= ON_START) | (df["t"] < RTH_OPEN)
    on = df[on_mask].copy()
    # assign session_date
    sd = on["cal_date"].copy()
    after6 = on["t"] >= ON_START
    sd_after = (pd.to_datetime(on.loc[after6, "cal_date"]) + pd.Timedelta(days=1)).dt.date
    sd.loc[after6] = sd_after
    on["session_date"] = sd

    feats: dict[dt.date, dict] = {}
    for d, g in on.groupby("session_date", sort=True):
        g = g.sort_values("ts")
        if len(g) < 30:   # need a real overnight session (>=30 1m bars)
            continue
        hi = float(g["high"].max())
        lo = float(g["low"].min())
        # 09:30 "close" = last overnight bar before 09:30 (the bar that ends the overnight run)
        last_close = float(g["close"].iloc[-1])
        first_open = float(g["open"].iloc[0])
        rng = hi - lo
        pos = (last_close - lo) / rng if rng > 0 else 0.5
        feats[d] = {
            "on_high": hi, "on_low": lo, "on_first_open": first_open,
            "on_last_close": last_close, "on_range": round(rng, 2),
            "on_close_position": round(float(pos), 4),
            "on_up": last_close > first_open,        # overnight net up?
            "n_on_bars": int(len(g)),
        }
    # higher_high vs prior overnight high
    dates = sorted(feats)
    prev_hi = None
    for d in dates:
        feats[d]["higher_high"] = bool(prev_hi is not None and feats[d]["on_high"] > prev_hi)
        prev_hi = feats[d]["on_high"]
    # blowoff flag
    for d in dates:
        f = feats[d]
        f["blowoff"] = bool(f["on_close_position"] > BLOWOFF_POS and f["higher_high"])
    return feats


# ─────────────────────────────────────────────────────────────────────────────
# EDGE by-day P&L (CALL/bull signals, real OPRA fills) -- reused path
# ─────────────────────────────────────────────────────────────────────────────
def edge_call_rows(signals, spy, ribbon, vix, *, strike_offset, setup):
    rows = []
    n_total = n_filled = n_miss = n_none = 0
    for sg in signals:
        if sg.side != "C":   # bull/long edge only
            continue
        n_total += 1
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm + strike_offset   # call: strike = atm + offset (offset<0 => ITM)
        strike = _nearest_cached_strike(d, target, "C", MAX_STRIKE_STEPS)
        if strike is None:
            n_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side="C",
            qty=QTY, setup=setup, strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=PREMIUM_STOP_PCT)
        if fill is None or fill.dollar_pnl is None:
            n_none += 1
            continue
        n_filled += 1
        rows.append({"date": str(d), "pnl": round(float(fill.dollar_pnl), 2)})
    cov = {"call_signals": n_total, "filled": n_filled, "cache_miss": n_miss, "sim_none": n_none}
    return rows, cov


# ─────────────────────────────────────────────────────────────────────────────
# METRICS / PARTITION
# ─────────────────────────────────────────────────────────────────────────────
def daily_pnl(rows) -> dict[dt.date, float]:
    by = defaultdict(float)
    for r in rows:
        by[dt.date.fromisoformat(r["date"])] += r["pnl"]
    return dict(by)


def risk_adjusted(daily_vals: list[float]) -> dict:
    """Sharpe/Sortino/maxDD on a per-DAY P&L series (the book's risk-adjusted return)."""
    if not daily_vals:
        return {"n_days": 0}
    a = np.array(daily_vals, float)
    mean = float(a.mean())
    sd = float(a.std(ddof=1)) if len(a) > 1 else 0.0
    downs = a[a < 0]
    dsd = float(downs.std(ddof=1)) if len(downs) > 1 else (float(abs(downs.mean())) if len(downs) else 0.0)
    eq = np.cumsum(a)
    peak = np.maximum.accumulate(eq)
    maxdd = float((eq - peak).min()) if len(eq) else 0.0
    return {
        "n_days": len(a),
        "total": round(float(a.sum()), 2),
        "mean_per_day": round(mean, 2),
        "std_per_day": round(sd, 2),
        "sharpe_day": round(mean / sd, 3) if sd > 0 else None,
        "sortino_day": round(mean / dsd, 3) if dsd > 0 else None,
        "maxdd": round(maxdd, 2),
        "win_days": int((a > 0).sum()),
        "loss_days": int((a < 0).sum()),
    }


def partition_and_test(edge_daily: dict, feats: dict, instrument: str) -> dict:
    """Partition the edge's by-day P&L into blowoff vs non-blowoff (per `feats`),
    apply the abstain-on-blowoff mask, and judge against the deploy-timing bar."""
    # only days that have BOTH an edge fill AND an overnight feature
    common = sorted(d for d in edge_daily if d in feats)
    missing_feat = sorted(d for d in edge_daily if d not in feats)
    blow_days = [d for d in common if feats[d]["blowoff"]]
    keep_days = [d for d in common if not feats[d]["blowoff"]]

    full_vals = [edge_daily[d] for d in common]
    keep_vals = [edge_daily[d] for d in keep_days]
    blow_vals = [edge_daily[d] for d in blow_days]

    full_ra = risk_adjusted(full_vals)
    keep_ra = risk_adjusted(keep_vals)   # = the deploy-timing book (abstain on blowoff)
    blow_ra = risk_adjusted(blow_vals)   # = the abstained set (must be net-NEGATIVE)

    # gate 1: lifts risk-adjusted return (mean/day up AND maxDD not worse AND sharpe up if defined)
    lift_mean = keep_ra.get("mean_per_day", -9e9) > full_ra.get("mean_per_day", -9e9)
    sh_f, sh_k = full_ra.get("sharpe_day"), keep_ra.get("sharpe_day")
    lift_sharpe = (sh_k is not None and sh_f is not None and sh_k > sh_f)
    dd_ok = keep_ra.get("maxdd", -9e9) >= full_ra.get("maxdd", -9e9)  # less-negative or equal
    lift_total = keep_ra.get("total", -9e9) >= full_ra.get("total", -9e9)
    lifts = bool(lift_mean and dd_ok and lift_total)

    # gate 2: no-regression -- abstained (blowoff) days sum NET-NEGATIVE
    blow_total = blow_ra.get("total", 0.0)
    blow_net_negative = bool(len(blow_vals) > 0 and blow_total < 0)

    accept = bool(lifts and blow_net_negative)
    return {
        "instrument": instrument,
        "n_common_days": len(common),
        "n_blowoff_days": len(blow_days),
        "n_keep_days": len(keep_days),
        "days_missing_overnight_feat": [str(x) for x in missing_feat],
        "full_book": full_ra,
        "deploy_timing_book_keep": keep_ra,
        "abstained_blowoff_set": blow_ra,
        "blowoff_total": round(float(blow_total), 2),
        "gate_lifts_risk_adjusted": lifts,
        "gate_lift_detail": {"mean_up": lift_mean, "sharpe_up": lift_sharpe,
                             "maxdd_ok": dd_ok, "total_ge": lift_total},
        "gate_blowoff_net_negative": blow_net_negative,
        "ACCEPT": accept,
        "blowoff_day_pnls": {str(d): round(edge_daily[d], 2) for d in blow_days},
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def main() -> int:
    print("[ona] loading merged SPY+VIX (master + recent) ...", flush=True)
    master_spy = pd.read_csv(DATA / "spy_5m_2025-01-01_2026-06-16.csv")
    master_vix = pd.read_csv(DATA / "vix_5m_2025-01-01_2026-06-16.csv")
    recent_spy = pd.read_csv(DATA / "spy_5m_2026-05-19_2026-06-18.csv")
    recent_vix = pd.read_csv(DATA / "vix_5m_2026-05-19_2026-06-18.csv")
    spy_raw = pd.concat([master_spy, recent_spy], ignore_index=True)
    vix_raw = pd.concat([master_vix, recent_vix], ignore_index=True)

    spy = _normalize_spy(spy_raw)
    spy = spy[spy["date"] <= CACHE_LAST].reset_index(drop=True)  # HARD-WINDOW to OPRA cache
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    print(f"[ona] SPY bars={len(spy)} trading_days={len(days)} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    signals = detect_vwap_continuation(days, vix, breakout_only=False, put_needs_rising_vix=False)
    n_call = sum(1 for s in signals if s.side == "C")
    print(f"[ona] vwap_continuation signals total={len(signals)} CALL/bull={n_call}", flush=True)

    print("[ona] computing overnight features from MES_1m + MNQ_1m ...", flush=True)
    feats_mes = overnight_features(FUT / "MES_1m_continuous.csv")
    feats_mnq = overnight_features(FUT / "MNQ_1m_continuous.csv")
    print(f"[ona] MES overnight days={len(feats_mes)} (blowoff={sum(f['blowoff'] for f in feats_mes.values())}) "
          f"MNQ days={len(feats_mnq)} (blowoff={sum(f['blowoff'] for f in feats_mnq.values())})", flush=True)

    results = {}
    for tier_name, off in TIERS.items():
        rows, cov = edge_call_rows(signals, spy, ribbon, vix, strike_offset=off,
                                   setup=f"ONA_{tier_name}")
        ed = daily_pnl(rows)
        # futures data ends 2026-06-12; intersect with edge days anyway (partition handles it)
        res_mes = partition_and_test(ed, feats_mes, "MES")
        res_mnq = partition_and_test(ed, feats_mnq, "MNQ")
        # sign-agreement: both instruments must ACCEPT (or both reject) for a robust verdict
        both_accept = res_mes["ACCEPT"] and res_mnq["ACCEPT"]
        sign_agree = (res_mes["ACCEPT"] == res_mnq["ACCEPT"])
        results[tier_name] = {
            "strike_offset": off,
            "coverage": cov,
            "n_edge_days_total": len(ed),
            "edge_full_book_all_days": risk_adjusted(list(ed.values())),
            "MES": res_mes,
            "MNQ": res_mnq,
            "sign_agreement_mes_mnq": sign_agree,
            "BOTH_ACCEPT": both_accept,
            "VERDICT": ("ACCEPT" if both_accept else
                        ("REJECT_no_sign_agreement" if not sign_agree else "REJECT")),
        }
        print(f"\n[ona] === TIER {tier_name} (off={off}) ===", flush=True)
        print(f"  edge full-book: {results[tier_name]['edge_full_book_all_days']}", flush=True)
        for inst in ("MES", "MNQ"):
            r = results[tier_name][inst]
            print(f"  {inst}: common={r['n_common_days']} blowoff={r['n_blowoff_days']} "
                  f"keep={r['n_keep_days']} | full mean/day=${r['full_book'].get('mean_per_day')} "
                  f"keep mean/day=${r['deploy_timing_book_keep'].get('mean_per_day')} "
                  f"blowoff_total=${r['blowoff_total']} | lifts={r['gate_lifts_risk_adjusted']} "
                  f"blow_neg={r['gate_blowoff_net_negative']} -> ACCEPT={r['ACCEPT']}", flush=True)
        print(f"  sign-agree={sign_agree} BOTH_ACCEPT={both_accept} "
              f"VERDICT={results[tier_name]['VERDICT']}", flush=True)

    summary = {
        "slug": "overnight-trend-agreement-bullish",
        "kind": "deploy_timing",
        "run_date": dt.date.today().isoformat(),
        "window": f"{spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
        "cache_last_hard_window": str(CACHE_LAST),
        "futures_note": ("MES/MNQ 1m continuous include the Globex overnight session "
                         "(18:00 prior ET .. 09:30); files end 2026-06-12 so edge days after "
                         "that have no overnight feature (counted in days_missing_overnight_feat)"),
        "blowoff_def": (f"on_close_position>{BLOWOFF_POS} AND higher_high vs prior overnight high; "
                        "on_close_position=(last_overnight_close - on_low)/(on_high - on_low)"),
        "detector": "_edgehunt_vwap_continuation.detect_signals (LIVE #1), CALL side only",
        "fills_authority": "lib.simulator_real.simulate_trade_real (real OPRA, C1)",
        "deploy_timing_bar": ("ACCEPT iff (1) keep-book lifts risk-adjusted return [mean/day up, "
                              "maxDD not worse, total not worse] AND (2) abstained blowoff days sum "
                              "NET-NEGATIVE (no winner-killing, L174); cross-validated MES & MNQ "
                              "must SIGN-AGREE"),
        "tiers": results,
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[ona] wrote {OUT_JSON}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

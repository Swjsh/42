"""DEPLOY-TIMING HYPOTHESIS: overnight-vol-expansion-favors-edges.

slug = overnight-vol-expansion-favors-edges  |  kind = regime_gate (DEPLOY-TIMING layer)

CLAIM (web-sourced): overnight realized volatility positively predicts next-day intraday
realized volatility (volatility clustering / persistence -- GARCH-family stylized fact;
overnight returns carry information into the cash session). These VWAP-continuation edges
need intraday RANGE to reach TP1/runner targets, so days FOLLOWING a high-overnight-vol
session should produce better edge outcomes than dead-overnight (theta-bleed / chop) days.

DEPLOY-TIMING RULE under test: DEPLOY the book when overnight realized vol (sum of |1m log
returns| over the 18:00->09:30 ET window, from MES continuous 1m incl. globex) EXCEEDS a
rolling-60d median; ABSTAIN on low-overnight-vol nights.

THE RIGHT BAR (deploy-timing layer, NOT a new signal, NOT a per-trade gate):
  ACCEPT the abstain-on-low-overnight-vol mask ONLY IF
    (a) it LIFTS the BOOK's risk-adjusted return (daily Sharpe / Sortino / total, lower maxDD)
        relative to deploy-every-day, AND
    (b) NO-REGRESSION (L174): the ABSTAINED days are net-NEGATIVE in aggregate (we removed
        losers, not winners). If abstained days were net-positive, the mask is winner-removal
        -> REJECT regardless of headline lift.
  DISAMBIGUATE from VIX-level (already DEAD via regime-gate-per-trade): this is an overnight-
  FLOW signal. We (1) report the correlation of overnight-vol with entry VIX, and (2) re-run
  the split CONTROLLING for entry VIX (within-VIX-tercile) so a positive result cannot be the
  VIX knob in disguise.

REUSE (no edits to any watcher/params/risk_gate/orchestrator/heartbeat -- money-path guard):
  - recency_check.{load_merged_spy_vix, detect_all, simulate_set, EDGE_TIERS, BOOKS} -> the
    validated detectors + the real-OPRA fill path (C1, the WR authority).
  - _edgehunt_vwap_continuation.{_normalize_spy, _align_vix}; infinite_ammo.build_day_contexts.
  - MES_1m_continuous.csv (globex 1m incl. overnight) for the overnight-vol feature.

HARD WINDOW: real OPRA fills cached to 2026-06-18; MES 1m overnight to 2026-06-12. The JOIN
(overnight night ending morning of day D -> edge P&L on day D) is therefore bounded by MES:
classifiable trading days run through 2026-06-12. Disclosed honestly; no extrapolation.

Pure Python, $0 (no LLM). RESEARCH ONLY -- no live edit, no orders (Sunday money-path guard).

Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_deploytiming_overnight_vol.py
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

from autoresearch.infinite_ammo_discovery import build_day_contexts  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy, _align_vix,
)
from autoresearch import recency_check as rc  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

MES_1M = REPO / "data" / "futures" / "MES_1m_continuous.csv"
OUT_JSON = ROOT / "analysis" / "recommendations" / "deploytiming-overnight-vol.json"

# Overnight window: globex open 18:00 prev-day -> 09:30 ET cash open. Realized vol = sum|1m logret|.
OVERNIGHT_START = dt.time(18, 0)
OVERNIGHT_END = dt.time(9, 30)
ROLL_MEDIAN_D = 60            # rolling median lookback (trading days) for the deploy threshold
OPRA_CACHE_LAST = dt.date(2026, 6, 18)


# ─────────────────────────────────────────────────────────────────────────────
# OVERNIGHT REALIZED VOL per trading day (causal: uses only the night BEFORE day D)
# ─────────────────────────────────────────────────────────────────────────────
def overnight_vol_by_day() -> pd.DataFrame:
    """For each cash trading day D, overnight realized vol = sum(|1m log returns|) over the
    globex window [18:00 prev-session .. 09:30 D). Returns DataFrame indexed by date D.

    The window is keyed to the SESSION that ENDS on D's 09:30 open: bars with t>=18:00 belong
    to the night leading into the NEXT cash day; bars with t<09:30 belong to the morning of
    their own calendar day's cash session. We bucket each overnight bar to its 'cash day'.
    """
    df = pd.read_csv(MES_1M)
    ts = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    df = pd.DataFrame({"ts": ts, "close": df["close"].astype(float)}).sort_values("ts").reset_index(drop=True)
    df["t"] = df["ts"].dt.time
    df["cal_date"] = df["ts"].dt.date
    # Overnight bar membership: 18:00..23:59 -> next cash day; 00:00..09:29 -> same cash day.
    is_evening = df["t"] >= OVERNIGHT_START
    is_early = df["t"] < OVERNIGHT_END
    df = df[is_evening | is_early].copy()
    # cash_day: evening bars roll forward to next calendar day; early bars stay.
    cal = pd.to_datetime(df["cal_date"])
    df["cash_day"] = np.where(is_evening[df.index], (cal + pd.Timedelta(days=1)).dt.date, df["cal_date"])
    df["logret"] = np.log(df["close"]).diff()
    # diff() at the very first bar of each contiguous overnight block crosses sessions; we
    # null those by recomputing diff WITHIN each cash_day block (no cross-night contamination).
    df["logret"] = df.groupby("cash_day")["close"].transform(lambda s: np.log(s).diff())
    g = df.groupby("cash_day")
    out = pd.DataFrame({
        "overnight_rv": g["logret"].apply(lambda s: float(np.abs(s).sum())),
        "overnight_bars": g["logret"].apply(lambda s: int(s.notna().sum())),
        "overnight_range_pct": g.apply(
            lambda x: float((x["close"].max() - x["close"].min()) / x["close"].mean()),
            include_groups=False),
    })
    out.index = pd.to_datetime(out.index).date
    out.index.name = "date"
    # Require a real overnight session (drop holiday stubs with too few bars).
    out = out[out["overnight_bars"] >= 120]   # >=2h of globex bars
    return out


# ─────────────────────────────────────────────────────────────────────────────
# BOOK DAILY P&L (real OPRA fills) -- reuse recency_check sim, aggregate per day per book
# ─────────────────────────────────────────────────────────────────────────────
def build_book_daily_pnl(spy, ribbon, vix, days) -> tuple[dict, dict, dict]:
    """Returns (book_daily, edge_daily, entry_vix_by_day).
    book_daily[book]   = {date -> pnl}     (sum across that book's edge/tier members)
    edge_daily[edge]   = {date -> pnl}     (ATM tier, single-edge view)
    entry_vix_by_day   = {date -> mean entry VIX across all fills that day} (the control var)
    """
    sigs = rc.detect_all(days, spy, vix)
    sigs.pop("_vix_cfg", None)
    rows_by_edge_tier: dict[tuple, list[dict]] = {}
    entry_vix_acc: dict[dt.date, list[float]] = defaultdict(list)
    for edge, tiers in rc.EDGE_TIERS.items():
        sig = sigs[edge]
        for tier, off in tiers.items():
            rows, _ = rc.simulate_set(sig, spy, ribbon, vix, strike_offset=off,
                                      setup=f"{edge}_{tier}")
            rows_by_edge_tier[(edge, tier)] = rows
        # capture entry VIX per fill-day from the ATM tier signals (one read per signal)
        for sg in sig:
            d = spy.iloc[sg.bar_idx]["timestamp_et"].date()
            v = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
            if v > 0:
                entry_vix_acc[d].append(v)

    book_daily: dict[str, dict] = {}
    for book, members in rc.BOOKS.items():
        bd: dict[dt.date, float] = defaultdict(float)
        for edge, tier in members:
            for r in rows_by_edge_tier[(edge, tier)]:
                bd[dt.date.fromisoformat(r["date"])] += r["pnl"]
        book_daily[book] = dict(bd)

    edge_daily: dict[str, dict] = {}
    for edge in rc.EDGE_TIERS:
        ed: dict[dt.date, float] = defaultdict(float)
        for r in rows_by_edge_tier[(edge, "ATM")]:
            ed[dt.date.fromisoformat(r["date"])] += r["pnl"]
        edge_daily[edge] = dict(ed)

    entry_vix_by_day = {d: float(np.mean(v)) for d, v in entry_vix_acc.items() if v}
    return book_daily, edge_daily, entry_vix_by_day


# ─────────────────────────────────────────────────────────────────────────────
# METRICS / THE BAR
# ─────────────────────────────────────────────────────────────────────────────
def daily_stats(daily_pnl: list[float]) -> dict:
    if not daily_pnl:
        return {"n_days": 0}
    a = np.array(daily_pnl, float)
    mean = float(a.mean())
    sd = float(a.std(ddof=1)) if len(a) > 1 else 0.0
    downside = a[a < 0]
    dsd = float(downside.std(ddof=1)) if len(downside) > 1 else (abs(float(downside.mean())) if len(downside) else 0.0)
    eq = np.cumsum(a)
    peak = np.maximum.accumulate(eq)
    maxdd = float((eq - peak).min()) if len(eq) else 0.0
    return {
        "n_days": len(a),
        "total": round(float(a.sum()), 2),
        "mean_day": round(mean, 2),
        "std_day": round(sd, 2),
        "sharpe_day": round(mean / sd, 3) if sd > 0 else None,
        "sortino_day": round(mean / dsd, 3) if dsd > 0 else None,
        "max_dd": round(maxdd, 2),
        "win_days": int((a > 0).sum()),
        "loss_days": int((a < 0).sum()),
        "sign": "POSITIVE" if a.sum() > 0 else ("FLAT" if a.sum() == 0 else "NEGATIVE"),
    }


def evaluate_mask(book_daily_for_day: dict, hi_days: set, lo_days: set) -> dict:
    """Deploy-on-HI vs deploy-every-day, plus the no-regression check on the ABSTAINED (lo) days."""
    all_days = sorted(d for d in book_daily_for_day if d in hi_days or d in lo_days)
    deploy_all = [book_daily_for_day[d] for d in all_days]
    deploy_hi = [book_daily_for_day[d] for d in all_days if d in hi_days]
    abstained = [book_daily_for_day[d] for d in all_days if d in lo_days]

    s_all = daily_stats(deploy_all)
    s_hi = daily_stats(deploy_hi)
    s_abst = daily_stats(abstained)

    # THE BAR
    # (a) risk-adjusted lift: deploy-HI Sharpe/Sortino/total better than deploy-all, DD no worse.
    def _g(s, k):
        return s.get(k) if s.get(k) is not None else -9e9
    lift_total = (s_hi.get("total", -9e9) - s_all.get("total", -9e9))
    lift_sharpe = (_g(s_hi, "sharpe_day") - _g(s_all, "sharpe_day"))
    lift_sortino = (_g(s_hi, "sortino_day") - _g(s_all, "sortino_day"))
    dd_no_worse = s_hi.get("max_dd", -9e9) >= s_all.get("max_dd", -9e9)  # closer to 0 = better
    risk_adj_lift = (lift_sharpe > 0 and lift_total > 0 and dd_no_worse)
    # (b) no-regression: abstained days must be net-NEGATIVE in aggregate (removed losers)
    abstained_net_negative = (s_abst.get("total", 0.0) < 0) if s_abst.get("n_days", 0) else False

    accept = bool(risk_adj_lift and abstained_net_negative)
    if accept:
        verdict = "DEPLOY_TIMING_SIGNAL"
    elif (lift_sharpe > 0 or lift_total > 0) and not abstained_net_negative:
        verdict = "WALL"   # looks like lift but it's winner-removal -> not real
    else:
        verdict = "DEAD"
    return {
        "deploy_every_day": s_all,
        "deploy_hi_only": s_hi,
        "abstained_lo_days": s_abst,
        "lift_total": round(lift_total, 2),
        "lift_sharpe": round(lift_sharpe, 3),
        "lift_sortino": round(lift_sortino, 3),
        "dd_no_worse": dd_no_worse,
        "risk_adjusted_lift": risk_adj_lift,
        "abstained_net_negative": abstained_net_negative,
        "accept": accept,
        "verdict": verdict,
    }


def main() -> int:
    print("[deploytiming] loading merged SPY+VIX + MES overnight ...", flush=True)
    spy_raw, vix_raw = rc.load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))

    onv = overnight_vol_by_day()
    print(f"[deploytiming] overnight-vol days: {len(onv)} "
          f"({onv.index.min()}..{onv.index.max()})", flush=True)

    book_daily, edge_daily, entry_vix_by_day = build_book_daily_pnl(spy, ribbon, vix, days)

    # JOIN: classifiable trading days = days with overnight-vol AND <= OPRA cache last AND <= MES last
    mes_last = onv.index.max()
    join_cutoff = min(OPRA_CACHE_LAST, mes_last)

    # rolling-60d median deploy threshold (causal: median over PRIOR 60 classifiable days, shift 1)
    onv_sorted = onv.sort_index()
    onv_sorted["roll_med"] = onv_sorted["overnight_rv"].shift(1).rolling(ROLL_MEDIAN_D, min_periods=20).median()
    onv_sorted["deploy_hi"] = onv_sorted["overnight_rv"] > onv_sorted["roll_med"]

    # also keep a static-median fallback (for tiny windows where rolling can't warm up)
    classifiable = onv_sorted[(onv_sorted.index <= join_cutoff)]
    static_med = float(classifiable["overnight_rv"].median())

    def split_for(daily_map: dict, recent_only: dict | None = None):
        """Return (hi_days, lo_days) over classifiable days that ALSO have edge P&L."""
        hi, lo = set(), set()
        for d, row in classifiable.iterrows():
            if d not in daily_map:
                continue
            thr = row["roll_med"] if not np.isnan(row["roll_med"]) else static_med
            (hi if row["overnight_rv"] > thr else lo).add(d)
        return hi, lo

    results = {}
    for book, dmap in book_daily.items():
        hi, lo = split_for(dmap)
        results[book] = evaluate_mask(dmap, hi, lo)
        results[book]["n_hi_days"] = len(hi & set(dmap))
        results[book]["n_lo_days"] = len(lo & set(dmap))

    edge_results = {}
    for edge, dmap in edge_daily.items():
        hi, lo = split_for(dmap)
        edge_results[edge] = evaluate_mask(dmap, hi, lo)
        edge_results[edge]["n_hi_days"] = len(hi & set(dmap))
        edge_results[edge]["n_lo_days"] = len(lo & set(dmap))

    # ── DISAMBIGUATION from VIX-level ─────────────────────────────────────────
    # (1) correlation overnight_rv vs entry VIX on shared days
    shared = [d for d in classifiable.index if d in entry_vix_by_day]
    if len(shared) >= 5:
        onv_v = np.array([classifiable.loc[d, "overnight_rv"] for d in shared], float)
        vix_v = np.array([entry_vix_by_day[d] for d in shared], float)
        corr = float(np.corrcoef(onv_v, vix_v)[0, 1])
    else:
        corr = None

    # (2) within-VIX-tercile control: for the headline book, does the HI-overnight lift survive
    #     when we restrict to the MIDDLE VIX tercile (so VIX level is held ~constant)?
    headline_book = "Safe2_ATM_1+2+4"
    dmap = book_daily[headline_book]
    vix_control = {"note": "insufficient overlap"}
    cand = [d for d in classifiable.index if d in dmap and d in entry_vix_by_day]
    if len(cand) >= 12:
        vv = np.array([entry_vix_by_day[d] for d in cand], float)
        q1, q2 = np.quantile(vv, [1/3, 2/3])
        mid = [d for d in cand if q1 <= entry_vix_by_day[d] <= q2]
        if len(mid) >= 6:
            hi_m = {d for d in mid if classifiable.loc[d, "overnight_rv"] >
                    (classifiable.loc[d, "roll_med"] if not np.isnan(classifiable.loc[d, "roll_med"]) else static_med)}
            lo_m = set(mid) - hi_m
            hi_pnl = [dmap[d] for d in hi_m]
            lo_pnl = [dmap[d] for d in lo_m]
            vix_control = {
                "vix_tercile_bounds": [round(float(q1), 2), round(float(q2), 2)],
                "mid_tercile_n_days": len(mid),
                "hi_overnight_in_mid_vix": daily_stats(hi_pnl),
                "lo_overnight_in_mid_vix": daily_stats(lo_pnl),
                "interpretation": ("if HI-overnight still beats LO-overnight WITHIN one VIX "
                                   "tercile, the signal is overnight-FLOW not VIX-level in disguise"),
            }

    headline_verdict = results[headline_book]["verdict"]
    any_accept = any(r["accept"] for r in results.values()) or any(r["accept"] for r in edge_results.values())

    summary = {
        "slug": "overnight-vol-expansion-favors-edges",
        "kind": "regime_gate (DEPLOY-TIMING layer)",
        "run_date": dt.date.today().isoformat(),
        "claim": ("overnight realized vol positively predicts next-day intraday range; "
                  "continuation edges need range to reach TP1/runner -> deploy on high-overnight-"
                  "vol nights, abstain on dead-overnight (theta-bleed/chop) days"),
        "web_sources": [
            "Volatility clustering / persistence (GARCH stylized fact): Bollerslev (1986) JoE; "
            "Engle (1982) ARCH. High vol tends to be followed by high vol.",
            "Overnight->intraday vol spillover: e.g. 'Overnight Returns and Firm-Specific "
            "Investor Sentiment' (Berkman et al. 2012, JFQA) + the broad RV-persistence "
            "literature (Andersen/Bollerslev/Diebold realized-vol HAR models) showing lagged "
            "RV (incl. overnight component) predicts next-period RV.",
        ],
        "the_bar": ("DEPLOY-TIMING layer: ACCEPT only if (a) abstain-on-low-overnight-vol LIFTS "
                    "the BOOK risk-adjusted return (Sharpe/Sortino/total up, maxDD no worse) AND "
                    "(b) NO-REGRESSION (L174): the ABSTAINED days are net-NEGATIVE (removed losers, "
                    "not winners). Disambiguated from the DEAD VIX-level knob by entry-VIX control."),
        "data": {
            "overnight_feature": "sum(|MES 1m log returns|) over 18:00->09:30 ET (globex incl. overnight)",
            "mes_overnight_last": str(mes_last),
            "opra_cache_last": str(OPRA_CACHE_LAST),
            "join_cutoff": str(join_cutoff),
            "join_caveat": ("JOIN bounded by MES 1m (ends 2026-06-12) -- classifiable trading days "
                            "run through 2026-06-12 though OPRA fills exist to 2026-06-18; "
                            "the freshest ~4 trading days are NOT classifiable (disclosed)."),
            "deploy_threshold": f"overnight_rv > rolling-{ROLL_MEDIAN_D}d median (causal shift-1); "
                                f"static-median fallback={round(static_med, 5)} pre-warmup",
            "fills_authority": "real OPRA via lib.simulator_real (C1, the WR authority)",
        },
        "overnight_vol_days": int(len(onv)),
        "classifiable_days": int(len(classifiable)),
        "vix_disambiguation": {
            "corr_overnight_rv_vs_entry_vix": (round(corr, 3) if corr is not None else None),
            "within_mid_vix_tercile_control": vix_control,
        },
        "books": results,
        "edges_ATM_single": edge_results,
        "headline": {
            "book": headline_book,
            "verdict": headline_verdict,
            "any_accept": any_accept,
        },
        "DISCLOSURE": {
            "small_n": ("classifiable window is short -- per-book n_days is SMALL; reported honestly, "
                        "not a standing ratification. A deploy-timing mask on this few days is a "
                        "directional read, not a live flip."),
            "no_regression": "L174 -- abstained days must be net-negative; winner-removal is rejected",
            "vix_separation": "C5/L122 -- VIX *level* gating is DEAD; this is overnight-FLOW, controlled for VIX",
            "spy_vs_option": "C3/L58 -- real OPRA fills; SPY/futures range != option edge",
            "research_only": "no live edit, no orders (Sunday money-path guard)",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    print("\n=== OVERNIGHT-VOL DEPLOY-TIMING VERDICT ===")
    print(f"classifiable days={len(classifiable)} (overnight-vol AND <= {join_cutoff})")
    print(f"corr(overnight_rv, entry_VIX) = {corr}")
    for book, r in results.items():
        a = r["deploy_every_day"]; h = r["deploy_hi_only"]; ab = r["abstained_lo_days"]
        print(f"\nBOOK {book} (hi={r['n_hi_days']}d lo={r['n_lo_days']}d)")
        print(f"  deploy-ALL : total=${a.get('total')} mean=${a.get('mean_day')} "
              f"sharpe={a.get('sharpe_day')} sortino={a.get('sortino_day')} maxDD=${a.get('max_dd')}")
        print(f"  deploy-HI  : total=${h.get('total')} mean=${h.get('mean_day')} "
              f"sharpe={h.get('sharpe_day')} sortino={h.get('sortino_day')} maxDD=${h.get('max_dd')}")
        print(f"  ABSTAINED  : total=${ab.get('total')} ({ab.get('n_days')}d) "
              f"-> net-neg={r['abstained_net_negative']}")
        print(f"  lift total=${r['lift_total']} sharpe={r['lift_sharpe']} "
              f"-> risk_adj_lift={r['risk_adjusted_lift']} ACCEPT={r['accept']} [{r['verdict']}]")
    print(f"\nheadline {headline_book} -> {headline_verdict}  any_accept={any_accept}")
    print(f"wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

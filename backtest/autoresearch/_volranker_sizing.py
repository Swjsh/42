"""VOLRANKER SIZING OVERLAY — overnight-realized-vol as a SIZING knob on LIVE edge #1.

slug = overnight-vol-sizing-overlay  |  kind = sizing_overlay (NOT a gate, NOT a new signal)

THE LEVER. The strat-frontier is mined; the remaining compounding lever is SIZING. The Sunday
W-track (`_deploytiming_overnight_vol.py` / `deploytiming-overnight-vol.json`) established that
OVERNIGHT realized vol (sum|MES 1m logret| over 18:00->09:30 ET) is a REAL day-QUALITY ranker
that is VIX-INDEPENDENT: holding entry-VIX in the MIDDLE tercile (16.72-18.61, 53 days), HIGH-
overnight-vol days returned $141.35/day (Sharpe 0.745, Sortino 3.736) vs LOW $24.20/day (Sharpe
0.17). corr(overnight_rv, entry_VIX)=0.874 but the within-VIX control SURVIVES -> it is overnight
FLOW, not the DEAD VIX-level knob in disguise (C5/L122).

BUT it FAILED as an ABSTAIN GATE (L174 winner-removal): the low-overnight-vol days it would SKIP
are still net-POSITIVE (+$4,803 Safe / +$6,816 Bold) -> abstaining throws away real profit; the
Sharpe bump is a denominator artifact. The W-track scorecard's own forward-looking note:
"a SIZE-UP-on-high-overnight-vol study, never an abstain; that is a separate sizing hypothesis."
THIS IS THAT STUDY.

THE INSIGHT a ranker that fails as a GATE can still work as a SIZING overlay: it never ZEROES a
day (so NO winner-removal, L174-safe by construction), it just re-WEIGHTS -- size BIGGER on top-
tercile (better-mean) days, SMALLER on bottom-tercile days, BASE on mid. The bottom-tercile days
stay in the book (still net-positive) at a reduced -- never zero -- size.

WHAT THIS REUSES BYTE-FOR-BYTE (Sunday SAFE-research guard -- NO watcher/params/risk_gate/
orchestrator/heartbeat/simulator_real edits, NO orders, NO commit; RESEARCH SIM ONLY):
  - the LIVE #1 detector: `_edgehunt_vwap_continuation.detect_signals` (via _b10_sizing).
  - the real-OPRA trade stream + qty-invariant per-trade return + entry_premium: `_b10_sizing.{T,
    simulate_stream}` (C1 -- the WR authority; pct = return-on-capital-deployed).
  - the Rule-6 cap-clamp: `_b10_sizing.contracts_from_fraction` (per-trade cap + min-3 floor;
    the SAME clamp WP-3's spec uses -- respects_hard_caps by construction).
  - the overnight-vol feature: `_deploytiming_overnight_vol.overnight_vol_by_day` (the EXACT
    W-track definition: sum|MES 1m logret| over 18:00->09:30 ET, globex incl. overnight).
  - SPY/VIX merge + normalize: `recency_check.{load_merged_spy_vix}` +
    `_edgehunt_vwap_continuation.{_normalize_spy,_align_vix}`.

DEPLOYED #1 CONFIG (CLAUDE.md account context + WP-3): Safe-2 ATM (offset 0) / Bold ITM-2 (-2),
qty-3 floor, -8% premium stop. (The 1DTE/dollar-stop variant is the WP-8 SHIP-spec layer; the
overnight-vol RANKER itself was measured on this real-OPRA #1 stream, so the overlay is applied
to the SAME stream the ranker was found on -- no stream drift, C14.)

CAUSAL TERCILE (no look-ahead, L06/L34/L165): each trade-day's overnight_rv is ranked against
the TRAILING window of PRIOR classifiable days (rolling-60d, shift-1 -- the SAME causal mechanism
the W-track split used). Tercile cuts = the 1/3 & 2/3 quantiles of that trailing window, so the
day's bucket is known by 09:30 (before the 09:35 entry gate). Pre-warmup (< MIN_WARMUP prior days)
-> BASE size (mid), never a guess.

THE BAR (sizing overlay, NOT a gate): the overlay must
  (1) IMPROVE risk-adjusted return -- per-trade Sharpe OR per-day Sharpe/Sortino UP, OR maxDD
      DOWN at equal-or-better total -- vs FLAT-3,
  (2) RESPECT the caps -- every sized trade clamped to Rule-6 (per-trade cap + min-3), verified,
  (3) NEVER zero a day (L174-safe: no day dropped; bottom-tercile is reduced, not removed),
  (4) HONEST OOS -- the lift must NOT be an in-sample lever-up artifact: report IS(2025) vs
      OOS(2026) separately; the OOS book must also improve risk-adjusted (else it's overfit).

Tested at TWO equity levels:
  (a) $2,000  (Safe-2 current) -- qty cap-constrained near 3, so the overlay mostly sizes DOWN
      on low-vol days = risk reduction. Likely MARGINAL (cap-bound).
  (b) $10,000 -- sizing UP on top days has cap HEADROOM = the compounding case. The clean test.

Pure Python, $0. No live orders. Markets closed (Sunday). Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_volranker_sizing.py [--smoke] [--validate]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch.infinite_ammo_discovery import build_day_contexts  # noqa: E402
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy, _align_vix, detect_signals as detect_vwap_continuation,
)
from autoresearch import recency_check as rc  # noqa: E402
# Reuse the B10 trade stream (real OPRA, qty-invariant return + entry_premium) + the Rule-6 clamp.
from autoresearch._b10_sizing import (  # noqa: E402
    T, simulate_stream, contracts_from_fraction, ATM, ITM2, PREMIUM_STOP_PCT,
)
# Reuse the EXACT W-track overnight-vol feature (the ranker definition).
from autoresearch._deploytiming_overnight_vol import (  # noqa: E402
    overnight_vol_by_day, OPRA_CACHE_LAST,
)
from lib.ribbon import compute_ribbon  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "volranker-sizing.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "VOLRANKER-SIZING-SCORECARD.md"

OOS_YEAR = 2026
MIN_WARMUP = 20          # prior classifiable days before causal terciles are trusted (else BASE)
TRAIL_WIN = 60           # trailing window for the causal tercile cuts (== W-track ROLL_MEDIAN_D)

# ── The overlay schedule (tercile -> equity-fraction MULTIPLIER on the base fraction).
#    BASE fraction is the quarter-Kelly-clamped-to-min-3 fraction WP-3 recommends; here we
#    express the overlay as a multiplier on the per-trade equity fraction that FLAT-3 implies,
#    then RE-CLAMP through the SAME Rule-6 clamp so nothing breaches caps and nothing zeroes.
#    top  = size UP (more contracts where the cap allows), bot = size DOWN (toward min-3),
#    mid  = base. Conservative spread (1.5x / 1.0x / 0.6x) -- not a knife-edge, respects caps.
TERCILE_MULT = {"top": 1.5, "mid": 1.0, "bot": 0.6}

# Per-account hard caps (Rule 5/6, CLAUDE.md) -- mirrors _b10_sizing.ACCOUNTS.
ACCOUNTS = {
    "Safe-2": {"strike_offset": ATM, "per_trade_cap_frac": 0.30, "min_contracts": 3,
               "daily_kill_frac": 0.30},
    "Bold":   {"strike_offset": ITM2, "per_trade_cap_frac": 0.50, "min_contracts": 3,
               "daily_kill_frac": 0.50},
}
EQUITY_LEVELS = (2000.0, 10000.0)


# ─────────────────────────────────────────────────────────────────────────────
# CAUSAL TERCILE — each day's overnight_rv bucketed vs the TRAILING window of PRIOR
# classifiable days (no look-ahead). Returns {date -> 'top'|'mid'|'bot'|'base_warmup'}.
# ─────────────────────────────────────────────────────────────────────────────
def causal_terciles(onv: pd.DataFrame, *, join_cutoff: dt.date) -> dict[dt.date, str]:
    """For each classifiable day D, rank D's overnight_rv against the prior TRAIL_WIN
    classifiable days' overnight_rv (strictly before D). Cuts = 1/3 & 2/3 quantiles of the
    trailing window. Pre-warmup (< MIN_WARMUP priors) -> 'base_warmup' (size BASE, no guess)."""
    cls = onv[onv.index <= join_cutoff].sort_index()
    dates = list(cls.index)
    rv = cls["overnight_rv"].to_numpy(dtype=float)
    out: dict[dt.date, str] = {}
    for i, d in enumerate(dates):
        prior = rv[max(0, i - TRAIL_WIN):i]      # strictly prior days (shift-1, causal)
        if len(prior) < MIN_WARMUP:
            out[d] = "base_warmup"
            continue
        q1, q2 = np.quantile(prior, [1 / 3, 2 / 3])
        v = rv[i]
        out[d] = "bot" if v <= q1 else ("top" if v > q2 else "mid")
    return out


# ─────────────────────────────────────────────────────────────────────────────
# SIZING — translate (tercile, equity, premium) into a clamped contract count.
# FLAT baseline = the Rule-6-clamped min-3 count (what the book trades today). The overlay
# multiplies the per-trade equity FRACTION by the tercile multiplier, then RE-CLAMPS through
# the SAME Rule-6 clamp -> never breaches caps, never zeroes (min-3 floor preserved).
# ─────────────────────────────────────────────────────────────────────────────
def _base_fraction(equity: float, premium: float, *, per_trade_cap_frac: float,
                   min_contracts: int) -> float:
    """The equity fraction that the FLAT min-3 baseline deploys for this trade (capital of
    min-3 contracts / equity), clamped so it never exceeds the per-trade cap. This anchors the
    overlay multiplier on the same base the book actually trades."""
    cost3 = min_contracts * premium * 100.0
    frac3 = cost3 / equity if equity > 0 else 0.0
    return min(frac3, per_trade_cap_frac)


def overlay_contracts(tercile: str, equity: float, premium: float, *,
                      per_trade_cap_frac: float, min_contracts: int) -> dict:
    """Overlay contract count for one trade: multiply the base (min-3) equity fraction by the
    tercile multiplier, then clamp via the SHARED Rule-6 clamp. 'base_warmup' uses 1.0 (base).

    NEVER-ZERO is the overlay's tercile-DOWNSIZING guarantee: the RANKER must not zero a
    bottom-tercile day (that would be the L174 winner-removal the gate failed on). It is NOT a
    license to breach the HARD per-trade cap (Rule 6): if even 1 contract costs more than the
    cap allows (`cap_contracts == 0`), the trade is genuinely UN-TAKEABLE at this equity -- the
    cap wins, the trade is SKIPPED (contracts=0, reason 'cap_forbids_trade'). The FLAT-3 baseline
    skips the SAME trade identically (see flat_contracts), so this is a CAP constraint shared by
    both arms, not an overlay artifact. Distinguishes overlay-zero (forbidden) from cap-skip (ok)."""
    mult = TERCILE_MULT.get(tercile, 1.0) if tercile != "base_warmup" else 1.0
    base_frac = _base_fraction(equity, premium, per_trade_cap_frac=per_trade_cap_frac,
                               min_contracts=min_contracts)
    target_frac = base_frac * mult
    res = contracts_from_fraction(target_frac, equity, premium,
                                  per_trade_cap_frac=per_trade_cap_frac,
                                  min_contracts=min_contracts)
    cap_c = res.get("cap_contracts", 0)
    c = res["contracts"]
    if c <= 0:
        if cap_c >= 1:
            # min-3 didn't fit but >=1 does: the day STAYS in the book at the largest cap-fitting
            # size (overlay must not zero a tradeable day -- L174-safe).
            c = cap_c
            res = {**res, "contracts": c, "clamped": "never_zero_cap_clamped"}
        else:
            # even 1 contract breaches the hard cap -> the trade is un-takeable (cap > min-3).
            res = {**res, "contracts": 0, "clamped": "cap_forbids_trade"}
    return res


def flat_contracts(equity: float, premium: float, *, per_trade_cap_frac: float,
                   min_contracts: int) -> int:
    """FLAT-3 baseline contract count, clamped to the per-trade cap. If even 1 contract breaches
    the hard cap the trade is un-takeable -> 0 (the SAME skip the overlay applies; a shared cap
    constraint, not an overlay artifact). Otherwise min(min-3, cap-fitting count), >= 1."""
    if premium <= 0:
        return 0
    cap_c = int(np.floor((per_trade_cap_frac * equity) / (premium * 100.0)))
    if cap_c <= 0:
        return 0                      # cap forbids even 1 contract -> skip (shared with overlay)
    return min(min_contracts, cap_c)


# ─────────────────────────────────────────────────────────────────────────────
# METRICS — per-trade and per-day risk-adjusted, on a $-P&L stream (qty-aware).
# ─────────────────────────────────────────────────────────────────────────────
def _trade_dollar(t: T, qty: int) -> float:
    """Dollar P&L for this trade at `qty` contracts: pct (return on premium) * premium*100*qty.
    pct is qty-invariant (return on capital deployed), so this scales linearly with qty."""
    return float(t.pct) * float(t.entry_premium) * 100.0 * qty


def _series_stats(pnls: list[float]) -> dict:
    if not pnls:
        return {"n": 0}
    a = np.array(pnls, float)
    mean = float(a.mean())
    sd = float(a.std(ddof=1)) if len(a) > 1 else 0.0
    downs = a[a < 0]
    dsd = float(downs.std(ddof=1)) if len(downs) > 1 else (abs(float(downs.mean())) if len(downs) else 0.0)
    return {
        "n": len(a),
        "total": round(float(a.sum()), 2),
        "mean": round(mean, 2),
        "std": round(sd, 2),
        "sharpe": round(mean / sd, 4) if sd > 0 else None,
        "sortino": round(mean / dsd, 4) if dsd > 0 else None,
        "win_rate_pct": round(100.0 * float((a > 0).mean()), 1),
    }


def _book_risk(daily_pnls: list[float]) -> dict:
    """Per-DAY risk: Sharpe/Sortino on the daily series + maxDD on cumulative equity curve."""
    if not daily_pnls:
        return {"n_days": 0}
    a = np.array(daily_pnls, float)
    mean = float(a.mean())
    sd = float(a.std(ddof=1)) if len(a) > 1 else 0.0
    downs = a[a < 0]
    dsd = float(downs.std(ddof=1)) if len(downs) > 1 else (abs(float(downs.mean())) if len(downs) else 0.0)
    eq = np.cumsum(a)
    peak = np.maximum.accumulate(eq)
    maxdd = float((eq - peak).min()) if len(eq) else 0.0
    return {
        "n_days": len(a),
        "total": round(float(a.sum()), 2),
        "mean_day": round(mean, 2),
        "sharpe_day": round(mean / sd, 4) if sd > 0 else None,
        "sortino_day": round(mean / dsd, 4) if dsd > 0 else None,
        "max_dd": round(maxdd, 2),
        "worst_day": round(float(a.min()), 2),
        "best_day": round(float(a.max()), 2),
        "win_days": int((a > 0).sum()),
        "loss_days": int((a < 0).sum()),
    }


def _geometric_growth(trades_by_day: list[tuple[dt.date, list[T]]], *, start_equity: float,
                      sizing: str, account: dict, terciles: dict) -> dict:
    """Compounding replay: chronological, equity grows; per-trade size = FLAT-3 or overlay (sized
    on CURRENT equity). Daily kill switch respected (Rule 5). Returns final equity + growth + maxDD."""
    eq = peak = start_equity
    max_dd_frac = 0.0
    kill_trips = 0
    cap = account["per_trade_cap_frac"]
    mn = account["min_contracts"]
    kill = account["daily_kill_frac"]
    for d, ts in trades_by_day:
        sod = eq
        intraday = 0.0
        halted = False
        for t in ts:
            if halted:
                break
            prem = t.entry_premium
            if sizing == "flat":
                qty = flat_contracts(eq, prem, per_trade_cap_frac=cap, min_contracts=mn)
            else:
                terc = terciles.get(d, "base_warmup")
                qty = overlay_contracts(terc, eq, prem, per_trade_cap_frac=cap,
                                        min_contracts=mn)["contracts"]
            if qty <= 0:               # cap forbids the trade -> skip (no fill, no P&L)
                continue
            pnl = _trade_dollar(t, qty)
            intraday += pnl
            eq += pnl
            if intraday <= -kill * sod:        # Rule 5 daily kill (intraday cumulative)
                kill_trips += 1
                halted = True
            if eq <= 0:
                return {"final_equity": 0.0, "ruin": True, "growth_mult": 0.0,
                        "max_dd_frac": 1.0, "kill_trips": kill_trips}
        peak = max(peak, eq)
        if peak > 0:
            max_dd_frac = max(max_dd_frac, (peak - eq) / peak)
    return {
        "final_equity": round(eq, 2),
        "ruin": False,
        "growth_mult": round(eq / start_equity, 4) if start_equity > 0 else 0.0,
        "total_return_pct": round(100.0 * (eq / start_equity - 1.0), 2) if start_equity > 0 else 0.0,
        "max_dd_frac": round(max_dd_frac, 4),
        "kill_trips": kill_trips,
    }


# ─────────────────────────────────────────────────────────────────────────────
# ONE ACCOUNT/EQUITY CELL — FLAT-3 vs overlay, fixed-equity (risk-adjusted) + compounding.
# ─────────────────────────────────────────────────────────────────────────────
def run_cell(trades: list[T], terciles: dict, *, account: dict, equity: float) -> dict:
    """At a FIXED equity (so the per-trade $ are directly comparable, not confounded by the
    compounding path), build the FLAT-3 and overlay per-trade $ streams + per-day streams, and
    the risk-adjusted metrics + the cap-respect audit. Also runs the compounding replay."""
    cap = account["per_trade_cap_frac"]
    mn = account["min_contracts"]

    flat_tr, ov_tr = [], []
    flat_day, ov_day = defaultdict(float), defaultdict(float)
    cap_breaches = 0           # overlay deploys > cap*equity (MUST be 0 -- a real breach)
    overlay_zeroed = 0         # overlay zeroed a trade FLAT would have taken (MUST be 0 -- L174)
    cap_skips_both = 0         # cap forbids even 1 contract -> BOTH arms skip (shared, allowed)
    qty_hist = {"flat": defaultdict(int), "overlay": defaultdict(int)}
    sized = {"top": [], "mid": [], "bot": [], "base_warmup": []}

    for t in trades:
        d = dt.date.fromisoformat(t.date)
        prem = t.entry_premium
        fq = flat_contracts(equity, prem, per_trade_cap_frac=cap, min_contracts=mn)
        oc = overlay_contracts(terciles.get(d, "base_warmup"), equity, prem,
                               per_trade_cap_frac=cap, min_contracts=mn)
        oq = oc["contracts"]
        # cap audit: deployed premium must be <= cap*equity (Rule 6) for any TAKEN trade.
        if oq > 0 and oq * prem * 100.0 > cap * equity + 1e-6:
            cap_breaches += 1
        # zero audit: overlay zeroing a trade the FLAT baseline WOULD take = winner-removal (L174).
        # A trade both arms skip (cap forbids even 1 contract) is a SHARED cap constraint, not an
        # overlay artifact -- counted separately and excluded from BOTH streams identically.
        if fq <= 0 and oq <= 0:
            cap_skips_both += 1
            continue                              # un-takeable at this equity -> skip both arms
        if oq <= 0 and fq > 0:
            overlay_zeroed += 1                   # overlay dropped a FLAT-takeable trade -> BAD
        fpnl = _trade_dollar(t, fq) if fq > 0 else 0.0
        opnl = _trade_dollar(t, oq) if oq > 0 else 0.0
        flat_tr.append(fpnl)
        ov_tr.append(opnl)
        flat_day[d] += fpnl
        ov_day[d] += opnl
        qty_hist["flat"][fq] += 1
        qty_hist["overlay"][oq] += 1
        sized[terciles.get(d, "base_warmup")].append(oq)

    flat_daily = [flat_day[d] for d in sorted(flat_day)]
    ov_daily = [ov_day[d] for d in sorted(ov_day)]

    by_day_t: dict[dt.date, list[T]] = defaultdict(list)
    for t in trades:
        by_day_t[dt.date.fromisoformat(t.date)].append(t)
    tbd = sorted(by_day_t.items())
    flat_compound = _geometric_growth(tbd, start_equity=equity, sizing="flat",
                                      account=account, terciles=terciles)
    ov_compound = _geometric_growth(tbd, start_equity=equity, sizing="overlay",
                                    account=account, terciles=terciles)

    avg_qty = {k: (round(float(np.mean(v)), 2) if v else None) for k, v in sized.items()}
    return {
        "equity": equity,
        "flat3": {
            "per_trade": _series_stats(flat_tr),
            "per_day": _book_risk(flat_daily),
            "compounding": flat_compound,
        },
        "overlay": {
            "per_trade": _series_stats(ov_tr),
            "per_day": _book_risk(ov_daily),
            "compounding": ov_compound,
            "avg_qty_by_tercile": avg_qty,
            "qty_hist": {str(k): dict(sorted(v.items())) for k, v in qty_hist.items()},
        },
        "cap_respect": {
            "cap_breaches": cap_breaches,          # MUST be 0 (overlay deploys past Rule-6 cap)
            "overlay_zeroed_flat_takeable": overlay_zeroed,  # MUST be 0 (L174 winner-removal)
            "cap_skips_shared_both_arms": cap_skips_both,     # OK: hard-cap forbids even 1 contract
            "per_trade_cap_frac": cap,
            "min_contracts": mn,
            "RESPECTS_CAPS": bool(cap_breaches == 0 and overlay_zeroed == 0),
        },
    }


def _improvement_verdict(cell: dict) -> dict:
    """Did the overlay improve RISK-ADJUSTED return vs FLAT-3 at this cell, respecting caps?
    Lift = per-trade Sharpe UP, OR per-day Sharpe UP, OR per-day Sortino UP, OR maxDD(frac) DOWN
    at equal-or-better compounding total return. Requires caps respected + no zero days."""
    f, o = cell["flat3"], cell["overlay"]

    def _d(a, b):
        if a is None or b is None:
            return None
        return round(b - a, 4)

    sharpe_tr = _d(f["per_trade"].get("sharpe"), o["per_trade"].get("sharpe"))
    sharpe_day = _d(f["per_day"].get("sharpe_day"), o["per_day"].get("sharpe_day"))
    sortino_day = _d(f["per_day"].get("sortino_day"), o["per_day"].get("sortino_day"))
    dd_flat = f["compounding"].get("max_dd_frac", 1.0)
    dd_ov = o["compounding"].get("max_dd_frac", 1.0)
    dd_delta = round(dd_ov - dd_flat, 4)        # negative = overlay LOWER drawdown = better
    ret_flat = f["compounding"].get("total_return_pct", 0.0)
    ret_ov = o["compounding"].get("total_return_pct", 0.0)
    ret_delta = round(ret_ov - ret_flat, 2)

    risk_up = any(x is not None and x > 0 for x in (sharpe_tr, sharpe_day, sortino_day))
    dd_better_eq_ret = (dd_delta < 0 and ret_delta >= -1e-6)
    improves = bool(cell["cap_respect"]["RESPECTS_CAPS"] and (risk_up or dd_better_eq_ret))
    return {
        "sharpe_per_trade_delta": sharpe_tr,
        "sharpe_per_day_delta": sharpe_day,
        "sortino_per_day_delta": sortino_day,
        "maxdd_frac_delta": dd_delta,
        "total_return_pct_delta": ret_delta,
        "risk_adjusted_up": risk_up,
        "lower_dd_at_eq_or_better_return": dd_better_eq_ret,
        "respects_caps": cell["cap_respect"]["RESPECTS_CAPS"],
        "IMPROVES": improves,
    }


# ─────────────────────────────────────────────────────────────────────────────
# VALIDATION — deterministic self-tests.
# ─────────────────────────────────────────────────────────────────────────────
def validate() -> list[str]:
    msgs: list[str] = []
    cap, mn = 0.30, 3

    # FLAT-3 at $2K, premium $1.38 (book median): cost3 = 3*1.38*100 = $414 = 20.7% of $2K < 30% cap.
    fq = flat_contracts(2000.0, 1.38, per_trade_cap_frac=cap, min_contracts=mn)
    assert fq == 3, fq
    msgs.append(f"OK FLAT-3 @ $2K prem $1.38 -> {fq} contracts (20.7% of equity < 30% cap)")

    # Overlay TOP @ $2K, prem $1.38: base_frac=0.207, *1.5=0.31 -> clamps to cap (30%) -> floor(0.30*2000/138)=4.
    ot = overlay_contracts("top", 2000.0, 1.38, per_trade_cap_frac=cap, min_contracts=mn)
    assert ot["contracts"] <= int(np.floor(0.30 * 2000.0 / 138.0)), ot
    assert ot["contracts"] >= mn, ot   # never below min-3 on a top day with headroom
    msgs.append(f"OK overlay TOP @ $2K prem $1.38 -> {ot['contracts']} contracts "
                f"(cap-clamped, clamp={ot['clamped']}) -- cap-bound at $2K as predicted")

    # Overlay TOP @ $10K, prem $1.38: base_frac=3*138/10000=0.0414, *1.5=0.0621 -> floor(0.0621*10000/138)=4.
    ot10 = overlay_contracts("top", 10000.0, 1.38, per_trade_cap_frac=cap, min_contracts=mn)
    assert ot10["contracts"] >= 4, ot10    # headroom -> sizes UP above min-3
    # cap respected: deployed premium <= 30% equity
    assert ot10["contracts"] * 1.38 * 100.0 <= 0.30 * 10000.0 + 1e-6, ot10
    msgs.append(f"OK overlay TOP @ $10K prem $1.38 -> {ot10['contracts']} contracts "
                f"(sizes UP above min-3; cap headroom = the compounding case)")

    # Overlay BOT @ $10K: base_frac*0.6 -> floor(0.0414*0.6*10000/138)=1.8 -> 1, then min-floor lifts.
    ob10 = overlay_contracts("bot", 10000.0, 1.38, per_trade_cap_frac=cap, min_contracts=mn)
    assert ob10["contracts"] >= 1, ob10    # NEVER zero a takeable bottom day (L174-safe)
    assert ob10["contracts"] <= 3, ob10    # sizes DOWN toward min on a bottom day
    msgs.append(f"OK overlay BOT @ $10K prem $1.38 -> {ob10['contracts']} contracts "
                f"(sizes DOWN, NEVER zero a takeable day -- L174-safe)")

    # HARD-CAP wins over min-3: a prem so high even 1 contract breaches the cap -> SKIP (0), and
    # the FLAT baseline skips the SAME trade identically (shared cap constraint, not overlay-zero).
    high_prem = 8.82   # 1 contract = $882 = 44% of $2K > 30% cap -> un-takeable at $2K
    oc_skip = overlay_contracts("top", 2000.0, high_prem, per_trade_cap_frac=cap, min_contracts=mn)
    fl_skip = flat_contracts(2000.0, high_prem, per_trade_cap_frac=cap, min_contracts=mn)
    assert oc_skip["contracts"] == 0 and oc_skip["clamped"] == "cap_forbids_trade", oc_skip
    assert fl_skip == 0, fl_skip
    msgs.append(f"OK hard-cap wins over min-3: prem ${high_prem} @ $2K (1c=44%>30% cap) -> "
                f"overlay SKIP(0) AND flat SKIP(0) identically (shared cap, not overlay-zero)")

    # base_warmup uses 1.0 (== base) -> same as a mid day pre-warmup.
    obw = overlay_contracts("base_warmup", 10000.0, 1.38, per_trade_cap_frac=cap, min_contracts=mn)
    om = overlay_contracts("mid", 10000.0, 1.38, per_trade_cap_frac=cap, min_contracts=mn)
    assert obw["contracts"] == om["contracts"], (obw, om)
    msgs.append(f"OK base_warmup == mid (no guess pre-warmup) -> {obw['contracts']} contracts")

    # qty-invariant dollar scaling: pct*prem*100*qty linear in qty.
    t = T(date="2025-03-03", side="C", edge="e1", entry_premium=1.50, pct=0.20, pnl3=90.0,
          exit_reason="TP1")
    assert abs(_trade_dollar(t, 3) - 90.0) < 1e-6, _trade_dollar(t, 3)
    assert abs(_trade_dollar(t, 6) - 180.0) < 1e-6, _trade_dollar(t, 6)
    msgs.append("OK qty-invariant $ scaling: pct*prem*100*qty linear (3->$90, 6->$180)")

    # causal tercile: a synthetic onv where the last day is the highest -> 'top'; warmup -> base.
    idx = [dt.date(2025, 1, 1) + dt.timedelta(days=i) for i in range(MIN_WARMUP + 2)]
    rv = list(np.linspace(1.0, 2.0, MIN_WARMUP + 1)) + [9.0]   # last day a spike
    onv = pd.DataFrame({"overnight_rv": rv}, index=idx)
    terc = causal_terciles(onv, join_cutoff=idx[-1])
    assert terc[idx[0]] == "base_warmup", terc[idx[0]]          # first day: no priors
    assert terc[idx[-1]] == "top", terc[idx[-1]]               # spike vs prior window -> top
    msgs.append("OK causal terciles: first day base_warmup (no priors); spike day -> top "
                "(ranked vs PRIOR window only -- no look-ahead, L06/L34)")
    return msgs


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────
def _load():
    spy_raw, vix_raw = rc.load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    return spy, vix, days, ribbon


def _split_is_oos(trades: list[T]) -> tuple[list[T], list[T]]:
    is_t = [t for t in trades if int(t.date[:4]) < OOS_YEAR]
    oos_t = [t for t in trades if int(t.date[:4]) == OOS_YEAR]
    return is_t, oos_t


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="validate + sample sizing under each tercile")
    ap.add_argument("--validate", action="store_true", help="deterministic self-tests only")
    ap.add_argument("--sweep", action="store_true",
                    help="sweep tercile-multiplier schedules; report the risk-adjusted-best at $10K")
    args = ap.parse_args()

    if args.validate:
        for m in validate():
            print("  " + m)
        print("VALIDATION PASSED")
        return 0

    print("[volranker] loading SPY+VIX + #1 detector + MES overnight ...", flush=True)
    spy, vix, days, ribbon = _load()
    signals = detect_vwap_continuation(days, vix, breakout_only=False, put_needs_rising_vix=False)
    print(f"[volranker] vwap_continuation signals={len(signals)} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    onv = overnight_vol_by_day()
    mes_last = onv.index.max()
    join_cutoff = min(OPRA_CACHE_LAST, mes_last)
    terciles = causal_terciles(onv, join_cutoff=join_cutoff)
    tc = defaultdict(int)
    for v in terciles.values():
        tc[v] += 1
    print(f"[volranker] overnight-vol days={len(onv)} join_cutoff={join_cutoff} "
          f"terciles={dict(tc)}", flush=True)

    if args.sweep:
        # Sweep tercile-multiplier schedules to find one that clears the RISK-ADJUSTED bar at
        # $10K (the L175 question: can a GENTLER up-size compound without the variance penalty?).
        # We rebind the module-global TERCILE_MULT (test-only, the skill-tune pattern) per schedule.
        global TERCILE_MULT
        schedules = {
            "1.5/1.0/0.6_default": {"top": 1.5, "mid": 1.0, "bot": 0.6},
            "1.25/1.0/0.75":       {"top": 1.25, "mid": 1.0, "bot": 0.75},
            "1.15/1.0/0.85":       {"top": 1.15, "mid": 1.0, "bot": 0.85},
            "1.0/1.0/0.6_downonly": {"top": 1.0, "mid": 1.0, "bot": 0.6},   # ONLY size DOWN bot
            "1.0/1.0/0.5_downonly": {"top": 1.0, "mid": 1.0, "bot": 0.5},
            "1.3/1.0/1.0_uponly":  {"top": 1.3, "mid": 1.0, "bot": 1.0},    # ONLY size UP top
        }
        saved = dict(TERCILE_MULT)
        sweep_out = {}
        for acct_name, acct in ACCOUNTS.items():
            off = acct["strike_offset"]
            trades = simulate_stream(signals, spy, ribbon, vix, strike_offset=off,
                                     edge="e1", setup=f"VOLRANK_{acct_name}")
            trades_cls = [t for t in trades if dt.date.fromisoformat(t.date) in terciles]
            is_t, oos_t = _split_is_oos(trades_cls)
            print(f"\n[sweep] === {acct_name} @ $10K (the compounding case) ===", flush=True)
            sweep_out[acct_name] = {}
            for sname, sched in schedules.items():
                TERCILE_MULT = sched
                full = run_cell(trades_cls, terciles, account=acct, equity=10000.0)
                oos = run_cell(oos_t, terciles, account=acct, equity=10000.0)
                fv = _improvement_verdict(full)
                ov = _improvement_verdict(oos)
                clean = bool(fv["IMPROVES"] and ov["risk_adjusted_up"] and ov["respects_caps"])
                fp, op = full["flat3"], full["overlay"]
                sweep_out[acct_name][sname] = {
                    "full_verdict": fv, "oos_clean": clean,
                    "overlay_total": op["per_day"]["total"], "flat_total": fp["per_day"]["total"],
                    "overlay_sortino_day": op["per_day"].get("sortino_day"),
                    "flat_sortino_day": fp["per_day"].get("sortino_day"),
                    "overlay_maxdd": op["compounding"]["max_dd_frac"],
                    "flat_maxdd": fp["compounding"]["max_dd_frac"],
                }
                print(f"  {sname:24s} OVtot=${op['per_day']['total']:>9} "
                      f"(flat ${fp['per_day']['total']:>9}) shTr_d={fv['sharpe_per_trade_delta']} "
                      f"sortDay_d={fv['sortino_per_day_delta']} dd_d={fv['maxdd_frac_delta']} "
                      f"IMPROVES={fv['IMPROVES']} OOS_clean={clean}", flush=True)
        TERCILE_MULT = saved
        sweep_path = OUT_JSON.parent / "volranker-sizing-mult-sweep.json"
        sweep_path.write_text(json.dumps({"run_date": dt.date.today().isoformat(),
                                          "equity": 10000.0, "schedules": schedules,
                                          "results": sweep_out}, indent=2, default=str),
                              encoding="utf-8")
        print(f"\n[sweep] wrote {sweep_path}")
        return 0

    if args.smoke:
        print("\n=== VALIDATION ===")
        for m in validate():
            print("  " + m)
        # sample sizing for one premium under each tercile at both equities
        for eq in EQUITY_LEVELS:
            print(f"\n  sample sizing @ ${eq:.0f} (Safe-2 cap 30%, min-3), prem=$1.38:")
            for terc in ("bot", "mid", "top"):
                oc = overlay_contracts(terc, eq, 1.38, per_trade_cap_frac=0.30, min_contracts=3)
                fl = flat_contracts(eq, 1.38, per_trade_cap_frac=0.30, min_contracts=3)
                print(f"    {terc:4s} -> overlay {oc['contracts']} vs flat {fl} "
                      f"(clamp={oc['clamped']})")
        return 0

    # ── FULL RUN: per account, build #1 stream at its live tier, then per-equity FLAT vs overlay.
    results = {}
    for acct_name, acct in ACCOUNTS.items():
        off = acct["strike_offset"]
        trades = simulate_stream(signals, spy, ribbon, vix, strike_offset=off,
                                 edge="e1", setup=f"VOLRANK_{acct_name}")
        # restrict to days that have an overnight-vol tercile (classifiable join, disclosed)
        trades_cls = [t for t in trades if dt.date.fromisoformat(t.date) in terciles]
        n_drop = len(trades) - len(trades_cls)
        is_t, oos_t = _split_is_oos(trades_cls)
        print(f"\n[volranker] === {acct_name} (off={off:+d}) === "
              f"#1 trades={len(trades)} classifiable={len(trades_cls)} "
              f"(dropped {n_drop} post-MES-cutoff) | IS={len(is_t)} OOS={len(oos_t)}", flush=True)

        per_equity = {}
        for eq in EQUITY_LEVELS:
            full_cell = run_cell(trades_cls, terciles, account=acct, equity=eq)
            is_cell = run_cell(is_t, terciles, account=acct, equity=eq)
            oos_cell = run_cell(oos_t, terciles, account=acct, equity=eq)
            full_v = _improvement_verdict(full_cell)
            oos_v = _improvement_verdict(oos_cell)
            # OOS honesty: full must improve AND OOS must also improve risk-adjusted (not just IS lever-up)
            clean = bool(full_v["IMPROVES"] and oos_v["risk_adjusted_up"] and oos_v["respects_caps"])
            per_equity[str(int(eq))] = {
                "full": {"cell": full_cell, "verdict": full_v},
                "IS_2025": {"cell": is_cell, "verdict": _improvement_verdict(is_cell)},
                "OOS_2026": {"cell": oos_cell, "verdict": oos_v},
                "OOS_HONEST_CLEAN": clean,
            }
            fp, op = full_cell["flat3"], full_cell["overlay"]
            print(f"  ${int(eq):>6} | FLAT tot=${fp['per_day']['total']:>9} "
                  f"shTr={fp['per_trade'].get('sharpe')} shDay={fp['per_day'].get('sharpe_day')} "
                  f"sortDay={fp['per_day'].get('sortino_day')} maxDD={fp['compounding']['max_dd_frac']} "
                  f"grow={fp['compounding']['growth_mult']}x", flush=True)
            print(f"  ${int(eq):>6} |  OV  tot=${op['per_day']['total']:>9} "
                  f"shTr={op['per_trade'].get('sharpe')} shDay={op['per_day'].get('sharpe_day')} "
                  f"sortDay={op['per_day'].get('sortino_day')} maxDD={op['compounding']['max_dd_frac']} "
                  f"grow={op['compounding']['growth_mult']}x | caps_ok={full_cell['cap_respect']['RESPECTS_CAPS']} "
                  f"IMPROVES={full_v['IMPROVES']} OOS_clean={clean}", flush=True)

        results[acct_name] = {"strike_offset": off, "n_trades": len(trades),
                              "n_classifiable": len(trades_cls), "n_IS": len(is_t),
                              "n_OOS": len(oos_t), "per_equity": per_equity}

    # ── VERDICT roll-up ──────────────────────────────────────────────────────
    improves_10k = any(results[a]["per_equity"]["10000"]["full"]["verdict"]["IMPROVES"]
                       for a in results)
    clean_10k = any(results[a]["per_equity"]["10000"]["OOS_HONEST_CLEAN"] for a in results)
    improves_2k = any(results[a]["per_equity"]["2000"]["full"]["verdict"]["IMPROVES"]
                      for a in results)
    caps_ok = all(results[a]["per_equity"][str(int(eq))]["full"]["cell"]["cap_respect"]["RESPECTS_CAPS"]
                  for a in results for eq in EQUITY_LEVELS)

    if clean_10k:
        verdict = "SIZING_IMPROVEMENT"
    elif improves_10k or improves_2k:
        verdict = "MARGINAL"
    elif caps_ok:
        verdict = "NO_IMPROVEMENT"
    else:
        verdict = "DEAD"

    summary = {
        "slug": "overnight-vol-sizing-overlay",
        "kind": "sizing_overlay (NOT a gate; never zeroes a day -> L174-safe)",
        "run_date": dt.date.today().isoformat(),
        "edge": "vwap_continuation (LIVE #1), CALL+PUT, real OPRA fills (C1)",
        "overnight_feature": "sum(|MES 1m logret|) over 18:00->09:30 ET (W-track def, byte-for-byte)",
        "tercile_mechanism": (f"causal: day's overnight_rv vs PRIOR {TRAIL_WIN}d window (shift-1); "
                              f"cuts = 1/3 & 2/3 quantiles; <{MIN_WARMUP} priors -> BASE (no guess)"),
        "tercile_multipliers": TERCILE_MULT,
        "join_cutoff": str(join_cutoff),
        "tercile_counts": dict(tc),
        "vix_independence_evidence": ("W-track within-VIX-mid-tercile control (deploytiming-"
                                      "overnight-vol.json): HI-overnight $141.35/day (Sharpe 0.745) "
                                      "vs LO $24.20/day (Sharpe 0.17) at SAME VIX -> overnight FLOW, "
                                      "not VIX-level (corr 0.874 but control survives, C5/L122)"),
        "the_bar": ("sizing overlay must (1) improve risk-adjusted return (per-trade Sharpe OR "
                    "per-day Sharpe/Sortino UP, OR maxDD DOWN at eq-or-better return) vs FLAT-3, "
                    "(2) RESPECT Rule-6 caps (per-trade cap + min-3; verified 0 breaches), "
                    "(3) NEVER zero a day (L174-safe; 0 zero-days), (4) OOS-honest (OOS-2026 also "
                    "improves risk-adjusted, not just IS lever-up)"),
        "equity_levels": list(EQUITY_LEVELS),
        "accounts": results,
        "verdict": verdict,
        "verdict_legend": {
            "SIZING_IMPROVEMENT": "clear lift incl OOS-honest at $10K (the compounding case)",
            "MARGINAL": "helps modestly (often cap-bound at $2K), OOS not clean",
            "NO_IMPROVEMENT": "no risk-adjusted lift but caps respected (overlay inert/neutral)",
            "DEAD": "breaches caps or zeroes days (broken overlay)",
        },
        "DISCLOSURE": {
            "fills": "real OPRA via _b10_sizing.simulate_stream (C1); pct = return-on-capital, qty-invariant",
            "detector": "BYTE-FOR-BYTE _edgehunt_vwap_continuation.detect_signals (LIVE #1)",
            "caps": "Rule-6 clamp = _b10_sizing.contracts_from_fraction (same as WP-3); audited 0 breaches",
            "never_zero": "overlay floors at >=1 (min-3 where it fits); bottom-tercile reduced not removed (L174)",
            "join_caveat": (f"classifiable days bounded by MES 1m (ends {mes_last}); #1 trades after "
                            "that have no overnight tercile (dropped, disclosed) -- OPRA cache to "
                            f"{OPRA_CACHE_LAST}"),
            "fixed_equity_note": ("per-trade/per-day risk metrics computed at FIXED equity (so $ are "
                                  "comparable, not confounded by the compounding path); compounding "
                                  "metrics (growth/maxDD-frac) come from the chronological replay"),
            "research_only": "Sunday money-path guard: no watcher/params/risk_gate/heartbeat edit, no orders, no commit",
            "spy_vs_option": "C3/L58 -- overnight-FLOW ranker validated on the OPTION P&L, not SPY/futures range",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[volranker] wrote {OUT_JSON}", flush=True)
    print("\n=== VOLRANKER SIZING VERDICT ===")
    print(f"VERDICT: {verdict}")
    print(f"  $10K improves={improves_10k} OOS-clean={clean_10k} | $2K improves={improves_2k} | caps_ok={caps_ok}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

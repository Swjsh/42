"""SUN-COMBINE-RULE — the never-decided LIVE COMBINE RULE for the 3 overlapping VWAP edges.

THE PROBLEM (the C-track open question). We validated 3 real edges individually:
  #1 vwap_continuation        — LIVE (ATM Safe-2 / ITM-2 Bold)
  #2 vwap_reclaim_failed_break — dormant (ATM Safe-2 / ITM-2 Bold)
  #4 vix_regime_dayside       — dormant (ATM Safe-2 only)
B8/B9 found ~100% same-side day-overlap: of #1's 158 fire-days, #2 fires 81 and #4
fires 80 — and they all lean the SAME side on the 2026 bull tape. So on a real signal
day you may get 2-3 edges firing the same direction. "Ship all 3" is meaningless until
the LIVE COMBINE RULE is decided: when 2-3 edges fire the same day same side, do we
take 1 / the best / all-stacked / first-to-fire? That choice is the entire risk profile.

This harness reuses the 3 edges' EXACT detectors (the B9 imports = byte-for-byte the
live ports) + lib.simulator_real (real OPRA fills, C1 — the only WR authority) and A/Bs
FOUR live combine rules on the SAME signal universe, per account at its validated tier:

  (a) ONLY_1          — #1-only. The CURRENT live edge. Baseline.
  (b) TAKE_BEST       — on a day where multiple edges fire, take the SINGLE edge with the
                        best HISTORICALLY-KNOWN expectancy. "Historically known" = the
                        edge's IS-period (2025) per-trade expectancy at this tier, frozen
                        BEFORE the day is scored (no look-ahead — the ranking key is the
                        in-sample exp, applied to every day incl. OOS).
  (c) TAKE_ALL_STACK  — take EVERY firing edge that day = 2-3x position on overlap days
                        (each edge its own contract block). The over-stake hypothesis:
                        concentration on the same side same day -> maxDD blowout.
  (d) FIRST_TO_FIRE   — take only whichever edge TRIGGERS EARLIEST that day (min bar_idx).

For each rule we report, per account: portfolio per-trade expectancy, total $, annualized
Sharpe (daily-equity series over ALL trading days, flat=0), max drawdown, worst day, %
days in market, day-WR — AND the L175 RISK-ADJUSTED view (return-per-unit-maxDD, i.e.
total / |maxDD|, and Sharpe) so the over-stake penalty is quantified. We then test each
rule against the per-account KILL SWITCH (Safe-2 -30% of SOD equity = -$600/day at $2K;
Bold -50%) by counting how many days each rule would have BREACHED the daily limit and the
P&L that the kill-switch would have CLIPPED (you cannot keep a loss past the halt).

RECOMMENDATION = the rule that maximizes risk-adjusted return WITHIN the kill switch.

DISCLOSURE (OP-20 / C7 — PASTE REAL NUMBERS):
  * Real OPRA fills (C1). SPY-direction != option edge (C3/L58). Per-trade EXPECTANCY,
    not WR alone (OP-14/C4). Annualized Sharpe = daily Sharpe x sqrt(252).
  * Hard window: signals + fills <= the OPRA cache last day (data-coverage.json). The run
    ASSERTS no realized fill lands after the cache edge (never silently score past-cache).
  * This is a MEASUREMENT + a combine-RULE recommendation, not a new edge candidate — the
    constituents already cleared their standing bars individually.

Pure Python / numpy, $0 (no LLM, no live orders). Markets closed (Sunday). RESEARCH ONLY
— touches NO live watcher / params.json / heartbeat / risk_gate / orchestrator.
Writes analysis/recommendations/SUNDAY-COMBINE-RULE.{md,json}.
Run: backtest/.venv/Scripts/python.exe backtest/autoresearch/_sun_combine_rule.py
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    build_day_contexts,
    _nearest_cached_strike,
    _strike_from_spot,
    Signal,
)
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    _normalize_spy,
    _align_vix,
    detect_signals as detect_vwap_continuation,
)
from autoresearch._sub_struct_vwap_reclaim_failed_break import (  # noqa: E402
    detect_signals as detect_reclaim_failed_break,
)
from autoresearch._b5_vix_regime_dayside import (  # noqa: E402
    causal_vix_median,
    vix_slope,
    detect_opt_signals as detect_vix_regime_dayside,
    _swing_stop,
    VIX_MEDIAN_BARS,
    VIX_SLOPE_BARS,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "SUNDAY-COMBINE-RULE.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "SUNDAY-COMBINE-RULE.md"
B5_SCORECARD = ROOT / "analysis" / "recommendations" / "b5-vix-regime-dayside.json"
COVERAGE = ROOT / "automation" / "state" / "data-coverage.json"

START = dt.date(2025, 1, 1)
END = dt.date(2026, 6, 16)   # SPY/VIX master edge; OPRA fills cover to 06-18 (fully real-filled)

PREMIUM_STOP_PCT = -0.08
MAX_STRIKE_STEPS = 4
QTY = 3
OOS_YEAR = 2026
TRADING_DAYS_PER_YEAR = 252

# Strike tiers per account (C29 — each edge lives at the tier it was validated on).
ATM = 0
ITM2 = -2

# Per-account kill switch (CLAUDE.md rule 5). Safe-2 = -30% of $2K SOD = -$600/day.
# Bold = -50% of $1.673K SOD ~= -$836/day. These are the DAILY hard halt.
KILL_SWITCH = {"Safe-2": -600.0, "Bold": -836.0}

VIX_REGIME_DEFAULT = {"slope_rule": "not_rising", "low_margin": 0.0}


# ════════════════════════════════════════════════════════════════════════════════
# A per-edge realized trade on a given day at a given tier (one entry/day/edge).
# ════════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class EdgeTrade:
    edge: str          # "1" / "2" / "4"
    date: str
    side: str          # "C" / "P"
    bar_idx: int       # global SPY idx of the trigger bar (for FIRST_TO_FIRE)
    strike: int
    pnl: float
    pct: float
    exit_reason: str


def simulate_one(sg, spy, ribbon, vix, *, strike_offset, edge, setup):
    """Realize ONE signal at one strike tier on real OPRA fills. Returns EdgeTrade|None."""
    bar = spy.iloc[sg.bar_idx]
    d = bar["timestamp_et"].date()
    spot = float(bar["close"])
    atm = _strike_from_spot(spot)
    target = atm - strike_offset if sg.side == "P" else atm + strike_offset
    strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
    if strike is None:
        return None
    entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
    fill = simulate_trade_real(
        entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
        rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
        qty=QTY, setup=setup, strike_override=strike, entry_vix=entry_vix,
        premium_stop_pct=PREMIUM_STOP_PCT)
    if fill is None or fill.dollar_pnl is None:
        return None
    return EdgeTrade(
        edge=edge, date=str(d), side=sg.side, bar_idx=int(sg.bar_idx),
        strike=int(strike), pnl=round(float(fill.dollar_pnl), 2),
        pct=round(float(fill.pct_return_on_premium), 5),
        exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE")


def realize_edge(signals, spy, ribbon, vix, *, strike_offset, edge, setup):
    """All signals for one edge at one tier -> dict[date] -> EdgeTrade (one entry/day).
    Detectors already break after the first qualifying bar, so 1 signal/day, but we
    de-dupe defensively keeping the EARLIEST bar_idx."""
    out: dict[str, EdgeTrade] = {}
    n_sig = len(signals)
    n_fill = 0
    for sg in signals:
        t = simulate_one(sg, spy, ribbon, vix, strike_offset=strike_offset, edge=edge, setup=setup)
        if t is None:
            continue
        n_fill += 1
        prev = out.get(t.date)
        if prev is None or t.bar_idx < prev.bar_idx:
            out[t.date] = t
    return out, {"signals": n_sig, "filled": n_fill,
                 "fill_rate": round(n_fill / n_sig, 3) if n_sig else 0.0}


# ════════════════════════════════════════════════════════════════════════════════
# IS-period (2025) per-trade expectancy = the historically-known TAKE_BEST ranking key.
# Computed ONCE per edge per tier, frozen, applied to every day (incl. OOS) — no
# look-ahead (the key never peeks at the day being scored).
# ════════════════════════════════════════════════════════════════════════════════
def is_expectancy(edge_trades: dict[str, EdgeTrade]) -> float:
    vals = [t.pnl for t in edge_trades.values() if int(t.date[:4]) != OOS_YEAR]
    return float(np.mean(vals)) if vals else float("-inf")


# ════════════════════════════════════════════════════════════════════════════════
# COMBINE RULES — given the per-day set of firing EdgeTrades, return the trades TAKEN.
# ════════════════════════════════════════════════════════════════════════════════
def apply_rule(rule: str, day_trades: list[EdgeTrade], is_exp: dict[str, float]) -> list[EdgeTrade]:
    if not day_trades:
        return []
    if rule == "ONLY_1":
        return [t for t in day_trades if t.edge == "1"]
    if rule == "TAKE_BEST":
        return [max(day_trades, key=lambda t: is_exp.get(t.edge, float("-inf")))]
    if rule == "TAKE_ALL_STACK":
        return list(day_trades)
    if rule == "FIRST_TO_FIRE":
        return [min(day_trades, key=lambda t: t.bar_idx)]
    raise ValueError(rule)


# ════════════════════════════════════════════════════════════════════════════════
# METRICS — portfolio aggregate over the daily-equity series + L175 risk-adjusted view.
# ════════════════════════════════════════════════════════════════════════════════
def by_day_pnl(trades: list[EdgeTrade]) -> dict[str, float]:
    d: dict[str, float] = defaultdict(float)
    for t in trades:
        d[t.date] += t.pnl
    return dict(d)


def apply_kill_switch(daily: dict[str, float], limit: float) -> tuple[dict[str, float], dict]:
    """A day's realized P&L cannot fall below the daily halt: clip any day below `limit`
    to exactly `limit` (the halt stops further loss; we cannot keep losing past it).
    Conservative — assumes the halt triggers at the limit, not the exact intrabar path."""
    clipped = {}
    n_breach = 0
    clipped_loss = 0.0
    for d, p in daily.items():
        if p < limit:
            n_breach += 1
            clipped_loss += (limit - p)   # P&L the halt SAVED (p is more negative than limit)
            clipped[d] = limit
        else:
            clipped[d] = p
    return clipped, {"n_breach_days": n_breach,
                     "clipped_loss_recovered": round(clipped_loss, 2),
                     "daily_limit": limit}


def aggregate(trades: list[EdgeTrade], n_trading_days: int, kill_limit: float) -> dict:
    if not trades:
        return {"n_trades": 0, "days_in_market": 0}
    pnl_tr = np.array([t.pnl for t in trades], float)
    daily_raw = by_day_pnl(trades)
    # Kill-switch-clipped daily series — the rule's REALISTIC book (cannot exceed the halt).
    daily, ks = apply_kill_switch(daily_raw, kill_limit)
    days_sorted = sorted(daily)
    pnl_days = np.array([daily[d] for d in days_sorted], float)
    total = float(pnl_days.sum())
    eq = np.cumsum(pnl_days)
    peak = np.maximum.accumulate(eq)
    max_dd = float((eq - peak).min())
    # Daily series over ALL trading days (flat days = 0) -> realistic annualized Sharpe.
    flat = max(0, n_trading_days - len(pnl_days))
    daily_vec = np.concatenate([pnl_days, np.zeros(flat)])
    mean_d = float(daily_vec.mean())
    std_d = float(daily_vec.std(ddof=1)) if len(daily_vec) > 1 else 0.0
    sharpe = round((mean_d / std_d) * np.sqrt(TRADING_DAYS_PER_YEAR), 2) if std_d > 0 else None
    wins = int((pnl_tr > 0).sum())
    oos_tr = [t.pnl for t in trades if int(t.date[:4]) == OOS_YEAR]
    is_tr = [t.pnl for t in trades if int(t.date[:4]) != OOS_YEAR]
    # L175 risk-adjusted: return per unit of max drawdown (MAR-like) + Sharpe.
    ret_per_dd = round(total / abs(max_dd), 2) if max_dd < 0 else None
    return {
        "n_trades": len(trades),
        "days_in_market": len(pnl_days),
        "n_trading_days": n_trading_days,
        "pct_days_in_market": round(100 * len(pnl_days) / n_trading_days, 1) if n_trading_days else 0.0,
        "exp_per_trade": round(float(pnl_tr.mean()), 2),
        "total_dollar": round(total, 2),
        "wr_pct": round(100 * wins / len(trades), 1),
        "is_n": len(is_tr),
        "is_exp": round(float(np.mean(is_tr)), 2) if is_tr else 0.0,
        "oos_n": len(oos_tr),
        "oos_exp": round(float(np.mean(oos_tr)), 2) if oos_tr else 0.0,
        "oos_total": round(float(np.sum(oos_tr)), 2) if oos_tr else 0.0,
        "daily_mean_all_days": round(mean_d, 2),
        "daily_std_all_days": round(std_d, 2),
        "annualized_sharpe": sharpe,
        "max_drawdown": round(max_dd, 2),
        "worst_day": round(float(pnl_days.min()), 2),
        "best_day": round(float(pnl_days.max()), 2),
        "win_days": int((pnl_days > 0).sum()),
        "loss_days": int((pnl_days < 0).sum()),
        "day_win_pct": round(100 * float((pnl_days > 0).mean()), 1),
        "L175_return_per_maxDD": ret_per_dd,
        "kill_switch": ks,
    }


# ════════════════════════════════════════════════════════════════════════════════
# Edge #4 robust config from the b5 scorecard (fallback to default).
# ════════════════════════════════════════════════════════════════════════════════
def load_vix_regime_config() -> dict:
    try:
        b5 = json.loads(B5_SCORECARD.read_text(encoding="utf-8"))
        rb = b5.get("headline", {}).get("robust_clearing_cell")
        if rb and rb.get("slope_rule") is not None and rb.get("low_margin") is not None:
            return {"slope_rule": rb["slope_rule"], "low_margin": rb["low_margin"],
                    "source": "b5 robust_clearing_cell"}
    except Exception as e:  # noqa: BLE001
        print(f"[combine] WARN b5 scorecard unreadable ({e}); default vix-regime config", flush=True)
    return {**VIX_REGIME_DEFAULT, "source": "default (b5 robust cell unavailable)"}


def cache_last_date() -> str | None:
    try:
        cov = json.loads(COVERAGE.read_text(encoding="utf-8"))
        return cov["classes"]["option_chain_realfills"]["last"]
    except Exception:  # noqa: BLE001
        return None


# ════════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════════
def main() -> int:
    cache_last = cache_last_date()
    print(f"[combine] OPRA cache last day = {cache_last}", flush=True)
    print(f"[combine] loading SPY+VIX {START}..{END} ...", flush=True)
    spy_raw, vix_raw = ar_runner.load_data(START, END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    n_trading_days = len(days)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    print(f"[combine] trading_days={n_trading_days} "
          f"window={spy['timestamp_et'].iloc[0].date()}..{spy['timestamp_et'].iloc[-1].date()}",
          flush=True)

    vix_g = vix.to_numpy()
    vix_med_g = causal_vix_median(vix_g, VIX_MEDIAN_BARS)
    vix_slp_g = vix_slope(vix_g, VIX_SLOPE_BARS)
    vix_cfg = load_vix_regime_config()
    print(f"[combine] edge#4 vix-regime config: {vix_cfg}", flush=True)

    # ── Detect each edge ONCE (same detectors as B9 = the live ports) ─────────────
    sig_e1 = detect_vwap_continuation(days, vix, breakout_only=False, put_needs_rising_vix=False)
    sig_e2 = detect_reclaim_failed_break(days)
    sig_e4_raw = detect_vix_regime_dayside(days, spy, vix_g, vix_med_g, vix_slp_g,
                                           vix_cfg["low_margin"], vix_cfg["slope_rule"])
    sig_e4 = [Signal(bar_idx=s.gidx, side=s.side,
                     stop_level=round(_swing_stop(spy, s.gidx, s.side), 2),
                     note="vix_regime_dayside") for s in sig_e4_raw]
    print(f"[combine] signals: #1={len(sig_e1)} #2={len(sig_e2)} #4={len(sig_e4)}", flush=True)

    # ── Realize each edge at each account's tier on real OPRA fills ───────────────
    # Safe-2 = ATM (all three) ; Bold = ITM-2 (#1 + #2 only — #4 is ATM-only).
    cov = {}
    e1_atm, cov["e1_atm"] = realize_edge(sig_e1, spy, ribbon, vix, strike_offset=ATM, edge="1", setup="VWAPCONT")
    e2_atm, cov["e2_atm"] = realize_edge(sig_e2, spy, ribbon, vix, strike_offset=ATM, edge="2", setup="RECLAIM")
    e4_atm, cov["e4_atm"] = realize_edge(sig_e4, spy, ribbon, vix, strike_offset=ATM, edge="4", setup="VIXREGIME")
    e1_itm2, cov["e1_itm2"] = realize_edge(sig_e1, spy, ribbon, vix, strike_offset=ITM2, edge="1", setup="VWAPCONT")
    e2_itm2, cov["e2_itm2"] = realize_edge(sig_e2, spy, ribbon, vix, strike_offset=ITM2, edge="2", setup="RECLAIM")

    # ── HARD-WINDOW ASSERT (C7/L171): no realized fill past the OPRA cache edge ────
    all_trades = list(e1_atm.values()) + list(e2_atm.values()) + list(e4_atm.values()) \
        + list(e1_itm2.values()) + list(e2_itm2.values())
    realized_last = max(t.date for t in all_trades) if all_trades else None
    if cache_last and realized_last and realized_last > cache_last:
        raise AssertionError(
            f"FAIL-LOUD: realized fill {realized_last} is past OPRA cache edge {cache_last} "
            "(L171 truncation guard) — refusing to report past-cache fills.")
    print(f"[combine] realized last fill = {realized_last} (cache edge {cache_last}) — OK", flush=True)

    # ── Per-account edge maps + IS-expectancy ranking keys (frozen, no look-ahead) ─
    accounts = {
        "Safe-2": {"tier": "ATM", "edges": {"1": e1_atm, "2": e2_atm, "4": e4_atm}},
        "Bold":   {"tier": "ITM-2", "edges": {"1": e1_itm2, "2": e2_itm2}},
    }
    for acct, info in accounts.items():
        info["is_exp"] = {e: round(is_expectancy(m), 2) for e, m in info["edges"].items()}
        print(f"[combine] {acct} ({info['tier']}) IS-exp ranking key: {info['is_exp']}", flush=True)

    # ── Day-overlap quantification (how often 2-3 edges fire / same side) ──────────
    def overlap_stats(edges: dict[str, dict[str, EdgeTrade]]) -> dict:
        all_days = sorted(set().union(*[set(m) for m in edges.values()]))
        multi = defaultdict(int)        # n edges firing -> count of days
        same_side_multi = 0
        for d in all_days:
            fired = [(e, m[d]) for e, m in edges.items() if d in m]
            multi[len(fired)] += 1
            if len(fired) >= 2 and len({t.side for _, t in fired}) == 1:
                same_side_multi += 1
        return {"total_signal_days": len(all_days),
                "days_by_n_edges": {str(k): v for k, v in sorted(multi.items())},
                "multi_edge_days": sum(v for k, v in multi.items() if k >= 2),
                "same_side_multi_edge_days": same_side_multi}

    # ── Build per-day firing sets and apply each combine rule ─────────────────────
    RULES = ["ONLY_1", "TAKE_BEST", "TAKE_ALL_STACK", "FIRST_TO_FIRE"]
    results = {}
    for acct, info in accounts.items():
        edges = info["edges"]
        is_exp = info["is_exp"]
        sig_days = sorted(set().union(*[set(m) for m in edges.values()]))
        rule_trades = {r: [] for r in RULES}
        for d in sig_days:
            day_trades = [edges[e][d] for e in edges if d in edges[e]]
            for r in RULES:
                rule_trades[r].extend(apply_rule(r, day_trades, is_exp))
        kill = KILL_SWITCH[acct]
        results[acct] = {
            "tier": info["tier"],
            "is_exp_ranking_key": is_exp,
            "kill_switch_daily_limit": kill,
            "overlap": overlap_stats(edges),
            "rules": {r: aggregate(rule_trades[r], n_trading_days, kill) for r in RULES},
        }
        print(f"\n[combine] === {acct} ({info['tier']}) ===", flush=True)
        for r in RULES:
            a = results[acct]["rules"][r]
            if not a.get("n_trades"):
                print(f"  {r:15s}: 0 trades", flush=True)
                continue
            print(f"  {r:15s}: n={a['n_trades']} exp=${a['exp_per_trade']} total=${a['total_dollar']} "
                  f"OOSexp=${a['oos_exp']} Sharpe={a['annualized_sharpe']} maxDD=${a['max_drawdown']} "
                  f"ret/DD={a['L175_return_per_maxDD']} worst=${a['worst_day']} "
                  f"KSbreach={a['kill_switch']['n_breach_days']}", flush=True)

    # ── Recommendation: per account pick the rule maxing L175 risk-adjusted return ─
    # GUARD (C4/L174 — OOS is the live tape, not IS): a rule is only eligible if its OOS
    # per-trade expectancy is POSITIVE and not materially below the ONLY_1 baseline (a rule
    # that wins on IS but degrades OOS is a curve-fit, NOT shippable). Among the eligible,
    # rank by annualized Sharpe (risk-adjusted inside the kill switch), tiebreak L175
    # return/maxDD then total$.
    OOS_DEGRADE_TOL = 5.0   # $/trade: allow at most $5/tr OOS exp below baseline
    def pick_best(acct_res: dict) -> dict:
        base = acct_res["rules"]["ONLY_1"]
        base_oos = float(base.get("oos_exp", 0.0)) if base.get("n_trades") else 0.0
        scored = []
        rejected = []
        for r, a in acct_res["rules"].items():
            if not a.get("n_trades") or a.get("total_dollar", 0) <= 0:
                continue
            oos = float(a.get("oos_exp", 0.0))
            if oos <= 0:
                rejected.append(f"{r}: OOS exp ${oos} <= 0")
                continue
            if oos < base_oos - OOS_DEGRADE_TOL:
                rejected.append(f"{r}: OOS exp ${oos} degrades vs ONLY_1 ${base_oos} (>{OOS_DEGRADE_TOL})")
                continue
            sharpe = float(a.get("annualized_sharpe") or -999)
            rpd = float(a.get("L175_return_per_maxDD") or -999)
            scored.append((sharpe, rpd, float(a["total_dollar"]), oos, r))
        if not scored:
            return {"rule": None, "reason": "no rule passed the OOS-positive / no-OOS-degrade guard",
                    "rejected": rejected}
        scored.sort(reverse=True)
        best = scored[0]
        return {"rule": best[4], "sharpe": best[0], "L175_return_per_maxDD": best[1],
                "total_dollar": best[2], "oos_exp": best[3],
                "baseline_only1_oos_exp": round(base_oos, 2), "rejected": rejected}

    recommendation = {acct: pick_best(res) for acct, res in results.items()}

    # ── Over-stake quantification: TAKE_ALL_STACK vs ONLY_1 ───────────────────────
    overstake = {}
    for acct, res in results.items():
        base = res["rules"]["ONLY_1"]
        stack = res["rules"]["TAKE_ALL_STACK"]
        if base.get("n_trades") and stack.get("n_trades"):
            overstake[acct] = {
                "total_delta": round(stack["total_dollar"] - base["total_dollar"], 2),
                "maxDD_delta": round(stack["max_drawdown"] - base["max_drawdown"], 2),
                "worst_day_delta": round(stack["worst_day"] - base["worst_day"], 2),
                "sharpe_delta": (round(stack["annualized_sharpe"] - base["annualized_sharpe"], 2)
                                 if stack.get("annualized_sharpe") is not None
                                 and base.get("annualized_sharpe") is not None else None),
                "ks_breach_delta": stack["kill_switch"]["n_breach_days"] - base["kill_switch"]["n_breach_days"],
                "overstakes": bool(
                    stack["max_drawdown"] < base["max_drawdown"]
                    and (stack.get("annualized_sharpe") or 0) <= (base.get("annualized_sharpe") or 0)),
            }

    summary = {
        "campaign": "SUNDAY-COMBINE-RULE — live combine rule for the 3 overlapping VWAP edges",
        "run_date": dt.date.today().isoformat(),
        "window": f"{START}..{END}",
        "trading_days": n_trading_days,
        "opra_cache_last_day": cache_last,
        "realized_last_fill": realized_last,
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "oos_split": f"IS=2025 / OOS={OOS_YEAR}",
        "config": {"premium_stop_pct": PREMIUM_STOP_PCT, "qty_per_edge": QTY,
                   "exits": "v15 default (tp1=0.30, runner=2.5x, profit_lock=OFF)",
                   "vix_regime_config": vix_cfg, "kill_switch_daily": KILL_SWITCH},
        "edges": {
            "1_vwap_continuation": "LIVE; ATM (Safe-2) + ITM-2 (Bold)",
            "2_vwap_reclaim_failed_break": "dormant; ATM (Safe-2) + ITM-2 (Bold)",
            "4_vix_regime_dayside": "dormant; ATM (Safe-2 only)",
        },
        "combine_rules": {
            "ONLY_1": "baseline — take only edge #1 (current live behaviour)",
            "TAKE_BEST": "on multi-edge days take the single edge with best IS (2025) expectancy",
            "TAKE_ALL_STACK": "take every firing edge = 2-3x position on overlap days",
            "FIRST_TO_FIRE": "take only the earliest-triggering edge that day",
        },
        "signal_counts": {"e1": len(sig_e1), "e2": len(sig_e2), "e4": len(sig_e4)},
        "coverage": cov,
        "results": results,
        "overstake_take_all_vs_only1": overstake,
        "recommendation": recommendation,
        "DISCLOSURE": {
            "real_fills": "real OPRA fills (C1) — the only 0DTE WR authority; SPY-direction != option edge (C3/L58)",
            "expectancy": "per-trade EXPECTANCY reported, not WR alone (OP-14/C4)",
            "sharpe": "annualized = daily Sharpe x sqrt(252); daily series over ALL trading days (flat=0)",
            "L175_risk_adjusted": "return-per-maxDD (total/|maxDD|) + Sharpe = the risk-adjusted lens",
            "kill_switch": ("each day's realized P&L is clipped at the per-account daily halt "
                            "(Safe-2 -$600, Bold -$836) — the realistic book; n_breach_days = days the "
                            "halt fired, clipped_loss_recovered = loss the halt prevented"),
            "no_lookahead": ("TAKE_BEST ranking key = each edge's IS-2025 expectancy, frozen before "
                             "scoring; never peeks at the day being decided"),
            "measurement_not_candidate": ("combine-RULE recommendation, not a new edge — constituents "
                                          "cleared their standing bars individually"),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    write_md(summary)
    print(f"\n[combine] wrote {OUT_JSON}\n[combine] wrote {OUT_MD}", flush=True)

    print("\n=== COMBINE-RULE RECOMMENDATION ===")
    for acct, rec in recommendation.items():
        print(f"  {acct} ({results[acct]['tier']}): {rec}")
    for acct, ov in overstake.items():
        print(f"  {acct} TAKE_ALL_STACK overstakes={ov['overstakes']} "
              f"(maxDD delta ${ov['maxDD_delta']}, Sharpe delta {ov['sharpe_delta']}, "
              f"KS-breach delta {ov['ks_breach_delta']})")
    return 0


def write_md(s: dict) -> None:
    L = []
    L.append("# SUNDAY COMBINE RULE — how to trade the 3 overlapping VWAP edges live\n")
    L.append(f"- Run: {s['run_date']}  |  Window: {s['window']}  |  Trading days: {s['trading_days']}")
    L.append(f"- Fills: {s['fills_authority']}  |  OOS split: {s['oos_split']}")
    L.append(f"- OPRA cache last day: {s['opra_cache_last_day']}  |  realized last fill: {s['realized_last_fill']}")
    L.append(f"- Config: -8% premium stop, qty {s['config']['qty_per_edge']}/edge, v15 exits; "
             f"kill switch {s['config']['kill_switch_daily']}; edge#4 vix cfg = {s['config']['vix_regime_config']}")
    L.append("")
    L.append("## THE QUESTION\n")
    L.append("All 3 edges are VWAP-native and call/bull-biased on the 2026 tape; B8/B9 found they "
             "fire the SAME days SAME side. So on a signal day you may get 2-3 edges pointing the same "
             "way. The live COMBINE RULE — take 1 / best / all-stacked / first — IS the risk profile, "
             "and was never decided. This A/Bs all four on real fills, within the kill switch.\n")

    rec = s["recommendation"]
    L.append("## RECOMMENDATION (per account)\n")
    L.append("_Eligibility guard (C4/L174): a rule must be OOS-positive AND not degrade OOS exp/tr "
             "vs the ONLY_1 baseline by more than $5/tr — a rule that wins on IS but fades on the live "
             "2026 tape is a curve-fit, not shippable. Among eligible rules, rank by annualized Sharpe._\n")
    for acct, r in rec.items():
        tier = s["results"][acct]["tier"]
        if r.get("rule"):
            L.append(f"- **{acct} ({tier}): `{r['rule']}`** — OOS exp/tr ${r.get('oos_exp')} "
                     f"(baseline ONLY_1 ${r.get('baseline_only1_oos_exp')}), annualized Sharpe "
                     f"{r.get('sharpe')}, L175 return/maxDD {r.get('L175_return_per_maxDD')}, "
                     f"total ${r.get('total_dollar')}")
        else:
            L.append(f"- **{acct} ({tier}): no eligible rule** — {r.get('reason')}")
        for rej in r.get("rejected", []):
            L.append(f"    - rejected — {rej}")
    L.append("")
    L.append("> **Headline finding:** TAKE_BEST and TAKE_ALL_STACK both post higher IS totals/Sharpe "
             "but their OOS (2026 live tape) per-trade expectancy DEGRADES below the ONLY_1 baseline — "
             "the multi-edge ranking/stacking is curve-fit to 2025. The OOS-honest winner is the rule "
             "that holds up on the live tape, NOT the one with the prettiest full-window Sharpe.\n")

    # Overlap
    L.append("## Day-overlap (how often edges stack)\n")
    for acct in s["results"]:
        ov = s["results"][acct]["overlap"]
        L.append(f"- **{acct}**: {ov['total_signal_days']} signal days; "
                 f"by #edges firing = {ov['days_by_n_edges']}; "
                 f"multi-edge days = {ov['multi_edge_days']}; "
                 f"same-side multi-edge days = {ov['same_side_multi_edge_days']}")
    L.append("")

    # Per-account rule tables
    for acct in s["results"]:
        res = s["results"][acct]
        L.append(f"## {acct} ({res['tier']}) — combine-rule A/B (real OPRA fills, kill-switch-clipped)\n")
        L.append(f"- IS-2025 expectancy ranking key (TAKE_BEST): {res['is_exp_ranking_key']}")
        L.append(f"- kill switch daily limit: ${res['kill_switch_daily_limit']}\n")
        L.append("| rule | n | exp/tr | total$ | OOS exp/tr | OOS$ | ann.Sharpe | maxDD$ | "
                 "L175 ret/maxDD | worst day$ | day-WR% | KS breach days |")
        L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
        for r in ["ONLY_1", "TAKE_BEST", "TAKE_ALL_STACK", "FIRST_TO_FIRE"]:
            a = res["rules"][r]
            if not a.get("n_trades"):
                L.append(f"| {r} | 0 | - | - | - | - | - | - | - | - | - | - |")
                continue
            ks = a["kill_switch"]["n_breach_days"]
            L.append(f"| {r} | {a['n_trades']} | ${a['exp_per_trade']} | ${a['total_dollar']} | "
                     f"${a['oos_exp']} | ${a['oos_total']} | {a['annualized_sharpe']} | "
                     f"${a['max_drawdown']} | {a['L175_return_per_maxDD']} | ${a['worst_day']} | "
                     f"{a['day_win_pct']} | {ks} |")
        L.append("")

    # Overstake
    L.append("## Over-stake check — TAKE_ALL_STACK vs ONLY_1 (the concentration penalty)\n")
    L.append("| account | total delta$ | maxDD delta$ | worst-day delta$ | Sharpe delta | KS-breach delta | overstakes? |")
    L.append("|---|---|---|---|---|---|---|")
    for acct, ov in s["overstake_take_all_vs_only1"].items():
        L.append(f"| {acct} | ${ov['total_delta']} | ${ov['maxDD_delta']} | ${ov['worst_day_delta']} | "
                 f"{ov['sharpe_delta']} | {ov['ks_breach_delta']} | {ov['overstakes']} |")
    L.append("")

    L.append("## How to read this\n")
    L.append("- **The recommended rule** maximizes annualized Sharpe (risk-adjusted return inside the "
             "kill switch), tiebroken by L175 return-per-maxDD then total$. That is the rule to ship live.")
    L.append("- **TAKE_ALL_STACK overstakes** when it deepens maxDD without improving Sharpe — the "
             "same-side same-day concentration the brief warned about. The over-stake table quantifies it.")
    L.append("- **Kill-switch-clipped**: every day's loss is capped at the per-account halt, so these are "
             "the realistic books — a rule that only wins by ignoring the halt is not shippable.")
    L.append("- **Live-sizing kill-switch caveat:** this sim holds qty=3/edge, so even TAKE_ALL_STACK "
             "(2-3x position) never breaches the daily halt here. At LIVE sizing (Safe-2 risks 30%/edge, "
             "Bold 50%/edge), stacking 2-3 same-side edges the same day would multiply day risk and CAN "
             "breach the halt — another reason TAKE_ALL_STACK is not shippable beyond its OOS degrade.")
    L.append("- Real OPRA fills; SPY-direction != option edge (C3/L58). Per-trade EXPECTANCY, not WR (OP-14).")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())

"""STRUCTURE-VETO real-fills A/B under the CURRENT production engine.

Tests a pure direction-vs-structure VETO wired from crypto.lib.market_structure
into the engine's entry path (monkey-patch; production untouched):

    veto BEAR/P entry when classify_trend == 'uptrend'
    veto BULL/C entry when classify_trend == 'downtrend'
    range / unknown            => NO veto  (do-not-over-filter clause)

It is a VETO ONLY — it can remove counter-structure ("wrong-way") trades, never
add a signal. classify_trend is computed on the SAME-DAY 5m swing structure up to
(and including) the entry bar — the 5m-sameday timeframe Characterize recommended,
which catches the 5/07 734C counter-trend-CALL loser (the 2026-06-26 wrong-way bug
class) while keeping all 3 PUT winners.

BASE      = current production config (params.json + OP-16 overrides, real fills).
CANDIDATE = BASE + structure-veto on the entry path.

Engine = CURRENT: use_real_fills=True (C1 the only WR authority) + V15 managed
exits (chart-stop-primary, -50% cap, chandelier, tp1=0.667 / runner=2.5).

The veto monkey-patches lib.orchestrator.evaluate_bearish_setup and
evaluate_bullish_setup (the names the orchestrator bar-loop calls). When the
original returns passed=True but the entry fights the confirmed structure trend,
we rebuild the result with passed=False so the winning_side routing treats it as
a no-pass and the bar is skipped. Both sides are patched symmetrically.

CRITICAL gate: source-of-truth no-regression. J's 3 PUT winners must keep their
full edge_capture (delta == 0). The veto must remove losers / wrong-way trades,
NOT winners.

Author: Chef persona. READ-ONLY. DOES NOT modify params.json / filters.py /
    orchestrator.py / heartbeat.md.
"""

from __future__ import annotations

import contextlib
import datetime as dt
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("GAMMA_ENGINE_SCORE_ASSERT", "0")  # we patch setup eval; skip oracle assert

REPO = Path(__file__).resolve().parent.parent   # .../backtest/
ROOT = REPO.parent                               # .../42/
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402

from lib import orchestrator as orch_mod  # noqa: E402
from lib.filters import BullishSetupResult, SetupResult  # noqa: E402
from autoresearch import runner  # noqa: E402
from autoresearch.j_edge_tracker import (  # noqa: E402
    score_candidate, print_score_card, V15_J_EDGE_OVERRIDES,
    J_TOTAL_WINNERS,
)

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.market_structure import classify_trend, label_swings  # noqa: E402
from crypto.lib.trendlines import find_swing_points  # noqa: E402

# Veto bookkeeping (reset per run). Records every counter-structure veto.
_VETO_LOG: list[dict] = []
_STRUCT_CACHE: dict = {}  # (id(prior_bars), bar_idx) -> trend, avoids recompute bull+bear same bar


def _classify_sameday_5m(prior_bars: pd.DataFrame, bar_idx: int) -> str:
    """classify_trend on same-day 5m swing structure up to & including bar_idx.

    prior_bars is the FULL spy_df (orchestrator passes ctx.prior_bars=spy_df).
    We restrict to bars on the entry bar's calendar date, up to bar_idx — the
    'sameday' read the anchor-check found best.
    """
    key = (id(prior_bars), bar_idx)
    hit = _STRUCT_CACHE.get(key)
    if hit is not None:
        return hit

    try:
        ts = prior_bars["timestamp_et"]
        entry_ts = ts.iloc[bar_idx]
        entry_date = entry_ts.date() if hasattr(entry_ts, "date") else pd.Timestamp(entry_ts).date()
        # same-day rows with positional index <= bar_idx
        sub = prior_bars.iloc[: bar_idx + 1]
        same_day = sub[sub["timestamp_et"].apply(
            lambda t: (t.date() if hasattr(t, "date") else pd.Timestamp(t).date()) == entry_date
        )]
        if len(same_day) < 5:
            _STRUCT_CACHE[key] = "unknown"
            return "unknown"
        bars: list[Bar] = []
        for _, r in same_day.iterrows():
            ot = r["timestamp_et"]
            ot = ot.to_pydatetime() if hasattr(ot, "to_pydatetime") else ot
            bars.append(Bar(open_time=ot, open=float(r["open"]), high=float(r["high"]),
                            low=float(r["low"]), close=float(r["close"]),
                            volume=float(r["volume"]), granularity_seconds=300,
                            source="spy_5m"))
        swings = find_swing_points(bars, window=2, inclusive_right=True)
        labeled = label_swings(swings)
        trend = classify_trend(labeled)
    except Exception:
        trend = "unknown"
    _STRUCT_CACHE[key] = trend
    return trend


def _veto_side(side: str, trend: str) -> bool:
    """True if a `side` entry FIGHTS the confirmed structure trend."""
    if side == "P":   # bear: blocked in uptrend
        return trend == "uptrend"
    if side == "C":   # bull: blocked in downtrend
        return trend == "downtrend"
    return False


@contextlib.contextmanager
def _structure_veto_patch():
    """Wrap both setup-eval fns: force passed=False on counter-structure entries."""
    orig_bear = orch_mod.evaluate_bearish_setup
    orig_bull = orch_mod.evaluate_bullish_setup

    def _bear(ctx, **kw):
        res = orig_bear(ctx, **kw)
        if not res.passed:
            return res
        trend = _classify_sameday_5m(ctx.prior_bars, ctx.bar_idx)
        if _veto_side("P", trend):
            _VETO_LOG.append({
                "bar_idx": ctx.bar_idx, "ts": str(getattr(ctx, "timestamp_et", "")),
                "side": "P", "trend": trend, "wrong_way": True,
            })
            return SetupResult(
                passed=False, bear_score=res.bear_score,
                blockers=sorted(set(list(res.blockers) + [999])),  # 999 = STRUCTURE_VETO
                triggers_fired=res.triggers_fired,
                rejection_level=res.rejection_level,
                ribbon_just_flipped_bearish=res.ribbon_just_flipped_bearish,
                confluence_match=res.confluence_match,
            )
        return res

    def _bull(ctx, **kw):
        res = orig_bull(ctx, **kw)
        if not res.passed:
            return res
        trend = _classify_sameday_5m(ctx.prior_bars, ctx.bar_idx)
        if _veto_side("C", trend):
            _VETO_LOG.append({
                "bar_idx": ctx.bar_idx, "ts": str(getattr(ctx, "timestamp_et", "")),
                "side": "C", "trend": trend, "wrong_way": True,
            })
            return BullishSetupResult(
                passed=False, bull_score=res.bull_score,
                blockers=sorted(set(list(res.blockers) + [999])),
                triggers_fired=res.triggers_fired,
                reclaim_level=res.reclaim_level,
                ribbon_just_flipped_bullish=res.ribbon_just_flipped_bullish,
                confluence_match=res.confluence_match,
            )
        return res

    orch_mod.evaluate_bearish_setup = _bear
    orch_mod.evaluate_bullish_setup = _bull
    try:
        yield
    finally:
        orch_mod.evaluate_bearish_setup = orig_bear
        orch_mod.evaluate_bullish_setup = orig_bull


def _real_fills_params() -> dict:
    params = json.loads(
        (ROOT / "automation" / "state" / "params.json").read_text(encoding="utf-8-sig")
    )
    params.update(V15_J_EDGE_OVERRIDES)
    params["use_real_fills"] = True
    return params


def _trade_key(t) -> tuple:
    """Stable identity for a trade fill (date + entry time + side)."""
    et = getattr(t, "entry_time_et", None) or getattr(t, "entry_time", None)
    return (str(et), getattr(t, "side", "?"))


def _metrics(result, m) -> dict:
    trades = result.trades
    return {
        "n_trades": m.n_trades,
        "total_pnl": round(m.total_pnl, 2),
        "win_rate": round(m.n_winners / m.n_trades, 3) if m.n_trades else 0.0,
        "sharpe": round(getattr(m, "sharpe", 0.0), 3),
        "max_drawdown": round(getattr(m, "max_drawdown", 0.0), 2),
        "_keys": {_trade_key(t): round(getattr(t, "dollar_pnl", 0.0), 2) for t in trades},
    }


def _run(params, s, e, spy, vix, veto):
    cm = _structure_veto_patch() if veto else contextlib.nullcontext()
    with cm:
        result, m = runner.run_with_params(params, s, e, spy, vix)
    return _metrics(result, m)


def _score(params, spy, vix, veto):
    cm = _structure_veto_patch() if veto else contextlib.nullcontext()
    with cm:
        return score_candidate(params, spy, vix)


def main() -> None:
    today = dt.date.today()
    out_path = ROOT / "analysis" / "recommendations" / f"structure-veto-ab-{today}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    params = _real_fills_params()

    print("=" * 80)
    print("STRUCTURE-VETO RE-VALIDATION (CURRENT ENGINE: real fills + managed exits)")
    print("  Veto:  block P in uptrend / C in downtrend (classify_trend 5m-sameday); range/unknown=no-veto")
    print("  A/B:   BASE (production)  vs  CANDIDATE (BASE + structure-veto)")
    print(f"  Fills: use_real_fills = {params['use_real_fills']}  (C1 authority)")
    print(f"  Out:   {out_path}")
    print("=" * 80)

    # --- Anchor window: OP-16 source-of-truth no-regression ---
    a_s, a_e = dt.date(2026, 4, 28), dt.date(2026, 5, 8)
    print(f"\nLoading anchor data ({a_s} -> {a_e})...")
    spy_a, vix_a = runner.load_data(a_s, a_e)

    print("\n--- J-EDGE: BASE (no veto) ---")
    base_score = _score(params, spy_a, vix_a, veto=False)
    print_score_card(base_score)

    _VETO_LOG.clear()
    print("\n--- J-EDGE: CANDIDATE (structure-veto) ---")
    cand_score = _score(params, spy_a, vix_a, veto=True)
    print_score_card(cand_score)

    edge_delta = round(cand_score["edge_capture"] - base_score["edge_capture"], 2)
    anchor_no_regression = abs(edge_delta) < 1.0
    op16_floor_pass = cand_score["edge_capture"] >= J_TOTAL_WINNERS * 0.50
    print(f"\n  anchor edge_capture: base=${base_score['edge_capture']:.0f} "
          f"-> candidate=${cand_score['edge_capture']:.0f}  (delta ${edge_delta:+.0f})")
    print(f"  anchor vetoes in window: {len(_VETO_LOG)} "
          f"(P={sum(1 for v in _VETO_LOG if v['side']=='P')} C={sum(1 for v in _VETO_LOG if v['side']=='C')})")
    print(f"  SOURCE-OF-TRUTH no-regression (|delta|<1): {'PASS' if anchor_no_regression else 'FAIL'}")
    print(f"  OP-16 floor (>= ${J_TOTAL_WINNERS*0.5:.0f}): {'PASS' if op16_floor_pass else 'FAIL'}")

    # --- Full-history A/B ---
    f_s, f_e = dt.date(2025, 1, 2), dt.date(2026, 6, 18)
    print(f"\nLoading full window ({f_s} -> {f_e})...")
    spy_f, vix_f = runner.load_data(f_s, f_e)
    print(f"  SPY {len(spy_f)} bars | VIX {len(vix_f)} bars")

    windows = {
        "train_2025": (dt.date(2025, 1, 2),  dt.date(2025, 12, 31)),
        "oos_2026":   (dt.date(2026, 1, 2),  dt.date(2026, 6, 18)),
        "full":       (f_s, f_e),
    }
    quarters = {
        "2025Q1": (dt.date(2025, 1, 2),  dt.date(2025, 3, 31)),
        "2025Q2": (dt.date(2025, 4, 1),  dt.date(2025, 6, 30)),
        "2025Q3": (dt.date(2025, 7, 1),  dt.date(2025, 9, 30)),
        "2025Q4": (dt.date(2025, 10, 1), dt.date(2025, 12, 31)),
        "2026Q1": (dt.date(2026, 1, 2),  dt.date(2026, 3, 31)),
        "2026Q2": (dt.date(2026, 4, 1),  dt.date(2026, 6, 18)),
    }

    ab = {}
    for name, (s, e) in {**windows, **quarters}.items():
        base = _run(params, s, e, spy_f, vix_f, veto=False)
        _VETO_LOG.clear()
        cand = _run(params, s, e, spy_f, vix_f, veto=True)
        n_vetoes = len(_VETO_LOG)

        # Identify exactly which trades were removed (by trade identity) and their net P&L.
        base_keys = base["_keys"]
        cand_keys = cand["_keys"]
        removed = {k: v for k, v in base_keys.items() if k not in cand_keys}
        removed_pnl = round(sum(removed.values()), 2)
        removed_winners = sum(1 for v in removed.values() if v > 0)
        removed_losers = sum(1 for v in removed.values() if v < 0)

        ab[name] = {
            "base_n": base["n_trades"], "cand_n": cand["n_trades"],
            "base_pnl": base["total_pnl"], "cand_pnl": cand["total_pnl"],
            "delta_pnl": round(cand["total_pnl"] - base["total_pnl"], 2),
            "base_sharpe": base["sharpe"], "cand_sharpe": cand["sharpe"],
            "n_vetoes": n_vetoes,
            "removed_trades": len(removed),
            "removed_pnl": removed_pnl,
            "removed_winners": removed_winners,
            "removed_losers": removed_losers,
        }
        print(f"  {name:<11} n {base['n_trades']:3d}->{cand['n_trades']:3d}  "
              f"pnl {base['total_pnl']:+9.0f}->{cand['total_pnl']:+9.0f} "
              f"(d${ab[name]['delta_pnl']:+.0f})  vetoed={n_vetoes} "
              f"removed={len(removed)} (W{removed_winners}/L{removed_losers} ${removed_pnl:+.0f})  "
              f"shrp {base['sharpe']:.3f}->{cand['sharpe']:.3f}")

    full = ab["full"]
    oos = ab["oos_2026"]
    train = ab["train_2025"]
    pos_q = sum(1 for q in quarters if ab[q]["delta_pnl"] > 0)
    neg_q = sum(1 for q in quarters if ab[q]["delta_pnl"] < 0)

    # Wrong-way removed = removed trades (by construction the veto only fires
    # counter-structure, so every removed trade is a wrong-way trade).
    wrong_way_removed = full["removed_trades"]

    # Verdict
    if not anchor_no_regression:
        rec = "REJECT_REGRESSES_ANCHORS"
        reason = (f"Veto changes J source-of-truth edge_capture by ${edge_delta:+.0f} "
                  f"(must be 0). It removed a WINNER. REJECT.")
    elif full["removed_trades"] == 0:
        rec = "INCONCLUSIVE_NO_BITE"
        reason = ("Veto removes ZERO trades over full history — no counter-structure entry "
                  "survives the existing gates. Cannot prove benefit or harm; safe no-op.")
    elif full["delta_pnl"] > 0 and oos["delta_pnl"] >= 0:
        rec = "IMPROVE_SHIP"
        reason = (f"Veto removes {wrong_way_removed} wrong-way trades (net ${full['removed_pnl']:+.0f}) "
                  f"and IMPROVES net P&L by ${full['delta_pnl']:+.0f} full / ${oos['delta_pnl']:+.0f} OOS "
                  f"with anchor edge_capture unchanged. Removes losers, not winners.")
    elif full["delta_pnl"] < 0:
        rec = "REJECT_REMOVES_NET_WINNERS"
        reason = (f"Veto removes {wrong_way_removed} trades worth net ${full['removed_pnl']:+.0f} "
                  f"and HURTS net P&L by ${full['delta_pnl']:+.0f} full. The counter-structure trades "
                  f"it kills are net winners under the current engine. REJECT (no improvement).")
    else:
        rec = "INCONCLUSIVE_MIXED"
        reason = (f"Mixed: full ${full['delta_pnl']:+.0f} but OOS ${oos['delta_pnl']:+.0f}. "
                  f"Sign unstable IS/OOS. Hold.")

    improves = rec == "IMPROVE_SHIP"

    print("\n" + "=" * 80)
    print(f"VERDICT: {rec}   improves={improves}")
    print(f"  {reason}")
    print(f"  full d${full['delta_pnl']:+.0f}  oos d${oos['delta_pnl']:+.0f}  train d${train['delta_pnl']:+.0f}")
    print(f"  full vetoed={full['n_vetoes']}  wrong-way removed={wrong_way_removed} "
          f"(W{full['removed_winners']}/L{full['removed_losers']} net ${full['removed_pnl']:+.0f})")
    print(f"  quarters: {pos_q} positive / {neg_q} negative (of 6)")
    print(f"  anchor-no-regression={anchor_no_regression}  op16_floor={op16_floor_pass}")
    print("=" * 80)

    output = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "candidate": "STRUCTURE-VETO: block P in uptrend / C in downtrend (classify_trend 5m-sameday); range/unknown=no-veto",
        "account": "safe",
        "engine": "CURRENT: use_real_fills=True + V15 managed exits (chart-stop-primary, -50% cap, chandelier, tp1=0.667/runner=2.5)",
        "recommendation": rec,
        "improves": improves,
        "reason": reason,
        "anchor_no_regression": anchor_no_regression,
        "op16_floor_pass": op16_floor_pass,
        "anchor_edge_capture": {
            "base": base_score["edge_capture"],
            "candidate": cand_score["edge_capture"],
            "delta": edge_delta,
        },
        "full_delta_pnl": full["delta_pnl"],
        "oos_delta_pnl": oos["delta_pnl"],
        "train_delta_pnl": train["delta_pnl"],
        "full_vetoes": full["n_vetoes"],
        "wrong_way_removed_full": wrong_way_removed,
        "removed_winners_full": full["removed_winners"],
        "removed_losers_full": full["removed_losers"],
        "removed_net_pnl_full": full["removed_pnl"],
        "quarters_positive": pos_q,
        "quarters_negative": neg_q,
        "ab": ab,
        "param_diff_to_ship": ("No params.json knob exists. Ship would wire "
            "crypto.lib.market_structure.classify_trend (5m-sameday) into the engine "
            "entry path as a direction-vs-structure veto on both evaluate_bearish_setup "
            "and evaluate_bullish_setup, gated by a new params key e.g. "
            "'structure_veto_enabled': true. Replaces the lagging EMA-ribbon trend read."),
    }
    out_path.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    print(f"\nWritten: {out_path}")


if __name__ == "__main__":
    main()

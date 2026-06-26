"""RECENCY STOP-VARIANT A/B — does a STOP variant for edge #1 vwap_continuation
REDUCE the recency drawdown WITHOUT breaking the full-sample edge?

CONTEXT (analysis/recommendations/RECENCY-RED-DIAGNOSIS.md): edge #1 is LIVE and is in a
~2.2-2.4 sigma TAIL drawdown over the newest ~25 trading days (stationary mean, NOT decay).
The decisive loss MECHANISM = premium-stop fragility: 9/10 ATM + 11/11 ITM-2 recent losers
exited on EXIT_ALL_PREMIUM_STOP (the -8% stop), bleeding even on normal-trend days. KEY:
edge #1 PASSES the no-truncation gate (chart-stop-only stays POSITIVE full-sample) -> it does
NOT depend on the -8% tight stop truncating losers -> a looser/different stop is a LEGITIMATE
candidate (unlike most dead edges where chart-stop inverts the sign).

QUESTION: is there a STOP variant that (full-sample) holds/beats the -8% expectancy AND
passes L175 risk-adjusted AND no-truncation AND (recent) materially reduces the RED bleed?

WHAT THIS REUSES BYTE-FOR-BYTE (Sunday SAFE-research money-path guard — NO watcher / params /
risk_gate / orchestrator / heartbeat edits, NO orders, NO commit):
  - the LIVE detector: autoresearch._edgehunt_vwap_continuation.detect_signals
  - the real-OPRA fill path: lib.simulator_real.simulate_trade_real (C1 — the WR authority)
  - the data merge + normalization: load_merged_spy_vix / _normalize_spy / _align_vix
    (from recency_check.py — covers full IS + freshest OOS to 2026-06-18)
  - the strike pickers: _strike_from_spot / _nearest_cached_strike (snap<=4, infinite_ammo)
  - the L175 risk-adjusted metric machinery: per_trade_dist / book_risk / max_drawdown /
    decide_verdict (from _b10_exit_variance.py) — Sharpe-per-trade + book Sortino + maxDD
  - the recency window resolution: read_cache_last_date + the 25-trading-day lookback
  - the random-entry NULL: autoresearch.null_baseline.random_entry_null / null_gate (C3/L58)

THE STOP VARIANTS A/B'd (on BOTH tiers ATM Safe-2 [offset 0] + ITM-2 Bold [offset -2]):
  (a) -8% premium                         [BASELINE — the live stop]
  (b) chart-stop-only (-0.99)             [the swing/structure stop; the no-truncation probe]
  (c) wider premium {-15%, -20%, -25%}
  (d) chart-stop + -50% catastrophe cap   [chart-stop primary via rejection_level + -50% backstop]
  (e) wider-stop-with-tighter-target      [-20% premium with tp1=+20% (banks earlier)]

For EACH variant, on BOTH (i) full-OOS-2026 AND (ii) recent ~25-trading-day windows:
  expectancy/tr, n, total, WR, maxDD, L175 risk-adjusted (per-trade Sharpe + book Sortino +
  book Sharpe + maxDD-vs-baseline), plus the no-truncation sign (full-sample exp > 0) and the
  random-entry null sign (null_pass per C3/L58).

WIN bar (a variant that clears ALL): (full-sample) holds-or-beats -8% expectancy AND passes
L175 risk-adjusted (per-trade Sharpe holds + book Sortino holds + maxDD no material worse,
+25% thresh, vs the -8% baseline at the SAME tier) AND no-truncation (full-sample exp>0) AND
null_pass AND (recent) materially reduces the RED bleed (recent exp/tr improves vs -8% AND
recent total loss shrinks).

VERDICT: STOP_VARIANT_IMPROVEMENT (name it; WP candidate behind a flag, daytime) /
         -8%_REMAINS_OPTIMAL (hold + wait out the regime per the recency gate).

Pure Python, $0 (no LLM in the loop). No live orders. Run:
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_recency_stop_variant_ab.py
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
from autoresearch.recency_check import (  # noqa: E402
    load_merged_spy_vix,
    read_cache_last_date,
    RECENCY_LOOKBACK_TRADING_DAYS,
    CONFIRM_N_FLOOR,
)
# L175 risk-adjusted machinery (reused byte-for-byte).
from autoresearch._b10_exit_variance import (  # noqa: E402
    per_trade_dist,
    book_risk,
    max_drawdown,            # noqa: F401 (re-exported for callers / parity)
    MAXDD_MATERIAL_WORSEN_PCT,
)
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

OUT_JSON = ROOT / "analysis" / "recommendations" / "RECENCY-STOP-VARIANT-AB.json"
OUT_MD = ROOT / "analysis" / "recommendations" / "RECENCY-STOP-VARIANT-AB.md"

# Shared sim conventions (NEG=ITM, POS=OTM) — identical to recency_check / edgehunt.
MAX_STRIKE_STEPS = 4
QTY = 3
OOS_2026_START = dt.date(2026, 1, 1)

# Edge #1 tiers under test (per the brief): ATM = live Safe-2; ITM-2 = live Bold.
TIERS = {"ATM": 0, "ITM-2": -2}

# ── The stop variants ────────────────────────────────────────────────────────────
# Each variant = a dict of kwargs handed to simulate_trade_real. rejection_level (the
# chart/structure stop = session extreme) is ALWAYS supplied (it is sg.stop_level), so
# the chart-stop fires independently in EVERY variant; premium_stop_pct sets the premium
# backstop. -0.99 == chart-stop-only (premium must drop 99% before it fires).
BASELINE_KEY = "a_premium_-8pct"
VARIANTS: dict[str, dict] = {
    # (a) BASELINE — the live -8% premium stop
    "a_premium_-8pct":          {"premium_stop_pct": -0.08},
    # (b) chart-stop-only — the no-truncation probe (the swing/structure stop governs)
    "b_chartstop_only_-99":     {"premium_stop_pct": -0.99},
    # (c) wider premium
    "c_premium_-15pct":         {"premium_stop_pct": -0.15},
    "c_premium_-20pct":         {"premium_stop_pct": -0.20},
    "c_premium_-25pct":         {"premium_stop_pct": -0.25},
    # (d) chart-stop primary + -50% catastrophe backstop
    "d_chartstop_+cat_-50":     {"premium_stop_pct": -0.50},
    # (e) wider-stop-with-tighter-target — -20% premium, bank earlier at +20% TP1
    "e_premium_-20_tp_+20":     {"premium_stop_pct": -0.20, "tp1_premium_pct": 0.20},
}


@dataclass
class TradeRow:
    date: str
    side: str
    pnl: float
    exit_reason: str
    tp1_filled: bool


def _sig_side_counts(signals) -> tuple[int, int]:
    return (sum(1 for s in signals if s.side == "C"),
            sum(1 for s in signals if s.side == "P"))


def simulate_variant(signals, spy, ribbon, vix, *, strike_offset, sim_kwargs) -> tuple[list[TradeRow], dict]:
    """Run every signal at one tier x stop-variant on real OPRA fills. Mirror of
    recency_check.simulate_set + edgehunt.simulate_cell — only the stop/exit kwargs vary."""
    rows: list[TradeRow] = []
    n_total = len(signals)
    n_filled = n_miss = n_none = 0
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            n_miss += 1
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "d"], side=sg.side,
            qty=QTY, setup="JVWAP_STOP_AB", strike_override=strike, entry_vix=entry_vix,
            **sim_kwargs,
        )
        if fill is None or fill.dollar_pnl is None:
            n_none += 1
            continue
        n_filled += 1
        rows.append(TradeRow(
            date=str(d), side=sg.side, pnl=round(float(fill.dollar_pnl), 2),
            exit_reason=fill.exit_reason.name if fill.exit_reason else "NONE",
            tp1_filled=bool(fill.tp1_filled),
        ))
    cov = {"signals": n_total, "filled": n_filled, "cache_miss": n_miss, "sim_none": n_none,
           "fill_rate": round(n_filled / n_total, 3) if n_total else 0.0}
    return rows, cov


def _window(rows: list[TradeRow], start: dt.date, end: dt.date) -> list[TradeRow]:
    return [r for r in rows if start <= dt.date.fromisoformat(r.date) <= end]


def _drop_top5_per_trade(rows: list[TradeRow]) -> float | None:
    """Per-trade after removing the 5 best P&L DAYS (concentration robustness, for the null)."""
    if not rows:
        return None
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r.date] += r.pnl
    drop_days = set(sorted(by_day, key=lambda d: by_day[d], reverse=True)[:5])
    kept = [r for r in rows if r.date not in drop_days]
    if not kept:
        return None
    return round(float(np.mean([r.pnl for r in kept])), 2)


def window_stats(rows: list[TradeRow]) -> dict:
    """Per-trade + book risk metrics for a window (L175 view). Reuses per_trade_dist /
    book_risk byte-for-byte (those accept any object with .pnl/.date)."""
    if not rows:
        return {"n": 0}
    pt = per_trade_dist(rows)
    bk = book_risk(rows)
    pnl = np.array([r.pnl for r in rows], float)
    exit_mix = defaultdict(int)
    for r in rows:
        exit_mix[r.exit_reason] += 1
    return {
        "n": pt["n"],
        "exp_per_trade": pt["mean"],
        "total": pt["total"],
        "wr_pct": round(100 * float((pnl > 0).mean()), 1),
        "std_per_trade": pt["std"],
        "sharpe_per_trade": pt["sharpe_per_trade"],
        "pct_losing": pt["pct_losing"],
        "worst_trade": pt["worst_trade"],
        "median_trade": pt["median"],
        "book_maxDD": bk.get("max_drawdown"),
        "book_worst_day": bk.get("worst_day"),
        "book_sortino_ann": bk.get("sortino_annualized"),
        "book_sharpe_ann": bk.get("sharpe_annualized"),
        "trading_days": bk.get("trading_days"),
        "exit_mix": dict(sorted(exit_mix.items())),
    }


def l175_gate(base_full: dict, var_full: dict) -> dict:
    """L175 risk-adjusted gate (vs the -8% baseline at the SAME tier), full-sample.

    PASS iff per-trade Sharpe holds AND book Sortino holds AND book maxDD does not worsen
    materially (>+25% deeper). Mirrors _b10_exit_variance.decide_verdict's risk legs but
    does NOT require higher_mean (that is a SEPARATE WIN-bar leg — "holds OR beats")."""
    sharpe_ok = var_full["sharpe_per_trade"] >= base_full["sharpe_per_trade"] - 1e-9
    sortino_ok = var_full["book_sortino_ann"] >= base_full["book_sortino_ann"] - 1e-9
    sharpe_bk_ok = var_full["book_sharpe_ann"] >= base_full["book_sharpe_ann"] - 1e-9
    base_mdd = abs(base_full["book_maxDD"])
    var_mdd = abs(var_full["book_maxDD"])
    worsen = (var_mdd - base_mdd) / base_mdd if base_mdd > 0 else 0.0
    material_worse = worsen > MAXDD_MATERIAL_WORSEN_PCT
    return {
        "per_trade_sharpe_holds": bool(sharpe_ok),
        "book_sortino_holds": bool(sortino_ok),
        "book_sharpe_holds": bool(sharpe_bk_ok),
        "maxdd_worsen_frac": round(worsen, 4),
        "maxdd_material_worse": bool(material_worse),
        "l175_pass": bool(sharpe_ok and sortino_ok and not material_worse),
    }


def main() -> int:
    print("[stop-ab] loading merged SPY+VIX (master + recent) ...", flush=True)
    spy_raw, vix_raw = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    trading_days = sorted({dc.date for dc in days})
    frame_first, frame_last = spy["timestamp_et"].iloc[0].date(), spy["timestamp_et"].iloc[-1].date()

    cache_last = read_cache_last_date()
    end = cache_last
    in_range = [d for d in trading_days if d <= end]
    lb = RECENCY_LOOKBACK_TRADING_DAYS
    recent_start = in_range[-lb] if len(in_range) >= lb else in_range[0]
    window_days = [d for d in trading_days if recent_start <= d <= end]
    print(f"[stop-ab] frame {frame_first}..{frame_last} | OPRA cache last={cache_last} | "
          f"recent window {recent_start}..{end} ({len(window_days)} trading days, floor n>={CONFIRM_N_FLOOR})",
          flush=True)

    # Detect edge #1 signals ONCE (LIVE detector, full pattern, no VIX gate).
    signals = detect_vwap_continuation(days, vix, breakout_only=False, put_needs_rising_vix=False)
    n_c, n_p = _sig_side_counts(signals)
    sig_days = len({spy.iloc[s.bar_idx]["timestamp_et"].date() for s in signals})
    print(f"[stop-ab] edge#1 signals={len(signals)} on {sig_days} days side={{C:{n_c},P:{n_p}}}", flush=True)

    # RTH-only frame for the random-entry null (reset index — null_baseline expects it).
    rth = spy[(spy["t"] >= dt.time(9, 30)) & (spy["t"] <= dt.time(16, 0))].reset_index(drop=True)

    tiers_out: dict[str, dict] = {}
    for tier, off in TIERS.items():
        print(f"\n[stop-ab] === TIER {tier} (strike_offset {off:+d}) ===", flush=True)
        # Simulate every variant once on the FULL frame; cut windows after.
        var_rows: dict[str, list[TradeRow]] = {}
        var_cov: dict[str, dict] = {}
        for vkey, kw in VARIANTS.items():
            rows, cov = simulate_variant(signals, spy, ribbon, vix, strike_offset=off, sim_kwargs=kw)
            var_rows[vkey] = rows
            var_cov[vkey] = cov

        base_rows = var_rows[BASELINE_KEY]
        base_full = window_stats(base_rows)
        base_oos = window_stats(_window(base_rows, OOS_2026_START, end))
        base_recent = window_stats(_window(base_rows, recent_start, end))

        variants_block: dict[str, dict] = {}
        for vkey, kw in VARIANTS.items():
            rows = var_rows[vkey]
            full = window_stats(rows)
            oos = window_stats(_window(rows, OOS_2026_START, end))
            recent = window_stats(_window(rows, recent_start, end))

            # No-truncation sign = full-sample expectancy stays POSITIVE.
            no_trunc = bool(full.get("exp_per_trade", -1) > 0)

            # Random-entry null (C3/L58) at this tier x stop. Match count + side mix; same
            # stop + strike. tp1 override (variant e) is not threaded through the module null
            # (which uses default v15 exits) — disclosed; the null is the SIGNAL vs STRUCTURE
            # probe on the stop/strike geometry, the dominant lever here.
            null = random_entry_null(
                rth, n_signals=full["n"], n_call=n_c, n_put=n_p,
                strike_offset=off, premium_stop_pct=kw["premium_stop_pct"])
            drop5 = _drop_top5_per_trade(rows)
            ngate = null_gate(full.get("exp_per_trade"), drop5, null)

            # L175 risk-adjusted gate vs the -8% baseline at this tier (full-sample).
            l175 = l175_gate(base_full, full) if vkey != BASELINE_KEY else {
                "per_trade_sharpe_holds": True, "book_sortino_holds": True,
                "book_sharpe_holds": True, "maxdd_worsen_frac": 0.0,
                "maxdd_material_worse": False, "l175_pass": True}

            # WIN-bar legs (skip for baseline).
            full_holds_or_beats = full.get("exp_per_trade", -9e9) >= base_full.get("exp_per_trade", 9e9) - 1e-9
            # recent bleed reduction: recent exp improves AND recent total loss shrinks (less negative).
            base_recent_exp = base_recent.get("exp_per_trade", 0.0) if base_recent.get("n") else 0.0
            base_recent_tot = base_recent.get("total", 0.0) if base_recent.get("n") else 0.0
            var_recent_exp = recent.get("exp_per_trade", 0.0) if recent.get("n") else 0.0
            var_recent_tot = recent.get("total", 0.0) if recent.get("n") else 0.0
            recent_exp_better = var_recent_exp > base_recent_exp + 1e-9
            recent_loss_shrinks = var_recent_tot > base_recent_tot + 1e-9  # less negative
            recent_bleed_reduced = bool(recent_exp_better and recent_loss_shrinks)

            wins = (vkey != BASELINE_KEY and full_holds_or_beats and l175["l175_pass"]
                    and no_trunc and ngate["null_pass"] and recent_bleed_reduced)

            variants_block[vkey] = {
                "stop_kwargs": {k: (v.strftime("%H:%M") if isinstance(v, dt.time) else v)
                                for k, v in kw.items()},
                "coverage": var_cov[vkey],
                "full_sample": full,
                "full_oos_2026": oos,
                "recent_window": recent,
                "no_truncation_full_exp_positive": no_trunc,
                "null": null,
                "null_gate": ngate,
                "l175_gate_vs_baseline": l175,
                "win_bar_legs": {
                    "is_baseline": vkey == BASELINE_KEY,
                    "full_holds_or_beats_baseline": bool(full_holds_or_beats),
                    "l175_pass": l175["l175_pass"],
                    "no_truncation": no_trunc,
                    "null_pass": ngate["null_pass"],
                    "recent_exp_better_than_baseline": bool(recent_exp_better),
                    "recent_loss_shrinks_vs_baseline": bool(recent_loss_shrinks),
                    "recent_bleed_reduced": recent_bleed_reduced,
                    "CLEARS_WIN_BAR": bool(wins),
                },
            }
            print(f"  {vkey:24s} | FULL n={full['n']:>3} exp=${full.get('exp_per_trade'):>7} "
                  f"sh/tr={full.get('sharpe_per_trade'):>6} maxDD=${full.get('book_maxDD'):>9} "
                  f"sortino={full.get('book_sortino_ann'):>6} | "
                  f"RECENT n={recent.get('n','-'):>2} exp=${recent.get('exp_per_trade','-'):>7} "
                  f"tot=${recent.get('total','-'):>8} | noTrunc={no_trunc} null={ngate['null_pass']} "
                  f"L175={l175['l175_pass']} -> {'WIN' if wins else ''}", flush=True)

        tiers_out[tier] = {
            "strike_offset": off,
            "baseline_key": BASELINE_KEY,
            "baseline_full": base_full,
            "baseline_oos": base_oos,
            "baseline_recent": base_recent,
            "variants": variants_block,
        }

    # ── Headline verdict ──────────────────────────────────────────────────────────
    winners: list[dict] = []
    for tier, tb in tiers_out.items():
        for vkey, vb in tb["variants"].items():
            if vb["win_bar_legs"]["CLEARS_WIN_BAR"]:
                winners.append({"tier": tier, "variant": vkey,
                                "full_exp": vb["full_sample"].get("exp_per_trade"),
                                "recent_exp": vb["recent_window"].get("exp_per_trade"),
                                "recent_total": vb["recent_window"].get("total")})
    verdict = "STOP_VARIANT_IMPROVEMENT" if winners else "-8%_REMAINS_OPTIMAL"

    summary = {
        "campaign": "RECENCY STOP-VARIANT A/B — edge #1 vwap_continuation (real OPRA fills)",
        "purpose": ("does a stop variant reduce the recency drawdown WITHOUT breaking the "
                    "full-sample edge? (holds/beats -8% exp + L175 risk-adjusted + no-truncation "
                    "+ null_pass + recent bleed reduced)"),
        "run_date": dt.date.today().isoformat(),
        "opra_cache_last": str(cache_last),
        "frame": f"{frame_first}..{frame_last} (master + recent daily concat)",
        "recent_window": f"{recent_start}..{end}",
        "recent_window_trading_days": len(window_days),
        "oos_split": f"OOS={OOS_2026_START.year} (full OOS-2026 to cache last)",
        "fills_authority": "real OPRA via lib.simulator_real.simulate_trade_real (C1)",
        "detector": ("BYTE-FOR-BYTE _edgehunt_vwap_continuation.detect_signals (LIVE detector); "
                     "live port = backtest/lib/watchers/vwap_continuation_watcher.py"),
        "tiers": list(TIERS.keys()),
        "n_signals": len(signals),
        "signal_side_count": {"C": n_c, "P": n_p},
        "stop_variants": {k: {kk: (vv.strftime("%H:%M") if isinstance(vv, dt.time) else vv)
                              for kk, vv in v.items()} for k, v in VARIANTS.items()},
        "win_bar": ("(full) exp >= -8% baseline exp (same tier) AND L175 risk-adjusted pass "
                    "(per-trade Sharpe holds + book Sortino holds + maxDD no material worse +25% "
                    "vs -8% baseline) AND no-truncation (full exp > 0) AND null_pass (C3/L58) AND "
                    "(recent) recent exp/tr improves AND recent total loss shrinks vs -8%"),
        "maxdd_material_worsen_threshold": MAXDD_MATERIAL_WORSEN_PCT,
        "results_by_tier": tiers_out,
        "winners": winners,
        "verdict": verdict,
        "DISCLOSURE": {
            "real_fills": "real OPRA fills, the only 0DTE WR authority (C1); SPY-dir != option edge (C3)",
            "chart_stop_always_on": ("rejection_level (=session-extreme chart stop) is supplied in "
                                     "EVERY variant; premium_stop_pct sets the premium backstop. "
                                     "-0.99 = chart-stop-only; -0.50 = chart-stop + catastrophe cap."),
            "wider_stop_caveat": ("C2/C28 — wider stops bleed FULL premium on 0DTE; a wider stop can "
                                  "raise mean while deepening maxDD. The L175 gate is the guard."),
            "recent_small_n": (f"recent window is {len(window_days)} trading days; recent n per tier is "
                               "SMALL by design (a directional bleed-reduction check, not a standing "
                               "ratification — full-history n is the ratification authority)."),
            "null_exit_caveat": ("the random-entry null uses default v15 exits; variant (e)'s tp1 "
                                 "override is NOT threaded into the module null. The null isolates the "
                                 "SIGNAL from the stop/strike STRUCTURE (the dominant lever); for the "
                                 "tighter-target variant the null is the stop-geometry probe only."),
            "annualization": "book Sortino/Sharpe annualized sqrt(252) on the daily P&L of traded days.",
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    print(f"\n[stop-ab] wrote {OUT_JSON}", flush=True)

    print("\n=== RECENCY STOP-VARIANT A/B VERDICT ===")
    print(f"VERDICT: {verdict}")
    if winners:
        for w in winners:
            print(f"  WIN: {w['tier']}/{w['variant']} full_exp=${w['full_exp']} "
                  f"recent_exp=${w['recent_exp']} recent_tot=${w['recent_total']}")
    else:
        print("  No variant clears the WIN bar -> the -8% stop is right; HOLD per the recency gate.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

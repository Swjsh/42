"""Canonical probe statistics — the ONE place significance + concentration live.

Why this module exists (self-audit gap 2026-06-28T17:30:40, items 1+2):

    Every real-fills probe (`range_scalp_probe`, `range_scalp_regime_gated_probe`,
    and the next data-widening slice) was HAND-ROLLING the same two judgments
    inline, with already-divergent vocabulary:

      * statistical significance  -- `if n < 10: verdict = "INCONCLUSIVE"` in one
        probe, `if n_trades < 10: verdict = "REGIME_GATE_TOO_TIGHT"` in the other.
      * concentration             -- `top3_pct_of_net > 150.0` open-coded twice.

    Duplicated thresholds drift (C14 dead/divergent-knob class). A future probe
    that quietly uses `n < 5` or forgets the concentration check would publish a
    "VEIN" on 6 trades and nobody's guard would catch it. This module is the single
    canonical source: probes import `significance`, `day_concentration`, and
    `base_verdict` instead of re-deriving them, so the n<10 / top3>150% policy can
    never silently diverge again.

Yardstick policy baked in (NOT J `edge_capture` -- that directional-anchor metric
auto-rejects range/mean-reversion strategies; see
`_lesson-inbox/2026-06-28-directional-anchor-edgecapture-autorejects-regime-strategies.md`):
    per-trade EXPECTANCY (not WR standalone, C4) + concentration-robust day metrics
    (top-3-day %, median-day, trimmed-day).

Rail-4 CLEAR: pure research/measurement helpers. Touches NO params/doctrine/orders/
heartbeat/filters/CLAUDE; computes statistics only; places no order; arms nothing.
"""
from __future__ import annotations

import statistics
from typing import Mapping, Sequence

# --- canonical thresholds (the single source of truth for both judgments) ------
# A probe below this trade count is statistically inconclusive -- a positive net on
# n<10 is noise, not an edge (C4: per-trade expectancy needs a real sample).
INCONCLUSIVE_MIN_N: int = 10
# A net driven by a handful of days is fragile, not an edge (OP-20 disclosure 6 / C4).
# top-3 days contributing > this % of the net == concentration-fragile.
CONCENTRATION_TOP3_PCT_MAX: float = 150.0


# --- strategy-class yardstick policy (lesson L192) -----------------------------
# J's `edge_capture` (OP-16, 771 floor) is anchored on J's DIRECTIONAL trend-day
# winners (5/14 +$1,208, 5/04 +$730, ...). A regime / mean-reversion strategy is
# flat-to-slightly-negative on big trend days BY CONSTRUCTION (it fades INTO the
# trend), so it can never capture those winners -> edge_capture << 771 -> the gate
# AUTO-REJECTS it before it is ever tested. Match the yardstick to the class:
# directional candidates compete on edge_capture; regime classes are judged on
# per-trade expectancy against a regime-MATCHED anchor (C4 / C24 / L192).
DIRECTIONAL_CLASSES: frozenset = frozenset({
    "directional", "momentum", "continuation", "breakout", "trend",
    "bearish_rejection", "bullish_reclaim", "rejection", "reclaim",
})
REGIME_CLASSES: frozenset = frozenset({
    "range", "mean_reversion", "scalp", "fade", "overnight", "level_fade",
})


def _norm_class(strategy_class: str) -> str:
    """Normalize a class label: lowercase, hyphens -> underscores, trim."""
    return (strategy_class or "").strip().lower().replace("-", "_").replace(" ", "_")


def requires_directional_anchor(strategy_class: str) -> bool:
    """True iff J `edge_capture` (OP-16) is a VALID yardstick for this class.

    Only directional / continuation candidates compete to replicate J's
    directional source-of-truth winners. Regime / mean-reversion classes -- and
    any UNKNOWN class (conservative: don't auto-reject what we can't classify) --
    return False, so they are NOT gated on a metric they can't satisfy."""
    return _norm_class(strategy_class) in DIRECTIONAL_CLASSES


def edge_capture_gate_misapplied(strategy_class: str, gate_uses_edge_capture: bool) -> bool:
    """Lesson L192 detector. A regime / mean-reversion (or unknown) strategy gated
    on `edge_capture < 771` is a MIS-APPLIED gate -- it auto-rejects by
    construction. Returns True when the gate is being mis-applied to such a class."""
    return bool(gate_uses_edge_capture) and not requires_directional_anchor(strategy_class)


def recommended_yardstick(strategy_class: str) -> str:
    """The correct merge yardstick for a strategy class:
        'edge_capture'          -- directional candidates (OP-16 valid)
        'per_trade_expectancy'  -- regime / mean-reversion / unknown (C4, L192)
    """
    return "edge_capture" if requires_directional_anchor(strategy_class) else "per_trade_expectancy"


def summarize_trades(pnls: Sequence[float]) -> dict:
    """Per-trade summary. Keys are a superset of what the probes emit so a probe
    can adopt this and select the subset it publishes without changing schema."""
    n = len(pnls)
    if not n:
        return {
            "n_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "expectancy_per_trade_usd": 0.0, "total_pnl_usd": 0.0,
            "mean_trade_usd": 0.0, "median_trade_usd": 0.0,
            "worst_trade_usd": 0.0, "best_trade_usd": 0.0,
        }
    wins = sum(1 for p in pnls if p > 0)
    total = round(sum(pnls), 2)
    return {
        "n_trades": n,
        "wins": wins,
        "losses": n - wins,
        "win_rate": round(wins / n, 3),
        "expectancy_per_trade_usd": round(total / n, 2),
        "total_pnl_usd": total,
        "mean_trade_usd": round(statistics.mean(pnls), 2),
        "median_trade_usd": round(statistics.median(pnls), 2),
        "worst_trade_usd": round(min(pnls), 2),
        "best_trade_usd": round(max(pnls), 2),
    }


def day_concentration(by_day: Mapping[str, float]) -> dict:
    """Concentration-robust day metrics. `by_day` may contain zero-PnL days (no
    trades); they are excluded from the active/median/trimmed math."""
    nz = {k: v for k, v in by_day.items() if v != 0.0}
    total = round(sum(nz.values()), 2)
    vals = sorted(nz.values(), reverse=True)
    top3_pct = round(100.0 * sum(vals[:3]) / total, 1) if total else None
    # trimmed (drop best + worst day) -- robust to a single dominant day.
    trimmed = vals[1:-1] if len(vals) > 2 else vals
    return {
        "n_active_days": len(nz),
        "n_losing_days": sum(1 for v in nz.values() if v < 0),
        "total_pnl_usd": total,
        "top3_day_pct_of_net": top3_pct,
        "median_day_usd": round(statistics.median(nz.values()), 2) if nz else 0.0,
        "trimmed_day_mean_usd": round(statistics.mean(trimmed), 2) if trimmed else 0.0,
        "trimmed_day_total_usd": round(sum(trimmed), 2) if trimmed else 0.0,
        "by_day_pnl": dict(by_day),
    }


def significance(n: int, min_n: int = INCONCLUSIVE_MIN_N) -> dict:
    """Self-audit gap #1: flag n < min_n as statistically inconclusive."""
    return {
        "n": n,
        "min_n": min_n,
        "sufficient": n >= min_n,
        "note": (
            f"n={n} >= {min_n}: sample sufficient"
            if n >= min_n
            else f"n={n} < {min_n}: INCONCLUSIVE -- a positive net on this few trades "
                 f"is noise, not a confirmed edge; widen the window before concluding"
        ),
    }


def concentration_flag(
    top3_day_pct_of_net: float | None, max_pct: float = CONCENTRATION_TOP3_PCT_MAX
) -> dict:
    """Self-audit gap #2: flag a net whose top-3 days exceed `max_pct` of it."""
    concentrated = top3_day_pct_of_net is not None and top3_day_pct_of_net > max_pct
    return {
        "top3_day_pct_of_net": top3_day_pct_of_net,
        "max_pct": max_pct,
        "concentrated": concentrated,
        "note": (
            "concentration within tolerance"
            if not concentrated
            else f"top-3 days = {top3_day_pct_of_net}% of net (> {max_pct}%): "
                 f"CONCENTRATED -- fragile, not deploy-ready; needs more spread-out days"
        ),
    }


# --- slippage robustness (self-audit gap #3, 2026-06-28T17:30:40) --------------
# Both range-scalp probes reported net-of-slippage at only TWO fixed haircuts
# (0.02 and 0.05 $/share half-spread). The gap: there was no automated SWEEP across
# a range of slippage assumptions, and no single robustness number. The deployable
# question is not "does it survive 0.05?" but "how MUCH slippage can it absorb before
# the edge dies?" -- the breakeven half-spread. An edge whose breakeven sits below
# realistic slippage is not deployable; a high breakeven is a robust edge (C4 / OP-20
# disclosure: state the robustness margin, don't pick a single flattering haircut).
#
# Cost model (matches both committed probes EXACTLY): options quote in $/share, the
# contract multiplier is 100, and a round trip pays the half-spread on BOTH entry and
# exit -> per-trade $ haircut = 2 * half_spread * 100 * qty.
SLIPPAGE_MULTIPLIER: float = 100.0  # standard options contract multiplier
# A round-trip half-spread we treat as "realistic" for 0DTE SPY (the harsh-end
# reference both probes already used). Breakeven >= this == survives realistic slippage.
REALISTIC_SLIPPAGE_HALF_SPREAD: float = 0.05
DEFAULT_SLIPPAGE_GRID: tuple[float, ...] = (0.0, 0.01, 0.02, 0.03, 0.05, 0.075, 0.10)


def slippage_haircut_per_trade(half_spread: float, qty: float) -> float:
    """Round-trip $ haircut for ONE trade of `qty` contracts at `half_spread` $/share
    (charged on entry AND exit, x100 contract multiplier)."""
    return round(2.0 * half_spread * SLIPPAGE_MULTIPLIER * qty, 2)


def net_pnls_after_slippage(
    rows: Sequence[Mapping], half_spread: float,
    pnl_key: str = "dollar_pnl", qty_key: str = "qty",
) -> list[float]:
    """Per-trade $ PnLs after a round-trip half-spread haircut. `rows` is a sequence
    of mappings each carrying a $ PnL (`pnl_key`) and a contract count (`qty_key`)."""
    return [
        round(r[pnl_key] - slippage_haircut_per_trade(half_spread, r[qty_key]), 2)
        for r in rows
    ]


def breakeven_half_spread(
    rows: Sequence[Mapping], pnl_key: str = "dollar_pnl", qty_key: str = "qty",
) -> float | None:
    """The half-spread $/share at which per-trade expectancy crosses to 0.

    Since the haircut is LINEAR in the half-spread, this is exact:
        expectancy_net(h) = mean(pnl) - 2*h*100*mean(qty)
        => breakeven h* = mean(pnl) / (200 * mean(qty))
    Returns None when there are no trades, mean(qty) <= 0, or the gross expectancy is
    already <= 0 (no positive edge to erode -- the edge is DRY at zero slippage)."""
    if not rows:
        return None
    pnls = [r[pnl_key] for r in rows]
    mean_pnl = statistics.mean(pnls)
    mean_qty = statistics.mean([r[qty_key] for r in rows])
    if mean_qty <= 0 or mean_pnl <= 0:
        return None
    return round(mean_pnl / (2.0 * SLIPPAGE_MULTIPLIER * mean_qty), 4)


def slippage_sweep(
    rows: Sequence[Mapping],
    grid: Sequence[float] = DEFAULT_SLIPPAGE_GRID,
    pnl_key: str = "dollar_pnl", qty_key: str = "qty",
    realistic: float = REALISTIC_SLIPPAGE_HALF_SPREAD,
) -> dict:
    """Self-audit gap #3: sweep per-trade expectancy across a RANGE of slippage
    assumptions (not just 2 fixed haircuts) and report the BREAKEVEN half-spread.

    Verdict (slippage robustness only -- significance/concentration are separate):
        DRY_AT_ZERO          -- expectancy <= 0 even with no slippage (no edge)
        FRAGILE_TO_SLIPPAGE  -- positive, but breakeven < `realistic` (dies too soon)
        SURVIVES_REALISTIC   -- positive AND breakeven >= `realistic`
    """
    points = []
    for h in grid:
        net = net_pnls_after_slippage(rows, h, pnl_key, qty_key)
        s = summarize_trades(net)
        points.append({
            "half_spread": h,
            "expectancy_per_trade_usd": s["expectancy_per_trade_usd"],
            "total_pnl_usd": s["total_pnl_usd"],
            "win_rate": s["win_rate"],
            "positive": s["expectancy_per_trade_usd"] > 0,
        })
    be = breakeven_half_spread(rows, pnl_key, qty_key)
    gross_exp = summarize_trades([r[pnl_key] for r in rows])["expectancy_per_trade_usd"]
    if gross_exp <= 0:
        verdict = "DRY_AT_ZERO"
    elif be is not None and be >= realistic:
        verdict = "SURVIVES_REALISTIC"
    else:
        verdict = "FRAGILE_TO_SLIPPAGE"
    return {
        "n_trades": len(rows),
        "gross_expectancy_per_trade_usd": gross_exp,
        "breakeven_half_spread": be,
        "realistic_half_spread": realistic,
        "verdict": verdict,
        "grid": points,
        "note": (
            f"edge breakeven at {be} $/share half-spread "
            f"(realistic reference {realistic}); {verdict}"
            if be is not None
            else f"no positive edge to erode at zero slippage; {verdict}"
        ),
    }


def base_verdict(
    n: int,
    expectancy_per_trade_usd: float,
    top3_day_pct_of_net: float | None,
    min_n: int = INCONCLUSIVE_MIN_N,
    max_top3_pct: float = CONCENTRATION_TOP3_PCT_MAX,
) -> str:
    """Canonical probe verdict ladder (neutral vocabulary). Probes may map these to
    their own labels, but the SIGNIFICANCE + CONCENTRATION decision is centralized:

        INCONCLUSIVE  -- n < min_n (sample too small to conclude anything)
        DRY           -- enough trades, but expectancy <= 0 (no edge)
        CONCENTRATED  -- positive expectancy, but top-3 days > max_top3_pct of net
        CLEAN         -- positive expectancy AND concentration within tolerance
    """
    if n < min_n:
        return "INCONCLUSIVE"
    if expectancy_per_trade_usd <= 0:
        return "DRY"
    if concentration_flag(top3_day_pct_of_net, max_top3_pct)["concentrated"]:
        return "CONCENTRATED"
    return "CLEAN"

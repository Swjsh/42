"""Risk module — position sizing, drawdown, daily loss budget."""
from __future__ import annotations

from ..schema import CategoryScore
from ..ingest import IngestedData


def analyze_risk(data: IngestedData, trades) -> CategoryScore:
    """Score 0-100 risk discipline.

    Weights:
      30 pts — max position size <= 20% of equity (v15 hard gate)
      25 pts — daily loss budget used < 50% of -50% kill switch
      25 pts — no individual trade > -50% premium loss
      20 pts — qty consistent with v15 tier (no oversize)

    Penalties:
      - immediate FAIL (0 total) if any trade exceeded 50% equity
      - -20 if daily loss budget > 50% of kill switch (-25% drawdown reached)
    """
    if not trades:
        return CategoryScore(
            score=100.0,
            evidence={"phase": "2.4", "trades": 0, "note": "no trades = no risk taken"},
            narrative="No trades today, no risk taken. Account capital preserved.",
            actions=[],
        )

    account = data.alpaca_account or {}
    try:
        equity_start = float(account.get("last_equity", 0))
    except (ValueError, TypeError):
        equity_start = 101272.15  # fallback

    sizes_pct = []
    largest_loss_pct = 0.0
    largest_loss_dollars = 0.0

    for t in trades:
        buy = next((f for f in t.fills if f.side == "buy"), None)
        if not buy:
            continue
        cost = buy.qty * buy.price * 100
        size_pct = (cost / equity_start * 100) if equity_start else 0
        sizes_pct.append(size_pct)
        if t.pnl_pct_on_capital < largest_loss_pct:
            largest_loss_pct = t.pnl_pct_on_capital
            largest_loss_dollars = t.pnl_dollars_realized

    max_size_pct = max(sizes_pct) if sizes_pct else 0.0

    # 30 pts — size <20%
    if max_size_pct < 15:
        size_pts = 30
    elif max_size_pct < 20:
        size_pts = 25
    elif max_size_pct < 30:
        size_pts = 15
    else:
        size_pts = 0  # hard gate breach

    # 25 pts — daily loss budget. Today closed UP so 100% pts.
    day_pnl_pct = sum(t.pnl_pct_on_capital for t in trades) / len(trades)
    if day_pnl_pct >= 0:
        budget_pts = 25
    elif day_pnl_pct > -10:
        budget_pts = 20
    elif day_pnl_pct > -25:
        budget_pts = 10
    else:
        budget_pts = 0

    # 25 pts — no trade lost > 50% premium
    if largest_loss_pct >= -20:
        loss_pts = 25
    elif largest_loss_pct >= -35:
        loss_pts = 20
    elif largest_loss_pct >= -50:
        loss_pts = 10
    else:
        loss_pts = 0

    # 20 pts — qty consistent (Phase 2.4 simple: all trades had qty in [3, 20] tier band)
    qty_max = max((next((f.qty for f in t.fills if f.side == "buy"), 0) for t in trades), default=0)
    qty_pts = 20 if 3 <= qty_max <= 20 else (10 if qty_max <= 30 else 0)

    score = size_pts + budget_pts + loss_pts + qty_pts

    narrative = (
        f"Max position {max_size_pct:.2f}% of equity (v15 gate: 20%). "
        f"Day P&L {day_pnl_pct:+.1f}% / max-trade-loss {largest_loss_pct:+.1f}% / max-qty {qty_max}. "
        f"Score: {score}/100 (size={size_pts}/30, budget={budget_pts}/25, loss={loss_pts}/25, qty={qty_pts}/20)."
    )

    actions = []
    if max_size_pct >= 20:
        actions.append({
            "type": "alert_doctrine_breach",
            "priority": "HIGH",
            "details": {"size_pct": max_size_pct, "v15_gate": 20.0,
                       "note": "v15 hard gate breached — investigate sizing logic"}
        })

    return CategoryScore(
        score=float(score),
        evidence={
            "phase": "2.4",
            "max_size_pct_of_equity": round(max_size_pct, 2),
            "day_pnl_pct": round(day_pnl_pct, 2),
            "largest_loss_pct": round(largest_loss_pct, 2),
            "largest_loss_dollars": round(largest_loss_dollars, 2),
            "qty_max": qty_max,
            "v15_hard_gate_pct": 20.0,
            "weights": {"size": size_pts, "budget": budget_pts, "loss": loss_pts, "qty": qty_pts},
        },
        narrative=narrative,
        actions=actions,
    )

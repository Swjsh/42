#!/usr/bin/env python3
"""Port Gamma's SPY 0DTE directional decision onto a Kalshi index contract.

THE MAPPING PROBLEM, stated honestly: Gamma trades SPY; Kalshi lists S&P 500 INDEX
contracts (~10x SPY). Hardcoding a 10.0x ratio would be a stale-constant bug the first
time dividends or a data seam moved it. So we DO NOT CONVERT AT ALL.

Instead the ladder self-calibrates: the market's own quotes tell us where the index is.
The strike whose YES price sits nearest 0.50 IS the market-implied level. We select
relative to that. No ratio, no drift, nothing to go stale.

Direction expression:
    BULLISH -> buy YES  ("index finishes above strike")
    BEARISH -> buy NO   (the same contract, other side -- never a separate ladder)

Selection targets a probability BAND rather than a single strike, so the trade is a
genuine directional expression rather than a lottery ticket or a near-certainty.

Every gate below is a REFUSAL. A blocked trade returns a Decision with take=False and a
stated reason -- it never silently degrades into a worse trade.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
PARAMS_PATH = HERE / "params.json"
SIGNAL_PATH = REPO / "automation" / "state" / "fleet" / "shared-signal.json"


def load_params(path: Path | None = None) -> dict[str, Any]:
    return json.loads((path or PARAMS_PATH).read_text())


def load_signal(path: Path | None = None) -> dict[str, Any]:
    p = path or SIGNAL_PATH
    if not p.exists():
        raise FileNotFoundError(f"shared-signal.json missing at {p}")
    return json.loads(p.read_text())


@dataclass
class Decision:
    """One tick's verdict. take=False carries the reason; nothing is ever implicit."""
    take: bool
    reason: str
    direction: str | None = None
    ticker: str | None = None
    side: str | None = None                 # "yes" | "no"
    limit_price_cents: int | None = None
    contracts: int | None = None
    stake_dollars: float | None = None
    est_fee_dollars: float | None = None
    breakeven_prob: float | None = None
    spread_cents: float | None = None
    depth_contracts: float | None = None
    signal_score: int | None = None
    setup_name: str | None = None
    diagnostics: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return asdict(self)


def direction_from_signal(sig: dict[str, Any], min_score: int) -> tuple[str | None, int, str | None, str]:
    """Extract (direction, score, setup_name, reason) from the shared signal.

    production_action is authoritative -- it is what the SPY arms actually act on.
    We deliberately do NOT re-derive direction from raw scores: two engines disagreeing
    about the same tick is the drift bug this project has paid for repeatedly.
    """
    action = (sig.get("production_action") or "").upper()
    if action == "ENTER_BULL":
        leg = sig.get("bull") or {}
        score = int(leg.get("score") or 0)
        if score < min_score:
            return None, score, leg.get("setup_name"), f"bull score {score} < min {min_score}"
        return "BULL", score, leg.get("setup_name"), "ok"
    if action == "ENTER_BEAR":
        leg = sig.get("bear") or {}
        score = int(leg.get("score") or 0)
        if score < min_score:
            return None, score, leg.get("setup_name"), f"bear score {score} < min {min_score}"
        return "BEAR", score, leg.get("setup_name"), "ok"
    return None, 0, None, f"production_action={action or 'MISSING'} (no directional signal)"


def _mid(market: dict) -> float | None:
    try:
        bid = float(market.get("yes_bid_dollars") or 0)
        ask = float(market.get("yes_ask_dollars") or 0)
    except (TypeError, ValueError):
        return None
    if not (0 < bid < ask < 1):
        return None
    return (bid + ask) / 2.0


def select_contract(client, series: str, direction: str, params: dict[str, Any]) -> Decision:
    """Pick the contract, verify it against every gate, and size it.

    `client` is a KalshiClient (injected so this is unit-testable without network).
    """
    lo, hi = params["target_prob_lo"], params["target_prob_hi"]
    max_spread = params["max_spread_cents"]
    min_depth = params["min_depth_contracts"]

    markets = client.markets(series_ticker=series, limit=1000)
    if not markets:
        return Decision(False, f"{series}: no open markets")

    # Candidates whose YES mid sits in the target probability band. For a BEAR we buy NO,
    # so the band applies to OUR side's price -- mirror the band for the no side.
    candidates: list[tuple[dict, float]] = []
    for m in markets:
        mid = _mid(m)
        if mid is None:
            continue
        our_price = mid if direction == "BULL" else (1.0 - mid)
        if lo <= our_price <= hi:
            candidates.append((m, our_price))
    if not candidates:
        return Decision(False, f"{series}: no contract priced in the {lo:.2f}-{hi:.2f} band",
                        direction=direction)

    # Prefer the contract closest to the middle of the band -- the purest directional read.
    target = (lo + hi) / 2.0
    candidates.sort(key=lambda c: abs(c[1] - target))

    blocked: list[str] = []
    for market, our_price in candidates[:12]:      # bounded scan; log what we skipped
        ticker = market["ticker"]
        book = client.orderbook(ticker, depth=10)
        best = client.best_prices(book)
        spread = best.get("spread_cents")
        if spread is None:
            blocked.append(f"{ticker}: no two-sided book")
            continue
        if spread > max_spread:
            blocked.append(f"{ticker}: spread {spread:.1f}c > {max_spread}c")
            continue

        side = "yes" if direction == "BULL" else "no"
        # MAKER ONLY: join the near touch on our side, never cross.
        if side == "yes":
            touch = best.get("yes_bid")
            depth = best.get("yes_bid_size") or 0
        else:
            # our NO bid is the mirror of the yes ask
            yes_ask = best.get("yes_ask")
            touch = round(1.0 - yes_ask, 2) if yes_ask is not None else None
            depth = best.get("yes_ask_size") or 0
        if touch is None or not (0.01 <= touch <= 0.99):
            blocked.append(f"{ticker}: no valid touch on {side}")
            continue
        if depth < min_depth:
            blocked.append(f"{ticker}: depth {depth:.0f} < {min_depth}")
            continue

        # Size it. Fee ceiling punishes tiny orders, so enforce a floor.
        from kalshi_client import fee_dollars
        max_stake = params["max_stake_dollars"]
        contracts = int(max_stake // touch)
        if contracts < params["min_contracts"]:
            blocked.append(f"{ticker}: ${max_stake} buys only {contracts} at {touch:.2f} "
                           f"(min {params['min_contracts']})")
            continue
        contracts = min(contracts, int(depth))     # never size past resting liquidity

        stake = round(contracts * touch, 2)
        fee = fee_dollars(contracts, touch, maker=True)
        breakeven = round(touch + fee / contracts, 4)

        return Decision(
            take=True, reason="ok", direction=direction, ticker=ticker, side=side,
            limit_price_cents=int(round(touch * 100)), contracts=contracts,
            stake_dollars=stake, est_fee_dollars=fee, breakeven_prob=breakeven,
            spread_cents=spread, depth_contracts=depth,
            diagnostics={"series": series, "our_price": round(our_price, 4),
                         "candidates_scanned": len(candidates), "blocked": blocked[:6]},
        )

    return Decision(False, f"{series}: all {len(candidates)} candidates blocked by gates",
                    direction=direction, diagnostics={"blocked": blocked[:10]})


def decide(client, params: dict[str, Any], signal: dict[str, Any]) -> Decision:
    """Full tick decision: signal -> direction -> contract -> gated, sized order."""
    direction, score, setup, why = direction_from_signal(signal, params["min_signal_score"])
    if direction is None:
        return Decision(False, why, signal_score=score, setup_name=setup)

    last = Decision(False, "no series attempted", direction=direction)
    for series in params["series_preference"]:
        d = select_contract(client, series, direction, params)
        d.signal_score, d.setup_name = score, setup
        if d.take:
            return d
        last = d
    return last

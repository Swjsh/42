#!/usr/bin/env python3
"""Pre-order sizing gate — CLI wrapper over the SINGLE source of truth.

Called from both heartbeat prompts BEFORE any place_option_order call.
Prevents the LLM from skipping the G6/G6b prose gate (2026-06-15 incident:
Bold placed 5x$2.06 = $1,030 = 92% of $1,122 account, violating both the
50% risk cap AND the 40% max-premium gate).

CONSOLIDATION 2026-06-18 (blueprint Phase 2a): this script used to hold its
OWN duplicate copy of the G6/G6b cap logic + tier tables. It now delegates to
`backtest/lib/risk_gate.check_order(...)` — the single implementation built this
session — so there is ONE risk-rule implementation shared by the backtest, the
live heartbeat, and this CLI (backtest-risk == live-risk-intent by construction).

This CLI keeps its narrow 4-argument surface (equity/qty/premium/account) because
that is the exact contract the heartbeat invokes. It is a SIZING gate only: it
exercises the sizing rules of `check_order` (MIN_CONTRACTS, RISK_CAP,
MAX_PREMIUM_TIER) and supplies neutral/clean values for the non-sizing inputs
(kill-switch handled separately by circuit-breaker.json; flat-check + PDT +
first-entry-lock are gates G5/G7/first-entry earlier in the heartbeat). Those
neutral values can only ever ALLOW more, never block more, so this CLI's verdict
is a pure subset of check_order's — it never blocks something the live gate
would pass.

Effective caps are byte-identical to the pre-consolidation CLI:
  * safe: tighter of (per_trade_risk_cap_pct, per-tier max_pct) from params.json
          (0-2k 40%, 2-10k 30%, 10-25k 25%, 25k+ 20%; risk cap 30%).
  * bold: tighter of (50% risk cap, the Bold per-tier table 0-2k 50%, 2-10k 40%,
          10-25k 35%, 25k+ 25%). aggressive/params.json carries no tier table, so
          the Bold table is supplied here (same values the old CLI hardcoded) —
          this is config, not a second rule implementation.

Usage:
  python automation/scripts/pre_order_gate.py \
      --equity 1122 --qty 5 --premium 2.06 --account bold

Exit 0 + prints "PASS: ..." if the trade is within caps.
Exit 1 + prints "BLOCK: ..." if the trade violates any cap.

The heartbeat prompt reads stdout and MUST stop on "BLOCK".
"""
import argparse
import sys
from pathlib import Path

# Import the single source of truth. The repo root is three parents up
# (automation/scripts/pre_order_gate.py -> repo root). backtest/ is on the path
# so `lib.risk_gate` resolves the same module the orchestrator + tests use.
_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "backtest"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.risk_gate import check_order, CODE_RISK_CAP, CODE_MAX_PREMIUM_TIER, CODE_MIN_CONTRACTS


# Per-tier max-premium tables. Safe mirrors params.json#v15_max_premium_pct_of_account.
# Bold's params.json carries NO tier table, so the CLI supplies the same values the
# pre-consolidation CLI enforced (this is account CONFIG, not duplicated rule logic —
# the rule that consumes it lives once, in risk_gate.check_order).
SAFE_MAX_PREMIUM_TIERS = [
    {"equity_min": 0,      "equity_max": 2_000,           "max_pct": 0.40},
    {"equity_min": 2_000,  "equity_max": 10_000,          "max_pct": 0.30},
    {"equity_min": 10_000, "equity_max": 25_000,          "max_pct": 0.25},
    {"equity_min": 25_000, "equity_max": 999_999_999,     "max_pct": 0.20},
]
BOLD_MAX_PREMIUM_TIERS = [
    {"equity_min": 0,      "equity_max": 2_000,           "max_pct": 0.50},
    {"equity_min": 2_000,  "equity_max": 10_000,          "max_pct": 0.40},
    {"equity_min": 10_000, "equity_max": 25_000,          "max_pct": 0.35},
    {"equity_min": 25_000, "equity_max": 999_999_999,     "max_pct": 0.25},
]

# Per-account per-trade risk cap (CLAUDE.md Rule 6). Matches params.json.
SAFE_RISK_CAP = 0.30
BOLD_RISK_CAP = 0.50


def _params_for(account: str) -> dict:
    """Build the minimal params mapping check_order needs for the SIZING rules.

    Only the keys the sizing path reads are populated. daily_loss_kill_switch_pct
    is required by check_order's input hygiene but the kill-switch trigger is
    neutralised below (we pass start_of_day_equity == equity so the realised-
    drawdown branch can never fire from this CLI — kill-switch is owned by
    circuit-breaker.json + heartbeat gate G5).
    """
    if account == "safe":
        return {
            "per_trade_risk_cap_pct": SAFE_RISK_CAP,
            "daily_loss_kill_switch_pct": 0.30,
            "min_contracts": 3,
            "first_entry_after_stop_blocked": True,
            "v15_max_premium_pct_of_account": SAFE_MAX_PREMIUM_TIERS,
        }
    return {
        "per_trade_risk_cap_pct": BOLD_RISK_CAP,
        "daily_loss_kill_switch_pct": 0.50,
        "min_contracts": 5,
        "first_entry_after_stop_blocked": True,
        "v15_max_premium_pct_of_account": BOLD_MAX_PREMIUM_TIERS,
    }


def check(equity: float, qty: int, premium: float, account: str) -> "tuple[bool, str]":
    """Sizing-gate verdict, delegated to the single source of truth.

    Returns (passed, message). message starts with "PASS: " or "BLOCK: " so the
    heartbeat can branch on the prefix exactly as before.
    """
    params = _params_for(account)
    decision = check_order(
        "Gamma-Safe-2" if account == "safe" else "Gamma-Risky-2",
        equity=equity,
        # Neutralise the non-sizing rules so ONLY the sizing caps can bind here
        # (this CLI is the G6/G6b sizing gate; G5/G7/flat/first-entry run earlier
        # in the heartbeat). start_of_day == equity => no realised-drawdown trip.
        start_of_day_equity=equity,
        proposed_qty=qty,
        premium=premium,
        setup_name="PRE_ORDER_SIZING_CHECK",
        current_position_status=None,      # flat — NOT_FLAT cannot fire here
        day_trades_used_5d=0,              # PDT handled by heartbeat G7
        kill_switch_tripped=False,         # kill-switch handled by heartbeat G5
        prior_stops_today=(),              # first-entry-lock handled in heartbeat
        params=params,
    )

    if decision.allowed:
        notional = qty * premium * 100.0
        return True, (
            f"PASS: cost=${notional:.0f} "
            f"({notional/equity:.1%} of ${equity:.0f} equity) [{decision.reason}]"
        )

    # Only sizing denials are reachable given the neutralised inputs above; map
    # them all to the BLOCK prefix the heartbeat keys on.
    return False, f"BLOCK: [{decision.code}] {decision.reason}"


def main() -> None:
    p = argparse.ArgumentParser(description="Pre-order sizing gate (G6+G6b) — delegates to lib.risk_gate")
    p.add_argument("--equity", type=float, required=True, help="Current account equity")
    p.add_argument("--qty", type=int, required=True, help="Proposed contract quantity")
    p.add_argument("--premium", type=float, required=True, help="Option mid price per contract")
    p.add_argument("--account", choices=["safe", "bold"], default="safe")
    args = p.parse_args()

    passed, msg = check(args.equity, args.qty, args.premium, args.account)
    print(msg)
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()

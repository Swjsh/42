#!/usr/bin/env python3
"""Kalshi unit economics — what edge do we need, and what does it actually pay?

Answers "is it profitable / how profitable" the only honest way available before we
have fills: compute the FRICTION exactly, then show what a given edge produces.
This is a sensitivity model. It does NOT claim we have any edge.

VERIFIED FEE FACTS (2026-08-09, two independent sources agreeing):
  taker fee = ceil(0.07   * C * P * (1-P))   -- ceiling on the ORDER TOTAL, not per contract
  maker fee = ceil(0.0175 * C * P * (1-P))   -- exactly 25% of taker
  no settlement fee, no inactivity fee, no data fee, no overnight/carry fee
  P in dollars 0.01-0.99, C = contract count

STRUCTURAL CONSEQUENCE most people miss: a contract held to settlement pays the fee
ONCE (on entry). There is no exit fee if it settles. Unlike options, there is no
theta, no spread paid on the way out, and no assignment risk. Round-tripping early
pays twice; holding to settlement pays once.
"""

from __future__ import annotations

import math

TAKER_RATE = 0.07
MAKER_RATE = 0.0175


def fee(contracts: int, price: float, maker: bool = False) -> float:
    """Exact Kalshi fee in dollars for one order. Ceiling applies to the order total."""
    rate = MAKER_RATE if maker else TAKER_RATE
    return math.ceil(rate * contracts * price * (1 - price) * 100) / 100


def fee_per_contract(price: float, maker: bool = False, size: int = 100) -> float:
    return fee(size, price, maker) / size


def kelly_fraction(q: float, price: float) -> float:
    """Optimal bankroll fraction for a binary at price P with true probability q."""
    if price <= 0 or price >= 1 or q <= price:
        return 0.0
    return (q - price) / (1 - price)


def rule(title: str, width: int = 96) -> None:
    print("\n" + "=" * width)
    print(title)
    print("=" * width)


# ---------------------------------------------------------------- 1. friction
rule("1. FRICTION — fee per contract by price (order size 100, ceiling negligible at this size)")
print(f"{'PRICE':>7}{'TAKER':>10}{'MAKER':>10}{'TAKER %stake':>15}{'MAKER %stake':>15}"
      f"{'breakeven q (taker)':>22}")
print("-" * 96)
for p in (0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 0.95):
    t, m = fee_per_contract(p, False), fee_per_contract(p, True)
    print(f"{p:>7.2f}{t*100:>9.2f}c{m*100:>9.2f}c{t/p*100:>14.2f}%{m/p*100:>14.2f}%"
          f"{p + t:>21.4f}")
print("\n  Fee peaks at P=0.50 (max uncertainty) and vanishes at the extremes.")
print("  As a %% of capital staked, cheap longshots are the MOST fee-punished.")

# ------------------------------------------------------- 2. maker vs taker
rule("2. THE MAKER/TAKER DECISION — the single biggest lever on this venue")
print(f"{'PRICE':>7}{'take+cross spread':>20}{'post as maker':>16}{'edge saved (pp)':>18}{'ratio':>10}")
print("-" * 96)
print("  (assumes the 1-2c spreads actually measured in the liquidity survey)")
for p, spread in ((0.20, 0.02), (0.35, 0.02), (0.50, 0.02), (0.50, 0.01), (0.65, 0.01), (0.80, 0.01)):
    take = fee_per_contract(p, False) + spread / 2   # cross the half-spread
    post = fee_per_contract(p, True)                 # earn the spread instead of paying it
    print(f"{p:>7.2f}{take*100:>19.2f}c{post*100:>15.2f}c{(take-post)*100:>17.2f}{take/post:>9.1f}x")
print("\n  >> Posting instead of taking cuts required edge by ~3-6x.")
print("  >> ANY Kalshi lane must be a LIMIT-ORDER (maker) design. A market-order bot")
print("     would need several points of edge just to break even.")

# --------------------------------------------------- 3. order-size ceiling
rule("3. ORDER-SIZE EFFECT — the ceiling punishes small orders")
print(f"{'CONTRACTS':>11}{'fee @P=0.50':>14}{'per contract':>15}{'vs raw formula':>17}")
print("-" * 96)
raw = TAKER_RATE * 0.50 * 0.50
for c in (1, 2, 5, 10, 25, 50, 100, 500):
    f = fee(c, 0.50)
    print(f"{c:>11}{f:>13.2f}${f/c*100:>14.3f}c{f/c/raw:>16.2f}x")
print("\n  >> 1-contract orders pay ~14% over the formula rate. Batch to 25+ contracts.")

# ------------------------------------------------------ 4. EV sensitivity
rule("4. WHAT IT PAYS — net EV per $1,000 deployed, held to settlement (maker fees)")
print("  Read: 'if our probability estimate beats the market by X points, we earn Y'")
print(f"\n{'EDGE (pp)':>11}", end="")
prices = (0.20, 0.35, 0.50, 0.65, 0.80)
for p in prices:
    print(f"{'P=' + format(p, '.2f'):>13}", end="")
print()
print("-" * 96)
for edge_pp in (1, 2, 3, 5, 8, 12):
    print(f"{edge_pp:>11}", end="")
    for p in prices:
        edge = edge_pp / 100.0
        contracts = 1000.0 / p                    # $1,000 fully deployed at price P
        net = (edge - fee_per_contract(p, True)) * contracts
        print(f"{net:>12.0f}$", end="")
    print()
print("\n  Same edge is worth far more at LOW prices: $1,000 buys 5,000 contracts at 20c")
print("  but only 1,250 at 80c. Edge is earned per CONTRACT, not per dollar.")
print("  Caveat: low-price markets are also where fee-as-%-of-stake is worst, and")
print("  where variance is brutal -- a 20c book wins 1 time in 5.")

# ------------------------------------------------------ 5. required edge
rule("5. BREAKEVEN — how right do we have to be?")
print(f"{'PRICE':>7}{'maker breakeven q':>21}{'taker breakeven q':>21}{'taker + 2c spread':>21}")
print("-" * 96)
for p in (0.20, 0.35, 0.50, 0.65, 0.80):
    print(f"{p:>7.2f}{p + fee_per_contract(p, True):>21.4f}"
          f"{p + fee_per_contract(p, False):>21.4f}"
          f"{p + fee_per_contract(p, False) + 0.01:>21.4f}")
print("\n  At P=0.50 a maker needs to be right 50.44%% of the time to break even.")
print("  A taker crossing a 2c spread needs 52.75%%. That gap IS the strategy.")

# ------------------------------------------------------ 6. bankroll math
rule("6. BANKROLL SCENARIOS — what deposit size actually supports")
print(f"{'DEPOSIT':>10}{'contracts @50c':>17}{'Kelly @3pp edge':>18}{'per-trade $':>14}"
      f"{'trades/day for $100':>22}")
print("-" * 96)
for bank in (100, 500, 1000, 2500, 5000, 10000):
    q, p = 0.53, 0.50
    kf = kelly_fraction(q, p)
    stake = bank * kf
    ev_per_trade = stake / p * (0.03 - fee_per_contract(p, True_ := True))
    need = (100 / ev_per_trade) if ev_per_trade > 0 else float("inf")
    print(f"{bank:>9}${bank/p:>16.0f}{kf*100:>17.1f}%{stake:>13.0f}${need:>21.0f}")
print("\n  Full Kelly is far too aggressive to run in practice -- most desks run 1/4 Kelly.")
print("  The right-hand column is the reality check on the $100/day target:")
print("  at a 3pp edge, small bankrolls need implausible trade counts to clear $100/day.")

# ------------------------------------------ 6b. capital required for $100/day
rule("6b. CAPITAL REQUIRED for $100/day  <-- THE decision number")
print("  There is NO LEVERAGE on Kalshi. A contract costs what it costs and pays at most")
print("  $1. Returns scale with CAPITAL, not with cleverness. This is the fundamental")
print("  difference from 0DTE options and it governs everything below.\n")
print(f"{'EDGE':>6}{'KELLY':>10}", end="")
trade_counts = (1, 3, 10, 30)
for n in trade_counts:
    print(f"{str(n) + ' trades/day':>16}", end="")
print()
print("-" * 96)
P0 = 0.50
net_edge_at = lambda e: e - fee_per_contract(P0, True)  # noqa: E731
for edge_pp in (2, 3, 5, 10):
    e = edge_pp / 100.0
    kf_full = kelly_fraction(P0 + e, P0)
    for name, k in (("full", kf_full), ("1/4", kf_full / 4)):
        print(f"{str(edge_pp) + 'pp':>6}{name:>10}", end="")
        for n in trade_counts:
            per_dollar = (k / P0) * net_edge_at(e)      # daily profit per $1 of bankroll
            need = 100.0 / (n * per_dollar) if per_dollar > 0 else float("inf")
            print(f"{('$' + format(need, ',.0f')):>16}", end="")
        print()
print("\n  >> At a realistic 3pp edge and prudent 1/4 Kelly, $100/day needs roughly")
print("     $13k (10 trades/day) to $43k (3 trades/day) of deployed capital.")
print("  >> A $1-2k Kalshi bankroll is a RESEARCH account, not an income account.")
print("     Sizing it like the 0DTE arms would be a category error.")

# --------------------------------------------------------- 7. vs the 0DTE lane
rule("7. STRUCTURAL COMPARISON vs the 0DTE SPY lane")
rows = [
    ("Time decay",        "theta bleeds every minute",    "NONE - price is a probability"),
    ("Exit friction",     "pay spread + fee on the way out", "ZERO if held to settlement"),
    ("Max loss",          "premium (can be 100%)",        "stake (defined, always)"),
    ("Strike selection",  "a whole ratified subsystem",   "no such problem"),
    ("Payoff shape",      "continuous, path-dependent",   "binary, path-INdependent"),
    ("Fee per round trip","commission + wide OPRA spread","0.44c-1.75c per contract"),
    ("Hours",             "09:30-16:00 ET",               "24/7 in several categories"),
    ("Capacity",          "deep, effectively unlimited",  "THIN - the binding constraint"),
    ("Tax",               "clean 1099-B",                 "UNSETTLED (see doc)"),
]
print(f"{'DIMENSION':<20}{'0DTE SPY OPTIONS':<34}{'KALSHI EVENT CONTRACTS'}")
print("-" * 96)
for a, b, c in rows:
    print(f"{a:<20}{b:<34}{c}")

print("\n" + "=" * 96)
print("BOTTOM LINE: friction is LOW (0.44c/contract as a maker at the money) and")
print("structurally cleaner than options -- no theta, no exit cost, defined risk.")
print("Low friction is NECESSARY, NOT SUFFICIENT. Nothing here demonstrates edge.")
print("The binding constraint is CAPACITY (book depth), which remains UNMEASURED.")
print("=" * 96)

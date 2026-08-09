#!/usr/bin/env python3
"""What a small Kalshi bankroll can actually compound to -- and what kills it.

Written 2026-08-09 against a real question: "$10 seed, can we make $5/day and compound it?"

The honest framing: on a binary contract there is no leverage, so a daily dollar target maps
DIRECTLY onto a required edge. State the target, and the arithmetic tells you how right you
would have to be. It does not negotiate.

Second, and less obvious: the way small accounts die is not absence of edge. It is OVER-BETTING
a real one. A 3-point edge at 50c justifies risking ~6% of bankroll per trade. Betting the whole
stack is ~16x Kelly, which is a ruin path even when the edge is genuinely there. This model
prices that.

No network. Pure arithmetic + Monte Carlo.
"""

from __future__ import annotations

import random
import statistics

TRIALS = 20_000
SEED = 42


def kelly(q: float, price: float) -> float:
    """Optimal fraction of bankroll to stake on a binary at `price` with true probability `q`."""
    if q <= price:
        return 0.0
    return (q - price) / (1 - price)


def maker_fee_per_contract(price: float) -> float:
    return 0.0175 * price * (1 - price)


def required_edge_for_target(target: float, bankroll: float, price: float,
                             trades_per_day: int) -> float:
    """Edge (in probability points) needed to earn `target` dollars per day."""
    capital_per_trade = bankroll / max(trades_per_day, 1)
    contracts = capital_per_trade / price
    if contracts <= 0:
        return float("inf")
    need_per_contract = target / (trades_per_day * contracts)
    return need_per_contract + maker_fee_per_contract(price)


def simulate(bankroll: float, edge: float, price: float, fraction: float,
             days: int, trades_per_day: int = 1, ruin_floor: float = 2.0) -> dict:
    """Monte Carlo the bankroll path. Ruin = falls below the minimum viable order size."""
    rng = random.Random(SEED)
    q = price + edge
    win_mult = (1 - price) / price
    finals, ruined = [], 0
    for _ in range(TRIALS):
        b = bankroll
        dead = False
        for _ in range(days * trades_per_day):
            if b < ruin_floor:
                dead = True
                break
            stake = b * fraction
            contracts = stake / price
            b -= maker_fee_per_contract(price) * contracts      # fee is paid on entry, once
            if rng.random() < q:
                b += stake * win_mult
            else:
                b -= stake
        if dead or b < ruin_floor:
            ruined += 1
            b = min(b, ruin_floor)
        finals.append(b)
    finals.sort()
    return {
        "median": statistics.median(finals),
        "p10": finals[int(0.10 * TRIALS)],
        "p90": finals[int(0.90 * TRIALS)],
        "ruin_pct": 100.0 * ruined / TRIALS,
        "mean": statistics.mean(finals),
    }


def rule(t: str) -> None:
    print("\n" + "=" * 94)
    print(t)
    print("=" * 94)


# ------------------------------------------------ 1. what the target demands
rule("1. WHAT '$5/DAY' ACTUALLY REQUIRES  (P=0.50, maker fees, full bankroll deployed)")
print(f"{'BANKROLL':>10}{'TARGET/DAY':>13}{'% PER DAY':>12}{'EDGE NEEDED':>15}   VERDICT")
print("-" * 94)
for bank, target in ((10, 5), (10, 1), (10, 0.50), (100, 5), (500, 5), (1000, 5), (2500, 5)):
    need = required_edge_for_target(target, bank, 0.50, 1)
    pct = 100 * target / bank
    if need > 0.20:
        verdict = "IMPOSSIBLE - market would have to be broken"
    elif need > 0.08:
        verdict = "not realistic"
    elif need > 0.04:
        verdict = "elite-only, unproven"
    else:
        verdict = "plausible IF an edge is validated"
    print(f"{bank:>9}${target:>12}${pct:>11.1f}%{need * 100:>14.1f}pp   {verdict}")
print("\n  Pro sports bettors live at 2-4pp. A 25pp edge means the market is wrong by 25")
print("  points, repeatedly, and only we notice. That is not a strategy, it is a fantasy.")

# ------------------------------------------------------ 2. over-betting kills
rule("2. THE REAL KILLER: OVER-BETTING A *REAL* EDGE  ($10, genuine 3pp edge, 90 days)")
k = kelly(0.53, 0.50)
print(f"  full Kelly at a 3pp edge on a 50c contract = {k * 100:.1f}% of bankroll per trade\n")
print(f"{'BET SIZE':>22}{'vs KELLY':>11}{'MEDIAN':>10}{'p10':>9}{'p90':>10}{'RUIN':>9}")
print("-" * 94)
for label, frac in (("100% (all-in)", 1.00), ("50%", 0.50), ("25%", 0.25),
                    ("12% (2x Kelly)", 0.12), ("6% (full Kelly)", k), ("1.5% (1/4 Kelly)", k / 4)):
    r = simulate(10.0, 0.03, 0.50, frac, days=90)
    print(f"{label:>22}{frac / k:>10.1f}x{r['median']:>9.2f}${r['p10']:>8.2f}${r['p90']:>9.2f}${r['ruin_pct']:>8.1f}%")
print("\n  Same edge, same 90 days, every row. The ONLY difference is bet size.")
print("  Chasing a big daily number forces the top rows -- which is how the edge gets you broke.")

# ---------------------------------------------------- 3. honest compounding
rule("3. WHAT $10 HONESTLY COMPOUNDS TO  (validated 3pp edge, 1/4 Kelly, 1 trade/day)")
print(f"{'DAYS':>7}{'MEDIAN':>11}{'p10':>10}{'p90':>11}{'RUIN':>9}")
print("-" * 94)
for d in (30, 90, 180, 365):
    r = simulate(10.0, 0.03, 0.50, k / 4, days=d)
    print(f"{d:>7}{r['median']:>10.2f}${r['p10']:>9.2f}${r['p90']:>10.2f}${r['ruin_pct']:>8.1f}%")
print("\n  Survives, grows, and is worth ~pennies a day in absolute dollars. That is the")
print("  honest shape of compounding a $10 stake: the PERCENTAGE is excellent, the")
print("  DOLLARS are small, and only capital fixes the dollars.")

# ------------------------------------------------------ 4. what fixes dollars
rule("4. WHAT ACTUALLY MOVES THE DOLLARS  (3pp edge, 1/4 Kelly, 1 trade/day, 90 days)")
print(f"{'START':>10}{'MEDIAN AFTER 90d':>20}{'GAIN':>12}{'~$/DAY':>10}{'RUIN':>9}")
print("-" * 94)
for bank in (10, 50, 100, 500, 1000, 5000):
    r = simulate(float(bank), 0.03, 0.50, k / 4, days=90)
    gain = r["median"] - bank
    print(f"{bank:>9}${r['median']:>19.2f}${gain:>11.2f}${gain / 90:>9.3f}${r['ruin_pct']:>8.1f}%")
print("\n  The percentage return is IDENTICAL in every row -- edge is scale-free.")
print("  Only the capital column changes the dollars. There is no way around that.")

rule("BOTTOM LINE")
print("""
  * $5/day on $10 needs a ~25pp edge. That is not achievable; it is a coin-flip
    dressed as a plan. You could hit it once by buying a longshot -- and the
    expected value of doing that repeatedly is negative after fees.

  * The compounding instinct is CORRECT. The target is just mis-scaled to the
    bankroll. Percentage compounding at $10 is real but pays pennies.

  * At $10 the product is not dollars -- it is a VALIDATED EDGE plus real fills.
    An edge proven at $10 is worth exactly as much at $5,000. Capital is the
    easy part to add later; a proven edge is not.

  * The fastest genuine route to $5/day is therefore NOT a bigger bet. It is
    finishing calibration, proving the edge is real, and THEN funding it.
""")

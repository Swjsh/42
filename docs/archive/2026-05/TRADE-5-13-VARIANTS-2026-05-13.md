# 5/13 BULLISH_RECLAIM Variant Grid (Real OPRA Fills)

_Generated 2026-05-13T21:34:29 ET_

**Trade replayed:** Production v14 fired at 11:38 ET; trigger bar 11:30 close;
entry on 11:35 bar open. SPY spot at trigger close = **$739.59**, ATM = **740C**.
Setup: BULLISH_RECLAIM_RIDE_THE_RIBBON. Rejection level: 738.1. Side: long calls.

**Variants tested (per the task's locked exit knobs + a no-lock control):**

| Variant  | profit_lock_threshold | profit_lock_offset | premium_stop |
| -------- | --------------------- | ------------------ | ------------ |
| `locked` | +5%  (arm at entry×1.05) | +10% (floor at entry×1.10) | -20% |
| `no_lock`| 0 (disabled)             | 0                          | -20% |

**Grid axes:** 7 strikes × 7 qtys × 5 TP1% × 3 TP1frac × 3 runner-pct × 2 variants = **4410 combos** (2205 per variant)
Blocked combos: **0** (OPRA cache holes)
Slippage: entry +$0.02/contract (ASK proxy), exit -$0.02/contract (BID proxy).

**Ground truth:** J's actual fill 738C × 15 @ $2.10. Scaled out in equal thirds at
$2.80 / $5.43 / $4.32 → gross +$3,125 (+99%); task reports +$2,932 (+93%) post-fees.
Simulator entry premium for 738C: **$2.03** (vs J's $2.10 fill).

**Note:** The 2-tier simulator (TP1+runner) does NOT perfectly match J's 3-way scale-out.
J's effective TP1 was ~+33%; my grid quantises at +30/+50/+75/+100/+150%.

---

## CRITICAL FINDING — profit-lock dominance

Under the **locked** variant (profit_lock_threshold=5%, offset=10%), all
**2205 combos collapse to 49 unique P&L outcomes across
49 (strike, qty) cells — i.e. exactly one outcome per cell.**

By contrast, the **no_lock** variant produced **772 unique P&L outcomes**
across 49 (strike, qty) cells — showing TP1%/TP1-frac/runner-target
actually discriminate between combos when profit-lock is disabled.

**Why:** The 11:50 ET bar low on 738C was $1.96, which is below the profit-lock floor
of entry×1.10 = $2.23 (which was armed at the 11:40 bar high of $2.52).
Every TP1 threshold ≥+10% in the grid is ABOVE the profit-lock arm threshold, so
profit-lock arms first, then stops the trade at ~$2.23 on the 11:50 retrace.
Net: trade always exits at ~+10% no matter which TP1/runner knobs are picked.

**Implication:** For an explosive bullish-reclaim like 5/13, the locked profit-lock
policy CAPS gains at ~+10% per contract. J's actual +93% trade only worked because he
did NOT have profit-lock active — he held through the 11:50-12:05 retrace and let
the runner extend to 738C peak of $5.80.

---

## TL;DR — Best LOCKED combo per account scenario (the task's main ask)

> All cells in the locked variant collapse to one outcome — TP1/runner knobs don't matter.
> The only knobs that change locked P&L are **strike** (entry premium) and **qty** (scale).

| Strike | K | Qty | TP1% | TP1frac | Runner | Lock | Entry$ | Cost$ | P&L$ | %Gain | %1K | %98K | ExitReason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ITM-2 | 738 | 2 | +30% | 0.333 | 1.50x | locked | $2.03 | $406 | $+41 | +10.0% | 40.6% | 0.4% | EXIT_ALL_PREMIUM_STOP |  ← **$1K account (≤50% = $500 cost)**

| Strike | K | Qty | TP1% | TP1frac | Runner | Lock | Entry$ | Cost$ | P&L$ | %Gain | %1K | %98K | ExitReason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ITM-2 | 738 | 15 | +30% | 0.333 | 1.50x | locked | $2.03 | $3,045 | $+304 | +10.0% | 304.5% | 3.1% | EXIT_ALL_PREMIUM_STOP |  ← **$10K account (≤50% = $5,000 cost)**

| Strike | K | Qty | TP1% | TP1frac | Runner | Lock | Entry$ | Cost$ | P&L$ | %Gain | %1K | %98K | ExitReason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ITM-2 | 738 | 15 | +30% | 0.333 | 1.50x | locked | $2.03 | $3,045 | $+304 | +10.0% | 304.5% | 3.1% | EXIT_ALL_PREMIUM_STOP |  ← **$98K account (≤50% = $49,000 cost)**

---

## CONTRAST — Best NO-LOCK combo per account scenario (what the trade could have made)

| Strike | K | Qty | TP1% | TP1frac | Runner | Lock | Entry$ | Cost$ | P&L$ | %Gain | %1K | %98K | ExitReason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OTM+1 | 741 | 10 | +150% | 0.333 | 5.00x | no_lock | $0.39 | $390 | $+1,540 | +395.0% | 39.0% | 0.4% | TP1_THEN_RUNNER_TARGET |  ← **$1K account, no profit-lock**

| Strike | K | Qty | TP1% | TP1frac | Runner | Lock | Entry$ | Cost$ | P&L$ | %Gain | %1K | %98K | ExitReason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ITM-2 | 738 | 15 | +150% | 0.333 | 1.50x | no_lock | $2.03 | $3,045 | $+4,568 | +150.0% | 304.5% | 3.1% | TP1_THEN_RUNNER_TARGET |  ← **Overall no-lock champion (any cost)**

---

## Top 10 by absolute $ P&L — LOCKED (per task spec)

| Strike | K | Qty | TP1% | TP1frac | Runner | Lock | Entry$ | Cost$ | P&L$ | %Gain | %1K | %98K | ExitReason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ITM-2 | 738 | 15 | +30% | 0.333 | 1.50x | locked | $2.03 | $3,045 | $+304 | +10.0% | 304.5% | 3.1% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 15 | +30% | 0.333 | 2.50x | locked | $2.03 | $3,045 | $+304 | +10.0% | 304.5% | 3.1% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 15 | +30% | 0.333 | 5.00x | locked | $2.03 | $3,045 | $+304 | +10.0% | 304.5% | 3.1% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 15 | +30% | 0.500 | 1.50x | locked | $2.03 | $3,045 | $+304 | +10.0% | 304.5% | 3.1% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 15 | +30% | 0.500 | 2.50x | locked | $2.03 | $3,045 | $+304 | +10.0% | 304.5% | 3.1% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 15 | +30% | 0.500 | 5.00x | locked | $2.03 | $3,045 | $+304 | +10.0% | 304.5% | 3.1% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 15 | +30% | 0.667 | 1.50x | locked | $2.03 | $3,045 | $+304 | +10.0% | 304.5% | 3.1% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 15 | +30% | 0.667 | 2.50x | locked | $2.03 | $3,045 | $+304 | +10.0% | 304.5% | 3.1% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 15 | +30% | 0.667 | 5.00x | locked | $2.03 | $3,045 | $+304 | +10.0% | 304.5% | 3.1% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 15 | +50% | 0.333 | 1.50x | locked | $2.03 | $3,045 | $+304 | +10.0% | 304.5% | 3.1% | EXIT_ALL_PREMIUM_STOP |

## Top 10 by % gain — LOCKED (per task spec, J's preferred metric)

| Strike | K | Qty | TP1% | TP1frac | Runner | Lock | Entry$ | Cost$ | P&L$ | %Gain | %1K | %98K | ExitReason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ITM-2 | 738 | 1 | +30% | 0.333 | 1.50x | locked | $2.03 | $203 | $+20 | +10.0% | 20.3% | 0.2% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 1 | +30% | 0.333 | 2.50x | locked | $2.03 | $203 | $+20 | +10.0% | 20.3% | 0.2% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 1 | +30% | 0.333 | 5.00x | locked | $2.03 | $203 | $+20 | +10.0% | 20.3% | 0.2% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 1 | +30% | 0.500 | 1.50x | locked | $2.03 | $203 | $+20 | +10.0% | 20.3% | 0.2% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 1 | +30% | 0.500 | 2.50x | locked | $2.03 | $203 | $+20 | +10.0% | 20.3% | 0.2% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 1 | +30% | 0.500 | 5.00x | locked | $2.03 | $203 | $+20 | +10.0% | 20.3% | 0.2% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 1 | +30% | 0.667 | 1.50x | locked | $2.03 | $203 | $+20 | +10.0% | 20.3% | 0.2% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 1 | +30% | 0.667 | 2.50x | locked | $2.03 | $203 | $+20 | +10.0% | 20.3% | 0.2% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 1 | +30% | 0.667 | 5.00x | locked | $2.03 | $203 | $+20 | +10.0% | 20.3% | 0.2% | EXIT_ALL_PREMIUM_STOP |
| ITM-2 | 738 | 1 | +50% | 0.333 | 1.50x | locked | $2.03 | $203 | $+20 | +10.0% | 20.3% | 0.2% | EXIT_ALL_PREMIUM_STOP |

## Top 10 by absolute $ P&L — NO LOCK (control, profit-lock disabled)

| Strike | K | Qty | TP1% | TP1frac | Runner | Lock | Entry$ | Cost$ | P&L$ | %Gain | %1K | %98K | ExitReason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| ITM-2 | 738 | 15 | +150% | 0.333 | 1.50x | no_lock | $2.03 | $3,045 | $+4,568 | +150.0% | 304.5% | 3.1% | TP1_THEN_RUNNER_TARGET |
| ITM-2 | 738 | 15 | +150% | 0.500 | 1.50x | no_lock | $2.03 | $3,045 | $+4,568 | +150.0% | 304.5% | 3.1% | TP1_THEN_RUNNER_TARGET |
| ITM-2 | 738 | 15 | +150% | 0.667 | 1.50x | no_lock | $2.03 | $3,045 | $+4,568 | +150.0% | 304.5% | 3.1% | TP1_THEN_RUNNER_TARGET |
| ITM-1 | 739 | 15 | +150% | 0.333 | 2.50x | no_lock | $1.31 | $1,965 | $+4,258 | +216.7% | 196.5% | 2.0% | TP1_THEN_RUNNER_TARGET |
| ITM-2 | 738 | 15 | +150% | 0.667 | 2.50x | no_lock | $2.03 | $3,045 | $+4,200 | +137.9% | 304.5% | 3.1% | TP1_THEN_RUNNER_TIME |
| ITM-2 | 738 | 15 | +150% | 0.667 | 5.00x | no_lock | $2.03 | $3,045 | $+4,200 | +137.9% | 304.5% | 3.1% | TP1_THEN_RUNNER_TIME |
| ITM-2 | 738 | 15 | +100% | 0.333 | 1.50x | no_lock | $2.03 | $3,045 | $+4,060 | +133.3% | 304.5% | 3.1% | TP1_THEN_RUNNER_TARGET |
| ITM-2 | 738 | 15 | +150% | 0.500 | 2.50x | no_lock | $2.03 | $3,045 | $+4,053 | +133.1% | 304.5% | 3.1% | TP1_THEN_RUNNER_TIME |
| ITM-2 | 738 | 15 | +150% | 0.500 | 5.00x | no_lock | $2.03 | $3,045 | $+4,053 | +133.1% | 304.5% | 3.1% | TP1_THEN_RUNNER_TIME |
| ITM-1 | 739 | 15 | +100% | 0.333 | 2.50x | no_lock | $1.31 | $1,965 | $+3,930 | +200.0% | 196.5% | 2.0% | TP1_THEN_RUNNER_TARGET |

## Top 10 by % gain — NO LOCK (J's preferred metric, control variant)

| Strike | K | Qty | TP1% | TP1frac | Runner | Lock | Entry$ | Cost$ | P&L$ | %Gain | %1K | %98K | ExitReason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OTM+1 | 741 | 10 | +150% | 0.333 | 5.00x | no_lock | $0.39 | $390 | $+1,540 | +395.0% | 39.0% | 0.4% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 10 | +150% | 0.333 | 5.00x | no_lock | $0.19 | $190 | $+750 | +395.0% | 19.0% | 0.2% | TP1_THEN_RUNNER_TARGET |
| OTM+1 | 741 | 3 | +150% | 0.333 | 5.00x | no_lock | $0.39 | $117 | $+448 | +383.3% | 11.7% | 0.1% | TP1_THEN_RUNNER_TARGET |
| OTM+1 | 741 | 15 | +150% | 0.333 | 5.00x | no_lock | $0.39 | $585 | $+2,242 | +383.3% | 58.5% | 0.6% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 3 | +150% | 0.333 | 5.00x | no_lock | $0.19 | $57 | $+218 | +383.3% | 5.7% | 0.1% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 15 | +150% | 0.333 | 5.00x | no_lock | $0.19 | $285 | $+1,092 | +383.3% | 28.5% | 0.3% | TP1_THEN_RUNNER_TARGET |
| OTM+1 | 741 | 10 | +100% | 0.333 | 5.00x | no_lock | $0.39 | $390 | $+1,482 | +380.0% | 39.0% | 0.4% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 10 | +100% | 0.333 | 5.00x | no_lock | $0.19 | $190 | $+722 | +380.0% | 19.0% | 0.2% | TP1_THEN_RUNNER_TARGET |
| OTM+1 | 741 | 10 | +75% | 0.333 | 5.00x | no_lock | $0.39 | $390 | $+1,453 | +372.5% | 39.0% | 0.4% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 10 | +75% | 0.333 | 5.00x | no_lock | $0.19 | $190 | $+708 | +372.5% | 19.0% | 0.2% | TP1_THEN_RUNNER_TARGET |

## Top 10 for $1K account (total_cost ≤ $500, both variants)

| Strike | K | Qty | TP1% | TP1frac | Runner | Lock | Entry$ | Cost$ | P&L$ | %Gain | %1K | %98K | ExitReason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OTM+1 | 741 | 10 | +150% | 0.333 | 5.00x | no_lock | $0.39 | $390 | $+1,540 | +395.0% | 39.0% | 0.4% | TP1_THEN_RUNNER_TARGET |
| OTM+1 | 741 | 10 | +100% | 0.333 | 5.00x | no_lock | $0.39 | $390 | $+1,482 | +380.0% | 39.0% | 0.4% | TP1_THEN_RUNNER_TARGET |
| OTM+1 | 741 | 10 | +75% | 0.333 | 5.00x | no_lock | $0.39 | $390 | $+1,453 | +372.5% | 39.0% | 0.4% | TP1_THEN_RUNNER_TARGET |
| OTM+1 | 741 | 10 | +50% | 0.333 | 5.00x | no_lock | $0.39 | $390 | $+1,424 | +365.0% | 39.0% | 0.4% | TP1_THEN_RUNNER_TARGET |
| OTM+1 | 741 | 10 | +150% | 0.500 | 5.00x | no_lock | $0.39 | $390 | $+1,268 | +325.0% | 39.0% | 0.4% | TP1_THEN_RUNNER_TARGET |
| OTM+1 | 741 | 10 | +100% | 0.500 | 5.00x | no_lock | $0.39 | $390 | $+1,170 | +300.0% | 39.0% | 0.4% | TP1_THEN_RUNNER_TARGET |
| OTM+1 | 741 | 8 | +150% | 0.333 | 5.00x | no_lock | $0.39 | $312 | $+1,150 | +368.8% | 31.2% | 0.3% | TP1_THEN_RUNNER_TARGET |
| OTM+1 | 741 | 10 | +75% | 0.500 | 5.00x | no_lock | $0.39 | $390 | $+1,121 | +287.5% | 39.0% | 0.4% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 15 | +150% | 0.333 | 5.00x | no_lock | $0.19 | $285 | $+1,092 | +383.3% | 28.5% | 0.3% | TP1_THEN_RUNNER_TARGET |
| OTM+1 | 741 | 8 | +100% | 0.333 | 5.00x | no_lock | $0.39 | $312 | $+1,092 | +350.0% | 31.2% | 0.3% | TP1_THEN_RUNNER_TARGET |

## J's pattern — cheapest cost, biggest $ gain (cost ≤ $100, P&L > $100)

| Strike | K | Qty | TP1% | TP1frac | Runner | Lock | Entry$ | Cost$ | P&L$ | %Gain | %1K | %98K | ExitReason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OTM+2 | 742 | 3 | +150% | 0.333 | 5.00x | no_lock | $0.19 | $57 | $+218 | +383.3% | 5.7% | 0.1% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 3 | +100% | 0.333 | 5.00x | no_lock | $0.19 | $57 | $+209 | +366.7% | 5.7% | 0.1% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 5 | +150% | 0.333 | 5.00x | no_lock | $0.19 | $95 | $+342 | +360.0% | 9.5% | 0.1% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 5 | +150% | 0.500 | 5.00x | no_lock | $0.19 | $95 | $+342 | +360.0% | 9.5% | 0.1% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 3 | +75% | 0.333 | 5.00x | no_lock | $0.19 | $57 | $+204 | +358.3% | 5.7% | 0.1% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 3 | +50% | 0.333 | 5.00x | no_lock | $0.19 | $57 | $+200 | +350.0% | 5.7% | 0.1% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 5 | +100% | 0.333 | 5.00x | no_lock | $0.19 | $95 | $+323 | +340.0% | 9.5% | 0.1% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 5 | +100% | 0.500 | 5.00x | no_lock | $0.19 | $95 | $+323 | +340.0% | 9.5% | 0.1% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 5 | +75% | 0.333 | 5.00x | no_lock | $0.19 | $95 | $+314 | +330.0% | 9.5% | 0.1% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 5 | +75% | 0.500 | 5.00x | no_lock | $0.19 | $95 | $+314 | +330.0% | 9.5% | 0.1% | TP1_THEN_RUNNER_TARGET |

## J-zone cluster — OTM+1 to OTM+4, total_cost ≤ $300

| Strike | K | Qty | TP1% | TP1frac | Runner | Lock | Entry$ | Cost$ | P&L$ | %Gain | %1K | %98K | ExitReason |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| OTM+2 | 742 | 15 | +150% | 0.333 | 5.00x | no_lock | $0.19 | $285 | $+1,092 | +383.3% | 28.5% | 0.3% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 15 | +100% | 0.333 | 5.00x | no_lock | $0.19 | $285 | $+1,045 | +366.7% | 28.5% | 0.3% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 15 | +75% | 0.333 | 5.00x | no_lock | $0.19 | $285 | $+1,021 | +358.3% | 28.5% | 0.3% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 15 | +50% | 0.333 | 5.00x | no_lock | $0.19 | $285 | $+998 | +350.0% | 28.5% | 0.3% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 15 | +150% | 0.500 | 5.00x | no_lock | $0.19 | $285 | $+893 | +313.3% | 28.5% | 0.3% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 15 | +100% | 0.500 | 5.00x | no_lock | $0.19 | $285 | $+817 | +286.7% | 28.5% | 0.3% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 15 | +75% | 0.500 | 5.00x | no_lock | $0.19 | $285 | $+779 | +273.3% | 28.5% | 0.3% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 15 | +150% | 0.667 | 5.00x | no_lock | $0.19 | $285 | $+760 | +266.7% | 28.5% | 0.3% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 10 | +150% | 0.333 | 5.00x | no_lock | $0.19 | $190 | $+750 | +395.0% | 19.0% | 0.2% | TP1_THEN_RUNNER_TARGET |
| OTM+2 | 742 | 15 | +50% | 0.500 | 5.00x | no_lock | $0.19 | $285 | $+741 | +260.0% | 28.5% | 0.3% | TP1_THEN_RUNNER_TARGET |

## Strike × Qty heatmap — BEST $ P&L per cell across all exit-knob combos (BOTH variants)

| Strike\Qty | 1 | 2 | 3 | 5 | 8 | 10 | 15 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ITM-2 (738C) | $+304 | $+609 | $+914 | $+1,522 | $+2,436 | $+3,045 | $+4,568 |
| ITM-1 (739C) | $+196 | $+524 | $+852 | $+1,376 | $+2,227 | $+2,882 | $+4,258 |
| ATM (740C) | $+114 | $+304 | $+494 | $+798 | $+1,292 | $+1,672 | $+2,470 |
| OTM+1 (741C) | $+58 | $+254 | $+448 | $+702 | $+1,150 | $+1,540 | $+2,242 |
| OTM+2 (742C) | $+28 | $+124 | $+218 | $+342 | $+560 | $+750 | $+1,092 |
| OTM+3 (743C) | $+1 | $+2 | $+3 | $+5 | $+8 | $+10 | $+15 |
| OTM+4 (744C) | $-1 | $-2 | $-4 | $-6 | $-10 | $-12 | $-18 |

## Strike × Qty heatmap — LOCKED variant only (task's main ask)

| Strike\Qty | 1 | 2 | 3 | 5 | 8 | 10 | 15 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ITM-2 (738C) | $+20 | $+41 | $+61 | $+102 | $+162 | $+203 | $+304 |
| ITM-1 (739C) | $+13 | $+26 | $+39 | $+66 | $+105 | $+131 | $+196 |
| ATM (740C) | $+8 | $+15 | $+23 | $+38 | $+61 | $+76 | $+114 |
| OTM+1 (741C) | $+4 | $+8 | $+12 | $+20 | $+31 | $+39 | $+58 |
| OTM+2 (742C) | $+2 | $+4 | $+6 | $+10 | $+15 | $+19 | $+28 |
| OTM+3 (743C) | $+1 | $+2 | $+3 | $+5 | $+8 | $+10 | $+15 |
| OTM+4 (744C) | $-1 | $-2 | $-4 | $-6 | $-10 | $-12 | $-18 |

## Strike × Qty heatmap — NO LOCK variant (control)

| Strike\Qty | 1 | 2 | 3 | 5 | 8 | 10 | 15 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| ITM-2 (738C) | $+304 | $+609 | $+914 | $+1,522 | $+2,436 | $+3,045 | $+4,568 |
| ITM-1 (739C) | $+196 | $+524 | $+852 | $+1,376 | $+2,227 | $+2,882 | $+4,258 |
| ATM (740C) | $+114 | $+304 | $+494 | $+798 | $+1,292 | $+1,672 | $+2,470 |
| OTM+1 (741C) | $+58 | $+254 | $+448 | $+702 | $+1,150 | $+1,540 | $+2,242 |
| OTM+2 (742C) | $+28 | $+124 | $+218 | $+342 | $+560 | $+750 | $+1,092 |
| OTM+3 (743C) | $-2 | $-4 | $-6 | $-10 | $-16 | $-20 | $-30 |
| OTM+4 (744C) | $-1 | $-2 | $-4 | $-6 | $-10 | $-12 | $-18 |

---

## Recommendation for J's $1K starting strategy

### Under the locked profit-lock policy (the production rule):

Optimal $1K-account combo: **ITM-2 (738C) × 2 contracts** with TP1 at +30% / 0.333 fraction and runner target 1.50x.

- **Cost:** $406 (40.6% of $1K, within 50% rule)
- **P&L:** $+41 (+10.0%)
- **Exit:** EXIT_ALL_PREMIUM_STOP after 5 minutes
- **Why this beats other strikes:** ITM-2 (738C) has the lowest entry premium ($2.03)
  of all in-the-money strikes, maximising contracts buyable under the $500 budget.
  Note: TP1/runner-target knobs are NOOPs in locked variant — only strike + qty matter.

### If profit-lock is relaxed (control comparison):

Optimal $1K-account no-lock combo: **OTM+1 (741C) × 10 contracts** with TP1 at +150% / 0.333 fraction and runner target 5.00x.

- **Cost:** $390 (39.0% of $1K)
- **P&L:** $+1,540 (+395.0%)
- **Exit:** TP1_THEN_RUNNER_TARGET after 155 minutes

**Headroom delta:** locked $+41 vs no-lock $+1,540 = **$+1,500 of theoretical upside locked away.**

### J's preferred '<$100 → >$100' pattern:

**OTM+2 (742C) × 3 @ $0.19** turned $57 into $276 (+383%) on this signal under the `no_lock` profit-lock.

---

## What to ratify (1-paragraph verdict)

This N=1 study surfaces a structural issue, not a new ratification candidate: the
locked profit-lock (+5%/+10%) caps explosive winners at ~+10% on this 5/13-style ribbon
ride. **Do NOT ratify** any TP1/runner-target change off this single trade — the knobs are
noop under the lock. The right follow-up is a regime-aware profit-lock: either
(a) widen the arm threshold (e.g., +15-20%) so it only activates once the trade is
clearly working, or (b) gate profit-lock by setup-type — only apply to chop-prone
setups (PIN_FADE, mean reversion), never to ride-the-ribbon trades. Either change is a
weekend-research candidate via the full 5-stage grinder + walk-forward + real-fills
pipeline (CLAUDE.md OP 20), NOT an immediate live-rule change.

**Disclaimer:** N=1 trade. This is what *would have happened* on this single 5/13 signal under each variant — it does NOT validate any combo's edge across other days/setups. To ratify any of these knobs, the standard 5-stage grinder + walk-forward + real-fills checklist still applies (CLAUDE.md OP 20).

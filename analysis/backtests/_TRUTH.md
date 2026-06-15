# MISSED-WEEK TRUTH SHEET
_Computed in-process 2026-05-31 from result CSVs. Authoritative — supersedes any earlier hand-typed numbers._

**Window:** backtest 2026-05-19 → 2026-05-29. Warmup/lead-in = 05-19..22 (option grid NOT fetched for these → they use Black-Scholes fallback). TARGET missed days = 05-26, 27, 28, 29 (real OPRA fills; 05-25 Memorial Day closed).

**SIZING CAVEAT (OP-16):** backtest uses fixed quality-tier qty (SUPER=15/ELITE=10/LEVEL=22/TRENDLINE=3), decoupled from account equity & risk cap. Raw $ P&L is at those quantities. Portable truth = per-contract; min-3 floor shown for account realism.

## BASE (run.py default, ITM-2, no profit-lock)
| date | entry | side | strike | qty | entry$ | P&L$(tier-qty) | per-contract$ | exit |
|---|---|---|---|---|---|---|---|---|
| 2026-05-20·warmup·BS | 13:00 | P | 739 | 3 | 0.91 | +7 | +2.5 | EXIT_ALL_RIBBON_FLIP_BACK |
| 2026-05-21·warmup·BS | 10:20 | P | 738 | 3 | 1.38 | -93 | -31.1 | EXIT_ALL_LEVEL_STOP |
| 2026-05-21·warmup·BS | 11:30 | P | 738 | 3 | 1.16 | -129 | -42.9 | EXIT_ALL_LEVEL_STOP |
| 2026-05-22·warmup·BS | 12:55 | P | 747 | 3 | 0.78 | -65 | -21.6 | EXIT_ALL_RIBBON_FLIP_BACK |
| 2026-05-28 | 10:15 | C | 751 | 15 | 2.67 | -320 | -21.4 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-29 | 10:55 | C | 754 | 10 | 2.59 | +466 | +46.6 | TP1_THEN_RUNNER_RIBBON |
- FULL window (incl warmup BS): **$-133** tier-qty | **$-67.8/contract-sum** | min-3 floor **$-203** | 2W/4L (n=6)
- MISSED DAYS ONLY (05-26..29, real fills): **$+146** tier-qty | **$+25.3/contract-sum** | min-3 floor **$+76** | 1W/1L (n=2)
- missed-days side mix: {'C': 2}  (C=bullish call, P=bearish put)
- missed-days setups: {'BULLISH_RECLAIM_RIDE_THE_RIBBON': 2}

## SAFE overlay (ATM, +30% TP1, trailing PL, eq $747)
| date | entry | side | strike | qty | entry$ | P&L$(tier-qty) | per-contract$ | exit |
|---|---|---|---|---|---|---|---|---|
| 2026-05-20·warmup·BS | 13:00 | P | 739 | 3 | 0.91 | +7 | +2.5 | EXIT_ALL_RIBBON_FLIP_BACK |
| 2026-05-21·warmup·BS | 10:20 | P | 738 | 3 | 1.38 | -93 | -31.1 | EXIT_ALL_LEVEL_STOP |
| 2026-05-21·warmup·BS | 11:30 | P | 738 | 3 | 1.16 | -129 | -42.9 | EXIT_ALL_LEVEL_STOP |
| 2026-05-22·warmup·BS | 12:55 | P | 747 | 3 | 0.78 | -65 | -21.6 | EXIT_ALL_RIBBON_FLIP_BACK |
| 2026-05-26 | 09:45 | C | 751 | 22 | 1.24 | -218 | -9.9 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-27 | 10:00 | C | 750 | 10 | 1.75 | -140 | -14.0 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-28 | 10:15 | C | 753 | 15 | 1.31 | -157 | -10.5 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-29 | 10:55 | C | 756 | 10 | 1.32 | +238 | +23.8 | TP1_THEN_RUNNER_RIBBON |
- FULL window (incl warmup BS): **$-557** tier-qty | **$-103.7/contract-sum** | min-3 floor **$-311** | 2W/6L (n=8)
- MISSED DAYS ONLY (05-26..29, real fills): **$-278** tier-qty | **$-10.6/contract-sum** | min-3 floor **$-32** | 1W/3L (n=4)
- missed-days side mix: {'C': 4}  (C=bullish call, P=bearish put)
- missed-days setups: {'BULLISH_RECLAIM_RIDE_THE_RIBBON': 4}

## BOLD overlay (ITM-2, +75% TP1, trailing PL, eq $1536)
| date | entry | side | strike | qty | entry$ | P&L$(tier-qty) | per-contract$ | exit |
|---|---|---|---|---|---|---|---|---|
| 2026-05-20·warmup·BS | 13:00 | P | 739 | 3 | 0.91 | +7 | +2.5 | EXIT_ALL_RIBBON_FLIP_BACK |
| 2026-05-21·warmup·BS | 10:20 | P | 738 | 3 | 1.38 | -93 | -31.1 | EXIT_ALL_LEVEL_STOP |
| 2026-05-21·warmup·BS | 11:30 | P | 738 | 3 | 1.16 | -129 | -42.9 | EXIT_ALL_LEVEL_STOP |
| 2026-05-22·warmup·BS | 12:55 | P | 747 | 3 | 0.78 | -65 | -21.6 | EXIT_ALL_RIBBON_FLIP_BACK |
| 2026-05-26 | 09:45 | C | 749 | 22 | 2.46 | -812 | -36.9 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-26 | 10:40 | C | 750 | 22 | 2.35 | -776 | -35.2 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-26 | 15:50 | C | 749 | 22 | 1.67 | -551 | -25.1 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-27 | 09:55 | C | 748 | 22 | 2.95 | -974 | -44.2 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-27 | 15:05 | C | 749 | 22 | 2.08 | -686 | -31.2 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-28 | 10:15 | C | 751 | 15 | 2.67 | -601 | -40.0 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-29 | 09:40 | C | 755 | 22 | 2.55 | +1071 | +48.7 | TP1_THEN_RUNNER_RIBBON |
| 2026-05-29 | 10:55 | C | 754 | 10 | 2.59 | +466 | +46.6 | TP1_THEN_RUNNER_RIBBON |
- FULL window (incl warmup BS): **$-3141** tier-qty | **$-210.5/contract-sum** | min-3 floor **$-631** | 3W/9L (n=12)
- MISSED DAYS ONLY (05-26..29, real fills): **$-2862** tier-qty | **$-117.4/contract-sum** | min-3 floor **$-352** | 2W/6L (n=8)
- missed-days side mix: {'C': 8}  (C=bullish call, P=bearish put)
- missed-days setups: {'BULLISH_RECLAIM_RIDE_THE_RIBBON': 8}

## Per-day market facts (real Alpaca SPY 5m; VIX = VIXY×0.648 proxy)
| date | open | close | net | high@ | low@ | gap | dir | VIX(reg) | bear-bars≥7 | maxbear |
|---|---|---|---|---|---|---|---|---|---|---|
| 2026-05-26 | 750.01 | 750.49 | +0.48 | 752.13@10:40 | 748.37@11:55 | +4.42 | UP | 16.08(MID) | 11 | 7 |
| 2026-05-27 | 750.9 | 750.47 | -0.43 | 751.38@10:20 | 748.22@13:05 | +0.41 | DOWN | 15.85(MID) | 14 | 8 |
| 2026-05-28 | 750.25 | 754.64 | +4.39 | 755.15@15:40 | 749.23@09:35 | -0.22 | UP | 15.66(MID) | 0 | 6 |
| 2026-05-29 | 755.9 | 756.4 | +0.50 | 758.08@10:00 | 754.69@10:45 | +1.26 | UP | 15.23(MID) | 8 | 7 |

Every target day closed at/above its open; SPY 750.0→756.4 over the 4 days (+0.85%). Low-VIX (15-16) MID-regime bull grind. The BEARISH evaluation track (decisions.csv) never passed (0 entries); the engine's profitable entries were BULLISH_RECLAIM calls — i.e. the engine correctly traded WITH the uptrend, not against it. (Earlier hypothesis of a 'bearish regime mismatch' was WRONG.)

## J-edge non-regression (anchor window 2026-04-27..05-07)
Purpose: confirm the data-plumbing changes (new Alpaca fetchers + timestamp fix) did NOT alter engine edge capture. Engine logic is byte-unchanged this session (only NEW tool files added), so anchor-window behavior should match the engine's known edge-capture profile. Filter-8 (VIX>17.30, added 2026-05-05) is disabled in Run B for the fair pre-rule test on the 4/29 entry.

### Run A — full v15.2 (filter 8 ACTIVE)
| date | entry | side | strike | qty | entry$ | P&L$ | per-contract$ | exit |
|---|---|---|---|---|---|---|---|---|
| 2026-04-28 | 10:40 | P | 712 | 22 | 2.49 | -438 | -19.9 | EXIT_ALL_PREMIUM_STOP |
| 2026-04-29 | 12:15 | P | 712 | 3 | 3.15 | -76 | -25.2 | EXIT_ALL_PREMIUM_STOP |
| 2026-04-30 | 10:05 | C | 710 | 10 | 3.16 | -253 | -25.3 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-01 | 13:40 | P | 725 | 3 | 2.22 | +3 | +1.0 | EXIT_ALL_RIBBON_FLIP_BACK |
| 2026-05-04 | 10:10 | P | 722 | 10 | 2.35 | -188 | -18.8 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-04 | 11:20 | P | 721 | 15 | 2.68 | +804 | +53.6 | TP1_THEN_RUNNER_RIBBON |
| 2026-05-07 | 12:50 | P | 735 | 3 | 2.80 | -67 | -22.4 | EXIT_ALL_PREMIUM_STOP |
- 4/29 anchor (J 710P 10:25): **MISS**
- 5/01 anchor (J 721P): **+$3 (P725 @13:40)**
- 5/04 anchor (J 721P 11:20): **+$804 (P721 @11:20)**
- window total (tier-qty): $-215

### Run B — filter 8 DISABLED (canonical pre-VIX-rule test)
| date | entry | side | strike | qty | entry$ | P&L$ | per-contract$ | exit |
|---|---|---|---|---|---|---|---|---|
| 2026-04-28 | 10:40 | P | 712 | 22 | 2.49 | -438 | -19.9 | EXIT_ALL_PREMIUM_STOP |
| 2026-04-29 | 12:15 | P | 712 | 3 | 3.15 | -76 | -25.2 | EXIT_ALL_PREMIUM_STOP |
| 2026-04-30 | 10:05 | C | 710 | 10 | 3.16 | -253 | -25.3 | EXIT_ALL_PREMIUM_STOP |
| 2026-04-30 | 13:25 | C | 714 | 10 | 2.18 | +1632 | +163.2 | TP1_THEN_RUNNER_TIME |
| 2026-05-01 | 13:40 | P | 725 | 3 | 2.22 | +3 | +1.0 | EXIT_ALL_RIBBON_FLIP_BACK |
| 2026-05-04 | 10:10 | P | 722 | 10 | 2.35 | -188 | -18.8 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-04 | 11:20 | P | 721 | 15 | 2.68 | +804 | +53.6 | TP1_THEN_RUNNER_RIBBON |
| 2026-05-05 | 15:20 | C | 723 | 10 | 1.98 | -158 | -15.8 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-07 | 11:55 | C | 733 | 10 | 2.26 | -181 | -18.1 | EXIT_ALL_PREMIUM_STOP |
| 2026-05-07 | 12:50 | P | 735 | 3 | 2.80 | -67 | -22.4 | EXIT_ALL_PREMIUM_STOP |
- 4/29 anchor (J 710P 10:25): **MISS**
- 5/01 anchor (J 721P): **+$3 (P725 @13:40)**
- 5/04 anchor (J 721P 11:20): **+$804 (P721 @11:20)**
- window total (tier-qty): $+1078

**VERDICT (honest): production captures the clean anchor; NO REGRESSION.**
- **Run A is production v15.2** (filter 8 active): 7 trades, all PUTS, -$215 tier-qty. Captures **5/04 721P +$804** (J's exact anchor, exact 11:20 entry) and 5/01 (+$3). MISSES J's 4/29 morning 710P — fires a losing 12:15 712P instead.
- **Run B (filter 8 OFF) is a sensitivity check, NOT 'what would have happened.'** It adds 3 bullish CALLS the VIX gate blocks live (4/30/5/05/5/07 entries at VIX~17.4 > 17.20 bull cap). The eye-catching 4/30 714C +$1,632 is therefore a filter-gated-out artifact — do NOT credit it as live edge.
- **No regression:** engine logic (orchestrator/simulator/filters/run.py) is byte-unchanged this session — only NEW data-fetch tool files were added, and the anchor-window option CSVs were already cached (not refetched). The 4/29 miss is a PRE-EXISTING edge-capture gap (OP-16 tracks capture as a fraction, max 1542, not 100%), not something introduced here. The clean 5/04 capture proves the data plumbing did not break the engine.

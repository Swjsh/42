# B9-CAP — Cap-Aware Re-Score of the 3-Edge VWAP Portfolio (the REALIZABLE book)

- Run window: 2025-01-01 .. 2026-05-15 (342 trading days). Fills: **real OPRA** via `lib.simulator_real` (C1).
- Cap: `lib.cap_admission.admit_book` -> `lib.risk_gate.check_order` (the single live authority), `enforce_cap=True`.
- Edge#4 vix-cfg: slope_rule=not_rising, low_margin=0.25 (b5 robust cell). v15 default exits, -8% premium stop.
- Harness: `backtest/autoresearch/_b9_cap_aware_rescore.py` (reuses the byte-for-byte B9 detectors + metrics; only
  new behaviour = qty parametrized to the account's real qty, entry_premium carried per fill, admit_book per book).

## The cap per account (tighter of risk-cap and v15 tier, measured at current equity)

| Account | Equity | qty | risk_cap (0.30/0.50) | v15 tier cap | **EFFECTIVE cap** | max prem/contract | min_contracts |
|---|---|---|---|---|---|---|---|
| Safe-2 | $2,000 | 3 | $600 | $600 (0.30 tier) | **$600** | $2.00 | 3 |
| Bold | $1,648 | 5 | $824 | $824 (0.50 tier) | **$824** | $1.648 | 5 |

## Affordable-tier scan (median 0DTE order = median entry premium x qty x 100 vs cap)

| Account | Tier | median prem | median order $ | fits cap? | cap-BLIND total | **cap-AWARE total** | Sharpe (blind->aware) | maxDD aware |
|---|---|---|---|---|---|---|---|---|
| Safe-2 | OTM-2 | $0.63 | $189 | YES | $6,215 | $6,283 | 3.04->3.62 | -$585 |
| Safe-2 | OTM-1 | $0.94 | $282 | YES | $10,076 | $9,332 | 3.88->4.23 | -$468 |
| **Safe-2** | **ATM** | **$1.38** | **$414** | **YES (AFFORDABLE)** | **$14,608** | **$12,920** | **4.53->4.79** | **-$401** |
| Safe-2 | ITM-2 | $2.57 | $771 | **NO** | $24,075 | $12,799 | 4.68->3.88 | -$88 |
| Bold | OTM-2 | $0.625 | $312 | YES | $9,123 | $5,745 | 3.01->3.00 | -$449 |
| Bold | OTM-1 | $0.92 | $460 | YES | $13,502 | $9,662 | 3.65->3.74 | -$331 |
| **Bold** | **ATM** | **$1.36** | **$680** | **YES (AFFORDABLE)** | **$19,201** | **$12,776** | **4.30->4.18** | **-$454** |
| Bold | ITM-2 | $2.57 | $1,285 | **NO** | $33,014 | $7,387 | 4.62->2.62 | -$65 |

## ITM-2 affordability hypothesis — CONFIRMED on BOTH accounts

- **Bold ITM-2 unaffordable**: median order $1,285 (qty5 x $2.57 x 100) > $824 cap. Cap-aware admission BLOCKS
  **90.6% of edge-1 fills and 90.8% of edge-2 fills** (RISK_CAP). The cap-blind Bold ITM-2 headline collapses to
  the cheap-premium residue: **$33,014 blind -> $7,387 realizable** (Sharpe 4.62 -> 2.62). The entire ITM-2 book
  is cap-blind fiction.
- **Safe ITM-2 also unaffordable**: median order $771 (qty3 x $2.57 x 100) > $600 cap. $24,075 blind -> $12,799 realizable.
- **The realizable richest tier for BOTH accounts is ATM/0DTE**, not ITM-2.

## TRUE realizable portfolio at the affordable (ATM) tier

| Account (ATM) | cap-blind headline | **REALIZABLE (cap-aware)** | Sharpe | maxDD | % days in mkt | day-WR |
|---|---|---|---|---|---|---|
| Safe-2 (#1+#2+#4) | $14,608 | **$12,919.72** | 4.79 | -$401.04 | 34.8% | 61.3% |
| Bold (#1+#2) | $18,784* | **$12,775.6** | 4.18 | -$454.0 | — | — |

\* Bold ITM-2 headline (+$18,784 in memory; +$33,014 blind over this longer window). It does NOT survive — the
realizable Bold book is ATM/qty5 = **+$12,775.6**, NOT the ITM-2 number. "ITM-2 dominates ATM = better compounder"
is FALSE once the cap binds: ITM-2 is unaffordable, so its dominance is unrealizable.

## Standalone realizable OOS exp/tr per edge (ATM, cap-aware)

| Edge | Safe (qty3) OOS exp/tr | Safe block-rate | Bold (qty5) OOS exp/tr | Bold block-rate |
|---|---|---|---|---|
| #1 vwap_continuation | $74.11 | 21.5% | $133.63 | 35.6% |
| #2 vwap_reclaim_failed_break | $30.27 | 22.4% | $92.70 | 39.5% |
| #4 vix_regime_dayside | $86.19 | 26.3% | n/a (ATM Safe-only) | — |

Even at the affordable ATM tier, **21-40% of fills are still cap-blocked** — premium spikes push individual orders
over the cap. Realizable expectancy stays solidly positive on all edges; the standalone OOS exp/tr (Safe ATM #1
$74.11 / #2 $30.27 / #4 $86.19) is in line with the cap-blind memory numbers, confirming the *per-trade* edge is
real; what the cap removes is the fat-premium tail, not the edge.

## Diversification — SURVIVES

| pair | cap-blind daily corr | cap-aware daily corr |
|---|---|---|
| Safe e1__e2 | 0.313 | 0.353 |
| Safe e1__e4 | 0.540 | 0.551 |
| Safe e2__e4 | **0.076** | **0.108** |
| Bold e1__e2 | 0.295 | 0.412 |

The headline diversification claim (e2-e4 daily-corr 0.076) survives the cap — it edges up to 0.108, still low.
All pairwise daily-P&L correlations stay <= 0.56. The portfolio Sharpe (4.79 Safe / 4.18 Bold) exceeds any single
constituent, so the diversification value is intact after the realizable filter.

## Bottom line

- The cap-blind headlines OVERSTATED the realizable book on both accounts. **Safe ATM $14,608 -> $12,920** (~12%
  haircut, ATM mostly fits). **Bold ITM-2 collapses entirely** -> the realizable Bold book is **ATM $12,776**.
- ITM-2 is **unaffordable** at current equity on both accounts (Bold $1,285 > $824, Safe $771 > $600). The
  "ITM-2/tight-stop dominates ATM" compounding claim is unrealizable until equity is high enough that an ITM-2
  qty-floor order fits the tier cap (Bold needs ~$2,570/0.50 = ~$5.1K just for the cap; min-5 floor at $2.57 = $1,285
  notional needs effective cap >= $1,285 i.e. equity >= ~$2,570 on the 0.50 tier).
- Realizable per-edge OOS expectancy stays positive; diversification intact. The honest realizable target tier is
  **ATM/0DTE/qty-floor for BOTH accounts today.**

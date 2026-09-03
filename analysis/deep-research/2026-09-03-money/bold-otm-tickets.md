# H3 BOLD OTM TICKETS -- premium bucket / moneyness / VIX-regime analysis

Stamp: 2026-09-03T10:24 ET. Slug: bold-otm-tickets.

**Scope note**: read-only, cached-data-only analysis per the money-hunt work order. No broker/market-data calls made. No trading-path files edited.

Population: 394 scored positions (all 6 arms, analysis/pain-ledger/mae-mfe.json), 394 matched to a core-decisions.jsonl market (spy,vix) snapshot within 150s (0 unmatched -- see JSON `unmatched_detail`).

## 0. Tier-ladder context (read-only inspection)
- **bold2_account_equity_2026_08_18_broker_verified**: 5048.4
- **v15_bold_tiers_live_core_bold_branch_AS_OF_2026_09_03**: heartbeat_core.py (~line 2679, direct read, not the strike_selection.py docstring) currently reads ss.V15_BOLD_TIERS for account=='bold' -- i.e. OTM-2 (strike_offset -2) at $2K-$10K equity, OTM-3 under $2K. This is NOT V15_BOLD_CORE_TIERS (which would be ATM 0-$10K).
- **stale_docstring_note**: crypto/lib/strike_selection.py's V15_BOLD_CORE_TIERS docstring says 'STATUS UPDATE 2026-07-18: WIRED' and does NOT mention the 2026-08-20 revert documented directly in heartbeat_core.py's inline comment at the call site. Doc drift, flagged here, NOT fixed (out of scope / read-only per this task's constraints).
- **min_entry_premium_floor_aggressive_params_json**: 0.3
- **min_entry_premium_enforced_against**: mid (option mid quote at plan time), NOT the fill price -- fill price (this report's entry_price) is typically >= mid via marketable-limit ask+buffer pricing, so filtering on entry_price is a conservative (slightly permissive) proxy for the live gate.
- **skip_min_premium_floor_events_bold_account_core_decisions**: 49

## 0b. PRIOR EXPERIMENT: bold-2 tier shift to ATM already ran live and was reverted
**The EXACT lever H3 asks about (shift bold-2 toward ATM, i.e. reduce OTM distance to ~0) was ALREADY shipped live 2026-07-18 (commit 718e0809, V15_BOLD_TIERS->V15_BOLD_CORE_TIERS) and REVERTED 2026-08-20 after its own standing falsification rail (setup/scripts/bold_tier_rail.py) triggered negative.**

- Rail verdict: Bold ATM tier: 38 of 20 fills, -$346 so far (old tier was +$406 on 4) -- rail TRIGGERED.
- Rail status: TRIGGERED_NEGATIVE
- Post-ship ATM population (2026-07-18..2026-08-20): n=38, net=$-346.0, WR=34.2%, mean/tr=$-9.11
- Pre-ship OTM population (baseline): n=4, net=$406.0, WR=50.0%, mean/tr=$101.5
- Revert authorization: J, in-chat, 2026-08-20: "so #2 is asking if I want to retire a strat that is losing? i guess so yeah" (quoted in heartbeat_core.py's inline comment at the strike-selection call site).
- **Relevance to H3**: This is DIRECT prior evidence against a tier shift toward ATM for bold-2: n=38 live ATM fills netted -$346 (WR 34.2%) vs the OTM tier's smaller pre-ship sample of n=4 at +$406 (WR 50%). Combined with this report's own distance-bucket finding (OTM-2-zone entries are bold-2's BEST-performing bucket post-revert, section 3/7 below), the tier-shift half of H3 is REFUTED by a real, larger live experiment, not just this report's smaller counterfactual slice.

## 1. Premium bucket x outcome

### All arms
| Bucket | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate (of losers) |
|---|---|---|---|---|---|---|
| <0.40 | 106 | $45.00 | $0.42 [-13.83, 15.01] | 18.6% | 1.018 | 21.5% |
| 0.40-0.80 | 112 | $545.00 | $4.87 [-17.85, 30.79] | 33.6% | 1.118 | 11.3% |
| 0.80-1.50 | 143 | $-51.00 | $-0.36 [-37.89, 38.48] | 24.6% | 0.996 | 13.1% |
| >1.50 | 33 | $-3.99 | $-0.12 [-87.55, 89.76] | 33.3% | 0.999 | 13.6% |

### bold-2 only
| Bucket | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate (of losers) |
|---|---|---|---|---|---|---|
| <0.40 | 10 | $684.00 | $68.40 [13.9, 118.2] | 70.0% | 6.067 | 33.3% |
| 0.40-0.80 | 16 | $506.00 | $31.62 [-57.06, 141.12] | 33.3% | 1.484 | 40.0% |
| 0.80-1.50 | 16 | $-1130.00 | $-70.62 [-199.25, 71.25] | 18.8% | 0.543 | 23.1% |
| >1.50 | 0 | $0.00 | $0.00 n/a | n/a | n/a | n/a |

## 2. Premium bucket x VIX regime, bold-2
### VIX <15
| Bucket | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate |
|---|---|---|---|---|---|---|
| <0.40 / VIX <15 | 1 | $159.00 | $159.00 [159.0, 159.0] | 100.0% | inf | n/a |
| 0.40-0.80 / VIX <15 | 6 | $24.00 | $4.00 [-138.33, 217.0] | 16.7% | 1.049 | 40.0% |
| 0.80-1.50 / VIX <15 | 6 | $-329.00 | $-54.83 [-269.17, 215.33] | 16.7% | 0.619 | 20.0% |
| >1.50 / VIX <15 | 0 | $0.00 | $0.00 n/a | n/a | n/a | n/a |

### VIX 15-17
| Bucket | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate |
|---|---|---|---|---|---|---|
| <0.40 / VIX 15-17 | 7 | $349.00 | $49.86 [-8.0, 104.0] | 71.4% | 3.908 | 50.0% |
| 0.40-0.80 / VIX 15-17 | 10 | $482.00 | $48.20 [-68.0, 166.7] | 44.4% | 1.861 | 40.0% |
| 0.80-1.50 / VIX 15-17 | 7 | $154.00 | $22.00 [-147.14, 246.71] | 28.6% | 1.235 | 0.0% |
| >1.50 / VIX 15-17 | 0 | $0.00 | $0.00 n/a | n/a | n/a | n/a |

### VIX >17
| Bucket | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate |
|---|---|---|---|---|---|---|
| <0.40 / VIX >17 | 2 | $176.00 | $88.00 [-15.0, 191.0] | 50.0% | 12.733 | 0.0% |
| 0.40-0.80 / VIX >17 | 0 | $0.00 | $0.00 n/a | n/a | n/a | n/a |
| 0.80-1.50 / VIX >17 | 3 | $-955.00 | $-318.33 [-355.0, -295.0] | 0.0% | 0.0 | 66.7% |
| >1.50 / VIX >17 | 0 | $0.00 | $0.00 n/a | n/a | n/a | n/a |

## 3. OTM distance bucket x outcome (recomputed moneyness: OCC strike vs decision-row spy)

### All arms
| Bucket | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate |
|---|---|---|---|---|---|---|
| ATM/ITM (<=0) | 119 | $684.01 | $5.75 [-36.86, 51.29] | 32.2% | 1.072 | 17.5% |
| OTM $0-1.5 | 104 | $-11.00 | $-0.11 [-34.19, 36.12] | 27.0% | 0.998 | 8.2% |
| OTM $1.5-3.5 (OTM-2 zone) | 171 | $-138.00 | $-0.81 [-18.19, 17.01] | 21.7% | 0.979 | 17.5% |
| OTM $3.5+ | 0 | $0.00 | $0.00 n/a | n/a | n/a | n/a |

### bold-2 only
| Bucket | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate |
|---|---|---|---|---|---|---|
| ATM/ITM (<=0) | 12 | $-391.00 | $-32.58 [-175.0, 141.0] | 25.0% | 0.749 | 11.1% |
| OTM $0-1.5 | 12 | $-112.00 | $-9.33 [-124.25, 122.83] | 27.3% | 0.891 | 25.0% |
| OTM $1.5-3.5 (OTM-2 zone) | 18 | $563.00 | $31.28 [-56.17, 126.5] | 50.0% | 1.526 | 55.6% |
| OTM $3.5+ | 0 | $0.00 | $0.00 n/a | n/a | n/a | n/a |

## 4. VIX regime summary, bold-2 vs all arms
### bold-2
| Regime | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate |
|---|---|---|---|---|---|---|
| <15 | 13 | $-146.00 | $-11.23 [-143.23, 150.0] | 23.1% | 0.892 | 30.0% |
| 15-17 | 24 | $985.00 | $41.04 [-31.5, 124.79] | 47.8% | 1.738 | 25.0% |
| >17 | 5 | $-779.00 | $-155.80 [-323.0, 40.6] | 20.0% | 0.197 | 50.0% |

### All arms
| Regime | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate |
|---|---|---|---|---|---|---|
| <15 | 84 | $-601.00 | $-7.15 [-52.58, 41.75] | 32.9% | 0.911 | 20.0% |
| 15-17 | 247 | $2639.00 | $10.68 [-10.07, 32.82] | 24.7% | 1.233 | 15.0% |
| >17 | 63 | $-1502.99 | $-23.86 [-57.81, 11.67] | 24.1% | 0.611 | 9.1% |

## 5. Per-arm baseline (context)
| Arm | n | Total P&L | Mean $/trade (95% CI) | WR | PF | Cap-hit rate |
|---|---|---|---|---|---|---|
| bold-2 | 42 | $60.00 | $1.43 [-66.69, 72.81] | 36.6% | 1.016 | 30.8% |
| risky-1 | 83 | $947.00 | $11.41 [-30.51, 55.52] | 28.9% | 1.201 | 18.5% |
| risky-3 | 94 | $-522.00 | $-5.55 [-42.66, 34.67] | 22.8% | 0.911 | 8.5% |
| safe-1 | 24 | $-242.00 | $-10.08 [-30.5, 21.54] | 8.7% | 0.565 | 4.8% |
| safe-2 | 88 | $-335.99 | $-3.82 [-32.72, 26.01] | 25.3% | 0.922 | 12.3% |
| safe-3 | 63 | $628.00 | $9.97 [-29.1, 50.76] | 30.0% | 1.225 | 21.4% |

## 6. Counterfactual: min-premium floor for bold-2, VIX<16 only
Actual bold-2 population under VIX<16 (no new floor): n=32, total P&L=$884.00, WR=41.9%, PF=1.376.

| Floor ($) | n blocked | Blocked total P&L | Kept n | Kept total P&L | Kept mean/tr (95% CI) | Kept WR | Kept PF | Blocks an 08-27/08-28 winner? |
|---|---|---|---|---|---|---|---|---|
| 0.3 | 0 | $0.00 | 32 | $884.00 | $27.62 [-51.56, 109.31] | 41.9% | 1.376 | False |
| 0.4 | 8 | $508.00 | 24 | $376.00 | $15.67 [-86.29, 122.42] | 30.4% | 1.169 | True |
| 0.5 | 8 | $508.00 | 24 | $376.00 | $15.67 [-85.38, 127.46] | 30.4% | 1.169 | True |
| 0.6 | 10 | $468.00 | 22 | $416.00 | $18.91 [-87.09, 134.05] | 31.8% | 1.19 | True |
| 0.8 | 21 | $924.00 | 11 | $-40.00 | $-3.64 [-169.36, 195.91] | 27.3% | 0.971 | True |

Blocked-trade detail per floor (dates/symbols/outcomes) is in the JSON sidecar (`counterfactual_min_premium_floor_bold2_vix_lt16[*].blocked_trades`).

## 7. Counterfactual: OTM-distance shift (proxy for a tier shift), bold-2 VIX<16 only

**Caveat**: this does NOT re-price at an alternate strike (no guaranteed cached option bars for every alternate strike/day). It only asks: does removing far-OTM entries (as actually traded) change bold-2's VIX<16 P&L. A genuine tier-shift simulation (re-pricing at the ATM/near strike) is a separate, larger undertaking flagged in Caveats below.

| OTM distance threshold ($) | n blocked | Blocked total P&L | Kept n | Kept total P&L | Kept WR | Kept PF | Blocks an 08-27/08-28 winner? |
|---|---|---|---|---|---|---|---|
| 1.5 | 12 | $602.00 | 20 | $282.00 | 31.6% | 1.157 | True |
| 2.5 | 0 | $0.00 | 32 | $884.00 | 41.9% | 1.376 | False |
| 3.5 | 0 | $0.00 | 32 | $884.00 | 41.9% | 1.376 | False |
| 5.0 | 0 | $0.00 | 32 | $884.00 | 41.9% | 1.376 | False |

## 8. Winner-day trades (08-06 / 08-13 / 08-27 / 08-28) -- did the floor/shift touch them?
### bold-2
| Date | Symbol | Entry $ | OTM dist | VIX | Outcome | P&L |
|---|---|---|---|---|---|---|
| 2026-08-13 | SPY260813C00777000 | 1.01 | 0.1 | 14.41 | winner | 534.0 |
| 2026-08-13 | SPY260813C00776000 | 0.97 | 0.01 | 14.57 | loser | -85.0 |
| 2026-08-13 | SPY260813P00776000 | 0.64 | 0.29 | 14.7 | loser | -200.0 |
| 2026-08-27 | SPY260827C00770000 | 0.72 | 1.8 | 15.04 | winner | 95.0 |
| 2026-08-27 | SPY260827C00771000 | 0.58 | 1.84 | 15.12 | loser | -40.0 |
| 2026-08-27 | SPY260827C00772000 | 0.34 | 2.32 | 14.51 | winner | 159.0 |
| 2026-08-28 | SPY260828C00773000 | 0.73 | 1.59 | 14.59 | winner | 509.0 |
| 2026-08-28 | SPY260828P00768000 | 0.85 | 1.7 | 14.55 | loser | -215.0 |

### All arms
| Date | Arm | Symbol | Entry $ | Bucket | OTM dist | VIX | Outcome | P&L |
|---|---|---|---|---|---|---|---|---|
| 2026-08-06 | risky-1 | SPY260806P00770000 | 1.23 | 0.80-1.50 | 0.43 | 15.56 | winner | 296.0 |
| 2026-08-06 | risky-3 | SPY260806P00770000 | 1.28 | 0.80-1.50 | 0.43 | 15.56 | winner | 830.0 |
| 2026-08-06 | safe-2 | SPY260806P00770000 | 1.28 | 0.80-1.50 | 0.43 | 15.85 | winner | 375.0 |
| 2026-08-06 | safe-2 | SPY260806C00769000 | 1.08 | 0.80-1.50 | -0.36 | 15.26 | loser | -36.0 |
| 2026-08-13 | bold-2 | SPY260813C00777000 | 1.01 | 0.80-1.50 | 0.1 | 14.41 | winner | 534.0 |
| 2026-08-13 | bold-2 | SPY260813C00776000 | 0.97 | 0.80-1.50 | 0.01 | 14.57 | loser | -85.0 |
| 2026-08-13 | bold-2 | SPY260813P00776000 | 0.64 | 0.40-0.80 | 0.29 | 14.7 | loser | -200.0 |
| 2026-08-13 | risky-1 | SPY260813C00777000 | 1.08 | 0.80-1.50 | 0.1 | 14.4 | winner | 405.0 |
| 2026-08-13 | risky-1 | SPY260813C00776000 | 1.14 | 0.80-1.50 | 0.01 | 14.61 | loser | -155.0 |
| 2026-08-13 | risky-1 | SPY260813C00777000 | 0.65 | 0.40-0.80 | -0.23 | 14.7 | winner | 152.0 |
| 2026-08-13 | risky-3 | SPY260813C00779000 | 0.36 | <0.40 | 2.1 | 14.4 | winner | 366.0 |
| 2026-08-13 | risky-3 | SPY260813C00781000 | 0.36 | <0.40 | 1.99 | 14.74 | loser | -90.0 |
| 2026-08-13 | risky-3 | SPY260813C00778000 | 0.32 | <0.40 | 2.01 | 14.58 | loser | -80.0 |
| 2026-08-13 | safe-2 | SPY260813C00777000 | 1.03 | 0.80-1.50 | 0.1 | 14.41 | winner | 332.0 |
| 2026-08-13 | safe-2 | SPY260813P00776000 | 0.63 | 0.40-0.80 | 0.29 | 14.7 | loser | -69.0 |
| 2026-08-13 | safe-2 | SPY260813C00777000 | 0.66 | 0.40-0.80 | -0.23 | 14.69 | winner | 181.0 |
| 2026-08-13 | safe-3 | SPY260813C00777000 | 1.09 | 0.80-1.50 | 0.1 | 14.4 | winner | 348.0 |
| 2026-08-13 | safe-3 | SPY260813C00776000 | 1.13 | 0.80-1.50 | 0.01 | 14.58 | loser | -90.0 |
| 2026-08-13 | safe-3 | SPY260813C00777000 | 0.65 | 0.40-0.80 | -0.23 | 14.7 | winner | 199.0 |
| 2026-08-27 | bold-2 | SPY260827C00770000 | 0.72 | 0.40-0.80 | 1.8 | 15.04 | winner | 95.0 |
| 2026-08-27 | bold-2 | SPY260827C00771000 | 0.58 | 0.40-0.80 | 1.84 | 15.12 | loser | -40.0 |
| 2026-08-27 | bold-2 | SPY260827C00772000 | 0.34 | <0.40 | 2.32 | 14.51 | winner | 159.0 |
| 2026-08-27 | risky-1 | SPY260827C00768000 | 1.66 | >1.50 | -0.2 | 15.04 | winner | 475.0 |
| 2026-08-27 | risky-1 | SPY260827C00770000 | 1.16 | 0.80-1.50 | 0.32 | 14.52 | winner | 353.0 |
| 2026-08-27 | risky-3 | SPY260827C00770000 | 0.72 | 0.40-0.80 | 1.8 | 15.04 | winner | 85.0 |
| 2026-08-27 | risky-3 | SPY260827C00771000 | 0.47 | 0.40-0.80 | 1.84 | 15.1 | loser | -100.0 |
| 2026-08-27 | risky-3 | SPY260827C00772000 | 0.34 | <0.40 | 2.32 | 14.51 | loser | -40.0 |
| 2026-08-27 | safe-2 | SPY260827C00768000 | 1.58 | >1.50 | -0.2 | 15.04 | winner | 138.0 |
| 2026-08-27 | safe-2 | SPY260827C00771000 | 0.71 | 0.40-0.80 | 0.125 | 14.46 | winner | 184.0 |
| 2026-08-27 | safe-3 | SPY260827C00768000 | 1.65 | >1.50 | -0.2 | 15.04 | winner | 285.0 |
| 2026-08-27 | safe-3 | SPY260827C00770000 | 1.13 | 0.80-1.50 | 0.32 | 14.52 | winner | 303.0 |
| 2026-08-28 | bold-2 | SPY260828C00773000 | 0.73 | 0.40-0.80 | 1.59 | 14.59 | winner | 509.0 |
| 2026-08-28 | bold-2 | SPY260828P00768000 | 0.85 | 0.80-1.50 | 1.7 | 14.55 | loser | -215.0 |
| 2026-08-28 | risky-1 | SPY260828C00771000 | 1.85 | >1.50 | -0.41 | 14.59 | winner | 650.0 |
| 2026-08-28 | risky-3 | SPY260828C00773000 | 0.79 | 0.40-0.80 | 1.59 | 14.59 | loser | -75.0 |
| 2026-08-28 | risky-3 | SPY260828C00773000 | 0.68 | 0.40-0.80 | 1.59 | 14.6 | loser | -115.0 |
| 2026-08-28 | risky-3 | SPY260828C00777000 | 0.33 | <0.40 | 2.16 | 14.22 | loser | -50.0 |
| 2026-08-28 | risky-3 | SPY260828P00768000 | 0.9 | 0.80-1.50 | 1.7 | 14.53 | loser | -120.0 |
| 2026-08-28 | risky-3 | SPY260828P00767000 | 0.44 | 0.40-0.80 | 1.92 | 14.77 | loser | -100.0 |
| 2026-08-28 | safe-2 | SPY260828C00771000 | 1.74 | >1.50 | -0.41 | 14.59 | winner | 527.0 |
| 2026-08-28 | safe-2 | SPY260828P00770000 | 1.76 | >1.50 | -0.3 | 14.55 | loser | -270.0 |
| 2026-08-28 | safe-3 | SPY260828C00771000 | 1.84 | >1.50 | -0.41 | 14.59 | winner | 563.0 |

## 9. Concentration disclosure (top-3 winning trades as % of total gains)
- bold-2: top-3 winners = $1657.00 of $3713.00 total gains (44.6%).
- All arms: top-3 winners = $2269.00 of $22437.00 total gains (10.1%).

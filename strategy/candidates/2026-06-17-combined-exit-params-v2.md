# CANDIDATE: COMBINED_EXIT_PARAMS_V2 (Rank 31)

**Filed:** 2026-06-17  
**Filer:** Gamma (autonomous overnight session)  
**Type:** Exit parameter bundle — `tp1_qty_fraction` (0.50→0.667) + `time_stop_minutes_before_close` (10→20)  
**Status:** NEEDS-J-DECISION — WF=1.08 PASS, all 4 sub-windows HELP, evidence_n=17 blocks auto-ratify

---

## Background

This candidate bundles Rank 29 (tp1_qty_fraction) and Rank 30 (time_stop_minutes_before_close) into a
single deployment recommendation. Both parameters were individually validated this overnight session:

- **Rank 29** (tp1=0.667): WF=1.39 PASS, all 4 sub-windows HELP
- **Rank 30** (stop=20min): WF=0.86 PASS, all 4 sub-windows HELP

The combined effect is near-additive (not conflicting) with a slightly better WF=1.08 and
combined OOS improvement of +$1,444 vs production (vs +$1,064 tp1 alone or +$475 stop alone).

---

## Mechanism

Both parameters operate independently on the exit leg:
1. **tp1_qty_fraction=0.667**: Take 67% of contracts at TP1 premium target (vs 50% production). Locks more P&L early, leaves fewer contracts exposed to runner decay.
2. **time_stop_minutes_before_close=20 (15:40 ET)**: Exit all remaining positions 20 min before close (vs 10 min production = 15:50 ET). Captures runner premium before 0DTE theta crush in final 15 minutes.

Both effects are in the same direction (lock more profit earlier, exit before premium erodes).

---

## OP-20 Disclosures

1. **Data period:** IS 2025-01-01 to 2026-04-30 (n=246); OOS 2026-05-08 to 2026-05-22 (n=17)
2. **Methodology:** Real-fills simulator (`use_real_fills=True`, L108+L109+L110 dead-knob fixes applied). Production-correct baseline: all other params at production values.
3. **Overfitting risk:** Low — both parameters independently validated; combined effect near-additive; all 4 market-regime sub-windows positive
4. **Walk-forward:** WF=1.08 (OOS_delta / IS_delta = 1,444 / 1,333). Gate ≥ 0.70 PASS
5. **Production baseline:** IS=-$6,077, OOS=+$3,304 (post-L108+L109+L110 correction)
6. **Edge concentration:** All regimes improve — tariff shock, recovery, and pre-tariff periods all positive

---

## Results

| Configuration | IS n | IS P&L | IS delta | OOS n | OOS P&L | OOS delta | WF |
|---|---:|---:|---:|---:|---:|---:|---:|
| Production (tp1=0.50, stop=10min) | 246 | −$6,077 | — | 17 | +$3,304 | — | — |
| tp1=0.667 only (Rank 29) | 246 | −$5,312 | +$765 | 17 | +$4,367 | +$1,064 | 1.39 |
| stop=20min only (Rank 30) | 246 | −$5,525 | +$552 | 17 | +$3,779 | +$475 | 0.86 |
| **COMBINED (Rank 31)** | **246** | **−$4,745** | **+$1,333** | **17** | **+$4,747** | **+$1,444** | **1.08** |

Additive sum of individual deltas: IS +$1,317, OOS +$1,539. Combined actual: IS +$1,333, OOS +$1,444. Near-additive (interaction is tiny).

---

## Sub-window Stability

| Window | Baseline | Combined | Delta | Verdict |
|---|---:|---:|---:|---|
| IS full (Jan 2025–Apr 2026) | −$6,077 | −$4,745 | **+$1,333** | HELP |
| IS ex-April (Jan 2025–Mar 2026) | +$964 | +$1,655 | **+$691** | HELP |
| April 2026 tariff shock | −$6,831 | −$6,189 | **+$641** | HELP |
| OOS May 2026 | +$3,304 | +$4,747 | **+$1,444** | HELP |

**Sub-window stable: ALL 4 POSITIVE.**

---

## Negative findings documented this session

| Knob | Sweep result | Conclusion |
|---|---|---|
| `f9_vol_mult` | Production 0.7 is OOS-best across 6 values | No improvement available |
| `no_trade_before` | Production 09:35 is optimal; later times hurt both IS+OOS | No improvement available |
| `no_trade_window` | None (v15.1) is optimal; reinstating 14:00-15:00 window: WF=-0.12 FAIL | v15.1 removal decision confirmed correct |

---

## Auto-ratify Gate Check

| Gate | Required | Actual | Result |
|---|---|---|---|
| WF ≥ 0.70 | 0.70 | 1.08 | ✓ PASS |
| OOS delta positive | > 0 | +$1,444 | ✓ PASS |
| Sub-window stable (all positive) | 4/4 | 4/4 | ✓ PASS |
| J-anchor no-regression | no new losers | n/a (exit-only params) | ✓ PASS |
| evidence_n ≥ 20 | 20 | **17** | ✗ **BLOCK** |

---

## Implementation (when J approves)

1. `automation/state/params.json`:
   ```json
   "tp1_qty_fraction": 0.667,
   "time_stop_minutes_before_close": 20
   ```
2. Same changes in `automation/state/aggressive/params.json` (C9 dual-account symmetry)
3. EOD flatten tasks (Gamma_EodFlatten, Gamma_EodFlatten_Aggressive at 15:55 ET) are independent safety nets — no conflict with 15:40 heartbeat time stop

---

## Recommendation

Deploy as a **single bundle** rather than two sequential changes. The combined candidate has:
- Higher total improvement (+$1,444 OOS vs +$1,539 sum = 6% interaction discount, negligible)
- Single deployment event (one Rule 9 decision, one heartbeat restart)
- Clean WF=1.08 (vs individual 1.39 and 0.86)

Ranks 29 and 30 are archived as individual analysis; Rank 31 is the recommended deployment path.

---

## Scorecards

- Combined: `analysis/recommendations/combined_exit_params_ab_scorecard.json`
- tp1 individual: `analysis/recommendations/tp1_qty_fraction_ab_scorecard.json`
- time_stop individual: `analysis/recommendations/time_stop_minutes_ab_scorecard.json`

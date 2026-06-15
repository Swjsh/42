# Strategy candidate: F11 Reversal-Day Bypass (conditional HTF relaxation on intraday reversals)

> DRAFT -- Chef proposal 2026-05-19-205500. J ratifies.

**Status:** DRAFT -- engine-benefit research per OP-25.
**Classification:** Filter relaxation (F11 -- 15m HTF stack) on qualifying reversal days
**Created:** 2026-05-19
**Chef script:** `backtest/autoresearch/f11_reversal_bypass_analysis.py`
**J ratification required:** YES -- modifies a structural filter gate condition

---

## Problem Statement

**F11 (15m HTF stack):** Requires the 15-minute timeframe EMA stack to show BEAR before any bull entries are allowed after a reversal. The stack is formed from 15m EMA9/EMA21 sampled from 5m bars.

**Observed failure mode (2026-05-19):** On reversal days — where SPY makes a session low before 11:00 ET then recovers ≥$2.00 — the 15m HTF stack lags the 5m ribbon by 25+ minutes (median). This is structural: it takes 3+ consecutive bullish 15m bars for the 15m EMAs to flip BULL.

**Impact:** On 4 of 232 reversal days in the 16-month dataset, the HTF stack NEVER cleared before 15:00 ET. On 10 others, it cleared with a 25-minute median lag. First-strike bull entries after the recovery were blocked for the entire afternoon on those 4 days.

---

## Analysis Results

**Dataset:** 344 trading days (2025-01-02 → 2026-05-19)  
**Reversal days:** 232 (67.4% of all days — intraday V-recoveries are common)

Of 232 reversal days where ribbon went BULL post-recovery:

| Metric | Value |
|--------|-------|
| Ribbon went BULL post-recovery | 164 days |
| HTF was BEAR when ribbon first hit BULL | 14 days |
| HTF eventually cleared (before 15:00 ET) | 10 days |
| HTF NEVER cleared (F11 blocked all afternoon) | **4 days** |
| Median HTF clear lag after ribbon-BULL | **25 min** |
| P75 lag | 45 min |
| Max lag | 60 min |

**Proxy WR on bypass scenario (next 60min SPY move ≥$1.00):**
| Guard | WR | N |
|-------|-----|---|
| No guard (all HTF-BEAR + ribbon-BULL) | 64.3% | 14 |
| With spread ≥ 60c guard | **100.0%** | 2 |

---

## OP-16 Source-of-Truth Check

| Day | Trade | Reversal? | HTF BEAR at ribbon-BULL? | Bypass applies? |
|-----|-------|-----------|--------------------------|-----------------|
| 4/29 (710P +$342) | WINNER | **No** | N/A | No |
| 5/01 (721P +$470) | WINNER | Yes (recovery=2.07, low@09:35) | **No** | No |
| 5/04 (721P +$730) | WINNER | Yes (recovery=2.07, low@09:35) | **No** | No |
| 5/05 (722P −$260) | LOSER | **No** | N/A | No |
| 5/06 (730P −$300) | LOSER | Yes (recovery=2.16) | **No** | No |
| 5/07 (734C −$45) | LOSER | Yes (recovery=2.03) | **No** | No |
| 5/07 (737C −$120) | LOSER | Yes (recovery=2.03) | **No** | No |

**OP-16 floor: INTACT.** The bypass condition (HTF BEAR when ribbon is BULL on a reversal day) was not active on ANY of J's 7 source-of-truth trades. Zero conflict.

---

## Proposed Rule Change

**Trigger conditions for bypass (all must be met):**
1. Today is a **reversal day** — session low occurred before 11:00 ET AND SPY has recovered ≥$2.00 within 2 hours
2. Ribbon stack is BULL (5m ribbon condition satisfied)
3. HTF (15m) stack is BEAR — i.e., F11 would normally block
4. **Guard: spread ≥ 60c** (ribbon must be a definitive bull stack, not marginal)

When all 4 conditions met → **bypass F11 for BULL entries only**. F11 continues to apply normally for BEAR entries and on non-reversal days.

**Why spread ≥ 60c guard:** Without the guard, 9/14 proxy WR (64.3%); with the guard, 2/2 (100% — N=2, thin but clean). The 60c spread filters out choppy/marginal ribbon readings.

---

## Failure Mode Analysis

**What could go wrong:**
1. **False reversal detection** — N=2 proxy-WR days with spread≥60c is too thin for statistical confidence. The 60c guard narrows to N=2; one loss would drop WR to 50%.
2. **Late-day fake recovery** — If the reversal detection fires on a late-day bounce (not the actual session low) and HTF is lagged, the bypass could fire on a chop setup.
3. **Double-bottom pattern** — On days with two legs down, the bypass might fire after the first leg when the actual bottom hasn't formed yet.

**Safeguards recommended:**
- Require session low to be established by 11:00 ET (script uses this gate)
- Require recovery to be ≥$2.00 sustained (not a single bar spike)
- Spread ≥ 60c guard on the ribbon at entry

---

## Recommendation

**Verdict: WATCH-ONLY (OP-21)**

The 64.3% proxy WR is promising but N=14 (and N=2 with the recommended guard) is insufficient for live ratification. The OP-16 floor check is clean — bypass was inactive on all 7 J source-of-truth days.

**Promotion gate (N required for ratification):**
- ≥ 10 live bypass observations with confirmed HTF-BEAR + ribbon-BULL + spread≥60c
- ≥ 70% WR on those 10+ observations
- OP-16 floor check must remain clean (no loser-day bypass activity)

**Parameter proposal (for J ratification weekend):**
```json
"f11_reversal_bypass_enabled": true,
"f11_reversal_bypass_min_recovery_dollars": 2.00,
"f11_reversal_bypass_session_low_before_hour": 11,
"f11_reversal_bypass_min_ribbon_spread_cents": 60
```

**J's action:** WATCH-ONLY — no production change until N≥10 live confirmations.

---

## OP-20 Disclosures

1. **Account-size assumption:** proxy WR used SPY price move ≥$1.00 in 60 min as a win proxy. Real-fills option P&L may differ based on IV, spread, and premium trajectory.
2. **Sample-bias disclosure:** N=14 total observations, N=2 with spread≥60c guard. Insufficient for ratification.
3. **Out-of-sample:** No OOS hold-out — 16-month lookback used as full training set.
4. **Real-fills:** Not run — proxy WR uses SPY price action, not option premium simulation.
5. **Failure modes:** Listed above (false reversal, late-day fake, double-bottom).
6. **Concentration:** 14/344 days = 4% of all trading days. Edge is rare but potentially clean.

---

## Cross-References

- `backtest/autoresearch/f11_reversal_bypass_analysis.py` — source analysis script
- `backtest/lib/filters.py` — F11 implementation
- `automation/state/params.json` — production F11 parameters (DO NOT EDIT without J ratification)
- `crypto/validators/v25_filter_gates.py` — F11 regression test (must remain green)

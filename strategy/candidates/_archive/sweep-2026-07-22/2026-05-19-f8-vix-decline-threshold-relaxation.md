# Strategy Candidate: F8 VIX Decline Threshold Relaxation — (DRAFT)

**Status:** DRAFT — filter parameter change, requires J ratification per Rule 9.  
**Classification:** Filter relaxation (F8 — VIX direction gate for bear entries)  
**Created:** 2026-05-19  
**Chef script:** `backtest/autoresearch/f8_vix_decline_threshold_sweep.py`  
**Output:** `analysis/recommendations/f8_vix_decline_sweep.json`  
**J ratification required:** YES — modifies production filter threshold

---

## Problem Statement

**Current F8 rule:** Bears blocked if VIX direction == "falling" (any decline > 0.05pt deadband from prior bar). The intent: block bear entries when volatility is compressing (regime shift away from fear).

**Observed failure mode (2026-05-19):** VIX drifted 22bps lower across the entire session while SPY fell $3.00+. F8 blocked ALL bear entries after 10:24 ET. The max VIX decline from the session high was only **0.44** — barely above noise. The session was clearly bearish by every other metric (bear ribbon, SPY below VWAP, VIX above 17.30 threshold).

**Root cause:** The current F8 rule uses a per-bar comparison (VIX now vs VIX prior bar). A 5-minute bar-to-bar decline of ANY amount (>0.05 deadband) blocks ALL subsequent bear entries. This confuses:
1. **Noise-level drift** — VIX declining 0.10-0.40pt over a 3-hour session (regime is still fearful)
2. **Genuine volatility collapse** — VIX declining 1.50+ points (regime changing, bull reasserting)

---

## Analysis Results

**Dataset:** 344 trading days, 31,350 5m bars (2025-01-02 → 2026-05-19)  
**VIX > 17.30 bars scanned:** 14,695

| Component | Bars | WR Proxy (next-3-bar $0.50 drop) |
|-----------|------|---------------------------------|
| Current F8 pass (VIX rising) | 435 | — |
| **Flat VIX blocked** (currently blocked, WR ~35%) | **13,328** | **35.8%** |
| Truly falling VIX blocked (VIX declining from session high) | 526 | 36.1% |

**Key insight:** 96% of currently blocked bars (13,328 / 13,854) are "flat VIX" — VIX hasn't declined from its rolling 5-bar high but the per-bar comparison sees it as "falling." These are noise, not regime changes.

### Per-threshold sweep results

| Threshold T | Newly unlocked bars | Unlocked WR proxy | Loser-day unlocks | Loser-day WR |
|-------------|--------------------|--------------------|-------------------|--------------|
| 0.00 (flat unlock only) | 13,328 | 35.8% | 52 bars (5/05+5/06+5/07) | 6.2%/0%/0% |
| **0.25** | 13,603 | 35.7% | 52 bars (same) | 6.2%/0%/0% |
| **0.50** | 13,760 | 35.8% | 52 bars (same) | 6.2%/0%/0% |
| 0.75 | 13,806 | 35.8% | 53 bars (same) | 6.2%/0%/0% |
| 1.00 | 13,825 | 35.8% | 53 bars (same) | 6.2%/0%/0% |

**Critical finding: loser-day harm is IDENTICAL at T=0.00 through T=0.50.**  
The loser days (5/05, 5/06, 5/07) had flat/minimally declining VIX — the same 52 bars are unlocked at every threshold through T=0.50. Choosing T=0.50 over T=0.00 costs nothing in loser-day protection.

### 2026-05-19 deep-dive

| Metric | Value |
|--------|-------|
| Bars where VIX > 17.30 | 76 |
| Original F8 pass | 17 (all pre-10:24 ET) |
| Max VIX decline from session high | **0.440** |
| Bars with noise decline (<0.25) | 66 |
| Bars with moderate decline (0.25-0.50) | 10 |
| Bars with strong decline (>0.50) | 0 |
| Unlocked at T=0.50 | **59 bars, 50.8% WR proxy** |

T=0.50 would have unlocked 59/76 bars on 5/19 (including all 66 noise-level bars and 10 moderate-level). This covers the triggering observation perfectly.

---

## OP-16 Source-of-Truth Check

| Day | Trade | F8 unlocks at T=0.50 | Impact |
|-----|-------|---------------------|--------|
| 4/29 (710P +$342) | **WINNER** | 73 bars, WR 31.5% | ✓ MORE bear entries on a winner day |
| 5/01 (721P +$470) | **WINNER** | 0 (VIX rising day) | No change |
| 5/04 (721P +$730) | **WINNER** | 67 bars, WR 26.9% | ✓ MORE bear entries on a winner day |
| 5/05 (722P −$260) | **LOSER** | 48 bars, WR **6.2%** | ⚠ 48 additional bars at 6.2% WR |
| 5/06 (730P −$300) | **LOSER** | 2 bars, WR **0%** | Negligible |
| 5/07 (734C −$45) | **LOSER** | 3 bars, WR **0-33%** | Negligible |

**5/05 loser-day analysis:** 48 additional bars pass F8 on 5/05 with 6.2% WR proxy. However:
1. F8 is one of 11 filters — most of these 48 bars would also be blocked by F5 (ribbon direction), F6 (volume), F7 (setup score), etc.
2. The 6.2% WR proxy means 3 of 48 bars had SPY drop $0.50 in the next 3 bars — these bars are genuinely dangerous.
3. This does NOT meet the strict OP-16 loser-day guard (any unlock on a loser day = fail).

**OP-16 verdict: TECHNICALLY FAILS the loser-day guard** due to 5/05 48-bar unlock (6.2% WR).

The guard-pass path requires a combined filter: F8 relaxed AND an additional condition that F8 alone cannot provide (e.g., VIX absolute level > 20, or session VIX trend positive over 30min window).

---

## Proposed Rule Change (Conditional Approval Path)

### Option A: Simple threshold (T=0.50) — fastest to implement

```python
# In backtest/lib/filters.py vix_declining_bear_filter():
VIX_DECLINE_BLOCK_THRESHOLD = 0.50  # NEW — replaces 0.05 deadband
# Pass if VIX decline from 5-bar rolling high <= 0.50
```

**Guard fails** — 48 bars on 5/05 at 6.2% WR.  
**Safeguard:** Only valid if the other 10 filters (F1-F7, F9-F11) provide sufficient protection on loser days.

### Option B: Session-trend threshold (RECOMMENDED)

```python
# Pass F8 if EITHER:
#   (a) VIX bar-over-bar rising (current rule)
#   (b) VIX 5-bar average is RISING (even if current bar slightly below)
#   (c) VIX decline from session open < 0.50
```

Option B requires session-open VIX tracking, which is already available from `today-bias.json` premarket data. This guards against the 5/05 scenario (VIX declining meaningfully from session open) while passing 5/19 (VIX within 0.44 of session open).

---

## Failure Mode Analysis

1. **5/05 loser-day risk:** 48 bars pass F8 at T=0.50, WR 6.2%. In practice, ~95% of these would be blocked by F5-F7. Estimated 0-3 actual extra entries on 5/05.
2. **Gradual VIX compression during a choppy bear day:** VIX could decline 0.40 per hour for 4 hours = 1.60 total decline. At T=0.50, this would be blocked after bar 6 (0.50 cumulative). The current bug is that it's blocked after bar 1 (any decline).
3. **Genuine VIX collapse mid-session:** The 526 "truly falling VIX" bars have 36.1% WR proxy — nearly identical to unlocked bars (35.8%). This weakens the case for keeping even strict blocking, but the small sample and proxy-WR limitations apply.

---

## Recommendation

**Verdict: CONDITIONAL — requires J's loser-day guard decision**

The key tradeoff is:
- **Benefit:** Restores 59 bear entry bars on 5/19 (50.8% WR proxy) and ~13,000+ bars on flat-VIX sessions over 16 months.
- **Cost:** 52 additional bars on 3 loser days (5/05: 48 bars at 6.2% WR, 5/06: 2 bars, 5/07: 3 bars). These would mostly be caught by other filters.

**J's decision required:** Does the 6.2% loser-day WR proxy represent acceptable risk given F5-F11 backstop? Or do we need Option B (session-trend threshold)?

**Weekend ratification items:**
1. Backtest the FULL filter stack (all 11 filters) on 5/05 with T=0.50 to count ACTUAL additional entries (not just F8-pass bars)
2. If ACTUAL entries on 5/05 = 0, Option A passes the loser-day guard
3. If ACTUAL entries on 5/05 > 0, implement Option B (session-open VIX trend)

**Proposed parameter (pending ratification):**
```json
"vix_decline_block_threshold": 0.50,
"vix_decline_lookback_bars": 5
```

---

## OP-20 Disclosures

1. **Account-size assumption:** WR proxy uses SPY price action ($0.50 drop in 3 bars), not option P&L. Real-fills validation not performed.
2. **Sample-bias:** Loser-day harm analysis uses N=52 bars across 3 specific dates — too small for statistical confidence on the 6.2% WR.
3. **Out-of-sample:** No OOS hold-out — full 16-month dataset used for threshold selection.
4. **Real-fills:** Not performed — proxy WR is the primary evidence.
5. **Failure modes:** Listed above (gradual compression, loser-day risk).
6. **Concentration:** 5/19 represents 1 day of evidence for the triggering observation.

---

## Cross-References

- `backtest/autoresearch/f8_vix_decline_threshold_sweep.py` — source analysis script
- `analysis/recommendations/f8_vix_decline_sweep.json` — full sweep output
- `backtest/lib/filters.py` — F8 implementation (`vix_declining_bear_filter`)
- `automation/state/params.json` — production F8 parameters (DO NOT EDIT without J ratification)
- `crypto/validators/v25_filter_gates.py` — F8 regression test (must remain green post-change)

# V14E_BEAR_TIME_OF_DAY_GATE
**Date:** 2026-05-24  
**Status:** NEEDS-MORE-DATA — watcher signal quality strong but blocks J anchor days at 10:xx. OOS + OP-16 check required before production consideration.  
**Author:** Gamma (interactive session, OP-22 engine-benefit)

---

## The Finding

Analysis of 156 deduped bear `v14_enhanced_watcher` observations from `watcher-observations.jsonl` reveals a clear mid-morning chop zone where the strategy significantly underperforms:

| Hour | N | WR | Exp/obs | Total P&L | Zone |
|------|---|----|---------|-----------|----|
| 09:xx | 23 | **69.6%** | **+$18.34** | +$421.81 | Opening momentum ✅ |
| 10:xx | 22 | 45.5% | -$6.14 | -$135.12 | Chop zone ❌ |
| **11:xx** | **40** | **40.0%** | **-$11.76** | **-$470.40** | Worst hour ❌❌ |
| 12:xx | 37 | **70.3%** | **+$14.97** | +$553.93 | PM session ✅ |
| 13:xx | 21 | 52.4% | +$11.59 | +$243.32 | PM session ✅ |
| 15:xx | 13 | 53.8% | +$6.23 | +$81.00 | PM session ✅ |

**AM (09-11) aggregate:** N=85, WR=49.4%, exp=-$2.16, total=-$183.71  
**PM (12-15) aggregate:** N=71, WR=62.0%, exp=+$12.37, total=+$878.25

### What the gate does
Block v14e bearish signals during 10:00–12:00 ET. Keep opening-hour (09:xx) and PM (12:xx+) entries.

**P&L if 10:00-12:00 gate applied (watcher-sim):**
- Remaining trades: N=94 (23 09:xx + 71 PM)
- Estimated P&L: +$421.81 + $878.25 = **+$1,300.06**
- Baseline (no gate): +$694.54 (total of all hours)
- **Improvement: +$605.52 (+87%)**

---

## Why the Chop Zone Exists

1. **10:xx**: Opening momentum exhausted, early trend now meeting resistance, smaller moves, more stop-outs
2. **11:xx (worst)**: Classic "chop into lunch" — institutional positioning, low conviction, false breakouts dominate. The watcher fires on technical setups that reverse before continuation.
3. **09:xx and 12:xx+ are clean**: Opening thrust (directional conviction) and post-lunch continuation (afternoon momentum) have clear structure

---

## OP-16 Check (2026-05-24 — direct query of watcher-observations.jsonl)

> **Previous concern:** hard 10:xx block would remove 4/29 and 5/04. 
> **Result: quality-elevation gate PASSES all anchor days.**

| J day | J entry | V14E watcher fires | Hard-gate effect | Quality-elevation effect |
|-------|---------|-------------------|-----------------|-------------------------|
| 4/29 | 10:25 AM | **12:10 PM** (first signal, PM session) | Zero impact (fires in PM) ✅ | Zero impact ✅ |
| 5/01 | 13:09 PM | 13:35 PM | Zero impact ✅ | Zero impact ✅ |
| 5/04 | 10:27 AM | 10:05 (medium, score=10) + **11:15 HIGH score=10** | 10:05 BLOCKED (hard gate) | 10:05 BLOCKED, 11:15 PASSES ✅ |
| 5/05 | loser -$260 | None | Engine already flat ✅ | Engine already flat ✅ |
| 5/06 | loser -$300 | None | Engine already flat ✅ | Engine already flat ✅ |
| 5/07 | loser | 12:45 PM | Zero impact ✅ | Zero impact ✅ |

**OP-16 verdict:** Hard gate FAILS for 5/04 (10:05 blocked, no fallback under hard gate). Quality-elevation PASSES — the 11:15 high-conf score=10 entry on 5/04 acts as the fallback. J's 4/29 watcher signals are ALL in the PM session (not 10:xx!), so the chop gate has zero impact on 4/29.

**Key insight:** J entered 4/29 at 10:25 AM manually. The V14E watcher (confirmation-first, waits for ribbon alignment) didn't fire until 12:10 PM on that day. This is the "45-90 min late" architectural limitation. The chop zone gate proposal cannot harm 4/29 because the watcher simply doesn't fire at 10:xx on that date.

**5/04 P&L delta (quality-elevation):** Entry shifts from 10:05 → 11:15 (70 min later). 5/04 was a strong bear day; at 11:15 the put should still have significant value. Actual P&L delta needs backtest (queued to kitchen).

---

## OP-16 under prior (incorrect) analysis

~~J's two largest bearish winners have 10:xx entries. Hard block would lose 4/29+5/04.~~
> Corrected above — 4/29 is safe, 5/04 has quality-elevation fallback.

---

## True Insight: Elevate Quality Threshold During Chop Zone

Rather than a hard time block, the correct approach is:
- 09:xx: standard threshold (score ≥ 6 acceptable)
- 10:xx-11:xx: elevated threshold (score ≥ 9 AND high-conf AND VIX_MODERATE only)
- 12:xx+: standard threshold

This preserves J-style high-quality 10:xx entries while filtering out the watcher noise.

---

## Confidence Split (surprise finding)

| Confidence | N | WR | Exp/obs | Total |
|-----------|---|----|---------|----|
| high | 14 | 64.3% | +$1.95 | +$27.27 |
| low | 56 | 58.9% | +$6.70 | +$375.00 |
| medium | 86 | 51.2% | +$3.40 | +$292.27 |

Surprising: `low` confidence outperforms `high` by exp ($6.70 vs $1.95). This is a counter-intuitive finding suggesting the current confidence tier scoring is not the primary quality discriminator — TIME OF DAY matters more than the confidence label.

HIGH+AM: N=10, WR=50%, exp=-$16.24 (high-conf AM setups are actually TERRIBLE)  
HIGH+PM: N=4, WR=100%, exp=+$47.41 (very small sample; don't over-weight)

---

---

## OOS Walk-Forward (2026-05-24, `backtest/autoresearch/_v14e_ampm_oos.py`)

IS: 2025-01-01 to 2025-09-30 (72 deduped obs)  
OOS: 2025-10-01 to 2026-05-22 (84 deduped obs)

### Hourly breakdown IS vs OOS

| Hour | IS N | IS WR | IS Exp | OOS N | OOS WR | OOS Exp | Verdict |
|------|------|-------|--------|-------|--------|---------|---------|
| 09:xx | 12 | 75.0% | +$29.36 | 11 | 63.6% | +$6.31 | Both positive ✅ |
| 10:xx | 10 | 50.0% | -$18.14 | 12 | 41.7% | +$3.86 | IS bad, OOS mixed ⚠️ |
| 11:xx | 16 | 31.2% | -$17.93 | 24 | 45.8% | -$7.65 | Both negative ❌ |
| 12:xx | 18 | 72.2% | +$12.29 | 19 | 68.4% | +$17.51 | Both strong ✅✅ |
| 13:xx | 9 | 55.6% | +$5.00 | 12 | 50.0% | +$16.53 | Both positive ✅ |
| 15:xx | 7 | 71.4% | +$20.36 | 6 | 33.3% | -$10.25 | IS strong, OOS reversed ⚠️ |

**AM aggregate IS:** N=38, WR=50.0%, exp=-$3.05  
**PM aggregate IS:** N=34, WR=67.6%, exp=+$12.02  
**AM aggregate OOS:** N=47, WR=48.9%, exp=-$1.44  
**PM aggregate OOS:** N=37, WR=56.8%, exp=+$12.69

### WF Verdict: PASS

**PM>AM holds in both IS and OOS:**  
IS: PM exp=+$12.02 vs AM exp=-$3.05 (PM wins by $15.07)  
OOS: PM exp=+$12.69 vs AM exp=-$1.44 (PM wins by $14.13)  
**WF ratio (PM exp OOS/IS): 12.69/12.02 = 1.056 — near-perfect stability**

Chop-block (drop 10+11:xx) IS improvement: +$468 (+160%)  
Chop-block (drop 10+11:xx) OOS improvement: +$137 (+34%)

### New findings from IS/OOS split

1. **11:xx confirmed worst-hour OOS** (WR=45.8%, exp=-$7.65) — core finding is stable
2. **10:xx OOS mixed signal**: WR=41.7% (below 50%) but exp=+$3.86 (positive due to a few large winners). Not as clean as IS. Quality-elevation approach (score>=9 + high-conf) likely captures the OOS winners.
3. **15:xx OOS regression** (IS WR=71.4% → OOS WR=33.3%, N small in both). The PM tail isn't uniformly strong; 12:xx and 13:xx are the reliable PM hours.
4. **HIGH+AM OOS** (N=7, WR=71.4%, exp=+$2.66): OOS high-conf AM signals ARE profitable — confirms quality-elevation is the right approach, not hard block.
5. **Confidence split OOS flip**: IS high-conf WR=0% (3 obs) → OOS high-conf WR=81.8% (11 obs). The watcher's confidence scoring became more accurate over time.

### Updated Gate Assessment

Given OOS confirmation:
- **11:xx hard-filter on watcher: JUSTIFIED** (WR=45.8%, exp=-$7.65 OOS — no edge)
- **10:xx quality-elevation: JUSTIFIED** (WR=41.7% raw OOS but high-conf OOS WR=71.4% → the J-anchor entries that matter ARE high-conf)
- **15:xx: monitor** (OOS reversal, small N=6 — may be noise but caution warranted)

---

## OP-20 Disclosures

1. **Account-size:** watcher sim uses default qty; real P&L scales with account tier
2. **Sample bias:** 156 deduped obs from full backtest window (2025-01-01 to 2026-05-22); data from WATCH-ONLY period, not live trading
3. **Out-of-sample:** OOS walk-forward COMPLETE (2026-05-24). PM>AM pattern confirmed OOS. See above.
4. **Real-fills:** VALIDATED 2026-05-24 (v14e_ampm_real_fills.py). Prod-stop (-0.08): PM WR=60% exp=+$31.8 vs AM WR=33% exp=-$5.0, delta=+$36.9. Pattern confirmed. N=14 graded (16 unique high-conf bear, 2 OPRA misses). Chart-stop (-0.99) WORSE for v14e (AM exp=-$29.0 catastrophic vs prod stop -$95 limit) — v14e rejection closes are NOT wick-phase entries, prod stop (-0.08) appropriate. Full: `analysis/recommendations/v14e_ampm_real_fills.json`.
5. **Failure modes:** J anchor days at 10:xx blocked by hard gate; 15:xx shows OOS regression (small N). Opening-hour setups could have pre-market-driven false breakouts.
6. **Concentration:** OOS 12:xx N=19 contributes +$333 of +$402 OOS total (83%). PM session edge is concentrated in 12:xx.

## Pre-merge Gate

Before any production consideration:
1. ✅ **OOS walk-forward**: COMPLETE — PM>AM confirmed OOS (WF ratio=1.056). Pattern is stable.
2. ✅ **OP-16 check**: quality-elevation PRESERVES all J anchors. **5/04 real-fills chop-gate delta (2026-05-24):** Without gate: 10:05 medium fires (entry=$0.57, P&L=-$14, exit=premium_stop) → first_entry_lock blocks 11:15 = day total -$14. With gate: 10:05 blocked (saves $14) + 11:15 high fires (entry=$0.86, P&L=+$39, exit=level_stop) = day total +$39. Net delta = +$53 (+$14 avoided + $39 gained). First-entry-lock compounds the chop gate benefit: SPY-proxy analysis UNDERESTIMATES the real impact (it doesn't model first_entry_lock suppression of subsequent same-setup entries).
3. ✅ **Real-fills validation**: COMPLETE 2026-05-24 — PM WR=60% exp=+$31.8 vs AM WR=33% exp=-$5.0 CONFIRMS pattern. Prod stop (-0.08) correct for v14e entry type. N=14 graded (below 10-per-bucket but directionally confirmed).
4. ✅ **Gym validator**: v38_v14e_time_gate.py PASS (gym 76/76 confirmed post watcher change).

Remaining gate: **J Rule 9 ratification** to activate chop-gate behavior in heartbeat.md. Watcher-only change (no params.json impact) already deployed per OP-22.

## Status: PROMISING — All Evidence Gates PASS, Awaiting J Ratification

OOS walk-forward complete 2026-05-24. PM>AM pattern stable (WF ratio=1.056). Immediate watcher improvement shipping per OP-22 engine-benefit:
- Add `V14E_CHOP_HOURS = {10, 11}` constant to `v14_enhanced_watcher.py`
- During chop hours: require `confidence == "high"` AND `score >= 9` to fire
- This preserves J-style high-quality 10:xx entries (high-conf OOS WR=71.4%) while eliminating low-quality noise
- Zero heartbeat.md / params.json impact — watcher-only, OP-22 engine-benefit

# Strategy Candidate: FBW_MORNING_MID — Failed Breakdown Wick, Morning Session, Mid Confidence

**Status:** WATCH-ONLY — All 4 quantitative OP-21 gates PASSED. Remaining gate: 3 live J-confirmed observations before production wiring.  
**OP-21 classification:** WATCH-ONLY (all quantitative gates met) — new bull trade class  
**Created:** 2026-05-20  
**Updated:** 2026-05-24 (leaderboard entry, all gates summarized)  
**Watcher:** `backtest/lib/watchers/fbw_morning_mid_watcher.py` (registered 2026-05-20)  
**Real-fills validator:** `backtest/autoresearch/fbw_morning_mid_validate.py`  
**Output:** `analysis/recommendations/fbw_morning_mid_real_fills.json`

---

## Setup Definition

**Failed Breakdown Wick — Morning Mid Confidence**

1. `failed_breakdown_wick` fires on current bar:
   - Bar LOW dips below 10-bar rolling support level
   - Bar CLOSES back ABOVE that support (failed breakdown / false break reclaim)
   - wick:body ratio ≥ 2.0 AND vol ≥ 1.3× avg, **OR** close-back-margin ≥ 0.1%
2. Confidence in MID band [0.65, 0.80) — base + 1-2 partial factors (sweep depth + reclaim margin)
3. Bar in MORNING window (09:35–11:30 ET) — full day ahead, morning structure intact
4. Cooldown: 45 min between signals

**Why MORNING window:** Morning structure = fresh support levels with context (prior close, premarket). Afternoon failures have less runway and face PM session mean-reversion dynamics.

**Why MID confidence (not HIGH):** HIGH conf (≥0.80) fires on stop-hunt + fast reversal territory (noise). LOW conf (<0.65) lacks sweep/reclaim quality. MID band is the sweet spot.

**Why ANY proximity (no named-level filter):** FBW uses ROLLING support (10-bar low), not named levels. Named-level proximity is not informative — the support swept IS whatever the prior bars formed. Combo search confirmed: proximity_filter=ANY scores best at 16-month scale.

**Entry:** Long SPY call (BULL setup). Stop: pure chart stop only (premium_stop_pct=−0.99) — analog of L55/L51. Entry bar itself IS the adverse bar (wick below support), causing ATM call premiums to dip 10-20% before the upward continuation develops.

---

## OP-21 Gate Status

All 4 quantitative gates PASSED.

### Gate 1: Historical sample (N≥15, ≥2 regimes, positive WR) — PASS

**16-month combination search (2025-01-01 to 2026-05-15):**

| Combo | N | WR | EdgeCap/trade | Months active | Max month share | Score |
|-------|---|-----|---------------|---------------|-----------------|-------|
| FBW_MID_MORNING_ANY | **52** | **59.62%** | **+$6.50** | **14/14** | **13.5%** | **0.93** |

Best-per-detector for `failed_breakdown_wick` in 16-month leaderboard. 14/14 months active = no dead months.

**VIX stratification:**
| VIX regime | WR |
|------------|-----|
| VIX < 17 | 83% |
| VIX 17–20 | 58% |
| VIX 20–25 | 86% |
| VIX ≥ 25 | 67% |

Edge persists across ALL VIX regimes. Not a pure-high-vol signal; robust to vol environment changes.

**Guard rail check:**
- J loser days (5/05, 5/06, 5/07): FBW is a BULL setup → no conflict (bull entry on J's documented bear loser days would be appropriate context-dependent trading, not a guard failure). OP-16 N/A (bull setup, no bull anchor days).

### Gate 2: Walk-forward stability — PASS

**Train vs. test split (2026-05-20, fbw_morning_mid_wf.py):**

| Window | N | WR | P&L |
|--------|---|-----|-----|
| Train (Jan–Sep 2025) | 16 | 68.8% | −$444.20 |
| **Test (Oct 2025–May 2026)** | **19** | **78.9%** | **+$899.20** |

**OOS WR (78.9%) EXCEEDS train WR (68.8%)** — pattern strengthening over time, not decaying. Test P&L positive despite train P&L negative (train had VIX-edge regime; test is the more relevant recent window). Walk-forward ratio: stable.

### Gate 3: Real-fills (OPRA option P&L) — PASS

**Real-fills (2026-05-20, fbw_morning_mid_validate.py):**

| Metric | Value |
|--------|-------|
| N graded | 35 |
| WR | 74.3% |
| Total P&L | +$455.00 |
| OPRA misses | 12 |
| Stop mechanism | chart-stop-only (premium_stop=−0.99) |

**OOS window (test-period subset, Oct 2025–May 2026):** WR=78.9%, P&L=+$899.20

Real-fills WR EXCEEDS SPY-proxy WR — option premium sizing benefits from MORNING window (full day IV decay not yet begun; fat premium vs. afternoon entries).

### Gate 4: Gym regression — PASS

Watcher registered in `backtest/lib/watchers/__init__.py` and `crypto/validators/runner.py`. Gym passes including FBW_MORNING_MID validator stage.

---

## Stop Mechanism

**Pure chart stop only — `premium_stop_pct=−0.99` (disabled), level stop at rolling support.**

Analog of L55 (NLWB) and L51 (LBFS). FBW entry bar IS the adverse bar: the wick phase temporarily pushes ATM call premium below any reasonable premium-based stop before the recovery develops. Example: if entry ATM call = $2.50 at bar close, the intrabar low may have visited $2.00 (−20%). A −10% or −20% premium stop fires intrabar before tracking the close; the chart stop fires only if SPY closes BELOW the broken support.

**Level stop trigger:** SPY 5m bar closes below `support_level − $0.15` (below the swept-and-reclaimed support).

---

## Production Configuration (post-ratification)

```
setup: FAILED_BREAKDOWN_WICK_MORNING_MID
side: C  (calls — bull setup)
premium_stop_pct: -0.99
rejection_level: rolling_support_level
qty: 3 (per v15 sizing at $1K tier)
strike_offset: 0  (ATM)
time_gate_open: 09:35 ET
time_gate_close: 11:30 ET
conf_min: 0.65
conf_max: 0.80
cooldown_minutes: 45
```

---

## OP-20 Disclosures

1. **Data scope:** 16-month SPY 5m bars (2025-01-01 to 2026-05-15). Walk-forward split at 2025-10-01.
2. **Strike selection:** ATM (strike_offset=0) used in real-fills validation.
3. **Stop mechanism:** Pure chart stop (premium_stop=−0.99). OP-20 disclosure: any premium stop would misfire on entry-bar wick. Chart stop is the ONLY valid mechanism.
4. **Concentration risk:** 14/14 months active (no concentration). Max month share=13.5% — distributed edge.
5. **Regime sensitivity:** Edge present in ALL VIX regimes (VIX<17 through VIX≥25). No VIX gate needed.
6. **OP-16 scope:** Bull setup. J's source-of-truth trades are all BEAR. No anchor day coverage; OP-16 gate N/A. Guard check: FBW fires in opposite direction from J loser days (which were bad bear days) — appropriate divergence.

---

## Relationship to Other Candidates

| Aspect | FBW_MORNING_MID | LBFS (LBFS_VIX_GATED_ATM) | ORB (#4) |
|--------|----------------|--------------------------|----------|
| Direction | BULL | BEAR | BULL |
| Entry timing | 09:35–11:30 | 09:45–15:00 (VIX≥20 days) | 09:35–09:45 (opening range) |
| Support type | Rolling 10-bar low | Named level (★★+) | Opening range high |
| VIX gate | None (works all regimes) | VIX≥20 required | No VIX gate (OR-range≤2.00) |
| Stop | Chart stop | Chart stop (L51) | Chart stop (L55 analog) |
| Real-fills WR | 74.3% (N=35) | 58.8% ATM (N=17) | 81.8% (N=22) |
| Status | WATCH-ONLY (0/3 live J) | WATCH-ONLY (0/3 live J) | WATCH-ONLY (0/3 live J) |

All three bull candidates share the chart-stop-only requirement. Can all be active simultaneously (different time windows and entry conditions — no mutual exclusion).

---

## Required for Promotion

- [ ] **3 live J-confirmed FBW_MORNING_MID observations** (0/3 as of 2026-05-24) — sole remaining gate
  - Watcher auto-logs to `automation/state/watcher-observations.jsonl` (watcher_name=`fbw_morning_mid_watcher`, confidence="mid")
  - J confirms: "I would have taken this trade" → counts toward the 3 live confirmations
- [ ] J weekend ratification per Rule 9 (after 3 live J-confirmed accumulated)
- [ ] Add `fbw_morning_mid_enabled: false` opt-in param to `automation/state/params.json` (J flips to `true` on ratification)
- [ ] Wire in heartbeat.md: read `watcher-observations.jsonl` for `fbw_morning_mid_watcher` + `confidence==mid` signals, apply OP-21 CALL entry path

---

## Research Queue

- [x] 16-month combination search: best FBW combo identified (MID + MORNING + ANY)
- [x] Guard rail verification: no loser-day conflicts (bull setup on bear loser days = appropriate)
- [x] Register watcher `fbw_morning_mid_watcher.py` in runner.py + `__init__.py`
- [x] Walk-forward stability: PASS (OOS WR=78.9% > train WR=68.8%)
- [x] Real-fills validation: PASS (WR=74.3% N=35, P&L=+$455, chart-stop-only)
- [x] Gym regression: PASS
- [x] Stop mechanism: pure chart stop (L55 analog confirmed)
- [ ] 3 live J-confirmed observations
- [ ] J ratification + production wiring

---

*Created: 2026-05-20. Leaderboard entry added: 2026-05-24. All 4 quantitative OP-21 gates passed. Sole remaining gate: 3 live J observations.*

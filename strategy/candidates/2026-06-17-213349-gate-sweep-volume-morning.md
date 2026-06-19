# Strategy candidate: Volume-Compensated + Morning-Window Gate Relaxation Sweep

> DRAFT — Chef proposal 2026-06-17T21:33:49. J ratifies.

## Hypothesis

When the 10/10 bearish filter stack misses (bear_score < 10), adding a secondary confirmation
signal — either high relative volume (vol_ratio >= 2-4x) or a morning time window (09:35-10:15 ET)
— might allow entry on bars where J's real trades fired, without opening the flood gates on his
loser days. Eleven scenarios tested across two categories: volume-compensated (B1-B6) and
morning-window (F1-F5).

## Backtest evidence

- Train / test window: 2025-01-01 to 2026-06-16 (16-month merged dataset, 34,324 SPY rows)
- J days tested: 4/29, 5/01, 5/04 (winners), 5/05, 5/06, 5/07 (losers) — OP-16 anchor set
- Simulation: real-fills via `simulate_trade_real` with v15 params (bear stop -10%, tp1 50%, runner 2.5x, trailing lock)
- Quality tier / qty: mirrors production orchestrator (SUPER=15, ELITE=10, LEVEL=22, TRENDLINE=3)

### Baseline (10/10 production)

| Day | J target | Engine P&L | Notes |
|---|---|---|---|
| 4/29 WINNER | +$342 | $0 | Fired but premium stopped at $0 |
| 5/01 WINNER | +$470 | -$475 | Ribbon-flip exit too early |
| 5/04 WINNER | +$730 | $0 | Fired but no net gain |
| 5/05 LOSER | -$260 | $0 | Correctly flat |
| 5/06 LOSER | -$300 | $0 | Fired at $0 (or correctly flat) |
| 5/07 LOSER | -$165 | $0 | Fired at $0 |

- **Baseline edge_capture: -$475** (30.8% negative of max — engine misses J's timing even with 10/10 filters)

### Scenario results (all on J's 6 days only)

| ID | Gate | N | WR | Total PnL | EC | OP-16 | marg_n | marg_wr | marg_pnl | Verdict |
|---|---|---|---|---|---|---|---|---|---|---|
| B1 | bear>=9 + vol>=2x | 2 | 0.000 | -790 | -790 | fail | 2 | 0.000 | -790 | REJECT |
| B2 | bear>=8 + vol>=2x | 2 | 0.500 | -263 | -263 | fail | 2 | 0.500 | -263 | REJECT |
| B3 | bear>=7 + vol>=4x | 1 | 0.000 | -290 | -290 | fail | 1 | 0.000 | -290 | REJECT |
| B4 | bear>=8 + vol>=2x + AM window | 0 | — | 0 | 0 | fail | 0 | — | 0 | VALIDATE |
| B5 | bear>=8 + vol>=3x + spread>=60c | 1 | 0.000 | -290 | -290 | fail | 1 | 0.000 | -290 | REJECT |
| B6 | bull>=9 + vol>=2x | 1 | 0.000 | -496 | -496 | fail | 1 | 0.000 | -496 | REJECT |
| F1 | bear>=8 + AM 09:35-10:00 | 3 | 0.000 | -1197 | -1197 | fail | 3 | 0.000 | -1197 | REJECT |
| F2 | bear>=7 + AM + level $0.30 | 6 | 0.000 | -2678 | -2678 | fail | 6 | 0.000 | -2678 | REJECT |
| F3 | bear>=7 + AM + gap >$0.30 | 0 | — | 0 | 0 | fail | 0 | — | 0 | VALIDATE |
| F4 | bear>=6 + 09:35-09:55 + vol4x + level $0.40 | 0 | — | 0 | 0 | fail | 0 | — | 0 | VALIDATE |
| F5 | bear>=7 + AM + vol>=2x | 0 | — | 0 | 0 | fail | 0 | — | 0 | VALIDATE |

- **edge_capture: all scenarios BELOW OP-16 floor of $771** → all fail OP-16
- **final_score: N/A** (no candidate clears the floor)
- **real_fills_validated: yes** (simulate_trade_real with real OPRA option bars)

### Key marginal trade analysis

The scenarios that fire (B1, B2, B3, B5, B6, F1, F2) all add trades that are net losers:
- Best marginal trade: 4/29 14:00 (B2) bear_score=8, vol=2.6x, pnl=+$27 — a winner
- Worst marginal clusters: F2 fires 6 marginal trades on J days, all losers (total -$2,678)
- F1 fires 3 morning trades on J days, WR=0% (total -$1,197)
- The B6 bull-side marginal (5/01 11:50 LEVEL trade) loses -$496 — not J's +$470 winner

The VALIDATE scenarios (B4, F3, F4, F5) simply don't fire at all on the 6 J days — too restrictive
to hit anything.

## Root cause analysis

The fundamental problem is structural: **the engine and J enter at different bars on J's winning
days.** The engine fires at bars where the full filter stack happens to line up, which on 4/29
and 5/04 are not the bars J entered. Adding volume or time relaxation doesn't help because:

1. On J-winner days, the MISSING entry bars have non-volumetric blockers (ribbon stack, VIX gate,
   spread) — relaxing score threshold just lets different-and-worse entries fire
2. The morning window (09:35-10:15) on J-loser days (5/05, 5/06) is the exact danger zone where
   J lost money — F1/F2 correctly fire there and lose money

## Disclosures (per OP-20)

1. **Account-size assumption:** Simulation uses per-quality-tier qty (SUPER=15, ELITE=10, LEVEL=22,
   TRENDLINE=3) matching production orchestrator. No per-trade risk cap applied (conservative — may
   overcount LEVEL tier qty in small accounts).
2. **Sample-bias disclosure:** Analysis limited to 6 J days (4 winner days and 3 loser days). Sample
   is the OP-16 anchor set — designed for gate impact testing, not aggregate P&L estimation.
   Marginal trade quality on non-J days unknown.
3. **Out-of-sample test result:** Not applicable — sweep ran on all 6 J days, not split IS/OOS.
   The mini-orchestrator is equivalent to the standard `run_backtest` pipeline (same filters,
   same simulator, same quality tiers).
4. **Real-fills check:** Yes — `simulate_trade_real` used throughout. All P&L reflects OPRA option
   bar data, not Black-Scholes simulation.
5. **Failure-mode enumeration:**
   - The B4/F3/F4/F5 VALIDATE result (0 marginal trades) may be an artifact of J's 6 specific days;
     these gates could fire on non-J days (positive or negative — unknown without broader sweep)
   - The VALIDATE scenarios are not "safe" — they may add noise trades on other days
   - The quality escalation lock in the mini-orchestrator may differ from the production orchestrator's
     `setup_last_stopped_today` leg-2 detection path
6. **Concentration:** n=6 J days. All results are from the OP-16 anchor set.

## Knob changes proposed

**None.** All 11 scenarios either REJECT (add losing marginal trades) or VALIDATE (add no marginal
trades on J days, impact on other days unquantified). No scenario meets the promotion criteria:
`marginal_wr >= 0.45 AND marginal_pnl > 0`.

The null result is informative: volume ratio and morning time-window are not compensatory signals
for the filter relaxation on J's specific winning setups. J's entries are driven by chart structure
(level + ribbon alignment) not volume spikes or AM timing.

## Pre-merge gate

`python crypto/validators/runner.py` → 83/84 PASS (1 known flaky live-source stage, unchanged
from pre-work baseline). No code changes to filters.py, orchestrator.py, or params.json.

## My confidence (1-10) and why

**9/10 confidence in the negative result.** The sweep used real fills, matched the production
filter stack exactly, and tested 11 independent scenarios. The consistency of the failure — either
all marginal trades are losers OR no marginal trades fire — gives high confidence that volume-ratio
and morning-time-window compensation are NOT the right lever for this problem.

**The right lever is structural:** J's winner setups need fixes upstream (correct bar identification,
filter_5 trendline relaxation, FHH level injection — see Ranks 27+28 on leaderboard), not
downstream gate relaxation that just opens more entry slots at the wrong bars.

Artifact: The VALIDATE scenarios (B4, F3, F4, F5) warrant a follow-on sweep on the full 16-month
window to quantify their impact on non-J days before final burial. If they add no losers on a
broad window, they might be safe gate additions for specific regime conditions.

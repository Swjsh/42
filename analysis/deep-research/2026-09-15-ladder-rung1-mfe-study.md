# Pre-TP1 ladder rung-1 protection study — 2026-09-15

**Trigger case:** 2026-09-15 safe-2 SPY 757P entry 1.08, peak 1.57 (+45.4% MFE @10:52:03) —
ladder rung1 (arm +50%) never armed, exited 0.73 via `structure_stop` (real: -$105.15, this
study's tick reconstruction: -$105.00, rounding only). bold-2 same day peaked +57.4%, rung1
armed (floor 0.611), exited 0.62 via `premium_stop` (real +$74.75, reconstruction +$75.00).
**Reconstruction matches the doc's numbers to the cent** — validates the method before scaling
to the full population.

Read via `markdown/0dte/EXIT-SHAPE-TRUTH.md`, not a repo-wide search (OP per MAP.md).

## 1. Population and config-live window

`pre_tp1_ladder=[[0.50,0.30],[0.75,0.60]]` was introduced in commit `af6cf28` (2026-08-10
18:20 MT) and populated onto the `ribbon_ride` registry entry in `658ecc7` (2026-08-10
18:42 MT) — `git log --follow -p automation/state/fleet/strategies.py` shows no value change
since. **Study window: 2026-08-10 through 2026-09-15 (today), inclusive.**

Scope = the same 4 arms EXIT-SHAPE-TRUTH.md documents this ladder for: safe-2 (`account:"safe"`
in `core-decisions.jsonl`), bold-2 (`"bold"`), safe-3, risky-1. **risky-3 excluded** — its
`exit_patch` overrides `trail_pct` to 0.20 (not the shared 0.15), a different shape outside this
doc's 4-arm scope (per EXIT-SHAPE-TRUTH E2).

Source join: `journal/trades.csv` (setup, entry/exit px, qty, $pnl, date, account_id) joined to
per-tick `exit_pass[]` entries (`best_premium`/`worst_premium`/`tp1_filled`/`actions[].stage`) in
`automation/state/core-decisions.jsonl` (safe/bold) and `automation/state/fleet/{safe-3,risky-1}/
decisions.jsonl`, matched by OCC symbol + date.

- Candidate `ribbon_ride` (BEARISH_REJECTION_RIDE_THE_RIBBON + BULLISH_RECLAIM_RIDE_THE_RIBBON)
  round trips, 4 arms, since 08-10: **221**.
- Matched to a tick sequence: **221 / 221** (0 excluded — every trade in window had exit_pass
  coverage).
- **Caveat:** 12/221 trades have <3 logged ticks (thin coverage on very short holds) — MFE/peak
  for these is a lower bound, not necessarily the true intrabar peak.

## 2. Per-trade table

Full 221-row table is in the companion JSON
(`ladder_results.json` in this session's scratchpad) — too large to inline. Columns: arm, date,
entry, peak, MFE%, peak_ts, exit_px, exit_stage, $pnl, rung1_armed_real, tp1_fired,
cf30_pnl, cf40_pnl. The 10 trigger-adjacent (35-50% MFE, closed loss) rows:

| Date | Arm | Entry | Peak | MFE% | Exit | $PnL | Stage |
|---|---|---|---|---|---|---|---|
| 08-12 | risky-1 | 0.92 | 1.29 | 40.2% | 0.82 | -50 | trail |
| 09-01 | bold | 0.43 | 0.62 | 44.2% | 0.15 | -140 | premium_stop |
| 09-02 | safe-3 | 1.11 | 1.52 | 36.9% | 0.95 | -48 | structure_stop |
| 09-02 | safe-3 | 1.03 | 1.52 | 47.6% | 0.81 | -66 | structure_stop |
| 09-02 | risky-1 | 1.11 | 1.52 | 36.9% | 0.95 | -16 | structure_stop |
| 09-02 | risky-1 | 1.11 | 1.52 | 36.9% | 0.95 | -64 | structure_stop |
| 09-02 | risky-1 | 1.03 | 1.52 | 47.6% | 0.82 | -105 | structure_stop |
| 09-15 | safe-3 | 1.12 | 1.61 | 43.7% | 0.74 | -114 | structure_stop |
| 09-15 | risky-1 | 1.13 | 1.58 | 39.8% | 0.74 | -195 | structure_stop |
| 09-15 | safe | 1.08 | 1.57 | 45.4% | 0.73 | -105 | structure_stop |

Note 09-02 and 09-15 are the SAME underlying move logged across multiple arms (shared signal,
per-arm sizing) — 4 distinct real-world moves produce these 10 rows, not 10 independent
occurrences.

## 3. MFE-band distribution (n=221)

| MFE band | n | Σ $pnl |
|---|---|---|
| <20% | 58 | -$5,197 |
| 20–35% | 22 | -$2,228 |
| 35–50% | 11 | -$864 |
| 50–75% | 15 | +$795 |
| >75% | 115 | +$9,001 |
| **Total** | **221** | **+$1,507** |

**Never-armed-real (MFE<50%, n=91):** 86 closed at a loss, totaling **-$8,351**. Exit-stage
breakdown: structure_stop 67, premium_stop 15, ribbon_flip 6, time_stop 2, trail 1 — the
trigger case's failure mode (structure_stop catching an unprotected pre-arm pullback) is the
**dominant** one, not an edge case: 67/91 (74%) of never-armed exits.

**Key stat — 35–50% MFE band, closed at a loss:** 10 of 11 trades. **Give-back (peak value −
exit value) across those 10: $2,422.**

## 4. Counterfactual — lower rung-1 arm (simulation, NOT real fills; C6-respecting: only ticks
≤ the real exit tick are used, and for trades that never armed the counterfactual rung, the
real outcome is left unchanged)

Two variants, same 30% lock, faster arm: **+30% MFE** and **+40% MFE** (current is +50%).
Simulated by tracking the same tick's `best_premium` HWM and firing on `worst_premium ≤ floor`
— the identical mechanism the live `premium_stop`/`profit_lock_floor` stage already uses, so
this is not a more generous fill assumption than the real system gets.

**Methodology correction (fable-too-good caught a real artifact):** a first pass used the
floor price itself as the assumed fill and derived $/point from a single real (exit−entry)
ratio — this produced an unrealistically clean **+$3,228** (30% arm) net swing. Two problems:
(a) using the floor as fill price instead of the tick's actual `worst_premium` is optimistic
(no slippage); (b) the ratio-based $ scaling explodes when a trade's real exit landed near its
entry price (small denominator). Rebuilt using `qty × 100 × (price − entry)` directly (matches
`journal/trades.csv` exactly on the trigger case and 7 other spot-checks) and the tick's
`worst_premium` as the assumed fill. A second, more important issue: `pre_tp1_ladder` is
**PRE-TP1 ONLY** (exit_manager.py comment, explicit) — once TP1 fires, the real position rides
a different, more protective post-TP1 trailing chandelier. The first pass kept applying the
fixed floor to the whole tick history regardless, which either double-protects or mis-charges
87 trades that hit TP1. Fixed by capping the ladder simulation at the real TP1-fill tick.

**Corrected results (n=221):**

| Rung | Real $ | Counterfactual $ | Net Δ |
|---|---|---|---|
| +30% arm / 30% lock | +$1,507 | +$2,931 | **+$1,424** |
| +40% arm / 30% lock | +$1,507 | +$2,774 | **+$1,267** |

Split by whether the trade ever reached real TP1 (+100% MFE):

| Subset | n | Rung | Real $ | CF $ | Net Δ |
|---|---|---|---|---|---|
| Never hit TP1 (the trigger case's class) | 134 | +30% | -$7,354 | -$2,771 | **+$4,583** |
| Never hit TP1 | 134 | +40% | -$7,354 | -$4,674 | **+$2,680** |
| Hit TP1 | 87 | +30% | +$8,861 | +$5,702 | **-$3,159** |
| Hit TP1 | 87 | +40% | +$8,861 | +$7,448 | **-$1,413** |

**The cost side is real, not an artifact:** 40 of 101 (30%-arm) counterfactual early-stops hit
trades that in reality went on to reach TP1's double — a lower rung locks 30% and gets stopped
out on a pullback before the runner ever gets there. That is the genuine trade-off, not a
methodology error (verified: for these trades the sim floor breach tick is always strictly
before the real TP1-fill tick, so it isn't reusing look-ahead information).

**Net verdict on the counterfactual:** modest positive (+$1,267 to +$1,424 over 221 trades,
~6 weeks, ~$6/trade) — NOT free money. It is a transfer: it protects the never-armed/
never-reach-TP1 cohort (the trigger case's class, +$2,680 to +$4,583) at the cost of clipping
some winners that would have doubled (-$1,413 to -$3,159). A 40% arm is a strictly worse
choice than 30% here (lower net on both sides) because it arms slower without changing the
lock level — no reason to prefer 40% over 30% on this evidence.

## 5. Verdict

- **n=221** real-fill `ribbon_ride` round trips under the current ladder config (live since
  2026-08-10), 4 arms, ~5.5 weeks.
- **Not sufficient for a prereg under OP-11 as specified.** OP-11 requires OOS_positive AND
  WF≥0.70 AND sub_window_stable AND anchor_no_regression; n≥15 is advisory only, not the gate.
  This study is a single in-sample backtest-on-logged-ticks with no train/test split, no
  walk-forward, and no out-of-sample holdout — none of the four gates have been run. n=221 is
  comfortably above the advisory floor, but evidence *quantity* was never the blocker here;
  evidence *structure* (OOS split, WF stability) is what's missing.
- **What a prereg would need to state**, minimum:
  1. A held-out OOS window (e.g. ratify on 08-10→08-31, validate on 09-01→09-15, or vice versa)
     showing the same-direction net-positive result, not just full-sample.
  2. Sub-window stability across at least 2-3 sub-periods (the current $+1,424 aggregate hides
     that 09-02 and 09-15 alone contribute 5 of the 10 "trigger-case-class" losses — a couple
     of shared-signal days are doing a lot of the driving).
  3. Anchor-no-regression: does not degrade the >75%-MFE cohort's $9,001 (this cohort is
     untouched by a pre-TP1-only change, but must be re-confirmed, not assumed).
  4. Explicit disclosure of the TP1-cohort cost (-$1,413 to -$3,159) as the mechanism's known
     downside, not just the headline net.
  5. Real-fills validation, not tick-log replay — this study used `best_premium`/
     `worst_premium` from the exit-actuator's own tick log (typically ~1/minute resolution),
     not true continuous bid/ask; a resting stop in reality could fill worse than the logged
     tick low on a fast move. The reconstruction matched the two known real fills to the cent,
     which is reassuring but n=2 is not a slippage-model validation.
- **Fable-too-good disposition:** hunted and found one real artifact (described in §4) which
  cut the apparent gain roughly in half and exposed a real cost-side (-$1.4k to -$3.2k on
  TP1-reaching trades) that the naive version hid entirely. The corrected number
  (+$1,267/+$1,424 net, ~$6/trade) is modest enough to be believable rather than suspicious —
  no further artifact found on inspection of the 5 largest single-trade swings in each
  direction (all traced to legitimate MFE/exit-timing differences, not data errors).
- **This is evidence-gathering only.** No code, config, or state was touched. Config freeze
  through 2026-09-29 stands; this is input for that checkpoint's review, not a ship decision.

---

## Orchestrator reconciliation note (Opus, 2026-09-15)

- Independent FIFO recount from `fills-ledger.jsonl` (same 4 arms, SPY options, date_et ≥ 2026-08-10, all setups):
  **231 closing round trips, realized +$1,047** (safe-3 +950, risky-1 +128, safe-2 −130, bold-2 +99).
  This study's 221 ribbon_ride trades sum to **+$1,507**. The $460 gap is **UNRECONCILED**. Likely
  causes: non-ribbon setups in the ledger count, trades.csv $pnl vs raw FIFO, fees, partial-lot
  pairing. Reconcile before this becomes prereg evidence.
- **Independence:** one signal fires across up to 4 arms, so the effective n is distinct signals, not
  221. The 35–50% loss rows are 4 real moves. Any prereg must count and bootstrap by signal/day.
- Status: **evidence only, NOT prereg-ready** (no OOS split, walk-forward, sub-window or anchor check).
  Trading path frozen until the 2026-09-29 checkpoint.

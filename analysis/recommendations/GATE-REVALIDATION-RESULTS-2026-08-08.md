# Gate Revalidation — 2026-08-08

> J's directive tonight: **"why do we still have gates blocking profitable trades?"** Runs the pre-registered revalidation for the 3 gates [`gate-recency-audit-2026-08-08.md`](gate-recency-audit-2026-08-08.md) ranked most-likely-costing-money. Frozen prereg: [`prereg-gate-revalidation-2026-08-08.json`](prereg-gate-revalidation-2026-08-08.json). Tool: [`backtest/tools/gate_revalidation_ab.py`](../../backtest/tools/gate_revalidation_ab.py). Guards: [`backtest/tests/test_gate_revalidation_ab.py`](../../backtest/tests/test_gate_revalidation_ab.py) (22/22 pass).

## Verdict: NONE of the 3 gates clear the bar. No unblock ships tonight.

All three params keys — `structure_veto_enabled` (Safe), `require_bearish_fill_bar` (Bold), `filter_10_min_triggers_bull` (Safe) — stay exactly as they are. Two fail on substance (not just power). The third's headline number was a mischaracterized population — the proposed unblock affects zero historical ticks.

---

## 1. Soundness audit of the reused instrument (done first, per the mission order)

`automation/state/gate-registry-status.json` (J's own gate-expiry checker, `backtest/autoresearch/gate_expiry_check.py`) is the instrument that originally flagged these 3 gates RED. Its **mining/attribution layer** — `load_decision_rows`, `cluster_events`, `bar_idx_for_ts`, `_stop_level_for_row` — is sound (pure, read-only, no look-ahead in the signal-identification sense) and is **reused verbatim** in this study.

Its **forward-replay layer** — `lib.simulator_real.simulate_trade_real` — is **UNSOUND** for this purpose, on two independently-documented, dated grounds already on file, not a new finding invented for this study:

1. **Exit-shape divergence** (2026-07-17 FRAME AUDIT, `GOAL-REPLAY-TODAY-GREEN.md`): `simulate_trade_real` reads exit knobs from `params.json`'s top-level keys (`tp1_premium_pct=0.5`, `profit_lock_mode="fixed"`), but the REAL exit_manager registration for ribbon_ride entries — both core accounts — reads `automation/state/fleet/strategies.py#RIBBON_RIDE.exit.to_dict()` instead (`tp1_premium_pct=1.0`, trailing chandelier, structure-stop primary). Measured: live ran a real trade to +$241; the sim breakeven-zeroed the same trade in 2 minutes.
2. **Intrabar look-ahead** (2026-07-11, `markdown/research/BACKTESTING-PLAYBOOK.md` §2.12): the sim's profit-lock ratchet reads the *current* bar's high to arm the trail, then checks the *same* bar's low against the just-armed stop — a documented C6 violation worth $46.32/tr on the cited cell, bigger than that cell's own recorded expectancy.

**This means gate-registry-status.json's own P&L verdicts for these gates (structure_veto +$32.69/tr n=11 RED; fill_bar +$22.96/tr n=36 RED) are not trustworthy as-is.** This study replaces `simulate_trade_real` with **`backtest/lib/exit_manager_walk.walk_exit_manager`**, which ticks the *actual* production `exit_manager.plan_exit_actions` core — the same path `prereg-tp1-reachability-2026-08-06.json` and `exit_manager_replay.py` (broker-fill-faithfulness-tested, 2026-07-17) already use, and the one `analysis/recommendations/prereg-tp1-reachability-2026-08-06.json` itself names explicitly: *"NEVER simulator_real (2026-07-09 SIM-EXIT-SHAPE-PARITY scar)."*

A divergence between this study's numbers and gate-registry-status.json's is therefore **expected and is evidence the fix mattered**, not a bug here.

---

## 2. A correction found before touching any P&L (Cell 3)

The audit's rank-1 finding — Safe's `filter_10_min_triggers_bull=2` (vs Bold's 1) "sole-blocked 551 bull ticks/15d... a real trigger existed... refused solely for having only one" — **does not match the ledger.**

Cross-tabulating the audit's own "sole-blocked" population (`bull_blockers == [11]` exactly) against `bull_triggers_raw` (the same local trigger list `filters.py`'s blocker-11 check reads) — a population-structure check, zero P&L touched — found:

- **All 275** of Safe's sole-`[11]` rows (and all 276 of Bold's) carry **zero** real triggers, not one.
- Across the *full* ledger, Safe has exactly **81** rows with 1 real trigger (always `ribbon_flip`, never level-tied) — and **none** of those 81 are sole-blocked by filter 11; every single one also fails a *different*, untouched filter (chiefly filter 10 "buyer pressure", 60/81).
- **Zero** rows anywhere have ≥2 triggers and blocker 11 present.

**Consequence:** relaxing Safe's `filter_10_min_triggers_bull` from 2 to 1 changes the verdict on **zero** historical ticks. The 551-combined "sole-blocked" figure is 0-trigger noise that Bold's own floor of 1 blocks identically; the only real-signal ticks the 2-floor uniquely touches are all separately blocked anyway. Guard: `test_cell3_population_classifier_zero_trigger_excluded` pins this so a future session doesn't regress to the audit's original framing.

---

## 3. Per-cell verdict table

| Cell | Account | n | Window | Mean $/tr | `one_sample_p` | Bootstrap null p | G_mean | G_oos | G_drop3 | G_bhfdr | G_n | **Verdict** |
|---|---|---:|---|---:|---:|---:|:-:|:-:|:-:|:-:|:-:|---|
| 1. `structure_veto_enabled` | Safe | 11 | 06-26 → 08-07 | +$6.00 | 0.885 | 0.543 | PASS | FAIL | FAIL | FAIL | FAIL | **NOT-UNBLOCK-ELIGIBLE** |
| 2. `require_bearish_fill_bar` | Bold | 38 | 06-25 → 08-07 | +$47.37 | 0.468 | 0.152 | PASS | PASS | FAIL | FAIL | PASS | **NOT-UNBLOCK-ELIGIBLE** |
| 3. `filter_10_min_triggers_bull` | Safe | 0 | 06-25 → 08-07 | n/a | 1.0 (by construction) | n/a | FAIL | FAIL | FAIL | FAIL | FAIL | **NOT-UNBLOCK-ELIGIBLE (STRUCTURAL-NULL)** |

BH-FDR run at q=0.10 across the full 3-cell family (`p = [0.885, 0.468, 1.0]`) — none survive.

### Why each one fails, in one sentence

- **Cell 1** — thin (n=11) *and* substantively fails: the OOS half is negative (-$4.00/tr), and dropping just the 3 biggest wins flips the whole cohort from +$66 to **-$447** — the positive mean is a few lucky trades, not an edge. The random-entry bootstrap (side-matched Calls/Puts, same window) beat this cohort's mean in 54% of draws — statistically indistinguishable from buying at random moments.
- **Cell 2** — decent n=38, positive mean, positive OOS half — but drop-top-3 is **-$1,363.60** against a **+$1,800** raw total: one single trade (`+$1,476.40`, a 140-minute runner) is nearly the entire cohort's edge. `one_sample_p=0.468` — nowhere near significant even before the BH correction. This reads as "got saved by one big runner," not a repeatable edge from unblocking the gate.
- **Cell 3** — mechanically empty population (see §2). No gate in the battery can pass n=0.

Full per-trade ledgers (dates, strikes, entry premiums, exit reasons, hold times) are in each cell's own scorecard JSON.

---

## 4. Params diffs (disclosed per the mission's ask — none recommended)

| Key | Current | Proposed (if flipped anyway) | Recommendation |
|---|---|---|---|
| `structure_veto_enabled` (safe) | `true` | `false` | **DO NOT FLIP** — fails G_oos/G_drop3/G_bhfdr/G_n |
| `require_bearish_fill_bar` (bold, aggressive/params.json) | `true` | `false` | **DO NOT FLIP** — fails G_drop3/G_bhfdr (concentration + not significant) |
| `filter_10_min_triggers_bull` (safe) | `2` | `1` | **NOT RECOMMENDED** — affects 0 historical ticks either way |

Kill criteria and guard-test snippets (pinning each current value so a future accidental flip is caught in CI) are embedded in each cell's own JSON scorecard (`kill_criterion` / `guard_test_snippet` fields).

---

## 5. Method notes

- **Entry convention**: the refused tick's own decision-moment SPY bar (located via `bar_idx_for_ts`, gate_expiry_check.py's own convention) is the signal bar; the fill is sourced from the option contract's own 5-min bar at-or-after the signal bar's close + 5min (`bar_at_or_after`) — the same "next bar's open after the trigger bar" convention `simulator_real.py`/`option_pricing_real.py` document. `walk_exit_manager`'s own strict `>` entry-bar exclusion (pinned by `test_exit_manager_walk_entry_bar_convention.py`, ruling 2026-07-25) then manages exits from the bar strictly after that fill bar.
- **Exit shape**: read live from `automation/state/fleet/strategies.py#RIBBON_RIDE.exit.to_dict()` at run time (not a hardcoded copy) — confirmed both core accounts register this exact shared shape with an empty arm-level patch.
- **Bootstrap null**: side-matched random-entry Monte Carlo (B=150 draws, RNG seed 20260808, disclosed), universe = every RTH 5-min bar 09:35–15:00 ET in the cell's own window. Answers a *different* question than `one_sample_p`: "is this cohort distinguishable from buying the same side at random moments in the same market regime?" — not folded into BH-FDR, reported alongside it.
- **Known limitation carried from the original instrument**: neither this study nor gate-registry-status.json re-verifies whether a refused tick would *also* have been blocked by a different, un-relaxed gate positioned later in `GATE_ORDER` (which short-circuits at the first failing gate, so downstream gates were never evaluated for a refused tick). Flagged, not solved, here.

---

## 6. Files

- Prereg: `analysis/recommendations/prereg-gate-revalidation-2026-08-08.json`
- Scorecards: `analysis/recommendations/gate-revalidation-{structure_veto,bearish_fill_bar,min_triggers_bull}-2026-08-08.json`
- Tool: `backtest/tools/gate_revalidation_ab.py`
- Guards: `backtest/tests/test_gate_revalidation_ab.py` (22 passed)

---

## Executive digest (5 lines)

1. **No gate ships unblocked tonight.** All 3 cells fail the pre-registered G-battery — 2 substantively (concentration risk / no OOS edge / not significant), 1 mechanically (empty population).
2. **The instrument that flagged these gates RED (`gate-registry-status.json`) uses a replay engine (`simulate_trade_real`) with two independently-documented, dated defects** (exit-shape divergence 2026-07-17, intrabar look-ahead 2026-07-11) — this study swapped in the sound production-exit-core replay (`exit_manager_walk`) and got materially different numbers, as expected.
3. **`structure_veto_enabled` (Safe):** sound replay gives +$6.00/tr n=11 (not the flagged +$32.69/tr) — negative OOS half, drop-top-3 goes to -$447. Not an edge.
4. **`require_bearish_fill_bar` (Bold):** +$47.37/tr n=38 (not +$22.96/tr) but one trade carries the whole cohort (drop-top-3 = -$1,363.60 vs +$1,800 raw) and p=0.468. Got saved by a runner, not a repeatable edge.
5. **`filter_10_min_triggers_bull` (Safe):** the audit's "551 sole-blocked bull ticks" claim was a mischaracterization — they're 100% zero-trigger noise; relaxing Safe's threshold to match Bold's would change zero historical outcomes. Corrected and guarded (`test_cell3_population_classifier_zero_trigger_excluded`) so this doesn't resurface as a false lead.

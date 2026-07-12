# Participation Opportunity-Cost — Deep Research Stream 2/5

**Date:** 2026-07-11 · **Scope:** read-only research, no param/order changes · **Window:** 10 trading sessions, 2026-06-29 → 2026-07-10 (2026-07-03 is IDLE, no signals at all; 9 active sessions)

**Instruments reused (per instruction, not rebuilt):** `backtest/tools/participation_cascade.py` (joint gate funnel, commit `580561b`-current), `setup/scripts/free_model_audit_heartbeat_veto.py`'s counterfactual-replay pattern (`exit_shape_parity_study.fetch_option_bars` + `.replay_position` + `strike_selection.pick_strike`), `backtest/autoresearch/probe_stats.py`'s documented slippage-haircut convention (`REALISTIC_SLIPPAGE_HALF_SPREAD=0.05`, `2×half_spread×100×qty`). Two small aggregation scripts were written to the session scratchpad (not the repo) to pool `participation_cascade`'s per-day output across 10 sessions and to run the haircut-adjusted replay on the one gate that needed fresh evidence — both call existing library functions, neither reimplements gate/exit logic.

---

## VERDICT

**The "sat out on a $7 trend day" story is mostly explained by things that are either already correctly protective or already someone else's open item — not by an accidental gate that just needs relaxing.** Of 238 pooled blocker-events over 10 sessions, 54.7% (58 min-premium-floor + 57 block_elite_bull + 51 not-flat/Rule-4 + 5 PDT + 10 entry-floor/ceiling) are either under separate active investigation, already rigorously revalidated as protective, or hard regulatory/J-doctrine that cannot be relaxed. The **single best-evidenced open candidate is `block_bull_1100_1200`** (Safe-only, thin n=11 IS/n=1 OOS provenance, a self-flagged caveat that predicted exactly the 07-10 failure mode) — but my own fresh counterfactual replay of the *only* live block in the window nets **-$157.20** (haircut-adjusted), i.e. **new evidence leans KEEP, not relax**. The correct move — running a forward probe instead of flipping the gate on n=2 — is already what the codebase decided to do (`risky-3` probe arm, shipped 2026-07-10). **But that probe is wired to the wrong account's ledger and will never fire** (see §4) — this is the highest-leverage, most time-sensitive finding in this report, independent of the gate-ranking question itself.

---

## 1. The joint gate funnel (10 sessions, pooled, 6 arms)

| date | passed_scoring | orders | joint participation | SPY range | verdict |
|---|---|---|---|---|---|
| 2026-06-29 | 6 | 4 | 66.7% | 1.236% | OK |
| 2026-06-30 | 46 | 20 | 43.5% | 0.962% | OK |
| 2026-07-01 | 18 | 4 | 22.2% | 0.948% | OK |
| 2026-07-02 | 44 | 14 | 31.8% | 1.509% | OK |
| 2026-07-03 | 0 | 0 | n/a | n/a | IDLE |
| 2026-07-06 | 42 | 21 | 50.0% | 0.668% | OK |
| 2026-07-07 | 30 | 6 | 20.0% | 0.766% | OK |
| 2026-07-08 | 31 | 14 | 45.2% | 0.892% | OK |
| 2026-07-09 | 82 | 10 | 12.2% | 0.854% | OK |
| 2026-07-10 | 32 | 0 | **0.0%** | 0.973% | **PARTICIPATION_HOLE** |
| **pooled** | **331** | **93** | **28.1%** | — | — |

07-10 is the only `PARTICIPATION_HOLE` day in the window (≥3 passed-scoring events, 0 orders, SPY range ≥0.8% floor). 07-09's 12.2% is the next-worst live day (82 passed-scoring events, only 10 orders) — worth flagging as a second data point, not a one-off.

### Attribution note: first-blocker only, joint attribution mostly unmeasurable

`participation_cascade.py` classifies each signal event to the **one terminal stage** the production ledger actually recorded. This is a structural property of the engine, not a limitation of the tool: `gates.py::evaluate_gates()` is a **first-fail cascade** — "Evaluate the 15 entry gates in `GATE_ORDER`; return the first SKIP" (its own docstring) — so a signal that dies at gate #3 never reaches gates #4-15, and the ledger has no record of whether it *would* have also failed them. Reconstructing true "died at 3 gates simultaneously" counts would require re-running every downstream gate's predicate against every blocked context regardless of order — a different, heavier computation this stream did not build (per instruction to reuse, not rebuild). **Reporting this as unmeasured rather than guessing**, per the task's honesty rail.

One case *is* directly verifiable by inspection: the two `block_bull_1100_1200` events (07-10) are clean single-gate blocks — `bull_score=11/11` (max), all three triggers fired (`level_reclaim`, `ribbon_flip`, `confluence`), `reason` carries exactly one gate name, no other blocker in contention at that tick. For this specific gate, joint-attribution depth is confirmed = **1** (only this gate needs to move for the signal to trade).

### Pooled blocker leaderboard (238 blocker-events = 331 passed − 93 orders, verified to balance exactly)

| rank | blocker | category | 10-day events | tiers hit |
|---|---|---|---|---|
| 1 | `min_premium_floor` | risk_gate | 58 | ELITE, SUPER |
| 2 | `block_elite_bull` | gate (tier/cohort) | 57 | — |
| 3 | `not_flat_rule4` | risk_gate | 51 | BASE, ELITE, SUPER, TRENDLINE |
| 4 | `arm_selectivity_gate` | gate | 20 | BASE |
| 5 | `require_bearish_fill_bar` | gate | 12 | — |
| 6 | `structure_veto` | veto | 9 | — |
| 7 | `entry_ceiling_15:00` | window | 6 | ELITE, SUPER, TRENDLINE |
| 8 | `risk_deny_pdt` | risk_gate | 5 | ELITE, SUPER, TRENDLINE |
| 9 | `broker_reject` | execution | 4 | BASE, TRENDLINE |
| 9 | `entry_floor_09:35` | window | 4 | ELITE |
| 11 | `block_conf_lvl_rec_afternoon` | window | 3 | — |
| 11 | `min_ribbon_momentum_cents` | gate | 3 | — |
| 13 | `quality_lock` | risk_gate | 2 | TRENDLINE |
| 13 | `block_bull_1100_1200` | window | 2 | — |
| 15 | `entry_bar_body_pct_min` | gate | 1 | — |
| 15 | `stale_trigger_bar` | execution | 1 | SUPER |

---

## 2. Per-gate blocked-value + provenance grade

Grade key: **A** = fresh (<2wk), multi-window OOS, honest caveats resolved. **B** = ratified, OOS-positive, some staleness. **C** = thin n, single-trade-driven, self-flagged caveats. **D** = doc contradicts itself or evidence traced to a misattributed/reversed source.

| Gate | Events | Blocked-winners $ | Protected-losers $ | NET | Grade | Disposition |
|---|---|---|---|---|---|---|
| `min_premium_floor` | 58 | **UNMEASURED** | **UNMEASURED** | **UNMEASURED** | n/a | **Excluded from ranking** — task_492a699b may be investigating this concurrently in another session; read-only, deferred, not this stream's call. Raw count reported for completeness only. |
| `block_elite_bull` | 57 | (in the -$3,873.60 total) | (in the -$3,873.60 total) | **-$3,873.60** (SS-B) / -$560.00 (OLD), n=28, both negative | — | **Excluded — SETTLED.** Hash-pinned SS-B revalidation (`analysis/recommendations/block-elite-bull-ssb-revalidation.json`, 2026-07-10) proved the blocked cohort is net-losing under BOTH the old and current exit shapes (SS-B is ~6.9× worse). Gate is net **protective**. Per instructions, not re-litigated. |
| `not_flat_rule4` | 51 | N/A | N/A | N/A — not a P&L question | — | Hard Rule 4 (no adding without a new trigger / one-position invariant). 2026-07-02 audit: "working as intended: position was genuinely open." Never relax. |
| `arm_selectivity_gate` | 20 | not evaluated | not evaluated | not evaluated | — | This *is* the deliberate tight/base/loose `min_triggers` experiment (accounts.json grid), not an accidental gate. Not a candidate. |
| `require_bearish_fill_bar` | 12 | mixed: 3 blocked bear signals on 07-02 would have won (SPY 60m: -2.10/-2.34/-2.32) | but 3 other instances the SAME week were correctly-saved losses (+2.50, +2.62, +2.74) | scorecard net positive (OOS +$1,153, WF 18.5) | **B** | KEEP-leaning on its own evidence. Bold-only; **fleet_executor.py never enforces `GATE_ORDER` gates at all** (confirmed: zero references to `evaluate_gates`/`GATE_ORDER` in fleet code), so the 2026-07-02 audit's "relax for risky arms" recommendation is **moot** — there is nothing to relax on a lane that never enforced it. |
| `structure_veto` | 9 | thin | thin | IS +$583 / OOS $0 | **C** | Already tracked as `F2-STRUCTURE-VETO-PROVENANCE` in `automation/overnight/queue.md` (status: `todo`). Not re-litigated here to avoid duplicate work — flagged, not re-solved. |
| `entry_ceiling_15:00` / `entry_floor_09:35` | 10 | N/A | N/A | N/A | — | Hard J doctrine (v15.1 theta protection). Every census: "KEEP — doctrine-mechanical." Never relax. |
| `risk_deny_pdt` | 5 | N/A | N/A | N/A | — | Federal PDT regulation (Rule 7). Not a tunable gate. |
| `broker_reject` | 4 | n/a | n/a | n/a | — | Execution/infra failure, not a selectivity gate. |
| `block_conf_lvl_rec_afternoon` | 3 | ~$0 | ~$0 | ~$0 | **D** | **Proven mostly-phantom.** GATE-PROVENANCE-SWEEP-2026-07-10 caught all 5 raw 07-10 Bold fires as a 36-hour-old stale bar echo (cross-account-verified against Safe's `SKIP_STALE_TRIGGER` at the identical tick), and its own doc-string self-contradicts ("KEPT but DEAD... superseded by [a gate removed the same day]"). Root cause (gate-evaluation runs before the stale-trigger-bar guard) was **fixed in production 2026-07-10 19:14 ET, commit `873281a`**; `participation_cascade.py` got the matching mirror fix 2026-07-11 (`580561b`). Verified directly: the raw 07-10 09:31-09:35 Bold rows still carry the pre-fix shape (`trigger_bar_et: None`, `action: SKIP_CONF_LVL_REC_AFTERNOON`) because they were logged *before* the fix landed that evening — expected, not a live re-check failure. Residual forward value ≈ $0; this is a closed item, not a candidate. |
| `min_ribbon_momentum_cents` | 3 | n/a | n/a | n/a | — | Confirmed bug (0 treated as "armed" instead of "off"). **Already fixed 2026-07-08**, closed 2026-07-11 per `queue.md` F1. Zero fires after 07-07 in this window, consistent with the fix. |
| `quality_lock` | 2 | n/a | n/a | n/a | — | J ordered this **deleted** 2026-07-02 ("Gone. We no longer have it in our codebase" — commit `1bad42f`). The 2 events in this window are both same-day 07-02, before the deletion landed that evening; zero recurrence since. Closed. |
| **`block_bull_1100_1200`** | **2** | **+$19.80** (net, 1 winner) | **-$177.00** (net, 1 loser) | **-$157.20** | **C** | **See §3 — the open candidate.** |
| `entry_bar_body_pct_min` | 1 | not evaluated | not evaluated | not evaluated | — | n=1 in-window, too thin to prioritize this pass. |
| `stale_trigger_bar` | 1 | n/a | n/a | n/a | — | Data-freshness artifact, not a selectivity gate. |

---

## 3. The one best-evidenced candidate: `block_bull_1100_1200`

**Why this gate, not another:** it is the only REVALIDATE-tagged gate in the entire 10-session window with (a) a **confirmed-live** fire (not a phantom/stale-bar artifact — cross-checked directly against the raw ledger, unlike item §2's `block_conf_lvl_rec_afternoon`), (b) genuinely thin provenance, and (c) not already settled, not already fixed, and not someone else's open item.

**Provenance (`analysis/recommendations/safe_bull_1100_1200_gate.json`, ratified 2026-06-18):**
- IS: n=11 blocked, WR 9.1% (**one** winner of eleven, +$198 on 2026-01-09, single-handedly making the IS delta positive: without it the cohort is 10-for-10 losers).
- OOS: n=**1** blocked (-$42). WF = 5.22 — computed as a ratio of two thin numbers (1 OOS trade over 11 IS trades); not a statistically meaningful walk-forward by the standard this codebase applies elsewhere.
- G4 sub-window check: one of three sub-windows shows the gate **hurting** (delta -$96), right at the "SW_hurt ≤ 1" ceiling — passes, but with zero margin.
- The scorecard's own caveats section: *"Gate is broad — blocks ALL bull entries 11-12, not just bad combos. Any future high-conviction 11:XX bull SUPER trade would also be blocked."* — written 2026-06-18, and it is exactly what happened on 2026-07-10.
- Pre-dates the SS-B exit-shape change entirely (ratified the same day chart-stop-primary shipped — its own IS/OOS split likely straddles an exit-shape transition, per the 2026-07-10 sweep).

**What happened live (07-10, Safe account, confirmed via direct ledger read):**
- 11:21:03 ET, SPY 752.67, `bull_score=11/11`, triggers `[level_reclaim, ribbon_flip, confluence]` (SUPER tier — the gate's own caveat scenario).
- 11:31:04 ET, SPY 753.23, identical shape, second cluster.
- Both are genuinely live (not the stale-bar artifact that contaminated the neighboring `block_conf_lvl_rec_afternoon` fires the same morning).

**Fresh counterfactual replay (this session, new evidence — not in any prior audit):**

Reused `exit_shape_parity_study.fetch_option_bars` (real Alpaca OPRA 1-min bars) + `.replay_position` (the actual live `exit_manager.plan_exit_actions` decision core) + `strike_selection.pick_strike` (Safe ATM tier at ~$1.5K equity → strike 753 both times), under the `v15_3_safe_ratified` shape (`-50%` cat cap / `+30%` TP1 / sell 80%) — the same shape `free_model_audit_heartbeat_veto.py` uses for this exact class of never-filled-signal replay. Haircut: codebase-standard round-trip half-spread (`probe_stats.REALISTIC_SLIPPAGE_HALF_SPREAD=0.05`, 3 contracts → $30/trade).

| Event | Entry (proxy) | Exit | Gross P&L | Net of haircut |
|---|---|---|---|---|
| 11:21 ET, SPY 752.67 | $0.83 | TP1 hit @ $1.079 (2 ctr), be-stop @ $0.83 (1 ctr) | +$49.80 | **+$19.80** |
| 11:31 ET, SPY 753.23 | $0.98 | -50% catastrophe stop @ $0.49 (3 ctr) | -$147.00 | **-$177.00** |
| **Combined (n=2)** | | | -$97.20 | **-$157.20** |

**Honest read:** this does **not** make the case to relax the gate. It reproduces the gate's own historical shape almost exactly — one modest winner, one larger loser, net negative — on the first fresh out-of-sample pair since ratification. n=2 is nowhere near enough to close the loop either way (this is precisely the kind of anchor-trade overfitting C24/`fable-too-good` discipline warns against), but if anything this new data point argues for **patience, not a flip**. The correct doctrine move — collect more forward evidence at minimum size before deciding — is exactly what the codebase already tried to build. See §4.

---

## 4. CRITICAL: the forward-evidence mechanism (probe arm) is wired to a dead source

The `risky-3` probe arm (`automation/state/fleet/accounts.json` top-level `probe_arm` block, shipped 2026-07-10, `enabled: true`) exists specifically to gather live forward evidence on exactly this gate: `build_shared_signal.PROBE_ALLOWED_VERDICTS = frozenset({"SKIP_BULL_1100_1200"})` — narrowed to this one gate, on purpose, by the same 2026-07-10 gate-provenance sweep that produced §3's provenance case.

**It cannot fire, as currently wired.** Verified via three independent, cross-checking facts:

1. `_probe_passed_blocks()` (`build_shared_signal.py:659`) reads off the **Bold** ledger (`_latest_today_decision(today, account="bold")`) — the code comment says it deliberately "mirrors `_bold_passed_blocks`' shape + the SAME BOLD-ledger source."
2. `block_bull_1100_1200` is **Safe-only**. Confirmed by direct grep: the key exists in `automation/state/params.json:188` (`true`) and is **absent** from `automation/state/aggressive/params.json` (zero matches). Every gate-provenance audit in this repo (2026-07-02, 2026-07-09, 2026-07-10) independently confirms "Bold: absent."
3. Confirmed empirically across the **entire ledger history**, not just the 10-day window: `automation/state/core-decisions.jsonl` has 4,342 `account=="bold"` rows, and **zero** of them contain `BULL_1100_1200` anywhere in `action` or `verdict`. Bold structurally cannot produce the one action string the probe's allowlist (`passed_probe_cohort`) checks for.

Consistent with this: `automation/state/fleet/risky-3/decisions.jsonl` has **zero** `PROBE_ARM`-tagged rows, and `automation/state/fleet/risky-3/probe-count.json` (created only on the probe's first real fire) **does not exist yet**. Today (2026-07-11) is a Saturday — markets have not been open since the probe shipped Friday evening, so "hasn't fired yet" is ambiguous between "hasn't had a chance" and "structurally can't" from ledger silence alone. **The code read removes the ambiguity: it can't, regardless of how many Mondays pass**, unless either `block_bull_1100_1200` gets armed on Bold too (no evidence anyone intended that — it would change what's being tested) or the probe's ledger source is repointed to Safe for this specific allowlisted verdict.

This is a one-account-string wiring mismatch, not a design flaw in the probe concept — the mechanism, allowlist, and safety floors (`min_entry_premium`/kill-switch/PDT/entry-window all still enforced downstream, untouched) are otherwise sound. Flagged as a background task (see below) rather than fixed here, per this stream's read-only mandate.

---

## 5. What this means for Monday (2026-07-13, next trading session)

- **Do not relax `block_bull_1100_1200`.** Thin historical evidence plus one net-negative fresh data point is not a case to flip a gate that was correctly identified as risky enough to probe rather than judge.
- **The probe wiring bug should be fixed before Monday**, or the next several trading days' worth of exactly the evidence this whole exercise wants will silently not be collected — a repeat of the "visibility gap" pattern (OP-33) this codebase has hit before. Flagged via `spawn_task` (see below), not fixed in this read-only pass.
- **`min_premium_floor` (58 events, the single largest blocker in the window) and `block_elite_bull` (57 events, settled) are correctly out of scope for this stream** — together they're over a third of all blocked participation, and neither needs a new decision from this research pass.
- **The deeper pattern worth naming:** in this 10-day sample, most of the "gate churn" is already self-correcting on a multi-day cycle (`min_ribbon_momentum_cents` fixed 07-08, `quality_lock` deleted 07-02, `block_conf_lvl_rec_afternoon`'s root cause fixed 07-10) — the participation-cost problem is less "static bad gates" and more "a system that's actively being debugged in near-real-time, with one open thin-evidence gate (`block_bull_1100_1200`) and one broken forward-evidence collector (the probe) at the center of what's left."

---

## Appendix: honesty-rail disclosures

- Counterfactual P&L in §3 uses an **entry-price proxy** (first post-tick 1-min bar open, not a real bid/ask) and a **documented haircut** (codebase-standard $30/trade round-trip half-spread @ 3 contracts) — both flagged inline, not hidden. This is a reasonable-but-not-exact reconstruction, same disclosed limitation `free_model_audit_heartbeat_veto.py` carries for the same technique.
- `min_premium_floor` blocked-value is explicitly reported **UNMEASURED**, not guessed, because it may be under separate active investigation (task_492a699b) this stream was told not to touch.
- Joint (multi-gate-simultaneous) attribution is **not generally measurable** from this ledger, because production gate evaluation is a first-fail cascade (see §1) — reported as a structural limitation, not silently worked around.
- No files outside this report were modified. Two throwaway aggregation/replay scripts were written to the session scratchpad only (never the repo) and are not part of this deliverable.

# Dormant-Asset Inventory — 2026-07-11

**Research stream 5/5 (profitability deep-research).** Everything in the repo that is
validated or near-validated but NOT currently trading, ranked by closeness-to-armable,
each with its single blocking step. **Read-only** — no arming, no param changes, no orders.

**Method:** every claim below is sourced from a dated artifact (file path quoted). Where a
memory/docstring claim (mine or a prior session's) contradicted the artifact, **the artifact
wins** — flagged explicitly in each section. Today = 2026-07-11 (Saturday, market closed).

---

## HEADLINE CROSS-CUTTING FINDING: queue.md ticket status is not trustworthy

Three separate tickets in `automation/overnight/queue.md` show `status:pending` or
`status:blocked-on-J` for work that dated artifacts prove is **already done, with a
verdict**:

| Ticket (queue.md) | queue.md says | Artifact says |
|---|---|---|
| `T-STOPA-ENTRY-EXIT-MATRIX` (line 536) | `status:blocked-on-J` | **SIGNED** 2026-07-09 ~00:35 ET, conditions attached (`markdown/planning/STOP-A-ENTRY-EXIT-MATRIX.md` lines 107-133) |
| `T-W7C-GRIND-VERIFY-THEN-STOPB` (line 582) | `status:pending` | Its own action item (regenerate `mass_grind_phase5`) **completed** 2026-07-10 03:48 ET — 106 P5 survivors written (`analysis/recommendations/mass-grind-phase5-summary.json`) |
| `T-W8-HEADROOM-RETEST-CANDIDATES` (line 583) | `status:pending`, `depends:T-W7C` | **RAN** 2026-07-09T11:28 ET, full verdict tally 0 PASS / 10 FAIL / 2 INCONCLUSIVE (`analysis/recommendations/headroom-retest-tw8.json`) |

None of these are hidden — the dated result files sit right next to the stale tickets. But
anyone (human or session) trusting `queue.md`'s `status:` field alone would materially
misjudge what's done. This is itself an OP-33(e) missing-instrument: **the queue's status
field needs a periodic reconciliation pass against `analysis/recommendations/*.json` mtimes**,
or it should be treated as a TODO list, never a completion ledger. Not fixed here (read-only
mandate) — flagged for a follow-up task.

---

## 1. Mass-grind P5 survivors (106 cells)

**Evidence state:** `analysis/recommendations/mass-grind-phase5-summary.json` (generated
2026-07-10T01:47:52, confirmed complete via `automation/state/logs/phase5-final-2026-07-10.log`
and `automation/overnight/STATUS.md` line 38): grind 7,560/7,560 → funnel 1,081/1,081 → **582
P4 elites → 106 P5 survivors** (P5 = P4 AND qpf==1.0 [positive every calendar quarter] AND
≥50% of parameter-neighbors also P4-elite — a plateau test against multiple-testing luck,
`backtest/autoresearch/mass_grind_phase5.py` lines 1-21).

**All 106 survivors are variations on ONE core shape**, verified by reading every row
(`python` pass over the jsonl, not just the summary's top-16): strike ∈ {OTM-1, ATM, OTM-2},
**stop ∈ {-8%, -12%} only** (nothing wider survives P5), trailing 0.15, varying only
TP1-level/sell-fraction/time-stop. Top cell: `OTM-1:LR0:mt1:stop-8:tp+30%:sell50%:trailing0.15:ts10`
— expectancy **$34.32/tr**, edge_over_null **$33.40**, edge_capture **$1,816.22**, qpf 1.0,
5/5 neighbors also elite (a real plateau, not an isolated spike).

**This directly matters because the currently-LIVE `ribbon_ride` shape is the opposite
direction and a documented loser.** `automation/state/fleet/strategies.py` line 103-111:
live shape = `premium_stop_pct=-0.20, tp1_premium_pct=1.0` with a code comment stating it
**"-$893 on our own fills"** and is kept only as the structure-stop (SS-B) fallback. The P5
grind's own top cell (tight -8% stop) independently corroborates the entry-exit-matrix's
finding (§2 below) that WIDE stops lose in the current regime — two independent evidence
sources now agree on stop direction.

**Caveat that must be resolved before trusting the number:** `mass_grind`'s `trailing`
axis sweeps `simulate_trade_real`'s SIM semantics (pre-TP1 whole-position profit-lock arm),
which does **not** match live `exit_manager`'s default `post_tp1` arm scope
(`markdown/planning/HANDOFF-2026-07-11-CONFIRM-AND-WIRE.md` "REVIEW DISCOVERY 5" appendix,
lines 200-231: "the fresh P5 universe is therefore RANKING-ONLY on the lock/trail axis; any
lock/trail candidate that reaches T5 confirms via the exit_manager replay"). This backtest
number is *ranking evidence*, not yet a live-equivalent number.

**Single blocking step:** run the SAME confirmatory replay `t5_confirmatory_matrix.py` already
used for T-W7 (see §2) against the top 3-5 P5 cells — fresh-slice replay + real-fills anchor,
explicitly declaring `profit_lock_arm_scope`. The morning brief itself names this as
still-owed ("survivor-neighborhood read + too-good audit + promote-pipeline consumption" —
`automation/overnight/STATUS.md` line 38) but **no such script exists yet** for phase5
specifically (verified: no `too_good_audit.py` / `survivor_neighborhood*.py` in the repo) —
it needs writing, though it can reuse `t5_confirmatory_matrix.py` and
`exit_shape_parity_study.py` almost unchanged. Separately, `STRATEGY-SPACE-REGISTRY.jsonl`
already has fresh funnel-v2 entries with `tested_at: 2026-07-10` and a live-realizability
haircut (`live_real_exp`/`live_admit_pct` via `cap_admission.py`) for lower-tier P3/P4 cells
— but `promote_keeper.py` reads `contender-rank-*.json` (newest on disk: 2026-07-01, **10
days stale**, predates this entire grind) — the registry-to-contender-rank bridge for the
new data hasn't run.

**Effort:** LOW-MEDIUM, ~3-6 hours. Tooling (`t5_confirmatory_matrix.py`,
`exit_shape_parity_study.py`, `cap_admission.py`) already exists and was proven on
2026-07-09; this is "point it at new candidates," not "build new infrastructure."

**Expected value if it clears:** the top cell's own backtest is edge_capture $1,816.22 /
expectancy $34.32 vs the live incumbent's real-fills-anchored **-$757 to -$893** (79 real
fleet positions, `analysis/recommendations/entry-exit-matrix-2026-07-09.json` line 76) — if
even partially confirmed, this is the single largest $ swing of anything in this sweep.

**What would kill it:** a fresh-slice replay (T-W7's own methodology) showing the same
regime-fragility pattern exit-A/B showed — tight stops can also fail if the fresh window's
specific price action doesn't recover before a -8% stop, though a TIGHT stop is mechanically
less exposed to this than the WIDE stops that failed. Also: if the live-semantics
`post_tp1` profit-lock scope (not the sim's `full` pre-TP1 scope) materially changes the P&L,
the backtest number doesn't transfer.

---

## 2. Entry-exit matrix (STOP-A / T-W7 / exit-C+entry-2)

**Evidence state — this whole item is FURTHER ALONG than the task brief's memory assumed.**
The brief cited "T5/T6 blocked on STOP-A sign-off." Artifact correction:

1. **STOP-A was SIGNED** 2026-07-09 ~00:35 ET by Fable, with 4 conditions
   (`markdown/planning/STOP-A-ENTRY-EXIT-MATRIX.md` lines 107-133).
2. **T-W7 layers (a)+(b) RAN** 2026-07-09, producing
   `analysis/recommendations/entry-exit-matrix-2026-07-09.{json,md}`. Verdict table (n=18
   fresh-slice signals, n=79 real-fills anchor / 17 unique signals):

   | candidate | fresh-slice (layer a) | real-fills anchor (layer b) | verdict |
   |---|---|---|:--:|
   | exit-A (-50/+150/sell66/trail15) | exp **-$272.54** (control -$100.67) | +$1,500.9 vs ctl -$757.1 | **FAIL** |
   | exit-B (per-band stop) | exp **-$253.57** | +$2,047.0 vs ctl -$757.1 | **FAIL** |
   | exit-C+entry-2 (paired, floor $0.30) | exp **-$14.73** (best of the 5, still negative) | N/A — entry-2 is shadow-only | **INCONCLUSIVE_NO_ANCHOR** |
   | entry-1 (floor $0.30) + control | exp -$173.82 | -$72.5 vs ctl -$757.1 | **FAIL** (n=11 artifact — floor excluded the slice's only winner) |
   | entry-1 + exit-A | exp -$434.55 | +$2,820.6 vs ctl -$757.1 | **FAIL** |

   The anchor and the fresh-slice **disagree** for the wide-stop candidates (anchor says
   they'd have rescued the real week; the fresh slice says they lose 2.5x more because none
   of the 18 fresh signals recovered before a wide stop). Per the pre-registration's own
   design, a failing confirmatory layer kills regardless of anchor strength — this is a
   designed kill, not a coin-flip.

3. **STOP-B disposition ALREADY MADE** 2026-07-09 ~01:25 ET
   (`analysis/recommendations/entry-exit-matrix-2026-07-09.md` lines 94-131): exit-A,
   exit-B, entry-1+exit-A **KILLED**. **SHIPPED**: entry-1 premium floor $0.30 (engine-wide,
   both lanes) and the vwap_continuation full validated core-cell port (this closed the
   separate T-W6 two-lane discrepancy — verified live in `strategies.py` line 122: the fleet
   shape now reads `-0.06/+0.40/frac 0.8/PL fixed`, matching the disposition). **STAYS
   SHADOW**: exit-C+entry-2 — the one candidate that beat control on the fresh slice, but
   has no live anchor and entry-2 (a new order state machine) can't arm overnight per
   sign-off condition 3.

**Is the remaining block (exit-C+entry-2 graduation) still justified now that SS-B shipped?**
Yes, for a reason the brief's framing didn't anticipate: **SS-B (structure-stop) and the
entry-exit-matrix are not competing — SS-B's own code says the entry-exit-matrix's
territory is its FALLBACK.** `strategies.py` line 109-111: `premium_stop_pct=-0.20` is
explicitly commented **"the flag-OFF emergency fallback"**, and the SS-B ship notes
(`automation/overnight/STATUS.md` line 101) disclose structure-stop "fail[s] OPEN to premium
mode" for ~22-39% of positions (no nearby level to anchor to). So a better premium-mode
shape still has direct, un-mooted value for that fallback path. **What's actually left
blocking exit-C+entry-2** is not STOP-A/B sign-off (done) — it's that **entry-2 has never
taken a real fill** (shadow-only, per condition 3), so there is no anchor to confirm it with.
This is the exact same gap as item 7 (`entry_manager` graduation) — **these are the same
blocker, not two independent ones.** See §7.

**Single blocking step:** graduate `entry_manager` from shadow to a real-fill-producing
context (crypto twin per TWIN-B3, or a direct SPY shadow-to-paper-arm decision) — then
exit-C+entry-2 gets its layer-(b) anchor and can re-enter the T5/T6 pipeline.

**Effort:** the analysis itself is DONE (0 further hours). The blocking step's effort is
counted under item 7.

**Expected value:** modest — exit-C+entry-2's OWN best number is still net-negative
(-$14.73/tr on the fresh slice, just the smallest loss of 5 candidates). This is "least bad
tested candidate," not a proven winner. Rank accordingly below item 1.

**What would kill it:** entry-2's real fill rate diverging materially from its shadow-implied
77-86% fill rate (T-W5 sim-live parity check), or a real anchor showing the same
fresh-slice-vs-anchor conflict pattern exit-A/B showed.

---

## 3. T-W8 pre-registered candidates (headroom gate, retest-limit entry)

**Evidence state — this is DEAD, not dormant.** The brief asked for "status"; the honest
answer is the study already ran and killed both candidates.
`analysis/recommendations/headroom-retest-tw8.json` (generated 2026-07-09T11:28:14):
pre-registered, hash-verified (`entry-exit-matrix-stop-a-preregistration.json` v1 confirmed),
ran on both the exploratory window (n=250) and the fresh confirmatory slice (n=18).

**Verdict tally: 0 PASS, 10 FAIL, 2 INCONCLUSIVE_SMALL_N** (file `key_findings[1]`). Headline
mechanism failure: the headroom gate (skip signals with <$0.50-1.50 of room to the next
level) **skips a net-POSITIVE cohort** — e.g. at $0.50 threshold, the skipped-on-fresh-slice
trades would have had expectancy **+$62.02/tr under CONTROL** (`skipped_cohort_net_negative:
false` in every H cell) — the gate throws away winners, not just losers, and never beats a
random-skip null at any threshold. The retest-limit entry (R) has the same problem in
reverse: it improves the exploratory window but reverses sign on the fresh slice at both
patience settings tested (3 and 6 bars).

**Single blocking step:** none — this is a closed question with a negative answer. No
further hours recommended on headroom/retest-limit AS SPECIFIED. (If revisited, it would
need a fundamentally different level-selection or headroom-normalization mechanism, not a
parameter retune — the pre-registered grid already covered $0.50-$1.50 thresholds and
3/6-bar patience.)

**Effort / EV / kill:** N/A — already killed by its own evidence.

---

## 4. Prospector battery-ready seeds

**Evidence state:** `analysis/prospector/ideas-ledger.jsonl` (64 rows) + `state.json`
(beat_index 5, fires_total 12, **ideas_total 47, promoted_total 13** — a ~28% historical
promotion rate off the ledger). **47 of 64 logged ideas are `testability:"battery-ready"`**;
every row's `status` field reads `"proposed"` (the ledger's own status field is never
updated to `promoted`/`killed` — promotion tracking lives only in `state.json`'s separate
`promoted_dedupe_keys` list, a minor but real bookkeeping gap).

`qqq_divergence_confluence` (the item named in the brief) is confirmed present
(`analysis/prospector/ideas-ledger.jsonl` line 26): seeded 2026-07-10, source "J+fable
cross-ticker verdict," `testability:"battery-ready"`, `cost:"$0"` (reuses cached SPY replay
machinery + a QQQ 5m feed already available via Alpaca/yfinance, no new vendor). **Zero
battery runs have executed on it** — it is NOT in `promoted_dedupe_keys`, and no
`analysis/recommendations/*qqq*` or `*divergence*` file exists yet.

**Battery cost:** per `backtest_design_swarm.py` docstring (lines 1-22): canonical battery
(WR + expectancy + drawdown + stop-sweep + OOS walk-forward + VIX-regime stratification +
null) runs on **real OPRA fills by default, $0 for the swarm layer** (free-tier models) —
cost is wall-clock, not dollars. Based on the mass-grind's much larger 7,560-combo run
taking ~1.5 days across 12 workers, a SINGLE-idea canonical battery (one hypothesis, not a
7,560-cell grid) should run in well under an hour of compute.

**Single blocking step:** run the canonical battery on `qqq_divergence_confluence` (and the
other 46 battery-ready ideas sitting behind it — **this is a throughput bottleneck**:
ideation is outpacing validation, 64 logged vs. only 13 ever promoted).

**Effort:** LOW per idea (~1-3 hours), but reaching genuinely-armable requires the FULL
sequential gate chain (battery → FDR-survival → real-fills, the same chain item 8 is
mid-way through) — realistically days, not hours, before this could be "close to armable."

**Expected value:** unknown — zero evidence exists yet. Rank below items 1/2/8 which already
carry SOME positive signal.

**What would kill it:** failing the canonical battery's OOS/regime legs, same as any fresh
idea — no reason to expect this one is special until tested.

---

## 5. NLWB (Named-Level Wick-Bounce)

**Evidence state — MEMORY CLAIM CONTRADICTED BY ARTIFACT, flagged per task instructions.**
Memory said "PDL N=157 WR=71%." That number is real but is the **scan-proxy** win rate
(`analysis/recommendations/nlwb_walk_forward.json`: `pdl_relaxed` variant, all-signals proxy
WR 71.3% N=157, walk-forward train 75.7%/N=70 → test 67.8%/N=87, delta -7.9pp, "STABLE").
**The number that actually matters — real option fills — is a different, much worse
picture:**

`analysis/recommendations/nlwb_full_real_fills.json` (run 2026-05-21, window
2025-01-01..2026-05-15): 29 signals found → 23 completed (6 no-OPRA-data) → **11 wins / 12
losses, WR 47.8%**, total P&L **-$1,293.80**, avg **-$56.25/trade**. Explicit verdict field:
**`"DEGRADED — real-fills WR >10pp below ribbon-favorable scan proxy"`**,
**`"op21_real_fills_gate": "FAIL"`**. This is a textbook instance of the repo's own C3
doctrine (SPY-price edge != option edge) — the underlying bounce pattern calls direction
correctly often enough, but premium decay/stop-misfire on the option leg erases it. The
walk-forward file's OTHER two variants (production-default `pdl_calibrated`, and
`round5_tight`) were **not** stable for promotion either (`"stable_for_promotion": false` /
`"FAILED"`); overall verdict: **`"promotion_path": "BLOCKED — OOS degradation detected"`**.

No file newer than 2026-05-24 shows any attempt to re-test or fix this (one untested
refinement idea sits in `strategy/candidates/2026-06-22-chef-nemo-nlwb-stop-tighten-to-bar-
low-minus-0-05.md`, never run; two 2026-07-01 "ideate" musings in `analysis/manager/`, no
new evidence). NLWB was correctly archived (`strategy/candidates/_archive/2026-05/`).

**Single blocking step:** N/A — this is a completed, killed research question, not a
dormant asset. It does not belong on an armable-shelf list. If J wants one more shot, the
only untested lever is the stop-tighten variant (06-22 candidate) — low confidence, given
the failure mode (premium decay before the level thesis plays out) isn't obviously a
stop-placement problem.

**Effort / EV / kill:** N/A (already killed). Optional stop-tighten retest: ~2-4 hours,
low-confidence.

---

## 6. Futures mirror-shadow (7th-arm forward evidence)

**Evidence state:** `automation/state/futures/mirror-shadow-state.json` +
`mirror-would-be.jsonl` confirm the shadow logger is REAL and RUNNING (not a stub): shipped
2026-07-09 (`git log`, commit `6dcc9b5`, 43/43 guards), scheduled `Gamma_FuturesMirror`
5-min RTH. It mirrors the live SPY 0DTE fleet's `BULLISH_RECLAIM_RIDE_THE_RIBBON` signals
into simulated MES point-stop trades (2.0xATR14 stop, 1R TP1, trailing runner).

**Actual accumulation: 1 completed round-trip** as of the last data
(`mirror-would-be.jsonl`, 5 lines total = 1 signal's placed/tp1/stopped lifecycle, entered
2026-07-10T09:34, net roughly -$46 on the two half-units — a single losing round-trip,
uninformative at n=1). Arm bar is **≥20 closed round-trips** with positive expectancy AND
beating an ES=F buy-hold null (`_doc` field in the state file). At the observed pace
(~1 signal per ~2 trading days, gated by how often that ONE specific setup+direction fires
on 4 fleet arms), reaching n=20 is a matter of **weeks**, not a task to execute.

**Single blocking step:** none actionable — **this is genuinely time-gated, not
effort-gated.** The only lever available (widening the mirror to more setups/both
directions to accumulate faster) is a scope decision, not mine to make read-only, and isn't
specified in the shipped spec.

**Effort:** ~0 hours (fully automatic).

**Expected value:** unknown (n=1); would add a 7th arm / new instrument diversification if
it clears, per the FUTURES-MIRROR-SHADOW queue entry.

**What would kill it:** doesn't beat the ES=F buy-hold null once n≥20, or negative
expectancy at n≥20.

---

## 7. entry_manager passive-limit machinery (T-W5 / TWIN-B3)

**Evidence state:** `automation/state/fleet/entry_manager.py` exists, unit-tested, shadow
ledger `automation/state/entry-shadow.jsonl` has **98 rows** (79 `filled`, 19 miss/other).
**Correction to memory:** the ledger has NOT grown since 2026-07-08 (same 98-row count the
last session reported) — confirmed by grep: the only 3 files in the repo that reference
`entry-shadow.jsonl` are `entry_manager.py` itself, `engine_contract.py` (card rendering),
and **`backtest/tools/shadow_entry_backfill.py`** — a one-time historical BACKFILL script,
not a live continuously-running actuator. So "shadow-first" here means "retrospectively
replayed against 8 already-existing historical sessions," not "accumulating forward" — it
satisfied T-W5's `≥3 sessions` acceptance bar via backfill, but there is no live hook
appending fresh rows today.

**What it would save per trade (computed fresh from the artifact, n=79 filled rows):**
mean `basis_delta` (real fill price − shadow limit price) = **$0.0268/contract**, range
$0.003-$0.136. On the ~$1-1.5 average contract in this sample that's roughly 2-3% cheaper
entry — modest, not dramatic — and doesn't net out the cost of the ~19% miss rate (trades
the passive limit wouldn't have gotten filled at all; T-W5's own acceptance check found
sim-live fill-rate parity at 85.9% vs 77.6% backtest, "within tolerance").

**TWIN-B1 dependency is SATISFIED** (verified live, not assumed): `automation/state/crypto-
twin/decisions.jsonl` has 278 rows, latest timestamped **2026-07-11T20:08** (today);
`path-coverage.json` shows real branch tracking (`ENTRY_TP1_TRAIL` GREEN, exercised today);
a real day-one review exists (`automation/state/crypto-twin/reviews/2026-07-11.json`). The
twin is genuinely operational, not just built.

**Single blocking step:** build TWIN-B3 itself (`markdown/planning/TWIN-PROGRAM.md` stream
3) — graduate `entry_manager` to place real limit-below/patience/cancel orders on the twin,
logging mechanism metrics (fill rate, basis delta) against REAL crypto fills instead of a
historical SPY backfill. This validates the entry_manager CODE's live behavior, but note:
it does not by itself produce a SPY-relevant P&L number (crypto twin doesn't trade options)
— it retires the "does this state machine actually work against a live order book" question,
which is a prerequisite for, not a substitute for, the SPY paper A/B exit-C+entry-2 needs
(§2).

**Effort:** MEDIUM, ~4-8 hours to build TWIN-B3 (dependency satisfied, no blockers to start
today). Reaching something armable on SPY is realistically weeks out even after TWIN-B3 —
the STOP-B disposition's own stated path is "forward shadow accrual → T6 paper A/B" (2-week
forward paper per ground rule 17), not a fast unlock.

**Expected value:** mechanism-validation value (de-risks entry_manager before it ever
touches real capital) more than a direct $ edge — the $ edge lives with exit-C+entry-2 (§2),
which is itself only "least-bad," not proven.

**What would kill it:** live crypto fill rate/basis-delta diverging materially from the
backfilled SPY shadow numbers (different market microstructure, expected to differ somewhat
— the twin explicitly discloses this as mechanism-transfer evidence, not edge-transfer).

---

## 8. Pattern-grammar registry + discovery_shadow_ledger (FDR survivors)

**Evidence state:** `backtest/lib/patterns/registry.py` — **11 seeded Tier-1/2 rules**
(triangle ascending/descending, engulfing, wick-rejection, etc., citation-backed via
`markdown/research/PATTERN-GRAMMAR.md`). Explicitly **NO WIRING**: "nothing here is imported
by the live engine, setup_dispatch, or any watcher" (registry.py docstring) — this is a
pure specification layer feeding `pattern_prescreen.py` and, downstream,
`discovery_shadow_ledger.py`.

`discovery_shadow_ledger.py` (the "$100K x all strategies x long and short, just document
what works" engine) has produced a real, large corpus: `analysis/discovery/shadow-ledger.jsonl`
= **66,804 rows**. Its FDR screen (`analysis/discovery/fdr-screen.json`, Benjamini-Hochberg
correction, alpha=0.1, **162 groups tested → 16 survivors**) is the "cleared FDR, waiting on
real-fills confirmation" set the brief asked about. Both files last modified **2026-06-29**
(12 days stale — not recomputed since, though the direction-proxy data doesn't necessarily
need daily refresh).

Strongest survivors by statistical power (large-n, not just large-effect):
`level_rejection/long/stop=0.3%/vix_lo`: **n=1,318, t=5.2, p≈1e-7**; `level_rejection/long/
stop=0.15%/vix_lo`: n=1,318, t=4.5; `trendline_rejection/long/stop=0.15%/vix_hi`: n=338,
t=3.78. Note `level_rejection` is **not one of the two currently-live setups**
(`ribbon_ride`, `vwap_continuation`) — if this clears real-fills, it's a genuinely new,
diversifying setup family, not a tweak to an existing one. (The weakest survivors have n=30-33
with large effects — classic small-n overfit risk; don't lead with those.)

**This is the item 8 exact ask, and it has its own ready-made ticket**, sitting idle:
`FDR-16-OPRA-CONFIRM` (`automation/overnight/queue.md` line 41, **queued 2026-07-02,
still `status:pending` 9 days later**): *"Consume the FDR screen's survivors: take the
top-2 NON-REDUNDANT groups... run them through `lib.simulator_real` on real OPRA fills...
the same real-fills confirm step that graduated bollinger_squeeze."*

**Single blocking step:** literally run the already-specified `FDR-16-OPRA-CONFIRM` action —
nothing to design, the ticket names the exact method and the exact prior precedent
(bollinger_squeeze's graduation used the identical step).

**Effort:** LOW, ~2-4 hours (tool exists — `lib.simulator_real` — data exists, ticket is
fully specified down to which groups to pick first).

**Expected value:** unknown until run (shadow-ledger P&L is a SPY-move direction proxy, not
option P&L — same C3 conversion risk as everything else in this sweep) — but the n=1,318 /
p≈1e-7 top group is about as strong a statistical prior as anything in this repo, and a
NEW setup family has diversification value beyond its raw expectancy.

**What would kill it:** the same C3 failure mode that killed NLWB — direction-proxy edge
evaporating once real premium decay/spread/strike selection is modeled. Given that
precedent, treat this as a real possibility, not a formality.

---

## RANKING — (expected value × probability of clearing) / effort

| rank | asset | EV if clears | P(clears) | effort | reasoning |
|---|---|---|---|---|---|
| **1** | **FDR-16-OPRA-CONFIRM** (§8) | Unknown, but n=1,318/p≈1e-7 is the strongest statistical prior in the sweep; new setup family | MEDIUM | **LOWEST** (~2-4h, fully specified, tool exists, precedent exists) | Cheapest, most neglected (9 days idle), best-specified action in the whole inventory. Even at moderate P(clears), the effort denominator is so small this wins on ratio. |
| **2** | **Mass-grind P5 top cell → real-fills replay** (§1) | **Largest raw $ swing of anything found** ($1,816 backtest edge_capture vs the live shape's proven -$757/-$893) | MEDIUM (two independent evidence sources — T-W7 fresh-slice + this grind — now agree tight-stop beats wide-stop; but live profit-lock-scope semantics unverified) | LOW-MEDIUM (~3-6h, reuses T-W7's proven tooling) | Directly touches the LIVE incumbent's fallback shape — highest stakes of anything on this list, and the confirmatory tooling already exists and was proven 2 days ago. |
| **3** | **entry_manager → TWIN-B3 graduation** (§7, unblocks §2's exit-C+entry-2) | Modest — exit-C+entry-2's own number is still net-negative (least-bad, not proven) | MEDIUM-LOW | MEDIUM (~4-8h to build TWIN-B3; weeks to a real SPY paper A/B after) | Dependency (TWIN-B1) confirmed live today, no blockers to start. Ranked below #1/#2 because the underlying candidate it unlocks (exit-C+entry-2) hasn't shown a positive number yet, only "smallest loss." |
| 4 | Prospector battery run (`qqq_divergence_confluence` + 46 others) (§4) | Unknown — zero evidence yet | LOW-MEDIUM (~28% historical ledger promotion rate) | LOW per idea (~1-3h) but full gate chain to armable is days | Cheap to test but starts from zero evidence, unlike #1/#2 which already carry positive backtest signal. Flagging the 47-idea backlog as a throughput problem, not just one idea. |
| 5 | Futures mirror-shadow (§6) | Unknown (n=1) | Unknown | ~0h but **weeks of calendar time**, not actionable | Excluded from the top of an effort-ranked list on purpose: there is no task to execute, only elapsed time. Zero effort but also zero lever to pull. |
| — | T-W8 headroom/retest (§3) | N/A | N/A | N/A | **DEAD.** 0/10 PASS, closed question. Not a dormant asset. |
| — | NLWB (§5) | N/A | N/A | N/A | **DEAD.** Real-fills gate FAILED 2026-05-21 (-$1,293.80, WR 47.8% vs the 71% scan-proxy memory cited). Not a dormant asset. |

---

## What this sweep changes about "how do we get profitable"

The two cheapest, best-evidenced, ready-to-run next steps (**#1 FDR-16-OPRA-CONFIRM** and
**#2 the P5 top-cell replay**) are both sitting on ALREADY-BUILT tooling and ALREADY-COLLECTED
data — neither needs new infrastructure, new data feeds, or new capital. The single biggest
lever in the entire inventory (#2) is not a new strategy at all: it's confirming whether the
P5 grind's tight-stop shape should replace the live ribbon_ride shape's own fallback, which
the code already flags as a proven loser. Two "near-validated" items (NLWB, T-W8
headroom/retest) turned out to be fully-validated DEAD ENDS on inspection — worth knowing so
no future session re-asks about them.

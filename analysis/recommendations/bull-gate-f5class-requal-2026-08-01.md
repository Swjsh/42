# block_elite_bull re-qualification on the f5=require (ribbon-stacked) subclass — 2026-08-01

> **Verdict: EVIDENCE_AGAINST unblocking. The gate earns its keep on this subclass.**
> On the full 391-day population, the f5=require (ribbon BULL-stacked at entry) subclass of
> block_elite_bull's refused cohort is **net-negative**: n=103, WR 18.45%, **−$4,550.70**
> (**−$44.18/tr**), drop-best **−$5,428.70**, recent-25 also negative (**−$74.45**, n=11).
> All 4 pre-registered gates FAIL. This is **EVIDENCE routed to Safe's scheduled forward
> re-eval trigger** (20 post-fix events or 2026-08-08, whichever first) — **it does NOT flip
> Safe's gate**, which stays armed unchanged.
>
> Prereg: [`bull-gate-f5class-requal-prereg-2026-08-01.json`](bull-gate-f5class-requal-prereg-2026-08-01.json)
> @ `beaa7ba8` (committed before the runner existed). Full cell table:
> [`bull-gate-f5class-requal-2026-08-01.json`](bull-gate-f5class-requal-2026-08-01.json).
> Tool: `backtest/tools/bull_gate_f5class_requal_2026_08_01.py` · Guard:
> `backtest/tests/test_bull_gate_f5class_requal_2026_08_01.py` (26 passed, RED-proofed —
> the guard caught a real drop-best semantics bug before this ran; see Guards below).

## Why this study

WEEKEND-TWELVE's Next-Twelve #2: shelf_hold_reclaim_study.py (WS5, 2026-08-01) found F5
(ribbon BULL-stacked at entry) is the strongest post-hoc separator on its own independent
shelf/geometry detector — `C_cross|f5=require|CONTROL`: n=168, +$5,447 total, **+$32.4/tr**,
positive in every window including held-out. WS5's own conclusion: *"the money lane is
re-qualifying `block_elite_bull` under its own written condition, not wiring a new admission
geometry."* This study tests that claim **directly on the PRODUCTION `block_elite_bull`
refused cohort** (gates.py `tier=='ELITE'` + `'level_reclaim' in triggers` + Safe VIX band
[0,25)) — not WS5's own detector — because that is the population the gate actually gates.

**Filename note:** the synthesis suggested `bull_gate_atm_ssb_requalification.py` as this
study's harness; that file already exists as a different, already-shipped 2026-07-22 study
(disclosed in the prereg's `filename_collision_disclosure` block). This study's runner is
the non-colliding `bull_gate_f5class_requal_2026_08_01.py`, reusing that lineage's mining/
replay machinery (added-cohort diff, `walk_exit_manager` wiring, N_FLOOR=20, drop-best) plus
`elite_bull_postfix_requal_2026_07_31.py`'s already-mined post-fix cohort.

## Method (two cells, two different mining methods, both disclosed)

- **Cell A (full-391, 2025-01-02..2026-07-31):** backtest simulation. `run_backtest` twice —
  BASE (`block_elite_bull=True`, production) and UNBLOCK_ELITE (`block_elite_bull=False`) —
  ATM strike, current Safe gate stack (`elite_bear_level_reject_gate_ab.SAFE_BASE`, the
  field-reconciled config `engine_fullhist_replay.py` itself uses) held fixed. Added cohort =
  trades in UNBLOCK_ELITE not in BASE. Frame: et-v2 throughout (SPY/VIX pre-parsed before
  `run_backtest`; option data independently et-v2-loaded for both entry premium and the exit
  walk — never `run_backtest`'s own wall-v1-tainted `entry_premium`/`dollar_pnl`, which are
  discarded, same doctrine as `engine_fullhist_replay.py`).
- **Cell B (post-fix, 2026-07-28..2026-07-31):** reclassifies the ALREADY-MINED,
  ALREADY-COMMITTED decision-log cohort from `elite-bull-requal-2026-07-31.json`
  (`safe_per_event_qty3`/`qty10`, n=10 events, full E1/E2/E3/F1 exclusion ladder already
  applied) by f5 — no re-mining, no re-walk, a pure post-hoc classification label.

## (a) Why Cell A answers the question — it is NOT the old broken-feed evidence restated

The gate's original 24-fill evidence base (0% WR) was invalidated because it was gathered
**entirely under the broken live intraday levels feed** (IEX premarket, fabricated PMH →
reclaims of levels that weren't really there). That is the specific objection the corrected
feed (levels-compiler-v2, SIP + shelves + weights, commit `7b4aa3f4`, shipped 2026-07-27) was
built to fix, and it is why the gate's own written condition demands "re-eval under corrected
feed."

Cell A's `run_backtest` **never reads that live feed at all.** Its ELITE/`level_reclaim`
trigger sources levels from `lib.levels._detect_from_history` — a backtest-native module that
retro-computes levels directly from the SPY price history itself (per-day, cached per
`LevelSet`), wired through `backtest/lib/orchestrator.py`, structurally separate from
`refresh_levels_intraday.py`/`key-levels.json` (the live pipeline that carried the IEX/SIP
bug). Cell A was therefore **never contaminated by the bug in the first place** — its −$44/tr
number cannot be explained away as "measured on broken data" the way the original 24-fill
evidence could. It answers a genuinely different, and prior, question: independent of any
live-feed defect, does this subclass have structure across 391 days of real OPRA fills? The
answer is no, and it converges with (rather than merely repeating) the old-era verdict from a
methodologically independent angle — two different data-quality regimes agreeing is stronger
evidence than either alone, not weaker. Cell B, by contrast, IS built from real engine
refusals logged live during the corrected-feed era — that is where "under the corrected feed"
is tested directly (see below); the two cells are deliberately not the same claim.

## The evidence, every cell

| Cell | n | Total | Exp/tr | WR | Day-maj | Drop-best | Recent-25 | BH-sig (q=0.10) | Tier |
|---|---|---|---|---|---|---|---|---|---|
| **Cell A require** (391d, PRIMARY) | **103** | **−$4,550.70** | **−$44.18** | 18.5% | 15/85 ✗ | **−$5,428.70** ✗ | −$74.45 (n=11) ✗ | ✗ (p=0.084) | **EVIDENCE_AGAINST** |
| Cell A drop (391d, baseline) | 106 | −$4,624.70 | −$43.63 | 18.9% | 16/88 ✗ | −$5,502.70 ✗ | −$238.45 (n=12) ✗ | ✗ (p=0.080) | EVIDENCE_AGAINST |
| Cell B require, qty3 (post-fix) | 10 | +$882.00 | +$88.20 | 40% | 2/3 ✓ | +$192.40 ✓ | n/a — whole cell | ✗ (p=0.419) | **UNDERPOWERED** |
| Cell B drop, qty3 (post-fix) | 10 | +$882.00 | +$88.20 | 40% | 2/3 ✓ | +$192.40 ✓ | n/a — whole cell | ✗ (p=0.419) | UNDERPOWERED |
| Cell B require, qty10 (sensitivity) | 10 | +$3,130.00 | +$313.00 | 40% | 2/3 ✓ | +$771.60 ✓ | n/a — whole cell | n/a (outside BH family) | UNDERPOWERED |
| Cell B drop, qty10 (sensitivity) | 10 | +$3,130.00 | +$313.00 | 40% | 2/3 ✓ | +$771.60 ✓ | n/a — whole cell | n/a (outside BH family) | UNDERPOWERED |

n floor = **20** (OP-16's own evidence_n bar, matching this exact lineage's established
constant, pinned by `test_n_floor_matches_op16_evidence_bar`). Below floor = UNDERPOWERED,
never a verdict either way, per the frozen prereg.

Population: base_trade_count=215, unblock_elite_trade_count=318, elite_added raw n=107
(1 dropped, no OPRA cache/no bar at/after entry — C7, never imputed). Cell A's own window
overlaps Cell B's 4 days: only 4 of Cell A's 103 f5=require trades fall in 07-28..07-31 —
`run_backtest`'s retro level detection finds a *smaller* set of ELITE bull signals in that
window than the live engine actually flagged in real time (4 vs Cell B's 10), a second,
independent confirmation that Cells A and B are genuinely different populations, not two
slices of the same thing.

**Cell B require == Cell B drop, exactly, at both qty tiers.** All 10 of the post-fix era's
real block_elite_bull refusals were already ribbon-stacked at entry — f5 classifies 10/10 as
`require`, so it narrows nothing in this specific small sample. Cell A's own require/drop gap
is similarly thin (103 of 106 valid replays, 97%) — the production ELITE tier's own
`confluence`+`level_reclaim` trigger requirement is *already* overwhelmingly coincident with
"ribbon bull-stacked," on both cells. That is the mechanical reason Cell A's require and drop
numbers move together (−$44.18/tr vs −$43.63/tr) rather than diverging the way WS5's own
`f5=drop` vs `f5=require` comparison did.

## BH-FDR

Family (per the frozen prereg): Cell A {require, drop} + Cell B qty3 {require, drop} — 4
raw p-values, one-sample t-test on per-trade pnls (`shelf_hold_reclaim_study.one_sample_p`,
reused verbatim so this study's p-values are computed identically to WS5's own). **0 of 4
cells survive BH-FDR q=0.10** — Cell A's raw p-values (0.084, 0.080) are the closest to
significance in the whole family, and they are the NEGATIVE cells. The qty10 cells are
reported as a sizing-sensitivity view outside the formal family (disclosed in the prereg;
qty3 is PRIMARY sizing per the elite-bull-requal-prereg-2026-07-31.json convention this study
inherits) — their own p-values (0.402) would not change the family's outcome either way.

## Concentration and day-majority detail

- **Cell A require:** 85 distinct trading days over 103 trades; only 15 of those days (17.6%)
  are net-positive — day-majority fails by a wide margin, not a coin flip. The single best day
  (2025-02-13, two trades, +$1,320.00 combined) is real but the aggregate is already negative
  before removing it; the `concentration_top_day_share` field renders as a negative ratio
  (best-day-$ ÷ negative-total) which is not a meaningful "% concentration" reading on a
  losing cohort — reported here as raw dollars instead, not the ratio. Drop-best removes the
  single largest-winning *trade* (2025-02-13's +$758.00 leg) and the remainder is still
  −$5,428.70 — the loss is not one unlucky/lucky trade away from flipping.
- **Cell A drop:** same shape, marginally worse (16/88 days win, −$5,502.70 drop-best) —
  consistent with require being a near-no-op filter on this cohort (see above).
- **Cell B (both qty tiers, require==drop):** day-majority technically PASSES (2 of 3 days
  positive) but `concentration_top_day_share` is 0.895 (qty3) / 0.882 (qty10) — 88-90% of the
  entire post-fix total sits in ONE day (2026-07-31). At n=10 this is exactly the
  "UNDERPOWERED, not a verdict" case the n-floor exists for: a real, disclosed positive
  number that is one good day away from being a loss, below the bar that would let it argue
  anything either way.

## (b) Verdict routing — evidence, not a flip

This study produces **evidence for Safe's forward `block_elite_bull` re-eval trigger**
(`automation/state/gate-registry.json`: *"post-fix distinct tradeable safe events >= 20 OR 10
corrected-feed sessions elapsed (2026-08-08), whichever first"*). It is **not** an automatic
gate flip. Safe's `block_elite_bull` (VIX band [0,25), effectively unconditional) **stays
armed, unchanged, by this study** — the scheduled trigger is the only mechanism that changes
it, and this artifact exists to feed that trigger's evidence base, not to substitute for it.
This session did not edit `automation/state/params.json`, and does not.

**Downstream, same-session context (performed by the coordinator, not by this study):** this
study's Cell A number was one of two independent disconfirmations (the other: Bold's own
cohort at true sizing runs +$7.80/n=5, drop-best −$535.00 — a coin flip, not the +$867 Safe
figure the trial was misattributed from) that led to reverting the bold-2 lift-gate trial
armed earlier tonight (`b6a9db67` → reverted `711420f4`; `block_elite_bull` is `true` on
bold-2 again). `gate-registry.json`'s `block_elite_bull` row was updated by that same session
(surgical edit, not touched by this study). A lesson item is filed at
`strategy/candidates/_lesson-inbox/2026-08-01-per-account-gate-needs-per-account-cohort.md`.
None of that reversal changes this study's own scope or verdict — it is reported here only so
a reader of this file has the full same-session chain, not because this study performed it.

## Reconciling against WS5's +$32.4/tr

WS5's `C_cross|f5=require|CONTROL` (+$32.4/tr, n=168) and this study's Cell A require
(−$44.18/tr, n=103) are **not the same population**, despite both being "ribbon-stacked bull
level-reclaims." WS5's admission is its own `detect_level_reclaim` fire at a *w5-anchor-scoped
persistent shelf* (a narrower, curated structural precondition WS5 built and validated with
its own anchor/zone machinery), independent of the production tier/trigger-count scoring.
This study's admission is the *production* ELITE tier (`confluence` or `sequence` trigger,
i.e. `n>=3` triggers or `confluence AND ribbon_flip`) `AND level_reclaim` — a broader,
score-based class that admits many level-reclaims WS5's shelf-anchor geometry would not. The
two studies independently confirm they are looking at overlapping but distinct signal
families; WS5's own report already flagged this as a "post-hoc, unshipped" secondary finding,
not a claim about the production gate's actual refused cohort. This study is the direct test
of that gate's actual population, and it does not carry WS5's positive number forward.

## Caveats (all of them)

- Cell A's ELITE/level_reclaim admission depends on `lib.levels._detect_from_history`, a
  backtest-native retro level detector, not the live compiler — see (a) above for why that
  makes Cell A responsive to the question rather than contaminated, but it also means Cell A
  is a **structural-generalization** test, not literally "under the corrected feed."
  Cell B is the corrected-feed-literal cell, and it is underpowered (n=10).
- `run_backtest`'s own `use_real_fills` ADMISSION gate (whether a trade enters the cohort at
  all) may internally consult wall-v1-parsed option data for winter dates; every dollar
  actually reported here is independently re-derived et-v2-consistent regardless (entry
  premium and the full exit walk both use a fresh et-v2 OPRA loader) — only the admission
  boundary carries this residual, disclosed risk, never the P&L math of admitted trades.
- Cell B's n=10 is a citation of an already-committed, already-guard-tested cohort
  (`elite-bull-requal-2026-07-31.json`) — this study did not re-mine or re-walk it, only
  applied the f5 label. Any correction to that source study would need re-propagating here.
- qty10 Cell B cells are a sizing-sensitivity view, not part of the formal BH-FDR family
  (disclosed in the prereg).
- block_bull_1100_1200 (a different GATE_ORDER gate) is out of scope by design — conflating
  two gates in one BH-FDR family would blur both; see the prereg's scope_lock.
- Bold is out of scope for this study's own hypothesis (it targets Safe's re-eval question);
  the coordinator's separate Bold-specific replay and reversal are cited above for context
  only.

## Guards

`backtest/tests/test_bull_gate_f5class_requal_2026_08_01.py` — 26 tests, pure functions only
(no network, no broker, no full backtest re-run). RED-proofed for real: the first full run of
this suite caught a genuine semantics bug in `drop_best` (it was unconditionally dropping
`max(pnls)` even when every trade was a loser, silently reporting a "least-bad-loser-removed"
number instead of the raw total) before any cell was computed — fixed to match
`bull_gate_atm_ssb_requalification.drop_top1`'s convention (only drop an actual winner),
documented in the function's own docstring as a deliberate deviation from
`shelf_hold_reclaim_study.lane_stats.drop_best`'s unconditional-max convention. Also covers:
day-majority aggregation (by day, not by trade), f5 backward-as-of correctness (no
look-ahead, verified against out-of-order input), `added_bull_cohort` base-vs-unblock diffing,
BH-FDR, and all four `grade_cell` verdict-tier branches (UNDERPOWERED / EVIDENCE_FOR_REEVAL /
EVIDENCE_AGAINST / MIXED).

Runtime: 189.2s (full 391-day, two `run_backtest` passes + per-trade et-v2 exit re-walk).

*Analysis only: this session edited no live config, param, or order. `gate-registry.json` was
edited by the coordinator's session, not this one.*

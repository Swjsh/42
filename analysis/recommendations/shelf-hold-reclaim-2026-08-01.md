# SHELF_HOLD_RECLAIM full-population study — RESULTS (WS5, 2026-08-01)

**VERDICT: NULL — all 4 admission geometries, all 96 cells. Nothing ships, nothing arms.**
J's "enter on the defended touch" question is now closed with full-population numbers:
entering the defense EARLY (wick-defense or touch-and-hold) does **not** beat the late
close-cross confirmation at w5 shelf anchors, and the whole lane is flat-to-negative
without trend alignment. The dose-response J's style implies is **inverted**.

- **Pre-reg:** `shelf-hold-reclaim-prereg-2026-08-01.md` @ `96a85efc` (et_clock stamped, committed
  before the runner existed). Runner: `backtest/tools/shelf_hold_reclaim_study.py` @ `21b6ba99`.
- **Population:** the VERIFIED 391 sessions 2025-01-02..2026-07-31 (et-v2 frame; 3 half-days
  excluded; 2024 untouched — backfill completion doc absent). 329/391 sessions had ≥1 w5 anchor
  (mean 5.79/day).
- **Data:** real OPRA only, **zero exclusions in the final pass** — 117 missing contracts
  (15% of 779 referenced; 30% of July-2026 signals) were backfilled mid-study via the canonical
  `fetch_option_data` conventions, and the study re-ran on the complete store. Pass-1
  (pre-backfill) preserved at `shelf-hold-reclaim-2026-08-01.pass1-precache.json` — verdicts
  identical in both passes (NULL), but pass-1's recent-25 numbers were distorted by the gap
  (A recent-25 −$137 → **+$1,035** after completion; e1/e2 were among the missing winners).
- Full 96-cell table: `shelf-hold-reclaim-2026-08-01.json`.

## Harness fidelity (the reason to believe the NULL)

- Sanity anchors **3/3 HIT**: the harness live-fires geometry A at J's e1 (07-31 10:15 wick,
  737.86 anchor), B at e2 (739.65 anchor, hold window), C at e3 (743.18 anchor, 12:10 cross).
- **Penny-exact walk validation** against the independent J-CALLED n=4 tool:
  e1 in-harness = fill 10:20 `SPY260731C00739000` @ $1.98 → **+$550.75, runner_stop @ 3.53**
  (anecdote: +$550.75, runner_stop 3.53); e3 = +$330.40 runner_stop @ 2.24 (anecdote: +$330.40).
  Same exit core (`walk_exit_manager` → real `plan_exit_actions`), entry+1, structure stop at
  zone floor, ribbon flip-back exits ENABLED (higher fidelity than the anecdote's df=None).
- On J's called day (07-31) the primary A-cell made **+$1,175 across 4 trades**. Friday was a
  genuinely good day for this lane. The population says Friday is not the norm.

## Primary cells (hypothesis-native: F5 drop, F8 off, F10 off, CONTROL exit, qty=3)

| Geometry | n | Total | Exp/tr | WR | Day-maj | Held-out (last 25%) | Recent-25 | p |
|---|---|---|---|---|---|---|---|---|
| A wick-defense | 599 | **+$173** | +$0.29 | 38% | 84/171 ✗ | −$1,805 ✗ | +$1,035 ✓ | 0.97 |
| B touch-and-hold | 691 | **−$10,223** | −$14.79 | 36% | ✗ | −$3,225 ✗ | +$1,280 ✓ | 0.045* |
| C close-cross | 615 | **+$289** | +$0.47 | 39% | ✗ | −$1,230 ✗ | +$2,318 ✓ | 0.96 |
| UNION | 942 | **−$5,105** | −$5.42 | 39% | ✗ | −$2,342 ✗ | +$649 ✓ | 0.38 |

*The grid's strongest raw p (0.045) is B's **negative** cell — the most confident finding in the
whole study is that buying the touch-and-hold is a loser. **0 of 96 cells survive BH-FDR q=0.10.**

- **Dose-response (H2) FAILS, inverted:** exp C (+$0.47) ≥ A (+$0.29) ≫ B (−$14.79).
  The late confirmation is not worse than the early defense — and the earliest-style entry (B)
  is the worst thing tested.
- Day-majority fails everywhere; held-out (post-2026-03-12) negative everywhere.
- Recent-25 (2026-06-26..07-31) is positive for every geometry — July's bull tape pays
  everything bull-shaped; it is not evidence for this lane specifically.

## The one real structure found (secondary, post-hoc, NOT shippable from this study)

**F5 (ribbon BULL-stacked) — the filter the spec demoted — is the strongest separator in the
grid, with a clean monotone dose in the OPPOSITE direction from the hypothesis** (CONTROL lane,
F8/F10 off):

| Geometry | F5=drop | F5=htf | F5=require |
|---|---|---|---|
| A wick-defense | +$173 (n=599) | +$2,385 (n=270) | **+$4,924** (n=172, exp +$28.6) |
| B touch-and-hold | −$10,223 | −$2,877 | −$2,662 (negative under every mode) |
| C close-cross | +$289 | +$1,359 | **+$5,447** (n=168, exp +$32.4) |

- `C_cross|f5=require|CONTROL` is the best cell in the study: +$5,447/168tr, held-out +$1,254,
  recent-25 +$2,462, concentration 15.8% — positive in every window — yet p=0.187 raw,
  BH-FDR ✗, and it is a post-hoc slice under a frozen prereg that made {F5=drop} primary.
- **What that cell IS: the engine's existing ELITE bull class** — `detect_level_reclaim` at a
  persistent shelf with the ribbon already BULL-stacked — i.e., the exact signal class
  `block_elite_bull` refused 111× on Friday. This study independently converges, from the full
  population, on the parent spec's §5 "smaller fact": **the money lane is re-qualifying
  `block_elite_bull` under its own written condition, not wiring a new admission geometry.**
  (That re-qual is its own pre-registered lane — `bull_gate_atm_ssb_requalification.py` — and
  is already flagged by tonight's WS1 elite-bull gap check.)
- H3 ("F5/F8/F10 don't distinguish winners here") is **contradicted** for F5. F8-on subtracts
  P&L at f5=require (A: +$4,924→+$1,692; C: +$5,447→+$1,886) — mostly by shrinking n. F10
  similar. e1 (refused live by {5,8,10}) remains a true individual winner the filters would
  refuse — but its CLASS (unstacked V-bottom defenses) is a net loser over 391 days.
- ZONE-RIDE (trail 0.20) loses to CONTROL (trail 0.15) on every primary combo
  (−$380..−$550 per cell): the n=4 anecdote's ZONE-RIDE edge does not generalize.

## Why B loses (mechanism, from exit-reason distribution)

B fires mid-consolidation at zone floors (2,049 admitted fires under hard filters alone — the
most permissive geometry). Dominant exit is `ribbon_flip_back` (~63%) at a loss: buying a
stagnating zone bleeds theta until the ribbon flips against. The hold-geometry's "earliness" is
mostly early entry into chop.

## Gates summary (frozen prereg §9)

| Gate | A | B | C | UNION |
|---|---|---|---|---|
| g1 positive aggregate | ✓ | ✗ | ✓ | ✗ |
| g2 day-majority | ✗ | ✗ | ✗ | ✗ |
| g3 drop-best | ✗ | ✗ | ✗ | ✗ |
| g4 held-out ≥ 0 | ✗ | ✗ | ✗ | ✗ |
| g5 recent-25 ≥ 0 | ✓ | ✓ | ✓ | ✓ |
| g6 dose-response | ✗ | ✗ | ✗ | ✗ |
| g7 BH-FDR q=0.10 | ✗ | ✗ | ✗ | ✗ |
| **Verdict** | **NULL** | **NULL** | **NULL** | **NULL** |

Runner-cohort no-regression (g8): satisfied by construction — entry-additive study; CONTROL
exit shape asserted byte-identical to the live registry `RIBBON_RIDE.exit`; no exit knob of any
existing lane was touched; the 35-winner +$15,774 runner cohort is untouched.

## Graveyard entry (append to the standing list)

> **shelf-hold defended-touch entries at w5 anchors (A wick-defense / B touch-and-hold /
> C early-routed close-cross, and their union) — tested full-population 2026-08-01, ALL NULL.**
> Dose-response inverted (late confirmation ≥ early defense; touch-and-hold −$14.8/tr,
> p=0.045 for the LOSS). Do not re-test these as standalone admission lanes. The surviving
> question is `block_elite_bull` re-qualification (ribbon-stacked shelf reclaims), which is a
> GATE re-eval, not a new detector — separate pre-reg.

## Caveats (all of them)

- Frame: et-v2 opt-in (prereg cited the ladder loader for file lineage; wall-v1 would inject
  winter VIX look-ahead (C6) + clip the last true hour on 129 EST days; decided before first
  run; the three 07-31 anchors are EDT ⇒ frame-invariant fidelity checks).
- Fills are OPRA bar-open prints at trigger+5min, no slippage/spread model (same convention as
  the parent replay; validated ~10% optimistic vs one broker-true cell there). A slippage
  haircut makes every number WORSE — it cannot rescue the NULL.
- Occupancy: one-position-at-a-time; trade set defined by CONTROL-lane exit times, both lanes
  paired on identical trades; exclusions never consumed occupancy (moot in pass-2: zero
  exclusions). Multiple same-bar geometry fires in UNION resolve A>B>C (frozen).
- Winter OPRA files end 15:30 EST per the store's own fetch window (uniform across old and
  newly-backfilled files); time-stop is 15:40 — winter trades still open then force-close at
  the last available bar, disclosed via `data_exhausted_force_close` exit reasons.
- `exit_manager.py` hardcodes the label `time_stop_15:50` regardless of the enforced 15:40
  time stop (mechanism verified correct at line 357; label-only bug; spin-off chip filed
  task_30a7b291).
- The retro w5 anchor feed is shelf-derived only (level-memory levels not retro-reconstructable)
  — J's e2 line 739.73 mapped to the retro 739.65 anchor (8c off), inside tolerance.
- qty=3 min size, ATM, calls only. Bear mirror untested (separate pre-reg per spec).
- The backfilled 117 contracts live in the gitignored options store; a fresh clone re-runs
  pass-1-like until refetched (fetch list derivable from the runner's own exclusion counters).

*Analysis only: no live config, param, gate, or order touched. Concurrent-lane fence respected
(no writes to twin/theta files). $0 LLM cost — pure Python + free OPRA fetches.*

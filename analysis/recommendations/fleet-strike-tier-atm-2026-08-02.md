# FLEET-STRIKE-TIER-ATM-EXTENSION — day+1 independent audit (2026-08-02)

**Verdict: KEEP AS SHIPPED. No revert, no code change.** This is NOT a fills-based A/B —
zero real fills exist under the new routing yet (see below). This is a verification pass on
an already-shipped change: is the routing correct, do the guards hold, and does anything in
the evidence base argue for an early revert before the forward evaluation even starts.

Full machine-readable version: [`fleet-strike-tier-atm-2026-08-02.json`](fleet-strike-tier-atm-2026-08-02.json).

---

## 0. The change was already shipped before this audit started

Commit `43bb979d` (Fri 2026-07-31 23:13:13 MT / ~01:13 ET Sat) — *"extend
V15_BOLD_CORE_TIERS (ATM) to risky-1/risky-3, pre-registered"* — is an ancestor of current
HEAD. `accounts.json` already carries `params_patch.strike_tier_table='bold_core'` on
risky-1/risky-3 only; safe-3 is unedited. The pre-reg
(`fleet-strike-tier-atm-extension-prereg-2026-08-01.json`) was frozen before arming. This
audit independently re-verifies that ship rather than re-deciding whether to make it.

## 1. Framing correction

The task brief characterized this as an extension of an "already-validated" change (core
Bold, 07-17). **That overstates it.** Read `bold-strike-axis-2026-07-15.json` directly:
every one of its 6 strike cells (OTM-3..ITM-2) is `ship_ready: false`. ATM fails only the
walk-forward gate — and that gate is *structurally unreachable* for this entire cohort+shape
(every cell's in-sample mean is negative under this exit convention, so `wf = oos/is` is
undefined by construction, confirmed independently on both Safe's and Bold's own strike-axis
studies). The study's own verdict label: **"WATCH — NOT ship-ready... a near-miss worth a
human/Fable look, not a same-night auto-ship."** Core Bold's 07-17/18 wire required J's
explicit in-chat "yes" specifically *because* the P&L case hadn't cleared.

So: `V15_BOLD_CORE_TIERS` is validated **machinery** (guard-tested, live since 07-17/18, no
incidents) whose underlying **P&L case never cleared full validation**. It shipped — and this
extension ships — on this repo's TRADE-TO-LEARN doctrine (paper, guarded, one-line-revertible,
forward-evidence-pending), the same pattern already used for score-ladder and full-send. That
is a legitimate pattern here, but it should be reported as what it is, not oversold.

## 2. Routing verification (before/after)

| Arm | Before (pre-07-31) | After (current, verified) | Change today? |
|---|---|---|---|
| safe-3 | `V15_BOLD_TIERS` (explicit `'bold'`) | `V15_BOLD_TIERS` — **unchanged** | No |
| risky-1 | `V15_BOLD_TIERS` (id-prefix default) | `V15_BOLD_CORE_TIERS` (`'bold_core'`) | **Yes** |
| risky-3 | `V15_BOLD_TIERS` (id-prefix default) | `V15_BOLD_CORE_TIERS` (`'bold_core'`) | Wired, but no-op today (see §3) |

The two tables are identical except the $0–2K bracket: `V15_BOLD_TIERS` = OTM-3 there,
`V15_BOLD_CORE_TIERS` = ATM. Both share $2K–10K = OTM-2, $10K–25K = OTM-1, $25K+ = ITM-2.

Confirmed via direct read of `fleet_executor._tiers_for_arm` and `accounts.json` — not from
the commit message.

## 3. Live equity (re-verified fresh, not trusted from the brief)

| Arm | Account | Equity | vs $2K | Resolved tier now |
|---|---|---:|---:|---|
| safe-3 | PA32RD49OB0Q | $1,967.81 | −$32.19 | OTM-3 (unchanged) |
| risky-1 | PA3W17FD8G19 | $1,756.87 | −$243.13 | **ATM** (was OTM-3) |
| risky-3 | PA31WIU8X15Q | $2,121.61 | +$121.61 | OTM-2 (same under both tables) |

**Only risky-1 changes behavior today.** risky-3 is above $2K, so it sits in the $2K–10K
bracket where both tables agree (OTM-2) — wired but inert until/unless its equity drops back
under $2K.

**Correction to a working assumption in the task brief:** risky-1's `full_send` lane is a
*fallback*, not the primary path. `fleet_executor.plan_all()` evaluates the normal
(tight-gated) lane FIRST on every tick via `_tiers_for_arm`/`bold_core`; probe/ladder/full-send
only fire when the normal lane produces zero ENTER. So risky-1's tight-gated entries
(`min_triggers=2` + confluence/sequence required) now price ATM on the first pass — this is
not a marginal/rarely-touched path, it's the primary one.

## 4. Guards — re-verified fresh, not trusted from the commit message

```
backtest/.venv/Scripts/python.exe -m pytest \
  backtest/tests/test_bold_core_strike_tier_2026_07_15.py \
  backtest/tests/test_fleet_strike_tier_floor_collision_2026_07_31.py \
  backtest/tests/test_fleet_arm_parity.py -q
→ 42 passed in 0.30s
```

Read the assertions directly (not just the pass count). Both are genuine bidirectional
vary-and-assert (the exact C14 dead-knob guard the task called for):

- `test_fleet_arms_resolve_otm3_under_2k_via_shared_table`: safe-3's tiers `is`
  `V15_BOLD_TIERS` **and** `is not` `V15_BOLD_CORE_TIERS`.
- `test_fleet_arms_risky_1_3_resolve_atm_under_2k_via_bold_core_table`: risky-1/risky-3's
  tiers `is` `V15_BOLD_CORE_TIERS` **and** `is not` `V15_BOLD_TIERS`.

This catches both a silent non-route on risky-1/risky-3 *and* a silent over-route onto
safe-3. Already present — no new guard needed.

## 5. Re-measurement attempt — why `bold_fullhist_replay.py` was not used as-is

The task named `backtest/tools/bold_fullhist_replay.py` for re-measurement. Read the full
source: it hardcodes **core Bold's own gate profile** (`aggressive/params.json`:
`min_triggers=1`, no confluence requirement, `require_bearish_fill_bar=True`) inside
`bold_base_live()`. Only `equity` is exposed as an override. Neither risky-1's TIGHT gate
(`min_triggers=2` + confluence required) nor risky-3's LOOSE gate (`min_triggers=1` +
`hard_skip_verdicts=[]`, which also makes it ignore `require_bearish_fill_bar` — looser than
Bold's own gate) is modeled. It also only re-derives `ribbon_ride` exits, not
`vwap_continuation`. Running it with equity overridden would answer "what would Bold's own
population look like at a fleet arm's equity" — a different, less useful question than "what
does risky-1/risky-3's own gated population look like" — and risks the exact OP-16
sim-accuracy failure this repo's own doctrine warns about. Ran `--anchor-only` as a pure
tool-health check (6/7 real bold-2 fills reproduce within tolerance) — informative about the
tool, not about this question.

`backtest/replay_fleet_arms.py` **does** faithfully construct each arm's own gated
population (injects `min_triggers` from `gate_override`, applies direction-lock/confluence
filters) — but its own docstring places strike/qty explicitly out of scope ("a separate
parity check, not the gate"); it validates entry timing only, never exit P&L by strike tier.

**Why not extended this session:** any such backtest is fundamentally unanchored at the ATM
strike specifically, because zero real fills exist at ATM pricing for these arms — that's the
whole reason this is a forward paper experiment. This repo's own `full-send-arm-2026-07-31.md`
already reached the identical conclusion for a related mechanism: *"the incremental trades
this arm adds have NO valid measurement at their actual strike. Its forward paper ledger is
the evidence, and nothing else here is."* Rushing new unanchored machinery under time
pressure would add false precision, not real evidence — this repo has already self-corrected
two similar mistakes this same week (an elite-bull mislabeled-cohort error, the full-send
biased-ratio-estimator error), both caught only by adversarial re-review after initial
shipping. Flagged as real follow-up work (see below), not built here.

## 6. Existing evidence synthesized

| Source | Population | Finding |
|---|---|---|
| `bold-strike-axis-2026-07-15.json` | Core Bold's own gate profile | ATM: OOS +$28.77/tr, floor-clearance 96.88% vs OTM-3's 33.76%, sub-window stable, BH-FDR survivor. Fails only the structurally-null WF gate. Verdict: WATCH, not ship-ready. |
| `min-entry-premium-2026-07-31.json` | The fleet-specific blocked cohort, replayed **at each arm's existing OTM strike** | n=25, total **−$145.20**, −$5.81/tr, still negative on drop-best. By arm: safe-3 +$27.40 (n=8), **risky-1 −$92.10 (n=10)**, risky-3 −$80.50 (n=7). Small-n anecdote, not auto-ratify-eligible. Measures the OLD strike, not the NEW one. |
| `full-send-arm-2026-07-31.md` | A related but distinct mechanism — risky-1's cohort-vetoed bypass population, priced OTM-2 vs ATM | Full pop (387 sess): OTM-2 **+$3,430** → ATM **−$5,110** (327 vs 332 trades). Recent-25: **+$118 → −$1,088**. Near-flat trade count, dramatically worse P&L nearer strike. |

The full-send precedent is real, on-the-record, real-OPRA-fills evidence that "nearer strike
= more participation" does not reliably mean "better P&L" for a *marginal/low-conviction*
fleet cohort. It does not directly contradict the bold_core case, because it measured an
explicitly lower-quality (cohort-vetoed) population, not risky-1's tight-gated (higher
selectivity than Bold's own) normal lane — but it argues for treating the first handful of
forward fills as an early-warning check, not a silent wait to n=20.

## 7. Forward evidence status

Ship landed Friday night after close. Saturday/Sunday are non-trading. **Zero real fills
exist under `bold_core` as of this audit** — simple calendar fact, not an assumption. The
pre-reg's `n>=20` gate is genuinely unstarted. `FLEET-STRIKE-TIER-ATM-EXTENSION-EVAL-2026-08-01`
in `queue.md` correctly stays `status:pending` — this audit does not close it, because doing
so would fabricate an evaluation that cannot exist yet.

## 8. Verdict

**KEEP AS SHIPPED.** No revert, no code change. Routing is correct, guards are green and
genuinely vary-and-assert, the change is paper-only and one-line-revertible, every downstream
risk guard is untouched and independently tested, and nothing has happened yet (zero fills)
that would justify reverting a bounded experiment before it's had a chance to run. The
full-send counter-precedent is disclosed and should sharpen the eventual evaluation, not
trigger an early kill on a population it didn't measure.

**Recommended, not applied:** add an n≥5 early-warning read (not a new decision gate — the
frozen pre-reg isn't reopened by this audit) that specifically checks for a
full-send-shaped result (P&L sharply negative despite fills up) ahead of the full n≥20 score.

**Forward kill criterion (unchanged from the frozen pre-reg):** de-arm if the n≥20-fill
cohort fails OOS-positive, or the anchor-collision cohort doesn't show materially fewer
`SKIP_MIN_PREMIUM_FLOOR` refusals. Revert = delete `'strike_tier_table': 'bold_core'` from
risky-1/risky-3's `params_patch` in `accounts.json` (one line each, byte-identical).

## 9. Correction (Sonnet, 2026-08-02, later same night -- instrumented dry-run + git-blame)

**§3 above is WRONG on one factual claim.** It describes risky-1's normal lane as
"tight-gated (min_triggers=2 + confluence/sequence required)". That is false on the current
`accounts.json`: commit `43bb979d` was preceded, the SAME night, by `e28d210c` (2026-07-31
16:21, the FULL-SEND ship), which **replaced** risky-1's `gate_override` with
`{"full_send": true}` wholesale -- it deleted `min_triggers`/`require_confluence_or_sequence`
rather than layering full-send under them (`git show e28d210c -- accounts.json`). This was
already independently found and fixed the same night, hours before this audit: `queue.md`'s
`FLEET-PARITY-TESTS-READ-LIVE-STATE` entry (commit `dea5b2e2`) rewrote a stale test with the
explicit note "risky-1 ... its normal lane is now UNGATED same as risky-3." Likely proximate
cause of this audit's error: `accounts.json`'s `grid.map` metadata still read
`"risky-1": "risky x tight"` (never updated in the full-send commit, even though the arm's
own `cell` field already said `"risky x FULL-SEND"`) -- fixed this session, `grid.map_doc`
added to prevent recurrence.

**Corrected composition** (proven by instrumented dry-run against the REAL
`fleet_executor.plan_all` + `build_shared_signal.build_from_rows`, not code-reading --
`setup/scripts/risky1_lane_composition_check.py`, guards in
`automation/state/fleet/test_risky1_lane_composition_check.py`, 9/9 green): risky-1's normal
lane is UNGATED and now prices ATM via `bold_core` for *any* passing signal -- the same
population class as risky-3/bold-2's own entries, not a narrow ELITE-only subset. At
risky-1's current equity (<$2K) this happens to numerically coincide with the FULL-SEND
lane's own `PROBE_STRIKE_TIERS` pricing (both ATM) -- verified **equity-contingent, not
structural**: the two tables diverge at/above $2,000 (`bold_core`\-\>OTM-2,
`PROBE_STRIKE_TIERS`\-\>stays ATM to $10K). The two lanes remain population-disjoint
(full-send requires an `action` on its own 5-verdict allowlist, mutually exclusive with a
normally-passing tick) and separately tagged (`EntryPlan.reason` `"FULL_SEND ..."` vs
`"{strategy} {side} ({quality})"`), so **per-fill attribution between the two 07-31
experiments is intact** despite this error -- what was actually missing was that this
prereg's own evaluation methodology never said to keep the two cohorts separate. Fixed: a
`lane_scoping_addendum` filed on `fleet-strike-tier-atm-extension-prereg-2026-08-01.json`
(frozen while n=0, before any fills exist) requiring risky-1's future bold_core scorecard to
exclude `reason`-tagged `FULL_SEND` fills from its own n>=20 cohort (bold_core is provably
inert on those fills -- `_full_send_plan` never calls `_tiers_for_arm`).

**Does this change the verdict? No.** KEEP AS SHIPPED still stands -- routing is still
correct, guards are still green, the change is still paper/one-line-revertible. What changes
is the *description* of how large a population risky-1's normal lane now touches (larger
than "tight-gated" implied), and the disclosure that full-send and bold_core are two
different-but-currently-coincident mechanisms on one arm, not that one silently substitutes
the other.

**Additional finding, flagged not fixed (out of scope tonight):** the same instrumented
check surfaced that risky-3's own `gate_params.hard_skip_verdicts: []` rescue (built
2026-07-23, "GATE-TIERS-IMPLEMENT", specifically so risky-3 could trade through
`require_bearish_fill_bar`) is empirically **dead on the live path** -- `fleet_live.py` calls
only `plan_all`/`_plan_from_strategies`, which never calls `_effective_passed` (the only
function that reads `hard_skip_verdicts`). Confirmed: a `SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY`
tick at a score above risky-3's own peak still HOLDS on risky-3, while risky-1's full-send
lane enters the identical tick. This makes risky-1's full-send lane the *only* fleet
mechanism currently capable of trading a cohort-vetoed tick, on *any* arm -- independent
confirmation it is not redundant "learning rate" cosmetics. Pinned by
`test_risky3_hard_skip_override_is_currently_not_consulted_by_plan_all`; a follow-up task to
wire `_effective_passed` into `_plan_from_strategies` should be spawned separately rather
than rushed into this fire.

---
_Source: independent audit, 2026-08-02. Raw JSON:
[`fleet-strike-tier-atm-2026-08-02.json`](fleet-strike-tier-atm-2026-08-02.json)._

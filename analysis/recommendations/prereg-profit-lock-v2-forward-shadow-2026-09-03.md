# PRE-REGISTRATION — PROFIT-LOCK V2 FORWARD SHADOW, 2026-09-03

**Status: FROZEN before any forward data accrues.** `FORWARD_START_DATE = "2026-09-03"` in
`setup/scripts/profit_lock_v2_shadow.py` is this build's own date — the first row this
instrument can ever mark `in_sample=False` (genuinely forward, not-yet-seen) is dated on or
after the day this freeze lands. Every row this module writes on its FIRST run (scored
against `analysis/entry-quality/entry-quality-ledger.json`'s existing 2026-06-26..2026-09-02
population) is marked `in_sample=True` and is a DISCLOSED PRIOR, not forward evidence — see
§7 for those numbers, measured and published in this same freeze so nothing is quietly
cherry-picked after the fact.

Task: F1 profit-lock-v2-shadow (filed 2026-09-03T11:20 ET). Descends from
`analysis/deep-research/2026-09-03-money/profit-lock-scope.md` (hypothesis H4) and
`analysis/recommendations/profit-lock-arm-scope-prereg-2026-08-06.json` (the original,
FROZEN, never-shipped arm-scope prereg).

---

## 1. What is being judged

`profit_lock_arm_scope='full'` (arm the pre-TP1 chandelier trail on favorable excursion
instead of only after TP1 fires — see `automation/state/fleet/exit_manager.py`'s own
`ARM_SCOPE_FULL` comment) — the SAME mechanism H4 already measured — but with TWO changes
meant specifically to avoid H4's own found failure mode (truncating big winning days by
arming on the very first small favorable tick):

1. `profit_lock_arm_pct` raised from the live default **0.05** (+5% favor) to **0.20** (+20%
   favor). A real, already-shipped `exit_manager.py` knob (`ExitState.from_entry` reads
   `exit_shape['profit_lock_arm_pct']`) — no code change needed for this half, it is passed
   through the shape dict exactly like any other `ExitShape` key.
2. An ADDITIONAL **minimum time-in-trade of 10 minutes** before the pre-TP1 lock may arm.
   `exit_manager.py` has **no such knob** (confirmed by grep at build time). Implemented
   ONLY in the shadow's own walker wrapper
   (`setup/scripts/profit_lock_v2_shadow.py#_walk_exit_manager_time_gated`) by masking
   `profit_lock_arm_scope` to `'post_tp1'` on every bar before `entry_time + 10min`, then
   restoring it to `'full'` afterward — every OTHER exit_manager mechanism (TP1's own
   unconditional arm, catastrophe/structure/time stops, ribbon-flip, the post-TP1 chandelier)
   is untouched by the mask, proven by `backtest/tests/test_profit_lock_v2_shadow_2026_09_03.py`'s
   parity test against the unmodified `exit_manager_walk.walk_exit_manager`.
   **⛔ This is a SHADOW-ONLY simulation of a knob that does not exist live.** A positive
   forward verdict is permission to build the real knob and re-evaluate for shipping — not a
   ship signal on its own, and the real knob is out of scope for this task (2026-10-30+
   config-freeze-end item).

`trail_pct` is **UNCHANGED** from `canonical_shape(date)`'s own value (today's live 0.125
chandelier width) — only the arm CONDITION changes, matching H4's own control-holds-trail
design.

## 2. Why a forward shadow, not another backtest prereg on H4's population

H4's own conclusion (quoted verbatim from `profit-lock-scope.md` §11): *"A narrower candidate
(e.g., a higher arm threshold than +5%, or a ladder that only activates after some minimum
time-in-trade / minimum favorable excursion rather than the first +5% tick) is a plausible
next step but must be its own fresh pre-registration against data not yet seen by this run
... the 394-trade population here is now SEEN data for the +5%/15%-trail cell."* This module
is exactly the candidate H4 named, and this file is that fresh prereg — its DECISION (§5) is
frozen against forward data only, even though (per the same seen-data discipline this
codebase already applies elsewhere) the backfilled facts in §7 below are disclosed as a prior,
not hidden.

## 3. Population and measurement (frozen)

- **Population source:** every row in `analysis/entry-quality/entry-quality-ledger.json` whose
  `attribution=='engine'`, `is_option==True`, and `exit_qty >= qty` (fully closed) — itself
  built from `automation/state/fills-ledger.jsonl` (broker truth), EXTEND-DON'T-FORK per this
  codebase's established convention (the same source `tp1_r50_forward_shadow.py` already
  reads). Covers ALL SIX arms (safe-1/2/3, bold-2, risky-1, risky-3), not just `ribbon_ride`
  setups — 438 closed fills at freeze time, 2026-06-26..2026-09-02.
- **Per-trade CONTROL:** `canonical_shape(date)` unchanged, replayed through the production
  `exit_manager.plan_exit_actions` via `pdt_blocked_counterfactual._price_via_walker
  (walker='exit_manager', ...)` — the IDENTICAL call H4's own `money_profit_lock_scope.py`
  makes, never re-implemented.
- **Per-trade TREATMENT:** the same shape with `profit_lock_arm_scope='full'`,
  `profit_lock_arm_pct=0.20`, replayed through this module's time-gated wrapper (§1.2) with
  `min_arm_minutes=10.0`.
- **Bars:** 1-minute disk cache first (`backtest/data/highres/`, cache-only, via H4's own
  `money_profit_lock_scope.load_1min_cache_only`), falling back to the 5-minute OPRA cache.
  No network call of any kind. A trade with neither cached is skipped and counted, never
  estimated.
- **Trusted dollars:** per `WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md` and H4's own
  independent confirmation, ONLY `safe-2` individually clears the walker's
  magnitude-fidelity bar. Every other arm's `delta` is SIGN-ONLY in the ledger's
  `trusted_dollars` field and in every summary statistic — never cited as a trustworthy
  magnitude, here or downstream.
- **No look-ahead:** the walker ticks bar-by-bar strictly forward from the entry bar using
  only that trade's own recorded entry premium/qty/side and that date's canonical exit
  shape — the same convention every existing consumer of this harness uses (C6).

## 4. Forward bar (frozen — NOT softened at read time)

Both conditions required before this shadow's forward numbers may be READ as a verdict:

- **>= 20 forward trading sessions accrued** (`sessions_forward >= 20`, any arm — dates
  `>= 2026-09-03`), AND
- **>= 25 forward `safe-2` scored fills** (`safe2_trusted.n_forward >= 25` — the EXACT
  population the CI decision in §5 is computed over; a low-fire-rate cell needs its own
  adequate-power floor on the population that actually feeds its decision statistic, not
  just on session count, per this codebase's own
  `GATE-DESIGN-FIXED-CALENDAR-WINDOWS-STARVE-LOW-FIRE-RATE-KNOBS` lesson).

Below the bar the summary's `status` is `ARMED_AWAITING_FILLS` (zero forward rows) or
`ACCRUING` (some forward rows, bar not yet met) and carries no ship/kill signal.

## 5. Decision rule (frozen — cannot be softened after data starts arriving)

Once the bar in §4 is met, this candidate becomes a **ship-candidate** for a real
ratification pass ONLY if **ALL FOUR** hold:

1. **`safe2_forward_ci_lower_gt_zero`** — the 2.5th-percentile of a bootstrap (5,000
   resamples, same methodology as H4's own `bootstrap_ci`) over the FORWARD-ONLY `safe-2`
   per-trade `delta` is strictly positive.
2. **`recent_quarter_delta_ge_zero`** — the chronological last-quartile split over ALL
   accrued `safe-2` rows (in-sample + forward combined, generalizing H4's own Q4 recency
   check as forward data absorbs more of the quarter over time) is `>= 0`. This is the
   SAME recency-stability check H4's own §6 already applied and failed on the plain +5%
   cell (Q4 = -$327.45) — this candidate must not repeat that failure.
3. **`four_big_days_all_ge_zero`** — safe-2's total delta on EACH of the four named days
   (2026-08-06, 08-13, 08-27, 08-28) is `>= 0`. These are fixed, already-measured
   (`in_sample=True`) facts — see §7 for their current values — but remain part of the
   decision because H4's own failure mode was specifically these days getting truncated to
   $0; a candidate that still hurts them has not fixed the problem H4 found, regardless of
   what the forward CI says.
4. **`runner_08_04_delta_ge_zero`** — safe-2's delta on the 2026-08-04
   `SPY260804C00769000` runner (the exact trade the ORIGINAL 2026-08-06 prereg named as the
   highest-risk anchor) is `>= 0`. Also already-measured (§7).

Any single failure = **the evidence does not support shipping this candidate**, full stop.
Reaching the bar in §4 is permission to READ this verdict, never to ship it — and per §6,
nothing ships before 2026-10-30 regardless of the read.

## 6. What this instrument is not, and the SEEN-DATA disclosure

Descriptive and shadow-only. It flips no live knob (`profit_lock_arm_scope` stays
`'post_tp1'` in `automation/state/fleet/strategies.py` throughout accrual — this module never
imports that file for writing, only `canonical_shape`/`ExitState.from_entry` for READING the
live baseline), places no order, and is never itself sufficient to ship. **Nothing ships
before 2026-10-30 (config freeze).** Even setting the freeze date aside: this candidate
changes an EXIT (arguably a risk reduction, not a new entry risk), but the `profit_lock_arm_pct
=0.20` / 10-minute-gate CELL tested against the backfilled population in §7 is SEEN data the
moment this file is committed — exactly the same caveat H4's own +5%/15%-trail cell carried
by the time it was reported. Only the forward-only statistic in decision condition 1 (§5) is
genuinely un-seen at freeze time; conditions 2–4 are re-confirmations of an already-known
fact about this exact cell, disclosed and re-measured every run, never presented as fresh
evidence.

## 7. Backfill (in-sample prior), measured and disclosed AT FREEZE TIME

Full population: 438/438 closed engine fills scored (0 skipped — 1-minute cache covered
every trade this run), 2026-06-26..2026-09-02, 44 sessions.

| Arm | n | trusted | Σcontrol | Σtreatment | Σdelta |
|---|--:|:--:|--:|--:|--:|
| safe-2 | 103 | **YES** | -268.60 | -852.95 | **-584.35** |
| bold-2 | 49 | sign-only | -299.70 | 654.15 | +953.85 |
| risky-1 | 90 | sign-only | -1115.00 | 848.65 | +1963.65 |
| risky-3 | 103 | sign-only | 7378.70 | 4223.60 | -3155.10 |
| safe-1 | 27 | sign-only | -186.40 | -149.80 | +36.60 |
| safe-3 | 66 | sign-only | -206.10 | 1447.75 | +1653.85 |

**safe-2 (the only trusted arm) is net NEGATIVE on the backfill at this candidate's exact
parameterization** (-$584.35/103 trades) — WORSE than H4's own plain +5% cell, which was
net POSITIVE (+$2,578.41/88 trades) on an overlapping population. This is an honest,
expected trade-off of raising the arm threshold: fewer trades ever clear +20% favor, so
fewer orphan-band rescues happen, while the mechanism still costs whatever it costs on the
trades that DO clear it and then reverse. **This backfill number is disclosed, not
favorable, and is not hidden because it disagrees with the hypothesis.**

Recency check (chronological last quartile, safe-2, all-time): n=25,
2026-08-14..2026-09-02, **delta = -$735.25** — also negative, also worse than H4's own Q4
(-$327.45).

Four named big days (safe-2, trusted):

| Date | n | delta |
|---|--:|--:|
| 2026-08-06 | 2 | $0.00 |
| 2026-08-13 | 4 | +$55.40 |
| 2026-08-27 | 2 | **-$675.50** |
| 2026-08-28 | 2 | $0.00 |

`all_ge_zero = False` — 08-27 is still hurt, and by MORE than H4's own +5% cell hurt it
(-$318.35 there vs -$675.50 here). The higher arm threshold did not fix this day; it is a
different, not obviously better, failure shape on the same day.

08-04 runner (safe-2, `SPY260804C00769000`, the ORIGINAL 2026-08-06 prereg's named anchor):
**delta = $0.00** — unchanged, because TP1 already fired (at 12:something ET, well past the
10-minute mask) before the trail could arm early under EITHER scope, exactly matching H4's
own "08-04 bonus check" finding on the plain +5% cell. This one condition currently passes
(`runner_08_04_delta_ge_zero = True`); the other three (§5 conditions 2–4, using the
backfill in place of forward-CI for condition 1's stand-in) currently do NOT.

**Reading these numbers honestly: at freeze time, this exact candidate parameterization
(arm=+20%, 10-min gate) looks WORSE on the backfill than H4's plain +5% cell did, on the one
arm this codebase trusts.** This prereg does not pre-judge the forward result from that —
the backfill is a different (and, per §6, already-seen) statistical question from the
forward one — but it is recorded here, unedited, so nobody reads only a rosy summary later.
A forward result that reverses this backfilled sign would itself be worth a `/fable-too-good`
pass before trusting it.

## 8. Build step (structured, for machine reference)

```json
{
  "build_step": {
    "id": "F1-profit-lock-v2-shadow",
    "descends_from": ["analysis/deep-research/2026-09-03-money/profit-lock-scope.md#H4",
                       "analysis/recommendations/profit-lock-arm-scope-prereg-2026-08-06.json"],
    "frozen_date": "2026-09-03",
    "forward_start_date": "2026-09-03",
    "backfill": "one-time, disclosed in_sample=true prior -- see section 7",
    "treatment": {
      "profit_lock_arm_scope": "full",
      "profit_lock_arm_pct": 0.20,
      "min_time_in_trade_minutes": 10.0,
      "min_time_in_trade_implementation": "walker-wrapper mask only -- no live exit_manager.py knob",
      "trail_pct": "unchanged"
    },
    "population": {"source": "analysis/entry-quality/entry-quality-ledger.json",
                    "scope": "all engine-attributed closed option fills, all 6 arms"},
    "trusted_arms": ["safe-2"],
    "bar": {"min_forward_sessions": 20, "min_forward_safe2_scored": 25},
    "decision_rule": {
      "safe2_forward_ci_lower_gt_zero": true,
      "recent_quarter_delta_ge_zero": true,
      "four_big_days_all_ge_zero": true,
      "runner_08_04_delta_ge_zero": true,
      "all_required": true,
      "softenable": false
    },
    "artifacts": {
      "ledger": "analysis/recommendations/profit-lock-v2-shadow-ledger.jsonl",
      "summary": "analysis/recommendations/profit-lock-v2-shadow-summary.json",
      "builder": "setup/scripts/profit_lock_v2_shadow.py",
      "scheduled_task": "Gamma_ProfitLockV2Shadow",
      "install_script": "setup/install-profit-lock-v2-shadow.ps1"
    },
    "do_not": [
      "ship anything before 2026-10-30 (config freeze)",
      "treat the backfill (section 7) as forward evidence",
      "soften the decision rule in section 5 after forward data starts arriving",
      "build the real min-time-in-trade exit_manager.py knob as part of this task"
    ]
  }
}
```

## 9. Revert

Whole instrument, one shot: `Unregister-ScheduledTask -TaskName Gamma_ProfitLockV2Shadow
-Confirm:$false` + delete `setup/scripts/profit_lock_v2_shadow.py` +
`setup/install-profit-lock-v2-shadow.ps1` + this file +
`analysis/recommendations/profit-lock-v2-shadow-ledger.jsonl` +
`analysis/recommendations/profit-lock-v2-shadow-summary.json`. Nothing on the trading path
depends on this instrument — it is an analysis-only leaf, exactly like
`Gamma_Tp1R50ForwardShadow` / `Gamma_LadderRungShadow`.

# PRE-REGISTRATION — TRENDLINE-TIGHT-EXIT SHADOW, 2026-09-03

**Status: FROZEN before any forward data accrues.** Commit timestamp of this file is the
freeze proof. `setup/scripts/trendline_tight_exit_shadow.py` (the ledger/summary builder)
and `setup/install-trendline-tight-exit-shadow.ps1` (the scheduled task) are committed
alongside this file, but `ACCRUAL_START_DATE = "2026-09-03"` — the forward clock's own build
date — means the first row this instrument can ever write is dated on or after the day this
freeze lands. Dry run at freeze time (today's session, pre-open) correctly reported
`n:0`/`status:ARMED_AWAITING_FILLS` — no trade this prereg could judge has happened yet.

Queue item: `TRENDLINE-TIGHT-EXIT-ACCRETE` (MED, "watch candidate from the kitchen's best
near-miss", `automation/overnight/queue.md`).

---

## 1. What is being judged

Kitchen cell `A6_T-TIGHT_TR-TIGHT` (`analysis/kitchen/class-conditional-exits-episodes.json`,
`analysis/kitchen/CLASS-CONDITIONAL-EXITS-2026-07-23.md`): TRENDLINE-tier `premium_stop_pct`
tightened **-20% → -12%** and the post-TP1 chandelier `trail_pct` tightened **15% → 10%**.
Every other exit knob (`tp1_premium_pct`, `tp1_qty_fraction`, `profit_lock_mode`,
`profit_lock_arm_pct`, `runner_target_pct`, `catastrophe_stop_pct`, `pre_tp1_*`) is
byte-identical to the shipped `ribbon_ride` cell.

That cell was the night's **ONLY 4/4-gate cell** and the **best day-WR of any candidate**
(67.4%, n=95 real-fills-derived episodes) — but after the 83-cell portfolio-wide
Benjamini-Hochberg correction it lands at **q=0.31** (its own-lane q=0.066 was
homework-self-grading — correcting only within its own 13-cell family hides that 82 OTHER
cells were tested that same night). **NOT a ship.** It IS the best-evidenced exit lead since
SS-B, which is why it gets a forward accrual clock instead of being discarded.

## 2. Why a forward shadow

A retrospective backtest population cannot be re-asked without either re-specifying the
83-cell BH correction after seeing which cell it blocked (forking-paths) or drawing a second
population from the SAME 190-trade `RIDE_THE_RIBBON` full-history replay that already
produced this q-value (contaminated — that answer is already known). The only clean path is
to judge the knob on data nobody has seen yet: every real trendline-class fill going
forward. This file freezes that bar before any of that data exists.

## 3. Population and measurement (frozen)

- **Class filter (causal-at-entry proxy, not the backtest tier directly):** a closed engine
  fill counts as trendline-class if `setup_taxonomy.canonical_setup(setup)` is
  `BEARISH_REJECTION_RIDE_THE_RIBBON` or `BULLISH_RECLAIM_RIDE_THE_RIBBON` (canonicalization
  catches the pre-rename `BULLISH_RECLAIM` alias too) **AND** `trigger_level is None`. This
  reuses the EXACT mechanism `class_conditional_exits_ab.py`'s own preflight verified on the
  backtest population: "ALL 124 TRENDLINE-tier trades have trigger_level=None … ALL 66
  non-TRENDLINE trades … have trigger_level set" — a 100%/0% causal-at-entry split. Real
  fills carry `trigger_level` (entry-quality-ledger.json enrichment) but not the backtest-only
  `triggers_fired` list the original tier classifier needs, so this proxy is the faithful
  real-fills equivalent, not an invented substitute.
- **Scope:** `is_option` AND `attribution=="engine"` AND `side=="buy"` AND fully closed
  (`exit_qty >= qty`) AND `date_et >= ACCRUAL_START_DATE`.
- **Shadow exit shape:** `dict(strategies.by_name("ribbon_ride").exit.to_dict())` with ONLY
  `premium_stop_pct=-0.12` and `trail_pct=0.10` overridden — the SAME single global control
  cell A6 itself used, not a per-arm resolution. Per-arm `exit_patch` differences (safe-3:
  `profit_lock_mode=trailing`; risky-1: `tp1_premium_pct=0.5`; risky-3: `stop_mode=premium`)
  are **not** modeled in the shadow arm — mixing them in would silently blend a second
  untested variable into cell A6's specific read. `stop_mode`/`structure_stop_enabled` are
  inert for this population by construction (`trigger_level is None` always resolves premium
  mode regardless — `exit_manager.ExitState.from_entry`).
- **Replay:** `backtest/lib/exit_manager_walk.walk_exit_manager` over the trade's own cached
  OPRA bars (`option_pricing_real.load_contract_bars`, disk cache only, never fetched).
  Walker defaults (`frame`, `exit_slippage`, `all_exits_market`) are left untouched.
- **Per-trade delta:** `recorded_exit.pnl` is the REAL broker-truth dollar P&L already on the
  enriched ledger (`entry-quality-ledger.json events[].pnl`). `shadow_exit.pnl` is the
  RE-SIMULATED walk under the tightened shape. `delta_pnl = shadow_exit.pnl - recorded_exit
  .pnl`. `sign_agree = (sign(shadow_exit.pnl) == sign(recorded_exit.pnl))`.
- **⛔ SIGN-ONLY CAVEAT ON DOLLARS (frozen, not softenable):** `recorded_exit` is real and
  `shadow_exit` is simulated — this pair is NOT apples-to-apples the way the paired
  simulated-vs-simulated deltas in `stop_mode_shadow_ledger.py` / `tp1_r50_forward_shadow.py`
  are. Option-bar-resolution effects and cached-quote-vs-actual-fill spread (measured
  elsewhere in this codebase at up to $1,821.75 aggregate one-directional,
  `OPTION-BAR-RESOLUTION-BIAS-2026-08-02`) contaminate `delta_pnl`'s MAGNITUDE. Its SIGN
  (did tightening help or hurt this specific trade) is the trustworthy read. Every summary
  this instrument writes carries a `dollar_caveat` field restating this; the decision rule
  in §5 leans on `sign_agreement` as an independent, sign-safe gate.
- **Missing bars:** a trendline-class fill whose OPRA bars are not cached is recorded with
  `status="SKIPPED_NO_BARS"` — never silently dropped, never backfilled by a network fetch
  from this instrument (the OPRA cache is owned by another agent).
- **No look-ahead, no backfill:** `ACCRUAL_START_DATE = "2026-09-03"`. Nothing before this
  build's own date is ever scored, by construction.

## 4. Forward bar (frozen — NOT softened at read time)

Both conditions required before this shadow's numbers may be READ as a verdict:

- **>= 20 trading days accrued** (`days_accrued >= 20`, counted over SCORED rows only), AND
- **>= 25 trendline-class fills actually scored** (`n_scored >= 25` — a low-fire-rate class
  needs its own adequate-power floor, the same lesson `GATE-DESIGN-FIXED-CALENDAR-WINDOWS-
  STARVE-LOW-FIRE-RATE-KNOBS` generalized).

Below the bar the instrument's status is `ACCRUING` and produces NO ship/kill signal —
`days_to_bar` / `trendline_to_bar` name the remaining distance every night.

## 5. Decision rule (frozen — the bar cannot be softened after data starts arriving)

Once the bar in §4 is met, the tightened TRENDLINE exit (-12% stop / 10% trail) becomes a
**ship-candidate** for a real ratification pass ONLY if ALL THREE hold on the accrued
forward ledger:

1. **`session_clustered_ci.ci_lower_2.5 > 0`** — the 2.5th-percentile of a day-clustered
   percentile bootstrap (resampling trading DAYS with replacement, matching
   `go_live_gate.bootstrap_pf_ci`'s methodology) over the per-trade `delta_pnl` mean is
   strictly positive. Reported and gated, but read through the §3 sign-only caveat — a
   borderline CI read should not be over-trusted on magnitude alone.
2. **`top3_share < 0.50`** — the 3 largest-magnitude per-trade deltas explain less than half
   of total `|delta|`. A verdict carried by 1-2 trades is not a verdict (the same
   concentration failure mode `stop_mode_shadow_ledger.py` / `tp1_r50_forward_shadow.py`
   both guard against).
3. **`sign_agreement >= 0.85`** — the tightened-shadow exit lands on the same win/loss side
   as the real recorded trade at least 85% of the time. This is the SIGN-SAFE gate the §3
   caveat exists to make load-bearing: it does not depend on the recorded-vs-simulated
   dollar wedge at all.

Any single failure = **the forward evidence does not support shipping** the tightened
TRENDLINE exit, full stop — reaching the bar is permission to READ the verdict, never to
ship regardless of the read, and this decision rule is not re-opened after the fact.

## 6. What this instrument is not

Descriptive and shadow-only. It writes a ledger + a summary, flips no knob
(`premium_stop_pct`/`trail_pct` stay `-0.20`/`0.15` in `strategies.py` throughout accrual),
proposes no change, and places no order. It is never itself sufficient to ship the knob — a
positive verdict here is the PERMISSION for a separate, later ratification decision to cite
this ledger as its forward evidence base, the same two-step contract every sibling shadow
clock in this codebase uses.

## 7. Build step (structured, for machine reference)

```json
{
  "build_step": {
    "id": "TRENDLINE-TIGHT-EXIT-ACCRETE",
    "queue_source": "automation/overnight/queue.md",
    "origin": "kitchen cell A6_T-TIGHT_TR-TIGHT, analysis/kitchen/class-conditional-exits-episodes.json",
    "frozen_date": "2026-09-03",
    "accrual_start_date": "2026-09-03",
    "backfill": "none -- forward-only by construction",
    "class_filter": {
      "setups": ["BEARISH_REJECTION_RIDE_THE_RIBBON", "BULLISH_RECLAIM_RIDE_THE_RIBBON"],
      "canonicalized_via": "backtest/lib/setup_taxonomy.canonical_setup",
      "trigger_level": null,
      "proxy_source": "class_conditional_exits_ab.py preflight-verified 100%/0% trigger_level<->TRENDLINE-tier split"
    },
    "tightened_knobs": {
      "premium_stop_pct": -0.12,
      "trail_pct": 0.10,
      "base": "control_shape = strategies.by_name('ribbon_ride').exit.to_dict(), NOT per-arm"
    },
    "bar": {
      "min_trading_days": 20,
      "min_trendline_scored": 25
    },
    "decision_rule": {
      "ci_lower_2p5_gt_zero": true,
      "top3_share_lt": 0.50,
      "sign_agreement_gte": 0.85,
      "all_required": true,
      "softenable": false
    },
    "dollar_caveat": "recorded_exit is real broker-truth; shadow_exit is a re-simulation -- delta_pnl sign is trustworthy, magnitude is not sizing-grade",
    "artifacts": {
      "ledger": "analysis/recommendations/trendline-tight-exit-shadow-ledger.jsonl",
      "summary": "analysis/recommendations/trendline-tight-exit-shadow-summary.json",
      "builder": "setup/scripts/trendline_tight_exit_shadow.py",
      "scheduled_task": "Gamma_TrendlineTightExitShadow",
      "install_script": "setup/install-trendline-tight-exit-shadow.ps1"
    },
    "do_not": [
      "re-spec the 83-cell BH correction to let this cell pass",
      "draw a second population from the same 190-trade RIDE_THE_RIBBON replay",
      "model per-arm exit_patch overrides into the shadow arm (blends a second variable into cell A6's read)",
      "soften the decision rule in section 5 after data starts arriving",
      "treat delta_pnl magnitude as sizing-grade evidence (section 3 caveat)"
    ]
  }
}
```

## 8. Revert

Whole instrument, one shot: `Unregister-ScheduledTask -TaskName
Gamma_TrendlineTightExitShadow -Confirm:$false` + delete
`setup/scripts/trendline_tight_exit_shadow.py` +
`setup/install-trendline-tight-exit-shadow.ps1` + this file. Nothing on the trading path
depends on this instrument — it is an analysis-only leaf, exactly like
`Gamma_Tp1R50ForwardShadow` / `Gamma_LadderRungShadow`.

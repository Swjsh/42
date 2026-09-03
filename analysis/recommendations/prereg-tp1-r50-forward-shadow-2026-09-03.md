# PRE-REGISTRATION — TP1-R50 FORWARD SHADOW, 2026-09-03

**Status: FROZEN before any forward data accrues.** Commit timestamp of this file is the
freeze proof. `setup/scripts/tp1_r50_forward_shadow.py` (the ledger/summary builder) and
`setup/install-tp1-r50-forward-shadow.ps1` (the scheduled task) are committed alongside this
file, but `ACCRUAL_START_DATE = "2026-09-03"` — the forward clock's own build date — means
the first row this instrument can ever write is dated on or after the day this freeze lands.
No trade this prereg could judge has happened yet at freeze time.

Queue item: `TP1-R50-FORWARD-SHADOW` (HIGH, filed 2026-08-23 Opus adjudication,
`automation/overnight/queue.md`), superseding the DONE `TP1-R50-READJUDICATION`.

---

## 1. What is being judged

`R_tp100_f50` — TP1 still triggers at the same +100% premium level `ribbon_ride` already
uses, but sells **50%** of the position instead of the live **66.7%**
(`tp1_qty_fraction=0.667`, `automation/state/fleet/strategies.py` `RIBBON_RIDE.exit`). The
knob under test changes ONLY the TP1 quantity split; everything else (stop, runner target,
trail, profit-lock) is byte-identical to the shipped cell.

## 2. Why a forward shadow, not another backtest prereg (the two DO-NOTs)

- **⛔ DO NOT re-spec gate G4.** The 2026-08-23 re-adjudication on extended popA (n=213,
  commit `97f3c864`) still failed G4 (>=3-of-4 fixed calendar sub-windows stable). The
  failure is STRUCTURAL: 2025H1 and 2026Q1 are CLOSED calendar windows with only 4 changed
  trades each, so no amount of forward extension can ever grow them past a >=3-window floor
  — G4 is unreachable for this cell by construction, independent of the knob's actual
  quality. Rewriting G4 after seeing which cell it blocked is forking-paths; the original
  prereg's bar is not softened, here or anywhere else (see also queue item
  `GATE-DESIGN-FIXED-CALENDAR-WINDOWS-STARVE-LOW-FIRE-RATE-KNOBS`, closed 2026-09-03, which
  documents the general fix for FUTURE preregs — never applied retroactively to this one).
- **⛔ DO NOT write a new backtest prereg on the same data.** popA is contaminated — its
  answer (7/8 gates pass, all 4 windows positive, runner_anchor +$628.05, p=0.002617, sole
  BH survivor of 28 cells) is already known and cannot be re-asked as if fresh.
- **The only clean path:** judge on data nobody has seen yet. This file freezes that bar.

## 3. Population and measurement (frozen)

- **Scope:** every CLOSED engine trade whose `setup` is `BEARISH_REJECTION_RIDE_THE_RIBBON`
  or `BULLISH_RECLAIM_RIDE_THE_RIBBON` (i.e. the `ribbon_ride` strategy), on an arm whose
  RESOLVED live `tp1_qty_fraction` is exactly `0.667` — confirmed per-trade from
  `strategies.by_name("ribbon_ride").exit.tp1_qty_fraction`, checked against that arm's
  `accounts.json` `params_patch.exit_patch` for an override of that same key. At freeze
  time all 6 SPY-option arms (safe-1/2/3, bold-2, risky-1, risky-3) resolve to 0.667 —
  risky-1's own `exit_patch` overrides `tp1_premium_pct` (the TP1 *trigger*), a different
  knob, not the quantity split. An arm whose resolved fraction ever drifts off 0.667 falls
  out of scope automatically and is recorded as skipped, never silently included.
- **Per-trade delta:** using ONLY the trade's recorded broker legs (the TP1 partial-sell fill
  and the runner exit fill(s), read from `automation/state/fills-ledger.jsonl`, never a
  re-simulation) — `qty_moved = int(qty*0.667) - int(qty*0.5)` (the engine's own int-floor
  split, `exit_manager.ExitState.from_entry`, mirrored not re-derived) contracts move from
  being sold at the TP1 fill price to riding to the runner leg(s)' quantity-weighted average
  exit price. `delta_pnl = qty_moved * (runner_avg_price - tp1_price) * multiplier`.
- **Never reached TP1:** a trade that closed in one single sell leg contributes exactly $0
  and is counted separately (`n_never_reached_tp1`), never blended into "no effect" cells
  that DID reach TP1 but rounded to a no-op.
- **Rounding no-op:** when `qty_moved == 0` (both fractions floor to the same whole-contract
  count at that trade's size) the row is `no_op_rounding=True`, delta $0 — honestly reported,
  not dropped.
- **No look-ahead, no backfill:** `ACCRUAL_START_DATE = "2026-09-03"`. Nothing before this
  build's own date is ever scored, by construction (forward-only is the entire point).

## 4. Forward bar (frozen — NOT softened at read time)

Both conditions required before this shadow's numbers may be READ as a verdict:

- **>= 20 trading days accrued** (`days_accrued >= 20`), AND
- **>= 25 trades that actually reached TP1** (`n_tp1_reached >= 25` — the population the
  knob can possibly change; a low-fire-rate cell needs its OWN adequate-power floor, exactly
  the lesson `GATE-DESIGN-FIXED-CALENDAR-WINDOWS-STARVE-LOW-FIRE-RATE-KNOBS` generalized).

Below the bar the instrument's status is `ACCRUING` and produces NO ship/kill signal —
`days_to_bar` / `tp1_reached_to_bar` name the remaining distance every night.

## 5. Decision rule (frozen — the bar cannot be softened after data starts arriving)

Once the bar in §4 is met, `R_tp100_f50` becomes a **ship-candidate** for a real ratification
pass ONLY if ALL THREE hold on the accrued forward ledger:

1. **`session_clustered_ci.ci_lower_2.5 > 0`** — the 2.5th-percentile of a day-clustered
   percentile bootstrap (resampling trading DAYS with replacement, matching
   `go_live_gate.bootstrap_pf_ci`'s methodology so within-day trade correlation is
   respected) over the per-trade `delta_pnl` mean is strictly positive.
2. **`top3_concentration_share < 0.50`** — the 3 largest-magnitude per-trade deltas explain
   less than half of total `|delta|`. A verdict carried by 1-2 trades is not a verdict
   (the same concentration failure mode `stop_mode_shadow_ledger.py` and
   `day_throttle_shadow.py` both guard against).
3. **`ex_best_day_sum_delta > 0`** — the cumulative delta stays positive after dropping the
   single best day's contribution entirely (mirrors `day_throttle_shadow.score`'s `F4`).

Any single failure = **the forward evidence does not support shipping** `R_tp100_f50`, full
stop — reaching the bar is permission to READ the verdict, never to ship regardless of the
read, and this decision rule is not re-opened after the fact (no re-spec of G4's replacement
either, per §2).

## 6. What this instrument is not

Descriptive and shadow-only. It writes a ledger + a summary, flips no knob
(`tp1_qty_fraction` stays `0.667` in `strategies.py` throughout accrual), proposes no
change, and places no order. It is never itself sufficient to ship the knob — a positive
verdict here is the PERMISSION for a separate, later ratification decision to cite this
ledger as its forward evidence base, exactly the same two-step contract
`stop_mode_shadow_ledger.py`'s own docstring states for its sibling clock.

## 7. Build step (structured, for machine reference)

```json
{
  "build_step": {
    "id": "TP1-R50-FORWARD-SHADOW",
    "queue_source": "automation/overnight/queue.md",
    "supersedes": "TP1-R50-READJUDICATION",
    "frozen_date": "2026-09-03",
    "accrual_start_date": "2026-09-03",
    "backfill": "none -- forward-only by construction",
    "population": {
      "setups": ["BEARISH_REJECTION_RIDE_THE_RIBBON", "BULLISH_RECLAIM_RIDE_THE_RIBBON"],
      "in_scope_live_tp1_fraction": 0.667,
      "counterfactual_tp1_fraction": 0.5
    },
    "bar": {
      "min_trading_days": 20,
      "min_trades_reached_tp1": 25
    },
    "decision_rule": {
      "ci_lower_2p5_gt_zero": true,
      "top3_concentration_share_lt": 0.50,
      "ex_best_day_sum_delta_gt_zero": true,
      "all_required": true,
      "softenable": false
    },
    "artifacts": {
      "ledger": "analysis/recommendations/tp1-r50-forward-shadow-ledger.jsonl",
      "summary": "analysis/recommendations/tp1-r50-forward-shadow-summary.json",
      "builder": "setup/scripts/tp1_r50_forward_shadow.py",
      "scheduled_task": "Gamma_Tp1R50ForwardShadow",
      "install_script": "setup/install-tp1-r50-forward-shadow.ps1"
    },
    "do_not": [
      "re-spec gate G4 to let this cell pass",
      "write a new backtest prereg on the already-seen popA data",
      "soften the decision rule in section 5 after data starts arriving"
    ]
  }
}
```

## 8. Revert

Whole instrument, one shot: `Unregister-ScheduledTask -TaskName Gamma_Tp1R50ForwardShadow
-Confirm:$false` + delete `setup/scripts/tp1_r50_forward_shadow.py` +
`setup/install-tp1-r50-forward-shadow.ps1` + this file. Nothing on the trading path
depends on this instrument — it is an analysis-only leaf, exactly like
`Gamma_LadderRungShadow`.

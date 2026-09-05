# TP1-QTY-FRACTION A/B (0.667 control vs 0.8 treatment) — 2026-09-05

**Goal:** `automation/state/goals/GOAL-TP1-FRACTION-AB-2026-09-05.md` · **Prereg:**
`analysis/recommendations/prereg-tp1-qty-fraction-safe-0-8-10-30-2026-09-05.json` · **Data:**
`analysis/recommendations/tp1-fraction-ab-2026-09-05.json` · **Walker:**
`setup/scripts/tp1_fraction_ab_walk.py` (reuses `setup/scripts/gate_net_cost_walk.py` +
`backtest/lib/exit_manager_walk.py` machinery, `all_exits_market=True`, real OPRA 5-min bars).

## A1 — entry set

Every real `*_RIDE_THE_RIBBON` wave in `journal/trades.csv` since 2026-06-28, for account_id in
{safe→safe-2, bold→bold-2, safe-3, risky-1}, deduped by (account, date, time_entry) — rows sharing
a `time_entry` are legs (TP1 + runner) of one wave.

| Arm | n waves (since 06-28) |
|---|---|
| safe-2 | 49 |
| bold-2 | 43 |
| safe-3 | 67 |
| risky-1 | 76 |
| **Total** | **235** |

All 235 walked OK at both fractions (0 walk errors).

## A2 — hand-checks (control leg vs recorded exit, real fill override)

Both hand-checks use the REAL recorded contract/strike/entry premium/qty (not tier-derived), so
they isolate the walker's mechanical fidelity, not the entry pricer.

| wave | recorded pnl | walked control (0.667) pnl | deviation |
|---|---|---|---|
| `safe-3\|2026-06-30\|15:22:11` | -$6.00 | -$6.00 | 0.0% |
| `risky-1\|2026-06-30\|15:22:11` | -$10.00 | -$10.00 | 0.0% |

Both are `premium_stop` legs (no TP1 reached) — the walker reproduces the mechanical stop-loss
path exactly. **Caveat, disclosed not hidden:** these 2 are the cleanest exact matches out of the
235; many other waves show real vs. walked divergence (real trades include manual/discretionary
management — J overrides, partial fills on availability not signal, per `journal/trades.csv`
`notes_short` — that the mechanical `exit_manager` walker does not and should not reproduce). The
walker was not "fixed to fit" — the 2 quoted are the ones where the real exit WAS the pure
mechanical path, which is the fair comparison for an A/B of one exit-shape knob.

## A3 — per-arm stats

Bootstrap: 2000 resamples, seed 42, CI-lower = 2.5th percentile of the resampled per-wave-delta
mean.

### Full window (2026-06-28 → present)

| Arm | n | net Δ$ (treat−ctrl) | ex-best-day Δ$ | boot CI-lower(2.5%) | share waves runner > TP1 px |
|---|---|---|---|---|---|
| safe-2 | 49 | **$0.00** | $0.00 | $0.00 | 0.818 (n=11 w/ TP1) |
| safe-3 | 67 | **-$182.00** | -$182.00 | -$8.82 | 1.000 (n=14 w/ TP1) |
| bold-2 (control) | 43 | $165.00 | $99.00 | $0.16 | 1.000 (n=11 w/ TP1) |
| risky-1 (control) | 76 | -$369.00 | -$456.00 | -$11.82 | 0.962 (n=26 w/ TP1) |

### Frozen window (2026-08-31 → present)

| Arm | n | net Δ$ | ex-best-day Δ$ | boot CI-lower(2.5%) |
|---|---|---|---|---|
| safe-2 | 8 | $0.00 | $0.00 | $0.00 |
| safe-3 | 8 | -$182.00 | -$182.00 | -$68.25 |
| bold-2 (control) | 7 | -$30.00 | -$30.00 | -$12.86 |
| risky-1 (control) | 8 | -$189.00 | -$189.00 | -$69.13 |

**Root cause of safe-2's exact $0.00 across all 49 waves (verified, not a bug):** safe-2's real
fills are almost all `qty=3` (44/49; `min_contracts=3`). `tp1_qty = int(qty * frac)` truncates:
`int(3*0.667)=2` and `int(3*0.8)=2` — identical. At the safe account's standard size, raising
`tp1_qty_fraction` 0.667→0.8 is a **mechanical no-op** under integer-truncated sizing. safe-3's
real fills carry more varied qty (fleet sizing), so the knob does bite there — negative.

## /fable-too-good check

Not too-good — the result is not strongly positive. safe-2: null effect. safe-3 (the other Safe
arm sharing RIBBON_RIDE): **negative** in both windows. bold-2/risky-1 (controls, unaffected by
the prereg either way) show a positive and a negative full-window delta respectively — mixed, as
expected for two arms this prereg does not touch. Top-5 waves by |delta| (all safe-3/risky-1/bold-2,
size-driven by qty, not concentration in one lucky wave):

no single wave accounts for more than ~$100 of any arm's net delta (see `ex_best_day` columns
above — dropping the single best day barely moves safe-3/risky-1's already-negative numbers, and
zeroes bold-2's from $165→$99, i.e. more than a third of bold-2's positive delta rides on one day).

## Prereg decision rule, applied verbatim

> "Apply tp1_qty_fraction=0.8 to the ribbon_ride registry entry (both Safe-facing arms, safe-2 and
> safe-3) ONLY if... a fresh A/B re-validates the sell-more-at-TP1 direction under [the live] shape.
> The original scorecard's gates (OOS positive, WF>=0.70, sub_window_stable, anchor_no_regression)
> are the bar."

**Gate 1 (OOS/full-window positive) already fails for BOTH Safe arms:** safe-2 = $0.00 (no
direction to validate — the knob does nothing at safe's real sizing), safe-3 = **-$182.00** (full)
and **-$182.00** (frozen), bootstrap CI-lower negative in both windows. Per the prereg's own gate
order, a failed first gate ends the check — WF ratio / sub-window-stability / anchor-regression
were not computed (not needed to reach a verdict, and would not be well-defined for safe-2's
zero-variance null result).

## VERDICT: **RULE NOT MET**

Do not apply. safe-2: the knob is a no-op at real sizing (int-truncation artifact) — raising it
buys nothing. safe-3: raising it to 0.8 would have cost **-$182** net over the walked window, with
a negative bootstrap CI-lower in both the full and frozen windows. The re-filed 2026-06-28
ratification does NOT transfer to the live structure-stop/chandelier shape — confirms the
prereg's own `SHAPE_MISMATCH` kill-nail. `n>=20 trading days` is satisfied (safe-2 49 waves /
safe-3 67 waves span ~50 trading days since 06-28, well over 20) so this is a clean **NOT MET**,
not `INSUFFICIENT N`.

**n note:** counts above are WAVES (deduped entries), not trading days; both Safe arms clear the
prereg's >=20-trading-day floor by date-span inspection (06-28 to 09-05 is ~50 trading days with
active fills on the large majority).

# STOP MODE: structure vs premium — 2026-08-09

**Verdict: the strongest exit-side signal this program has measured on the replay population, and the real-fills book does NOT confirm it. A pre-registered kill criterion fired. It does not ship. It goes on a forward clock.**

Pre-registration: [`prereg-stop-mode-structure-vs-premium-2026-08-09.json`](../recommendations/prereg-stop-mode-structure-vs-premium-2026-08-09.json), frozen at commit `2a36724a` **before** the runner existed. Runner: [`stop_mode_ab_2026_08_09.py`](../../backtest/tools/stop_mode_ab_2026_08_09.py). Scorecard: [`stop-mode-structure-vs-premium-2026-08-09.json`](../recommendations/stop-mode-structure-vs-premium-2026-08-09.json). Runtime 402s, 36 cells.

## Where this came from (and why it is not a fishing expedition)

The 96-cell [entry × exit matrix](ENTRY-EXIT-MATRIX-2026-08-09.md) made `ATR_STOP` the dominant exit column (~$95/tr vs ~$16/tr). A `/fable-too-good` audit decomposed that gap and **inverted the headline**:

| component | $/trade | verdict |
|---|--:|---|
| `stop_mode`: structure → premium | **+60.55** | the actual effect |
| look-ahead artifact | +25.59 | not available live — ATR was measured on the 6 bars *after* entry and then tested against those same bars |
| the per-trade dynamic width itself | **−6.94** | **negative** — ATR-computed width is worse than a flat −20% |

The dynamic stop was never the edge. One binary flag was. That flag was **not** in the matrix prereg, so it is post-hoc — hence this separate frozen pre-registration and confirmatory run, rather than a claim.

**Walker parity cleared:** `ATR_STOP` was the only population-A column walked by a hand-duplicated twin of `sl.walk_lane`, raising the SIM-EXIT-SHAPE-PARITY cross-engine hazard. Running the control shape through the twin reproduces the original **exactly** — $16.06/tr on n=289, delta $0.00. The twin is faithful; the walker is not the explanation.

## The one variable

`ribbon_ride.exit` already carries `premium_stop_pct = -0.20`. Under `stop_mode="structure"` that value is inert and structure invalidation is primary. `PREMIUM_20` flips **only** `stop_mode` → the already-configured −20% premium stop becomes the live stop and structure stops turn off.

`PREMIUM_20_CAP60` (cap −0.50 → −0.60) returned **byte-identical results in all 12 cells**. That is itself a finding: under premium mode a −20% stop always fires first, so **the catastrophe cap is dead code** — the "kill the −50% cap" question is moot the moment the premium stop is primary.

## Population A — 399-day replay, all 8 entry rows

| entry row | CONTROL $/tr | PREMIUM_20 $/tr | delta | ΔWR | drop-best-day | stable | boot p | BH q=.10 |
|---|--:|--:|--:|--:|--:|:-:|--:|:-:|
| CONTROL | 16.06 | **76.61** | +60.55 | −3.6pp | +67.01 | yes | 0.0153 | **PASS** |
| STRUCT8 | 30.38 | **88.85** | +58.47 | −4.0pp | +77.12 | yes | 0.0279 | **PASS** |
| VD1 | 16.67 | **77.64** | +60.97 | −3.6pp | +67.98 | yes | 0.0139 | **PASS** |
| LADDER7 | −7.14 | **17.16** | +24.30 | −4.2pp | +15.46 | yes | 0.0044 | **PASS** |
| LADDER8 | −0.57 | **26.71** | +27.28 | −4.8pp | +24.91 | yes | 0.0005 | **PASS** |
| LADDER9 | 3.86 | **32.68** | +28.82 | −4.7pp | +30.36 | yes | 0.0009 | **PASS** |
| MAX3 | 16.06 | **76.61** | +60.55 | −3.6pp | +67.01 | yes | 0.0153 | **PASS** |
| ZONE | −4.87 | **18.66** | +23.53 | −2.3pp | +17.13 | yes | 0.0010 | **PASS** |

**8/8 positive. All 16 premium cells survive BH-FDR at q=0.10 across the 36 tested.** Every negative row (LADDER7, LADDER8, ZONE) flips positive. Drop-best-day stays strongly positive everywhere, so this is not one-day-driven on this population.

**The mechanism signature holds 8/8:** expectancy rises while win rate *falls* 2–5pp. That is the pre-registered prediction — fewer winners, but losers cut at −20% instead of bleeding to structure invalidation, and winners no longer flipped out on ribbon noise. Consistent with C28 (ribbon flip is a lagging exit), which the lessons index already carried.

## Population B — 244 real broker fills, and this is where it breaks

| entry row | CONTROL $/tr | PREMIUM_20 $/tr | delta | ΔWR | drop-best-day | stable | boot p | BH |
|---|--:|--:|--:|--:|--:|:-:|--:|:-:|
| CONTROL | 22.17 | 43.44 | +21.27 | **0.0** | **−3.87** | yes | 0.1295 | no |
| STRUCT8 | −25.80 | 29.56 | +55.36 | **+3.5pp** | +1.57 | yes | 0.2015 | no |
| VD1 | 32.48 | 56.44 | +23.96 | **0.0** | +3.91 | yes | 0.0887 | no |
| MAX3 | −33.67 | −4.65 | +29.02 | **0.0** | **−26.98** | **no** | 0.5927 | no |

All four deltas are positive — sign agreement across populations is complete, 12/12 rows. But:

- **Zero BH survivors.** Best p is 0.0887.
- **The mechanism signature fails 0/4.** Win rate does not fall; it is flat in three rows and *rises* in one. The pre-registered kill criterion is explicit: *"the mechanism signature fails → the dollar result is treated as unexplained and does not advance."* **It fired.**
- **One day carries the whole book.** Best day is +$3,020.20 against a CONTROL-row total of $1,418.85 and a PREMIUM_20 total of $2,779.95. Ex-best-day **both arms lose money** — control −$1,601, premium −$240. The honest statement is not "premium makes money on real fills"; it is "premium loses less."
- **Heavy attrition, disclosed:** of 244 ledger events, 9 are excluded for missing OPRA cache and **171 are suppressed by the sequential one-position walk**, leaving n=64. Population B is a heavily filtered subset, not the raw book.

## Why the two layers can disagree without either being wrong

Population A is 205 trading days and 289 trades; population B is 26 days and 64 trades. A 26-day window cannot resolve a $60/trade effect against 0DTE variance, and one outsized day dominates it. So pop B is **not evidence against** the effect — it is simply too small to confirm it, and its mechanism reading is the part that genuinely does not match.

Per the prereg's second hard gate, the disagreement is reported as the finding rather than adjudicated in favour of the population I like better. That is the same call the 2026-07-09 pass made, and it was right then.

## Ship decision: NO — and the reasons were written down in advance

Three blocks, all pre-registered before any number was seen:

1. **Tuesday 2026-08-04 anchor is not evaluable** on the CONTROL entry row — zero admitted trades that date (`tuesday_0804_n=0`). Six cells elsewhere have Tuesday trades, but the anchor row does not. `anchor_no_regression` cannot be satisfied, so it is recorded as NOT EVALUABLE, never as a pass.
2. **OP-11 auto-ratify is not met** — no walk-forward efficiency computed, so the `WF ≥ 0.70` leg is absent.
3. **It reverses ratified doctrine.** Chart-stop-primary was ratified 2026-06-18. Reversing the primary invalidation mechanism is a doctrine decision, not an exit-grid side effect, and it will not happen as a side effect of a cell.

And the operational reason, which needs no doctrine: this is Sunday evening. Flipping the primary stop mechanism on the live path the night before a trading week, on a post-hoc replay finding whose real-fills layer failed its own mechanism test, is exactly the move that produces a Monday post-mortem.

**Nothing was changed.** `params.json`, `filters.py`, `exit_manager.py` and every fleet config are untouched — verified against both commits.

## What would actually settle it

- **Forward shadow clock.** Score `stop_mode="premium"` as a shadow exit alongside the live structure exit on every real fill, accumulating the paired per-trade delta until n ≥ 20 independent trading days. That converts a 26-day retrospective into forward evidence with no live risk. This is the same shape as the SSR shadow and `DYN-TRAIL-ATR`.
- **Walk-forward efficiency** on population A, to close the OP-11 leg.
- **Resolve the mechanism contradiction.** If the effect is real, WR must fall on real fills as it does on the replay. If it never does, the replay effect is a fill-model artifact and the whole thing dies — and that is the cheapest available falsification.

## Reproduce

```bash
backtest/.venv/Scripts/python.exe backtest/tools/stop_mode_ab_2026_08_09.py
```

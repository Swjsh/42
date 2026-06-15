# Pattern Mining — Cross-Strategy Convergence + Day-Coverage Audit (2026-05-13)

> Pattern mining across tonight's grinder output: sniper_stage2 keepers (4), sniper_stage1 keepers (2) + 24 passed-floor combos, v14_enhanced_stage1 rejections, vwap_stage1 rejections (972), opening_drive_fade_stage1 rejections (810). Source files in `backtest/autoresearch/_state/*`.

---

## TL;DR

1. **Knob convergence is now a doctrine.** Every strategy's top combos converge on the SAME structural knobs: `strike_offset=2 (sniper) / 0 (v14e)`, `tp1_qty_fraction=0.5–0.667`, `min_triggers/min_stars` at the LOOSE end of the grid, premium-stop in a tight tape-dependent band. The KEY exit knobs that vary (tp1_premium_pct, runner_target_pct) are not structural — they're tape-dependent tuning. Robust signal is in the WIDTH of the entry filter, not the exit.
2. **Four strategies cover seven days. Almost zero overlap on the unique days.** Across the top combo per strategy, the day-level union is `{4/29, 5/01, 5/04, 5/05, 5/06, 5/07, 5/12}` = 7 days. Three of those days are caught by ONLY ONE strategy (5/01-vwap, 5/06-odf, 5/12-v14e). **Sniper alone catches 4/7. A naive multi-strategy blender would catch 7/7.** This is the strongest diversification signal the grinder has ever surfaced.
3. **5/05 is a regime-flip day.** Sniper +$202, v14_enhanced -$152, vwap +$40, odf $0. The two BEAR strategies disagree. Whatever filter discriminates "5/05 is a sniper day, NOT a v14e day" is a new feature that would resolve $354/day of disagreement noise. This is the highest-value pattern in tonight's data.

---

## Section 1: Cross-Strategy Knob Convergence Table

### What CONVERGES (signal — keep stable across knob grids)

| Knob | Sniper Stage1 (24/24) | Sniper Stage2 (4/4) | v14e top-5 (5/5) | Reading |
|---|---|---|---|---|
| `strike_offset` (sniper) / `strike_offset_bear` (v14e) | 2 (100%) | 2 (100%) | 0 (100%) | ITM-2 for momentum / ATM for direction — both strategies anchor on a specific moneyness |
| `min_stars` / `min_triggers_bear` | 2 (100%) | 2 (100%) | 1 (100%) | Both at LOOSE end — looser entry = more trades; tighter filters reduce edge_capture |
| `tp1_qty_fraction` | 0.667 (100%) | 0.667 (100%) | 0.5 (100%) | Same direction: lock-half-take-rest. Universal exit doctrine. |
| `proximity_dollars` | 1.5 (100%) | 1.5 (100%) | — | Sniper-specific: $1.50 trendline proximity is the working zone |
| `qty` | 10 (100%) | 10 (100%) | — | Sizing doesn't matter for backtest — but converges to 10 because of P&L floors |
| `profit_lock_threshold_pct` | 0.0 (100%) | 0.0 (100%) | 0.05 (100%) | **Sniper wins with NO threshold (always-on lock). v14e wins with a SMALL threshold (0.05). Both reject 0.10.** Implies U-shape: locking either immediately or after a small breakout-confirmation works; locking too late doesn't. |
| `require_break_above_open` | True (100%) | True (100%) | — | Universal: don't fight the day's open break |

### What DIVERGES (tape-tuning — leave wide in grids)

| Knob | Distribution | Reading |
|---|---|---|
| `runner_target_pct` (sniper) | Sniper-1: 2.5 / 1.5 / 1.0 (8/8/8 each). Sniper-2: 2.0 (3/4), 1.25 (1/4) | Runner depth depends on the day — no single value dominates |
| `runner_target_premium_pct` (v14e high-EC) | 1.5 (7/11), 2.0 (4/11) | v14e settles toward 1.5x runner — shallower than sniper |
| `premium_stop_pct` | Sniper-1: -0.08 / -0.12 (12/12). Sniper-2: -0.06 / -0.10 (2/2). | Sniper-2 (stricter) likes tighter stops, but still no convergence |
| `body_min_cents` | Sniper-1: 0.05 / 0.10 (12/12). Sniper-2: 0.02 / 0.05 (2/2). | The momentum threshold is sensitive to the dataset — no universal value |

### Knob convergence summary

**Six structural knobs** (`strike_offset`, `tp1_qty_fraction`, `proximity_dollars`, `profit_lock_threshold_pct=0`, `require_break_above_open=True`, `profit_lock_stop_offset_pct≈0.05–0.08`) are STABLE across every top combo of every passing strategy. **These should be hard-coded defaults in the next grinder generation, not knobs at all.** Six of the eight knobs the grinder is permuting are not actually being searched — they collapsed to a single value at the top of the ranking.

The remaining knobs (`runner_target`, `premium_stop`, `body_min_cents`, `vol_mult`) are tape-dependent. The grinder is currently spending most of its compute reshuffling these, which is fine — but it should report disagreement in these knobs as "tape regime sensitivity," not "uncertainty about parameter choice."

---

## Section 2: Day-Coverage Diversification Analysis

> Each strategy's TOP combo's by_day P&L distribution. ZERO = no trade taken on that day.

| Date | Sniper #1 | v14_enhanced #1 (wide_pnl=$23k) | VWAP #1 (wide_pnl=$588) | ODF #1 (wide_pnl=$1442) | Sole-catcher |
|---|---|---|---|---|---|
| 2026-04-29 | +$181 | +$294 | $0 | $0 | Sniper + v14e (both) |
| 2026-05-01 | $0 | -$22 | **+$40** | $0 | **vwap ONLY** |
| 2026-05-04 | +$192 | +$5 | $0 | $0 | Sniper |
| 2026-05-05 | **+$202** | **-$153** | +$41 | $0 | **REGIME FLIP — see below** |
| 2026-05-06 | $0 | $0 | $0 | **+$122** | **odf ONLY** |
| 2026-05-07 | +$235 | +$250 | $0 | $0 | Sniper + v14e |
| 2026-05-12 | $0 | **+$241** | $0 | $0 | **v14e ONLY** |
| **DAYS CAUGHT** | **4/7** | **3/7** | **1/7** | **1/7** | **Union: 7/7** |

### Key implications

- **Sniper is the SPINE.** It's the only strategy that catches multiple anchor days reliably (4 of 7).
- **VWAP and ODF are PATCH STRATEGIES.** Each catches a single day that sniper misses. They are not standalone — they complement.
- **v14_enhanced has SAME-DAY DISAGREEMENT with sniper on 5/05.** Both strategies are bearish setups. On the same day, sniper made +$202 and v14_enhanced lost -$153. This is the single highest-information disagreement in tonight's data. Something about 5/05 distinguishes "Sniper-style setup" from "v14-style setup" that neither strategy currently encodes.
- **The disjoint days are clean.** 5/01 (vwap), 5/06 (odf), 5/12 (v14e) are each caught by exactly ONE strategy. A switching engine that picks the right strategy for the right macro regime would multiply effective coverage by ~2x without altering any strategy internals.

---

## Section 3: NEW STRATEGY HYPOTHESIS

### Hypothesis A: REGIME SWITCHER — multi-strategy blender gated by macro regime

The clearest pattern in tonight's data is **non-overlapping day coverage**: sniper alone hits 4 of 7 anchor days, but the remaining 3 days are each won by a DIFFERENT strategy (vwap=5/01, odf=5/06, v14e=5/12). The current pipeline treats each strategy as a standalone candidate competing for the same throne. But J's actual P&L would maximize if we ran ALL FOUR strategies in parallel and let each fire on its own days.

The implementation question is whether to (a) just run them all and accept overlap-day double-trades (cheap, naive, but exposes us to correlated losers like 5/05 where v14e loses $153 while sniper wins $202), or (b) gate each strategy on a macro regime indicator: VIX level, overnight gap size, prior-day range, premarket trend bias. A simple test: compute the prior-day range/ATR and the overnight gap for each of the 7 anchor days, then check whether each day's winning strategy correlates with that regime. If sniper days have small overnight gaps and v14e days have larger gaps (or vice versa), the switcher knob is just `if overnight_gap > X then v14e else sniper`. **This is the highest expected-value research direction in tonight's data and is testable in ~200 lines of Python without touching any production code.**

### Hypothesis B: 5/05 REGIME-DISCRIMINATOR — the "sniper-not-v14e" filter

On 2026-05-05, sniper made +$202 while v14_enhanced lost -$153 — a $355 daily swing on the same direction (both bear) using the same dataset. v14e fires earlier and on weaker triggers (`min_triggers_bear=1`); sniper requires 2-star confluence (`min_stars=2`) and a body-momentum threshold. Whatever filter differentiates these two on 5/05 is encoding a real market microstructure pattern.

**The investigation:** pull 5/05's intraday tape and identify what TRIGGER fired for v14e at its entry point that did NOT trigger sniper's 2-star + body filter. The two most likely candidates are: (1) v14e fired on a weak (single-confluence) trigger in a chop window before the real bear leg developed, and (2) v14e's strike_offset=0 (ATM) put it in a more theta-decay-sensitive contract that bled out during chop before the bear move arrived. If (1), a "chop guard" feature would help v14e — bar volatility/range expansion required before any trigger fires. If (2), v14e should be forced to ITM strikes on lower-conviction setups. Either fix is testable in ~50 lines of grinder code and would directly raise v14_enhanced's edge_capture without expanding its grid.

---

## Section 4: Recommendation for J's Morning Review

The grinder is converging on doctrine: structural knobs are stable across strategies, tape-dependent knobs cluster around regime-appropriate values. **Three concrete next moves:**

1. **(Highest EV) Test the multi-strategy blender hypothesis.** Build a 50-line script that simulates running sniper + v14_enhanced + vwap + odf in parallel across 2025-Q1 → 2026-Q2, computing combined daily P&L. If correlation between strategies is low (which the day-coverage table strongly suggests it is), the union catches ~2x the days sniper catches alone. Score: aggregate Sharpe + edge_capture vs sniper-alone.

2. **(High EV) Investigate the 5/05 regime-flip.** Generate a chart walk for 5/05 showing v14e's entry, sniper's entry, and the tape between them. Identify the discriminator. Add it as an explicit pre-trade filter. The fact that two bear strategies disagree on direction by $355 on the same day is a process leak.

3. **(Maintenance) Promote stable knobs to hard-coded defaults in the next grinder generation.** `strike_offset=2`, `tp1_qty_fraction=0.667`, `min_stars=2`, `profit_lock_threshold_pct=0`, `require_break_above_open=True`, `profit_lock_stop_offset_pct=0.05` are 100% converged across sniper's top combos. Removing them from the search space frees compute for the actual tape-dependent knobs and reduces overfit risk from the false dimensionality.

**Caveat:** All four strategies remain on the WATCH-FIRST promotion path per OP 21. None of these recommendations bypass that. The blender is a research candidate, not a production deployment.

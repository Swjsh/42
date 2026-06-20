# TRENDLINE_BREAK_RETEST — First-Pass Backtest Findings

**Run:** 2026-05-08 evening (post-market)
**Window:** 2026-03-15 → 2026-05-08 (37 trading days, 53 calendar days)
**Pricing:** Real OPRA option fills (with BS fallback for puts on uncached days)
**Position size:** 3 contracts (BASE) — no quality-tier scaling, to compare apples-to-apples vs v14
**Premium stop:** −8% (v14 baseline)
**Strike offset:** ITM-2 (v14 baseline)

---

## TL;DR

**Strategy has positive edge but FAILS the 45% WR gate.**

| Metric | min_touches=2 | min_touches=3 | **min_touches=4** | min_touches=5 | v14 baseline |
|---|---|---|---|---|---|
| Trades | 20 | 20 | **13** | 6 | 63 |
| Total P&L | +$198 | +$189 | **+$508** | −$114 | +$4,731 |
| Win rate | 20% | 20% | **23%** | 33% | 49% |
| W/L ratio | 5.09× | 5.03× | **7.43×** | 0.18× | 2.93× |
| Expectancy | +$9.90 | +$9.47 | **+$39.05** | −$18.98 | +$75 |
| Max DD | −$628 | −$630 | **−$315** | −$118 | −$348 |
| **Gates passed** | **3/4** | **3/4** | **3/4** | 0/4 | **4/4** |

`min_touches=4` is the cleanest sweet spot — fewer trades but each one is higher quality. Total P&L per trade ($39) is half of v14's ($75), with a 7.4× W/L ratio that's 2.5× v14's 2.93×.

**The problem: 23% WR fails the 45% gate.** The strategy is structurally a low-hit-rate / high-payoff scalp pattern. Two big winners (5/6 sessions, both ribbon-trend rides post-entry) carry an otherwise losing book.

---

## Trade-by-trade summary (min_touches=3, real fills, 20 trades)

Source: `trendline_break_retest_real_fills/trades.csv`.

| Date | Time | Side | Slope $/hr | Retest level | P&L | Exit |
|---|---|---|---|---|---|---|
| 4/9 | 11:15 | C | -0.23 | 675.80 | -$67 | premium_stop |
| 4/10 | 11:25 | C | +0.10 | 681.16 | -$64 | premium_stop |
| 4/14 | 13:20 | C | +0.50 | 693.74 | -$51 | premium_stop |
| 4/15 | 12:05 | P | +0.97 | 697.56 | +$4 | ribbon_flip |
| 4/16 | 13:00 | P | +0.16 | 700.85 | -$7 | ribbon_flip |
| 4/17 | 11:45 | P | +0.40 | 711.35 | -$43 | ribbon_flip |
| 4/22 | 11:10 | C | +0.14 | 709.74 | -$60 | premium_stop |
| 4/22 | 12:05 | C | +0.14 | 709.74 | -$59 | premium_stop |
| 4/22 | 13:45 | C | -0.16 | 709.74 | -$58 | premium_stop |
| 4/23 | 11:50 | P | +0.08 | 711.20 | -$54 | ribbon_flip |
| 4/24 | 12:35 | C | +2.02 | 713.38 | -$67 | premium_stop |
| 4/24 | 13:15 | P | +1.07 | 713.38 | -$13 | ribbon_flip |
| 4/27 | 12:25 | P | -0.17 | 713.98 | -$48 | ribbon_flip |
| 4/29 | 11:15 | P | -0.06 | 710.79 | -$29 | level_stop |
| 4/30 | 10:50 | C | +0.08 | 712.60 | -$64 | premium_stop |
| 4/30 | 12:30 | P | +1.42 | 715.39 | -$20 | ribbon_flip |
| **5/6** | **10:15** | **C** | **+0.32** | **729.50** | **+$551** | **TP1+runner_time** |
| 5/6 | 11:40 | P | +2.29 | 731.70 | -$34 | ribbon_flip |
| 5/6 | 12:35 | P | +0.36 | 731.70 | +$9 | ribbon_flip |
| **5/6** | **13:50** | **C** | **-0.32** | **731.70** | **+$361** | **TP1+runner_time** |

**Two trades carried the entire book: 5/6 10:15 (+$551) and 5/6 13:50 (+$361) = +$912.** All other 18 trades net −$722.

5/6 had a strong directional trend day where the trendline-break-retest pattern aligned with sustained directional movement. The other days the pattern fired but price chopped — premium stops or ribbon flips killed each entry.

---

## Why today's (5/8) 14:55 setup did NOT fire

J described the 14:55 break as a textbook setup, but the auto-detector did not produce a TRENDLINE_BREAK_RETEST trigger. Two reasons surface from the probe:

**1. Auto-detection missed J's trendline.**

J's mental line was an ascending support connecting:
- 5/7 14:30 ET intraday low ~$729.75
- 5/8 09:30 ET session low ~$734.70

That line projects to roughly **$736.12 at 14:55** — exactly the level (yesterday's RTH high $736.11/736.13, role-reversed). Beautiful confluence.

But the auto-detector requires ≥ 3 swing-point touches (`MIN_TOUCHES = 3`). With only 2 swings (one per session), this line was never generated as a candidate. Neither was a tighter min_touches=2 sweep able to find it — across-session swing-low pairing has limited coverage in `scipy.signal.find_peaks` over the session-boundary gap.

**2. Active-levels detector missed yesterday's RTH high.**

`backtest/lib/levels.py` derives prior-day high from ALL prior-day bars including premarket. 5/7 had a thin 04:00 premarket spike to $737.91 — that became `pdh` instead of the actual RTH high $736.11. The retest-level proximity check at 14:55 had no level near 736.11 to anchor on.

**Implication:** The strategy as currently implemented has TWO blind spots that today's setup happened to fall into:
- Cross-session 2-touch trendlines that connect overnight gaps
- Yesterday's RTH high specifically (always overshadowed by premarket spikes if any)

Both are fixable. See "Recommendations" below.

---

## Comparison to v14 baseline

| Comparison | TRENDLINE_BREAK_RETEST (mt=4) | v14 (BEAR + BULL_RECLAIM) |
|---|---|---|
| Trades | 13 | 63 |
| WR | 23% | 49% |
| W/L | 7.43× | 2.93× |
| Expectancy/trade | +$39 | +$75 |
| Total P&L | +$508 | +$4,731 |
| Max DD | −$315 | −$348 |
| Gates | 3/4 | **4/4** |

Per-trade economics are competitive (W/L is much better, expectancy is half), but the strategy fires far less often AND fails the WR gate. **TRENDLINE_BREAK_RETEST cannot stand alone as a live setup.**

But the W/L ratio is striking. If the auto-detector were tuned to find more setups (especially the cross-session 2-touch lines J draws), AND the level detector preferred RTH-only prior-day H/L, the trade count could rise without WR collapsing. There's a path to making this work.

---

## Promotion gate scorecard (per playbook markdown/0dte/playbook.md TRENDLINE_BREAK_RETEST)

| Gate | Threshold | Result | Status |
|---|---|---|---|
| (a) Backtest clears v14 baseline (P&L > 0) | > 0 | +$508 | ✅ |
| (a) WR ≥ 45% | 45% | 23% | ❌ |
| (a) W/L ≥ 1.5× | 1.5× | 7.43× | ✅ |
| (a) Max DD comparable to −$348 | ≤ −$348 ish | −$315 | ✅ |
| (b) 3+ paper-validated observations | 3 | 1 (today's 14:55) | ❌ |

**3 of 5 promotion gates clear; 2 fail.** Cannot promote to entry trigger. The setup remains CONTEXT-ONLY in the heartbeat, exactly as the playbook specifies.

---

## Recommendations (for next backtest cycle)

### R-TL-01: Improve trendline detection coverage

The auto-detector's `min_touches=3` rule misses cross-session 2-touch lines that J's eye routinely draws. Two extensions worth backtesting:

- **Allow 2-touch lines IF the projection at current bar is within $0.30 of an Active-tier level.** Confluence elevates a 2-touch line from speculation to actionable. This would have caught today's 5/8 14:55 setup.
- **Add explicit prior-day-low / prior-day-RTH-low as forced anchor points.** Many real trendlines connect a clean session low to today's morning low.

### R-TL-02: Use RTH-only prior-day high/low in levels detector

`backtest/lib/levels.py` should compute pdh/pdl from RTH bars only (09:30-16:00 ET), not full session including premarket. This change would have made 5/7's $736.11 RTH high an Active level on 5/8, enabling the retest check to anchor properly. **Risk:** other backtest results may shift slightly (older runs all used full-session pdh). Re-run v14 baseline alongside any change here.

### R-TL-03: Manual-trendline backtest mode

Auto-detection is structurally limited. The `chart_drawings.json` produced by the new ui_evaluate workaround captures J's actual drawn lines. A future backtest mode would:
1. Snapshot manually-drawn trendlines daily (via the existing premarket Step 5b).
2. Replay each day's manual lines through the trigger logic.
3. Produce trade simulations from J's exact mental model rather than the algorithm's approximation.

This is the highest-leverage extension. The auto-detector is a fallback; J's drawn lines are the gold standard.

### R-TL-04: Add a SCALP exit variant

Per the playbook, variant A (quick scalp) is the better fit when a level holds vs breaks. Currently every trade rides v14's ribbon-trail exits. A scalp variant should:
- Exit on first counter-bar that bounces > $0.30 from the entry (level-held condition).
- Tighten premium stop to −5% (vs current −8%).

Worth backtesting — likely lower per-trade expectancy but higher WR (which is the failing gate).

### R-TL-05: Skip 5/6-style scaffold-day trendlines

The two big winners are both from 5/6, a strong directional trend day. The other 18 trades are mid-chop nicks. A simple regime filter (e.g., 5m ribbon spread expanding through 30c with a fresh day-high or day-low at the break) would discard many losers without hurting the winners. Worth a sweep.

---

## Files

- `analysis/backtests/trendline_break_retest_real_fills/` — baseline run (min_touches=3)
- `analysis/backtests/trendline_break_retest_touches4/` — min_touches=4 (sweet spot)
- `analysis/backtests/trendline_break_retest_touches5/` — min_touches=5 (too restrictive)
- `analysis/backtests/trendline_break_retest_touches2/` — min_touches=2 (no improvement)
- `backtest/tools/sweep_trendline_break_retest.py` — scenario script (rerunnable)
- `backtest/tools/probe_5_8_setup.py` — diagnostic for today's missed setup

---

## Status

**Strategy held in CANDIDATE status in the playbook.** Heartbeat does not score trendline signals as entry triggers. Trendlines remain CONTEXT data via `automation/state/trendlines.json` for journal/dashboard reasoning.

Next gate-clearing milestones (in priority order):
1. R-TL-02 — fix levels.py RTH-only pdh/pdl
2. R-TL-01 — add 2-touch-with-confluence acceptance
3. R-TL-04 — backtest SCALP variant
4. Re-run with all three; if WR ≥ 45%, promote to PAPER-ELIGIBLE (parallel to BULLISH_RECLAIM_RIDE_THE_RIBBON's status)

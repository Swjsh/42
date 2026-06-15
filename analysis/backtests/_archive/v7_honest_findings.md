# Honest Real-Fill Backtest — v7

**Critical correction to v6.** v6's headline numbers (69% WR, $891 P&L,
3-of-4 PASS) included a look-ahead bias that flattered every trade. v7 fixes
the bias and adds bid/ask slippage modeling. Production rules unchanged —
only the fill simulator changed.

---

## TL;DR

The strategy as currently coded is **marginal-to-negative on this 53-day
window when fills are honest** — net **−$364, expectancy −$28/trade,
46% WR, 0.72× W/L**. v6's positive numbers came from look-ahead, not edge.

The setup-finder is real (engine fires on the right days). The auto-execution
is not yet ready. **Do not graduate from paper.** Continue using the engine
as a setup-surfacer with J reviewing each entry — that's the mode J's actual
3 winning trades came from.

---

## What was wrong with v6

**Look-ahead bug.** SPY 5-min bars are timestamped by their START time. A bar
with timestamp `10:25:00` covers the 10:25-10:30 window and CLOSES at
10:30:00. The trigger fires at the bar's close — at 10:30:00.

v6's entry logic used `bar_containing(opt_df, trigger_time)` which returned
the option bar starting at 10:25:00 — the SAME bar as the trigger. v6 then
used that bar's VWAP as the entry premium. **VWAP averages all option trades
during 10:25-10:30, including trades that printed BEFORE the trigger fired
at 10:30.** That's textbook look-ahead.

Concrete example — 2026-04-23 708P trigger at 13:05 bar:

| Bar | Open | High | Low | Close | VWAP | What this represents |
|---|---|---|---|---|---|---|
| 13:00 | 0.21 | 0.89 | 0.16 | 0.74 | 0.59 | Pre-trigger |
| **13:05 (trigger)** | 0.74 | 1.60 | 0.70 | **1.56** | **1.02** | Trigger bar — closes at 13:10 |
| **13:10 (next)** | **1.56** | 1.96 | 1.40 | 1.61 | **1.73** | First fillable bar |

v6 used **$1.02** (trigger-bar VWAP) as entry. Real entry happens at 13:10
or later — first realistic fill is **$1.56** (next bar open) or **$1.73**
(next bar VWAP). v6 was buying the trade $0.54-$0.71 cheaper than possible.
On 3 contracts, that's $162-$213 of fake P&L per trade.

The bug stacked across all 13 trades.

---

## The fix (v7)

Two changes to `lib/simulator_real.py`:

**1. Entry uses the next bar's open + slippage.** No look-ahead — entry happens
strictly AFTER the trigger bar closes. Minimum hold time is now 1 full bar
(5 min). Entry price = `next_bar.open + entry_slippage` (default $0.02).

**2. Slippage on market exits.** Limit-fill exits (TP1, BE-stop, premium stop,
runner target) fill at the bracket level exactly — no slippage. Market exits
(level stop, ribbon flip, time stop) fill at `bar.close - exit_slippage`
(default $0.02).

Slippage is configurable per call. Default $0.02 each way matches typical
OPRA bid/ask half-spread on liquid SPY 0DTE ATM options.

---

## Three-way comparison

Same 13 trades, same triggers, same engine. Only pricing model changed.

| Metric | v5 (BS, no LA) | v6 (real, look-ahead) | **v7 (honest)** |
|---|---|---|---|
| Trades | 13 | 13 | 13 |
| Winners | 7 (54%) | 9 (69%) | **6 (46%)** |
| Avg winner | $131 | $134 | **$99** |
| Avg loser | $-101 | $-78 | **$-138** |
| W/L ratio | 1.29× | 1.72× | **0.72×** |
| Total P&L | $309 | $891 | **−$364** |
| Expectancy | $24 | $69 | **−$28** |
| Max drawdown | $-243 | $-124 | **−$634** |
| Avg hold | 48 min | 17 min | **40 min** |
| Runner-target hits | 1 | 2 | **0** |
| Premium-stop fills | 3 | 0 | **1** |

**Live deployment scorecard:**

| Threshold | v5 | v6 | **v7** |
|---|---|---|---|
| Trades ≥ 20 | FAIL (13) | FAIL (13) | **FAIL (13)** |
| Win rate ≥ 45% | PASS (54%) | PASS (69%) | **PASS (46%)** |
| W/L ratio ≥ 1.5× | FAIL (1.29×) | PASS (1.72×) | **FAIL (0.72×)** |
| Expectancy > 0 | PASS ($24) | PASS ($69) | **FAIL (−$28)** |
| **Total** | 2 / 4 | 3 / 4 | **1 / 4** |

v7 is the truth. The strategy is not green-light ready.

---

## Trade-by-trade verification

I walked one trade by hand against raw OPRA bars to confirm v7's fills are
correct:

**2026-04-23 708P (engine-found trade, NOT a J-replicated trade)**

Trigger bar: SPY 13:05:00 (covers 13:05-13:10). High 709.32, low 707.86,
close 707.93. Trigger fires at 13:10:00 — close 707.93 < rejection level
708.75. ✓

Entry: next bar SPY 13:10:00. Option bar 13:10 open=$1.56, +$0.02 slippage
= **$1.58 entry**. ✓ (matches v7 trades.csv)

TP1 target: $1.58 × 1.30 = $2.05. Hit at bar 13:15 (option bar high $2.77
> $2.05). 2 contracts sell at $2.05 → $94 profit ($2.05 − $1.58 = $0.47
× 2 × 100). Stop moves to BE = $1.58.

Runner: continues. Option bar lows stay above $1.58 through 13:55. At some
point between 13:55-14:05, low touches $1.58 → BE stop fires. Runner P&L
= $0.

Trade total: $94 + $0 = **+$94.80** ✓ (matches v7 row exactly)

The trade card matches the raw OPRA data to the cent.

---

## Where the engine differs from J's manual trading

The engine is firing on the right DAYS but at different times and strikes
than J's actual entries. This is the gap that explains why J's 3 historical
trades were all winners while the engine's auto-fires net negative:

| Trade day | J's entry | Engine's entry (v7) | Why different |
|---|---|---|---|
| 4/29 | 10:25 ET, 710P, +$342 | 12:35 ET, 709P, **−$129**; 14:10 ET, 709P, **−$153** | Engine waited for filter sequence; missed the 10:25 morning rejection. |
| 5/1 | 13:36 ET, 721P, +$470 | doesn't fire | yfinance/TV ribbon mismatch — engine sees BULL/MIXED at 13:36; chart was BEAR. |
| 5/4 | 10:27 ET, 721P, +$730 | 11:20 ET, 719P, **+$94** | Engine fires later, picks ATM strike $2 below J's. |

The engine's setup detection works but its **timing and strike discretion
are noticeably worse than J's manual reads**. Tomorrow's autonomous
execution will be making those same auto-decisions.

---

## Recommendation

**Do not graduate the engine to live money on the 12-trade-count threshold
alone.** The engine has 1-of-4 PASS under honest pricing. Keep paper-trading
at minimum until:

1. Sample size reaches n ≥ 20 — calendar requirement.
2. **EITHER** the win rate / expectancy improves under honest fills as the
   engine's internal logic is tuned, **OR** we accept the engine as a
   setup-surfacer only and require manual J approval for each entry.

**Recommended near-term changes to investigate:**

- **Earlier-bar entry preference.** The engine missed J's 10:25 ET entry on
  4/29 because filter 9 wasn't satisfied yet. With filter 9 already relaxed
  in heartbeat.md, re-run backtest comparing entry-time distribution to
  J's bars.
- **Strike discretion.** Engine picks ATM round-to-$1. J seems to pick $1-2
  ITM (closer to spot than the round number). Test ITM-1 selection.
- **Daily setup quality gating.** Engine fires on first valid trigger of
  the day. Many of these are MIDDAY mediocre setups. Adding a "best of day"
  rule (wait until 11:00 ET, take the highest-conviction setup of the day)
  may improve average quality at the cost of trade count.

These are R-BT-08, R-BT-09, R-BT-10 — logged in recommendations-log.jsonl.

---

## What's still genuinely true about v6

- Real OPRA data IS the right pricing source — Black-Scholes was directionally
  off. We just need to use the data correctly.
- The engine triggers on the right setup days (4/29, 5/4 both fire; 5/1
  blocked by ribbon-data mismatch but trigger primitive detects rejection).
- The slippage model ($0.02 each way) is conservative-but-defensible.
- The fill simulator is now honest — verifiable by hand against raw bars.

---

## Files

- v7: `analysis/backtests/production_rules_v7_honest_fills/`
- Engine: `backtest/lib/simulator_real.py` (look-ahead fixed, slippage added)
- Cache: `backtest/data/options/SPY*.csv` (16 contracts now, 704P added)
- E2E tests: 13/13 pass under v7 (`tests/test_e2e_*.py`)

Re-run any time:
```
cd backtest
.venv/Scripts/python tools/fetch_option_data.py
.venv/Scripts/python run.py --start 2026-03-15 --end 2026-05-07 \
    --label production_rules_v7_honest_fills --real-fills
```

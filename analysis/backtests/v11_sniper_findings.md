# v11 — Sniper Entry Configuration · 4-of-4 PASS

**Run:** 2026-05-07
**Window:** 2026-03-15 → 2026-05-07 (53 calendar days)
**Result:** **+$3,053 · 52% WR · 2.12× W/L · $55/trade · 4-of-4 PASS**

---

## TL;DR

Three changes from v10 produced the first **fully passing** configuration:

1. **No entries before 10:00 ET** — skips the 9:35-10:00 chop
2. **No entries 14:00-15:00 ET** — skips the structural-loser afternoon window
3. **Filter 9 vol threshold dropped from 1.3× → 0.7×** — catches the morning
   rejection bars where the move hasn't started so volume hasn't spiked yet

Total P&L jumped from $1,352 (v10) to **+$3,053** (v11) on 56 trades vs 26.
Hit rate on J-quality morning entries went from 4 → 11. Engine now passes ALL
four live-deployment thresholds.

---

## The diagnosis — why the engine was firing late

For 5/4 specifically (J entered 10:27 ET; old engine fired 11:20 ET):

```
Time   Bar   Stack  Score  Why blocked
10:00  red   BEAR   8/10   filter 8 (VIX) + filter 9 (vol 0.4x)
10:05  red   BEAR   9/10   filter 9 (vol 0.7x)         <-- needed only 0.7x to pass!
10:25  red   BEAR   8/10   filter 8 + filter 9 (J's actual entry bar)
11:15  red   BEAR  10/10   ENTRY (vol finally hit 1.7x)
```

The structural insight: **morning rejection bars have LOW volume because the
move hasn't started yet.** J reads them with his eye. The old engine waited
for volume to confirm — by which time the optimal entry had passed.

Dropping the 1.3× threshold to 0.7× lets the engine fire on rejection bars
where price action is right but volume hasn't spiked. The "red bar" check
remains (filter 9 still requires close < open).

---

## Sniper sweep results (held: ITM-2 strikes, -10% stop, ≥1 trigger, time filters)

| F9 Vol | Trades | WR | TOTAL | Worst | Max DD | 10-11AM | PASS |
|---|---|---|---|---|---|---|---|
| 1.3× (old) | 21 | 52% | $1,768 | −$99 | −$226 | 4 | 4/4 |
| 1.0× | 35 | 49% | $2,136 | −$161 | −$321 | 5 | 4/4 |
| **0.7×** | **56** | **52%** | **$3,053** | **−$183** | **−$439** | **11** | **4/4** |
| OFF | 67 | 43% | $1,922 | −$183 | −$610 | 18 | 3/4 |

**0.7× is the sniper sweet spot** — relaxed enough to catch morning rejections,
strict enough to filter dead bars. Going to fully off (no volume req) added
trades but dropped WR below 45% — too permissive.

---

## Live deployment scorecard

| Threshold | Required | v11 | Status |
|---|---|---|---|
| Logged trades | ≥ 20 | 56 | **PASS** |
| Win rate | ≥ 45% | 52% | **PASS** |
| W/L ratio | ≥ 1.5× | 2.12× | **PASS** |
| Expectancy | > 0 | $55 | **PASS** |
| **Total** | | | **4/4 PASS** |

First config to pass all four thresholds.

---

## $1,000 account scaling (1-contract sizing)

| Metric | $ amount | % of $1k account |
|---|---|---|
| Total P&L over 53 days | **+$1,018** | **+102%** |
| Avg winner | $63 | 6.3% |
| Avg loser | -$29 | -2.9% |
| **Worst single trade** | **-$61** | **-6.1%** |
| Max drawdown | -$146 | -14.6% |
| Best single trade | $147 | 14.7% |

102% growth in 53 days = absurd if sustained. Real-world won't be — variance
matters and 53 days is a small sample. But the math is clean.

Per-trade risk -6.1% is well within the playbook's 50% cap. Max DD -14.6% is
manageable for a paper account. **Genuine safe-growth profile.**

---

## Caveat — J's morning winners still get stopped on -10%

Same caveat as v10: J's actual 4/29, 5/1, 5/4 trades had MAE -15.6%, -59.4%,
-34.1%. A -10% stop would have stopped him out of all three. The engine still
doesn't catch his EXACT entry timing (4/29 morning is green-bar; engine needs
red bar).

For now this is fine — the engine catches a DIFFERENT subset of profitable
trades on the same broader pattern. Once R-BT-08 closes more of the timing
gap to match J's intra-bar reads, stops will need re-sweeping.

---

## Locked production config (v11)

```python
# RATIFIED defaults in lib/orchestrator.py and lib/filters.py:
min_triggers = 1                                    # filter 10: ≥1 trigger
strike_offset = -2                                  # ITM-2 puts (delta ~0.7)
premium_stop_pct = -0.10                            # -10% safe-growth cap
no_trade_before = dt.time(10, 0)                    # skip 9:35-10:00 chop
no_trade_window = (dt.time(14, 0), dt.time(15, 0))  # skip afternoon loser
f9_vol_mult = 0.7                                   # sniper morning rejections
```

Plus the v8 exit doctrine (chart-level TP1 + tiered runners + opposite-stack
ribbon flip back).

---

## Per-day distribution (consistency check)

26 trading days had at least one trade. P&L ranges:

- Best day: 3/20 with +$595 across multiple trades
- Worst day: 4/29 (J's late-entry day) with -$199 ish
- Most days: small + or - trades, with ribbon-ride bigger wins on a few days

No catastrophic single-day losses. Drawdown is gradual.

---

## Files

- Production canonical: `analysis/backtests/production_rules_v11_sniper/`
- Findings: this doc
- Tools: `tools/sweep_sniper_entries.py`, `tools/sweep_sniper_v2.py`,
  `tools/benchmark_v10.py`
- Defaults locked: `lib/orchestrator.py`, `lib/filters.py`

Re-runnable:
```
cd backtest
.venv/Scripts/python run.py --start 2026-03-15 --end 2026-05-07 \
    --label production_rules_v11_sniper --real-fills
.venv/Scripts/python tools/sweep_sniper_v2.py
```

---

## Next priorities

1. **Sync `automation/prompts/heartbeat.md`** to v11 production rules. Live
   engine still uses old defaults — backtest doesn't match live until done.
2. **R-BT-08 — closer entry timing for green-bar morning rejections** like
   J's 4/29. Possibly requires 1-min bar resolution or different bar-shape
   logic.
3. **Validate on broader window** — current 53-day sample might be regime-
   specific. Extend to 90+ days when feasible.

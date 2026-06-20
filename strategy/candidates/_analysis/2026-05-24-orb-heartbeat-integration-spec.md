# ORB Heartbeat Integration Spec

**Filed:** 2026-05-24  
**Status:** SPEC-ONLY — prerequisites audit and exact diff for J ratification  
**Candidate:** [#4 ORB_NARROW_OR_GATE](../2026-05-21-orb-narrow-or-gate.md) / [#5 ORB_DIRECTION_FILTER](../2026-05-21-orb-direction-filter.md)  
**Why this doc exists:** Leaderboard #4 notes said "OR-range engine feature-add required in heartbeat.md before production." That claim was partially wrong — clarified below. This doc is the authoritative prerequisites list and exact change spec.

---

## 1. What is already wired (nothing for J to build)

### Watcher (live, OP-22 engine-benefit, ratified 2026-05-21)

`backtest/lib/watchers/orb_watcher.py`:
- Full 4-state ORB GOAT machine: NEUTRAL → BREAKOUT → WAITING_RETEST → RETEST_HELD
- `MAX_OR_RANGE = 2.00` — narrow-OR gate baked in at `compute_opening_range()` line 109.  
  Wide-OR days (or_range >= 2.00) return `None` from `compute_opening_range()` → watcher
  returns `None` → no signal logged. OR-range filtering is fully internal. **No heartbeat
  feature-add needed for OR-range.**
- `ORB_DIRECTION_FILTER = "long"` — short breakout state machine never activates.
- Real-fills validation PASS: N=22 OPRA cases, WR=81.8%, chart-stop-only config (L64).
  15-month period with chart-stop: N=32 deduped, WR=81.2%, P&L=+$976, 5/6 quarters positive.

### Watcher runner (live, called on every tick)

`backtest/lib/watchers/runner.py` line 107:
```python
orb = detect_orb_break(bar, day_bars, bar_idx_in_day, vol_baseline_20)
if orb is not None:
    if orb.confidence == "medium":    # 16-month: medium=$+589/86 fires (+EV)
        raw_signals.append(orb)       # high=$-198/9 fires (consensus trap, suppressed)
```

Every ORB_RETEST_LONG signal with confidence=medium is:
1. Appended to `automation/state/watcher-observations.jsonl`
2. Available the next tick for any reader

### Summary of the gap

The watcher OBSERVES ORB setups. The heartbeat NEVER READS those observations.
Heartbeat.md Entry Branch scores only BEARISH_REJECTION and BULLISH_RECLAIM.
No ORB entry path exists. Signals accumulate but nothing acts on them.

---

## 2. What does NOT need to be built (closing the OR-range myth)

Old note in leaderboard #4: *"OP-20 production note: OR-range feature-add required in
heartbeat.md before production (engine must compute or_range at 09:35-09:45 ET)"*

**This is wrong.** `compute_opening_range()` builds the OR from `day_bars` at the first
bar after 10:00 ET (when `state["or_data"] is None`). If `or_range >= 2.00` (MAX_OR_RANGE),
it returns `None` → `detect_orb_break()` returns `None` → no observation logged → heartbeat
reads nothing for that day. The filtering chain is:

```
day_bars → compute_opening_range() →
  or_range >= 2.00 → None (wide ORB suppressed, day effectively skipped)
  or_range <  2.00 → OpeningRange (narrow ORB, proceed)
```

The heartbeat doesn't need to know the or_range value. It just reads signals that already
passed the filter. Zero heartbeat feature-add for OR-range.

---

## 3. The two changes needed

### Change A — heartbeat.md: add ORB branch (WATCH-ONLY initially)

**File:** `automation/prompts/heartbeat.md`  
**Where:** After the standard Scoring section (BEARISH 10 / BULLISH 11), before the
Decisions Ledger section.  
**Rule 9 status:** Adding a WATCH-ONLY branch that logs to decisions.jsonl without
placing orders = OP-22 engine-benefit. Uncommenting the execution block = Rule 9 change,
requires J weekend ratification.

**Exact text to add:**

```markdown
## ORB branch (WATCH-ONLY until J ratifies for live execution)

> **Status 2026-05-24: WATCH-ONLY.** OP-21 live gate: 0/3 live J wins on ORB_RETEST_LONG.
> This block reads watcher-observations.jsonl and logs ORB_WOULD_ENTER to decisions.jsonl
> but does NOT place orders. Activation: uncomment execution block + J ratification (Rule 9).

**Only run when:** position flat AND neither BEARISH nor BULLISH entry fired this tick.

**Signal read:**

```
Read last 30 lines of automation/state/watcher-observations.jsonl.
For each line, newest-first:
  row = json.parse(line)
  Skip if row.watcher_name != "orb_watcher"
  Skip if row.setup_name != "ORB_RETEST_LONG"
  Skip if row.confidence != "medium"
  Skip if row.bar_timestamp_et.date != today_et
  Skip if (now_et - row.bar_timestamp_et) > 10 min (signal stale, retest window missed)
  orb_signal = row
  break (first match = most recent)
```

If `orb_signal` found:

**Gate sequence** (same as BEARISH/BULLISH gates, adapted):

| Gate | Check |
|---|---|
| G5 | circuit_breaker.tripped → SKIP_ORB_TRIPPED |
| G7 | PDT: day_trades_used_5d >= 3 AND equity < 25000 → SKIP_ORB_PDT |
| G1 | "ORB_RETEST_LONG" in playbook.md `### Setup name:` headings → SKIP_ORB_G1 if missing |
| G2 | bar_timestamp_et is a closed bar (runner.py only writes post-close) → auto-pass |
| G10 | heartbeat log: ORB BLOCK within 15 min → skip |

**Execution block (CURRENTLY COMMENTED OUT — activate with J ratification):**

```
# Stop = orb_signal.stop_price   (chart stop: min(retest_bar_low - $0.05, ORH - $0.05))
# TP1  = orb_signal.tp1_price    (ORH + 50% × or_range — 0.5R projection)
# Run  = orb_signal.runner_price  (ORH + 100% × or_range — 1.0R projection)
# Direction = "long"  →  ENTER_BULL (SPY call)
# Strike selection: per-tier table, same as BULLISH branch
# Qty: BASE tier (ORB triggers never include confluence/sequence_reclaim)
# premium_stop_pct = -0.99  (chart-stop-only per L64 — premium stop misfires at ORH retest)
# G6 + G6b sizing gates apply unchanged
# Write current-position.json with setup_name = "ORB_RETEST_LONG"
# Emit ENTER_BULL
```

**Watch-only log (always active, no order placed):**

```
append to decisions.jsonl:
{
  "action": "ORB_WOULD_ENTER",
  "setup_name": "ORB_RETEST_LONG",
  "confidence": "medium",
  "entry_price": orb_signal.entry_price,
  "stop_price": orb_signal.stop_price,
  "tp1_price": orb_signal.tp1_price,
  "runner_price": orb_signal.runner_price,
  "or_high": orb_signal.metadata.or_high,
  "or_range": orb_signal.metadata.or_range,
  "bars_to_retest": orb_signal.metadata.bars_to_retest,
  "sma_bullish": orb_signal.metadata.sma10 > orb_signal.metadata.sma50,
  "bar_timestamp_et": orb_signal.bar_timestamp_et
}
```
```

### Change A2 — ORB position management (exit rules diverge from BEARISH)

When `current-position.setup_name == "ORB_RETEST_LONG"` is open, use these exit rules
instead of the standard BEARISH position rules:

| Exit type | Rule |
|---|---|
| **Chart stop** | SPY close < ORH - $0.05 (price re-enters opening range) |
| **Premium stop** | `-0.99` safety net only (chart stop is primary) |
| **TP1** | At `orb_signal.tp1_price` (ORH + 50% × or_range). qty_fraction = 0.50 |
| **Runner** | At `orb_signal.runner_price` (ORH + 100% × or_range). BE stop after TP1 |
| **Profit-lock** | v15 chandelier applies (arm at +5% favor, trail 20% off HWM) |
| **Ribbon flip** | **NOT USED** — ORB is momentum continuation; ribbon may be MIXED during retest |
| **Time stop** | 15:50 ET hard (same as all setups) |

Rationale for no ribbon-flip exit: the ORB retest entry fires DURING the retest pullback when
ribbon may temporarily show MIXED. Flipping to BEAR on a retest would exit immediately after entry.
The OR level hold (chart stop) is the correct invalidation signal, not ribbon direction.

### Change B — playbook.md: add ORB_RETEST_LONG to live setups

**File:** `markdown/0dte/playbook.md`  
**Where:** After the two live setup blocks (BEARISH_REJECTION and BULLISH_RECLAIM), before the
"Setup ideas / candidates" section.  
**Rule 9 status:** Adding to the live section would allow Gate G1 to pass. This is part of
the production activation — do at the same time as uncommenting the execution block.  
**Pre-ratification:** Add to "Setup ideas / candidates (NOT YET TRADABLE)" now as documentation.

**Exact text for `### Setup ideas` section:**

```markdown
### ORB_RETEST_LONG (watch-only, OP-21 gate 0/3 live wins)

**Pattern:** SPY breaks above the 30-min opening range high (ORH), pulls back to within $0.20
of ORH from above, holds (green bar, close >= ORH), then enters on the close of the retest bar.

**Conditions:**
- OR range: < $2.00 (narrow-OR gate: or_range >= 2.00 → watcher returns None, day skipped)
- OR definition: 09:30-10:00 ET high/low
- Direction: LONG ONLY (short ORBs suppressed — 16-mo long-only: +$7,378, 4/6 quarters positive)
- Entry window: RETEST_HELD state by 12:30 ET (8 bars × 5min after breakout)
- Confidence gate: medium only (high = consensus trap: $-198/9 fires; medium = +EV: $+589/86)
- SMA trend filter: SMA10 > SMA50 = bullish bias (elevates to high, but high is suppressed — medium is the sweet spot)
- Volume confirm: bar_volume >= 1.3× 20-bar avg (elevates to high, same suppression applies)

**Exit rules (non-standard — diverge from BEARISH_REJECTION):**
- Stop = chart stop at ORH (premium_stop_pct = -0.99, chart stop is primary per L64)
- TP1 = ORH + 50% × or_range
- Runner = ORH + 100% × or_range
- NO ribbon-flip exit
- Profit-lock chandelier (v15 standard)
- Time stop 15:50 ET

**OP-21 promotion path:** 3+ live J wins on ORB_RETEST_LONG → move to live `### Setup name:` block → J ratification → execution uncommented.

**Evidence:** 16-month deduped: N=32, WR=81.2%, P&L=+$976, 5/6 quarters positive.
Walk-forward OOS/IS Sharpe ratio=0.667 (PASS). Real-fills N=22 OPRA, WR=81.8% (PASS, L64 chart-stop).
See leaderboard #4 + `analysis/backtests/orb-narrow-or-walkforward/results.json`.
```

---

## 4. Prerequisites checklist (in order)

| # | Item | Action required | Owner | Blocking what |
|---|---|---|---|---|
| 1 | ORB_RETEST_LONG in playbook.md candidates section | Write now (docs only) | Gamma | Nothing yet |
| 2 | heartbeat.md WATCH-ONLY ORB branch | Write + gym test | Gamma/J (Rule 9) | Live signal capture |
| 3 | Gym 70/70+ PASS after heartbeat.md WATCH-ONLY edit | Run after #2 | Gamma | Confirms no regression |
| 4 | Accumulate watcher-observations.jsonl ORB entries | Passive (watcher already running) | — | Need to see signal frequency |
| 5 | J marks 3+ live ORB wins in journal | Trading session capture | J (OP-21 gate) | Execution activation |
| 6 | ORB_RETEST_LONG moved to live setups in playbook.md | Same commit as #7 | J/Gamma | Gate G1 |
| 7 | heartbeat.md execution block uncommented | Weekend ratification | J (Rule 9) | Live trades |

Items 1-3 can be done by Gamma autonomously (OP-22 — no live orders impacted).
Items 4-7 require market time + J's active participation.

---

## 5. Timing and signal frequency

Based on 16-month deduped data (N=32 over ~16 months):
- Expected frequency: ~2 signals/month
- Peak quarter (Q2-2026): ~5 signals in 2 months
- These are not high-frequency signals — the ORB retest pattern requires specific conditions

For OP-21 accumulation (3 live wins), at 2 fires/month, expect 6-8 weeks minimum to see 3 wins.
At 81.8% WR, P(3 wins in 4 fires) = 0.818³ × 4 = 54.9%. Most likely 2-3 months to accumulate.

---

## 6. Integration cost

| Item | Incremental cost per tick |
|---|---|
| Read watcher-observations.jsonl (last 30 lines) | ~2ms, $0 |
| Parse + filter (Python in LLM context) | ~1ms, $0 |
| decisions.jsonl append on ORB_WOULD_ENTER | ~1ms, $0 |
| **Total per tick** | **~3ms, $0** |
| TradingView API calls added | **0** (no new TV calls needed) |
| Alpaca API calls added | **0** (watch-only mode has no order calls) |

The integration is minimal-footprint. It would not affect the heartbeat tick runtime budget
(target <60s for HOLD ticks).

---

## 7. What happens on activation day

When J ratifies and the execution block is uncommented:

1. At 10:00 ET, compute_opening_range() runs for today's bars (already happens in runner.py)
2. If SPY breaks ORH with a bullish close and volume after 10:00 ET → watcher enters WAITING_RETEST
3. If SPY pulls back to within $0.20 of ORH → RETEST_HELD fires → medium-conf signal logged
4. Heartbeat reads the signal (within 3-5 min depending on watcher fire time vs heartbeat tick timing)
5. All gates pass → ENTER_BULL with chart-stop-only, TP1 at 0.5R, runner at 1.0R
6. If ORH holds post-entry → likely 81.8% WR based on 22 OPRA real-fills

The 3-5 min read delay (watcher fire → heartbeat tick) is acceptable because:
- ORB entries are time-insensitive at the bar level (5-min bars, entry at close)
- The retest bar's closing price IS the entry price — no intrabar urgency
- Ticker drift during the heartbeat's 3-min cadence: typically $0.10-0.30 in normal vol

One edge case: if heartbeat tick fires just AFTER bar close and watcher fires on that SAME bar,
the heartbeat might miss the signal by 1 tick (5 min). Acceptable — the entry window is 10:00-12:30 ET.

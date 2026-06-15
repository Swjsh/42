# Heartbeat Chart-Data Audit — 2026-05-14

> **Scope:** End-to-end audit of how `Gamma_Heartbeat` consumes TradingView MCP chart data, with focus on closed-bar vs in-progress-bar handling. Triggered by J's concern that the heartbeat may not be reading the right candle.
>
> **Mode:** READ-ONLY investigation (per CLAUDE.md OP 24 + rule 9). No production files modified. Recommendations queued at end.
>
> **Bottom line:** A class-of-bug ANALOGOUS to the watcher_live T76 V=0 in-progress-bar problem (fixed earlier today) exists in the production heartbeat. The doctrine SAYS "last closed bar" but the prompt does NOT instruct the model to verify or filter the bar's close-time against `now_et`. Empirically, today's loop-state writes the in-progress bar timestamp as `last_bar_timestamp` and reasons over its incomplete OHLCV. Today's first live v15 trade (09:58 ENTER_BULL 745C, +$913) was scored against an in-progress live snapshot, not the just-closed bar. The trade won, but the trigger that fired likely didn't match the actual closed-bar OHLCV.

---

## 1. Scheduler & cadence

**Source-of-truth file:** `setup/install-tasks.ps1` lines 100-107
**Wrapper script:** `setup/scripts/run-heartbeat.ps1`

```
Task name:           Gamma_Heartbeat
Trigger time:        09:30 ET daily
Repetition interval: 3 min
Repetition duration: 6h25m (until ~15:55 ET)
Action:              powershell.exe -File setup\scripts\run-heartbeat.ps1
Per-tick budget:     0.50 USD (Haiku) / 0.50 (Sonnet escalation)
Per-tick timeout:    160s Haiku / 150s Sonnet
```

**Tick-time pattern (every 3 min from 09:30):** 09:30, 09:33, 09:36, 09:39, 09:42, 09:45, 09:48, ...

**Bar-boundary pattern (5m):** 09:30, 09:35, 09:40, 09:45, 09:50, 09:55, ...

**Critical relationship:**
- 09:30 fire → bar 09:25-09:30 just closed AT 09:30 → reading right after close = OK
- 09:33 fire → bar 09:30-09:35 is IN PROGRESS (3 of 5 min elapsed) → in-progress bar
- 09:36 fire → bar 09:35-09:40 is IN PROGRESS (1 of 5 min elapsed) → in-progress bar
- 09:39 fire → bar 09:35-09:40 is IN PROGRESS (4 of 5 min elapsed) → in-progress bar
- 09:42 fire → bar 09:40-09:45 is IN PROGRESS (2 of 5 min elapsed) → in-progress bar
- 09:45 fire → bar 09:40-09:45 just closed AT 09:45 → reading right after close = OK

So **roughly 3-of-5 ticks fire MID-BAR, 2-of-5 fire RIGHT AFTER a 5m close**. The mid-bar ticks are where the bug bites.

**Throttle layer (run-heartbeat.ps1 lines 73-80):** in BASE mode skip every-non-3rd tick; in COOL mode skip every-non-4th. Plus hash-based early-exit (lines 87-118) skips entirely if state digest unchanged.

---

## 2. What chart-data tools the heartbeat calls

**Production prompt:** `automation/prompts/heartbeat.md` — line numbers cited below.

| Step | Tool call | Purpose | Line |
|---|---|---|---|
| Skip-stale gate | `data_get_ohlcv(count=1, summary=true)` on BATS:SPY 5m | Compare timestamp to `loop-state.last_bar_timestamp` and skip if same bar AND volume grew <30% | 200 |
| Main bar read | `data_get_ohlcv(count=2, summary=true)` on BATS:SPY 5m | "Latest = just-closed bar; prior = one cycle back" | 214 |
| Ribbon | `data_get_study_values` (Saty Pivot Ribbon) | Read fast/pivot/slow EMA values | 216 |
| HTF (every 15min) | `chart_set_timeframe("15")` → `data_get_ohlcv(count=2, summary=true)` → `data_get_study_values` → `chart_set_timeframe("5")` | 15-min stack | 220 |
| VIX (cached) | `chart_set_symbol("TVC:VIX")` → `quote_get` → restore SPY symbol | VIX value + direction | 210 |

**No CSV or yfinance fallback.** Heartbeat is 100% TradingView MCP-driven. The same bars later get journaled to CSVs by `eod-summary` for backtests; live trading reads only TV.

---

## 3. THE BUG — in-progress bar treated as just-closed

### Doctrine vs implementation gap

**Doctrine (heartbeat.md line 214):**
> `data_get_ohlcv(count=2, summary=true)` on BATS:SPY 5m. **Latest = just-closed bar; prior = one cycle back.**

**Doctrine (heartbeat.md line 304):**
> Score both setups against the **LAST CLOSED 5m bar**. UNKNOWN field = FAIL.

**Doctrine (heartbeat.md line 409, Gate G2):**
> `last_closed_bar_time = SPY 5m bar where time_close < now_et`
> `trigger_fired_on_closed_bar = developing_setup.triggers_fired evaluated against ONLY bars where time_close < now_et`
> BLOCK if "trigger from live bar"

**What the prompt does NOT do:**
1. It does NOT instruct the model to compute `time_close = bar.timestamp + 5m` and compare to `now_et` before treating bar[-1] as "just closed."
2. It does NOT instruct the model to filter bars where `volume == 0` or where `volume` is implausibly low for the time-of-day (the watcher_live T76 fix lines 193-208 in `backtest/autoresearch/watcher_live.py`).
3. It does NOT instruct the model to discard bar[-1] if it's the in-progress bar and use bar[-2] instead.

**TradingView's `data_get_ohlcv`** returns bars labeled by their **OPEN time** (confirmed against CSV at `backtest/data/spy_5m_2026-05-08_2026-05-14.csv` line 461 onward — `2026-05-14 14:20:00-04:00` is the bar that opened at 14:20 ET and closes at 14:25 ET). When the heartbeat fires at 14:24:03 ET and asks for `count=2`, TV returns:
- bar[0]: 14:15:00 ET (closed at 14:20 ET) — the actual just-closed bar
- bar[1]: 14:20:00 ET (will close at 14:25 ET) — the **IN-PROGRESS** bar

The doctrine TELLS the model "Latest = just-closed bar" — but the LATEST bar TV returns is the in-progress one, because TV always streams the live forming bar at the head of the time series.

### Real-world evidence — today (2026-05-14)

**Loop-state at HB#27, 14:24:03 ET write** (`automation/state/loop-state.json` lines 4-6):
```json
{
  "last_change_at": "2026-05-14T14:24:03-04:00",
  "last_change_reason": "tick 27: 14:20 5m bar close 747.98, ...",
  "last_bar_timestamp": 1778782800,   // = 14:20 ET
  ...
  "spy": { "last": 747.98, ... }
}
```

**Tick 27 fired at 14:24:03 ET** (`automation/state/logs/heartbeat-2026-05-14.log` near line 600).

**Verified bar boundaries:** bar `14:20:00` opens at 14:20 ET, closes at 14:25 ET. At 14:24:03 ET, the 14:20 bar has 57 seconds remaining — it is NOT yet closed.

**Actual close of the 14:20 bar** (from CSV `backtest/data/spy_5m_2026-05-08_2026-05-14.csv` line ~482):
```
2026-05-14 14:20:00-04:00, O=748.26, H=748.30, L=747.81, C=748.01, V=372233
```

The actual 14:20 bar closed at **748.01**. Heartbeat saw and recorded **747.98**. That's not a rounding error — that's the live snapshot at 14:24:03 ET, mid-bar.

The reason text "14:20 5m bar close 747.98" is the model misunderstanding what TV gave it: it labels the in-progress bar as "closed" because that's what the doctrine told it to do.

### Real-world evidence — today's first live v15 trade (09:58 ET)

**Tick 9 fired at 09:57:03 ET, emitted ENTER_BULL at 09:58:35 ET.** Log line:
```
HB#2 09:58 ENTER_BULL | spy=745.35 ribbon=30c(BULL) vix=17.9(falling) bear=3/10 bull=10/11 htf=N/A
| level_reclaim+ribbon_flip, 10×745C limit 1.76, pending fill
```

**Bar boundaries around the trigger:**
- Bar 09:50 opened 09:50, closed 09:55: O=745.68, H=745.89, L=744.93, **C=745.02 (RED close)**
- Bar 09:55 opened 09:55, closes 10:00: O=745.02, H=745.47, L=744.25, **C=744.43 (RED close)**

**At 09:57:03 ET** the 09:55 bar is in-progress (2:03 elapsed of 5min). At 09:58:35 ET (when the order fired), 3:35 elapsed.

**Heartbeat saw `spy=745.35`.** Neither closed bar matches:
- 09:50 closed at 745.02 (the actual just-closed bar — RED rejection from 745.89 high)
- 09:55 closed at 744.43 (still-forming at decision time)

745.35 is consistent with a live snapshot in the middle of the in-progress 09:55 bar — somewhere between its open 745.02 and its eventual high 745.47.

**Implication for trigger detection:** the doctrine requires `level_reclaim` (reclaim a level on a CLOSED bar) AND `ribbon_flip` (5m ribbon stack flipped to BULL on a CLOSED bar). With actual closed-bar data:
- 09:50 close 745.02 — that's a RED bar that REJECTED 745.43 (today's PMH/resistance, per `journal/2026-05-14.md` line 23). It is NOT a level-reclaim. It is the OPPOSITE — it's a level rejection.
- 09:55 was in-progress; its eventual close 744.43 confirms continued red.

So the actual triggers didn't fire on the closed-bar data. They appear to have fired on the LIVE SNAPSHOT (745.35 > 743.79 prior-RTH-high reclaim, ribbon stack BULL at 30c spread on the LIVE numbers). The trade WORKED (+$913 by 11:57) because the bigger BULL move resumed after a deeper pullback. But the trigger that fired was technically misaligned with v15's own gate doctrine (G2: "trigger from live bar = BLOCK").

### Cross-reference: same class-of-bug as watcher_live T76

`backtest/autoresearch/watcher_live.py` lines 193-208 explicitly fixed this same problem in the watcher path TODAY (2026-05-14 11:30 ET). The fix:

```python
# T76 (2026-05-14 11:30 ET fix) — INCOMPLETE-BAR FILTER. yfinance's
# most recent 5m bar (the one currently in progress) returns volume=0
# and OHLC all equal to the snapshot price. That bar fails every
# watcher's volume gate (vol_mult > 1.1) → all 5 multi-day watchers
# silent. Diag-trail captured: 24 fires, 0 signals, latest_bar.volume=0
# while vol_baseline_20=425K. Fix: drop bars with volume==0 so we
# use the most recent CLOSED 5m bar.
_pre_filter_rows = len(rth)
rth = rth[rth["volume"] > 0].reset_index(drop=True)
```

**Difference between yfinance and TradingView in-progress behavior:**
- **yfinance**: in-progress bar has `volume=0` and OHLC all equal to snapshot — so the watchers' volume gate accidentally caught the bug (every signal silent).
- **TradingView**: in-progress bar has REAL accumulating volume and an evolving OHLC. The bar looks "real" — there's no volume==0 sentinel. The model has no easy way to distinguish in-progress from closed unless it's TOLD to compute `time_close vs now_et`.

So the heartbeat's bug is **more dangerous** than the watcher's pre-T76 bug — instead of silently no-op'ing, it silently SCORES an entry on incomplete OHLCV data, which can fire ENTER actions on phantom triggers.

---

## 4. Why this hasn't blown up yet (and why it will)

**Mitigants currently masking the bug:**
1. **3-min cadence with 5-min bars** means 2-of-5 ticks fire right after a bar close (timestamps 09:30, 09:45, 10:00, 10:15, 10:30, 10:45, 11:00, ...). The hash-based early-exit (`run-heartbeat.ps1` line 87) prevents re-firing the same bar across multiple in-progress reads, so the FIRST tick that catches a bar (often the post-close one at minute :00, :15, :30, :45) wins.
2. **`SKIP_STALE` gate** (heartbeat.md line 200) requires `volume - prior_volume ≥ 30%` to NOT skip. On in-progress bars early in their life-cycle, volume is low — so the gate often skips them. The gate is accidentally protecting against the bug for slow ticks.
3. **Ribbon EMA values from `data_get_study_values`** are computed off the live close including the in-progress bar — but EMAs are slow-moving, so the contamination is small for a single forming bar.
4. **VIX is cached** (10-min refresh), so VIX-based gates aren't tick-jittery.

**Why it WILL bite:**
1. **Early-bar in-progress reads with high volume** (e.g., 09:30, 09:33 fire — 09:30 bar has huge volume from open) defeat the SKIP_STALE 30% guard immediately. The very first 5-min bar of the day is the one most likely to be misread.
2. **Trigger conditions like `level_reject` evaluate `bar.high > level AND bar.close < level`** (heartbeat.md line 322). On an in-progress bar, `bar.high` is the live HIGH so far and `bar.close` is the live snapshot price. A bar that has SPIKED above a level mid-progress and is currently pulling back will fire `level_reject` on the live snapshot, even if the bar's eventual close is back above the level (no rejection).
3. **`sequence_rejection`** (line 324) checks `last_closed_bar.close < level` AND `bounce_history[].high_reached` decreasing. Both fields use bar attributes; in-progress bar.close is meaningless. False positives possible.
4. **The 09:58 trade today was wrong-bar-data lucky.** The next time it fires on misaligned data, the trade may not work out.

---

## 5. Specific recommendations (queued — NOT applied per OP 24 read-only)

### R1 — Doctrine fix in heartbeat.md (HIGH priority)

Replace lines 200, 214, 220 with explicit close-time arithmetic. Proposed wording:

```
3. `data_get_ohlcv(count=3, summary=true)` → bar list returned ordered oldest→newest.
   Compute now_et = current ET time. For each bar, compute bar_close_et = bar.time + 5min.
   Filter to bars where bar_close_et <= now_et. Last surviving bar = "last closed bar."
   IF last closed bar's time == loop-state.last_bar_timestamp AND
      filtered.last.volume - prior_volume < 30%, emit `SKIP_STALE`.

## SPY 5m + ribbon
`data_get_ohlcv(count=3, summary=true)` on BATS:SPY 5m. Apply close-time filter
(bar_close_et = bar.time + 5min, filter where bar_close_et <= now_et).
"Latest" = the LAST surviving bar after filter. The unfiltered bar[-1]
(in-progress) MUST NOT be used for scoring. Prior = filtered bar[-2].
```

Why count=3, not count=2: gives the model headroom — at any tick time, at most 1 bar at the head is in-progress, so count=3 guarantees ≥ 2 closed bars are returned for "latest" + "prior."

### R2 — Add a "bar age" guard in `run-heartbeat.ps1` (MEDIUM priority)

Pre-compute `seconds_into_current_bar = (now_et.minute * 60 + now_et.second) % 300`. If `seconds_into_current_bar < 30s` (i.e., we just rolled into a fresh bar), force a 30-second sleep before invoking Claude — gives TV time to register the bar boundary. Cheap protection against off-by-5-second race conditions.

### R3 — Diagnostic JSONL trail (MEDIUM priority)

Mirror the `watcher-live-diag.jsonl` pattern (watcher_live.py lines 338-374) for the heartbeat. Every fire writes one row to `automation/state/heartbeat-diag.jsonl`:
```json
{"fire_at": "...", "tick_id": N, "bars_returned": [{"time":..., "open":..., "high":..., "low":..., "close":..., "volume":...}, ...], "selected_bar": {...}, "now_et": "...", "seconds_into_bar": N}
```
Lets EOD-summary detect "tick X selected an in-progress bar" and grade it.

### R4 — Backtest the misalignment (MEDIUM priority)

Replay 2026-05-14 ticks against the CSV with both interpretations (in-progress-OK vs closed-bar-only). Quantify: how many heartbeat decisions today would have differed under the closed-bar-only interpretation? Hand off finding to the v15 ratification scorecard.

### R5 — Verify `data_get_ohlcv` actually returns the in-progress bar (LOW priority, sanity check)

Add a one-shot diagnostic call early next session (before market open if possible, or use the replay engine) that calls `data_get_ohlcv(count=5)` at a known mid-bar moment and dumps the response. Confirms the in-progress bar is in fact at index [-1], and confirms TV uses open-time labels (consistent with the CSVs). Removes any residual "is this really how TV behaves" uncertainty.

### R6 — Add to `OP-25 Lessons absorbed` (HIGH priority — doctrine-level)

A new lesson entry encoding: "TradingView `data_get_ohlcv` returns the live in-progress bar at index [-1]. UNLIKE yfinance (where in-progress = volume==0 sentinel), TV in-progress bars look real. The 'just-closed bar' must be computed by `bar.time + 5min ≤ now_et` filtering, not by trusting the index. Encoded in: heartbeat.md SPY 5m + ribbon section."

---

## 6. Files involved (absolute paths)

| File | Role |
|---|---|
| `C:\Users\jackw\Desktop\42\automation\prompts\heartbeat.md` | Production v15 prompt |
| `C:\Users\jackw\Desktop\42\automation\prompts\heartbeat-v14-prod-backup.md` | v14 fallback (same bug) |
| `C:\Users\jackw\Desktop\42\automation\prompts\heartbeat-v15-draft.md` | Draft v15 (same bug) |
| `C:\Users\jackw\Desktop\42\automation\prompts\aggressive\heartbeat.md` | Bold-account variant (same bug) |
| `C:\Users\jackw\Desktop\42\setup\scripts\run-heartbeat.ps1` | Wrapper (cadence + throttle + hash gate) |
| `C:\Users\jackw\Desktop\42\setup\scripts\run-heartbeat-aggressive.ps1` | Bold variant wrapper |
| `C:\Users\jackw\Desktop\42\setup\install-tasks.ps1` | Task scheduler config (lines 100-107) |
| `C:\Users\jackw\Desktop\42\automation\state\loop-state.json` | Per-tick state writes |
| `C:\Users\jackw\Desktop\42\automation\state\decisions.jsonl` | Per-tick decision ledger |
| `C:\Users\jackw\Desktop\42\automation\state\logs\heartbeat-2026-05-14.log` | Today's heartbeat fire log |
| `C:\Users\jackw\Desktop\42\backtest\autoresearch\watcher_live.py` | Reference for T76 fix (lines 193-208) |
| `C:\Users\jackw\Desktop\42\doctrine\rules-as-gates.md` | Gate G2 — closed-bar trigger check |
| `C:\Users\jackw\Desktop\42\backtest\data\spy_5m_2026-05-08_2026-05-14.csv` | Authoritative bar timestamps |
| `C:\Users\jackw\Desktop\42\journal\2026-05-14.md` | Today's trade context |
| `C:\Users\jackw\Desktop\42\docs\T48-FOLLOWUP-FIRE-EVENING-2026-05-14.md` | Sister T76 fix notes |

---

## 7. Bottom-line summary for J

1. **Cadence:** Heartbeat fires every 3 min via Windows Task Scheduler `Gamma_Heartbeat`. ~3-of-5 fires happen mid-bar (e.g., 09:33, 09:36, 09:39 within the 09:30-09:35 bar).
2. **Data source:** 100% TradingView MCP via `data_get_ohlcv(count=2, summary=true)` on BATS:SPY 5m. No CSV / yfinance / Alpaca fallback for live bar reads.
3. **The bug:** Doctrine SAYS "last closed bar" but the prompt doesn't tell the model HOW to compute that. TV returns the in-progress bar at index [-1]. Today's loop-state writes prove this — `last_bar_timestamp = 14:20 ET` written at 14:24:03 ET when the 14:20 bar was still 57 seconds from closing. Recorded `spy=747.98` ≠ actual 14:20 bar close `748.01`.
4. **Today's first v15 live trade (09:58 ENTER_BULL +$913)** was scored on a live mid-bar snapshot (745.35) when the actual just-closed bar (09:50→09:55 close 745.02) was a RED rejection of the 745.43 PMH — the OPPOSITE of a `level_reclaim` trigger. The trade worked but on misaligned data.
5. **Cross-reference T76:** Same class of bug as watcher_live's V=0 issue, except TV in-progress bars look "real" (no zero-volume sentinel) so the bug is harder to detect and more likely to fire false triggers.
6. **Fix is not deployed.** Per OP 24 (no live-doctrine changes from a read-only audit), recommendations queued for J ratification — see Section 5.

Audit complete. Awaiting J's call on whether to ship R1+R2+R3 tonight (after 4pm window, per OP 22) or queue for weekend ratification (per OP 13 — but the foot-gun lesson absorbed 2026-05-14 evening says "don't defer if it fits in the after-4pm block").

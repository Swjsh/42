# ORB Narrow-OR Gate — Engine Feature Spec

**Written:** 2026-05-21 ~05:35 ET by overnight session (pre-empts kitchen task f0f05fcc)
**Gate:** `MAX_OR_RANGE = 2.00` in `backtest/lib/watchers/orb_watcher.py`
**Verdict:** **NO heartbeat.md change needed.** Gate is fully self-contained.

---

## 1. How or_range is computed

```python
# In orb_watcher.py compute_opening_range(day_bars: pd.DataFrame) -> Optional[dict]:
OR_CLOSE_MINUTE = 9 * 60 + 55  # 09:55 ET (exclusive)
or_bars = day_bars[day_bars["timestamp_et"].apply(...) < OR_CLOSE_MINUTE]
high = or_bars["high"].max()    # ORH
low  = or_bars["low"].min()     # ORL
rng  = high - low               # or_range = ORH - ORL
```

The opening range covers SPY bars from 09:30 to 09:50 (5 bars at 5-min resolution).
`or_range` = ORH (max high of 09:30-09:50 bars) minus ORL (min low of same).

---

## 2. Gate enforcement point

The gate fires at the FIRST call to `detect_orb_break()` after 09:55 ET:

```python
def detect_orb_break(bar, day_bars, bar_idx_in_day, vol_baseline) -> Optional[WatcherSignal]:
    ...
    state = _get_or_init_state(date_str)
    if state["phase"] == "NEUTRAL":
        or_data = compute_opening_range(day_bars)   # <-- gate fires here
        if or_data is None:
            return None   # <-- wide ORB never advances past NEUTRAL
        state["or_data"] = or_data
        state["phase"] = "WATCHING"
```

`compute_opening_range()` returns `None` when `or_range >= MAX_OR_RANGE (2.00)`.
A wide ORB (≥ $2.00) never populates `state["or_data"]` — the state machine stays
at NEUTRAL and never emits a signal for the rest of the day.

---

## 3. Call chain from watcher_live.py to the gate

```
watcher_live.py:
  today_bars = rth[rth["timestamp_et"].dt.date == latest_date]  # all RTH bars
  signals = run_all_watchers(bar, today_bars, bar_idx_in_day, ...)

runner.py run_all_watchers():
  orb = detect_orb_break(bar, day_bars, bar_idx_in_day, vol_baseline_20)
                              ^^^^ = today_bars

orb_watcher.py detect_orb_break():
  or_data = compute_opening_range(day_bars)  # ← MAX_OR_RANGE gate here
  if or_data is None: return None             # ← wide ORB rejected
```

`today_bars` contains ALL RTH bars from 09:30 to now. `compute_opening_range()` slices
to the 09:30-09:50 window internally. The gate is fully self-contained.

---

## 4. Live deployment status (as of 2026-05-21)

| Check | Status |
|---|---|
| `MAX_OR_RANGE = 2.00` in orb_watcher.py | ✅ LIVE |
| Gate boundary: `rng >= MAX_OR_RANGE` (strict less-than for acceptance) | ✅ CORRECT |
| Fallback semantics when `MAX_OR_RANGE = None` (R&D disable) | ✅ Preserved (`rng > 5.00`) |
| Gym 70/70 PASS (incl. benchmark) | ✅ CONFIRMED |
| watcher_live.py passes `today_bars` to detect_orb_break | ✅ CONFIRMED |
| T82 warmup loop includes orb_watcher | ✅ CONFIRMED (lines 330-343 of watcher_live.py) |

---

## 5. Heartbeat.md — NO change required

**Q: Does heartbeat.md need to pass `or_range` to the watcher?**
**A: No.** The watcher receives `today_bars` which contains the raw price data. It
computes `or_range` internally from those bars. No external parameter injection needed.

**Q: Could the premarket or heartbeat pre-compute or_range and store it for the watcher?**
**A: Unnecessary.** Pre-computing and caching `or_range` would add complexity with no
benefit — `compute_opening_range()` runs in O(N_or_bars) ≈ O(5) time, effectively free.

**Q: Is there any risk of stale or_range if heartbeat fires before 09:55?**
**A: Handled.** The ORB state machine only initializes when `bar.time >= OR_CLOSE_MINUTE`.
Pre-10:00 bars skip OR computation entirely (NEUTRAL phase stays NEUTRAL until post-OR).

---

## 6. Future extension points

If the ORB direction gate (BEARISH ORB break-down) is ever added, the spec would change:
- The state machine currently only handles BREAKOUT_LONG (price > ORH)
- Adding BREAKOUT_SHORT would require: OR range same gate, direction detection inverted
- No heartbeat change needed even then — `day_bars` provides all necessary data

---

## 7. Evidence for the gate value

From `analysis/backtests/orb-narrow-or-walkforward/results.json` (deduped):
- Walk-forward OOS/IS Sharpe ratio = 0.667 (gate ≥ 0.50: PASS)
  - IS: N=21 unique bars, WR=76.2%  |  OOS: N=11 unique bars, WR=90.9%
  - Note: Original undeduplicated ratio was 1.149 on N=143 raw (4.5× inflation per L67).
    Deduped verdict is UNCHANGED — PASS — but with corrected per-unique-bar counts.
- Narrow (or_range < 2.00): N=32 unique bars, WR=81.2%, P&L=+$976 (deduped)
  - Raw inflated: N=143, WR=88.1%, P&L=+$4,597 (4.5× multi-tick inflation)
- Q2-2026 concentration: 16% deduped (vs 45% raw — dramatically better)
- 5/6 positive quarters (unchanged from raw analysis)
- Real-fills (OPRA): N=22 OPRA cases, WR=81.8% chart-stop-only (unaffected by dedup — OPRA-based)

**VIX gate was tested and FAILED:** VIX≥20 is the WRONG discriminator.
Q2-2026 profitable signals all had VIX<20. The correct discriminator is OR range.
See `analysis/backtests/orb-vix-gate/results.json`.

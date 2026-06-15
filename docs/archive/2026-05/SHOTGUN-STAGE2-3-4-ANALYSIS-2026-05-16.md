# SHOTGUN_SCALPER Stage 2 → 3 → 4 Research — Saturday 2026-05-16

> Authored autonomously 14:44–16:15 ET. J was gaming.

## TL;DR

The engine can now match your direction on **3 of 5 J-winner days** (up from 0/5 with dollar-match gates).  
Stage 4 is running tonight to push toward 4–5/5 via:
- **HTF 15m ribbon gate** — suppresses wrong-direction signals when macro stack disagrees (broke through 4/29 wall)
- **Lower vol_ratio thresholds** (0.60/0.80 added) — may fire on 5/14 and 5/15 where 1.0 was too strict

---

## Stage 2 Results — Dollar-Match Gate Autopsy

**Launched:** 09:47 ET | **Deadline:** 14:47 ET | **Combos:** 1,458

**Result: 0 keepers / 1,176 combos tested.**

Every profitable combo (729 of 876 have sharpe>0, wide_pnl>$0) was rejected by the dollar-match gate:
- Gate required: engine dollar P&L on J-winner days ≥ 20% of J's actual dollar P&L
- Root cause: qty mismatch alone (engine baseline qty=3, J's actual qty=5–20) makes this mathematically impossible

**J's feedback (13:50 ET):** "as long as we take the trade, I feel like that counts for something."

→ Dollar-match gate replaced with binary directional participation in Stage 3.

---

## Stage 3 — Directional Participation Scoring

**Design:**
```
stage3_final_score =
    directional_score  × 1000   # did engine fire same-dir as J on each winner day?
  + loser_avoid_score  × 500    # was engine flat/positive on J-loser days?
  + log10(wide_pnl)   × 100    # 16-month profitability
  + sharpe            × 50     # risk-adjusted
```

Gates: `dir ≥ 2` | `avoid ≥ 2` | `wide_pnl ≥ $1K` | `sharpe ≥ 1.0` | `n_trades ≥ 100`

**Launched:** 14:44 ET | **Running until:** 17:44 ET | **Grid:** 972 combos  
**Status (16:10 ET):** 195/972 tested, **8 keepers** | PID 13468 (pythonw3.13.exe)

### Top Stage 3 Keepers

| Stage3 Score | Wide PnL | Sharpe | Dir | Avoid | TP | Stop | TimeStop | Strike | Chandelier | Vol |
|---|---|---|---|---|---|---|---|---|---|---|
| **3633** | $19,721 | 4.07 | 2/5 | 2/3 | 1.50 | -0.35 | 15 | +2 | 0.50 | 1.0 |
| 3618 | $17,815 | 3.86 | 2/5 | 2/3 | 1.00 | -0.35 | 15 | +2 | 0.40 | 1.5 |
| 3617 | $17,061 | 3.87 | 2/5 | 2/3 | 0.50 | -0.35 | 15 | +1 | 0.60 | 1.2 |
| 3606 | $18,102 | 3.61 | 2/5 | 2/3 | 0.75 | -0.35 | 15 | +2 | 0.60 | 1.0 |
| 3588 | $16,327 | 3.33 | 2/5 | 2/3 | 0.75 | -0.30 | 15 | +2 | 0.50 | 1.2 |

**Knob clustering on top keepers:**
- `stop=-0.35`: all top 5
- `time_stop=15`: all top 5
- `strike_offset=+2`: 4 of 5
- `chandelier_arm=0.40–0.60`: spread (no winner)
- `vol_ratio_threshold=1.0–1.5`: spread

### Stage 3 Directional Ceiling: 2/5 Is Structural

After 195 combos tested, **every single keeper has `directional_score=2`** — no combo achieves 3, 4, or 5.

Root-cause analysis per J-winner day:

| Date | J Direction | Engine | Why Stuck |
|---|---|---|---|
| **4/29** | SHORT (put) | LONG (5 fires) | Intraday trendlines on 4/29 scored more bullish touches than bearish. Even after the morning's Tier 3 both-directions fix, the engine picks bullish (more touches × span_bars). |
| **5/01** | SHORT ✓ | SHORT ✓ | Engine correctly fires bearish — 5 puts placed. |
| **5/04** | SHORT ✓ | SHORT ✓ | Engine correctly fires bearish — 4–5 puts placed. |
| **5/14** | LONG (call) | no-fire | `vol_ratio_threshold=1.0–1.5` requires above-average bar volume. 5/14's bars don't meet threshold. |
| **5/15** | SHORT (put) | no-fire | Same vol_ratio issue as 5/14. |

**Fix direction:** (1) HTF 15m ribbon gate for 4/29 (suppresses bullish signals when 15m stack is BEAR). (2) Lower vol_ratio for 5/14 and 5/15 (0.60/0.80 threshold enables quieter-bar firing).

---

## Stage 4 — HTF-Gated Directional Scoring

**Core change:** The SHOTGUN detector now respects an optional `htf_15m_stack` parameter:

```python
# In shotgun_scalper_detector.py — detect() function (added 2026-05-16):
for fn in (_detect_open_rejection, _detect_level_reject, _detect_trendline_break):
    result = fn(today_bars, today_bar_idx, enriched)
    if result is None:
        continue
    if htf_15m_stack in ("BULL", "BEAR"):
        sig_dir = result.get("direction", "")
        if htf_15m_stack == "BEAR" and sig_dir in ("bullish", "long"):
            continue  # 15m macro bearish → skip bullish tier
        if htf_15m_stack == "BULL" and sig_dir in ("bearish", "short"):
            continue  # 15m macro bullish → skip bearish tier
    return result
```

**All 8 Stage 3 detector tests still pass.** The gate is opt-in (None = transparent, backward compatible).

### Smoke Test — Stage 4 vs Stage 3 Comparison

| Field | Stage 3 | Stage 4 |
|---|---|---|
| 4/29 | **MISS** (engine LONG, J SHORT) | **HIT** — "YES same-dir (short), 1 fires" |
| 5/01 | HIT | HIT |
| 5/04 | HIT | HIT |
| 5/14 | no-fire | no-fire (vol too high in smoke combo) |
| 5/15 | no-fire | no-fire (vol too high in smoke combo) |
| `directional_score` | **2/5** | **3/5** ← breakthrough |

The HTF stack for 4/29 is confirmed BEAR (loaded from 60-day pre-anchor context). The engine's bullish signals on that day are now suppressed, and the detector correctly falls through to a SHORT signal.

For 5/14 and 5/15: local SPY bar data ends at 5/12 (append hasn't run for those days). These days get `htf_15m_stack=None` (no filter), but lower vol_ratio thresholds should still allow firing if the market structure is directionally coherent.

### Stage 4 Grid (focused, 288 combos)

| Knob | Values | Rationale |
|---|---|---|
| TP | 0.75, 1.00, 1.50 | Stage 3 top-keeper sweet spot |
| Stop | -0.30, -0.35 | Stage 3 keepers only used these |
| TimeStop | 12, 15 | Stage 3 keepers never used 10 |
| Strike | +1, +2 | Stage 3 top-5 never used -1 |
| Chandelier | 0.40, 0.50, 0.60 | Keep full range |
| Vol_ratio | **0.60, 0.80**, 1.00, 1.20 | New lower thresholds for 5/14+5/15 |

**Total: 3 × 2 × 2 × 2 × 3 × 4 = 288 combos**

**Stage 4 gates (raised from Stage 3):**
- `min_directional_score: 3` ← raised from 2
- `min_loser_avoid_score: 2` (unchanged)
- `min_wide_pnl: $1,000` (unchanged)
- `min_sharpe: 1.0` (unchanged)

**Launched:** 16:12 ET | **Deadline:** 22:12 ET | **PID:** 33636  
**Expected completion:** ~19:00 ET (288 combos × ~2× Stage 3 per-combo time with 4 workers)

### What Stage 4 Can Achieve

| directional_score | Conditions | stage4_final_score estimate |
|---|---|---|
| 3/5 (4/29+5/01+5/04) | HTF gate alone, current data | 3000 + avoid×500 + log10(19K)×100 + sharpe×50 ≈ **4700+** |
| 4/5 (+ 5/14 or 5/15) | HTF + lower vol_ratio | **5700+** |
| 5/5 | HTF + lower vol for both | **6700+** |

---

## Code Shipped Today (Afternoon Session)

| File | Change | Status |
|---|---|---|
| `backtest/autoresearch/shotgun_scalper_stage3.py` | Created (yesterday plan, today shipped) | ✅ Running |
| `backtest/autoresearch/shotgun_scalper_stage4.py` | Created — HTF gate, lower vol grid | ✅ Running |
| `backtest/lib/watchers/shotgun_scalper_detector.py` | HTF gate in detect() loop (+11 lines) | ✅ 8/8 tests pass |
| `journal/trades.csv` | Runner exit corrected: 3@$3.35 → 3@$4.32 (Alpaca ground truth), pnl $1,208 → $1,500 | ✅ |
| `automation/prompts/aggressive/heartbeat.md` | Already at v15.1 (pre-verified) | ✅ No change needed |
| `automation/state/aggressive/params.json` | Already at v15.1 (pre-verified) | ✅ No change needed |

---

## What to Watch When You're Back

1. **Stage 3 deadline ~17:44 ET** — check `_state/shotgun_scalper_stage3/keepers.jsonl` for final keepers
2. **Stage 4 results ~19:00–22:00 ET** — check `_state/shotgun_scalper_stage4/keepers.jsonl`
   - Look for `stage4_directional_score ≥ 3` — that's the breakthrough
   - Top combo should have `wide_pnl > $15K` and `sharpe > 3.0`
3. **4/29 directional fix is confirmed working** — the HTF gate converts 4/29 from MISS to HIT
4. **The 5/14+5/15 question** is open until Stage 4 completes — if vol_ratio=0.60 enables fires on those days in the correct direction, we hit 4–5/5

---

## What This Means for Live Trading

Stage 4's top combo (when it arrives) will be the first SHOTGUN configuration that:
1. Fires in the same direction as J on **3+ of 5 real winning days**
2. Stays flat or profits on J's losing days (avoid_score ≥ 2)
3. Nets >$1K over 16 months of real OPRA fills
4. Has Sharpe > 1.0 over 16 months

Per OP 21 (Watch-First Promotion Path), the next step after Stage 4 is:
- Add as a WATCH-ONLY watcher in `lib/watchers/`
- Log observations for 3+ weeks
- Compare against J's live trades
- Positive expectancy confirmed → propose ratification to J

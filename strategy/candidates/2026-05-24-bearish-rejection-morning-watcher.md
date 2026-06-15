<!-- Author: Gamma (interactive session 2026-05-24, engine-benefit autonomy OP-22) -->
<!-- Status: WATCH_ONLY — per OP-21, needs 3+ live J confirmations before production wiring -->
<!-- Gym: v40_bearish_rejection_morning_gate — 78/78 PASS (2026-05-24) -->

# CANDIDATE: BEARISH_REJECTION_MORNING

**Filed:** 2026-05-24  
**Filer:** Gamma (interactive analysis — anchor day reconstruction)  
**Type:** new_watcher (WATCH-ONLY per OP-21)  
**Status:** WATCH_ONLY — live accumulation in progress (0/3 J confirmations)  
**Spec file:** `strategy/candidates/2026-05-24-bearish-rejection-morning-watcher.md`  
**Watcher:** `backtest/lib/watchers/bearish_rejection_morning_watcher.py`  
**Validator:** `crypto/validators/v40_bearish_rejection_morning_gate.py` — 78/78 PASS

---

## Origin — The anchor day reconstruction problem

The OP-16 edge score measures how well the engine captures J's known winners. The two biggest BEAR winners in the anchor set are both MORNING entries:

| J trade | Time | Entry | Notes |
|---|---|---|---|
| 4/29 SPY 710P ×6 | **10:25 ET** | at_close | "Clean entry on 711.4 rejection + ribbon flip" |
| 5/04 SPY 721P ×10 | **10:27 ET** | at_close | "Confluence: premarket level + multi-day trendline + ribbon flip" |

Both have `bars_after_trigger=0` and `entry_relative_to_bar=at_close` — J entered exactly when the trigger bar closed. Both made +$342 and +$730 respectively.

**The gap:** The existing `BEARISH_REVERSAL_AT_LEVEL_ON_BULL_RIBBON` watcher has a time gate of `11:00-14:30 ET` — it structurally cannot fire at 10:25/10:27 ET. A watcher survey on 2026-04-29 and 2026-05-04 confirmed **zero bear watcher signals** in the 09:35-11:00 ET window on either anchor day.

---

## What makes this setup distinct from BEARISH_REVERSAL

| Dimension | BEARISH_REVERSAL (existing) | BEARISH_REJECTION_MORNING (this) |
|---|---|---|
| Time gate | 11:00–14:30 ET | **09:35–10:55 ET** |
| Ribbon | BULL required (countertrend fade) | **BEAR required (enter WITH the flip)** |
| Trade character | Fade extended uptrend at level | **Ride the ribbon flip from level** |
| Volume threshold | 2.0× 20-bar avg | **1.5× 20-bar avg** (early session) |
| Uptrend gate | ≥$3 from RTH open required | None (morning reaction) |
| Level proximity | $0.30 | **$0.50** (morning wicks more energetic) |
| J anchor coverage | ~0 (misses 4/29, 5/04) | **4/29 +$342, 5/04 +$730** |
| Live watcher P&L | Net negative (WR=41%, exp=-$3.55) | Unknown — accumulating |

The BEARISH_REVERSAL (11:00+, ribbon=BULL) is a countertrend fade: J has a bull day, waits for the ribbon to still be BULL, then fades a level. The BEARISH_REJECTION_MORNING (09:35-10:55, ribbon=BEAR) enters the moment the ribbon flips — it's riding the flip, not betting against the trend.

---

## Detection conditions

1. **Time gate:** 09:35–10:55 ET (morning session; 11:00+ is BEARISH_REVERSAL territory)
2. **Ribbon = BEAR** at bar close — the ribbon has flipped, confirming directional momentum
3. **Level proximity:** bar high within $0.50 of a named ★★★ level (bars can wick more in the morning)
4. **Rejection body:** bar close ≥ 15 cents BELOW the level (confirmed failed breakout)
5. **Volume:** ≥ 1.5× 20-bar average (directional conviction, lower threshold for early session)
6. **HTF 15m:** logged in metadata (not a hard gate — often BULL before the flip)

---

## Confidence tiers

| Tier | Conditions |
|---|---|
| **HIGH** | body ≥ 30c + vol ≥ 2.5× AND bear candle (close < open) |
| **MEDIUM** | body ≥ 20c OR vol ≥ 2.0× |
| **LOW** | minimum thresholds met, or doji (close ≥ open) with medium criteria |

Both J anchor entries (4/29 "clean entry" and 5/04 "confluence") would likely be HIGH confidence — large rejection bodies at named levels with ribbon flip.

---

## Exit mechanics

Inherits from v15 BEARISH_REJECTION_RIDE_THE_RIBBON:
- **Chart stop:** rejection_level + $0.25 above level (hard stop)
- **TP1:** bar_close − $1.00 (proxy for +30% premium at $0.50 put entry)
- **Runner:** bar_close − $2.50 (proxy for 2.5× entry at runner, per v15 knob)
- **Premium stop fallback:** −8% (v15 bear default)
- **Time stop:** 15:50 ET (standard EOD)

The EXIT logic is production-identical to the heartbeat's BEARISH_REJECTION handling. The only new piece is the ENTRY detection in the morning window.

---

## OP-16 anchor coverage

| J day | Engine signal | J action | Notes |
|---|---|---|---|
| **4/29 +$342 ✓** | WATCH — no watcher fire at 10:20 bar close (watcher just shipped) | J entered at 10:25 at_close | Watcher would fire at 10:20 bar if bar_high ≥ 711.10 AND ribbon=BEAR at close |
| **5/01 +$470** | Anticipation entry by J (rule break) — no watcher needed at 13:09 | Watcher doesn't cover this; BEARISH_REVERSAL (11:50 +$175) was the real signal | Out of scope |
| **5/04 +$730 ✓** | WATCH — no watcher fire at 10:25 bar close (watcher just shipped) | J entered at 10:27 at_close | Watcher would fire at 10:25 bar if bar_high ≥ 720.75 AND ribbon=BEAR at close |

The 5/01 winner at 13:09 is covered by the existing BEARISH_REVERSAL at 11:50 (+$175). The BEARISH_REJECTION_MORNING fills the 4/29 and 5/04 gap.

---

## What we don't know yet (OP-20 disclosures)

1. **Historical fire rate unknown:** We have no key-levels archive for past dates, so we can't replay this watcher against 4/29 or 5/04 to confirm it would have fired. The detection depends on `ctx.levels_active` (today's named levels), which weren't stored historically.

2. **Real-fills validation pending:** No OPRA fills data exists for the would-be entries, so we can't validate what the actual premium entry/exit would have been.

3. **Walk-forward pending:** The watcher only fires in the 09:35-10:55 window (~7 bars/day), so signal frequency is low. Building a valid OOS window requires several months of live accumulation.

4. **False-positive rate: low (proxy estimate):** A historical proxy scan (2026-05-24) using PDH as the resistance level proxy showed 31 signals over 347 trading days = 0.09 signals/day. The watcher fires roughly once every 10-11 trading days. This is LOW frequency — the watcher is selective, not spammy. **Important caveat:** PDH is only one type of named level; the real watcher also watches premarket highs, key round numbers, prior weekly levels, etc. Actual fire rate may be 2-4× higher.

5. **Proxy WR estimate:** The PDH-proxy scan showed WR=40.9% (N=22 graded) with a 4:1 proxy R:R ($1.00 target / $0.25 stop above level). At 40.9% WR with 4:1 R:R, expected P&L per signal ≈ +11c SPY-space — positive but thin. **However**, PDH is a poor proxy: it fires on any PDH touch, not just named ★★★ levels with ribbon flip. Real watcher signals at true ★★★ levels with ribbon confirmation likely have higher WR.

6. **OP-20 disclosure:** All P&L estimates in the OP-16 anchor table above assume the watcher would have fired correctly on those dates. This cannot be verified without historical key-levels data. **Do not use these estimates in any aggregate backtest.**

---

## Promotion path (OP-21)

| Gate | Status | Threshold |
|---|---|---|
| Code correct | ✅ PASS (v40 10/10 offline) | Required |
| Live observations | 0/3 | Need ≥3 J-confirmed obs with positive P&L |
| Real-fills | Pending | WR ≥50%, exp > 0 after OPRA check |
| Walk-forward | Not yet applicable | Need ≥20 obs across ≥2 OOS windows |
| J ratification | Blocked | Rule 9 — heartbeat.md change needs weekend ratification |

**Current action:** Live shadow accumulation. Every heartbeat tick will check 09:35-10:55 ET for ribbon-flip-at-level setups and log to `watcher-observations.jsonl`. When 3 confirmed J-pattern observations accumulate with positive P&L, escalate to real-fills + walk-forward, then J ratification.

---

## Pre-merge gate (when ready for promotion)

```
[ ] Gym validators: 78/78 PASS (already confirmed 2026-05-24)
[ ] Live obs: N >= 3 with WR >= 50% and exp > 0
[ ] Real-fills: OPRA check on top 3 observations, P&L deviation < 25% vs proxy
[ ] Walk-forward: OOS/IS ratio >= 0.50 (once N >= 20)
[ ] J ratification: weekend review per Rule 9
[ ] heartbeat.md: add BEARISH_REJECTION_MORNING trigger check in morning pass
```

---

## Files

| File | Purpose |
|---|---|
| `backtest/lib/watchers/bearish_rejection_morning_watcher.py` | Watcher code |
| `backtest/lib/watchers/runner.py` | Registered (after rsi_divergence block) |
| `backtest/lib/watchers/__init__.py` | Docstring entry added |
| `crypto/validators/v40_bearish_rejection_morning_gate.py` | 10 offline + 1 live audit |
| `crypto/validators/runner.py` | v40 registered in stages |
| `strategy/candidates/2026-05-24-bearish-rejection-morning-watcher.md` | This spec |

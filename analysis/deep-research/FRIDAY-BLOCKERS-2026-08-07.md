# FRIDAY-BLOCKERS-2026-08-07 — Lane 1: Name and Mechanism

> Written 2026-08-07 ~12:15 ET (market open — this lane wrote analysis/** + backtest/tools/** only;
> zero trading-path writes). Data artifact: `FRIDAY-BLOCKERS-2026-08-07.json`.
> Runner: `backtest/tools/friday_blockers_lane1_2026_08_07.py` (re-runnable for the evening addendum).
> Clock verified at session start: `2026-08-07 12:01:21 Friday EDT / market_hours=True` (et_clock.py).

## Verdict (one screen)

| Filter | Identity (bull side) | Verdict | Basis |
|---|---|---|---|
| **7** | `_bullish_volume_divergence_failed` (filters.py:1352) | **POLICY** — working as coded, inputs feed-consistent (6/6 sole-blocks reproduce on BOTH IEX and SIP). Its design weakness (no minimum body/volume on the "breakout" leg) is a relax/qualifier question → Lane 2 L2-4 prereg + battery. | §1, §4 |
| **10** | `buyer_pressure_bar_v11` (filters.py:1343) | **DEFECT (calibration fidelity)** — the 0.7× constant was ratified on SIP-cache bars (v11) but is applied live to IEX ratios. **34–35% of its sole-elite refusals evaporate on the ratified feed.** NOT the suspected mixed-feed bias (refuted, §2). Deployable fix is NOT a feed switch (SIP is 15-min delayed on this key — verified live, §2c). Fix = threshold recalibrated/validated against the live IEX distribution → frozen prereg cells (L2-3) + the knob-split staged below. | §2, §4 |

**Ships tonight (staged, §6):** heartbeat_core knob-split so bull f10 becomes independently armable
(zero behavior change by default — today bull f10 and bear f9 share ONE params key).
**Does NOT ship tonight:** any threshold change (waits for L2-3 battery verdict + IEX-sensitivity check).

---

## 1. Filter identity + the three exhibits, reconstructed exactly

**Filter 7 (bull)** = `_bullish_volume_divergence_failed(ctx.prior_bars, ctx.bar_idx)` — filters.py:1182-1186 call, body at 1352-1373:

```python
# candidates = [(idx-1, idx), (idx-2, idx-1), (idx-2, idx)]   # rec can be the CURRENT bar
if bo["close"] <= bo["open"]: continue          # ANY green bar qualifies as "breakout"
if rec["close"] < rec["open"] and rec["volume"] >= bo["volume"]: return True  # block
```

No minimum body or volume on the breakout leg: **a +6-cent green bar with 17k IEX shares arms the
invalidation**, and any later red bar trivially exceeds its volume.

**Filter 10 (bull)** = `buyer_pressure_bar_v11(ctx.bar, ctx.vol_baseline_20, vol_mult=f10_vol_mult)` —
filters.py:1206-1212, body at 1343-1349: trigger bar must be green AND volume ≥ 0.7 × mean(prior 20 bars).
Also blocks when `ribbon_now is None` (1211-1212) — never the case today (ribbon=BULL logged every exhibit).

**Exhibit reconstruction — 3/3 match the live ledger** (same IEX feed, same `_build_payload`
window math: RTH-only → last 150 bars → trig = n−2; recon script validated before any measurement):

| Tick | Trig bar | Ledger block | Reconstructed condition that failed |
|---|---|---|---|
| 10:15:03 | 10:05 | [10] | GREEN bar, vol 17,148 < 0.7 × 27,433 = 19,203 (ratio **0.625**) — volume leg, missed by 2,055 IEX shares. SIP ratio 0.51 → **legit low-volume bar on both feeds, NOT a feed flip** |
| 10:21:03 | 10:15 | [7] | f10 **PASSED** (ratio 0.999, green +$1.82 — the actual breakout bar). f7 blocked: green 10:05 bar (body **+$0.06**, v=17,148) = "breakout"; red 10:10 bar (v=30,662 ≥ 17,148) = "failed recovery". **Reproduces on SIP too** — not a feed artifact; it is the no-minimum-breakout-leg design |
| 11:46:04 | 11:40 | [10] | Trig bar RED (773.42 → 773.17) — close≤open leg, as coded (ratio 0.651 would also fail). SIP agrees red |

The one tick today where the engine's own buyer-pressure test agreed with the entry (10:15 bar,
level_reclaim + confluence, PAY-cohort shape) was killed by filter 7's noise-armed invalidation.

## 2. Volume provenance — the suspicion tested, refuted, and replaced

**(a) The live path is single-feed, and has been since 2026-06-26.**
`heartbeat_core._fetch_spy_5m()` (line 279-296) makes ONE REST call, `feed=iex`; `_build_payload`
computes BOTH `ctx.bar.volume` (line 622-623) AND `vol_baseline_20` (line 599:
`win["volume"].iloc[trig_idx-20:trig_idx].mean()`) from that same frame. `git log -L 279,296` shows
exactly one commit touching it: 667217a1 (2026-06-26). **The suspected SIP-history-vs-IEX-live mix
inside the ratio does not exist**, and the 08-03 IEX-tail ship (level-refresh path, spy_5m cache)
never touches filter 10's inputs.

**(b) "Structurally biased low" — refuted at population level.**
All matched RTH bars 07-28→08-07 (n=653): IEX pass rate **0.335** vs SIP **0.349** — no systematic
depression. What IS there: IEX prints a **median 3.6%** of SIP volume with p10–p90 share 2.1%→5.4%
(a 2.5× swing bar-to-bar, CV 0.35), ratio correlation only **0.884**, so the ratio test is NOISY on
IEX, not biased: **13.7% of all bars** get a different f10 answer than the ratified feed
(7.6% IEX-fail/SIP-pass, 6.2% IEX-pass/SIP-fail), and the green/red leg misreads the consolidated
tape on **5.2%** of bars. Conditioning on refusals concentrates the noise: of 176 sole-[10]-elite
refusal ticks (44 unique bars), **62 ticks / 15 bars (34–35%) pass f10 on SIP**. Steady every
session (1/2, 0/2, 2/6, 4/12, 4/8, 1/5, 3/9) — chronic since IEX went live, no 08-03 break.

**(c) Why the naive fix is unavailable — live entitlement test, 12:11 ET today:**
`feed=sip` request returned latest bar **15:55Z** while `feed=iex` returned **16:10Z** (now = 16:11Z).
**SIP is 15-minute delayed on this key**; the trigger bar is 5–11 min old — inside the delay window.
The IEX choice is forced by entitlement, not an oversight. Fix classes that remain:
1. **Recalibrate the threshold against live-IEX ratios** — the frozen prereg's relax cells
   (0.5 / 0.35 / 0.0) approximate this; the L2-3 battery verdict MUST add an IEX-sensitivity check
   (a cell ratified on SIP still deploys onto IEX ratios).
2. **Pay for real-time SIP** — real-money vendor decision = J's (OP-0 #1-adjacent; not staged).
3. NOT an option: hybrid SIP-baseline/IEX-trigger — that would CREATE the mixed-feed ratio the
   suspicion feared.

**(d) Knob wiring gap (blocks any bull-only arming):** heartbeat_core.py:647+654 —
`_vm = account_params.get("filter_9_vol_multiplier", 0.7)` feeds BOTH `bear_kwargs f9_vol_mult`
AND `bull_kwargs f10_vol_mult`. **One knob, two filters.** The frozen prereg's kill rule
("restore f10_vol_mult to 0.7, single key") assumes a bull key that does not exist. Split staged in §6.

## 3. Pass-rate history — 9 logged sessions (label: `bull_blockers` only exists since 07-28)

The ledger did not log `bull_blockers` before 2026-07-28 (field absent in 100% of safe rows
06-25→07-27, present in ~100% after). "Last 15 sessions" is therefore answerable for **9**:

| Session | Ticks | f10 block % | f7 block % | sole-[10] elite | sole-[7] elite | bull-trigger ticks |
|---|---|---|---|---|---|---|
| 07-28 | 386 | 67.6 | 30.1 | 3 | 0 | 213 |
| 07-29 | 375 | 66.7 | 20.0 | 8 | 1 | 153 |
| 07-30 | 410 | 69.5 | 25.6 | 0 | 0 | 31 |
| 07-31 | 386 | 62.4 | 24.9 | 21 | 0 | 196 |
| 08-03 | 386 | 58.3 | 32.4 | 56 | 0 | 125 |
| 08-04 | 390 | 51.5 | 25.9 | 28 | 0 | 92 |
| 08-05 | 386 | 76.7 | 22.3 | 22 | 0 | 110 |
| 08-06 | 388 | 71.1 | 28.6 | 0 | 0 | 100 |
| **08-07** (thru ~11:55) | 159 | **81.8** | **47.2** | **38** | **5** | 88 |

(sole-elite = bull_score ≥ 9 AND bull_blockers exactly [10] / [7]; safe-account rows; bold differs
only in f11 min_triggers, f7/f10 inputs identical.) No structural break at 08-03 — block rate moves
with market character. Today is the worst f10+f7 day on record, on a +2.7-point SPY grind.

## 4. Today's sole-blocked ELITE series (10:14–11:55, unique trigger bars)

| Trig bar | SPY | Blocker | IEX says | SIP says | Class |
|---|---|---|---|---|---|
| 10:05 | 770.50 | 10 | 0.625 vol-fail | 0.51 vol-fail | legit both-feed refusal |
| 10:15 | 771.69 | 7 | block (10:05 pair) | block (same pair) | POLICY design, not feed |
| 10:20 | 772.05 | 10 | 0.678 vol-fail | 0.647 vol-fail | both-feed (IEX missed by 0.022) |
| 10:25 | 773.13 | 10 | 0.679 vol-fail | 0.616 vol-fail | both-feed |
| 10:40 | 771.79 | 10 | **RED bar** | **GREEN**, 0.537 vol-fail | green-leg feed misread (outcome same) |
| 11:05 | 773.02 | 10 | 0.477 vol-fail | **1.714 PASS** | **FEED FLIP** — SIP volume surge invisible to IEX |
| 11:10 | 773.07 | 10 | 0.667 vol-fail | **0.881 PASS** | **FEED FLIP** |
| 11:20 | 773.54 | 10 | 0.582 vol-fail | **0.756 PASS** | **FEED FLIP** |
| 11:40 | 773.17 | 10 | RED bar | RED bar | legit (pullback bar) |
| 11:45 | 773.58 | 10 | 0.524 vol-fail | 0.49 vol-fail | legit both-feed |

3 of 9 f10-refused bars today are feed flips, clustered exactly on the 11:05–11:20 leg where SPY
broke 773. Pricing of what these refusals cost is Lane 2's job (per-tick est_premium track, EST-labeled).

## 5. Standing evidence honored

- Frozen prereg found: `analysis/recommendations/bull-f10-buyer-pressure-prereg-2026-08-04.json` —
  cells f10_vol_mult {0.7, 0.5, 0.35, 0.0}, full gate battery (OOS-positive added cohort, WF ≥ 0.70
  or disclosed-null, sub-window ≤ 50%, anchor no-regression, drop-best, n ≥ 20 floor). Runner is
  queued as BULL-F10-PREREG-RUNNER (automation/overnight/queue.md:14) and mapped to task **L2-3** —
  Lane 1 does not duplicate it. **Addendum required of L2-3 by this lane's finding:** report each
  cell's added-cohort BOTH on SIP ratios (the battery's native feed) AND re-screened on IEX ratios
  for the post-06-26 window — a cell that only clears on SIP is not cleared for the live path.
- WEEK-ORDER-2026-08-03.md:79: "filter 10 buyer-pressure | +$4,535 / 2d | prereg frozen, runner
  queued" — today is the third exhibit.
- Rule-2 firewall from the prereg stands: filter 11 is not liftable by any of this.
- F7 has no prereg yet → L2-4 freezes it (this doc supplies the mechanism: breakout-leg minimum
  body/volume qualifier is the discriminating cell family, alongside lift/relax).

## 6. STAGED FOR 15:55 — knob-split (fix-class, zero behavior change)

**File:** `setup/scripts/heartbeat_core.py` (TRADING-PATH — apply only after 15:55 ET).

**Diff (exact):** after line 647 (`_vm = account_params.get("filter_9_vol_multiplier", 0.7)`) insert:

```python
    # KNOB-SPLIT 2026-08-07 (FRIDAY-BLOCKERS Lane 1): bull f10 armable independently of bear f9.
    # Absent key -> exactly _vm -> byte-identical to pre-split behavior. Guard:
    # backtest/tests/test_f10_knob_split_2026_08_07.py
    _vm_bull = account_params.get("filter_10_vol_multiplier_bull", _vm)
```

and on the `bull_kwargs` line (654) change `f10_vol_mult=_vm` → `f10_vol_mult=_vm_bull`.

**No params key is added tonight** — key stays absent in both params files, so live behavior is
byte-identical. The split only makes whatever cell L2-3 ratifies armable bull-side without touching
bear f9.

**Guard (new file `backtest/tests/test_f10_knob_split_2026_08_07.py`, source-contract style per
repo precedent `test_enter_bull_in_placement_path`):**

```python
"""Guard: bull f10 vol-mult knob is split from bear f9 (FRIDAY-BLOCKERS-2026-08-07 sec 6).
REDs if bull_kwargs silently re-couples to _vm or the fallback chain breaks."""
import re
from pathlib import Path

SRC = (Path(__file__).resolve().parents[2] / "setup" / "scripts" / "heartbeat_core.py").read_text(encoding="utf-8")

def test_bull_knob_reads_own_key_with_vm_fallback():
    assert re.search(r'_vm_bull\s*=\s*account_params\.get\(\s*"filter_10_vol_multiplier_bull"\s*,\s*_vm\s*\)', SRC)

def test_bull_kwargs_use_split_knob_and_bear_keeps_vm():
    assert re.search(r'"bull_kwargs":.*f10_vol_mult=_vm_bull', SRC)
    assert re.search(r'"bear_kwargs":.*f9_vol_mult=_vm[,)]', SRC)
```

**RED-proof:** revert the diff → both tests fail (asserts reference `_vm_bull` which won't exist).
**Revert:** delete the inserted `_vm_bull` line and restore `f10_vol_mult=_vm` (or `git revert` the
single commit). Kill rule unchanged from the prereg.

## Labels / caveats

- Reconstruction bars re-fetched post-hoc; late corrections possible. Fidelity check: recon
  reproduced the live block on **all 176/176** sole-[10] ticks (iex_pass=0) and 3/3 named exhibits.
- sole-[7] n=6 ticks / 2 bars — **n-small**; F7's POLICY verdict rests on mechanism + feed
  reproduction, not on cohort statistics.
- Today's rows end ~11:55 ET (mid-session snapshot); evening re-run of the tool extends them.
- Pre-07-28 block-rate history does not exist (field not logged) — do not read the JSON's absent
  sessions as 0% block.
- All P&L claims herein are citations of prior lanes' work; this lane priced nothing.

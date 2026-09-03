# D7 — Structure veto misclassification (safe-2, 2026-09-03 11:11–11:35 ET)

Stamp: 2026-09-03T11:40 ET (report finalized ~11:50 ET, market open, live-only read-only pass).
Scratch script: `backtest/tools/dissect_structure_veto_misclass.py`. Raw data: `dissect-structure-veto-misclass.json` in this folder.

## Verdict

**DEFECT.** `_classify_sameday_5m` (`backtest/lib/engine/engine_cli.py:192-224`) calls only the
"tentative" fallback trend read (`classify_trend`), never the module's own documented
"authoritative" state machine (`walk_structure`), and the swing detector it feeds
(`find_swing_points(..., window=2)`) structurally excludes the newest 2 bars (10 min) of
whatever's fed to it from ever becoming a pivot. Today it labeled SPY "downtrend" at 11:11,
11:16, 11:21, 11:26 and 11:31 ET while SPY ran from 770.73 to 772.93 — a **continuous rally**,
6+ points above the session low (767.78 @ 10:10) and climbing the entire time the veto fired.
Of the 5 episodes, 2 now have a completed 30-min forward window (11:11 and 11:16 entries) and
**both** show the blocked bull side would have gained (+$1.735 and +$1.08 SPY respectively —
veto wrong both times); the other three are still in-flight as of this report (11:48 ET last
tick) but every interim read is likewise higher or flat, not lower. An
**independent, already-computed, sound-replay-engine instrument** (`gate_expiry_check.py`,
reading `automation/state/gate-registry-status.json`) reaches the same conclusion from its own
angle: the refused cohort is net **POSITIVE EV**, contradicting the gate's own thin ratifying
study — and a fix (drop `structure_veto_enabled` to `false`) was pre-registered over a month ago
and never shipped.

---

## 1. The mechanism, read from the code

### 1a. `_veto_side` (engine_cli.py:177-187) — unconditional on the trend label

```python
def _veto_side(side, trend) -> bool:
    if side == "P": return trend == "uptrend"
    if side == "C": return trend == "downtrend"
    return False
```
No magnitude, no distance-from-low check, no minimum-move gate — any `trend=='downtrend'` blocks
every bull ("C") entry, however far price has already reclaimed.

### 1b. `_classify_sameday_5m` (engine_cli.py:192-224) — the tentative fallback, not the authoritative one

```python
swings = find_swing_points(bars, window=2, inclusive_right=True)   # line 220
labeled = label_swings(swings)
return classify_trend(labeled)
```

`crypto/lib/market_structure.py`'s own module docstring distinguishes two trend reads:

> `classify_trend` — *"Tentative trend from the last TWO highs and last TWO lows jointly... Used
> as the fallback before any confirmed structure break; `walk_structure` gives the authoritative
> trend."*
> `walk_structure` — *"the authoritative BOS/CHoCH state machine"* that only flips on a confirmed
> break, maintaining state chronologically instead of re-deriving from whatever two swings happen
> to be visible right now.

`grep -n "walk_structure" backtest/lib/engine/engine_cli.py setup/scripts/heartbeat_core.py`
returns **zero matches** — the live engine has never called the authoritative function. It ships
with the module's own self-labeled placeholder.

`classify_trend`'s rule (market_structure.py:100-122): take the last 2 swing highs and last 2
swing lows found anywhere in the fed bar list; `downtrend` iff both pairs are non-increasing.
This has no concept of recency-weighting or confirmed breaks — a downtrend read persists exactly
as long as no NEW pivot has been confirmed above it, however stale the comparison swings are.

### 1c. `find_swing_points` (`crypto/lib/trendlines.py:41-72`) — a hard-coded confirmation lag

```python
for i in range(window, n - window):   # window=2 here
    ...
```
A bar at index `i` needs `window` bars *after* it to qualify as a swing. With `window=2`, indices
`n-2` and `n-1` (**the newest 2 bars fed in — the most recent 10 minutes of price action, always**)
can never be evaluated as pivot candidates, full stop, independent of what those bars actually
look like. Any reversal in progress is invisible to the classifier until it is at least 10 minutes
old.

### 1d. `heartbeat_core.py` — which bars, and an extra minute of lag on top

`sameday_5m_bars` (heartbeat_core.py:993-1013) is built from the FULL RTH `df` (not the bounded
`win`), masked to `(date == trig_date) & (ts <= trig_ts)` — i.e. every 5m bar of the session up to
and including the current trigger bar, oldest-first. That part is sound (no future bars leak in).

But the trigger bar itself already carries lag: empirically (from `trigger_bar_et` /
`bar_freshness.bar_et` logged every tick today), a bar labeled by its **interval start** `T` first
becomes the "current" trigger bar at tick `T+6` minutes — one minute *after* its `[T, T+5)` window
closes at `T+5` (confirmed: bar `09:30` is absent through tick `09:35:03`, present as of tick
`09:36:03`; bar `11:10` absent through `11:15:xx`, present at `11:16:03`). So at the moment the
veto fires, the newest bar in `sameday_5m_bars` is already ~1-6 minutes stale, and (1c) then adds
a further mandatory 2-bar/10-minute blind spot on top before anything in it can register as a new
swing. Total minimum lag from "now" to "the newest thing the classifier can possibly react to":
roughly 10-15 minutes, structurally, every single tick — this is not a today-only glitch.

**Bar freshness was NOT stale by the engine's own check** (`bar_freshness.stale: false`,
`age_min` 6-8 at each veto tick) — the defect is not a data-staleness bug the engine already
guards against; it's a swing-confirmation-lag defect the engine has no guard for at all.

---

## 2. Reconstruction from today's tape — does it reproduce "downtrend"?

Per-minute `spy` snapshots for account=safe, date=2026-09-03 (`automation/state/core-decisions.jsonl`,
read-only) were bucketed into 5-min OHLC (open=first sample in bucket, close=last, high=max,
low=min — **APPROXIMATE**: ~5 one-per-minute polls per bucket, not true continuous-tick OHLC, so
intrabar extremes can be missed relative to whatever real feed `df` uses). The real
`classify_trend`/`label_swings`/`find_swing_points` functions were imported (not reimplemented)
and run against the reconstructed bars, sliced to the exact `trigger_bar_et` each tick logged.

| Tick (ET) | Logged verdict | Logged `structure_reason` | SPY | Bars fed | Reconstructed trend |
|---|---|---|---|---|---|
| 11:16:03 | SKIP_STRUCTURE_VETO | downtrend | 771.50 | 21 (09:30→11:10) | **range** |
| 11:21:03 | SKIP_STRUCTURE_VETO | downtrend | 772.02 | 22 (09:30→11:15) | **range** |
| 11:27:03 | HOLD* (nearest tick 11:26/11:28 = veto) | downtrend | 772.11 | 23 (09:30→11:20) | **range** |

*The 11:27 target tick itself logged HOLD (no bull triggers that exact minute); the veto episode
straddling it ran 11:26:03–11:28:03. Reconstruction shown uses the nearest ≤ target row.

**Does not byte-for-byte reproduce "downtrend"** — my proxy bars find only 4 swings across the
whole session (H 769.79@09:45, L 767.78@10:10, LH 768.87@10:20, HL 767.96@10:35), giving
highs-down/lows-up = mixed = `range`, not `downtrend`. The live system, reading the real
continuous-tick 5m bars, evidently found a lower low somewhere in the 10:35-ish bar my once-a-
minute sampling missed, tipping its low-pair to non-increasing too. **This is an approximation
gap, not a refutation of the mechanism**: both readings agree on the load-bearing fact — the
*newest* confirmable high in the fed bar list is stuck at **10:20 (768.87 in my recon)**, 56-67
minutes stale relative to the 11:16-11:27 triggers, because bars 11:05 onward (which contain the
actual 770.7→772.1 push) can never be pivot candidates per (1c) above. Whether the last-two-pair
comparison nets out to "range" or "downtrend" is sensitive to bar-construction noise; that the
newest real price action is invisible to it either way is not. Full reconstructed session bar
table and swing dumps: `dissect-structure-veto-misclass.json`.

**Root-cause statement (one sentence):** the veto reads a trend classifier that (a) is the
module's own self-labeled non-authoritative fallback, (b) is mathematically forbidden from
seeing the newest 10 minutes of price action, and (c) compares whatever two pivots happen to
still be visible with no recency weighting — so a multi-bar rally reads as "downtrend" for as
long as its own newest highs remain unconfirmed, which by construction is always.

---

## 3. History — every SKIP_STRUCTURE_VETO in the retained ledger

`automation/state/core-decisions.jsonl` (READ-ONLY) currently retains **2026-08-26 through
2026-09-03 only** — 7 full sessions + today. It does **not** reach back to 2026-06-26 when the
veto shipped (commit `26832c07` / `667217a1`, 2026-06-26 15:10:58 -0600); that history has rolled
off under the ledger's retention policy (OP-22). This is disclosed, not worked around.

**Within the retained window: every single SKIP_STRUCTURE_VETO row is from today.** Raw ticks:
17 (1/min re-logging of the same blocked signal). Deduped into same-side, same-date,
≤2-min-gap episodes: **5**, all `side=C` (bull blocked, structure="downtrend"), all today:

| Episode | First tick | Last tick | Entry SPY | SPY @ +30m | Move | Blocked side would've won? |
|---|---|---|---|---|---|---|
| 1 | 11:11:04 | 11:13:03 | 770.73 | 772.465 | **+1.735** | **YES — veto wrong** |
| 2 | 11:16:03 | 11:18:03 | 771.50 | 772.58 | **+1.08** | **YES — veto wrong** |
| 3 | 11:21:03 | 11:23:03 | 772.02 | not yet elapsed | interim +0.56 (@11:48, 27m) | trending yes |
| 4 | 11:26:03 | 11:28:03 | 772.11 | not yet elapsed | interim +0.47 (@11:48, 22m) | trending yes |
| 5 | 11:31:03 | 11:35:04 | 772.93 | not yet elapsed | interim −0.35 (@11:48, 17m) | too early to call |

2 of 5 episodes now have a completed +30-min readout (last tape row at report-finalization:
11:48:03 ET, SPY 772.58) — **both wrong**, both cost the blocked bull side gains (+$1.735,
+$1.08 SPY). Episodes 3-5 are genuinely still in-flight — reported as **interim/UNVERIFIED**, not
claimed as final. **0/2 completed 30-min windows favored the veto.** n=2 is too small for a
non-degenerate bootstrap CI, so none is reported (stated as n=2, not inflated with a fake
interval) — the population-level evidence for this failure mode comes from the independent
`gate_expiry_check.py` instrument below (n=5, n=11 historically), not from this report's own
2-episode sample.

**Zero SKIP_STRUCTURE_VETO fires 2026-08-26 through 2026-09-02** in the retained window,
including on winner days **2026-08-27 and 2026-08-28** (both inside the retention window) — the
veto had **zero effect, neither helped nor cost**, on those two winning days. **2026-08-06 and
2026-08-13** are outside the retained window; no row-level data exists to check them (disclosed
gap, not filled with a guess).

### Independent confirmation — the gate already has its own automated verdict

Two separate, already-computed, sound-replay-engine instruments (not built for this report) bear
directly on the same question:

- **`automation/state/gate-registry-status.json`** (nightly `gate_expiry_check.py`, replayed
  through the real production `exit_manager.plan_exit_actions` core, `replay_soundness: "sound"`):
  `structure_veto_enabled` is currently **`overall: "YELLOW"`**, window 2026-07-29..2026-09-01,
  refused (vetoed) cohort **n=5, win rate 40%, expectancy +$69.7/trade, total +$348.50, POSITIVE**
  — i.e. the trades this gate is blocking are, on average, winners. Verdict text verbatim:
  *"refused cohort positive ($69.7/tr) but n=5 < floor 10 -- watch, not yet actionable."*
- **`analysis/recommendations/structure-veto-lift-prereg-2026-08-04.json`**: an EARLIER run of the
  same instrument (window 2026-06-26..2026-07-31) rated the gate **RED**, n=11 (over the n≥10
  action floor), refused cohort **+$38.97/trade POSITIVE**. That RED verdict triggered a
  pre-registered lift trial (`structure-veto-lift-trial`) with a frozen kill criterion
  ("n≥10 fills on refused entries OR 10 sessions net<0 → re-arm") and a one-key revert
  (`structure_veto_enabled → false`). Its own doc says it was queued for *"the next after-hours
  arming decision"* — **`automation/state/params.json` still reads `structure_veto_enabled: true`
  today (2026-09-03)**, so that decision never happened; the fix has been sitting written and
  ready since 2026-08-04.
- **Contrast with the original ratifying study** (`analysis/recommendations/structure-veto-ab-2026-06-26.json`,
  the evidence that shipped the gate): full-sample `n_vetoes=107` raw ticks, but only **2 actual
  trades** were ever affected — both **losers removed, 0 winners removed**, entire effect
  concentrated in 2025Q1 in-sample (**$0 delta OOS in 2026**). That is thin, stale (>21-day
  revalidation interval as of 08-04, per the prereg doc), and has since been **contradicted twice**
  by live post-ship monitoring (RED 08-04, still-positive-but-YELLOW 09-01) plus today's fresh
  5-episode cluster, all wrong-way.

---

## 4. Classification: DEFECT

Not a judgment call operating within known, accepted limits. Four independent lines converge:

1. **Code-level fact**: the live veto calls the module's own self-documented *non-authoritative*
   fallback (`classify_trend`), never the *authoritative* state machine (`walk_structure`) the
   same module ships and documents for exactly this purpose (zero references in engine_cli.py or
   heartbeat_core.py — confirmed by grep, not inference).
2. **Code-level fact**: `find_swing_points(window=2)` makes the newest 10 minutes of whatever bars
   are fed structurally un-confirmable as pivots — a hard-coded blind spot, not a tunable
   sensitivity choice made on purpose for this use.
3. **Reconstructed evidence**: even a coarser proxy of today's tape shows the newest confirmable
   high frozen 56+ minutes stale during a live, ongoing rally — mechanically explaining a
   "downtrend" (or in my proxy, "range") read 6+ points above the session low.
4. **Independent, already-shipped instrumentation** (`gate_expiry_check.py`, sound replay,
   built and run by prior sessions, not by this report) has **twice** found the refused cohort
   net-positive-EV (RED then YELLOW-but-still-positive), directly contradicting the gate's own
   thin ratifying study, and a fix for exactly this failure mode was pre-registered over a month
   ago and never armed.

## 5. Proposed fix (NOT applied — trading-path files are frozen per this task's hard constraints)

In priority order, exact location for each:

1. **Ship the already-pre-registered trial** — `automation/state/params.json` line ~314,
   `"structure_veto_enabled": true` → `false`. This is the exact single-key revert the 2026-08-04
   prereg (`analysis/recommendations/structure-veto-lift-prereg-2026-08-04.json`) already
   designed, with its own kill criterion and shadow-logging requirement, sitting unarmed. Lowest
   risk (byte-identical revert path, already reviewed), highest priority — it has been ready to
   ship for a month.
2. **If a structure check is kept**, `backtest/lib/engine/engine_cli.py:203-224`
   (`_classify_sameday_5m`) should call `walk_structure` (the module's documented authoritative
   BOS/CHoCH machine, `crypto/lib/market_structure.py:125+`) instead of
   `classify_trend`+`label_swings` — using the production-intended function instead of its own
   labeled fallback.
3. **Independent of (2)**, the `window=2` argument to `find_swing_points` at
   `backtest/lib/engine/engine_cli.py:220` guarantees a ≥10-minute blind spot on the newest price
   action for whichever trend function is used; any fix should either document that lag as an
   accepted limit (currently undocumented anywhere in engine_cli.py) or reduce it.

None of these three were applied — `backtest/lib/engine/engine_cli.py` and
`automation/state/params.json` are both on this task's frozen/read-only list.

---

## Caveats and what's UNVERIFIED

- The 5m-bar reconstruction is an **APPROXIMATE proxy** (per-minute polling, not continuous-tick
  OHLC) per this task's documented-proxy instruction — it does not byte-reproduce the live
  "downtrend" label, though it does reproduce the load-bearing mechanism (newest highs
  unconfirmable). Stated as APPROXIMATE throughout, not FACT.
- Episodes 2-5's 30-min forward outcome are **UNVERIFIED / interim** — the market has not yet run
  30 full minutes past those veto ticks as of this report (last tape row 11:45:04 ET). Only
  episode 1 has a completed readout.
- No SKIP_STRUCTURE_VETO history exists in the live ledger before 2026-08-26 (retention-capped) —
  2026-08-06 and 2026-08-13 (two of the four named winning days) cannot be checked directly; this
  gap is disclosed, not filled with an assumption. 2026-08-27 and 2026-08-28 (the other two) are
  in-window and show zero fires.
- n=1 completed episode is not a population — no defensible bootstrap CI is reported for it
  (a degenerate n=1 "CI" would be misleading); the independent `gate_expiry_check.py` instrument's
  n=5 and (historically) n=11 samples are the load-bearing population-level evidence here, and
  those numbers are FACT (read from already-computed files), not derived by this report.

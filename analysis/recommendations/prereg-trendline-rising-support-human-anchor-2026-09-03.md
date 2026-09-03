# PRE-REGISTRATION (FROZEN) — rising-support HUMAN-ANCHOR shadow, 2026-09-03

**Status: FROZEN before any forward data accrues past this build.** Commit timestamp of
this file is the freeze proof. `setup/scripts/trendline_human_anchor_shadow.py` (ledger/
summary builder) and `setup/install-trendline-human-anchor-shadow.ps1` (scheduled task, NOT
run this session) are committed alongside this file. This instrument DOES backfill once
over every cached session at build time (unlike the forward-only `tp1-r50` sibling) —
every session dated `<= 2026-09-03` is an **in-sample prior**, reported honestly and never
used to gate a decision. The decision rule (§7) is evaluated on **forward sessions only**
(`> 2026-09-03`), and even a met bar produces no verdict before **2026-10-30** (§7, hard
date gate) or any live/paper wiring, **ever** (§9).

Supersedes: [`prereg-trendline-rising-support-v2-human-anchor-PROPOSAL-2026-09-03.md`](prereg-trendline-rising-support-v2-human-anchor-PROPOSAL-2026-09-03.md)
— that file was an unarmed proposal (no instrument built, no frozen anchor rule, no dated
accrual clock). This file is the frozen, built, scheduled version of the same idea; the
proposal file is left in place with a superseded banner rather than deleted (append-only
history).

Motivating evidence (read-only, all three already committed):
- [`trendline-today-exhibit.md`](../deep-research/2026-09-03-money/trendline-today-exhibit.md) (T2) —
  J's literal anchors (5m `08:20`→`10:10`, 15m `08:15`→`10:00`) are NOT the session's first
  two fractal pivots; the mechanical 3-touch pivot detector cannot construct this line at
  10:55 ET with no look-ahead, on either timeframe, with or without premarket bars.
- [`trendline-historical-study.md`](../deep-research/2026-09-03-money/trendline-historical-study.md) (T3) —
  the literal "first two confirmed pivot lows of the session" rule REFUTED (3 of 4
  falsifier conditions fired); its own §6 finding is the direct motivation for this file:
  *"J's mental model is closer to 'the low of the pre-move decline, and the first higher
  low after it' ... than to 'the first two confirmed pivot lows of the day'"* — an
  UNTESTED, different hypothesis requiring its own fresh prereg. This file is that prereg.
- [`trendline-sight-check.md`](../deep-research/2026-09-03-money/trendline-sight-check.md) (T4) —
  the live engine has no support-line/low-anchored trendline code path at all (5m-only,
  descending-HIGHS only, RTH-only bars) — confirms this is genuinely unbuilt, on any anchor
  rule, not merely "the existing detector is tuned differently."

---

## 1. The hypothesis (still UNTESTED beyond T3's n=1 qualitative read)

A rising-support line anchored the way J actually reads it — **the lowest low of the
session so far, paired with the next confirmed higher swing low** — rather than "the first
two fractal pivots of the day" (T3's literal, refuted rule), may carry information the
pivot-gated 3-touch detector discards. The prior from T3 is a REFUTATION of the adjacent,
simpler rule; this is a **different, freshly-frozen rule**, tested on its own forward
population, not a re-run of T3 with the threshold loosened.

**Null hypothesis (default, stated up front):** this anchor rule performs no better than
the time-of-day baseline — the same null T3 already confirmed for the simpler rule.

## 2. Bars (frozen)

Built from `backtest/data/spy_sip_cache/spy_1m_<date>.json` (never re-fetched; cached only,
per this session's hard constraint). Aggregation convention **identical to T2/T3**,
verified there against the existing `spy_5m_*.json` cache (146/148 exact bar match):

- A bar labeled `T` covers `[T, T+width)` — open-of-interval. 5m bar `08:20` = 1m bars
  `08:20`–`08:24`. 15m bar `08:15` = 1m bars `08:15`–`08:29`.
- `open`=first 1m open, `high`=max(1m highs), `low`=min(1m lows), `close`=last 1m close,
  `volume`=sum.
- **15m buckets built from 1m only** (not resampled from 5m) and **require a full 15/15
  1m-bar bucket** — no partial trailing bucket is scored.
- **Four bar-sets, all built:**

  | bar_set | timeframe | scope |
  |---|---|---|
  | `5m_premkt` | 5m | full day from 04:00 ET (matches J's own chart) |
  | `5m_rth` | 5m | `>=09:30 ET` only — **disclosure variant**, not primary |
  | `15m_premkt` | 15m | full day from 04:00 ET (matches J's own chart) |
  | `15m_rth` | 15m | `>=09:30 ET` only — **disclosure variant**, not primary |

  **Primary config for the headline decision readout: `5m_premkt`.** The RTH-only rows are
  built and reported every run (T3 found RTH-only sometimes stronger, sometimes weaker —
  no reason to hide it), but they do not gate the ship/kill verdict in §7; that verdict is
  read from `5m_premkt` and `15m_premkt` only, because those are the bar sets J is actually
  looking at when he draws these lines.

## 3. Anchor rule (frozen — the load-bearing definition)

For each bar_set, for each of two **anchor modes** (never mixed within one line, per
doctrine "ALL-wick or ALL-body, never mixed"):

- **wick** — pivot/anchor value = bar low (`l`). **Primary mode.**
- **body** — pivot/anchor value = `min(open, close)`. **Secondary/disclosure mode.**

Let `get_low(i)` be the bar-`i` low under the active mode.

- **Swing-low pivot test, window `k=2`, both timeframes:** bar `j` is a confirmed swing low
  iff `get_low(j) <` every `get_low` in `[j-k, j)` (strict) AND `get_low(j) <=` every
  `get_low` in `(j, j+k]` (inclusive-right — a flat-bottomed plateau registers one pivot at
  its first bar; same `inclusive_right=True` convention `crypto/lib/trendlines.py`'s
  `market_structure` caller already uses, imported read-only, never edited). A pivot at bar
  `j` is only **knowable** once bar `j+k` has closed (no look-ahead) — this repo processes
  whole closed sessions in one batch nightly, so a pivot's full window always exists in the
  cache by the time this script runs, but every touch/break check below is still gated to
  start no earlier than bar `j+k`, reproducing what a live, incremental reader would have
  known at that exact moment.

- **A = the running minimum of `get_low` over every bar of the session seen so far**
  (bar-1 = whichever bar the bar_set's scope starts at), tracked continuously, bar by bar —
  **not** a pivot itself, matching T2's finding that J's own `08:15`/`08:20` anchor is
  never a confirmed fractal pivot on 15m, and is one bar off the true session minimum on
  5m. Whenever a new bar's low undercuts the current `A`, `A` resets to that new bar
  (killing any currently-active line — see re-anchor rule below).

- **B = the first swing-low pivot, confirmed (per the window-`k` rule above) after `A` was
  set, whose price is above `A`'s price, and whose bar index is at least `MIN_GAP` bars
  after `A`'s** — `MIN_GAP = 6` on 5m (30 min), `MIN_GAP = 2` on 15m (30 min) — matched
  wall-clock gap across timeframes, not matched bar-count.

- **The line through A and B is a candidate the instant B confirms — no third touch
  required.** This is the explicit, named difference from `backtest/lib/trendline_
  detector.py`'s `min_touches=3` default (imported read-only nowhere in this instrument;
  it is a from-scratch reimplementation over the frozen rule above, kept shadow-only and
  never wired to that module or to `filters.py`'s live trigger functions).

- **Re-anchor (line death + new-search restart), two independent triggers:**
  1. **A new lower low prints** (`get_low` of the current bar < current `A`'s price) — `A`
     resets to that bar, any currently-active line is marked dead (`end_reason:
     "reanchor_lower_low"`), and the search for a new `B` restarts from the new `A`.
  2. **The line breaks** (§4) — the line is marked dead (`end_reason: "break"`), `A` is
     **not** reset (no new lower low necessarily occurred), and the search for a new `B`
     restarts using the same `A`, honoring `MIN_GAP` from that same `A` and never reusing
     an already-consumed pivot as `B` again.

  Only one line is ever active at a time per (bar_set, anchor_mode, session); a session may
  produce zero, one, or several sequential lines as A/B get replaced across the day.

## 4. Events (frozen)

Evaluated on every bar from the confirming bar of `B` (`B`'s index `+k`) onward, using the
line value `line(j) = A_price + slope*(j - A_idx)`, `slope = (B_price - A_price)/(B_idx -
A_idx)`:

- **TOUCH** — a bar whose `|get_low(j) - line(j)| <= tol` **and** whose `close(j) >
  line(j)`. This is a strict two-sided proximity test on the low (not merely "the low
  stayed above line − tol", which the T2 exhibit showed would count a $1.10+ wick-through
  as a "touch" — it should not). `tol = $0.20` on 5m, `$0.30` on 15m.
- **BREAK** — the first bar whose `close(j) < line(j) - tol` (same `tol`). The line dies at
  the break bar (§3's re-anchor rule 2); no further touches/breaks are evaluated against a
  dead line.
- A session/config can produce multiple TOUCH events on one line (no ceiling), and at most
  one BREAK event per line (first close-break kills it).

## 5. Outcome measurement + baseline (frozen)

For every TOUCH (implied direction: **up**) and BREAK (implied direction: **down**), at
horizons **H ∈ {15, 30, 60} minutes** (bar counts: 5m → 3/6/12 bars, 15m → 1/2/4 bars),
skipped when the forward window does not fully fit in that session's cached bars (never
padded, never estimated):

- **close-to-close move**: `c2c = close[j+N] - close[j]` (touch) or `close[j] - close[j+N]`
  (break). `favorable = c2c > 0`.
- **max favourable excursion**: `mfe = max(high[j+1..j+N]) - close[j]` (touch) or
  `close[j] - min(low[j+1..j+N])` (break).
- **Time-of-day baseline** (same convention T3 used): for every distinct `HH:MM` at which a
  TOUCH (resp. BREAK) occurred anywhere in the whole bar_set's session population, pool
  **every** bar at that same `HH:MM` across **all** sessions of that bar_set that is **not
  itself an event bar** and has a full forward window, and compute the same `favorable`
  rate and mean `c2c` over that pool. This directly answers "is closing up in the next N
  minutes after this specific clock time unusual, or is it just what that time of day
  usually does?" — not a synthetic random-bar baseline.

## 6. Backfill + in-sample flag (frozen)

This instrument backfills **once**, at first run, over **every session in
`backtest/data/spy_sip_cache`** with both a `spy_1m_*.json` and `spy_5m_*.json` file present
(no date floor — "every cached session" per the task, not a fixed 45-session window like
T3). Every row (`line`, `event`, `session_marker`) carries `in_sample: true` when
`date_et <= "2026-09-03"` and `in_sample: false` for any later session. Re-runs are
idempotent per `(date_et, bar_set, anchor_mode)` — a `session_marker` row already present
for that triple means that session/config was already processed and is never
re-processed or duplicated, whether historical or forward.

**The in-sample prior is reported every run, honestly, and is never permitted to satisfy
§7's bar** — only `in_sample: false` (forward, `> 2026-09-03`) rows count toward
`n_sessions_forward` / `n_touches_forward` / `n_breaks_forward` and the CIs in §7.

## 7. Decision rule (frozen — NOT softened after data starts arriving)

Evaluated **separately** for TOUCH (bull `trendline_bounce` candidate) and BREAK (bear
`trendline_break` candidate), **on the `5m_premkt` and `15m_premkt` wick-mode configs
only** (§2), **at H=60 min**, **using forward (`in_sample: false`) rows only**:

A trigger proposal proceeds to a real ratification pass only if **ALL** of:

1. **`n_sessions_forward >= 25`** AND **`n_events_forward >= 40`** (events = touches for
   the bull check, breaks for the bear check) — the same adequate-power floor T3 used and
   failed on the simpler rule.
2. **`rate_ci_lower (session-clustered bootstrap, day-resampled) > baseline_rate`** — the
   60-min favourable-rate CI's 2.5th percentile must clear the time-of-day baseline's point
   rate, not merely tie it.
3. **`mean_move_ci_lower > 0`** — the session-clustered bootstrap CI's 2.5th percentile of
   mean `c2c` must be strictly positive — a real $-edge, not just a directional coin-flip.

**Hard date gate, independent of the above:** even if all three conditions are met, this
instrument reports **no ship/kill verdict before `2026-10-30`** — `status` stays
`ACCRUING` (bar not yet met) or `BAR_MET_DATE_GATED` (bar met, verdict withheld) until that
date. This mirrors the existing convention (`tp1-r50-forward-shadow`'s "reaching the bar is
permission to READ the verdict, not to ship") with an additional explicit calendar floor,
because this rule was frozen the same day as its own motivating exhibit and needs real
forward distance before any single session can dominate a small forward sample.

Any single failed condition (post-date-gate) = **the forward evidence does not support a
build**, full stop.

## 8. Falsifier (frozen, stated up front — matches T3's own falsifier discipline)

The rule is **falsified** (do not build) if, once the bar in §7.1 is met:

- `rate_ci_lower <= baseline_rate` for the primary config's TOUCH or BREAK at H=60, OR
- `mean_move_ci_lower <= 0` for either, OR
- **top-3-session concentration `>= 0.60`** of total events (a verdict carried by a
  handful of sessions is not a verdict — same guard `stop_mode_shadow_ledger.py` and
  `day_throttle_shadow.py` both use).

Any one of these firing on the forward population is a REFUTATION of this specific anchor
rule, reported as such — not quietly re-parameterized into a third prereg without a fresh
freeze.

## 9. Explicit non-goals

- **Never live, never paper, ever — for this instrument specifically.** Not "until
  ratified" — this shadow's own decision rule (§7) caps out at "proceeds to a real
  ratification pass," and even that pass is a SEPARATE, later, explicitly-authorized step
  this file does not pre-authorize. No code path in `trendline_human_anchor_shadow.py`
  ever calls a broker, a live trigger function, or `filters.py`.
- Not a change to `backtest/lib/trendline_detector.py`'s `min_touches=3` default or any
  other existing consumer's behavior — this is a from-scratch, standalone, shadow-only
  reimplementation of a DIFFERENT rule, imported by nothing on the live or shadow-trigger
  path.
- Not evidence yet. The in-sample backfill is a **prior**, reported honestly, never a
  gate-passing substitute for forward data (§6).
- Not a claim that J's anchors are "wrong" in any session where this rule still misses
  them — a human eye can integrate context (multi-day levels, volume, news) this 2-point
  mechanical rule never sees. This tests whether the SPECIFIC mechanical operationalization
  in §3 carries information, not whether J's judgment is reducible to it.

## 10. Build step (structured, for machine reference)

```json
{
  "build_step": {
    "id": "TRENDLINE-RISING-SUPPORT-HUMAN-ANCHOR-SHADOW",
    "supersedes_proposal": "prereg-trendline-rising-support-v2-human-anchor-PROPOSAL-2026-09-03.md",
    "motivating_exhibits": ["trendline-today-exhibit.md", "trendline-historical-study.md", "trendline-sight-check.md"],
    "frozen_date": "2026-09-03",
    "backfill": "once, all cached sessions, in_sample flag by date <= 2026-09-03",
    "anchor_rule": {
      "pivot_window_k": 2,
      "min_gap_bars": {"5m": 6, "15m": 2},
      "a": "running minimum low of session so far, resets on new lower low",
      "b": "first confirmed swing-low pivot after A, price above A, >=min_gap bars after A",
      "min_touches_required": 0,
      "modes": ["wick", "body"],
      "primary_mode": "wick"
    },
    "tolerance": {"5m": 0.20, "15m": 0.30},
    "horizons_min": [15, 30, 60],
    "bar_sets": ["5m_premkt", "5m_rth", "15m_premkt", "15m_rth"],
    "primary_bar_sets": ["5m_premkt", "15m_premkt"],
    "bar": {"min_sessions_forward": 25, "min_events_forward": 40},
    "decision_rule": {
      "rate_ci_lower_gt_baseline": true,
      "mean_move_ci_lower_gt_zero": true,
      "all_required": true,
      "softenable": false,
      "hard_date_gate": "2026-10-30",
      "never_live": true
    },
    "falsifier": {
      "rate_ci_lower_le_baseline": true,
      "mean_move_ci_lower_le_zero": true,
      "top3_concentration_ge": 0.60
    },
    "artifacts": {
      "ledger": "analysis/recommendations/trendline-human-anchor-ledger.jsonl",
      "summary": "analysis/recommendations/trendline-human-anchor-summary.json",
      "builder": "setup/scripts/trendline_human_anchor_shadow.py",
      "scheduled_task": "Gamma_TrendlineHumanAnchorShadow",
      "install_script": "setup/install-trendline-human-anchor-shadow.ps1"
    },
    "do_not": [
      "lower min_touches on backtest/lib/trendline_detector.py's live/shadow consumers",
      "wire this instrument's output into any live or paper trigger, ever",
      "read a verdict before 2026-10-30 even if the bar is met earlier",
      "let in-sample (<=2026-09-03) rows satisfy the forward bar in section 7"
    ]
  }
}
```

## 11. Revert

Whole instrument, one shot: `Unregister-ScheduledTask -TaskName
Gamma_TrendlineHumanAnchorShadow -Confirm:$false` + delete
`setup/scripts/trendline_human_anchor_shadow.py` +
`setup/install-trendline-human-anchor-shadow.ps1` + this file (+ the two output
artifacts under `analysis/recommendations/`, which are analysis-only leaves nothing on the
trading path reads). Same class as `Gamma_LadderRungShadow` / `Gamma_Tp1R50ForwardShadow`.

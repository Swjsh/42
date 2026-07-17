# HTF Levels Audit — why 06-30/07-02/07-08 weren't visible this morning

_generated 2026-07-17 ~18:28 ET (Friday, after-hours work block), Sonnet_

**J's question:** "figure out why we didn't look back to Tuesday June 30th, Thursday July 2nd,
Wednesday July 8th. if we had high-timeframe key level knowledge, we could have gotten in calls
confidently this morning — that was an extremely strong bounce off this level."

**Verdict up front:**
- J's read is **CORRECT** — 740-744.5 is a real, repeatedly-tested multi-week zone. Quantified below.
- The zone was **captured then aged out** (06-30, 07-02) or **captured but fragmented below the
  merge bar** (07-08) — two distinct, additive root causes in `level_memory_producer.py` /
  `refresh_levels_intraday.py`. Not "never captured."
- **Counterfactual verdict: the missing HTF level was NOT the binding constraint this morning.**
  Even with a perfect 741-742 support level live in `levels_active` at 09:30, the trade does not
  fire — ribbon never flip-stacked BULL all session (hard veto, Filter 5) and, even if it had,
  `block_elite_bull` would have vetoed it at today's VIX (~19, inside its [0,25) band) exactly as
  it did on 07-15/16. Say it plainly per the brief: fixing the level lookback alone would not have
  produced this morning's trade. It is still worth fixing for visibility/conviction/context — see
  Part 4.

---

## Part 1 — verify J's read (real bars, `backtest/data/spy_5m_2026-05-19_2026-07-17.csv`)

RTH open/high/low/close for the named sessions plus today:

| date | RTH open | RTH high | RTH low | RTH close | notes |
|---|---|---|---|---|---|
| 2026-06-30 | 741.29 | 748.02 | **740.89** | 747.75 | opened AT the zone, ripped +$6.86 off the low |
| 2026-07-02 | 747.40 | 751.31 | **740.03** | 745.30 | rolled over from 751 high, bottomed 13:00-13:05 (740.52/740.37), ripped back to 745.30 |
| 2026-07-08 | 743.16 | 746.14 | **739.51** | 745.96 | dipped 10:45-11:20 (741.29→740.05), based 740-742 midday, ripped to close 745.96 |
| 2026-07-17 (today) | 742.05 | 747.29 | **740.80** | 743.23 | 09:30 low 741.03, 09:35 low 740.80, then +$4.00 in 25 min to 744.81 by 09:55 |

All four RTH lows print inside a **$1.86 band** (739.51–741.61). This is not four unrelated dips —
it's the same shelf tested four times in roughly three weeks.

**Broader confluence scan** (every RTH session since 2026-05-19, n=41): sessions whose **RTH low**
itself printed inside 739.0–744.5 (not just passed through in transit):

```
2026-05-22  low 744.48  bounce +1.04
2026-06-17  low 739.23  bounce +1.78
2026-06-18  low 743.86  bounce +4.06
2026-06-22  low 743.13  bounce +1.19
2026-06-30  low 740.89  bounce +6.86
2026-07-01  low 742.38  bounce +3.30
2026-07-02  low 740.03  bounce +5.27
2026-07-08  low 739.51  bounce +6.45
2026-07-17  low 740.80  bounce +2.43 (through 09:55; kept extending after)
```

9/41 sessions (22%) — and 5 of the last ~13 trading days (06-30 through today) — had their RTH low
land in this exact band. Median close-vs-low bounce on these days: **$3.30**; mean **$3.60**.
Today's +$4.00 move in 25 minutes is squarely in-family, not an outlier — this is the zone doing
what it has repeatedly done. **J's read is verified, with numbers.**

---

## Part 2 — why the level system didn't have it

Two additive, independent gaps, both in the still-shadow (never-fed-to-entries) memory system:

### Root cause 1 — 10-trading-day lookback window (`setup/scripts/level_memory_producer.py:51`)

```python
LOOKBACK_DAYS = 10      # multi-day memory horizon
```

`LevelMemory._lookback_start_idx` (`backtest/lib/watchers/level_memory.py:266`) keeps only the
**last 10 unique trading dates** up to the eval bar — a hard calendar-trading-day window, not a
bar count. As of today (07-17), that window is **07-06 through 07-17 inclusive**. Counting back:

```
07-17(1) 07-16(2) 07-15(3) 07-14(4) 07-13(5) 07-10(6) 07-09(7) 07-08(8) 07-07(9) 07-06(10)
```

- **06-30 is 13 trading days back** — entirely outside the window.
- **07-02 is 11 trading days back** — entirely outside the window.
- **07-08 is 8 trading days back** — inside, but only by 2 days of margin.

Both dates J named as primary evidence were captured live on their own day (each session's own
PML/session-low gets written that day) and then **aged out of the 10-day horizon** before today.
This is "expired," not "never captured."

### Root cause 2 — narrow clustering tolerance fragments a wide HTF zone, even in-window

`CLUSTER_TOL = 0.35` (`level_memory.py:61`) and the producer's `DEDUP_EPS = 0.60` merge pivots
into one level only within $0.35–0.60. J's zone is **$3.5 wide** (741.0–744.5) — a genuine
multi-day *zone* per the levels-are-zones doctrine, not a single price. The algorithm splits it
into several narrow sub-clusters, each of which only gets partial credit (touches/wicks/consol
bars), so none crosses the merge bar.

**Empirical proof** — `automation/state/key-levels-memory.json`, generated 16:00 ET **today**
(07-08 is in-window, and today's whole V-bounce is already baked into the score): the entire
12-level shadow map has **exactly one support-side entry near this zone**:

```json
{"price": 743.19, "role": "support", "memory_score": 48.0, "touches": 24,
 "role_flips": 6, "tier": "Reference"}
```

`STRONG_MEMORY = 60.0` is the bar for `tier: "Active"`; 48 misses it. `refresh_levels_intraday.py`'s
G11 merge additionally requires `MEMORY_MERGE_MIN_SCORE = 60.0` **and** `tier == "Active"` before a
memory level is unioned into the live `key-levels.json` the engine reads. 48 < 60 on both counts —
this level **never merged**, even after four confirmed touches and today's own bounce. The other 11
slots in the 12-cap shadow file are all resistance from 744–754 (last week's price action ran up
through there), crowding out weaker support candidates before they can even be compared.

### Side-note (not a live bug, but clutter worth a cleanup pass)

Today's raw `key-levels.json` still carries `PML_2026-06-30 @ 741.61` (`expires_at:
"2026-06-30T16:00:00-04:00"`) as a cosmetic leftover. `heartbeat_core._level_expired` (FIX2,
2026-07-07 — this exact class of stale-level leak was already root-caused and patched once) does
correctly exclude it from `active`/`multi` — it is **not** being read live, just visually stale in
the file. Low priority; noted so it doesn't get mistaken for evidence of a live-read bug.

---

## Part 3 — the counterfactual, walked bar-by-bar (honest answer)

Pulled `automation/state/core-decisions.jsonl` for the `safe` account, 09:30–10:15 ET today
(`spy` field has a display-lag artifact 09:30-09:35 — jumps 749.96→741.06 in one tick; the
underlying VIX/ribbon/verdict fields are unaffected and used below):

```
09:30-09:50  ribbon=BEAR  spy ~741.0-743.0   verdict=HOLD  triggers=[]  bull_score climbing 6-8
09:51-10:15  ribbon=BEAR  spy 743.0->746.4   verdict=HOLD  triggers=[]  bull_score 7-9, reason:
             "no setup passed scoring (neither bear nor bull)"
```

**Ribbon stayed BEAR-stacked continuously from 09:30 through at least 12:16 ET** (first transition
of the whole day was BEAR→MIXED at 12:16; it never went BULL at all today). `evaluate_bullish_setup`
Filter 5 (`backtest/lib/filters.py:1056`) is a **hard veto**: `ribbon_now.stack != "BULL"` blocks
the setup outright, independent of any trigger. This is empirically confirmed — zero `side=='C'`
rows, zero bull triggers, for the entire session, even as `bull_score` climbed to 8-9 during the
exact bounce window. **A hypothetical 741-742 HTF support level would not have changed this** —
`detect_level_reclaim` never even gets evaluated against a passing setup if Filter 5 already failed.

Second-order check — would the 2-trigger minimum (`filter_10_min_triggers_bull=2`) have been a
problem even if ribbon had flipped? Probably not: `detect_confluence` (`filters.py:741`) just
checks whether the reclaimed level is within `CONFLUENCE_TOLERANCE_DOLLARS=$0.30` of ANY entry in
`multi_day_levels` — and `_read_levels` tags essentially every active support/resistance level as
"multi_day" (`heartbeat_core.py:319`). So a `level_reclaim` off a new HTF level would very likely
also self-trigger `confluence`, satisfying `min_triggers=2` off one physical event. This is exactly
what 07-15 and 07-16 show: `triggers=['level_reclaim', 'confluence']` together, off the same level,
on nearly every qualifying tick.

**Third gate — `block_elite_bull` — is where 07-15/16 actually died, and where today would have
died too:**

```
params.json: block_elite_bull=True, block_elite_bull_vix_low=0.0, block_elite_bull_vix_high=25.0
```

- **07-15, 09:56-10:53 ET:** ribbon=BULL, VIX 16.0-16.2, triggers=['level_reclaim','confluence']
  — 25 ticks, every one `SKIP_ELITE_BULL_LEVEL_RECLAIM`.
- **07-16, 09:34-09:35 ET:** same pattern, VIX 16.1-16.2, 2 ticks, same SKIP.
- **Today, 09:30-10:15 ET:** VIX ran **19.0-19.5** — also inside the [0.0, 25.0) block band.

This gate is currently ACTIVE, validated, and closed as "KEEP" by a 2026-06-30 audit (removing it
cost the backtest cohort net -$241 on the fresh OPRA window — `self_check.py:372`). This pre-reg
does **not** reopen that finding.

**Plain verdict:** even in the best-case counterfactual where the HTF level existed, was merged
live, AND ribbon had somehow flip-stacked BULL in time — `block_elite_bull` still fires at VIX~19,
same as it fired twice this week. The missing HTF level was moot today. Two independent,
already-active gates (ribbon-stack, and block_elite_bull) would each have blocked the trade on
their own. **The value of fixing the level-memory lookback is conviction/visibility/context for J
and for the `multi_day_confluence`/Discord-alert path — not a guaranteed unlock of more live bull
entries, because `block_elite_bull` is a separate, already-adjudicated decision.**

---

## Part 4 — the fix, spec'd as a weekend-ratifiable pre-reg

Filed to `automation/overnight/queue.md` as `HTF-LEVEL-LOOKBACK-EXTENSION` (see that file for the
actionable queue entry). Summary:

1. **Additive HTF tier**, not a replacement — new constants in `level_memory_producer.py`,
   existing 10-day/$0.35 intraday tier untouched (byte-identical current behavior preserved):
   - `HTF_LOOKBACK_DAYS = 25` (~5 trading weeks — covers 06-30 and 07-02 with margin)
   - `HTF_CLUSTER_TOL = 1.00` (vs $0.35 intraday — wide enough to merge the 740-741 shelf into one
     level without also swallowing the separate 743-744.5 shelf ~$2-3 away)
   - Own `HTF_MIN_MEMORY`/`HTF_STRONG_MEMORY` floors — needs backtesting, not a guessed copy of
     20/60 (weekly touches are sparser per unit time than intraday ones; using the same bar would
     likely still starve it).
   - Separate shadow file `key-levels-htf.json`, write-only first — mirrors the existing G11
     shadow-before-merge rollout exactly.
2. **Separate live-merge flag** `level_memory_htf_live_merge` (default false) in
   `refresh_levels_intraday.py`, its own `HTF_MERGE_CAP` (propose 4, vs the existing intraday cap
   of 6) — independently A/B-able without touching the already-tuned intraday merge.
3. **Dashboard/Discord rendering as a ZONE**, not a hairline — labeled `HTF_SUP_NN`/`HTF_RES_NN`
   so J can visually tell multi-week structure from today's intraday swing. Cross-ref: today's
   `strategy/candidates/_lesson-inbox/2026-07-17-levels-are-zones-proximity-band.md` (filed ~10:15
   ET, same "zones not lines" theme on the *rejection*-tolerance side — this pre-reg is the
   *lookback/clustering* side of the same doctrine gap).
4. **Validation** via the standing eval-first gate (OP-16): backfill 60-90 trading days, replay
   through the existing trigger-replay harness, file the A/B scorecard at
   `analysis/recommendations/htf-level-lookback-extension.json`. Ratify only if OOS_positive AND
   WF≥0.70 AND sub_window_stable AND anchor_no_regression — same bar as any other engine change,
   no J gate needed to ship (J is REVOKE-only per OP-16).
5. **Flag, don't touch:** a larger HTF-eligible `level_reclaim` candidate pool changes the input
   distribution feeding the already-CLOSED `block_elite_bull` audit (2026-06-30, -$241). Re-running
   that audit's cohort math after the HTF tier ships is an *informational* follow-up, not a
   reopening — do not let this pre-reg become a backdoor to relitigate block_elite_bull.

### Cost

- **Compute: $0.** Pure Python, already scheduled, no LLM. Lookback 10→25 trading days at 5m bars
  is ~780→~1950 bars through the existing O(n) pivot/cluster/score pass — negligible (<100ms).
- **Level-count growth:** current live `key-levels.json` typically carries 12-14 active entries
  (`ACTIVE_BAND=$12`); +HTF_MERGE_CAP (4) pushes worst case to ~16-18. Still well inside engine/
  dashboard budget.
- **Confluence-tolerance interaction (the real risk, not compute):** an intraday $0.35-cluster
  level and an HTF $1.00-cluster level from the SAME physical shelf can both land in
  `key-levels.json` a dollar or two apart. Per Part 3, `detect_confluence`'s $0.30 tolerance is
  already near-tautological once any level_reclaim fires — TWO nearby levels from the same shelf
  make it easier still, risking `min_triggers=2` becoming closer to `min_triggers=1` in practice
  for HTF-adjacent reclaims. **Build requirement, not an afterthought:** extend
  `_normalize_levels`'s existing prefix-stripped dedup (or widen `ROLE_EPSILON` specifically for
  HTF/intraday same-shelf pairs) so the two tiers collapse to one canonical entry per physical
  shelf before this ships live. Must be a named test in the A/B scorecard, not assumed safe.

---

## Sources

- `backtest/data/spy_5m_2026-05-19_2026-07-17.csv` (RTH bar data, all 4 named dates + confluence scan)
- `setup/scripts/level_memory_producer.py`, `backtest/lib/watchers/level_memory.py` (lookback/cluster constants)
- `setup/scripts/refresh_levels_intraday.py` (G11 merge gate, `ACTIVE_BAND`, `MEMORY_MERGE_MIN_SCORE`)
- `setup/scripts/heartbeat_core.py` (`_level_expired`, `_read_levels`, gate constants)
- `backtest/lib/filters.py` (`evaluate_bullish_setup`, `detect_level_reclaim`, `detect_confluence`)
- `backtest/lib/engine/gates.py` (`block_elite_bull` implementation)
- `setup/scripts/self_check.py:372-379` (block_elite_bull KEEP audit, 2026-06-30, thread CLOSED)
- `automation/state/core-decisions.jsonl` (live ticks: today 09:30-10:15, 07-15, 07-16)
- `automation/state/key-levels.json`, `automation/state/key-levels-memory.json` (live snapshots)
- `automation/state/params.json` (`block_elite_bull*`, `level_memory_live_merge`)

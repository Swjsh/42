# ARM-EXIT-DEGENERACY — measurement report (2026-09-11)

**Scope: measurement only.** No production file touched (`params*.json`, `heartbeat*`,
`filters.py`, `exit_manager.py`, `build_shared_signal.py`, `go_live_gate.py` all read-only).
Queue item: `automation/overnight/queue.md` `ARM-EXIT-DEGENERACY-2026-09-11`.

## Verdict

**PARTIALLY CONFIRMED, but the feared gate-integrity consequence does NOT hold in the code
as it exists today.**

- **Q1 (code path) — CONFIRMED.** `trigger_level` is produced once per (date, entry event)
  by the shared signal producer and copied verbatim into every arm's entry plan. It is not
  re-derived per arm.
- **Structure-stop exits DO correlate across arms** — empirically confirmed (Q3) and
  currently true for all 4 active arms (Q1 addendum), because none of them currently
  overrides `stop_mode` away from `structure`.
- **Q4 (gate integrity) — the specific mechanism in the queue item is NOT how
  `go_live_gate.py` computes its pass/fail statistic.** The criterion that actually gates
  `overall_verdict` (`statistical.pass`) bootstraps **each arm on its own trading days only**
  — it never pools (arm, date) pairs across different arms into one array of pretend-i.i.d.
  samples. There is a second, disclosure-only "book_wide_correlated_rollup" key that DOES
  pool across arms, but it pools by **calendar date** (one value per day, summing all arms'
  P&L that day) — already exactly the de-duplication the queue item asked for — and its own
  `pass` field is discarded; it never reaches `overall_verdict`. Ran live, read-only,
  side-effect-free (see Q4 below): the gate is currently RED by a wide margin anyway
  (CI-lower ≈ 0.29–0.40 on every arm), so this question is currently moot for any arming
  decision, but the code-level finding stands independent of that.
- There remains a real, narrower epistemic point (not a coded bug): requiring all 4 arms to
  pass **independently** is weaker evidence of "4 independent confirmations" than the gate's
  design implies, because on structure-stop days the arms' win/loss outcome for that day is
  driven by the same bar-close event. This doesn't inflate any single CI, but it does mean
  "4-for-4" isn't 4 uncorrelated replications. Recommend a one-line disclosure addition to
  `go_live_gate.py`'s output (not applied — freeze, and out of this task's scope) rather than
  a kill.

---

## Q1 — code path (confirmed by reading code, not inferred)

- `automation/state/fleet/build_shared_signal.py` computes `trigger_level` /
  `trigger_level_exact` **once per tick, per side**, sourced from
  `filters.detect_level_rejection` / `detect_level_reclaim` (core-decisions.jsonl) or the
  `_nearest_level` proximity heuristic (build_shared_signal.py:521-522). This happens before
  any arm is considered.
- `automation/state/fleet/fleet_executor.py:_plan_from_strategies` runs once per active arm
  (`for arm in accounts.get("arms", [])`, fleet_executor.py:1520) but reads the trigger level
  straight off the **shared** `signal` dict, unmodified:
  ```
  _tl_exact = entry.get("trigger_level_exact")
  _tl = _tl_exact if _tl_exact is not None else entry.get("trigger_level")
  ...
  trigger_level=(float(_tl) if _tl is not None else None)
  ```
  (fleet_executor.py:772-773, 779). No arm-specific transform, scaling, or offset is applied
  anywhere in this path.
- `exit_manager._structure_stop_hit` (exit_manager.py:140-149) then does exactly what the
  queue item states: exits when the first CLOSED 5m bar closes beyond that same
  `trigger_level`, side-aware. Since every arm gets the identical `trigger_level` for the
  identical entry event, a structure-stop exit fires on the identical bar close for every
  arm carrying that stop mode.
- **What genuinely IS arm-specific**: `_exit_shape_dict(strat, arm)` (fleet_executor.py:624)
  shallow-merges each arm's `params_patch.exit_patch` over the strategy registry's exit
  shape — this is where `premium_stop_pct`, `tp1_premium_pct`, `trail_pct`,
  `profit_lock_mode`, and (critically) **`stop_mode` itself** can differ per arm. And
  `structure_stop_enabled` is read from each arm's OWN resolved params
  (`fleet_live.py:720`, `params.get("structure_stop_enabled", False)`), so it is possible,
  in principle, for one arm to trade premium-stop while its siblings trade structure-stop.
- **This possibility is not hypothetical — it happened once, and was reverted by attrition,
  not by design-for-decorrelation.** `automation/state/fleet/accounts.json:212` documents a
  2026-08-09 change that set `risky-3`'s `exit_patch` to `{"stop_mode": "premium"}`,
  explicitly to de-correlate it from the rest of the book (own text: "EVERY fleet arm
  currently resolves stop_mode='structure' ... so the whole live book is chart-stop-primary
  and the premium lane has NEVER traded"). **`risky-3` is now `status:"retired"`** in the
  current `accounts.json` (confirmed by direct read, 2026-09-11). The 4 currently **active**
  arms are `safe-3`, `safe-2`, `risky-1`, `bold-2` — verified their resolved `stop_mode`:

  | arm | exit_patch | resolves | structure_stop_enabled (own params.json) |
  |---|---|---|---|
  | safe-3 | `{"stop_mode":"structure","profit_lock_mode":"trailing"}` | structure | true |
  | safe-2 | none (base `automation/state/params.json`) | structure (registry default) | true |
  | risky-1 | `{"tp1_premium_pct":0.5,"stop_mode":"structure"}` | structure | true |
  | bold-2 | none (base `automation/state/aggressive/params.json`) | structure (registry default) | true |

  **All 4 currently active arms resolve `stop_mode="structure"` with
  `structure_stop_enabled=true`.** The observed 2026-09-11 live event (4 arms exiting within
  1 second, 3 separate entry events) is exactly what this code path predicts for the
  *current* fleet composition. The claim would be **false** only for a fleet that still
  included an arm like the old `risky-3` with `stop_mode:"premium"`.

## Q2 / Q3 — exit mix + simultaneity (journal/trades.csv, 600 logged round trips)

Source: `journal/trades.csv`, exit stage parsed from `notes_short` field (`stage=...`).
53/600 rows carry no stage tag (older/manual entries) and are excluded from the mix %.
`automation/state/pnl-statement.json`'s 869 `round_trips` are broker-fills-derived and carry
**no exit-stage field** — not usable for this breakout; trades.csv is the only tagged source.

**Overall exit mix (n=547 tagged):**

| stage | count | % |
|---|---|---|
| premium_stop | 246 | 45.0% |
| structure_stop | 126 | 23.0% |
| tp1 | 73 | 13.3% |
| trail | 61 | 11.2% |
| ribbon_flip | 34 | 6.2% |
| time_stop | 4 | 0.7% |
| runner_target | 3 | 0.5% |

**Per account_id** (`account_id` field as logged — `safe`/`aggressive`/`bold` are legacy
labels pre-dating the current `safe-2`/`bold-2`/`safe-3`/`risky-1`/`risky-3` arm-id scheme;
`safe-1`/`risky-3` are now retired):

| account_id | n tagged | structure_stop % | premium_stop % | tp1 % | trail % |
|---|---|---|---|---|---|
| safe-1 (retired) | 30 | 0.0% | 93.3% | 3.3% | 0.0% |
| safe-3 | 89 | 33.7% | 38.2% | 13.5% | 12.4% |
| risky-1 | 123 | 24.4% | 32.5% | 18.7% | 13.8% |
| risky-3 (retired) | 129 | 7.8% | 65.1% | 8.5% | 7.8% |
| safe (legacy safe-2) | 113 | 26.5% | 38.9% | 14.2% | 12.4% |
| bold (legacy bold-2) | 63 | 41.3% | 25.4% | 15.9% | 14.3% |

structure_stop is a material (23–41%) share of exits for every arm that has ever run
`stop_mode:"structure"`; premium_stop dominates for arms/periods where structure mode was
off (`safe-1`, and `risky-3` post its 2026-08-10 de-arm).

**Simultaneity** — entry events reconstructed by grouping trades with the same
`(date, c_or_p side)` whose entry timestamps fall within a 3-minute window (a proxy for "the
same shared-signal fire"; 187 such cohorts found, 104 of them multi-arm). Within each
multi-arm cohort, all same-stage cross-arm exit-timestamp pairs were compared:

| exit stage | pairs within ≤1s | ≤5s | ≤60s | ≤300s (one 5m bar) |
|---|---|---|---|---|
| **structure_stop** | 40/154 (26.0%) | 63/154 (40.9%) | 72/154 (46.8%) | **152/154 (98.7%)** |
| premium_stop | 81/246 (32.9%) | 136/246 (55.3%) | 148/246 (60.2%) | 200/246 (81.3%) |
| tp1 | 7/73 (9.6%) | 9/73 (12.3%) | 10/73 (13.7%) | 29/73 (39.7%) |
| trail | 12/52 (23.1%) | 24/52 (46.2%) | 26/52 (50.0%) | 35/52 (67.3%) |
| ribbon_flip | 3/19 (15.8%) | 7/19 (36.8%) | 9/19 (47.4%) | 19/19 (100.0%) |

**Reading this honestly (OP-33):** the discriminating signature is NOT at ≤60s — journal
fill-timestamp jitter (separate broker order per arm, logged after each account's own fill
confirmation) smears sub-minute precision for every stage, including premium_stop.
The clean signal is at the **bar-close timescale (≤300s = one 5m bar)**: `structure_stop`
clusters at 98.7% (i.e. essentially every cross-arm structure-stop pair shares a bar),
matching the mechanism exactly (all arms test the same closed 5m bar against the same
`trigger_level`). `tp1` (39.7%) and `trail` (67.3%) — the genuinely arm-specific stages,
since they key off each arm's own `tp1_premium_pct`/`trail_pct` and current premium — cluster
markedly less even at the 5-minute scale. `premium_stop`'s 81.3% is higher than expected for
a "purely arm-specific" stage, but this is explained by Q1's finding: for most of the
history, every arm shared the SAME `premium_stop_pct` (only the 2026-08-09 risky-3 A/B and
recent per-arm `exit_patch` overlays introduced real divergence), so a shared percentage
stop on a shared entry premium also tends to trip on the same bar. This is a genuine finding,
not a wash: **structure_stop is the most mechanically-forced-simultaneous stage in the
book**, exactly as hypothesized.

## Q4 — effective sample size / go-live gate

Read `setup/scripts/go_live_gate.py` in full and called its own `build_report()` function
directly (bypassing `main()`, so nothing was written to `OUT_JSON`/`OUT_MD`, and passing
`trades_enriched_refresh` as an already-completed marker so its `refresh_trades_enriched()`
side-effecting rebuild step never ran — genuinely read-only against the on-disk
`analysis/trades-enriched.jsonl`, no reimplementation of its math):

```
overall stat pass (gates go-live): False

== per_arm (THIS is what gates overall_verdict) ==
safe-3   -> pass=False  n_days=29  as_traded_ci_lower=0.402
safe-2   -> pass=False  n_days=33  as_traded_ci_lower=0.294
risky-1  -> pass=False  n_days=29  as_traded_ci_lower=0.392
bold-2   -> pass=False  n_days=24  as_traded_ci_lower=0.342

== book_wide_correlated_rollup (DISCLOSURE ONLY -- does not gate) ==
n_trading_days (calendar days, all arms summed per day) = 44
as_traded ci_lower = 0.396
pass field (unused for gating) = False
```

**Reading `statistical_criterion()` (go_live_gate.py:276-346) and `build_report()`
(go_live_gate.py:1206 ff.) directly**, the criterion that actually decides
`overall_verdict` is:

```python
statistical["per_arm"] = {arm_id: statistical_criterion(engine_rows, arm_id) for arm_id in ACTIVE_ARMS}
stat_pass = all(statistical["per_arm"][a].get("pass") for a in ACTIVE_ARMS)
```

`statistical_criterion(rows, arm_id)` scopes `rows` to **one arm only**
(`[r for r in rows if r["arm"] == arm_id]`) before computing `_daily_totals` (sum P&L per
calendar date, that arm's dates only) and bootstrapping over that arm's OWN day-value list.
**It never flattens multiple arms' (arm, date) rows into one pooled array of pretend-i.i.d.
samples.** The correlation the queue item worried about — arm A's and arm B's day-4 P&L
both driven by the same structure-stop bar close — cannot inflate arm A's own CI, because
arm B's numbers never enter arm A's bootstrap input at all.

There IS a second key, `book_wide_correlated_rollup` (`statistical_criterion(engine_rows,
arm_id=None)`), that pools all arms together — but it does so by **summing all arms'
P&L into one value per calendar date** (`_daily_totals` groups by `r["date"]` only, not by
`(arm, date)`), giving `n_trading_days=44` **unique calendar days** — which already IS the
"clustered by date" treatment the queue item asked me to compute as an alternative. There is
no separate "unclustered by (arm, date)" version of this key to contrast it against — the
code was never written to produce one, so there's nothing to re-derive; the query's proposed
clustering fix is already what this key does. Its own internal `pass` field is computed but
discarded — `groups["statistical"] = {**statistical, "pass": stat_pass}` overwrites the
top-level `pass` with the per-arm-only `stat_pass`, and `overall = all(g["pass"] for g in
groups.values())` reads only that top-level key. **`book_wide_correlated_rollup["pass"]`
never reaches `overall_verdict` today.**

**Conclusion on Q4:** the go-live gate's day-level bootstrap, as coded, does not exhibit the
specific arm-day-pooling degeneracy hypothesized. CI-lower is identical whether or not you
"cluster by (date, entry-minute, trigger_level)" for the criterion that actually gates
arming, because that criterion was never pooling across arms in the first place. The gate
is RED on every arm today by roughly 0.6-0.7 of CI-lower headroom (need >1.0, currently
0.29-0.40) — nowhere near the margin where this distinction would matter even if it did
apply.

**What IS real, and worth carrying forward (not a code bug, a design caveat):** `stat_pass`
requires all 4 arms to pass their OWN bootstraps independently. Because structure-stop days
are shared market events across the 3-of-4 arms currently resolving `stop_mode="structure"`,
a day that is good/bad for one arm tends to be good/bad for its siblings too (Q3's 98.7%
same-bar clustering). So "4-for-4 arms passing" is weaker evidence of 4 independently
-replicated edges than the gate's structure implies — it is closer to "the shared signal
plus each arm's own sizing/exit-shape overlay survives," which is still meaningful (sizing
and premium-stop/tp1/trail DO differ per arm — Q2/Q3 show real per-arm divergence there) but
is not literally 4 uncorrelated trials of "is the entry+structure-stop edge real." Recommend
this be added as a one-line disclosure in a future (post-freeze) `go_live_gate.py` change —
NOT actioned here (config freeze to 2026-10-30; measurement only).

## What I could NOT verify

- Today's (2026-09-11) specific 3 entry events cited in the queue item are **not yet in
  `journal/trades.csv`** as of this read (checked: zero rows with `date=2026-09-11`) —
  journaling appears to lag same-day live fills. I could not independently re-derive the
  "within 1 second" figure for today's specific events from the journal; I relied on the
  46-history-wide pattern (Q3 table) as the corroborating evidence instead, which shows the
  same signature (98.7% same-bar clustering for structure_stop) across 154 historical
  cross-arm pairs.
- `automation/state/pnl-statement.json`'s `round_trips` (869 entries, broker-fills-derived)
  carry no exit-stage field, so Q2/Q3 rely on `journal/trades.csv`'s `notes_short`
  free-text tag alone. That tag is operator/heartbeat-authored prose, not a structured
  machine field — a small number of exits could be mis-tagged or untagged (53/600, 8.8%,
  had no `stage=` tag at all and were excluded rather than guessed at).

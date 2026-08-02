# DATA-PROVENANCE — backtest/data feed strata

> Living doc. Which data source produced which rows of the cached bar files, and the
> rules that keep new rows provenance-consistent. Born from the **premarket-volume
> incident (2026-07-14)**; append new strata/incidents here, don't fork dated copies.

## Why this matters

`backtest/data/*.csv` looks homogeneous but is a **patchwork of feeds** with different
volume semantics. Volume-based work (RVOL, volume-confirmation gates, premarket tape
reads) that spans a feed seam compares apples to oranges. Price (OHLC) is near-identical
across these feeds; **volume is not**.

## Feed strata — spy_5m canonical chain (`spy_5m_2026-05-19_*.csv`)

| Rows | Source | Premarket vol | RTH vol scale | Notes |
|---|---|---|---|---|
| 2026-05-19 .. 2026-05-29 (seed) | **Alpaca SIP** | ✅ real (66 bars/day) | consolidated (SIP) | Seed also carried post-market rows to 19:55 |
| 2026-06-01 .. 2026-07-14 **RTH only** | **yfinance** (Yahoo consolidated) | — | ~7% ABOVE Alpaca SIP (06-10: 51.7M vs 48.3M) | Bounded stratum: ends 2026-07-14 |
| 2026-06-01 .. 2026-07-14 **premarket** | **Alpaca SIP** (repaired 2026-07-14) | ✅ real | consolidated (SIP) | Replaced in place; RTH rows untouched (verified value-identical) |
| 2026-07-15 onward | **Alpaca SIP** (full session) | ✅ real | consolidated (SIP) | `append_today.py` SPY path switched off yfinance |

## Other files

| File(s) | Source | Volume caveat |
|---|---|---|
| `spy_5m_2025-*` masters (built by `extend_data_v2.py`) | **Alpaca IEX** | 🚨 IEX volume ≈ 2-4% of consolidated. NEVER mix with SIP/Yahoo volume in one calc. Premarket window starts 09:00 ET (13:00Z), not 04:00. |
| `spy_5m_2024-01-18_2024-12-31.csv` + merged `spy_5m_2024-01-18_2026-07-22.csv` (OPRA-BACKFILL-2026-07-31) | **Alpaca IEX** — same feed/script as the 2025-* masters above, so this is a **pure floor extension, not a new stratum**. Merged onto the existing `spy_5m_2025-01-01_2026-07-22.csv` — **independently re-verified unmutated 2026-08-02** (unchanged mtime, exact row-for-row equality on the shared range, hash pinned in `test_opra_2025_spy_master_unmutated_by_2024_backfill`) — with 0 dupes on `timestamp_et`. | Same IEX volume caveat as above. 2024-01-18 = verified TRUE FLOOR of Alpaca's SPY 0DTE option-bar history (binary search; 2024-01-16/17 = zero option bars across a ±10-strike net). **NOT uniformly reliable onward** — completeness verification (2026-08-02) found **239 of 241 targeted 2024 trading days usable**, not all of them: `2024-02-02` has zero real option bars (options-side gap, live-reconfirmed against an 82-contract net) and `2024-12-23` has only 11 of 78 expected SPY bars (SPY-side gap, session cuts off 10:20 ET, live-reconfirmed against Alpaca — genuine IEX single-venue thinness, NOT a fetcher bug; the options cache for that same day is fully populated). 3 more days carry a disclosed minor tail-only SPY-bar gap (≤5 bars). `expand_opra_cache.py` NOT modified — its `resolve_spy_master()` glob still resolves the 2025-01-01 lineage (guarded); a dedicated one-off (`_backfill_opra_2024_01_18_2024_12_31.py`) reads this new master instead. **Full detail + per-day methodology + the mandatory disclosure rules for any study touching 2024: `analysis/deep-research/OPRA-BACKFILL-2026-07-31.md`.** |
| `spy_5m_2026-05-08_*` chain (retired May chain) | yfinance appends | Premarket volume = 0 for sessions ≥ 2026-05-13. NOT repaired (superseded; repair tool works on it if ever needed). |
| Intermediate `spy_5m_2026-05-19_<06-01..07-10>.csv` snapshots | seed + yfinance | Premarket volume = 0 for sessions ≥ 06-01. NOT repaired — superseded daily snapshots; consumers auto-discover the latest end-date file. |
| `vix_5m_*` | yfinance | VIX is an index — volume is legitimately absent. Unaffected. |
| `vix_daily_proxy_2024-01-18_2024-07-30.csv` (OPRA-BACKFILL-2026-07-31) | **yfinance DAILY** (degraded proxy) | 🚨 **LOUD FLAG:** yfinance's 1h VIX endpoint is capped at "within the last 730 days" of the *call* date, not the query range — from 2026-07-31 that boundary is 2024-07-31, so hourly VIX for 2024-01-18..2024-07-30 is permanently unfetchable via this path. Fell back to daily O/H/L/C (one row/day, 09:30 ET anchor). Deliberately kept OUT of the `vix_5m_*` hourly chain — never merged, never auto-discovered by the same glob — so no consumer silently treats daily-shaped data as hourly. Any research spanning this window must disclose the coarser VIX granularity. |
| `data/highres/SPY_1m_*` | Alpaca **IEX** | Same IEX volume caveat. |
| `data/options*` | Alpaca OPRA | 🚨 **RESOLUTION CAVEAT (OPTION-BAR-RESOLUTION-BIAS-2026-08-02):** `backtest/data/options/*.csv` is **5-MINUTE bars only** (`fetch_option_data.py` hardcodes `timeframe="5Min"`) — served by `backtest/lib/option_pricing_real.load_contract_bars`, a silent default until 2026-08-02 (now an explicit, logged `resolution` kwarg — see that file's module docstring). A stop breached and recovered INSIDE a 5-minute bar is invisible at this resolution: measured on the canonical real-fills population (123 positions, all 6 arms, identical production decision core both times, ONLY resolution varied), 4 positions' exits flip from non-stop to stop-ONLY-at-1-minute, **0 the other way** (one-directional — 5-min never invents a phantom stop, it only misses real ones), aggregate P&L swing **$1,821.75**, always in the direction of 5-min FLATTERING P&L. Full measurement + the two live-knob re-verifications (structure_stop_study SS-B: CONFIRMED; ribbon_ride_strike_exit_ab ATM-over-OTM-2: CONFIRMED; ITM-2: CONFIRMED-still-rejected once a coverage-gap confound is isolated — see below): `analysis/deep-research/OPTION-BAR-RESOLUTION-BIAS-2026-08-02.md`. **Any study/scorecard dated before 2026-08-02 that walks option-bar stops/TPs via this cache may under-detect intra-bar stop hits** — disclosed in `analysis/recommendations/README.md`. Honest 1-minute bars: live REST via `backtest/tools/_option_bars_1min_cache.fetch_1min_cached` (wraps `exit_shape_parity_study.fetch_option_bars`), cached to `data/highres/{symbol}_1m_{date}.csv`. **Separate, adjacent finding from the same investigation:** the 5-min disk cache also has a material *coverage* gap (not a resolution gap) that widens with distance from the OTM-2 default — 0/250 signals missing at OTM-2, 1/250 at OTM-1, 6/250 at ATM, 19/250 at ITM-2 (`ribbon_ride_strike_exit_ab_1min_coverage_matched_2026-08-02.json`) — a strike-comparison study using this cache is measuring different-sized populations per strike, independent of the resolution issue. |

## The incident (2026-07-14) — summary

- **Symptom:** every 5m premarket bar (04:00–09:25 ET) had `volume=0` for all 29 sessions
  2026-06-01..2026-07-13 in `spy_5m_2026-05-19_2026-07-13.csv`; 09:15–09:25 bars missing
  entirely (63 bars/session instead of 66).
- **Root cause:** `append_today.py` fetched SPY from **yfinance**, whose extended-hours
  intraday bars carry no volume and drop those 3 bars. The appender had done this since
  its **first fire (2026-05-13)** — the "2026-06-01 onset" was a provenance seam, not a
  behavior change: rows ≤05-29 came from the Alpaca-SIP seed, rows ≥06-01 from appends.
- **Proof of seed provenance:** Alpaca SIP re-fetch of 2026-05-27 matches the seed bar-for-bar
  (premarket vol 1,196,584; 08:30 bar 27,319). IEX same day: 6 bars / 2,711 shares — useless.
- **Fix (shipped 2026-07-14 evening):**
  - `backtest/tools/alpaca_bars.py` — SIP fetch (04:00–16:00 ET, DST-correct, 403-proof
    clamp for the Basic-plan 15-min delay, `sip_aged_at()` age gate).
  - `append_today.py` SPY path → Alpaca SIP; waits ≤25 min for the session to age
    (EOD task fires 16:00:33 ET; full session aged 16:16 ET; backtest venv is reaper-exempt);
    way-too-early runs NOOP instead of appending a partial day. yfinance remains a loud,
    ledger-flagged fallback (`source` field in `data-versions.jsonl`).
  - `backtest/tools/repair_premarket_volume.py` — replaced the dead premarket rows in the
    two newest chain files with SIP bars; RTH rows verified value-identical; originals in
    `backtest/data/_backup_premarket_zero/`; ledger rows `action=premarket_repair` carry
    old/new hashes.
  - Guards: `test_premarket_volume_alive_in_latest_chain` +
    `test_append_today_spy_uses_alpaca_sip` in `backtest/tests/test_graduated_guards.py`.
- **Side effect fixed:** a midday manual append used to write a partial day the next-day
  window would never re-fetch; the age gate now NOOPs those runs.

## Consumer audit (2026-07-14) — was anything downstream poisoned?

Swept every volume-feature consumer (orchestrator.py, heartbeat_core.py, watcher_live.py,
gate_sweep_volume_morning.py, trendline_break_battery, all crypto validators/benchmarks).
**Verdict: clean.** Every real volume-gated path (`f9_vol_mult`, TBR_HIGH_VOL,
BEARISH_REJECTION_MORNING, ORB-RVOL, breakout volume-confirm) slices to RTH ≥09:30 *before*
computing any volume feature — independent of this defect, predates it. No scorecard,
validator verdict, or research JSON from 2026-06-01..07-14 is volume-contaminated.

Residual (price, not volume, and NOT chased further): the missing 09:15-09:25 bars also
carried price data. `refresh_levels_intraday.py` — the LIVE production PMH/PML path — reads
no cache CSV (live-fetch only), so production trading levels were never exposed. Only
backtest-time PMH/PML re-derivation (`backtest/lib/levels.py`, `pml_scan.py`) could
theoretically miss a premarket extreme that fell inside that exact 3-bar window — narrow,
research-only, and moot now the cache is repaired. Not investigated further; flag here if a
specific day's PMH/PML research result ever looks suspicious.

## Winter-frame (DST) join caveat — 2026-08-02 recurrence

`backtest/data/spy_5m_*.csv` AND `backtest/data/options/*.csv` share the same fixed
`-04:00` offset-label writer bug (root cause + fix: `backtest/lib/et_frame.py`,
`markdown/audits/DST-FRAME-AUDIT-2026-07-02.md`). The UTC instant of every row is correct;
the offset LABEL is wrong for EST months (Nov–Mar). **This is orthogonal to the volume
strata above (a timestamp-parsing issue, not a source/feed issue) but interacts with the
same files**, so any study spanning an EST month needs BOTH disclosures.

**2026-08-02 finding:** the fix shipped 2026-07-02 as an opt-in library
(`et_frame.parse_timestamp_et`), not enforced at the shared OPRA loader
(`backtest/lib/option_pricing_real.py::load_contract_bars`, which still returned raw,
un-normalized, tz-aware fixed-offset data). Full re-audit, quantified delta on a real
consumer, and a detection guard shipped to stop a 4th occurrence:
`analysis/deep-research/DST-FRAME-BLAST-RADIUS-2026-08-02.md`.

**2026-08-02 ROOT FIX LANDED (same day, follow-up lane):** `load_contract_bars()` gained a
keyword-only `frame: Optional[str] = None` parameter (`None` = unchanged raw tz-aware output,
byte-identical for every pre-existing caller; `"wall-v1"`/`"et-v2"` return an
already-normalized naive column via `et_frame.parse_timestamp_et`). `exit_manager_walk.
walk_exit_manager`, `simulator_credit.simulate_credit_trade`, and `simulator_debit.
simulate_debit_trade` all gained a `frame: str = "wall-v1"` parameter, replacing their prior
unconditional bare `.tz_localize(None)` strips — default reproduces every one of their
combined 90+ pre-existing call sites byte-for-byte (pinned:
`test_dst_frame_fix_walk_exit_manager_frame_kwarg_diverges_on_winter`'s own
`res_default == res_wall` assertion). Winter canary (`SPY250102C00580000`, true-ET 13:00)
now resolves to **$2.44** via `frame="et-v2"` through the real production functions (was
$8.25 via `frame="wall-v1"`, unchanged/reproduced); summer control shows 0-minute/$0.00
delta. `bold_fullhist_replay.py`'s two `walk_exit_manager` call sites (`run_anchor_
validation` + the elite-bull-requal qty5-rescale closure) and `test_bold_fullhist_replay.py`'s
own inline anchor test now explicitly pass `frame="et-v2"` — zero behavior change today
(every populated date is summer/EDT), closes the gap before a winter date is ever added.

**A SECOND, subtler bug found+fixed while wiring this in:** `et_frame.parse_timestamp_et`'s
`et-v2` branch does not honor its own documented "naive input passes through unchanged"
contract (only its `wall-v1` branch does) — it unconditionally reinterprets already-naive
digits as UTC and shifts them by the zone offset. This corrupted `walk_exit_manager`'s
handling of a `five_min_spy_df` that a caller (`bold_fullhist_replay.run_anchor_validation`)
had already pre-parsed to naive et-v2 upstream — caught live by
`test_bold_fullhist_replay.py` failing with a wrong-direction P&L on a real anchor the moment
`frame="et-v2"` was wired in, not shipped silently. Fixed LOCALLY in
`exit_manager_walk._reframe_series` / `simulator_credit._reframe_series` (deliberately NOT by
modifying `et_frame.py` itself — out of scope, heavily used, heavily guarded elsewhere).
Guard: `test_dst_frame_fix_reframe_series_passes_through_already_naive_input`.

**Live-knob re-verification (task requirement, done 2026-08-02):** both v15.3
CHART-STOP-PRIMARY (`structure_stop_study.py` SS-B) and the ATM-over-OTM-2 strike knob
(`ribbon_ride_strike_exit_ab.py` axis 1, incl. the ITM-2 rejection) were traced end-to-end —
NEITHER actually routes through `exit_manager_walk.walk_exit_manager` or the buggy
`load_contract_bars` join path exposed to cross-frame mixing. Both tool families run their
OWN independent walk (`plan_exit_actions` called directly via `t4_exit_matrix.replay()` /
`ribbon_ride_strike_exit_ab.fetch_entry_and_bars()`), and every timestamp in that chain
(`_signal_cache.py` → `orchestrator.run_backtest(use_real_fills=True)` → `simulate_trade_real`'s
`frame="wall-v1"` default, through `tw8_level_context.py`) is wall-v1-consistent — confirmed
both by reading every file in the chain (zero `et-v2`/`tz_convert("America/New_York")` markers
anywhere in it) AND empirically (the actual `signal-set.json` 250-signal population's earliest
WINTER entry is 10:30 ET, the wall-v1 clipped-open signature — true et-v2 would show ~09:30-
09:40 matching summer). **Verdict: both knobs STILL-CONFIRMED — not a re-run producing the
same number, but proof neither was ever on the affected path.** structure_stop_study.py's
Layer B (real-fills anchor) is doubly unaffected — it never touches the buggy CSV cache at
all, using `exit_shape_parity_study.fetch_option_bars` (live REST) instead.

**Affected artifacts (disclose when citing):**
- `analysis/recommendations/PIVOT-PREMIUM-SELLING-SCORECARD.md` — the LEAD IC cell's
  published OOS expectancy (**+$23.03/tr**) is overstated vs the frame-consistent re-run
  (**+$15.30/tr, −33.6%**). The scorecard's own verdict (LEAD-not-EDGE, NOT shippable) does
  **not** change — a lower true expectancy sits further from beating the random-strike null
  the scorecard already failed on, not closer. Cite the corrected +$15.30/tr number for any
  new work; the scorecard file itself stays as the historical record of what wall-frame
  measurement originally showed (same "wall-frame scorecard stays citable for wall-frame
  comparisons" convention as the 2026-07-02 audit).
- `backtest/tools/bold_fullhist_replay.py::run_anchor_validation` — **FIXED 2026-08-02**
  (now passes `frame="et-v2"`); was zero-exposure at the time it was found (`ANCHOR_FILLS`
  0/7 winter) and stays that way going forward.
- `backtest/tools/elite_bull_postfix_requal_2026_07_31.py` — AFFECTED (et-v2 SPY vs
  bare-stripped OPRA reaching `walk_exit_manager`, no `tz_convert` step; found in the
  2026-08-02 16-file sweep). Its output `elite-bull-requal-2026-07-31.json` was cited in
  `analysis/deep-research/FRIDAY-DIAL-IN-2026-07-31.md` to justify a `block_elite_bull:
  false` lift trial on bold-2 — **verified 2026-08-02: that trial was independently armed
  2026-08-01 then REVERTED SAME SESSION** for unrelated reasons (a misattributed basis +
  properly-powered contrary evidence, see `automation/state/aggressive/params.json`'s
  `_block_elite_bull_trial_doc`) — `block_elite_bull` is currently `true` (armed/blocking) on
  both accounts, so there is no CURRENT live exposure from this citation. The file's own
  DST-frame mismatch is still real and should be fixed before it is ever cited again.
- `backtest/autoresearch/rrw_bull_veto_study.py` — AFFECTED (its own direct OPRA-vs-bear-event
  join was correctly frame-matched, but the UPSTREAM `entry_time_et` it trusts as et-v2 —
  from `orchestrator.run_backtest(use_real_fills=True)` — is actually still wall-v1-labeled
  at the source, despite the study's own commit note claiming the DST-frame fix was applied).
  Cited in `automation/overnight/queue.md` (RRW-AS-VETO-STUDY) as a `done-failed-both-
  overlays-honest-kill` — **zero live exposure**: no params/trading-path file was ever
  touched by this study regardless of verdict (its own stated policy), so a soft small-n
  count does not change anything armed.
- Any OTHER consumer of `backtest/lib/simulator_credit.py` / `simulator_debit.py` /
  `backtest/lib/exit_manager_walk.py::walk_exit_manager` whose caller derives its entry time
  via an et-v2-style parse but doesn't explicitly pass `frame="et-v2"` into these functions
  (now that they support it) — full inventory (SAFE / AFFECTED / UNCLEAR) in the blast-radius
  doc above and its `test_graduated_guards.py::_DST_FRAME_PATTERN_ALLOWLIST` companion.

**Rule:** any study joining SPY/underlying timestamps to OPRA option timestamps must verify
BOTH sides were parsed with the SAME `et_frame` convention — never trust a docstring or an
`import et_frame` line alone; verify the actual call. As of 2026-08-02, `load_contract_bars`,
`walk_exit_manager`, `simulate_credit_trade`, and `simulate_debit_trade` all accept an
explicit `frame=` to do this correctly in one call — prefer that over a hand-rolled
`.tz_localize(None)`/`tz_convert` sequence. Guards: `backtest/tests/test_et_frame_guards.py`
(library correctness) + `backtest/tests/test_graduated_guards.py::test_dst_frame_*` (bug
pinning + new-consumer scan) + `test_dst_frame_fix_*` (the root-fix proof, added 2026-08-02).

## Rules

1. **Canonical chain appends = Alpaca SIP only.** Never IEX for anything volume-bearing;
   never yfinance for extended hours.
2. **Disclose the stratum** when any volume calc spans 2026-05-29/06-01 or 2026-07-14/07-15
   RTH seams (~7% Yahoo-vs-SIP level shift), or touches the IEX masters.
3. **New bar producers register here** (file pattern, feed, window, volume semantics)
   before their output is consumed.
4. **New OPRA/SPY join consumers** must route both sides through `lib.et_frame.
   parse_timestamp_et` with the SAME `frame`, never a bare `.tz_localize(None)` strip on
   one side only — see the winter-frame caveat above.

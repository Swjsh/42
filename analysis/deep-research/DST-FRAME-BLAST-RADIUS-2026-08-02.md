# DST-Frame Blast Radius — a re-violated lesson, graduated to a guard (2026-08-02)

> Overnight integrity lane. Trigger: building `backtest/tools/fleet_arm_replay.py` tonight
> (commit `151123a2`) independently re-hit the exact DST wall-time artifact the 2026-07-02
> incident already found and fixed (`markdown/audits/DST-FRAME-AUDIT-2026-07-02.md`,
> `backtest/lib/et_frame.py`). The fix EXISTS and was NOT universally applied. Per this
> repo's own doctrine (CLAUDE.md C7/OP-25), a re-violated lesson is a MISSING GUARDRAIL, not
> a repeated mistake. This doc pins the mechanism, maps the blast radius, quantifies the
> delta on a real high-stakes consumer, and ships the guard that stops a 4th occurrence.

## Verdict

- **Mechanism confirmed, reproduced live, quoted below.** Not theoretical.
- **Two confirmed-affected consumer chains found**, one with a **material but
  non-decision-flipping** quantified delta, one with a **live mechanism but zero current
  numeric exposure** (population-timing luck, not a fix).
- **No live trading knob touched.** Both affected chains are offline research artifacts;
  neither backs an armed `params.json` value.
- **Guardrail shipped and RED-proofed** in `backtest/tests/test_graduated_guards.py`
  (3 new tests). The correct PERMANENT fix (normalize the frame inside
  `option_pricing_real.load_contract_bars()` itself, once) is **deferred** — that file is
  explicitly out of scope tonight (a concurrent lane owns the 5-min-resolution question
  there) and `exit_manager_walk.py` shares that exact surface (live docstring referencing
  the same concurrent lane, dated today).

---

## 1. The mechanism, pinned

### Which side is which

Both `backtest/data/spy_5m_*.csv` (SPY/underlying) and `backtest/data/options/*.csv` (OPRA)
were written by the same buggy pre-2026-07-02 path in `tools/extend_data_v2.py`: `ts_et =
ts_utc - 4h`, then a **hardcoded `-04:00` string suffix**, year-round. The UTC instant of
every row is correct; the offset **label** is wrong for EST months (Nov–Mar). Verified in the
raw cache tonight:

```
backtest/data/options/SPY250102C00580000.csv (2025-01-02, a verified EST day):
timestamp_et,open,high,low,close,volume,vwap,trade_count
2025-01-02T10:30:00-04:00,8.42,8.42,8.42,8.42,1,8.42,1
```

`backtest/lib/et_frame.py` is the fix that already exists: `parse_timestamp_et(series,
frame)` with two conventions — `wall-v1` (legacy: parse the embedded offset, strip tz, KEEP
the wall-clock digits as printed — for the row above, "10:30") and `et-v2` (DST-correct:
parse `utc=True`, `tz_convert("America/New_York")`, strip tz — for the row above, true ET
"09:30", one hour earlier). Its own docstring names the trap: **"NEVER join a naive et-v2
series against a naive wall-v1 series."**

### What the SHARED OPRA loader actually returns (not documented before tonight)

`backtest/lib/option_pricing_real.py::load_contract_bars()` — the one function nearly every
real-fills consumer in the repo calls — does:

```python
df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
```

Live-verified tonight (`backtest/.venv`, pandas 2.3.3): given the CSV's embedded `-04:00`
string, this is **NOT wall-v1 and NOT et-v2** — it is a **third, undocumented convention**:
tz-**AWARE**, fixed offset (`dtype: datetime64[ns, UTC-04:00]`). Comparing this directly
against ANY naive datetime (wall-v1 OR et-v2) raises a hard `TypeError` — a LOUD crash, not a
silent corruption. The silent corruption only happens once a caller "fixes" that crash the
natural-but-wrong way: bare `.dt.tz_localize(None)` (strip the tz, keep the digits — this is
byte-identical to wall-v1) on the OPRA side, while the SPY/underlying side was parsed et-v2.
That specific combination is what fleet_arm_replay.py's first draft did (per its own commit
message), and it is what several still-shipping consumers do today (Section 2).

### Concrete winter example (quoted, both paths, live data)

Contract `SPY250102C00580000`, 2025-01-02 (EST day). A SPY trigger that TRULY fired at
**13:00 ET** (as an et-v2-parsed SPY series would correctly label it):

| path | OPRA row picked (as displayed in its OWN frame) | raw-CSV (frame-invariant) label | close |
|---|---|---|---|
| **buggy** (OPRA bare-`.tz_localize(None)` = wall-v1; SPY et-v2) | `13:00:00` | `13:00:00-04:00` | **$8.25** |
| **correct** (OPRA re-parsed et-v2, matching SPY) | `13:00:00` | `14:00:00-04:00` | **$2.44** |

Both picks *display* as "13:00:00" — that is the trap: each `bar_at_or_after()` call finds a
row labeled ≥ the query time **within its own frame**, so a naive before/after comparison of
the two picks' display labels is meaningless (subtracting them gives 0). Mapped back to the
frame-invariant raw-CSV label, the buggy path is picking a bar from a **full hour earlier**
(true UTC instant) than the correct one — i.e. **stale, not future**: the bug prices the
trade against option data from an hour before the SPY signal actually fired.

Swept across the session (same contract, same day):

| true-ET query | buggy pick (raw label) | close | correct pick (raw label) | close | price delta |
|---|---|---|---|---|---|
| 09:35 (session open, edge case) | 10:30 | $8.42 | 10:35 | $6.99 | +20.5% |
| 11:00 | 11:00 | $10.00 | 12:00 | $5.65 | +77.0% |
| 13:00 | 13:00 | $8.25 | 14:00 | $2.44 | +238.1% |
| 14:45 | 14:45 | $2.10 | 15:45 | $3.53 | −40.5% |

Control, same experiment on a summer (EDT) contract `SPY250701C00612000` (2025-07-01): buggy
and correct picks agree **bar-for-bar, 0:00:00 delta, $0.00 price delta** — confirming this is
specifically a DST/winter artifact, not a general bug in either path. Both tables are now
pinned as pytest guards (Section 4).

---

## 2. Blast radius inventory

Scope: every place that (a) joins a SPY/underlying timestamp to an OPRA option timestamp, or
(b) parses either side's raw `timestamp_et` column independently. `git grep` for
`option_pricing_real` imports found **87 files** touching the raw OPRA loader; **24** call the
raw join primitives (`bar_at_or_after` / `bar_containing` / `quote_at_index`) directly rather
than delegating to an already-verified wrapper. Classification below does NOT trust a
docstring or an import line alone (L249) — every SAFE/AFFECTED verdict in the "verified"
tables was confirmed by reading the actual call chain; the "pattern-flagged" table was NOT
individually traced (see caveat).

### 2a. Core shared libraries (highest leverage — fully verified)

| File | Verdict | Why |
|---|---|---|
| `backtest/lib/option_pricing_real.py::load_contract_bars` | **ROOT CAUSE** | Returns tz-aware fixed-offset data with zero frame normalization. Every downstream consumer must independently remember to reconcile — most do not. **Out of scope to edit tonight** (concurrent lane owns the 5-min-resolution question in this exact file). |
| `backtest/lib/simulator_real.py::simulate_trade_real` | **SAFE** | Explicit `frame:` parameter threaded end-to-end (`_naive_in_frame` + `parse_timestamp_et(opt_df["timestamp_et"], frame)`, line 428). SPY and OPRA always parsed with the SAME frame. This is production's `use_real_fills=True` path. |
| `backtest/lib/simulator_real_trailing.py` | **SAFE** | Same `frame:` threading pattern as `simulator_real.py`, verified independently. |
| `backtest/lib/simulator_credit.py::_load_leg_df` / `simulate_credit_trade` | **AFFECTED (confirmed + quantified, §3)** | No `frame` parameter at all. OPRA unconditionally bare-`.tz_localize(None)`-stripped (wall-v1); `entry_time_et` accepted from the caller as-is via `_normalize_naive` (strips tz if present, no verification of WHICH frame). Safe only if the caller happens to pass wall-v1-consistent times. |
| `backtest/lib/simulator_debit.py::_load_leg_df` / `simulate_debit_trade` | **AFFECTED (same gap)** | Explicitly reuses `simulator_credit`'s loader "byte-for-byte" — inherits the identical gap. |
| `backtest/lib/exit_manager_walk.py::walk_exit_manager` | **AFFECTED — the real keystone** | Used directly by `fleet_arm_replay.py`, `bold_fullhist_replay.py`, `engine_fullhist_replay.py`, `dojo_exit_diversity_replay.py`, `pullback_hold_bull_replay.py`, `ladder_fullhist_replay.py`, `edge_matrix_bull_level_reclaim_quality.py`, `edge_matrix_sr_flip_retest.py`, `wick_lane_fullhist_replay.py` and more. Lines 170-180: bare `.tz_localize(None)` on `opt_df["timestamp_et"]` (unconditional) and on `entry_time_et` (whatever frame the caller passed, no check). **Confirmed corrupting** a real call site (§3b). Sharing a fix location with `option_pricing_real.py` would close this for every listed caller at once — **deferred**, see §5. |

### 2b. Confirmed AFFECTED consumer chains (individually traced, not pattern-matched)

| File | Mechanism | Feeds |
|---|---|---|
| `backtest/autoresearch/_pivot_premium_selling.py` | `_load_spy_master()` parses SPY et-v2 (`utc=True` → `tz_convert("America/New_York")` → `tz_localize(None)`, lines 150-154); `_spot_and_decision()` returns that et-v2 `decision_dt`, fed straight into `simulator_credit.simulate_credit_trade` (wall-v1 OPRA). | `analysis/recommendations/PIVOT-PREMIUM-SELLING-SCORECARD.md` — **quantified in §3a** |
| `backtest/autoresearch/_pivot_premium_finalize.py` | Imports `_pivot_premium_selling as P`, calls `P._spot_and_decision` directly (`run_real`, lines 73/95/120). Same mechanism. | Same scorecard, "finalize" section |
| `backtest/autoresearch/_pivot_premium_ic_validate.py` | Same reuse pattern (per the scorecard's own "Artifacts" section). | Same scorecard, IC-validate section |
| `backtest/autoresearch/_regime_switch_book.py` | Explicitly reuses `_pivot_premium_selling`'s `_load_spy_master` / `_spot_and_decision` "so the condor sleeve is identical to the validated scorecard run" (own docstring, lines 24-25). | Its own regime-switch book (not yet a scorecard) |
| `backtest/tools/bold_fullhist_replay.py::run_anchor_validation` | `entry_time_et = dt.datetime.fromisoformat(a["entry_ts_et"])` — a REAL broker-fill timestamp (true-ET) from `ANCHOR_FILLS` — passed with `opt_df = load_contract_bars(symbol)` **unstripped** straight into `walk_exit_manager` (lines 469-487). | Bold's real-fills anchor pass-rate (quoted in `fleet_arm_replay.py`'s own commit message: "safe-3 85%, risky-1 83%, risky-3 89%") — **see §3b for why this is 0/7 exposed today, not 0 exposed forever** |
| `backtest/autoresearch/v14e_chartstop_research.py` | BOTH conventions present in one file: et-v2 parse (lines 124-126) and a separate bare `.tz_localize(None)` OPRA strip (line 183), no `et_frame` import. | Chart-stop research (not currently ratified) |
| `backtest/autoresearch/_event_iv_crush_debias.py`, `_pivot_spreadify_vix_regime.py` | Bare `.tz_localize(None)` OPRA strip, reachable from the pivot family's et-v2 SPY helpers (confirmed via `git grep _pivot_premium_selling`). | IV-crush / VIX-regime spreadify variants (research-only) |

### 2c. Verified SAFE-despite-appearances (worth naming — proof that "verify the call" mattered)

`backtest/tools/edge_matrix_bear_level_rejection.py` trips a naive pattern scan (both an
et-v2 signature AND a bare tz-strip appear in the file) but is **not actually mixed**: a
single `_true_et()` helper (lines 124-126, `utc=True` → `tz_convert` → `tz_localize(None)`)
is applied **consistently to both** the SPY frame (line 157) and the OPRA frame (line 284).
Confirmed by reading both call sites, not by the pattern match. `backtest/tools/
fleet_arm_replay.py` (tonight's trigger) is genuinely SAFE: SPY parsed wall-v1 explicitly
(`efr.naive_dt`), OPRA left unstripped from `load_contract_bars` and handed to
`walk_exit_manager`, which then bare-strips it to wall-v1 too — both sides land on wall-v1,
internally consistent (RED-proofed by its own `test_fleet_arm_replay.py`, 20/20 green).
`backtest/autoresearch/daily_book_synthesis.py` delegates its actual OPRA join to
`simulator_real.simulate_trade_real` (SAFE, §2a) — its own bare tz-strip is on unrelated
data, not the join.

### 2d. Pattern-flagged, NOT individually traced tonight (one-offs — reclassify if re-cited)

A repo-wide scan (same detection logic as the shipped guard, §4) for "parses one timestamp
column et-v2 AND bare-strips a `timestamp_et` column, no `et_frame` import, in the same file"
flags 18 files total. Two are already accounted for above (`bold_fullhist_replay.py`
confirmed-affected; `edge_matrix_bear_level_rejection.py` confirmed-safe false-positive). The
remaining 16 are **UNCLEAR** — the pattern is present but entry-time provenance was not
hand-traced tonight, consistent with the 2026-07-02 audit's own precedent for one-off dated
research tools ("reclassify only if re-cited"):

```
backtest/autoresearch/_iv_skew_confirmer.py
backtest/autoresearch/bull_ribbon_reversal_real_fills.py
backtest/autoresearch/eod_deep/missed_setups_scanner.py
backtest/autoresearch/eod_deep/modules/edge.py
backtest/autoresearch/infinite_ammo_discovery.py
backtest/autoresearch/ribbon_rejection_spread_battery.py
backtest/autoresearch/rrw_bull_veto_study.py
backtest/autoresearch/shotgun_scalper_grinder.py  (KILLED strategy -- low stakes regardless)
backtest/autoresearch/trade_5_13_variants.py
backtest/tests/test_bold_fullhist_replay.py  (exercises the same anchor pattern -- see §3b)
backtest/tools/debit_spread_ab_study.py
backtest/tools/edge_matrix_bull_level_reclaim_quality.py
backtest/tools/edge_matrix_sr_flip_retest.py
backtest/tools/elite_bull_postfix_requal_2026_07_31.py
backtest/tools/kitchen_trend_day_continuation.py
backtest/tools/pullback_hold_bull_replay.py
```

Additionally, ~63 of the 87 files that touch `option_pricing_real` only call
`load_contract_bars`/`option_symbol` and hand the result to `simulate_trade_real` (SAFE,
§2a) rather than joining raw timestamps themselves — spot-checked, not individually verified
for all 63. None of these back a currently-armed live knob (verified: `params.json` /
`aggressive/params.json` values were not touched by, and do not cite, any of the files in
this section).

**Caveat on the scan's blind spot:** it only catches SAME-FILE mixing. The two consumer
chains actually confirmed in §2b (`_pivot_premium_selling` family, `bold_fullhist_replay.py`)
involve CROSS-file mixing (et-v2 parse in one file, bare-strip in a shared library it calls)
— the scan would not have found either on its own; both were found by hand-tracing call
chains. Treat the pattern-flag list as a lower bound on same-file risk, not a substitute for
tracing shared-function callers.

---

## 3. Quantified delta

### 3a. PIVOT-PREMIUM-SELLING-SCORECARD.md — LEAD IC cell (material, non-decision-flipping)

Re-ran the scorecard's own LEAD cell (`IC / 10:30 ET / short_offset=2 / wing=2 / pt_frac=0.50
/ stop_mult=1.5×`) over the **exact same population** the scorecard used
(2025-01-02..2026-06-18, 365-day intersection, verified identical count), via the scorecard's
own `run_variant`/`score_variant` functions — changing ONLY `simulator_credit._load_leg_df`'s
OPRA parse (monkeypatched to `et_frame.parse_timestamp_et(..., FRAME_ET_V2)`, matching
`_spot_and_decision`'s et-v2 SPY frame; nothing else touched):

| metric | BASELINE (published, as-shipped) | FIXED (frame-consistent) | delta |
|---|--:|--:|--:|
| OOS-2026 expectancy/tr | **+$23.03** | **+$15.30** | **−$7.73 (−33.6%)** |
| full-sample expectancy/tr | +$16.86 | +$12.54 | −$4.32 (−25.6%) |
| n (taken trades) | 164 | 163 | — |
| trades with a materially different P&L | — | — | **60 / 163 (37%)**, all in EST months (Jan–Feb 2025 sampled) |
| gate_pass (all 7 deterministic gates) | **True** | **True** | **unchanged** |

**The published number is soft — the decision is not.** The scorecard's own final verdict was
already "LEAD, not EDGE — fails gate 6 (beats-random-strike-null), NOT shippable" (real
expectancy sitting at the ~76th percentile of a random-strike null, needing to beat the ~95th
percentile). A LOWER true expectancy (+$15.30 vs the published +$23.03) sits at an even lower
percentile of that same null distribution — **further from beating it, not closer**. The DST
bug was making this dead-on-arrival structure look BETTER than it truly is, not worse, and it
was already correctly killed. No live knob was ever set from this artifact (`params*.json`
untouched, confirmed by the scorecard's own text: "Nothing was flipped live"). This is exactly
the "material delta, unchanged verdict" case the task anticipated — reported plainly, no
crisis manufactured, but the scorecard's headline OOS number needs a correction footnote
(actioned in DATA-PROVENANCE.md, §6).

### 3b. bold_fullhist_replay.py anchor validation (live mechanism, currently ZERO exposure)

`ANCHOR_FILLS` (the 7 real-broker-fill trades `run_anchor_validation` replays to compute
Bold's real-fills pass-rate) are dated **2026-06-26 through 2026-07-28 — all 7 are EDT/summer
dates. 0 of 7 are winter.** The mixed-frame mechanism is confirmed live in this exact code
path (§2b), but with the CURRENT anchor population it produces **zero numeric corruption
today** — the quoted 83%/85%/89% pass-rates in `fleet_arm_replay.py`'s commit message are not
currently wrong because of this bug. This is a decisive, reassuring answer for TODAY, with an
explicit expiration: the first winter real fill added to `ANCHOR_FILLS` (this account is
~5 weeks old; winter exposure is a matter of when, not if) will silently corrupt its own
anchor-validation entry unless `walk_exit_manager` or `option_pricing_real.load_contract_bars`
is fixed first. Flagged forward, not chased further tonight (guard test docstring references
this explicitly so a future session re-checks `ANCHOR_FILLS` dates before trusting the pass
rate).

---

## 4. Guardrail shipped

`backtest/tests/test_graduated_guards.py` — 3 new tests (all green; full suite `85 passed, 1
skipped` after the addition, `-m "not slow"`; the 2 pre-existing `test_et_frame_guards.py`
files unaffected, `8 passed`):

1. **`test_dst_frame_naive_mixed_join_diverges_on_winter_canary`** — structural, data-driven
   (not a naming-convention check): runs the ACTUAL shared loader
   (`option_pricing_real.load_contract_bars`) on the real winter fixture used throughout this
   doc, constructs the buggy pick and the et_frame-consistent pick, and asserts they land on
   DIFFERENT bars with the expected ~60-minute magnitude (mapped through the frame-invariant
   raw timestamp, not the trap of comparing two same-looking display labels — see the bug I
   hit and fixed mid-session, quoted in the test's own comment).
2. **`test_dst_frame_consistent_join_agrees_on_summer_control`** — same mechanism on a summer
   contract; asserts the two paths agree bar-for-bar, proving the divergence above is
   DST-specific, not a general harness bug.
3. **`test_dst_frame_no_new_unguarded_opra_join_consumers`** — the actual stop-a-4th-occurrence
   guard. Repo-wide scan for the same-file smoking-gun pattern (§2d's method) against a fixed,
   per-file-commented allowlist. Any NEW file tripping the pattern that is not on the
   allowlist fails CI, forcing a conscious fix-or-justify decision.

**RED-proofed, both non-trivially:**
- Guard 3: temporarily removed `edge_matrix_bear_level_rejection.py` from the allowlist,
  reran — failed with that exact filename in the assertion diff, restored, reran green.
- Guard 1: manually confirmed that forcing the "correct" path to ALSO use wall-v1 (i.e.
  simulating the 2026-07-02 fix never having shipped) collapses the divergence to zero —
  proving the assertion is sensitive to the actual frame parameter, not vacuously true.

**Why a repo-scan allowlist and not a loader fix:** the correct single fix point is
`option_pricing_real.load_contract_bars()` returning an already frame-normalized series (or
`exit_manager_walk.walk_exit_manager` gaining a `frame:` parameter mirroring
`simulator_real.py`'s pattern) — either would close the gap for every listed caller in §2a/§2b
at once, per the task's own preference for fixing a shared loader once over patching N call
sites. **Both files are out of scope tonight**: `option_pricing_real.py` is explicitly banned
(a concurrent lane owns the 5-min-resolution question there — `backtest/tools/
option_bar_resolution_bias_2026_08_02.py` is that lane's artifact, confirmed present tonight),
and `exit_manager_walk.py` carries a live docstring (dated 2026-08-02, referencing
`OPTION-BAR-RESOLUTION-BIAS-2026-08-02` by name) showing the same concurrent lane is actively
editing this exact function's `opt_df` handling. Touching either tonight risks clobbering that
lane's work. The guard tests exercise both files as read-only black boxes — nothing in them
was edited.

---

## 5. Follow-up (pre-registered, not done tonight)

1. **The real fix**, once the concurrent option-bar-resolution lane lands: give
   `option_pricing_real.load_contract_bars()` a `frame:` parameter (default `wall-v1`, no
   silent swap, mirroring `et_frame.py`'s own migration discipline) OR make it return an
   already-normalized series and thread `frame:` through `exit_manager_walk.walk_exit_manager`,
   `simulator_credit.py`, `simulator_debit.py` the same way `simulator_real.py` already does.
   That single change closes §2a's keystone gap for every caller in §2b/§2d at once.
2. **Re-check `bold_fullhist_replay.ANCHOR_FILLS`** the first time a winter (Nov–Mar) real
   fill is added — the pass-rate computation will silently corrupt that entry until fix #1
   ships.
3. **Trace the 16 UNCLEAR files in §2d individually** if any is ever re-cited toward a
   ratification decision (matching the 2026-07-02 audit's own standing rule for one-offs).
4. **Footnote PIVOT-PREMIUM-SELLING-SCORECARD.md's LEAD-cell OOS number** with the corrected
   +$15.30/tr figure (actioned below in DATA-PROVENANCE.md; the scorecard file itself is left
   as the historical record of what was measured at the time, per this repo's "wall-frame
   scorecard stays citable for wall-frame comparisons" convention from the 2026-07-02 audit).

---

## Commits

- `151123a2` — `fleet_arm_replay.py` (the trigger: found + self-fixed the bug within its own
  scope tonight, before this audit began).
- Guard + doc commits: see `git log` for this lane's commits following this artifact
  (`backtest/tests/test_graduated_guards.py`, this file, `markdown/infra/DATA-PROVENANCE.md`,
  `backtest/_lesson-inbox/2026-08-02-dst-frame-recurrence.md`,
  `automation/overnight/STATUS.md`).

# VERIFY (CODE-PATH lens) — fleet-gates-designation-accuracy.md (G4)

Stamp: 2026-09-03, ~14:30-15:10 ET (market hours), read-only, zero writes to any tracked
state. Re-traces every load-bearing code path and ledger claim from source; does not
re-litigate `veto-scope-safe-3.md` or `fleet-gates-ledger-binding-check.md` beyond what's
needed to check this report's own quotes of them.

## Verdict: SUPPORTED, with 3 numerical/citation errors in supporting text (none load-bearing)

The mechanism claim, the "no go-live instrument reads gate identity" claim, the live
day-count status, and — most importantly — the brand-new §4c day-level leak-dependency
finding (133 ticks / 12 dates / 0-of-12 leak-only) all reproduce EXACTLY from source. Three
supporting numbers in the report are wrong (quoted below); none of them are inputs to the
report's headline conclusions.

---

## 1. Code-path re-trace — CONFIRMED, quotes match exactly

**`fleet_executor.plan_all`** (`automation/state/fleet/fleet_executor.py:933`, function starts
line 909): confirmed `if signal.get("strategies") is not None: plans = _plan_from_strategies(...)`
else falls back to `_perception_for_arm`. Live signal file
`automation/state/fleet/shared-signal.json` on disk right now carries a top-level `"strategies"`
key that is a list (currently empty, but present and not None) — `d.get("strategies") is not None`
== True, confirming the branch fires on the live signal.

**`_plan_from_strategies`** (line 720): confirmed it iterates `signal.get("strategies") or []`,
builds `blk` via `_gate_block_for_entry(entry)` (synthesized from the strategies-list entry's own
`triggers`/`quality` fields), and calls `_gate_check(arm, blk, signal)` — it never calls
`_perception_for_arm` and never reads `signal["safe"]`/`signal["bold"]`. Matches the report
exactly.

**`_gate_check`** (line 599): confirmed it reads only `arm.get("gate_override")`
(`min_triggers`, `require_confluence_or_sequence`, `min_setup_quality`) against the
strategies-entry's own `triggers`/quality — no reference to `structure_veto_enabled`,
`block_bull_1100_1200`, or any other `GATE_KEYS` name.

**`build_shared_signal.py`**: `EMIT_STRATEGIES = True` at line 293, confirmed verbatim.
`do_strats` block (line 812-820): confirmed `s_bear, s_bull = bear, bull` (top-level,
production-faithful — i.e. safe's own block) as the DEFAULT, overridden to
`bold.get("bear")/bold.get("bull")` only `if (bold.get("bear") or {}).get("passed") or
(bold.get("bull") or {}).get("passed")`. Exactly the "defaults to safe's block, swaps to bold's
whenever bold independently passed" mechanism the report describes.

**`heartbeat_core.py` GATE_KEYS** (line 184-199): read (not edited, per constraint) — confirmed
the exact list quoted in this task's own preamble (`block_level_rejection`,
`trendline_requires_ribbon_flip`, `block_elite_bull`, `block_elite_bull_vix_low/high`,
`block_bull_ribbon_flip`, `block_bull_1100_1200`, `block_bull_morning_agg`,
`require_bearish_fill_bar`, `min_ribbon_momentum_cents`, `max_ribbon_duration_bars`,
`midday_trendline_gate`, `block_conf_lvl_rej_midday_afternoon`, `block_conf_lvl_rec_afternoon`,
`entry_bar_body_pct_min(_bull)`, `vix_bear_hard_cap`, `structure_veto_enabled`,
`structure_shift_confirmation_enabled`). This list is consumed only inside `heartbeat_core.py`
(`gate_params = {k: account_params[k] for k in GATE_KEYS if k in account_params}`, line 985) —
i.e. it shapes the CORE safe/bold rows in `core-decisions.jsonl`, a structurally different
mechanism from fleet_executor's `_gate_check`/`gate_override`. This is the concrete basis for
"safe's cohort gates don't independently bind safe-3" — confirmed by code, not just by
inference.

**git provenance**: `git log -S'EMIT_STRATEGIES = True'` and
`git log -S'signal.get("strategies") is not None'` both land on commit `667217a`, confirmed
`2026-06-26` via `git show --stat`. safe-3's minimum `date_et` across all 179 of its
`fills-ledger.jsonl` rows is `2026-06-29` — 3 days after that commit. Matches exactly.

## 2. Ledger rows — CONFIRMED, exact counts and exact rows

`automation/state/fleet/safe-3/decisions.jsonl` (12,602 rows total, independently counted):
`reason == "gate: requires confluence/sequence"` → **284**; `reason == "gate: 1 triggers < 2"` →
**218**; sum **502**. Exact match to the report.

All 3 quoted example rows (`core_tick_id` 2026-09-03T10:24:02.595671, 10:30:03.934929,
13:55:02.903251) exist verbatim with the claimed action/side/setup_name/reason. Note: earlier
(pre-schema-change, e.g. 2026-06-26 rows) `decisions.jsonl` rows carry no `core_tick_id` field
at all (only a null `tick_id`) — the field was added later in the arm's history. The three
quoted rows are all from the current schema and check out.

The live example tick this task's preamble names (`2026-09-03T11:21:02`,
safe=SKIP_STRUCTURE_VETO, bold=ENTER_BULL) independently re-pulled from
`core-decisions.jsonl`: `safe` row has `action=SKIP_STRUCTURE_VETO, verdict=SKIP_STRUCTURE_VETO`;
`bold` row has `action=SKIP_MIN_PREMIUM_FLOOR, verdict=ENTER_BULL` — same
`core_tick_id=2026-09-03T11:21:02.576928`. This is the exact case that makes "action" (not
"verdict") the correct join key for the GATED side, and "verdict" (not "action") the correct
key for the PASSED side — see §4 below, this distinction is where my own first-pass
reproduction initially diverged from the report before I corrected it.

## 3. The four go-live/fidelity instruments — CONFIRMED, no gate-identity assumption in any

- `go_live_gate.py` — `profile_summary` appears exactly once in the whole file, line 826,
  inside `result["designation"]` — a pure display pass-through (`cfg.get("profile_summary")`).
  Read the surrounding `prod_shadow_criterion()` end-to-end (lines 765-867): `pass`/`status` are
  computed solely from `days_scored`, `min_days`, and `statistical_criterion()` on
  ledger-derived `window_rows` — zero reference to `profile_summary` in that computation.
  Confirmed exactly as claimed: display-only, never load-bearing.
- `prod_shadow.py` — `DEFAULT_BASE_ARM = "safe-2"` (line 110), `not_criterion_5: True` /
  `see_instead` keys present (lines 410-411) exactly as quoted. Zero `safe-3`/`safe_3`
  references anywhere in the file (grep confirms).
- `first_live_day_review.py` — zero matches for gate-identity terms (structure_veto,
  min_triggers, profile_summary, cohort). The one "gate" usage found is
  `open_gate_blocking_items` / "Never gates the overall verdict -- textual signal only" — the
  textual-queue-item sense the report describes, not an entry-filter sense.
- `live_readiness.py` — zero matches for gate-identity terms or `safe-3`. Confirmed the file's
  own self-description: "THIS IS A REPORTING INSTRUMENT ONLY. It arms nothing, changes no gate,
  edits no [state]."
- `backtest/tools/walker_full_population_anchor.py` (report's path was
  `setup/scripts/walker_full_population_anchor.py`, which does not exist — the real path is
  under `backtest/tools/`; a locator error, not a content error) — confirmed it filters by
  `arm in POPULATION_ARMS` (= `wen.ACTIVE_ARMS`, the same 4-arm set go_live_gate.py scores) with
  zero matches for structure_veto/profile_summary/min_triggers/cohort.

## 4. §4a/§4b — live status and calendar math — CONFIRMED exactly, ONE discrepancy found

Ran `go_live_gate.prod_shadow_criterion(go_live_gate.load_ledger_rows())` directly (pure read
— `load_ledger_rows()` only calls `TRADES_ENRICHED.read_text()`, no
`refresh_trades_enriched()`, zero writes verified by inspecting the function body before
calling it):

```
status: INSUFFICIENT_DAYS
days_scored: 1
days_needed: 20
note: 1/20 scored trading days for arm 'safe-3' in 2026-09-01..2026-10-30. ...
```

Exact match. `trades-enriched.jsonl`'s max date overall is `2026-09-02`; safe-3's last scored
date in it is `2026-09-02`; `2026-09-01` carries zero safe-3 rows in `fills-ledger.jsonl`
(confirmed); `2026-09-03` is not yet in `trades-enriched.jsonl` (confirmed, consistent with
`market_hours=True` at time of this check, 14:33 ET). Calendar math independently recomputed
(Python `datetime`, Labor Day 2026-09-07 excluded): 43 total trading days 09-01..10-30, 3
elapsed, 19 pre-hypothetical-fix (09-01..09-28), 24 post-fix (09-29..10-30) — all four numbers
match the report's table exactly. 26/44 = 59% baseline: independently counted 26 distinct
`date_et` values with a safe-3 fill in `fills-ledger.jsonl` over 2026-06-29..2026-08-28 —
matches (did not independently re-verify the "44" denominator).

**Discrepancy found (minor, not load-bearing):** the report states "Today, 2026-09-03, already
carries **8** real safe-3 fills across 4 round trips." Direct count from
`fills-ledger.jsonl` for `arm=="safe-3", date_et=="2026-09-03"` returns **10** rows (4 buys,
6 sells — two of the four round trips have a split TP1+runner exit, each counted as a separate
fill leg), spanning 09:42:06-11:34:07 ET — the same window the report names, and still 4 round
trips as claimed, but the fill-leg count is off by 2. This has no effect on any downstream
conclusion (the day still isn't in `trades-enriched.jsonl` yet either way), but it is stated
in a "verified, not estimated" section and the exact number is wrong.

## 5. §4c — the day-level leak-dependency check — INDEPENDENTLY REPRODUCED, exact match, after correcting my own first-pass error

This is the report's one genuinely new empirical claim this session, so I rebuilt it from
scratch rather than trusting the prose. Script: `backtest/tools/fleetgates_verify_g4.py`
(new file, read-only, <5s runtime).

**First pass (my error, not the report's):** joining `core-decisions.jsonl` `safe`/`bold` rows
on `core_tick_id` using the **`verdict`** field on BOTH sides for the "safe gated" test
(`verdict startswith SKIP`) yielded only **116 leak-eligible ticks / 11 distinct dates** — short
of the report's 133/12, and specifically missing 2026-08-20 entirely (on 08-20, safe's
`verdict` is never `SKIP_*` for any tick — only `HOLD`/`ENTER_BEAR`).

**Root cause of my discrepancy, found and fixed:** `verdict` and `action` diverge on 943 of
16,030 core-decisions rows since 2026-08-06 (checked directly) — e.g. a row can carry
`verdict:ENTER_BULL` but `action:SKIP_MIN_PREMIUM_FLOOR` (a later execution-time filter overrides
the score-time verdict). The sibling `fleet-gates-ledger-binding-check.md` documents the correct
method explicitly (its own "Method" section, quoted): **"Gated" = that account's `action` field
starts with `SKIP_`; "read ENTER_BULL/ENTER_BEAR" = the OTHER account's `verdict` field.**
Re-running with `safe.action startswith SKIP` AND `bold.verdict startswith ENTER`:

```
leak-eligible ticks: 133
distinct leak dates: 12
dates: 2026-08-07, 08-11, 08-12, 08-13, 08-17, 08-18, 08-19, 08-20, 08-21, 08-27, 09-02, 09-03
```

Per-date safe-3 ENTER-type (`ENTER_BULL`/`ENTER_BEAR`/`PLACED`) breakdown reproduces the report's
§4c table **exactly, row for row** (08-07: 3/1/2, 08-12: 4/0/4, 08-13: 3/1/2, 08-19: 3/1/2,
08-21: 4/3/1, 08-27: 2/1/1, 09-02: 4/2/2, 09-03: 4/2/2; 08-11/08-17/08-18/08-20: 0/0/0).

**Dates where safe-3's only entry that day came via a leak tick: 0 of 12** — exact match to the
report's central §4c finding.

This exact figure (133 ticks, 12 dates, `leak_eligible_dates` list, `only_leak_dates: []`) is
also independently present in `analysis/deep-research/2026-09-03-money/
verify-fleet-gates-designation-accuracy-1.json` — a second, separately-run verification this
session that used the correct method from the start and landed on the identical numbers. Three
independent computations (the report's own, that prior verifier's, and mine after fixing my
methodology) now agree exactly. This is the strongest possible confirmation available for a
finding whose caveat already correctly says "not a proof" — n=12, proxy metric, bounded window —
those caveats are accurate as stated.

**One numeric error found in the surrounding caveat text:** the report states "the sample is
bounded to the **34** trading days since 2026-08-06." Independently counted: 2026-08-06 through
2026-09-03 inclusive is **21** trading days (weekday count, Python `datetime`; also
cross-checked as 21 distinct dates actually present in `core-decisions.jsonl` over that span).
34 is wrong; should be 21. Does not change the 133/12/0-of-12 figures themselves, only the
denominator description of how bounded the sample is (21 is smaller than 34, so if anything the
true sample is MORE bounded / narrower than the report states — a conservative-direction error,
not one that inflates confidence).

## 6. One mis-citation found (not a factual error about the mechanism)

The report's §1c states: "CLAUDE.md's own doctrine (Account context section) states arms
'differ ONLY by sizing, gates, and stop.'" Grepped the live `CLAUDE.md` for this exact phrase
(`differ ONLY by sizing`, `ONLY by sizing`, `differ only`) — **zero matches**, anywhere in the
file. Read the full "Account context" section verbatim (lines 51-64) — it covers account
numbers, equity, live-threshold, kill-switches, MCP wiring; it does not contain this sentence.
The underlying doctrine is real and documented — it appears in the user's private
`~/.claude/projects/.../MEMORY.md` ("Arms are RISK profiles, not strategies... differ ONLY by
sizing/gates/stop") and is restated in this very task's own "ESTABLISHED THIS SESSION" preamble
— but attributing it to "CLAUDE.md's own doctrine (Account context section)" specifically is
incorrect; that phrase is not in CLAUDE.md. This does not weaken the §1c argument itself (a
reader could reasonably form the same expectation from the arm's own name/cell/note fields in
`accounts.json`, which ARE quoted correctly), but the citation as given would fail a
direct fact-check if someone tried to find the quoted sentence in CLAUDE.md.

## What I did not re-verify

Did not re-derive the "44" denominator behind the 26/44=59% baseline, did not re-check the
bold-2 47% figure cited from the designation file, and did not re-audit
`fleet-gates-ledger-binding-check.md`'s own Table A/B percentages beyond using its documented
method to reproduce the 133/12 headline figures (which matched). Did not test whether
`2026-09-03` becomes the window's 2nd scored day at EOD — that remains correctly labeled
UNVERIFIED/pending in the source report.

## Bottom line for the parent's SUPPORTED verdict

Every load-bearing claim (branch-selection code path, gate-application code path, the
602-refusal/3-row ledger proof, the commit-dating provenance, the 4-instrument
non-assumption survey, the live INSUFFICIENT_DAYS/1/20 status, the 43-day calendar math, and —
critically — the brand-new 133-tick/12-date/0-of-12 day-level leak-dependency finding)
reproduces exactly from source. Three numbers in the supporting narrative are wrong (a fill-leg
count off by 2, a trading-day count off by 13, and one doctrine-sentence mis-attributed to the
wrong file) — none of them inputs to the verdict, the headline, or the go-live-instrument
survey. Recommend the parent doc get those three corrected before being treated as a final
citable artifact, but the SUPPORTED verdict itself stands on evidence I independently
re-derived from source, not on trust of the report's prose.

# Stale documentation + dead code inventory — 2026-08-11

> Read-only audit. No files deleted, moved, or edited except this one. Routed through `MAP.md`
> first per doctrine. Every claim below was grep-verified this session — paths and line numbers
> are exact quotes, not paraphrase. Where a claim could not be fully verified, it is labeled
> UNCLEAR rather than asserted.
>
> **Context that changed the shape of this audit:** this folder (`analysis/deep-research/2026-08-11-audit/`)
> already contained `PIPELINE-AUDIT.md`, `TWO-WEEK-ENGINE-RETRO.md`, and `HARNESS-CALIBRATION.md`
> — written earlier today by a prior session, and they already contain the two retractions this
> audit was asked to hunt (the $6,454 ladder claim, the $384 harness claim). Section 2 builds on
> those docs rather than re-deriving them, and found one propagation gap *between* them (see 2.2).

---

## 1. Stale analysis artifacts

### 1.1 `analysis/deep-research/` — files older than 2026-07-25

Eight files predate the cutoff (everything else in the directory is 2026-07-28 or later).

| File | mtime | In `INDEX.md`? | External references (grep-verified) | Disposition |
|---|---|---|---|---|
| `2026-07-11-strike-tier-reconciliation.md` | 2026-07-11 | Yes | **`CLAUDE.md`** strategy section: *"reconciliation: `analysis/deep-research/2026-07-11-strike-tier-reconciliation.md`"* — still load-bearing today | **KEEP** — actively cited doctrine |
| `2026-07-11-participation-cost.md` | 2026-07-11 | Yes | `analysis/INDEX.md`, `automation/overnight/queue.md` (live), `automation/overnight/STATUS-archive-2026-07.md`, `analysis/daily-brief/2026-07-13-FULL-AUDIT.md` | KEEP — indexed + live-referenced, no supersession found |
| `2026-07-11-ledger-forensics.md` | 2026-07-11 | Yes | same set as above | KEEP |
| `2026-07-11-dormant-assets.md` | 2026-07-11 | Yes | same set as above | KEEP |
| `2026-07-11-friction-budget.md` | 2026-07-11 | Yes | same set as above | KEEP |
| `2026-07-14-premarket-reliability.md` | 2026-07-14 | Yes | same set as above | KEEP |
| `2026-07-14-trendline-break-exhibit.md` | 2026-07-14 | Yes | same set as above | KEEP |
| `2026-07-14-vix-deadzone-map.md` | 2026-07-14 | Yes | same set as above | KEEP |

**Finding: none of the 8 qualify as stale.** All are indexed AND carry at least one external
reference outside the auto-generated `INDEX.md` (which trivially lists every file in the
directory, so it alone is a weak signal — the `analysis/INDEX.md` + live `queue.md` hits are the
real evidence). No same-topic superseding doc was found for any of the four 2026-07-11 "find the
money" one-offs or the three 2026-07-14 ones.

### 1.2 `analysis/recommendations/` — 833 files, ~700+ older than 2026-07-25

**This directory is not a documentation corpus and the OP-22 fold-into-living-docs framing does
not apply to it as designed.** `analysis/recommendations/README.md` (exists, read in full)
states explicitly:

> "This is **not** a place to write narrative analysis. Findings go in
> `analysis/backtests/{label}_findings.md`." / "This directory will accumulate one `R-NNNN.json`
> per ratified or declined recommendation."

Its real index is `analysis/recommendations-log.jsonl` (lifecycle ledger) +
`analysis/backtests/REGISTRY.jsonl` (content-addressed run registry) — not a wikilinked
`INDEX.md` (none exists, confirmed via Glob). The doctrine's own correction mechanism for this
folder is a **standing disclosure banner**, not per-file rewrites — see the
`OPTION-BAR-RESOLUTION-BIAS` banner already inside `README.md` lines 46–60, which retroactively
flags every pre-2026-08-02 scorecard's timing numbers without touching any of them. This is the
same pattern Section 2 found working correctly on `giveback-ratchet-population-2026-08-10.md`.

**Disposition: KEEP-AS-LEDGER for the corpus** — apparent "duplicates" like the `v15.json` →
`v15-final.json` → `v15.3.json` chain or the `contender-rank-2026-06-25.json` … `-07-01.json`
daily series are the intended historical record of an evidence ledger, not redundant docs to fold.

**Observation, not a finding (flagging for the disposition owner, not asserting a defect):**
CLAUDE.md OP-22 states *"every append-only producer has a retention cap; hitting it triggers
CONSOLIDATION (prune/dedupe/archive)."* No retention cap or consolidation event was found for
this directory in 3 months / 833 files. Whether that's a gap or an intentional exemption
(evidence ledgers arguably should never be pruned) is a doctrine call, not something this
read-only pass can resolve.

---

## 2. Retracted/superseded claims still uncorrected

### 2.1 The two named claims — already corrected, verified in place

| Claim | Where corrected | Verified text |
|---|---|---|
| Ladder = +$6,454 | `analysis/recommendations/giveback-ratchet-population-2026-08-10.md` lines 1–19 | `# ⛔ VERDICT RETRACTED 2026-08-11 — read this first` banner sits **above** the preserved original table; explains the harness broke on first-exit, discarding 74 runner legs |
| Ladder = +$6,454 | `analysis/deep-research/2026-08-11-audit/PIPELINE-AUDIT.md:83`, `TWO-WEEK-ENGINE-RETRO.md:36` | Both list it `❌ RETRACTED` |
| Ladder = +$6,454 | `analysis/eod-deep/eod-deep-2026-08-11.md:81` | `Ladder verdict (08-10) | RETRACTED — the +$6,454 came from a first-exit harness that discarded 74 runner legs` |
| Harness "+$384, near-perfect" | `analysis/deep-research/2026-08-11-audit/TWO-WEEK-ENGINE-RETRO.md:37` | `superseded | ... v5 = extreme fills + 1¢ → −$7.4/pos, 95% sign` |
| Harness "+$384, near-perfect" | `analysis/eod-deep/eod-deep-2026-08-11.md:80` | `Bias +$5,949 → +$384; hold-time bias 87 → 32 positions` (shown as an intermediate stage, not the final number) |

No other file in the repo was found asserting either figure as current/valid. The broad `6454`
and `$384` greps returned 132 raw hits; every one outside the docs above was a **coincidental
digit match** — real per-trade P&L figures ($384.00 realized on specific unrelated days in
`journal/2026-08-03.md`, `analysis/eod-deep/eod-deep-2026-08-0{4,6,7}.md`, `analysis/eod-deep/eod-deep-2026-07-21.md`),
a substring of `$526,454` (marketing quote in `TORI-TRENDLINE-RESEARCH-2026-08-09.md:304`), a
substring of `$3848.61` (`B10-EXIT-AUDIT-SCORECARD.md`), or an unrelated `+$384` delta from the
2026-06-17 time-stop-minutes exit study (`strategy/candidates/2026-06-17-time-stop-minutes-exit-optimization.md:68`,
echoed in the archived `STATUS-archive-2026-07.md:2836`). None need correction.

### 2.2 New finding: `HARNESS-CALIBRATION.md` is stale relative to its own sibling, by about 26 minutes

`analysis/deep-research/2026-08-11-audit/HARNESS-CALIBRATION.md` (mtime 16:44:44) is the
dedicated calibration writeup. Its own table stops at **v4 "+$384 (+$2.11/pos), 90% sign
agreement"**, framed as *"what it says once it can be trusted."* It contains no v5 row.

`TWO-WEEK-ENGINE-RETRO.md` (mtime 17:11:12, ~26 minutes later, same folder) line 37 states the
v4 number was **itself superseded**: *"two errors cancelling: SPY feed ended 07-22 (optimistic)
vs 2¢ slippage (pessimistic). v5 = extreme fills + 1¢ → −$7.4/pos, 95% sign."*

So the file whose entire purpose is "the trustworthy calibration number" now under-states its own
supersession — a reader opening `HARNESS-CALIBRATION.md` alone gets the retracted v4 figure with
no pointer to v5. **CORRECTION-NEEDED:** add a one-line pointer at the top of
`HARNESS-CALIBRATION.md` to `TWO-WEEK-ENGINE-RETRO.md`'s v5 correction (−$7.4/pos), matching the
in-place-banner pattern already used successfully in `giveback-ratchet-population-2026-08-10.md`.

### 2.3 "`ladder_day_replay.py` as authoritative" — no uncorrected instance found

Every doc referencing `ladder_day_replay.py` (`giveback-ratchet-population-2026-08-10.md`, the
three `2026-08-11-audit/` docs, `analysis/deep-research/2026-08-10-live/ladder-replay.html`) is
already correctly framed as disqualified/first-exit-broken. `SHADOW.md`'s frozen-prereg line for
`GIVEBACK-RATCHET-2026-08-10` already reads *"does **not** ship on its own evidence"* — consistent,
not contradicted. `automation/overnight/STATUS.md` and `HOME.md` contain zero mentions of the
ladder claim, the $384 figure, or `ladder_day_replay` (grep-confirmed, no matches) — nothing to
correct there either way.

---

## 3. Dead code candidates

Conservative pass: zero inbound references anywhere in the repo (grepped by exact filename,
whole-tree, including `SCHEDULED-TASKS.md` and all `.ps1` files), not registered as a scheduled
task, last modified before 2026-08-01. Self-mentions in a file's own docstring/usage line do not
count as a reference; a mention from a **different** file does.

### 3.1 `backtest/tools/` — 32 files, verified zero external references

| Cluster | Files | Last modified | Evidence |
|---|---|---|---|
| One same-commit "closing out" cluster (all timestamped identically, reads as an iterative scratch sequence — finalize → finalize_content → final_truth → final_v2/v3 → correct_status → capstone_brief → lock_gate/lock_expanded) | `_capstone_brief.py`, `_correct_status.py`, `_finalize.py`, `_final_status_update.py`, `_finalize_content.py`, `_final_truth.py`, `_final_v2.py`, `_final_v3.py`, `_lock_expanded.py`, `_lock_gate.py` | 2026-06-20 | Only cross-reference found: `_finalize_content.py:1` docstring names `_finalize.py` (its own sibling). No file outside the cluster mentions any of the 10. |
| Kitchen-fleet repair pair (mutual reference, no external consumer) | `_load_kitchen_fleet.py`, `_fix_kitchen_fleet.py` | 2026-05-31 | `_fix_kitchen_fleet.py:3,22` references `_load_kitchen_fleet.py` in comments; nothing outside the pair references either |
| Missed-days research chain | `_aggregate_missed.py`, `_extract_missed_facts.py`, `_jedge_facts.py`, `_truth.py` | 2026-05-31 | Zero hits anywhere, including each other |
| Sniper scratch outputs | `_show_sniper.py`, `_show_sniper2.py` | 2026-05-31 | Zero hits |
| Kitchen queue cleanup one-offs | `_archive_bad_fleet.py`, `_queue_state.py`, `_archive_remaining.py`, `_validate_green_config.py`, `_add_minstop_cook.py`, `_queue_autopsy_cooks.py` | 2026-05-31 | Zero hits |
| Data-prep scratch | `_probe_matrix.py`, `_normalize_data.py`, `_consolidate.py`, `_fmt.py`, `_concentration.py`, `_implement_midday_gate.py` | 2026-05-31 | Zero hits |
| DTE report scratch | `_dte_n_report.py` | 2026-06-21 | Zero hits |
| DTE backfill (self-referencing only) | `_fetch_dte_backfill.py` | 2026-06-21 | Only mentions its own siblings (`_dte_signal_days.py`, `_fetch_1dte_2dte_sample.py`) in its own docstring; nothing external mentions `_fetch_dte_backfill.py` back |
| PC fixture extract | `_pc_fixture_extract.py` | 2026-07-10 | Zero hits |
| VIX proxy fetch | `_fetch_vix_daily_proxy_2024.py` | 2026-07-31 | Zero hits |

**Checked and cleared (NOT dead — kept out of the table above):** `_alpaca_creds.py` (heavily
referenced as the shared credential-resolution pattern across many active tools),
`_probe_opra_floor.py` (referenced by `backtest/tests/test_graduated_guards.py:4101` — a test,
per the conservative rule this alone clears it), `_dte_signal_days.py` (imported pattern-matched
by `backtest/autoresearch/_dte_expansion_sim.py`, an active directory), `_fade_battery_artifact_hunt.py`
(cited as the runner in `analysis/recommendations/trendline-fade-battery.md:48`),
`_pong_prereg_builder.py` / `_pong_finalize_scorecard.py` (both cited in
`analysis/recommendations/pong-resting-limit-2026-07-17.md` / `RESTING-ORDER-EXIT-FEASIBILITY-2026-08-02.md`),
`_backfill_opra_2024_01_18_2024_12_31.py` (cited in `analysis/deep-research/OPRA-BACKFILL-2026-07-31.md`),
`_fetch_1dte_2dte_sample.py` (cited by `_fetch_dte_backfill.py`'s docstring — weak but non-zero),
`_backfill_opra_2026_05_30_06_18.py` (named in `STATUS-archive-2026-06.md:2722`'s build list —
archived-mention only, borderline, left out of the dead list on the conservative side).

### 3.2 `setup/scripts/` — 6 files, verified zero-or-archive-only references

| File | Last modified | Evidence |
|---|---|---|
| `_parse_w8.py` | 2026-05-09 | Zero hits anywhere |
| `_compare_top5.py` | 2026-05-09 | Zero hits anywhere |
| `_fix_key_levels_2026_06_24.py` | 2026-06-24 | Only mention: `automation/overnight/STATUS-archive-2026-08.md:2833`, describing a one-time hand-fix already applied 6+ weeks ago (name itself is date-stamped as a one-off) |
| `_sync_keylevel_entities_2026_06_24.py` | 2026-06-24 | Zero hits (paired same-session one-off with the file above) |
| `_trim_heartbeat_oneoff.py` | 2026-06-25 | Zero hits; name self-declares one-off |
| `_trim_heartbeat_pass2.py` | 2026-06-25 | Zero hits; paired with the file above |

**Checked and cleared (NOT dead):** `_crypto_daily_digest.py` — actively called by
`setup/scripts/run-crypto-daily.ps1:117` (`Invoke-PythonHidden -ScriptPath "setup\scripts\_crypto_daily_digest.py"`).

**Scope note:** `backtest/tools/` has ~380 files and `setup/scripts/` ~250; the vast majority are
one-off research/utility scripts by design (backtest/tools/ especially — the doctrine's own
pattern is "named study script produces output, output gets cited in deep-research/recommendations,
script itself is not meant to be re-run"). The lists above are the underscore-prefixed
"scratch/private" naming convention specifically, cross-checked individually — not an exhaustive
sweep of all ~630 files in both directories. Treat this as a high-confidence starter list, not a
complete one.

---

## 4. Stale state producers

| Producer | Path | mtime found | Status |
|---|---|---|---|
| Pain ledger (named example) | `analysis/pain-ledger/mae-mfe.json`, `.mae-mfe-floor-state.json` | **2026-08-11 (today)** — regenerated twice during this session (last at the equivalent of ~17:16 ET, confirmed via a second mtime check mid-audit) | **NO LONGER STALE.** `TWO-WEEK-ENGINE-RETRO.md:78` (written earlier today) states *"pain-ledger producer stale since 08-01"* — that claim is itself now stale, resolved between when the retro was written and this pass. Confirmed via `git status` showing both files `M` (modified, uncommitted) in the live tree. |
| Pain ledger sibling | `analysis/pain-ledger/latency.json` | 2026-08-11 (today) | Fresh, consistent with the above |
| Pain ledger sibling | `analysis/pain-ledger/sampling-gap.json` | 2026-08-02 — **9 days stale** | Genuinely unrefreshed. UNCLEAR whether this is a stalled nightly producer or a one-time diagnostic (its sibling `PREREG-2026-08-01.md` reads as a frozen one-time spec, which would make a single output correct-as-is). `setup/scripts/sampling_gap_ledger.py` exists and has `backtest/tests/test_sampling_gap_ledger.py`, but no scheduled-task wiring was found for it in `SCHEDULED-TASKS.md`. Flagging for a follow-up check rather than asserting broken. |
| `pain_ledger.py`'s own schedule | — | — | No `Gamma_*` task or `install-pain-ledger.ps1` found. The module is real and tested (`backtest/tests/test_pain_ledger.py`), so not dead code — but its regeneration trigger (which task's fire calls it, or whether it's still only run ad hoc) was not identified in this pass. |
| Free-model audit family | `analysis/free-model-audit/{heartbeat-veto,prospector,swarm-consult,twin-review}/` | last scorecard 2026-08-10 | **Spot-checked and cleared** — `Gamma_FreeModelAudit` self-gates to every-other-day per `SCHEDULED-TASKS.md`, so a 08-10→08-11 gap is expected behavior, not staleness. |

**Scope note:** `git status` shows **1,755 files** modified under `analysis/` +
`automation/state/` in the current working tree alone — this is an extremely active state layer.
An exhaustive sweep of every nightly producer against its own expected cadence was out of scope
for this pass; the rows above are the specifically-verified items (the task's named example, its
immediate siblings, and one cadence-based spot-check for contrast).

---

## 5. Contradicted doctrine

| # | Doc : line | Claim | Contradicting evidence | Disposition |
|---|---|---|---|---|
| 1 | `markdown/specs/EXIT-DISCIPLINE-SPEC.md:149` | *"chart-stop does 92/100 of the binding exits"* — tagged **SHIP (already live)** | `markdown/doctrine/LESSONS-LEARNED.md` **L291** (2026-08-08): *"a chart-stop family claimed 92/100 of binding exits for a different era's population; on the current book it's a dead-frequency knob"* and explicitly: *"`EXIT-DISCIPLINE-SPEC.md`'s 92/100 figure flagged as not citable for today's book."* The flag exists in the lessons doc; **the spec itself was never annotated.** | **CORRECTION-NEEDED** — add a pointer to L291 at line 149. Verified this is the only copy of "92/100" in the repo (single hit for the pattern outside `LESSONS-LEARNED.md`/`CLAUDE.md`'s own citation of it) — no other copies to chase. |
| 2 | `markdown/audits/T-W6-VWAP-TWO-LANE-PROVENANCE-2026-07-08.md:59-79` | Frames `vwap_continuation`'s `-0.06/+0.40` premium stop as *"the LATER of the two validated cells"* and recommends standardizing on it | `analysis/deep-research/2026-08-11-audit/PIPELINE-AUDIT.md` (today, n=126 real fills, reproduced per-arm): tight % stops **including this exact −6%** value lose **−$28.96/trade** vs. wide structure/−50%-cap stops at **+$33.43/trade**; PIPELINE-AUDIT.md itself lists `vwap_continuation −6%` as one of two live paths still carrying a stop shape the new real-money evidence contradicts (§2, §5) | **CORRECTION-NEEDED** (or at minimum a cross-reference) — T-W6's "validated" framing has no pointer to the newer, contradicting finding. Note: −6% is confirmed the current live value via auto-generated `automation/state/engine-contract.md` lines 29/55, so this isn't academic — it's describing today's live config. |
| 3 | "exit-replay harness called trustworthy" (general sweep) | — | No instance found beyond the already-corrected `giveback-ratchet-population-2026-08-10.md` (Section 2). | **NO FINDING** — nothing further to correct here. |

---

## Summary

| Disposition | Count | Where |
|---|---|---|
| KEEP (verified, indexed/referenced, no action) | 8 | `analysis/deep-research/` pre-07-25 files |
| KEEP-AS-LEDGER (structural, by design) | ~700+ files / whole directory | `analysis/recommendations/` |
| CORRECTION-NEEDED | 3 | `HARNESS-CALIBRATION.md` (§2.2), `EXIT-DISCIPLINE-SPEC.md:149` (§5.1), `T-W6-VWAP-TWO-LANE-PROVENANCE-2026-07-08.md` (§5.2) |
| DELETE-CANDIDATE (dead code, zero references) | 38 | 32 in `backtest/tools/` (§3.1) + 6 in `setup/scripts/` (§3.2) |
| ARCHIVE-CANDIDATE (borderline / archive-mention-only) | 3 | `_load_kitchen_fleet.py`+`_fix_kitchen_fleet.py` pair, `_backfill_opra_2026_05_30_06_18.py` |
| RESOLVED-DURING-AUDIT (was stale, self-corrected mid-session) | 1 | `analysis/pain-ledger/mae-mfe.json` + `.mae-mfe-floor-state.json` |
| STILL STALE, cadence unconfirmed | 1 | `analysis/pain-ledger/sampling-gap.json` (9 days, UNCLEAR if one-time-by-design) |
| OP-22 OBSERVATION (not a hard finding) | 1 | `analysis/recommendations/` has no retention cap/consolidation despite OP-22's stated requirement |

Two retracted claims the task named as known-bad ($6,454 ladder, $384 harness) were **already
correctly retracted in-repo before this audit started**, dated the same day — the real find was
the 26-minute propagation gap between the two correction docs themselves (§2.2), plus one doctrine
spec (`EXIT-DISCIPLINE-SPEC.md`) that was flagged as stale once (L291) but never actually
annotated at the source. The pain-ledger staleness the task asked to verify **resolved itself
during this session** — worth noting because it means `TWO-WEEK-ENGINE-RETRO.md`, written only
hours earlier, is already carrying one outdated line.

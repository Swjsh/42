# Lesson candidate: a documented fix that isn't structurally enforced WILL recur

**Date:** 2026-08-02
**Found during:** building `backtest/tools/fleet_arm_replay.py` (commit `151123a2`) — the
tool's own first draft independently re-hit the exact bug the 2026-07-02 incident already
found and fixed, and self-corrected before commit. This inbox item is filed for the
BROADER recurrence discovered while auditing why that was possible at all.
**Canonical audit:** `analysis/deep-research/DST-FRAME-BLAST-RADIUS-2026-08-02.md`
**Prior occurrence:** `backtest/_lesson-inbox/2026-07-02-dst-fixed-offset-wall-frame.md`
(processed into `markdown/audits/DST-FRAME-AUDIT-2026-07-02.md` + `backtest/lib/et_frame.py`
+ `backtest/tests/test_et_frame_guards.py`)

**Symptom:** the 2026-07-02 fix shipped a canonical frame module (`et_frame.py`) and
8 guards pinning both conventions — but the guards only pin `et_frame.py`'s OWN correctness,
not that every consumer actually ROUTES THROUGH it. Tonight's audit found the SHARED OPRA
loader (`option_pricing_real.py::load_contract_bars`) still returns raw, un-normalized,
tz-aware fixed-offset data three-plus weeks after the fix shipped — every one of its 87
downstream callers had to independently remember to reconcile frames, and several didn't:
`simulator_credit.py`/`simulator_debit.py` (no `frame` parameter at all, unconditional bare
tz-strip) and `exit_manager_walk.py::walk_exit_manager` (same gap, and the busiest shared
exit-walk function in the newer "fullhist replay" tool generation — at least 9 call sites).
Two consumer chains were confirmed actually corrupted: the `_pivot_premium_selling.py`
family (feeding `PIVOT-PREMIUM-SELLING-SCORECARD.md`, LEAD-cell OOS expectancy overstated
+$23.03 vs a corrected +$15.30, −33.6%) and `bold_fullhist_replay.py::run_anchor_validation`
(mechanism live, currently 0/7 anchors are winter-dated so no numeric corruption yet — but
will bite the first winter real fill).

**Root cause:** the 2026-07-02 fix was a **library** (`et_frame.py`) plus **opt-in threading**
through the handful of call sites known at the time (`build_rth`, `simulate_trade_real`,
`simulate_trade_real_trailing`). It was never enforced AT THE LOWEST SHARED CHOKEPOINT
(`load_contract_bars` itself), so every NEW tool written since — and there have been dozens,
several dated `_2026_08_0{1,2}` — had to rediscover the convention from scratch, with only a
docstring and a sibling test file to learn it from. A library that requires every caller to
remember to use it correctly is not a fix, it's a well-documented trap. This matches C14's
"dead/translated-but-unapplied knob" family but is subtly different: the knob here (`frame=`)
is neither dead nor mistranslated — it simply was never PROPAGATED to the one place
(`load_contract_bars`) that would have made propagation automatic.

**Fix shape (tonight, partial — see follow-up):** 3 graduated guards added to
`backtest/tests/test_graduated_guards.py`: (1) a data-driven canary proving the divergence
mechanism through the real shared loader, (2) a summer control proving it's DST-specific,
(3) a repo-wide same-file pattern scan with a per-file-commented allowlist that fails CI on
any NEW file introducing the same-file version of the mistake. **NOT done tonight**
(deliberately, scope-fenced): the actual loader fix, because `option_pricing_real.py` is
owned by a concurrent lane tonight (5-min-resolution work) and `exit_manager_walk.py` shares
that exact surface (live docstring proves it). Guard 3 explicitly cannot see cross-file
mixing (the ACTUAL mechanism in both confirmed-affected chains) — it only catches the
same-file copy-paste version of the mistake, which is the more likely shape of a genuine
4th occurrence (a new tool copy-pasting an old tool's naive parse) but is not a complete
architectural fix.

**Generalizable lessons:**
1. **A fix shipped as an opt-in library, not enforced at the shared chokepoint, decays.**
   Three-plus weeks and dozens of new tools later, the shared loader most of them call was
   still emitting the unnormalized convention. If a fix can live in ONE function all callers
   already go through, put it there — don't rely on N call sites remembering to opt in.
2. **A guard suite that only tests the library, not the library's adoption, gives false
   confidence.** `test_et_frame_guards.py`'s 8 tests all still pass today — they were never
   wrong. They just don't (and structurally can't) tell you whether a brand-new tool used
   the library correctly. A second guard tier — "does anything NEW touch this surface
   unsafely" — is a different, necessary check.
3. **"The tool that found the bug already fixed itself" is not the same as "the bug is
   fixed."** fleet_arm_replay.py's own commit message correctly diagnosed and fixed its OWN
   instance — a genuinely good catch — but reading that commit message as "the DST bug is
   handled" would have been exactly the L249 docstring-trust failure this repo has hit
   before. The fix being local to one file, one session, is why this had to become a
   blast-radius audit rather than a one-line note.
4. **Cross-file mixing is harder to catch than same-file mixing, and it's what actually
   happened both confirmed times.** `_pivot_premium_selling.py` parses SPY et-v2 in one
   file and hands the result to `simulator_credit.py` (a different file) which parses OPRA
   wall-v1. Neither file alone looks wrong in isolation — the bug is only visible at the
   CALL BOUNDARY. Any future automated scan for this class of bug needs to trace call
   graphs, not just grep single files.

**Candidate lesson families:** C6 (look-ahead / frame joins — this is the sibling "stale
data" case, not future leakage, but same family), C14 (unapplied knob — but the "chokepoint
never adopted the knob" variant, not "mistranslated"), C7 (silent success — the scorecard's
`gate_pass=True` stayed `True` in both the buggy and corrected runs, so nothing LOOKED
broken; only re-running with the fix applied surfaced the -33.6% delta).

---

## FOLLOW-UP: ROOT FIX LANDED (2026-08-02, same day, follow-up integrity lane)

The deferred fix above shipped this same day, once `option_pricing_real.py` /
`exit_manager_walk.py` came unblocked (the concurrent 5-min-resolution lane finished and
committed — `01640055`/`41ccfeb4`/`f61ec781`). This closes the "opt-in library, not enforced
at the chokepoint" root cause named above, at the chokepoint itself:

- **`option_pricing_real.load_contract_bars`** gained a keyword-only
  `frame: Optional[str] = None` parameter. `None` (default) preserves the exact prior raw
  tz-aware output — zero behavior change for every existing caller — because that raw shape
  is what SAFE callers (`simulator_real.py`) already correctly re-parse themselves;
  `"wall-v1"`/`"et-v2"` return an already-normalized naive column via
  `et_frame.parse_timestamp_et`, giving ANY caller (present or future) a one-call, correct,
  unambiguous path that can no longer silently mis-join.
- **`exit_manager_walk.walk_exit_manager`**, **`simulator_credit.simulate_credit_trade`**,
  **`simulator_debit.simulate_debit_trade`** all gained a `frame: str = "wall-v1"` parameter,
  replacing their prior unconditional bare `.tz_localize(None)` strips. Default reproduces
  every one of their combined 90+ pre-existing call sites byte-for-byte (this is the load-
  bearing claim a future editor must not casually change — see the guard list below).
- **Both confirmed-affected call sites in `bold_fullhist_replay.py`** (`run_anchor_
  validation` + the elite-bull-requal qty5-rescale closure) and **`test_bold_fullhist_
  replay.py`'s own inline anchor test** now explicitly pass `frame="et-v2"` — zero behavior
  change today (every populated date is summer/EDT), closes the gap before a winter date is
  ever added to either population.
- **A SECOND, subtler bug was found and fixed in the same build**, not shipped separately:
  `et_frame.parse_timestamp_et`'s `et-v2` branch does not honor its own documented
  "already-naive input passes through unchanged" contract (only its `wall-v1` branch does)
  — it unconditionally reinterprets already-naive digits as UTC and shifts them by the zone
  offset. This corrupted `walk_exit_manager`'s handling of a `five_min_spy_df` a caller had
  already pre-parsed to naive et-v2 upstream (exactly `bold_fullhist_replay.run_anchor_
  validation`'s shape) — caught LIVE by `test_bold_fullhist_replay.py` failing with a
  wrong-direction replayed P&L on a real anchor the moment `frame="et-v2"` was wired in,
  fixed before being reported done, not after. Fixed LOCALLY (`exit_manager_walk.
  _reframe_series` / `simulator_credit._reframe_series`), deliberately NOT by modifying
  `et_frame.py` itself (out of scope this session — heavily used, heavily guarded by
  `test_et_frame_guards.py`, and changing its documented contract is a bigger, separate,
  riskier change than this fix needed). This is itself a small instance of lesson #2 above
  ("a guard suite that only tests the library... gives false confidence") — `et_frame.py`'s
  own docstring claim was never actually pinned by a guard for the et-v2-branch-on-naive-
  input case, so it silently drifted from true.

**Which guard now prevents recurrence #4:** `test_dst_frame_no_new_unguarded_opra_join_
consumers` (the repo-wide same-file scan, unchanged in mechanism) remains the structural
stop for a NEW same-file copy-paste instance. Six NEW tests
(`test_dst_frame_fix_load_contract_bars_frame_kwarg_winter_canary` /
`_summer_control` / `_frame_none_default_unchanged` / `_rejects_bad_frame_value`,
`test_dst_frame_fix_walk_exit_manager_frame_kwarg_diverges_on_winter` / `_agrees_on_summer`,
`test_dst_frame_fix_reframe_series_passes_through_already_naive_input`) in
`backtest/tests/test_graduated_guards.py` now pin the ROOT FIX itself (not just the bug) —
so a future edit that breaks the actual `frame=` mechanism (not just the bug-reproduction
harness the original 3 guards used) fails loudly. All 3 original guards plus these 6 pass
green (RED-proofed: temporarily reverted `_reframe_series` to its pre-fix shape, confirmed
both the new guard AND `test_bold_fullhist_replay.py`'s two anchor tests failed with the
exact expected wrong-direction P&L, then restored and reconfirmed green).

**16-file sweep (this audit's own §2d "UNCLEAR — reclassify if re-cited" list), traced
individually 2026-08-02:** SAFE (7): `_iv_skew_confirmer.py`, `eod_deep/missed_setups_
scanner.py`, `eod_deep/modules/edge.py`, `debit_spread_ab_study.py`, `edge_matrix_bull_
level_reclaim_quality.py`, `edge_matrix_sr_flip_retest.py`, `kitchen_trend_day_
continuation.py`, `pullback_hold_bull_replay.py`. AFFECTED (8, one newly high-priority):
`bull_ribbon_reversal_real_fills.py`, `infinite_ammo_discovery.py`, `ribbon_rejection_
spread_battery.py`, `rrw_bull_veto_study.py` (zero live exposure — pure research kill, no
params ever touched), `shotgun_scalper_grinder.py` (KILLED strategy), `trade_5_13_
variants.py` (hardcoded summer date, zero exposure), `test_bold_fullhist_replay.py` (was
accurate at sweep-read-time, fixed moments earlier in the same session — verified current
on disk), and **`elite_bull_postfix_requal_2026_07_31.py`** — cited in `FRIDAY-DIAL-IN-
2026-07-31.md` to justify a `block_elite_bull: false` lift trial on bold-2; verified
2026-08-02 that trial was independently armed-then-reverted the SAME session (2026-08-01)
for unrelated reasons (misattributed basis + contrary properly-powered evidence), so there
is no current live exposure, but the file's own join is still genuinely mismatched and
should not be cited again unfixed. Full detail: `markdown/infra/DATA-PROVENANCE.md`'s
winter-frame section.

**Live-knob re-verification (the reason this fix was prioritized tonight):** neither v15.3
CHART-STOP-PRIMARY (`structure_stop_study.py`) nor the ATM-over-OTM-2 strike knob
(`ribbon_ride_strike_exit_ab.py`, incl. ITM-2) actually routes through the affected
`walk_exit_manager`/`load_contract_bars` join path — both run an independent, wall-v1-
consistent walk (`plan_exit_actions` called directly), confirmed by reading every file in
both chains (zero et-v2 markers anywhere) AND empirically (the real `signal-set.json`
population's earliest winter entry is 10:30 ET — the wall-v1 clip signature, not the ~09:30
et-v2 would show). Both knobs: **STILL-CONFIRMED**, unchanged from `OPTION-BAR-RESOLUTION-
BIAS-2026-08-02.md`'s own numbers, because that path was never on the affected surface —
not because a re-run happened to agree.

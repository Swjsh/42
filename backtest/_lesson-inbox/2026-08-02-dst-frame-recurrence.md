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

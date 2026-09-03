# G5 — Design intent: role-blind sourcing of sig['strategies']

_generated 2026-09-03T14:27 ET (`et_clock.py`). Read-only doc-archaeology. Nothing armed, changed, or ordered._
_Companion to `analysis/deep-research/2026-09-03-money/veto-scope-safe-3.md` (this session's own established finding)._

## Headline

**The mechanism is documented as intentional for "genuinely looser" arms (bold-2, risky-1, risky-3). Its application to safe-3 specifically was never separately decided — and safe-3's own carve-out mechanism (`_perception_for_arm`, purpose-built for exactly this) is dead code on the path that matters. The exact symptom this session found (safe SKIP, safe-3 ENTER on bold's verdict) was already proven, named, and partly doc-corrected on 2026-08-13/08-14 — three weeks before this session re-found it under a new investigation name — and one of the two stale comments that caused the confusion is STILL uncorrected in code today.**

---

## 1. What problem did the 08-12 "strategies" commit actually solve?

**FACT.** The 08-12 commit most directly named by the task brief is `e3a44956` ("fix(fleet): move the params disarm to select_plan — my first two placements were wrong", 2026-08-12 22:43:16 -0600), preceded same night by `e816178d` ("fix(fleet): a params DISARM must reach the fleet arms, not just core", 2026-08-12).

Its problem: `vwap_continuation` was disarmed for-cause in `params.json` on 2026-07-25 (commit `e0356fb1`, "0-for-12 live, -$357"). `params.json` governs only the **core** arms (safe-2/bold-2); the fleet arms (safe-3/risky-1/risky-3) never read it. The disarm was supposed to reach the fleet arms via `strategies.fired()`, but `strategies.fired()` is **never called in production** because `build_shared_signal.py` always emits a top-level `"strategies"` key, so `fleet_executor.plan_all` always takes the FIX2 branch (`_plan_from_strategies`) instead of the branch that calls `fired()`. Consequence: the kill "half-landed" — it worked on 2/5 arms and the setup kept trading on the other 3, for **43 fills / −$1,046, ~3x the loss that motivated the original kill** (quoted directly from `e816178d`'s commit message).

The fix: move the disarm check to `select_plan()` (the true order choke point, after planning, before placement) keyed on one new switch, `params.extra_setup_exec_armed`, read by both the core and fleet paths.

**This is NOT the commit that introduced role-blind/peak-sourced `sig['strategies']`.** That mechanism (`EMIT_STRATEGIES`, `_strategies_block`, the FIX2 architecture itself) is older — introduced **2026-06-26** in `667217a1` ("feat(engine): EOD 2026-06-26 — engine repairs..."). The 08-12 fix operated *inside* that pre-existing architecture to close a narrower, unrelated gap (a disarmed strategy still firing on fleet arms), not to create or extend the safe/bold perception-sourcing behavior.

**INFERENCE (labelled):** the task brief's phrasing ("the commit(s) introducing EMIT_STRATEGIES / the FIX2 branch... around 2026-08-11..08-13") conflates two different things that happened to be adjacent in time: (a) FIX2/EMIT_STRATEGIES's actual introduction (06-26, unrelated to 08-12/08-13), and (b) a cluster of 08-12/08-13 fixes and a 36-agent review that all touched the *same* code region for *different* reasons. Treat them as three separate events, not one.

---

## 2. Was "fleet arms use whichever perception passed" ever written down as a decision — or is it an undocumented side effect?

**Both, split by which arms — and this split is the actual finding.**

### 2a. For bold-2 / risky-1 / risky-3 ("genuinely looser" arms): documented, deliberate, J-directed.

- `SCORING_PEAK_LIVE = True` since 2026-06-25 (comment: "flipped 2026-06-25 (J directive): all paper fleet ar[ms]…").
- `build_shared_signal.py:1131` states the intent explicitly: *"a genuinely-looser arm is NOT representable downstream and must be a producer-side lane, exactly like `probe` and `ladder`."* — written against a named J directive (quoted in the same file, 2026-07-31): *"we're paper trading. We have six arms, and we should just be getting in shit and seeing if it works."*
- The `_strategies_block` call site (`build_shared_signal.py` ~line 806-823) carries its own inline rationale: *"When the dual-perception 'bold' block passed a side the top-level (production-faithful) one did not, derive the ribbon entries from the LOOSER perception so the loose arms see the scoring-peak setup."*

This is a real, load-bearing, doctrine-cited design: **FACT**, not inference.

### 2b. For safe-3 specifically: never separately decided — an undocumented side effect of two documented mechanisms colliding.

Three independent pieces of evidence:

1. **A purpose-built carve-out for safe already exists in the code and is dead.** `fleet_executor._perception_for_arm` (line 108) exists *specifically* to route a safe-role arm to `signal['safe']` and a bold-role arm to `signal['bold']`, with its own docstring calling this a **"perception-source confound fix."** But `plan_all` (line 933) only calls `_perception_for_arm` in the `else` branch, taken **only when `signal.get("strategies") is None`** — which in production is never, since `do_strats` defaults to `EMIT_STRATEGIES=True`. So the one mechanism explicitly designed to keep safe-3 bound to safe's own perception never runs. This is the same "INERT" shape as the `strategies.fired()` bug `e816178d` fixed one day earlier — a second instance of the same L287-class lesson ("an imperative fix applied to ONE surface expires the moment a second surface regenerates the same decision independently," quoted from `e816178d`'s own message) — except this second instance was never fixed.

2. **The bug was caught and named on 2026-08-13, by a 36-agent adversarial review, using this session's exact example.** `analysis/deep-research/DEEP-REVIEW-2026-08-13-MULTIAGENT.md` §3, *"The fleet CAN enter where production refuses — the docstring is false"*: *"Proved today: at 11:41–11:43 safe returned `SKIP_BULL_1100_1200` and took nothing; safe-3, risky-1 and risky-3 all entered at 11:42:05 for −$325 = 42% of the day's losses… Consequence: fleet risk is not bounded by production's gate perimeter. Any reasoning that assumes it is, is wrong."* This is the SAME mechanism, same failure mode, same arm (safe-3) named alongside the two loose arms — three weeks before `veto-scope-safe-3.md`'s 2026-09-03 core_tick 11:21:02 example.

3. **The finding was acted on incompletely.** `build_shared_signal.py`'s docstring was corrected 2026-08-14 (dated "STALE-GUARANTEE CORRECTION (2026-08-14; found by the 2026-08-13 deep review)") to state plainly: *"fleet exposure is NOT bounded by production's gate perimeter."* But that correction documents the SYMPTOM, not a DECISION about whether safe-3 belongs in the bypass. No commit, prereg, or doctrine doc anywhere in the repo says "safe-3 is intended to trade off bold's/peak's perception" — the closest thing to a decision is `_perception_for_arm`'s docstring, which says the opposite. The companion stale comment in `fleet_executor.py:790` ("apply UNIFORMLY to every arm") was flagged the SAME day (`ae6e0059`'s commit message: *"That would be the THIRD stale-guarantee comment found today"*) but **was never corrected — it still reads unqualified today, 2026-09-03** (verified by direct read of the current file, this session).

4. `ae6e0059` ("gate x arm matrix") itself shipped with an explicit, honest **scope limit** rather than a resolution: *"I could not resolve a contradiction: fleet_executor.py:789 asserts these shared-signal gates 'apply UNIFORMLY to every arm', but the ledgers disagree… Either that comment is stale or the gate is not applied on the fleet path… Resolving it needs the gate id logged on every SKIP verdict and diffed per arm over a week."* That instrumentation was never built. This session's `veto-scope-safe-3.md` is, functionally, the diffed-per-arm-over-a-week analysis that commit asked for and nobody ran for three weeks.

**Verdict on Q2: undocumented side effect, with a documented-but-abandoned near-miss.** The general mechanism is intentional (2a). Its scope — which arms it's *supposed* to cover — was never decided for safe-3, was flagged as an open contradiction on 08-13, was half-corrected in prose on 08-14, and the remaining stale comment plus the missing per-arm-gate-id instrument mean the contradiction is still live in the code today.

---

## 3. What does the doctrine say should bind a safe-role arm?

**FACT — the standing doctrine, J-directed, repeated across multiple docs (grep hits below):**

> "arms are RISK PROFILES, not strategies… All arms pick from the SAME validated setup menu; they differ only in expression parameters (sizing, gate-strictness, stop/exit shape, DTE, drawdown)."
> — `markdown/audits/FABLE-DECISIONS-2026-07-07.md` D7 (labelled "J's standing (angry, repeated) correction")

Same statement, independently, in:
- `markdown/audits/GATE-PROVENANCE-AUDIT-2026-07-02.md:121` — *"arms are RISK profiles, not strategies. The 2×3 grid already varies `min_triggers`; this extends the gate axis... same strategy menu everywhere, different tolerance."*
- `markdown/planning/WEEKLY-OPTIONS-PROGRAM.md:299` — cites the same standing rule.
- `MAP.md:121-123` — *"The arms — risk profiles, NOT strategies… All arms trade the SAME shared signal. They differ only in sizing, gates and exit shape."*
- `automation/state/fleet/build_shared_signal.py:1133` (the full_send lane comment) — *"WHAT THIS LANE IS (doctrine: ARMS ARE RISK PROFILES, NOT STRATEGIES): the SAME validated setups, at MINIMUM size, with the COHORT-LEVEL vetoes not inherited."*

**Reading the doctrine literally against the code:** "same shared signal… differ only in sizing, gates and exit shape" describes a model where every arm sees the SAME setup-admission (which side/setup fired, at all) and differs ONLY in what it does after that — size it differently, refuse it via its own gate, exit it differently. `_perception_for_arm`'s docstring is the one piece of code that implements this literally for the safe/bold split: *"a safe arm reads signal['safe']… so a bold arm is judged on the BOLD ledger's perception, not the SAFE one."*

What actually binds safe-3 in production is different: entry ADMISSION (which setups are even candidates) is peak/bold-sourced whenever bold passed a side safe didn't; safe-3's OWN differentiation is confined to what runs downstream of that admission — `_gate_check` (min_triggers=2, require_confluence_or_sequence per the designation doc's `profile_summary`), sizing, and exit shape. That is real and does still apply (it is not the SAME zero-differentiation the 07-10 participation-cascade lesson describes) — but the SOURCE of the candidate list itself is not safe's own, contrary to the doctrine's "same shared signal" framing which implicitly assumes a single, uncontested signal rather than a signal that silently swaps sources per tick based on which side scored higher.

**So: doctrine says a safe-role arm should be bound by (a) the same validated setup menu, sourced identically for every arm, and (b) its OWN tighter selectivity/sizing/exit on top.** Production gives safe-3 (a) sourced from whichever of safe/bold passed, not safe's own, and (b) intact. The gap is narrower than "safe-3 has no differentiation at all" (07-10's participation-cascade problem) but wider than the doctrine's plain reading.

---

## 4. Every other place in the repo describing fleet arms as running safe's gates — false or misleading today

| Location | Claim | Status today |
|---|---|---|
| `automation/state/fleet/fleet_executor.py:790` | *"the cohort/tier gates baked into the shared signal's passed-derivation… apply UNIFORMLY to every arm"* | **Still present, uncorrected, as of this read (2026-09-03).** Literally true (all arms get the identical `strategies[]` list) but invites exactly the false inference the 08-13 review named ("bound by production's gate perimeter") — flagged as the "third stale-guarantee comment" on 08-13 (`ae6e0059`) and never fixed, unlike its sibling in `build_shared_signal.py` which WAS corrected 08-14. |
| `markdown/specs/ARCHITECTURE.md:115` (launch-chain diagram) | *"fleet_live.py → fleet_executor.py (per-arm sizing/admission, gate/sizing profile)"* | **Misleading as worded.** "Per-arm… admission" implies each arm's admission is its own; in fact admission (which setups are ENTER candidates) is shared/peak-sourced across all `fleet_rest` arms — only sizing and gate-based selectivity are genuinely per-arm. §3.2a's detailed "Known gaps" list (kill-switch latch, PDT enforcement) does not mention this gap at all — it is the one architecturally significant fleet behavior difference from core that §3.2a's otherwise-thorough 2026-09-02 refresh omitted. |
| `automation/state/fleet/accounts.json` / `automation/state/prod-shadow-designation.json` `profile_summary` (quoted in this task's brief) | *"FLEET-TIGHT-S (T20H): safe sizing, tight gate (min_triggers=2, require_confluence_or_sequence:true)…"* | **Incomplete, not strictly false.** "tight gate" is true for the downstream selectivity filter, but the summary makes no claim about (and a reader would not infer) that the pre-gate candidate list itself can be bold-sourced. This is exactly the arm the go-live-gate's criterion 5 rests on (`ARCHITECTURE.md:155`), so the omission is load-bearing. |
| `markdown/0dte/dual-account-design.md` "Overlap Resolution" (§, "When Bold sees a setup Safe doesn't: Bold enters; Safe holds. No cross-contamination.") | Describes the **core** two-account model (safe-2/bold-2) | **Accurate for what it describes** (core path genuinely has no cross-contamination — `heartbeat_core.py` computes each account's own verdict independently). Risk is a reader generalizing this "no cross-contamination" property to the fleet, where it does not hold for safe-3. The doc predates the fleet entirely (2026-05-14) and never claims fleet coverage, so this is a gap-by-omission, not a false statement. |
| `setup/scripts/gate_arm_matrix.py` / `automation/state/gate-arm-matrix.json` | Reports "is gate key X present in arm Y's params file" | **Self-scoped correctly** — its own commit message (`ae6e0059`) states the limit explicitly: "necessary but NOT sufficient to prove the arm's code path evaluates it." Not false, but easy to over-read as "gate coverage" when it only proves "gate key present." |

No hits found in `dashboard/` (grepped; empty — the cockpit does not appear to render any fleet-gate-coverage claim at all, so nothing there to correct, but also no visibility into this gap for J).

---

## Proposed DOC_FIX

Two edits, both mechanical and small:

1. **`automation/state/fleet/fleet_executor.py:790`** — append one clause to the existing comment (do not delete the historical rationale, per DOC-ARCHITECTURE fold discipline):

   > `apply UNIFORMLY to every arm` → `apply UNIFORMLY to every arm THAT READS THE SAME SOURCE — but that source is not always production/safe's own verdict: when SCORING_PEAK_LIVE diverges safe from bold, strategies[] is sourced from whichever side passed (see build_shared_signal.py's 2026-08-14 STALE-GUARANTEE CORRECTION). "Uniform across arms" is not "bound by production's gate perimeter."`

2. **`markdown/specs/ARCHITECTURE.md` §3.2a "Known gaps"** — add one bullet alongside the existing kill-switch-latch / PDT-enforcement gaps (same section, same disclosure standard already used there):

   > **Fleet-arm entry admission is not always safe-production-faithful.** When `SCORING_PEAK_LIVE`'s dual perception diverges (safe SKIPs, bold ENTERs), `build_shared_signal.py`'s shared `strategies[]` block — consumed identically by every `fleet_rest` arm including safe-3 — is sourced from whichever side (safe or bold) passed, not safe's own verdict. safe-3's `_gate_check` selectivity and sizing still apply downstream, but the underlying candidate set is not guaranteed to be safe-production-faithful. A purpose-built per-arm carve-out exists (`fleet_executor._perception_for_arm`) but is dead code on this path (only reached when `strategies[]` is absent, which is never in production). Proven 2026-08-13 (`DEEP-REVIEW-2026-08-13-MULTIAGENT.md` §3), re-confirmed 2026-09-03 (`veto-scope-safe-3.md`), still unresolved.

Both edits are additive/correcting-comment-only — no `automation/state/**` trading-path file behavior changes, consistent with this session's read-only constraint.

---

## The decision the main session must make

This is a judgment call, not a doc fix — argued both ways, ≤6 bullets each:

**Ship the fix (route safe-3 through `_perception_for_arm`/`signal['safe']`, i.e. make safe-3 production-faithful on admission, same as it already is on selectivity):**
- Restores the literal doctrine ("same shared signal… differ only in sizing/gates/exit") for the one arm (safe-3) the 2026-10-30 go-live decision is scored on — criterion 5's PF number should reflect safe's OWN edge, not a blend contaminated by bold's looser admission.
- The carve-out mechanism (`_perception_for_arm`) already exists, is already tested in isolation (it's the fallback branch's live path), and needs only a consumer-side change in `_plan_from_strategies`/`plan_all` to route per-arm — a small, reviewable, RED-proofable diff, not a redesign.
- Directly answers the open contradiction `ae6e0059` shipped three weeks ago and left unresolved; closes an L287-class recurrence (second instance of "a fix on one surface doesn't reach a second surface that regenerates the same decision").
- Config freeze is in effect until 2026-10-30 for the SCORED WINDOW — but this is a wiring/architecture fix, not a `params.json` value change, and the freeze's own carve-out allows "kill-type reductions... with a prereg"; this would need the same treatment (prereg before shipping, per this session's HARD CONSTRAINTS).

**Leave it (accept safe-3 as intentionally riding the "genuinely looser" bypass, same as risky-1/risky-3):**
- The bypass mechanism is explicitly J-directed doctrine for the WHOLE fleet ("we should just be getting in shit and seeing if it works," 2026-07-31) — nothing in that directive carved safe-3 out, and one could read J's intent as "every fleet arm should see everything the producer can find," with safe-3's SAFETY coming entirely from its selectivity gate + sizing + exit shape, not from a narrower admission set.
- safe-3's designation profile (`FLEET-TIGHT-S`) already names its differentiator as "tight gate," not "tight signal source" — arguably the design was always meant to differentiate on gate-strictness alone, and `_perception_for_arm` was built for a DIFFERENT purpose (the safe/bold CORE split) that was never meant to extend to fleet.
- Changing it now, mid-scoring-window (safe-3 is 1/20 days into its go-live criterion-5 clock per `HOME.md`), resets or contaminates the CI-lower(2.5%) bootstrap that clock is building toward — a wiring change to the admission source is arguably MORE disruptive to the measurement than leaving a known, now-well-documented gap in place until the window closes naturally.
- The dollar evidence so far is mixed, not one-directional: the 08-13 review's own numbers show the SAME bypass mechanism cost safe-3 −$410 on one event (11:41 cohort) but a symmetric loose-admission event elsewhere in the same fleet saved money relative to running both ratified gates everywhere (`ae6e0059`: "Running BOTH ratified gates on all arms would have been $122 WORSE than actual") — the case for "fixing" it as a strict improvement, rather than a different bet, is not yet made.

---

## Caveats / what was not verified this session

- **UNVERIFIED:** whether `dashboard/` genuinely contains zero fleet-gate-coverage claims, or whether the grep simply didn't finish (the first attempt timed out on a large tree walk and was not re-run to completion after the narrower re-grep returned empty — treat "no hits" as weak evidence, not a clean bill).
- **UNVERIFIED:** whether any commit between 2026-08-14 and 2026-09-03 touched `fleet_executor.py`'s stale comment and reverted a fix (git blame on that exact line block was not re-run after the 08-14 date; the content read this session is the current HEAD only).
- No trading-path file was read for behavior beyond what is quoted; no code was executed; nothing was armed, changed, or ordered, per this session's read-only constraint.

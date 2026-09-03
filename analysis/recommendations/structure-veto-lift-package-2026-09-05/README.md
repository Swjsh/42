# B3 — Structure-veto lift package (for the 2026-09-05 Rule-9 weekend decision)

Stamp: 2026-09-03T12:40 ET, built during market hours, read-only on every trading-path file.
**Nothing in this package has been applied.** `automation/state/params.json` is unmodified
(confirmed below). This is the package, not the decision.

## Verdict up front — this is contested, not clean

**The classifier defect is real and code-confirmed** (§1). **The case for actually flipping the
switch is NOT clean** — the codebase's own most rigorous instrument, a full production-replay
battery run 2026-08-23, already tested this exact flip and returned **`NOT-UNBLOCK-ELIGIBLE`, "DO
NOT FLIP"** (§3.2). Today added a fresh, favorable 5-episode cluster that battery never saw (§3.4).
Neither the rigorous battery nor today's cluster is individually decisive; they point opposite
directions at different evidence weights. **The main session's 09-05 decision is a real judgment
call between a documented defect and a documented "do not flip," not a clear ship.** This package
gives it everything needed to make that call in one sitting — it does not make the call.

---

## 1. Scope — exactly which arms this flip touches (verified in code this session)

**Direct: `safe-2` only** (the account `automation/state/params.json` governs). **Indirect:
`safe-3`** — see mechanism below. **Unaffected: `bold-2`, `risky-1`** (both retired-adjacent
arms `safe-1`/`risky-3` are `status: "retired", "live": false` in `accounts.json`, moot either
way).

### 1a. The production call site (unchanged from the morning D7 report, re-confirmed byte-exact)

`backtest/lib/engine/engine_cli.py:633-646` — gated on `gate_params.get("structure_veto_enabled",
False)`, called from the same account's own `gate_params`, which `setup/scripts/heartbeat_core.py:985`
builds as `{k: account_params[k] for k in GATE_KEYS if k in account_params}` — i.e. **per-account**,
not global. `automation/state/params.json:314` (safe) says `true`; `automation/state/aggressive/params.json:52`
(bold) says `false`, **explicit since 2026-08-12** (own doc string: *"Bold has been trading with
the structure veto off by OMISSION, never by a recorded decision... Writing false here is a
behavioural NO-OP... but converts a silent default into a stated choice"*). This package's patch
touches only the safe file; bold's explicit `false` is untouched and guarded independently by
`backtest/tests/test_structure_veto_explicit_2026_08_12.py` (still present, not duplicated here).

### 1b. Fleet routing — where the flip's effect actually propagates (my own trace, new this session)

Fleet arms don't read `params.json` gates directly; they read a **shared signal** built by
`automation/state/fleet/build_shared_signal.py` from the **same `core-decisions.jsonl` row** the
safe core engine already wrote. `fleet_executor._perception_for_arm` (line 108):

```python
role = "safe" if str(arm.get("id", "")).startswith("safe") else "bold"
block = signal.get(role)
```

— an arm whose `id` starts with `"safe"` reads `signal["safe"]`; everything else reads
`signal["bold"]`. `build_shared_signal.py:809` constructs `sig["safe"] = {"bull": dict(bull),
"bear": dict(bear)}` directly from the **safe** `core-decisions.jsonl` row's own `action` field
(`bull_pass = action == "ENTER_BULL"`) — **not a re-computation**, the literal same verdict safe's
core engine already reached. Confirmed directly from a raw row (today, 11:16:03 ET):

```json
"action": "SKIP_STRUCTURE_VETO",
"extra_exec_blocked_by": "structure_veto"
```

`action != "ENTER_BULL"` here, so `bull_pass = False` → `sig["safe"]["bull"]["passed"] = False`.
`fleet_executor._effective_passed` (line 122) defaults to `block.get("passed") is True` **unless**
the arm's `accounts.json` entry carries a `gate_params.hard_skip_verdicts` override — grepped
`automation/state/fleet/accounts.json`: only **`risky-3`** (retired, and reads `signal["bold"]`
regardless since its id doesn't start with `"safe"`) has such an override. **`safe-3` has none.**
So on any tick where safe's core engine returns `SKIP_STRUCTURE_VETO`, `safe-3` — which reads
`signal["safe"]`, the identical row — is also blocked, with no rescue path.

**Correction to this morning's D7 report/verify-1**: verify-1 stated *"`SKIP_STRUCTURE_VETO` is
architecturally exclusive to `account=safe` (safe-2)... `grep -c STRUCTURE_VETO` on
`fleet/{safe-3,...}/decisions.jsonl` → 0 in every file."* That grep is **true but not what it
sounds like** — `automation/state/fleet/decisions/safe-3.jsonl` only logs **actioned** (ENTER/EXIT)
events (6 rows total, ever; confirmed by direct read), never blocked-HOLD ticks, so it could never
show a literal `"STRUCTURE_VETO"` string regardless of whether safe-3 was blocked by it. The literal
verdict string is safe-2-exclusive (it's written once, by the safe core engine); **the blocking
effect is not** — it reaches safe-3 through the shared perception block by construction. I could
not empirically re-verify this against safe-3's own ledger (it doesn't log the negative case) — this
is a **source-code-verified mechanism (FACT)**, not a ledger-cross-checked one. If the main session
wants a ledger-level confirmation, it would need to instrument `safe-3`'s HOLD ticks, which
currently aren't persisted anywhere.

**Net scope statement: this flip changes trade population for `safe-2` (direct) and `safe-3`
(inherited, same tick, same direction, never independently blocked or rescued). `bold-2` and
`risky-1` are unaffected — both already read `signal["bold"]`, and bold's own config is an
independent, explicit `false` this package does not touch.**

---

## 2. Reproducing today's misclassification at 11:16 / 11:21 / 11:27 ET

Not re-run from scratch (already computed this morning, `backtest/tools/dissect_structure_veto_misclass.py`,
output `analysis/deep-research/2026-09-03-money/dissect-structure-veto-misclass.json`) — read
directly from that JSON this session (not the `.md` summary) to quote the classifier's own
inputs/outputs verbatim:

| Target tick (ET) | Logged verdict | Logged reason | SPY | Trigger bar fed | Bars fed (09:30→) | Reconstructed trend | Newest confirmable swing |
|---|---|---|---|---|---|---|---|
| 11:16:03 | `SKIP_STRUCTURE_VETO` | `downtrend` | 771.50 | 11:10:00 | 21 bars | `range` (APPROXIMATE, see below) | swing_high 768.87 @ 10:20 (56 min stale) |
| 11:21:03 | `SKIP_STRUCTURE_VETO` | `downtrend` | 772.02 | 11:15:00 | 22 bars | `range` (APPROXIMATE) | same 4 swings — 09:45 H 769.79, 10:10 L 767.78, 10:20 LH 768.87, 10:35 HL 767.96 |
| 11:27:03 | (nearest logged tick: 11:26:03/11:28:03 `SKIP_STRUCTURE_VETO`) | `downtrend` | 772.11 | 11:20:00 | 23 bars | `range` (APPROXIMATE) | same 4 swings, still 10:20/10:35-anchored |

All three ticks feed the identical 4-swing set (H 769.79@09:45, L 767.78@10:10, LH 768.87@10:20,
HL 767.96@10:35) into `classify_trend` — the classifier's own inputs are **frozen** across three
consecutive 5-minute triggers while SPY itself climbed 771.50→772.11→772.93, because
`find_swing_points(window=2)` (`crypto/lib/trendlines.py:41-72`, `for i in range(window, n -
window)`) makes the newest 2 bars of whatever's fed structurally ineligible to become a pivot —
a hard-coded property of the loop bounds, re-confirmed by direct read this session, not
re-derived. The reconstruction's own bucketing (once-per-minute-sampled proxy OHLC, not true
continuous-tick 5m bars) reads `range`, not the live system's logged `downtrend` — **does not
byte-reproduce**, labeled APPROXIMATE by the original report and re-confirmed as such here — but
both readings agree on the load-bearing fact: the newest real price action (bars from 11:05
onward, which contain the actual 770.7→772.9 push) can never register as a pivot, by construction,
regardless of which classifier verdict it nets out to.

**Root-cause statement (one sentence, unchanged from the morning report, re-verified from source
this session):** the veto reads `classify_trend` — the module's own self-documented **non-
authoritative fallback** (`crypto/lib/market_structure.py` docstring: *"the tentative trend...
`walk_structure` gives the authoritative trend"*) — never the authoritative `walk_structure`
state machine (`grep -n "walk_structure" backtest/lib/engine/engine_cli.py
setup/scripts/heartbeat_core.py` → zero matches, re-confirmed), fed through a swing detector that
is mathematically forbidden from seeing the newest 10 minutes of whatever bars it's given.

---

## 3. History since first fire — and the load-bearing contradiction

### 3.1 Today, freshly recomputed this session (not copied from the morning docs)

All 5 of today's episodes now have completed +30m readouts (they did not at the time of the
original D7 report or its 3 verify passes — market has ticked ~50 more minutes since). Recomputed
directly from `automation/state/core-decisions.jsonl` this session:

| Episode | Entry (ET) | Entry SPY | +30m SPY | +30m move | +60m SPY | +60m move |
|---|---|---:|---:|---:|---:|---:|
| 1 (11:11) | 770.73 | 11:42:04 | 772.465 | **+1.735** | 12:12:03, 772.545 | **+1.815** |
| 2 (11:16) | 771.50 | 11:46:03 | 772.58 | **+1.08** | 12:16:03, 772.69 | **+1.19** |
| 3 (11:21) | 772.02 | 11:51:07 | 772.935 | **+0.915** | 12:21:03, 772.77 | **+0.75** |
| 4 (11:26) | 772.11 | 11:56:04 | 773.145 | **+1.035** | 12:26:03, 772.525 | **+0.415** |
| 5 (11:31) | 772.93 | 12:01:07 | 773.30 | **+0.37** | 12:31:03, 772.45 | **−0.48** |

**+30m: 5/5 favorable to the blocked bull side (veto wrong every time today). +60m: 4/5 favorable,
1/5 (episode 5) flips unfavorable.** n=5 same-day episodes sharing one trend/session are not 5
independent trials (same rally, same regime) — no CI is claimed for n=5. This is FACT, computed
this session directly from the ledger, not carried over from the morning report (which only had
2-3 completed readouts at write time).

### 3.2 The contested full-history read — two instruments disagree, and one is stale

**Nightly instrument (`backtest/autoresearch/gate_expiry_check.py` → `automation/state/gate-registry-status.json`),
confirmed FRESH this session (`run_date: "2026-09-03"`, mtime 2026-09-03 02:16 Mountain / ~04:16
ET pre-market, `evidence_stale: false`, `evidence_age_days: 10` vs a 21-day interval) — cited
verbatim, not re-derived:**

```
window 2026-07-29..2026-09-01, n=5, wr=40%, exp/tr=+$69.7, total=+$348.50
drop_top1=+$45.5, drop_top3=−$189.0, verdict YELLOW
reason: "refused cohort positive ($69.7/tr) but n=5 < floor 10 -- watch, not yet actionable"
```

**Full-battery production replay** (`analysis/recommendations/gate-revalidation-structure_veto-2026-08-23-extended.json`,
generated 2026-08-23 — **11 days stale relative to today**, window 2026-06-26..2026-08-21, does
**not** include today's cluster or anything after 08-21), replayed through the real production
`exit_manager.plan_exit_actions` core (`walk_exit_manager`, same sound path), n=15 real simulated
trades — cited verbatim, not re-derived:

```
n=15, total=$111.50, mean=$7.43/tr, wr=40%
drop_top3=-$588.0 (fails), one_sample_p=0.8361 (indistinguishable from chance)
g_battery: {G_mean:true, G_oos:true, G_drop3:false, G_bhfdr:false, G_n:true}
verdict: "NOT-UNBLOCK-ELIGIBLE"
params_diff.recommendation: "DO NOT FLIP -- fails G_drop3/G_bhfdr"
```

**This is the exact proposed flip, already tested by this codebase's own more rigorous
instrument, with an explicit negative recommendation still on disk and not superseded by
anything newer.** The lighter nightly YELLOW (n=5, `drop_top3=-$189`) is fresher in wall-clock
terms but is the naive/lower-rigor read the extended battery was specifically built to
double-check (`gate_expiry_check.py`'s own module docstring: *"proved that wrong BOTH times it
fired: structure_veto_enabled..."*, referencing the same 08-23 commit). **Neither instrument has
been re-run with today's 5 fresh episodes folded in — that re-run is the single most decisive
next step and is outside this package's scope** (a `backtest/autoresearch` grind, not a
read-only citation).

### 3.3 Original ratifying study (the evidence that shipped the veto, 2026-06-26)

`structure-veto-ab-2026-06-26.json`, cited verbatim, re-confirmed present and unchanged:
`full_vetoes: 107` raw ticks, but only **2 actual trades** ever affected — both losers removed, 0
winners removed, **$0 delta out-of-sample** (all effect concentrated in-sample, 2025Q1). Thin and
stale by its own 21-day interval as of 08-04.

### 3.4 Full-ledger population reconstruction (two independent skeptic passes this morning, cited not re-derived)

`automation/state/core-decisions.jsonl` retains **2026-06-25 → today** (37,659 rows) — the D7
report's own claim that it only retains 08-26 onward was a bug in its scratch script's date
filter (`r.get("date", "") >= VETO_SHIP_DATE` silently drops the 87% of rows with no top-level
`date` key), independently caught by **two of three** skeptic passes this morning
(`verify-dissect-structure-veto-misclass-1.md`, `-2.md`). Corrected reconstruction (armed=true
only, `account=safe`, same-day/same-side/≤2.5min-gap dedup):

- **27 episodes** total history (12 C + 15 P), 5 today; **23 with completed +30m SPY-move
  readouts** (pre-today) → **13/23 (56.5%)** blocked side would have gained, **95% bootstrap CI
  [34.8%, 78.3%] — straddles 50%, not statistically distinguishable from a coin flip.**
- VIX-band split (verify-1): **VIX<15 mean +0.578** (n=7, veto worst here) / **15-18 mean +0.289**
  (n=9) / **18-22 mean −0.749** (n=4, veto net helpful here). **Today's VIX ran 14.84–14.91** —
  squarely the band where history says this classifier struggles most; not necessarily
  representative of higher-VIX regimes.
- Concentration: the nightly `$348.50` YELLOW total is carried by 2 of 5 win-days; drop the best
  day → `$45.5`; drop both win-days → `−$189.0` (§3.2, now baked into `gate-registry-status.json`'s
  own `combined` block since the 2026-08-23 concentration-guard fix, commit `71c39545`).

**This is a genuine disagreement in population size and effect strength between three
instruments** (naive nightly YELLOW-but-thin, rigorous battery NOT-UNBLOCK-ELIGIBLE, full-ledger
SPY-proxy CI-straddles-zero), **not a single settled number**. Today's fresh 5/5-at-30m cluster
(§3.1) adds new evidence in the "lift it" direction that none of the three above have seen yet.

### 3.5 The four named winning days — zero effect, confirmed twice independently

**2026-08-06, 08-13, 08-27, 08-28: zero `SKIP_STRUCTURE_VETO` fires that bind RTH trading**, on
both a corrected re-read of the full ledger (two independent skeptic passes) and the original
report's own in-window check for 08-27/08-28. (08-06 shows exactly one fire, 04:16 ET
**pre-market**, `side` field null — not an RTH trading event.) **Whatever this flip costs or
saves, none of it touches any of the four winning days.** This holds under both the "lift it" and
"don't lift it" readings — it is not itself evidence for either side, only a floor: the flip
cannot regress the sessions the whole book's edge case rests on.

---

## 4. Freeze classification — defect vs. expansion, both sides stated

**Task framing says "defect."** The mechanism (§1a-2) supports that: the classifier is provably
using its own module's self-labeled non-authoritative fallback, with a hard-coded blind spot on
the newest 10 minutes of price action — that is a bug in what the gate reads, independent of
whether the gate itself should exist.

**But the flip's own *effect* is a risk EXPANSION by the freeze's own definition**, and this is
the tension the main session needs to resolve, not this package:

- **Defect-side argument**: the classifier bug is real and unconditional — it doesn't matter what
  VIX regime or day type is active, `find_swing_points(window=2)` can never see the newest 10
  minutes, on any day. Fixing what a gate reads (not removing the gate) is squarely a "kill-type
  risk reduction" in spirit — it makes an existing control less wrong, not more permissive by
  design.
- **Expansion-side argument**: `structure_veto_enabled: false` does not fix the classifier — it
  **disables the entire gate**, which is a strictly WIDER trade population for both `safe-2` and
  `safe-3` (§1b) on every future tick where the (still-broken) classifier would have fired,
  correctly or not. The 08-04 prereg's own `against_case_carried` field says the same: *"it also
  gates the extra-setup dispatch path... lifting it widens `bollinger_squeeze`-class entries too."*
  A gate that is currently net-YELLOW-but-thin (§3.2) being turned fully off is exactly the shape
  "risk expansion" is meant to catch — more entries reach the book, not fewer.
- **This package does not resolve the classification** — it hands the main session both
  arguments, verified, so the 09-05 decision states which reading it is using and why, rather than
  defaulting to "defect" because that word appears in the task framing. If the main session reads
  it as an expansion, `GAMMA_FREEZE_OVERRIDE` (§6) does not apply and the change waits for 10-30
  regardless of any evidence quality — the CLAUDE.md freeze rule is explicit that reductions are
  the only 09-29 exemption, expansions wait unconditionally.

## 4a. Precondition gap this package found (new this session, not in the morning docs)

The 2026-08-04 prereg's own `trial_shape_frozen.shadow_requirement` field states: *"While
lifted, every would-have-vetoed entry must remain identifiable... if that logging path does not
exist at arming time, BUILD IT FIRST; arming without it is arming blind."* Checked this session:
`_classify_sameday_5m` (`engine_cli.py:634-635`) is called **only inside** the
`if gate_params.get("structure_veto_enabled", False):` block — flipping the key to `False` does
not just stop the veto from blocking; **it stops the classifier from running at all**, so nothing
would be logged for what the veto would have said post-flip. **The prereg's own precondition for
the kill criterion being countable is not currently met.** This is not a reason to block the flip
by itself (the prereg's precondition, not this package's judgment), but it means the "exact
one-line change" (§5) would ship **without the shadow-visibility the flip's own kill criterion
depends on** — the main session should treat this as a known gap, not an oversight if the kill
criterion turns out to be uncheckable after the fact.

---

## 5. The exact one-line change

```
automation/state/params.json:314
  "structure_veto_enabled": true,
→ "structure_veto_enabled": false,
```

**And only that.** No other key in `params.json` changes. Verified: the sibling `_structure_veto_enabled_doc`
string is left untouched by this patch (a future commit shipping this flip should update that doc
string to record the flip's rationale and date, but that is a second, deliberate edit — not part
of this package's single-key patch).

**Patch file**: [`structure-veto-lift.patch`](structure-veto-lift.patch) — generated via `git diff
--no-index` against a scratch copy (`params.json` was **never** touched on disk; verified via
`git status --short automation/state/params.json` → empty, both before and after building this
package). Verified this session, read-only, against the live working tree:

```
$ git apply --check analysis/recommendations/structure-veto-lift-package-2026-09-05/structure-veto-lift.patch
(exit 0 — applies cleanly, no output)
```

`--check` performs no write; the real file is confirmed unchanged immediately after (`grep -n
"structure_veto_enabled" automation/state/params.json` still shows `true` at line 314).

## 5a. Guard test

[`test_structure_veto_lift_2026_09_05.py`](test_structure_veto_lift_2026_09_05.py) — stored in
**this package directory**, not `backtest/tests/`, per the task instruction (copy it into
`backtest/tests/` in the same commit as the params.json edit, not before). Asserts: (a) safe's key
is `False` post-flip, (b) bold's key is still `False` and untouched, (c) the 08-04 prereg's
`trial_shape_frozen.kill_criterion` and `shadow_requirement` fields are still on disk and
non-empty, (d) `backtest/autoresearch/gate_expiry_check.py`'s replay entrypoint and
`gate-registry-status.json`'s `structure_veto_enabled` row are still wired (the re-check plumbing
exists), (e) no second key changed alongside this one.

**Run this session, against today's actual (pre-flip) repo state, to prove the guard is wired
correctly before anyone ships it:**

```
$ python -m pytest analysis/recommendations/structure-veto-lift-package-2026-09-05/test_structure_veto_lift_2026_09_05.py -v
...
test_safe_structure_veto_flipped_off FAILED
test_bold_structure_veto_still_false_unaffected_by_this_package PASSED
test_2026_08_04_prereg_kill_criterion_still_on_disk_and_nonempty PASSED
test_gate_expiry_reengine_still_wired_to_structure_veto_enabled PASSED
test_flip_did_not_silently_widen_beyond_the_single_key PASSED
1 failed, 4 passed in 2.62s
```

The one failure is **correct and expected** — it proves the guard would catch a missing/reverted
flip; it must go green only once the patch is actually applied.

## 6. Revert line

```
automation/state/params.json:314
  "structure_veto_enabled": false,
→ "structure_veto_enabled": true,
```

Byte-identical single-key revert, same as the original 2026-06-26 doc string already promises
(`"Revert: set false"` — inverted here since this package flips the other direction). No other
file needs to change to revert; `bold`'s file is never touched by either direction.

## 7. `GAMMA_FREEZE_OVERRIDE` invocation

Read directly from `setup/hooks/doctrine.py` this session (not assumed): the freeze hook
(`setup/hooks/gamma_doctrine.py:436-479`) checks for the literal string `GAMMA_FREEZE_OVERRIDE`
in **the tool call's own payload** — for an `Edit`/`Write` to a frozen path, in the **added
content** (`_added_content(tool, tin)`, i.e. the new text being written); for a `Bash`/`PowerShell`
command that writes to a frozen path, literally in **the command text** (`D.shell_write_hit`,
checked before any redirect/`sed -i`/`cp` pattern match — note `_strip_multiword_quoted` collapses
multi-word quoted spans first, so the token should sit **outside** any multi-word quoted argument,
e.g. as a trailing shell comment or inside the JSON value itself, not buried inside a `-m "long
message"` string).

Two concrete invocation shapes (**neither run this session** — this package applies nothing):

**Edit-tool shape** (edit the doc string alongside the flip, in the same edit, so the token rides
in the added content):
```
new_string includes: "...GAMMA_FREEZE_OVERRIDE: kill-type reduction, ref
analysis/recommendations/structure-veto-lift-package-2026-09-05/README.md, shipped 2026-09-05..."
```

**Shell shape** (e.g. a scripted `sed -i` or Python in-place edit):
```bash
python -c "..." automation/state/params.json  # GAMMA_FREEZE_OVERRIDE: kill-type reduction per
# structure-veto-lift-package-2026-09-05 -- prereg attached, guard test copied to backtest/tests/
```

Both forms only matter **on/after 2026-09-29** (`FREEZE_SAFETY_CHECKPOINT`) per `doctrine.py` —
before that date the freeze hook denies the edit unconditionally regardless of the token
(`freeze_active` gates on `FREEZE_START` 08-31 through `FREEZE_END` 10-30; the checkpoint text
itself only says pre-registered kill-type reductions "may ship on/after" 09-29, so an attempt
before then is out of window on its own terms, separate from the classification question in §4).

---

## 8. Addendum to the 2026-08-04 prereg (written here, `structure-veto-lift-prereg-2026-08-04.json` NOT edited)

If the main session re-opens `analysis/recommendations/structure-veto-lift-prereg-2026-08-04.json`,
the following exhibit should be appended to its `sources` array (as text here — the file itself
is untouched by this package):

```
"2026-09-03 exhibit (this package, structure-veto-lift-package-2026-09-05/README.md):
 5 fresh SKIP_STRUCTURE_VETO episodes, safe account, 11:11-11:35 ET, all side=C
 (bull blocked, structure_reason=downtrend) during a continuous SPY rally
 (770.73->772.93). +30m forward SPY move favorable to the blocked side in 5/5
 episodes (+0.37 to +1.735); +60m favorable in 4/5 (episode 5 flips to -0.48).
 Classifier inputs verified frozen across 3 consecutive 5-min triggers
 (11:16/11:21/11:27) -- same 4 swings fed each time, newest confirmable swing
 56-67 min stale, per find_swing_points(window=2)'s structural blind spot.
 DOES NOT resolve the 2026-08-23 extended battery's NOT-UNBLOCK-ELIGIBLE verdict
 (gate-revalidation-structure_veto-2026-08-23-extended.json, window ending
 2026-08-21, does not include this episode) -- neither instrument has been
 re-run with this exhibit folded in. Also surfaces a precondition gap: the
 prereg's own shadow_requirement (would-have-vetoed entries must stay
 identifiable post-flip) is not currently met -- _classify_sameday_5m only
 runs inside the gated block, so flipping the key silently also disables the
 shadow computation the kill criterion needs to be countable."
```

---

## 9. Proper fix path for after 2026-10-30 (spec only — nothing built, nothing scheduled)

The task-scoped flip (§5) turns the gate off; it does not fix the classifier. After the freeze
ends, the actual fix per the morning D7 report (re-confirmed by source read this session, not
re-derived):

1. **Swap `classify_trend` for `walk_structure`** at `backtest/lib/engine/engine_cli.py:203-224`
   (`_classify_sameday_5m`) — `crypto/lib/market_structure.py`'s own module docstring names
   `walk_structure` "the authoritative BOS/CHoCH state machine," explicitly built to replace the
   "tentative... fallback" `classify_trend` this function currently calls. This is a same-shaped
   swap to the one `dissect_structure_veto_misclass.py` already validated has "no look-ahead"
   (its docstring, re-read this session: swings become breakable only `window` bars after their
   own pivot — chronological, not a global re-derive).
2. **Confirmation-lag disclosure, independent of (1)**: `find_swing_points(bars, window=2, ...)`
   guarantees a structural ≥10-minute blind spot on the newest price action for *either*
   classifier function — `walk_structure` inherits the same swing detector, so swapping the trend
   function alone does not remove this lag, only the "which 2-pivot pair matters" ambiguity
   `classify_trend` adds on top of it. The fix path should either (a) document this lag
   explicitly in `engine_cli.py` (currently undocumented anywhere in that file — a comment-only
   change) as an accepted limit, sized against the entry-trigger cadence (5-min bars, ~1-6 min of
   additional bar-freshness lag already measured on top per the morning report's §1d), or (b)
   reduce `window` and re-validate the swing detector's false-pivot rate at the lower setting
   (a real backtest question, not a doc change — needs its own prereg).
3. **Re-run both instruments with the full corrected history** (§3.2, §3.4) before either shipping
   a permanent fix or re-arming the veto as-is — the two disagreeing verdicts on file today
   (naive-fresh-thin vs. rigorous-stale-negative) should not both still be the most recent word by
   the time this ships; whichever of (1)/(2) lands, the go/no-go evidence should be re-generated
   against it, not inherited from the pre-fix classifier's own track record.

No installer, no scheduled task, no registry row for any of this — spec only, per task scope.

---

## Caveats / what remains UNVERIFIED

- §1b (safe-3 inheriting the block) is verified from source code, not from safe-3's own ledger —
  that ledger doesn't log blocked ticks at all (confirmed: 6 total rows, ever, none from today).
  If the main session wants ledger-level confirmation, blocked-tick logging for fleet arms doesn't
  currently exist to check against.
- §3.2/§3.4's numbers are all citations of already-computed, dated files or this-session's own
  direct ledger reads — none of the heavier grinds (`gate_expiry_check.py`, the extended battery,
  or a full historical re-walk) were re-run in this task, per its own scope and the 5-minute
  python-process ceiling. The single most decisive open action is re-running both against today's
  cluster folded in, and that is explicitly **not** done here.
- Today's n=5 episodes are one session, one regime, not independent trials — no CI is computed or
  implied for them (§3.1).
- The VIX-band split (§3.4) is a citation of this morning's verify-1 pass, not re-derived this
  session.

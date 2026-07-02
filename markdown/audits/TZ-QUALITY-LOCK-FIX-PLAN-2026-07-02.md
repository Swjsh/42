# TZ QUALITY-LOCK FIX PLAN — 2026-07-02 (apply AFTER 16:00 ET, **after** the entry-floor patch)

> **Status: STAGED, NOT APPLIED.** Diagnosed live ~12:50 ET 2026-07-02 (market open — no
> live-path edits this session per hard rule). Guards already committed inert:
> `backtest/tests/test_tz_quality_lock_2026_07_02.py` (6 evidence pins green, 4 fix guards
> skip-until-applied via functional probe, 1 strict-xfail sentinel that turns RED if the
> fix lands without arming them).
>
> **Coordination:** this is the SECOND of two staged heartbeat_core patches today. Apply
> [`ENTRY-FLOOR-FIX-PLAN-2026-07-02.md`](ENTRY-FLOOR-FIX-PLAN-2026-07-02.md) first; this
> patch was **generated against the post-entry-floor tree** (hunk @838) and verified in
> that order. It also `--check`s clean against the pristine tree (offset −40), so the
> reverse order works, but the verified sequence is entry-floor → tz.

## Incident

2026-07-02, BOLD account: `verdict=ERROR` `"can't subtract offset-naive and offset-aware
datetimes"` for exactly **6 ticks, 11:50:02–11:55:02 ET**, then gone. Same minutes, SAFE
emitted ENTER_BEAR → SKIP_QUALITY_LOCK on the identical rank-1 TRENDLINE signal.

## Root cause (one sentence)

`_prior_fill_stopped` returns a **tz-aware** `last_exit` (`datetime.fromisoformat('…+00:00')`
is aware and the `+ timedelta` ET shift preserves tzinfo — `heartbeat_core.py:798-801`)
while `_et_now()` is **naive ET** (et_clock convention), so the quality-lock leg-2 gap
check `gap_min = (now_et - last_exit).total_seconds()` (`heartbeat_core.py:855`) raises
TypeError whenever it is actually reached.

## Evidence (verified this session, live ledger + code)

| Fact | Source |
|---|---|
| 6 bold ERROR rows, 11:50:02–11:55:02, exact message | core-decisions.jsonl:3592-3602 (even lines) |
| Safe rows same minutes: ENTER_BEAR → SKIP_QUALITY_LOCK | core-decisions.jsonl:3591-3601 (odd lines) |
| `_et_now()` → `et_clock.et_now()` → **naive** (`.replace(tzinfo=None)`) | heartbeat_core.py:138-140, et_clock.py:66 |
| `last_exit` built aware; tzinfo survives `+ timedelta` | heartbeat_core.py:798-801 |
| Crash site: `(now_et - last_exit)` — only mixed-tz subtraction on the tick path | heartbeat_core.py:855 (grep: 4 candidate lines, 855 is the only subtraction) |
| Both accounts entered 09:30 at **quality_rank 1** (TRENDLINE) and stopped out → both later hit the `rank == prior_quality` leg-2 branch | ledger 09:30:03 / 09:30:38 exec blocks |
| ERROR wrapper writes the bare row (per-account try/except) | heartbeat_core.py:1164-1166 |

## Why only bold — the state that differed

The gap subtraction only runs when `prior_stopped=True AND last_exit is not None`
(line 854), and `prior_stopped` = "exactly ONE same-symbol sell FILL activity today"
(`had_partial = len(same_sym_sells) >= 2`, line 806).

- **BOLD:** 5-lot premium_stop `SELL_ALL` at 09:32:04 filled in **one execution** → one
  sell activity → `prior_stopped=True`, aware `last_exit` → subtraction ran → **crash**.
- **SAFE:** 3-lot `SELL_ALL` at 09:31 filled in **multiple partial executions** (fill
  funnel: safe `exited: 3` vs bold `exited: 1`) → ≥2 sell activities → `had_partial=True`
  → `prior_stopped=False` → line 854 short-circuits **before** the subtraction → clean
  SKIP_QUALITY_LOCK. Safe was lucky (fill-shape), not immune — the bug is account-agnostic.

## Why it self-cleared at 11:56

The bear signal died: at 11:56:03 safe went HOLD "no setup passed scoring" (bear_score
dropped 8→7). No ENTER verdict → `_execute` → `_quality_lock_check` never reached → no
crash. **Latent, not fixed** — it fires again on the next same-rank re-entry signal after
any single-execution stop-out, on either account.

## Impact — what bold missed in the 6 dead ticks

The crash sits **past** scoring, entry gates, ceiling, creds, equity and FLAT-verify, and
**on the ALLOW branch** of the lock: rank 1 == prior 1, `prior_stopped=True`, gap at
11:50:02 ≈ **138 min ≥ 45** → the leg-2 exemption would have permitted the re-entry.
Absent the crash, bold **would have placed a put leg-2 at 11:50** (risk_gate sizing was
the only remaining gate; it sized 5 contracts at 09:30 on similar equity).

Observed tape after the blocked entry (ledger `spy` field): 745.38 (11:50) → 744.79
(11:51-55) → 744.63 (11:56) → 743.86 (12:15) → **742.67 (12:45)** — a −2.71 favorable
move for the put. Against bold's morning trade shape (5 lots, ~$0.45 premium, TP1 +75%),
that move very likely reaches TP1 — **estimated ~$100–170 forgone** (estimate; premium
path not observable). Hard facts: 6 consecutive permitted-entry ticks were killed, the
signal never returned (funnel: bold `enter: 1` all day), so the bug cost bold its only
recovery attempt after the −$40 morning stop-out.

## The fix — one hunk, normalize to naive ET at the source

`setup/scripts/heartbeat_core.py` `_prior_fill_stopped`, the `last_exit` assignment:

```python
# OLD (line 801 pristine / 841 post-entry-floor):
            last_exit = last_exit_utc + timedelta(hours=_et_offset_hours(last_exit_utc.replace(tzinfo=timezone.utc)))
# NEW:
            _shift = timedelta(hours=_et_offset_hours(last_exit_utc.replace(tzinfo=timezone.utc)))
            last_exit = (last_exit_utc + _shift).replace(tzinfo=None)
```

(plus the incident comment block — see the patch). Same normalization `et_clock.et_now`
itself uses. The inner `.replace(tzinfo=timezone.utc)` is kept: it is load-bearing for a
hypothetical offset-less timestamp string (keeps `_et_offset_hours`'s aware-UTC compare
safe). Gap arithmetic, 45-min cooldown, partial-fill logic: byte-identical.

## Mechanical apply (16:00 ET sequence)

```
# 1. entry-floor first (its own plan, edits 1-7)
git apply markdown/audits/entry-floor-fix-2026-07-02.patch
#    ... + its Edit 7 (delete entry-floor sentinel xfail marker)

# 2. then this patch
git apply markdown/audits/tz-quality-lock-fix-2026-07-02.patch

# 3. delete THIS file's sentinel marker: remove the line
#      @pytest.mark.xfail(reason=_NOT_APPLIED, strict=True)
#    in test_tz_quality_lock_2026_07_02.py::TestFixAppliedSentinel (leave the test).
```

**Pre-validated 2026-07-02 (scratch copies, live files untouched):**

- `git apply --check` of this patch **after** entry-floor on scratch: clean.
- `git apply --check` against the pristine tree: clean (`Hunk #1 succeeded at 798 (offset -40 lines)`).
- Entry-floor patch re-`--check`ed against live tree after staging this one: clean (no collision — hunks at 162/648/917 vs this one at 798-801).
- Full post-apply simulation (both patches + both sentinel markers deleted, module
  pre-cache): **`39 passed, 3 skipped in 0.69s`** — all 4 tz guards + all 21 entry-floor
  guards armed and green; the 3 skips are the soft incident-ledger pins (scratch stage
  has no core-decisions.jsonl; they pass on the live tree).
- Regression, isolated (money-path suite): live baseline **`36 passed`**; tz-patch-ONLY
  scratch copy vs byte-identical UNPATCHED scratch copy → **identical results** (2 fails
  in both, a scratch-import path artifact — REPO anchors to `__file__`) ⇒ **this patch
  introduces zero money-path regressions.** `test_graduated_guards.py` has zero
  references to `_prior_fill_stopped`/quality-lock/`last_exit` (grep: 0 hits) — out of
  this patch's blast radius.

## ⚠ Coordination warning for the 16:00 apply (entry-floor, NOT this patch)

Running `test_money_path_2026_07_01.py` against a module with the **entry-floor patch**
applied fails **6 tests** (`PLACED` → `SKIP_STALE_TRIGGER`): TestEntryCeiling
`_1400_is_allowed`, TestSimpleFirstPlacement ×2, TestVwapContinuationArmed ×3. Their
synthetic `_execute` payloads carry no today-dated `bar_ctx.timestamp_et`, so the new
fail-closed `_stale_trigger_bar` gate rejects them — a **test-fixture interaction, not a
production defect** (live payloads always carry the real bar timestamp). Verified
attribution: tz-only patched copy shows NONE of these. The entry-floor plan's
verification step 2 expects money-path all-green — **the apply commit must also add a
today-dated `timestamp_et` to those 6 fixtures** (or the suite goes RED and looks like a
bad apply). This tz patch is unaffected either way.

**RESOLVED 2026-07-02 (same day, before apply):** the 6 fixture updates are now staged
as hunks INSIDE `entry-floor-fix-2026-07-02.patch` itself (4th file; see that plan's
Edit 8), so they land in the same apply commit automatically. Re-verified:
`git apply --check` clean; both patches applied to a worktree copy →
`test_money_path_2026_07_01.py` **36 passed**. No action needed at apply time beyond
the standard `git apply`.

## Verification after apply (OP-33: quote the check)

1. `backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_tz_quality_lock_2026_07_02.py`
   → expect **11 passed** (0 skipped, 0 xfailed; the probe arms Part B).
2. `... -m pytest -q backtest/tests/test_entry_floor_2026_07_02.py backtest/tests/test_money_path_2026_07_01.py backtest/tests/test_graduated_guards.py` → all green.
3. Next session: any ENTER verdict on an account whose earlier stop-out was a
   single-execution fill logs `SKIP_QUALITY_LOCK` **or** places a leg-2 — never
   `verdict=ERROR "can't subtract offset-naive..."` in core-decisions.jsonl.

## Revert

Single commit; `git revert <apply-commit>`. No params/state changes involved.

## Related latent-risk note (out of scope here)

Pre-fix, `last_exit` was not just aware — its tzinfo **claimed UTC while the wall-clock
value was ET** (double-wrong for any future `astimezone`/`%z` use). The fix removes the
class of error. C3/C6-style sweep of other `fromisoformat` call sites on the live path
found no other mixed subtraction reaching `_et_now()` operands (grep evidence in the
staging session); a repo-wide naive/aware audit remains a reasonable FUTURE-IMPROVEMENTS
item, not part of this patch.

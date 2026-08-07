# CLOSE EXECUTION — 2026-08-07 evening (score-ladder ship gate + f10 behavior-neutral fix)

> Clock verified at execution: `python setup/scripts/et_clock.py` → `2026-08-07 16:25:02 Friday EDT, market_hours=False`. Executed AFTER the §5.3 ship condition's ≥16:21 ET floor, per doctrine.
> Scope: this file executes ONE pre-stated gate — the SCORE-LADDER-RUNG (LANE 1) ship/hold decision frozen in `analysis/deep-research/CLOSE-PACKAGE-LADDER-ADDENDUM-2026-08-07.md` §5.3 — plus the one unconditional behavior-neutral fix from `FRIDAY-2026-08-07-FULL.md` item A1. No parameter was adjusted after seeing results; the frozen prereg (`a780122e`, runner `3b3072a9`) ran verbatim.

## VERDICT: HOLD. The patch is NOT applied.

`accounts.json` carries no `score_ladder_rung` key. Production stays byte-identical binary on both risky arms tonight. The $0 forward shadow clock (`Gamma_LadderRungShadow`) is now registered and already has one real session logged.

The f10 bull-knob threading fix (item A1, unconditional/behavior-neutral) **DID ship** — see §4.

---

## 1. Step 1 — Friday real broker book, reconciled

FIFO-reconstructed every real fill today (`automation/state/fills-ledger.jsonl`, `attribution=="engine"` rows, `automation/state/fleet/fills_fifo.mine_real_arm_fills`) across all 5 arms:

| Arm | n | Real P&L (my FIFO recompute) | Claimed (task brief) | Residual |
|---|---|---|---|---|
| safe-2 | 3 | −$375.00 | −$375.77 | −$0.77 |
| safe-3 | 3 | −$1,048.00 | −$1,049.20 | −$1.20 |
| risky-1 | 3 | −$640.00 | −$640.96 | −$0.96 |
| risky-3 | 3 | −$624.00 | −$626.13 | −$2.13 |
| bold-2 | 0 | $0.00 (flat/PDT-dark) | $0.00 | $0.00 |
| **TOTAL** | 12 | **−$2,687.00** | **−$2,692.06** | **−$5.06** |

**Residual: $5.06 on a $2,687 book (0.19%), consistent with small per-contract fee/rounding, not a data error.** Confirmed the book is real and reconciles.

Trade-level detail also **independently confirms the deterioration story**: summing only the two waves `FRIDAY-2026-08-07-FULL.md` knew about at its ~12:53 ET write time (09:46 entries, 12:06 entries) reproduces that doc's own **−$1,820** figure almost exactly. The real ledger shows a **third wave** the doc never saw — 12:37–12:40 re-entries on safe-3/risky-1/risky-3 (−$828 combined) — plus a small put scalp on safe-2 at 14:16 (−$39). `−1820 − 828 − 39 = −2687`, matching the FIFO total exactly. Friday genuinely got much worse after the doc was frozen, exactly as the task brief described.

Real OPRA 1-min bars for the traded contracts (`SPY260807C0077{2,3,4,5}000`, plus `P00772000`) were confirmed fetchable this run (same-day OPRA unlock held) and are what price every rescue trade in §2 below — `REAL_OPRA_1MIN`, never EST.

## 2. Step 2 — Ladder replay re-run on Friday's full real-OPRA tape

Frozen runbook command, verbatim, no parameters changed:

```
backtest/.venv/Scripts/python.exe backtest/tools/ladder_rung_replay_2026_08_07.py \
    --ledger 2026-08-07 --sides C --no-est --out-tag friday-final
```

Provenance verified fresh: `git merge-base --is-ancestor a780122e HEAD` → true (prereg frozen before this run, git-provable).

**Result — a large negative swing from the earlier partial-day EST estimate:**

| | risky-3 (rung 7) | risky-1 (rung 8) |
|---|---|---|
| Earlier EST cell (partial day, ~180/386 ticks, captured ~12:30 ET) | +$217.01 | +$217.01 |
| **Real full-day cell (this run)** | **−$945.00** | **−$945.00** |
| n_added (rescue trades admitted) | 57 | 57 |
| binary_day_pnl (model, same day) | +$80.00 | +$80.00 |
| ladder_day_pnl (binary+rescue) | −$865.00 | −$865.00 |

**Reproducibility stress-tested, not just trusted on one run.** A second independent invocation of the identical CLI command (`--out-tag friday-final-rerun`) reproduced −$945.00/57 exactly. An ad-hoc diagnostic call that skipped `main()`'s `ALLOWED_RESCUE_SIDES = {"C"}` global assignment produced a spurious −$1,284.10/40 for risky-3 — root-caused to a real bug in *my own* first draft of the new shadow instrument (bear rescues silently admitted, occupying the one-position slot and changing which bull rescues fired), not evidence of non-determinism in the frozen mechanism. Both official `--sides C` runs agree exactly. Full root-cause trail in `backtest/tools/score_ladder_rung_shadow_nightly.py`'s own comment. risky-3/risky-1 producing an identical trade-by-trade set is an already-disclosed property of this week's data (addendum §1: "L1 (identical set)"), re-confirmed, not a new bug.

**Week-added recompute:**

| Day | Added P&L | Status |
|---|---|---|
| Mon 08-03 | +$1,307.00 | real (unchanged) — 1 trade |
| Tue 08-04 | +$3,384.00 | real (unchanged) — 1 trade |
| Wed 08-05 | −$1,555.00 | real (unchanged) — 19 trades |
| Thu 08-06 | −$325.00 | real (unchanged) — 30 trades |
| **Fri 08-07** | **−$945.00** | **real, NEW (was +$217.01 EST)** |
| **WEEK-ADDED** | **+$1,866.00** | Mon–Thu $2,811 + Fri −$945 |

**The literal frozen STOP RULE ("if week-added ≤ 0 → hold") is technically NOT triggered** — $1,866 > 0. If the gate were a single aggregate-sign check, this would read SHIP. It is not: the task's actual gate has a second, independent clause, and that clause fails hard (§3).

**The pointed question the task asked — what happened to the flagship 10:15 entry:**

```
sig 10:14:03  entry 10:15:00  SPY260807C00770000 @ 1.42  score=10 blockers=[10]
  -> exit 10:16:00  pnl=+$115.00  ribbon_flip_back
```

**It won.** One-minute round trip, exited via `ribbon_flip_back` — **not** TP1, **not** the −50% catastrophe cap. The literal motivating anecdote (J's complaint, the 10:15 refusal) held up fine on real data. The day lost for a different, more structural reason: the other 56 admitted rescue signals. Exit-reason histogram across all 57: `ribbon_flip_back` ×48, `structure_stop` ×9, **zero catastrophe-cap exits**. Win/loss split: 20 wins (+$915.00) vs 37 losses (−$1,860.00) = net −$945.00. Most trades are 1-minute round trips (enter minute N, `ribbon_flip_back` minute N+1) — the mechanism repeatedly re-admitted on a choppy, twice-reversing tape (rising trendline break 10:00, violent reclaim 10:15, break again 12:15, four failed retests 13:00–13:45, dump into the close — exactly as briefed).

**Friday's 57 admitted rescue signals is the highest of the week** — above Wednesday's already-flagged "chop bleeds" 19 and Thursday's 30 (addendum §1). By the ladder's own admission-count metric, Friday was the choppiest day it has seen, on the exact day used to motivate shipping it.

**Structural fragility also worth naming plainly:** the entire positive week is two single anchor trades (Mon +$1,307 from 1 trade, Tue +$3,384 from 1 trade = $4,691 combined) funding an accumulating bleed on every day with real admission volume (Wed 19 / Thu 30 / Fri 57 trades, netting −$2,825). C24 ("anchor trades are one-off exceptional setups") applies directly — Friday's real data makes the pattern worse, not better, than it looked this morning.

## 3. Step 3 — THE GATE, applied honestly

Two conditions, both required to ship:

| Condition | Result |
|---|---|
| (a) Recomputed week still positive | **PASS** — +$1,866.00 |
| (b) Friday not materially worse under the ladder | **FAIL** |

**(b) fails on every reasonable reading:**
- **Same-day, with vs. without:** binary_day_pnl +$80.00 → ladder_day_pnl −$865.00 for the identical arms/day — a **$945 same-day swing** attributable to the rescue lane alone, **−17.7% of SOD equity** (risky-3, $5,342.98) in one session.
- **Estimate vs. reality:** the ship-verdict's own Friday cell moved from +$217.01 (EST, partial day) to −$945.00 (real, full day) — a **$1,162 negative swing**, precisely the failure mode §5.3 existed to catch.
- **Admission volume:** 57 rescue signals is the week's maximum, exceeding the two days already flagged as the mechanism's chop-bleed weakness.

**Verdict: HOLD.** The week-added aggregate survives only because Mon/Tue's two anchor trades are large enough to absorb Friday's real loss — that is portfolio-level cushioning, not evidence the mechanism is sound on a chop day, and Friday (the day motivating the whole patch) is the sharpest chop-bleed example measured yet. This is not "straining for HOLD" — the literal single-metric gate would have said SHIP; the task's own two-part gate, applied honestly and checked against real trade-level data (including the specific question about the 10:15 position), says HOLD.

**Action taken:** patch NOT applied. No `git apply` run against the trading-path patch. `accounts.json` untouched — confirmed 0 matches for `score_ladder_rung` after this session, same as before it.

### $0 shadow clock (HOLD-branch deliverable)

Built `backtest/tools/score_ladder_rung_shadow_nightly.py` — replays LANE 1's exact frozen admission rule (imports `rung_admits`/`walk_day`/`DayBars` from `ladder_rung_replay_2026_08_07`, never a second copy — C14) against each day's real ledger + real OPRA, appends one row per arm to `analysis/arm-ladder/ladder-rung-shadow-ledger.jsonl`. Zero trading-path effect (source-text grep-guarded: never references `fleet_live`/`risk_gate`/`place_bracket`/`place_option_order`/`accounts.json`).

**RED-proof:** guard test written before the worker script existed → `1 failed, 3 errors` (`ModuleNotFoundError`).
**GREEN after building it:** `4 passed` — including a non-vacuous assertion that replaying 2026-08-07 reproduces the exact gate-decision number (−$945.00, both arms) from an independently-invoked code path. This guard is what caught the `ALLOWED_RESCUE_SIDES` bug above before it could ship.

Registered `Gamma_LadderRungShadow` (16:40 ET weekdays / 14:40 MT, hidden wscript→pythonw chain) — verified `State=Ready`. Seeded with today's real session (session 1 of the forward re-decision bar: ≥10 sessions, extras net>0, no session worse than −$500, negative-session average no worse than −$300 — today already breaches the per-session floor). Row added to `automation/state/SCHEDULED-TASKS.md` (count 106→107).

**Revert (whole instrument, one shot):** `Unregister-ScheduledTask -TaskName Gamma_LadderRungShadow -Confirm:$false`, then delete `backtest/tools/score_ladder_rung_shadow_nightly.py` + its guard test + `setup/install-ladder-rung-shadow.ps1` — analysis-only leaf, nothing else depends on it.

**Reconsideration path:** re-run this gate after the shadow ledger accumulates ≥10 forward sessions, or sooner if a chop-free trending day gives a cleaner read on the mechanism's upside case.

## 4. Step 4 — Behavior-neutral fix (ships regardless of the ladder gate) — APPLIED

Bull filter 10 (`buyer_pressure_bar_v11`) shared its volume-multiplier config key with bear filter 9 (`f10_vol_mult=f9_vol_mult` at both `run_backtest` call sites, `orchestrator.py`) — any future bull-only relax would have silently relaxed the unrelated bear filter. Applied the two staged, pre-generated diffs verbatim (`analysis/staged/f10-bull-knob-threading-2026-08-07.diff`, `f10-guard-activation-2026-08-07.diff`), fresh `git apply --check` confirmed clean on both before applying (commits had landed since they were staged this morning; no conflict).

**Mechanism:** `heartbeat_core._bull_f10_vol_mult()` reads `filter_10_vol_multiplier_bull` when present, else falls back to the existing `filter_9_vol_multiplier` — byte-identical while the new key is absent. `orchestrator.run_backtest` gained `f10_vol_mult_bull: Optional[float] = None`, threaded through `_params_to_kwargs` and both bull call sites via `(f10_vol_mult_bull if f10_vol_mult_bull is not None else f9_vol_mult)`.

**RED (pre-apply, quoted fresh this session):**
```
GAMMA_STAGED_2026_08_07=1 pytest test_f10_bull_knob_threading_2026_08_07.py test_feed_divergence_tool_2026_08_07.py
  7 failed, 47 passed
```
**GREEN (post-apply):**
```
same suite -> 54 passed
test_engine_gates_parity.py test_audit_fix_heartbeat.py -> 41 passed  (unchanged, as predicted)
```
**Curated safety gate (6 suites):** `59 passed` — clean, safe to commit (a phantom-name false-positive from this session's own `Gamma_LadderRungShadow` installer docstring — an incidental comment-mention of LANE 2's unregistered task name tripped the doc-parity scanner — was fixed by rewording the comment, not by weakening the guard).

**Independently verified byte-identical** (not just trusting the doc): both live params files (`automation/state/params.json`, `automation/state/aggressive/params.json`) confirmed to have zero occurrences of the new key; direct call `heartbeat_core._bull_f10_vol_mult(params)` returns exactly `filter_9_vol_multiplier` (0.7) for both.

**Revert:** `git revert <sha>`. **Kill trigger (frozen, n=1):** any tick where bull `f10_vol_mult` ≠ bear `f9_vol_mult` while the new key is absent from both params files → revert same evening.

## 5. What's live now that was not live this morning

**One line:** the score-ladder patch is still dormant (HOLD, unchanged from this morning) — what actually changed is that bull filter 10 now has its own config knob (behavior-neutral, unshipped-yet-usable for a future relax) and a new $0 nightly instrument is now watching, for real, what the held ladder mechanism would have done every trading day going forward.

## 6. Commits (pathspec-scoped, local only — not pushed, after-hours discipline holds for the NEXT push, not required tonight since nothing here needs urgent push)

1. `fix(engine): thread dedicated bull f10 knob (filter_10_vol_multiplier_bull), byte-identical while key absent` — `setup/scripts/heartbeat_core.py`, `backtest/lib/orchestrator.py`, `backtest/tests/test_f10_bull_knob_threading_2026_08_07.py`
2. `analysis(ladder): SCORE-LADDER-RUNG Friday real-OPRA gate -- HOLD verdict + $0 forward shadow clock` — `analysis/arm-ladder/LADDER-RUNG-2026-08-07-friday-final.json`, `analysis/arm-ladder/LADDER-RUNG-2026-08-07-friday-final-rerun.json`, `analysis/arm-ladder/ladder-rung-shadow-ledger.jsonl`, `backtest/tools/score_ladder_rung_shadow_nightly.py`, `backtest/tests/test_score_ladder_rung_shadow_nightly.py`, `setup/install-ladder-rung-shadow.ps1`, `automation/state/SCHEDULED-TASKS.md`
3. `docs(close-execution): score-ladder gate HOLD + f10 fix applied -- CLOSE-EXECUTION-2026-08-07.md` — this file + `automation/overnight/STATUS.md`

No trading-path file (`accounts.json`, `params.json`, `aggressive/params.json`) was touched. No order was placed. Market was closed throughout.

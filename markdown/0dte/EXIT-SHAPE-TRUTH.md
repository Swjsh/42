# EXIT-SHAPE-TRUTH — GOAL-EXIT-SHAPE-PARITY-2026-09-05

> One doc, one truth. Three sources disagreed on the core `ribbon_ride` runner exit:
> `automation/state/params.json` (top-level `v15_profit_lock_mode`/`runner_max_premium_pct`/
> `tp1_premium_pct`/`tp1_qty_fraction`), `automation/state/fleet/strategies.py` `RIBBON_RIDE`
> (the shared registry ExitShape), and `CLAUDE.md`'s doctrine prose. This doc resolves it with
> code line refs + real-fills evidence, per the goal's truth order: **exit-state.json /
> fills-ledger exit stages > code > params doc > CLAUDE.md prose.**

## The one-line verdict

`ribbon_ride` (the entry that fires 5-6 of every 6 live trades on all four arms) is exit-managed
by **`automation/state/fleet/strategies.py::RIBBON_RIDE.exit`** everywhere — core (safe-2/bold-2
via `heartbeat_core.py`) and fleet (safe-3/risky-1 via `fleet_executor.py`) alike. `params.json`'s
top-level `v15_profit_lock_mode` / `v15_profit_lock_trail_pct` / `runner_max_premium_pct` /
`tp1_premium_pct` (non-isolated) are **VESTIGIAL on this path** — read by sim/replay tooling only,
never by the live exit code for `ribbon_ride`. This was independently discovered and documented by
three prior sessions (`backtest/lib/exit_manager_walk.py`, `backtest/tools/exit_manager_replay.py`,
`backtest/tools/regime_readjudication_correctexit.py`) before this goal — this doc is the first
place it is stated as the per-arm exit-shape reference, corrected into CLAUDE.md, and guarded by a
test.

## Per-arm live exit shape (ribbon_ride)

| Element | Live value (all 4 arms unless noted) | Code line | params.json key claiming it | Read on the ribbon_ride path? |
|---|---|---|---|---|
| TP1 trigger | +100% premium (`tp1_premium_pct=1.0`) — **risky-1 patched to +50%** (`tp1_premium_pct=0.5`) | `strategies.py:143` (registry); `fleet/accounts.json` arms[risky-1].params_patch.exit_patch (patch) | `tp1_premium_pct` (0.30/0.50 default) | **NO** for safe-2/bold-2/safe-3 (registry 1.0 wins); risky-1's value comes from its `exit_patch`, not the top-level params key |
| TP1 qty fraction | 0.667 (sell 66.7%, ride 33.3%) — all 4 arms | `strategies.py:143` `tp1_qty_fraction=0.667` | `tp1_qty_fraction` (0.8 default) | **NO** — registry hardcodes 0.667 for ribbon_ride; the 0.8 default only applies to isolated setups (bollinger_squeeze etc.) via `heartbeat_core.py`'s `_xov` branch |
| Pre-TP1 ladder | rungs `[[0.50,0.30],[0.75,0.60]]` (lock 30%/60% at +50%/+75% MFE) | `strategies.py:141` `pre_tp1_ladder` | none (no params key) | hardcoded, not params-driven |
| Pre-TP1 trail | arms at +75% MFE, trails 20% off HWM | `strategies.py:142` `pre_tp1_trail_arm_pct=0.75, pre_tp1_trail_pct=0.20` | none | hardcoded |
| Stop | chart-level structure stop (trigger-level invalidation); catastrophe cap −50% | `strategies.py:144` `stop_mode="structure", catastrophe_stop_pct=-0.50`; resolved in `exit_manager.py::ExitState.from_entry` (requires `params.json:structure_stop_enabled=True`, confirmed true both accounts) | `structure_stop_enabled` (gate only, not the shape) + `premium_stop_pct` (−0.50 fallback) | **structure_stop_enabled IS read** (gates the mode); the −0.50 cap value itself comes from the registry's `catastrophe_stop_pct`, not `premium_stop_pct` |
| Post-TP1 profit-lock | trailing chandelier, arms at +5% favor (`profit_lock_arm_pct=0.05`), trails 15% off HWM (`trail_pct=0.15`) | `strategies.py:143` `profit_lock_mode="trailing", runner_target_pct=99.0, trail_pct=0.15`; default `profit_lock_arm_pct=0.05` from the dataclass default (`strategies.py:41`) | `v15_profit_lock_mode` ("fixed"), `v15_profit_lock_threshold_pct` (0.05), `v15_profit_lock_trail_pct` (0.125) | **NO** — params.json says "fixed"/0.125; live is "trailing"/0.15. This is the exact discrepancy CLAUDE.md's prose got right on the numbers (5%/15%) but params.json's doc-adjacent value (0.125, "fixed") is the vestigial one |
| Runner target | **99.0×** (effectively unconstrained — "tgt-none", exits via structure/trail/EOD only, never the target itself) | `strategies.py:143` `runner_target_pct=99.0`; fires in `exit_manager.py:665-669` (`stage="runner_target"`) only when `entry*(1+99.0)` is reached — practically never | `runner_max_premium_pct` (2.5) — a DIFFERENT, unrelated key read only by sim/replay tools (`backtest/lib/orchestrator.py:346`, `backtest/autoresearch/*_runner_target_sweep.py`), never by the live `ribbon_ride` exit path | **NO** — confirmed dead on this path (see real-fills evidence below and vary-and-assert) |
| Time stop | 15:50 ET hard flatten (`Gamma_EodFlatten`); `time_stop_et` param forwarded to `exit_actuator.manage_tick` | `heartbeat_core.py::_manage_exits` forwards `params.get("time_stop_et")`; `automation/state/fleet/fleet_live.py:983` same | `time_stop_et` | YES — this one IS read (unlike the exit-shape keys above) |

**safe-3's exit_patch** (`accounts.json` arms[safe-3].params_patch.exit_patch = `{stop_mode:
"structure", profit_lock_mode: "trailing"}`) does not touch `runner_target_pct` — it inherits the
registry's 99.0. **risky-1's exit_patch** (`{tp1_premium_pct: 0.5, stop_mode: "structure"}`)
likewise never overrides `runner_target_pct` — also 99.0. So all four goal arms run the same
effectively-unconstrained runner target.

## E1 — real-fills exit-stage evidence (since 2026-08-01)

Instrument: exit-actuator `actions[].stage` entries logged per tick — core lane in
`automation/state/core-decisions.jsonl` (`exit_pass[].actions[]`, keyed by `account` = "safe"/"bold"),
fleet lane in `automation/state/fleet/<arm>/decisions.jsonl` (same `exit_pass` shape). Counted with a
one-off tally script over every row with `ts_et >= 2026-08-01`, `exit_pass` non-empty (this is a
count of exit-actuator STAGE FIRINGS across ticks, not unique round-trips — a position can be
touched by the same stage on consecutive ticks before it actually closes, so these are upper-bound
frequency counts, not trade counts. UNVERIFIED as trade-level dedup was not built for this goal).

| Arm | tp1 | trail | structure_stop | premium_stop | ribbon_flip | time_stop | runner_target |
|---|---|---|---|---|---|---|---|
| safe-2 | 24 | 68 | 18 | 19 | 3 | 1 | **0** |
| bold-2 | 16 | 58 | 16 | 13 | 2 | 0 | **0** |
| safe-3 | 18 | 54 | 23 | 7 | 0 | 1 | **0** |
| risky-1 | 32 | 103 | 22 | 13 | 11 | 0 | **1** |

`trail` fired 54-103x per arm; `runner_target` fired **once** across all four arms combined (one
tick on risky-1) and **zero times** on the two core accounts. This matches the pre-existing
`prereg-runner-finite-tgt-candidate-2026-08-06.json`'s own disclosed `blocking_facts` ("live
runner_target exits: 2 fleet / 0 core, ever") — this session's narrower since-08-01 window finds 1
fleet / 0 core, consistent direction, not a new finding. **The runner target is dead in practice**:
every runner that survives to the point a fixed 99.0× target could matter is instead cut by the
trailing chandelier, the structure stop, or the EOD flatten first.

## E2 — code trace + vary-and-assert

**Core lane** (safe-2, bold-2): `heartbeat_core.py` → on a `ribbon_ride` entry (non-`_xov` setup,
~line 3045) imports `strategies` and calls `strategies.by_name("ribbon_ride").exit.to_dict()` to
build `_shape`, then `exit_actuator.register_entry(..., exit_shape=_shape, ...)`. **No params.json
argument is passed into this branch at all** — the dict comes straight from the hardcoded
dataclass. `heartbeat_core._manage_exits` → `exit_actuator.manage_tick` runs the tick-managed
scale-out against that registered shape every tick.

**Fleet lane** (safe-3, risky-1): `fleet_executor.py::_exit_shape_dict(strat, arm)` starts from
`strat.exit.to_dict()` (same registry `RIBBON_RIDE.exit`) and shallow-merges the arm's
`params_patch.exit_patch` (validated against `EXIT_PATCH_ALLOWED_KEYS`, derived from
`ExitShape.__dataclass_fields__` — so a typo'd key raises `ValueError` at config-load, not a
silent no-op). safe-3's patch touches `stop_mode`/`profit_lock_mode` only; risky-1's touches
`tp1_premium_pct`/`stop_mode` only. Neither touches `runner_target_pct`, `trail_pct`, or
`profit_lock_arm_pct` — those three stay at the registry's 99.0 / 0.15 / 0.05 for every fleet arm
that hasn't explicitly patched them (risky-3 patches `trail_pct` to 0.20, out of this goal's 4-arm
scope). `fleet_live.py::manage_tick` runs the same `exit_actuator` scale-out as core.

**Vary-and-assert** (READ-ONLY, run against in-memory copies, no file writes):

```
$ backtest/.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0, 'automation/state/fleet')
import strategies, copy
base_params = {'runner_max_premium_pct': 2.5, 'v15_profit_lock_mode': 'fixed',
               'v15_profit_lock_trail_pct': 0.125, 'tp1_premium_pct': 0.30,
               'tp1_qty_fraction': 0.8}
shape_before = strategies.by_name('ribbon_ride').exit.to_dict()
mutated = copy.deepcopy(base_params)
mutated['runner_max_premium_pct'] = 999.0   # wildly different value
mutated['v15_profit_lock_mode'] = 'fixed'
mutated['tp1_qty_fraction'] = 0.01
shape_after = strategies.by_name('ribbon_ride').exit.to_dict()   # <-- takes NO params arg
print('shape unchanged by mutated params:', shape_before == shape_after)
print('runner_target_pct:', shape_after['runner_target_pct'],
      'tp1_qty_fraction:', shape_after['tp1_qty_fraction'])
"
shape unchanged by mutated params: True
runner_target_pct: 99.0 tp1_qty_fraction: 0.667
```

This proves the claim mechanically, not just by inspection: `strategies.by_name("ribbon_ride")`
takes **no params argument whatsoever** — the returned `ExitShape` is a frozen dataclass literal.
Mutating a copy of `params.json`'s values before the call changes nothing about the shape the live
exit engine will register. `runner_max_premium_pct`, `v15_profit_lock_mode`,
`v15_profit_lock_trail_pct`, and the non-isolated `tp1_premium_pct`/`tp1_qty_fraction` keys are
**C14 dead/translated-but-unapplied knobs** on the `ribbon_ride` path specifically (they ARE read
by the isolated-setup `_xov` branch and by sim/replay tooling — this finding is scoped to
`ribbon_ride`, the entry that fires 5-6 of 6 live trades).

**Constants in force today, all 4 arms, ribbon_ride:** `premium_stop_pct=-0.20` (flag-off
fallback only; live path is `stop_mode="structure"` + `catastrophe_stop_pct=-0.50`),
`tp1_premium_pct=1.0` (0.5 risky-1 patched), `tp1_qty_fraction=0.667`,
`pre_tp1_ladder=[[0.50,0.30],[0.75,0.60]]`, `pre_tp1_trail_arm_pct=0.75`,
`pre_tp1_trail_pct=0.20`, `profit_lock_mode="trailing"`, `runner_target_pct=99.0`,
`trail_pct=0.15`, `profit_lock_arm_pct=0.05` (default), `profit_lock_arm_scope="post_tp1"`
(default), `stop_mode="structure"`, `catastrophe_stop_pct=-0.50`.

## E5 — runner_target_pct 99.0: (a) deliberate trail-only runner

**Adjudicated (a): deliberate, documented, C30-consistent design — not a dead knob whose finite
setting would be a risk reduction.**

- `strategies.py`'s own comment on `RIBBON_RIDE` (line ~120) states the intent verbatim:
  "runner_target 99.0 == the cell's tgt-none (runner exits via structure/trail/EOD only)" —
  ported byte-for-byte from the SS-B validated cell (`analysis/recommendations/structure-stop-2026-07-09.json`,
  "the ONLY candidate passing BOTH pre-registered layers").
- CLAUDE.md OP-25 lesson index **C30** ("Unconstrained exit targets (runner never hits 5x in
  0DTE) = dead knob", L24/148/176/291) is the doctrine class this shape deliberately sits inside
  — an unconstrained target is fine *when the runner is meant to exit some other way*, which this
  one is (trail/structure/EOD). C30 is a warning against believing a raised-but-still-finite
  target changes behavior when nothing ever reaches it, not a mandate to always set a finite
  number.
- The right-tail ledger (`analysis/right-tail/ledger.jsonl` + the fresh join computed in
  `analysis/recommendations/prereg-runner-target-vs-tape-peak-10-30-2026-09-05.json`, filed
  2026-09-05 same day) shows realized exits sitting BELOW the wave's own tape peak on 27 of 34
  waves (79%) — the give-back is real, but the fix that prereg proposes is a **wider** trail/target
  (an EXPANSION candidate, 2.5x-4.0x / 20-25% trail), not tightening toward CLAUDE.md's stale 2.5x
  text. That prereg is the correct place for "should the runner target move" — this goal's job is
  only to state today's live truth, which it now does.
- The 2026-08-06 sibling prereg
  (`analysis/recommendations/prereg-runner-finite-tgt-candidate-2026-08-06.json`) already
  adjudicated NULL on a finite-target hypothesis, citing the same "2 fleet / 0 core, ever"
  runner_target-fire fact this doc's E1 table reproduces (1 fleet / 0 core since 08-01 —
  consistent, narrower window).
- A finite runner target would cap *upside*, not reduce *downside* risk — the downside is already
  bounded by the structure stop / −50% catastrophe cap, which `runner_target_pct` does not touch.
  So "finite target = risk reduction" does not hold mechanically here; per DONE-WHEN's own fork,
  that means this is (a), not (b). No reduction-type prereg is filed by this goal.

## Correction ledger (what changed and why)

| Doc | Before | After | Why |
|---|---|---|---|
| `CLAUDE.md` strategy paragraph | "runner target 2.5×"; "tp1_qty_fraction 0.8 Safe / 0.667 Bold" | "runner target UNCONSTRAINED (99.0× sentinel — trail-only, C30)"; "tp1_qty_fraction 0.667 on ribbon_ride (all arms)" | Corrected to the live code (`strategies.py::RIBBON_RIDE`), not params.json's vestigial values, per this doc's E1/E2 evidence |
| `automation/state/params.json` `_doc` strings | n/a | **not edited** | FROZEN_TRADING_PATH file; the doctrine hook blocks edits to this file even for `_doc` strings (see Operating Rules). Correction lives here instead. |

## What this doc does NOT change

No `params.json` value, no `strategies.py` value, no code behavior. This is a documentation-only
correction of what CLAUDE.md's prose claims about an already-live exit shape.

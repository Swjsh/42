# G1 CODE TRUTH TABLE — entry-side gates per arm

Stamp: 2026-09-03T14:30 ET (market hours). Read-only, code-first investigation; 3 ledger rows
independently re-read and quoted verbatim this session (not carried over from
`veto-scope-safe-3.md`, though this session's findings agree with and extend it). Companion:
[`fleet-gates-code-binding-table.json`](fleet-gates-code-binding-table.json).

## Verdict up front

**Only TWO gate layers ever bind a fleet arm's (safe-3, risky-1, risky-3) entry: engine_cli's
scoring filters (computed once, off the SAFE ledger, shared by everyone) and the arm's OWN
`gate_override` (min_triggers / require_confluence_or_sequence / min_setup_quality).** The
GATE_KEYS cohort flags in `params.json`/`aggressive/params.json` (`structure_veto_enabled`,
`block_bull_1100_1200`, `block_elite_bull`, etc.) bind ONLY the core accounts (safe-2, bold-2) —
they never reach a fleet arm, because `fleet_executor.plan_all` always takes the
`signal["strategies"]` branch (`build_shared_signal.EMIT_STRATEGIES=True`, unconditional), and
that branch's `_plan_from_strategies` never reads `signal["safe"]`/`signal["bold"]` or calls the
safe/bold perception router at all. This was confirmed source-code-verified last session
(`veto-scope-safe-3.md`) and is re-verified here against 3 fresh ledger rows plus extended with
the full per-side filter list, the `finalize()` gate ordering, git-history provenance, and the
retired-arm/probe-arm loose ends.

---

## (a) engine_cli scoring filters — both perceptions, per side

Source: `backtest/lib/filters.py`, called via `backtest/lib/engine/engine_cli.py::decide_payload`
→ `score.score_bar` → `evaluate_bearish_setup` / `evaluate_bullish_setup`. Scored **once per
tick, per account** (safe's own bars/VIX/ribbon vs bold's own — they read the SAME underlying
SPY 5m data but each account's `run_account` call builds its own `bar_ctx`), never per-arm — the
fleet arms consume whichever perception `build_shared_signal.py` hands them (see §c).

### BEARISH_REJECTION_RIDE_THE_RIBBON — 11 filters (10 + sweep)

Docstring `filters.py:1-18`, body `evaluate_bearish_setup` ~1535-1930:

| # | Filter | Note |
|---|---|---|
| 1 | time >= 09:35 ET | + `no_trade_before`/`no_trade_window` |
| 2 | news clear | backtest stub, always pass |
| 3 | budget > risk | always true in backtest |
| 4 | day-trades >= 1 | always true in backtest |
| 5 | ribbon BEAR-stacked (Fast<Pivot<Slow) | structural |
| 6 | spread >= 30 cents | |
| 7 | NOT volume_divergence_failed | |
| 8 | VIX > 17.30 AND vix_rising | `vix_soft_mode`: -1 demerit instead of hard block, default **False** |
| 9 | breakdown_bar_bearish on last closed bar | `f9_vol_mult` configurable (0.7 default, v11 ratified) |
| 10 | >= `min_triggers` of {level_reject / ribbon_flip / multi_day_confluence / sequence_rejection} + >=1 level-tied trigger | `min_triggers` default 1 (ratified 2026-05-07) |
| 11 | SWEEP_BLOCKER — HARD block if a BULLISH_SWEEP (down-sweep) hit the rejection level in the prior N bars | `sweep_blocker_enabled` default **False**; confluence carve-out skips it when enabled |

### BULLISH_RECLAIM_RIDE_THE_RIBBON — 12 filters (11 + sweep)

Docstring `filters.py:1279-1296` ("Filters (per heartbeat.md BULLISH (11))"), body
`evaluate_bullish_setup` ~1310-1420:

| # | Filter | Note |
|---|---|---|
| 1 | time gates (doc says >=10:00 ET; code default no_trade_before=09:35) + NOT 14:00-15:00 | |
| 2 | news clear | stub |
| 3 | budget > risk | always pass |
| 4 | day-trades >= 1 | always pass |
| 5 | ribbon BULL-stacked Fast>Pivot>Slow | |
| 6 | spread >= 30c | |
| 7 | NOT volume_divergence_failed | mirror of bearish |
| 8 | VIX < 17.20 OR vix_falling | `vix_soft_mode_bull`: -1 demerit, default **False**, and per its own docstring **NOT wired into heartbeat_core.py's score_params construction** — live in every backtest path, inert in production regardless |
| 9 | VIX < 22 HARD cap | `VIX_BULL_HARD_CAP` |
| 10 | buyer pressure: close>open AND vol >= 0.7x 20-bar avg | `f10_vol_mult`, RATIFIED v11 |
| 11 | >= `min_triggers` of {level_reclaim / ribbon_flip / multi_day_confluence / sequence_reclaim} AND htf_15m != BEAR | HTF disagreement is a -1 score modifier, not a hard block; `min_triggers` default 2 |
| 12 | SWEEP_BLOCKER — HARD block if a BEARISH_SWEEP (up-sweep) hit the reclaim level in the prior N bars | `sweep_blocker_enabled` default **False**; confluence carve-out |

Both `min_triggers` values are overridden per-account by `heartbeat_core.py`'s `score_params`
construction (`filter_10_min_triggers_bear`/`filter_10_min_triggers_bull` keys in the account's
own params file) — this is the ONE lever GATE_KEYS-adjacent config actually reaches inside
`score_bar` itself, and it is identical machinery for safe and bold (each reads its own file).

---

## (b) GATE_KEYS — params.json / aggressive/params.json, applied in heartbeat_core

`setup/scripts/heartbeat_core.py:184-197`:

```python
GATE_KEYS = [
    "block_level_rejection", "trendline_requires_ribbon_flip", "block_elite_bull",
    "block_elite_bull_vix_low", "block_elite_bull_vix_high",
    "block_bull_ribbon_flip", "block_bull_1100_1200", "block_bull_morning_agg",
    "require_bearish_fill_bar", "min_ribbon_momentum_cents", "max_ribbon_duration_bars",
    "midday_trendline_gate", "block_conf_lvl_rej_midday_afternoon", "block_conf_lvl_rec_afternoon",
    "entry_bar_body_pct_min", "entry_bar_body_pct_min_bull", "vix_bear_hard_cap",
    "structure_veto_enabled",
    "structure_shift_confirmation_enabled",
]
```

**Which params file each core account reads** — `heartbeat_core.py:145-148`:

```python
ACCOUNTS = {
    "safe": {"params": STATE / "params.json", "mcp_server": "alpaca", "fleet_arm": "safe-2"},
    "bold": {"params": STATE / "aggressive" / "params.json", "mcp_server": "alpaca_aggressive", ...},
}
```

`run_account(account, ...)` (`heartbeat_core.py:1641`) does `params =
json.loads(cfg["params"].read_text(...))` at line 1647 — **direct file read, no fleet
`gate_override` merge, no cross-account fallback.** `gate_params = {k: account_params[k] for k in
GATE_KEYS if k in account_params}` (line 985) is passed to `engine_cli.decide_payload` as
`payload.gate_params`, consumed by `gates.evaluate_gates`. `score_params` (bear/bull kwargs,
lines 991-996) is built from the same `account_params` dict, same file.

**Divergence confirmed, both by file content and by ledger**: `structure_veto_enabled` and
`block_bull_1100_1200` live in `automation/state/params.json` (safe); `aggressive/params.json`
sets `structure_veto_enabled: false` **explicitly** (line 52-53, with a doc citing "over 25,821
ledger rows SKIP_STRUCTURE_VETO fired 116 times for account=safe and ZERO times for bold") and
carries **zero** matches for `block_bull_1100_1200` (grep-confirmed). This is by design for the
CORE accounts (bold is deliberately looser) — the defect this task investigates is that the SAME
divergence propagates, un-reviewed, to every fleet arm via §(c)/(d) below, including the
`safe`-cell arm (safe-3).

---

## (c) build_shared_signal.py — sig['safe'], sig['bold'], sig['strategies']

Source: `automation/state/fleet/build_shared_signal.py`.

- `EMIT_STRATEGIES = True` — **line 293**, unconditional module default.
- `SCORING_PEAK_LIVE = True` — **line 281** ("flipped 2026-06-25 J directive: all paper fleet
  arms live for the DATA").
- `_latest_today_decision(today, account: str = "safe", ...)` — **line 238**: the DEFAULT
  perception, when nothing else overrides it, is the SAFE ledger.

`build()` (line 654+), inside the main branch (row found, not blind/beacon-fallback):

```python
# line 809
sig["safe"] = {"bull": dict(bull), "bear": dict(bear)}
# line 810
sig["bold"] = _bold_passed_blocks(today, now, core_tick_id=_core_tick_id)
```

`bear`/`bull` here are mapped straight off the **SAFE** core-decisions.jsonl row —
`passed = (action == "ENTER_BEAR"/"ENTER_BULL")` literally (production-faithful). `sig["bold"]`
comes from `_bold_passed_blocks_from_row` (lines 583-627), which is **not** a literal
`action == "ENTER_BULL"` check — it's `_score_peak_check(side, action, score, trigger, fired)`:
`passed=True` whenever `score >= peak_threshold` (bull 9/11, bear 8/10 — `BULL_PEAK_THRESHOLD` /
`BEAR_PEAK_THRESHOLD`, lines 850-851) with a fired trigger, `AND action not in
_HARD_SKIP_VERDICTS` (`{"SKIP_BULLISH_FILL_BAR_AT_BEAR_ENTRY"}`, line 861 — the only verdict that
hard-blocks this check). None of safe's `GATE_KEYS` flags (`structure_veto_enabled`,
`block_bull_1100_1200`, …) appear anywhere in this function — bold's own core row already ran
those checks against **bold's own params file**, where most of them are absent or disabled.

`sig["strategies"]` construction (lines 819-823):

```python
s_bear, s_bull = bear, bull
if use_peak:
    bold = sig.get("bold") or {}
    if (bold.get("bear") or {}).get("passed") or (bold.get("bull") or {}).get("passed"):
        s_bear, s_bull = bold.get("bear") or bear, bold.get("bull") or bull
sig["strategies"] = _strategies_block(s_bear, s_bull, row.get("spy"), now, do_vwap)
```

**What happens in each case:**

| bold bear passed? | bold bull passed? | source for BOTH s_bear and s_bull |
|---|---|---|
| No | No | safe (production-faithful bear+bull, unchanged) |
| Yes | No | bold's bear+bull dicts (bold's bear carries `passed=True`; bold's bull dict rides along too, still whatever bold's own bull pass state is) |
| No | Yes | bold's bear+bull dicts (bold's bull carries `passed=True`; bold's bear rides along, still bold's own bear pass state) |
| Yes | Yes | bold's bear+bull dicts |

The condition only checks **whether bold passed EITHER side** — the swap, when it fires, always
replaces **both** `s_bear` and `s_bull` together (a populated dict is truthy, so `bold.get(x) or
y` takes bold's dict whenever `bold.get(x)` is a non-empty mapping, independent of that side's own
`passed` value). There is no per-side split and no reference anywhere in this function to which
arm will eventually consume the result.

`_strategies_block` → `_ribbon_strategy_entries` (line 484): one entry per side where
`blk.get("passed") is True`, `name="ribbon_ride"`, `quality` ELITE if a confluence/sequence
trigger is present else BASE. This list — sourced per the table above — is what **every** arm's
`_plan_from_strategies` iterates, unmodified, regardless of arm id.

---

## (d) fleet_executor.py — per-arm gates and the `plan_all` branch

### The branch (quoted exactly), `fleet_executor.py:933-936`

```python
if signal.get("strategies") is not None:
    plans = _plan_from_strategies(arm, signal, equity, params, arm_id, tiers, spot)
else:
    src = _perception_for_arm(signal, arm)
    plans = []
    for side, blk in (("P", src.get("bear") or {}), ("C", src.get("bull") or {})):
```

`_perception_for_arm` (the safe/bold role router — `fleet_executor.py:108-122`) lives **only** in
the `else` branch. Because `build_shared_signal.EMIT_STRATEGIES=True` unconditionally, `build()`
ALWAYS sets `sig["strategies"]` — an **empty list on a no-signal tick**, never `None`/absent
(`build_shared_signal.py:714`, `739`, `1327`: `sig["strategies"] = []`). So `signal.get("strategies")
is not None` is **always** true on the live signal shape, and the `if` branch always runs.
Verified live 2026-09-03 14:22 ET: a fresh read of `automation/state/fleet/shared-signal.json`
shows the `strategies` key present (type `list`, length 0 on that particular no-fire tick).

### The self-documented FIX2 comment (quoted exactly), `fleet_executor.py:494-497`

```
#   1. strategies.fired() -- INERT. build_shared_signal always emits a top-level
#      "strategies" key (:684), so plan_all always takes the FIX2 branch and fired() is
#      never called in production.
```

This is part of the "⛔ PARAMS DISARM ENFORCED AT THE ORDER CHOKE POINT (2026-08-12)" comment
block ahead of `select_plan()` — see git-history section below for the commit that introduced it
and what it was actually fixing (not this defect directly).

### `_plan_from_strategies` (`fleet_executor.py:721-774`)

Iterates `signal.get("strategies") or []` — **the same list for every arm**. Applies only:
`strategies.by_name(entry.name)` lookup (skip unknown names), `_gate_block_for_entry` (synthesizes
a `passed=True` side-block from the entry), `_gate_check(arm, blk, signal)` (the arm's OWN
selectivity), per-setup strike routing (`STRATEGY_STRIKE_TIERS`, only `vwap_reclaim_failed_break`
is special-cased), sizing tiers, recency/full-send min-sizing clamps. **Never** reads
`signal["safe"]`, `signal["bold"]`, `signal["bear"]`, or `signal["bull"]`; **never** calls
`_perception_for_arm`.

### `_gate_check` (`fleet_executor.py:599-620`) — the arm's ONLY selectivity lever

```python
g = arm.get("gate_override") or {}
min_trig = g.get("min_triggers")
...
if g.get("require_confluence_or_sequence") and not elite: return "requires confluence/sequence"
if str(g.get("min_setup_quality", "")).upper() == "EXCELLENT" and not elite: return "setup not EXCELLENT"
return None
```

Reads only `min_triggers`, `require_confluence_or_sequence`, `min_setup_quality` off the arm's own
`accounts.json` `gate_override` block. **No role/safe/bold awareness anywhere in this function.**

### `accounts.json` profile fields per arm (full read, `automation/state/fleet/accounts.json`)

| arm | cell | status | `gate_override` | `params_patch` (excl. exit_patch) | exit_patch |
|---|---|---|---|---|---|
| **safe-3** | safe x tight | active | `min_triggers:2, require_confluence_or_sequence:true` | `strike_tier_table: bold_core` | `stop_mode: structure, profit_lock_mode: trailing` |
| **safe-2** | safe x base (CONTROL) | active | `{}` | `{}` | — (core, `mcp_heartbeat`, not a `fleet_rest` arm) |
| **safe-1** | safe x loose | **retired** (2026-07-11) | `min_triggers:1` | `strike_tier_table: bold` | — |
| **risky-1** | risky x FULL-SEND | active | `full_send:true, min_triggers:2, require_confluence_or_sequence:true` (restored 2026-08-12 after accidental 2026-07-31 deletion) | `strike_tier_table: bold_core` | `tp1_premium_pct:0.5, stop_mode: structure` |
| **bold-2** | risky x base (CONTROL) | active | `{}` | `{}` | — (core, `mcp_heartbeat`) |
| **risky-3** | risky x loose | **retired** (2026-08-28) | `min_triggers:1`, `gate_params.hard_skip_verdicts: []` | `cheap_contract_qty_boost{premium_below:0.5,qty:10}, strike_tier_table: bold_core_pre_ext` | `stop_mode: premium` |

`gate_params.hard_skip_verdicts: []` (risky-3 only, live before its 2026-08-28 retirement) is a
**separate** mechanism from `gate_override`: `_effective_passed` (`fleet_executor.py:124-142`)
lets an arm opt out of `build_shared_signal`'s global `_HARD_SKIP_VERDICTS` and instead honor only
verdicts named in its own list — an empty list means it inherits none of them.

`probe_arm` (top-level accounts.json block, `enabled:true, arm_id:"risky-3"`) still names the
now-retired risky-3. Dispatch gates on the ARM's own `status=="active"` check
(`fleet_live`/`fleet_executor.run_dry`), so this is inert dead config post-retirement, **not
independently re-verified this session** — flagged for follow-up if probe-arm dispatch is ever
audited in isolation.

### Settlement / PDT / kill-switch — `finalize()` gate ordering (`fleet_executor.py:1224-1420+`)

1. HOLD plans pass through untouched.
2. **`min_entry_premium` floor** (arm's base params file) — `SKIP_MIN_PREMIUM_FLOOR`. Runs before
   `risk_gate`, not a `risk_gate` rule.
3. `_fleet_params["pdt_gate_mode"]` **forced to `"margin_pdt"`** regardless of the arm's base
   params file value — a deliberate "BLAST-RADIUS GUARD" (fleet arms don't compute the
   settled-cash/entries-used inputs `cash_settlement` mode needs).
4. `cheap_contract_qty_boost` (risky-3 only, was live pre-retirement) — raises qty, never shrinks.
5. **Tight-ladder per-entry caps** (`max_contracts_per_entry` / `max_position_dollars`, via
   `risk_gate.cap_entry_qty`) — `MAX_POSITION_CONFLICT` HOLD on deadlock, else a visible
   `"qty capped X->Y"` note (seen live today on safe-3: `"qty capped 8->5"`).
6. `_shrink_qty_to_affordable` — pct-of-equity RISK_CAP-aware shrink, independent of step 5.
7. **FLEET SETTLEMENT GATE** (`fleet_settlement_gate_enabled=true` in both params files since
   2026-08-18): `risk_gate.check_settlement` called **directly**, independent of `pdt_gate_mode` —
   settled cash + `max_same_day_roundtrips` (=4 since 2026-08-29, tightened from 5) — only runs
   when `settled_cash_available` is actually supplied (`fleet_live.run()` supplies it per-arm;
   `run_dry()`/tests do not).
8. `risk_gate.check_order` — kill switch (Rule 5), per-trade risk cap (Rule 6), legacy
   `margin_pdt` day-trade check (Rule 7 — day_trades_used_5d is still read here per step 3, even
   though FINRA repealed the underlying $25K/day-trade-count rule 2026-06-04 per `params.json`'s
   own doc), NOT_FLAT/no-add (Rule 4), `first_entry_after_stop_blocked`.
9. Rescue lanes if still no ENTER: probe (risky-3-gated by `arm_id`, arm itself now retired —
   inert), score ladder (no live arm currently carries `gate_override.score_ladder_floor` — both
   safe-3's and risky-1's/risky-3's ladders were disarmed 2026-07-27 on negative-replay evidence,
   per their own `score_ladder_doc` fields), full_send (risky-1 only, `gate_override.full_send`).

**Core accounts (safe-2, bold-2) never enter `finalize()` at all** — they're placed directly by
`heartbeat_core._execute` via `risk_gate.check_order` in **`cash_settlement`** mode (safe since
2026-07-14, bold since 2026-08-09), a structurally different call path than every fleet arm's
forced `margin_pdt` + settlement-gate-bolted-on-separately shape.

---

## (e) Exit-side ownership per arm

- **Fleet arms (safe-3, risky-1, risky-3 while active)**: `fleet_live.py` imports `exit_actuator`
  unconditionally (`import exit_actuator as ea`, line 44) and, for every cycle, registers each
  fill (`ea.register_entry`, line ~716) and runs `ea.manage_tick` (line ~980) — **not gated by any
  env flag**. Each arm's `exit_shape` is the `strategies.py` REGISTRY default, shallow-merged with
  its own `accounts.json` `params_patch.exit_patch` (`fleet_executor._exit_shape_dict`,
  `fleet_executor.py:622-654`) — this is how safe-3/risky-1 force `stop_mode:structure` and
  risky-3 forced `stop_mode:premium` while it was live.
- **Core accounts (safe-2, bold-2)**: `heartbeat_core.py` imports `exit_actuator`/`exit_manager`
  too, but exit management is gated by `GAMMA_CORE_MANAGES_EXITS` (env var, default `"0"` in code
  — `heartbeat_core.py:128`). When off, `_execute` places only the single catastrophe-floor
  bracket at entry with no active scale-out/profit-lock management; when on, the engine registers
  each fill and runs a per-tick management pass (TP1 partial, runner, profit-lock, time stop),
  live-placing only when `ARMED`. **This session did not check the live process's actual env var
  value** (no live process/env inspection performed — out of scope per this task's read-only
  constraint); the mechanism is described, not confirmed live.

---

## Git history: when did role-blind `strategies[]` sourcing enter the codebase, and was it intent?

### `build_shared_signal.py` / `EMIT_STRATEGIES`

```
git log -S"EMIT_STRATEGIES" --oneline -- automation/state/fleet/build_shared_signal.py
24bc365c 2026-07-20 feat(dojo): wire fleet arms into engine_step via build_from_rows
667217a1 2026-06-26 feat(engine): EOD 2026-06-26 — engine repairs + direction-block audit + structure-veto + trendline engine
```

`build_shared_signal.py` **did not exist** before `667217a1`
(`git cat-file -e 667217a1^:...build_shared_signal.py` → `fatal: ... exists on disk, but not in
667217a1^`). It was created **wholesale** in that one commit, already containing
`EMIT_STRATEGIES = True` and the exact `s_bear/s_bull` bold-perception-swap logic quoted above,
verbatim. `fleet_executor.py` was created in the **same** commit, same way.

The commit message (`git log -1 --format=%B 667217a1`) is entirely about engine repairs,
structure-veto, and a new trendline tool — it never mentions `build_shared_signal.py`, fleet
arms, or multi-strategy emission — and it separately says, about *other* files in the same
commit: *"SAVE untracked new engine: heartbeat_core.py + sight_beacon.py (were never
git-tracked)."* This is strong circumstantial evidence (**INFERENCE**, not proven) that this
repo's early fleet infrastructure was developed off-git and swept into version control in one
bulk snapshot commit — meaning git history cannot date the *true* authorship or design-review
process for the `strategies[]` mechanism to this commit's stated date or scope.

### `fleet_executor.py` — the "plan_all always takes the FIX2 branch" discovery

```
git log --oneline -S"strategies" -- automation/state/fleet/fleet_executor.py
e3a44956 2026-08-12 fix(fleet): move the params disarm to select_plan -- my first two placements were wrong
...
667217a1 2026-06-26 feat(engine): EOD 2026-06-26 ...
```

`e3a44956`'s full message (quoted in the JSON companion) opens: *"SELF-CORRECTION. The disarm I
shipped earlier tonight in `strategies.fired()` was INERT ON THE LIVE PATH. `plan_all` branches
on a top-level `'strategies'` key; `build_shared_signal` ALWAYS emits one (:684) ... so production
always takes the FIX2 branch and `fired()` is never called."*

**Verdict: side effect, not stated intent — for the specific defect this queue item is about.**
The commit that documents "plan_all always takes the FIX2 branch" was written the same night as a
**narrower** bug (the `vwap_continuation` strategy kept filling on risky-1/risky-3 despite being
"killed" in `params.json`, because the disarm check lived in dead code) — the author explicitly
labels it a self-correction discovered while debugging something else, not a planned design
review of the branch's scope. The **broader** consequence this session's and last session's
investigation establish — that EVERY safe-role cohort gate baked into `GATE_KEYS` (not just the
one strategy-disarm mechanism) is a no-op for every fleet arm reading `strategies[]` — is not
stated as intent anywhere found in this repo's tracked history; it was never fully characterized
until `veto-scope-safe-3.md` (this session's predecessor) and this document.

The **original**, broader design decision — defaulting `EMIT_STRATEGIES=True` so `plan_all` sees
"the FULL set, not just the single ribbon verdict the core ledger carries" — IS documented as a
stated, deliberate intent in the flag's own doc-comment, present from the first tracked commit.
What was never stated as intent is the downstream fact that this makes the safe/bold perception
router (`_perception_for_arm`) and everything gated on it (including every safe-only `GATE_KEYS`
cohort flag) **dead code on the live path** for every arm, safe-cell arms included.

---

## Ledger verifications (3 rows, independently re-read this session)

1. **Safe/bold same-tick divergence + safe-3 riding bold's pass.** `core-decisions.jsonl`,
   `core_tick_id 2026-09-03T11:06:02.738610`: `account=safe` → `verdict SKIP_BULL_1100_1200`;
   `account=bold` same tick → `verdict ENTER_BULL`, `action PLACED`. Second tick,
   `core_tick_id 2026-09-03T11:21:02.576928`: `account=safe` → `SKIP_STRUCTURE_VETO` ("price
   structure is 'downtrend'"); `account=bold` same tick → `ENTER_BULL` (`action
   SKIP_MIN_PREMIUM_FLOOR` on bold's OWN order, but `verdict:ENTER_BULL` is what
   `_bold_passed_blocks_from_row` reads). `automation/state/fleet/safe-3/decisions.jsonl` carries
   rows at these EXACT `core_tick_id`s with `action:ENTER_BULL, placed:true`, broker order ids
   `8a8c237c…`/`d6d0b3f8…`, matching `fills-ledger.jsonl` fills at 11:07:15 ($1.17×5) and
   11:22:07 ($0.74×5).
2. **risky-3 retirement is live-enforced.** `automation/state/fleet/risky-3/decisions.jsonl`'s
   last row is `core_tick_id 2026-08-28T15:53:01.404946` / `ts_et 2026-08-28T15:54:06` — no rows
   on or after 2026-09-03 (or any date after 08-28).
3. **`strategies` key is live-present today.** Fresh read of
   `automation/state/fleet/shared-signal.json` at the 14:22 ET tick: keys include `strategies`
   (type `list`, length 0 on that no-fire tick) — confirms `EMIT_STRATEGIES=True` is not just a
   code default but the actual on-disk artifact the live fleet task reads every minute.

---

## Facts vs inference (summary)

**FACT** (source-code line-verified this session): filter counts and defaults (§a); which params
file each core account reads (§b); `structure_veto_enabled`/`block_bull_1100_1200` divergence
between the two params files (§b); `plan_all`'s branch condition and that it is unconditionally
true on the live signal shape (§d, corroborated by a fresh shared-signal.json read); `_gate_check`
has no role-awareness (§d); the `finalize()` gate ordering (§d); `fleet_live.py`'s unconditional
exit-actuator wiring vs `heartbeat_core.py`'s env-flag-gated one (§e); all 3 ledger rows above.

**INFERENCE** (stated as such, not proven): the "bulk pre-existing-code commit" read of
`667217a1` (circumstantial: file non-existence before the commit + commit-message/content
mismatch + an explicit same-commit note about other untracked files — no reflog/stash search was
performed to try to recover an earlier state); the classification of role-blind `strategies[]`
sourcing as a "side effect" rests on the `e3a44956` commit message's own framing ("SELF-CORRECTION
... was INERT ON THE LIVE PATH") plus the absence of any earlier commit message discussing the
role-blindness consequence — this session did not exhaustively grep every commit message in the
repo's history for a possible earlier, undiscovered mention.

**UNVERIFIED / out of scope this session**: `fleet_executor.py:1543`'s second call site for
`_perception_for_arm` was located but not traced — whether it is reachable on any live path is
unknown, flagged for follow-up. `GAMMA_CORE_MANAGES_EXITS`/`GAMMA_CORE_ARMED`'s actual runtime
values were not checked (no live process/env inspection — read-only constraint). `probe_arm`
naming the retired risky-3 was read but its dispatch-gating-on-arm-status claim was not
independently re-traced beyond locating the `status=="active"` check description already in
`accounts.json`'s own doc fields.

---

## What this does NOT resolve

This is a code-truth table, not a should-we-fix-it verdict. It does not re-open the "should
`structure_veto_enabled`/GATE_KEYS cohort flags be made to bind fleet arms" question — that is a
kill-type-reduction / expansion decision requiring a prereg under the current config freeze
(scoring window through 2026-10-30, kill-type reductions permitted 2026-09-29+ with a prereg per
this task's hard constraints), not something this investigation ships.

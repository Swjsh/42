# VETO-SCOPE-SAFE-3-VERIFY — does safe-3 inherit safe-2's SKIP_STRUCTURE_VETO?

Stamp: 2026-09-03, ~13:20 ET (market hours), read-only investigation. Answers queue item
VETO-SCOPE-SAFE-3-VERIFY. Every artifact below was read this session; nothing carried over.

## Verdict up front

**NO — in the code path actually running live today, safe-3 does NOT inherit safe-2's
`SKIP_STRUCTURE_VETO` (or `block_bull_1100_1200`) block.** Evidence (A) in the prompt —
`analysis/recommendations/structure-veto-lift-package-2026-09-05/README.md` §1b, which traces
`fleet_executor._perception_for_arm` + `build_shared_signal.py`'s `sig["safe"]` construction —
describes **real code that is dead on the production path**. `fleet_executor.plan_all` only
calls that safe/bold-role-routed code in its `else` branch, taken **only when
`signal.get("strategies") is None`**. `build_shared_signal.py` sets `EMIT_STRATEGIES = True`
(line 293) and the live `shared-signal.json` on disk right now (13:18 ET tick) carries a
non-null `strategies` key — confirming the `else` branch never fires in production. This exact
gap is **already self-documented in the codebase** from a prior incident
(`fleet_executor.py` lines ~495-497, 2026-08-12, re: the `vwap_continuation` disarm gap):

> "`strategies.fired()` -- INERT. build_shared_signal always emits a top-level `"strategies"`
> key (:684), so `plan_all` always takes the FIX2 branch and `fired()` is never called in
> production."

Today's ledger reproduces that exact defect class for `structure_veto_enabled` /
`block_bull_1100_1200`: safe-3 placed **live entries on the identical `core_tick_id`** where
safe-2's own core row was blocked by both gates (quoted below). Evidence (B) in the prompt is
correct and is the discriminating signal; evidence (A)'s mechanism trace stopped one layer too
early — it verified how `sig["safe"]` is built and how `_perception_for_arm` would route to it,
but never checked whether `plan_all` actually calls into that code at all on the live signal
shape. It doesn't.

---

## 1. The mechanism, traced end-to-end in code this session

### 1a. `plan_all` branches on `signal.get("strategies")` — `automation/state/fleet/fleet_executor.py:933-935`

```python
if signal.get("strategies") is not None:
    plans = _plan_from_strategies(arm, signal, equity, params, arm_id, tiers, spot)
else:
    src = _perception_for_arm(signal, arm)
    ...
```

`_perception_for_arm` (the safe/bold role router the README's §1b cites) lives **only in the
`else` branch**. `_plan_from_strategies` (`fleet_executor.py:721-774`) never calls
`_perception_for_arm`, never reads `signal["safe"]` or `signal["bold"]`, and never reads
`signal["bear"]`/`signal["bull"]` — it iterates `signal.get("strategies") or []` directly, the
**same list for every arm**, and applies only `_gate_check` (arm's own selectivity: min_triggers /
confluence-or-sequence / min_setup_quality — no role/perception logic at all, confirmed reading
`fleet_executor.py:599-620`) plus sizing.

### 1b. `EMIT_STRATEGIES = True` is the confirmed live default — `build_shared_signal.py:293`

```python
EMIT_STRATEGIES = True
```

Confirmed against the actual production artifact, not just the source default: `python -c` read
of `automation/state/fleet/shared-signal.json` (the file the live fleet task writes/reads every
tick) at the 13:18 ET tick this session shows key `"strategies"` present (`type list`, currently
empty because no strategy fired that tick — but the key exists, which is the branch condition).

### 1c. How `sig["strategies"]` is populated — `build_shared_signal.py:802-820`

```python
s_bear, s_bull = bear, bull
if use_peak:
    bold = sig.get("bold") or {}
    if (bold.get("bear") or {}).get("passed") or (bold.get("bull") or {}).get("passed"):
        s_bear, s_bull = bold.get("bear") or bear, bold.get("bull") or bull
sig["strategies"] = _strategies_block(s_bear, s_bull, row.get("spy"), now, do_vwap)
```

`bear`/`bull` here are derived from the **safe** core row (`row = _latest_today_decision(today,
core_tick_id=_core_tick_id)`, and `_latest_today_decision`'s default is `account="safe"` —
confirmed at `build_shared_signal.py:238`). But whenever the **bold** row's `_bold_passed_blocks`
(`build_shared_signal.py:628-651`, itself sourced from `_bold_passed_blocks_from_row` at line
584) says bull (or bear) passed — and bold's pass check is a **scoring-peak check keyed on
bold's own `action` against `_HARD_SKIP_VERDICTS`, not a literal `action == "ENTER_BULL"` string
match, and not gated on safe's structure-veto flag at all** — `s_bear`/`s_bull` are silently
swapped to bold's block, and **that's what every arm's `strategies[]` list is built from**, safe
arms and bold arms alike. There is no per-arm role split in this construction; it is one shared
list.

### 1d. Bold's own config makes this override load-bearing on structure-veto ticks

`automation/state/aggressive/params.json:52-53`:

```
"structure_veto_enabled": false,
"_structure_veto_enabled_doc": "EXPLICIT, not defaulted (2026-08-12) ... Live proof: over
25,821 ledger rows SKIP_STRUCTURE_VETO fired 116 times for account=safe and ZERO times for
bold."
```

`block_bull_1100_1200` is likewise **absent** from `automation/state/aggressive/params.json`
(grep confirmed zero matches) — present only in `automation/state/params.json:215` (safe). So on
any tick where safe's core engine blocks a bull entry via either gate, bold's core engine (same
underlying market read, independent gate config) very often still emits `ENTER_BULL`, and
`sig["strategies"]` gets built from bold's passing block instead of safe's blocked one — for
**every** arm reading `signal["strategies"]`, which per §1a/1b is every arm, always.

---

## 2. Ledger proof: safe-3 traded through both gates today, on the exact blocked ticks

### 2a. `automation/state/core-decisions.jsonl` — account=safe, quoted verbatim

```
{"ts_et": "2026-09-03T11:06:03", "account": "safe", "verdict": "SKIP_BULL_1100_1200",
 "action": "SKIP_BULL_1100_1200", "side": "C", "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
 "reason": "blocked by entry gate block_bull_1100_1200",
 "core_tick_id": "2026-09-03T11:06:02.738610", "spy": 770.445}

{"ts_et": "2026-09-03T11:21:03", "account": "safe", "verdict": "SKIP_STRUCTURE_VETO",
 "action": "SKIP_STRUCTURE_VETO", "side": "C", "setup": null,
 "reason": "structure-veto: C entry blocked — price structure is 'downtrend' (wrong-way entry)",
 "core_tick_id": "2026-09-03T11:21:02.576928", "spy": 772.02}

{"ts_et": "2026-09-03T11:22:03", "account": "safe", "verdict": "SKIP_STRUCTURE_VETO",
 "action": "SKIP_STRUCTURE_VETO", "side": "C", "setup": null,
 "reason": "structure-veto: C entry blocked — price structure is 'downtrend' (wrong-way entry)",
 "core_tick_id": "2026-09-03T11:22:02.766332", "spy": 772.02}
```

### 2b. Same ticks, account=bold — the row that actually feeds `sig["strategies"]` on these ticks

```
{"ts_et": "2026-09-03T11:06:04", "account": "bold", "verdict": "ENTER_BULL", "action": "PLACED",
 "side": "C", "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
 "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)",
 "core_tick_id": "2026-09-03T11:06:02.738610", "spy": 770.445}

{"ts_et": "2026-09-03T11:21:04", "account": "bold", "verdict": "ENTER_BULL",
 "action": "SKIP_MIN_PREMIUM_FLOOR", "side": "C", "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
 "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)",
 "core_tick_id": "2026-09-03T11:21:02.576928", "spy": 772.02}

{"ts_et": "2026-09-03T11:22:04", "account": "bold", "verdict": "ENTER_BULL",
 "action": "SKIP_MIN_PREMIUM_FLOOR", "side": "C", "setup": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
 "reason": "BULLISH_RECLAIM_RIDE_THE_RIBBON passed scoring + all entry gates (tier ELITE)",
 "core_tick_id": "2026-09-03T11:22:02.766332", "spy": 772.02}
```

Bold's own `action` (`PLACED`/`SKIP_MIN_PREMIUM_FLOOR`) is bold-2's own order-placement/floor
outcome and is irrelevant to the shared-signal construction — `_bold_passed_blocks_from_row`
keys off `verdict`/`action` against `_HARD_SKIP_VERDICTS` for the **pass/fail** determination,
and `SKIP_MIN_PREMIUM_FLOOR` is not a hard-skip verdict, so `bull_peak=True` there. `verdict:
ENTER_BULL` on all three ticks is the load-bearing field.

### 2c. `automation/state/fleet/safe-3/decisions.jsonl` — safe-3's own arm-level ledger, quoted verbatim

```
{"ts_et": "2026-09-03T11:07:05.820991-04:00", "core_tick_id": "2026-09-03T11:06:02.738610",
 "signal_status": "ok", "action": "ENTER_BULL", "side": "C",
 "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
 "reason": "ribbon_ride C (ELITE); qty capped 8->5: tight-ladder max_contracts_per_entry",
 "strike": 770, "qty": 5, "premium": 1.15}

{"ts_et": "2026-09-03T11:22:06.284749-04:00", "core_tick_id": "2026-09-03T11:21:02.576928",
 "signal_status": "ok", "action": "ENTER_BULL", "side": "C",
 "setup_name": "BULLISH_RECLAIM_RIDE_THE_RIBBON",
 "reason": "ribbon_ride C (ELITE); qty capped 8->5: tight-ladder max_contracts_per_entry",
 "strike": 772, "qty": 5, "premium": 0.73}
```

Each safe-3 row's `core_tick_id` is byte-identical to the corresponding **safe** core row's
`core_tick_id` (`2026-09-03T11:06:02.738610` and `2026-09-03T11:21:02.576928` respectively) —
i.e. safe-3's decision is pinned to the exact tick where safe-2's own engine returned
`SKIP_BULL_1100_1200` / `SKIP_STRUCTURE_VETO`. safe-3 entered `ENTER_BULL` anyway, both times.

The `11:22:03` `SKIP_STRUCTURE_VETO` tick (core_tick_id `2026-09-03T11:22:02.766332`) is not
independently re-tested by safe-3 because safe-3 was already in a fresh position from the
`11:21:02.576928` tick's fill one tick earlier — the `11:23:06` row shows `"reason": "fleet
settlement gate: ... 4 same-day entries already placed >= sanity cap 4"`, a different (and also
non-safe-role) gate, not a structure-veto rescue-miss.

### 2d. `automation/state/fills-ledger.jsonl` — the two live fills this predicts, quoted verbatim

```
{"arm": "safe-3", "order_id": "8a8c237c-a1ba-4c59-824d-ba3b51f1d8db",
 "symbol": "SPY260903C00770000", "side": "buy", "qty": 5.0, "price": 1.17,
 "ts_et": "2026-09-03T11:07:15.548666", "attribution": "engine"}

{"arm": "safe-3", "order_id": "d6d0b3f8-ccf0-4df2-9d2a-a035c5664f5b",
 "symbol": "SPY260903C00772000", "side": "buy", "qty": 5.0, "price": 0.74,
 "ts_et": "2026-09-03T11:22:07.262113", "attribution": "engine"}
```

Both fills correspond 1:1 to the `ENTER_BULL` rows in §2c — safe-3 filled real (paper) orders on
ticks where safe-2's own engine was gated OFF by `block_bull_1100_1200` and `structure_veto_enabled`
respectively. This is the discriminating ledger evidence named in the task, and it holds up.

---

## 3. Which gates actually bind safe-3

- **`structure_veto_enabled` (`automation/state/params.json:314`) and `block_bull_1100_1200`
  (`automation/state/params.json:215`) bind ONLY safe-2's own order placement**, i.e. only the
  `account="safe"` row's `action`/`verdict` in `core-decisions.jsonl` and whatever downstream
  reads that row directly (safe-2's own live/paper order). They do **not** bind safe-3, because
  safe-3's entries are sourced through `fleet_executor.plan_all → _plan_from_strategies →
  signal["strategies"]` (§1a), and that list is built from **whichever of (safe, bold) perception
  passed** (§1c), with bold's config running `structure_veto_enabled: false` and no
  `block_bull_1100_1200` key at all (§1d) — independent of safe's flag. Today's ledger (§2)
  confirms safe-3 already trades through both gates live, right now, unmodified.
- **What DOES bind safe-3**: its own `accounts.json` `gate_override` selectivity
  (`_gate_check`: `min_triggers`, `require_confluence_or_sequence`, `min_setup_quality` — none of
  which reference safe/bold role), its own sizing/strike-tier table, `risk_gate.check_order`, the
  fleet settlement cap (`max_same_day_roundtrips`, seen firing at `11:23:06` above),
  one-position-open dedup, and `strategies._disarmed_setups()` in `select_plan`. These are
  arm-level, not safe-role-level, controls.

---

## 4. Effect of flipping `automation/state/params.json:314` (`structure_veto_enabled`) — corrected scope

**Flipping the key to `false` changes safe-2's own core-engine verdict/order placement (direct,
as the README's §1a already established correctly). It does NOT change safe-3's trade
population**, because on any tick where safe's flag currently causes a `SKIP_STRUCTURE_VETO`
block, safe-3 is *already* unblocked today via the bold-perception override in §1c/1d — the flip
would make safe's own top-level `bear`/`bull` block pass directly instead of via the bold
override, but the **net result for `signal["strategies"]`'s bull-side pass state on that tick is
the same either way** (bold already passes it now; safe would also pass it after the flip). The
specific score/trigger/`trigger_level_exact` values feeding the entry plan could shift by a few
cents (safe's own block vs. bold's, once the override path is no longer taken) but the gate that
the README's §1b treats as the scope-determining mechanism for safe-3 is not, in the live
`_plan_from_strategies` path, actually gating safe-3 at all today.

**This corrects the README's §1b "Net scope statement"** ("this flip changes trade population
for `safe-2` (direct) and `safe-3` (inherited, same tick, same direction, never independently
blocked or rescued)") — that document explicitly flagged this as unverified ("I could not
empirically re-verify this against safe-3's own ledger... this is a source-code-verified
mechanism (FACT), not a ledger-cross-checked one"), and the missing ledger cross-check is exactly
what breaks the conclusion: safe-3's ledger *does* log the positive case (`ENTER_BULL` rows), and
today it shows entries on ticks the README predicted would be blocked.

---

## 5. Go-live gate criterion-5 (safe-3, `automation/state/prod-shadow-designation.json`)

`automation/state/prod-shadow-designation.json` names **`safe-3`** as the designated
`PROD-SHADOW` arm for criterion 5 (window `2026-09-01..2026-10-30`, min 20 scored days), used by
`go_live_gate.py`'s `prod_shadow_criterion()`. Per §4, **flipping
`automation/state/params.json:314` would NOT change safe-3's trade population or its scored-day
count**, because safe-3's entries already route around that flag via the shared `strategies[]`
list sourced from bold's independent (already-`false`) perception. The flip is scope-isolated to
safe-2's own ledger/order-placement outcomes; it does not touch the go-live gate's criterion-5
evidence stream.

---

## 6. What this does NOT resolve

This report is purely a scope/mechanism verification — it does not re-open or re-score the
"should the veto be lifted" question the structure-veto-lift-package README raises (§3-4 there,
the contested defect-vs-expansion classification and the two disagreeing instruments). It also
does not audit whether `sig["strategies"]`'s silent safe/bold-role-blind construction is itself a
defect worth fixing (arguably yes — it means **every** safe-role cohort gate baked only into
`automation/state/params.json`'s `GATE_KEYS` is currently a no-op for every fleet arm reading
`strategies[]`, not just `structure_veto_enabled`/`block_bull_1100_1200` — but that is a new,
broader finding outside this ticket's question and is flagged here for a separate follow-up, not
fixed).

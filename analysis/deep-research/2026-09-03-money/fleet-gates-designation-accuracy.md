# G4 — DOES THE PROD-SHADOW-DESIGNATION TEXT DESCRIBE WHAT SAFE-3 ACTUALLY TRADES?

Stamp: 2026-09-03, ~13:30-14:30 ET (market hours), read-only. Answers queue item
G4-DESIGNATION-ACCURACY. Builds directly on `veto-scope-safe-3.md` (this session, mechanism +
2 live ticks) and the concurrent `fleet-gates-ledger-binding-check.md` (sibling session, full
ledger join, tick-level leak rates) — neither is re-litigated, both are extended with new,
independently-derived evidence (the day-level leak-dependency check in §4 has not been run
anywhere else this session).

## Verdict up front

1. **The `gate_override` text ("tight gate: min_triggers=2, require_confluence_or_sequence")
   is accurate and IS real, applied, arm-level selectivity** — 502 refusals in safe-3's own
   ledger this session alone, quoted below. **But the designation's implicit framing — "safe-3"
   / "safe x tight" / "safe sizing" — implies safe's COHORT entry gates (structure_veto_enabled,
   block_bull_1100_1200, and every other `params.json` GATE_KEYS entry) also bind safe-3. They do
   not**, and have not since before safe-3's first-ever trade.
2. **No go-live or fidelity instrument reads or asserts safe-3's gate identity.** All four named
   instruments score ledger rows (fills/PnL), not config. `go_live_gate.py` carries the
   `profile_summary` string through verbatim into its report but never validates it against the
   code that produced the trades — it is display text, not a load-bearing input to any pass/fail
   math.
3. **Honest description (§3) and suggested designation text are below.**
4. **The 20-scored-day bar very likely survives a 09-29 gate-inheritance fix.** 1 scored day
   banked (verified through the actual instrument), 19 needed from 40 remaining trading days —
   and, more importantly, a new day-level check run this session found **zero** historical dates
   (of 12, since 2026-08-06) where the leak was safe-3's *only* source of that day's entry. The
   fix would probably cost some entries and some dollars; the evidence says it would not cost
   scored days.

---

## 1. Is the profile_summary text accurate about what binds safe-3?

**`automation/state/prod-shadow-designation.json`:**
> "FLEET-TIGHT-S (T20H): safe sizing, **tight gate (min_triggers=2,
> require_confluence_or_sequence:true)**, exit_patch{stop_mode:structure,
> profit_lock_mode:trailing}, strike_tier_table=bold_core (ATM under $2K)."

**`automation/state/fleet/accounts.json`, safe-3's `gate_override` (verbatim):**
```json
"gate_override": { "min_triggers": 2, "require_confluence_or_sequence": true }
```
`"cell": "safe x tight"`, `"note": "SAFE sizing, TIGHT gate. Most selective safe arm..."`

### 1a. The gate_override IS real and IS applied — mechanism

`automation/state/fleet/fleet_executor.py:599-620`, `_gate_check` (quoted in full):
```python
def _gate_check(arm, blk, signal) -> Optional[str]:
    """The arm's SELECTIVITY gate (triggers / quality)..."""
    g = arm.get("gate_override") or {}
    min_trig = g.get("min_triggers")
    triggers = blk.get("triggers_fired", []) or []
    if min_trig is not None and len(triggers) < int(min_trig):
        return f"{len(triggers)} triggers < {min_trig}"
    elite = _is_elite(blk)
    if g.get("require_confluence_or_sequence") and not elite:
        return "requires confluence/sequence"
    ...
```
Called from **both** branches of `plan_all` — `_plan_from_strategies` (fleet_executor.py:743,
the FIX2/production path: `gate_reason = _gate_check(arm, blk, signal)`) and the legacy
`else` branch — so unlike the safe/bold cohort gates (§1b), this one is not branch-dependent.
It runs on every tick regardless of which perception produced the candidate entry.

### 1b. Ledger proof the gate_override actually refuses trades — 3 rows, quoted verbatim

`automation/state/fleet/safe-3/decisions.jsonl` (502 total refusals this way: 284
`"requires confluence/sequence"` + 218 `"1 triggers < 2"`):

```
{"core_tick_id": "2026-09-03T10:24:02.595671", "action": "HOLD", "side": "C",
 "setup_name": "VWAP_CONTINUATION", "reason": "gate: requires confluence/sequence"}

{"core_tick_id": "2026-09-03T10:30:03.934929", "action": "HOLD", "side": "C",
 "setup_name": "VWAP_CONTINUATION", "reason": "gate: requires confluence/sequence"}

{"core_tick_id": "2026-09-03T13:55:02.903251", "action": "HOLD", "side": "P",
 "setup_name": "BEARISH_REJECTION_RIDE_THE_RIBBON", "reason": "gate: 1 triggers < 2"}
```

**This part of the text is not misleading.** The arm-level gate is real, live, and the single
largest source of HOLD verdicts in safe-3's own ledger.

### 1c. What the text does NOT say, and what a reader would reasonably infer anyway

CLAUDE.md's own doctrine (Account context section) states arms "differ ONLY by sizing, **gates**,
and stop." Given that framing plus the designation's own vocabulary — arm named `safe-3`,
`display_name: FLEET-TIGHT-S`, `cell: "safe x tight"`, profile_summary opening with "safe
sizing, tight gate" — the natural reading is: *safe-3 = safe's cohort-level entry-gate set
("safe" half) with additional arm-level selectivity layered on top ("tight" half)*. That reading
is false on the live path, established this session (`veto-scope-safe-3.md` §1, reproduced
briefly here because it is load-bearing for this question too):

- `fleet_executor.plan_all` (fleet_executor.py:933-935) takes the `_plan_from_strategies`
  branch whenever `signal.get("strategies") is not None` — true on every live tick, because
  `build_shared_signal.py:293` sets `EMIT_STRATEGIES = True`.
- `_plan_from_strategies` never calls `_perception_for_arm` and never reads
  `signal["safe"]`/`signal["bold"]` directly — it reads the single shared `signal["strategies"]`
  list, identical for every fleet arm.
- `build_shared_signal.py:802-820` builds that list from **safe's** block by default, but swaps
  to **bold's** block whenever bold's own perception separately passed — independent of whether
  safe's cohort gates (`structure_veto_enabled`, `block_bull_1100_1200`, etc.) blocked safe.
  Bold's own config runs `structure_veto_enabled: false` and carries no `block_bull_1100_1200`
  key at all.
- **New this session — how long this has been true:** `git log -S'EMIT_STRATEGIES = True'` and
  `git log -S'signal.get("strategies") is not None'` both land on the **same commit**,
  `667217a`, **2026-06-26** — three days *before* safe-3's first-ever fill (2026-06-29,
  confirmed against `automation/state/fills-ledger.jsonl`). **The shared-signal mechanism is not
  a recent regression relative to safe-3's track record — it predates every single trade in it.**
  Every number in the designation's own `profile_summary` ("n_days=26, +$841, WR 30.5%") and in
  the handoff doc's §0.1 comparator ("n=59, +$841, WR 30.5%") was earned entirely under this
  mechanism, never under a regime where safe's cohort gates cleanly bound safe-3.

### 1d. The size of the gap (from the sibling session's ledger join, cited for completeness)

`fleet-gates-ledger-binding-check.md` (this same directory, 2026-09-03) quantifies it at the
tick level: aggregating every safe-cohort `SKIP_*` gate since 2026-08-06, safe-3 entered anyway
on **11 of 133 qualifying ticks (8.3%)**, across 12 distinct dates — "real but partial, not
total," their words, independently reproduced by my own query in §4 below (same 133/12 figures).

**Answer to 1, stated plainly:** the gate_override half of the text is accurate and verified
live. The "safe"-cohort half is not stated explicitly, but is implied by the arm's own name,
cell label, and CLAUDE.md's "arms differ only by sizing/gates/stop" doctrine — and that implied
half is false on the live path, and has been false for safe-3's entire trading history.

---

## 2. Does any go-live/fidelity instrument assume safe-3 runs the safe gate set?

Checked all four named instruments plus the "walker anchor" tooling — none of them read or
assert safe-3's gate identity. All are ledger/PnL scorers, not config validators.

| Instrument | What it reads | Gate-identity assumption? |
|---|---|---|
| `go_live_gate.py` `prod_shadow_criterion()` | `analysis/trades-enriched.jsonl` rows where `arm == cfg["arm"]` and `attribution=="engine"`; runs `statistical_criterion()` (bootstrap PF CI) on realized P&L. Carries `cfg.get("profile_summary")` into the report **verbatim, display-only** (line 826) — never parsed, never checked against fleet_executor/accounts.json. | **No.** Scores whatever safe-3 actually traded, regardless of what produced it. The `profile_summary` text is propagated, not verified. |
| `prod_shadow.py` | `analysis/trades-enriched.jsonl` filtered to **`arm=="safe-2"`** (`DEFAULT_BASE_ARM`). Explicitly disclaims: `"not_criterion_5": True`, `"see_instead": "...go_live_gate.prod_shadow_criterion"`, and a top-of-file `NAME COLLISION WARNING`. | **N/A — doesn't touch safe-3 at all**, despite the similar name. Confirmed by grep: zero `safe-3`/`safe_3` references in the file. |
| `first_live_day_review.py` | Grep for gate/cohort/`min_triggers`/`structure_veto`/`profile_summary`: zero matches. Reads `queue.md` GATE-BLOCKING markers (a different, textual meaning of "gate" — open work items, not entry filters) and portfolio/reconciliation data. | **No.** |
| `live_readiness.py` | Same grep: zero matches on gate identity or `safe-3`. Scores CLAUDE.md's 4-condition per-arm readiness bar from realized ledger data; explicitly "arms nothing, changes no gate, edits no [state]." | **No.** |
| `walker_full_population_anchor.py` / `WALKER-FULL-POPULATION-ANCHOR-2026-09-03.md` ("walker anchors") | Pulls `analysis/trades-enriched.jsonl` rows for `arm in {safe-2,bold-2,safe-3,risky-1}` (go-live gate's `ACTIVE_ARMS`) and re-walks **exit** trigger/timing fidelity against 1-min option bars via `exit_manager_walk`. Entirely about exit-side magnitude fidelity (backtest-vs-live P&L reconciliation), not entry gates. | **No.** Filters by the `arm` tag on each row; carries no assumption about which entry gates produced that row. |

**Answer to 2:** no. The only place safe-3's gate identity is even *described* is the
designation file's own `profile_summary` string, and the one place that string is *read* by
code (`go_live_gate.py:826`) is a pass-through into a report field, never an input to any
pass/fail computation. The pass/fail math (criterion 1 and criterion 5 alike) is 100% ledger-
derived and therefore already reflects reality (including the leak) whether or not the prose
description is accurate — the risk from the inaccurate text is to **human readers of the
designation** (J, or a future session, concluding "safe-3 = safe's vetoes + tighter" and reasoning
about its risk/edge profile on that false premise), not to the gate's own arithmetic.

---

## 3. The honest description

**One paragraph, as requested:**

> safe-3 trades the fleet's shared `strategies[]` signal — built each tick from whichever of the
> **safe** or **bold** core perceptions independently passed, defaulting to safe's block but
> silently substituting bold's whenever bold passed and safe didn't (`build_shared_signal.py:
> 802-820`) — filtered through exactly one arm-level selectivity gate (`gate_override:
> min_triggers>=2 AND require_confluence_or_sequence`, real and verified refusing trades: 502
> HOLDs this session alone), sized at safe-tier caps, priced off the `bold_core` (ATM) strike
> table, and exited under a structure-stop/trailing-lock patch. It does **not** run safe's own
> cohort entry-gate set (`structure_veto_enabled`, `block_bull_1100_1200`, and the rest of
> `params.json`'s `GATE_KEYS`) as an independent filter — those bind only safe-2's own core
> order-placement decision, and safe-3 rides through them on the minority of ticks (~8%,
> 11/133 since 2026-08-06) where bold's own, structurally looser gate set (no structure-veto, no
> time-of-day block) happened to pass instead. This has been true of every trade in safe-3's
> history, including the full-sample and window figures the designation itself cites, because the
> mechanism (`EMIT_STRATEGIES=True` + the `strategies`-branch in `fleet_executor.plan_all`)
> shipped 2026-06-26, three days before safe-3's first trade.

**What the designation text should say instead** (drop-in replacement for `profile_summary`):

> "FLEET-TIGHT-S (T20H): safe sizing, **arm-level selectivity gate only** (min_triggers=2,
> require_confluence_or_sequence:true) — **does NOT independently run safe's cohort entry-gate
> set** (structure_veto_enabled, block_bull_1100_1200, etc.); safe-3 trades the fleet's shared
> strategies[] signal, which defaults to safe's block but substitutes bold's whenever only bold
> passes (~8% of entries since 2026-08-06, see fleet-gates-ledger-binding-check.md), exit_patch
> {stop_mode:structure, profit_lock_mode:trailing}, strike_tier_table=bold_core (ATM under $2K).
> Full-sample (as of 2026-09-01): n_days=26, +$841 total, WR 30.5% — earned entirely under this
> shared-signal mechanism, not a clean safe-cohort-gated sample."

---

## 4. If safe-3 inherited safe's cohort gates on 2026-09-29, does the 20-day bar survive?

### 4a. Where the window stands today (verified, not estimated)

Ran `go_live_gate.prod_shadow_criterion()` directly against the on-disk ledger this session
(read-only — `load_ledger_rows()`, no `refresh_trades_enriched()` call, **zero writes**):

```
days_scored: 1        days_needed: 20      status: INSUFFICIENT_DAYS
note: "1/20 scored trading days for arm 'safe-3' in 2026-09-01..2026-10-30."
```

That 1 day is 2026-09-02 (the last date `trades-enriched.jsonl` has fully processed). Window
day-1, 2026-09-01, had **zero** safe-3 fills (`fills-ledger.jsonl` confirms no safe-3 rows dated
2026-09-01 — a normal "sitting out" day, per doctrine). Today, 2026-09-03, already carries 8
real safe-3 fills across 4 round trips (`fills-ledger.jsonl`, 09:42-11:34 ET) but is **not yet**
reflected in `trades-enriched.jsonl` (still mid-session, `market_hours=True` at the 14:30 ET
stamp) — it will very likely become the window's 2nd scored day at EOD processing, but that is
UNVERIFIED as of this report.

**Calendar (Labor Day 2026-09-07 excluded, no other market holiday in range):**

| Segment | Trading days |
|---|---:|
| Full window, 2026-09-01..2026-10-30 | **43** (matches the designation file's own stated arithmetic) |
| Elapsed so far, 09-01..09-03 | 3 |
| Remaining after today, 09-04..10-30 | 40 |
| Pre-hypothetical-fix, 09-01..09-28 | 19 |
| Post-hypothetical-fix, 09-29..10-30 | 24 |

(2026-09-29 used as the fix date because it is the earliest date CLAUDE.md's freeze rule permits
a kill-type reduction to ship, with a prereg — not because any fix is actually planned.)

### 4b. Participation-rate arithmetic (the naive framing, and its flaw)

The designation file's own justification for the 43-day window uses safe-3's historical
participation: 26/44 trading days filled, 2026-06-29..2026-08-28 = **59%**. Naively:
19 pre-fix days × 59% ≈ 11 scored days banked by 09-28; the remaining 24 post-fix days would then
need ≥ 9 more scored days, i.e. a post-fix participation rate ≥ **9/24 = 37.5%** — comfortably
below even the fleet's current worst-arm floor (bold-2, 47%, per the designation file), so the
naive read is "survives with room to spare."

**The flaw, stated honestly:** that 59% baseline is not a clean pre-leak number to project
forward from — per §1c, the leak mechanism has been live for safe-3's *entire* history, so 59%
already contains whatever inflation the leak provides, and the naive math silently assumes the
post-fix rate equals a number earned partly *because of* the thing being removed.

### 4c. The stronger check — does the leak ever cause a day to score at all? (new this session)

Rather than guess a post-fix rate, I joined `core-decisions.jsonl` (`account=safe` gated,
`account=bold` `verdict` ENTER on the same `core_tick_id`, since 2026-08-06 — independently
reproduces the sibling session's 133 ticks / 12 distinct dates exactly) against safe-3's own
`decisions.jsonl` **per date**, splitting each day's ENTER-type decisions into "via a leak tick"
vs "via any other tick":

```
2026-08-07: 3 entries total | 1 via leak | 2 non-leak
2026-08-11: 0 entries total | 0 via leak | 0 non-leak
2026-08-12: 4 entries total | 0 via leak | 4 non-leak
2026-08-13: 3 entries total | 1 via leak | 2 non-leak
2026-08-17: 0 entries total | 0 via leak | 0 non-leak
2026-08-18: 0 entries total | 0 via leak | 0 non-leak
2026-08-19: 3 entries total | 1 via leak | 2 non-leak
2026-08-20: 0 entries total | 0 via leak | 0 non-leak
2026-08-21: 4 entries total | 3 via leak | 1 non-leak
2026-08-27: 2 entries total | 1 via leak | 1 non-leak
2026-09-02: 4 entries total | 2 via leak | 2 non-leak
2026-09-03: 4 entries total | 2 via leak | 2 non-leak

Dates where safe-3's ONLY entry that day came via a leak tick: NONE (0 of 12).
```

Every one of the 12 dates that carried a leak-eligible tick **also** carried at least one
independently-sourced (non-leak) safe-3 entry that same day. Caveat: this measures *ENTER-type
decisions* (action ∈ {ENTER_BULL, ENTER_BEAR, PLACED}), the closest available proxy for "would
this day have scored" — not the exact `trades-enriched.jsonl` FIFO-fill criterion
`prod_shadow_criterion()` actually uses, and the sample is bounded to the 34 trading days since
2026-08-06 (not safe-3's full 06-29-start history, and not the future post-fix regime, which
could behave differently). It also uses the inclusive `SKIP_*` superset (not only the named
GATE_KEYS), which makes this a conservative (harder-to-clear) test, not a lenient one.

### 4d. Answer to 4

**On present evidence, the 20-scored-day bar very likely survives a 09-29 gate-inheritance
fix.** Two independent supports: (a) the window carries structural slack — 43 total trading days
against a 20-day bar tolerates up to ~53% no-fill days, far more cushion than either the naive
37.5%-required-rate math or the historical 59%/47% participation range implies is needed; (b) the
day-level check in §4c found the leak has **never once**, in the observed window, been the sole
reason a day scored for safe-3 — every leak-affected date already had an independent entry.
This is **not a proof** — n=12 dates, a proxy metric (decisions, not fills), and no test of the
actual future post-fix regime — but it is the best available evidence, it required no
extrapolation from a contaminated baseline, and it points the same direction as the naive
participation math: **survives, not fails.** What it does not resolve, and what a real prereg
would need before shipping any fix on 09-29, is P&L impact (§1d's ~8% of entries removed is a
real dollar cost, separate from the day-count question this section answers) and the two other
open items already filed this session (`veto-scope-safe-3.md` §6: whether the shared-signal
safe/bold-blind construction is itself a defect worth fixing more broadly).

---

## 5. What this does not resolve

Does not re-adjudicate whether the shared-signal leak should be fixed, does not re-score P&L
impact (the sibling ledger-binding-check document already covers entry-count/dollar exposure
better than this report would), and does not test the counterfactual post-fix regime directly
(no fix exists to test). Flagged, not fixed, per this session's read-only/no-trading-path-edit
constraint.

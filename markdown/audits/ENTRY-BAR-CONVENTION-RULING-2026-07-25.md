# RULING — Entry-bar eligibility convention (closes EXIT-ENGINE-ENTRY-BAR-CONVENTION-AUDIT)

**Date:** 2026-07-25 (Saturday, market closed) · **Tier:** Opus judgment pass, as the queue item required
**Closes:** `FABLE-ESCALATION: EXIT-ENGINE-ENTRY-BAR-CONVENTION-AUDIT` (`automation/overnight/queue.md:2727`, HIGH)
**Depends on:** `EXIT-ENGINE-PARITY-RESIDUAL` (`queue.md:2725`, status:done)

---

## The question, as filed

> Does a live position, filled at a 5-min bar's open, realistically get exposed to that SAME bar's
> remaining high/low before the next heartbeat tick, or not?

Two independently-precedented conventions disagreed, and the difference explained **91.1% of a
$39.71/trade aggregate parity gap** on the `vwap_continuation` control cell.

## RULING: entry+1 (strict `>`) is the live-faithful convention.

**A position placed on tick N is not exit-checked until tick N+1.** This is not an approximation
chosen for convenience — it is what the live code actually does.

### Evidence (three independent points, all read fresh 2026-07-25)

**1. The live engine manages exits BEFORE it places entries, within the same tick.**
`setup/scripts/heartbeat_core.py:975-977`, verbatim:

> `# EXIT-MANAGEMENT PASS (flag-gated, default OFF -> byte-identical armed behavior).`
> `# Manage every open position's scale-out FIRST (before evaluating a new entry), so a`
> `# winner's TP1/runner or a stop is realized this tick.`

`_manage_exits(...)` runs at `heartbeat_core.py:987`; the `ENTER_BEAR`/`ENTER_BULL` execution branch
runs after it. A position created by *this* tick's entry branch therefore does not exist in the
tracked-position ledger when *this* tick's exit pass already ran. Its first possible exit evaluation
is the next tick.

Confirmed armed in production, not merely flag-available: `setup/scripts/run-heartbeat-core.ps1:12`
sets `$env:GAMMA_CORE_MANAGES_EXITS = '1'`.

**2. `exit_manager_walk` already implements exactly this.**
`backtest/lib/exit_manager_walk.py:167`:

```python
after = opt_df.index[opt_df["timestamp_et"] > entry_ts]
```

Strict `>`. The entry bar itself is never evaluated. This is the function that
`backtest/tools/engine_fullhist_replay.py` and `setup/scripts/dojo/sim_executor.py` both drive.

**3. `simulate_trade_real` independently arrived at the same convention.**
`lib/simulator_real.py:534-535` (`spy_idx = entry_bar_idx + 2`, `opt_idx = entry_idx_opt + 1`).

**4. `exit_manager_walk`'s own module docstring already states this as deliberate design intent** —
it was never an accident of implementation. Verbatim (`exit_manager_walk.py:28-31`):

> `TICK-MANAGED SEMANTICS (mirrors heartbeat_core.py:870-883 / exit_actuator.manage_tick exactly):`
> `exits are managed BEFORE a new entry is evaluated each real tick, so a freshly-registered`
> `position's FIRST managed tick is the row strictly AFTER its entry timestamp, never the entry`
> `row itself.`

Two engines, the live tick loop, and the harness author's own written reasoning all agree. That is
the ruling.

---

## What this means for the two families

| Family | Convention | Verdict |
|---|---|---|
| `exit_manager_walk` / `plan_exit_actions` / `simulate_trade_real` | entry+1 (strict `>`) | ✅ **Live-faithful. Canonical.** |
| `t4_exit_matrix.py`, `t3`/`t5`, `structure_stop_study.py` | entry+0 (fill bar included) | ⚠️ **Disclosed approximation, valid for their own scope only** |

The entry+0 family is **not a bug**. `backtest/tests/test_fill_bar_convention.py` documents it as a
deliberate, separately-audited choice justified by 1-minute-tick-within-a-5-minute-bar reasoning
(`analysis/recommendations/entry-exit-matrix-fillbar-audit-2026-07-11.md`). Two conventions may
coexist.

**The actual defect was never the convention — it was the silent cross-family comparison.**
`vwapcont_entry_exit_matrix.py`'s `parity_check()` inherited entry+0 from the bar-replay family and
compared its number against a `simulate_trade_real` (entry+1) number **without disclosing that the
two arms used different exit-eligibility rules.** That is the thing to prevent.

### Standing rule

> Entry+0 must never be silently substituted into anything driving `walk_exit_manager`,
> `plan_exit_actions`, `engine_fullhist_replay.py`, `sim_executor.py`, or the day-report-card.
> Any comparison that spans the two families must state the convention of each arm explicitly.

---

## Disclosed residual — the part this ruling does NOT fix

Entry+1 is directionally right but **coarse**, and the coarseness is real:

- Live heartbeat ticks every **60 seconds** (`Gamma_HeartbeatCore`, 09:30-15:55 ET /1min).
- The replay's "next bar" is the next **5-minute** bar.

So a live position filled at 10:32 gets its first exit check around 10:33; the replay's first check
is the 10:35 bar. **The replay under-covers up to ~4 minutes of real exposure on every trade.**

This is not fixable at 5-minute bar resolution — it needs 1-minute OPRA history we do not cache for
the 386-day window. It is **out of scope here and stated rather than papered over.** Sign of the
bias: the replay is *optimistic* on trades that would have stopped out inside the entry bar's tail.

---

## Blast radius — what to re-audit, and what NOT to

Per the escalation's own scoping (`queue.md:2727` item 2), **it is not true that every replay number
is suspect:**

- ✅ **Probably unaffected:** any relative A/B run entirely *within* `simulate_trade_real`. Same bias
  in both arms; the delta survives.
- ⚠️ **At risk, re-audit these:** any study comparing a `simulate_trade_real` number against a
  bar-replay-family number, or against a live / real-fills anchor.

No change is required to `plan_exit_actions` or any shared decision core. This ruling is
documentation + a guard, not a code migration.

---

## Guard — BUILT and RED-proofed 2026-07-25

`backtest/tests/test_exit_manager_walk_entry_bar_convention.py` — 4 tests, **4 passed**.

Fixture note worth keeping: `walk_exit_manager` **point-samples `bar["open"]`** as both best and
worst (`exit_manager_walk.py:181-187`) — it deliberately never reads bar high/low, because the live
actuator reads a single NBBO snapshot per tick. So the trap bar is built on `open`, not `low`.

| Test | Pins |
|---|---|
| `test_entry_bar_own_quote_never_resolves_the_position` | a stop-tripping quote ON the entry bar is ignored; exactly 2 post-entry ticks walked |
| `test_positive_control_same_quote_one_bar_later_DOES_stop` | **anti-vacuity** — the same quote one bar later *does* stop out |
| `test_exit_never_timestamped_at_the_entry_bar` | resolution timestamp is always strictly after entry |
| `test_single_bar_day_cannot_resolve` | entry-bar-only day → `no_bars_after_entry`, never an invented tick |

**RED-proof executed:** flipped `exit_manager_walk.py:167` `>` → `>=`; **3 of 4 failed** (the
positive control correctly stayed green, proving the trap is real), then reverted — `git diff` on
the file is empty. Sibling walk consumers re-run clean afterwards
(`test_engine_fullhist_replay.py` + `test_dojo_sim_executor.py`, 11 passed).

---

## Correction to a hypothesis stated earlier the same day

An earlier note in the 2026-07-25 planning pass argued the *opposite* — that because the live engine
ticks every 60s against live quotes, it "would see an intrabar adverse move inside the entry bar,"
favouring entry+0. **That reasoning was wrong.** It accounted for tick frequency but missed the
manage-before-enter ordering at `heartbeat_core.py:975-987`: the exit pass for tick N runs before
tick N's position exists. Frequency was never the binding constraint; ordering was.

Recorded here because the wrong version was briefly load-bearing in a plan.

---

## Consequence for the 0-for-12 falsification

`ZERO-FOR-TWELVE-POSTMORTEM` (`queue.md:18`) named this convention as **prime suspect** for
`vwap_continuation` (7tr, 0% WR, −$204) and `vix_regime_dayside` (5tr, 0% WR, −$153) being armed on
8/8-gate backtests claiming +$32-79/tr.

**This ruling partially exonerates the convention as the primary cause** — those cells' ship gates
were computed by relative A/B inside one engine, which this ruling says is the unaffected class. The
falsification therefore still needs a root cause, and the postmortem should **not** close on
"entry-bar convention explained it." The ~4-minute under-coverage residual above is a real but small
optimistic bias and is unlikely to account for 0-for-12 at a claimed 55-64% WR (p < 1%) on its own.

**Next suspect to pursue:** the entry-layer divergence — `engine_fullhist_replay` produced only 2
entries on 2026-07-17 against 4 live fills, and its anchor matcher pairs on strike+side alone, so it
"matched" a live 11:40 fill to a replay 13:55 entry **2h15m apart**. That is an entry/scoring
cascade gap, not an exit gap, and it is where the next pass should look.

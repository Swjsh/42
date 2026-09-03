# H9 FLEET MECHANICS — cost of skipped exit-checks + fleet exit lag (2026-09-03)

Stamp: 2026-09-03T10:24 ET. Sonnet, read-only, no broker/MCP/network calls, no writes to
`automation/state/**`. Full machine-readable output:
[`fleet-mechanics-cost.json`](fleet-mechanics-cost.json). Tool (new file, per this task's
constraints):
[`backtest/tools/money_fleet-mechanics-cost.py`](../../../backtest/tools/money_fleet-mechanics-cost.py).

**Window: 2026-08-13..2026-09-02, the 15 full trading sessions immediately before today's
still-live session** (2026-09-03 excluded — market is open, `automation/state/**` is
read-only for this task). Arms: safe-1, safe-3, risky-1, risky-3 (fleet); safe-2/bold-2
(core, comparison only).

## Starting point — what was already closed

Two queue items cover part of this ground and are cited, not redone:

- **FLEET-STALE-SIGNAL-SKIPS-STRUCTURE-STOP** — CLOSED 2026-09-03 06:02 ET. The
  `SIGNAL_MAX_AGE_SEC=420s` staleness branch (`fleet_live.py:938`) has fired with an open
  position on **0 of 2,688 ticks/arm** in 08-25..09-02, and only twice ever, both flat. Not
  re-litigated here; my own extractor confirms **0 stale-with-open-position ticks in the
  wider 08-13..09-02 window too** (see JSON `part_a...total_stale_with_open_position`, all
  arms 0).
- **FLEET-SIGNAL-UNREADABLE-WITH-POSITION** — filed, NOT verified. The sibling failure
  (`signal_unreadable: <JSONDecodeError>`, same `usable_signal=None` collapse, same
  structure-check skip) DOES coincide with open positions and was explicitly left unjoined
  to trades-enriched ("out of scope for this claim, not run"). **This is the gap this report
  closes.**

## Part A — skip census + would-have-fired costing

**Root cause (question 1 from the queue item, answered):** every single one of the 180
`signal_unreadable` events in-window across all arms carries the **identical** message
`Expecting value: line 1 column 1 (char 0)` — the standard `json.JSONDecodeError` for
parsing an **empty file**. That is the fingerprint of a non-atomic write: a reader opens
`shared-signal.json` in the brief window between the writer truncating/opening it and the
content actually landing. It is not partial/corrupt JSON (which would raise a mid-token
delimiter error) — confirms the queue item's own hypothesized fix (atomic tmp+rename on the
writer) targets the right mechanism.

**Incidence:** 65/5,745 ticks (1.13%) on both safe-3 and risky-1 are `signal_unreadable`
(safe-3 and risky-1 read the identical `shared-signal.json`, so they fail on the exact same
ticks — verified: the 12 in-window unreadable-with-position timestamps are byte-identical
between the two arms). Of those, **12 per arm coincided with an open
`stop_mode=="structure"` leg** (up from the smaller 08-25..09-02 window's 18/38 and 6/38
because that prior count included stale+no_signal_file ticks and a shorter window; this
run isolates unreadable-with-open-structure-leg specifically). safe-1 had 0 (retired before
window), risky-3 had 2 unreadable-open ticks but 0 with a live structure leg at that instant.

**Would-have-fired (question 2, "did the option move through the stop"):** applying
`_structure_stop_hit` (`exit_manager.py:140-149`: call exits when closed-5m-close <
trigger_level, put the mirror) with core-decisions.jsonl's `account=="safe"` `spy` field as
the proxy for the value the tick couldn't read — verified byte-for-byte to be
`shared-signal.json`'s `"spot"` field's own source
(`build_shared_signal.py:150 "spy": row.get("spy")`, `_latest_today_core(..., account="safe")`
default) — **2 of 12 unreadable-with-open-structure-leg ticks per arm would have fired**
(2026-08-21 11:12:05 ET, SPY260821C00766000; 2026-09-02 13:12:05 ET, SPY260902C00765000).
Both are the **same underlying event replicated across safe-3 and risky-1** (identical
symbol/trigger/timestamp, different qty) — 2 distinct signal-moments, not 4 independent
failures, consistent with the WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM doc's "one misfire
event, replicated Nx by sizing" pattern.

**Cost (question 2, dollars):** for each would-fire tick, the actual cost is priced against
the FIRST real SELL fill on that arm+symbol at-or-after the skip tick (`fills-ledger.jsonl`
ground truth, not a walker/replay): the fleet's very next tick — **~1 minute later in all 4
cases** (delay 1.00, 1.02, 1.02, 1.03 min) — fired the sell anyway.

| Arm | Date | Symbol | Skip tick | Delay to actual exit | Cost |
|---|---|---|---|---|---|
| safe-3 | 2026-08-21 | SPY260821C00766000 | 11:12:05 | 1.00 min | $3.00 |
| risky-1 | 2026-08-21 | SPY260821C00766000 | 11:12:05 | 1.02 min | $10.00 |
| safe-3 | 2026-09-02 | SPY260902C00765000 | 13:12:05 | 1.02 min | $9.00 |
| risky-1 | 2026-09-02 | SPY260902C00765000 | 13:12:05 | 1.03 min | $10.00 |

n=4, pooled mean **$8.00**, bootstrap CI (5,000 resamples) **[$4.75, $10.00]**. Sum $32.00
across both arms over 15 sessions. **Top-3-trade concentration: 3 of 4 = 87.5% of the pooled
dollar total** (small-n disclosure per the standards — with n=4 this statistic is
uninformative beyond "no single event dominates by an order of magnitude"; all 4 are the
same order of magnitude).

**Interpretation:** the mechanism is real (root cause confirmed, exits genuinely delayed) but
the fleet's ~1-minute tick cadence self-heals the empty-file race almost every time — no
in-window unreadable event persisted past a single tick (verified: all 12 unreadable-open
timestamps per arm are isolated, none back-to-back at 1-tick spacing). The exposure window a
skip can buy is bounded at roughly one tick interval, and SPY's typical 60-90s move at these
VIX levels (both would-fire events measured VIX 15.28-15.38 — 15-17 regime band) is a few
cents of premium, not a catastrophe-cap-sized move.

## Winners check

Zero would-have-fired ticks land on 08-06, 08-13, 08-27, or 08-28 (the named winning days) —
`winners_check.verdict = NO_IMPACT_ON_WINNERS`. Mechanically this class of fix (evaluate the
skipped structure check) can only ever ADD an exit-side check on ticks that currently skip
it — it cannot block or delay an entry — so there is no plausible path by which it hurts a
winning day; the empirical check confirms no such tick even occurred on one.

## Part B — cross-arm exit-timing lag (safe-2 core vs safe-3/risky-1 fleet, matched entries)

18 (date, symbol, fleet_arm) pairs where safe-2 and a fleet arm both bought the identical OCC
contract the same day (fills-ledger, ground truth). Comparing each side's LAST sell fill of
the day:

- **Lag** (fleet's last sell minus safe-2's last sell): mean **+5.22 min**, CI **[0.22, 11.82]**
  — most pairs cluster at ~1-2 min (the normal tick-offset between core's and the fleet
  wrapper's per-minute schedule), with two outliers on 2026-08-27 (SPY260827C00768000,
  +24 and +48 min) pulling the mean up.
- **Per-contract price delta** (fleet vwap − core vwap) x $100: mean **+$9.63**, CI
  **[-$1.43, $21.18]** — the point estimate favors the FLEET side (later exit, better price),
  and the CI straddles zero. The two 08-27 lag outliers are the same trade driving both
  numbers: fleet held ~24-48 min longer into a running winning day and sold **higher**
  (core $2.04 -> fleet $2.60-2.61, +$56-57/contract) — a benefit, not a cost, of that lag.

**This does not isolate the signal-skip mechanism** — CLAUDE.md's own doctrine is that arms
differ by sizing/gates/**stop** by design, so a core-vs-fleet exit-timing difference on a
shared entry is confounded with each arm's own stop_mode/target parameters, not just signal
freshness. Treat Part B as a directional sanity check ("does fleet-vs-core lag look like it
costs money in aggregate, on the days it happens to occur") rather than a clean measurement
of the unreadable-signal mechanism specifically — it does not, on this sample, and if
anything trends the other way. n=18 is too small and the CI too wide to call this SUPPORTED
or REFUTED on its own; it is reported as a null/inconclusive corroborating check alongside
Part A's much more direct (ground-truth, mechanism-isolated) costing.

## Part C — exit-state save-race scan (light, exploratory)

`FLEET-EXIT-STATE-SAVE-PER-SYMBOL` (filed HIGH, bundle candidate, **not yet verified to have
manifested**) hypothesizes a kill between a broker-accepted sell and `exit_actuator.py`'s
once-per-tick `save_states()` (~line 798-799) could leave stale `tp1_filled` state on disk.
Screened for candidate double-fires: SELL fills on the same arm+symbol+day within 90s of each
other. **6 candidates found, all false positives on inspection:**

- 5 of 6 are the **same `order_id`** at the **same price**, sub-second apart (0.1-0.4s) — a
  single logical order the broker reported as multiple fill legs, not two separate exit
  decisions.
- The 6th (risky-3, 2026-08-13, SPY260813C00779000, 60.2s gap, different price/qty) is
  exactly one tick apart at two different prices — a normal two-tick sequential partial exit
  (e.g. TP1 leg then a trim), not a race signature (a race would show the SAME state being
  re-sold, not a legitimately smaller remaining qty at a new price).

**No evidence found that the exit-state save race has manifested** in this window. Consistent
with the queue item's own framing (a theoretical risk from a code-path kill, not yet observed)
— this does not clear the item (a kill-timed process death is rare by nature and this window
had none), but it does not add urgency either.

## Regime split

Both Part A would-fire events measured VIX 15.28-15.38 (15-17 band) — the same calm regime
named in the task's session context. n=2 is too small to say anything about regime dependence
of the unreadable-signal mechanism itself (it's a file-write race, not a market-driven
failure — no market-regime mechanism is expected to modulate it, and none is observed to).
Part B's 18 pairs were not regime-split (out of scope — the mechanism under test there is
arm-vs-arm timing, not VIX-conditional).

## Verdict

**SUPPORTED** (the mechanism is real, root-caused, and now dollar-costed) but the effect size
is trivial: $8/event mean, $32 total pooled cost across both live-fills-carrying fleet arms
over 15 sessions, against a stated recent 4-session book loss of -$1,322. This mechanism is
not a material contributor to the recent losing stretch.

## Proposed change

Confirms (does not implement — `build_shared_signal.py`, `fleet_live.py`, `exit_manager.py`
are all frozen trading-path files under this task's constraints) the fix already specified
in FLEET-SIGNAL-UNREADABLE-WITH-POSITION: atomic write (write to a temp file, `os.replace`
into place) on `build_shared_signal.py`'s `shared-signal.json` output, plus a read-side
fallback to the arm's own last confirmed closed-5m-close when the signal is unreadable. Ship
it as **hygiene**, not urgent risk-reduction — the measured cost is real but small, and the
fix is free (no new complexity on the hot exit path, same pattern already used elsewhere in
this codebase for atomic state writes). This closes FLEET-SIGNAL-UNREADABLE-WITH-POSITION's
verification asks (1)-(3): root cause = non-atomic write / empty-file read race (1); yes, a
delay occurred, ~1 minute, 4 instances / $32 total (2); frequency = 12/arm unreadable-with-
structure-leg-open ticks in 15 sessions, 1.13% of all ticks are unreadable, 18.5% of those
coincide with an open position (3).

## UNVERIFIED / not attempted

- Whether the write race is bounded strictly by process scheduling (i.e. would a slower/busier
  box widen the empty-file window past one tick) — not tested, this is an observational study
  of the actual window's cadence, not a stress test.
- Part B's confound (different stop_mode/target parameters per arm) was not decomposed
  further — a clean isolation would need to hold stop_mode identical across compared arms,
  not attempted this session (budget).
- `no_signal_file` (missing file entirely, distinct from empty-file-mid-write) had 0
  with-open-position occurrences in-window — not a live contributor, noted not investigated
  further.
- Exit-state save-race Part C is a screen, not a proof of absence — a kill-timed process death
  during the exact sub-second window between broker-accept and `save_states()` would not
  necessarily show up as a near-duplicate fill pair (it could instead show up as a stale
  on-disk `tp1_filled=False` with no second fill at all, which this fills-ledger-only screen
  cannot detect without reading exit-state.json's write history — that history is not
  retained/versioned on disk, so this check is inherently limited to fill-pair evidence).

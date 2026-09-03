# FLEET-STALE-SIGNAL-SKIPS-STRUCTURE-STOP -- verify (2026-09-03, Sonnet, report-only)

Full machine-readable result:
[`FLEET-STALE-SIGNAL-SKIP-2026-09-03.json`](FLEET-STALE-SIGNAL-SKIP-2026-09-03.json).
Extractor (read-only): `backtest/tools/fleet_stale_signal_skip_extract.py`, fixture-tested by
`backtest/tests/test_fleet_stale_signal_skip_extract.py` (7/7 pass, `python -m pytest
backtest/tests/test_fleet_stale_signal_skip_extract.py -q` -> `7 passed in 0.32s`).

## 1. The quoted branch

`automation/state/fleet/fleet_live.py`:

```
63: SIGNAL_MAX_AGE_SEC = 420  # 7 min

112: def _load_signal(path: Path, now: datetime) -> tuple[dict | None, str | None]:
113:     if not path.exists():
114:         return None, "no_signal_file"
115:     try:
116:         sig = json.loads(path.read_text(encoding="utf-8"))
117:     except (json.JSONDecodeError, OSError) as e:
118:         return None, f"signal_unreadable: {e}"
119:     age = _signal_age_sec(sig, now)
120:     if age is not None and age > SIGNAL_MAX_AGE_SEC:
121:         return sig, f"signal_stale_{int(age)}s"
122:     return sig, None

796: signal, sig_err = _load_signal(signal_path, now)
797: usable_signal = signal if (signal is not None and sig_err is None) else None
...
824: "signal_status": sig_err or "ok",   # <- written to every decisions.jsonl row
...
937-945 (comment) / 946: _closed_5m_close = (usable_signal or {}).get("spot")
...
manage_tick(..., last_closed_5m_close=_closed_5m_close, ...)
```

`_closed_5m_close` becomes `None` whenever `usable_signal` is `None` -- i.e. on `no_signal_file`,
`signal_unreadable: ...`, **or** `signal_stale_{age}s`. It threads into
`exit_actuator.manage_tick` -> `exit_manager.plan_exit_actions(..., last_closed_5m_close=...)`.

`automation/state/fleet/exit_manager.py:520-534`:

```python
# last_closed_5m_close is None whenever the caller's feed is missing/stale -> fail-open,
# this tick's structure check is simply skipped (the catastrophe cap below and the time
# stop still protect the position).
if state.stop_mode == "structure" and _structure_stop_hit(
        state.side, state.trigger_level, last_closed_5m_close):
    actions.append(ExitAction("SELL_ALL", ..., stage="structure_stop"))
    return ExitDecision(pre_state, tuple(actions))
# (a2) premium/catastrophe stop -> exit ALL ...
if worst_premium <= runner_stop:
    ...
# (b) time stop pre-TP1 -> exit ALL at market
if time_stop_now:
    ...
# (c) ribbon-flip-back -> exit ALL at market
```

**What else is skipped on that branch:** nothing else. Only the `state.stop_mode ==
"structure"` check is gated on `last_closed_5m_close`. **What the tick still does instead:**
premium/catastrophe stop (a2), pre-TP1 profit-lock floor/ladder/trail (a0, evaluated earlier
in the same function, unconditional), time stop (b), and ribbon-flip-back (c) all evaluate
normally on the same tick -- confirmed by code, not inferred. The claim in the queue item is
**verified true as stated**: it is specifically the structure-stop check, and only that check,
that is skipped; every other exit mechanism (including chandelier/profit-lock, which is the
pre-TP1 (a0) block and the post-TP1 runner logic further down, both untouched by this
parameter) still runs.

`row["signal_status"]` (fleet_live.py:824) IS the field the branch writes -- `"signal_stale_
{age}s"` on this exact branch, `"signal_unreadable: ..."` on the sibling branch, `"ok"`
otherwise. It is not invisible at the data layer (present in every decisions.jsonl row); it
**is** invisible at the alerting layer -- nothing currently reads it and raises.

## 2. Per-arm counts, 2026-08-25..2026-09-02

| Arm | Total ticks | `signal_stale_*` ticks | ...with position open | `signal_unreadable` ticks | ...with position open |
|---|---|---|---|---|---|
| safe-1 | 0 (arm retired before window; last row 2026-07-10) | 0 | 0 | 0 | 0 |
| safe-3 | 2,688 | 0 | 0 | 38 | 6 |
| risky-1 | 2,688 | 0 | 0 | 38 | 18 |
| risky-3 | 0 (arm retired mid-window; last row 2026-08-28) | 0 | 0 | 0 | 0 |

**Signal-age distribution on ticks with an open position:** N/A -- zero stale ticks exist in
the window on any arm, so there is no distribution to report. The `signal_status` field never
takes the `signal_stale_*` value in this window; every in-window row is `"ok"` except the
`signal_unreadable` rows above (a distinct, unrelated failure mode -- see below).

**Full-history check (not just the window):** the `signal_stale_*` branch has fired exactly
**twice, ever**, identically across all 4 arms (they share one `shared-signal.json` reader):
`2026-06-24T16:53:47-04:00` (age 1452s) and `2026-06-26T08:14:20-04:00` (age 30920s, an
overnight gap). Both rows carry `"flat": true` -- no open position either time, in the whole
recorded history of any arm.

## 3. Join to trades-enriched.jsonl

10 `structure_stop` exits recorded in-window (risky-1 x5, safe-3 x5; safe-1/risky-3 had none,
consistent with 0 total ticks). Since zero stale-with-open-position ticks exist anywhere in
the window (or ever), the join is negative by construction: **0 of 10 structure_stop exits
were preceded by a stale-skipped tick with the position open.** Worst case: none -- there is
no case. (Full per-exit `preceded_by_stale_skip: false` list in the JSON.)

## 4. Classification

**NEVER-FIRED** (all 4 arms, both the requested window and full history). The
`SIGNAL_MAX_AGE_SEC` staleness path is real, wired, and behaves exactly as the queue item
describes mechanically -- but the shared-signal feed has been fresh enough (<420s) on every
tick with an open position across the entire recorded fleet history. This is a live-behaviour
claim about a branch that is correctly built but has not yet been exercised under the
condition that matters (staleness + open position).

## 5. Fix spec (downgraded, per the queue item's own instruction)

Since it never fired, this downgrades from a kill-type fix to a **guard-only visibility
change** -- log the skip loudly instead of changing exit logic:

- **What:** when `sig_err` starts with `"signal_stale_"` or `"signal_unreadable"` AND any arm
  has an open position that tick (`flat is False`), emit a WARN-level log line (or append to
  `STATUS.md ## Known broken` / a dedicated `automation/state/fleet/stale-signal-open-position.
  jsonl`) naming the arm, age, and open symbol -- today this is silently present only in
  `decisions.jsonl`'s `signal_status` field, which nothing reads or alerts on.
- **Why guard-only, not kill-type:** the branch's own fail-open design is correct (premium
  stop / time stop / ribbon-flip-back remain active), and there is zero evidence of harm to
  fix. A kill-type change (re-evaluate structure from the arm's own last bar, or flatten after
  N stale ticks with a position) would be solving a problem that has not occurred, at the cost
  of new complexity on the hot exit path.
- **Guard test name:** `test_stale_signal_open_position_logs_warn_2026_09_03.py` (assert: a
  tick with `sig_err="signal_stale_500s"` and an open position produces the WARN/alert
  artifact; a flat position or `sig_err=None` produces none).

## Related finding (out of scope, not investigated further here)

`signal_unreadable` (missing/corrupt `shared-signal.json` -- a different root cause, same
`usable_signal=None` downstream effect) is far more frequent in-window and DOES coincide with
open positions: risky-1 18/38 unreadable ticks had a position open, safe-3 6/38. Not joined
against trades-enriched.jsonl under this fire (out of the named claim's scope) -- flagged for
a follow-up queue item, not spawned as a chip per this session's report-only/no-chip
constraint.

## Unverified / not done

- The `signal_unreadable` -> structure-stop-exit join (see above) -- explicitly out of scope
  for this claim, not run.
- No live/paper verification -- this is a pure log-and-code read, no MCP/broker calls made.
- `safe-1` and `risky-3` have no rows inside the window at all (arms retired/paused before
  09-01) -- their `NEVER-FIRED` classification is trivially true (no ticks to fire on), not
  independent evidence of the guard behaving correctly under load; noted, not treated as
  equivalent to safe-3/risky-1's non-trivial zero-count result.

`queue_closure` string (for the archiver) is in the JSON's `queue_closure` field.

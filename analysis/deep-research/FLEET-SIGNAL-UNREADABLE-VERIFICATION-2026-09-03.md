# FLEET-SIGNAL-UNREADABLE-WITH-POSITION -- verification (2026-09-03, 18:45 ET, Sonnet, read-only)

**Verdict: ZERO-COST RACE, verified.** Root cause is real and confirmed (two independent
1-min writers racing a non-atomic writer against a no-retry reader). The queue item's
headline number for risky-1 is **wrong** (18/38 claimed, 6/38 verified — identical to
safe-3). Of the 12 verified unreadable-with-open-position ticks in the 08-25..09-02 window
(6 risky-1 + 6 safe-3), **10 never had SPY anywhere near the structure-stop trigger level**,
and the remaining 2 (both bracketing one risky-1/safe-3 trade pair) show **no evidence of a
costly delay** — one is provably identical to its readable neighbors, the other's disputed
window shows the option price *recovering*, not deteriorating. **$0 quantified cost.** The
09-29 bundle fix (atomic write + reader retry/fallback) is still correct to ship — it
closes a real, reproducible bug — but it is not correcting a proven live loss in this
window.

Full data: [`FLEET-SIGNAL-UNREADABLE-VERIFICATION-2026-09-03.json`](FLEET-SIGNAL-UNREADABLE-VERIFICATION-2026-09-03.json).
Extraction tool (new, read-only): [`backtest/tools/fleet_signal_unreadable_extract.py`](../../backtest/tools/fleet_signal_unreadable_extract.py).

---

## 1. Root cause -- VERIFIED

**The writer is not atomic.** `automation/state/fleet/build_shared_signal.py` — every
branch of `build()` ends the same way:

```python
OUT.write_text(json.dumps(sig, indent=2), encoding="utf-8")
```

(confirmed at lines ~720, 744, 835; the replay-only `build_from_rows` sibling has its own
guarded copies at ~1333/1392, not on the live path). `Path.write_text()` opens the file in
`"w"` mode, which **truncates it to 0 bytes before the new content is written** — it is not
`tmp + os.replace`. No lock, no `filelock`/`msvcrt`/`fcntl` anywhere in this file or in the
reader.

**The reader does not retry.** `automation/state/fleet/fleet_live.py:112-119`:

```python
def _load_signal(path: Path, now: datetime) -> tuple[dict | None, str | None]:
    if not path.exists():
        return None, "no_signal_file"
    try:
        sig = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return None, f"signal_unreadable: {e}"
    ...
```

One `read_text()` + `json.loads()`, one shot. On the caught exception it returns the
`signal_unreadable: {e}` string that lands in `decisions.jsonl`'s `signal_status` field
(`fleet_live.py:824`, `"signal_status": sig_err or "ok"`).

**There are TWO independent writers, not one.** This is the part the queue item didn't
name and is the actual mechanism:

| Writer | Schedule | Task | What it does |
|---|---|---|---|
| 1 | Every 1 min, **09:31–16:01 ET** wd | `Gamma_FleetExecutor` (`setup/scripts/run-fleet-executor.ps1`) | Step 1 runs `build_shared_signal.py` as its own process; step 2 (serially, same script, blocking `Invoke-PythonHidden`) then runs `fleet_live.py` to *read* it. **No race inside one fleet-executor tick** — `-MultipleInstances IgnoreNew` (`setup/install-fleet-executor.ps1:31`) also blocks it from overlapping itself. |
| 2 | Every 1 min, **09:00–16:30 ET** wd | `Gamma_SightBeacon` (`setup/scripts/sight_beacon.py`) | `main()` unconditionally calls `build_shared_signal.build()` every fire — see the module's own comment: *"Drive the fleet's shared-signal off this beacon every minute so the 4 fleet accounts are never blind either... this is safe to call every tick"* (`sight_beacon.py:184-193`). Targets the **same** `automation/state/fleet/shared-signal.json`. This is a completely separate Windows Scheduled Task with no shared mutex with writer 1. |

So the actual race is: **sight_beacon's write** (phase-random relative to fleet-executor's
own 1-min cycle) landing under **fleet_live's read**, not the two steps *within* one
fleet-executor tick racing each other as might be assumed from "1 min behind" framing in
the ps1 header comment.

**The exception text confirms the truncation-race mechanism, not something else.** Every
single one of the 106 occurrences found (2026-08-01..09-03, risky-1's file) is byte-
identical:

```
signal_unreadable: Expecting value: line 1 column 1 (char 0)
```

That is exactly `json.JSONDecodeError` on an **empty string** — what you get when
`read_text()` lands in the truncate-to-write gap, never a partial-object / mid-key parse
error (which would say something like "Expecting ',' delimiter" or "Unterminated
string"). This rules out disk I/O flakiness or encoding drift as the mechanism and points
squarely at the truncate race.

---

## 2. Cost -- VERIFIED, $0 in the checked window

Method: for each of the 6 unreadable-with-open-position ticks per arm in 08-25..09-02 (12
rows total across risky-1 + safe-3), confirmed the skip is real (every `exit_pass` entry
carries `stop_mode: "structure"`, `last_closed_5m_close: None`), then checked (a) the
option's cached 1-min bar (`backtest/data/highres/`) against its own recorded
`runner_stop` (the separate, unconditional premium/catastrophe stop), and (b) SPY's 5-min
close (`backtest/data/spy_5m_2026-05-19_2026-09-03.csv`) against `trigger_level` (the
structure-stop threshold), both around and after the tick.

- **4 of 6 ticks (2026-08-27 x3, 2026-08-28 x1):** SPY was 2–5 points clear of
  `trigger_level` at and after the tick; the option premium was 2–4x the `runner_stop`
  level. Neither stop mechanism was anywhere near firing. Confirmed: none of these
  positions ever exited via `structure_stop` (trades-enriched.jsonl shows `tp1+trail` for
  all of them). **Zero cost, trivially.**
- **2 of 6 ticks (2026-09-02T13:09:06 and 13:12:05, both `SPY260902C00765000`,
  `trigger_level=765.46`):** SPY *had* crossed below trigger nearby. This is the one real
  candidate. Detail:

  | Tick | Status | `last_closed_5m_close` |
  |---|---|---|
  | 13:08:06 (readable) | ok | 765.465 |
  | **13:09:06** | **signal_unreadable** | **None (skipped)** |
  | 13:10:07 (readable) | ok | 765.465 |
  | 13:11:05 (readable) | ok | 765.465 |
  | **13:12:05** | **signal_unreadable** | **None (skipped)** |
  | 13:13:05 (readable) | ok | 764.63 → **`_structure_stop_hit` fires** (`764.63 < 765.46`) |

  `exit_manager._structure_stop_hit` uses a strict `<` comparison (`exit_manager.py:149`).

  - **13:09 tick: PROVABLY zero incremental cost.** Its immediate readable neighbors on
    both sides (13:08 and 13:10) show the **identical** `765.465` value. Even fully
    readable, the 13:09 tick would have seen `765.465` (not `< 765.46`) and would **not**
    have fired. The unreadability changed nothing here.
  - **13:12 tick: ambiguous mechanism, but no evidence of cost.** Its neighbors bracket a
    real change (`765.465` → `764.63`), so it's not provably a no-op the same way. But the
    price data during the disputed minute argues against any cost: the 13:12–13:13 1-min
    option bar traded `O=0.81 H=0.86 L=0.77 C=0.86`; the **actual** fills — `safe-3` sold 3
    @ 0.81 (13:13:06.891 ET), `risky-1` sold 5 @ 0.82 (13:13:07.955 ET), both from
    `automation/state/fills-ledger.jsonl` — land inside that same range's low end, and the
    *following* minute (13:13–13:14) printed `O=0.86 C=0.88`: **premium was recovering, not
    deteriorating**, through the disputed window. A maximally-generous hypothetical
    one-tick-earlier exit would not plausibly have done better.

**Verdict: $0 quantified cost across the verified 08-25..09-02 window.** This is a
genuine negative result, not an absence of looking — see the neighbor-bracket check and
fills-ledger cross-reference above. Scope note: unreadable-with-open-position ticks also
occur on dates outside this window (2026-07-17, 08-07, 08-10 x4, 08-13, 08-14, 08-19 x2,
08-21 x2, 09-03 — visible in risky-1's full decisions.jsonl) — **not** checked for cost
here (out of the task's stated 08-25..09-02 scope). UNVERIFIED whether any of those carry
real delay cost.

---

## 3. Frequency -- flat ~1-1.5% of ticks, no clustering

Over 2026-08-01..09-03 (risky-1's file, 9,203 ticks): **106 unreadable (1.15%)**.

| Hour ET | Total ticks | Unreadable | Rate |
|---|---|---|---|
| 09 | 681 | 4 | 0.59% |
| 10 | 1440 | 18 | 1.25% |
| 11 | 1440 | 22 | 1.53% |
| 12 | 1440 | 16 | 1.11% |
| 13 | 1440 | 19 | 1.32% |
| 14 | 1440 | 14 | 0.97% |
| 15 | 1320 | 13 | 0.98% |

No escalating-drift pattern (rules out clock-drift-over-session as the driver). No
single-minute clustering — unreadable ticks land on ~40 distinct minute-of-hour values,
3-4 each, spread essentially uniformly. The 09:00 hour's lower rate (0.59%) is itself
corroborating evidence for the two-writer theory: `Gamma_FleetExecutor` doesn't open its
market-hours gate until 09:31, so from 09:00-09:31 only `Gamma_SightBeacon` touches
`shared-signal.json` and there is no reader running yet to collide with — consistent with
near-zero unreadable ticks in that half hour, rising to the steady ~1-1.5% rate once both
independently-scheduled writers and the reader are all live.

---

## 4. Discrepancy vs. the queue item's numbers -- risky-1's "18 of 38" is WRONG

The queue item states *"risky-1 18 of 38 unreadable ticks... had a position open"*.
Direct query against `automation/state/fleet/risky-1/decisions.jsonl` (rows where
`signal_status` starts with `"signal_unreadable"` AND `flat is False`, `ts_et` date in
`[2026-08-25, 2026-09-02]`):

```
total unreadable 38 with flat is False 6
```

**Verified: 6 of 38, not 18.** This is identical to safe-3's verified count (also 6 of
38) — both arms were in a position at the exact same shared-signal-read ticks
(2026-08-27 10:47/12:39/12:58, 2026-08-28 10:38, 2026-09-02 13:09/13:12), because risky-1
and safe-3 trade the same `ribbon_ride` triggers off the same shared signal, differing
only in sizing (per the arms-are-risk-profiles doctrine). No grouping tried (per-arm open
count, total unreadable count regardless of position, any other arm's total) produces 18.
**Treat the queue item's "18" as unverified/wrong** until whoever filed it shows the
derivation.

---

## 5. Kill-type fix shape for the 09-29 bundle -- NOT APPLIED (per task scope)

**Writer: atomic replace.** In `build_shared_signal.py`, replace every
`OUT.write_text(json.dumps(sig, indent=2), encoding="utf-8")` call (and the
`build_from_rows`/`SHADOW_OUT` siblings, for consistency) with a small helper:

```python
def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + f".tmp.{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)   # atomic on the same filesystem, POSIX and Windows both
```

`os.replace` on Windows uses `MoveFileExW` with `MOVEFILE_REPLACE_EXISTING`, which is an
atomic rename at the filesystem level — no reader can ever observe a partially-written
file, matching the pattern `sight_beacon.py` itself already uses for its own
`sight-beacon.json` write (`tmp.write_text(...); tmp.replace(BEACON)` — ironic, since
`sight_beacon.py` gets its OWN write right but calls the fleet's non-atomic one right next
to it).

**Reader: retry once, then fall back instead of collapsing to None.** In
`fleet_live.py::_load_signal`:

```python
def _load_signal(path: Path, now: datetime) -> tuple[dict | None, str | None]:
    if not path.exists():
        return None, "no_signal_file"
    sig = None
    last_err: Exception | None = None
    for attempt in (0, 1):
        try:
            sig = json.loads(path.read_text(encoding="utf-8"))
            last_err = None
            break
        except (json.JSONDecodeError, OSError) as e:
            last_err = e
            if attempt == 0:
                time.sleep(0.25)
    if last_err is not None:
        return None, f"signal_unreadable: {last_err}"
    age = _signal_age_sec(sig, now)
    if age is not None and age > SIGNAL_MAX_AGE_SEC:
        return sig, f"signal_stale_{int(age)}s"
    return sig, None
```

Then, in the caller (`fleet_live.py` around line 937-940, the STRUCTURE-STOP comment
block), when `usable_signal is None` *and* the arm has a registered `stop_mode ==
"structure"` position, fall back to the arm's own last known `last_closed_5m_close`
(persisted from its previous successful tick — e.g. carried on the `ExitState`/exit-state
file, or simply the last non-None value seen in that arm's own `decisions.jsonl`) rather
than `None`, mirroring the existing fail-open design already used for the
`SIGNAL_MAX_AGE_SEC` staleness branch (accept a slightly-stale value rather than skip the
check outright).

**Guard test (RED-proofs the fix):** a new
`automation/state/fleet/test_shared_signal_atomic_write_race.py` that:
1. Points `build_shared_signal.OUT` and `fleet_live`'s signal path at a temp file.
2. Spins up a writer thread that calls `build_shared_signal.build()` in a tight loop for
   ~2-3 seconds (or the module's own write helper, isolated) while a reader thread calls
   `fleet_live._load_signal()` in a tight loop concurrently.
3. Asserts **zero** `signal_status` values starting with `"signal_unreadable"` were
   observed across the whole run, post-fix.
4. Includes a `pytest.mark.xfail`-style companion (or a `monkeypatch` back to the OLD
   `path.write_text` call, no `os.replace`) that demonstrates the **same test reliably
   reproduces at least one `signal_unreadable` hit** against the pre-fix code — proving the
   test is discriminating (catches the regression, not just passing vacuously) rather than
   relying on the ~1.15%/tick real-world race to show up by chance in CI.

None of this was applied — writer, reader, and guard test above are unapplied per the
`STRICTLY read-only` / `never edit trading-path files` scope of this task. `fleet_live.py`
and `build_shared_signal.py` are both on the do-not-edit list.

---

## Files

- New (this task): `analysis/deep-research/FLEET-SIGNAL-UNREADABLE-VERIFICATION-2026-09-03.md`,
  `analysis/deep-research/FLEET-SIGNAL-UNREADABLE-VERIFICATION-2026-09-03.json`,
  `backtest/tools/fleet_signal_unreadable_extract.py`.
- Read, not edited: `automation/state/fleet/fleet_live.py` (`_load_signal` L112-119,
  STRUCTURE-STOP comment block ~L937-940), `automation/state/fleet/build_shared_signal.py`
  (`build()` L654 onward, `OUT.write_text` call sites), `automation/state/fleet/exit_manager.py`
  (`_structure_stop_hit` L140-149, `plan_exit_actions` L523-539), `setup/scripts/sight_beacon.py`
  (L184-193), `setup/scripts/run-fleet-executor.ps1`, `setup/install-fleet-executor.ps1` (L31),
  `automation/state/SCHEDULED-TASKS.md` (`Gamma_FleetExecutor`, `Gamma_SightBeacon` rows),
  `automation/state/fleet/{risky-1,safe-3}/decisions.jsonl`, `analysis/trades-enriched.jsonl`,
  `automation/state/fills-ledger.jsonl`, `backtest/data/highres/SPY260902C00765000_1m_2026-09-02.csv`,
  `backtest/data/spy_5m_2026-05-19_2026-09-03.csv`, `backtest/tools/fleet_stale_signal_skip_extract.py`
  (sibling module, copied from, not edited).

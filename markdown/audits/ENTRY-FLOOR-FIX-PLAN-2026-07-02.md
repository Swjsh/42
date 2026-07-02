# ENTRY-FLOOR FIX PLAN — 2026-07-02 (apply AFTER 16:00 ET)

> **Status: STAGED, NOT APPLIED.** Diagnosed live ~11:20 ET 2026-07-02 (market open — no
> live-path edits this session per hard rule). Guards already committed inert:
> `backtest/tests/test_entry_floor_2026_07_02.py` (9 evidence pins green, 21 fix guards
> skip-until-applied, 1 strict-xfail sentinel that turns RED if the fix lands without
> arming them).

## Incident

2026-07-02 core engine fired **ENTER_BEAR @ 09:30:03 (safe) + 09:30:38 (bold)**, both
PLACED + filled (first core round trips) — 5 minutes before the doctrine [09:35, 15:00)
entry window opens. Fleet safe-1 entered 09:31:01 off the fanned-out verdict. Both were
stop-outs in opening chop (anecdote, not evidence — the bug is the window breach).

## Root cause (one sentence)

`entry_no_trade_before_et="09:35"` IS forwarded (heartbeat_core.py:444) and parsed
(engine_cli.py:331-332), but filter-1 enforces it against the **trigger bar's own
timestamp** (filters.py:1073-1077 bear / 848-852 bull) — and at the market-open ticks
the trigger bar (2nd-to-last fetched 5m bar) is still the **prior day's 15:50/15:55
bar**, so the 09:35 floor structurally cannot fire and yesterday's ceiling-blocked
ENTER_BEAR executed at today's open. Not C14 forwarded-but-unread — a new variant:
**forwarded-and-read-against-the-wrong-clock** (bar-time vs wall-clock), compounded by
**no same-session freshness check** on the trigger bar.

## Evidence (verified this session)

| Fact | Source |
|---|---|
| Both params files say `"entry_no_trade_before_et": "09:35"` | params.json:32, aggressive/params.json:26 |
| 09:30:03/09:30:38 ENTER rows carry `spy=746.26` | core-decisions.jsonl:3311-3312 |
| **746.26 = the 2026-07-01 15:50 ET bar close** (Alpaca IEX REST, fetched 07-02) | 19:50Z bar close=746.26 |
| 09:31–09:35 ticks carry `spy=745.665` = 07-01 **15:55** close; 09:36 tick `spy=748.56` = 07-02 **09:30** close | ledger rows 3313-3324 + bar fetch |
| Yesterday 15:53–15:55 the engine emitted the *same* signal (ENTER_BEAR / trendline_rejection / bear_score 9), ceiling-blocked | ledger rows 3305-3310 |
| FIX1 ceiling checks **wall-clock** (`now_et.time() >= ceiling`); the floor has **no wall-clock check anywhere** on the live path | heartbeat_core.py:148-164, 644 |
| fleet_live has a ceiling mirror but **no floor mirror** | fleet_live.py:215-229, 249-251 |
| build_shared_signal derives fleet `passed` from the **verdict**, not the action — a core-side skip alone can't stop the fleet | build_shared_signal.py:99-111 |

So the open tick is the one moment a stale after-hours signal escapes BOTH time gates:
bar-time 15:50 passes the floor, wall-clock 09:30 passes the ceiling.

## The fix — 2 gates + fleet mirror + fan-out guard (FIX1's exact pattern)

The **staleness gate is the load-bearing half** (today's incident was a prior-day
signal). The wall-clock floor makes the knob's intent explicit and covers the
09:31–09:36 window where the trigger is yesterday's 15:55 bar, plus any future feed
hiccup. Both are cheap and mirror `_past_entry_ceiling`.

### Edit 1 — `setup/scripts/heartbeat_core.py` after line 164 (end of `_past_entry_ceiling`)

Insert two helpers:

```python
def _before_entry_floor(params: dict, now_et: datetime) -> bool:
    """FIX (2026-07-02): wall-clock entry-time floor — mirror of _past_entry_ceiling.
    entry_no_trade_before_et was enforced only against the TRIGGER BAR timestamp
    (filters.py filter-1), which at the open ticks is still the PRIOR day's 15:50/15:55
    bar — so the 09:35 floor could never fire (2026-07-02: ENTER_BEAR placed 09:30:03).
    True => now_et is BEFORE the floor => the caller logs SKIP_EARLY_ENTRY and never
    attempts an order. Missing/malformed key fails CLOSED to the 09:35 doctrine default.
    Guard: test_entry_floor_2026_07_02.py::TestCoreWallClockFloor."""
    raw = params.get("entry_no_trade_before_et") if isinstance(params, dict) else None
    floor = time(9, 35)
    if raw:
        try:
            parts = str(raw).split(":")
            floor = time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except (TypeError, ValueError, IndexError):
            floor = time(9, 35)
    return now_et.time() < floor


def _stale_trigger_bar(payload: dict, now_et: datetime) -> bool:
    """FIX (2026-07-02): an ENTER is only actionable when its trigger bar is from
    TODAY's session. At the open ticks the 2nd-to-last fetched bar is the PRIOR day's
    15:50/15:55 bar — scoring it re-emits yesterday's dying signal at today's prices
    (the 2026-07-02 09:30:03 incident). Malformed/absent timestamp fails CLOSED (stale).
    Guard: test_entry_floor_2026_07_02.py::TestCoreStaleTriggerBar."""
    try:
        ts = str(payload["bar_ctx"]["timestamp_et"])
        return ts[:10] != now_et.strftime("%Y-%m-%d")
    except (KeyError, TypeError, IndexError):
        return True
```

### Edit 2 — `setup/scripts/heartbeat_core.py` run_account, line 651

OLD:
```python
    elif v in ("ENTER_BEAR", "ENTER_BULL"):
```
NEW (insert two elifs BEFORE it; staleness first — it is the true cause):
```python
    elif v in ("ENTER_BEAR", "ENTER_BULL") and _stale_trigger_bar(payload, et):
        # FIX (2026-07-02): prior-day trigger bar — yesterday's signal, not today's.
        rec["action"] = "SKIP_STALE_TRIGGER"
        rec["trigger_bar_et"] = str(payload["bar_ctx"].get("timestamp_et"))
    elif v in ("ENTER_BEAR", "ENTER_BULL") and _before_entry_floor(params, et):
        # FIX (2026-07-02): wall-clock floor — [09:35, 15:00) now enforced on BOTH ends.
        rec["action"] = "SKIP_EARLY_ENTRY"
        rec["entry_floor_et"] = str(params.get("entry_no_trade_before_et") or "09:35")
    elif v in ("ENTER_BEAR", "ENTER_BULL"):
```

### Edit 3 — `setup/scripts/heartbeat_core.py` `_execute`, after line 922 (ceiling return)

OLD (lines 920-922):
```python
    if _past_entry_ceiling(params, _et_now()):
        return {"status": "SKIP_LATE_ENTRY",
                "entry_ceiling_et": str(params.get("entry_no_trade_after_et") or "15:00")}
```
NEW (belt-and-suspenders, covers the extra-setup G4 route — same as FIX1):
```python
    _now_exec = _et_now()
    if _past_entry_ceiling(params, _now_exec):
        return {"status": "SKIP_LATE_ENTRY",
                "entry_ceiling_et": str(params.get("entry_no_trade_after_et") or "15:00")}
    if _stale_trigger_bar(payload, _now_exec):
        return {"status": "SKIP_STALE_TRIGGER",
                "trigger_bar_et": str(payload["bar_ctx"].get("timestamp_et"))}
    if _before_entry_floor(params, _now_exec):
        return {"status": "SKIP_EARLY_ENTRY",
                "entry_floor_et": str(params.get("entry_no_trade_before_et") or "09:35")}
```

### Edit 4 — `automation/state/fleet/fleet_live.py` after line 229 (end of `_past_entry_ceiling`)

Insert the floor mirror:
```python
def _before_entry_floor(params: dict, now_et: datetime) -> bool:
    """FIX (2026-07-02): wall-clock entry-time floor (mirror of heartbeat_core).
    Fleet had a ceiling mirror but NO floor — safe-1 entered 09:31:01 on 2026-07-02 off
    the core's stale 09:30:03 verdict. Fails CLOSED to the 09:35 doctrine default.
    Guard: test_entry_floor_2026_07_02.py::TestFleetFloorMirror."""
    raw = params.get("entry_no_trade_before_et") if isinstance(params, dict) else None
    floor = dt_time(9, 35)
    if raw:
        try:
            parts = str(raw).split(":")
            floor = dt_time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except (TypeError, ValueError, IndexError):
            floor = dt_time(9, 35)
    return now_et.time() < floor
```

### Edit 5 — `automation/state/fleet/fleet_live.py` `_place_live`, after line 251 (ceiling block)

OLD (lines 249-251):
```python
    if _past_entry_ceiling(params, now):
        return {"mode": "LIVE", "placed": False, "reason": "SKIP_LATE_ENTRY",
                "entry_ceiling_et": str(params.get("entry_no_trade_after_et") or "15:00")}
```
NEW (append the floor block directly after):
```python
    if _past_entry_ceiling(params, now):
        return {"mode": "LIVE", "placed": False, "reason": "SKIP_LATE_ENTRY",
                "entry_ceiling_et": str(params.get("entry_no_trade_after_et") or "15:00")}
    # FIX (2026-07-02): wall-clock floor mirror — the fleet consumes the core verdict
    # via shared-signal (passed derives from VERDICT, not action), so it needs its own gate.
    if _before_entry_floor(params, now):
        return {"mode": "LIVE", "placed": False, "reason": "SKIP_EARLY_ENTRY",
                "entry_floor_et": str(params.get("entry_no_trade_before_et") or "09:35")}
```

### Edit 6 — `automation/state/fleet/build_shared_signal.py` `_map_core_row`, lines 104-111

Insert above the function (line ~104):
```python
# 2026-07-02 entry-floor fix: brain-level TIME-GATE skips must not fan out as ENTER.
# Unlike PLACE_FAIL (execution noise — arms may succeed where the core's broker call
# failed), these mean the entry was never actionable at this wall-clock time.
_TIME_GATE_SKIPS = frozenset({"SKIP_EARLY_ENTRY", "SKIP_STALE_TRIGGER", "SKIP_LATE_ENTRY"})
```
And inside `_map_core_row`, OLD (line 105):
```python
    verdict = row.get("verdict")
```
NEW:
```python
    verdict = row.get("verdict")
    if row.get("action") in _TIME_GATE_SKIPS:
        verdict = "HOLD"
```

### Edit 7 — `backtest/tests/test_entry_floor_2026_07_02.py`

Delete the `@pytest.mark.xfail(...)` line in `TestFixAppliedSentinel.test_fix_is_applied`
(strict xfail goes XPASS=RED the moment edits 1-6 land — this step IS the proof the 21
skipped guards armed).

## Mechanical apply (edits 1–6 as one command)

The exact edits above are also staged as a verified unified diff:

```
git apply markdown/audits/entry-floor-fix-2026-07-02.patch
```

(`git apply --check --stat` verified clean against the tree at commit time: 3 files,
+77/−1.) Then do Edit 7 (delete the sentinel's xfail marker) by hand.

**Pre-validated 2026-07-02 (staged copies, live files untouched):** the patch was
applied to scratchpad copies and the full guard suite run against them via module
pre-cache — `30 passed, 1 deselected in 0.09s` (all 21 skip-until-applied guards armed
and green; sentinel deselected because its XPASS-goes-RED is the apply-time reminder).

## Verification (OP-33: quote the check, not the claim)

1. `backtest/.venv/Scripts/python.exe -m pytest -q backtest/tests/test_entry_floor_2026_07_02.py`
   → expect **31 passed, 0 skipped, 0 xfailed** (soft ledger pin may skip if pruned).
2. Full regression: `... -m pytest -q backtest/tests/test_money_path_2026_07_01.py backtest/tests/test_graduated_guards.py` → all green.
3. Next session open (09:30–09:34 ET): core-decisions.jsonl shows `SKIP_STALE_TRIGGER`
   (or `SKIP_EARLY_ENTRY`) with `armed: true` and **no** `exec` block; fleet decisions
   show `SKIP_EARLY_ENTRY` reason rows; first possible ENTER ≈ 09:40–09:41.

## Post-fix timing semantics (expected — not a new bug)

With the staleness gate, the earliest actionable core entry is ~**09:40–09:41
wall-clock**: the first same-day trigger bar passing filter-1 is the 09:35 bar, which
becomes the trigger once the 09:40 bar exists in the feed. This MATCHES the backtest's
semantics (a 09:35 trigger bar fills on the next bar) — the live/backtest window is now
aligned, which is the point.

## Revert

Single commit; `git revert <apply-commit>`. No params/state changes involved.

## The VALUE question (flagged, NOT decided here)

This fix makes the 09:35 knob WORK; it does not decide what the floor SHOULD be.
Tension on record: E3/TRAITS found 09:30–10:00 was J's toxic window and 44.2% of engine
flow lands there — arguing for a LATER floor (10:00) — while the engine's own setups
were validated on 2025-26 real fills **including open-window entries**. Today's two
09:30 stop-outs are anecdote (n=2, and they breached the ratified window anyway).
Right move: once the knob is live-enforced, A/B the floor value (09:35 vs 10:00)
through the standard scorecard rail (`analysis/recommendations/`) on real fills —
separate change, separate evidence.

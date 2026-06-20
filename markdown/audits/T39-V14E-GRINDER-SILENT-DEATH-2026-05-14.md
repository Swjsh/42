# T39 — v14_enhanced grinder silent-death forensics (Fire #23 2026-05-14T03:20 ET)

> Status: FORENSICS COMPLETE. Mitigations queued T70-T74.

## Symptoms

`backtest/autoresearch/v14_enhanced_grinder.py` died silently 3 times on 5/13:

| Launch | PID | Started | Last log | Combos completed | Status at death |
|---|---|---|---|---|---|
| #1 | 30476 (parent) / 22640 (runner) | 5/13 00:44:41 | 5/13 01:45 area | 35-40 (per earlier STATUS.md) | silent stop, no traceback |
| #2 | 20856 / 22640 | 5/13 02:02:54 | 5/13 04:00 deadline | 100/540 partial | deadline-reached graceful exit |
| #3 | 19408 (relaunched 08:19:39) | 5/13 08:19 | 5/13 08:26 (5 combos) | 5/540 | silent stop |
| #4 | 10232 / 21036 | 5/13 08:41:31 | **5/13 09:35:12** | 50/540, **60 rejections written** | `status: "running"` but **NO further log writes** |

`progress.json` final snapshot (PID 21036 at death):
```json
{
  "completed": 50,
  "rejected": 50,    // log says 50, but rejections.jsonl actually has 60 entries
  "keepers": 0,
  "current_pid": 21036,
  "last_update": "2026-05-13T09:35:12.645163",
  "status": "running"   // never updated to "deadline_reached" or "completed"
}
```

**The key signature:** `status="running"` + `last_update` 17+ hours ago + `current_pid` no longer alive (verified Fire #20 stage 0 — PID 21036 is not in `Get-Process | Where ProcessName -eq python` output). **Silent kill.**

## What we know

1. **pythonw.exe is used** per `mp.set_executable(pythonw.exe)` at v14_enhanced_grinder.py L43-46. pythonw = GUI subsystem Python, no stdout/stderr console attached. **Any unhandled exception goes nowhere** — including in worker processes.
2. **Logging is file-based** to `grinder.log`. But Python's `logging` module BUFFERS writes; on hard process kill, the trailing N seconds of log entries vanish.
3. **The 50 vs 60 mismatch** (progress.json says 50, rejections.jsonl has 60) suggests at least 10 combos completed but their `progress` log entry (every 5 combos) was never written. Death between rejection write and progress write.
4. **Workers don't recycle.** `mp.Pool(workers)` doesn't pass `maxtasksperchild=N`, so workers live for the entire run. After 50 chunksize=1 combos, each worker has loaded the master CSV (30,645 rows × 6 cols × float64 = ~150MB) and any associated state ~50 times in worker memory. Python's GC reclaims, but fragmentation grows.
5. **Spawn mode on Windows.** Every worker re-imports the entire module tree. If any import is non-deterministic (e.g., a Pool inside an evaluator?), Windows spawn can deadlock.

## Most likely root cause

**Memory pressure → Windows OOM killer.** 4 workers × ~400MB working set + parent + IDE/Claude Code = ~2.5-3GB committed. Windows can kill pythonw silently when memory commit limit is hit (no popup, no error to event log unless administrator-elevated).

Secondary suspect: `runner._patched_filter_constants` monkey-patch (CLAUDE.md OP 15) is process-safe BUT NOT cleanup-safe — if it registers filters lazily and never cleans up, RSS grows monotonically per combo within a single worker.

## Mitigations queued

### T70 (HIGH) — maxtasksperchild=10

Tiny patch to `v14_enhanced_grinder.py` L303:
```python
# BEFORE
with mp.Pool(workers) as pool:

# AFTER (T70)
with mp.Pool(workers, maxtasksperchild=10) as pool:
```

Forces worker recycle every 10 combos. Restores fresh memory. Cost: ~5% throughput hit (worker startup overhead × 4 vs none). Benefit: bounded memory commit.

### T71 (HIGH) — Launcher stderr-to-file

Update `setup/scripts/launch-v14-enhanced-stage1.ps1` to redirect stderr (and stdout, even from pythonw) to a log file via the `2>` PowerShell operator. Even if pythonw is GUI-subsystem, the launcher PS can capture exceptions if pythonw is started with stdio pipes (`UseShellExecute=false`).

### T72 (MED) — gc.collect() between combos

In `evaluate_v14_enhanced_combo`, end the function with `gc.collect()` before returning. Frees the master CSV DataFrame + any intermediate objects per-combo. Adds ~10ms per combo, but prevents fragmentation.

### T73 (MED) — Logging.flush() per progress write

Force `logging.getLogger().handlers[0].flush()` every 5 combos so the LAST seconds of activity are durable on kill.

### T74 (LOW) — RSS watchdog

Sidecar PS script `setup/scripts/grinder-rss-monitor.ps1` that polls `Get-Process -Id <runner_pid>` every 30s and writes RSS to a sidecar JSONL. Run alongside the grinder. Lets us SEE memory ballooning even when grinder logs nothing.

## What's NOT the cause

- **NOT a code bug in `evaluate_v14_enhanced_combo`.** The try/except at L249-256 catches ALL exceptions and writes `execution_error` rejections. No execution_error rejections present in the data — so no Python exception is escaping.
- **NOT data corruption.** Other grinders (sniper Stage 1+2+3+4+5, vwap, odf, regime_switcher) all completed their runs against the SAME master CSV.
- **NOT a deadlock in pool.imap_unordered.** Deadlock would freeze ALL 4 workers at the same combo. We see steady completion to 50, then stop.

## Production impact

**ZERO impact on tomorrow's CPI day.** v14_enhanced is NOT the production strategy — v15 is. The v14_enhanced grinder is RESEARCH-ONLY. Its silent deaths are a NIGHTLY-RESEARCH problem, not a live-trading problem.

Future weekend research blitzes will be more reliable with T70+T71 applied.

## Decision

Queue T70+T71 (small surgical patches) for fire #24 — they take ~5 min each. T72-T74 are nice-to-haves; defer to weekend research session. **No production-risk action needed.**

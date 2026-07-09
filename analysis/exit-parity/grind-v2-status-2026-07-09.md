# Mass-Grind v2 Status — 2026-07-09

## VERDICT: DEAD-INCOMPLETE

The grind stopped writing progress ~5h+ before this check, no live process exists, and no completion marker was ever written. It died silently mid-run — it did not finish and it is not still running.

## The 3 key numbers

| Metric | Value |
|---|---|
| **Progress rows done** | **5,172 / 7,560 (68.41%)** |
| **Funnel rows evaluated** | **327** (216 PASS-P4 elite / 91 PASS-P2 / 20 STOP-P2) |
| **Time since last write** | Progress last wrote **2026-07-09 05:51:15 local**; now (this check) is **2026-07-09 13:03:55 ET** (≈11:04 local) → **~5h13m of silence**, with zero live process the whole time |

---

## Evidence

### 1. Driver script + intended totals (`backtest/autoresearch/mass_grind.py`)

- Combo space: `STRIKES(7) × BLOCK_LR(1) × MIN_TRIG(1) × STOPS(9) × TP1_LEVELS(5) × TP1_QTY(4) × LOCK_TRAIL(3) × TIME_EXIT(2) = 7560` (docstring line 156: `"= 7 x 1 x 1 x 9 x 5 x 4 x 3 x 2 = 7560 combos (v2..."`).
- Confirmed live by the script's own emitted total file — `analysis/recommendations/mass-grind-total.json`:
  ```json
  {"total": 7560}
  ```
- **Completion marker**: the script only writes `OUT` (`analysis/recommendations/mass-grind-v2.json`, or `mass-grind-v2-{shard}.json`) when the `while True:` pool loop reaches a clean `break` (all combos done) — see lines 392-398. **This file does not exist** (`Glob analysis/recommendations/mass-grind-v2*.json` → "No files found"). A completed run would have produced it plus a final stdout line `"DONE. {N} bangers / {M} valid in {mins} min. Best: ..."` — neither exists anywhere on disk.
- Default worker count if unset: `WORKERS = int(os.environ.get("GAMMA_GRIND_WORKERS", "6"))` (line 124) — relevant for the relaunch command below.
- Progress file path (unsharded run, which this is — no `GAMMA_GRIND_SHARD` set): `analysis/recommendations/mass-grind-v2-progress.jsonl`. Resume glob: `mass-grind-v2-progress*.jsonl` (only the unsharded file exists — confirmed via `Glob analysis/recommendations/mass-grind-v2-progress*.jsonl` → single match).

### 2. Row counts vs intended total

```
PROGRESS rows: 5172 / intended 7560
FUNNEL-v2-0 rows: 327
Percent complete: 68.41%
```

Funnel verdict breakdown (`mass-grind-funnel-v2-0.jsonl`, 327 rows):

```
PASS-P4   216
PASS-P2    91
STOP-P2    20
```

(216 P4-elite survivors is a lot — flagged as a "too-good" candidate for a separate audit before anything ships off this data; out of scope for this status check.)

### 3. Last-write timestamps (file mtimes + embedded timestamps)

```
mass-grind-v2-progress.jsonl       7169470 bytes   7/9/2026 5:51:15 AM   (local)
mass-grind-funnel-v2-0.jsonl        193989 bytes   7/9/2026 5:50:05 AM   (local)
```

The funnel's last row carries its own embedded timestamp that matches the file mtime exactly, confirming the clock read is correct (not a filesystem artifact):
```json
"evaluated_at": "2026-07-09T05:50:05"
```

Last 2 progress rows (no crash/error payload — these are ordinary completed-combo results, `op16_reject`/`error` fields show nothing abnormal about the LAST thing it did):
```json
{"label": "ATM:LR0:mt1:stop-40:tp+30%:sell66%:trailing0.22:ts60", ... "edge_capture": 891.3, ... "op16_reject": false, ...}
{"label": "ATM:LR0:mt1:stop-40:tp+30%:sell66%:trailing0.22:ts10", ... "edge_capture": 891.3, ... "op16_reject": false, ...}
```
This matters: the process didn't die *because* of a bad combo — the last recorded combo is a normal, successfully-computed result. Death happened between finishing that combo and starting/finishing the next one, i.e. the **process itself** stopped, not the computation.

### 4. No persisted log for this run

`setup/scripts/grind-watchdog.ps1` is the only script that redirects `mass_grind.py`'s stdout/stderr to disk (`mass-grind-stdout.log` / `mass-grind-stderr.log`), but:
- Its own progress threshold is hardcoded to the **old v1 total (3360)**, and it points at the **non-versioned** `mass-grind-progress.jsonl` / launches plain `-m autoresearch.mass_grind` with no `GAMMA_GRIND_WORKERS` override — it is the legacy v1 watchdog, not v2-aware.
- Both log files it writes are stale from the prior grind generation: `mass-grind-stdout.log` last modified **6/26/2026 10:23:58 AM**, `mass-grind-stderr.log` last modified **6/25/2026 10:37:37 AM** — i.e. **neither was touched during the v2 run at all.**
- `mass-grind-watchdog.log` (the watchdog's own self-log) is also stale — last modified **6/26/2026 2:38:05 PM**.
- The scheduled task that would run any watchdog is confirmed OFF: `Get-ScheduledTask -TaskName 'Gamma_Grind_Watchdog'` → **`State : Disabled`**.
- Per `markdown/planning/CONFIRM-AND-WIRE-REPORT-2026-07-08.md`, this v2 grind was launched ad-hoc in a background shell in that session (`"Launched (background, still running as of this report): ONE mass_grind.py process (GAMMA_GRIND_WORKERS=12...) + ONE mass_grind_funnel.py process"`), not through a script that redirects output to a file. **Conclusion: no stdout/stderr for this specific run was ever captured to disk — the only surviving evidence is the JSONL row data and file mtimes.** A repo-wide glob for `*grind*v2*` and for files touched after 2026-07-08 18:00 turned up only the two JSONL files themselves plus the source `.py`/test files edited earlier that evening while building the v2 grid — no v2-specific log file exists anywhere.

### 5. Live-process check

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.Name -match 'python' -and ($_.CommandLine -match 'mass_grind' -or $_.CommandLine -match 'grind') }
```
Result: **zero matches for `mass_grind` or `mass_grind_funnel`.** The only "grind"-matching processes currently alive are the unrelated **crypto gym harness** (`run-crypto-grinder-keepalive.ps1`, `live_grinder.py --symbol BTC-USD`, PIDs 18692/23796, both created `7/9/2026 7:11:02 AM`) — per project scope (CLAUDE.md: "Trading crypto as an instrument... crypto is gym-only"), these are a completely different subsystem and not the SPY exit-shape grind. **No mass_grind.py or mass_grind_funnel.py process is running.** This rules out STILL-RUNNING.

Note that these crypto-keepalive processes were (re-)created at **7:11 AM local — after** the grind's last progress write (5:51 AM) — confirming the *machine itself* stayed up and kept spawning/running other Python automation well past the grind's death. This was not a machine-wide outage; specifically the mass_grind process(es) went away.

### 6. Cause-of-death signal (circumstantial — flagged, not asserted as fact per OP-33)

Two differential checks were run:

**(a) Windows Event Log — crash vs. external kill.** Per this repo's own debugging doctrine (CLAUDE.md): *"Silent death — clean stderr, no Windows Event Log entry, ~3–5 min cadence — is an external kill, NOT a crash."* Checked Application log (python.exe errors / Application Error / .NET Runtime entries) and System log (unexpected shutdown IDs 41/1074/6006/6008) for the window bracketing the last write (05:30–08:35 local):
```
=== Application log: Error/Warning entries mentioning python, 05:30-08:35 local ===
(none)
=== System log: Kernel-Power / unexpected shutdown 05:30-08:35 local ===
(none)
```
**Zero entries either way.** No crash trace, no reboot. This is the exact "clean silent death" signature the doctrine attributes to an external kill (e.g. reaper or manual `Stop-Process`), not a genuine process crash (no access-violation / unhandled-exception event was logged, and the last-recorded combo result was itself unremarkable — see §3).

**(b) A reaper event fired that morning, but the timing doesn't cleanly line up as the direct cause.** `automation/state/logs/premarket-2026-07-09.log`:
```
2026-07-09 08:30:03 ET REAPED stale: 12556,28560,34008,8136,18924,35216,30812,15676,19144,10628,17856,3004,8068,20484,22532,10800,22532
2026-07-09 08:30:03 ET FIRE attempt=1 et=08:30:03
```
This is `Gamma_Premarket`'s own call into `Stop-StaleClaudeProcesses` (`setup/scripts/_shared.ps1`), which reaped 17 PIDs at 08:30:03 ET. `mass_grind`/`backtest\.venv` are in that function's `$EXEMPT_DAEMONS` list (added 2026-06-25 specifically because an earlier version of this reaper killed a grind — see the code comment at `_shared.ps1` lines 281-286), so on paper the exemption should have protected it. However:
- The reap fired **08:30:03 ET**, which is **~07:51 ET in the machine's own local-vs-ET framing at 05:51 local + 2h offset** — i.e. the reap happened **~39 minutes after** the progress file's last write, not at the same moment.
- Given the grind's own throughput (~1 combo every few seconds across 12 workers, per its `eta = remaining*55/WORKERS/60` estimator), a genuinely-alive process should have kept writing every few seconds through that 39-minute gap — it didn't. **This means whatever killed the grind most likely happened at or shortly after 05:51 local (~07:51 ET), and the 08:30:03 reap is more likely a cleanup of already-orphaned/idle multiprocessing worker remnants than the original cause.**
- The CONFIRM-AND-WIRE-REPORT itself documented a standing contingency for exactly this scenario: *"If premarket checks see slow heartbeat ticks, `Stop-Process` the two `mass_grind` pythons ... and relaunch after 16:00"* — i.e. a manual/scripted kill during premarket hours was an anticipated, sanctioned action, not necessarily a bug.

**Net: root cause is UNVERIFIED.** The evidence rules out a genuine crash (clean Event Log) and rules out STILL-RUNNING (no live process), and is consistent with — but does not conclusively prove — an external kill sometime around 05:51–07:51 local/ET, whether from the reaper, a manual stop, or the documented premarket contingency. No process-level log survives to say definitively which. This is a gap worth closing (redirect stdout/stderr to a persistent log on the next launch) but does not change the completion verdict.

### 7. Downstream phase5 step

`analysis/backtests/mass-grind-phase5.jsonl` — **does not exist** (`Glob analysis/backtests/mass-grind-phase5*` → "No files found", confirmed twice). This is expected/correct: `mass_grind_phase5.py` regenerates this file FROM the v2 funnel data and per doctrine should only run once the grind is actually done — it has not been run, and per the funnel's own `_grind_complete()` gate (`n >= total`, i.e. `>= 7560`), it would have refused to consider the grind complete at 5,172 rows anyway even if manually invoked.

---

## Relaunch command (for the after-close relaunch — NOT executed by this investigation)

Resume-safe: the script reads the union of all `mass-grind-v2-progress*.jsonl` files and skips already-completed labels (`_label(c) not in done_labels`), so this will pick up at combo 5,173/7,560 and only run the remaining ~2,388 combos. The prior mid-run restart (documented in the CONFIRM-AND-WIRE-REPORT, the `-35` stop addition) already proved this resume path loses zero completed results.

```powershell
cd C:\Users\jackw\Desktop\42\backtest
$env:GAMMA_GRIND_WORKERS = "6"
C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe -m autoresearch.mass_grind
```

- Interpreter: `backtest\.venv\Scripts\python.exe` (reaper-exempt via the `backtest\.venv` / `mass_grind` markers in `_shared.ps1`).
- ONE process (per `project_grind_reaper_killer` memory: concurrent grind processes have previously deadlocked on the OPRA cache — one Pool with more workers beats multiple shards).
- `GAMMA_GRIND_WORKERS=6` — **note this is lower than the prior launch's `GAMMA_GRIND_WORKERS=12`** (this is also `mass_grind.py`'s own hardcoded default if the env var is omitted entirely, so `=6` is explicit-but-equivalent to leaving it unset).
- Recommend (not included above since the ask was "command only"): redirect stdout/stderr to a persistent log file this time — this run had zero on-disk log, which is the reason root cause in §6 is unverified.

**Companion process** (also died at the same time, same evidence — needed for the resumed grind's fresh bangers to actually get funneled; not covered by the "workers" instruction since it has no pool):
```powershell
cd C:\Users\jackw\Desktop\42\backtest
$env:GAMMA_FUNNEL_SHARD = "0"
$env:GAMMA_FUNNEL_NSHARDS = "1"
C:\Users\jackw\Desktop\42\backtest\.venv\Scripts\python.exe -m autoresearch.mass_grind_funnel
```

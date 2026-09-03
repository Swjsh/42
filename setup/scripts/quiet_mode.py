"""Quiet Mode -- after-hours blackout so the rig never touches J's machine.

J directive 2026-08-24: "everything needs to be turned off after market hours."
Popups and a 4-worker backtest grind pegging four cores were landing on top of
his gaming session. This is the standing instrument that retires the question.

WHAT IT DOES, in the quiet window (weekday 18:00-23:00 ET, plus weekend 08:00-23:00;
23:00-08:00 is a LOUD maintenance band -- see the band comment below):
  * Disables every non-essential Gamma_* scheduled task, recording each one's
    prior state first so restore is exact.
  * Stops the Kitchen daemon and any project-owned worker pool it spawned, so no
    CPU-heavy grind survives.
  * Leaves the ESSENTIAL set running -- see ESSENTIAL below.

FAIL-OPEN BY DOCTRINE (OP-25). Any error path restores rather than leaving the
rig disabled: a quiet mode that silently eats J's trading day is worse than a
popup. `--enforce` outside the quiet window ALWAYS restores, and the restore is
idempotent, so a crash mid-blackout self-heals on the next 5-minute fire.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import subprocess
import sys
from pathlib import Path

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3) ========================================
# Under pythonw.exe there is no console, so bare print() raises and takes the whole
# process down before anything reaches the log -- verified live 2026-08-24, the scheduled
# task exited 1 in under a second having written nothing at all.
if os.path.basename(sys.executable).lower().startswith("pythonw"):
    _log_dir = Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    sys.stdout = open(_log_dir / "quiet-mode.stdout.log", "a", buffering=1, encoding="utf-8")
    sys.stderr = open(_log_dir / "quiet-mode.stderr.log", "a", buffering=1, encoding="utf-8")
# ========================================================================================

ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = ROOT / "automation" / "state"
RESTORE_FILE = STATE_DIR / "quiet-mode-restore.json"
STATUS_FILE = STATE_DIR / "quiet-mode.json"
HOLD_FILE = STATE_DIR / "quiet-hold.json"
PRESENCE_FILE = STATE_DIR / "quiet-presence.json"
LOG_FILE = STATE_DIR / "quiet-mode.log"

# ET comes from et_clock, never zoneinfo: this box runs Mountain time, and the system
# Python has no tzdata, so ZoneInfo("America/New_York") raises at import under the
# scheduled task's interpreter (verified live 2026-08-24 -- exit 1, nothing logged).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from et_clock import ET_TZ as ET  # noqa: E402
# Reused for the catch-up sweep below (query_tasks / parse_quiet_holds / attribute_quiet_hold)
# rather than re-deriving the same hold-attribution logic a second time in this file.
import scheduled_task_staleness as _sts  # noqa: E402

# The blackout exists to keep the rig off J's EVENING (popups + a 4-worker grind on
# top of his gaming session). It was never meant to be a 16-hour outage.
#
# 2026-08-26 STARVATION FIX. The original 16:00->08:00 window disabled 68 tasks whose
# ONLY trigger falls inside that window -- the entire EOD pipeline, the nightly guard
# suite, the GitHub secrets audit, unattended-health itself. Those tasks could never
# run again: quiet mode disabled them before their trigger time and restored them
# after it, every single night, silently. Two bands fix it without touching J's evening:
#   * a post-close GRACE to 18:00 so the 16:00-17:45 EOD chain completes, and
#   * a LOUD MAINTENANCE band 23:00->08:00, when J is asleep and a popup costs nothing,
#     so the nightly safety/learning layer runs.
QUIET_START_HOUR = 18       # 18:00 ET -- after the EOD chain has finished writing
MAINTENANCE_START_HOUR = 23  # 23:00 ET -- blackout lifts, nightly work runs
MAINTENANCE_END_HOUR = 8     # 08:00 ET -- when Gamma_LaunchTV opens the trading day

# 2026-08-30 WEEKEND STARVATION FIX (J: "its not quiet hours i have a 200/mo plan we're
# not wasting it doing nothing on the weekend").
#
# ROOT CAUSE: the weekend band held ALL 116 non-essential tasks down from 08:00 to 23:00,
# so every Saturday and Sunday the kitchen, the futures lane, the multi-symbol lane, the
# prospector and the conductor were off for 30 of the weekend's 48 hours -- measured live
# Sun 2026-08-30 12:07 ET: 116 held down, kitchen daemon dead, last free-tier task 4h old.
#
# The original directive was never "do no work at the weekend". It was "no popups and no
# 4-worker grind on top of my gaming session" -- a CPU-and-focus constraint, which the
# PRESENCE GATE below now enforces directly and far better than a clock ever did. Holding
# the whole fleet down on top of that is belt-and-braces paid for in a dark research day.
#
# So the weekend daytime becomes a RESEARCH band: the headless, $0, IO-bound producers run
# (kitchen on free-tier models, futures lane, multi-symbol lane, prospector, conductor),
# while the genuinely core-pegging grinders below stay held. J's weekend EVENING is
# untouched -- 18:00-23:00 is still a full blackout, exactly as on a weekday -- and a
# fullscreen game still takes everything down through the presence gate whatever the clock
# says, because that gate reads the real constraint rather than guessing at it.
WEEKEND_RESEARCH_START_HOUR = MAINTENANCE_END_HOUR   # 08:00 ET
WEEKEND_RESEARCH_END_HOUR = QUIET_START_HOUR         # 18:00 ET -- J's evening begins

# The core-peggers. These are what actually landed on J's gaming session, so they are the
# ONLY thing the research band still holds down. Everything else is network-bound: it waits
# on an HTTP response, it does not eat a core.
HEAVY_TASKS = {
    "Gamma_EngineStressSwarm",      # spawns a swarm of concurrent model consults
    "Gamma_CryptoGrinderKeepalive", # revives the multi-worker crypto grinder
    "Gamma_GymSession",             # full gym run, all validators
    "Gamma_GuardsFull",             # full pytest suite
    "Gamma_DressRehearsal",         # end-to-end replay
    "Gamma_TwinChaos",              # chaos harness
    "Gamma_EodFullAudit",           # heavy audit sweep
    "Gamma_EodDeepDive",            # heavy replay + analysis
}

# Tasks that stay alive even in the blackout.
#   - the trading chain, so a market day is never lost to quiet mode
#   - the window-leak detector, which IS the popup guard
#   - quiet mode itself, or it could never restore
ESSENTIAL = {
    "Gamma_QuietMode",
    "Gamma_WindowLeakDetectorKeepalive",
    # Cockpit action-cards/army-view fire path (build spec sec 4/7 step 8, 2026-08-29) posts
    # to the companion at :4317 -- disabling it mid-quiet-window silently breaks that path
    # with no error surfaced to J (the click just does nothing). Node process, $0, read-only
    # liveness probe -- no reason to hold it down like the LLM/CPU producers below.
    "Gamma_CompanionKeepalive",
    "Gamma_LaunchTV",
    "Gamma_TvWatchdog",
    "Gamma_Premarket",
    "Gamma_PremarketReadiness",
    "Gamma_PreopenReadiness",
    "Gamma_ScoutPremarket",
    "Gamma_OpenBellStatus",
    "Gamma_HeartbeatCore",
    "Gamma_Heartbeat",
    "Gamma_Heartbeat_Aggressive",
    "Gamma_SightBeacon",
    "Gamma_MarketKeepAwake",
    # Its WATCHDOG must be as essential as the daemon it guards (2026-08-31). Registering
    # it revealed the hole: Gamma_MarketKeepAwake was already ESSENTIAL, so quiet mode left
    # the daemon running while disabling the only thing that would notice it die -- and
    # dying silently mid-session is precisely this daemon's failure mode (09:23 ET that
    # day, 99 ticks in, empty stderr). A presence hold can persist past 23:00 into the
    # 07:47 ET first fire, so the clock bands alone do not close it. $0, read-only
    # liveness probe -- same justification as Gamma_WindowLeakDetectorKeepalive above.
    "Gamma_MarketKeepAwakeKeepalive",
    "Gamma_EodFlatten",
    "Gamma_EodFlatten_Aggressive",
    "Gamma_EodFlattenCore",
    # Early-close flatten check (B2, 2026-09-01). ESSENTIAL is an exact-match set, NOT a
    # glob -- "Gamma_EodFlatten*" does not cover this task; it must be listed explicitly or
    # quiet mode would silently disable the one task that acts before the 2026-11-27/12-24
    # 13:00 ET early closes. Fires at 12:32 ET, well inside the LOUD weekday band anyway,
    # but listed here for the same defense-in-depth reason as the other flatten backstops.
    "Gamma_EodFlattenEarlyClose",
    # Independent open-position watchdog (TASK W1, 2026-09-01, queue.md
    # DEAD-MANS-SWITCH-POSITION-FLATTENER) -- trading-critical in exactly the same sense as
    # the flatten backstops above: it only ever acts on an ENGINE-STALE arm holding an open
    # SPY 0DTE position, which is precisely the RTH window quiet mode's LOUD weekday
    # 08:00-18:00 band already covers, but disabling it here would be the same silent-gap
    # class of bug the flatten-coverage fix (2026-08-18) exists to prevent.
    "Gamma_DeadMansSwitch",
    # Futures trading chain (2026-09-01, queue.md QUIET-MODE-BLACKS-OUT-THE-SUNDAY-
    # FUTURES-OPEN). CME equity-index futures trade Sunday 18:00 ET -> Friday 17:00 ET;
    # the SPY chain above is exempted "so a market day is never lost to quiet mode" but
    # ESSENTIAL is 100% SPY-named, so every Sunday 18:00-23:00 ET -- the first five hours
    # of the futures week, itself a weekend-quiet band per WEEKEND_RESEARCH_END_HOUR --
    # and every weekday 18:00-23:00 ET (also live GLOBEX time) silently disabled the
    # futures trading chain on the identical rationale that already exempts SPY. Verified
    # before adding: all three launch through the flash-free wscript->run_exe_hidden.vbs->
    # pythonw hidden-spawn chain (install-futures-trader.ps1 / install-futures-broker-
    # lane.ps1 / install-futures-mirror.ps1, grepped live) -- no popup/window-flash risk,
    # so this does not recreate J's #1 complaint. Currently a no-op in practice (all three
    # only trigger 09:30-16:00/16:05 ET weekdays, already inside the LOUD trading-day
    # band) -- this closes the gap for when a Sunday-open producer is added, and is what
    # test_essential_set_covers_the_futures_trading_chain pins.
    "Gamma_FuturesTrader",
    "Gamma_FuturesBrokerLane",
    "Gamma_FuturesMirror",
    # The staleness reporter (2026-09-02). Not trading-critical -- it is here because a
    # monitor its own subject can switch off is not a monitor. THIS file's presence hold is
    # what made Gamma_GuardsFull -- the ~11,400-test regression suite -- dark from 08-31 to
    # 09-02: a trigger inside a hold is skipped, and because the task was Disabled rather
    # than merely unavailable, Windows' StartWhenAvailable cannot recover the fire. Nothing
    # noticed, because every surface reads State/LastTaskResult, neither of which moves when
    # a task never starts. scheduled_task_staleness.py reads LastRunTime +
    # NumberOfMissedRuns and names this hold as the cause -- so leaving it disable-able
    # would mean the first thing a long blackout silences is the alarm about the blackout.
    # It fires 05:45 ET (inside the LOUD band), $0, pure stdlib, report-only: it never
    # enables, disables, starts or kills anything, so exempting it cannot affect J's
    # evening. Same self-silencing class as the prereg-hygiene orphan-proxy bug (09-01).
    "Gamma_TaskStaleness",
}

# Command-line substrings identifying project-owned CPU hogs to stop in the blackout.
HEAVY_PROCESS_MARKERS = (
    "kitchen_daemon.py",
    "autoresearch.",
    "multiprocessing-fork",
    "shotgun_scalper",
    "_grind",
)

# === CATCH-UP SWEEP (QUIET-HOLD-CATCH-UP-SWEEP, queue.md 2026-09-02) ====================
# A trigger that fires while its task is Disabled is SKIPPED, and because the task was
# Disabled rather than merely unavailable, Windows' StartWhenAvailable cannot recover the
# fire -- proven 7/7 over 2026-09-01 (Gamma_GuardsFull et al went dark exactly this way).
# Promoted from hygiene to gate-blocking work 2026-09-02: the go-live gate's registered
# prod-shadow window (automation/state/prod-shadow-designation.json, 2026-09-01..2026-09-29,
# pre-registered BEFORE any result was seen) has zero slack -- a single further silently-lost
# day puts criterion 5 out of reach of its own 20-scored-day bar.
#
# CURATED ALLOWLIST, deliberately a POSITIVE list not a denylist (constraint (a)). Every name
# below is $0-or-near-$0, report/audit/monitor-only, places no order, arms no live money, and
# is NOT in HEAVY_TASKS. Anything not on this list is left to Gamma_TaskStaleness + a
# deliberate manual start -- silence is the safe default for anything that could touch a
# broker or capital on stale data.
CATCHUP_ELIGIBLE = {
    "Gamma_McpDailyAudit",   # MCP round-trip health probe (Alpaca+TV), no orders, ~$0.10
    "Gamma_GitHubAudit",     # secrets/privacy scan of tracked files, public repo, $0
    "Gamma_SpendSummary",    # cost rollup, $0
    "Gamma_OosCheck",        # OOS drift check, report-only, $0
    "Gamma_LicenseMonitor",  # notify-only RED->green license detector, $0
    "Gamma_GateExpiryCheck", # prereg gate-expiry monitor, $0
    "Gamma_RosterLiveness",  # model-roster liveness probe, $0
    "Gamma_PreregHygiene",   # prereg staleness/orphan/malformed-JSON monitor, $0
    "Gamma_RuleBreakAudit",  # rule-break ledger auditor (go-live criterion 4), report-only, $0
}
# Explicitly considered and EXCLUDED, stated so a future editor does not have to re-derive
# why (constraint (a)/(b)):
#   Gamma_KalshiAuto            -- places orders off a next-day weather prediction; restarting
#                                  it hours late trades on stale NOAA data, a different act
#                                  from re-running an audit.
#   Gamma_FuturesBrokerProbe    -- broker-touching by name; excluded conservatively even
#                                  though "probe" suggests read-only.
#   Gamma_GuardsFull            -- CORRECTED 2026-09-03 (queue item
#                                  GUARDS-FULL-NEVER-RUNS-ON-A-GAMING-EVENING). The comment
#                                  that used to sit here claimed restarting it "would hit the
#                                  same 'started, then killed mid-run by the next hold'
#                                  failure" as the HEAVY_TASKS blackout. That was a PROVENANCE
#                                  ERROR: read _stop_heavy_processes() (below, ~line 425) --
#                                  the blackout kills ONLY a process whose CommandLine matches
#                                  HEAVY_PROCESS_MARKERS (kitchen_daemon.py, autoresearch.,
#                                  multiprocessing-fork, shotgun_scalper, _grind). A pytest run
#                                  launched by guard_runner_full.py matches none of those
#                                  markers, so a later hold DISABLES the scheduled task
#                                  (blocking its NEXT trigger) but never kills a run already in
#                                  flight. The real constraint was only "never launch a
#                                  core-pegger while J is at the machine", which the presence
#                                  gate already encodes -- so Gamma_GuardsFull is now in
#                                  HEAVY_CATCHUP_ELIGIBLE below instead of excluded outright,
#                                  gated by its own narrower band + a live presence check + a
#                                  live HEAVY_PROCESS_MARKERS check (see _heavy_catchup_pass).
#   Gamma_GuardsNightly         -- left excluded. It was not this item's subject, runs ~35
#                                  data-heavy backtests, and needs its own runtime/duration
#                                  check (the 23:00-06:30 heavy band below was sized for
#                                  Gamma_GuardsFull's ~25 minutes, not verified against this
#                                  task) before it can be added on the same reasoning.
#   Gamma_ConductorWeekend      -- spawns a full autonomous Sonnet session with its own
#                                  ship/commit authority; a scheduler-level catch-up should
#                                  not silently multiply conductor fires.
CATCHUP_MAX_STARTS = 5  # constraint (d): cap started per fire, most-overdue first

# === HEAVY CATCH-UP TIER (GUARDS-FULL-NEVER-RUNS-ON-A-GAMING-EVENING, queue.md 2026-09-02)
# =========================================================================================
# A second, even narrower, positive allowlist -- deliberately never merged into
# CATCHUP_ELIGIBLE above, so a future edit to one list cannot silently widen the other's
# (very different) safety envelope. Only Gamma_GuardsFull for now (see the exclusion note
# above); Gamma_GuardsNightly/Gamma_GymSession are NOT here and each needs its own runtime
# check before being added -- do not just copy this set to include them.
HEAVY_CATCHUP_ELIGIBLE = {"Gamma_GuardsFull"}

# Gamma_GuardsFull takes ~25 minutes end-to-end (measured via guard-watch-full.json
# durations). Starting it any later than 06:30 risks it still be running at 08:00 ET when
# Gamma_LaunchTV opens the trading day -- narrower than the general LOUD maintenance band
# (23:00-08:00) for exactly that reason.
HEAVY_BAND_END_HOUR = 6
HEAVY_BAND_END_MINUTE = 30


def _in_loud_heavy_band(now: dt.datetime) -> bool:
    """23:00-06:30 ET -- the heavy tier's own, narrower, slice of the LOUD maintenance band.

    Never the weekday trading band and never the weekend research band -- both checked
    explicitly per constraint (c) even though the 23:00-06:30 hour range is disjoint from
    both (08:00-18:00) by construction, so this cannot silently start passing if either of
    those bands is ever widened to touch midnight.
    """
    if _in_trading_band(now) or in_research_band(now):
        return False
    hour, minute = now.hour, now.minute
    if hour >= MAINTENANCE_START_HOUR:
        return True
    if hour < HEAVY_BAND_END_HOUR:
        return True
    return hour == HEAVY_BAND_END_HOUR and minute < HEAVY_BAND_END_MINUTE


def _heavy_process_running() -> bool:
    """True if another guard suite / pytest run (GUARD_SUITE_MARKERS, below) is alive right
    now. Read-only: checks, never kills. NOT the blackout's HEAVY_PROCESS_MARKERS -- see the
    note on GUARD_SUITE_MARKERS for why that made the heavy tier dead on arrival.

    Deliberately fail-CLOSED (unlike most of this file's fail-open error paths): this gate
    decides whether to START new heavy work, not whether to restore/protect the trading day,
    so an unknown process state is a reason to wait, not a reason to pile a second pytest run
    on top of one that might already be running (constraint (d)'s whole point).
    """
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | "
        "Select-Object CommandLine | ConvertTo-Json -Depth 3 -Compress"
    )
    try:
        raw = _ps(script).strip()
    except Exception as exc:  # noqa: BLE001
        _log(f"WARN heavy-process probe failed ({exc}) -- treating as busy (fail-safe)")
        return True
    if not raw:
        return False
    try:
        rows = json.loads(raw)
    except ValueError as exc:
        _log(f"WARN heavy-process probe returned unparseable JSON ({exc}) -- treating as busy")
        return True
    if isinstance(rows, dict):
        rows = [rows]
    for row in rows:
        cl = row.get("CommandLine") or ""
        if any(m in cl for m in GUARD_SUITE_MARKERS):
            return True
    return False


# What the heavy-tier gate (d) actually guards against: a SECOND guard suite / pytest run
# stacked on one already in flight. It deliberately does NOT use HEAVY_PROCESS_MARKERS
# (2026-09-03 00:52 ET): kitchen_daemon.py is a permanent resident and the kitchen spawns
# autoresearch grinds most nights, so gating on those markers made Gamma_GuardsFull
# uncatchable on exactly the nights it is needed -- dead on arrival, observed live on the
# first night. A pytest run beside a grind only slows both; the presence gate (b) is what
# protects J's frame rate, and the blackout's own kill path still only targets the markers.
GUARD_SUITE_MARKERS = (
    "guard_runner_full",
    "guard_runner_slow",
    # WHOLE-suite runs only ("pytest tests/ ..."): a bare "pytest" marker matched every
    # builder session's 2-second per-file run, and with Sonnet builders working all night one
    # is nearly always alive -- observed 2026-09-03 01:00 ET, the tier deferred 7 cycles in a
    # row behind a single-file test run. A per-file run is not the stacking this gate exists
    # to prevent.
    "pytest tests/ ",
    "pytest tests\ ",
)


def _heavy_catchup_pass(rows: list[dict], holds: list[tuple[dt.datetime, dt.datetime]],
                        latest_hold_end: dt.datetime, now: dt.datetime) -> list[str]:
    """The heavy tier: same attribution/idempotency rules as the light tier (constraints
    (a)/(e)), plus three extra gates the light tier does not need because none of its members
    are CPU-heavy:
      (b) no presence hold active now or within the last 15 minutes -- presence_hold()
          already folds the linger window in via _presence_linger, so this reuses it rather
          than re-deriving a foreground check.
      (c) ET inside the narrow 23:00-06:30 heavy-safe band (_in_loud_heavy_band above).
      (d) no other guard suite / pytest run already alive (_heavy_process_running,
          GUARD_SUITE_MARKERS) -- a second full pytest run stacked on a running one is the
          exact stacking this gate exists to prevent. Kitchen grinds do NOT block it.
    Called by _catchup_sweep AFTER the light tier and only with whatever budget the light
    tier left (constraint (f)); the caller enforces the shared CATCHUP_MAX_STARTS cap.
    """
    if not _in_loud_heavy_band(now):
        return []
    held = presence_hold(now)
    if held:
        _log(f"CATCH-UP SWEEP (heavy): held by presence ({held})")
        return []
    started: list[str] = []
    for row in rows:
        name = row.get("name")
        if name not in HEAVY_CATCHUP_ELIGIBLE:
            continue
        cause = _sts.attribute_quiet_hold(row, holds, now=now)
        if not cause:
            continue
        last_run = _sts._parse_dt(row.get("lastRun"))
        if _sts.is_never_ran(last_run):
            last_run = None
        if last_run is not None and last_run >= latest_hold_end:
            continue  # constraint (e): already ran since the hold closed
        if _heavy_process_running():
            _log(f"CATCH-UP SWEEP (heavy): {name} hold-attributed but a guard-suite/pytest "
                 "process is already running -- deferring rather than stacking")
            continue
        try:
            _ps(f"Start-ScheduledTask -TaskName '{name}' -ErrorAction Stop")
            started.append(name)
            _log(f"CATCH-UP SWEEP (heavy): started {name}: {cause}")
        except Exception as exc:  # noqa: BLE001
            _log(f"WARN heavy catch-up start failed for {name}: {exc}")
    return started
# ========================================================================================


def _catchup_sweep(now: dt.datetime) -> list[str]:
    """Start, at most once each this fire, CATCHUP_ELIGIBLE tasks that genuinely missed a
    scheduled fire inside a quiet-mode hold. Returns the names actually started.

    Constraints from the queue item, each enforced here:
      (a) allowlist only -- see CATCHUP_ELIGIBLE above.
      (b) HEAVY_TASKS are never in the light allowlist, so they are never touched by the
          light-tier loop below.
      (c) only DAILY triggers can match -- attribute_quiet_hold() only ever attributes a
          daily trigger; a repeater self-heals on its own next tick and needs no help.
      (d) capped at CATCHUP_MAX_STARTS, most-overdue (highest NumberOfMissedRuns) first,
          and the caller gates this out of the weekday trading band.

    HEAVY TIER (GUARDS-FULL-NEVER-RUNS-ON-A-GAMING-EVENING, 2026-09-03): after the light
    tier above, _heavy_catchup_pass() may start a member of HEAVY_CATCHUP_ELIGIBLE
    (currently only Gamma_GuardsFull) subject to its own extra gates -- see that function's
    docstring. Runs last and shares this function's CATCHUP_MAX_STARTS cap.

    Idempotency: a candidate is skipped if it has already run since the most recent hold
    closed (real LastRunTime advances past the hold), so a 5-minute enforcer cadence cannot
    restart the same task over and over for as long as the hold stays in the 7-day
    attribution lookback.

    Fail-open everywhere (OP-25): any read/query error yields an empty sweep, never an
    exception -- this must never be able to block the restore that already happened above it.
    """
    if _in_trading_band(now):
        return []  # constraint (d): never launch a grind into the premarket/trading day
    try:
        rows = _sts.query_tasks()
    except Exception as exc:  # noqa: BLE001
        _log(f"WARN catch-up sweep could not query tasks ({exc})")
        return []
    if not rows:
        return []
    try:
        quiet_text = LOG_FILE.read_text(encoding="utf-8", errors="replace") if LOG_FILE.exists() else None
    except OSError:
        quiet_text = None
    holds = _sts.parse_quiet_holds(quiet_text, now=now)
    if not holds:
        return []  # no attributable hold -- do not guess

    latest_hold_end = max(h[1] for h in holds)
    # OPEN-HOLD GUARD (2026-09-03 00:45 ET live incident): parse_quiet_holds closes an
    # unterminated trailing hold AT `now`, so while a hold is still open latest_hold_end
    # advances every enforcer cycle and the idempotency test below ("already ran since the
    # hold closed") can never be satisfied -- the sweep restarted the same five tasks every
    # 5 minutes for an hour (McpDailyAudit twelve times an hour). The LOUD-band presence
    # path routes a fullscreen app to the research band without writing QUIET OFF, which is
    # exactly this state. Catch-up is for AFTER a hold closes; an open hold defers it.
    if latest_hold_end >= now - dt.timedelta(seconds=5):
        _log("CATCH-UP SWEEP deferred: the latest hold is still OPEN (no QUIET OFF after the "
             "last QUIET HELD) -- catch-up only runs after a hold CLOSES")
        return []
    candidates: list[tuple[str, str, int]] = []
    for row in rows:
        name = row.get("name")
        if name not in CATCHUP_ELIGIBLE:
            continue
        cause = _sts.attribute_quiet_hold(row, holds, now=now)
        if not cause:
            continue
        last_run = _sts._parse_dt(row.get("lastRun"))
        if _sts.is_never_ran(last_run):
            last_run = None
        if last_run is not None and last_run >= latest_hold_end:
            continue  # already ran since the hold closed -- nothing to catch up
        candidates.append((name, cause, int(row.get("missedRuns") or 0)))

    # NOTE: deliberately no early "if not candidates: return []" here -- an empty light tier
    # must still let the heavy tier below get its turn (constraint (f) requires it to run
    # every fire the clock/presence/process gates allow, independent of whether any
    # CATCHUP_ELIGIBLE task also happened to miss a fire).
    candidates.sort(key=lambda c: (-c[2], c[0]))

    started: list[str] = []
    for name, cause, _missed in candidates[:CATCHUP_MAX_STARTS]:
        try:
            _ps(f"Start-ScheduledTask -TaskName '{name}' -ErrorAction Stop")
            started.append(name)
            _log(f"CATCH-UP started {name}: {cause}")
        except Exception as exc:  # noqa: BLE001
            _log(f"WARN catch-up start failed for {name}: {exc}")

    # Heavy tier -- constraint (f): LAST, and only with whatever budget the light tier above
    # left in the shared CATCHUP_MAX_STARTS cap. A deliberately separate positive list
    # (HEAVY_CATCHUP_ELIGIBLE), never merged with CATCHUP_ELIGIBLE.
    if len(started) < CATCHUP_MAX_STARTS:
        started.extend(_heavy_catchup_pass(rows, holds, latest_hold_end, now))
    return started
# ========================================================================================


NO_WINDOW = 0x08000000
STATE_READY = "3"  # TASK_STATE: 1=Disabled 2=Queued 3=Ready 4=Running


def _log(msg: str) -> None:
    line = f"{dt.datetime.now(ET).isoformat()} {msg}"
    # The file is the durable record; the console is a nicety. Never let a dead
    # stdout stop the log line from landing on disk.
    try:
        print(line, flush=True)
    except (OSError, ValueError, AttributeError):
        pass
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except OSError:
        pass


def _ps(script: str) -> str:
    """Run PowerShell and return stdout. Raises on non-zero exit."""
    out = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
        capture_output=True, text=True, timeout=180, creationflags=NO_WINDOW,
    )
    if out.returncode != 0:
        raise RuntimeError(f"powershell failed: {out.stderr.strip()[:400]}")
    return out.stdout


def in_quiet_window(now: dt.datetime | None = None) -> bool:
    """True when the rig must stay off J's machine.

    Bands, in precedence order:
      23:00-08:00 any day  -> LOUD  (maintenance: J is asleep, nightly work runs)
      weekend              -> quiet
      weekday 18:00-23:00  -> quiet (J's evening)
      weekday 08:00-18:00  -> LOUD  (trading day + the post-close EOD chain)
    """
    now = now or dt.datetime.now(ET)
    hour = now.hour
    # Maintenance band wins over everything, weekends included: a nightly guard that
    # only runs Mon-Fri is a guard that misses every weekend regression.
    if hour >= MAINTENANCE_START_HOUR or hour < MAINTENANCE_END_HOUR:
        return False
    if now.weekday() >= 5:
        # Weekend DAYTIME is the research band (loud-but-light); only the evening is quiet.
        return hour >= WEEKEND_RESEARCH_END_HOUR
    return hour >= QUIET_START_HOUR


def in_research_band(now: dt.datetime | None = None) -> bool:
    """Weekend 08:00-18:00 ET: light producers run, core-peggers stay down.

    Deliberately narrower than "not quiet": on a WEEKDAY the same hours are the trading
    day, when the heavy tasks are wanted too. This band exists only because J is at the
    machine on a weekend afternoon, which is a reason to spare his cores -- not a reason
    to stop thinking.
    """
    now = now or dt.datetime.now(ET)
    return (now.weekday() >= 5
            and WEEKEND_RESEARCH_START_HOUR <= now.hour < WEEKEND_RESEARCH_END_HOUR)


def _gamma_tasks() -> dict[str, str]:
    raw = _ps(
        "Get-ScheduledTask | Where-Object {$_.TaskName -like 'Gamma*'} | "
        "Select-Object TaskName,State | ConvertTo-Json -Depth 3 -Compress"
    ).strip()
    if not raw:
        return {}
    data = json.loads(raw)
    if isinstance(data, dict):
        data = [data]
    return {r["TaskName"]: str(r["State"]) for r in data}


def _set_tasks(names: list[str], enable: bool) -> int:
    if not names:
        return 0
    verb = "Enable-ScheduledTask" if enable else "Disable-ScheduledTask"
    ok = 0
    # Chunk so one bad name cannot poison the whole batch.
    for start in range(0, len(names), 25):
        chunk = names[start:start + 25]
        quoted = ",".join("'" + n.replace("'", "''") + "'" for n in chunk)
        script = (
            "foreach($n in @(" + quoted + ")){ try{ " + verb + " -TaskName $n "
            "-ErrorAction Stop | Out-Null; 'OK' } catch { 'FAIL' } }"
        )
        try:
            ok += _ps(script).count("OK")
        except Exception as exc:  # noqa: BLE001 -- surfaced, never swallowed
            _log(f"WARN task batch {verb} failed: {exc}")
    return ok


def _load_restore_list() -> list[str]:
    if not RESTORE_FILE.exists():
        return []
    try:
        return list(json.loads(RESTORE_FILE.read_text(encoding="utf-8")).get("restore_to_ready", []))
    except (OSError, ValueError) as exc:
        _log(f"WARN unreadable restore file ({exc}) -- treating as empty")
        return []


def _save_restore_list(names: list[str]) -> None:
    RESTORE_FILE.write_text(json.dumps({
        "recorded_at": dt.datetime.now(ET).isoformat(),
        "restore_to_ready": sorted(set(names)),
    }, indent=2), encoding="utf-8")


def _stop_heavy_processes() -> list[str]:
    """Kill project-owned CPU hogs. Never touches anything outside the repo path."""
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name like '%python%'\" | "
        "Select-Object ProcessId,CommandLine | ConvertTo-Json -Depth 3 -Compress"
    )
    try:
        raw = _ps(script).strip()
    except Exception as exc:  # noqa: BLE001
        _log(f"WARN could not enumerate processes: {exc}")
        return []
    if not raw:
        return []
    rows = json.loads(raw)
    if isinstance(rows, dict):
        rows = [rows]

    me = os.getpid()
    root = str(ROOT)
    killed: list[str] = []
    for row in rows:
        cl = row.get("CommandLine") or ""
        pid = row.get("ProcessId")
        if pid == me or not cl:
            continue
        # Two-part gate: must belong to this repo AND look like heavy R&D.
        # multiprocessing workers carry no repo path, so they match by marker alone.
        if root not in cl and "multiprocessing-fork" not in cl:
            continue
        if not any(m in cl for m in HEAVY_PROCESS_MARKERS):
            continue
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"],
                           capture_output=True, timeout=30, creationflags=NO_WINDOW)
            killed.append(f"{pid}:{cl[:70]}")
        except Exception as exc:  # noqa: BLE001
            _log(f"WARN kill {pid} failed: {exc}")
    return killed


# === PRESENCE GATE (J 2026-08-29) =======================================================
# The 23:00 ET maintenance band assumes J is asleep. On 2026-08-29 at 23:30 ET he was
# gaming: the blackout lifted, ~68 tasks fired at once, and two of them flashed a console
# window that stole focus mid-match. The clock was never the real constraint -- "is J at
# the machine" is. This holds the blackout while a fullscreen app owns the foreground.
#
# FAIL-OPEN: every path here returns "no hold" on error, so a broken detector degrades to
# exactly the clock-only behaviour that shipped before it.
GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000


def _foreground_fullscreen() -> str | None:
    """Return the foreground exe name if it is genuinely fullscreen, else None.

    The discriminator is window STYLE, not size. A merely MAXIMISED window (browser,
    terminal, editor) keeps WS_CAPTION/WS_THICKFRAME and its rect also covers the
    monitor -- matching on geometry alone would hold the blackout forever and starve
    the nightly maintenance band. Fullscreen and borderless-fullscreen games drop both
    styles, which is what this tests.
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None

        style = user32.GetWindowLongW(hwnd, GWL_STYLE)
        if style & (WS_CAPTION | WS_THICKFRAME):
            return None  # framed window -> not a fullscreen app

        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]

        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        mon = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        if not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return None
        m = mi.rcMonitor
        if (rect.left, rect.top, rect.right, rect.bottom) != (m.left, m.top, m.right, m.bottom):
            return None

        # Name it for the log -- diagnosing "why did quiet mode hold" needs the culprit.
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        name = f"pid {pid.value}"
        try:
            kernel32 = ctypes.windll.kernel32
            h = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
            if h:
                buf = ctypes.create_unicode_buffer(512)
                size = wintypes.DWORD(512)
                if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
                    name = os.path.basename(buf.value) or name
                kernel32.CloseHandle(h)
        except Exception:  # noqa: BLE001 -- naming is a nicety, the hold is the point
            pass
        return name
    except Exception as exc:  # noqa: BLE001
        _log(f"WARN fullscreen probe failed ({exc}) -- no presence hold")
        return None


def _manual_hold() -> str | None:
    """Honour an explicit `--hold` until its expiry."""
    if not HOLD_FILE.exists():
        return None
    try:
        until = dt.datetime.fromisoformat(
            json.loads(HOLD_FILE.read_text(encoding="utf-8"))["until"])
    except (OSError, ValueError, KeyError) as exc:
        _log(f"WARN unreadable hold file ({exc}) -- clearing")
        HOLD_FILE.unlink(missing_ok=True)
        return None
    if dt.datetime.now(ET) >= until:
        HOLD_FILE.unlink(missing_ok=True)
        return None
    return f"manual hold until {until:%H:%M %Z}"


def _in_trading_band(now: dt.datetime | None = None) -> bool:
    """Weekday 08:00-18:00 ET. A presence hold must NEVER reach into the trading day."""
    now = now or dt.datetime.now(ET)
    return now.weekday() < 5 and MAINTENANCE_END_HOUR <= now.hour < QUIET_START_HOUR


# Alt-tabbing out of a game for thirty seconds must not restore 116 tasks and put the
# popups straight back on screen. The hold LINGERS past the last sighting, so a glance
# at Discord costs nothing and only genuinely walking away lifts the blackout.
PRESENCE_LINGER_MIN = 15


def _remember_presence(app: str, now: dt.datetime) -> None:
    try:
        PRESENCE_FILE.write_text(json.dumps(
            {"last_fullscreen_at": now.isoformat(), "app": app}, indent=2), encoding="utf-8")
    except OSError as exc:
        _log(f"WARN could not record presence ({exc})")


def _presence_linger(now: dt.datetime) -> str | None:
    if not PRESENCE_FILE.exists():
        return None
    try:
        data = json.loads(PRESENCE_FILE.read_text(encoding="utf-8"))
        seen = dt.datetime.fromisoformat(data["last_fullscreen_at"])
    except (OSError, ValueError, KeyError):
        PRESENCE_FILE.unlink(missing_ok=True)
        return None
    age_min = (now - seen).total_seconds() / 60
    if age_min >= PRESENCE_LINGER_MIN:
        PRESENCE_FILE.unlink(missing_ok=True)
        return None
    return (f"linger: {data.get('app', 'fullscreen app')} was foreground "
            f"{age_min:.0f}m ago (<{PRESENCE_LINGER_MIN}m)")


def presence_hold(now: dt.datetime | None = None) -> str | None:
    """Reason to stay quiet despite the clock saying LOUD, or None."""
    now = now or dt.datetime.now(ET)
    if _in_trading_band(now):
        return None
    manual = _manual_hold()
    if manual:
        return manual
    app = _foreground_fullscreen()
    if app:
        _remember_presence(app, now)
        return f"fullscreen app in foreground ({app})"
    return _presence_linger(now)
# ========================================================================================


def _write_status(active: bool, detail: dict) -> None:
    STATUS_FILE.write_text(json.dumps({
        "quiet_active": active,
        "updated_at": dt.datetime.now(ET).isoformat(),
        "quiet_window_et": (
            f"quiet {QUIET_START_HOUR:02d}:00-{MAINTENANCE_START_HOUR:02d}:00 ET every day "
            f"(J's evening); LOUD maintenance {MAINTENANCE_START_HOUR:02d}:00-"
            f"{MAINTENANCE_END_HOUR:02d}:00; weekend {WEEKEND_RESEARCH_START_HOUR:02d}:00-"
            f"{WEEKEND_RESEARCH_END_HOUR:02d}:00 = RESEARCH band (light producers run)"
        ),
        **detail,
    }, indent=2), encoding="utf-8")


def go_research() -> int:
    """Weekend daytime: restore the light producers, keep the core-peggers down.

    Written as restore-then-hold rather than a selective enable so it is idempotent and
    self-healing: whatever a previous fire left disabled, this converges to exactly
    "everything except HEAVY_TASKS", and it does NOT kill running processes -- a kitchen
    task mid-flight through a free-tier model call is precisely the work this band exists
    to allow.
    """
    tasks = _gamma_tasks()
    if not tasks:
        _log("ERROR no Gamma tasks enumerated -- refusing to act")
        return 1

    wanted = _load_restore_list()
    light = [n for n in wanted if n not in HEAVY_TASKS]
    heavy_up = [n for n, state in tasks.items()
                if n in HEAVY_TASKS and state == STATE_READY]

    # The heavy set must stay on the restore list, or the 23:00 maintenance band would
    # never bring it back: that list is the ONLY record of what quiet mode took down.
    enabled = _set_tasks(light, enable=True)
    held = _set_tasks(heavy_up, enable=False)
    _log(f"RESEARCH BAND: light_up={enabled}/{len(light)} heavy_held={held}")
    caught_up = _catchup_sweep(dt.datetime.now(ET))
    caught_up_light, caught_up_heavy = _log_and_split_catchup(caught_up)
    _write_status(False, {
        "band": "weekend-research",
        "light_enabled": enabled,
        "light_expected": len(light),
        "heavy_held_down": sorted(HEAVY_TASKS),
        "caught_up": caught_up_light,
        "caught_up_heavy": caught_up_heavy,
        "note": ("weekend daytime -- headless $0 producers run, core-peggers held. "
                 "A fullscreen app still triggers a full blackout via the presence gate."),
    })
    return 0


def go_quiet() -> int:
    tasks = _gamma_tasks()
    if not tasks:
        _log("ERROR no Gamma tasks enumerated -- refusing to act")
        return 1

    newly = [n for n, state in tasks.items()
             if n not in ESSENTIAL and state == STATE_READY]
    # Record BEFORE disabling, merged with anything a previous fire already took
    # down, so a crash mid-blackout still leaves an exact restore list on disk.
    _save_restore_list(_load_restore_list() + newly)

    disabled = _set_tasks(newly, enable=False)
    killed = _stop_heavy_processes()
    _log(f"QUIET ON: disabled={disabled}/{len(newly)} killed={len(killed)}")
    for k in killed:
        _log(f"  killed {k}")
    _write_status(True, {"disabled_now": disabled,
                         "total_held_down": len(_load_restore_list()),
                         "killed_count": len(killed)})
    return 0


def _log_and_split_catchup(caught_up: list[str]) -> tuple[list[str], list[str]]:
    """Shared by go_loud/go_research: split the flat _catchup_sweep() result into light vs
    heavy, logging a distinct line for each (heavy tier: GUARDS-FULL-NEVER-RUNS-ON-A-GAMING-
    EVENING, 2026-09-03) -- _catchup_sweep() itself already logs the per-item start, this is
    the fire-level summary the caller previously logged for the light tier alone."""
    heavy = [n for n in caught_up if n in HEAVY_CATCHUP_ELIGIBLE]
    light = [n for n in caught_up if n not in HEAVY_CATCHUP_ELIGIBLE]
    if light:
        _log(f"CATCH-UP SWEEP: started {len(light)} missed task(s): {', '.join(light)}")
    if heavy:
        _log(f"CATCH-UP SWEEP (heavy): started {', '.join(heavy)}")
    return light, heavy


def go_loud() -> int:
    names = _load_restore_list()
    if not names:
        # Still worth a catch-up pass: nothing was held down THIS fire, but an earlier
        # fire this evening may already have restored everything while a hold-attributed
        # task still hasn't run since -- cheap, fail-open, and idempotent (see
        # _catchup_sweep's last-run check).
        caught_up = _catchup_sweep(dt.datetime.now(ET))
        caught_up_light, caught_up_heavy = _log_and_split_catchup(caught_up)
        _write_status(False, {"note": "nothing to restore", "caught_up": caught_up_light,
                              "caught_up_heavy": caught_up_heavy})
        return 0
    enabled = _set_tasks(names, enable=True)
    _log(f"QUIET OFF: re-enabled={enabled}/{len(names)}")
    if enabled == len(names):
        RESTORE_FILE.unlink(missing_ok=True)
    else:
        _log("WARN partial restore -- keeping restore file for the next fire")
    # Called AFTER the restore, so a bug in the sweep can never block the re-enable above
    # (constraint (d)) -- and fail-open internally, so it can never turn this 0 into non-0.
    caught_up = _catchup_sweep(dt.datetime.now(ET))
    caught_up_light, caught_up_heavy = _log_and_split_catchup(caught_up)
    _write_status(False, {"restored_count": enabled, "expected": len(names),
                          "caught_up": caught_up_light, "caught_up_heavy": caught_up_heavy})
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="After-hours blackout enforcer")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--enforce", action="store_true", help="apply whatever the clock says")
    g.add_argument("--on", action="store_true", help="force quiet now")
    g.add_argument("--off", action="store_true", help="force restore now")
    g.add_argument("--hold", type=float, metavar="HOURS", nargs="?", const=4.0,
                   help="stay quiet for HOURS (default 4) regardless of the clock")
    g.add_argument("--release", action="store_true", help="clear a manual hold")
    g.add_argument("--status", action="store_true")
    args = ap.parse_args()

    if args.status:
        now = dt.datetime.now(ET)
        print(f"ET now      : {now:%Y-%m-%d %H:%M:%S %a}")
        print(f"quiet window: {in_quiet_window(now)}")
        print(f"research band: {in_research_band(now)}")
        print(f"presence hold: {presence_hold(now) or 'none'}")
        print(f"held down   : {len(_load_restore_list())} tasks")
        if STATUS_FILE.exists():
            print(STATUS_FILE.read_text(encoding="utf-8"))
        return 0

    try:
        if args.hold is not None:
            until = dt.datetime.now(ET) + dt.timedelta(hours=args.hold)
            HOLD_FILE.write_text(json.dumps({"until": until.isoformat()}, indent=2),
                                 encoding="utf-8")
            _log(f"HOLD set until {until.isoformat()}")
            return go_quiet()
        if args.release:
            HOLD_FILE.unlink(missing_ok=True)
            _log("HOLD cleared")
            return go_loud() if not in_quiet_window() else go_quiet()
        if args.on:
            return go_quiet()
        if args.off:
            HOLD_FILE.unlink(missing_ok=True)
            return go_loud()
        if in_quiet_window():
            return go_quiet()
        held = presence_hold()
        if held and in_research_band():
            # J at the machine on a weekend afternoon DOWNGRADES to research, it does not
            # black out. Measured 2026-08-30 12:14 ET: the band had correctly flipped LOUD
            # and the presence gate still held all 116 tasks down, because Apex was
            # foreground -- which is J's normal weekend state, so a full blackout there is
            # the same 30-hour outage wearing a different trigger.
            #
            # What actually protects a frame rate is HEAVY_TASKS staying down, and the
            # research band already does that. The other half of the 2026-08-29 scar was a
            # console window stealing focus mid-match; that is structurally handled --
            # every Gamma task launches through a hidden wscript shim (all 4 shims use
            # windowStyle 0 / WshShell.Exec, audited 2026-08-30), and
            # Gamma_WindowLeakDetectorKeepalive is ESSENTIAL so it keeps watching either
            # way. A task that still flashes a window is a bug in that task, and hiding it
            # behind a fleet-wide blackout is how it stays unfixed.
            _log(f"PRESENCE -> research band (not blackout): {held}")
            return go_research()
        if held:
            # Outside the research band the original behaviour stands unchanged: this is
            # the 23:00 maintenance case from 2026-08-29, when the heavy grinders ARE
            # scheduled and a blackout is the right answer.
            _log(f"QUIET HELD past the clock: {held}")
            return go_quiet()
        if in_research_band():
            return go_research()
        return go_loud()
    except Exception as exc:  # noqa: BLE001
        # FAIL OPEN: never leave the rig disabled because the enforcer broke.
        _log(f"ERROR enforcer failed ({exc}) -- restoring")
        try:
            go_loud()
        except Exception as exc2:  # noqa: BLE001
            _log(f"FATAL restore also failed: {exc2}")
            return 2
        return 1


if __name__ == "__main__":
    sys.exit(main())

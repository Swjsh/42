"""futures_mirror_shadow.py -- forward MES shadow-mirror of the LIVE 0DTE SPY fleet signals.

WHY THIS EXISTS: the futures 7th-arm (mes-linear-sim, automation/state/fleet/accounts.json)
has no armable edge from HISTORICAL replay -- Phase-1 swing batteries killed the seed pile
twice (backtest/futures/analysis/PHASE1-swing-battery/RESULTS.md: DOES_NOT_TRANSFER, 0/12
BH-FDR survivors). The one path left is FORWARD evidence: mirror the CURRENT live 0DTE
signals (the SAME setups the SPY fleet already trades, per accounts.json's "every validated
strategy runs on every account" grid model) expressed on the linear MES instrument, and let
evidence accumulate going forward. This script is that mirror. It places NOTHING real --
own synthetic fill-sim only, no broker, no creds.

FROZEN SPEC (task requirement -- do not drift without updating this docstring):
  SPEC VERSION: v2 (2026-07-09). v1 (STOP_ATR_MULT=1.5) is RETIRED -- see "SPEC v1 -> v2"
    below for the full rationale + citation. Bump SPEC_VERSION (and this note) on any future
    change to the STOP/TP1/TRAIL constants; futures_mirror_shadow self-migrates on the next
    `run_once()` poll after a bump (see `_migrate_spec_version_if_needed`): archives any
    PRIOR spec's ledger rows to `mirror-would-be.{old_version}-archive.jsonl` (only if that
    ledger actually holds real rows -- a doc-header-only file is not evidence worth
    archiving) and starts mirror-would-be.jsonl fresh, so old-spec round-trips never
    silently count toward the NEW spec's arming bar.
  PROXY: entry price = latest ES=F 1-minute close (yfinance). ES and MES quote the SAME
    index level (both are E-mini S&P 500 products; MES is 1/10th NOTIONAL size of ES, not
    1/10th PRICE -- see backtest/futures/instruments.py), so no price scaling is needed --
    only the $-per-point conversion differs (MES.point_value = $5/pt).
  DIRECTION: ENTER_BULL -> long, ENTER_BEAR -> short (fleet decisions.jsonl `action` field).
  STOP: entry -/+ 2.0 x ATR14 (v2; v1 was 1.5x -- see "SPEC v1 -> v2" below), where ATR14 =
    Wilder ATR (backtest/futures/swing_sim.wilder_atr, imported not reimplemented) on ES=F
    5-MINUTE bars. R := that stop distance (2.0xATR14), frozen at entry -- "1R" everywhere
    below means this same point distance.
  TP1: 1R favorable from entry (tp1_r_mult UNCHANGED from v1 -- only the stop multiple moved).
    Sized 2 contracts in, 1 off at TP1 ("sell half"), stop moves to breakeven (entry) on the
    remaining runner.
  RUNNER: the other 1 contract trails a stop 1R off its own high-water-mark (best price seen
    since TP1 filled), ratcheted every poll. No fixed runner target.
  HORIZON: max-hold = flat by 15:55 ET on the NEXT trading day if neither stop nor TP1/trail
    has closed the position first (a "2-session" horizon -- today's session + one more --
    distinct from the killed multiday 1-5 TRADING-DAY swing shapes in PHASE1-swing-battery;
    this mirrors "the signal would have paid within a day or two", not a multiday swing).
    Next-trading-day = the next weekday that is not a US market holiday per
    automation/state/calendar.json (fail-open: an unreadable calendar degrades to
    weekend-only skipping).
  COSTS: MES.round_turn_usd ($1.24/contract, backtest/futures/instruments.py) charged on
    every CLOSING fill (tp1/stopped/time_flat), consistent with how every other battery in
    this repo discloses commission. No separate slippage line -- the stop leg is already
    gap/poll-realistic (see FILL CONVENTIONS below); the target/TP1 leg uses the standard
    touch-at-level convention used throughout this repo's sims (no slippage modeled there).
  FILL CONVENTIONS: TP1 and time-flat fill at the observed level/quote directly (touch
    convention -- matches fill_sim_broker.py's documented "TP1/runner target: touch-at-level,
    no slippage"). STOP legs (both the fixed pre-TP1 stop and the post-TP1 trailing stop) use
    `fill_sim_broker.gap_aware_stop_fill` (imported, not reimplemented) -- fills AT the stop
    on a normal touch, WORSE (at the observed quote) when the poll already shows price beyond
    it. Because this is a 5-MINUTE POLL system (not a continuous bar walk), every fill is, by
    construction, only ever as precise as "the price we happened to observe this poll" -- a
    level that is touched and reverses entirely between two 5-min polls is invisible here.
    This is a disclosed limitation of forward SHADOW evidence, not a backtest, and is the
    reason gap-aware (worst-observed-price) fills are used for the stop leg specifically.

SPEC v1 -> v2 (2026-07-09, BEFORE any forward evidence existed -- the v1 ledger held ZERO
  closed round-trips at the time of this bump: registered 15:00 ET the day before, market
  closed 16:00, so the reset cost nothing real): a pre-forward backtest-grade sanity check
  (analysis/recommendations/mirror-spec-backfill-sanity.json -- explicitly NOT forward
  evidence, does NOT count toward the arming bar) replayed 38 deduped real fleet signals (13
  unique day+direction pairs -- NOT independent draws, treat n as an upper bound on effective
  sample size) through a declared 6-cell grid (atr_mult x tp1_r_mult in {1.0,1.5,2.0} x
  {1.0,1.5}) and found v1's stop (1.5xATR14) sat at a single-bar-range/stop-distance ratio of
  0.659 (1h bars) / 0.66 (1m bars) -- a single bar's ORDINARY range can cover roughly
  two-thirds of the stop distance on its own, the same class of defect that killed the 0DTE
  -20% premium stop (markdown/doctrine/LESSONS-LEARNED.md). NO cell in the grid had positive
  expectancy in this small/correlated backfill, and expectancy WORSENED monotonically as
  atr_mult widened (1.0x: -$88.74/trade, the best of the six cells; 2.0x: -$172.22/trade, the
  worst) while the noise ratio only IMPROVED with a wider stop (1.0x: ~0.99 -- the stop sits
  barely wider than one bar's ordinary noise; 2.0x: ~0.494 (1h) / ~0.495 (1m)). The two
  objectives point in OPPOSITE directions across the grid and no cell wins on both, so per
  this task's explicit fallback clause: SPEC V2 = atr_mult 2.0 / tp1_r_mult 1.0, chosen on
  the noise-ratio argument ALONE -- it is the best available stop-vs-bar-noise ratio in the
  declared grid (roughly halving v1's ~0.66 toward, but not quite under, the ~0.45
  aspirational bar named in the task) and dominates its sibling atr_mult=2.0/tp1_r_mult=1.5
  cell on every metric (WR 28.9% vs 21.1%, expectancy -$172.22 vs -$172.69/trade, avg hold
  8.86h vs 9.34h, tied max_consecutive_losers=8). It ALSO happens to leave tp1_r_mult
  untouched from v1, so this bump moves exactly one knob.

REUSE DECISION (task explicitly invites this call -- documented per instruction):
  FillSimBroker (backtest/futures/fill_sim_broker.py) was read first and NOT reused as the
  position engine, for two concrete interface mismatches:
    1. `process_quote()` deliberately never threads `now_et` into `decide_exit()`, so its
       TIME_STOP branch (futures_exit_manager.DEFAULT_TIME_STOP_ET, an INTRADAY 15:50 ET
       wall-clock check) can never fire -- by design, because FillSimBroker targets true
       multiday swing holds. This mirror's 2-SESSION horizon is exactly the piece
       FillSimBroker punts on; forcing it through would silently never flatten on schedule.
    2. `place_bracket()` REFUSES a new entry while any pending/open position already exists
       for that instrument (one position per instrument, no-stacking). This mirror's whole
       purpose is to log EVERY distinct qualifying signal as its OWN shadow trade for
       forward evidence -- refusing overlapping signals would silently throw away exactly
       the data this script exists to collect.
  What IS reused (both pure, stateless, no coupling to FillSimBroker's own file layout):
    - `futures.swing_sim.wilder_atr` -- the canonical ATR14 implementation (not reimplemented).
    - `futures.fill_sim_broker.gap_aware_stop_fill` -- the canonical gap-aware stop-fill rule.
    - `futures.instruments.MES` -- point_value / round_turn_usd (not re-typed constants).
    - The atomic-write-JSON + append-JSONL + fail-open `_log()` PATTERNS (not the functions
      themselves -- each script in this repo owns its own copies; see fill_sim_broker.py and
      setup/scripts/swing_core_runner.py for the precedent this follows) and the resilient
      yfinance-fetch SHAPE (try/except/never-raise, MultiIndex-column flatten) established by
      swing_core_runner.py's `fetch_live_bar()`.
  Consequence: mirror state is SELF-CONTAINED in automation/state/futures/mirror-*  (distinct
  filenames from FillSimBroker's fillsim-*.json / would-be-trades.jsonl and from the REAL
  swing engine's position.json/decisions.jsonl in the same directory -- no collision), and
  `mirror-positions.json` supports MULTIPLE CONCURRENT open positions keyed by `signal_ref`
  (a deliberate divergence from FillSimBroker's one-position-per-instrument rule).

WATCH / DEDUPE: tails automation/state/fleet/*/decisions.jsonl (today: safe-3, safe-1,
  risky-1, risky-3 -- the 4 `execution: fleet_rest` arms; resolved by glob, not hardcoded, so
  a future roster change is picked up automatically) PLUS automation/state/core-decisions.jsonl
  (the CORE Gamma-Safe-2 / Gamma-Risky-2 accounts -- added 2026-07-14, J directive "make sure
  you trade futures today too": the fleet-only glob structurally never watched the two
  PRIMARY accounts' own signals, which is the actual live-money-adjacent lane CLAUDE.md
  describes as the source of truth. core-decisions.jsonl interleaves both accounts' rows in
  ONE file tagged by an `account` field ("safe"/"bold") rather than living in its own
  per-account subfolder like the fleet arms -- so its candidates are tagged `core-{account}`
  (e.g. "core-safe"/"core-bold") instead of a directory-derived arm_id; see `_scan_core_ledger`
  and the `account` passthrough added to `scan_arm_lines`'s candidate dict, which is additive
  and does not change fleet-row behavior) for NEW rows (tracked via a per-source LINE COUNT
  watermark -- both ledger styles are append-only, so a line count is a safe, simple progress
  marker) with action ENTER_BULL/ENTER_BEAR. Because every validated strategy runs on every
  fleet arm (accounts.json's grid model -- arms differ ONLY by gate strictness and sizing,
  never by strategy) AND the identical setup menu drives core Safe/Bold too, the SAME
  underlying signal routinely fires across core AND fleet within the same processing tick.
  Deduped to ONE mirror signal per (direction, ts_et truncated to the minute) -- see
  `dedupe_signals()` -- across BOTH sources; a signal seen on core AND 2 fleet arms in the
  same minute still yields exactly one mirror trade with all 3 in `source_arms`. A signal that
  dedupes cleanly but whose yfinance fetch fails this poll is retried on the NEXT poll
  (`pending_signals`, persisted) -- a transient network hiccup must never silently drop real
  evidence. COLD START: the first time a given source (a fleet arm's file, or the core ledger)
  is ever scanned (no prior watermark for it), the watermark jumps straight to end-of-file
  with ZERO candidates emitted -- historical backlog is never mirrored, only signals that fire
  AFTER a poll first watches a source. Mirroring an old signal with TODAY's quote/ATR would be
  a real price/time mismatch, not forward evidence (verified live: an early unguarded run
  against the real fleet logs opened 7 positions off signals up to 18 days stale before this
  guard existed; the SAME guard is why adding core-decisions.jsonl today is safe even though
  that file's on-disk content is 18 days stale as of this edit -- see STATUS.md 2026-07-14
  entry "CORE/FLEET DECISION LEDGERS FOUND STALE" -- cold start ignores all of it and only
  mirrors whatever core-decisions.jsonl grows by FROM THIS POLL FORWARD).

RUNNER MODE: `python futures_mirror_shadow.py --once` runs exactly one poll pass (the only
  mode this script has -- flag kept for literal spec compliance / explicit caller intent).
  Fail-open: every internal step is try/except-guarded, `main()` always returns 0, every
  exception is logged to automation/state/logs/futures-mirror-YYYY-MM-DD.log, never raised.

ARMING BAR (evaluated by a LATER session, not this one -- also written into
  mirror-would-be.jsonl's own `_doc` header line so the bar travels with the data): >=20
  CLOSED v2 mirror round-trips (a spec bump migrates any prior-spec rows out to their own
  archive file first -- see SPEC VERSION above -- so they can never silently count toward
  this), positive expectancy in pnl_usd_mes, AND beats a same-horizon ES=F buy-and-hold null
  (same signal timestamps/directions, held flat-to-deadline, no stop/target). This script
  does not compute or check that bar -- it only accumulates rows.

ARMED EXECUTION (added 2026-08-20, desk_allocator.py "DECISION ROTTING" -- the bar above
  CLEARED 2026-08-19: 59/20 round trips, +$1,268.66, beats null). Gated by `MIRROR_ARMED=1`
  (env, read fresh at call time -- never cached, so a caller can flip it after import), OFF
  by default. When OFF: zero behavior change, this file's entire pre-existing shadow
  machinery above runs exactly as it always has -- the arming-bar evidence stream is never
  touched by anything below. When ON: for EVERY signal this poll also opens as a synthetic
  shadow position (unchanged), `_broker_execute_entry()` ADDITIONALLY places a REAL bracket
  order on the Tastytrade sandbox (paper only, TT_SANDBOX=true, never reachable from live
  money -- OP-0 #1 plus a new venue, double-gated same as futures_trader_core). It reuses,
  never reimplements: `compute_entry_levels`'s already-computed entry/stop/tp1 (same numbers
  the shadow row got), `futures_risk_rails.FuturesRiskRails` (the SAME dollar/points rails
  the should_take_v3 broker lane uses), and `futures_trader_core.make_broker("tastytrade")` /
  `_load_broker_env` (the SAME credential-loading + FUTURES_ARMED-gated watch_only construction
  already proven end-to-end 2026-08-09 -- dry run, resting order, filled marketable order; see
  AUTONOMOUS-FUTURES-LANE.md).
    QTY is the FROZEN spec's ENTRY_QTY=2/TP1_QTY=1 -- never resized by the rails; a rail
    failure REJECTS the trade rather than shrinking it, since resizing would deploy an
    unvalidated variant of the exact spec that earned the arming bar.
    ENTRY is a LIMIT order at the ES proxy quote +/- BROKER_ENTRY_SLIPPAGE_PTS (marketable,
    not price-perfect) -- a plain LIMIT at the unbuffered proxy price could rest unfilled
    forever against MES's own (slightly different) real quote.
    CROSS-LANE SAFETY: `broker.is_flat(ARM_INSTRUMENT)` reads the BROKER's actual account
    position, which the should_take_v3 broker lane (Gamma_FuturesBrokerLane, SAME sandbox
    account 5WW73759, SAME "MES" instrument) also trades -- so this naturally refuses to
    stack on top of whatever that lane already holds, and vice versa (its own run_tick() no-
    stack gate reads the same broker truth). DISCLOSED, not solved: a same-5-minute-window
    TOCTOU race between the two independently-scheduled lanes is possible in principle (both
    read is_flat()=True before either places an order) -- bounded by each lane's own dollar
    caps, paper money, and the 2026-08-19 atomic-entry-claim lesson names this exact class;
    a shared OS-level claim file is a disclosed follow-up (queue.md), not built tonight.
    `session_realized_pnl` for the check_session_loss rail comes from
    `futures_trader_core._session_realized_pnl(broker, now_et)`, which calls a
    `get_account_snapshot()` TastytradeBroker does not implement -- it fails open to 0.0 (its
    own documented behavior: "an unreadable ledger makes the session-loss rail MORE
    permissive"). The account-floor rail (equity read live from the broker, therefore already
    reflecting BOTH lanes' fills) remains the hard backstop regardless.
    Journals to `mirror-broker-orders.jsonl` (fills=BROKER) -- disjoint from `mirror-would-
    be.jsonl` (fills=SIMULATED) so the two classes can never be aggregated by accident, same
    convention as futures_trader_core's trader/ vs trader-broker/ split.
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "futures-mirror-shadow.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "futures-mirror-shadow.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import datetime as dt
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest", "setup/scripts"):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)


def _et_now() -> dt.datetime:
    """ET wall-clock via the repo's DST-aware clock. Lazily re-imports et_clock on every call
    (mirrors fill_sim_broker.py / swing_core_runner.py exactly) so tests that monkeypatch
    `et_clock.et_now` are honored -- a top-level `from et_clock import et_now` would bind a
    stale local name at import time a later monkeypatch could never reach. NEVER a naive
    local-clock read (this box runs Mountain time, ET = local + 2h -- CLAUDE.md TZ scar)."""
    import et_clock  # noqa: PLC0415
    return et_clock.et_now()


# ── paths / constants ──────────────────────────────────────────────────────────
FLEET_DIR = REPO / "automation" / "state" / "fleet"
STATE_DIR = REPO / "automation" / "state" / "futures"
LOG_DIR = REPO / "automation" / "state" / "logs"
CALENDAR_FILE = REPO / "automation" / "state" / "calendar.json"

WATERMARK_FILE = STATE_DIR / "mirror-shadow-state.json"
POSITIONS_FILE = STATE_DIR / "mirror-positions.json"
WOULD_BE_FILE = STATE_DIR / "mirror-would-be.jsonl"
CORE_LEDGER = STATE_DIR.parent / "core-decisions.jsonl"   # automation/state/core-decisions.jsonl
                                                            # (heartbeat_core.py's LEDGER const)
CORE_ARM_ID = "core"       # watermark key for CORE_LEDGER's single-file line count

# ── ARMED EXECUTION (see module docstring "ARMED EXECUTION") ──────────────────────────────
BROKER_ORDERS_FILE = STATE_DIR / "mirror-broker-orders.jsonl"
ARM_INSTRUMENT = "MES"
BROKER_ENTRY_SLIPPAGE_PTS = 2.0    # LIMIT entry buffered beyond the ES proxy quote so it is
                                    # marketable against MES's own real quote, not price-perfect.
BROKER_PER_TRADE_RISK_CAP = 150.0  # sized for the frozen spec's 2-lot ATR stop; see docstring.

SPEC_VERSION = "v2"               # bump on ANY change to the constants below -- see module
                                   # docstring "SPEC VERSION" + "SPEC v1 -> v2" for the
                                   # migration this triggers and the 2026-07-09 rationale.
YF_SYMBOL = "ES=F"                # MES front-quote proxy (see module docstring)
ATR_PERIOD = 14
STOP_ATR_MULT = 2.0               # R := STOP_ATR_MULT * ATR14(ES=F 5m). v2 (was 1.5 in v1 --
                                   # see module docstring SPEC v1 -> v2 rationale + citation).
TP1_R_MULT = 1.0                  # TP1 = 1R (unchanged from v1)
TRAIL_R_MULT = 1.0                # runner trail distance = 1R off HWM (unchanged from v1)
ENTRY_QTY = 2
TP1_QTY = 1
DEADLINE_TIME_ET = dt.time(15, 55)
SIGNAL_KEY_RETENTION_DAYS = 5     # prune horizon for the cross-arm dedup key store
PENDING_MAX_AGE_DAYS = 2          # drop a still-unopened signal after a sustained outage
CLOSED_POSITION_RETENTION_DAYS = 10

EV_PLACED = "placed"
EV_FILLED = "filled"
EV_TP1 = "tp1"
EV_STOPPED = "stopped"
EV_TIME_FLAT = "time_flat"

DIRECTION_BY_ACTION = {"ENTER_BULL": "long", "ENTER_BEAR": "short"}

WATERMARK_DOC = (
    "Watermark + cross-arm dedup state for futures_mirror_shadow.py. spec_version = the "
    "FROZEN SPEC version (module docstring) this state was last migrated to -- a mismatch "
    "(including total absence, the shape every mirror-shadow-state.json written before "
    "2026-07-09 carries) triggers a one-time ledger migration on the next run_once() poll "
    "(see _migrate_spec_version_if_needed). arm_line_watermarks = how many lines of each "
    "fleet arm's decisions.jsonl have been scanned (append-only file, so a line count is a "
    "safe progress marker). seen_signal_keys = {direction|minute -> first_seen_et} keys "
    "already turned into ONE mirror signal (pruned after "
    f"{SIGNAL_KEY_RETENTION_DAYS}d). pending_signals = deduped signals not yet successfully "
    "opened (retried every poll; a transient yfinance failure must never silently drop a "
    "signal seen once). See futures_mirror_shadow.py module docstring for the frozen spec."
)
POSITIONS_DOC = (
    "Open + recently-closed MES mirror-shadow positions, keyed by signal_ref "
    "(direction|YYYY-MM-DDTHH:MM). MULTIPLE CONCURRENT positions are expected by design -- "
    "every distinct fleet signal gets its own shadow trade. See futures_mirror_shadow.py "
    "module docstring (REUSE DECISION) for why this diverges from FillSimBroker's "
    "one-position-per-instrument convention."
)
ARMING_BAR_DOC = (
    f"ARMING BAR (evaluated by a LATER session, not this one): >=20 CLOSED {SPEC_VERSION} "
    "mirror round-trips (tp1/stopped/time_flat rows that bring a signal_ref's qty_open_after "
    "to 0, counted per signal_ref not per row), positive expectancy summed in pnl_usd_mes, "
    "AND beats a same-horizon ES=F buy-and-hold null (enter at the same signal "
    "timestamps/directions, hold flat to the same 2-session 15:55 ET deadline, no "
    "stop/target). Any PRIOR spec's rows (archived to mirror-would-be.{old_version}-archive."
    "jsonl on a spec bump -- see module docstring SPEC VERSION) do NOT count toward this "
    "bar; only rows in the CURRENT mirror-would-be.jsonl do. Event vocabulary: "
    "placed|filled|tp1|stopped|time_flat. Proxy: MES tracks ES=F 1:1 in index points "
    "(instruments.py); $ conversion uses MES point_value=$5/pt, round_turn_usd=$1.24/contract "
    f"charged on every CLOSING fill. Stop spec: entry -/+ {STOP_ATR_MULT}xATR14(ES=F 5m "
    "Wilder), frozen at entry as 1R. TP1 = 1R (half qty off). Runner = other half, trails 1R "
    "off its HWM, ratcheted once per 5-min POLL (not continuous -- a disclosed limitation vs "
    "a true bar-by-bar backtest). Max-hold = flat by 15:55 ET the NEXT trading day."
)


# ── fail-open IO helpers (patterns matched to fill_sim_broker.py / swing_core_runner.py) ──
def _log(msg: str) -> None:
    """Fail-open logger -- never raises, even if the log dir/file itself is unwritable."""
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        day = _et_now().strftime("%Y-%m-%d")
        ts = _et_now().strftime("%Y-%m-%dT%H:%M:%S")
        with open(LOG_DIR / f"futures-mirror-{day}.log", "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {msg}\n")
    except Exception:  # noqa: BLE001
        pass


def _atomic_write_json(path: Path, data: dict) -> None:
    """Temp file + os.replace -- atomic on both Windows and POSIX."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def _load_json(path: Path, default: dict) -> dict:
    """Fail-open: a missing file, an unreadable file, or corrupt JSON all degrade to a fresh
    copy of `default` -- never raises."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return json.loads(json.dumps(default))


def _ensure_would_be_doc_header() -> None:
    """Writes the arming-bar `_doc` line as the FIRST line of mirror-would-be.jsonl, once.
    Consumers must skip any row carrying a `_doc` key when parsing lifecycle events."""
    if WOULD_BE_FILE.exists():
        return
    try:
        WOULD_BE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(WOULD_BE_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({"_doc": ARMING_BAR_DOC}) + "\n")
    except Exception:  # noqa: BLE001
        pass


# ── spec-version migration (module docstring SPEC VERSION / SPEC v1 -> v2) ─────────────
def _ledger_has_real_rows(path: Path) -> bool:
    """True iff `path` exists and holds at least one JSON line that is NOT the `_doc` header
    -- i.e. at least one real placed/filled/tp1/stopped/time_flat lifecycle row. Fail-open:
    an unreadable file or a missing file reads as False (nothing worth archiving), never
    raises."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if "_doc" not in row:
            return True
    return False


def _archive_or_reset_ledger_for_migration(old_version_label: str) -> bool:
    """Called once, the first run_once() poll after SPEC_VERSION changes (see
    _migrate_spec_version_if_needed). If WOULD_BE_FILE holds at least one REAL (non-`_doc`)
    lifecycle row, renames it to a `mirror-would-be.{old_version_label}-archive.jsonl` sibling
    so old-spec round-trips never silently count toward the NEW spec's arming bar. Either
    way, removes any stale WOULD_BE_FILE so the caller's next `_ensure_would_be_doc_header()`
    call regenerates it with the CURRENT spec's ARMING_BAR_DOC text -- a doc-header-only file
    is not evidence worth archiving, but leaving its now-stale header text in place would be
    misleading. Returns True iff an archive rename happened. Fail-open: any OSError is logged
    + swallowed -- a migration hiccup must never break a scheduled poll."""
    try:
        if not WOULD_BE_FILE.exists():
            return False
        has_rows = _ledger_has_real_rows(WOULD_BE_FILE)
        if has_rows:
            archive_path = WOULD_BE_FILE.with_name(
                f"{WOULD_BE_FILE.stem}.{old_version_label}-archive{WOULD_BE_FILE.suffix}")
            os.replace(WOULD_BE_FILE, archive_path)
            _log(f"spec_version migration: archived {old_version_label} ledger -> "
                f"{archive_path.name}")
        else:
            WOULD_BE_FILE.unlink()
            _log(f"spec_version migration: prior ({old_version_label}) ledger had zero real "
                "rows -- reset in place, no archive file created")
        return has_rows
    except OSError as e:  # noqa: BLE001
        _log(f"spec_version migration FAILED (fail-open): {type(e).__name__}: {e}")
        return False


def _migrate_spec_version_if_needed(wm_state: dict) -> dict:
    """PURE-ish (may archive/reset the WOULD_BE_FILE ledger as a disk side effect via
    _archive_or_reset_ledger_for_migration). Returns a NEW wm_state dict (never mutates the
    input) stamped with the module's current SPEC_VERSION. Any persisted spec_version that
    does not match SPEC_VERSION -- including total absence, the shape every
    mirror-shadow-state.json written before 2026-07-09 carries -- is treated as a PRIOR spec
    needing migration, defaulting its archive label to "v1" (this repo's only spec before
    this change). See module docstring SPEC VERSION / SPEC v1 -> v2 for the full rationale."""
    persisted = wm_state.get("spec_version")
    if persisted == SPEC_VERSION:
        return wm_state
    _archive_or_reset_ledger_for_migration(persisted or "v1")
    return {**wm_state, "spec_version": SPEC_VERSION}


# ── calendar / 2-session horizon ────────────────────────────────────────────────
def _load_holidays() -> set:
    try:
        doc = json.loads(CALENDAR_FILE.read_text(encoding="utf-8"))
        return set(doc.get("holidays", []))
    except Exception:  # noqa: BLE001
        return set()


def next_trading_day(d: dt.date, holidays: Optional[set] = None) -> dt.date:
    """PURE when `holidays` is supplied. Next weekday that is not a US market holiday.
    Fail-open: an unreadable calendar.json (holidays=None -> loaded fresh, empty on error)
    degrades to weekend-only skipping, never raises."""
    if holidays is None:
        holidays = _load_holidays()
    nd = d + dt.timedelta(days=1)
    while nd.weekday() >= 5 or nd.strftime("%Y-%m-%d") in holidays:
        nd += dt.timedelta(days=1)
    return nd


# ── fleet scan + cross-arm dedupe ───────────────────────────────────────────────
def signal_key(direction: str, ts_et: dt.datetime) -> str:
    return f"{direction}|{ts_et.strftime('%Y-%m-%dT%H:%M')}"


def _parse_ts_et(s: Optional[str]) -> Optional[dt.datetime]:
    """decisions.jsonl's ts_et carries a real UTC offset (e.g. '...-04:00') but the wall-clock
    hour IS already ET (the fleet writer stamps ET-local wall time with its true DST offset) --
    stripping tzinfo yields the naive-ET value used everywhere else in this repo."""
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s).replace(tzinfo=None)
    except (ValueError, TypeError):
        return None


def scan_arm_lines(lines: list[str], start_line: int) -> tuple[list[dict], int]:
    """PURE. Scans lines[start_line:] for ENTER_BULL/ENTER_BEAR rows. Returns
    (candidate_dicts, new_line_count). Malformed JSON / non-ENTER / unparseable ts_et lines
    are silently skipped (a fleet decisions.jsonl is mostly HOLD rows by volume). Also used
    for core-decisions.jsonl (2026-07-14 extension) -- that ledger's rows carry an `account`
    field ("safe"/"bold") a fleet arm's row never has; passed through here (None for fleet
    rows) so the caller can derive a `core-{account}` arm_id without a second parser."""
    candidates = []
    for raw in lines[start_line:]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError:
            continue
        direction = DIRECTION_BY_ACTION.get(row.get("action"))
        if direction is None:
            continue
        ts = _parse_ts_et(row.get("ts_et"))
        if ts is None:
            continue
        candidates.append({
            "direction": direction, "ts_et": ts,
            # core-decisions.jsonl names this field "setup" (verified against the real live
            # ledger 2026-07-14); every fleet arm's decisions.jsonl names it "setup_name" --
            # this fallback reads either schema without needing to know which source a given
            # line came from (a fleet row never has "setup", so the fallback is a safe no-op
            # there; a core row never has "setup_name", so it falls through to "setup").
            "setup_name": row.get("setup_name") or row.get("setup"),
            "side": row.get("side"),
            "account": row.get("account"),
        })
    return candidates, len(lines)


def dedupe_signals(candidates: list[dict], seen_keys: dict, now_et: dt.datetime) -> tuple[list[dict], dict]:
    """PURE. Groups candidates (each carrying an `arm_id`) by (direction, ts_et-minute); a key
    already in `seen_keys` is skipped (already turned into a mirror signal on a prior poll or
    earlier in THIS batch); a new key becomes exactly ONE signal dict (ts_et re-encoded as a
    JSON-safe string) recording every arm_id that fired it. Returns (new_unique_signals,
    updated_and_pruned seen_keys)."""
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for c in sorted(candidates, key=lambda c: c["ts_et"]):
        key = signal_key(c["direction"], c["ts_et"])
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(c)

    updated = dict(seen_keys)
    unique = []
    for key in order:
        if key in updated:
            continue
        group = groups[key]
        rep = group[0]
        arms = sorted({c["arm_id"] for c in group if c.get("arm_id")})
        unique.append({
            "signal_ref": key, "direction": rep["direction"],
            "ts_et": rep["ts_et"].strftime("%Y-%m-%dT%H:%M:%S"),
            "setup_name": rep.get("setup_name"), "side": rep.get("side"),
            "source_arms": arms,
        })
        updated[key] = now_et.strftime("%Y-%m-%dT%H:%M:%S")

    cutoff = now_et - dt.timedelta(days=SIGNAL_KEY_RETENTION_DAYS)
    pruned = {}
    for k, v in updated.items():
        seen_at = _parse_ts_et(v)
        if seen_at is not None and seen_at >= cutoff:
            pruned[k] = v
    return unique, pruned


def _prune_stale_pending(pending: list[dict], now_et: dt.datetime,
                         max_age_days: int = PENDING_MAX_AGE_DAYS) -> list[dict]:
    """PURE. Drops a pending (deduped-but-not-yet-opened) signal once it is older than
    max_age_days -- protects against unbounded growth during a sustained yfinance outage."""
    out = []
    for sig in pending:
        ts = _parse_ts_et(sig.get("ts_et"))
        if ts is None or (now_et - ts) <= dt.timedelta(days=max_age_days):
            out.append(sig)
    return out


# ── live quote / ATR fetch (yfinance; shape matches swing_core_runner.fetch_live_bar) ──
def fetch_es_quote_1m() -> Optional[float]:
    """Latest ES=F 1-minute close -- the MES front-quote proxy. Fail-open -> None, never
    raises."""
    try:
        import yfinance as yf  # noqa: PLC0415
        df = yf.download(YF_SYMBOL, period="1d", interval="1m", auto_adjust=False,
                         progress=False, prepost=True)
        if df is None or df.empty:
            return None
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        last_close = df["Close"].iloc[-1]
        if last_close is None or (hasattr(last_close, "__len__") is False and last_close != last_close):
            return None  # NaN check without importing pandas just for isna()
        return float(last_close)
    except Exception:  # noqa: BLE001
        return None


def fetch_es_atr14() -> Optional[float]:
    """ATR14 on ES=F 5-minute bars (frozen spec: R = STOP_ATR_MULT x this, v2 = 2.0x). Reuses
    futures.swing_sim.wilder_atr -- not reimplemented. Fail-open -> None, never raises."""
    try:
        import pandas as pd  # noqa: PLC0415
        import yfinance as yf  # noqa: PLC0415
        from futures.swing_sim import wilder_atr  # noqa: PLC0415

        df = yf.download(YF_SYMBOL, period="10d", interval="5m", auto_adjust=False,
                         progress=False, prepost=True)
        if df is None or df.empty:
            return None
        if hasattr(df.columns, "nlevels") and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        bars = pd.DataFrame({
            "open": df["Open"].astype(float), "high": df["High"].astype(float),
            "low": df["Low"].astype(float), "close": df["Close"].astype(float),
        }).reset_index(drop=True)
        atr = wilder_atr(bars, period=ATR_PERIOD)
        if len(atr) == 0:
            return None
        val = atr.iloc[-1]
        if val != val or val <= 0:  # NaN-safe without a pandas.isna import
            return None
        return float(val)
    except Exception:  # noqa: BLE001
        return None


# ── entry math ───────────────────────────────────────────────────────────────
def compute_entry_levels(direction: str, entry_price: float, atr: float) -> dict:
    """PURE. R := STOP_ATR_MULT * ATR14. stop = entry -/+ R. tp1 = entry +/- TP1_R_MULT*R."""
    r_points = STOP_ATR_MULT * atr
    sign = 1.0 if direction == "long" else -1.0
    return {
        "r_points": r_points,
        "stop": entry_price - sign * r_points,
        "tp1": entry_price + sign * (TP1_R_MULT * r_points),
    }


def _mirror_armed() -> bool:
    """Read fresh at call time -- never cached as a module constant -- so a caller (main(),
    or a test) can flip MIRROR_ARMED after this module is already imported. Same reasoning as
    _et_now()'s lazy et_clock import above: a top-level constant would bind at import time and
    ignore any later os.environ change, including monkeypatch."""
    return os.environ.get("MIRROR_ARMED", "0") == "1"


def _broker_execute_entry(sig: dict, pos: dict, now_et: dt.datetime) -> Optional[dict]:
    """Places a REAL Tastytrade-sandbox bracket order for a mirror signal that has ALREADY
    been recorded in the (untouched) synthetic shadow ledger by the caller. See module
    docstring "ARMED EXECUTION" for the full design + disclosed limitations. Returns None when
    not armed (the overwhelmingly common case); a dict describing the outcome (placed, skipped
    with a reason, or error) when armed. NEVER raises -- any failure here must not break the
    shadow poll that is this file's actual arming-bar evidence stream."""
    if not _mirror_armed():
        return None
    try:
        from futures.futures_risk_rails import FuturesRiskRails  # noqa: PLC0415
        from futures.instruments import get as get_instrument  # noqa: PLC0415
        from futures.futures_trader_core import (  # noqa: PLC0415
            make_broker, _session_realized_pnl,
        )

        inst = get_instrument(ARM_INSTRUMENT)
        rails = FuturesRiskRails(max_contracts=ENTRY_QTY,
                                 per_trade_risk_cap=BROKER_PER_TRADE_RISK_CAP)
        # make_broker("tastytrade") gates watch_only on FUTURES_ARMED (its own established
        # convention) -- set it for THIS process only, mirroring futures_trader_runner.py's
        # --armed flag. Each scheduled task is its own python.exe invocation, so this never
        # leaks into another lane's process.
        os.environ.setdefault("FUTURES_ARMED", "1")
        broker = make_broker("tastytrade")
        if not broker.connect():
            return {"skipped": "broker_not_connected"}
        if not broker.is_flat(ARM_INSTRUMENT):
            return {"skipped": "position_open_no_stack"}

        equity = broker.get_account_equity() or rails.start_equity
        session_pnl = _session_realized_pnl(broker, now_et)
        verdict = rails.check_entry(
            now_et=now_et, equity=equity, session_realized_pnl=session_pnl,
            stop_points=pos["r_points"], qty=ENTRY_QTY, instrument=inst,
            freshness_verdict="GREEN")
        if not verdict.allow:
            row = {"ts_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
                  "signal_ref": pos["signal_ref"], "placed": False,
                  "skipped": verdict.rail, "reason": verdict.reason, "fills": "BROKER"}
            _append_jsonl(BROKER_ORDERS_FILE, row)
            return row

        side = "BUY" if pos["direction"] == "long" else "SELL"
        entry_limit = (pos["entry"] + BROKER_ENTRY_SLIPPAGE_PTS if side == "BUY"
                       else pos["entry"] - BROKER_ENTRY_SLIPPAGE_PTS)
        ids = broker.place_bracket(
            ARM_INSTRUMENT, side, ENTRY_QTY, entry_limit, pos["tp1"], pos["stop"],
            tp1_qty=TP1_QTY)
        row = {
            "ts_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"), "signal_ref": pos["signal_ref"],
            "direction": pos["direction"], "side": side, "qty": ENTRY_QTY,
            "entry_limit": round(entry_limit, 4), "stop": pos["stop"], "tp1": pos["tp1"],
            "order_ids": ids, "placed": bool(ids), "equity_at_entry": equity,
            "fills": "BROKER",
        }
        _append_jsonl(BROKER_ORDERS_FILE, row)
        return row
    except Exception as e:  # noqa: BLE001 -- armed execution must never break the shadow poll
        row = {"ts_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
              "signal_ref": pos.get("signal_ref"), "placed": False,
              "error": f"{type(e).__name__}: {e}", "fills": "BROKER"}
        try:
            _append_jsonl(BROKER_ORDERS_FILE, row)
        except Exception:  # noqa: BLE001
            pass
        return row


def open_mirror_position(signal: dict, entry_price: float, atr: float, now_et: dt.datetime) -> dict:
    """PURE. Builds a brand-new position dict (never mutates `signal`)."""
    levels = compute_entry_levels(signal["direction"], entry_price, atr)
    deadline = dt.datetime.combine(next_trading_day(now_et.date()), DEADLINE_TIME_ET)
    return {
        "signal_ref": signal["signal_ref"], "direction": signal["direction"], "status": "open",
        "qty_open": ENTRY_QTY, "entry": round(entry_price, 4), "stop": round(levels["stop"], 4),
        "tp1": round(levels["tp1"], 4), "r_points": round(levels["r_points"], 4),
        "tp1_filled": False, "hwm": None,
        "entry_time_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
        "deadline_et": deadline.strftime("%Y-%m-%dT%H:%M:%S"), "closed_at_et": None,
        "source_arms": signal.get("source_arms", []), "setup_name": signal.get("setup_name"),
        "atr_at_entry": round(atr, 4),
    }


def _placed_row(signal: dict, position: dict) -> dict:
    ts = _parse_ts_et(signal.get("ts_et")) or dt.datetime.fromisoformat(position["entry_time_et"])
    return {
        "ts_et": ts.strftime("%Y-%m-%dT%H:%M:%S"), "signal_ref": position["signal_ref"],
        "direction": position["direction"], "entry": position["entry"], "stop": position["stop"],
        "tp1": position["tp1"], "event": EV_PLACED, "pnl_pts": 0.0, "pnl_usd_mes": 0.0,
        "exit_qty": 0, "fill_price": None, "qty_open_after": position["qty_open"],
        "reason": f"signal_fired arms={position.get('source_arms')} setup={position.get('setup_name')}",
        "setup_name": position.get("setup_name"), "source_arms": position.get("source_arms"),
    }


def _filled_row(position: dict, now_et: dt.datetime) -> dict:
    return {
        "ts_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"), "signal_ref": position["signal_ref"],
        "direction": position["direction"], "entry": position["entry"], "stop": position["stop"],
        "tp1": position["tp1"], "event": EV_FILLED, "pnl_pts": 0.0, "pnl_usd_mes": 0.0,
        "exit_qty": position["qty_open"], "fill_price": position["entry"],
        "qty_open_after": position["qty_open"], "reason": "market_fill_at_poll_quote",
        "setup_name": position.get("setup_name"), "source_arms": position.get("source_arms"),
    }


# ── exit decision (the fill engine) ─────────────────────────────────────────────
def _trail_stop(hwm: float, direction: str, r_points: float) -> float:
    return hwm - r_points if direction == "long" else hwm + r_points


def _close_all(position: dict, price: float, now_et: dt.datetime, event: str, reason: str,
              *, gap_aware: bool) -> tuple[dict, dict]:
    from futures.instruments import MES  # noqa: PLC0415
    from futures.fill_sim_broker import gap_aware_stop_fill  # noqa: PLC0415

    direction = position["direction"]
    long = direction == "long"
    fill = (gap_aware_stop_fill(direction, position["stop"], price, None)
            if gap_aware else price)
    qty = position["qty_open"]
    pts = (fill - position["entry"]) if long else (position["entry"] - fill)
    pnl_usd = round(pts * MES.point_value * qty - MES.round_turn_usd * qty, 2)
    new_pos = {**position, "status": "closed", "qty_open": 0,
              "closed_at_et": now_et.strftime("%Y-%m-%dT%H:%M:%S")}
    row = {
        "ts_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"), "signal_ref": position["signal_ref"],
        "direction": direction, "entry": position["entry"], "stop": position["stop"],
        "tp1": position["tp1"], "event": event, "pnl_pts": round(pts, 4),
        "pnl_usd_mes": pnl_usd, "exit_qty": qty, "fill_price": round(fill, 4),
        "qty_open_after": 0, "reason": reason, "setup_name": position.get("setup_name"),
        "source_arms": position.get("source_arms"),
    }
    return row, new_pos


def _partial_tp1(position: dict, now_et: dt.datetime) -> tuple[dict, dict]:
    from futures.instruments import MES  # noqa: PLC0415

    direction = position["direction"]
    long = direction == "long"
    fill = position["tp1"]
    qty = TP1_QTY
    pts = (fill - position["entry"]) if long else (position["entry"] - fill)
    pnl_usd = round(pts * MES.point_value * qty - MES.round_turn_usd * qty, 2)
    remaining = position["qty_open"] - qty
    new_pos = {**position, "qty_open": remaining, "tp1_filled": True,
              "stop": position["entry"], "hwm": fill}
    row = {
        "ts_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"), "signal_ref": position["signal_ref"],
        "direction": direction, "entry": position["entry"], "stop": position["stop"],
        "tp1": position["tp1"], "event": EV_TP1, "pnl_pts": round(pts, 4),
        "pnl_usd_mes": pnl_usd, "exit_qty": qty, "fill_price": round(fill, 4),
        "qty_open_after": remaining, "reason": "tp1_touch_1R",
        "setup_name": position.get("setup_name"), "source_arms": position.get("source_arms"),
    }
    return row, new_pos


def decide_mirror_exit(position: dict, price: float, now_et: dt.datetime) -> tuple[Optional[dict], dict]:
    """PURE (never mutates `position` -- always returns NEW dicts). Returns (row_or_None,
    new_position). `row` is a ready-to-append mirror-would-be.jsonl record, or None for a
    silent HOLD/HWM-ratchet (new_position may still differ from `position` in that case).

    Priority per poll (matches futures_exit_manager.decide_exit's documented order, and the
    "stop-first" convention used throughout this repo's sims -- swing_sim.py, the original
    PHASE1 ExitEngine): 1) 2-session deadline (unconditional flatten) 2) stop leg (adverse
    first: fixed pre-TP1 stop, or the ratcheted post-TP1 trailing stop) 3) target leg (TP1
    touch pre-fill; a silent HWM/trailing-stop ratchet post-fill, no fixed runner target)."""
    if position.get("status") != "open" or position.get("qty_open", 0) <= 0:
        return None, position

    direction = position["direction"]
    long = direction == "long"

    deadline = dt.datetime.strptime(position["deadline_et"], "%Y-%m-%dT%H:%M:%S")
    if now_et >= deadline:
        return _close_all(position, price, now_et, EV_TIME_FLAT, "2_session_deadline",
                          gap_aware=False)

    working = position
    if position["tp1_filled"]:
        prior_hwm = working["hwm"]
        new_hwm = price if prior_hwm is None else (max(prior_hwm, price) if long else min(prior_hwm, price))
        new_stop = _trail_stop(new_hwm, direction, position["r_points"])
        if new_hwm != prior_hwm or new_stop != working["stop"]:
            working = {**working, "hwm": new_hwm, "stop": new_stop}

    stop_hit = (price <= working["stop"]) if long else (price >= working["stop"])
    if stop_hit:
        reason = "trail_stop_off_hwm" if working["tp1_filled"] else "full_stop_pre_tp1"
        return _close_all(working, price, now_et, EV_STOPPED, reason, gap_aware=True)

    if not working["tp1_filled"]:
        tp1_hit = (price >= working["tp1"]) if long else (price <= working["tp1"])
        if tp1_hit:
            return _partial_tp1(working, now_et)

    if working is not position:
        return None, working
    return None, position


def _prune_closed_positions(positions: dict, now_et: dt.datetime,
                            retention_days: int = CLOSED_POSITION_RETENTION_DAYS) -> dict:
    """PURE. Drops CLOSED positions older than retention_days from the live JSON (the full
    permanent record lives in mirror-would-be.jsonl regardless) -- OP-22 retention cap."""
    out = {}
    cutoff = now_et - dt.timedelta(days=retention_days)
    for key, pos in positions.items():
        if pos.get("status") != "closed":
            out[key] = pos
            continue
        ts = _parse_ts_et(pos.get("closed_at_et"))
        if ts is None or ts >= cutoff:
            out[key] = pos
    return out


# ── state load ───────────────────────────────────────────────────────────────
def load_watermark_state() -> dict:
    return _load_json(WATERMARK_FILE, {
        "arm_line_watermarks": {}, "seen_signal_keys": {}, "pending_signals": [],
        "last_run_et": None, "spec_version": SPEC_VERSION,
    })


def load_positions_state() -> dict:
    return _load_json(POSITIONS_FILE, {"positions": {}})


# ── orchestration ────────────────────────────────────────────────────────────
def run_once(*, now_et: Optional[dt.datetime] = None, quote_fetcher=None, atr_fetcher=None,
            fleet_files: Optional[list] = None, core_file: Optional[Path] = None) -> dict:
    """ONE poll pass. Never raises internally (every step is try/except-guarded and any
    failure is recorded in the returned summary's `errors` list, not propagated) -- callers
    that need a hard signal should inspect `summary["errors"]`.

    `core_file` (2026-07-14 extension) resolves to the module-level CORE_LEDGER at CALL time
    (never bound as a literal default -- the same lazy-resolution pattern `fleet_files` already
    uses for FLEET_DIR, and the same reason `_et_now()`'s docstring gives for lazy et_clock
    import: a test's `monkeypatch.setattr(fms, "CORE_LEDGER", tmp_path/...)` must be honored).
    Pass `core_file=some_path` to point at a fixture; the isolation fixture in
    test_futures_mirror_shadow.py points the module-level CORE_LEDGER at a nonexistent tmp
    path so every pre-existing test (which never passes core_file explicitly) stays hermetic
    without editing each test individually."""
    if now_et is None:
        now_et = _et_now()
    quote_fetcher = quote_fetcher or fetch_es_quote_1m
    atr_fetcher = atr_fetcher or fetch_es_atr14
    if fleet_files is None:
        fleet_files = sorted(FLEET_DIR.glob("*/decisions.jsonl"))
    if core_file is None:
        core_file = CORE_LEDGER

    errors: list = []
    wm_state = load_watermark_state()
    try:
        wm_state = _migrate_spec_version_if_needed(wm_state)
    except Exception as e:  # noqa: BLE001 -- migration must never break a scheduled poll
        errors.append(f"spec_migration_failed:{type(e).__name__}:{e}")
        wm_state = {**wm_state, "spec_version": SPEC_VERSION}
    _ensure_would_be_doc_header()
    positions = dict(load_positions_state().get("positions", {}))

    # 1) scan every fleet arm's decisions.jsonl past its watermark, dedupe cross-arm.
    #    COLD START (an arm never watermarked before): jump straight to end-of-file with
    #    zero candidates instead of treating the whole historical backlog as "new". This
    #    script mirrors FORWARD signals only -- opening a position for a signal that fired
    #    days ago, priced with TODAY's quote/ATR, would be a real entry-price mismatch, not
    #    honest shadow evidence. Only signals that fire AFTER a given arm is first watched
    #    are ever mirrored (verified live 2026-07-09: an unguarded first run against the
    #    real fleet logs opened 7 positions off signals up to 18 days stale before this
    #    guard was added).
    all_candidates = []
    line_wm = dict(wm_state.get("arm_line_watermarks", {}))
    for path in fleet_files:
        arm_id = path.parent.name
        try:
            lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        except OSError as e:  # noqa: BLE001
            errors.append(f"read_failed:{arm_id}:{type(e).__name__}:{e}")
            lines = []
        cold_start = arm_id not in line_wm
        start = len(lines) if cold_start else int(line_wm[arm_id])
        candidates, new_count = scan_arm_lines(lines, start)
        for c in candidates:
            c["arm_id"] = arm_id
        all_candidates.extend(candidates)
        line_wm[arm_id] = new_count

    # 1b) core ledger (automation/state/core-decisions.jsonl -- the 2 PRIMARY accounts,
    #     Gamma-Safe-2/Gamma-Risky-2). Same cold-start-safe, line-count-watermark treatment as
    #     a fleet arm (see module docstring WATCH/DEDUPE for why this file needs its own
    #     per-row arm_id derivation instead of a directory-derived one).
    try:
        core_lines = (core_file.read_text(encoding="utf-8").splitlines()
                     if core_file and core_file.exists() else [])
    except OSError as e:  # noqa: BLE001
        errors.append(f"read_failed:{CORE_ARM_ID}:{type(e).__name__}:{e}")
        core_lines = []
    core_cold_start = CORE_ARM_ID not in line_wm
    core_start = len(core_lines) if core_cold_start else int(line_wm[CORE_ARM_ID])
    core_candidates, core_new_count = scan_arm_lines(core_lines, core_start)
    for c in core_candidates:
        acct = c.get("account")
        c["arm_id"] = f"core-{acct}" if acct else CORE_ARM_ID
    all_candidates.extend(core_candidates)
    line_wm[CORE_ARM_ID] = core_new_count

    new_signals, seen_keys = dedupe_signals(
        all_candidates, wm_state.get("seen_signal_keys", {}), now_et)
    pending = _prune_stale_pending(
        list(wm_state.get("pending_signals", [])) + new_signals, now_et)

    # 2) one shared quote fetch this poll, only if there's anything to do with it.
    open_keys = [k for k, p in positions.items() if p.get("status") == "open"]
    quote = None
    if pending or open_keys:
        try:
            quote = quote_fetcher()
        except Exception as e:  # noqa: BLE001
            errors.append(f"quote_fetch_failed:{type(e).__name__}:{e}")

    # 3) open every pending signal this poll's quote+ATR can support; retry the rest.
    opened, still_pending = 0, []
    if pending:
        atr = None
        if quote is not None:
            try:
                atr = atr_fetcher()
            except Exception as e:  # noqa: BLE001
                errors.append(f"atr_fetch_failed:{type(e).__name__}:{e}")
        for sig in pending:
            if quote is None or atr is None:
                still_pending.append(sig)
                continue
            pos = open_mirror_position(sig, quote, atr, now_et)
            positions[pos["signal_ref"]] = pos
            _append_jsonl(WOULD_BE_FILE, _placed_row(sig, pos))
            _append_jsonl(WOULD_BE_FILE, _filled_row(pos, now_et))
            opened += 1
            # ARMED EXECUTION (see module docstring) -- strictly additive; a no-op unless
            # MIRROR_ARMED=1, and any failure here is caught inside the function itself so it
            # can never break the shadow tracking above (opened/positions/WOULD_BE_FILE).
            try:
                broker_result = _broker_execute_entry(sig, pos, now_et)
                if broker_result is not None and broker_result.get("error"):
                    errors.append(f"broker_execute_failed:{pos['signal_ref']}:"
                                 f"{broker_result['error']}")
            except Exception as e:  # noqa: BLE001 -- belt-and-braces; the function already
                errors.append(f"broker_execute_unexpected:{pos['signal_ref']}:"  # catches
                             f"{type(e).__name__}:{e}")                          # internally

    # 4) manage every open position (including any just opened this poll).
    events = 0
    if quote is not None:
        for key in [k for k, p in positions.items() if p.get("status") == "open"]:
            try:
                row, new_pos = decide_mirror_exit(positions[key], quote, now_et)
                positions[key] = new_pos
                if row is not None:
                    _append_jsonl(WOULD_BE_FILE, row)
                    events += 1
            except Exception as e:  # noqa: BLE001
                errors.append(f"manage_failed:{key}:{type(e).__name__}:{e}")

    positions = _prune_closed_positions(positions, now_et)

    spec_version = wm_state.get("spec_version", SPEC_VERSION)
    _atomic_write_json(WATERMARK_FILE, {
        "_doc": WATERMARK_DOC, "spec_version": spec_version, "arm_line_watermarks": line_wm,
        "seen_signal_keys": seen_keys, "pending_signals": still_pending,
        "last_run_et": now_et.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    _atomic_write_json(POSITIONS_FILE, {"_doc": POSITIONS_DOC, "positions": positions})

    # 5) recompute the arming-bar progress tracker (2026-07-14 extension, queue.md
    #    FUTURES-MIRROR-SHADOW item #5) -- piggybacks on this same poll (every 5 min RTH +
    #    16:05 sweep) so shadow-progress.json is always current without its own scheduled
    #    task. Fail-open: a progress-computation hiccup is recorded in `errors` but never
    #    blocks the watermark/positions writes above (already committed to disk by this point).
    try:
        import futures_shadow_progress  # noqa: PLC0415
        futures_shadow_progress.main()
    except Exception as e:  # noqa: BLE001
        errors.append(f"shadow_progress_failed:{type(e).__name__}:{e}")

    return {
        "new_signals": len(new_signals), "opened": opened, "pending_retry": len(still_pending),
        "events": events,
        "positions_open": sum(1 for p in positions.values() if p.get("status") == "open"),
        "errors": errors, "spec_version": spec_version,
    }


def main() -> int:
    """CLI entry point. ALWAYS returns 0 (fail-open) -- every exception is caught + logged,
    never re-raised (task requirement: a scheduled fire must never break the chain)."""
    try:
        ap = argparse.ArgumentParser()
        ap.add_argument("--once", action="store_true",
                        help="run exactly one poll pass (the only mode this script has; "
                             "kept for explicit/literal CLI compliance)")
        ap.add_argument("--armed", action="store_true",
                        help="set MIRROR_ARMED=1 for this process (real bracket orders on "
                             "the SANDBOX broker; never reaches live money). Default OFF -- "
                             "the shadow tracker runs identically either way.")
        args = ap.parse_args()
        if args.armed:
            os.environ["MIRROR_ARMED"] = "1"
        summary = run_once()
        _log(f"pass complete: {json.dumps(summary, default=str)[:2000]}")
        return 0
    except Exception as e:  # noqa: BLE001 -- fail-open is the task's explicit requirement
        try:
            _log(f"main() FAILED (fail-open, exit 0 anyway): {type(e).__name__}: {e}\n"
                f"{traceback.format_exc()}")
        except Exception:  # noqa: BLE001 -- even logging must not break the fail-open contract
            pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

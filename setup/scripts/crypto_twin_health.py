"""crypto_twin_health.py -- T3: visibility instruments for the CRYPTO TWIN (OP-33c).

markdown/planning/CRYPTO-TWIN-TRAINING-GROUND.md's T3 build order: "funnel/autopsy/
glance wiring + Gamma_CryptoTwin registration + 48h soak". This module is the
"glance wiring" half. It is a THIN WRAPPER AROUND crypto_twin_core.run_tick() --
T1/T2's tested (40/40) surface is imported and called, NEVER edited by this file.

Gamma_CryptoTwin's scheduled task invokes THIS file (not crypto_twin_core.py
directly) every 1 min, 24/7 (CADENCE-TUNE 2026-08-01: was 5 min 2026-07-10..2026-07-31
-- see install-crypto-twin.ps1's docstring for the measured-latency + realized-vol
evidence behind the tighter cadence; twin-only, the SPY heartbeat is untouched), because:

  1. crypto_twin_broker deliberately fail-louds on a genuine HTTP/network failure
     (see its module docstring: "Raises on a genuine HTTP/network failure"). Under
     the flash-free wscript->run_exe_hidden.vbs->pythonw chain, pythonw.exe has no
     console -- an uncaught exception's traceback goes to a stderr nobody reads.
     That is a SILENT failure mode (OP-33a: "never claim a tick worked without a
     quoted check" cuts both ways -- a crash nobody recorded is functionally
     indistinguishable from "nothing happened" without a wrapper that catches it and
     writes down what happened). run_tick_with_health() is that outermost net: it
     can print/return an error but it must never itself raise.

  2. automation/state/twin-health.json is a TOP-LEVEL glance file -- a deliberate,
     narrow exception to T1/T2's "zero writes outside crypto-twin/" namespace-
     isolation hard rail (see crypto_twin_core.py's module docstring + the static
     AST guard in test_crypto_twin_core.py, which is intentionally NOT extended to
     this file -- see test_crypto_twin_health.py's own path-identity tests instead).
     It sits next to engine-health.json / self-check-last.json / dress-rehearsal.json
     because that is where J already looks (automation/state/*.json), not buried
     inside the twin's own private ledger directory.

  3. automation/state/crypto-twin/soak-log.jsonl accrues ONE summary row per elapsed
     ET hour (watermarked -- a restart or a multi-hour gap never double-counts or
     loops trying to backfill; it just reports the true period it covers), so T4's
     soak report (crypto_twin_soak_report.py) never has to re-derive a full history
     from raw decisions.jsonl by hand.

Every function here reads either T1/T2's own append-only ledgers (decisions.jsonl,
journal.jsonl, breaker.json) or crypto_twin_broker's creds loader -- never a second
source of truth for the same fact (ticks_today and n_orders_lifetime are RE-DERIVED
from the ledgers on every call, not a separately persisted counter that could drift).

B1c ADDITION (2026-07-11, markdown/planning/TWIN-PROGRAM.md): twin-health.json now also
carries {path_coverage, branches_green_today, incidents_today}, RE-DERIVED every call
from crypto_twin_scenarios.py's path-coverage.json (same "never a second source of
truth" discipline as the rest of this file -- no separately persisted green/incident
counter that could drift from the scoreboard itself). B1b ADDITION: the wrapped tick now
calls crypto_twin_scenarios.run_scenario_tick() instead of crypto_twin_core.run_tick()
directly -- the scenario scheduler's own network-free scheduling step degrades to
"run organically" on any internal error (see that module's run_scenario_tick
docstring), so this file's own outermost catch-all is still the true last line of
defense for a genuine crypto_twin_core.run_tick() failure (network/HTTP/broker).

TWIN-B1.5-WIRE (2026-07-16): run_scenario_tick() itself now ALSO ticks the SIM-tier bear
lane (crypto_twin_scenarios.run_sim_bear_tick(), TWIN-B1.5) every call, wrapped in its own
try/except inside that function so a SIM-lane bug can never turn this file's row into a
TICK_ERROR. No edit was needed here -- run_tick_with_health's `row = cts.run_scenario_tick(
...)["row"]` line is unchanged; the sim-bear result rides along in the same dict under
`result["sim_bear"]` for any caller (this file's own CLI does not surface it -- see
crypto_twin_scenarios.py's own `main()` / `--sim-bear` flag for a direct, visible run).
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
    _sys.stdout = open(_log_dir / "crypto-twin-health.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "crypto-twin-health.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "setup" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from et_clock import et_now  # noqa: E402

import crypto_twin_core as ctc  # noqa: E402
import crypto_twin_broker as broker  # noqa: E402
import crypto_twin_scenarios as cts  # noqa: E402
import broker_canary as bc  # noqa: E402  -- BROKER-CANARY-SENTINEL-HOOKUP (queue.md 2026-07-11):
# the one-line piggyback this scheduled tick was built to carry. See main()'s call site.

STATE = REPO / "automation" / "state"
# TOP-LEVEL glance file -- deliberately a sibling of engine-health.json/
# self-check-last.json, NOT under automation/state/crypto-twin/. See module docstring.
HEALTH_PATH = STATE / "twin-health.json"


# --- fail-open JSONL reader (shared by every counter below) ----------------------------
def _read_jsonl(path: Path) -> list[dict]:
    """Missing file -> []. A malformed individual line is skipped, never aborts the
    whole read (this is a READ-side tolerance for glance/reporting code -- state-file
    corruption RECOVERY is _shared.ps1's Repair-StateFiles' job, not this module's)."""
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    out: list[dict] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


# --- the four health facts --------------------------------------------------------------
def count_ticks_today(decisions_path: Path, today_et: str) -> int:
    """Count of decisions.jsonl rows whose ts_et falls on `today_et` (YYYY-MM-DD).
    Every tick (HOLD, ENTER, MANAGED, HOLD_BAD_BARS, or this module's own TICK_ERROR)
    writes exactly one decisions.jsonl row, so this is precisely "how many times the
    scheduled task fired today", re-derived fresh every call -- self-healing across
    restarts, can never drift from a separately maintained counter."""
    rows = _read_jsonl(decisions_path)
    return sum(1 for r in rows if str(r.get("ts_et", "")).startswith(today_et))


def count_orders_lifetime(journal_path: Path) -> int:
    """Count of journal.jsonl 'PLACED' events whose broker order response carries no
    _error/_refused/_skipped marker -- i.e. genuinely ACCEPTED by Alpaca, not merely
    attempted (place_entry always journals PLACED before checking the response).
    Reads 0 while BLOCKED_NO_ACCOUNT, honestly, since place_entry is never reached on
    that path (run_tick short-circuits before calling it)."""
    rows = _read_jsonl(journal_path)
    n = 0
    for r in rows:
        if r.get("event") != "PLACED":
            continue
        order = r.get("order")
        if isinstance(order, dict) and not (order.get("_error") or order.get("_refused") or order.get("_skipped")):
            n += 1
    return n


def account_status() -> str:
    """'LIVE' when a dedicated twin account is configured AND Alpaca has activated crypto
    on it; 'BLOCKED_NO_ACCOUNT' when secrets.json has no 'twin' entry yet (FileNotFoundError
    = not created, KeyError = file exists but missing the entry); 'BLOCKED_CRYPTO_NOT_APPROVED'
    when the account exists/authenticates but crypto_status != 'ACTIVE' (mirrors run_tick's
    own creds try/except exactly, including the crypto-approval check added 2026-07-11 after
    confirming via Alpaca's docs + live account reads that crypto shares an account's existing
    approval state, not a separate account type -- see crypto_twin_broker.CryptoNotApprovedError).
    NOTE: 'LIVE' describes ACCOUNT CONFIGURATION, not order placement -- whether orders
    actually fire additionally depends on the task's own --live flag, which is separate (and
    already on, safely no-op'ing, per the T3 build note)."""
    try:
        broker.get_twin_creds()
        return "LIVE"
    except (FileNotFoundError, KeyError):
        return "BLOCKED_NO_ACCOUNT"
    except broker.CryptoNotApprovedError:
        return "BLOCKED_CRYPTO_NOT_APPROVED"


def _read_breaker_tripped(cfg: ctc.TwinConfig) -> Optional[bool]:
    p = cfg.state_dir / "breaker.json"
    if not p.exists():
        return None
    try:
        return bool(json.loads(p.read_text(encoding="utf-8")).get("tripped", False))
    except (OSError, json.JSONDecodeError):
        return None


# --- B1c: path-coverage scoreboard summary (fail-open, RE-DERIVED every call) -----------
def _read_path_coverage_doc(cfg: ctc.TwinConfig) -> dict:
    p = cfg.state_dir / "path-coverage.json"
    if not p.exists():
        return {}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def summarize_path_coverage(coverage_doc: dict) -> dict:
    """{path_coverage, branches_green_today, incidents_today} from a path-coverage.json
    doc (crypto_twin_scenarios._load_coverage's on-disk shape). Fail-open on a
    missing/malformed doc (empty branches dict, zero counts) -- never raises, mirrors
    every other fact in this file. `path_coverage` carries EACH branch's tier alongside
    its status so a downstream reader (the firm-brief line, B2) can render e.g. "5/6 LIVE
    branches green, bear-sim lane pending" without re-deriving tier from BRANCH_REGISTRY
    itself."""
    branches = coverage_doc.get("branches", {}) if isinstance(coverage_doc, dict) else {}
    rendered: dict = {}
    green = 0
    incidents = 0
    for name, rec in branches.items():
        if not isinstance(rec, dict):
            continue
        status = rec.get("status", "PENDING")
        rendered[name] = {
            "tier": rec.get("tier", "LIVE"),
            "status": status,
            "count_today": rec.get("count_today", 0),
            "last_exercised_utc": rec.get("last_exercised_utc"),
            "last_result": rec.get("last_result"),
        }
        if status == "GREEN":
            green += 1
        elif status == "INCIDENT":
            incidents += 1
    return {"path_coverage": rendered, "branches_green_today": green, "incidents_today": incidents}


# --- position snapshot + last-trade (T3 latency-drill follow-up, 2026-08-01) -------------
# J's explicit weekend order after the watch-loop latency drill (commit af849657): "make
# sure we're able to properly watch trades." That drill found this glance file carried NO
# position/P&L fields at all -- only last_action/breaker/coverage -- so a normal twin trade
# was invisible to every downstream surface (firm_brief renders straight off this file; the
# dashboard has zero twin integration, confirmed by grep before this shipped). Both
# summaries below are RE-DERIVED every call from the twin's own existing ledgers -- same
# "never a second source of truth" discipline as summarize_path_coverage above -- and
# NEITHER adds a network call.
def _remaining_qty_btc(position: dict, cfg: ctc.TwinConfig) -> Optional[float]:
    """UNIT-LOT MODE (crypto_twin_core.TwinConfig's own docstring): a position's REAL held
    BTC size is always `remaining_units * cfg.unit_qty_btc` -- the exact conversion
    manage_positions itself uses for a SELL_PARTIAL (`btc_qty = round(units_sold *
    cfg.unit_qty_btc, 8)`). `remaining_units` is runner_qty once TP1 has filled (2 of the
    default 3 units already sold), else the full total_qty."""
    st = position.get("exit_state") or {}
    total_qty = st.get("total_qty")
    runner_qty = st.get("runner_qty")
    tp1_filled = bool(st.get("tp1_filled", False))
    units = runner_qty if (tp1_filled and runner_qty is not None) else total_qty
    if units is None:
        return None
    try:
        return round(float(units) * cfg.unit_qty_btc, 8)
    except (TypeError, ValueError):
        return None


def _tick_quote_mid(row: Optional[dict], symbol: str) -> Optional[float]:
    """(best+worst)/2 from THIS tick's own exit_pass entry for `symbol` -- manage_positions
    already called broker.get_crypto_quote_hilo while managing an already-open position
    this tick, so reading it back here is zero extra network calls. None when exit_pass
    carries no entry for `symbol` (e.g. the very tick a position was just entered, before
    it existed for manage_positions to have quoted)."""
    for entry in (row or {}).get("exit_pass") or []:
        if isinstance(entry, dict) and entry.get("symbol") == symbol:
            best, worst = entry.get("best"), entry.get("worst")
            if best is not None and worst is not None:
                try:
                    return round((float(best) + float(worst)) / 2.0, 4)
                except (TypeError, ValueError):
                    return None
    return None


def _latest_decisions_price(decisions_path: Path, symbol: str) -> Optional[float]:
    """OFF-TICK / NO-QUOTE FALLBACK ONLY: the latest decisions.jsonl row's own `price`
    field for `symbol` (scanned newest-first). Only reached when THIS tick's row carries
    neither a fresh tick_quote_mid nor a bar-close price (a TICK_ERROR row has no `price`
    key at all -- see _tick_error_row above) -- see summarize_position's current_mid_source
    tiers for the full fallback order."""
    rows = _read_jsonl(decisions_path)
    for r in reversed(rows):
        if r.get("symbol") == symbol and r.get("price") is not None:
            try:
                return float(r["price"])
            except (TypeError, ValueError):
                continue
    return None


def summarize_position(cfg: ctc.TwinConfig, *, row: Optional[dict], now_utc: datetime,
                       decisions_path: Optional[Path] = None) -> dict:
    """POSITION SNAPSHOT: position_status/symbol/qty/entry_price/current_mid/
    unrealized_usd/unrealized_pct/time_in_trade_min -- RE-DERIVED every call from
    exit-state.json (crypto_twin_core.get_open_position, the SAME source run_tick itself
    reads for its own decision-row position_status) so this is never a second, possibly-
    divergent store of position truth.

    position_status is "flat"/"long" ONLY -- Alpaca crypto is cash/long-only (see
    crypto_twin_core.place_entry's docstring: a bear verdict never reaches place_entry,
    action=SKIP_NO_SHORT_CRYPTO instead), so there is no "short" to ever report. Read
    directly from exit-state.json rather than trusting row['position_status'] (which reads
    "unknown" on a TICK_ERROR/HOLD_BAD_BARS row even though the position itself, if any, is
    perfectly well-known) -- so this block stays accurate even on an errored tick.

    current_mid is sourced BEST-FIRST from data THIS tick already fetched -- this function
    NEVER adds a new network call:
      1. tick_quote_mid          -- exit_pass's own best/worst quote, fetched by
                                    manage_positions THIS tick (only present when the
                                    position was already open BEFORE this tick, i.e. not
                                    the entry tick itself).
      2. tick_bar_close          -- row['price'], the closed 5m bar's close
                                    fetch_closed_bars fetches every healthy tick (present
                                    on the entry tick too).
      3. decisions_jsonl_fallback -- the latest decisions.jsonl row's own price for this
                                    symbol, read fresh from disk. Only reached when `row`
                                    itself carries neither of the above -- a TICK_ERROR row
                                    (no price key at all) while a position from a PRIOR
                                    tick is still open, or write_twin_health called
                                    standalone with no fresh row.
    `current_mid_source` names exactly which tier supplied it -- never silently blended,
    and every field stays honestly None rather than fabricated when truly unknown."""
    symbol = cfg.symbol
    position = ctc.get_open_position(cfg)
    if position is None:
        return {
            "position_status": "flat", "symbol": None, "qty": None, "entry_price": None,
            "current_mid": None, "current_mid_source": None,
            "unrealized_usd": None, "unrealized_pct": None, "time_in_trade_min": None,
        }

    st = position.get("exit_state") or {}
    entry_price = st.get("entry_premium")
    qty = _remaining_qty_btc(position, cfg)

    current_mid = _tick_quote_mid(row, symbol)
    source = "tick_quote_mid" if current_mid is not None else None
    if current_mid is None:
        price = (row or {}).get("price")
        if price is not None:
            try:
                current_mid = float(price)
                source = "tick_bar_close"
            except (TypeError, ValueError):
                current_mid = None
    if current_mid is None:
        dp = decisions_path or (cfg.state_dir / "decisions.jsonl")
        current_mid = _latest_decisions_price(dp, symbol)
        if current_mid is not None:
            source = "decisions_jsonl_fallback"

    unrealized_usd = unrealized_pct = None
    if entry_price is not None and current_mid is not None:
        try:
            ep = float(entry_price)
            if ep > 0:
                unrealized_pct = round((current_mid - ep) / ep * 100.0, 4)
                if qty is not None:
                    unrealized_usd = round((current_mid - ep) * qty, 6)
        except (TypeError, ValueError):
            pass

    time_in_trade_min = None
    entered_at = position.get("entered_at_utc")
    if entered_at:
        try:
            dt_ = datetime.fromisoformat(str(entered_at))
            if dt_.tzinfo is None:
                dt_ = dt_.replace(tzinfo=timezone.utc)
            time_in_trade_min = round((now_utc - dt_).total_seconds() / 60.0, 2)
        except ValueError:
            time_in_trade_min = None

    return {
        "position_status": "long", "symbol": symbol, "qty": qty,
        "entry_price": entry_price, "current_mid": current_mid,
        "current_mid_source": source,
        "unrealized_usd": unrealized_usd, "unrealized_pct": unrealized_pct,
        "time_in_trade_min": time_in_trade_min,
    }


def summarize_last_trade(journal_path: Path) -> Optional[dict]:
    """The most recent CLOSED/EXIT_FILLED journal.jsonl row (scanned newest-first).
    journal.jsonl is append-only, so when a real fill capture succeeds EXIT_FILLED always
    lands strictly AFTER its paired CLOSED row (see crypto_twin_core._journal_exit_fill,
    called immediately after the CLOSED/MANAGED row for that same exit) -- scanning
    newest-first therefore naturally prefers EXIT_FILLED (which carries realized_usd/
    realized_pct) and only falls back to a bare CLOSED row (realized_usd/pct left honestly
    None, never fabricated) for a WATCH-mode or close-failed exit that never got a fill
    captured. Returns None when the twin has never closed a single round trip yet.

    side is always the literal string 'long' -- Alpaca crypto is cash/long-only (bear
    verdicts are SKIP_NO_SHORT_CRYPTO'd before place_entry is ever called, see
    crypto_twin_core.run_tick), so every REAL completed trade in this ledger is
    unambiguously a long round trip; this is a documented fact, not a guessed default."""
    rows = _read_jsonl(journal_path)
    for r in reversed(rows):
        if r.get("event") in ("CLOSED", "EXIT_FILLED"):
            return {
                "ts": r.get("ts_utc"),
                "side": "long",
                "realized_usd": r.get("realized_usd"),
                "realized_pct": r.get("realized_pct"),
            }
    return None


# --- twin-health.json --------------------------------------------------------------------
def write_twin_health(cfg: ctc.TwinConfig, *, row: Optional[dict], error: Optional[str],
                      now_et: datetime, health_path: Path = HEALTH_PATH,
                      now_utc: Optional[datetime] = None) -> dict:
    """Builds + writes the twin-health.json snapshot. `health_path` defaults to the
    production HEALTH_PATH but is an explicit override (mirrors run_tick's own
    injectable now_utc/raw_bars pattern) so tests never touch the real file.

    last_error reflects ONLY this tick -- None means THIS tick was clean, even if a
    prior tick errored (history lives in decisions.jsonl's TICK_ERROR rows + the
    soak-log's per-hour n_errors, not here; this file is a "right now" glance).

    `now_utc` (new, optional, defaults to real wall-clock -- mirrors every other
    injectable-clock parameter in this module) drives `position`'s time_in_trade_min.
    `position` and `last_trade` are ADDITIVE keys (2026-08-01, see the section above) --
    every existing reader (firm_brief.render_twin_lines, twin_sentinel.read_health_facts)
    reads named keys via .get() and ignores unknown ones, confirmed by grep before this
    shipped; every pre-existing caller/test that omits the new `now_utc` kwarg is
    unaffected (it defaults to real wall-clock, same as every other clock param here)."""
    now_utc = now_utc or datetime.now(timezone.utc)
    today_et = now_et.strftime("%Y-%m-%d")
    coverage_summary = summarize_path_coverage(_read_path_coverage_doc(cfg))
    position = summarize_position(cfg, row=row, now_utc=now_utc)
    last_trade = summarize_last_trade(cfg.state_dir / "journal.jsonl")
    health = {
        "last_tick_et": now_et.isoformat(),
        "ticks_today": count_ticks_today(cfg.state_dir / "decisions.jsonl", today_et),
        "last_action": (row or {}).get("action"),
        "breaker_tripped": _read_breaker_tripped(cfg),
        "account_status": account_status(),
        "n_orders_lifetime": count_orders_lifetime(cfg.state_dir / "journal.jsonl"),
        "last_error": error,
        **coverage_summary,  # B1c: path_coverage, branches_green_today, incidents_today
        "position": position,      # T3 latency-drill follow-up, 2026-08-01
        "last_trade": last_trade,  # T3 latency-drill follow-up, 2026-08-01
    }
    health_path.parent.mkdir(parents=True, exist_ok=True)
    health_path.write_text(json.dumps(health, indent=2), encoding="utf-8")
    return health


# --- soak-log.jsonl (hourly rollup, watermarked) ------------------------------------------
def _soak_log_path(cfg: ctc.TwinConfig) -> Path:
    return cfg.state_dir / "soak-log.jsonl"


def _soak_watermark_path(cfg: ctc.TwinConfig) -> Path:
    return cfg.state_dir / "soak-watermark.json"


def _load_watermark(cfg: ctc.TwinConfig) -> Optional[str]:
    p = _soak_watermark_path(cfg)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8")).get("last_period_end_et")
    except (OSError, json.JSONDecodeError):
        return None


def _save_watermark(cfg: ctc.TwinConfig, period_end_et: str) -> None:
    p = _soak_watermark_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({"last_period_end_et": period_end_et}, indent=2), encoding="utf-8")


def _hour_floor(now_et: datetime) -> datetime:
    return now_et.replace(minute=0, second=0, microsecond=0)


def append_soak_row_if_due(cfg: ctc.TwinConfig, *, now_et: datetime) -> Optional[dict]:
    """Appends ONE soak-log.jsonl row per elapsed ET hour. Watermarked via
    soak-watermark.json (persisted on disk -- survives a task restart, so a gap never
    re-rolls-up an hour twice) -- returns None on every call that is NOT the first
    tick to cross an hour boundary (the common case: 11 of every 12 ticks at 5-min
    cadence). A multi-hour gap (e.g. the box was off overnight) does not loop trying
    to backfill one row per skipped hour -- it produces ONE honest row whose
    period_start/period_end span the true gap, which is simpler and cannot spin.

    Summarizes decisions.jsonl rows in [period_start, hour_floor): tick count,
    TICK_ERROR count, and the full action distribution (HOLD/ENTERED/MANAGED/
    TICK_ERROR/... counts) -- everything crypto_twin_soak_report.py needs without
    re-scanning raw decisions.jsonl itself for historical hours.
    """
    hour_floor = _hour_floor(now_et)
    hour_floor_iso = hour_floor.isoformat()
    last = _load_watermark(cfg)
    if last is not None and last >= hour_floor_iso:
        return None  # this hour is already rolled up

    period_start_iso = last or (hour_floor - timedelta(hours=1)).isoformat()
    rows = _read_jsonl(cfg.state_dir / "decisions.jsonl")
    in_window = [r for r in rows if period_start_iso <= str(r.get("ts_et", "")) < hour_floor_iso]

    dist: dict[str, int] = {}
    for r in in_window:
        action = str(r.get("action", "UNKNOWN"))
        dist[action] = dist.get(action, 0) + 1

    soak_row = {
        "period_start_et": period_start_iso,
        "period_end_et": hour_floor_iso,
        "n_ticks": len(in_window),
        "n_errors": dist.get("TICK_ERROR", 0),
        "action_distribution": dist,
        "written_at_et": now_et.isoformat(),
    }
    p = _soak_log_path(cfg)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(soak_row) + "\n")
    _save_watermark(cfg, hour_floor_iso)
    return soak_row


# --- the wrapped tick (the scheduled-task entrypoint) -------------------------------------
def _tick_error_row(cfg: ctc.TwinConfig, *, now_et: datetime, now_utc: datetime,
                    live: bool, error_str: str) -> dict:
    return {
        "ts_et": now_et.isoformat(), "ts_utc": now_utc.isoformat(),
        "account": cfg.account_label, "twin": True, "symbol": cfg.symbol,
        "armed": live, "verdict": "HOLD", "side": None, "setup": None,
        "triggers": [], "reason": error_str, "trigger_level_exact": None,
        "exit_pass": [], "action": "TICK_ERROR", "position_status": "unknown",
    }


def run_tick_with_health(cfg: ctc.TwinConfig = ctc.TwinConfig(), *, live: bool = False,
                         now_utc: Optional[datetime] = None, now_et: Optional[datetime] = None,
                         raw_bars: Optional[list[dict]] = None,
                         health_path: Path = HEALTH_PATH) -> dict:
    """The T3 scheduled-task entrypoint: crypto_twin_scenarios.run_scenario_tick()
    (B1b: the scenario-scheduler-wrapped tick -- itself a thin layer over
    crypto_twin_core.run_tick(), see that module's docstring) wrapped in a catch-all so a
    genuine exception is captured (never silently lost under pythonw's discarded
    stderr), logged as a TICK_ERROR decision row, and reflected in twin-health.json's
    last_error -- then ALWAYS writes the health snapshot and the hourly soak rollup,
    whether the tick succeeded or not. This function itself never raises; the only way
    to know it is unhealthy is to read what it wrote down.

    `now_utc`/`now_et`/`raw_bars` are all injectable (default to real network/wall-
    clock) -- mirrors run_tick's own injectable-clock pattern, so this wrapper is
    fully testable without the network or real time.
    """
    now_utc = now_utc or datetime.now(timezone.utc)
    now_et = now_et or et_now()

    error_str: Optional[str] = None
    row: Optional[dict] = None
    try:
        row = cts.run_scenario_tick(cfg, live=live, now_utc=now_utc, raw_bars=raw_bars)["row"]
    except Exception as e:  # noqa: BLE001 -- deliberate outermost catch-all; see module docstring.
        error_str = f"{type(e).__name__}: {e}"
        row = _tick_error_row(cfg, now_et=now_et, now_utc=now_utc, live=live, error_str=error_str)
        try:
            ctc.log_decision(cfg, row)
        except Exception:  # noqa: BLE001 -- best-effort; the health snapshot below still tries.
            pass

    try:
        health = write_twin_health(cfg, row=row, error=error_str, now_et=now_et,
                                   health_path=health_path, now_utc=now_utc)
    except Exception as e:  # noqa: BLE001 -- visibility must not itself become a crash.
        health = {"write_failed": f"{type(e).__name__}: {e}"}

    try:
        soak_row = append_soak_row_if_due(cfg, now_et=now_et)
    except Exception:  # noqa: BLE001
        soak_row = None

    return {"row": row, "health": health, "soak_row": soak_row, "error": error_str}


# --- CLI ------------------------------------------------------------------------------
def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(
        description="Crypto Twin health-wrapped tick -- the Gamma_CryptoTwin scheduled-task entrypoint")
    parser.add_argument("--live", action="store_true", help="place real paper orders (default WATCH)")
    args = parser.parse_args(argv)

    result = run_tick_with_health(live=args.live)

    # BROKER-CANARY-SENTINEL-HOOKUP (queue.md 2026-07-11): the one-line piggyback.
    # bc.probe() is already fail-open internally (never raises -- see its own module
    # docstring), so this call can never affect this tick's action/error/exit-code.
    # The try/except is belt-and-suspenders only, kept OUTSIDE run_tick_with_health so
    # the twin's own tested tick path (40+ existing tests) is untouched by this addition.
    canary_result: Optional[dict] = None
    try:
        canary_result = bc.probe()
    except Exception:  # noqa: BLE001 -- the canary must never break the twin's own tick
        pass

    print(json.dumps({
        "action": (result["row"] or {}).get("action"),
        "error": result["error"],
        "health": result["health"],
        "soak_row_written": result["soak_row"] is not None,
        "broker_canary": (canary_result or {}).get("assess", {}).get("verdict"),
    }, indent=2))
    return 0 if result["error"] is None else 1


if __name__ == "__main__":
    raise SystemExit(main())

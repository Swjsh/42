"""sector_rows.py -- ONE per-lane portfolio table: crypto, futures, non-SPY options,
SPY options (GOAL-GAMMA-STATION-2026-09-13 item (13); plan `dapper-cuddling-peacock.md`
Slice 3).

WHY THIS EXISTS: J (2026-09-13 step-back) -- "It's gonna run the different sectors of
crypto, futures, non-SPY options, and SPY options." Today those lanes are invisible as a
PORTFOLIO: each one's health lives in its own directory and nobody sees them side by
side, so a dark lane (futures RED since 09-08, multi-symbol killed-but-still-firing,
weekly frozen) stays invisible until someone happens to open that one directory.

WHAT THIS IS NOT: per the plan's own subtraction list, this is explicitly NOT a new
JSON producer ("No sector-board.json -- the table is rendered by the existing HOME
generator from files that exist") and NOT a new scheduled task. `build_sector_rows()`
below is a pure reader over ledgers/summaries OTHER code already writes.
`setup/scripts/obsidian_vault_sync.py` renders its output as `## Sectors` on HOME.md.
`setup/scripts/station_facts.py` (owned by a different builder on this same goal) is
expected to fold the same rows into the Station facts block so RED/zombie/frozen lanes
become cards -- that wiring is NOT done here (this module has no opinion on who calls
it), it only has to be import-safe and side-effect-free for that to work later.

CONTRACT (do not weaken -- a future edit that breaks any of these breaks HOME.md):
  - `build_sector_rows()` is a PURE function: no writes, no network, no LLM call, ever.
  - FAIL-OPEN per lane: an unreadable/missing PRIMARY source file for a lane degrades
    THAT lane's row to state="unknown", health="amber", last_evidence_et="unknown",
    window_pnl="n/a", evidence="source missing: <repo-relative path>" -- never an
    exception. A bug inside one lane's builder function is caught the same way, so one
    bad lane can never take down the other seven (C7 -- "a dark lane must still
    render, that is exactly when it matters most").
  - `window_pnl` is a NUMBER only where an EXISTING summary file already states one
    (go-live-gate.json's book-wide as-traded total, the crypto twin's own
    challenger-h1-summary window, the futures autopsy's total_pnl_usd) -- this module
    never sums raw fills/ticks itself. Every other lane honestly reports "n/a".
  - `state` and `health` are closed enumerations (STATE_VALUES / HEALTH_VALUES) --
    every row uses one of them, nothing invented ad hoc per lane.
  - Never reads/prints a credential. accounts.json carries none; this module does not
    read secrets.json, any *.pem, or any key_ref value.

Row shape (one dict per lane): lane, state, arm_or_acct_alias, last_evidence_et,
evidence, window_pnl, health, doc.

VERIFIED CORRECTION (2026-09-13, this module's own read -- see `_kalshi_row`'s
docstring): the task brief that specced this module described the Kalshi SPY-index
leg as dark "waiting on the RSA key + .pem". That is not what the files on disk say --
the .pem and its secrets.json entry have existed since 2026-08-09. The row below (and
the corrected gamma-wants.json entry this same goal item writes) report the verified
reason instead: the tick script was never put on a recurring schedule, and the RTH
liquidity survey still verdicts the S&P-index series BLEED/NO-ATM-QUOTES as of 09-11.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)
from et_clock import et_now  # noqa: E402
import twin_ledger_io as tlio  # noqa: E402

STATE_VALUES = frozenset(
    {"armed-paper", "shadow", "killed", "dormant", "dead", "pending", "unknown"}
)
HEALTH_VALUES = frozenset({"green", "amber", "red", "frozen", "zombie"})

# The SPY 0DTE core fleet's own instrument tag (accounts.json) -- the more honest
# discriminator than status=="active" alone, since weekly-1 is also "pending_build"
# on a *different* instrument and must never be swept into this lane's alias list.
_SPY_CORE_INSTRUMENT = "SPY_0DTE_OPTION"

TICKERS_ARMS = ("tickers-1", "tickers-2", "tickers-3")

_DATETIME_CORE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})")


# --------------------------------------------------------------------------- #
# Shared fail-open helpers -- every one of these returns None (never raises) on
# any read/parse/stat failure. Callers turn None into the row's own honest
# fallback ("unknown" / "n/a"), never a guess.
# --------------------------------------------------------------------------- #

def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig", errors="replace"))
    except Exception:  # noqa: BLE001 -- fail-open by contract
        return None


def _read_jsonl_last(path: Path) -> Optional[dict]:
    """The last non-blank decoded JSON row of a .jsonl file, or None if the file is
    missing, empty, or its last line is not valid JSON."""
    try:
        last_line: Optional[str] = None
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    last_line = line
        if last_line is None:
            return None
        row = json.loads(last_line)
        return row if isinstance(row, dict) else None
    except Exception:  # noqa: BLE001
        return None


def _count_lines(path: Path) -> Optional[int]:
    try:
        n = 0
        with path.open(encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if line.strip():
                    n += 1
        return n
    except Exception:  # noqa: BLE001
        return None


def _mtime_et(path: Path) -> Optional[str]:
    """Source file's mtime as an ET string. Same donor pattern as
    station_facts.py::_mtime_stamp_et -- file mtimes are POSIX UTC epoch seconds
    regardless of local timezone, so et_clock's DST-aware et_now(now_utc=...) is the
    correct (and only sanctioned) conversion; see CLAUDE.md's TIME discipline note."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    dt_utc = datetime.fromtimestamp(mtime, tz=timezone.utc)
    return et_now(now_utc=dt_utc).strftime("%Y-%m-%d %H:%M:%S ET")


def _utc_iso_to_et(raw: Any) -> Optional[str]:
    """Parses a UTC ISO-8601 string (a 'ts_utc'/'generated_at_utc'-named field) and
    converts to a 'YYYY-MM-DD HH:MM:SS ET' string via et_clock. None on any parse
    failure -- never fabricated."""
    if not raw or not isinstance(raw, str):
        return None
    try:
        s = raw.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_utc = dt.astimezone(timezone.utc)
        return et_now(now_utc=dt_utc).strftime("%Y-%m-%d %H:%M:%S ET")
    except Exception:  # noqa: BLE001
        return None


def _already_et(raw: Any) -> Optional[str]:
    """Cosmetic normalizer for a field that is ALREADY Eastern Time by construction
    (its own name says so: 'ts_et', 'generated_et', 'checked_at_et'). Regex-extracts
    the 'YYYY-MM-DD HH:MM:SS' core and re-appends ' ET', discarding whatever
    fractional-seconds / numeric-offset / 'ET'-suffix noise the producer already had
    -- performs NO timezone ARITHMETIC (the value is already ET; running it back
    through et_now() would double-shift it across a DST boundary). None if no
    recognizable date+time core is found."""
    if not raw or not isinstance(raw, str):
        return None
    m = _DATETIME_CORE_RE.search(raw)
    if not m:
        return None
    return f"{m.group(1)} {m.group(2)} ET"


def _rel(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root)).replace("\\", "/")
    except ValueError:
        return str(path)


def _unknown_row(lane: str, doc: str, missing_path: Path, root: Path) -> dict:
    return {
        "lane": lane,
        "state": "unknown",
        "arm_or_acct_alias": "n/a",
        "last_evidence_et": "unknown",
        "evidence": f"source missing: {_rel(missing_path, root)}",
        "window_pnl": "n/a",
        "health": "amber",
        "doc": doc,
    }


# --------------------------------------------------------------------------- #
# Per-lane builders. Each returns exactly one row dict, and each is individually
# fail-open (a missing PRIMARY source degrades to _unknown_row, never raises).
# --------------------------------------------------------------------------- #

def _spy_core_row(root: Path) -> dict:
    """SPY 0DTE core -- the flagship fleet, 5 arms, paper real-fills. Primary
    source: automation/state/fleet/accounts.json, read for `id`/`instrument`/
    `status` ONLY (never `key_ref` or any credential field -- the file carries none,
    but this function does not touch that field even so), filtered to
    instrument==SPY_0DTE_OPTION and status=='active'. Secondary: the ONE go-live
    number this project computes (analysis/go-live-gate.json) -- read verbatim,
    never re-derived here (that file's own docstring: 'REPORTING INSTRUMENT ONLY').
    health=green reflects the LANE's operational state (it ticks every session,
    Ready/last=0 per MAP.md's daily-loop table) -- the go-live gate's RED verdict is
    a readiness-for-LIVE-MONEY bar, a different question, surfaced in `evidence`
    instead of downgrading a functioning paper lane's health."""
    lane = "SPY 0DTE core"
    doc = "CLAUDE.md"
    accounts_path = root / "automation" / "state" / "fleet" / "accounts.json"
    accounts = _read_json(accounts_path)
    if not isinstance(accounts, dict) or not isinstance(accounts.get("arms"), list):
        return _unknown_row(lane, doc, accounts_path, root)

    core_arms = [
        a for a in accounts["arms"]
        if isinstance(a, dict)
        and a.get("instrument") == _SPY_CORE_INSTRUMENT
        and a.get("status") == "active"
    ]
    alias = ", ".join(str(a.get("id", "?")) for a in core_arms) or "n/a"

    gate_path = root / "analysis" / "go-live-gate.json"
    gate = _read_json(gate_path)
    if isinstance(gate, dict):
        verdict = gate.get("overall_verdict", "?")
        rollup = ((gate.get("criteria") or {}).get("statistical") or {}).get(
            "book_wide_correlated_rollup"
        ) or {}
        as_traded = rollup.get("as_traded") or {}
        n_days = as_traded.get("n_days", "?")
        pnl = as_traded.get("total_pnl")
        window_pnl: Any = float(pnl) if isinstance(pnl, (int, float)) else "n/a"
        last_evidence_et = _already_et(gate.get("generated_et")) or "unknown"
        evidence = (
            f"go-live gate {verdict} over {n_days} scored trading days "
            f"(book-wide as-traded PF CI-lower bar; the gate ARMS NOTHING, it only reports)"
        )
    else:
        window_pnl = "n/a"
        last_evidence_et = "unknown"
        evidence = (
            f"{len(core_arms)} active core arm(s) found in accounts.json; "
            f"go-live gate unreadable: {_rel(gate_path, root)}"
        )

    return {
        "lane": lane,
        "state": "armed-paper",
        "arm_or_acct_alias": alias,
        "last_evidence_et": last_evidence_et,
        "evidence": evidence,
        "window_pnl": window_pnl,
        "health": "green",
        "doc": doc,
    }


def _crypto_twin_row(root: Path) -> dict:
    """Crypto twin -- 24/7 mechanism-validation arm on Alpaca paper; P&L is NEVER SPY
    evidence (doctrine, TWIN-PROGRAM.md). Primary source: decisions.jsonl (~56K rows
    and growing -- the twin's own tick-by-tick ledger). Secondary:
    challenger-h1-summary.json's forward_since_start window for a genuinely-STATED
    (not summed-here) P&L number -- the forward clock only started 2026-09-13
    16:25 UTC, so 0.0 there is an honest 'no trades yet', not a missing value."""
    lane = "Crypto twin"
    doc = "markdown/planning/TWIN-PROGRAM.md"
    twin_dir = root / "automation" / "state" / "crypto-twin"
    decisions_path = twin_dir / "decisions.jsonl"
    last_row = _read_jsonl_last(decisions_path)
    if last_row is None:
        return _unknown_row(lane, doc, decisions_path, root)

    # Total across the live file + twin_ledger_rotate.py's archived days (2026-09-15) --
    # a plain _count_lines(decisions_path) would silently undercount to "today's rows
    # only" the moment rotation starts moving completed days out of the live file.
    try:
        n_rows = tlio.count_rows(None, live_path=decisions_path,
                                 archive_dir=decisions_path.parent / "archive")
    except OSError:
        n_rows = _count_lines(decisions_path)
    n_rows_s = str(n_rows) if n_rows is not None else "?"
    last_evidence_et = (
        _already_et(last_row.get("ts_et"))
        or _utc_iso_to_et(last_row.get("ts_utc"))
        or "unknown"
    )
    last_action = last_row.get("action", "?")

    summary = _read_json(twin_dir / "challenger-h1-summary.json")
    if isinstance(summary, dict):
        fwd = (summary.get("windows") or {}).get("forward_since_start") or {}
        net = fwd.get("control_net_usd")
        window_pnl: Any = float(net) if isinstance(net, (int, float)) else "n/a"
        start = summary.get("h1_forward_start_utc", "?")
        evidence = (
            f"{n_rows_s} decisions rows, last action {last_action}; H1 forward clock "
            f"from {start} ({fwd.get('control_n', 0)} control trade(s) so far)"
        )
    else:
        window_pnl = "n/a"
        evidence = f"{n_rows_s} decisions rows, last action {last_action}"

    return {
        "lane": lane,
        "state": "armed-paper",
        "arm_or_acct_alias": "crypto-twin",
        "last_evidence_et": last_evidence_et,
        "evidence": evidence,
        "window_pnl": window_pnl,
        "health": "green",
        "doc": doc,
    }


def _futures_row(root: Path) -> dict:
    """Futures (MES/MNQ) -- two sub-lanes (fillsim book + tastytrade SANDBOX real
    fills), neither of them live money. Primary source: futures/health.json, the
    FUSED liveness verdict (7 checks) this project already treats as the lane's one
    health signal (render_other_lanes reads the same file the same way). Secondary:
    analysis/futures/autopsy-latest.json for a STATED (not re-derived) P&L number.
    state='shadow': the book lane is a simulator and the broker lane runs on a
    sandbox, so neither is the 'armed-paper' flagship class the SPY/crypto/tickers
    lanes are.

    autopsy-latest.json is a LIST of DIFFERENT-EVIDENCE-CLASS reports from the same
    run (fills: BROKER / SIMULATED / UNKNOWN), not a time series -- `[-1]` is NOT
    "the most recent run", it is whichever bucket happens to sort last (verified
    2026-09-13: that was the near-empty UNKNOWN bucket, n_trips=0, which would have
    silently reported $0 P&L over real broker evidence of -$93.75). This picks the
    fills=='BROKER' entry explicitly, per this project's own repeated doctrine that
    simulated fills are mechanism evidence and never edge evidence
    (render_other_lanes' identical framing)."""
    lane = "Futures"
    doc = "markdown/futures/README.md"
    health_path = root / "automation" / "state" / "futures" / "health.json"
    health = _read_json(health_path)
    if not isinstance(health, dict):
        return _unknown_row(lane, doc, health_path, root)

    verdict = health.get("verdict", "?")
    reasons = health.get("reasons") or []
    top_reason = reasons[0] if reasons else "no RED/YELLOW reasons logged"
    last_evidence_et = _already_et(health.get("checked_at_et")) or "unknown"
    health_color = {"GREEN": "green", "YELLOW": "amber", "RED": "red"}.get(verdict, "amber")

    autopsy_path = root / "analysis" / "futures" / "autopsy-latest.json"
    autopsy = _read_json(autopsy_path)
    window_pnl: Any = "n/a"
    pnl_note = ""
    if isinstance(autopsy, list):
        broker_run = next(
            (r for r in autopsy if isinstance(r, dict) and r.get("fills") == "BROKER"),
            None,
        )
        if broker_run is not None and isinstance(broker_run.get("total_pnl_usd"), (int, float)):
            window_pnl = float(broker_run["total_pnl_usd"])
            pnl_note = (
                f"; last broker-fills autopsy {broker_run.get('generated_at_et', '?')} "
                f"({broker_run.get('n_trips', '?')} broker trip(s), real fills)"
            )

    return {
        "lane": lane,
        "state": "shadow",
        "arm_or_acct_alias": "mes-mnq-div-futures, mes-linear-sim",
        "last_evidence_et": last_evidence_et,
        "evidence": f"health {verdict}: {top_reason}{pnl_note}",
        "window_pnl": window_pnl,
        "health": health_color,
        "doc": doc,
    }


def _multi_symbol_row(root: Path) -> dict:
    """Multi-symbol options (arm multi-1) -- SHADOW_BUILD, STOPPED_ON_NULL. Primary
    source: automation/state/multi/shadow-ledger.jsonl, the lane's own per-tick
    evidence file, frozen since the 2026-08-20 kill. Gamma_MultiEvaluate /
    Gamma_MultiOutcomes keep firing daily with no order path (read-only) well past
    that kill -- reported here via health='zombie' per the plan's own framing.
    Parking those two tasks is a SEPARATE change (Task Scheduler access) this
    read-only module does not make."""
    lane = "Multi-symbol options"
    doc = "markdown/planning/WEEKLY-OPTIONS-PROGRAM.md"
    ledger_path = root / "automation" / "state" / "multi" / "shadow-ledger.jsonl"
    last_row = _read_jsonl_last(ledger_path)
    if last_row is None:
        return _unknown_row(lane, doc, ledger_path, root)

    last_evidence_et = (
        _already_et(last_row.get("ts_et")) or _mtime_et(ledger_path) or "unknown"
    )
    trades_multi = root / "journal" / "trades-multi.csv"
    csv_note = "trades-multi.csv never created" if not trades_multi.exists() else "trades-multi.csv exists"

    return {
        "lane": lane,
        "state": "killed",
        "arm_or_acct_alias": "multi-1",
        "last_evidence_et": last_evidence_et,
        "evidence": (
            "shadow-ledger frozen since the kill (lane state STOPPED_ON_NULL); "
            "Gamma_MultiEvaluate/Gamma_MultiOutcomes still fire daily, read-only, "
            f"no order path; {csv_note}"
        ),
        "window_pnl": "n/a",
        "health": "zombie",
        "doc": doc,
    }


def _weekly_options_row(root: Path) -> dict:
    """Weekly options (GLD/QQQ, arm weekly-1) -- account wired 2026-09-12 but the v1
    signal is REFUTED (fails its own random-entry null on all 4 expiry arms), so
    fleet_executor never trades a non-'active' status. Primary source:
    expiry-experiment-shadow-ledger.jsonl, frozen since the refutation (no per-row
    timestamp field, so its own mtime is the honest 'last evidence'). Secondary:
    accounts.json's weekly-1 entry, status only."""
    lane = "Weekly options (GLD/QQQ)"
    doc = "markdown/planning/WEEKLY-OPTIONS-PROGRAM.md"
    ledger_path = root / "automation" / "state" / "weekly" / "expiry-experiment-shadow-ledger.jsonl"
    if not ledger_path.exists():
        return _unknown_row(lane, doc, ledger_path, root)

    last_evidence_et = _mtime_et(ledger_path) or "unknown"
    n_rows = _count_lines(ledger_path)
    n_rows_s = str(n_rows) if n_rows is not None else "?"

    status = "?"
    accounts = _read_json(root / "automation" / "state" / "fleet" / "accounts.json")
    if isinstance(accounts, dict):
        for a in accounts.get("arms") or []:
            if isinstance(a, dict) and a.get("id") == "weekly-1":
                status = a.get("status", "?")
                break

    return {
        "lane": lane,
        "state": "pending",
        "arm_or_acct_alias": "weekly-1",
        "last_evidence_et": last_evidence_et,
        "evidence": (
            f"expiry-experiment ledger frozen ({n_rows_s} rows); v1 signal refuted "
            f"(fails random-entry null on all 4 expiry arms); account status={status}"
        ),
        "window_pnl": "n/a",
        "health": "frozen",
        "doc": doc,
    }


def _tickers_row(root: Path) -> dict:
    """Tickers lane (AMZN/AAPL/NVDA/TSLA/AVGO/QQQ/GLD, 3 paper arms, production
    scorer) -- already has its own rich per-session block on HOME
    (obsidian_vault_sync.render_tickers_lane); this row is the one-line portfolio
    summary. Primary source: the freshest of the 3 arms' own ledger.jsonl (the
    per-tick evaluation ledger each arm writes -- day-*.json files are per-SESSION
    summaries the existing block already tables, not this row's job to repeat)."""
    lane = "Tickers (non-SPY 0DTE)"
    doc = "markdown/planning/TICKERS-LANE.md"
    tickers_dir = root / "automation" / "state" / "tickers"

    stamps: list[tuple[str, Path]] = []
    for arm in TICKERS_ARMS:
        p = tickers_dir / arm / "ledger.jsonl"
        if p.exists():
            stamps.append((arm, p))
    if not stamps:
        return _unknown_row(lane, doc, tickers_dir / TICKERS_ARMS[0] / "ledger.jsonl", root)

    freshest_arm, freshest_path = max(stamps, key=lambda t: t[1].stat().st_mtime)
    last_evidence_et = _mtime_et(freshest_path) or "unknown"

    day_files = sorted((tickers_dir / freshest_arm).glob("day-????-??-??.json"))
    last_session = day_files[-1].stem[len("day-"):] if day_files else "?"

    return {
        "lane": lane,
        "state": "armed-paper",
        "arm_or_acct_alias": ", ".join(TICKERS_ARMS),
        "last_evidence_et": last_evidence_et,
        "evidence": (
            f"3 paper arms on the same production scorer as SPY core; last session "
            f"{last_session}; full per-session P&L table already on HOME "
            f"(render_tickers_lane)"
        ),
        "window_pnl": "n/a",
        "health": "green",
        "doc": doc,
    }


def _kalshi_row(root: Path) -> dict:
    """Kalshi (2 legs, 1 lane) -- weather leg alive on its own schedule
    (Gamma_KalshiAuto), SPY-index leg dark since 2026-08-09.

    VERIFIED CORRECTION (this module's own read, 2026-09-13): the task brief that
    specced this row described the SPY-index leg as blocked on J creating an RSA
    key. That is NOT what the files say -- automation/state/fleet/kalshi-1.pem and
    the secrets.json 'kalshi-1' entry KALSHI-LANE-SETUP.md steps 1-2 ask for both
    exist, dated 2026-08-09 (the same day the last shadow-ledger row was written).
    SCHEDULED-TASKS.md carries Gamma_KalshiAuto (weather) and
    Gamma_KalshiLiquiditySurvey (spread survey, no trading) but no task for
    kalshi_tick.py / run-kalshi-tick.ps1 -- the SPY-index leg was never put on a
    recurring schedule. Its own liquidity survey (analysis/kalshi/liquidity-survey-
    2026-09-11.json) still verdicts KXINXU/KXINX BLEED / NO-ATM-QUOTES against the
    5c spread gate. This function reports the credential file's existence
    honestly; it does not read the .pem's contents or secrets.json's values."""
    lane = "Kalshi (prediction markets)"
    doc = "markdown/prediction-markets/KALSHI-LANE-SETUP.md"
    kalshi_dir = root / "automation" / "state" / "kalshi"
    weather_path = kalshi_dir / "weather-predictions.jsonl"
    weather_last = _read_jsonl_last(weather_path)
    if weather_last is None:
        return _unknown_row(lane, doc, weather_path, root)

    weather_et = _utc_iso_to_et(weather_last.get("ts_utc")) or "unknown"
    weather_day = weather_last.get("day", "?")

    last_tick = _read_json(kalshi_dir / "last-tick.json")
    spy_leg_date = last_tick.get("date", "?") if isinstance(last_tick, dict) else "?"

    pem_exists = (root / "automation" / "state" / "fleet" / "kalshi-1.pem").exists()
    key_note = "credentials PRESENT since 08-09" if pem_exists else "credentials MISSING"

    return {
        "lane": lane,
        "state": "shadow",
        "arm_or_acct_alias": "kalshi-1",
        "last_evidence_et": weather_et,
        "evidence": (
            f"weather leg alive (last prediction {weather_day}); SPY-index leg dark "
            f"since {spy_leg_date} -- {key_note}, never scheduled (no Gamma_KalshiTick "
            f"task), RTH spreads still BLEED/NO-ATM-QUOTES as of the 09-11 liquidity survey"
        ),
        "window_pnl": "n/a",
        "health": "amber",
        "doc": doc,
    }


def _station_row(root: Path) -> dict:
    """Station (the local loop) -- not a trading lane; every 30 min it reads
    ledgers/hypotheses and proposes ideas via the local planner, and never places an
    order. Primary source: automation/state/station/loop-ledger.jsonl (one row per
    fire: ok / yielded / error)."""
    lane = "Station (local loop)"
    doc = "markdown/planning/GAMMA-STATION.md"
    ledger_path = root / "automation" / "state" / "station" / "loop-ledger.jsonl"
    last_row = _read_jsonl_last(ledger_path)
    if last_row is None:
        return _unknown_row(lane, doc, ledger_path, root)

    last_evidence_et = (
        _already_et(last_row.get("ts_et")) or _mtime_et(ledger_path) or "unknown"
    )
    n_fires = _count_lines(ledger_path)
    n_fires_s = str(n_fires) if n_fires is not None else "?"
    status = last_row.get("status", "?")
    reason = last_row.get("reason")
    status_note = f"{status}" + (f" ({reason})" if reason else "")

    board = _read_json(root / "automation" / "state" / "station" / "ideas-board.json")
    n_cards = len(board) if isinstance(board, list) else "?"

    return {
        "lane": lane,
        "state": "shadow",
        "arm_or_acct_alias": "station-loop",
        "last_evidence_et": last_evidence_et,
        "evidence": (
            f"{n_fires_s} fire(s) logged, last {status_note}; {n_cards} idea card(s) "
            f"on the board; never trades"
        ),
        "window_pnl": "n/a",
        "health": "green",
        "doc": doc,
    }


_LANE_BUILDERS = (
    _spy_core_row,
    _crypto_twin_row,
    _futures_row,
    _multi_symbol_row,
    _weekly_options_row,
    _tickers_row,
    _kalshi_row,
    _station_row,
)


def build_sector_rows(repo_root: "str | Path | None" = None) -> list[dict]:
    """One dict per lane -- see module docstring for the row shape and the
    fail-open contract. PURE function: no writes, no network, no LLM call. Never
    raises: a bug or a bad value inside one lane's builder degrades ONLY that
    lane's row to state='unknown' (belt-and-suspenders on top of each builder's own
    fail-open reads), so a mistake here can never take HOME.md down with it.
    """
    root = Path(repo_root) if repo_root is not None else REPO
    rows: list[dict] = []
    for builder in _LANE_BUILDERS:
        try:
            row = builder(root)
            if row.get("state") not in STATE_VALUES or row.get("health") not in HEALTH_VALUES:
                raise ValueError(
                    f"{builder.__name__} produced an invalid state/health enum: "
                    f"state={row.get('state')!r} health={row.get('health')!r}"
                )
        except Exception as exc:  # noqa: BLE001 -- one bad lane must never break the table
            lane_name = builder.__name__.strip("_").replace("_row", "").replace("_", " ")
            row = {
                "lane": lane_name or builder.__name__,
                "state": "unknown",
                "arm_or_acct_alias": "n/a",
                "last_evidence_et": "unknown",
                "evidence": f"builder raised: {exc}",
                "window_pnl": "n/a",
                "health": "amber",
                "doc": "n/a",
            }
        rows.append(row)
    return rows


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def _format_cell(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:+,.2f}"
    return str(v)


def _print_table(rows: list[dict]) -> None:
    cols = ["lane", "state", "arm_or_acct_alias", "last_evidence_et", "evidence",
            "window_pnl", "health", "doc"]
    if not rows:
        print("(no rows)")
        return
    widths = {c: max(len(c), *(len(_format_cell(r.get(c, ""))) for r in rows)) for c in cols}

    def _fmt(vals: dict) -> str:
        return " | ".join(_format_cell(vals.get(c, "")).ljust(widths[c]) for c in cols)

    print(_fmt({c: c for c in cols}))
    print("-+-".join("-" * widths[c] for c in cols))
    for r in rows:
        print(_fmt(r))


def main(argv: "list[str] | None" = None) -> int:
    parser = argparse.ArgumentParser(
        description="Print the Gamma per-lane sector table (crypto / futures / "
                     "non-SPY options / SPY options)."
    )
    parser.add_argument("--print", dest="do_print", action="store_true",
                        help="print the sector table to stdout (the default with no "
                             "flags)")
    parser.add_argument("--json", dest="do_json", action="store_true",
                        help="print build_sector_rows() as a single JSON array to "
                             "stdout instead of the text table (additive, 2026-09-13 "
                             "GAMMA-HQ-VISUALS: dashboard/lib/hq.ts shells this)")
    args = parser.parse_args(argv)
    rows = build_sector_rows()
    if args.do_json:
        print(json.dumps(rows, default=str))
        return 0
    _print_table(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""fleet_journal_bridge.py -- closes the Rule-8 journaling debt for the 4
fleet_rest arms (safe-1, safe-3, risky-1, risky-3) AND the 2 core mcp_heartbeat
arms (safe-2, bold-2): their real round-trip fills were never reaching
`journal/trades.csv`, so per doctrine ("if it's not in the journal, it didn't
happen") real fills were invisible to the journal system of record. This script
is that bridge. It does NOT touch analysis/autopsies/ (a separate consumer being
fixed elsewhere).

CORE-ACCOUNT EXTENSION (2026-07-17, SAFE-TRADES-CSV-JOURNALING-GAP, filed by the
2026-07-17 safe-tape audit): this module's docstring used to claim safe-2/bold-2
had "an existing journaling path... written by the live heartbeat" and was
deliberately out of scope here. That path does NOT exist -- verified empirically:
`journal/trades.csv` had ZERO automated engine rows for account_id=='safe' across
multiple real trading days (2026-07-16, 2026-07-17), including a `bollinger_squeeze`
extra-setup (G4 side-channel) fill worth +$105 that reached the broker and pinged
Discord but never reached the journal. The only core rows that WERE present were
J-called manual trades (a separate, working pathway -- j_intent_journal.py /
the log-trade skill) plus a handful of legacy one-off "RECONCILE_FILL" backfills.
broker_fills.py ALREADY computes correct engine-vs-manual attribution for
safe-2/bold-2 round trips in pnl-statement.json (its ATTRIBUTION RULE checks
`exec` AND `extra_exec` AND `exit_pass` in core-decisions.jsonl) -- so extra_exec
fills get identical treatment to primary fills automatically, with zero new
attribution logic needed here: they're just more `attribution=="engine"` round
trips in the SAME pnl-statement.json array the fleet arms already flow through.
CORE_ARMS below maps arm id -> the short account_id trades.csv already uses for
manual core rows ("safe"/"bold", not "safe-2"/"bold-2") to match the existing
convention. Manual round trips (attribution=="manual") are explicitly EXCLUDED
from the core path in `_primary_round_trips` -- those are J-called trades already
journaled by the separate manual pathway; bridging them here would duplicate them.

SOURCE (preferred -- C1 real-fills authority): `automation/state/pnl-statement.json`'s
`round_trips` array. That file is built by `setup/scripts/broker_fills.py` via
`fleet_broker.load_creds()` READ-ONLY GETs against Alpaca `/v2/account/activities/FILL`,
and is already refreshed every 10 min 09:00-16:00 ET + one 16:05 ET EOD fire by the
`Gamma_BrokerFills` scheduled task. This bridge does NOT re-call Alpaca or import
`fleet_broker` itself: it is a PURE local-file transform (zero network calls, zero
credentials touched, stdlib-only) that reads the already-materialized broker-truth
artifact. Re-deriving FIFO round-trip pairing here would duplicate broker_fills.py's
tested logic and risk drift between two independently-computed P&L truths -- reading
its output instead guarantees this journal always agrees with what J already sees in
fill_funnel.py / firm_brief.py. Setup/strategy/exit-stage context (not present in the
fills-only statement) is joined in via `automation/state/fills-ledger.jsonl`
(activity_id -> order_id) and each arm's `automation/state/fleet/<arm>/decisions.jsonl`
(order_id -> ENTER decision row / exit action), both also pure local reads.

FALLBACK (only used for an (arm, date) pnl-statement.json has NOTHING for -- e.g. a
day before broker_fills.py's backfill window, or a fresh clone before it has fired):
reconstruct an approximate round trip directly from that arm's decisions.jsonl ENTER
row + the exit_pass action that closed it. Lower fidelity -- there is no true fill
price in the decision ledger, so the exit price is parsed from the exit action's own
threshold text (e.g. "premium_stop @ 0.43"); if no usable price is found the leg is
SKIPPED, never fabricated. Rows built this way are labeled
`fill_quality=decisions_reconstruction (approximate)` so they are never mistaken for
broker-truth. (`automation/state/trade-today.json` is a core-account-only state file,
not per-arm, and is intentionally not used here.)

SCOPE: SPY 0DTE options only. A few of these accounts' Alpaca histories also contain
crypto fills (symbol contains "/") -- excluded here: crypto is gym-only per doctrine
and the option-shaped trades.csv columns (contract/dte/strike/c_or_p) don't fit it.

IDEMPOTENT: `automation/state/.fleet-journal-watermark.json` records every
(arm, entry_activity_id, exit_activity_id) key already written. Re-running (including
across the primary/fallback boundary) appends zero duplicate rows. Rows are appended
(never rewrites/reformats existing trades.csv lines -- some pre-existing rows have
non-canonical quoting; this script only adds well-formed lines after them).

CLI:  backtest/.venv/Scripts/python.exe setup/scripts/fleet_journal_bridge.py
        [--date YYYY-MM-DD] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
FLEET_DIR = STATE / "fleet"
PNL_STATEMENT = STATE / "pnl-statement.json"
FILLS_LEDGER = STATE / "fills-ledger.jsonl"
ACCOUNTS_JSON = FLEET_DIR / "accounts.json"
CORE_DECISIONS = STATE / "core-decisions.jsonl"
TRADES_CSV = REPO / "journal" / "trades.csv"
WATERMARK = STATE / ".fleet-journal-watermark.json"
# THETA-COCKPIT (2026-08-01): theta_clock.py's per-position first-observation snapshot --
# read-only fallback source for delta_at_entry/iv_at_entry/theta_at_entry. See
# _greeks_at_entry()'s docstring for the precedence rule.
THETA_CLOCK_POSITION_STATE = STATE / "theta-clock" / "position-state.json"

# The 3 fleet_rest arms (execution=fleet_rest -> 100% engine per broker_fills.py's
# attribution rule). Intentionally re-declared here (not imported from broker_fills)
# to keep this module dependency-free -- see module docstring.
# safe-1 RETIRED 2026-07-11 (accounts.json status=retired, account reassigned to core Safe
# "safe-2" -- see broker_fills.py's FLEET_REST_ARMS comment for the full mechanism). Its
# historical automation/state/fleet/safe-1/decisions.jsonl is untouched and still readable
# directly by id if ever needed; it just stops being indexed by this default going forward.
FLEET_REST_ARMS: tuple[str, ...] = ("safe-3", "risky-1", "risky-3")

# The 2 core mcp_heartbeat arms -> the short account_id trades.csv already uses for their
# (manually-journaled) rows. Deliberately the SAME mapping as broker_fills.CORE_ARMS
# (re-declared, not imported -- dependency-free, see module docstring), since it must agree
# with the `account` field core-decisions.jsonl rows carry.
CORE_ARMS: dict[str, str] = {"safe-2": "safe", "bold-2": "bold"}

# Everything this bridge journals by default: 3 fleet_rest arms + 2 core arms.
ALL_BRIDGE_ARMS: tuple[str, ...] = FLEET_REST_ARMS + tuple(CORE_ARMS)

# Canonical trades.csv schema. Source of truth: journal/trades.csv header.
# Similar in spirit to backtest/autoresearch/webull_winner_journal.py's SCHEMA (that module
# writes a DIFFERENT file, journal/j-real-winners.csv -- already independently ~41 columns,
# pre-existing drift this change does not touch) -- kept independent (different subsystem/
# venv) but byte-for-byte matched to journal/trades.csv's OWN live header.
#
# THETA-COCKPIT EXTENSION (2026-08-01): added `theta_at_entry` at the END of the schema
# (44th column, was 43). Appending at the end (never inserting mid-schema) is deliberate --
# every real consumer greppable in this repo reads trades.csv by COLUMN NAME (csv.DictReader
# or manual header-zip), never positional index, so an end-appended column cannot misalign any
# existing reader. The on-disk header line itself is migrated exactly once by
# `_ensure_schema_header()` below (idempotent, called at the top of run_bridge()) BEFORE any
# new row is appended -- migrating the header first, before ever writing a 44-value row under
# it, is the one ordering constraint that keeps the file rectangular: old data rows keep their
# original 43 values (csv.DictReader fills a too-short trailing row with None for the new
# column -- fine, they genuinely have no theta_at_entry), while new rows get all 44.
SCHEMA: list[str] = [
    "date", "time_entry", "time_exit", "setup", "contract", "dte", "strike",
    "c_or_p", "qty", "entry_px", "exit_px", "premium_paid", "premium_received",
    "dollar_pnl", "r_multiple", "stop_px", "target_px", "dollar_risk",
    "pct_risk_of_acct", "account_equity_pre", "followed_rules", "setup_quality",
    "fill_quality", "gamma_recommended", "j_override", "hold_minutes",
    "trade_grade", "trade_grade_score", "delta_at_entry", "iv_at_entry",
    "iv_regime", "slippage_cents", "exit_slippage_cents", "tod_bucket",
    "bars_after_trigger", "entry_relative_to_bar", "hold_quality_pct",
    "cf_time_stop_pnl", "cf_high_water_pnl", "archetype_match_json",
    "tape_assistance", "notes_short", "account_id", "theta_at_entry",
]

_OCC_RE = re.compile(r"^([A-Z]+)(\d{2})(\d{2})(\d{2})([CP])(\d{8})$")
_PRICE_RE = re.compile(r"@\s*([\d.]+)")

PRIMARY_SOURCE_LABEL = "pnl-statement.json (T1 broker-truth round_trips)"
FALLBACK_SOURCE_LABEL = "decisions.jsonl reconstruction (approximate -- broker fills unavailable)"


# --------------------------------------------------------------------------- #
# small pure helpers
# --------------------------------------------------------------------------- #
def _is_option(symbol: str) -> bool:
    """OCC option symbols are >=15 chars; crypto pairs contain '/'. Mirrors
    broker_fills._is_option (duplicated intentionally -- see module docstring)."""
    return isinstance(symbol, str) and len(symbol) >= 15 and "/" not in symbol


def _parse_occ_symbol(symbol: str) -> Optional[dict[str, Any]]:
    m = _OCC_RE.match(symbol or "")
    if not m:
        return None
    root, yy, mm, dd, right, strike_raw = m.groups()
    try:
        strike = int(strike_raw) / 1000.0
    except ValueError:
        return None
    return {"root": root, "expiry": f"20{yy}-{mm}-{dd}", "right": right, "strike": strike}


def _fmt_num(x: Any) -> str:
    """Number -> trades.csv-style string (no trailing .0, no float noise)."""
    try:
        f = float(x)
    except (TypeError, ValueError):
        return ""
    if f == int(f):
        return str(int(f))
    return f"{f:g}"


def _tod_bucket(hhmm: str) -> str:
    try:
        h, m = (int(x) for x in hhmm.split(":")[:2])
    except (ValueError, AttributeError):
        return ""
    minutes = h * 60 + m
    if minutes < 11 * 60:
        return "MORNING"
    if minutes < 14 * 60:
        return "MIDDAY"
    return "AFTERNOON"


def _hold_minutes(entry_ts_et: str, exit_ts_et: str) -> str:
    try:
        a = dt.datetime.fromisoformat(entry_ts_et)
        b = dt.datetime.fromisoformat(exit_ts_et)
        return str(int(round((b - a).total_seconds() / 60)))
    except (ValueError, TypeError):
        return ""


def _rt_key(rt: dict) -> str:
    return f"{rt.get('arm')}::{rt.get('entry_activity_id')}::{rt.get('exit_activity_id')}"


# --------------------------------------------------------------------------- #
# ledger / index readers (all pure local-file reads)
# --------------------------------------------------------------------------- #
def _load_jsonl(path: Path) -> list[dict]:
    rows: list[dict] = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except ValueError:
                continue
    return rows


def _load_accounts_meta(accounts_json_path: Path) -> dict[str, dict]:
    if not accounts_json_path.exists():
        return {}
    try:
        data = json.loads(accounts_json_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, dict] = {}
    for a in data.get("arms", []):
        aid = a.get("id")
        if aid:
            out[aid] = {"cell": a.get("cell"), "starting_equity": a.get("starting_equity")}
    return out


def _build_activity_to_order(fills_ledger_path: Path, arms: tuple[str, ...]) -> dict[str, str]:
    out: dict[str, str] = {}
    for row in _load_jsonl(fills_ledger_path):
        if row.get("arm") not in arms:
            continue
        aid, oid = row.get("activity_id"), row.get("order_id")
        if aid and oid:
            out[aid] = oid
    return out


def _build_decision_index(fleet_dir: Path, arm: str) -> tuple[dict[str, dict], dict[str, dict]]:
    """order_id -> ENTER decision row, order_id -> exit action info, for one arm."""
    path = fleet_dir / arm / "decisions.jsonl"
    by_order_entry: dict[str, dict] = {}
    by_order_exit: dict[str, dict] = {}
    for row in _load_jsonl(path):
        placement = row.get("placement") or {}
        broker = placement.get("broker") or {}
        oid = broker.get("id")
        if oid and str(row.get("action", "")).startswith("ENTER"):
            r = dict(row)
            r["_order_id"] = oid
            by_order_entry.setdefault(oid, r)
        for ep in (row.get("exit_pass") or []):
            for act in (ep.get("actions") or []):
                b = act.get("broker") or {}
                eoid = b.get("id")
                if eoid and act.get("placed"):
                    by_order_exit.setdefault(eoid, {
                        "stage": act.get("stage", ""), "reason": act.get("reason", ""),
                        "kind": act.get("kind", ""), "_order_id": eoid,
                    })
    return by_order_entry, by_order_exit


_TIER_RE = re.compile(r"\(tier (\w+)\)")


def _build_core_decision_index(core_decisions_path: Path, account: str) -> tuple[dict[str, dict], dict[str, dict]]:
    """order_id -> synthetic entry-decision dict, order_id -> exit action info, for one
    CORE account ("safe"/"bold"). core-decisions.jsonl uses a DIFFERENT schema than
    fleet_rest's decisions.jsonl (see trade_today_watcher.py::_is_engine_attributed's
    docstring for the full split): the primary path logs an entry under row["exec"], the
    G4 extra-setup side-channel logs under row["extra_exec"][i]["exec"] -- BOTH are the
    SAME shape (status/symbol/setup/entry_px/stop/tp/equity/broker.id), so both normalize
    into the exact same synthetic entry_dec build_row() already understands from the fleet
    path (entry_dec.setup_name / .reason / .equity / .placement.{entry_px,stop,tp} /
    ._order_id) -- this is what gives extra_exec fills IDENTICAL trades.csv treatment to
    primary fills, with zero new attribution logic: they're just two sources of the same
    normalized shape. exit_pass has the SAME structure as the fleet schema already handles
    (exit_pass[].actions[].broker.id/.stage/.reason/.placed) -- only the row-level filter
    (`account` field instead of `arm_id`) differs from `_build_decision_index`."""
    by_order_entry: dict[str, dict] = {}
    by_order_exit: dict[str, dict] = {}
    for row in _load_jsonl(core_decisions_path):
        if row.get("account") != account:
            continue
        top_reason = row.get("reason", "") or ""
        tier_m = _TIER_RE.search(top_reason)
        quality = tier_m.group(1) if tier_m else ""

        # (exec_dict, reason_text, is_extra) triples -- primary and extra_exec need DIFFERENT
        # reason sources: the top-level row["reason"] describes the PRIMARY verdict (often
        # "no setup passed scoring" on a tick whose extra_exec fired anyway -- that text would
        # be actively misleading attached to the extra-setup fill). extra_exec fills instead
        # pull their firing rationale from row["extra_signals"] (matched by setup name,
        # fired==true), the same triggers/confidence data the live Discord ping shows.
        exec_candidates: list[tuple[dict, str, bool]] = []
        primary = row.get("exec")
        if isinstance(primary, dict):
            exec_candidates.append((primary, top_reason, False))
        extra_signals_by_setup = {
            s.get("setup_name"): s for s in (row.get("extra_signals") or [])
            if isinstance(s, dict) and s.get("fired")
        }
        for extra in (row.get("extra_exec") or []):
            if not (isinstance(extra, dict) and isinstance(extra.get("exec"), dict)):
                continue
            setup_name = extra.get("setup") or extra["exec"].get("setup")
            sig = extra_signals_by_setup.get(setup_name)
            if sig:
                reason = (f"{setup_name} fired via G4 extra-setup side-channel "
                          f"(triggers: {', '.join(sig.get('triggers') or [])}; "
                          f"confidence {sig.get('confidence', 'n/a')})")
            else:
                reason = f"{setup_name} fired via G4 extra-setup side-channel"
            exec_candidates.append((extra["exec"], reason, True))

        for ex, reason_text, is_extra in exec_candidates:
            broker = ex.get("broker") or {}
            oid = broker.get("id")
            if not oid:
                continue
            entry_dec = {
                "setup_name": ex.get("setup"),
                "quality": quality,
                "reason": reason_text,
                "placement": {"entry_px": ex.get("entry_px"), "stop": ex.get("stop"), "tp": ex.get("tp")},
                "equity": ex.get("equity"),
                "_order_id": oid,
                "_via_extra_exec": is_extra,
                # THETA-COCKPIT (2026-08-01): pass through the G8 per-entry greeks capture
                # (heartbeat_core._capture_greeks -> plan["greeks"] -> this row's exec.greeks),
                # PRIMARY source for delta_at_entry/iv_at_entry/theta_at_entry in build_row().
                # Empirically {} on every real entry checked so far (see theta_clock.py's
                # module docstring) -- build_row() falls back to theta_clock's own
                # first-observation snapshot when this is empty, never fabricates a value.
                "greeks": ex.get("greeks"),
            }
            by_order_entry.setdefault(oid, entry_dec)

        for ep in (row.get("exit_pass") or []):
            for act in (ep.get("actions") or []):
                b = act.get("broker") or {}
                eoid = b.get("id")
                if eoid and act.get("placed"):
                    by_order_exit.setdefault(eoid, {
                        "stage": act.get("stage", ""), "reason": act.get("reason", ""),
                        "kind": act.get("kind", ""), "_order_id": eoid,
                    })
    return by_order_entry, by_order_exit


def _load_theta_clock_positions(path: Path) -> dict[str, dict]:
    """Fail-open read of theta_clock.py's position-state.json -> {"{arm}::{symbol}": entry
    snapshot dict}. Missing/corrupt/not-yet-run (e.g. a fresh clone before Gamma_ThetaClock has
    ever fired) -> {} -- delta/iv/theta_at_entry just stay blank, exactly like today, never a
    crash in the journaling path over an unrelated instrument's file."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data.get("positions") or {}


def _load_watermark(path: Path) -> dict:
    if not path.exists():
        return {"schema": "fleet-journal-watermark-v1", "processed": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"schema": "fleet-journal-watermark-v1", "processed": {}}
    data.setdefault("processed", {})
    return data


def _save_watermark(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")


# --------------------------------------------------------------------------- #
# round-trip sources
# --------------------------------------------------------------------------- #
def _primary_round_trips(pnl_statement_path: Path, arms: tuple[str, ...],
                          date_filter: Optional[str]) -> list[dict]:
    if not pnl_statement_path.exists():
        return []
    try:
        stmt = json.loads(pnl_statement_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for rt in stmt.get("round_trips", []):
        if rt.get("arm") not in arms:
            continue
        if not _is_option(rt.get("symbol", "")):
            continue  # crypto / non-option -- out of scope (crypto is gym-only)
        if date_filter and rt.get("date_et") != date_filter:
            continue
        if rt.get("arm") in CORE_ARMS and rt.get("attribution") != "engine":
            # A core-account round trip broker_fills.py attributed "manual" is a J-called
            # trade -- already journaled by the separate manual pathway (j_intent_journal.py
            # / the log-trade skill). Bridging it here would write a SECOND, duplicate row
            # for the same fill. Fleet_rest arms need no such check (100% engine by
            # broker_fills.py's own attribution rule -- see FLEET_REST_ARMS comment).
            continue
        out.append(rt)
    return out


def _fallback_round_trips(fleet_dir: Path, arms: tuple[str, ...],
                           date_filter: Optional[str]) -> list[dict]:
    """Single forward pass per arm: track open entries by symbol, close them out
    against the first placed exit_pass action seen for that symbol. Never invents
    a price -- a leg with no parseable exit price is dropped, not guessed."""
    out: list[dict] = []
    for arm in arms:
        if arm in CORE_ARMS:
            # This reconstruction reads the fleet_rest decisions.jsonl schema
            # (placement.broker / action.startswith("ENTER")) -- core accounts write a
            # different schema (core-decisions.jsonl, exec/extra_exec) and don't need a
            # fallback anyway: broker_fills.py's BACKFILL_SINCE window already covers every
            # core-account trading day pnl-statement.json has ever seen. Explicit skip
            # (rather than relying on fleet_dir/{arm}/decisions.jsonl simply not existing)
            # so this stays correct even if that directory is ever created for another
            # purpose (e.g. exit-state.json already lives there for safe-2/bold-2).
            continue
        path = fleet_dir / arm / "decisions.jsonl"
        open_lots: dict[str, dict] = {}
        for row in _load_jsonl(path):
            placement = row.get("placement") or {}
            broker = placement.get("broker") or {}
            action = str(row.get("action", ""))
            symbol = placement.get("symbol")
            if action.startswith("ENTER") and broker.get("id") and symbol and _is_option(symbol):
                entry_row = dict(row)
                entry_row["_order_id"] = broker.get("id")
                open_lots[symbol] = entry_row
            for ep in (row.get("exit_pass") or []):
                sym = ep.get("symbol")
                entry_row = open_lots.get(sym)
                if not entry_row:
                    continue
                for act in (ep.get("actions") or []):
                    if not act.get("placed"):
                        continue
                    entry_placement = entry_row.get("placement") or {}
                    entry_px = entry_placement.get("entry_px")
                    entry_ts = entry_row.get("ts_et", "")
                    date_et = entry_ts[:10]
                    qty = entry_row.get("qty")
                    exit_ts = row.get("ts_et", "")
                    exit_broker = act.get("broker") or {}
                    m = _PRICE_RE.search(act.get("reason", ""))
                    exit_px = float(m.group(1)) if m else None
                    del open_lots[sym]
                    if date_filter and date_et != date_filter:
                        break
                    if exit_px is None or entry_px is None or qty is None:
                        break  # never fabricate a price/pnl -- drop this leg
                    pnl = round((exit_px - float(entry_px)) * 100 * float(qty), 2)
                    out.append({
                        "arm": arm, "symbol": sym,
                        "entry_activity_id": f"decisions:{entry_row['_order_id']}",
                        "exit_activity_id": f"decisions:{exit_broker.get('id') or exit_ts}",
                        "entry_price": entry_px, "exit_price": exit_px, "qty": qty,
                        "pnl": pnl, "entry_ts_et": entry_ts, "exit_ts_et": exit_ts,
                        "attribution": "engine", "date_et": date_et,
                        "_entry_dec": entry_row,
                        "_exit_info": {"stage": act.get("stage", ""), "reason": act.get("reason", ""),
                                       "_order_id": exit_broker.get("id")},
                    })
                    break
    return out


def _greeks_at_entry(entry_dec: dict, theta_clock_entry: Optional[dict]) -> dict:
    """PURE: resolve delta_at_entry/iv_at_entry/theta_at_entry with an explicit precedence --
    PRIMARY = the G8 per-entry broker-greeks capture already threaded onto entry_dec["greeks"]
    (decisions.jsonl exec.greeks, core arms only today); FALLBACK = theta_clock.py's own
    first-observation snapshot (automation/state/theta-clock/position-state.json, keyed
    "{arm}::{symbol}", within ~1 min of fill -- covers fleet_rest arms, which have no G8 path
    at all, AND covers core arms on the (empirically common) tick where G8's own capture came
    back empty). Returns "" (matching every other still-unpopulated cell in this schema) for
    any field neither source has -- NEVER fabricates a number into a column named as if it
    were real broker data (a downstream consumer -- perps leverage calibration -- was cited as
    blocked on this column meaning real greeks)."""
    primary = entry_dec.get("greeks") or {}
    if not isinstance(primary, dict):
        primary = {}
    fallback = theta_clock_entry or {}

    def _pick(primary_key: str, fallback_key: str):
        v = primary.get(primary_key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v, "broker_snapshot_at_entry (decisions.jsonl exec.greeks)"
        v = fallback.get(fallback_key)
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return v, "theta_clock_first_observation (~1min-of-fill fallback)"
        return None, None

    delta, delta_src = _pick("delta", "entry_delta")
    iv, iv_src = _pick("iv", "entry_iv")
    theta, theta_src = _pick("theta", "entry_theta")
    return {
        "delta_at_entry": "" if delta is None else delta,
        "iv_at_entry": "" if iv is None else iv,
        "theta_at_entry": "" if theta is None else theta,
        "_sources": {"delta": delta_src, "iv": iv_src, "theta": theta_src},
    }


# --------------------------------------------------------------------------- #
# row assembly
# --------------------------------------------------------------------------- #
def build_row(rt: dict, entry_dec: Optional[dict], exit_info: Optional[dict],
              arm_meta: dict, source_label: str,
              theta_clock_entry: Optional[dict] = None) -> Optional[dict[str, str]]:
    """One round trip + joined decision context -> one canonical trades.csv row.
    Returns None only if the symbol itself isn't a parseable SPY option (defensive;
    callers already filter to _is_option before reaching here).

    `theta_clock_entry` (2026-08-01, optional, defaults None -- every pre-existing call site
    stays byte-for-byte unaffected) is the FALLBACK source for delta/iv/theta_at_entry -- see
    `_greeks_at_entry`'s docstring."""
    parsed = _parse_occ_symbol(rt.get("symbol", ""))
    if not parsed:
        return None

    arm = rt["arm"]
    qty = rt.get("qty")
    entry_px = rt.get("entry_price")
    exit_px = rt.get("exit_price")
    pnl = rt.get("pnl")
    entry_ts = rt.get("entry_ts_et", "") or ""
    exit_ts = rt.get("exit_ts_et", "") or ""
    date_et = rt.get("date_et") or entry_ts[:10]

    premium_paid = round((float(entry_px) if entry_px is not None else 0.0) * 100 * (float(qty) if qty else 0.0), 2)
    premium_received = round((float(exit_px) if exit_px is not None else 0.0) * 100 * (float(qty) if qty else 0.0), 2)

    entry_dec = entry_dec or {}
    exit_info = exit_info or {}
    placement = entry_dec.get("placement") or {}
    greeks_at_entry = _greeks_at_entry(entry_dec, theta_clock_entry)

    setup_name = entry_dec.get("setup_name") or "UNKNOWN_FLEET_FILL"
    quality = entry_dec.get("quality", "")
    entry_reason = entry_dec.get("reason", "")
    stop_px = placement.get("stop", "")
    target_px = placement.get("tp", "")
    decision_entry_px = placement.get("entry_px")
    equity_pre = entry_dec.get("equity")
    if equity_pre is None:
        equity_pre = arm_meta.get("starting_equity")

    exit_stage = exit_info.get("stage", "")
    exit_reason = exit_info.get("reason", "")

    pct_risk = ""
    try:
        if equity_pre:
            pct_risk = f"{(premium_paid / float(equity_pre)) * 100:.1f}%"
    except (TypeError, ZeroDivisionError, ValueError):
        pct_risk = ""

    slippage_cents = ""
    try:
        if decision_entry_px is not None and entry_px is not None:
            slippage_cents = str(round((float(entry_px) - float(decision_entry_px)) * 100))
    except (TypeError, ValueError):
        slippage_cents = ""

    entry_hhmm = entry_ts.split("T", 1)[1][:5] if "T" in entry_ts else ""
    attribution = rt.get("attribution", "engine")
    is_engine = attribution == "engine"
    is_broker_truth = source_label == PRIMARY_SOURCE_LABEL

    order_bits = []
    if rt.get("entry_activity_id"):
        order_bits.append(f"entry_act={str(rt['entry_activity_id']).split('::')[-1][:8]}")
    if rt.get("exit_activity_id"):
        order_bits.append(f"exit_act={str(rt['exit_activity_id']).split('::')[-1][:8]}")

    is_core = arm in CORE_ARMS
    account_id = CORE_ARMS.get(arm, arm)

    if is_core:
        notes = (
            f"CORE ACCOUNT {arm} (account_id={account_id}, mcp_heartbeat live engine). "
            f"Entry reason: {entry_reason or 'n/a'}. "
            + (f"Exit stage={exit_stage} ({exit_reason}). " if exit_stage else "")
            + f"Source: {source_label}. "
            + (f"{', '.join(order_bits)}. " if order_bits else "")
            + "Backfilled by fleet_journal_bridge.py (Rule-8 core-account journaling gap, "
              "2026-07-17 safe-tape audit)."
        )
        if not is_engine:
            notes = ("UNEXPECTED attribution=manual on a core account bridged row -- should "
                      "have been filtered upstream, verify for a duplicate. " + notes)
    else:
        notes = (
            f"FLEET ARM {arm} ({arm_meta.get('cell', '?')}). "
            f"Entry reason: {entry_reason or 'n/a'}. "
            + (f"Exit stage={exit_stage} ({exit_reason}). " if exit_stage else "")
            + f"Source: {source_label}. "
            + (f"{', '.join(order_bits)}. " if order_bits else "")
            + "Backfilled by fleet_journal_bridge.py (Rule-8 fleet journaling debt, 2026-07-09)."
        )
        if not is_engine:
            notes = "UNEXPECTED attribution=manual on a fleet_rest arm -- verify. " + notes

    arch_json = json.dumps({
        "arm": arm, "cell": arm_meta.get("cell"), "quality": quality,
        "attribution": attribution, "source": source_label,
        "entry_order_id": entry_dec.get("_order_id"),
        "exit_order_id": exit_info.get("_order_id"),
        **({"via_extra_exec": bool(entry_dec.get("_via_extra_exec"))} if is_core else {}),
    }, separators=(",", ":"))

    return {
        "date": date_et,
        "time_entry": entry_ts.split("T", 1)[1][:8] if "T" in entry_ts else "",
        "time_exit": exit_ts.split("T", 1)[1][:8] if "T" in exit_ts else "",
        "setup": setup_name,
        "contract": f"{parsed['root']} {parsed['expiry']} {_fmt_num(parsed['strike'])}{parsed['right']}",
        "dte": "0",
        "strike": _fmt_num(parsed["strike"]),
        "c_or_p": parsed["right"],
        "qty": _fmt_num(qty),
        "entry_px": _fmt_num(entry_px),
        "exit_px": _fmt_num(exit_px),
        "premium_paid": _fmt_num(premium_paid),
        "premium_received": _fmt_num(premium_received),
        "dollar_pnl": _fmt_num(pnl),
        "r_multiple": "N/A",
        "stop_px": _fmt_num(stop_px),
        "target_px": _fmt_num(target_px),
        "dollar_risk": _fmt_num(premium_paid),
        "pct_risk_of_acct": pct_risk,
        "account_equity_pre": _fmt_num(equity_pre) if equity_pre is not None else "",
        "followed_rules": "N/A",
        "setup_quality": quality or "",
        "fill_quality": "real_fill" if is_broker_truth else "decisions_reconstruction (approximate)",
        "gamma_recommended": "Y" if is_engine else "N/A",
        "j_override": "N" if is_engine else "N/A",
        "hold_minutes": _hold_minutes(entry_ts, exit_ts),
        "trade_grade": "",
        "trade_grade_score": "",
        "delta_at_entry": greeks_at_entry["delta_at_entry"],
        "iv_at_entry": greeks_at_entry["iv_at_entry"],
        "iv_regime": "",
        "slippage_cents": slippage_cents,
        "exit_slippage_cents": "",
        "tod_bucket": _tod_bucket(entry_hhmm) if entry_hhmm else "",
        "bars_after_trigger": "",
        "entry_relative_to_bar": "",
        "hold_quality_pct": "",
        "cf_time_stop_pnl": "",
        "cf_high_water_pnl": "",
        "archetype_match_json": arch_json,
        "tape_assistance": "",
        "notes_short": notes,
        "account_id": account_id,
        "theta_at_entry": greeks_at_entry["theta_at_entry"],
    }


def _ensure_schema_header(trades_csv_path: Path) -> bool:
    """ONE-TIME, IDEMPOTENT migration: if the on-disk header is missing the current SCHEMA's
    trailing column(s) (today: just `theta_at_entry`), rewrite ONLY the header line -- every
    existing data row is left byte-for-byte untouched. Safe because every column added by this
    migration is appended at the END of SCHEMA (see SCHEMA's own docstring comment) and every
    real consumer reads by column name, not position.

    Returns True if a migration was performed (for the caller's log line), False if the header
    already matches (the common case on every run after the first) or the file doesn't exist
    yet (a fresh file gets the full header on first write via `_append_rows`, nothing to do
    here). Fail-open in the sense that any read/parse problem is treated as "nothing to
    migrate" -- this must never be the reason a journaling run fails."""
    if not trades_csv_path.exists() or trades_csv_path.stat().st_size == 0:
        return False
    try:
        with trades_csv_path.open("r", newline="", encoding="utf-8-sig") as fh:
            lines = fh.readlines()
    except OSError:
        return False
    if not lines:
        return False
    current_header = next(csv.reader([lines[0]]), [])
    if list(current_header) == SCHEMA:
        return False  # already migrated
    missing = [c for c in SCHEMA if c not in current_header]
    if not missing:
        return False  # header has every SCHEMA column already (e.g. reordered by hand) -- leave it
    # Only ever append missing trailing columns -- never touch/reorder an existing column name,
    # never drop one. This keeps the migration a pure additive, reversible (git-revertible) op.
    new_header_line = ",".join(current_header + missing) + "\n"
    lines[0] = new_header_line
    tmp = trades_csv_path.with_suffix(trades_csv_path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8-sig") as fh:
        fh.writelines(lines)
    tmp.replace(trades_csv_path)
    return True


def _append_rows(trades_csv_path: Path, rows: list[dict]) -> None:
    trades_csv_path.parent.mkdir(parents=True, exist_ok=True)
    needs_header = not trades_csv_path.exists() or trades_csv_path.stat().st_size == 0
    with trades_csv_path.open("a", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        if needs_header:
            w.writerow(SCHEMA)
        for r in rows:
            w.writerow([r.get(c, "") for c in SCHEMA])


# --------------------------------------------------------------------------- #
# orchestration (pure function -- all paths injectable for tests)
# --------------------------------------------------------------------------- #
def run_bridge(*, pnl_statement_path: Path = PNL_STATEMENT, fills_ledger_path: Path = FILLS_LEDGER,
               fleet_dir: Path = FLEET_DIR, accounts_json_path: Path = ACCOUNTS_JSON,
               core_decisions_path: Path = CORE_DECISIONS,
               trades_csv_path: Path = TRADES_CSV, watermark_path: Path = WATERMARK,
               theta_clock_position_state_path: Path = THETA_CLOCK_POSITION_STATE,
               date_filter: Optional[str] = None, dry_run: bool = False,
               arms: tuple[str, ...] = FLEET_REST_ARMS) -> dict:
    arm_meta_all = _load_accounts_meta(accounts_json_path)
    watermark = _load_watermark(watermark_path)
    processed: dict = watermark.get("processed", {})
    theta_clock_positions = _load_theta_clock_positions(theta_clock_position_state_path)

    # THETA-COCKPIT schema migration (2026-08-01): idempotent, additive-only, skipped on a
    # dry run (dry_run means "compute + report, write nothing" -- the header migration IS a
    # write). Must happen BEFORE any new row is appended below -- see SCHEMA's own comment.
    if not dry_run:
        _ensure_schema_header(trades_csv_path)

    primary = _primary_round_trips(pnl_statement_path, arms, date_filter)
    activity_to_order = _build_activity_to_order(fills_ledger_path, arms) if primary else {}
    decision_idx = {}
    if primary:
        for arm in arms:
            if arm in CORE_ARMS:
                decision_idx[arm] = _build_core_decision_index(core_decisions_path, CORE_ARMS[arm])
            else:
                decision_idx[arm] = _build_decision_index(fleet_dir, arm)

    candidates: list[tuple[dict, Optional[dict], Optional[dict], str]] = []
    covered: set[tuple[str, str]] = set()
    for rt in primary:
        covered.add((rt["arm"], rt["date_et"]))
        by_entry, by_exit = decision_idx.get(rt["arm"], ({}, {}))
        eoid = activity_to_order.get(rt.get("entry_activity_id"))
        xoid = activity_to_order.get(rt.get("exit_activity_id"))
        entry_dec = by_entry.get(eoid) if eoid else None
        exit_info = by_exit.get(xoid) if xoid else None
        candidates.append((rt, entry_dec, exit_info, PRIMARY_SOURCE_LABEL))

    # Fallback only fills (arm, date) gaps the primary source had nothing for --
    # it never shadows or duplicates a real broker-truth round trip.
    for rt in _fallback_round_trips(fleet_dir, arms, date_filter):
        if (rt["arm"], rt["date_et"]) in covered:
            continue
        candidates.append((rt, rt.get("_entry_dec"), rt.get("_exit_info"), FALLBACK_SOURCE_LABEL))

    new_rows: list[dict] = []
    per_arm: Counter = Counter()
    dates_seen: set[str] = set()
    skipped_existing = 0
    skipped_unparsed = 0
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat()

    for rt, entry_dec, exit_info, label in candidates:
        key = _rt_key(rt)
        if key in processed:
            skipped_existing += 1
            continue
        arm_meta = arm_meta_all.get(rt["arm"], {})
        tc_key = f"{rt['arm']}::{rt.get('symbol', '')}"
        row = build_row(rt, entry_dec, exit_info, arm_meta, label,
                         theta_clock_entry=theta_clock_positions.get(tc_key))
        if row is None:
            skipped_unparsed += 1
            continue
        new_rows.append(row)
        per_arm[rt["arm"]] += 1
        dates_seen.add(rt["date_et"])
        processed[key] = {"date_et": rt["date_et"], "written_at_utc": now_iso, "source": label}

    if new_rows and not dry_run:
        _append_rows(trades_csv_path, new_rows)
        watermark["processed"] = processed
        watermark["updated_at_utc"] = now_iso
        _save_watermark(watermark_path, watermark)

    return {
        "n_written": len(new_rows), "per_arm": dict(per_arm),
        "dates": sorted(dates_seen), "skipped_existing": skipped_existing,
        "skipped_unparsed": skipped_unparsed, "rows": new_rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Bridge fleet_rest (safe-1/safe-3/risky-1/risky-3) broker-truth "
                     "fills into journal/trades.csv (Rule 8).")
    ap.add_argument("--date", default=None, help="restrict to one ET date YYYY-MM-DD "
                     "(default: all not-yet-journaled history in pnl-statement.json)")
    ap.add_argument("--dry-run", action="store_true", help="compute + report, write nothing")
    args = ap.parse_args()

    summary = run_bridge(date_filter=args.date, dry_run=args.dry_run)
    tag = "(dry-run) " if args.dry_run else ""
    print(f"[fleet_journal_bridge] {tag}{summary['n_written']} new row(s) written, "
          f"{summary['skipped_existing']} already journaled, "
          f"{summary['skipped_unparsed']} skipped (unparseable symbol).")
    if summary["dates"]:
        print(f"  span: {summary['dates'][0]} .. {summary['dates'][-1]} "
              f"({len(summary['dates'])} distinct day(s))")
    for arm, n in sorted(summary["per_arm"].items()):
        print(f"  {arm}: {n} row(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

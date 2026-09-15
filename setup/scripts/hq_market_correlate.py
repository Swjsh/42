"""hq_market_correlate.py -- READ-ONLY market/engine/HQ correlation instrument.

J's ask (2026-09-15): "let the orchestrator see, minute by minute during RTH,
what the market and the engine did next to what the HQ world displayed, and
flag mismatches." This is a pure observer -- it never trades, never writes
to any trading-path file, and never calls a broker write endpoint.

WHY ONE-SHOT (design constraint, not a style choice): setup/scripts/_shared.ps1
#Stop-StaleClaudeProcesses reaps any python.exe older than ~5 min unless it's
in $EXEMPT_DAEMONS. This script is NOT exempt and MUST NOT be made a daemon --
each invocation takes exactly one sample, appends one JSONL row, and exits in
well under 20s. The orchestrator loops it externally (see the `loop_command`
printed by --help, or the return-schema of the build task that created this
file) every ~60s during RTH.

SOURCES (read real paths from the writer, not memory -- verified 2026-09-15):
  - Sight beacon:      automation/state/sight-beacon.json
                        (written by setup/scripts/sight_beacon.py#main,
                        fields: spy, last_bar, ts_et -- see that file's
                        build()/main() for the schema this script reads.)
  - Engine ticks:       automation/state/core-decisions.jsonl
                        (appended by setup/scripts/heartbeat_core.py#_log,
                        one row per account per tick: account="safe"|"bold",
                        ts_et, verdict/action, reason, spy, bear_score,
                        bull_score.)
  - Positions:          automation/state/fleet/safe-2/exit-state.json,
                        automation/state/fleet/bold-2/exit-state.json
                        (HQ-POSITION-TRUTH, 2026-09-15 -- the LIVE truth;
                        the OLDER current-position-{safe,bold}.json pair
                        this script used to read is dead, nothing writes
                        it -- see read_positions()'s own docstring.)
  - Circuit breakers:   automation/state/circuit-breaker.json (safe),
                        automation/state/aggressive/circuit-breaker.json (bold)
                        -- NOTE the two files use a divergent vocabulary
                        (see circuit-breaker.json's own "_schema_note");
                        this script reads only the field present in both:
                        "tripped".
  - HQ dashboard:        GET http://127.0.0.1:3000/api/hq (dashboard/app/api/
                        hq/route.ts) -- build_id, runtime.brain.state,
                        liveAgents, company.personas (Pilot/Gamma (Manager)/
                        Treasurer -- there is no "SPY-core" persona in the
                        roster; recorded as absent rather than invented),
                        trading.core.{safe,bold} (spy/engineBarSpy/vix/
                        ribbon/verdict/action/actionReason/side/setup -- the
                        SAME core-decisions.jsonl row this script also reads
                        directly, via a different reader), trading.readiness,
                        trading.market.live (MARKET-TRUTH, 2026-09-15: the
                        live sight-beacon quote, distinct from the engine's
                        decision-bar price -- see check_hq_live_vs_beacon /
                        check_hq_engine_bar_vs_ledger below for the two
                        separate correctness checks this split enables).

Every field read is wrapped so a missing/stale/malformed source degrades to
null + an "error" string on that field alone -- this script NEVER crashes
and NEVER fabricates a value (failure-honesty rule, CLAUDE.md judgment
guards). Two modes:
  sample (default): take one reading, append one row, exit 0.
  report:           read today's (or --date's) JSONL, print a compact
                     timeline + a MISMATCH list (4 rules, see check_*
                     functions below), exit 0 always.

All paths are injectable (constructor args) so setup/scripts/
test_hq_market_correlate.py can point them at tmp_path fixtures without
touching real state.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
from et_clock import et_now  # noqa: E402

BEACON_PATH = STATE / "sight-beacon.json"
LEDGER_PATH = STATE / "core-decisions.jsonl"
# HQ-POSITION-TRUTH (2026-09-15): repointed off the dead
# current-position-{safe,bold}.json pair (nothing writes them -- root cause
# of the bug this whole task fixes: HQ fell back to HOLD/flat while a real
# broker position stayed open for hours) onto the LIVE per-account truth --
# automation/state/fleet/<arm>/exit-state.json, a dict keyed by open option
# symbol written by setup/scripts/heartbeat_core.py's exit_manager, `{}` ==
# flat. Same source dashboard/lib/hq-positions.ts now reads for /api/hq.
POSITION_PATHS = {"safe-2": STATE / "fleet" / "safe-2" / "exit-state.json", "bold-2": STATE / "fleet" / "bold-2" / "exit-state.json"}
BREAKER_PATHS = {"safe-2": STATE / "circuit-breaker.json", "bold-2": STATE / "aggressive" / "circuit-breaker.json"}
STATION_DIR = STATE / "station"
HQ_URL = "http://127.0.0.1:3000/api/hq"

STALE_BEACON_S = 180
ENGINE_TICK_GAP_S = 180  # rule (c): engine tick missing > 3 min during RTH
HQ_STALE_S = 180  # rule (b)
MISMATCH_SAMPLE_WINDOW = 2  # rule (a): "within 2 samples"

ACCOUNT_TO_ARM = {"safe": "safe-2", "bold": "bold-2"}
LEDGER_TAIL_BYTES = 512 * 1024  # last ~512KiB is plenty for the newest row per account


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _parse_ts_et(ts: Optional[str]) -> Optional[datetime]:
    """Parse a ts_et string ('%Y-%m-%dT%H:%M:%S', no offset -- see
    heartbeat_core.py's own _log docstring) into a naive datetime. Never
    raises; returns None on anything unparseable."""
    if not isinstance(ts, str):
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(ts[:19], fmt)
        except ValueError:
            continue
    return None


# ----------------------------------------------------------------------------
# per-source readers -- each is independently fail-open
# ----------------------------------------------------------------------------

def read_beacon(now_et: datetime, path: Path = BEACON_PATH) -> dict[str, Any]:
    out: dict[str, Any] = {
        "spy_last": None, "bar_time": None, "source_file": str(path),
        "source_age_s": None, "error": None,
    }
    try:
        if not path.exists():
            out["error"] = "beacon file not found"
            return out
        snap = json.loads(path.read_text(encoding="utf-8"))
        out["spy_last"] = snap.get("spy")
        out["bar_time"] = snap.get("last_bar")
        ts = _parse_ts_et(snap.get("ts_et"))
        if ts is not None:
            out["source_age_s"] = round((now_et.replace(tzinfo=None) - ts).total_seconds(), 1)
        else:
            out["source_age_s"] = None
            out["error"] = "beacon ts_et unparseable"
        if not snap.get("ok", True):
            out["error"] = (out["error"] + "; " if out["error"] else "") + "beacon reported not-ok (stale fetch kept)"
    except (OSError, json.JSONDecodeError) as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def _tail_lines(path: Path, tail_bytes: int) -> list[str]:
    """Read the last tail_bytes of a file, return complete non-empty lines
    (drops a likely-truncated first line when the read seeked mid-file --
    same convention as dashboard/lib/hq.ts#readCoreDecisionsLatest)."""
    with path.open("rb") as fh:
        fh.seek(0, 2)
        size = fh.tell()
        start = max(0, size - tail_bytes)
        fh.seek(start)
        data = fh.read()
    text = data.decode("utf-8", errors="replace")
    lines = text.split("\n")
    if start > 0:
        lines = lines[1:]
    return [ln for ln in lines if ln.strip()]


def read_engine(now_et: datetime, ledger_path: Path = LEDGER_PATH) -> dict[str, Any]:
    out: dict[str, Any] = {
        "last_tick_ts": None, "last_tick_age_s": None,
        "per_account": {"safe-2": None, "bold-2": None}, "error": None,
    }
    if not ledger_path.exists():
        out["error"] = "core-decisions.jsonl not found"
        return out
    try:
        lines = _tail_lines(ledger_path, LEDGER_TAIL_BYTES)
    except OSError as e:
        out["error"] = f"{type(e).__name__}: {e}"
        return out

    latest: dict[str, dict[str, Any]] = {}
    for ln in lines:
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        acct = row.get("account")
        if acct not in ("safe", "bold"):
            continue
        ts = row.get("ts_et")
        prev = latest.get(acct)
        if prev is None or (ts or "") >= (prev.get("ts_et") or ""):
            latest[acct] = row

    if not latest:
        out["error"] = "no parseable rows in tail window"
        return out

    newest_ts: Optional[datetime] = None
    for acct, arm in ACCOUNT_TO_ARM.items():
        row = latest.get(acct)
        if row is None:
            out["per_account"][arm] = {"error": f"no {acct} row in tail window"}
            continue
        ts_dt = _parse_ts_et(row.get("ts_et"))
        age_s = round((now_et.replace(tzinfo=None) - ts_dt).total_seconds(), 1) if ts_dt else None
        reason = row.get("reason")
        reason_short = reason[:160] if isinstance(reason, str) else reason
        out["per_account"][arm] = {
            "ts_et": row.get("ts_et"),
            "age_s": age_s,
            "action": row.get("action") or row.get("verdict"),
            # MARKET-TRUTH (2026-09-15): the row's own `spy` field IS the
            # engine's decision-bar price (last CLOSED bar -- no look-ahead
            # by design), needed here so rule (b2) below can compare it
            # against HQ's engineBarSpy without a second ledger read.
            "spy": row.get("spy"),
            "score": {"bear": row.get("bear_score"), "bull": row.get("bull_score")},
            "reason_short": reason_short,
        }
        if ts_dt is not None and (newest_ts is None or ts_dt > newest_ts):
            newest_ts = ts_dt

    if newest_ts is not None:
        out["last_tick_ts"] = _iso(newest_ts)
        out["last_tick_age_s"] = round((now_et.replace(tzinfo=None) - newest_ts).total_seconds(), 1)
    return out


def read_positions(paths: dict[str, Path] = POSITION_PATHS) -> dict[str, Any]:
    """Reads each arm's exit-state.json (dict keyed by open option symbol,
    `{}` == flat). Kept CLI-backward-compatible: `status`/`symbol`/`qty`/
    `entry` still describe the SINGLE most-material open leg (largest qty,
    same "most material fact first" convention lib/hq-positions-pure.ts's
    formatPositionClause uses) when one exists, plus a new `open_count`/
    `open_symbols` pair the p1_position_hidden mismatch rule below reads to
    know "is ANYTHING open" without re-deriving it from `status` alone."""
    out: dict[str, Any] = {}
    for arm, path in paths.items():
        entry: dict[str, Any] = {
            "status": None, "symbol": None, "qty": None, "entry": None,
            "open_count": None, "open_symbols": None,
            "source_file": str(path), "error": None,
        }
        try:
            if not path.exists():
                entry["error"] = "exit-state file not found"
                out[arm] = entry
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                entry["error"] = f"exit-state.json is not a dict (got {type(data).__name__})"
                out[arm] = entry
                continue
            legs = [v for v in data.values() if isinstance(v, dict) and v.get("symbol")]
            entry["open_count"] = len(legs)
            entry["open_symbols"] = [leg.get("symbol") for leg in legs]
            entry["status"] = "open" if legs else "flat"
            if legs:
                biggest = max(legs, key=lambda leg: leg.get("total_qty") or 0)
                entry["symbol"] = biggest.get("symbol")
                entry["qty"] = biggest.get("total_qty")
                entry["entry"] = biggest.get("entry_premium")
        except (OSError, json.JSONDecodeError) as e:
            entry["error"] = f"{type(e).__name__}: {e}"
        out[arm] = entry
    return out


def read_breakers(paths: dict[str, Path] = BREAKER_PATHS) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for arm, path in paths.items():
        entry: dict[str, Any] = {"tripped": None, "source_file": str(path), "error": None}
        try:
            if not path.exists():
                entry["error"] = "circuit-breaker file not found"
                out[arm] = entry
                continue
            data = json.loads(path.read_text(encoding="utf-8"))
            entry["tripped"] = data.get("tripped")
        except (OSError, json.JSONDecodeError) as e:
            entry["error"] = f"{type(e).__name__}: {e}"
        out[arm] = entry
    return out


PERSONA_NAMES_OF_INTEREST = ("Pilot", "Gamma (Manager)", "SPY-core", "Treasurer")


def fetch_hq(url: str = HQ_URL, timeout: float = 5.0) -> dict[str, Any]:
    out: dict[str, Any] = {
        "build_id": None, "brain_state": None, "live_agent_count": None,
        "personas": {}, "market": {}, "market_live": None,
        "trading_readiness": None, "error": None,
    }
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        out["error"] = f"{type(e).__name__}: {e}"
        return out
    except json.JSONDecodeError as e:
        out["error"] = f"malformed /api/hq JSON: {e}"
        return out

    try:
        out["build_id"] = payload.get("build_id")
        runtime = payload.get("runtime") or {}
        out["brain_state"] = (runtime.get("brain") or {}).get("state")
        live_agents = payload.get("liveAgents")
        out["live_agent_count"] = len(live_agents) if isinstance(live_agents, list) else None

        personas = (payload.get("company") or {}).get("personas") or []
        by_name = {p.get("name"): p for p in personas if isinstance(p, dict)}
        for name in PERSONA_NAMES_OF_INTEREST:
            p = by_name.get(name)
            if p is None:
                out["personas"][name] = {"present": False}
                continue
            bubble = p.get("recentOutput") or p.get("lastFireResult")
            out["personas"][name] = {
                "present": True,
                "status": p.get("status"),
                "bubble_text": bubble[:160] if isinstance(bubble, str) else bubble,
            }

        trading = payload.get("trading") or {}
        core = trading.get("core") or {}
        # HQ-POSITION-TRUTH (2026-09-15): trading.position.<acct> is the NEW
        # /api/hq field (dashboard/lib/hq.ts#readTradingStatus, sourced from
        # lib/hq-positions.ts's exit-state.json read -- independent of
        # `core`, which can be null/stale on a given tick even while a real
        # position stays open). Merged into each account's own dict here so
        # rule (p1) below can read `market.<acct>.position.open` without a
        # second payload traversal.
        position = trading.get("position") or {}
        def _merge_account(acct_key: str) -> dict[str, Any]:
            base = core.get(acct_key)
            merged: dict[str, Any] = dict(base) if isinstance(base, dict) else {}
            merged["position"] = position.get(acct_key)
            return merged
        out["market"] = {
            "safe": _merge_account("safe"),
            "bold": _merge_account("bold"),
        }
        # MARKET-TRUTH (2026-09-15): the NEW top-level live field HQ's
        # /api/hq trading payload now carries (dashboard/lib/hq.ts
        # readTradingStatus's `market.live`, sourced from lib/quote.ts's
        # getQuote() over the SAME sight-beacon.json this script also reads
        # directly via read_beacon). This is what rule (b1) below checks
        # against read_beacon's own independent read of that file.
        out["market_live"] = (trading.get("market") or {}).get("live")
        out["trading_readiness"] = trading.get("readiness")
    except (AttributeError, TypeError) as e:
        # payload shape drifted from what this script expects -- fail open on
        # the derived fields, keep whatever was already extracted above.
        out["error"] = (out["error"] + "; " if out["error"] else "") + f"payload shape error: {type(e).__name__}: {e}"
    return out


# ----------------------------------------------------------------------------
# sample mode
# ----------------------------------------------------------------------------

def build_row(now_et: datetime, beacon_path: Path = BEACON_PATH, ledger_path: Path = LEDGER_PATH,
              position_paths: dict[str, Path] = None, breaker_paths: dict[str, Path] = None,
              hq_url: str = HQ_URL) -> dict[str, Any]:
    position_paths = position_paths or POSITION_PATHS
    breaker_paths = breaker_paths or BREAKER_PATHS
    return {
        "ts_et": _iso(now_et),
        "market": read_beacon(now_et, beacon_path),
        "engine": read_engine(now_et, ledger_path),
        "positions": read_positions(position_paths),
        "breakers": read_breakers(breaker_paths),
        "hq": fetch_hq(hq_url),
    }


def out_path_for(now_et: datetime, station_dir: Path = STATION_DIR) -> Path:
    return station_dir / f"market-correlation-{now_et.strftime('%Y-%m-%d')}.jsonl"


def append_row(row: dict[str, Any], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def cmd_sample(args: argparse.Namespace) -> int:
    now_et = et_now()
    row = build_row(
        now_et,
        beacon_path=Path(args.beacon_path) if args.beacon_path else BEACON_PATH,
        ledger_path=Path(args.ledger_path) if args.ledger_path else LEDGER_PATH,
        hq_url=args.hq_url,
    )
    out_path = Path(args.out) if args.out else out_path_for(now_et, Path(args.station_dir) if args.station_dir else STATION_DIR)
    append_row(row, out_path)
    print(json.dumps({"wrote": str(out_path), "ts_et": row["ts_et"],
                       "market_spy": row["market"].get("spy_last"),
                       "market_age_s": row["market"].get("source_age_s"),
                       "engine_last_tick_age_s": row["engine"].get("last_tick_age_s"),
                       "hq_error": row["hq"].get("error")}))
    return 0


# ----------------------------------------------------------------------------
# report mode
# ----------------------------------------------------------------------------

def load_rows(jsonl_path: Path) -> list[dict[str, Any]]:
    if not jsonl_path.exists():
        return []
    rows = []
    for ln in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not ln.strip():
            continue
        try:
            rows.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return rows


def _in_rth(ts: datetime) -> bool:
    start = ts.replace(hour=9, minute=31, second=0, microsecond=0)
    end = ts.replace(hour=15, minute=55, second=0, microsecond=0)
    return start <= ts <= end


def check_action_not_reflected(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """(a) engine action changed (ENTER/EXIT, or a position opened/closed) but
    no HQ field reflected it within MISMATCH_SAMPLE_WINDOW samples."""
    mismatches = []
    prev_actions: dict[str, Optional[str]] = {}
    for i, row in enumerate(rows):
        engine = row.get("engine") or {}
        per_acct = engine.get("per_account") or {}
        for arm, info in per_acct.items():
            if not isinstance(info, dict):
                continue
            action = info.get("action")
            prev = prev_actions.get(arm)
            prev_actions[arm] = action
            if prev is None or action == prev:
                continue
            if not (isinstance(action, str) and action.upper() in ("ENTER", "EXIT")):
                continue
            # look ahead up to MISMATCH_SAMPLE_WINDOW samples for HQ to reflect it
            hq_key = "safe" if arm == "safe-2" else "bold"
            reflected = False
            for j in range(i, min(i + 1 + MISMATCH_SAMPLE_WINDOW, len(rows))):
                hq_market = ((rows[j].get("hq") or {}).get("market") or {}).get(hq_key) or {}
                hq_verdict = hq_market.get("verdict") if isinstance(hq_market, dict) else None
                if isinstance(hq_verdict, str) and hq_verdict.upper() == action.upper():
                    reflected = True
                    break
            if not reflected:
                mismatches.append({
                    "rule": "a_action_not_reflected", "ts_et": row.get("ts_et"),
                    "arm": arm, "action": action,
                    "detail": f"{arm} engine action {action} not seen in HQ within "
                              f"{MISMATCH_SAMPLE_WINDOW} samples",
                })
    return mismatches


HQ_LIVE_PRICE_TOL = 0.05  # rule (b1): HQ live vs beacon must match tightly (same source, ~1 poll apart)
HQ_ENGINE_BAR_TOL = 1e-6  # rule (b2): HQ engineBarSpy vs the SAME ledger row's spy -- exact by construction
B2_LEDGER_STALE_S = 50  # rule (b2): skip when this script's own engine row is this old --
                        # HQ's independent ledger read (dashboard/lib/hq.ts) and this
                        # script's read_engine() each tail core-decisions.jsonl at a
                        # DIFFERENT instant, so near a tick boundary they can legitimately
                        # land on adjacent rows (evidence 2026-09-15: sampled 15:41:02,
                        # this script's row ts 15:40:03 spy=756.925 age=59.5s, while HQ had
                        # already read the 15:41:02 row spy=756.66 written in the same
                        # second -- HQ was correct, this script's read was one tick stale).
                        # A row this old relative to the sample means a newer row likely
                        # exists that this script simply hasn't picked up yet, so a diff
                        # against it is not evidence of a real HQ/ledger drift -- skip it.
                        # A fresh row (age_s <= this) still fires on any real diff.


def check_hq_live_vs_beacon(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """(b1) FIXED price rule (2026-09-15, replaces the old single rule (b),
    which compared the beacon's LIVE price against HQ's per-account `spy` --
    that field is the ENGINE's decision-bar price (last closed bar, by
    design lags live during RTH), so the old rule fired a false mismatch on
    every normal tick where price moved between bar-close and now (the exact
    09:30-09:36 evidence that motivated this fix: engine spy=760.755 vs
    live spy=759.16, a real $1.59 lag, not a bug).

    This rule instead checks HQ's NEW `market.live` field (dashboard/lib/hq.ts
    readTradingStatus, sourced from the SAME sight-beacon.json this script's
    own read_beacon() reads) against read_beacon()'s own reading: they must
    match within HQ_LIVE_PRICE_TOL and HQ's live quote must be fresh
    (age_s < HQ_STALE_S). A real mismatch here means the dashboard's OWN
    live-quote read is broken or serving a different/stale beacon snapshot
    -- not "the engine is lagging," which is expected and no longer flagged."""
    mismatches = []
    for row in rows:
        ts = _parse_ts_et(row.get("ts_et"))
        if ts is None or not _in_rth(ts):
            continue
        beacon_price = (row.get("market") or {}).get("spy_last")
        hq = row.get("hq") or {}
        hq_live = hq.get("market_live")
        if not isinstance(hq_live, dict):
            # HQ payload predates this field, or /api/hq errored -- nothing
            # to check this sample (other rules already flag hq.error).
            continue
        hq_live_price = hq_live.get("spy")
        hq_live_age_s = hq_live.get("age_s")
        if isinstance(hq_live_age_s, (int, float)) and hq_live_age_s > HQ_STALE_S:
            mismatches.append({
                "rule": "b1_stale", "ts_et": row.get("ts_et"),
                "detail": f"HQ market.live is {hq_live_age_s:.0f}s stale (> {HQ_STALE_S}s)",
            })
        if isinstance(beacon_price, (int, float)) and isinstance(hq_live_price, (int, float)):
            diff = abs(beacon_price - hq_live_price)
            if diff > HQ_LIVE_PRICE_TOL:
                mismatches.append({
                    "rule": "b1_price_mismatch", "ts_et": row.get("ts_et"),
                    "detail": f"HQ market.live.spy={hq_live_price} vs beacon spy={beacon_price} "
                              f"(diff {diff:.3f} > {HQ_LIVE_PRICE_TOL})",
                })
    return mismatches


def check_hq_engine_bar_vs_ledger(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """(b2) HQ's per-account engineBarSpy must match the SAME
    core-decisions.jsonl row's own `spy` field EXACTLY -- both are supposed
    to be the identical decision-bar price read two different ways
    (dashboard/lib/hq.ts#readCoreDecisionsLatest vs this script's own
    read_engine()). Any real diff here means the dashboard's ledger read
    (tail window, parse, or field mapping) has drifted from the raw file --
    a genuine bug, unlike the expected engine-vs-live lag rule (b1) covers."""
    mismatches = []
    for row in rows:
        ts = _parse_ts_et(row.get("ts_et"))
        if ts is None or not _in_rth(ts):
            continue
        engine = row.get("engine") or {}
        per_acct = engine.get("per_account") or {}
        hq = row.get("hq") or {}
        hq_market = hq.get("market") or {}
        for hq_key, arm in (("safe", "safe-2"), ("bold", "bold-2")):
            hq_info = hq_market.get(hq_key)
            engine_info = per_acct.get(arm)
            if not isinstance(hq_info, dict) or not isinstance(engine_info, dict):
                continue
            engine_age_s = engine_info.get("age_s")
            if isinstance(engine_age_s, (int, float)) and engine_age_s > B2_LEDGER_STALE_S:
                continue  # sampling race at a tick boundary -- see B2_LEDGER_STALE_S docstring
            hq_bar = hq_info.get("engineBarSpy")
            ledger_bar = engine_info.get("spy")
            if isinstance(hq_bar, (int, float)) and isinstance(ledger_bar, (int, float)):
                diff = abs(hq_bar - ledger_bar)
                if diff > HQ_ENGINE_BAR_TOL:
                    mismatches.append({
                        "rule": "b2_engine_bar_mismatch", "ts_et": row.get("ts_et"), "arm": arm,
                        "detail": f"HQ {hq_key} engineBarSpy={hq_bar} vs ledger spy={ledger_bar} "
                                  f"(diff {diff})",
                    })
    return mismatches


def check_engine_tick_gap(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """(c) engine tick missing for > 3 min during RTH (09:31-15:55)."""
    mismatches = []
    prev_ts: Optional[datetime] = None
    for row in rows:
        ts = _parse_ts_et(row.get("ts_et"))
        if ts is None or not _in_rth(ts):
            continue
        last_tick_ts = _parse_ts_et((row.get("engine") or {}).get("last_tick_ts"))
        if last_tick_ts is not None:
            gap_s = (ts - last_tick_ts).total_seconds()
            if gap_s > ENGINE_TICK_GAP_S:
                mismatches.append({
                    "rule": "c_engine_tick_gap", "ts_et": row.get("ts_et"),
                    "detail": f"last engine tick {gap_s:.0f}s ago (> {ENGINE_TICK_GAP_S}s) during RTH",
                })
        prev_ts = ts
    return mismatches


def check_hq_activity_no_engine(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """(d) HQ showing trading activity while the engine shows none."""
    mismatches = []
    for row in rows:
        hq = row.get("hq") or {}
        hq_market = hq.get("market") or {}
        engine = row.get("engine") or {}
        per_acct = engine.get("per_account") or {}
        for hq_key, arm in (("safe", "safe-2"), ("bold", "bold-2")):
            info = hq_market.get(hq_key)
            if not isinstance(info, dict):
                continue
            hq_verdict = info.get("verdict")
            if not (isinstance(hq_verdict, str) and hq_verdict.upper() in ("ENTER", "EXIT")):
                continue
            engine_info = per_acct.get(arm) or {}
            engine_action = engine_info.get("action") if isinstance(engine_info, dict) else None
            if not (isinstance(engine_action, str) and engine_action.upper() in ("ENTER", "EXIT")):
                mismatches.append({
                    "rule": "d_hq_activity_no_engine", "ts_et": row.get("ts_et"), "arm": arm,
                    "detail": f"HQ shows {hq_key} verdict={hq_verdict} but engine action={engine_action}",
                })
    return mismatches


def check_position_hidden(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """(p1) HQ-POSITION-TRUTH (2026-09-15): the engine/broker holds an open
    position (this script's own read_positions() -- exit-state.json truth,
    status=="open") but /api/hq's `trading.position.<acct>.open` is empty --
    the exact bug this task was filed against (HQ showed ENTER_BEAR for two
    minutes then fell back to HOLD/flat while a real 3-lot put stayed open
    for hours). Independent of check_hq_activity_no_engine (rule d, which
    only ever compares HQ verdict vs the engine's per-tick action ledger,
    never the actual broker position)."""
    mismatches = []
    for row in rows:
        positions = row.get("positions") or {}
        hq = row.get("hq") or {}
        hq_market = hq.get("market") or {}
        for arm in ("safe-2", "bold-2"):
            pos_entry = positions.get(arm) or {}
            if pos_entry.get("status") != "open":
                continue
            hq_key = "safe" if arm == "safe-2" else "bold"
            hq_info = hq_market.get(hq_key)
            hq_position = hq_info.get("position") if isinstance(hq_info, dict) else None
            hq_open = hq_position.get("open") if isinstance(hq_position, dict) else None
            if not (isinstance(hq_open, list) and len(hq_open) > 0):
                mismatches.append({
                    "rule": "p1_position_hidden", "ts_et": row.get("ts_et"), "arm": arm,
                    "detail": f"{arm} exit-state shows OPEN ({pos_entry.get('symbol')} x{pos_entry.get('qty')}) "
                              f"but HQ trading.position.{hq_key}.open is empty",
                })
    return mismatches


def cmd_report(args: argparse.Namespace) -> int:
    now_et = et_now()
    date_str = args.date or now_et.strftime("%Y-%m-%d")
    if args.jsonl_path:
        jsonl_path = Path(args.jsonl_path)
    else:
        jsonl_path = out_path_for(datetime.strptime(date_str, "%Y-%m-%d"),
                                   Path(args.station_dir) if args.station_dir else STATION_DIR)

    rows = load_rows(jsonl_path)
    print(f"=== hq_market_correlate report: {jsonl_path} ({len(rows)} samples) ===")
    for row in rows[-20:]:
        engine = row.get("engine") or {}
        per_acct = engine.get("per_account") or {}
        safe_a = (per_acct.get("safe-2") or {}).get("action") if isinstance(per_acct.get("safe-2"), dict) else None
        bold_a = (per_acct.get("bold-2") or {}).get("action") if isinstance(per_acct.get("bold-2"), dict) else None
        print(f"  {row.get('ts_et')}  spy={((row.get('market') or {}).get('spy_last'))}"
              f"  safe={safe_a}  bold={bold_a}  hq_err={((row.get('hq') or {}).get('error'))}")

    mismatches = (
        check_action_not_reflected(rows)
        + check_hq_live_vs_beacon(rows)
        + check_hq_engine_bar_vs_ledger(rows)
        + check_engine_tick_gap(rows)
        + check_hq_activity_no_engine(rows)
        + check_position_hidden(rows)
    )
    print(f"\n=== MISMATCHES: {len(mismatches)} ===")
    by_rule: dict[str, int] = {}
    for m in mismatches:
        by_rule[m["rule"]] = by_rule.get(m["rule"], 0) + 1
        print(f"  [{m['rule']}] {m.get('ts_et')} {m.get('arm', '')} -- {m['detail']}")
    print(f"\ncounts by rule: {json.dumps(by_rule)}")
    return 0


# ----------------------------------------------------------------------------
# CLI
# ----------------------------------------------------------------------------

def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("mode", nargs="?", default="sample", choices=["sample", "report"])
    parser.add_argument("--station-dir", default=None, help="override automation/state/station (tests)")
    parser.add_argument("--beacon-path", default=None, help="override sight-beacon.json path (tests)")
    parser.add_argument("--ledger-path", default=None, help="override core-decisions.jsonl path (tests)")
    parser.add_argument("--out", default=None, help="override the row's output jsonl path (sample mode)")
    parser.add_argument("--jsonl-path", default=None, help="override the input jsonl path (report mode)")
    parser.add_argument("--date", default=None, help="ET date YYYY-MM-DD (report mode; default today)")
    parser.add_argument("--hq-url", default=HQ_URL, help="override /api/hq URL")
    args = parser.parse_args(argv)

    if args.mode == "sample":
        return cmd_sample(args)
    return cmd_report(args)


if __name__ == "__main__":
    sys.exit(main())

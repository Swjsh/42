"""participation_cascade.py -- the JOINT GATE CASCADE instrument (C15).

WHY (J, 2026-07-10, a $0 day on a $7 SPY trend): "6 arms and nothing took a
trade from over 700 signals? why didn't you see this yesterday?" Every gate in
this rig is validated in isolation (block_elite_bull, block_bull_1100_1200,
structure-veto, the risk gate's premium floor, an arm's own A+ selectivity
gate...) but nothing traced the JOINT funnel -- a setup that survives gate A
can still die at gate B, C, or D, and nobody summed that across all 6 arms
until now. C15 ("gates interact multiplicatively") is doctrine; this is the
instrument that enforces it.

Reconstructs the funnel from the ACTUAL LOGGED FIELDS -- this never re-runs
the engine, it reads what the engine already wrote:
  automation/state/core-decisions.jsonl (+ core-decisions*.jsonl archives if
      the ledger ever rotates) -- CORE: safe-2 + bold-2 CONTROL, split by the
      row's 'account' field ('safe' | 'bold').
  automation/state/fleet/<arm>/decisions.jsonl -- the 4 fleet_rest arms
      (safe-1, safe-3, risky-1, risky-3).
6 arms total, matching automation/state/fleet/accounts.json's 'arms' list:
safe-1/2/3, risky-1/3, bold-2. safe-2/bold-2 are the CONTROL cells, executed
by the live heartbeat (mcp_heartbeat) and therefore logged into
core-decisions.jsonl rather than their own fleet/<arm>/decisions.jsonl.

SIGNAL EVENT dedup rule (deterministic, stated once, used everywhere below):
within one arm's row stream (time-sorted), consecutive rows collapse into ONE
event while they share the same terminal identity: (side, setup, stage,
blocker). A tick that still HOLDs with no candidate (side=setup=None) also
collapses with its neighbors under this rule -- so a long boring stretch is
one NO_SIGNAL event, a condition that persists for 5 ticks in a row is one
event, and a setup that clears, drops out, and re-fires later is reported as
TWO events (the identity run breaks the moment a HOLD row sits between them).
This deliberately UNDER-counts rather than tick-inflates -- see
test_participation_cascade.py::test_dedup_collapses_consecutive_identical_ticks.

STAGE FUNNEL per event (terminal -- each event ends at exactly one stage):
  NO_DATA         bad/stale input, feed errors -- pre-scoring failure
  NO_SIGNAL       scored, nothing crossed threshold (the modal outcome)
  STRUCTURE_VETO  core structure-veto blocked a would-be entry
  GATE_BLOCK      a NAMED entry-selectivity gate blocked it (block_elite_bull,
                  an arm's own A+ gate_override, block_level_rejection, ...)
  WINDOW_BLOCK    a TIME-WINDOW gate blocked it (block_bull_1100_1200,
                  block_conf_lvl_rec_afternoon, the 09:35 entry floor, the
                  15:00 entry ceiling)
  STALE_TRIGGER   the trigger bar was not from today's session
  RISK_GATE_DENY  the risk gate refused (PDT, NOT_FLAT/Rule-4, min-premium
                  floor, quality-lock)
  PLACE_FAIL      attempted, broker rejected / no response recorded
  PLACED          order sent, no same-day fill evidence yet
  FILLED          broker-truth fill evidence in the same day's ledger
  OTHER_BLOCK     an unrecognized code -- fail-open bucket so a genuinely NEW
                  block type is never silently dropped (OP-33)

Every event also carries a `tier` (SUPER/ELITE/TRENDLINE for core,
ELITE/BASE for fleet) when the underlying setup reached that stage -- this is
what lets the blocker leaderboard say "block_elite_bull killed N SUPER-tier
signals" instead of just "N signals died somewhere".

Named CORE gates are classified GATE vs WINDOW using heartbeat_core.py's own
GATE_KEYS list (setup/scripts/heartbeat_core.py) -- window-shaped names
(morning/afternoon/midday/an explicit hour range) go in _CORE_WINDOW_GATES;
everything else (including block_elite_bull and block_bull_ribbon_flip -- the
tier/cohort gates) is a plain GATE_BLOCK.

OUTPUT: automation/state/participation-cascade.json -- the standing glanceable
state file: {date, events, joint_participation_pct, top_blockers, verdict,
sessions (the N-day trend)}. verdict=PARTICIPATION_HOLE fires when a REAL,
tradeable-range day produced passed_scoring events with ZERO joint
participation (see `evaluate_day` for the exact predicate). This is a standing
instrument, not yet wired into engine_health/self_check -- suggested one-line
hookup (mirrors self_check.py's existing check_fill_funnel):

    def check_participation_cascade(now):
        import participation_cascade as pc
        f = pc.compute_cascade_day(now.strftime("%Y-%m-%d"), now=now)
        return [f"PARTICIPATION-HOLE {f['blocker_summary']}"] if f["verdict"] == "PARTICIPATION_HOLE" else []

CLI:  backtest/.venv/Scripts/python.exe backtest/tools/participation_cascade.py
      [--date YYYY-MM-DD] [--sessions N] [--write] [--markdown] [--report PATH]
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
DATA = REPO / "backtest" / "data"
sys.path.insert(0, str(REPO / "setup" / "scripts"))

try:
    from et_clock import et_now
except Exception:  # noqa: BLE001  -- fail-open (rig is on Mountain; never Bash TZ)
    def et_now() -> dt.datetime:
        return dt.datetime.utcnow() - dt.timedelta(hours=4)

# ---------------------------------------------------------------------------
# arms + sources
# ---------------------------------------------------------------------------
FLEET_ARM_IDS = ("safe-1", "safe-3", "risky-1", "risky-3")
CORE_ARM_LABEL = {"safe": "safe-2", "bold": "bold-2"}   # account -> arm_id (accounts.json CONTROL cells)
ALL_ARMS = ("bold-2", "risky-1", "risky-3", "safe-1", "safe-2", "safe-3")  # alphabetical, deterministic

# ---------------------------------------------------------------------------
# stage / category taxonomy
# ---------------------------------------------------------------------------
CAT_NONE = "none"          # NO_DATA / NO_SIGNAL -- nothing to attribute a block to
CAT_GATE = "gate"          # named entry-selectivity gate (tier/quality/cohort)
CAT_WINDOW = "window"      # time-of-day / session-window gate
CAT_VETO = "veto"          # structure-veto
CAT_RISK = "risk_gate"     # PDT / NOT_FLAT (Rule 4) / premium floor / quality-lock
CAT_EXEC = "execution"     # stale-trigger / broker place-fail
CAT_SUCCESS = "success"    # placed / filled

_TERMINAL_STAGES = (
    "NO_DATA", "NO_SIGNAL", "STRUCTURE_VETO", "GATE_BLOCK", "WINDOW_BLOCK",
    "STALE_TRIGGER", "RISK_GATE_DENY", "PLACE_FAIL", "PLACED", "FILLED", "OTHER_BLOCK",
)
_NON_SCORING_STAGES = ("NO_DATA", "NO_SIGNAL")  # excluded from "passed_scoring"

# heartbeat_core.py GATE_KEYS -- window-shaped names (time-of-day / session windows).
# Everything else in GATE_KEYS (block_elite_bull, block_bull_ribbon_flip,
# block_level_rejection, require_bearish_fill_bar, min_ribbon_momentum_cents,
# entry_bar_body_pct_min[_bull], trendline_requires_ribbon_flip,
# max_ribbon_duration_bars, vix_bear_hard_cap) is a plain GATE_BLOCK.
_CORE_WINDOW_GATES = frozenset({
    "block_bull_1100_1200", "block_conf_lvl_rec_afternoon",
    "block_conf_lvl_rej_midday_afternoon", "block_bull_morning_agg",
    "midday_trendline_gate",
})
# J's "tier/cohort" language (WHY section) -- the two gates that block by
# assigned quality-tier or by ribbon_flip-cohort membership, not by time.
TIER_COHORT_GATES = frozenset({"block_elite_bull", "block_bull_ribbon_flip"})

_SPY_RANGE_PCT_THRESHOLD = 0.8  # task spec: "a day whose SPY range >= 0.8%"
_MIN_PASSED_SCORING_FOR_HOLE = 3


def _stage(side, setup, tier, stage, category, blocker, detail) -> dict:
    """Build one classification result. Pure -- never mutates its caller's dict."""
    return {"side": side, "setup": setup, "tier": tier, "stage": stage,
            "category": category, "blocker": blocker, "detail": str(detail or "")}


# ---------------------------------------------------------------------------
# ledger readers (fail-open -- a missing/corrupt file yields [], never a crash)
# ---------------------------------------------------------------------------

def _iter_jsonl(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            o = json.loads(ln)
        except (ValueError, json.JSONDecodeError):
            continue
        if isinstance(o, dict):
            yield o


def _read_core_rows(day: str, core_glob_dir: Path) -> list[dict]:
    """core-decisions.jsonl + any core-decisions*.jsonl rotation archives,
    deduped by (ts_et, account) in case a rotation ever overlaps."""
    seen: set[tuple] = set()
    out: list[dict] = []
    try:
        paths = sorted(core_glob_dir.glob("core-decisions*.jsonl"))
    except OSError:
        paths = []
    for p in paths:
        for row in _iter_jsonl(p):
            ts = str(row.get("ts_et") or "")
            if not ts.startswith(day):
                continue
            key = (ts, row.get("account"))
            if key in seen:
                continue
            seen.add(key)
            out.append(row)
    return out


def _read_fleet_rows(day: str, arm: str, fleet_dir: Path) -> list[dict]:
    p = fleet_dir / arm / "decisions.jsonl"
    return [r for r in _iter_jsonl(p) if str(r.get("ts_et") or "").startswith(day)]


def discover_sessions(n: int, *, core_glob_dir: Path | None = None,
                      fleet_dir: Path | None = None) -> list[str]:
    """Every ET calendar date that appears in ANY source, ascending, last N."""
    core_glob_dir = core_glob_dir or STATE
    fleet_dir = fleet_dir or (STATE / "fleet")
    days: set[str] = set()
    try:
        paths = sorted(core_glob_dir.glob("core-decisions*.jsonl"))
    except OSError:
        paths = []
    for p in paths:
        for row in _iter_jsonl(p):
            ts = str(row.get("ts_et") or "")
            if len(ts) >= 10:
                days.add(ts[:10])
    for arm in FLEET_ARM_IDS:
        for row in _iter_jsonl(fleet_dir / arm / "decisions.jsonl"):
            ts = str(row.get("ts_et") or "")
            if len(ts) >= 10:
                days.add(ts[:10])
    return sorted(days)[-n:] if n else sorted(days)


# ---------------------------------------------------------------------------
# row classification -- CORE
# ---------------------------------------------------------------------------

def _core_broker_filled(exec_: dict) -> bool:
    broker = (exec_ or {}).get("broker") or {}
    try:
        if float(broker.get("filled_qty") or 0) > 0:
            return True
    except (TypeError, ValueError):
        pass
    return bool(broker.get("filled_at"))


def _classify_action_code(side, setup, tier, code: str) -> dict:
    """Shared downstream-code classifier for the post-tier action/placement
    layer. Fail-open: any code we don't recognize still lands in OTHER_BLOCK
    (counted + visible) instead of being silently dropped."""
    c = (code or "").upper()
    if c == "SKIP_LATE_ENTRY":
        return _stage(side, setup, tier, "WINDOW_BLOCK", CAT_WINDOW, "entry_ceiling_15:00", code)
    if c == "SKIP_EARLY_ENTRY":
        return _stage(side, setup, tier, "WINDOW_BLOCK", CAT_WINDOW, "entry_floor_09:35", code)
    if c == "SKIP_STALE_TRIGGER":
        return _stage(side, setup, tier, "STALE_TRIGGER", CAT_EXEC, "stale_trigger_bar", code)
    if c == "SKIP_MIN_PREMIUM_FLOOR":
        return _stage(side, setup, tier, "RISK_GATE_DENY", CAT_RISK, "min_premium_floor", code)
    if c == "SKIP_QUALITY_LOCK":
        return _stage(side, setup, tier, "RISK_GATE_DENY", CAT_RISK, "quality_lock", code)
    if c in ("NOT_FLAT",) or "position already open" in c.lower():
        return _stage(side, setup, tier, "RISK_GATE_DENY", CAT_RISK, "not_flat_rule4", code)
    if c.startswith("RISK_DENY"):
        return _stage(side, setup, tier, "RISK_GATE_DENY", CAT_RISK, c.lower(), code)
    if c == "PLACE_FAIL":
        return _stage(side, setup, tier, "PLACE_FAIL", CAT_EXEC, "broker_reject", code)
    if c == "PLACED":
        return _stage(side, setup, tier, "PLACED", CAT_SUCCESS, None, code)
    if c.startswith("SKIP_") or c.startswith("A+ GATE"):
        return _stage(side, setup, tier, "OTHER_BLOCK", CAT_GATE, c.lower(), code)
    return _stage(side, setup, tier, "OTHER_BLOCK", CAT_GATE, c.lower() or "unknown", code)


def classify_core_row(row: dict) -> dict:
    """Terminal classification for one automation/state/core-decisions.jsonl row."""
    verdict = str(row.get("verdict") or "")
    reason = str(row.get("reason") or "")
    side = row.get("side")
    setup = row.get("setup")

    if verdict in ("ERROR", "SKIP_BAD_INPUT") or row.get("error"):
        return _stage(None, None, None, "NO_DATA", CAT_NONE, "engine_error",
                      row.get("error") or reason or verdict)

    if not reason or reason == "no setup passed scoring (neither bear nor bull)":
        return _stage(None, None, None, "NO_SIGNAL", CAT_NONE, None, reason or "HOLD")

    if reason.startswith("structure-veto:"):
        return _stage(side, setup, None, "STRUCTURE_VETO", CAT_VETO, "structure_veto", reason)

    if reason.startswith("blocked by entry gate "):
        name = reason.split("blocked by entry gate ", 1)[1].strip()
        cat = CAT_WINDOW if name in _CORE_WINDOW_GATES else CAT_GATE
        stage_name = "WINDOW_BLOCK" if cat == CAT_WINDOW else "GATE_BLOCK"
        return _stage(side, setup, None, stage_name, cat, name, reason)

    tier = None
    m = re.search(r"\(tier (\w+)\)", reason)
    if m:
        tier = m.group(1)

    if not verdict.startswith("ENTER"):
        # a named SKIP_*/other verdict not covered by the two branches above --
        # fail-open bucket so a new gate signature is never silently dropped.
        return _stage(side, setup, tier, "OTHER_BLOCK", CAT_GATE, verdict.lower() or "unknown", reason)

    # verdict IS an ENTER_* (passed scoring + all named entry gates + tier
    # assigned). `action` carries the post-tier outcome; when unchanged from
    # `verdict`, `exec` (if present) carries the final broker-layer word.
    action = str(row.get("action") or verdict)
    exec_ = row.get("exec") or {}
    if action == verdict:
        st = str(exec_.get("status") or "")
        if not exec_:
            # ENTER verdict, no exec detail recorded at all -- ambiguous but
            # never silently dropped: treat as an unconfirmed placement attempt.
            return _stage(side, setup, tier, "PLACED", CAT_SUCCESS, None, "ENTER (no exec detail logged)")
        if st == "PLACED" or _core_broker_filled(exec_):
            stage = "FILLED" if _core_broker_filled(exec_) else "PLACED"
            return _stage(side, setup, tier, stage, CAT_SUCCESS, None, st or "PLACED")
        return _classify_action_code(side, setup, tier, st or action)
    return _classify_action_code(side, setup, tier, action)


# ---------------------------------------------------------------------------
# row classification -- FLEET
# ---------------------------------------------------------------------------

def _classify_risk_code(side, setup, tier, risk_code, reason: str) -> dict:
    rc = (risk_code or "").upper()
    rl = reason.lower()
    if rc == "NOT_FLAT" or "position already open" in rl:
        return _stage(side, setup, tier, "RISK_GATE_DENY", CAT_RISK, "not_flat_rule4", reason or rc)
    if rc == "SKIP_MIN_PREMIUM_FLOOR" or "min_entry_premium floor" in rl:
        return _stage(side, setup, tier, "RISK_GATE_DENY", CAT_RISK, "min_premium_floor", reason or rc)
    if rc == "UNREADABLE_INPUT":
        return _stage(side, setup, tier, "NO_DATA", CAT_NONE, "unreadable_input", reason or rc)
    if "pdt" in rl or rc == "PDT":
        return _stage(side, setup, tier, "RISK_GATE_DENY", CAT_RISK, "pdt", reason or rc)
    return _stage(side, setup, tier, "RISK_GATE_DENY", CAT_RISK, rc.lower() or "risk_gate_deny", reason or rc)


def classify_fleet_row(row: dict) -> dict:
    """Terminal classification for one automation/state/fleet/<arm>/decisions.jsonl row."""
    action = str(row.get("action") or "HOLD")
    side = row.get("side")
    setup = row.get("setup_name")
    tier = row.get("quality")  # fleet's tier vocabulary: ELITE / BASE
    risk_code = row.get("risk_code")
    reason = str(row.get("reason") or "")
    signal_status = str(row.get("signal_status") or "ok")
    placement = row.get("placement") or {}

    if signal_status != "ok" or reason == "no live signal":
        return _stage(None, None, None, "NO_DATA", CAT_NONE, "signal_feed", signal_status or reason)

    if action == "HOLD" and not setup:
        return _stage(None, None, None, "NO_SIGNAL", CAT_NONE, None, reason or "HOLD")

    if action == "HOLD" and setup and not risk_code:
        # a candidate fired but was blocked BEFORE the risk gate: the arm's own
        # selectivity gate_override (min_triggers / confluence / quality) or a
        # direction lock (fleet_executor.py plan_entry / _gate_check).
        name = "direction_lock" if reason.startswith("direction_lock=") else "arm_selectivity_gate"
        return _stage(side, setup, tier, "GATE_BLOCK", CAT_GATE, name, reason)

    if action == "HOLD" and setup and risk_code:
        return _classify_risk_code(side, setup, tier, risk_code, reason)

    if action.startswith("ENTER"):
        if risk_code and risk_code != "ALLOW":
            return _classify_risk_code(side, setup, tier, risk_code, reason)
        if placement.get("placed"):
            return _stage(side, setup, tier, "PLACED", CAT_SUCCESS, None, reason)
        p_reason = str(placement.get("reason") or "")
        if p_reason == "SKIP_EARLY_ENTRY":
            return _stage(side, setup, tier, "WINDOW_BLOCK", CAT_WINDOW, "entry_floor_09:35", p_reason)
        if p_reason == "SKIP_LATE_ENTRY":
            return _stage(side, setup, tier, "WINDOW_BLOCK", CAT_WINDOW, "entry_ceiling_15:00", p_reason)
        if p_reason.startswith("risk_gate denied"):
            return _classify_risk_code(side, setup, tier, "RISK_GATE", p_reason)
        # placement.reason is the authoritative field here (NOT a synthesized
        # "no broker response recorded" default -- see module docstring: fleet
        # PLACE_FAIL rows carry their real reason directly in `placement.reason`).
        return _stage(side, setup, tier, "PLACE_FAIL", CAT_EXEC, "broker_reject",
                      p_reason or "no placement reason recorded")

    return _stage(side, setup, tier, "OTHER_BLOCK", CAT_GATE, action.lower() or "unknown", reason)


# ---------------------------------------------------------------------------
# fill-evidence promotion (PLACED -> FILLED) -- same-day exit_pass, both kinds
# ---------------------------------------------------------------------------

def _row_symbol(row: dict, kind: str) -> Optional[str]:
    if kind == "core":
        exec_ = row.get("exec") or {}
        return exec_.get("symbol") or (exec_.get("broker") or {}).get("symbol")
    placement = row.get("placement") or {}
    return placement.get("symbol")


def _filled_symbols(rows: list[dict]) -> set[str]:
    """Symbols with broker-truth open-position evidence anywhere in the day's
    exit_pass rows (mirrors setup/scripts/fill_funnel.py's proven signal)."""
    out: set[str] = set()
    for row in rows:
        for ep in (row.get("exit_pass") or []):
            sym = ep.get("symbol")
            if not sym:
                continue
            try:
                if float(ep.get("open_qty") or 0) > 0:
                    out.add(sym)
            except (TypeError, ValueError):
                pass
    return out


# ---------------------------------------------------------------------------
# per-arm event construction (the dedup rule, applied uniformly)
# ---------------------------------------------------------------------------

def build_events(rows: list[dict], arm: str, kind: str) -> list[dict]:
    """Time-sort + classify + run-length-encode into events. See module
    docstring "SIGNAL EVENT dedup rule" for the exact collapse condition."""
    rows_sorted = sorted(rows, key=lambda r: str(r.get("ts_et") or ""))
    classify = classify_core_row if kind == "core" else classify_fleet_row
    filled_syms = _filled_symbols(rows_sorted)

    events: list[dict] = []
    cur: Optional[dict] = None
    for row in rows_sorted:
        c = classify(row)
        if c["stage"] == "PLACED":
            sym = _row_symbol(row, kind)
            if sym and sym in filled_syms:
                c = {**c, "stage": "FILLED"}
        ts = str(row.get("ts_et") or "")
        identity = (c["side"], c["setup"], c["stage"], c["blocker"])
        if cur is not None and cur["identity"] == identity:
            cur["ts_end"] = ts
            cur["n_ticks"] += 1
        else:
            if cur is not None:
                events.append(cur)
            cur = {"arm": arm, "ts_start": ts, "ts_end": ts, "n_ticks": 1,
                   "identity": identity, **c}
    if cur is not None:
        events.append(cur)
    return events


# ---------------------------------------------------------------------------
# SPY session range (real 5m OHLC bars -- NOT the sparse tick-sampled 'spy'
# field, which misses intrabar wicks and understates range; verified against
# J's own "$7 trend" recollection: the bar CSV gives 07-10 = $7.32 / 0.973%,
# the tick-sampled field gives only $4.28 / 0.570% -- material difference)
# ---------------------------------------------------------------------------

_SPY_CSV_RE = re.compile(r"^spy_5m_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.csv$")


def _find_spy_csv(day: str, data_dir: Path) -> Optional[Path]:
    """Among spy_5m_<start>_<end>.csv files that bracket `day`, prefer the
    smallest `end` (freshest-scoped) and, tied on that, the largest `start`
    (tightest/smallest file to read). Plain two-pass min/max -- no cleverness."""
    try:
        cands = list(data_dir.glob("spy_5m_*.csv"))
    except OSError:
        return None
    bracketing: list[tuple[str, str, Path]] = []
    for p in cands:
        m = _SPY_CSV_RE.match(p.name)
        if not m:
            continue
        start, end = m.group(1), m.group(2)
        if start <= day <= end:
            bracketing.append((start, end, p))
    if not bracketing:
        return None
    min_end = min(end for _, end, _ in bracketing)
    tightest = [(start, end, p) for start, end, p in bracketing if end == min_end]
    tightest.sort(key=lambda t: t[0], reverse=True)  # largest start first
    return tightest[0][2]


def spy_session_range_pct(day: str, *, data_dir: Path | None = None) -> Optional[float]:
    """(session high - session low) / session open * 100 over RTH 5m bars
    (09:30-15:55 ET bar-open times). None if no bar cache covers this day
    (fail-open -- never crashes, never fabricates a number)."""
    data_dir = data_dir or DATA
    p = _find_spy_csv(day, data_dir)
    if p is None:
        return None
    try:
        with open(p, encoding="utf-8", newline="") as fh:
            rows = [r for r in csv.DictReader(fh)]
    except OSError:
        return None
    bars = [r for r in rows if str(r.get("timestamp_et", "")).startswith(day)
            and "09:30" <= str(r["timestamp_et"])[11:16] <= "15:55"]
    if not bars:
        return None
    try:
        highs = [float(r["high"]) for r in bars]
        lows = [float(r["low"]) for r in bars]
        open_px = float(bars[0]["open"])
    except (KeyError, TypeError, ValueError):
        return None
    if open_px <= 0:
        return None
    return (max(highs) - min(lows)) / open_px * 100.0


# ---------------------------------------------------------------------------
# per-day cascade
# ---------------------------------------------------------------------------

def compute_cascade_day(day: str, *, core_glob_dir: Path | None = None,
                        fleet_dir: Path | None = None, data_dir: Path | None = None) -> dict:
    """Full joint cascade for one ET session day. Fail-open throughout."""
    core_glob_dir = core_glob_dir or STATE
    fleet_dir = fleet_dir or (STATE / "fleet")
    data_dir = data_dir or DATA

    core_rows = _read_core_rows(day, core_glob_dir)
    events_by_arm: dict[str, list[dict]] = {}
    for account, arm in CORE_ARM_LABEL.items():
        rows = [r for r in core_rows if str(r.get("account") or "") == account]
        events_by_arm[arm] = build_events(rows, arm, "core")
    for arm in FLEET_ARM_IDS:
        rows = _read_fleet_rows(day, arm, fleet_dir)
        events_by_arm[arm] = build_events(rows, arm, "fleet")

    per_arm_funnel = {}
    for arm in ALL_ARMS:
        events = events_by_arm.get(arm, [])
        counts = Counter(e["stage"] for e in events)
        passed = [e for e in events if e["stage"] not in _NON_SCORING_STAGES]
        orders = [e for e in events if e["stage"] in ("PLACED", "FILLED")]
        per_arm_funnel[arm] = {
            "events": len(events),
            "passed_scoring": len(passed),
            "by_stage": {s: counts.get(s, 0) for s in _TERMINAL_STAGES if counts.get(s, 0)},
            "orders": len(orders),
        }

    all_events = [e for evs in events_by_arm.values() for e in evs]
    passed_scoring_events = [e for e in all_events if e["stage"] not in _NON_SCORING_STAGES]
    order_events = [e for e in all_events if e["stage"] in ("PLACED", "FILLED")]
    n_passed = len(passed_scoring_events)
    n_orders = len(order_events)
    joint_pct = (100.0 * n_orders / n_passed) if n_passed else None

    blocker_events = [e for e in passed_scoring_events if e["stage"] not in ("PLACED", "FILLED")]
    leaderboard = Counter((e["category"], e["blocker"] or e["stage"]) for e in blocker_events)
    top_blockers = [
        {"blocker": name, "category": cat, "n_arm_events": n,
         "tier_cohort_gate": name in TIER_COHORT_GATES,
         "tiers": sorted({e["tier"] for e in blocker_events
                          if (e["category"], e["blocker"] or e["stage"]) == (cat, name) and e["tier"]})}
        for (cat, name), n in leaderboard.most_common()
    ]

    range_pct = spy_session_range_pct(day, data_dir=data_dir)
    verdict, flags = evaluate_day(n_passed, n_orders, range_pct)

    return {
        "date": day,
        "per_arm_funnel": per_arm_funnel,
        "n_passed_scoring_events": n_passed,
        "n_orders": n_orders,
        "joint_participation_pct": None if joint_pct is None else round(joint_pct, 1),
        "spy_range_pct": None if range_pct is None else round(range_pct, 3),
        "top_blockers": top_blockers,
        "verdict": verdict,
        "flags": flags,
        "events": all_events,  # full detail (dropped from the compact state-file view)
    }


def evaluate_day(n_passed: int, n_orders: int, range_pct: Optional[float]) -> tuple[str, list[str]]:
    """verdict=PARTICIPATION_HOLE iff >=3 passed_scoring events, ZERO joint
    participation, on a session whose real SPY range cleared 0.8%. If the
    range can't be confirmed (no bar cache for that day), the hole is still
    fully visible as LOW_PARTICIPATION_RANGE_UNKNOWN -- never silently
    dropped just because one input was missing (OP-33)."""
    flags: list[str] = []
    if n_passed == 0:
        return "IDLE", flags
    if n_orders > 0:
        return "OK", flags
    # n_orders == 0, n_passed > 0
    if n_passed < _MIN_PASSED_SCORING_FOR_HOLE:
        flags.append(f"{n_passed} passed_scoring event(s), below the {_MIN_PASSED_SCORING_FOR_HOLE}-event "
                      f"PARTICIPATION_HOLE floor -- flagged LOW_PARTICIPATION, not the headline alert.")
        return "LOW_PARTICIPATION", flags
    if range_pct is None:
        flags.append("SPY range could not be confirmed (no spy_5m_*.csv bar cache covers this day) -- "
                      "PARTICIPATION_HOLE suppressed pending range confirmation.")
        return "LOW_PARTICIPATION_RANGE_UNKNOWN", flags
    if range_pct >= _SPY_RANGE_PCT_THRESHOLD:
        flags.append(f"{n_passed} passed_scoring events, 0 orders, SPY range {range_pct:.3f}% "
                      f">= {_SPY_RANGE_PCT_THRESHOLD}% floor -- a tradeable day, nobody traded.")
        return "PARTICIPATION_HOLE", flags
    flags.append(f"{n_passed} passed_scoring events, 0 orders, but SPY range {range_pct:.3f}% "
                  f"< {_SPY_RANGE_PCT_THRESHOLD}% floor -- chop day, not flagged as a hole.")
    return "LOW_PARTICIPATION", flags


# ---------------------------------------------------------------------------
# multi-session orchestration
# ---------------------------------------------------------------------------

def compute_cascade_sessions(n: int = 10, *, core_glob_dir: Path | None = None,
                             fleet_dir: Path | None = None, data_dir: Path | None = None) -> list[dict]:
    core_glob_dir = core_glob_dir or STATE
    fleet_dir = fleet_dir or (STATE / "fleet")
    data_dir = data_dir or DATA
    days = discover_sessions(n, core_glob_dir=core_glob_dir, fleet_dir=fleet_dir)
    return [compute_cascade_day(d, core_glob_dir=core_glob_dir, fleet_dir=fleet_dir, data_dir=data_dir)
            for d in days]


# ---------------------------------------------------------------------------
# renderers
# ---------------------------------------------------------------------------

_STAGE_ABBR = {
    "NO_DATA": "dat", "NO_SIGNAL": "sig", "STRUCTURE_VETO": "vet", "GATE_BLOCK": "gat",
    "WINDOW_BLOCK": "win", "STALE_TRIGGER": "stl", "RISK_GATE_DENY": "rsk",
    "PLACE_FAIL": "pfl", "PLACED": "pcd", "FILLED": "fil", "OTHER_BLOCK": "otr",
}


def render_day_text(f: dict) -> str:
    jp = f["joint_participation_pct"]
    rp = f["spy_range_pct"]
    jp_str = "n/a" if jp is None else f"{jp:.1f}%"
    rp_str = "n/a" if rp is None else f"{rp:.3f}%"
    out = [f"CASCADE {f['date']}  [{f['verdict']}]  passed_scoring={f['n_passed_scoring_events']} "
           f"orders={f['n_orders']} joint_participation={jp_str} spy_range={rp_str}"]
    header = "  {:<10}{:>4} {:>4}  ".format("arm", "evt", "pass") + " ".join(
        f"{_STAGE_ABBR[s]:>4}" for s in _TERMINAL_STAGES)
    out.append(header)
    for arm in ALL_ARMS:
        a = f["per_arm_funnel"].get(arm, {"events": 0, "passed_scoring": 0, "by_stage": {}, "orders": 0})
        row = "  {:<10}{:>4} {:>4}  ".format(arm, a["events"], a["passed_scoring"]) + " ".join(
            f"{a['by_stage'].get(s, 0):>4}" for s in _TERMINAL_STAGES)
        out.append(row)
    if f["top_blockers"]:
        out.append("  blockers (passed-scoring events killed, ranked):")
        for b in f["top_blockers"]:
            tiers = f" tiers={','.join(b['tiers'])}" if b["tiers"] else ""
            mark = " [TIER/COHORT GATE]" if b.get("tier_cohort_gate") else ""
            out.append(f"    {b['n_arm_events']:>3}x [{b['category']:<9}] {b['blocker']}{tiers}{mark}")
    for fl in f["flags"]:
        out.append(f"  ! {fl}")
    return "\n".join(out)


def render_report_markdown(sessions: list[dict], *, spotlight: tuple[str, ...] = ()) -> str:
    out = ["# Participation Cascade -- joint gate coverage (C15)", "",
           f"Generated from `core-decisions.jsonl` + `fleet/<arm>/decisions.jsonl` "
           f"across {len(sessions)} session(s): {sessions[0]['date'] if sessions else '?'} .. "
           f"{sessions[-1]['date'] if sessions else '?'}.", "",
           "## Joint-participation trend (one number per day)", "",
           "| date | passed_scoring | orders | joint participation | spy range | verdict |",
           "|---|---|---|---|---|---|"]
    for f in sessions:
        jp = "n/a" if f["joint_participation_pct"] is None else f"{f['joint_participation_pct']:.1f}%"
        rp = "n/a" if f["spy_range_pct"] is None else f"{f['spy_range_pct']:.3f}%"
        out.append(f"| {f['date']} | {f['n_passed_scoring_events']} | {f['n_orders']} | {jp} | {rp} | "
                   f"**{f['verdict']}** |")
    out.append("")
    for f in sessions:
        if spotlight and f["date"] not in spotlight:
            continue
        out.append(f"## {f['date']}  --  {f['verdict']}")
        out.append("")
        out.append("```")
        out.append(render_day_text(f))
        out.append("```")
        out.append("")
    out.append("## Stage legend")
    out.append("")
    out.append(", ".join(f"`{abbr}`={name}" for name, abbr in _STAGE_ABBR.items()))
    out.append("")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# artifact writers
# ---------------------------------------------------------------------------

def _compact_for_state(f: dict) -> dict:
    """Drop the full per-tick `events` list from the persisted state file --
    the per_arm_funnel + top_blockers already carry everything a glance needs;
    the full detail stays in the markdown report / re-runnable from ledgers."""
    return {k: v for k, v in f.items() if k != "events"}


def write_state_file(sessions: list[dict], *, state_dir: Path | None = None) -> Optional[Path]:
    """automation/state/participation-cascade.json -- the standing instrument.
    `date`/`verdict`/`top_blockers`/`joint_participation_pct` describe the
    LATEST session; `sessions` carries the full N-day trend. Fail-open."""
    if not sessions:
        return None
    state_dir = state_dir or STATE
    latest = sessions[-1]
    payload = {
        **_compact_for_state(latest),
        "generated_at_et": et_now().strftime("%Y-%m-%dT%H:%M:%S"),
        "sessions": [{"date": f["date"], "n_passed_scoring_events": f["n_passed_scoring_events"],
                      "n_orders": f["n_orders"], "joint_participation_pct": f["joint_participation_pct"],
                      "spy_range_pct": f["spy_range_pct"], "verdict": f["verdict"]} for f in sessions],
        "sources": {"core": str(STATE / "core-decisions.jsonl"), "fleet": str(STATE / "fleet")},
    }
    p = state_dir / "participation-cascade.json"
    try:
        p.write_text(json.dumps(payload, indent=1), encoding="utf-8")
        return p
    except OSError:
        return None


def write_report(sessions: list[dict], *, report_path: Path | None = None,
                 spotlight: tuple[str, ...] = ()) -> Optional[Path]:
    if not sessions:
        return None
    report_path = report_path or (REPO / "analysis" / "participation-cascade" / f"{sessions[-1]['date']}.md")
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(render_report_markdown(sessions, spotlight=spotlight), encoding="utf-8")
        return report_path
    except OSError:
        return None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # some reason
    except (AttributeError, ValueError):                            # strings carry
        pass                                                        # mojibake em-dashes

    ap = argparse.ArgumentParser(description="Joint gate-cascade funnel across all 6 arms (C15)")
    ap.add_argument("--date", default=None, help="ET date YYYY-MM-DD (default: latest session)")
    ap.add_argument("--sessions", type=int, default=10, help="how many trailing sessions (default 10)")
    ap.add_argument("--write", action="store_true",
                    help="write automation/state/participation-cascade.json")
    ap.add_argument("--report", action="store_true",
                    help="write the analysis/participation-cascade/{date}.md report")
    ap.add_argument("--markdown", action="store_true", help="print the markdown report instead of text")
    args = ap.parse_args()

    if args.date:
        all_days = discover_sessions(0)  # 0 = no truncation, search the full ledger history
        days = [d for d in all_days if d <= args.date]
        if not days or days[-1] != args.date:
            days.append(args.date)  # target date has no ledger rows yet -- still analyze it (-> IDLE)
        days = days[-args.sessions:]
        sessions = [compute_cascade_day(d) for d in days]
    else:
        sessions = compute_cascade_sessions(args.sessions)

    if not sessions:
        print("[participation-cascade] no sessions found in core-decisions.jsonl / fleet ledgers.")
        return 0

    spotlight = (sessions[-1]["date"],)
    if args.markdown:
        print(render_report_markdown(sessions, spotlight=spotlight))
    else:
        for f in sessions:
            print(render_day_text(f))
            print()

    if args.write:
        p = write_state_file(sessions)
        print(f"[participation-cascade] wrote {p}" if p else "[participation-cascade] WARN state write failed")
    if args.report:
        p = write_report(sessions, spotlight=spotlight)
        print(f"[participation-cascade] wrote {p}" if p else "[participation-cascade] WARN report write failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

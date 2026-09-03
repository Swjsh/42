"""rule_break_audit.py -- deterministic post-hoc audit of the SPY arms against J's 10 rules.

WHY THIS EXISTS. `automation/state/rule-breaks.jsonl` is what the go-live gate's BEHAVIOURAL
criterion (criterion 4) counts. It holds exactly ONE row, dated 2026-05-18. Its only writers
were ever LLM prompt instructions -- `automation/prompts/eod-summary.md`,
`eod-workers/02-predictions-and-audit.md`, `weekly-review.md` -- and the LLM EOD workers were
retired. **No code path has ever written a rule break.** So criterion 4 reads an abandoned
ledger and, before the 2026-09-01 honesty fix, reported `0 rule breaks -> PASS`. It now
reports PASS_UNVERIFIED, which is honest but permanent: nothing can ever verify it.

`analysis/weekly/2026-W30.md` put it plainly months ago: "if rule-breaks.jsonl is dead AND
followed_rules is always blank, there is currently no mechanism anywhere that flags a Rule
1-10 violation on a real trade." The 2026-09-01 audit said "writer restoration queued" -- no
queue item was ever filed. This is that writer.

Ported from the pattern that already works on the futures side
(`backtest/futures/futures_eod.py::rule_audit`): a post-hoc check run INDEPENDENTLY of the
pre-trade gate, because checking only at entry time cannot catch a gate that was bypassed or
mis-wired. Process over P&L -- a winning trade that broke a rule is still a break.

THE DESIGN RULE THAT MATTERS MOST. This instrument must never let "0 breaks" be read as "the
day was clean". It checks the mechanically-verifiable SUBSET of the 10 rules, and every run
emits a COVERAGE artifact naming, per rule and per arm, whether that rule was actually
checkable from the recorded data. A rule whose inputs are missing is reported NOT_CHECKED --
never as a pass. That distinction is the entire point: this file exists because an instrument
that could not tell "clean" from "dead" reported clean for four months.

WHAT IT WRITES
  automation/state/rule-breaks.jsonl   -- ONLY real breaks, in the existing row schema.
      The gate counts EVERY parseable row with an in-window `date` as a break, so a
      heartbeat/coverage row written here would spuriously FAIL criterion 4. Coverage goes
      to its own file, deliberately.
  automation/state/rule-break-audit.json -- the coverage/heartbeat artifact: what ran, over
      which arms and dates, which rules were checkable, and what was found.

DELIBERATELY NOT DONE HERE: teaching `go_live_gate.py` criterion 4 to read the coverage
artifact so an audited-and-clean window can read PASS instead of PASS_UNVERIFIED. That
changes how a go-live criterion is MEASURED, mid-window, and a measurement change slipped in
without a pre-registration is the post-hoc-bar-change anti-pattern this project bans (OP-11).
Filed as its own item instead.

R7/R8 EXTENSION (2026-09-03, RULE-AUDIT-COVERAGE-GAPS). Closes two of the four rules the
original build declared NOT_CHECKED, with LIVE broker reads (read-only GET, never a write
path) via the same `fleet_broker` module the fleet already uses. Both are OFF by default
(`run(..., include_r7_r8=False)`) so the existing network-free tests and every other caller
of `run()`/`main()` keep behaving exactly as before; opt in via `--live-r7-r8` on the CLI.

  R7 (PDT awareness): fetch_r7_pdt_observations() reads /v2/account per arm. VERIFIED LIVE
  2026-09-03 against all 5 reachable arms: Alpaca's account payload no longer carries
  `daytrade_count` or `pattern_day_trader` AT ALL (replaced by `intraday_adjustments`) --
  matching pdt_tracker.py's own 2026-08-18 finding. The queue item's proposed break
  condition ("pattern_day_trader flips true while equity is under the broker's stated
  threshold") therefore has no field to read on any arm today; this reports exactly what
  the broker returns per arm (equity, intraday_adjustments, and the two fields' presence)
  and marks the break condition `break_checkable: false` with the concrete missing field
  name, rather than inventing a threshold or silently reporting a false "0 breaks".

  R8 (journal every trade): fetch_r8_journal_join() pulls each arm's CLOSED broker orders
  for one date (GET /v2/orders?status=closed, filtered to that ET date locally -- `after=`
  is a lower bound only, same trap entry_location_shadow.py already documents) and matches
  each option fill to its `journal/trades.csv` leg by (account_id, OCC symbol, side, qty,
  fill time +/-120s, price +/-$0.02) via the pure, fixture-tested match_fills_to_journal().
  There is no separate fleet ledger to also read: fleet_journal_bridge.py bridges ALL
  fleet_rest arms (safe-1/safe-3/risky-1/risky-3) AND both core mcp_heartbeat arms
  (safe-2/bold-2) into this SAME trades.csv, keyed by short `account_id` (safe/bold/
  safe-3/risky-1/risky-3) -- verified: journal/trades-aggressive.csv carries only 15 rows
  with no account_id populated on any of them and no current writer greps it. Reports
  match RATE + unmatched rows with their closest candidate; per the queue item's own
  warning that a wrong join manufactures false breaks, this module never auto-promotes an
  unmatched fill to a RULE_8 break -- see run()'s r8_journal_join key for the numbers this
  was validated against (2026-09-02 and 2026-08-27) before any break judgement is made.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import itertools
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
CORE_DECISIONS = STATE / "core-decisions.jsonl"
FLEET_DIR = STATE / "fleet"
ACCOUNTS = FLEET_DIR / "accounts.json"
SAFE_PARAMS = STATE / "params.json"
BOLD_PARAMS = STATE / "aggressive" / "params.json"
RULE_BREAKS = STATE / "rule-breaks.jsonl"
COVERAGE = STATE / "rule-break-audit.json"

# The named playbook patterns (markdown/0dte/playbook.md, mirrored by
# automation/state/fleet/strategies.py). Rule 1: no setup, no trade.
PLAYBOOK_SETUPS = {
    "BEARISH_REJECTION_RIDE_THE_RIBBON",
    "BULLISH_RECLAIM_RIDE_THE_RIBBON",
    "VWAP_CONTINUATION",
    "VWAP_RECLAIM_FAILED_BREAK",
}

# Core `account` label -> arm id. The core engine writes one ledger for both core arms.
CORE_ACCOUNT_TO_ARM = {"safe": "safe-2", "bold": "bold-2"}

# Rules this instrument can and cannot mechanically check. Kept as data, and emitted
# verbatim in every coverage artifact, so the report can never imply more than it verified.
RULES_CHECKED = {
    "RULE_1_NAMED_SETUP": "entry's setup is a named playbook pattern",
    "RULE_2_WAIT_FOR_TRIGGER": "entry timestamp is after its own trigger bar closed "
                               "(anticipation entries are forbidden) -- core arms only",
    "RULE_3_DEFINED_STOP": "entry carries a stop, and a structure-mode stop carries the "
                           "chart level it is anchored to",
    "RULE_4_NO_ADDING": "entry was placed while flat -- fleet arms only",
    "RULE_5_KILL_SWITCH": "no entry after that arm's daily kill switch tripped -- fleet only",
    "RULE_6_RISK_CAP": "position cost is within the arm's per-trade risk cap",
}
RULES_NOT_CHECKED = {
    "RULE_7_PDT": "the BREAK condition (pattern_day_trader flips true under the broker's "
                  "equity threshold) is not checkable: verified live 2026-09-03, Alpaca's "
                  "account payload carries neither `pattern_day_trader` nor "
                  "`daytrade_count` on any of the 5 reachable arms any more -- see "
                  "r7_pdt_observations for what IS read (equity + intraday_adjustments) "
                  "when run(include_r7_r8=True)",
    "RULE_8_JOURNAL": "the BREAK condition (a fill with no journal row) is not auto-"
                      "declared: the fill->trades.csv join is now built and fixture-"
                      "tested (match_fills_to_journal), but a wrong join would manufacture "
                      "false breaks on the gate's own ledger, so it ships as an "
                      "OBSERVATION (match rate + unmatched rows) via r8_journal_join when "
                      "run(include_r7_r8=True, r8_date=...) rather than an automatic break",
    "RULE_9_NO_MIDSESSION_RULE_CHANGES": "needs a timestamped hash/snapshot of every "
                                         "frozen trading-path file (params.json, "
                                         "aggressive/params.json, heartbeat_core.py, "
                                         "filters.py, risk_gate.py, exit_manager.py) taken "
                                         "at RTH open (09:30 ET) and close (16:00 ET); no "
                                         "such snapshot exists today, so there is no pair "
                                         "of hashes to diff for a mid-session change",
    "RULE_10_GAMMA_VETO": "the free-model veto has been disabled since 2026-08-12 "
                          "(GAMMA_FREE_MODEL_VETO defaults 0) and no ledger records a "
                          "refused-but-would-have-fired decision -- there is no row shape "
                          "for a veto event to check against even in principle",
}


# ---------------------------------------------------------------------------------------
# io helpers -- every one fails OPEN to a value the caller can recognise as "no data",
# never to a value that reads as "fine".
# ---------------------------------------------------------------------------------------

def read_jsonl(path: Path) -> Optional[list[dict]]:
    """None means unreadable/absent -- distinct from [] meaning genuinely empty."""
    if not path.exists():
        return None
    out: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict):
                out.append(row)
    except OSError:
        return None
    return out


def read_json(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _date_of(row: dict) -> Optional[str]:
    for key in ("date", "ts_et", "ts"):
        v = row.get(key)
        if isinstance(v, str) and len(v) >= 10 and v[4] == "-" and v[7] == "-":
            return v[:10]
    return None


def _f(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out


# ---------------------------------------------------------------------------------------
# risk caps
# ---------------------------------------------------------------------------------------

def per_trade_cap_pct(arm_id: str, safe_params: Optional[dict],
                      bold_params: Optional[dict]) -> Optional[float]:
    """The arm's per-trade risk cap as a fraction, or None if it cannot be resolved.

    None is load-bearing: an arm whose cap we cannot read has RULE_6 reported NOT_CHECKED
    for that arm rather than audited against a guessed number. A fabricated cap would
    manufacture breaks or, worse, silently clear real ones.
    """
    src = bold_params if arm_id.startswith(("bold", "risky")) else safe_params
    if not src:
        return None
    return _f(src.get("per_trade_risk_cap_pct"))


# ---------------------------------------------------------------------------------------
# entry normalisation -- the two ledgers have different shapes; audit logic sees one shape.
# ---------------------------------------------------------------------------------------

def normalise_core_entry(row: dict) -> dict:
    ex = row.get("exec") or {}
    return {
        "source": "core", "arm_id": CORE_ACCOUNT_TO_ARM.get(str(row.get("account")), "core-?"),
        "date": _date_of(row), "ts_et": row.get("ts_et"),
        "setup": row.get("setup") or ex.get("setup"),
        "side": row.get("side") or ex.get("side"),
        "qty": _f(ex.get("qty")), "premium": _f(ex.get("entry_px") or ex.get("premium")),
        "equity": _f(ex.get("equity")),
        "stop": ex.get("stop"), "stop_mode": ex.get("stop_mode"),
        "trigger_level": ex.get("trigger_level"),
        "trigger_bar_et": row.get("trigger_bar_et"),
        "flat": None,      # core refuses separately via its NOT_FLAT action
        "killed": None,    # not recorded on the core row
    }


def normalise_fleet_entry(row: dict) -> dict:
    pl = row.get("placement") or {}
    return {
        "source": "fleet", "arm_id": row.get("arm_id"),
        "date": _date_of(row), "ts_et": row.get("ts_et"),
        "setup": row.get("setup_name"), "side": row.get("side"),
        "qty": _f(row.get("qty")), "premium": _f(row.get("premium") or pl.get("mid")),
        "equity": _f(row.get("equity")),
        "stop": pl.get("stop"), "stop_mode": pl.get("stop_mode"),
        "trigger_level": row.get("trigger_level") if row.get("trigger_level") is not None
        else pl.get("trigger_level"),
        "trigger_bar_et": None,   # not recorded on the fleet row
        "flat": row.get("flat"),
        "killed": row.get("killed"),
    }


def collect_entries(core_rows: Optional[list[dict]],
                    fleet_rows_by_arm: dict[str, Optional[list[dict]]]) -> list[dict]:
    entries: list[dict] = []
    for row in core_rows or []:
        if row.get("action") == "PLACED":
            entries.append(normalise_core_entry(row))
    for arm, rows in fleet_rows_by_arm.items():
        for row in rows or []:
            if str(row.get("action", "")).startswith("ENTER") and "REFUSED" not in str(row.get("action")):
                e = normalise_fleet_entry(row)
                e["arm_id"] = e.get("arm_id") or arm
                entries.append(e)
    return entries


# ---------------------------------------------------------------------------------------
# the checks. Each returns (breaks, checked) -- `checked` False means the inputs were not
# present, so this rule was NOT verified for this entry. Never conflate the two.
# ---------------------------------------------------------------------------------------

def check_named_setup(e: dict) -> tuple[list[dict], bool]:
    setup = e.get("setup")
    if not setup:
        return [], False
    if str(setup).upper() not in PLAYBOOK_SETUPS:
        return [_break(e, "RULE_1_NAMED_SETUP", "high",
                       f"entry taken on setup {setup!r}, which is not a named playbook "
                       f"pattern (Rule 1: no setup, no trade)")], True
    return [], True


def check_wait_for_trigger(e: dict, bar_minutes: int = 5) -> tuple[list[dict], bool]:
    bar, ts = e.get("trigger_bar_et"), e.get("ts_et")
    if not isinstance(bar, str) or not isinstance(ts, str):
        return [], False
    try:
        bar_dt = dt.datetime.fromisoformat(bar)
        ts_dt = dt.datetime.fromisoformat(ts)
    except ValueError:
        return [], False
    if bar_dt.tzinfo is not None and ts_dt.tzinfo is None:
        bar_dt = bar_dt.replace(tzinfo=None)
    if ts_dt.tzinfo is not None and bar_dt.tzinfo is None:
        ts_dt = ts_dt.replace(tzinfo=None)
    close = bar_dt + dt.timedelta(minutes=bar_minutes)
    if ts_dt < close:
        return [_break(e, "RULE_2_WAIT_FOR_TRIGGER", "high",
                       f"entered {ts} before its own trigger bar ({bar}) closed at "
                       f"{close.isoformat()} -- an anticipation entry (Rule 2)")], True
    return [], True


def check_defined_stop(e: dict) -> tuple[list[dict], bool]:
    """Rule 3, plus the invariant exit_manager.py:268 actually enforces -- a structure-mode
    stop with no trigger_level silently resolves to premium mode, so the chart stop the
    journal claims was set is not the stop that was armed."""
    if e.get("stop") is None and e.get("stop_mode") is None:
        return [], False
    out = []
    if e.get("stop") is None:
        out.append(_break(e, "RULE_3_DEFINED_STOP", "high",
                          "entry recorded with no stop (Rule 3: defined stop on entry)"))
    if str(e.get("stop_mode")) == "structure" and e.get("trigger_level") is None:
        out.append(_break(e, "RULE_3_DEFINED_STOP", "medium",
                          "structure-mode stop carries no trigger_level -- exit_manager "
                          "resolves this to PREMIUM mode, so the chart stop recorded is "
                          "not the stop that was armed"))
    return out, True


def check_no_adding(e: dict) -> tuple[list[dict], bool]:
    if e.get("flat") is None:
        return [], False
    if not e.get("flat"):
        return [_break(e, "RULE_4_NO_ADDING", "high",
                       "entry placed while NOT flat -- adding without a new confirmed "
                       "trigger (Rule 4)")], True
    return [], True


def check_kill_switch(e: dict) -> tuple[list[dict], bool]:
    if e.get("killed") is None:
        return [], False
    if e.get("killed"):
        return [_break(e, "RULE_5_KILL_SWITCH", "high",
                       "entry placed after this arm's daily kill switch had tripped "
                       "(Rule 5: day closed, no revenge trades)")], True
    return [], True


def check_risk_cap(e: dict, cap_pct: Optional[float]) -> tuple[list[dict], bool]:
    qty, prem, eq = e.get("qty"), e.get("premium"), e.get("equity")
    if cap_pct is None or not qty or not prem or not eq or eq <= 0:
        return [], False
    cost = qty * prem * 100.0
    frac = cost / eq
    if frac > cap_pct + 1e-9:
        return [_break(e, "RULE_6_RISK_CAP", "high",
                       f"position cost ${cost:,.2f} is {frac:.1%} of ${eq:,.2f} equity, over "
                       f"this arm's {cap_pct:.0%} per-trade cap (Rule 6)")], True
    return [], True


def _break(e: dict, rule_id: str, severity: str, what: str) -> dict:
    """A row in the EXISTING rule-breaks.jsonl schema -- the gate parses these."""
    return {
        "date": e.get("date"),
        "rule_id": rule_id,
        "setup_name": e.get("setup"),
        "trade_row": None,
        "arm_id": e.get("arm_id"),
        "ts_et": e.get("ts_et"),
        "severity": severity,
        "what_happened": what,
        "fix_proposal": "",
        "cost_estimate_dollars": 0,
        "cost_estimate_method": "not estimated -- this auditor detects, it does not price",
        "detected_by": "rule_break_audit.py",
    }


# ---------------------------------------------------------------------------------------
# audit
# ---------------------------------------------------------------------------------------

def audit_entries(entries: list[dict], safe_params: Optional[dict],
                  bold_params: Optional[dict]) -> tuple[list[dict], dict]:
    """Returns (breaks, per-rule coverage). Coverage counts entries the rule could actually
    be evaluated against -- the number that makes '0 breaks' meaningful or meaningless."""
    breaks: list[dict] = []
    coverage = {rule: {"checked": 0, "not_checked": 0, "breaks": 0} for rule in RULES_CHECKED}

    for e in entries:
        cap = per_trade_cap_pct(str(e.get("arm_id") or ""), safe_params, bold_params)
        results = {
            "RULE_1_NAMED_SETUP": check_named_setup(e),
            "RULE_2_WAIT_FOR_TRIGGER": check_wait_for_trigger(e),
            "RULE_3_DEFINED_STOP": check_defined_stop(e),
            "RULE_4_NO_ADDING": check_no_adding(e),
            "RULE_5_KILL_SWITCH": check_kill_switch(e),
            "RULE_6_RISK_CAP": check_risk_cap(e, cap),
        }
        for rule, (found, checked) in results.items():
            coverage[rule]["checked" if checked else "not_checked"] += 1
            coverage[rule]["breaks"] += len(found)
            breaks.extend(found)
    return breaks, coverage


def binding_evidence(entries: list[dict], safe_params: Optional[dict],
                     bold_params: Optional[dict]) -> dict:
    """Was each constraint ever APPROACHED? A zero from a rule tested at 99% of its limit and
    a zero from a rule that never had an opportunity to fire are both "0 breaks" and mean
    completely different things.

    First real run: RULE_6's largest position was 0.99 of its cap (8 entries above 0.8) --
    an informative zero, the cap is binding and was respected. RULE_5 saw `killed=True`
    exactly never, so its zero says nothing about enforcement. Reporting the count alone
    would have flattened that difference away.
    """
    fracs: list[float] = []
    for e in entries:
        cap = per_trade_cap_pct(str(e.get("arm_id") or ""), safe_params, bold_params)
        qty, prem, eq = e.get("qty"), e.get("premium"), e.get("equity")
        if cap and qty and prem and eq and eq > 0:
            fracs.append((qty * prem * 100.0 / eq) / cap)
    fracs.sort()
    kill_seen = sum(1 for e in entries if e.get("killed") is True)
    notflat_seen = sum(1 for e in entries if e.get("flat") is False)
    return {
        "RULE_6_RISK_CAP": {
            "n": len(fracs),
            "max_fraction_of_cap": round(fracs[-1], 4) if fracs else None,
            "n_above_80pct_of_cap": sum(1 for f in fracs if f > 0.8),
            "informative": bool(fracs) and fracs[-1] > 0.8,
            "note": ("the cap was approached and not crossed" if fracs and fracs[-1] > 0.8
                     else "the cap was never approached -- a zero here says little"),
        },
        "RULE_5_KILL_SWITCH": {
            "kill_switch_tripped_events_seen": kill_seen,
            "informative": kill_seen > 0,
            "note": ("the kill switch tripped and entries were checked against it"
                     if kill_seen else "the kill switch never tripped in this window, so "
                                       "zero breaks says nothing about enforcement"),
        },
        "RULE_4_NO_ADDING": {
            "not_flat_at_entry_events_seen": notflat_seen,
            "informative": notflat_seen > 0,
            "note": ("entries were attempted while not flat" if notflat_seen else
                     "no entry was ever attempted while not flat -- the engine's own "
                     "NOT_FLAT refusal fires upstream, so zero here is expected, not proof"),
        },
    }


def load_all(repo: Path = REPO) -> dict:
    state = repo / "automation" / "state"
    fleet = state / "fleet"
    fleet_rows: dict[str, Optional[list[dict]]] = {}
    accounts = read_json(fleet / "accounts.json") or {}
    for arm in (accounts.get("arms") or []):
        arm_id = arm.get("id")
        if not arm_id or arm.get("execution") != "fleet_rest":
            continue
        fleet_rows[arm_id] = read_jsonl(fleet / arm_id / "decisions.jsonl")
    return {
        "core": read_jsonl(state / "core-decisions.jsonl"),
        "fleet": fleet_rows,
        "safe_params": read_json(state / "params.json"),
        "bold_params": read_json(state / "aggressive" / "params.json"),
    }


# ---------------------------------------------------------------------------------------
# R7 (PDT awareness) + R8 (journal-every-trade) -- live-broker OBSERVATION extensions.
# See the module docstring's "R7/R8 EXTENSION" section for the full design rationale.
# Both are additive-only to the report schema and OFF by default in run().
# ---------------------------------------------------------------------------------------

# arm id -> the short account_id journal/trades.csv uses for that arm's rows (matches
# fleet_journal_bridge.CORE_ARMS for the 2 core arms, and the arm id itself for fleet_rest
# arms -- re-declared here rather than imported, same dependency-free convention every
# other module in this family (fleet_journal_bridge.py, day_summary.py) already follows).
R7_R8_ARMS: dict[str, str] = {
    "safe-2": "safe", "bold-2": "bold", "safe-3": "safe-3",
    "risky-1": "risky-1", "risky-3": "risky-3",
}

_OCC_SYMBOL_RE = re.compile(r"^SPY\d{6}[CP]\d{8}$")
_JOURNAL_CONTRACT_RE = re.compile(r"^SPY (\d{4})-(\d{2})-(\d{2}) (\d+(?:\.\d+)?)([CP])$")


def _fleet_broker_module():
    """Import automation/state/fleet/fleet_broker.py by path, READ-ONLY use only
    (get_account / _request(..., method='GET', ...)). Never touches order_intent_log's
    write path or any place/cancel/close call. Returns None (never raises) on any import
    failure -- this is an observation surface, not the trading path, and must fail open."""
    import importlib.util
    path = REPO / "automation" / "state" / "fleet" / "fleet_broker.py"
    try:
        spec = importlib.util.spec_from_file_location("fleet_broker_rba", path)
        if not spec or not spec.loader:
            return None
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:  # noqa: BLE001 -- observation surface must never crash the caller
        return None


def fetch_r7_pdt_observations(repo: Path = REPO) -> dict:
    """R7 PDT awareness. Reads /v2/account (GET only) per arm in R7_R8_ARMS. See the
    module docstring: verified live 2026-09-03 that `pattern_day_trader` and
    `daytrade_count` are ABSENT from every reachable arm's account payload today, so the
    queue item's proposed break condition has no field to evaluate. Reports what IS
    present (equity, intraday_adjustments) and marks `break_checkable` per-arm on whether
    `pattern_day_trader` was actually in the payload -- never fabricated."""
    fb = _fleet_broker_module()
    if fb is None:
        return {"error": "fleet_broker import failed", "arms": {}}
    try:
        creds = fb.load_creds()
    except Exception as exc:  # noqa: BLE001
        return {"error": f"load_creds failed: {exc}", "arms": {}}

    out: dict[str, dict] = {}
    for arm, acct_label in R7_R8_ARMS.items():
        c = creds.get(arm)
        if not c:
            out[arm] = {"reachable": False, "reason": "no credentials in fleet/secrets.json"}
            continue
        acct = fb.get_account(c)
        if not isinstance(acct, dict) or "_error" in acct:
            reason = acct.get("_error") if isinstance(acct, dict) else "bad response"
            out[arm] = {"reachable": False, "reason": str(reason)}
            continue
        pdt_present = "pattern_day_trader" in acct
        dtc_present = "daytrade_count" in acct
        out[arm] = {
            "reachable": True,
            "account_label": acct_label,
            "equity": _f(acct.get("equity")),
            "pattern_day_trader": acct.get("pattern_day_trader") if pdt_present else None,
            "pattern_day_trader_field_present": pdt_present,
            "daytrade_count": acct.get("daytrade_count") if dtc_present else None,
            "daytrade_count_field_present": dtc_present,
            "intraday_adjustments": acct.get("intraday_adjustments"),
            "break_checkable": pdt_present,
            "break": bool(pdt_present and acct.get("pattern_day_trader") is True),
        }
    return {
        "generated_at_et": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "finra_note": "FINRA repealed the $25K margin day-trading floor 2026-06-04 "
                      "(SR-FINRA-2025-017); these accounts are verified on the new "
                      "regime (CLAUDE.md Account context). This is awareness, not a "
                      "break condition, per the queue item's own framing.",
        "arms": out,
    }


def occ_symbol_from_contract(contract: Optional[str]) -> Optional[str]:
    """Normalise either trades.csv contract shape ('SPY 2026-08-27 768C', the common
    case, or an already-OCC 'SPY260827C00768000', seen on 27 older rows) to the canonical
    OCC symbol the broker returns. Returns None on anything that doesn't parse -- never a
    guessed symbol, which would silently corrupt the join."""
    if not contract:
        return None
    contract = contract.strip()
    if _OCC_SYMBOL_RE.match(contract):
        return contract
    m = _JOURNAL_CONTRACT_RE.match(contract)
    if not m:
        return None
    yyyy, mm, dd, strike, side = m.groups()
    strike_thousandths = round(float(strike) * 1000)
    return f"SPY{yyyy[2:]}{mm}{dd}{side}{strike_thousandths:08d}"


def _time_to_seconds(hms: Optional[str]) -> Optional[int]:
    if not isinstance(hms, str):
        return None
    parts = hms.strip().split(":")
    if len(parts) != 3:
        return None
    try:
        h, m, s = (int(p) for p in parts)
    except ValueError:
        return None
    return h * 3600 + m * 60 + s


def journal_legs_for_date(date: str, repo: Path = REPO) -> list[dict]:
    """Every ENTRY and EXIT leg journal/trades.csv carries for `date`, one dict per leg.
    Pure file read. This is the ONLY journal ledger to read for R8: fleet_journal_bridge.py
    bridges every fleet_rest arm (safe-1/safe-3/risky-1/risky-3) AND both core
    mcp_heartbeat arms (safe-2/bold-2) into this SAME file, keyed by short `account_id`.
    journal/trades-aggressive.csv is NOT a second fleet ledger -- verified: all 15 of its
    rows carry no account_id and no current writer (grepped setup/scripts + automation)
    appends to it any more; reading it here would silently double- or mis-count."""
    path = repo / "journal" / "trades.csv"
    if not path.exists():
        return []
    legs: list[dict] = []
    with path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for i, row in enumerate(reader):
            if row.get("date") != date:
                continue
            occ = occ_symbol_from_contract(row.get("contract"))
            acct = row.get("account_id")
            qty = _f(row.get("qty"))
            if row.get("time_entry") and row.get("entry_px") not in (None, ""):
                legs.append({
                    "row": i, "leg": "entry", "account_id": acct, "occ": occ,
                    "side": "buy", "qty": qty, "px": _f(row.get("entry_px")),
                    "ts_s": _time_to_seconds(row.get("time_entry")),
                    "ts_hms": row.get("time_entry"),
                })
            if row.get("time_exit") and row.get("exit_px") not in (None, ""):
                legs.append({
                    "row": i, "leg": "exit", "account_id": acct, "occ": occ,
                    "side": "sell", "qty": qty, "px": _f(row.get("exit_px")),
                    "ts_s": _time_to_seconds(row.get("time_exit")),
                    "ts_hms": row.get("time_exit"),
                })
    return legs


def _closest_candidate(f: dict, legs: list[dict], available: list[int]) -> Optional[dict]:
    """Diagnostics for an unmatched fill: the nearest journal leg by (qty delta, time
    delta, price delta) among same-account/same-symbol/same-side candidates, so an
    unmatched report names its nearest miss instead of just 'none found'."""
    best: Optional[dict] = None
    best_score: Optional[tuple] = None
    for idx in available:
        leg = legs[idx]
        if leg["account_id"] != f.get("account_id") or leg["occ"] != f.get("symbol"):
            continue
        if leg["side"] != f.get("side"):
            continue
        t_delta = (abs(leg["ts_s"] - f["ts_s"])
                   if leg.get("ts_s") is not None and f.get("ts_s") is not None else 999_999)
        q_delta = abs((leg.get("qty") or 0) - (f.get("qty") or 0))
        px_delta = abs((leg.get("px") or 0) - (f.get("px") or 0))
        score = (q_delta, t_delta, px_delta)
        if best_score is None or score < best_score:
            best_score, best = score, {
                "row": leg["row"], "leg": leg["leg"], "qty": leg["qty"], "px": leg["px"],
                "ts": leg["ts_hms"], "delta_seconds": t_delta, "qty_delta": q_delta,
                "px_delta": round(px_delta, 4),
            }
    return best


def _split_match(f: dict, legs: list[dict], available: list[int],
                 tolerance_s: int, price_tol: float) -> Optional[list[int]]:
    """SPLIT-FILL fallback. Live-run finding (2026-09-02, risky-1): a single broker order
    can fill as ONE execution while the journal records it as MULTIPLE same-timestamp,
    same-price legs whose quantities sum to the fill (e.g. one qty=5 buy fill journaled
    as qty=1 + qty=4 rows) -- the journal splits at the DECISION level (TP1/runner
    bookkeeping), the broker does not. An exact single-leg match therefore fails even
    though every contract IS journaled; this is the difference between a real Rule-8 gap
    and a many-legs-to-one-fill granularity mismatch. Tries qty-summing combinations of
    2-4 same-account/symbol/side/time/price candidate legs before giving up."""
    candidates = [idx for idx in available
                  if legs[idx]["account_id"] == f.get("account_id")
                  and legs[idx]["occ"] == f.get("symbol")
                  and legs[idx]["side"] == f.get("side")
                  and legs[idx]["ts_s"] is not None and f.get("ts_s") is not None
                  and abs(legs[idx]["ts_s"] - f["ts_s"]) <= tolerance_s
                  and (legs[idx]["px"] is None or f.get("px") is None
                       or abs(legs[idx]["px"] - f["px"]) <= price_tol)]
    target = f.get("qty")
    if not candidates or target is None:
        return None
    for r in range(2, min(len(candidates), 4) + 1):
        for combo in itertools.combinations(candidates, r):
            if abs(sum(legs[i]["qty"] or 0 for i in combo) - target) < 1e-9:
                return list(combo)
    return None


def match_fills_to_journal(fills: list[dict], legs: list[dict],
                           tolerance_s: int = 120, price_tol: float = 0.02) -> dict:
    """Pure matcher -- fixture-tested, no I/O. `fills`: broker closed-order fills, one
    dict per fill {account_id, symbol (OCC), side, qty, px, ts_s}. `legs`:
    journal_legs_for_date() output. Greedy nearest-time match within tolerance_s seconds
    and price_tol dollars, requiring exact account/symbol/side/qty match first, then a
    qty-summing split-fill fallback (_split_match, see its docstring); each leg is
    consumed at most once so two same-priced fills/legs can't both claim one journal row."""
    available = list(range(len(legs)))
    journaled: list[dict] = []
    unmatched: list[dict] = []
    ordered = sorted(fills, key=lambda x: x.get("ts_s") if x.get("ts_s") is not None else -1)
    for f in ordered:
        candidates = []
        for idx in available:
            leg = legs[idx]
            if leg["account_id"] != f.get("account_id"):
                continue
            if leg["occ"] != f.get("symbol"):
                continue
            if leg["side"] != f.get("side"):
                continue
            if leg["qty"] != f.get("qty"):
                continue
            if leg["ts_s"] is None or f.get("ts_s") is None:
                continue
            delta = abs(leg["ts_s"] - f["ts_s"])
            if delta > tolerance_s:
                continue
            if (leg["px"] is not None and f.get("px") is not None
                    and abs(leg["px"] - f["px"]) > price_tol):
                continue
            candidates.append((delta, idx))
        if candidates:
            candidates.sort()
            _, best_idx = candidates[0]
            available.remove(best_idx)
            journaled.append({"fill": f, "journal_row": legs[best_idx]["row"],
                              "leg": legs[best_idx]["leg"], "delta_s": candidates[0][0],
                              "match_kind": "exact"})
            continue
        split_idxs = _split_match(f, legs, available, tolerance_s, price_tol)
        if split_idxs:
            for idx in split_idxs:
                available.remove(idx)
            journaled.append({
                "fill": f,
                "journal_row": [legs[i]["row"] for i in split_idxs],
                "leg": legs[split_idxs[0]]["leg"],
                "delta_s": max(abs(legs[i]["ts_s"] - f["ts_s"]) for i in split_idxs),
                "match_kind": "split_fill (journal recorded this one broker fill as "
                              "multiple same-time/same-price legs summing to its qty)",
            })
            continue
        unmatched.append({"fill": f, "closest_candidate": _closest_candidate(f, legs, available)})
    return {
        "n_fills": len(fills),
        "n_journaled": len(journaled),
        "n_unmatched": len(unmatched),
        "match_rate": (len(journaled) / len(fills)) if fills else None,
        "journaled": journaled,
        "unmatched": unmatched,
    }


def fetch_broker_fills_for_date(arm: str, creds: dict, date: str) -> list[dict]:
    """CLOSED broker orders (GET only) for one arm/date, normalised to fill dicts. Per the
    queue item: source of fills is the broker's closed orders, NOT the journal. `after=`
    is a lower bound only (entry_location_shadow.py's documented trap) -- every fill is
    re-checked against the requested ET date locally before being kept."""
    fb = _fleet_broker_module()
    if fb is None:
        return []
    from zoneinfo import ZoneInfo
    url = (f"orders?status=closed&after={date}T00:00:00Z&until={date}T23:59:59Z"
           f"&limit=500&direction=asc")
    rows = fb._request(creds, url)  # noqa: SLF001 -- deliberate reuse of the fleet REST core, GET only
    if not isinstance(rows, list):
        return []
    out: list[dict] = []
    for o in rows:
        sym = str(o.get("symbol") or "")
        if not (sym.startswith("SPY") and len(sym) >= 15):
            continue
        try:
            qty = float(o.get("filled_qty") or 0)
        except (TypeError, ValueError):
            qty = 0.0
        if qty <= 0 or not o.get("filled_at"):
            continue
        try:
            ts_utc = dt.datetime.fromisoformat(str(o["filled_at"]).replace("Z", "+00:00"))
            ts_et = ts_utc.astimezone(ZoneInfo("America/New_York"))
        except ValueError:
            continue
        if ts_et.date().isoformat() != date:
            continue
        out.append({
            "account_id": R7_R8_ARMS.get(arm, arm),
            "arm_id": arm,
            "symbol": sym,
            "side": o.get("side"),
            "qty": qty,
            "px": _f(o.get("filled_avg_price")),
            "ts_s": ts_et.hour * 3600 + ts_et.minute * 60 + ts_et.second,
            "filled_at_et": ts_et.strftime("%H:%M:%S"),
            "order_id": o.get("id"),
        })
    return out


def fetch_r8_journal_join(date: str, repo: Path = REPO,
                          arms: Optional[dict] = None) -> dict:
    """R8 journal-every-trade, OBSERVATION-first (see module docstring). Pulls each arm's
    closed broker orders for `date` and matches against journal/trades.csv via
    match_fills_to_journal(). Returns match rate + unmatched detail per arm; never
    auto-declares a RULE_8 break -- the caller decides after reading the unmatched rows,
    per the queue item's own warning about a wrong join manufacturing false breaks."""
    arms = arms or R7_R8_ARMS
    fb = _fleet_broker_module()
    legs = journal_legs_for_date(date, repo)
    if fb is None:
        return {"date": date, "error": "fleet_broker import failed", "arms": {}}
    try:
        creds = fb.load_creds()
    except Exception as exc:  # noqa: BLE001
        return {"date": date, "error": f"load_creds failed: {exc}", "arms": {}}

    per_arm: dict[str, dict] = {}
    totals = {"n_fills": 0, "n_journaled": 0, "n_unmatched": 0}
    for arm, acct_label in arms.items():
        c = creds.get(arm)
        if not c:
            per_arm[arm] = {"reachable": False, "reason": "no credentials"}
            continue
        fills = fetch_broker_fills_for_date(arm, c, date)
        arm_legs = [leg for leg in legs if leg["account_id"] == acct_label]
        result = match_fills_to_journal(fills, arm_legs)
        per_arm[arm] = result
        totals["n_fills"] += result["n_fills"]
        totals["n_journaled"] += result["n_journaled"]
        totals["n_unmatched"] += result["n_unmatched"]
    totals["match_rate"] = (totals["n_journaled"] / totals["n_fills"]) if totals["n_fills"] else None
    return {"date": date, "arms": per_arm, "totals": totals}


def run(since: Optional[str] = None, repo: Path = REPO, write: bool = True,
        include_r7_r8: bool = False, r8_date: Optional[str] = None) -> dict:
    data = load_all(repo)
    entries = collect_entries(data["core"], data["fleet"])
    if since:
        entries = [e for e in entries if (e.get("date") or "") >= since]

    breaks, coverage = audit_entries(entries, data["safe_params"], data["bold_params"])

    dates = sorted({e["date"] for e in entries if e.get("date")})
    report = {
        "generated_at_et": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "since": since,
        "entries_audited": len(entries),
        "date_range": [dates[0], dates[-1]] if dates else None,
        "arms_seen": sorted({str(e.get("arm_id")) for e in entries}),
        "breaks_found": len(breaks),
        "coverage_by_rule": coverage,
        "binding_evidence": binding_evidence(
            entries, data["safe_params"], data["bold_params"]),
        "rules_checked": RULES_CHECKED,
        "rules_NOT_checked": RULES_NOT_CHECKED,
        "honesty_note": (
            "'breaks_found: 0' means zero breaks AMONG THE RULES LISTED IN rules_checked, "
            "over entries where that rule's inputs were actually present (see "
            "coverage_by_rule.*.checked). It is NOT a statement that the window was clean: "
            "the rules in rules_NOT_checked were never evaluated, and any rule whose "
            "not_checked count is high was evaluated on very little. See "
            "binding_evidence: a zero from a rule tested at 99% of its limit and a zero "
            "from a rule that never had an opportunity to fire are the same number and "
            "completely different claims."
        ),
        "core_ledger_readable": data["core"] is not None,
        "fleet_arms_readable": {a: rows is not None for a, rows in data["fleet"].items()},
    }

    # ADDITIVE ONLY (2026-09-03, RULE-AUDIT-COVERAGE-GAPS) -- new keys, nothing above
    # renamed/removed, and OFF by default so every existing caller/test is unaffected.
    if include_r7_r8:
        report["r7_pdt_observations"] = fetch_r7_pdt_observations(repo)
        if r8_date:
            report["r8_journal_join"] = fetch_r8_journal_join(r8_date, repo)

    if write:
        state = repo / "automation" / "state"
        _write_json(state / "rule-break-audit.json", report)
        if breaks:
            _append_breaks(state / "rule-breaks.jsonl", breaks)
    return {"report": report, "breaks": breaks}


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps(payload, indent=2)
    body.encode("utf-8")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8")
    tmp.replace(path)


def _append_breaks(path: Path, breaks: list[dict]) -> int:
    """Append only rows not already present, keyed by (date, rule_id, arm_id, ts_et) --
    this runs daily over an append-only ledger and must be idempotent, or a re-run would
    manufacture duplicate 'breaks' and fail the gate's behavioural criterion on its own
    output."""
    existing = read_jsonl(path) or []
    seen = {(r.get("date"), r.get("rule_id"), r.get("arm_id"), r.get("ts_et")) for r in existing}
    fresh = [b for b in breaks
             if (b.get("date"), b.get("rule_id"), b.get("arm_id"), b.get("ts_et")) not in seen]
    if not fresh:
        return 0
    with path.open("a", encoding="utf-8") as fh:
        for row in fresh:
            fh.write(json.dumps(row) + "\n")
    return len(fresh)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--since", help="only audit entries on/after this YYYY-MM-DD")
    ap.add_argument("--no-write", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--live-r7-r8", action="store_true",
                    help="also fetch R7 PDT observations (live GET /v2/account per arm) "
                         "and, with --r8-date, the R8 fill->journal join")
    ap.add_argument("--r8-date", help="YYYY-MM-DD to run the R8 fill->journal join for "
                                      "(requires --live-r7-r8)")
    args = ap.parse_args(argv)

    out = run(since=args.since, write=not args.no_write,
              include_r7_r8=args.live_r7_r8, r8_date=args.r8_date)
    rep = out["report"]
    if args.json:
        print(json.dumps(rep, indent=2))
    else:
        print(f"[{rep['generated_at_et']}] audited {rep['entries_audited']} entries "
              f"across {len(rep['arms_seen'])} arm(s), range {rep['date_range']}")
        for rule, c in rep["coverage_by_rule"].items():
            print(f"  {rule:<26} checked={c['checked']:<5} not_checked={c['not_checked']:<5} "
                  f"breaks={c['breaks']}")
        print(f"  BREAKS FOUND: {rep['breaks_found']}")
        for rule, ev in rep["binding_evidence"].items():
            flag = "informative" if ev.get("informative") else "UNINFORMATIVE"
            print(f"  {rule:<26} [{flag}] {ev['note']}")
        print(f"  NOT checked at all: {', '.join(sorted(RULES_NOT_CHECKED))}")
        if "r7_pdt_observations" in rep:
            r7 = rep["r7_pdt_observations"]
            print("  R7 PDT observations:")
            for arm, obs in r7.get("arms", {}).items():
                if not obs.get("reachable"):
                    print(f"    {arm:<10} UNREACHABLE ({obs.get('reason')})")
                    continue
                print(f"    {arm:<10} equity=${obs['equity']:<10} "
                      f"pattern_day_trader_field_present={obs['pattern_day_trader_field_present']} "
                      f"daytrade_count_field_present={obs['daytrade_count_field_present']} "
                      f"break_checkable={obs['break_checkable']}")
        if "r8_journal_join" in rep:
            r8 = rep["r8_journal_join"]
            print(f"  R8 journal join ({r8.get('date')}):")
            for arm, res in r8.get("arms", {}).items():
                if not res.get("reachable", True):
                    print(f"    {arm:<10} UNREACHABLE ({res.get('reason')})")
                    continue
                rate = res.get("match_rate")
                rate_s = f"{rate:.1%}" if rate is not None else "n/a"
                print(f"    {arm:<10} fills={res['n_fills']:<3} journaled={res['n_journaled']:<3} "
                      f"unmatched={res['n_unmatched']:<3} match_rate={rate_s}")
            t = r8.get("totals", {})
            trate = t.get("match_rate")
            trate_s = f"{trate:.1%}" if trate is not None else "n/a"
            print(f"    TOTAL     fills={t.get('n_fills')} journaled={t.get('n_journaled')} "
                  f"unmatched={t.get('n_unmatched')} match_rate={trate_s}")
    return 0  # fail-open: an auditor that can break its caller is worse than no auditor


if __name__ == "__main__":
    sys.exit(main())

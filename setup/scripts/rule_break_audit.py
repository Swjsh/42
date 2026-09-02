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
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
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
    "RULE_7_PDT": "needs the rolling 5-business-day day-trade count from the broker, not "
                  "just the per-row `day_trades` field",
    "RULE_8_JOURNAL": "needs a verified join from each fill to its journal/trades.csv row; "
                      "the join key has not been established, and a wrong join would "
                      "manufacture false breaks",
    "RULE_9_NO_MIDSESSION_RULE_CHANGES": "needs params file history during RTH, which is "
                                         "not retained",
    "RULE_10_GAMMA_VETO": "not mechanically checkable -- it is about a refusal that, when "
                          "honoured, leaves no trade to audit",
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


def run(since: Optional[str] = None, repo: Path = REPO, write: bool = True) -> dict:
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
    args = ap.parse_args(argv)

    out = run(since=args.since, write=not args.no_write)
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
    return 0  # fail-open: an auditor that can break its caller is worse than no auditor


if __name__ == "__main__":
    sys.exit(main())

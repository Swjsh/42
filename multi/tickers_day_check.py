"""tickers_day_check.py -- the deterministic day-check for the TICKERS lane (goal T6 instrument).

WHY THIS EXISTS. Goal GOAL-TICKERS-LANE-2026-09-04 T6 says "confirm ledger rows at 09:37 ET ...
EOD: flat check from broker". Rule-9 discipline forbids an interactive Claude session during
09:30-15:55 ET, and a check that depends on a human/LLM remembering to look is the failure this
repo keeps re-learning (C7: silent success is failure). So the check is a $0 script fired by
Windows Task Scheduler (Gamma_TickersDayCheck: 09:40 ET + 15:05 ET), reading cold reality:

  open phase (09:40 ET)  did every arm write ledger rows this session? NO_CREDS-only = AMBER
                         (waiting on the secrets paste), DARK / INVARIANT_FAIL = RED.
  eod phase  (15:05 ET)  is every arm FLAT at the broker (never from state), what filled, what
                         was realized, does any state record outlive its broker position?

It writes (1) automation/state/tickers/day-check-<date>-<phase>.json, (2) one PROGRESS LOG line
into the goal file, (3) a `TICKERS-DAY-CHECK` line on STATUS.md `## Known broken` when RED
(cleared again when a later phase is green). It NEVER places or cancels an order and NEVER edits
state -- read-only against the lane and the broker. Exit code is 0 on every verdict (the
verdict is the payload; a non-zero exit would only be swallowed by the hidden-runner hop).

Usage:  python multi/tickers_day_check.py --phase auto|open|eod [--dry-run] [--no-broker]
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from multi import execute as mx  # noqa: E402  -- path helpers, ET clock, creds precheck
from multi.lib import broker as mb  # noqa: E402
from multi.lib import creds as mc  # noqa: E402
from multi.lib import position_state as mps  # noqa: E402

GOAL_PATH = REPO_ROOT / "automation" / "state" / "goals" / "GOAL-TICKERS-LANE-2026-09-04.md"
STATUS_PATH = REPO_ROOT / "automation" / "overnight" / "STATUS.md"
STATUS_MARKER = "TICKERS-DAY-CHECK"
GOAL_LOG_ANCHOR = "## HONEST STATE"
OPEN_PHASE_UNTIL_ET = dt.time(12, 0)   # --phase auto: before noon ET = open, after = eod

GREEN, AMBER, RED, SKIP = "GREEN", "AMBER", "RED", "SKIP"
_RANK = {GREEN: 0, AMBER: 1, RED: 2}


def _load_status_writer():
    """setup/scripts/status_known_broken.py by file path (it is not a package)."""
    p = REPO_ROOT / "setup" / "scripts" / "status_known_broken.py"
    spec = importlib.util.spec_from_file_location("status_known_broken", p)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


# --- readers (all fail SOFT into the report; a read failure is a finding, never a crash) -----
def read_ledger_today(arm: str, date_str: str) -> dict:
    p = mx.arm_ledger_path(arm)
    out: dict[str, Any] = {"path": str(p), "exists": p.exists(), "rows_today": 0, "decisions": {},
                           "first_ts": None, "last_ts": None, "bad_lines": 0}
    if not p.exists():
        return out
    hist: collections.Counter = collections.Counter()
    try:
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    out["bad_lines"] += 1
                    continue
                ts = str(row.get("ts_et") or "")
                if not ts.startswith(date_str):
                    continue
                out["rows_today"] += 1
                hist[str(row.get("decision") or "?")] += 1
                out["first_ts"] = out["first_ts"] or ts
                out["last_ts"] = ts
    except OSError as e:
        out["read_error"] = f"{type(e).__name__}: {e}"
    out["decisions"] = dict(hist.most_common())
    return out


def read_day_file(arm: str, date_str: str) -> dict:
    p = mx.arm_day_path(arm, date_str)
    if not p.exists():
        return {"exists": False, "fills": 0, "realized_pnl_today": None, "kill_tripped": None}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"exists": True, "read_error": f"{type(e).__name__}: {e}"}
    fills = list(d.get("fills") or [])
    return {"exists": True, "fills": len(fills),
            "buys": sum(1 for f in fills if str(f.get("side")) == "BUY"),
            "sells": sum(1 for f in fills if str(f.get("side", "")).startswith("SELL")),
            "realized_pnl_today": d.get("realized_pnl_today"),
            "start_of_day_equity": d.get("start_of_day_equity"),
            "kill_tripped": d.get("kill_tripped")}


def read_state(arm: str) -> dict:
    p = mx.arm_state_path(arm)
    if not p.exists():
        return {"exists": False, "records": 0, "contracts": []}
    try:
        st = mps.load_state(path=p)
    except Exception as e:  # noqa: BLE001 -- unreadable state is a finding
        return {"exists": True, "read_error": f"{type(e).__name__}: {e}", "records": -1, "contracts": []}
    return {"exists": True, "records": len(st), "contracts": sorted(st.keys())}


def broker_snapshot(lane_params: dict, arm: str, arm_cfg: dict) -> dict:
    """Read-only: account + option positions in THIS arm's universe. Mirrors execute.run_arm's
    resolve/verify path so the day-check sees exactly the account the executor traded."""
    key_source = mx.effective_key_source(arm_cfg)
    err = mx.precheck_creds(key_source, arm)
    if err:
        return {"ok": False, "reason": f"NO_CREDS: {err}"}
    pinned = mx.load_pinned_account(arm)
    arm_params = {**lane_params, "account": {"key_source": key_source, "account_number": pinned or ""}}
    try:
        creds = mc.resolve(arm_params)
        acct = mc.verify_account(creds)
        pos = mb.equity_option_positions(creds, allowed_roots=list(arm_cfg.get("universe") or []))
    except Exception as e:  # noqa: BLE001 -- broker/creds failure is a finding
        return {"ok": False, "reason": f"{type(e).__name__}: {e}"}
    return {"ok": True, "account_number": acct.get("account_number"), "equity": acct.get("equity"),
            "options_approved_level": acct.get("options_approved_level"),
            "open_option_positions": [{"symbol": p.get("symbol"), "qty": p.get("qty")} for p in pos]}


# --- verdicts --------------------------------------------------------------------------------
def _worse(a: str, b: str) -> str:
    return a if _RANK[a] >= _RANK[b] else b


def arm_verdict(phase: str, ledger: dict, day: dict, state: dict, broker: Optional[dict]) -> tuple:
    reasons: list = []
    v = GREEN
    dec = ledger.get("decisions") or {}
    if ledger.get("rows_today", 0) == 0:
        return RED, [f"DARK: no ledger rows today in {ledger.get('path')}"]
    if "INVARIANT_FAIL" in dec:
        v = RED
        reasons.append(f"INVARIANT_FAIL x{dec['INVARIANT_FAIL']}")
    if "ACCOUNT_PIN_MISMATCH" in dec:
        v = RED
        reasons.append(f"ACCOUNT_PIN_MISMATCH x{dec['ACCOUNT_PIN_MISMATCH']}")
    if set(dec) <= {"NO_CREDS"}:
        v = _worse(v, AMBER)
        reasons.append(f"NO_CREDS only ({dec.get('NO_CREDS')} ticks): waiting on the secrets paste")
    if "TICK_ERROR" in dec:
        v = _worse(v, AMBER)
        reasons.append(f"TICK_ERROR x{dec['TICK_ERROR']}")
    if phase == "eod":
        if broker and broker.get("ok"):
            open_pos = broker.get("open_option_positions") or []
            if open_pos:
                v = RED
                reasons.append(f"NOT_FLAT at broker: {open_pos}")
            elif state.get("records", 0) > 0:
                v = _worse(v, AMBER)
                reasons.append(f"state holds {state['records']} record(s) but broker is flat: "
                               f"{state['contracts']}")
        elif broker is not None:
            v = _worse(v, AMBER)
            reasons.append(f"broker flat-check unavailable: {broker.get('reason')}")
        if day.get("kill_tripped"):
            reasons.append("daily kill switch tripped (blocks new entries only)")
    return v, reasons


def lane_verdict(arms: dict) -> str:
    v = GREEN
    for a in arms.values():
        v = _worse(v, a["verdict"])
    return v


# --- writers ---------------------------------------------------------------------------------
def append_goal_log(goal_path: Path, line: str) -> None:
    s = goal_path.read_text(encoding="utf-8")
    if GOAL_LOG_ANCHOR in s:
        s = s.replace(GOAL_LOG_ANCHOR, line + "\n" + GOAL_LOG_ANCHOR, 1)
    else:
        s = s.rstrip("\n") + "\n" + line + "\n"
    goal_path.write_text(s, encoding="utf-8")


def _fmt_arm(name: str, a: dict) -> str:
    led, day, br = a["ledger"], a["day"], a.get("broker") or {}
    dec_items = list((led.get("decisions") or {}).items())[:4]
    top = ", ".join(f"{k}={v}" for k, v in dec_items) or "none"
    bits = [f"{name} {a['verdict']}: rows {led.get('rows_today', 0)} ({top})"]
    if day.get("exists"):
        bits.append(f"fills {day.get('fills')} pnl {day.get('realized_pnl_today')}")
    if br.get("ok"):
        n_open = len(br.get("open_option_positions") or [])
        bits.append(f"acct {br.get('account_number')} eq {br.get('equity')} "
                    f"lvl {br.get('options_approved_level')} open {n_open}")
    if a["reasons"]:
        bits.append("; ".join(a["reasons"]))
    return " | ".join(bits)


def run_check(lane_params: dict, phase: str, now: dt.datetime, *, goal_path: Path = GOAL_PATH,
              status_path: Path = STATUS_PATH, out_dir: Optional[Path] = None, dry_run: bool = False,
              broker_fn: Optional[Callable[[dict, str, dict], dict]] = broker_snapshot) -> dict:
    date_str = now.date().isoformat()
    arms_cfg = dict(lane_params.get("arms") or {})
    report: dict[str, Any] = {"date": date_str, "phase": phase,
                              "checked_at_et": now.isoformat(timespec="seconds"),
                              "arms": {}, "verdict": GREEN, "dry_run": dry_run}
    if now.weekday() >= 5:
        report["verdict"] = SKIP
        report["reason"] = "weekend: the lane's own invariants refuse to trade; nothing to check"
        return report
    for arm, cfg in arms_cfg.items():
        if str(arm).startswith("_") or not isinstance(cfg, dict):
            continue  # params.arms carries a _doc string; execute.py skips it the same way
        ledger = read_ledger_today(arm, date_str)
        day = read_day_file(arm, date_str)
        state = read_state(arm)
        broker = broker_fn(lane_params, arm, cfg) if broker_fn is not None else None
        v, reasons = arm_verdict(phase, ledger, day, state, broker)
        report["arms"][arm] = {"verdict": v, "reasons": reasons, "ledger": ledger, "day": day,
                               "state": state, "broker": broker}
    report["verdict"] = lane_verdict(report["arms"])
    if report["arms"] and all(set(a["ledger"].get("decisions") or {}) <= {"MARKET_CLOSED"}
                              and a["ledger"].get("rows_today", 0) > 0 for a in report["arms"].values()):
        report["verdict"] = SKIP  # holiday / early close: the executor said so on every arm
        report["reason"] = "MARKET_CLOSED on every arm"
        return report

    summary = "; ".join(_fmt_arm(n, a) for n, a in report["arms"].items()) or "no arms configured"
    ts = now.strftime("%Y-%m-%d %H:%M")
    goal_line = f"- {ts} ET -- [day-check/{phase}] {report['verdict']} :: {summary}"
    reason_bits = "; ".join(f"{n}: {', '.join(a['reasons'])}"
                            for n, a in report["arms"].items() if a["reasons"])
    status_line = (f"- [{ts} ET] TICKERS-DAY-CHECK {report['verdict']} :: {phase}: {reason_bits} "
                   "-- ledgers automation/state/tickers/<arm>/ledger.jsonl, runner log "
                   "automation/state/tickers/execute-last-run.log. Revoke: shadow_only:true in "
                   "automation/state/tickers/params.json.")
    report["goal_line"] = goal_line
    report["status_line"] = status_line if report["verdict"] == RED else None

    if not dry_run:
        out_dir = out_dir or mx.TICKERS_STATE_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"day-check-{date_str}-{phase}.json"
        out_path.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
        report["out_path"] = str(out_path)
        if goal_path.exists():
            append_goal_log(goal_path, goal_line)
        skb = _load_status_writer()
        skb.upsert(STATUS_MARKER, status_line if report["verdict"] == RED else None,
                   status_path=status_path)
    return report


def resolve_phase(phase: str, now: dt.datetime) -> str:
    if phase != "auto":
        return phase
    return "open" if now.time() < OPEN_PHASE_UNTIL_ET else "eod"


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phase", choices=["auto", "open", "eod"], default="auto")
    ap.add_argument("--params", default=str(mx.DEFAULT_PARAMS_PATH))
    ap.add_argument("--dry-run", action="store_true", help="compute + print, write nothing")
    ap.add_argument("--no-broker", action="store_true", help="skip the broker read (offline)")
    a = ap.parse_args(argv)
    lane_params = json.loads(Path(a.params).read_text(encoding="utf-8"))
    now = mx.now_et()
    phase = resolve_phase(a.phase, now)
    rep = run_check(lane_params, phase, now, dry_run=a.dry_run,
                    broker_fn=None if a.no_broker else broker_snapshot)
    print(json.dumps({k: v for k, v in rep.items() if k != "arms"}, indent=2, default=str))
    for n, arm in rep["arms"].items():
        print(f"  {_fmt_arm(n, arm)}")
    tail = f" -> {rep.get('out_path')}" if rep.get("out_path") else " (dry-run)"
    print(f"[tickers-day-check] {phase} {rep['verdict']}{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

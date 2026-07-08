"""fill_funnel.py -- the per-day FILL FUNNEL: ticks -> signals -> ENTER -> attempted
-> accepted -> filled -> exited, per account. Pure-ledger, $0, read-only.

THE INSTRUMENT THAT RETIRES "is it actually trading?" (OP-33e). 2026-07-01 ground
truth vs what the surfaces said: core-decisions had 766 rows / 10 ENTER_BEAR (all
PLACE_FAIL) and the fleet arms filled + exit-managed 4 ENTER_BULL at 11:22 -- yet
the EOD journal claimed "ENTER signals: 0" and loop-state said ticks_today=0.
Every number here is re-derived from the decision ledgers J can open himself:

  automation/state/core-decisions.jsonl          (heartbeat core: safe + bold)
  automation/state/fleet/<arm>/decisions.jsonl   (fleet arms; exit_pass rows carry
                                                  broker-truth fills + exit actions)

Funnel stage definitions (deterministic, no LLM):
  ticks      = rows for the day
  signals    = rows with a fired trigger OR a non-HOLD verdict/action
  enter      = verdict/action startswith ENTER
  attempted  = ENTER rows where a LIVE placement was actually tried
  accepted   = attempted rows whose broker response carries an order id
  filled     = distinct symbols with broker fill evidence (filled_qty>0 on the
               order, or an exit_pass row showing open_qty>0 at the broker)
  exited     = distinct filled symbols with a placed exit action (SELL_ALL/TP/...)

Verdict rules (shared by self_check + gamma_glance + guard tests):
  RED       any account with attempted>0 and accepted==0  (placement broken) --
            UNLESS every failed attempt carries bracket_err/oto_err, i.e. the
            retired bracket->oto->simple ladder produced it: the shipped
            _place_simple_entry code never emits those, so such a day is PROVABLY
            pre-fix history (DEGRADED "PLACEMENT PRE-FIX ARTIFACT", not a live RED).
  DEGRADED  any ENTER after the 15:00 ET entry ceiling; a pre-fix retired-ladder
            placement day; or (at/after EOD) a fill with no exit record
  GREEN     ENTER>0 and none of the above
  IDLE      no ENTER fired (not a fault by itself)

CLI:  backtest/.venv/Scripts/python.exe setup/scripts/fill_funnel.py [--date YYYY-MM-DD] [--write]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
sys.path.insert(0, str(REPO / "setup" / "scripts"))

try:
    from et_clock import et_now
except Exception:  # noqa: BLE001
    def et_now() -> dt.datetime:  # fail-open (rig is on Mountain; never Bash TZ)
        return dt.datetime.utcnow() - dt.timedelta(hours=4)

ENTRY_CEILING_HHMM = "15:00"   # ENTER after this = DEGRADED (0DTE theta cliff)
EOD_HHMM = "16:00"             # after this, a fill with no exit record = DEGRADED

# FALSE-RED FIX (2026-07-07): a CORE ENTER row's exec dict is TRUTHY for every
# outcome -- including pure-skip statuses that NEVER call the broker (NOT_FLAT,
# SKIP_*). Counting those as `attempted` made a flat-veto day (already holding a
# position -> NOT_FLAT) read as attempted>0 & accepted==0 -> a false "PLACEMENT
# BROKEN" RED that reached gamma_glance + self_check while the broker was never
# touched. `attempted` now requires a status that is a REAL placement OUTCOME:
# the order was sent (PLACED / a broker reject in PLACE_FAIL) or it died at the
# last pre-broker sizing/pricing/risk gate that is genuinely PART of the placement
# attempt (NO_PREMIUM). A skip that bails BEFORE that (NOT_FLAT and
# every SKIP_*) is NOT a placement attempt. Anything unrecognized fails OPEN to
# "attempted" so a NEW real-fault status can never be silently swallowed.
#
# SECOND FALSE-RED FIX (2026-07-08): RISK_DENY_* was counted as `attempted`,
# so a PDT-jail day (13 ENTER, all correctly refused by the risk gate) read as
# attempted>0 & accepted==0 -> "PLACEMENT BROKEN" spam to Discord while Rule 7
# was doing its job. RISK_DENY_* is now its own funnel stage: `rule_blocked`,
# with its own informational flag -- disclosed, never RED (guard:
# test_fill_funnel_guard.py::test_risk_deny_is_rule_block_not_broken).
_CORE_ATTEMPT_STATUSES = frozenset({
    "PLACED", "PLACE_FAIL", "PLACING", "NO_PREMIUM",
})
# statuses that are provably a skip BEFORE any broker interaction -> never attempted
_CORE_SKIP_STATUSES = frozenset({
    "NOT_FLAT", "NO_CREDS", "EQUITY_FETCH_FAIL", "WOULD_PLACE",
})


def _core_is_rule_block(status: str) -> bool:
    """True iff the exec status is the risk gate REFUSING the entry (RISK_DENY_*:
    PDT, per-trade cap, kill switch...). That is rule ENFORCEMENT working, not a
    placement fault -- counted in its own `rule_blocked` stage."""
    return (status or "").upper().startswith("RISK_DENY")


def _core_is_attempt(status: str) -> bool:
    """True iff a CORE exec status represents a real placement OUTCOME (the broker
    was called OR the attempt died at the last in-placement gate). NOT_FLAT and
    every SKIP_* bail before the broker and are NOT attempts; RISK_DENY_* is a
    rule-block, not an attempt. Fail-OPEN: an unrecognized status counts as an
    attempt so a genuinely-broken new status still trips the RED (OP-33)."""
    s = (status or "").upper()
    if s in _CORE_ATTEMPT_STATUSES:
        return True
    if s in _CORE_SKIP_STATUSES or s.startswith("SKIP_") or _core_is_rule_block(s):
        return False
    return True  # unknown status -> fail open (never hide a possible real fault)


# ---------------------------------------------------------------------------
# ledger readers
# ---------------------------------------------------------------------------

def _read_jsonl_day(path: Path, day: str) -> list[dict]:
    """JSONL rows whose ts_et starts with the day. Fail-open -> []."""
    rows: list[dict] = []
    try:
        for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
            ln = ln.strip()
            if not ln or day not in ln:
                continue
            try:
                o = json.loads(ln)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(o, dict) and str(o.get("ts_et", "")).startswith(day):
                rows.append(o)
    except OSError:
        pass
    return rows


def _hhmm(ts_et: str) -> str:
    """'2026-07-01T15:51:02' or '...T11:22:01.4-04:00' -> '15:51' / '11:22'."""
    return ts_et.split("T", 1)[1][:5] if "T" in ts_et else ""


def _fail_reason(broker: dict) -> str:
    """Verbatim broker rejection text (the PLACE_FAIL truth J needs to see)."""
    if not broker:
        return "no broker response recorded"
    msgs: list[str] = []
    if broker.get("_error"):
        msgs.append(str(broker["_error"]))
    for k in ("bracket_err", "oto_err", "simple_err"):
        e = broker.get(k)
        if isinstance(e, dict):
            body = e.get("_body") if isinstance(e.get("_body"), dict) else e
            m = (body or {}).get("message") or e.get("message")
            if m:
                msgs.append(f"{k}: {m}")
        elif e:
            msgs.append(f"{k}: {e}")
    return " | ".join(msgs) if msgs else "unknown (no error detail in ledger)"


# ---------------------------------------------------------------------------
# per-account funnel
# ---------------------------------------------------------------------------

def _acct_funnel(rows: list[dict], kind: str) -> dict:
    """Fold one account's day rows into funnel stages. kind: 'core' | 'fleet'."""
    f = {
        "ticks": len(rows), "signals": 0, "enter": 0, "rule_blocked": 0,
        "attempted": 0,
        "accepted": 0, "filled": 0, "exited": 0, "retired_ladder_fails": 0,
        "enter_events": [], "place_fail_reasons": [], "rule_block_reasons": [],
        "enters_after_ceiling": [], "open_fills_no_exit": [],
    }
    filled_syms: set[str] = set()
    exited_syms: set[str] = set()
    for r in rows:
        v = str((r.get("verdict") if kind == "core" else r.get("action")) or "")
        if r.get("triggers") or (v and v != "HOLD"):
            f["signals"] += 1
        # exit_pass rows carry broker-truth: open_qty>0 = we HOLD a fill;
        # a placed action (SELL_ALL / tp / stop) = the exit went to the broker.
        for ep in (r.get("exit_pass") or []):
            sym = ep.get("symbol")
            if not sym:
                continue
            try:
                if float(ep.get("open_qty") or 0) > 0:
                    filled_syms.add(sym)
            except (TypeError, ValueError):
                pass
            for a in (ep.get("actions") or []):
                if a.get("placed"):
                    exited_syms.add(sym)
        if not v.startswith("ENTER"):
            continue
        f["enter"] += 1
        ex = (r.get("exec") if kind == "core" else r.get("placement")) or {}
        broker = ex.get("broker") or {}
        rule_blocked = False
        if kind == "core":
            # only count a CORE ENTER as attempted when its exec status is a REAL
            # placement outcome -- NOT_FLAT / SKIP_* bail before the broker (they
            # were falsely counted, tripping a phantom PLACEMENT BROKEN RED);
            # RISK_DENY_* is rule enforcement -> its own stage, never an attempt.
            st = str(ex.get("status", ""))
            rule_blocked = bool(ex) and _core_is_rule_block(st)
            attempted = bool(ex) and _core_is_attempt(st)
        else:
            attempted = bool(ex) and str(ex.get("mode", "LIVE")).upper() == "LIVE"
        accepted = bool(broker.get("id"))
        if rule_blocked:
            f["rule_blocked"] += 1
            f["rule_block_reasons"].append(str(ex.get("reason") or ex.get("status") or "risk gate deny"))
        if attempted:
            f["attempted"] += 1
        if accepted:
            f["accepted"] += 1
        elif attempted:
            f["place_fail_reasons"].append(_fail_reason(broker))
            # A rejection carrying bracket_err/oto_err was produced by the RETIRED
            # bracket->oto->simple ladder. The shipped _place_simple_entry path emits
            # only simple_err/_error (no order_class), so such an attempt is PROVABLY
            # pre-fix history, not a live fault -- and the code invariant is guarded
            # build-side (test_money_path_2026_07_01: AST test_no_place_bracket_call_*
            # + behavioral test_execute_first_and_only_order_call_is_simple_marketable),
            # so a regression re-adding the ladder REDs at build before it reaches here.
            if broker.get("bracket_err") or broker.get("oto_err"):
                f["retired_ladder_fails"] += 1
        # fill evidence on the entry order itself
        sym = ex.get("symbol") or broker.get("symbol")
        try:
            entry_filled = float(broker.get("filled_qty") or 0) > 0
        except (TypeError, ValueError):
            entry_filled = False
        if sym and (entry_filled or broker.get("filled_at")):
            filled_syms.add(sym)
        hhmm = _hhmm(str(r.get("ts_et", "")))
        ev = {
            "ts_et": r.get("ts_et"), "hhmm": hhmm, "verdict": v,
            "setup": r.get("setup") or r.get("setup_name"),
            "symbol": sym, "qty": ex.get("qty") or r.get("qty"),
            "status": ("ACCEPTED" if accepted
                       else (str(ex.get("status") or "PLACE_FAIL")
                             if (attempted or rule_blocked) else "NOT_ATTEMPTED")),
            "order_id": broker.get("id"),
            "reason": r.get("reason"),
        }
        f["enter_events"].append(ev)
        if hhmm and hhmm > ENTRY_CEILING_HHMM:
            f["enters_after_ceiling"].append(f"{hhmm} {v} {sym or '?'}")
    f["filled"] = len(filled_syms)
    f["exited"] = len(filled_syms & exited_syms)
    f["open_fills_no_exit"] = sorted(filled_syms - exited_syms)
    return f


# ---------------------------------------------------------------------------
# whole-day funnel + evaluation
# ---------------------------------------------------------------------------

_STAGES = ("ticks", "signals", "enter", "rule_blocked", "attempted", "accepted", "filled", "exited")


def compute_funnel(day: str | None = None, *, core_path: Path | None = None,
                   fleet_dir: Path | None = None, now: dt.datetime | None = None) -> dict:
    """Compute the per-day funnel. All inputs overridable for tests. Fail-open."""
    now = now or et_now()
    day = day or now.strftime("%Y-%m-%d")
    core_path = core_path or (STATE / "core-decisions.jsonl")
    fleet_dir = fleet_dir or (STATE / "fleet")

    accounts: dict[str, dict] = {}
    core_rows = _read_jsonl_day(core_path, day)
    for acct in sorted({str(r.get("account") or "core") for r in core_rows}):
        accounts[f"core:{acct}"] = _acct_funnel(
            [r for r in core_rows if str(r.get("account") or "core") == acct], "core")
    try:
        arm_files = sorted(fleet_dir.glob("*/decisions.jsonl"))
    except OSError:
        arm_files = []
    for p in arm_files:
        rows = _read_jsonl_day(p, day)
        if rows:
            accounts[f"fleet:{p.parent.name}"] = _acct_funnel(rows, "fleet")

    totals = {s: sum(a[s] for a in accounts.values()) for s in _STAGES}
    funnel = {
        "date": day,
        "generated_at_et": now.strftime("%Y-%m-%dT%H:%M:%S"),
        "accounts": accounts,
        "totals": totals,
        "sources": {"core": str(core_path), "fleet": str(fleet_dir)},
    }
    funnel["flags"], funnel["verdict"] = _evaluate(funnel, now)
    return funnel


def _evaluate(funnel: dict, now: dt.datetime) -> tuple[list[str], str]:
    """Shared verdict rules -- see module docstring."""
    flags: list[str] = []
    red = False
    day = funnel["date"]
    at_eod = (now.strftime("%Y-%m-%d") > day) or (
        now.strftime("%Y-%m-%d") == day and now.strftime("%H:%M") >= EOD_HHMM)
    for name, a in funnel["accounts"].items():
        if a.get("rule_blocked", 0):
            reasons = Counter(a.get("rule_block_reasons", []))
            top = "; ".join(f"{n}x {r[:120]}" for r, n in reasons.most_common(2))
            flags.append(f"RULE-BLOCKED[{name}]: {a['rule_blocked']} ENTER refused by the risk "
                         f"gate (rule enforcement working, NOT a placement fault): {top}")
        if a["attempted"] > 0 and a["accepted"] == 0:
            reasons = Counter(a["place_fail_reasons"])
            top = "; ".join(f"{n}x {r[:120]}" for r, n in reasons.most_common(2))
            if a.get("retired_ladder_fails", 0) == a["attempted"]:
                # EVERY failed attempt used the retired bracket/oto ladder -> this day is
                # pre-fix history (current code is simple-first). DEGRADED, not a live RED:
                # surfaced for J's visibility but does not falsely flag placement dead.
                flags.append(f"PLACEMENT PRE-FIX ARTIFACT[{name}]: {a['attempted']} attempted via the "
                             f"retired bracket/oto ladder (current code is simple-first) -- stale pre-fix "
                             f"decisions, not a live fault. Reasons: {top}")
            else:
                red = True
                flags.append(f"PLACEMENT BROKEN[{name}]: {a['enter']} ENTER, "
                             f"{a['attempted']} attempted, 0 broker-accepted. Reasons: {top}")
        if a["enters_after_ceiling"]:
            flags.append(f"ENTER AFTER CEILING[{name}]: {len(a['enters_after_ceiling'])} ENTER "
                         f"after {ENTRY_CEILING_HHMM} ET: {a['enters_after_ceiling'][:3]}")
        if at_eod and a["open_fills_no_exit"]:
            flags.append(f"FILL WITHOUT EXIT AT EOD[{name}]: {a['open_fills_no_exit']} "
                         f"filled but no exit record in the ledger.")
    if red:
        return flags, "RED"
    if flags:
        return flags, "DEGRADED"
    return flags, ("GREEN" if funnel["totals"]["enter"] > 0 else "IDLE")


# ---------------------------------------------------------------------------
# trades-CSV P&L (deterministic; feeds the EOD quant section)
# ---------------------------------------------------------------------------

def _trades_today(csv_path: Path, day: str, default_header: list[str] | None = None) -> list[dict]:
    """Today's rows from a trades CSV. Tolerates a headerless file (trades-aggressive)."""
    import csv as _csv
    out: list[dict] = []
    if not csv_path.exists():
        return out
    try:
        with open(csv_path, encoding="utf-8-sig", newline="") as fh:
            rdr = _csv.reader(fh)
            rows = [r for r in rdr if r]
    except OSError:
        return out
    if not rows:
        return out
    if rows[0] and rows[0][0].strip().lower() == "date":
        header, data = rows[0], rows[1:]
    else:
        header, data = (default_header or []), rows
    for r in data:
        if not r or not r[0].startswith(day):
            continue
        d = {header[i].strip(): r[i] for i in range(min(len(header), len(r)))} if header else {}
        d["_raw"] = r
        out.append(d)
    return out


_TRADES_HEADER = ["date", "time_entry", "time_exit", "setup", "contract", "dte", "strike",
                  "c_or_p", "qty", "entry_px", "exit_px", "premium_paid", "premium_received",
                  "dollar_pnl"]


def _pnl_statement_today(day: str, repo: Path) -> "dict | None":
    """T1 broker-truth per-day P&L (setup/scripts/broker_fills.py's pnl-statement.json), or
    None if that file doesn't exist yet or has no entry for this day."""
    path = repo / "automation" / "state" / "pnl-statement.json"
    if not path.exists():
        return None
    try:
        stmt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return stmt.get("per_day", {}).get(day) or None


def trades_pnl_today(day: str, repo: Path | None = None) -> dict:
    """P&L truth for the day. PRIMARY SOURCE (T2 rewire, HANDOFF-2026-07-09-TRUTH-AND-EXITS,
    ground rule 2): setup/scripts/broker_fills.py's automation/state/pnl-statement.json --
    Alpaca /account/activities/FILL, broker-truth. journal/trades.csv is used ONLY as a
    fallback when T1 has no entry for this day (e.g. Gamma_BrokerFills hasn't fired yet for
    a historical date) -- it is never the primary source, since it depends on a separate,
    less-reliable EOD reconciliation workflow."""
    repo = repo or REPO
    per_day = _pnl_statement_today(day, repo)
    if per_day:
        by_arm = []
        total = 0.0
        for arm, stats in sorted(per_day.items()):
            total += stats.get("realized_pnl", 0.0)
            by_arm.append({"arm": arm, "n_round_trips": stats.get("n_round_trips", 0),
                           "realized_pnl": stats.get("realized_pnl", 0.0),
                           "engine_pnl": stats.get("engine_pnl", 0.0),
                           "manual_pnl": stats.get("manual_pnl", 0.0)})
        return {"by_arm": by_arm, "total_pnl": round(total, 2),
                "source": "pnl-statement.json (T1, broker-truth)"}

    out = {"safe": [], "aggressive": [], "total_pnl": 0.0,
           "source": "journal/trades.csv (T1 fallback -- no pnl-statement.json entry for this day)"}
    for label, fname in (("safe", "trades.csv"), ("aggressive", "trades-aggressive.csv")):
        for t in _trades_today(repo / "journal" / fname, day, default_header=_TRADES_HEADER):
            pnl = 0.0
            try:
                pnl = float(t.get("dollar_pnl") or t["_raw"][13])
            except (KeyError, IndexError, TypeError, ValueError):
                pass
            out[label].append({
                "setup": t.get("setup") or (t["_raw"][3] if len(t["_raw"]) > 3 else "?"),
                "contract": t.get("contract") or (t["_raw"][4] if len(t["_raw"]) > 4 else "?"),
                "qty": t.get("qty") or (t["_raw"][8] if len(t["_raw"]) > 8 else "?"),
                "time_entry": t.get("time_entry") or (t["_raw"][1] if len(t["_raw"]) > 1 else "?"),
                "time_exit": t.get("time_exit") or (t["_raw"][2] if len(t["_raw"]) > 2 else "?"),
                "pnl": pnl,
            })
            out["total_pnl"] += pnl
    return out


# ---------------------------------------------------------------------------
# renderers + artifact
# ---------------------------------------------------------------------------

def render_text(funnel: dict) -> str:
    """One glanceable block (gamma_glance / CLI)."""
    t = funnel["totals"]
    out = [f"FUNNEL {funnel['date']}  [{funnel['verdict']}]  "
           f"ticks->sig->ENTER->ruleblk->attempt->accept->fill->exit"]
    for name, a in funnel["accounts"].items():
        out.append(f"  {name:<14} {a['ticks']:>4} -> {a['signals']:>3} -> {a['enter']:>2} "
                   f"-> {a.get('rule_blocked', 0):>2} -> {a['attempted']:>2} -> {a['accepted']:>2} "
                   f"-> {a['filled']:>2} -> {a['exited']:>2}")
    out.append(f"  {'TOTAL':<14} {t['ticks']:>4} -> {t['signals']:>3} -> {t['enter']:>2} "
               f"-> {t.get('rule_blocked', 0):>2} -> {t['attempted']:>2} -> {t['accepted']:>2} "
               f"-> {t['filled']:>2} -> {t['exited']:>2}")
    for fl in funnel["flags"]:
        out.append(f"  ! {fl}")
    return "\n".join(out)


def render_markdown(funnel: dict, repo: Path | None = None) -> str:
    """The deterministic QUANT section for the EOD digest/journal. Every number
    here is computed from the ledgers -- never LLM-generated (OP-33a)."""
    day = funnel["date"]
    t = funnel["totals"]
    pnl = trades_pnl_today(day, repo=repo)
    out = [
        "## Quantitative (deterministic -- computed from ledgers, not LLM)",
        "",
        f"Source ledgers: `core-decisions.jsonl` + `fleet/*/decisions.jsonl` + trades CSVs. "
        f"Generated {funnel['generated_at_et']} ET. Funnel verdict: **{funnel['verdict']}**.",
        "",
        "| account | ticks | signals | ENTER | rule-blocked | attempted | accepted | filled | exited |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, a in funnel["accounts"].items():
        out.append(f"| {name} | {a['ticks']} | {a['signals']} | {a['enter']} | "
                   f"{a.get('rule_blocked', 0)} | "
                   f"{a['attempted']} | {a['accepted']} | {a['filled']} | {a['exited']} |")
    out.append(f"| **TOTAL** | {t['ticks']} | {t['signals']} | {t['enter']} | "
               f"{t.get('rule_blocked', 0)} | "
               f"{t['attempted']} | {t['accepted']} | {t['filled']} | {t['exited']} |")
    # ENTER events with times + verdicts
    events = [(name, ev) for name, a in funnel["accounts"].items() for ev in a["enter_events"]]
    out.append("")
    out.append(f"**ENTER events ({len(events)}):**")
    if events:
        for name, ev in sorted(events, key=lambda x: str(x[1].get("ts_et"))):
            out.append(f"- {ev['hhmm']} ET [{name}] {ev['verdict']} {ev.get('symbol') or '?'} "
                       f"x{ev.get('qty') or '?'} -> {ev['status']}"
                       + (f" (order {str(ev['order_id'])[:8]})" if ev.get("order_id") else "")
                       + (f" -- {ev['reason']}" if ev.get("reason") else ""))
    else:
        out.append("- none")
    # PLACE_FAIL reasons verbatim
    fails = Counter()
    for a in funnel["accounts"].values():
        for r in a["place_fail_reasons"]:
            fails[r] += 1
    out.append("")
    out.append("**PLACE_FAIL reasons (verbatim from broker):**")
    if fails:
        for r, n in fails.most_common():
            out.append(f"- {n}x {r}")
    else:
        out.append("- none")
    # flags
    out.append("")
    out.append("**Funnel flags:**")
    out.extend([f"- {fl}" for fl in funnel["flags"]] or ["- none"])
    # P&L -- broker-truth (T1) unless flagged as the CSV fallback
    out.append("")
    out.append(f"**P&L (source: {pnl.get('source', 'unknown')}):**")
    any_trade = False
    if "by_arm" in pnl:
        for r in pnl["by_arm"]:
            any_trade = True
            out.append(f"- [{r['arm']}] {r['n_round_trips']} round trip(s): "
                       f"{r['realized_pnl']:+.0f} (engine {r['engine_pnl']:+.0f} / "
                       f"manual {r['manual_pnl']:+.0f})")
    else:
        for label in ("safe", "aggressive"):
            for tr in pnl.get(label, []):
                any_trade = True
                out.append(f"- [{label}] {tr['setup']} {tr['contract']} x{tr['qty']} "
                           f"{tr['time_entry']}->{tr['time_exit']} ET: {tr['pnl']:+.0f}")
    if not any_trade:
        out.append("- no P&L rows for this day")
    out.append(f"- **Total recorded P&L: {pnl['total_pnl']:+.0f}**")
    out.append("")
    return "\n".join(out)


def write_artifact(funnel: dict, state_dir: Path | None = None) -> Path | None:
    """Persist the funnel JSON so J (and the dashboard) can glance at it. Fail-open."""
    state_dir = state_dir or STATE
    p = state_dir / f"fill-funnel-{funnel['date']}.json"
    try:
        p.write_text(json.dumps(funnel, indent=1), encoding="utf-8")
        return p
    except OSError:
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description="Per-day fill funnel from decision ledgers")
    ap.add_argument("--date", default=None, help="ET date YYYY-MM-DD (default today)")
    ap.add_argument("--write", action="store_true", help="also write automation/state/fill-funnel-{date}.json")
    ap.add_argument("--markdown", action="store_true", help="print the EOD quant markdown instead of the table")
    args = ap.parse_args()
    f = compute_funnel(args.date)
    print(render_markdown(f) if args.markdown else render_text(f))
    if args.write:
        p = write_artifact(f)
        print(f"[fill-funnel] wrote {p}" if p else "[fill-funnel] WARN artifact write failed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

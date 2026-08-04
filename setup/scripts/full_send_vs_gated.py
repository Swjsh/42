"""full_send_vs_gated.py -- the standing FULL-SEND vs GATED comparison query
                            + the WEEKLY risky-vs-safes MARGINAL-COHORT instrument.

WHY THIS EXISTS: the full-send arm (risky-1, armed 2026-07-31) only earns its keep if we
LEARN from it. Its whole justification is LEARNING RATE, not P&L -- so "how many more fills
did the loose arm take than the gated arms, on the IDENTICAL signal, and what did that cost"
must be a QUERY, not a research project. Per OP-33: visibility is the product.

WHAT IT ANSWERS, per trading day and per arm:
  * ticks evaluated, ENTERs produced, orders actually placed
  * WHICH LANE produced each entry (normal / FULL_SEND / PROBE_ARM / SCORE_LADDER)
  * the blocker cascade -- exactly what stopped the arm on every non-entering tick
  * same-tick comparison: on ticks where the full-send arm entered, what did each gated arm do

MARGINAL COHORT (RISKY3-SPECULATIVE lane, 2026-08-04 -- J's week directive: "risky-3 is
getting in speculative trades that safe-1 and safe-2 are not getting in -- that's the
entire point of the risky account"): for each RISK-tier fleet arm, every PLACED entry
where NEITHER safe-3 (fleet tight) NOR core safe-2 placed the same minute -- joined to
its REAL closed round-trip P&L (fills_fifo FIFO, the same single implementation
fleet_arm_replay anchors against). The weekly headline J never has to ask for:
"risky-3 took N trades the safes did not; that cohort paid $X."

CORE-SAFE COUNTING (L244 -- wall #5 of EOD-2026-08-03: three counters were blind to
extra_exec entries): a core row counts as an entry if its top-level action is ENTER_*
OR any element of its extra_exec LIST (it is a list of per-setup dicts, NOT a dict)
has action == "PLACED". Guard: backtest/tests/test_risky_divergence_weekly_2026_08_04.py.

$0, offline, read-only on trading state -- --weekly writes ONLY report artifacts under
analysis/fleet-weekly/. Run:
    python setup/scripts/full_send_vs_gated.py               # today
    python setup/scripts/full_send_vs_gated.py 2026-07-31    # a specific ET date
    python setup/scripts/full_send_vs_gated.py --since 2026-07-01
    python setup/scripts/full_send_vs_gated.py --weekly      # last 5 sessions + artifact
Scheduled: Gamma_RiskyDivergenceWeekly (Sun 15:00 MT = 17:00 ET) runs --weekly.
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
FLEET = REPO / "automation" / "state" / "fleet"
if str(FLEET) not in sys.path:
    sys.path.insert(0, str(FLEET))
ACCOUNTS = FLEET / "accounts.json"
CORE_DECISIONS = REPO / "automation" / "state" / "core-decisions.jsonl"
WEEKLY_OUT_DIR = REPO / "analysis" / "fleet-weekly"

LANE_TAGS = (("FULL_SEND", "FULL_SEND"), ("PROBE_ARM", "PROBE"), ("SCORE_LADDER", "LADDER"))


def _et_today() -> str:
    from et_clock import et_now
    return et_now().strftime("%Y-%m-%d")


def _arms() -> list[dict]:
    acc = json.loads(ACCOUNTS.read_text(encoding="utf-8"))
    return [a for a in acc.get("arms", [])
            if a.get("status") == "active" and a.get("execution") == "fleet_rest"]


def _lane(reason: str) -> str:
    for needle, tag in LANE_TAGS:
        if str(reason).startswith(needle):
            return tag
    return "normal"


def _blocker(row: dict) -> str:
    """One canonical label for why this tick produced no order."""
    if row.get("action") != "HOLD":
        return "ENTERED"
    code = row.get("risk_code")
    if code:
        return code
    reason = str(row.get("reason") or "")
    if reason.startswith("gate:"):
        return "ARM_GATE"
    if "no qualifying setup" in reason:
        return "NO_SIGNAL_FROM_PRODUCER"
    if "no live signal" in reason:
        return "NO_LIVE_SIGNAL"
    return reason[:40] or "UNKNOWN"


def load(arm_id: str, day: str | None, since: str | None) -> list[dict]:
    p = FLEET / arm_id / "decisions.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = str(r.get("ts_et") or "")[:10]
        if day and ts != day:
            continue
        if since and ts < since:
            continue
        out.append(r)
    return out


# --- MARGINAL COHORT (RISKY3-SPECULATIVE lane, 2026-08-04) --------------------------------
def _minute(ts) -> str:
    return str(ts)[:16]


def load_core_safe_entry_minutes(days: set[str], path: Path = CORE_DECISIONS) -> dict[str, str]:
    """{minute -> tag} for every core SAFE row that actually entered: top-level ENTER_* OR
    an extra_exec LIST element with action=='PLACED' (L244 shape-correct parse)."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        ts = r.get("ts_et") or r.get("timestamp_et") or ""
        if str(ts)[:10] not in days or str(r.get("account", "")).lower() != "safe":
            continue
        tag = None
        if str(r.get("action") or "").startswith("ENTER"):
            tag = "core_enter"
        else:
            for xe in (r.get("extra_exec") or []):
                if isinstance(xe, dict) and str(xe.get("action")) == "PLACED":
                    tag = f"extra_exec:{xe.get('setup')}"
                    break
        if tag:
            out[_minute(ts)] = tag
    return out


def _real_pnl_by_symbol(arm_id: str, days: set[str]) -> dict[str, list[dict]]:
    """symbol -> closed FIFO round trips (real fills) in the window, via fills_fifo --
    the SAME single implementation fleet_arm_replay anchors against (C14)."""
    import fills_fifo
    out: dict[str, list[dict]] = {}
    # ledger_path passed EXPLICITLY from the module attribute (not the def-time default)
    # so a test can monkeypatch fills_fifo.FILLS_LEDGER_PATH -- byte-identical in prod.
    for t in fills_fifo.mine_real_arm_fills(arm_id, ledger_path=fills_fifo.FILLS_LEDGER_PATH):
        if t["date"] in days:
            out.setdefault(t["symbol"], []).append(t)
    return out


def marginal_cohort(days: set[str]) -> dict:
    """Every RISK-tier fleet arm's placed entries where NEITHER safe-3 (same minute) NOR
    core safe-2 (same minute, extra_exec-aware) placed -- joined to real closed P&L."""
    arms = {a["id"]: a for a in _arms()}
    risk_ids = sorted(i for i in arms if i.startswith("risky"))
    safe3_rows = load("safe-3", None, None)
    safe3_placed_minutes = {_minute(r.get("ts_et")) for r in safe3_rows
                            if str(r.get("ts_et", ""))[:10] in days
                            and (r.get("placement") or {}).get("placed")}
    core_minutes = load_core_safe_entry_minutes(days)
    result: dict = {"days": sorted(days), "arms": {}}
    for rid in risk_ids:
        rows = [r for r in load(rid, None, None) if str(r.get("ts_et", ""))[:10] in days]
        placed = [r for r in rows if (r.get("placement") or {}).get("placed")]
        pnl_by_sym = _real_pnl_by_symbol(rid, days)
        entries = []
        for r in placed:
            m = _minute(r.get("ts_et"))
            sym = (r.get("placement") or {}).get("symbol")
            trips = pnl_by_sym.get(sym) or []
            # symbol is date-scoped; multiple same-day round trips are summed for the row
            # (attribution note rides along when >1 trip matched).
            pnl = round(sum(t["real_pnl"] for t in trips), 2) if trips else None
            entries.append({
                "ts_et": r.get("ts_et"), "minute": m, "symbol": sym,
                "strategy": r.get("reason", "").split(" ")[0] or None,
                "lane": _lane(r.get("reason")), "quality": r.get("quality"),
                "qty": r.get("qty"), "premium": r.get("premium"),
                "safe3_same_minute": m in safe3_placed_minutes,
                "core_safe_same_minute": core_minutes.get(m),
                "marginal": (m not in safe3_placed_minutes) and (m not in core_minutes),
                "real_pnl_closed": pnl,
                "n_round_trips_matched": len(trips),
            })
        marg = [e for e in entries if e["marginal"]]
        marg_pnl = round(sum(e["real_pnl_closed"] or 0.0 for e in marg), 2)
        result["arms"][rid] = {
            "placed": len(entries),
            "marginal_n": len(marg),
            "marginal_closed_pnl": marg_pnl,
            "marginal_unresolved": sum(1 for e in marg if e["real_pnl_closed"] is None),
            "entries": entries,
        }
    return result


def print_marginal(mc: dict) -> None:
    print("\nMARGINAL COHORT -- risk-arm entries NEITHER safe-3 nor core safe-2 took "
          "(same-minute; core count is extra_exec-aware, L244)")
    print("-" * 86)
    for rid, blk in mc["arms"].items():
        print(f"  {rid}: placed={blk['placed']}  MARGINAL n={blk['marginal_n']} "
              f"closed pnl=${blk['marginal_closed_pnl']:+.2f}"
              + (f"  ({blk['marginal_unresolved']} unresolved/open)" if blk["marginal_unresolved"] else ""))
        for e in blk["entries"]:
            if not e["marginal"]:
                continue
            pnl = "open/unmatched" if e["real_pnl_closed"] is None else f"${e['real_pnl_closed']:+.2f}"
            print(f"     {e['minute']} {e['symbol']} q={e['qty']} {e['strategy']} "
                  f"[{e['lane']}/{e['quality']}] -> {pnl}")


def last_n_session_days(n: int = 5, arm_id: str = "risky-3") -> set[str]:
    """The last n distinct WEEKDAY ET dates present in the arm's ledger.

    WEEKDAY filter is load-bearing (caught live 2026-08-04 building this): risky-3's
    ledger contains Saturday 2026-08-01 rows (a weekend fire wrote ticks), and a naive
    distinct-dates read counted that non-session, silently dropping the oldest real
    session from the window. Weekday-only matches the fleet's own fire schedule
    (09:30-15:55 ET weekdays); a weekday holiday can only appear if a ledger actually
    wrote rows that day, which the schedule precludes."""
    dates = set()
    for r in load(arm_id, None, None):
        d = str(r.get("ts_et", ""))[:10]
        if not d:
            continue
        try:
            if _dt.date.fromisoformat(d).weekday() < 5:
                dates.add(d)
        except ValueError:
            continue
    return set(sorted(dates)[-n:])


def write_weekly_artifact(mc: dict) -> Path:
    WEEKLY_OUT_DIR.mkdir(parents=True, exist_ok=True)
    today = _et_today()
    jpath = WEEKLY_OUT_DIR / f"risky-divergence-{today}.json"
    jpath.write_text(json.dumps(mc, indent=1), encoding="utf-8")
    lines = [f"# Risky-vs-safes weekly divergence -- {today}", "",
             f"Window (sessions): {', '.join(mc['days'])}", "",
             "One line per J's ask: how many trades did each risk arm take that the safes "
             "did not, and what did that cohort pay (REAL closed fills, FIFO).", ""]
    for rid, blk in mc["arms"].items():
        lines.append(f"## {rid}: took **{blk['marginal_n']}** trades the safes did not; "
                     f"that cohort paid **${blk['marginal_closed_pnl']:+.2f}**"
                     + (f" ({blk['marginal_unresolved']} still open/unmatched)"
                        if blk["marginal_unresolved"] else ""))
        lines.append("")
        lines.append("| minute | symbol | qty | strategy | lane | quality | real P&L |")
        lines.append("|---|---|---|---|---|---|---|")
        for e in blk["entries"]:
            if not e["marginal"]:
                continue
            pnl = "open" if e["real_pnl_closed"] is None else f"${e['real_pnl_closed']:+.2f}"
            lines.append(f"| {e['minute']} | {e['symbol']} | {e['qty']} | {e['strategy']} "
                         f"| {e['lane']} | {e['quality']} | {pnl} |")
        lines.append("")
    lines.append("_Source: setup/scripts/full_send_vs_gated.py --weekly "
                 "(Gamma_RiskyDivergenceWeekly). Real-fill P&L via fills_fifo (the same "
                 "FIFO fleet_arm_replay anchors against). Core-safe counting is "
                 "extra_exec-aware (L244)._")
    mpath = WEEKLY_OUT_DIR / f"risky-divergence-{today}.md"
    mpath.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return mpath


def main() -> int:
    args = [a for a in sys.argv[1:]]
    since = None
    day = None
    weekly = "--weekly" in args
    if weekly:
        args = [a for a in args if a != "--weekly"]
        days = last_n_session_days(5)
        since = min(days)
    elif "--since" in args:
        since = args[args.index("--since") + 1]
    elif args:
        day = args[0]
    else:
        day = _et_today()

    arms = _arms()
    fs_ids = [a["id"] for a in arms if (a.get("gate_override") or {}).get("full_send")]
    scope = f"day={day}" if day else f"since={since}"
    print(f"\nFULL-SEND vs GATED  ({scope})")
    print(f"full-send arm(s): {fs_ids or 'NONE ARMED'}   gated: "
          f"{[a['id'] for a in arms if a['id'] not in fs_ids]}\n")

    rows_by_arm: dict[str, list[dict]] = {}
    print(f"{'arm':<10} {'label':<22} {'ticks':>6} {'ENTER':>6} {'placed':>7}  lanes")
    print("-" * 86)
    for a in arms:
        rid = a["id"]
        rows = load(rid, day, since)
        rows_by_arm[rid] = rows
        enters = [r for r in rows if r.get("action") != "HOLD"]
        placed = [r for r in enters if (r.get("placement") or {}).get("placed")]
        lanes = Counter(_lane(r.get("reason")) for r in enters)
        tag = "FULL-SEND" if rid in fs_ids else "gated"
        print(f"{rid:<10} {a.get('display_name', '')[:21]:<22} {len(rows):>6} "
              f"{len(enters):>6} {len(placed):>7}  {dict(lanes) or '-'}  [{tag}]")

    print("\nBLOCKER CASCADE (why each arm did not place)")
    print("-" * 86)
    for rid, rows in rows_by_arm.items():
        c = Counter(_blocker(r) for r in rows)
        top = ", ".join(f"{k}={v}" for k, v in c.most_common(6))
        print(f"  {rid:<10} {top}")

    # --- same-tick comparison: the actual A/B ---------------------------------
    if fs_ids:
        fs = fs_ids[0]
        fs_enter_ticks = {str(r.get("ts_et"))[:16] for r in rows_by_arm.get(fs, [])
                          if r.get("action") != "HOLD"}
        print(f"\nSAME-TICK A/B -- ticks where {fs} (FULL-SEND) entered: {len(fs_enter_ticks)}")
        print("-" * 86)
        if not fs_enter_ticks:
            print(f"  (none in this window -- {fs} produced no entry)")
        for rid, rows in rows_by_arm.items():
            if rid == fs:
                continue
            same = [r for r in rows if str(r.get("ts_et"))[:16] in fs_enter_ticks]
            c = Counter(_blocker(r) for r in same)
            print(f"  {rid:<10} on those ticks: {dict(c) or 'no matching tick logged'}")

    # --- per-day fills, the learning-rate headline ---------------------------
    print("\nFILLS PER DAY (learning rate -- the metric this arm exists to move)")
    print("-" * 86)
    per_day: dict[str, dict[str, int]] = defaultdict(dict)
    for rid, rows in rows_by_arm.items():
        d2 = Counter(str(r.get("ts_et"))[:10] for r in rows
                     if (r.get("placement") or {}).get("placed"))
        for dd, n in d2.items():
            per_day[dd][rid] = n
    if not per_day:
        print("  no placed orders in this window")
    for dd in sorted(per_day):
        cells = "  ".join(f"{k}={v}" for k, v in sorted(per_day[dd].items()))
        print(f"  {dd}  {cells}")
    ndays = len({str(r.get('ts_et'))[:10] for rows in rows_by_arm.values() for r in rows})
    if ndays:
        print(f"\n  sessions in window: {ndays}")
        for rid, rows in rows_by_arm.items():
            f = sum(1 for r in rows if (r.get("placement") or {}).get("placed"))
            mark = " <- FULL-SEND" if rid in fs_ids else ""
            print(f"    {rid:<10} fills={f:<4} fills/session={f / ndays:.3f}{mark}")

    # --- marginal cohort (risk arms vs BOTH safes) + weekly artifact ----------
    mc_days = ({str(r.get("ts_et", ""))[:10] for rows in rows_by_arm.values() for r in rows}
               if (day or since) else set())
    mc_days.discard("")
    if weekly:
        mc_days = last_n_session_days(5)
    if mc_days:
        mc = marginal_cohort(mc_days)
        print_marginal(mc)
        if weekly:
            path = write_weekly_artifact(mc)
            print(f"\n  weekly artifact: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

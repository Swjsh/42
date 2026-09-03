#!/usr/bin_env python
"""money_structure_stop_extract.py -- H5 STRUCTURE-STOP WHIPSAW: extraction pass.

Extracts every real structure_stop exit event (placed=True) from the core decision
ledger (automation/state/core-decisions.jsonl) and the fleet decision ledgers
(automation/state/fleet/<arm>/decisions.jsonl), matches each to its entry in the
frozen pain-ledger (analysis/pain-ledger/mae-mfe.json) for realized dollars, and
writes a flat JSON population to
analysis/deep-research/2026-09-03-money/structure-stop-population.json for the
downstream buffer-simulation pass. READ-ONLY on automation/state and journal;
writes ONLY under analysis/deep-research/2026-09-03-money/.

Cached data only. No network / broker calls.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
FLEET = STATE / "fleet"
OUT_DIR = REPO / "analysis" / "deep-research" / "2026-09-03-money"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CORE_ACCOUNT_TO_ARM = {"safe": "safe-2", "bold": "bold-2"}
FLEET_ARMS = ("safe-3", "risky-1", "risky-3")


def option_side_from_symbol(symbol: str) -> str:
    return symbol[9]


def extract_core() -> list[dict]:
    out = []
    path = STATE / "core-decisions.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or '"structure_stop"' not in line:
            continue
        try:
            r = json.loads(line)
        except ValueError:
            continue
        ep = r.get("exit_pass")
        if not ep:
            continue
        for leg in ep:
            for act in (leg.get("actions") or []):
                if act.get("stage") == "structure_stop" and act.get("placed"):
                    sym = leg.get("symbol")
                    out.append({
                        "arm": CORE_ACCOUNT_TO_ARM.get(r.get("account"), r.get("account")),
                        "account": r.get("account"),
                        "ts_et": r.get("ts_et"),
                        "symbol": sym,
                        "side": option_side_from_symbol(sym) if sym else None,
                        "spy_top": r.get("spy"),
                        "vix": r.get("vix"),
                        "open_qty": leg.get("open_qty"),
                        "best_premium": leg.get("best_premium"),
                        "worst_premium": leg.get("worst_premium"),
                        "tp1_filled": leg.get("tp1_filled"),
                        "runner_stop": leg.get("runner_stop"),
                        "trigger_level": leg.get("trigger_level"),
                        "last_closed_5m_close": leg.get("last_closed_5m_close"),
                        "reason": act.get("reason"),
                        "source": "core",
                    })
    return out


def extract_fleet() -> list[dict]:
    out = []
    for arm in FLEET_ARMS:
        path = FLEET / arm / "decisions.jsonl"
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or '"structure_stop"' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            ep = r.get("exit_pass")
            if not ep:
                continue
            for leg in ep:
                for act in (leg.get("actions") or []):
                    if act.get("stage") == "structure_stop" and act.get("placed"):
                        sym = leg.get("symbol")
                        out.append({
                            "arm": r.get("arm_id") or arm,
                            "account": None,
                            "ts_et": r.get("ts_et"),
                            "symbol": sym,
                            "side": option_side_from_symbol(sym) if sym else None,
                            "spy_top": None,
                            "vix": None,
                            "open_qty": leg.get("open_qty"),
                            "best_premium": leg.get("best_premium"),
                            "worst_premium": leg.get("worst_premium"),
                            "tp1_filled": leg.get("tp1_filled"),
                            "runner_stop": leg.get("runner_stop"),
                            "trigger_level": leg.get("trigger_level"),
                            "last_closed_5m_close": leg.get("last_closed_5m_close"),
                            "reason": act.get("reason"),
                            "source": "fleet",
                        })
    return out


def load_mae_mfe() -> list[dict]:
    p = REPO / "analysis" / "pain-ledger" / "mae-mfe.json"
    return json.loads(p.read_text(encoding="utf-8"))["trades"]


def _naive_et_z(ts: str) -> "object":
    import datetime as _dt
    s = ts.strip()
    if s.endswith("Z"):
        d = _dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    else:
        d = _dt.datetime.fromisoformat(s)
    if d.tzinfo is not None:
        d = d.astimezone(_dt.timezone(_dt.timedelta(hours=-4))).replace(tzinfo=None)
    return d


def match_to_mae_mfe(events: list[dict], trades: list[dict]) -> None:
    """Match each structure_stop event to its mae-mfe.json entry trade by
    (arm, symbol, date) -- date derived from ts_et. When a symbol was entered
    more than once the same day (re-entries), pick the candidate trade whose
    entry_ts_utc is the closest ON-OR-BEFORE the stop event's own timestamp and
    not already claimed by an earlier stop leg for the same key -- this is more
    robust than index order when a symbol carries 3+ same-day entries."""
    by_key: dict[tuple, list[dict]] = {}
    for t in trades:
        key = (t["arm"], t["symbol"], t["date"])
        by_key.setdefault(key, []).append(t)
    for key in by_key:
        by_key[key].sort(key=lambda t: t["entry_ts_utc"])

    claimed: dict[tuple, set[int]] = {}
    for ev in events:
        date = (ev["ts_et"] or "")[:10]
        key = (ev["arm"], ev["symbol"], date)
        cands = by_key.get(key, [])
        if not cands:
            ev["mae_mfe_match"] = None
            continue
        used = claimed.setdefault(key, set())
        ev_dt = _naive_et_z(ev["ts_et"])
        best_i, best_delta = None, None
        for i, t in enumerate(cands):
            if i in used:
                continue
            t_dt = _naive_et_z(t["entry_ts_utc"])
            delta = (ev_dt - t_dt).total_seconds()
            if delta < -60:  # entry strictly after the stop event -- not a valid candidate
                continue
            if best_delta is None or delta < best_delta:
                best_i, best_delta = i, delta
        if best_i is None:
            # no unclaimed candidate entered before this stop -- reuse nearest by
            # absolute time among ALL candidates (claimed or not), flagged
            best_i = min(range(len(cands)),
                        key=lambda i: abs((ev_dt - _naive_et_z(cands[i]["entry_ts_utc"])).total_seconds()))
            ev["mae_mfe_match"] = dict(cands[best_i], _reused=True)
        else:
            used.add(best_i)
            ev["mae_mfe_match"] = cands[best_i]


def main() -> int:
    core = extract_core()
    fleet = extract_fleet()
    events = core + fleet
    events.sort(key=lambda e: (e["ts_et"] or ""))
    trades = load_mae_mfe()
    match_to_mae_mfe(events, trades)

    n_matched = sum(1 for e in events if e.get("mae_mfe_match"))
    n_reused = sum(1 for e in events if (e.get("mae_mfe_match") or {}).get("_reused"))
    print(f"[extract] core={len(core)} fleet={len(fleet)} total={len(events)} "
          f"matched_to_mae_mfe={n_matched} reused_match={n_reused}")

    out_path = OUT_DIR / "structure-stop-population.json"
    out_path.write_text(json.dumps({
        "_meta": {
            "n_events": len(events), "n_core": len(core), "n_fleet": len(fleet),
            "n_matched_mae_mfe": n_matched, "n_reused_match": n_reused,
            "sources": ["automation/state/core-decisions.jsonl",
                        "automation/state/fleet/{safe-3,risky-1,risky-3}/decisions.jsonl",
                        "analysis/pain-ledger/mae-mfe.json"],
        },
        "events": events,
    }, indent=2, default=str), encoding="utf-8")
    print(f"[extract] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

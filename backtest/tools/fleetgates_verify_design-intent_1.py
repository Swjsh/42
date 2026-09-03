"""fleetgates_verify_design-intent_1.py -- independent rebuild of the join
core_tick_id -> {safe, bold} core verdict -> fleet arm decision -> fill,
to verify (not trust) the counts/claims in
analysis/deep-research/2026-09-03-money/fleet-gates-design-intent.md and its
companion veto-scope-safe-3.md.

READ-ONLY. Writes only analysis/deep-research/2026-09-03-money/fleetgates-verify-*.json.
No automation/state/** file is modified. < 5 min single process, no network/broker calls.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_DECISIONS = ROOT / "automation" / "state" / "core-decisions.jsonl"
FLEET_DIR = ROOT / "automation" / "state" / "fleet"
FILLS = ROOT / "automation" / "state" / "fills-ledger.jsonl"
OUT = ROOT / "analysis" / "deep-research" / "2026-09-03-money" / "fleetgates-verify-design-intent-1.json"

ARMS = ["safe-3", "risky-1", "risky-3"]  # risky-1/risky-3 for cross-check even though risky-3 retired 08-28
NAMED_DAYS = ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]
SEPT_WINDOW_START = "2026-09-01"


def load_core_decisions():
    """core_tick_id -> {'safe': row, 'bold': row}. Track dup collisions for QA."""
    by_tick = defaultdict(dict)
    dup_count = 0
    total = 0
    bad_json = 0
    with open(CORE_DECISIONS, encoding="utf-8") as f:
        for line in f:
            total += 1
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                bad_json += 1
                continue
            tick = row.get("core_tick_id")
            acct = row.get("account")
            if tick is None or acct not in ("safe", "bold"):
                continue
            if acct in by_tick[tick]:
                dup_count += 1
                # keep the LATER row (later ts_et) -- decisions.jsonl is append-only in time order
                prev = by_tick[tick][acct]
                if row.get("ts_et", "") >= prev.get("ts_et", ""):
                    by_tick[tick][acct] = row
            else:
                by_tick[tick][acct] = row
    return by_tick, {"total_rows": total, "bad_json": bad_json, "dup_account_tick_pairs": dup_count,
                      "unique_ticks": len(by_tick)}


def is_blocked(verdict: str | None) -> bool:
    if verdict is None:
        return True
    return verdict == "HOLD" or verdict.startswith("SKIP_") or verdict == "ERROR"


def is_enter(verdict: str | None, side: str) -> bool:
    """side: 'C' (bull) or 'P' (bear)."""
    if verdict is None:
        return False
    if side == "C":
        return verdict == "ENTER_BULL"
    if side == "P":
        return verdict == "ENTER_BEAR"
    return False


def load_arm_decisions(arm: str):
    path = FLEET_DIR / arm / "decisions.jsonl"
    if not path.exists():
        return []
    rows = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("action") in ("ENTER_BULL", "ENTER_BEAR"):
                rows.append(row)
    return rows


def load_fills():
    """arm -> list of buy fills (side='buy'), sorted by ts_et."""
    by_arm = defaultdict(list)
    if not FILLS.exists():
        return by_arm
    with open(FILLS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:
                continue
            if row.get("side") == "buy":
                by_arm[row.get("arm")].append(row)
    for arm in by_arm:
        by_arm[arm].sort(key=lambda r: r.get("ts_et", ""))
    return by_arm


def nearest_buy_fill(fills_for_arm, symbol, ts_et, max_seconds=180):
    """Find the buy fill for `symbol` closest in time (within max_seconds) to ts_et."""
    from datetime import datetime

    def parse(ts):
        # ts_et strings may or may not carry an offset; normalize by stripping offset
        ts = ts.split("-04:00")[0].split("-05:00")[0]
        try:
            return datetime.fromisoformat(ts)
        except Exception:
            return None

    t0 = parse(ts_et)
    if t0 is None:
        return None
    best = None
    best_dt = None
    for row in fills_for_arm:
        if row.get("symbol") != symbol:
            continue
        t1 = parse(row.get("ts_et", ""))
        if t1 is None:
            continue
        dt = abs((t1 - t0).total_seconds())
        if dt <= max_seconds and (best_dt is None or dt < best_dt):
            best = row
            best_dt = dt
    return best


def main():
    by_tick, core_qa = load_core_decisions()
    print("CORE-DECISIONS QA:", core_qa, file=sys.stderr)

    fills_by_arm = load_fills()

    results = {}
    gate_breakdown = Counter()          # (arm, safe_blocking_verdict) -> n role-blind entries
    per_day_gate = defaultdict(Counter)  # date -> (arm,classification) -> n
    per_arm_class = defaultdict(Counter)  # arm -> classification -> n
    role_blind_rows = []  # full detail rows for role-blind entries, for spot audit
    dollar_by_class = defaultdict(float)  # classification -> sum notional (qty*premium*100), decision-row basis
    dollar_fills_by_class = defaultdict(float)  # classification -> sum qty*fill_price*100 (fills-ledger basis, where matched)
    matched_fill_count = Counter()
    unmatched_fill_count = Counter()

    for arm in ARMS:
        rows = load_arm_decisions(arm)
        per_arm_class[arm]  # touch to ensure key exists
        for row in rows:
            tick = row.get("core_tick_id")
            side = row.get("side")  # 'C' or 'P'
            date = (row.get("ts_et") or "")[:10]
            core_rows = by_tick.get(tick, {})
            safe_row = core_rows.get("safe")
            bold_row = core_rows.get("bold")
            safe_verdict = safe_row.get("verdict") if safe_row else None
            bold_verdict = bold_row.get("verdict") if bold_row else None

            safe_blocked = is_blocked(safe_verdict)
            safe_same_side_entered = is_enter(safe_verdict, side)
            bold_same_side_entered = is_enter(bold_verdict, side)

            if safe_row is None:
                cls = "no_safe_row_for_tick"
            elif safe_same_side_entered:
                cls = "safe_faithful"  # safe's own core verdict already agreed with this entry
            elif safe_blocked and bold_same_side_entered:
                cls = "role_blind_ride"  # the exact mechanism under test: safe blocked, bold passed same side
            elif safe_blocked and not bold_same_side_entered:
                cls = "safe_blocked_bold_also_not_entered"  # neither safe nor bold's OWN verdict explains it (e.g. vwap strategy, not core-gated)
            else:
                cls = "other"

            per_arm_class[arm][cls] += 1
            per_day_gate[date][(arm, cls)] += 1

            qty = row.get("qty") or 0
            premium = row.get("premium") or 0.0
            notional = qty * premium * 100
            dollar_by_class[cls] += notional

            if cls == "role_blind_ride":
                gate_breakdown[(arm, safe_verdict)] += 1
                symbol = None
                placement = row.get("placement") or {}
                symbol = placement.get("symbol")
                fill = nearest_buy_fill(fills_by_arm.get(arm, []), symbol, row.get("ts_et", "")) if symbol else None
                fill_notional = None
                if fill:
                    fill_notional = fill.get("qty", 0) * fill.get("price", 0.0) * 100
                    dollar_fills_by_class[cls] += fill_notional
                    matched_fill_count[cls] += 1
                else:
                    unmatched_fill_count[cls] += 1
                role_blind_rows.append({
                    "arm": arm, "date": date, "core_tick_id": tick, "side": side,
                    "setup": row.get("setup_name"), "safe_verdict": safe_verdict,
                    "bold_verdict": bold_verdict, "qty": qty, "premium": premium,
                    "decision_notional": notional, "fill_notional": fill_notional,
                    "symbol": symbol,
                })

    # ---- summarize ----
    summary = {
        "core_qa": core_qa,
        "per_arm_classification_counts": {arm: dict(c) for arm, c in per_arm_class.items()},
        "role_blind_ride_gate_breakdown": {f"{arm}|{v}": n for (arm, v), n in gate_breakdown.most_common()},
        "dollar_notional_by_class_decision_basis": dict(dollar_by_class),
        "dollar_notional_role_blind_fills_basis": dict(dollar_fills_by_class),
        "role_blind_fill_match_counts": {"matched": dict(matched_fill_count), "unmatched": dict(unmatched_fill_count)},
    }

    # per named day + Sept window
    named_day_summary = {}
    for d in NAMED_DAYS:
        day_rows = [r for r in role_blind_rows if r["date"] == d]
        named_day_summary[d] = {
            "role_blind_ride_count": len(day_rows),
            "by_arm": dict(Counter(r["arm"] for r in day_rows)),
            "decision_notional_sum": sum(r["decision_notional"] for r in day_rows),
            "fill_notional_sum": sum(r["fill_notional"] for r in day_rows if r["fill_notional"] is not None),
        }

    sept_rows = [r for r in role_blind_rows if r["date"] >= SEPT_WINDOW_START]
    sept_summary = {
        "role_blind_ride_count": len(sept_rows),
        "by_arm": dict(Counter(r["arm"] for r in sept_rows)),
        "by_date": dict(Counter(r["date"] for r in sept_rows)),
        "decision_notional_sum": sum(r["decision_notional"] for r in sept_rows),
        "fill_notional_sum": sum(r["fill_notional"] for r in sept_rows if r["fill_notional"] is not None),
    }

    out = {
        "generated_by": "backtest/tools/fleetgates_verify_design-intent_1.py",
        "summary": summary,
        "named_days": named_day_summary,
        "september_window": sept_summary,
        "role_blind_rows_sample": role_blind_rows[:50],
        "role_blind_rows_all_count": len(role_blind_rows),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)
    print("WROTE", OUT, file=sys.stderr)
    print(json.dumps(summary, indent=2, default=str))
    print("--- NAMED DAYS ---")
    print(json.dumps(named_day_summary, indent=2, default=str))
    print("--- SEPT WINDOW ---")
    print(json.dumps(sept_summary, indent=2, default=str))


if __name__ == "__main__":
    main()

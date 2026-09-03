"""
Verification script (skeptic pass) for fleet-gates-ledger-binding-check.md.
READ-ONLY. Re-derives Table A/B "entered" counts using DISTINCT REAL BUY FILLS
(fills-ledger.jsonl, matched by order_id within 300s of the core_tick_id) instead
of raw decisions.jsonl action rows, to check whether repeated same-tick decision
logging (a persisting signal logged every ~1min while unfilled/already-held)
inflates the original finding's entry counts.
"""
import json
from datetime import datetime
from collections import defaultdict

REPO = "C:/Users/jackw/Desktop/42"
FLEET_ARMS = ["safe-3", "risky-1", "risky-3"]
ENTER_VERDICTS = {"ENTER_BULL", "ENTER_BEAR"}
ENTER_ACTIONS = {"ENTER_BULL", "ENTER_BEAR", "PLACED"}
MATCH_WINDOW_S = 300


def load_jsonl(path):
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def parse(ts):
    return datetime.fromisoformat(ts)


def build_tables(min_date="2026-08-06"):
    core = load_jsonl(f"{REPO}/automation/state/core-decisions.jsonl")
    by_tick = {}
    for r in core:
        ts = r.get("ts_et") or ""
        if ts < min_date:
            continue
        ct = r.get("core_tick_id")
        if ct is None:
            continue
        acct = r.get("account")
        if acct not in ("safe", "bold"):
            continue
        by_tick.setdefault(ct, {})[acct] = r

    tableA, tableB = set(), set()
    for ct, accts in by_tick.items():
        s, b = accts.get("safe"), accts.get("bold")
        if s is None or b is None:
            continue
        s_gated = isinstance(s.get("action"), str) and s["action"].startswith("SKIP_")
        b_gated = isinstance(b.get("action"), str) and b["action"].startswith("SKIP_")
        s_enter_v = s.get("verdict") in ENTER_VERDICTS
        b_enter_v = b.get("verdict") in ENTER_VERDICTS
        if s_gated and b_enter_v:
            tableA.add(ct)
        if b_gated and s_enter_v:
            tableB.add(ct)
    return tableA, tableB


def main():
    fills = load_jsonl(f"{REPO}/automation/state/fills-ledger.jsonl")
    tableA, tableB = build_tables()

    print(f"n_ticks Table A = {len(tableA)}, Table B = {len(tableB)}\n")

    grand = {}
    for arm in FLEET_ARMS:
        fleet = load_jsonl(f"{REPO}/automation/state/fleet/{arm}/decisions.jsonl")
        by_ct = defaultdict(list)
        for r in fleet:
            ct = r.get("core_tick_id")
            if ct:
                by_ct[ct].append(r)
        arm_buys = sorted(
            [f for f in fills if f.get("arm") == arm and f.get("side") == "buy"],
            key=lambda f: f["ts_et"],
        )

        for label, table in [("A", tableA), ("B", tableB)]:
            entered_ticks = sorted(
                ct for ct in table
                if any(r.get("action") in ENTER_ACTIONS for r in by_ct.get(ct, []))
            )
            matched_orders = {}
            phantom = []  # decision said ENTER, no real fill within window on record
            for ct in entered_ticks:
                t0 = parse(ct)
                best = None
                for f in arm_buys:
                    delta = (parse(f["ts_et"]) - t0).total_seconds()
                    if 0 <= delta <= MATCH_WINDOW_S:
                        best = f
                        break
                if best:
                    matched_orders.setdefault(best["order_id"], []).append(ct)
                else:
                    phantom.append(ct)

            n_ticks = len(table)
            n_raw = len(entered_ticks)
            n_real = len(matched_orders)
            share_raw = n_raw / n_ticks if n_ticks else None
            share_real = n_real / n_ticks if n_ticks else None
            grand[(arm, label)] = dict(
                n_ticks=n_ticks, n_raw=n_raw, n_real=n_real,
                n_phantom=len(phantom), share_raw=share_raw, share_real=share_real,
                phantom_sample=phantom[:8],
            )
            print(f"{arm} Table {label}: n_ticks={n_ticks} raw_entered_ticks={n_raw} "
                  f"distinct_real_buy_orders={n_real} phantom(no fill<=300s)={len(phantom)} "
                  f"| share_raw={share_raw:.1%} share_real(corrected)={share_real:.1%}")

    print("\n=== Corrected asymmetry check (Table B / Table A ratio, real-trade basis) ===")
    for arm in FLEET_ARMS:
        a = grand[(arm, "A")]
        b = grand[(arm, "B")]
        ratio_raw = (b["share_raw"] / a["share_raw"]) if a["share_raw"] else None
        ratio_real = (b["share_real"] / a["share_real"]) if a["share_real"] else None
        print(f"{arm}: raw-basis B/A ratio={ratio_raw:.2f}  real-trade-basis B/A ratio={ratio_real:.2f}")


if __name__ == "__main__":
    main()

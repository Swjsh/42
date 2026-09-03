"""
Skeptic-pass robustness check: real-trade-corrected Table A/B aggregate shares,
with top-3-contributing-dates removed, per arm. READ-ONLY.
"""
import json
from datetime import datetime
from collections import defaultdict, Counter

REPO = "C:/Users/jackw/Desktop/42"
ENTER_VERDICTS = {"ENTER_BULL", "ENTER_BEAR"}
ENTER_ACTIONS = {"ENTER_BULL", "ENTER_BEAR", "PLACED"}


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

    for arm in ["safe-3", "risky-1", "risky-3"]:
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
            real_trade_dates = []
            seen_orders = set()
            for ct in entered_ticks:
                t0 = parse(ct)
                best = None
                for f in arm_buys:
                    delta = (parse(f["ts_et"]) - t0).total_seconds()
                    if 0 <= delta <= 300:
                        best = f
                        break
                if best and best["order_id"] not in seen_orders:
                    seen_orders.add(best["order_id"])
                    real_trade_dates.append(ct[:10])

            n_ticks = len(table)
            n_real = len(real_trade_dates)
            share = n_real / n_ticks if n_ticks else 0
            by_date = Counter(real_trade_dates)
            top3 = by_date.most_common(3)
            top3_dates = {d for d, _ in top3}
            # remove ticks on top-3-contributing dates from BOTH numerator and
            # denominator (drop those calendar days from the whole comparison)
            ticks_dropped = {ct for ct in table if ct[:10] in top3_dates}
            n_ticks_d = n_ticks - len(ticks_dropped)
            n_real_d = n_real - sum(c for _, c in top3)
            share_d = n_real_d / n_ticks_d if n_ticks_d else 0

            print(f"{arm} Table {label}: n_ticks={n_ticks} real_trades={n_real} "
                  f"share={share:.1%} | top3 contributing dates={top3} | "
                  f"after dropping those 3 dates entirely: n_ticks={n_ticks_d} "
                  f"real_trades={n_real_d} share={share_d:.1%}")


if __name__ == "__main__":
    main()

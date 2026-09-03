"""
Independent LEDGER-lens verification of analysis/deep-research/2026-09-03-money/
fleet-gates-code-binding-table.{md,json} (finding "code-binding-table").

Rebuilds, from scratch, the join core_tick_id -> per-account core verdict (safe/bold)
-> fleet-arm decision -> broker fill, WITHOUT importing anything from the finding's own
scripts. Recounts:
  - how often safe's core verdict BLOCKED a side (SKIP_*, HOLD) on a tick where bold's
    core verdict PASSED (verdict == ENTER_<SIDE>) the same side, same tick
  - how often a fleet arm (safe-3 / risky-1 / risky-3) placed ENTER_<SIDE> on exactly
    that blocked-safe/passed-bold tick (i.e. rode bold's perception, not safe's)
  - cross-checked against fills-ledger.jsonl for broker-fill confirmation
  - broken out: ALL history, the 4 named "winning days" (2026-08-06/13/27/28), and the
    September window (2026-09-01..today)
  - risky-3 retirement enforcement (any row on/after 2026-08-29?)

READ-ONLY. No network/broker calls. < 5 min run.
"""
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CORE_PATH = ROOT / "automation/state/core-decisions.jsonl"
FILLS_PATH = ROOT / "automation/state/fills-ledger.jsonl"
FLEET_ARMS = ["safe-3", "risky-1", "risky-3"]
WINNING_DAYS = {"2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"}
SEPT_WINDOW_START = "2026-09-01"

SIDE_TO_ENTER = {"P": "ENTER_BEAR", "C": "ENTER_BULL"}


def load_jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def main():
    core_rows = load_jsonl(CORE_PATH)
    print(f"[load] core-decisions.jsonl: {len(core_rows)} rows")

    # index: core_tick_id -> {account: row}   (last-write-wins per account per tick, but
    # in practice each (tick_id, account) pair should appear once)
    core_by_tick = defaultdict(dict)
    core_tick_dupes = 0
    for r in core_rows:
        ctid = r.get("core_tick_id")
        acct = r.get("account")
        if ctid is None or acct is None:
            continue
        if acct in core_by_tick[ctid]:
            core_tick_dupes += 1
        core_by_tick[ctid][acct] = r
    print(f"[index] distinct core_tick_ids: {len(core_by_tick)}  (dupe acct/tick pairs: {core_tick_dupes})")

    fills_rows = load_jsonl(FILLS_PATH)
    print(f"[load] fills-ledger.jsonl: {len(fills_rows)} rows")
    # index fills by (arm, order_id) via order_id substring match against fleet decision
    # placement.broker.id / placement.broker.client_order_id
    fills_by_order_id = {}
    for fr in fills_rows:
        oid = fr.get("order_id")
        if oid:
            fills_by_order_id[oid] = fr

    results = {}  # arm -> list of divergence-join records
    arm_totals = {}
    retirement_check = {}

    for arm in FLEET_ARMS:
        path = ROOT / f"automation/state/fleet/{arm}/decisions.jsonl"
        rows = load_jsonl(path)
        print(f"[load] {arm}/decisions.jsonl: {len(rows)} rows")

        # retirement check: any row on/after 2026-08-29 for risky-3?
        last_ts = None
        after_0829 = []
        for r in rows:
            ts = r.get("ts_et", "")
            if last_ts is None or ts > last_ts:
                last_ts = ts
            if ts >= "2026-08-29":
                after_0829.append(ts)
        retirement_check[arm] = {"last_ts_et": last_ts, "n_rows_on_or_after_2026-08-29": len(after_0829)}

        enter_rows = [r for r in rows if str(r.get("action", "")).startswith("ENTER_")]
        n_with_ctid = sum(1 for r in enter_rows if r.get("core_tick_id"))
        arm_totals[arm] = {
            "total_rows": len(rows),
            "enter_action_rows": len(enter_rows),
            "enter_rows_with_core_tick_id": n_with_ctid,
        }

        divergences = []
        matched_no_divergence = 0
        no_ctid_or_no_core_match = 0

        for r in enter_rows:
            ctid = r.get("core_tick_id")
            side = r.get("side")
            if not ctid or side not in SIDE_TO_ENTER:
                no_ctid_or_no_core_match += 1
                continue
            core_pair = core_by_tick.get(ctid)
            if not core_pair or "safe" not in core_pair or "bold" not in core_pair:
                no_ctid_or_no_core_match += 1
                continue
            safe_row = core_pair["safe"]
            bold_row = core_pair["bold"]
            want = SIDE_TO_ENTER[side]
            safe_verdict = safe_row.get("verdict")
            bold_verdict = bold_row.get("verdict")
            safe_passed = safe_verdict == want
            bold_passed = bold_verdict == want

            if (not safe_passed) and bold_passed:
                # THE divergence pattern: safe's own core row blocked this side, bold's
                # passed it, and the fleet arm entered anyway on this exact tick.
                # find matching fill if any (via placement.broker.id)
                broker_id = None
                placement = r.get("placement") or {}
                broker = placement.get("broker") or {}
                broker_id = broker.get("id")
                fill = fills_by_order_id.get(broker_id) if broker_id else None
                divergences.append({
                    "date": r.get("ts_et", "")[:10],
                    "ts_et": r.get("ts_et"),
                    "core_tick_id": ctid,
                    "side": side,
                    "safe_verdict": safe_verdict,
                    "bold_verdict": bold_verdict,
                    "arm_action": r.get("action"),
                    "arm_placed": placement.get("placed"),
                    "qty": r.get("qty"),
                    "premium": r.get("premium"),
                    "strike": r.get("strike"),
                    "broker_id": broker_id,
                    "fill_found": fill is not None,
                    "fill_price": fill.get("price") if fill else None,
                    "fill_ts": fill.get("ts_et") if fill else None,
                })
            else:
                matched_no_divergence += 1

        results[arm] = divergences
        arm_totals[arm]["divergence_joins"] = len(divergences)
        arm_totals[arm]["matched_no_divergence"] = matched_no_divergence
        arm_totals[arm]["unjoinable_no_ctid_or_no_core_pair"] = no_ctid_or_no_core_match

    # -------- breakdowns --------
    def bucket(divs, pred):
        return [d for d in divs if pred(d["date"])]

    print("\n" + "=" * 78)
    print("ARM TOTALS")
    print("=" * 78)
    for arm in FLEET_ARMS:
        print(f"\n{arm}: {arm_totals[arm]}")

    print("\n" + "=" * 78)
    print("DIVERGENCE JOIN COUNTS (safe core-blocked + bold core-passed + arm ENTER, same tick)")
    print("=" * 78)
    all_div_by_reason = defaultdict(int)
    for arm in FLEET_ARMS:
        divs = results[arm]
        all_time = len(divs)
        winning = bucket(divs, lambda d: d in WINNING_DAYS)
        sept = bucket(divs, lambda d: d >= SEPT_WINDOW_START)
        fills_confirmed = sum(1 for d in divs if d["fill_found"])
        print(f"\n{arm}: total={all_time}  winning-days={len(winning)}  sept-window={len(sept)}  "
              f"fills-confirmed={fills_confirmed}/{all_time}")
        reason_counts = defaultdict(int)
        for d in divs:
            reason_counts[d["safe_verdict"]] += 1
            all_div_by_reason[d["safe_verdict"]] += 1
        for reason, cnt in sorted(reason_counts.items(), key=lambda x: -x[1]):
            print(f"    safe_verdict={reason}: {cnt}")

    print("\n" + "=" * 78)
    print("ALL-ARMS safe_verdict reason breakdown (union)")
    print("=" * 78)
    for reason, cnt in sorted(all_div_by_reason.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {cnt}")

    print("\n" + "=" * 78)
    print("WINNING-DAY DETAIL (all divergence rows, all arms)")
    print("=" * 78)
    for arm in FLEET_ARMS:
        for d in results[arm]:
            if d["date"] in WINNING_DAYS:
                print(f"  [{arm}] {json.dumps(d, default=str)}")

    print("\n" + "=" * 78)
    print("SEPTEMBER WINDOW DETAIL (all divergence rows, all arms)")
    print("=" * 78)
    for arm in FLEET_ARMS:
        for d in results[arm]:
            if d["date"] >= SEPT_WINDOW_START:
                print(f"  [{arm}] {json.dumps(d, default=str)}")

    print("\n" + "=" * 78)
    print("RETIREMENT ENFORCEMENT CHECK")
    print("=" * 78)
    for arm, info in retirement_check.items():
        print(f"  {arm}: {info}")

    # -------- specific ledger rows the finding quoted verbatim: re-derive independently --------
    print("\n" + "=" * 78)
    print("SPOT-CHECK: the 2 core_tick_ids the finding quoted for safe-3 today (2026-09-03)")
    print("=" * 78)
    for ctid in ["2026-09-03T11:06:02.738610", "2026-09-03T11:21:02.576928"]:
        pair = core_by_tick.get(ctid)
        print(f"\n  core_tick_id={ctid}")
        if not pair:
            print("    NOT FOUND in core-decisions.jsonl index")
            continue
        for acct in ("safe", "bold"):
            row = pair.get(acct)
            if row:
                print(f"    account={acct}: verdict={row.get('verdict')} action={row.get('action')} "
                      f"side={row.get('side')} reason={row.get('reason')}")
        for arm in FLEET_ARMS:
            match = [d for d in results[arm] if d["core_tick_id"] == ctid]
            if match:
                print(f"    [{arm}] divergence-join match: {match}")
            else:
                # also check raw arm rows regardless of divergence classification
                path = ROOT / f"automation/state/fleet/{arm}/decisions.jsonl"
                for r in load_jsonl(path):
                    if r.get("core_tick_id") == ctid:
                        print(f"    [{arm}] raw row (non-divergence classified): action={r.get('action')} "
                              f"side={r.get('side')}")

    out = {
        "arm_totals": arm_totals,
        "retirement_check": retirement_check,
        "divergence_counts": {
            arm: {
                "all_time": len(results[arm]),
                "winning_days": len(bucket(results[arm], lambda d: d in WINNING_DAYS)),
                "sept_window": len(bucket(results[arm], lambda d: d >= SEPT_WINDOW_START)),
                "fills_confirmed": sum(1 for d in results[arm] if d["fill_found"]),
            }
            for arm in FLEET_ARMS
        },
        "winning_day_rows": {arm: [d for d in results[arm] if d["date"] in WINNING_DAYS] for arm in FLEET_ARMS},
        "sept_window_rows": {arm: [d for d in results[arm] if d["date"] >= SEPT_WINDOW_START] for arm in FLEET_ARMS},
    }
    out_path = ROOT / "analysis/deep-research/2026-09-03-money/verify-fleet-gates-code-binding-table-1.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"\n[write] {out_path}")


if __name__ == "__main__":
    main()

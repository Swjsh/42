"""full_send_vs_gated.py -- the standing FULL-SEND vs GATED comparison query.

WHY THIS EXISTS: the full-send arm (risky-1, armed 2026-07-31) only earns its keep if we
LEARN from it. Its whole justification is LEARNING RATE, not P&L -- so "how many more fills
did the loose arm take than the gated arms, on the IDENTICAL signal, and what did that cost"
must be a QUERY, not a research project. Per OP-33: visibility is the product.

WHAT IT ANSWERS, per trading day and per arm:
  * ticks evaluated, ENTERs produced, orders actually placed
  * WHICH LANE produced each entry (normal / FULL_SEND / PROBE_ARM / SCORE_LADDER)
  * the blocker cascade -- exactly what stopped the arm on every non-entering tick
  * same-tick comparison: on ticks where the full-send arm entered, what did each gated arm do

Reads ONLY existing per-arm ledgers (automation/state/fleet/<arm>/decisions.jsonl), which
already carry arm_id + reason + risk_code + placement, so no new producer was needed.

$0, offline, read-only -- never writes trading state. Run:
    python setup/scripts/full_send_vs_gated.py               # today
    python setup/scripts/full_send_vs_gated.py 2026-07-31    # a specific ET date
    python setup/scripts/full_send_vs_gated.py --since 2026-07-01
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))
FLEET = REPO / "automation" / "state" / "fleet"
ACCOUNTS = FLEET / "accounts.json"

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


def main() -> int:
    args = [a for a in sys.argv[1:]]
    since = None
    day = None
    if "--since" in args:
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

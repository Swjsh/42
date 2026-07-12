"""broker_fills.py -- the broker-truth fills instrument (HANDOFF-2026-07-09-TRUTH-AND-EXITS, T1).

GROUND RULE 2: broker = truth for fills/P&L. decisions.jsonl / core-decisions.jsonl structurally
lack fleet fills (reconciliation only runs on the core path) -- any "did we trade / how much"
number must originate from Alpaca activities/orders, never a decision ledger. This is the one
place that pulls FILL activities directly from Alpaca for all 6 fleet accounts, normalizes
UTC->ET via et_clock, FIFO-pairs round trips per (account, symbol), computes realized P&L, and
writes the two files every downstream consumer (T2) must read instead of a decision ledger:

  - automation/state/fills-ledger.jsonl  (append-only, deduped by activity id)
  - automation/state/pnl-statement.json  (per-account + per-day: n_fills, realized P&L,
    engine-vs-manual attribution, round trips, open lots)

ATTRIBUTION RULE (pre-decided, HANDOFF T1): fleet_rest arms (safe-1, safe-3, risky-1, risky-3)
= 100% engine. safe-2/bold-2 = manual UNLESS the fill's order_id matches a PLACED entry row
(`exec`), an exit action (`exit_pass`), or a G4 extra-setup placement (`extra_exec`) for that
account in core-decisions.jsonl (then engine). Crypto (symbol contains "/") = always manual,
excluded from engine P&L.

Idempotent: re-running only appends fills whose activity id isn't already in the ledger, then
recomputes the full statement (round trips + open lots) from the complete ledger every time --
so a partial-history run followed by a full backfill run converges to the same statement.
Attribution self-heals PROMOTE-ONLY on every run: a core-arm row written "manual" whose
order_id has since become a known engine order id flips to "engine" (atomic full rewrite);
"engine" is never demoted, so a pruned/rotated core-decisions.jsonl can't corrupt history.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))
import fleet_broker as fb  # noqa: E402
from et_clock import et_now  # noqa: E402

STATE = REPO / "automation" / "state"
LEDGER = STATE / "fills-ledger.jsonl"
STATEMENT = STATE / "pnl-statement.json"
CORE_DECISIONS = STATE / "core-decisions.jsonl"
ACCOUNTS_JSON = STATE / "fleet" / "accounts.json"

BACKFILL_SINCE = "2026-06-25T00:00:00Z"  # per HANDOFF T1 -- fleet went live around this date
# safe-1 RETIRED 2026-07-11 (accounts.json status=retired): its account (PA3DHPT7KIQE) was
# reassigned to core Safe (CORE_ARMS["safe-2"] below). Leaving "safe-1" in this tuple after the
# repoint would make main()'s `for arm, creds in creds_all.items(): if arm not in FLEET_REST_ARMS
# and arm not in CORE_ARMS: continue` loop process the SAME broker account under TWO labels
# (creds_all iterates fleet/secrets.json, where safe-1 and safe-2 now share identical creds) --
# since dict order puts "safe-1" before "safe-2", its fills would get attributed engine_ids=None
# (arm not in CORE_ARMS) and misclassified as "manual" instead of "engine", corrupting
# total_engine_pnl/total_manual_pnl. Dropping safe-1 here routes those fills through CORE_ARMS
# ("safe-2" -> "safe") with correct engine-order attribution instead.
FLEET_REST_ARMS = ("safe-3", "risky-1", "risky-3")  # execution=fleet_rest -> 100% engine
CORE_ARMS = {"safe-2": "safe", "bold-2": "bold"}  # arm -> core-decisions.jsonl `account` field


def _is_crypto(symbol: str) -> bool:
    return "/" in (symbol or "")


def _is_option(symbol: str) -> bool:
    """OCC option symbols are >=15 chars (root+date+C/P+strike); crypto pairs contain '/'."""
    return isinstance(symbol, str) and len(symbol) >= 15 and not _is_crypto(symbol)


def _multiplier(symbol: str) -> int:
    return 100 if _is_option(symbol) else 1


def fetch_fill_activities(creds: dict, after_iso: str, timeout: float = 15.0) -> list:
    """Pull ALL FILL activities since after_iso, paginating via Alpaca's page_token cursor
    (ground rule 6: page_size max 100). Fail-open -> returns whatever was accumulated so far
    on any error, never raises."""
    out: list = []
    page_token: Optional[str] = None
    base = creds["base_url"].rstrip("/") + "/v2/account/activities/FILL"
    headers = {"APCA-API-KEY-ID": creds["key"], "APCA-API-SECRET-KEY": creds["secret"]}
    for _ in range(200):  # hard cap -- 100/page * 200 = 20k rows, far above any real history
        url = f"{base}?after={after_iso}&direction=asc&page_size=100"
        if page_token:
            url += f"&page_token={page_token}"
        try:
            req = urllib.request.Request(url, headers=headers)
            data = json.loads(urllib.request.urlopen(req, timeout=timeout).read())
        except Exception as exc:  # noqa: BLE001 -- fail-open, log and stop paginating
            print(f"[broker_fills] fetch error: {exc}", file=sys.stderr)
            break
        if not isinstance(data, list) or not data:
            break
        out.extend(data)
        if len(data) < 100:
            break
        last = data[-1]
        page_token = last.get("id") if isinstance(last, dict) else None
        if not page_token:
            break
    return out


def engine_order_ids(account_field_value: str, core_decisions_path: Path = CORE_DECISIONS) -> set:
    """Order ids that appear as a PLACED entry (`exec.broker.id`), an exit action
    (`exit_pass[].actions[].broker.id`), or a G4 extra-setup placement
    (`extra_exec[].exec.broker.id` -- heartbeat_core._route_extra_setups: vwap_continuation,
    bollinger_squeeze, ...) for this core account (`account_field_value` = "safe"/"bold")
    in core-decisions.jsonl. safe-2/bold-2 route through the MCP heartbeat path, not
    fleet_rest -- these ARE the engine's own orders even though they're a different
    execution path, and must attribute as engine, not manual. (2026-07-09 fix: extra_exec
    was not scanned -- every extra-setup ENTRY fill mis-attributed manual while its exit
    attributed engine, orphaning the position for attribution-filtering consumers.)"""
    ids: set = set()
    if not core_decisions_path.exists():
        return ids
    with core_decisions_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if row.get("account") != account_field_value:
                continue
            exec_ = row.get("exec")
            if isinstance(exec_, dict):
                b = exec_.get("broker")
                if isinstance(b, dict) and b.get("id"):
                    ids.add(b["id"])
            for ep in (row.get("exit_pass") or []):
                if not isinstance(ep, dict):
                    continue
                for act in (ep.get("actions") or []):
                    if not isinstance(act, dict):
                        continue
                    b = act.get("broker")
                    if isinstance(b, dict) and b.get("id"):
                        ids.add(b["id"])
            for ee in (row.get("extra_exec") or []):
                if not isinstance(ee, dict):
                    continue
                ee_exec = ee.get("exec")
                if isinstance(ee_exec, dict):
                    b = ee_exec.get("broker")
                    if isinstance(b, dict) and b.get("id"):
                        ids.add(b["id"])
    return ids


def normalize_fill(activity: dict, arm: str, engine_ids: "set | None" = None) -> "dict | None":
    """PURE: one Alpaca FILL activity row -> a normalized fill dict, or None if malformed
    (missing id/symbol/side/timestamp, or non-positive price/qty)."""
    if not isinstance(activity, dict):
        return None
    activity_id = activity.get("id")
    symbol = activity.get("symbol")
    side = str(activity.get("side") or "").lower()
    ts = activity.get("transaction_time")
    if not activity_id or not symbol or side not in ("buy", "sell") or not ts:
        return None
    try:
        price = float(activity.get("price") or 0)
        qty = float(activity.get("qty") or 0)
    except (TypeError, ValueError):
        return None
    if price <= 0 or qty <= 0:
        return None
    try:
        dt_utc = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except ValueError:
        return None
    ts_et = et_now(dt_utc)
    crypto = _is_crypto(symbol)
    order_id = activity.get("order_id")

    if arm in FLEET_REST_ARMS:
        attribution = "manual" if crypto else "engine"
    elif arm in CORE_ARMS:
        attribution = "manual" if crypto else (
            "engine" if engine_ids and order_id in engine_ids else "manual")
    else:
        attribution = "manual"

    return {
        "activity_id": activity_id,
        "arm": arm,
        "order_id": order_id,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "price": price,
        "multiplier": _multiplier(symbol),
        "is_crypto": crypto,
        "is_option": _is_option(symbol),
        "ts_utc": dt_utc.isoformat().replace("+00:00", "Z"),
        "ts_et": ts_et.isoformat(),
        "date_et": ts_et.strftime("%Y-%m-%d"),
        "attribution": attribution,
    }


def load_existing_ledger(ledger_path: Path = LEDGER) -> "tuple[list[dict], set]":
    if not ledger_path.exists():
        return [], set()
    rows: list = []
    ids: set = set()
    with ledger_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            rows.append(r)
            if r.get("activity_id"):
                ids.add(r["activity_id"])
    return rows, ids


def append_new_fills(new_fills: list, ledger_path: Path = LEDGER) -> int:
    if not new_fills:
        return 0
    with ledger_path.open("a", encoding="utf-8") as fh:
        for f in new_fills:
            fh.write(json.dumps(f) + "\n")
    return len(new_fills)


def promote_ledger_attribution(rows: list, engine_ids_by_account: dict) -> "tuple[list, int]":
    """PURE, promote-only attribution self-heal for already-written ledger rows: a core-arm
    (safe-2/bold-2) non-crypto row still tagged "manual" whose order_id is NOW a known engine
    order id flips to "engine". Returns (new row list, n promoted) -- input rows are never
    mutated; changed rows are copies. NEVER demotes engine->manual: engine attribution, once
    earned by an id match, is durable even if core-decisions.jsonl is later pruned/rotated.
    Heals both the pre-2026-07-09 extra_exec blind spot and any row appended by an intraday
    fire before its decision row (e.g. a later exit_pass append) reached core-decisions."""
    out: list = []
    promoted = 0
    for r in rows:
        acct = CORE_ARMS.get(r.get("arm"))
        if (acct is not None and r.get("attribution") == "manual" and not r.get("is_crypto")
                and r.get("order_id") in engine_ids_by_account.get(acct, set())):
            out.append({**r, "attribution": "engine"})
            promoted += 1
        else:
            out.append(r)
    return out, promoted


def rewrite_ledger(rows: list, ledger_path: Path = LEDGER) -> None:
    """Atomic full rewrite (tmp + os.replace) -- used only on a run where the promote pass
    changed rows, so a concurrent reader never sees a half-written ledger."""
    tmp = ledger_path.with_name(ledger_path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    tmp.replace(ledger_path)


def fifo_round_trips(fills: list) -> "tuple[list[dict], list[dict]]":
    """FIFO-match opposite-side fills per (arm, symbol), sorted by ts_utc. PURE -- no I/O.
    A same-side fill while lots are open just adds to the open-lot queue (scale-in);
    an opposite-side fill consumes the oldest open lot(s) first, producing one round-trip
    row per matched chunk (so a partial exit against a multi-lot entry yields >=1 rows)."""
    by_key: dict = defaultdict(list)
    for f in fills:
        by_key[(f["arm"], f["symbol"])].append(f)

    round_trips: list = []
    open_lots_out: list = []
    for _key, group in by_key.items():
        group_sorted = sorted(group, key=lambda x: x["ts_utc"])
        open_lots: deque = deque()
        for f in group_sorted:
            remaining = f["qty"]
            while remaining > 1e-9 and open_lots and open_lots[0]["side"] != f["side"]:
                lot = open_lots[0]
                matched = min(lot["qty"], remaining)
                entry, exitf = (lot, f) if lot["side"] == "buy" else (f, lot)
                pnl = (exitf["price"] - entry["price"]) * matched * f["multiplier"]
                round_trips.append({
                    "arm": f["arm"], "symbol": f["symbol"],
                    "entry_activity_id": entry["activity_id"],
                    "exit_activity_id": exitf["activity_id"],
                    "entry_price": entry["price"], "exit_price": exitf["price"], "qty": matched,
                    "pnl": round(pnl, 2), "entry_ts_et": entry["ts_et"], "exit_ts_et": exitf["ts_et"],
                    "attribution": f["attribution"], "date_et": exitf["date_et"],
                })
                lot["qty"] -= matched
                remaining -= matched
                if lot["qty"] <= 1e-9:
                    open_lots.popleft()
            if remaining > 1e-9:
                open_lots.append({**f, "qty": remaining})
        open_lots_out.extend(open_lots)
    return round_trips, open_lots_out


def build_statement(round_trips: list, open_lots: list) -> dict:
    """Per-account + per-day n_round_trips / realized P&L / engine-vs-manual split. PURE."""
    per_account: dict = {}
    per_day: dict = {}
    for rt in round_trips:
        arm, day, attr, pnl = rt["arm"], rt["date_et"], rt["attribution"], rt["pnl"]
        a = per_account.setdefault(arm, {"n_round_trips": 0, "realized_pnl": 0.0,
                                          "engine_pnl": 0.0, "manual_pnl": 0.0,
                                          "n_engine": 0, "n_manual": 0})
        a["n_round_trips"] += 1
        a["realized_pnl"] += pnl
        a["engine_pnl" if attr == "engine" else "manual_pnl"] += pnl
        a["n_engine" if attr == "engine" else "n_manual"] += 1

        da = per_day.setdefault(day, {}).setdefault(
            arm, {"n_round_trips": 0, "realized_pnl": 0.0, "engine_pnl": 0.0, "manual_pnl": 0.0})
        da["n_round_trips"] += 1
        da["realized_pnl"] += pnl
        da["engine_pnl" if attr == "engine" else "manual_pnl"] += pnl

    for a in per_account.values():
        for k in ("realized_pnl", "engine_pnl", "manual_pnl"):
            a[k] = round(a[k], 2)
    for d in per_day.values():
        for arm_stats in d.values():
            for k in ("realized_pnl", "engine_pnl", "manual_pnl"):
                arm_stats[k] = round(arm_stats[k], 2)

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "per_account": per_account,
        "per_day": per_day,
        "n_open_lots": len(open_lots),
        "open_lots": open_lots,
        "total_engine_pnl": round(sum(a["engine_pnl"] for a in per_account.values()), 2),
        "total_manual_pnl": round(sum(a["manual_pnl"] for a in per_account.values()), 2),
        "total_realized_pnl": round(sum(a["realized_pnl"] for a in per_account.values()), 2),
        "note": ("Broker-truth (Alpaca /v2/account/activities/FILL). Decision ledgers "
                 "(decisions.jsonl / core-decisions.jsonl / fleet/*/decisions.jsonl) are "
                 "DECISIONS-only -- fills/P&L must always be read from here, per "
                 "HANDOFF-2026-07-09-TRUTH-AND-EXITS ground rule 2."),
    }


def _starting_equity_by_arm() -> dict:
    if not ACCOUNTS_JSON.exists():
        return {}
    data = json.loads(ACCOUNTS_JSON.read_text(encoding="utf-8"))
    return {a["id"]: a.get("starting_equity") for a in data.get("arms", []) if a.get("id")}


def verify_against_broker_equity(statement: dict, creds_all: dict) -> None:
    """Self-check (not written to the statement file, printed only): for the 4 fleet_rest
    arms, compare ledger-derived realized P&L against the LIVE broker equity delta
    (current_equity - starting_equity). These won't match exactly (open-lot unrealized
    P&L, and the ledger's realized P&L excludes anything still open) but should be in the
    same ballpark -- a large divergence means the ledger is missing fills."""
    starting = _starting_equity_by_arm()
    print("[broker_fills] verify vs live broker equity (fleet_rest arms):")
    for arm in FLEET_REST_ARMS:
        creds = creds_all.get(arm)
        start_eq = starting.get(arm)
        if not creds or start_eq is None:
            continue
        acct = fb.get_account(creds)
        if acct.get("_error"):
            print(f"  {arm}: broker fetch error {acct.get('_error')}")
            continue
        try:
            current_eq = float(acct.get("equity"))
        except (TypeError, ValueError):
            continue
        equity_delta = round(current_eq - float(start_eq), 2)
        ledger_realized = statement["per_account"].get(arm, {}).get("realized_pnl", 0.0)
        print(f"  {arm}: starting={start_eq} current={current_eq} "
              f"equity_delta={equity_delta} ledger_realized_pnl={ledger_realized}")


def main() -> int:
    creds_all = fb.load_creds()
    existing_rows, existing_ids = load_existing_ledger()

    engine_ids_by_account = {acct: engine_order_ids(acct) for acct in CORE_ARMS.values()}
    existing_rows, n_promoted = promote_ledger_attribution(existing_rows, engine_ids_by_account)

    new_fills = []
    for arm, creds in creds_all.items():
        if arm not in FLEET_REST_ARMS and arm not in CORE_ARMS:
            continue  # skip futures-sandbox placeholder arms -- out of scope for SPY fills
        engine_ids = engine_ids_by_account.get(CORE_ARMS.get(arm)) if arm in CORE_ARMS else None
        activities = fetch_fill_activities(creds, BACKFILL_SINCE)
        for a in activities:
            if not isinstance(a, dict) or a.get("id") in existing_ids:
                continue
            norm = normalize_fill(a, arm, engine_ids)
            if norm is None:
                continue
            new_fills.append(norm)
            existing_ids.add(norm["activity_id"])

    all_fills = existing_rows + new_fills
    if n_promoted:
        rewrite_ledger(all_fills)  # promoted rows exist only in memory -> full atomic rewrite
        appended = len(new_fills)
        print(f"[broker_fills] re-attributed {n_promoted} ledger rows manual->engine "
              f"(promote-only self-heal: extra_exec / late decision rows)")
    else:
        appended = append_new_fills(new_fills)
    round_trips, open_lots = fifo_round_trips(all_fills)
    statement = build_statement(round_trips, open_lots)
    statement["round_trips"] = round_trips
    STATEMENT.write_text(json.dumps(statement, indent=2), encoding="utf-8")

    print(f"[broker_fills] {len(all_fills)} total fills ({appended} new this run), "
          f"{len(round_trips)} round trips, {len(open_lots)} open lots")
    print(f"[broker_fills] total_engine_pnl={statement['total_engine_pnl']} "
          f"total_manual_pnl={statement['total_manual_pnl']} "
          f"total_realized_pnl={statement['total_realized_pnl']}")
    verify_against_broker_equity(statement, creds_all)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""order_intent_log -- the ORDER-INTENT LEDGER: every order's WHY, keyed by order_id.

WHY THIS EXISTS (J, 2026-08-19):
  "Every single entry, every exit -- if we had ten contracts, I wanna know what each ten
  contract did at what time and why it did that."

  automation/state/fills-ledger.jsonl is BROKER ECHO: activity_id, order_id, symbol, side,
  qty, price, ts. It answers WHAT filled. It has never carried a single field explaining WHY
  that leg fired -- not the exit reason, not which of the N contracts this leg was, not the
  quote we crossed, not the underlying at that instant, not which entry an exit closed.
  Five exits in the entire book (the fleet_eod / eod_flatten force-flattens) have NO logged
  reason ANYWHERE, one of them risky-1's -$440 on 2026-08-10 -- the second-largest loss in
  the book, and we cannot say why it exited.

  Storage was never the constraint (the whole fills ledger is 416 KB). We simply never wrote
  the fields. This module writes them, at the moment of submit, in the engine's own words.

THE CONTRACT
  * ONE row per SUBMIT (not per fill), keyed by order_id, appended to
    automation/state/order-intents.jsonl.
  * The fills ledger JOINS to it on order_id, so every FILL LEG inherits its WHY.
  * A submit the broker REJECTED still writes a row (order_id=null, submit_status=REJECTED)
    -- a refused order is exactly the kind of thing we lose today.

WARNING -- THIS RUNS ON THE LIVE ORDER PATH. Three rules, all enforced here, all guarded:

  1. IT CAN NEVER RAISE. `record_submit` is total: any exception from any cause -- full
     disk, unwritable path, unserialisable input, NaN, circular reference, a caller passing
     nonsense -- is swallowed. A logging failure must never cost a trade. The signature is
     **fields (no required positional args) so even a WRONG CALL cannot TypeError into an
     order submission. Guard: test_order_intent_log_2026_08_19.py.
  2. IT NEVER TOUCHES THE ORDER. Every call site invokes this AFTER the order payload is
     built and (where possible) after the POST returns. It is passed what was already
     computed; it never prices, sizes, routes, or times anything. Guard:
     test_order_intent_log_2026_08_19.py::TestOrderPathUnchanged asserts the submitted
     payload is byte-identical before/after this wiring.
  3. IT ADDS NO NETWORK CALL. nbbo/spy are only recorded when the submit path ALREADY had
     them in hand (it usually does -- it priced the order off them). When they are not in
     hand we write null and SAY SO via nbbo_source, rather than slowing an entry with a
     telemetry-only quote fetch.

PROVENANCE IS PART OF THE RECORD, NOT AN AFTERTHOUGHT
  Fields recovered by the backfill joiner carry "logged" / "derived" / "unknown" tags. A
  field we could not recover comes out "unknown" -- never a silent null, never a guess
  dressed as a fact.

CLI
  python setup/scripts/order_intent_log.py --verify   # ledger stats + schema check
  python setup/scripts/order_intent_log.py --join     # join fills -> intents, print recovery
"""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Iterable, Iterator

_SCRIPTS = Path(__file__).resolve().parent
_REPO = _SCRIPTS.parents[1]

SCHEMA = "order-intent/1"
INTENTS_PATH = _REPO / "automation" / "state" / "order-intents.jsonl"
FILLS_PATH = _REPO / "automation" / "state" / "fills-ledger.jsonl"
ENRICHED_PATH = _REPO / "automation" / "state" / "fills-enriched.jsonl"

# Env override so tests (and a dry run) never touch the production ledger.
_PATH_ENV = "GAMMA_ORDER_INTENTS_PATH"

# Provenance vocabulary. Anything reconstructed carries exactly one of these.
PROV_LOGGED = "logged"      # came from a real record written at the time
PROV_DERIVED = "derived"    # inferred from a join; the join is named in provenance_note
PROV_UNKNOWN = "unknown"    # could not be recovered. NOT a null. NOT a guess.

# Roles a leg can play -- "which of the 10 contracts was this".
ROLE_CORE = "core"          # the entry leg itself
ROLE_TP1 = "tp1"            # the scale-out tranche
ROLE_RUNNER = "runner"      # the remainder riding for the runner target
ROLE_FLATTEN = "flatten"    # force-closed by the EOD sweep
ROLE_MANUAL = "manual"      # J-originated / adopted
ROLE_UNKNOWN = "unknown"

# Keys every call site is expected to supply. A row missing any of them is still WRITTEN
# (never dropped -- a partial record beats no record) but flags itself via "_incomplete",
# so a gap is visible in the ledger instead of silently becoming a null.
REQUIRED_FIELDS = ("arm", "symbol", "side", "qty", "leg_role", "intent", "reason", "source")


# --------------------------------------------------------------------------------------
# internals -- every one of these is reached only from inside the total try/except
# --------------------------------------------------------------------------------------

def _intents_path(explicit: Any = None) -> Path:
    if explicit:
        return Path(str(explicit))
    env = os.environ.get(_PATH_ENV)
    if env:
        return Path(env)
    return INTENTS_PATH


def _now_parts() -> "dict[str, Any]":
    """ET/UTC stamps via the DST-aware et_clock (this box runs Mountain -- a naive now() is
    2h wrong year-round; the TZ-SYSTEMIC scar). Degrades to nulls rather than raising."""
    out: dict[str, Any] = {"ts_et": None, "ts_utc": None, "date_et": None}
    try:
        from datetime import datetime, timezone  # noqa: PLC0415
        out["ts_utc"] = datetime.now(timezone.utc).isoformat()
    except Exception:  # noqa: BLE001
        pass
    try:
        if str(_SCRIPTS) not in sys.path:
            sys.path.insert(0, str(_SCRIPTS))
        from et_clock import et_now  # noqa: PLC0415
        et = et_now()
        out["ts_et"] = et.isoformat()
        out["date_et"] = et.strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        pass
    return out


def _num(v: Any) -> Any:
    """Finite float, or None. json.dumps happily emits NaN/Infinity, which is INVALID JSON --
    one NaN would make the row unreadable by every consumer downstream."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _sanitize(obj: Any, depth: int = 0) -> Any:
    """Make any input JSON-safe WITHOUT losing it. An unserialisable object becomes its repr
    (truncated) rather than killing the row. Depth- and width-capped so a self-referential
    or enormous structure cannot recurse forever or blow the line size."""
    if depth > 6:
        return "<depth-capped>"
    if obj is None or isinstance(obj, (bool, int, str)):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        out = {}
        for k, v in list(obj.items())[:60]:
            try:
                out[str(k)] = _sanitize(v, depth + 1)
            except Exception:  # noqa: BLE001
                out[str(k)] = "<unserialisable>"
        return out
    if isinstance(obj, (list, tuple, set)):
        try:
            return [_sanitize(v, depth + 1) for v in list(obj)[:60]]
        except Exception:  # noqa: BLE001
            return "<unserialisable-sequence>"
    try:
        return repr(obj)[:300]
    except Exception:  # noqa: BLE001
        return "<unreprable>"


def _order_ids(broker_response: Any) -> "tuple[Any, Any, str, Any]":
    """(order_id, client_order_id, submit_status, submit_error) from a broker response.

    fleet_broker._request returns the raw Alpaca order dict on success, or a dict carrying
    _error/_status/_body on an HTTP/network failure; the placement wrappers add _refused /
    _skipped for their own pre-flight vetoes. All four shapes are recorded DISTINCTLY --
    "the broker said no" and "we refused to ask" are different facts."""
    if not isinstance(broker_response, dict):
        return None, None, "UNKNOWN", (repr(broker_response)[:200]
                                       if broker_response is not None else None)
    if broker_response.get("_refused"):
        return None, None, "REFUSED", str(broker_response.get("_refused"))[:300]
    if broker_response.get("_skipped"):
        return None, None, "SKIPPED", str(broker_response.get("_skipped"))[:300]
    if broker_response.get("_error"):
        return None, None, "REJECTED", str(broker_response.get("_error"))[:300]
    oid = broker_response.get("id")
    coid = broker_response.get("client_order_id")
    return ((str(oid) if oid else None), (str(coid) if coid else None),
            ("ACCEPTED" if oid else "UNKNOWN"), None)


def _build_row(fields: "dict[str, Any]") -> "dict[str, Any]":
    """Assemble the record. Pure; the caller owns the try/except."""
    broker_response = fields.pop("broker_response", None)
    oid, coid, status, err = _order_ids(broker_response)
    # An explicit order_id/status always wins over the sniffed one (a caller that already
    # knows better -- e.g. the flatten loop, which holds each per-symbol response).
    row: dict[str, Any] = {
        "schema": SCHEMA,
        "order_id": (str(fields.pop("order_id", None) or "") or oid),
        "client_order_id": (str(fields.pop("client_order_id", None) or "") or coid),
        "submit_status": (str(fields.pop("submit_status", None) or "") or status),
        "submit_error": (fields.pop("submit_error", None) or err),
    }
    row.update(_now_parts())
    row["arm"] = fields.pop("arm", None)
    row["symbol"] = fields.pop("symbol", None)
    row["side"] = fields.pop("side", None)
    row["qty"] = fields.pop("qty", None)
    row["leg_role"] = fields.pop("leg_role", ROLE_UNKNOWN)
    row["intent"] = fields.pop("intent", None)          # ENTRY | EXIT
    row["reason"] = fields.pop("reason", None)          # the engine's OWN words
    row["strategy"] = fields.pop("strategy", None)
    row["decision_tick_id"] = fields.pop("decision_tick_id", None)
    row["entry_link"] = fields.pop("entry_link", None)  # which entry an exit closes
    row["source"] = fields.pop("source", None)          # module.function that submitted
    row["limit_price"] = _num(fields.pop("limit_price", None))
    row["order_type"] = fields.pop("order_type", None)

    nbbo = fields.pop("nbbo", None)
    if isinstance(nbbo, dict):
        row["nbbo_bid"] = _num(nbbo.get("bid"))
        row["nbbo_ask"] = _num(nbbo.get("ask"))
        row["nbbo_mid"] = _num(nbbo.get("mid"))
        row["nbbo_source"] = nbbo.get("source")
        fields.pop("nbbo_bid", None)
        fields.pop("nbbo_ask", None)
        fields.pop("nbbo_mid", None)
        fields.pop("nbbo_source", None)
    else:
        row["nbbo_bid"] = _num(fields.pop("nbbo_bid", None))
        row["nbbo_ask"] = _num(fields.pop("nbbo_ask", None))
        row["nbbo_mid"] = _num(fields.pop("nbbo_mid", None))
        row["nbbo_source"] = fields.pop("nbbo_source", None)
    if row["nbbo_bid"] is None and row["nbbo_ask"] is None and not row["nbbo_source"]:
        # HONEST ABSENCE. Not "we forgot" -- "this path did not have a quote in hand, and we
        # refuse to add a blocking fetch to the hot path for telemetry."
        row["nbbo_source"] = "not_in_hand_at_submit"
    row["spy_at_submit"] = _num(fields.pop("spy_at_submit", None))

    exit_state = fields.pop("exit_state", None)
    row["exit_state"] = _sanitize(exit_state) if exit_state else None

    # A leg_role that fell through to ROLE_UNKNOWN counts as MISSING, not as a value. An
    # unlabelled leg is precisely the gap this ledger exists to close, so it must show up in
    # _incomplete rather than reading as a legitimately-recorded "unknown".
    missing = [k for k in REQUIRED_FIELDS
               if row.get(k) in (None, "") or (k == "leg_role" and row.get(k) == ROLE_UNKNOWN)]
    if missing:
        row["_incomplete"] = missing
    if fields:
        row["extra"] = _sanitize(fields)
    return row


# --------------------------------------------------------------------------------------
# THE WRITER -- the only thing the live order path calls
# --------------------------------------------------------------------------------------

def record_submit(**fields: Any) -> None:
    """Append ONE order-intent row. TOTAL: never raises, never blocks, always returns None.

    Expected keys (all optional at the type level -- see rule #1 in the module docstring; a
    missing one is flagged in-row as "_incomplete", never dropped):

      arm              "safe-2" | "bold-2" | "safe-3" | "risky-1" | "risky-3" | ...
      symbol           OCC option symbol
      side             "buy" | "sell"
      qty              contracts submitted
      leg_role         core | tp1 | runner | flatten | manual  (which of the N contracts)
      intent           "ENTRY" | "EXIT"
      reason           the engine's OWN words for why this fired
      source           "module.function" that submitted -- the audit trail back to code
      broker_response  the raw response dict; order_id/client_order_id/status read off it
      decision_tick_id the engine tick that caused this order
      nbbo             {"bid","ask","mid","source"} IF already in hand (never fetched here)
      spy_at_submit    underlying at submit IF already in hand
      exit_state       {"stop_premium","target_premium","hwm",...} on an exit
      entry_link       the entry order_id this exit closes
      strategy, limit_price, order_type, path=<override ledger path>

    Anything else passed lands under "extra" verbatim (sanitised), so a call site can add a
    field without touching this module.
    """
    try:
        f = dict(fields)                      # never mutate the caller's dict
        path = _intents_path(f.pop("path", None))
        row = _build_row(f)
        line = json.dumps(row, default=lambda o: repr(o)[:300], allow_nan=False)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:  # noqa: BLE001 -- an unwritable dir is still not worth a lost trade
            pass
        with path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")            # ONE write: O_APPEND keeps concurrent arms sane
    except Exception:  # noqa: BLE001 -- THE POINT OF THIS FUNCTION. See module docstring #1.
        return None
    return None


# --------------------------------------------------------------------------------------
# THE JOINER -- fills-ledger x order-intents, with provenance on every field
# --------------------------------------------------------------------------------------

ENRICHED_FIELDS = ("exit_reason", "leg_role", "nbbo_bid", "nbbo_ask", "spy_at_fill",
                   "entry_link", "decision_tick_id")


def read_jsonl_counted(path: "str | Path") -> "tuple[list[dict], int]":
    """(rows, malformed_count). A malformed line is SKIPPED, never fatal -- and never
    silently pretended away: the count comes back so the caller can report it."""
    rows: list[dict] = []
    bad = 0
    p = Path(path)
    if not p.exists():
        return rows, bad
    with p.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                bad += 1
                continue
            if isinstance(obj, dict):
                rows.append(obj)
            else:
                bad += 1
    return rows, bad


def read_jsonl(path: "str | Path") -> "list[dict]":
    rows, _ = read_jsonl_counted(path)
    return rows


def load_intents(path: "str | Path | None" = None) -> "dict[str, dict]":
    """{order_id: intent_row}. Last write wins (a re-submitted id is the newer truth)."""
    out: dict[str, dict] = {}
    for row in read_jsonl(_intents_path(path)):
        oid = row.get("order_id")
        if oid:
            out[str(oid)] = row
    return out


def enrich_fill(fill: dict, intents: "dict[str, dict]") -> dict:
    """One fills-ledger leg + everything we can HONESTLY say about why it fired.

    Provenance rules, applied without exception:
      logged   -- an order-intent row written at submit time carried this field
      derived  -- reconstructed from a join; the join is NAMED in provenance_note
      unknown  -- not recoverable. Emitted as an explicit "unknown" tag with value None.
                  This is the honest answer for the force-flatten exits, and it is the point.
    """
    out = dict(fill)
    oid = str(fill.get("order_id") or "")
    intent = intents.get(oid)
    prov: dict[str, str] = {}
    note: dict[str, str] = {}

    if intent is None:
        for k in ENRICHED_FIELDS:
            out[k] = None
            prov[k] = PROV_UNKNOWN
            note[k] = ("no order-intent row for this order_id "
                       "(order predates the intent ledger)")
        out["intent_matched"] = False
    else:
        out["intent_matched"] = True
        src = f"order-intents.jsonl order_id={oid}"
        pairs = (
            ("exit_reason", intent.get("reason") if intent.get("intent") == "EXIT" else None),
            ("leg_role", intent.get("leg_role")),
            ("nbbo_bid", intent.get("nbbo_bid")),
            ("nbbo_ask", intent.get("nbbo_ask")),
            ("spy_at_fill", intent.get("spy_at_submit")),
            ("entry_link", intent.get("entry_link")),
            ("decision_tick_id", intent.get("decision_tick_id")),
        )
        for k, v in pairs:
            out[k] = v
            if v is None or v == ROLE_UNKNOWN:
                prov[k] = PROV_UNKNOWN
                note[k] = f"{src} exists but carries no value for this field"
            else:
                prov[k] = PROV_LOGGED
                note[k] = src
        out["entry_reason"] = (intent.get("reason")
                               if intent.get("intent") == "ENTRY" else None)
        out["exit_state_at_submit"] = intent.get("exit_state")
        out["submit_source"] = intent.get("source")

    out["provenance"] = prov
    out["provenance_note"] = note
    return out


def join_fills(fills: "Iterable[dict]", intents: "dict[str, dict]") -> "Iterator[dict]":
    for fill in fills:
        yield enrich_fill(fill, intents)


def recovery_rate(enriched: "Iterable[dict]") -> dict:
    """Per-field {logged, derived, unknown, recovered, pct_recovered} over enriched rows."""
    counts: dict[str, dict[str, int]] = {}
    total = 0
    for row in enriched:
        total += 1
        prov = row.get("provenance") or {}
        for field, tag in prov.items():
            b = counts.setdefault(field, {PROV_LOGGED: 0, PROV_DERIVED: 0, PROV_UNKNOWN: 0})
            if tag in b:
                b[tag] += 1
    out: dict[str, Any] = {"total_legs": total, "fields": {}}
    for field, b in sorted(counts.items()):
        rec = b[PROV_LOGGED] + b[PROV_DERIVED]
        out["fields"][field] = dict(
            b, recovered=rec,
            pct_recovered=(round(100.0 * rec / total, 1) if total else 0.0))
    return out


# --------------------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------------------

def _cli(argv: "list[str]") -> int:
    if "--join" in argv:
        fills, bad = read_jsonl_counted(FILLS_PATH)
        intents = load_intents()
        enriched = list(join_fills(fills, intents))
        print(json.dumps(recovery_rate(enriched), indent=2))
        if bad:
            print(f"WARN: {bad} malformed line(s) skipped in {FILLS_PATH.name}")
        return 0
    rows, bad = read_jsonl_counted(_intents_path())
    accepted = sum(1 for r in rows if r.get("submit_status") == "ACCEPTED")
    incomplete = sum(1 for r in rows if r.get("_incomplete"))
    roles: dict[str, int] = {}
    for r in rows:
        roles[str(r.get("leg_role"))] = roles.get(str(r.get("leg_role")), 0) + 1
    print(json.dumps({"path": str(_intents_path()), "rows": len(rows), "malformed": bad,
                      "accepted": accepted, "incomplete_rows": incomplete,
                      "by_leg_role": roles}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))

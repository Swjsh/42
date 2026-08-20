"""backfill_fills_enriched -- reconstruct WHY for the 1,040 historical fill legs.

WHY (J, 2026-08-19): "I thought we were logging all this, dude."
  Going forward, order_intent_log.record_submit writes the WHY at submit time. This script
  answers the other half: how much of the WHY behind the legs we ALREADY FILLED can be
  honestly recovered from what the engine happened to write down at the time.

WHAT IT JOINS (exact key paths, mapped from the real logs -- not guessed):
  automation/state/fills-ledger.jsonl        1,040 legs, keyed by order_id
    x automation/state/order-intents.jsonl   the new forward ledger  -> provenance "logged"
    x automation/state/core-decisions.jsonl  safe-2 / bold-2         -> provenance "derived"
        entries  exec.broker.id  and  extra_exec[i].exec.broker.id
        exits    exit_pass[i].actions[j].broker.id
    x automation/state/fleet/{arm}/decisions.jsonl   safe-1/3, risky-1/3 -> "derived"
        entries  placement.broker.id
        exits    exit_pass[i].actions[j].broker.id

THE PROVENANCE RULE, NO EXCEPTIONS
  logged   an order-intent row written AT SUBMIT carried this field.
  derived  reconstructed from a join. The join is NAMED in provenance_note, and where the
           derived value is not literally the thing the field is named after, the note SAYS
           SO (the clearest case: `spy_at_fill` derived from a decision row is the tick's
           DECISION-TIME spot, not the underlying at the instant of fill -- those differ, and
           pretending otherwise would be exactly the fake precision this build exists to end).
  unknown  not recoverable. Emitted as an explicit tag with a null value -- NEVER a silent
           null, never a guess. The force-flatten exits come out unknown. That is the honest
           answer and it is the point.

WHAT IS PERMANENTLY UNKNOWABLE, and why
  * Exits placed by fleet_broker.close_all_spy_options (the EOD force-flatten). It recorded
    only the SYMBOL in its `closed` list and threw the broker response -- order_id included --
    away. No log anywhere ever held those ids, so no join can recover them. Fixed FORWARD by
    the order-intent row now written inside that function; the historical ones stay unknown.
  * True nbbo AT FILL, for every historical leg. The engine only ever recorded a
    pre-submit quote reconstruction, and only on 77 of 29,651 core rows. A fill-time quote
    was never captured and cannot be back-derived from a fill price.
  * J's own manual trades: correctly outside the engine decision logs.

USAGE
  python setup/scripts/backfill_fills_enriched.py            # write fills-enriched.jsonl
  python setup/scripts/backfill_fills_enriched.py --dry-run  # report only, write nothing
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Iterator

_SCRIPTS = Path(__file__).resolve().parent
_REPO = _SCRIPTS.parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import order_intent_log as oil  # noqa: E402

STATE = _REPO / "automation" / "state"
FILLS = STATE / "fills-ledger.jsonl"
CORE_DECISIONS = STATE / "core-decisions.jsonl"
FLEET_DIR = STATE / "fleet"
FLEET_ARMS = ("safe-1", "safe-3", "risky-1", "risky-3")
OUT = STATE / "fills-enriched.jsonl"

# core-decisions' `account` -> the fills-ledger `arm` value.
_CORE_ACCOUNT_TO_ARM = {"safe": "safe-2", "bold": "bold-2"}


def _iter_jsonl(path: Path) -> "Iterator[dict]":
    """Stream a .jsonl. core-decisions.jsonl is ~68 MB; never read it whole."""
    if not path.exists():
        return
    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except (ValueError, TypeError):
                continue
            if isinstance(obj, dict):
                yield obj


def _bid(node: Any) -> "str | None":
    """The broker order id hanging off a placement/action node, or None."""
    if not isinstance(node, dict):
        return None
    b = node.get("broker")
    if isinstance(b, dict) and b.get("id"):
        return str(b["id"])
    return None


def _index_core(path: Path) -> "dict[str, dict]":
    """{order_id: derivation record} from core-decisions.jsonl (safe-2 / bold-2)."""
    idx: dict[str, dict] = {}
    for row in _iter_jsonl(path):
        arm = _CORE_ACCOUNT_TO_ARM.get(str(row.get("account") or ""), None)
        tick = row.get("core_tick_id") or row.get("ts_et")
        base = {"arm": arm, "ts_et": row.get("ts_et"), "tick_id": tick,
                "spy": row.get("spy"), "setup": row.get("setup"),
                "log": "core-decisions.jsonl"}

        # --- ENTRIES: exec.broker.id, and extra_exec[i].exec.broker.id (multi-setup ticks)
        execs = []
        if isinstance(row.get("exec"), dict):
            execs.append(("exec", row["exec"]))
        for i, xe in enumerate(row.get("extra_exec") or []):
            if isinstance(xe, dict) and isinstance(xe.get("exec"), dict):
                execs.append((f"extra_exec[{i}].exec", xe["exec"]))
        for keypath, ex in execs:
            oid = _bid(ex)
            if not oid:
                continue
            nbbo = ex.get("nbbo") if isinstance(ex.get("nbbo"), dict) else {}
            idx[oid] = dict(base, kind="ENTRY", keypath=f"{keypath}.broker.id",
                            reason=(f"{row.get('verdict') or '?'} "
                                    f"{ex.get('setup') or row.get('setup') or '?'}").strip(),
                            nbbo_bid=nbbo.get("bid"), nbbo_ask=nbbo.get("ask"),
                            leg_role=oil.ROLE_CORE)

        # --- EXITS: exit_pass[i].actions[j].broker.id
        for i, ep in enumerate(row.get("exit_pass") or []):
            if not isinstance(ep, dict):
                continue
            for j, a in enumerate(ep.get("actions") or []):
                oid = _bid(a)
                if not oid:
                    continue
                idx[oid] = dict(base, kind="EXIT",
                                keypath=f"exit_pass[{i}].actions[{j}].broker.id",
                                reason=(f"{a.get('kind') or '?'}:{a.get('stage') or '?'} "
                                        f"{a.get('reason') or ''}").strip(),
                                action_kind=a.get("kind"), stage=a.get("stage"),
                                symbol=ep.get("symbol"), nbbo_bid=None, nbbo_ask=None)
    return idx


def _index_fleet(arm: str) -> "dict[str, dict]":
    """{order_id: derivation record} from one fleet arm's decisions.jsonl."""
    idx: dict[str, dict] = {}
    path = FLEET_DIR / arm / "decisions.jsonl"
    for row in _iter_jsonl(path):
        base = {"arm": row.get("arm_id") or arm, "ts_et": row.get("ts_et"),
                "tick_id": row.get("tick_id") or row.get("core_tick_id"),
                "spy": None, "setup": row.get("setup_name"),
                "log": f"fleet/{arm}/decisions.jsonl"}
        oid = _bid(row.get("placement"))
        if oid:
            idx[oid] = dict(base, kind="ENTRY", keypath="placement.broker.id",
                            reason=(f"{row.get('action') or '?'} "
                                    f"{row.get('setup_name') or '?'}").strip(),
                            nbbo_bid=None, nbbo_ask=None, leg_role=oil.ROLE_CORE)
        for i, ep in enumerate(row.get("exit_pass") or []):
            if not isinstance(ep, dict):
                continue
            for j, a in enumerate(ep.get("actions") or []):
                oid = _bid(a)
                if not oid:
                    continue
                idx[oid] = dict(base, kind="EXIT",
                                keypath=f"exit_pass[{i}].actions[{j}].broker.id",
                                reason=(f"{a.get('kind') or '?'}:{a.get('stage') or '?'} "
                                        f"{a.get('reason') or ''}").strip(),
                                action_kind=a.get("kind"), stage=a.get("stage"),
                                symbol=ep.get("symbol"), nbbo_bid=None, nbbo_ask=None)
    return idx


def build_decision_index() -> "dict[str, dict]":
    idx = _index_core(CORE_DECISIONS)
    for arm in FLEET_ARMS:
        idx.update(_index_fleet(arm))
    return idx


def _entry_link_map(fills: "list[dict]") -> "dict[str, str]":
    """{sell_order_id: the buy order_id it most plausibly closes}.

    THE JOIN, stated exactly: within one (arm, date_et, symbol), a SELL leg is linked to the
    LATEST BUY leg on that same contract at or before its timestamp. On this book that is a
    tight join -- an arm holds one 0DTE contract at a time by construction (the flat-verify
    gate refuses a second entry while one is open), so "the open position on this symbol" is
    unambiguous. It is still DERIVED, not logged: if an arm ever did hold two entries on the
    same symbol the same day, this would attribute the exit to the later one."""
    buys: dict[tuple, list[tuple[str, str]]] = {}
    for f in fills:
        if str(f.get("side")) != "buy":
            continue
        key = (f.get("arm"), f.get("date_et"), f.get("symbol"))
        buys.setdefault(key, []).append((str(f.get("ts_et") or ""), str(f.get("order_id") or "")))
    for v in buys.values():
        v.sort()
    out: dict[str, str] = {}
    for f in fills:
        if str(f.get("side")) != "sell":
            continue
        key = (f.get("arm"), f.get("date_et"), f.get("symbol"))
        ts = str(f.get("ts_et") or "")
        prior = [oid for (bts, oid) in buys.get(key, []) if bts <= ts and oid]
        if prior:
            out[str(f.get("order_id") or "")] = prior[-1]
    return out


def _derive_leg_role(rec: dict, fill: dict, seen_partial: set) -> "tuple[str, str]":
    """(leg_role, note). Which of the N contracts this leg was.

    Entries are the CORE leg. SELL_PARTIAL is the TP1 tranche. A SELL_ALL is the RUNNER if a
    TP1 partial already fired on this (arm, date, symbol), otherwise it closed the whole
    original position and is the CORE leg."""
    if rec.get("kind") == "ENTRY":
        return oil.ROLE_CORE, "entry placement record -> the core leg"
    kind = str(rec.get("action_kind") or "")
    if kind == "SELL_PARTIAL":
        return oil.ROLE_TP1, "exit action kind=SELL_PARTIAL -> the TP1 tranche"
    if kind == "SELL_ALL":
        key = (fill.get("arm"), fill.get("date_et"), fill.get("symbol"))
        if key in seen_partial:
            return oil.ROLE_RUNNER, ("exit action kind=SELL_ALL after a SELL_PARTIAL fired on "
                                     "this (arm,date,symbol) -> the runner remainder")
        return oil.ROLE_CORE, ("exit action kind=SELL_ALL with no prior SELL_PARTIAL on this "
                               "(arm,date,symbol) -> closed the whole original position")
    return oil.ROLE_UNKNOWN, f"exit action kind={kind or '?'} does not map to a known tranche"


def enrich(fills: "list[dict]", intents: "dict[str, dict]",
           decisions: "dict[str, dict]") -> "list[dict]":
    links = _entry_link_map(fills)
    # (arm, date, symbol) that saw a SELL_PARTIAL -- lets a later SELL_ALL be called a runner.
    seen_partial = {(f.get("arm"), f.get("date_et"), f.get("symbol"))
                    for f in fills
                    if str(decisions.get(str(f.get("order_id") or ""), {})
                           .get("action_kind") or "") == "SELL_PARTIAL"}
    out: list[dict] = []
    for fill in fills:
        oid = str(fill.get("order_id") or "")
        if oid in intents:
            # The forward path already recorded this at submit time -> "logged" throughout.
            out.append(oil.enrich_fill(fill, intents))
            continue

        row = dict(fill)
        prov: dict[str, str] = {}
        note: dict[str, str] = {}
        rec = decisions.get(oid)

        def _set(field: str, value: Any, tag: str, why: str) -> None:
            row[field] = value
            prov[field] = tag
            note[field] = why

        if rec is None:
            reason = ("no order-intent row and no decision-log row carries this order_id")
            if fill.get("is_crypto"):
                reason = ("crypto leg -- the decision logs are SPY-0DTE only, so this was "
                          "never in scope for an engine WHY")
            elif str(fill.get("attribution")) == "manual":
                reason = ("attribution=manual -- a hand-placed trade, correctly outside the "
                          "engine decision logs")
            for k in oil.ENRICHED_FIELDS:
                _set(k, None, oil.PROV_UNKNOWN, reason)
            row["intent_matched"] = False
            row["derivation_source"] = None
        else:
            row["intent_matched"] = False   # not from the intent ledger -- reconstructed
            row["derivation_source"] = f"{rec['log']} :: {rec['keypath']}"
            src = row["derivation_source"]
            if rec.get("kind") == "EXIT":
                _set("exit_reason", rec.get("reason"), oil.PROV_DERIVED,
                     f"join fills.order_id -> {src} (kind:stage reason, verbatim)")
            else:
                _set("exit_reason", None, oil.PROV_UNKNOWN,
                     "this leg is an ENTRY -- it has no exit reason by definition")
            role, role_note = _derive_leg_role(rec, fill, seen_partial)
            _set("leg_role", role, oil.PROV_DERIVED, f"join fills.order_id -> {src}: {role_note}")
            for f_, v_ in (("nbbo_bid", rec.get("nbbo_bid")), ("nbbo_ask", rec.get("nbbo_ask"))):
                if v_ is None:
                    _set(f_, None, oil.PROV_UNKNOWN,
                         ("no quote was recorded on this path (nbbo appears on only 77 of "
                          "29,651 core rows and never on exit actions); a fill-time quote "
                          "cannot be back-derived from a fill price"))
                else:
                    _set(f_, v_, oil.PROV_DERIVED,
                         (f"join fills.order_id -> {src} exec.nbbo -- this is the PRE-SUBMIT "
                          f"quote reconstruction the engine priced off, NOT the quote at fill"))
            if rec.get("spy") is None:
                _set("spy_at_fill", None, oil.PROV_UNKNOWN,
                     "no underlying price recorded on this log path")
            else:
                _set("spy_at_fill", rec.get("spy"), oil.PROV_DERIVED,
                     (f"join fills.order_id -> {src} row.spy -- this is the DECISION-TICK "
                      f"spot, NOT the underlying at the instant of fill; they differ"))
            tick = rec.get("tick_id")
            _set("decision_tick_id", tick,
                 oil.PROV_DERIVED if tick else oil.PROV_UNKNOWN,
                 (f"join fills.order_id -> {src} (row tick_id/core_tick_id)" if tick
                  else "the matched decision row carries no tick id"))

        link = links.get(oid)
        if str(fill.get("side")) == "sell" and link:
            row["entry_link"] = link
            prov["entry_link"] = oil.PROV_DERIVED
            note["entry_link"] = ("derived within (arm,date_et,symbol): the latest BUY leg at "
                                  "or before this SELL's timestamp -- see _entry_link_map")
        elif str(fill.get("side")) == "buy":
            row["entry_link"] = str(fill.get("order_id") or "") or None
            prov["entry_link"] = oil.PROV_DERIVED
            note["entry_link"] = "this leg IS the entry; it links to itself"
        else:
            row.setdefault("entry_link", None)
            prov["entry_link"] = oil.PROV_UNKNOWN
            note["entry_link"] = "no BUY leg on this (arm,date_et,symbol) precedes this SELL"

        row["provenance"] = prov
        row["provenance_note"] = note
        out.append(row)
    return out


def report(enriched: "list[dict]") -> dict:
    rr = oil.recovery_rate(enriched)
    # The all-legs numbers above are the honest denominator J asked for, but two of them read
    # better than they are and must not be quoted alone:
    #   * exit_reason is scored against BUY legs too, which have no exit reason by definition.
    #   * entry_link counts a BUY linking to itself, which is trivially true.
    # The cohort that actually answers "why did this exit fire, and which entry did it close"
    # is SPY-option SELL legs. Scored separately so neither number can flatter the other.
    spy_sells = [r for r in enriched
                 if not r.get("is_crypto") and str(r.get("side")) == "sell"]
    rr["spy_option_sell_legs_only"] = oil.recovery_rate(spy_sells)
    spy_legs = [r for r in enriched if not r.get("is_crypto")]
    engine_spy = [r for r in spy_legs if str(r.get("attribution")) == "engine"]
    unresolved = [r for r in engine_spy
                  if r.get("provenance", {}).get("exit_reason") == oil.PROV_UNKNOWN
                  and str(r.get("side")) == "sell"]
    rr["cohorts"] = {
        "all_legs": len(enriched),
        "crypto_legs_out_of_scope": len(enriched) - len(spy_legs),
        "spy_option_legs": len(spy_legs),
        "spy_manual_legs": len([r for r in spy_legs if str(r.get("attribution")) == "manual"]),
        "spy_engine_legs": len(engine_spy),
        "spy_engine_sells_with_no_recoverable_reason": len(unresolved),
    }
    rr["unrecoverable_engine_exits"] = [
        {"arm": r.get("arm"), "date_et": r.get("date_et"), "ts_et": r.get("ts_et"),
         "order_id": r.get("order_id"), "symbol": r.get("symbol"),
         "qty": r.get("qty"), "price": r.get("price")}
        for r in sorted(unresolved, key=lambda x: str(x.get("ts_et")))]
    return rr


def main(argv: "list[str] | None" = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="report only, write nothing")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    fills, bad = oil.read_jsonl_counted(FILLS)
    if not fills:
        print(json.dumps({"error": f"no fills read from {FILLS}"}))
        return 1
    intents = oil.load_intents()
    decisions = build_decision_index()
    enriched = enrich(fills, intents, decisions)
    rpt = report(enriched)
    rpt["malformed_fill_lines_skipped"] = bad
    rpt["order_intent_rows_available"] = len(intents)
    rpt["decision_log_order_ids_indexed"] = len(decisions)

    if not args.dry_run:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            for row in enriched:
                fh.write(json.dumps(row, default=str, allow_nan=False) + "\n")
        tmp.replace(out_path)   # atomic: a reader never sees a half-written ledger
        rpt["written"] = str(out_path)
    print(json.dumps(rpt, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

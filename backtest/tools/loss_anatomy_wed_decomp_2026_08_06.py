#!/usr/bin/env python
"""loss_anatomy_wed_decomp_2026_08_06.py -- LANE 0 / Q2: decompose 2026-08-05's -$1,935.00
of SPY-option engine loss into buckets that SUM, and reconcile against the prior audit's
"ENTRY-side 70.4% / EXIT-side 29.6%" split.

AUTHORITY: real broker fills (automation/state/fills-ledger.jsonl, attribution==engine) +
real OPRA 1-min bars fetched live (exit_shape_parity_study.fetch_option_bars). No synthetic
prices anywhere; no simulate_trade_real.

THE FIVE BUCKETS (brief's (a)..(e)), each defined as a COUNTERFACTUAL BOOK, never a label:
  (e) FRICTION      -- price every entry and exit fill at its OWN minute's real OPRA VWAP
                       instead of the price we actually got. What our execution cost vs the
                       volume-weighted average of the very same minute.
  (c) SIZE          -- scale every position to Rule 6's doctrinal floor of 3 contracts
                       (CLAUDE.md Rule 6: "Min 3 contracts (2 TP + 1 runner)"). Legs scale
                       pro-rata (3/qty); disclosed as linear-in-qty.
  (b) RE-ENTRY      -- keep only ordinal-1 of each (arm, symbol, date) wave. This is CAP-1,
                       strictly harsher than the CAP-3 lever under evaluation elsewhere.
  (d) EXIT-CONFIG   -- OBSERVED SIBLING EXECUTION, not a modelled replay. On SPY260805P00772000
                       three arms bought the identical contract inside 62 seconds at 1.69 /
                       1.65 / 1.63. risky-1 (TP1 +50% via exit_patch) realised +$69.40 per
                       contract. risky-3 and safe-2 (TP1 +100% from the ribbon_ride registry,
                       never reachable -- ask peaked 2.69/2.76) realised -$83.00 per contract.
                       The per-contract gap of $152.40 is charged to exit-config. Every number
                       is a real broker fill; nothing is simulated. NOTE this UNDER-states the
                       config effect, because risky-1 also paid the WORST entry of the three.
  (a) ENTRY LOCATION-- the RESIDUAL. What the day still costs after removing friction, after
                       sizing at the doctrinal minimum, after taking each signal exactly once,
                       and after giving every arm the best exit configuration that actually
                       existed in the fleet that day. This is the irreducible cost of the
                       decision to buy where we bought.

ORDER SENSITIVITY IS REPORTED, NOT HIDDEN (CLAUDE.md C15 -- levers interact multiplicatively).
Two full waterfalls are run in opposite orders and both are printed, plus every lever's
STANDALONE marginal effect. Only the declared-order waterfall is used for the headline split.

DESCRIPTIVE ONLY. Writes only analysis/deep-research/LOSS-ANATOMY-2026-08-06.json (merged).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "setup" / "scripts",
           REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import exit_shape_parity_study as esp  # noqa: E402

LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"
OUT_JSON = REPO / "analysis" / "deep-research" / "LOSS-ANATOMY-2026-08-06.json"
WED = "2026-08-05"
RULE6_MIN_CONTRACTS = 3.0
PUT = "SPY260805P00772000"
SIBLING_ARM = "risky-1"           # the arm whose exit_patch TP1 (+50%) actually fired


# ------------------------------------------------------------------ position model
def load_wed_positions() -> list[dict]:
    fills = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        r = json.loads(line)
        if (r.get("attribution") == "engine" and r.get("is_option")
                and not r.get("is_crypto") and r.get("date_et") == WED):
            fills.append(r)
    ts_et = {(f["arm"], f["symbol"], f["ts_utc"]): f["ts_et"] for f in fills}
    pos = [p for p in esp.reconstruct_positions(fills) if p["exit_fills"]]
    for p in pos:
        p["entry_ts_et"] = ts_et[(p["arm"], p["symbol"], p["entry_ts_utc"])]
        p["pnl"] = round(p["actual_exit_pnl"], 2)
    pos.sort(key=lambda p: (p["entry_ts_utc"], p["arm"]))
    seq: dict = defaultdict(int)
    for p in pos:
        seq[(p["arm"], p["symbol"])] += 1
        p["ordinal"] = seq[(p["arm"], p["symbol"])]
    return pos


def minute_key(ts_utc_or_et: str) -> str:
    return ts_utc_or_et[:16]


def build_vwap_index(symbols: list[str]) -> dict:
    """(symbol, 'YYYY-MM-DDTHH:MM') -> real OPRA 1-min VWAP, UTC minute keys."""
    idx: dict = {}
    for s in sorted(set(symbols)):
        bars = esp.fetch_option_bars(s, WED)
        if not bars:
            raise SystemExit(f"FATAL: 0 OPRA bars for {s} {WED} -- refusing to guess")
        for b in bars:
            idx[(s, minute_key(b["t"]))] = float(b["vw"])
        print(f"[wed-decomp] {s}: {len(bars)} real OPRA 1-min bars")
    return idx


# ------------------------------------------------------------------ counterfactual books
def pnl_of(entry_price: float, legs: list[tuple[float, float]]) -> float:
    """legs = [(qty, price), ...]"""
    return sum((px - entry_price) * q * 100.0 for q, px in legs)


def book_pnl(rows: list[dict]) -> float:
    return round(sum(r["cf_pnl"] for r in rows), 2)


def make_rows(pos: list[dict], vwap: dict, *, friction: bool, size: bool,
              reentry: bool, exitcfg: bool) -> list[dict]:
    """Return the counterfactual book under any subset of the four levers.
    friction=True  -> re-price every fill at its own minute's real OPRA VWAP
    size=True      -> scale every position to 3 contracts, legs pro-rata
    reentry=True   -> drop every ordinal>=2 position
    exitcfg=True   -> credit the observed sibling per-contract execution on the 772P
    """
    out = []
    for p in pos:
        if reentry and p["ordinal"] > 1:
            continue
        qty = p["entry_qty"]
        ep = p["entry_price"]
        legs = [(ef["qty"], ef["price"]) for ef in p["exit_fills"]]
        if friction:
            k = (p["symbol"], minute_key(p["entry_ts_utc"]))
            if k in vwap:
                ep = vwap[k]
            legs = [(q, vwap.get((p["symbol"], minute_key(ef["ts_utc"])), px))
                    for (q, px), ef in zip(legs, p["exit_fills"])]
        scale = (RULE6_MIN_CONTRACTS / qty) if size else 1.0
        legs = [(q * scale, px) for q, px in legs]
        eff_qty = qty * scale
        cf = pnl_of(ep, legs)
        if exitcfg and p["symbol"] == PUT and p["arm"] != SIBLING_ARM:
            # replace this arm's realised per-contract outcome with the sibling's realised
            # per-contract outcome on the identical contract (real fills, both sides).
            cf = SIBLING_PER_CONTRACT * eff_qty
        out.append({**p, "cf_qty": round(eff_qty, 4), "cf_entry": round(ep, 4),
                    "cf_pnl": round(cf, 2)})
    return out


SIBLING_PER_CONTRACT = None  # set in main from real fills


def waterfall(pos, vwap, order: list[str]) -> dict:
    """Sequential attribution in `order`; each step's delta is measured on the book the
    prior steps left behind. Sums to ACTUAL by construction."""
    state = {"friction": False, "size": False, "reentry": False, "exitcfg": False}
    prev = book_pnl(make_rows(pos, vwap, **state))
    actual = prev
    steps = []
    for lever in order:
        state[lever] = True
        cur = book_pnl(make_rows(pos, vwap, **state))
        steps.append({"lever": lever, "delta": round(cur - prev, 2),
                      "book_after": round(cur, 2)})
        prev = cur
    residual = round(prev, 2)
    total_attributed = round(sum(s["delta"] for s in steps), 2)
    return {"order": order, "actual": round(actual, 2), "steps": steps,
            "residual_entry_location": residual,
            "sum_of_deltas": total_attributed,
            # identity: residual == actual + sum(deltas). 0.0 == the buckets SUM.
            "sum_check_must_be_zero": round(residual - (actual + total_attributed), 2)}


def shapley(pos, vwap, levers: list[str]) -> dict:
    """EXACT Shapley attribution over all 4! = 24 orderings (16 coalition books, memoised).
    Order-INDEPENDENT and still sums exactly: sum(shapley) == all_levers_on - actual.
    This is the answer to 'but your waterfall order chose the winner' (C15)."""
    from itertools import permutations
    import math as _m
    cache: dict = {}

    def val(subset: frozenset) -> float:
        if subset not in cache:
            st = {lv: (lv in subset) for lv in levers}
            cache[subset] = book_pnl(make_rows(pos, vwap, **st))
        return cache[subset]

    contrib = {lv: 0.0 for lv in levers}
    perms = list(permutations(levers))
    for perm in perms:
        seen: set = set()
        for lv in perm:
            before = frozenset(seen)
            seen.add(lv)
            contrib[lv] += val(frozenset(seen)) - val(before)
    n = len(perms)
    out = {lv: round(contrib[lv] / n, 2) for lv in levers}
    out["_sum"] = round(sum(out.values()), 2)
    out["_all_on_minus_actual"] = round(val(frozenset(levers)) - val(frozenset()), 2)
    out["_sum_check_must_be_zero"] = round(out["_sum"] - out["_all_on_minus_actual"], 2)
    out["_n_orderings"] = n
    assert _m.isclose(out["_sum"], out["_all_on_minus_actual"], abs_tol=0.05)
    return out


def main() -> int:
    global SIBLING_PER_CONTRACT
    pos = load_wed_positions()
    actual = round(sum(p["pnl"] for p in pos), 2)
    print(f"[wed-decomp] {len(pos)} positions, ACTUAL = {actual}")

    sib = [p for p in pos if p["symbol"] == PUT and p["arm"] == SIBLING_ARM]
    assert len(sib) == 1, sib
    SIBLING_PER_CONTRACT = sib[0]["pnl"] / sib[0]["entry_qty"]
    print(f"[wed-decomp] sibling per-contract (risky-1 772P) = {SIBLING_PER_CONTRACT:+.4f}")

    vwap = build_vwap_index([p["symbol"] for p in pos])

    levers = ["friction", "size", "reentry", "exitcfg"]
    base = book_pnl(make_rows(pos, vwap, friction=False, size=False,
                              reentry=False, exitcfg=False))
    assert abs(base - actual) < 0.01, (base, actual)

    standalone = {}
    for lv in levers:
        st = {k: (k == lv) for k in levers}
        standalone[lv] = round(book_pnl(make_rows(pos, vwap, **st)) - actual, 2)

    # ---- friction split: entry side vs exit side, in dollars, at ACTUAL qty.
    #      entry cost = (fill - minuteVWAP) * qty * 100   (positive == we overpaid to buy)
    #      exit  cost = (minuteVWAP - fill) * qty * 100   (positive == we sold below VWAP)
    fr_entry = fr_exit = 0.0
    fr_rows = []
    for p in pos:
        ke = (p["symbol"], minute_key(p["entry_ts_utc"]))
        e_ref = vwap.get(ke)
        e_cost = ((p["entry_price"] - e_ref) * p["entry_qty"] * 100.0) if e_ref else 0.0
        x_cost = 0.0
        for ef in p["exit_fills"]:
            kx = (p["symbol"], minute_key(ef["ts_utc"]))
            x_ref = vwap.get(kx)
            if x_ref:
                x_cost += (x_ref - ef["price"]) * ef["qty"] * 100.0
        fr_entry += e_cost
        fr_exit += x_cost
        fr_rows.append({"arm": p["arm"], "symbol": p["symbol"], "ordinal": p["ordinal"],
                        "entry_vs_vwap_dollars": round(e_cost, 2),
                        "exit_vs_vwap_dollars": round(x_cost, 2)})
    friction_detail = {
        "entry_side_cost_dollars": round(fr_entry, 2),
        "exit_side_cost_dollars": round(fr_exit, 2),
        "total_cost_dollars": round(fr_entry + fr_exit, 2),
        "sign_convention": "POSITIVE == a real cost vs that same minute's real OPRA VWAP; "
                           "NEGATIVE == we executed BETTER than the minute's volume-weighted "
                           "average.",
        "reference_caveat": "The 1-min VWAP is the average of everyone's prints in that "
                            "minute, not a quote we could certainly have hit. It is a fair, "
                            "reproducible, real-data reference -- not an achievable-price claim.",
        "per_position": fr_rows,
    }

    declared = ["friction", "size", "reentry", "exitcfg"]
    reverse = ["exitcfg", "reentry", "size", "friction"]
    wf_a = waterfall(pos, vwap, declared)
    wf_b = waterfall(pos, vwap, reverse)

    shap = shapley(pos, vwap, levers)
    all_on = book_pnl(make_rows(pos, vwap, friction=True, size=True,
                                reentry=True, exitcfg=True))
    interaction = round(sum(standalone.values()) - (all_on - actual), 2)

    # ---- reconciliation against the prior audit's event-level split
    ev = {"A_776C_spiral": 0.0, "A2_777C": 0.0, "B_772P": 0.0}
    for p in pos:
        if p["symbol"] == "SPY260805C00776000":
            ev["A_776C_spiral"] += p["pnl"]
        elif p["symbol"] == "SPY260805C00777000":
            ev["A2_777C"] += p["pnl"]
        elif p["symbol"] == PUT:
            ev["B_772P"] += p["pnl"]
    ev = {k: round(v, 2) for k, v in ev.items()}
    prior_entry_side = ev["A_776C_spiral"] + ev["A2_777C"]

    # ---- ordinal decomposition on Wednesday specifically
    by_ord: dict = defaultdict(lambda: {"n": 0, "pnl": 0.0})
    for p in pos:
        by_ord[p["ordinal"]]["n"] += 1
        by_ord[p["ordinal"]]["pnl"] += p["pnl"]
    ordinals = {str(k): {"n": v["n"], "pnl": round(v["pnl"], 2)}
                for k, v in sorted(by_ord.items())}

    out = {
        "_question": "Decompose 2026-08-05 into orthogonal buckets that SUM.",
        "actual_spy_option_pnl": actual,
        "actual_day_pnl_incl_crypto_twin": -1943.66,
        "crypto_twin_residual": round(-1943.66 - actual, 2),
        "n_positions": len(pos),
        "positions": [{"arm": p["arm"], "symbol": p["symbol"], "ordinal": p["ordinal"],
                       "entry_ts_et": p["entry_ts_et"], "qty": p["entry_qty"],
                       "entry_price": p["entry_price"], "pnl": p["pnl"],
                       "pnl_per_contract": round(p["pnl"] / p["entry_qty"], 2)} for p in pos],
        "sibling_per_contract_772P": round(SIBLING_PER_CONTRACT, 4),
        "standalone_marginal_effects": standalone,
        "friction_detail": friction_detail,
        "standalone_note": ("Each lever applied ALONE from the actual book. These deliberately "
                            "do NOT sum -- the gap is the interaction term below (C15)."),
        "interaction_term": interaction,
        "all_levers_on_book": round(all_on, 2),
        "waterfall_declared_order": wf_a,
        "waterfall_reverse_order": wf_b,
        "shapley_order_independent": shap,
        "shapley_note": ("EXACT Shapley over all 24 orderings of the 4 levers. This is the "
                         "HEADLINE attribution: order-independent, and it still sums exactly "
                         "to (all-levers-on book - actual). Use these numbers, not either "
                         "single waterfall -- the two waterfalls differ by up to $1,294 on "
                         "the SIZE lever alone, which is the C15 interaction, not ambiguity "
                         "in the data."),
        "event_level_reconciliation": {
            "events": ev,
            "prior_audit_entry_side_dollars": round(prior_entry_side, 2),
            "prior_audit_entry_side_share": round(prior_entry_side / actual, 4),
            "prior_audit_exit_side_dollars": ev["B_772P"],
            "prior_audit_exit_side_share": round(ev["B_772P"] / actual, 4),
        },
        "wednesday_ordinal_decomposition": ordinals,
    }
    prev = json.loads(OUT_JSON.read_text(encoding="utf-8")) if OUT_JSON.exists() else {}
    prev["q2_wednesday_decomposition"] = out
    OUT_JSON.write_text(json.dumps(prev, indent=2), encoding="utf-8")
    print(json.dumps({k: out[k] for k in
                      ("standalone_marginal_effects", "interaction_term",
                       "waterfall_declared_order", "waterfall_reverse_order",
                       "event_level_reconciliation", "wednesday_ordinal_decomposition")},
                     indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())

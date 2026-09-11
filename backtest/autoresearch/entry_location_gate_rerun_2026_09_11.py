"""BULL-ENTRY-LOCATION-RERUN-2026-09-11 -- extends the population for the FROZEN
prereg ENTRY-LOCATION-GATE-2026-08-14 and re-runs its UNCHANGED evaluate() logic.

Nothing about the test itself changes: same 11 cells (build_cells() imported verbatim from
the original runner), same BH-FDR q=0.10, same blocked-winner accounting, same MIN_CELL_N=30,
same causality rule (every feature computed from bars strictly before the entry bar; entry
price = entry bar's OPEN). This file only extends the DATA the frozen test runs against:

1. bars: the pinned CSV (backtest/data/spy_5m_2025-01-01_2026-07-08.csv, ends 2026-07-08)
   merged with a NEW extension file (backtest/data/spy_5m_2026-07-09_2026-09-11_extension.csv,
   fetched fresh via backtest/tools/alpaca_bars.py SIP feed, 2026-07-09..2026-09-11). The
   pinned CSV is NOT modified.
2. trades: the original 191-trade population (engine-fullhist-replay-2026-07-23.json, ends
   2026-07-21) concatenated with a NEW real-fills population built here from
   journal/trades.csv (fill_quality == real_fill, 2026-07-28..2026-09-10) plus
   automation/state/pnl-statement.json round_trips for 2026-09-11 (not yet backfilled into
   trades.csv). Multi-arm fleet fires the SAME signal from multiple accounts simultaneously
   (safe-2/safe-3/risky-1/bold-2/...) -- these are deduped to distinct entry EVENTS by
   (date, entry minute, strike), per the task's methodology (verified: 133 distinct bull
   events, matching the number already published in
   ENTRY-LOCATION-GATE-2026-08-14.md's 2026-09-11 update). Within one event, dollar_pnl is
   SUMMED across the arms that fired it (an explicit, stated judgment call -- it reflects the
   book-level cost/benefit of that one entry decision, not an arbitrary single arm's fill).

Read-only. Writes analysis/recommendations/entry-location-gate-2026-09-11.json. Arms nothing.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "autoresearch"))
import entry_location_gate_2026_08_14 as base  # noqa: E402

ORIG_REPLAY = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
PINNED_BARS = REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-07-08.csv"
EXT_BARS = REPO / "backtest" / "data" / "spy_5m_2026-07-09_2026-09-11_extension.csv"
TRADES_CSV = REPO / "journal" / "trades.csv"
PNL_STATEMENT = REPO / "automation" / "state" / "pnl-statement.json"
OUT = REPO / "analysis" / "recommendations" / "entry-location-gate-2026-09-11.json"

NEW_WINDOW_START = "2026-07-28"
NEW_WINDOW_CSV_END = "2026-09-10"   # trades.csv coverage; 09-11 comes from pnl-statement
NEW_WINDOW_END = "2026-09-11"


def features_floor(day_bars: list[dict], prior_bars: list[dict] | None, entry_hhmm: str) -> dict | None:
    """Same causal contract as base.features() (bars STRICTLY BEFORE the entry bar; entry
    price = entry bar's OPEN) -- but the base function requires entry_hhmm to EXACTLY match a
    bar's 5-min-grid start, which real-fill timestamps do not: the live heartbeat fires every
    1 minute, so 191 of 217 new real-fill events (88%, verified by direct count) land on a
    minute that is not a multiple of 5 and would silently exclude AS "no_causal_features" --
    not because the data is causally unavailable, but because of a grid-alignment mismatch
    between the backtest-replay population (entries snapped to 5m bars by construction, 100%
    grid-aligned per direct check) and real-fill timestamps.

    Fix: find the 5m bar whose interval [start, start+5) CONTAINS entry_hhmm (floor), and treat
    THAT bar as "the entry bar" -- its open is the entry-price proxy (used only for the location
    feature, never for the trade's own realized P&L, which is the actual executed fill), and
    "before" is every bar strictly before ITS start. This is the identical causal rule applied
    to a timestamp that does not fall exactly on a bar boundary; no cell definition, threshold,
    or FDR/blocked-winner accounting changes.
    """
    session = base.rth(day_bars)
    if not session:
        return None
    floor_bar = None
    for b in session:
        if b["t"] <= entry_hhmm:
            floor_bar = b
        else:
            break
    if floor_bar is None:
        return None
    before = [b for b in session if b["t"] < floor_bar["t"]]
    if len(before) < base.MIN_PRIOR_BARS:
        return None
    hi = max(b["h"] for b in before)
    lo = min(b["l"] for b in before)
    rng = hi - lo
    if rng < base.MIN_RANGE_PTS:
        return None
    entry_px = floor_bar["o"]
    prior_run = None
    if prior_bars:
        ps = base.rth(prior_bars)
        if ps:
            prior_run = ps[-1]["c"] - ps[0]["o"]
    return {
        "entry_px": entry_px, "hi_so_far": hi, "lo_so_far": lo, "range_pts": rng,
        "n_prior_bars": len(before),
        "dist_from_high_frac": (hi - entry_px) / rng,
        "dist_from_low_frac": (entry_px - lo) / rng,
        "prior_day_run_pts": prior_run,
    }


def load_merged_bars() -> dict[str, list[dict]]:
    days: dict[str, list[dict]] = defaultdict(list)
    for path in (PINNED_BARS, EXT_BARS):
        with path.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                ts = row["timestamp_et"]
                days[ts[:10]].append({
                    "t": ts[11:16],
                    "o": float(row["open"]), "h": float(row["high"]),
                    "l": float(row["low"]), "c": float(row["close"]),
                })
    for d in days:
        days[d].sort(key=lambda b: b["t"])
    return days


def build_extended_trades_from_csv() -> tuple[list[dict], dict]:
    """journal/trades.csv real_fill rows, 2026-07-28..2026-09-10, deduped to distinct entry
    EVENTS by (date, entry minute, strike). Returns (trades, diagnostics)."""
    rows = list(csv.DictReader(TRADES_CSV.open(encoding="utf-8-sig")))
    pop = [r for r in rows if r["fill_quality"] == "real_fill"
           and NEW_WINDOW_START <= r["date"] <= NEW_WINDOW_CSV_END]
    events: dict[tuple, list[dict]] = defaultdict(list)
    for r in pop:
        minute = r["time_entry"][:5]
        key = (r["date"], minute, r["c_or_p"], r["strike"])
        events[key].append(r)

    trades = []
    for (date, minute, side, strike), grp in events.items():
        pnls = []
        for x in grp:
            try:
                pnls.append(float(x["dollar_pnl"]))
            except (ValueError, TypeError):
                pass
        if len(pnls) != len(grp):
            continue  # VOID: a fill in this event lacked a parseable dollar_pnl
        setups = [x["setup"] for x in grp if x.get("setup")]
        setup = max(set(setups), key=setups.count) if setups else None
        trades.append({
            "date": date,
            "entry_time_et": f"{date}T{minute}:00",
            "setup": setup,
            "side": side,
            "tier": "fleet-multi-arm-2026-09-11-rerun",
            "symbol": None,
            "qty": sum(int(float(x["qty"])) for x in grp if x.get("qty")),
            "dollar_pnl": round(sum(pnls), 2),
            "_n_arms_in_event": len(grp),
            "_accounts": sorted({x.get("account_id") for x in grp}),
        })
    diag = {
        "raw_real_fill_rows": len(pop),
        "raw_by_side": {"C": sum(1 for r in pop if r["c_or_p"] == "C"),
                        "P": sum(1 for r in pop if r["c_or_p"] == "P")},
        "distinct_events": len(events),
        "distinct_events_by_side": {"C": sum(1 for t in trades if t["side"] == "C"),
                                     "P": sum(1 for t in trades if t["side"] == "P")},
    }
    return trades, diag


def build_extended_trades_from_pnl_statement() -> tuple[list[dict], dict]:
    """automation/state/pnl-statement.json round_trips for 2026-09-11 (not yet in
    trades.csv), same event-dedup rule."""
    d = json.load(PNL_STATEMENT.open(encoding="utf-8"))
    rt = [r for r in d["round_trips"] if r["date_et"] == NEW_WINDOW_END]

    def side_of(sym: str) -> str:
        return sym[9]  # SPY260911C00768000 -- side char at fixed offset

    def strike_of(sym: str) -> str:
        return str(int(int(sym[10:18]) / 1000))

    events: dict[tuple, list[dict]] = defaultdict(list)
    for r in rt:
        minute = r["entry_ts_et"][11:16]
        key = (NEW_WINDOW_END, minute, side_of(r["symbol"]), strike_of(r["symbol"]))
        events[key].append(r)

    trades = []
    for (date, minute, side, strike), grp in events.items():
        trades.append({
            "date": date,
            "entry_time_et": f"{date}T{minute}:00",
            "setup": None,
            "side": side,
            "tier": "fleet-multi-arm-2026-09-11-rerun",
            "symbol": None,
            "qty": round(sum(x["qty"] for x in grp), 1),
            "dollar_pnl": round(sum(x["pnl"] for x in grp), 2),
            "_n_arms_in_event": len(grp),
            "_accounts": sorted({x["arm"] for x in grp}),
        })
    diag = {
        "raw_round_trip_rows": len(rt),
        "raw_by_side": {"C": sum(1 for r in rt if side_of(r["symbol"]) == "C"),
                        "P": sum(1 for r in rt if side_of(r["symbol"]) == "P")},
        "distinct_events": len(events),
        "distinct_events_by_side": {"C": sum(1 for t in trades if t["side"] == "C"),
                                     "P": sum(1 for t in trades if t["side"] == "P")},
    }
    return trades, diag


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    days = load_merged_bars()
    ordered = sorted(days)
    prior_of = {d: (ordered[i - 1] if i else None) for i, d in enumerate(ordered)}

    orig_raw = json.load(ORIG_REPLAY.open(encoding="utf-8"))["trades"]
    csv_trades, csv_diag = build_extended_trades_from_csv()
    pnl_trades, pnl_diag = build_extended_trades_from_pnl_statement()

    combined_raw = list(orig_raw) + csv_trades + pnl_trades

    n_bull_new = csv_diag["distinct_events_by_side"]["C"] + pnl_diag["distinct_events_by_side"]["C"]
    n_put_new = csv_diag["distinct_events_by_side"]["P"] + pnl_diag["distinct_events_by_side"]["P"]
    expected_bull = 133
    bull_check = {
        "expected_from_doc_2026_09_11_update": expected_bull,
        "computed_here": n_bull_new,
        "match": n_bull_new == expected_bull,
    }

    trades, skipped = [], defaultdict(int)
    for t in combined_raw:
        d = t["date"]
        if d not in days:
            skipped["no_bar_day"] += 1
            continue
        f = features_floor(days[d], days.get(prior_of[d]) if prior_of[d] else None,
                            t["entry_time_et"][11:16])
        if f is None:
            skipped["no_causal_features"] += 1
            continue
        trades.append({"date": d, "side": t["side"], "dollar_pnl": t["dollar_pnl"],
                        "entry_time_et": t["entry_time_et"], "tier": t.get("tier"),
                        "setup": t.get("setup"), "feat": f})

    rep = base.evaluate(trades, "extended population: engine-fullhist-replay-2026-07-23 "
                                 "(191, ends 2026-07-21) + real fills 2026-07-28..2026-09-11 "
                                 "(event-deduped)")
    rep["_doc"] = __doc__.strip().splitlines()[0]
    rep["prereg_id"] = "ENTRY-LOCATION-GATE-2026-08-14"
    rep["rerun_id"] = "BULL-ENTRY-LOCATION-RERUN-2026-09-11"
    rep["excluded"] = dict(skipped)
    rep["params"] = {"prox_bands": base.PROX_BANDS, "run_bands": base.RUN_BANDS,
                      "min_prior_bars": base.MIN_PRIOR_BARS, "min_range_pts": base.MIN_RANGE_PTS,
                      "min_cell_n": base.MIN_CELL_N}
    rep["feature_alignment_fix"] = (
        "base.features() requires entry_hhmm to exactly equal a bar's 5m-grid start; real-fill "
        "timestamps from the live 1-min heartbeat mostly do not (191/217 new events, 88%, "
        "verified by direct count). features_floor() in this file applies the IDENTICAL causal "
        "rule (bars strictly before the entry bar; entry price = entry bar's open) to the 5m bar "
        "whose interval contains the entry timestamp instead of requiring exact equality. No "
        "cell, threshold, FDR, or blocked-winner logic changed -- see this file's docstring."
    )
    rep["population_build"] = {
        "orig_replay_n": len(orig_raw),
        "orig_replay_window": "2025-01-02..2026-07-21",
        "new_from_trades_csv": csv_diag,
        "new_from_pnl_statement_2026_09_11": pnl_diag,
        "bull_event_count_check_vs_doc": bull_check,
        "put_events_added": n_put_new,
    }
    published_orig = json.load(ORIG_REPLAY.open(encoding="utf-8"))["headline"]["total_pnl"]
    ours = round(sum(t["dollar_pnl"] for t in trades), 2)
    rep["G1_control"] = {
        "note": ("this is an EXTENDED population, not the original 191 -- G1 here reconciles "
                 "the ORIGINAL-window subtotal only, then reports the extension's own subtotal "
                 "separately so nothing is silently blended into a single unverifiable number"),
        "published_total_orig_191": published_orig,
        "our_total_after_exclusions": ours,
        "orig_window_subtotal_recomputed": round(
            sum(t["dollar_pnl"] for t in trades if t["date"] <= "2026-07-21"), 2),
        "extension_subtotal": round(
            sum(t["dollar_pnl"] for t in trades if t["date"] > "2026-07-21"), 2),
        "excluded_n": sum(skipped.values()),
    }
    for s in ("C", "P"):
        sizes = [c["n_gated"] for c in rep["cells"]
                 if c["side"] == s and c["run"] is None and c["prox"] is not None]
        rep.setdefault("G2_monotonic", {})[s] = {
            "gated_n_by_band": sizes,
            "monotonic_nondecreasing": all(a <= b for a, b in zip(sizes, sizes[1:])),
        }
    OUT.write_text(json.dumps(rep, indent=1), encoding="utf-8")

    print(f"ENTRY-LOCATION-GATE RERUN  population n={rep['n']}  {rep['by_side']}")
    print(f"  bull event count check: {bull_check}")
    print(f"  excluded: {dict(skipped)}")
    print(f"  G1: {rep['G1_control']}")
    print(f"  G2 monotonic: { {k: v['monotonic_nondecreasing'] for k, v in rep['G2_monotonic'].items()} }")
    for s in ("P", "C"):
        b = rep["baseline"].get(s)
        if b:
            print(f"\n  === {s} baseline: n={b['n']} total=${b['total']} mean=${b['mean']} wr={b['win_rate']:.1%}")
        for c in rep["cells"]:
            if c["side"] != s:
                continue
            if c["verdict"] == "NOT-RUN":
                print(f"    [NOT-RUN] {c['cell']:<34} n_gated={c['n_gated']}")
                continue
            star = "*" if c["survives_bh_fdr_q10"] else " "
            print(f"    [{star}] {c['cell']:<34} gated n={c['n_gated']:>3} "
                  f"mean=${c['gated_mean']:>8} vs kept=${c['kept_mean']:>8}  "
                  f"p={c['perm_p']}  book_delta=${c['book_delta_if_gated']:>9}  "
                  f"blocked_winners={c['blocked_winners_n']} (${c['blocked_winner_dollars']})")
    print(f"\nwrote {OUT.relative_to(REPO).as_posix()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

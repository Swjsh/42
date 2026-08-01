"""trendline_context_conditioning_2026_08_01.py -- WS8: does multi-day trendline
CONTEXT change the expectancy of the engine's profitable level-anchored entries?

PRE-REGISTERED. Frozen prereg (committed BEFORE this file existed -- freeze order
git-provable): analysis/recommendations/prereg-trendline-context-conditioning-2026-08-01.json
(in commit 9d4d242c, 2026-08-01 12:43:51 EDT; NOTE that commit's message describes a
concurrent session's WS4 prereg -- this file was absorbed into it by a same-second
commit race, disclosed; content and ordering are unaffected).

WHAT THIS IS: a CONDITIONING re-slice of the 66 structure-stop level-anchored
trades (+$6,894.85 real OPRA) of engine-fullhist-replay-2026-07-23.json. It
invents NO new entries, changes NO P&L, arms NOTHING. Graveyard respected:
trendline_reclaim/wick_reclaim as STANDALONE triggers stay dead -- this tests the
one untested form, trendline events as CONTEXT on level-anchored setups (C15).

MECHANICS (all frozen in the prereg -- see it for rationale):
  - Context detector: trendline_engine.detect(bars, families=('wick','body'),
    include_same_day_tier=True) -- the SAME code production runs every 5 min.
  - Bars: backtest/data/spy_5m_2025-01-01_2026-07-22.csv, the replay's OWN file;
    wall-v1 naive labels both sides (et_frame.py doctrine -- no cross-frame join).
  - RTH filter per-date via et_clock.et_offset_hours: EST label window
    [10:30,17:00), EDT [09:30,16:00).
  - Lookback per trade: prior 5 trading days + same-day bars with label
    strictly < entry_time_et (entry+1: the trigger bar is closed at fill --
    markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md). No bar at/after
    entry ever reaches the detector.
  - ACTIVE line = status INTACT|TESTING on the lookback window's last bar.
  - ref price = trigger-bar close. Bands B in {1.00 primary, 0.50, 2.00, ANY}.
    bull C: aligned = active support cv in [ref-B, ref+TOL]; opposing = active
    resistance cv in [ref-TOL, ref+B]. bear P mirrored. ANY drops the far bound.
  - 2 contrasts (aligned vs rest, opposing vs rest) x 2 strata (FULL, R2026)
    x 4 bands = 16 two-sided permutation tests (mean $/trade diff, 20k perms,
    random.Random(42)); degenerate cells (either side n<3) excluded, disclosed.
  - BH-FDR q*=0.10 across all non-degenerate p-values. ALL cells reported.
  - Decision rule frozen in the prereg: SIGNAL -> propose-only score-contributor
    prereg; NULL -> trendline program is VISIBILITY-ONLY.

Outputs: analysis/deep-research/TRENDLINE-CONTEXT-CONDITIONING-2026-08-01.{json,md}

Run:  backtest/.venv/Scripts/python.exe backtest/tools/trendline_context_conditioning_2026_08_01.py
"""
from __future__ import annotations

import csv
import json
import random
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest" / "autoresearch"))
sys.path.insert(0, str(REPO / "setup" / "scripts"))

import trendline_engine as te  # noqa: E402
from et_clock import et_offset_hours, et_now  # noqa: E402

REPLAY = REPO / "analysis" / "recommendations" / "engine-fullhist-replay-2026-07-23.json"
BARS_CSV = REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-07-22.csv"
OUT_JSON = REPO / "analysis" / "deep-research" / "TRENDLINE-CONTEXT-CONDITIONING-2026-08-01.json"
OUT_MD = REPO / "analysis" / "deep-research" / "TRENDLINE-CONTEXT-CONDITIONING-2026-08-01.md"

TOL = 0.10
N_LOOKBACK_DAYS = 5
BANDS = [("B1.00", 1.00), ("B0.50", 0.50), ("B2.00", 2.00), ("ANY", None)]  # frozen order
N_PERMS = 20_000
SEED = 42
Q_STAR = 0.10
MIN_CELL = 3
EXPECT_N = 66
EXPECT_TOTAL = 6894.85


# ------------------------------------------------------------------ data loading
def load_cohort() -> list[dict]:
    d = json.loads(REPLAY.read_text(encoding="utf-8"))
    trades = [t for t in d["trades"] if t.get("resolved_stop_mode") == "structure"]
    n, total = len(trades), round(sum(t["dollar_pnl"] for t in trades), 2)
    if n != EXPECT_N or abs(total - EXPECT_TOTAL) > 0.005:
        raise SystemExit(f"ANCHOR FAIL: cohort n={n} total={total} != expected "
                         f"{EXPECT_N}/{EXPECT_TOTAL} -- aborting per prereg.")
    print(f"anchor OK: n={n} total=+${total:,.2f}")
    return trades


def _is_est(date_str: str) -> bool:
    """Wall-v1 frame helper: is this ET calendar date an EST (-5) date?"""
    y, m, dd = int(date_str[0:4]), int(date_str[5:7]), int(date_str[8:10])
    return et_offset_hours(datetime(y, m, dd, 12, 0, tzinfo=timezone.utc)) == -5


def load_bars_by_day() -> tuple[dict[str, list[dict]], list[str]]:
    """{date: [bar dicts]} RTH-only in the wall-v1 frame, plus sorted date list.

    Bar dict shape matches trendline_engine.detect's expectation: o/h/l/c floats
    + 't' as a fake-UTC ISO string carrying the wall-v1 label (labels are only
    used for identity/grouping inside the engine -- all fit math is index+price;
    date portion survives the engine's _et() offset arithmetic for RTH hours)."""
    by_day: dict[str, list[dict]] = defaultdict(list)
    with BARS_CSV.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            label = row["timestamp_et"][:19]          # strip the (broken) fixed offset
            date, hhmm = label[:10], label[11:16]
            lo, hi = ("10:30", "17:00") if _is_est(date) else ("09:30", "16:00")
            if not (lo <= hhmm < hi):
                continue
            by_day[date].append({
                "t": label.replace(" ", "T") + "Z",
                "o": float(row["open"]), "h": float(row["high"]),
                "l": float(row["low"]), "c": float(row["close"]),
            })
    for date in by_day:
        by_day[date].sort(key=lambda b: b["t"])
    return dict(by_day), sorted(by_day)


# ------------------------------------------------------------- context per trade
def context_for_trade(trade: dict, by_day: dict[str, list[dict]],
                      dates: list[str]) -> dict:
    entry = datetime.fromisoformat(trade["entry_time_et"])   # naive wall-v1
    edate = trade["date"]
    if edate not in by_day:
        raise SystemExit(f"bar file is missing trade date {edate} -- frame/coverage bug")
    i = dates.index(edate)
    prior = dates[max(0, i - N_LOOKBACK_DAYS):i]
    entry_label = entry.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    same_day = [b for b in by_day[edate] if b["t"] < entry_label]
    bars = [b for d in prior for b in by_day[d]] + same_day
    if len(bars) < te.MIN_SPAN + 2:
        return {"lines": [], "ref": None, "n_prior_days": len(prior),
                "trigger_bar_gap": True, "n_bars": len(bars)}
    lines = te.detect(bars, families=("wick", "body"), include_same_day_tier=True)
    ref = bars[-1]["c"]
    expect_trigger = (entry - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%S") + "Z"
    return {
        "lines": [{"kind": ln.kind, "family": ln.anchor_family, "tier": ln.tier,
                   "status": ln.status, "cv": ln.current_value} for ln in lines],
        "ref": ref,
        "n_prior_days": len(prior),
        "trigger_bar_gap": bars[-1]["t"] != expect_trigger,
        "n_bars": len(bars),
    }


def classify(side: str, ref: float, lines: list[dict], band: float | None) -> dict:
    """Frozen cell formulas. side C=bull, P=bear. band None = ANY (existence)."""
    act_sup = [ln["cv"] for ln in lines if ln["status"] in ("INTACT", "TESTING")
               and ln["kind"] == "support"]
    act_res = [ln["cv"] for ln in lines if ln["status"] in ("INTACT", "TESTING")
               and ln["kind"] == "resistance"]
    if side == "C":
        aligned = any(cv <= ref + TOL and (band is None or cv >= ref - band) for cv in act_sup)
        opposing = any(cv >= ref - TOL and (band is None or cv <= ref + band) for cv in act_res)
    else:
        aligned = any(cv >= ref - TOL and (band is None or cv <= ref + band) for cv in act_res)
        opposing = any(cv <= ref + TOL and (band is None or cv >= ref - band) for cv in act_sup)
    return {"aligned": aligned, "opposing": opposing}


# ------------------------------------------------------------------- statistics
def perm_test(pnls_a: list[float], pnls_b: list[float], rng: random.Random) -> dict:
    """Two-sided permutation test on mean difference (a minus b)."""
    n_a = len(pnls_a)
    pooled = pnls_a + pnls_b
    obs = (sum(pnls_a) / n_a) - (sum(pnls_b) / len(pnls_b))
    hits = 0
    for _ in range(N_PERMS):
        rng.shuffle(pooled)
        d = (sum(pooled[:n_a]) / n_a) - (sum(pooled[n_a:]) / (len(pooled) - n_a))
        if abs(d) >= abs(obs) - 1e-12:
            hits += 1
    return {"obs_diff": round(obs, 2), "p": (1 + hits) / (1 + N_PERMS)}


def bh_fdr(tests: list[dict], q: float = Q_STAR) -> None:
    """Benjamini-Hochberg across all non-None p-values; annotates in place."""
    scored = [t for t in tests if t.get("p") is not None]
    m = len(scored)
    for t in tests:
        t["bh_survives"] = False
    if not m:
        return
    scored.sort(key=lambda t: t["p"])
    cutoff_rank = 0
    for i, t in enumerate(scored, start=1):
        if t["p"] <= q * i / m:
            cutoff_rank = i
    for i, t in enumerate(scored, start=1):
        t["bh_rank"] = i
        t["bh_threshold"] = round(q * i / m, 5)
        t["bh_survives"] = i <= cutoff_rank
    print(f"BH-FDR: m={m}, survivors={sum(1 for t in scored if t['bh_survives'])}")


def cell_stats(trades: list[dict]) -> dict:
    if not trades:
        return {"n": 0, "total": 0.0, "per_trade": None, "wr": None, "n_tl_rejection_tag": 0}
    pnls = [t["dollar_pnl"] for t in trades]
    return {
        "n": len(trades),
        "total": round(sum(pnls), 2),
        "per_trade": round(sum(pnls) / len(pnls), 2),
        "wr": round(sum(1 for p in pnls if p > 0) / len(pnls), 3),
        "n_tl_rejection_tag": sum(1 for t in trades
                                  if "trendline_rejection" in (t.get("triggers") or [])),
    }


# -------------------------------------------------------------------------- main
def main() -> int:
    t0 = et_now().strftime("%Y-%m-%dT%H:%M:%S")
    trades = load_cohort()
    by_day, dates = load_bars_by_day()
    print(f"bars: {len(dates)} trading days loaded")

    for k, t in enumerate(trades):
        t["_ctx"] = context_for_trade(t, by_day, dates)
        if (k + 1) % 10 == 0:
            print(f"  context {k + 1}/{len(trades)}")
    truncated = sum(1 for t in trades if t["_ctx"]["n_prior_days"] < N_LOOKBACK_DAYS)
    gaps = sum(1 for t in trades if t["_ctx"]["trigger_bar_gap"])
    print(f"lookback<5d: {truncated} trades; trigger-bar label gaps: {gaps}")

    for t in trades:
        t["_cells"] = {name: classify(t["side"], t["_ctx"]["ref"], t["_ctx"]["lines"], b)
                       for name, b in BANDS}

    strata = {
        "FULL": trades,
        "R2026": [t for t in trades if t["date"] >= "2026-01-01"],
    }

    # 16 pre-registered tests, frozen iteration order: band -> contrast -> stratum
    rng = random.Random(SEED)
    tests: list[dict] = []
    for band_name, _ in BANDS:
        for contrast, key in (("C1_aligned", "aligned"), ("C2_opposing", "opposing")):
            for stratum_name, pop in strata.items():
                in_cell = [t for t in pop if t["_cells"][band_name][key]]
                out_cell = [t for t in pop if not t["_cells"][band_name][key]]
                row = {
                    "test": f"{contrast}|{stratum_name}|{band_name}",
                    "band": band_name, "contrast": contrast, "stratum": stratum_name,
                    "cell": cell_stats(in_cell), "complement": cell_stats(out_cell),
                }
                if len(in_cell) < MIN_CELL or len(out_cell) < MIN_CELL:
                    row.update({"p": None, "obs_diff": None,
                                "degenerate": f"cell n={len(in_cell)}, complement n={len(out_cell)}"})
                else:
                    row.update(perm_test([t["dollar_pnl"] for t in in_cell],
                                         [t["dollar_pnl"] for t in out_cell], rng))
                    row["degenerate"] = None
                tests.append(row)
    bh_fdr(tests)

    # mutually exclusive 4-cell descriptives per band (FULL + R2026), all reported
    excl: dict[str, dict] = {}
    for band_name, _ in BANDS:
        for stratum_name, pop in strata.items():
            cells = {"ALIGNED_ONLY": [], "OPPOSING_ONLY": [], "BOTH_SIDES": [], "NO_LINE": []}
            for t in pop:
                c = t["_cells"][band_name]
                key = ("BOTH_SIDES" if c["aligned"] and c["opposing"] else
                       "ALIGNED_ONLY" if c["aligned"] else
                       "OPPOSING_ONLY" if c["opposing"] else "NO_LINE")
                cells[key].append(t)
            excl[f"{band_name}|{stratum_name}"] = {k: cell_stats(v) for k, v in cells.items()}

    # day-level robustness for BH survivors only (prereg: disclosure, not a gate)
    day_level = []
    rng_day = random.Random(SEED + 1)
    for row in tests:
        if not row.get("bh_survives"):
            continue
        pop = strata[row["stratum"]]
        key = "aligned" if row["contrast"] == "C1_aligned" else "opposing"
        by_date_in, by_date_out = defaultdict(float), defaultdict(float)
        for t in pop:
            (by_date_in if t["_cells"][row["band"]][key] else by_date_out)[t["date"]] += t["dollar_pnl"]
        a, b = list(by_date_in.values()), list(by_date_out.values())
        if len(a) >= MIN_CELL and len(b) >= MIN_CELL:
            day_level.append({"test": row["test"], "n_days_cell": len(a),
                              "n_days_complement": len(b), **perm_test(a, b, rng_day)})
        else:
            day_level.append({"test": row["test"], "degenerate_days": f"{len(a)}/{len(b)}"})

    # frozen decision rule
    survivors = [r for r in tests if r["bh_survives"]]
    signal_rows = []
    for r in survivors:
        mate = next((x for x in tests if x["contrast"] == r["contrast"]
                     and x["band"] == r["band"] and x["stratum"] == "R2026"), None)
        sign_consistent = (mate is not None and mate.get("obs_diff") is not None
                           and r.get("obs_diff") is not None
                           and (mate["obs_diff"] > 0) == (r["obs_diff"] > 0))
        min_side = min(r["cell"]["n"], r["complement"]["n"])
        if sign_consistent and min_side >= 10:
            signal_rows.append(r["test"])
    verdict = "SIGNAL" if signal_rows else "NULL"

    result = {
        "_doc": __doc__.strip().splitlines()[0],
        "prereg": "analysis/recommendations/prereg-trendline-context-conditioning-2026-08-01.json (commit 9d4d242c; absorbed by a same-second concurrent commit -- disclosed)",
        "generated_et": t0,
        "population": {"n": len(trades), "total_pnl": EXPECT_TOTAL,
                       "window": "2025-01-06..2026-07-22 (subset of verified 391-day population)",
                       "n_lookback_truncated": truncated, "n_trigger_bar_gaps": gaps,
                       "n_r2026": len(strata["R2026"])},
        "tests_preregistered": tests,
        "mutually_exclusive_cells": excl,
        "day_level_robustness": day_level,
        "verdict": verdict,
        "signal_tests": signal_rows,
        "per_trade": [{
            "date": t["date"], "entry_time_et": t["entry_time_et"], "side": t["side"],
            "tier": t["tier"], "dollar_pnl": t["dollar_pnl"],
            "trigger_level": t["trigger_level"], "ref_close": t["_ctx"]["ref"],
            "n_active_lines": sum(1 for ln in t["_ctx"]["lines"]
                                  if ln["status"] in ("INTACT", "TESTING")),
            "lines": t["_ctx"]["lines"],
            "cells": {b: t["_cells"][b] for b, _ in BANDS},
            "has_tl_rejection_tag": "trendline_rejection" in (t.get("triggers") or []),
        } for t in trades],
    }
    OUT_JSON.write_text(json.dumps(result, indent=1), encoding="utf-8")
    write_md(result)
    print(f"VERDICT: {verdict}" + (f" -- {signal_rows}" if signal_rows else ""))
    print(f"wrote {OUT_JSON.relative_to(REPO)} + {OUT_MD.relative_to(REPO)}")
    return 0


def write_md(res: dict) -> None:
    L = []
    add = L.append
    add("# TRENDLINE-CONTEXT CONDITIONING -- 2026-08-01 (WS8)")
    add("")
    add(f"**Verdict: {res['verdict']}**"
        + (f" -- surviving tests: {', '.join(res['signal_tests'])}" if res["signal_tests"] else
           " -- no BH-FDR survivor meets the frozen decision rule."))
    add("")
    add(f"Pre-registered: `{res['prereg']}`. Generated {res['generated_et']} ET. "
        f"Population: the {res['population']['n']} structure-stop level-anchored trades "
        f"(+${res['population']['total_pnl']:,.2f} real OPRA) of engine-fullhist-replay-2026-07-23; "
        f"conditioning re-slice only -- no new entries, no P&L changes, nothing arms. "
        f"R2026 stratum n={res['population']['n_r2026']}. "
        f"Lookback<5d: {res['population']['n_lookback_truncated']} trades; "
        f"trigger-bar label gaps: {res['population']['n_trigger_bar_gaps']}.")
    add("")
    add("## The 16 pre-registered tests (ALL reported; BH-FDR q*=0.10)")
    add("")
    add("| Test | cell n | cell $/tr | cell WR | comp n | comp $/tr | comp WR | diff $/tr | p | BH |")
    add("|---|---|---|---|---|---|---|---|---|---|")
    for t in res["tests_preregistered"]:
        c, k = t["cell"], t["complement"]
        p_txt = f"{t['p']:.4f}" if t.get("p") is not None else f"— ({t['degenerate']})"
        diff = f"{t['obs_diff']:+.2f}" if t.get("obs_diff") is not None else "—"
        bh = "**SURVIVES**" if t.get("bh_survives") else ""
        add(f"| {t['test']} | {c['n']} | {_fmt(c['per_trade'])} | {_fmt(c['wr'])} "
            f"| {k['n']} | {_fmt(k['per_trade'])} | {_fmt(k['wr'])} | {diff} | {p_txt} | {bh} |")
    add("")
    add("## Mutually exclusive cells (descriptive, every band x stratum)")
    for key, cells in res["mutually_exclusive_cells"].items():
        add("")
        add(f"### {key}")
        add("")
        add("| Cell | n | total | $/trade | WR | w/ intraday TL-tag |")
        add("|---|---|---|---|---|---|")
        for name in ("ALIGNED_ONLY", "OPPOSING_ONLY", "BOTH_SIDES", "NO_LINE"):
            s = cells[name]
            add(f"| {name} | {s['n']} | {_fmt(s['total'], money=True)} | "
                f"{_fmt(s['per_trade'], money=True)} | {_fmt(s['wr'])} | {s['n_tl_rejection_tag']} |")
    add("")
    add("## Day-level robustness (BH survivors only)")
    add("")
    if res["day_level_robustness"]:
        for d in res["day_level_robustness"]:
            add(f"- {json.dumps(d)}")
    else:
        add("- (no BH survivors -- section empty by construction)")
    add("")
    add("## Disclosures (frozen in prereg)")
    add("")
    add("- n=66 small; conditioning read on an already-selected profitable cohort; "
        "hypothesis-generating only -- NOTHING arms from this study.")
    add("- Cohort is 100% structure-stop trades; the premium-stop TL_only leak "
        "(-$1,830/124tr) is out of population by design.")
    add("- 7/66 trades carry the intraday `trendline_rejection` trigger tag (a different, "
        "single-day detector); per-cell overlap column above.")
    add("- Context computed retrospectively with today's detector code on historical bars "
        "-- mechanism-faithful to what a score-contributor would see at decision time "
        "(same code, same no-look-ahead window), but the multi-day engine did not exist "
        "live for most of the window.")
    add("- Bars are the SIP/IEX cache patchwork (DATA-PROVENANCE.md); wall-v1 frame both "
        "sides of every join (et_frame doctrine); real-OPRA P&L only, zero synthetic.")
    add("- Sacred runner cohort (35 winners +$15,774) untouched -- read-only study.")
    add("")
    add(f"*Decision rule applied (frozen): {res['verdict']} -> "
        + ("propose-only score-contributor prereg (see companion recommendation)."
           if res["verdict"] == "SIGNAL" else
           "the trendline program is VISIBILITY-ONLY (watch surface + premarket line, "
           "shipped this session); no further trendline-entry research without a new "
           "evidence class.") + "*")
    OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8")


def _fmt(v, money: bool = False):
    if v is None:
        return "—"
    return f"${v:+,.2f}" if money else (f"{v:.3f}" if isinstance(v, float) and abs(v) < 10 else f"{v:,.2f}")


if __name__ == "__main__":
    raise SystemExit(main())

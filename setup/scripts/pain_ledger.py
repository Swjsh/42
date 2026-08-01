#!/usr/bin/env python
"""pain_ledger.py -- the MAE/MFE PAIN LEDGER (WS9, 2026-08-01): how much heat did every
historical filled trade actually take, and how much favor did it actually see?

PREREG: analysis/pain-ledger/PREREG-2026-08-01.md -- committed BEFORE this file existed
(freeze order git-provable). Every definition below is the frozen one; if a definition here
ever drifts from the prereg, the prereg wins and the drift is a bug.

⛔ DESCRIPTIVE ONLY. This module measures; it validates NOTHING. MAE knowledge is hindsight
by definition (C6: a live stop cannot condition on the trade's eventual maximum heat). No
stop-placement change may cite this ledger as sufficient evidence -- a stop change is its
own future pre-registered A/B, which may cite this ledger only as its evidence BASE.
Accordingly this module writes ONLY `analysis/pain-ledger/mae-mfe.json` (+ an optional
one-off report when asked): never hypothesis-queue.jsonl, never queue.md, never any
params/engine surface.

WHY EXTEND-NOT-FORK (the winner_autopsy.py reuse contract)
----------------------------------------------------------
Same single-source-of-truth argument as winner_autopsy itself: there must be exactly ONE
definition of "a position" (`exit_shape_parity_study.reconstruct_positions` via
`trade_autopsy.load_engine_positions`), ONE OPRA fetch path (`trade_autopsy.fetch_bars_cached`
-> `esp.fetch_option_bars`, real Alpaca OPRA 1-min, NO synthetic path exists), and ONE
entry+1 implementation (`winner_autopsy.entry_bar_minute` / `bars_between` per
markdown/audits/ENTRY-BAR-CONVENTION-RULING-2026-07-25.md). This module imports all of them
and adds only what is genuinely new: the excursion arithmetic and the ledger surface.

THE WINDOW (frozen)
-------------------
MAE/MFE are computed over the EXIT-ELIGIBLE HOLDING WINDOW: bars strictly AFTER the entry
bar's minute, through the final-exit-fill bar inclusive (`winner_autopsy.bars_between`).
  * entry bar excluded (entry+1): the live engine's exit pass cannot act inside the entry
    bar's own minute, so heat printed there is invisible to it -- excluded to match, and
    disclosed rather than pretended away.
  * nothing after the final exit bar counts: a crash AFTER we were flat is not pain we held
    through (winner_autopsy's 2026-07-31 case: flat 12:43 ET, day high 15:54 ET).

HONESTY RAILS (C7/L241)
-----------------------
  * REAL OPRA ONLY. Synthetic n=0 by construction of the fetch path; the meta block states
    it anyway so a reader never has to trust silence.
  * A position with no OPRA bars, or no exit-eligible bars, or a non-positive entry price is
    EXCLUDED AND COUNTED (n_no_bars / n_no_window / n_bad_entry, symbols listed) -- never
    zero-filled, never silently dropped. n_positions == n_scored + the three exclusion
    counters, asserted at build time.
  * `stop_inside_mae` means "the level TRADED THROUGH during the holding window" (1-min bar
    lows see every intra-minute print; the live actuator samples ~one NBBO snapshot per
    minute) -- it does NOT mean "live would have fired". Bias direction: overcounts touches.
  * $ figures are at FULL ENTRY QTY and each row carries `mae_before_first_exit` /
    `mfe_before_first_exit` so a reader can tell when the $ figure is hypothetical (the
    extreme printed after a partial exit had already reduced the position).

NIGHTLY: folded into the existing Gamma_WinnerAutopsy 16:25 ET fire (winner_autopsy.main
calls build_ledger with its own bar cache -- winners' bars are never fetched twice). No new
scheduled task. Fail-open there: a pain-ledger failure never costs the capture-rate product.

COST: $0. Pure Python + the same Alpaca OPRA bars endpoint every autopsy already uses.

Manual:
    python setup/scripts/pain_ledger.py                 # full population -> mae-mfe.json
    python setup/scripts/pain_ledger.py --report analysis/deep-research/PAIN-LEDGER-2026-08-01.md
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "pain-ledger.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "pain-ledger.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import json
import sys
import time as _time_mod
from datetime import datetime
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet",
           REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now  # noqa: E402

LEDGER_OUT = REPO / "analysis" / "pain-ledger" / "mae-mfe.json"
PREREG = "analysis/pain-ledger/PREREG-2026-08-01.md"
RECENT_N_DATES = 25            # frozen in the prereg: recent-25-distinct-ET-dates vs older
SMALL_N = 5                    # report cells below this n are flagged, never dropped
_EPS = 1e-9

DESCRIPTIVE_BANNER = (
    "⛔ DESCRIPTIVE ONLY — this ledger VALIDATES NO STOP CHANGE. MAE knowledge is hindsight "
    "by definition (C6): a live stop cannot condition on a trade's eventual maximum heat. "
    "Any stop-placement change is its own future pre-registered A/B that may cite this "
    "ledger only as its evidence base.")


# ---------- pure helpers (unit-tested; no I/O) ---------------------------------------------

def holding_window(bars: list[dict], entry_ts_utc: str, last_exit_ts_utc: str) -> list[dict]:
    """PURE: the exit-eligible holding window -- delegates to winner_autopsy.bars_between so
    there is exactly ONE entry+1 implementation in the repo (extend, don't fork). Exists as
    a named seam so the guard suite pins THIS module's window against both convention edges
    (entry-bar exclusion, final-exit-bar cutoff) without touching the shared frozen helper."""
    import winner_autopsy as wa
    return wa.bars_between(bars, entry_ts_utc, last_exit_ts_utc)


def bar_minute(ts: str) -> str:
    """PURE: alias of winner_autopsy.entry_bar_minute -- one bar-identity rule everywhere."""
    import winner_autopsy as wa
    return wa.entry_bar_minute(ts)


def minutes_between(bar_minute_a: str, bar_minute_b: str) -> int | None:
    """PURE: whole minutes from bar-minute key a to b ('YYYY-MM-DDTHH:MM'). None on parse
    failure -- honest absence, never a guessed zero."""
    try:
        a = datetime.strptime(bar_minute_a, "%Y-%m-%dT%H:%M")
        b = datetime.strptime(bar_minute_b, "%Y-%m-%dT%H:%M")
    except (ValueError, TypeError):
        return None
    return int(round((b - a).total_seconds() / 60.0))


def first_extremes(window: list[dict]) -> dict:
    """PURE: min low / max high over the window, each with the FIRST bar minute that printed
    it (frozen: time-to-extreme is time to first touch, not last). Empty window -> all None."""
    min_low = max_high = None
    min_low_bm = max_high_bm = None
    for b in window:
        lo, hi = float(b["l"]), float(b["h"])
        if min_low is None or lo < min_low - _EPS:
            min_low, min_low_bm = lo, bar_minute(b["t"])
        if max_high is None or hi > max_high + _EPS:
            max_high, max_high_bm = hi, bar_minute(b["t"])
    return {"min_low": min_low, "min_low_bar_minute": min_low_bm,
            "max_high": max_high, "max_high_bar_minute": max_high_bm}


def excursion_metrics(entry_price: float, qty: float, entry_ts_utc: str,
                      window: list[dict], first_exit_ts_utc: str) -> dict | None:
    """PURE: the frozen MAE/MFE row core. None when the window is empty (caller counts it).

    mae_pct = min(0, min_low/entry - 1)  (<= 0; 0.0 == never adverse -> time_to None)
    mfe_pct = max(0, max_high/entry - 1) (>= 0; 0.0 == never favorable -> time_to None)
    $ figures at FULL ENTRY QTY, flagged via *_before_first_exit (strictly-before test:
    an extreme printing in the SAME minute as the first exit fill is NOT 'before' it)."""
    if not window or entry_price <= 0:
        return None
    ex = first_extremes(window)
    entry_bm = bar_minute(entry_ts_utc)
    first_exit_bm = bar_minute(first_exit_ts_utc)

    mae_pct = min(0.0, ex["min_low"] / entry_price - 1.0)
    mfe_pct = max(0.0, ex["max_high"] / entry_price - 1.0)
    out = {
        "n_bars_walked": len(window),
        "min_low": round(ex["min_low"], 4),
        "max_high": round(ex["max_high"], 4),
        "mae_pct": round(mae_pct, 4),
        "mae_dollars_entry_qty": round(mae_pct * entry_price * qty * 100, 2),
        "time_to_mae_min": None,
        "mae_before_first_exit": None,
        "mfe_pct": round(mfe_pct, 4),
        "mfe_dollars_entry_qty": round(mfe_pct * entry_price * qty * 100, 2),
        "time_to_mfe_min": None,
        "mfe_before_first_exit": None,
    }
    if mae_pct < 0.0:
        out["time_to_mae_min"] = minutes_between(entry_bm, ex["min_low_bar_minute"])
        out["mae_before_first_exit"] = ex["min_low_bar_minute"] < first_exit_bm
    if mfe_pct > 0.0:
        out["time_to_mfe_min"] = minutes_between(entry_bm, ex["max_high_bar_minute"])
        out["mfe_before_first_exit"] = ex["max_high_bar_minute"] < first_exit_bm
    return out


def stop_fields(entry_price: float, placement: dict | None, arm_patch: dict | None) -> dict:
    """PURE: the as-configured-at-the-time stop, in premium terms, layered exactly like the
    live actuator resolves it (winner_autopsy.resolve_shipped_shape: engine default <- arm
    exit_patch <- as-placed placement block, most authoritative last).

    `stop_basis` keeps the reader honest about WHAT the premium number is:
      premium                  -- stop_mode recorded 'premium': this WAS the operative stop.
      structure_catastrophe_cap-- stop_mode 'structure': the operative stop was a chart
                                  level; the premium number is only the -50% catastrophe cap.
      premium_unverified       -- stop_mode unrecoverable: premium math shown, provenance not.
    """
    import winner_autopsy as wa
    shape = wa.resolve_shipped_shape(placement, arm_patch)
    pct = float(shape["premium_stop_pct"])
    if (placement or {}).get("premium_stop_pct") is not None:
        source = "placement"
    elif (arm_patch or {}).get("premium_stop_pct") is not None:
        source = "arm_patch"
    else:
        source = "default"
    stop_mode = (placement or {}).get("stop_mode")
    if stop_mode == "structure":
        basis = "structure_catastrophe_cap"
    elif stop_mode == "premium":
        basis = "premium"
    else:
        basis = "premium_unverified"
    return {"stop_mode": stop_mode, "stop_basis": basis, "premium_stop_pct": pct,
            "stop_premium": round(entry_price * (1.0 + pct), 4), "source": source}


def stop_inside_mae(min_low: float | None, stop_premium: float | None) -> bool | None:
    """PURE: did the adverse excursion trade AT or THROUGH the configured premium-stop level?
    Touch counts (frozen). None in, None out -- never a guessed False."""
    if min_low is None or stop_premium is None:
        return None
    return bool(min_low <= stop_premium + _EPS)


def classify_outcome(realized_pnl: float) -> str:
    """PURE: winner (>0) / loser (<0) / scratch (==0). Scratches are their own cohort so
    neither side quietly absorbs them."""
    if realized_pnl > 0:
        return "winner"
    if realized_pnl < 0:
        return "loser"
    return "scratch"


def recent_older_split(all_dates: list[str], n_recent: int = RECENT_N_DATES) -> tuple[set, set]:
    """PURE: the frozen recency cut -- the most recent `n_recent` DISTINCT ET dates in the
    population vs everything older. Returns (recent_set, older_set)."""
    distinct = sorted(set(all_dates))
    recent = set(distinct[-n_recent:]) if n_recent > 0 else set()
    return recent, set(distinct) - recent


def percentile(sorted_vals: list[float], p: float) -> float | None:
    """PURE: linear-interpolation percentile (numpy-default style) on an ASCENDING list.
    None on empty -- a percentile of nothing is not 0."""
    n = len(sorted_vals)
    if n == 0:
        return None
    if n == 1:
        return float(sorted_vals[0])
    idx = (p / 100.0) * (n - 1)
    lo = int(idx)
    hi = min(lo + 1, n - 1)
    frac = idx - lo
    return float(sorted_vals[lo] * (1.0 - frac) + sorted_vals[hi] * frac)


def dist(values: list[float]) -> dict:
    """PURE: the frozen report distribution -- n, mean, p25/p50/p75/p90. All-None on empty
    (never a zero-filled distribution)."""
    vals = sorted(float(v) for v in values)
    n = len(vals)
    if n == 0:
        return {"n": 0, "mean": None, "p25": None, "p50": None, "p75": None, "p90": None}
    return {"n": n,
            "mean": round(sum(vals) / n, 4),
            "p25": round(percentile(vals, 25), 4),
            "p50": round(percentile(vals, 50), 4),
            "p75": round(percentile(vals, 75), 4),
            "p90": round(percentile(vals, 90), 4)}


def build_rows(positions: list[dict], bars_for, placement_for, patches: dict,
               setup_for) -> dict:
    """Assemble every ledger row + the exclusion counters. All I/O is INJECTED (bars_for /
    placement_for / setup_for are callables) so the guard suite can drive this with fixtures
    and the accounting invariant is testable end-to-end:

        n_positions == n_scored + n_no_bars + n_no_window + n_bad_entry   (asserted)
    """
    rows: list[dict] = []
    no_bars: list[str] = []
    no_window: list[str] = []
    bad_entry: list[str] = []
    for pos in positions:
        tag = f"{pos['date_et']} {pos['arm']} {pos['symbol']}"
        entry_price = float(pos.get("entry_price") or 0.0)
        qty = float(pos.get("entry_qty") or 0.0)
        if entry_price <= 0 or qty <= 0:
            bad_entry.append(tag)
            continue
        bars = bars_for(pos)
        if not bars:
            no_bars.append(tag)
            continue
        exit_ts = sorted(ef["ts_utc"] for ef in pos["exit_fills"])
        window = holding_window(bars, pos["entry_ts_utc"], exit_ts[-1])
        core = excursion_metrics(entry_price, qty, pos["entry_ts_utc"], window, exit_ts[0])
        if core is None:
            no_window.append(tag)
            continue
        placement = placement_for(pos)
        stop = stop_fields(entry_price, placement, patches.get(pos["arm"]))
        stop["stop_inside_mae"] = stop_inside_mae(core["min_low"], stop["stop_premium"])
        realized = round(float(pos["actual_exit_pnl"]), 2)
        rows.append({
            "date": pos["date_et"], "arm": pos["arm"], "symbol": pos["symbol"],
            "setup": setup_for(pos, placement) or "(unattributed)",
            "outcome": classify_outcome(realized),
            "entry_ts_utc": pos["entry_ts_utc"],
            "entry_price": entry_price, "qty": qty,
            "realized_pnl": realized,
            "hold_minutes": minutes_between(bar_minute(pos["entry_ts_utc"]),
                                            bar_minute(exit_ts[-1])),
            "n_exit_legs": len(pos["exit_fills"]),
            **core,
            "stop": stop,
        })
    n_scored = len(rows)
    total = len(positions)
    assert total == n_scored + len(no_bars) + len(no_window) + len(bad_entry), (
        "pain-ledger accounting broke: positions leaked out of the counters "
        f"({total} != {n_scored}+{len(no_bars)}+{len(no_window)}+{len(bad_entry)})")
    rows.sort(key=lambda r: (r["date"], r["entry_ts_utc"], r["arm"], r["symbol"]))
    return {"rows": rows, "n_positions": total, "n_scored": n_scored,
            "no_bars": no_bars, "no_window": no_window, "bad_entry": bad_entry}


# ---------- I/O layer ----------------------------------------------------------------------

def _load_all_positions() -> list[dict]:
    """Every closed engine option position, all dates, via the ONE shared loader."""
    import trade_autopsy as ta
    import winner_autopsy as wa
    positions: list[dict] = []
    for d in sorted(wa._all_ledger_dates()):
        positions.extend(ta.load_engine_positions(d))
    return positions


def build_ledger(bar_cache: dict | None = None, out_path: Path = LEDGER_OUT) -> dict:
    """Full-population build -> mae-mfe.json. Returns the summary dict (what the nightly
    winner_autopsy fold records). `bar_cache` is shared with winner_autopsy's own walk when
    called from there, so winners' bars are fetched exactly once per fire."""
    import exit_shape_parity_study as esp
    import trade_autopsy as ta
    import winner_autopsy as wa

    started = et_now()
    positions = _load_all_positions()
    cache = bar_cache if bar_cache is not None else {}
    patches = wa.load_arm_exit_patches()
    arm_rows_cache: dict = {}

    def bars_for(pos: dict) -> list[dict]:
        fresh = (pos["symbol"], pos["date_et"]) not in cache
        bars = ta.fetch_bars_cached(esp, pos["symbol"], pos["date_et"], cache)
        if fresh:
            _time_mod.sleep(0.05)   # be polite to the data API on cache misses only
        return bars

    def _arm_rows(pos: dict) -> list[dict]:
        key = (pos["arm"], pos["date_et"])
        if key not in arm_rows_cache:
            arm_rows_cache[key] = wa.load_arm_rows(pos["arm"], pos["date_et"])
        return arm_rows_cache[key]

    def placement_for(pos: dict) -> dict | None:
        row = wa.find_entry_decision(_arm_rows(pos), pos["symbol"])
        if not row:
            return None
        return row.get("placement") or row.get("exec")

    def setup_for(pos: dict, placement: dict | None) -> str | None:
        row = wa.find_entry_decision(_arm_rows(pos), pos["symbol"])
        if row and (row.get("setup_name") or row.get("setup")):
            return row.get("setup_name") or row.get("setup")
        return ta.lookup_strategy(pos["arm"], pos["symbol"], pos["entry_ts_utc"])

    built = build_rows(positions, bars_for, placement_for, patches, setup_for)
    dates = sorted({r["date"] for r in built["rows"]})
    recent, older = recent_older_split([r["date"] for r in built["rows"]])
    for r in built["rows"]:
        r["recency"] = "recent25" if r["date"] in recent else "older"

    ledger = {
        "_meta": {
            "generated_at_et": started.isoformat(),
            "builder": "setup/scripts/pain_ledger.py",
            "prereg": PREREG,
            "descriptive_only": DESCRIPTIVE_BANNER,
            "provenance": {
                "pnl": "broker fills (fills-ledger.jsonl, attribution==engine)",
                "bars": "real Alpaca OPRA 1-min via exit_shape_parity_study.fetch_option_bars",
                "synthetic_rows": 0,
                "synthetic_note": ("no synthetic pricing path exists in this machinery; "
                                   "positions without OPRA bars are excluded AND counted"),
            },
            "conventions": {
                "window": "exit-eligible holding window (entry+1 .. final-exit bar incl.)",
                "entry_bar": "excluded per ENTRY-BAR-CONVENTION-RULING-2026-07-25",
                "stop_inside_mae": "level traded through on bar lows; NOT 'live would have fired'",
                "dollars": "at full entry qty; see *_before_first_exit validity flags",
                "recent_split": f"most recent {RECENT_N_DATES} distinct ET dates vs older",
            },
            "population": {
                "n_positions": built["n_positions"],
                "n_scored": built["n_scored"],
                "n_no_bars": len(built["no_bars"]),
                "n_no_window": len(built["no_window"]),
                "n_bad_entry": len(built["bad_entry"]),
                "excluded_no_bars": built["no_bars"],
                "excluded_no_window": built["no_window"],
                "excluded_bad_entry": built["bad_entry"],
                "n_winners": sum(1 for r in built["rows"] if r["outcome"] == "winner"),
                "n_losers": sum(1 for r in built["rows"] if r["outcome"] == "loser"),
                "n_scratch": sum(1 for r in built["rows"] if r["outcome"] == "scratch"),
                "dates": {"n_distinct": len(dates),
                          "first": dates[0] if dates else None,
                          "last": dates[-1] if dates else None,
                          "recent25_first": min(recent) if recent else None},
                "arms": sorted({r["arm"] for r in built["rows"]}),
            },
        },
        "trades": built["rows"],
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(ledger, indent=1), encoding="utf-8")
    summary = {
        "generated_at_et": started.isoformat(),
        "out": str(out_path.relative_to(REPO)).replace("\\", "/"),
        "n_positions": built["n_positions"], "n_scored": built["n_scored"],
        "n_no_bars": len(built["no_bars"]), "n_no_window": len(built["no_window"]),
        "n_bad_entry": len(built["bad_entry"]),
        "descriptive_only": True,
    }
    print(f"[pain-ledger] {built['n_scored']}/{built['n_positions']} positions scored "
          f"({len(built['no_bars'])} no-bars, {len(built['no_window'])} no-window, "
          f"{len(built['bad_entry'])} bad-entry) -> {summary['out']}")
    return summary


# ---------- report (one-off, invoked manually -- NOT part of the nightly) ------------------

def _fmt_pct(x) -> str:
    return "n/a" if x is None else f"{x * 100:.1f}%"


def _dist_row(label: str, d: dict, flag_small: bool = True) -> str:
    flag = " ⚠small-n" if flag_small and 0 < d["n"] < SMALL_N else ""
    return (f"| {label} | {d['n']}{flag} | {_fmt_pct(d['mean'])} | {_fmt_pct(d['p25'])} | "
            f"{_fmt_pct(d['p50'])} | {_fmt_pct(d['p75'])} | {_fmt_pct(d['p90'])} |")


def _median_int(vals: list) -> str:
    usable = sorted(v for v in vals if v is not None)
    if not usable:
        return "n/a"
    return f"{usable[len(usable) // 2]:.0f}m"


def render_report(ledger: dict) -> str:
    """The frozen report cuts (prereg §'Frozen report cuts'), ALL cells rendered."""
    meta = ledger["_meta"]
    rows = ledger["trades"]
    pop = meta["population"]
    L: list[str] = []
    L.append("# PAIN LEDGER — MAE/MFE over every closed engine trade (2026-08-01)")
    L.append("")
    L.append(f"> # {DESCRIPTIVE_BANNER}")
    L.append(">")
    L.append("> Nothing in this file is a pass/fail verdict, a knob proposal, or evidence "
             "sufficient for one. It answers ONE question: *what did our filled trades "
             "actually live through?*")
    L.append("")
    L.append(f"_Generated {meta['generated_at_et']} ET · prereg `{meta['prereg']}` "
             f"(committed before the builder existed) · real OPRA 1-min bars · entry+1 "
             f"holding-window · $0._")
    L.append("")
    L.append("## Population + provenance")
    L.append("")
    L.append(f"- **{pop['n_scored']} of {pop['n_positions']}** closed engine option positions "
             f"scored ({pop['n_winners']} winners / {pop['n_losers']} losers / "
             f"{pop['n_scratch']} scratch), arms: {', '.join(pop['arms'])}, "
             f"{pop['dates']['n_distinct']} ET dates {pop['dates']['first']} → "
             f"{pop['dates']['last']}.")
    L.append(f"- Excluded AND counted: {pop['n_no_bars']} no-OPRA-bars, "
             f"{pop['n_no_window']} no-exit-eligible-window, {pop['n_bad_entry']} bad-entry "
             f"(symbols in `mae-mfe.json` `_meta.population`). Synthetic rows: **0 by "
             f"construction** (no synthetic path exists in this machinery).")
    L.append(f"- P&L = broker fills; excursions = real Alpaca OPRA 1-min bar lows/highs.")
    L.append(f"- Recency split: most recent {RECENT_N_DATES} distinct ET dates "
             f"(from {pop['dates']['recent25_first']}) vs older.")
    L.append("")

    def cohort(rows_, name):
        return [r for r in rows_ if r["outcome"] == name]

    def plural(name: str) -> str:
        return "scratches" if name == "scratch" else name + "s"

    # ---- cut 1: MAE distribution, winners vs losers vs scratch ----------------------
    L.append("## 1 · How much heat? |MAE| distribution by outcome (premium %, whole population)")
    L.append("")
    L.append("| Cohort | n | mean | p25 | p50 | p75 | p90 |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for name in ("winner", "loser", "scratch"):
        c = cohort(rows, name)
        L.append(_dist_row(f"**{plural(name)}**", dist([-r["mae_pct"] for r in c]),
                           flag_small=False))
    L.append("")
    L.append("_|MAE| shown as positive magnitude (a p50 of 20% means half the cohort never "
             "traded more than 20% below entry during the holding window)._")
    L.append("")

    # ---- cut 2: by setup family -----------------------------------------------------
    L.append("## 2 · By setup family (winners vs losers; every family shown, small-n flagged)")
    L.append("")
    fams = sorted({r["setup"] for r in rows})
    L.append("| Setup family | outcome | n | mean |MAE| | p50 |MAE| | p75 |MAE| | p50 MFE | med t→MAE | med t→MFE |")
    L.append("|---|---|---:|---:|---:|---:|---:|---:|---:|")
    for fam in fams:
        for name in ("winner", "loser"):
            c = [r for r in rows if r["setup"] == fam and r["outcome"] == name]
            if not c:
                L.append(f"| `{fam}` | {name} | 0 | — | — | — | — | — | — |")
                continue
            d = dist([-r["mae_pct"] for r in c])
            flag = " ⚠small-n" if d["n"] < SMALL_N else ""
            L.append(f"| `{fam}` | {name} | {d['n']}{flag} | {_fmt_pct(d['mean'])} | "
                     f"{_fmt_pct(d['p50'])} | {_fmt_pct(d['p75'])} | "
                     f"{_fmt_pct(dist([r['mfe_pct'] for r in c])['p50'])} | "
                     f"{_median_int([r['time_to_mae_min'] for r in c])} | "
                     f"{_median_int([r['time_to_mfe_min'] for r in c])} |")
    L.append("")

    # ---- cut 3: recency --------------------------------------------------------------
    L.append(f"## 3 · Recent-{RECENT_N_DATES}-dates vs older (recency > aggregate)")
    L.append("")
    L.append("| Window | outcome | n | mean |MAE| | p50 |MAE| | p75 |MAE| | p50 MFE |")
    L.append("|---|---|---:|---:|---:|---:|---:|")
    for win in ("recent25", "older"):
        for name in ("winner", "loser", "scratch"):
            c = [r for r in rows if r["recency"] == win and r["outcome"] == name]
            d = dist([-r["mae_pct"] for r in c])
            flag = " ⚠small-n" if 0 < d["n"] < SMALL_N else ""
            L.append(f"| {win} | {name} | {d['n']}{flag} | {_fmt_pct(d['mean'])} | "
                     f"{_fmt_pct(d['p50'])} | {_fmt_pct(d['p75'])} | "
                     f"{_fmt_pct(dist([r['mfe_pct'] for r in c])['p50'])} |")
    L.append("")
    if not any(r["recency"] == "older" for r in rows):
        L.append(f"_⚠ The **older cohort is EMPTY today**: the population spans only "
                 f"{pop['dates']['n_distinct']} distinct ET dates (≤ {RECENT_N_DATES}), so "
                 f"every trade falls inside the frozen recent-{RECENT_N_DATES} window. The "
                 f"split is kept AS FROZEN (not re-tuned post-hoc) and becomes informative "
                 f"as dates accrue._")
        L.append("")

    # ---- cut 4: MFE + timing --------------------------------------------------------
    L.append("## 4 · MFE + timing (medians)")
    L.append("")
    L.append("| Cohort | n | p50 MFE | p90 MFE | med t→MAE | med t→MFE | med hold |")
    L.append("|---|---:|---:|---:|---:|---:|---:|")
    for name in ("winner", "loser", "scratch"):
        c = cohort(rows, name)
        dm = dist([r["mfe_pct"] for r in c])
        L.append(f"| {plural(name)} | {dm['n']} | {_fmt_pct(dm['p50'])} | {_fmt_pct(dm['p90'])} | "
                 f"{_median_int([r['time_to_mae_min'] for r in c])} | "
                 f"{_median_int([r['time_to_mfe_min'] for r in c])} | "
                 f"{_median_int([r['hold_minutes'] for r in c])} |")
    L.append("")

    # ---- cut 5: stop-inside-MAE -----------------------------------------------------
    L.append("## 5 · Configured stop vs MAE (`stop_inside_mae` = level traded through, "
             "NOT 'live would have fired')")
    L.append("")
    L.append("| Cohort | stop basis | n | stop inside MAE | stop outside MAE | unknown |")
    L.append("|---|---|---:|---:|---:|---:|")
    bases = sorted({r["stop"]["stop_basis"] for r in rows})
    for name in ("winner", "loser", "scratch"):
        for basis in bases:
            c = [r for r in rows if r["outcome"] == name and r["stop"]["stop_basis"] == basis]
            if not c:
                continue
            inside = sum(1 for r in c if r["stop"]["stop_inside_mae"] is True)
            outside = sum(1 for r in c if r["stop"]["stop_inside_mae"] is False)
            unk = sum(1 for r in c if r["stop"]["stop_inside_mae"] is None)
            L.append(f"| {plural(name)} | `{basis}` | {len(c)} | {inside} | {outside} | {unk} |")
    L.append("")
    L.append("_`structure_catastrophe_cap` rows: the operative stop was a CHART level; the "
             "premium number tested here is only the −50% catastrophe cap. "
             "`premium_unverified`: stop_mode was not recoverable from the decision ledger._")
    L.append("")

    # ---- limitations ----------------------------------------------------------------
    L.append("---")
    L.append("")
    L.append("## Method / disclosed limitations (frozen in the prereg — read before quoting)")
    L.append("")
    L.append("- **Bar-low basis:** 1-min bar lows see every intra-minute print; the live "
             "actuator samples ~one NBBO snapshot per minute. `stop_inside_mae` overcounts "
             "touches relative to live behavior — by design, and labelled.")
    L.append("- **entry+1:** heat inside the entry bar's own minute is excluded (the live "
             "exit pass cannot act there); nothing after the final exit bar counts.")
    L.append("- **$ figures at full entry qty** — `*_before_first_exit` flags mark when an "
             "extreme postdates a partial exit (the $ figure is hypothetical there).")
    L.append("- **Sub-$0.20-premium entries quantize the % stats:** on a $0.02 entry, one "
             "$0.01 tick is ±50% of premium, so MAE/MFE percentages in that cohort are "
             "tick-noise multiples (the noise-floor lesson). The $0.30 min-entry-premium "
             "floor (KEEP, real provenance) removes these going forward; historical rows "
             "keep them, labelled by their `entry_price`.")
    L.append("- **No significance tests anywhere** — these are distributions, not claims. A "
             "future study slicing this ledger to hunt an effect owes its own prereg + FDR.")
    L.append("- **Winners took their heat and lived; losers' MAE is bounded below by their "
             "exits** (a stopped trade cannot show heat past its stop). Comparing the two "
             "cohorts' MAE is conditioned on the exit policy that produced them — one more "
             "reason this ledger cannot validate a stop by itself.")
    L.append("")
    L.append(f"_Ledger: `analysis/pain-ledger/mae-mfe.json` · builder "
             f"`setup/scripts/pain_ledger.py` · refreshed nightly by the existing "
             f"`Gamma_WinnerAutopsy` 16:25 ET fire (no new task)._")
    return "\n".join(L) + "\n"


# ---------- main ----------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="MAE/MFE pain ledger (descriptive only).")
    ap.add_argument("--out", default=None, help="override ledger output path")
    ap.add_argument("--report", default=None,
                    help="ALSO render the one-off descriptive report to this path")
    args = ap.parse_args()
    try:
        out = Path(args.out) if args.out else LEDGER_OUT
        build_ledger(out_path=out)
        if args.report:
            ledger = json.loads(out.read_text(encoding="utf-8"))
            rp = Path(args.report)
            rp.parent.mkdir(parents=True, exist_ok=True)
            rp.write_text(render_report(ledger), encoding="utf-8")
            print(f"[pain-ledger] report -> {args.report}")
    except Exception as e:  # noqa: BLE001 -- notify-only organ: never propagate a failure
        print(f"[pain-ledger] ERROR (fail-open): {type(e).__name__}: {e}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

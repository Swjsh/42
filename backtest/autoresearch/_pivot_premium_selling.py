"""PIVOT: 0DTE SPY PREMIUM-SELLING research harness (defined-risk credit structures).

THE THESIS: ~64 long-premium families died because BUYING 0DTE premium pays theta +
fights delta decay (C3 / L58). SELLING defined-risk premium INVERTS this — theta is
income, structurally high win-rate, and it PROFITS in range/chop (the regime currently
drawing down the bull-directional book). New strategy CLASS, in-scope (0DTE SPY options),
testable on the OPRA cache.

Combines per-leg OPRA 5m fills (via simulator_credit, which reuses simulator_real's
loader byte-for-byte) into spread/condor net-credit P&L paths over a grid of:
    structure x short-offset x wing-width x entry-time x {pt_frac, stop_mult}
and scores each variant against the PREMIUM-SELLING gate bar.

*** CACHE CONSTRAINT (designed around) ***
The OPRA cache is a FIXED ~$10-wide band (11 $1 strikes/side, +/-$5 around ATM). So:
  - short strikes are a $-OFFSET from ATM, NOT a delta target (no Greeks; band can't
    reach true 16-delta on wide days). Realized %OTM reported per trade.
  - wings are NARROW ($1-$3) — a tighter, higher-PoP / lower-credit condor than the
    textbook 30-wide. Disclosed divergence from the cited playbook.
  - any day with a required strike OUTSIDE the band is SKIPPED + logged; skip-rate is
    itself a finding (the cache cannot validate wide condors).

Run (offline, $0):
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_pivot_premium_selling.py --smoke
  backtest/.venv/Scripts/python.exe backtest/autoresearch/_pivot_premium_selling.py --full
"""
from __future__ import annotations

import argparse
import datetime as dt
import glob
import json
import os
import re
import statistics
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

# Make `lib` importable whether run as module or script.
_HERE = Path(__file__).resolve()
_BT = _HERE.parents[1]
if str(_BT) not in sys.path:
    sys.path.insert(0, str(_BT))

from lib import simulator_credit as sc                       # noqa: E402
from lib.multileg_structures import build_legs, legs_in_band  # noqa: E402

# ── L177: single source of truth for the per-day eligibility pre-filter ─────
# run_variant() (production), the random-null, AND the IC-validate null MUST apply
# the IDENTICAL band pre-filter by construction. When the standalone null omitted /
# diverged on this filter it priced off=4 condors production never takes, dragging the
# null mean and INFLATING the actual's apparent percentile (94.8th vs the true ~76th) —
# a knife-edge that flips PASS/FAIL on the RNG seed. Every harness calls THIS function
# (not a private legs_in_band(half_width=...) literal) so the band is byte-identical.
BAND_HALF_WIDTH = 5


def eligible(legs, spot: float) -> bool:
    """True iff `legs` are tradeable under production's strike-universe band.
    The ONE eligibility gate every premium-selling harness (production + every null)
    must share — see L177 / OP-16 sim-accuracy gate."""
    return legs_in_band(legs, spot, half_width=BAND_HALF_WIDTH)


DATA = _BT / "data"
OPT_DIR = DATA / "options"
OUT_DIR = _BT / "autoresearch" / "_state" / "pivot_premium_selling"

# ── Grid (per the spec) ───────────────────────────────────────────────────
STRUCTURES = ["IC", "PCS", "CCS", "IB", "BWIC"]
ENTRY_TIMES_ET = [dt.time(9, 40), dt.time(10, 30), dt.time(11, 0),
                  dt.time(13, 0), dt.time(14, 30)]
SHORT_OFFSETS = [2, 3, 4]      # $-offset from ATM (cache forbids delta targeting)
WING_WIDTHS = [1, 2]           # narrow wings the band can actually price
PT_FRACS = [0.25, 0.50]
STOP_MULTS: list[Optional[float]] = [1.5, 2.0, None]  # None = EOD-only (no stop)

# IS/OOS split: IS = 2025 H1 (Jan-Jun 2025), OOS = all of 2026.
IS_2025_START = dt.date(2025, 1, 1)
IS_2025_END = dt.date(2025, 6, 30)
OOS_2026_START = dt.date(2026, 1, 1)

# Kill-switch caps (per CLAUDE.md): Safe -30%/day on $2K = -$600; Bold -50% = -$835.
# For tail-survivability we use the SAFE cap as the binding constraint per 1-lot scaled
# reasonably. We report the raw per-1-lot max single-day loss + book maxDD and compare.
SAFE_KILL_DOLLARS = 600.0


@dataclass
class VariantScore:
    structure: str
    entry_time: str
    short_offset: int
    wing_width: int
    pt_frac: float
    stop_mult: Optional[float]
    n: int
    n_skipped: int
    skip_rate: float
    wr: float
    expectancy: float            # mean realized_pnl per trade ($, net costs)
    total_pnl: float
    avg_win: float
    avg_loss: float
    max_single_day_loss: float
    book_max_dd: float
    n_oos: int
    expectancy_oos: float
    posq_oos: int                # positive quarters out of up-to-6 OOS sub-windows
    n_is25: int
    expectancy_is25: float
    drop_top5_expectancy: float
    drop_worst5_expectancy: float
    oos_drop_top5_expectancy: float
    recency_n: int
    recency_expectancy: float
    avg_pct_otm: float
    avg_credit: float
    intrabar_stop_extra_hits: int  # bars where intrabar-worst would've stopped but close didn't
    tail_survivable: bool
    gate_pass: bool
    gate_notes: str


def _option_cache_dates() -> set[dt.date]:
    dates: set[dt.date] = set()
    for p in glob.glob(str(OPT_DIR / "SPY*P*.csv")):
        m = re.search(r"SPY(\d{6})P", os.path.basename(p))
        if m:
            try:
                dates.add(dt.datetime.strptime(m.group(1), "%y%m%d").date())
            except ValueError:
                pass
    return dates


def _load_spy_master() -> pd.DataFrame:
    """Union the long master SPY (through 06-16) with the freshest file (through 06-18)."""
    frames = []
    for name in ("spy_5m_2025-01-01_2026-06-16.csv", "spy_5m_2026-05-19_2026-06-18.csv"):
        p = DATA / name
        if p.exists():
            df = pd.read_csv(p)
            frames.append(df)
    spy = pd.concat(frames, ignore_index=True)
    spy["ts"] = pd.to_datetime(spy["timestamp_et"], utc=True)
    spy = spy.drop_duplicates(subset="ts").sort_values("ts").reset_index(drop=True)
    spy["date"] = spy["ts"].dt.tz_convert("America/New_York").dt.date
    spy["time_et"] = spy["ts"].dt.tz_convert("America/New_York").dt.time
    spy["dt_naive"] = spy["ts"].dt.tz_convert("America/New_York").dt.tz_localize(None)
    return spy


def _spot_and_decision(spy_day: pd.DataFrame, entry_time: dt.time):
    """Return (decision_dt_naive, spot_at_decision, spot_close) for an entry time.

    decision = the bar whose time is the LAST bar at/before entry_time (the bar that has
    just closed). spot = that bar's close. spot_close = the day's final bar close.
    """
    rows = spy_day[spy_day["time_et"] <= entry_time]
    if rows.empty:
        return None, None, None
    drow = rows.iloc[-1]
    spot_close = float(spy_day.iloc[-1]["close"])
    return drow["dt_naive"].to_pydatetime(), float(drow["close"]), spot_close


def _build_variant_legs(structure, spot, short_offset, wing_width):
    if structure == "BWIC":
        # Broken-wing: skew the CALL side $1 further out + $1 wider (kill upside tail lean).
        return build_legs(spot, "BWIC", short_offset=short_offset, wing_width=wing_width,
                          call_short_offset=short_offset + 1, call_wing_width=wing_width + 1)
    if structure == "IB":
        return build_legs(spot, "IB", short_offset=0, wing_width=wing_width)
    return build_legs(spot, structure, short_offset=short_offset, wing_width=wing_width)


def run_variant(structure, entry_time, short_offset, wing_width, pt_frac, stop_mult,
                spy, day_list, commission=0.65, verbose=False):
    """Run one variant across all days. Returns (fills, scored)."""
    fills: list[sc.CreditFill] = []
    for d in day_list:
        spy_day = spy[spy["date"] == d]
        if spy_day.empty:
            continue
        decision_dt, spot, _ = _spot_and_decision(spy_day, entry_time)
        if decision_dt is None or spot is None or spot <= 0:
            continue
        legs = _build_variant_legs(structure, spot, short_offset, wing_width)
        # Cheap band pre-filter (necessary, not sufficient — sim still verifies CSVs).
        # Shared eligible() helper so every null mirrors this EXACTLY (L177).
        if not eligible(legs, spot):
            f = sc.CreditFill(date=d.strftime("%Y-%m-%d"), structure=structure,
                              skipped=True, skip_reason="out_of_band")
            fills.append(f)
            continue
        # binding wing for asymmetric structures = the widest wing
        binding_wing = wing_width + (1 if structure == "BWIC" else 0)
        f = sc.simulate_credit_trade(
            d, legs, decision_dt, spot, wing_width=binding_wing,
            structure_name=structure, contracts=1, pt_frac=pt_frac, stop_mult=stop_mult,
            commission_per_contract=commission)
        fills.append(f)
        if verbose and not f.skipped:
            print(f"  {d} {structure} credit=${f.net_credit:.0f} "
                  f"maxloss=${f.max_loss_defined:.0f} exit={f.exit_reason} "
                  f"pnl=${f.realized_pnl:.0f} %OTM={f.realized_pct_otm:.2f}")
    return fills


def _expectancy(pnls: list[float]) -> float:
    return statistics.mean(pnls) if pnls else 0.0


def _drop_top_n(pnls: list[float], n: int) -> list[float]:
    if len(pnls) <= n:
        return []
    return sorted(pnls, reverse=True)[n:]


def _drop_worst_n(pnls: list[float], n: int) -> list[float]:
    if len(pnls) <= n:
        return []
    return sorted(pnls)[n:]


def _book_max_dd(dated_pnls: list[tuple[dt.date, float]]) -> float:
    """Running equity drawdown ($) over the chronological trade sequence."""
    eq = 0.0
    peak = 0.0
    mdd = 0.0
    for _, p in sorted(dated_pnls, key=lambda x: x[0]):
        eq += p
        peak = max(peak, eq)
        mdd = min(mdd, eq - peak)
    return mdd


def _quarter_key(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def _oos_subwindow_key(d: dt.date) -> str:
    """Sub-window key for posQ. OOS-2026 spans only ~Jan-Jun (2 calendar quarters),
    so calendar-quarter counting caps posQ at 2 and makes the spec's posQ>=4/6 gate
    UNREACHABLE by construction. The spec intent is '>=4 of ~6 OOS sub-windows', so
    we split OOS by calendar MONTH (6 sub-windows across Jan-Jun 2026). Each month
    with mean realized pnl > 0 counts as one positive sub-window."""
    return f"{d.year}-{d.month:02d}"


def score_variant(structure, entry_time, short_offset, wing_width, pt_frac, stop_mult,
                  fills: list[sc.CreditFill]) -> VariantScore:
    taken = [f for f in fills if not f.skipped]
    n_skipped = sum(1 for f in fills if f.skipped)
    skip_rate = n_skipped / len(fills) if fills else 0.0

    def _d(f):
        return dt.date.fromisoformat(f.date)

    pnls = [f.realized_pnl for f in taken]
    dated = [(_d(f), f.realized_pnl) for f in taken]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]

    oos = [f for f in taken if _d(f) >= OOS_2026_START]
    is25 = [f for f in taken if IS_2025_START <= _d(f) <= IS_2025_END]
    oos_pnls = [f.realized_pnl for f in oos]
    is25_pnls = [f.realized_pnl for f in is25]

    # OOS positive sub-windows (posQ): OOS-2026 = ~6 calendar MONTHS (Jan-Jun), so we
    # count monthly sub-windows with mean>0 (calendar quarters would cap posQ at 2 and
    # make the spec's posQ>=4/6 gate structurally impossible). Require a sub-window to
    # have >=2 trades to count (a single lucky day is not a positive sub-window).
    by_q: dict[str, list[float]] = {}
    for f in oos:
        by_q.setdefault(_oos_subwindow_key(_d(f)), []).append(f.realized_pnl)
    posq = sum(1 for v in by_q.values() if len(v) >= 2 and statistics.mean(v) > 0)

    # recency: freshest ~25 trading days of taken trades
    recency = [f for f in sorted(taken, key=lambda x: x.date)][-25:]
    recency_pnls = [f.realized_pnl for f in recency]

    max_day_loss = min(pnls) if pnls else 0.0
    book_dd = _book_max_dd(dated)
    tail_survivable = (abs(max_day_loss) <= SAFE_KILL_DOLLARS
                       and abs(book_dd) <= SAFE_KILL_DOLLARS * 3)  # ~3 bad days of cushion

    intrabar_extra = sum(1 for f in taken if f.intrabar_stop_would_hit)

    expc = _expectancy(pnls)
    expc_oos = _expectancy(oos_pnls)
    expc_is25 = _expectancy(is25_pnls)

    # Gate evaluation (premium-selling adapted bar).
    notes = []
    g1 = expc_oos > 0;                                   notes.append(f"OOSexp>0:{g1}")
    g2 = len(oos) >= 20;                                 notes.append(f"OOSn>=20:{g2}({len(oos)})")
    g3 = posq >= 4;                                      notes.append(f"posQ>=4:{g3}({posq})")
    g4 = tail_survivable;                                notes.append(f"tail_ok:{g4}")
    oos_dtop5 = _expectancy(_drop_top5 := _drop_top_n(oos_pnls, 5))
    dtop5 = _expectancy(_drop_top_n(pnls, 5))
    dworst5 = _expectancy(_drop_worst_n(pnls, 5))
    g5 = (oos_dtop5 > 0) and (dtop5 > 0);                notes.append(f"drop_top5>0:{g5}")
    g7 = expc_is25 > 0;                                  notes.append(f"IS25exp>0:{g7}")
    g8 = (_expectancy(recency_pnls) > 0);                notes.append(f"recency>0:{g8}")
    gate_pass = all([g1, g2, g3, g4, g5, g7, g8])

    return VariantScore(
        structure=structure, entry_time=entry_time.strftime("%H:%M"),
        short_offset=short_offset, wing_width=wing_width, pt_frac=pt_frac,
        stop_mult=stop_mult, n=len(taken), n_skipped=n_skipped, skip_rate=round(skip_rate, 3),
        wr=round(len(wins) / len(pnls), 3) if pnls else 0.0,
        expectancy=round(expc, 2), total_pnl=round(sum(pnls), 2),
        avg_win=round(_expectancy(wins), 2), avg_loss=round(_expectancy(losses), 2),
        max_single_day_loss=round(max_day_loss, 2), book_max_dd=round(book_dd, 2),
        n_oos=len(oos), expectancy_oos=round(expc_oos, 2), posq_oos=posq,
        n_is25=len(is25), expectancy_is25=round(expc_is25, 2),
        drop_top5_expectancy=round(dtop5, 2), drop_worst5_expectancy=round(dworst5, 2),
        oos_drop_top5_expectancy=round(oos_dtop5, 2),
        recency_n=len(recency), recency_expectancy=round(_expectancy(recency_pnls), 2),
        avg_pct_otm=round(_expectancy([f.realized_pct_otm for f in taken]), 3),
        avg_credit=round(_expectancy([f.net_credit for f in taken]), 2),
        intrabar_stop_extra_hits=intrabar_extra,
        tail_survivable=tail_survivable, gate_pass=gate_pass, gate_notes="; ".join(notes),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="1-date leg-by-leg sanity run")
    ap.add_argument("--full", action="store_true", help="full grid sweep + gate scoring")
    ap.add_argument("--commission", type=float, default=0.65)
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    cache_dates = _option_cache_dates()
    spy = _load_spy_master()
    spy_dates = set(spy["date"].unique())
    day_list = sorted(cache_dates & spy_dates)
    print(f"[pivot] OPRA-cache dates={len(cache_dates)} SPY dates={len(spy_dates)} "
          f"INTERSECTION={len(day_list)} ({day_list[0]}..{day_list[-1]})")

    if args.smoke:
        # 1-date leg-by-leg sanity on the freshest day in the band.
        d = day_list[-1]
        spy_day = spy[spy["date"] == d]
        decision_dt, spot, spot_close = _spot_and_decision(spy_day, dt.time(9, 40))
        print(f"\n[SMOKE] {d} spot@9:40={spot:.2f} close={spot_close:.2f}")
        for structure in ["IC", "PCS", "CCS", "IB"]:
            legs = _build_variant_legs(structure, spot, 3, 2)
            binding_wing = 2
            f = sc.simulate_credit_trade(d, legs, decision_dt, spot, wing_width=binding_wing,
                                         structure_name=structure, pt_frac=0.5, stop_mult=2.0,
                                         commission_per_contract=args.commission)
            print(f"\n  {structure}: skipped={f.skipped} {f.skip_reason}")
            if not f.skipped:
                for lf in f.legs:
                    print(f"    leg {lf.side}{lf.strike} sign={lf.qty_sign:+d} "
                          f"entry={lf.entry_fill:.2f} exit={lf.exit_fill:.2f} "
                          f"(bar.open={lf.entry_bar_open:.2f})")
                print(f"    net_credit=${f.net_credit:.0f} max_loss=${f.max_loss_defined:.0f} "
                      f"exit={f.exit_reason}@{f.exit_time_et} pnl=${f.realized_pnl:.0f} "
                      f"%OTM={f.realized_pct_otm:.2f} maxfav=${f.max_favorable:.0f} "
                      f"maxadv=${f.max_adverse:.0f} intrabar_worst=${f.intrabar_worst_mtm:.0f}")
        return

    if args.full:
        results: list[VariantScore] = []
        total = (len(STRUCTURES) * len(ENTRY_TIMES_ET) * len(SHORT_OFFSETS)
                 * len(WING_WIDTHS) * len(PT_FRACS) * len(STOP_MULTS))
        i = 0
        for structure in STRUCTURES:
            for entry_time in ENTRY_TIMES_ET:
                for short_offset in SHORT_OFFSETS:
                    for wing_width in WING_WIDTHS:
                        for pt_frac in PT_FRACS:
                            for stop_mult in STOP_MULTS:
                                i += 1
                                fills = run_variant(structure, entry_time, short_offset,
                                                    wing_width, pt_frac, stop_mult,
                                                    spy, day_list, commission=args.commission)
                                vs = score_variant(structure, entry_time, short_offset,
                                                   wing_width, pt_frac, stop_mult, fills)
                                results.append(vs)
                                if i % 25 == 0 or i == total:
                                    print(f"[pivot] {i}/{total} variants scored")

        results.sort(key=lambda v: (v.gate_pass, v.expectancy_oos), reverse=True)
        out_json = OUT_DIR / "results.json"
        with open(out_json, "w") as fh:
            json.dump([asdict(v) for v in results], fh, indent=2, default=str)
        print(f"\n[pivot] wrote {out_json} ({len(results)} variants)")

        passers = [v for v in results if v.gate_pass]
        print(f"\n[pivot] GATE-PASSERS: {len(passers)}")
        print(f"\n=== TOP 15 by OOS expectancy ===")
        hdr = (f"{'struct':6} {'entry':5} {'off':3} {'w':2} {'pt':4} {'stop':5} "
               f"{'n':4} {'skip%':6} {'WR':5} {'exp$':7} {'OOSexp':7} {'posQ':4} "
               f"{'maxDayL':8} {'bookDD':8} {'tail':5} {'GATE':5}")
        print(hdr)
        for v in results[:15]:
            sm = "EOD" if v.stop_mult is None else f"{v.stop_mult}x"
            print(f"{v.structure:6} {v.entry_time:5} {v.short_offset:<3} {v.wing_width:<2} "
                  f"{v.pt_frac:<4} {sm:5} {v.n:<4} {v.skip_rate*100:<6.1f} {v.wr:<5} "
                  f"{v.expectancy:<7} {v.expectancy_oos:<7} {v.posq_oos:<4} "
                  f"{v.max_single_day_loss:<8} {v.book_max_dd:<8} "
                  f"{str(v.tail_survivable):5} {str(v.gate_pass):5}")
        return

    ap.print_help()


if __name__ == "__main__":
    main()

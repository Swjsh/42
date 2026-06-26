"""NEW-HUNT: IBS (Internal Bar Strength) mean-reversion — 0DTE SPY directional.

STRATEGY (NOT in our fleet). Hypothesis: Internal Bar Strength
    IBS = (close - low) / (high - low)         [range 0..1]
is a famous *daily* mean-reversion edge in equity ETFs (SPY/QQQ). Close near the
bar LOW (IBS<=~0.2) => short-term oversold => fade UP (buy CALL). Close near the
bar HIGH (IBS>=~0.8) => overbought => fade DOWN (buy PUT). Here we test the
INTRADAY / last-closed-bar variant on SPY 5-minute bars, mapped to a 0DTE
single-leg directional option.

────────────────────────────────────────────────────────────────────────────
STEP 1 — SOURCED RULES (cited; rules are NOT invented):
  Formula  : IBS = (close - low) / (high - low)            [Robust Trader, Kinlay, Alvarez]
  LONG     : IBS < 0.2  -> buy on the close (oversold)     [Robust Trader, Kinlay]
  SHORT/exit: IBS > 0.8 (overbought)                       [Robust Trader, Kinlay]
  Timing   : execute at/near the CLOSE (next-open degrades 0.41%->0.31%) [Robust Trader]
  Daily edge (Pagonidis 2013, SPY since early-90s):
      avg fwd return  IBS<0.20 = +0.35% ;  IBS>0.80 = -0.13%   [Kinlay / Pagonidis]
  Published SPY daily backtest 2000-2020: +0.41%/trade, WR 69.7%, PF 1.92, N~600 [Robust Trader]
  Origin   : CSS Analytics (Mike Stokes); documented by A. Pagonidis,
             "The IBS Effect: Mean Reversion in Equity ETFs" (2013).      [Kinlay]
  Sources:
    https://therobusttrader.com/internal-bar-strength-ibs/
    https://jonathankinlay.com/2019/07/the-internal-bar-strength-indicator/
    https://alvarezquanttrading.com/blog/internal-bar-strength-for-mean-reversion/
    https://www.quantifiedstrategies.com/ibs-internal-bar-strength-indicator-strategies/

  ADAPTATION NOTE (honest): the published edge is a DAILY, hold-to-next-close,
  SPY-SPOT %-return edge. We are testing (a) the INTRADAY 5-min last-bar variant
  and (b) a 0DTE single-leg OPTION expression that is FLAT by EOD. SPY-direction
  edge != option edge (CLAUDE.md C3 / L58). The real-fills backtest below is the
  only authority on whether any of the spot edge survives the option transform.

STEP 2/3 — causal signals on 16mo SPY 5m + REAL-FILLS OPRA sim (lib.simulator_real).
  Entry mechanics handled by simulator_real (fills NEXT bar open after the closed
  trigger bar -> no look-ahead). rejection_level = the strategy's invalidation:
    CALL (oversold)  -> support below = the trigger bar's LOW   (close below = wrong)
    PUT  (overbought)-> resistance above = the trigger bar's HIGH (close above = wrong)

STEP 4 — deterministic self-verify (in-script, no agents):
  REAL CANDIDATE only if: OOS(2026) per-trade>0 AND positive_quarters>=4/6 AND
  top5_day_pct<200% AND n>=20 AND drop-top-5-days per-trade still >0.

OP-20 disclosure: per-trade EXPECTANCY (not WR), IS/OOS, positive_quarters,
top5 + drop-top5. No cherry-picking: if the only positive cell is thin-N /
high-concentration / OOS-negative, clears_bar=false.

Pure Python, $0 in the sim loop. Writes analysis/recommendations/newhunt-ibs-mean-reversion.json
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.truncation_guard import cross_check_grid  # noqa: E402  shared graduated guard (L171)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "newhunt-ibs-mean-reversion.json"

# ── Strategy params (sourced) ─────────────────────────────────────────────────
IBS_LONG_MAX = 0.20      # IBS < 0.20 -> oversold -> CALL          [sourced]
IBS_SHORT_MIN = 0.80     # IBS > 0.80 -> overbought -> PUT         [sourced]
RTH_START = dt.time(9, 35)
RTH_END = dt.time(15, 55)   # entry must precede 15:50 time stop
COOLDOWN_MIN = 30           # anti-churn (task allows 30-45)
QTY = 3
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# Small grid (per task)
STRIKE_OFFSETS = [-2, -1, 0, 1, 2]
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


class _Acc:
    """Per-trade accumulator with by-day P&L (for top5 + drop-top5 concentration)."""
    __slots__ = ("n", "wins", "pnl", "by_day")

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.pnl = 0.0
        self.by_day: dict[str, float] = defaultdict(float)

    def add(self, pnl: float, day: str):
        self.n += 1
        self.wins += 1 if pnl > 0 else 0
        self.pnl += pnl
        self.by_day[day] += pnl

    def report(self) -> dict:
        if not self.n:
            return {"n": 0}
        days_sorted = sorted(self.by_day.values(), reverse=True)
        top5 = sum(days_sorted[:5])
        return {
            "n": self.n,
            "wr": round(100 * self.wins / self.n, 1),
            "total_pnl": round(self.pnl, 0),
            "avg_pnl": round(self.pnl / self.n, 1),  # per-trade EXPECTANCY (OP-14)
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


def build_signals(rth: pd.DataFrame) -> list[dict]:
    """Causal IBS signals on closed 5m bars. Signal on bar i; simulator fills i+1 open."""
    signals: list[dict] = []
    last_sig: dt.datetime | None = None
    n = len(rth)
    highs = rth["high"].to_numpy()
    lows = rth["low"].to_numpy()
    closes = rth["close"].to_numpy()
    times = rth["timestamp_et"]

    for i in range(n):
        ts = times.iloc[i]
        if hasattr(ts, "tz") and ts.tz is not None:
            ts = ts.tz_localize(None)
        ts = pd.Timestamp(ts).to_pydatetime()

        t = ts.time()
        if t < RTH_START or t > RTH_END:
            continue

        rng = highs[i] - lows[i]
        if rng <= 0:
            continue  # degenerate bar (no internal strength defined)

        ibs = (closes[i] - lows[i]) / rng

        if ibs < IBS_LONG_MAX:
            side, direction = "C", "long"
            rejection_level = float(lows[i])      # support below; close below = thesis dead
        elif ibs > IBS_SHORT_MIN:
            side, direction = "P", "short"
            rejection_level = float(highs[i])     # resistance above; close above = thesis dead
        else:
            continue

        if last_sig is not None and (ts - last_sig).total_seconds() / 60.0 < COOLDOWN_MIN:
            continue
        last_sig = ts

        signals.append({
            "idx": i,
            "date": ts.date(),
            "time": ts.strftime("%H:%M"),
            "side": side,
            "direction": direction,
            "ibs": round(float(ibs), 3),
            "rejection_level": round(rejection_level, 2),
        })
    return signals


def run_cell(rth: pd.DataFrame, signals: list[dict], strike_offset: int,
             premium_stop_pct: float) -> tuple[_Acc, dict, list, dict]:
    """Run one (strike_offset, premium_stop) grid cell over all signals."""
    overall = _Acc()
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    by_side = {"C": _Acc(), "P": _Acc()}
    no_data = 0
    rows: list[dict] = []

    for s in signals:
        fill = simulate_trade_real(
            entry_bar_idx=s["idx"],
            entry_bar=rth.iloc[s["idx"]],
            spy_df=rth,
            ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["ibs_mean_reversion", s["direction"], f"ibs_{s['ibs']}"],
            side=s["side"],
            qty=QTY,
            setup="IBS_MEAN_REVERSION",
            premium_stop_pct=premium_stop_pct,
            strike_offset=strike_offset,
        )
        if fill is None:
            no_data += 1
            continue
        pnl = float(fill.dollar_pnl)
        day = s["date"].isoformat()
        overall.add(pnl, day)
        by_sample["IS_2025" if s["date"].year == 2025 else "OOS_2026"].add(pnl, day)
        by_q[_quarter(s["date"])].add(pnl, day)
        by_side[s["side"]].add(pnl, day)
        rows.append({
            "date": day, "time": s["time"], "side": s["side"], "ibs": s["ibs"],
            "rejection_level": s["rejection_level"], "strike": fill.strike,
            "entry_premium": round(fill.entry_premium, 3), "pnl": round(pnl, 2),
            "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason),
        })

    q_reports = {k: by_q[k].report() for k in sorted(by_q)}
    pos_q = sum(1 for r in q_reports.values() if r.get("total_pnl", 0) and r["total_pnl"] > 0)
    extras = {
        "no_data": no_data,
        "by_sample": {k: v.report() for k, v in by_sample.items()},
        "by_side": {k: v.report() for k, v in by_side.items()},
        "by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{len(q_reports)}",
        "pos_q_n": pos_q,
        "n_quarters": len(q_reports),
        "oos_acc": by_sample["OOS_2026"],
    }
    return overall, extras, rows, q_reports


def main() -> dict:
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, _vix = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
                   & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    log.info("RTH bars: %d", len(rth))

    signals = build_signals(rth)
    n_long = sum(1 for s in signals if s["side"] == "C")
    n_short = sum(1 for s in signals if s["side"] == "P")
    log.info("IBS signals: %d (long/CALL=%d, short/PUT=%d)", len(signals), n_long, n_short)

    # ── Sweep the small grid ──────────────────────────────────────────────────
    grid_results: list[dict] = []
    best = None  # (overall_avg, cell_dict, overall_acc, extras, rows)
    for so in STRIKE_OFFSETS:
        for ps in PREMIUM_STOPS:
            overall, extras, rows, q_reports = run_cell(rth, signals, so, ps)
            rep = overall.report()
            cell = {
                "strike_offset": so,
                "premium_stop_pct": ps,
                "overall": rep,
                "by_sample": extras["by_sample"],
                "by_side": extras["by_side"],
                "positive_quarters": extras["positive_quarters"],
                "by_quarter": q_reports,
                "no_data": extras["no_data"],
            }
            grid_results.append(cell)
            log.info("cell so=%+d ps=%.2f -> n=%s avg=$%s total=$%s posQ=%s OOS=%s",
                     so, ps, rep.get("n"), rep.get("avg_pnl"), rep.get("total_pnl"),
                     extras["positive_quarters"], extras["by_sample"]["OOS_2026"].get("avg_pnl"))
            # Rank cells by OVERALL per-trade expectancy (only among n>=20).
            score = rep.get("avg_pnl", -1e9) if rep.get("n", 0) >= 20 else -1e9
            if best is None or score > best[0]:
                best = (score, cell, overall, extras, rows)

    # ── STEP 4: deterministic self-verify on the best cell ────────────────────
    _, best_cell, best_overall, best_extras, best_rows = best
    oos_acc: _Acc = best_extras["oos_acc"]
    overall_rep = best_overall.report()

    # drop-top-5-days per-trade (whole-day removal) — need per-day trade counts.
    day_pnl = dict(best_overall.by_day)
    day_n: dict[str, int] = defaultdict(int)
    for r in best_rows:
        day_n[r["date"]] += 1
    top5_days = [d for d, _ in sorted(day_pnl.items(), key=lambda kv: kv[1], reverse=True)[:5]]
    rem_pnl = sum(p for d, p in day_pnl.items() if d not in top5_days)
    rem_n = sum(c for d, c in day_n.items() if d not in top5_days)
    drop_top5_avg = round(rem_pnl / rem_n, 2) if rem_n > 0 else None

    top5_day_sum = sum(day_pnl[d] for d in top5_days)
    top5_day_pct = round(100 * top5_day_sum / best_overall.pnl, 0) if best_overall.pnl > 0 else None

    oos_rep = oos_acc.report()
    oos_per_trade = oos_rep.get("avg_pnl") if oos_rep.get("n") else None
    n_trades = overall_rep.get("n", 0)
    pos_q = best_extras["pos_q_n"]
    n_q = best_extras["n_quarters"]

    # ── TRUNCATION-ARTIFACT DIAGNOSTIC (C2 / L51 / L55 / L171 anti-pattern) ────
    # A tight premium stop (-8%) can manufacture a fake "edge" by mechanically
    # cutting every loser at -8% while a few fast winners run — NOT by signal
    # quality. The tell: the edge exists ONLY at the tight stop and the SAME
    # signal at the loosest (chart-stop-only) stop is deeply negative. The shared
    # graduated guard looks up the SAME strike_offset at premium_stop=-0.99 to
    # expose this (lib.truncation_guard, the generalization of this reference impl).
    _trunc = cross_check_grid(grid_results, best_cell)
    loose_avg = _trunc.chart_stop_only_per_trade
    is_truncation_artifact = _trunc.is_artifact

    # CANDIDATE gate (all must hold). The 6th gate (no_truncation_artifact) is the
    # honest guard that the task warned about (anti-pattern 2.10 / C2): a positive
    # cell that exists ONLY because a tight stop truncates losers is NOT an edge.
    crit_oos = oos_per_trade is not None and oos_per_trade > 0
    crit_posq = pos_q >= 4  # of 6 quarters
    crit_top5 = top5_day_pct is not None and top5_day_pct < 200
    crit_n = n_trades >= 20
    crit_drop = drop_top5_avg is not None and drop_top5_avg > 0
    crit_not_artifact = not is_truncation_artifact
    clears_bar = bool(crit_oos and crit_posq and crit_top5 and crit_n and crit_drop
                      and crit_not_artifact)

    verdict_bits = []
    verdict_bits.append(f"OOS/trade={oos_per_trade} ({'PASS' if crit_oos else 'FAIL'} >0)")
    verdict_bits.append(f"posQ={pos_q}/{n_q} ({'PASS' if crit_posq else 'FAIL'} >=4)")
    verdict_bits.append(f"top5_day%={top5_day_pct} ({'PASS' if crit_top5 else 'FAIL'} <200)")
    verdict_bits.append(f"n={n_trades} ({'PASS' if crit_n else 'FAIL'} >=20)")
    verdict_bits.append(f"drop-top5/trade={drop_top5_avg} ({'PASS' if crit_drop else 'FAIL'} >0)")
    verdict_bits.append(
        f"chart-stop-only(same strike)/trade=${loose_avg} "
        f"({'PASS not-truncation' if crit_not_artifact else 'FAIL truncation-artifact'})")

    if clears_bar:
        verdict = "REAL CANDIDATE — clears all 6 gates on real OPRA fills."
    elif is_truncation_artifact:
        verdict = (
            f"NOT A CANDIDATE — TRUNCATION ARTIFACT (anti-pattern 2.10 / C2). The only "
            f"positive cells in the whole grid sit at the -8% premium stop, where WR "
            f"COLLAPSES to ~{overall_rep.get('wr')}% (the IBS thesis is a ~70%-WR edge). "
            f"The SAME IBS signal at chart-stop-only (-99%) on the same strike is "
            f"${loose_avg}/trade — deeply NEGATIVE. The +$ comes from mechanically cutting "
            f"every loser at -8% while a few fast winners run, NOT from IBS signal quality. "
            f"Intraday IBS -> 0DTE option edge does NOT survive the real-fills transform "
            f"(published edge is DAILY SPY-SPOT; SPY-direction != option edge, C3/L58). "
            f"Also a firehose: {len(signals)} signals/16mo (~{len(signals)//252}/day) is noise, "
            f"not a selective setup.")
    else:
        verdict = ("NOT A CANDIDATE — " + "; ".join(b for b in verdict_bits if "FAIL" in b)
                   + ". IBS intraday->0DTE-option edge does NOT survive the real-fills "
                     "transform (the published edge is a DAILY SPY-spot edge; SPY-direction "
                     "!= option edge, C3/L58).")

    best_config = (f"strike_offset={best_cell['strike_offset']}, "
                   f"premium_stop_pct={best_cell['premium_stop_pct']}")

    summary = {
        "run_date": dt.date.today().isoformat(),
        "strategy": "ibs_mean_reversion",
        "hypothesis": ("Internal Bar Strength IBS=(close-low)/(high-low); IBS<0.2 -> CALL "
                       "(oversold), IBS>0.8 -> PUT (overbought). Intraday 5m last-bar variant "
                       "on SPY mapped to 0DTE single-leg directional."),
        "sourced_rules": ("IBS=(close-low)/(high-low); LONG IBS<0.20, SHORT IBS>0.80; "
                          "buy on the close; published DAILY SPY edge +0.41%/trade WR 69.7% "
                          "(2000-2020); Pagonidis: IBS<0.20 +0.35% / IBS>0.80 -0.13% fwd."),
        "sources": [
            "https://therobusttrader.com/internal-bar-strength-ibs/",
            "https://jonathankinlay.com/2019/07/the-internal-bar-strength-indicator/",
            "https://alvarezquanttrading.com/blog/internal-bar-strength-for-mean-reversion/",
            "https://www.quantifiedstrategies.com/ibs-internal-bar-strength-indicator-strategies/",
        ],
        "window": f"{START}..{END}",
        "params": {
            "ibs_long_max": IBS_LONG_MAX, "ibs_short_min": IBS_SHORT_MIN,
            "rth": f"{RTH_START}-{RTH_END}", "cooldown_min": COOLDOWN_MIN, "qty": QTY,
            "grid_strike_offsets": STRIKE_OFFSETS, "grid_premium_stops": PREMIUM_STOPS,
        },
        "n_signals": len(signals),
        "n_signals_long_call": n_long,
        "n_signals_short_put": n_short,
        "best_config": best_config,
        "best_cell_overall": overall_rep,
        "best_cell_by_sample": best_cell["by_sample"],
        "best_cell_by_side": best_cell["by_side"],
        "best_cell_by_quarter": best_cell["by_quarter"],
        "self_verify": {
            "overall_per_trade": overall_rep.get("avg_pnl"),
            "oos_per_trade": oos_per_trade,
            "positive_quarters": best_extras["positive_quarters"],
            "top5_day_pct": top5_day_pct,
            "drop_top5_per_trade": drop_top5_avg,
            "n_trades": n_trades,
            "best_cell_wr_pct": overall_rep.get("wr"),
            "same_strike_chart_stop_only_per_trade": loose_avg,
            "is_truncation_artifact": is_truncation_artifact,
            "criteria": {
                "oos_per_trade_gt0": crit_oos,
                "positive_quarters_ge4": crit_posq,
                "top5_day_lt200": crit_top5,
                "n_ge20": crit_n,
                "drop_top5_gt0": crit_drop,
                "no_truncation_artifact": crit_not_artifact,
            },
            "criteria_detail": verdict_bits,
        },
        "clears_bar": clears_bar,
        "verdict": verdict,
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) — the only WR/expectancy authority",
            "spy_vs_option": "published edge is DAILY SPY-SPOT %; this tests intraday->0DTE option. "
                             "SPY-direction != option edge (C3/L58).",
            "per_trade": "avg_pnl = per-trade expectancy reported, not WR alone (OP-14)",
            "concentration": "top5_day_pct + drop-top-5-days per-trade shown (OP-20 #5, anti-pattern 2.10)",
            "no_cherry_pick": "best cell ranked by OVERALL expectancy among n>=20; if it fails any "
                              "gate, clears_bar=false (no thin-N / high-concentration rescue).",
            "grid": f"{len(grid_results)} cells = {len(STRIKE_OFFSETS)} strike_offset x "
                    f"{len(PREMIUM_STOPS)} premium_stop; v15 default exits.",
        },
        "grid": grid_results,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    print("\n=== IBS MEAN-REVERSION — REAL-FILLS VERDICT ===")
    print(f"signals={len(signals)} (CALL={n_long} PUT={n_short})")
    print(f"BEST CELL: {best_config}")
    print(f"  overall : {overall_rep}")
    print(f"  IS 2025 : {best_cell['by_sample']['IS_2025']}")
    print(f"  OOS 2026: {best_cell['by_sample']['OOS_2026']}")
    print(f"  by_side : C={best_cell['by_side']['C']}  P={best_cell['by_side']['P']}")
    print(f"  posQ={best_extras['positive_quarters']}  top5_day%={top5_day_pct}  "
          f"drop-top5/trade=${drop_top5_avg}")
    print(f"SELF-VERIFY: {' | '.join(verdict_bits)}")
    print(f"CLEARS BAR: {clears_bar}")
    print(f"VERDICT: {verdict}")
    return summary


if __name__ == "__main__":
    main()

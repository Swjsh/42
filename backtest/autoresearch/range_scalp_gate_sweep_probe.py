"""RANGE-SCALP slice 3 (part 2): the gate-leg-loosening recovery sweep.

The decisive bounded question (conductor 2026-06-28, the explicitly-named next
slice of RANGE-SCALP-REGIME-GATE-SLICE after slice 2 returned REGIME_GATE_TOO_TIGHT):

    Slice 2 proved the flat-ribbon(<30c) AND VIX[14,20] gate is the RIGHT mechanism
    -- it fully killed the 2 biggest loser days (06-04 -$157.2, 06-24 -$264.6) -- but
    the strict AND is too RARE (n=8 < 10 = statistically inconclusive) and the gated
    net is one-winner-day-dominated (05-29 = $354 of $355).

    If we LOOSEN ONE gate leg (spread up to 40/50c, OR VIX band out to [13,22]/[12,24]),
    does the trade count RECOVER toward n>=10 (enough to conclude) WHILE the loser-kill
    on the two biggest loser days (06-04, 06-24) STILL HOLDS and expectancy stays
    positive AND survives slippage?

If a loosened variant reaches n>=10 AND keeps both big losers killed AND stays
positive net-of-slippage -> that variant is the real edge boundary; promote it to the
tp/stop/strike sweep + IS/OOS slice (slice 4).
If every variant that recovers count RE-ADMITS a big loser day (count recovers only by
letting the trending-bar losers back in) -> the gate is genuinely a knife-edge; the
Tier-2 level-fade edge is too rare on this regime window and the lever is to WIDEN the
data window (slice 3 part 1, currently data-blocked: VIX csv + OPRA cache both fixed
to 2026-05-19..06-26) before any further gate tuning.

REUSE not rebuild (L17/L36): one OPRA pass via run_shotgun_day(tier_filter=2), then
re-filter the SAME per-trade rows for every gate variant -- no re-simulation per
variant. The slice-2 gated probe stays byte-identical (this imports its causal
spread/VIX helpers, mutates nothing).

COMPOUND not accumulate (self-audit gap 2026-06-28T17:30:40 #1+#2, the named
instruction): significance (n<10), concentration (top-3-day %), the per-trade summary
and the verdict ladder all come from the CANONICAL `probe_stats` helper -- this probe
does NOT re-derive any of them, so the n<10 / top3>150% policy can never silently
diverge here.

Yardstick = per-trade expectancy + concentration-robust day metrics (NOT J
edge_capture -- that directional-anchor metric structurally auto-rejects range
strategies; _lesson-inbox/2026-06-28-directional-anchor-edgecapture...).

Rail-4 CLEAR: a research probe + results JSON. Touches NO params/doctrine/orders/
heartbeat/filters/CLAUDE; places NO order; arms NOTHING.

Run:
    backtest/.venv/Scripts/python.exe -m autoresearch.range_scalp_gate_sweep_probe --smoke
    backtest/.venv/Scripts/python.exe -m autoresearch.range_scalp_gate_sweep_probe
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from autoresearch.shotgun_scalper_grinder import run_shotgun_day
from autoresearch.range_scalp_probe import (
    RANGE_SCALP_COMBO,
    TIER_LEVEL_REJECT,
    WINDOW_START,
    WINDOW_END,
    _load_spy,
    _trading_days,
)
# Reuse slice-2's CAUSAL gate helpers (no look-ahead, L40/L44/C6) verbatim -- the
# slice-2 probe stays byte-identical; we only consume its functions.
from autoresearch.range_scalp_regime_gated_probe import (
    _load_vix,
    _vix_asof,
    _ribbon_spread_at,
)
# COMPOUND: the single canonical source for significance + concentration + verdict.
from autoresearch.probe_stats import (
    summarize_trades,
    day_concentration,
    significance,
    concentration_flag,
    base_verdict,
)

# --- the gate-leg loosening grid ----------------------------------------------
# Each leg is loosened INDEPENDENTLY and jointly so we can attribute a recovery to a
# specific leg. spread<30 == slice-2 baseline (engine's RIBBON_SPREAD_MIN_CENTS trend
# threshold); VIX[14,20] == slice-2 baseline (compressed-vol range).
SPREAD_MAX_GRID = (30.0, 40.0, 50.0)
VIX_BAND_GRID = ((14.0, 20.0), (13.0, 22.0), (12.0, 24.0))

# The two BIGGEST loser days the gate exists to kill. Slice 2 found 05-26 retains one
# genuine flat-ribbon trade, so the loser-kill invariant we hold is on these two.
BIG_LOSER_DAYS = ("2026-06-04", "2026-06-24")
ALL_LOSER_DAYS = ("2026-05-26", "2026-06-04", "2026-06-24")

# Harsh-end slippage (half-spread $/contract, charged on entry+exit) -- a $/trade edge
# that dies under realistic slippage is not deployable.
SLIPPAGE_HALF_SPREAD = 0.05

OUT_PATH = _REPO / "analysis" / "recommendations" / "range-scalp-gate-sweep-2026-06-28.json"


def _build_rows(start: dt.date, end: dt.date) -> tuple[list[dict], list[str]]:
    """ONE OPRA pass: every Tier-2 trade with its causal spread + as-of VIX attached."""
    spy = _load_spy(start - dt.timedelta(days=5), end)
    vix = _load_vix()
    days = _trading_days(spy, start, end)
    day_keys = [d.isoformat() for d in days]
    opra_cache: dict = {}
    rows: list[dict] = []
    for d in days:
        for t in run_shotgun_day(d, spy, RANGE_SCALP_COMBO, opra_cache, tier_filter=TIER_LEVEL_REJECT):
            spread = _ribbon_spread_at(spy, t.entry_time_et)
            vixv = _vix_asof(vix, t.entry_time_et)
            rows.append({
                "date": d.isoformat(),
                "entry_time_et": t.entry_time_et.isoformat(),
                "dollar_pnl": t.dollar_pnl,
                "qty": t.qty,
                "spread_cents": round(spread, 1) if spread is not None else None,
                "vix": round(vixv, 2) if vixv is not None else None,
            })
    return rows, day_keys


def _by_day(rows: list[dict], day_keys: list[str]) -> dict[str, float]:
    bd = {k: 0.0 for k in day_keys}
    for r in rows:
        bd[r["date"]] = round(bd[r["date"]] + r["dollar_pnl"], 2)
    return bd


def _kept(rows: list[dict], spread_max: float, vix_low: float, vix_high: float) -> list[dict]:
    out = []
    for r in rows:
        sp, vx = r["spread_cents"], r["vix"]
        if sp is None or vx is None:
            continue
        if sp < spread_max and vix_low <= vx <= vix_high:
            out.append(r)
    return out


def _evaluate_variant(rows: list[dict], day_keys: list[str],
                      spread_max: float, vix_low: float, vix_high: float) -> dict:
    kept = _kept(rows, spread_max, vix_low, vix_high)
    pnls = [r["dollar_pnl"] for r in kept]
    summ = summarize_trades(pnls)                                   # COMPOUND
    conc = day_concentration(_by_day(kept, day_keys))               # COMPOUND
    sig = significance(summ["n_trades"])                            # COMPOUND (gap #1)
    cflag = concentration_flag(conc["top3_day_pct_of_net"])         # COMPOUND (gap #2)

    # slippage net@0.05 on the kept set
    net = [round(r["dollar_pnl"] - 2.0 * SLIPPAGE_HALF_SPREAD * 100.0 * r["qty"], 2) for r in kept]
    net_summ = summarize_trades(net)

    # loser-day audit: did each big loser day stay killed?
    loser_audit = {}
    for ld in ALL_LOSER_DAYS:
        after = [r for r in kept if r["date"] == ld]
        loser_audit[ld] = {
            "trades_kept": len(after),
            "pnl_kept": round(sum(r["dollar_pnl"] for r in after), 2),
            "killed": len(after) == 0,
        }
    big_losers_killed = all(loser_audit[ld]["killed"] for ld in BIG_LOSER_DAYS)

    verdict = base_verdict(                                          # COMPOUND ladder
        summ["n_trades"], summ["expectancy_per_trade_usd"], conc["top3_day_pct_of_net"],
    )
    # the slice-3 recovery question, layered on the canonical ladder:
    #   RECOVERED == n>=10 (significant) AND big losers still killed AND positive net@0.05
    recovered = (
        sig["sufficient"]
        and big_losers_killed
        and net_summ["expectancy_per_trade_usd"] > 0
    )
    return {
        "gate": {"spread_max_cents": spread_max, "vix_low": vix_low, "vix_high": vix_high},
        "is_slice2_baseline": (spread_max == 30.0 and vix_low == 14.0 and vix_high == 20.0),
        "summary_gross": summ,
        "summary_net_0.05": net_summ,
        "concentration": conc,
        "significance": sig,
        "concentration_flag": cflag,
        "base_verdict": verdict,
        "big_losers_killed": big_losers_killed,
        "loser_day_audit": loser_audit,
        "recovered": recovered,
    }


def run_sweep(start: dt.date, end: dt.date) -> dict:
    rows, day_keys = _build_rows(start, end)
    variants = []
    for sp in SPREAD_MAX_GRID:
        for (vlo, vhi) in VIX_BAND_GRID:
            variants.append(_evaluate_variant(rows, day_keys, sp, vlo, vhi))

    baseline = next(v for v in variants if v["is_slice2_baseline"])
    recovered = [v for v in variants if v["recovered"]]
    # the "best recoverable" = among recovered, the one with highest net@0.05 expectancy,
    # tie-broken toward lower concentration (more spread-out days = more robust).
    best = None
    if recovered:
        best = sorted(
            recovered,
            key=lambda v: (
                v["summary_net_0.05"]["expectancy_per_trade_usd"],
                -(v["concentration"]["top3_day_pct_of_net"] or 9999),
            ),
            reverse=True,
        )[0]

    if best is not None:
        verdict = "GATE_LEG_RECOVERS"          # a loosened variant reaches n>=10 + holds the kill + survives slippage
    elif any(v["significance"]["sufficient"] and not v["big_losers_killed"] for v in variants):
        verdict = "RECOVERS_ONLY_BY_READMITTING_LOSERS"   # count recovers only by letting the big losers back in
    else:
        verdict = "GATE_KNIFE_EDGE_WIDEN_DATA"  # nothing reaches n>=10 cleanly -> the lever is more data, not more tuning

    return {
        "probe": "range_scalp_tier2_gate_leg_sweep",
        "slice": "RANGE-SCALP-REGIME-GATE-SLICE slice 3 part 2 (loosen one gate leg, count recovery)",
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "verdict": verdict,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "grid": {"spread_max_cents": list(SPREAD_MAX_GRID),
                 "vix_bands": [list(b) for b in VIX_BAND_GRID],
                 "slippage_half_spread": SLIPPAGE_HALF_SPREAD},
        "slice2_baseline": baseline,
        "best_recoverable": best,
        "variants": variants,
        "method_disclosures": {
            "reuse": "ONE OPRA pass via run_shotgun_day(tier_filter=2); the SAME per-trade "
                     "rows are re-filtered for every gate variant (no re-simulation). "
                     "slice-2 gated probe imported, untouched (byte-identical).",
            "compound": "significance / concentration / per-trade summary / verdict ladder "
                        "all from probe_stats (single canonical source; n<10 + top3>150% "
                        "policy cannot diverge here). self-audit gap 2026-06-28 #1+#2.",
            "causality": "ribbon spread = EMA value at entry bar over bars<=entry; VIX = "
                         "as-of last bar<=entry (slice-2 helpers). No look-ahead.",
            "fill_model": "Real OPRA bars via _simulate_trade_real (NO Black-Scholes).",
            "recovery_def": "RECOVERED == n>=10 (probe_stats.significance) AND both big loser "
                            "days (06-04, 06-24) still fully killed AND positive expectancy "
                            f"net of {SLIPPAGE_HALF_SPREAD} half-spread slippage.",
            "yardstick": "per-trade expectancy + concentration-robust day metrics. J "
                         "edge_capture NOT used (auto-rejects range edges).",
            "limitations": "ONE combo (RANGE_SCALP_COMBO), ONE strike/tp/stop config, no "
                           "IS/OOS. A GATE_LEG_RECOVERS verdict justifies the tp/stop/strike "
                           "sweep + IS/OOS slice; the other two verdicts point at data-widening.",
        },
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true", help="build rows only, print the baseline + counts")
    args = ap.parse_args()

    if args.smoke:
        rows, day_keys = _build_rows(WINDOW_START, WINDOW_END)
        print(f"SMOKE: {len(rows)} Tier-2 trades over {len(day_keys)} days")
        base = _evaluate_variant(rows, day_keys, 30.0, 14.0, 20.0)
        print(f"  baseline(30c/14-20): n={base['summary_gross']['n_trades']} "
              f"exp=${base['summary_gross']['expectancy_per_trade_usd']} "
              f"top3%={base['concentration']['top3_day_pct_of_net']} "
              f"big_losers_killed={base['big_losers_killed']} verdict={base['base_verdict']}")
        loose = _evaluate_variant(rows, day_keys, 50.0, 12.0, 24.0)
        print(f"  loosest(50c/12-24): n={loose['summary_gross']['n_trades']} "
              f"exp=${loose['summary_gross']['expectancy_per_trade_usd']} "
              f"big_losers_killed={loose['big_losers_killed']}")
        return 0

    result = run_sweep(WINDOW_START, WINDOW_END)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(f"VERDICT={result['verdict']}")
    b = result["slice2_baseline"]
    print(f"  slice2 baseline(30c/14-20): n={b['summary_gross']['n_trades']} "
          f"exp=${b['summary_gross']['expectancy_per_trade_usd']} "
          f"big_losers_killed={b['big_losers_killed']} sig={b['significance']['sufficient']}")
    if result["best_recoverable"]:
        r = result["best_recoverable"]
        print(f"  BEST RECOVERABLE: spread<{r['gate']['spread_max_cents']}c "
              f"VIX[{r['gate']['vix_low']},{r['gate']['vix_high']}] "
              f"n={r['summary_gross']['n_trades']} exp=${r['summary_gross']['expectancy_per_trade_usd']} "
              f"net@0.05=${r['summary_net_0.05']['expectancy_per_trade_usd']} "
              f"top3%={r['concentration']['top3_day_pct_of_net']}")
    else:
        print("  no variant recovered n>=10 while holding the big-loser kill")
    print(f"written: {OUT_PATH.relative_to(_REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

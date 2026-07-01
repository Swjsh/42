"""BULL-UNBLOCK-STRUCTURAL-PROBE — re-audit `filter_10_min_triggers_bull` on the FRESH OPRA window.

Context (queue BULL-UNBLOCK-REPLAY-PROBE, the #1 project thread — SLICE 2):
  The rig has never filled an ENTER_BULL in 2544 lifetime decisions. SLICE 1
  (bull_unblock_replay_probe.py, commit 79f842c) retired the `block_elite_bull`
  lever: its removed cohort was net -$241 / WR 14.3% / DRY_AT_ZERO on the fresh
  window -> BLOCK_CORRECTLY_REMOVES_LOSERS_KEEP (no params change).

  The remaining bull-unblock lever is STRUCTURAL: `filter_10_min_triggers_bull=2`.
  Filter 11 requires TWO triggers for a bull entry; a smooth uptrend rarely
  produces a single-bar straddle reclaim AND a 2nd confirming trigger, so the
  bull path is starved before block_elite_bull even sees it. This probe isolates
  exactly the bull cohort filter 11 removes at the 2-trigger threshold.

Method (the correct A/B — min_triggers_bull is a real config knob, not post-hoc):
  Run the REAL engine twice over the fresh window with use_real_fills=True,
  holding block_elite_bull=True (production) FIXED so this isolates ONLY the
  structural lever (not a re-test of the already-retired elite block):
    BASE    = production bull config (min_triggers_bull=2)
    UNBLOCK = identical but min_triggers_bull=1
  The ADDED bull cohort (trades present in UNBLOCK but not BASE) is exactly what
  filter 11 removes at the 2-trigger threshold. Score that cohort on real fills:
    - net positive + survives slippage  -> relaxing the trigger ADDS edge -> propose to J (rail-4)
    - net negative                       -> the 2-trigger requirement correctly
                                            starves losers on the fresh window ->
                                            honest null, bull stays structurally gated

  If BOTH bull-unblock levers (elite + structural) come back net-negative, the
  honest project-level finding is the 0DTE-SPY bull lens is structurally +
  edge-gated on this regime -> re-point standing direction fully at the GEX class rung.

Read-only on production state. No Alpaca calls. No params edits. $0 (cached fills).
Rail-4 CLEAR: research tool + JSON result; touches NO params/orders/filters/heartbeat/CLAUDE.
"""
import sys, os, json, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
from lib.orchestrator import run_backtest
from autoresearch.probe_stats import (
    significance, day_concentration, concentration_flag, slippage_sweep,
)
# Reuse SLICE-1's verdict ladder + trade-key helpers (compound, don't duplicate).
from autoresearch.bull_unblock_replay_probe import (
    classify_verdict, _key, _date, START, END, ANCHOR_DATES, SPY, VIX,
)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _bull_cfg(min_triggers_bull: int) -> dict:
    """Production Safe bull config (read from live params.json), trigger-count toggled.

    block_elite_bull is held at its PRODUCTION value (True) so this isolates ONLY
    the structural `min_triggers_bull` lever — SLICE 1 already audited the elite block.
    """
    p = json.load(open(os.path.join(REPO, "automation", "state", "params.json")))
    return dict(
        use_real_fills=True,
        no_trade_before=dt.time(9, 35),
        enable_bullish=True,
        block_elite_bull=True,  # production FIXED — isolates the structural lever
        block_elite_bull_vix_low=float(p.get("block_elite_bull_vix_low", 0.0)),
        block_elite_bull_vix_high=float(p.get("block_elite_bull_vix_high", 25.0)),
        block_bull_1100_1200=bool(p.get("block_bull_1100_1200", True)),
        block_level_rejection=bool(p.get("block_level_rejection", True)),
        min_triggers_bull=min_triggers_bull,   # THE lever under test
        strike_offset=-2,            # Safe OTM-2 tier (held constant across A/B)
        per_trade_risk_cap_pct=0.30,
        initial_equity=1763.0,
    )


def main():
    spy = pd.read_csv(os.path.join(REPO, "backtest", SPY))
    vix = pd.read_csv(os.path.join(REPO, "backtest", VIX))

    print("=" * 72)
    print("BULL-UNBLOCK-STRUCTURAL-PROBE — re-audit min_triggers_bull on fresh OPRA")
    print(f"window {START}..{END}  (use_real_fills=True, block_elite_bull=True FIXED)")
    print("=" * 72)

    r_base = run_backtest(spy, vix, start_date=START, end_date=END, **_bull_cfg(2))
    r_unbl = run_backtest(spy, vix, start_date=START, end_date=END, **_bull_cfg(1))

    base_keys = {_key(t) for t in r_base.trades}
    added = [t for t in r_unbl.trades if _key(t) not in base_keys]
    added_bulls = [t for t in added if t.side == "C"]

    base_pnl = sum(t.dollar_pnl for t in r_base.trades)
    unbl_pnl = sum(t.dollar_pnl for t in r_unbl.trades)
    added_pnl = sum(t.dollar_pnl for t in added_bulls)
    rows = [{"dollar_pnl": t.dollar_pnl, "qty": getattr(t, "qty", 1) or 1}
            for t in added_bulls]
    pnls = [t.dollar_pnl for t in added_bulls]
    wins = sum(1 for x in pnls if x > 0)

    print(f"\nBASE   (min_triggers_bull=2):  n={len(r_base.trades):3d}  pnl={base_pnl:+.0f}")
    print(f"UNBLOCK(min_triggers_bull=1):  n={len(r_unbl.trades):3d}  pnl={unbl_pnl:+.0f}")
    print(f"\nADDED bull cohort (filter-11 removes at 2-trigger): n={len(added_bulls)}")
    print(f"{'date':12s} {'time':6s} {'strike':>8} {'pnl':>8}  W/L")
    for t in sorted(added_bulls, key=_date):
        ts = pd.Timestamp(t.entry_time_et)
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        wl = "WIN" if t.dollar_pnl > 0 else ("EVEN" if t.dollar_pnl == 0 else "LOSS")
        print(f"  {_date(t)} {ts.strftime('%H:%M')} {float(t.strike):8.0f} {t.dollar_pnl:+8.1f}  {wl}")

    wr = wins / len(added_bulls) if added_bulls else 0.0
    exp = added_pnl / len(added_bulls) if added_bulls else 0.0
    sig = significance(len(added_bulls))
    by_day: dict = {}
    for t in added_bulls:
        by_day[str(_date(t))] = by_day.get(str(_date(t)), 0.0) + t.dollar_pnl
    conc = day_concentration(by_day) if added_bulls else {}
    top3 = conc.get("top3_day_pct_of_net") if conc else None
    cflag = concentration_flag(top3) if added_bulls else {}
    sweep = slippage_sweep(rows) if added_bulls else {}

    anchor_added = [t for t in added_bulls if _date(t) in ANCHOR_DATES]
    anchor_ok = not anchor_added  # no bull anchors exist -> must be empty

    added_net_positive = added_pnl > 0
    survives = isinstance(sweep, dict) and sweep.get("verdict") == "SURVIVES_REALISTIC"
    sufficient = bool(sig.get("sufficient"))
    verdict = classify_verdict(bool(added_bulls), added_net_positive, survives, sufficient)

    print(f"\n--- SCORE (added cohort) ---")
    print(f"  n={len(added_bulls)}  WR={wr:.1%}  exp/tr={exp:+.1f}  net={added_pnl:+.0f}")
    print(f"  significance: sufficient={sufficient} ({sig['note']})")
    print(f"  day_concentration top3={top3}% concentrated={cflag.get('concentrated') if cflag else 'NA'}")
    print(f"  slippage={sweep.get('verdict','NA') if isinstance(sweep,dict) else 'NA'} "
          f"breakeven={sweep.get('breakeven_half_spread') if isinstance(sweep,dict) else 'NA'}")
    print(f"  anchor_no_regression={'PASS' if anchor_ok else 'FAIL'} (no bull anchors exist)")
    print(f"\nVERDICT: {verdict}")

    out = {
        "probe": "bull_unblock_structural_probe",
        "lever": "filter_10_min_triggers_bull (2 -> 1)",
        "block_elite_bull": "True (production, held FIXED to isolate structural lever)",
        "generated_at": dt.datetime.now().isoformat(),
        "window": [str(START), str(END)],
        "real_fills": True,
        "base": {"n": len(r_base.trades), "pnl": round(base_pnl, 2), "min_triggers_bull": 2},
        "unblock": {"n": len(r_unbl.trades), "pnl": round(unbl_pnl, 2), "min_triggers_bull": 1},
        "added_bull_cohort": {
            "n": len(added_bulls), "wr": round(wr, 4), "exp_per_trade": round(exp, 2),
            "net_pnl": round(added_pnl, 2), "significance": sig,
            "day_concentration": conc, "concentration_flag": cflag,
            "slippage": sweep if isinstance(sweep, dict) else {},
            "anchor_no_regression": anchor_ok,
            "trades": [
                {"date": str(_date(t)), "strike": float(t.strike),
                 "pnl": round(t.dollar_pnl, 2)} for t in sorted(added_bulls, key=_date)
            ],
        },
        "verdict": verdict,
    }
    outp = os.path.join(REPO, "analysis", "recommendations",
                        "bull-unblock-structural-2026-06-30.json")
    json.dump(out, open(outp, "w"), indent=2)
    print(f"\n[written] {outp}")
    return out


if __name__ == "__main__":
    main()

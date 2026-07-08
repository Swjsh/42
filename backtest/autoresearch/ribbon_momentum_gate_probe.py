"""RIBBON-MOMENTUM-GATE PROBE (V0, engine-vision build 2026-07-08).

F1 (recovered audit, re-verified live 2026-07-08): `min_ribbon_momentum_cents=0` in Safe params
ARMS the RIBBON_MOMENTUM_GATE (gates.py: `_thresh is not None` — 0 != None), blocking entries
when the 3-bar ribbon spread CONTRACTS (_rmom < 0). It was intended OFF (0) but the code needs
null. Fired 29x SKIP_RIBBON_MOMENTUM_GATE in the live log. Before disabling it (which unblocks
entries), A/B it: is the cohort it removes net-POSITIVE (gate harmful -> disable) or net-NEGATIVE
(gate protective -> keep, just relabel)? Decision by DATA, not by "J wants trades."

Method (same as bull_unblock_replay_probe.py): run the REAL engine twice over the fresh OPRA
window (use_real_fills=True):
  ON  = production Safe config, min_ribbon_momentum_cents=0   (gate armed, current live)
  OFF = identical but min_ribbon_momentum_cents=None          (gate disabled)
REMOVED cohort = trades present with the gate OFF but not ON = exactly what the gate removes.
Net-positive + survives slippage + sufficient n -> DISABLE (unblock). Else -> KEEP.

Read-only on production state. No Alpaca. No params edits. $0 (cached fills).
"""
import sys, os, json, datetime as dt
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import pandas as pd
from lib.orchestrator import run_backtest
from autoresearch.probe_stats import (
    significance, day_concentration, concentration_flag, slippage_sweep,
)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPY = "data/spy_5m_2026-05-19_2026-06-30.csv"
VIX = "data/vix_5m_2026-05-19_2026-06-30.csv"
START = dt.date(2026, 5, 21)
END = dt.date(2026, 6, 30)
ANCHOR_DATES = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}


def _cfg(gate_on: bool) -> dict:
    """Production Safe config (live params.json), ribbon-momentum gate toggled — all OTHER
    gates held at their live values so this isolates the ribbon-momentum gate."""
    p = json.load(open(os.path.join(REPO, "automation", "state", "params.json")))
    return dict(
        use_real_fills=True,
        no_trade_before=dt.time(9, 35),
        enable_bullish=True,
        block_elite_bull=bool(p.get("block_elite_bull", True)),
        block_elite_bull_vix_low=float(p.get("block_elite_bull_vix_low", 0.0)),
        block_elite_bull_vix_high=float(p.get("block_elite_bull_vix_high", 25.0)),
        block_bull_1100_1200=bool(p.get("block_bull_1100_1200", True)),
        block_level_rejection=bool(p.get("block_level_rejection", True)),
        min_triggers_bull=int(p.get("filter_10_min_triggers_bull", 2)),
        min_ribbon_momentum_cents=(0.0 if gate_on else None),  # THE TOGGLE (0=armed / None=off)
        strike_offset=-2,
        per_trade_risk_cap_pct=0.30,
        initial_equity=1513.0,
    )


def classify_verdict(has_trades, added_net_positive, survives_slippage, sufficient_n):
    """Removing the gate is worth it ONLY if the cohort it removes is net-positive AND survives
    slippage AND is statistically sufficient. A net-negative removed cohort = the gate correctly
    blocks losers (keep it; the 0-vs-null bug is then benign)."""
    if not has_trades:
        return "GATE_INERT_ON_FRESH_WINDOW"
    if added_net_positive and survives_slippage and sufficient_n:
        return "GATE_HARMFUL_DISABLE"
    if added_net_positive:
        return "REMOVED_COHORT_POSITIVE_BUT_THIN_OR_FRAGILE"
    return "GATE_PROTECTIVE_KEEP"


def _key(t):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return (ts.to_pydatetime(), t.side, round(float(t.strike), 2))


def _date(t):
    ts = pd.Timestamp(t.entry_time_et)
    if ts.tzinfo is not None:
        ts = ts.tz_localize(None)
    return ts.date()


def main():
    spy = pd.read_csv(os.path.join(REPO, "backtest", SPY))
    vix = pd.read_csv(os.path.join(REPO, "backtest", VIX))
    print("=" * 72)
    print("RIBBON-MOMENTUM-GATE PROBE (V0) — F1 on/off A/B on real fills")
    print(f"window {START}..{END}  (use_real_fills=True)")
    print("=" * 72)
    r_on = run_backtest(spy, vix, start_date=START, end_date=END, **_cfg(True))
    r_off = run_backtest(spy, vix, start_date=START, end_date=END, **_cfg(False))

    on_keys = {_key(t) for t in r_on.trades}
    added = [t for t in r_off.trades if _key(t) not in on_keys]

    on_pnl = sum(t.dollar_pnl for t in r_on.trades)
    off_pnl = sum(t.dollar_pnl for t in r_off.trades)
    added_pnl = sum(t.dollar_pnl for t in added)
    pnls = [t.dollar_pnl for t in added]
    wins = sum(1 for x in pnls if x > 0)
    rows = [{"dollar_pnl": t.dollar_pnl, "qty": getattr(t, "qty", 1) or 1} for t in added]

    print(f"\nGATE ON  (min_ribbon_momentum_cents=0, live):  n={len(r_on.trades):3d}  pnl={on_pnl:+.0f}")
    print(f"GATE OFF (disabled):                           n={len(r_off.trades):3d}  pnl={off_pnl:+.0f}")
    print(f"\nREMOVED cohort (blocked by the gate): n={len(added)}")
    for t in sorted(added, key=_date):
        ts = pd.Timestamp(t.entry_time_et)
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        wl = "WIN" if t.dollar_pnl > 0 else ("EVEN" if t.dollar_pnl == 0 else "LOSS")
        print(f"  {_date(t)} {ts.strftime('%H:%M')} {t.side} {float(t.strike):8.0f} {t.dollar_pnl:+8.1f} {wl}")

    wr = wins / len(added) if added else 0.0
    exp = added_pnl / len(added) if added else 0.0
    sig = significance(len(added))
    by_day: dict = {}
    for t in added:
        by_day[str(_date(t))] = by_day.get(str(_date(t)), 0.0) + t.dollar_pnl
    conc = day_concentration(by_day) if added else {}
    top3 = conc.get("top3_day_pct_of_net") if conc else None
    sweep = slippage_sweep(rows) if added else {}
    anchor_added = [t for t in added if _date(t) in ANCHOR_DATES]

    added_net_positive = added_pnl > 0
    survives = isinstance(sweep, dict) and sweep.get("verdict") == "SURVIVES_REALISTIC"
    sufficient = bool(sig.get("sufficient"))
    verdict = classify_verdict(bool(added), added_net_positive, survives, sufficient)

    print("\n--- REMOVED COHORT SCORE ---")
    print(f"  n={len(added)}  WR={wr:.1%}  exp/tr={exp:+.1f}  net={added_pnl:+.0f}")
    print(f"  sufficient={sufficient} ({sig.get('note')})  slippage={sweep.get('verdict')} "
          f"top3day%={top3}  anchors_hit={len(anchor_added)}")
    print(f"\n=== VERDICT: {verdict} ===")
    if verdict == "GATE_HARMFUL_DISABLE":
        print("  -> DISABLE min_ribbon_momentum_cents (null). Gate removes a NET-POSITIVE cohort = costing entries.")
    elif verdict == "GATE_PROTECTIVE_KEEP":
        print("  -> KEEP. Gate removes a NET-NEGATIVE cohort = correctly blocks losers (0-vs-null bug is benign).")
    else:
        print("  -> NO CLEAN ACTION (thin/fragile/inert). Do not disable on this evidence.")

    out = {"probe": "ribbon_momentum_gate_V0", "window": [str(START), str(END)],
           "gate_on_n": len(r_on.trades), "gate_on_pnl": on_pnl,
           "gate_off_n": len(r_off.trades), "gate_off_pnl": off_pnl,
           "removed_n": len(added), "removed_pnl": added_pnl, "removed_wr": wr,
           "removed_exp": exp, "sufficient": sufficient, "slippage": sweep.get("verdict"),
           "top3_day_pct": top3, "anchors_hit": len(anchor_added), "verdict": verdict}
    outp = os.path.join(REPO, "analysis", "recommendations", "ribbon-momentum-gate-probe-2026-07-08.json")
    json.dump(out, open(outp, "w"), indent=2)
    print(f"\nwrote {outp}")


if __name__ == "__main__":
    main()

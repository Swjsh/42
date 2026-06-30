"""BULL-UNBLOCK-REPLAY-PROBE — re-audit `block_elite_bull` on the FRESH OPRA window.

Context (queue BULL-UNBLOCK-REPLAY-PROBE, the #1 project thread):
  The rig has never filled an ENTER_BULL in 2544 lifetime decisions. On 2026-06-30
  the live engine logged 32x SKIP_ELITE_BULL_LEVEL_RECLAIM on a bull day — i.e.
  `detect_level_reclaim` DID fire (the single-bar straddle happened) and the setup
  reached ELITE, but `block_elite_bull` (VIX band [0,25)) killed it. So the
  empirically-firing block on bull days is block_elite_bull, not (only) the
  structural reclaim detector.

  block_elite_bull's OP-22 A/B (2026-06-18, _block_elite_bull_doc) was run on the
  OLD engine over 2025-01..2026-06 and concluded "remove the OOS losers @ VIX
  17.5-25". Per memory `bull-blocks A/B'd on OLD engine, re-audit on engine change`
  and OP-16 (per-direction blocks each remove a *losing* cohort), this probe
  RE-AUDITS that block on the freshest OPRA real-fills window.

Method (the correct A/B — block_elite_bull is a real config knob, not post-hoc):
  Run the REAL engine twice over the fresh window with use_real_fills=True:
    BASE    = production bull config (block_elite_bull=True, band [0,25))
    UNBLOCK = identical but block_elite_bull=False
  The ADDED bull cohort (trades present in UNBLOCK but not BASE) is exactly what
  block_elite_bull removes. Score that cohort on real fills:
    - net positive + survives slippage  -> unblocking ADDS edge -> propose to J (rail-4)
    - net negative                       -> block correctly removes losers on the
                                            fresh window too -> honest null, bull stays gated

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

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SPY = "data/spy_5m_2026-05-19_2026-06-30.csv"
VIX = "data/vix_5m_2026-05-19_2026-06-30.csv"

# Fresh OPRA real-fills window (matches the recency-check window; first full
# trading day after the 05-19 data start so the ribbon/level warmup is clean).
START = dt.date(2026, 5, 21)
END = dt.date(2026, 6, 30)

# Anchor days are J's PUT/BEAR source-of-truth trades (CLAUDE.md OP-16) — none are
# bulls, so no bull-unblock can regress an anchor; we assert that holds.
ANCHOR_DATES = {dt.date(2026, 4, 29), dt.date(2026, 5, 1), dt.date(2026, 5, 4)}


def _bull_cfg(block_elite_bull: bool) -> dict:
    """Production Safe bull config (read from live params.json), block toggled."""
    p = json.load(open(os.path.join(REPO, "automation", "state", "params.json")))
    return dict(
        use_real_fills=True,
        no_trade_before=dt.time(9, 35),
        enable_bullish=True,
        block_elite_bull=block_elite_bull,
        block_elite_bull_vix_low=float(p.get("block_elite_bull_vix_low", 0.0)),
        block_elite_bull_vix_high=float(p.get("block_elite_bull_vix_high", 25.0)),
        block_bull_1100_1200=bool(p.get("block_bull_1100_1200", True)),
        block_level_rejection=bool(p.get("block_level_rejection", True)),
        min_triggers_bull=int(p.get("filter_10_min_triggers_bull", 2)),
        strike_offset=-2,            # Safe OTM-2 tier (held constant across A/B)
        per_trade_risk_cap_pct=0.30,
        initial_equity=1763.0,
    )


def classify_verdict(has_trades: bool, added_net_positive: bool,
                     survives_slippage: bool, sufficient_n: bool) -> str:
    """Pure verdict ladder for the added-bull cohort (extracted for guarding).

    Unblocking the gate is only worth proposing if the cohort it removes is
    net-positive AND survives realistic slippage AND is statistically sufficient.
    A net-negative cohort means the block is correctly removing losers -> KEEP.
    """
    if not has_trades:
        return "NO_DELTA_BLOCK_INERT_ON_FRESH_WINDOW"
    if added_net_positive and survives_slippage and sufficient_n:
        return "UNBLOCK_ADDS_EDGE_PROPOSE"
    if added_net_positive:
        return "UNBLOCK_POSITIVE_BUT_THIN_OR_FRAGILE"
    return "BLOCK_CORRECTLY_REMOVES_LOSERS_KEEP"


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
    print("BULL-UNBLOCK-REPLAY-PROBE — re-audit block_elite_bull on fresh OPRA")
    print(f"window {START}..{END}  (use_real_fills=True)")
    print("=" * 72)

    r_base = run_backtest(spy, vix, start_date=START, end_date=END, **_bull_cfg(True))
    r_unbl = run_backtest(spy, vix, start_date=START, end_date=END, **_bull_cfg(False))

    base_keys = {_key(t) for t in r_base.trades}
    added = [t for t in r_unbl.trades if _key(t) not in base_keys]
    added_bulls = [t for t in added if t.side == "C"]

    base_pnl = sum(t.dollar_pnl for t in r_base.trades)
    unbl_pnl = sum(t.dollar_pnl for t in r_unbl.trades)
    added_pnl = sum(t.dollar_pnl for t in added_bulls)
    # rows for the probe_stats slippage helpers (need dollar_pnl + qty keys)
    rows = [{"dollar_pnl": t.dollar_pnl, "qty": getattr(t, "qty", 1) or 1}
            for t in added_bulls]
    pnls = [t.dollar_pnl for t in added_bulls]
    wins = sum(1 for x in pnls if x > 0)

    print(f"\nBASE   (block_elite_bull=True):  n={len(r_base.trades):3d}  pnl={base_pnl:+.0f}")
    print(f"UNBLOCK(block_elite_bull=False): n={len(r_unbl.trades):3d}  pnl={unbl_pnl:+.0f}")
    print(f"\nADDED bull cohort (the block's removed trades): n={len(added_bulls)}")
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
    # by-day pnl map for concentration
    by_day: dict = {}
    for t in added_bulls:
        by_day[str(_date(t))] = by_day.get(str(_date(t)), 0.0) + t.dollar_pnl
    conc = day_concentration(by_day) if added_bulls else {}
    top3 = conc.get("top3_day_pct_of_net") if conc else None
    cflag = concentration_flag(top3) if added_bulls else {}
    sweep = slippage_sweep(rows) if added_bulls else {}

    anchor_added = [t for t in added_bulls if _date(t) in ANCHOR_DATES]
    anchor_ok = not anchor_added  # no bull anchors exist -> must be empty

    # VERDICT: unblocking adds edge only if the removed cohort is net-positive AND
    # survives realistic slippage AND is statistically sufficient. Otherwise
    # block_elite_bull is correctly removing losers on the fresh window (honest null).
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
        "probe": "bull_unblock_replay_probe",
        "generated_at": dt.datetime.now().isoformat(),
        "window": [str(START), str(END)],
        "real_fills": True,
        "base": {"n": len(r_base.trades), "pnl": round(base_pnl, 2)},
        "unblock": {"n": len(r_unbl.trades), "pnl": round(unbl_pnl, 2)},
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
                        "bull-unblock-elite-replay-2026-06-30.json")
    json.dump(out, open(outp, "w"), indent=2)
    print(f"\n[written] {outp}")
    return out


if __name__ == "__main__":
    main()

"""Chef A/B: OP-16 BULLISH_RECLAIM setup-scope lock — KEEP (bear-only) vs UNBLOCK (bull+bear).

Re-validates the OP-16 doctrine setup-scope lock under the CURRENT engine
(real OPRA fills + production params + managed exits), NOT the old BS-sim/OTM/wide-stop engine.

KEEP  = production params, enable_bullish=False  (current dormant doctrine state)
UNBLOCK = production params, enable_bullish=True   (bull setup allowed; its own
          VALIDATED sub-gates — block_elite_bull, block_bull_1100_1200,
          block_bull_ribbon_flip — stay ON; only the scope lock is removed)

Both runs use real fills + the full production params translation. Reports
edge_capture on J's source-of-truth days + aggregate metrics + anchor-no-regression.
"""
import datetime as dt
import json
import math
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backtest"))

from backtest.lib.orchestrator import run_backtest, _params_to_kwargs  # noqa: E402

DATA = REPO / "backtest" / "data"
PARAMS = json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8"))

START = "2025-01-02"
END = "2026-06-18"
SAFE_EQUITY = 2000.0  # Safe-2 tier -> v15 strike ladder picks OTM-3 at $2K

# J source-of-truth (OP-16). All PUT/bear. winners engine MUST take; losers MUST skip/lose-less.
WINNERS = {  # date -> J pnl
    "2026-04-29": 342.0,
    "2026-05-01": 470.0,
    "2026-05-04": 730.0,
}
LOSERS = {
    "2026-05-05": -260.0,
    "2026-05-06": -300.0,
    "2026-05-07": -120.0,  # 734C -45 + 737C -120; worst-case loser day, use the larger
}
MAX_EDGE = 1542.0


def load():
    spy = pd.read_csv(DATA / f"spy_5m_2025-01-01_2026-06-18.csv")
    vix = pd.read_csv(DATA / f"vix_5m_2025-01-01_2026-06-18.csv")
    spy = spy[(spy["timestamp_et"] >= START) & (spy["timestamp_et"] < f"{END}T23:59:59")].reset_index(drop=True)
    vix = vix[(vix["timestamp_et"] >= START) & (vix["timestamp_et"] < f"{END}T23:59:59")].reset_index(drop=True)
    return spy, vix


def run(spy, vix, enable_bullish):
    kwargs = _params_to_kwargs(PARAMS, account_equity=SAFE_EQUITY)
    kwargs["enable_bullish"] = enable_bullish
    res = run_backtest(
        spy, vix,
        start_date=dt.date.fromisoformat(START),
        end_date=dt.date.fromisoformat(END),
        use_real_fills=True,
        **kwargs,
    )
    return res.trades


def naive(ts):
    ts = pd.Timestamp(ts)
    return ts.tz_localize(None) if ts.tzinfo else ts


def metrics(trades):
    pnls = [t.dollar_pnl for t in trades]
    n = len(pnls)
    total = sum(pnls)
    wins = [p for p in pnls if p > 0]
    wr = len(wins) / n if n else 0.0
    mean = total / n if n else 0.0
    sd = (sum((p - mean) ** 2 for p in pnls) / (n - 1)) ** 0.5 if n > 1 else 0.0
    sharpe = mean / sd if sd else 0.0
    # drawdown on chronological equity
    cum = 0.0
    peak = 0.0
    mdd = 0.0
    for t in sorted(trades, key=lambda x: naive(x.entry_time_et)):
        cum += t.dollar_pnl
        peak = max(peak, cum)
        mdd = min(mdd, cum - peak)
    # concentration top5
    srt = sorted(pnls, reverse=True)
    top5 = sum(srt[:5]) / total if total > 0 else 0.0
    return dict(n=n, total=total, wr=wr, mean=mean, sharpe=sharpe, mdd=mdd, top5_pct=top5)


def per_day_pnl(trades):
    d = {}
    for t in trades:
        day = naive(t.entry_time_et).date().isoformat()
        d.setdefault(day, 0.0)
        d[day] += t.dollar_pnl
    return d


def edge_capture(trades):
    byday = per_day_pnl(trades)
    cap = 0.0
    detail = {}
    for day in WINNERS:
        pnl = byday.get(day, 0.0)  # engine took -> its pnl; engine skipped -> 0
        cap += pnl
        detail[day] = ("WIN", pnl)
    for day in LOSERS:
        pnl = byday.get(day, 0.0)
        loss_charge = max(0.0, -pnl)  # only positive losses charged
        cap -= loss_charge
        detail[day] = ("LOSS", pnl)
    return cap, detail


def bull_trades(trades):
    return [t for t in trades if "BULLISH" in t.setup]


def main():
    spy, vix = load()
    print(f"Loaded SPY {len(spy)} bars, VIX {len(vix)} bars  [{START}..{END}]")

    keep = run(spy, vix, enable_bullish=False)
    unblock = run(spy, vix, enable_bullish=True)

    mk = metrics(keep)
    mu = metrics(unblock)
    ek, dk = edge_capture(keep)
    eu, du = edge_capture(unblock)

    nbull_k = len(bull_trades(keep))
    nbull_u = len(bull_trades(unblock))
    bull_u_pnl = sum(t.dollar_pnl for t in bull_trades(unblock))
    bull_u_wins = sum(1 for t in bull_trades(unblock) if t.dollar_pnl > 0)

    out = {
        "window": f"{START}..{END}",
        "KEEP_bear_only": mk,
        "UNBLOCK_bull_and_bear": mu,
        "edge_capture_KEEP": ek,
        "edge_capture_UNBLOCK": eu,
        "max_edge": MAX_EDGE,
        "edge_floor_771": 771.0,
        "anchor_detail_KEEP": dk,
        "anchor_detail_UNBLOCK": du,
        "bull_trades_KEEP": nbull_k,
        "bull_trades_UNBLOCK": nbull_u,
        "bull_pnl_UNBLOCK": bull_u_pnl,
        "bull_wr_UNBLOCK": (bull_u_wins / nbull_u) if nbull_u else None,
        "delta_total": mu["total"] - mk["total"],
        "delta_sharpe": mu["sharpe"] - mk["sharpe"],
        "delta_edge_capture": eu - ek,
        "delta_mdd": mu["mdd"] - mk["mdd"],
        "final_score_KEEP": ek * mk["sharpe"],
        "final_score_UNBLOCK": eu * mu["sharpe"],
    }
    print(json.dumps(out, indent=2, default=str))
    (REPO / "analysis" / "recommendations" / "chef-bull-scope-ab-2026-06-26.json").write_text(
        json.dumps(out, indent=2, default=str), encoding="utf-8"
    )


if __name__ == "__main__":
    main()

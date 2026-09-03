"""Re-validate block_conf_lvl_rec_afternoon (Bold/AGG) under the CURRENT engine.

J-directed 2026-06-26: every direction-block must justify itself under the
CURRENT engine (real OPRA fills + ITM strikes + managed exits) or be removed.

This gate (gates.py #12) blocks confluence+level_reclaim entries from 14:00 ET
onward, BOTH directions (the code does not check side). Bold params has it
true with a doc claiming "KEPT but DEAD, fully superseded by
block_conf_lvl_rej_midday_afternoon" -- but that superseding gate was set to
FALSE on 2026-06-18, so the "harmless because superseded" justification is
itself stale and must be re-checked.

A/B: identical engine, toggle ONLY block_conf_lvl_rec_afternoon.
  BLOCKED   = current production (gate true, 14:00+ conf+rec skipped)
  UNBLOCKED = gate false (14:00+ conf+rec allowed)

delta = UNBLOCKED_total - BLOCKED_total. If delta <= 0, blocking helps -> KEEP.
If delta > 0, the block is suppressing net-positive trades -> UNBLOCK candidate.

Real fills only (simulate_trade_real via use_real_fills=True). Anchor check on
the bearish source-of-truth days. Read-only; no Alpaca, no state writes.
"""
from __future__ import annotations
import sys, json, datetime as dt
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from lib.orchestrator import run_backtest  # noqa: E402
from sniper_matrix import norm_str  # noqa: E402

DATA = REPO / "data"
OUT_PATH = REPO.parent / "analysis" / "recommendations" / "conf_lvl_rec_afternoon_revalidate.json"

IS_CUTOFF = dt.date(2026, 2, 27)
MDATES_SET = {dt.date(2026, 5, 26), dt.date(2026, 5, 27),
              dt.date(2026, 5, 28), dt.date(2026, 5, 29)}

# OP-16 source-of-truth bearish anchors (engine MUST take winners / skip-or-lose-less losers)
ANCHOR_WINNERS = {dt.date(2026, 4, 29): 342, dt.date(2026, 5, 1): 470, dt.date(2026, 5, 4): 730}
ANCHOR_LOSERS = {dt.date(2026, 5, 5): -260, dt.date(2026, 5, 6): -300,
                 dt.date(2026, 5, 7): -165}  # 734C -45 + 737C -120

# Current Bold engine config (matches conf_lvl_rec_deep_dive AGG_KWARGS = production-shaped)
BASE_KWARGS = dict(
    use_real_fills=True,
    strike_offset=-2,                 # ITM-2 (Bold)
    premium_stop_pct_bear=-0.50,      # current chart-stop-primary: -50% catastrophe cap
    premium_stop_pct_bull=-0.50,
    tp1_premium_pct=0.75,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=2.5,
    f9_vol_mult=0.7,
    min_triggers_bear=1,
    min_triggers_bull=1,
    no_trade_before=dt.time(9, 35),
    no_trade_window=None,
    block_level_rejection=True,
    block_conf_lvl_rej_midday_afternoon=False,  # CURRENT prod value (removed 2026-06-18)
    midday_trendline_gate=False,                # CURRENT prod value (removed 2026-06-18)
    block_elite_bull=True,
    block_elite_bull_vix_low=15.0,
    block_elite_bull_vix_high=17.5,
    require_bearish_fill_bar=True,
    time_stop_minutes_before_close=20,
    per_trade_risk_cap_pct=0.5,
    enable_bullish=True,
    params_overrides={"vix_bear_threshold": 15.0},
)


def get_fill_days():
    c = Counter(f.name[3:9] for f in (DATA / "options").glob("SPY*.csv"))
    return sorted({dt.datetime.strptime(k, "%y%m%d").date() for k, v in c.items() if v >= 8})


def load_spy_vix():
    spy_path = sorted(DATA.glob("spy_5m_2025-01-01_*.csv"),
                      key=lambda p: p.stat().st_size, reverse=True)[0]
    vix_path = DATA / spy_path.name.replace("spy_5m", "vix_5m")
    print(f"  SPY: {spy_path.name}")
    print(f"  VIX: {vix_path.name}")
    return norm_str(pd.read_csv(spy_path)), norm_str(pd.read_csv(vix_path))


def is_conf_rec(t):
    trigs = t.triggers_fired
    return "confluence" in trigs and "level_reclaim" in trigs


def is_afternoon(t):
    edt = t.entry_time_et
    if getattr(edt, "tzinfo", None) is not None:
        edt = edt.replace(tzinfo=None)
    return edt.time() >= dt.time(14, 0)


def summarize(trades, label):
    pnls = [t.dollar_pnl for t in trades]
    n = len(pnls)
    wins = sum(1 for p in pnls if p > 0)
    total = sum(pnls)
    return {
        "label": label, "n": n, "wins": wins,
        "wr": round(wins / n, 4) if n else 0.0,
        "total": round(total, 2),
        "avg": round(total / n, 2) if n else 0.0,
    }


def anchor_report(trades):
    """Per-anchor-date engine P&L (sum of trades that day)."""
    by_date = defaultdict(float)
    cnt = defaultdict(int)
    for t in trades:
        d = t.entry_time_et.date()
        by_date[d] += t.dollar_pnl
        cnt[d] += 1
    rep = {}
    for d in list(ANCHOR_WINNERS) + list(ANCHOR_LOSERS):
        rep[str(d)] = {"engine_pnl": round(by_date.get(d, 0.0), 2),
                       "n_trades": cnt.get(d, 0)}
    return rep


def edge_capture(trades):
    """OP-16 edge_capture = sum(pnl on winner days) - sum(max(0, loss on loser days))."""
    by_date = defaultdict(float)
    for t in trades:
        by_date[t.entry_time_et.date()] += t.dollar_pnl
    cap = 0.0
    for d in ANCHOR_WINNERS:
        cap += by_date.get(d, 0.0)
    for d in ANCHOR_LOSERS:
        loss = by_date.get(d, 0.0)
        cap -= max(0.0, -loss)  # subtract magnitude of any loss on loser days
    return round(cap, 2)


def run_window(spy_df, vix_df, days, blocked):
    kw = dict(BASE_KWARGS)
    kw["block_conf_lvl_rec_afternoon"] = blocked
    res = run_backtest(spy_df, vix_df, start_date=days[0], end_date=days[-1], **kw)
    return res.trades


def main():
    print("=" * 72)
    print("RE-VALIDATE block_conf_lvl_rec_afternoon (Bold) - CURRENT ENGINE, REAL FILLS")
    print("=" * 72)

    all_days = get_fill_days()
    spy_df, vix_df = load_spy_vix()
    spy_dates = set(pd.to_datetime(spy_df["timestamp_et"].str[:10]).dt.date)

    is_days = [d for d in all_days if d < IS_CUTOFF and d not in MDATES_SET and d in spy_dates]
    oos_days = [d for d in all_days if d >= IS_CUTOFF and d not in MDATES_SET and d in spy_dates]

    print(f"  IS:  {len(is_days)} days  {is_days[0]} .. {is_days[-1]}")
    print(f"  OOS: {len(oos_days)} days {oos_days[0]} .. {oos_days[-1]}")

    out = {"gate": "block_conf_lvl_rec_afternoon", "account": "bold",
           "engine": "real_fills + ITM-2 + managed -50% cap + chandelier",
           "is_range": [str(is_days[0]), str(is_days[-1])],
           "oos_range": [str(oos_days[0]), str(oos_days[-1])],
           "windows": {}}

    for wname, days in [("IS", is_days), ("OOS", oos_days)]:
        print(f"\n[{wname}] running BLOCKED then UNBLOCKED ...")
        t_block = run_window(spy_df, vix_df, days, blocked=True)
        t_unblk = run_window(spy_df, vix_df, days, blocked=False)

        # The trades the gate ACTUALLY removes = afternoon conf+rec present in
        # unblocked set but absent in blocked set.
        removed = [t for t in t_unblk if is_conf_rec(t) and is_afternoon(t)]
        removed_sum = summarize(removed, "afternoon_conf_rec_removed_by_gate")
        removed_side = Counter(t.side for t in removed)

        s_block = summarize(t_block, "BLOCKED(prod)")
        s_unblk = summarize(t_unblk, "UNBLOCKED")
        delta_total = round(s_unblk["total"] - s_block["total"], 2)

        print(f"  BLOCKED:   n={s_block['n']:>4} WR={s_block['wr']:.3f} total={s_block['total']:+.0f}")
        print(f"  UNBLOCKED: n={s_unblk['n']:>4} WR={s_unblk['wr']:.3f} total={s_unblk['total']:+.0f}")
        print(f"  delta (UNBLOCKED - BLOCKED) = {delta_total:+.2f}")
        print(f"  gate removes {removed_sum['n']} afternoon conf+rec trades: "
              f"total={removed_sum['total']:+.0f} WR={removed_sum['wr']:.3f} "
              f"sides={dict(removed_side)}")

        out["windows"][wname] = {
            "blocked": s_block, "unblocked": s_unblk,
            "delta_total_unblocked_minus_blocked": delta_total,
            "trades_removed_by_gate": removed_sum,
            "removed_sides": dict(removed_side),
            "removed_detail": [
                {"date": str(t.entry_time_et.date()), "side": t.side,
                 "pnl": round(t.dollar_pnl, 2),
                 "time": str(t.entry_time_et.time())[:5],
                 "exit": str(t.exit_reason)} for t in removed],
            "anchor_blocked": anchor_report(t_block),
            "anchor_unblocked": anchor_report(t_unblk),
            "edge_capture_blocked": edge_capture(t_block),
            "edge_capture_unblocked": edge_capture(t_unblk),
        }

    # Verdict logic
    is_d = out["windows"]["IS"]["delta_total_unblocked_minus_blocked"]
    oos_d = out["windows"]["OOS"]["delta_total_unblocked_minus_blocked"]
    ec_is_b = out["windows"]["IS"]["edge_capture_blocked"]
    ec_is_u = out["windows"]["IS"]["edge_capture_unblocked"]
    ec_oos_b = out["windows"]["OOS"]["edge_capture_blocked"]
    ec_oos_u = out["windows"]["OOS"]["edge_capture_unblocked"]

    n_removed_total = (out["windows"]["IS"]["trades_removed_by_gate"]["n"]
                       + out["windows"]["OOS"]["trades_removed_by_gate"]["n"])

    # KEEP only if blocking still produces a positive (or non-negative) delta AND
    # does not regress anchors. UNBLOCK if delta>0 (block suppresses winners) OR
    # gate is a true no-op (removes 0 trades -> trivially remove the dead knob).
    anchor_regress = (ec_is_u < ec_is_b - 1) or (ec_oos_u < ec_oos_b - 1)

    if n_removed_total == 0:
        verdict = "UNBLOCK_NOOP"  # truly dead; remove per target-state (nothing unvalidated should carry a live gate)
    elif is_d > 0 and oos_d >= 0 and not anchor_regress:
        verdict = "UNBLOCK_SUPPRESSES_WINNERS"
    elif is_d <= 0 and oos_d <= 0:
        verdict = "KEEP"
    else:
        verdict = "INCONCLUSIVE"

    out["verdict"] = verdict
    out["n_removed_total"] = n_removed_total
    out["anchor_regress_on_unblock"] = anchor_regress
    out["summary"] = {
        "is_delta": is_d, "oos_delta": oos_d,
        "edge_capture": {"is_blocked": ec_is_b, "is_unblocked": ec_is_u,
                         "oos_blocked": ec_oos_b, "oos_unblocked": ec_oos_u},
    }

    print("\n" + "=" * 72)
    print(f"VERDICT: {verdict}")
    print(f"  n trades removed by gate (IS+OOS) = {n_removed_total}")
    print(f"  IS delta={is_d:+.0f}  OOS delta={oos_d:+.0f}")
    print(f"  edge_capture IS  blocked={ec_is_b:+.0f} unblocked={ec_is_u:+.0f}")
    print(f"  edge_capture OOS blocked={ec_oos_b:+.0f} unblocked={ec_oos_u:+.0f}")
    print(f"  anchor regress on unblock = {anchor_regress}")

    OUT_PATH.parent.mkdir(exist_ok=True)
    OUT_PATH.write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved: {OUT_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())

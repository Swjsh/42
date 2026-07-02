"""Fresh-eyes trait analysis of J's WeBull history (2021-2023), from trades-normalized.csv.

Writes analysis/j-webull/traits.json + traits-report.md.
Population: closed SPX/SPY-family flat->flat episodes. P&L = J's actual fills (real money).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT_DIR = Path(__file__).resolve().parents[1]
rng = np.random.default_rng(42)


def stats(g: pd.DataFrame) -> dict:
    if len(g) == 0:
        return {"n": 0}
    w = g[g.pnl > 0]
    l = g[g.pnl <= 0]
    return {
        "n": int(len(g)),
        "wr_pct": round((g.pnl > 0).mean() * 100, 1),
        "total": round(g.pnl.sum(), 0),
        "exp": round(g.pnl.mean(), 1),
        "avg_win": round(w.pnl.mean(), 1) if len(w) else None,
        "avg_loss": round(l.pnl.mean(), 1) if len(l) else None,
        "pf": round(w.pnl.sum() / abs(l.pnl.sum()), 2) if len(l) and l.pnl.sum() != 0 else None,
    }


def by(df: pd.DataFrame, key, order=None) -> dict:
    out = {}
    for k, g in df.groupby(key, observed=True):
        out[str(k)] = stats(g)
    if order:
        out = {k: out[k] for k in order if k in out}
    return out


def main() -> None:
    df = pd.read_csv(OUT_DIR / "trades-normalized.csv", parse_dates=["entry_ts_et", "exit_ts_et"])
    fam = df[df.is_family & df.closed].copy().sort_values("entry_ts_et").reset_index(drop=True)
    fam["date"] = fam.entry_ts_et.dt.date
    fam["win"] = fam.pnl > 0
    R = {"population": {"closed_family_episodes": len(fam),
                        "date_range": [str(fam.date.min()), str(fam.date.max())],
                        "distinct_days": int(fam.date.nunique())}}
    R["overall"] = stats(fam)
    R["by_year"] = by(fam, fam.entry_ts_et.dt.year)
    R["by_quarter"] = by(fam, fam.entry_ts_et.dt.to_period("Q").astype(str))
    R["by_underlying"] = by(fam, "underlying")
    R["by_bias"] = by(fam, "bias")
    R["by_dte"] = by(fam, np.where(fam.is_0dte, "0dte", "1dte+"))
    R["by_dow"] = by(fam, "dow", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"])
    R["by_tod"] = by(fam, "tod_bucket")

    # ---- sizing (C31 test) ----
    R["by_size_band"] = by(fam, "size_band", ["1-2", "3-5", "6-10", "11+"])
    fam["risk_band"] = pd.cut(fam.premium_at_risk, [0, 250, 750, 1500, 1e9],
                              labels=["<=250", "250-750", "750-1500", ">1500"])
    R["by_premium_at_risk"] = by(fam, "risk_band")
    R["by_scaled_in"] = by(fam, np.where(fam.scaled_in, "scaled_in", "single_fill"))
    # per-contract expectancy: same-entry-quality test (sizing vs selection)
    for band in ["1-2", "3-5", "6-10"]:
        g = fam[fam.size_band == band]
        R["by_size_band"][band]["exp_per_contract"] = round((g.pnl / g.qty).mean(), 1)
    # XSP contamination: XSP is ~1/10 SPX notional
    R["xsp_share_of_3plus"] = {
        "n_3plus": int((fam.qty >= 3).sum()),
        "n_3plus_xsp": int(((fam.qty >= 3) & (fam.underlying == "XSP")).sum()),
    }
    # bootstrap: is the 1-2 lot profit distinguishable from luck?
    small = fam[fam.size_band == "1-2"].pnl.values
    boots = np.array([rng.choice(small, len(small), replace=True).sum() for _ in range(10000)])
    R["small_lot_bootstrap"] = {
        "total": round(small.sum(), 0), "p_sum_gt_0": round((boots > 0).mean(), 3),
        "ci90": [round(np.percentile(boots, 5), 0), round(np.percentile(boots, 95), 0)],
        "top5_wins_share": round(np.sort(small)[-5:].sum() / small.sum(), 2) if small.sum() > 0 else None,
    }

    # ---- moneyness ----
    m = fam[fam.ctx_ok & fam.otm_pct.notna()].copy()
    m["m_band"] = pd.cut(m.otm_pct, [-99, -0.5, -0.1, 0.1, 0.5, 1.0, 99],
                         labels=["ITM>0.5%", "ITM0.1-0.5", "ATM±0.1", "OTM0.1-0.5",
                                 "OTM0.5-1.0", "OTM>1.0%"])
    R["by_moneyness"] = by(m, "m_band")

    # ---- hold duration / exit discipline ----
    w, l = fam[fam.win], fam[~fam.win]
    R["hold_min"] = {
        "winners": {"mean": round(w.hold_min.mean(), 1), "median": round(w.hold_min.median(), 1), "n": len(w)},
        "losers": {"mean": round(l.hold_min.mean(), 1), "median": round(l.hold_min.median(), 1), "n": len(l)},
    }
    R["exit_discipline"] = {
        "loser_ret_median_pct": round(l.ret_pct.median(), 1),
        "losers_beyond_-50pct": {"n": int((l.ret_pct <= -50).sum()),
                                 "share_of_losers": round((l.ret_pct <= -50).mean(), 2),
                                 "pnl": round(l[l.ret_pct <= -50].pnl.sum(), 0)},
        "losers_beyond_-80pct": {"n": int((l.ret_pct <= -80).sum()),
                                 "pnl": round(l[l.ret_pct <= -80].pnl.sum(), 0)},
        "winner_ret_median_pct": round(w.ret_pct.median(), 1),
        "winners_cut_below_+30pct": {"n": int((w.ret_pct < 30).sum()),
                                     "share_of_winners": round((w.ret_pct < 30).mean(), 2)},
        "winners_ridden_past_+100pct": {"n": int((w.ret_pct >= 100).sum()),
                                        "pnl": round(w[w.ret_pct >= 100].pnl.sum(), 0)},
    }

    # ---- tilt: behaviour after a loss vs after a win (same-day previous episode) ----
    fam["prev_pnl"] = np.nan
    fam["prev_exit"] = pd.NaT
    fam["prev_risk"] = np.nan
    for d, g in fam.groupby("date"):
        idx = g.index
        for i in range(1, len(idx)):
            prev_closed = g.iloc[:i][g.iloc[:i].exit_ts_et <= g.iloc[i].entry_ts_et]
            if len(prev_closed):
                p = prev_closed.iloc[-1]
                fam.loc[idx[i], ["prev_pnl", "prev_risk"]] = [p.pnl, p.premium_at_risk]
                fam.loc[idx[i], "prev_exit"] = p.exit_ts_et
    seq = fam[fam.prev_pnl.notna()].copy()
    seq["after"] = np.where(seq.prev_pnl > 0, "after_win", "after_loss")
    seq["gap_min"] = (seq.entry_ts_et - seq.prev_exit).dt.total_seconds() / 60
    seq["risk_ratio"] = seq.premium_at_risk / seq.prev_risk
    tilt = {}
    for k, g in seq.groupby("after"):
        tilt[k] = stats(g) | {
            "median_reentry_gap_min": round(g.gap_min.median(), 1),
            "reentry_<=5min_share": round((g.gap_min <= 5).mean(), 2),
            "median_risk_ratio_vs_prev": round(g.risk_ratio.median(), 2),
            "sized_up_>=1.5x_share": round((g.risk_ratio >= 1.5).mean(), 2),
        }
    # revenge cohort: re-entry within 5 min of a LOSS
    rev = seq[(seq.after == "after_loss") & (seq.gap_min <= 5)]
    tilt["revenge_reentry_<=5min_after_loss"] = stats(rev)
    tilt["patient_reentry_>15min_after_loss"] = stats(seq[(seq.after == "after_loss") & (seq.gap_min > 15)])
    # size band x preceding outcome (is 3+ sizing a tilt behaviour?)
    tilt["size3plus_given_prior"] = {
        k: round((g.qty >= 3).mean(), 3) for k, g in seq.groupby("after")
    }
    R["tilt"] = tilt

    # consecutive-loss escalation within a day
    esc = {}
    seq2 = fam.copy()
    seq2["daily_loss_streak_before"] = 0
    for d, g in seq2.groupby("date"):
        streak = 0
        for i in g.index:
            seq2.loc[i, "daily_loss_streak_before"] = streak
            streak = streak + 1 if seq2.loc[i, "pnl"] <= 0 else 0
    for k in [0, 1, 2, 3]:
        g = seq2[seq2.daily_loss_streak_before == (k if k < 3 else seq2.daily_loss_streak_before)]
        g = seq2[seq2.daily_loss_streak_before == k] if k < 3 else seq2[seq2.daily_loss_streak_before >= 3]
        esc[f"{'>=3' if k == 3 else k}_losses_before"] = stats(g) | {
            "median_risk": round(g.premium_at_risk.median(), 0)}
    R["loss_streak_escalation"] = esc

    # ---- daily aggregation + concentration ----
    daily = fam.groupby("date").pnl.sum()
    R["daily"] = {
        "n_days": len(daily), "green_days_pct": round((daily > 0).mean() * 100, 1),
        "mean": round(daily.mean(), 0), "worst5": [round(x) for x in daily.nsmallest(5)],
        "worst5_share_of_net_loss": round(daily.nsmallest(5).sum() / daily.sum(), 2),
        "best5": [round(x) for x in daily.nlargest(5)],
    }
    # counterfactual: hard stop after 2 consecutive losing episodes in a day
    saved, kept = 0.0, 0.0
    for d, g in seq2.groupby("date"):
        cut = g[g.daily_loss_streak_before >= 2]
        saved += cut.pnl.sum()
    R["counterfactual_stop_after_2_daily_losses"] = {
        "pnl_of_trades_that_would_be_blocked": round(saved, 0),
        "n_blocked": int((seq2.daily_loss_streak_before >= 2).sum()),
    }
    # counterfactual: cap every episode at 2 contracts (scale pnl by 2/qty for qty>2)
    capped = fam.pnl.where(fam.qty <= 2, fam.pnl * 2 / fam.qty)
    R["counterfactual_cap_2_lots"] = {
        "actual_total": round(fam.pnl.sum(), 0),
        "capped_total": round(capped.sum(), 0),
        "note": "linear scaling; ignores fill-size market impact (tiny at 1-2 SPX lots)",
    }

    # ---- entry fingerprint (context features, ctx_ok only) ----
    c = fam[fam.ctx_ok].copy()
    c["vwap_aligned"] = ((c.bias == "bull") & (c.vwap_side == "above")) | \
                        ((c.bias == "bear") & (c.vwap_side == "below"))
    c["ribbon_aligned"] = ((c.bias == "bull") & (c.ribbon_state == "bull")) | \
                          ((c.bias == "bear") & (c.ribbon_state == "bear"))
    fp = {
        "ctx_coverage_pct": round(fam.ctx_ok.mean() * 100, 1),
        "vwap_aligned": by(c, np.where(c.vwap_aligned, "aligned", "counter")),
        "ribbon_aligned": by(c, np.where(c.ribbon_aligned, "aligned", "counter")),
        "both_aligned": by(c, np.where(c.vwap_aligned & c.ribbon_aligned, "both",
                           np.where(~c.vwap_aligned & ~c.ribbon_aligned, "neither", "mixed"))),
    }
    c["rp_band"] = pd.cut(c.sess_range_pos, [-0.01, 0.25, 0.75, 1.01],
                          labels=["bottom_q", "middle", "top_q"])
    fp["session_range_pos"] = by(c, "rp_band")
    # chase vs fade: bull entries in top quartile / bear in bottom quartile = chasing
    c["chase"] = np.where(((c.bias == "bull") & (c.rp_band == "top_q")) |
                          ((c.bias == "bear") & (c.rp_band == "bottom_q")), "chase",
                 np.where(((c.bias == "bull") & (c.rp_band == "bottom_q")) |
                          ((c.bias == "bear") & (c.rp_band == "top_q")), "fade", "mid"))
    fp["chase_vs_fade"] = by(c, "chase")
    c["lvl_band"] = pd.cut(c.nearest_level_dist_pct.abs(), [-0.001, 0.1, 0.3, 99],
                           labels=["at_level<=0.1%", "near0.1-0.3%", "far>0.3%"])
    fp["nearest_prior_day_level"] = by(c, "lvl_band")
    fp["aligned_morning_vs_rest"] = {
        "vwap_aligned_&_<=10:30": stats(c[c.vwap_aligned & (c.mins_since_open <= 60)]),
        "vwap_aligned_&_>10:30": stats(c[c.vwap_aligned & (c.mins_since_open > 60)]),
        "counter_&_<=10:30": stats(c[~c.vwap_aligned & (c.mins_since_open <= 60)]),
        "counter_&_>10:30": stats(c[~c.vwap_aligned & (c.mins_since_open > 60)]),
    }
    # size x alignment: does J size UP into counter-trend?
    fp["counter_trend_share_by_size"] = {
        b: round((~c[c.size_band == b].vwap_aligned).mean(), 2)
        for b in ["1-2", "3-5", "6-10"] if (c.size_band == b).any()
    }
    fp["by_size_within_aligned"] = by(c[c.vwap_aligned], "size_band", ["1-2", "3-5", "6-10"])
    fp["by_size_within_counter"] = by(c[~c.vwap_aligned], "size_band", ["1-2", "3-5", "6-10"])
    R["entry_fingerprint"] = fp

    # direction x alignment (is the put bleed a direction problem or alignment problem?)
    R["bias_x_alignment"] = {
        f"{b}_{a}": stats(c[(c.bias == b) & (c.vwap_aligned == al)])
        for b in ["bull", "bear"] for a, al in [("aligned", True), ("counter", False)]
    }

    (OUT_DIR / "traits.json").write_text(json.dumps(R, indent=2, default=str))
    print(json.dumps(R, indent=2, default=str))


if __name__ == "__main__":
    main()

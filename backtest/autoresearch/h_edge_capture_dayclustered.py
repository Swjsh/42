"""Adversarial re-check of h_edge_capture_tape: is the big-print/absorption AUC a
per-trade signal or a DAY effect (trending days -> more big prints AND more winners)?
Rebuilds per-trade rows from the (now fully cached) tape, saves them, then:
  (1) within-day label permutation null (shuffle winner labels ONLY within each day,
      2000x) -> preserves the day structure exactly;
  (2) day-demeaned Spearman (feature and label demeaned by day);
  (3) between-day check: corr(day mean feature, day win rate);
  (4) day concentration: distinct days, top-5-day share of winners.
Zero API calls (all windows cached)."""
import sys, json, numpy as np, pandas as pd
sys.path.insert(0, ".")
from autoresearch.h_edge_capture_tape import (load_trades, setup_bucket, entry_ns,
    get_window_signed_tape, compute_features, auc_score, Path)
from pathlib import Path as P
OUT_ROWS = P("data/_edge_capture_rows.csv"); OUT = P("../analysis/recommendations/h-edge-capture-dayclustered.json")
trades = load_trades(P("../journal/trades.csv"))
rows = []
for tr in trades:
    try:
        t_ns = entry_ns(tr.date, tr.time_entry); w = get_window_signed_tape(tr.date, t_ns)
        if w.empty: continue
        rows.append({"idx": tr.idx, "date": tr.date, "bucket": setup_bucket(tr.setup), "pnl": tr.dollar_pnl,
                     "winner": int(tr.dollar_pnl > 0), **compute_features(w, t_ns, 1 if tr.c_or_p == "C" else -1)})
    except Exception as e:
        print("skip", tr.idx, e)
df = pd.DataFrame(rows); df.to_csv(OUT_ROWS, index=False); print("rows", len(df), "->", OUT_ROWS)
FEATS = ["big_share_300s", "big_share_60s", "absorb_300s", "sv_share_300s"]
rng = np.random.default_rng(20260907); res = {}
for b in ["BULLISH_RECLAIM_RIDE_THE_RIBBON", "BEARISH_REJECTION_RIDE_THE_RIBBON"]:
    d = df[df.bucket == b].copy(); days = d.date.nunique()
    wins_by_day = d.groupby("date").winner.sum().sort_values(ascending=False)
    top5 = float(wins_by_day.head(5).sum() / max(1, d.winner.sum()))
    res[b] = {"n": len(d), "days": int(days), "winners": int(d.winner.sum()), "top5_day_share_of_winners": round(top5, 3), "feats": {}}
    print(f"\n{b}: n={len(d)} days={days} winners={int(d.winner.sum())} top5-day share of winners={top5:.2f}")
    for f in FEATS:
        x = d[[f, "winner", "pnl", "date"]].dropna()
        if len(x) < 30: continue
        auc = auc_score(x[f].to_numpy(), x.winner.to_numpy())
        # (1) within-day permutation null
        nulls = []
        for _ in range(2000):
            lab = x.groupby("date").winner.transform(lambda s: rng.permutation(s.to_numpy()))
            nulls.append(auc_score(x[f].to_numpy(), lab.to_numpy()))
        nulls = np.array([v for v in nulls if v is not None]); p_within = float((nulls >= auc).mean())
        # (2) day-demeaned spearman
        fd = x[f] - x.groupby("date")[f].transform("mean"); ld = x.winner - x.groupby("date").winner.transform("mean")
        rho_within = float(pd.Series(fd).rank().corr(pd.Series(ld).rank()))
        # (3) between-day
        g = x.groupby("date").agg(fm=(f, "mean"), wr=("winner", "mean")); rho_between = float(g.fm.corr(g.wr, method="spearman"))
        # tercile $ (full)
        q = pd.qcut(x[f].rank(method="first"), 3, labels=[1, 2, 3]); terc = x.groupby(q).pnl.agg(["mean", "sum", "count"]).round(1).to_dict("index")
        res[b]["feats"][f] = {"auc": round(auc, 4), "within_day_null_95": round(float(np.percentile(nulls, 95)), 4), "p_within_day": round(p_within, 4),
                              "rho_within_day": round(rho_within, 4), "rho_between_day": round(rho_between, 4), "tercile_pnl": {str(k): v for k, v in terc.items()}}
        print(f"  {f:16s} AUC={auc:.3f} within-day null95={np.percentile(nulls,95):.3f} p={p_within:.4f} | rho within-day={rho_within:+.3f} between-day={rho_between:+.3f} | tercile mean$ {[round(terc[k]['mean'],1) for k in sorted(terc)]} sum$ {[round(terc[k]['sum']) for k in sorted(terc)]}")
json.dump(res, open(OUT, "w"), indent=1); print("\nwrote", OUT)

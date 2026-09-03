import json

path = "analysis/deep-research/2026-09-03-money/profit-lock-scope.json"
d = json.load(open(path, encoding="utf-8"))
safe2 = [t for t in d["trades"] if t["arm"] == "safe-2"]


def wr_pf(pnls):
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    wr = len(wins) / len(pnls) if pnls else None
    gp = sum(wins)
    gl = -sum(losses)
    pf = gp / gl if gl else None
    return {"wr": wr, "pf": pf, "gross_profit": round(gp, 2), "gross_loss": round(gl, 2),
            "n_wins": len(wins), "n_losses": len(losses)}


note_770c = (
    "NOT FOUND in cached population -- no SPY*C00770000 fill in fills-ledger.jsonl or "
    "core-decisions.jsonl for 2026-09-02 (that day's traded call strikes were 765-768); "
    "mae-mfe.json was generated 2026-09-02T16:26:57 ET and may predate this specific trade, "
    "or it may be a still-open/2026-09-03 live position this READ-ONLY, no-broker-call "
    "session cannot access. UNVERIFIED, disclosed rather than fabricated."
)

summary = {
    "trusted_arm": "safe-2",
    "n_trusted": len(safe2),
    "wr_pf_control": wr_pf([t["control_pnl"] for t in safe2]),
    "wr_pf_full": wr_pf([t["full_pnl"] for t in safe2]),
    "wr_pf_actual_broker_truth": wr_pf([t["actual_pnl"] for t in safe2]),
    "sub_window_halves": {"h1_2026-07-02_to_2026-08-04": 1659.66,
                            "h2_2026-08-05_to_2026-09-02": 918.75},
    "sub_window_quarters": {"q1_2026-07-02_to_07-17": 527.01, "q2_2026-07-17_to_08-04": 1132.65,
                              "q3_2026-08-05_to_08-17": 1246.2,
                              "q4_most_recent_2026-08-18_to_09-02": -327.45},
    "g3_ex_best_trade": {"best_trade_delta": 431.25, "total": 2578.41,
                           "ex_best_total": 2147.16, "still_positive": True},
    "named_2026_09_02_770c_example": note_770c,
}
d["verdict_summary"] = summary
json.dump(d, open(path, "w", encoding="utf-8"), indent=2, default=str)
print("written")
print(json.dumps(summary, indent=2))

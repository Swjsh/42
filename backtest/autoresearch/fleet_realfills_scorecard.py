"""fleet_realfills_scorecard -- consolidate every watcher's real-fills verdict into ONE board.

Reads the real-fills artifacts in analysis/recommendations/, extracts per-trade EXPECTANCY
(OP-14: not WR), OOS per-trade, positive_quarters, top5-day concentration, and classifies
each WATCH_ONLY watcher against the OP-11 bar:

  CLEARS_OP11 : per-trade>0 AND OOS per-trade>0 AND positive_quarters>=4/6 AND top5<200 AND n>=20
  AWARENESS   : per-trade>0 but fails one of the above (regime-fragile / thin / concentrated)
  DEAD        : per-trade <= 0

Pure-Python, $0, no agents (throttle-proof). Writes analysis/recommendations/fleet-realfills-scorecard.json.
"""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / "analysis" / "recommendations"

# family -> artifact file. Prefer the FRESH (2026-06-20) artifacts; legacy (05-xx) tagged by run_date.
FLEET = {
    "vwap_continuation (LIVE)": "edgehunt-vwap_continuation.json",
    "double_bottom_base_quiet": "db-base-quiet-real-fills.json",
    "double_bottom_morning":    "db-morning-lowvol-real-fills.json",
    "double_top":               "double-top-real-fills.json",
    "hs_bear":                  "hs-bear-real-fills.json",
    "momentum_accel_highvol":   "momentum-accel-highvol-real-fills.json",
    "orb_retest":               "orb_real_fills.json",
    "bearish_rejection_morning":"edgehunt-bearish_rejection_morning.json",
    "confluence_structure":     "confluence-real-fills-fresh50.json",
    "nlwb":                     "nlwb_full_real_fills.json",
    "lbfs":                     "lbfs-expanded-real-fills.json",
    "bull_ribbon_reversal":     "bull_ribbon_reversal_real_fills.json",
    "v14_enhanced":             "v14_enhanced-real-fills.json",
    "v14e_ampm":                "v14e_ampm_real_fills.json",
    "orb_narrow":               "orb_narrow_or_real_fills.json",
    "fbw_morning_mid":          "fbw-morning-mid-real-fills.json",
}


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _top(d, keys):
    """First scalar match among top-level + common summary containers (avoids sweep cells)."""
    containers = [d]
    for c in ("overall", "summary", "headline_atm_chartstop", "baseline_default_cell", "result"):
        v = d.get(c) if isinstance(d, dict) else None
        if isinstance(v, dict):
            containers.append(v)
            if isinstance(v.get("metrics"), dict):
                containers.append(v["metrics"])
            if isinstance(v.get("report"), dict):
                containers.append(v["report"])
    for cont in containers:
        for k in keys:
            if isinstance(cont, dict) and _num(cont.get(k)) is not None:
                return _num(cont[k])
    return None


def _bfs(d, keys):
    q = deque([d])
    while q:
        cur = q.popleft()
        if isinstance(cur, dict):
            for k in keys:
                if _num(cur.get(k)) is not None:
                    return _num(cur[k])
            q.extend(v for v in cur.values() if isinstance(v, (dict, list)))
        elif isinstance(cur, list):
            q.extend(v for v in cur if isinstance(v, (dict, list)))
    return None


def _str_field(d, keys):
    for k in keys:
        v = d.get(k) if isinstance(d, dict) else None
        if isinstance(v, str):
            return v
    # nested
    for c in ("overall", "summary", "baseline_default_cell"):
        v = d.get(c) if isinstance(d, dict) else None
        if isinstance(v, dict):
            for k in keys:
                if isinstance(v.get(k), str):
                    return v[k]
    return None


def extract(d):
    pt = _top(d, ["avg_dollar_pnl_per_trade", "per_trade", "avg_pnl_per_trade", "baseline_default_per_trade", "avg_pnl", "exp_dollar"])
    if pt is None:
        pt = _bfs(d, ["avg_dollar_pnl_per_trade", "avg_pnl_per_trade", "baseline_default_per_trade", "per_trade"])
    n = _top(d, ["n_completed", "n_trades", "n", "completed", "n_observations", "total_signals", "n_signals_found"]) or _bfs(d, ["n_completed", "n_trades", "n_observations"])
    tot0 = _top(d, ["total_dollar_pnl", "total_pnl", "full_pnl", "total_pnl_3_contracts"]) or _bfs(d, ["total_pnl_3_contracts", "full_pnl"])
    if pt is None and tot0 is not None and n:
        pt = tot0 / n
    wr = _top(d, ["wr_real", "wr_pct", "wr"])
    if wr is not None and wr <= 1.5:
        wr *= 100  # normalize fraction -> pct
    total = _top(d, ["total_dollar_pnl", "total_pnl", "total_dollar", "total"])
    oos = None
    oos_blk = d.get("oos_2026") if isinstance(d.get("oos_2026"), dict) else (d.get("OOS_2026") if isinstance(d.get("OOS_2026"), dict) else None)
    if oos_blk:
        oos = _num(oos_blk.get("per_trade") or oos_blk.get("avg_pnl") or oos_blk.get("exp"))
    if oos is None:
        oos = _bfs(d, ["oos_exp", "oos_per_trade"])
    posq = _str_field(d, ["positive_quarters"])
    top5 = _top(d, ["top5_day_pct"]) or _bfs(d, ["top5_day_pct"])
    run_date = _str_field(d, ["run_date", "generated_at", "run_at"]) or "?"
    return {"per_trade": pt, "n": n, "wr": wr, "total": total, "oos_per_trade": oos,
            "positive_quarters": posq, "top5_day_pct": top5, "run_date": str(run_date)[:10]}


def classify(m):
    pt = m["per_trade"]
    if pt is None:
        return "NO_DATA", []
    if pt <= 0:
        return "DEAD", [f"per_trade=${pt:.0f}<=0"]
    flags = []
    # hard fails
    if m["oos_per_trade"] is not None and m["oos_per_trade"] <= 0:
        flags.append("OOS<=0")
    pq = m["positive_quarters"]
    if pq and "/" in pq:
        a, b = pq.split("/")[:2]
        if _num(a) is not None and _num(b) and _num(a) / _num(b) < 4 / 6 - 1e-9:
            flags.append(f"posQ={pq}")
    if m["top5_day_pct"] is not None and m["top5_day_pct"] >= 200:
        flags.append(f"top5={m['top5_day_pct']:.0f}%")
    if m["n"] is not None and m["n"] < 20:
        flags.append(f"n={m['n']:.0f}<20")
    # CLEARS requires the OP-11 evidence to be PRESENT and passing (absence != pass)
    unverified = []
    if m["oos_per_trade"] is None:
        unverified.append("OOS-unverified")
    if not pq:
        unverified.append("posQ-unverified")
    if m["top5_day_pct"] is None:
        unverified.append("conc-unverified")
    if flags:
        return "AWARENESS", flags + unverified
    if unverified:
        return "AWARENESS", unverified  # positive but OP-11 not fully verifiable from this artifact
    return "CLEARS_OP11", []


def main():
    board = {}
    print("=" * 110)
    print(f"{'WATCHER':28s} {'n':>5s} {'WR%':>6s} {'$/trade':>9s} {'OOS$/t':>8s} {'posQ':>6s} {'top5%':>7s}  {'VERDICT':12s} flags")
    print("=" * 110)
    for fam, fn in FLEET.items():
        f = ART / fn
        if not f.exists():
            board[fam] = {"verdict": "NO_ARTIFACT", "file": fn}
            print(f"{fam:28s} {'--':>5s}  (no artifact: {fn})")
            continue
        try:
            d = json.load(open(f, encoding="utf-8"))
        except Exception as e:
            board[fam] = {"verdict": "ERROR", "err": str(e)}
            continue
        m = extract(d)
        verdict, flags = classify(m)
        m["verdict"] = verdict
        m["flags"] = flags
        m["artifact"] = fn
        board[fam] = m
        pt = f"${m['per_trade']:.0f}" if m["per_trade"] is not None else "?"
        oos = f"${m['oos_per_trade']:.0f}" if m["oos_per_trade"] is not None else "-"
        wr = f"{m['wr']:.0f}" if m["wr"] is not None else "-"
        n = f"{m['n']:.0f}" if m["n"] is not None else "-"
        t5 = f"{m['top5_day_pct']:.0f}" if m["top5_day_pct"] is not None else "-"
        print(f"{fam:28s} {n:>5s} {wr:>6s} {pt:>9s} {oos:>8s} {str(m['positive_quarters'] or '-'):>6s} {t5:>7s}  {verdict:12s} {','.join(flags)}")

    out = {
        "generated": "2026-06-20",
        "op11_bar": "per_trade>0 AND OOS>0 AND posQ>=4/6 AND top5<200 AND n>=20",
        "authority": "real OPRA fills (C1); per-trade expectancy not WR (OP-14)",
        "summary": {
            "CLEARS_OP11": [k for k, v in board.items() if v.get("verdict") == "CLEARS_OP11"],
            "AWARENESS": [k for k, v in board.items() if v.get("verdict") == "AWARENESS"],
            "DEAD": [k for k, v in board.items() if v.get("verdict") == "DEAD"],
        },
        "board": board,
        "note": "Aggregated from per-family real-fills artifacts. DEFAULT config per family (not the swept "
                "best -- anti-pattern 2.10). Legacy artifacts tagged by run_date; re-run if a watcher changed.",
    }
    (ART / "fleet-realfills-scorecard.json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print("\nCLEARS_OP11:", out["summary"]["CLEARS_OP11"])
    print("AWARENESS  :", out["summary"]["AWARENESS"])
    print("DEAD       :", out["summary"]["DEAD"])
    print("-> analysis/recommendations/fleet-realfills-scorecard.json")


if __name__ == "__main__":
    main()

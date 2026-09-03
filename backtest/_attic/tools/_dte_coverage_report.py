"""B-FETCH coverage report: achievable FILLED n per directional family per DTE.

Reuses the EXACT snap logic the DTE sim uses (_nearest_cached_strike_dte, max_steps=4)
so the numbers match what simulate_dte_trade will actually fill. For each signal day T
and the signal side, at strike offsets ITM-2/0/OTM+2 (the band the sim sweeps), counts a
day as FILLABLE if any cached non-empty contract exists within the snap radius. Reports
total + OOS n per family per DTE so (A)/(B) know which families clear n>=20 OOS.

Pure python, $0. Read-only over the cache.
"""
from __future__ import annotations
import datetime as dt, json, sys
from pathlib import Path
import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from autoresearch._dte_expansion_sim import _nearest_cached_strike_dte, _expiry_for_entry  # noqa: E402
from lib.simulator_real import _strike_from_spot  # noqa: E402

SIG = Path(__file__).resolve().parent / "_dte_signal_days.json"
SPY_MASTER = REPO / "data" / "spy_5m_2025-01-01_2026-06-16.csv"
OOS_FRAC = 0.70
FAMS = ["momentum_morning", "orb_continuation", "power_hour", "vwap_pullback"]
# strike offsets in simulator convention (puts: atm-off, calls: atm+off; neg=ITM)
OFFSETS = {"ITM2": -2, "ATM": 0, "OTM2": 2}


def main() -> int:
    sig = json.loads(SIG.read_text())
    cal = sorted(pd.to_datetime(pd.read_csv(SPY_MASTER, usecols=["timestamp_et"])
                                ["timestamp_et"]).dt.date.unique())
    cut = cal[int(len(cal) * OOS_FRAC)]
    print(f"OOS cut = {cut}  (snap max_steps=4, offsets={OFFSETS})\n")
    hdr = f"{'family':18s} {'DTE':>3s} {'off':>5s} {'sigdays':>7s} {'fill_tot':>8s} {'fill_OOS':>8s} {'>=20OOS':>7s}"
    print(hdr)
    summary = {}
    for fam in FAMS:
        rows = sig.get(fam, [])
        for dte in (1, 2):
            for oname, off in OFFSETS.items():
                tot = oos = 0
                for r in rows:
                    d = dt.date.fromisoformat(r["date"])
                    if _expiry_for_entry(d, dte) is None:
                        continue
                    atm = int(r["atm"]); side = r["side"]
                    target = atm - off if side == "P" else atm + off
                    if _nearest_cached_strike_dte(d, target, side, dte) is not None:
                        tot += 1
                        if d >= cut:
                            oos += 1
                flag = "YES" if oos >= 20 else "no"
                print(f"{fam:18s} {dte:3d} {oname:>5s} {len(rows):7d} {tot:8d} {oos:8d} {flag:>7s}")
                summary[f"{fam}|{dte}DTE|{oname}"] = {"sigdays": len(rows),
                                                      "fill_total": tot, "fill_oos": oos}
        print()
    out = Path(__file__).resolve().parent / "_dte_coverage_report.json"
    out.write_text(json.dumps({"generated": dt.datetime.now().isoformat(),
                               "oos_cut": str(cut), "offsets": OFFSETS,
                               "coverage": summary}, indent=2))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

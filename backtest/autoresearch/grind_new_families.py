"""Driver: grind the 4 brand-NEW entry families through matrix -> funnel -> consolidation.

Families (genuinely-new ENTRIES, not strike/exit variations of the live ribbon-ride edge):
  supply_demand_zone, ema_adx, three_ducks, bollinger_squeeze  (see family_detectors.py).

Runs each family SEQUENTIALLY in one process (the OPRA cache is per-process; running
concurrent grind processes deadlocks on it — grind-reaper-killer scar). Pure Python, $0,
PROPOSE-ONLY. Markets-closed heavy compute.

Cross-family MULTIPLE-TESTING disclosure (C4 / OP-20 #5.2): every distinct setup that
reaches the null is one shot at a false positive. The more families x cells searched, the
higher the family-wise error rate -> a lone PASS-P4 among many shots needs a search-
corrected (DSR/Bonferroni) view before it means anything. This driver counts the shots and
states the corrected bar in the summary; NOTHING is flipped live on an in-sample search.

Run (foreground):  backtest/.venv/Scripts/python.exe -m autoresearch.grind_new_families
"""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_ROOT = _REPO.parent
for _p in (str(_REPO), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch import runner as ar                # noqa: E402
from autoresearch import family_detectors as fdet    # noqa: E402
from autoresearch import family_grind as fg          # noqa: E402

_RECO = _ROOT / "analysis" / "recommendations"
OUT = _RECO / "grind-new-families-summary.json"


def _log(msg: str) -> None:
    print(f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


def main() -> int:
    t0 = time.time()
    _log("loading SPY/VIX...")
    spy, vix = ar.load_data(fg.START, fg.END)
    rth = fdet.build_rth(spy)
    ndays = rth["date"].nunique()
    _log(f"RTH bars={len(rth)} trading_days={ndays}; grinding {len(fdet.FAMILIES)} families")

    summaries = []
    for family, fn in fdet.FAMILIES.items():
        ft = time.time()
        try:
            signals = fn(rth)
            sdays = len(set(s["date"] for s in signals))
            _log(f"[{family}] detected {len(signals)} signals on {sdays} days "
                 f"({100*sdays/ndays:.0f}% of days)")
            summ = fg.run_family(rth, family, signals, log=_log)
            summ["signal_day_pct"] = round(100 * sdays / ndays, 0)
            summ["elapsed_min"] = round((time.time() - ft) / 60, 1)
            summaries.append(summ)
        except Exception as e:  # noqa: BLE001 — record the failure loudly, never silently drop (C7)
            _log(f"[{family}] FAILED: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            summaries.append({"family": family, "error": f"{type(e).__name__}: {e}"})

    # ── cross-family multiple-testing accounting (C4) ─────────────────────────
    total_p3_shots = sum(s.get("p3_survivors", 0) for s in summaries if "error" not in s)
    total_p4 = sum(s.get("p4_elites", 0) for s in summaries if "error" not in s)
    # null_pass already requires beating the MAX of 10 random seeds (a stringent per-test
    # bar ~ p<=1/11 per shot under the null). Family-wise: with K independent shots the
    # chance >=1 false PASS-P4 is ~1-(1-p)^K. Bonferroni-style: a lone P4 among many shots
    # is suspect; demand a LARGE edge_over_null and forward-validation, never a flip.
    p_per_shot = 1.0 / (fg.N_NULL_SEEDS + 1)
    fwer = 1 - (1 - p_per_shot) ** max(1, total_p3_shots)

    summary = {
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "window": f"{fg.START}..{fg.END}",
        "families": [s["family"] for s in summaries],
        "per_family": summaries,
        "multiple_testing": {
            "null_shots_p3_survivors": total_p3_shots,
            "p4_elites_total": total_p4,
            "approx_p_per_shot": round(p_per_shot, 4),
            "approx_family_wise_false_positive_rate": round(fwer, 3),
            "interpretation": (
                "Each P3 survivor is one shot at beating the random-entry null MAX (~p=1/11 "
                "per shot). With this many shots a lone PASS-P4 can be search-luck; require a "
                "LARGE edge_over_null + forward paper-validation as a fleet challenger, NEVER "
                "an in-sample params flip (C4/OP-20, consolidate_elites caveat)."),
        },
        "authority": "real OPRA fills (C1); random-entry MATCHING-exit null (C3/L58/L171); "
                     "candidate-bar+null gate; edge_capture disclosed-only (vacuous for "
                     "non-J-anchor entries).",
        "elapsed_min": round((time.time() - t0) / 60, 1),
    }
    OUT.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    _log(f"ALL DONE in {summary['elapsed_min']} min. "
         f"P3-shots={total_p3_shots} P4-elites={total_p4} (FWER~{fwer:.2f}). wrote {OUT.name}")
    for s in summaries:
        if "error" in s:
            _log(f"  {s['family']:20s} ERROR {s['error']}")
        else:
            _log(f"  {s['family']:20s} P1cand={s.get('p1_candidate_cells')} "
                 f"P3={s.get('p3_survivors')} P4={s.get('p4_elites')} ({s.get('elapsed_min')}min)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

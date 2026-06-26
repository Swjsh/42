"""PHASE 5 — the deploy-grade gate. Hardens the funnel against the two real holes that
P4 (beat-the-null) does not close on its own:

  5a  NEIGHBORHOOD ROBUSTNESS (the multiple-testing antidote). We searched thousands of
      configs; the single luckiest will beat its own per-config null by chance. A REAL edge
      is a PLATEAU -- its adjacent-parameter neighbors (+-1 strike / stop / TP1 / sell-qty)
      also clear P4. An isolated spike with dead neighbors is an overfit artifact. Require a
      majority of a config's existing neighbors to also be P4 elites.

  5b  EVERY-QUARTER-POSITIVE (regime robustness). P2 only required qpf >= 0.60 (majority of
      quarters). Phase 5 requires qpf == 1.0 -- positive in EVERY calendar quarter, so the
      edge is not carried by one favorable regime window.

A config is a P5 SURVIVOR iff it passed P4 AND qpf == 1.0 AND its neighbor-pass-rate >= 0.5
(with >= MIN_NEIGHBORS real neighbors to judge). Pure read of the funnel outputs -- no
backtests, $0. Writes mass-grind-phase5.jsonl + a survivor summary; the dashboard /winners
view can show the P5 set as the deploy-grade tier.

Run after the funnel finishes:
    backtest/.venv/Scripts/python.exe -m autoresearch.mass_grind_phase5
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_ROOT = _REPO.parent
RECO = _ROOT / "analysis" / "recommendations"
OUT = RECO / "mass-grind-phase5.jsonl"
SUMMARY = RECO / "mass-grind-phase5-summary.json"

# Ordered parameter axes (must match mass_grind.py). Neighbor = +-1 index on a continuous axis.
STRIKE_OFFSETS = [6, 5, 4, 3, 2, 1, 0, -1, -2]                  # OTM-6 .. ITM-2 (so the grid grows OK)
STOP_VALS      = [-0.08, -0.12, -0.15, -0.20, -0.25, -0.30, -0.40, -0.50]
TP1_LEVELS     = [0.3, 0.5, 0.75, 1.0, 1.5]
TP1_QTY        = [0.5, 0.667, 0.8, 1.0]

MIN_NEIGHBORS = 3        # need at least this many real neighbors to judge a plateau
NEIGHBOR_PASS = 0.5      # >= half of existing neighbors must also be P4 elites
QPF_REQUIRED  = 1.0      # every quarter positive


def _key(combo) -> tuple:
    """Canonical combo identity (the 9-tuple as a hashable key)."""
    sk, so, blr, mt, stp, sv, tp, tq, lk = combo
    return (int(so), bool(blr), int(mt), round(float(sv), 4), round(float(tp), 4),
            round(float(tq), 4), str(lk))


def _load_p4_elites() -> dict:
    """label -> record, for every phase-4 elite across the funnel shard outputs."""
    elites = {}
    for f in glob.glob(str(RECO / "mass-grind-funnel-*.jsonl")):
        for line in Path(f).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("phase_reached") == 4 and r.get("combo"):
                elites[r["label"]] = r
    return elites


def _neighbors(combo) -> list[tuple]:
    """The +-1 neighbors on each continuous axis (strike, stop, TP1, sell-qty); blr/mt/lock fixed."""
    sk, so, blr, mt, stp, sv, tp, tq, lk = combo
    out = []
    for axis, vals, cur in (
        ("so", STRIKE_OFFSETS, int(so)),
        ("sv", STOP_VALS, round(float(sv), 4)),
        ("tp", TP1_LEVELS, round(float(tp), 4)),
        ("tq", TP1_QTY, round(float(tq), 4)),
    ):
        try:
            i = vals.index(cur)
        except ValueError:
            continue
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                nb = {"so": int(so), "sv": round(float(sv), 4), "tp": round(float(tp), 4), "tq": round(float(tq), 4)}
                nb[axis] = vals[j]
                out.append((nb["so"], bool(blr), int(mt), nb["sv"], nb["tp"], nb["tq"], str(lk)))
    return out


def main() -> int:
    elites = _load_p4_elites()
    if not elites:
        print("[phase5] no P4 elites found yet")
        return 1
    elite_keys = {_key(r["combo"]) for r in elites.values()}

    survivors, results = [], []
    for label, r in elites.items():
        combo = r["combo"]
        qpf = float(r.get("qpf") or 0.0)
        nbrs = _neighbors(combo)
        nbrs_present = [n for n in nbrs if n in elite_keys]
        rate = (len(nbrs_present) / len(nbrs)) if nbrs else 0.0
        plateau = len(nbrs) >= MIN_NEIGHBORS and rate >= NEIGHBOR_PASS
        every_q = qpf >= QPF_REQUIRED
        passed = plateau and every_q
        row = {
            "label": label,
            "combo": combo,
            "p5_pass": passed,
            "qpf": qpf,
            "every_quarter_positive": every_q,
            "neighbors_total": len(nbrs),
            "neighbors_elite": len(nbrs_present),
            "neighbor_pass_rate": round(rate, 3),
            "plateau": plateau,
            "expectancy": r.get("expectancy"),
            "edge_over_null": (r.get("p4_null") or {}).get("edge_over_null"),
            "edge_capture": r.get("edge_capture"),
        }
        results.append(row)
        if passed:
            survivors.append(row)

    survivors.sort(key=lambda x: -((x["edge_over_null"] or 0) * (x["qpf"] or 0)))
    OUT.write_text("\n".join(json.dumps(r) for r in results) + "\n", encoding="utf-8")
    SUMMARY.write_text(json.dumps({
        "generated": dt.datetime.now().isoformat(timespec="seconds"),
        "p4_elites": len(elites),
        "p5_survivors": len(survivors),
        "rule": f"P4 AND qpf=={QPF_REQUIRED} AND >={MIN_NEIGHBORS} neighbors with >={NEIGHBOR_PASS} elite-rate",
        "top_survivors": survivors[:15],
    }, indent=2), encoding="utf-8")

    print(f"[phase5] {len(elites)} P4 elites -> {len(survivors)} P5 deploy-grade survivors")
    for s in survivors[:5]:
        print(f"  {s['label']}  qpf={s['qpf']}  plateau={s['neighbors_elite']}/{s['neighbors_total']}  +${s['edge_over_null']} vs null")
    print(f"[phase5] wrote {OUT.name} + {SUMMARY.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

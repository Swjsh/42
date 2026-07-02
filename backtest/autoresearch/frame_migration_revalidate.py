"""DST frame migration re-validation — wall-v1 vs et-v2 diff harness.

The 2026-07-02 DST audit (markdown/audits/DST-FRAME-AUDIT-2026-07-02.md) found
the SPY master stores a fixed -04:00 offset year-round, so every wall-time
consumer evaluated EST-month (Nov-Mar) sessions truncated (last true hour
clipped) and +1h-labeled — 129 of 365 trading days in the master. Per the
no-silent-swap rule, NO params/wiring decision may rely on the corrected
("et-v2") frame until the validated baselines have been RE-RUN on it and the
diffs filed here.

  Stage 1 (cheap, pure pandas — minutes): re-run the 4 family DETECTORS on both
    frames; diff signal populations, cluster diffs by month (must concentrate
    Nov-Feb), report session-shape stats. Safe to run any time.
  Stage 2 (heavy, real OPRA fills — run AFTER-HOURS only, single process): re-sim
    the family-grind ELITE cells under both frames; diff n / expectancy / OOS /
    candidate-bar verdicts per cell. This is the evidence a re-wiring decision
    (e.g. WIRE-BOLLINGER) must cite before trusting et-v2 numbers.

Outputs: analysis/frame-migration/frame-revalidation-stage{N}-{date}.json

Usage:
    python autoresearch/frame_migration_revalidate.py --stage 1
    python autoresearch/frame_migration_revalidate.py --stage 2 --families bollinger_squeeze
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

_BACKTEST = Path(__file__).resolve().parents[1]
if str(_BACKTEST) not in sys.path:
    sys.path.insert(0, str(_BACKTEST))

from lib.et_frame import FRAME_ET_V2, FRAME_WALL_V1  # noqa: E402
from autoresearch import runner as ar                # noqa: E402
from autoresearch import family_detectors as fdet    # noqa: E402
from autoresearch import family_grind as fg          # noqa: E402

_ROOT = _BACKTEST.parent
OUT_DIR = _ROOT / "analysis" / "frame-migration"
FRAMES = (FRAME_WALL_V1, FRAME_ET_V2)


def _log(msg: str) -> None:
    print(f"{dt.datetime.now().strftime('%H:%M:%S')} {msg}", flush=True)


def _sig_key(s: dict) -> tuple:
    """Frame-independent-ish identity for clustering (date + side); times shift
    between frames by construction, so keys deliberately exclude time."""
    return (str(s["date"]), s["side"])


def stage1(start: dt.date, end: dt.date) -> dict:
    spy, _vix = ar.load_data(start, end)
    report: dict = {"stage": 1, "window": f"{start}..{end}",
                    "generated": dt.datetime.now().isoformat(timespec="seconds"),
                    "frames": {}, "families": {}}

    rth = {}
    for frame in FRAMES:
        f = fdet.build_rth(spy, frame=frame)
        rth[frame] = f
        days = f.groupby("date").size()
        report["frames"][frame] = {
            "rth_bars": int(len(f)),
            "trading_days": int(days.size),
            "days_66_bars": int((days == 66).sum()),
            "days_78_bars": int((days == 78).sum()),
            "first_bar_time_min": str(f["t"].min()),
        }

    for family, fn in fdet.FAMILIES.items():
        per: dict = {}
        sigs = {}
        for frame in FRAMES:
            s = fn(rth[frame])
            sigs[frame] = s
            per[frame] = {"signals": len(s),
                          "signal_days": len({x["date"] for x in s})}
        # month clustering of the DELTA (per C4 disclosure: diffs must sit Nov-Feb)
        cnt = {frame: Counter(str(x["date"])[:7] for x in sigs[frame]) for frame in FRAMES}
        months = sorted(set(cnt[FRAMES[0]]) | set(cnt[FRAMES[1]]))
        delta_by_month = {m: cnt[FRAME_ET_V2].get(m, 0) - cnt[FRAME_WALL_V1].get(m, 0)
                          for m in months}
        per["delta_signals"] = per[FRAME_ET_V2]["signals"] - per[FRAME_WALL_V1]["signals"]
        per["delta_by_month"] = {m: d for m, d in delta_by_month.items() if d != 0}
        report["families"][family] = per
        _log(f"[{family}] wall-v1={per[FRAME_WALL_V1]['signals']} "
             f"et-v2={per[FRAME_ET_V2]['signals']} delta={per['delta_signals']}")
    return report


def _cell_metrics(rth, signals, so, stop_pct, tp1, tq, trail, frame) -> dict:
    fills, m = fg.sim_cell(rth, signals, so, stop_pct, tp1, tq, trail, frame=frame)
    cb, reasons = fg.candidate_bar(m)
    keep = ("n", "exp", "total", "wr", "oos_n", "oos_exp", "oos_total", "qpf",
            "top5_day_pct", "no_data")
    return {"metrics": {k: m.get(k) for k in keep},
            "candidate_bar": cb, "fail_reasons": reasons}


def stage2(start: dt.date, end: dt.date, families: list[str]) -> dict:
    spy, _vix = ar.load_data(start, end)
    report: dict = {"stage": 2, "window": f"{start}..{end}",
                    "generated": dt.datetime.now().isoformat(timespec="seconds"),
                    "families": {}}
    rth = {frame: fdet.build_rth(spy, frame=frame) for frame in FRAMES}

    for family in families:
        grind_path = _ROOT / "analysis" / "recommendations" / f"family-grind-{family}.json"
        if not grind_path.exists():
            report["families"][family] = {"error": f"no grind baseline at {grind_path}"}
            _log(f"[{family}] SKIP — no baseline scorecard")
            continue
        baseline = json.loads(grind_path.read_text(encoding="utf-8"))
        elites = [c for c in baseline.get("cells", baseline.get("elites", []))
                  if str(c.get("verdict", c.get("p4", ""))).startswith("PASS")]
        if not elites:
            report["families"][family] = {"error": "no PASS cells in baseline"}
            _log(f"[{family}] SKIP — no PASS cells")
            continue
        fn = fdet.FAMILIES[family]
        cells_out = []
        for cell in elites:
            so = int(cell["strike_offset"]); stop_pct = float(cell["stop_pct"])
            tp1 = float(cell.get("tp1", 0.30)); tq = float(cell.get("tq", 0.667))
            trail = cell.get("trail")
            row = {"cell": cell.get("cell"), "strike_offset": so, "stop_pct": stop_pct,
                   "tp1": tp1, "tq": tq, "trail": trail, "by_frame": {}}
            for frame in FRAMES:
                signals = fn(rth[frame])
                row["by_frame"][frame] = _cell_metrics(
                    rth[frame], signals, so, stop_pct, tp1, tq, trail, frame)
            w = row["by_frame"][FRAME_WALL_V1]["metrics"]
            e = row["by_frame"][FRAME_ET_V2]["metrics"]
            row["delta"] = {k: (round(e[k] - w[k], 2)
                                if isinstance(e.get(k), (int, float)) and isinstance(w.get(k), (int, float))
                                else None)
                            for k in ("n", "exp", "total", "oos_exp", "oos_total")}
            row["survives_et_v2"] = row["by_frame"][FRAME_ET_V2]["candidate_bar"]
            cells_out.append(row)
            _log(f"[{family}] {row['cell']} wall n={w.get('n')} exp={w.get('exp')} | "
                 f"et-v2 n={e.get('n')} exp={e.get('exp')} | survives={row['survives_et_v2']}")
        report["families"][family] = {
            "elite_cells": len(cells_out),
            "cells_surviving_et_v2_candidate_bar": sum(1 for c in cells_out if c["survives_et_v2"]),
            "cells": cells_out,
        }
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--stage", type=int, choices=(1, 2), required=True)
    ap.add_argument("--start", type=dt.date.fromisoformat, default=fg.START)
    ap.add_argument("--end", type=dt.date.fromisoformat, default=fg.END)
    ap.add_argument("--families", nargs="*", default=list(fdet.FAMILIES.keys()))
    args = ap.parse_args()

    report = stage1(args.start, args.end) if args.stage == 1 else \
        stage2(args.start, args.end, args.families)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"frame-revalidation-stage{args.stage}-{dt.date.today().isoformat()}.json"
    out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    _log(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

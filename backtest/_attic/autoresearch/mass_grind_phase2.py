"""Phase 2 watcher — runs alongside mass_grind.py.

Polls mass-grind-progress.jsonl every 30s for new bangers (EC>=771, WF>=0.70).
For each new banger: re-runs the same combo to extract sub_window_stable +
quarter breakdown, then auto-registers to STRATEGY-SPACE-REGISTRY.jsonl if it
clears all four OP-11 gates:

    oos_positive AND wf >= 0.70 AND sub_window_stable AND ec >= 771

Writes detailed Phase 2 verdicts to mass-grind-phase2.jsonl (append-only).
Prints SHIP / HOLD-SOFT decisions live so you can watch without waiting for noon.

Run alongside the grind (separate terminal or background):
    backtest/.venv/Scripts/python.exe -m autoresearch.mass_grind_phase2
"""
from __future__ import annotations

import os
os.environ.setdefault("GAMMA_ENGINE_SCORE_ASSERT", "0")
os.environ.setdefault("GAMMA_RISK_GATE_ASSERT", "0")
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import copy
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

from autoresearch.strategy_space_grind import (  # noqa: E402
    L2_PATCH, OOS_BOUNDARY, START, END, PARAMS_PATH,
    run_cell, metrics_for,
)
from autoresearch.runner import load_data  # noqa: E402

_RECO    = _ROOT / "analysis" / "recommendations"
PROGRESS_GLOB = "mass-grind-progress*.jsonl"   # union across all parallel shards
PHASE2   = _RECO / "mass-grind-phase2.jsonl"
REG      = _ROOT / "analysis" / "backtests" / "STRATEGY-SPACE-REGISTRY.jsonl"
POLL_SEC = 30


def _progress_lines() -> list[str]:
    """All lines across every shard progress file."""
    out: list[str] = []
    for pf in sorted(_RECO.glob(PROGRESS_GLOB)):
        try:
            out.extend(pf.read_text(encoding="utf-8").splitlines())
        except Exception:
            pass
    return out

# OP-16 / OP-11 gates
EC_FLOOR = 771.0
WF_FLOOR = 0.70
QPF_FLOOR = 0.60   # quarter_positive_fraction for sub_window_stable


def _is_phase1_banger(r: dict) -> bool:
    ec = r.get("edge_capture")
    return (
        ec is not None
        and ec >= EC_FLOOR
        and (r.get("wf") or 0.0) >= WF_FLOOR
        and not r.get("op16_reject")
        and not r.get("error")
    )


def _load_done() -> set[str]:
    done: set[str] = set()
    if PHASE2.exists():
        for line in PHASE2.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if "label" in r:
                    done.add(r["label"])
            except Exception:
                pass
    return done


def _load_bangers() -> list[dict]:
    bangers = []
    for line in _progress_lines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
            if _is_phase1_banger(r):
                bangers.append(r)
        except Exception:
            pass
    return bangers


def _validate(r: dict, spy, vix, params: dict) -> dict:
    """Re-run the combo to get sub_window_stable + full quarterly detail."""
    combo = r["combo"]
    sk, so, blr, mt, stp, sv, tp, tq, lk = combo

    patch = dict(L2_PATCH)
    patch["block_level_rejection"] = bool(blr)
    patch["min_triggers_bear"] = int(mt)
    patch["min_triggers_bull"] = int(mt)
    patch["tp1_premium_pct"]   = float(tp)
    patch["tp1_qty_fraction"]  = float(tq)
    patch["profit_lock_mode"]  = lk

    trades = run_cell(spy, vix, params, strike_offset=int(so),
                      gate_patch=patch, stop_pct=float(sv))
    m = metrics_for(trades)
    val = m["_validation"]
    gate = val["gate"]
    qpf  = val.get("quarter_positive_fraction", 0.0)

    sub_window_stable = qpf >= QPF_FLOOR
    all_pass = (
        gate["oos_positive"]
        and gate["wf_ge_0.70"]
        and sub_window_stable
    )
    verdict = "SHIP" if all_pass else "HOLD-SOFT"

    return {
        "label":                r["label"],
        "combo":                combo,
        "verdict":              verdict,
        "edge_capture":         m["edge_capture"],
        "wf":                   m["wf"],
        "expectancy":           m["expectancy"],
        "n":                    m["n"],
        "wr":                   m["wr"],
        "max_dd":               m["max_dd"],
        "oos_positive":         gate["oos_positive"],
        "wf_ok":                gate["wf_ge_0.70"],
        "sub_window_stable":    sub_window_stable,
        "quarter_pos_fraction": round(qpf, 3),
        "quarters":             val.get("quarters", {}),
        "qty_frontier":         r.get("qty_frontier"),
        "validated_at":         dt.datetime.now().isoformat(timespec="seconds"),
    }


def _register(r2: dict) -> None:
    """Append a SHIP-grade banger to the strategy-space registry."""
    combo = r2["combo"]
    sk, so, blr, mt, stp, sv, tp, tq, lk = combo
    combo_id = (
        "p2_"
        + r2["label"]
        .replace(":", "_")
        .replace("%", "")
        .replace("+", "")
        .replace("-", "neg")
    )
    row = {
        "combo_id":  combo_id,
        "dims": {
            "structure":  "0DTE-single",
            "strike":     sk,
            "sizing":     "v15_tier",
            "direction":  "both",
            "gates":      f"LR{int(blr)}_mt{mt}",
            "exit":       f"sell{int(tq*100)}%@+{int(tp*100)}% {lk}",
            "conditions": "phase2-validated",
        },
        "result": {
            "edge_capture":         r2["edge_capture"],
            "expectancy":           r2["expectancy"],
            "wr":                   r2["wr"],
            "max_dd":               r2["max_dd"],
            "wf":                   r2["wf"],
            "n":                    r2["n"],
            "sub_window_stable":    r2["sub_window_stable"],
            "quarter_pos_fraction": r2["quarter_pos_fraction"],
        },
        "verdict":    "PROMOTE",
        "account":    None,
        "tested_at":  r2["validated_at"][:10],
        "source":     "mass-grind-phase2",
        "notes":      f"Phase-2 SHIP: {r2['label']} | qpf={r2['quarter_pos_fraction']}",
    }
    with open(REG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def main() -> None:
    print(f"[Phase 2] starting — polling {PROGRESS_GLOB} every {POLL_SEC}s", flush=True)
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8-sig"))
    print("[Phase 2] loading SPY/VIX data...", flush=True)
    spy, vix = load_data(START, END)
    print("[Phase 2] data loaded. Watching for bangers...", flush=True)

    while True:
        done = _load_done()
        bangers = _load_bangers()
        new = [b for b in bangers if b["label"] not in done]

        for b in new:
            print(f"[Phase 2] validating {b['label']}  EC={b['edge_capture']}  WF={b['wf']:.2f}", flush=True)
            try:
                r2 = _validate(b, spy, vix, params)
            except Exception as e:
                r2 = {"label": b["label"], "verdict": "ERROR", "error": str(e)[:200],
                      "validated_at": dt.datetime.now().isoformat(timespec="seconds")}

            with open(PHASE2, "a", encoding="utf-8") as f:
                f.write(json.dumps(r2) + "\n")

            verdict = r2.get("verdict", "ERROR")
            if verdict == "SHIP":
                _register(r2)
                print(
                    f"  --> SHIP  qpf={r2.get('quarter_pos_fraction')}  "
                    f"exp=${r2.get('expectancy',0):.0f}/tr  registered to dashboard",
                    flush=True,
                )
            else:
                print(
                    f"  --> {verdict}  "
                    f"qpf={r2.get('quarter_pos_fraction')}  "
                    f"sub_window_stable={r2.get('sub_window_stable')}",
                    flush=True,
                )

        total_done = len(_load_done())
        total_bangers = len(bangers)
        grind_lines = sum(1 for _ln in _progress_lines() if _ln.strip())
        print(
            f"[Phase 2] {grind_lines}/3360 grind combos  "
            f"{total_bangers} phase-1 bangers  "
            f"{total_done} phase-2 validated",
            flush=True,
        )

        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()

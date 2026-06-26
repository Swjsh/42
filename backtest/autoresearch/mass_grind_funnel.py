"""PROGRESSIVE VALIDATION FUNNEL — phases 2 -> 3 -> 4 over the mass_grind bangers.

Each phase-1 banger (EC>=771, WF>=0.70, no op16_reject) is pushed through progressively
STRICTER, more expensive gates. A config that survives all of them is genuinely robust,
not a lucky single-window / un-realizable / exit-structure artifact:

  P2  cross-quarter stability   : quarter_positive_fraction (qpf) >= 0.60
  P3  live-realizability + tight: qpf >= 0.75 AND the LIVE order gate actually admits it
                                  (qty_frontier safe2000_q5 real_exp > 0 AND admit_pct >= 0.5, per L180)
  P4  beat-the-null (ELITE)     : random-entry null_gate.null_pass  -- proves the edge is
                                  the SIGNAL, not the v15 exit bracket (C3/L58/L171). [wired in wave 2]

ONE re-run per banger feeds P2 + P3 (the realizability frontier comes from the same trades,
so P3 costs nothing extra). Only P3 survivors pay for P4's K random-entry null runs, so the
expensive test only ever touches the narrow tip of the funnel.

Sharded for parallel workers with ZERO shared-file contention: GAMMA_FUNNEL_SHARD /
GAMMA_FUNNEL_NSHARDS split the bangers by a stable md5 hash (process-independent, unlike
hash()), each worker writes its own mass-grind-funnel-<shard>.jsonl. Downstream readers
(dashboard) union mass-grind-funnel-*.jsonl.

Run (2 workers):
    GAMMA_FUNNEL_SHARD=0 GAMMA_FUNNEL_NSHARDS=2 python -m autoresearch.mass_grind_funnel
    GAMMA_FUNNEL_SHARD=1 GAMMA_FUNNEL_NSHARDS=2 python -m autoresearch.mass_grind_funnel
"""
from __future__ import annotations

import os
os.environ.setdefault("GAMMA_ENGINE_SCORE_ASSERT", "0")
os.environ.setdefault("GAMMA_RISK_GATE_ASSERT", "0")
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import datetime as dt
import hashlib
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
_ROOT = _REPO.parent
for _p in (str(_REPO), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch.strategy_space_grind import (  # noqa: E402
    L2_PATCH, START, END, PARAMS_PATH, run_cell, metrics_for,
)
from autoresearch.runner import load_data  # noqa: E402
from autoresearch.mass_grind import qty_realizability  # noqa: E402 — reuse the cap frontier
from autoresearch.null_baseline import random_entry_null, null_gate  # noqa: E402 — P4 beat-the-null

_RECO = _ROOT / "analysis" / "recommendations"
PROGRESS_GLOB = "mass-grind-progress*.jsonl"
REG = _ROOT / "analysis" / "backtests" / "STRATEGY-SPACE-REGISTRY.jsonl"
POLL_SEC = 30

# Sharding so N workers split the backlog with no shared-file writes.
SHARD = os.environ.get("GAMMA_FUNNEL_SHARD", "").strip()
NSHARDS = int(os.environ.get("GAMMA_FUNNEL_NSHARDS", "1"))
OUT = _RECO / (f"mass-grind-funnel-{SHARD}.jsonl" if SHARD else "mass-grind-funnel.jsonl")
FUNNEL_GLOB = "mass-grind-funnel-*.jsonl"

# Phase-1 banger floor (identical to mass_grind._is_banger)
EC_FLOOR = 771.0
WF_FLOOR = 0.70
# Progressive bars
QPF_P2 = 0.60          # cross-quarter stability
QPF_P3 = 0.75          # tighter cross-quarter stability
LIVE_QTY_KEY = "safe2000_q5"   # live Safe-2 base tier (5 contracts at $2K)
ADMIT_FLOOR = 0.50     # the live order gate must admit >= half the fills (L180)
# P4 beat-the-null
N_NULL_SEEDS = 10      # standard coin-flip seed count (null_baseline DEFAULT_SEEDS)
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)


def _stable_shard(label: str) -> int:
    return int(hashlib.md5(label.encode("utf-8")).hexdigest(), 16) % max(1, NSHARDS)


def _rth_frame(spy) -> "pd.DataFrame":
    """RTH-only frame with a reset RangeIndex + datetime timestamp_et, as the null
    harness expects. Built ONCE per process and reused for every banger's null."""
    ts = pd.to_datetime(spy["timestamp_et"])
    if getattr(ts.dt, "tz", None) is not None:
        ts = ts.dt.tz_localize(None)
    df = spy.copy()
    df["timestamp_et"] = ts
    times = ts.dt.time
    return df[(times >= RTH_OPEN) & (times < RTH_CLOSE)].reset_index(drop=True)


def _drop_top5_pt(trades) -> float:
    """Per-trade expectancy after removing the 5 best P&L DAYS (concentration robustness,
    the null_gate's drop-top5 input). Mirrors _b4_volume_profile_poc._drop_top5_per_trade."""
    by_day: dict = defaultdict(float)
    for t in trades:
        by_day[t.entry_time_et.date()] += float(t.dollar_pnl)
    top5 = {d for d, _ in sorted(by_day.items(), key=lambda kv: kv[1], reverse=True)[:5]}
    kept = [t for t in trades if t.entry_time_et.date() not in top5]
    if not kept:
        return 0.0
    return sum(float(t.dollar_pnl) for t in kept) / len(kept)


def _is_phase1_banger(r: dict) -> bool:
    ec = r.get("edge_capture")
    return (
        ec is not None and ec >= EC_FLOOR
        and (r.get("wf") or 0.0) >= WF_FLOOR
        and not r.get("op16_reject") and not r.get("error")
    )


def _load_done() -> set:
    done = set()
    for pf in sorted(_RECO.glob(FUNNEL_GLOB)):
        for line in pf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                if r.get("label"):
                    done.add(r["label"])
            except Exception:
                pass
    return done


def _load_my_bangers() -> list:
    """Phase-1 bangers from the grind union that belong to THIS shard."""
    out, seen = [], set()
    for pf in sorted(_RECO.glob(PROGRESS_GLOB)):
        for line in pf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            lbl = r.get("label")
            if not lbl or lbl in seen or not _is_phase1_banger(r):
                continue
            if NSHARDS > 1 and _stable_shard(lbl) != (int(SHARD) if SHARD.isdigit() else 0):
                continue
            seen.add(lbl)
            out.append(r)
    # Strongest-first: test the highest-edge_capture bangers earliest so the elite
    # PASS-P4 survivors surface first even if the full backlog isn't finished.
    out.sort(key=lambda r: -(r.get("edge_capture") or 0.0))
    return out


def _evaluate(banger: dict, spy, vix, params: dict, rth) -> dict:
    """One re-run feeds P2 (qpf) + P3 (realizability). Only P3 survivors pay for the
    P4 beat-the-null test (K random-entry runs) — the expensive tip of the funnel."""
    combo = banger["combo"]
    sk, so, blr, mt, stp, sv, tp, tq, lk = combo

    patch = dict(L2_PATCH)
    patch["block_level_rejection"] = bool(blr)
    patch["min_triggers_bear"] = int(mt)
    patch["min_triggers_bull"] = int(mt)
    patch["tp1_premium_pct"] = float(tp)
    patch["tp1_qty_fraction"] = float(tq)
    patch["profit_lock_mode"] = lk

    trades = run_cell(spy, vix, params, strike_offset=int(so), gate_patch=patch, stop_pct=float(sv))
    m = metrics_for(trades)
    val = m["_validation"]
    qpf = float(val.get("quarter_positive_fraction", 0.0))

    # P3 live realizability (does the LIVE order gate actually place this at the Safe-2 base tier?)
    frontier = qty_realizability(trades) if (m["edge_capture"] > 0 and m["n"] >= 20) else {}
    live = frontier.get(LIVE_QTY_KEY, {}) if frontier else {}
    live_exp = float(live.get("real_exp", 0.0))
    live_admit = float(live.get("admit_pct", 0.0))

    pass_p2 = qpf >= QPF_P2
    pass_p3 = pass_p2 and qpf >= QPF_P3 and live_exp > 0 and live_admit >= ADMIT_FLOOR

    # P4 — beat-the-null (C3/L58/L171): re-run the SAME #entries / call-put mix / strike /
    # stop at RANDOM RTH bars; the signal's per-trade must clear the null MAX, AND the
    # concentration-robust drop-top5 must clear the null MEAN. Only P3 survivors are tested.
    p4_null = None
    pass_p4 = False
    if pass_p3:
        n_call = sum(1 for t in trades if t.side == "C")
        n_put = sum(1 for t in trades if t.side == "P")
        drop5 = _drop_top5_pt(trades)
        null = random_entry_null(
            rth, n_signals=len(trades), n_call=n_call, n_put=n_put,
            strike_offset=int(so), premium_stop_pct=float(sv), seeds=N_NULL_SEEDS,
        )
        gate = null_gate(m["expectancy"], drop5, null)
        pass_p4 = bool(gate["null_pass"])
        p4_null = {
            "null_pass": pass_p4,
            "per_trade": round(float(m["expectancy"]), 2),
            "drop_top5_per_trade": round(drop5, 2),
            "null_mean": null.get("per_trade_mean"),
            "null_max": null.get("per_trade_max"),
            "edge_over_null": gate.get("edge_over_null_per_trade"),
            "beats_null_max": gate.get("beats_null_max"),
            "drop_top5_beats_null_mean": gate.get("drop_top5_beats_null_mean"),
            "seeds": N_NULL_SEEDS,
        }

    if not pass_p2:
        phase, verdict = 1, "STOP-P2"        # phase-1 banger that failed cross-quarter stability
    elif not pass_p3:
        phase, verdict = 2, "PASS-P2"        # robust across quarters, but not live-realizable / tight
    elif not pass_p4:
        phase, verdict = 3, "PASS-P3"        # robust + live-placeable, but an exit-structure artifact
    else:
        phase, verdict = 4, "PASS-P4"        # ELITE: beats the coin-flip null -> real signal alpha

    return {
        "label": banger["label"],
        "combo": combo,
        "phase_reached": phase,
        "verdict": verdict,
        "edge_capture": m["edge_capture"],
        "expectancy": m["expectancy"],
        "wr": m["wr"],
        "n": m["n"],
        "wf": m["wf"],
        "max_dd": m["max_dd"],
        "qpf": round(qpf, 3),
        "p2_pass": pass_p2,
        "p3_pass": pass_p3,
        "p4_pass": pass_p4,
        "live_real_exp": round(live_exp, 2),
        "live_admit_pct": round(live_admit, 3),
        "p4_null": p4_null,
        "evaluated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }


def _register(r: dict) -> None:
    """Register P3+ survivors to the strategy-space registry with their funnel tier."""
    combo = r["combo"]
    sk, so, blr, mt, stp, sv, tp, tq, lk = combo
    tier = {3: "P3-STRONG", 4: "P4-ELITE"}.get(r["phase_reached"], "P2")
    row = {
        "combo_id": "funnel_" + r["label"].replace(":", "_").replace("%", "").replace("+", "").replace("-", "neg"),
        "dims": {
            "structure": "0DTE-single", "strike": sk, "sizing": "v15_tier", "direction": "both",
            "gates": f"LR{int(blr)}_mt{mt}", "exit": f"sell{int(tq*100)}%@+{int(tp*100)}% {lk}",
            "conditions": f"funnel-{tier}",
        },
        "result": {
            "edge_capture": r["edge_capture"], "expectancy": r["expectancy"], "wr": r["wr"],
            "max_dd": r["max_dd"], "wf": r["wf"], "n": r["n"], "qpf": r["qpf"],
            "live_real_exp": r["live_real_exp"], "live_admit_pct": r["live_admit_pct"],
        },
        "verdict": "PROMOTE",
        "account": None, "tested_at": r["evaluated_at"][:10], "source": "mass-grind-funnel",
        "notes": f"Funnel {tier}: {r['label']} | qpf={r['qpf']} live_exp=${r['live_real_exp']}",
    }
    with open(REG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def main() -> None:
    tag = f"shard {SHARD}/{NSHARDS}" if SHARD else "single"
    print(f"[funnel {tag}] starting; polling {PROGRESS_GLOB} every {POLL_SEC}s", flush=True)
    params = json.loads(PARAMS_PATH.read_text(encoding="utf-8-sig"))
    print(f"[funnel {tag}] loading SPY/VIX...", flush=True)
    spy, vix = load_data(START, END)
    rth = _rth_frame(spy)   # built once; reused for every banger's P4 null
    print(f"[funnel {tag}] data loaded (rth bars={len(rth)}); watching for bangers", flush=True)

    def _grind_complete() -> bool:
        n = 0
        for pf in _RECO.glob(PROGRESS_GLOB):
            try:
                n += sum(1 for ln in pf.read_text(encoding="utf-8").splitlines() if ln.strip())
            except Exception:
                pass
        total = 3360
        try:
            total = int(json.loads((_RECO / "mass-grind-total.json").read_text(encoding="utf-8"))["total"])
        except Exception:
            pass
        return n >= total

    while True:
        done = _load_done()
        fresh = [b for b in _load_my_bangers() if b["label"] not in done]
        if not fresh and _grind_complete():
            print(f"[funnel {tag}] grind complete + no fresh bangers -> done ({len(done)} evaluated)", flush=True)
            break
        for b in fresh:
            try:
                r = _evaluate(b, spy, vix, params, rth)
            except Exception as e:  # noqa: BLE001 — record, never fabricate
                r = {"label": b["label"], "combo": b.get("combo"), "phase_reached": 0,
                     "verdict": "ERROR", "error": str(e)[:200],
                     "evaluated_at": dt.datetime.now().isoformat(timespec="seconds")}
            with open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(r) + "\n")
            if r.get("phase_reached", 0) >= 3:
                _register(r)
            nul = r.get("p4_null") or {}
            nstr = (f" null[exp=${nul.get('per_trade')} vs max=${nul.get('null_max')} "
                    f"-> {'BEATS' if nul.get('null_pass') else 'artifact'}]") if nul else ""
            print(f"[funnel {tag}] {r['label']} -> {r.get('verdict')} "
                  f"(qpf={r.get('qpf')} live_exp=${r.get('live_real_exp')}){nstr}", flush=True)

        total_done = len(_load_done())
        print(f"[funnel {tag}] {total_done} evaluated; sleeping {POLL_SEC}s", flush=True)
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()

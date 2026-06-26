"""PROGRESSIVE VALIDATION FUNNEL (vwap_continuation) — phases 2 -> 3 -> 4.

The vwap analog of ``mass_grind_funnel.py``. Each phase-1 survivor from
``mass_grind_vwap.py`` (OOS-positive, n>=20, WF>=0.70, qpf>=0.60 — the family-correct
floor; edge_capture is NOT gated here, see mass_grind_vwap docstring) is pushed through
progressively stricter gates:

  P2  cross-quarter stability    : qpf >= 0.60
  P3  live-realizability + tight : qpf >= 0.75 AND the LIVE order gate admits it at the
                                   Safe-2 base tier (qty_frontier safe2000_q5 real_exp > 0
                                   AND admit_pct >= 0.5, per L180)
  P4  beat-the-null + no-trunc   : fraud_gates.verify_candidate — the random-entry null MAX
       (ELITE)                     AND drop-top5 beats the null MEAN (C3/L58/L172) AND the
                                   sign does NOT invert at chart-stop-only -0.99 (L171). This
                                   is the SAME validated harness _sel_vwap_continuation uses;
                                   it is STRICTER than the ribbon funnel's null-only P4.

P2 + P3 read the qpf + qty_frontier the grind ALREADY recorded (same deterministic code,
same window — no re-sim needed). P4 re-simulates via verify_candidate, which isolates ENTRY
alpha from exit engineering: it re-runs the cell's SIGNALS at the chosen strike/stop with
DEFAULT v15 exits vs a random-entry null at the same strike/stop. Because that test depends
ONLY on (trigger, strike, stop) — not the exit knobs — P4 is computed ONCE per distinct
(trigger, strike_offset, premium_stop_pct) triple (<=84 total) and cached, so the funnel is
fast, single-process, and free of the multi-process OPRA-cache deadlock.

Writes mass-grind-vwap-funnel-<shard>.jsonl (sharded for parity; default single process).
Real OPRA fills only (C1). Pure Python, $0. PROPOSE-ONLY.

Run (single process, after the grind completes):
    backtest/.venv/Scripts/python.exe -m autoresearch.mass_grind_vwap_funnel
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
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_ROOT = _REPO.parent
for _p in (str(_REPO), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from autoresearch.fraud_gates import CandidateSignal, verify_candidate  # noqa: E402
from autoresearch.mass_grind_vwap import (  # noqa: E402
    PROGRESS_GLOB, TOTAL_COMBOS, TRIGGERS, _is_banger, build_data,
)
from autoresearch.strategy_space_grind import END, START  # noqa: E402

_RECO = _ROOT / "analysis" / "recommendations"
REG = _ROOT / "analysis" / "backtests" / "STRATEGY-SPACE-REGISTRY.jsonl"
POLL_SEC = 30

# Sharding parity (default single-process — deadlock-safe given the P4 (trig,so,sv) cache).
SHARD = os.environ.get("GAMMA_FUNNEL_SHARD", "").strip()
NSHARDS = int(os.environ.get("GAMMA_FUNNEL_NSHARDS", "1"))
OUT = _RECO / (f"mass-grind-vwap-funnel-{SHARD}.jsonl" if SHARD else "mass-grind-vwap-funnel.jsonl")
# NB: no dash before '*' so the union matches BOTH the single-process file
# (mass-grind-vwap-funnel.jsonl) AND sharded files (mass-grind-vwap-funnel-0.jsonl). A
# dash here ("...funnel-*.jsonl") silently misses the single-process file -> _load_done()
# can't see its own output -> the poll loop never terminates and rewrites duplicates.
FUNNEL_GLOB = "mass-grind-vwap-funnel*.jsonl"

# Progressive bars (identical thresholds to the ribbon funnel).
QPF_P2 = 0.60
QPF_P3 = 0.75
LIVE_QTY_KEY = "safe2000_q5"   # live Safe-2 base tier (5 contracts at $2K)
ADMIT_FLOOR = 0.50             # the live order gate must admit >= half the fills (L180)
N_NULL_SEEDS = 20              # fraud-gate standard (stronger than the ribbon funnel's 10)

RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)


def _stable_shard(label: str) -> int:
    return int(hashlib.md5(label.encode("utf-8")).hexdigest(), 16) % max(1, NSHARDS)


def _rth_frame(spy):
    """RTH-only frame with a reset RangeIndex (CandidateSignal.bar_idx + the null draw from
    it). spy is already tz-naive ET with a 't' time column (from _normalize_spy)."""
    return spy[(spy["t"] >= RTH_OPEN) & (spy["t"] < RTH_CLOSE)].reset_index(drop=True)


def _cand_signals(sigs_for_trig, spy, rth) -> list:
    """Map a trigger's detector signals (indexing the FULL spy frame) to CandidateSignals
    indexing the RTH frame (mirrors _sel_vwap_continuation)."""
    out = []
    for s in sigs_for_trig:
        ts = spy.iloc[s.bar_idx]["timestamp_et"]
        matches = rth.index[rth["timestamp_et"] == ts]
        if len(matches):
            out.append(CandidateSignal(bar_idx=int(matches[0]), side=s.side,
                                       rejection_level=float(s.stop_level),
                                       note=s.note or "jvwap"))
    return out


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
    """Phase-1 survivors from the grind union that belong to THIS shard, strongest first."""
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
            if not lbl or lbl in seen or not _is_banger(r):
                continue
            if NSHARDS > 1 and _stable_shard(lbl) != (int(SHARD) if SHARD.isdigit() else 0):
                continue
            seen.add(lbl)
            out.append(r)
    out.sort(key=lambda r: -(r.get("expectancy") or 0.0))
    return out


def _grind_complete() -> bool:
    n = 0
    for pf in _RECO.glob(PROGRESS_GLOB):
        try:
            n += sum(1 for ln in pf.read_text(encoding="utf-8").splitlines() if ln.strip())
        except Exception:
            pass
    return n >= TOTAL_COMBOS


def _evaluate(banger: dict, cand_by_trig: dict, rth, verify_cache: dict) -> dict:
    combo = banger["combo"]
    trig, bo, pv, sk, so, stop_label, sv, tp, tq, lk = combo

    qpf = float(banger.get("qpf") or 0.0)
    frontier = banger.get("qty_frontier") or {}
    live = frontier.get(LIVE_QTY_KEY, {}) if frontier else {}
    live_exp = float(live.get("real_exp", 0.0))
    live_admit = float(live.get("admit_pct", 0.0))

    pass_p2 = qpf >= QPF_P2
    pass_p3 = pass_p2 and qpf >= QPF_P3 and live_exp > 0 and live_admit >= ADMIT_FLOOR

    # P4 — beat-the-null + no-truncation. Depends ONLY on (trigger, strike, stop); cache it.
    p4_detail = None
    pass_p4 = False
    if pass_p3:
        key = (trig, int(so), float(sv))
        verdict = verify_cache.get(key)
        if verdict is None:
            verdict = verify_candidate(
                cand_by_trig[trig], rth, strike_offset=int(so), premium_stop_pct=float(sv),
                qty=3, setup="VWAP_FUNNEL", seeds=N_NULL_SEEDS)
            verify_cache[key] = verdict
        pass_p4 = bool(verdict.passes)
        nd = verdict.null or {}
        p4_detail = {
            "passes": pass_p4,
            "null_pass": verdict.null_pass,
            "no_truncation_pass": verdict.no_truncation_pass,
            "chosen_per_trade_default_exits": verdict.chosen_per_trade,
            "chart_stop_only_per_trade": verdict.chart_stop_only_per_trade,
            "null_mean": nd.get("per_trade_mean"),
            "null_max": nd.get("per_trade_max"),
            "edge_over_null": (verdict.null_gate or {}).get("edge_over_null_per_trade"),
            "combo_headline_expectancy": banger.get("expectancy"),
            "seeds": N_NULL_SEEDS,
            "note": ("P4 isolates ENTRY alpha: chosen re-sim uses DEFAULT v15 exits vs a "
                     "random-entry null at the same strike/stop; the combo's headline "
                     "expectancy (its specific exits) is disclosed separately."),
        }

    if not pass_p2:
        phase, verdict_s = 1, "STOP-P2"
    elif not pass_p3:
        phase, verdict_s = 2, "PASS-P2"
    elif not pass_p4:
        phase, verdict_s = 3, "PASS-P3"
    else:
        phase, verdict_s = 4, "PASS-P4"

    return {
        "label": banger["label"], "combo": combo, "family": "vwap_continuation",
        "phase_reached": phase, "verdict": verdict_s,
        "edge_capture": banger.get("edge_capture"), "expectancy": banger.get("expectancy"),
        "wr": banger.get("wr"), "n": banger.get("n"), "wf": banger.get("wf"),
        "max_dd": banger.get("max_dd"), "qpf": round(qpf, 3),
        "p2_pass": pass_p2, "p3_pass": pass_p3, "p4_pass": pass_p4,
        "live_real_exp": round(live_exp, 2), "live_admit_pct": round(live_admit, 3),
        "p4": p4_detail,
        "evaluated_at": dt.datetime.now().isoformat(timespec="seconds"),
    }


def _register(r: dict) -> None:
    combo = r["combo"]
    trig, bo, pv, sk, so, stop_label, sv, tp, tq, lk = combo
    tier = {3: "P3-STRONG", 4: "P4-ELITE"}.get(r["phase_reached"], "P2")
    row = {
        "combo_id": "funnelvwap_" + r["label"].replace(":", "_").replace("%", "").replace("+", "").replace("-", "neg"),
        "dims": {
            "structure": "0DTE-single", "family": "vwap_continuation", "strike": sk,
            "sizing": "v15_tier", "direction": "both", "gates": f"trig_{trig}",
            "exit": f"sell{int(tq * 100)}%@+{int(tp * 100)}% {lk}", "conditions": f"funnel-{tier}",
        },
        "result": {
            "edge_capture": r["edge_capture"], "expectancy": r["expectancy"], "wr": r["wr"],
            "max_dd": r["max_dd"], "wf": r["wf"], "n": r["n"], "qpf": r["qpf"],
            "live_real_exp": r["live_real_exp"], "live_admit_pct": r["live_admit_pct"],
        },
        "verdict": "PROMOTE", "account": None, "tested_at": r["evaluated_at"][:10],
        "source": "mass-grind-vwap-funnel",
        "notes": f"Funnel {tier}: {r['label']} | qpf={r['qpf']} live_exp=${r['live_real_exp']}",
    }
    with open(REG, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def main() -> None:
    tag = f"shard {SHARD}/{NSHARDS}" if SHARD else "single"
    print(f"[vwap-funnel {tag}] loading data + detecting signals (once) ...", flush=True)
    spy, vix, ribbon, sigs = build_data()
    rth = _rth_frame(spy)
    cand_by_trig = {trig: _cand_signals(sigs[trig], spy, rth) for trig, _b, _p in TRIGGERS}
    for trig in cand_by_trig:
        print(f"[vwap-funnel {tag}] trigger {trig}: {len(cand_by_trig[trig])} candidate signals "
              f"(rth bars={len(rth)})", flush=True)
    verify_cache: dict = {}

    while True:
        done = _load_done()
        fresh = [b for b in _load_my_bangers() if b["label"] not in done]
        if not fresh and _grind_complete():
            print(f"[vwap-funnel {tag}] grind complete + no fresh bangers -> done "
                  f"({len(done)} evaluated)", flush=True)
            break
        if not fresh:
            print(f"[vwap-funnel {tag}] no fresh bangers yet; grind incomplete; "
                  f"sleeping {POLL_SEC}s", flush=True)
            time.sleep(POLL_SEC)
            continue
        for b in fresh:
            try:
                r = _evaluate(b, cand_by_trig, rth, verify_cache)
            except Exception as e:  # noqa: BLE001 — record, never fabricate (C7)
                r = {"label": b["label"], "combo": b.get("combo"), "family": "vwap_continuation",
                     "phase_reached": 0, "verdict": "ERROR", "error": str(e)[:200],
                     "evaluated_at": dt.datetime.now().isoformat(timespec="seconds")}
            with open(OUT, "a", encoding="utf-8") as f:
                f.write(json.dumps(r, default=str) + "\n")
            if r.get("phase_reached", 0) >= 3:
                _register(r)
            p4 = r.get("p4") or {}
            nstr = (f" null[chosen=${p4.get('chosen_per_trade_default_exits')} vs "
                    f"max=${p4.get('null_max')} trunc_ok={p4.get('no_truncation_pass')} "
                    f"-> {'ELITE' if p4.get('passes') else 'artifact'}]") if p4 else ""
            print(f"[vwap-funnel {tag}] {r['label']} -> {r.get('verdict')} "
                  f"(qpf={r.get('qpf')} live_exp=${r.get('live_real_exp')}){nstr}", flush=True)
        print(f"[vwap-funnel {tag}] {len(_load_done())} evaluated; "
              f"{len(verify_cache)} distinct (trig,strike,stop) P4s cached", flush=True)
        if not _grind_complete():
            time.sleep(POLL_SEC)

    print(f"[vwap-funnel {tag}] DONE.", flush=True)


if __name__ == "__main__":
    main()

"""MASS GRIND (vwap_continuation) — a SECOND strategy family for the strategy table.

The ribbon ``mass_grind.py`` grinds BEARISH_REJECTION_RIDE_THE_RIBBON through the
orchestrator ``run_cell`` path. ``vwap_continuation`` is a DIFFERENT setup with a
DIFFERENT, validated backtest path: the standalone detector
``_edgehunt_vwap_continuation.detect_signals`` (byte-for-byte the live
``vwap_continuation_watcher`` port) + per-signal real OPRA fills via
``lib.simulator_real.simulate_trade_real``. This module grinds vwap_continuation's
trigger x strike x stop x exit matrix the SAME WAY, writing to its OWN progress files
(``mass-grind-vwap-progress*.jsonl``) so it never collides with the ribbon table.

REUSE (no rebuild, no drift on the load-bearing parts):
  * detector            : _edgehunt_vwap_continuation.detect_signals (== live watcher)
  * strike snap + fills : infinite_ammo_discovery._strike_from_spot / _nearest_cached_strike
                          + lib.simulator_real.simulate_trade_real (real OPRA, C1)
  * metric bundle       : strategy_space_grind.metrics_for + mass_grind.qty_realizability
                          (byte-identical columns to the ribbon table -> directly comparable)

The ONE knob ``_edgehunt_vwap_continuation.simulate_cell`` omits — ``tp1_qty_fraction``
(the scale-out fraction, J's "various scale outs" axis) — is passed through a thin local
cell-sim (``_simulate_cell_vwap``). Every other piece is imported; the detector + fill
mechanics are untouched. ``_simulate_cell_vwap`` emits rows that ``metrics_for`` consumes
directly (no shim), so the OP-16 edge_capture / WF / qpf math is identical to the ribbon.

MATRIX (mirrors the ribbon's 3,360-cell shape):
    trigger(4) x strike(7) x stop(3) x tp1(5) x tp1_qty(4) x lock(2) = 3,360
    trigger = breakout_only{F,T} x put_needs_rising_vix{F,T}  (vwap's entry-looseness axis,
              the analog of the ribbon's block_level_rejection{F,T} x min_triggers{1,2})

EXITS are live-faithful: lock="trailing" reproduces the LIVE v15 chandelier
(threshold +5%, trail 12.5% off HWM); lock="fixed" arms at +5% and locks break-even with
no trail; runner target fixed at the v15 2.5x. So the current live vwap exit IS a grid cell.

PHASE-1 banger floor for THIS family (NOT the ribbon's edge_capture>=771): vwap_continuation
is a bull-tilted continuation edge, NOT one of J's bearish-rejection ANCHOR trades, so OP-16
edge_capture (which measures J's specific anchor-day capture, C24/OP-16) is the WRONG gate
here. edge_capture is still COMPUTED + recorded for disclosure/parity, but the phase-1 bar
is the honest edge-hunt bar the validated vwap research already uses:
    OOS per-trade > 0  AND  n >= 20  AND  WF >= 0.70  AND  qpf >= 0.60.
The funnel (``mass_grind_vwap_funnel.py``) then applies P2/P3/P4 (qpf -> live-realizability
-> beat-the-random-entry-null MAX + drop-top5 + no-truncation, C3/L58/L171/L172).

PROPOSE-ONLY: never edits params.json. Real OPRA fills only (C1). Pure Python, $0.
Run (8 workers, SINGLE process — do NOT shard into multiple processes; concurrent grind
processes deadlock on the OPRA cache, see CLAUDE.md grind-reaper lesson):
    GAMMA_GRIND_WORKERS=8 backtest/.venv/Scripts/python.exe -m autoresearch.mass_grind_vwap
  Single-cell smoke (also asserts fixed != trailing — C14 vary-and-assert):
    backtest/.venv/Scripts/python.exe -m autoresearch.mass_grind_vwap --smoke
"""
from __future__ import annotations

import os

# CPU-bound multiprocessing: one math thread per worker (avoid BLAS oversubscription).
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
# Fast exploratory pass (the per-bar engine-score parity oracle is moot here — we never
# touch the orchestrator score path; this just keeps imported modules cheap if they read it).
os.environ.setdefault("GAMMA_ENGINE_SCORE_ASSERT", "0")

import argparse
import datetime as dt
import json
import multiprocessing as mp
import pickle
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parent.parent     # backtest/
_ROOT = _REPO.parent                               # repo root
for _p in (str(_REPO), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# §6.1 BACKTESTING-PLAYBOOK: spawn pythonw workers on Windows so the Pool never flashes a
# console window (J pain-point: "don't disturb user"). Must run before any Pool().
if sys.platform == "win32":
    # L41/C8: hardcode the SYSTEM pythonw (never Path(sys.executable).parent — under an old
    # daemon that resolves to a venv stub that re-execs a visible console; recurred 5x).
    _pw = Path(r"C:\Users\jackw\AppData\Local\Programs\Python\Python313\pythonw.exe")
    if _pw.exists():
        try:
            mp.set_executable(str(_pw))
        except RuntimeError:
            pass

# Validated detector + fill helpers (byte-for-byte the live vwap_continuation_watcher port).
from autoresearch._edgehunt_vwap_continuation import (  # noqa: E402
    MAX_STRIKE_STEPS,
    QTY,
    _align_vix,
    _normalize_spy,
    detect_signals,
)
from autoresearch.infinite_ammo_discovery import (  # noqa: E402
    _nearest_cached_strike,
    _strike_from_spot,
    build_day_contexts,
)
from autoresearch.mass_grind import qty_realizability  # noqa: E402 — reuse the cap frontier
from autoresearch.runner import load_data  # noqa: E402
from autoresearch.strategy_space_grind import (  # noqa: E402
    END,
    OOS_BOUNDARY,
    START,
    metrics_for,
)
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

_RECO = _ROOT / "analysis" / "recommendations"

# --- Sharding parity with mass_grind (default single-process for the OPRA-cache-safe run) -
_SHARD = os.environ.get("GAMMA_GRIND_SHARD", "").strip()
PROGRESS = _RECO / (f"mass-grind-vwap-progress-{_SHARD}.jsonl" if _SHARD
                    else "mass-grind-vwap-progress.jsonl")
PROGRESS_GLOB = "mass-grind-vwap-progress*.jsonl"   # union for resume + funnel + dashboard
OUT = _RECO / (f"mass-grind-vwap-{_SHARD}.json" if _SHARD else "mass-grind-vwap.json")
REG = _ROOT / "analysis" / "backtests" / "STRATEGY-SPACE-REGISTRY.jsonl"

WORKERS = int(os.environ.get("GAMMA_GRIND_WORKERS", "8"))

# ---- THE FULL MATRIX (mirrors the ribbon 3,360-cell shape) ----
# trigger = the vwap detector's entry-looseness axis (analog of ribbon block_lr x min_trig).
TRIGGERS: list[tuple[str, bool, bool]] = [
    ("bk0vx0", False, False),  # all entries (breakout OR pullback), no VIX gate  [== headline edge-hunt cell]
    ("bk1vx0", True, False),   # breakout-only
    ("bk0vx1", False, True),   # all entries, puts require rising VIX
    ("bk1vx1", True, True),    # breakout-only + puts require rising VIX
]
# strike_offset SIMULATOR convention: NEGATIVE = ITM, 0 = ATM, POSITIVE = OTM (verified in
# simulator_real.py L357-364 + the edge-hunt header; identical to the ribbon grind's axis).
STRIKES: dict[str, int] = {"OTM-4": 4, "OTM-3": 3, "OTM-2": 2, "OTM-1": 1,
                           "ATM": 0, "ITM-1": -1, "ITM-2": -2}            # 7
STOPS: dict[str, float] = {"-8": -0.08, "-20": -0.20, "-50": -0.50}       # 3
TP1_LEVELS = [0.3, 0.5, 0.75, 1.0, 1.5]                                   # 5 — sell at +30%..+150%
TP1_QTY = [0.5, 0.667, 0.8, 1.0]                                          # 4 — sell 50%..100% (1.0 = no runner)
LOCK = ["fixed", "trailing"]                                             # 2 — runner: fixed vs live chandelier
# = 4 x 7 x 3 x 5 x 4 x 2 = 3,360 combos
TOTAL_COMBOS = len(TRIGGERS) * len(STRIKES) * len(STOPS) * len(TP1_LEVELS) * len(TP1_QTY) * len(LOCK)

# ---- LIVE-FAITHFUL exit constants (params.json v15) — non-swept exit knobs ----
RUNNER_TGT = 2.5            # v15 runner target premium pct (CLAUDE.md "runner target 2.5x")
PL_THRESHOLD = 0.05         # v15_profit_lock_threshold_pct — arm at +5% favorable
PL_OFFSET = 0.0             # lock at break-even when armed
TRAIL_PCT = 0.125           # v15_profit_lock_trail_pct — chandelier 12.5% off HWM (WP-6 live)

# Phase-1 floor for THIS family (see module docstring — NOT the ribbon's edge_capture>=771).
N_FLOOR = 20
WF_FLOOR = 0.70
QPF_FLOOR = 0.60


@dataclass(frozen=True)
class _VTrade:
    """One real-fills vwap_continuation trade, shaped so strategy_space_grind.metrics_for
    and mass_grind.qty_realizability consume it DIRECTLY (no shim). Immutable per coding-style.
    """
    dollar_pnl: float
    entry_time_et: object   # tz-naive pandas Timestamp / datetime (metrics_for handles both)
    setup: str              # contains "BULLISH" for calls so _summ's bull/bear split is correct
    side: str               # "C" / "P"
    qty: int
    entry_premium: float
    exit_reason: str


def _label(combo: tuple) -> str:
    trig, bo, pv, sk, so, stop_label, sv, tp, tq, lk = combo
    return f"{trig}:{sk}:stop{stop_label}:tp+{int(tp * 100)}%:sell{int(tq * 100)}%:{lk}"


def _combos() -> list:
    out = []
    for (trig, bo, pv) in TRIGGERS:
        for sk, so in STRIKES.items():
            for stop_label, sv in STOPS.items():
                for tp in TP1_LEVELS:
                    for tq in TP1_QTY:
                        for lk in LOCK:
                            out.append((trig, bo, pv, sk, so, stop_label, sv, tp, tq, lk))
    return out


def build_data() -> tuple:
    """Load + normalize SPY/VIX, build day contexts + ribbon, and detect the vwap signal
    list ONCE per trigger combo. Returns (spy, vix, ribbon, signals_by_trig).

    Detection depends ONLY on the trigger combo (breakout_only, put_needs_rising_vix), so
    the 4 lists are computed once and reused across every strike/stop/exit cell."""
    spy_raw, vix_raw = load_data(START, END)
    spy = _normalize_spy(spy_raw)
    vix = _align_vix(spy, vix_raw)
    days = build_day_contexts(spy)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    signals_by_trig: dict[str, list] = {}
    for (trig, bo, pv) in TRIGGERS:
        signals_by_trig[trig] = detect_signals(
            days, vix, breakout_only=bo, put_needs_rising_vix=pv)
    return spy, vix, ribbon, signals_by_trig


def _simulate_cell_vwap(signals, spy, ribbon, vix, *, strike_offset: int,
                        premium_stop_pct: float, tp1_premium_pct: float,
                        tp1_qty_fraction: float, lock: str) -> list:
    """Faithful extension of _edgehunt_vwap_continuation.simulate_cell that ALSO sweeps
    tp1_qty_fraction (the scale-out fraction) and emits metrics_for-ready _VTrade rows.

    Strike resolution + fill mechanics are imported byte-for-byte (nearest-cached snap +
    simulate_trade_real on real OPRA). Exits are live-faithful: lock="trailing" == the v15
    chandelier (arm +5%, trail 12.5% off HWM); lock="fixed" arms +5% locks BE, no trail.
    """
    trailing = lock == "trailing"
    rows: list = []
    for sg in signals:
        bar = spy.iloc[sg.bar_idx]
        d = bar["timestamp_et"].date()
        spot = float(bar["close"])
        atm = _strike_from_spot(spot)
        target = atm - strike_offset if sg.side == "P" else atm + strike_offset
        strike = _nearest_cached_strike(d, target, sg.side, MAX_STRIKE_STEPS)
        if strike is None:
            continue
        entry_vix = float(vix.iloc[sg.bar_idx]) if sg.bar_idx < len(vix) else 0.0
        setup = "VWAP_CONT_BULLISH" if sg.side == "C" else "VWAP_CONT_BEARISH"
        fill = simulate_trade_real(
            entry_bar_idx=sg.bar_idx, entry_bar=bar, spy_df=spy, ribbon_df=ribbon,
            rejection_level=sg.stop_level, triggers_fired=[sg.note or "jvwap"], side=sg.side,
            qty=QTY, setup=setup, strike_override=strike, entry_vix=entry_vix,
            premium_stop_pct=premium_stop_pct,
            tp1_premium_pct=tp1_premium_pct,
            tp1_qty_fraction=tp1_qty_fraction,
            runner_target_premium_pct=RUNNER_TGT,
            profit_lock_threshold_pct=PL_THRESHOLD,
            profit_lock_stop_offset_pct=PL_OFFSET,
            profit_lock_mode=("trailing" if trailing else "fixed"),
            profit_lock_trail_pct=(TRAIL_PCT if trailing else 0.0),
        )
        if fill is None or fill.dollar_pnl is None:
            continue
        rows.append(_VTrade(
            dollar_pnl=float(fill.dollar_pnl), entry_time_et=bar["timestamp_et"],
            setup=setup, side=sg.side, qty=QTY, entry_premium=float(fill.entry_premium),
            exit_reason=(fill.exit_reason.name if fill.exit_reason else "NONE"),
        ))
    return rows


def cell_metrics(rows: list) -> dict:
    """The ribbon-identical metric bundle for one vwap cell, plus the qty cap frontier and
    the per-family phase-1 fields (oos_positive / qpf)."""
    m = metrics_for(rows)
    qf = qty_realizability(rows) if (m["n"] >= N_FLOOR and m["total"] != 0.0) else None
    return {
        "edge_capture": m["edge_capture"], "expectancy": m.get("expectancy"),
        "wr": m.get("wr"), "trades_per_day": m.get("trades_per_day"),
        "max_dd": m.get("max_dd"), "wf": m.get("wf"), "n": m["n"],
        "total": m.get("total"),
        "oos_positive": bool(m.get("oos_positive")),
        "qpf": m["_validation"].get("quarter_positive_fraction", 0.0),
        "op16_reject": m["rejected_by_op16"], "qty_frontier": qf,
    }


def _is_banger(r: dict) -> bool:
    """Phase-1 floor for vwap_continuation: OOS-positive, enough n, WF and cross-quarter
    stability. edge_capture is disclosed but NOT gated (it measures J's bearish anchors —
    the wrong axis for this bull-tilted continuation family; C24/OP-16)."""
    if r.get("error"):
        return False
    return (
        bool(r.get("oos_positive"))
        and (r.get("n") or 0) >= N_FLOOR
        and (r.get("wf") or 0.0) >= WF_FLOOR
        and (r.get("qpf") or 0.0) >= QPF_FLOOR
    )


# ---------------- worker plumbing (mirror mass_grind: pickle once, workers unpickle) -------
_SPY = _VIX = _RIBBON = _SIGS = None


def _init(cache_path: str) -> None:
    global _SPY, _VIX, _RIBBON, _SIGS
    spy, vix, ribbon, sigs = pickle.loads(Path(cache_path).read_bytes())
    _SPY, _VIX, _RIBBON, _SIGS = spy, vix, ribbon, sigs


def _run(combo: tuple) -> dict:
    trig, bo, pv, sk, so, stop_label, sv, tp, tq, lk = combo
    label = _label(combo)
    try:
        rows = _simulate_cell_vwap(
            _SIGS[trig], _SPY, _RIBBON, _VIX,
            strike_offset=int(so), premium_stop_pct=float(sv),
            tp1_premium_pct=float(tp), tp1_qty_fraction=float(tq), lock=lk)
        m = cell_metrics(rows)
    except Exception as e:  # noqa: BLE001 — record the failure, never fabricate a number (C7)
        return {"label": label, "combo": list(combo), "error": str(e)[:160]}
    return {"label": label, "combo": list(combo), **m}


# ---------------- single-cell smoke (fail fast + C14 vary-and-assert) ----------------------
def _smoke() -> int:
    print(f"[smoke] building data {START}..{END} (real OPRA fills) ...", flush=True)
    spy, vix, ribbon, sigs = build_data()
    for trig, _bo, _pv in TRIGGERS:
        n = len(sigs[trig])
        sig_days = len({spy.iloc[s.bar_idx]["timestamp_et"].date() for s in sigs[trig]})
        print(f"[smoke] trigger {trig}: {n} signals on {sig_days} days", flush=True)

    base = dict(strike_offset=-2, premium_stop_pct=-0.08, tp1_premium_pct=0.5,
                tp1_qty_fraction=0.667)
    rows_fixed = _simulate_cell_vwap(sigs["bk0vx0"], spy, ribbon, vix, lock="fixed", **base)
    rows_trail = _simulate_cell_vwap(sigs["bk0vx0"], spy, ribbon, vix, lock="trailing", **base)
    m_fixed = cell_metrics(rows_fixed)
    m_trail = cell_metrics(rows_trail)
    print(f"\n[smoke] cell ITM-2|stop-8|tp+50%|sell67% (trigger bk0vx0):", flush=True)
    print(f"  FIXED   : n={m_fixed['n']} exp=${m_fixed['expectancy']} wr={m_fixed['wr']} "
          f"wf={m_fixed['wf']} qpf={m_fixed['qpf']} oos+={m_fixed['oos_positive']} "
          f"EC={m_fixed['edge_capture']} total=${m_fixed['total']}", flush=True)
    print(f"  TRAILING: n={m_trail['n']} exp=${m_trail['expectancy']} wr={m_trail['wr']} "
          f"wf={m_trail['wf']} qpf={m_trail['qpf']} oos+={m_trail['oos_positive']} "
          f"EC={m_trail['edge_capture']} total=${m_trail['total']}", flush=True)

    # C14 vary-and-assert: the lock knob MUST move the number, else it is a dead knob.
    same_total = abs((m_fixed["total"] or 0) - (m_trail["total"] or 0)) < 1e-6
    if m_fixed["n"] == 0:
        print("[smoke] FAIL: zero fills — strike cache / detector wiring broken", flush=True)
        return 1
    if same_total:
        print("[smoke] FAIL: fixed == trailing total — lock knob is DEAD (C14)", flush=True)
        return 1
    print(f"\n[smoke] PASS: {len(_combos())} combos defined (expected {TOTAL_COMBOS}); "
          f"fixed!=trailing (lock binds); n>0 (fills land).", flush=True)
    return 0


# ---------------- the grind ----------------
def _load_done_union() -> set:
    done: set = set()
    for pf in sorted(_RECO.glob(PROGRESS_GLOB)):
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true",
                    help="Detect signals + run ONE cell fixed-vs-trailing + assert the lock "
                         "knob binds (C14). No full grind, no writes.")
    args = ap.parse_args()
    if args.smoke:
        return _smoke()

    combos = _combos()
    assert len(combos) == TOTAL_COMBOS, f"combo count {len(combos)} != {TOTAL_COMBOS}"

    # Resume from the union of all vwap progress files (this run + any prior/sibling shard).
    results: list[dict] = []
    bangers: list[dict] = []
    _my_labels = {_label(c) for c in combos}
    done_labels = set()
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
            if lbl:
                done_labels.add(lbl)
                if lbl in _my_labels:
                    results.append(r)
                    if _is_banger(r):
                        bangers.append(r)

    remaining = [c for c in combos if _label(c) not in done_labels]
    eta = len(remaining) * 8 / max(1, WORKERS) / 60
    print(f"MASS GRIND VWAP: {len(combos)} combos / {len(combos) - len(remaining)} done / "
          f"{len(remaining)} remaining ~= {eta:.0f} min (workers={WORKERS})", flush=True)

    print("Loading SPY/VIX + detecting vwap signals (once) ...", flush=True)
    spy, vix, ribbon, sigs = build_data()
    for trig, _bo, _pv in TRIGGERS:
        sd = len({spy.iloc[s.bar_idx]["timestamp_et"].date() for s in sigs[trig]})
        print(f"  trigger {trig}: {len(sigs[trig])} signals on {sd} days", flush=True)
    cache_f = tempfile.NamedTemporaryFile(suffix=".pkl", delete=False)
    cache_f.write(pickle.dumps((spy, vix, ribbon, sigs)))
    cache_f.close()
    cache_path = cache_f.name
    print(f"Data cached to {cache_path}", flush=True)

    t0 = time.time()
    # Self-healing pool loop: on any worker/pool crash, reload the done-union and restart
    # the pool for the remaining combos (mirrors mass_grind).
    while True:
        done_labels = _load_done_union()
        batch = [c for c in combos if _label(c) not in done_labels]
        if not batch:
            break
        print(f"Pool starting: {len(combos) - len(batch)} done / {len(batch)} remaining",
              flush=True)
        try:
            with mp.Pool(WORKERS, initializer=_init, initargs=(cache_path,)) as pool:
                for r in pool.imap_unordered(_run, batch):
                    results.append(r)
                    with open(PROGRESS, "a", encoding="utf-8") as f:
                        f.write(json.dumps(r) + "\n")
                    done_labels.add(r.get("label", ""))
                    if _is_banger(r):
                        bangers.append(r)
                        print(f"  [BANGER {len(done_labels)}/{len(combos)}] {r['label']}  "
                              f"exp=${r.get('expectancy')} wf={r.get('wf')} qpf={r.get('qpf')} "
                              f"oos+={r.get('oos_positive')} EC={r.get('edge_capture')}",
                              flush=True)
                    if len(done_labels) % 50 == 0:
                        print(f"  ...{len(done_labels)}/{len(combos)} "
                              f"({(time.time() - t0) / 60:.0f} min)", flush=True)
            break  # clean completion
        except Exception as e:  # noqa: BLE001
            print(f"Pool error ({type(e).__name__}: {e}) — reloading done set + restarting",
                  flush=True)

    try:
        Path(cache_path).unlink(missing_ok=True)
    except Exception:
        pass

    valid = [r for r in results if r.get("n") is not None and not r.get("error")]
    valid.sort(key=lambda r: -((r.get("expectancy") or 0.0) * (1.0 if r.get("oos_positive") else 0.0)))
    # de-dup (resume can append a label twice across runs)
    seen_lbl: set = set()
    uniq_bangers = []
    for r in bangers:
        if r["label"] not in seen_lbl:
            seen_lbl.add(r["label"])
            uniq_bangers.append(r)
    OUT.write_text(json.dumps({
        "family": "vwap_continuation",
        "ran_combos": len(combos), "valid": len(valid), "bangers": len(uniq_bangers),
        "elapsed_min": round((time.time() - t0) / 60, 1),
        "phase1_floor": {"oos_positive": True, "n_ge": N_FLOOR, "wf_ge": WF_FLOOR,
                         "qpf_ge": QPF_FLOOR,
                         "note": "edge_capture (OP-16, J bearish anchors) disclosed but NOT "
                                 "gated for this bull-tilted continuation family (C24/OP-16)"},
        "window": f"{START}..{END}", "oos_boundary": str(OOS_BOUNDARY),
        "exits": {"runner_target": RUNNER_TGT, "profit_lock_threshold": PL_THRESHOLD,
                  "trail_pct_trailing": TRAIL_PCT, "note": "live-faithful v15 chandelier"},
        "bangers_list": uniq_bangers[:50],
        "top25_by_oos_exp": valid[:25],
    }, indent=2, default=str), encoding="utf-8")

    # Append phase-1 survivors to the strategy-space registry tagged as the vwap family so
    # the dashboard /winners + strategy-space view show it DISTINCT from the ribbon table.
    try:
        # Registry is a curated dashboard view, not a dump: append only a TOP-N PREVIEW of
        # the phase-1 survivors (the funnel appends the validated P3/P4 rows). The phase-1
        # floor is deliberately loose, so this set can be thousands of cells — flooding the
        # shared registry. Cap to the strongest 25 by OOS-favorable expectancy.
        keep = sorted(uniq_bangers, key=lambda r: -((r.get("expectancy") or 0.0)))[:25]
        seen: set = set()
        with open(REG, "a", encoding="utf-8") as f:
            for r in keep:
                if r["label"] in seen:
                    continue
                seen.add(r["label"])
                c = r["combo"]
                f.write(json.dumps({
                    "combo_id": "massgrindvwap_" + r["label"].replace(":", "_").replace("%", "").replace("+", ""),
                    "dims": {"structure": "0DTE-single", "family": "vwap_continuation",
                             "strike": c[3], "sizing": "v15_tier", "direction": "both",
                             "gates": f"trig_{c[0]}",
                             "exit": f"sell{int(c[8] * 100)}%@+{int(c[7] * 100)}% {c[9]}",
                             "conditions": "vwap-matrix"},
                    "result": {"edge_capture": r.get("edge_capture"), "expectancy": r.get("expectancy"),
                               "wr": r.get("wr"), "max_dd": r.get("max_dd"), "wf": r.get("wf"),
                               "n": r.get("n"), "qpf": r.get("qpf")},
                    "verdict": "PHASE1" if _is_banger(r) else "HOLD",
                    "account": None, "tested_at": dt.date.today().isoformat(),
                    "source": "mass-grind-vwap",
                    "notes": f"vwap_continuation cell: {r['label']}",
                }) + "\n")
    except OSError:
        pass

    best = valid[0] if valid else None
    print(f"DONE. {len(uniq_bangers)} phase-1 survivors / {len(valid)} valid in "
          f"{(time.time() - t0) / 60:.0f} min. "
          f"Best by OOS exp: {best['label'] if best else 'none'} "
          f"exp=${best.get('expectancy') if best else '-'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

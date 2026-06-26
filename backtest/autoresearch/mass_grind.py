"""MASS GRIND — parallel brute-force of the scale-out neighbourhood across all cores.

J 2026-06-24: "do 10 small contracts and do various scale outs ... spin up a bunch
of python to blow through the thousands of strategies." The backtest is pure Python
($0, no LLM) so it should pin every core.

Grid (the scale-out brainstorm around J's OTM-4 scalp idea, on the L2 edge-gate):
    strike  x  stop  x  tp1_premium_pct (sell level)  x  tp1_qty_fraction (how much)  x  profit_lock_mode

Each cell = one real-fills backtest over the full OPRA window (reusing
strategy_space_grind.run_cell + metrics_for so the OP-16 verdict ladder is identical).
Results stream to analysis/recommendations/mass-grind-progress.jsonl as they finish
(bangers print live); survivors are appended to the strategy-space registry at the end.

PROPOSE-ONLY: never edits params.json. Run:
    backtest/.venv/Scripts/python.exe -m autoresearch.mass_grind
"""
from __future__ import annotations

import os

# CPU-bound multiprocessing: one math thread per worker (avoid BLAS oversubscription).
for _v in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")
# Fast exploratory pass; survivors get an assert-on re-validation before any ship.
os.environ.setdefault("GAMMA_RISK_GATE_ASSERT", "0")
# VECTORIZE 2026-06-24: the per-bar engine-score parity oracle (re-runs every filter a
# 2nd time/bar just to assert two scorers agree) is the dominant cost — opt out for
# sweeps. Validated byte-identical (hash c9b7c82bce74250d); 73.4s -> 46.0s = 1.6x.
os.environ.setdefault("GAMMA_ENGINE_SCORE_ASSERT", "0")

import json
import sys
import time
import datetime as dt
import multiprocessing as mp
from pathlib import Path

_REPO = Path(__file__).resolve().parent.parent
_ROOT = _REPO.parent
for _p in (str(_REPO), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from lib.cap_admission import cap_allows  # noqa: E402 — post-hoc qty x cap admission

# qty as a swept dimension (post-hoc on each config's fills — P&L is linear in qty, so
# no re-run: cap_allows tells us which fills the LIVE gate admits at each (account, qty)).
QTY_SWEEP = [3, 5, 8, 10, 15]
QTY_ACCOUNTS = [("safe", 2000.0), ("bold", 1648.75), ("safe", 25000.0)]


def qty_realizability(trades) -> dict:
    """For each (account, qty): admit% (fills the live cap admits) + realizable per-trade
    expectancy (P&L scaled linearly from the fill's qty). The cap-realizability frontier."""
    out = {}
    n_tot = len(trades)
    for acct, eq in QTY_ACCOUNTS:
        for q in QTY_SWEEP:
            adm = [float(t.dollar_pnl) * (q / float(t.qty))
                   for t in trades
                   if float(t.qty) > 0 and cap_allows(acct, eq, q, float(t.entry_premium))]
            n = len(adm)
            out[f"{acct}{int(eq)}_q{q}"] = {
                "admit_pct": round(n / n_tot, 3) if n_tot else 0.0,
                "real_exp": round(sum(adm) / n, 2) if n else 0.0,
                "real_total": round(sum(adm), 2),
            }
    return out


_RECO = _ROOT / "analysis" / "recommendations"

# --- Sharding (run 3 strike-disjoint shards in parallel for speed + fault isolation) ---
# GAMMA_GRIND_SHARD: suffix for this shard's own progress file (e.g. "a"/"b"/"c").
#   Empty = single-process mode, writes the canonical mass-grind-progress.jsonl.
# GAMMA_GRIND_STRIKES: comma-separated strike names this shard owns (e.g. "OTM-2,OTM-1").
#   Empty = all strikes.
# GAMMA_GRIND_WORKERS: pool size for this shard (default 6).
# Resume reads the UNION of every mass-grind-progress*.jsonl so disjoint shards never
# re-run a combo another shard (or a prior run) already finished.
_SHARD = os.environ.get("GAMMA_GRIND_SHARD", "").strip()
_STRIKE_FILTER = [s.strip() for s in os.environ.get("GAMMA_GRIND_STRIKES", "").split(",") if s.strip()]

PROGRESS = _RECO / (f"mass-grind-progress-{_SHARD}.jsonl" if _SHARD else "mass-grind-progress.jsonl")
PROGRESS_GLOB = "mass-grind-progress*.jsonl"   # union for resume + dashboard
OUT = _RECO / (f"mass-grind-{_SHARD}.json" if _SHARD else "mass-grind.json")
REG = _ROOT / "analysis" / "backtests" / "STRATEGY-SPACE-REGISTRY.jsonl"

WORKERS = int(os.environ.get("GAMMA_GRIND_WORKERS", "6"))

# ---- THE FULL MATRIX (every key knob) — strike x gate x triggers x stop x exit-structure ----
_ALL_STRIKES = {"OTM-4": 4, "OTM-3": 3, "OTM-2": 2, "OTM-1": 1, "ATM": 0, "ITM-1": -1, "ITM-2": -2}  # 7
STRIKES = {k: v for k, v in _ALL_STRIKES.items() if not _STRIKE_FILTER or k in _STRIKE_FILTER}
BLOCK_LR = [True, False]                              # 2 — block_level_rejection (the proven edge gate)
MIN_TRIG = [1, 2]                                     # 2 — entry looseness (>=1 vs >=2 triggers)
# STOPS expanded 2026-06-25 (matrix deepening): finer granularity to MAP the stop curve.
# Winners cluster at -8/-20; the added -12/-15/-25/-30/-40 resolve the exact optimum + the
# wider-stop regime. Stop is a % of premium (no OPRA-cache dependency), so safe to refine.
STOPS = {"-8": -0.08, "-12": -0.12, "-15": -0.15, "-20": -0.20,
         "-25": -0.25, "-30": -0.30, "-40": -0.40, "-50": -0.50}    # 8 (was 3)
TP1_LEVELS = [0.3, 0.5, 0.75, 1.0, 1.5]              # 5 — sell at +30% .. +150%
TP1_QTY = [0.5, 0.667, 0.8, 1.0]                     # 4 — sell 50% .. 100% (1.0 = no runner = pure ride)
LOCK = ["fixed", "trailing"]                         # 2 — runner: fixed vs chandelier-trailing
# = 7 x 2 x 2 x 8 x 5 x 4 x 2 = 8960 combos (resume skips the original 3360)


def _label(combo: tuple) -> str:
    sk, so, blr, mt, stp, sv, tp, tq, lk = combo
    return f"{sk}:LR{int(blr)}:mt{mt}:stop{stp}:tp+{int(tp*100)}%:sell{int(tq*100)}%:{lk}"


def _combos() -> list:
    out = []
    for sk, so in STRIKES.items():
        for blr in BLOCK_LR:
            for mt in MIN_TRIG:
                for stp, sv in STOPS.items():
                    for tp in TP1_LEVELS:
                        for tq in TP1_QTY:
                            for lk in LOCK:
                                out.append((sk, so, blr, mt, stp, sv, tp, tq, lk))
    return out


_G = None
_SPY = None
_VIX = None
_PARAMS = None
_DATA_CACHE: Path | None = None


def _init(cache_path: str) -> None:
    # Workers load from a pre-serialized pickle — no concurrent Arrow/pandas I/O.
    # Root cause of repeated crashes: arrow.dll access violation (0xc0000005) when
    # 6+ workers simultaneously call load_data() during pool init.
    global _G, _SPY, _VIX, _PARAMS, _DATA_CACHE
    import pickle
    import autoresearch.strategy_space_grind as g
    _G = g
    _DATA_CACHE = Path(cache_path)
    spy_vix, params = pickle.loads(_DATA_CACHE.read_bytes())
    _SPY, _VIX = spy_vix
    _PARAMS = params


def _run(combo: tuple) -> dict:
    sk, so, blr, mt, stp, sv, tp, tq, lk = combo
    g = _G
    patch = dict(g.L2_PATCH)
    patch["block_level_rejection"] = blr
    patch["min_triggers_bear"] = mt
    patch["min_triggers_bull"] = mt
    patch.update({"tp1_premium_pct": tp, "tp1_qty_fraction": tq, "profit_lock_mode": lk})
    label = _label(combo)
    try:
        trades = g.run_cell(_SPY, _VIX, _PARAMS, strike_offset=so, gate_patch=patch, stop_pct=sv)
        m = g.metrics_for(trades)
        # qty x cap frontier — only for live (positive-edge, enough-n) configs; moot on the dead.
        qf = qty_realizability(trades) if (m["edge_capture"] > 0 and m["n"] >= 20) else None
    except Exception as e:  # noqa: BLE001 — record the failure, never fabricate a number
        return {"label": label, "combo": list(combo), "error": str(e)[:140]}
    return {
        "label": label, "combo": list(combo),
        "edge_capture": m["edge_capture"], "expectancy": m.get("expectancy"),
        "wr": m.get("wr"), "trades_per_day": m.get("trades_per_day"),
        "max_dd": m.get("max_dd"), "wf": m.get("wf"), "n": m["n"],
        "op16_reject": m["rejected_by_op16"], "qty_frontier": qf,
    }


def _is_banger(r: dict) -> bool:
    ec = r.get("edge_capture")
    return ec is not None and ec >= 771 and (r.get("wf") or 0) >= 0.70 and not r.get("op16_reject")


if __name__ == "__main__":
    combos = _combos()

    # Emit the live matrix total so the dashboard / watchdog / funnel track the real size
    # (the matrix grows when knobs are added — no more hardcoded 3360).
    if not _STRIKE_FILTER:   # only the full-matrix run owns the canonical total
        try:
            (_RECO / "mass-grind-total.json").write_text(
                json.dumps({"total": len(combos)}), encoding="utf-8")
        except OSError:
            pass

    # Resume: load already-completed results from the UNION of all shard progress files
    # so disjoint shards (and prior single-process runs) never re-run a finished combo.
    results: list[dict] = []
    bangers: list[dict] = []
    done_labels: set[str] = set()
    _my_labels = {_label(c) for c in combos}   # only this shard's strikes go into results
    for pf in sorted(_RECO.glob(PROGRESS_GLOB)):
        for line in pf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                lbl = r.get("label")
                if lbl:
                    done_labels.add(lbl)
                    if lbl in _my_labels:   # this shard owns it → keep for final summary
                        results.append(r)
                        if _is_banger(r):
                            bangers.append(r)
            except Exception:
                pass

    remaining = [c for c in combos if _label(c) not in done_labels]
    n_skip = len(combos) - len(remaining)
    eta = len(remaining) * 55 / WORKERS / 60
    print(
        f"MASS GRIND: {len(combos)} combos / {n_skip} already done / "
        f"{len(remaining)} remaining ~= {eta:.0f} min",
        flush=True,
    )

    # Pre-load data ONCE in main process, pickle to temp file.
    # Workers unpickle — eliminates concurrent Arrow I/O that causes arrow.dll crashes.
    import pickle
    import tempfile
    import autoresearch.strategy_space_grind as _g_mod
    from autoresearch.runner import load_data as _load_data
    print("Loading SPY/VIX data...", flush=True)
    _spy, _vix = _load_data(_g_mod.START, _g_mod.END)
    _params = json.load(open(_g_mod.PARAMS_PATH, encoding="utf-8"))
    _cache_f = tempfile.NamedTemporaryFile(suffix=".pkl", delete=False)
    _cache_f.write(pickle.dumps(((_spy, _vix), _params)))
    _cache_f.close()
    _cache_path = _cache_f.name
    print(f"Data cached to {_cache_path}", flush=True)

    t0 = time.time()
    # Self-healing pool loop: if a worker crashes (WorkerLostError or any pool error),
    # reload done_labels from the progress file and restart the pool for remaining combos.
    while True:
        # Reload done set from the UNION of all shard files (picks up results written
        # before any crash, by this shard or its siblings).
        done_labels = set()
        for _pf in sorted(_RECO.glob(PROGRESS_GLOB)):
            for _line in _pf.read_text(encoding="utf-8").splitlines():
                _line = _line.strip()
                if not _line:
                    continue
                try:
                    _r = json.loads(_line)
                    if _r.get("label"):
                        done_labels.add(_r["label"])
                except Exception:
                    pass
        batch = [c for c in combos if _label(c) not in done_labels]
        if not batch:
            break
        n_done = len(combos) - len(batch)
        print(f"Pool starting: {n_done} done / {len(batch)} remaining", flush=True)
        try:
            with mp.Pool(WORKERS, initializer=_init, initargs=(_cache_path,)) as pool:
                for r in pool.imap_unordered(_run, batch):
                    results.append(r)
                    with open(PROGRESS, "a", encoding="utf-8") as f:
                        f.write(json.dumps(r) + "\n")
                    done_labels.add(r.get("label", ""))
                    if _is_banger(r):
                        bangers.append(r)
                        print(
                            f"  [BANGER {len(done_labels)}/{len(combos)}] {r['label']}  "
                            f"EC={r['edge_capture']} wf={r['wf']} exp={r.get('expectancy')}",
                            flush=True,
                        )
                    if len(done_labels) % 25 == 0:
                        print(f"  ...{len(done_labels)}/{len(combos)} ({(time.time()-t0)/60:.0f} min)", flush=True)
            break  # clean completion
        except Exception as e:
            print(f"Pool error ({type(e).__name__}: {e}) — reloading done set and restarting pool", flush=True)

    # Clean up data cache
    try:
        Path(_cache_path).unlink(missing_ok=True)
    except Exception:
        pass

    valid = [r for r in results if r.get("edge_capture") is not None]
    valid.sort(key=lambda r: -(r["edge_capture"] * (r.get("expectancy") or 0)))
    OUT.write_text(json.dumps({
        "ran_combos": len(combos), "valid": len(valid), "bangers": len(bangers),
        "elapsed_min": round((time.time() - t0) / 60, 1),
        "promotes": bangers, "top25": valid[:25],
    }, indent=2), encoding="utf-8")

    # Append survivors (bangers + top-5 HOLDs) to the strategy-space registry for the dashboard.
    try:
        keep = bangers + [r for r in valid if not _is_banger(r)][:5]
        seen = set()
        with open(REG, "a", encoding="utf-8") as f:
            for r in keep:
                if r["label"] in seen:
                    continue
                seen.add(r["label"])
                f.write(json.dumps({
                    "combo_id": "massgrind_" + r["label"].replace(":", "_").replace("%", "").replace("+", ""),
                    "dims": {"structure": "0DTE-single", "strike": r["combo"][0], "sizing": "v15_tier",
                             "direction": "both", "gates": f"LR{int(r['combo'][2])}_mt{r['combo'][3]}",
                             "exit": f"sell{int(r['combo'][7]*100)}%@+{int(r['combo'][6]*100)}% {r['combo'][8]}", "conditions": "matrix"},
                    "result": {"edge_capture": r["edge_capture"], "expectancy": r.get("expectancy"),
                               "wr": r.get("wr"), "max_dd": r.get("max_dd"), "wf": r.get("wf"), "n": r.get("n")},
                    "verdict": "PROMOTE" if _is_banger(r) else "HOLD",
                    "account": None, "tested_at": "2026-06-24", "source": "mass-grind",
                    "notes": f"scale-out brainstorm cell: {r['label']}",
                }) + "\n")
    except OSError:
        pass

    print(f"DONE. {len(bangers)} bangers / {len(valid)} valid in {(time.time()-t0)/60:.0f} min. "
          f"Best: {valid[0]['label'] if valid else 'none'} EC={valid[0]['edge_capture'] if valid else '-'}", flush=True)

"""Phase C -- J-EDGE bull-family PORT confirmation study (2026-07-02, overnight).

> REAL OPRA FILLS (use_real_fills=True) -- the only P&L authority per C1.

Question: do the ENGINE'S OWN bull entries (BULLISH_RECLAIM_RIDE_THE_RIBBON,
production entry gates incl. per-direction block filters) carry the Phase-B
survivor exit family on 2025-26?

Phase-B family (analysis/j-webull/PHASEB-matrix/RESULTS.md, 6 BH-FDR survivors,
all one family): CALL entries + TP1 +30% sell 2/3 + breakeven runner +
chandelier (arm +5%, trail 15% off HWM) + 1 lot, ATM/OTM1, catastrophe stop
-20%/-50%, time-stop t60/t120/tEOD.

PRE-REGISTERED GRID (confirmation study, NO wider fishing):
the 6 surviving Phase-B cells x qty {1, 3} = 12 cells. qty1 is the exact
fractional 1/3 sibling of qty3 by construction (identical signal; Phase-B made
the same disclosure for fixed_3), so BH q-values are unchanged by the split.

Cells (stop, strike, time-stop):
  c1  stop-50  otm1  tEOD      c2  stop-50  atm  tEOD
  c3  stop-50  otm1  t120      c4  stop-50  atm  t120
  c5  stop-20  atm   t120      c6  stop-50  otm1 t60

PORT MECHANICS (wrapper around orchestrator.simulate_trade_real -- production
code untouched; same monkeypatch pattern as autoresearch.overnight_grinder):
  - entries: production engine, bull-only (min_triggers_bear=999 blocks bears)
  - exits swapped to the family: premium-only. Chart-level stop OFF
    (rejection_level=None), chart-level TP1 + level-based runner exits OFF
    (levels_active/carry=[]), ribbon-flip-back OFF (min spread 1e9),
    runner target OFF (99.0 -- C30: unconstrained = never hit in 0DTE),
    TP1 +30% sell 2/3, BE runner after TP1 (simulator native), chandelier
    arm +5% / floor BE / trail 15% HWM, premium catastrophe stop per cell,
    per-trade time stop = min(15:50 ET, fill_bar_start + t_minutes).
  - strike: simulator convention positive offset = OTM both sides
    (calls atm+off / puts atm-off). ATM=0, OTM1=+1.
  - qty=3 forced (2 TP1 + 1 runner -- exact 2/3 split; qty1 = /3).

BATTERY per cell: expectancy, WR, OOS=2026 split (repo convention), drop-top3,
both-halves, one-sided t p + bootstrap P(sum<=0), spread stress (per-side
half-spread penalty to breakeven, ON TOP of the engine's default 2c/side),
opposite-direction null (same entry moments, PUT through same exit config).
BH-FDR across the 12 cells, alpha 0.1.

SURVIVAL (pre-registered): q<=0.10 AND OOS_total>0 AND drop_top3>0 AND both
halves>0 AND spread_breakeven>=+$0.02/side AND null not dominant
(null_total<=0 OR null_total < 0.5*cell_total).

Verdict ladder: PORT_CONFIRMS (>=1 cell survives everything; mixed-run confirm
+ scorecard + conductor proposal) / PORT_WEAK (positive but fails a named
nail) / PORT_FAILS.

Runtime: ONE process, backtest/.venv python (reaper-exempt). $0.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "backtest"))

from backtest.lib import orchestrator as orch  # noqa: E402
from backtest.lib.orchestrator import run_backtest, _params_to_kwargs  # noqa: E402
from backtest.lib.option_pricing_real import (  # noqa: E402
    load_contract_bars, option_symbol,
)

OUT_DIR = REPO / "analysis" / "j-webull" / "PHASEC-port"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PARAMS = json.loads((REPO / "automation" / "state" / "params.json").read_text(encoding="utf-8"))

START = "2025-01-02"
END = "2026-06-18"          # freshest full-window SPY 5m master
SAFE_EQUITY = 2000.0        # chef-bull-scope-ab methodology (anchor reproduction)
OOS_SPLIT = "2026-01-01"    # repo convention: IS=2025, OOS=2026
BOOT_N = 10_000
SEED = 42
ALPHA = 0.10
SPREAD_PASS = 0.02          # $/side extra beyond engine default 2c slippage
DATA = REPO / "backtest" / "data"

# Chef-recorded anchor (2026-06-26 params): bull n=25, +$5,586.5, WR 56%.
CHEF_RECORD = {"bull_n": 25, "bull_pnl": 5586.5, "bull_wr": 0.56}

# J source-of-truth days (OP-16) for the mixed-run confirm.
WINNERS = {"2026-04-29": 342.0, "2026-05-01": 470.0, "2026-05-04": 730.0}
LOSERS = {"2026-05-05": -260.0, "2026-05-06": -300.0, "2026-05-07": -120.0}

CELLS = [
    {"id": "c1_s50_otm1_tEOD", "stop": -0.50, "offset": 1, "tmin": None,
     "label": "stop-50 / otm1 / tEOD"},
    {"id": "c2_s50_atm_tEOD",  "stop": -0.50, "offset": 0, "tmin": None,
     "label": "stop-50 / atm / tEOD"},
    {"id": "c3_s50_otm1_t120", "stop": -0.50, "offset": 1, "tmin": 120,
     "label": "stop-50 / otm1 / t120"},
    {"id": "c4_s50_atm_t120",  "stop": -0.50, "offset": 0, "tmin": 120,
     "label": "stop-50 / atm / t120"},
    {"id": "c5_s20_atm_t120",  "stop": -0.20, "offset": 0, "tmin": 120,
     "label": "stop-20 / atm / t120"},
    {"id": "c6_s50_otm1_t60",  "stop": -0.50, "offset": 1, "tmin": 60,
     "label": "stop-50 / otm1 / t60"},
]

_ORIG_SIM = orch.simulate_trade_real
_MISS_LOG: list[dict] = []   # OPRA cache misses seen inside the wrapper

PORT_EXITS = dict(
    tp1_premium_pct=0.30,
    tp1_qty_fraction=0.667,
    runner_target_premium_pct=99.0,
    profit_lock_threshold_pct=0.05,
    profit_lock_stop_offset_pct=0.0,
    profit_lock_mode="trailing",
    profit_lock_trail_pct=0.15,
    ribbon_flip_back_min_spread_cents=1e9,
)


def load_frames():
    spy = pd.read_csv(DATA / "spy_5m_2025-01-01_2026-06-18.csv")
    vix = pd.read_csv(DATA / "vix_5m_2025-01-01_2026-06-18.csv")
    spy = spy[(spy["timestamp_et"] >= START) & (spy["timestamp_et"] < f"{END}T23:59:59")].reset_index(drop=True)
    vix = vix[(vix["timestamp_et"] >= START) & (vix["timestamp_et"] < f"{END}T23:59:59")].reset_index(drop=True)
    return spy, vix


def base_kwargs(bull_only: bool) -> dict:
    kw = _params_to_kwargs(PARAMS, account_equity=SAFE_EQUITY)
    kw["enable_bullish"] = True
    if bull_only:
        kw["min_triggers_bear"] = 999   # explicit kwarg wins -> zero bear entries
    return kw


def make_wrapper(cell: dict, null_side: bool, calls_only: bool):
    """Wrap simulate_trade_real: swap exits/strike/size to the Phase-B family.

    calls_only=True leaves bear (P) calls untouched (mixed-confirm mode).
    null_side=True flips the CALL to the same-strike-distance PUT (opposite-
    direction null: same entry moments + same exit config).
    """
    def wrapper(**kw):
        if calls_only and kw.get("side") != "C":
            return _ORIG_SIM(**kw)
        ts = pd.Timestamp(kw["entry_bar"]["timestamp_et"])
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        fill_start = ts + pd.Timedelta(minutes=5)
        hard = dt.time(15, 50)
        if cell["tmin"] is not None:
            cut = (fill_start + pd.Timedelta(minutes=cell["tmin"])).time()
            tstop = min(hard, cut)
        else:
            tstop = hard
        kw.update(PORT_EXITS)
        kw.update(
            qty=3,
            premium_stop_pct=cell["stop"],
            strike_offset=cell["offset"],
            rejection_level=None,
            levels_active=[],
            levels_carry=[],
            time_stop_et=tstop,
        )
        if null_side:
            kw["side"] = "P"
        fill = _ORIG_SIM(**kw)
        if fill is None:
            spot = float(kw["entry_bar"]["close"])
            atm = int(round(spot))
            side = kw["side"]
            strike = (atm - cell["offset"]) if side == "P" else (atm + cell["offset"])
            _MISS_LOG.append({"date": str(ts.date()), "strike": strike, "side": side,
                              "symbol": option_symbol(ts.date(), strike, side)})
        return fill
    return wrapper


def naive(ts):
    ts = pd.Timestamp(ts)
    return ts.tz_localize(None) if ts.tzinfo else ts


def t_row(t) -> dict:
    return {
        "entry_time": str(naive(t.entry_time_et)),
        "setup": t.setup,
        "side": t.side,
        "strike": t.strike,
        "qty": t.qty,
        "entry_premium": round(float(t.entry_premium), 4),
        "tp1_premium": (round(float(t.tp1_premium), 4) if getattr(t, "tp1_premium", None) else None),
        "runner_exit_premium": (round(float(t.runner_exit_premium), 4)
                                if getattr(t, "runner_exit_premium", None) else None),
        "exit_reason": str(getattr(t, "exit_reason", "")),
        "dollar_pnl": round(float(t.dollar_pnl), 2),
        "entry_vix": round(float(getattr(t, "entry_vix", 0.0) or 0.0), 2),
        "hold_minutes": getattr(t, "hold_minutes", None),
        "triggers": list(getattr(t, "triggers_fired", []) or []),
    }


def run_engine(spy, vix, kwargs, wrapper=None, tag=""):
    t0 = time.time()
    orch.simulate_trade_real = wrapper if wrapper is not None else _ORIG_SIM
    try:
        res = run_backtest(
            spy, vix,
            start_date=dt.date.fromisoformat(START),
            end_date=dt.date.fromisoformat(END),
            use_real_fills=True,
            **kwargs,
        )
    finally:
        orch.simulate_trade_real = _ORIG_SIM
    rows = [t_row(t) for t in res.trades]
    print(f"[run] {tag}: n={len(rows)} total={sum(r['dollar_pnl'] for r in rows):+.0f} "
          f"({time.time()-t0:.0f}s)", flush=True)
    return rows


def bull_rows(rows):
    return [r for r in rows if "BULLISH" in r["setup"]]


def battery(rows, boot_rng) -> dict:
    """Full pre-registered battery on qty3 per-trade rows."""
    pnls = np.array([r["dollar_pnl"] for r in rows], dtype=float)
    n = len(pnls)
    if n == 0:
        return {"n": 0}
    total = float(pnls.sum())
    mean = total / n
    wr = float((pnls > 0).mean())
    sd = float(pnls.std(ddof=1)) if n > 1 else 0.0
    tstat = mean / (sd / math.sqrt(n)) if sd > 0 else 0.0
    try:
        from scipy import stats
        p_t = float(stats.t.sf(tstat, df=n - 1)) if n > 1 else 1.0
    except Exception:
        p_t = 0.5 * math.erfc(tstat / math.sqrt(2))
    boot = boot_rng.choice(pnls, size=(BOOT_N, n), replace=True).sum(axis=1)
    p_boot = float((boot <= 0).mean())
    srt = sorted(pnls, reverse=True)
    drop_top3 = float(total - sum(x for x in srt[:3] if x > 0))
    order = np.argsort([r["entry_time"] for r in rows])
    chron = pnls[order]
    h1 = float(chron[: n // 2].sum())
    h2 = float(chron[n // 2:].sum())
    oos_mask = np.array([r["entry_time"] >= OOS_SPLIT for r in rows])
    oos = pnls[oos_mask]
    ins = pnls[~oos_mask]
    # spread stress: each qty-3 trade = 6 contract-sides -> $600 per 1c/side... no:
    # penalty per trade = 2 * qty * 100 * x  (x $/side). Breakeven x*:
    x_star = total / (n * 2 * 3 * 100.0)
    return {
        "n": n, "total": round(total, 2), "exp_tr": round(mean, 2),
        "wr": round(wr, 4), "t": round(tstat, 3),
        "p_t": p_t, "p_boot": p_boot,
        "drop_top3": round(drop_top3, 2),
        "half1": round(h1, 2), "half2": round(h2, 2),
        "is_n": int((~oos_mask).sum()), "is_total": round(float(ins.sum()), 2),
        "oos_n": int(oos_mask.sum()), "oos_total": round(float(oos.sum()), 2),
        "oos_exp_tr": round(float(oos.mean()), 2) if oos_mask.any() else None,
        "spread_breakeven_per_side": round(x_star, 4),
        "exit_reasons": pd.Series([r["exit_reason"] for r in rows]).value_counts().to_dict(),
    }


def bh_qvalues(pvals: list[float]) -> list[float]:
    m = len(pvals)
    order = sorted(range(m), key=lambda i: pvals[i])
    q = [0.0] * m
    prev = 1.0
    for rank_from_end in range(m, 0, -1):
        i = order[rank_from_end - 1]
        val = min(prev, pvals[i] * m / rank_from_end)
        q[i] = val
        prev = val
    return q


def fetch_misses(misses: list[dict]) -> int:
    """Fetch any uncached contracts via the canonical expander (free Alpaca data API)."""
    uniq = {}
    for m in misses:
        uniq[m["symbol"]] = m
    todo = []
    for sym, m in uniq.items():
        if load_contract_bars(sym) is None:
            p = DATA / "options" / f"{sym}.csv"
            e = DATA / "options" / f"{sym}.csv.empty"
            if not p.exists() and not e.exists():
                todo.append(m)
    if not todo:
        return 0
    sys.path.insert(0, str(REPO / "backtest" / "tools"))
    import expand_opra_cache as eoc
    from _alpaca_creds import resolve_alpaca_creds
    creds = resolve_alpaca_creds()
    print(f"[fetch] {len(todo)} uncached contracts, fetching via Alpaca data API...", flush=True)
    done = 0
    for m in todo:
        d = dt.date.fromisoformat(m["date"])
        try:
            bars = eoc.fetch_contract_bars(m["symbol"], d, creds.key, creds.secret)
            if bars:
                eoc.write_cache(m["symbol"], bars)
                done += 1
            else:
                eoc.write_empty_sentinel(m["symbol"])
        except Exception as ex:  # noqa: BLE001
            print(f"[fetch] FAIL {m['symbol']}: {ex}", flush=True)
        time.sleep(0.35)
    # invalidate in-process negative cache
    from backtest.lib import option_pricing_real as opr
    for m in todo:
        opr._CONTRACT_BAR_CACHE.pop(m["symbol"], None)
    print(f"[fetch] fetched {done}/{len(todo)}", flush=True)
    return done


def per_day(rows):
    d = {}
    for r in rows:
        day = r["entry_time"][:10]
        d[day] = d.get(day, 0.0) + r["dollar_pnl"]
    return d


def edge_capture(rows):
    byday = per_day(rows)
    cap, detail = 0.0, {}
    for day in WINNERS:
        pnl = byday.get(day, 0.0)
        cap += pnl
        detail[day] = ["WIN", round(pnl, 2)]
    for day in LOSERS:
        pnl = byday.get(day, 0.0)
        cap -= max(0.0, -pnl)
        detail[day] = ["LOSS", round(pnl, 2)]
    return round(cap, 2), detail


def main():
    print(f"[phasec] start {dt.datetime.now().isoformat(timespec='seconds')}", flush=True)
    spy, vix = load_frames()
    print(f"[phasec] SPY {len(spy)} bars / VIX {len(vix)} bars [{START}..{END}]", flush=True)
    out = {"window": f"{START}..{END}", "authority": "REAL OPRA FILLS (use_real_fills=True, C1)",
           "ran_at": dt.datetime.now().isoformat(timespec="seconds")}

    # ── Stage 1: baselines ────────────────────────────────────────────────
    mixed = run_engine(spy, vix, base_kwargs(bull_only=False), tag="B_mixed(prod params, bear+bull)")
    bull_mixed = bull_rows(mixed)
    bo = run_engine(spy, vix, base_kwargs(bull_only=True), tag="B_bullonly(prod exits)")
    assert all("BULLISH" in r["setup"] for r in bo), "bear leak in bull-only run"
    rng = np.random.default_rng(SEED)
    out["baseline_mixed_bull_subset"] = battery(bull_mixed, rng)
    out["baseline_mixed_bull_subset"]["note"] = (
        "current-params reproduction of chef-bull-scope-ab UNBLOCK bull subset; "
        f"chef 2026-06-26 record: n={CHEF_RECORD['bull_n']} total=+{CHEF_RECORD['bull_pnl']:.0f} "
        f"wr={CHEF_RECORD['bull_wr']:.2f} (params have drifted since: tp1_qty_fraction "
        "0.667->0.8 on 06-28 etc.)")
    out["baseline_bullonly_prod_exits"] = battery(bo, rng)
    out["baseline_mixed_all"] = battery(mixed, rng)
    Path(OUT_DIR / "_stage1.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")

    # ── Stage 2+3: cells + nulls (with one fetch-and-retry pass) ─────────
    cell_rows, null_rows = {}, {}
    for attempt in (1, 2):
        _MISS_LOG.clear()
        for cell in CELLS:
            cell_rows[cell["id"]] = run_engine(
                spy, vix, base_kwargs(bull_only=True),
                wrapper=make_wrapper(cell, null_side=False, calls_only=False),
                tag=f"{cell['id']} attempt{attempt}")
            null_rows[cell["id"]] = run_engine(
                spy, vix, base_kwargs(bull_only=True),
                wrapper=make_wrapper(cell, null_side=True, calls_only=False),
                tag=f"{cell['id']}-NULL attempt{attempt}")
        if not _MISS_LOG:
            break
        fetched = fetch_misses(list(_MISS_LOG))
        out["opra_misses_attempt%d" % attempt] = len(_MISS_LOG)
        if fetched == 0:
            break  # nothing fetchable -> accept coverage as-is
    out["opra_misses_final"] = len(_MISS_LOG)
    out["opra_miss_symbols"] = sorted({m["symbol"] for m in _MISS_LOG})

    # ── Stage 4: battery + BH across 12 ──────────────────────────────────
    results = []
    for cell in CELLS:
        rows = cell_rows[cell["id"]]
        nrows = null_rows[cell["id"]]
        b = battery(rows, rng)
        nb = battery(nrows, rng) if nrows else {"n": 0, "total": 0.0}
        for qty in (3, 1):
            scale = 1.0 if qty == 3 else (1.0 / 3.0)
            results.append({
                "cell": f"{cell['id']}_q{qty}",
                "base_cell": cell["id"], "label": cell["label"], "qty": qty,
                "n": b.get("n", 0),
                "total": round(b.get("total", 0.0) * scale, 2),
                "exp_tr": round(b.get("exp_tr", 0.0) * scale, 2),
                "wr": b.get("wr"),
                "p_t": b.get("p_t", 1.0), "p_boot": b.get("p_boot", 1.0),
                "drop_top3": round(b.get("drop_top3", 0.0) * scale, 2),
                "half1": round(b.get("half1", 0.0) * scale, 2),
                "half2": round(b.get("half2", 0.0) * scale, 2),
                "is_total": round(b.get("is_total", 0.0) * scale, 2),
                "oos_n": b.get("oos_n"), "oos_total": round(b.get("oos_total", 0.0) * scale, 2),
                "oos_exp_tr": (round(b["oos_exp_tr"] * scale, 2) if b.get("oos_exp_tr") is not None else None),
                "spread_breakeven_per_side": b.get("spread_breakeven_per_side"),
                "null_n": nb.get("n", 0), "null_total": round(nb.get("total", 0.0) * scale, 2),
                "exit_reasons": b.get("exit_reasons"),
            })
    pvals = [r["p_t"] for r in results]
    qvals = bh_qvalues(pvals)
    for r, q in zip(results, qvals):
        r["q"] = round(q, 4)
        r["p_t"] = round(r["p_t"], 5)
        r["p_boot"] = round(r["p_boot"], 5)
        gates = {
            "q_le_0.10": r["q"] <= ALPHA,
            "oos_positive": (r["oos_total"] or 0) > 0,
            "drop_top3_positive": r["drop_top3"] > 0,
            "both_halves_positive": r["half1"] > 0 and r["half2"] > 0,
            "spread_stress_ge_2c": (r["spread_breakeven_per_side"] or 0) >= SPREAD_PASS,
            "null_not_dominant": (r["null_total"] <= 0) or (r["null_total"] < 0.5 * r["total"]),
        }
        r["gates"] = gates
        r["SURVIVES"] = all(gates.values())
    out["cells"] = results
    survivors = [r for r in results if r["SURVIVES"]]
    out["n_survivors"] = len(survivors)

    # ── Stage 5: mixed-run confirm for surviving base cells ──────────────
    ec_base, ec_base_detail = edge_capture(mixed)
    out["edge_capture_baseline_mixed"] = {"cap": ec_base, "detail": ec_base_detail}
    confirmed_base_cells = sorted({r["base_cell"] for r in survivors})
    out["mixed_confirm"] = {}
    for cid in confirmed_base_cells:
        cell = next(c for c in CELLS if c["id"] == cid)
        mrows = run_engine(
            spy, vix, base_kwargs(bull_only=False),
            wrapper=make_wrapper(cell, null_side=False, calls_only=True),
            tag=f"MIXED-CONFIRM {cid} (bear prod + bull port)")
        cap, detail = edge_capture(mrows)
        out["mixed_confirm"][cid] = {
            "all": battery(mrows, rng),
            "bull_subset": battery(bull_rows(mrows), rng),
            "edge_capture": cap, "edge_capture_detail": detail,
            "edge_capture_delta_vs_baseline": round(cap - ec_base, 2),
            "anchor_no_regression": cap >= ec_base,
        }

    # ── Verdict ───────────────────────────────────────────────────────────
    if survivors:
        verdict = "PORT_CONFIRMS"
    else:
        positives = [r for r in results if r["total"] > 0]
        verdict = "PORT_WEAK" if positives else "PORT_FAILS"
    out["verdict"] = verdict

    # per-cohort trade dumps for audit
    dump = {"baseline_mixed": mixed, "baseline_bullonly": bo,
            "cells": cell_rows, "nulls": null_rows}
    (OUT_DIR / "trades.json").write_text(json.dumps(dump, indent=1, default=str), encoding="utf-8")
    (OUT_DIR / "results.json").write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"[phasec] VERDICT={verdict} survivors={len(survivors)}", flush=True)
    print(f"[phasec] wrote {OUT_DIR / 'results.json'}", flush=True)


if __name__ == "__main__":
    main()

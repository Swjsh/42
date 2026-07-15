"""debit_spread_ab_study.py -- EDGE-2-DEBIT-SPREAD-AB.

Frozen pre-registration: analysis/recommendations/prereg-debit-spread-ab-2026-07-14.json
(content_sha256_16 pinned below; preflight() FAILS LOUD on any drift between what's frozen
on disk and what this runner executes).

WHAT THIS TESTS (markdown/research/EDGE-DEEP-RESEARCH-SYNTHESIS-2026-07-14.md, ranked #2):
does selling back part of the overpriced 0DTE single-leg debit via a vertical DEBIT spread
(long ATM + short 1 or 2 strikes further OTM, same side) beat the current naked single-leg
on the SAME validated ribbon_ride signal cohort, run through the SAME live exit_manager
decision core? Or does crossing 2 bid-ask spreads (open+close, both legs) eat the VRP the
short leg is meant to capture? A KILL is a fully anticipated, valid, publishable outcome --
nothing here is tuned after seeing results.

METHOD (see the frozen pre-reg for the full spec; summarized here):
  * Population: the canonical 250-signal ribbon_ride cohort (backtest/tools/_signal_cache.py)
    + 110 real-fill positions (automation/state/fills-ledger.jsonl, all arms, engine-attributed
    options) as disclosure-only corroboration.
  * Structure: long leg ALWAYS ATM (matches the live tier); naked control = long leg alone;
    treatment = long leg + a short leg 1 or 2 whole-dollar strikes further OTM
    (backtest/lib/simulator_debit.py:build_debit_vertical).
  * Pricing: real 5-min OPRA bars (backtest/lib/option_pricing_real.py), local cache, $0.
    Entry/exit haircut = simulator_credit's DEFAULT_ENTRY_SLIPPAGE/EXIT_SLIPPAGE/COMMISSION
    (byte-for-byte simulator_real's own defaults) -- applied ONCE per leg at entry, and at
    EVERY closing transaction (so the spread pays the haircut on BOTH legs, twice the naked
    control's cost -- the mechanism under test).
  * Exits: automation/state/fleet/exit_manager.py's plan_exit_actions -- the LIVE decision
    core, unmodified -- applied to the naked premium (1 instrument, real intrabar touch) and
    to the spread's NET premium (long.close - short.close, a real simultaneous joint quote --
    CORRECTED post-freeze to match simulator_debit.py's own opnl-gated PT/STOP trigger; see
    the pre-reg's post_freeze_correction_2026_07_14 for the found-and-fixed intrabar-combo
    defect) identically in every other respect. Shape sourced fresh from automation/state/
    params.json at run time (see _live_shape()). DISCLOSED GAP: structure_stop/ribbon-flip is
    NOT modeled (premium-only replay, same simplification as t4_exit_matrix / exit_shape_parity_study).
  * Nulls: naked control as the paired baseline + a 5000-iteration sign-flip permutation test
    per variant, BH-FDR (alpha=0.10) across the 2 variants (backtest/autoresearch/
    ribbon_rejection_wick_battery.bh_fdr, reused unchanged).
  * OP-16 anchor check (non-negotiable, checked FIRST): replay the 3 J_WINNERS ride-the-ribbon
    days as naked vs each variant; a variant that caps those days' payoff by more than the
    frozen materiality threshold is an ANCHOR REGRESSION and FAILS regardless of aggregate.

Run: backtest/.venv/Scripts/python.exe backtest/tools/debit_spread_ab_study.py
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import random
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools", REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from lib.option_pricing_real import load_contract_bars, option_symbol       # noqa: E402
from lib.simulator_debit import build_debit_vertical                        # noqa: E402
from lib.simulator_credit import (                                          # noqa: E402
    DEFAULT_ENTRY_SLIPPAGE, DEFAULT_EXIT_SLIPPAGE, DEFAULT_COMMISSION)
from exit_manager import ExitState, plan_exit_actions                       # noqa: E402
from _signal_cache import load_or_build_signals                             # noqa: E402
import exit_shape_parity_study as esp                                       # noqa: E402
from autoresearch.strategy_space_grind import OOS_BOUNDARY, J_WINNERS       # noqa: E402
from autoresearch.ribbon_rejection_wick_battery import bh_fdr, FDR_ALPHA    # noqa: E402
from autoresearch.runner import load_data                                   # noqa: E402

PREREG = REPO / "analysis" / "recommendations" / "prereg-debit-spread-ab-2026-07-14.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "debit-spread-ab.json"
OUT_MD = REPO / "analysis" / "recommendations" / "debit-spread-ab.md"
PARAMS_PATH = REPO / "automation" / "state" / "params.json"
LEDGER = REPO / "automation" / "state" / "fills-ledger.jsonl"

EXPECTED_PREREG_VERSION = 2
EXPECTED_PREREG_SHA16 = "7da146fba3898cba"

QTY = 10
VARIANTS = {"OTM-1": 1, "OTM-2": 2}
N_PERMUTATIONS = 5000
SEED = 1729


# --- preflight: never run a drifted spec ---------------------------------------------------
def _content_hash(payload_obj) -> str:
    payload = json.dumps(payload_obj, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def preflight() -> dict:
    preg = json.loads(PREREG.read_text(encoding="utf-8"))
    stored = preg.get("content_sha256_16")
    preg_no_hash = {k: v for k, v in preg.items() if k != "content_sha256_16"}
    recomputed = _content_hash(preg_no_hash)
    ok = (recomputed == EXPECTED_PREREG_SHA16 == stored
          and preg.get("version") == EXPECTED_PREREG_VERSION
          and preg.get("status") == "FROZEN_PENDING_RUN")
    return {"ok": ok, "recomputed_sha16": recomputed, "stored_sha16": stored,
            "version": preg.get("version"), "status": preg.get("status")}


# --- live shape, sourced fresh from params.json at run time -------------------------------
def _live_shape() -> dict:
    p = json.loads(PARAMS_PATH.read_text(encoding="utf-8-sig"))
    return {
        "premium_stop_pct": float(p.get("premium_stop_pct", -0.50)),
        "tp1_premium_pct": float(p.get("tp1_premium_pct", 0.50)),
        "tp1_qty_fraction": float(p.get("tp1_qty_fraction", 0.8)),
        "profit_lock_mode": str(p.get("v15_profit_lock_mode", "fixed")),
        "profit_lock_arm_pct": float(p.get("v15_profit_lock_threshold_pct", 0.05)),
        "trail_pct": float(p.get("v15_profit_lock_trail_pct", 0.125)),
        "runner_target_pct": 2.5,
    }


def _time_stop() -> dt.time:
    p = json.loads(PARAMS_PATH.read_text(encoding="utf-8-sig"))
    parts = str(p.get("time_stop_et", "15:40")).split(":")
    return dt.time(int(parts[0]), int(parts[1]))


# --- bar loading / alignment ----------------------------------------------------------------
def _load_bars_at_strike(date: dt.date, strike: int, side: str, entry_ts: dt.datetime) -> list | None:
    """5m bars for one leg from the entry bar (>= entry_ts) onward. Fill-bar-INCLUDED
    convention (bar-0's OPEN is the entry fill), same as t4_exit_matrix._load_bars."""
    df = load_contract_bars(option_symbol(date, strike, side))
    if df is None or df.empty:
        return None
    ts = df["timestamp_et"]
    if ts.dt.tz is not None:
        ts = ts.dt.tz_localize(None)
    mask = (ts >= entry_ts) & (ts.dt.date == date)
    sub = df[mask.values]
    if sub.empty:
        return None
    out = []
    for _, r in sub.iterrows():
        t = r["timestamp_et"]
        tt = t.tz_localize(None).to_pydatetime() if getattr(t, "tz", None) is not None else t.to_pydatetime()
        out.append((tt.time(), float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])))
    return out or None


def _align_legs(long_bars: list, short_bars: list) -> list:
    """Inner-join two leg bar lists on bar time -> [(t, lo,lh,ll,lc, so,sh,sl,sc)]."""
    short_by_t = {b[0]: b for b in short_bars}
    aligned = []
    for b in long_bars:
        sb = short_by_t.get(b[0])
        if sb is None:
            continue
        aligned.append((b[0], b[1], b[2], b[3], b[4], sb[1], sb[2], sb[3], sb[4]))
    return aligned


# --- replay: naked single-leg (control) -----------------------------------------------------
def replay_naked(long_bars: list, side: str, shape: dict, time_stop_et: dt.time, qty: int = QTY) -> dict:
    entry_premium = long_bars[0][1] + DEFAULT_ENTRY_SLIPPAGE
    if entry_premium <= 0:
        return {"pnl": None, "reason": "bad_entry_premium"}
    state = ExitState.from_entry(symbol="x", side=side, entry_premium=entry_premium, qty=qty, exit_shape=shape)
    open_qty = qty
    realized = 0.0
    total_slip = DEFAULT_ENTRY_SLIPPAGE * 100.0 * qty       # 1 leg, entry
    last_close = entry_premium
    exit_stage = None
    for (btime, o, h, l, c) in long_bars:
        last_close = c
        dec = plan_exit_actions(state, best_premium=h, worst_premium=l, open_qty=open_qty,
                                 now_et=btime, ribbon_flip_back=False, time_stop_et=time_stop_et)
        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            if a.stage == "tp1":
                target = entry_premium * (1.0 + state.tp1_premium_pct)
            elif a.stage == "runner_target":
                target = entry_premium * (1.0 + state.runner_target_pct)
            elif a.stage == "premium_stop":
                # Always use the ACTUAL just-computed runner_stop_premium: under
                # profit_lock_arm_scope="full" a "premium_stop"-labeled exit can be a pre-TP1
                # profit-lock floor/trail ratchet, not the static catastrophe level (exit_manager
                # doesn't distinguish them in its stage naming). No-op for this study's own
                # shapes (arm_scope always defaults to "post_tp1", where runner_stop_premium is
                # byte-identical to entry*(1+premium_stop_pct)) -- fixed for correctness since
                # hold_posture_ab_study.py reuses this module and DOES use arm_scope="full".
                target = (dec.state.runner_stop_premium if dec.state.runner_stop_premium is not None
                          else entry_premium * (1.0 + state.premium_stop_pct))
            elif a.stage in ("trail", "be_stop"):
                target = dec.state.runner_stop_premium
            else:  # time_stop
                target = c
            fill = max(0.01, target - DEFAULT_EXIT_SLIPPAGE)
            realized += (fill - entry_premium) * a.qty * 100.0
            total_slip += DEFAULT_EXIT_SLIPPAGE * 100.0 * a.qty
            open_qty -= a.qty
            exit_stage = a.stage
        state = dec.state
        if open_qty <= 0:
            break
    if open_qty > 0:
        fill = max(0.01, last_close - DEFAULT_EXIT_SLIPPAGE)
        realized += (fill - entry_premium) * open_qty * 100.0
        total_slip += DEFAULT_EXIT_SLIPPAGE * 100.0 * open_qty
        exit_stage = exit_stage or "eod_leftover"
    commission = DEFAULT_COMMISSION * 1 * 2 * qty
    realized -= commission
    friction = total_slip + commission
    notional = entry_premium * 100.0 * qty
    theta = None
    if exit_stage in ("time_stop", "eod_leftover"):
        theta = round((entry_premium - last_close) / entry_premium, 4) if entry_premium else None
    return {"pnl": round(realized, 2), "entry_premium": round(entry_premium, 4),
            "friction_usd": round(friction, 2),
            "friction_pct_of_premium": round(friction / notional, 4) if notional else None,
            "exit_stage": exit_stage, "theta_bleed_proxy": theta}


# --- replay: debit vertical spread (treatment) ----------------------------------------------
def replay_spread(aligned: list, side: str, shape: dict, time_stop_et: dt.time, qty: int = QTY) -> dict:
    long_entry = aligned[0][1] + DEFAULT_ENTRY_SLIPPAGE
    short_entry = aligned[0][5] - DEFAULT_ENTRY_SLIPPAGE
    entry_premium = long_entry - short_entry   # net debit per share (must be > 0)
    if entry_premium <= 0:
        return {"pnl": None, "reason": "non_debit"}
    state = ExitState.from_entry(symbol="x", side=side, entry_premium=entry_premium, qty=qty, exit_shape=shape)
    open_qty = qty
    realized = 0.0
    total_slip = DEFAULT_ENTRY_SLIPPAGE * 2 * 100.0 * qty    # 2 legs, entry
    last_net_close = entry_premium
    exit_stage = None
    for (btime, lo, lh, ll, lc, so, sh, sl, sc) in aligned:
        # CORRECTED post-freeze (see prereg post_freeze_correction_2026_07_14): use the
        # bar-CLOSE-based net premium for BOTH best/worst -- a real simultaneous joint quote,
        # matching simulator_debit.py's own opnl-gated PT/STOP trigger. The intrabar
        # long.low-short.high / long.high-short.low combo is NOT used to trigger here (that
        # module reserves it for a disclosure-only flag, never the actual exit test) because
        # it assumes two independently-timed leg extrema co-occurred, which is far more
        # pessimistic than either leg's own single-instrument touch.
        net_now = lc - sc
        last_net_close = net_now
        dec = plan_exit_actions(state, best_premium=net_now, worst_premium=net_now, open_qty=open_qty,
                                 now_et=btime, ribbon_flip_back=False, time_stop_et=time_stop_et)
        for a in dec.actions:
            if a.kind not in ("SELL_PARTIAL", "SELL_ALL"):
                continue
            if a.stage == "tp1":
                target = entry_premium * (1.0 + state.tp1_premium_pct)
            elif a.stage == "runner_target":
                target = entry_premium * (1.0 + state.runner_target_pct)
            elif a.stage == "premium_stop":
                # Always use the ACTUAL just-computed runner_stop_premium: under
                # profit_lock_arm_scope="full" a "premium_stop"-labeled exit can be a pre-TP1
                # profit-lock floor/trail ratchet, not the static catastrophe level (exit_manager
                # doesn't distinguish them in its stage naming). No-op for this study's own
                # shapes (arm_scope always defaults to "post_tp1", where runner_stop_premium is
                # byte-identical to entry*(1+premium_stop_pct)) -- fixed for correctness since
                # hold_posture_ab_study.py reuses this module and DOES use arm_scope="full".
                target = (dec.state.runner_stop_premium if dec.state.runner_stop_premium is not None
                          else entry_premium * (1.0 + state.premium_stop_pct))
            elif a.stage in ("trail", "be_stop"):
                target = dec.state.runner_stop_premium
            else:  # time_stop
                target = last_net_close
            fill = target - 2 * DEFAULT_EXIT_SLIPPAGE   # crossing BOTH legs' spreads to close
            realized += (fill - entry_premium) * a.qty * 100.0
            total_slip += DEFAULT_EXIT_SLIPPAGE * 2 * 100.0 * a.qty
            open_qty -= a.qty
            exit_stage = a.stage
        state = dec.state
        if open_qty <= 0:
            break
    if open_qty > 0:
        fill = last_net_close - 2 * DEFAULT_EXIT_SLIPPAGE
        realized += (fill - entry_premium) * open_qty * 100.0
        total_slip += DEFAULT_EXIT_SLIPPAGE * 2 * 100.0 * open_qty
        exit_stage = exit_stage or "eod_leftover"
    commission = DEFAULT_COMMISSION * 2 * 2 * qty
    realized -= commission
    friction = total_slip + commission
    notional = entry_premium * 100.0 * qty
    theta = None
    if exit_stage in ("time_stop", "eod_leftover"):
        theta = round((entry_premium - last_net_close) / entry_premium, 4) if entry_premium else None
    return {"pnl": round(realized, 2), "entry_premium": round(entry_premium, 4),
            "friction_usd": round(friction, 2),
            "friction_pct_of_premium": round(friction / notional, 4) if notional else None,
            "exit_stage": exit_stage, "theta_bleed_proxy": theta}


# --- per-signal record build -----------------------------------------------------------------
def build_records(signals: list[dict], shape: dict, time_stop_et: dt.time,
                   spot_lookup=None) -> tuple[list[dict], dict]:
    """spot_lookup: optional callable(date, entry_ts) -> entry_spot override (used for the
    corroboration population, which has no cached entry_spot of its own)."""
    records = []
    misses = {"long": 0, "OTM-1": 0, "OTM-2": 0}
    for s in signals:
        date = dt.date.fromisoformat(s["date"]) if isinstance(s["date"], str) else s["date"]
        side = s["side"]
        entry_ts = dt.datetime.fromisoformat(s["entry_ts"]) if isinstance(s["entry_ts"], str) else s["entry_ts"]
        entry_spot = s.get("entry_spot")
        if entry_spot is None and spot_lookup is not None:
            entry_spot = spot_lookup(date, entry_ts)
        if entry_spot is None:
            misses["long"] += 1
            continue
        atm = int(round(entry_spot))
        long_bars = _load_bars_at_strike(date, atm, side, entry_ts)
        if long_bars is None:
            misses["long"] += 1
            continue
        naked = replay_naked(long_bars, side, shape, time_stop_et)
        rec = {"date": str(date), "direction": s.get("direction", "bull" if side == "C" else "bear"),
               "side": side, "entry_spot": entry_spot, "naked": naked, "variants": {}}
        for label, width in VARIANTS.items():
            legs = build_debit_vertical(entry_spot, side, near_offset=0, width=width)
            short_strike = legs[1].strike
            short_bars = _load_bars_at_strike(date, short_strike, side, entry_ts)
            if short_bars is None:
                misses[label] += 1
                rec["variants"][label] = None
                continue
            aligned = _align_legs(long_bars, short_bars)
            if not aligned:
                misses[label] += 1
                rec["variants"][label] = None
                continue
            rec["variants"][label] = replay_spread(aligned, side, shape, time_stop_et)
        records.append(rec)
    return records, misses


# --- battery (canonical: n/total/expectancy/wr/oos/wf/qpf/drop3) -----------------------------
def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


def battery(pnls_with_dates: list[tuple[dt.date, float]]) -> dict:
    if not pnls_with_dates:
        return {"n": 0}
    pnls = [p for _, p in pnls_with_dates]
    n = len(pnls)
    total = sum(pnls)
    wins = sum(1 for p in pnls if p > 0)
    is_t = [p for d, p in pnls_with_dates if d < OOS_BOUNDARY]
    oos_t = [p for d, p in pnls_with_dates if d >= OOS_BOUNDARY]
    is_mean = (sum(is_t) / len(is_t)) if is_t else 0.0
    oos_mean = (sum(oos_t) / len(oos_t)) if oos_t else 0.0
    wf = round(oos_mean / is_mean, 3) if is_mean > 0 else None
    wf_ge_070 = bool(is_mean > 0 and oos_mean > 0 and wf is not None and wf >= 0.70)
    byq: dict = {}
    for d, p in pnls_with_dates:
        byq.setdefault(_quarter(d), []).append(p)
    q_pos = sum(1 for v in byq.values() if sum(v) / len(v) > 0)
    qpf = q_pos / len(byq) if byq else 0.0
    drop3 = sorted(pnls)[:-3] if n > 3 else []
    exp_drop3 = sum(drop3) / len(drop3) if drop3 else 0.0
    return {"n": n, "total": round(total, 2), "expectancy": round(total / n, 2),
            "wr": round(wins / n, 3), "n_oos": len(oos_t), "n_is": len(is_t),
            "oos_total": round(sum(oos_t), 2), "oos_positive": sum(oos_t) > 0,
            "wf": wf, "wf_ge_070": wf_ge_070, "qpf": round(qpf, 3),
            "exp_drop_top3": round(exp_drop3, 2)}


# --- shuffle null (sign-flip permutation test) ------------------------------------------------
def shuffle_null_pvalue(diffs: list[float], n_perm: int = N_PERMUTATIONS, seed: int = SEED) -> dict:
    if not diffs:
        return {"n_pairs": 0, "observed_mean_diff": None, "p_null": None}
    rng = random.Random(seed)
    observed = sum(diffs) / len(diffs)
    n_extreme = 0
    for _ in range(n_perm):
        s = 0.0
        for d in diffs:
            s += d if rng.random() < 0.5 else -d
        m = s / len(diffs)
        if abs(m) >= abs(observed):
            n_extreme += 1
    p = n_extreme / n_perm
    return {"n_pairs": len(diffs), "observed_mean_diff": round(observed, 2), "p_null": round(p, 4)}


# --- OP-16 anchor check ------------------------------------------------------------------------
def anchor_check(records: list[dict]) -> dict:
    by_date: dict[str, list[dict]] = {}
    for r in records:
        by_date.setdefault(r["date"], []).append(r)
    rows = []
    naked_total_3d = 0.0
    variant_totals_3d = {label: 0.0 for label in VARIANTS}
    for wdate, side, actual_pnl in J_WINNERS:
        key = str(wdate)
        matches = [r for r in by_date.get(key, []) if r["side"] == side]
        naked_day = sum(r["naked"]["pnl"] for r in matches if r["naked"].get("pnl") is not None)
        variant_day = {}
        for label in VARIANTS:
            vals = [r["variants"][label]["pnl"] for r in matches
                    if r["variants"].get(label) and r["variants"][label].get("pnl") is not None]
            variant_day[label] = sum(vals) if vals else None
        naked_total_3d += naked_day
        for label in VARIANTS:
            if variant_day[label] is not None:
                variant_totals_3d[label] += variant_day[label]
        rows.append({"date": key, "j_actual_real_fill_pnl": actual_pnl, "n_matching_signals": len(matches),
                     "naked_atm_convention_pnl": round(naked_day, 2),
                     "variant_pnl": {k: (round(v, 2) if v is not None else None) for k, v in variant_day.items()}})
    regressions = {}
    for label in VARIANTS:
        shortfall = naked_total_3d - variant_totals_3d[label]
        material = shortfall > 0 and naked_total_3d > 0 and (shortfall / naked_total_3d) > 0.20
        regressions[label] = {
            "naked_total_3day": round(naked_total_3d, 2),
            "variant_total_3day": round(variant_totals_3d[label], 2),
            "shortfall": round(shortfall, 2),
            "shortfall_pct_of_naked": round(shortfall / naked_total_3d, 4) if naked_total_3d else None,
            "anchor_regression": bool(material),
        }
    return {"rows": rows, "naked_total_3day": round(naked_total_3d, 2),
            "variant_totals_3day": {k: round(v, 2) for k, v in variant_totals_3d.items()},
            "regressions": regressions}


# --- corroboration population (110 real fills, all arms, engine, options) ---------------------
def load_corroboration_signals() -> list[dict]:
    rows = [json.loads(l) for l in LEDGER.read_text(encoding="utf-8").splitlines() if l.strip()]
    opts_engine = [r for r in rows if r.get("attribution") == "engine" and not r.get("is_crypto")
                   and r.get("is_option")]
    positions = esp.reconstruct_positions(opts_engine)
    sigs = []
    for p in positions:
        sym = p["symbol"]
        # OCC symbol: SPY{yymmdd}{C|P}{strike*1000:08d} -- side is always index 9 ("SPY"+6 digits).
        side = sym[9]
        assert side in ("C", "P"), f"unexpected OCC side char in {sym!r}"
        entry_ts_et = dt.datetime.fromisoformat(p["entry_ts_utc"].replace("Z", "+00:00")).astimezone(
            dt.timezone(dt.timedelta(hours=-4))).replace(tzinfo=None)
        sigs.append({"date": p["date_et"], "entry_ts": entry_ts_et.isoformat(), "side": side,
                     "entry_spot": None, "direction": "bull" if side == "C" else "bear",
                     "_arm": p["arm"], "_real_entry_price": p["entry_price"],
                     "_real_actual_pnl": p["actual_exit_pnl"]})
    return sigs


def make_spy_spot_lookup():
    import pandas as pd
    spy, _vix = load_data(dt.date(2026, 6, 20), dt.date(2026, 7, 14))
    spy = spy.copy()
    ts = pd.to_datetime(spy["timestamp_et"], utc=True).dt.tz_convert("America/New_York").dt.tz_localize(None)
    spy["timestamp_et"] = ts

    def _lookup(date: dt.date, entry_ts: dt.datetime) -> float | None:
        sub = spy[spy["timestamp_et"] <= entry_ts]
        if sub.empty:
            return None
        return float(sub.iloc[-1]["close"])
    return _lookup


# --- main ---------------------------------------------------------------------------------------
def main() -> int:
    pf = preflight()
    print(f"[debit_spread_ab] preflight: {pf}")
    if not pf["ok"]:
        print("[debit_spread_ab] PREREG DRIFT DETECTED -- refusing to run. Fix the freeze first.",
              file=sys.stderr)
        return 2

    shape = _live_shape()
    time_stop_et = _time_stop()
    print(f"[debit_spread_ab] live shape: {shape}, time_stop={time_stop_et}")

    data = load_or_build_signals()
    signals = data["signals"] if isinstance(data, dict) else data
    print(f"[debit_spread_ab] primary cohort: {len(signals)} signals")

    records, misses = build_records(signals, shape, time_stop_et)
    print(f"[debit_spread_ab] primary: {len(records)} replayed, misses={misses}")

    corro_sigs = load_corroboration_signals()
    spot_lookup = make_spy_spot_lookup()
    corro_records, corro_misses = build_records(corro_sigs, shape, time_stop_et, spot_lookup=spot_lookup)
    print(f"[debit_spread_ab] corroboration: {len(corro_records)} replayed, misses={corro_misses}")

    # --- per-arm batteries (primary) ---
    naked_pnls = [(dt.date.fromisoformat(r["date"]), r["naked"]["pnl"]) for r in records
                  if r["naked"].get("pnl") is not None]
    naked_battery = battery(naked_pnls)

    variant_batteries = {}
    nulls = {}
    for label in VARIANTS:
        v_pnls = [(dt.date.fromisoformat(r["date"]), r["variants"][label]["pnl"]) for r in records
                  if r["variants"].get(label) and r["variants"][label].get("pnl") is not None]
        variant_batteries[label] = battery(v_pnls)
        # paired diffs (only signals where BOTH naked and this variant are valid)
        diffs = []
        for r in records:
            n = r["naked"].get("pnl")
            v = r["variants"].get(label)
            vp = v.get("pnl") if v else None
            if n is not None and vp is not None:
                diffs.append(vp - n)
        nulls[label] = shuffle_null_pvalue(diffs)
        mean_fric = [r["variants"][label]["friction_pct_of_premium"] for r in records
                     if r["variants"].get(label) and r["variants"][label].get("friction_pct_of_premium") is not None]
        variant_batteries[label]["mean_friction_pct_of_premium"] = (
            round(sum(mean_fric) / len(mean_fric), 4) if mean_fric else None)
        naked_fric = [r["naked"]["friction_pct_of_premium"] for r in records
                      if r["naked"].get("friction_pct_of_premium") is not None]
        naked_battery["mean_friction_pct_of_premium"] = (
            round(sum(naked_fric) / len(naked_fric), 4) if naked_fric else None)
        theta_vals = [r["variants"][label]["theta_bleed_proxy"] for r in records
                      if r["variants"].get(label) and r["variants"][label].get("theta_bleed_proxy") is not None]
        variant_batteries[label]["mean_theta_bleed_proxy"] = (
            round(sum(theta_vals) / len(theta_vals), 4) if theta_vals else None)

    # --- BH-FDR across the 2 variants ---
    bh_input = [{"label": label, "p_null": nulls[label]["p_null"]} for label in VARIANTS
                if nulls[label]["p_null"] is not None]
    if bh_input:
        bh_fdr(bh_input, alpha=FDR_ALPHA)
    bh_by_label = {row["label"]: row for row in bh_input}
    for label in VARIANTS:
        nulls[label]["bh_fdr_survivor"] = bh_by_label.get(label, {}).get("bh_fdr_survivor", False)
        nulls[label]["bh_rank"] = bh_by_label.get(label, {}).get("bh_rank")

    # --- OP-16 anchor check ---
    anchor = anchor_check(records)

    # --- corroboration (disclosure only) ---
    corro_naked = [(dt.date.fromisoformat(r["date"]), r["naked"]["pnl"]) for r in corro_records
                   if r["naked"].get("pnl") is not None]
    corro_naked_battery = battery(corro_naked)
    corro_variant_batteries = {}
    corro_agreement = {}

    def _exp(b: dict):
        return b.get("expectancy") if b.get("n") else None

    for label in VARIANTS:
        v_pnls = [(dt.date.fromisoformat(r["date"]), r["variants"][label]["pnl"]) for r in corro_records
                  if r["variants"].get(label) and r["variants"][label].get("pnl") is not None]
        corro_variant_batteries[label] = battery(v_pnls)
        v_exp, n_exp = _exp(variant_batteries[label]), _exp(naked_battery)
        primary_delta = (v_exp - n_exp) if (v_exp is not None and n_exp is not None) else None
        cv_exp, cn_exp = _exp(corro_variant_batteries[label]), _exp(corro_naked_battery)
        corro_delta = (cv_exp - cn_exp) if (cv_exp is not None and cn_exp is not None) else None
        same_sign = (primary_delta is not None and corro_delta is not None
                     and (primary_delta >= 0) == (corro_delta >= 0))
        corro_agreement[label] = {
            "primary_delta": round(primary_delta, 2) if primary_delta is not None else None,
            "corro_delta": round(corro_delta, 2) if corro_delta is not None else None,
            "same_sign": same_sign}

    # --- pass bar ---
    verdicts = {}
    for label in VARIANTS:
        favorable_and_significant = bool(
            nulls[label].get("bh_fdr_survivor")
            and (nulls[label].get("observed_mean_diff") or 0) > 0)
        conds = {
            "1_no_anchor_regression": not anchor["regressions"][label]["anchor_regression"],
            # bh_fdr_survivor alone only means "the delta vs naked is not chance" -- it says
            # NOTHING about direction. A statistically-significant WORSENING must not count as
            # passing this gate; only a significant IMPROVEMENT (positive observed_mean_diff)
            # does.
            "2_bh_fdr_survivor": favorable_and_significant,
            "3_oos_positive_and_wf": bool(variant_batteries[label].get("oos_positive")
                                          and variant_batteries[label].get("wf_ge_070")),
            "4_sub_window_stable": bool(variant_batteries[label].get("qpf", 0) >= 0.5),
            "5_corroboration_same_sign": bool(corro_agreement[label]["same_sign"]),
        }
        gating = conds["1_no_anchor_regression"] and conds["2_bh_fdr_survivor"] and conds["3_oos_positive_and_wf"]
        verdict = "CANDIDATE_PASS" if (gating and conds["4_sub_window_stable"]) else "KILL"
        if not conds["1_no_anchor_regression"]:
            verdict = "KILL_ANCHOR_REGRESSION"
        verdicts[label] = {"conditions": conds, "verdict": verdict}

    out = {
        "generated_at": dt.datetime.now().isoformat(),
        "prereg": str(PREREG.relative_to(REPO)),
        "prereg_preflight": pf,
        "cost_usd": 0.0,
        "live_shape_used": shape,
        "time_stop_et_used": str(time_stop_et),
        "primary_cohort": {"n_signals": len(signals), "n_replayed": len(records), "misses": misses,
                            "window": data.get("window") if isinstance(data, dict) else None},
        "control_naked": naked_battery,
        "variants": variant_batteries,
        "nulls": nulls,
        "fdr_alpha": FDR_ALPHA,
        "anchor_check_op16": anchor,
        "corroboration_110_real_fills": {
            "n_positions": len(corro_sigs), "n_replayed": len(corro_records), "misses": corro_misses,
            "naked": corro_naked_battery, "variants": corro_variant_batteries, "agreement": corro_agreement,
        },
        "verdicts": verdicts,
        "disclosures": [
            "premium-only exit replay (structure_stop/ribbon-flip collapse to the -50% catastrophe cap)",
            "fill-bar-INCLUDED convention (bar-0 open is the entry fill), same as t4_exit_matrix",
            "qty=10 flat (per-episode expectancy is the primary metric, not edge_capture)",
            "corroboration population's entry_spot is a nearest-prior-5m-bar SPY close lookup, "
            "not the engine's own recorded spot (the ledger does not persist it) -- secondary/disclosure only",
            "spread net-premium walk treats the 2-leg combo as one synthetic instrument for the "
            "exit_manager pct-of-entry-premium math -- a simplification, not a per-leg fill reconstruction "
            "at each trigger level (no tool in this repo does that for a 2-leg combo under live-shape replay)",
            "POST-FREEZE CORRECTION (see prereg): the spread's exit trigger uses bar-CLOSE net premium "
            "(a real simultaneous joint quote), not the intrabar long.low-short.high/long.high-short.low "
            "combo -- the v1 run fed that combo directly into the touch-based stop test and produced an "
            "implausible ~95% catastrophic-stop rate; simulator_debit.py itself only uses that combo as a "
            "disclosure flag, gating its actual PT/STOP on the same close-based figure this study now uses.",
        ],
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(render_md(out), encoding="utf-8")
    print(f"[debit_spread_ab] wrote {OUT_JSON.name} + {OUT_MD.name}")
    print(json.dumps({"control": naked_battery, "variants": variant_batteries, "verdicts": verdicts},
                      indent=2, default=str))
    return 0


def render_md(out: dict) -> str:
    L = []
    L.append("# EDGE-2 — Debit-spread vs naked single-leg A/B")
    L.append("")
    L.append(f"Pre-registration: `{out['prereg']}` (preflight ok={out['prereg_preflight']['ok']}). "
             f"Cost: $0 (local OPRA cache only). Generated {out['generated_at']}.")
    L.append("")
    c = out["control_naked"]
    L.append(f"**CONTROL (naked ATM single-leg):** n={c.get('n')} exp=${c.get('expectancy')} "
             f"WR={c.get('wr')} OOS+={c.get('oos_positive')} WF={c.get('wf')} qpf={c.get('qpf')} "
             f"friction%={c.get('mean_friction_pct_of_premium')}")
    L.append("")
    L.append("## Variants")
    L.append("")
    L.append("| variant | n | exp | WR | OOS+ | WF | qpf | friction% | theta-bleed | p_null | BH-FDR | verdict |")
    L.append("|---|--:|--:|--:|:--:|--:|--:|--:|--:|--:|:--:|---|")
    for label, b in out["variants"].items():
        nu = out["nulls"][label]
        v = out["verdicts"][label]
        L.append(f"| {label} | {b.get('n')} | ${b.get('expectancy')} | {b.get('wr')} | "
                 f"{'Y' if b.get('oos_positive') else 'N'} | {b.get('wf')} | {b.get('qpf')} | "
                 f"{b.get('mean_friction_pct_of_premium')} | {b.get('mean_theta_bleed_proxy')} | "
                 f"{nu.get('p_null')} | {'Y' if nu.get('bh_fdr_survivor') else 'N'} | **{v['verdict']}** |")
    L.append("")
    L.append("## OP-16 anchor check (non-negotiable, checked FIRST)")
    L.append("")
    a = out["anchor_check_op16"]
    L.append(f"3 J_WINNERS ride-the-ribbon days, naked ATM total = ${a['naked_total_3day']}.")
    L.append("")
    L.append("| variant | variant total (3d) | shortfall | shortfall % of naked | ANCHOR REGRESSION |")
    L.append("|---|--:|--:|--:|:--:|")
    for label, r in a["regressions"].items():
        L.append(f"| {label} | ${r['variant_total_3day']} | ${r['shortfall']} | "
                 f"{r['shortfall_pct_of_naked']} | {'**YES (FAIL)**' if r['anchor_regression'] else 'no'} |")
    L.append("")
    for row in a["rows"]:
        L.append(f"- {row['date']}: J's real fill pnl ${row['j_actual_real_fill_pnl']} | "
                 f"naked-ATM-convention ${row['naked_atm_convention_pnl']} | variants {row['variant_pnl']}")
    L.append("")
    L.append("**Caveat (read before trusting 'no regression' at face value):** the naked-ATM-convention "
             "total across these 3 days is ITSELF negative (\\$" + f"{a['naked_total_3day']}" +
             "), far from J's real +\\$1,542 across the same 3 days — because this study's ATM-long-leg "
             "convention is NOT J's actual historical strike/qty (see the pre-reg's anchor_check_op16."
             "signal_match_method). The spreads losing LESS than an already-losing ATM baseline on these "
             "specific days is not evidence spreads protect J's real edge; it means neither structure, "
             "replayed at ATM, reproduces what actually made these days winners. The anchor check's real "
             "job — did adding a short leg cap a payoff that was otherwise working — could not be "
             "meaningfully exercised here because the naked baseline itself doesn't reproduce the win. "
             "Treat `anchor_regression: no` as 'not disproven', not as a validated pass.")
    L.append("")
    L.append("## Corroboration (110 real-fill episodes, disclosure only)")
    L.append("")
    cn = out["corroboration_110_real_fills"]["naked"]
    L.append(f"n_positions={out['corroboration_110_real_fills']['n_positions']}, "
             f"n_replayed={out['corroboration_110_real_fills']['n_replayed']}. "
             f"Naked exp=${cn.get('expectancy')} (n={cn.get('n')}).")
    for label, agr in out["corroboration_110_real_fills"]["agreement"].items():
        L.append(f"- {label}: primary delta ${agr['primary_delta']}, corroboration delta "
                 f"${agr['corro_delta']}, same sign: {agr['same_sign']}")
    L.append("")
    L.append("## Disclosures")
    L.append("")
    for d in out["disclosures"]:
        L.append(f"- {d}")
    L.append("")
    L.append("---")
    L.append("_Source: `backtest/tools/debit_spread_ab_study.py`. Nothing ships from this file — "
             "a CANDIDATE_PASS still owes a J-visible REVOKE window per standing doctrine._")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())

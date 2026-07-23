"""backtest/tools/edge_matrix_sr_flip_retest.py -- S/R FLIP + RETEST edge-matrix runner.

Family: sr-flip-retest (J 07-21: 745.89 "S/R flipped" premarket; J 07-17: "13:50 is a nice
break and then retest"). A battle-tested horizontal level breaks (close-through by margin),
price leaves the zone, returns, retests the level from the OTHER side, and a confirm candle
is the entry. Both directions: break-UP -> support retest -> CALL; break-DOWN -> resistance
retest -> PUT.

Frozen pre-reg (written BEFORE this file ran): analysis/edge-matrix/prereg-sr-flip-retest-2026-07-23.json
Population:  analysis/edge-matrix/day-inventory-2026-07-23.json (heldout list HONORED --
             held-out days enter ONLY gate 4 / held_out_total, never tuning aggregates).

REUSE (never hand-rolled twice):
  levels  -> backtest/lib/watchers/level_memory.py LevelMemory (the LIVE perception layer)
  exits   -> backtest/lib/exit_manager_walk.walk_exit_manager (REAL production exit core),
             live RIBBON_RIDE shape via setup/scripts/dojo/sim_executor._resolve_exit_shape
  dollars -> backtest/lib/option_pricing_real (real OPRA 5m ONLY; a missing contract csv
             is excluded from gate math and disclosed as status=NO_REAL_OPRA -- BS-synthetic
             is never priced in this runner)
  ribbon  -> backtest/lib/ribbon.compute_ribbon over the full continuous source-file frame
  sizing  -> fleet_executor risk_gate.max_affordable_qty + V15 Safe (ATM) strike tiers

CAUSALITY (C6): bar i uses bars <= i only. Assert-checked two ways in this file:
  (a) structural: every signal's flip_idx <= retest_idx <= confirm_idx, and the level
      snapshot index is strictly BEFORE the day's first bar;
  (b) prefix-equality self-check: on sampled (day, cell) pairs the detector is re-run on
      every truncated prefix of the day and must emit exactly the full run's signals whose
      confirm_idx fits in the prefix. Any mismatch raises AssertionError and aborts.

Rail-4 CLEAR: research tool + JSON outputs only. NO live wiring, NO git ops, NO broker
imports (sim_executor/fleet_executor graphs are pinned broker-free by test_dojo_no_broker).

USAGE:
    backtest/.venv/Scripts/python.exe -m backtest.tools.edge_matrix_sr_flip_retest
"""
from __future__ import annotations

import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]  # .../42
for _p in ("backtest", "setup/scripts", "setup/scripts/dojo", "automation/state/fleet"):
    _ap = str(_ROOT / _p)
    if _ap not in sys.path:
        sys.path.insert(0, _ap)

from lib.watchers.level_memory import LevelMemory  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402
from lib.option_pricing_real import bar_at_or_after, load_contract_bars, option_symbol  # noqa: E402
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from dojo import sim_executor as se  # noqa: E402
import fleet_executor as fx  # noqa: E402  -- reuse risk_gate.max_affordable_qty

PREREG_PATH = _ROOT / "analysis" / "edge-matrix" / "prereg-sr-flip-retest-2026-07-23.json"
INVENTORY_PATH = _ROOT / "analysis" / "edge-matrix" / "day-inventory-2026-07-23.json"
EPISODES_PATH = _ROOT / "analysis" / "edge-matrix" / "sr-flip-retest-episodes.json"
RESULTS_PATH = _ROOT / "analysis" / "edge-matrix" / "sr-flip-retest-results-2026-07-23.json"
PARAMS_PATH = _ROOT / "automation" / "state" / "params.json"
DATA_DIR = _ROOT / "backtest" / "data"

ARM_ID = "safe"                # dojo alias -> accounts.json "safe-2" (CORE-SAFE, ATM tiers)
STRATEGY_NAME = "ribbon_ride"  # the LIVE flagship exit shape
STRUCTURE_STOP_ENABLED = True  # frozen per pre-reg (same for every cell)
MIN_MEMORY_SCORE = 20.0        # key-levels producer MIN_MEMORY floor (frozen, not a knob)
BASE_QTY = 3                   # live min_contracts
DEFAULT_EQUITY = 2000.0

# Decision-instant window (bar CLOSE times): 09:35 live entry gate .. 15:00 runway cutoff.
DECISION_MIN = dtime(9, 35)
DECISION_MAX = dtime(15, 0)


# =====================================================================================
# Grid
# =====================================================================================
@dataclass(frozen=True)
class CellParams:
    flip_margin_cents: int
    retest_band_cents: int
    confirm_mode: str  # "RETEST_CLOSE" | "NEXT_BAR_CLOSE"
    direction: str     # "BULL" | "BEAR"

    def cell_id(self) -> str:
        cm = "RC" if self.confirm_mode == "RETEST_CLOSE" else "NB"
        return f"m{self.flip_margin_cents}_b{self.retest_band_cents}_{cm}_{self.direction}"


def build_grid(prereg: dict) -> list[CellParams]:
    axes = prereg["grid_axes"]
    cells = []
    for m in axes["flip_margin_cents"]:
        for b in axes["retest_band_cents"]:
            for cm in axes["confirm_mode"]:
                for d in axes["direction"]:
                    cells.append(CellParams(int(m), int(b), str(cm), str(d)))
    return cells


# =====================================================================================
# Detector -- pure, causal state machine over ONE day's bars against a STATIC level set.
# =====================================================================================
@dataclass(frozen=True)
class Signal:
    day: str
    direction: str          # BULL | BEAR
    level_price: float
    memory_score: float
    snapshot_role: str
    flip_idx: int
    retest_idx: int
    confirm_idx: int
    flip_ts: str
    retest_ts: str
    confirm_ts: str
    decision_ts: str        # confirm bar close instant (bar_start + 5min) -- the entry instant
    entry_spot: float       # confirm bar close


def detect_day(opens: np.ndarray, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
               ts_list: list, levels: list[dict], p: CellParams, day_label: str) -> list[Signal]:
    """Causal by construction: the loop at bar i reads ONLY arrays[0..i] and per-level state
    built from bars < i. Levels are a STATIC prior-session snapshot (see main)."""
    margin = p.flip_margin_cents / 100.0
    band = p.retest_band_cents / 100.0
    n = len(closes)
    states = [{"price": float(lv["price"]), "mem": float(lv["mem"]),
               "role": str(lv["role"]), "snapshot_role": str(lv["role"]), "pending": None}
              for lv in levels]
    signals: list[Signal] = []

    for i in range(n):
        c = float(closes[i]); hi = float(highs[i]); lo = float(lows[i])
        bar_candidates: list[tuple[dict, dict, int, int]] = []  # (state, pending, retest_idx, confirm_idx)

        for st in states:
            L = st["price"]
            pend = st["pending"]
            # -- retest / confirm handling (only for the cell's direction; pendings of the
            #    other direction sit inert -- flips below still replace them causally).
            if pend is not None and not pend["consumed"] and pend["dir"] == p.direction:
                if pend["dir"] == "BULL":
                    in_zone = lo <= L + band
                    fully_clear = lo > L + band
                    confirm_ok = c > L
                else:
                    in_zone = hi >= L - band
                    fully_clear = hi < L - band
                    confirm_ok = c < L
                if pend["awaiting_confirm"]:
                    # NEXT_BAR_CLOSE: this bar is the confirm bar for pend["retest_idx"]
                    if confirm_ok:
                        bar_candidates.append((st, pend, pend["retest_idx"], i))
                    elif in_zone:
                        pend["retest_idx"] = i          # rolling retest, keep awaiting
                    else:
                        pend["awaiting_confirm"] = False  # left zone unconfirmed -> re-armed
                        pend["retest_idx"] = None
                elif pend["cleared"] and in_zone:
                    if p.confirm_mode == "RETEST_CLOSE":
                        if confirm_ok:
                            bar_candidates.append((st, pend, i, i))
                        # unconfirmed touch: stays armed for a later retest attempt
                    else:
                        pend["retest_idx"] = i
                        pend["awaiting_confirm"] = True
                elif not pend["cleared"] and fully_clear:
                    pend["cleared"] = True

            # -- flip / cancel detection on THIS bar's close (margin = grid knob). A flip
            #    replaces any pending wholesale (cancel + arm the new direction).
            if st["role"] == "resistance" and c >= L + margin:
                st["role"] = "support"
                st["pending"] = {"dir": "BULL", "flip_idx": i, "cleared": False,
                                 "retest_idx": None, "awaiting_confirm": False, "consumed": False}
            elif st["role"] == "support" and c <= L - margin:
                st["role"] = "resistance"
                st["pending"] = {"dir": "BEAR", "flip_idx": i, "cleared": False,
                                 "retest_idx": None, "awaiting_confirm": False, "consumed": False}

        if not bar_candidates:
            continue
        # same-bar tiebreak: highest memory_score wins (frozen in pre-reg)
        st, pend, retest_idx, confirm_idx = max(bar_candidates, key=lambda t: t[0]["mem"])
        # consume ALL candidates' pendings? No -- only the taken one; the others stay armed
        # (they never emitted). Consumption is per (level, flip) on emission only.
        pend["consumed"] = True
        pend["awaiting_confirm"] = False
        ts_confirm = ts_list[confirm_idx]
        decision_dt = ts_confirm + timedelta(minutes=5)
        if not (DECISION_MIN <= decision_dt.time() <= DECISION_MAX):
            continue
        sig = Signal(
            day=day_label, direction=p.direction, level_price=round(st["price"], 2),
            memory_score=round(st["mem"], 1), snapshot_role=st["snapshot_role"],
            flip_idx=int(pend["flip_idx"]), retest_idx=int(retest_idx), confirm_idx=int(confirm_idx),
            flip_ts=ts_list[pend["flip_idx"]].isoformat(), retest_ts=ts_list[retest_idx].isoformat(),
            confirm_ts=ts_confirm.isoformat(), decision_ts=decision_dt.isoformat(),
            entry_spot=float(closes[confirm_idx]),
        )
        # (a) structural causality assert -- every referenced index <= the decision index
        assert sig.flip_idx <= sig.retest_idx <= sig.confirm_idx, (
            f"CAUSALITY VIOLATION {day_label} {p.cell_id()}: {sig}")
        signals.append(sig)
    return signals


def causality_prefix_check(day_ctx: dict, cells: list[CellParams], sample_days: list[str]) -> int:
    """(b) prefix-equality self-check: detector on every truncated prefix must emit exactly
    the full run's signals with confirm_idx < prefix length. Raises on any mismatch."""
    n_checked = 0
    for d in sample_days:
        ctx = day_ctx.get(d)
        if ctx is None:
            continue
        o, h, lo, c, ts = ctx["opens"], ctx["highs"], ctx["lows"], ctx["closes"], ctx["ts"]
        for p in cells:
            full = detect_day(o, h, lo, c, ts, ctx["levels"], p, d)
            for m in range(1, len(c) + 1):
                sub = detect_day(o[:m], h[:m], lo[:m], c[:m], ts[:m], ctx["levels"], p, d)
                expected = [s for s in full if s.confirm_idx < m]
                assert [asdict(s) for s in sub] == [asdict(s) for s in expected], (
                    f"PREFIX CAUSALITY VIOLATION day={d} cell={p.cell_id()} prefix={m}: "
                    f"sub={len(sub)} expected={len(expected)}")
            n_checked += 1
    return n_checked


# =====================================================================================
# Data loading -- one continuous frame PER inventory source_file (dedupe honored).
# =====================================================================================
def load_frame(source_file: str) -> pd.DataFrame:
    df = pd.read_csv(DATA_DIR / source_file)
    # format="mixed": caches mix "YYYY-MM-DD HH:MM:SS-04:00" and ISO-T rows in one file;
    # every row carries its own explicit offset, so per-element parsing stays exact.
    ts = pd.to_datetime(df["timestamp_et"], utc=True, format="mixed").dt.tz_convert("America/New_York")
    df = df.assign(timestamp_et=ts)
    for col in ("open", "high", "low", "close"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[(ts.dt.time >= dtime(9, 30)) & (ts.dt.time < dtime(16, 0))]
    df = df.drop_duplicates(subset="timestamp_et").sort_values("timestamp_et").reset_index(drop=True)
    return df


# =====================================================================================
# Statistics (same conventions as pullback_hold_bull_replay / rsi probe -- reused style)
# =====================================================================================
def one_sample_p(pnls: list[float]) -> float:
    n = len(pnls)
    if n < 2:
        return 1.0
    mean = sum(pnls) / n
    var = sum((x - mean) ** 2 for x in pnls) / (n - 1)
    se_ = (var / n) ** 0.5
    if se_ == 0:
        return 1.0
    t = mean / se_
    p = 2.0 * (1.0 - 0.5 * (1.0 + math.erf(abs(t) / (2 ** 0.5))))
    return max(0.0, min(1.0, p))


# =====================================================================================
# Pricing + REAL exit walk (one position at a time per cell; walk results cached)
# =====================================================================================
_WALK_CACHE: dict[tuple, dict] = {}


def price_and_walk(sig: Signal, day_naive: pd.DataFrame, arm_cfg: dict, safe_params: dict,
                   time_stop: dtime, exit_shape: dict) -> dict:
    trade_date = date.fromisoformat(sig.day)
    side = "C" if sig.direction == "BULL" else "P"
    strike = se._strike_for(arm_cfg, sig.entry_spot, side)
    key = (sig.day, sig.decision_ts, side, strike, round(sig.level_price, 2))
    if key in _WALK_CACHE:
        return dict(_WALK_CACHE[key])

    symbol = option_symbol(trade_date, strike, side)
    row = {"symbol": symbol, "strike": strike, "side": side}
    # REAL OPRA ONLY (protocol): a missing contract csv is excluded from gate math and
    # disclosed (status=NO_REAL_OPRA). BS-synthetic is never priced in this runner -- the
    # pre-reg's "flagged is_synthetic" disclosure is realized as these excluded rows
    # (deviation-of-disclosure-shape only; gates/axes/population untouched -- noted in results).
    real = load_contract_bars(symbol)
    if real is None or real.empty:
        row.update(status="NO_REAL_OPRA")
        _WALK_CACHE[key] = row
        return dict(row)
    opt_df = real.copy()
    ts_col = opt_df["timestamp_et"]
    if getattr(ts_col.dt, "tz", None) is not None:
        ts_col = ts_col.dt.tz_convert("America/New_York").dt.tz_localize(None)
    opt_df = opt_df.assign(timestamp_et=ts_col).sort_values("timestamp_et").reset_index(drop=True)
    price_source, is_synth = "opra_5m", False
    decision_naive = pd.Timestamp(sig.decision_ts)
    fill = bar_at_or_after(opt_df, decision_naive)
    if fill is None:
        row.update(status="NO_FILL", price_source=price_source, is_synthetic=is_synth)
        _WALK_CACHE[key] = row
        return dict(row)
    entry_premium = round(float(fill.vwap), 4)
    afford = fx.risk_gate.max_affordable_qty(
        equity=float(arm_cfg.get("starting_equity", DEFAULT_EQUITY)), premium=entry_premium,
        params=safe_params)
    qty = min(BASE_QTY, int(afford or 0))
    if qty < 1:
        row.update(status="UNAFFORDABLE", entry_premium=entry_premium,
                   price_source=price_source, is_synthetic=is_synth)
        _WALK_CACHE[key] = row
        return dict(row)

    ribbon_tick_df = se._ribbon_aligned_to(day_naive, opt_df)
    result = walk_exit_manager(
        symbol=symbol, side=side, entry_time_et=fill.timestamp_et, entry_premium=entry_premium,
        qty=qty, exit_shape=exit_shape, structure_stop_enabled=STRUCTURE_STOP_ENABLED,
        trigger_level=float(sig.level_price), strategy=STRATEGY_NAME, time_stop_et=time_stop,
        opt_df=opt_df, ribbon_tick_df=ribbon_tick_df, five_min_spy_df=day_naive,
    )
    if result.exit_reason == "no_bars_after_entry":
        row.update(status="NO_BARS_AFTER_ENTRY", entry_premium=entry_premium,
                   price_source=price_source, is_synthetic=is_synth)
        _WALK_CACHE[key] = row
        return dict(row)
    row.update(
        status="FILLED", qty=qty, entry_premium=entry_premium, price_source=price_source,
        is_synthetic=bool(is_synth), pnl=float(result.dollar_pnl), exit_reason=result.exit_reason,
        hold_minutes=int(result.hold_minutes),
        exit_time_et=(result.exit_time_et.isoformat() if result.exit_time_et else None),
    )
    _WALK_CACHE[key] = row
    return dict(row)


# =====================================================================================
# main
# =====================================================================================
def main() -> dict:
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    inv = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))

    covered_days = [d["date"] for d in inv["days"]]
    src_of = {d["date"]: d["source_file"] for d in inv["days"]}
    opra_set = set(inv["opra_days"]) & set(covered_days)
    heldout_set = set(inv["heldout_days"])
    tuning_set = opra_set - heldout_set

    grid = build_grid(prereg)
    assert len(grid) == int(prereg["grid_size"]) == 16, "grid drifted from frozen pre-reg"

    # -- group days by their inventory-assigned source file (dedupe honored) -------------
    days_by_src: dict[str, list[str]] = {}
    for d in covered_days:
        days_by_src.setdefault(src_of[d], []).append(d)

    day_ctx: dict[str, dict] = {}
    skipped_days: list[dict] = []
    for src, days in sorted(days_by_src.items()):
        print(f"[frame] {src}: {len(days)} assigned days", file=sys.stderr)
        frame = load_frame(src)
        lm = LevelMemory(frame)
        ribbon = compute_ribbon(frame["close"].reset_index(drop=True))
        frame = frame.assign(stack=ribbon["stack"].values)
        frame_dates = frame["timestamp_et"].dt.date.values
        for dstr in sorted(days):
            day_date = date.fromisoformat(dstr)
            idxs = np.nonzero(frame_dates == day_date)[0]
            if len(idxs) == 0:
                skipped_days.append({"day": dstr, "reason": "NO_BARS_IN_ASSIGNED_FRAME"})
                continue
            first = int(idxs[0])
            if first == 0:
                skipped_days.append({"day": dstr, "reason": "NO_PRIOR_DAY_IN_FRAME"})
                continue
            prev = first - 1
            # level-snapshot causality: strictly prior-session bars only
            assert frame_dates[prev] < day_date, f"snapshot leak on {dstr}"
            levels_all = lm.levels_at(prev)
            levels = [{"price": L.price, "role": L.role, "mem": L.memory_score}
                      for L in levels_all if L.memory_score >= MIN_MEMORY_SCORE]
            day_df = frame.iloc[idxs].reset_index(drop=True)
            naive_ts = day_df["timestamp_et"].dt.tz_localize(None)
            day_naive = day_df.assign(timestamp_et=naive_ts)
            day_ctx[dstr] = {
                "opens": day_df["open"].values.astype(float),
                "highs": day_df["high"].values.astype(float),
                "lows": day_df["low"].values.astype(float),
                "closes": day_df["close"].values.astype(float),
                "ts": [t.to_pydatetime() for t in naive_ts],
                "levels": levels,
                "day_naive": day_naive,   # naive-ET RTH bars + 'stack' col (walk + ribbon + synth)
            }

    print(f"[days] contexts built: {len(day_ctx)}; skipped: {len(skipped_days)}", file=sys.stderr)

    # -- detector pass: all covered days, all 16 cells -----------------------------------
    signals_by_cell: dict[str, list[Signal]] = {p.cell_id(): [] for p in grid}
    for dstr in sorted(day_ctx):
        ctx = day_ctx[dstr]
        for p in grid:
            sigs = detect_day(ctx["opens"], ctx["highs"], ctx["lows"], ctx["closes"],
                              ctx["ts"], ctx["levels"], p, dstr)
            signals_by_cell[p.cell_id()].extend(sigs)

    # -- causality prefix self-check on a fixed sample (deterministic pick) --------------
    sample_days = sorted(day_ctx)[:: max(1, len(day_ctx) // 3)][:3]
    sample_cells = [grid[0], grid[-1]]
    n_checked = causality_prefix_check(day_ctx, sample_cells, sample_days)
    print(f"[causality] prefix-equality self-check PASS on {n_checked} (day,cell) pairs "
          f"days={sample_days}", file=sys.stderr)

    # -- pricing + REAL exit walk on OPRA days (one position at a time per cell) ---------
    arm_cfg, _canonical = se._resolve_arm_cfg(ARM_ID)
    safe_params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    time_stop = se._parse_hhmm(se._time_stop_et_for(arm_cfg))
    exit_shape = se._resolve_exit_shape(arm_cfg, STRATEGY_NAME, None)
    print(f"[exit-shape] {exit_shape} time_stop={time_stop} structure_stop={STRUCTURE_STOP_ENABLED}",
          file=sys.stderr)

    episodes_by_cell: dict[str, list[dict]] = {}
    for p in grid:
        cid = p.cell_id()
        episodes: list[dict] = []
        sigs = sorted(signals_by_cell[cid], key=lambda s: (s.day, s.decision_ts))
        busy_until: Optional[pd.Timestamp] = None
        busy_day: Optional[str] = None
        for sig in sigs:
            base = asdict(sig)
            base["cell_id"] = cid
            base["population"] = ("heldout" if sig.day in heldout_set
                                  else "tuning" if sig.day in tuning_set
                                  else "no_opra")
            if sig.day not in opra_set:
                base["status"] = "NOT_OPRA_DAY"
                episodes.append(base)
                continue
            decision = pd.Timestamp(sig.decision_ts)
            if busy_day == sig.day and busy_until is not None and decision < busy_until:
                base["status"] = "SKIPPED_OVERLAP"
                episodes.append(base)
                continue
            priced = price_and_walk(sig, day_ctx[sig.day]["day_naive"], arm_cfg, safe_params,
                                    time_stop, exit_shape)
            base.update(priced)
            episodes.append(base)
            if priced.get("status") == "FILLED":
                busy_day = sig.day
                exit_iso = priced.get("exit_time_et")
                busy_until = pd.Timestamp(exit_iso) if exit_iso else pd.Timestamp(
                    f"{sig.day}T16:00:00")
        episodes_by_cell[cid] = episodes
        n_filled = sum(1 for e in episodes if e.get("status") == "FILLED")
        print(f"[cell] {cid}: signals={len(sigs)} filled={n_filled}", file=sys.stderr)

    # -- aggregation + gates -------------------------------------------------------------
    cell_rows = []
    for p in grid:
        cid = p.cell_id()
        eps = episodes_by_cell[cid]
        n_signals = len(eps)  # every detector signal across all covered days (incl. skips)
        real_fills = [e for e in eps if e.get("status") == "FILLED" and not e.get("is_synthetic")]
        synth_fills = [e for e in eps if e.get("status") == "FILLED" and e.get("is_synthetic")]
        tun = [e for e in real_fills if e["population"] == "tuning"]
        held = [e for e in real_fills if e["population"] == "heldout"]

        pnls = [float(e["pnl"]) for e in tun]
        total = round(sum(pnls), 2)
        n = len(pnls)
        by_day: dict[str, float] = {}
        for e in tun:
            by_day[e["day"]] = by_day.get(e["day"], 0.0) + float(e["pnl"])
        n_days = len(by_day)
        day_wins = sum(1 for v in by_day.values() if v > 0)
        day_wr = round(day_wins / n_days, 3) if n_days else 0.0
        top_sorted = sorted(pnls, reverse=True)
        ex_top1 = round(total - (top_sorted[0] if top_sorted else 0.0), 2)
        ex_top3 = round(total - sum(top_sorted[:3]), 2)
        held_total = round(sum(float(e["pnl"]) for e in held), 2)
        p_raw = round(one_sample_p(pnls), 4)

        gate_1 = total > 0
        gate_2 = n_days > 0 and day_wins > (n_days / 2.0)
        gate_3 = n > 0 and ex_top1 > 0
        gate_4 = len(held) > 0 and held_total > 0
        gates_passed = int(gate_1) + int(gate_2) + int(gate_3) + int(gate_4)

        cell_rows.append({
            "cell_id": cid, "params": asdict(p),
            "n_signals": n_signals,
            "n_real_fills": n,
            "expectancy": round(total / n, 2) if n else 0.0,
            "total_pnl": total,
            "day_wr": day_wr,
            "ex_top1_total": ex_top1,
            "ex_top3_total": ex_top3,
            "held_out_total": held_total,
            "n_heldout_fills": len(held),
            "p_raw": p_raw,
            "gate_1_positive_aggregate": gate_1,
            "gate_2_day_majority": gate_2,
            "gate_3_survives_ex_top1": gate_3,
            "gate_4_heldout_positive": gate_4,
            "gates_passed": gates_passed,
            "win_rate": round(sum(1 for x in pnls if x > 0) / n, 3) if n else 0.0,
            "n_tuning_days_with_fills": n_days,
            "disclosures": {
                "n_synth_excluded": len(synth_fills),  # always 0: synthetic never priced here
                "n_missing_real_opra": sum(1 for e in eps if e.get("status") == "NO_REAL_OPRA"),
                "n_skipped_overlap": sum(1 for e in eps if e.get("status") == "SKIPPED_OVERLAP"),
                "n_unaffordable": sum(1 for e in eps if e.get("status") == "UNAFFORDABLE"),
                "n_no_fill": sum(1 for e in eps if e.get("status") in
                                 ("NO_FILL", "NO_BARS_AFTER_ENTRY")),
                "n_not_opra_day": sum(1 for e in eps if e.get("status") == "NOT_OPRA_DAY"),
            },
        })

    # -- sanity anchor (DIAGNOSTIC ONLY, evaluated after the frozen pass) ----------------
    anchor_hits = []
    for p in grid:
        if p.direction != "BEAR":
            continue
        for e in episodes_by_cell[p.cell_id()]:
            if e["day"] == "2026-07-17":
                t = pd.Timestamp(e["decision_ts"]).time()
                if dtime(13, 40) <= t <= dtime(14, 15):
                    anchor_hits.append({"cell_id": e["cell_id"], "decision_ts": e["decision_ts"],
                                        "level": e["level_price"], "status": e.get("status")})
    anchor = {"anchor": prereg["sanity_anchor_diagnostic_only"]["anchor"],
              "hits": anchor_hits, "hit": bool(anchor_hits)}

    cell_rows.sort(key=lambda r: (r["gates_passed"], r["expectancy"]), reverse=True)

    results = {
        "generated_at": datetime.now().isoformat(),
        "family": "sr-flip-retest",
        "prereg_file": str(PREREG_PATH.relative_to(_ROOT)).replace("\\", "/"),
        "grid_size": len(grid),
        "population": {
            "covered_days": len(covered_days), "day_contexts_built": len(day_ctx),
            "days_skipped": skipped_days, "opra_days": len(opra_set),
            "tuning_days": len(tuning_set), "heldout_days": len(heldout_set),
        },
        "fixed_execution": {
            "arm": ARM_ID, "strategy": STRATEGY_NAME, "structure_stop_enabled": STRUCTURE_STOP_ENABLED,
            "exit_shape": exit_shape, "time_stop_et": str(time_stop),
            "min_memory_score": MIN_MEMORY_SCORE, "base_qty": BASE_QTY,
        },
        "causality_self_check": {"prefix_pairs_checked": n_checked, "sample_days": sample_days},
        "execution_notes": [
            "DISCLOSURE-SHAPE DEVIATION from pre-reg (gates/axes/population untouched): the "
            "pre-reg said BS-synthetic fallback episodes would be 'flagged is_synthetic' and "
            "excluded; this runner never prices synthetic at all -- OPRA days whose exact "
            "contract csv is absent are excluded from gate math and disclosed as "
            "status=NO_REAL_OPRA (root cause: sim_executor's synthetic path crashes on "
            "mixed-DST VIX caches; pricing synthetic was disclosure-only either way).",
        ],
        "sanity_anchor_diagnostic": anchor,
        "cells": cell_rows,
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")

    episodes_payload = {
        "family": "sr-flip-retest",
        "generated_at": results["generated_at"],
        "prereg_file": results["prereg_file"],
        "note": ("Episode-level detail for verifier recompute. status=FILLED with "
                 "is_synthetic=false and population=tuning are the ONLY rows entering "
                 "tuning gate math; population=heldout FILLED real rows feed gate 4 only. "
                 "BS-synthetic rows are disclosed, never gated."),
        "episodes_by_cell": episodes_by_cell,
    }
    EPISODES_PATH.write_text(json.dumps(episodes_payload, indent=0, default=str), encoding="utf-8")
    print(f"[written] {RESULTS_PATH}", file=sys.stderr)
    print(f"[written] {EPISODES_PATH}", file=sys.stderr)

    for r in cell_rows:
        print(f"  {r['cell_id']:22s} gates={r['gates_passed']} n={r['n_real_fills']:4d} "
              f"total=${r['total_pnl']:>10.2f} exp=${r['expectancy']:>8.2f} day_wr={r['day_wr']:.3f} "
              f"held=${r['held_out_total']:>9.2f} p={r['p_raw']}")
    return results


if __name__ == "__main__":
    main()

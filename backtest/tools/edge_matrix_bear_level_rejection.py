"""backtest/tools/edge_matrix_bear_level_rejection.py -- EDGE-MATRIX family runner:
bear-level-rejection (LEVEL REJECTION bear puts -- the proven live family, REFINEMENT grid).

Frozen pre-reg (written BEFORE this module ran): analysis/edge-matrix/
prereg-bear-level-rejection-2026-07-23.json -- 3 knobs x 18 cells:
    zone_band_dollars in {0.00, 0.20}   (0.00 = live penny-exact; 0.20 = LevelMemory TOUCH_TOL)
    nth_touch_min     in {1, 2, 3}      (J 07-17 dojo thesis: repeated rejection => put)
    confirmation      in {close_below, red_bar, none}
Baseline cell band0.00|nth1|close_below replicates the LIVE trigger exactly
(backtest/lib/filters.py detect_level_rejection: bar.high > level AND bar.close < level,
max rejected level, no touch-count requirement).

LEVEL SOURCE (never invented): backtest/lib/watchers/level_memory.py LevelMemory over the
continuous RTH 5m frame, lookback_days=10 / memory_score >= 20.0 -- byte-matched to the live
key-levels-memory producer (setup/scripts/level_memory_producer.py LOOKBACK_DAYS / MIN_MEMORY).

EXITS (identical for all 18 cells -- entry-side tuning ONLY): the LIVE RIBBON_RIDE shape via
dojo sim_executor._resolve_exit_shape(safe arm, "ribbon_ride", None), walked through
backtest/lib/exit_manager_walk.walk_exit_manager (the REAL production exit_manager core).
structure stop enabled per params.json; trigger_level = the rejected level price.

DOLLARS: real OPRA fills only (option_pricing_real.load_contract_bars). NO BS-synthetic
anywhere -- uncached contracts are counted + disclosed as NO_OPRA skips, never priced.

TIMESTAMP FRAME (prereg amendment 1, pre-results): TRUE ET -- per-row offset -> UTC ->
DST-aware America/New_York -> naive wall, applied uniformly to SPY AND OPRA (see _true_et
for the verified patchwork-store evidence that killed the wall-v1 offset-strip plan: it
misaligned SPY vs OPRA by 1h on 2026 winter days, leakage direction).

CAUSALITY (C6): LevelMemory is causal by construction (guard-tested); the detector receives
only day arrays sliced to <= the signal bar; and this module ADDITIONALLY assert-checks a
deterministic sample of signals by recomputing levels on a TRUNCATED frame (bars <= signal
bar only) and requiring the exact same level list (test_level_memory truncation pattern).

Rail-4 CLEAR: research tool + JSON outputs. Touches NO params/orders/filters/heartbeat_core/
strategies.py/CLAUDE.md. No broker import. No git operations. No live wiring.

Run: backtest/.venv/Scripts/python.exe backtest/tools/edge_matrix_bear_level_rejection.py
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
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
from lib.exit_manager_walk import walk_exit_manager  # noqa: E402
from lib.option_pricing_real import bar_at_or_after, load_contract_bars, option_symbol  # noqa: E402
from tools.pullback_hold_bull_replay import _one_sample_p  # noqa: E402  -- reused stat convention
from dojo import sim_executor as se  # noqa: E402
import fleet_executor as fx  # noqa: E402  -- reuse risk_gate.max_affordable_qty (broker-free, guard-tested)

PREREG_PATH = _ROOT / "analysis" / "edge-matrix" / "prereg-bear-level-rejection-2026-07-23.json"
INVENTORY_PATH = _ROOT / "analysis" / "edge-matrix" / "day-inventory-2026-07-23.json"
EPISODES_PATH = _ROOT / "analysis" / "edge-matrix" / "bear-level-rejection-episodes.json"
RESULTS_PATH = _ROOT / "analysis" / "edge-matrix" / "bear-level-rejection-results-2026-07-23.json"
PARAMS_PATH = _ROOT / "automation" / "state" / "params.json"
DATA_DIR = _ROOT / "backtest" / "data"

# Live level-vocabulary config -- setup/scripts/level_memory_producer.py (LOOKBACK_DAYS / MIN_MEMORY)
LM_LOOKBACK_DAYS = 10
LM_MIN_MEMORY = 20.0
DEDUPE_TOL = 0.35        # LevelMemory CLUSTER_TOL -- one signal per (level, touch-episode)
ENTRY_DELAY = timedelta(minutes=5)   # signal bar closes, entry fills in the NEXT 5m bar
STRATEGY_NAME = "ribbon_ride"
ARM_ID = "safe"

# entry window: read fresh from params.json in main() (09:35 / 15:00 as of freeze)


@dataclass(frozen=True)
class Cell:
    band: float
    nth: int
    confirm: str  # close_below | red_bar | none

    def cell_id(self) -> str:
        return f"band{self.band:.2f}|nth{self.nth}|{self.confirm}"


def log(msg: str) -> None:
    print(f"[edge-matrix-bear-level-rejection] {msg}", flush=True)


def _true_et(series: pd.Series) -> pd.Series:
    """TRUE-ET frame (prereg amendment 1, matches the day-inventory's own method note):
    per-row offset -> UTC -> US-DST-aware America/New_York -> naive true-ET wall.

    WHY (found live this build, BEFORE any full-run results were read): the SPY master is
    a display-frame PATCHWORK -- the 2025 winter stratum is stored fixed -04:00 (wall
    10:30 RTH start) while the 2026 winter stratum is stored true-EST (-05:00, wall 09:30
    start); the OPRA cache is uniformly fixed -04:00. A naive offset-STRIP therefore
    misaligns SPY vs OPRA by exactly 1h on 2026 winter days -- fills would price off
    option prints from BEFORE the signal (leakage direction). All strata carry CORRECT
    UTC instants (verified: SPY 2025-01-07 10:30-04:00 == OPRA 10:30-04:00 == 09:30 EST
    true), so converting EVERY store through UTC to DST-aware ET aligns everything AND
    makes RTH slicing / entry windows / time stops read TRUE ET -- exactly live semantics."""
    if pd.api.types.is_datetime64_any_dtype(series):
        if getattr(series.dt, "tz", None) is None:
            raise ValueError(
                "tz-naive datetime series: frame unknowable -- refuse to guess (C6). "
                "All cache stores carry per-row offsets; a naive column here is a bug.")
        return series.dt.tz_convert("America/New_York").dt.tz_localize(None)
    ts = pd.to_datetime(series, format="mixed", utc=True)
    return ts.dt.tz_convert("America/New_York").dt.tz_localize(None)


# =====================================================================================
# SPY frame -- built per-day from each inventory day's OWN designated source_file.
# =====================================================================================
def load_spy_frame(inventory: dict) -> pd.DataFrame:
    """Per-day frame assembly from each inventory day's designated source_file, in TRUE ET.

    OFFSET-LESS SOURCE FALLBACK (found + verified this build): spy_5m_2025-01-01_
    2026-05-19_merged.csv stores NO per-row offsets (31,350 naive rows), and its naive
    wall numbers are a frame PATCHWORK internally (2025 winter stratum = EDT-frame wall,
    2026 winter stratum = EST-frame wall) -- unknowable per-row, so _true_et refuses it.
    Exactly 3 inventory days designate it (the 2025 half-days 07-03 / 11-28 / 12-24), and
    ALL 3 exist row-identical WITH offsets in spy_5m_2025-06-01_2025-12-31.csv (verified:
    same row counts, byte-identical closes). Deterministic rule: if a day's designated
    source is offset-less, re-source that day from the other inventory source files
    (first one yielding >= 30 true-ET RTH bars wins); fail LOUD if none does."""
    sources = list(dict.fromkeys(r["source_file"] for r in inventory["days"]))
    parsed: dict[str, Optional[pd.DataFrame]] = {}
    cols = ["timestamp_et", "open", "high", "low", "close", "volume"]

    def _load(src: str) -> Optional[pd.DataFrame]:
        if src in parsed:
            return parsed[src]
        raw = pd.read_csv(DATA_DIR / src)
        s = raw["timestamp_et"].astype(str)
        if not s.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})\s*$", regex=True).all():
            log(f"  source {src}: offset-less timestamps -- frame unknowable, unusable")
            parsed[src] = None
            return None
        raw["timestamp_et"] = _true_et(raw["timestamp_et"])
        for c in ("open", "high", "low", "close"):
            raw[c] = pd.to_numeric(raw[c], errors="coerce")
        parsed[src] = raw
        return raw

    parts: list[pd.DataFrame] = []
    n_resourced = 0
    for rec in inventory["days"]:
        day = date.fromisoformat(rec["date"])
        chosen = None
        for src in [rec["source_file"]] + [s for s in sources if s != rec["source_file"]]:
            df = _load(src)
            if df is None:
                continue
            t = df["timestamp_et"]
            m = (t.dt.date == day) & (t.dt.time >= dtime(9, 30)) & (t.dt.time < dtime(16, 0))
            d = (df.loc[m, cols]
                   .drop_duplicates(subset="timestamp_et", keep="last")
                   .sort_values("timestamp_et"))
            if len(d) >= 30:  # the inventory's own per-day coverage rule
                chosen = (src, d)
                break
        assert chosen is not None, (
            f"{rec['date']}: no offset-carrying source file yields >= 30 true-ET RTH bars")
        if chosen[0] != rec["source_file"]:
            n_resourced += 1
            log(f"  re-sourced {rec['date']}: designated {rec['source_file']} unusable "
                f"-> {chosen[0]} ({len(chosen[1])} RTH bars)")
        parts.append(chosen[1])
    if n_resourced:
        log(f"  re-sourced days total: {n_resourced}")
    out = pd.concat(parts, ignore_index=True).sort_values("timestamp_et").reset_index(drop=True)
    assert out["timestamp_et"].is_monotonic_increasing, "SPY frame not time-ordered"
    assert not out["timestamp_et"].duplicated().any(), "duplicate timestamps in SPY frame"
    return out


# =====================================================================================
# Detector -- pure, causal. Receives only per-day arrays; levels come from a per-bar
# cache computed via LevelMemory.levels_at(g) (bars <= g only, by construction).
# =====================================================================================
def _episode_index(highs_upto_incl: np.ndarray, p: float, band: float) -> int:
    """1-based index of the CURRENT tag-episode of zone [p-band, ...] among today's bars.
    Causal: caller passes highs[:i+1] only."""
    tags = highs_upto_incl > (p - band)
    d = np.diff(tags.astype(np.int8))
    return int(tags[0]) + int(np.count_nonzero(d == 1))


def detect_cell_day(highs: np.ndarray, opens: np.ndarray, closes: np.ndarray,
                    gidxs: np.ndarray, levels_cache: dict[int, list[float]],
                    cell: Cell) -> list[dict]:
    """One day, one cell. Returns signal dicts (local_i, gidx, level, episode).
    hot-zone list implements the pre-reg per-(level, episode) dedupe."""
    signals: list[dict] = []
    hot: list[float] = []
    n = len(gidxs)
    for i in range(n):
        hi = float(highs[i])
        # a zone stays hot only while the current bar still tags it (episode continues)
        hot = [z for z in hot if hi > z - cell.band]
        lv = levels_cache.get(int(gidxs[i]))
        if not lv:
            continue
        cl = float(closes[i])
        op = float(opens[i])
        best: Optional[float] = None
        best_ep: Optional[int] = None
        for p in lv:
            if not (hi > p - cell.band):                      # tag (live reach condition at band=0)
                continue
            if cell.confirm == "close_below":
                if not (cl < p - cell.band):
                    continue
            elif cell.confirm == "red_bar":
                if not (cl < op):
                    continue
            # confirm == "none": tag alone
            upto = highs[: i + 1]
            assert upto.shape[0] == i + 1, "causality: episode slice must end at signal bar"
            ep = _episode_index(upto, p, cell.band)
            if ep < cell.nth:
                continue
            if any(abs(p - z) <= DEDUPE_TOL for z in hot):    # per-episode dedupe
                continue
            if best is None or p > best:                       # live convention: max rejected level
                best, best_ep = p, ep
        if best is not None:
            signals.append({"local_i": i, "gidx": int(gidxs[i]), "level": round(best, 2),
                            "episode": int(best_ep)})
            hot.append(best)
    return signals


# =====================================================================================
# Fill + exit walk (real OPRA only; walk result cached across cells sharing a signal)
# =====================================================================================
def fill_and_walk_day(day_str: str, signals: list[dict], spy_ts: pd.Series,
                      spy_close: np.ndarray, day_slice_naive: pd.DataFrame,
                      arm_cfg: dict, safe_params: dict, exit_shape: dict,
                      structure_stop_enabled: bool, time_stop: dtime,
                      min_entry_premium: float, walk_cache: dict) -> list[dict]:
    out: list[dict] = []
    trade_date = date.fromisoformat(day_str)
    eod = datetime.combine(trade_date, dtime(16, 0))
    busy_until: Optional[pd.Timestamp] = None
    for s in signals:
        g = s["gidx"]
        sig_ts = pd.Timestamp(spy_ts.iloc[g])
        entry_ts = sig_ts + ENTRY_DELAY
        rec = {"day": day_str, "gidx": g, "signal_ts": sig_ts.isoformat(),
               "entry_ts": entry_ts.isoformat(), "level": s["level"], "episode": s["episode"]}
        if busy_until is not None and entry_ts <= busy_until:
            rec["status"] = "SKIPPED_IN_POSITION"
            out.append(rec)
            continue
        spot = float(spy_close[g])
        strike = se._strike_for(arm_cfg, spot, "P")
        symbol = option_symbol(trade_date, strike, "P")
        rec.update({"strike": strike, "symbol": symbol, "spot_at_signal": round(spot, 2)})
        raw = load_contract_bars(symbol)
        if raw is None or raw.empty:
            rec["status"] = "NO_OPRA"
            out.append(rec)
            continue
        opt = raw.copy()
        opt["timestamp_et"] = _true_et(opt["timestamp_et"])
        opt = opt.sort_values("timestamp_et").reset_index(drop=True)
        fill = bar_at_or_after(opt, entry_ts)
        if fill is None:
            rec["status"] = "NO_FILL"
            out.append(rec)
            continue
        prem = round(float(fill.vwap), 4)
        rec["entry_premium"] = prem
        if prem < min_entry_premium:
            rec["status"] = "BELOW_MIN_PREMIUM"
            out.append(rec)
            continue
        base_qty = int(safe_params.get("min_contracts", 3))
        afford = fx.risk_gate.max_affordable_qty(
            equity=float(arm_cfg.get("starting_equity", 2000.0)), premium=prem, params=safe_params)
        qty = min(base_qty, afford) if afford else base_qty   # pullback_hold_bull_replay convention
        if qty < 1:
            rec["status"] = "UNAFFORDABLE"
            out.append(rec)
            continue
        key = (day_str, str(fill.timestamp_et), symbol, qty, round(s["level"], 2))
        res = walk_cache.get(key)
        if res is None:
            ribbon_tick_df = se._ribbon_aligned_to(day_slice_naive, opt)
            res = walk_exit_manager(
                symbol=symbol, side="P", entry_time_et=fill.timestamp_et, entry_premium=prem,
                qty=qty, exit_shape=exit_shape, structure_stop_enabled=structure_stop_enabled,
                trigger_level=float(s["level"]), strategy=STRATEGY_NAME, time_stop_et=time_stop,
                opt_df=opt, ribbon_tick_df=ribbon_tick_df, five_min_spy_df=day_slice_naive)
            walk_cache[key] = res
        if res.exit_reason == "no_bars_after_entry":
            rec["status"] = "NO_BARS_AFTER_ENTRY"
            out.append(rec)
            busy_until = pd.Timestamp(eod)
            continue
        rec.update({"status": "FILLED", "qty": qty, "pnl": round(res.dollar_pnl, 2),
                    "exit_reason": res.exit_reason, "hold_minutes": res.hold_minutes,
                    "fill_ts": str(fill.timestamp_et)})
        out.append(rec)
        busy_until = pd.Timestamp(res.exit_time_et) if res.exit_time_et is not None else pd.Timestamp(eod)
    return out


# =====================================================================================
# Causality audit -- truncated-frame recompute (test_level_memory truncation pattern)
# =====================================================================================
def causality_audit(spy_et: pd.DataFrame, lm_full: LevelMemory,
                    sampled_gidxs: list[int]) -> list[dict]:
    audits = []
    for g in sampled_gidxs:
        full_levels = [(lv.price, round(lv.memory_score, 6)) for lv in
                       lm_full.levels_at(g, lookback_days=LM_LOOKBACK_DAYS)]
        lm_trunc = LevelMemory(spy_et.iloc[: g + 1])
        trunc_levels = [(lv.price, round(lv.memory_score, 6)) for lv in
                        lm_trunc.levels_at(g, lookback_days=LM_LOOKBACK_DAYS)]
        assert full_levels == trunc_levels, (
            f"CAUSALITY VIOLATION at gidx={g}: full-frame levels != truncated-frame levels\n"
            f"full={full_levels}\ntrunc={trunc_levels}")
        audits.append({"gidx": g, "n_levels": len(full_levels), "match": True})
    return audits


# =====================================================================================
# Per-cell metrics + gates
# =====================================================================================
def cell_metrics(cell: Cell, rows: list[dict], tuning_set: set[str], heldout_set: set[str]) -> dict:
    tun = [r for r in rows if r["day"] in tuning_set]
    held = [r for r in rows if r["day"] in heldout_set]
    n_signals = len(tun)
    fills = [r for r in tun if r["status"] == "FILLED"]
    pnls = [r["pnl"] for r in fills]
    n = len(fills)
    total = round(sum(pnls), 2)
    expectancy = round(total / n, 2) if n else 0.0

    by_day: dict[str, float] = {}
    for r in fills:
        by_day[r["day"]] = by_day.get(r["day"], 0.0) + r["pnl"]
    n_days = len(by_day)
    day_wins = sum(1 for v in by_day.values() if v > 0)
    day_wr = round(day_wins / n_days, 3) if n_days else 0.0

    desc = sorted(pnls, reverse=True)
    ex_top1 = round(total - sum(desc[:1]), 2) if n else 0.0
    ex_top3 = round(total - sum(desc[:3]), 2) if n else 0.0

    held_fills = [r for r in held if r["status"] == "FILLED"]
    held_total = round(sum(r["pnl"] for r in held_fills), 2)

    p_raw = round(_one_sample_p(pnls), 5) if n >= 2 else 1.0

    g1 = total > 0
    g2 = n_days > 0 and day_wins > (n_days / 2.0)
    g3 = n >= 1 and ex_top1 > 0
    g4 = len(held_fills) > 0 and held_total > 0

    def _count(status: str, pop: list[dict]) -> int:
        return sum(1 for r in pop if r["status"] == status)

    return {
        "cell_id": cell.cell_id(),
        "params": {"zone_band_dollars": cell.band, "nth_touch_min": cell.nth,
                   "confirmation": cell.confirm},
        "n_signals": n_signals,
        "n_real_fills": n,
        "expectancy": expectancy,
        "total_pnl": total,
        "day_wr": day_wr,
        "n_days_covered": n_days,
        "n_day_wins": day_wins,
        "ex_top1_total": ex_top1,
        "ex_top3_total": ex_top3,
        "held_out_total": held_total,
        "n_heldout_fills": len(held_fills),
        "n_heldout_signals": len(held),
        "p_raw": p_raw,
        "gates": {"g1_positive_aggregate": g1, "g2_day_majority": g2,
                  "g3_survives_ex_top1": g3, "g4_held_out_positive": g4},
        "gates_passed": int(g1) + int(g2) + int(g3) + int(g4),
        "below_evidence_floor_n15": n < 15,
        "skips_tuning": {
            "skipped_in_position": _count("SKIPPED_IN_POSITION", tun),
            "no_opra": _count("NO_OPRA", tun),
            "no_fill": _count("NO_FILL", tun),
            "below_min_premium": _count("BELOW_MIN_PREMIUM", tun),
            "unaffordable": _count("UNAFFORDABLE", tun),
            "no_bars_after_entry": _count("NO_BARS_AFTER_ENTRY", tun),
        },
    }


# =====================================================================================
# main
# =====================================================================================
def main(smoke_days: int = 0) -> dict:
    prereg = json.loads(PREREG_PATH.read_text(encoding="utf-8"))
    inv = json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    log(f"frozen pre-reg loaded: {PREREG_PATH.name} frozen_at={prereg['frozen_at']}")

    covered = {r["date"] for r in inv["days"]}
    heldout = [d for d in inv["heldout_days"] if d in covered]
    opra = [d for d in inv["opra_days"] if d in covered]
    heldout_set = set(heldout)
    tuning = [d for d in opra if d not in heldout_set]
    tuning_set = set(tuning)
    signal_days = tuning + heldout
    results_path, episodes_path = RESULTS_PATH, EPISODES_PATH
    if smoke_days:
        # SMOKE MODE: correctness shakedown only -- tiny day subset, scratch outputs,
        # NEVER the real result/episode files. The frozen grid itself is unchanged.
        signal_days = tuning[:smoke_days] + heldout[:max(1, smoke_days // 4)]
        import tempfile
        _scratch = Path(tempfile.gettempdir())
        results_path = _scratch / "edge_matrix_blr_results.SMOKE.json"
        episodes_path = _scratch / "edge_matrix_blr_episodes.SMOKE.json"
        log(f"SMOKE MODE: {len(signal_days)} days only -> {results_path.name}")
    log(f"days: covered={len(covered)} opra(signal)={len(signal_days)} "
        f"tuning={len(tuning)} heldout={len(heldout)} "
        f"(heldout honored: {heldout[0]}..{heldout[-1]})")

    log("building continuous RTH SPY frame from inventory per-day source files ...")
    spy = load_spy_frame(inv)
    log(f"  spy rows={len(spy)} range={spy['timestamp_et'].iloc[0]}..{spy['timestamp_et'].iloc[-1]}")

    spy_et = spy.copy()
    spy_et["timestamp_et"] = spy["timestamp_et"].dt.tz_localize("America/New_York")
    lm = LevelMemory(spy_et)

    ribbon_df = compute_ribbon(spy["close"].reset_index(drop=True))
    stacks = ribbon_df["stack"].values
    spy_with_stack = spy.copy()
    spy_with_stack["stack"] = stacks

    safe_params = json.loads(PARAMS_PATH.read_text(encoding="utf-8"))
    arm_cfg, canonical = se._resolve_arm_cfg(ARM_ID)
    exit_shape = se._resolve_exit_shape(arm_cfg, STRATEGY_NAME, None)
    structure_stop_enabled = se._structure_stop_enabled()
    time_stop = se._parse_hhmm(se._time_stop_et_for(arm_cfg))
    min_entry_premium = float(safe_params.get("min_entry_premium", 0.3))
    ent_before = se._parse_hhmm(safe_params.get("entry_no_trade_before_et", "09:35"))
    ent_after = se._parse_hhmm(safe_params.get("entry_no_trade_after_et", "15:00"))
    log(f"arm={canonical} exit_shape={exit_shape} structure_stop={structure_stop_enabled} "
        f"time_stop={time_stop} entry_window=[{ent_before},{ent_after}) "
        f"min_premium={min_entry_premium}")

    # per-day global index map + candidate bars
    ts = spy["timestamp_et"]
    dates_str = ts.dt.date.astype(str).values
    day_gidx: dict[str, np.ndarray] = {}
    for d in signal_days:
        day_gidx[d] = np.flatnonzero(dates_str == d)
    spy_close = spy["close"].to_numpy()
    spy_open = spy["open"].to_numpy()
    spy_high = spy["high"].to_numpy()

    # candidate = entry (signal+5m) inside the live window AND ribbon BEAR at signal bar
    times = np.array([t.time() for t in ts], dtype=object)
    entry_lo = (datetime.combine(date(2000, 1, 1), ent_before) - ENTRY_DELAY).time()
    entry_hi = (datetime.combine(date(2000, 1, 1), ent_after) - ENTRY_DELAY).time()
    candidates: dict[str, np.ndarray] = {}
    n_cand = 0
    for d in signal_days:
        gs = day_gidx[d]
        mask = np.array([(entry_lo <= times[g] < entry_hi) and (stacks[g] == "BEAR")
                         for g in gs])
        candidates[d] = gs[mask]
        n_cand += int(mask.sum())
    log(f"candidate signal bars (entry-window + ribbon BEAR): {n_cand}")

    # per-candidate-bar level cache -- ONE LevelMemory pass shared by all 18 cells
    log("computing LevelMemory levels per candidate bar (lookback=10d, memory>=20) ...")
    levels_cache: dict[int, list[float]] = {}
    done = 0
    for k, d in enumerate(signal_days):
        for g in candidates[d]:
            levels_cache[int(g)] = [
                lv.price for lv in lm.levels_at(int(g), lookback_days=LM_LOOKBACK_DAYS)
                if lv.memory_score >= LM_MIN_MEMORY]
            done += 1
        if (k + 1) % 40 == 0:
            log(f"  levels: day {k + 1}/{len(signal_days)} ({done}/{n_cand} bars)")

    # grid from the frozen pre-reg (never re-typed)
    axes = prereg["grid"]["axes"]
    grid = [Cell(float(b), int(n), c)
            for b in axes["zone_band_dollars"]
            for n in axes["nth_touch_min"]
            for c in axes["confirmation"]]
    assert len(grid) == prereg["grid"]["n_cells"] == 18
    log(f"grid: {len(grid)} cells (baseline = {prereg['grid']['baseline_cell']})")

    # detect + fill + walk
    walk_cache: dict = {}
    episodes: dict[str, list[dict]] = {}
    day_slices_naive: dict[str, pd.DataFrame] = {}
    for d in signal_days:
        sl = spy_with_stack.iloc[day_gidx[d]].reset_index(drop=True)
        day_slices_naive[d] = sl
    for ci, cell in enumerate(grid):
        cid = cell.cell_id()
        rows: list[dict] = []
        for d in signal_days:
            gs = day_gidx[d]
            sigs = detect_cell_day(spy_high[gs], spy_open[gs], spy_close[gs], gs,
                                   levels_cache, cell)
            if not sigs:
                continue
            rows.extend(fill_and_walk_day(
                d, sigs, ts, spy_close, day_slices_naive[d], arm_cfg, safe_params,
                exit_shape, structure_stop_enabled, time_stop, min_entry_premium, walk_cache))
        episodes[cid] = rows
        n_fill = sum(1 for r in rows if r["status"] == "FILLED")
        log(f"  cell {ci + 1}/18 {cid}: signals={len(rows)} fills={n_fill}")

    # causality audit on a deterministic sample of baseline-cell signal bars
    base_id = "band0.00|nth1|close_below"
    base_g = sorted({int(r["gidx"]) for r in episodes.get(base_id, [])})
    sample: list[int] = []
    if base_g:
        picks = {0, len(base_g) // 4, len(base_g) // 2, (3 * len(base_g)) // 4, len(base_g) - 1}
        sample = sorted({base_g[i] for i in picks})
    audits = causality_audit(spy_et, lm, sample)
    log(f"causality audit: {len(audits)} sampled signal bars, truncated-frame recompute "
        f"matched exactly (asserted)")

    # metrics
    cells_out = [cell_metrics(cell, episodes[cell.cell_id()], tuning_set, heldout_set)
                 for cell in grid]

    results = {
        "family": prereg["family"],
        "generated_at": datetime.now().isoformat(),
        "prereg_path": str(PREREG_PATH.relative_to(_ROOT)).replace("\\", "/"),
        "prereg_frozen_at": prereg["frozen_at"],
        "day_inventory": str(INVENTORY_PATH.relative_to(_ROOT)).replace("\\", "/"),
        "n_tuning_days": len(tuning),
        "n_heldout_days": len(heldout),
        "n_candidate_bars": n_cand,
        "exit_shape": exit_shape,
        "structure_stop_enabled": structure_stop_enabled,
        "time_stop_et": str(time_stop),
        "causality_audit": audits,
        "cells": cells_out,
    }
    results_path.write_text(json.dumps(results, indent=1, default=str), encoding="utf-8")
    log(f"wrote {results_path}")

    episodes_path.write_text(json.dumps({
        "family": prereg["family"],
        "generated_at": results["generated_at"],
        "prereg_path": results["prereg_path"],
        "note": ("per-cell episode detail so verifiers can recompute every cell metric. "
                 "status=FILLED rows carry real-OPRA pnl; all other statuses are disclosed "
                 "skips (NEVER BS-synthetic-priced). heldout membership derivable from "
                 "day-inventory heldout_days."),
        "cells": episodes,
    }, indent=1, default=str), encoding="utf-8")
    log(f"wrote {episodes_path}")

    log("==== CELL TABLE (tuning population; held_out separate) ====")
    for c in sorted(cells_out, key=lambda r: (-r["gates_passed"], -r["expectancy"])):
        log(f"  {c['cell_id']:32s} n={c['n_real_fills']:4d} exp=${c['expectancy']:+8.2f} "
            f"total=${c['total_pnl']:+10.2f} dayWR={c['day_wr']:.3f} "
            f"exTop3=${c['ex_top3_total']:+10.2f} held=${c['held_out_total']:+9.2f} "
            f"p={c['p_raw']:.4f} gates={c['gates_passed']}/4")
    return results


if __name__ == "__main__":
    _smoke = 0
    if len(sys.argv) > 2 and sys.argv[1] == "--smoke":
        _smoke = int(sys.argv[2])
    main(smoke_days=_smoke)

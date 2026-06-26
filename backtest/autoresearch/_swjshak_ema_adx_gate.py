"""SwjshAK strategy 'ema_adx_gate' (class: continuation / survivor) — REAL-FILLS test.

HYPOTHESIS (source: SwjshAK data/brain/ema-crossover-adx.md):
  EMA(9) cross EMA(21) on SPY 5m, taken ONLY when ADX(14) > 25 (trend, not chop).
  Continuation idea (survivor class). cross-up -> CALL, cross-down -> PUT.
  The ADX regime gate is the KEY idea — the cross alone is noise; the gate is
  meant to filter chop out so only trending crosses fire.

WHY THIS IS A "SURVIVOR" CANDIDATE (CLAUDE.md THE 0DTE WALL, C3/L58/L74):
  Nearly every directional SPY-PRICE signal has an edge that DIES on 0DTE options
  (theta + delta + stop-misfire). The only structure that has SURVIVED in our rig
  (live vwap_continuation) is: ITM-2 strike (high delta / low theta) + tight -8%
  premium stop + sustained-directional (trend-continuation) signal + morning.
  So the PRIMARY config here mirrors that survivor structure exactly:
    strike_offset = -2 (ITM-2), premium_stop_pct = -0.08, v15 default exits.

REAL-FILLS, not BS (C1): every premium comes from cached OPRA bars via
  lib.simulator_real.simulate_trade_real. SPY-direction WR != option edge (C3).

HARD SELF-VERIFY (deterministic, in-script — these caught 2 fakes last run):
  (a) OP-11: OOS(2026) per-trade > 0 AND positive_quarters >= 4/6 AND
      top5-day < 200% of total AND n >= 20 AND drop-top-5-days still > 0.
  (b) RANDOM-NULL: re-run with RANDOM entry bars (same count, same exit/stop, ~20
      seeds); the strategy per-trade MUST beat the null mean. If random ties it,
      the edge is the exit bracket not the signal -> FAIL.
  (c) NO-TRUNCATION: the SIGN of per-trade must NOT invert between the -8% stop and
      chart-stop-only (-0.99). If it's only positive because -8% truncates losers
      -> stop artifact -> FAIL.
  A real edge passes ALL of (a)+(b)+(c).

OP-20 honesty: per-trade expectancy (not WR alone); IS/OOS; concentration
  (top5-day %); random-null delta; truncation check; no parameter cherry-picking.

Pure Python, $0 in the sim loop. No live orders. Markets CLOSED.
Writes analysis/recommendations/swjshak-ema-adx-gate.json.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import logging
import random
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

# ── Strategy params (from the hypothesis) ───────────────────────────────────────
EMA_FAST = 9
EMA_SLOW = 21
ADX_LEN = 14
ADX_MIN = 25.0           # the KEY regime gate: trend, not chop
COOLDOWN_MIN = 30        # 30-45m anti-churn; use 30 (more signals, conservative on n)
WARMUP_BARS = 12         # bars into the session before evaluating (let opening settle)

# ── Real-fills sim params ───────────────────────────────────────────────────────
QTY = 3
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# PRIMARY config = survivor structure (vwap_continuation shape)
PRIMARY_STRIKE_OFFSET = -2     # ITM-2 (call: strike $2 below spot)
PRIMARY_PREMIUM_STOP = -0.08   # tight -8% premium stop

# Secondary sweep grid
SWEEP_OFFSETS = [-2, -1, 0]
SWEEP_STOPS = [-0.08, -0.20, -0.50, -0.99]

RANDOM_SEEDS = 20


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


# ── Indicator math (Wilder ADX + Pine-EMA, vectorized) ──────────────────────────

def _ema(series: pd.Series, length: int) -> pd.Series:
    """Pine ta.ema convention: alpha = 2/(length+1), SMA seed at index length-1."""
    arr = series.to_numpy(dtype=float)
    n = len(arr)
    out = np.full(n, np.nan)
    if n < length:
        return pd.Series(out, index=series.index)
    seed = arr[:length].mean()
    out[length - 1] = seed
    alpha = 2.0 / (length + 1)
    for i in range(length, n):
        out[i] = arr[i] * alpha + out[i - 1] * (1 - alpha)
    return pd.Series(out, index=series.index)


def _adx(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    """Wilder ADX(length). Matches TradingView's ta.adx / DMI default.

    +DM = up_move if up_move > down_move and up_move > 0 else 0
    -DM = down_move if down_move > up_move and down_move > 0 else 0
    TR  = max(h-l, |h-pc|, |l-pc|)
    Wilder-smooth TR, +DM, -DM over `length`; +DI=100*smDM+/smTR; -DI similarly.
    DX = 100*|+DI - -DI|/(+DI + -DI); ADX = Wilder-smoothed DX over `length`.
    """
    h = high.to_numpy(dtype=float)
    l = low.to_numpy(dtype=float)
    c = close.to_numpy(dtype=float)
    n = len(h)
    out = np.full(n, np.nan)
    if n < 2 * length + 1:
        return pd.Series(out, index=high.index)

    tr = np.zeros(n)
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        up = h[i] - h[i - 1]
        down = l[i - 1] - l[i]
        plus_dm[i] = up if (up > down and up > 0) else 0.0
        minus_dm[i] = down if (down > up and down > 0) else 0.0
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))

    # Wilder smoothing (RMA): seed with simple sum over first `length` (idx 1..length)
    atr = np.full(n, np.nan)
    sm_plus = np.full(n, np.nan)
    sm_minus = np.full(n, np.nan)
    atr[length] = tr[1:length + 1].sum()
    sm_plus[length] = plus_dm[1:length + 1].sum()
    sm_minus[length] = minus_dm[1:length + 1].sum()
    for i in range(length + 1, n):
        atr[i] = atr[i - 1] - (atr[i - 1] / length) + tr[i]
        sm_plus[i] = sm_plus[i - 1] - (sm_plus[i - 1] / length) + plus_dm[i]
        sm_minus[i] = sm_minus[i - 1] - (sm_minus[i - 1] / length) + minus_dm[i]

    dx = np.full(n, np.nan)
    for i in range(length, n):
        if atr[i] and atr[i] > 0:
            pdi = 100.0 * sm_plus[i] / atr[i]
            mdi = 100.0 * sm_minus[i] / atr[i]
            denom = pdi + mdi
            dx[i] = 100.0 * abs(pdi - mdi) / denom if denom > 0 else 0.0

    # ADX = Wilder-smoothed DX; seed = mean of first `length` valid DX values
    first = length  # first index with a DX value
    seed_end = first + length  # need `length` DX values: indices first..first+length-1
    if seed_end > n:
        return pd.Series(out, index=high.index)
    out[seed_end - 1] = np.nanmean(dx[first:seed_end])
    for i in range(seed_end, n):
        out[i] = (out[i - 1] * (length - 1) + dx[i]) / length
    return pd.Series(out, index=high.index)


# ── Accumulator ─────────────────────────────────────────────────────────────────

class _Acc:
    __slots__ = ("n", "wins", "pnl", "by_day", "pnls")

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.pnl = 0.0
        self.by_day: dict[str, float] = defaultdict(float)
        self.pnls: list[float] = []

    def add(self, pnl: float, day: str):
        self.n += 1
        self.wins += 1 if pnl > 0 else 0
        self.pnl += pnl
        self.by_day[day] += pnl
        self.pnls.append(pnl)

    def report(self) -> dict:
        if not self.n:
            return {"n": 0}
        days_sorted = sorted(self.by_day.values(), reverse=True)
        top5 = sum(days_sorted[:5])
        return {
            "n": self.n,
            "wr": round(100 * self.wins / self.n, 1),
            "total_pnl": round(self.pnl, 0),
            "avg_pnl": round(self.pnl / self.n, 1),
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


# ── Data load + signal scan ─────────────────────────────────────────────────────

def _load_rth():
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
                   & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    rth["date"] = rth["timestamp_et"].dt.date
    log.info("RTH bars: %d (%d days)", len(rth), rth["date"].nunique())
    return rth


def scan_signals(rth: pd.DataFrame) -> list[dict]:
    """Causal EMA(9/21) cross gated by ADX(14) > 25, per-day indicators (no look-ahead).

    Indicators are computed PER SESSION (reset each day) so a fresh ADX/EMA warms up
    intraday — matches a live 5m-RTH read and avoids leaking prior-day structure.
    The cross is detected on bar i using bars <= i only; entry fills on the NEXT bar
    via the simulator (so even bar i's close is causal).
    """
    signals: list[dict] = []
    day_start: dict[dt.date, int] = {}
    for i, d in enumerate(rth["date"]):
        if d not in day_start:
            day_start[d] = i

    for d, i0 in day_start.items():
        day_df = rth[rth["date"] == d]
        if len(day_df) < (2 * ADX_LEN + 2 + WARMUP_BARS):
            continue
        ef = _ema(day_df["close"], EMA_FAST).to_numpy()
        es = _ema(day_df["close"], EMA_SLOW).to_numpy()
        adx = _adx(day_df["high"], day_df["low"], day_df["close"], ADX_LEN).to_numpy()
        diff = ef - es  # >0 fast above slow (bullish), <0 bearish

        last_sig_local = None
        for k in range(1, len(day_df)):
            if k < WARMUP_BARS:
                continue
            if np.isnan(diff[k]) or np.isnan(diff[k - 1]) or np.isnan(adx[k]):
                continue
            cross_up = diff[k - 1] <= 0 < diff[k]
            cross_dn = diff[k - 1] >= 0 > diff[k]
            if not (cross_up or cross_dn):
                continue
            # KEY GATE: only take the cross in a trending regime
            if adx[k] < ADX_MIN:
                continue
            row = day_df.iloc[k]
            bar_time = pd.Timestamp(row["timestamp_et"])
            if bar_time.tzinfo is not None:
                bar_time = bar_time.tz_localize(None)
            tmin = bar_time.hour * 60 + bar_time.minute
            if last_sig_local is not None and (tmin - last_sig_local) < COOLDOWN_MIN:
                continue
            last_sig_local = tmin
            side = "C" if cross_up else "P"
            global_idx = i0 + k

            # rejection_level = strategy invalidation:
            #   for a CALL (cross-up), support is the recent swing LOW below entry —
            #     if price loses it, the bullish cross failed.
            #   for a PUT (cross-down), resistance is the recent swing HIGH above entry.
            look = day_df.iloc[max(0, k - 6):k + 1]
            if side == "C":
                rej = float(look["low"].min())
            else:
                rej = float(look["high"].max())

            signals.append({
                "idx": int(global_idx),
                "date": d,
                "side": side,
                "adx": round(float(adx[k]), 1),
                "rejection_level": rej,
                "time": bar_time.strftime("%H:%M"),
            })
    log.info("Signals (EMA%d/%d cross, ADX>%.0f): %d", EMA_FAST, EMA_SLOW, ADX_MIN, len(signals))
    return signals


# ── Real-fills runner over a fixed signal list ──────────────────────────────────

def run_fills(rth: pd.DataFrame, signals: list[dict], strike_offset: int,
              premium_stop_pct: float) -> tuple[_Acc, dict, int, list[dict]]:
    overall = _Acc()
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    by_side = {"C": _Acc(), "P": _Acc()}
    no_data = 0
    rows: list[dict] = []

    for s in signals:
        fill = simulate_trade_real(
            entry_bar_idx=s["idx"], entry_bar=rth.iloc[s["idx"]], spy_df=rth, ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["ema_cross", "adx_gate", "bullish" if s["side"] == "C" else "bearish"],
            side=s["side"], qty=QTY, setup="EMA_ADX_GATE",
            premium_stop_pct=premium_stop_pct, strike_offset=strike_offset)
        if fill is None:
            no_data += 1
            continue
        pnl = fill.dollar_pnl
        day = s["date"].isoformat()
        overall.add(pnl, day)
        by_sample["IS_2025" if s["date"].year == 2025 else "OOS_2026"].add(pnl, day)
        by_q[_quarter(s["date"])].add(pnl, day)
        by_side[s["side"]].add(pnl, day)
        rows.append({
            "date": day, "time": s["time"], "side": s["side"], "adx": s["adx"],
            "strike": fill.strike, "entry_premium": round(fill.entry_premium, 3),
            "pnl": round(pnl, 2),
            "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason),
        })

    extra = {
        "by_sample": {k: v.report() for k, v in by_sample.items()},
        "by_side": {k: v.report() for k, v in by_side.items()},
        "by_quarter": {k: by_q[k].report() for k in sorted(by_q)},
        "_acc_by_sample": by_sample,
        "_acc_by_q": by_q,
    }
    return overall, extra, no_data, rows


# ── Random-null entry control (verify (b)) ──────────────────────────────────────

def run_random_null(rth: pd.DataFrame, n_target: int, sides: list[str],
                    strike_offset: int, premium_stop_pct: float,
                    seeds: int) -> dict:
    """Re-run with RANDOM entry bars: same count, same side mix, same exit/stop.

    Eligible entry bars = RTH bars in [WARMUP_BARS, last-tradeable] each day. Each
    seed draws n_target random (idx, side) pairs (side sampled from the real mix),
    runs real-fills, records per-trade. The signal must beat the mean of the null.
    """
    day_start: dict[dt.date, int] = {}
    for i, d in enumerate(rth["date"]):
        if d not in day_start:
            day_start[d] = i
    # eligible global indices: at least WARMUP_BARS into the day, and leave room for a fill
    eligible: list[int] = []
    for d, i0 in day_start.items():
        day_len = int((rth["date"] == d).sum())
        if day_len < WARMUP_BARS + 4:
            continue
        for k in range(WARMUP_BARS, day_len - 2):
            eligible.append(i0 + k)
    if not eligible:
        return {"per_trade_mean": None, "per_trade_seeds": [], "n_eligible": 0}

    n_call = sides.count("C")
    n_put = sides.count("P")
    per_trade_means: list[float] = []
    for seed in range(seeds):
        rng = random.Random(1000 + seed)
        picks = rng.sample(eligible, min(n_target, len(eligible)))
        # assign sides proportional to real mix
        side_pool = (["C"] * n_call + ["P"] * n_put)
        rng.shuffle(side_pool)
        acc = _Acc()
        for j, idx in enumerate(picks):
            side = side_pool[j % len(side_pool)] if side_pool else "C"
            row = rth.iloc[idx]
            look = rth.iloc[max(0, idx - 6):idx + 1]
            rej = float(look["low"].min()) if side == "C" else float(look["high"].max())
            fill = simulate_trade_real(
                entry_bar_idx=int(idx), entry_bar=row, spy_df=rth, ribbon_df=None,
                rejection_level=rej, triggers_fired=["random_null"], side=side, qty=QTY,
                setup="EMA_ADX_GATE_RANDOM", premium_stop_pct=premium_stop_pct,
                strike_offset=strike_offset)
            if fill is None:
                continue
            acc.add(fill.dollar_pnl, row["date"].isoformat() if hasattr(row["date"], "isoformat") else str(row["date"]))
        if acc.n > 0:
            per_trade_means.append(acc.pnl / acc.n)

    mean = round(sum(per_trade_means) / len(per_trade_means), 1) if per_trade_means else None
    return {
        "per_trade_mean": mean,
        "per_trade_seeds": [round(x, 1) for x in per_trade_means],
        "n_eligible": len(eligible),
        "seeds_completed": len(per_trade_means),
    }


# ── Drop-top-5-days robustness (part of verify (a)) ─────────────────────────────

def _drop_top5_per_trade(acc: _Acc) -> float | None:
    """Per-trade expectancy after removing the 5 best P&L DAYS entirely."""
    if acc.n == 0:
        return None
    top5_days = set(sorted(acc.by_day, key=lambda d: acc.by_day[d], reverse=True)[:5])
    # Need per-trade granularity by day; we only kept pnls + by_day. Recompute via rows
    # is cleaner — but here approximate using day totals removed from the pool.
    remaining_pnl = sum(v for d, v in acc.by_day.items() if d not in top5_days)
    # count trades on remaining days: we didn't store trade->day, so reconstruct from pnls
    # is impossible w/o mapping. Instead store mapping in caller. (see _drop_top5_exact)
    return None


def _drop_top5_exact(rows: list[dict]) -> tuple[float | None, int]:
    """Exact per-trade expectancy after dropping the 5 best P&L days, using row-level data."""
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r["date"]] += r["pnl"]
    top5_days = set(sorted(by_day, key=lambda d: by_day[d], reverse=True)[:5])
    kept = [r["pnl"] for r in rows if r["date"] not in top5_days]
    if not kept:
        return None, 0
    return round(sum(kept) / len(kept), 1), len(kept)


# ── Orchestration ───────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tag", default="ema-adx-gate")
    args = p.parse_args(argv)

    rth = _load_rth()
    signals = scan_signals(rth)
    sides = [s["side"] for s in signals]

    # ── PRIMARY: survivor structure (ITM-2, -8% stop) ──
    log.info("PRIMARY real-fills: strike_offset=%d stop=%.2f", PRIMARY_STRIKE_OFFSET, PRIMARY_PREMIUM_STOP)
    prim, prim_extra, prim_nodata, prim_rows = run_fills(
        rth, signals, PRIMARY_STRIKE_OFFSET, PRIMARY_PREMIUM_STOP)
    prim_report = prim.report()

    by_sample = prim_extra["by_sample"]
    by_q = prim_extra["by_quarter"]
    oos = by_sample.get("OOS_2026", {"n": 0})
    oos_pt = oos.get("avg_pnl") if oos.get("n") else None
    pos_q = sum(1 for r in by_q.values() if r.get("total_pnl", 0) and r["total_pnl"] > 0)
    n_q = len(by_q)
    top5_pct = prim_report.get("top5_day_pct")
    drop5_pt, drop5_n = _drop_top5_exact(prim_rows)

    # ── SECONDARY SWEEP: offset x stop ──
    log.info("Secondary sweep %dx%d ...", len(SWEEP_OFFSETS), len(SWEEP_STOPS))
    sweep: list[dict] = []
    truncation_pairs: dict[int, dict[float, float | None]] = defaultdict(dict)
    for off in SWEEP_OFFSETS:
        for stop in SWEEP_STOPS:
            acc, _ex, nodata, _rows = run_fills(rth, signals, off, stop)
            rep = acc.report()
            sweep.append({"strike_offset": off, "premium_stop_pct": stop,
                          "n": rep.get("n", 0), "no_opra": nodata,
                          "total_pnl": rep.get("total_pnl"), "avg_pnl": rep.get("avg_pnl"),
                          "wr": rep.get("wr")})
            truncation_pairs[off][stop] = rep.get("avg_pnl") if rep.get("n") else None

    # ── VERIFY (b): RANDOM-NULL at the PRIMARY config ──
    log.info("Random-null control (%d seeds) at primary config ...", RANDOM_SEEDS)
    null = run_random_null(rth, prim.n if prim.n else len(signals), sides,
                           PRIMARY_STRIKE_OFFSET, PRIMARY_PREMIUM_STOP, RANDOM_SEEDS)
    strat_pt = prim_report.get("avg_pnl")
    null_pt = null.get("per_trade_mean")
    beats_null = (strat_pt is not None and null_pt is not None and strat_pt > null_pt)

    # ── VERIFY (c): NO-TRUNCATION — sign at -8% vs -0.99 at PRIMARY offset ──
    pt_8 = truncation_pairs[PRIMARY_STRIKE_OFFSET].get(-0.08)
    pt_99 = truncation_pairs[PRIMARY_STRIKE_OFFSET].get(-0.99)
    def _sign(x): return 0 if x is None else (1 if x > 0 else (-1 if x < 0 else 0))
    truncation_safe = (pt_8 is not None and pt_99 is not None
                       and _sign(pt_8) == _sign(pt_99) and _sign(pt_8) >= 0)
    # If primary itself is non-positive, the sign-invert test is moot but we still
    # report it; truncation_safe also requires the positive branch to hold.

    # ── VERIFY (a): OP-11 composite ──
    op11 = {
        "oos_per_trade_gt0": bool(oos_pt is not None and oos_pt > 0),
        "positive_quarters_ok": bool(pos_q >= 4 and n_q >= 6) or (pos_q >= 4),
        "top5_day_lt200": bool(top5_pct is not None and top5_pct < 200),
        "n_ge_20": bool(prim.n >= 20),
        "drop_top5_gt0": bool(drop5_pt is not None and drop5_pt > 0),
    }
    op11_pass = all(op11.values())

    clears_bar = bool(op11_pass and beats_null and truncation_safe)

    # ── Best sweep config by total_pnl among n>=20 ──
    elig = [c for c in sweep if (c.get("n") or 0) >= 20 and c.get("total_pnl") is not None]
    best = max(elig, key=lambda c: c["total_pnl"]) if elig else None
    best_cfg = (f"offset={best['strike_offset']} stop={best['premium_stop_pct']} "
                f"(n={best['n']}, total=${best['total_pnl']:.0f}, pt=${best['avg_pnl']:.0f})") if best else "none (no config reached n>=20)"

    # ── Verdict prose ──
    if prim.n < 20:
        verdict = (f"INSUFFICIENT N — primary survivor-structure config produced only "
                   f"{prim.n} real fills (no_opra={prim_nodata}); cannot validate. The "
                   f"ITM-2 ({PRIMARY_STRIKE_OFFSET}) contracts are thinly cached in the OPRA set.")
    elif clears_bar:
        verdict = (f"SURVIVES — EMA{EMA_FAST}/{EMA_SLOW} cross + ADX>{ADX_MIN:.0f} gate clears ALL "
                   f"three gates (OP-11 OOS+quarters+concentration, beats random-null by "
                   f"${(strat_pt - null_pt):.0f}/trade, sign stable across stops). Survivor "
                   f"structure ITM-2/-8% per-trade=${strat_pt:.0f}.")
    else:
        fails = []
        if not op11_pass:
            sub = [k for k, v in op11.items() if not v]
            fails.append("OP-11(" + ",".join(sub) + ")")
        if not beats_null:
            fails.append(f"random-null(strat={strat_pt} vs null={null_pt})")
        if not truncation_safe:
            fails.append(f"truncation(pt@-8%={pt_8} vs pt@-99%={pt_99})")
        verdict = (f"FAILS — EMA{EMA_FAST}/{EMA_SLOW}+ADX>{ADX_MIN:.0f} does NOT clear: "
                   + "; ".join(fails) + ". This is another 0DTE-wall casualty (C3/L58): a "
                   "SPY-price regime gate that does not convert to a per-trade option edge.")

    summary = {
        "run_date": dt.date.today().isoformat(),
        "strategy": "ema_adx_gate",
        "cls": "continuation",
        "source": "SwjshAK data/brain/ema-crossover-adx.md",
        "hypothesis": f"EMA({EMA_FAST}) cross EMA({EMA_SLOW}) on SPY 5m, taken ONLY when "
                      f"ADX({ADX_LEN})>{ADX_MIN:.0f}; cross-up->CALL, cross-down->PUT; ADX gate is the key idea.",
        "window": f"{START}..{END}",
        "strategy_params": {"ema_fast": EMA_FAST, "ema_slow": EMA_SLOW, "adx_len": ADX_LEN,
                            "adx_min": ADX_MIN, "cooldown_min": COOLDOWN_MIN,
                            "warmup_bars": WARMUP_BARS, "indicators": "per-session reset, causal"},
        "n_signals": len(signals),
        "primary_config": {
            "desc": "SURVIVOR STRUCTURE (vwap_continuation shape): ITM-2 + -8% premium stop + v15 exits",
            "strike_offset": PRIMARY_STRIKE_OFFSET, "premium_stop_pct": PRIMARY_PREMIUM_STOP, "qty": QTY,
            "n_completed": prim.n, "n_no_opra_data": prim_nodata,
            "overall": prim_report,
            "by_sample": by_sample,
            "by_side": prim_extra["by_side"],
            "by_quarter": by_q,
            "positive_quarters": f"{pos_q}/{n_q}",
            "drop_top5_days_per_trade": drop5_pt,
            "drop_top5_n": drop5_n,
        },
        "secondary_sweep": sweep,
        "best_sweep_config": best_cfg,
        "self_verify": {
            "a_op11": {**op11, "_pass": op11_pass,
                       "oos_per_trade": oos_pt, "positive_quarters": f"{pos_q}/{n_q}",
                       "top5_day_pct": top5_pct, "n": prim.n, "drop_top5_per_trade": drop5_pt},
            "b_random_null": {**null, "strategy_per_trade": strat_pt,
                              "delta_vs_null": (round(strat_pt - null_pt, 1)
                                                if (strat_pt is not None and null_pt is not None) else None),
                              "_pass": beats_null},
            "c_no_truncation": {"per_trade_stop_8pct": pt_8, "per_trade_stop_99pct": pt_99,
                                "sign_8pct": _sign(pt_8), "sign_99pct": _sign(pt_99),
                                "_pass": truncation_safe},
            "ALL_PASS": clears_bar,
        },
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) — the only WR/edge authority; no BS-sim here",
            "spy_vs_option": "EMA/ADX is a SPY-PRICE signal; this is the option-edge test (C3/L58/L74)",
            "per_trade": "expectancy (avg_pnl) is primary, NOT WR (OP-14/C4)",
            "concentration": "top5_day_pct + drop-top-5-days per-trade both reported (OP-20 #5)",
            "random_null": "per-trade vs random-entry null (same count/side-mix/exit) — isolates signal from bracket",
            "truncation": "sign stability of per-trade across -8% .. -99% stop — isolates signal from stop truncation",
            "no_cherry_pick": "PRIMARY is the pre-registered survivor structure; sweep reported in full, not mined (anti-2.10)",
            "account_scaling": "qty=3 ITM-2 ~ several hundred $/trade; fits $2K Safe per-trade cap",
        },
        "verdict": verdict,
        "results": prim_rows,
    }

    out = ROOT / "analysis" / "recommendations" / f"swjshak-{args.tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", out)

    print("\n=== SwjshAK ema_adx_gate REAL-FILLS VERDICT ===")
    print(f"signals={len(signals)} primary_completed={prim.n} no_opra={prim_nodata}")
    print(f"PRIMARY (ITM-2/-8%): {prim_report}")
    print(f"  IS 2025 : {by_sample.get('IS_2025')}")
    print(f"  OOS 2026: {oos}")
    print(f"  by_side : {prim_extra['by_side']}")
    print(f"  pos_quarters={pos_q}/{n_q}  by_quarter={by_q}")
    print(f"  drop-top5-days per-trade={drop5_pt} (n={drop5_n})")
    print(f"VERIFY (a) OP-11      : {op11} -> {op11_pass}")
    print(f"VERIFY (b) random-null: strat_pt={strat_pt} null_pt={null_pt} -> beats={beats_null}")
    print(f"VERIFY (c) truncation : pt@-8%={pt_8} pt@-99%={pt_99} -> safe={truncation_safe}")
    print(f"ALL THREE PASS        : {clears_bar}")
    print(f"best sweep cfg        : {best_cfg}")
    print(f"VERDICT: {verdict}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

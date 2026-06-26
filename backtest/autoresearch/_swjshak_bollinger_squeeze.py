"""SwjshAK strategy #8 — BOLLINGER SQUEEZE breakout (class: continuation-breakout).

REAL-FILLS validation on 0DTE SPY options (OPRA sim, the C1 WR authority).

HYPOTHESIS (source: SwjshAK data/brain/bollinger-breakout.md, ported here):
  Bollinger(20,2) bandwidth SQUEEZE (width < ~50% of recent avg) then EXPANSION +
  VOLUME -> breakout entry in the expansion direction (close breaks above upper band
  -> CALL ; below lower band -> PUT). Vol-expansion CONTINUATION.

This is a SPY-PRICE signal. The 0DTE WALL doctrine (C3/L58, proven across 23 strategies):
nearly every directional SPY signal has a price edge that DIES on 0DTE options
(theta + delta + stop-misfire). The ONLY structure that has survived is the
vwap_continuation shape: ITM-2 strike + tight -8% premium stop + sustained-directional
signal + morning. So the PRIMARY config tested here is exactly that SURVIVOR STRUCTURE:
strike_offset=-2 (ITM-2), premium_stop_pct=-0.08, default v15 exits.

HARD SELF-VERIFY (deterministic, all MANDATORY — these caught 2 fakes last run):
  (a) OP-11   : OOS(2026) per-trade>0 AND positive_quarters>=4/6 AND top5-day<200%
                AND n>=20 AND drop-top-5-days still>0.
  (b) RANDOM-NULL: re-run with RANDOM entry bars (same count, same exits/stop, ~20
                seeds); the strategy per-trade MUST beat the null mean. If random ties
                it, the edge is the exit bracket, not the signal -> FAIL.
  (c) NO-TRUNCATION: the SIGN of per-trade must NOT invert between the -8% stop and
                chart-stop-only (-0.99). Positive ONLY because -8% truncates losers
                -> stop artifact -> FAIL.
A real edge passes ALL of (a)+(b)+(c).

OP-20 honesty: per-trade expectancy (not WR), IS/OOS, concentration (top5),
random-null delta + truncation check disclosed. No cherry-picking (anti-2.10): the
PRIMARY survivor-structure verdict is reported FIRST; the small secondary sweep is
disclosed in full but does NOT override the primary verdict.

Pure Python, $0. No live orders. Writes analysis/recommendations/swjshak-bollinger-squeeze.json.
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

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

# ── Strategy / sim parameters ────────────────────────────────────────────────
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)
QTY = 3
COOLDOWN_MIN = 35                 # anti-pattern 2.7 (no back-to-back same-setup churn); spec says 30-45m

# Bollinger / squeeze parameters
BB_LEN = 20
BB_K = 2.0
BW_AVG_LOOKBACK = 50              # window (prior bars) for "recent avg" bandwidth
SQUEEZE_RATIO = 0.50             # squeeze = bandwidth < 50% of recent-avg bandwidth
VOL_AVG_LOOKBACK = 20            # window (prior bars) for "recent avg" volume
VOL_MULT = 1.0                   # expansion requires volume > recent-avg volume
WARMUP_BARS = BB_LEN + BW_AVG_LOOKBACK  # need full BB + bandwidth-avg history before evaluating

# PRIMARY config = the proven SURVIVOR STRUCTURE
PRIMARY_STRIKE_OFFSET = -2        # ITM-2 (calls: strike $2 below spot; puts: $2 above)
PRIMARY_PREMIUM_STOP = -0.08      # tight premium stop
# Default v15 exits used implicitly via simulate_trade_real defaults.

# Secondary sweep grid
SWEEP_OFFSETS = [-2, -1, 0]
SWEEP_STOPS = [-0.08, -0.20, -0.50, -0.99]

# Random-null
N_NULL_SEEDS = 20

# Chart-stop level (rejection_level) = strategy invalidation: for a CALL, the support
# the squeeze broke UP from (lower band on the trigger bar); for a PUT, the resistance
# it broke DOWN from (upper band). simulator_real fires the level-stop at
# rejection_level -/+ level_stop_buffer_dollars ($0.50). We pass the band itself.


def _quarter(d: dt.date) -> str:
    return f"{d.year}Q{(d.month - 1) // 3 + 1}"


class _Acc:
    __slots__ = ("n", "wins", "pnl", "by_day")

    def __init__(self):
        self.n = 0
        self.wins = 0
        self.pnl = 0.0
        self.by_day: dict[str, float] = defaultdict(float)

    def add(self, pnl: float, day: str):
        self.n += 1
        self.wins += 1 if pnl > 0 else 0
        self.pnl += pnl
        self.by_day[day] += pnl

    def report(self) -> dict:
        if not self.n:
            return {"n": 0}
        days_sorted = sorted(self.by_day.values(), reverse=True)
        top5 = sum(days_sorted[:5])
        pnl_ex_top5 = self.pnl - top5
        return {
            "n": self.n,
            "wr": round(100 * self.wins / self.n, 1),
            "total_pnl": round(self.pnl, 0),
            "avg_pnl": round(self.pnl / self.n, 2),
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
            "pnl_ex_top5_days": round(pnl_ex_top5, 0),
        }


# ── Data load (mirrors confluence_real_fills_validate.py) ────────────────────

def _load_rth_and_vix():
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
                   & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    rth["date"] = rth["timestamp_et"].dt.date
    log.info("RTH bars: %d", len(rth))

    vix_full["timestamp_et"] = pd.to_datetime(
        vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index)
    vix_ser = vix_full.set_index("timestamp_et")["close"] if "close" in vix_full.columns else vix_full.iloc[:, 0]
    rth_naive = rth["timestamp_et"].dt.tz_localize(None) if rth["timestamp_et"].dt.tz is not None else rth["timestamp_et"]
    vix_arr: list[float] = []
    for ts in rth_naive:
        try:
            j = vix_ser.index.get_indexer([ts], method="ffill")[0]
            vix_arr.append(float(vix_ser.iloc[j]) if j >= 0 else 17.0)
        except Exception:
            vix_arr.append(17.0)
    return rth, vix_arr


# ── Signal detection: causal Bollinger squeeze -> expansion+volume breakout ──

def _detect_signals(rth: pd.DataFrame, vix_arr: list[float]) -> list[dict]:
    """Scan RTH bars per-day for the squeeze->expansion breakout.

    CAUSAL: every quantity at bar i uses ONLY bars <= i.
      - BB(20,2): middle=SMA20(close), sd=std20(close), upper/lower=middle +/- 2*sd.
      - bandwidth bw[i] = (upper-lower)/middle = 2*K*sd/middle.
      - recent-avg bandwidth = mean(bw over the prior BW_AVG_LOOKBACK bars, EXCLUDING i).
      - squeeze[i]   = bw[i] < SQUEEZE_RATIO * recent_avg_bw   (volatility was compressed)
      - expansion[i] = bw[i] > bw[i-1]                          (bands now widening)
      - volume[i]    = vol[i] > VOL_MULT * mean(vol prior VOL_AVG_LOOKBACK bars excl i)
      - breakout up  = close[i] > upper[i]  -> CALL ; rej = lower[i] (support broken up from)
      - breakout dn  = close[i] < lower[i]  -> PUT  ; rej = upper[i] (resistance broken dn from)
    Entry then fills on the NEXT bar inside simulate_trade_real (no look-ahead).
    """
    # day boundaries
    day_start: dict[dt.date, int] = {}
    for i, d in enumerate(rth["date"]):
        if d not in day_start:
            day_start[d] = i

    close = rth["close"].astype(float).values
    high = rth["high"].astype(float).values
    low = rth["low"].astype(float).values
    vol = rth.get("volume")
    if vol is None:
        vol = pd.Series([50000.0] * len(rth))
    vol = vol.fillna(50000.0).astype(float).values

    signals: list[dict] = []
    last_sig_time: dt.datetime | None = None

    # Precompute rolling BB per DAY (reset each session — no cross-day leakage)
    for d, i0 in day_start.items():
        # end index of this day
        i_end = len(rth)
        # find next day's start
        nxt = [s for s in day_start.values() if s > i0]
        if nxt:
            i_end = min(nxt)
        idxs = list(range(i0, i_end))
        if len(idxs) < WARMUP_BARS + 2:
            continue
        c = pd.Series(close[i0:i_end])
        v = pd.Series(vol[i0:i_end])
        mid = c.rolling(BB_LEN).mean()
        sd = c.rolling(BB_LEN).std(ddof=0)
        upper = mid + BB_K * sd
        lower = mid - BB_K * sd
        bw = (upper - lower) / mid  # = 2*K*sd/mid
        # recent-avg bandwidth EXCLUDING current bar: shift(1) then rolling-mean
        bw_avg = bw.shift(1).rolling(BW_AVG_LOOKBACK).mean()
        # recent-avg volume EXCLUDING current bar
        vol_avg = v.shift(1).rolling(VOL_AVG_LOOKBACK).mean()

        for local in range(WARMUP_BARS, len(idxs)):
            gi = i0 + local  # global index
            if pd.isna(bw.iloc[local]) or pd.isna(bw_avg.iloc[local]) or pd.isna(vol_avg.iloc[local]):
                continue
            if pd.isna(bw.iloc[local - 1]):
                continue
            cur_bw = float(bw.iloc[local])
            prev_bw = float(bw.iloc[local - 1])
            avg_bw = float(bw_avg.iloc[local])
            if avg_bw <= 0:
                continue
            squeeze = cur_bw < SQUEEZE_RATIO * avg_bw
            expansion = cur_bw > prev_bw
            volume_ok = float(v.iloc[local]) > VOL_MULT * float(vol_avg.iloc[local])
            if not (squeeze and expansion and volume_ok):
                continue
            cl = float(c.iloc[local])
            up_brk = cl > float(upper.iloc[local])
            dn_brk = cl < float(lower.iloc[local])
            if not (up_brk or dn_brk):
                continue
            side = "C" if up_brk else "P"
            rej = float(lower.iloc[local]) if up_brk else float(upper.iloc[local])
            bar_time = pd.Timestamp(rth["timestamp_et"].iloc[gi])
            if bar_time.tzinfo is not None:
                bar_time = bar_time.tz_localize(None)
            bar_time = bar_time.to_pydatetime()
            if last_sig_time is not None and (bar_time - last_sig_time).total_seconds() / 60.0 < COOLDOWN_MIN:
                # cooldown is global (mirrors reference scripts); skip churn
                # but note: last_sig_time tracked across days too -> first signal each day
                # is rarely within 35m of prior day's last (>17h gap), so this is fine.
                continue
            last_sig_time = bar_time
            signals.append({
                "idx": gi,
                "date": rth["date"].iloc[gi],
                "side": side,
                "rejection_level": round(rej, 2),
                "vix": round(vix_arr[gi], 1),
                "time": bar_time.strftime("%H:%M"),
                "bw": round(cur_bw, 5),
                "bw_avg": round(avg_bw, 5),
            })
    signals.sort(key=lambda s: s["idx"])
    return signals


# ── Real-fills runner for one (strike_offset, premium_stop) config ───────────

def _run_config(rth: pd.DataFrame, signals: list[dict], strike_offset: int,
                premium_stop_pct: float, collect_rows: bool = False):
    overall = _Acc()
    by_bias = {"C": _Acc(), "P": _Acc()}
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    no_data = 0
    rows: list[dict] = []
    for s in signals:
        fill = simulate_trade_real(
            entry_bar_idx=s["idx"], entry_bar=rth.iloc[s["idx"]], spy_df=rth, ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["bollinger_squeeze", "expansion", "volume",
                            "breakout_up" if s["side"] == "C" else "breakout_dn"],
            side=s["side"], qty=QTY, setup="BOLLINGER_SQUEEZE",
            premium_stop_pct=premium_stop_pct, strike_offset=strike_offset)
        if fill is None:
            no_data += 1
            continue
        pnl = fill.dollar_pnl
        day = s["date"].isoformat()
        overall.add(pnl, day)
        by_bias[s["side"]].add(pnl, day)
        by_sample["IS_2025" if s["date"].year == 2025 else "OOS_2026"].add(pnl, day)
        by_q[_quarter(s["date"])].add(pnl, day)
        if collect_rows:
            rows.append({"date": day, "time": s["time"], "side": s["side"], "vix": s["vix"],
                         "strike": fill.strike, "entry_premium": round(fill.entry_premium, 3),
                         "pnl": round(pnl, 2),
                         "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason)})
    return overall, by_bias, by_sample, by_q, no_data, rows


# ── Random-null: same N entries, RANDOM bars (same exit bracket + stop) ───────

def _eligible_entry_indices(rth: pd.DataFrame) -> list[int]:
    """Bars that COULD be an entry: RTH, not too late (need a next bar same day),
    and >= WARMUP into the day. We draw random entries from this pool."""
    day_start: dict[dt.date, int] = {}
    for i, d in enumerate(rth["date"]):
        if d not in day_start:
            day_start[d] = i
    starts = sorted(set(day_start.values()))
    out: list[int] = []
    times = rth["timestamp_et"]
    for k, i0 in enumerate(starts):
        i_end = starts[k + 1] if k + 1 < len(starts) else len(rth)
        # leave a tail so a next-bar entry exists and isn't past 15:55
        for gi in range(i0 + WARMUP_BARS, i_end - 1):
            t = pd.Timestamp(times.iloc[gi])
            if t.tzinfo is not None:
                t = t.tz_localize(None)
            if t.time() >= dt.time(15, 50):
                continue
            out.append(gi)
    return out


def _run_random_null(rth: pd.DataFrame, signals: list[dict], strike_offset: int,
                     premium_stop_pct: float, n_signals_completed: int) -> dict:
    """Draw the SAME number of completed trades from random bars, same exit/stop,
    side drawn from the strategy's own side mix (so the null is direction-matched).
    Average per-trade across N_NULL_SEEDS seeds. Strategy must BEAT the null mean."""
    pool = _eligible_entry_indices(rth)
    if not pool:
        return {"error": "empty random pool"}
    # match the strategy's call/put proportion so the null isn't biased by side
    n_call = sum(1 for s in signals if s["side"] == "C")
    n_put = sum(1 for s in signals if s["side"] == "P")
    tot = max(1, n_call + n_put)
    call_frac = n_call / tot
    target = max(n_signals_completed, 20)

    seed_means: list[float] = []
    seed_totals: list[float] = []
    for seed in range(N_NULL_SEEDS):
        rng = random.Random(1000 + seed)
        acc = _Acc()
        tries = 0
        while acc.n < target and tries < target * 25:
            tries += 1
            gi = rng.choice(pool)
            side = "C" if rng.random() < call_frac else "P"
            # rejection level for a random bar: place it just out-of-the-money relative
            # to entry so the level-stop is not artificially tight/loose: use a band-like
            # offset of ~0.15% of price on the invalidation side.
            spot = float(rth["close"].iloc[gi])
            rej = spot * (1 - 0.0015) if side == "C" else spot * (1 + 0.0015)
            fill = simulate_trade_real(
                entry_bar_idx=gi, entry_bar=rth.iloc[gi], spy_df=rth, ribbon_df=None,
                rejection_level=round(rej, 2),
                triggers_fired=["random_null"], side=side, qty=QTY,
                setup="RANDOM_NULL", premium_stop_pct=premium_stop_pct,
                strike_offset=strike_offset)
            if fill is None:
                continue
            acc.add(fill.dollar_pnl, rth["date"].iloc[gi].isoformat())
        if acc.n:
            seed_means.append(acc.pnl / acc.n)
            seed_totals.append(acc.pnl)
    if not seed_means:
        return {"error": "no random fills"}
    null_mean = sum(seed_means) / len(seed_means)
    null_lo = min(seed_means)
    null_hi = max(seed_means)
    return {
        "seeds": len(seed_means),
        "target_n_per_seed": target,
        "null_per_trade_mean": round(null_mean, 2),
        "null_per_trade_min": round(null_lo, 2),
        "null_per_trade_max": round(null_hi, 2),
        "call_frac": round(call_frac, 3),
    }


def run(tag: str) -> dict:
    rth, vix_arr = _load_rth_and_vix()
    log.info("Detecting bollinger-squeeze breakout signals (causal)...")
    signals = _detect_signals(rth, vix_arr)
    log.info("Signals: %d (calls=%d puts=%d)", len(signals),
             sum(1 for s in signals if s["side"] == "C"),
             sum(1 for s in signals if s["side"] == "P"))

    # ── PRIMARY: survivor structure (ITM-2, -8% stop, v15 exits) ─────────────
    log.info("Running PRIMARY survivor-structure config (offset=%d stop=%.2f)...",
             PRIMARY_STRIKE_OFFSET, PRIMARY_PREMIUM_STOP)
    p_overall, p_bias, p_sample, p_q, p_nodata, p_rows = _run_config(
        rth, signals, PRIMARY_STRIKE_OFFSET, PRIMARY_PREMIUM_STOP, collect_rows=True)

    q_reports = {k: p_q[k].report() for k in sorted(p_q)}
    pos_q = sum(1 for r in q_reports.values() if r.get("total_pnl", 0) and r["total_pnl"] > 0)
    is_r, oos_r = p_sample["IS_2025"].report(), p_sample["OOS_2026"].report()
    overall_r = p_overall.report()

    # ── (b) RANDOM-NULL on the primary config ────────────────────────────────
    log.info("Running random-null (%d seeds)...", N_NULL_SEEDS)
    null = _run_random_null(rth, signals, PRIMARY_STRIKE_OFFSET, PRIMARY_PREMIUM_STOP, p_overall.n)
    strat_per_trade = overall_r.get("avg_pnl", 0.0) if overall_r.get("n") else 0.0
    null_mean = null.get("null_per_trade_mean")
    beats_random_null = (null_mean is not None) and (strat_per_trade > null_mean)
    random_null_delta = round(strat_per_trade - null_mean, 2) if null_mean is not None else None

    # ── (c) NO-TRUNCATION: sign stability -8% stop vs chart-stop-only (-0.99) ─
    log.info("Running truncation check (chart-stop-only -0.99)...")
    cs_overall, _, _, _, _, _ = _run_config(rth, signals, PRIMARY_STRIKE_OFFSET, -0.99)
    cs_r = cs_overall.report()
    cs_per_trade = cs_r.get("avg_pnl", 0.0) if cs_r.get("n") else 0.0
    sign8 = (strat_per_trade > 0) - (strat_per_trade < 0)
    sign99 = (cs_per_trade > 0) - (cs_per_trade < 0)
    truncation_safe = (sign8 == sign99) and not (strat_per_trade > 0 and cs_per_trade <= 0)

    # ── small SECONDARY sweep (disclosed, does NOT override primary) ──────────
    log.info("Running secondary sweep %dx%d...", len(SWEEP_OFFSETS), len(SWEEP_STOPS))
    sweep = []
    for off in SWEEP_OFFSETS:
        for stp in SWEEP_STOPS:
            o, _, smp, _, _, _ = _run_config(rth, signals, off, stp)
            r = o.report()
            sweep.append({
                "strike_offset": off, "premium_stop_pct": stp,
                "n": r.get("n", 0), "avg_pnl": r.get("avg_pnl"),
                "total_pnl": r.get("total_pnl"),
                "oos_avg_pnl": smp["OOS_2026"].report().get("avg_pnl"),
                "oos_n": smp["OOS_2026"].report().get("n", 0),
            })

    # ── (a) OP-11 gate evaluation (on PRIMARY) ───────────────────────────────
    oos_pt = oos_r.get("avg_pnl", 0.0) if oos_r.get("n") else 0.0
    oos_n = oos_r.get("n", 0)
    top5 = overall_r.get("top5_day_pct")
    ex_top5 = overall_r.get("pnl_ex_top5_days", 0)
    gate_oos_pos = oos_pt > 0
    gate_quarters = pos_q >= 4
    gate_top5 = (top5 is not None) and (top5 < 200)
    gate_n = overall_r.get("n", 0) >= 20 and oos_n >= 1
    gate_drop_top5 = ex_top5 > 0
    op11_pass = all([gate_oos_pos, gate_quarters, gate_top5, gate_n, gate_drop_top5])

    clears_bar = op11_pass and beats_random_null and truncation_safe

    if clears_bar:
        verdict = ("SHIP CANDIDATE — bollinger_squeeze SURVIVES the 0DTE wall on the "
                   "survivor structure (passes OP-11 + random-null + truncation). "
                   "File A/B scorecard and ship under standing authorization, report for REVOKE.")
    else:
        reasons = []
        if not gate_n:
            reasons.append(f"n<20 (overall={overall_r.get('n',0)}, oos={oos_n})")
        if not gate_oos_pos:
            reasons.append(f"OOS per-trade<=0 ({oos_pt})")
        if not gate_quarters:
            reasons.append(f"positive_quarters<4 ({pos_q}/{len(q_reports)})")
        if not gate_top5:
            reasons.append(f"top5_day>=200% ({top5})")
        if not gate_drop_top5:
            reasons.append(f"drop-top5<=0 ({ex_top5})")
        if not beats_random_null:
            reasons.append(f"does NOT beat random-null (strat={strat_per_trade} vs null={null_mean})")
        if not truncation_safe:
            reasons.append(f"truncation artifact (-8%={strat_per_trade} vs -0.99={cs_per_trade})")
        verdict = ("REJECT — bollinger_squeeze fails the 0DTE wall. " + "; ".join(reasons)
                   + ". Consistent with C3/L58: SPY-price signal, no surviving option edge.")

    summary = {
        "run_date": dt.date.today().isoformat(),
        "strategy": "bollinger_squeeze",
        "cls": "continuation-breakout",
        "source": "SwjshAK data/brain/bollinger-breakout.md",
        "hypothesis": ("BB(20,2) bandwidth squeeze (<50% recent avg) -> expansion + volume "
                       "-> breakout entry in expansion direction (up=CALL, down=PUT). "
                       "Vol-expansion continuation."),
        "window": f"{START}..{END}",
        "signal_params": {
            "bb_len": BB_LEN, "bb_k": BB_K, "bw_avg_lookback": BW_AVG_LOOKBACK,
            "squeeze_ratio": SQUEEZE_RATIO, "vol_avg_lookback": VOL_AVG_LOOKBACK,
            "vol_mult": VOL_MULT, "cooldown_min": COOLDOWN_MIN, "warmup_bars": WARMUP_BARS,
            "rth": "09:30-16:00", "causal": True, "per_day_reset": True,
        },
        "n_signals": len(signals),
        "n_calls": sum(1 for s in signals if s["side"] == "C"),
        "n_puts": sum(1 for s in signals if s["side"] == "P"),
        "primary_config": {
            "strike_offset": PRIMARY_STRIKE_OFFSET, "premium_stop_pct": PRIMARY_PREMIUM_STOP,
            "qty": QTY, "exits": "default v15",
            "label": "SURVIVOR STRUCTURE (ITM-2 + -8% stop + v15 exits)",
        },
        "primary_overall": overall_r,
        "primary_by_side": {k: v.report() for k, v in p_bias.items()},
        "primary_IS_2025": is_r,
        "primary_OOS_2026": oos_r,
        "primary_by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{len(q_reports)}",
        "n_no_opra_data": p_nodata,
        "self_verify": {
            "a_op11": {
                "pass": op11_pass,
                "oos_per_trade_gt0": gate_oos_pos, "oos_per_trade": oos_pt, "oos_n": oos_n,
                "positive_quarters_ge4": gate_quarters,
                "top5_day_lt200pct": gate_top5, "top5_day_pct": top5,
                "n_ge20": gate_n, "n_overall": overall_r.get("n", 0),
                "drop_top5_days_gt0": gate_drop_top5, "pnl_ex_top5_days": ex_top5,
            },
            "b_random_null": {
                "pass": beats_random_null,
                "strategy_per_trade": strat_per_trade,
                **null,
                "delta_strategy_minus_null": random_null_delta,
            },
            "c_no_truncation": {
                "pass": truncation_safe,
                "per_trade_stop_8pct": strat_per_trade,
                "per_trade_chart_stop_only_99": cs_per_trade,
                "sign_8pct": sign8, "sign_99": sign99,
                "note": "FAIL if sign inverts OR positive only because -8% truncates losers",
            },
            "ALL_THREE_PASS": clears_bar,
        },
        "secondary_sweep": sweep,
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) — the only WR authority",
            "spy_vs_option": "bollinger squeeze is a SPY-PRICE signal; this is the OPTION-edge test (C3/L58)",
            "per_trade": "expectancy (avg_pnl) reported, not WR alone (OP-14/OP-20)",
            "concentration": "top5_day_pct + pnl_ex_top5_days shown (OP-20 #5)",
            "no_cherry_pick": ("PRIMARY survivor-structure verdict is canonical; the secondary "
                               "sweep is disclosed in full but does NOT override it (anti-2.10)"),
            "random_null": "direction-matched random entries, same exit bracket+stop, 20 seeds",
            "truncation": "sign-stability of per-trade between -8% stop and chart-stop-only",
        },
        "verdict": verdict,
        "results_primary": p_rows,
    }

    out = ROOT / "analysis" / "recommendations" / f"swjshak-{tag}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", out)

    print("\n=== BOLLINGER-SQUEEZE REAL-FILLS VERDICT ===")
    print(f"signals={len(signals)} (C={summary['n_calls']} P={summary['n_puts']})  completed={overall_r.get('n',0)}  no_opra={p_nodata}")
    print(f"PRIMARY (ITM-2,-8%): {overall_r}")
    print(f"  by_side: C={summary['primary_by_side']['C']}  P={summary['primary_by_side']['P']}")
    print(f"  IS_2025 : {is_r}")
    print(f"  OOS_2026: {oos_r}")
    print(f"  quarters: {pos_q}/{len(q_reports)}  {q_reports}")
    print(f"(a) OP-11 pass={op11_pass}  [oos>0={gate_oos_pos} q>=4={gate_quarters} top5<200={gate_top5} n>=20={gate_n} drop5>0={gate_drop_top5}]")
    print(f"(b) random-null pass={beats_random_null}  strat={strat_per_trade} vs null_mean={null_mean} (delta={random_null_delta})")
    print(f"(c) truncation-safe={truncation_safe}  -8%={strat_per_trade} vs -0.99={cs_per_trade}")
    print(f"ALL THREE PASS = {clears_bar}")
    print(f"VERDICT: {verdict}")
    return summary


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tag", default="bollinger-squeeze")
    args = p.parse_args(argv)
    run(args.tag)
    return 0


if __name__ == "__main__":
    sys.exit(main())

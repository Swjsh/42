"""SwjshAK NEW-HUNT: "Three Ducks" multi-timeframe (MTF) momentum alignment on SPY 5m
-> 0DTE single-leg directional. Continuation / trend class (survivor class).

Engine does NOT have this. We read trend from the EMA ribbon / market-structure swings;
we do NOT have a clean 3-timeframe SMA60 alignment momentum gate.

────────────────────────────────────────────────────────────────────────────────
STEP 1 — SOURCED RULE (SwjshAK, J's first project). Concise rule extracted verbatim from
`markdown/research/SWJSHAK-STRATEGY-EXTRACTION-2026-06-20.md` row 7, which in turn pulled it
from `data/brain/three-ducks.md` in the old project (read-only; not in this repo):

    "Three Ducks (MTF align): 4H price>SMA60 + 1H>SMA60 + 5m SMA60 cross -> entry
     (all 3 TFs agree)."

This is the classic Robbie/"Three Ducks Trading System" (Trader Dale / babypips folklore):
all three ducks must "line up" — the higher two timeframes define the REGIME (price on the
correct side of its 60-period SMA), and the lowest timeframe (5m) provides the TRIGGER (a
fresh SMA60 cross in the regime direction).

  - BULLISH (all up):  4H close > 4H-SMA60  AND  1H close > 1H-SMA60  AND
                       5m close crosses ABOVE 5m-SMA60 (prev close <= SMA, this close > SMA)
                       -> BUY CALL ('C')
  - BEARISH (mirror):  4H close < 4H-SMA60  AND  1H close < 1H-SMA60  AND
                       5m close crosses BELOW 5m-SMA60
                       -> BUY PUT ('P')

ADAPTATION TO SPY 5m INTRADAY 0DTE (single-leg directional) — NO LOOK-AHEAD (C6):
  - The 5m series is the CONTINUOUS RTH 5-min close series (concatenated across days,
    reset_index). SMA60 on 5m ~= 5 hours of bars (a within/cross-session trend proxy).
  - 1H and 4H regimes are built by RESAMPLING the continuous 5m series (right-closed,
    right-labeled bins) and computing SMA60 on each higher TF. CAUSALITY: a higher-TF bar
    is only usable AFTER it closes, so each higher-TF (close>SMA) boolean is SHIFTED by one
    bar and then mapped onto the 5m grid with a backward (ffill) as-of join. At 5m bar i the
    regime reflects only higher-TF bars that had fully closed at-or-before bar i's close.
    NOTE: 1H-SMA60 needs 60 one-hour bars and 4H-SMA60 needs 60 four-hour bars of history;
    on a ~6.5h RTH session these span many trading days (the continuous series treats the
    cash session as contiguous — standard for an intraday SMA proxy of a daily-bar idea).
  - 5m SMA60 cross is evaluated on CLOSED bars only (prev vs current close vs current SMA);
    entry fills on the NEXT 5m bar via simulator_real (min hold 5 min) — no look-ahead.
  - rejection_level (strategy INVALIDATION, so the chart-stop is meaningful):
      CALL -> recent SWING LOW below entry  (support that must hold)
      PUT  -> recent SWING HIGH above entry (resistance that must hold)
    over a trailing window of prior+current closed bars (no future look-ahead).
  - Cooldown 30 min between signals (anti-pattern 2.7 — no back-to-back same-setup churn).
  - Entry gate 09:35-15:45 ET (match prod 09:35 gate; leave room before 15:50 time stop).

STEP 2 — REAL-FILLS (C1 authority): simulator_real.simulate_trade_real, v15 default exits,
qty=3. PRIMARY config = SURVIVOR STRUCTURE: strike_offset=-2 (ITM-2), premium_stop_pct=-0.08.
Then a SMALL secondary sweep strike_offset {-2,-1,0} x premium_stop {-0.08,-0.20,-0.50,-0.99}.

STEP 3 — HARD SELF-VERIFY (deterministic, in-script — NO agents; ALL MANDATORY):
  (a) OP-11: OOS(2026) per-trade>0 AND positive_quarters>=4/6 AND top5-day<200% AND n>=20
      AND drop-top-5-days per-trade still >0.
  (b) RANDOM-NULL: re-run with RANDOM entry bars (same count, same call/put mix, same
      exit/stop/strike, ~20 seeds); strategy per-trade MUST beat the null mean. If random
      ties it, the edge is the exit bracket not the signal -> FAIL.
  (c) NO-TRUNCATION: the SIGN of per-trade must NOT invert between -8% stop and chart-stop-
      only (-0.99) at the SURVIVOR strike (ITM-2). If only positive because -8% truncates
      losers -> stop artifact -> FAIL.
A real edge passes ALL of (a)+(b)+(c).

OP-20 honesty: per-trade expectancy (not WR); IS/OOS; concentration; random-null delta +
truncation check reported. No cherry-picking (anti-2.10) — verdict uses the PRIMARY survivor
config as the headline; the sweep is disclosure, not a winner-picker.

Output: analysis/recommendations/swjshak-three-ducks.json
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from autoresearch.null_baseline import random_entry_null  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "swjshak-three-ducks.json"

# ── Strategy parameters ──────────────────────────────────────────────────────
SMA_LEN = 60                    # Three Ducks SMA60 on every timeframe
SWING_LOOKBACK = 12             # bars for invalidation swing low/high (~60 min)
QTY = 3
COOLDOWN_MIN = 30
RTH_START = dt.time(9, 30)
RTH_END = dt.time(16, 0)
ENTRY_GATE_START = dt.time(9, 35)   # match prod 09:35 entry gate (no first-bar)
ENTRY_GATE_END = dt.time(15, 45)    # leave room before 15:50 time stop
START = dt.date(2025, 1, 1)
END = dt.date(2026, 5, 15)

# PRIMARY survivor config (the live-vwap_continuation shape: ITM-2 + tight -8% stop)
PRIMARY_STRIKE_OFFSET = -2
PRIMARY_STOP = -0.08
TRUNCATION_STOP = -0.99             # chart-stop only — the (c) truncation comparator

# Secondary sweep (disclosure only — NOT a winner-picker)
STRIKE_OFFSETS = [-2, -1, 0]
PREMIUM_STOPS = [-0.08, -0.20, -0.50, -0.99]

RANDOM_SEEDS = 20

# Self-verify gate (OP-11)
GATE = {"oos_per_trade": 0.0, "positive_quarters_min": 4, "top5_max_pct": 200.0,
        "n_min": 20, "drop_top5_per_trade_min": 0.0}


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
        return {
            "n": self.n,
            "wr": round(100 * self.wins / self.n, 1),
            "total_pnl": round(self.pnl, 0),
            "per_trade": round(self.pnl / self.n, 2),
            "top5_day_pct": round(100 * top5 / self.pnl, 0) if self.pnl > 0 else None,
        }


def _drop_top5_per_trade(rows: list[dict]) -> tuple[float, int, float]:
    """Per-trade expectancy after removing the 5 best P&L days."""
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        by_day[r["date"]] += r["pnl"]
    top5_days = [d for d, _ in sorted(by_day.items(), key=lambda kv: kv[1], reverse=True)[:5]]
    kept = [r for r in rows if r["date"] not in top5_days]
    dropped_pnl = sum(by_day[d] for d in top5_days)
    if not kept:
        return 0.0, 0, dropped_pnl
    return sum(r["pnl"] for r in kept) / len(kept), len(kept), dropped_pnl


def _htf_regime_on_5m(rth: pd.DataFrame, rule: str) -> tuple[pd.Series, pd.Series]:
    """Build a CAUSAL higher-timeframe (close>SMA60 / close<SMA60) regime mapped onto the
    5m grid.

    Resample the continuous 5m close series to `rule` (e.g. '1H','4H') with right-closed,
    right-labeled bins (bar timestamp = bar CLOSE time). Compute SMA60 on the higher TF.
    SHIFT the (close>SMA) / (close<SMA) booleans by ONE higher-TF bar so a bar is only
    usable AFTER it closes, then as-of (ffill) map back to each 5m bar by its close time.

    Returns (bull_regime, bear_regime) boolean Series aligned to rth.index. NaN-SMA bars
    (insufficient history) map to False (regime not yet established -> no trade).
    """
    s = rth.copy()
    ts = pd.to_datetime(s["timestamp_et"])
    if ts.dt.tz is not None:
        ts = ts.dt.tz_localize(None)
    s = s.assign(_ts=ts).set_index("_ts")
    # 5m bar timestamp in this data is the bar START (e.g. 09:30 covers 09:30-09:35).
    # The bar CLOSE = start + 5min. Use close time so the as-of join reflects closed info.
    close_time = s.index + pd.Timedelta(minutes=5)

    htf_close = s["close"].resample(rule, label="right", closed="right").last().dropna()
    if len(htf_close) < SMA_LEN + 1:
        idx = rth.index
        return pd.Series(False, index=idx), pd.Series(False, index=idx)
    htf_sma = htf_close.rolling(SMA_LEN, min_periods=SMA_LEN).mean()
    bull_htf = (htf_close > htf_sma)
    bear_htf = (htf_close < htf_sma)
    # Causality (C6): a higher-TF bar labeled at time T closes AT T (right-labeled bins). It
    # can only be CONSUMED by a 5m bar whose CLOSE time is strictly AFTER T. We enforce this
    # with merge_asof(direction='backward', allow_exact_matches=False): for each 5m close-time
    # it picks the most-recent higher-TF bar that closed STRICTLY before. No look-ahead, and
    # no redundant extra-bar lag — the regime is the latest fully-closed HTF bar, exactly the
    # faithful reading of "4H close>SMA60 / 1H close>SMA60" as of the 5m signal bar.
    htf_frame = pd.DataFrame({
        "htf_time": htf_close.index,
        "bull": bull_htf.values,
        "bear": bear_htf.values,
    }).dropna(subset=["htf_time"])

    q = pd.DataFrame({"close_time": close_time.values, "orig_idx": rth.index})
    q = q.sort_values("close_time")
    htf_frame = htf_frame.sort_values("htf_time")
    merged = pd.merge_asof(
        q, htf_frame, left_on="close_time", right_on="htf_time",
        direction="backward", allow_exact_matches=False,
    )
    # NaN (no prior closed HTF bar) -> False. Cast to float first so the fillna is a
    # numeric downcast (avoids the object-dtype FutureWarning), then to bool.
    merged["bull"] = merged["bull"].astype(float).fillna(0.0).astype(bool)
    merged["bear"] = merged["bear"].astype(float).fillna(0.0).astype(bool)
    merged = merged.set_index("orig_idx").reindex(rth.index)
    return merged["bull"].fillna(False).astype(bool), merged["bear"].fillna(False).astype(bool)


def build_signals(rth: pd.DataFrame, vix_arr: list[float]) -> list[dict]:
    """Causal Three Ducks signals on the continuous 5m close series.

    Regime: 1H + 4H both on the correct side of their SMA60 (causal as-of, shifted).
    Trigger: 5m SMA60 cross in the regime direction (prev vs current close, both closed bars).
    """
    close = rth["close"].astype(float)
    sma5 = close.rolling(SMA_LEN, min_periods=SMA_LEN).mean()

    bull_1h, bear_1h = _htf_regime_on_5m(rth, "1h")
    bull_4h, bear_4h = _htf_regime_on_5m(rth, "4h")

    signals: list[dict] = []
    last_sig_time: dt.datetime | None = None

    for idx in range(1, len(rth)):
        s5 = sma5.iloc[idx]
        s5_prev = sma5.iloc[idx - 1]
        if pd.isna(s5) or pd.isna(s5_prev):
            continue
        bar = rth.iloc[idx]
        ts = pd.Timestamp(bar["timestamp_et"])
        if ts.tz is not None:
            ts = ts.tz_localize(None)
        bar_dt = ts.to_pydatetime()
        t = bar_dt.time()
        if t < ENTRY_GATE_START or t > ENTRY_GATE_END:
            continue
        bd = bar_dt.date()
        if bd < START or bd > END:
            continue

        c = float(bar["close"])
        c_prev = float(rth["close"].iloc[idx - 1])

        # 5m SMA60 cross (closed-bar): prev on/below -> current above (bull); mirror (bear)
        cross_up = (c_prev <= s5_prev) and (c > s5)
        cross_dn = (c_prev >= s5_prev) and (c < s5)

        # All three ducks aligned
        bull_sig = cross_up and bool(bull_1h.iloc[idx]) and bool(bull_4h.iloc[idx])
        bear_sig = cross_dn and bool(bear_1h.iloc[idx]) and bool(bear_4h.iloc[idx])
        if not (bull_sig or bear_sig):
            continue

        if last_sig_time is not None and (bar_dt - last_sig_time).total_seconds() / 60.0 < COOLDOWN_MIN:
            continue

        side = "C" if bull_sig else "P"

        # Invalidation level over trailing window (prior+current closed bars only)
        lo_start = max(0, idx - SWING_LOOKBACK + 1)
        win = rth.iloc[lo_start: idx + 1]
        if side == "C":
            swing = float(win["low"].min())
            rej = swing if swing < c else round(c - 1.0, 2)
        else:
            swing = float(win["high"].max())
            rej = swing if swing > c else round(c + 1.0, 2)

        last_sig_time = bar_dt
        signals.append({
            "idx": idx, "date": bd, "time": bar_dt.strftime("%H:%M"), "side": side,
            "sma5": round(float(s5), 2), "entry_spot": round(c, 2),
            "rejection_level": round(float(rej), 2), "vix": round(vix_arr[idx], 1),
        })
    return signals


def simulate_cell(rth: pd.DataFrame, signals: list[dict], strike_offset: int,
                  premium_stop_pct: float) -> tuple[_Acc, list[dict], int]:
    """Run real-fills for one (strike_offset, premium_stop) cell."""
    overall = _Acc()
    rows: list[dict] = []
    no_data = 0
    for s in signals:
        fill = simulate_trade_real(
            entry_bar_idx=s["idx"], entry_bar=rth.iloc[s["idx"]], spy_df=rth, ribbon_df=None,
            rejection_level=s["rejection_level"],
            triggers_fired=["three_ducks_mtf", "sma60_cross_5m",
                            "regime_bull_1h_4h" if s["side"] == "C" else "regime_bear_1h_4h"],
            side=s["side"], qty=QTY, setup="THREE_DUCKS",
            premium_stop_pct=premium_stop_pct, strike_offset=strike_offset)
        if fill is None:
            no_data += 1
            continue
        pnl = float(fill.dollar_pnl)
        day = s["date"].isoformat()
        overall.add(pnl, day)
        rows.append({
            "date": day, "time": s["time"], "side": s["side"], "vix": s["vix"],
            "strike": fill.strike, "entry_premium": round(fill.entry_premium, 3),
            "pnl": round(pnl, 2), "year": s["date"].year, "quarter": _quarter(s["date"]),
            "exit": fill.exit_reason.value if hasattr(fill.exit_reason, "value") else str(fill.exit_reason),
        })
    return overall, rows, no_data


def verify_cell(rows: list[dict]) -> dict:
    """Deterministic OP-11 self-verification for a single cell's per-trade rows (gate a)."""
    by_sample = {"IS_2025": _Acc(), "OOS_2026": _Acc()}
    by_q: dict[str, _Acc] = defaultdict(_Acc)
    overall = _Acc()
    for r in rows:
        overall.add(r["pnl"], r["date"])
        by_sample["IS_2025" if r["year"] == 2025 else "OOS_2026"].add(r["pnl"], r["date"])
        by_q[r["quarter"]].add(r["pnl"], r["date"])

    q_reports = {k: by_q[k].report() for k in sorted(by_q)}
    pos_q = sum(1 for v in q_reports.values() if v.get("total_pnl", 0) and v["total_pnl"] > 0)
    is_r, oos_r = by_sample["IS_2025"].report(), by_sample["OOS_2026"].report()
    drop_pt, n_ex, dropped = _drop_top5_per_trade(rows)
    ov = overall.report()

    oos_pt = oos_r.get("per_trade") if oos_r.get("n") else None
    clears = bool(
        (oos_pt is not None and oos_pt > GATE["oos_per_trade"]) and
        (pos_q >= GATE["positive_quarters_min"]) and
        (ov.get("top5_day_pct") is not None and ov["top5_day_pct"] < GATE["top5_max_pct"]) and
        (ov["n"] >= GATE["n_min"]) and
        (drop_pt > GATE["drop_top5_per_trade_min"])
    )
    return {
        "overall": ov,
        "by_sample": {k: v.report() for k, v in by_sample.items()},
        "by_quarter": q_reports,
        "positive_quarters": f"{pos_q}/{len(q_reports)}",
        "positive_quarters_n": pos_q,
        "n_quarters": len(q_reports),
        "oos_per_trade": oos_pt,
        "drop_top5_per_trade": round(drop_pt, 2),
        "drop_top5_n": n_ex,
        "dropped_top5_pnl": round(dropped, 0),
        "top5_day_pct": ov.get("top5_day_pct"),
        "clears_bar": clears,
    }


def run() -> dict:
    log.info("Loading %s..%s SPY+VIX", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= RTH_START)
                   & (spy_full["timestamp_et"].dt.time < RTH_END)].reset_index(drop=True)
    rth["date"] = rth["timestamp_et"].dt.date
    log.info("RTH bars: %d", len(rth))

    # VIX aligned (ffill) — same pattern as the reference scripts
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

    signals = build_signals(rth, vix_arr)
    n_call = sum(1 for s in signals if s["side"] == "C")
    n_put = sum(1 for s in signals if s["side"] == "P")
    log.info("Three Ducks signals: %d (CALL=%d PUT=%d)", len(signals), n_call, n_put)

    # ── Secondary sweep (disclosure only) ──────────────────────────────────
    sweep: list[dict] = []
    primary_rows: list[dict] = []
    primary_overall: _Acc | None = None
    trunc_rows: list[dict] = []   # ITM-2 chart-stop-only cell, for the (c) truncation check
    for so in STRIKE_OFFSETS:
        for ps in PREMIUM_STOPS:
            overall, rows, no_data = simulate_cell(rth, signals, so, ps)
            rep = overall.report()
            sweep.append({"strike_offset": so, "premium_stop_pct": ps,
                          "report": rep, "n_no_opra_data": no_data})
            log.info("  so=%+d ps=%.2f -> n=%s per_trade=%s total=%s top5%%=%s",
                     so, ps, rep.get("n"), rep.get("per_trade"), rep.get("total_pnl"),
                     rep.get("top5_day_pct"))
            if so == PRIMARY_STRIKE_OFFSET and abs(ps - PRIMARY_STOP) < 1e-9:
                primary_rows, primary_overall = rows, overall
            if so == PRIMARY_STRIKE_OFFSET and abs(ps - TRUNCATION_STOP) < 1e-9:
                trunc_rows = rows

    n_primary = primary_overall.n if primary_overall else 0

    # ── (a) OP-11 structural self-verify on the PRIMARY survivor config ──
    verify = verify_cell(primary_rows) if primary_rows else {
        "overall": {"n": 0}, "by_sample": {}, "by_quarter": {}, "positive_quarters": "0/0",
        "positive_quarters_n": 0, "n_quarters": 0, "oos_per_trade": None,
        "drop_top5_per_trade": 0.0, "drop_top5_n": 0, "dropped_top5_pnl": 0,
        "top5_day_pct": None, "clears_bar": False}
    primary_pt = verify["overall"].get("per_trade") if verify["overall"].get("n") else None

    # ── (b) RANDOM-NULL on the PRIMARY survivor config ──
    null = None
    null_pass = False
    if n_primary > 0:
        log.info("Running random-entry NULL (%d seeds) for PRIMARY survivor cell...", RANDOM_SEEDS)
        null = random_entry_null(rth, n_signals=len(primary_rows), n_call=n_call, n_put=n_put,
                                 strike_offset=PRIMARY_STRIKE_OFFSET, premium_stop_pct=PRIMARY_STOP,
                                 entry_gate=(ENTRY_GATE_START, ENTRY_GATE_END),
                                 swing_lookback=SWING_LOOKBACK, qty=QTY, seeds=RANDOM_SEEDS)
        edge_over_null = round((primary_pt if primary_pt is not None else 0.0) - null["per_trade_mean"], 2)
        beats_null_mean = primary_pt is not None and primary_pt > null["per_trade_mean"]
        beats_null_max = primary_pt is not None and primary_pt > null["per_trade_max"]
        drop_beats_null_mean = verify["drop_top5_per_trade"] > null["per_trade_mean"]
        null["edge_over_null_per_trade"] = edge_over_null
        null["best_beats_null_mean"] = bool(beats_null_mean)
        null["best_beats_null_max"] = bool(beats_null_max)
        null["drop_top5_beats_null_mean"] = bool(drop_beats_null_mean)
        # Task (b): per-trade MUST beat the null mean. (We also report the stricter max test.)
        null_pass = bool(beats_null_mean and drop_beats_null_mean)

    # ── (c) NO-TRUNCATION: sign must not invert between -8% stop and -0.99 at ITM-2 ──
    trunc_overall = _Acc()
    for r in trunc_rows:
        trunc_overall.add(r["pnl"], r["date"])
    trunc_rep = trunc_overall.report()
    trunc_pt = trunc_rep.get("per_trade") if trunc_rep.get("n") else None
    if primary_pt is None or trunc_pt is None:
        truncation_safe = False
    else:
        # Safe iff the sign does NOT invert (both >=0, or both <=0). A flip from + (at -8%)
        # to - (at chart-stop) means the -8% stop was truncating losers -> stop artifact.
        truncation_safe = (primary_pt >= 0) == (trunc_pt >= 0)
    truncation = {
        "primary_stop_per_trade": primary_pt,
        "chart_stop_only_per_trade": trunc_pt,
        "primary_stop_n": n_primary,
        "chart_stop_only_n": trunc_rep.get("n", 0),
        "sign_inverts": (None if (primary_pt is None or trunc_pt is None)
                         else bool((primary_pt >= 0) != (trunc_pt >= 0))),
        "truncation_safe": bool(truncation_safe),
    }

    coded_pass = bool(verify["clears_bar"])
    clears_bar = bool(coded_pass and null_pass and truncation_safe)

    # ── Verdict (no cherry-pick: PRIMARY survivor config is the headline) ──
    if n_primary == 0:
        verdict = ("NO_CANDIDATE: PRIMARY survivor cell produced 0 completed trades "
                   "(strategy too sparse on SPY 5m 0DTE or no OPRA data at ITM-2).")
    elif n_primary < GATE["n_min"]:
        verdict = (f"NO_CANDIDATE: PRIMARY survivor cell n={n_primary} < {GATE['n_min']} "
                   "(too few signals to validate — three-duck MTF alignment is rare on SPY).")
    elif clears_bar:
        verdict = ("REAL CANDIDATE: PRIMARY survivor config (ITM-2, -8% stop) clears OP-11 "
                   "(a) AND beats the random-entry null (b) AND is truncation-safe (c) — the "
                   "Three Ducks MTF signal adds option-edge beyond the asymmetric exit structure.")
    else:
        fails = []
        v = verify
        if not (v["oos_per_trade"] is not None and v["oos_per_trade"] > 0):
            fails.append(f"(a) OOS per-trade={v['oos_per_trade']} (need >0)")
        if v["positive_quarters_n"] < GATE["positive_quarters_min"]:
            fails.append(f"(a) positive_quarters={v['positive_quarters']} (need >=4/6)")
        if not (v["top5_day_pct"] is not None and v["top5_day_pct"] < GATE["top5_max_pct"]):
            fails.append(f"(a) top5_day_pct={v['top5_day_pct']} (need <200)")
        if v["overall"].get("n", 0) < GATE["n_min"]:
            fails.append(f"(a) n={v['overall'].get('n')} (need >=20)")
        if not (v["drop_top5_per_trade"] > 0):
            fails.append(f"(a) drop_top5_per_trade={v['drop_top5_per_trade']} (need >0)")
        if null is not None and not null["best_beats_null_mean"]:
            fails.append(f"(b) per_trade={primary_pt} does NOT beat random-null MEAN "
                         f"{null['per_trade_mean']} (edge_over_null={null['edge_over_null_per_trade']}) "
                         f"=> 'edge' is the asymmetric exit STRUCTURE, not the MTF signal (C3/L58)")
        if null is not None and not null["drop_top5_beats_null_mean"]:
            fails.append(f"(b) drop-top5 per-trade={v['drop_top5_per_trade']} <= random-null mean "
                         f"{null['per_trade_mean']} => surviving edge is day-concentration, not signal")
        if not truncation_safe:
            fails.append(f"(c) per-trade SIGN inverts between -8% stop ({primary_pt}) and chart-stop-only "
                         f"({trunc_pt}) => the -8% stop is truncating losers (stop artifact, not signal)")
        verdict = "NOT A CANDIDATE (no cherry-pick): PRIMARY survivor config fails — " + "; ".join(fails)

    summary = {
        "run_date": dt.date.today().isoformat(),
        "strategy": "three_ducks",
        "cls": "continuation",
        "hypothesis": ("Three Ducks MTF: 4H close>SMA60 AND 1H close>SMA60 -> bullish regime; "
                       "enter on 5m SMA60 cross that direction (CALL); mirror bearish (PUT). "
                       "Continuation/trend (survivor class)."),
        "source": "SwjshAK data/brain/three-ducks.md (via markdown/research/SWJSHAK-STRATEGY-EXTRACTION-2026-06-20.md row 7)",
        "window": f"{START}..{END}",
        "sourced_rule": {
            "regime_4h": "4H close vs 4H-SMA60 (>SMA = bull duck, <SMA = bear duck)",
            "regime_1h": "1H close vs 1H-SMA60 (>SMA = bull duck, <SMA = bear duck)",
            "trigger_5m": "5m close crosses SMA60 in the regime direction (closed-bar cross)",
            "alignment": "all 3 ducks must agree (regime 4H + regime 1H + 5m cross direction)",
            "original_exit": "FX swing system has no 0DTE exit; substituted v15 intraday exits "
                             "(TP1 +30%/chart-level, BE runner, 15:50 hard time stop) per task spec",
        },
        "adaptation": {
            "instrument": "SPY 0DTE single-leg directional (bull->CALL, bear->PUT)",
            "sma_len": SMA_LEN, "timeframes": ["5min(trigger)", "1H(regime)", "4H(regime)"],
            "htf_causality": ("higher-TF close>SMA booleans shifted 1 bar + merge_asof backward "
                              "(strict prior) onto 5m close-times -> no look-ahead (C6)"),
            "swing_lookback_bars": SWING_LOOKBACK,
            "rejection_level": "CALL->trailing swing LOW (support); PUT->trailing swing HIGH (resistance)",
            "cooldown_min": COOLDOWN_MIN, "entry_gate": f"{ENTRY_GATE_START}-{ENTRY_GATE_END}",
            "qty": QTY, "exits": "v15 defaults (causal, no look-ahead C6)",
        },
        "primary_config": {
            "label": "SURVIVOR STRUCTURE (live vwap_continuation shape)",
            "strike_offset": PRIMARY_STRIKE_OFFSET, "premium_stop_pct": PRIMARY_STOP,
            "exits": "v15 defaults",
        },
        "grid": {"strike_offset": STRIKE_OFFSETS, "premium_stop_pct": PREMIUM_STOPS},
        "self_verify_gate": GATE,
        "n_signals": len(signals), "n_call": n_call, "n_put": n_put,
        "sweep": sweep,
        "primary_verify_a": verify,
        "random_null_b": null,
        "truncation_check_c": truncation,
        "primary_per_trade": primary_pt,
        "oos_per_trade": verify.get("oos_per_trade"),
        "beats_random_null": bool(null_pass),
        "truncation_safe": bool(truncation_safe),
        "clears_bar": clears_bar,
        "verdict": verdict,
        "sample_rows": primary_rows[:25],
        "DISCLOSURE": {
            "authority": "real OPRA fills (C1) — the only WR/expectancy authority",
            "per_trade": "per-trade EXPECTANCY reported, not WR alone (OP-14)",
            "is_oos": "IS=2025, OOS=2026 split shown for the PRIMARY survivor cell",
            "concentration": "top5_day_pct + drop-top-5-days per-trade shown (OP-20 #5; anti-2.10)",
            "no_cherry_pick": ("verdict uses the PRIMARY survivor config (ITM-2,-8%) as the headline, "
                               "NOT the best sweep cell; the sweep is disclosure only"),
            "spy_vs_option": ("C3/L58 — a SPY-price/FX trend edge is NOT an option edge; theta+delta+"
                              "stop-misfire routinely erase a directional-underlying edge in 0DTE"),
            "random_entry_null": ("PRIMARY cell vs a coin-flip null (random RTH entries, same count/"
                                  "side-mix/stop/strike, 20 seeds). If random reproduces the per-trade, "
                                  "the 'edge' is the asymmetric exit STRUCTURE, not the MTF signal."),
            "truncation_check": ("sign of per-trade must NOT invert between -8% stop and chart-stop-only "
                                 "(-0.99) at ITM-2; a +->- flip means the tight stop truncates losers "
                                 "(stop artifact, not directional signal)"),
            "the_0dte_wall": ("23-strategy prior: nearly every directional SPY-price edge dies on 0DTE; "
                              "the only survivor (live vwap_continuation) is ITM-2 + tight -8% stop + "
                              "sustained-directional + morning — which is exactly the PRIMARY config tested"),
        },
    }
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", OUT_JSON)

    print("\n=== SWJSHAK THREE DUCKS REAL-FILLS VERDICT ===")
    print(f"signals={len(signals)} (CALL={n_call} PUT={n_put})")
    print(f"PRIMARY survivor (ITM-2,-8%): n={n_primary} per_trade={primary_pt} "
          f"overall={verify['overall']}")
    if verify["overall"].get("n"):
        print(f"  IS={verify['by_sample'].get('IS_2025')}  OOS={verify['by_sample'].get('OOS_2026')}")
        print(f"  positive_quarters={verify['positive_quarters']}  oos_per_trade={verify['oos_per_trade']}")
        print(f"  drop_top5_per_trade={verify['drop_top5_per_trade']} (n={verify['drop_top5_n']})  "
              f"top5_day_pct={verify['top5_day_pct']}")
    if null is not None:
        print(f"  RANDOM-NULL per_trade: mean={null['per_trade_mean']} "
              f"[{null['per_trade_min']}..{null['per_trade_max']}]  "
              f"edge_over_null={null['edge_over_null_per_trade']}  "
              f"beats_null_mean={null['best_beats_null_mean']}  "
              f"drop_top5_beats_null_mean={null['drop_top5_beats_null_mean']}")
    print(f"  TRUNCATION: -8%={truncation['primary_stop_per_trade']} vs "
          f"chart-only={truncation['chart_stop_only_per_trade']} "
          f"sign_inverts={truncation['sign_inverts']} safe={truncation_safe}")
    print(f"\nCLEARS BAR: {clears_bar}")
    print(f"VERDICT: {verdict}")
    return summary


if __name__ == "__main__":
    run()

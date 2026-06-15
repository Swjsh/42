"""FBW morning timing split: EARLY (09:35-10:30) vs LATE (10:30-11:30).

Extends fbw_morning_mid_validate.py with sub-band walk-forward analysis.

Hypothesis: EARLY signals (first 55-min slot) vs LATE signals (next 60-min
slot) may have distinct edge profiles due to:
- EARLY: First-hour vol, gap-fill dynamics, fresh overnight levels
- LATE: Post-digestion structure, lower vol, more orderly re-test

If EARLY shows strong WF PASS and LATE fails, the watcher window can be
narrowed to 09:35-10:30 in heartbeat.md. If LATE dominates, keep 09:35-11:30.
If both pass, keep the full window for max trade frequency.

Output: analysis/recommendations/fbw_timing_split.json
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import NamedTuple

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from autoresearch import runner as ar_runner  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

OUT_JSON = ROOT / "analysis" / "recommendations" / "fbw_timing_split.json"

# ── Watcher parameters (must match fbw_morning_mid_watcher.py) ───────────────
QTY = 3
PREMIUM_STOP_PCT = -0.99          # chart-stop only (L55: bounce entry, premium stops fail)
STRIKE_OFFSET = 0                 # ATM calls

# Production watcher entry gate: 09:35 (v15 heartbeat entry gate)
ENTRY_TIME_START = dt.time(9, 35)
ENTRY_TIME_END   = dt.time(11, 30)  # MORNING band end

# Split point: EARLY = [09:35, 10:30) | LATE = [10:30, 11:30)
SPLIT_TIME = dt.time(10, 30)

COOLDOWN_MINUTES = 45             # match watcher
CONF_MID_LOW  = 0.65              # inclusive
CONF_MID_HIGH = 0.80              # exclusive

# Chart stop: see fbw_morning_mid_watcher.py rejection_level logic
CHART_STOP_BELOW_SUPPORT = 0.50

START = dt.date(2025, 1, 1)
END   = dt.date(2026, 5, 15)
WALK_FORWARD_SPLIT = dt.date(2025, 9, 30)  # train: Jan-Sep 2025 | test: Oct 2025-May 2026

try:
    from crypto.lib.chart_patterns import Bar, failed_breakdown_wick as _detect_fbw
    _PATTERNS_OK = True
except ImportError:
    _PATTERNS_OK = False
    log.error("crypto.lib.chart_patterns not available")
    sys.exit(1)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_bars(rth: pd.DataFrame, idx: int, window: int = 12) -> list[Bar]:
    start = max(0, idx - window + 1)
    sub = rth.iloc[start: idx + 1]
    result = []
    for _, row in sub.iterrows():
        ts = pd.Timestamp(row["timestamp_et"])
        if ts.tzinfo is not None:
            ts = ts.tz_localize(None)
        open_time = ts.to_pydatetime().replace(tzinfo=dt.timezone.utc)
        result.append(Bar(
            open_time=open_time,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=int(row.get("volume", 50_000)),
            granularity_seconds=300,
            source="spy_5m",
        ))
    return result


class BandStats(NamedTuple):
    label: str
    n: int
    wins: int
    losses: int
    total_pnl: float
    train_n: int
    train_wins: int
    train_pnl: float
    test_n: int
    test_wins: int
    test_pnl: float

    @property
    def wr(self) -> float:
        return self.wins / self.n if self.n else 0.0

    @property
    def avg_pnl(self) -> float:
        return self.total_pnl / self.n if self.n else 0.0

    @property
    def train_wr(self) -> float:
        return self.train_wins / self.train_n if self.train_n else 0.0

    @property
    def test_wr(self) -> float:
        return self.test_wins / self.test_n if self.test_n else 0.0

    @property
    def train_exp(self) -> float:
        return self.train_pnl / self.train_n if self.train_n else 0.0

    @property
    def test_exp(self) -> float:
        return self.test_pnl / self.test_n if self.test_n else 0.0

    @property
    def wf_ratio(self) -> float:
        return self.test_exp / self.train_exp if self.train_exp > 0 else 0.0

    def gate_pass(self) -> bool:
        return (
            self.test_wr >= 0.50
            and self.wr >= 0.50
            and self.test_n >= 10
            and self.test_pnl > 0
        )

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "n": self.n,
            "wr": round(self.wr, 3),
            "avg_pnl": round(self.avg_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "train_n": self.train_n,
            "train_wr": round(self.train_wr, 3),
            "train_exp": round(self.train_exp, 2),
            "train_pnl": round(self.train_pnl, 2),
            "test_n": self.test_n,
            "test_wr": round(self.test_wr, 3),
            "test_exp": round(self.test_exp, 2),
            "test_pnl": round(self.test_pnl, 2),
            "wf_ratio": round(self.wf_ratio, 3),
            "gate_pass": self.gate_pass(),
        }


def _accumulate(
    pnl: float,
    is_train: bool,
    acc: dict,
) -> None:
    """Mutate acc dict — only call from within scan_and_validate."""
    acc["n"] += 1
    acc["total_pnl"] += pnl
    if pnl > 0:
        acc["wins"] += 1
    elif pnl < 0:
        acc["losses"] += 1
    if is_train:
        acc["train_n"] += 1
        acc["train_pnl"] += pnl
        if pnl > 0:
            acc["train_wins"] += 1
    else:
        acc["test_n"] += 1
        acc["test_pnl"] += pnl
        if pnl > 0:
            acc["test_wins"] += 1


def _empty_acc() -> dict:
    return dict(n=0, wins=0, losses=0, total_pnl=0.0,
                train_n=0, train_wins=0, train_pnl=0.0,
                test_n=0, test_wins=0, test_pnl=0.0)


def _acc_to_stats(label: str, acc: dict) -> BandStats:
    return BandStats(
        label=label,
        n=acc["n"],
        wins=acc["wins"],
        losses=acc["losses"],
        total_pnl=acc["total_pnl"],
        train_n=acc["train_n"],
        train_wins=acc["train_wins"],
        train_pnl=acc["train_pnl"],
        test_n=acc["test_n"],
        test_wins=acc["test_wins"],
        test_pnl=acc["test_pnl"],
    )


def _print_band(stats: BandStats) -> None:
    tag = "PASS" if stats.gate_pass() else "FAIL"
    log.info(
        "  %-6s N=%-3d  WR=%5.1f%%  exp=%+6.2f  P&L=%+8.2f  "
        "| WF: train N=%-2d WR=%5.1f%% exp=%+6.2f  test N=%-2d WR=%5.1f%% exp=%+6.2f  ratio=%5.3f  [%s]",
        stats.label, stats.n, stats.wr * 100, stats.avg_pnl, stats.total_pnl,
        stats.train_n, stats.train_wr * 100, stats.train_exp,
        stats.test_n, stats.test_wr * 100, stats.test_exp,
        stats.wf_ratio, tag,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def scan_and_split() -> dict:
    log.info("Loading %s to %s SPY+VIX data...", START, END)
    spy_full, vix_full = ar_runner.load_data(START, END)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date

    rth = spy_full[
        (spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
        (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)
    log.info("RTH bars: %d", len(rth))

    # VIX alignment
    vix_full["timestamp_et"] = pd.to_datetime(
        vix_full["timestamp_et"] if "timestamp_et" in vix_full.columns else vix_full.index
    )
    vix_ser = (
        vix_full.set_index("timestamp_et")["close"]
        if "close" in vix_full.columns
        else vix_full.iloc[:, 0]
    )
    rth_times_naive = (
        rth["timestamp_et"].dt.tz_localize(None)
        if rth["timestamp_et"].dt.tz is not None
        else rth["timestamp_et"]
    )
    vix_vals: list[float] = []
    for ts in rth_times_naive:
        try:
            idx_vix = vix_ser.index.get_indexer([ts], method="ffill")[0]
            vix_vals.append(float(vix_ser.iloc[idx_vix]) if idx_vix >= 0 else 17.0)
        except Exception:
            vix_vals.append(17.0)
    vix_arr = pd.Series(vix_vals, index=rth.index)

    log.info(
        "Scanning MORNING window (%s-%s), conf=[%.2f,%.2f), split at %s ...",
        ENTRY_TIME_START, ENTRY_TIME_END, CONF_MID_LOW, CONF_MID_HIGH, SPLIT_TIME,
    )

    signals: list[dict] = []
    last_signal_time: dt.datetime | None = None

    for idx in range(len(rth)):
        if idx < 12:
            continue

        bar = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        if hasattr(bar_time, "tz_localize") and bar_time.tz is not None:
            bar_time_naive = bar_time.tz_localize(None).to_pydatetime()
        else:
            bar_time_naive = pd.Timestamp(bar_time).to_pydatetime()

        bar_date = bar_time_naive.date()
        if bar_date < START or bar_date > END:
            continue

        bar_time_only = bar_time_naive.time()
        if bar_time_only < ENTRY_TIME_START or bar_time_only >= ENTRY_TIME_END:
            continue

        if last_signal_time is not None:
            elapsed_min = (bar_time_naive - last_signal_time).total_seconds() / 60.0
            if elapsed_min < COOLDOWN_MINUTES:
                continue

        bars = _make_bars(rth, idx, window=12)
        if len(bars) < 12:
            continue

        hit = _detect_fbw(bars, lookback_for_support=10)
        if hit is None:
            continue

        if hit.confidence < CONF_MID_LOW or hit.confidence >= CONF_MID_HIGH:
            continue

        last_signal_time = bar_time_naive
        bar_close = float(bar["close"])
        support = float(hit.notes.get("support_price", bar_close))
        vix_now = float(vix_arr.iloc[idx])
        is_train = bar_date <= WALK_FORWARD_SPLIT
        band = "EARLY" if bar_time_only < SPLIT_TIME else "LATE"

        signals.append({
            "date": bar_date.isoformat(),
            "time": bar_time_naive.strftime("%H:%M"),
            "band": band,
            "bar_idx": idx,
            "bar": bar,
            "side": "C",
            "entry_spot": bar_close,
            "support": round(support, 2),
            "rejection_level": round(support - CHART_STOP_BELOW_SUPPORT, 2),
            "vix": round(vix_now, 1),
            "conf_score": round(hit.confidence, 3),
            "is_train": is_train,
        })

    n_early = sum(1 for s in signals if s["band"] == "EARLY")
    n_late  = sum(1 for s in signals if s["band"] == "LATE")
    log.info(
        "Found %d total signals (%d EARLY / %d LATE, %d train / %d test). Simulating...",
        len(signals), n_early, n_late,
        sum(1 for s in signals if s["is_train"]),
        sum(1 for s in signals if not s["is_train"]),
    )

    # ── Simulate + accumulate ─────────────────────────────────────────────────
    all_acc   = _empty_acc()
    early_acc = _empty_acc()
    late_acc  = _empty_acc()

    results: list[dict] = []
    no_data = 0

    for sig in signals:
        entry_bar = rth.iloc[sig["bar_idx"]]
        fill = simulate_trade_real(
            entry_bar_idx=sig["bar_idx"],
            entry_bar=entry_bar,
            spy_df=rth,
            ribbon_df=None,
            rejection_level=sig["rejection_level"],
            triggers_fired=["fbw_detector", "morning_window", "conf_mid_band"],
            side=sig["side"],
            qty=QTY,
            setup="FAILED_BREAKDOWN_WICK_MORNING_MID",
            premium_stop_pct=PREMIUM_STOP_PCT,
            strike_offset=STRIKE_OFFSET,
        )

        base_rec = {k: v for k, v in sig.items() if k != "bar"}

        if fill is None:
            no_data += 1
            results.append({**base_rec, "outcome": "NO_OPRA_DATA", "pnl": 0.0})
            continue

        pnl = float(fill.dollar_pnl)
        exit_reason = (
            fill.exit_reason.value if hasattr(fill.exit_reason, "value")
            else str(fill.exit_reason)
        )
        outcome = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN")

        _accumulate(pnl, sig["is_train"], all_acc)
        if sig["band"] == "EARLY":
            _accumulate(pnl, sig["is_train"], early_acc)
        else:
            _accumulate(pnl, sig["is_train"], late_acc)

        results.append({
            **base_rec,
            "outcome": outcome,
            "pnl": round(pnl, 2),
            "exit_reason": exit_reason,
            "strike": fill.strike,
            "entry_premium": round(float(fill.entry_premium), 3),
        })

    # ── Build stats objects ───────────────────────────────────────────────────
    all_stats   = _acc_to_stats("ALL",   all_acc)
    early_stats = _acc_to_stats("EARLY", early_acc)
    late_stats  = _acc_to_stats("LATE",  late_acc)

    log.info("-" * 80)
    log.info(
        "FBW MORNING MID — timing split analysis (%s to %s, WF split %s)",
        START, END, WALK_FORWARD_SPLIT,
    )
    log.info(
        "  Time bands: EARLY=%s-%s | LATE=%s-%s",
        ENTRY_TIME_START, SPLIT_TIME, SPLIT_TIME, ENTRY_TIME_END,
    )
    log.info("-" * 80)
    for stats in (all_stats, early_stats, late_stats):
        _print_band(stats)
    log.info("-" * 80)

    # ── Recommendation ────────────────────────────────────────────────────────
    early_pass = early_stats.gate_pass()
    late_pass  = late_stats.gate_pass()

    if early_pass and not late_pass:
        recommendation = "NARROW_TO_EARLY: Use 09:35-10:30 window only"
        window_advice = "narrow_to_early"
    elif late_pass and not early_pass:
        recommendation = "NARROW_TO_LATE: Use 10:30-11:30 window only"
        window_advice = "narrow_to_late"
    elif early_pass and late_pass:
        # Keep full window; pick whichever has higher WF ratio
        if early_stats.wf_ratio >= late_stats.wf_ratio:
            recommendation = "KEEP_FULL: Both bands pass. EARLY has stronger WF ratio — prefer 09:35-10:30 if capacity forces a choice."
        else:
            recommendation = "KEEP_FULL: Both bands pass. LATE has stronger WF ratio — prefer 10:30-11:30 if capacity forces a choice."
        window_advice = "keep_full"
    else:
        recommendation = "NEITHER_BAND_STANDALONE_PASS: Keep full window per existing validation; sub-bands lack power (low N)."
        window_advice = "keep_full_insufficient_subband_n"

    log.info("Recommendation: %s", recommendation)

    summary = {
        "analysis": "FBW MORNING MID — timing split",
        "date_range": {"start": START.isoformat(), "end": END.isoformat()},
        "walk_forward_split": WALK_FORWARD_SPLIT.isoformat(),
        "bands": {
            "early": f"{ENTRY_TIME_START.strftime('%H:%M')}-{SPLIT_TIME.strftime('%H:%M')} ET",
            "late":  f"{SPLIT_TIME.strftime('%H:%M')}-{ENTRY_TIME_END.strftime('%H:%M')} ET",
        },
        "params": {
            "qty": QTY,
            "strike_offset": STRIKE_OFFSET,
            "premium_stop_pct": PREMIUM_STOP_PCT,
            "chart_stop_below_support": CHART_STOP_BELOW_SUPPORT,
            "cooldown_minutes": COOLDOWN_MINUTES,
            "conf_band": f"[{CONF_MID_LOW},{CONF_MID_HIGH})",
        },
        "results": {
            "all":   all_stats.to_dict(),
            "early": early_stats.to_dict(),
            "late":  late_stats.to_dict(),
        },
        "n_no_data": no_data,
        "recommendation": recommendation,
        "window_advice": window_advice,
        "op21_gate_details": {
            "threshold_test_wr": ">=50%",
            "threshold_full_wr": ">=50%",
            "threshold_test_n":  ">=10",
            "threshold_test_pnl": ">0",
        },
        "per_trade_records": results,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    log.info("Output: %s", OUT_JSON)
    return summary


if __name__ == "__main__":
    scan_and_split()

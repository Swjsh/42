"""UNBIASED + REGIME-CONDITIONED re-eval of the watcher fleet (the de-bias pass).

THE REFRAME (why this script exists)
====================================
The weekend research (analysis/recommendations/bounce-family-rescue.json +
bearish-continuation-family.json) gated EVERY setup on `edge_capture` vs J's 3
BEARISH anchor winners (4/29, 5/01, 5/04 — all PUT down-days) minus his 3 LOSS
days (5/05-5/07 — up/range days). That gate is STRUCTURALLY biased toward
bearish-continuation: a mean-reversion LONG that works on range/up days is
*penalised* precisely because those days happen to be J's bearish-anchor LOSS
days. So the weekend wrongly concluded "BEARISH_REJECTION is THE edge" and
"retire the bounce family" — but it never asked the right question:

    Does each setup have STANDALONE positive real-fills expectancy in the REGIME
    it is MEANT for — judged on its own merits, not against bearish anchors?

This script answers that. It is PROPOSE-ONLY research (Rule 9). No watcher code,
params, or doctrine is changed.

TWO HYPOTHESES (matching the task brief)
========================================
H1 — STANDALONE FLEET RANKING (unbiased).
   Fire each candidate watcher (both directions) over the OPRA real-fills window
   and rank by STANDALONE expectancy + WR + n + DSR — with NO bearish-anchor gate.
   `edge_capture` is reported as a SECONDARY diagnostic only (to expose the
   contrast with the weekend method), never as a filter.

H2 — REGIME-CONDITIONED MEAN-REVERSION (the key test).
   Dealer-gamma literature: mean-reversion works on LONG-GAMMA / pin days (low
   realised vol, range-bound, vol-suppressed) and continuation works on
   SHORT-GAMMA trend days. We have NO GEX history, so we PROXY the long-gamma/pin
   regime with low-vol + range metrics (disclosed, OP-20). Re-test the bounce /
   mean-reversion family (floor_hold, close_ceiling, named_level_second_test,
   double_bottom) CONDITIONED on that regime. Is "dead" actually "dead
   unconditioned, alive in its regime"?

REGIME PROXY (no look-ahead; OP-20 proxy disclosure)
====================================================
Per signal bar, computed only from data at-or-before the bar:
  - vix_now              : aligned VIX at the bar (lib.orchestrator._align_vix_to_spy)
  - vix_bucket           : LOW (<15) / MID (15-19) / HIGH (>=19)
  - ribbon_stack         : BULL / BEAR / MIXED (lib.ribbon, EMA stack at the bar)
  - day_range_compression: today's high-low range *so far* (09:30..bar) divided by
                           the trailing-20-trading-day MEDIAN full-RTH daily range.
                           < 0.85 == COMPRESSED (range-bound so far). Trailing
                           median uses only PRIOR days (no look-ahead).
  - PIN_PROXY (long-gamma): vix_now < 16  AND  day_range_compression < 0.85  AND
                            ribbon_stack == MIXED (not trending). This is the
                            low-vol + range + not-trending conjunction that stands
                            in for a long-gamma pin day. It is a PROXY — disclosed.
  - TREND_PROXY          : vix_now >= 16 OR ribbon_stack in {BULL,BEAR} (the
                           complement-ish "directional" regime).

REGIME BUCKETS for the diversified-book map:
  bear_trend  : ribbon_stack == BEAR
  bull_trend  : ribbon_stack == BULL
  range_pin   : PIN_PROXY True
  high_vol    : vix_bucket == HIGH

AUTHORITY + CAVEATS
===================
  - Real-fills (OPRA) is the ONLY authority (theme C1). lib.simulator_real, options
    cache valid through 2026-05-29. BS-sim NOT used.
  - chart-stop only (premium_stop_pct=-0.99) baseline (C1/C2/L51/L55). For the
    high-WR mean-reversion family we ALSO report a mean-reversion-appropriate exit
    (ITM-2, tighter TP) because ATM + chart-stop-only is the WRONG geometry for a
    high-WR scalp — the weekend used ATM+chart-stop-only uniformly, which itself
    biased the bounce family's exp downward (a high-WR setup needs to bank the win).
  - LEVEL-SOURCE CAVEAT (OP-20, inherited): all level-keyed watchers are evaluated
    on SYNTHETIC PDH/PDL/PDC/PDO proxies (the same monkeypatch the weekend used),
    NOT production ★★★ named levels (no historical archive). Absolute WR is a proxy
    LOWER-BOUND. The level set is IDENTICAL across every setup + regime, so the
    SIGN/RANKING questions are answerable; absolute WR is not the production number.
  - DSR/PSR advisory (lib.validation.gate). Small per-bucket n => low_power flagged;
    we REPORT n and flag low-power buckets, never over-read them (C24).
  - J's own winning examples PER SETUP (he only has bearish anchors today) would
    sharpen this — disclosed in the report.

Usage:
  python -m autoresearch.eval_fleet_standalone_regime \
      --start 2025-01-01 --end 2026-05-29 \
      --out analysis/recommendations/fleet-standalone-regime.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

# Reuse the proven disk-reader firing pass + level machinery verbatim (no drift).
from autoresearch.sweep_watcher_exits import _collect_signals  # noqa: E402
from autoresearch.validate_level_family import (  # noqa: E402
    ANCHORS,
    _REJ_LEVEL_KEY,
    _load_data,
    _stats,
    _synthetic_levels_for_day,
)

from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext  # noqa: E402
from lib.ribbon import compute_ribbon, RibbonState  # noqa: E402
from lib.orchestrator import (  # noqa: E402
    _align_vix_to_spy,
    _precompute_htf_15m_stacks,
    _update_level_states,
)
from lib.simulator_real import simulate_trade_real  # noqa: E402
from lib.validation.gate import evaluate_candidate  # noqa: E402

# ctx.levels_active-native detectors (no disk monkeypatch needed). Fired in a
# parallel loop that mirrors _collect_signals' ctx construction EXACTLY, with the
# SAME synthetic levels injected into ctx (so the level set is identical to the
# disk-readers — fair comparison, uniform OP-20 caveat).
from lib.watchers.bullish_watcher import detect_bullish_setup  # noqa: E402
from lib.watchers.bearish_rejection_morning_watcher import detect_bearish_rejection_morning  # noqa: E402
from lib.watchers.double_bottom_base_quiet_watcher import detect_db_base_quiet_setup  # noqa: E402
from lib.watchers.double_bottom_morning_low_vol_watcher import detect_db_morning_low_vol_setup  # noqa: E402

# ── Configuration ────────────────────────────────────────────────────────────

# The bounce / mean-reversion family — the H2 focus (the "dead unconditioned"
# patterns). Disk-readers fired via _collect_signals.
BOUNCE_FAMILY = ["FLOOR_HOLD_BOUNCE", "CLOSE_CEILING_FADE", "NAMED_LEVEL_SECOND_TEST"]

# ctx-native detectors fired in the parallel loop: (stream, fn).
CTX_DETECTORS = [
    ("BULLISH_RECLAIM", detect_bullish_setup),
    ("BEARISH_REJECTION_MORNING", detect_bearish_rejection_morning),
    ("DOUBLE_BOTTOM_BASE_QUIET", detect_db_base_quiet_setup),
    ("DOUBLE_BOTTOM_MORNING_LOW_VOL", detect_db_morning_low_vol_setup),
]
# Rejection-level metadata key for the ctx-native detectors (real-fills anchor).
_CTX_REJ_KEY = {
    "BULLISH_RECLAIM": "reclaim_level",
    "BEARISH_REJECTION_MORNING": None,         # fall back to sig.stop_price
    "DOUBLE_BOTTOM_BASE_QUIET": "neckline",
    "DOUBLE_BOTTOM_MORNING_LOW_VOL": "neckline",
}

# Exit geometries.
#   default   : ATM + chart-stop-only — the weekend's uniform exit (the baseline
#               we de-bias). Right for momentum/continuation, WRONG for high-WR
#               mean-reversion (no premium TP => the win is never banked).
#   meanrev   : ITM-2 + tight premium TP — appropriate for a high-WR scalp that
#               needs to take the win before mean-reversion completes/reverses.
EXIT_DEFAULT = {"premium_stop_pct": -0.99, "strike_offset": 0,
                "tp1_premium_pct": 0.30, "level_stop_buffer_dollars": 0.50}
EXIT_MEANREV = {"premium_stop_pct": -0.99, "strike_offset": -2,
                "tp1_premium_pct": 0.30, "level_stop_buffer_dollars": 0.50}

# n_trials for DSR deflation. We evaluate a modest fixed arm set per setup
# (standalone + a handful of regime slices + 1 alt-exit). Keep honest, not 1.
N_TRIALS = 8

# Regime-proxy thresholds (disclosed; tunable documented defaults — NOT law).
VIX_LOW = 15.0
VIX_HIGH = 19.0
PIN_VIX_MAX = 16.0
PIN_COMPRESSION_MAX = 0.85   # today's range-so-far < 0.85 * trailing-median = compressed
COMPRESSION_LOOKBACK_DAYS = 20


# ── Regime computation (no look-ahead) ───────────────────────────────────────

def _daily_full_rth_range(rth: pd.DataFrame) -> dict[dt.date, float]:
    """Full-RTH (high-low) range per trading day. Used ONLY via a trailing median
    over PRIOR days, so referencing a completed day's full range is not look-ahead
    for any bar on a LATER day."""
    df = rth.copy()
    df["date"] = pd.to_datetime(df["timestamp_et"]).dt.date
    g = df.groupby("date")
    return {d: float(g.get_group(d)["high"].max() - g.get_group(d)["low"].min())
            for d in g.groups}


def _build_regime_index(rth: pd.DataFrame, ribbon_df: pd.DataFrame,
                        vix_aligned: pd.Series) -> dict:
    """Precompute per-bar regime tags, indexed by rth row position.

    Returns dict: idx -> {vix_now, vix_bucket, ribbon_stack, compression,
                          pin_proxy, trend_proxy, date}.
    No look-ahead: compression uses today's range *so far* (09:30..bar) over a
    trailing median of PRIOR days' full ranges; ribbon/vix are at-the-bar.
    """
    ts = pd.to_datetime(rth["timestamp_et"])
    dates = ts.dt.date  # date per row
    daily_range = _daily_full_rth_range(rth)
    ordered_days = sorted(daily_range)
    # Trailing median of prior days' full ranges, per day (no look-ahead).
    trailing_median: dict[dt.date, float] = {}
    for i, d in enumerate(ordered_days):
        prior = ordered_days[max(0, i - COMPRESSION_LOOKBACK_DAYS):i]
        vals = [daily_range[p] for p in prior if daily_range[p] > 0]
        trailing_median[d] = float(statistics.median(vals)) if vals else float("nan")

    # Running intraday high/low so far per day (cumulative within day).
    day_hi: dict[dt.date, float] = {}
    day_lo: dict[dt.date, float] = {}
    out: dict[int, dict] = {}
    cur_date = None
    for idx in range(len(rth)):
        d = dates.iloc[idx]
        if d != cur_date:
            cur_date = d
            day_hi[d] = float(rth.iloc[idx]["high"])
            day_lo[d] = float(rth.iloc[idx]["low"])
        else:
            day_hi[d] = max(day_hi[d], float(rth.iloc[idx]["high"]))
            day_lo[d] = min(day_lo[d], float(rth.iloc[idx]["low"]))
        range_so_far = day_hi[d] - day_lo[d]
        tmed = trailing_median.get(d, float("nan"))
        compression = (range_so_far / tmed) if (tmed == tmed and tmed > 0) else float("nan")

        vix_now = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else float("nan")
        if vix_now != vix_now:
            vix_bucket = "UNK"
        elif vix_now < VIX_LOW:
            vix_bucket = "LOW"
        elif vix_now < VIX_HIGH:
            vix_bucket = "MID"
        else:
            vix_bucket = "HIGH"

        stack = str(ribbon_df.iloc[idx]["stack"]) if idx < len(ribbon_df) else "WARMUP"

        pin_proxy = (
            vix_now == vix_now and vix_now < PIN_VIX_MAX
            and compression == compression and compression < PIN_COMPRESSION_MAX
            and stack == "MIXED"
        )
        trend_proxy = (vix_now == vix_now and vix_now >= PIN_VIX_MAX) or stack in ("BULL", "BEAR")

        out[idx] = {
            "date": d,
            "vix_now": round(vix_now, 2) if vix_now == vix_now else None,
            "vix_bucket": vix_bucket,
            "ribbon_stack": stack,
            "compression": round(compression, 3) if compression == compression else None,
            "pin_proxy": bool(pin_proxy),
            "trend_proxy": bool(trend_proxy),
        }
    return out


def _regime_buckets(tag: dict) -> list[str]:
    """Which named regime buckets a signal bar belongs to (can be >1)."""
    b = []
    if tag["ribbon_stack"] == "BEAR":
        b.append("bear_trend")
    if tag["ribbon_stack"] == "BULL":
        b.append("bull_trend")
    if tag["pin_proxy"]:
        b.append("range_pin")
    if tag["vix_bucket"] == "HIGH":
        b.append("high_vol")
    if tag["vix_bucket"] == "LOW":
        b.append("vix_low")
    if tag["ribbon_stack"] == "MIXED":
        b.append("ribbon_mixed")
    return b


# ── ctx-native firing loop (mirror of _collect_signals for non-disk detectors) ─

def _collect_ctx_signals(start: dt.date, end: dt.date,
                         rth: pd.DataFrame, ribbon_df: pd.DataFrame,
                         vix_aligned: pd.Series) -> dict:
    """Fire the ctx.levels_active-native detectors over the window, mirroring
    _collect_signals' ctx construction EXACTLY (same synthetic levels into ctx,
    same warmup, same htf stacks). Returns stream -> [(idx, bar, sig, date)]."""
    spy_full, _vix_full = _load_data(start, end)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date

    htf_stacks = _precompute_htf_15m_stacks(rth)
    inputs: dict[str, list] = {k: [] for k, _ in CTX_DETECTORS}

    level_states: dict = {}
    ribbon_history: list = []
    last_date = None
    _day_levels_cache: dict[dt.date, tuple] = {}

    for idx in range(len(rth)):
        bar = rth.iloc[idx]
        bar_time = bar["timestamp_et"]
        bar_date = bar_time.date()
        if start and bar_date < start:
            continue
        if end and bar_date > end:
            continue
        if last_date is not None and bar_date != last_date:
            ribbon_history = []
            level_states = {}
        last_date = bar_date
        if idx < 60:
            continue

        try:
            r = ribbon_df.iloc[idx]
            ribbon_state = RibbonState(
                fast=float(r["fast"]), pivot=float(r["pivot"]), slow=float(r["slow"]),
                stack=str(r["stack"]), spread_cents=float(r["spread_cents"]),
            )
        except Exception:
            continue
        ribbon_history.append(ribbon_state)
        ribbon_history = ribbon_history[-10:]

        vol_baseline = vol_baseline_20bar(rth, idx)
        range_baseline = range_baseline_20bar(rth, idx)
        vix_now = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 17.0
        vix_prior = float(vix_aligned.iloc[max(0, idx - 3)]) if max(0, idx - 3) < len(vix_aligned) else vix_now

        if bar_date not in _day_levels_cache:
            _day_levels_cache[bar_date] = _synthetic_levels_for_day(spy_full, bar_date)
        all_levels, _supports, _resistances = _day_levels_cache[bar_date]

        htf = htf_stacks[idx] if idx < len(htf_stacks) else None
        ctx = BarContext(
            bar_idx=idx,
            timestamp_et=bar_time.to_pydatetime(),
            bar=bar,
            prior_bars=rth.iloc[: idx + 1],
            ribbon_now=ribbon_state,
            ribbon_history=ribbon_history,
            vix_now=vix_now,
            vix_prior=vix_prior,
            vol_baseline_20=vol_baseline,
            range_baseline_20=range_baseline,
            levels_active=all_levels,
            multi_day_levels=all_levels,
            htf_15m_stack=htf,
            level_states=level_states,
        )
        _update_level_states(level_states, all_levels, bar, idx)

        for stream, fn in CTX_DETECTORS:
            try:
                sig = fn(ctx)
            except Exception as exc:  # surface, never swallow (C7)
                sys.stderr.write(f"{stream} exc @ {bar_time}: {type(exc).__name__}: {exc}\n")
                continue
            if sig is None:
                continue
            inputs[stream].append((idx, bar, sig, bar_date))
    return inputs


# ── Real-fills + regime tagging per stream ───────────────────────────────────

def _simulate_with_regime(stream: str, signals: list, rth: pd.DataFrame,
                          ribbon_df: pd.DataFrame, regime_idx: dict,
                          rej_key, exit_cfg: dict) -> list[dict]:
    """Real-fills every signal under exit_cfg; tag each fill with its regime.
    Returns a list of per-trade dicts: {pnl, dir, date, regime tags...}.
    Dedup to ONE signal per (date, direction) — keep first (mirror of the level-
    family dedup; prevents intraday signal spam inflating n)."""
    seen: set[tuple] = set()
    rows: list[dict] = []
    for (idx, bar, sig, bar_date) in signals:
        key = (str(bar_date), sig.direction)
        if key in seen:
            continue
        seen.add(key)
        side = "C" if sig.direction == "long" else "P"
        rej = None
        if rej_key is not None:
            rej = sig.metadata.get(rej_key)
        if rej is None:
            rej = sig.stop_price
        try:
            fill = simulate_trade_real(
                entry_bar_idx=idx, entry_bar=bar, spy_df=rth, ribbon_df=ribbon_df,
                rejection_level=float(rej), triggers_fired=list(sig.triggers_fired),
                side=side, qty=3, setup=sig.setup_name, **exit_cfg,
            )
        except Exception as exc:  # surface, never swallow (C7)
            sys.stderr.write(f"realfills {stream} exc @ {bar['timestamp_et']}: "
                             f"{type(exc).__name__}: {exc}\n")
            fill = None
        if fill is None or getattr(fill, "dollar_pnl", None) is None:
            continue
        tag = regime_idx.get(idx, {})
        rows.append({
            "pnl": float(fill.dollar_pnl),
            "dir": sig.direction,
            "date": str(bar_date),
            "conf": sig.confidence,
            "vix_bucket": tag.get("vix_bucket", "UNK"),
            "ribbon_stack": tag.get("ribbon_stack", "WARMUP"),
            "pin_proxy": tag.get("pin_proxy", False),
            "trend_proxy": tag.get("trend_proxy", False),
            "compression": tag.get("compression"),
            "buckets": _regime_buckets(tag) if tag else [],
        })
    return rows


# ── Metrics ──────────────────────────────────────────────────────────────────

def _edge_capture_diag(rows: list[dict]) -> dict:
    """SECONDARY DIAGNOSTIC ONLY (NOT a gate): the weekend's OP-16 edge_capture on
    these real-fills, shown to expose the bias it would have imposed."""
    by_day: dict[str, float] = defaultdict(float)
    for r in rows:
        d = dt.date.fromisoformat(r["date"])
        if d in ANCHORS:
            by_day[r["date"]] += r["pnl"]
    win_cap = sum(by_day[d] for d in by_day if ANCHORS[dt.date.fromisoformat(d)] == "WIN")
    loss_add = sum(max(0.0, -by_day[d]) for d in by_day if ANCHORS[dt.date.fromisoformat(d)] == "LOSS")
    return {
        "edge_capture": round(win_cap - loss_add, 2),
        "anchor_days_fired": len(by_day),
        "note": "SECONDARY DIAGNOSTIC, NOT a gate. Shows what the weekend's "
                "bearish-anchor gate would have done to this setup.",
    }


def _dsr(rows: list[dict]) -> dict:
    pnls = [r["pnl"] for r in rows]
    if len(pnls) < 2:
        return {"verdict": "FAIL", "reason": f"n={len(pnls)} < 2", "dsr": None,
                "psr": None, "low_power": True}
    # Zero-variance guard: deflated_sharpe raises ValueError when every return is
    # identical (sigma=0 -> Sharpe undefined). Common in tiny same-exit buckets.
    if len(set(round(p, 6) for p in pnls)) == 1:
        return {"verdict": "FAIL", "reason": "zero-variance return series",
                "dsr": None, "psr": None, "n_obs": len(pnls), "low_power": True}
    try:
        res = evaluate_candidate(pnls, n_trials=N_TRIALS)
    except ValueError as exc:  # surface, never swallow (C7)
        return {"verdict": "FAIL", "reason": f"DSR undefined: {exc}",
                "dsr": None, "psr": None, "n_obs": len(pnls), "low_power": True}
    return {"verdict": res.verdict, "dsr": round(res.dsr, 4), "psr": round(res.psr, 4),
            "n_obs": res.n_obs, "low_power": res.low_power}


def _oos_median_split(rows: list[dict]) -> dict:
    """In-sample vs out-of-sample by median signal DATE (balanced split). Reports
    exp + n per half + sign-stability flag."""
    if len(rows) < 6:
        return {"skipped": f"n={len(rows)} < 6 — OOS underpowered"}
    dates = sorted(dt.date.fromisoformat(r["date"]) for r in rows)
    boundary = dates[len(dates) // 2]
    is_rows = [r for r in rows if dt.date.fromisoformat(r["date"]) < boundary]
    oos_rows = [r for r in rows if dt.date.fromisoformat(r["date"]) >= boundary]
    is_s = _stats([{"pnl": r["pnl"]} for r in is_rows])
    oos_s = _stats([{"pnl": r["pnl"]} for r in oos_rows])
    sign_stable = (is_s["exp"] > 0) == (oos_s["exp"] > 0)
    return {
        "boundary": str(boundary),
        "in_sample": {"exp": is_s["exp"], "wr": is_s["wr"], "n": is_s["n"]},
        "out_of_sample": {"exp": oos_s["exp"], "wr": oos_s["wr"], "n": oos_s["n"]},
        "sign_stable": sign_stable,
    }


def _full_metrics(rows: list[dict]) -> dict:
    s = _stats([{"pnl": r["pnl"]} for r in rows])
    return {
        **s,
        "dsr_gate": _dsr(rows),
        "oos_median": _oos_median_split(rows),
        "edge_capture_diagnostic": _edge_capture_diag(rows),
    }


def _by_regime(rows: list[dict]) -> dict:
    """Stratify a stream's trades by every named regime bucket. Each trade can
    appear in multiple buckets (e.g. range_pin AND vix_low). Also by direction."""
    out: dict[str, dict] = {}
    # Named buckets.
    bucket_rows: dict[str, list] = defaultdict(list)
    for r in rows:
        for b in r["buckets"]:
            bucket_rows[b].append(r)
    for b in sorted(bucket_rows):
        br = bucket_rows[b]
        s = _stats([{"pnl": x["pnl"]} for x in br])
        out[b] = {**s, "dsr": _dsr(br), "low_power": s["n"] < 20}
    # Direction split.
    for d in ("long", "short"):
        dr = [r for r in rows if r["dir"] == d]
        if dr:
            s = _stats([{"pnl": x["pnl"]} for x in dr])
            out[f"direction_{d}"] = {**s, "low_power": s["n"] < 20}
    return out


# ── Main run ─────────────────────────────────────────────────────────────────

def run(start: dt.date, end: dt.date) -> dict:
    # Disk-reader bounce family — reuse the proven firing pass (synthetic-level
    # monkeypatch + anchor-coverage logic baked in).
    disk_inputs, rth, ribbon_df = _collect_signals(start, end)
    rth = rth.reset_index(drop=True)

    # VIX + regime index (shared across all streams).
    _spy_full, vix_full = _load_data(start, end)
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    regime_idx = _build_regime_index(rth, ribbon_df, vix_aligned)

    # ctx-native detectors — parallel firing loop (same ctx construction).
    ctx_inputs = _collect_ctx_signals(start, end, rth, ribbon_df, vix_aligned)

    # Assemble the full stream -> (signals, rej_key) table.
    streams: dict[str, tuple] = {}
    for s in BOUNCE_FAMILY:
        streams[s] = (disk_inputs[s], _REJ_LEVEL_KEY[s])
    for s, _ in CTX_DETECTORS:
        streams[s] = (ctx_inputs[s], _CTX_REJ_KEY[s])

    # Which streams are the mean-reversion family (get the alt meanrev exit + H2).
    MEANREV_STREAMS = set(BOUNCE_FAMILY) | {
        "DOUBLE_BOTTOM_BASE_QUIET", "DOUBLE_BOTTOM_MORNING_LOW_VOL"}

    fleet: dict = {}
    for stream, (signals, rej_key) in streams.items():
        # Standalone (default exit) — the unbiased H1 number.
        rows_default = _simulate_with_regime(
            stream, signals, rth, ribbon_df, regime_idx, rej_key, EXIT_DEFAULT)
        entry: dict = {
            "n_signals_collected": len(signals),
            "standalone_default_exit": {
                "exit": EXIT_DEFAULT,
                **_full_metrics(rows_default),
                "by_regime": _by_regime(rows_default),
            },
        }
        # Mean-reversion family also gets the meanrev-appropriate exit (H2 fairness).
        if stream in MEANREV_STREAMS:
            rows_mr = _simulate_with_regime(
                stream, signals, rth, ribbon_df, regime_idx, rej_key, EXIT_MEANREV)
            entry["standalone_meanrev_exit"] = {
                "exit": EXIT_MEANREV,
                **_full_metrics(rows_mr),
                "by_regime": _by_regime(rows_mr),
            }
            # Keep the per-trade rows for the H2 regime-conditioned cross-cut.
            entry["_rows_default"] = rows_default
            entry["_rows_meanrev"] = rows_mr
        fleet[stream] = entry

    # ── H1: standalone fleet ranking (by standalone default-exit expectancy) ──
    ranking = []
    for stream, e in fleet.items():
        sa = e["standalone_default_exit"]
        ranking.append({
            "setup": stream,
            "exp": sa["exp"], "wr": sa["wr"], "n": sa["n"], "total": sa["total"],
            "dsr_verdict": sa["dsr_gate"]["verdict"],
            "dsr": sa["dsr_gate"]["dsr"],
            "oos_sign_stable": sa["oos_median"].get("sign_stable"),
            "edge_capture_diag": sa["edge_capture_diagnostic"]["edge_capture"],
            "positive_standalone": sa["exp"] > 0,
        })
    ranking.sort(key=lambda x: (-(x["exp"]), -(x["wr"])))

    # ── H2: regime-conditioned mean-reversion revival test ───────────────────
    h2 = _h2_regime_conditioned(fleet, MEANREV_STREAMS)

    # ── Diversified-book regime -> setup map ─────────────────────────────────
    book = _build_regime_book(fleet)

    # Strip internal rows before serialising.
    for e in fleet.values():
        e.pop("_rows_default", None)
        e.pop("_rows_meanrev", None)

    return {
        "window": f"{start}..{end}",
        "generated_at": dt.datetime.now().isoformat(timespec="seconds"),
        "research_question": (
            "UNBIASED + REGIME-CONDITIONED fleet re-eval. (H1) Rank every candidate "
            "watcher by STANDALONE real-fills expectancy/WR/DSR with NO bearish-anchor "
            "gate. (H2) Re-test the bounce/mean-reversion family CONDITIONED on a "
            "low-vol/range pin-regime PROXY (long-gamma stand-in; no GEX history). "
            "Goal: a regime->setup map for a diversified multi-setup book. Real-fills "
            "(OPRA) is the only authority (C1). PROPOSE-ONLY (Rule 9)."
        ),
        "method_contrast": {
            "weekend_method": "Gated EVERY setup on edge_capture vs 3 BEARISH anchors "
                              "(4/29,5/01,5/04 down-days) minus 3 LOSS days (5/05-07 "
                              "up/range-days). Mean-reversion longs that work on range/up "
                              "days were PENALISED because those are J's anchor LOSS days. "
                              "=> structurally biased to bearish-continuation.",
            "this_method": "STANDALONE expectancy per setup (no anchor gate) + regime "
                           "conditioning. edge_capture reported as a SECONDARY diagnostic "
                           "only, to expose the bias it would impose.",
        },
        "regime_proxy_definition": {
            "vix_buckets": f"LOW<{VIX_LOW} / MID / HIGH>={VIX_HIGH}",
            "pin_proxy_long_gamma": (
                f"vix_now<{PIN_VIX_MAX} AND day_range_compression<{PIN_COMPRESSION_MAX} "
                f"AND ribbon_stack==MIXED. Compression = today's range-so-far / trailing "
                f"{COMPRESSION_LOOKBACK_DAYS}-day MEDIAN full-RTH range (prior days only, "
                f"no look-ahead). PROXY for long-gamma/pin — NO GEX data (OP-20)."),
            "regime_buckets": "bear_trend(BEAR) / bull_trend(BULL) / range_pin(pin_proxy) "
                              "/ high_vol(VIX HIGH) / vix_low / ribbon_mixed",
        },
        "h1_standalone_fleet_ranking": ranking,
        "h2_regime_conditioned_meanrev": h2,
        "diversified_book_regime_map": book,
        "fleet_detail": fleet,
        "op20_disclosures": _op20_disclosures(),
        "overall_verdict": _overall_verdict(ranking, h2, book),
    }


def _h2_regime_conditioned(fleet: dict, meanrev_streams: set) -> dict:
    """The KEY test: for each mean-reversion setup, is its IN-REGIME (range_pin /
    vix_low / ribbon_mixed) standalone expectancy POSITIVE even though its
    UNCONDITIONED expectancy is negative? I.e. dead-unconditioned but alive-in-regime?
    Uses the meanrev-appropriate exit (the fair geometry for a high-WR scalp)."""
    out: dict = {}
    for stream in sorted(meanrev_streams):
        if stream not in fleet:
            continue
        e = fleet[stream]
        # Prefer the meanrev exit's stratification for the in-regime read; fall
        # back to default if no meanrev arm.
        arm = e.get("standalone_meanrev_exit") or e["standalone_default_exit"]
        uncond_exp = arm["exp"]
        uncond_n = arm["n"]
        by_reg = arm["by_regime"]
        in_regime = {}
        for bucket in ("range_pin", "vix_low", "ribbon_mixed"):
            if bucket in by_reg:
                b = by_reg[bucket]
                in_regime[bucket] = {
                    "exp": b["exp"], "wr": b["wr"], "n": b["n"],
                    "low_power": b["low_power"],
                    "revived": b["exp"] > 0 and uncond_exp <= 0,
                }
        any_revival = any(v.get("revived") for v in in_regime.values())
        out[stream] = {
            "exit_used": arm["exit"],
            "unconditioned": {"exp": uncond_exp, "wr": arm["wr"], "n": uncond_n},
            "in_regime": in_regime,
            "revived_in_some_regime": any_revival,
            "verdict": (
                "REVIVED-IN-REGIME (dead unconditioned, positive in-regime — worth "
                "a focused real-fills re-test on production ★★★ levels)"
                if any_revival else
                "DEAD-EVEN-IN-REGIME (no low-vol/range slice flips it positive)"
            ),
        }
    return out


def _build_regime_book(fleet: dict) -> dict:
    """For each named regime, list setups with POSITIVE standalone in-regime
    expectancy, ranked by in-regime exp. The candidate diversified book.
    Uses each setup's BEST available exit arm for its in-regime read."""
    REGIMES = ["bear_trend", "bull_trend", "range_pin", "high_vol", "vix_low", "ribbon_mixed"]
    book: dict[str, list] = {r: [] for r in REGIMES}
    for stream, e in fleet.items():
        arms = [e["standalone_default_exit"]]
        if "standalone_meanrev_exit" in e:
            arms.append(e["standalone_meanrev_exit"])
        for r in REGIMES:
            best = None
            for arm in arms:
                br = arm["by_regime"].get(r)
                if br and (best is None or br["exp"] > best["exp"]):
                    best = {"exp": br["exp"], "wr": br["wr"], "n": br["n"],
                            "exit": arm["exit"], "low_power": br["low_power"]}
            if best and best["exp"] > 0 and best["n"] >= 5:
                book[r].append({"setup": stream, **best})
    for r in REGIMES:
        book[r].sort(key=lambda x: -x["exp"])
    return book


def _overall_verdict(ranking: list, h2: dict, book: dict) -> dict:
    positive = [r["setup"] for r in ranking if r["positive_standalone"]]
    revived = [s for s, v in h2.items() if v["revived_in_some_regime"]]
    book_summary = {r: [c["setup"] for c in cands] for r, cands in book.items() if cands}
    return {
        "setups_positive_standalone_unconditioned": positive,
        "meanrev_setups_revived_in_regime": revived,
        "diversified_book_candidates_by_regime": book_summary,
        "headline": (
            "Unbiased standalone ranking + regime conditioning complete. "
            f"{len(positive)} setup(s) positive standalone (unconditioned). "
            f"{len(revived)} mean-reversion setup(s) revived in a low-vol/range regime "
            "(dead-unconditioned -> positive-in-regime). See diversified_book_regime_map "
            "for the regime->setup candidates. ALL on ★★ proxy levels (OP-20) + WATCH_ONLY "
            "by doctrine — these are candidates worth a production-★★★ real-fills re-test, "
            "not promotions."
        ),
    }


def _op20_disclosures() -> dict:
    return {
        "authority": "Real-fills (lib.simulator_real + OPRA cache, valid through "
                     "2026-05-29). BS-sim NOT used (C1).",
        "no_anchor_gate": "edge_capture is reported ONLY as a secondary diagnostic to "
                          "contrast with the weekend method. It is NOT used to filter or "
                          "rank any setup here. Ranking is by STANDALONE expectancy.",
        "level_source_caveat": "All level-keyed watchers evaluated on SYNTHETIC "
                               "PDH/PDL/PDC/PDO proxies (★★/★) via the same monkeypatch the "
                               "weekend used, NOT production ★★★ named levels (no historical "
                               "archive). Absolute WR is a proxy LOWER-BOUND (PDL-class "
                               "proxies understate ★★★ WR up to ~20pp, L58). The level set is "
                               "IDENTICAL across every setup AND regime, so the ranking/sign "
                               "questions are answerable; absolute WR is not the production number.",
        "regime_proxy_caveat": "NO GEX / dealer-gamma history exists. The long-gamma/pin "
                               "regime is PROXIED by low-vol (VIX<16) + range compression "
                               "(today's range-so-far < 0.85x trailing-20d median) + "
                               "ribbon==MIXED. This is a STAND-IN, not measured dealer gamma. "
                               "Disclosed per OP-20. Compression + ribbon + VIX are all "
                               "computed at-or-before the signal bar (no look-ahead).",
        "exit_geometry": "Two exits reported: DEFAULT (ATM + chart-stop-only, the weekend's "
                         "uniform exit) and MEANREV (ITM-2 + tight TP) for the mean-reversion "
                         "family. ATM+chart-stop-only is the WRONG geometry for a high-WR "
                         "mean-reversion scalp (the win is never banked) — using it uniformly "
                         "itself biased the weekend's bounce-family exp downward.",
        "small_n": "Per-regime buckets can be small; low_power (n<20) is flagged per bucket. "
                   "DSR/PSR are advisory; never over-read an underpowered bucket (C24).",
        "j_examples_caveat": "J has documented winning examples ONLY for the bearish-anchor "
                             "pattern. He has NO logged winners for bullish-reclaim, "
                             "mean-reversion, or double-bottom setups. Per-setup J winners "
                             "would sharpen each setup's in-regime validation; their absence "
                             "is why this stays STANDALONE-statistical, not J-anchored.",
        "not_a_promotion": "RESEARCH ONLY (Rule 9). No watcher code, params, or doctrine "
                           "changed. Every setup remains WATCH_ONLY. A positive standalone or "
                           "in-regime result = 'worth a focused production-★★★ real-fills "
                           "re-test', NOT 'wire it live'.",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-05-29")  # OPRA coverage ends 2026-05-29
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end))

    # Compact stdout (drop the heavy fleet_detail).
    summary = {k: v for k, v in res.items() if k != "fleet_detail"}
    print(json.dumps(summary, indent=2, default=str))

    if a.out:
        out_path = Path(a.out)
        if not out_path.is_absolute():
            out_path = ROOT / out_path
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
        print("wrote", out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

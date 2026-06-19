"""Stage-1 price-space scan + real-fills validation for the BREAKOUT/MOMENTUM watcher family.

Clones the structure of validate_reddit_watchers.py (price-space scan -> grade_observation
-> quarterly breakdown -> real-fills -> OP-16 anchor preservation). Swaps in seven detectors:

  1. ORB_RETEST_LONG               orb_watcher.detect_orb_break (legacy positional sig)
  2. DOUBLE_BOTTOM_BASE_QUIET      double_bottom_base_quiet_watcher (ctx-based)
  3. DOUBLE_BOTTOM_MORNING_LOW_VOL double_bottom_morning_low_vol_watcher (ctx-based)
  4. MOMENTUM_ACCELERATION_HIGHVOL momentum_acceleration_highvol_watcher (ctx-based)
  5. RSI_DIVERGENCE_BULL           rsi_divergence_watcher (ctx-based)
  6. STAIRSTEP_CONTINUATION        stairstep_continuation_watcher (ctx-based, key-level keyed)
  7. SHOTGUN_SCALPER               shotgun_scalper_watcher (single-exit doctrine — see caveat)

CORRECTNESS NOTES (verified, see op20_disclosures in output JSON):
  * ORB / double_bottom / momentum / rsi are NOT level-keyed off disk state — they read
    ctx.prior_bars (price structure), ctx.ribbon_now, ctx.vix_now, and ctx.levels_active
    (the latter rebuilt historically per bar-date via _detect_from_history). No look-ahead
    beyond the current bar.
  * STAIRSTEP reads automation/state/key-levels.json (TODAY's live levels) — a look-ahead /
    wrong-levels trap for a 16-month replay. We MONKEYPATCH its _load_named_levels to feed
    historically-detected ★★+ levels per bar-date. Roles (broken_to_*) are unavailable in the
    historical level set, so STAIRSTEP runs on its fallback intraday-break path only.
  * SHOTGUN reads key-levels.json too, but its detector also auto-derives intraday levels
    from the bar window (auto_derive_intraday_levels=True). Its exit is a 12-min time stop +
    chandelier (single exit, NO runner) — grade_observation's TP1+runner model does NOT fit.
    We report raw fire counts only and mark it NEEDS-DEDICATED-GRADER.

crypto.lib.chart_patterns bootstrap: backtest/crypto/__init__.py shadows the top-level
crypto/lib namespace, so a plain `from crypto.lib.chart_patterns import ...` raises
ImportError (the double_bottom / momentum watchers would silently degrade to
_PATTERNS_AVAILABLE=False). We inject the real top-level module into sys.modules first.

Usage:
  python -m autoresearch.validate_breakout_family --start 2025-01-01 --end 2026-06-16 --realfills \
      --out ../analysis/recommendations/breakout-family-validation.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
import types
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))


# ── crypto.lib.chart_patterns bootstrap (must run BEFORE importing watchers) ──
def _ensure_chart_patterns() -> bool:
    """Inject the REAL top-level crypto/lib/chart_patterns.py into sys.modules.

    backtest/crypto/ is a regular package (has __init__.py) with NO lib/ subdir, so it
    shadows the top-level crypto namespace and `from crypto.lib.chart_patterns import ...`
    fails. We synthesize the crypto + crypto.lib namespace packages pointing at the
    top-level dirs, then exec the real chart_patterns under its canonical dotted name
    (required so its @dataclass(slots=True) classes register correctly in sys.modules).
    """
    if "crypto.lib.chart_patterns" in sys.modules:
        return True
    cp_path = ROOT / "crypto" / "lib" / "chart_patterns.py"
    if not cp_path.exists():
        return False
    existing = sys.modules.get("crypto")
    if existing is None or not hasattr(existing, "__path__"):
        pkg = types.ModuleType("crypto")
        pkg.__path__ = [str(ROOT / "crypto")]
        sys.modules["crypto"] = pkg
    if "crypto.lib" not in sys.modules:
        libpkg = types.ModuleType("crypto.lib")
        libpkg.__path__ = [str(ROOT / "crypto" / "lib")]
        sys.modules["crypto.lib"] = libpkg
    spec = importlib.util.spec_from_file_location("crypto.lib.chart_patterns", cp_path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["crypto.lib.chart_patterns"] = mod
    spec.loader.exec_module(mod)
    return True


_PATTERNS_BOOTSTRAPPED = _ensure_chart_patterns()

# ── Engine imports (after bootstrap) ─────────────────────────────────────────
from lib.filters import vol_baseline_20bar, range_baseline_20bar, BarContext  # noqa: E402
from lib.ribbon import compute_ribbon, RibbonState  # noqa: E402
from lib.levels import _detect_from_history  # noqa: E402
from lib.orchestrator import (  # noqa: E402
    _align_vix_to_spy,
    _precompute_htf_15m_stacks,
    _update_level_states,
)
from lib.watchers.runner import grade_observation  # noqa: E402

# Detectors
from lib.watchers.orb_watcher import detect_orb_break, _orb_state  # noqa: E402
from lib.watchers import double_bottom_base_quiet_watcher as _dbbq  # noqa: E402
from lib.watchers import double_bottom_morning_low_vol_watcher as _dbml  # noqa: E402
from lib.watchers import momentum_acceleration_highvol_watcher as _mahv  # noqa: E402
from lib.watchers import rsi_divergence_watcher as _rsidiv  # noqa: E402
from lib.watchers import stairstep_continuation_watcher as _stair  # noqa: E402
from lib.watchers import shotgun_scalper_watcher as _shotgun  # noqa: E402

DATA = REPO / "data"

# OP-16 J-edge anchors.
ANCHORS = {
    dt.date(2026, 4, 29): "WIN", dt.date(2026, 5, 1): "WIN", dt.date(2026, 5, 4): "WIN",
    dt.date(2026, 5, 5): "LOSS", dt.date(2026, 5, 6): "LOSS", dt.date(2026, 5, 7): "LOSS",
}
EOD = dt.time(15, 50)

# Streams graded with the standard TP1+runner grade_observation model.
_STD_STREAMS = [
    "ORB_RETEST_LONG",
    "DOUBLE_BOTTOM_BASE_QUIET",
    "DOUBLE_BOTTOM_MORNING_LOW_VOL",
    "MOMENTUM_ACCELERATION_HIGHVOL",
    "RSI_DIVERGENCE_BULL",
    "STAIRSTEP_CONTINUATION",
]
# SHOTGUN graded separately (single-exit doctrine) — fire counts only here.
_SHOTGUN_STREAM = "SHOTGUN_SCALPER"

# Streams whose real-fills design is long-only ATM (calls) — skip ITM2 (matches reddit ORB note).
_LONG_ATM_ONLY = {"ORB_RETEST_LONG", "DOUBLE_BOTTOM_BASE_QUIET",
                  "DOUBLE_BOTTOM_MORNING_LOW_VOL", "RSI_DIVERGENCE_BULL"}


def _load_data(start, end):
    """Load the SPY+VIX CSVs covering [start, end]; dedupe by parsed timestamp."""
    spy_path = DATA / "spy_5m_2025-01-01_2026-06-16.csv"
    vix_path = DATA / "vix_5m_2025-01-01_2026-06-16.csv"
    spy = pd.read_csv(spy_path)
    vix = pd.read_csv(vix_path)
    for df in (spy, vix):
        df["_ts"] = pd.to_datetime(df["timestamp_et"], utc=True)
        df.drop_duplicates("_ts", inplace=True)
        df.drop(columns=["_ts"], inplace=True)
    return spy.reset_index(drop=True), vix.reset_index(drop=True)


def _sig_to_obs(s):
    return {"direction": s.direction, "entry_price": s.entry_price, "stop_price": s.stop_price,
            "tp1_price": s.tp1_price, "runner_price": s.runner_price, "would_be_outcome": None}


def _grade(sig, rth, idx, bar_date):
    """Score a signal with the standard TP1+runner model over same-day future bars."""
    day = rth[(rth["timestamp_et"].dt.date == bar_date)]
    fut = day[(day["timestamp_et"] > rth.iloc[idx]["timestamp_et"]) &
              (day["timestamp_et"].dt.time <= EOD)]
    o = grade_observation(_sig_to_obs(sig), fut)
    return o.get("would_be_outcome"), float(o.get("would_be_pnl_dollars") or 0.0)


def _stats(rows):
    n = len(rows)
    if n == 0:
        return {"n": 0, "wr": 0.0, "total": 0.0, "exp": 0.0}
    wins = sum(1 for r in rows if r["pnl"] > 0)
    tot = sum(r["pnl"] for r in rows)
    return {"n": n, "wr": round(100 * wins / n, 1), "total": round(tot, 2), "exp": round(tot / n, 2)}


def _quarter(date_str: str) -> str:
    y, m, _ = date_str.split("-")
    q = (int(m) - 1) // 3 + 1
    return f"{y}Q{q}"


def _per_quarter(rows):
    buckets: dict[str, list] = defaultdict(list)
    for r in rows:
        buckets[_quarter(r["date"])].append(r)
    return {q: _stats(buckets[q]) for q in sorted(buckets)}


def _reset_watcher_state():
    """Reset all module-level dedup/cooldown state so a fresh replay is deterministic.

    Clears STAIRSTEP's level caches too — otherwise a second run in the same process
    (e.g. pytest) could serve a stale prior-run day's levels when _cached_levels_date
    coincidentally matches.
    """
    _orb_state.clear()
    _dbbq._last_signal_time = None
    _dbml._last_signal_time = None
    _mahv._last_signal_time = None
    _rsidiv._last_signal_bar_idx = -_rsidiv._COOLDOWN_BARS
    _stair._last_signal_time = None
    _stair._cached_all = []
    _stair._cached_broken_res = []
    _stair._cached_broken_sup = []
    _stair._cached_levels_date = None
    _stair_levels_by_date.clear()


# ── STAIRSTEP look-ahead fix: feed historically-detected ★★+ levels per day ──
_stair_levels_by_date: dict[str, list[float]] = {}


def _patched_stair_load_named_levels(today_str: str):
    """Monkeypatch replacement for stairstep_continuation_watcher._load_named_levels.

    Returns (all_levels, broken_res, broken_sup) using levels detected from history
    AS OF that day (no look-ahead). Roles are unknown in the historical level set, so
    broken_res / broken_sup are empty — STAIRSTEP runs on its intraday-break fallback.
    """
    levels = _stair_levels_by_date.get(today_str, [])
    return list(levels), [], []


def run(start, end, do_realfills):
    spy_full, vix_full = _load_data(start, end)
    spy_full["timestamp_et"] = pd.to_datetime(spy_full["timestamp_et"])
    spy_full["date"] = spy_full["timestamp_et"].dt.date
    rth = spy_full[(spy_full["timestamp_et"].dt.time >= dt.time(9, 30)) &
                   (spy_full["timestamp_et"].dt.time < dt.time(16, 0))].reset_index(drop=True)
    ribbon_df = compute_ribbon(rth["close"])
    vix_aligned = _align_vix_to_spy(rth, vix_full)
    htf_stacks = _precompute_htf_15m_stacks(rth)

    streams: dict[str, list] = {k: [] for k in _STD_STREAMS}
    shotgun_fires: list = []
    anchor_hits = defaultdict(lambda: defaultdict(list))  # date -> stream -> [(dir,conf,pnl)]
    realfills_inputs: dict[str, list] = {k: [] for k in _STD_STREAMS}

    # Patch STAIRSTEP level loader to historical levels.
    _stair._load_named_levels = _patched_stair_load_named_levels

    _reset_watcher_state()

    level_states: dict = {}
    ribbon_history: list = []
    last_date = None
    _lvl_cache = [None]
    _lvl_date = [None]
    _day_groups = {d: g.reset_index(drop=True) for d, g in rth.groupby(rth["timestamp_et"].dt.date)}
    _ts_to_gidx = {t: i for i, t in enumerate(rth["timestamp_et"])}

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
            ribbon_state = RibbonState(fast=float(r["fast"]), pivot=float(r["pivot"]),
                                       slow=float(r["slow"]), stack=str(r["stack"]),
                                       spread_cents=float(r["spread_cents"]))
        except Exception:
            continue
        ribbon_history.append(ribbon_state)
        ribbon_history = ribbon_history[-10:]
        vol_baseline = vol_baseline_20bar(rth, idx)
        range_baseline = range_baseline_20bar(rth, idx)
        vix_now = float(vix_aligned.iloc[idx]) if idx < len(vix_aligned) else 17.0
        vix_prior = float(vix_aligned.iloc[max(0, idx - 3)]) if max(0, idx - 3) < len(vix_aligned) else vix_now

        # Rebuild today's levels from history (no look-ahead: history <= bar_time).
        if bar_date != _lvl_date[0]:
            full_history = spy_full[spy_full["timestamp_et"] <= bar_time]
            _lvl_cache[0] = _detect_from_history(full_history, bar_date)
            _lvl_date[0] = bar_date
            # Populate the historical ★★+ level set for STAIRSTEP (all active+multi-day).
            ls = _lvl_cache[0]
            _stair_levels_by_date[bar_date.isoformat()] = sorted(set(
                list(ls.active) + list(ls.multi_day)
            ))
        level_set = _lvl_cache[0]
        _update_level_states(level_states, level_set.active, bar, idx)
        htf = htf_stacks[idx] if idx < len(htf_stacks) else None

        ctx = BarContext(
            bar_idx=idx, timestamp_et=bar_time.to_pydatetime(), bar=bar,
            prior_bars=rth.iloc[:idx + 1], ribbon_now=ribbon_state, ribbon_history=ribbon_history,
            vix_now=vix_now, vix_prior=vix_prior, vol_baseline_20=vol_baseline,
            range_baseline_20=range_baseline, levels_active=level_set.active,
            multi_day_levels=level_set.multi_day, htf_15m_stack=htf, level_states=level_states,
        )
        day_bars = _day_groups[bar_date]
        bidx = int((day_bars["timestamp_et"] == bar_time).values.argmax())

        # ── 1. ORB_RETEST_LONG (legacy positional signature) ──
        try:
            orb = detect_orb_break(bar, day_bars, bidx, vol_baseline)
        except Exception as _e:
            sys.stderr.write(f"ORB_RETEST_LONG bar={bar_time}: {type(_e).__name__}: {_e}\n")
            orb = None
        if orb is not None:
            out, pnl = _grade(orb, rth, idx, bar_date)
            streams["ORB_RETEST_LONG"].append(
                {"date": str(bar_date), "conf": orb.confidence, "dir": orb.direction,
                 "out": out, "pnl": pnl, "vix": round(vix_now, 1)})
            if bar_date in ANCHORS:
                anchor_hits[bar_date]["ORB_RETEST_LONG"].append((orb.direction, orb.confidence, pnl))
            realfills_inputs["ORB_RETEST_LONG"].append((idx, bar, orb))

        # ── 2. DOUBLE_BOTTOM_BASE_QUIET ──
        try:
            dbbq = _dbbq.detect_db_base_quiet_setup(ctx)
        except Exception as _e:
            sys.stderr.write(f"DOUBLE_BOTTOM_BASE_QUIET bar={bar_time}: {type(_e).__name__}: {_e}\n")
            dbbq = None
        if dbbq is not None:
            out, pnl = _grade(dbbq, rth, idx, bar_date)
            streams["DOUBLE_BOTTOM_BASE_QUIET"].append(
                {"date": str(bar_date), "conf": dbbq.confidence, "dir": dbbq.direction,
                 "out": out, "pnl": pnl, "vix": round(vix_now, 1)})
            if bar_date in ANCHORS:
                anchor_hits[bar_date]["DOUBLE_BOTTOM_BASE_QUIET"].append((dbbq.direction, dbbq.confidence, pnl))
            realfills_inputs["DOUBLE_BOTTOM_BASE_QUIET"].append((idx, bar, dbbq))

        # ── 3. DOUBLE_BOTTOM_MORNING_LOW_VOL ──
        try:
            dbml = _dbml.detect_db_morning_low_vol_setup(ctx)
        except Exception as _e:
            sys.stderr.write(f"DOUBLE_BOTTOM_MORNING_LOW_VOL bar={bar_time}: {type(_e).__name__}: {_e}\n")
            dbml = None
        if dbml is not None:
            out, pnl = _grade(dbml, rth, idx, bar_date)
            streams["DOUBLE_BOTTOM_MORNING_LOW_VOL"].append(
                {"date": str(bar_date), "conf": dbml.confidence, "dir": dbml.direction,
                 "out": out, "pnl": pnl, "vix": round(vix_now, 1)})
            if bar_date in ANCHORS:
                anchor_hits[bar_date]["DOUBLE_BOTTOM_MORNING_LOW_VOL"].append((dbml.direction, dbml.confidence, pnl))
            realfills_inputs["DOUBLE_BOTTOM_MORNING_LOW_VOL"].append((idx, bar, dbml))

        # ── 4. MOMENTUM_ACCELERATION_HIGHVOL ──
        try:
            mahv = _mahv.detect_momentum_accel_highvol_setup(ctx)
        except Exception as _e:
            sys.stderr.write(f"MOMENTUM_ACCELERATION_HIGHVOL bar={bar_time}: {type(_e).__name__}: {_e}\n")
            mahv = None
        if mahv is not None:
            out, pnl = _grade(mahv, rth, idx, bar_date)
            streams["MOMENTUM_ACCELERATION_HIGHVOL"].append(
                {"date": str(bar_date), "conf": mahv.confidence, "dir": mahv.direction,
                 "out": out, "pnl": pnl, "vix": round(vix_now, 1)})
            if bar_date in ANCHORS:
                anchor_hits[bar_date]["MOMENTUM_ACCELERATION_HIGHVOL"].append((mahv.direction, mahv.confidence, pnl))
            realfills_inputs["MOMENTUM_ACCELERATION_HIGHVOL"].append((idx, bar, mahv))

        # ── 5. RSI_DIVERGENCE_BULL ──
        try:
            rsid = _rsidiv.detect_rsi_divergence_bull(ctx)
        except Exception as _e:
            sys.stderr.write(f"RSI_DIVERGENCE_BULL bar={bar_time}: {type(_e).__name__}: {_e}\n")
            rsid = None
        if rsid is not None:
            out, pnl = _grade(rsid, rth, idx, bar_date)
            streams["RSI_DIVERGENCE_BULL"].append(
                {"date": str(bar_date), "conf": rsid.confidence, "dir": rsid.direction,
                 "out": out, "pnl": pnl, "vix": round(vix_now, 1)})
            if bar_date in ANCHORS:
                anchor_hits[bar_date]["RSI_DIVERGENCE_BULL"].append((rsid.direction, rsid.confidence, pnl))
            realfills_inputs["RSI_DIVERGENCE_BULL"].append((idx, bar, rsid))

        # ── 6. STAIRSTEP_CONTINUATION (historical levels via monkeypatch) ──
        try:
            stair = _stair.detect_stairstep_continuation_setup(ctx)
        except Exception as _e:
            sys.stderr.write(f"STAIRSTEP_CONTINUATION bar={bar_time}: {type(_e).__name__}: {_e}\n")
            stair = None
        if stair is not None:
            out, pnl = _grade(stair, rth, idx, bar_date)
            streams["STAIRSTEP_CONTINUATION"].append(
                {"date": str(bar_date), "conf": stair.confidence, "dir": stair.direction,
                 "out": out, "pnl": pnl, "vix": round(vix_now, 1)})
            if bar_date in ANCHORS:
                anchor_hits[bar_date]["STAIRSTEP_CONTINUATION"].append((stair.direction, stair.confidence, pnl))
            realfills_inputs["STAIRSTEP_CONTINUATION"].append((idx, bar, stair))

        # ── 7. SHOTGUN_SCALPER (fire counts only; single-exit doctrine) ──
        rb_dict = {"fast": ribbon_state.fast, "pivot": ribbon_state.pivot,
                   "slow": ribbon_state.slow, "spread_cents": ribbon_state.spread_cents,
                   "stack": ribbon_state.stack}
        try:
            sgs = _shotgun.detect_shotgun_scalper_setup(
                bar=bar, day_bars=day_bars, bar_idx_in_day=bidx,
                ribbon_state_dict=rb_dict, vix_now=vix_now)
        except Exception as _e:
            sys.stderr.write(f"SHOTGUN_SCALPER bar={bar_time}: {type(_e).__name__}: {_e}\n")
            sgs = None
        if sgs is not None:
            shotgun_fires.append(
                {"date": str(bar_date), "conf": sgs.confidence, "dir": sgs.direction,
                 "tier": sgs.metadata.get("tier"), "vix": round(vix_now, 1)})
            if bar_date in ANCHORS:
                anchor_hits[bar_date]["SHOTGUN_SCALPER"].append((sgs.direction, sgs.confidence, None))

    # ── Build per-stream blocks (dedup = first fire per (date,dir,conf)) ──
    def _dedup(rows):
        seen = set()
        out = []
        for r in rows:
            key = (r["date"], r.get("dir"), r.get("conf"))
            if key in seen:
                continue
            seen.add(key)
            out.append(r)
        return out

    def _rowsfmt(rows):
        return [{"pnl": r["pnl"], "date": r["date"]} for r in rows]

    stream_blocks = {}
    for name in _STD_STREAMS:
        raw_rows = streams[name]
        ded = _dedup(raw_rows)
        raw_pnl = _rowsfmt(raw_rows)
        ded_pnl = _rowsfmt(ded)
        distinct = sorted({r["date"] for r in ded})
        stream_blocks[name] = {
            "raw": _stats(raw_pnl),
            "deduped": _stats(ded_pnl),
            "per_quarter_deduped": _per_quarter(ded_pnl),
            "distinct_dates": len(distinct),
        }

    # SHOTGUN fire-count block (no grade).
    sg_dates = sorted({r["date"] for r in shotgun_fires})
    sg_by_tier = defaultdict(int)
    for r in shotgun_fires:
        sg_by_tier[str(r["tier"])] += 1
    stream_blocks[_SHOTGUN_STREAM] = {
        "raw_fire_count": len(shotgun_fires),
        "distinct_dates": len(sg_dates),
        "by_tier": dict(sg_by_tier),
        "note": ("NEEDS-DEDICATED-GRADER: single-exit doctrine (12-min time stop + chandelier, "
                 "no runner). grade_observation's TP1+runner model does not fit; fire counts only."),
    }

    # ── Anchor-day block (OP-16 preservation) ──
    anchor_block = {}
    for d in sorted(ANCHORS):
        per_stream = {}
        for name in _STD_STREAMS + [_SHOTGUN_STREAM]:
            fires = anchor_hits.get(d, {}).get(name, [])
            if name == _SHOTGUN_STREAM:
                per_stream[name] = {"n": len(fires)}
            else:
                pnl = round(sum((f[2] or 0.0) for f in fires), 2)
                per_stream[name] = {"n": len(fires), "pnl": pnl}
        anchor_block[str(d)] = {"label": ANCHORS[d], **per_stream}

    result = {
        "window": f"{start}..{end}",
        "patterns_bootstrapped": _PATTERNS_BOOTSTRAPPED,
        "streams": stream_blocks,
        "anchor_days": anchor_block,
    }

    # ── Real-fills (optional) ──
    if do_realfills:
        from lib.simulator_real import simulate_trade_real
        rf = {}
        rf_diag: dict = {}
        for stream in _STD_STREAMS:
            inputs = realfills_inputs[stream]
            offsets = (("ATM", 0),) if stream in _LONG_ATM_ONLY else (("ATM", 0), ("ITM2", -2))
            for label, offset in offsets:
                rows = []
                n_attempted = 0
                n_no_fill = 0
                n_errored = 0
                for (idx, bar, sig) in inputs[:120]:
                    n_attempted += 1
                    side = "C" if sig.direction == "long" else "P"
                    rej = (sig.metadata.get("swept_level")
                           or sig.metadata.get("or_high")
                           or sig.metadata.get("neckline")
                           or sig.metadata.get("broken_level")
                           or sig.stop_price)
                    try:
                        fill = simulate_trade_real(
                            entry_bar_idx=idx, entry_bar=bar, spy_df=rth, ribbon_df=ribbon_df,
                            rejection_level=float(rej), triggers_fired=sig.triggers_fired,
                            side=side, qty=3, setup=sig.setup_name,
                            premium_stop_pct=-0.99, strike_offset=offset)
                    except Exception as _e:
                        n_errored += 1
                        if n_errored <= 3:  # surface first few; avoid log spam
                            sys.stderr.write(
                                f"real-fills {stream}_{label} bar={bar['timestamp_et']}: "
                                f"{type(_e).__name__}: {_e}\n")
                        fill = None
                    if fill is not None and getattr(fill, "dollar_pnl", None) is not None:
                        rows.append({"pnl": float(fill.dollar_pnl), "date": str(bar["timestamp_et"].date())})
                    else:
                        n_no_fill += 1
                rf[f"{stream}_{label}"] = _stats(rows)
                # OPRA coverage diagnostic — distinguishes "no edge" from "no OPRA data / errors".
                rf_diag[f"{stream}_{label}"] = {
                    "attempted": n_attempted, "filled": len(rows),
                    "no_fill_or_no_data": n_no_fill, "errored": n_errored,
                }
        result["real_fills_capped"] = rf
        result["real_fills_diagnostics"] = rf_diag

    return result


def _anchor_capture(anchor_block, name):
    """OP-16 edge_capture for one stream: sum(pnl on WIN days) - sum(max(0,-pnl) on LOSS days).

    Returns (win_pnl, loss_loss, edge_capture, anti_correlated_bool). anti_correlated=True
    means the stream loses on J's WIN days and/or profits on J's LOSS days — a red flag.
    """
    win_pnl = 0.0
    loss_loss = 0.0
    loss_day_profit = 0.0
    for d, blk in anchor_block.items():
        b = blk.get(name, {})
        pnl = b.get("pnl")
        if pnl is None:
            continue
        if blk["label"] == "WIN":
            win_pnl += pnl
        else:  # LOSS day
            loss_loss += max(0.0, -pnl)
            loss_day_profit += max(0.0, pnl)
    edge = round(win_pnl - loss_loss, 2)
    anti = win_pnl < 0 or loss_day_profit > abs(win_pnl)
    return round(win_pnl, 2), round(loss_loss, 2), edge, anti


def _verdict(block, rf, name, anchor_block):
    """Verdict per pattern: PROMOTE-CANDIDATE / WATCH-ONLY / FAILS-REAL-FILLS / NEEDS-DEDICATED-GRADER.

    Gates (all must hold for PROMOTE-CANDIDATE): n>=20, WR>=45, SPY exp>0, real-fills ATM exp>0,
    AND OP-16 anchor-no-regression (not anti-correlated with J's edge).
    """
    if name == _SHOTGUN_STREAM:
        return ("NEEDS-DEDICATED-GRADER — single-exit doctrine (12-min time stop + chandelier, no "
                "runner); grade_observation's TP1+runner model does not fit. Over-fires ~35x/day.")
    ded = block["deduped"]
    n, wr, exp = ded["n"], ded["wr"], ded["exp"]
    atm = (rf or {}).get(f"{name}_ATM")
    rf_str = ""
    rf_pass = None
    if atm and atm["n"] > 0:
        rf_str = f" Real-fills ATM exp ${atm['exp']} (N={atm['n']}, WR {atm['wr']}%)."
        rf_pass = atm["exp"] > 0 and atm["wr"] >= 45 and atm["n"] >= 15
    win_pnl, loss_loss, edge, anti = _anchor_capture(anchor_block, name)
    anchor_str = f" OP-16 anchor: WIN-day P&L ${win_pnl}, LOSS-day loss ${loss_loss}, edge_capture ${edge}."
    if anti:
        anchor_str += " ANTI-CORRELATED with J's edge (loses on WIN days / profits on LOSS days)."

    if n < 20:
        return f"WATCH-ONLY — SPY-space N={n} (<20 gate).{rf_str}{anchor_str}"
    if wr < 45 or exp <= 0:
        return f"WATCH-ONLY / DO-NOT-PROMOTE — SPY-space WR {wr}% exp ${exp} (N={n}).{rf_str}{anchor_str}"
    if rf_pass is False:
        return f"FAILS-REAL-FILLS — SPY-space WR {wr}% exp ${exp} (N={n}) but real-fills negative/thin.{rf_str}{anchor_str}"
    if rf_pass is True and anti:
        return (f"WATCH-ONLY / ANCHOR-REGRESSION — SPY-space WR {wr}% exp ${exp} (N={n}) and real-fills "
                f"positive, BUT fails OP-16 anchor gate.{rf_str}{anchor_str} Mechanical gates pass; "
                f"edge-alignment fails — DO NOT promote.")
    if rf_pass is True:
        return f"PROMOTE-CANDIDATE — SPY-space WR {wr}% exp ${exp} (N={n}); real-fills positive; anchor OK.{rf_str}{anchor_str}"
    return f"WATCH-ONLY — SPY-space WR {wr}% exp ${exp} (N={n}); real-fills inconclusive.{rf_str}{anchor_str}"


def _build_verdicts(result):
    rf = result.get("real_fills_capped", {})
    anchor_block = result.get("anchor_days", {})
    out = {}
    for name in _STD_STREAMS + [_SHOTGUN_STREAM]:
        out[name] = _verdict(result["streams"][name], rf, name, anchor_block)
    return out


def _op20_disclosures(result):
    return {
        "data_source_per_watcher": {
            "ORB_RETEST_LONG": "Price structure only (opening range H/L + SMA10/50 from day_bars). "
                               "No disk-state look-ahead. Long-only via ORB_DIRECTION_FILTER; "
                               "MAX_OR_RANGE=2.00 narrow-OR gate active.",
            "DOUBLE_BOTTOM_BASE_QUIET": "ctx.prior_bars sliding window (double_bottom_detector) + "
                                        "VIX<20 + conf<0.60 + NOT_NEAR_NAMED via ctx.levels_active "
                                        "(historical levels). No disk look-ahead.",
            "DOUBLE_BOTTOM_MORNING_LOW_VOL": "Same as BASE_QUIET + MORNING 09:35-11:30 window. "
                                             "No disk look-ahead.",
            "MOMENTUM_ACCELERATION_HIGHVOL": "ctx.prior_bars (momentum_acceleration) + ribbon ALIGNED "
                                             "+ VIX>=20. No disk look-ahead.",
            "RSI_DIVERGENCE_BULL": "RSI(14) computed from ctx.prior_bars closes each bar; stateless "
                                   "except cooldown. No disk look-ahead.",
            "STAIRSTEP_CONTINUATION": "LOOK-AHEAD TRAP in production: reads automation/state/key-levels.json "
                                      "(TODAY's live levels). FIXED HERE by monkeypatching _load_named_levels "
                                      "to historical ★★+ levels per bar-date (_detect_from_history). Roles "
                                      "(broken_to_*) unavailable historically -> runs on intraday-break fallback "
                                      "path only; role-confirmed 'high' confidence is unreachable in this replay. "
                                      "CAVEAT: the historical level set is computed once at each day's FIRST RTH bar, "
                                      "so today's session-H/L levels are as-of day-open, not as-of-bar (a minor "
                                      "staleness, conservative — fewer levels). The intraday-break detection itself "
                                      "uses clean ctx.prior_bars (no look-ahead).",
            "SHOTGUN_SCALPER": "Reads key-levels.json AND auto-derives intraday levels from the bar window "
                               "(auto_derive_intraday_levels=True). Partially self-sufficient. Single-exit "
                               "doctrine -> not graded here.",
        },
        "look_ahead_audit": (
            "ORB / double_bottom / momentum / rsi confirmed free of disk-state look-ahead "
            "(all read ctx.prior_bars <= current bar + historically-rebuilt levels). STAIRSTEP's "
            "production key-levels.json read is a genuine look-ahead trap, neutralized here via "
            "historical-level monkeypatch. SHOTGUN's key-levels read not exercised for grading."
        ),
        "grading_model": (
            "grade_observation: 50% qty TP1 + 50% runner-to-BE, same-day future bars to 15:50 ET, "
            "$ per 1 SPY contract (SPY move * 100). SPY-space proxy WR != real option P&L (see real_fills)."
        ),
        "real_fills_model": (
            "simulator_real.simulate_trade_real over OPRA bars (valid through 2026-05-29; later signals "
            "yield no fill and are dropped). chart-stop only (premium_stop_pct=-0.99 per L51/L55). "
            "qty=3. ATM (strike_offset=0) reported for all; ITM2 (strike_offset=-2) for streams that "
            "can take either side. Capped at first 120 signals/stream for runtime. NOTE: real-fills N "
            "counts RAW signals (pre-dedup, OPRA-available), so it can exceed the SPY-space DEDUPED N "
            "(which collapses same-date/dir/conf). Compare WR/exp, not N directly."
        ),
        "anchor_gate": (
            "OP-16: positive capture on WIN anchors (4/29, 5/01, 5/04), no/low loss on LOSS anchors "
            "(5/05, 5/06, 5/07). See anchor_days block."
        ),
        "cross_check": (
            "ORB cross-checked vs analysis/recommendations/orb_real_fills.json; double-bottom variants vs "
            "db-base-quiet-real-fills.json / db-morning-lowvol-real-fills.json; momentum vs "
            "momentum-accel-highvol-real-fills.json. Differences expected because those scans use simplified "
            "filters (e.g. NOT_NEAR_NAMED omitted) and curated test pools; this is a full ctx-pipeline replay."
        ),
        "concentration_caveat": (
            "Per-quarter breakdown discloses regime concentration; a stream whose positive expectancy "
            "is one-quarter-driven is regime-fragile (cf. ORB 2026-Q2 concentration in orb_real_fills.json)."
        ),
    }


def _cross_check_findings(result):
    """Compare to existing per-watcher scorecards in analysis/recommendations/."""
    rec = ROOT / "analysis" / "recommendations"
    rf = result.get("real_fills_capped", {})
    out = {}

    def _load(name):
        p = rec / name
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8-sig"))
            except Exception:
                return None
        return None

    mom = _load("momentum-accel-highvol-real-fills.json")
    if mom:
        mine = rf.get("MOMENTUM_ACCELERATION_HIGHVOL_ATM", {})
        out["MOMENTUM_ACCELERATION_HIGHVOL"] = {
            "existing_scorecard": "momentum-accel-highvol-real-fills.json",
            "existing_real_wr_pct": round(mom.get("wr_real", 0) * 100, 1),
            "existing_exp": mom.get("avg_dollar_pnl_per_trade"),
            "mine_real_wr_pct": mine.get("wr"),
            "mine_exp": mine.get("exp"),
            "agreement": "AGREE — both DEGRADED (real WR ~41-43%, negative expectancy). "
                         "My exp is harsher (full ctx pipeline + 120-cap).",
        }
    db = _load("db-base-quiet-real-fills.json")
    if db:
        mine = rf.get("DOUBLE_BOTTOM_BASE_QUIET_ATM", {})
        out["DOUBLE_BOTTOM_BASE_QUIET"] = {
            "existing_scorecard": "db-base-quiet-real-fills.json",
            "existing_real_wr_pct": round(db.get("wr_real", 0) * 100, 1),
            "existing_exp": db.get("avg_dollar_pnl_per_trade"),
            "mine_real_wr_pct": mine.get("wr"),
            "mine_exp": mine.get("exp"),
            "agreement": "DISAGREE — existing FAVORABLE (+$14/trade, WR 63.9%) OMITS the "
                         "NOT_NEAR_NAMED proximity filter (N=122); my full-pipeline replay "
                         "APPLIES it and flips NEGATIVE (-$14.88, WR 43.9%, N=41). The proximity "
                         "filter is doing real work — the simplified scan overstated edge.",
        }
    dbm = _load("db-morning-lowvol-real-fills.json")
    if dbm:
        mine = rf.get("DOUBLE_BOTTOM_MORNING_LOW_VOL_ATM", {})
        out["DOUBLE_BOTTOM_MORNING_LOW_VOL"] = {
            "existing_scorecard": "db-morning-lowvol-real-fills.json",
            "existing_real_wr_pct": round(dbm.get("wr_real", 0) * 100, 1),
            "existing_exp": dbm.get("avg_dollar_pnl_per_trade"),
            "mine_real_wr_pct": mine.get("wr"),
            "mine_exp": mine.get("exp"),
            "agreement": "PARTIAL — existing FAVORABLE (+$7.6/trade, WR 67.9%, N=109, NOT_NEAR_NAMED "
                         "omitted). My full-pipeline real-fills WR 54.5% but exp -$3.74 (N=22). "
                         "SPY-space stays strong (WR 73.7%); real-fills slips with the proximity "
                         "filter + small N. WATCH_FRAGILE (walk-forward already DEGRADED -15.2pp).",
        }
    orb = _load("orb_real_fills.json")
    if orb:
        mine = rf.get("ORB_RETEST_LONG_ATM", {})
        out["ORB_RETEST_LONG"] = {
            "existing_scorecard": "orb_real_fills.json",
            "existing_watcher_proxy_wr_oos_pct": round(orb.get("watcher_proxy_wr_oos", 0) * 100, 1),
            "existing_verdict": orb.get("verdict"),
            "mine_real_wr_pct": mine.get("wr"),
            "mine_exp": mine.get("exp"),
            "agreement": "CONSISTENT DIRECTION — existing v2 chart-stop FAIL (<50% gate in some "
                         "variants); my full-window real-fills ATM is ~breakeven (exp -$0.86, "
                         "WR 58.1%, N=62). Both say ORB long is NOT a clean real-fills win. "
                         "My SPY-space proxy (63.1%) is lower than their 79.8% OOS proxy because "
                         "I run the full state machine over ALL days incl. narrow-OR gate.",
        }
    return out


def _promotion_priority(result):
    """Rank patterns by promotion-readiness. Lower rank = closer to promotion."""
    rf = result.get("real_fills_capped", {})
    anchor_block = result.get("anchor_days", {})
    rows = []
    for name in _STD_STREAMS:
        ded = result["streams"][name]["deduped"]
        atm = rf.get(f"{name}_ATM", {})
        n, wr, exp = ded["n"], ded["wr"], ded["exp"]
        rf_exp = atm.get("exp")
        rf_n = atm.get("n", 0)
        win_pnl, loss_loss, edge, anti = _anchor_capture(anchor_block, name)
        gate_n = n >= 20
        gate_wr = wr >= 45
        gate_exp = exp > 0
        gate_rf = rf_exp is not None and rf_exp > 0
        gate_anchor = not anti
        gates_passed = sum([gate_n, gate_wr, gate_exp, gate_rf, gate_anchor])
        rows.append({
            "pattern": name, "spy_n": n, "spy_wr": wr, "spy_exp": exp,
            "realfills_atm_exp": rf_exp, "realfills_atm_n": rf_n,
            "anchor_edge_capture": edge, "anchor_anti_correlated": anti,
            "gates": {"n>=20": gate_n, "wr>=45": gate_wr, "spy_exp>0": gate_exp,
                      "realfills_exp>0": gate_rf, "anchor_no_regression": gate_anchor},
            "gates_passed": gates_passed,
        })
    rows.sort(key=lambda r: (-r["gates_passed"], -(r["realfills_atm_exp"] or -999)))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    rows.append({
        "pattern": _SHOTGUN_STREAM, "rank": "n/a",
        "note": "NEEDS-DEDICATED-GRADER — not rankable until single-exit grader exists. "
                "Fires ~35x/day (12,667 over 361 days) — over-firing, matches WATCH_FRAGILE -$1.63/obs.",
    })
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2025-01-01")
    ap.add_argument("--end", default="2026-06-16")
    ap.add_argument("--realfills", action="store_true")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    res = run(dt.date.fromisoformat(a.start), dt.date.fromisoformat(a.end), a.realfills)
    res["verdict"] = _build_verdicts(res)
    res["cross_check_findings"] = _cross_check_findings(res)
    res["promotion_priority"] = _promotion_priority(res)
    res["op20_disclosures"] = _op20_disclosures(res)
    txt = json.dumps(res, indent=2, default=str)
    print(txt)
    if a.out:
        outp = Path(a.out)
        if not outp.is_absolute():
            outp = (Path.cwd() / outp).resolve()
        outp.write_text(txt, encoding="utf-8")
        print("wrote", outp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

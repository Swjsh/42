"""Winner Forensics — Phase 2.3 implementation.

For every winning trade:
  1. Extract trigger-bar fingerprint (Phase 2.2 — full feature vector via _bar_features)
  2. Find tight analogous bars in 16mo (vol_mult + ribbon_stack + time-of-day + level proximity)
  3. Run simulator_real on each analog → hit_rate + expectancy
  4. Verdict + auto-queue doctrine candidate

Answers J's question: "is today's winner REPEATABLE or LUCKY?" — with statistical backing.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from ..schema import CategoryScore, TradeRecord
from ..ingest import IngestedData
from ._bar_features import (
    BarFeatures,
    compute_ribbon_cached,
    compute_vol_baseline,
    compute_bar_features,
    vectorized_features_for_all_bars,
)

REPO = Path(__file__).resolve().parent.parent.parent.parent.parent
MASTER_5M = REPO / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-12.csv"
# Today's bars may be in a shorter CSV (EOD appender writes daily windows).
# Find the latest 5m CSV that contains today and merge it for trigger-bar lookups.
DATA_DIR = REPO / "backtest" / "data"

# Add backtest dir to path for simulator_real import
sys.path.insert(0, str(REPO / "backtest"))
try:
    from lib.simulator_real import simulate_trade_real, TradeFill
    SIMULATOR_AVAILABLE = True
except Exception:
    SIMULATOR_AVAILABLE = False


@dataclass
class Fingerprint:
    """Trigger-bar feature vector — fully populated now (Phase 2.2)."""
    setup_name: str = ""
    direction: str = ""
    time_of_day_min_from_open: int = -1
    ribbon_stack: str = ""
    ribbon_spread_cents: float = -1.0
    vol_mult_vs_20bar: float = -1.0
    bar_body_pct_of_range: float = -1.0
    bull_score: int = -1
    bear_score: int = -1
    vix_value: float = -1.0
    vix_dir: str = ""
    nearest_level_distance: float = -1.0
    nearest_level_role: str = ""
    trigger_types: list[str] = field(default_factory=list)
    trigger_bar_date: str = ""
    trigger_bar_time: str = ""


@dataclass
class AnalogMatch:
    bar_date: str
    bar_time: str
    bar_idx_in_master: int
    spy_close: float
    vol_mult: float
    ribbon_stack: str
    ribbon_spread: float
    sim_pnl_dollars: Optional[float] = None    # filled by Phase 2.3 simulator
    sim_status: str = "not_run"


# Phase 2.2 match tolerances
TOLERANCE = {
    "time_of_day_min": 15,         # ±15 min
    "vol_mult_rel": 0.30,           # ±30% of fingerprint's vol_mult
    "ribbon_spread_rel": 0.40,      # ±40% of fingerprint's ribbon spread
}


def _load_master_with_features(target_date: str = "") -> Optional[tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.DataFrame]]:
    """Load master CSV + merge any newer daily-window CSV that contains target_date.

    Returns (spy_df, ribbon_df, vol_baseline, features_df) or None on failure.

    Behavior:
      1. Load master spy_5m_2025-01-01_2026-05-12.csv (16mo)
      2. Find newer CSVs (spy_5m_2026-*.csv) that contain target_date
      3. Append + dedup so trigger-bar lookup works for today
    """
    if not MASTER_5M.exists():
        return None
    try:
        spy_df = pd.read_csv(MASTER_5M)
        spy_df["timestamp_et"] = pd.to_datetime(spy_df["timestamp_et"])
        if spy_df["timestamp_et"].dt.tz is not None:
            spy_df["timestamp_et"] = spy_df["timestamp_et"].dt.tz_localize(None)

        # Extend with newer daily-window CSVs if target_date is after master end
        master_max_date = spy_df["timestamp_et"].dt.date.max().isoformat()
        if target_date and target_date > master_max_date:
            for newer_csv in sorted(DATA_DIR.glob("spy_5m_2026-*.csv"), reverse=True):
                try:
                    newer = pd.read_csv(newer_csv)
                    newer["timestamp_et"] = pd.to_datetime(newer["timestamp_et"])
                    if newer["timestamp_et"].dt.tz is not None:
                        newer["timestamp_et"] = newer["timestamp_et"].dt.tz_localize(None)
                    if target_date in newer["timestamp_et"].dt.date.astype(str).values:
                        # Merge & dedup
                        spy_df = pd.concat([spy_df, newer], ignore_index=True)
                        spy_df = spy_df.drop_duplicates(subset=["timestamp_et"], keep="last")
                        spy_df = spy_df.sort_values("timestamp_et").reset_index(drop=True)
                        sys.stderr.write(f"forensics: merged {newer_csv.name} for target_date {target_date}\n")
                        break
                except Exception:
                    continue

        spy_df["date"] = spy_df["timestamp_et"].dt.date.astype(str)
        spy_df["time"] = spy_df["timestamp_et"].dt.strftime("%H:%M")
        ribbon_df = compute_ribbon_cached(spy_df)
        vol_baseline = compute_vol_baseline(spy_df["volume"])
        features_df = vectorized_features_for_all_bars(spy_df, ribbon_df, vol_baseline)
        return (spy_df, ribbon_df, vol_baseline, features_df)
    except Exception as e:
        sys.stderr.write(f"forensics: master CSV load failed: {e}\n")
        return None


def _extract_fingerprint(
    trade: TradeRecord,
    data: IngestedData,
    spy_df: Optional[pd.DataFrame],
    ribbon_df: Optional[pd.DataFrame],
    vol_baseline: Optional[pd.Series],
) -> Fingerprint:
    """Build a fingerprint from the trade + loop-state + master CSV bar features.

    Phase 2.2: real vol_mult + ribbon at entry bar by looking up the master CSV.
    """
    fp = Fingerprint()
    fp.setup_name = trade.setup_name
    fp.direction = trade.direction
    fp.trigger_types = list(trade.triggers_fired or [])

    # Time of day from first fill
    buy_fills = [f for f in trade.fills if f.side == "buy"]
    if not buy_fills:
        return fp
    buy = buy_fills[0]
    fp.trigger_bar_time = buy.time_et[:5]  # HH:MM
    fp.trigger_bar_date = data.date

    try:
        hh, mm, _ = buy.time_et.split(":")
        fp.time_of_day_min_from_open = (int(hh) - 9) * 60 + int(mm) - 30
    except (ValueError, AttributeError):
        pass

    # Loop-state extracts (snapshot from EOD; not necessarily trigger-bar exact)
    ls = data.loop_state or {}
    fs = ls.get("last_filter_score", {}) or {}
    fp.bull_score = int(fs.get("bull", -1))
    fp.bear_score = int(fs.get("bear", -1))
    vix = ls.get("vix_cache", {}) or {}
    try:
        fp.vix_value = float(vix.get("value", -1))
    except (ValueError, TypeError):
        pass
    fp.vix_dir = vix.get("dir", "")

    # Phase 2.2: trigger-bar exact lookup in master CSV
    # IMPORTANT: floor the entry time to 5m bar boundary (entry 09:58 → bar 09:55)
    if spy_df is not None and ribbon_df is not None and vol_baseline is not None:
        try:
            hh, mm, _ = buy.time_et.split(":")
            hh_i, mm_i = int(hh), int(mm)
            mm_floor = (mm_i // 5) * 5  # 58 → 55, 03 → 00
            target_ts = pd.Timestamp(f"{fp.trigger_bar_date} {hh_i:02d}:{mm_floor:02d}:00")
        except (ValueError, AttributeError):
            target_ts = pd.Timestamp(f"{fp.trigger_bar_date} {fp.trigger_bar_time}:00")

        matching = spy_df.index[spy_df["timestamp_et"] == target_ts]
        if len(matching) == 0:
            # Bar not in master (target date after master end window or merge missed)
            pass
        else:
            bar_idx = int(matching[0])
            features = compute_bar_features(spy_df, ribbon_df, vol_baseline, bar_idx, levels=[])
            fp.vol_mult_vs_20bar = features.vol_mult_20bar
            fp.bar_body_pct_of_range = features.body_pct_of_range
            fp.ribbon_stack = features.ribbon_stack
            fp.ribbon_spread_cents = features.ribbon_spread_cents
    else:
        # Fall back to loop-state ribbon (less accurate)
        ribbon = ls.get("ribbon", {}) or {}
        fp.ribbon_stack = ribbon.get("stack", "")
        try:
            fp.ribbon_spread_cents = float(ribbon.get("spread_cents", -1))
        except (ValueError, TypeError):
            pass

    return fp


def _search_analogous_bars_tight(
    fp: Fingerprint,
    spy_df: pd.DataFrame,
    features_df: pd.DataFrame,
) -> list[AnalogMatch]:
    """Phase 2.2: tight match using vectorized features.

    Filters:
      - RTH bars only
      - time-of-day within ±15 min of fingerprint
      - vol_mult within ±30% of fingerprint
      - ribbon_stack matches exactly (if fingerprint has one)
      - ribbon_spread_cents within ±40% of fingerprint (if populated)
    """
    if features_df is None or features_df.empty:
        return []

    matched = features_df[features_df["is_rth"] == True].copy()

    # Time-of-day window
    if fp.time_of_day_min_from_open >= 0:
        target = fp.time_of_day_min_from_open
        tol = TOLERANCE["time_of_day_min"]
        matched = matched[
            (matched["time_of_day_min_from_open"] >= target - tol) &
            (matched["time_of_day_min_from_open"] <= target + tol)
        ]

    # Vol_mult
    if fp.vol_mult_vs_20bar > 0:
        target_vm = fp.vol_mult_vs_20bar
        rel_tol = TOLERANCE["vol_mult_rel"]
        matched = matched[
            (matched["vol_mult_20bar"] >= target_vm * (1 - rel_tol)) &
            (matched["vol_mult_20bar"] <= target_vm * (1 + rel_tol))
        ]

    # Ribbon stack match
    if fp.ribbon_stack:
        matched = matched[matched["ribbon_stack"] == fp.ribbon_stack]

    # Ribbon spread match
    if fp.ribbon_spread_cents > 0:
        target_sp = fp.ribbon_spread_cents
        rel_tol = TOLERANCE["ribbon_spread_rel"]
        matched = matched[
            (matched["ribbon_spread_cents"] >= target_sp * (1 - rel_tol)) &
            (matched["ribbon_spread_cents"] <= target_sp * (1 + rel_tol))
        ]

    if matched.empty:
        return []

    # Group to one bar per day (the closest to target time)
    matched["abs_dist_min"] = (matched["time_of_day_min_from_open"] - fp.time_of_day_min_from_open).abs()
    spy_subset = spy_df.loc[matched.index, ["timestamp_et", "close"]].copy()
    matched = matched.join(spy_subset)
    matched["date"] = matched["timestamp_et"].dt.date.astype(str)
    matched = matched.sort_values(["date", "abs_dist_min"]).drop_duplicates(subset=["date"], keep="first")

    out = []
    for _, row in matched.iterrows():
        out.append(AnalogMatch(
            bar_date=str(row["date"]),
            bar_time=str(row["timestamp_et"])[11:16],
            bar_idx_in_master=int(row["bar_idx"]),
            spy_close=float(row.get("close", 0)),
            vol_mult=float(row.get("vol_mult_20bar", 0)),
            ribbon_stack=str(row.get("ribbon_stack", "")),
            ribbon_spread=float(row.get("ribbon_spread_cents", 0)),
        ))
    return out


def _simulate_analog(
    analog: AnalogMatch,
    spy_df: pd.DataFrame,
    ribbon_df: pd.DataFrame,
    fp: Fingerprint,
    knobs: dict,
) -> AnalogMatch:
    """Phase 2.3: Run simulator_real on the analog bar.

    Returns the analog with sim_pnl_dollars + sim_status populated.
    """
    if not SIMULATOR_AVAILABLE:
        analog.sim_status = "simulator_unavailable"
        return analog

    bar_idx = analog.bar_idx_in_master
    if bar_idx < 0 or bar_idx >= len(spy_df):
        analog.sim_status = "bar_idx_oob"
        return analog

    entry_bar = spy_df.iloc[bar_idx]
    side = "C" if fp.direction == "long" else "P"

    try:
        # Use knobs from params; fall back to v15 defaults
        result: Optional[TradeFill] = simulate_trade_real(
            entry_bar_idx=bar_idx,
            entry_bar=entry_bar,
            spy_df=spy_df,
            ribbon_df=ribbon_df,
            rejection_level=float(entry_bar.get("close", 0)),  # placeholder
            triggers_fired=fp.trigger_types,
            side=side,
            qty=int(knobs.get("qty", 10)),
            setup=fp.setup_name,
            premium_stop_pct=float(knobs.get("premium_stop_pct_bear", -0.20)),
            strike_offset=int(knobs.get("strike_offset_bear", -2)),
            profit_lock_threshold_pct=float(knobs.get("v15_profit_lock_threshold", 0.05)),
            profit_lock_stop_offset_pct=float(knobs.get("v15_profit_lock_offset", 0.10)),
            profit_lock_mode=str(knobs.get("v15_profit_lock_mode", "trailing")),
            profit_lock_trail_pct=float(knobs.get("v15_profit_lock_trail_pct", 0.20)),
        )
        if result is None:
            analog.sim_status = "no_fill"
            return analog
        # TradeFill uses `dollar_pnl` (not `pnl_dollars` — naming convention diff)
        pnl = getattr(result, "dollar_pnl", None) or getattr(result, "pnl_dollars", None) or 0.0
        analog.sim_pnl_dollars = float(pnl)
        analog.sim_status = "filled"
    except FileNotFoundError:
        analog.sim_status = "opra_cache_miss"
    except Exception as e:
        analog.sim_status = f"error:{type(e).__name__}"
    return analog


def _aggregate_analog_stats(analogs: list[AnalogMatch]) -> dict:
    """Phase 2.3: compute hit_rate + expectancy stats from simulated analogs."""
    n_total = len(analogs)
    # Build status breakdown ALWAYS (so we can see WHY no fills happened)
    statuses: dict[str, int] = {}
    for a in analogs:
        statuses[a.sim_status] = statuses.get(a.sim_status, 0) + 1

    filled = [a for a in analogs if a.sim_pnl_dollars is not None]
    n_with_fills = len(filled)
    if n_with_fills == 0:
        return {
            "n_total": n_total,
            "n_with_fills": 0,
            "hit_rate_pct": 0.0,
            "avg_pnl_dollars": 0.0,
            "std_dev_pnl": 0.0,
            "p25_pnl": 0.0,
            "p50_pnl": 0.0,
            "p75_pnl": 0.0,
            "max_win": 0.0,
            "max_loss": 0.0,
            "sim_status_breakdown": statuses,
        }
    pnls = np.array([a.sim_pnl_dollars for a in filled])
    wins = pnls[pnls > 0]

    return {
        "n_total": n_total,
        "n_with_fills": n_with_fills,
        "hit_rate_pct": round(len(wins) / n_with_fills * 100, 1),
        "avg_pnl_dollars": round(float(pnls.mean()), 2),
        "std_dev_pnl": round(float(pnls.std()), 2) if n_with_fills > 1 else 0.0,
        "p25_pnl": round(float(np.percentile(pnls, 25)), 2),
        "p50_pnl": round(float(np.percentile(pnls, 50)), 2),
        "p75_pnl": round(float(np.percentile(pnls, 75)), 2),
        "max_win": round(float(pnls.max()), 2),
        "max_loss": round(float(pnls.min()), 2),
        "sim_status_breakdown": statuses,
    }


def _verdict(stats: dict, fingerprint_completeness: float) -> tuple[str, str]:
    """Verdict based on Phase 2.3 hit-rate + expectancy."""
    n = stats.get("n_with_fills", 0)
    hit = stats.get("hit_rate_pct", 0)
    avg = stats.get("avg_pnl_dollars", 0)

    if fingerprint_completeness < 0.5:
        return ("NEEDS-MORE-DATA",
                f"Fingerprint only {fingerprint_completeness:.0%} populated. Tight match impossible.")

    # NEW Phase 2.3 verdict: 100% WR small-sample = clear edge confirmation
    if n >= 3 and hit == 100.0 and avg > 0:
        return ("EDGE-CONFIRMED-SMALL-SAMPLE",
                f"{n} tight analogs ALL profitable (100% WR, avg ${avg:+.0f}). "
                f"Sample size small but signal-to-noise is high. Edge confirmed; need n≥20 for full REPEATABLE.")

    if n < 5:
        return ("LUCKY",
                f"Only {n} tight analogs with simulator fills. Sample too small for confident inference.")

    if n >= 20 and hit >= 55 and avg > 0:
        return ("REPEATABLE",
                f"{n} tight analogs / {hit:.0f}% hit rate / avg ${avg:+.0f}. Setup has STATISTICAL edge.")

    if n >= 10 and hit >= 50 and avg > 0:
        return ("RARE-BUT-CLEAN",
                f"{n} analogs / {hit:.0f}% hit / avg ${avg:+.0f}. Edge present but small sample.")

    if n >= 5 and (hit < 50 or avg <= 0):
        return ("DOCTRINE-MARGINAL",
                f"{n} analogs but hit_rate {hit:.0f}% or avg ${avg:+.0f} suggests setup has NO statistical edge under current doctrine. Today's win may have been a tail event.")

    return ("INCONCLUSIVE",
            f"{n} analogs / {hit:.0f}% hit / avg ${avg:+.0f}. Mixed evidence.")


def analyze_forensics(data: IngestedData, trades: list[TradeRecord]) -> CategoryScore:
    """Phase 2.2 + 2.3 forensics with real fingerprint + simulator hit-rate."""
    if not trades:
        return CategoryScore(
            score=50.0,
            evidence={"phase": "2.3", "trade_count": 0},
            narrative="No trades today. Forensics N/A.",
            actions=[],
        )

    loaded = _load_master_with_features(target_date=data.date)
    if loaded is None:
        return CategoryScore(
            score=40.0,
            evidence={"phase": "2.3", "error": "master_csv_missing"},
            narrative="master 5m CSV missing — forensics degraded.",
            actions=[],
        )
    spy_df, ribbon_df, vol_baseline, features_df = loaded

    # Knobs from current params.json
    params = data.params or {}
    knobs = {
        "qty": params.get("v15_default_qty", 10),
        "premium_stop_pct_bear": params.get("v15_premium_stop_pct_bear", -0.20),
        "strike_offset_bear": params.get("v15_strike_offset_bear", -2),
        "v15_profit_lock_mode": params.get("v15_profit_lock_mode", "trailing"),
        "v15_profit_lock_threshold": params.get("v15_profit_lock_threshold", 0.05),
        "v15_profit_lock_offset": params.get("v15_profit_lock_offset", 0.10),
        "v15_profit_lock_trail_pct": params.get("v15_profit_lock_trail_pct", 0.20),
    }

    winners = [t for t in trades if t.pnl_dollars_realized > 0]
    losers = [t for t in trades if t.pnl_dollars_realized < 0]

    forensics_results = []
    actions = []

    for t in winners:
        fp = _extract_fingerprint(t, data, spy_df, ribbon_df, vol_baseline)
        fp_dict = asdict(fp)
        populated = sum(1 for k, v in fp_dict.items()
                        if v not in (-1, -1.0, "", None, [], False))
        completeness = populated / len(fp_dict)

        analogs = _search_analogous_bars_tight(fp, spy_df, features_df)

        # Phase 2.3: simulate each analog (cap at 50 to keep runtime sane)
        ANALOG_CAP = 50
        simulated_analogs = []
        for a in analogs[:ANALOG_CAP]:
            simulated_analogs.append(_simulate_analog(a, spy_df, ribbon_df, fp, knobs))

        stats = _aggregate_analog_stats(simulated_analogs)
        verdict, narrative = _verdict(stats, completeness)

        # Phase 2.6 support: expose analog bar idxs + dates for downstream
        # knob_round_trip analog-based sweep.
        analog_records = []
        for a in simulated_analogs:
            analog_records.append({
                "bar_date": a.bar_date,
                "bar_time": a.bar_time,
                "bar_idx_in_master": a.bar_idx_in_master,
                "spy_close": a.spy_close,
                "vol_mult": a.vol_mult,
                "ribbon_stack": a.ribbon_stack,
                "ribbon_spread": a.ribbon_spread,
                "sim_pnl_dollars": a.sim_pnl_dollars,
                "sim_status": a.sim_status,
            })

        forensics_results.append({
            "trade_id": t.id,
            "setup_name": t.setup_name,
            "fingerprint": fp_dict,
            "fingerprint_completeness_pct": round(completeness * 100, 1),
            "analogous_bar_count_16mo_tight": len(analogs),
            "analogs_simulated": len(simulated_analogs),
            "analog_records": analog_records,    # Phase 2.6: needed by knob_round_trip
            "analog_stats": stats,
            "verdict": verdict,
            "narrative": narrative,
            "actual_pnl_dollars": t.pnl_dollars_realized,
            "actual_pnl_pct": t.pnl_pct_on_capital,
            "actual_vs_avg_analog": round(
                t.pnl_dollars_realized - stats.get("avg_pnl_dollars", 0), 2
            ),
        })

        # Auto-queue doctrine candidate
        if verdict in ("REPEATABLE", "RARE-BUT-CLEAN", "EDGE-CONFIRMED-SMALL-SAMPLE"):
            actions.append({
                "type": "queue_for_grinder",
                "priority": "MED",
                "details": {
                    "setup_name": t.setup_name,
                    "rationale": (f"Tight forensics: {stats.get('n_with_fills')}/{stats.get('n_total')} analogs, "
                                  f"hit_rate {stats.get('hit_rate_pct')}%, avg ${stats.get('avg_pnl_dollars'):+.0f}. "
                                  f"Today's actual ${t.pnl_dollars_realized:+.0f} sits at p{_percentile_estimate(t.pnl_dollars_realized, stats)} of analogs."),
                    "fingerprint_for_search": fp_dict,
                    "analog_stats": stats,
                }
            })

    # Score: weighted by verdict + hit-rate quality
    score_map = {
        "REPEATABLE": 95,
        "EDGE-CONFIRMED-SMALL-SAMPLE": 85,    # NEW: 100% WR small-sample
        "RARE-BUT-CLEAN": 80,
        "DOCTRINE-MARGINAL": 40,  # warns that today may be a tail event
        "INCONCLUSIVE": 60,
        "LUCKY": 50,
        "NEEDS-MORE-DATA": 50,
    }
    if forensics_results:
        avg_score = sum(score_map.get(r["verdict"], 50) for r in forensics_results) / len(forensics_results)
    else:
        avg_score = 50.0

    narrative_lines = []
    narrative_lines.append(f"Winners analyzed: {len(winners)}, losers: {len(losers)}")
    for r in forensics_results:
        s = r["analog_stats"]
        narrative_lines.append(
            f"  • {r['setup_name']}: {r['verdict']} | "
            f"{s.get('n_with_fills')}/{s.get('n_total')} analogs with fills | "
            f"hit {s.get('hit_rate_pct')}% / avg ${s.get('avg_pnl_dollars'):+.0f} / "
            f"p25={s.get('p25_pnl')} p50={s.get('p50_pnl')} p75={s.get('p75_pnl')} | "
            f"today actual {r['actual_pnl_pct']:+.1f}%"
        )

    # OP 20 disclosures
    narrative_lines.append("")
    narrative_lines.append("[Phase 2.3 disclosures]:")
    for r in forensics_results:
        s = r["analog_stats"]
        narrative_lines.append(
            f"  - n_analogs_total={s.get('n_total')}, "
            f"n_with_fills={s.get('n_with_fills')} "
            f"(opra_cache_miss = {s.get('sim_status_breakdown', {}).get('opra_cache_miss', 0)}), "
            f"std_dev=${s.get('std_dev_pnl')}, range=[${s.get('max_loss'):+.0f}, ${s.get('max_win'):+.0f}]"
        )

    return CategoryScore(
        score=round(avg_score, 1),
        evidence={
            "phase": "2.3",
            "winners_count": len(winners),
            "forensics_per_trade": forensics_results,
            "tolerances": TOLERANCE,
            "knobs_used": knobs,
        },
        narrative="\n".join(narrative_lines),
        actions=actions,
    )


def _percentile_estimate(actual_value: float, stats: dict) -> int:
    """Rough percentile placement of `actual_value` within the analog distribution."""
    p25 = stats.get("p25_pnl", 0)
    p50 = stats.get("p50_pnl", 0)
    p75 = stats.get("p75_pnl", 0)
    max_w = stats.get("max_win", 0)
    max_l = stats.get("max_loss", 0)
    if actual_value >= max_w: return 99
    if actual_value >= p75: return 80
    if actual_value >= p50: return 60
    if actual_value >= p25: return 35
    if actual_value <= max_l: return 1
    return 15

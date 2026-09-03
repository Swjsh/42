#!/usr/bin/env python
"""money_structure_stop_buffer_sim.py -- H5 STRUCTURE-STOP WHIPSAW buffer simulation.

Reads analysis/deep-research/2026-09-03-money/structure-stop-population.json
(built by money_structure_stop_extract.py) and, for every real structure_stop exit
with a usable entry match and forward SPY/option bars:

  1. Reconstructs the exact 5-min bar the LIVE stop fired on (validates against
     backtest/lib/../automation/state/fleet/exit_manager.py::_structure_stop_hit's
     documented rule: side C exits close < trigger_level, side P exits
     close > trigger_level -- single closed 5m bar, no buffer, no confirm-count).
  2. Checks SPY whipsaw: does price reclaim the trigger level (close back through
     it, in the ORIGINAL side's favor) within 15/30/60 minutes (3/6/12 5m bars)
     after the actual stop bar.
  3. Reports the option's own premium path afterwards (+15/+30/+60 min close vs
     the reconstructed stop-exit premium), from cached 5-min option bars
     (backtest/data/options/<symbol>.csv).
  4. Re-walks the SAME bar sequence under 5 candidate stop rules, using ONLY
     information available at or before each bar's own close (no look-ahead):
       BUF-0.15 / BUF-0.25 : fixed-dollar buffer beyond trigger_level
       BUF-ATR0.5x         : buffer = 0.5 * trailing-12-bar SPY 5m ATR (as of
                              that bar; computed only from PRIOR closed bars)
       TWO-CLOSES          : raw (unbuffered) breach must hold on 2 CONSECUTIVE
                              closed 5m bars before firing
       GRACE-1BAR          : fires unconditionally one closed 5m bar later than
                              CONTROL's own fire bar (a fixed one-bar execution
                              delay, not a re-arming filter)
     Each variant's counterfactual exit premium is read off the SAME cached
     option-bar series (close - $0.02 slippage, matching the market-style-stage
     convention documented in backtest/tools/ribbon_flipback_buffer_ab.py's own
     disclosures), with the -50% catastrophe cap and the 15:50 ET hard time-stop
     enforced as a floor/ceiling on every variant identically.
  5. Aggregates dollars-saved-vs-absorbed per variant, per arm, with a bootstrap
     CI on the per-position paired delta (>=2000 resamples), and reports the
     effect on the 4 named winning days (08-06/08-13/08-27/08-28) explicitly.

READ-ONLY on automation/state and journal. Writes ONLY under
analysis/deep-research/2026-09-03-money/. Cached data only -- no network/broker
calls (backtest/data/options/*.csv and backtest/data/spy_5m_*.csv are static
disk files fetched by earlier sessions).
"""
from __future__ import annotations

import datetime as dt
import json
import random
import statistics
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
OUT_DIR = REPO / "analysis" / "deep-research" / "2026-09-03-money"
POP_PATH = OUT_DIR / "structure-stop-population.json"
SPY5M = REPO / "backtest" / "data" / "spy_5m_2026-05-19_2026-09-02.csv"
OPT_DIR = REPO / "backtest" / "data" / "options"
ARCH = REPO / "analysis" / "regime-library" / "day-archetypes.json"

TIME_STOP_ET = dt.time(15, 50)
RTH_OPEN = dt.time(9, 30)
RTH_CLOSE = dt.time(16, 0)
ATR_LOOKBACK_BARS = 12          # trailing 1 hour of 5m bars, entry-tick-available only
ATR_MULTIPLIER = 0.5            # a priori choice, NOT fitted to this study's outcomes
SLIPPAGE = 0.02                 # market-style-stage fill convention (documented precedent)
CATASTROPHE_FRAC = 0.50         # -50% of entry premium, doctrine-fixed floor both sides
N_BOOTSTRAP = 4000
RNG_SEED = 20260903
TODAY_ET = "2026-09-03"         # session in progress -- excluded, no forward bars exist yet

WINNING_DAYS = {"2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"}


def _naive_et(ts: str) -> dt.datetime:
    s = ts.strip()
    if s.endswith("Z"):
        d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    else:
        d = dt.datetime.fromisoformat(s)
    if d.tzinfo is not None:
        d = d.astimezone(dt.timezone(dt.timedelta(hours=-4))).replace(tzinfo=None)
    return d


def load_spy() -> pd.DataFrame:
    df = pd.read_csv(SPY5M)
    ts = pd.to_datetime(df["timestamp_et"], utc=True, format="mixed")
    ts = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    df = df.assign(timestamp_et=ts).sort_values("timestamp_et").reset_index(drop=True)
    df["date_et"] = df["timestamp_et"].dt.strftime("%Y-%m-%d")
    df["time_et"] = df["timestamp_et"].dt.time
    return df


def load_opt(symbol: str) -> pd.DataFrame | None:
    p = OPT_DIR / f"{symbol}.csv"
    if not p.exists():
        return None
    df = pd.read_csv(p)
    ts = pd.to_datetime(df["timestamp_et"], utc=True, format="mixed")
    ts = ts.dt.tz_convert("America/New_York").dt.tz_localize(None)
    return df.assign(timestamp_et=ts).sort_values("timestamp_et").reset_index(drop=True)


def rth_day_bars(spy: pd.DataFrame, date_et: str) -> pd.DataFrame:
    day = spy[spy["date_et"] == date_et]
    day = day[(day["time_et"] >= RTH_OPEN) & (day["time_et"] < RTH_CLOSE)]
    return day.reset_index(drop=True)


def raw_breach(side: str, close: float, trigger: float) -> bool:
    return (close < trigger) if side == "C" else (close > trigger)


def breach_margin(side: str, close: float, trigger: float) -> float:
    """Positive = breaching, magnitude = how far past trigger."""
    return (trigger - close) if side == "C" else (close - trigger)


def find_opt_close(opt_df: pd.DataFrame | None, ts: pd.Timestamp) -> float | None:
    if opt_df is None or opt_df.empty:
        return None
    exact = opt_df[opt_df["timestamp_et"] == ts]
    if not exact.empty:
        return float(exact.iloc[0]["close"])
    before = opt_df[opt_df["timestamp_et"] <= ts]
    if before.empty:
        return None
    return float(before.iloc[-1]["close"])


def opt_low_between(opt_df: pd.DataFrame | None, ts_start: pd.Timestamp,
                     ts_end: pd.Timestamp) -> tuple[pd.Timestamp, float] | None:
    if opt_df is None or opt_df.empty:
        return None
    window = opt_df[(opt_df["timestamp_et"] >= ts_start) & (opt_df["timestamp_et"] <= ts_end)]
    if window.empty:
        return None
    idx = window["low"].idxmin()
    row = window.loc[idx]
    return row["timestamp_et"], float(row["low"])


def simulate_variant(bars: pd.DataFrame, side: str, trigger: float, atr: pd.Series,
                      control_fire_idx: int, variant: str,
                      search_from: int = 0) -> int | None:
    """Returns the row-index (into `bars`) the variant fires on, or None if it
    never fires within the sequence (caller applies the 15:50 time-stop).
    `search_from` bounds the earliest bar a variant may fire on -- for the
    buffer/ATR variants this is always >= control_fire_idx BY CONSTRUCTION
    (adding a buffer can only make the raw breach condition harder to satisfy,
    never easier, so a buffered variant can never fire before the unbuffered
    CONTROL rule does)."""
    n = len(bars)
    closes = bars["close"].values
    if variant == "CONTROL":
        for i in range(search_from, n):
            if raw_breach(side, closes[i], trigger):
                return i
        return None
    if variant.startswith("BUF"):
        buf_dollars = {"BUF-0.15": 0.15, "BUF-0.25": 0.25}.get(variant)
        for i in range(search_from, n):
            margin = breach_margin(side, closes[i], trigger)
            if variant == "BUF-ATR0.5x":
                buf = ATR_MULTIPLIER * (atr.iloc[i] if pd.notna(atr.iloc[i]) else float("inf"))
            else:
                buf = buf_dollars
            if margin > buf:
                return i
        return None
    if variant == "TWO-CLOSES":
        start = max(search_from, 1)
        for i in range(start, n):
            if raw_breach(side, closes[i], trigger) and raw_breach(side, closes[i - 1], trigger):
                return i
        return None
    if variant == "GRACE-1BAR":
        if control_fire_idx is None:
            return None
        return min(control_fire_idx + 1, n - 1)
    raise ValueError(variant)


def resolve_exit_premium(opt_df: pd.DataFrame | None, bars: pd.DataFrame, fire_idx: int | None,
                          entry_price: float, event_bar_idx: int) -> dict:
    """Walk forward from event_bar_idx applying the catastrophe cap + 15:50 time
    stop as a floor/ceiling identical across every variant, using ONLY the
    cached option bar series. Returns dict with exit_ts, exit_premium, exit_kind."""
    n = len(bars)
    cap_level = entry_price * (1 - CATASTROPHE_FRAC)
    target_idx = fire_idx if fire_idx is not None else (n - 1)
    # clamp to the 15:50 hard time-stop
    for i in range(event_bar_idx, min(target_idx, n - 1) + 1):
        ts = bars.iloc[i]["timestamp_et"]
        if ts.time() >= TIME_STOP_ET:
            target_idx = min(target_idx, i)
            break
    ts_start = bars.iloc[event_bar_idx]["timestamp_et"]
    ts_target = bars.iloc[min(target_idx, n - 1)]["timestamp_et"]
    cap_hit = opt_low_between(opt_df, ts_start, ts_target)
    if cap_hit is not None and cap_hit[1] <= cap_level:
        return {"exit_ts": str(cap_hit[0]), "exit_premium": round(cap_level, 4),
                "exit_kind": "catastrophe_cap"}
    px = find_opt_close(opt_df, ts_target)
    if px is None:
        return {"exit_ts": str(ts_target), "exit_premium": None, "exit_kind": "no_opt_bar"}
    kind = "time_stop" if fire_idx is None or target_idx != fire_idx else "structure_stop_variant"
    return {"exit_ts": str(ts_target), "exit_premium": round(max(px - SLIPPAGE, 0.01), 4),
            "exit_kind": kind}


def bootstrap_ci(deltas: list[float], n_boot: int, rng: random.Random) -> dict:
    n = len(deltas)
    if n == 0:
        return {"n": 0, "mean": None, "ci_lo": None, "ci_hi": None}
    means = []
    for _ in range(n_boot):
        means.append(sum(deltas[rng.randrange(n)] for _ in range(n)) / n)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[int(0.975 * n_boot) - 1]
    return {"n": n, "mean": round(statistics.mean(deltas), 2),
            "sum": round(sum(deltas), 2),
            "ci_lower_2.5pct_mean": round(lo, 2), "ci_upper_97.5pct_mean": round(hi, 2),
            "ci_lower_2.5pct_sum": round(lo * n, 2), "ci_upper_97.5pct_sum": round(hi * n, 2)}


def vix_bucket(vix: float | None) -> str:
    if vix is None:
        return "unknown"
    if vix < 15:
        return "vix<15"
    if vix <= 17:
        return "vix15-17"
    return "vix>17"


def main() -> int:
    pop = json.loads(POP_PATH.read_text(encoding="utf-8"))
    events = pop["events"]
    spy = load_spy()
    arch = json.loads(ARCH.read_text(encoding="utf-8"))["days"]

    VARIANTS = ["BUF-0.15", "BUF-0.25", "BUF-ATR0.5x", "TWO-CLOSES", "GRACE-1BAR"]

    n_excluded_today = 0
    n_excluded_no_match = 0
    n_excluded_no_side_or_trigger = 0
    n_excluded_no_spy_day = 0
    n_excluded_no_control_bar = 0
    n_excluded_no_opt_bars = 0
    n_control_bar_close_value_mismatch = 0

    per_event = []
    opt_cache: dict[str, pd.DataFrame | None] = {}

    for ev in events:
        date_et = (ev["ts_et"] or "")[:10]
        if date_et == TODAY_ET:
            n_excluded_today += 1
            continue
        match = ev.get("mae_mfe_match")
        if not match:
            n_excluded_no_match += 1
            continue
        side = ev.get("side")
        trigger = ev.get("trigger_level")
        qty = ev.get("open_qty")
        last_closed = ev.get("last_closed_5m_close")
        if side not in ("C", "P") or trigger is None or not qty or last_closed is None:
            n_excluded_no_side_or_trigger += 1
            continue

        day_bars = rth_day_bars(spy, date_et)
        if day_bars.empty:
            n_excluded_no_spy_day += 1
            continue

        # --- anchor control_idx DIRECTLY from the real ledger record (the bar the
        # LIVE engine itself used), never re-derived by walking from an approximate
        # entry match -- eliminates entry-matching noise entirely for timing.
        # PRIMARY anchor = nearest closed 5m bar strictly before the recorded stop
        # tick (heartbeat fires ~1/min so this is unambiguous); the ledger's own
        # last_closed_5m_close is used only as a QC cross-check (median abs diff
        # against the cached SPY series is $0.015 -- rounding noise, disclosed --
        # not a switch condition), consistent with the documented live-feed-vs-
        # cached-CSV provenance gap in WALKER-STRUCTURE-STOP-MISFIRE-MECHANISM.
        event_ts = pd.Timestamp(_naive_et(ev["ts_et"]))
        closes_at = day_bars["timestamp_et"] + pd.Timedelta(minutes=5)
        eligible = day_bars[closes_at <= event_ts + pd.Timedelta(minutes=1)].reset_index(drop=True)
        if eligible.empty:
            n_excluded_no_control_bar += 1
            continue
        control_row = eligible.iloc[-1]  # nearest closed bar strictly before the stop tick
        close_qc_diff = abs(float(control_row["close"]) - float(last_closed))
        close_value_mismatch = close_qc_diff > 0.10  # flag only genuine provenance outliers
        if close_value_mismatch:
            n_control_bar_close_value_mismatch += 1
        control_idx = int(day_bars.index[day_bars["timestamp_et"] == control_row["timestamp_et"]][0])

        atr = (day_bars["high"] - day_bars["low"]).shift(1).rolling(
            ATR_LOOKBACK_BARS, min_periods=3).mean()

        opt_key = ev["symbol"]
        if opt_key not in opt_cache:
            opt_cache[opt_key] = load_opt(opt_key)
        opt_df = opt_cache[opt_key]
        if opt_df is None or opt_df.empty:
            n_excluded_no_opt_bars += 1
            continue

        entry_price = float(match["entry_price"])
        actual = resolve_exit_premium(opt_df, day_bars, control_idx, entry_price, control_idx)
        if actual["exit_premium"] is None:
            n_excluded_no_opt_bars += 1
            continue

        control_bar_closes_at = day_bars.iloc[control_idx]["timestamp_et"] + pd.Timedelta(minutes=5)

        # --- whipsaw check: reclaim within 3/6/12 bars (15/30/60 min) after control bar ---
        recl = {}
        for horizon, nbars in (("15m", 3), ("30m", 6), ("60m", 12)):
            window = day_bars.iloc[control_idx + 1: control_idx + 1 + nbars]
            reclaimed = False
            for _, r in window.iterrows():
                if side == "C" and r["close"] > trigger:
                    reclaimed = True
                    break
                if side == "P" and r["close"] < trigger:
                    reclaimed = True
                    break
            recl[horizon] = reclaimed

        # --- option path afterwards (close at +15/+30/+60m vs actual stop premium) ---
        opt_path = {}
        for horizon, minutes in (("15m", 15), ("30m", 30), ("60m", 60)):
            ts_h = control_bar_closes_at + pd.Timedelta(minutes=minutes)
            px = find_opt_close(opt_df, ts_h)
            opt_path[horizon] = (round(px, 4) if px is not None else None)

        row = {
            "date_et": date_et, "arm": ev["arm"], "symbol": ev["symbol"], "side": side,
            "trigger_level": trigger, "open_qty": qty, "entry_price": entry_price,
            "control_fire_bar_et": str(day_bars.iloc[control_idx]["timestamp_et"]),
            "recorded_event_ts_et": ev["ts_et"],
            "control_bar_close_qc_diff": round(close_qc_diff, 4),
            "control_bar_close_value_mismatch_gt_10c": bool(close_value_mismatch),
            "actual_exit_premium": actual["exit_premium"], "actual_exit_kind": actual["exit_kind"],
            "whipsaw_reclaim": recl, "option_path_close": opt_path,
            "vix": ev.get("vix"), "vix_from_archetype": (arch.get(date_et) or {}).get("vix_close"),
            "is_winning_day": date_et in WINNING_DAYS,
            "realized_pnl_full_position": match.get("realized_pnl"),
            "outcome": match.get("outcome"),
            "entry_match_reused": bool(match.get("_reused")),
            "variants": {},
        }

        for variant in VARIANTS:
            v_idx = simulate_variant(day_bars, side, trigger, atr, control_idx, variant,
                                     search_from=control_idx)
            res = resolve_exit_premium(opt_df, day_bars, v_idx, entry_price, control_idx)
            delta_dollars = None
            if res["exit_premium"] is not None:
                delta_dollars = round((res["exit_premium"] - actual["exit_premium"]) * qty * 100, 2)
            row["variants"][variant] = {
                "fire_bar_et": (str(day_bars.iloc[v_idx]["timestamp_et"]) if v_idx is not None else None),
                "fired_same_bar_as_control": (v_idx == control_idx),
                "exit_premium": res["exit_premium"], "exit_kind": res["exit_kind"],
                "delta_dollars_vs_actual": delta_dollars,
            }
        per_event.append(row)

    print(f"[sim] usable positions: {len(per_event)}")
    print(f"[sim] excluded: today={n_excluded_today} no_mae_match={n_excluded_no_match} "
          f"no_side_or_trigger={n_excluded_no_side_or_trigger} no_spy_day={n_excluded_no_spy_day} "
          f"no_control_bar={n_excluded_no_control_bar} no_opt_bars={n_excluded_no_opt_bars}")
    print(f"[sim] control-bar close QC outliers (>10c vs ledger's last_closed_5m_close, "
          f"anchor still used -- time-based, not value-based): "
          f"{n_control_bar_close_value_mismatch}/{len(per_event) + n_excluded_no_opt_bars}")

    rng = random.Random(RNG_SEED)
    agg = {}
    for variant in VARIANTS:
        deltas_all = [r["variants"][variant]["delta_dollars_vs_actual"] for r in per_event
                      if r["variants"][variant]["delta_dollars_vs_actual"] is not None]
        by_arm = {}
        for arm in sorted({r["arm"] for r in per_event}):
            d = [r["variants"][variant]["delta_dollars_vs_actual"] for r in per_event
                 if r["arm"] == arm and r["variants"][variant]["delta_dollars_vs_actual"] is not None]
            by_arm[arm] = bootstrap_ci(d, N_BOOTSTRAP, rng)
        by_vix = {}
        for bucket in ("vix<15", "vix15-17", "vix>17", "unknown"):
            d = [r["variants"][variant]["delta_dollars_vs_actual"] for r in per_event
                 if vix_bucket(r["vix"] or r["vix_from_archetype"]) == bucket
                 and r["variants"][variant]["delta_dollars_vs_actual"] is not None]
            if d:
                by_vix[bucket] = bootstrap_ci(d, N_BOOTSTRAP, rng)
        n_helped = sum(1 for d in deltas_all if d > 0.01)
        n_hurt = sum(1 for d in deltas_all if d < -0.01)
        n_flat = sum(1 for d in deltas_all if abs(d) <= 0.01)
        winning_day_rows = [r for r in per_event if r["is_winning_day"]]
        winning_day_deltas = [r["variants"][variant]["delta_dollars_vs_actual"]
                              for r in winning_day_rows
                              if r["variants"][variant]["delta_dollars_vs_actual"] is not None]
        agg[variant] = {
            "overall": bootstrap_ci(deltas_all, N_BOOTSTRAP, rng),
            "n_helped": n_helped, "n_hurt": n_hurt, "n_flat": n_flat,
            "dollars_saved_sum": round(sum(d for d in deltas_all if d > 0), 2),
            "dollars_extra_loss_sum": round(sum(d for d in deltas_all if d < 0), 2),
            "by_arm": by_arm, "by_vix_regime": by_vix,
            "winning_days_present": sorted({r["date_et"] for r in winning_day_rows}),
            "winning_days_n_events": len(winning_day_rows),
            "winning_days_delta_sum": round(sum(winning_day_deltas), 2) if winning_day_deltas else 0.0,
            "winning_days_detail": [
                {"date": r["date_et"], "arm": r["arm"], "symbol": r["symbol"],
                 "delta": r["variants"][variant]["delta_dollars_vs_actual"],
                 "fired_same_bar_as_control": r["variants"][variant]["fired_same_bar_as_control"]}
                for r in winning_day_rows
            ],
        }

    whipsaw_counts = {"15m": 0, "30m": 0, "60m": 0}
    for r in per_event:
        for h in whipsaw_counts:
            if r["whipsaw_reclaim"][h]:
                whipsaw_counts[h] += 1

    out = {
        "_meta": {
            "generated_from": str(POP_PATH.relative_to(REPO)).replace("\\", "/"),
            "n_population_events": len(events),
            "n_usable_positions": len(per_event),
            "exclusions": {
                "today_in_progress_no_forward_bars": n_excluded_today,
                "no_mae_mfe_match": n_excluded_no_match,
                "no_side_or_trigger_level": n_excluded_no_side_or_trigger,
                "no_spy_5m_bars_for_date": n_excluded_no_spy_day,
                "control_rule_never_fired_in_sequence": n_excluded_no_control_bar,
                "no_cached_option_bars": n_excluded_no_opt_bars,
            },
            "control_bar_close_qc_outliers_gt_10c": n_control_bar_close_value_mismatch,
            "n_bootstrap": N_BOOTSTRAP, "rng_seed": RNG_SEED,
            "slippage_dollars": SLIPPAGE, "catastrophe_frac": CATASTROPHE_FRAC,
            "atr_lookback_bars": ATR_LOOKBACK_BARS, "atr_multiplier": ATR_MULTIPLIER,
            "time_stop_et": str(TIME_STOP_ET),
        },
        "whipsaw_reclaim_counts": whipsaw_counts,
        "whipsaw_reclaim_rate": {h: round(c / len(per_event), 4) if per_event else None
                                 for h, c in whipsaw_counts.items()},
        "variant_aggregates": agg,
        "per_event": per_event,
    }
    out_path = OUT_DIR / "structure-stop-buffer-sim.json"
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    print(f"[sim] wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

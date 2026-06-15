"""pattern_backtest -- replay chart-pattern detectors against historical bars.

Per the 2026-05-18 ENGINE-BENEFIT AUTONOMY PRINCIPLE: the vision-observer L3 layer
is the human-eye on the chart. These detectors are its NUMERIC ground truth.

This driver walks a date's 5m bars sequentially, runs each detector at every bar
(using a 20-bar trailing window), records every pattern hit, and grades each hit
against the next-bar truth (did the pattern's bias direction win on the next bar?).

CLI:
    python -m autoresearch.pattern_backtest --date 2026-05-18
    python -m autoresearch.pattern_backtest --date 2026-04-29 --csv backtest/data/spy_5m_2025-01-01_2025-05-31.csv

Outputs:
    analysis/pattern-backtest-{date}.json
    analysis/pattern-backtest-{date}.md

Grading rules:
    A pattern HIT is graded WIN/LOSS/NEUTRAL based on next-5-min-bar close:
        - bullish pattern WINS if next bar close > current close
        - bearish pattern WINS if next bar close < current close
        - NEUTRAL if no next bar (final bar of session)

    A pattern HIT is graded HEARTBEAT_MISS if the heartbeat HOLD'd or didn't
    score it at the time of pattern completion (from decisions.jsonl).

Comparison to heartbeat:
    For each pattern hit, find the heartbeat decision in the matching 3-min window
    and tag:
        - ALIGNED: pattern bullish + heartbeat ENTER_BULL (within 3 min)
        - DIVERGED: pattern bullish + heartbeat HOLD/ENTER_BEAR
        - heartbeat_only: heartbeat fired but no pattern at that bar
        - pattern_only: pattern fired but no heartbeat decision

This is the quantification of "what we missed today" for the vision-observer
20-day promotion-path data flywheel.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from datetime import date as Date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any

# Make crypto + autoresearch importable
PROJECT_ROOT = Path(__file__).resolve().parents[2]
for p in (PROJECT_ROOT, PROJECT_ROOT / "backtest"):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

from crypto.lib.bar import Bar  # noqa: E402
from crypto.lib.chart_patterns import (  # noqa: E402
    PatternHit,
    double_bottom_detector,
    double_top_detector,
    failed_breakdown_wick,
    rejection_at_level,
    momentum_acceleration,
    inside_bar_consolidation,
    head_and_shoulders_detector,
    disambiguate_by_regime,
    contra_regime_only,
    enrich_hit_with_proximity,
)


# Map detector name -> bound callable taking only bars. Each detector's signature
# differs (lookback vs lookback_for_support); bind defaults explicitly here so
# the runner can call them uniformly.
DETECTORS: dict[str, Any] = {
    # RAW (one detector per row, no regime filter)
    "double_bottom": lambda bars: double_bottom_detector(bars, lookback=20),
    "double_top": lambda bars: double_top_detector(bars, lookback=20),
    "failed_breakdown_wick": lambda bars: failed_breakdown_wick(bars, lookback_for_support=10),
    "rejection_at_level_bearish": lambda bars: rejection_at_level(bars, lookback_for_resistance=10),
    "momentum_acceleration": lambda bars: momentum_acceleration(bars, lookback=10),
    "inside_bar_consolidation": lambda bars: inside_bar_consolidation(bars, min_consecutive_inside=2),
    "head_and_shoulders_top": lambda bars: head_and_shoulders_detector(bars, lookback=30),
    # REGIME-GATED variants — only fire when bias is contra to 50-bar SMA trend.
    # SMA50 (~4.2hr trailing) was the lookback used in the prior 16-mo
    # regime_breakdown analysis where contra-trend hits scored +4-15pp better.
    # SMA20 was tried first; backed out because intraday-only noise
    # (PATTERN-DISAMBIGUATION-16MO-2026-05-18 v2).
    "double_bottom_contra": lambda bars: contra_regime_only(
        double_bottom_detector(bars, lookback=20), bars, sma_lookback=50),
    "double_top_contra": lambda bars: contra_regime_only(
        double_top_detector(bars, lookback=20), bars, sma_lookback=50),
    "failed_breakdown_wick_contra": lambda bars: contra_regime_only(
        failed_breakdown_wick(bars, lookback_for_support=10), bars, sma_lookback=50),
    "rejection_at_level_bearish_contra": lambda bars: contra_regime_only(
        rejection_at_level(bars, lookback_for_resistance=10), bars, sma_lookback=50),
    "momentum_acceleration_contra": lambda bars: contra_regime_only(
        momentum_acceleration(bars, lookback=10), bars, sma_lookback=50),
    "head_and_shoulders_top_contra": lambda bars: contra_regime_only(
        head_and_shoulders_detector(bars, lookback=30), bars, sma_lookback=50),
}


def _load_bars_for_date(
    csv_path: Path,
    target_date: Date,
    prior_day_context: int = 0,
) -> tuple[list[Bar], int]:
    """Load 5m bars for the target trading date + optionally N prior-day RTH
    bars as context (for SMA50, regime classification, multi-day primitives).

    Returns:
        (bars, first_target_idx)
        - bars: chronological list of RTH bars, prior-day context FIRST then target-date.
        - first_target_idx: index in bars[] where target_date's RTH bars start.
                            If prior_day_context=0, this is 0 and bars == target-date only.

    CSV schema: timestamp_et,open,high,low,close,volume
    timestamp_et format: 2025-01-02 10:30:00-04:00 (ISO 8601 with tz offset)
    """
    import csv
    from datetime import timedelta as _td

    # Window: from (target_date - prior_day_context calendar days) through target_date
    # (calendar days, not trading days — we just over-fetch then filter)
    start_window = target_date - _td(days=prior_day_context * 2 + 5)  # generous buffer
    end_window = target_date

    all_target: list[Bar] = []
    all_prior: list[Bar] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts_str = row["timestamp_et"]
            try:
                ts = datetime.fromisoformat(ts_str)
            except ValueError:
                continue
            d = ts.date()
            if d > end_window or d < start_window:
                continue
            # Only RTH bars (09:30-16:00 ET); ignore extended-hours
            et_time = ts.time()
            if not (time(9, 30) <= et_time < time(16, 0)):
                continue
            bar = Bar(
                open_time=ts.astimezone(timezone.utc),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
                granularity_seconds=300,
                source="csv",
            )
            if d == target_date:
                all_target.append(bar)
            elif d < target_date and prior_day_context > 0:
                all_prior.append(bar)

    # all_prior is unsorted-by-date if CSV is monolithic; sort by open_time to be safe
    all_prior.sort(key=lambda b: b.open_time)
    all_target.sort(key=lambda b: b.open_time)

    # Trim prior to last (prior_day_context * 78) bars approx, by counting unique dates
    if prior_day_context > 0 and all_prior:
        # Walk backward, keep last prior_day_context unique trading days
        seen_dates: list[Date] = []
        kept: list[Bar] = []
        for b in reversed(all_prior):
            d = b.open_time.astimezone(timezone(timedelta(hours=-4))).date()
            if d not in seen_dates:
                if len(seen_dates) >= prior_day_context:
                    break
                seen_dates.append(d)
            kept.append(b)
        all_prior = list(reversed(kept))

    bars = all_prior + all_target
    first_target_idx = len(all_prior)
    return bars, first_target_idx


def _load_heartbeat_decisions(target_date: Date) -> list[dict]:
    """Load heartbeat decisions for the target date from decisions.jsonl.

    Returns a list of dict records with `time_et`, `action`, `bull_score`,
    `bear_score`, `spy`, etc. Empty list if file missing or no decisions for date.
    """
    decisions_file = PROJECT_ROOT / "automation" / "state" / "decisions.jsonl"
    if not decisions_file.exists():
        return []

    target_str = target_date.strftime("%Y-%m-%d")
    out: list[dict] = []
    with decisions_file.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(rec, dict):
                continue
            if rec.get("date") == target_str:
                out.append(rec)
    return out


def _load_named_levels_from_keyjson(target_date: Date) -> list[dict] | None:
    """Try to load ★★+ named levels for target_date.

    Lookup order:
      1. journal/key-levels-archive/key-levels-{YYYY-MM-DD}.json  (historical)
      2. automation/state/key-levels.json  (today only, for_session must match)

    If neither path has matching data, returns None so the caller falls back
    to synthetic PDH/PDL/PDC levels (_derive_named_levels).

    Archive path enables historical backtests to use the ACTUAL production ★★+
    levels that were in play on each day (not just PDH/PDL/PDC proxies).
    Archive files are written daily by the premarket archiver or manually via:
        cp automation/state/key-levels.json journal/key-levels-archive/key-levels-{date}.json

    Returns list of {price, name, tier, stars, source} dicts — same schema as
    _derive_named_levels() — filtered to levels with strength.stars >= 2.
    """
    def _parse_kl_file(path: Path) -> list[dict] | None:
        try:
            with path.open("r", encoding="utf-8") as f:
                kl = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None
        levels: list[dict] = []
        for lvl in kl.get("levels", []):
            stars = lvl.get("strength", {}).get("stars", 0)
            if stars < 2:
                continue
            price = lvl.get("price")
            if price is None:
                continue
            tier = lvl.get("tier", "Reference")
            direction = lvl.get("type", "")  # "support" or "resistance"
            source = lvl.get("source", "")
            dir_abbr = "R" if direction == "resistance" else "S"
            name = f"{tier[:3]}{dir_abbr} {price:.2f}"
            levels.append({
                "price": round(price, 2),
                "name": name,
                "tier": tier,
                "stars": stars,
                "source": source,
                "type": direction,  # preserve for named-level detector routing
            })
        return levels if levels else None

    # 1. Check per-date archive (works for any historical date)
    date_str = target_date.isoformat()
    archive_path = PROJECT_ROOT / "journal" / "key-levels-archive" / f"key-levels-{date_str}.json"
    if archive_path.exists():
        result = _parse_kl_file(archive_path)
        if result:
            return result

    # 2. Fall back to live state file (today only)
    kl_path = PROJECT_ROOT / "automation" / "state" / "key-levels.json"
    if not kl_path.exists():
        return None
    try:
        with kl_path.open("r", encoding="utf-8") as f:
            kl = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    for_session_str = kl.get("for_session", "")
    try:
        for_session = Date.fromisoformat(for_session_str)
    except (ValueError, TypeError):
        return None
    if for_session != target_date:
        return None
    return _parse_kl_file(kl_path)


def _derive_named_levels(bars: list[Bar], first_target_idx: int) -> list[dict]:
    """Derive prior-day's RTH H/L + first-target-day's pre-open H/L as
    named ★+ levels for the target day.

    For historical backtest, key-levels.json doesn't exist per-day. Instead we
    synthesize the well-known production levels:
        - PDH (prior-day RTH high) — ★★ Active
        - PDL (prior-day RTH low) — ★★ Active
        - PDC (prior-day RTH close) — ★ Reference
        - PDO (target-day RTH open) — ★ Reference (computed at bar 0)

    These are the deterministic levels J's strategy already keys off (see
    strategy/key-levels-protocol.md). Sufficient as a proxy for backtest
    enrichment.

    Returns list of {price, name, tier, stars, source}.
    """
    levels: list[dict] = []
    if first_target_idx == 0 or first_target_idx >= len(bars):
        # No prior-day context loaded; can't derive PDH/PDL
        return levels
    prior_bars = bars[:first_target_idx]
    if not prior_bars:
        return levels
    pdh = max(b.high for b in prior_bars)
    pdl = min(b.low for b in prior_bars)
    pdc = prior_bars[-1].close
    levels.extend([
        # PDH = prior-day high → acts as RESISTANCE (price rejected from above)
        {"price": round(pdh, 2), "name": "PDH", "tier": "Active",
         "stars": 2, "source": "prior_day_rth_high", "type": "resistance"},
        # PDL = prior-day low → acts as SUPPORT (price bounces from below)
        {"price": round(pdl, 2), "name": "PDL", "tier": "Active",
         "stars": 2, "source": "prior_day_rth_low", "type": "support"},
        # PDC = reference: acts as both support and resistance depending on context
        {"price": round(pdc, 2), "name": "PDC", "tier": "Reference",
         "stars": 1, "source": "prior_day_rth_close", "type": "reference"},
    ])
    # Target-day open (computed if target bars present)
    if first_target_idx < len(bars):
        pdo = bars[first_target_idx].open
        levels.append({"price": round(pdo, 2), "name": "PDO", "tier": "Reference",
                       "stars": 1, "source": "target_day_rth_open", "type": "reference"})
    return levels


def _nearest_named_level(price: float, named_levels: list[dict],
                         max_distance: float = 0.50) -> dict | None:
    """Find the nearest named ★+ level to `price` within `max_distance`.

    Returns the level dict + distance, or None if nothing within range.
    """
    if not named_levels:
        return None
    best: tuple[float, dict] | None = None
    for lvl in named_levels:
        d = abs(lvl["price"] - price)
        if d <= max_distance and (best is None or d < best[0]):
            best = (d, lvl)
    if best is None:
        return None
    return {
        "name": best[1]["name"],
        "tier": best[1]["tier"],
        "stars": best[1]["stars"],
        "level_price": best[1]["price"],
        "distance_dollars": round(best[0], 3),
    }


def _regime_at_bar(bars: list[Bar], i: int, sma_lookback: int = 50) -> str:
    """Classify regime at bar i based on close vs SMA of prior N closes.

    Returns:
        'uptrend'   if close > SMA
        'downtrend' if close < SMA
        'unknown'   if not enough history
    """
    if i < sma_lookback:
        return "unknown"
    window = bars[i - sma_lookback + 1: i + 1]
    sma = sum(b.close for b in window) / len(window)
    if bars[i].close > sma:
        return "uptrend"
    elif bars[i].close < sma:
        return "downtrend"
    return "unknown"


def _grade_hit(hit: PatternHit, bars: list[Bar]) -> str:
    """Grade a pattern hit against the next 5m bar's close.

    Returns 'WIN', 'LOSS', 'NEUTRAL'.
    Note: patterns with bias='neutral' (e.g. inside_bar_consolidation) always
    return NEUTRAL because they identify a regime (chop/consolidation) rather
    than predicting a direction — this is correct behavior, not a bug.
    """
    idx = hit.bar_index
    if idx + 1 >= len(bars):
        return "NEUTRAL"  # No next bar to grade against (final bar)
    current_close = bars[idx].close
    next_close = bars[idx + 1].close
    if hit.bias == "bullish":
        return "WIN" if next_close > current_close else "LOSS"
    elif hit.bias == "bearish":
        return "WIN" if next_close < current_close else "LOSS"
    return "NEUTRAL"


def _heartbeat_overlay(hit: PatternHit, bars: list[Bar], decisions: list[dict]) -> dict:
    """For each pattern hit, find heartbeat decisions in the SAME 5m window
    and tag the relationship."""
    # Convert hit's bar time to ET HH:MM
    hit_bar = bars[hit.bar_index]
    hit_et = hit_bar.open_time.astimezone(timezone(__import__("datetime").timedelta(hours=-4)))
    hit_minute = hit_et.hour * 60 + hit_et.minute

    # Find heartbeat decisions within +/- 3 min of hit bar's open
    matching: list[dict] = []
    for d in decisions:
        d_time_et = d.get("time_et", "")
        if not d_time_et:
            continue
        try:
            hh, mm = d_time_et.split(":")[0:2]
            d_minute = int(hh) * 60 + int(mm)
        except (ValueError, IndexError):
            continue
        if abs(d_minute - hit_minute) <= 3:
            matching.append(d)

    if not matching:
        return {"alignment": "pattern_only", "matched_decisions": 0}

    # Check if any heartbeat fired ENTER_BULL/ENTER_BEAR matching our bias
    for d in matching:
        action = d.get("action", "")
        if hit.bias == "bullish" and action == "ENTER_BULL":
            return {"alignment": "ALIGNED", "matched_action": action,
                    "matched_decisions": len(matching)}
        if hit.bias == "bearish" and action == "ENTER_BEAR":
            return {"alignment": "ALIGNED", "matched_action": action,
                    "matched_decisions": len(matching)}
        if (hit.bias == "bullish" and action == "ENTER_BEAR") or (
            hit.bias == "bearish" and action == "ENTER_BULL"
        ):
            return {"alignment": "DIVERGED", "matched_action": action,
                    "matched_decisions": len(matching)}

    # Heartbeat present but HOLD/HOLD_DEV/no_entry
    return {
        "alignment": "HEARTBEAT_MISS",
        "matched_action": matching[0].get("action", "UNKNOWN"),
        "matched_decisions": len(matching),
        "matched_bull_score": matching[0].get("bull_score"),
        "matched_bear_score": matching[0].get("bear_score"),
    }


def run_pattern_backtest(
    target_date: Date,
    csv_path: Path,
    prior_day_context: int = 1,
) -> dict:
    """Run all registered detectors against the target date and produce a scorecard.

    Args:
        target_date: trading date to analyze
        csv_path: master spy_5m CSV
        prior_day_context: number of prior trading days of RTH bars to load as
                           context (no detectors fire on them, but they extend
                           the trailing window so SMA50 / regime / level
                           lookback work from bar 0 of the target date).
                           Default 1 (= ~78 bars before target opens, sufficient
                           for SMA50 coverage from open).
    """
    bars, first_target_idx = _load_bars_for_date(csv_path, target_date,
                                                  prior_day_context=prior_day_context)
    decisions = _load_heartbeat_decisions(target_date)

    # Named ★★+ levels: try live key-levels.json first (today only), then
    # fall back to synthetic PDH/PDL/PDC/PDO for historical dates.
    named_levels = (
        _load_named_levels_from_keyjson(target_date)
        or _derive_named_levels(bars, first_target_idx)
    )

    if not bars:
        return {
            "date": target_date.isoformat(),
            "error": f"No bars found for {target_date} in {csv_path.name}",
            "bars_count": 0,
        }

    # Build the active detector set: base DETECTORS + named-level-keyed variants.
    # For each ★★+ level, add detector variants that use the named level as the
    # explicit support/resistance price (v2 override introduced 2026-05-20).
    # These fire only when price sweeps the exact named level, making them
    # directly comparable to what the heartbeat would see from key-levels.json.
    active_detectors: dict[str, Any] = dict(DETECTORS)
    for _lvl in named_levels:
        if _lvl.get("stars", 0) < 2:
            continue
        _lname = _lvl["name"].replace(" ", "_")
        _lprice = _lvl["price"]
        # Resolve level directionality.  Default "support" when "type" absent
        # (conservative: FBW-only, no spurious RAL on untyped levels).
        _lvl_type = _lvl.get("type", "support")
        # Bullish: failed_breakdown_wick keyed to this support level.
        # PDL → "support", reference levels fire both.
        if _lvl_type in ("support", "reference"):
            active_detectors[f"fbw_at_{_lname}"] = (
                lambda bars, p=_lprice: failed_breakdown_wick(bars, support_price=p)
            )
        # Bearish: rejection_at_level keyed to this resistance level.
        # PDH → "resistance", reference levels fire both.
        if _lvl_type in ("resistance", "reference"):
            active_detectors[f"ral_at_{_lname}"] = (
                lambda bars, p=_lprice: rejection_at_level(bars, resistance_price=p)
            )

    hits: list[dict] = []
    # disambiguated_hits: one-row-per-bar (instead of one-row-per-detector) where
    # conflicting hits got resolved via 50-bar regime trend.
    disambiguated_hits: list[dict] = []
    # Conflict ledger: bars where >=2 detectors fired opposite biases (regime
    # disambiguated). Tracks resolution + grade for the A/B improvement metric.
    conflicts: list[dict] = []

    # Walk forward: at each bar of the TARGET date, run each detector with
    # the trailing window (including prior-day context). Skip prior-day
    # context bars themselves — we only grade hits on target-date bars.
    start_walk = max(first_target_idx, 20)  # need at least 20 bars window for detectors
    for i in range(start_walk, len(bars)):
        window = bars[: i + 1]
        bar_hits: list[tuple[str, PatternHit]] = []  # (detector_name, hit) for this bar

        for det_name, det_fn in active_detectors.items():
            hit = det_fn(window)
            if hit is None:
                continue
            # Only record hits where the pattern COMPLETES on the current bar
            # (i.e., bar_index = len(window) - 1 in the window's frame)
            # The detector already returns absolute index in the bars passed in,
            # so just check it matches the latest bar.
            if hit.bar_index != i:
                continue
            # Enrich hit with named-level proximity before recording.
            # Populates notes["near_key_level"] (bool) + notes["nearest_key_level_name"]
            # / notes["nearest_key_level_distance"] when within $0.50 of a ★2+ level.
            # WATCH-ONLY per OP-21 — heartbeat integration requires Rule 9.
            hit = enrich_hit_with_proximity(hit, named_levels)
            bar_hits.append((det_name, hit))
            grade = _grade_hit(hit, bars)
            overlay = _heartbeat_overlay(hit, bars, decisions)
            regime = _regime_at_bar(bars, hit.bar_index, sma_lookback=50)
            named_lvl = _nearest_named_level(hit.key_price or bars[hit.bar_index].close,
                                              named_levels, max_distance=0.50)
            hits.append({
                "detector": det_name,
                "bar_index": hit.bar_index,
                "bar_time_et": bars[hit.bar_index].open_time.astimezone(
                    timezone(__import__("datetime").timedelta(hours=-4))
                ).strftime("%H:%M"),
                "bar_close": bars[hit.bar_index].close,
                "pattern": hit.pattern,
                "bias": hit.bias,
                "confidence": hit.confidence,
                "key_price": hit.key_price,
                "regime": regime,
                "regime_aligned": (
                    (regime == "uptrend" and hit.bias == "bullish")
                    or (regime == "downtrend" and hit.bias == "bearish")
                ),
                "nearest_named_level": named_lvl,
                # near_named_level and near_key_level are both proximity flags;
                # near_named_level is the dict-level field; near_key_level is
                # embedded in notes (via enrich_hit_with_proximity) for heartbeat use.
                "near_named_level": named_lvl is not None,
                "notes": hit.notes,  # notes["near_key_level"] is now populated
                "grade_next_bar": grade,
                "heartbeat_overlay": overlay,
            })

        # --- DISAMBIGUATION PASS ----------------------------------------------
        # If multiple detectors fired at this bar, resolve via regime + record
        # the resolution. If 0 or 1 fired, mirror the same row into the
        # disambiguated_hits list so apples-to-apples comparison stays clean.
        if not bar_hits:
            continue

        # SMA-20 = ~100 min trailing trend (single-day pattern_backtest only loads
        # RTH bars = max 78/day, so SMA50 would only fire after 12:40 ET).
        # SMA20 is the intraday-usable proxy; full SMA50 will be enabled when
        # _load_bars_for_date loads prior-day context bars (queued).
        regime = _regime_at_bar(bars, i, sma_lookback=20)
        all_hits = [h for _, h in bar_hits]
        biases_present = set(h.bias for h in all_hits)
        is_conflict = "bullish" in biases_present and "bearish" in biases_present

        # LOOKAHEAD-SAFE: only pass bars UP TO i so the disambiguator's SMA
        # uses trailing history (matching live behavior).
        winner = disambiguate_by_regime(all_hits, bars[: i + 1], sma_lookback=20)
        if winner is None:
            # Flat regime or insufficient bars; no disambiguated row
            if is_conflict:
                conflicts.append({
                    "bar_index": i,
                    "bar_time_et": bars[i].open_time.astimezone(
                        timezone(__import__("datetime").timedelta(hours=-4))
                    ).strftime("%H:%M"),
                    "regime": regime,
                    "candidates": [(d, h.pattern, h.bias, h.confidence) for d, h in bar_hits],
                    "resolution": "UNRESOLVED",
                    "grade_next_bar": None,
                })
            continue

        winner_grade = _grade_hit(winner, bars)
        winner_overlay = _heartbeat_overlay(winner, bars, decisions)
        disambiguated_hits.append({
            "bar_index": i,
            "bar_time_et": bars[i].open_time.astimezone(
                timezone(__import__("datetime").timedelta(hours=-4))
            ).strftime("%H:%M"),
            "bar_close": bars[i].close,
            "pattern": winner.pattern,
            "bias": winner.bias,
            "confidence": winner.confidence,
            "key_price": winner.key_price,
            "regime": regime,
            "regime_resolved": "regime_resolved" in winner.pattern,
            "rejected_pattern": winner.notes.get("rejected_pattern"),
            "rejected_bias": winner.notes.get("rejected_bias"),
            "grade_next_bar": winner_grade,
            "heartbeat_overlay": winner_overlay,
            "conflict_count": len(bar_hits),
        })

        if is_conflict:
            conflicts.append({
                "bar_index": i,
                "bar_time_et": bars[i].open_time.astimezone(
                    timezone(__import__("datetime").timedelta(hours=-4))
                ).strftime("%H:%M"),
                "regime": regime,
                "candidates": [(d, h.pattern, h.bias, h.confidence) for d, h in bar_hits],
                "resolution": f"{winner.bias.upper()} ({winner.pattern})",
                "rejected_pattern": winner.notes.get("rejected_pattern"),
                "grade_next_bar": winner_grade,
            })

    # Aggregate (use active_detectors which includes named-level-keyed variants)
    by_detector = {}
    for det_name in active_detectors:
        det_hits = [h for h in hits if h["detector"] == det_name]
        if not det_hits:
            by_detector[det_name] = {"hits": 0, "wins": 0, "losses": 0, "neutral": 0,
                                      "aligned": 0, "diverged": 0, "heartbeat_miss": 0,
                                      "pattern_only": 0, "win_rate_pct": None}
            continue
        wins = sum(1 for h in det_hits if h["grade_next_bar"] == "WIN")
        losses = sum(1 for h in det_hits if h["grade_next_bar"] == "LOSS")
        neutral = sum(1 for h in det_hits if h["grade_next_bar"] == "NEUTRAL")
        aligned = sum(1 for h in det_hits if h["heartbeat_overlay"]["alignment"] == "ALIGNED")
        diverged = sum(1 for h in det_hits if h["heartbeat_overlay"]["alignment"] == "DIVERGED")
        hb_miss = sum(1 for h in det_hits if h["heartbeat_overlay"]["alignment"] == "HEARTBEAT_MISS")
        pattern_only = sum(1 for h in det_hits if h["heartbeat_overlay"]["alignment"] == "pattern_only")
        graded = wins + losses
        by_detector[det_name] = {
            "hits": len(det_hits),
            "wins": wins,
            "losses": losses,
            "neutral": neutral,
            "aligned": aligned,
            "diverged": diverged,
            "heartbeat_miss": hb_miss,
            "pattern_only": pattern_only,
            "win_rate_pct": round(wins / graded * 100, 1) if graded > 0 else None,
        }

    # --- DISAMBIGUATED A/B SUMMARY -----------------------------------------
    # Compare RAW one-hit-per-detector outputs vs DISAMBIGUATED one-hit-per-bar
    # output. This is the headline number for the trend-aware fix.
    dh_wins = sum(1 for h in disambiguated_hits if h["grade_next_bar"] == "WIN")
    dh_losses = sum(1 for h in disambiguated_hits if h["grade_next_bar"] == "LOSS")
    dh_neutral = sum(1 for h in disambiguated_hits if h["grade_next_bar"] == "NEUTRAL")
    dh_graded = dh_wins + dh_losses
    dh_resolved = sum(1 for h in disambiguated_hits if h.get("regime_resolved"))

    # Conflict-only win rate: how often did the regime-resolved winner win
    conflict_resolved = [c for c in conflicts if c["resolution"] != "UNRESOLVED"]
    cr_wins = sum(1 for c in conflict_resolved if c.get("grade_next_bar") == "WIN")
    cr_losses = sum(1 for c in conflict_resolved if c.get("grade_next_bar") == "LOSS")
    cr_graded = cr_wins + cr_losses

    disambiguated_summary = {
        "total_disambiguated_hits": len(disambiguated_hits),
        "wins": dh_wins,
        "losses": dh_losses,
        "neutral": dh_neutral,
        "win_rate_pct": round(dh_wins / dh_graded * 100, 1) if dh_graded > 0 else None,
        "regime_resolved_count": dh_resolved,  # subset where regime had to break a tie
        "conflicts_total": len(conflicts),
        "conflicts_resolved": len(conflict_resolved),
        "conflicts_unresolved_flat": len(conflicts) - len(conflict_resolved),
        "conflict_resolution_win_rate_pct": (
            round(cr_wins / cr_graded * 100, 1) if cr_graded > 0 else None
        ),
    }

    # Determine source label: archive > live > synthetic
    _archive_p = PROJECT_ROOT / "journal" / "key-levels-archive" / f"key-levels-{target_date.isoformat()}.json"
    _live_p = PROJECT_ROOT / "automation" / "state" / "key-levels.json"
    if _archive_p.exists():
        kl_source = "archive"
    elif _live_p.exists() and _load_named_levels_from_keyjson(target_date) is not None:
        kl_source = "live"
    else:
        kl_source = "synthetic_pdh_pdl"
    return {
        "date": target_date.isoformat(),
        "csv_source": str(csv_path),
        "bars_count": len(bars),
        "named_levels_count": len(named_levels),
        "named_levels_source": kl_source,
        "heartbeat_decisions_count": len(decisions),
        "detectors_run": list(active_detectors.keys()),
        "named_level_detectors_count": len(active_detectors) - len(DETECTORS),
        "summary_by_detector": by_detector,
        "disambiguated_summary": disambiguated_summary,
        "total_hits": len(hits),
        "hits": hits,
        "disambiguated_hits": disambiguated_hits,
        "conflicts": conflicts,
    }


def _write_markdown(result: dict, out_path: Path) -> None:
    """Render a human-readable summary."""
    lines = [
        f"# Pattern Backtest -- {result['date']}",
        "",
        f"- bars: {result.get('bars_count', 0)}",
        f"- heartbeat decisions logged: {result.get('heartbeat_decisions_count', 0)}",
        f"- detectors run: {', '.join(result.get('detectors_run', []))}",
        f"- total pattern hits: {result.get('total_hits', 0)}",
        "",
        "## Summary by detector",
        "",
        "| Detector | Hits | Wins | Losses | WR % | Aligned w/ HB | Diverged | HB Miss (HOLD) | Pattern-only |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for det, stats in result.get("summary_by_detector", {}).items():
        wr = f"{stats['win_rate_pct']}" if stats.get("win_rate_pct") is not None else "n/a"
        lines.append(
            f"| {det} | {stats['hits']} | {stats['wins']} | {stats['losses']} | "
            f"{wr} | {stats['aligned']} | {stats['diverged']} | "
            f"{stats['heartbeat_miss']} | {stats['pattern_only']} |"
        )

    if result.get("hits"):
        lines.extend(["", "## Hits detail", ""])
        for h in result["hits"][:50]:  # cap to first 50 to keep doc readable
            ov = h["heartbeat_overlay"]
            lines.append(
                f"- **{h['bar_time_et']}** {h['pattern']} "
                f"({h['bias']}, conf {h['confidence']}) @ close ${h['bar_close']:.2f} -- "
                f"grade: **{h['grade_next_bar']}** -- heartbeat: **{ov['alignment']}**"
            )

    out_path.write_text("\n".join(lines), encoding="utf-8")


def _aggregate_range(per_day_results: list[dict]) -> dict:
    """Aggregate per-day results into a multi-day scorecard."""
    by_detector: dict[str, dict] = {}
    total_days = len(per_day_results)
    days_with_hits = 0
    total_hits = 0
    all_confidences: list[float] = []

    for day in per_day_results:
        if day.get("total_hits", 0) > 0:
            days_with_hits += 1
        total_hits += day.get("total_hits", 0)
        for hit in day.get("hits", []):
            all_confidences.append(hit["confidence"])
        for det, stats in day.get("summary_by_detector", {}).items():
            if det not in by_detector:
                by_detector[det] = {"hits": 0, "wins": 0, "losses": 0, "neutral": 0,
                                     "aligned": 0, "diverged": 0, "heartbeat_miss": 0,
                                     "pattern_only": 0}
            by_detector[det]["hits"] += stats["hits"]
            by_detector[det]["wins"] += stats["wins"]
            by_detector[det]["losses"] += stats["losses"]
            by_detector[det]["neutral"] += stats["neutral"]
            by_detector[det]["aligned"] += stats["aligned"]
            by_detector[det]["diverged"] += stats["diverged"]
            by_detector[det]["heartbeat_miss"] += stats["heartbeat_miss"]
            by_detector[det]["pattern_only"] += stats["pattern_only"]

    # Compute WR per detector
    for det, stats in by_detector.items():
        graded = stats["wins"] + stats["losses"]
        stats["win_rate_pct"] = round(stats["wins"] / graded * 100, 1) if graded > 0 else None

    # Confidence-band WR analysis (helps tune thresholds)
    conf_bands = {"<0.60": [], "0.60-0.70": [], "0.70-0.80": [], "0.80+": []}
    for day in per_day_results:
        for hit in day.get("hits", []):
            c = hit["confidence"]
            grade = hit["grade_next_bar"]
            if grade == "NEUTRAL":
                continue
            if c < 0.60:
                conf_bands["<0.60"].append(grade)
            elif c < 0.70:
                conf_bands["0.60-0.70"].append(grade)
            elif c < 0.80:
                conf_bands["0.70-0.80"].append(grade)
            else:
                conf_bands["0.80+"].append(grade)
    conf_band_stats = {}
    for band, grades in conf_bands.items():
        if not grades:
            conf_band_stats[band] = {"n": 0, "wr_pct": None}
            continue
        wins = sum(1 for g in grades if g == "WIN")
        conf_band_stats[band] = {
            "n": len(grades),
            "wins": wins,
            "losses": len(grades) - wins,
            "wr_pct": round(wins / len(grades) * 100, 1),
        }

    # Regime-aligned WR analysis (per detector × regime alignment)
    # FIXED 2026-05-18 v2: hits with regime="unknown" (bar < SMA50 lookback)
    # were previously misclassified as regime_contrary. They are now in their
    # own bucket ("regime_unknown") so the +contra-edge measurement is clean.
    regime_breakdown: dict = {}
    for day in per_day_results:
        for hit in day.get("hits", []):
            grade = hit["grade_next_bar"]
            if grade == "NEUTRAL":
                continue
            det = hit["detector"]
            regime = hit.get("regime", "unknown")
            if regime not in ("uptrend", "downtrend"):
                bucket = "regime_unknown"
            elif hit.get("regime_aligned", False):
                bucket = "regime_aligned"
            else:
                bucket = "regime_contrary"
            key = (det, bucket)
            if key not in regime_breakdown:
                regime_breakdown[key] = {"n": 0, "wins": 0, "losses": 0}
            regime_breakdown[key]["n"] += 1
            if grade == "WIN":
                regime_breakdown[key]["wins"] += 1
            else:
                regime_breakdown[key]["losses"] += 1
    regime_breakdown_serializable = {}
    for (det, align_tag), stats in regime_breakdown.items():
        key_str = f"{det}::{align_tag}"
        stats["wr_pct"] = round(stats["wins"] / stats["n"] * 100, 1) if stats["n"] > 0 else None
        regime_breakdown_serializable[key_str] = stats

    # --- DISAMBIGUATED A/B AGGREGATE -----------------------------------------
    # Roll up the disambiguated_summary across all days for headline comparison.
    dis_total = sum(d.get("disambiguated_summary", {}).get("total_disambiguated_hits", 0)
                    for d in per_day_results)
    dis_wins = sum(d.get("disambiguated_summary", {}).get("wins", 0) for d in per_day_results)
    dis_losses = sum(d.get("disambiguated_summary", {}).get("losses", 0) for d in per_day_results)
    dis_neutral = sum(d.get("disambiguated_summary", {}).get("neutral", 0) for d in per_day_results)
    dis_resolved = sum(d.get("disambiguated_summary", {}).get("regime_resolved_count", 0)
                       for d in per_day_results)
    dis_conflicts = sum(d.get("disambiguated_summary", {}).get("conflicts_total", 0)
                        for d in per_day_results)
    dis_conflicts_resolved = sum(
        d.get("disambiguated_summary", {}).get("conflicts_resolved", 0) for d in per_day_results
    )
    dis_graded = dis_wins + dis_losses

    # Conflict-only roll-up: WR among bars where the engine WOULD have been
    # confused without disambiguation
    conflict_resolved_grades: list[str] = []
    for day in per_day_results:
        for c in day.get("conflicts", []):
            if c.get("resolution") == "UNRESOLVED":
                continue
            g = c.get("grade_next_bar")
            if g in ("WIN", "LOSS"):
                conflict_resolved_grades.append(g)
    cr_wins = sum(1 for g in conflict_resolved_grades if g == "WIN")
    cr_n = len(conflict_resolved_grades)

    # Compute the RAW (one-row-per-detector) overall WR for direct comparison
    raw_total_wins = sum(s["wins"] for s in by_detector.values())
    raw_total_losses = sum(s["losses"] for s in by_detector.values())
    raw_graded = raw_total_wins + raw_total_losses
    raw_wr = round(raw_total_wins / raw_graded * 100, 1) if raw_graded > 0 else None
    dis_wr = round(dis_wins / dis_graded * 100, 1) if dis_graded > 0 else None

    # Named-level proximity breakdown (Option D 2026-05-18)
    named_level_breakdown: dict[str, dict[str, int]] = {}
    for day in per_day_results:
        for hit in day.get("hits", []):
            grade = hit["grade_next_bar"]
            if grade == "NEUTRAL":
                continue
            det = hit["detector"]
            near = hit.get("near_named_level", False)
            key = f"{det}::{'near_named' if near else 'no_named'}"
            named_level_breakdown.setdefault(key, {"n": 0, "wins": 0, "losses": 0})
            named_level_breakdown[key]["n"] += 1
            if grade == "WIN":
                named_level_breakdown[key]["wins"] += 1
            else:
                named_level_breakdown[key]["losses"] += 1
    for k, s in named_level_breakdown.items():
        s["wr_pct"] = round(s["wins"] / s["n"] * 100, 1) if s["n"] > 0 else None

    return {
        "total_days_scanned": total_days,
        "days_with_hits": days_with_hits,
        "total_hits": total_hits,
        "summary_by_detector": by_detector,
        "confidence_band_wr": conf_band_stats,
        "regime_breakdown": regime_breakdown_serializable,
        "named_level_breakdown": named_level_breakdown,
        "disambiguated_summary": {
            "total_disambiguated_hits": dis_total,
            "wins": dis_wins,
            "losses": dis_losses,
            "neutral": dis_neutral,
            "win_rate_pct": dis_wr,
            "regime_resolved_count": dis_resolved,
            "conflicts_total": dis_conflicts,
            "conflicts_resolved": dis_conflicts_resolved,
            "conflicts_unresolved_flat": dis_conflicts - dis_conflicts_resolved,
            "conflict_resolution_n": cr_n,
            "conflict_resolution_wr_pct": (
                round(cr_wins / cr_n * 100, 1) if cr_n > 0 else None
            ),
        },
        "ab_comparison": {
            "raw_wr_pct": raw_wr,
            "raw_graded_n": raw_graded,
            "disambiguated_wr_pct": dis_wr,
            "disambiguated_graded_n": dis_graded,
            "wr_delta_pp": (round(dis_wr - raw_wr, 1) if (raw_wr is not None and dis_wr is not None) else None),
            "conflict_only_wr_pct": (
                round(cr_wins / cr_n * 100, 1) if cr_n > 0 else None
            ),
            "conflict_only_n": cr_n,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Single date YYYY-MM-DD")
    parser.add_argument("--range", nargs=2, metavar=("START", "END"),
                        help="Batch mode: scan all trading days in [START, END]")
    parser.add_argument(
        "--csv",
        default=None,
        help="Path to spy_5m CSV. Auto-detected from most recent file covering --date if omitted.",
    )
    args = parser.parse_args()

    if not args.date and not args.range:
        print("ERROR: must specify either --date or --range START END", file=sys.stderr)
        return 1

    # === BATCH MODE ===
    if args.range:
        start = Date.fromisoformat(args.range[0])
        end = Date.fromisoformat(args.range[1])
        if end < start:
            print(f"ERROR: end ({end}) before start ({start})", file=sys.stderr)
            return 1

        per_day: list[dict] = []
        from datetime import timedelta as _td
        cur = start
        skipped_no_data = 0
        while cur <= end:
            # Only weekdays
            if cur.weekday() < 5:
                csv_path = Path(args.csv) if args.csv else _autodetect_csv(cur)
                if csv_path and csv_path.exists():
                    result = run_pattern_backtest(cur, csv_path)
                    if result.get("bars_count", 0) > 0:
                        per_day.append(result)
                    else:
                        skipped_no_data += 1
                else:
                    skipped_no_data += 1
            cur += _td(days=1)

        agg = _aggregate_range(per_day)
        out = {
            "range_start": start.isoformat(),
            "range_end": end.isoformat(),
            "days_with_data": len(per_day),
            "days_skipped_no_data": skipped_no_data,
            "aggregate": agg,
        }

        analysis_dir = PROJECT_ROOT / "analysis"
        analysis_dir.mkdir(exist_ok=True)
        json_path = analysis_dir / f"pattern-backtest-range-{start.isoformat()}-to-{end.isoformat()}.json"
        json_path.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")

        print(f"\n=== Pattern Backtest Range -- {start} to {end} ===")
        print(f"  days with data:    {len(per_day)}")
        print(f"  days skipped:      {skipped_no_data}")
        print(f"  days with hits:    {agg['days_with_hits']}")
        print(f"  total hits:        {agg['total_hits']}")
        print(f"")
        print(f"  Per-detector aggregate:")
        for det, stats in agg["summary_by_detector"].items():
            wr = f"{stats['win_rate_pct']}%" if stats.get("win_rate_pct") is not None else "n/a"
            print(f"    {det:32s}: {stats['hits']:4d} hits | {stats['wins']:3d}W/{stats['losses']:3d}L ({wr})")
        print(f"")
        print(f"  Confidence-band WR (calibration check):")
        for band, stats in agg["confidence_band_wr"].items():
            if stats["n"] == 0:
                print(f"    {band:12s}: n=0")
                continue
            print(f"    {band:12s}: n={stats['n']:4d} | {stats['wins']:3d}W/{stats['losses']:3d}L = {stats['wr_pct']}%")
        print(f"")
        print(f"  Regime-aligned WR (does pattern bias match SPY 50-bar trend?):")
        rb = agg.get("regime_breakdown", {})
        for key in sorted(rb.keys()):
            stats = rb[key]
            wr = f"{stats['wr_pct']}%" if stats.get("wr_pct") is not None else "n/a"
            print(f"    {key:50s}: n={stats['n']:4d} | {stats['wins']:3d}W/{stats['losses']:3d}L = {wr}")
        print(f"\n  json: {json_path}")
        return 0

    # === SINGLE-DATE MODE ===
    target_date = Date.fromisoformat(args.date)

    csv_path = Path(args.csv) if args.csv else _autodetect_csv(target_date)
    if not csv_path or not csv_path.exists():
        print(f"ERROR: CSV not found at {csv_path}", file=sys.stderr)
        return 1

    result = run_pattern_backtest(target_date, csv_path)

    analysis_dir = PROJECT_ROOT / "analysis"
    analysis_dir.mkdir(exist_ok=True)
    json_path = analysis_dir / f"pattern-backtest-{target_date.isoformat()}.json"
    md_path = analysis_dir / f"pattern-backtest-{target_date.isoformat()}.md"

    json_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    _write_markdown(result, md_path)

    print(f"\n=== Pattern Backtest -- {target_date} ===")
    print(f"  bars: {result.get('bars_count', 0)}")
    print(f"  heartbeat decisions: {result.get('heartbeat_decisions_count', 0)}")
    print(f"  total hits: {result.get('total_hits', 0)}")
    for det, stats in result.get("summary_by_detector", {}).items():
        wr = f"{stats['win_rate_pct']}%" if stats.get("win_rate_pct") is not None else "n/a"
        print(f"  {det}: {stats['hits']} hits | {stats['wins']}W/{stats['losses']}L "
              f"({wr}) | aligned={stats['aligned']} diverged={stats['diverged']} "
              f"miss={stats['heartbeat_miss']} pattern_only={stats['pattern_only']}")
    print(f"\n  json: {json_path}")
    print(f"  md:   {md_path}")
    return 0


def _autodetect_csv(target_date: Date) -> Path | None:
    """Find the most recent SPY 5m CSV that covers the target_date."""
    data_dir = PROJECT_ROOT / "backtest" / "data"
    candidates = []
    for p in data_dir.glob("spy_5m_*.csv"):
        # Filename pattern: spy_5m_<start>_<end>.csv
        parts = p.stem.split("_")
        if len(parts) >= 4:
            try:
                start = Date.fromisoformat(parts[2])
                end = Date.fromisoformat(parts[3])
                if start <= target_date <= end:
                    candidates.append((end, p))
            except ValueError:
                continue
    if not candidates:
        return None
    # Return the one with the latest end-date (most recent data)
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


if __name__ == "__main__":
    sys.exit(main())

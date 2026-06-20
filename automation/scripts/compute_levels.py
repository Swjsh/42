"""Compute the comprehensive key-levels set for tomorrow's premarket.

Pulls together:
  - Carry-over Active levels from existing key-levels.json (with role/bounce_history preserved)
  - Floor Trader Pivot Points (P, R1-R3, S1-S3) from prior-day RTH HLC
  - Today's RTH session high/low (promoted to Active for tomorrow)
  - Today's premarket high/low (PMH/PML)
  - Multi-day swing highs/lows (5-day rolling RTH H/L)
  - Round-number psychological levels near spot
  - Volume Profile POC/VAH/VAL (if Pine output available — read by ui_evaluate)
  - Anchored VWAP from yesterday's session low
  - Per-level strength scoring (★/★★/★★★) + confluence detection
  - Distance-from-spot filter (≤ $5 unless Carry/Reference tier)
  - Hypothesis-grade integration (level prior from prior predictions)

Writes:
  - automation/state/key-levels.json (fresh schema with strength + confluence)

Usage:
    python automation/scripts/compute_levels.py
    python automation/scripts/compute_levels.py --target-date 2026-05-09
    python automation/scripts/compute_levels.py --spot 737.54

Run from premarket task at 08:30 ET. The output is read by heartbeat for
trigger anchoring + by the dashboard for level visualization.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from dataclasses import asdict
from pathlib import Path

import pandas as pd
import pytz

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "backtest"))

from lib.level_strength import (  # noqa: E402
    floor_trader_pivots,
    opening_range,
    count_touches,
    score_level,
    find_confluences,
    filter_by_distance,
    compute_vwap,
    compute_volume_profile,
)
from lib.levels import _detect_from_history  # noqa: E402

ET = pytz.timezone("America/New_York")
STATE_DIR = REPO_ROOT / "automation" / "state"
DATA_DIR = REPO_ROOT / "backtest" / "data"

# Config — calibrated for chart clarity (target: 6-10 levels visible, not 24)
ROUND_NUMBER_RADIUS_USD = 2.0          # Only round numbers within ±$2 of spot
ROUND_NUMBER_INCREMENTS = [5.0]         # $5-increment only ($740, $735) — $1 increments are noise
DISTANCE_LIMIT_USD = 5.0
KEEP_TIERS_REGARDLESS = ("Carry",)      # Reference levels are now distance-filtered too
PIVOT_LEVELS_TO_EMIT = ("P", "R1", "S1")  # Only emit P/R1/S1, drop R2/R3/S2/S3 unless near spot
PIVOT_DISTANCE_LIMIT = 3.0              # Pivots must be within ±$3 to be drawn
TOUCH_TOLERANCE_USD = 0.05              # Tighter — bars routinely graze ±$0.10
ROUND_NUMBER_MAX_STARS = 1              # Round numbers cap at ★ unless confluent


# ---------------------------------------------------------------------------
# Bar loading
# ---------------------------------------------------------------------------

def _load_spy_bars() -> pd.DataFrame:
    """Load latest SPY 5m CSV with mixed-format timestamp parsing."""
    candidates = sorted(DATA_DIR.glob("spy_5m_*.csv"))
    if not candidates:
        raise FileNotFoundError("No SPY 5m CSV found")
    df = pd.read_csv(candidates[-1])
    df["timestamp_et"] = df["timestamp_et"].astype(str).str.replace("T", " ", regex=False)
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp_et"]).reset_index(drop=True)
    df["timestamp_et"] = df["timestamp_et"].dt.tz_convert(ET).dt.tz_localize(None)
    df["date"] = df["timestamp_et"].dt.date
    return df


def _rth_only(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        (df["timestamp_et"].dt.time >= dt.time(9, 30))
        & (df["timestamp_et"].dt.time < dt.time(16, 0))
    ].reset_index(drop=True)


def _premarket_only(df: pd.DataFrame, target_date: dt.date) -> pd.DataFrame:
    return df[
        (df["date"] == target_date)
        & (df["timestamp_et"].dt.time < dt.time(9, 30))
    ].reset_index(drop=True)


# ---------------------------------------------------------------------------
# Level construction helpers
# ---------------------------------------------------------------------------

def _make_level(
    price: float,
    type_: str,
    tier: str,
    source: str,
    reasoning: str,
    color: str,
    style: str,
    entity_id: str | None = None,
    role: str | None = None,
    bounce_history: list | None = None,
    respect_count: int = 0,
    broken_count: int = 0,
    strength: dict | None = None,
    extra: dict | None = None,
) -> dict:
    now_iso = dt.datetime.now(ET).isoformat()
    expires_days = {"Active": 1, "Carry": 5, "Reference": 30, "Liquidity": 1}.get(tier, 1)
    expires = (dt.datetime.now(ET) + dt.timedelta(days=expires_days)).isoformat()
    lv = {
        "price": round(float(price), 4),
        "type": type_,
        "tier": tier,
        "source": source,
        "reasoning": reasoning,
        "verified_at": now_iso,
        "expires_at": expires,
        "color": color,
        "style": style,
        "entity_id": entity_id,
        "draw_needed": entity_id is None,
        "respect_count": respect_count,
        "broken_count": broken_count,
        "role": role,
        "bounce_history": bounce_history or [],
        "strength": strength or {},
    }
    if extra:
        lv.update(extra)
    return lv


# ---------------------------------------------------------------------------
# Component builders — each returns a list of level dicts
# ---------------------------------------------------------------------------

def _carry_over_levels(existing: list[dict]) -> list[dict]:
    """Pass through existing Carry/Reference levels (the deep anchors)."""
    out = []
    for lv in existing or []:
        if lv.get("tier") in ("Carry", "Reference"):
            new = dict(lv)
            new["respect_count"] = lv.get("respect_count", 0)
            new["broken_count"] = lv.get("broken_count", 0)
            out.append(new)
    return out


def _prior_day_rth_levels(prior_rth: pd.DataFrame, prior_date: dt.date) -> list[dict]:
    """PDH / PDL / PDC from prior session's RTH bars only."""
    if prior_rth.empty:
        return []
    pdh = float(prior_rth["high"].max())
    pdl = float(prior_rth["low"].min())
    pdc = float(prior_rth["close"].iloc[-1])
    src_prefix = f"{prior_date.isoformat()} RTH"
    return [
        _make_level(
            price=pdh, type_="resistance", tier="Active",
            source=f"{src_prefix} session high (RTH-only — premarket spikes excluded)",
            reasoning="Prior-day RTH high acts as resistance until reclaimed.",
            color="#ef4444", style="solid",
        ),
        _make_level(
            price=pdl, type_="support", tier="Active",
            source=f"{src_prefix} session low (RTH-only)",
            reasoning="Prior-day RTH low acts as support until broken.",
            color="#22c55e", style="solid",
        ),
        _make_level(
            price=pdc, type_="support", tier="Active",
            source=f"{src_prefix} closing price",
            reasoning="Prior-day close — opening reference for gap measurement.",
            color="#3b82f6", style="dashed",
        ),
    ]


def _pivot_levels(prior_rth: pd.DataFrame, prior_date: dt.date, spot: float) -> list[dict]:
    """Floor Trader Pivot Points — emit only P/R1/S1, only within ±$3 of spot.

    R2/R3/S2/S3 are kept in-memory but only emitted on extreme-volatility days
    (where the full range projects within $5). This keeps the chart from being
    flooded with 7 extra dotted lines every day.
    """
    if prior_rth.empty:
        return []
    pdh = float(prior_rth["high"].max())
    pdl = float(prior_rth["low"].min())
    pdc = float(prior_rth["close"].iloc[-1])
    pivots = floor_trader_pivots(pdh, pdl, pdc)
    src = f"Floor Trader Pivot from {prior_date.isoformat()} RTH HLC ({pdh:.2f}/{pdl:.2f}/{pdc:.2f})"
    out = []
    for label, price in pivots.as_list():
        # Only emit P/R1/S1 by default; outer pivots (R2/R3/S2/S3) require closer proximity
        if label not in PIVOT_LEVELS_TO_EMIT:
            if abs(price - spot) > PIVOT_DISTANCE_LIMIT:
                continue
        if abs(price - spot) > DISTANCE_LIMIT_USD:
            continue
        is_pivot = (label == "P")
        is_resistance = label.startswith("R")
        out.append(_make_level(
            price=price, type_="psychological",
            tier="Reference",
            source=src,
            reasoning=f"Floor trader {label} pivot — {'center' if is_pivot else ('resistance' if is_resistance else 'support')}.",
            color="#a855f7" if is_pivot else ("#ef4444" if is_resistance else "#22c55e"),
            style="dotted",
            extra={"pivot_label": label, "is_pivot_point": True},
        ))
    return out


def _todays_session_extremes(today_rth: pd.DataFrame, today_date: dt.date) -> list[dict]:
    """Today's RTH session high and low — promoted to Active for tomorrow's premarket."""
    if today_rth.empty:
        return []
    h = float(today_rth["high"].max())
    l = float(today_rth["low"].min())
    return [
        _make_level(
            price=h, type_="resistance", tier="Active",
            source=f"{today_date.isoformat()} RTH session high",
            reasoning="Today's session high — fresh resistance for tomorrow's open.",
            color="#ef4444", style="solid",
        ),
        _make_level(
            price=l, type_="support", tier="Active",
            source=f"{today_date.isoformat()} RTH session low",
            reasoning="Today's session low — fresh support for tomorrow's open.",
            color="#22c55e", style="solid",
        ),
    ]


def _premarket_extremes(today_premarket: pd.DataFrame, today_date: dt.date) -> list[dict]:
    """Premarket high/low for today — context only, may overlap RTH levels."""
    if today_premarket.empty:
        return []
    pmh = float(today_premarket["high"].max())
    pml = float(today_premarket["low"].min())
    return [
        _make_level(
            price=pmh, type_="resistance", tier="Active",
            source=f"{today_date.isoformat()} premarket high (04:00–09:30 ET)",
            reasoning="Premarket high — overshoot can become resistance.",
            color="#f97316", style="dashed",
        ),
        _make_level(
            price=pml, type_="support", tier="Active",
            source=f"{today_date.isoformat()} premarket low",
            reasoning="Premarket low — undershoot can become support.",
            color="#f97316", style="dashed",
        ),
    ]


def _round_numbers_near_spot(spot: float, radius_usd: float = ROUND_NUMBER_RADIUS_USD) -> list[dict]:
    """Round-number psychological levels — $5-increment only, ±$2 from spot.

    Per operating principle 5 (round numbers are awareness-only, low weight).
    They serve as visual anchors when price is approaching them, NOT as
    independent levels worth their own line. The dedupe step will collapse them
    into nearby chart-structural levels via confluence.
    """
    out = []
    for inc in ROUND_NUMBER_INCREMENTS:
        lower = int((spot - radius_usd) // inc) * inc
        upper = int((spot + radius_usd) // inc) * inc + inc
        v = lower
        while v <= upper:
            if abs(v - spot) <= radius_usd:
                out.append(_make_level(
                    price=v, type_="psychological", tier="Reference",
                    source=f"Round number ${v:.0f} (${inc:.0f}-increment)",
                    reasoning="Round-number magnet — awareness only, capped at ★ unless confluent.",
                    color="#94a3b8", style="dotted",
                    extra={"is_round_number": True},
                ))
            v += inc
    return out


def _vwap_levels(today_rth: pd.DataFrame, today_date: dt.date, spot: float) -> list[dict]:
    """Compute today's VWAP + ±1σ bands. Tagged as Liquidity tier.

    Only emit if within ±$5 of spot (anchored VWAP from today's open is always
    near spot, so this filter rarely kicks in for the main VWAP — but the ±2σ
    bands can be far on volatile days).
    """
    if today_rth.empty:
        return []
    snap = compute_vwap(today_rth)
    if snap is None:
        return []
    levels = []
    for label, price, role in [
        ("VWAP", snap.vwap, "support"),
        ("VWAP+1σ", snap.upper_1sigma, "resistance"),
        ("VWAP-1σ", snap.lower_1sigma, "support"),
    ]:
        if abs(price - spot) > DISTANCE_LIMIT_USD:
            continue
        levels.append(_make_level(
            price=price, type_="psychological", tier="Reference",
            source=f"{label} from {today_date.isoformat()} RTH bars",
            reasoning=f"{label} — institutional fair-value benchmark, dynamic.",
            color="#a855f7" if label == "VWAP" else "#94a3b8",
            style="dashed",
            extra={"is_vwap": True, "vwap_label": label, "vwap_bars": snap.bars_in_calc},
        ))
    return levels


def _volume_profile_levels(today_rth: pd.DataFrame, today_date: dt.date, spot: float) -> list[dict]:
    """Compute POC/VAH/VAL from today's RTH bars. Tagged as Liquidity tier."""
    if today_rth.empty:
        return []
    vp = compute_volume_profile(today_rth, bucket_size_usd=0.10, value_area_pct=0.70)
    if vp is None:
        return []
    levels = []
    for label, price, type_, color in [
        ("POC", vp.poc, "support", "#f59e0b"),     # amber
        ("VAH", vp.vah, "resistance", "#ef4444"),
        ("VAL", vp.val, "support", "#22c55e"),
    ]:
        if abs(price - spot) > DISTANCE_LIMIT_USD:
            continue
        levels.append(_make_level(
            price=price, type_=type_, tier="Liquidity",
            source=f"Volume Profile {label} from {today_date.isoformat()} RTH",
            reasoning=f"VP {label} — {'point of control' if label == 'POC' else 'value area boundary'}, magnet for tomorrow.",
            color=color, style="dashed",
            extra={"is_volume_profile": True, "vp_label": label,
                   "total_volume": round(vp.total_volume, 0)},
        ))
    return levels


def _anchored_vwap_levels(spy_full: pd.DataFrame, today_date: dt.date, spot: float) -> list[dict]:
    """Anchored VWAP from yesterday's session low — dynamic support reference."""
    available_dates = sorted(spy_full["date"].unique())
    prior_dates = [d for d in available_dates if d < today_date]
    if not prior_dates:
        return []
    prior = prior_dates[-1]
    prior_rth = spy_full[
        (spy_full["date"] == prior)
        & (spy_full["timestamp_et"].dt.time >= dt.time(9, 30))
        & (spy_full["timestamp_et"].dt.time < dt.time(16, 0))
    ]
    if prior_rth.empty:
        return []
    # Anchor at the low bar of prior day's RTH
    low_idx = int(prior_rth["low"].idxmin())
    anchor_ts = prior_rth.loc[low_idx, "timestamp_et"]
    # All bars from anchor onward
    from_anchor = spy_full[spy_full["timestamp_et"] >= anchor_ts]
    snap = compute_vwap(from_anchor)
    if snap is None:
        return []
    if abs(snap.vwap - spot) > DISTANCE_LIMIT_USD:
        return []
    return [_make_level(
        price=snap.vwap, type_="psychological", tier="Reference",
        source=f"Anchored VWAP from {prior.isoformat()} session low at {anchor_ts.strftime('%H:%M')} ET",
        reasoning="AVWAP from prior swing low — institutional algo benchmark.",
        color="#06b6d4", style="dashed",  # cyan
        extra={"is_anchored_vwap": True, "anchor_ts": str(anchor_ts), "avwap_bars": snap.bars_in_calc},
    )]


def _multi_day_swings(prior_rth_5d: pd.DataFrame, today_date: dt.date) -> list[dict]:
    """5-day rolling RTH high/low — Carry tier."""
    if prior_rth_5d.empty:
        return []
    h = float(prior_rth_5d["high"].max())
    l = float(prior_rth_5d["low"].min())
    return [
        _make_level(
            price=h, type_="resistance", tier="Carry",
            source=f"5-day rolling RTH high ending {today_date.isoformat()}",
            reasoning="Multi-day swing high — relevant if today's range expands.",
            color="#ef4444", style="dashed",
        ),
        _make_level(
            price=l, type_="support", tier="Carry",
            source=f"5-day rolling RTH low ending {today_date.isoformat()}",
            reasoning="Multi-day swing low — deep target if support cascades break.",
            color="#22c55e", style="dashed",
        ),
    ]


# ---------------------------------------------------------------------------
# Strength scoring + confluence over the merged level set
# ---------------------------------------------------------------------------

def _score_levels(
    levels: list[dict],
    spy_5m_full: pd.DataFrame,
    today_date: dt.date,
    avg_5m_volume: float,
) -> list[dict]:
    """Compute touch_count, recency, mtf, volume, strength for each level.

    Touch counting is **RTH-only** (premarket bars don't count) and uses tighter
    tolerance ($0.05) so transient grazes don't count as touches.
    """
    cutoff_date = today_date - dt.timedelta(days=30)
    rth_history = _rth_only(spy_5m_full[spy_5m_full["date"] >= cutoff_date])

    out = []
    for lv in levels:
        price = float(lv["price"])
        stats = count_touches(rth_history, level_price=price, tolerance_usd=TOUCH_TOLERANCE_USD)
        recency_days = None
        if stats.last_touched_at is not None:
            recency_days = (dt.datetime.combine(today_date, dt.time(0, 0)) - stats.last_touched_at).total_seconds() / 86400.0
            recency_days = max(0.0, recency_days)
        mtf_agreement = 2 if lv.get("tier") in ("Carry", "Reference") else 1
        components = score_level(
            touch_count=stats.touch_count,
            recency_days=recency_days,
            mtf_agreement=mtf_agreement,
            volume_at_touches=stats.volume_at_touches,
            avg_volume=avg_5m_volume,
        )
        new_lv = dict(lv)
        new_lv["touch_count"] = stats.touch_count
        new_lv["held_count"] = stats.held_count
        new_lv["broken_count"] = max(stats.broken_count, lv.get("broken_count", 0))
        new_lv["volume_at_touches"] = round(stats.volume_at_touches, 0)
        new_lv["last_touched_at"] = stats.last_touched_at.isoformat() if stats.last_touched_at else None
        new_lv["recency_days"] = round(recency_days, 2) if recency_days is not None else None
        new_lv["mtf_agreement"] = mtf_agreement

        stars = components.stars()
        # Cap round numbers at ROUND_NUMBER_MAX_STARS unless confluent (handled later)
        if lv.get("is_round_number") and stars > ROUND_NUMBER_MAX_STARS:
            stars = ROUND_NUMBER_MAX_STARS
        # Pivot points cap at 2 stars unless confluent — they're conventional, not chart-validated
        if lv.get("is_pivot_point") and stars > 2:
            stars = 2

        new_lv["strength"] = {
            "stars": stars,
            "points": components.total_points(),
            "components": asdict(components),
        }
        out.append(new_lv)
    return out


def _annotate_confluence(levels: list[dict]) -> list[dict]:
    """Find confluences and bump strength score for confluent levels."""
    levels_with_id = [{**lv, "_temp_id": str(i)} for i, lv in enumerate(levels)]
    groups = find_confluences(
        levels_with_id, proximity_usd=0.30,
        price_key="price", id_key="_temp_id",
    )
    for g in groups:
        for tid in g.member_ids:
            idx = int(tid)
            levels_with_id[idx]["confluence_center"] = round(g.center_price, 4)
            levels_with_id[idx]["confluence_member_count"] = len(g.member_ids)
            # Re-score with confluence bonus
            comps = levels_with_id[idx]["strength"]["components"]
            comps["confluence_score"] = 1
            new_pts = sum(comps.values())
            levels_with_id[idx]["strength"]["points"] = new_pts
            if new_pts >= 5:
                levels_with_id[idx]["strength"]["stars"] = 3
            elif new_pts >= 3:
                levels_with_id[idx]["strength"]["stars"] = 2
            else:
                levels_with_id[idx]["strength"]["stars"] = 1
    for lv in levels_with_id:
        lv.pop("_temp_id", None)
    return levels_with_id


# ---------------------------------------------------------------------------
# Hypothesis-grade integration
# ---------------------------------------------------------------------------

def _hypothesis_priors(state_dir: Path) -> dict[float, dict]:
    """Read hypothesis-grades.jsonl and compute per-level prior scores.

    Returns dict of {price -> {hits, misses, hit_rate}} based on prior predictions
    that mentioned that price.
    """
    path = state_dir / "hypothesis-grades.jsonl"
    if not path.exists():
        return {}
    priors: dict[float, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except Exception:
            continue
        for pred in row.get("predictions", []):
            claim = str(pred.get("claim", ""))
            outcome = pred.get("outcome", "")
            # Extract any $XXX.XX numbers from the claim
            import re
            for m in re.findall(r"\$?(\d{3,4}\.\d{2})", claim):
                try:
                    price = round(float(m), 2)
                except ValueError:
                    continue
                if price not in priors:
                    priors[price] = {"hits": 0, "misses": 0, "total": 0}
                priors[price]["total"] += 1
                if outcome == "PASS":
                    priors[price]["hits"] += 1
                else:
                    priors[price]["misses"] += 1
    for p, d in priors.items():
        d["hit_rate"] = round(d["hits"] / d["total"], 3) if d["total"] > 0 else None
    return priors


def _attach_hypothesis_priors(levels: list[dict], priors: dict) -> list[dict]:
    """Match each level price to nearest prior (within $0.20)."""
    out = []
    for lv in levels:
        new = dict(lv)
        price = round(float(lv["price"]), 2)
        # Find any prior within $0.20
        nearest = None
        nearest_dist = 1.0
        for pp, data in priors.items():
            d = abs(pp - price)
            if d <= 0.20 and d < nearest_dist:
                nearest = (pp, data)
                nearest_dist = d
        if nearest is not None:
            pp, data = nearest
            new["hypothesis_prior"] = {
                "matched_price": pp,
                "hits": data.get("hits", 0),
                "misses": data.get("misses", 0),
                "hit_rate": data.get("hit_rate"),
            }
        out.append(new)
    return out


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def compute(target_date: dt.date | None, spot: float | None) -> dict:
    spy = _load_spy_bars()
    if target_date is None:
        target_date = spy["date"].max()
        # If today_date is already in data and we're computing tomorrow's levels,
        # increment to next business day.
        target_date = target_date + dt.timedelta(days=1)
        while target_date.weekday() >= 5:
            target_date += dt.timedelta(days=1)

    # Identify "today" (most recent date in data) and "prior" (the date before)
    available_dates = sorted(spy["date"].unique())
    today_date = available_dates[-1]  # last day in data
    prior_dates = [d for d in available_dates if d < today_date]
    if not prior_dates:
        raise ValueError("Need at least 2 days of bars to compute pivots")
    prior_date = prior_dates[-1]

    rth = _rth_only(spy)
    today_rth = rth[rth["date"] == today_date]
    prior_rth = rth[rth["date"] == prior_date]
    today_premarket = _premarket_only(spy, today_date)

    # 5-day rolling RTH (excluding today)
    five_day_dates = prior_dates[-5:]
    prior_rth_5d = rth[rth["date"].isin(five_day_dates)]

    # Spot
    if spot is None:
        if not today_rth.empty:
            spot = float(today_rth["close"].iloc[-1])
        else:
            spot = float(prior_rth["close"].iloc[-1])

    # Average 5m volume baseline (last 20 RTH bars)
    avg_5m_volume = float(rth.tail(20)["volume"].mean()) if "volume" in rth.columns else 50_000.0

    # Read existing key-levels.json for carry-over
    klp = STATE_DIR / "key-levels.json"
    existing: list[dict] = []
    if klp.exists():
        try:
            data = json.loads(klp.read_text(encoding="utf-8"))
            existing = data.get("levels", [])
        except Exception:
            existing = []

    # Build levels from each source
    levels: list[dict] = []
    levels.extend(_carry_over_levels(existing))
    levels.extend(_prior_day_rth_levels(prior_rth, prior_date))
    levels.extend(_pivot_levels(prior_rth, prior_date, spot))
    levels.extend(_todays_session_extremes(today_rth, today_date))
    levels.extend(_premarket_extremes(today_premarket, today_date))
    levels.extend(_round_numbers_near_spot(spot))
    levels.extend(_multi_day_swings(prior_rth_5d, today_date))
    levels.extend(_vwap_levels(today_rth, today_date, spot))
    levels.extend(_volume_profile_levels(today_rth, today_date, spot))
    levels.extend(_anchored_vwap_levels(spy, today_date, spot))

    # Dedupe by price (within $0.05)
    levels = _dedupe_by_price(levels)

    # Score
    levels = _score_levels(levels, spy, today_date, avg_5m_volume)

    # Confluence detection + score bump
    levels = _annotate_confluence(levels)

    # Hypothesis priors
    priors = _hypothesis_priors(STATE_DIR)
    levels = _attach_hypothesis_priors(levels, priors)

    # Distance filter
    kept, dropped = filter_by_distance(
        levels, spot=spot, limit_usd=DISTANCE_LIMIT_USD,
        keep_tiers=KEEP_TIERS_REGARDLESS,
    )

    # Sort by price descending
    kept.sort(key=lambda lv: -float(lv["price"]))

    return {
        "schema_version": 3,
        "protocol_version": "markdown/0dte/key-levels-protocol.md@2",
        "as_of": dt.datetime.now(ET).isoformat(),
        "for_session": target_date.isoformat(),
        "spot_at_compute": round(spot, 2),
        "computed_from": {
            "prior_date": prior_date.isoformat(),
            "today_date": today_date.isoformat(),
            "prior_rth_bars": int(len(prior_rth)),
            "today_rth_bars": int(len(today_rth)),
            "premarket_bars": int(len(today_premarket)),
        },
        "levels": kept,
        "dropped_for_distance": [{"price": lv["price"], "tier": lv["tier"], "source": lv["source"]} for lv in dropped],
        "summary": {
            "total_in": len(levels),
            "kept": len(kept),
            "dropped_distance": len(dropped),
            "by_stars": {
                "3star": sum(1 for lv in kept if lv["strength"].get("stars") == 3),
                "2star": sum(1 for lv in kept if lv["strength"].get("stars") == 2),
                "1star": sum(1 for lv in kept if lv["strength"].get("stars") == 1),
            },
            "confluences": sum(1 for lv in kept if lv.get("confluence_member_count")) // 2,
        },
    }


def _dedupe_by_price(levels: list[dict], tolerance: float = 0.05) -> list[dict]:
    """Collapse near-duplicate prices, keeping highest-tier source."""
    if not levels:
        return []
    levels = sorted(levels, key=lambda lv: float(lv["price"]))
    tier_priority = {"Active": 4, "Carry": 3, "Reference": 2, "Liquidity": 1}
    out: list[dict] = []
    for lv in levels:
        if not out:
            out.append(lv)
            continue
        last = out[-1]
        if abs(float(lv["price"]) - float(last["price"])) <= tolerance:
            # Keep the higher-tier one; merge sources
            if tier_priority.get(lv.get("tier"), 0) > tier_priority.get(last.get("tier"), 0):
                merged = dict(lv)
                merged["source"] = lv["source"] + " + " + last["source"]
                out[-1] = merged
            else:
                last["source"] = last["source"] + " + " + lv["source"]
        else:
            out.append(lv)
    return out


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-date", type=str, default=None,
                        help="Date the levels are FOR (default: next business day after data).")
    parser.add_argument("--spot", type=float, default=None,
                        help="Current spot price (default: latest close in data).")
    parser.add_argument("--out", type=Path, default=STATE_DIR / "key-levels.json",
                        help="Output path.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but don't write.")
    args = parser.parse_args()

    target_date = dt.date.fromisoformat(args.target_date) if args.target_date else None
    payload = compute(target_date=target_date, spot=args.spot)

    if args.dry_run:
        print(json.dumps(payload, indent=2, default=str))
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    s = payload["summary"]
    print(f"wrote {args.out}")
    print(f"  for_session={payload['for_session']}  spot=${payload['spot_at_compute']}")
    print(f"  kept={s['kept']} (dropped {s['dropped_distance']} for distance)")
    print(f"  stars: 3*={s['by_stars']['3star']}  2*={s['by_stars']['2star']}  1*={s['by_stars']['1star']}")
    print(f"  confluence_groups={s['confluences']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

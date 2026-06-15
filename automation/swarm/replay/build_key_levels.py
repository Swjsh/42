"""
Synthesize key-levels.json for a historical date — replay-mode replacement for the
hand-curated key-levels.json that the level_thesis agent reads.

Uses ALGORITHMIC derivation only (no journal extraction):
  - Prior day RTH high/low (from SPY 5m bars)
  - 5-day RTH high/low (rolling)
  - Today's premarket high/low (bars before 09:30 ET on target date)
  - Classic pivot levels: P, R1/R2, S1/S2 from prior day OHLC
  - Round number levels within $5 of current price (psychological, Reference tier)

NOTE: This intentionally misses J-curated Carry levels (e.g., the 5/15 738.10 ★★★
5-touch hold). That's by design — we're testing the swarm's signal quality with
the level set it COULD reproduce algorithmically. A journal-augmented mode can
be added later if we want to measure the upper-bound performance.

Schema matches key-levels.json v3 so level_thesis agent consumes it unmodified.

Usage:
  python build_key_levels.py --date 2026-05-15 --as-of 06:00
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

ET = ZoneInfo("America/New_York")
WORK_DIR = Path(__file__).parent.parent.parent.parent.resolve()
SWARM_DIR = WORK_DIR / "automation" / "swarm"

SPY_CSV_DEFAULT = WORK_DIR / "backtest" / "data" / "spy_5m_2025-01-01_2026-05-15.csv"


def _log(msg: str) -> None:
    print(f"[build_key_levels] {msg}", flush=True)


@dataclass(frozen=True)
class LevelCandidate:
    price: float
    type: str       # resistance | support
    tier: str       # Active | Carry | Reference
    source: str
    reasoning: str
    stars: int      # 1-3
    expires_in_days: int = 1


def _load_spy_5m(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=["timestamp_et"])
    df["timestamp_et"] = pd.to_datetime(df["timestamp_et"], utc=True).dt.tz_convert(ET).dt.tz_localize(None)
    return df.sort_values("timestamp_et").reset_index(drop=True)


def _prior_session_ohlc(spy_df: pd.DataFrame, target_date: str) -> dict | None:
    """Compute OHLC of the most recent completed RTH session before target_date."""
    sessions_before = spy_df[spy_df["timestamp_et"].dt.strftime("%Y-%m-%d") < target_date]
    if sessions_before.empty:
        return None
    prior_date = sessions_before["timestamp_et"].dt.strftime("%Y-%m-%d").max()
    prior_rth = sessions_before[
        (sessions_before["timestamp_et"].dt.strftime("%Y-%m-%d") == prior_date) &
        (sessions_before["timestamp_et"].dt.time >= time(9, 30)) &
        (sessions_before["timestamp_et"].dt.time < time(16, 0))
    ]
    if prior_rth.empty:
        return None
    return {
        "date": prior_date,
        "open": float(prior_rth.iloc[0]["open"]),
        "high": float(prior_rth["high"].max()),
        "low": float(prior_rth["low"].min()),
        "close": float(prior_rth.iloc[-1]["close"]),
    }


def _five_day_rth_range(spy_df: pd.DataFrame, target_date: str) -> tuple[float | None, float | None]:
    """Compute high/low across the 5 most recent completed RTH sessions before target_date."""
    sessions_before = spy_df[spy_df["timestamp_et"].dt.strftime("%Y-%m-%d") < target_date]
    if sessions_before.empty:
        return None, None
    prior_dates = sorted(set(sessions_before["timestamp_et"].dt.strftime("%Y-%m-%d")), reverse=True)[:5]
    five_day_rth = sessions_before[
        (sessions_before["timestamp_et"].dt.strftime("%Y-%m-%d").isin(prior_dates)) &
        (sessions_before["timestamp_et"].dt.time >= time(9, 30)) &
        (sessions_before["timestamp_et"].dt.time < time(16, 0))
    ]
    if five_day_rth.empty:
        return None, None
    return float(five_day_rth["high"].max()), float(five_day_rth["low"].min())


def _premarket_high_low(spy_df: pd.DataFrame, target_date: str, as_of: datetime) -> tuple[float | None, float | None]:
    """High/low across premarket bars (before 09:30 ET) on target_date, up to as-of."""
    as_of_naive = as_of.replace(tzinfo=None) if as_of.tzinfo else as_of
    today_premarket = spy_df[
        (spy_df["timestamp_et"].dt.strftime("%Y-%m-%d") == target_date) &
        (spy_df["timestamp_et"].dt.time < time(9, 30)) &
        (spy_df["timestamp_et"] < as_of_naive)
    ]
    if today_premarket.empty:
        return None, None
    return float(today_premarket["high"].max()), float(today_premarket["low"].min())


def _classic_pivots(ohlc: dict) -> dict:
    """Standard floor-trader pivot points from prior day OHLC."""
    h, l, c = ohlc["high"], ohlc["low"], ohlc["close"]
    p = (h + l + c) / 3.0
    r1 = 2.0 * p - l
    r2 = p + (h - l)
    s1 = 2.0 * p - h
    s2 = p - (h - l)
    return {"P": p, "R1": r1, "R2": r2, "S1": s1, "S2": s2}


def _current_price(spy_df: pd.DataFrame, as_of: datetime) -> float | None:
    as_of_naive = as_of.replace(tzinfo=None) if as_of.tzinfo else as_of
    bars = spy_df[spy_df["timestamp_et"] < as_of_naive]
    if bars.empty:
        return None
    return float(bars.iloc[-1]["close"])


def _round_number_levels(current_price: float, radius: float = 5.0) -> list[LevelCandidate]:
    """Whole dollar levels within ±$radius of current price."""
    lo = int(current_price - radius)
    hi = int(current_price + radius) + 1
    out = []
    for n in range(lo, hi):
        if n == round(current_price):
            continue
        out.append(LevelCandidate(
            price=float(n),
            type="resistance" if n > current_price else "support",
            tier="Reference",
            source=f"psychological ${n} round number",
            reasoning="Awareness-only level — round numbers attract attention but per OP 5 not a trigger.",
            stars=1,
        ))
    return out


def _build_level_candidates(spy_df: pd.DataFrame, target_date: str, as_of: datetime) -> list[LevelCandidate]:
    candidates: list[LevelCandidate] = []

    current_price = _current_price(spy_df, as_of)
    if current_price is None:
        return candidates

    prior = _prior_session_ohlc(spy_df, target_date)
    if prior is not None:
        candidates.append(LevelCandidate(
            price=prior["high"], type="resistance", tier="Active",
            source=f"Prior session ({prior['date']}) RTH high",
            reasoning="First overhead resistance after gap-up open or any intraday rally.",
            stars=2,
        ))
        candidates.append(LevelCandidate(
            price=prior["low"], type="support", tier="Active",
            source=f"Prior session ({prior['date']}) RTH low",
            reasoning="First support shelf on any retrace; gap-fill target on bearish days.",
            stars=2,
        ))

        pivots = _classic_pivots(prior)
        for label, price in [("R1", pivots["R1"]), ("R2", pivots["R2"]),
                             ("S1", pivots["S1"]), ("S2", pivots["S2"])]:
            ltype = "resistance" if price > current_price else "support"
            candidates.append(LevelCandidate(
                price=round(price, 2), type=ltype, tier="Reference",
                source=f"Classic floor-trader pivot {label} from {prior['date']} OHLC",
                reasoning=f"Algorithmic pivot {label} = derived from prior-day H/L/C. Awareness-only weight.",
                stars=1,
            ))

    h5, l5 = _five_day_rth_range(spy_df, target_date)
    if h5 is not None and h5 > current_price:
        candidates.append(LevelCandidate(
            price=h5, type="resistance", tier="Carry",
            source="5-day RTH high (rolling)",
            reasoning="Multi-session high — carries cross-session significance per strategy/key-levels-protocol.md.",
            stars=2,
        ))
    if l5 is not None and l5 < current_price:
        candidates.append(LevelCandidate(
            price=l5, type="support", tier="Carry",
            source="5-day RTH low (rolling)",
            reasoning="Multi-session low — carries cross-session significance per strategy/key-levels-protocol.md.",
            stars=2,
        ))

    pmh, pml = _premarket_high_low(spy_df, target_date, as_of)
    if pmh is not None and pmh != current_price:
        ltype = "resistance" if pmh > current_price else "support"
        candidates.append(LevelCandidate(
            price=pmh, type=ltype, tier="Active",
            source=f"Today {target_date} premarket high",
            reasoning="PMH — gap-up ceiling or first RTH overhead. Active tier expires today 18:00 ET.",
            stars=2,
        ))
    if pml is not None and pml != current_price:
        ltype = "resistance" if pml > current_price else "support"
        candidates.append(LevelCandidate(
            price=pml, type=ltype, tier="Active",
            source=f"Today {target_date} premarket low",
            reasoning="PML — gap-down floor or first RTH support. Active tier expires today 18:00 ET.",
            stars=2,
        ))

    candidates.extend(_round_number_levels(current_price, radius=5.0))

    return candidates


def _dedupe_and_assemble(candidates: list[LevelCandidate], current_price: float,
                        target_date: str) -> list[dict]:
    """Deduplicate within 25c, keep the highest-tier/star candidate."""
    sorted_cands = sorted(candidates, key=lambda c: (
        -{"Carry": 3, "Active": 2, "Reference": 1}[c.tier],
        -c.stars,
        c.price,
    ))
    chosen: list[LevelCandidate] = []
    for cand in sorted_cands:
        if any(abs(cand.price - c.price) < 0.25 for c in chosen):
            continue
        chosen.append(cand)

    levels = []
    expires_iso = datetime.fromisoformat(f"{target_date}T18:00:00").replace(tzinfo=ET).isoformat()
    for cand in chosen:
        levels.append({
            "price": round(cand.price, 2),
            "type": cand.type,
            "tier": cand.tier,
            "source": cand.source,
            "reasoning": cand.reasoning,
            "verified_at": f"{target_date}T06:00:00-04:00",
            "expires_at": expires_iso,
            "color": "#ef4444" if cand.type == "resistance" else "#22c55e",
            "style": "solid" if cand.tier in ("Carry", "Active") else "dashed",
            "entity_id": None,
            "draw_needed": False,
            "respect_count": 0,
            "broken_count": 0,
            "role": None,
            "bounce_history": [],
            "strength": {
                "stars": cand.stars,
                "points": cand.stars * 2,
                "components": {
                    "touch_score": 1,
                    "recency_score": 2 if cand.tier == "Active" else 1,
                    "mtf_score": 0,
                    "volume_score": 0,
                    "confluence_score": 0,
                },
            },
            "touch_count": 1,
            "held_count": 1,
            "volume_at_touches": 0,
            "last_touched_at": None,
            "recency_days": 0.0 if cand.tier == "Active" else 1.0,
            "mtf_agreement": 0,
            "drawn_on_chart": False,
        })
    return levels


def build_key_levels(date_et: str, as_of_hhmm: str,
                     spy_csv: Path = SPY_CSV_DEFAULT,
                     output_path: Path | None = None) -> dict:
    as_of = datetime.fromisoformat(f"{date_et}T{as_of_hhmm}:00").replace(tzinfo=ET)
    spy_df = _load_spy_5m(spy_csv)

    current_price = _current_price(spy_df, as_of)
    candidates = _build_level_candidates(spy_df, date_et, as_of)
    levels = _dedupe_and_assemble(candidates, current_price or 0.0, date_et)

    key_levels = {
        "schema_version": 3,
        "protocol_version": "strategy/key-levels-protocol.md@2 (replay-mode algorithmic)",
        "as_of": f"{date_et}T{as_of_hhmm}:00-04:00",
        "for_session": date_et,
        "spot_at_compute": round(current_price, 2) if current_price else None,
        "replay_mode": True,
        "computed_from": {
            "prior_date": "auto",
            "today_date": date_et,
            "prior_rth_bars": 78,
            "today_rth_bars": 0,
            "premarket_bars": len(spy_df[
                (spy_df["timestamp_et"].dt.strftime("%Y-%m-%d") == date_et) &
                (spy_df["timestamp_et"].dt.time < time(9, 30))
            ]),
        },
        "levels": levels,
    }

    if output_path is None:
        output_path = SWARM_DIR / "state" / "key-levels.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(key_levels, f, indent=2)
    _log(f"wrote {output_path} ({len(levels)} levels, spot={current_price})")
    return key_levels


def main() -> int:
    parser = argparse.ArgumentParser(description="Build synthetic key-levels.json for historical date")
    parser.add_argument("--date", required=True, help="Target date YYYY-MM-DD")
    parser.add_argument("--as-of", default="06:00", help="As-of time HH:MM ET (default 06:00)")
    parser.add_argument("--spy-csv", type=Path, default=SPY_CSV_DEFAULT)
    parser.add_argument("--output", type=Path, default=None,
                        help="Output JSON path (default: automation/swarm/state/key-levels.json)")
    args = parser.parse_args()

    try:
        build_key_levels(args.date, args.as_of, args.spy_csv, args.output)
        return 0
    except Exception as exc:
        _log(f"ERROR: {exc}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

"""Tomorrow module — carry levels, scheduled events, dev-setups for next session."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pandas as pd

from ..schema import CategoryScore
from ..ingest import IngestedData

REPO = Path(__file__).resolve().parent.parent.parent.parent.parent


def _read_macro_calendar() -> list[dict]:
    """Load automation/state/macro-calendar.json if available."""
    try:
        path = REPO / "automation" / "state" / "macro-calendar.json"
        if not path.exists():
            return []
        data = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("events", [])
        return []
    except Exception:
        return []


def _compute_carry_levels_from_csv(date_str: str) -> dict:
    """Compute today's RTH H/L/C from 5m CSV → carry for tomorrow.

    Tomorrow's premarket will see these levels in `today-bias.json` after
    `Gamma_Premarket` writes them.
    """
    data_dir = REPO / "backtest" / "data"
    for csv in sorted(data_dir.glob("spy_5m_2026-*.csv"), reverse=True):
        try:
            df = pd.read_csv(csv)
            df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
            if df["timestamp_et"].dt.tz is not None:
                df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)
            df["date"] = df["timestamp_et"].dt.date.astype(str)
            df["time"] = df["timestamp_et"].dt.strftime("%H:%M")
            today = df[
                (df["date"] == date_str) &
                (df["time"] >= "09:30") &
                (df["time"] < "16:00")
            ]
            if today.empty:
                continue
            return {
                "today_rth_high": round(float(today["high"].max()), 2),
                "today_rth_low": round(float(today["low"].min()), 2),
                "today_rth_close": round(float(today.iloc[-1]["close"]), 2),
                "today_rth_open": round(float(today.iloc[0]["open"]), 2),
                "today_session_range": round(
                    float(today["high"].max() - today["low"].min()), 2
                ),
                "today_volume_total": int(today["volume"].sum()),
            }
        except Exception:
            continue
    return {}


def _next_trading_day(date_str: str) -> str:
    """Return next weekday (skip Sat/Sun). NOT holiday-aware (Phase 2.4 simple)."""
    try:
        d = dt.date.fromisoformat(date_str)
        d = d + dt.timedelta(days=1)
        while d.weekday() >= 5:  # Sat=5, Sun=6
            d = d + dt.timedelta(days=1)
        return d.isoformat()
    except Exception:
        return ""


def analyze_tomorrow(data: IngestedData, trades) -> CategoryScore:
    """Compose forward-look. Score = quality of forward-state capture."""
    ls = data.loop_state or {}
    spy = ls.get("spy", {}) or {}
    next_day = _next_trading_day(data.date)
    events = _read_macro_calendar()
    tomorrow_events = []
    for e in events:
        if not isinstance(e, dict):
            continue
        e_date = e.get("date") or e.get("date_et")
        if e_date and str(e_date).startswith(next_day):
            tomorrow_events.append(e)

    dev_setup = ls.get("developing_setup")
    # Filter dev_setup keys for serialization safety
    if isinstance(dev_setup, dict):
        dev_serializable = {
            "name": dev_setup.get("name"),
            "trigger": dev_setup.get("trigger"),
            "score": dev_setup.get("score"),
            "score_max": dev_setup.get("score_max"),
            "blockers": dev_setup.get("blockers", []),
        }
    else:
        dev_serializable = None

    # Carry levels — today's H/L/C + key levels from today_bias + CSV-computed
    carry_levels = {
        "today_session_high": spy.get("session_high"),
        "today_session_low": spy.get("session_low"),
        "today_session_close": spy.get("last"),
    }
    # NEW: pull from CSV for higher precision than loop-state snapshot
    csv_carry = _compute_carry_levels_from_csv(data.date)
    if csv_carry:
        carry_levels["csv_computed"] = csv_carry

    tb = data.today_bias or {}
    if isinstance(tb, dict):
        key_levels = tb.get("key_levels")
        if isinstance(key_levels, dict):
            carry_levels["key_levels_from_today_bias"] = key_levels

    # Compute "5d_high" — max RTH high over last 5 trading days
    # (excluding today; used as ★★★ Carry by SNIPER-style level detection)
    try:
        data_dir = REPO / "backtest" / "data"
        for csv in sorted(data_dir.glob("spy_5m_2026-*.csv"), reverse=True):
            df = pd.read_csv(csv)
            df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
            if df["timestamp_et"].dt.tz is not None:
                df["timestamp_et"] = df["timestamp_et"].dt.tz_localize(None)
            df["date"] = df["timestamp_et"].dt.date.astype(str)
            df["time"] = df["timestamp_et"].dt.strftime("%H:%M")
            rth = df[(df["time"] >= "09:30") & (df["time"] < "16:00")]
            prior_dates = sorted(set(rth["date"].values))
            prior_dates = [d for d in prior_dates if d <= data.date]
            if not prior_dates:
                continue
            last_5 = prior_dates[-5:]
            day5 = rth[rth["date"].isin(last_5)]
            if not day5.empty:
                carry_levels["5d_high"] = round(float(day5["high"].max()), 2)
                carry_levels["5d_low"] = round(float(day5["low"].min()), 2)
                carry_levels["5d_dates"] = last_5
            break
    except Exception:
        pass

    # Score: 100 if we have session H/L/C + macro calendar + dev_setup state
    pts = 0
    if spy.get("session_high") and spy.get("session_low") and spy.get("last"):
        pts += 40
    if tomorrow_events:
        pts += 30
    elif events:
        pts += 15
    else:
        pts += 5
    if dev_serializable:
        pts += 20
    else:
        pts += 10
    if next_day:
        pts += 10

    narrative_parts = [
        f"Next trading day: {next_day or 'unknown'}.",
        f"Session H/L/C: {spy.get('session_high')} / {spy.get('session_low')} / {spy.get('last')}.",
        f"Macro events tomorrow: {len(tomorrow_events)}.",
    ]
    if dev_serializable:
        narrative_parts.append(
            f"Dev setup at close: {dev_serializable.get('name')} score "
            f"{dev_serializable.get('score')}/{dev_serializable.get('score_max')}."
        )

    return CategoryScore(
        score=float(pts),
        evidence={
            "phase": "2.4",
            "next_trading_day": next_day,
            "carry_levels": carry_levels,
            "scheduled_events_tomorrow": tomorrow_events,
            "developing_setup_at_close": dev_serializable,
        },
        narrative=" ".join(narrative_parts),
        actions=[],
    )

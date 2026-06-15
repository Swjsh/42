"""Macro module — predicted regime vs realized."""
from __future__ import annotations

from ..schema import CategoryScore
from ..ingest import IngestedData


def analyze_macro(data: IngestedData, trades) -> CategoryScore:
    """Score 0-100 based on news.json predicted regime vs realized SPY behavior."""
    news = data.news or {}
    ls = data.loop_state or {}
    spy = ls.get("spy", {}) or {}

    predicted_regime = news.get("regime", "")
    primary_catalyst = news.get("primary_catalyst", {})
    if isinstance(primary_catalyst, dict):
        catalyst_type = primary_catalyst.get("type", "")
    else:
        catalyst_type = ""

    # Realized regime from session range
    session_high = float(spy.get("session_high") or 0)
    session_low = float(spy.get("session_low") or 0)
    session_close = float(spy.get("last") or 0)

    realized_regime = "unknown"
    if session_high > 0 and session_low > 0 and session_close > 0:
        session_open = session_close  # fallback if open not in loop-state
        # Use first 5m bar from today_bias if available
        tb = data.today_bias or {}
        try:
            # PMH from today_bias.key_levels is sometimes the open
            pass
        except Exception:
            pass

        range_pct = (session_high - session_low) / session_close * 100
        move_pct = (session_close - session_low) / session_close * 100  # rough proxy

        if move_pct >= 0.5 and session_close >= session_high * 0.99:
            realized_regime = "bullish_close_at_high"
        elif move_pct <= -0.5:
            realized_regime = "bearish_close"
        elif range_pct < 0.5:
            realized_regime = "tight_chop"
        else:
            realized_regime = "mixed_drift"

    # Score: match between predicted + realized
    score = 50
    if predicted_regime and realized_regime != "unknown":
        # Heuristic match
        pred_lower = predicted_regime.lower()
        rel_lower = realized_regime.lower()
        if "bullish" in pred_lower and "bullish" in rel_lower:
            score = 95
        elif "bearish" in pred_lower and "bearish" in rel_lower:
            score = 95
        elif "chop" in pred_lower and "chop" in rel_lower:
            score = 85
        elif "drift" in pred_lower and "drift" in rel_lower:
            score = 80
        elif "drift" in pred_lower and ("bullish" in rel_lower or "mixed" in rel_lower):
            score = 75  # drift can become bullish; close enough
        else:
            score = 30  # mismatch

    # News freshness check
    as_of = news.get("as_of", "")
    fresh = "" if not as_of else (
        "fresh" if as_of.startswith(data.date) else "stale_one_day_or_more"
    )

    narrative = (
        f"Predicted regime: {predicted_regime or 'none'} "
        f"(catalyst: {catalyst_type or 'unknown'}). "
        f"Realized: {realized_regime}. "
        f"News freshness: {fresh}. Score {score}/100."
    )

    actions = []
    if fresh == "stale_one_day_or_more":
        actions.append({
            "type": "alert_stale_news",
            "priority": "MED",
            "details": {"as_of": as_of, "today": data.date,
                       "note": "Premarket should re-fetch news.json on next fire."},
        })

    return CategoryScore(
        score=float(score),
        evidence={
            "phase": "2.4",
            "predicted_regime": predicted_regime,
            "primary_catalyst_type": catalyst_type,
            "realized_regime": realized_regime,
            "session_high": session_high,
            "session_low": session_low,
            "session_close": session_close,
            "news_freshness": fresh,
            "news_as_of": as_of,
        },
        narrative=narrative,
        actions=actions,
    )

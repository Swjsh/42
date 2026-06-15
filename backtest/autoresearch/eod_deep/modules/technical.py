"""Technical module — chart-read accuracy via hypothesis-grades + key-level holds/breaks."""
from __future__ import annotations

from ..schema import CategoryScore
from ..ingest import IngestedData


def analyze_technical(data: IngestedData, trades) -> CategoryScore:
    """Score 0-100 based on:
      - 40 pts: hypothesis grades pass rate (from hypothesis-grades.jsonl)
      - 30 pts: key levels predicted vs actual (from today_bias.key_levels)
      - 30 pts: ribbon stack at close consistent with bias direction
    """
    grades = data.hypothesis_grades_today or []
    tb = data.today_bias or {}
    ls = data.loop_state or {}
    spy = ls.get("spy", {}) or {}
    ribbon = ls.get("ribbon", {}) or {}

    # 40 pts: hypothesis grades
    pass_count = sum(1 for g in grades if g.get("verdict") in ("PASS", "TRUE", "CONFIRMED"))
    fail_count = sum(1 for g in grades if g.get("verdict") in ("FAIL", "FALSE", "REJECTED"))
    total_grades = pass_count + fail_count
    if total_grades >= 3:
        grades_pts = round(40 * pass_count / total_grades)
    elif total_grades >= 1:
        grades_pts = round(25 * pass_count / total_grades)
    else:
        grades_pts = 15  # no grades = no signal either way

    # 30 pts: key level prediction accuracy
    key_levels = tb.get("key_levels", {}) if isinstance(tb, dict) else {}
    session_high = float(spy.get("session_high") or 0)
    session_low = float(spy.get("session_low") or 0)
    levels_held = []
    levels_broken = []
    if isinstance(key_levels, dict):
        for tier in ("resistance", "support", "active", "carry"):
            items = key_levels.get(tier, [])
            if not isinstance(items, list):
                continue
            for item in items:
                try:
                    if isinstance(item, dict):
                        price = float(item.get("price", 0))
                        kind = item.get("type", tier).lower()
                    else:
                        price = float(item)
                        kind = tier.lower()
                    if price <= 0:
                        continue
                    # Resistance: held if session_high <= price
                    # Support: held if session_low >= price
                    if "resistance" in kind or kind == "r":
                        if session_high <= price:
                            levels_held.append({"price": price, "kind": "resistance"})
                        else:
                            levels_broken.append({"price": price, "kind": "resistance"})
                    elif "support" in kind or kind == "s":
                        if session_low >= price:
                            levels_held.append({"price": price, "kind": "support"})
                        else:
                            levels_broken.append({"price": price, "kind": "support"})
                except (ValueError, TypeError):
                    continue
    n_levels = len(levels_held) + len(levels_broken)
    if n_levels >= 3:
        # Either bias direction OK: aim is the levels were ACCURATE forecasts
        # Score: held=correct (held expectation), broken=correct on opposite (broke through)
        # Simple: pass rate = held / total (favors the bias-direction predictor)
        levels_pts = round(30 * len(levels_held) / n_levels)
    elif n_levels >= 1:
        levels_pts = round(20 * len(levels_held) / n_levels)
    else:
        levels_pts = 15

    # 30 pts: ribbon at close consistent with bias direction
    bias_dir = tb.get("bias", "").lower() if isinstance(tb, dict) else ""
    ribbon_stack = ribbon.get("stack", "")
    ribbon_pts = 15
    if "bullish" in bias_dir and ribbon_stack == "BULL":
        ribbon_pts = 30
    elif "bearish" in bias_dir and ribbon_stack == "BEAR":
        ribbon_pts = 30
    elif "neutral" in bias_dir or not bias_dir:
        ribbon_pts = 20
    elif ribbon_stack == "MIXED":
        ribbon_pts = 20  # bias direction was committed but ribbon ended chop = not a hard fail

    score = grades_pts + levels_pts + ribbon_pts

    narrative = (
        f"Hypothesis grades: {pass_count}/{total_grades} PASS. "
        f"Key levels: {len(levels_held)} held / {len(levels_broken)} broken. "
        f"Ribbon close: {ribbon_stack} (bias was: {bias_dir or 'unset'}). "
        f"Score {score}/100 (grades={grades_pts}/40, levels={levels_pts}/30, ribbon={ribbon_pts}/30)."
    )

    return CategoryScore(
        score=float(score),
        evidence={
            "phase": "2.4",
            "hypothesis_grades": {"pass": pass_count, "fail": fail_count, "total": total_grades},
            "levels_held": levels_held,
            "levels_broken": levels_broken,
            "ribbon_close_stack": ribbon_stack,
            "bias_direction_predicted": bias_dir,
            "weights": {"grades": grades_pts, "levels": levels_pts, "ribbon": ribbon_pts},
        },
        narrative=narrative,
        actions=[],
    )

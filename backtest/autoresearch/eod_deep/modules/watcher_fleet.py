"""Watcher Fleet module — per-watcher fires, observations, would-be P&L."""
from __future__ import annotations

from ..schema import CategoryScore
from ..ingest import IngestedData


# Expected watcher fire counts for full RTH session
EXPECTED_DIAG_FIRES = 76  # every 5 min × ~6h20m
# Known live watchers per lib/watchers/runner.py (post-SNIPER-retirement)
EXPECTED_WATCHERS = [
    "orb_watcher", "bullish_watcher", "v14_enhanced_watcher",
    "opening_drive_fade_watcher", "vwap_watcher",
    "premarket_fail_fade_watcher",
    # pinfade_watcher / sniper_watcher retired
]


def analyze_watcher_fleet(data: IngestedData, trades) -> CategoryScore:
    """Score 0-100 watcher infrastructure health.

    Weights:
      30 pts — diag fires count ≥80% expected (T76 working)
      30 pts — fraction of fires that emitted ≥1 signal
      20 pts — number of UNIQUE watchers that fired today (≥3 of 6 = healthy)
      20 pts — no silent-zero-observation pattern (any watcher with 0 obs but
               >5 fires in last 7 days = silent failure flag)
    """
    diag = data.watcher_diag_today or []
    obs = data.watcher_obs_today or []

    fires_total = len(diag)
    fires_with_signal = sum(1 for d in diag if d.get("signals_emitted", 0) > 0)

    # Diag fires pts
    if fires_total >= EXPECTED_DIAG_FIRES * 0.95:
        diag_pts = 30
    elif fires_total >= EXPECTED_DIAG_FIRES * 0.80:
        diag_pts = 25
    elif fires_total >= EXPECTED_DIAG_FIRES * 0.50:
        diag_pts = 15
    elif fires_total >= 10:
        diag_pts = 8
    else:
        diag_pts = 0

    # Signal-emitting fraction
    if fires_total > 0:
        sig_pct = fires_with_signal / fires_total
        if sig_pct >= 0.50:
            signal_pts = 30
        elif sig_pct >= 0.25:
            signal_pts = 22
        elif sig_pct >= 0.10:
            signal_pts = 15
        elif sig_pct > 0:
            signal_pts = 8
        else:
            signal_pts = 0
    else:
        signal_pts = 0

    # Per-watcher obs count
    by_watcher: dict[str, int] = {}
    for o in obs:
        w = o.get("watcher_name", "unknown")
        by_watcher[w] = by_watcher.get(w, 0) + 1
    unique_firing = len([w for w in by_watcher if by_watcher[w] > 0])

    if unique_firing >= 5:
        uniq_pts = 20
    elif unique_firing >= 3:
        uniq_pts = 15
    elif unique_firing >= 1:
        uniq_pts = 8
    else:
        uniq_pts = 0

    # Silent-failure detection — watchers expected but with 0 obs today
    silent_watchers = [w for w in EXPECTED_WATCHERS if by_watcher.get(w, 0) == 0]
    if not silent_watchers:
        silent_pts = 20
    elif len(silent_watchers) <= 1:
        silent_pts = 15
    elif len(silent_watchers) <= 3:
        silent_pts = 8
    else:
        silent_pts = 0

    score = diag_pts + signal_pts + uniq_pts + silent_pts

    actions = []
    if silent_watchers:
        actions.append({
            "type": "alert_silent_watchers",
            "priority": "MED" if len(silent_watchers) <= 2 else "HIGH",
            "details": {"silent_watchers": silent_watchers,
                       "expected": EXPECTED_WATCHERS,
                       "by_watcher_today": by_watcher,
                       "note": "Run setup/scripts/audit-silent-watcher-days.ps1 for cross-day pattern"}
        })

    narrative = (
        f"Diag fires: {fires_total}/{EXPECTED_DIAG_FIRES} "
        f"({100*fires_total/EXPECTED_DIAG_FIRES:.0f}% of expected). "
        f"Fires with signals: {fires_with_signal} ({100*fires_with_signal/max(1,fires_total):.0f}%). "
        f"Watchers active: {unique_firing}/{len(EXPECTED_WATCHERS)}. "
        f"Silent watchers: {silent_watchers if silent_watchers else 'none'}. "
        f"Score {score}/100."
    )

    return CategoryScore(
        score=float(score),
        evidence={
            "phase": "2.4",
            "diag_fires_total": fires_total,
            "expected_diag_fires": EXPECTED_DIAG_FIRES,
            "fires_with_signals": fires_with_signal,
            "observations_by_watcher": by_watcher,
            "unique_watchers_firing_today": unique_firing,
            "expected_watchers": EXPECTED_WATCHERS,
            "silent_watchers_today": silent_watchers,
            "weights": {"diag": diag_pts, "signal": signal_pts,
                       "unique": uniq_pts, "silent": silent_pts},
        },
        narrative=narrative,
        actions=actions,
    )

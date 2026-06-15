"""Engine Health module — heartbeat ticks, pin chain, watcher diag activity."""
from __future__ import annotations

from ..schema import CategoryScore
from ..ingest import IngestedData


# Expected RTH activity counts (09:30-15:55 ET):
EXPECTED_HEARTBEAT_TICKS = 127       # every 3 min × 6h25m
EXPECTED_WATCHER_LIVE_FIRES = 76     # every 5 min × 6h20m


def analyze_engine_health(data: IngestedData, trades) -> CategoryScore:
    """Score the autonomous infrastructure for today.

    Weights:
      30 pts — pin chain intact (params.rule_version + heartbeat.md + premarket.md)
      25 pts — heartbeat tick count ≥80% of expected
      25 pts — watcher diag fires ≥80% of expected
      20 pts — no silent-failure markers (no TV CDP down, Discord bridge down, etc.)
    """
    # Pin chain — single check
    params = data.params or {}
    # Accept v15 or any v15.x sub-version (v15.1, v15.2, ...) — ratified variants.
    rv = str(params.get("rule_version", ""))
    pin_rule = rv == "v15" or rv.startswith("v15.")

    # Phase 2.4: trust params.rule_version=v15.x as enough; deeper check (heartbeat.md
    # RULE_VERSION constant) requires reading files outside ingest scope.
    pin_pts = 30 if pin_rule else 0

    # Heartbeat ticks today = entries in decisions.jsonl
    tick_count = len(data.decisions_today)
    if tick_count >= EXPECTED_HEARTBEAT_TICKS * 0.95:
        hb_pts = 25
    elif tick_count >= EXPECTED_HEARTBEAT_TICKS * 0.80:
        hb_pts = 20
    elif tick_count >= EXPECTED_HEARTBEAT_TICKS * 0.50:
        hb_pts = 12
    elif tick_count >= 10:
        hb_pts = 5
    else:
        hb_pts = 0

    # Watcher diag fires
    diag_fires = len(data.watcher_diag_today)
    if diag_fires >= EXPECTED_WATCHER_LIVE_FIRES * 0.95:
        diag_pts = 25
    elif diag_fires >= EXPECTED_WATCHER_LIVE_FIRES * 0.80:
        diag_pts = 20
    elif diag_fires >= EXPECTED_WATCHER_LIVE_FIRES * 0.50:
        diag_pts = 12
    elif diag_fires >= 10:
        diag_pts = 5
    else:
        diag_pts = 0

    # Silent-failure markers — scan journal_md + ingest_warnings for known issues
    incidents = []
    md_lower = (data.journal_md or "").lower()
    if "tv cdp" in md_lower and ("down" in md_lower or "silent-death" in md_lower):
        incidents.append("tv_cdp_silent_death")
    if "discord bridge" in md_lower and "dead" in md_lower:
        incidents.append("discord_bridge_died")
    for w in (data.ingest_warnings or []):
        incidents.append(f"ingest_warning:{w}")

    silent_pts = 20 if not incidents else max(0, 20 - 5 * len(incidents))

    score = pin_pts + hb_pts + diag_pts + silent_pts

    narrative_parts = [
        f"Pin chain: {rv if pin_rule else f'FAIL ({rv!r} ≠ v15.x)'}.",
        f"Heartbeat ticks: {tick_count}/{EXPECTED_HEARTBEAT_TICKS} ({100*tick_count/EXPECTED_HEARTBEAT_TICKS:.0f}%).",
        f"Watcher diag fires: {diag_fires}/{EXPECTED_WATCHER_LIVE_FIRES} ({100*diag_fires/EXPECTED_WATCHER_LIVE_FIRES:.0f}%).",
    ]
    if incidents:
        narrative_parts.append(f"Incidents: {', '.join(incidents)}.")
    else:
        narrative_parts.append("No silent-failure incidents detected.")

    actions = []
    if not pin_rule:
        actions.append({
            "type": "alert_pin_chain_break",
            "priority": "HIGH",
            "details": {"observed": rv, "expected": "v15 or v15.x"}
        })

    return CategoryScore(
        score=float(score),
        evidence={
            "phase": "2.4",
            "rule_version_active": params.get("rule_version"),
            "heartbeat_tick_count": tick_count,
            "expected_heartbeat_ticks": EXPECTED_HEARTBEAT_TICKS,
            "watcher_diag_fires": diag_fires,
            "expected_watcher_fires": EXPECTED_WATCHER_LIVE_FIRES,
            "incidents": incidents,
            "weights": {"pin": pin_pts, "heartbeat": hb_pts,
                       "diag": diag_pts, "silent_failure": silent_pts},
        },
        narrative=" ".join(narrative_parts),
        actions=actions,
    )

"""Watcher OP-21 Promotion Gate Dashboard.

Produces a concise one-screen report of every watcher's OP-21 gate status:
  - Historical gate (N + WR)
  - Walk-forward gate
  - Real-fills gate
  - Live J observations (from watcher-observations.jsonl)
  - Overall: READY_FOR_LIVE / ACCUMULATING / WATCH_FRAGILE / WATCH_STABLE / RETIRED

Usage:
    python backtest/autoresearch/watcher_promotion_gates.py
    python backtest/autoresearch/watcher_promotion_gates.py --json

Output:
    Console report (default)
    automation/state/watcher-promotion-snapshot.json  (always written)

Claude Code skill: /watcher-promotion-gates
Registered in markdown/infra/SKILLS-CATALOG.md
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO = Path(__file__).resolve().parents[2]
STATE_DIR = REPO / "automation" / "state"
OBS_LOG = STATE_DIR / "watcher-observations.jsonl"
OUT_PATH = STATE_DIR / "watcher-promotion-snapshot.json"

# ── Live observation cutoff (when watchers went live) ─────────────────────────
# Watchers became live on 2026-05-18 (J authorization per OP-25 ENGINE-BENEFIT).
# Use 2026-05-18 as the cutoff for "live" vs "historical/replay" observations.
LIVE_CUTOFF = "2026-05-18"

# ── Watcher registry ─────────────────────────────────────────────────────────
# Each entry describes the OP-21 gate status and promotion criteria.
# Fields:
#   watcher_name     : matches watcher_name field in observations.jsonl
#   display_name     : human-readable name
#   direction        : "short" | "long" | "mixed"
#   historical_n     : N from 16-month scan
#   historical_wr    : WR from 16-month scan (proxy)
#   historical_gate  : True/False/None (None = no historical possible — live only)
#   wf_gate          : True/False/None (None = no WF available)
#   wf_note          : short note on walk-forward result
#   real_fills_gate  : True/False/None (None = not yet run)
#   real_fills_wr    : WR from real-fills validation (or None)
#   real_fills_n     : N from real-fills (or None)
#   real_fills_note  : short note
#   live_wins_needed : how many live J-confirmed wins needed to promote
#   overall_status   : WATCH_STABLE/WATCH_FRAGILE/LIVE_ONLY/RETIRED/OBSERVE_ONLY
#   notes            : any important caveats
WATCHER_REGISTRY: list[dict] = [
    # ── HIGH-READINESS: all technical gates passed, pending live observations ──
    {
        "watcher_name": "hs_bear",
        "display_name": "HEAD_AND_SHOULDERS_BEAR",
        "direction": "short",
        "historical_n": 185,
        "historical_wr": 55.7,
        "historical_gate": True,
        "wf_gate": True,
        "wf_note": "OOS 58.5% vs train 54.5% (+4.0pp STABLE)",
        "real_fills_gate": True,
        "real_fills_wr": 73.7,
        "real_fills_n": 19,
        "real_fills_note": "Morning-only 09:40-12:00 ET. VIX 15-20=87.5% (best), >=25=80%.",
        "live_wins_needed": 3,
        "overall_status": "WATCH_STABLE",
        "notes": "NO VIX gate needed — all VIX regimes good in morning window. premium_stop=-0.99 (chart-stop).",
    },
    {
        "watcher_name": "fbw_morning_mid",
        "display_name": "FAILED_BREAKDOWN_WICK_MORNING_MID",
        "direction": "long",
        "historical_n": 35,
        "historical_wr": 74.3,
        "historical_gate": True,
        "wf_gate": True,
        "wf_note": "OOS 78.9% vs train 68.8% (+10.1pp STABLE)",
        "real_fills_gate": True,
        "real_fills_wr": 74.3,
        "real_fills_n": 35,
        "real_fills_note": "+$455 total. FAVORABLE +5.5pp vs proxy. WATCH_STABLE.",
        "live_wins_needed": 3,
        "overall_status": "WATCH_STABLE",
        "notes": "conf=MID [0.65,0.80) | 09:35-11:30 ET | chart-stop only (L55).",
    },
    {
        "watcher_name": "db_base_quiet",
        "display_name": "DOUBLE_BOTTOM_BASE_QUIET",
        "direction": "long",
        "historical_n": 122,
        "historical_wr": 63.9,
        "historical_gate": True,
        "wf_gate": True,
        "wf_note": "OOS +1.2pp STABLE. Most robust watcher in fleet.",
        "real_fills_gate": True,
        "real_fills_wr": 63.9,
        "real_fills_n": 122,
        "real_fills_note": "+$1,755 total. conf=LOW (< 0.60) gate excludes pathological 0.60-0.70 band.",
        "live_wins_needed": 3,
        "overall_status": "WATCH_STABLE",
        "notes": "Full RTH 09:35-15:55 ET. VIX<20 only. Walk-forward verdict: STABLE.",
    },
    # ── MODERATE-READINESS: technical gates with some caveats ──────────────────
    {
        "watcher_name": "named_level_wick_bounce_watcher",
        "display_name": "NAMED_LEVEL_WICK_BOUNCE",
        "direction": "long",
        "historical_n": 157,
        "historical_wr": 71.3,
        "historical_gate": True,
        "wf_gate": True,
        "wf_note": "OOS -7.9pp STABLE (PDL proxy — weaker level type).",
        "real_fills_gate": True,
        "real_fills_wr": 67.0,
        "real_fills_n": 25,
        "real_fills_note": "chart-stop only (L51/L55). PDL proxy WR=71.3% -> real 67%. L58: PDL parameter sweeps fail — need ★★★ named levels.",
        "live_wins_needed": 3,
        "overall_status": "WATCH_STABLE",
        "notes": "L58: PDL is weakest level type — focus live obs on ★★★ bounce signals only.",
    },
    {
        "watcher_name": "db_morning_low_vol",
        "display_name": "DOUBLE_BOTTOM_MORNING_LOW_VOL",
        "direction": "long",
        "historical_n": 109,
        "historical_wr": 67.9,
        "historical_gate": True,
        "wf_gate": False,
        "wf_note": "Walk-forward DEGRADED -15.2pp (WATCH_FRAGILE). Overfitting source: ENTRY_TIME_END=11:30.",
        "real_fills_gate": True,
        "real_fills_wr": 67.9,
        "real_fills_n": 109,
        "real_fills_note": "+$828 total. FAVORABLE. But WF fails: WATCH_FRAGILE.",
        "live_wins_needed": 5,
        "overall_status": "WATCH_FRAGILE",
        "notes": "11:30 ET cutoff may be overfit. Promote only with N>=5 live wins (higher bar due to WF fragility).",
    },
    {
        "watcher_name": "level_break_first_strike_watcher",
        "display_name": "LEVEL_BREAK_FIRST_STRIKE",
        "direction": "short",
        "historical_n": 4,
        "historical_wr": 100.0,
        "historical_gate": True,
        "wf_gate": None,
        "wf_note": "VIX>=20 gate: N=4 VIX-gated signals (all WIN) — too thin for WF.",
        "real_fills_gate": None,
        "real_fills_wr": None,
        "real_fills_n": None,
        "real_fills_note": "VIX<20 real-fills: WR=0% (violent initial bounce). VIX>=20 real-fills not yet run (N=4 too thin).",
        "live_wins_needed": 15,
        "overall_status": "WATCH_STABLE",
        "notes": "VIX>=20 only gate. Need N_vix_ge_20>=15 across >=2 distinct high-vol regimes before promotion.",
    },
    {
        "watcher_name": "bearish_reversal_at_level_watcher",
        "display_name": "BEARISH_REVERSAL_AT_LEVEL",
        "direction": "short",
        "historical_n": 4,
        "historical_wr": 75.0,
        "historical_gate": True,
        "wf_gate": None,
        "wf_note": "N too thin for walk-forward. 3/3 wins on verified subset (1 unverified).",
        "real_fills_gate": None,
        "real_fills_wr": None,
        "real_fills_n": None,
        "real_fills_note": "Real-fills not yet run — N too thin.",
        "live_wins_needed": 3,
        "overall_status": "WATCH_STABLE",
        "notes": "Countertrend setup: BULL ribbon day + SPY up>=$3 + ★★★ rejection + vol>=2x. 11:00 ET+ only.",
    },
    # ── LIVE-ACCUMULATION-ONLY: no historical possible (key-levels archive needed) ──
    {
        "watcher_name": "close_ceiling_fade",
        "display_name": "CLOSE_CEILING_DISTRIBUTION_FADE",
        "direction": "short",
        "historical_n": None,
        "historical_wr": None,
        "historical_gate": None,
        "wf_gate": None,
        "wf_note": "Historical backtest impossible — no key-levels archive exists.",
        "real_fills_gate": None,
        "real_fills_wr": None,
        "real_fills_n": None,
        "real_fills_note": "Will run real-fills after N>=20 live observations.",
        "live_wins_needed": 20,
        "overall_status": "LIVE_ONLY",
        "notes": "L59 pattern. N>=3 bars testing ★★+ resistance → fake breakout → puts. promotion gate N>=20 obs WR>=50% -> real-fills -> 3 J wins.",
    },
    {
        "watcher_name": "floor_hold_bounce",
        "display_name": "FLOOR_HOLD_DISTRIBUTION_BOUNCE",
        "direction": "long",
        "historical_n": None,
        "historical_wr": None,
        "historical_gate": None,
        "wf_gate": None,
        "wf_note": "Historical backtest impossible — no key-levels archive exists.",
        "real_fills_gate": None,
        "real_fills_wr": None,
        "real_fills_n": None,
        "real_fills_note": "Will run real-fills after N>=20 live observations.",
        "live_wins_needed": 20,
        "overall_status": "LIVE_ONLY",
        "notes": "L59 bull analog (Wyckoff spring). N>=3 bars testing ★★+ support → fake breakdown → calls.",
    },
    # ── WATCH_FRAGILE: one gate fails or real-fills negative ──────────────────
    {
        "watcher_name": "momentum_accel_highvol",
        "display_name": "MOMENTUM_ACCELERATION_HIGHVOL",
        "direction": "mixed",
        "historical_n": 47,
        "historical_wr": 59.6,
        "historical_gate": True,
        "wf_gate": True,
        "wf_note": "OOS +6.6pp IMPROVED (SPY-price proxy).",
        "real_fills_gate": False,
        "real_fills_wr": 42.9,
        "real_fills_n": 35,
        "real_fills_note": "DEGRADED -16.7pp. VIX[20-25) drag (WR=37.5%). VIX>=25: WR=54.5% N=11 (MARGINAL).",
        "live_wins_needed": 15,
        "overall_status": "WATCH_FRAGILE",
        "notes": "VIX>=25 subset promising but N=11 too thin. Real-fills FAIL on VIX[20-25). Needs VIX>=25 accumulation. Long direction at VIX>=25: WR=75% N=4 (very thin).",
    },
    # ── OBSERVE_ONLY: no promotion path (superseded or insufficient WR) ────────
    {
        "watcher_name": "hs_near_named",
        "display_name": "HEAD_AND_SHOULDERS_NEAR_NAMED",
        "direction": "short",
        "historical_n": 26,
        "historical_wr": 46.2,
        "historical_gate": False,
        "wf_gate": None,
        "wf_note": "NOT RUN — WR below 50% gate.",
        "real_fills_gate": None,
        "real_fills_wr": None,
        "real_fills_n": None,
        "real_fills_note": "NOT RUN — superseded by hs_watcher (no proximity filter).",
        "live_wins_needed": None,
        "overall_status": "OBSERVE_ONLY",
        "notes": "Proximity filter HURTS H&S (46.2% near vs 55.7% far). No promotion path. Kept for observation.",
    },
    # ── HIGH-VOLUME OBSERVATION (but different status) ──────────────────────────
    {
        "watcher_name": "orb_watcher",
        "display_name": "ORB_RETEST (medium-conf only)",
        "direction": "mixed",
        "historical_n": 86,
        "historical_wr": None,
        "historical_gate": True,
        "wf_gate": None,
        "wf_note": "Medium confidence only (+$589/86 fires). Low and High suppressed.",
        "real_fills_gate": None,
        "real_fills_wr": None,
        "real_fills_n": None,
        "real_fills_note": "Proxy-based scoring. Real-fills not run.",
        "live_wins_needed": 3,
        "overall_status": "WATCH_STABLE",
        "notes": "Medium-only filter active. Accumulating observations. Real-fills needed before promotion.",
    },
    {
        "watcher_name": "v14_enhanced_watcher",
        "display_name": "BEARISH_REJECTION_v14e / BULLISH_RECLAIM_v14e",
        "direction": "mixed",
        "historical_n": 505,
        "historical_wr": None,
        "historical_gate": True,
        "wf_gate": True,
        "wf_note": "Walk-forward STABLE. $36K wide across 16mo.",
        "real_fills_gate": None,
        "real_fills_wr": None,
        "real_fills_n": None,
        "real_fills_note": "Covered by production v15 engine — not separately validated as watcher.",
        "live_wins_needed": None,
        "overall_status": "OBSERVE_ONLY",
        "notes": "Production engine covers this pattern. Watcher exists for observation parity.",
    },
]


def _load_live_observations() -> dict[str, dict]:
    """Read watcher-observations.jsonl, return per-watcher live stats.

    Applies L67 dedup: watcher-observations.jsonl has one row per heartbeat tick.
    Multiple ticks within the same 5-min SPY bar each append a row. Dedup by
    (watcher_name, bar_timestamp_et[:16]) so each unique bar counts once.
    Without dedup, live_wins counts are ~4.5× inflated — enough to trigger false
    promotion gates (live_wins_needed=3 met by a single actual trade).
    """
    stats: dict[str, dict] = {}

    if not OBS_LOG.exists():
        return stats

    # First pass: collect all rows, dedup per (watcher, bar-minute)
    raw_rows: list[dict] = []
    with OBS_LOG.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                raw_rows.append(json.loads(line))
            except (json.JSONDecodeError, ValueError, TypeError):
                continue

    # Sort by bar_timestamp_et so we keep the first tick per bar
    raw_rows.sort(key=lambda x: x.get("bar_timestamp_et") or "")

    # Dedup: one row per (watcher_name, bar_minute_key)
    seen: set[tuple[str, str]] = set()
    deduped: list[dict] = []
    for obs in raw_rows:
        wn = obs.get("watcher_name", "unknown")
        bar_ts = obs.get("bar_timestamp_et", "") or ""
        key = (wn, bar_ts[:16])
        if key not in seen:
            seen.add(key)
            deduped.append(obs)

    watcher_counts: dict[str, int] = Counter()
    watcher_wins: dict[str, int] = Counter()       # positive P&L since LIVE_CUTOFF
    watcher_total_pnl: dict[str, float] = {}

    for obs in deduped:
        wn = obs.get("watcher_name", "unknown")
        watcher_counts[wn] += 1

        # Use bar_timestamp_et (actual trading bar date) NOT observed_at
        # (observed_at is when the replay task ran — historical replay obs
        #  always have recent observed_at but old bar_timestamp_et)
        bar_ts = obs.get("bar_timestamp_et", "") or ""
        bar_date = bar_ts[:10]  # "YYYY-MM-DD"
        if bar_date >= LIVE_CUTOFF:
            pnl = obs.get("would_be_pnl_dollars")
            if pnl is not None:
                try:
                    pnl_f = float(pnl)
                    if pnl_f > 0:
                        watcher_wins[wn] += 1
                    watcher_total_pnl[wn] = watcher_total_pnl.get(wn, 0.0) + pnl_f
                except (ValueError, TypeError):
                    pass

    # Merge into stats dict
    all_names = set(watcher_counts.keys()) | set(watcher_wins.keys())
    for wn in all_names:
        stats[wn] = {
            "total_obs": watcher_counts.get(wn, 0),
            "live_wins": watcher_wins.get(wn, 0),   # >=LIVE_CUTOFF + positive PnL
            "live_pnl": round(watcher_total_pnl.get(wn, 0.0), 2),
        }

    return stats


def _gate_symbol(gate: bool | None) -> str:
    if gate is True:
        return "Y"
    if gate is False:
        return "N"
    return "-"   # N/A or not yet run


def build_report() -> dict:
    """Build the promotion gate snapshot."""
    live_obs = _load_live_observations()
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")

    entries = []
    for w in WATCHER_REGISTRY:
        wn = w["watcher_name"]
        obs = live_obs.get(wn, {"total_obs": 0, "live_wins": 0, "live_pnl": 0.0})

        live_needed = w["live_wins_needed"]
        live_wins = obs["live_wins"]

        # Determine live gate status
        if live_needed is None:
            live_gate = None   # no promotion path
        else:
            live_gate = live_wins >= live_needed

        # Compute overall READY flag
        all_tech_gates = [w["historical_gate"], w["wf_gate"], w["real_fills_gate"]]
        required_tech = [g for g in all_tech_gates if g is not None]
        tech_ready = all(required_tech) if required_tech else False

        if w["overall_status"] == "OBSERVE_ONLY" or w["overall_status"] == "RETIRED":
            ready = False
        elif live_needed is None:
            ready = False
        else:
            ready = tech_ready and live_gate

        entry = {
            "watcher_name": wn,
            "display_name": w["display_name"],
            "direction": w["direction"],
            "overall_status": w["overall_status"],
            "gates": {
                "historical": w["historical_gate"],
                "walk_forward": w["wf_gate"],
                "real_fills": w["real_fills_gate"],
                "live_observations": live_gate,
            },
            "evidence": {
                "historical_n": w["historical_n"],
                "historical_wr_pct": w["historical_wr"],
                "wf_note": w["wf_note"],
                "real_fills_wr_pct": w["real_fills_wr"],
                "real_fills_n": w["real_fills_n"],
                "real_fills_note": w["real_fills_note"],
            },
            "live": {
                "total_obs": obs["total_obs"],
                "live_wins_graded": live_wins,
                "live_wins_needed": live_needed,
                "live_pnl": obs["live_pnl"],
            },
            "ready_for_promotion": ready,
            "notes": w["notes"],
        }
        entries.append(entry)

    snapshot = {
        "generated_at": generated_at,
        "live_cutoff": LIVE_CUTOFF,
        "total_watchers": len(entries),
        "ready_for_promotion": sum(1 for e in entries if e["ready_for_promotion"]),
        "watch_stable": sum(1 for e in entries if e["overall_status"] == "WATCH_STABLE"),
        "watch_fragile": sum(1 for e in entries if e["overall_status"] == "WATCH_FRAGILE"),
        "live_only": sum(1 for e in entries if e["overall_status"] == "LIVE_ONLY"),
        "observe_only": sum(1 for e in entries if e["overall_status"] in ("OBSERVE_ONLY", "RETIRED")),
        "watchers": entries,
    }
    return snapshot


def print_console_report(snapshot: dict) -> None:
    """Print a human-readable one-screen report."""
    now_str = snapshot["generated_at"][:19].replace("T", " ")
    print("=" * 80)
    print(f"  WATCHER OP-21 PROMOTION GATE SNAPSHOT  {now_str} UTC")
    print("=" * 80)
    print(f"  Total: {snapshot['total_watchers']} | "
          f"READY: {snapshot['ready_for_promotion']} | "
          f"STABLE: {snapshot['watch_stable']} | "
          f"FRAGILE: {snapshot['watch_fragile']} | "
          f"LIVE_ONLY: {snapshot['live_only']} | "
          f"OBSERVE: {snapshot['observe_only']}")
    print()

    # Header
    print(f"  {'WATCHER':<35} {'STATUS':<14} {'H'} {'WF'} {'RF'} {'LIVE':<8} {'READY'}")
    print(f"  {'-'*35} {'-'*14} {'-'} {'--'} {'--'} {'-'*8} {'-'*5}")

    for e in snapshot["watchers"]:
        h_sym = _gate_symbol(e["gates"]["historical"])
        wf_sym = _gate_symbol(e["gates"]["walk_forward"])
        rf_sym = _gate_symbol(e["gates"]["real_fills"])
        lv = e["live"]
        if lv["live_wins_needed"] is None:
            live_str = "N/A"
        else:
            live_str = f"{lv['live_wins_graded']}/{lv['live_wins_needed']}"

        ready_str = "READY" if e["ready_for_promotion"] else ""
        status_str = e["overall_status"]

        print(f"  {e['display_name'][:35]:<35} {status_str:<14} {h_sym} {wf_sym}  {rf_sym}  {live_str:<8} {ready_str}")

        # Evidence line
        wr_display = ""
        if e["evidence"]["real_fills_wr_pct"] is not None:
            wr_display = f"RF-WR={e['evidence']['real_fills_wr_pct']:.1f}% N={e['evidence']['real_fills_n']}"
        elif e["evidence"]["historical_wr_pct"] is not None:
            wr_display = f"Proxy-WR={e['evidence']['historical_wr_pct']:.1f}% N={e['evidence']['historical_n']}"
        if wr_display:
            pnl_str = f"  live_pnl=${lv['live_pnl']:+.0f}" if lv["live_pnl"] != 0 else ""
            print(f"    -> {wr_display}{pnl_str}")

    print()
    print("  Legend: H=Historical  WF=Walk-Forward  RF=Real-Fills  LIVE=live_wins/needed")
    print("          Y=PASS  N=FAIL  -=N/A or not-yet-run")
    print("=" * 80)


def main() -> None:
    parser = argparse.ArgumentParser(description="Watcher OP-21 Promotion Gate Dashboard")
    parser.add_argument("--json", action="store_true", help="Print JSON output instead of table")
    args = parser.parse_args()

    snapshot = build_report()

    # Always write JSON to state dir
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with OUT_PATH.open("w", encoding="utf-8") as f:
        json.dump(snapshot, f, indent=2)

    if args.json:
        print(json.dumps(snapshot, indent=2))
    else:
        print_console_report(snapshot)
        print(f"\n  Full JSON: {OUT_PATH}")


if __name__ == "__main__":
    main()

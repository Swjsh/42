"""V14E HIGH-CONF+VIX_MODERATE promotion gate monitor.

Tracks progress toward the OP-21 sub-tier promotion gate for:
  direction=short + confidence=high + VIX_MODERATE (15<=VIX<20)

Evidence from fingerprint (2026-05-21):
  - Historical (training): N=24, WR=95.8%, P&L=+$1,281 (VIX_MODERATE)
  - Gold sub-tier: score=10 + VIX_MODERATE = N=18, WR=100%, P&L=+$871 (ZERO LOSSES)
  - VIX_ELEVATED: N=7, WR=57%; VIX_HIGH: N=2, WR=50% — no edge

OP-21 Promotion Gate (fast-track Path B):
  - N_new >= 15 live observations at VIX_MODERATE (post gate-deployment date)
  - WR_new >= 75%
  - >=8 distinct trading dates
  - Single-date concentration <= 30%
  Gate-deployment date: 2026-05-21 (V14E_DIRECTION_FILTER="bear" wired)

Output: analysis/recommendations/v14e-highconf-vix-monitor.json
"""
from __future__ import annotations

import os as _os, sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "v14e-highconf-vix-monitor.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "v14e-highconf-vix-monitor.stderr.log", "a", buffering=1, encoding="utf-8")

import datetime as dt
import json
import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(REPO))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

OBS_PATH = ROOT / "automation" / "state" / "watcher-observations.jsonl"
OUT_JSON = ROOT / "analysis" / "recommendations" / "v14e-highconf-vix-monitor.json"

# Gate-deployment date: V14E_DIRECTION_FILTER="bear" wired (engine-benefit, 2026-05-21)
GATE_DEPLOYMENT_DATE = "2026-05-21"

# OP-21 promotion gate thresholds (Path B fast-track)
PROMO_N_MIN = 15
PROMO_WR_MIN = 0.75
PROMO_DATES_MIN = 8
PROMO_CONCENTRATION_MAX = 0.30   # no single date > 30% of live obs

# VIX regime boundaries (must match v14_enhanced_watcher._vix_regime)
VIX_LOW_MAX = 15.0
VIX_MOD_MAX = 20.0
VIX_ELEV_MAX = 25.0

# VIX data — prefer latest merged CSV
for _cand in [
    "vix_5m_2025-01-01_2026-05-19_merged.csv",
    "vix_5m_2025-01-01_2026-05-15.csv",
    "vix_5m_2025-01-01_2026-05-12.csv",
]:
    _p = REPO / "data" / _cand
    if _p.exists():
        VIX_PATH: Optional[Path] = _p
        break
else:
    VIX_PATH = None


def _vix_regime(vix: float) -> str:
    """Classify VIX into regime buckets (mirrors v14_enhanced_watcher._vix_regime)."""
    if vix <= 0:
        return "UNKNOWN"
    if vix < VIX_LOW_MAX:
        return "VIX_LOW"
    if vix < VIX_MOD_MAX:
        return "VIX_MODERATE"
    if vix < VIX_ELEV_MAX:
        return "VIX_ELEVATED"
    return "VIX_HIGH"


def _load_vix_index(path: Path) -> pd.Series:
    """Load VIX 5m data; return Series indexed by tz-naive ET timestamp."""
    df = pd.read_csv(path)
    df["ts"] = pd.to_datetime(df["timestamp_et"], utc=False)
    df = df.sort_values("ts").set_index("ts")
    return df["close"]


def _vix_at(vix_index: pd.Series, bar_ts: str) -> float:
    """Return VIX close at or just before bar_ts. Returns -1.0 if not found.

    bar_ts may carry a UTC offset (e.g. '2026-04-23T13:10:00-04:00').
    The VIX index is tz-naive ET. Normalize by stripping offset (tz-localise
    treats the wall-clock time as ET, which is correct since the bar is already
    in local ET time).
    """
    try:
        target = pd.Timestamp(bar_ts)
        # Strip timezone info — bar_ts is already in ET wall-clock time.
        # tz_localize(None) raises TypeError on tz-aware; use replace() to strip.
        if target.tzinfo is not None:
            target = target.replace(tzinfo=None)
        mask = vix_index.index <= target
        if not mask.any():
            return -1.0
        return float(vix_index[mask].iloc[-1])
    except Exception:
        return -1.0


def _load_observations() -> list[dict]:
    """Load high-conf short v14e observations from watcher-observations.jsonl."""
    rows: list[dict] = []
    seen: set[str] = set()

    for line in OBS_PATH.read_text(encoding="utf-8-sig").strip().split("\n"):
        if not line.strip():
            continue
        d = json.loads(line)
        if "v14" not in d.get("watcher_name", "").lower():
            continue
        if d.get("direction") != "short":
            continue
        if d.get("confidence") != "high":
            continue
        if d.get("would_be_pnl_dollars") is None:
            continue
        key = d.get("bar_timestamp_et", "")[:16]
        if key in seen:
            continue
        seen.add(key)
        rows.append(d)

    rows.sort(key=lambda x: x.get("bar_timestamp_et", ""))
    return rows


def _enrich_with_vix(rows: list[dict], vix_index: Optional[pd.Series]) -> list[dict]:
    """Add vix_value + vix_regime to each observation record."""
    enriched = []
    for row in rows:
        # Use metadata vix_at_signal if available (post-tagging obs from 2026-05-21+)
        meta = row.get("metadata") or {}
        vix_val = meta.get("vix_at_signal")
        vix_reg = meta.get("vix_regime")

        if (vix_val is None or vix_val <= 0) and vix_index is not None:
            bar_ts = row.get("bar_timestamp_et", "")
            vix_val = _vix_at(vix_index, bar_ts)
            vix_reg = _vix_regime(vix_val) if vix_val > 0 else "UNKNOWN"

        if vix_reg is None:
            vix_reg = "UNKNOWN"

        enriched.append({
            "date": (row.get("bar_timestamp_et") or "?")[:10],
            "bar_ts": (row.get("bar_timestamp_et") or "?")[:16],
            "pnl": float(row["would_be_pnl_dollars"]),
            "outcome": row.get("would_be_outcome", "?"),
            "vix": round(float(vix_val), 2) if vix_val and vix_val > 0 else None,
            "vix_regime": vix_reg,
            "score": (row.get("metadata") or {}).get("score"),
            "is_live": row.get("bar_timestamp_et", "")[:10] >= GATE_DEPLOYMENT_DATE,
        })
    return enriched


def _regime_stats(obs: list[dict]) -> dict:
    """Return per-VIX-regime stats dict."""
    regimes: dict[str, list[float]] = {}
    for o in obs:
        reg = o["vix_regime"]
        regimes.setdefault(reg, []).append(o["pnl"])

    result: dict[str, dict] = {}
    for reg, pnls in sorted(regimes.items()):
        wins = sum(1 for p in pnls if p > 0)
        result[reg] = {
            "n": len(pnls),
            "wins": wins,
            "wr": round(wins / len(pnls), 4) if pnls else None,
            "wr_pct": round(wins / len(pnls) * 100, 1) if pnls else None,
            "total_pnl": round(sum(pnls), 2),
            "avg_pnl": round(sum(pnls) / len(pnls), 2) if pnls else None,
        }
    return result


def _promotion_status(live_obs: list[dict]) -> dict:
    """Assess OP-21 promotion gate progress for live VIX_MODERATE obs."""
    mod_obs = [o for o in live_obs if o["vix_regime"] == "VIX_MODERATE"]
    n = len(mod_obs)
    wins = sum(1 for o in mod_obs if o["pnl"] > 0)
    wr = wins / n if n > 0 else 0.0
    dates = sorted(set(o["date"] for o in mod_obs))
    n_dates = len(dates)

    # Concentration: pct from the top date
    date_counts: dict[str, int] = {}
    for o in mod_obs:
        date_counts[o["date"]] = date_counts.get(o["date"], 0) + 1
    max_pct = max(v / n for v in date_counts.values()) if n > 0 else 0.0

    n_ok = n >= PROMO_N_MIN
    wr_ok = wr >= PROMO_WR_MIN
    dates_ok = n_dates >= PROMO_DATES_MIN
    conc_ok = max_pct <= PROMO_CONCENTRATION_MAX

    return {
        "n_vix_moderate": n,
        "wins": wins,
        "wr": round(wr, 4),
        "wr_pct": round(wr * 100, 1),
        "n_distinct_dates": n_dates,
        "max_single_date_pct": round(max_pct, 4),
        "gates": {
            "n_ge_15": {"required": PROMO_N_MIN, "actual": n, "pass": n_ok},
            "wr_ge_75pct": {"required": PROMO_WR_MIN, "actual": round(wr, 4), "pass": wr_ok},
            "dates_ge_8": {"required": PROMO_DATES_MIN, "actual": n_dates, "pass": dates_ok},
            "concentration_le_30pct": {"required": PROMO_CONCENTRATION_MAX, "actual": round(max_pct, 4), "pass": conc_ok},
        },
        "all_gates_pass": bool(n_ok and wr_ok and dates_ok and conc_ok),
        "verdict": "PROMOTE" if (n_ok and wr_ok and dates_ok and conc_ok) else "ACCUMULATING",
        "pct_complete_n": round(n / PROMO_N_MIN * 100, 1),
        "pct_complete_dates": round(n_dates / PROMO_DATES_MIN * 100, 1),
    }


def main() -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    log.info("Loading v14e high-conf bear observations...")
    rows = _load_observations()
    log.info("Total high-conf short v14e obs: %d", len(rows))

    vix_index: Optional[pd.Series] = None
    if VIX_PATH:
        log.info("Loading VIX data from %s...", VIX_PATH.name)
        vix_index = _load_vix_index(VIX_PATH)
    else:
        log.warning("No VIX CSV found — VIX regime will be UNKNOWN for pre-tagged obs")

    log.info("Enriching observations with VIX regime...")
    enriched = _enrich_with_vix(rows, vix_index)

    hist = [o for o in enriched if not o["is_live"]]
    live = [o for o in enriched if o["is_live"]]

    log.info("\n========== HISTORICAL (training evidence) ==========")
    log.info("N=%d  |  Date range: %s to %s", len(hist),
             hist[0]["date"] if hist else "N/A", hist[-1]["date"] if hist else "N/A")
    hist_stats = _regime_stats(hist)
    for reg, s in hist_stats.items():
        log.info("  %-20s  N=%d  WR=%.1f%%  P&L=$%+.0f", reg, s["n"], s["wr_pct"], s["total_pnl"])

    log.info("\n========== LIVE (post gate-deployment: %s) ==========", GATE_DEPLOYMENT_DATE)
    log.info("N=%d live observations", len(live))
    if live:
        live_stats = _regime_stats(live)
        for reg, s in live_stats.items():
            log.info("  %-20s  N=%d  WR=%.1f%%  P&L=$%+.0f", reg, s["n"], s["wr_pct"] or 0, s["total_pnl"])
    else:
        log.info("  No live observations yet — accumulation begins today (2026-05-21)")
        live_stats = {}

    log.info("\n========== OP-21 PROMOTION GATE PROGRESS ==========")
    promo = _promotion_status(live)
    log.info("N_VIX_MODERATE live:  %d / %d required  (%s%% complete)",
             promo["n_vix_moderate"], PROMO_N_MIN, promo["pct_complete_n"])
    log.info("WR:                   %.1f%% / %.0f%% required  [%s]",
             promo["wr_pct"], PROMO_WR_MIN * 100, "PASS" if promo["gates"]["wr_ge_75pct"]["pass"] else "pending")
    log.info("Distinct dates:       %d / %d required  (%s%% complete)",
             promo["n_distinct_dates"], PROMO_DATES_MIN, promo["pct_complete_dates"])
    log.info("Max single-date conc: %.1f%% / %.0f%% limit  [%s]",
             promo["max_single_date_pct"] * 100, PROMO_CONCENTRATION_MAX * 100,
             "OK" if promo["gates"]["concentration_le_30pct"]["pass"] else "CONCENTRATED")
    log.info("VERDICT: %s", promo["verdict"])

    # Output
    output = {
        "monitor": "V14E HIGH-CONF+VIX_MODERATE promotion gate",
        "generated_at": dt.datetime.now().isoformat(),
        "gate_deployment_date": GATE_DEPLOYMENT_DATE,
        "vix_data_source": VIX_PATH.name if VIX_PATH else "none",
        "dedup_note": (
            "Observations are deduplicated by bar_timestamp_et[:16] (minute precision). "
            "The fingerprint (analysis/backtests/v14e-bear-gate/highconf_fingerprint.json) "
            "reported N=33 (undeduplicated, multiple watcher ticks per bar). "
            "This monitor reports N=16 unique bars — the correct count for P&L purposes "
            "(in production only one entry fires per bar via first_entry_lock)."
        ),
        "promotion_gate": {
            "n_min": PROMO_N_MIN,
            "wr_min": PROMO_WR_MIN,
            "dates_min": PROMO_DATES_MIN,
            "concentration_max": PROMO_CONCENTRATION_MAX,
        },
        "historical_evidence": {
            "n_total": len(hist),
            "by_vix_regime": hist_stats,
            "vix_moderate_wr": hist_stats.get("VIX_MODERATE", {}).get("wr_pct"),
            "vix_moderate_n": hist_stats.get("VIX_MODERATE", {}).get("n"),
        },
        "live_observations": {
            "n_total": len(live),
            "by_vix_regime": live_stats,
        },
        "promotion_status": promo,
        "op21_ref": "strategy/candidates/2026-05-21-v14e-quality-filter.md#path-b",
    }

    OUT_JSON.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log.info("\nOutput: %s", OUT_JSON)


if __name__ == "__main__":
    main()

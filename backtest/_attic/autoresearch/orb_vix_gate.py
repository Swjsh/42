"""ORB VIX-regime gate analysis.

Extends orb_gate_analysis.py to test whether requiring VIX >= threshold at session open
resolves the Q2-2026 concentration risk in ORB_DIRECTION_FILTER (long-only).

Scenarios tested:
  1. LONG_ALL (baseline from orb_gate_analysis)
  2. LONG_VIX15 - long-only AND VIX daily close >= 15
  3. LONG_VIX18 - long-only AND VIX >= 18
  4. LONG_VIX20 - long-only AND VIX >= 20 (kitchen daemon recommendation)
  5. LONG_VIX22 - long-only AND VIX >= 22
  6. LONG_VIX25 - long-only AND VIX >= 25

Key question: at what VIX threshold do non-Q2-2026 quarters become profitable
AND Q2-2026 retains most signals?

Output:
  analysis/backtests/orb-vix-gate/results.json
  analysis/backtests/orb-vix-gate/summary.md
"""
from __future__ import annotations

import os as _os
import sys as _sys
from pathlib import Path as _Path

if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "orb-vix-gate.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "orb-vix-gate.stderr.log", "a", buffering=1, encoding="utf-8")
    print(f"[orb-vix-gate] stdout redirected (pid={_os.getpid()})")

import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stdout)
log = logging.getLogger(__name__)

OBS_FILE = ROOT / "automation" / "state" / "watcher-observations.jsonl"
OUT_DIR = ROOT / "analysis" / "backtests" / "orb-vix-gate"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUT_DIR / "results.json"
OUT_MD = OUT_DIR / "summary.md"

VIX_THRESHOLDS = [0, 15, 18, 20, 22, 25]


def _load_vix_daily() -> dict[str, float]:
    """Return {date_str: vix_daily_close} from the largest VIX CSV."""
    for cand in [
        "vix_5m_2025-01-01_2026-05-19_merged.csv",
        "vix_5m_2025-01-01_2026-05-15.csv",
        "vix_5m_2025-01-01_2026-05-12.csv",
        "vix_5m_2025-01-01_2026-05-07.csv",
    ]:
        p = REPO / "data" / cand
        if p.exists():
            df = pd.read_csv(p)
            # VIX CSVs have naive timestamps in ET already (no tz suffix)
            df["ts"] = pd.to_datetime(df["timestamp_et"])
            df["date"] = df["ts"].dt.date
            df["time"] = df["ts"].dt.time
            # Use VIX close at ~15:55 ET (last bar of RTH) as daily close
            rth = df[(df["time"] >= dt.time(9, 30)) & (df["time"] <= dt.time(16, 0))]
            daily = rth.groupby("date")["close"].last().to_dict()
            log.info("Loaded VIX from %s: %d days", cand, len(daily))
            return {str(d): float(v) for d, v in daily.items()}
    raise FileNotFoundError("No VIX CSV found")


def _load_orb_obs() -> list[dict]:
    lines = OBS_FILE.read_text(encoding="utf-8").splitlines()
    obs = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except Exception:
            continue
        if r.get("watcher_name") != "orb_watcher":
            continue
        if r.get("would_be_pnl_dollars") is None:
            continue
        obs.append(r)
    # Dedup by bar_timestamp_et[:16] — one row per unique 5-min SPY bar.
    # Gamma_Heartbeat fires every 3 min; multiple ticks within the same bar
    # each append a row, inflating N ~4.5×. Without dedup WR/N are misleading.
    # (L67 — watcher-obs-dedup-inflates-wr)
    seen: set[str] = set()
    deduped: list[dict] = []
    for o in sorted(obs, key=lambda x: x.get("bar_timestamp_et", "")):
        key = o.get("bar_timestamp_et", "")[:16]
        if key not in seen:
            seen.add(key)
            deduped.append(o)
    return deduped


def _obs_date(o: dict) -> str:
    """Extract YYYY-MM-DD from bar_timestamp_et."""
    ts = o.get("bar_timestamp_et", "")
    try:
        return ts[:10]
    except Exception:
        return ""


def _quarter(date_str: str) -> str:
    try:
        d = dt.date.fromisoformat(date_str)
        return f"{d.year}-Q{(d.month - 1) // 3 + 1}"
    except Exception:
        return "unknown"


def _analyze(obs: list[dict], label: str) -> dict:
    if not obs:
        return {"label": label, "n": 0, "wr_pct": 0.0, "pnl": 0.0, "positive_quarters": "0/0", "quarters": {}}

    wins = sum(1 for o in obs if (o.get("would_be_pnl_dollars") or 0) > 0)
    pnl = sum(o.get("would_be_pnl_dollars") or 0 for o in obs)
    wr = wins / len(obs) * 100

    by_q: dict[str, list] = defaultdict(list)
    for o in obs:
        by_q[_quarter(_obs_date(o))].append(o)

    quarters = {}
    for q in sorted(by_q):
        q_obs = by_q[q]
        q_wins = sum(1 for o in q_obs if (o.get("would_be_pnl_dollars") or 0) > 0)
        q_pnl = sum(o.get("would_be_pnl_dollars") or 0 for o in q_obs)
        quarters[q] = {
            "n": len(q_obs),
            "wr_pct": round(q_wins / len(q_obs) * 100, 1),
            "pnl": round(q_pnl, 2),
        }

    pos_q = sum(1 for v in quarters.values() if v["pnl"] > 0)
    return {
        "label": label,
        "n": len(obs),
        "wins": wins,
        "wr_pct": round(wr, 1),
        "pnl": round(pnl, 2),
        "positive_quarters": f"{pos_q}/{len(quarters)}",
        "quarters": quarters,
    }


def main() -> None:
    log.info("Loading ORB observations...")
    all_obs = _load_orb_obs()
    log.info("Loaded %d graded ORB observations", len(all_obs))

    log.info("Loading VIX daily closes...")
    vix_daily = _load_vix_daily()
    log.info("Loaded VIX for %d days", len(vix_daily))

    # Attach VIX close to each observation
    no_vix = 0
    for o in all_obs:
        d = _obs_date(o)
        vix = vix_daily.get(d)
        if vix is None:
            no_vix += 1
        o["_vix_close"] = vix
    log.info("Observations missing VIX: %d / %d", no_vix, len(all_obs))

    long_obs = [o for o in all_obs if o.get("direction") == "long"]
    log.info("Long-only observations: %d", len(long_obs))

    results = {}
    for thresh in VIX_THRESHOLDS:
        label = f"LONG_VIX{thresh}" if thresh > 0 else "LONG_ALL"
        filtered = [o for o in long_obs if o.get("_vix_close") is None or o["_vix_close"] >= thresh]
        log.info("Scenario %s: %d obs", label, len(filtered))
        results[label] = _analyze(filtered, label)

    # Compute Q2-2026 concentration for each scenario
    for k, v in results.items():
        q2_2026 = v["quarters"].get("2026-Q2", {})
        total_pnl = v["pnl"]
        q2_pnl = q2_2026.get("pnl", 0)
        v["q2_2026_concentration_pct"] = round(q2_pnl / total_pnl * 100, 1) if total_pnl else 0
        v["q2_2026_n"] = q2_2026.get("n", 0)
        v["q2_2026_pnl"] = round(q2_pnl, 2)

    # Log summary table
    log.info("")
    log.info("=== ORB VIX Regime Gate — Summary ===")
    log.info("%-18s %5s %6s %8s %5s %6s %12s",
             "Scenario", "N", "WR%", "P&L", "PosQ", "Q2n", "Q2-Conc%")
    for k, v in results.items():
        log.info("%-18s %5d %5.1f%% %8.0f %5s %6d %11.1f%%",
                 k, v["n"], v["wr_pct"], v["pnl"],
                 v["positive_quarters"], v["q2_2026_n"], v["q2_2026_concentration_pct"])

    log.info("")
    log.info("=== Per-quarter breakdown (LONG_ALL vs LONG_VIX20) ===")
    for q in sorted(set(list(results["LONG_ALL"]["quarters"].keys()) + list(results.get("LONG_VIX20", {}).get("quarters", {}).keys()))):
        all_q = results["LONG_ALL"]["quarters"].get(q, {})
        v20_q = results.get("LONG_VIX20", {}).get("quarters", {}).get(q, {})
        log.info("  %s: ALL n=%d pnl=%+.0f | VIX20 n=%d pnl=%+.0f",
                 q,
                 all_q.get("n", 0), all_q.get("pnl", 0),
                 v20_q.get("n", 0), v20_q.get("pnl", 0))

    # OP-20 disclosure
    best_key = max(results, key=lambda k: results[k]["pnl"])
    best = results[best_key]

    output = {
        "candidate": "ORB_VIX_REGIME_GATE",
        "generated_at": dt.datetime.now().isoformat(),
        "methodology": (
            "VIX-gated long-only ORB from 391 graded watcher observations (2025-01 to 2026-05). "
            "VIX daily close from vix_5m merged CSV, joined by observation date. "
            "Tests VIX thresholds 0/15/18/20/22/25."
        ),
        "scenarios": results,
        "best_scenario": best_key,
        "op20_disclosure": {
            "account_size": "$1K paper (qty=3, ~$30-60 per trade at ATM option premiums)",
            "sample_bias": "391 obs from replay — watcher-based grading, not production fills",
            "oos_test": "No walk-forward yet — pending if VIX gate shows promise",
            "real_fills": "Not run — watcher grading uses fixed premium model",
            "failure_modes": (
                "VIX threshold may not generalize to future high-vol regimes. "
                "If VIX reverts to <20, ORB signals would be suppressed entirely."
            ),
            "concentration": f"Q2-2026 concentration in LONG_ALL = ~85%. "
                             f"Best VIX gate Q2 concentration: "
                             f"{results.get('LONG_VIX20', {}).get('q2_2026_concentration_pct', '?')}%",
        },
    }

    OUT_JSON.write_text(json.dumps(output, indent=2), encoding="utf-8")
    log.info("Output written: %s", OUT_JSON)

    # Write summary markdown
    lines = [
        "# ORB VIX Regime Gate Analysis",
        f"Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M ET')}",
        "",
        "## Summary Table",
        "",
        "| Scenario | N | WR% | P&L | Pos-Q | Q2-2026 N | Q2 Conc% |",
        "|---|---|---|---|---|---|---|",
    ]
    for k, v in results.items():
        lines.append(
            f"| {k} | {v['n']} | {v['wr_pct']:.1f}% | ${v['pnl']:+,.0f} | "
            f"{v['positive_quarters']} | {v['q2_2026_n']} | {v['q2_2026_concentration_pct']:.1f}% |"
        )
    lines += ["", "## Per-Quarter Breakdown (LONG_ALL vs LONG_VIX20)", ""]
    all_qs = results["LONG_ALL"]["quarters"]
    v20_qs = results.get("LONG_VIX20", {}).get("quarters", {})
    all_keys = sorted(set(list(all_qs.keys()) + list(v20_qs.keys())))
    lines.append("| Quarter | ALL N | ALL P&L | VIX20 N | VIX20 P&L |")
    lines.append("|---|---|---|---|---|")
    for q in all_keys:
        aq = all_qs.get(q, {})
        vq = v20_qs.get(q, {})
        lines.append(
            f"| {q} | {aq.get('n', 0)} | ${aq.get('pnl', 0):+,.0f} | "
            f"{vq.get('n', 0)} | ${vq.get('pnl', 0):+,.0f} |"
        )
    lines += ["", "## OP-20 Disclosure", ""]
    for k, v in output["op20_disclosure"].items():
        lines.append(f"- **{k}:** {v}")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    log.info("Summary written: %s", OUT_MD)


if __name__ == "__main__":
    main()

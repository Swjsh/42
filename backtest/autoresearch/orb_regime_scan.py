"""ORB regime gate comprehensive scan — correct quarter parsing.

Tests gate combinations to find which OR-range + direction gate maximizes both
P&L AND quarter distribution (resolving the Q2-2026 concentration risk).

orb_gate_analysis.py had a broken _quarter() function that put most observations
in "unknown". This script uses the correct approach (ts[:10] → date.fromisoformat).

Scenarios:
  1. LONG_ALL
  2. LONG_OR_LT1.50 — or_range < 1.50
  3. LONG_OR_LT2.00 — or_range < 2.00 (leaderboard candidate #4)
  4. LONG_OR_GT1.50 — or_range >= 1.50 (wider ORB)
  5. LONG_OR_GT2.00 — or_range >= 2.00 (very wide ORB)
  6. LONG_OR_1.50_to_3.00 — "Goldilocks" range

Output:
  analysis/backtests/orb-regime-scan/results.json
  analysis/backtests/orb-regime-scan/summary.md
"""
from __future__ import annotations

import os as _os
import sys as _sys
from pathlib import Path as _Path

if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "orb-regime-scan.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "orb-regime-scan.stderr.log", "a", buffering=1, encoding="utf-8")
    print(f"[orb-regime-scan] stdout redirected (pid={_os.getpid()})")

import datetime as dt
import json
import logging
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                    stream=sys.stdout)
log = logging.getLogger(__name__)

OBS_FILE = ROOT / "automation" / "state" / "watcher-observations.jsonl"
OUT_DIR = ROOT / "analysis" / "backtests" / "orb-regime-scan"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUT_DIR / "results.json"
OUT_MD = OUT_DIR / "summary.md"


def _obs_date(o: dict) -> str:
    ts = o.get("bar_timestamp_et", "")
    return ts[:10] if len(ts) >= 10 else ""


def _quarter(date_str: str) -> str:
    try:
        d = dt.date.fromisoformat(date_str)
        return f"{d.year}-Q{(d.month - 1) // 3 + 1}"
    except Exception:
        return "unknown"


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


def _analyze(obs: list[dict], label: str) -> dict:
    if not obs:
        return {
            "label": label, "n": 0, "wr_pct": 0.0, "pnl": 0.0,
            "positive_quarters": "0/0", "quarters": {}, "or_range_mean": 0.0,
        }

    wins = sum(1 for o in obs if (o.get("would_be_pnl_dollars") or 0) > 0)
    pnl = sum(o.get("would_be_pnl_dollars") or 0 for o in obs)
    wr = wins / len(obs) * 100

    or_ranges = [
        (o.get("metadata") or {}).get("or_range", 0)
        for o in obs
    ]
    or_range_mean = sum(or_ranges) / len(or_ranges) if or_ranges else 0

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

    pos_q = sum(1 for q, v in quarters.items() if v["pnl"] > 0 and q != "unknown")
    total_q = sum(1 for q in quarters if q != "unknown")

    # Q2-2026 concentration
    q2_2026_pnl = quarters.get("2026-Q2", {}).get("pnl", 0)
    concentration = round(q2_2026_pnl / pnl * 100, 1) if pnl else 0

    return {
        "label": label,
        "n": len(obs),
        "wins": wins,
        "wr_pct": round(wr, 1),
        "pnl": round(pnl, 2),
        "or_range_mean": round(or_range_mean, 2),
        "positive_quarters": f"{pos_q}/{total_q}",
        "q2_2026_concentration_pct": concentration,
        "quarters": quarters,
    }


def main() -> None:
    log.info("Loading ORB observations...")
    all_obs = _load_orb_obs()
    log.info("Loaded %d graded ORB observations", len(all_obs))

    long_obs = [o for o in all_obs if o.get("direction") == "long"]
    log.info("Long-only: %d obs", len(long_obs))

    def or_range(o: dict) -> float:
        return (o.get("metadata") or {}).get("or_range", 9999.0)

    scenarios = {
        "LONG_ALL": long_obs,
        "LONG_OR_LT1.50": [o for o in long_obs if or_range(o) < 1.50],
        "LONG_OR_LT2.00": [o for o in long_obs if or_range(o) < 2.00],
        "LONG_OR_GT1.50": [o for o in long_obs if or_range(o) >= 1.50],
        "LONG_OR_GT2.00": [o for o in long_obs if or_range(o) >= 2.00],
        "LONG_OR_1.5_to_3.0": [o for o in long_obs if 1.50 <= or_range(o) < 3.00],
    }

    results = {}
    for name, obs in scenarios.items():
        results[name] = _analyze(obs, name)
        log.info("%-22s N=%d WR=%.1f%% P&L=%+.0f PosQ=%s Q2conc=%.0f%%",
                 name, results[name]["n"], results[name]["wr_pct"],
                 results[name]["pnl"], results[name]["positive_quarters"],
                 results[name]["q2_2026_concentration_pct"])

    log.info("")
    log.info("=== Per-quarter for LONG_ALL and LONG_OR_LT2.00 ===")
    all_qs = sorted(set(
        list(results["LONG_ALL"]["quarters"].keys()) +
        list(results["LONG_OR_LT2.00"]["quarters"].keys())
    ))
    log.info("%-12s  ALL(n/pnl)    OR<2(n/pnl)", "Quarter")
    for q in all_qs:
        aq = results["LONG_ALL"]["quarters"].get(q, {"n": 0, "pnl": 0})
        lq = results["LONG_OR_LT2.00"]["quarters"].get(q, {"n": 0, "pnl": 0})
        log.info("%-12s  %3d/%+6.0f    %3d/%+6.0f",
                 q, aq["n"], aq["pnl"], lq["n"], lq["pnl"])

    log.info("")
    log.info("=== Per-quarter for LONG_OR_GT2.00 ===")
    for q in sorted(results["LONG_OR_GT2.00"]["quarters"]):
        v = results["LONG_OR_GT2.00"]["quarters"][q]
        log.info("  %s: n=%d WR=%.0f%% pnl=%+.0f", q, v["n"], v["wr_pct"], v["pnl"])

    output = {
        "candidate": "ORB_REGIME_SCAN (or_range gates, correct quarter parsing)",
        "generated_at": dt.datetime.now().isoformat(),
        "vix_gate_finding": (
            "VIX>=20 is WRONG direction. Q2-2026 ORB signals (133 obs) had VIX<20. "
            "VIX>=20 removes profitable signals, keeps losing ones. VIX is not the discriminator."
        ),
        "scenarios": results,
    }

    OUT_JSON.write_text(json.dumps(output, indent=2), encoding="utf-8")
    log.info("Output written: %s", OUT_JSON)

    # Write summary
    lines = [
        "# ORB Regime Scan — OR-Range Gates (Correct Quarter Parsing)",
        f"Generated: {dt.datetime.now().strftime('%Y-%m-%d %H:%M ET')}",
        "",
        "**VIX Gate Finding:** VIX>=20 is the WRONG direction. Q2-2026 ORB signals (133 obs) had VIX<20.",
        "VIX>=20 removes Q2-2026 signals entirely while keeping the bad VIX-spike observations.",
        "",
        "## Summary Table",
        "",
        "| Scenario | N | WR% | P&L | Pos-Q | Q2 Conc% | OR-Range Mean |",
        "|---|---|---|---|---|---|---|",
    ]
    for k, v in results.items():
        lines.append(
            f"| {k} | {v['n']} | {v['wr_pct']:.1f}% | ${v['pnl']:+,.0f} | "
            f"{v['positive_quarters']} | {v['q2_2026_concentration_pct']:.0f}% | {v['or_range_mean']:.2f} |"
        )
    lines += [
        "",
        "## Per-Quarter: LONG_ALL vs LONG_OR_LT2.00",
        "",
        "| Quarter | ALL N | ALL P&L | OR<2 N | OR<2 P&L |",
        "|---|---|---|---|---|",
    ]
    all_qs = sorted(set(
        list(results["LONG_ALL"]["quarters"].keys()) +
        list(results["LONG_OR_LT2.00"]["quarters"].keys())
    ))
    for q in all_qs:
        aq = results["LONG_ALL"]["quarters"].get(q, {"n": 0, "pnl": 0})
        lq = results["LONG_OR_LT2.00"]["quarters"].get(q, {"n": 0, "pnl": 0})
        lines.append(
            f"| {q} | {aq['n']} | ${aq['pnl']:+,.0f} | {lq['n']} | ${lq['pnl']:+,.0f} |"
        )

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")
    log.info("Summary written: %s", OUT_MD)


if __name__ == "__main__":
    main()

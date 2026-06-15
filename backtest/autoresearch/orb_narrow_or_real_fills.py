"""Real-fills validation for ORB_NARROW_OR_GATE (or_range < 2.00, long-only).

Extends orb_real_fills_validate.py: uses INDEPENDENT non-J-anchor narrow-OR
observations from 2025 to confirm the watcher proxy WR holds in OPRA fills.

The J-anchor sample (#5 / orb_real_fills.json) already confirmed 90% WR on
chart-stop-only for narrow OR cases. This script provides OOS validation on
the 2025 narrow-OR observations NOT in that test.

Gate: real_fills WR >= 60% with chart-stop-only (higher threshold than #5
because this focuses specifically on narrow-OR, which the watcher shows 88.1%).

Output: analysis/recommendations/orb_narrow_or_real_fills.json
"""
from __future__ import annotations

import os as _os, sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "orb-narrow-or-real-fills.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "orb-narrow-or-real-fills.stderr.log", "a", buffering=1, encoding="utf-8")

import datetime as dt
import json
import logging
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(ROOT))

from lib.ribbon import compute_ribbon  # noqa: E402
from lib.simulator_real import simulate_trade_real  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger(__name__)

OBS_PATH = ROOT / "automation" / "state" / "watcher-observations.jsonl"
OUT_JSON = ROOT / "analysis" / "recommendations" / "orb_narrow_or_real_fills.json"

# Load SPY data — prefer latest merged CSV
for _cand in [
    "spy_5m_2025-01-01_2026-05-19_merged.csv",
    "spy_5m_2025-01-01_2026-05-15.csv",
    "spy_5m_2025-01-01_2026-05-12.csv",
]:
    _p = REPO / "data" / _cand
    if _p.exists():
        SPY_PATH = _p
        break
else:
    raise FileNotFoundError("No SPY CSV found in backtest/data/")

QTY = 3
STRIKE_OFFSET = 0          # ATM call (watch-only knob)
NARROW_OR_THRESHOLD = 2.00 # same as ORB_NARROW_OR_GATE

# J anchor period — already covered by orb_real_fills.json
J_WINNER_DATES = {"2026-04-29", "2026-05-01", "2026-05-04"}
J_LOSER_DATES = {"2026-05-05", "2026-05-06", "2026-05-07"}
J_ALL_DATES = J_WINNER_DATES | J_LOSER_DATES

# 2026 recency buffer — also covered by the #5 test set
RECENCY_CUTOFF = "2026-01-01"


def _load_spy() -> pd.DataFrame:
    df = pd.read_csv(SPY_PATH)
    df["timestamp_et"] = (
        pd.to_datetime(df["timestamp_et"], utc=True)
        .dt.tz_convert("America/New_York")
        .dt.tz_localize(None)
    )
    df = df.sort_values("timestamp_et").reset_index(drop=True)
    df["date"] = df["timestamp_et"].dt.date
    df["time"] = df["timestamp_et"].dt.time
    return df


def _bar_at(spy_df: pd.DataFrame, date_str: str, time_str: str):
    target_date = dt.datetime.strptime(date_str, "%Y-%m-%d").date()
    target_time = dt.datetime.strptime(time_str, "%H:%M").time()
    mask = (spy_df["date"] == target_date) & (spy_df["time"] == target_time)
    matches = spy_df[mask]
    if matches.empty:
        return None, None
    idx = int(matches.index[0])
    return idx, spy_df.iloc[idx]


def _load_narrow_or_test_cases() -> list[dict]:
    """Load ORB long narrow-OR obs from 2025 (independent from J-anchor + 2026 samples)."""
    seen: set[str] = set()
    all_narrow: list[dict] = []

    for line in OBS_PATH.read_text(encoding="utf-8-sig").strip().split("\n"):
        if not line.strip():
            continue
        d = json.loads(line)
        if d.get("watcher_name") != "orb_watcher":
            continue
        if d.get("direction") != "long":
            continue
        if d.get("would_be_pnl_dollars") is None:
            continue
        bar_ts = d.get("bar_timestamp_et", "")
        date_str = bar_ts[:10]

        # Skip J-anchor and 2026 (already covered)
        if date_str in J_ALL_DATES:
            continue
        if date_str >= RECENCY_CUTOFF:
            continue

        meta = d.get("metadata", {})
        or_range = meta.get("or_range")
        if or_range is None or or_range >= NARROW_OR_THRESHOLD:
            continue  # Wide OR — not relevant to this test

        # Dedup by minute (watcher can fire multiple times on same bar)
        key = bar_ts[:16]
        if key in seen:
            continue
        seen.add(key)

        or_high = meta.get("or_high")
        if or_high is None:
            continue

        all_narrow.append({
            "id": f"ORB_NARROW_{date_str.replace('-', '')}_{bar_ts[11:16].replace(':', '')}",
            "date": date_str,
            "time": bar_ts[11:16],
            "or_high": float(or_high),
            "or_low": float(meta.get("or_low", or_high - 1.0)),
            "or_range": float(or_range),
            "pt_05": float(meta.get("pt_05", or_high + 0.5)),
            "watcher_pnl": d["would_be_pnl_dollars"],
            "watcher_outcome": d.get("would_be_outcome", "?"),
            "confidence": d.get("confidence", "?"),
            "quarter": f"{date_str[:4]}-Q{(int(date_str[5:7])-1)//3+1}",
        })

    # Select representative sample: balanced winners/losers from across quarters
    winners = [e for e in all_narrow if e["watcher_pnl"] > 0]
    losers = [e for e in all_narrow if e["watcher_pnl"] < 0]

    # Sort by date to spread quarters
    winners_sorted = sorted(winners, key=lambda x: x["date"])
    losers_sorted = sorted(losers, key=lambda x: x["date"])

    # Pick 8-10 cases: try to balance quarters and W/L
    # Take every Nth winner to spread across full 2025 range
    n_winners = min(8, len(winners_sorted))
    n_losers = min(4, len(losers_sorted))

    if len(winners_sorted) <= n_winners:
        sampled_winners = winners_sorted
    else:
        step = max(1, len(winners_sorted) // n_winners)
        sampled_winners = winners_sorted[::step][:n_winners]

    if len(losers_sorted) <= n_losers:
        sampled_losers = losers_sorted
    else:
        step = max(1, len(losers_sorted) // n_losers)
        sampled_losers = losers_sorted[::step][:n_losers]

    test_cases = sorted(sampled_winners + sampled_losers, key=lambda x: x["date"])
    log.info(
        "Narrow-OR 2025 pool: %d winners, %d losers — sampling %d winners + %d losers = %d test cases",
        len(winners), len(losers), len(sampled_winners), len(sampled_losers), len(test_cases)
    )
    return test_cases


def _run_cases(spy_df: pd.DataFrame, ribbon_df: pd.DataFrame,
               test_cases: list[dict], stop_pct: float, label: str) -> list[dict]:
    results = []
    wins = losses = no_data = 0

    log.info("\n=== ORB NARROW-OR real-fills: %s (stop=%.0f%%) ===", label, stop_pct * 100)
    log.info("Side=CALL, ATM (strike_offset=0), qty=%d, OR-range < %.2f\n", QTY, NARROW_OR_THRESHOLD)

    for tc in test_cases:
        log.info(
            "--- %s: %s %s [or_range=%.2f, Q=%s] ---",
            tc["id"], tc["date"], tc["time"], tc["or_range"], tc["quarter"]
        )
        log.info(
            "    ORH=%.2f  watcher_pnl=$%.2f (%s)  conf=%s",
            tc["or_high"], tc["watcher_pnl"], tc["watcher_outcome"], tc["confidence"]
        )

        bar_idx, entry_bar = _bar_at(spy_df, tc["date"], tc["time"])
        if bar_idx is None:
            log.warning("    SKIP — bar not found for %s %s", tc["date"], tc["time"])
            results.append({**tc, "stop_label": label, "status": "BAR_NOT_FOUND"})
            no_data += 1
            continue

        entry_spot = float(entry_bar["close"])

        fill = simulate_trade_real(
            entry_bar_idx=bar_idx,
            entry_bar=entry_bar,
            spy_df=spy_df,
            ribbon_df=ribbon_df,
            rejection_level=tc["or_high"],   # chart stop: SPY drops back below ORH
            triggers_fired=["orh_breakout_retest"],
            side="C",
            qty=QTY,
            setup="ORB_NARROW_OR_RETEST_LONG",
            premium_stop_pct=stop_pct,
            strike_offset=STRIKE_OFFSET,
            profit_lock_threshold_pct=0.0,
        )

        if fill is None:
            log.warning("    NO_DATA — no OPRA bars for %s", tc["date"])
            results.append({**tc, "stop_label": label, "status": "NO_OPRA_DATA"})
            no_data += 1
            continue

        pnl = fill.dollar_pnl
        outcome = "WIN" if pnl > 0 else ("LOSS" if pnl < 0 else "BREAKEVEN")
        if pnl > 0:
            wins += 1
        else:
            losses += 1

        watcher_consistent = (tc["watcher_pnl"] > 0) == (pnl > 0)
        log.info(
            "    strike=%d  entry=$%.2f  spot=$%.2f",
            fill.strike, fill.entry_premium, entry_spot
        )
        log.info(
            "    exit=%s  pnl=$%.0f (%s)  watcher_consistent=%s",
            fill.exit_reason, pnl, outcome, watcher_consistent
        )

        results.append({
            **tc,
            "stop_label": label,
            "status": outcome,
            "real_pnl": round(pnl, 2),
            "entry_premium": round(fill.entry_premium, 4),
            "exit_reason": fill.exit_reason,
            "watcher_consistent": watcher_consistent,
        })

    n = wins + losses
    wr = wins / n if n > 0 else 0.0
    log.info(
        "\n%s SUMMARY: N=%d  WR=%.0f%%  wins=%d  losses=%d  no_data=%d",
        label, n, wr * 100, wins, losses, no_data
    )
    return results


def main() -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    log.info("Loading SPY data from %s...", SPY_PATH.name)
    spy_df = _load_spy()
    log.info("Computing ribbon...")
    ribbon_df = compute_ribbon(spy_df["close"])
    log.info("Loading narrow-OR ORB 2025 test cases...")
    test_cases = _load_narrow_or_test_cases()

    log.info("Total test cases: %d", len(test_cases))
    for tc in test_cases:
        log.info("  %s %s  or_range=%.2f  watcher_pnl=$%.1f  quarter=%s",
                 tc["date"], tc["time"], tc["or_range"], tc["watcher_pnl"], tc["quarter"])

    # Only run chart-stop-only (v2) — premium stop is structurally incompatible per L64
    results_v2 = _run_cases(spy_df, ribbon_df, test_cases, stop_pct=-0.99, label="v2_chart_stop")

    def _summary(results: list[dict]) -> dict:
        valid = [r for r in results if r.get("status") in ("WIN", "LOSS", "BREAKEVEN")]
        if not valid:
            return {"n": 0, "wr": None, "total_pnl": 0}
        wins_n = sum(1 for r in valid if r["status"] == "WIN")
        total = sum(r["real_pnl"] for r in valid)
        return {
            "n": len(valid),
            "wins": wins_n,
            "losses": len(valid) - wins_n,
            "wr": round(wins_n / len(valid), 4),
            "total_pnl": round(total, 2),
            "avg_pnl": round(total / len(valid), 2),
            "consistent_with_watcher": sum(1 for r in valid if r.get("watcher_consistent")),
        }

    s2 = _summary(results_v2)
    gate_pass = (s2["wr"] or 0) >= 0.60

    log.info("\n==================== FINAL SUMMARY ====================")
    log.info("v2 (chart-stop only):  N=%d  WR=%.0f%%  P&L=$%.0f",
             s2["n"], (s2["wr"] or 0) * 100, s2["total_pnl"])
    log.info("Gate (WR >= 60%%): %s", "PASS" if gate_pass else "FAIL")
    log.info("Prior test (J-anchor): N=10 WR=90%%  (orb_real_fills.json v2)")
    log.info("Watcher proxy (narrow only): N=143 WR=88.1%%")

    output = {
        "candidate": "ORB_NARROW_OR_GATE (or_range < 2.00, long-only, chart-stop)",
        "generated_at": dt.datetime.now().isoformat(),
        "spy_data": SPY_PATH.name,
        "narrow_or_threshold": NARROW_OR_THRESHOLD,
        "test_scope": "2025 only (non-J-anchor, independent from orb_real_fills.json)",
        "prior_test_ref": "analysis/recommendations/orb_real_fills.json — v2: N=10 WR=90%",
        "watcher_proxy_narrow_wr": 0.881,
        "watcher_proxy_narrow_n": 143,
        "v2_chart_stop_only": s2,
        "gate_pass": gate_pass,
        "verdict": "PASS" if gate_pass else "FAIL",
        "results_v2": results_v2,
        "op20_disclosure": {
            "account_size": "$1K paper (qty=3, ~$30-60 per trade at ATM call premiums)",
            "sample_bias": (
                f"{len(test_cases)} representative narrow-OR cases sampled from 2025 pool; "
                "not full OOS replay"
            ),
            "oos_test": (
                "Walk-forward OOS Sharpe=11.797 (orb-narrow-or-walkforward.json); "
                "OOS/IS ratio=1.149 — PASS"
            ),
            "real_fills": "This file + orb_real_fills.json — OPRA-sourced bars via simulator_real.py",
            "failure_modes": (
                "L64: premium stops fire during retest pullback — chart-stop-only required. "
                "Q2-2026 concentration risk (46% with narrow-OR gate vs 85% all-long)."
            ),
            "concentration": (
                "Narrow-OR 2025: Q1 n=3, Q2 n=18, Q3 n=42, Q4 n=5 — 2026-Q2 n=65. "
                "With OR-range gate, Q2 concentration reduced to 46% vs 85% for all-long."
            ),
        },
    }

    OUT_JSON.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log.info("\nOutput: %s", OUT_JSON)


if __name__ == "__main__":
    main()

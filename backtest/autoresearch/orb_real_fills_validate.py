"""Real-fills validation for ORB_DIRECTION_FILTER (long-only) via simulator_real.py.

Addresses OP-20 disclosure 4: watcher proxy WR != real option P&L.
Tests two stop variants:
  v1: premium_stop_pct=-0.10 (moderate stop, typical 0DTE fill)
  v2: premium_stop_pct=-0.99 (chart-stop only — OR-high chart stop)

Test cases: 4 J-anchor-adjacent days + 6 OOS representative signals.

ORB entry mechanics:
  - Entry on RETEST_HELD bar (close >= ORH, green close after retest of ORH)
  - rejection_level = or_high (chart stop fires if SPY drops back below ORH)
  - side = CALL (bullish long)
  - TP1 = pt_05 (0.5x range projection above ORH)
  - Runner = pt_10 (1.0x range projection above ORH)

Key difference from NLWB/LBFS (per L51): ORB retest bar has CLOSED ABOVE ORH —
the adverse pullback to ORH already happened during WAITING_RETEST phase. Entry bar
is a GREEN close at/above ORH. Should not have the violent initial collapse that
breaks -10% stops on first-strike entries. Testing both to confirm.

Output: analysis/recommendations/orb_real_fills.json
"""
from __future__ import annotations

import os as _os, sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "orb-real-fills.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "orb-real-fills.stderr.log", "a", buffering=1, encoding="utf-8")
    print(f"[orb-real-fills] stdout redirected (pid={_os.getpid()})")

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
OUT_JSON = ROOT / "analysis" / "recommendations" / "orb_real_fills.json"

# Try latest merged CSV first
for _cand in [
    "spy_5m_2025-01-01_2026-05-19_merged.csv",
    "spy_5m_2025-01-01_2026-05-15.csv",
    "spy_5m_2025-01-01_2026-05-12.csv",
    "spy_5m_2025-01-01_2026-05-07.csv",
]:
    _p = REPO / "data" / _cand
    if _p.exists():
        SPY_PATH = _p
        break
else:
    raise FileNotFoundError("No SPY CSV found in backtest/data/")

QTY = 3
STRIKE_OFFSET = 0  # ATM call (OP-21 watch-only knob)

# J anchor days
J_WINNER_DATES = {"2026-04-29", "2026-05-01", "2026-05-04"}
J_LOSER_DATES = {"2026-05-05", "2026-05-06", "2026-05-07"}
J_ALL_DATES = J_WINNER_DATES | J_LOSER_DATES


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


def _load_orb_test_cases() -> list[dict]:
    """Load ORB long observations with metadata. Dedup by minute. Select test cases."""
    seen: set[str] = set()
    all_entries: list[dict] = []
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
        key = bar_ts[:16]
        if key in seen:
            continue
        seen.add(key)
        meta = d.get("metadata", {})
        or_high = meta.get("or_high")
        if or_high is None:
            continue
        date_str = bar_ts[:10]
        time_str = bar_ts[11:16]
        all_entries.append({
            "id": f"ORB_{date_str.replace('-', '')}_{time_str.replace(':', '')}",
            "date": date_str,
            "time": time_str,
            "or_high": float(or_high),
            "or_low": float(meta.get("or_low", or_high - 1.0)),
            "pt_05": float(meta.get("pt_05", or_high + 0.5)),
            "watcher_pnl": d["would_be_pnl_dollars"],
            "watcher_outcome": d.get("would_be_outcome", "?"),
            "confidence": d.get("confidence", "?"),
            "is_j_winner": date_str in J_WINNER_DATES,
            "is_j_loser": date_str in J_LOSER_DATES,
        })

    # Priority: J-adjacent days first, then OOS 2025-Q3 + 2025-Q4, then IS sample
    j_entries = [e for e in all_entries if e["date"] in J_ALL_DATES]
    # OOS 2025-Q3/Q4 entries (mix of winners and losers)
    oos_entries = [e for e in all_entries
                   if "2025-07" <= e["date"] <= "2025-12-31"
                   and e["date"] not in J_ALL_DATES]
    oos_winners = [e for e in oos_entries if e["watcher_pnl"] > 0][:3]
    oos_losers = [e for e in oos_entries if e["watcher_pnl"] < 0][:3]

    test_cases = j_entries + oos_winners + oos_losers
    return test_cases


def _run_cases(spy_df: pd.DataFrame, ribbon_df: pd.DataFrame,
               test_cases: list[dict], stop_pct: float, label: str) -> list[dict]:
    results = []
    wins = losses = no_data = 0

    log.info("\n=== ORB long real-fills: %s (stop=%.0f%%) ===", label, stop_pct * 100)
    log.info("Side=CALL, ATM (strike_offset=0), qty=%d\n", QTY)

    for tc in test_cases:
        j_tag = " [J-WINNER]" if tc["is_j_winner"] else (" [J-LOSER]" if tc["is_j_loser"] else "")
        log.info("--- %s: %s %s%s ---", tc["id"], tc["date"], tc["time"], j_tag)
        log.info("    ORH=%.2f  watcher_pnl=$%.2f (%s)  conf=%s",
                 tc["or_high"], tc["watcher_pnl"], tc["watcher_outcome"], tc["confidence"])

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
            rejection_level=tc["or_high"],        # chart stop: SPY drops below ORH
            triggers_fired=["orh_breakout_retest"],
            side="C",
            qty=QTY,
            setup="ORB_RETEST_LONG",
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
        log.info("    strike=%d  entry=$%.2f  spot=$%.2f",
                 fill.strike, fill.entry_premium, entry_spot)
        log.info("    exit=%s  pnl=$%.0f (%s)  watcher_consistent=%s",
                 fill.exit_reason, pnl, outcome, watcher_consistent)

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
    log.info("\n%s SUMMARY: N=%d  WR=%.0f%%  wins=%d  losses=%d  no_data=%d",
             label, n, wr * 100, wins, losses, no_data)
    return results


def main() -> None:
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)

    log.info("Loading SPY data from %s...", SPY_PATH.name)
    spy_df = _load_spy()
    log.info("Computing ribbon...")
    ribbon_df = compute_ribbon(spy_df["close"])
    log.info("Loading ORB test cases...")
    test_cases = _load_orb_test_cases()
    log.info("Test cases: %d total (%d J-adjacent, %d OOS, %d IS)",
             len(test_cases),
             sum(1 for t in test_cases if t["date"] in J_ALL_DATES),
             sum(1 for t in test_cases if "2025-07" <= t["date"] <= "2025-12-31"
                 and t["date"] not in J_ALL_DATES),
             sum(1 for t in test_cases if t["date"] < "2025-07"))

    # Test v1: -10% premium stop
    results_v1 = _run_cases(spy_df, ribbon_df, test_cases, stop_pct=-0.10, label="v1_-10pct_stop")
    # Test v2: chart-stop only (-99%)
    results_v2 = _run_cases(spy_df, ribbon_df, test_cases, stop_pct=-0.99, label="v2_chart_stop")

    # Compute summary
    def _summary(results: list[dict]) -> dict:
        valid = [r for r in results if r.get("status") in ("WIN", "LOSS", "BREAKEVEN")]
        if not valid:
            return {"n": 0, "wr": None, "total_pnl": 0}
        wins = sum(1 for r in valid if r["status"] == "WIN")
        total = sum(r["real_pnl"] for r in valid)
        return {
            "n": len(valid),
            "wins": wins,
            "losses": len(valid) - wins,
            "wr": round(wins / len(valid), 4),
            "total_pnl": round(total, 2),
            "avg_pnl": round(total / len(valid), 2),
            "consistent_with_watcher": sum(1 for r in valid if r.get("watcher_consistent")),
        }

    s1 = _summary(results_v1)
    s2 = _summary(results_v2)

    # J-day analysis
    def _j_summary(results: list[dict]) -> dict:
        j_results = [r for r in results if r.get("is_j_winner") or r.get("is_j_loser")]
        winner_pnl = sum(r.get("real_pnl", 0) for r in j_results if r.get("is_j_winner") and "real_pnl" in r)
        loser_loss = sum(max(0, -r.get("real_pnl", 0)) for r in j_results if r.get("is_j_loser") and "real_pnl" in r)
        return {
            "n_j_days": len(j_results),
            "winner_pnl": round(winner_pnl, 2),
            "loser_loss": round(loser_loss, 2),
            "edge_capture": round(winner_pnl - loser_loss, 2),
        }

    log.info("\n==================== FINAL SUMMARY ====================")
    log.info("v1 (-10%% stop):   N=%d  WR=%.0f%%  P&L=$%.0f",
             s1["n"], s1["wr"] * 100 if s1["wr"] else 0, s1["total_pnl"])
    log.info("v2 (chart-stop):  N=%d  WR=%.0f%%  P&L=$%.0f",
             s2["n"], s2["wr"] * 100 if s2["wr"] else 0, s2["total_pnl"])
    log.info("Watcher proxy WR (OOS): 79.8%%  (N=163)")
    log.info("Gate: real_fills WR >= 50%% in both variants = PASS")

    j1 = _j_summary(results_v1)
    j2 = _j_summary(results_v2)

    output = {
        "candidate": "ORB_DIRECTION_FILTER (long-only)",
        "generated_at": dt.datetime.now().isoformat(),
        "spy_data": SPY_PATH.name,
        "watcher_proxy_wr_oos": 0.798,
        "watcher_proxy_n_oos": 163,
        "v1_premium_stop_10pct": {**s1, "j_day_analysis": j1},
        "v2_chart_stop_only": {**s2, "j_day_analysis": j2},
        "gate_pass": (s1["wr"] or 0) >= 0.50 and (s2["wr"] or 0) >= 0.50,
        "verdict": "PASS" if ((s1["wr"] or 0) >= 0.50 and (s2["wr"] or 0) >= 0.50) else "FAIL",
        "results_v1": results_v1,
        "results_v2": results_v2,
        "op20_disclosure": {
            "account_size": "$1K paper (qty=3, ~$30-60 per trade at ATM call premiums)",
            "sample_bias": f"10 representative cases from {len(test_cases)} total test pool; not full OOS replay",
            "oos_test": "Watcher walk-forward OOS Sharpe=7.950 (see orb-longonly-walkforward.json)",
            "real_fills": "This file — OPRA-sourced option bars via simulator_real.py",
            "failure_modes": "Q2-2026 concentration risk (85%% of OOS P&L); stops may widen if VIX spikes",
            "concentration": "2026-Q2 = 85%% of long-ORB P&L; 2025-Q1 WR=0%% = regime-fragile",
        },
    }

    OUT_JSON.write_text(json.dumps(output, indent=2, default=str), encoding="utf-8")
    log.info("\nOutput: %s", OUT_JSON)


if __name__ == "__main__":
    main()

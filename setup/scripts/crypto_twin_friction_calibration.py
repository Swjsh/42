"""crypto_twin_friction_calibration.py -- TWIN-B6-SIM-FRICTION-CALIBRATION.

Every SPY 0DTE backtest study discloses "frictionless fills" as a caveat (real market
impact on entry/exit is approximated, never measured). This closes that caveat HONESTLY
using the crypto twin's accumulating REAL Alpaca paper fills -- MECHANISM TRANSFER, never
an edge claim (twin P&L stays health-only per CLAUDE.md/TWIN-PROGRAM.md doctrine; friction
magnitudes are BTC-notional/bps, not SPY-options-dollars -- crypto taker-fee economics
differ from options economics, see TWIN-PROGRAM.md "Fee model note").

Reads (never writes trading-path state):
  * automation/state/crypto-twin/entry-quality.json -- ENTRY friction, already measured
    since TWIN-B3 (2026-07-14): "marketable" cohort = true market-order entry (comparable
    in KIND to backtest/lib/simulator_real.py's entry_slippage bucket), "passive" cohort =
    resting-limit entry (no SPY analog exists yet -- entry_manager/T-W5 is sim-shadow only
    on the SPY side).
  * automation/state/crypto-twin/journal.jsonl -- EXIT friction via the NEW "EXIT_FILLED"
    rows (crypto_twin_core.py's _journal_exit_fill, wired this fire, TWIN-B6). Every twin
    exit stage (structure_stop / catastrophe cap / TP1-trail / premium_stop / runner_stop /
    time_stop / max_hold) is placed as a MARKET order (crypto_twin_core.manage_positions ->
    broker.market_sell_crypto) -- so ALL twin exit-side calibration data is comparable to
    simulator_real.py's DEFAULT_EXIT_SLIPPAGE (market-exit) bucket, NEVER its "limit exits
    (TP1/stop) have zero slippage" assumption (the twin has no passive/limit EXIT lane --
    only entries got the TWIN-B3 passive-limit graduation; flagged as a follow-up, not
    fixed here).

$0, pure stdlib, read-only except for its own output artifact. Usage:
    backtest/.venv/Scripts/python.exe setup/scripts/crypto_twin_friction_calibration.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from statistics import mean, median
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))  # simulator_real.py is part of the backtest.lib PACKAGE
                               # (relative imports) -- must import via backtest.lib.*,
                               # not by putting backtest/lib on sys.path directly.

TWIN_DIR = REPO / "automation" / "state" / "crypto-twin"
ENTRY_QUALITY_PATH = TWIN_DIR / "entry-quality.json"
JOURNAL_PATH = TWIN_DIR / "journal.jsonl"
OUTPUT_PATH = TWIN_DIR / "friction-calibration.json"

try:
    from backtest.lib.simulator_real import DEFAULT_ENTRY_SLIPPAGE, DEFAULT_EXIT_SLIPPAGE  # noqa: E402
except ImportError:  # pragma: no cover -- keeps this script runnable stand-alone
    DEFAULT_ENTRY_SLIPPAGE = DEFAULT_EXIT_SLIPPAGE = None


def _read_jsonl(path: Path) -> list[dict]:
    """Fail-open: missing file -> []. Skips (never aborts on) a malformed line."""
    if not path.exists():
        return []
    out: list[dict] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _stats(values: list[float]) -> dict:
    if not values:
        return {"n": 0, "avg": None, "median": None, "min": None, "max": None}
    return {"n": len(values), "avg": round(mean(values), 4), "median": round(median(values), 4),
           "min": round(min(values), 4), "max": round(max(values), 4)}


def entry_friction(entry_quality: dict) -> dict:
    """The "marketable" cohort IS the market-order entry -- directly comparable in kind to
    simulator_real.py's entry_slippage. improvement_bps in entry-quality.json is signed so
    that POSITIVE = better than the baseline ask (i.e. NEGATIVE slippage relative to a naive
    "always pay the ask" assumption); we report slippage_bps = -improvement_bps so the sign
    convention matches simulator_real.py's entry_slippage (a POSITIVE cost added to fill)."""
    cohorts = entry_quality.get("cohorts", {})
    marketable = cohorts.get("marketable", {})
    passive = cohorts.get("passive", {})
    out = {"marketable_market_order": None, "passive_resting_limit_no_spy_analog": None}
    if marketable.get("fills"):
        avg_improvement_bps = marketable.get("avg_improvement_bps")
        out["marketable_market_order"] = {
            "n_fills": marketable.get("fills"), "fill_rate": marketable.get("fill_rate"),
            "avg_slippage_bps": round(-avg_improvement_bps, 4) if avg_improvement_bps is not None else None,
            "avg_time_to_fill_sec": marketable.get("avg_time_to_fill_sec")}
    if passive.get("attempts"):
        avg_improvement_bps = passive.get("avg_improvement_bps")
        out["passive_resting_limit_no_spy_analog"] = {
            "n_attempts": passive.get("attempts"), "n_fills": passive.get("fills"),
            "fill_rate": passive.get("fill_rate"),
            "avg_improvement_bps": avg_improvement_bps,
            "avg_time_to_fill_sec": passive.get("avg_time_to_fill_sec")}
    return out


def exit_friction(journal_rows: list[dict]) -> dict:
    """Every EXIT_FILLED row -- ALL are market orders (see module docstring), so this is
    ONE bucket comparable to simulator_real.py's exit_slippage, broken down by exit KIND
    for visibility (a catastrophe-cap exit under a gap is expected to slip worse than a
    calm structure-stop touch)."""
    rows = [r for r in journal_rows if r.get("event") == "EXIT_FILLED" and r.get("slippage_bps") is not None]
    by_stage: dict[str, list[float]] = {}
    latencies: list[float] = []
    for r in rows:
        reason = str(r.get("reason") or "")
        stage = reason.split(" @ ")[0].split("(")[0].strip() or "unlabeled"
        by_stage.setdefault(stage, []).append(-float(r["slippage_bps"]))  # sign-match entry convention
        if r.get("time_to_fill_sec") is not None:
            latencies.append(float(r["time_to_fill_sec"]))
    return {
        "n_exit_fills_captured": len(rows),
        "all_market_orders": True,
        "overall_slippage_bps": _stats([-float(r["slippage_bps"]) for r in rows]),
        "by_stage_slippage_bps": {k: _stats(v) for k, v in sorted(by_stage.items())},
        "latency_sec": _stats(latencies),
        "n_capture_errors": sum(1 for r in journal_rows if r.get("event") == "EXIT_FILLED_CAPTURE_ERROR"),
    }


def backtest_assumptions() -> dict:
    return {
        "source": "backtest/lib/simulator_real.py",
        "DEFAULT_ENTRY_SLIPPAGE": DEFAULT_ENTRY_SLIPPAGE,
        "DEFAULT_EXIT_SLIPPAGE": DEFAULT_EXIT_SLIPPAGE,
        "units": "USD per SPY option contract (NOT bps -- crypto/options magnitudes are not "
                "directly comparable, see module docstring 'Fee model note')",
        "limit_exit_convention": "TP1/premium_stop/BE-stop exits assumed to fill EXACTLY at "
                                 "the bracket level (zero slippage) -- the twin has no exit-side "
                                 "passive/limit lane to validate this assumption; only its "
                                 "market-order exit-slippage bucket is transferable today.",
    }


def build_report() -> dict:
    entry_quality = _read_json(ENTRY_QUALITY_PATH)
    journal_rows = _read_jsonl(JOURNAL_PATH)
    report = {
        "generated_by": "crypto_twin_friction_calibration.py",
        "doctrine": "TWIN-B6-SIM-FRICTION-CALIBRATION -- mechanism transfer, never an edge claim",
        "entry_friction": entry_friction(entry_quality),
        "exit_friction": exit_friction(journal_rows),
        "backtest_current_assumptions": backtest_assumptions(),
    }
    n_exit = report["exit_friction"]["n_exit_fills_captured"]
    report["verdict"] = ("ACCRUING -- exit-fill capture wired 2026-07-23, 0 samples yet; "
                         "re-run after live twin exits accrue" if n_exit == 0 else
                         f"{n_exit} exit fills captured -- see by_stage_slippage_bps")
    return report


def main() -> int:
    report = build_report()
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2), encoding="utf-8")
    ef = report["entry_friction"].get("marketable_market_order")
    xf = report["exit_friction"]
    print(f"ENTRY (market-order): n={ef['n_fills'] if ef else 0} "
         f"avg_slippage_bps={ef['avg_slippage_bps'] if ef else 'n/a'}")
    print(f"EXIT (market-order, all stages): n={xf['n_exit_fills_captured']} "
         f"verdict={report['verdict']}")
    print(f"Written: {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

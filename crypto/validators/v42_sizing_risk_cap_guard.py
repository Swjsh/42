"""v42_sizing_risk_cap_guard — Assert backtest position notional respects per_trade_risk_cap_pct.

Background (evidence):
  2026-05-31 analysis (analysis/backtests/_TRUTH.md sizing caveat): orchestrator.py L669-702
  assigns trade_qty by a FIXED quality-tier ladder (SUPER=15/ELITE=10/LEVEL=22/TRENDLINE_LEG2=20/
  TRENDLINE,BASE=3), decoupled from initial_equity and per_trade_risk_cap_pct.
  Concrete foot-gun: LEVEL-tier trade prints qty=22 when simulating missed_week_safe at $747.11 equity.
    22 contracts × ~$1.24 entry premium × 100 = ~$2,728 notional = ~365% of equity.
  Rule 6 (30% Safe / 50% Bold) forbids this live. Live<->backtest drift (OP-16).

  Fixture verification: missed_week_safe metadata.json initial_equity=747.11 (safe cap 0.30 = $224.13
  per trade max notional). missed_week_bold metadata.json initial_equity=1535.83 (bold cap 0.50 =
  $767.92 per trade max notional). First safe trade: 3 contracts × $0.91 × 100 = $273 notional = 36.5%
  of equity → BREACH. First bold trade same qty=3 × $0.91 × 100 = $273 / $1535.83 = 17.8% → OK.

Modes:
  offline  12 deterministic notional-vs-cap tests at varied equity/qty/premium combos.
           All 12 must PASS (validator logic correct). The fixture scenarios include both
           expected-breach and expected-OK cases to verify the detector itself works.
  live     Audit-only: scan missed_week_safe/trades.csv + missed_week_bold/trades.csv from
           analysis/backtests/. Report breach counts per run. pass=True always (surface-only).
  both     Run offline then live.

Offline coverage:
  Safe account (cap=0.30):
    T01:  E=$1000, qty=3,  px=$1.00  → notional=$300  = 30.0% → OK  (at cap boundary)
    T02:  E=$1000, qty=3,  px=$1.01  → notional=$303  = 30.3% → BREACH
    T03:  E=$747,  qty=3,  px=$0.91  → notional=$273  = 36.5% → BREACH  (missed_week_safe T1)
    T04:  E=$747,  qty=3,  px=$0.50  → notional=$150  = 20.1% → OK
    T05:  E=$747,  qty=22, px=$1.24  → notional=$2728 = 365%  → BREACH  (LEVEL-tier foot-gun)
    T06:  E=$2000, qty=5,  px=$1.20  → notional=$600  = 30.0% → OK  (exactly at cap)
  Bold account (cap=0.50):
    T07:  E=$1535, qty=3,  px=$0.91  → notional=$273  = 17.8% → OK
    T08:  E=$1535, qty=8,  px=$1.00  → notional=$800  = 52.1% → BREACH
    T09:  E=$1535, qty=7,  px=$1.15  → notional=$805  = 52.4% → BREACH (> toleranced cap $775)
    T10:  E=$1535, qty=7,  px=$1.09  → notional=$763  = 49.7% → OK
    T11:  E=$500,  qty=3,  px=$0.83  → notional=$249  = 49.8% → OK
    T12:  E=$500,  qty=4,  px=$0.85  → notional=$340  = 68.0% → BREACH

Live coverage:
  For each CSV row in missed_week_safe + missed_week_bold:
    notional = qty × entry_px × 100
    cap = initial_equity × (0.30 if safe else 0.50)
    tolerance_pct = 0.01  (1% buffer for rounding differences)
    breach = notional > cap × (1 + tolerance_pct)
  Reports: total_trades, breach_count, worst_offender_pct_of_equity.
  all_pass = True always (surface-only — validator does NOT alter sizing logic).

Exit code:
  0 — all offline tests PASS (or live-only run)
  1 — any offline test FAIL
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

# Tolerance: 1% over cap is allowed for rounding / partial-fill scenarios
_TOLERANCE_PCT = 0.01

# Safe cap is 30% of equity; Bold cap is 50% of equity (Rule 6)
_CAP_SAFE = 0.30
_CAP_BOLD = 0.50


# ---------------------------------------------------------------------------
# Core check function (inline — no production dependency)
# ---------------------------------------------------------------------------

def check_notional(
    qty: int | float,
    entry_premium: float,
    initial_equity: float,
    cap_fraction: float,
    tolerance: float = _TOLERANCE_PCT,
) -> tuple[bool, float, float]:
    """Return (is_breach, notional, cap_with_tolerance).

    notional = qty * entry_premium * 100  (options contract multiplier)
    cap      = initial_equity * cap_fraction
    breach   = notional > cap * (1 + tolerance)
    """
    notional = qty * entry_premium * 100.0
    cap = initial_equity * cap_fraction
    cap_toleranced = cap * (1.0 + tolerance)
    is_breach = notional > cap_toleranced
    return is_breach, notional, cap_toleranced


# ---------------------------------------------------------------------------
# Offline tests
# ---------------------------------------------------------------------------

def run_offline() -> dict:
    """Run 12 deterministic notional-vs-cap tests."""
    results: list[dict] = []

    def t(
        label: str,
        qty: int | float,
        entry_px: float,
        equity: float,
        cap_frac: float,
        expect_breach: bool,
    ) -> None:
        is_breach, notional, cap_tol = check_notional(qty, entry_px, equity, cap_frac)
        pct_of_equity = notional / equity * 100.0
        passed = is_breach == expect_breach
        results.append({
            "label": label,
            "qty": qty,
            "entry_px": entry_px,
            "equity": equity,
            "cap_pct": round(cap_frac * 100, 0),
            "notional": round(notional, 2),
            "notional_pct_of_equity": round(pct_of_equity, 1),
            "cap_toleranced": round(cap_tol, 2),
            "expect_breach": expect_breach,
            "got_breach": is_breach,
            "passed": passed,
        })
        status = "PASS" if passed else "FAIL"
        breach_str = "BREACH" if is_breach else "OK    "
        expect_str = "BREACH" if expect_breach else "OK    "
        print(
            f"  [{status}] {label:4s}  qty={qty:2}  px=${entry_px:.2f}  E=${equity:.0f}  "
            f"cap={cap_frac*100:.0f}%  notional=${notional:.0f}({pct_of_equity:.1f}%)  "
            f"got={breach_str}  expect={expect_str}"
        )

    # --- Safe account (cap=30%) ---
    # T01: exactly AT cap (no breach — tolerance is 1% buffer)
    t("T01", 3, 1.00, 1000.0, _CAP_SAFE, False)  # $300 = 30.0%, cap=$303 with tol
    # T02: 0.33% over cap → still within 1% tolerance? No — $303/$300=1.01 exactly at edge;
    #      $303.0 > $300*1.01=$303.0 is False; so $304 would breach. Use px=1.10 for clear breach.
    t("T02", 3, 1.10, 1000.0, _CAP_SAFE, True)   # $330 = 33.0% → BREACH
    # T03: missed_week_safe first trade fixture (2026-05-31 finding)
    t("T03", 3, 0.91,  747.0, _CAP_SAFE, True)   # $273 = 36.5% vs cap $224.1 → BREACH
    # T04: small safe trade at low premium → OK
    t("T04", 3, 0.50,  747.0, _CAP_SAFE, False)  # $150 = 20.1% → OK
    # T05: LEVEL-tier foot-gun (qty=22 at safe account)
    t("T05", 22, 1.24,  747.0, _CAP_SAFE, True)  # $2728 = 365% → BREACH
    # T06: $2K equity, 5 contracts at $1.20 → exactly 30% cap
    t("T06", 5, 1.20, 2000.0, _CAP_SAFE, False)  # $600 = 30.0% → OK (within tol)

    # --- Bold account (cap=50%) ---
    # T07: missed_week_bold first trade (qty=3 at $1535)
    t("T07", 3, 0.91, 1535.0, _CAP_BOLD, False)  # $273 = 17.8% → OK
    # T08: 8 contracts at $1535 → BREACH
    t("T08", 8, 1.00, 1535.0, _CAP_BOLD, True)   # $800 = 52.1% → BREACH
    # T09: 7 contracts × $1.15 at $1535 → clearly over cap + tolerance (50% cap * 1.01 = $775.17)
    t("T09", 7, 1.15, 1535.0, _CAP_BOLD, True)   # $805 = 52.4% → BREACH (> $775.17 toleranced cap)
    # T10: 7 contracts × $1.09 at $1535 → under cap + tolerance
    t("T10", 7, 1.09, 1535.0, _CAP_BOLD, False)  # $763 = 49.7% → OK
    # T11: small bold account $500, 3 contracts at $0.83
    t("T11", 3, 0.83,  500.0, _CAP_BOLD, False)  # $249 = 49.8% → OK
    # T12: bold at $500, 4 contracts × $0.85 → clearly over 50% + 1% tolerance ($252.53 toleranced cap)
    t("T12", 4, 0.85,  500.0, _CAP_BOLD, True)   # $340 = 68.0% → BREACH

    passed_n = sum(1 for r in results if r["passed"])
    total_n = len(results)

    return {
        "mode": "offline",
        "tests": results,
        "passed": passed_n,
        "total": total_n,
        "all_pass": passed_n == total_n,
    }


# ---------------------------------------------------------------------------
# Live audit
# ---------------------------------------------------------------------------

def _audit_csv(
    csv_path: Path,
    initial_equity: float,
    cap_fraction: float,
    label: str,
) -> dict:
    """Scan one trades.csv and return breach summary."""
    if not csv_path.exists():
        print(f"  [SKIP] {label}: {csv_path} not found")
        return {
            "label": label,
            "found": False,
            "total_trades": 0,
            "breach_count": 0,
            "worst_pct_of_equity": None,
            "examples": [],
        }

    total = 0
    breaches = 0
    worst_pct = 0.0
    examples: list[dict] = []

    with csv_path.open(newline="", encoding="utf-8", errors="replace") as fh:
        for row in csv.DictReader(fh):
            try:
                qty = float(row.get("qty", 0) or 0)
                entry_px = float(row.get("entry_px", 0) or 0)
            except (ValueError, TypeError):
                continue
            if qty <= 0 or entry_px <= 0:
                continue

            total += 1
            is_breach, notional, _ = check_notional(qty, entry_px, initial_equity, cap_fraction)
            pct = notional / initial_equity * 100.0 if initial_equity > 0 else 0.0

            if pct > worst_pct:
                worst_pct = pct

            if is_breach:
                breaches += 1
                if len(examples) < 5:
                    examples.append({
                        "date": row.get("date", "?"),
                        "time_entry": row.get("time_entry", "?"),
                        "qty": qty,
                        "entry_px": entry_px,
                        "notional": round(notional, 2),
                        "pct_of_equity": round(pct, 1),
                        "cap_pct": round(cap_fraction * 100, 0),
                    })

    cap_dollars = initial_equity * cap_fraction
    print(f"  [AUDIT] {label}: equity=${initial_equity:.2f}  cap={cap_fraction*100:.0f}%"
          f"  (${cap_dollars:.0f})  trades={total}  breaches={breaches}  "
          f"worst={worst_pct:.1f}% of equity")
    if examples:
        print(f"          breach examples:")
        for ex in examples:
            print(f"            {ex['date']} {ex['time_entry']}  "
                  f"qty={ex['qty']:.0f}  px=${ex['entry_px']:.2f}  "
                  f"notional=${ex['notional']:.0f}={ex['pct_of_equity']:.1f}%")

    return {
        "label": label,
        "found": True,
        "initial_equity": initial_equity,
        "cap_fraction": cap_fraction,
        "cap_dollars": round(cap_dollars, 2),
        "total_trades": total,
        "breach_count": breaches,
        "worst_pct_of_equity": round(worst_pct, 1),
        "examples": examples,
    }


def run_live() -> dict:
    """Audit-only: scan missed_week_safe + missed_week_bold trades.csv for Rule 6 breaches.

    Reads initial_equity from metadata.json in each run directory.
    pass=True always — this validator SURFACES drift, never fixes it.
    """
    base = _ROOT / "analysis" / "backtests"

    # Load metadata for equity and account type
    safe_meta_path = base / "missed_week_safe" / "metadata.json"
    bold_meta_path = base / "missed_week_bold" / "metadata.json"

    safe_equity = 747.11  # fallback from inbox item
    bold_equity = 1535.83

    if safe_meta_path.exists():
        try:
            safe_meta = json.loads(safe_meta_path.read_text(encoding="utf-8"))
            safe_equity = float(safe_meta.get("initial_equity", safe_equity))
        except Exception:
            pass

    if bold_meta_path.exists():
        try:
            bold_meta = json.loads(bold_meta_path.read_text(encoding="utf-8"))
            bold_equity = float(bold_meta.get("initial_equity", bold_equity))
        except Exception:
            pass

    safe_result = _audit_csv(
        base / "missed_week_safe" / "trades.csv",
        safe_equity,
        _CAP_SAFE,
        "missed_week_safe",
    )
    bold_result = _audit_csv(
        base / "missed_week_bold" / "trades.csv",
        bold_equity,
        _CAP_BOLD,
        "missed_week_bold",
    )

    total_trades = safe_result["total_trades"] + bold_result["total_trades"]
    total_breaches = safe_result["breach_count"] + bold_result["breach_count"]

    print(f"\n  COMBINED: total_trades={total_trades}  breaches={total_breaches}")
    if total_breaches > 0:
        print(f"  NOTE: {total_breaches} breach(es) found — backtest notional exceeds live Rule 6 cap.")
        print(f"        Per OP-16: live<->backtest drift MUST be disclosed before ratifying any run.")
        print(f"        This validator SURFACES the gap; sizing fix belongs in orchestrator.py.")
    else:
        print(f"  NOTE: No breaches found — backtest sizing is within live Rule 6 caps.")

    return {
        "mode": "live",
        "all_pass": True,  # audit-only — never fails; surfaces drift only
        "safe": safe_result,
        "bold": bold_result,
        "total_trades": total_trades,
        "total_breaches": total_breaches,
        "note": "informational audit — pass=True always; breaches indicate live<->backtest sizing drift",
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode",
        choices=["offline", "live", "both"],
        default="offline",
        help="offline=notional cap tests; live=trades.csv audit; both=all",
    )
    args = parser.parse_args(argv)

    print(f"\n[v42] SIZING_RISK_CAP_GUARD — mode={args.mode}")
    print(f"      safe_cap={_CAP_SAFE*100:.0f}%  bold_cap={_CAP_BOLD*100:.0f}%  "
          f"tolerance={_TOLERANCE_PCT*100:.0f}%  contract_multiplier=100")

    rc = 0
    if args.mode in ("offline", "both"):
        result = run_offline()
        status = "PASS" if result["all_pass"] else "FAIL"
        print(f"\n  [{status}] offline: {result['passed']}/{result['total']} tests passed")
        if not result["all_pass"]:
            rc = 1

    if args.mode in ("live", "both"):
        print()
        run_live()

    return rc


if __name__ == "__main__":
    sys.exit(main())

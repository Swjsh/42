#!/usr/bin/env python
"""EOD-2026-08-04 LENS 2 -- "criticize the winners". ONE-OFF day analysis.

Reuses winner_autopsy / trade_autopsy / exit_shape_parity_study rather than reimplementing
anything: this script OWNS no replay logic, no position definition and no bar fetcher.

Emits analysis/deep-research/EOD-2026-08-04-WINNERS.json. The .md is authored by hand from
this JSON so the prose and the numbers cannot drift.

DISCIPLINE:
  * Real broker fills + real 1-min OPRA only.
  * ORACLE columns are labelled and NEVER mixed into live-executable columns.
  * Sizing counterfactuals scale the REALIZED per-contract result. That is exact only if the
    same fills were available at the larger size -- no market-impact model exists here, so
    every scaled number is labelled MODELLED, not measured.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "setup" / "scripts", REPO / "backtest" / "tools",
           REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import trade_autopsy as ta           # noqa: E402
import exit_shape_parity_study as esp  # noqa: E402
import winner_autopsy as wa          # noqa: E402

DATE = "2026-08-04"
OUT = REPO / "analysis" / "deep-research" / "EOD-2026-08-04-WINNERS.json"

# Start-of-day equity, broker-verified (from the task brief + last_equity reads).
SOD = {"safe-2": 5067.73, "bold-2": 5000.00, "safe-3": 5144.73,
       "risky-1": 5144.55, "risky-3": 5175.55}
# Rule 6 per-trade risk cap, from fleet_live._limit_pct_for + CLAUDE.md Rule 6.
LIMIT_PCT = {"safe-2": 0.30, "safe-3": 0.30, "bold-2": 0.50,
             "risky-1": 0.50, "risky-3": 0.50}
# SHIP C (risky-3 only): qty 10 when contract premium < $0.50.
SHIP_C_ARM, SHIP_C_BELOW, SHIP_C_QTY = "risky-3", 0.50, 10


def main() -> int:
    positions = ta.load_engine_positions(DATE)
    bar_cache: dict = {}
    rows = []
    for p in sorted(positions, key=lambda x: x["entry_ts_utc"]):
        bars = ta.fetch_bars_cached(esp, p["symbol"], p["date_et"], bar_cache)
        elig = wa.exit_eligible_bars(bars, p["entry_ts_utc"]) if bars else []
        qty = float(p["entry_qty"])
        realized = round(p["actual_exit_pnl"], 2)
        per_contract = round(realized / qty, 4) if qty else None

        # Rule-6 ceiling in CONTRACTS: premium outlay capped at limit_pct of start-of-day
        # equity. Min 3 contracts (Rule 6) is a FLOOR the engine already respects; the
        # ceiling is what we are measuring headroom against.
        cap_dollars = SOD[p["arm"]] * LIMIT_PCT[p["arm"]]
        max_contracts = int(cap_dollars // (p["entry_price"] * 100))
        ship_c_legal = (p["arm"] == SHIP_C_ARM and p["entry_price"] < SHIP_C_BELOW)

        rows.append({
            "arm": p["arm"], "symbol": p["symbol"],
            "entry_ts_et": p["entry_ts_utc"][11:19], "entry_price": p["entry_price"],
            "qty": qty, "realized_pnl": realized, "pnl_per_contract": per_contract,
            "is_winner": realized > 0,
            "notional_paid": round(p["entry_price"] * qty * 100, 2),
            "rule6_cap_dollars": round(cap_dollars, 2),
            "rule6_max_contracts": max_contracts,
            "rule6_headroom_contracts": max_contracts - int(qty),
            "capital_left_on_table": round(cap_dollars - p["entry_price"] * qty * 100, 2),
            # MODELLED, not measured -- see module docstring.
            "pnl_at_qty10_MODELLED": round(per_contract * 10, 2) if per_contract else None,
            "pnl_at_rule6_ceiling_MODELLED": (round(per_contract * max_contracts, 2)
                                              if per_contract else None),
            "ship_c_would_have_fired": ship_c_legal,
            # ORACLE -- labelled, never mixed into a live-executable column.
            "ORACLE_pnl": wa.oracle_pnl(elig, p["entry_price"], qty) if elig else None,
            "n_bars": len(bars),
        })

    win = [r for r in rows if r["is_winner"]]
    book = {
        "n_positions": len(rows), "n_winners": len(win), "n_losers": len(rows) - len(win),
        "realized_total": round(sum(r["realized_pnl"] for r in rows), 2),
        "winners_total": round(sum(r["realized_pnl"] for r in win), 2),
        "losers_total": round(sum(r["realized_pnl"] for r in rows if not r["is_winner"]), 2),
        "notional_deployed": round(sum(r["notional_paid"] for r in rows), 2),
        "pnl_at_qty10_MODELLED": round(sum(r["pnl_at_qty10_MODELLED"] or 0 for r in rows), 2),
        "pnl_at_rule6_ceiling_MODELLED": round(
            sum(r["pnl_at_rule6_ceiling_MODELLED"] or 0 for r in rows), 2),
        "ship_c_fires": sum(1 for r in rows if r["ship_c_would_have_fired"]),
        "min_entry_premium": min(r["entry_price"] for r in rows),
        "ORACLE_total_UNREACHABLE": round(sum(r["ORACLE_pnl"] or 0 for r in rows), 2),
    }

    per_arm = {}
    for arm in SOD:
        ar = [r for r in rows if r["arm"] == arm]
        if not ar:
            continue
        per_arm[arm] = {
            "n_positions": len(ar), "n_legs_entry": len(ar),
            "realized": round(sum(r["realized_pnl"] for r in ar), 2),
            "contracts_traded": int(sum(r["qty"] for r in ar)),
            "sod_equity": SOD[arm], "rule6_limit_pct": LIMIT_PCT[arm],
            "avg_rule6_headroom_contracts": round(
                sum(r["rule6_headroom_contracts"] for r in ar) / len(ar), 2),
            "capital_left_on_table_total": round(
                sum(r["capital_left_on_table"] for r in ar), 2),
            "pnl_at_qty10_MODELLED": round(
                sum(r["pnl_at_qty10_MODELLED"] or 0 for r in ar), 2),
            "pnl_at_rule6_ceiling_MODELLED": round(
                sum(r["pnl_at_rule6_ceiling_MODELLED"] or 0 for r in ar), 2),
        }

    # ---- PDT truth vs what each execution path actually saw -------------------------------
    # The fleet path reads acct["daytrade_count"], which Alpaca returns as None on these
    # accounts -> int(None or 0) == 0 forever (fleet_live.py:660). The core path calls
    # pdt_tracker directly (heartbeat_core.py:1909) and is correct. Measured live, not assumed.
    import fleet_broker as fb          # noqa: PLC0415
    import pdt_tracker as _pdt         # noqa: PLC0415
    creds = fb.load_creds()
    pdt_block = {"limit_per_5_business_days": 3, "arms": {}}
    for arm in SOD:
        try:
            true_n = _pdt.fetch_day_trades_used_5d(creds[arm])
        except Exception as e:  # noqa: BLE001
            true_n = f"ERR {type(e).__name__}: {e}"[:80]
        is_core = arm in ("safe-2", "bold-2")
        try:
            acct = fb.get_account(creds[arm])
            raw = acct.get("daytrade_count") if isinstance(acct, dict) else None
            mult = acct.get("multiplier") if isinstance(acct, dict) else None
        except Exception:  # noqa: BLE001
            raw, mult = None, None
        pdt_block["arms"][arm] = {
            "path": "core (pdt_tracker)" if is_core else "fleet (acct.daytrade_count)",
            "true_day_trades_5d": true_n,
            "engine_saw": true_n if is_core else 0,
            "broker_daytrade_count_raw": raw,
            "multiplier": mult,
            "gate_effective": bool(is_core),
            "over_limit": (isinstance(true_n, int) and true_n > 3),
        }
    pdt_block["root_cause"] = (
        "automation/state/fleet/fleet_live.py:660 -- int(acct.get('daytrade_count', 0) or 0); "
        "broker returns None on these accounts so the fleet gate is structurally inert "
        "(0 >= 3 is never true). Verbatim re-run of the 2026-07-06 bug fixed in "
        "heartbeat_core.py but never carried across to the fleet path.")
    pdt_block["measured_cost_today"] = (
        "bold-2 PDT-denied 21 ELITE setups 12:26:55-13:48:26 ET and therefore missed the "
        "12:28 769C wave that paid the other four arms +$2,192; at bold-2's 5-lot sizing and "
        "the wave's realized $125-158/contract that is approx +$630..+$790 foregone. The gate "
        "was CORRECT -- this is the cost of compliance, not a bug.")

    payload = {
        "date": DATE,
        "generated_by": "setup/scripts/_eod_2026_08_04_winners.py",
        "provenance": "broker fills (fills-ledger.jsonl) + real 1-min OPRA bars",
        "pdt": pdt_block,
        "runner_shape_counterfactual_WINNERS_ONLY": {
            "note": "Each arm keeps its own TP1; only the post-TP1 runner policy changes. "
                    "WINNERS-ONLY sample on a TREND day -- says nothing about losers, which "
                    "outnumber winners 15:10 today. PREREG only, never armed.",
            "be_floor_only_fixed": 5724.20,
            "chandelier_trailing": 3812.20,
            "delta": 1912.00,
            "realized": 4735.00,
        },
        "late_fade_verdict": {
            "conclusion": "HINDSIGHT -- no live-executable standdown signal existed.",
            "evidence": "ribbon BULL and htf_15m BULL every tick 13:20-13:48; bull_score 9-11; "
                        "SPY rose 771.135 -> 772.34 (high AFTER both entries); VIX 16.33->16.55. "
                        "Direction was right; the 772C bled 1.22->0.90 on theta (C3: SPY-price "
                        "edge != option edge).",
            "prereg": "NONE -- would be fitted to 2 trades totalling -$114 on the best day on record.",
        },
        "book": book, "per_arm": per_arm, "positions": rows,
        "caveats": [
            "qty10 / Rule-6-ceiling P&L is MODELLED by scaling the realized per-contract "
            "result. No market-impact model: valid only if identical fills were available "
            "at the larger size.",
            "ORACLE_* columns are the sell-at-the-high bound. UNREACHABLE by any live rule. "
            "Never mixed into a live-executable column.",
            "n=1 trading day. Nothing here is armable on its own.",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(book, indent=2))
    print("\nper arm:")
    for a, v in per_arm.items():
        print(f"  {a:8s} realized {v['realized']:>9.2f} contracts {v['contracts_traded']:>3d} "
              f"qty10 {v['pnl_at_qty10_MODELLED']:>10.2f} "
              f"rule6ceil {v['pnl_at_rule6_ceiling_MODELLED']:>11.2f} "
              f"left_on_table ${v['capital_left_on_table_total']:>9.2f}")
    print(f"\n-> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

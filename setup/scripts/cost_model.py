#!/usr/bin/env python
"""cost_model.py -- REAL-ACCOUNT COST REALISM MODEL for Project Gamma's 5 active
real-fills arms (safe-2, bold-2, safe-3, risky-1, risky-3).

J'S ASK (2026-08-18, verbatim intent): "what are we doing about documenting how much it
would cost to get in the trades, taxes, fees -- to try and copy what it would be like if
we're trading a real account, so that's a seamless transition." Every P&L figure this repo
has ever produced (trades.csv, decisions ledgers, EOD digests, HOME.md) comes from Alpaca
PAPER fills. This instrument quantifies how much of that P&L survives contact with what a
REAL account actually costs.

HEADLINE FINDING (full sourcing in analysis/deep-research/COST-REALISM-2026-08-18.md) --
disclosed here because it inverts the assumption this task started from: **Alpaca PAPER is
NOT frictionless.** It already charges REAL regulatory pass-through fees (OCC clearing, ORF,
FINRA TAF, SEC Section 31, CAT) -- empirically confirmed 2026-08-18 by reading
get_account_activities_by_type(FEE) live on safe-2 (PA3POKNV46VG, 9 trading days
2026-08-04..2026-08-17) and cross-checked on bold-2 (PA3WEBXJU67N). Commission stays exactly
$0 on both paper AND live (Alpaca's real published rate -- not a paper-only artifact).
What IS new: these regulatory fees are charged by Alpaca (debited from paper equity, visible
in account activity) but are NEVER INGESTED anywhere in this repo's P&L pipeline --
broker_fills.py pulls Alpaca activity_type="FILL" only; FEE-type rows are never read. Every
"real_pnl" in fills-ledger.jsonl / trades.csv / every downstream dashboard has therefore
always silently excluded fees Alpaca is actually charging. This script is the first thing in
the repo to apply them.

RATE PROVENANCE (all empirical, reverse-engineered from real Alpaca fee-activity rows this
session, each formula reproduces EVERY observed row to the cent across 9 days / 2 accounts --
see the module constants below and COST-REALISM-2026-08-18.md section 2 for the row-by-row
arithmetic):
  - OCC Clearing Fee : $0.025/contract, BOTH sides, per execution, round UP to the cent.
  - ORF               : $0.015/contract, BOTH sides (proved by a 2x relationship vs TAF's
                        sells-only contract count, 9/9 sampled days).
  - FINRA TAF         : $0.00329/contract, SELLS ONLY, round UP to the cent.
  - SEC Section 31    : $20.60 per $1,000,000 of SELL proceeds, SELLS ONLY, round UP to the
                        cent. Matches tastytrade's own dated fee schedule ("as of
                        2026-04-04") exactly -- this is a federally-set rate, not
                        broker-specific.
  - CAT fee           : empirically flat $0.01/account/trading-day in the observed sample
                        (2-10 trades/day, always exactly $0.01) -- FINRA Rule 6897 assesses
                        CAT fees on the EXECUTING BROKER by aggregate monthly volume, not a
                        published retail per-contract rate, so this is modeled as observed,
                        not derived from a public formula. Immaterial at Gamma's scale either
                        way.
  - Commission        : $0.00 (alpaca.markets/support/what-are-the-commission-fees-per-
                        option-contract, fetched 2026-08-18: "Alpaca Trading API users will
                        not encounter any commissions for options trading" -- true for both
                        paper and live).

THE SPREAD QUESTION (does paper fill at midpoint, hiding real spread cost?) -- ENTRY side is
MEASURED, HIGH confidence: this session re-ran backtest/tools/entry_execution_cost_2026_08_02.py
--no-fetch (n=250 real entry fills, all 6 arms incl. retired safe-1). Every arm's
avg_price_improvement_cents_per_contract (entry_px - fill_price) lands within noise of
avg_cross_buffer_cents_per_contract (exactly 3.0c, the deliberate entry_cross_buffer padding
on top of the real fetched ask) -- 2.90 to 4.30 cents/contract across all 6 arms. If paper
were filling generously at the NBBO midpoint, price_improvement would run buffer + roughly
half the real bid/ask spread (several more cents, per this repo's own simulator_real.py
calibration note of a typical 4-10c 0DTE spread) -- it does not. **Paper fills BUY orders at
essentially the real quoted ASK, not the midpoint.** avg_spread_crossed_cents_per_contract
(the reconstructed ask-vs-mid half-spread) is noise-level and occasionally negative across
arms (-0.69 to +1.00c) -- expected artifact of two independent near-simultaneous live quote
calls each independently rounded to the cent (see heartbeat_core.py's nbbo-reconstruction
comment), NOT evidence of a real wide spread being hidden.

EXIT side is UNVERIFIED this session -- exits are placed as MARKET orders (fleet_broker.
market_sell), which have no "submitted limit" to diff against fill price the way entries do.
exit_actuator.py DOES fetch a real bid/ask hilo before every exit decision (best_premium=ask,
worst_premium=bid) and persists it into each fleet arm's decisions.jsonl via `exit_pass` --
so an exit-side instrument mirroring entry_execution_cost.py is BUILDABLE from data that
already exists, but was NOT built this session (flagged as a concrete follow-up, not a vague
TODO). Two scenarios are carried explicitly rather than guessed between (see
_ScenarioResult below): (a) exits mirror the entries' measured realism -> $0 incremental
spread cost, and (b) a conservative placeholder reusing this repo's OWN standing backtest
assumption for market-exit slippage (simulator_real.DEFAULT_EXIT_SLIPPAGE = $0.02/contract),
applied to the exit leg only. Scenario (a) is the headline because it is the one with actual
measurement behind it (entries); (b) is shown alongside, not averaged in, per this rig's
"never split the difference silently" rule.

TAXES -- see analysis/deep-research/COST-REALISM-2026-08-18.md section 4. NOT computed here
(no tax bill, NOT tax advice): SPY options are ordinary short-term gains (wash-sale applies);
SPX/XSP would get 60/40 Section 1256 blended treatment (no wash-sale) but exist at Alpaca in
PAPER ONLY as of 2026-08-18 (alpaca.markets blog, 2026-07-23, no live date announced).

$0, pure stdlib, zero network calls, deterministic, well under the 5-minute grinder-reaper
budget on this box's fill-ledger volume.

Run:
    backtest/.venv/Scripts/python.exe setup/scripts/cost_model.py
    backtest/.venv/Scripts/python.exe setup/scripts/cost_model.py --json
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "automation" / "state" / "fleet", REPO / "setup" / "scripts"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now  # noqa: E402
import fills_fifo  # noqa: E402

ACCOUNTS_JSON = REPO / "automation" / "state" / "fleet" / "accounts.json"
OUT_JSON = REPO / "analysis" / "recommendations" / "cost-model.json"

# ============================================================================
# FEE RATES -- see module docstring for full provenance. Every constant below is
# EMPIRICAL (read from Alpaca's own paper-account activity ledger 2026-08-18),
# not a web estimate. Changing these without re-deriving from a fresh activity
# read is a doctrine violation of this instrument's whole premise.
# ============================================================================

COMMISSION_PER_CONTRACT = 0.00
OCC_FEE_PER_CONTRACT = 0.025       # both sides, per execution, ceil to the cent
ORF_FEE_PER_CONTRACT = 0.015       # both sides, ceil to the cent
TAF_FEE_PER_CONTRACT = 0.00329     # sells only, ceil to the cent
SEC_FEE_RATE_PER_DOLLAR = 20.60 / 1_000_000.0   # sells only, on dollar proceeds
CAT_FEE_PER_ARM_DAY = 0.01         # flat, once per arm per trading day with activity

# Spread placeholder for the UNVERIFIED exit leg only (see module docstring). Reused
# verbatim from backtest/lib/simulator_real.py's own DEFAULT_EXIT_SLIPPAGE constant --
# this repo's existing standing assumption for market-exit cost, not a new invention.
EXIT_SLIPPAGE_CONSERVATIVE_PER_CONTRACT = 0.02

# Entry-side spread-fill-quality evidence, produced THIS session by re-running the
# existing backtest/tools/entry_execution_cost_2026_08_02.py --no-fetch (local data
# only, no network) and reading its 'overall'/'by_lane'/'by_arm' summary blocks.
# Hardcoded here (not re-run at import time) to keep this script $0/network-free/fast --
# refresh by re-running that tool and updating these numbers + the date below.
SPREAD_EVIDENCE_ENTRY_SIDE = {
    "_doc": ("avg_price_improvement_cents_per_contract = entry_px - fill_price, averaged. "
             "avg_cross_buffer_cents_per_contract is the deliberate ask+$0.03 padding this "
             "engine always adds (constant by construction). price_improvement landing near "
             "cross_buffer (not buffer + half-spread) means fills cluster at the real ask, "
             "not the NBBO midpoint. avg_spread_crossed_cents_per_contract is a noisy, "
             "sometimes-negative reconstruction of the ask-vs-mid half-spread from two "
             "independent near-simultaneous quote calls -- noise-level, not a real signal."),
    "measured_et": "2026-08-18",
    "source": "backtest/tools/entry_execution_cost_2026_08_02.py --no-fetch (this session)",
    "overall": {"n": 250, "avg_price_improvement_cents_per_contract": 3.40,
                "avg_cross_buffer_cents_per_contract": 3.00,
                "avg_spread_crossed_cents_per_contract": 0.10},
    "by_lane": {
        "core": {"n": 59, "avg_price_improvement_cents_per_contract": 3.03,
                  "avg_spread_crossed_cents_per_contract": -0.29},
        "fleet": {"n": 191, "avg_price_improvement_cents_per_contract": 3.52,
                   "avg_spread_crossed_cents_per_contract": 0.22},
    },
    "by_arm": {
        "safe-2": {"n": 33, "avg_price_improvement_cents_per_contract": 2.99, "avg_spread_crossed_cents_per_contract": 0.03},
        "bold-2": {"n": 26, "avg_price_improvement_cents_per_contract": 3.08, "avg_spread_crossed_cents_per_contract": -0.69},
        "safe-3": {"n": 40, "avg_price_improvement_cents_per_contract": 2.90, "avg_spread_crossed_cents_per_contract": -0.10},
        "risky-1": {"n": 59, "avg_price_improvement_cents_per_contract": 3.35, "avg_spread_crossed_cents_per_contract": 0.05},
        "risky-3": {"n": 72, "avg_price_improvement_cents_per_contract": 3.78, "avg_spread_crossed_cents_per_contract": 0.32},
    },
    "conclusion": ("HIGH confidence: paper ENTRY fills land at ~the real quoted ask, not the "
                   "midpoint -- across all 5 active arms, 250 fills. EXIT side not "
                   "independently measured this session (see module docstring); carried as "
                   "an explicit two-scenario range, not assumed identical."),
}


# ============================================================================
# Pure fee arithmetic -- unit-tested in backtest/tests/test_cost_model.py
# ============================================================================

def _ceil_cents(x: float) -> float:
    """Ceiling to the nearest cent -- Alpaca's own disclosed rounding convention
    ('rounded up to the nearest penny', alpaca.markets/support/regulatory-fees,
    fetched 2026-08-18). Rounds to 6dp first to kill binary-float noise before the
    ceiling (so an exact 0.03 never spuriously becomes 0.04)."""
    return math.ceil(round(x * 100.0, 6) - 1e-9) / 100.0


def occ_fee(qty: int) -> float:
    """OCC Clearing Fee for ONE execution of `qty` contracts. Both sides (call once
    for the entry execution, once for the exit execution)."""
    return _ceil_cents(qty * OCC_FEE_PER_CONTRACT)


def orf_fee(qty: int) -> float:
    """Options Regulatory Fee for ONE execution of `qty` contracts. Both sides."""
    return _ceil_cents(qty * ORF_FEE_PER_CONTRACT)


def taf_fee(sell_qty: int) -> float:
    """FINRA Trading Activity Fee. SELLS ONLY -- caller must pass the SELL-side qty."""
    return _ceil_cents(sell_qty * TAF_FEE_PER_CONTRACT)


def sec_fee(sell_dollar_proceeds: float) -> float:
    """SEC Section 31 fee. SELLS ONLY, assessed on dollar proceeds (not premium-space
    -- see sell_dollar_proceeds_of for the premium-to-dollars conversion)."""
    return _ceil_cents(max(0.0, sell_dollar_proceeds) * SEC_FEE_RATE_PER_DOLLAR)


def sell_dollar_proceeds_of(round_trip: dict) -> float:
    """Exact SELL-side dollar proceeds for one fills_fifo round trip, reconstructed
    ALGEBRAICALLY so this works even when exit_premium is None (a >1-leg exit, e.g.
    TP1 + runner -- see fills_fifo.mine_real_arm_fills docstring). Identity fills_fifo
    itself uses to compute real_pnl:
        real_pnl = (sell_notional - buy_notional) * 100          [sell_notional,
                                                                    buy_notional in
                                                                    premium-space]
        buy_notional = entry_premium * qty
    Solve for the dollar-space sell proceeds (sell_notional * 100):
        sell_dollar_proceeds = real_pnl + entry_premium * qty * 100
    Exact, not an estimate -- pure algebra on fields fills_fifo already returns, no
    re-read of exit_premium required."""
    entry_premium = round_trip.get("entry_premium") or 0.0
    qty = round_trip.get("qty") or 0
    real_pnl = round_trip.get("real_pnl") or 0.0
    return real_pnl + entry_premium * qty * 100.0


def fee_breakdown(round_trip: dict) -> dict:
    """Pure. Regulatory-fee decomposition of ONE closed round trip. Excludes CAT
    (applied once per arm-day at aggregation time, not per trip -- CAT_FEE_PER_ARM_DAY)
    and commission ($0 either way, COMMISSION_PER_CONTRACT).

    KNOWN SIMPLIFICATION (disclosed, bounded): OCC is charged per EXECUTION on the
    real ledger, and a multi-leg exit (TP1 + runner) is technically 2 executions, not
    1 -- this treats each leg (entry, exit) as a single execution at the round trip's
    total qty. Understates OCC by at most a few cents on the minority of round trips
    with a split exit; ORF/TAF/SEC are aggregate-based and unaffected. See
    COST-REALISM-2026-08-18.md limitations section."""
    qty = int(round_trip.get("qty") or 0)
    sell_proceeds = sell_dollar_proceeds_of(round_trip)

    occ_entry = occ_fee(qty)
    occ_exit = occ_fee(qty)
    orf_entry = orf_fee(qty)
    orf_exit = orf_fee(qty)
    taf_exit = taf_fee(qty)
    sec_exit = sec_fee(sell_proceeds)

    fee_total_ex_cat = round(occ_entry + occ_exit + orf_entry + orf_exit
                              + taf_exit + sec_exit, 4)
    spread_conservative = round(EXIT_SLIPPAGE_CONSERVATIVE_PER_CONTRACT * qty * 100.0, 2)

    return {
        "qty": qty, "sell_dollar_proceeds": round(sell_proceeds, 2),
        "occ_entry": occ_entry, "occ_exit": occ_exit,
        "orf_entry": orf_entry, "orf_exit": orf_exit,
        "taf_exit": taf_exit, "sec_exit": sec_exit,
        "fee_total_ex_cat": fee_total_ex_cat,
        "spread_adjustment_conservative": spread_conservative,
    }


# ============================================================================
# Roster + aggregation
# ============================================================================

def load_roster() -> list[str]:
    """The active, real-fills arms -- DERIVED from accounts.json, never hardcoded.
    status=='active' AND fidelity=='real_fills' excludes safe-1 (retired) and the
    two futures arms (pending_build / dormant, fidelity bs_sim_ranking_only /
    point_pnl_validated -- neither is real broker fills)."""
    data = json.loads(ACCOUNTS_JSON.read_text(encoding="utf-8"))
    return [a["id"] for a in data.get("arms", [])
            if a.get("status") == "active" and a.get("fidelity") == "real_fills"]


def build_report() -> dict[str, Any]:
    roster = load_roster()
    per_arm: dict[str, Any] = {}

    for arm in roster:
        trips = fills_fifo.mine_real_arm_fills(arm)
        rows = []
        as_traded = 0.0
        fee_ex_cat_total = 0.0
        spread_cons_total = 0.0
        days = set()
        for t in trips:
            fb = fee_breakdown(t)
            as_traded += t.get("real_pnl") or 0.0
            fee_ex_cat_total += fb["fee_total_ex_cat"]
            spread_cons_total += fb["spread_adjustment_conservative"]
            if t.get("date"):
                days.add(t["date"])
            rows.append({**t, "fees": fb})

        cat_total = round(len(days) * CAT_FEE_PER_ARM_DAY, 2)
        as_traded = round(as_traded, 2)
        fee_total = round(fee_ex_cat_total + cat_total, 2)
        fee_adjusted = round(as_traded - fee_total, 2)
        fee_spread_a = fee_adjusted  # scenario A: exits mirror entries' measured realism (+$0)
        fee_spread_b = round(fee_adjusted - spread_cons_total, 2)  # scenario B: conservative

        per_arm[arm] = {
            "n_round_trips": len(trips), "n_trading_days": len(days),
            "as_traded_pnl": as_traded,
            "fee_total_ex_cat": round(fee_ex_cat_total, 2), "cat_total": cat_total,
            "fee_total": fee_total,
            "fee_adjusted_pnl": fee_adjusted,
            "spread_adjustment_conservative_total": round(spread_cons_total, 2),
            "fee_plus_spread_adjusted_pnl_scenario_a_zero_incremental_spread": fee_spread_a,
            "fee_plus_spread_adjusted_pnl_scenario_b_conservative_exit_slippage": fee_spread_b,
            "rows": rows,
        }

    def _sum(key: str) -> float:
        return round(sum(v[key] for v in per_arm.values()), 2)

    book_wide = {
        "_disclosure": ("CORRELATED ROLLUP, NOT 5 independent samples. All 5 arms trade the "
                        "SAME shared signal (automation/state/fleet/build_shared_signal.py) "
                        "and differ only in sizing/gates/exit shape (MAP.md) -- arms "
                        "correlate at r=0.846. Read this as one book's economics under 5 "
                        "risk profiles, never as 5x the statistical confidence of one arm."),
        "n_round_trips": sum(v["n_round_trips"] for v in per_arm.values()),
        "as_traded_pnl": _sum("as_traded_pnl"),
        "fee_total": _sum("fee_total"),
        "fee_adjusted_pnl": _sum("fee_adjusted_pnl"),
        "fee_plus_spread_adjusted_pnl_scenario_a_zero_incremental_spread":
            _sum("fee_plus_spread_adjusted_pnl_scenario_a_zero_incremental_spread"),
        "fee_plus_spread_adjusted_pnl_scenario_b_conservative_exit_slippage":
            _sum("fee_plus_spread_adjusted_pnl_scenario_b_conservative_exit_slippage"),
    }

    return {"roster": roster, "per_arm": per_arm, "book_wide": book_wide}


def _print_human(report: dict[str, Any]) -> None:
    hdr = (f"{'arm':<10}{'trips':>7}{'as-traded':>13}{'fees':>9}{'fee-adj':>12}"
           f"{'+spread(A)':>13}{'+spread(B)':>13}")
    print(hdr)
    print("-" * len(hdr))
    for arm, v in report["per_arm"].items():
        print(f"{arm:<10}{v['n_round_trips']:>7}{v['as_traded_pnl']:>13,.2f}"
              f"{v['fee_total']:>9,.2f}{v['fee_adjusted_pnl']:>12,.2f}"
              f"{v['fee_plus_spread_adjusted_pnl_scenario_a_zero_incremental_spread']:>13,.2f}"
              f"{v['fee_plus_spread_adjusted_pnl_scenario_b_conservative_exit_slippage']:>13,.2f}")
    print("-" * len(hdr))
    b = report["book_wide"]
    print(f"{'BOOK*':<10}{b['n_round_trips']:>7}{b['as_traded_pnl']:>13,.2f}"
          f"{b['fee_total']:>9,.2f}{b['fee_adjusted_pnl']:>12,.2f}"
          f"{b['fee_plus_spread_adjusted_pnl_scenario_a_zero_incremental_spread']:>13,.2f}"
          f"{b['fee_plus_spread_adjusted_pnl_scenario_b_conservative_exit_slippage']:>13,.2f}")
    print("\n* BOOK is a CORRELATED rollup (r=0.846) -- 5 risk profiles on one shared "
          "signal, not 5 independent samples.")
    print("\nScenario A = $0 incremental spread cost (measured, entry side, HIGH confidence;")
    print("             extended to exits via mechanism-consistency, UNVERIFIED).")
    print("Scenario B = conservative $0.02/contract exit-slippage placeholder (this repo's")
    print("             own existing simulator_real.py backtest assumption), exit leg only.")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true", help="print the full JSON payload to stdout")
    ap.add_argument("--out", default=None, help="override output path (default: %s)" % OUT_JSON)
    args = ap.parse_args()

    report = build_report()
    payload = {
        "_doc": ("Real-account cost realism model -- J's 2026-08-18 ask: what would it cost "
                "to trade this for real. Empirical Alpaca regulatory-fee rates (read live "
                "from account activity, not modeled/estimated) applied to every closed "
                "real-fills round trip across the 5 active arms. Full methodology, sourcing, "
                "and the spread-fill-quality evidence: "
                "analysis/deep-research/COST-REALISM-2026-08-18.md"),
        "generated_et": et_now().isoformat(),
        "rates": {
            "commission_per_contract": COMMISSION_PER_CONTRACT,
            "occ_fee_per_contract_both_sides": OCC_FEE_PER_CONTRACT,
            "orf_fee_per_contract_both_sides": ORF_FEE_PER_CONTRACT,
            "taf_fee_per_contract_sells_only": TAF_FEE_PER_CONTRACT,
            "sec_fee_rate_per_dollar_sells_only": SEC_FEE_RATE_PER_DOLLAR,
            "cat_fee_per_arm_day": CAT_FEE_PER_ARM_DAY,
            "exit_spread_adjustment_conservative_per_contract": EXIT_SLIPPAGE_CONSERVATIVE_PER_CONTRACT,
        },
        "spread_evidence_entry_side": SPREAD_EVIDENCE_ENTRY_SIDE,
        **report,
    }

    out_path = Path(args.out) if args.out else OUT_JSON
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, indent=2, default=str))
    else:
        _print_human(report)
        try:
            print(f"\nwrote -> {out_path.relative_to(REPO)}")
        except ValueError:
            print(f"\nwrote -> {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

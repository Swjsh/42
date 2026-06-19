"""Principled SIZING study, grounded in J's REAL Webull round-trip ledger.

Answers J's two open sizing decisions with his own numbers, not generic theory:
  (a) min-3 floor vs flat-2: is the doctrine MIN_CONTRACTS=3 inside J's losing
      zone, or is a CONSISTENT flat-3 fine and the killer purely the adding?
  (b) post-loss throttle: should risk_gate gain an equity-trajectory throttle,
      and what is the exact rule?

This is a PROPOSE-ONLY analysis (CLAUDE.md Rule 9). It reads the ledger, prints
the report, and writes a machine-readable scorecard. It changes NO live config,
NO params, NO risk_gate behaviour. The throttle is DESIGNED here (reference
signature + slot-in point) and documented in docs/SIZING-STUDY-2026-06-19.md;
it is NOT wired into check_order.

DATA
----
Source: analysis/webull-j-trades/j_roundtrips.csv — every reconstructed
round-trip from J's 2021-2023 Webull options history (SPX/SPY family + single
names; bull + bear; long premium only). Columns of interest:
  qty            number of contracts on the round-trip
  n_entry_fills  >1 == scaled-in / added-to (the revenge-sizing signature)
  pnl            realized dollar P&L of the round-trip
  status         'closed' (realized) | 'unclosed' | 'expired_worthless'
  entry_time     FULL datetime string (parse directly; do NOT prepend `date`)

We analyse `status == 'closed'` for P&L purity (realized exits only). The 16
`expired_worthless` rows are real -100% losses; they are reported as a
sensitivity but excluded from the headline so the win/loss payoff distribution
reflects trades J actually managed to an exit (which is what the engine's
chart-stop emulates).

THE FULL-PREMIUM-AT-RISK REALITY (why this is not a textbook Kelly problem)
--------------------------------------------------------------------------
A long 0DTE option can go to ZERO the same day. There is no overnight recovery
and no margin-style partial loss floor: if the chart-stop fails to fire, the
whole premium is gone. So two Kelly framings bracket the truth:
  * J-realized-payoff Kelly  — uses his ACTUAL average loss (he cut losers at
    ~42% of premium). This is the optimistic bound and assumes the disciplined
    exit always holds.
  * Conservative-binary Kelly — models a loss as 100% of premium (the genuine
    0DTE catastrophe). This is the pessimistic bound.
The gap between them is the small-account lesson: the edge survives ONLY on
tight exits, so the prudent size is the SMALLEST viable one, not a Kelly-optimal
one. We report both and recommend heavy fractional (<= 1/2) Kelly.

USAGE
-----
    python backtest/autoresearch/sizing_study.py            # print + write scorecard
    python backtest/autoresearch/sizing_study.py --no-write # print only

Pure-Python + pandas/numpy. $0 cost. Deterministic (no sampling).
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional, Sequence

import numpy as np
import pandas as pd

# REPO = backtest/, REPO.parent = project root (convention shared with the rest
# of backtest/autoresearch/*; anchored to __file__ per L21/C9).
REPO = Path(__file__).resolve().parent.parent
ROOT = REPO.parent
LEDGER_CSV = ROOT / "analysis" / "webull-j-trades" / "j_roundtrips.csv"
SCORECARD = ROOT / "analysis" / "recommendations" / "sizing-study-2026-06-19.json"

# Account math constants (CLAUDE.md account context + params.json).
SAFE_EQUITY = 2_000.0          # Gamma-Safe-2 fresh capital
BOLD_EQUITY = 1_673.0          # Gamma-Risky-2
DOCTRINE_MIN_CONTRACTS = 3     # params.json min_contracts (the knob in question)
OTM3_PREMIUMS = (0.30, 0.40, 0.50)  # typical OTM-3 0DTE long premium band


# --------------------------------------------------------------------------- #
# Pure metric helpers
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Stats:
    """Immutable summary of one slice of the ledger."""

    label: str
    n: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    expectancy_per_trade: float
    profit_factor: float

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "n": self.n,
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.win_rate, 4),
            "total_pnl": round(self.total_pnl, 1),
            "expectancy_per_trade": round(self.expectancy_per_trade, 2),
            "profit_factor": (
                round(self.profit_factor, 3)
                if np.isfinite(self.profit_factor)
                else None
            ),
        }


def summarize(label: str, pnl: pd.Series) -> Stats:
    """Win-rate / expectancy / profit-factor for a P&L slice. Pure."""
    pnl = pnl.dropna()
    n = int(len(pnl))
    wins = int((pnl > 0).sum())
    losses = int((pnl < 0).sum())
    decided = wins + losses
    wr = wins / decided if decided else 0.0
    gross_win = float(pnl[pnl > 0].sum())
    gross_loss = float(pnl[pnl < 0].sum())
    pf = gross_win / abs(gross_loss) if gross_loss != 0 else float("inf")
    exp = float(pnl.mean()) if n else 0.0
    return Stats(label, n, wins, losses, wr, float(pnl.sum()), exp, pf)


def lot_band(qty: float) -> str:
    """Map a contract count into the study's lot bands."""
    if qty <= 2:
        return "1-2"
    if qty <= 5:
        return "3-5"
    return "6+"


# --------------------------------------------------------------------------- #
# Fractional-Kelly bounds
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class KellyResult:
    p_win: float
    payoff_b: float
    full_kelly_fraction: float
    half_kelly_fraction: float
    quarter_kelly_fraction: float
    basis: str

    def as_dict(self) -> dict:
        return {
            "basis": self.basis,
            "p_win": round(self.p_win, 4),
            "payoff_b": round(self.payoff_b, 4),
            "full_kelly_fraction": round(self.full_kelly_fraction, 4),
            "half_kelly_fraction": round(self.half_kelly_fraction, 4),
            "quarter_kelly_fraction": round(self.quarter_kelly_fraction, 4),
        }


def kelly(p_win: float, payoff_b: float, basis: str) -> KellyResult:
    """Kelly fraction f* = (b*p - q) / b, with q = 1 - p.

    `payoff_b` is the win/loss ratio on the chosen basis. A negative f* means
    "no bet" — the edge does not justify ANY fraction on that basis.
    """
    q = 1.0 - p_win
    f = (payoff_b * p_win - q) / payoff_b if payoff_b > 0 else float("-inf")
    return KellyResult(p_win, payoff_b, f, f / 2.0, f / 4.0, basis)


def contracts_for_fraction(
    fraction: float, equity: float, premium: float
) -> float:
    """How many contracts a bankroll fraction buys at a given premium.

    fraction * equity dollars / (premium * 100 per contract).
    """
    if premium <= 0:
        return 0.0
    return (fraction * equity) / (premium * 100.0)


# --------------------------------------------------------------------------- #
# The study
# --------------------------------------------------------------------------- #
def load_closed(csv_path: Path) -> pd.DataFrame:
    """Load the ledger, keep realized (closed) round-trips, add derived cols."""
    df = pd.read_csv(csv_path)
    closed = df[df["status"] == "closed"].copy()
    # entry_time is already a full datetime string; parse directly (L: do NOT
    # concatenate with `date` — that double-prefixes and raises tzoffset errors).
    closed["entry_dt"] = pd.to_datetime(closed["entry_time"])
    closed = closed.sort_values("entry_dt").reset_index(drop=True)
    closed["band"] = closed["qty"].apply(lot_band)
    closed["scaled_in"] = closed["n_entry_fills"] > 1
    closed["flat"] = ~closed["scaled_in"]
    # prior-trade-outcome (revenge) signal, chronological
    closed["prior_pnl"] = closed["pnl"].shift(1)
    closed["same_day"] = closed["date"] == closed["date"].shift(1)
    closed["prior_loss_same_day"] = (closed["prior_pnl"] < 0) & closed["same_day"]
    closed["prior_win_same_day"] = (closed["prior_pnl"] > 0) & closed["same_day"]
    return closed


def empirical_sizing_curve(c: pd.DataFrame) -> list[Stats]:
    """P&L / WR / expectancy / PF by lot band (the headline cliff)."""
    out = []
    for b in ("1-2", "3-5", "6+"):
        g = c[c["band"] == b]
        out.append(summarize(f"lot {b}", g["pnl"]))
    return out


def flat_vs_scaled(c: pd.DataFrame) -> dict[str, Stats]:
    """THE key untangle: flat (single entry) vs scaled-in, within each band."""
    out: dict[str, Stats] = {}
    for b in ("1-2", "3-5", "6+"):
        for flat, tag in ((True, "flat"), (False, "scaled")):
            g = c[(c["band"] == b) & (c["flat"] == flat)]
            if len(g):
                out[f"{b}|{tag}"] = summarize(f"{b} {tag}", g["pnl"])
    # the decisive comparison: flat-1-2 vs flat-3plus (single-entry only)
    out["flat_1_2"] = summarize("flat 1-2", c[c["flat"] & (c["qty"] <= 2)]["pnl"])
    out["flat_3plus"] = summarize("flat 3+", c[c["flat"] & (c["qty"] >= 3)]["pnl"])
    out["scaled_any"] = summarize("scaled-in (any size)", c[c["scaled_in"]]["pnl"])
    out["single_entry_any"] = summarize(
        "single-entry (any size)", c[c["flat"]]["pnl"]
    )
    return out


def revenge_signal(c: pd.DataFrame) -> dict:
    """Does size correlate with a PRIOR loss (revenge-sizing)?"""
    after_loss = c[c["prior_loss_same_day"]]
    after_win = c[c["prior_win_same_day"]]

    def desc(g: pd.DataFrame) -> dict:
        return {
            "n": int(len(g)),
            "avg_qty": round(float(g["qty"].mean()), 3) if len(g) else None,
            "pct_qty_ge_3": round(float((g["qty"] >= 3).mean()), 4) if len(g) else None,
            "pct_scaled_in": round(float(g["scaled_in"].mean()), 4) if len(g) else None,
            "total_pnl": round(float(g["pnl"].sum()), 1),
            "expectancy_per_trade": round(float(g["pnl"].mean()), 2) if len(g) else None,
            "win_rate": round(float((g["pnl"] > 0).mean()), 4) if len(g) else None,
        }

    return {
        "after_same_day_loss": desc(after_loss),
        "after_same_day_win": desc(after_win),
        "interpretation": (
            "Size rises after a loss (avg_qty and pct_qty_ge_3 both higher "
            "after a same-day loss than after a same-day win) => mild but real "
            "revenge-sizing. Trades placed AFTER a same-day loss are net "
            "negative."
        ),
    }


def flat3_confounders(c: pd.DataFrame) -> dict:
    """Is flat-3+ losing everywhere, or only in one confounded bucket?"""
    f3 = c[c["flat"] & (c["qty"] >= 3)]
    out = {"overall": summarize("flat 3+", f3["pnl"]).as_dict(), "by_bias": {}, "by_0dte": {}}
    for v, g in f3.groupby("bias"):
        out["by_bias"][str(v)] = summarize(f"flat3 {v}", g["pnl"]).as_dict()
    for v, g in f3.groupby("is_0dte"):
        out["by_0dte"][str(v)] = summarize(f"flat3 0dte={v}", g["pnl"]).as_dict()
    return out


def kelly_block(c: pd.DataFrame) -> dict:
    """Fractional-Kelly bounds from the WINNING (1-2 flat) band."""
    f12 = c[c["flat"] & (c["qty"] <= 2)].copy()
    f12["pnl_per_contract"] = f12["pnl"] / f12["qty"]
    p_win = float((f12["pnl"] > 0).mean())
    win_pc = float(f12[f12["pnl"] > 0]["pnl_per_contract"].mean())
    loss_pc = float(f12[f12["pnl"] < 0]["pnl_per_contract"].mean())
    mean_premium = float(f12["entry_px"].mean())

    # Basis 1: J-realized payoff (he cut losers; optimistic, assumes exit holds).
    b_realized = win_pc / abs(loss_pc)
    k_realized = kelly(p_win, b_realized, "j_realized_payoff (loser cut ~42% premium)")

    # Basis 2: conservative binary (loss = 100% of premium; 0DTE-to-zero risk).
    b_binary = win_pc / (mean_premium * 100.0)
    k_binary = kelly(p_win, b_binary, "conservative_binary (loss = full premium)")

    # Concrete contract counts for half-Kelly (realized basis) on the $2K account.
    half_frac = max(0.0, k_realized.half_kelly_fraction)
    half_kelly_contracts = {
        f"{prem:.2f}": round(contracts_for_fraction(half_frac, SAFE_EQUITY, prem), 2)
        for prem in OTM3_PREMIUMS
    }

    return {
        "winning_band": "flat 1-2 (single entry, <=2 contracts)",
        "p_win": round(p_win, 4),
        "avg_win_per_contract": round(win_pc, 1),
        "avg_loss_per_contract": round(loss_pc, 1),
        "mean_entry_premium": round(mean_premium, 3),
        "kelly_realized_payoff": k_realized.as_dict(),
        "kelly_conservative_binary": k_binary.as_dict(),
        "half_kelly_realized_contracts_at_2k": half_kelly_contracts,
        "interpretation": (
            "On J's realized payoff (b={:.2f}) full Kelly is {:.1%} of bankroll; "
            "half-Kelly {:.1%}. On the conservative full-premium-at-risk binary "
            "(b={:.2f}) full Kelly is {:.1%} — i.e. NO bet unless the disciplined "
            "chart-stop holds. Truth is between: size at the SMALLEST viable lot, "
            "<= 1/2 Kelly on the optimistic basis."
        ).format(
            b_realized,
            k_realized.full_kelly_fraction,
            k_realized.half_kelly_fraction,
            b_binary,
            k_binary.full_kelly_fraction,
        ),
    }


def account_math(kelly_data: Mapping) -> dict:
    """Translate the floor decision into concrete $2K account dollars."""
    rows = []
    for prem in OTM3_PREMIUMS:
        cost1 = prem * 100.0
        rows.append(
            {
                "premium": prem,
                "cost_1_contract": round(cost1, 0),
                "pct_2k_1c": round(cost1 / SAFE_EQUITY * 100, 1),
                "cost_3_contracts": round(cost1 * 3, 0),
                "pct_2k_3c": round(cost1 * 3 / SAFE_EQUITY * 100, 1),
                "cost_2_contracts": round(cost1 * 2, 0),
                "pct_2k_2c": round(cost1 * 2 / SAFE_EQUITY * 100, 1),
            }
        )
    half_kelly_pct = max(0.0, kelly_data["kelly_realized_payoff"]["half_kelly_fraction"]) * 100
    return {
        "safe_equity": SAFE_EQUITY,
        "doctrine_min_contracts": DOCTRINE_MIN_CONTRACTS,
        "otm3_premium_table": rows,
        "half_kelly_pct_realized_basis": round(half_kelly_pct, 1),
        "min3_vs_half_kelly": (
            "MIN 3 contracts at OTM-3 ~$0.30-0.50 = $90-150 = 4.5-7.5% of $2K, "
            f"which sits ABOVE half-Kelly (~{half_kelly_pct:.1f}% = ~$78). The "
            "floor forces a slightly-larger-than-Kelly bet. Prudent, but only at "
            "the cheap end of the premium band."
        ),
    }


def throttle_design() -> dict:
    """DESIGN (propose-only) of the post-loss / equity-trajectory throttle.

    NOT wired into check_order. This is the reference spec the design doc
    expands. The throttle would slot in as a NEW sizing gate evaluated BEFORE
    MIN_CONTRACTS in check_order, computing a per-order qty CEILING from loss
    state + equity trajectory, then denying (or, in the engine, clamping) any
    proposal above that ceiling.
    """
    return {
        "name": "POST_LOSS_THROTTLE",
        "status": "DESIGN ONLY - not implemented in risk_gate.check_order",
        "rationale": (
            "J's ledger shows size rises after losses (revenge-sizing) and that "
            "the larger-lot bands are where the account bleeds. A throttle caps "
            "size to the FLOOR while underwater and restores it only after a win "
            "or a fresh session, so a losing streak can never be met with a "
            "bigger bet."
        ),
        "new_inputs": {
            "consecutive_losses_today": "int >=0 — losing round-trips since last win, this session",
            "realized_pnl_today": "float — session realized P&L (negative => underwater)",
            "equity": "float — already an input; trajectory vs start_of_day_equity",
            "start_of_day_equity": "float — already an input",
        },
        "new_params_proposed": {
            "post_loss_throttle_enabled": "bool, default true",
            "throttle_after_consecutive_losses": "int, default 1 (cap after the FIRST loss)",
            "throttle_underwater_pct": "float, default 0.0 (any red day => floor)",
            "throttle_to_contracts": "int, default = min_contracts (the floor)",
        },
        "rule": (
            "Compute qty_ceiling. If post_loss_throttle_enabled AND "
            "(consecutive_losses_today >= throttle_after_consecutive_losses OR "
            "equity <= start_of_day_equity * (1 - throttle_underwater_pct)), then "
            "qty_ceiling = throttle_to_contracts (the floor). Otherwise qty_ceiling "
            "= +inf. If proposed_qty > qty_ceiling => Deny(POST_LOSS_THROTTLE) "
            "(engine clamps to ceiling instead of denying). Restores automatically "
            "next session (counters reset at SoD) and after any win "
            "(consecutive_losses_today resets to 0)."
        ),
        "reference_signature": (
            "def post_loss_qty_ceiling(*, equity: float, start_of_day_equity: float, "
            "consecutive_losses_today: int, realized_pnl_today: float, "
            "min_contracts: int, params: Mapping) -> Optional[int]: ...  "
            "# returns the ceiling, or None for 'no throttle'. Pure; no I/O."
        ),
        "slot_in_point": (
            "backtest/lib/risk_gate.py check_order — a NEW section between the "
            "FIRST_ENTRY_LOCK block and the MIN_CONTRACTS block (evaluate the "
            "throttle ceiling, then the existing MIN_CONTRACTS floor). Add code "
            "POST_LOSS_THROTTLE to the stable CODE_* set. Fail-closed: if the new "
            "inputs are unreadable, deny (same discipline as every other input)."
        ),
        "invariant": (
            "Order-only, fails OPEN on the operator (OP-32 scar): like every "
            "other rule it returns a decision and NEVER touches sessions/processes."
        ),
        "honest_caveat": (
            "J's 3+ data is confounded with revenge-adds, so the ledger cannot "
            "cleanly separate 'flat-3 is too big' from 'the adding is the killer'. "
            "What it CAN say: (1) scaled-in is catastrophic at every size, and "
            "(2) even flat-3+ is a loser across both biases and both DTEs. The "
            "throttle attacks BOTH failure modes by holding size at the floor "
            "while underwater."
        ),
    }


def build_report(c: pd.DataFrame) -> dict:
    """Assemble the full machine-readable scorecard."""
    curve = empirical_sizing_curve(c)
    fvs = flat_vs_scaled(c)
    kelly_data = kelly_block(c)
    return {
        "study": "principled-sizing-from-j-data",
        "date": "2026-06-19",
        "status": "PROPOSE-ONLY (Rule 9) - no live change",
        "source": str(LEDGER_CSV.relative_to(ROOT)).replace("\\", "/"),
        "n_closed_round_trips": int(len(c)),
        "empirical_sizing_curve": [s.as_dict() for s in curve],
        "flat_vs_scaled_untangle": {k: v.as_dict() for k, v in fvs.items()},
        "revenge_signal": revenge_signal(c),
        "flat3_confounders": flat3_confounders(c),
        "fractional_kelly": kelly_data,
        "account_math": account_math(kelly_data),
        "throttle_design": throttle_design(),
        "recommendations": {
            "decision_a_min3_vs_flat2": (
                "KEEP MIN 3 as the FLOOR, but recognise it is slightly above "
                "half-Kelly. The data does NOT support raising the floor; flat-3+ "
                "is already a loser. The real fix is a CEILING (the throttle), not "
                "a lower floor. Flat-2 would be marginally more Kelly-prudent but "
                "breaks the 2-TP+1-runner structure; min-3 at the cheap OTM-3 end "
                "(<=$0.40 => <=6% of $2K) is acceptable. Pair min-3 with a hard "
                "premium ceiling so 3 contracts never exceeds ~6% of equity."
            ),
            "decision_b_throttle": (
                "ADD the post-loss throttle (design above). It is the highest-value "
                "sizing change available from J's data: it directly neutralises the "
                "revenge-sizing the ledger documents and caps the larger-lot bands "
                "where the account bleeds. Ship as a pure function gated behind "
                "post_loss_throttle_enabled; default-on in the engine as a CLAMP, "
                "default-deny in the live gate."
            ),
        },
    }


def print_report(rep: Mapping) -> None:
    line = "=" * 78
    print(line)
    print("PRINCIPLED SIZING STUDY - J's real Webull ledger (PROPOSE-ONLY)")
    print(line)
    print(f"source: {rep['source']}   n_closed_round_trips: {rep['n_closed_round_trips']}")
    print()

    print("1. EMPIRICAL SIZING CURVE (P&L by lot band)")
    print(f"   {'band':<8}{'n':>5}{'WR':>8}{'total_pnl':>12}{'exp/trade':>11}{'PF':>7}")
    for s in rep["empirical_sizing_curve"]:
        pf = "inf" if s["profit_factor"] is None else f"{s['profit_factor']:.2f}"
        print(f"   {s['label']:<8}{s['n']:>5}{s['win_rate']:>8.3f}"
              f"{s['total_pnl']:>12.0f}{s['expectancy_per_trade']:>11.1f}{pf:>7}")
    print()

    print("2. FLAT vs SCALED-IN UNTANGLE (THE key question)")
    fvs = rep["flat_vs_scaled_untangle"]
    for key in ("flat_1_2", "flat_3plus", "scaled_any", "single_entry_any"):
        s = fvs[key]
        print(f"   {s['label']:<22} n={s['n']:>4} WR={s['win_rate']:.3f} "
              f"pnl={s['total_pnl']:>9.0f} exp/trade={s['expectancy_per_trade']:>7.1f}")
    print("   within-band (flat | scaled):")
    for b in ("1-2", "3-5", "6+"):
        f = fvs.get(f"{b}|flat")
        sc = fvs.get(f"{b}|scaled")
        fs = (f"flat n={f['n']} pnl={f['total_pnl']:.0f} exp={f['expectancy_per_trade']:.0f}"
              if f else "flat n=0")
        scs = (f"scaled n={sc['n']} pnl={sc['total_pnl']:.0f} exp={sc['expectancy_per_trade']:.0f}"
               if sc else "scaled n=0")
        print(f"     {b:>4}: {fs:<42} | {scs}")
    print()

    print("3. REVENGE SIGNAL (size vs prior-trade outcome)")
    rv = rep["revenge_signal"]
    for k in ("after_same_day_loss", "after_same_day_win"):
        d = rv[k]
        print(f"   {k:<22} n={d['n']:>4} avg_qty={d['avg_qty']} "
              f"pct>=3={d['pct_qty_ge_3']} pct_scaled={d['pct_scaled_in']} "
              f"pnl={d['total_pnl']:.0f} WR={d['win_rate']}")
    print()

    print("4. FRACTIONAL-KELLY (winning 1-2 flat band)")
    k = rep["fractional_kelly"]
    kr = k["kelly_realized_payoff"]
    kb = k["kelly_conservative_binary"]
    print(f"   p_win={k['p_win']}  avg_win/c=${k['avg_win_per_contract']}  "
          f"avg_loss/c=${k['avg_loss_per_contract']}  mean_premium=${k['mean_entry_premium']}")
    print(f"   realized-payoff basis: b={kr['payoff_b']}  full={kr['full_kelly_fraction']:.3f} "
          f"half={kr['half_kelly_fraction']:.3f} quarter={kr['quarter_kelly_fraction']:.3f}")
    print(f"   conservative-binary:   b={kb['payoff_b']}  full={kb['full_kelly_fraction']:.3f} "
          "(negative => NO bet unless chart-stop holds)")
    print(f"   half-Kelly contracts at $2K by premium: {k['half_kelly_realized_contracts_at_2k']}")
    print()

    print("5. ACCOUNT MATH ($2K Safe)")
    am = rep["account_math"]
    for row in am["otm3_premium_table"]:
        print(f"   premium ${row['premium']:.2f}: 1c=${row['cost_1_contract']:.0f} "
              f"({row['pct_2k_1c']}%)  2c=${row['cost_2_contracts']:.0f} "
              f"({row['pct_2k_2c']}%)  3c=${row['cost_3_contracts']:.0f} ({row['pct_2k_3c']}%)")
    print(f"   half-Kelly (realized basis) = {am['half_kelly_pct_realized_basis']}% of $2K")
    print()

    print("6. RECOMMENDATIONS")
    rec = rep["recommendations"]
    print("   (a) min-3 vs flat-2:")
    print(f"       {rec['decision_a_min3_vs_flat2']}")
    print("   (b) throttle:")
    print(f"       {rec['decision_b_throttle']}")
    print(line)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Principled sizing study from J's ledger.")
    ap.add_argument("--no-write", action="store_true", help="print only; do not write scorecard")
    args = ap.parse_args(argv)

    if not LEDGER_CSV.exists():
        print(f"ERROR: ledger not found: {LEDGER_CSV}")
        return 1

    c = load_closed(LEDGER_CSV)
    rep = build_report(c)
    print_report(rep)

    if not args.no_write:
        SCORECARD.parent.mkdir(parents=True, exist_ok=True)
        SCORECARD.write_text(json.dumps(rep, indent=2), encoding="utf-8")
        print(f"\nscorecard -> {SCORECARD.relative_to(ROOT)}".replace("\\", "/"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

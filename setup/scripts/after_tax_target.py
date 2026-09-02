"""after_tax_target.py -- what the $100-200/day target is worth AFTER TAX.

*** NOT TAX ADVICE. *** This is arithmetic under assumptions you supply, written so the
assumptions are visible instead of buried. Nothing here is a statement about J's actual tax
situation, filing status, state, carryforwards, or entity structure, and nobody in this repo
is qualified to make one. Its real output is the CPA QUESTION LIST at the bottom: the point
is to walk into that conversation knowing which numbers move.

WHY IT EXISTS. CLAUDE.md's target is "$100-200/day PER ACCOUNT". Every number in this repo
-- the gate, the dollar model, the daily P&L -- is PRE-TAX. For a strategy whose entire
output is short-term gains, the pre-tax figure is not the figure that reaches the bank, and
the gap is large enough to change what "the target" should even be.

THE ONE STRUCTURAL FACT WORTH THE WHOLE FILE. SPY is an ETF, so SPY options are ordinary
equity options: gains are short-term capital gains, taxed at ordinary income rates, and the
wash-sale rules apply. SPX and XSP are broad-based INDEX options, which are generally
Section 1256 contracts: 60% long-term / 40% short-term regardless of holding period, marked
to market at year end, and NOT subject to wash-sale. A 0DTE strategy holds nothing overnight,
so under ordinary treatment 100% of its gains are short-term -- the worst case -- while the
same read expressed in XSP would blend 60/40. That is a structural difference in the
after-tax result of the SAME trade, and it is the strongest argument the XSP box in
OPUS-WORK-ORDER-2026-09 has going for it. VERIFY WITH A CPA before acting on it: the
classification depends on facts about the instrument and the taxpayer, not on this script.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
OUT = REPO / "analysis" / "after-tax"

TRADING_DAYS_PER_YEAR = 252
TRADING_DAYS_PER_MONTH = 20

# Two ILLUSTRATIVE brackets. Not a recommendation, not a lookup of anyone's real rate --
# they bracket a plausible range so the sensitivity is visible.
BRACKETS = {
    "illustrative_low": {
        "label": "22% federal marginal + 5% state",
        "federal_ordinary": 0.22,
        "state": 0.05,
        "federal_longterm": 0.15,
    },
    "illustrative_high": {
        "label": "32% federal marginal + 5% state",
        "federal_ordinary": 0.32,
        "state": 0.05,
        "federal_longterm": 0.15,
    },
}


def ordinary_rate(b: dict) -> float:
    """Everything short-term: SPY options under ordinary equity-option treatment."""
    return b["federal_ordinary"] + b["state"]


def section_1256_rate(b: dict) -> float:
    """60/40 blend. State is applied to the whole gain -- most states do not mirror the
    federal long-term preference, and assuming they do would flatter the XSP case."""
    fed = 0.60 * b["federal_longterm"] + 0.40 * b["federal_ordinary"]
    return fed + b["state"]


def after_tax(gross_per_day: float, rate: float) -> dict:
    keep = 1.0 - rate
    return {
        "gross_per_day": round(gross_per_day, 2),
        "effective_rate": round(rate, 4),
        "net_per_day": round(gross_per_day * keep, 2),
        "net_per_month_20d": round(gross_per_day * keep * TRADING_DAYS_PER_MONTH, 2),
        "net_per_year_252d": round(gross_per_day * keep * TRADING_DAYS_PER_YEAR, 2),
        "gross_needed_to_net_the_target": None,  # filled by build() where a target exists
    }


def gross_needed(net_target: float, rate: float) -> float:
    keep = 1.0 - rate
    return net_target / keep if keep > 0 else float("inf")


def build(targets=(100.0, 200.0)) -> dict:
    rows = []
    for key, b in BRACKETS.items():
        ord_r = ordinary_rate(b)
        s1256_r = section_1256_rate(b)
        for t in targets:
            rows.append({
                "bracket": key, "bracket_label": b["label"], "gross_target_per_day": t,
                "spy_ordinary": {**after_tax(t, ord_r),
                                 "gross_needed_to_net_the_target": round(gross_needed(t, ord_r), 2)},
                "xsp_section_1256": {**after_tax(t, s1256_r),
                                     "gross_needed_to_net_the_target": round(gross_needed(t, s1256_r), 2)},
                "section_1256_advantage_per_day": round(t * (ord_r - s1256_r), 2),
                "section_1256_advantage_per_year": round(
                    t * (ord_r - s1256_r) * TRADING_DAYS_PER_YEAR, 2),
            })
    return {
        "_DISCLAIMER": ("NOT TAX ADVICE. Arithmetic under illustrative assumptions only. "
                        "No statement about any real taxpayer's situation, filing status, "
                        "state, carryforwards or entity structure is made or implied."),
        "trading_days_per_year": TRADING_DAYS_PER_YEAR,
        "trading_days_per_month": TRADING_DAYS_PER_MONTH,
        "brackets": BRACKETS,
        "rows": rows,
        "cpa_questions": CPA_QUESTIONS,
        "assumptions_that_would_change_everything": [
            "That every gain is short-term. True for 0DTE under ordinary treatment, and it "
            "is the WORST case -- there is no long-term rate to reach for.",
            "That gains are taxed in the year realised with no offsetting losses "
            "carried in. A real first year may have carryforwards that change the "
            "effective rate to zero until they are used up.",
            "That the state applies a flat rate to the whole gain and does not mirror the "
            "federal long-term preference. Some do; assuming otherwise would flatter XSP.",
            "That no entity structure, mark-to-market election (IRC 475(f)) or "
            "trader-tax-status treatment applies. Any of those changes the answer "
            "materially, and whether they are available is a question for a professional.",
            "That wash-sale deferrals net out within the year. Across roughly 500 round "
            "trips on ONE underlying they may not, and that is a bookkeeping problem "
            "before it is a tax problem.",
        ],
    }


CPA_QUESTIONS = [
    "SPY options vs XSP/SPX options: is the Section 1256 60/40 treatment actually "
    "available on the index products for how I trade, and what would it be worth against "
    "my real marginal rate? (This repo's own arithmetic says the gap is the single largest "
    "lever on after-tax return that does not require the strategy to get better.)",
    "Wash sales across roughly 500 round trips a year on a single underlying: what is the "
    "realistic year-end deferral, and does it materially change what I owe or only when I "
    "owe it? What records do you need me to keep from day one?",
    "Does trader tax status apply to this pattern of activity, and if so is an IRC 475(f) "
    "mark-to-market election worth making? What is the deadline, and what does it cost me "
    "if the strategy is later abandoned?",
    "Estimated quarterly payments: given income that is lumpy and could be negative for a "
    "quarter, what is the safe-harbour approach that avoids an underpayment penalty "
    "without over-remitting?",
    "If a year ends net negative, what is actually deductible against ordinary income, "
    "what carries forward, and how does that interact with the answer on 475(f)?",
    "Is there any reason to hold this in an entity rather than personally, at this size?",
    "State treatment: does my state mirror the federal long-term/short-term distinction, "
    "or tax the whole gain at one rate?",
]


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="After-tax view of the daily target. NOT TAX ADVICE.")
    ap.add_argument("--targets", default="100,200")
    ap.add_argument("--no-write", action="store_true")
    args = ap.parse_args(argv)

    targets = tuple(float(x) for x in args.targets.split(","))
    rep = build(targets)

    print("*** NOT TAX ADVICE -- illustrative arithmetic only ***\n")
    print(f"{'bracket':<20} {'gross/day':>10} {'SPY net/day':>12} {'XSP net/day':>12} "
          f"{'XSP edge/yr':>12}")
    for r in rep["rows"]:
        print(f"{r['bracket']:<20} {r['gross_target_per_day']:>10.0f} "
              f"{r['spy_ordinary']['net_per_day']:>12.2f} "
              f"{r['xsp_section_1256']['net_per_day']:>12.2f} "
              f"{r['section_1256_advantage_per_year']:>12.2f}")
    print("\nTo NET the target, gross must be:")
    for r in rep["rows"]:
        print(f"  {r['bracket']:<20} net ${r['gross_target_per_day']:.0f}/day  ->  "
              f"SPY ${r['spy_ordinary']['gross_needed_to_net_the_target']:.2f} gross  |  "
              f"XSP ${r['xsp_section_1256']['gross_needed_to_net_the_target']:.2f} gross")

    if not args.no_write:
        OUT.mkdir(parents=True, exist_ok=True)
        p = OUT / "after-tax-target.json"
        body = json.dumps(rep, indent=2)
        body.encode("utf-8")
        tmp = p.with_suffix(".json.tmp")
        tmp.write_text(body, encoding="utf-8")
        tmp.replace(p)
        print(f"\nwrote {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

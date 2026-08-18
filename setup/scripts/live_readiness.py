"""live_readiness.py -- the per-arm LIVE-MONEY READINESS instrument.

WHY THIS EXISTS (built 2026-08-18, closing markdown/planning/ROADMAP.md's Gate 2
"criterion partially undefined" gap): CLAUDE.md's account-context table states a "Live
threshold (per account independently): >=20 trades, WR>=45%, positive expectancy, <=2 rule
breaks" -- the ONE gate that is supposed to say an arm has earned the right to trade real
money. Nothing computed it. Grepping setup/scripts, backtest/tools, and
automation/state/fleet found ONLY prose: CLAUDE.md itself, a narrative "M/4 conditions met"
template in .claude/agents/treasurer.md, and passing mentions in analysis docs. ROADMAP.md
(2026-08-18) named this Gate 2 "criterion PARTIALLY DEFINED" for exactly this reason. This
script is the missing instrument.

THIS IS A REPORTING INSTRUMENT ONLY. It arms nothing, changes no gate, edits no
params*.json, places no orders. OP-0 #1 still applies in full: a PASS verdict here is
evidence for a conversation with J about live-money arming, never a trigger to act alone.

INPUTS:
  - automation/state/fleet/fills_fifo.py#mine_real_arm_fills(arm_id) -- the ONE FIFO
    round-trip reconstructor for REAL (attribution=='engine') fills. Round-trip dict keys:
    date, symbol, side, entry_ts_et, entry_premium, exit_ts_et, exit_premium, qty, real_pnl,
    _note.
  - automation/state/fleet/accounts.json's `arms` list -- roster is DERIVED every run,
    never hardcoded: status == 'active' AND account_number starts with 'PA' (excludes the
    two futures arms, mes-linear-sim / mes-mnq-div-futures, account_number '5WW73759',
    status pending_build / dormant anyway -- the account-number check is belt-and-suspenders
    against a future non-PA SPY account, not a substitute for the status check).
  - automation/state/rule-breaks.jsonl -- read as-is. CONFIRMED 2026-08-18 (every row's
    keys grepped + cross-checked against backtest/autoresearch/eod_deep/schema.py's own
    EodDeepDive.rule_breaks: list[str]): this ledger carries NO arm/account attribution
    field. Every rule break in it is reported book-level/unattributed -- this script never
    guesses which arm a break belongs to. If a future row DOES carry one of
    _RULE_BREAK_ATTRIBUTION_KEYS, this is picked up automatically (see
    _rule_breaks_for_arm) -- but note the counting there only matches an exact arm_id
    string; a future schema keyed by account_number instead would need its own translation,
    not silently attempted here.

OUTPUTS:
  - human table (default) or --json machine payload to stdout
  - analysis/recommendations/live-readiness.json, ALWAYS written, generated_et stamped via
    et_clock.et_now() (never bash TZ -- this box runs Mountain, ET = local+2)

DISCLOSURE (not smoothed, per this rig's standing rule): the 5 SPY arms trade ONE shared
signal at r=0.846 / 95.7% sign agreement
(analysis/deep-research/LEVER-CORRELATION-2026-08-06.md). A book-wide n is inflated
roughly 2.3-3.5x versus 5 independent samples. Per-arm rows print FIRST and prominently;
any aggregate is explicitly labeled a CORRELATED ROLLUP, never independent evidence.

Run:
    backtest/.venv/Scripts/python.exe setup/scripts/live_readiness.py            # human table
    backtest/.venv/Scripts/python.exe setup/scripts/live_readiness.py --json     # machine payload
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = REPO / "setup" / "scripts"
FLEET_DIR = REPO / "automation" / "state" / "fleet"
for _p in (SCRIPTS_DIR, FLEET_DIR):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now  # noqa: E402
from fills_fifo import mine_real_arm_fills  # noqa: E402

ACCOUNTS_PATH = FLEET_DIR / "accounts.json"
RULE_BREAKS_PATH = REPO / "automation" / "state" / "rule-breaks.jsonl"
OUT_PATH = REPO / "analysis" / "recommendations" / "live-readiness.json"

# CLAUDE.md account-context table, "Live threshold (per account independently)".
MIN_TRADES = 20
MIN_WIN_RATE = 0.45
MIN_RULE_BREAKS_OK = 2

# Fields that WOULD carry arm/account attribution on a rule-break row, if this ledger ever
# grows one. Checked defensively every run rather than hardcoded to "never".
_RULE_BREAK_ATTRIBUTION_KEYS = ("arm", "arm_id", "account", "account_id", "account_number")

_CORRELATION_DISCLOSURE = (
    "The 5 active SPY arms trade ONE shared signal: r=0.846 (r^2=0.716), 95.7% sign "
    "agreement, 139 matched trade pairs, every one of 15 pairwise daily correlations "
    "positive (analysis/deep-research/LEVER-CORRELATION-2026-08-06.md, 2026-08-16 "
    "forward-checked). A book-wide n is NOT 5x independent evidence -- read per-arm rows "
    "first; any aggregate below is a CORRELATED ROLLUP."
)


# --------------------------------------------------------------------------------------- #
# Pure gate-criteria functions -- each is independently testable with zero I/O.
# --------------------------------------------------------------------------------------- #
def criterion_n_trades(n: int) -> bool:
    """CLAUDE.md live threshold: >= 20 closed real round trips."""
    return n >= MIN_TRADES


def criterion_win_rate(win_rate: float) -> bool:
    """CLAUDE.md live threshold: win rate >= 45%."""
    return win_rate >= MIN_WIN_RATE


def criterion_expectancy(expectancy: float) -> bool:
    """CLAUDE.md live threshold: expectancy must be POSITIVE -- strictly greater than 0.
    Exactly $0.00/trade FAILS; the doctrine says "positive", not "non-negative"."""
    return expectancy > 0


def criterion_rule_breaks(count: int | None) -> bool | None:
    """CLAUDE.md live threshold: <= 2 rule breaks. Returns None (UNKNOWN) when the count
    itself is unattributable -- see _rule_breaks_for_arm. None must NEVER be treated as
    True or False by a caller; it means "cannot evaluate this criterion", not "pass"."""
    if count is None:
        return None
    return count <= MIN_RULE_BREAKS_OK


# --------------------------------------------------------------------------------------- #
# Rule-break attribution -- refuse to guess.
# --------------------------------------------------------------------------------------- #
def _rule_breaks_for_arm(rows: list[dict], arm_id: str) -> tuple[int | None, str]:
    """Attribute rule-breaks.jsonl rows to one arm, or explicitly refuse to guess.

    CONFIRMED 2026-08-18 against the real ledger (grep of every row's keys + cross-check
    against backtest/autoresearch/eod_deep/schema.py's EodDeepDive.rule_breaks: list[str]):
    this ledger carries NO arm/account attribution field today. If that ever changes, this
    function picks it up automatically -- but it never GUESSES: a ledger where even ONE row
    lacks an attribution key is treated as fully unattributable, because a partial guess is
    worse than an honest "unknown".
    """
    if not rows:
        return 0, "0 total rule breaks logged (book-wide) -- ledger is empty"
    attributed = [r for r in rows
                  if any(r.get(k) not in (None, "") for k in _RULE_BREAK_ATTRIBUTION_KEYS)]
    if len(attributed) != len(rows):
        unattributed_n = len(rows) - len(attributed)
        return None, (
            f"{len(rows)} total rule break(s) logged book-wide ({unattributed_n} carrying no "
            f"arm/account key); rule-breaks.jsonl's schema does not guarantee attribution -- "
            f"cannot assign to '{arm_id}' specifically. Reported as book-level, unattributed, "
            f"never silently assigned to an arm or dropped."
        )
    count = sum(
        1 for r in attributed
        if str(r.get("arm") or r.get("arm_id") or r.get("account")
               or r.get("account_id") or r.get("account_number")) == arm_id
    )
    return count, f"{count} of {len(rows)} book-wide rule break(s) attributed to '{arm_id}'"


# --------------------------------------------------------------------------------------- #
# Context math (NOT gate criteria).
# --------------------------------------------------------------------------------------- #
def _max_consecutive_losses(pnls_in_order: list[float]) -> int:
    """Longest streak of non-win round trips (real_pnl <= 0) in chronological order."""
    best = cur = 0
    for p in pnls_in_order:
        if p <= 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _context_stats(trips_sorted: list[dict]) -> dict:
    """CONTEXT metrics -- explicitly NOT part of the 4-condition CLAUDE.md gate. These
    exist because the 4 criteria alone can pass a bad book (task brief, verbatim)."""
    pnls_in_order = [float(t["real_pnl"]) for t in trips_sorted]
    wins = [p for p in pnls_in_order if p > 0]
    losses = [p for p in pnls_in_order if p <= 0]
    total_pnl = sum(pnls_in_order)
    avg_win = statistics.fmean(wins) if wins else None
    avg_loss = statistics.fmean(losses) if losses else None
    payoff_ratio = (
        avg_win / abs(avg_loss)
        if (avg_win is not None and avg_loss is not None and avg_loss != 0)
        else None
    )
    by_day: dict[str, float] = {}
    for t in trips_sorted:
        by_day[t["date"]] = by_day.get(t["date"], 0.0) + float(t["real_pnl"])
    best_day_date, best_day_pnl = max(by_day.items(), key=lambda kv: kv[1])
    dates = sorted(by_day.keys())
    concentration_share = (best_day_pnl / total_pnl) if total_pnl != 0 else None
    return {
        "total_pnl": round(total_pnl, 2),
        "median_trade": round(statistics.median(pnls_in_order), 2),
        "largest_win": round(max(pnls_in_order), 2),
        "largest_loss": round(min(pnls_in_order), 2),
        "avg_win": round(avg_win, 2) if avg_win is not None else None,
        "avg_loss": round(avg_loss, 2) if avg_loss is not None else None,
        "payoff_ratio": round(payoff_ratio, 3) if payoff_ratio is not None else None,
        "max_consecutive_losses": _max_consecutive_losses(pnls_in_order),
        "date_range": [dates[0], dates[-1]],
        "trading_days_represented": len(by_day),
        "concentration": {
            "best_day": best_day_date,
            "best_day_pnl": round(best_day_pnl, 2),
            "share_of_total_pnl": (
                round(concentration_share, 4) if concentration_share is not None else None
            ),
            "note": (
                None if concentration_share is not None
                else "total_pnl is $0.00 -- a 'share of total' is not meaningful; "
                     "best_day_pnl is printed raw instead"
            ),
        },
    }


# --------------------------------------------------------------------------------------- #
# Per-arm scoring
# --------------------------------------------------------------------------------------- #
def score_round_trips(trips: list[dict], rule_breaks_count: int | None,
                       rule_breaks_note: str) -> dict:
    """Score ONE arm's closed real round trips against CLAUDE.md's 4-condition live
    threshold, plus CONTEXT metrics. `trips` is the exact return shape of
    fills_fifo.mine_real_arm_fills -- each dict needs at least real_pnl, entry_ts_et, date.
    Pass synthetic dicts directly in tests; no I/O happens in this function.
    """
    n = len(trips)
    rb_pass = criterion_rule_breaks(rule_breaks_count)
    rb_criterion = {
        "value": rule_breaks_count, "threshold": f"<={MIN_RULE_BREAKS_OK}",
        "pass": rb_pass, "note": rule_breaks_note,
    }
    if n == 0:
        return {
            "insufficient_data": True,
            "n_trades": 0,
            "win_rate": None,
            "expectancy": None,
            "criteria": {
                "n_trades": {"value": 0, "threshold": f">={MIN_TRADES}", "pass": False},
                "win_rate": {"value": None, "threshold": f">={MIN_WIN_RATE:.1%}", "pass": None},
                "expectancy": {"value": None, "threshold": "> $0.00 (exactly $0.00 FAILS)",
                               "pass": None},
                "rule_breaks": rb_criterion,
            },
            "overall_verdict": "INSUFFICIENT",
            "context": None,
            "note": "INSUFFICIENT DATA -- zero closed real round trips for this arm. "
                    "Never reported as a 0% win rate.",
        }
    trips_sorted = sorted(trips, key=lambda t: t["entry_ts_et"])
    pnls_in_order = [float(t["real_pnl"]) for t in trips_sorted]
    win_rate = sum(1 for p in pnls_in_order if p > 0) / n
    expectancy = statistics.fmean(pnls_in_order)
    n_pass = criterion_n_trades(n)
    wr_pass = criterion_win_rate(win_rate)
    exp_pass = criterion_expectancy(expectancy)
    if rb_pass is None:
        overall = "UNKNOWN"
    elif n_pass and wr_pass and exp_pass and rb_pass:
        overall = "PASS"
    else:
        overall = "FAIL"
    return {
        "insufficient_data": False,
        "n_trades": n,
        "win_rate": round(win_rate, 4),
        "expectancy": round(expectancy, 2),
        "criteria": {
            "n_trades": {"value": n, "threshold": f">={MIN_TRADES}", "pass": n_pass},
            "win_rate": {"value": round(win_rate, 4), "threshold": f">={MIN_WIN_RATE:.1%}",
                         "pass": wr_pass},
            "expectancy": {"value": round(expectancy, 2),
                           "threshold": "> $0.00 (exactly $0.00 FAILS)", "pass": exp_pass},
            "rule_breaks": rb_criterion,
        },
        "overall_verdict": overall,
        "context": _context_stats(trips_sorted),
    }


# --------------------------------------------------------------------------------------- #
# Arm roster + orchestration
# --------------------------------------------------------------------------------------- #
def _active_spy_arms(accounts_path: Path = ACCOUNTS_PATH) -> list[str]:
    """Derive the live SPY arm roster from accounts.json -- NEVER hardcoded.

    status == "active" AND account_number starts with "PA" (the Alpaca paper-account
    prefix every SPY arm on this rig uses). The account_number check is a second,
    independent guard against the two futures arms (mes-linear-sim: pending_build,
    mes-mnq-div-futures: dormant; both account_number "5WW73759") -- belt-and-suspenders
    with the status filter, not a substitute for it.
    """
    data = json.loads(accounts_path.read_text(encoding="utf-8"))
    out = []
    for arm in data.get("arms", []):
        if arm.get("status") != "active":
            continue
        acct = str(arm.get("account_number") or "")
        if not acct.startswith("PA"):
            continue
        arm_id = arm.get("id")
        if arm_id:
            out.append(arm_id)
    return out


def _arm_metadata(accounts_path: Path = ACCOUNTS_PATH) -> dict[str, dict]:
    data = json.loads(accounts_path.read_text(encoding="utf-8"))
    return {
        arm["id"]: {"display_name": arm.get("display_name"),
                    "account_number": arm.get("account_number")}
        for arm in data.get("arms", []) if arm.get("id")
    }


def _load_rule_breaks(path: Path = RULE_BREAKS_PATH) -> list[dict]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def _book_wide_rollup(arms_out: list[dict]) -> dict:
    verdicts = Counter(a.get("overall_verdict") for a in arms_out)
    total_trips = sum(a.get("n_trades") or 0 for a in arms_out)
    total_pnl = sum((a.get("context") or {}).get("total_pnl") or 0.0 for a in arms_out)
    return {
        "_label": "CORRELATED ROLLUP -- NOT independent evidence. " + _CORRELATION_DISCLOSURE,
        "arms_scored": len(arms_out),
        "arms_pass": verdicts.get("PASS", 0),
        "arms_fail": verdicts.get("FAIL", 0),
        "arms_unknown": verdicts.get("UNKNOWN", 0),
        "arms_insufficient": verdicts.get("INSUFFICIENT", 0),
        "total_closed_round_trips": total_trips,
        "total_real_pnl": round(total_pnl, 2),
    }


def build_report(accounts_path: Path = ACCOUNTS_PATH, rule_breaks_path: Path = RULE_BREAKS_PATH,
                  fills_ledger_path: Path | None = None, now_et: str | None = None) -> dict:
    """Orchestrate the full per-arm live-readiness report. Every path is injectable so
    tests run entirely against tmp_path fixtures -- never the live ledgers."""
    arm_ids = _active_spy_arms(accounts_path)
    arm_meta = _arm_metadata(accounts_path)
    rule_break_rows = _load_rule_breaks(rule_breaks_path)
    arms_out = []
    for arm_id in arm_ids:
        if fills_ledger_path is not None:
            trips = mine_real_arm_fills(arm_id, ledger_path=fills_ledger_path)
        else:
            trips = mine_real_arm_fills(arm_id)
        rb_count, rb_note = _rule_breaks_for_arm(rule_break_rows, arm_id)
        scored = score_round_trips(trips, rb_count, rb_note)
        scored["arm_id"] = arm_id
        meta = arm_meta.get(arm_id, {})
        scored["display_name"] = meta.get("display_name")
        scored["account_number"] = meta.get("account_number")
        arms_out.append(scored)
    return {
        "generated_et": now_et or et_now().isoformat(timespec="seconds"),
        "instrument": "setup/scripts/live_readiness.py",
        "gate_source": (
            "CLAUDE.md account-context table: \"Live threshold (per account independently): "
            ">= 20 trades, WR >= 45%, positive expectancy, <= 2 rule breaks.\""
        ),
        "thresholds": {
            "min_trades": MIN_TRADES, "min_win_rate": MIN_WIN_RATE,
            "min_rule_breaks_ok": MIN_RULE_BREAKS_OK,
            "expectancy_rule": "strictly > 0 (exactly $0.00 FAILS)",
        },
        "disclosure": {
            "correlation": _CORRELATION_DISCLOSURE,
            "rule_breaks_ledger": (
                "automation/state/rule-breaks.jsonl carries no arm/account attribution field "
                "as verified this run -- see each arm's criteria.rule_breaks.note."
            ),
        },
        "arms": arms_out,
        "book_wide_rollup": _book_wide_rollup(arms_out),
    }


# --------------------------------------------------------------------------------------- #
# Human-readable console output
# --------------------------------------------------------------------------------------- #
def _mark(passed: bool | None) -> str:
    if passed is None:
        return "UNK"
    return "PASS" if passed else "FAIL"


def _fmt_money(x: float | None) -> str:
    if x is None:
        return "n/a"
    sign = "-" if x < 0 else ""
    return f"{sign}${abs(x):,.2f}"


def print_human_report(report: dict) -> None:
    print(f"LIVE READINESS -- {report['generated_et']} ET")
    print(f"gate: {report['gate_source']}")
    print()
    header = (f"{'ARM':<10} {'N_TRADES':<12} {'WIN_RATE':<14} {'EXPECTANCY':<18} "
              f"{'RULE_BREAKS':<14} {'OVERALL':<12}")
    print(header)
    print("-" * len(header))
    for arm in report["arms"]:
        aid = arm["arm_id"]
        if arm.get("insufficient_data"):
            print(f"{aid:<10} {'INSUFFICIENT DATA -- 0 closed real round trips':<60} "
                  f"{'INSUFFICIENT':<12}")
            continue
        c = arm["criteria"]
        n_cell = f"{c['n_trades']['value']:>3} {_mark(c['n_trades']['pass'])}"
        wr_cell = f"{c['win_rate']['value']:.1%} {_mark(c['win_rate']['pass'])}"
        exp_cell = f"{_fmt_money(c['expectancy']['value'])} {_mark(c['expectancy']['pass'])}"
        rb_val = c["rule_breaks"]["value"]
        rb_str = "UNK" if rb_val is None else str(rb_val)
        rb_cell = f"{rb_str} {_mark(c['rule_breaks']['pass'])}"
        print(f"{aid:<10} {n_cell:<12} {wr_cell:<14} {exp_cell:<18} {rb_cell:<14} "
              f"{arm['overall_verdict']:<12}")
    print()
    print("rule-break attribution: " + report["disclosure"]["rule_breaks_ledger"])
    print()
    print("CONTEXT (not gate criteria -- disclosure, not a pass/fail bar):")
    for arm in report["arms"]:
        aid = arm["arm_id"]
        ctx = arm.get("context")
        if not ctx:
            print(f"  {aid}: -- (insufficient data)")
            continue
        conc = ctx["concentration"]
        share = (f"{conc['share_of_total_pnl']:.1%}" if conc["share_of_total_pnl"] is not None
                 else "n/a")
        print(f"  {aid}:")
        print(f"    total_pnl={_fmt_money(ctx['total_pnl'])}  "
              f"median_trade={_fmt_money(ctx['median_trade'])}  "
              f"largest_win={_fmt_money(ctx['largest_win'])}  "
              f"largest_loss={_fmt_money(ctx['largest_loss'])}")
        print(f"    payoff_ratio={ctx['payoff_ratio']}  "
              f"max_consecutive_losses={ctx['max_consecutive_losses']}  "
              f"date_range={ctx['date_range'][0]}..{ctx['date_range'][1]} "
              f"({ctx['trading_days_represented']} days)")
        print(f"    concentration: best day {conc['best_day']} "
              f"({_fmt_money(conc['best_day_pnl'])}) = {share} of total P&L")
    print()
    roll = report["book_wide_rollup"]
    print("=" * 78)
    print(roll["_label"])
    print("=" * 78)
    print(f"  arms_scored={roll['arms_scored']}  PASS={roll['arms_pass']}  "
          f"FAIL={roll['arms_fail']}  UNKNOWN={roll['arms_unknown']}  "
          f"INSUFFICIENT={roll['arms_insufficient']}")
    print(f"  total_closed_round_trips={roll['total_closed_round_trips']}  "
          f"total_real_pnl={_fmt_money(roll['total_real_pnl'])}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Per-arm live-readiness scorer against CLAUDE.md's 4-condition gate. "
                    "Reporting instrument only -- arms nothing, changes no gate, edits no "
                    "params*.json, places no orders.")
    parser.add_argument("--json", action="store_true",
                         help="print the machine JSON payload instead of the human table")
    args = parser.parse_args(argv)
    report = build_report()
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_human_report(report)
    return 0


if __name__ == "__main__":
    sys.exit(main())

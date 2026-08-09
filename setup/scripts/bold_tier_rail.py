#!/usr/bin/env python
"""bold_tier_rail.py -- THE STANDING INSTRUMENT for BOLD-CORE-ATM-WIRE-FALSIFICATION-RAIL
(automation/overnight/queue.md, filed 2026-07-18, from the BOLD-CORE-ATM-WIRE ship).

THE GAP THIS CLOSES: commit 718e0809 (2026-07-18, "feat(bold-strike): wire core-Bold $0-2K
tier OTM-3 -> ATM") shipped core-Bold's strike tier on J's explicit authorization while
EXPLICITLY DISCLOSING it failed its own auto-ratify gate (wf_ge_070) -- "a PARTICIPATION fix,
not a proven P&L edge." The commit's own falsification rail, verbatim: "first n>=20 live Bold
fills under this tier get an expectancy check; negative result escalates to Fable judgment, not
a silent revert." A 2026-08-08 audit found that rail existed ONLY as prose -- a queue.md bullet
and a test-file docstring (backtest/tests/test_bold_core_strike_tier_2026_07_15.py). NOTHING
COMPUTED IT. Live status at audit time: n=6 post-ship fills, net -$476.00, WR 16.7% (vs +$406.00
/ WR 50% on the old OTM-3 tier's last 4 fills) -- see analysis/deep-research/lane1-loss-anatomy-
2026-08-08.json and analysis/recommendations/{prereg,profitability-ab}-2026-08-08.json. This
script is the fix: a deterministic, $0, pure-Python instrument that computes the rail every run,
so TRIGGERED_NEGATIVE can never rot unnoticed the way BOLD-CORE-ATM-WIRE-FALSIFICATION-RAIL did
for three weeks.

POPULATION (never re-derived -- reuses the repo's ONE definition of a position and its ONE
fills-loader, both from backtest/tools/exit_shape_parity_study.py, exactly as lane1-loss-
anatomy-2026-08-08.json's own `position_def` field cites):
  1. `exit_shape_parity_study.load_fleet_engine_fills(LEDGER, arms=("bold-2",))` -- real fills
     only, attribution=="engine", is_option, NOT is_crypto (excludes bold-2's manual crypto-gym
     legs, e.g. the AAVE/USD and UNI/USD rows sharing this arm's ledger rows).
  2. `exit_shape_parity_study.reconstruct_positions(fills)` -- groups raw buy/sell fills into
     logical round-trip positions (qty-weighted entry price, summed exit-leg pnl).
  3. Split on `date_et >= TIER_SHIP_DATE_ET` (2026-07-18, commit 718e0809's ship date) into
     post_ship (the falsification population) and pre_ship (the comparison cohort, i.e. the old
     OTM-3 tier's last trades on record in fills-ledger.jsonl).
This reproduces lane1's own numbers exactly (verified live, 2026-08-08): post_ship n=6,
net=-$476.00, WR 16.7%; pre_ship n=4, net=+$406.00, WR 50%. Pinned as a regression anchor in
backtest/tests/test_bold_tier_rail.py against the REAL ledger (same pattern
exit_shape_parity_study.py's own docstring cites for `test_control_anchor_reproduces_
established_baseline_live`) -- a change to this file that silently shifts those two numbers is
the exact "gate provenance drifted" failure class this instrument exists to prevent.

RAIL_STATUS (the falsification decision, computed fresh every run):
  NO_DATA            -- zero post-ship positions on record yet.
  ACCRUING           -- n < ESCALATION_N (20, the commit's own "n>=20" bar). Normal state today.
  TRIGGERED_NEGATIVE -- n >= 20 AND net_usd <= 0. THE escalation condition -- commit 718e0809's
                        own text: "negative result escalates to Fable judgment, not a silent
                        revert." See ESCALATION below.
  TRIGGERED_POSITIVE -- n >= 20 AND net_usd > 0. Closes the falsification question the other way
                        -- also worth a human look, but not an escalation (no money is bleeding).

HONEST CLOCK (2026-08-08 audit finding: ignoring bold-2's PDT-block window materially
understates how long n=20 takes). bold-2 runs under `pdt_gate_mode=margin_pdt` -- a SELF-
imposed legacy-PDT count the paper broker itself does not enforce (see
analysis/deep-research/PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md) -- which hard-blocks bold-2 on
known calendar dates. `BOLD_PDT_DARK_DATES` below is MANUALLY TRANSCRIBED from that memo (cross-
confirmed live via a 2026-08-08 self_check row already sitting in discord-outbox.jsonl: "PDT-
BLOCKED[bold]: 3/3 day-trades used ... rolls off 2026-08-12") because a live `pdt_tracker` query
needs a broker credential round-trip this offline, dependency-light instrument deliberately does
not make (same design choice gate_recency_report.py documents for its own provenance fallback).
The method is disclosed in every report's `eta.method` field, never silently assumed. If J moves
the PDT decision (analysis/deep-research/PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md section 6),
extend/replace `BOLD_PDT_DARK_DATES` by hand -- this script has no live broker call to re-derive
it automatically yet.

ESCALATION (the point of the instrument): the FIRST run where rail_status flips to
TRIGGERED_NEGATIVE appends one first-person row to automation/state/discord-outbox.jsonl using
the EXACT {content, source, queued_at} schema setup/scripts/gamma_standup.py's
`build_outbox_row` writes (copied, not reinvented) naming the finding and the one-line revert.
Posts EXACTLY ONCE per status transition INTO TRIGGERED_NEGATIVE -- never once per run. Dedup
needs no separate state file: this script reads its OWN previous automation/state/bold-tier-
rail.json output (escalation.last_escalated_status) before overwriting it, the same "read what
you wrote last time" pattern catastrophe_cap_shadow_ledger.py's `_flag_ready_transition` uses
against a dedicated ready-state file, folded here into the one output file this instrument is
allowed to own.

FAIL-OPEN EVERYWHERE (rail-2, matches every other standing instrument in this family): a
missing/corrupt ledger, a missing previous report, or an outbox-append failure each degrade
independently -- `main()` never raises, always exits 0. A fetch/parse failure can only under-
report the rail (silently stay ACCRUING/NO_DATA), never fabricate a false TRIGGERED_NEGATIVE.

Output: automation/state/bold-tier-rail.json (overwritten every run; schema below run()).

Run:
  backtest/.venv/Scripts/python.exe setup/scripts/bold_tier_rail.py [--dry-run]
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, copied verbatim from
# catastrophe_cap_shadow_ledger.py / gate_recency_report.py). When launched via pythonw.exe (no
# console), Windows 11's default-terminal setting can allocate a visible window on the FIRST
# stdout/stderr write. Redirect to log files BEFORE any other import gets a chance to write.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "bold-tier-rail.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "bold-tier-rail.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import argparse
import json
import math
import statistics
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest" / "tools", REPO / "setup" / "scripts",
           REPO / "automation" / "state" / "fleet"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from et_clock import et_now  # noqa: E402

STATE = REPO / "automation" / "state"
LEDGER = STATE / "fills-ledger.jsonl"
OUT_JSON = STATE / "bold-tier-rail.json"
OUTBOX_PATH = STATE / "discord-outbox.jsonl"

ARM = "bold-2"

# commit 718e0809 (2026-07-18 08:53:15 -0600): "feat(bold-strike): wire core-Bold $0-2K tier
# OTM-3 -> ATM (V15_BOLD_CORE_TIERS)" -- the falsification rail's own population start date.
TIER_SHIP_DATE_ET = "2026-07-18"
TIER_SHIP_COMMIT = "718e0809"

# commit 718e0809's own text: "first n>=20 live Bold fills under this tier get an expectancy
# check; negative result escalates to Fable judgment, not a silent revert."
ESCALATION_N = 20

# The one-line revert commit 718e0809 documents (both call sites, verified live 2026-08-08):
REVERT_LOCATIONS = (
    "setup/scripts/heartbeat_core.py:1975",
    "setup/scripts/j_intent_executor.py:311",
)
REVERT_INSTRUCTION = (
    f"repoint the bold branch in {REVERT_LOCATIONS[0]} and {REVERT_LOCATIONS[1]} from "
    f"ss.V15_BOLD_CORE_TIERS back to ss.V15_BOLD_TIERS"
)

# Known PDT-blocked calendar dates for bold-2 (params.pdt_gate_mode=="margin_pdt": a real
# pdt_tracker count >=3 in the trailing 5 business days blocks a 4th day-trade -- a SELF-imposed
# rule the paper broker itself does not enforce, per PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md).
# MANUALLY TRANSCRIBED (method disclosed, not hidden): pdt_tracker.fetch_day_trades_detail needs
# a live broker credential round-trip this offline/deterministic instrument deliberately does
# not make (same provenance-fallback design gate_recency_report.py uses for gates outside its
# registry's scope). Source: analysis/deep-research/PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md
# section 3 ("Blocked Wed 08-05 + Thu 08-06 ... stays blocked Fri + Mon + Tue ... unblocks
# 2026-08-12") + section 5, cross-confirmed live via the 2026-08-08 20:39 ET self_check row
# already sitting in discord-outbox.jsonl ("PDT-BLOCKED[bold]: 3/3 day-trades used (rolling 5bd)
# ... blocks a 4th day-trade until it rolls off 2026-08-12"). If J resolves the open PDT memo
# (section 6 of that doc) before this script gains a live pdt_tracker call, extend/replace this
# set by hand.
BOLD_PDT_DARK_DATES: frozenset = frozenset({
    "2026-08-05", "2026-08-06", "2026-08-07", "2026-08-10", "2026-08-11",
})
PDT_DARK_METHOD = (
    "manually transcribed from analysis/deep-research/PDT-ACCOUNT-TYPE-DECISION-2026-08-06.md "
    "section 3/5, cross-confirmed live via a 2026-08-08 self_check discord-outbox row -- NOT a "
    "live pdt_tracker query (that needs a broker credential round-trip this offline instrument "
    "does not make); extend BOLD_PDT_DARK_DATES by hand if the PDT decision memo's section 6 "
    "is resolved differently"
)


# ─────────────────────────────────────────────────────────────────────────────────────
# PURE layer -- no I/O, fully unit-testable.
# ─────────────────────────────────────────────────────────────────────────────────────

def split_cohorts(positions: list, ship_date: str = TIER_SHIP_DATE_ET) -> tuple:
    """PURE. (post_ship, pre_ship) -- positions partitioned on date_et >= ship_date. The
    falsification population is post_ship; pre_ship is the disclosed comparison cohort (the old
    OTM-3 tier's own last trades on record)."""
    post = [p for p in positions if p.get("date_et", "") >= ship_date]
    pre = [p for p in positions if p.get("date_et", "") < ship_date]
    return post, pre


def cohort_stats(positions: list) -> dict:
    """PURE. n / net / win_rate / mean / median / avg_notional for one cohort. Empty-safe --
    never divides by zero. avg_notional_usd = mean(entry_price * entry_qty * 100), i.e. the
    real dollar premium paid to open each position (options multiplier=100, matches every fill
    row in fills-ledger.jsonl)."""
    n = len(positions)
    if n == 0:
        return {"n": 0, "net_usd": 0.0, "win_rate": None, "mean_usd": None,
                "median_usd": None, "avg_notional_usd": None}
    pnls = [float(p["actual_exit_pnl"]) for p in positions]
    notionals = [float(p["entry_price"]) * float(p["entry_qty"]) * 100.0 for p in positions]
    net = round(sum(pnls), 2)
    wins = sum(1 for x in pnls if x > 0)
    return {
        "n": n,
        "net_usd": net,
        "win_rate": round(wins / n, 4),
        "mean_usd": round(net / n, 2),
        "median_usd": round(statistics.median(pnls), 2),
        "avg_notional_usd": round(sum(notionals) / n, 2),
    }


def regime_delta(post: dict, pre: dict) -> dict:
    """PURE. The delta between the ATM-tier regime (post) and the OTM-3 regime (pre). None-safe
    when either cohort is empty -- never fabricates a delta from a missing side."""
    if post["n"] == 0 or pre["n"] == 0:
        return {"net_usd_delta": None, "mean_usd_delta": None, "win_rate_delta": None,
                "avg_notional_multiplier": None}
    return {
        "net_usd_delta": round(post["net_usd"] - pre["net_usd"], 2),
        "mean_usd_delta": round(post["mean_usd"] - pre["mean_usd"], 2),
        "win_rate_delta": round(post["win_rate"] - pre["win_rate"], 4),
        "avg_notional_multiplier": (round(post["avg_notional_usd"] / pre["avg_notional_usd"], 4)
                                     if pre["avg_notional_usd"] else None),
    }


def rail_status(n: int, net_usd: float, escalation_n: int = ESCALATION_N) -> str:
    """PURE. One of NO_DATA / ACCRUING / TRIGGERED_NEGATIVE / TRIGGERED_POSITIVE -- the
    falsification decision commit 718e0809's own rail promised."""
    if n == 0:
        return "NO_DATA"
    if n < escalation_n:
        return "ACCRUING"
    return "TRIGGERED_NEGATIVE" if net_usd <= 0 else "TRIGGERED_POSITIVE"


def verdict_line(post: dict, pre: dict, status: str, escalation_n: int = ESCALATION_N) -> str:
    """PURE. One-line plain-English standup verdict, e.g.:
    'Bold ATM tier: 6 of 20 fills, -$476 so far (old tier was +$406 on 4) -- rail not yet
    triggered.'"""
    n = post["n"]
    net = post["net_usd"] or 0.0
    net_s = f"-${abs(net):,.0f}" if net < 0 else f"+${net:,.0f}"
    if pre["n"]:
        pre_net = pre["net_usd"] or 0.0
        pre_s = f"old tier was {'+' if pre_net >= 0 else '-'}${abs(pre_net):,.0f} on {pre['n']}"
    else:
        pre_s = "no pre-ship trades on record"
    triggered = status.startswith("TRIGGERED")
    tail = "rail TRIGGERED" if triggered else "rail not yet triggered"
    return f"Bold ATM tier: {n} of {escalation_n} fills, {net_s} so far ({pre_s}) -- {tail}."


def trading_days_between(start: date, end: date, dark_dates: frozenset) -> list:
    """PURE. Weekdays in the half-open range [start, end) excluding dark_dates. `end` (today)
    is deliberately excluded -- today's session may not be fully closed out yet, so counting it
    as "elapsed" would overstate the observed rate."""
    out: list = []
    d = start
    while d < end:
        if d.weekday() < 5 and d.isoformat() not in dark_dates:
            out.append(d)
        d += timedelta(days=1)
    return out


def project_forward_trading_days(start: date, n_trading_days: int, dark_dates: frozenset) -> date:
    """PURE. The calendar date reached after n_trading_days qualifying (weekday, non-dark) days
    STRICTLY AFTER start. n_trading_days==0 returns start unchanged."""
    d = start
    counted = 0
    while counted < n_trading_days:
        d += timedelta(days=1)
        if d.weekday() < 5 and d.isoformat() not in dark_dates:
            counted += 1
    return d


def compute_eta(n_post_ship: int, ship_date: date, today: date,
                 dark_dates: frozenset = BOLD_PDT_DARK_DATES,
                 escalation_n: int = ESCALATION_N) -> dict:
    """PURE. Honest-clock ETA to n>=escalation_n, excluding known PDT-dark trading days on both
    the observed-rate side (elapsed_trading_days_ex_dark) and the projection side. Never guesses
    an ETA when the observed rate is undefined (zero elapsed trading days or zero fills so far)
    -- returns method-disclosed None fields instead, per OP-33 (never imply a number it doesn't
    have)."""
    elapsed_days = trading_days_between(ship_date, today, dark_dates)
    elapsed_n = len(elapsed_days)
    remaining = max(0, escalation_n - n_post_ship)

    if remaining == 0:
        return {
            "elapsed_trading_days_ex_dark": elapsed_n,
            "observed_fills_per_trading_day": (round(n_post_ship / elapsed_n, 4)
                                                if elapsed_n else None),
            "remaining_fills_needed": 0,
            "projected_trading_days_needed": 0,
            "expected_trigger_eta_et": today.isoformat(),
            "method": "power floor already met -- no projection needed",
        }

    if elapsed_n == 0 or n_post_ship == 0:
        return {
            "elapsed_trading_days_ex_dark": elapsed_n,
            "observed_fills_per_trading_day": None,
            "remaining_fills_needed": remaining,
            "projected_trading_days_needed": None,
            "expected_trigger_eta_et": None,
            "method": ("no post-ship fills observed yet over the elapsed window -- rate "
                       "undefined, no ETA projectable (never guessed)"),
        }

    rate = n_post_ship / elapsed_n
    needed_days = math.ceil(remaining / rate)
    eta = project_forward_trading_days(today, needed_days, dark_dates)
    return {
        "elapsed_trading_days_ex_dark": elapsed_n,
        "observed_fills_per_trading_day": round(rate, 4),
        "remaining_fills_needed": remaining,
        "projected_trading_days_needed": needed_days,
        "expected_trigger_eta_et": eta.isoformat(),
        "method": (f"observed {n_post_ship} fill(s) over {elapsed_n} trading day(s) since "
                   f"{ship_date.isoformat()} (weekdays, excluding {len(dark_dates)} known "
                   f"PDT-dark date(s) -- {PDT_DARK_METHOD}) -> rate {round(rate, 4)}/day, "
                   f"{needed_days} more trading day(s) needed for {remaining} more fill(s), "
                   f"projected forward the same way (weekdays, dark dates excluded)"),
    }


def build_escalation_message(post: dict, pre: dict) -> str:
    """PURE. First-person finding + the one-line revert, per commit 718e0809's own rail text
    ("negative result escalates to Fable judgment, not a silent revert")."""
    net = post["net_usd"] or 0.0
    net_s = f"-${abs(net):,.0f}" if net < 0 else f"+${net:,.0f}"
    wr_pct = round((post["win_rate"] or 0.0) * 100)
    if pre["n"]:
        pre_net = pre["net_usd"] or 0.0
        pre_s = f"{'+' if pre_net >= 0 else '-'}${abs(pre_net):,.0f} on {pre['n']}"
    else:
        pre_s = "no pre-ship trades on record"
    return (
        f"I'm escalating BOLD-CORE-ATM-WIRE-FALSIFICATION-RAIL (commit {TIER_SHIP_COMMIT}, "
        f"{TIER_SHIP_DATE_ET}): bold-2's ATM strike tier has hit its own n>={ESCALATION_N} "
        f"falsification check -- {post['n']} fills, {net_s} net (WR {wr_pct}%), vs the old "
        f"OTM-3 tier's {pre_s}. Per the ship commit's own rail this is NOT a silent revert -- "
        f"it escalates to Fable judgment (/think-like-fable). The one-line revert is ready any "
        f"time: {REVERT_INSTRUCTION}."
    )


def build_report(positions: list, today: date, *,
                  ship_date_et: str = TIER_SHIP_DATE_ET,
                  escalation_n: int = ESCALATION_N,
                  dark_dates: frozenset = BOLD_PDT_DARK_DATES,
                  prior_escalation: Optional[dict] = None,
                  generated_at_et: Optional[str] = None) -> dict:
    """PURE. Assembles the full report dict (everything run() writes to bold-tier-rail.json)
    from already-loaded positions + injected clock/state -- the seam unit tests call directly."""
    post_positions, pre_positions = split_cohorts(positions, ship_date_et)
    post = cohort_stats(post_positions)
    pre = cohort_stats(pre_positions)
    delta = regime_delta(post, pre)
    status = rail_status(post["n"], post["net_usd"] or 0.0, escalation_n)
    ship_date = date.fromisoformat(ship_date_et)
    eta = compute_eta(post["n"], ship_date, today, dark_dates, escalation_n)

    prior_escalation = prior_escalation or {}
    prior_status = prior_escalation.get("last_escalated_status")
    escalate_now = status == "TRIGGERED_NEGATIVE" and prior_status != "TRIGGERED_NEGATIVE"

    if escalate_now:
        finding = build_escalation_message(post, pre)
        posted_at = generated_at_et
    elif status == "TRIGGERED_NEGATIVE":
        # Already escalated on a prior run -- carry the record forward, never repost.
        finding = prior_escalation.get("finding")
        posted_at = prior_escalation.get("posted_at_et")
    else:
        finding = None
        posted_at = None

    return {
        "_doc": ("Standing falsification-rail instrument for commit 718e0809's BOLD-CORE-ATM-"
                 "WIRE ship. See module docstring for full provenance."),
        "generated_at_et": generated_at_et,
        "ship_date_et": ship_date_et,
        "ship_commit": TIER_SHIP_COMMIT,
        "escalation_n": escalation_n,
        "days_since_ship": (today - ship_date).days,
        "population": {
            "source": "automation/state/fills-ledger.jsonl",
            "arm": ARM,
            "filter": "attribution==engine, is_option, not is_crypto",
            "position_def": "exit_shape_parity_study.reconstruct_positions",
        },
        "post_ship": post,
        "pre_ship": pre,
        "delta": delta,
        "rail_status": status,
        "verdict": verdict_line(post, pre, status, escalation_n),
        "eta": eta,
        "escalation": {
            "posted_this_run": escalate_now,
            "last_escalated_status": status,
            "finding": finding,
            "posted_at_et": posted_at,
            "revert_instruction": REVERT_INSTRUCTION,
        },
        "warnings": [
            "avg_notional_usd = mean(entry_price * entry_qty * 100), the real dollar premium "
            "paid per position -- a different definition than any per-trade notional figure "
            "quoted in prereg-profitability-2026-08-08.json (that document's own $ figures use "
            "a different basis; only its 3.45x notional-shift RATIO was independently cross-"
            "checked against this cohort split and matches).",
            "PDT dark dates are hand-transcribed, not live-queried -- see eta.method.",
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────────────
# I/O layer
# ─────────────────────────────────────────────────────────────────────────────────────

def load_bold_positions(ledger_path: Path = LEDGER) -> list:
    """I/O: real bold-2 fills -> reconstructed positions, via the repo's ONE position
    definition (exit_shape_parity_study). Fail-open -> [] on any loader/import failure -- never
    fabricates a false NO_DATA vs a real outage; both read the same way to the caller by design
    (rail-2: a failed fetch can only under-report, never invent a trigger)."""
    import exit_shape_parity_study as esp
    fills = esp.load_fleet_engine_fills(ledger_path, arms=(ARM,))
    return esp.reconstruct_positions(fills)


def _load_previous_report(path: Path = OUT_JSON) -> Optional[dict]:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
        return doc if isinstance(doc, dict) else None
    except (OSError, ValueError):
        return None


def _post_escalation(content: str, queued_at: str, outbox_path: Path = OUTBOX_PATH) -> dict:
    """I/O: append ONE row using gamma_standup.py's exact outbox schema
    ({"content", "source", "queued_at"}), copied verbatim, not reinvented."""
    row = {"content": content, "source": "bold_tier_rail", "queued_at": queued_at}
    outbox_path.parent.mkdir(parents=True, exist_ok=True)
    with outbox_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def run(ledger_path: Path = LEDGER, out_path: Path = OUT_JSON,
        outbox_path: Path = OUTBOX_PATH, *, dry_run: bool = False) -> dict:
    now = et_now()
    today = now.date()
    generated_at_et = now.isoformat(timespec="seconds")

    try:
        positions = load_bold_positions(ledger_path)
    except Exception as e:  # noqa: BLE001 -- fail-open: a loader crash reads as NO_DATA
        print(f"[bold-tier-rail] loader error (fail-open to empty population): "
              f"{type(e).__name__}: {e}", file=sys.stderr)
        positions = []

    previous = _load_previous_report(out_path)
    prior_escalation = (previous or {}).get("escalation")

    report = build_report(positions, today, prior_escalation=prior_escalation,
                          generated_at_et=generated_at_et)

    if report["escalation"]["posted_this_run"] and not dry_run:
        try:
            _post_escalation(report["escalation"]["finding"], generated_at_et, outbox_path)
        except OSError as e:
            print(f"[bold-tier-rail] escalation outbox append FAILED (fail-open, will retry "
                  f"next run since last_escalated_status only updates below): "
                  f"{type(e).__name__}: {e}", file=sys.stderr)
            # If the append failed, don't claim it posted -- next run will retry (prior_status
            # will still read as whatever it was BEFORE this run, since we return early here
            # without ever having written out_path).
            report["escalation"]["posted_this_run"] = False
            report["escalation"]["finding"] = None
            report["escalation"]["posted_at_et"] = None
            report["escalation"]["last_escalated_status"] = (
                (prior_escalation or {}).get("last_escalated_status")
            )

    if not dry_run:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = out_path.with_suffix(out_path.suffix + ".tmp")
        tmp.write_text(json.dumps(report, indent=2), encoding="utf-8")
        tmp.replace(out_path)

    return report


def main(argv: Optional[list] = None) -> int:
    ap = argparse.ArgumentParser(
        description="BOLD-CORE-ATM-WIRE-FALSIFICATION-RAIL standing instrument (commit "
                     "718e0809's promised n>=20 expectancy check, wired for real)."
    )
    ap.add_argument("--dry-run", action="store_true",
                     help="print only -- no file write, no escalation post")
    args = ap.parse_args(argv)

    try:
        report = run(dry_run=args.dry_run)
    except Exception as e:  # noqa: BLE001 -- standing instrument: never propagate, always exit 0
        print(f"[bold-tier-rail] ERROR (fail-open): {type(e).__name__}: {e}", file=sys.stderr)
        return 0

    print(f"[bold-tier-rail] {report['verdict']}")
    print(f"[bold-tier-rail] rail_status={report['rail_status']} "
          f"post_ship_n={report['post_ship']['n']} eta={report['eta'].get('expected_trigger_eta_et')}")
    if report["escalation"]["posted_this_run"]:
        print(f"[bold-tier-rail] ESCALATION POSTED: {report['escalation']['finding']}")
    if args.dry_run:
        print("\n[bold-tier-rail] --dry-run: no file written\n")
        print(json.dumps(report, indent=2))
    else:
        print(f"\n[bold-tier-rail] wrote {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

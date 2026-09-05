"""intervention_counter.py -- TASK B2 instrument 1/3 (built 2026-08-28).

WHY THIS EXISTS: the 2026-08-27 go-live readiness audit named the largest
UNMODELLED risk as J himself -- his own 667-trade manual record (WR 46.9%,
PF 0.75, net -$12,885, a documented habit of cutting winners early) -- while
this engine's entire realized edge is a right tail (money only from exits
>=1.3x entry premium; setup/scripts/winner_signature.py / SIGNATURE.md). If J
starts manually touching the SAME paper arms the engine trades, that exact
risk imports itself into the go-live evidence with zero visibility unless
something counts it. This counts it.

SOURCE OF TRUTH: automation/state/fills-ledger.jsonl (broker-truth fills,
HANDOFF-2026-07-09-TRUTH-AND-EXITS ground rule 2 -- decision ledgers are
DECISIONS-only, fills/P&L must always be read from the broker-fills ledger).
READ-ONLY: this script never writes to fills-ledger.jsonl, pnl-statement.json,
or any live-trading-path file. Its own outputs live under analysis/interventions/
and (loudly, only on a new SPY-option intervention) automation/overnight/STATUS.md.

ATTRIBUTION GROUND TRUTH (setup/scripts/broker_fills.py, reused not
reimplemented -- fifo_round_trips is a PURE function, imported directly):
  - FLEET_REST arms (safe-3, risky-1, risky-3): "engine" unless the fill is
    crypto (crypto fills are ALWAYS "manual" by broker_fills.py's own rule --
    project scope is crypto=gym-only, never traded live, see CLAUDE.md
    "What I will refuse"). Verified this session: every non-engine fill on
    these 3 arms to date (58 of 58) is crypto (ETH/UNI/BTC/LTC/BCH), i.e.
    zero real SPY-option interventions on the fleet_rest arms in history.
  - CORE arms (safe-2, bold-2): "engine" only if the fill's order_id matches
    a PLACED entry / exit_pass / extra_exec order id in core-decisions.jsonl
    for that account; else "manual". This tag SELF-HEALS promote-only on
    every broker_fills.py run (a later-discovered engine order retroactively
    flips a stale "manual" tag to "engine"; engine is never demoted). A row
    still "manual" as of the CURRENT ledger has survived every self-heal pass
    to date -- the best available proxy for "not engine-placed", but it
    cannot fully rule out an order whose core-decisions.jsonl row was lost
    or rotated (disclosed in the summary's `caveat` field, not hidden).
  - CRYPTO fills (symbol contains "/") are reported SEPARATELY and NEVER
    counted in the SPY-0DTE intervention headline number.

CLASSIFICATION (per FIFO round trip): a round trip's own `attribution` tag
(broker_fills.py semantics) is the CLOSING fill's tag. This script additionally
looks up the OPENING fill's own attribution (fills-ledger row keyed by
entry_activity_id) to split every non-fully-engine SPY-option round trip into:
  - manual_both              : J placed AND closed the trade himself.
  - engine_entered_manual_exit: the engine opened it, J closed it early/late
                                -- the specific "cuts winners" risk pattern
                                the audit named, tracked as its OWN count.
  - manual_entered_engine_exit: J opened it, the engine's own exit logic
                                closed it (anomalous / unexpected -- flagged).
  - rescue_exit               : the engine opened it (same shape as
                                engine_entered_manual_exit) BUT the manual exit landed
                                within engine_gaps.RESCUE_WINDOW_MIN minutes after the
                                END of a detected engine_gaps tick-gap on that account/
                                day (added 2026-09-05, 2026-09-04 blackout post-mortem:
                                the box lost power 09:51-10:46 ET while safe-2/bold-2
                                held open positions; J closed both from the Alpaca
                                dashboard at 10:46 during the blackout -- a RESCUE, not
                                J second-guessing a live engine). Reclassified OUT of
                                engine_entered_manual_exit and OUT of is_intervention;
                                tracked separately (`rescues` in the summary) so it never
                                counts against the Sept ZERO-intervention target while
                                staying fully visible.

P&L: reports the ACTUAL realized P&L of intervention round trips (knowable,
straight from the ledger's own FIFO pnl field). Does NOT fabricate a
counterfactual "what would the engine have done" P&L -- that is not
reconstructable from fills alone (no guarantee the engine's own in-flight
decision on that exact leg was even ENTER at that moment). Per C7 / no
fabricated data: reported as `counterfactual_pnl: null, counterfactual_note:
"not reconstructable from fills alone -- UNVERIFIED, not fabricated"`.

TARGET: J's directive is ZERO new SPY-option interventions from 2026-09-01
forward. `since_target_start` in the summary tracks that forward window
starting empty; `all_time` gives full backfilled history for context.

Run:  backtest/.venv/Scripts/python.exe setup/scripts/intervention_counter.py [--quiet]
      (plain `python` also works -- stdlib only, no pandas/venv deps, no network)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
STATE = REPO / "automation" / "state"
FILLS_PATH = STATE / "fills-ledger.jsonl"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
OUT_DIR = REPO / "analysis" / "interventions"
OUT_PATH = OUT_DIR / "summary.json"

TARGET_START_DATE = "2026-09-01"  # J directive: Sept target = ZERO new interventions
KNOWN_BROKEN_MARKER = "## Known broken"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import broker_fills as bf  # noqa: E402 -- reused, PURE fifo_round_trips only, no network
import engine_gaps as eg  # noqa: E402 -- shared RTH-gap detector, see rescue_exit below
from et_clock import et_now  # noqa: E402

# fills-ledger tags positions by fleet arm name; engine_gaps/core-decisions.jsonl use the
# bare account label (CLAUDE.md Account context table) -- inverse of engine_gaps.ACCOUNT_TO_ARM.
ARM_TO_ACCOUNT = {v: k for k, v in eg.ACCOUNT_TO_ARM.items()}


def load_fills(path: Path = FILLS_PATH) -> list:
    fills = []
    if not path.exists():
        return fills
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                fills.append(json.loads(line))
            except ValueError:
                continue
    return fills


def _is_rescue(rt: dict) -> bool:
    """True if this round trip's exit lands within engine_gaps.RESCUE_WINDOW_MIN minutes
    after the END of a detected engine_gaps tick-gap for this account/day -- i.e. the
    manual exit is presumptively a rescue during an engine blackout, not a second-guess
    of a healthy engine. Fail-open: False on any unmapped arm / unparseable timestamp /
    detector error -- a broken rescue-detector must never silently shrink the
    intervention count."""
    account = ARM_TO_ACCOUNT.get(rt.get("arm"))
    if account is None:
        return False
    exit_dt = eg._parse_naive(rt.get("exit_ts_et"))
    day = rt.get("date_et")
    if exit_dt is None or not day:
        return False
    try:
        return eg.is_rescue_exit(account, exit_dt, day)
    except Exception:  # noqa: BLE001 -- fail-open, never inflate/deflate silently
        return False


def classify_round_trips(fills: list) -> list:
    """PURE: fills -> list of classified round-trip dicts.

    Reuses bf.fifo_round_trips for the FIFO pairing (proven machinery), then
    cross-references each round trip's ENTRY fill (by entry_activity_id) to
    recover the opening side's own attribution -- fifo_round_trips only
    stores the CLOSING fill's tag on the row itself."""
    by_activity_id = {f.get("activity_id"): f for f in fills if f.get("activity_id")}
    round_trips, _open_lots = bf.fifo_round_trips(fills)

    out = []
    for rt in round_trips:
        entry_fill = by_activity_id.get(rt["entry_activity_id"], {})
        exit_fill = by_activity_id.get(rt["exit_activity_id"], {})
        is_crypto = bool(entry_fill.get("is_crypto") or exit_fill.get("is_crypto"))
        entry_attr = entry_fill.get("attribution", "unknown")
        exit_attr = rt["attribution"]  # == exit_fill's attribution, per broker_fills semantics

        if is_crypto:
            category = "crypto_excluded"
        elif entry_attr == "engine" and exit_attr == "engine":
            category = "fully_engine"
        elif entry_attr != "engine" and exit_attr != "engine":
            category = "manual_both"
        elif entry_attr == "engine" and exit_attr != "engine":
            category = "engine_entered_manual_exit"
        else:  # entry_attr != "engine" and exit_attr == "engine"
            category = "manual_entered_engine_exit"

        is_rescue = False
        if category == "engine_entered_manual_exit" and not is_crypto:
            is_rescue = _is_rescue(rt)
            if is_rescue:
                category = "rescue_exit"

        out.append({
            **rt,
            "is_crypto": is_crypto,
            "entry_attribution": entry_attr,
            "exit_attribution": exit_attr,
            "category": category,
            "is_rescue": is_rescue,
            "is_intervention": category not in ("fully_engine", "crypto_excluded", "rescue_exit"),
        })
    return out


INTERVENTION_CATEGORIES = (
    "manual_both", "engine_entered_manual_exit", "manual_entered_engine_exit")


def summarize(classified: list, now_et=None) -> dict:
    """PURE: classified round trips -> the full summary dict written to disk."""
    now_et = now_et or et_now()
    today = now_et.strftime("%Y-%m-%d")

    interventions = [r for r in classified if r["is_intervention"]]
    crypto_excluded = [r for r in classified if r["category"] == "crypto_excluded"]
    fully_engine = [r for r in classified if r["category"] == "fully_engine"]
    rescues = [r for r in classified if r["category"] == "rescue_exit"]
    since_target = [r for r in interventions if r["date_et"] >= TARGET_START_DATE]
    today_interventions = [r for r in interventions if r["date_et"] == today]
    today_rescues = [r for r in rescues if r["date_et"] == today]

    def _bucket(rows: list) -> dict:
        by_cat: dict = {}
        by_arm: dict = {}
        pnl_total = 0.0
        for r in rows:
            by_cat[r["category"]] = by_cat.get(r["category"], 0) + 1
            by_arm[r["arm"]] = by_arm.get(r["arm"], 0) + 1
            pnl_total += r["pnl"]
        return {
            "n_round_trips": len(rows),
            "by_category": by_cat,
            "by_arm": by_arm,
            "realized_pnl": round(pnl_total, 2),
        }

    events = sorted(
        ({"date_et": r["date_et"], "arm": r["arm"], "symbol": r["symbol"],
          "category": r["category"], "qty": r["qty"], "pnl": r["pnl"],
          "entry_ts_et": r["entry_ts_et"], "exit_ts_et": r["exit_ts_et"],
          "entry_attribution": r["entry_attribution"], "exit_attribution": r["exit_attribution"]}
         for r in interventions),
        key=lambda e: e["exit_ts_et"])

    return {
        "generated_at_et": now_et.isoformat(),
        "date_et": today,
        "target_start_date": TARGET_START_DATE,
        "target": "ZERO new SPY-0DTE interventions from target_start_date forward (J directive)",
        "all_time": _bucket(interventions),
        "since_target_start": _bucket(since_target),
        "today": _bucket(today_interventions),
        "fully_engine_round_trips": len(fully_engine),
        "crypto_excluded": _bucket(crypto_excluded),
        "rescues": _bucket(rescues),
        "rescues_today": _bucket(today_rescues),
        "rescue_note": ("a manual exit within engine_gaps.RESCUE_WINDOW_MIN "
                         f"({eg.RESCUE_WINDOW_MIN:.0f}m) of the END of a detected "
                         "core-decisions.jsonl tick-gap on that account/day -- NOT counted "
                         "against the Sept ZERO-intervention target (2026-09-05, "
                         "2026-09-04 blackout post-mortem)."),
        "events": events,
        "counterfactual_pnl": None,
        "counterfactual_note": ("what the engine would have done on the SAME leg is NOT "
                                 "reconstructable from fills alone -- reported realized_pnl "
                                 "above is the ACTUAL P&L of the intervention trades "
                                 "themselves, never a fabricated counterfactual (C7)."),
        "caveat": ("'manual' on safe-2/bold-2 means: the fill's order_id has never matched a "
                   "known engine placement in core-decisions.jsonl, across every promote-only "
                   "self-heal pass to date. This is the best available proxy for a human-"
                   "placed order but cannot fully rule out an engine order whose "
                   "core-decisions.jsonl row was lost or rotated."),
    }


def one_liner(summary: dict) -> str:
    at = summary["all_time"]
    st = summary["since_target_start"]
    td = summary["today"]
    rescues_today = summary.get("rescues_today", {}).get("n_round_trips", 0)
    flag = " <== NEW TODAY" if td["n_round_trips"] > 0 else ""
    rescue_note = f", rescues today={rescues_today}" if rescues_today else ""
    return (f"[intervention-counter] {summary['date_et']}: all-time={at['n_round_trips']} "
            f"SPY-0DTE intervention round trip(s) (${at['realized_pnl']}), "
            f"since {summary['target_start_date']} (Sept target=ZERO)="
            f"{st['n_round_trips']} (${st['realized_pnl']}), today={td['n_round_trips']}{flag}"
            f"{rescue_note}")


def _flag_status_md(summary: dict, status_md: Path = STATUS_MD) -> bool:
    """Loudly escalate to STATUS.md '## Known broken' ONLY when a NEW SPY-option
    intervention landed TODAY (create-if-missing pattern -- see
    catastrophe_cap_shadow_ledger.py / backtest/tests/test_status_known_broken_section_
    2026_08_20.py; position-based fixes do not hold, this recreates the section)."""
    today = summary["today"]
    if today["n_round_trips"] == 0:
        return False
    try:
        text = status_md.read_text(encoding="utf-8")
    except OSError:
        return False
    detail = ", ".join(f"{cat}={n}" for cat, n in today["by_category"].items())
    line = (f"- [{summary['generated_at_et']}] INTERVENTION-COUNTER: {today['n_round_trips']} "
            f"NEW SPY-0DTE intervention round trip(s) today ({detail}), realized "
            f"${today['realized_pnl']} -- Sept target is ZERO. "
            f"See analysis/interventions/summary.json.")
    # CANONICAL create-if-missing pattern (monday_verify.py::_flag_known_broken, proven by
    # backtest/tests/test_status_known_broken_section_2026_08_20.py): position cannot be
    # relied on -- the conductor PREPENDS new '## [' entries above the preamble, so the
    # marker heading rolls off into a monthly archive the same way it did in the June 2026
    # outage. If the heading is absent, PREPEND it to the top of the file before proceeding,
    # so the partition below always finds it. Never a bare append with no heading.
    if KNOWN_BROKEN_MARKER not in text:
        text = KNOWN_BROKEN_MARKER + "\n\n" + text
    head, _, tail = text.partition(KNOWN_BROKEN_MARKER + "\n")
    status_md.write_text(
        f"{head}{KNOWN_BROKEN_MARKER}\n\n{line}\n{tail.lstrip(chr(10))}", encoding="utf-8")
    return True


def run(fills_path: Path = FILLS_PATH, out_path: Path = OUT_PATH,
        status_md: Path = STATUS_MD, write: bool = True) -> dict:
    fills = load_fills(fills_path)
    classified = classify_round_trips(fills)
    summary = summarize(classified)
    if write:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")
        _flag_status_md(summary, status_md)
    return summary


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    try:
        summary = run()
    except Exception as e:  # noqa: BLE001 -- fail-open notify-only instrument, never propagate
        print(f"[intervention-counter] ERROR (fail-open): {type(e).__name__}: {e}",
              file=sys.stderr)
        return 0
    if not args.quiet:
        print(one_liner(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""futures_eod.py -- the futures session review. Closes the learn loop.

WHY (the other half of journaling). Recording trades is not reviewing them. The SPY side
has an EOD digest that grades the day against the rules and feeds the next research pass;
the futures lane had a journal and no reviewer, which is how a lane accumulates rows nobody
reads and drifts without anyone noticing.

WHAT IT GRADES, and why each one is here rather than "nice to have":

  TICK COVERAGE -- did the lane actually fire every tick it was scheduled to? This is the
    headline number, deliberately. Every other metric on this page is conditional on the
    engine having been awake, and a lane that quietly stops ticking produces a PERFECT
    -looking digest: zero trades, zero errors, zero rule breaks. "No trades today" and "the
    engine was dead today" must never render identically (C7 -- audit outputs, not exit
    codes; and the crypto twin's four dark days).

  FUNNEL -- signals seen -> qualified -> entered, with the RAIL that rejected each drop.
    A lane that sees 57 signals and takes 0 is either correctly disciplined or silently
    broken, and only the rejection breakdown distinguishes those.

  ROUND TRIPS -- closed trades from the ledger, filtered to ONE fill class. Never mixed.

  RULE ADHERENCE -- every entry is checked against the rails AFTER the fact, independently
    of the pre-trade gate. A gate that is bypassed or mis-wired shows up as a post-hoc
    violation, which a pre-trade-only check can never reveal.

  REFUSAL (added 2026-08-29) -- did a signal clear every rail and then have the BROKER
    itself refuse the placement? Distinct from "no signal" (nothing to act on) and from
    "rejected by a rail" (the pipeline correctly said no) -- a REFUSAL means the pipeline
    worked, the engine tried to act, and place_bracket() said no anyway. Most often a stuck
    resting order: this grading exists because of the 2026-08-14 pending_entry deadlock --
    15 sessions, 60 refusals, 0 fills, every single day of it reported GREEN because
    nothing before today graded refusals at all. Sitting out on a genuinely quiet day is
    NOT this -- that stays GREEN, per standing doctrine (a losing/quiet day is not itself
    a failure). See REFUSAL_RED_SESSIONS below for the exact grading rule.

DISCLOSURE: the digest states its fill class on every P&L line. Simulated fills are
mechanism evidence, never edge evidence.

Read-only over state and the journal, with ONE exception: `rule_audit()`'s findings are
persisted into `journal/futures/mistakes.md` via `futures_journal.record_mistake()` --
the futures analogue of Rule 8's mistakes ledger (queue item
FUTURES-MISTAKES-LEDGER-IS-DEAD-CODE; `record_mistake()` existed, was fully implemented,
and had zero call sites anywhere in the repo). Grouped by rule, keyed by (date, rule,
lane) so a re-run of the same session never duplicates a row (`_mistakes_already_logged`
dedupes off a marker this module writes into its own bullet text), and fail-open the
same way every write in futures_journal.py is -- a ledger write error is logged to
nothing and swallowed, never raised, because a mistakes ledger that can break the EOD
review is worse than a missing one.

Never places, cancels, or modifies anything else -- no orders, no position state.

CLI:
    python -m futures.futures_eod                 # today's session
    python -m futures.futures_eod --date 2026-08-07
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

from futures.futures_session import et_now, is_holiday  # noqa: E402
from futures import futures_journal as fj  # noqa: E402

STATE_DIR = REPO / "automation" / "state" / "futures" / "trader"
LEDGER = STATE_DIR / "decisions.jsonl"
# The broker's OWN event ledger -- the only place a placement refusal's REASON lives.
# decisions.jsonl's ENTER_REFUSED rows say a placement was refused, never WHY (the "why"
# is in fill_sim_broker.place_bracket()'s "placed_refused" event). Same directory as
# LEDGER: fill_sim_broker's default state_dir for this (fillsim/intraday) lane.
WOULD_BE_LEDGER = STATE_DIR / "would-be-trades.jsonl"
DIGEST_DIR = REPO / "analysis" / "futures-eod"
STATE_OUT = REPO / "automation" / "state" / "futures" / "eod-summary.json"

# Gamma_FuturesTrader fires every 5 min across the 6.5h RTH window.
TICK_INTERVAL_MIN = 5
EXPECTED_TICKS = int(6.5 * 60 / TICK_INTERVAL_MIN)   # 78
# Below this fraction of expected ticks the lane was not meaningfully awake.
COVERAGE_RED = 0.70
COVERAGE_YELLOW = 0.90

# Task 2 (2026-08-29 pending_entry deadlock) -- refusal grading thresholds.
#
# A single session with a REFUSED placement is surprising enough to flag (a signal
# cleared every rail and the broker still said no -- see the module docstring's REFUSAL
# bullet) but is not yet distinguishable from a one-off broker hiccup, so on its own it
# only degrades the verdict to YELLOW.
#
# The SAME refusal reason repeating on REFUSAL_RED_SESSIONS or more CONSECUTIVE sessions
# is not a hiccup -- a transient cause does not reproduce identically day after day -- so
# that degrades to RED. 3 was chosen as "one session could be noise, two could be a bad
# coincidence, three in a row is a pattern", and it is 1/5th of the 15 sessions the real
# deadlock ran silently before anyone graded it -- this threshold would have caught THAT
# failure five times faster than it was actually caught.
REFUSAL_RED_SESSIONS = 3
# How many calendar days build() will scan backward looking for that streak. Generous
# enough to bridge a weekend + a one-day holiday without truncating a real 3-session run.
REFUSAL_LOOKBACK_SESSIONS = 10


def _read_ledger(date: str) -> list[dict]:
    rows: list[dict] = []
    try:
        for line in LEDGER.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(r.get("ts_et", "")).startswith(date):
                rows.append(r)
    except OSError:
        pass
    return rows


def tick_coverage(rows: list[dict], date: str) -> dict:
    """Did the engine actually run? The metric every other metric depends on."""
    ticks = len(rows)
    pct = ticks / EXPECTED_TICKS if EXPECTED_TICKS else 0.0
    if is_holiday(dt.datetime.fromisoformat(date)):
        verdict, note = "HOLIDAY", "market holiday -- no ticks expected"
    elif dt.datetime.fromisoformat(date).weekday() > 4:
        verdict, note = "WEEKEND", "weekend -- no ticks expected"
    elif pct >= COVERAGE_YELLOW:
        verdict, note = "GREEN", "lane was awake"
    elif pct >= COVERAGE_RED:
        verdict, note = "YELLOW", "gaps in the tick record -- check the scheduler"
    elif ticks > 0:
        verdict, note = "RED", "lane was mostly dark; today's other numbers are not trustworthy"
    else:
        verdict, note = "DARK", "NO ticks at all -- the lane did not run; zero trades means nothing"
    return {"ticks": ticks, "expected": EXPECTED_TICKS, "pct": round(pct, 3),
            "verdict": verdict, "note": note}


def funnel(rows: list[dict]) -> dict:
    """signals seen -> qualified -> entered, plus WHY each drop happened."""
    seen = sum(int(r.get("n_signals") or 0) for r in rows)
    entries = [r for r in rows if r.get("action") == "ENTER"]
    rejections: Counter = Counter()
    for r in rows:
        for rej in r.get("rejected") or []:
            rejections[rej.get("rail", "?")] += 1
    actions = Counter(r.get("action", "?") for r in rows)
    feeds = Counter(r.get("freshness", "?") for r in rows)
    return {
        "signals_seen": seen,
        "entries": len(entries),
        "rejections_by_rail": dict(rejections),
        "actions": dict(actions),
        "feed_verdicts": dict(feeds),
        "exit_events": sum(len(r.get("exit_events") or []) for r in rows),
        "errors": [r.get("see_error") or r.get("exit_error")
                   for r in rows if r.get("see_error") or r.get("exit_error")],
    }


def _placed_refused_by_date() -> dict[str, Counter]:
    """One pass over would-be-trades.jsonl, bucketing 'placed_refused' events by date
    (from ts_et) into a reason Counter. Read once and reused for both today's reason
    breakdown and the backward consecutive-session scan in refusal_history() -- walking
    N days back must not mean N full re-reads of an append-only log that only grows.
    """
    out: dict[str, Counter] = {}
    try:
        for line in WOULD_BE_LEDGER.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("event") != "placed_refused":
                continue
            day = str(r.get("ts_et", ""))[:10]
            if not day:
                continue
            out.setdefault(day, Counter())[r.get("reason", "?")] += 1
    except OSError:
        pass
    return out


def refusal_history(date: str, by_date: Optional[dict] = None) -> dict:
    """Refusal reason breakdown for `date`, plus how many CONSECUTIVE sessions (walking
    backward from `date`) shared at least one of those reasons -- "the same refusal
    repeating" (Task 2 / REFUSAL_RED_SESSIONS). Weekends/holidays are skipped WITHOUT
    breaking the streak (the lane simply did not run those days -- a Friday-to-Monday
    refusal streak is still a streak); bounded by REFUSAL_LOOKBACK_SESSIONS calendar days
    so a bad/garbled date can never spin the scan forever.

    `by_date` is an injection point for tests (`_placed_refused_by_date()`'s real return
    shape, keyed by 'YYYY-MM-DD') so a guard never has to write a real would-be-trades.jsonl.
    """
    by_date = _placed_refused_by_date() if by_date is None else by_date
    today_reasons = by_date.get(date, Counter())
    if not today_reasons:
        return {"sessions": 0, "reasons": {}}

    run = 0
    cur = dt.datetime.fromisoformat(date)
    scanned = 0
    while scanned < REFUSAL_LOOKBACK_SESSIONS:
        if cur.weekday() <= 4 and not is_holiday(cur):
            day_reasons = by_date.get(cur.strftime("%Y-%m-%d"), Counter())
            if not (day_reasons.keys() & today_reasons.keys()):
                break
            run += 1
        cur -= dt.timedelta(days=1)
        scanned += 1
    return {"sessions": run, "reasons": dict(today_reasons)}


def round_trips(date: str, fills: str = "SIMULATED") -> dict:
    """Closed trades for the date, from ONE fill class only. Never mixed."""
    rows = [r for r in fj.read_trades(fills=fills) if r.get("date") == date]
    pnls = []
    for r in rows:
        try:
            pnls.append(float(r.get("dollar_pnl") or 0.0))
        except (TypeError, ValueError):
            continue
    wins = [p for p in pnls if p > 0]
    return {
        "fills": fills,
        "n": len(rows),
        "total_pnl": round(sum(pnls), 2),
        "win_rate": round(len(wins) / len(pnls), 3) if pnls else None,
        "best": round(max(pnls), 2) if pnls else None,
        "worst": round(min(pnls), 2) if pnls else None,
        "by_setup": dict(Counter(r.get("setup", "?") for r in rows)),
        "by_exit": dict(Counter(r.get("exit_reason", "?") for r in rows)),
        "rows": rows,
    }


def rule_audit(rows: list[dict], trades: dict) -> list[dict]:
    """Post-hoc rule check on every entry, INDEPENDENT of the pre-trade gate.

    Checking only at entry time cannot catch a gate that was bypassed or mis-wired --
    the same reason a winning trade that broke a rule still gets red-flagged on the SPY
    side. Process over P&L.
    """
    from futures.futures_risk_rails import FuturesRiskRails  # noqa: PLC0415

    rails = FuturesRiskRails()
    breaks: list[dict] = []
    for r in rows:
        if r.get("action") != "ENTER":
            continue
        e = r.get("entry") or {}
        qty = int(e.get("qty") or 0)
        risk = float(e.get("risk_usd") or 0.0)
        if qty > rails.max_contracts:
            breaks.append({"ts": r.get("ts_et"), "rule": "contract_cap",
                           "detail": f"qty {qty} > cap {rails.max_contracts}"})
        if risk > rails.per_trade_risk_cap:
            breaks.append({"ts": r.get("ts_et"), "rule": "per_trade_risk",
                           "detail": f"${risk:.2f} > cap ${rails.per_trade_risk_cap:.2f}"})
        if not e.get("stop"):
            breaks.append({"ts": r.get("ts_et"), "rule": "defined_stop",
                           "detail": "entry recorded with no stop -- Rule 3"})
        if r.get("freshness") != "GREEN":
            breaks.append({"ts": r.get("ts_et"), "rule": "data_freshness",
                           "detail": f"entered on a {r.get('freshness')} feed"})
    day_pnl = trades.get("total_pnl") or 0.0
    if -day_pnl >= rails.session_loss_cap:
        breaks.append({"ts": "session", "rule": "session_loss_cap",
                       "detail": f"session P&L ${day_pnl:.2f} reached the "
                                 f"${rails.session_loss_cap:.2f} cap"})
    return breaks


MISTAKES_LANE = "futures"


def _mistakes_already_logged(date: str, lane: str = MISTAKES_LANE) -> set[str]:
    """Which rule names are already persisted to mistakes.md for (date, lane).

    Dedupe works by scanning for a marker THIS module writes inline into the bullet
    text (`<!-- dedupe:{date}:{lane}:{rule} -->`) rather than a separate index file,
    so the ledger itself stays the single source of truth for what has been logged.
    Read-only; any parse/read failure returns an empty set -- fail open means "might
    write one duplicate row", never "crash the EOD build".
    """
    try:
        if not fj.MISTAKES_MD.exists():
            return set()
        text = fj.MISTAKES_MD.read_text(encoding="utf-8")
    except OSError:
        return set()
    prefix = f"<!-- dedupe:{date}:{lane}:"
    seen: set[str] = set()
    for line in text.splitlines():
        idx = line.find(prefix)
        if idx == -1:
            continue
        rest = line[idx + len(prefix):]
        end = rest.find(" -->")
        if end != -1:
            seen.add(rest[:end])
    return seen


def persist_mistakes(date: str, breaks: list[dict], lane: str = MISTAKES_LANE) -> int:
    """Wire rule_audit()'s post-hoc findings into the futures mistakes ledger.

    Same role as `journal/mistakes.md` on the SPY side (Rule 8): "if it's not in the
    journal, it didn't happen" applies to rule breaks too. Groups by rule so one
    session with 3 `contract_cap` breaks produces one row, not three -- the idempotency
    key is (date, rule, lane), so a same-day re-run of `build()` (a manual re-generate,
    a test, a retry) never appends a second row for a rule already logged that day.

    Returns the number of NEW rows written (0 on a clean day or a fully-deduped re-run).
    Fail-open: this can never raise into the EOD build.
    """
    if not breaks:
        return 0
    try:
        already = _mistakes_already_logged(date, lane)
        by_rule: dict[str, list[dict]] = {}
        for b in breaks:
            by_rule.setdefault(b.get("rule", "?"), []).append(b)
        written = 0
        for rule, items in by_rule.items():
            if rule in already:
                continue
            details = "; ".join(str(i.get("detail", "")) for i in items[:5])
            what = (f"{len(items)} `{rule}` break(s) on {date} (post-hoc rule_audit(), "
                    f"lane={lane}): {details} "
                    f"<!-- dedupe:{date}:{lane}:{rule} -->")
            fj.record_mistake(
                what=what, rule=rule,
                fix="reviewed by futures_eod.py -- see analysis/futures-eod digest")
            written += 1
        return written
    except Exception:  # noqa: BLE001 -- ledger write must never break the EOD path
        return 0


def build(date: Optional[str] = None, fills: str = "SIMULATED") -> dict:
    date = date or et_now().strftime("%Y-%m-%d")
    rows = _read_ledger(date)
    cov = tick_coverage(rows, date)
    fun = funnel(rows)
    trades = round_trips(date, fills)
    breaks = rule_audit(rows, trades)
    persist_mistakes(date, breaks)
    refusals = refusal_history(date)
    # "n" and "by_setup" come from decisions.jsonl (the engine's own record of having
    # tried and been refused) -- authoritative even if would-be-trades.jsonl is missing
    # or unreadable, which is why refusals["sessions"]/"reasons" (would-be-trades-sourced)
    # are read separately above rather than gating this count on that file's presence.
    refusals["n"] = fun["actions"].get("ENTER_REFUSED", 0)
    refusals["by_setup"] = dict(Counter(
        r.get("reason", "?") for r in rows if r.get("action") == "ENTER_REFUSED"))

    # The digest verdict leads with coverage on purpose: if the lane was dark, a clean
    # trade record is an artifact of silence, not evidence of discipline. A REFUSAL
    # streak grades ABOVE rule breaks -- it is evidence of a STRUCTURAL inability to
    # trade at all, worse than one day's rule violation. A single-session refusal ranks
    # below a rule break (still just a possible one-off) but above plain coverage YELLOW
    # (a refusal is a positive signal something is wrong; a coverage gap is merely
    # incomplete information). Sitting out on NO signal never reaches this branch at all
    # -- refusals["n"] is 0 whenever place_bracket() was never even called, which is the
    # entire point: silence is fine, being refused after clearing every rail is not.
    if cov["verdict"] in ("DARK", "RED"):
        verdict = "RED"
    elif refusals["sessions"] >= REFUSAL_RED_SESSIONS:
        verdict = "RED"
    elif breaks:
        verdict = "RULE_BREAK"
    elif refusals["n"] > 0:
        verdict = "YELLOW"
    elif cov["verdict"] == "YELLOW":
        verdict = "YELLOW"
    elif cov["verdict"] in ("WEEKEND", "HOLIDAY"):
        verdict = "NO_SESSION"
    else:
        verdict = "GREEN"

    return {"date": date, "generated_at_et": et_now().isoformat(timespec="seconds"),
            "verdict": verdict, "coverage": cov, "funnel": fun, "trades": trades,
            "rule_breaks": breaks, "refusals": refusals, "fill_class": fills}


def render(d: dict) -> str:
    cov, fun, tr = d["coverage"], d["funnel"], d["trades"]
    ref = d.get("refusals", {"n": 0, "sessions": 0, "reasons": {}, "by_setup": {}})
    L = [f"# Futures EOD — {d['date']}", "",
         f"> Generated `{d['generated_at_et']}` · verdict **{d['verdict']}**",
         f"> Fill class **{d['fill_class']}**"
         + (" — simulated fills are mechanism evidence, **never edge evidence**."
            if d["fill_class"] == "SIMULATED" else ""), ""]

    L += ["## Was the lane awake?", "",
          f"**{cov['verdict']}** — {cov['ticks']}/{cov['expected']} ticks "
          f"({cov['pct']:.0%}). {cov['note']}", ""]
    if cov["verdict"] in ("DARK", "RED"):
        L += ["> ⚠️ Everything below is conditional on the engine having run. It mostly "
              "did not, so read the numbers as *unknown*, not as *zero*.", ""]
    if ref.get("sessions", 0) >= REFUSAL_RED_SESSIONS:
        L += [f"> 🚨 **{ref['sessions']}-session refusal streak** — the same placement "
              f"reason has now been refused {ref['sessions']} consecutive sessions in a "
              f"row. This is not discipline, it is stuck.", ""]
    elif ref.get("n", 0):
        L += [f"> ⚠️ **{ref['n']} placement(s) refused** after clearing every rail this "
              f"session. Sitting out on no signal is fine; being refused after clearing "
              f"the rails is not.", ""]

    L += ["## Funnel", "",
          f"- **{fun['signals_seen']}** signals seen → **{fun['entries']}** entries "
          f"→ {fun['exit_events']} exit events"]
    if fun["rejections_by_rail"]:
        L.append("- rejected by rail: " + " · ".join(
            f"`{k}` {v}" for k, v in sorted(fun["rejections_by_rail"].items(),
                                            key=lambda kv: -kv[1])))
    if fun["actions"]:
        L.append("- actions: " + " · ".join(f"`{k}` {v}" for k, v in fun["actions"].items()))
    if fun["feed_verdicts"]:
        L.append("- feed: " + " · ".join(f"`{k}` {v}" for k, v in fun["feed_verdicts"].items()))
    if fun["errors"]:
        L.append(f"- ⚠️ **{len(fun['errors'])} errors** — {fun['errors'][:3]}")
    L.append("")

    L += ["## Refusals", ""]
    if ref.get("n"):
        streak_note = (f" · **{ref['sessions']}-session streak**"
                       if ref.get("sessions", 0) > 1 else "")
        L.append(f"- **{ref['n']}** `ENTER_REFUSED`{streak_note}")
        if ref.get("reasons"):
            L.append("- by reason: " + " · ".join(
                f"`{k}` {v}" for k, v in sorted(ref["reasons"].items(),
                                                key=lambda kv: -kv[1])))
        if ref.get("by_setup"):
            L.append("- by setup: " + " · ".join(
                f"`{k}` {v}" for k, v in ref["by_setup"].items()))
    else:
        L.append("✅ no refused placements")
    L.append("")

    L += [f"## Round trips ({tr['fills']})", ""]
    if tr["n"]:
        L += [f"- **{tr['n']}** closed · **${tr['total_pnl']:,.2f}** · "
              f"WR {tr['win_rate']:.0%} · best ${tr['best']:,.2f} / worst ${tr['worst']:,.2f}",
              "- by setup: " + " · ".join(f"`{k}` {v}" for k, v in tr["by_setup"].items()),
              "- by exit: " + " · ".join(f"`{k}` {v}" for k, v in tr["by_exit"].items())]
    else:
        L.append("- none closed today")
    L.append("")

    L += ["## Rule audit", ""]
    if d["rule_breaks"]:
        L.append(f"🚨 **{len(d['rule_breaks'])} break(s)** — process over P&L, a winning "
                 "trade that broke a rule still counts:")
        for b in d["rule_breaks"]:
            L.append(f"- `{b['ts']}` **{b['rule']}** — {b['detail']}")
    else:
        L.append("✅ no rule breaks detected (post-hoc check, independent of the entry gate)")
    L.append("")
    return "\n".join(L)


def write(d: dict) -> Path:
    DIGEST_DIR.mkdir(parents=True, exist_ok=True)
    path = DIGEST_DIR / f"{d['date']}.md"
    path.write_text(render(d), encoding="utf-8")
    try:
        STATE_OUT.parent.mkdir(parents=True, exist_ok=True)
        slim = {k: v for k, v in d.items() if k != "trades"}
        slim["trades"] = {k: v for k, v in d["trades"].items() if k != "rows"}
        tmp = STATE_OUT.with_suffix(".tmp")
        tmp.write_text(json.dumps(slim, indent=2, default=str), encoding="utf-8")
        os.replace(tmp, STATE_OUT)
    except Exception:  # noqa: BLE001 -- digest write is the deliverable; state is a bonus
        pass
    return path


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Futures EOD session review")
    ap.add_argument("--date", default=None)
    ap.add_argument("--fills", default="SIMULATED",
                    choices=["SIMULATED", "BROKER", "UNKNOWN"])
    ap.add_argument("--print", action="store_true", help="print the digest to stdout")
    args = ap.parse_args(argv)

    d = build(args.date, args.fills)
    path = write(d)
    if args.print:
        # The digest is UTF-8 (arrows, check marks); a Windows console defaults to cp1252
        # and would raise UnicodeEncodeError mid-print, turning a successful review into a
        # traceback. The FILE is always written correctly regardless -- only stdout needs
        # persuading.
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
        print(render(d))
    else:
        print(json.dumps({"date": d["date"], "verdict": d["verdict"],
                          "coverage": d["coverage"]["verdict"],
                          "ticks": d["coverage"]["ticks"],
                          "entries": d["funnel"]["entries"],
                          "closed": d["trades"]["n"],
                          "pnl": d["trades"]["total_pnl"],
                          "rule_breaks": len(d["rule_breaks"]),
                          "digest": str(path.relative_to(REPO))}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

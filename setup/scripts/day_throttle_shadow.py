#!/usr/bin/env python
"""day_throttle_shadow.py -- the forward counter for day-throttle-forward-prereg-2026-08-18.

The pre-registration froze two candidate throttles (T-2, T-6) plus a secondary observation
(H-FIRSTWAVE) and promised a 15-session forward window. THIS is the thing that keeps that
promise. Without it the pre-reg is prose, and prose does not adjudicate itself (C35/L221:
a falsification promise nobody wired is a promise nobody keeps).

WHAT IT MEASURES
----------------
For every real fill, whether a per-arm intraday realized-loss throttle WOULD HAVE blocked
that entry -- and what that entry actually went on to make. Two thresholds, expressed as a
percent of the arm's start-of-day equity so they scale with the account:

    T-2  halt the arm for the session once its own REALIZED session P&L <= -2% of SoD equity
    T-6  same at -6%

Plus H-FIRSTWAVE: was the session's FIRST impulse wave red at the moment this entry was
placed?

WHY IT RUNS NIGHTLY OFF THE LEDGER AND NOT ON THE HOT PATH
----------------------------------------------------------
The engine's 1-minute tick is deterministic Python with no room for speculative
instrumentation, and every shadow counter that has ever been bolted onto it became a
market-hours failure surface. The same evidence is exactly recomputable after the close
from `journal/trades.csv`, so it is. $0, read-only, and a crash here can never touch a
trade.

THE NO-LOOK-AHEAD RULE (the whole validity of this counter)
-----------------------------------------------------------
The realized-P&L sum that arms the throttle may include ONLY trades whose EXIT timestamp is
at or before the candidate entry's timestamp. A still-open loser must NOT arm it -- we could
not have known. Violating that turns a counterfactual into an oracle and every number below
becomes fiction. Pinned by test_day_throttle_shadow.py.

SHADOW ONLY. Neither threshold refuses anything live. This script writes measurements; it
does not modify params, prompts, or engine state.
"""
from __future__ import annotations

import collections
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

TRADES = REPO / "journal" / "trades.csv"
PREREG = REPO / "analysis" / "recommendations" / "day-throttle-forward-prereg-2026-08-18.json"
OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "day-throttle-shadow-ledger.jsonl"
SUMMARY = OUT_DIR / "day-throttle-shadow-summary.json"

# Frozen by the pre-registration. Changing either value VOIDS the window (no_peeking_rule).
CANDIDATES = {"T-2": 2.0, "T-6": 6.0}
FORWARD_FIRST_DATE = "2026-08-18"   # the window opens the first session AFTER the freeze
SESSIONS_REQUIRED = 15
WAVE_GAP_S = 900

KNOWN_ARMS = {"safe", "bold", "safe-1", "safe-3", "risky-1", "risky-3"}


def _num(x):
    try:
        return float(str(x).replace("$", "").replace(",", ""))
    except (TypeError, ValueError):
        return None


def _secs(t):
    try:
        p = str(t).split(":")
        return int(p[0]) * 3600 + int(p[1]) * 60 + (int(float(p[2])) if len(p) > 2 else 0)
    except (TypeError, ValueError, IndexError):
        return None


def load_fills():
    out = []
    with open(TRADES, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r.get("account_id") not in KNOWN_ARMS:
                continue
            pnl, sec = _num(r.get("dollar_pnl")), _secs(r.get("time_entry"))
            if pnl is None or sec is None:
                continue
            out.append({"date": r["date"], "arm": r["account_id"], "pnl": pnl, "sec": sec,
                        "xsec": _secs(r.get("time_exit")), "eq": _num(r.get("account_equity_pre")),
                        "qty": _num(r.get("qty")), "side": r.get("c_or_p"),
                        "setup": r.get("setup")})
    out.sort(key=lambda r: (r["date"], r["sec"], r["arm"]))
    return out


def realized_before(rows, at_sec):
    """Session P&L an arm could actually SEE at `at_sec`: only already-EXITED trades.

    A trade with no exit timestamp is treated as still open (contributes nothing) -- the
    conservative reading, and the one that cannot manufacture an oracle."""
    return sum(q["pnl"] for q in rows if q["xsec"] is not None and q["xsec"] <= at_sec)


def first_wave_was_red(session_rows, at_sec):
    """Was the session's FIRST impulse wave closed and red by `at_sec`?

    Returns None while the first wave is still open or is itself the entry being judged --
    'not yet knowable' is a third state, never silently folded into False."""
    if not session_rows:
        return None
    t0 = min(r["sec"] for r in session_rows)
    wave1 = [r for r in session_rows if r["sec"] - t0 <= WAVE_GAP_S]
    if any(r["sec"] >= at_sec for r in wave1):
        return None                      # the entry is inside wave 1
    if any(r["xsec"] is None or r["xsec"] > at_sec for r in wave1):
        return None                      # wave 1 has not fully closed yet
    return sum(r["pnl"] for r in wave1) < 0


def evaluate(fills):
    by_session = collections.defaultdict(list)
    by_arm_day = collections.defaultdict(list)
    for r in fills:
        by_session[r["date"]].append(r)
        by_arm_day[(r["arm"], r["date"])].append(r)

    rows = []
    for r in fills:
        arm_rows = by_arm_day[(r["arm"], r["date"])]
        realized = realized_before(arm_rows, r["sec"])
        eqs = [x["eq"] for x in arm_rows if x["eq"]]
        eq = max(eqs) if eqs else None
        rec = {"date": r["date"], "arm": r["arm"], "time_entry_s": r["sec"],
               "pnl": r["pnl"], "side": r["side"], "setup": r["setup"],
               "sod_equity": eq, "realized_before_entry": round(realized, 2),
               "first_wave_was_red": first_wave_was_red(by_session[r["date"]], r["sec"])}
        for cid, pct in CANDIDATES.items():
            if eq is None:
                rec[f"would_block_{cid}"] = None   # abstain -- never guess an equity
            else:
                rec[f"would_block_{cid}"] = realized <= -(pct / 100.0) * eq
        rows.append(rec)
    return rows


def score(rows, since=None):
    """Aggregate a candidate's forward performance. `delta` is the book improvement from
    NOT taking the blocked fills -- i.e. minus their P&L."""
    sel = [r for r in rows if since is None or r["date"] >= since]
    out = {}
    for cid in CANDIDATES:
        key = f"would_block_{cid}"
        blocked = [r for r in sel if r[key] is True]
        abstain = [r for r in sel if r[key] is None]
        bw = sum(r["pnl"] for r in blocked if r["pnl"] > 0)
        bl = sum(r["pnl"] for r in blocked if r["pnl"] <= 0)
        by_day = collections.defaultdict(float)
        for r in blocked:
            by_day[r["date"]] -= r["pnl"]
        best_day = max(by_day.values(), default=0.0)
        delta = -sum(r["pnl"] for r in blocked)
        out[cid] = {
            "n_kept": len(sel) - len(blocked) - len(abstain),
            "n_blocked": len(blocked), "n_abstain": len(abstain),
            "delta_usd": round(delta, 2),
            "blocked_winner_usd": round(bw, 2), "blocked_loser_usd": round(bl, 2),
            "blocked_wr_pct": round(100 * sum(1 for r in blocked if r["pnl"] > 0) / len(blocked), 1)
            if blocked else None,
            "delta_ex_best_session_usd": round(delta - best_day, 2),
            "sessions_touched": len(by_day),
            "f_gates": {
                "F1_direction_positive": delta > 0,
                "F2_not_a_winner_killer": bw < abs(bl),
                "F3_frequency_n_blocked_ge_10": len(blocked) >= 10,
                "F4_survives_dropping_best_session": (delta - best_day) > 0,
                "_note": "F5 (regime split) is adjudicated by a session reading the window, "
                         "not computed nightly -- it needs the range classification for each "
                         "session in the window.",
            },
        }
    fw = [r for r in sel if r["first_wave_was_red"] is not None]
    red = [r for r in fw if r["first_wave_was_red"]]
    green = [r for r in fw if not r["first_wave_was_red"]]
    out["H-FIRSTWAVE"] = {
        "n_judgeable": len(fw),
        "after_red_first_wave": {"n": len(red), "usd": round(sum(r["pnl"] for r in red), 2)},
        "after_green_first_wave": {"n": len(green), "usd": round(sum(r["pnl"] for r in green), 2)},
        "_observation_only": "No rule is proposed from this. It is logged so the window can "
                             "measure whether the in-sample split survives.",
    }
    return out


def main() -> int:
    from et_clock import et_now

    if not PREREG.exists():
        print(f"day_throttle_shadow: pre-registration missing at {PREREG} -- refusing to "
              "produce numbers with no frozen spec behind them", file=sys.stderr)
        return 1
    prereg = json.loads(PREREG.read_text(encoding="utf-8"))

    fills = load_fills()
    if not fills:
        print("day_throttle_shadow: no usable fills in journal/trades.csv", file=sys.stderr)
        return 1
    rows = evaluate(fills)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    tmp = LEDGER.with_suffix(".jsonl.tmp")
    tmp.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
    tmp.replace(LEDGER)

    fwd_dates = sorted({r["date"] for r in rows if r["date"] >= FORWARD_FIRST_DATE})
    summary = {
        "_meta": {
            "generated_at_et": et_now().isoformat(),
            "builder": "setup/scripts/day_throttle_shadow.py",
            "prereg": str(PREREG.relative_to(REPO)).replace("\\", "/"),
            "prereg_status": prereg.get("status"),
            "shadow_only": "MEASUREMENT ONLY -- neither threshold refuses a live entry.",
            "candidates_pct_of_sod_equity": CANDIDATES,
            "forward_window": {"first_date": FORWARD_FIRST_DATE,
                               "sessions_required": SESSIONS_REQUIRED,
                               "sessions_elapsed": len(fwd_dates),
                               "dates": fwd_dates,
                               "verdict_ready": len(fwd_dates) >= SESSIONS_REQUIRED},
        },
        "forward": score(rows, since=FORWARD_FIRST_DATE),
        "in_sample_reference": score(rows, since=None),
        "_reading_note": "`forward` is the ONLY block that can adjudicate the pre-registration. "
                         "`in_sample_reference` is the population the hypothesis was generated on "
                         "and is printed for drift-checking only -- it can never clear a gate.",
    }
    SUMMARY.write_text(json.dumps(summary, indent=1), encoding="utf-8")

    fw = summary["_meta"]["forward_window"]
    print(f"day_throttle_shadow: {len(rows)} fills scored; forward window "
          f"{fw['sessions_elapsed']}/{fw['sessions_required']} sessions"
          f"{' -- VERDICT READY' if fw['verdict_ready'] else ' (measuring, judge nothing)'}")
    for cid in CANDIDATES:
        f = summary["forward"][cid]
        print(f"  {cid}: blocked={f['n_blocked']} delta=${f['delta_usd']:,.0f} "
              f"ex-best-session=${f['delta_ex_best_session_usd']:,.0f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

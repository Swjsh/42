"""Shadow clock for the LOSS-ARMED per-arm session premium BUDGET.

MEASUREMENT ONLY. Nothing here refuses a live entry. The live gate
(`risk_gate.check_daily_premium_budget`) exists but is INERT --
`params.daily_premium_budget_dollars` is absent from every params file.

Frozen spec: analysis/recommendations/loss-armed-budget-forward-prereg-2026-08-28.json
This script REFUSES to emit numbers if that file is missing (same stance as its
sibling `day_throttle_shadow.py`): no frozen spec, no output.

WHAT IT MEASURES
----------------
Once an arm's REALIZED session P&L goes below $0 -- counting only trades already
EXITED at the moment a new entry would be placed -- that arm may not place an
entry whose premium would push its CUMULATIVE session premium deployed past the
candidate's cap. Entries placed while flat or green are unconstrained. Three caps
are registered ($500 / $700 / $1,000) so the forward window tests the BAND, not
the in-sample argmax. See the prereg's HONESTY_DISCLOSURE: $700 was chosen
in-sample and is the candidate most likely to be an artifact.

REUSE (L184 -- one implementation, never re-inline)
---------------------------------------------------
The tape loader, the second-of-day parser, the number coercion and the
"what could this arm actually SEE at time T" helper are imported from
`day_throttle_shadow`, NOT copied. That sibling's own window is frozen and
mid-flight; this module imports from it and never mutates it. The F-gate scoring
shape is deliberately mirrored so the two studies stay directly comparable.

CAUSALITY
---------
Both inputs are knowable at decision time: cumulative premium spent so far today
and realized P&L from already-closed trades. No look-ahead. `realized_before`
treats a trade with no exit timestamp as still open (contributes nothing), which
is the reading that cannot manufacture an oracle.
"""

from __future__ import annotations

import collections
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "setup" / "scripts"))

from day_throttle_shadow import (  # noqa: E402  -- reuse, do not re-inline
    KNOWN_ARMS,
    _num,
    _secs,
    realized_before,
)

TRADES = REPO / "journal" / "trades.csv"
PREREG = REPO / "analysis" / "recommendations" / "loss-armed-budget-forward-prereg-2026-08-28.json"
OUT_DIR = REPO / "analysis" / "recommendations"
LEDGER = OUT_DIR / "loss-armed-budget-shadow-ledger.jsonl"
SUMMARY = OUT_DIR / "loss-armed-budget-shadow-summary.json"

# Frozen by the pre-registration. Changing any of these VOIDS the window.
CANDIDATES = {"B-500": 500.0, "B-700": 700.0, "B-1000": 1000.0}
FORWARD_FIRST_DATE = "2026-08-29"
SESSIONS_REQUIRED = 15


def load_entries() -> list[dict]:
    """Collapse trades.csv ROUND-TRIP rows into ENTRIES.

    One entry can appear as several rows (a TP1 slice and a runner slice share a
    time_entry and a contract). The budget is spent once, at entry, so the rows
    are summed back into a single spend of `premium_paid`.
    """
    groups: dict[tuple, dict] = {}
    with open(TRADES, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            if r.get("account_id") not in KNOWN_ARMS:
                continue
            sec = _secs(r.get("time_entry"))
            pnl = _num(r.get("dollar_pnl"))
            if sec is None or pnl is None:
                continue
            key = (r["date"], r["account_id"], sec, r.get("contract"))
            g = groups.setdefault(
                key,
                {
                    "date": r["date"],
                    "arm": r["account_id"],
                    "sec": sec,
                    "contract": r.get("contract"),
                    "side": r.get("c_or_p"),
                    "setup": r.get("setup"),
                    "quality": r.get("setup_quality") or None,
                    "pnl": 0.0,
                    "cost": 0.0,
                    "cost_readable": True,
                    "xsec": None,
                },
            )
            g["pnl"] += pnl
            paid = _num(r.get("premium_paid"))
            if paid is None:
                g["cost_readable"] = False  # abstain -- never guess a spend
            else:
                g["cost"] += paid
            xs = _secs(r.get("time_exit"))
            # the entry is closed only when its LAST slice closes
            if xs is not None and (g["xsec"] is None or xs > g["xsec"]):
                g["xsec"] = xs
            elif xs is None:
                g["xsec"] = g["xsec"]
    out = sorted(groups.values(), key=lambda g: (g["date"], g["sec"], g["arm"]))
    return out


def evaluate(entries: list[dict]) -> list[dict]:
    """Replay each session per arm in time order, spending the budget causally."""
    by_arm_day = collections.defaultdict(list)
    for e in entries:
        by_arm_day[(e["arm"], e["date"])].append(e)

    # exit-aware view for realized_before(): it expects rows with pnl + xsec
    rows_out = []
    for (arm, date), day_entries in sorted(by_arm_day.items()):
        day_entries.sort(key=lambda e: e["sec"])
        spent = {cid: 0.0 for cid in CANDIDATES}
        for e in day_entries:
            realized = realized_before(day_entries, e["sec"])
            rec = {
                "date": date,
                "arm": arm,
                "time_entry_s": e["sec"],
                "contract": e["contract"],
                "side": e["side"],
                "setup": e["setup"],
                "quality": e["quality"],
                "pnl": round(e["pnl"], 2),
                "premium_paid": round(e["cost"], 2) if e["cost_readable"] else None,
                "realized_before_entry": round(realized, 2),
                "armed": realized < 0,
            }
            for cid, cap in CANDIDATES.items():
                if not e["cost_readable"]:
                    rec[f"would_block_{cid}"] = None  # abstain
                    continue
                if realized < 0 and spent[cid] + e["cost"] > cap:
                    rec[f"would_block_{cid}"] = True
                else:
                    rec[f"would_block_{cid}"] = False
                    spent[cid] += e["cost"]
            rows_out.append(rec)
    rows_out.sort(key=lambda r: (r["date"], r["time_entry_s"], r["arm"]))
    return rows_out


def score(rows: list[dict], since: str | None = None) -> dict:
    """Mirror of day_throttle_shadow.score's shape, plus the band-coherence gate."""
    sel = [r for r in rows if since is None or r["date"] >= since]
    out: dict = {}
    for cid in CANDIDATES:
        key = f"would_block_{cid}"
        blocked = [r for r in sel if r[key] is True]
        abstain = [r for r in sel if r[key] is None]
        bw = sum(r["pnl"] for r in blocked if r["pnl"] > 0)
        bl = sum(r["pnl"] for r in blocked if r["pnl"] <= 0)
        by_day: dict[str, float] = collections.defaultdict(float)
        for r in blocked:
            by_day[r["date"]] -= r["pnl"]
        best_day = max(by_day.values(), default=0.0)
        delta = -sum(r["pnl"] for r in blocked)
        out[cid] = {
            "n_kept": len(sel) - len(blocked) - len(abstain),
            "n_blocked": len(blocked),
            "n_abstain": len(abstain),
            "delta_usd": round(delta, 2),
            "premium_not_deployed_usd": round(
                sum(r["premium_paid"] or 0.0 for r in blocked), 2
            ),
            "blocked_winner_usd": round(bw, 2),
            "blocked_loser_usd": round(bl, 2),
            "blocked_wr_pct": round(
                100 * sum(1 for r in blocked if r["pnl"] > 0) / len(blocked), 1
            )
            if blocked
            else None,
            "delta_ex_best_session_usd": round(delta - best_day, 2),
            "sessions_touched": len(by_day),
            "f_gates": {
                "F1_direction_positive": delta > 0,
                "F2_not_a_winner_killer": bw < abs(bl),
                "F3_frequency_n_blocked_ge_10": len(blocked) >= 10,
                "F4_survives_dropping_best_session": (delta - best_day) > 0,
            },
        }

    # F5 -- the gate that makes the in-sample-argmax disclosure testable.
    out["F5_band_coherence"] = {
        "all_three_caps_F1_positive": all(
            out[cid]["f_gates"]["F1_direction_positive"] for cid in CANDIDATES
        ),
        "per_cap_delta_usd": {cid: out[cid]["delta_usd"] for cid in CANDIDATES},
        "_meaning": "If only the in-sample argmax (B-700) is positive, the finding is a "
        "curve-fit and the study is REFUTED regardless of B-700's own number.",
    }

    # H-TIER -- observation only, no rule proposed.
    tier = collections.defaultdict(lambda: [0, 0.0, 0])
    for r in sel:
        q = r.get("quality")
        if not q:
            continue
        t = tier[q]
        t[0] += 1
        t[1] += r["pnl"]
        t[2] += r["pnl"] > 0
    out["H-TIER"] = {
        q: {
            "n": v[0],
            "usd": round(v[1], 2),
            "wr_pct": round(100 * v[2] / v[0], 1),
        }
        for q, v in sorted(tier.items())
    }
    out["H-TIER"]["_observation_only"] = (
        "In-sample the conviction label did NOT rank outcomes (ELITE 23.2% WR vs BASE "
        "28.6%; entry score vs return r=+0.052). Logged to see whether that holds "
        "forward. No rule is proposed from this."
    )
    return out


def main() -> int:
    from et_clock import et_now

    if not PREREG.exists():
        print(
            f"loss_armed_budget_shadow: pre-registration missing at {PREREG} -- refusing "
            "to produce numbers with no frozen spec behind them",
            file=sys.stderr,
        )
        return 2

    entries = load_entries()
    if not entries:
        print("loss_armed_budget_shadow: no entries parsed from trades.csv", file=sys.stderr)
        return 2

    rows = evaluate(entries)
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")

    fwd_dates = sorted({r["date"] for r in rows if r["date"] >= FORWARD_FIRST_DATE})
    summary = {
        "_meta": {
            "generated_at_et": et_now().isoformat(),
            "builder": "setup/scripts/loss_armed_budget_shadow.py",
            "prereg": str(PREREG.relative_to(REPO)).replace("\\", "/"),
            "prereg_status": "FROZEN_PREREG_FORWARD",
            "shadow_only": "MEASUREMENT ONLY -- no candidate refuses a live entry. The live "
            "gate risk_gate.check_daily_premium_budget is INERT "
            "(params.daily_premium_budget_dollars absent everywhere).",
            "trigger": "arm's realized session P&L < $0 from already-EXITED trades only",
            "candidates_cap_usd": CANDIDATES,
            "threshold_provenance_warning": "B-700 was chosen as the IN-SAMPLE argmax. F5 "
            "band-coherence is the gate that tests whether that is a curve-fit.",
            "forward_window": {
                "first_date": FORWARD_FIRST_DATE,
                "sessions_required": SESSIONS_REQUIRED,
                "sessions_elapsed": len(fwd_dates),
                "dates": fwd_dates,
                "verdict_ready": len(fwd_dates) >= SESSIONS_REQUIRED,
            },
        },
        "forward": score(rows, since=FORWARD_FIRST_DATE),
        "in_sample_NOT_EVIDENCE": score(rows, since=None),
    }
    SUMMARY.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    fw = summary["_meta"]["forward_window"]
    print(
        f"loss_armed_budget_shadow: {len(rows)} entries scored | forward sessions "
        f"{fw['sessions_elapsed']}/{SESSIONS_REQUIRED} | verdict_ready={fw['verdict_ready']}"
    )
    for cid in CANDIDATES:
        f = summary["forward"][cid]
        i = summary["in_sample_NOT_EVIDENCE"][cid]
        print(
            f"  {cid:7} forward: blocked {f['n_blocked']:>3} delta ${f['delta_usd']:>+9.2f}"
            f"   | in-sample (NOT evidence): blocked {i['n_blocked']:>3} "
            f"delta ${i['delta_usd']:>+9.2f}"
        )
    print(f"  wrote {LEDGER.relative_to(REPO)} + {SUMMARY.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

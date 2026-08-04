"""postfix_gate_costing.py -- window-scoped refusal costing for EVERY entry gate/filter.

Born Lane 1, 2026-08-04 ("make sure nothing is gated that actually works", J week
directive): the nightly gate-expiry instrument mines only SKIP_* verdicts, so the
10/11-filter checklist (which refuses via HOLD rows with per-door blocker lists, not SKIP
verdicts) had NO refusal-costing instrument at all. This tool closes that gap for any
window (default: the post-level-feed-fix era 2026-07-31..2026-08-03).

Reuses gate_expiry_check's machinery byte-for-bit (armed=True rows, 15-min event
clustering, stale-bar drop, ATM real-OPRA replay, premium_stop -8%, recency exit shape).
Parts:
  A. core SKIP-verdict gates (whatever fired in the window, regardless of current armed
     flag -- unlike the nightly, which INERTs a now-disarmed gate and loses its history)
  B. filter sole-blocker cohorts from HOLD rows, per door (bear/bull) x filter 1..11:
     rows where the checklist failed on EXACTLY ONE filter -- the honest per-filter
     binding cohort (multi-blocker rows are cascade cohorts, C15: no single filter may
     claim them; census reported separately, the bear [5,8] both-lifted cell priced as
     ORACLE only)
  C. fleet SKIP_MIN_PREMIUM_FLOOR events priced at the counterfactual ATM strike (what
     ATM-TIER-EXTENSION-2K-10K plans) -- SIM label, per-event independent (no
     NOT_FLAT sequencing), refused OTM quote recorded alongside.

Output: analysis/recommendations/gate-postfix-costing-<end>.json (or --out).
Never blocks, never kills, never edits params -- a report, same doctrine as the nightly.

Run: backtest/.venv/Scripts/python.exe backtest/tools/postfix_gate_costing.py
     [--start YYYY-MM-DD] [--end YYYY-MM-DD] [--out PATH]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]   # ...\42\backtest
ROOT = REPO.parent                           # ...\42
for _p in (str(REPO), str(ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from autoresearch.gate_expiry_check import (  # noqa: E402
    CORE_DECISIONS, EVENT_CLUSTER_GAP_MINUTES, cluster_events, load_decision_rows,
    simulate_event,
)
from autoresearch.recency_check import (  # noqa: E402
    QTY_BY_ACCOUNT, load_merged_spy_vix, window_metrics,
)
from autoresearch._edgehunt_vwap_continuation import _normalize_spy  # noqa: E402
from lib.ribbon import compute_ribbon  # noqa: E402

DOORS = {
    "bear": ("bear_blockers", "P", "bear_rejection_level_raw"),
    "bull": ("bull_blockers", "C", "bull_reclaim_level_raw"),
}
FLEET_ARMS = ("safe-3", "risky-1", "risky-3")


def mine(start: dt.date, end: dt.date) -> dict:
    print("[postfix] loading SPY+VIX frame ...", flush=True)
    spy_raw, _vix = load_merged_spy_vix()
    spy = _normalize_spy(spy_raw)
    ribbon = compute_ribbon(pd.Series(spy["close"].values))
    spy_ts = spy["timestamp_et"]

    rows = [r for r in load_decision_rows(CORE_DECISIONS, start)
            if r.get("ts_et", "")[:10] <= end.isoformat() and r.get("armed") is True]
    print(f"[postfix] core rows in window: {len(rows)}", flush=True)
    verdict_counts = Counter((r.get("account"), r.get("verdict")) for r in rows)

    # ---- PART A ------------------------------------------------------------------
    skip_actions = sorted({v for (_a, v) in verdict_counts if v and v.startswith("SKIP")})
    part_a = {}
    for action in skip_actions:
        per_account, all_ok, door_keys, late = {}, [], set(), 0
        for account in ("safe", "bold"):
            sub = [r for r in rows if r.get("account") == account and r.get("verdict") == action]
            events = cluster_events(sub, EVENT_CLUSTER_GAP_MINUTES)
            sims = [simulate_event(ev, spy, ribbon, spy_ts, QTY_BY_ACCOUNT.get(account, 1), action)
                    for ev in events]
            ok = [s for s in sims if s["status"] == "ok"]
            m = window_metrics(ok, start, end) if ok else {"n": 0}
            per_account[account] = {"n_raw_fires": len(sub), "n_events": len(events),
                                    "status_counts": dict(Counter(s["status"] for s in sims)), **m}
            all_ok.extend(ok)
            for ev in events:
                door_keys.add(ev["ts_et"][:16])
                if ev["ts_et"][11:16] >= "15:00":
                    late += 1
        combined = window_metrics(all_ok, start, end) if all_ok else {"n": 0}
        late_ok = [s for s in all_ok if str(s.get("ts_et", ""))[11:16] >= "15:00"]
        part_a[action] = {
            "per_account": per_account, "combined": combined,
            "door_level_distinct_clusters_across_accounts": len(door_keys),
            "events_at_or_after_1500_et": late,
            "pnl_at_or_after_1500_et": round(sum(s["pnl"] for s in late_ok), 2),
        }
        print(f"[postfix] A {action}: n={combined.get('n')} total=${combined.get('total_dollar')}", flush=True)

    # ---- PART B ------------------------------------------------------------------
    part_b = {}
    for door, (bkey, side, lvl_key) in DOORS.items():
        for account in ("safe", "bold"):
            holds = [r for r in rows if r.get("account") == account and r.get("verdict") == "HOLD"]
            for filt in range(1, 12):
                sub = []
                for r in holds:
                    if (r.get(bkey) or []) == [filt]:
                        ev = dict(r)
                        ev["side"] = side
                        if r.get(lvl_key) is not None:
                            ev["trigger_level_exact"] = r[lvl_key]
                        sub.append(ev)
                if not sub:
                    continue
                events = cluster_events(sub, EVENT_CLUSTER_GAP_MINUTES)
                sims = [simulate_event(ev, spy, ribbon, spy_ts, QTY_BY_ACCOUNT.get(account, 1),
                                       f"filter{filt}_{door}") for ev in events]
                ok = [s for s in sims if s["status"] == "ok"]
                m = window_metrics(ok, start, end) if ok else {"n": 0}
                key = f"{door}_filter{filt}_{account}"
                part_b[key] = {"n_raw_sole_blocker_rows": len(sub), "n_events": len(events),
                               "status_counts": dict(Counter(s["status"] for s in sims)), **m,
                               "vix_at_events": [round(float(e.get("vix") or 0), 2) for e in events][:12]}
                print(f"[postfix] B {key}: events={len(events)} total=${m.get('total_dollar')}", flush=True)

    combo_counts = {}
    for door, (bkey, _s, _l) in DOORS.items():
        c = Counter()
        for r in rows:
            if r.get("verdict") == "HOLD":
                combo = tuple(r.get(bkey) or [])
                if combo:
                    c[combo] += 1
        combo_counts[door] = {"|".join(map(str, k)): v for k, v in c.most_common(12)}

    oracle_58 = {}
    for account in ("safe", "bold"):
        sub = []
        for r in rows:
            if (r.get("account") == account and r.get("verdict") == "HOLD"
                    and (r.get("bear_blockers") or []) == [5, 8]):
                ev = dict(r)
                ev["side"] = "P"
                if r.get("bear_rejection_level_raw") is not None:
                    ev["trigger_level_exact"] = r["bear_rejection_level_raw"]
                sub.append(ev)
        events = cluster_events(sub, EVENT_CLUSTER_GAP_MINUTES)
        sims = [simulate_event(ev, spy, ribbon, spy_ts, QTY_BY_ACCOUNT.get(account, 1),
                               "oracle_bear_5_8") for ev in events]
        ok = [s for s in sims if s["status"] == "ok"]
        m = window_metrics(ok, start, end) if ok else {"n": 0}
        oracle_58[account] = {"n_rows": len(sub), "n_events": len(events),
                              "status_counts": dict(Counter(s["status"] for s in sims)), **m}
        print(f"[postfix] ORACLE bear[5,8] {account}: total=${m.get('total_dollar')}", flush=True)

    # ---- PART C ------------------------------------------------------------------
    part_c = {}
    for arm in FLEET_ARMS:
        fp = ROOT / "automation" / "state" / "fleet" / arm / "decisions.jsonl"
        sub = []
        if fp.exists():
            for line in fp.open(encoding="utf-8"):
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                ts = str(r.get("ts_et") or "")
                if (start.isoformat() <= ts[:10] <= end.isoformat()
                        and r.get("risk_code") == "SKIP_MIN_PREMIUM_FLOOR"):
                    sub.append(r)
        events = cluster_events(sub, EVENT_CLUSTER_GAP_MINUTES)
        sims, refused = [], []
        for ev in events:
            e = dict(ev)
            e["ts_et"] = e["ts_et"][:19]
            e.setdefault("side", "C")
            qty = int(ev.get("qty") or (3 if arm.startswith("safe") else 5))
            sims.append(simulate_event(e, spy, ribbon, spy_ts, qty, "min_premium_floor_atm_cf"))
            refused.append({"ts": ev["ts_et"][:16], "planned_strike": ev.get("strike"),
                            "refused_premium": ev.get("premium"), "qty": qty})
        ok = [s for s in sims if s["status"] == "ok"]
        m = window_metrics(ok, start, end) if ok else {"n": 0}
        by_day = defaultdict(float)
        for s in ok:
            by_day[s["date"]] += s["pnl"]
        part_c[arm] = {"n_raw_floor_rows": len(sub), "n_events": len(events),
                       "status_counts": dict(Counter(s["status"] for s in sims)), **m,
                       "by_day": {k: round(v, 2) for k, v in sorted(by_day.items())},
                       "refused_quotes_sample": refused[:10]}
        print(f"[postfix] C {arm}: floor_rows={len(sub)} ATM-cf total=${m.get('total_dollar')}", flush=True)

    return {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "window": f"{start}..{end}",
        "conventions": {
            "miner": "gate_expiry_check machinery (armed=True, 15-min clustering, stale-bar drop)",
            "pricing": "real OPRA 5m cache, ATM strike, premium_stop -8%, recency exit shape (shared with the nightly instrument)",
            "resolution_bias": "5-min bars under-detect intra-bar stops (one-directional, flattering) -- OPTION-BAR-RESOLUTION-BIAS-2026-08-02",
            "per_account_double_count": "safe+bold rows at the same tick are the same door signal logged per account (instrument-consistent; door-level distinct clusters reported separately)",
            "part_c_label": "SIM counterfactual (ATM strike under ATM-TIER-EXTENSION-2K-10K), NOT broker fills; per-event independent; overlaps Part A's elite cohort (same door) -- never sum A+C",
        },
        "verdict_counts_in_window": {f"{a}|{v}": n for (a, v), n in sorted(verdict_counts.items())},
        "part_a_skip_gates": part_a,
        "part_b_filter_sole_blockers": part_b,
        "blocker_combo_census_hold_rows": combo_counts,
        "oracle_bear_5_8_both_lifted": {
            "label": ("ORACLE -- lifting filter 8 alone admits none of these (ribbon filter 5 "
                      "still blocks; filter-5 deletion is graveyarded); both-lifted upper bound only"),
            **oracle_58},
        "part_c_fleet_floor_atm_counterfactual": part_c,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Window-scoped refusal costing for every entry gate/filter")
    ap.add_argument("--start", default="2026-07-31")
    ap.add_argument("--end", default="2026-08-03")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    start, end = dt.date.fromisoformat(args.start), dt.date.fromisoformat(args.end)
    out = mine(start, end)
    out_path = Path(args.out) if args.out else (
        ROOT / "analysis" / "recommendations" / f"gate-postfix-costing-{end.isoformat()}.json")
    out_path.write_text(json.dumps(out, indent=1, default=str), encoding="utf-8")
    print(f"[postfix] wrote {out_path}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

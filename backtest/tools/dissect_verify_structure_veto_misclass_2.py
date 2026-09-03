"""Independent reproduction / verification of dissect-structure-veto-misclass finding.

Reads automation/state/core-decisions.jsonl (READ-ONLY). Backfills a missing
'date' field from ts_et[:10] (older rows in this ledger predate the 'date'
key but carry a full ts_et). Rebuilds SKIP_STRUCTURE_VETO episodes for the
'safe' account across the FULL retained history (not just today), and
computes the same 30-min forward SPY move test the original report used,
to check whether the "ledger only retains 2026-08-26 onward" claim and the
"n=2 today only" population claim hold up.

No network calls. No trading-path files touched.
"""
import json
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict, Counter

REPO = Path(__file__).resolve().parents[2]
CORE = REPO / "automation" / "state" / "core-decisions.jsonl"
WINNER_DAYS = ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]


def load_all():
    rows = []
    with open(CORE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if "date" not in d:
                ts = d.get("ts_et") or ""
                d["date"] = ts[:10] if ts else None
            rows.append(d)
    return rows


def main():
    rows = load_all()
    print(f"total rows in ledger: {len(rows)}")
    ts_all = sorted(r.get("ts_et") for r in rows if r.get("ts_et"))
    print(f"ts_et range: {ts_all[0]} .. {ts_all[-1]}")
    n_with_date_key = sum(1 for r in rows if r.get("date"))
    print(f"rows with a derivable date: {n_with_date_key} / {len(rows)}")

    safe_rows = [r for r in rows if r.get("account") == "safe"]
    veto_rows = [r for r in safe_rows if r.get("verdict") == "SKIP_STRUCTURE_VETO"]
    veto_rows.sort(key=lambda r: r["ts_et"])
    print(f"\ntotal SKIP_STRUCTURE_VETO rows (safe, full retained history): {len(veto_rows)}")

    by_date = Counter(r["date"] for r in veto_rows)
    print("\nSKIP_STRUCTURE_VETO raw-row counts by date:")
    for d in sorted(by_date):
        print(f"  {d}: {by_date[d]}")

    print("\nWinner-day check (raw per-minute decision rows present? veto rows present?):")
    for wd in WINNER_DAYS:
        day_rows = [r for r in safe_rows if r.get("date") == wd]
        day_veto = [r for r in veto_rows if r["date"] == wd]
        print(f"  {wd}: total_decision_rows={len(day_rows)} veto_rows={len(day_veto)}")

    # ---- Episode dedup: consecutive same-side same-date runs, gap<=120s ----
    episodes = []
    cur = None
    for r in veto_rows:
        side = r.get("side")
        date = r.get("date")
        ts = r["ts_et"]
        dt = datetime.fromisoformat(ts)
        if cur and cur["date"] == date and cur["side"] == side and (dt - cur["last_dt"]).total_seconds() <= 120:
            cur["rows"].append(r)
            cur["last_dt"] = dt
            cur["last_ts"] = ts
        else:
            if cur:
                episodes.append(cur)
            cur = {"date": date, "side": side, "first_ts": ts, "first_spy": r.get("spy"),
                   "last_ts": ts, "last_dt": dt, "rows": [r]}
    if cur:
        episodes.append(cur)

    print(f"\ntotal episodes (deduped, all history): {len(episodes)}")
    side_counts = Counter(e["side"] for e in episodes)
    print(f"episodes by side: {dict(side_counts)}")

    # per-date tape cache (safe account, any verdict, for forward SPY lookups)
    tape_cache = {}

    def get_tape(date):
        if date not in tape_cache:
            d_rows = [r for r in safe_rows if r.get("date") == date and r.get("spy") is not None]
            d_rows.sort(key=lambda r: r["ts_et"])
            tape_cache[date] = [(r["ts_et"], r["spy"]) for r in d_rows]
        return tape_cache[date]

    def spy_at_or_after(date, ts_target):
        for ts, spy in get_tape(date):
            if ts >= ts_target:
                return ts, spy
        return None, None

    results = []
    for ep in episodes:
        if ep["side"] not in ("C", "P"):
            continue
        first_dt = datetime.fromisoformat(ep["first_ts"])
        entry_spy = ep["first_spy"]
        if entry_spy is None:
            continue
        t30 = (first_dt + timedelta(minutes=30)).isoformat()
        ts30, spy30 = spy_at_or_after(ep["date"], t30)
        move30 = (spy30 - entry_spy) if spy30 is not None else None
        fav30 = None
        if move30 is not None:
            fav30 = (move30 > 0) if ep["side"] == "C" else (move30 < 0)
        results.append({
            "date": ep["date"], "side": ep["side"], "first_ts": ep["first_ts"],
            "entry_spy": entry_spy, "spy_t30": spy30, "move30": round(move30, 3) if move30 is not None else None,
            "blocked_entry_would_have_won_30m": fav30,
            "has_30m_readout": spy30 is not None and (datetime.fromisoformat(ts30) - first_dt).total_seconds() <= 45*60 if ts30 else False,
        })

    n_complete = [r for r in results if r["move30"] is not None]
    print(f"\nepisodes with a computable +30m SPY readout (all history): {len(n_complete)} / {len(results)}")
    wins = sum(1 for r in n_complete if r["blocked_entry_would_have_won_30m"])
    losses = len(n_complete) - wins
    print(f"blocked entry would have WON (30m, favorable direction): {wins}")
    print(f"blocked entry would have LOST (30m, unfavorable direction): {losses}")
    if n_complete:
        print(f"win rate: {wins/len(n_complete):.1%}")
        avg_move = sum(r["move30"] if r["side"]=="C" else -r["move30"] for r in n_complete) / len(n_complete)
        print(f"avg signed-favorable SPY move (30m): {avg_move:+.3f}")

    print("\nPer-date episode detail:")
    for r in results:
        print(f"  {r['date']} {r['first_ts']} side={r['side']} entry_spy={r['entry_spy']} "
              f"spy_t30={r['spy_t30']} move30={r['move30']} won={r['blocked_entry_would_have_won_30m']}")

    # bootstrap CI on win rate if n is large enough
    if len(n_complete) >= 8:
        import random
        random.seed(42)
        outcomes = [1 if r["blocked_entry_would_have_won_30m"] else 0 for r in n_complete]
        boots = []
        for _ in range(5000):
            sample = [random.choice(outcomes) for _ in outcomes]
            boots.append(sum(sample) / len(sample))
        boots.sort()
        lo = boots[int(0.025 * len(boots))]
        hi = boots[int(0.975 * len(boots))]
        print(f"\nbootstrap 95% CI on win rate, n={len(outcomes)}: [{lo:.1%}, {hi:.1%}]")

    out_path = REPO / "analysis" / "deep-research" / "2026-09-03-money" / "verify-dissect-structure-veto-misclass-2.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_ledger_rows": len(rows),
            "ts_et_range": [ts_all[0], ts_all[-1]],
            "total_veto_rows_safe_full_history": len(veto_rows),
            "veto_rows_by_date": dict(by_date),
            "winner_day_check": {wd: {
                "total_decision_rows": len([r for r in safe_rows if r.get("date") == wd]),
                "veto_rows": len([r for r in veto_rows if r["date"] == wd]),
            } for wd in WINNER_DAYS},
            "episodes_all_history": results,
            "n_complete_30m": len(n_complete),
            "wins_30m": wins,
            "losses_30m": losses,
        }, f, indent=2, default=str)
    print(f"\nwrote {out_path}")


if __name__ == "__main__":
    main()

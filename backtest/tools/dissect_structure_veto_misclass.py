"""D7 STRUCTURE VETO MISCLASSIFICATION -- read-only dissection.

Scratch analysis tool. Reads automation/state/core-decisions.jsonl (READ-ONLY),
reconstructs 5m SPY bars from the per-minute 'spy' tape logged there, and runs
the REAL classify_trend/find_swing_points/label_swings functions (imported,
not reimplemented) against them to check whether the 2026-09-03 11:16-11:27
SKIP_STRUCTURE_VETO rows are reproducible from the tape.

Never touches automation/state/**, journal/**, analysis/quote-tape/**, or any
trading-path file. No network calls.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone
from collections import defaultdict

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backtest"))
sys.path.insert(0, str(REPO))

from crypto.lib.bar import Bar
from crypto.lib.market_structure import classify_trend, label_swings
from crypto.lib.trendlines import find_swing_points

CORE = REPO / "automation" / "state" / "core-decisions.jsonl"
VETO_SHIP_DATE = "2026-06-26"  # commit 26832c07 / 667217a1
WINNER_DAYS = ["2026-08-06", "2026-08-13", "2026-08-27", "2026-08-28"]


def load_rows(account=None, date=None):
    out = []
    with open(CORE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if account is not None and d.get("account") != account:
                continue
            if date is not None and d.get("date") != date:
                continue
            out.append(d)
    return out


def bucket_5m(rows):
    """Bucket per-minute 'spy' snapshots into 5m OHLC bars keyed by bucket-start ET.

    APPROXIMATE: each bucket has at most ~5 one-per-minute samples (the tick
    cadence), not true continuous-tick OHLC, so high/low can undershoot the
    real bar's true intrabar extremes. open=first sample, close=last sample,
    high=max, low=min. Bucket key = 5-min floor of the tick timestamp, matching
    the observed bar_et / trigger_bar_et labeling convention (bar label =
    INTERVAL START; confirmed empirically: bar '09:30' first appears as
    trigger_bar_et at tick 09:36:03, i.e. one minute after its [09:30,09:35)
    interval closes).
    """
    buckets = defaultdict(list)
    for r in rows:
        ts = r.get("ts_et")
        spy = r.get("spy")
        if ts is None or spy is None:
            continue
        dt = datetime.fromisoformat(ts)
        floor_min = (dt.minute // 5) * 5
        bkey = dt.replace(minute=floor_min, second=0, microsecond=0)
        buckets[bkey].append((dt, float(spy)))
    bars = {}
    for bkey, samples in buckets.items():
        samples.sort(key=lambda x: x[0])
        prices = [p for _, p in samples]
        bars[bkey] = {
            "open": prices[0], "high": max(prices), "low": min(prices),
            "close": prices[-1], "volume": 0.0, "n_samples": len(prices),
        }
    return bars


def bars_dict_to_barlist(bars_dict, up_to_key):
    keys = sorted(k for k in bars_dict if k <= up_to_key)
    out = []
    for k in keys:
        b = bars_dict[k]
        out.append(Bar(
            open_time=k.replace(tzinfo=timezone.utc), open=b["open"], high=b["high"], low=b["low"],
            close=b["close"], volume=b["volume"], granularity_seconds=300,
            source="reconstructed_spy_5m",
        ))
    return out, keys


def run_classifier(bars_list):
    swings = find_swing_points(bars_list, window=2, inclusive_right=True)
    labeled = label_swings(swings)
    trend = classify_trend(labeled)
    return trend, swings, labeled


def find_trigger_bar_et_for_tick(rows_by_ts, ts_et_target):
    """Find the row nearest (<=) the target ts_et and return its trigger_bar_et."""
    best = None
    for r in rows_by_ts:
        if r["ts_et"] <= ts_et_target:
            if best is None or r["ts_et"] > best["ts_et"]:
                best = r
    return best


def main():
    out = {"section": {}}

    # ---------- PART 1: reproduce today's 11:16 / 11:21 / 11:27 classification ----------
    rows_today = load_rows(account="safe", date="2026-09-03")
    rows_today.sort(key=lambda r: r["ts_et"])
    bars_dict = bucket_5m(rows_today)

    targets = ["2026-09-03T11:16:03", "2026-09-03T11:21:03", "2026-09-03T11:27:03"]
    repro = []
    for target in targets:
        row = find_trigger_bar_et_for_tick(rows_today, target)
        if row is None:
            repro.append({"target": target, "error": "no row found"})
            continue
        trig_bar_et_raw = row.get("trigger_bar_et")
        logged_reason = None
        if row.get("conviction"):
            logged_reason = row["conviction"].get("structure_reason")
        trig_key = datetime.fromisoformat(trig_bar_et_raw.replace("-04:00", "")) if trig_bar_et_raw else None
        bar_list, used_keys = bars_dict_to_barlist(bars_dict, trig_key) if trig_key else ([], [])
        trend, swings, labeled = run_classifier(bar_list)
        repro.append({
            "target_tick": row["ts_et"],
            "logged_verdict": row.get("verdict"),
            "logged_structure_reason": logged_reason,
            "logged_spy": row.get("spy"),
            "trigger_bar_et_used": trig_bar_et_raw,
            "n_bars_fed": len(bar_list),
            "bar_keys_first_last": [str(used_keys[0]), str(used_keys[-1])] if used_keys else None,
            "reconstructed_trend": trend,
            "matches_logged": (trend == logged_reason),
            "swings_detected": [
                {"bar_idx": s.bar_index, "kind": s.kind, "price": round(s.price, 2),
                 "bar_key": str(used_keys[s.bar_index]) if used_keys and s.bar_index < len(used_keys) else None}
                for s in sorted(swings, key=lambda s: s.bar_index)
            ],
            "labeled_swings": [
                {"bar_idx": ls.bar_index, "kind": ls.kind, "price": round(ls.price, 2), "label": ls.label}
                for ls in labeled
            ],
        })
    out["section"]["today_reproduction"] = repro

    # Full session bar table for 09:30 through 11:30 (for the report appendix)
    session_bars = []
    for k in sorted(bars_dict.keys()):
        if k >= datetime.fromisoformat("2026-09-03T09:30:00") and k <= datetime.fromisoformat("2026-09-03T11:35:00"):
            b = bars_dict[k]
            session_bars.append({"bar_start_et": k.strftime("%H:%M"), **{kk: round(vv, 3) if isinstance(vv, float) else vv for kk, vv in b.items()}})
    out["section"]["session_bars_0930_1135"] = session_bars

    # last 2 bars before each trigger (to show the confirmation-lag blind spot)
    for entry in repro:
        if "trigger_bar_et_used" in entry and entry["trigger_bar_et_used"]:
            pass

    # ---------- PART 2: full history of SKIP_STRUCTURE_VETO since ship ----------
    all_safe_rows = load_rows(account="safe")
    veto_rows = [r for r in all_safe_rows if r.get("verdict") == "SKIP_STRUCTURE_VETO" and r.get("date", "") >= VETO_SHIP_DATE]
    veto_rows.sort(key=lambda r: r["ts_et"])

    # group into "episodes": consecutive-minute runs of the SAME side veto on the SAME date
    # (avoids 1/min re-logging of the identical blocked signal inflating the episode count)
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
            cur["last_spy"] = r.get("spy")
        else:
            if cur:
                episodes.append(cur)
            cur = {"date": date, "side": side, "first_ts": ts, "first_spy": r.get("spy"),
                   "last_ts": ts, "last_spy": r.get("spy"), "last_dt": dt, "rows": [r]}
    if cur:
        episodes.append(cur)

    # per-date per-minute spy tape cache for forward-move lookups
    spy_tape_by_date = {}

    def get_tape(date):
        if date not in spy_tape_by_date:
            rows_d = load_rows(account="safe", date=date)
            rows_d.sort(key=lambda r: r["ts_et"])
            spy_tape_by_date[date] = [(r["ts_et"], r.get("spy")) for r in rows_d if r.get("spy") is not None]
        return spy_tape_by_date[date]

    def spy_at_or_after(date, ts_target):
        tape = get_tape(date)
        for ts, spy in tape:
            if ts >= ts_target:
                return ts, spy
        return None, None

    ep_summaries = []
    for ep in episodes:
        date = ep["date"]
        side = ep["side"]  # 'C' = bull blocked (structure='downtrend'), 'P' = bear blocked (structure='uptrend')
        first_dt = datetime.fromisoformat(ep["first_ts"])
        entry_spy = ep["first_spy"]
        t30 = (first_dt + timedelta(minutes=30)).isoformat()
        t60 = (first_dt + timedelta(minutes=60)).isoformat()
        ts30, spy30 = spy_at_or_after(date, t30)
        ts60, spy60 = spy_at_or_after(date, t60)
        move30 = (spy30 - entry_spy) if (spy30 is not None and entry_spy is not None) else None
        move60 = (spy60 - entry_spy) if (spy60 is not None and entry_spy is not None) else None
        # "would the entry have gone the right way": for a blocked C (bull) entry, favorable = SPY up.
        # for a blocked P (bear) entry, favorable = SPY down.
        fav30 = None
        fav60 = None
        if move30 is not None:
            fav30 = (move30 > 0) if side == "C" else (move30 < 0) if side == "P" else None
        if move60 is not None:
            fav60 = (move60 > 0) if side == "C" else (move60 < 0) if side == "P" else None
        ep_summaries.append({
            "date": date, "side_blocked": side,
            "structure_label": "downtrend" if side == "C" else ("uptrend" if side == "P" else None),
            "first_ts": ep["first_ts"], "last_ts": ep["last_ts"],
            "n_ticks": len(ep["rows"]), "entry_spy": entry_spy,
            "spy_t30": spy30, "spy_t60": spy60,
            "move30": round(move30, 3) if move30 is not None else None,
            "move60": round(move60, 3) if move60 is not None else None,
            "veto_would_have_been_right_30m": (not fav30) if fav30 is not None else None,
            "veto_would_have_been_right_60m": (not fav60) if fav60 is not None else None,
            "entry_would_have_won_30m": fav30,
            "entry_would_have_won_60m": fav60,
        })

    out["section"]["episode_count_raw_rows"] = len(veto_rows)
    out["section"]["episode_count_deduped"] = len(episodes)
    out["section"]["episodes"] = ep_summaries

    # aggregate by side
    def agg(side, horizon_key):
        subset = [e for e in ep_summaries if e["side_blocked"] == side and e[horizon_key] is not None]
        n = len(subset)
        wins = sum(1 for e in subset if e[horizon_key])
        return n, wins

    agg_summary = {}
    for side in ("C", "P"):
        for hz in ("veto_would_have_been_right_30m", "veto_would_have_been_right_60m"):
            n, wins = agg(side, hz)
            agg_summary[f"{side}_{hz}"] = {"n": n, "veto_correct": wins, "pct": round(100 * wins / n, 1) if n else None}
    out["section"]["aggregate_by_side"] = agg_summary

    # bootstrap CI on "veto correct" rate for C-side (bull-in-downtrend), 60m horizon (largest population expected)
    import random
    random.seed(42)

    def bootstrap_ci(vals, n_boot=5000):
        if not vals:
            return None
        n = len(vals)
        means = []
        for _ in range(n_boot):
            sample = [vals[random.randrange(n)] for _ in range(n)]
            means.append(sum(sample) / n)
        means.sort()
        lo = means[int(0.025 * n_boot)]
        hi = means[int(0.975 * n_boot)]
        return {"n": n, "mean": round(sum(vals) / n, 4), "ci_lo_2.5pct": round(lo, 4), "ci_hi_97.5pct": round(hi, 4)}

    for side in ("C", "P"):
        for hz in ("veto_would_have_been_right_30m", "veto_would_have_been_right_60m"):
            vals = [1.0 if e[hz] else 0.0 for e in ep_summaries if e["side_blocked"] == side and e[hz] is not None]
            out["section"].setdefault("bootstrap_ci", {})[f"{side}_{hz}"] = bootstrap_ci(vals)

    # ---------- PART 3: winner-day effect ----------
    winner_hits = [e for e in ep_summaries if e["date"] in WINNER_DAYS]
    out["section"]["winner_day_vetoes"] = winner_hits
    out["section"]["winner_days_checked"] = WINNER_DAYS

    # ---------- write ----------
    outdir = REPO / "analysis" / "deep-research" / "2026-09-03-money"
    outdir.mkdir(parents=True, exist_ok=True)
    with open(outdir / "dissect-structure-veto-misclass.json", "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, default=str)

    print(json.dumps({
        "today_repro": [{"tick": r.get("target_tick"), "logged": r.get("logged_structure_reason"),
                          "reconstructed": r.get("reconstructed_trend"), "match": r.get("matches_logged"),
                          "n_bars": r.get("n_bars_fed")} for r in repro],
        "episode_count_raw_rows": len(veto_rows),
        "episode_count_deduped": len(episodes),
        "agg_summary": agg_summary,
    }, indent=2, default=str))


if __name__ == "__main__":
    main()

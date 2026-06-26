"""Near-miss outcome analysis: for each filter-blocked near-miss, compute what
happened to price in the next N bars to assess whether the filter was correct.

Security: read-only on decisions.jsonl + CSV data. No writes to production state.
Output: analysis/recommendations/near-miss-outcome.json
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path
import pandas as pd
import datetime as dt

REPO = Path(__file__).resolve().parents[1]
REPO_ROOT = REPO.parent
DECISIONS = REPO_ROOT / "automation" / "state" / "decisions.jsonl"
DATA = REPO / "data"
OUT = REPO_ROOT / "analysis" / "recommendations"
OUT.mkdir(parents=True, exist_ok=True)

NEAR_MISS_BEAR = 8
NEAR_MISS_BULL = 9
HOLD_ACTIONS = {"HOLD", "HOLD_DEV", "HOLD_RUNNER"}

# Outcome window: look N bars forward to compute excursion
OUTCOME_BARS = 12  # 60 minutes at 5-min resolution


def load_decisions(path: Path) -> list[dict]:
    rows = []
    if not path.exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    rows.append(parsed)
            except json.JSONDecodeError:
                pass
    return rows


def _score(row: dict, key: str) -> int:
    v = row.get(key, 0)
    try:
        return int(v) if v is not None else 0
    except (TypeError, ValueError):
        return 0


def extract_blocked_filters(row: dict) -> list[int]:
    side = "bull" if _score(row, "bull_score") >= NEAR_MISS_BULL else "bear"
    fs = row.get("filter_state", {})
    if fs:
        key = f"{side}_blocked"
        blocked = fs.get(key) or fs.get("blocked") or []
        if blocked:
            return [int(b) for b in blocked]
    reason = row.get("reason", "")
    nums = re.findall(r'filter[_\s]?(\d+)', reason, re.I)
    return [int(n) for n in nums]


def load_spy_data() -> pd.DataFrame:
    """Load and merge all spy 5-min CSV files. Uses UTC-aware timestamps for sorting."""
    import sys
    autoresearch = REPO / "autoresearch"
    if str(autoresearch) not in sys.path:
        sys.path.insert(0, str(autoresearch))
    try:
        from runner import load_data
        spy, _ = load_data(dt.date(2025, 1, 1), dt.date(2026, 6, 15))
        # runner returns df with _parsed_ts (UTC-aware). Keep it for comparison.
        return spy
    except Exception:
        pass

    # Fallback: manual load with UTC parse
    csvs = sorted(DATA.glob("spy_5m_*.csv"))
    dfs = []
    for p in csvs:
        try:
            df = pd.read_csv(p)
            df["_parsed_ts"] = pd.to_datetime(df["timestamp_et"], utc=True, errors="coerce")
            df = df.dropna(subset=["_parsed_ts"])
            dfs.append(df)
        except Exception:
            pass
    if not dfs:
        return pd.DataFrame()
    combined = pd.concat(dfs, ignore_index=True)
    combined = combined.drop_duplicates(subset=["_parsed_ts"]).sort_values("_parsed_ts").reset_index(drop=True)
    return combined


def compute_outcome(spy: pd.DataFrame, ts: pd.Timestamp, side: str) -> dict | None:
    """For a given entry timestamp and side, compute what happened in the next OUTCOME_BARS bars."""
    # Use _parsed_ts (UTC-aware) if available, else fall back to timestamp_et
    col = "_parsed_ts" if "_parsed_ts" in spy.columns else "timestamp_et"
    # Convert ts to UTC-aware for comparison if col is UTC-aware
    try:
        sample = spy[col].dropna().iloc[0]
        if isinstance(sample, pd.Timestamp) and sample.tzinfo is not None and ts.tzinfo is None:
            ts_cmp = pd.Timestamp(ts).tz_localize("America/New_York").tz_convert("UTC")
        else:
            ts_cmp = ts
    except Exception:
        ts_cmp = ts
    idx_matches = spy.index[spy[col] == ts_cmp].tolist()
    if not idx_matches:
        # Try fuzzy match within 2 minutes
        target_range = (ts_cmp - pd.Timedelta(minutes=2), ts_cmp + pd.Timedelta(minutes=2))
        idx_matches = spy.index[(spy[col] >= target_range[0]) &
                                (spy[col] <= target_range[1])].tolist()
    if not idx_matches:
        return None
    idx = idx_matches[0]
    entry_bar = spy.iloc[idx]
    entry_price = float(entry_bar["close"])

    future_bars = spy.iloc[idx + 1: idx + 1 + OUTCOME_BARS]
    if len(future_bars) == 0:
        return None

    highs = future_bars["high"].values
    lows = future_bars["low"].values
    final_close = float(future_bars["close"].iloc[-1])

    if side == "bull":
        max_favorable = float(max(highs)) - entry_price
        max_adverse = entry_price - float(min(lows))
        final_move = final_close - entry_price
    else:  # bear
        max_favorable = entry_price - float(min(lows))
        max_adverse = float(max(highs)) - entry_price
        final_move = entry_price - final_close

    return {
        "entry_price": round(entry_price, 2),
        "max_favorable_spy": round(max_favorable, 2),
        "max_adverse_spy": round(max_adverse, 2),
        "final_move_spy": round(final_move, 2),
        "outcome_bars": len(future_bars),
        "favorable": max_favorable > 0.50,  # >50c favorable move
        "adverse": max_adverse > 1.00,      # >$1 adverse (stop-level)
    }


def parse_timestamp(row: dict) -> pd.Timestamp | None:
    date_str = row.get("date", "")
    time_str = row.get("time_et", "")
    if not date_str or not time_str:
        ts_raw = row.get("timestamp_et") or row.get("ts") or ""
        if ts_raw:
            try:
                return pd.Timestamp(ts_raw)
            except Exception:
                return None
        return None
    try:
        return pd.Timestamp(f"{date_str} {time_str}")
    except Exception:
        return None


def main():
    rows = load_decisions(DECISIONS)
    print(f"Loaded {len(rows)} decision rows")

    spy = load_spy_data()
    print(f"Loaded {len(spy)} SPY bars" if len(spy) > 0 else "No SPY data")

    # Find near-miss rows with filter blocks
    near_miss_blocked: list[dict] = []
    for r in rows:
        action = r.get("action", r.get("decision", ""))
        if action not in HOLD_ACTIONS:
            continue
        bs = _score(r, "bear_score")
        bu = _score(r, "bull_score")
        if not (bs >= NEAR_MISS_BEAR or bu >= NEAR_MISS_BULL):
            continue
        blocked = extract_blocked_filters(r)
        if not blocked:
            continue
        side = "bull" if bu >= NEAR_MISS_BULL else "bear"
        near_miss_blocked.append({
            "row": r,
            "side": side,
            "blocked": blocked,
            "bull_score": bu,
            "bear_score": bs,
        })

    print(f"\nNear-miss rows with filter blocks: {len(near_miss_blocked)}")

    # Group by primary filter
    from collections import defaultdict
    by_filter: dict[int, list] = defaultdict(list)
    results = []

    for nm in near_miss_blocked:
        row = nm["row"]
        ts = parse_timestamp(row)
        if ts is None:
            continue
        outcome = compute_outcome(spy, ts, nm["side"]) if len(spy) > 0 else None

        entry = {
            "date": str(row.get("date", "")),
            "time_et": str(row.get("time_et", "")),
            "side": nm["side"],
            "bull_score": nm["bull_score"],
            "bear_score": nm["bear_score"],
            "blocked_filters": nm["blocked"],
            "primary_filter": nm["blocked"][0] if nm["blocked"] else None,
            "spy": row.get("spy"),
            "vix": row.get("vix"),
            "outcome": outcome,
        }
        results.append(entry)
        for f in nm["blocked"]:
            by_filter[f].append(entry)

    # Summarise by filter
    filter_summary = {}
    for f_id, entries in sorted(by_filter.items()):
        outcomes = [e["outcome"] for e in entries if e["outcome"]]
        n_favorable = sum(1 for o in outcomes if o and o["favorable"])
        n_adverse = sum(1 for o in outcomes if o and o["adverse"])
        avg_favorable = (sum(o["max_favorable_spy"] for o in outcomes) / len(outcomes)) if outcomes else 0
        avg_adverse = (sum(o["max_adverse_spy"] for o in outcomes) / len(outcomes)) if outcomes else 0
        avg_final = (sum(o["final_move_spy"] for o in outcomes) / len(outcomes)) if outcomes else 0
        filter_summary[str(f_id)] = {
            "total_blocks": len(entries),
            "with_outcome_data": len(outcomes),
            "n_favorable_move": n_favorable,
            "n_adverse_move": n_adverse,
            "pct_favorable": round(100 * n_favorable / len(outcomes), 1) if outcomes else 0,
            "avg_max_favorable_spy": round(avg_favorable, 2),
            "avg_max_adverse_spy": round(avg_adverse, 2),
            "avg_final_move_spy": round(avg_final, 2),
            "verdict": "BLOCK_JUSTIFIED" if avg_final < 0 else "BLOCK_COSTLY" if avg_final > 0.50 else "NEUTRAL",
            "by_date": [f"{e['date']} {e['time_et']} {e['side']} f{e['primary_filter']} outcome:{e['outcome']['final_move_spy'] if e['outcome'] else 'N/A'}" for e in entries[:10]],
        }

    output = {
        "generated": str(dt.datetime.now()),
        "total_near_miss_blocked": len(results),
        "filter_summary": filter_summary,
        "raw": results,
    }

    out_path = OUT / "near-miss-outcome.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(f"\nWrote: {out_path}")

    print("\n=== FILTER OUTCOME SUMMARY ===")
    for f_id, s in filter_summary.items():
        print(f"\nFilter {f_id} [{s['verdict']}]:")
        print(f"  Blocks: {s['total_blocks']} ({s['with_outcome_data']} with data)")
        print(f"  Favorable moves (>50c): {s['n_favorable_move']}/{s['with_outcome_data']} ({s['pct_favorable']}%)")
        print(f"  Avg max favorable: +${s['avg_max_favorable_spy']}")
        print(f"  Avg max adverse:   +${s['avg_max_adverse_spy']}")
        print(f"  Avg final move:     {'+' if s['avg_final_move_spy'] >= 0 else ''}{s['avg_final_move_spy']}")
        for line in s["by_date"][:5]:
            print(f"    {line}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

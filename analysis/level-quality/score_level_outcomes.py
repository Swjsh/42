"""Task 0.2 + 0.3 — EOD level-outcome scorer and level-memory builder.

For each trading day:
  1. Load that day's levels (from archived snapshot if available, else from
     the production generator via levels._detect_from_history).
  2. Walk the day's RTH bars and classify each level as RESPECT / BREAK /
     CHOP / UNTOUCHED using classify_level() from the benchmark script.
  3. Write per-day outcomes-{date}.jsonl under automation/state/level-quality/.
  4. Append a row to the running level-quality-ledger.jsonl.
  5. (Task 0.3) Update level-memory.json: keyed by $0.05 price buckets,
     cumulative {respect_count, broken_count, touch_count, last_seen, hit_rate}.

Usage:
  python score_level_outcomes.py                         # score today
  python score_level_outcomes.py --date 2026-06-10       # score one day
  python score_level_outcomes.py --backfill 2026-05-01 2026-06-15

Imports classify_level() and tag_source() directly from benchmark_level_quality.py
so the classification logic is never duplicated (per task spec).

OP-20 disclosure:
  N reported per run; IS/OOS not applicable here (this is live outcome labelling).
  Null/baseline = the benchmark JSON for comparison context.
  Metric: RESPECT = price moved >= $0.30 away from level within 6 bars of first touch.
  Real-fills authority: this is SPY price-space, not option premium (L74).
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib.util
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "backtest" / "data"
SNAPSHOTS_DIR = REPO / "analysis" / "level-quality" / "snapshots"
OUT_DIR = REPO / "automation" / "state" / "level-quality"
OUT_DIR.mkdir(parents=True, exist_ok=True)

LEDGER_PATH = REPO / "analysis" / "level-quality" / "level-quality-ledger.jsonl"
MEMORY_PATH = OUT_DIR / "level-memory.json"

# ---------------------------------------------------------------------------
# Import production level generator
# ---------------------------------------------------------------------------
_levels_path = REPO / "backtest" / "lib" / "levels.py"
_spec = importlib.util.spec_from_file_location("gamma_levels", _levels_path)
levels_mod = importlib.util.module_from_spec(_spec)
sys.modules["gamma_levels"] = levels_mod
_spec.loader.exec_module(levels_mod)  # type: ignore

# ---------------------------------------------------------------------------
# Import classify_level, tag_source from benchmark (single source of truth)
# ---------------------------------------------------------------------------
_bench_path = REPO / "analysis" / "level-quality" / "benchmark_level_quality.py"
_bench_spec = importlib.util.spec_from_file_location("bench_lq", _bench_path)
bench_mod = importlib.util.module_from_spec(_bench_spec)
sys.modules["bench_lq"] = bench_mod
_bench_spec.loader.exec_module(bench_mod)  # type: ignore

classify_level = bench_mod.classify_level
tag_source = bench_mod.tag_source
HEADLINE_REACT = bench_mod.HEADLINE_REACT    # $0.30
HEADLINE_K = bench_mod.HEADLINE_K            # 6 bars
RTH_OPEN = bench_mod.RTH_OPEN
RTH_CLOSE = bench_mod.RTH_CLOSE

# ---------------------------------------------------------------------------
# Data loaders
# ---------------------------------------------------------------------------
SPY_FILES = [
    "spy_5m_2025-01-01_2026-05-22.csv",
    "spy_5m_2026-05-19_2026-06-15.csv",
]


def _parse_wall_clock(series: pd.Series) -> pd.Series:
    return pd.to_datetime(
        series.astype(str).str.slice(0, 19), format="%Y-%m-%d %H:%M:%S"
    )


def load_spy() -> pd.DataFrame:
    frames = []
    for fn in SPY_FILES:
        p = DATA_DIR / fn
        if not p.exists():
            continue
        df = pd.read_csv(p)
        df["timestamp_et"] = _parse_wall_clock(df["timestamp_et"])
        frames.append(df)
    if not frames:
        raise SystemExit("No SPY data files found.")
    spy = pd.concat(frames, ignore_index=True)
    spy = spy.drop_duplicates(subset=["timestamp_et"]).sort_values("timestamp_et").reset_index(drop=True)
    for c in ("open", "high", "low", "close", "volume"):
        spy[c] = pd.to_numeric(spy[c], errors="coerce")
    spy["date"] = spy["timestamp_et"].dt.date
    spy["time"] = spy["timestamp_et"].dt.time
    return spy.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Level loader: snapshot first, then generator fallback
# ---------------------------------------------------------------------------
def load_levels_for_day(d: dt.date, spy: pd.DataFrame):
    """Return (active_levels, multi_day_set, swept_set) for day d.

    Tries archived snapshot first (curated levels).
    Falls back to production generator (deterministic approximation).
    """
    snap_file = SNAPSHOTS_DIR / d.isoformat() / "key-levels.json"
    if snap_file.exists():
        try:
            data = json.loads(snap_file.read_text(encoding="utf-8"))
            levels_list = data.get("levels", [])
            prices = [float(lv["price"]) for lv in levels_list if lv.get("price")]
            # No multi_day / swept distinction in curated JSON without extra parsing
            multi = set()
            swept = set()
            for lv in levels_list:
                src = (lv.get("source") or "").lower()
                if "multi" in src or "carry" in (lv.get("tier") or "").lower():
                    multi.add(float(lv["price"]))
                if "swept" in src:
                    swept.add(float(lv["price"]))
            return sorted(set(prices)), multi, swept
        except Exception as e:
            print(f"  WARNING: snapshot load failed for {d}: {e} — falling back to generator")

    # Generator fallback
    open_mask = (spy["date"] == d) & (spy["time"] >= RTH_OPEN)
    if not open_mask.any():
        return [], set(), set()
    open_idx = int(np.argmax(open_mask.to_numpy()))
    history = spy.iloc[:open_idx]
    if history["date"].nunique() < 6:
        return [], set(), set()
    try:
        ls = levels_mod._detect_from_history(history.copy(), d)
        multi = set(ls.multi_day)
        swept = set(getattr(ls, "swept_levels", []) or [])
        return sorted(set(ls.active)), multi, swept
    except Exception as e:
        print(f"  WARNING: generator failed for {d}: {e}")
        return [], set(), set()


# ---------------------------------------------------------------------------
# Price bucket for level memory ($0.05 granularity)
# ---------------------------------------------------------------------------
BUCKET = 0.05

def price_bucket(price: float) -> str:
    return str(round(round(price / BUCKET) * BUCKET, 2))


# ---------------------------------------------------------------------------
# Score one day
# ---------------------------------------------------------------------------
def score_day(d: dt.date, spy: pd.DataFrame) -> dict | None:
    active, multi, swept = load_levels_for_day(d, spy)
    if not active:
        return None

    rth = spy[(spy["date"] == d) & (spy["time"] >= RTH_OPEN) & (spy["time"] < RTH_CLOSE)]
    if len(rth) < 5:
        return None
    rth = rth.reset_index(drop=True)
    regime = "unknown"  # VIX not loaded here; use "unknown"

    rows = []
    n_touched = 0
    n_respect = 0
    n_break = 0
    by_source: dict[str, dict] = {}

    for L in active:
        src = tag_source(L, multi, swept)
        o = classify_level(L, rth, HEADLINE_REACT, HEADLINE_K, src, regime)
        row = {
            "date": d.isoformat(),
            "price": L,
            "source": src,
            "touched": o.touched,
            "outcome": o.kind,
            "reaction_dollars": round(o.reaction, 3),
            "false_break": o.false_break,
        }
        rows.append(row)
        if o.touched:
            n_touched += 1
            if o.kind == "RESPECT":
                n_respect += 1
            elif o.kind == "BREAK":
                n_break += 1
        if src not in by_source:
            by_source[src] = {"n": 0, "touched": 0, "respect": 0}
        by_source[src]["n"] += 1
        if o.touched:
            by_source[src]["touched"] += 1
            if o.kind == "RESPECT":
                by_source[src]["respect"] += 1

    n = len(active)
    touch_rate = round(n_touched / n, 4) if n else None
    respect_rate = round(n_respect / n_touched, 4) if n_touched else None
    break_rate = round(n_break / n_touched, 4) if n_touched else None

    summary = {
        "date": d.isoformat(),
        "n_levels": n,
        "n_touched": n_touched,
        "n_respect": n_respect,
        "n_break": n_break,
        "touch_rate": touch_rate,
        "respect_rate_of_touched": respect_rate,
        "break_rate_of_touched": break_rate,
        "by_source": {
            k: {
                "n": v["n"],
                "touch_rate": round(v["touched"] / v["n"], 4) if v["n"] else None,
                "respect_rate_of_touched": round(v["respect"] / v["touched"], 4) if v["touched"] else None,
            }
            for k, v in by_source.items()
        },
        "source": "snapshot" if (SNAPSHOTS_DIR / d.isoformat() / "key-levels.json").exists() else "generator",
    }

    return {"summary": summary, "rows": rows}


# ---------------------------------------------------------------------------
# Ledger append (append-only; skip if date already in ledger)
# ---------------------------------------------------------------------------
def _ledger_dates() -> set[str]:
    if not LEDGER_PATH.exists():
        return set()
    seen = set()
    for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
        try:
            seen.add(json.loads(line)["date"])
        except Exception:
            pass
    return seen


def append_ledger(summary: dict) -> None:
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary) + "\n")


# ---------------------------------------------------------------------------
# Level memory update (Task 0.3)
# ---------------------------------------------------------------------------
def update_level_memory(rows: list[dict]) -> None:
    if MEMORY_PATH.exists():
        try:
            memory = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        except Exception:
            memory = {}
    else:
        memory = {}

    for row in rows:
        key = price_bucket(row["price"])
        entry = memory.get(key, {
            "price_bucket": float(key),
            "touch_count": 0,
            "respect_count": 0,
            "broken_count": 0,
            "last_seen": None,
            "hit_rate": None,
        })
        entry["last_seen"] = row["date"]
        if row["touched"]:
            entry["touch_count"] += 1
            if row["outcome"] == "RESPECT":
                entry["respect_count"] += 1
            elif row["outcome"] == "BREAK":
                entry["broken_count"] += 1
        if entry["touch_count"] >= 1:
            entry["hit_rate"] = round(entry["respect_count"] / entry["touch_count"], 4)
        memory[key] = entry

    MEMORY_PATH.write_text(json.dumps(memory, indent=2), encoding="utf-8")

    # Emit STATUS if any bucket reaches >=10 touches
    stable = [v for v in memory.values() if v["touch_count"] >= 10]
    if stable:
        print(f"  LEVEL_MEMORY: {len(stable)} buckets with >=10 touches; "
              f"best hit_rate={max(v['hit_rate'] or 0 for v in stable):.3f}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def run_day(d: dt.date, spy: pd.DataFrame, ledger_seen: set[str]) -> bool:
    d_str = d.isoformat()
    out_file = OUT_DIR / f"outcomes-{d_str}.jsonl"

    result = score_day(d, spy)
    if result is None:
        return False

    summary, rows = result["summary"], result["rows"]

    # Write per-day outcomes file
    with out_file.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    # Append to ledger if not already present
    if d_str not in ledger_seen:
        append_ledger(summary)
        ledger_seen.add(d_str)

    # Update level memory
    update_level_memory(rows)

    touch = summary["touch_rate"]
    resp = summary["respect_rate_of_touched"]
    resp_str = f"{resp:.3f}" if resp is not None else "n/a"
    print(f"  {d_str}: n={summary['n_levels']}  touch={touch:.3f}  respect={resp_str}"
          f"  src={summary['source']}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Score level outcomes for one day or backfill range.")
    parser.add_argument("--date", help="Single date YYYY-MM-DD")
    parser.add_argument("--backfill", nargs=2, metavar=("START", "END"),
                        help="Backfill START END (inclusive, YYYY-MM-DD)")
    args = parser.parse_args()

    print("Loading SPY data...")
    spy = load_spy()
    print(f"  Loaded {len(spy):,} bars {spy['date'].min()} -> {spy['date'].max()}")

    ledger_seen = _ledger_dates()

    if args.backfill:
        start = dt.date.fromisoformat(args.backfill[0])
        end = dt.date.fromisoformat(args.backfill[1])
        trading_days = sorted(d for d in spy["date"].unique() if start <= d <= end)
        print(f"Backfilling {len(trading_days)} days ({start} -> {end})...")
        n_ok = 0
        for d in trading_days:
            if run_day(d, spy, ledger_seen):
                n_ok += 1
        print(f"\nBackfill done: {n_ok}/{len(trading_days)} days scored")

    elif args.date:
        d = dt.date.fromisoformat(args.date)
        run_day(d, spy, ledger_seen)

    else:
        # Default: today (or most recent trading day in data)
        today = dt.date.today()
        available = sorted(spy["date"].unique())
        d = today if today in available else available[-1]
        print(f"Scoring {d}...")
        run_day(d, spy, ledger_seen)

    # Summary
    all_lines = []
    if LEDGER_PATH.exists():
        for line in LEDGER_PATH.read_text(encoding="utf-8").splitlines():
            try:
                all_lines.append(json.loads(line))
            except Exception:
                pass

    if all_lines:
        all_touch = [l["touch_rate"] for l in all_lines if l.get("touch_rate") is not None]
        all_resp = [l["respect_rate_of_touched"] for l in all_lines if l.get("respect_rate_of_touched") is not None]
        print(f"\nLEDGER TOTAL: {len(all_lines)} days")
        print(f"  avg touch rate:   {np.mean(all_touch):.3f}")
        print(f"  avg respect rate: {np.mean(all_resp):.3f}")


def get_level_prior(price: float) -> dict | None:
    """Read helper: return cumulative stats for a price bucket from level-memory.json.

    Returns dict with {touch_count, respect_count, broken_count, hit_rate} or None.
    Intended for future use by premarket (Phase 3, not yet wired in production).
    """
    if not MEMORY_PATH.exists():
        return None
    try:
        memory = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
        return memory.get(price_bucket(price))
    except Exception:
        return None


if __name__ == "__main__":
    main()

"""Merge the full-history data file (through 2026-07-14) with the incremental rolling
window file (2026-05-19 to 2026-07-22) into a single extended full-history dataset, for
the engine-fullhist-replay-2026-07-23 mission (analysis/recommendations/engine-fullhist-
replay-2026-07-23.json). Mirrors merge_extend_data.py's established pattern exactly.

Output:
  backtest/data/spy_5m_2025-01-01_2026-07-22.csv
  backtest/data/vix_5m_2025-01-01_2026-07-22.csv

Deduplication: on timestamp_et (keeps last occurrence -- the incremental/rolling file
wins in the overlap window, since it is the more-recently re-fetched source).

Data only. No trading-path code touched.
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "backtest" / "data"


def merge(sym: str, base_name: str, incr_name: str, out_name: str, expect_substr: str) -> None:
    base = DATA / base_name
    incr = DATA / incr_name
    out = DATA / out_name

    print(f"Loading {base.name} ...")
    df_base = pd.read_csv(base)
    print(f"  {len(df_base)} rows, range {df_base['timestamp_et'].min()} .. {df_base['timestamp_et'].max()}")

    print(f"Loading {incr.name} ...")
    df_incr = pd.read_csv(incr)
    print(f"  {len(df_incr)} rows, range {df_incr['timestamp_et'].min()} .. {df_incr['timestamp_et'].max()}")

    combined = pd.concat([df_base, df_incr], ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates(subset=["timestamp_et"], keep="last")
    combined = combined.sort_values("timestamp_et").reset_index(drop=True)
    after = len(combined)
    print(f"  merged: {before} -> {after} rows (removed {before - after} dupes)")

    max_ts = combined["timestamp_et"].max()
    min_ts = combined["timestamp_et"].min()
    print(f"  date range: {min_ts[:10]} to {max_ts[:10]}")
    assert expect_substr in max_ts, f"merge didn't extend to expected date: max={max_ts}"

    # Parity check: parse via pandas datetime to confirm strictly monotonic increasing
    # (catches any string-sort/tz-format mismatch silently producing an out-of-order file).
    ts_parsed = pd.to_datetime(combined["timestamp_et"], utc=True)
    n_non_monotonic = int((ts_parsed.diff().dt.total_seconds().dropna() < 0).sum())
    print(f"  monotonicity check: {n_non_monotonic} out-of-order rows (must be 0)")
    assert n_non_monotonic == 0, f"{sym}: merged file is NOT chronologically monotonic after sort"

    combined.to_csv(out, index=False)
    print(f"  wrote {out.relative_to(ROOT)}  ({after} rows)")


if __name__ == "__main__":
    merge("spy", "spy_5m_2025-01-01_2026-07-14.csv", "spy_5m_2026-05-19_2026-07-22.csv",
          "spy_5m_2025-01-01_2026-07-22.csv", "2026-07-22")
    merge("vix", "vix_5m_2025-01-01_2026-07-08.csv", "vix_5m_2026-05-19_2026-07-22.csv",
          "vix_5m_2025-01-01_2026-07-22.csv", "2026-07-22")
    print("\nDone. Full-history window: 2025-01-02 to 2026-07-22.")

"""FINRA daily short-sale-volume vs SPY next-day return -- first-pass pre-registered screen.

Source chef item: strategy/candidates/_chef-inbox/2026-07-14-prospector-finra-daily-short-sale-volume-aggregated.md
Pre-registration (frozen BEFORE running): analysis/recommendations/finra-short-volume-preregistration.json

Pure functions are unit-testable without network access; `main()` does the real
fetch + full pipeline and is exercised by a live smoke test only (network-gated).
"""
from __future__ import annotations

import datetime as dt
import io
import json
import random
from pathlib import Path

import pandas as pd

from backtest.lib.http_fetch import HttpFetchBlocked, fetch_url_text

REPO_ROOT = Path(__file__).resolve().parents[2]
FINRA_URL_TMPL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ymd}.txt"
PREREG_PATH = REPO_ROOT / "analysis" / "recommendations" / "finra-short-volume-preregistration.json"
OUTPUT_PATH = REPO_ROOT / "analysis" / "recommendations" / "finra-short-volume-2026-07-22.json"

SPY_CACHE_FILES = [
    REPO_ROOT / "backtest" / "data" / "spy_5m_2025-01-01_2026-07-14.csv",
    REPO_ROOT / "backtest" / "data" / "spy_5m_2026-05-19_2026-07-22.csv",
]


def load_spy_daily_closes() -> pd.DataFrame:
    """Merge the cached 5m SPY frames and collapse to one row per trading day
    (last bar of the day = close). No look-ahead: each day's close is only the
    close of THAT day's own bars."""
    frames = []
    for p in SPY_CACHE_FILES:
        if p.exists():
            df = pd.read_csv(p)
            df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
            frames.append(df)
    if not frames:
        raise FileNotFoundError("no SPY 5m cache files found")
    df = pd.concat(frames).drop_duplicates(subset="timestamp_et").sort_values("timestamp_et")
    df["date"] = df["timestamp_et"].dt.date
    daily = df.groupby("date").agg(close=("close", "last")).reset_index()
    return daily


def fetch_finra_short_ratio(
    date: dt.date, symbol: str = "SPY", timeout: float = 15.0, raise_on_block: bool = False
) -> float | None:
    """Fetch ONE day's FINRA Reg SHO short-volume file and return SPY's
    ShortVolume/TotalVolume ratio, or None if unavailable (holiday/no file/symbol
    missing). Fails open by default -- never raises -- via the shared
    `backtest.lib.http_fetch.fetch_url_text` helper (browser-like User-Agent by
    default; FINRA's CDN 403s the bare urllib default UA, see L241).

    Set `raise_on_block=True` to instead propagate `HttpFetchBlocked` on a 403/429
    -- used by `main()`'s loop to detect a SYSTEMATIC block across many dates
    rather than silently recording each blocked day as "no data" (L241)."""
    ymd = date.strftime("%Y%m%d")
    url = FINRA_URL_TMPL.format(ymd=ymd)
    try:
        raw = fetch_url_text(url, timeout=timeout)
    except HttpFetchBlocked:
        if raise_on_block:
            raise
        return None
    if raw is None:
        return None
    try:
        df = pd.read_csv(io.StringIO(raw), sep="|")
    except Exception:
        return None
    row = df[df["Symbol"] == symbol]
    if row.empty:
        return None
    total = float(row["TotalVolume"].iloc[0])
    if total <= 0:
        return None
    short = float(row["ShortVolume"].iloc[0])
    return short / total


def build_sample(daily_closes: pd.DataFrame, short_ratios: dict) -> pd.DataFrame:
    """Join short_ratio_t with next_day_return_t = (close_{t+1}-close_t)/close_t.
    Pure function, no network -- unit-testable with a synthetic frame + dict."""
    daily_closes = daily_closes.sort_values("date").reset_index(drop=True)
    rows = []
    for i in range(len(daily_closes) - 1):
        d = daily_closes.loc[i, "date"]
        d_next = daily_closes.loc[i + 1, "date"]
        ratio = short_ratios.get(d)
        if ratio is None:
            continue
        close_t = daily_closes.loc[i, "close"]
        close_next = daily_closes.loc[i + 1, "close"]
        next_ret = (close_next - close_t) / close_t
        rows.append({"date": d, "next_date": d_next, "short_ratio": ratio, "next_day_return": next_ret})
    return pd.DataFrame(rows)


def median_split_test(sample: pd.DataFrame, n_perm: int = 5000, seed: int = 42) -> dict:
    """Median-split HIGH vs LOW short_ratio, compare mean next_day_return,
    two-sided permutation test on the difference of means. Pure function."""
    if sample.empty:
        return {"n": 0, "error": "empty sample"}
    med = sample["short_ratio"].median()
    high = sample[sample["short_ratio"] >= med]["next_day_return"].to_numpy()
    low = sample[sample["short_ratio"] < med]["next_day_return"].to_numpy()
    n_high, n_low = len(high), len(low)
    if n_high == 0 or n_low == 0:
        return {"n": len(sample), "error": "one side empty after median split"}
    obs_diff = float(high.mean() - low.mean())

    all_vals = sample["next_day_return"].to_numpy()
    n = len(all_vals)
    rng = random.Random(seed)
    count_ge = 0
    idx = list(range(n))
    for _ in range(n_perm):
        rng.shuffle(idx)
        perm_high = all_vals[idx[:n_high]]
        perm_low = all_vals[idx[n_high:]]
        perm_diff = perm_high.mean() - perm_low.mean()
        if abs(perm_diff) >= abs(obs_diff):
            count_ge += 1
    p_value = count_ge / n_perm

    return {
        "n": len(sample),
        "n_high": n_high,
        "n_low": n_low,
        "mean_return_high_short_ratio": float(high.mean()),
        "mean_return_low_short_ratio": float(low.mean()),
        "observed_diff_high_minus_low": obs_diff,
        "hypothesis_direction_confirmed": obs_diff < 0,
        "permutation_p_value": p_value,
        "n_permutations": n_perm,
        "underpowered": n_high < 15 or n_low < 15,
    }


def verdict_from_result(result: dict) -> str:
    if result.get("error"):
        return "KILL_DATA_INSUFFICIENT"
    if result["hypothesis_direction_confirmed"] and result["permutation_p_value"] < 0.05:
        return "PASS_FIRST_SCREEN"
    return "KILL"


def main() -> dict:
    daily = load_spy_daily_closes()
    # bound the fetch: last 65 trading days that have a "next day" available
    candidate_dates = list(daily["date"])[-70:-1]  # exclude today (no next-day yet)
    short_ratios = {}
    n_blocked = 0
    for d in candidate_dates:
        try:
            r = fetch_finra_short_ratio(d, raise_on_block=True)
        except HttpFetchBlocked:
            n_blocked += 1
            continue
        if r is not None:
            short_ratios[d] = r

    # L241 guard: a systematic 403/429 block looks identical to "no data" unless
    # surfaced distinctly -- if MOST attempted dates came back blocked (not just
    # a stray holiday/rate-limit blip), this is a fetcher-is-blocked situation,
    # not a genuinely-empty data source. Flag it loudly instead of quietly
    # reporting a near-zero sample as if the hypothesis had been tested.
    fetcher_systematically_blocked = bool(candidate_dates) and n_blocked >= 0.5 * len(candidate_dates)

    sample = build_sample(daily[daily["date"].isin(candidate_dates + [candidate_dates[-1]])] if candidate_dates else daily, short_ratios)
    # simpler + correct: just use full daily frame, build_sample already looks up next-day internally
    sample = build_sample(daily, short_ratios)
    result = median_split_test(sample)
    verdict = "KILL_FETCHER_BLOCKED" if fetcher_systematically_blocked else verdict_from_result(result)

    output = {
        "study_id": "finra-short-volume-spy-2026-07-22",
        "run_at_et": dt.datetime.now().isoformat(),
        "n_dates_attempted": len(candidate_dates),
        "n_dates_with_finra_data": len(short_ratios),
        "n_dates_blocked_403_429": n_blocked,
        "fetcher_systematically_blocked": fetcher_systematically_blocked,
        "result": result,
        "verdict": verdict,
    }
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, default=str))
    return output


if __name__ == "__main__":
    out = main()
    print(json.dumps(out, indent=2, default=str))

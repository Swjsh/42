"""H-edge-capture INDEPENDENT SAMPLE — J's real-money historical trades
(analysis/j-webull/trades-normalized.csv, 1,099 rows), replicating the
engine-trade lead from h_edge_capture_tape.py / h_edge_capture_dayclustered.py
("THE ONE THAT SURVIVED", markdown/trading-knowledge/microstructure-informed-flow.md
Section 4 H1): does the SIP tape in the 5 minutes before entry (big_share_300s
etc.) separate J's real winners from his real losers?

Scope per task spec:
  - Filter trades-normalized.csv to underlying in {SPY, SPX, SPXW} and
    entry_ts_et within RTH 09:30-15:55 ET.
  - SPX/SPXW have no listed tape -> SPY SIP tape is used as the flow proxy for
    ALL rows in this study (stated here and in the output JSON; this is a
    deliberate proxy, not a bug).
  - Direction sign: bias bull=+1 / bear=-1, falling back to right C/P (C=+1,
    P=-1) when bias is missing/blank.
  - Reuses compute_features / auc_score / shuffle_null_95th / tercile_pnl /
    spearman_corr from h_edge_capture_tape.py (imported, not reimplemented)
    and the day-demeaned / between-day / within-day-permutation logic pattern
    from h_edge_capture_dayclustered.py (reimplemented inline here since that
    script is a linear one-off, not an importable module — same formulas).
  - Tape fetch: backtest/tools/fetch_sip_tape.py fetch_trades/fetch_quotes/
    sign_trades, on-disk cached, ~3s per uncovered window. No whole-day-cache
    shortcut here (this sample's dates don't overlap the engine's cached
    days) - every window is fetched tight [entry-300s, entry).

Ownership: this file + analysis/recommendations/h-edge-capture-jreal.json are
the ONLY artifacts this script owns. Does not modify h_edge_capture_tape.py or
fetch_sip_tape.py (read-only imports only).

No tuning after seeing outcomes. Splits and features fixed by this docstring
before the run.
"""

from __future__ import annotations

import csv
import json
import sys
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from h_edge_capture_tape import (  # noqa: E402  (READ-ONLY reuse, per task spec)
    compute_features,
    auc_score,
    shuffle_null_95th,
    tercile_pnl,
    spearman_corr,
    get_window_signed_tape,
)

ET = ZoneInfo("America/New_York")
UTC = timezone.utc
SYMBOL = "SPY"

TRADES_CSV = (
    Path(__file__).resolve().parents[2] / "analysis" / "j-webull" / "trades-normalized.csv"
)
OUT_PATH = (
    Path(__file__).resolve().parents[2]
    / "analysis"
    / "recommendations"
    / "h-edge-capture-jreal.json"
)

FEATURES = [
    "sv_share_60s",
    "sv_share_300s",
    "big_share_60s",
    "big_share_300s",
    "absorb_300s",
    "ret_sign_300s",
]
PRIMARY_FEATURE = "big_share_300s"

N_SHUFFLE = 2000
RNG_SEED = 42

RTH_START = (9, 30)
RTH_END = (15, 55)
ELIGIBLE_UNDERLYINGS = {"SPY", "SPX", "SPXW"}


# --------------------------------------------------------------------------------
# Loading + filtering
# --------------------------------------------------------------------------------


@dataclass
class JTrade:
    episode_id: str
    entry_dt_et: datetime
    underlying: str
    dir_sign: int
    dir_source: str
    pnl: float
    ret_pct: float | None
    is_0dte: bool
    is_family: bool
    bias: str
    size_band: str
    vwap_side: str
    ctx_ok: str


def _parse_bool(s: str) -> bool:
    return (s or "").strip().lower() == "true"


def load_jreal_trades(path: Path) -> tuple[list[JTrade], dict]:
    """Load + filter trades-normalized.csv. Returns (trades, skip_counts)."""
    skip_counts = {
        "total_rows": 0,
        "wrong_underlying": 0,
        "bad_timestamp": 0,
        "outside_rth": 0,
        "no_direction_signal": 0,
        "missing_pnl": 0,
        "kept": 0,
    }
    trades: list[JTrade] = []
    with open(path, encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            skip_counts["total_rows"] += 1
            underlying = (row.get("underlying") or "").strip().upper()
            if underlying not in ELIGIBLE_UNDERLYINGS:
                skip_counts["wrong_underlying"] += 1
                continue

            entry_raw = (row.get("entry_ts_et") or "").strip()
            try:
                entry_dt_et = datetime.strptime(entry_raw, "%Y-%m-%d %H:%M:%S").replace(tzinfo=ET)
            except ValueError:
                skip_counts["bad_timestamp"] += 1
                continue

            t = (entry_dt_et.hour, entry_dt_et.minute)
            if not (RTH_START <= t <= RTH_END):
                skip_counts["outside_rth"] += 1
                continue

            bias = (row.get("bias") or "").strip().lower()
            right = (row.get("right") or "").strip().upper()
            dir_sign = 0
            dir_source = "none"
            if bias == "bull":
                dir_sign, dir_source = 1, "bias"
            elif bias == "bear":
                dir_sign, dir_source = -1, "bias"
            elif right == "C":
                dir_sign, dir_source = 1, "right"
            elif right == "P":
                dir_sign, dir_source = -1, "right"
            if dir_sign == 0:
                skip_counts["no_direction_signal"] += 1
                continue

            pnl_raw = (row.get("pnl") or "").strip()
            if not pnl_raw:
                skip_counts["missing_pnl"] += 1
                continue
            try:
                pnl = float(pnl_raw)
            except ValueError:
                skip_counts["missing_pnl"] += 1
                continue

            ret_raw = (row.get("ret_pct") or "").strip()
            ret_pct = float(ret_raw) if ret_raw else None

            trades.append(
                JTrade(
                    episode_id=row.get("episode_id", ""),
                    entry_dt_et=entry_dt_et,
                    underlying=underlying,
                    dir_sign=dir_sign,
                    dir_source=dir_source,
                    pnl=pnl,
                    ret_pct=ret_pct,
                    is_0dte=_parse_bool(row.get("is_0dte", "")),
                    is_family=_parse_bool(row.get("is_family", "")),
                    bias=bias,
                    size_band=(row.get("size_band") or "").strip(),
                    vwap_side=(row.get("vwap_side") or "").strip().lower(),
                    ctx_ok=(row.get("ctx_ok") or "").strip(),
                )
            )
            skip_counts["kept"] += 1
    return trades, skip_counts


def entry_ns(dt_et: datetime) -> int:
    return int(dt_et.astimezone(UTC).timestamp() * 1_000_000_000)


# --------------------------------------------------------------------------------
# Day-clustered stats (same formulas as h_edge_capture_dayclustered.py)
# --------------------------------------------------------------------------------


def within_day_permutation_p(
    fv: np.ndarray, labels: np.ndarray, dates: np.ndarray, real_auc: float, n_shuffle: int, rng: np.random.Generator
) -> tuple[float | None, float | None]:
    """Within-day label permutation: shuffle winner labels ONLY within each day.
    Returns (null_95th, p_value) where p = P(null_auc >= real_auc)."""
    df = pd.DataFrame({"f": fv, "lab": labels, "date": dates})
    if df["date"].nunique() < 1 or len(df) < 4:
        return None, None
    nulls = []
    for _ in range(n_shuffle):
        shuffled = df.groupby("date")["lab"].transform(lambda s: rng.permutation(s.to_numpy()))
        a = auc_score(df["f"].to_numpy(), shuffled.to_numpy())
        if a is not None:
            nulls.append(a)
    if not nulls:
        return None, None
    nulls_arr = np.array(nulls)
    return float(np.percentile(nulls_arr, 95)), float((nulls_arr >= real_auc).mean())


def day_demeaned_spearman(fv: np.ndarray, labels: np.ndarray, dates: np.ndarray) -> float | None:
    df = pd.DataFrame({"f": fv, "lab": labels, "date": dates})
    if len(df) < 4:
        return None
    fd = df["f"] - df.groupby("date")["f"].transform("mean")
    ld = df["lab"] - df.groupby("date")["lab"].transform("mean")
    if fd.std() == 0 or ld.std() == 0:
        return None
    return float(pd.Series(fd).rank().corr(pd.Series(ld).rank()))


def between_day_spearman(fv: np.ndarray, labels: np.ndarray, dates: np.ndarray) -> float | None:
    df = pd.DataFrame({"f": fv, "lab": labels, "date": dates})
    g = df.groupby("date").agg(fm=("f", "mean"), wr=("lab", "mean"))
    if len(g) < 3 or g["fm"].std() == 0 or g["wr"].std() == 0:
        return None
    rho, _p = stats.spearmanr(g["fm"], g["wr"])
    return float(rho) if not np.isnan(rho) else None


def top5_day_share_of_winners(labels: np.ndarray, dates: np.ndarray) -> tuple[float | None, int]:
    df = pd.DataFrame({"lab": labels, "date": dates})
    total_winners = int(df["lab"].sum())
    n_days = int(df["date"].nunique())
    if total_winners == 0:
        return None, n_days
    by_day = df.groupby("date")["lab"].sum().sort_values(ascending=False)
    top5 = float(by_day.head(5).sum() / total_winners)
    return top5, n_days


# --------------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------------


def build_feature_rows(trades: list[JTrade]) -> tuple[pd.DataFrame, list[dict]]:
    rows: list[dict] = []
    failures: list[dict] = []
    total = len(trades)
    t_start = time.time()
    for n, tr in enumerate(trades, 1):
        try:
            t_ns = entry_ns(tr.entry_dt_et)
            window = get_window_signed_tape(tr.entry_dt_et.strftime("%Y-%m-%d"), t_ns)
            if window.empty:
                failures.append(
                    {
                        "episode_id": tr.episode_id,
                        "entry": tr.entry_dt_et.isoformat(),
                        "reason": "empty_window",
                    }
                )
                continue
            feats = compute_features(window, t_ns, tr.dir_sign)
            rows.append(
                {
                    "episode_id": tr.episode_id,
                    "date": tr.entry_dt_et.strftime("%Y-%m-%d"),
                    "underlying": tr.underlying,
                    "bias": tr.bias,
                    "dir_source": tr.dir_source,
                    "is_0dte": tr.is_0dte,
                    "is_family": tr.is_family,
                    "size_band": tr.size_band,
                    "vwap_side": tr.vwap_side,
                    "pnl": tr.pnl,
                    "ret_pct": tr.ret_pct,
                    "winner": 1 if tr.pnl > 0 else 0,
                    **feats,
                }
            )
        except Exception as exc:  # noqa: BLE001 - must count, never silently skip
            failures.append(
                {
                    "episode_id": tr.episode_id,
                    "entry": tr.entry_dt_et.isoformat(),
                    "reason": f"{type(exc).__name__}: {exc}",
                }
            )
            print(f"[h-edge-capture-jreal] FAILED {tr.episode_id} {tr.entry_dt_et}: {exc}", flush=True)
            traceback.print_exc()
        if n % 10 == 0 or n == total:
            elapsed = time.time() - t_start
            print(
                f"[h-edge-capture-jreal] {n}/{total} processed ({elapsed:.0f}s elapsed), "
                f"{len(rows)} covered, {len(failures)} failures",
                flush=True,
            )
    return pd.DataFrame(rows), failures


def analyze_split(df: pd.DataFrame, rng: np.random.Generator) -> dict:
    n = len(df)
    labels = df["winner"].to_numpy()
    pnl = df["pnl"].to_numpy()
    dates = df["date"].to_numpy()
    top5_share, n_days = top5_day_share_of_winners(labels, dates)

    feat_results = {}
    for feat in FEATURES:
        fv_full = df[feat].to_numpy(dtype=float)
        mask = ~np.isnan(fv_full)
        n_valid = int(mask.sum())
        if n_valid < 6:
            feat_results[feat] = {"n_valid": n_valid, "insufficient_n": True}
            continue
        fv = fv_full[mask]
        lb = labels[mask]
        pv = pnl[mask]
        dt_ = dates[mask]

        real_auc = auc_score(fv, lb)
        null_95 = shuffle_null_95th(fv, lb, N_SHUFFLE, rng)
        wd_null95, wd_p = within_day_permutation_p(fv, lb, dt_, real_auc, N_SHUFFLE, rng) if real_auc is not None else (None, None)
        rho_within = day_demeaned_spearman(fv, lb, dt_)
        rho_between = between_day_spearman(fv, lb, dt_)
        tercile = tercile_pnl(fv, pv)
        spearman = spearman_corr(fv, pv)

        feat_results[feat] = {
            "n_valid": n_valid,
            "auc": real_auc,
            "cross_trade_null_auc_95th_pctile": null_95,
            "beats_cross_trade_null": (real_auc is not None and null_95 is not None and real_auc > null_95),
            "within_day_null_auc_95th_pctile": wd_null95,
            "p_within_day_permutation": wd_p,
            "beats_within_day_null": (wd_p is not None and wd_p < 0.05),
            "rho_day_demeaned": rho_within,
            "rho_between_day": rho_between,
            "tercile_pnl": tercile,
            "spearman_pnl": spearman,
        }
        print(
            f"[h-edge-capture-jreal]   {feat:16s} n={n_valid:4d} AUC={real_auc if real_auc is None else round(real_auc,4)} "
            f"wd_p={wd_p if wd_p is None else round(wd_p,4)} rho_wd={rho_within if rho_within is None else round(rho_within,4)} "
            f"rho_bd={rho_between if rho_between is None else round(rho_between,4)}",
            flush=True,
        )
    return {
        "n": n,
        "n_days": n_days,
        "n_winners": int(labels.sum()),
        "top5_day_share_of_winners": top5_share,
        "features": feat_results,
    }


def main() -> int:
    t_start = time.time()
    trades, skip_counts = load_jreal_trades(TRADES_CSV)
    print(f"[h-edge-capture-jreal] filter summary: {skip_counts}", flush=True)
    print(f"[h-edge-capture-jreal] {len(trades)} eligible trades (SPY/SPX/SPXW, RTH, has direction+pnl)", flush=True)

    df, failures = build_feature_rows(trades)
    covered = len(df)
    total_eligible = len(trades)
    print(
        f"[h-edge-capture-jreal] coverage: {covered}/{total_eligible} eligible trades covered "
        f"({total_eligible - covered} uncovered)",
        flush=True,
    )

    rng = np.random.default_rng(RNG_SEED)

    splits: dict[str, pd.DataFrame] = {"ALL": df}
    if not df.empty:
        for b in sorted(df["bias"].dropna().unique()):
            if b:
                splits[f"bias={b}"] = df[df["bias"] == b]
        for v in [True, False]:
            splits[f"is_0dte={v}"] = df[df["is_0dte"] == v]
        for v in [True, False]:
            splits[f"is_family={v}"] = df[df["is_family"] == v]
        # size_band: 1-2 lot vs larger, per C31
        splits["size_band=1-2"] = df[df["size_band"] == "1-2"]
        splits["size_band=3+"] = df[~df["size_band"].isin(["1-2", ""])]
        for side in sorted(df["vwap_side"].dropna().unique()):
            if side:
                splits[f"vwap_side={side}"] = df[df["vwap_side"] == side]

    results = {}
    n_cells = 0
    for name, sub in splits.items():
        if sub.empty:
            continue
        print(f"[h-edge-capture-jreal] SPLIT {name}: n={len(sub)}", flush=True)
        results[name] = analyze_split(sub, rng)
        n_cells += sum(1 for f in results[name]["features"].values() if not f.get("insufficient_n"))

    primary_auc = results.get("ALL", {}).get("features", {}).get(PRIMARY_FEATURE, {}).get("auc")
    primary_p = results.get("ALL", {}).get("features", {}).get(PRIMARY_FEATURE, {}).get("p_within_day_permutation")
    replicates = (
        primary_auc is not None
        and primary_auc > 0.5
        and primary_p is not None
        and primary_p < 0.05
    )
    verdict = (
        f"REPLICATES on ALL split: {PRIMARY_FEATURE} AUC={round(primary_auc,4) if primary_auc is not None else None}, "
        f"within-day-permutation p={round(primary_p,4) if primary_p is not None else None} < 0.05, same direction as engine study"
        if replicates
        else f"NULL on ALL split: {PRIMARY_FEATURE} AUC={round(primary_auc,4) if primary_auc is not None else None} "
        f"does not clear AUC>0.5 with within-day p<0.05 on J's real trades -- the engine-trade lead does NOT "
        "replicate on this independent sample as tested (a fully acceptable outcome: it would mean the lead is a "
        "conditional-population artifact of the engine's own entry filters, not a general SPY tape property)"
    )

    output = {
        "meta": {
            "generated_at_utc": datetime.now(tz=UTC).isoformat(),
            "trades_csv": str(TRADES_CSV),
            "sample": "J's real-money historical trades (INDEPENDENT of engine paper trades)",
            "features": FEATURES,
            "primary_feature": PRIMARY_FEATURE,
            "n_shuffle": N_SHUFFLE,
            "rng_seed": RNG_SEED,
            "rth_window_et": "09:30-15:55",
            "eligible_underlyings": sorted(ELIGIBLE_UNDERLYINGS),
        },
        "proxy_caveat": (
            "SPX/SPXW options have no listed tape. SPY SIP tape is used as the flow proxy for ALL "
            "trades in this study, including SPX/SPXW rows, since SPY and SPX/SPXW track the same "
            "underlying index/ETF pair intraday. This is a deliberate methodological choice, not an "
            "oversight, and weakens the read for any SPX/SPXW-only subsplit."
        ),
        "direction_sign_rule": "bias bull=+1/bear=-1, fallback to right C=+1/P=-1 when bias missing/blank",
        "filter_summary": skip_counts,
        "coverage": {
            "eligible_trades": total_eligible,
            "covered_trades": covered,
            "uncovered_trades": total_eligible - covered,
            "failures": failures,
        },
        "disclosure": {
            "n_feature_x_split_cells": n_cells,
            "multiple_testing_caveat": (
                f"{n_cells} feature x split cells tested; splits overlap heavily (e.g. bias and "
                "size_band partitions are not independent of each other or of ALL). No single cell's "
                "p-value should be read as significant without correcting for this."
            ),
            "conditional_population_caveat": (
                "J's real trades are pre-selected by his own discretionary judgment (playbook setups, "
                "levels, and market read), an entirely different selection process from the engine's "
                "mechanical filters. A replication here would be evidence the tape feature generalizes "
                "across selection processes; a null would be evidence the engine-trade lead is specific "
                "to the engine's own conditional population."
            ),
            "single_source_tape_caveat": (
                "All tape is SPY SIP regardless of the traded underlying (see proxy_caveat)."
            ),
        },
        "results_by_split": results,
        "verdict": verdict,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, sort_keys=False, default=str)

    print(f"[h-edge-capture-jreal] wrote {OUT_PATH}", flush=True)
    print(f"[h-edge-capture-jreal] VERDICT: {verdict}", flush=True)
    print(f"[h-edge-capture-jreal] total elapsed: {time.time() - t_start:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""multi_levels_transplant.py -- give the fork's trigger PRODUCTION-GRADE levels and re-measure.

ONE VARIABLE MOVES, and it is measured PAIRED: every symbol is replayed TWICE in the same
process, over the same bars, through the same code path, differing only in where levels come
from:

    arm FORK :  multi/lib/levels.compute_levels(window)   swing pivots + prior day/week +
                                                          round numbers, ATR-deduped
    arm PROD :  reconstruct_levels_asof(as_of=bar_i)      daily_context SHELVES + pivots +
                                                          PDH/PDL/PDC + intraday RTH/swing/
                                                          premarket extremes, tiered + sourced

Running both arms in one process is deliberate. Comparing arm PROD against remembered numbers
from a previous run would leave "was the baseline really comparable?" permanently open; a paired
run closes it, because everything except the level source is literally the same execution.

WHY. The calibration run (`spy_production_calibration.py`) showed the production trigger reading
curated levels hits 58.23% at +10min (n=881, +4.89 sigma) while the identical filter stack
reading fork levels hits 49.06% (n=7,489, -1.63 sigma). If levels are the missing input, arm
PROD recovers. If it does not, the signal family is dead for the third and final time.

SPY IS THE INTERNAL POSITIVE CONTROL and the most important row in the output. If SPY does not
recover, **the port is broken and this run says nothing about the other eight symbols** -- a
broken transplant and an absent edge are indistinguishable without it.

EVERY LOOP CONSTANT IS COPIED FROM STAGE A ON PURPOSE (WARMUP=220, LEVEL_REFRESH_BARS=12,
HORIZONS=(2,6,12), window=bars.iloc[:i+1], action in ENTER_BULL/ENTER_BEAR, forward return in
percent signed into the signal's direction, and NO extra session filter). Any of those changing
would be a second variable and would forfeit the attribution this whole run exists to establish.

Frozen decision rule: analysis/recommendations/prereg-multi-levels-transplant-2026-08-20.json
Headline horizon is +2 bars (10 min) and the primary channel is HIT RATE -- both set by
measurement on the independent production control population, both justified in the prereg
BEFORE any result here was seen.

CAUSALITY -- two independent guards, both required:
  * `reconstruct_levels` slices its own inputs to <= as_of_et (RED-proofed by
    test_reconstruct_levels_asof.py).
  * this harness only ever hands it `bars.iloc[:i+1]`, so a future bar cannot be in the frame.

READ-ONLY. Places nothing, arms nothing, writes no production state.

Run:  backtest/.venv/Scripts/python.exe backtest/tools/multi_levels_transplant.py
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from multi import core as mcore  # noqa: E402
from multi.lib import creds as mcreds  # noqa: E402
from multi.lib import levels as mlv  # noqa: E402
from multi.lib import signal as ms  # noqa: E402
from backtest.lib.reconstruct_levels_asof import reconstruct_levels  # noqa: E402

SYMBOLS = ["SPY", "QQQ", "IWM", "NVDA", "AAPL", "TSLA", "MSFT", "AMD", "GLD"]
CONTROL = "SPY"

# --- copied verbatim from multi_intraday_null_harness.py; changing any is a 2nd variable ---
HORIZONS = (2, 6, 12)
WARMUP = 220
LEVEL_REFRESH_BARS = 12
# -------------------------------------------------------------------------------------------

HEADLINE = 2          # +10 min, set by measurement on the production control (see prereg)
NULL_DRAWS = 200
SEED = 20260820
MULTI_DAY_TIERS = ("Carry", "Reference")


class TransplantError(RuntimeError):
    """Fail loud: an empty or short run must never be reported as a result."""


def _norm5m(df: pd.DataFrame) -> pd.DataFrame:
    out = df.reset_index()
    out.columns = [str(c).lower() for c in out.columns]
    tcol = next(c for c in out.columns if "time" in c or "date" in c)
    out = out.rename(columns={tcol: "timestamp_et"})
    out["timestamp_et"] = pd.to_datetime(out["timestamp_et"]).dt.tz_localize(None)
    return out[["timestamp_et", "open", "high", "low", "close", "volume"]]


def _norm_daily(df: pd.DataFrame) -> list[dict]:
    out = df.reset_index()
    out.columns = [str(c).lower() for c in out.columns]
    dcol = next(c for c in out.columns if "time" in c or "date" in c)
    return [{"date": pd.Timestamp(r[dcol]).strftime("%Y-%m-%d"), "o": float(r["open"]),
             "h": float(r["high"]), "l": float(r["low"]), "c": float(r["close"]),
             "v": float(r["volume"])} for _, r in out.iterrows()]


def _prod_levels(as_of, daily, hist5, spot, diag) -> tuple[list, list]:
    """Production-grade levels as-of this bar, split into active vs multi-day BY TIER -- the
    same two-bucket shape the fork's own compute_levels returns, so the call site is unchanged."""
    try:
        res = reconstruct_levels(as_of_et=as_of.to_pydatetime(), daily_bars=daily,
                                 five_min_df=hist5, spot=spot)
    except Exception as e:  # noqa: BLE001 -- counted and surfaced, never silently "no levels"
        diag["level_errors"] += 1
        diag.setdefault("level_error_sample", str(e)[:200])
        return [], []
    if not res.get("ok"):
        diag["level_not_ok"] += 1
        return [], []
    active, multi = [], []
    for lv in res.get("levels") or []:
        p = lv.get("price")
        if not isinstance(p, (int, float)):
            continue
        (multi if lv.get("tier") in MULTI_DAY_TIERS else active).append(float(p))
    diag["level_count_sum"] += len(active) + len(multi)
    diag["shelf_count_sum"] += sum(
        1 for lv in (res.get("levels") or []) if "SHELF" in str(lv.get("label") or ""))
    return active, multi


def replay(symbol: str, bars: pd.DataFrame, params: dict, arm: str,
           daily: list[dict] | None = None) -> tuple[list[dict], dict]:
    """Bar-by-bar replay. `arm` is 'fork' or 'prod' and selects ONLY the level source."""
    closes = [float(x) for x in bars["close"].to_numpy()]
    n = len(bars)
    max_h = max(HORIZONS)
    hist5 = _norm5m(bars) if arm == "prod" else None
    times = hist5["timestamp_et"].tolist() if hist5 is not None else None

    out: list[dict] = []
    diag = {"evaluated": 0, "level_errors": 0, "level_not_ok": 0, "signal_errors": 0,
            "level_count_sum": 0, "shelf_count_sum": 0, "level_refreshes": 0}
    lv_active, lv_multi, lv_at = None, None, -10**9

    for i in range(WARMUP, n - max_h):
        window = bars.iloc[: i + 1]                       # strictly up to and including bar i
        if lv_active is None or (i - lv_at) >= LEVEL_REFRESH_BARS:
            diag["level_refreshes"] += 1
            if arm == "fork":
                try:
                    lv_active, lv_multi = mlv.compute_levels(window)
                    lv_at = i
                except mlv.LevelError:
                    continue
            else:
                lv_active, lv_multi = _prod_levels(
                    times[i], daily, hist5.iloc[: i + 1], closes[i], diag)
                lv_at = i
        if not lv_active:
            continue
        diag["evaluated"] += 1
        try:
            sig = ms.build_signal(symbol, window, params=params,
                                  candidate_levels=lv_active,
                                  candidate_multi_day_levels=lv_multi)
        except (ms.SignalBuildError, ValueError):
            diag["signal_errors"] += 1
            continue

        action = str(sig.get("action") or "HOLD").upper()
        if action not in ("ENTER_BULL", "ENTER_BEAR"):
            continue
        sign = 1.0 if action == "ENTER_BULL" else -1.0
        base = closes[i]
        if base <= 0:
            continue
        rec = {"i": i, "direction": action, "ts": bars.index[i].isoformat(),
               "day": str(bars.index[i])[:10]}
        for h in HORIZONS:
            rec[f"fwd_{h}"] = round(sign * 100.0 * (closes[i + h] / base - 1.0), 5)
        out.append(rec)
    return out, diag


def summarize(sigs: list[dict]) -> dict:
    s: dict = {"n": len(sigs)}
    for h in HORIZONS:
        vals = [r[f"fwd_{h}"] for r in sigs if r.get(f"fwd_{h}") is not None]
        if not vals:
            s[f"h{h}"] = None
            continue
        hits = sum(1 for v in vals if v > 0)
        hr = 100.0 * hits / len(vals)
        se = math.sqrt(0.25 / len(vals)) * 100.0
        s[f"h{h}"] = {"n": len(vals), "hit_rate_pct": round(hr, 2),
                      "sigma": round((hr - 50.0) / se, 2) if se else None,
                      "mean_pct": round(sum(vals) / len(vals), 5)}
    return s


def random_null(sigs: list[dict], bars: pd.DataFrame, draws: int = NULL_DRAWS) -> dict:
    """Same count, same direction mix, same session population. Compared at MAX, never mean."""
    if not sigs:
        return {}
    rng = random.Random(SEED)
    closes = [float(x) for x in bars["close"].to_numpy()]
    total = len(closes)
    day_set = {r["day"] for r in sigs}
    pool = [i for i in range(WARMUP, total - max(HORIZONS))
            if str(bars.index[i])[:10] in day_set]
    if not pool:
        return {}
    dirs = [r["direction"] for r in sigs]
    per_h: dict[int, list[float]] = {h: [] for h in HORIZONS}
    for _ in range(draws):
        picks = [rng.choice(pool) for _ in range(len(sigs))]
        rng.shuffle(dirs)
        for h in HORIZONS:
            hits = tot = 0
            for i, d in zip(picks, dirs):
                base = closes[i]
                if base <= 0:
                    continue
                sign = 1.0 if d == "ENTER_BULL" else -1.0
                v = sign * (closes[i + h] / base - 1.0)
                tot += 1
                hits += 1 if v > 0 else 0
            if tot:
                per_h[h].append(100.0 * hits / tot)
    out = {}
    for h in HORIZONS:
        v = sorted(per_h[h])
        if v:
            out[f"h{h}"] = {"draws": len(v), "null_mean_hit": round(sum(v) / len(v), 2),
                            "null_max_hit": round(v[-1], 2)}
    return out


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--bars", type=int, default=4300)
    ap.add_argument("--symbols", type=str, default=",".join(SYMBOLS))
    ap.add_argument("--out", type=Path,
                    default=REPO / "analysis" / "multi-lane" / "levels-transplant.json")
    args = ap.parse_args(argv)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]

    params = json.loads((REPO / "automation" / "state" / "multi" / "params.json").read_text(encoding="utf-8"))
    c = mcreds.resolve(params)
    print(f"[transplant] fetching {len(symbols)} symbols ...", flush=True)
    f5 = mcore.fetch_bars_batch(c, symbols, "5Min", limit=args.bars)
    fd = mcore.fetch_bars_batch(c, symbols, "1Day", limit=200)

    report: dict = {
        "prereg": "analysis/recommendations/prereg-multi-levels-transplant-2026-08-20.json",
        "control": CONTROL, "headline_horizon_bars": HEADLINE,
        "design": "PAIRED -- both arms replayed in one process over identical bars; only the "
                  "level source differs.",
        "symbols": {},
    }

    for sym in symbols:
        b5, bd = f5.get(sym), fd.get(sym)
        if b5 is None or b5.empty or bd is None or bd.empty:
            report["symbols"][sym] = {"error": "no bars -- excluded, not imputed"}
            print(f"[transplant] {sym}: NO BARS -- excluded", flush=True)
            continue
        daily = _norm_daily(bd)
        entry: dict = {"bars_5m": len(b5), "bars_daily": len(daily), "arms": {}}
        for arm in ("fork", "prod"):
            sigs, diag = replay(sym, b5, params, arm, daily=daily if arm == "prod" else None)
            a: dict = {"signals": len(sigs), "diagnostics": diag}
            if sigs:
                a["summary"] = summarize(sigs)
                a["null"] = random_null(sigs, b5)
            entry["arms"][arm] = a
        report["symbols"][sym] = entry
        fk = ((entry["arms"]["fork"].get("summary") or {}).get(f"h{HEADLINE}") or {})
        pr = ((entry["arms"]["prod"].get("summary") or {}).get(f"h{HEADLINE}") or {})
        print(f"[transplant] {sym:5s} fork n={entry['arms']['fork']['signals']:5d} "
              f"hit={fk.get('hit_rate_pct','n/a')}   |   prod n={entry['arms']['prod']['signals']:5d} "
              f"hit={pr.get('hit_rate_pct','n/a')}", flush=True)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")

    print("\n" + "=" * 92)
    print("PAIRED TRANSPLANT -- hit rate at +10 min (headline). Only the level source differs.")
    print(f"{'SYM':<6}{'fork n':>8}{'fork hit':>10}{'prod n':>8}{'prod hit':>10}"
          f"{'delta':>9}{'sigma':>8}{'nullMAX':>10}  gate")
    for sym in symbols:
        e = report["symbols"].get(sym) or {}
        if "arms" not in e:
            print(f"{sym:<6}  {e.get('error')}")
            continue
        fk = (e["arms"]["fork"].get("summary") or {}).get(f"h{HEADLINE}")
        pr = (e["arms"]["prod"].get("summary") or {}).get(f"h{HEADLINE}")
        nl = (e["arms"]["prod"].get("null") or {}).get(f"h{HEADLINE}")
        if not pr:
            print(f"{sym:<6}{(fk or {}).get('n', 0):>8}{(fk or {}).get('hit_rate_pct', 0):>10}"
                  f"{'--':>8}{'no prod signals':>22}")
            continue
        d = pr["hit_rate_pct"] - fk["hit_rate_pct"] if fk else float("nan")
        gate = "BEATS_NULL_MAX" if (nl and pr["hit_rate_pct"] > nl["null_max_hit"]) else "fails"
        tag = "  <== CONTROL" if sym == CONTROL else ""
        print(f"{sym:<6}{(fk or {}).get('n',0):>8}{(fk or {}).get('hit_rate_pct',0):>10.2f}"
              f"{pr['n']:>8}{pr['hit_rate_pct']:>10.2f}{d:>+9.2f}{pr['sigma']:>8.2f}"
              f"{(nl or {}).get('null_max_hit', float('nan')):>10.2f}  {gate}{tag}")
    print("=" * 92)
    print(f"[transplant] wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

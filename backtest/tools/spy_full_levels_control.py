"""spy_full_levels_control.py -- the decisive control: does the FULL curated level stack
recover the fork's trigger on SPY?

WHY THIS RUN EXISTS. The paired transplant handed the fork's trigger levels from
`reconstruct_levels` alone and SPY got WORSE (48.90% vs the fork's own 51.08%). Per the frozen
prereg that is `CONTROL_FAILS_PORT_IS_BROKEN`, which forbids drawing any conclusion about the
other eight symbols and requires debugging the port instead. The port was in fact incomplete:
production composes FOUR level families and I had wired only the first.

    base     reconstruct_levels          shelves, pivots, PDH/PDL/PDC, intraday + premarket
    memory   memory_levels_asof          multi-day level memory (the G11 layer)
    priorday prior_day_levels            prior-session structure
    curated  snapshot_curated_levels     the ARCHIVED HUMAN/PIPELINE-CURATED key-levels

`level_records_asof` composes all four, then applies production's own two admission rules
(not expired relative to the AS-OF date, and |price - spot| <= ACTIVE_BAND).

WHAT THIS RUN CAN SETTLE. Three arms over identical SPY bars, identical filter stack, identical
scoring code -- only the level source differs:

    fork        multi/lib/levels.compute_levels     the home-made set
    prod_base   reconstruct_levels                  family 1 of 4  (already known: no recovery)
    prod_full   level_records_asof                  all 4 families

If prod_full recovers toward the 58.23% the production trigger achieves, **the curated stack is
the edge** -- and the honest consequence for other tickers is immediate and uncomfortable, since
`snapshot_curated_levels` reads ARCHIVED SPY SNAPSHOTS THAT EXIST FOR NO OTHER SYMBOL. That is
the pre-committed PARTIAL_SPY_ONLY outcome: the moat is the curation, and other names do not
have one yet.

If prod_full does NOT recover either, then levels are not the missing input, the transplant
thesis is dead, and the multi-lane verdict needs no amendment.

Either way this is a CONTROL on SPY only. It draws no conclusion about other symbols by design.

READ-ONLY. Places nothing, arms nothing.

Run:  backtest/.venv/Scripts/python.exe backtest/tools/spy_full_levels_control.py
"""
from __future__ import annotations

import json
import math
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
import backtest.tools.conviction_levels_asof as CLA  # noqa: E402

HORIZONS = (2, 6, 12)
HEADLINE = 2
WARMUP = 220
LEVEL_REFRESH_BARS = 12
MULTI_DAY_TIERS = ("Carry", "Reference")
OUT = REPO / "analysis" / "multi-lane" / "spy-full-levels-control.json"


def _norm5m(df: pd.DataFrame) -> pd.DataFrame:
    out = df.reset_index()
    out.columns = [str(c).lower() for c in out.columns]
    tcol = next(c for c in out.columns if "time" in c or "date" in c)
    out = out.rename(columns={tcol: "timestamp_et"})
    out["timestamp_et"] = pd.to_datetime(out["timestamp_et"]).dt.tz_localize(None)
    out = out[["timestamp_et", "open", "high", "low", "close", "volume"]].copy()
    # conviction_levels_asof.prior_day_levels indexes df5["date"] and memory/confluence paths
    # expect "hm". Omitting them made level_records_asof raise on 89 of 477 refreshes in the
    # first run -- errors that were COUNTED but that I failed to print, so a broken arm reported
    # a plausible-looking 47.10%. Supplying the columns its contract actually requires.
    out["date"] = out["timestamp_et"].dt.strftime("%Y-%m-%d")
    out["hm"] = out["timestamp_et"].dt.strftime("%H:%M")
    return out


def _norm_daily(df: pd.DataFrame) -> list[dict]:
    out = df.reset_index()
    out.columns = [str(c).lower() for c in out.columns]
    dcol = next(c for c in out.columns if "time" in c or "date" in c)
    return [{"date": pd.Timestamp(r[dcol]).strftime("%Y-%m-%d"), "o": float(r["open"]),
             "h": float(r["high"]), "l": float(r["low"]), "c": float(r["close"]),
             "v": float(r["volume"])} for _, r in out.iterrows()]


def replay(bars: pd.DataFrame, params: dict, arm: str, daily: list) -> tuple[list, dict]:
    closes = [float(x) for x in bars["close"].to_numpy()]
    n = len(bars)
    hist5 = _norm5m(bars)
    times = hist5["timestamp_et"].tolist()
    out, diag = [], {"evaluated": 0, "lvl_err": 0, "lvl_empty": 0, "lvl_sum": 0,
                     "curated_hits": 0, "refreshes": 0}
    lv_active, lv_multi, lv_at = None, None, -10**9

    for i in range(WARMUP, n - max(HORIZONS)):
        window = bars.iloc[: i + 1]
        if lv_active is None or (i - lv_at) >= LEVEL_REFRESH_BARS:
            diag["refreshes"] += 1
            lv_at = i
            if arm == "fork":
                try:
                    lv_active, lv_multi = mlv.compute_levels(window)
                except mlv.LevelError:
                    lv_active, lv_multi = [], []
            else:
                as_of = times[i].to_pydatetime()
                spot = closes[i]
                sub = hist5.iloc[: i + 1]
                try:
                    if arm == "prod_base":
                        from backtest.lib.reconstruct_levels_asof import reconstruct_levels
                        res = reconstruct_levels(as_of_et=as_of, daily_bars=daily,
                                                 five_min_df=sub, spot=spot)
                        recs = res.get("levels") or [] if res.get("ok") else []
                    else:
                        r = CLA.level_records_asof(as_of=as_of, spot=spot, df5=sub,
                                                   daily_bars=daily)
                        recs = r.get("records") or []
                        if any("snapshot" in str(x.get("source", "")).lower()
                               or x.get("_from_snapshot") for x in recs):
                            diag["curated_hits"] += 1
                    lv_active, lv_multi = [], []
                    for lv in recs:
                        p = lv.get("price")
                        if not isinstance(p, (int, float)):
                            continue
                        (lv_multi if lv.get("tier") in MULTI_DAY_TIERS
                         else lv_active).append(float(p))
                except Exception:  # noqa: BLE001 -- counted, never silently "no levels"
                    diag["lvl_err"] += 1
                    lv_active, lv_multi = [], []
        if not lv_active:
            diag["lvl_empty"] += 1
            continue
        diag["lvl_sum"] += len(lv_active) + len(lv_multi)
        diag["evaluated"] += 1
        try:
            sig = ms.build_signal("SPY", window, params=params,
                                  candidate_levels=lv_active,
                                  candidate_multi_day_levels=lv_multi)
        except (ms.SignalBuildError, ValueError):
            continue
        action = str(sig.get("action") or "HOLD").upper()
        if action not in ("ENTER_BULL", "ENTER_BEAR"):
            continue
        sign = 1.0 if action == "ENTER_BULL" else -1.0
        base = closes[i]
        if base <= 0:
            continue
        rec = {"i": i, "direction": action, "day": str(bars.index[i])[:10]}
        for h in HORIZONS:
            rec[f"fwd_{h}"] = round(sign * 100.0 * (closes[i + h] / base - 1.0), 5)
        out.append(rec)
    return out, diag


def summarize(sigs: list) -> dict:
    s = {"n": len(sigs)}
    for h in HORIZONS:
        vals = [r[f"fwd_{h}"] for r in sigs if r.get(f"fwd_{h}") is not None]
        if not vals:
            s[f"h{h}"] = None
            continue
        hits = sum(1 for v in vals if v > 0)
        hr = 100.0 * hits / len(vals)
        se = math.sqrt(0.25 / len(vals)) * 100.0
        s[f"h{h}"] = {"n": len(vals), "hit": round(hr, 2),
                      "sigma": round((hr - 50.0) / se, 2),
                      "mean_pct": round(sum(vals) / len(vals), 5)}
    return s


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    params = json.loads((REPO / "automation" / "state" / "multi" / "params.json").read_text(encoding="utf-8"))
    c = mcreds.resolve(params)
    print("[control] fetching SPY ...", flush=True)
    b5 = mcore.fetch_bars_batch(c, ["SPY"], "5Min", limit=4300).get("SPY")
    bd = mcore.fetch_bars_batch(c, ["SPY"], "1Day", limit=200).get("SPY")
    if b5 is None or b5.empty or bd is None or bd.empty:
        print("[control] FATAL: no bars -- refusing to report", file=sys.stderr)
        return 1
    daily = _norm_daily(bd)
    print(f"[control] 5m bars={len(b5)}  daily={len(daily)}", flush=True)

    report = {"symbol": "SPY", "headline_horizon_bars": HEADLINE,
              "production_trigger_reference_hit_at_10min": 58.23, "arms": {}}
    for arm in ("fork", "prod_base", "prod_full"):
        sigs, diag = replay(b5, params, arm, daily)
        report["arms"][arm] = {"signals": len(sigs), "diagnostics": diag,
                               "summary": summarize(sigs) if sigs else None}
        hh = ((report["arms"][arm]["summary"] or {}).get(f"h{HEADLINE}") or {})
        avg = round(diag["lvl_sum"] / diag["evaluated"], 1) if diag["evaluated"] else 0
        err_pct = 100.0 * diag["lvl_err"] / max(diag["refreshes"], 1)
        flag = "  *** ARM UNTRUSTWORTHY ***" if err_pct > 1.0 else ""
        print(f"[control] {arm:10s} n={len(sigs):5d}  hit@10m={hh.get('hit','n/a')}  "
              f"sigma={hh.get('sigma','n/a')}  avg_levels={avg}  "
              f"lvl_err={diag['lvl_err']}/{diag['refreshes']} ({err_pct:.1f}%)"
              f"  empty_bars={diag['lvl_empty']}{flag}", flush=True)
        report["arms"][arm]["trustworthy"] = err_pct <= 1.0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[control] wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

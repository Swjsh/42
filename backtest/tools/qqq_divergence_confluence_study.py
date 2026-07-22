"""qqq_divergence_confluence_study.py -- FIRST-PASS proxy information test for the
prospector's cross_asset_signals finding (chef-inbox 2026-07-11 --
`2026-07-11-prospector-qqq_divergence_confluence.md`; spec source:
markdown/planning/CROSS-TICKER-BRAINSTORM-2026-07-10.md, "battery-ready").

QUESTION: does QQQ's own simultaneous structural behavior at a SPY ribbon_ride signal's
entry timestamp (did QQQ ALSO reclaim its own recent N-bar high [bull] / break its own
recent N-bar low [bear], or fail to, or do neither) predict whether the SPY signal
continues in its intended direction over the next 30 minutes?

WHY A PROXY, NOT THE FULL REAL-FILLS REPLAY (disclosed per OP-20 -- do not oversell this):
the canonical 250-signal cohort (`_signal_cache.load_or_build_signals()`) has no $ P&L
attached without running the full per-strike real-OPRA replay
(`ribbon_ride_strike_exit_ab.py::replay_cell`, ~250 signals x per-strike option-chain
fetch/replay) -- a legitimate but SEPARATE, heavier task the 2026-07-21 chef-inbox note
explicitly deferred to "a future chef fire with its own budget." Per the BACKTESTING-
PLAYBOOK 5-stage grinder (cheap synthetic screen BEFORE expensive real-fills validation),
this script answers the cheaper prior question first: does a QQQ agreement/disagreement
label carry ANY information about SPY's own forward spot continuation? If this first pass
shows nothing, the expensive real-fills wiring is not worth funding. If it shows a real
split, THAT is the evidence to fund the full pipeline next.

MEASURED vs MODELED: QQQ bars + SPY bars are real market data (Alpaca SIP/cached CSV), but
the "outcome" is a spot-return proxy, NOT a $ P&L and NOT a real fill. This result is NOT
eligible for conductor-proposals.jsonl / wiring on its own (OP-11's OOS+WF+anchor+A/B bar
does not apply to a spot-return information test) -- it is a funding decision for the next,
heavier study.

NO LOOK-AHEAD (C6): QQQ's own N-bar high/low as of a signal's entry_ts is computed from
QQQ bars STRICTLY BEFORE entry_ts. The reclaim/failure label is assigned by reading the
entry bar (the first QQQ bar with timestamp >= entry_ts) against that PRIOR window only --
never a bar that closes after the label is assigned. `qqq_label_for_signal()` is the one
place this happens; guarded by backtest/tests/test_qqq_divergence_confluence_study.py.

Run: backtest/.venv/Scripts/python.exe backtest/tools/qqq_divergence_confluence_study.py
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
import sys
import time as _time_mod
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO / "backtest", REPO / "backtest" / "tools"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from _alpaca_creds import resolve_alpaca_creds  # noqa: E402
import _signal_cache as sc  # noqa: E402
from autoresearch.runner import load_data  # noqa: E402
from autoresearch.probe_stats import significance  # noqa: E402

QQQ_BARS_URL = "https://data.alpaca.markets/v2/stocks/QQQ/bars"
CACHE = REPO / "analysis" / "backtests" / "cache"
CACHE.mkdir(parents=True, exist_ok=True)
QQQ_CACHE_F = CACHE / f"qqq-5m-{sc.START}_{sc.END}.csv"

LEVEL_WINDOW_BARS = 20      # ~100 min of QQQ 5m bars -- "QQQ's own recent structure"
FORWARD_MINUTES = 30        # outcome horizon: does the SPY signal keep going for 30 min?
OUT_JSON = REPO / "analysis" / "recommendations" / "qqq-divergence-confluence-study.json"
OUT_MD = REPO / "analysis" / "recommendations" / "qqq-divergence-confluence-study.md"


# ---------------------------------------------------------------------------------------
# FETCH -- QQQ 5m bars for the SAME window as the canonical SPY signal cohort. Cached to
# disk so re-runs (or a future full real-fills study) never re-fetch. Mirrors
# backtest/tools/alpaca_bars.py's SIP-fetch shape, generalized to QQQ, paginated.
# ---------------------------------------------------------------------------------------
def fetch_qqq_5m(start_date: dt.date, end_date: dt.date, *, refresh: bool = False) -> pd.DataFrame:
    if QQQ_CACHE_F.exists() and not refresh:
        df = pd.read_csv(QQQ_CACHE_F)
        df["timestamp_et"] = pd.to_datetime(df["timestamp_et"])
        return df

    creds = resolve_alpaca_creds()
    start_utc = f"{start_date.isoformat()}T07:00:00Z"
    end_utc = f"{end_date.isoformat()}T21:30:00Z"
    ET = dt.timezone(dt.timedelta(hours=-4))  # crude; real per-row offset applied below via zoneinfo
    from zoneinfo import ZoneInfo
    ET_ZONE = ZoneInfo("America/New_York")

    raw: list[dict] = []
    page_token: str | None = None
    while True:
        params = {"timeframe": "5Min", "start": start_utc, "end": end_utc,
                   "limit": 10000, "feed": "sip"}
        if page_token:
            params["page_token"] = page_token
        req = Request(f"{QQQ_BARS_URL}?{urlencode(params)}",
                       headers={"APCA-API-KEY-ID": creds.key, "APCA-API-SECRET-KEY": creds.secret})
        payload = json.loads(urlopen(req, timeout=60).read())
        raw.extend(payload.get("bars", []) or [])
        page_token = payload.get("next_page_token")
        print(f"  [qqq_fetch] {len(raw)} bars so far" + (f" (paging...)" if page_token else ""))
        if not page_token:
            break
        _time_mod.sleep(0.15)

    rows = []
    for b in raw:
        ts_et = dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00")).astimezone(ET_ZONE)
        rows.append({"timestamp_et": ts_et.replace(tzinfo=None), "open": b["o"], "high": b["h"],
                      "low": b["l"], "close": b["c"], "volume": b["v"]})
    df = pd.DataFrame(rows, columns=["timestamp_et", "open", "high", "low", "close", "volume"])
    df.to_csv(QQQ_CACHE_F, index=False)
    return df


# ---------------------------------------------------------------------------------------
# LABEL -- QQQ's own reclaim/failure/none at a signal's entry_ts. No look-ahead: the rolling
# high/low window uses bars strictly BEFORE entry_ts; only the entry bar itself (>= entry_ts)
# is compared against it.
# ---------------------------------------------------------------------------------------
def qqq_label_for_signal(qqq_df: pd.DataFrame, entry_ts: dt.datetime, direction: str,
                          window_bars: int = LEVEL_WINDOW_BARS) -> dict:
    """Returns {'label': 'reclaimed'|'failed'|'none'|'no_data', 'level': float|None}.

    bull: QQQ 'reclaimed' if its entry-bar CLOSE > the prior-window HIGH (broke its own
          recent structure up); 'failed' if the entry-bar HIGH touched/exceeded the prior
          high but the CLOSE fell back under it; else 'none'.
    bear: mirrored on the prior-window LOW.
    """
    prior = qqq_df[qqq_df["timestamp_et"] < entry_ts].tail(window_bars)
    at_or_after = qqq_df[qqq_df["timestamp_et"] >= entry_ts]
    if len(prior) < max(5, window_bars // 4) or at_or_after.empty:
        return {"label": "no_data", "level": None}
    entry_bar = at_or_after.iloc[0]
    if direction == "bull":
        level = float(prior["high"].max())
        if float(entry_bar["close"]) > level:
            label = "reclaimed"
        elif float(entry_bar["high"]) >= level:
            label = "failed"
        else:
            label = "none"
    else:
        level = float(prior["low"].min())
        if float(entry_bar["close"]) < level:
            label = "reclaimed"
        elif float(entry_bar["low"]) <= level:
            label = "failed"
        else:
            label = "none"
    return {"label": label, "level": level}


# ---------------------------------------------------------------------------------------
# OUTCOME PROXY -- direction-aligned SPY forward return over FORWARD_MINUTES from entry_ts.
# Positive = the signal kept going the intended way. NOT a $ P&L (disclosed above).
# ---------------------------------------------------------------------------------------
def spy_forward_return(spy_by_date: dict, date_obj: dt.date, entry_ts: dt.datetime,
                        entry_spot: float, direction: str) -> float | None:
    day = spy_by_date.get(date_obj)
    if day is None:
        return None
    horizon = entry_ts + dt.timedelta(minutes=FORWARD_MINUTES)
    window = day[(day["timestamp_et"] >= entry_ts) & (day["timestamp_et"] <= horizon)]
    if window.empty:
        return None
    end_close = float(window.iloc[-1]["close"])
    raw_ret = end_close - entry_spot
    return raw_ret if direction == "bull" else -raw_ret


# ---------------------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------------------
def run(refresh: bool = False) -> dict:
    print("[1/4] loading canonical ribbon_ride signal cohort...")
    raw = sc.load_or_build_signals()
    signals = raw["signals"] if isinstance(raw, dict) else raw
    print(f"      {len(signals)} signals, window {sc.START}..{sc.END}")

    print("[2/4] loading/fetching QQQ 5m bars for the same window...")
    qqq = fetch_qqq_5m(sc.START, sc.END, refresh=refresh)
    print(f"      {len(qqq)} QQQ bars ({qqq['timestamp_et'].min()} .. {qqq['timestamp_et'].max()})")

    print("[3/4] loading SPY 5m bars (reused cache, autoresearch.runner.load_data)...")
    spy, _vix = load_data(sc.START, sc.END)
    spy["timestamp_et"] = pd.to_datetime(spy["timestamp_et"]).dt.tz_localize(None)
    spy["date"] = spy["timestamp_et"].dt.date
    spy_by_date = {d: g.reset_index(drop=True) for d, g in spy.groupby("date")}

    print("[4/4] labeling + stratifying...")
    rows = []
    for s in signals:
        entry_ts = dt.datetime.fromisoformat(s["entry_ts"])
        date_obj = dt.date.fromisoformat(s["date"])
        lbl = qqq_label_for_signal(qqq, entry_ts, s["direction"])
        fwd = spy_forward_return(spy_by_date, date_obj, entry_ts, float(s["entry_spot"]), s["direction"])
        rows.append({**s, "qqq_label": lbl["label"], "qqq_level": lbl["level"],
                     "spy_forward_return_aligned": fwd})

    usable = [r for r in rows if r["spy_forward_return_aligned"] is not None
              and r["qqq_label"] != "no_data"]
    n_dropped = len(rows) - len(usable)

    strata = {}
    for label in ("reclaimed", "failed", "none"):
        rets = [r["spy_forward_return_aligned"] for r in usable if r["qqq_label"] == label]
        if rets:
            strata[label] = {
                "n": len(rets),
                "mean_aligned_return": round(statistics.mean(rets), 4),
                "median_aligned_return": round(statistics.median(rets), 4),
                "pct_positive": round(100 * sum(1 for x in rets if x > 0) / len(rets), 1),
                **significance(len(rets)),
            }
        else:
            strata[label] = {"n": 0}

    # by direction too (bull is the historically thin/weak side per CLAUDE.md OP-16)
    by_direction = {}
    for d in ("bull", "bear"):
        sub = [r for r in usable if r["direction"] == d]
        by_direction[d] = {"n": len(sub),
                            "n_reclaimed": sum(1 for r in sub if r["qqq_label"] == "reclaimed"),
                            "n_failed": sum(1 for r in sub if r["qqq_label"] == "failed"),
                            "n_none": sum(1 for r in sub if r["qqq_label"] == "none")}

    reclaimed_rets = [r["spy_forward_return_aligned"] for r in usable if r["qqq_label"] == "reclaimed"]
    other_rets = [r["spy_forward_return_aligned"] for r in usable if r["qqq_label"] != "reclaimed"]
    spread = None
    if reclaimed_rets and other_rets:
        spread = round(statistics.mean(reclaimed_rets) - statistics.mean(other_rets), 4)

    out = {
        "_doc": __doc__,
        "generated_at": dt.datetime.now().isoformat(),
        "signal_cohort": {"source": "_signal_cache.load_or_build_signals()",
                           "window": f"{sc.START}..{sc.END}", "n_total": len(signals),
                           "n_usable": len(usable), "n_dropped_no_data": n_dropped},
        "method": {
            "qqq_level_window_bars": LEVEL_WINDOW_BARS,
            "forward_horizon_minutes": FORWARD_MINUTES,
            "outcome_metric": "direction-aligned SPY spot return over forward_horizon_minutes "
                              "from signal entry_ts (NOT a $ P&L, NOT a real fill -- MODELED "
                              "spot-return information-test proxy, disclosed per OP-20)",
        },
        "strata_by_qqq_label": strata,
        "by_direction": by_direction,
        "reclaimed_vs_other_mean_spread": spread,
        "verdict": (
            "NO_SIGNAL" if spread is None or abs(spread) < 0.05 else
            ("QQQ_AGREEMENT_INFORMATIVE" if spread > 0 else "QQQ_AGREEMENT_INVERSE")
        ),
        "next_step": (
            "If verdict == QQQ_AGREEMENT_INFORMATIVE: fund the full real-fills replay "
            "(ribbon_ride_strike_exit_ab.py-class per-strike OPRA replay, stratified by "
            "qqq_label) before any wiring proposal. If NO_SIGNAL or INVERSE: do not fund "
            "the expensive replay; close the chef-inbox item as explored-and-not-promising."
        ),
    }
    OUT_JSON.write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
    OUT_MD.write_text(_render_md(out), encoding="utf-8")
    print(f"\nWrote {OUT_JSON}\nWrote {OUT_MD}")
    print(f"Verdict: {out['verdict']}  (spread={spread})")
    return out


def _render_md(out: dict) -> str:
    lines = [
        "# QQQ divergence/confluence -- first-pass information test",
        "",
        f"Generated {out['generated_at']}. Verdict: **{out['verdict']}**.",
        "",
        "## Method (disclosed proxy, NOT a real-fills P&L study)",
        f"- QQQ own-level window: {out['method']['qqq_level_window_bars']} bars",
        f"- Forward horizon: {out['method']['forward_horizon_minutes']} min",
        f"- Outcome metric: {out['method']['outcome_metric']}",
        "",
        "## Signal cohort",
        f"- {out['signal_cohort']['n_total']} total signals "
        f"({out['signal_cohort']['window']}), {out['signal_cohort']['n_usable']} usable "
        f"({out['signal_cohort']['n_dropped_no_data']} dropped for missing QQQ/SPY bars)",
        "",
        "## Strata by QQQ label",
    ]
    for label, s in out["strata_by_qqq_label"].items():
        if s.get("n"):
            lines.append(f"- **{label}** (n={s['n']}): mean aligned return={s['mean_aligned_return']}, "
                         f"median={s['median_aligned_return']}, %positive={s['pct_positive']}%, "
                         f"{s['note']}")
        else:
            lines.append(f"- **{label}**: n=0")
    lines += [
        "",
        f"## Reclaimed vs other mean spread: {out['reclaimed_vs_other_mean_spread']}",
        "",
        "## By direction",
        json.dumps(out["by_direction"], indent=2),
        "",
        "## Next step",
        out["next_step"],
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    run(refresh="--refresh" in sys.argv)

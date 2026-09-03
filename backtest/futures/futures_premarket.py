"""futures_premarket.py -- deterministic ($0, no LLM) futures premarket level + bias producer.

WHY (2026-09-03, queue item FUTURES-PREMARKET-PRODUCER-MISSING). The SPY engine's 08:30 ET
premarket step writes automation/state/key-levels.json + today-bias.json before the 09:30 RTH
open (markdown/0dte/key-levels-protocol.md@2). The futures lane never had an equivalent
producer: the only existing one, the `Gamma_FuturesPremarket` scheduled task, points at an LLM
persona (`automation/prompts/futures-premarket.md`, retired to `_retired/` alongside this
module) that has **NEVER FIRED** (live Task Scheduler: LastResult 267011 /
SCHED_S_TASK_HAS_NOT_RUN, Disabled since 2026-07-08) and reads June-era corpse state files. This
module replaces it: deterministic, $0, mirrors the SPY producer's SHAPE but computes everything
mechanically from bars -- no chart read, no persona, no narrative prose.

WHAT IT COMPUTES per instrument (default MES, MNQ -- the two roots `futures_trader_core.py`
actually trades):
  - prior RTH day high/low/close (PDH/PDL/PDC) from the most recently completed RTH session
    strictly before `for_session`
  - overnight GLOBEX high/low: the range of bars strictly after the prior RTH close and at/
    before "now"
  - prior RTH session VWAP (volume-weighted; None when the feed carries no/zero volume --
    never fabricated)
  - a MECHANICAL bias: overnight-last vs PDC, normalized by the prior day's own RTH range (so
    the threshold scales with each instrument's typical volatility instead of a fixed point
    count), producing bullish/bearish/neutral with a numeric `confidence` and the exact formula
    spelled out in `method`. No narrative text anywhere in this file's output.
  - falsifiable, numeric predictions keyed to the levels above

DATA SOURCE -- REUSED, not reinvented. `futures_live_data.append_live` + `.load_series(mode=
"live")` is the SAME live bar spine `futures_trader_core.py` / `futures_heartbeat_core.py`
consume, so a level computed here is provenance-consistent with what the live engine itself
would see on the same tick. `--offline` skips the network refresh and reads whatever is
already cached (used by tests, and by any caller that already refreshed the cache this pass).

NO FABRICATION. If the live cache has no bars at all, no bars for the prior RTH session, no
overnight bar yet, or a computed level falls outside the instrument's index-point sanity band
(garbled-feed guard), the affected instrument's block is written as `status: "DATA_MISSING"`
plus a `reason` string and NO numeric level/bias field is emitted for it -- never a null
standing in for a fabricated number.

SCHEMA FAMILY -- shares its top-level shape with the SPY producer so a consumer COULD share a
reader: `schema_version`, `as_of`, `for_session`, `computed_from` on both files (per this
module's build task). The per-level shape is a deliberately smaller subset of the SPY
protocol's five mandatory fields (source/tier/verification/reasoning/type) -- TV-chart manual
verification does not apply to a bar-computed level, so only `source` (an exact bar/window
citation), `type`, `label`, and `reasoning` are populated; `tier` is always "Active" (rebuilt
fresh every premarket, never carried over).

NO CONSUMER YET (checked before writing this module: grepped `key-levels` / `today-bias` under
backtest/futures/*.py and found no reader). Neither `futures_trader_core.py` nor
`futures_heartbeat_core.py` reads these files today -- both compute their own levels internally
via `lib.levels._detect_from_history` on the live bar frame directly. This module is a producer
with NO wired consumer; wiring one in would be a lane BEHAVIOUR change and is deliberately out
of scope here (see the queue item this module closes). Treat these files as visibility /
journaling output until a consumer is built on purpose.

CLI:
    python -m futures.futures_premarket                          # MES + MNQ, live network refresh
    python -m futures.futures_premarket --instruments MES        # one instrument
    python -m futures.futures_premarket --offline                # skip network fetch, use cached bars
    python -m futures.futures_premarket --now 2026-09-03T08:35:00  # deterministic ET override (testing)
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[2]
for _p in ("backtest",):
    _pp = str(REPO / _p)
    if _pp not in sys.path:
        sys.path.insert(0, _pp)

import pandas as pd  # noqa: E402

from futures.futures_session import et_now, is_holiday, RTH_START, RTH_END  # noqa: E402
from futures import futures_live_data as fld  # noqa: E402
from futures.instruments import get as get_instrument  # noqa: E402

STATE_DIR = REPO / "automation" / "state" / "futures"
KEY_LEVELS_OUT = STATE_DIR / "key-levels.json"
TODAY_BIAS_OUT = STATE_DIR / "today-bias.json"

SCHEMA_VERSION = 1
PROTOCOL_NOTE = "markdown/0dte/key-levels-protocol.md@2 (schema family; futures subset -- see module docstring)"
DEFAULT_INSTRUMENTS = ("MES", "MNQ")

TZ = "America/New_York"

# Index-point sanity bands -- a garbled/misaligned feed producing a level outside the
# plausible range for the instrument is refused rather than published (never a
# fabricated-looking number). MES per the queue spec (3000-9000); MNQ generous
# (8000-35000) since it trades ~5x higher and this module has no independent source
# to pin an exact current band against.
SANITY_BANDS = {
    "MES": (3000.0, 9000.0),
    "MNQ": (8000.0, 35000.0),
}


# ── session-date arithmetic ─────────────────────────────────────────────────────

def next_rth_session_date(now_et: dt.datetime) -> dt.date:
    """The next RTH session date at/after `now_et` (naive ET).

    Normal case: this runs ~08:35 ET, before the 09:30 open on a valid trading day --
    that day IS the next session. Outside that window (after today's RTH close, or on
    a weekend/holiday) scans forward to the next weekday that is not a holiday.
    """
    d = now_et.date()
    if now_et.time() < RTH_END and now_et.weekday() < 5 and not is_holiday(now_et):
        return d
    cur = dt.datetime.combine(d + dt.timedelta(days=1), RTH_START)
    while cur.weekday() >= 5 or is_holiday(cur):
        cur += dt.timedelta(days=1)
    return cur.date()


def prior_rth_session_date(session_date: dt.date) -> dt.date:
    """The most recent RTH session date strictly before `session_date`."""
    cur = session_date - dt.timedelta(days=1)
    probe = dt.datetime.combine(cur, RTH_START)
    while cur.weekday() >= 5 or is_holiday(probe):
        cur -= dt.timedelta(days=1)
        probe = dt.datetime.combine(cur, RTH_START)
    return cur


# ── bar loading (reuses the live spine futures_trader_core/futures_heartbeat_core read) ────

def _load_bars(root: str, offline: bool) -> pd.DataFrame:
    if not offline:
        try:
            fld.append_live(root, interval="5m")
        except Exception:  # noqa: BLE001 -- a network hiccup falls through to whatever is
            pass          # cached; an empty/stale cache is caught by the DATA_MISSING checks below.
    return fld.load_series(root, interval="5m", mode="live")


def _session_slice(bars: pd.DataFrame, session_date: dt.date) -> pd.DataFrame:
    if bars.empty:
        return bars
    ts = bars["timestamp_et"]
    mask = (ts.dt.date == session_date) & (ts.dt.time >= RTH_START) & (ts.dt.time < RTH_END)
    return bars[mask]


def _overnight_slice(bars: pd.DataFrame, after_ts: "pd.Timestamp", at_or_before_ts: "pd.Timestamp") -> pd.DataFrame:
    if bars.empty:
        return bars
    ts = bars["timestamp_et"]
    mask = (ts > after_ts) & (ts <= at_or_before_ts)
    return bars[mask]


# ── per-instrument levels ────────────────────────────────────────────────────────

def compute_instrument(root: str, now_et: dt.datetime, offline: bool = True,
                        bars: Optional[pd.DataFrame] = None) -> dict:
    """Compute the levels block for one instrument. `bars` lets tests inject a frame
    directly instead of touching the real live-cache file / network."""
    root = root.upper()
    for_session = next_rth_session_date(now_et)
    prior_date = prior_rth_session_date(for_session)

    if bars is None:
        bars = _load_bars(root, offline)

    if bars is None or bars.empty:
        return {
            "instrument": root,
            "status": "DATA_MISSING",
            "reason": f"live bar cache for {root} is empty (futures_live_data.load_series mode=live)",
            "for_session": for_session.isoformat(),
            "prior_session": prior_date.isoformat(),
        }

    prior_bars = _session_slice(bars, prior_date)
    if prior_bars.empty:
        return {
            "instrument": root,
            "status": "DATA_MISSING",
            "reason": f"no RTH bars for prior session {prior_date.isoformat()} in the live cache",
            "for_session": for_session.isoformat(),
            "prior_session": prior_date.isoformat(),
        }

    prior_close_ts = pd.Timestamp(dt.datetime.combine(prior_date, RTH_END)).tz_localize(TZ)
    cutoff_ts = pd.Timestamp(now_et).tz_localize(TZ)
    overnight_bars = _overnight_slice(bars, prior_close_ts, cutoff_ts)

    pdh = float(prior_bars["high"].max())
    pdl = float(prior_bars["low"].min())
    pdc_row = prior_bars.iloc[-1]
    pdc = float(pdc_row["close"])
    pdc_ts = pdc_row["timestamp_et"]

    vol_sum = float(prior_bars["volume"].sum()) if "volume" in prior_bars else 0.0
    prior_vwap = (
        float((prior_bars["close"] * prior_bars["volume"]).sum() / vol_sum)
        if vol_sum > 0 else None
    )

    if not overnight_bars.empty:
        onh = float(overnight_bars["high"].max())
        onl = float(overnight_bars["low"].min())
        last_row = overnight_bars.iloc[-1]
        overnight_last = float(last_row["close"])
        overnight_last_ts = last_row["timestamp_et"]
    else:
        onh = onl = overnight_last = None
        overnight_last_ts = None

    band = SANITY_BANDS.get(root)
    if band is not None:
        candidates = [v for v in (pdh, pdl, pdc, onh, onl, overnight_last) if v is not None]
        if any(not (band[0] <= v <= band[1]) for v in candidates):
            return {
                "instrument": root,
                "status": "DATA_MISSING",
                "reason": (f"computed level(s) fell outside the {root} sanity band "
                           f"{band[0]}-{band[1]} index points -- feed looks garbled, refusing to publish"),
                "for_session": for_session.isoformat(),
                "prior_session": prior_date.isoformat(),
            }

    inst = get_instrument(root)
    levels = [
        {
            "price": pdh, "type": "resistance", "label": f"PDH_{prior_date.isoformat()}",
            "tier": "Active",
            "source": f"5m bars, RTH session {prior_date.isoformat()} -- session high",
            "reasoning": "Prior RTH session high; standard PDH reference for gap/break setups.",
        },
        {
            "price": pdl, "type": "support", "label": f"PDL_{prior_date.isoformat()}",
            "tier": "Active",
            "source": f"5m bars, RTH session {prior_date.isoformat()} -- session low",
            "reasoning": "Prior RTH session low; standard PDL reference for gap/break setups.",
        },
        {
            "price": pdc, "type": "reference", "label": f"PDC_{prior_date.isoformat()}",
            "tier": "Active",
            "source": f"5m bar at {pdc_ts.isoformat()} -- last RTH close",
            "reasoning": "Prior RTH session close; anchor for the overnight-change bias calc.",
        },
    ]
    if onh is not None:
        levels.append({
            "price": onh, "type": "resistance", "label": f"ONH_{for_session.isoformat()}",
            "tier": "Active",
            "source": (f"5m bars {prior_close_ts.isoformat()} .. "
                       f"{overnight_last_ts.isoformat()} -- overnight GLOBEX high"),
            "reasoning": "Overnight GLOBEX session high since prior RTH close; gap-trade reference.",
        })
    if onl is not None:
        levels.append({
            "price": onl, "type": "support", "label": f"ONL_{for_session.isoformat()}",
            "tier": "Active",
            "source": (f"5m bars {prior_close_ts.isoformat()} .. "
                       f"{overnight_last_ts.isoformat()} -- overnight GLOBEX low"),
            "reasoning": "Overnight GLOBEX session low since prior RTH close; gap-trade reference.",
        })

    return {
        "instrument": root,
        "status": "OK",
        "for_session": for_session.isoformat(),
        "prior_session": prior_date.isoformat(),
        "point_value": inst.point_value,
        "tick_size": inst.tick_size,
        "levels": levels,
        "prior_rth_vwap": prior_vwap,
        "prior_close": pdc,
        "prior_high": pdh,
        "prior_low": pdl,
        "overnight_high": onh,
        "overnight_low": onl,
        "overnight_last": overnight_last,
        "overnight_last_ts": overnight_last_ts.isoformat() if overnight_last_ts is not None else None,
    }


# ── mechanical bias (NO narrative prose -- numeric formula only) ───────────────────

NEUTRAL_BAND = 0.15  # |range_frac| below this -> neutral. Documented in `method`, not tuned/backtested.


def compute_bias(levels_result: dict) -> dict:
    root = levels_result["instrument"]
    if levels_result.get("status") != "OK":
        return {
            "instrument": root,
            "status": "DATA_MISSING",
            "reason": levels_result.get("reason", "levels unavailable"),
            "for_session": levels_result.get("for_session"),
        }

    pdc = levels_result["prior_close"]
    pdh = levels_result["prior_high"]
    pdl = levels_result["prior_low"]
    last = levels_result["overnight_last"]
    prior_range = pdh - pdl

    if last is None or prior_range <= 0:
        return {
            "instrument": root,
            "status": "DATA_MISSING",
            "reason": "no overnight bar since the prior RTH close yet, or prior RTH range is zero",
            "for_session": levels_result.get("for_session"),
        }

    change_pts = last - pdc
    change_pct = (change_pts / pdc) if pdc else None
    # Normalize by the prior day's own RTH range so the bias threshold scales with
    # each instrument's typical volatility instead of a fixed point count (MES and
    # MNQ move on very different point scales).
    range_frac = change_pts / prior_range

    if range_frac > NEUTRAL_BAND:
        bias = "bullish"
    elif range_frac < -NEUTRAL_BAND:
        bias = "bearish"
    else:
        bias = "neutral"

    confidence = round(min(1.0, abs(range_frac) / (2 * NEUTRAL_BAND)), 3)

    predictions = []
    if bias != "neutral":
        predictions.append({
            "claim": (f"{root} RTH session opens/holds "
                      f"{'above' if bias == 'bullish' else 'below'} prior close {pdc} "
                      "through the first 30 minutes of RTH"),
            "reference_level": pdc,
            "direction": bias,
            "trigger_window_et": "09:30-10:00",
        })

    return {
        "instrument": root,
        "status": "OK",
        "for_session": levels_result.get("for_session"),
        "bias": bias,
        "confidence": confidence,
        "method": (
            "range_frac = (overnight_last - prior_rth_close) / (prior_rth_high - prior_rth_low); "
            f"bullish if range_frac > {NEUTRAL_BAND}, bearish if range_frac < {-NEUTRAL_BAND}, "
            f"else neutral. confidence = min(1, |range_frac| / {2 * NEUTRAL_BAND})."
        ),
        "overnight_change_pts": round(change_pts, 4),
        "overnight_change_pct": round(change_pct, 6) if change_pct is not None else None,
        "prior_close": pdc,
        "prior_rth_high": pdh,
        "prior_rth_low": pdl,
        "overnight_last": last,
        "overnight_last_ts": levels_result.get("overnight_last_ts"),
        "falsifiable_predictions": predictions,
    }


# ── build + write ────────────────────────────────────────────────────────────────

def _atomic_write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)


def build(instruments, now_et: dt.datetime, offline: bool = True,
          bars_by_instrument: Optional[dict] = None) -> tuple[dict, dict]:
    """Compute both output documents. `bars_by_instrument` (root -> DataFrame) lets
    tests drive the full pipeline deterministically without touching the live cache."""
    as_of = now_et.replace(microsecond=0).isoformat()
    for_session = next_rth_session_date(now_et).isoformat()

    levels_by_instrument = {}
    bias_by_instrument = {}
    for root in instruments:
        root = root.upper()
        injected = (bars_by_instrument or {}).get(root)
        lv = compute_instrument(root, now_et, offline=offline, bars=injected)
        levels_by_instrument[root] = lv
        bias_by_instrument[root] = compute_bias(lv)

    key_levels_doc = {
        "schema_version": SCHEMA_VERSION,
        "protocol_version": PROTOCOL_NOTE,
        "as_of": as_of,
        "for_session": for_session,
        "computed_from": "futures_premarket.py (futures_live_data live bar spine, mode=live)",
        "instruments": levels_by_instrument,
    }
    today_bias_doc = {
        "schema_version": SCHEMA_VERSION,
        "as_of": as_of,
        "for_session": for_session,
        "computed_from": "futures_premarket.py (mechanical overnight-change-vs-prior-range formula, no LLM)",
        "instruments": bias_by_instrument,
    }
    return key_levels_doc, today_bias_doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Futures premarket level + bias producer ($0, no LLM)")
    ap.add_argument("--instruments", default=",".join(DEFAULT_INSTRUMENTS),
                     help="comma-separated instrument roots, e.g. MES,MNQ")
    ap.add_argument("--offline", action="store_true",
                     help="skip the live network refresh; read whatever bars are already cached")
    ap.add_argument("--now", default=None,
                     help="ISO ET datetime override, e.g. 2026-09-03T08:35:00 (testing/determinism)")
    ap.add_argument("--print", action="store_true", help="print the written docs to stdout")
    args = ap.parse_args(argv)

    instruments = [s.strip().upper() for s in args.instruments.split(",") if s.strip()]
    now_et = dt.datetime.fromisoformat(args.now) if args.now else et_now()

    key_levels_doc, today_bias_doc = build(instruments, now_et, offline=args.offline)

    _atomic_write_json(KEY_LEVELS_OUT, key_levels_doc)
    _atomic_write_json(TODAY_BIAS_OUT, today_bias_doc)

    def _rel(p: Path) -> str:
        try:
            return str(p.relative_to(REPO))
        except ValueError:
            return str(p)

    summary = {
        "for_session": key_levels_doc["for_session"],
        "as_of": key_levels_doc["as_of"],
        "instruments": {
            root: key_levels_doc["instruments"][root].get("status")
            for root in instruments
        },
        "key_levels_out": _rel(KEY_LEVELS_OUT),
        "today_bias_out": _rel(TODAY_BIAS_OUT),
    }
    if args.print:
        print(json.dumps({"key_levels": key_levels_doc, "today_bias": today_bias_doc}, indent=2, default=str))
    else:
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""backtest/tools/eth_ribbon.py -- ETH-inclusive Saty Pivot Ribbon ground truth.

RIBBON-SESSION-SCOPE-DIVERGENCE PART A (automation/overnight/queue.md 2026-07-23; discovery
doc analysis/edge-matrix/tv-parity-oracle-2026-07-23.md): J's TV chart computes its ribbon
EMAs over EXTENDED-HOURS bars (premarket 04:00 ET onward); the engine/backtest ribbon
(backtest/lib/ribbon.py) is RTH-only by deliberate 2026-06-25 parity design. The oracle
measured up to $6.40 divergence at gap opens between the two SCOPES -- confirmed NOT a math
bug (same lib.ribbon EMA fed TV's own scope tracked TV within ~$0.38 worst-case).

This module does NOT reimplement the EMA math. It reuses backtest/lib/ribbon.py's `ema()` /
`compute_ribbon()` / fingerprinted periods verbatim (ribbon_config.json: fast=13, pivot=20,
slow=48, SMA-then-EMA seed) and feeds them a DIFFERENT-SCOPE closes Series: the FULL
extended-hours series the spy_5m_*.csv caches already carry (04:00 premarket through
whatever the cache holds that day -- caches do NOT carry 16:00-20:00 after-hours bars, a
known, disclosed residual scope gap vs TV's full 04:00-20:00 session; the oracle's
"Attribution run" measured this residual at ~$0.38 worst-case / ~$0.01-0.17 typical, i.e.
~94% of the $6.40 RTH-only gap is closed by premarket bars alone). Any parity finding this
module produces is therefore about SESSION SCOPE, never about arithmetic.

FRAME: built continuously across every day-inventory-covered day (386 days back to
2025-01-02) so the EMA-48/51 warmup has genuinely converged (alpha=2/49; weight of the
initial SMA seed decays to <2% within ~100 bars, negligible well before any bar this module
is ever queried against) by the time any validation/production day is reached -- mirrors
backtest/tools/edge_matrix_bear_level_rejection.py's load_spy_frame warmup-continuity
rationale, generalized to ETH scope. Per-day source-file resolution mirrors that module's
day-inventory-driven, offset-less-source-fallback pattern; `_true_et` below is ported
VERBATIM from that module (frozen, DST-bug-tested there -- amendments 1-2 in
analysis/edge-matrix/prereg-bear-level-rejection-2026-07-23.json) rather than re-derived,
to avoid reintroducing the exact SPY-vs-OPRA 1h winter-DST misalignment that module's own
amendment 1 found and fixed (C6/C34 discipline: don't re-derive a proven DST converter).

NOT a new EMA implementation. NOT RTH-filtered (mirrors setup/scripts/dojo/engine_step.py
load_day_bars's deliberate contract: "this loader deliberately does NOT RTH-filter").
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

import pandas as pd

_ROOT = Path(__file__).resolve().parents[2]  # .../42
_BACKTEST_DIR = str(_ROOT / "backtest")
if _BACKTEST_DIR not in sys.path:
    sys.path.insert(0, _BACKTEST_DIR)

from lib.ribbon import compute_ribbon, load_periods, RibbonState  # noqa: E402 -- reused verbatim

INVENTORY_PATH = _ROOT / "analysis" / "edge-matrix" / "day-inventory-2026-07-23.json"
DATA_DIR = _ROOT / "backtest" / "data"


# =====================================================================================
# _true_et -- ported VERBATIM from backtest/tools/edge_matrix_bear_level_rejection.py
# (that module's proven, amendment-tested DST-safe conversion). Do not diverge from it;
# if that module's `_true_et` ever changes, port the change here too.
# =====================================================================================
def _true_et(series: pd.Series) -> pd.Series:
    """TRUE-ET frame: per-row offset -> UTC -> US-DST-aware America/New_York -> naive
    true-ET wall. See edge_matrix_bear_level_rejection.py's `_true_et` docstring for the
    full DST-misalignment story this fixes (SPY-vs-OPRA 1h offset on 2026 winter days)."""
    if pd.api.types.is_datetime64_any_dtype(series):
        if getattr(series.dt, "tz", None) is None:
            raise ValueError(
                "tz-naive datetime series: frame unknowable -- refuse to guess (C6). "
                "All cache stores carry per-row offsets; a naive column here is a bug.")
        return series.dt.tz_convert("America/New_York").dt.tz_localize(None)
    ts = pd.to_datetime(series, format="mixed", utc=True)
    return ts.dt.tz_convert("America/New_York").dt.tz_localize(None)


# =====================================================================================
# ETH-inclusive continuous frame
# =====================================================================================
def load_eth_frame(inventory: Optional[dict] = None) -> pd.DataFrame:
    """Continuous multi-day ETH-inclusive (whole calendar date, NO RTH time mask) 5m close
    series, built per-day from each day-inventory day's OWN designated source_file, TRUE-ET
    converted, with the SAME offset-less-source fallback rule
    edge_matrix_bear_level_rejection.load_spy_frame uses (first offset-carrying source file
    yielding >= 30 bars for that date wins; deterministic order), generalized to NOT
    RTH-filter. Returns columns: timestamp_et, open, high, low, close, volume.

    Days whose designated source (and every fallback source) is offset-less, or yields < 30
    bars for the FULL calendar date, are skipped and counted in the returned coverage note
    (accessible via `load_eth_frame.last_skipped`, set as a side-channel for callers that
    want to disclose it -- avoids changing this function's return shape).
    """
    inv = inventory or json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))
    sources = list(dict.fromkeys(r["source_file"] for r in inv["days"]))
    parsed: dict[str, Optional[pd.DataFrame]] = {}
    cols = ["timestamp_et", "open", "high", "low", "close", "volume"]

    def _load(src: str) -> Optional[pd.DataFrame]:
        if src in parsed:
            return parsed[src]
        raw = pd.read_csv(DATA_DIR / src)
        s = raw["timestamp_et"].astype(str)
        if not s.str.contains(r"(?:Z|[+-]\d{2}:?\d{2})\s*$", regex=True).all():
            parsed[src] = None
            return None
        raw["timestamp_et"] = _true_et(raw["timestamp_et"])
        for c in ("open", "high", "low", "close"):
            raw[c] = pd.to_numeric(raw[c], errors="coerce")
        parsed[src] = raw
        return raw

    parts: list[pd.DataFrame] = []
    skipped: list[str] = []
    for rec in inv["days"]:
        day = date.fromisoformat(rec["date"])
        chosen: Optional[tuple[str, pd.DataFrame]] = None
        for src in [rec["source_file"]] + [s for s in sources if s != rec["source_file"]]:
            df = _load(src)
            if df is None:
                continue
            t = df["timestamp_et"]
            m = t.dt.date == day  # ETH-inclusive: whole date, NO RTH time mask
            d = (df.loc[m, cols]
                   .drop_duplicates(subset="timestamp_et", keep="last")
                   .sort_values("timestamp_et"))
            if len(d) >= 30:
                chosen = (src, d)
                break
        if chosen is None:
            skipped.append(rec["date"])
            continue
        parts.append(chosen[1])
    out = pd.concat(parts, ignore_index=True).sort_values("timestamp_et").reset_index(drop=True)
    assert out["timestamp_et"].is_monotonic_increasing, "ETH frame not time-ordered"
    assert not out["timestamp_et"].duplicated().any(), "duplicate timestamps in ETH frame"
    load_eth_frame.last_skipped = skipped  # type: ignore[attr-defined]
    return out


load_eth_frame.last_skipped = []  # type: ignore[attr-defined]


def compute_eth_ribbon(frame: Optional[pd.DataFrame] = None,
                       periods: Optional[dict] = None) -> pd.DataFrame:
    """Ribbon state per bar over the FULL ETH-inclusive frame. Literally
    lib.ribbon.compute_ribbon (unmodified) fed a different-scope closes Series -- carries a
    `timestamp_et` column alongside the fast/pivot/slow/spread_cents/stack columns so callers
    can look bars up by wall-clock time."""
    frame = frame if frame is not None else load_eth_frame()
    df = compute_ribbon(frame["close"].reset_index(drop=True), periods=periods)
    df["timestamp_et"] = frame["timestamp_et"].reset_index(drop=True)
    return df


def ribbon_at_ts(ribbon_with_ts: pd.DataFrame, ts) -> Optional[RibbonState]:
    """Exact-timestamp lookup. An RTH bar's timestamp exists verbatim inside the ETH frame
    (RTH is a strict subset of ETH by construction), so no interpolation/backward-asof is
    needed for RTH-bar queries; returns None on WARMUP / not-found."""
    tsx = pd.Timestamp(ts)
    if tsx.tzinfo is not None:
        tsx = tsx.tz_localize(None)
    row = ribbon_with_ts.loc[ribbon_with_ts["timestamp_et"] == tsx]
    if row.empty:
        return None
    r = row.iloc[0]
    if r["stack"] == "WARMUP" or pd.isna(r["fast"]):
        return None
    return RibbonState(fast=float(r["fast"]), pivot=float(r["pivot"]), slow=float(r["slow"]),
                       spread_cents=float(r["spread_cents"]), stack=str(r["stack"]))


if __name__ == "__main__":
    frame = load_eth_frame()
    n_skipped = len(load_eth_frame.last_skipped)  # type: ignore[attr-defined]
    print(f"[eth_ribbon] ETH frame: {len(frame)} bars, "
          f"{frame['timestamp_et'].iloc[0]} .. {frame['timestamp_et'].iloc[-1]}, "
          f"days_skipped={n_skipped}")
    ribbon = compute_eth_ribbon(frame)
    print(f"[eth_ribbon] periods={load_periods()}")
    print(ribbon.tail(5).to_string())

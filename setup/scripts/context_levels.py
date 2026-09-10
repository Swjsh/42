"""context_levels.py -- WS-E: canon levels as DRAWN context, NEVER gate input
(work order markdown/0dte/KEY-LEVELS-CHART-READING-HANDOFF.md #9.5 row E, corrected
per #9.13 A after Opus found the original row-E design would have broken the freeze).

THE DEFECT THIS FILE AVOIDS (read #9.13 A before touching this file):
    Row E as originally written said context levels go into key-levels.json under
    `role: "context"` "that _read_levels ignores". Verified from source:
    `heartbeat_core._read_level_records` filters ONLY on `_level_expired(...)` and
    `abs(p - spy) <= 12` -- there is no role filter anywhere in it -- and `_read_levels`
    then appends EVERY returned record's price to `active` unconditionally. A
    `role: "context"` row inside the $12 band would have landed straight in the gate's
    active level list and silently changed which levels the engine trades against.

THE CORRECTED DESIGN:
    Context levels NEVER go into key-levels.json. They are written to a SEPARATE file,
    `automation/state/context-levels.json`, that only the drawing path
    (draw_context_levels.py) reads. Consequence: `heartbeat_core._read_levels` and
    `_read_level_records` need ZERO code changes -- not a new filter, not a new branch.
    The freeze guard ("_read_levels output byte-identical with/without context rows")
    then holds BY CONSTRUCTION, not because a filter was added to a frozen path. See
    backtest/tests/test_context_levels_2026_09_09.py guard 1.

REUSE, NOT REBUILD (per the work order's explicit instruction -- L251: two producers of
the same read silently disagree):
    * Bar loading: `refresh_levels_intraday._spy_bars_with_meta` (SIP spine + IEX tail,
      already fetches SPY 5m bars the same un-blockable way the engine does). This file
      does NOT open a second bar reader.
    * VWAP + opening-range math: `backtest.lib.level_strength.compute_vwap` /
      `opening_range` -- the SAME functions `automation/scripts/compute_levels.py`
      already uses for the premarket VWAP/OR levels. Initial Balance is just
      `opening_range(minutes=60)` starting from the 09:30 open -- no new IB-specific
      window logic needed.
    * Zone width default: `refresh_levels_intraday._zone_width` (the ratified
      "DEFAULT pending a pre-registered A/B, never hand-picked" fallback). Every level
      this file emits ALSO carries `zone_width_provenance`, and where a family has a
      genuinely OBSERVED spread (an IB/opening-range range, a VWAP sigma band, a shelf
      band -- same convention `refresh_levels_intraday._level` already uses for
      `shelf_band_observed`), that observed spread is used INSTEAD of the hand-picked
      default so measured information is never discarded for a guess (#9.13 B).
    * Gamma walls: reuses `backtest.lib.engine.gex_regime.compute_gex_regime` /
      `GammaContract` (the GEX math is not reimplemented) over the ALREADY-WIRED,
      ALREADY-RUNNING free CBOE OI+gamma banker (`Gamma_CboeOiBank`, registered
      2026-06-22, `backtest/tools/cboe_oi_bank.py` -> `journal/gex-archive/{date}-cboe
      .json`, $0, no auth). OP-3/C36 requires checking wired free pipes FIRST -- this
      is that pipe, verified present and current in this session. This file reads only
      the already-banked local archive; it never fetches new data itself.

Writes automation/state/context-levels.json. Nothing in this repo reads that file except
draw_context_levels.py (drawing-only consumer, also new, also additive).
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parent
STATE = REPO / "automation" / "state"
CONTEXT_LEVELS = STATE / "context-levels.json"
GEX_ARCHIVE_DIR = REPO / "journal" / "gex-archive"

# HARD STALENESS CAP on the banked CBOE archive (added at Opus review, 2026-09-10).
# _latest_cboe_archive() takes the newest file AT OR BEFORE the session date with no lower
# bound, so an arbitrarily old archive would still be drawn -- flagged `stale: true`, but
# drawn. Gamma walls are an OI-positioning read that decays fast; a two-week-old wall is not
# "stale context", it is a wrong line on J's chart, and the entire point of work-order sec 9 is
# that J cannot tell decoration from decision. This is a live hazard, not a hypothetical:
# journal/gex-archive/ has NO file for 2026-09-05 or 2026-09-09, and known-gaps.json records
# neither -- the banker misses days silently (2 prior outages ARE documented there, both
# mechanism "scheduled_task_did_not_fire", both unbackfillable because the CBOE CDN is
# current-day-only). 4 calendar days covers a Fri bank -> Tue read across a long weekend;
# beyond that, emit NOTHING and say why (fail loud, never a quietly wrong level).
MAX_ARCHIVE_STALENESS_DAYS = 4

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(REPO / "backtest") not in sys.path:
    sys.path.insert(0, str(REPO / "backtest"))

from refresh_levels_intraday import (  # noqa: E402 -- reuse, do not re-derive (L251)
    _spy_bars_with_meta,
    _zone_width,
)
from et_clock import et_now  # noqa: E402
from lib.level_strength import compute_vwap, opening_range  # noqa: E402
from lib.engine.gex_regime import GammaContract, compute_gex_regime  # noqa: E402

ET_RTH_START = dt.time(9, 30)
ET_RTH_END = dt.time(16, 0)

DEFAULT_ZONE_WIDTH_PROVENANCE = "default_pre_ab"

# Families this producer knows how to emit. Used by build_context_levels() to report
# exactly what was emitted vs skipped -- never silent about a family it did not produce.
FAMILIES = ("initial_balance", "opening_range_5m", "opening_range_15m", "vwap_bands",
            "prior_day_vwap", "gamma_walls")


# ---------------------------------------------------------------------------
# bar-frame helpers (pure slicing of the frame refresh_levels_intraday already built)
# ---------------------------------------------------------------------------

def _rth_bars(df: pd.DataFrame, session_date: str) -> pd.DataFrame:
    """One session's RTH (09:30-16:00 ET) bars, sorted, reindexed. A pure filter over
    the frame refresh_levels_intraday._spy_bars_with_meta() already produced -- no bar
    loading logic is re-implemented here."""
    sub = df[df["date"] == session_date]
    sub = sub[(sub["ts"].dt.time >= ET_RTH_START) & (sub["ts"].dt.time < ET_RTH_END)]
    return sub.sort_values("ts").reset_index(drop=True)


def _as_opening_range_frame(rth: pd.DataFrame) -> pd.DataFrame:
    """backtest.lib.level_strength.opening_range() expects a `timestamp_et` column;
    refresh_levels_intraday's own convention is `ts`. Rename only -- the frame itself
    (and everything that produced it) is untouched."""
    return rth.rename(columns={"ts": "timestamp_et"})


def _make_context_level(*, family: str, type_: str, session_date: str, role: str | None,
                         label: str, source: str, zone_width: float,
                         zone_width_provenance: str, price: float | None = None,
                         high: float | None = None, low: float | None = None,
                         n_bars: int | None = None) -> dict:
    lv: dict = {
        "family": family,
        "type": type_,
        "session_date": session_date,
        "role": role,
        "label": label,
        "source": source,
        # Every context level carries BOTH fields -- never hand-pick a bare number
        # without saying where it came from (#9.13 B).
        "zone_width": round(float(zone_width), 4),
        "zone_width_provenance": zone_width_provenance,
    }
    if price is not None:
        lv["price"] = round(float(price), 2)
    if high is not None:
        lv["high"] = round(float(high), 2)
    if low is not None:
        lv["low"] = round(float(low), 2)
    if n_bars is not None:
        lv["n_bars"] = int(n_bars)
    return lv


def _range_zone_width(hi: float, lo: float, center_price: float) -> tuple[float, str]:
    """Observed-range zone width, mirroring refresh_levels_intraday's existing
    `shelf_band_observed` convention (zone_width = half the observed range) -- this is
    a MEASURED quantity, not a hand-picked one. Falls back to the ratified default only
    when the range is degenerate (hi <= lo, e.g. a single-bar window)."""
    if hi > lo:
        return round((hi - lo) / 2, 4), "ib_or_range_observed"
    return _zone_width(center_price), DEFAULT_ZONE_WIDTH_PROVENANCE


# ---------------------------------------------------------------------------
# 1. Initial balance -- 2. Opening range (5m / 15m)
# ---------------------------------------------------------------------------

def compute_initial_balance(rth: pd.DataFrame, session_date: str) -> dict | None:
    """09:30-10:30 ET high/low. Just opening_range(minutes=60) starting from the open
    -- IB IS a 60-minute opening range, so no separate window-slicing logic is written."""
    orng = opening_range(_as_opening_range_frame(rth), minutes=60)
    if orng is None:
        return None
    zw, prov = _range_zone_width(orng.high, orng.low, (orng.high + orng.low) / 2)
    return _make_context_level(
        family="initial_balance", type_="initial_balance", session_date=session_date,
        role="range", high=orng.high, low=orng.low, zone_width=zw, zone_width_provenance=prov,
        label="INITIAL BALANCE", source=f"09:30-10:30 ET RTH bars, {session_date}",
    )


def compute_opening_range(rth: pd.DataFrame, minutes: int, session_date: str) -> dict | None:
    orng = opening_range(_as_opening_range_frame(rth), minutes=minutes)
    if orng is None:
        return None
    zw, prov = _range_zone_width(orng.high, orng.low, (orng.high + orng.low) / 2)
    return _make_context_level(
        family="opening_range", type_=f"opening_range_{minutes}m", session_date=session_date,
        role="range", high=orng.high, low=orng.low, zone_width=zw, zone_width_provenance=prov,
        label=f"OPENING RANGE {minutes}M", source=f"first {minutes}m of RTH, {session_date}",
    )


# ---------------------------------------------------------------------------
# 3. Session VWAP +/- 1sigma/2sigma -- 4. Prior-day VWAP
# ---------------------------------------------------------------------------

def _vwap_zone_width(snap, price: float) -> tuple[float, str]:
    """The stdev compute_vwap() ALREADY computed (upper_1sigma - vwap) IS the natural,
    measured zone width for a VWAP-family level -- reusing it, not hand-picking a new
    number, and not re-deriving the stdev a second time."""
    stdev = snap.upper_1sigma - snap.vwap
    if stdev > 0:
        return round(stdev, 4), "vwap_sigma_observed"
    return _zone_width(price), DEFAULT_ZONE_WIDTH_PROVENANCE


def compute_vwap_bands(rth: pd.DataFrame, session_date: str) -> list[dict]:
    snap = compute_vwap(rth)
    if snap is None:
        return []
    out = []
    for type_, price, role in (
        ("session_vwap", snap.vwap, "pivot"),
        ("vwap_upper_1sigma", snap.upper_1sigma, "resistance"),
        ("vwap_lower_1sigma", snap.lower_1sigma, "support"),
        ("vwap_upper_2sigma", snap.upper_2sigma, "resistance"),
        ("vwap_lower_2sigma", snap.lower_2sigma, "support"),
    ):
        zw, prov = _vwap_zone_width(snap, price)
        out.append(_make_context_level(
            family="vwap", type_=type_, session_date=session_date, role=role, price=price,
            zone_width=zw, zone_width_provenance=prov,
            label=type_.upper().replace("_", " "),
            source=f"session VWAP, {session_date} RTH bars ({snap.bars_in_calc} bars)",
            n_bars=snap.bars_in_calc,
        ))
    return out


def compute_prior_day_vwap(spy_full: pd.DataFrame, session_date: str) -> dict | None:
    prior_dates = sorted(d for d in spy_full["date"].unique() if d < session_date)
    if not prior_dates:
        return None
    prior_date = prior_dates[-1]
    prior_rth = _rth_bars(spy_full, prior_date)
    if prior_rth.empty:
        return None
    snap = compute_vwap(prior_rth)
    if snap is None:
        return None
    zw, prov = _vwap_zone_width(snap, snap.vwap)
    return _make_context_level(
        family="prior_day_vwap", type_="prior_day_vwap", session_date=session_date, role="pivot",
        price=snap.vwap, zone_width=zw, zone_width_provenance=prov,
        label="PRIOR DAY VWAP", source=f"prior session {prior_date} RTH VWAP ({snap.bars_in_calc} bars)",
        n_bars=snap.bars_in_calc,
    )


# ---------------------------------------------------------------------------
# 5. Gamma walls -- ONLY via the already-wired free CBOE banker (OP-3/C36)
# ---------------------------------------------------------------------------

def _latest_cboe_archive(on_or_before: str) -> Path | None:
    """Most recent already-banked CBOE archive file at or before `on_or_before`
    (YYYY-MM-DD). Reads only what Gamma_CboeOiBank (registered 2026-06-22, $0, free
    CBOE CDN, `backtest/tools/cboe_oi_bank.py`) has already written to
    journal/gex-archive/{date}-cboe.json -- this function performs NO network fetch."""
    if not GEX_ARCHIVE_DIR.exists():
        return None
    candidates = sorted(GEX_ARCHIVE_DIR.glob("*-cboe.json"))
    dated = [p for p in candidates if p.stem[:-5] <= on_or_before]  # strip "-cboe" suffix
    return dated[-1] if dated else None


def compute_gamma_walls(session_date: str) -> list[dict]:
    """Call-wall / put-wall context levels from the already-wired free CBOE OI+gamma
    archive. Emits nothing (not a proxy, not an estimate) if no banked archive exists
    at all -- see build_context_levels()'s `families_skipped` for the reason when that
    happens. Reuses gex_regime.compute_gex_regime/GammaContract verbatim; only adapts
    the CBOE wire shape (strike/right/gamma/open_interest fields already present in the
    banked JSON) into GammaContract rows."""
    path = _latest_cboe_archive(session_date)
    if path is None:
        return []
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    spy = (doc.get("by_symbol") or {}).get("SPY") or {}
    raw_contracts = spy.get("contracts") or []
    spot = spy.get("spot")
    if not raw_contracts or spot is None:
        return []
    contracts = [
        GammaContract(
            strike=float(c["strike"]), option_type=str(c["right"]),
            gamma=float(c.get("gamma") or 0.0), open_interest=float(c.get("open_interest") or 0.0),
        )
        for c in raw_contracts
        if c.get("strike") is not None and c.get("right") is not None
    ]
    if not contracts:
        return []
    regime = compute_gex_regime(contracts, float(spot))
    archive_date = path.stem[:-5]  # "YYYY-MM-DD-cboe" -> "YYYY-MM-DD"
    stale = archive_date != session_date
    try:
        staleness_days = (dt.date.fromisoformat(session_date) - dt.date.fromisoformat(archive_date)).days
    except ValueError:
        return []  # unparseable date on either side -> refuse to guess
    if staleness_days > MAX_ARCHIVE_STALENESS_DAYS:
        return []  # too old to be context; build_context_levels records the reason
    out = []
    for wall_label, wall, role in (
        ("call_wall", regime.call_wall, "resistance"),
        ("put_wall", regime.put_wall, "support"),
    ):
        if wall is None:
            continue
        # A strike is a single price with no observed spread of its own -- fall back to
        # the ratified default, honestly labeled (never invent an "observed" provenance
        # for a number that was not measured).
        zw = _zone_width(wall.strike)
        lv = _make_context_level(
            family="gamma_wall", type_=wall_label, session_date=session_date, role=role,
            price=wall.strike, zone_width=zw, zone_width_provenance=DEFAULT_ZONE_WIDTH_PROVENANCE,
            label=wall_label.upper().replace("_", " "),
            source=f"CBOE OI+gamma archive {archive_date} (Gamma_CboeOiBank, $0)"
                   + (f" -- STALE, session is {session_date}" if stale else ""),
        )
        lv["gex_notional"] = round(float(wall.gex_notional), 2)
        lv["archive_date"] = archive_date
        lv["stale"] = stale
        lv["staleness_days"] = staleness_days
        out.append(lv)
    return out


# ---------------------------------------------------------------------------
# assembly + write
# ---------------------------------------------------------------------------

def build_context_levels(spy_full: pd.DataFrame, session_date: str) -> dict:
    rth = _rth_bars(spy_full, session_date)
    levels: list[dict] = []
    emitted: list[str] = []
    skipped: dict[str, str] = {}

    ib = compute_initial_balance(rth, session_date)
    if ib:
        levels.append(ib)
        emitted.append("initial_balance")
    else:
        skipped["initial_balance"] = "insufficient RTH bars in the 09:30-10:30 window"

    for minutes in (5, 15):
        key = f"opening_range_{minutes}m"
        orr = compute_opening_range(rth, minutes, session_date)
        if orr:
            levels.append(orr)
            emitted.append(key)
        else:
            skipped[key] = f"insufficient RTH bars in the first {minutes}m"

    vwap_levels = compute_vwap_bands(rth, session_date)
    if vwap_levels:
        levels.extend(vwap_levels)
        emitted.append("vwap_bands")
    else:
        skipped["vwap_bands"] = "no RTH bars / zero volume for session VWAP"

    pdv = compute_prior_day_vwap(spy_full, session_date)
    if pdv:
        levels.append(pdv)
        emitted.append("prior_day_vwap")
    else:
        skipped["prior_day_vwap"] = "no prior session RTH bars available"

    walls = compute_gamma_walls(session_date)
    if walls:
        levels.extend(walls)
        emitted.append("gamma_walls")
    else:
        skipped["gamma_walls"] = (
            "no banked CBOE OI+gamma archive found under journal/gex-archive/ "
            "(Gamma_CboeOiBank is wired but has not banked a usable snapshot yet) "
            "-- emitting nothing rather than a proxy"
        )

    return {
        "schema_version": 1,
        "generated_at": et_now().isoformat(),
        "session_date": session_date,
        "levels": levels,
        "families_known": list(FAMILIES),
        "families_emitted": emitted,
        "families_skipped": skipped,
    }


def _write_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    tmp.replace(path)


def main() -> int:
    df, _meta = _spy_bars_with_meta()
    if df is None or df.empty:
        print("SKIP: no SPY bars available (context-levels.json not updated)")
        return 0
    session_date = sorted(df["date"].unique())[-1]
    out = build_context_levels(df, session_date)
    _write_atomic(CONTEXT_LEVELS, out)
    print(
        f"OK session={session_date} levels={len(out['levels'])} "
        f"emitted={out['families_emitted']} skipped={list(out['families_skipped'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

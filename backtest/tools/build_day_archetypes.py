"""build_day_archetypes.py -- WS6 REGIME LIBRARY builder (2026-08-01).

Tags every trading day in the verified population window (2025-01-02..2026-07-31,
extending forward as the rolling feed appends) with ONE deterministic day-archetype
computed from RTH 5m OHLC alone. No LLM, no indicators, no network. Byte-identical
re-run given identical input files (sorted keys, fixed rounding, no timestamps in
the artifact body -- provenance is carried as input-file sha256 hashes instead).

ARTIFACT:  analysis/regime-library/day-archetypes.json
CONSUMER:  backtest/lib/regime_slice.py (per-archetype slicing for any study)
STAMP:     automation/scripts/regime_stamp.py (premarket "yesterday was X" line)
GUARDS:    backtest/tests/test_regime_library_guards.py
DOC:       analysis/regime-library/README.md

DATA LINEAGE (pinned, mirrors g2_trendline_bypass_ab_2026_08_01.py):
    spy_5m_2025-01-01_2026-07-22.csv   master, authoritative through 2026-07-22
                                       (UNTOUCHED by the 2026-07-31 OPRA backfill)
    spy_5m_2026-05-19_*.csv            rolling feed, supplies days AFTER 2026-07-22
                                       (resolved by newest end-date in filename so
                                       tomorrow's append is picked up automatically)
    vix_5m_ (same two-file lineage)    VIX session open/close attach
The 2024 backfill lineage (spy_5m_2024-*) is deliberately NOT read -- the verified
study population starts 2025-01-02 (feed seams are a known corruption source).

FRAME DECISION: et-v2 (DST-correct), explicitly opted in per backtest/lib/et_frame.py.
This is a NEW pipeline with no wall-v1-era scorecard to stay comparable with, and
wall-v1 would CLIP the last true trading hour on the 129+ EST-month days, corrupting
session close/high/low -- exactly what a day-shape library cannot afford.

ARCHETYPES (first match wins -- precedence documented in PRECEDENCE):
    gap-fade     significant gap that FILLS (touches prior close) and closes back
                 through the open against the gap direction
    gap-go       significant gap that NEVER fills and closes beyond the open in the
                 gap direction
    V-reversal   early/mid low, deep excursion below open, strong close near high
    inverted-V   early/mid high, big pop above open, weak close near low
    trend-up     big up body, opens near low, closes near high
    trend-down   big down body, opens near high, closes near low
    pin-day      tiny range AND tiny body -- closes where it opened
    range-chop   residual class: none of the above mechanisms resolved
Days with n_bars < MIN_BARS_ASSIGNABLE get archetype "data-incomplete" and are
EXCLUDED from distribution stats (loud, never silent -- C7).

Thresholds are FROZEN at spec_version 1.0.0. They were chosen by inspection of the
population distribution during the 2026-08-01 build (descriptive taxonomy design,
not a fitted trading signal -- no P&L touched this choice). Any change = version
bump + rebuild + guard update.

Usage:
    backtest/.venv python backtest/tools/build_day_archetypes.py           # build
    backtest/.venv python backtest/tools/build_day_archetypes.py --check  # verify
        (re-derives the artifact in memory and exits 1 if bytes differ from disk)
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKTEST = REPO / "backtest"
for _p in (str(BACKTEST),):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pandas as pd  # noqa: E402

from lib.et_frame import parse_timestamp_et  # noqa: E402

DATA = BACKTEST / "data"
OUT_DIR = REPO / "analysis" / "regime-library"
OUT_JSON = OUT_DIR / "day-archetypes.json"

SPY_MASTER = DATA / "spy_5m_2025-01-01_2026-07-22.csv"
VIX_MASTER = DATA / "vix_5m_2025-01-01_2026-07-22.csv"
MASTER_END = dt.date(2026, 7, 22)          # rolling files supply days AFTER this
ROLLING_SPY_GLOB = "spy_5m_2026-05-19_*.csv"
ROLLING_VIX_GLOB = "vix_5m_2026-05-19_*.csv"

POP_START = dt.date(2025, 1, 2)
VERIFIED_END = dt.date(2026, 7, 31)        # frozen verified-population end marker

SPEC_VERSION = "1.0.0"

# ---- classification constants (FROZEN at 1.0.0; document any change) ----------
GAP_SIG_PCT = 0.30          # |gap| >= 0.30% of prior close = significant gap
SHAPE_MIN_RANGE_PCT = 0.50  # V shapes need a real range to mean anything
V_DEPTH_FRAC = 0.55         # excursion beyond open >= 55% of the day's range
V_CLOSE_LOC = 0.70          # V-reversal closes in top 30% of range
IV_CLOSE_LOC = 0.30         # inverted-V closes in bottom 30%
V_TIME_FRAC = 0.50          # extreme printed in the first half of the session
TREND_BODY_PCT = 0.60       # |close-open| >= 0.60% of open = trend body
TREND_CLOSE_LOC = 0.75      # trend-up closes in top quartile
TREND_OPEN_LOC = 0.40       # trend-up opens in bottom 40% of range
PIN_RANGE_PCT = 0.50        # pin-day: whole range <= 0.50% ...
PIN_BODY_PCT = 0.12         # ... and body <= 0.12% (closes where it opened)
MIN_BARS_ASSIGNABLE = 30    # below this the session is data-incomplete
FULL_SESSION_BARS = 78
HALF_DAY_MAX_BARS = 50      # 42..46-bar exchange early closes
RECENT_N = 25

ARCHETYPES = (
    "trend-up", "trend-down", "V-reversal", "inverted-V",
    "range-chop", "pin-day", "gap-go", "gap-fade",
)
PRECEDENCE = (
    "gap-fade", "gap-go", "V-reversal", "inverted-V",
    "trend-up", "trend-down", "pin-day", "range-chop",
)
DATA_INCOMPLETE = "data-incomplete"

_END_DATE_RE = re.compile(r"_(\d{4}-\d{2}-\d{2})\.csv$")


# ---------------------------------------------------------------------------
# data loading
# ---------------------------------------------------------------------------

def _rolling_latest(glob_pat: str) -> Path:
    """Newest end-date file of the rolling lineage (compute_ema_snapshot fix 2026-06-28:
    end-date parsed from filename, never st_size/mtime)."""
    def end_date(p: Path) -> dt.date:
        m = _END_DATE_RE.search(p.name)
        return dt.date.fromisoformat(m.group(1)) if m else dt.date.min
    cands = sorted(DATA.glob(glob_pat), key=end_date, reverse=True)
    if not cands:
        raise FileNotFoundError(f"no rolling file matches {glob_pat} in {DATA}")
    return cands[0]


def _load_rth(path: Path) -> pd.DataFrame:
    """Load one CSV -> RTH-only frame with naive TRUE-ET timestamps (et-v2)."""
    df = pd.read_csv(path)
    df["ts"] = parse_timestamp_et(df["timestamp_et"], frame="et-v2")
    df = df.drop_duplicates(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    t = df["ts"].dt.time
    rth = df[(t >= dt.time(9, 30)) & (t < dt.time(16, 0))].copy()
    rth["date"] = rth["ts"].dt.date
    for col in ("open", "high", "low", "close"):
        rth[col] = pd.to_numeric(rth[col], errors="coerce")
    return rth.dropna(subset=["open", "high", "low", "close"])


def load_sessions() -> tuple[dict, dict, dict]:
    """Return (spy_days, vix_days, input_hashes).

    spy_days: {date: DataFrame of RTH 5m bars}  master <= MASTER_END, rolling after.
    vix_days: {date: (vix_open, vix_close)} first/last in-RTH-window row per day.
    """
    spy_roll = _rolling_latest(ROLLING_SPY_GLOB)
    vix_roll = _rolling_latest(ROLLING_VIX_GLOB)
    inputs = {}
    for p in (SPY_MASTER, VIX_MASTER, spy_roll, vix_roll):
        inputs[p.name] = hashlib.sha256(p.read_bytes()).hexdigest()

    m = _load_rth(SPY_MASTER)
    r = _load_rth(spy_roll)
    spy = pd.concat(
        [m[(m["date"] >= POP_START) & (m["date"] <= MASTER_END)],
         r[r["date"] > MASTER_END]],
        ignore_index=True,
    )
    spy_days = {d: g.sort_values("ts").reset_index(drop=True)
                for d, g in spy.groupby("date")}

    vm = _load_rth(VIX_MASTER)
    vr = _load_rth(vix_roll)
    vix = pd.concat(
        [vm[(vm["date"] >= POP_START) & (vm["date"] <= MASTER_END)],
         vr[vr["date"] > MASTER_END]],
        ignore_index=True,
    )
    vix_days = {}
    for d, g in vix.groupby("date"):
        g = g.sort_values("ts")
        vix_days[d] = (float(g.iloc[0]["open"]), float(g.iloc[-1]["close"]))
    return spy_days, vix_days, inputs


# ---------------------------------------------------------------------------
# feature extraction + classification (pure functions -- unit-tested)
# ---------------------------------------------------------------------------

def day_features(bars: pd.DataFrame, prior_close: float | None) -> dict:
    """OHLC-alone shape features for one session. bars = RTH 5m rows, ts-sorted."""
    o = float(bars.iloc[0]["open"])
    h = float(bars["high"].max())
    l = float(bars["low"].min())
    c = float(bars.iloc[-1]["close"])
    n = len(bars)
    rng = h - l
    denom = max(n - 1, 1)
    # numpy argmax/argmin return the FIRST occurrence -- deterministic tie-break
    t_high = float(bars["high"].values.argmax()) / denom
    t_low = float(bars["low"].values.argmin()) / denom
    return {
        "open": o, "high": h, "low": l, "close": c, "n_bars": n,
        "prior_close": prior_close,
        "gap_pct": (100.0 * (o - prior_close) / prior_close) if prior_close else None,
        "range_dollars": rng,
        "range_pct": 100.0 * rng / o if o else 0.0,
        "body_pct": 100.0 * (c - o) / o if o else 0.0,
        "close_loc": (c - l) / rng if rng > 0 else 0.5,
        "open_loc": (o - l) / rng if rng > 0 else 0.5,
        "t_high": t_high, "t_low": t_low,
    }


def classify(f: dict) -> str:
    """Deterministic archetype from a day_features dict. First match in PRECEDENCE wins."""
    if f["n_bars"] < MIN_BARS_ASSIGNABLE:
        return DATA_INCOMPLETE
    o, h, l, c = f["open"], f["high"], f["low"], f["close"]
    gap, rng = f["gap_pct"], f["range_dollars"]
    pc = f["prior_close"]

    # 1-2. gap mechanisms (only when the gap is significant AND resolved)
    if gap is not None and pc is not None:
        if gap >= GAP_SIG_PCT:
            if l <= pc and c <= o:
                return "gap-fade"           # filled the gap, closed back below open
            if l > pc and c > o:
                return "gap-go"             # never filled, continued up
        elif gap <= -GAP_SIG_PCT:
            if h >= pc and c >= o:
                return "gap-fade"           # filled the gap, closed back above open
            if h < pc and c < o:
                return "gap-go"             # never filled, continued down

    # 3-4. reversal shapes
    if f["range_pct"] >= SHAPE_MIN_RANGE_PCT and rng > 0:
        if (f["t_low"] <= V_TIME_FRAC and (o - l) >= V_DEPTH_FRAC * rng
                and f["close_loc"] >= V_CLOSE_LOC):
            return "V-reversal"
        if (f["t_high"] <= V_TIME_FRAC and (h - o) >= V_DEPTH_FRAC * rng
                and f["close_loc"] <= IV_CLOSE_LOC):
            return "inverted-V"

    # 5-6. trend days
    if (f["body_pct"] >= TREND_BODY_PCT and f["close_loc"] >= TREND_CLOSE_LOC
            and f["open_loc"] <= TREND_OPEN_LOC):
        return "trend-up"
    if (f["body_pct"] <= -TREND_BODY_PCT and f["close_loc"] <= (1.0 - TREND_CLOSE_LOC)
            and f["open_loc"] >= (1.0 - TREND_OPEN_LOC)):
        return "trend-down"

    # 7. pin
    if f["range_pct"] <= PIN_RANGE_PCT and abs(f["body_pct"]) <= PIN_BODY_PCT:
        return "pin-day"

    # 8. residual
    return "range-chop"


def session_flag(n_bars: int) -> str:
    if n_bars < MIN_BARS_ASSIGNABLE:
        return "incomplete"
    if n_bars <= HALF_DAY_MAX_BARS:
        return "half-day"
    if n_bars < FULL_SESSION_BARS:
        return "truncated-tail"
    return "full"


def _r(x, nd=4):
    return None if x is None else round(float(x), nd)


def build_days(spy_days: dict, vix_days: dict) -> dict:
    """{iso_date: day-record} over all sessions, in date order."""
    out = {}
    prior_close = None
    prior_trs: list[float] = []          # true-range %s of prior days (for ATR14)
    for d in sorted(spy_days.keys()):
        bars = spy_days[d]
        f = day_features(bars, prior_close)
        arch = classify(f)
        atr = _r(sum(prior_trs[-14:]) / len(prior_trs[-14:])) if prior_trs else None
        vo, vc = vix_days.get(d, (None, None))
        out[d.isoformat()] = {
            "archetype": arch,
            "session": session_flag(f["n_bars"]),
            "n_bars": f["n_bars"],
            "open": _r(f["open"], 2), "high": _r(f["high"], 2),
            "low": _r(f["low"], 2), "close": _r(f["close"], 2),
            "prior_close": _r(f["prior_close"], 2),
            "gap_pct": _r(f["gap_pct"]),
            "range_dollars": _r(f["range_dollars"], 2),
            "range_pct": _r(f["range_pct"]),
            "body_pct": _r(f["body_pct"]),
            "close_loc": _r(f["close_loc"]),
            "open_loc": _r(f["open_loc"]),
            "t_high": _r(f["t_high"]), "t_low": _r(f["t_low"]),
            "atr14_prior_pct": atr,
            "vix_open": _r(vo, 2), "vix_close": _r(vc, 2),
            "dow": d.strftime("%a"),
        }
        # roll state forward (incomplete sessions still advance prior_close --
        # their close is the last bar we HAVE; disclosed via session flag)
        if f["prior_close"] is not None:
            tr = max(f["high"], f["prior_close"]) - min(f["low"], f["prior_close"])
            prior_trs.append(100.0 * tr / f["prior_close"])
        prior_close = f["close"]
    return out


def build_distribution(days: dict) -> dict:
    """Full-population vs last-RECENT_N mix over ASSIGNABLE days only."""
    assignable = [(d, rec) for d, rec in sorted(days.items())
                  if rec["archetype"] != DATA_INCOMPLETE]
    full_counts = {a: 0 for a in ARCHETYPES}
    for _, rec in assignable:
        full_counts[rec["archetype"]] += 1
    recent = assignable[-RECENT_N:]
    recent_counts = {a: 0 for a in ARCHETYPES}
    for _, rec in recent:
        recent_counts[rec["archetype"]] += 1
    n_full = len(assignable) or 1
    n_recent = len(recent) or 1
    full_pct = {a: _r(100.0 * full_counts[a] / n_full, 1) for a in ARCHETYPES}
    recent_pct = {a: _r(100.0 * recent_counts[a] / n_recent, 1) for a in ARCHETYPES}
    l1 = _r(sum(abs(full_counts[a] / n_full - recent_counts[a] / n_recent)
                for a in ARCHETYPES))
    return {
        "n_assignable": len(assignable),
        "full_counts": full_counts,
        "full_pct": full_pct,
        "last_25_counts": recent_counts,
        "last_25_pct": recent_pct,
        "last_25_window": [recent[0][0], recent[-1][0]] if recent else [],
        "mix_l1_distance": l1,
        "top_full": max(ARCHETYPES, key=lambda a: (full_counts[a], a)),
        "top_last_25": max(ARCHETYPES, key=lambda a: (recent_counts[a], a)),
    }


def build_artifact() -> dict:
    spy_days, vix_days, inputs = load_sessions()
    days = build_days(spy_days, vix_days)
    dist = build_distribution(days)
    sessions = {"full": 0, "half-day": 0, "truncated-tail": 0, "incomplete": 0}
    for rec in days.values():
        sessions[rec["session"]] += 1
    all_dates = sorted(days.keys())
    return {
        "spec_version": SPEC_VERSION,
        "note": ("Deterministic day-archetype library. Byte-identical re-run given "
                 "identical inputs. Post-hoc DESCRIPTIVE taxonomy -- distinct from "
                 "backtest/lib/regime_classifier.py (pre-open lookahead-safe router). "
                 "No trading verdicts."),
        "population": {
            "start": all_dates[0],
            "data_end": all_dates[-1],
            "verified_window": {"start": POP_START.isoformat(),
                                "end": VERIFIED_END.isoformat()},
            "data_days": len(days),
            "assignable_days": dist["n_assignable"],
            "sessions": sessions,
            "incomplete_dates": sorted(d for d, rec in days.items()
                                       if rec["session"] == "incomplete"),
            "accounting_note": ("data_days counts every session present in the pinned "
                                "lineage; replay-population figures quoted elsewhere "
                                "(e.g. 391) may exclude short/broken sessions -- join "
                                "on date, never on count."),
        },
        "inputs_sha256": inputs,
        "thresholds": {
            "GAP_SIG_PCT": GAP_SIG_PCT, "SHAPE_MIN_RANGE_PCT": SHAPE_MIN_RANGE_PCT,
            "V_DEPTH_FRAC": V_DEPTH_FRAC, "V_CLOSE_LOC": V_CLOSE_LOC,
            "IV_CLOSE_LOC": IV_CLOSE_LOC, "V_TIME_FRAC": V_TIME_FRAC,
            "TREND_BODY_PCT": TREND_BODY_PCT, "TREND_CLOSE_LOC": TREND_CLOSE_LOC,
            "TREND_OPEN_LOC": TREND_OPEN_LOC, "PIN_RANGE_PCT": PIN_RANGE_PCT,
            "PIN_BODY_PCT": PIN_BODY_PCT,
            "MIN_BARS_ASSIGNABLE": MIN_BARS_ASSIGNABLE,
            "HALF_DAY_MAX_BARS": HALF_DAY_MAX_BARS,
            "FULL_SESSION_BARS": FULL_SESSION_BARS, "RECENT_N": RECENT_N,
        },
        "precedence": list(PRECEDENCE),
        "archetypes": list(ARCHETYPES),
        "distribution": dist,
        "days": days,
    }


def serialize(artifact: dict) -> bytes:
    return (json.dumps(artifact, indent=1, sort_keys=True, ensure_ascii=True)
            + "\n").encode("ascii")


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the day-archetype regime library")
    ap.add_argument("--check", action="store_true",
                    help="re-derive and compare bytes against the on-disk artifact")
    args = ap.parse_args()

    payload = serialize(build_artifact())
    if args.check:
        if not OUT_JSON.exists():
            print(f"[FAIL] artifact missing: {OUT_JSON}")
            return 1
        on_disk = OUT_JSON.read_bytes()
        if on_disk == payload:
            print(f"[OK] {OUT_JSON.name} is byte-identical to a fresh rebuild "
                  f"({len(payload)} bytes)")
            return 0
        print(f"[FAIL] {OUT_JSON.name} differs from a fresh rebuild "
              f"(disk {len(on_disk)}B vs rebuild {len(payload)}B) -- inputs moved "
              f"or artifact is stale; re-run the builder")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Atomic write (2026-09-04, L-pending): a plain write_bytes() truncates-then-writes
    # in place, so a reader that lands mid-write (e.g. this project's own 12,000+-test
    # full suite calling regime_slice.load_library() while this builder happens to be
    # re-run by a parallel session) can see a torn/incomplete JSON body. Same class as
    # the STATUS.md writer bug fixed 2026-09-03 (_find_real_heading); the fix here is
    # the same idiom already used by backtest/autoresearch/trendline_watch.py and the
    # futures/ writers -- write to a same-directory temp file, then os.replace() so any
    # concurrent reader always sees either the complete old file or the complete new one,
    # never a partial one.
    tmp = OUT_JSON.with_suffix(OUT_JSON.suffix + ".tmp")
    tmp.write_bytes(payload)
    os.replace(tmp, OUT_JSON)
    art = json.loads(payload)
    dist = art["distribution"]
    print(f"[OK] wrote {OUT_JSON} ({len(payload)} bytes)")
    print(f"     days={art['population']['data_days']} "
          f"assignable={art['population']['assignable_days']} "
          f"sessions={art['population']['sessions']}")
    print(f"     full mix:    {dist['full_counts']}")
    print(f"     last-25 mix: {dist['last_25_counts']} "
          f"window={dist['last_25_window']} L1={dist['mix_l1_distance']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

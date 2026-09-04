"""WP-2 — CONTEXT PARITY. The inputs the forked filters were designed against.

THE PROBLEM THIS SOLVES (fidelity audit, root cause #2): `multi/core.py` called `build_signal`
with bars and levels only. `vix_now`, `vix_prior`, `vix_5d_ma`, `vix_20d_ma`, `htf_15m_bars`,
`level_states` and `fhh_level` were all `None`/`0.0`. The SPY engine feeds every one of those
on every tick. A scoring engine given half its inputs is a different strategy wearing the same
code, and 178/178 HOLD was the arithmetic consequence.

THREE CONTEXT FAMILIES, all lane-owned (the SPY lane's state files are never read — separation):

  1. VIX regime      -- real ^VIX via yfinance (already a project dependency). Alpaca does not
                        serve the index (verified: /v1beta1/indices 404s), and VIXY is an ETF
                        proxy whose level is NOT the index — using it would silently feed the
                        filters a number that looks like VIX and is not.
  2. HTF 15m stack   -- supplied by the caller from the batch bar fetch; this module only
                        documents the contract, since the fetch belongs to core.
  3. Level states    -- per-symbol reclaim/reject MEMORY across ticks. This is the machinery
                        J's stated philosophy actually runs on: "wait for the RETURN to the
                        zone." Without it a level has no history, so `sequence_rejection` /
                        `sequence_reclaim` can never fire and filter 10's level-tied trigger
                        set is permanently one member short.

DEGRADED, NEVER SILENT. A stale or unavailable feed returns an explicit degraded marker that
the caller raises into the participation cascade. It never substitutes a plausible number.
That distinction is the exact class that cost this lane a trading day (an HTTP 400 wearing the
costume of "no quote"), so the boundary here classifies rather than collapses.
"""

from __future__ import annotations

import datetime as dt
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = REPO_ROOT / "automation" / "state" / "multi"
VIX_CACHE = STATE_DIR / "vix.json"
ET = ZoneInfo("America/New_York")

# A VIX read older than this during RTH is stale. 20 minutes is deliberately loose: the daily
# MAs move slowly and a slightly old spot VIX is far better than none, but a feed that has been
# dark for a third of an hour is a real outage and must surface.
VIX_STALE_MINUTES = 20


class ContextError(RuntimeError):
    """Raised only for programmer errors (bad args). Feed outages DEGRADE, they do not raise."""


@dataclass(frozen=True)
class VixContext:
    now: Optional[float]
    prior: Optional[float]
    ma_5d: float
    ma_20d: float
    as_of_et: Optional[str]
    degraded: bool
    reason: Optional[str] = None

    def as_kwargs(self) -> dict:
        """The exact kwargs `build_signal` expects. Degraded => Nones/0.0, never a guess."""
        return {"vix_now": self.now, "vix_prior": self.prior,
                "vix_5d_ma": self.ma_5d, "vix_20d_ma": self.ma_20d}


def _now_et() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).astimezone(ET)


def fetch_vix(*, cache_path: Path = VIX_CACHE, max_age_min: int = VIX_STALE_MINUTES) -> VixContext:
    """Real ^VIX + 5/20-day MAs. Cached; degrades explicitly rather than fabricating."""
    now = _now_et()

    cached = None
    if cache_path.exists():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            cached = None  # a corrupt cache is a miss, not a crash -- we refetch below
    if cached:
        try:
            age = (now - dt.datetime.fromisoformat(cached["as_of_et"])).total_seconds() / 60.0
            if age <= max_age_min:
                return VixContext(now=cached["now"], prior=cached["prior"],
                                  ma_5d=cached["ma_5d"], ma_20d=cached["ma_20d"],
                                  as_of_et=cached["as_of_et"], degraded=False)
        except (KeyError, TypeError, ValueError):
            pass  # malformed cache -> refetch

    try:
        import yfinance as yf
        hist = yf.Ticker("^VIX").history(period="60d", interval="1d")
        closes = [float(x) for x in hist["Close"] if x == x]  # drop NaN
        if len(closes) < 21:
            return VixContext(None, None, 0.0, 0.0, None, True,
                              f"only {len(closes)} VIX closes; need 21 for a 20d MA")
        ctx = VixContext(
            now=round(closes[-1], 2), prior=round(closes[-2], 2),
            ma_5d=round(sum(closes[-5:]) / 5.0, 3),
            ma_20d=round(sum(closes[-20:]) / 20.0, 3),
            as_of_et=now.isoformat(timespec="seconds"), degraded=False,
        )
    except Exception as e:  # noqa: BLE001 -- classified into a degraded state, never swallowed
        if cached:
            return VixContext(cached.get("now"), cached.get("prior"),
                              cached.get("ma_5d", 0.0), cached.get("ma_20d", 0.0),
                              cached.get("as_of_et"), True,
                              f"live fetch failed ({type(e).__name__}); serving STALE cache")
        return VixContext(None, None, 0.0, 0.0, None, True,
                          f"VIX unavailable: {type(e).__name__}: {str(e)[:80]}")

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"now": ctx.now, "prior": ctx.prior, "ma_5d": ctx.ma_5d,
                               "ma_20d": ctx.ma_20d, "as_of_et": ctx.as_of_et}, indent=2),
                   encoding="utf-8")
    tmp.replace(cache_path)
    return ctx


# --- level-state memory ----------------------------------------------------------------------

def _states_path(symbol: str, state_dir: Path = STATE_DIR) -> Path:
    return state_dir / f"level-states-{symbol.upper()}.json"


@dataclass
class LevelStateRec:
    """Mirrors filters.LevelState's contract, persisted across ticks."""
    price: float
    role: Optional[str] = None            # None | broken_to_resistance | broken_to_support
    broken_at_bar_idx: Optional[int] = None
    bounce_history: list = field(default_factory=list)


def update_level_states(symbol: str, levels: list, bars, *, max_bounces: int = 8,
                        state_dir: Path = STATE_DIR) -> dict:
    """Advance each level's memory using CLOSED bars, and persist.

    Role transitions use the same vocabulary the filters read: a level whose closes move from
    above to below becomes `broken_to_resistance` (old support, now overhead), and vice versa.
    `bounce_history` accumulates touch extremes so `sequence_rejection`/`sequence_reclaim` (3+
    progressively lower highs / higher lows) becomes detectable -- it cannot fire at all
    without this history, which is why the lane's filter-10 trigger set was short a member.

    Returns {price: LevelState-shaped object} ready to hand to build_signal.
    """
    if bars is None or len(bars) < 3 or not levels:
        return {}

    # BUG FIX (2026-09-04, found while building the tickers-lane production-scorer adapter):
    # `state_dir` was a DEAD knob for the actual read/write path -- it only drove the mkdir
    # below, while `path` was always derived from the module-level STATE_DIR constant via
    # _states_path(symbol) regardless of what the caller passed. A caller isolating tests with
    # state_dir=<tmp> was silently ALSO writing (and, on a second run, reading stale memory
    # from) the real automation/state/multi/ directory. `_states_path` now takes `state_dir`
    # too so the two actually agree.
    path = _states_path(symbol, state_dir)
    prior: dict = {}
    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            for k, v in (raw.get("levels") or {}).items():
                prior[float(k)] = v
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            prior = {}  # corrupt memory: rebuild rather than crash; it is derived data

    closes = [float(x) for x in bars["close"].to_numpy()]
    highs = [float(x) for x in bars["high"].to_numpy()]
    lows = [float(x) for x in bars["low"].to_numpy()]
    last = closes[-1]
    # Touch band scales with the symbol, never a fixed dollar amount.
    band = max(abs(last) * 0.0015, 1e-6)

    out: dict = {}
    for lv in levels:
        p = round(float(lv), 4)
        rec = prior.get(p) or {}
        role = rec.get("role")
        hist = list(rec.get("bounce_history") or [])

        # Role: derived from where price sits now vs the most recent crossing.
        above = [c > p for c in closes[-40:]]
        if len(set(above)) > 1:
            crossed_to = above[-1]
            role = "broken_to_support" if crossed_to else "broken_to_resistance"

        # Bounce: the newest closed bar touched the band -> record its extreme.
        if lows[-1] - band <= p <= highs[-1] + band:
            extreme = highs[-1] if last < p else lows[-1]
            if not hist or abs(hist[-1] - extreme) > band:
                hist.append(round(extreme, 4))
                hist = hist[-max_bounces:]

        out[p] = LevelStateRec(price=p, role=role, bounce_history=hist)

    state_dir.mkdir(parents=True, exist_ok=True)
    payload = {"symbol": symbol.upper(),
               "updated_et": _now_et().isoformat(timespec="seconds"),
               "levels": {str(k): {"price": v.price, "role": v.role,
                                   "bounce_history": v.bounce_history}
                          for k, v in out.items()}}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)
    return out

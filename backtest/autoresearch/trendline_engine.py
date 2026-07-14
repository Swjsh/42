"""trendline_engine.py -- autonomous swing-pivot trendline detection + respect/break tracking.

Built 2026-06-26 (J: "look how it's being respected... this needs reviewed and logged so you
draw your own trendlines. maybe a skill you can create to utilize"). The manual win: the
9:45->11:15 ascending support held 11 straight 5m bars before its first test.

MULTI-DAY EXTENSION (T8, 2026-07-08 -- HANDOFF-2026-07-09-TRUTH-AND-EXITS): the single-day
version could not structurally represent a real line J trades off that spans multiple days
(e.g. anchored 07-06 15:30 @ 752.29, descending through 07-07's afternoon lower-high). Lookback
is now N_DAYS trading days (default 5) via `fetch_spy_5m_lookback`; `find_pivots`/`_fit` were
ALREADY lookback-agnostic (pure index-based, no per-day reset) so no change was needed there --
verified empirically against real 07-06..07-08 SPY bars (see test_trendline_multiday.py).

WHAT IT DOES (pure stdlib + urllib; NO MCP/LLM/CDP -- the un-blockable data path):
  1. Pull the trailing N_DAYS trading days of RTH 5m SPY bars (direct Alpaca REST, same feed as
     the sight beacon; paginated via next_page_token so a multi-day pull is never truncated).
  2. Find swing pivots (a low/high that is the extreme of a +/-k window) across the WHOLE
     lookback window (not reset per day -- pivots and lines can span day boundaries).
  3. Fit the best ASCENDING-support (through higher-lows) and the best resistance/upper-rail
     (through swing-highs) trendline -- the pair of pivots that is most RESPECTED (touches that
     held) with the fewest closes-through. Anchors are ALWAYS wicks (high/low) for both points of
     a given line -- NEVER a wick paired with a body/close (J's rule) -- structurally guaranteed
     because `_fit` derives both anchor prices through the SAME `px` accessor per kind; guarded
     by `test_no_mixed_wick_body_anchors` in test_trendline_multiday.py.
  4. Score respect_count + classify status INTACT / TESTING / BROKEN, and compute the live
     BREAK LEVEL (a 5m CLOSE beyond the line = Break-of-Structure = signal).
  5. Log every detected line to analysis/trendlines/trendline-log.jsonl (the record J asked for).
  6. Emit TradingView draw_shape anchor params (unix ts + price) so the trendline-draw skill can
     draw it on the chart without re-deriving the math.

A trendline break IS a Break-of-Structure; pair with crypto/lib/market_structure.py (BOS/CHoCH +
HH/HL/LH/LL labels) for the full structure context. This is the manual-to-automatic bridge for
the "engine draws its own trendlines" roadmap item (sits behind the structure-veto wiring).
"""
from __future__ import annotations

# === HEADLESS STDIO REDIRECT (OP-27 L41 layer 3, 2026-07-14 popup-storm fix) =====
# When launched via pythonw.exe (no console), Windows 11's default-terminal setting
# can allocate a visible WindowsTerminal -Embedding window on the FIRST stderr/stdout
# write. Redirect stdio to log files BEFORE any other import gets a chance to write.
# Root-caused live 2026-07-14 (J: "stop the fkin popus on my screen") via the
# re-armed window-leak-detector.py: this exact script, launched wscript->
# run_exe_hidden.vbs->backtest-venv-pythonw with NO relay layer, was caught flashing
# a WindowsTerminal window on a real Start-ScheduledTask fire within 45s.
import os as _os
import sys as _sys
from pathlib import Path as _Path
if _os.path.basename(_sys.executable).lower().startswith("pythonw"):
    _log_dir = _Path(__file__).resolve().parents[2] / "automation" / "state" / "logs"
    _log_dir.mkdir(parents=True, exist_ok=True)
    _sys.stdout = open(_log_dir / "trendline-engine.stdout.log", "a", buffering=1, encoding="utf-8")
    _sys.stderr = open(_log_dir / "trendline-engine.stderr.log", "a", buffering=1, encoding="utf-8")
# ==================================================================================

import json
import math
import sys
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOG = REPO / "analysis" / "trendlines" / "trendline-log.jsonl"
LIVE_STATE = REPO / "automation" / "state" / "trendlines-live.json"  # V4 shadow state (engine-readable)
TOL = 0.10          # $ tolerance for a "touch" and for break confirmation
PIVOT_K = 1         # swing pivot = extreme of a +/-PIVOT_K window
MIN_SPAN = 3        # anchors must be >= this many bars apart (a real trend, not 2 adjacent bars)
N_DAYS = 5          # T8: trailing trading days of lookback (was implicitly 1 -- today only)

# MIN_SPAN=3 stays correct at the N_DAYS=5 scale (~390 RTH bars): it is a MINIMUM floor that
# still lets short, fresh intraday lines qualify (unchanged single-day behavior), while the
# `+ span*0.1` term in _fit's score already rewards LONGER-lived lines on its own -- verified
# against real 07-06..07-08 data that the top-scored multi-day line spans 60+ bars regardless
# of whether MIN_SPAN is 3, 5, or 10 (raising it would only prune SHORT candidates that already
# lose on score, not change which multi-day line wins).

# setup/scripts/et_clock.py is the ONE DST-aware ET source on this rig (never hand-roll -4/-5).
SETUP_SCRIPTS = REPO / "setup" / "scripts"
if str(SETUP_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SETUP_SCRIPTS))
from et_clock import et_offset_hours, et_today_str  # noqa: E402


# --------------------------------------------------------------------------- bars
def _creds() -> tuple[str, str]:
    env = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["alpaca"]["env"]
    return env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]


def fetch_spy_5m(start_utc: str, end_utc: str, limit: int = 1000) -> list[dict]:
    """SPY 5m RTH bars for [start_utc, end_utc], PAGINATED via Alpaca's `next_page_token` cursor
    (T8, 2026-07-08) so a multi-day range is never silently truncated. `sort=asc` end-to-end --
    pagination makes the old sort=desc-then-reverse truncation-avoidance trick unnecessary (it
    existed only because a single un-paginated page could drop the tail of a wide range).
    Single-day callers (trendline_outcomes.py's main()) are unaffected: one page always covers a
    day (78 RTH bars << limit), so this is a strict superset of the old behavior for them."""
    key, sec = _creds()
    base = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=5Min"
            f"&start={start_utc}&end={end_utc}&feed=iex&sort=asc&limit={limit}&adjustment=raw")
    bars: list[dict] = []
    url = base
    for _ in range(20):  # hard cap on pages -- never loop forever on a malformed cursor
        req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
        with urllib.request.urlopen(req, timeout=15) as r:
            payload = json.loads(r.read())
        bars.extend(payload.get("bars", []))
        token = payload.get("next_page_token")
        if not token:
            break
        url = base + f"&page_token={token}"
    bars.sort(key=lambda b: b["t"])  # defensive: guarantee chronological regardless of page order
    # RTH only (09:30-16:00 ET == 13:30-20:00 UTC)
    return [b for b in bars if "13:30:00" <= b["t"][11:19] <= "20:00:00"]


def fetch_spy_5m_lookback(n_days: int = N_DAYS, now: datetime | None = None) -> list[dict]:
    """SPY 5m RTH bars for the trailing `n_days` TRADING days (T8 multi-day lookback).

    ~78 RTH 5m bars/trading day => n_days=5 needs ~390 bars. Pads the CALENDAR window (weekends
    + a little holiday slack) rather than trying to count trading days directly -- the RTH bar
    filter in fetch_spy_5m already drops the non-trading-day noise, so over-fetching calendar
    days is harmless (just a few extra empty-day queries), while under-fetching would silently
    truncate the lookback."""
    now = now or datetime.now(timezone.utc)
    calendar_days = math.ceil(n_days * 7 / 5) + 2  # weekend padding + holiday slack
    start = (now - timedelta(days=calendar_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    return fetch_spy_5m(start, end, limit=1000)


def _et(iso: str) -> str:
    """UTC ISO bar timestamp ('YYYY-MM-DDTHH:MM:SSZ') -> 'MM-DD HH:MM' Eastern.

    T8 (2026-07-08) fix: was a hand-rolled `(h - 4) % 24` -- WRONG by an hour in EST months
    (ground rule: every UTC timestamp converts via et_clock, never a hardcoded offset). Now
    DST-aware via et_clock.et_offset_hours. Also DATE-PREFIXED ('07-06 15:30' not '15:30') --
    a bare 'HH:MM' is ambiguous once a line's two anchors can be on different calendar days
    (multi-day lookback); every consumer (trendline_outcomes.py) only ever compares _et(bar)
    to a Trendline's a_et/b_et -- both sides call this SAME function, so the format change is
    self-consistent and doesn't require touching any consumer.

    Uses plain string-slicing (not datetime.fromisoformat) for the hour/minute/date components
    so it never raises on the synthetic out-of-range-looking timestamps some unit-test fixtures
    build; only the DATE portion feeds et_offset_hours's DST lookup (day-resolution is enough --
    trading never runs across the 2am DST-transition instant)."""
    y, mo, d = int(iso[0:4]), int(iso[5:7]), int(iso[8:10])
    h, m = int(iso[11:13]), int(iso[14:16])
    off = et_offset_hours(datetime(y, mo, d, tzinfo=timezone.utc))
    et_h = (h + off) % 24
    day_shift = (h + off) // 24  # -1 if adding the (negative) offset rolled back a calendar day
    et_date = datetime(y, mo, d) + timedelta(days=day_shift)
    return f"{et_date.month:02d}-{et_date.day:02d} {et_h:02d}:{m:02d}"


def _unix(iso: str) -> int:
    return int(datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


# ------------------------------------------------------------------------- pivots
def find_pivots(bars: list[dict], k: int = PIVOT_K) -> tuple[list[int], list[int]]:
    """(swing_low_indices, swing_high_indices): a bar that is the strict extreme of its +/-k window."""
    lows, highs = [], []
    for i in range(k, len(bars) - k):
        win = bars[i - k:i + k + 1]
        if bars[i]["l"] == min(b["l"] for b in win) and bars[i]["l"] < bars[i + 1]["l"]:
            lows.append(i)
        if bars[i]["h"] == max(b["h"] for b in win) and bars[i]["h"] > bars[i + 1]["h"]:
            highs.append(i)
    return lows, highs


@dataclass(frozen=True)
class Trendline:
    kind: str               # "support" | "resistance"
    a_et: str
    a_price: float
    b_et: str
    b_price: float
    slope_per_bar: float    # $ per 5m bar
    current_et: str
    current_value: float    # line projected to the last bar
    last_close: float
    break_level: float      # a 5m CLOSE beyond this = break
    respect_count: int      # bars that touched the line and held
    violations: int         # bars that closed through it
    status: str             # INTACT | TESTING | BROKEN
    a_unix: int
    b_unix: int
    proj_unix: int          # a forward point ON the line (for drawing)
    proj_price: float

    def summary(self) -> str:
        sign = "below" if self.kind == "support" else "above"
        return (f"{self.kind.upper()} {self.a_et}@{self.a_price:.2f} -> {self.b_et}@{self.b_price:.2f} "
                f"slope {self.slope_per_bar:+.2f}/bar | line now {self.current_value:.2f} "
                f"(close {self.last_close:.2f}) | respected x{self.respect_count} | {self.status} | "
                f"BREAK = 5m close {sign} ~{self.break_level:.2f}")


def _fit(bars, pivots, kind: str) -> Trendline | None:
    """Best line through two same-kind pivots: maximize respected touches, penalize closes-through.

    WICK-ONLY INVARIANT (J's rule, T8 explicit guard): both anchors of a line are ALWAYS priced
    through the SAME `px` accessor (low-wick for support, high-wick for resistance) -- a line can
    never mix a wick anchor with a body/close anchor. `px` is chosen once per `kind` and reused for
    every candidate pair below, so this is structural, not incidental; the assert is a tripwire in
    case a future edit accidentally introduces a per-anchor accessor."""
    px = (lambda b: b["l"]) if kind == "support" else (lambda b: b["h"])
    best, best_score = None, -1e9
    for ai in range(len(pivots)):
        for bi in range(ai + 1, len(pivots)):
            i1, i2 = pivots[ai], pivots[bi]
            if i2 - i1 < MIN_SPAN:
                continue
            wick_field = "l" if kind == "support" else "h"
            p1, p2 = px(bars[i1]), px(bars[i2])
            assert p1 == bars[i1][wick_field] and p2 == bars[i2][wick_field], (
                f"wick-only anchor invariant violated -- both anchors of a {kind} line must be "
                f"the SAME wick field ('{wick_field}'), never a body/close or the opposite wick")
            if kind == "support" and p2 <= p1:      # support must ascend through higher-lows
                continue
            if kind == "resistance" and p2 >= p1:    # upper rail through lower-highs (or flat)
                continue
            slope = (p2 - p1) / (i2 - i1)
            respect = violations = 0
            for j in range(i1, len(bars)):
                lv = p1 + slope * (j - i1)
                extreme = px(bars[j])
                close = bars[j]["c"]
                if kind == "support":
                    if close < lv - TOL:
                        violations += 1
                    elif abs(extreme - lv) <= max(TOL, 0.0015 * lv):
                        respect += 1
                else:
                    if close > lv + TOL:
                        violations += 1
                    elif abs(extreme - lv) <= max(TOL, 0.0015 * lv):
                        respect += 1
            score = respect - 5 * violations + (i2 - i1) * 0.1
            if respect >= 1 and score > best_score:
                best_score, best = score, (i1, i2, p1, p2, slope, respect, violations)
    if not best:
        return None
    i1, i2, p1, p2, slope, respect, violations = best
    last = len(bars) - 1
    cur = p1 + slope * (last - i1)
    lc = bars[last]["c"]
    if kind == "support":
        status = "BROKEN" if lc < cur - TOL else ("TESTING" if bars[last]["l"] <= cur + TOL else "INTACT")
    else:
        status = "BROKEN" if lc > cur + TOL else ("TESTING" if bars[last]["h"] >= cur - TOL else "INTACT")
    proj_j = last + 6  # ~30 min forward on the line
    return Trendline(
        kind=kind, a_et=_et(bars[i1]["t"]), a_price=round(p1, 2),
        b_et=_et(bars[i2]["t"]), b_price=round(p2, 2), slope_per_bar=round(slope, 3),
        current_et=_et(bars[last]["t"]), current_value=round(cur, 2), last_close=round(lc, 2),
        break_level=round(cur, 2), respect_count=respect, violations=violations, status=status,
        a_unix=_unix(bars[i1]["t"]), b_unix=_unix(bars[i2]["t"]),
        proj_unix=_unix(bars[last]["t"]) + 6 * 300, proj_price=round(p1 + slope * (proj_j - i1), 2),
    )


def detect(bars: list[dict]) -> list[Trendline]:
    lows, highs = find_pivots(bars)
    out = []
    for kind, piv in (("support", lows), ("resistance", highs)):
        line = _fit(bars, piv, kind)
        if line:
            out.append(line)
    return out


def log_lines(lines: list[Trendline], date_et: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    with LOG.open("a", encoding="utf-8") as f:
        for ln in lines:
            f.write(json.dumps({"date_et": date_et, **asdict(ln)}) + "\n")


def write_live_state(lines: list[Trendline], date_et: str) -> None:
    """V4 (2026-07-08, T8 multi-day): the CURRENT trendlines as a SHADOW state file the engine /
    dashboard / self-check can read (overwritten each run, unlike the append-only LOG). SHADOW-
    only -- the engine does NOT trade off these yet (the trendline-as-veto / BOS-break-trigger
    entry-wire is A/B-gated NEEDS-REVIEW). Each line carries kind/current_value/break_level/
    status/respect so a consumer can see 'ascending support now 746.8, INTACT, respected x11;
    BREAK = 5m close below'. Schema is UNCHANGED from V3 (still shadow-only, same fields) --
    only the underlying lookback window grew from 1 day to N_DAYS."""
    import datetime as _dt
    payload = {
        "date_et": date_et,
        "generated_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "count": len(lines),
        "trendlines": [{"kind": ln.kind, "current_value": round(ln.current_value, 2),
                        "break_level": round(ln.break_level, 2), "status": ln.status,
                        "respect_count": ln.respect_count, "violations": ln.violations,
                        "slope_per_bar": round(ln.slope_per_bar, 3),
                        "last_close": round(ln.last_close, 2), "summary": ln.summary()}
                       for ln in lines],
        "note": ("SHADOW trendlines (V4, N_DAYS multi-day lookback). NOT fed to entries -- "
                 "entry-wire is A/B-gated NEEDS-REVIEW."),
    }
    LIVE_STATE.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main(n_days: int = N_DAYS) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    now = datetime.now(timezone.utc)
    day = et_today_str(now)  # ET calendar date (DST-aware), not a raw UTC-date string
    bars = fetch_spy_5m_lookback(n_days=n_days, now=now)
    if len(bars) < MIN_SPAN + 2:
        print(f"trendline_engine: only {len(bars)} RTH bars -- too early/no data")
        return 0
    lines = detect(bars)
    if not lines:
        print("trendline_engine: no respected trendline yet")
        return 0
    log_lines(lines, day)
    write_live_state(lines, day)   # V4: shadow state for the engine/dashboard/self-check
    print(f"trendline_engine {day} ({len(bars)} bars):")
    for ln in lines:
        print("  " + ln.summary())
        print(f"     draw_shape trend_line: A=({ln.a_unix},{ln.a_price}) "
              f"B=({ln.proj_unix},{ln.proj_price})  [color {'#26a69a' if ln.kind=='support' else '#ef5350'}]")
    print(f"  logged -> {LOG.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""trendline_engine.py -- autonomous swing-pivot trendline detection + respect/break tracking.

Built 2026-06-26 (J: "look how it's being respected... this needs reviewed and logged so you
draw your own trendlines. maybe a skill you can create to utilize"). The manual win: the
9:45->11:15 ascending support held 11 straight 5m bars before its first test.

WHAT IT DOES (pure stdlib + urllib; NO MCP/LLM/CDP -- the un-blockable data path):
  1. Pull today's RTH 5m SPY bars (direct Alpaca REST, same feed as the sight beacon).
  2. Find swing pivots (a low/high that is the extreme of a +/-k window).
  3. Fit the best ASCENDING-support (through higher-lows) and the best resistance/upper-rail
     (through swing-highs) trendline -- the pair of pivots that is most RESPECTED (touches that
     held) with the fewest closes-through.
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

import json
import sys
import urllib.request
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LOG = REPO / "analysis" / "trendlines" / "trendline-log.jsonl"
TOL = 0.10          # $ tolerance for a "touch" and for break confirmation
PIVOT_K = 1         # swing pivot = extreme of a +/-PIVOT_K window
MIN_SPAN = 3        # anchors must be >= this many bars apart (a real trend, not 2 adjacent bars)


# --------------------------------------------------------------------------- bars
def _creds() -> tuple[str, str]:
    env = json.loads((REPO / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["alpaca"]["env"]
    return env["ALPACA_API_KEY"], env["ALPACA_SECRET_KEY"]


def fetch_spy_5m(start_utc: str, end_utc: str) -> list[dict]:
    """SPY 5m RTH bars (sort=desc so the NEWEST bars are never truncated by `limit`; re-sorted asc)."""
    key, sec = _creds()
    url = (f"https://data.alpaca.markets/v2/stocks/SPY/bars?timeframe=5Min"
           f"&start={start_utc}&end={end_utc}&feed=iex&sort=desc&limit=200&adjustment=raw")
    req = urllib.request.Request(url, headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": sec})
    with urllib.request.urlopen(req, timeout=15) as r:
        bars = json.loads(r.read()).get("bars", [])
    bars.sort(key=lambda b: b["t"])  # back to chronological
    # RTH only (09:30-16:00 ET == 13:30-20:00 UTC)
    return [b for b in bars if "13:30:00" <= b["t"][11:19] <= "20:00:00"]


def _et(iso: str) -> str:
    h, m = int(iso[11:13]), int(iso[14:16])
    return f"{(h - 4) % 24:02d}:{m:02d}"


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
    """Best line through two same-kind pivots: maximize respected touches, penalize closes-through."""
    px = (lambda b: b["l"]) if kind == "support" else (lambda b: b["h"])
    best, best_score = None, -1e9
    for ai in range(len(pivots)):
        for bi in range(ai + 1, len(pivots)):
            i1, i2 = pivots[ai], pivots[bi]
            if i2 - i1 < MIN_SPAN:
                continue
            p1, p2 = px(bars[i1]), px(bars[i2])
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


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    now = datetime.now(timezone.utc)
    day = now.strftime("%Y-%m-%d")
    bars = fetch_spy_5m(f"{day}T13:30:00Z", now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    if len(bars) < MIN_SPAN + 2:
        print(f"trendline_engine: only {len(bars)} RTH bars -- too early/no data")
        return 0
    lines = detect(bars)
    if not lines:
        print("trendline_engine: no respected trendline yet")
        return 0
    log_lines(lines, day)
    print(f"trendline_engine {day} ({len(bars)} bars):")
    for ln in lines:
        print("  " + ln.summary())
        print(f"     draw_shape trend_line: A=({ln.a_unix},{ln.a_price}) "
              f"B=({ln.proj_unix},{ln.proj_price})  [color {'#26a69a' if ln.kind=='support' else '#ef5350'}]")
    print(f"  logged -> {LOG.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

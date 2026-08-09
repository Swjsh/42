#!/usr/bin/env python3
"""trendline_chart_draw.py -- bull+bear symmetric trendline CHART-DRAWING bridge.

Built 2026-08-09 (Task 2 of the bull-trendline-graduation + chart-drawing session).
This module owns the "what to draw" computation for both directions; the actual
draw_shape / draw_remove_one MCP calls happen in a live Claude+CDP session (they
cannot run from a headless scheduled task -- see ARCHITECTURE NOTE below, verified
against this repo's OWN prior finding, not re-derived).

WHY A NEW BRIDGE, GIVEN THE EXISTING trendline-draw SKILL ALREADY DRAWS LINES
-------------------------------------------------------------------------------
`.claude/skills/trendline-draw/SKILL.md` + `backtest/autoresearch/trendline_engine.py`
already detect+draw wick/body support+resistance lines (both directions -- the OLD
engine was never bear-only at the DISPLAY layer, only the LIVE TRIGGER in
`backtest/lib/filters.py` is bear-only, a DIFFERENT system). That flow stays exactly
as-is; it is proven (real respect counts up to x63 in production,
`automation/state/trendline-draw-state.json`) and this module does not replace it.

This bridge consumes the NEW `backtest/lib/trendline_detector.py` (built the same
session, sibling agent's lane, read-only import per the file-ownership boundary) for
three things the OLD autoresearch engine did not have:
  1. A STABLE, formal line-id scheme (`make_line_id` -> "TL-{symbol}-{timeframe}-
     {RES|SUP}-{W|B}-{first_anchor_unix}") for cross-referencing in labels/state/logs
     -- the OLD engine's `trendline-draw-state.json` bookkeeping only ever stored
     entity_id+kind+family, no stable identity independent of the TradingView-assigned
     entity_id.
  2. `just_retested` -- a first-class boolean (a touch landed on the CURRENT query bar
     and it isn't the line's own defining anchor) distinct from the 3-way
     intact/testing/broken status. This is the "retested-from-below" visual state the
     task brief asked for by name; the OLD engine's TESTING status is a proxy for the
     same idea but doesn't separate "currently sitting at the line" from "just bounced
     off it again".
  3. A `timeframe` parameter (default "5m", not hardcoded) -- the OLD engine always
     fetches its own SPY 5m bars via Alpaca REST; this module accepts ANY already-
     fetched bar series (TradingView `data_get_ohlcv`, Alpaca, or a backtest
     DataFrame), so the SAME code path draws lines fit on whatever timeframe the
     caller hands it -- see TASK 3's timeframe recommendation below.

KNOWN STATE OF `trendline_detector.py` AS OF THIS SESSION (disclosed, not hidden):
`backtest/tests/test_trendline_detector.py` was 22/25 GREEN the first time it was
checked this session (3 failures: test_wick_mode_uses_raw_wick_never_body,
test_min_span_bars_rejects_close_anchors, test_max_slope_pct_per_bar_caps_steep_lines
-- all candidate-generation edge cases, not public-API breakage); re-verified 25/25
GREEN later the same session after the owning (sibling, concurrent) session's own
fixes landed -- confirmed by re-running the suite fresh, not assumed. This bridge
still never edits that module (file-ownership boundary) and still calls it
defensively (try/except, fail-open per C7) regardless of its current pass rate, so a
future regression in an untested edge case cannot break chart drawing or -- more
importantly -- anything else, since this module has zero order/exit/decision side
effects (read bars in, drawing payloads out).

ARCHITECTURE NOTE -- why this cannot become a new always-on scheduled task
---------------------------------------------------------------------------
Verified first-hand this session (`mcp__tradingview__tv_health_check` fails until
TradingView Desktop + CDP is launched via `setup/launch_tv_debug.ps1`; `draw_shape`
et al. are MCP tools that only exist inside a live Claude+CDP session) and matches
the trendline-draw skill's own prior finding: "draw_shape only appears in
automation/prompts/*.md persona instructions, never in a standalone .py script." A
Windows Scheduled Task launching bare pythonw.exe has no Claude session and therefore
no MCP tools to call -- there is no code fix for this, it is the shape of the
integration. DRAWING is therefore always: (a) embedded in an LLM-driven persona fire
that already runs as a live session (Gamma_Premarket, 08:30 ET -- "fold into the
existing scheduled task" per the task brief means THIS one, not a new one), or
(b) on-demand, any time a live session invokes the trendline-draw skill. DETECTION
(this module's `compute_draw_payload`, no MCP calls) can run standalone/headless.

$0, pure Python (+ pandas for the DataFrame adapter). No MCP calls in this file --
draw_shape/draw_remove_one/draw_list happen in the calling session. Read-only import
of `backtest/lib/trendline_detector.py`. Fail-open (C7): any missing data or detector
error returns an empty payload with a `note`, never raises to the caller.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional, Sequence

REPO = Path(__file__).resolve().parents[2]
for _p in (str(REPO), str(REPO / "backtest"), str(REPO / "setup" / "scripts"),
           str(REPO / "backtest" / "autoresearch")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from crypto.lib.bar import Bar  # noqa: E402
from lib import trendline_detector as td  # noqa: E402

# ---------------------------------------------------------------------------
# Color table -- PORTED VERBATIM from the existing trendline-draw skill (J-approved,
# already shipped in production, do not re-derive). FAMILY is ALWAYS also in the
# label text -- color alone must never be the only tell (accessibility + the skill's
# own stated rule).
# ---------------------------------------------------------------------------
_COLOR_TABLE = {
    ("support", "wick"): "#26a69a",        # solid teal
    ("support", "body"): "#80cbc4",        # muted teal
    ("resistance", "wick"): "#ef5350",     # solid red
    ("resistance", "body"): "#ef9a9a",     # muted red
}

# DRAW CAP (J, 2026-07-15: "way too many trend lines on the screen"): at most 2 lines
# rendered -- the single best-respected line per SIDE (support + resistance), selected
# across BOTH anchor modes by touch_count. Preserved verbatim from the existing skill;
# this bridge does not reopen that decision.
MAX_LINES_PER_SIDE = 1

# Forward projection for the drawn ray's second point -- ~30 min on a 5m chart (6
# bars), matching trendline_engine.py's existing convention (proj_j = last + 6).
_PROJECTION_BARS_5M = 6


@dataclass(frozen=True)
class DrawLine:
    """One line, ready to hand to `mcp__tradingview__draw_shape` -- computed here,
    drawn by the caller (this module makes zero MCP calls)."""
    line_id: str
    kind: Literal["resistance", "support"]
    anchor_mode: Literal["wick", "body"]
    status: Literal["intact", "testing", "broken"]
    just_retested: bool
    touch_count: int
    violation_count: int
    point: dict          # {"time": unix, "price": float} -- first anchor
    point2: dict          # {"time": unix, "price": float} -- forward projection point
    color: str
    linewidth: int
    label: str

    def draw_shape_kwargs(self) -> dict:
        """Ready-to-splat kwargs for mcp__tradingview__draw_shape."""
        return dict(
            shape="trend_line",
            point=self.point,
            point2=self.point2,
            overrides=json.dumps({
                "linecolor": self.color,
                "linewidth": self.linewidth,
                "extendRight": True,
                "showLabel": True,
                "text": self.label,
            }),
        )


def bars_from_ohlcv_json(bars_json: Sequence[dict]) -> tuple[Bar, ...]:
    """Adapter for TradingView MCP's `data_get_ohlcv` shape: [{time, open, high, low,
    close, volume}, ...], unix seconds, oldest-first (verified against a live
    data_get_ohlcv call this session). Distinct from trendline_detector.
    bars_from_dataframe (that one expects a pandas DataFrame with a timestamp_et
    COLUMN, the backtest-engine shape -- this is the TradingView MCP JSON shape)."""
    import datetime as _dt
    out = []
    for b in bars_json:
        out.append(Bar(
            open_time=_dt.datetime.fromtimestamp(b["time"], tz=_dt.timezone.utc),
            open=float(b["open"]), high=float(b["high"]), low=float(b["low"]),
            close=float(b["close"]), volume=float(b.get("volume") or 0.0),
            granularity_seconds=300, source="tradingview_mcp",
        ))
    return tuple(out)


def _label(ln, family_tag: str) -> str:
    """ALWAYS states the anchor flavor (J's hard rule, re-taught twice: wick vs body
    must be stated whenever a line is described) plus kind/status/touches/id-suffix."""
    retest_tag = " RETESTED" if ln.just_retested else ""
    status_tag = ln.status.upper()
    # Suffix (not the full line_id) keeps the on-chart label readable; the full
    # line_id is always in the JSON payload / state-file record for lookup.
    id_suffix = ln.line_id.rsplit("-", 1)[-1]
    return (f"[{family_tag}] {ln.kind.upper()} | touch x{ln.touch_count} | "
            f"{status_tag}{retest_tag} | {id_suffix}")


def _to_draw_line(ln, *, now_unix: int, projection_bars: int, bar_seconds: int) -> DrawLine:
    color = _COLOR_TABLE[(ln.kind, ln.anchor_mode)]
    family_tag = ln.anchor_mode.upper()
    # Line width communicates state at a glance (family + status are ALSO always in
    # the text label -- width is a secondary, not sole, tell): a just-retested line
    # is the most actionable event (price came back and held again) so it gets the
    # thickest render; broken lines are de-emphasized (still visible -- a broken
    # line is useful context for "this rail failed here") but thinner than an
    # active one.
    if ln.status == "broken":
        linewidth = 1
    elif ln.just_retested:
        linewidth = 3
    else:
        linewidth = 2
    # `current_value` is the line already projected to query_bar_index (= now, the
    # last bar the caller passed in) -- point2 is `projection_bars` bars FURTHER
    # forward from `now_unix` (never from an anchor's own timestamp, which can be
    # days old and would place point2 in the past relative to "now").
    proj_unix = now_unix + projection_bars * bar_seconds
    proj_price = ln.current_value + ln.slope_per_bar * projection_bars
    return DrawLine(
        line_id=ln.line_id, kind=ln.kind, anchor_mode=ln.anchor_mode,
        status=ln.status, just_retested=ln.just_retested,
        touch_count=ln.touch_count, violation_count=ln.violation_count,
        point={"time": int(ln.anchors[0].bar_time_unix), "price": round(ln.anchors[0].price, 2)},
        point2={"time": int(proj_unix), "price": round(proj_price, 2)},
        color=color, linewidth=linewidth,
        label=_label(ln, family_tag),
    )


def compute_draw_payload(
    bars: Sequence[Bar],
    *,
    symbol: str = "SPY",
    timeframe: str = "5m",
    bar_seconds: int = 300,
    projection_bars: int = _PROJECTION_BARS_5M,
    **detect_kwargs,
) -> dict:
    """The full "what to draw" computation: detect wick+body x support+resistance
    (up to 4 candidates), apply the standing DRAW CAP (best 1 per side by touch_count,
    across anchor modes), and return ready-to-draw payloads plus full diagnostics.

    Fail-open (C7): a `trendline_detector` exception (e.g. one of the 3 known-failing
    edge cases) is caught and reported in `errors`, never raised -- chart drawing is
    display-only and must never be able to break anything else by erroring here.
    Returns `{"lines": [], ...}` (never omits the key) when nothing qualifies, so a
    caller can always safely iterate `payload["lines"]`.
    """
    if len(bars) < 10:
        return dict(lines=[], candidates=[], errors=[], note=f"only {len(bars)} bars -- too little data")

    candidates = []
    errors = []
    for mode in ("wick", "body"):
        try:
            found = td.detect_trendlines(
                bars, kinds=("resistance", "support"), anchor_mode=mode,
                symbol=symbol, timeframe=timeframe, **detect_kwargs,
            )
            candidates.extend(found)
        except Exception as exc:  # noqa: BLE001 -- fail-open, never break chart drawing
            errors.append(f"anchor_mode={mode}: {type(exc).__name__}: {exc}")

    chosen: list = []
    for kind in ("support", "resistance"):
        side_candidates = sorted(
            [c for c in candidates if c.kind == kind],
            key=lambda c: (c.touch_count, c.age_bars), reverse=True,
        )
        chosen.extend(side_candidates[:MAX_LINES_PER_SIDE])

    now_unix = int(bars[-1].open_time.timestamp())
    draw_lines = [_to_draw_line(ln, now_unix=now_unix, projection_bars=projection_bars,
                                 bar_seconds=bar_seconds)
                  for ln in chosen]

    return dict(
        symbol=symbol, timeframe=timeframe,
        n_bars=len(bars), n_candidates=len(candidates), n_chosen=len(draw_lines),
        lines=[dl.draw_shape_kwargs() | {
            "line_id": dl.line_id, "kind": dl.kind, "anchor_mode": dl.anchor_mode,
            "status": dl.status, "just_retested": dl.just_retested,
            "touch_count": dl.touch_count, "violation_count": dl.violation_count,
            "label": dl.label,
        } for dl in draw_lines],
        candidates_summary=[
            {"line_id": c.line_id, "kind": c.kind, "anchor_mode": c.anchor_mode,
             "touch_count": c.touch_count, "status": c.status}
            for c in candidates
        ],
        errors=errors,
        note=("DRAW CAP: at most 1 line per side (support+resistance), best by "
              "touch_count across wick+body -- preserves the existing skill's "
              "2026-07-15 anti-clutter rule. `errors` is non-fatal diagnostic "
              "output, not a failure signal -- an empty `lines` list with a "
              "populated `errors` list still means 'draw nothing', same as an "
              "empty list with no errors."),
    )


def _cli() -> int:
    """Standalone smoke-test entry point: fetch SPY 5m bars via the SAME Alpaca path
    trendline_engine.py already uses (so this module can also run headless for a
    detect-only dry run), print the payload as JSON. Never called by a scheduled
    task for DRAWING (see ARCHITECTURE NOTE) -- this CLI is for manual verification
    and for the detect-only/no-draw half of the pipeline."""
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--n-days", type=int, default=3)
    args = ap.parse_args()

    import trendline_engine as te  # noqa -- reuse the proven Alpaca fetch, not re-derived
    raw_bars = te.fetch_spy_5m_lookback(n_days=args.n_days)
    if len(raw_bars) < 10:
        print(json.dumps({"lines": [], "note": f"only {len(raw_bars)} bars fetched"}))
        return 0
    bars = tuple(
        Bar(
            open_time=__import__("datetime").datetime.fromisoformat(b["t"].replace("Z", "+00:00")),
            open=float(b["o"]), high=float(b["h"]), low=float(b["l"]), close=float(b["c"]),
            volume=float(b.get("v") or 0.0), granularity_seconds=300, source="alpaca",
        )
        for b in raw_bars
    )
    payload = compute_draw_payload(bars, symbol="SPY", timeframe="5m")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())

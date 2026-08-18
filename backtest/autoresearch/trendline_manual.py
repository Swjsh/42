"""trendline_manual.py -- intraday refresh of J's hand-drawn ("manual") TradingView trendlines.

WHY THIS EXISTS (2026-08-18, J verbatim: "the engine reads his hand-drawn TradingView
trendlines ONLY at premarket, so anything he draws during the session is never seen... I
wanna do this on a higher time frame, though, so we don't have a bunch of small individual
trend lines"):

  automation/scripts/compute_trendlines.py already reads J's manual chart drawings (from
  automation/state/chart_drawings.json) and age/distance-filters them into trendlines.json --
  but two things kept that pipeline premarket-only in practice, confirmed live 2026-08-18:

    1. chart_drawings.json ITSELF was only ever refreshed by a step in
       automation/prompts/premarket.md (an LLM instruction using the TradingView MCP's
       ui_evaluate tool) -- found stale at 2026-06-18 in the real state dir, i.e. not
       reliably refreshed even once daily (C7: an LLM step that silently skips still
       reports success). Every one of J's real chart-drawn trendlines in trendlines.json
       today (7 of them) was 62-102 days old and correctly age-dropped -- the age filter
       works; it just never saw anything fresher than a June snapshot.
    2. compute_trendlines.py's compute() was invoked from that SAME once-daily premarket
       step, on no scheduled task at all (see that module's own docstring).

  This module closes BOTH gaps by piggybacking on Gamma_Trendlines, the scheduled task that
  ALREADY runs backtest/autoresearch/trendline_engine.py every 5 minutes during RTH (see
  setup/install-trendlines.ps1). trendline_engine.main() calls refresh() here as one more
  best-effort step, exactly the same fail-open pattern it already uses for trendline_watch.py
  (WS8, 2026-08-01) -- see the bottom of trendline_engine.main(). NO NEW SCHEDULED TASK.

REUSE, NOT REINVENTION (L251: two implementations of the same read silently disagree):
  - The actual TradingView-chart read uses setup/scripts/tv_cdp.py, the EXISTING headless CDP
    client (built 2026-08-06) specifically so a pythonw scheduled task can drive/read the
    chart with no MCP and no LLM. This module does not open a second CDP connection type -- it
    calls the SAME Runtime.evaluate mechanism tv_cdp.py already wraps.
  - The JS payload evaluated is automation/scripts/read_chart_drawings.js, VERBATIM -- the
    exact file the MCP ui_evaluate premarket path already uses (same shape in, same shape out:
    {success, count, drawings:[{id, title, point_count, points:[{time, price}]}]}). One JS
    reader, two transports (MCP for a live session, tv_cdp for headless).
  - The age/distance staleness filter, the manual-line parsing, and the NEW higher-timeframe
    significance filter all live in automation/scripts/compute_trendlines.py (`compute()` /
    `_load_manual_drawings` / `score_manual_significance`) -- this module imports and calls
    that file directly rather than re-deriving any filtering logic. Both the once-daily
    premarket CLI path and this 5-min intraday path share the exact same thresholds.

SHADOW / LOGGED-ONLY. This module only refreshes VISIBILITY -- what J drew, whether it is
still age/distance/significance-valid, and how price is behaving around it (respect_count_
recent). NOTHING here is consumed by entry decisions; automation/state/trendlines.json already
carries its own `doctrine_note` saying so, and this module adds no new consumer and wires into
none. Same posture as trendlines-live.json's standing note: "NOT fed to entries -- entry-wire
is A/B-gated NEEDS-REVIEW."

FAIL-OPEN EVERYWHERE (C7 doctrine + this task's explicit requirement): `refresh()` NEVER
raises. If TradingView/CDP is unreachable, the chart isn't ready, the JS payload reports
failure, or compute_trendlines.compute() itself fails for any reason, this cycle's refresh is
skipped ENTIRELY -- automation/state/chart_drawings.json AND automation/state/trendlines.json
are BOTH left exactly as they were (no partial writes, no half-updated state). The next 5-min
tick tries again. trendline_engine.main() additionally wraps this call in its OWN try/except
(belt-and-suspenders, identical to the trendline_watch hook already there), so a bug in this
module can never block the primary auto-detection production fire either -- and this module's
own call is placed AFTER that fire's own writes in trendline_engine.main(), so even a total
failure here has zero blast radius on trendlines-live.json / trendline-watch.json / the
append-only trendline-log.jsonl.

Run standalone: python backtest/autoresearch/trendline_manual.py
Production: called by trendline_engine.main() after write_live_state/trendline_watch each fire.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Callable, Optional

REPO = Path(__file__).resolve().parents[2]

SETUP_SCRIPTS = REPO / "setup" / "scripts"
if str(SETUP_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SETUP_SCRIPTS))
import tv_cdp  # noqa: E402 -- the existing headless CDP client, reused verbatim (not re-derived)
from et_clock import et_now  # noqa: E402 -- the ONE DST-aware ET source on this rig

AUTOMATION_SCRIPTS = REPO / "automation" / "scripts"
if str(AUTOMATION_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(AUTOMATION_SCRIPTS))
import compute_trendlines  # noqa: E402 -- the existing manual-line reader + filters, reused

READ_DRAWINGS_JS = REPO / "automation" / "scripts" / "read_chart_drawings.js"


def refresh_chart_drawings(
    chart_factory: Optional[Callable[[], Any]] = None,
    out_path: Optional[Path] = None,
) -> dict:
    """Pull J's LIVE chart drawings via CDP and overwrite automation/state/chart_drawings.json.

    Raises (TvCdpError, RuntimeError, or whatever the JS payload raises through tv_cdp) on ANY
    failure -- reachability, chart-not-ready, or a JS-side {success: false}. This function does
    NOT swallow anything itself; `refresh()` below is the fail-open layer that catches this and
    treats any exception as "skip this cycle", never a crash.

    `chart_factory` (default tv_cdp.TvChart) exists purely so tests can inject a fake CDP
    session without a live TradingView Desktop running -- production always uses the real
    client. `out_path` similarly defaults to the real state path but is overridable for tests.
    """
    out_path = out_path or (compute_trendlines.STATE_DIR / "chart_drawings.json")
    factory = chart_factory or tv_cdp.TvChart
    js = READ_DRAWINGS_JS.read_text(encoding="utf-8")

    with factory() as chart:
        chart.require_chart_api()
        result = chart.evaluate(js)

    if not isinstance(result, dict) or not result.get("success"):
        err = result.get("error", "unknown") if isinstance(result, dict) else f"non-dict result: {result!r}"
        raise RuntimeError(f"read_chart_drawings.js reported failure: {err}")

    payload = {
        "schema_version": 2,
        "purpose": "Snapshot of all line-tool drawings on the SPY chart. Read by trendline detection pipeline.",
        "as_of": et_now().isoformat(),
        "source": ("tv_cdp direct (intraday refresh via trendline_manual.refresh_chart_drawings, "
                   "piggybacked on Gamma_Trendlines' 5-min RTH cadence -- see this module's docstring)"),
        "count": result.get("count", len(result.get("drawings", []))),
        "drawings": result.get("drawings", []),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def refresh(
    spot: Optional[float] = None,
    lookback_sessions: int = 2,
    chart_factory: Optional[Callable[[], Any]] = None,
) -> Optional[dict]:
    """The one production entry point: best-effort intraday refresh of trendlines.json.

    NEVER raises (see module docstring FAIL-OPEN section). Returns the freshly written payload
    on success, or None if the refresh could not complete this cycle -- in which case BOTH
    chart_drawings.json and trendlines.json are left exactly as they were.

    `spot` should be the caller's freshest known SPY price (trendline_engine.main() passes its
    own just-fetched Alpaca bar close) so the distance-staleness filter in compute_trendlines
    judges against real-time price, not compute_trendlines' own CSV's last row (which may be a
    prior session on a day the CSV hasn't rolled yet).
    """
    try:
        refresh_chart_drawings(chart_factory=chart_factory)
    except Exception as exc:  # noqa: BLE001 -- deliberate fail-open, see module docstring
        print(f"trendline_manual: CDP read failed, refresh skipped this cycle ({exc})")
        return None

    try:
        payload = compute_trendlines.compute(spot=spot, lookback_sessions=lookback_sessions)
    except Exception as exc:  # noqa: BLE001 -- deliberate fail-open, see module docstring
        print(f"trendline_manual: compute_trendlines failed, trendlines.json left untouched ({exc})")
        return None

    out_path = compute_trendlines.STATE_DIR / "trendlines.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(f"trendline_manual: refreshed trendlines.json -- "
          f"{payload.get('manual_significant_count', 0)} significant manual "
          f"(of {payload.get('manual_count', 0)} age/distance-valid, "
          f"{len(payload.get('manual_dropped', []))} dropped) + "
          f"{payload.get('auto_count', 0)} auto")
    return payload


if __name__ == "__main__":
    _result = refresh()
    raise SystemExit(0 if _result is not None else 1)

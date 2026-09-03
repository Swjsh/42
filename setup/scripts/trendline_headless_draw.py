"""trendline_headless_draw.py -- headless, $0 chart-drawing runner for the NEW
(2026-08-09) `trendline_chart_draw.py` / `trendline_detector.py` pair.

WHY THIS EXISTS (TRENDLINE-DRAW-HEADLESS, 2026-09-03, automation/overnight/queue.md):
    Premarket Step 5c (an LLM-driven step) is supposed to draw the live engine's
    trendlines once daily. It is context-budget-discretionary and had skipped with
    reason='budget conservation' -- a REAL gap, not a false alarm: an LLM chose not to
    run a $0 deterministic job. `trendline_chart_draw.py`'s own header justified being
    LLM-only by citing a "cannot run from a headless scheduled task" constraint that
    `Gamma_ChartAutoDraw` (2026-08-06, `draw_key_levels.py` + `tv_cdp.py`) had ALREADY
    disproved three days earlier the constraint was written down. That module's header
    has been corrected (2026-09-03) to point at this file instead of repeating the
    disproved claim.

    This script is the same shape as `draw_key_levels.py`: compute what to draw
    (`trendline_chart_draw.compute_draw_payload`, imported not copied), draw it via
    `tv_cdp.TvChart` (the same CDP path the TradingView MCP itself uses --
    `removeEntity` for cleanup, `createMultipointShape` for `trend_line` specifically,
    verified LIVE 2026-09-03: create -> text readback -> remove, then a full real run
    against BATS:SPY that drew 2 lines, left the chart's other 22 pre-existing
    trend_line shapes untouched, and was idempotent on a second run -- see
    `TvChart.create_trend_line`'s own docstring for why `createShape` was NOT the right
    call here), remove ONLY its own prior trendline drawings first (never `draw_clear`,
    never a key-level `horizontal_line` -- those are `draw_key_levels.py`'s exclusive
    territory and this script never touches a `horizontal_line`-named shape), and fail
    open with a distinct `SKIPPED_TV_DOWN` stamp on any CDP outage so a normal
    off-hours run never looks like a crash.

STATE: writes `automation/state/trendline-headless-draw.json` -- a NEW stamp, separate
from the OLD LLM-path stamp `automation/state/trendline-draw-state.json` (owned by
`trendline_draw_state.py` / the `trendline-draw` skill's Step 6, meaning "the LLM skill
ran today"). Overwriting that file's meaning would make a future session think the
manual skill fired when it didn't; this script never touches it.

SAFETY (mirrors draw_key_levels.py):
    * Only ever creates/removes `trend_line`-named shapes; a `horizontal_line` (J's
      manual lines OR draw_key_levels.py's key-level lines) is structurally out of
      reach -- `_own_trend_lines()` filters `list_shapes()` to `name == "trend_line"`
      before anything else runs.
    * Every line this script draws is TAG-prefixed ("[GTL] ") in its on-chart text, so
      an orphan (state lost, e.g. a corrupt/deleted stamp file) can still be recognised
      and swept on the next run, same recovery path draw_key_levels.py uses.
    * `draw_clear`/`removeAllShapes()` is never called.

FAIL-OPEN (C7): TradingView/CDP unreachable is the normal off-hours state -> stamp
`status=SKIPPED_TV_DOWN`, exit 0, never raise into the scheduler. An unexpected error
also never raises uncaught -- it is caught, stamped `status=ERROR`, and returns 1 (a
loud but controlled failure, not a bare traceback into Task Scheduler).

Usage:
    python setup/scripts/trendline_headless_draw.py               # compute + draw
    python setup/scripts/trendline_headless_draw.py --dry-run      # compute + log only
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (str(REPO), str(REPO / "backtest"), str(SCRIPTS_DIR), str(REPO / "backtest" / "autoresearch")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytz  # noqa: E402

import trendline_chart_draw as tcd  # noqa: E402 -- computes what to draw, not copied
from tv_cdp import TvChart, TvCdpError  # noqa: E402
from et_clock import et_now  # noqa: E402

STATE_DIR = REPO / "automation" / "state"
STATE_FILE = STATE_DIR / "trendline-headless-draw.json"
STATUS_MD = REPO / "automation" / "overnight" / "STATUS.md"
ET = pytz.timezone("America/New_York")

# Marker that makes a drawing recognisably ours -- distinct from draw_key_levels.py's
# "[G] " (which tags horizontal_line key-level shapes, a different producer/surface).
TAG = "[GTL] "

DEFAULT_N_DAYS = 3


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"schema_version": 1, "drawn": []}
    try:
        raw = json.loads(STATE_FILE.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        # A corrupt stamp must not strand our drawings; TAG-orphan recovery covers it.
        return {"schema_version": 1, "drawn": []}
    if not isinstance(raw, dict) or not isinstance(raw.get("drawn"), list):
        return {"schema_version": 1, "drawn": []}
    return raw


def write_state(out: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    tmp.replace(STATE_FILE)


def flag_status_md(message: str) -> None:
    try:
        STATUS_MD.parent.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
        with open(STATUS_MD, "a", encoding="utf-8") as fh:
            fh.write(f"\n### BROKEN: trendline-headless-draw {stamp}\n- {message}\n")
    except OSError:
        pass


def fetch_bars(n_days: int = DEFAULT_N_DAYS):
    """SPY 5m bars via the SAME Alpaca REST path trendline_chart_draw.py's own CLI
    already uses (`trendline_engine.fetch_spy_5m_lookback`) -- reused, not re-derived.
    """
    import trendline_engine as te  # noqa: E402 -- backtest/autoresearch, on sys.path above
    from crypto.lib.bar import Bar

    raw_bars = te.fetch_spy_5m_lookback(n_days=n_days)
    return tuple(
        Bar(
            open_time=dt.datetime.fromisoformat(b["t"].replace("Z", "+00:00")),
            open=float(b["o"]), high=float(b["h"]), low=float(b["l"]), close=float(b["c"]),
            volume=float(b.get("v") or 0.0), granularity_seconds=300, source="alpaca",
        )
        for b in raw_bars
    )


def _own_trend_lines(chart: TvChart) -> list[dict]:
    return [s for s in chart.list_shapes() if s.get("name") == "trend_line"]


def remove_own_lines(chart: TvChart, state: dict, dry_run: bool) -> list[dict]:
    """Remove every trend_line provably ours: recorded entity_id, or TAG-prefixed text
    (orphan recovery). NEVER touches a horizontal_line -- key levels and J's manual
    trend lines (untagged) are structurally out of reach of this function."""
    recorded = {d.get("entity_id") for d in state.get("drawn") or [] if d.get("entity_id")}
    on_chart = _own_trend_lines(chart)
    on_chart_ids = {s["id"] for s in on_chart}

    targets: list[dict] = []
    for sid in recorded & on_chart_ids:
        targets.append({"entity_id": sid, "why": "recorded_in_state"})

    already = {t["entity_id"] for t in targets}
    for shape in on_chart:
        if shape["id"] in already:
            continue
        text = chart.shape_text(shape["id"]) or ""
        if text.startswith(TAG):
            targets.append({"entity_id": shape["id"], "why": "tagged_orphan", "text": text})

    if dry_run:
        return targets

    removed = []
    for t in targets:
        try:
            if chart.remove_entity(t["entity_id"]):
                removed.append(t)
        except TvCdpError:
            continue
    return removed


def draw_lines(chart: TvChart, lines: list[dict], dry_run: bool) -> list[dict]:
    drawn: list[dict] = []
    for ln in lines:
        text = f"{TAG}{ln['label']}"
        if dry_run:
            drawn.append({"entity_id": None, "line_id": ln["line_id"], "kind": ln["kind"],
                          "anchor_mode": ln["anchor_mode"], "text": text})
            continue
        overrides = json.loads(ln["overrides"]) if isinstance(ln.get("overrides"), str) else (ln.get("overrides") or {})
        overrides = dict(overrides)
        overrides["text"] = text  # re-tag: compute_draw_payload's label doesn't carry TAG
        eid = chart.create_trend_line(ln["point"], ln["point2"], text, overrides)
        drawn.append({"entity_id": eid, "line_id": ln["line_id"], "kind": ln["kind"],
                      "anchor_mode": ln["anchor_mode"], "status": ln["status"],
                      "touch_count": ln["touch_count"], "text": text})
    return drawn


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", help="compute + log the plan; touch nothing")
    ap.add_argument("--n-days", type=int, default=DEFAULT_N_DAYS)
    args = ap.parse_args(argv)

    now = et_now()
    state = load_state()
    out: dict = {
        "schema_version": 1,
        "as_of": now.isoformat(),
        "tag": TAG,
        "dry_run": bool(args.dry_run),
        "symbol": "SPY",
        "timeframe": "5m",
    }

    try:
        bars = fetch_bars(n_days=args.n_days)
    except Exception as exc:  # noqa: BLE001 -- fetch failure is a real error, never silent
        msg = f"bar fetch failed: {type(exc).__name__}: {exc}"
        print(f"ERROR {msg}")
        out.update(status="ERROR", reason=msg, n_drawn=0, drawn=state.get("drawn", []))
        write_state(out)
        flag_status_md(f"trendline_headless_draw failed -- {msg}")
        return 1

    if len(bars) < 10:
        msg = f"only {len(bars)} bars fetched -- too little data"
        print(f"SKIP {msg}")
        out.update(status="SKIPPED_NO_DATA", reason=msg, n_drawn=0, drawn=state.get("drawn", []))
        write_state(out)
        return 0

    payload = tcd.compute_draw_payload(bars, symbol="SPY", timeframe="5m")
    out["n_candidates"] = payload.get("n_candidates", 0)
    out["errors"] = payload.get("errors") or []

    if args.dry_run:
        out.update(status="DRY_RUN", n_drawn=len(payload.get("lines") or []),
                   drawn=[{"line_id": ln["line_id"], "kind": ln["kind"],
                           "anchor_mode": ln["anchor_mode"], "label": ln["label"]}
                          for ln in payload.get("lines") or []])
        print(json.dumps(out, indent=2))
        return 0

    try:
        with TvChart() as chart:
            chart.require_chart_api()
            out["chart_symbol"] = chart.symbol()

            removed = remove_own_lines(chart, state, dry_run=False)
            out["removed"] = removed

            drawn = draw_lines(chart, payload.get("lines") or [], dry_run=False)
            out["drawn"] = drawn
            out["n_drawn"] = len(drawn)
            out["status"] = "OK"

    except TvCdpError as exc:
        # TradingView down is the normal off-hours state -> soft skip, exit 0.
        msg = str(exc)
        print(f"SKIP (TradingView/CDP unavailable): {msg}")
        out.update(status="SKIPPED_TV_DOWN", reason=msg, n_drawn=0, drawn=state.get("drawn", []))
        write_state(out)
        return 0
    except Exception as exc:  # noqa: BLE001 -- unexpected: loud, never silent, never raised
        msg = f"{type(exc).__name__}: {exc}"
        print(f"ERROR {msg}")
        out.update(status="ERROR", reason=msg, n_drawn=0, drawn=state.get("drawn", []))
        write_state(out)
        flag_status_md(f"trendline_headless_draw failed -- {msg}")
        return 1

    write_state(out)
    print(f"{out['status']} symbol={out.get('chart_symbol')} removed={len(out.get('removed') or [])} "
          f"drawn={out['n_drawn']}")
    for d in out.get("drawn") or []:
        print(f"   {d.get('kind'):>10}/{d.get('anchor_mode'):<4}  {d.get('text')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

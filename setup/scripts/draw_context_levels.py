"""Draw automation/state/context-levels.json onto the live TradingView chart -- headless,
$0 (WS-E, work order #9.5 row E, markdown/0dte/KEY-LEVELS-CHART-READING-HANDOFF.md).

SCOPE: this is a DRAWING-ONLY consumer of context-levels.json. It never reads or writes
key-levels.json and never touches heartbeat_core/filters.py -- the gate is unaffected by
construction (see context_levels.py's module docstring and #9.13 A). This file is the
ONLY reader of context-levels.json in the repo.

TAG: draws with the SAME `[G] ` level-context tag draw_key_levels.py uses, per the
ratified tag taxonomy (#9.10: `[G] ` = level context). Imported from engine_shape_tags
(the ONE shared tuple), never re-typed -- L251 is exactly the failure mode of a second,
independently-spelled copy of a tag constant.

Drawn as horizontal RAYS at each level's `price` (point levels: VWAP bands, gamma
walls, prior-day VWAP) or as a HIGH/LOW PAIR of lines (initial balance, opening range),
each carrying its own weight (by family) in the line's width/opacity. Never draws a
rectangle/zone primitive -- draw_key_levels.py's own zone-merge scaffold is still
un-ratified (ZONE_MERGE_ENABLED stays False there); this file does not invent one either.

Keeps its OWN chart-autodraw state file (context-chart-autodraw.json) -- entirely
separate bookkeeping from draw_key_levels.py's chart-autodraw.json, so nothing here can
misclassify or remove a key-level line (or vice versa).

FAIL-OPEN: TradingView not running is a soft SKIP, exit 0 (same convention as
draw_key_levels.py). Only an unexpected error exits non-zero and is flagged to STATUS.md.

Usage:
    python setup/scripts/draw_context_levels.py                # draw/refresh
    python setup/scripts/draw_context_levels.py --dry-run       # show the plan, touch nothing
    python setup/scripts/draw_context_levels.py --clear-only    # remove our lines, draw none
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import pytz

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tv_cdp import TvChart, TvCdpError  # noqa: E402
from engine_shape_tags import LEVELS_TAG as TAG  # noqa: E402 -- "[G] ", imported not copied

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = REPO_ROOT / "automation" / "state"
CONTEXT_LEVELS = STATE_DIR / "context-levels.json"
STATE_FILE = STATE_DIR / "context-chart-autodraw.json"
STATUS_MD = REPO_ROOT / "automation" / "overnight" / "STATUS.md"

ET = pytz.timezone("America/New_York")

# Weight by family -- a coarse visual priority, not a score used anywhere else.
FAMILY_WEIGHT = {
    "initial_balance": 3,
    "opening_range": 2,
    "vwap": 3,
    "prior_day_vwap": 2,
    "gamma_wall": 2,
}

COLOR_SUPPORT = "#26a69a"
COLOR_RESISTANCE = "#ef5350"
COLOR_NEUTRAL = "#787b86"
COLOR_PIVOT = "#a855f7"


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"schema_version": 1, "drawn": []}
    try:
        return load_json(STATE_FILE)
    except (json.JSONDecodeError, OSError):
        return {"schema_version": 1, "drawn": []}


def write_state(state: dict) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    tmp.replace(STATE_FILE)


def flag_status_md(message: str) -> None:
    try:
        STATUS_MD.parent.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(ET).strftime("%Y-%m-%d %H:%M ET")
        with open(STATUS_MD, "a", encoding="utf-8") as fh:
            fh.write(f"\n### BROKEN: context-chart-autodraw {stamp}\n- {message}\n")
    except OSError:
        pass


def _color_for(role: str | None) -> str:
    if role == "support":
        return COLOR_SUPPORT
    if role == "resistance":
        return COLOR_RESISTANCE
    if role == "pivot":
        return COLOR_PIVOT
    return COLOR_NEUTRAL


def _weight_for(level: dict) -> int:
    return FAMILY_WEIGHT.get(level.get("family"), 1)


def level_lines(level: dict) -> list[tuple[float, str]]:
    """One context-level record -> [(price, on-chart text), ...]. A point level (has
    `price`) draws one line; a range level (has `high`/`low`) draws two, each labeled
    with its own edge."""
    label = level.get("label") or level.get("type") or "CONTEXT"
    out: list[tuple[float, str]] = []
    if level.get("price") is not None:
        out.append((float(level["price"]), f"{TAG}{label} {float(level['price']):.2f}"))
        return out
    if level.get("high") is not None:
        out.append((float(level["high"]), f"{TAG}{label} HIGH {float(level['high']):.2f}"))
    if level.get("low") is not None:
        out.append((float(level["low"]), f"{TAG}{label} LOW {float(level['low']):.2f}"))
    return out


def overrides_for(level: dict) -> dict:
    color = _color_for(level.get("role"))
    weight = _weight_for(level)
    return {
        "linecolor": color,
        "linewidth": max(1, min(3, weight)),
        "linestyle": 2,  # dashed -- context, never mistaken for J's solid hand-drawn work
        "showLabel": True,
        "textcolor": color,
        "fontsize": 10,
        "horzLabelsAlign": "right",
        "vertLabelsAlign": "bottom",
        "showPrice": False,
    }


def _horizontal_lines(chart: TvChart) -> list[dict]:
    return [s for s in chart.list_shapes() if s.get("name") == "horizontal_line"]


def remove_own_lines(chart: TvChart, state: dict, dry_run: bool) -> list[dict]:
    """Remove only lines provably ours: recorded id, or TAG-prefixed text (orphans).
    Identical safety shape to draw_key_levels.remove_own_lines -- see that file's header
    for the full rationale (never touches anything untagged / not our own id)."""
    recorded = {d.get("entity_id") for d in state.get("drawn") or [] if d.get("entity_id")}
    on_chart = _horizontal_lines(chart)
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


def draw_levels(chart: TvChart, levels: list[dict], dry_run: bool) -> list[dict]:
    drawn: list[dict] = []
    for lv in levels:
        overrides = overrides_for(lv)
        for price, text in level_lines(lv):
            if dry_run:
                drawn.append({"entity_id": None, "price": price, "text": text})
                continue
            eid = chart.create_horizontal_line(price, text, overrides)
            drawn.append({"entity_id": eid, "price": price, "text": text,
                          "family": lv.get("family"), "role": lv.get("role")})
    return drawn


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Draw context-levels.json on the TradingView chart")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; touch nothing")
    ap.add_argument("--clear-only", action="store_true", help="remove our lines, draw nothing")
    args = ap.parse_args(argv)

    now = dt.datetime.now(ET)
    state = load_state()
    out: dict = {
        "schema_version": 1,
        "as_of": now.isoformat(),
        "tag": TAG,
        "dry_run": bool(args.dry_run),
    }

    try:
        context = load_json(CONTEXT_LEVELS)
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"context-levels.json unreadable: {exc}"
        print(f"SKIP {msg}")
        out.update(status="SKIPPED_NO_FILE", message=msg, drawn=state.get("drawn", []))
        write_state(out)
        return 0  # fail-open: no context file yet is a normal cold-start state, not an error

    try:
        with TvChart() as chart:
            chart.require_chart_api()
            out["symbol"] = chart.symbol()
            out["shapes_before"] = len(chart.list_shapes())

            removed = remove_own_lines(chart, state, args.dry_run)
            out["removed"] = removed

            levels = context.get("levels") or []
            out["session_date"] = context.get("session_date")
            drawn = [] if args.clear_only else draw_levels(chart, levels, args.dry_run)
            out["drawn"] = drawn
            out["shapes_after"] = len(chart.list_shapes())
            out["status"] = "DRY_RUN" if args.dry_run else "OK"

    except TvCdpError as exc:
        msg = str(exc)
        print(f"SKIP (TradingView/CDP unavailable): {msg}")
        out.update(status="SKIPPED_TV_DOWN", message=msg, drawn=state.get("drawn", []))
        write_state(out)
        return 0
    except Exception as exc:  # noqa: BLE001 - unexpected: must be loud, never silent
        msg = f"{type(exc).__name__}: {exc}"
        print(f"ERROR {msg}")
        out.update(status="ERROR", message=msg, drawn=state.get("drawn", []))
        write_state(out)
        flag_status_md(f"draw_context_levels failed -- {msg}")
        return 1

    if not args.dry_run:
        write_state(out)

    print(
        f"{out['status']} removed={len(out.get('removed') or [])} "
        f"drawn={len(out.get('drawn') or [])} shapes {out.get('shapes_before')} -> {out.get('shapes_after')}"
    )
    for d in out.get("drawn") or []:
        print(f"   {d['price']:>8.2f}  {d['text']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

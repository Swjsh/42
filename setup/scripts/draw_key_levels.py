"""Draw automation/state/key-levels.json onto the live TradingView chart -- headless, $0.

WHY THIS EXISTS (J asked twice; OP-33(e) "a repeated question is a missing instrument"):
    On 2026-08-06 J looked at his chart and saw levels from JUNE -- a "PMH 732.62" line
    with SPY at 770. Two separate defects produced that:

      1. key-levels.json correctly moved 732.62 / 728.50 into `deprecated_levels`, but
         nothing ever removed the DRAWINGS. Every Claude session that drew levels added
         to the chart; no session ever subtracted. 27 horizontal lines had accumulated.
      2. Two June entries (PRIOR_CLOSE_2026-06-26 @ 731.22, PML_2026-06-29 @ 734.52) were
         still in the ACTIVE `levels` array with draw_needed=true, ~$35 below spot.

    This producer closes both: it draws only near-spot, non-deprecated levels, and it
    removes its OWN prior drawings first so the set is replaced, never appended.

SAFETY -- how it avoids ever deleting J's hand-drawn work:
    * It only ever touches shapes of type `horizontal_line`. J's trendlines/rays/
      rectangles are a different shape type and are structurally out of reach.
    * Every line it draws is tagged: the text starts with TAG ("[G] ").
    * It removes a line only when that line is provably its own, by one of:
        (a) the entity_id is recorded in its own state file, or
        (b) the line's text starts with TAG (orphan recovery if state is lost).
    * `--sweep-legacy` is the ONE exception, for cleaning up pre-tag Gamma litter. It
      removes an untagged horizontal_line ONLY when the line's price exactly matches a
      price in key-levels.json `deprecated_levels`. That is a staleness proof taken from
      our own state file, not a guess about authorship. It is dry-run unless --apply,
      and every removal is recorded in the state file so it is auditable and redrawable.
    * removeAllShapes()/draw_clear is never called -- it takes no scope argument and
      would wipe the chart.

FAIL-OPEN: TradingView not running (the normal off-hours case) is a soft SKIP with
exit 0. Only an unexpected error exits non-zero, and it also appends to STATUS.md so
the failure is never silent (C7).

Usage:
    python setup/scripts/draw_key_levels.py                 # draw/refresh today's set
    python setup/scripts/draw_key_levels.py --dry-run       # show the plan, touch nothing
    python setup/scripts/draw_key_levels.py --clear-only    # remove our lines, draw none
    python setup/scripts/draw_key_levels.py --sweep-legacy  # dry-run legacy report
    python setup/scripts/draw_key_levels.py --sweep-legacy --apply
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

REPO_ROOT = Path(__file__).resolve().parents[2]
STATE_DIR = REPO_ROOT / "automation" / "state"
KEY_LEVELS = STATE_DIR / "key-levels.json"
STATE_FILE = STATE_DIR / "chart-autodraw.json"
STATUS_MD = REPO_ROOT / "automation" / "overnight" / "STATUS.md"

ET = pytz.timezone("America/New_York")

# Marker that makes a drawing recognisably ours. Changing this orphans every line
# drawn under the old marker, so it is pinned by test_draw_key_levels.py.
TAG = "[G] "

DEFAULT_BAND_DOLLARS = 15.0
DEFAULT_MAX_LEVELS = 14

COLOR_SUPPORT = "#26a69a"
COLOR_RESISTANCE = "#ef5350"
COLOR_NEUTRAL = "#787b86"


# --------------------------------------------------------------------------
# pure helpers (unit-testable with no chart, no CDP)
# --------------------------------------------------------------------------

def humanize_label(raw: str) -> str:
    """'PRIOR_DAY_CLOSE_2026-08-06' -> 'PRIOR DAY CLOSE'.

    Strips a trailing ISO date (it is redundant on a chart that shows the date axis)
    and turns underscores into spaces so the on-chart text is readable.
    """
    if not raw:
        return "LEVEL"
    parts = raw.split("_")
    while parts and _looks_like_iso_date(parts[-1]):
        parts.pop()
    return " ".join(p for p in parts if p) or "LEVEL"


def _looks_like_iso_date(tok: str) -> bool:
    if len(tok) != 10 or tok[4] != "-" or tok[7] != "-":
        return False
    try:
        dt.date.fromisoformat(tok)
    except ValueError:
        return False
    return True


def deprecated_prices(key_levels: dict) -> set[float]:
    """Prices key-levels.json has explicitly retired. Used for the legacy sweep."""
    out: set[float] = set()
    for d in key_levels.get("deprecated_levels") or []:
        price = d.get("price") if isinstance(d, dict) else None
        if price is None:
            continue
        try:
            out.add(round(float(price), 2))
        except (TypeError, ValueError):
            continue
    return out


def select_levels(
    key_levels: dict,
    spot: float,
    band: float = DEFAULT_BAND_DOLLARS,
    max_levels: int = DEFAULT_MAX_LEVELS,
) -> list[dict]:
    """Levels worth drawing right now: non-deprecated, near spot, deduped, capped.

    The band is what structurally prevents a June level from reappearing on an
    August chart -- it does not rely on anyone having remembered to deprecate it.
    """
    dep = deprecated_prices(key_levels)
    seen: set[float] = set()
    picked: list[dict] = []

    for lv in key_levels.get("levels") or []:
        try:
            price = round(float(lv["price"]), 2)
        except (KeyError, TypeError, ValueError):
            continue
        if price in dep or price in seen:
            continue
        if abs(price - spot) > band:
            continue
        seen.add(price)
        role = (lv.get("role") or "").strip().lower()
        picked.append(
            {
                "price": price,
                "role": role,
                "label": humanize_label(str(lv.get("label") or "")),
                "raw_label": lv.get("label"),
                "distance": round(price - spot, 2),
            }
        )

    picked.sort(key=lambda r: abs(r["distance"]))
    return picked[:max_levels]


def line_text(level: dict) -> str:
    """On-chart text, always TAG-prefixed so the line is identifiable as ours."""
    return f"{TAG}{level['label']} {level['price']:.2f}"


def overrides_for(level: dict) -> dict:
    role = level.get("role")
    color = COLOR_SUPPORT if role == "support" else COLOR_RESISTANCE if role == "resistance" else COLOR_NEUTRAL
    return {
        "linecolor": color,
        "linewidth": 1,
        "linestyle": 2,          # dashed -- visually distinct from J's solid hand-drawn work
        "showLabel": True,
        "textcolor": color,
        "fontsize": 11,
        "horzLabelsAlign": "right",
        "vertLabelsAlign": "top",
        "showPrice": False,      # the text already carries the price
    }


# --------------------------------------------------------------------------
# state
# --------------------------------------------------------------------------

def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def load_state() -> dict:
    if not STATE_FILE.exists():
        return {"schema_version": 1, "drawn": []}
    try:
        return load_json(STATE_FILE)
    except (json.JSONDecodeError, OSError):
        # A corrupt state file must not strand our drawings; the TAG orphan sweep
        # is the recovery path, so start clean rather than crash.
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
            fh.write(f"\n### BROKEN: chart-autodraw {stamp}\n- {message}\n")
    except OSError:
        pass


# --------------------------------------------------------------------------
# chart operations
# --------------------------------------------------------------------------

def _horizontal_lines(chart: TvChart) -> list[dict]:
    return [s for s in chart.list_shapes() if s.get("name") == "horizontal_line"]

def remove_own_lines(chart: TvChart, state: dict, dry_run: bool) -> list[dict]:
    """Remove every line provably ours: recorded id, or TAG-prefixed text (orphans)."""
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


def sweep_legacy(chart: TvChart, key_levels: dict, apply: bool) -> list[dict]:
    """Remove untagged horizontal lines whose price is an explicitly DEPRECATED level.

    This is the only path that touches a line we did not draw. The authorisation is
    not a guess about who drew it -- it is key-levels.json having already retired that
    exact price. Anything not on the deprecated list is left strictly alone.
    """
    dep = deprecated_prices(key_levels)
    if not dep:
        return []

    hits: list[dict] = []
    for shape in _horizontal_lines(chart):
        text = chart.shape_text(shape["id"]) or ""
        if text.startswith(TAG):
            continue  # ours; handled by remove_own_lines
        price = chart.evaluate(
            "(function(){try{var s=%s.getShapeById(%s);var p=s.getPoints();"
            "return p&&p.length?p[0].price:null;}catch(e){return null;}})()"
            % ("window.TradingViewApi._activeChartWidgetWV.value()", json.dumps(shape["id"]))
        )
        if price is None:
            continue
        if round(float(price), 2) in dep:
            hits.append({"entity_id": shape["id"], "price": round(float(price), 2), "text": text})

    if not apply:
        return hits

    removed = []
    for h in hits:
        try:
            if chart.remove_entity(h["entity_id"]):
                removed.append(h)
        except TvCdpError:
            continue
    return removed


def draw_levels(chart: TvChart, levels: list[dict], dry_run: bool) -> list[dict]:
    drawn: list[dict] = []
    for lv in levels:
        text = line_text(lv)
        if dry_run:
            drawn.append({"entity_id": None, "price": lv["price"], "label": lv["label"], "text": text})
            continue
        eid = chart.create_horizontal_line(lv["price"], text, overrides_for(lv))
        drawn.append({"entity_id": eid, "price": lv["price"], "label": lv["label"], "text": text,
                      "role": lv["role"], "raw_label": lv["raw_label"]})
    return drawn


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Draw key-levels.json on the TradingView chart")
    ap.add_argument("--band", type=float, default=DEFAULT_BAND_DOLLARS,
                    help=f"only draw levels within +/- this many dollars of spot (default {DEFAULT_BAND_DOLLARS})")
    ap.add_argument("--max-levels", type=int, default=DEFAULT_MAX_LEVELS)
    ap.add_argument("--spot", type=float, default=None, help="override spot (default: chart last price)")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; touch nothing")
    ap.add_argument("--clear-only", action="store_true", help="remove our lines, draw nothing")
    ap.add_argument("--sweep-legacy", action="store_true",
                    help="also report/remove untagged lines at DEPRECATED prices")
    ap.add_argument("--apply", action="store_true", help="with --sweep-legacy, actually remove")
    args = ap.parse_args(argv)

    now = dt.datetime.now(ET)
    state = load_state()
    out: dict = {
        "schema_version": 1,
        "as_of": now.isoformat(),
        "tag": TAG,
        "band_dollars": args.band,
        "dry_run": bool(args.dry_run),
    }

    try:
        key_levels = load_json(KEY_LEVELS)
    except (OSError, json.JSONDecodeError) as exc:
        msg = f"key-levels.json unreadable: {exc}"
        print(f"ERROR {msg}")
        out.update(status="ERROR", message=msg, drawn=state.get("drawn", []))
        write_state(out)
        flag_status_md(msg)
        return 1

    try:
        with TvChart() as chart:
            chart.require_chart_api()
            spot = args.spot if args.spot is not None else chart.last_price()
            if spot is None:
                spot = float(key_levels.get("spot_at_compute") or 0) or None
            if spot is None:
                raise TvCdpError("could not determine spot from chart or key-levels.json")

            out["symbol"] = chart.symbol()
            out["spot"] = spot
            out["shapes_before"] = len(chart.list_shapes())

            removed = remove_own_lines(chart, state, args.dry_run)
            out["removed"] = removed

            legacy: list[dict] = []
            if args.sweep_legacy:
                legacy = sweep_legacy(chart, key_levels, apply=args.apply and not args.dry_run)
                out["legacy_%s" % ("removed" if (args.apply and not args.dry_run) else "candidates")] = legacy

            levels = select_levels(key_levels, spot, args.band, args.max_levels)
            out["selected"] = levels
            drawn = [] if args.clear_only else draw_levels(chart, levels, args.dry_run)
            out["drawn"] = drawn
            out["shapes_after"] = len(chart.list_shapes())
            out["status"] = "DRY_RUN" if args.dry_run else "OK"

    except TvCdpError as exc:
        # TradingView down is the normal off-hours state -> soft skip, exit 0.
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
        flag_status_md(f"draw_key_levels failed -- {msg}")
        return 1

    if not args.dry_run:
        write_state(out)

    print(
        f"{out['status']} spot={out.get('spot')} removed={len(out.get('removed') or [])} "
        f"drawn={len(out.get('drawn') or [])} shapes {out.get('shapes_before')} -> {out.get('shapes_after')}"
    )
    for d in out.get("drawn") or []:
        print(f"   {d['price']:>8.2f}  {d['text']}")
    for k in ("legacy_candidates", "legacy_removed"):
        for h in out.get(k) or []:
            print(f"   LEGACY[{k.split('_')[-1]}] {h['price']:>8.2f}  {h['text'][:44]!r}  {h['entity_id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
